"""
Gap closure outcome tracker.

Records whether recommended actions resulted in gap closure at 30/60/90 days.
This is the ground truth signal that feeds the LLM-as-judge and PromptOptimizer.

Every approved recommendation creates a pending_outcome row.
Weekly batch job resolves outcomes by checking the gap registry.
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
import os

from settings import create_log

log = create_log()

_DEFAULT_TRACKER_DB = os.getenv(
    "PRAKTOR_CLINICAL_DB",
    str(Path.home() / ".praktor" / "clinical_data.db"),
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS recommendations (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    member_id_hash  TEXT NOT NULL,
    measure_id      TEXT NOT NULL,
    action_type     TEXT NOT NULL,
    priority_score  REAL DEFAULT 0,
    closure_probability REAL DEFAULT 0,
    rationale       TEXT,
    draft_content   TEXT,
    language        TEXT DEFAULT 'en',
    care_mgr_action TEXT DEFAULT 'pending',  -- pending/approved/modified/rejected
    care_mgr_notes  TEXT,
    created_at      REAL NOT NULL,
    resolved_at     REAL,
    outcome         TEXT DEFAULT 'pending',  -- pending/closed/not_closed/excluded
    span_id         TEXT
);

CREATE INDEX IF NOT EXISTS idx_rec_member  ON recommendations(member_id_hash);
CREATE INDEX IF NOT EXISTS idx_rec_measure ON recommendations(measure_id);
CREATE INDEX IF NOT EXISTS idx_rec_outcome ON recommendations(outcome);
"""


class ClosureTracker:
    """Records recommendations and tracks their eventual outcomes."""

    def __init__(self, db_path: str | None = None) -> None:
        self._db_path = db_path or _DEFAULT_TRACKER_DB
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def record_recommendation(self, rec: dict) -> int:
        """Store a new recommendation. Returns the row id."""
        with self._connect() as conn:
            cursor = conn.execute(
                """INSERT INTO recommendations
                   (member_id_hash, measure_id, action_type, priority_score,
                    closure_probability, rationale, draft_content, language,
                    care_mgr_action, created_at, outcome, span_id)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    rec["member_id_hash"],
                    rec.get("measure_id", "unknown"),
                    rec.get("action_type", "unknown"),
                    rec.get("priority_score", 0.0),
                    rec.get("closure_probability", 0.0),
                    rec.get("rationale", ""),
                    rec.get("draft_content", ""),
                    rec.get("language", "en"),
                    "pending",
                    time.time(),
                    "pending",
                    rec.get("span_id", ""),
                ),
            )
            return cursor.lastrowid

    def record_care_mgr_action(
        self,
        rec_id: int,
        action: str,          # approved/modified/rejected
        notes: str = "",
        modified_content: str | None = None,
    ) -> None:
        with self._connect() as conn:
            if modified_content:
                conn.execute(
                    "UPDATE recommendations SET care_mgr_action=?, care_mgr_notes=?, "
                    "draft_content=? WHERE id=?",
                    (action, notes, modified_content, rec_id),
                )
            else:
                conn.execute(
                    "UPDATE recommendations SET care_mgr_action=?, care_mgr_notes=? WHERE id=?",
                    (action, notes, rec_id),
                )

    def resolve_outcome(
        self,
        rec_id: int,
        outcome: str,    # closed/not_closed/excluded
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE recommendations SET outcome=?, resolved_at=? WHERE id=?",
                (outcome, time.time(), rec_id),
            )

    def get_review_queue(self, limit: int = 200) -> list[dict]:
        """Recommendations awaiting care manager review (care_mgr_action='pending')."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM recommendations WHERE care_mgr_action='pending' "
                "ORDER BY priority_score DESC, created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_pending(self, days_threshold: int = 30) -> list[dict]:
        """Recommendations awaiting outcome resolution (already approved, outcome TBD)."""
        cutoff = time.time() - days_threshold * 86400
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM recommendations WHERE outcome='pending' "
                "AND care_mgr_action='approved' AND created_at <= ? "
                "ORDER BY created_at ASC",
                (cutoff,),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_stats(self, hours: float = 24 * 30) -> dict:
        """Closure rate stats for prompt optimization feedback."""
        since = time.time() - hours * 3600
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT outcome, action_type, COUNT(*) as count "
                "FROM recommendations WHERE created_at >= ? AND outcome != 'pending' "
                "GROUP BY outcome, action_type",
                (since,),
            ).fetchall()

        total = sum(r["count"] for r in rows)
        closed = sum(r["count"] for r in rows if r["outcome"] == "closed")
        by_action: dict[str, dict] = {}
        for r in rows:
            at = r["action_type"]
            if at not in by_action:
                by_action[at] = {"closed": 0, "not_closed": 0}
            by_action[at][r["outcome"]] = r["count"]

        return {
            "total_resolved": total,
            "closed": closed,
            "closure_rate": round(closed / total, 3) if total else 0.0,
            "by_action": by_action,
        }

    def get_for_optimization(self, limit: int = 50) -> list[dict]:
        """
        Returns approved recommendations with known outcomes for PromptOptimizer.
        Format: [{"input": {...}, "output": "...", "score": ...}]
        """
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM recommendations WHERE outcome != 'pending' "
                "AND care_mgr_action = 'approved' ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()

        examples = []
        for r in rows:
            r = dict(r)
            score = 1.0 if r["outcome"] == "closed" else 0.0
            examples.append({
                "input": {
                    "member_id_hash": r["member_id_hash"],
                    "measure_id": r["measure_id"],
                },
                "output": r["draft_content"],
                "outcome": r["outcome"],
                "score": score,
            })
        return examples


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_tracker: ClosureTracker | None = None


def get_tracker() -> ClosureTracker:
    global _tracker
    if _tracker is None:
        _tracker = ClosureTracker()
    return _tracker
