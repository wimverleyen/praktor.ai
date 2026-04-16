"""
HIPAA-compliant audit trail for clinical agent operations.

Every access to member data, every FAISS read/write, and every LLM call on
clinical data is logged here. Stored in SQLite alongside the monitoring store.

HIPAA minimum retention: 6 years. Set PRAKTOR_AUDIT_DB env var to override path.
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from settings import create_log

log = create_log()

_DEFAULT_AUDIT_DB = os.getenv(
    "PRAKTOR_AUDIT_DB",
    str(Path.home() / ".praktor" / "clinical_audit.db"),
)

_SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS audit_events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp       REAL    NOT NULL,
    event_type      TEXT    NOT NULL,
    member_id_hash  TEXT,
    agent_session   TEXT,
    action          TEXT    NOT NULL,
    data_source     TEXT,
    span_id         TEXT,
    outcome         TEXT    NOT NULL,
    details         TEXT
);

CREATE INDEX IF NOT EXISTS idx_audit_ts     ON audit_events(timestamp);
CREATE INDEX IF NOT EXISTS idx_audit_member ON audit_events(member_id_hash);
CREATE INDEX IF NOT EXISTS idx_audit_type   ON audit_events(event_type);
"""

AuditEventType = Literal[
    "data_access",       # member data read from any source
    "faiss_write",       # chunk written to member FAISS shard
    "faiss_read",        # similarity search on member shard
    "llm_call",          # LLM invoked with member context
    "phi_gate_pass",     # phi_scrubbed=True validated
    "phi_gate_fail",     # phi_scrubbed=False blocked (HIPAA incident)
    "recommendation",    # NextBestAction produced
    "care_mgr_approve",  # care manager accepted recommendation
    "care_mgr_modify",   # care manager modified recommendation
    "care_mgr_reject",   # care manager rejected recommendation
    "gap_closed",        # HEDIS gap confirmed closed
]


@dataclass
class AuditEvent:
    event_type: AuditEventType
    action: str
    outcome: Literal["success", "blocked", "error"]
    member_id_hash: str | None = None
    agent_session: str | None = None
    data_source: str | None = None
    span_id: str | None = None
    details: dict | None = None
    timestamp: float | None = None


class ClinicalAuditLog:
    """Write-only audit log. Never deletes. Append-only by design."""

    def __init__(self, db_path: str | None = None) -> None:
        self._db_path = db_path or _DEFAULT_AUDIT_DB
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def log(self, event: AuditEvent) -> None:
        ts = event.timestamp or time.time()
        try:
            with self._connect() as conn:
                conn.execute(
                    """INSERT INTO audit_events
                       (timestamp, event_type, member_id_hash, agent_session,
                        action, data_source, span_id, outcome, details)
                       VALUES (?,?,?,?,?,?,?,?,?)""",
                    (
                        ts,
                        event.event_type,
                        event.member_id_hash,
                        event.agent_session,
                        event.action,
                        event.data_source,
                        event.span_id,
                        event.outcome,
                        json.dumps(event.details) if event.details else None,
                    ),
                )
        except Exception as e:
            # Audit log failure must never silently swallow — re-raise after logging
            log.error(f"ClinicalAuditLog write failed: {e}")
            raise

    def query(
        self,
        member_id_hash: str | None = None,
        event_type: str | None = None,
        hours: float = 24,
        limit: int = 500,
    ) -> list[dict]:
        since = time.time() - hours * 3600
        clauses = ["timestamp >= ?"]
        params: list = [since]
        if member_id_hash:
            clauses.append("member_id_hash = ?")
            params.append(member_id_hash)
        if event_type:
            clauses.append("event_type = ?")
            params.append(event_type)
        where = " AND ".join(clauses)
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM audit_events WHERE {where} ORDER BY timestamp DESC LIMIT ?",
                params + [limit],
            ).fetchall()
        return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_audit_log: ClinicalAuditLog | None = None


def get_audit_log() -> ClinicalAuditLog:
    global _audit_log
    if _audit_log is None:
        _audit_log = ClinicalAuditLog()
    return _audit_log


def audit(
    event_type: AuditEventType,
    action: str,
    outcome: Literal["success", "blocked", "error"] = "success",
    **kwargs,
) -> None:
    """Convenience function for one-line audit logging throughout the codebase."""
    get_audit_log().log(AuditEvent(
        event_type=event_type,
        action=action,
        outcome=outcome,
        **kwargs,
    ))
