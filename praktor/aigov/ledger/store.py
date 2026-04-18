"""
DuckDB ledger store for AIGov ObligationEvents.

One writer at a time within a process; filelock for cross-process safety.
All writes are async via asyncio.to_thread() (Decision 3A).

Default DB path: ~/.praktor/aigov-ledger.duckdb
Override via LedgerStore(db_path=...) or AIGOV_LEDGER_PATH env var.
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Optional

import duckdb
from filelock import FileLock

from praktor.aigov.event import ObligationEvent

_DEFAULT_DB_PATH = Path.home() / ".praktor" / "aigov-ledger.duckdb"
_SCHEMA_SQL = Path(__file__).parent / "schema.sql"

_INSERT_SQL = """
INSERT OR IGNORE INTO fact_obligation_event (
    event_id, schema_version, event_ts, ingest_ts,
    tenant_id, agent_id, agent_version, agent_pattern,
    deployment_env, cim_version, bundle_id,
    obligation_id, enforcement_point, measurement_technique,
    predicate_result, severity, waiver_id, deferred_reason,
    evidence_uri, evidence_sha256, evidence_size_bytes, evidence_redacted,
    reviewer_id, regulatory_tags, trace_id, span_id,
    source_kind, source_version, source_host
) VALUES (
    ?, ?, ?, ?,
    ?, ?, ?, ?,
    ?, ?, ?,
    ?, ?, ?,
    ?, ?, ?, ?,
    ?, ?, ?, ?,
    ?, ?, ?, ?,
    ?, ?, ?
)
"""


def _event_to_row(event: ObligationEvent) -> list:
    ev = event.evidence
    rv = event.reviewer
    return [
        event.event_id,
        event.schema_version,
        event.event_ts,
        event.ingest_ts,
        event.tenant_id,
        event.agent_id,
        event.agent_version,
        event.agent_pattern.value,
        event.deployment_env.value,
        event.cim_version,
        event.bundle_id,
        event.obligation_id,
        event.enforcement_point.value,
        event.measurement_technique,
        event.predicate_result.value,
        event.severity.value,
        event.waiver_id,
        event.deferred_reason,
        ev.uri if ev else "",
        ev.sha256 if ev else "",
        ev.size_bytes if ev else 0,
        ev.redacted if ev else True,
        rv.reviewer_id if rv else None,
        event.regulatory_tags,
        event.trace_id,
        event.span_id,
        event.source.kind,
        event.source.version,
        event.source.host,
    ]


class LedgerStore:
    """
    Append-only DuckDB store for ObligationEvents.

    Thread-safe within a process; cross-process writes serialized via FileLock.
    Use write_event() for all writes — it dispatches to a thread to avoid
    blocking the asyncio event loop.
    """

    def __init__(self, db_path: Optional[Path | str] = None) -> None:
        path_env = os.environ.get("AIGOV_LEDGER_PATH")
        self._db_path = Path(db_path or path_env or _DEFAULT_DB_PATH)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock_path = str(self._db_path) + ".lock"
        self._init_schema()

    # ------------------------------------------------------------------
    # Public async API
    # ------------------------------------------------------------------

    async def write_event(self, event: ObligationEvent) -> None:
        """Write one ObligationEvent to the ledger. Non-blocking."""
        await asyncio.to_thread(self._write_sync, event)

    async def write_events(self, events: list[ObligationEvent]) -> None:
        """Write a batch of ObligationEvents to the ledger. Non-blocking."""
        await asyncio.to_thread(self._write_batch_sync, events)

    # ------------------------------------------------------------------
    # Synchronous read (safe to call from threads or scoreboard queries)
    # ------------------------------------------------------------------

    def query_sync(self, sql: str, params: list | None = None) -> list[tuple]:
        """Run a read-only SELECT against the ledger. Returns list of tuples."""
        with duckdb.connect(str(self._db_path), read_only=True) as con:
            return con.execute(sql, params or []).fetchall()

    # ------------------------------------------------------------------
    # Internal sync helpers (run inside asyncio.to_thread)
    # ------------------------------------------------------------------

    def _init_schema(self) -> None:
        schema_sql = _SCHEMA_SQL.read_text()
        # Strip comment lines before splitting so semicolons inside comments
        # (e.g. "-- opened; closed") don't produce bogus partial statements.
        clean_lines = [
            line for line in schema_sql.splitlines()
            if not line.strip().startswith("--")
        ]
        statements = [s.strip() for s in "\n".join(clean_lines).split(";") if s.strip()]
        with FileLock(self._lock_path):
            with duckdb.connect(str(self._db_path)) as con:
                for stmt in statements:
                    con.execute(stmt)

    def _write_sync(self, event: ObligationEvent) -> None:
        row = _event_to_row(event)
        with FileLock(self._lock_path):
            with duckdb.connect(str(self._db_path)) as con:
                con.execute(_INSERT_SQL, row)

    def _write_batch_sync(self, events: list[ObligationEvent]) -> None:
        rows = [_event_to_row(e) for e in events]
        with FileLock(self._lock_path):
            with duckdb.connect(str(self._db_path)) as con:
                for row in rows:
                    con.execute(_INSERT_SQL, row)
