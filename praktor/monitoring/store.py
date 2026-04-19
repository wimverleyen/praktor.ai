"""
SQLite-backed persistent store for agent monitoring data.

Schema:
    agent_runs       — one row per completed agent.run()
    trajectory_steps — per-step breakdown (LLM calls, tool calls)
    judge_evals      — LLM-as-judge evaluation results
    kpi_events       — custom business KPI measurements

All writes are async-safe via asyncio.to_thread().
Reads return plain dicts for zero-dependency portability.

Usage:
    store = MonitoringStore()
    await store.insert_run(run_record)
    rows = await store.query_runs(agent="cover_letter", hours=24)
    summary = await store.aggregate(agent="cover_letter")
"""

from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

from praktor.settings import create_log

log = create_log()

_DEFAULT_DB = os.getenv(
    "PRAKTOR_MONITORING_DB",
    str(Path.home() / ".praktor" / "monitoring.db"),
)

_SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS agent_runs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      TEXT    NOT NULL,
    agent_type      TEXT    NOT NULL,
    model           TEXT    NOT NULL,
    timestamp       REAL    NOT NULL,
    duration_ms     REAL    DEFAULT 0,
    input_tokens    INTEGER DEFAULT 0,
    output_tokens   INTEGER DEFAULT 0,
    total_tokens    INTEGER DEFAULT 0,
    cost_usd        REAL    DEFAULT 0.0,
    passes          INTEGER DEFAULT 1,
    cached          INTEGER DEFAULT 0,
    error           TEXT,
    status          TEXT    DEFAULT 'ok',
    prompt_version  TEXT
);

CREATE TABLE IF NOT EXISTS trajectory_steps (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id      INTEGER NOT NULL REFERENCES agent_runs(id) ON DELETE CASCADE,
    step        INTEGER,
    kind        TEXT,
    tool_name   TEXT,
    latency_ms  REAL    DEFAULT 0,
    input_tokens  INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    cached      INTEGER DEFAULT 0,
    error       TEXT
);

CREATE TABLE IF NOT EXISTS judge_evals (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      TEXT    NOT NULL,
    agent_type      TEXT    NOT NULL,
    judge_type      TEXT    DEFAULT 'general',
    version_id      TEXT,
    score           REAL    NOT NULL,
    -- 5 base performance dimensions (all agents)
    accuracy        REAL,
    completeness    REAL,
    relevance       REAL,
    conciseness     REAL,
    clarity         REAL,
    -- HEDIS clinical extensions (hedis_gap agent)
    gap_identification_accuracy REAL,
    action_appropriateness      REAL,
    evidence_citation_quality   REAL,
    safety_flag_coverage        REAL,
    -- Diabetes extensions (diabetes_hedis agent)
    inertia_detection_accuracy     REAL,
    escalation_ladder_correctness  REAL,
    gap_stacking_completeness      REAL,
    evidence_anchor_quality        REAL,
    safety_exclusion_coverage      REAL,
    reasoning       TEXT,
    question        TEXT,
    timestamp       REAL    NOT NULL
);

CREATE TABLE IF NOT EXISTS kpi_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL,
    value       REAL    NOT NULL,
    tags        TEXT,
    timestamp   REAL    NOT NULL
);

CREATE TABLE IF NOT EXISTS hitl_reviews (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      TEXT NOT NULL,
    agent_type      TEXT NOT NULL,
    original_output TEXT,
    modified_output TEXT,
    action          TEXT DEFAULT 'pending',
    reviewer_notes  TEXT,
    reviewed_at     REAL,
    created_at      REAL,
    judge_score_pre  REAL,
    judge_score_post REAL
);

CREATE INDEX IF NOT EXISTS idx_hitl_session ON hitl_reviews(session_id);
CREATE INDEX IF NOT EXISTS idx_hitl_action  ON hitl_reviews(action);

CREATE INDEX IF NOT EXISTS idx_runs_agent     ON agent_runs(agent_type);
CREATE INDEX IF NOT EXISTS idx_runs_ts        ON agent_runs(timestamp);
CREATE INDEX IF NOT EXISTS idx_runs_session   ON agent_runs(session_id);
CREATE INDEX IF NOT EXISTS idx_judge_agent    ON judge_evals(agent_type);
CREATE INDEX IF NOT EXISTS idx_judge_type     ON judge_evals(judge_type);
CREATE INDEX IF NOT EXISTS idx_kpi_name       ON kpi_events(name);
"""


# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------

@dataclass
class RunRecord:
    """Normalized record from one completed agent.run()."""
    session_id: str
    agent_type: str
    model: str
    timestamp: float           # Unix epoch (UTC)
    duration_ms: float
    input_tokens: int
    output_tokens: int
    total_tokens: int
    cost_usd: float
    passes: int
    cached: bool
    error: str | None
    status: str                # "ok" | "error"
    prompt_version: str | None = None
    trajectory: list[dict] | None = None   # not persisted to agent_runs table


@dataclass
class JudgeEvalRecord:
    """
    One LLM-as-judge evaluation result.

    Always carries the 5 base performance dimensions.
    Clinical/domain extension fields are None for non-clinical agents.
    """
    session_id: str
    agent_type: str
    score: float
    timestamp: float
    judge_type: str = "general"      # "general" | "hedis" | "diabetes_hedis"
    version_id: str | None = None
    # 5 base performance dimensions
    accuracy: float | None = None
    completeness: float | None = None
    relevance: float | None = None
    conciseness: float | None = None
    clarity: float | None = None
    # HEDIS clinical extensions
    gap_identification_accuracy: float | None = None
    action_appropriateness: float | None = None
    evidence_citation_quality: float | None = None
    safety_flag_coverage: float | None = None
    # Diabetes extensions
    inertia_detection_accuracy: float | None = None
    escalation_ladder_correctness: float | None = None
    gap_stacking_completeness: float | None = None
    evidence_anchor_quality: float | None = None
    safety_exclusion_coverage: float | None = None
    reasoning: str = ""
    question: str = ""


@dataclass
class KPIRecord:
    """One business KPI measurement."""
    name: str
    value: float
    timestamp: float
    tags: dict[str, str] | None = None


@dataclass
class HITLReviewRecord:
    session_id: str
    agent_type: str
    original_output: str
    action: str = "pending"          # pending / approved / rejected / modified
    modified_output: str | None = None
    reviewer_notes: str | None = None
    reviewed_at: float | None = None
    created_at: float | None = None
    judge_score_pre: float | None = None
    judge_score_post: float | None = None


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------

class MonitoringStore:
    """
    SQLite-backed persistent store.

    Thread/async safe: all writes go through asyncio.to_thread() so they
    never block the event loop.
    """

    def __init__(self, db_path: str | None = None) -> None:
        self._db_path = db_path or _DEFAULT_DB
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    async def insert_run(self, record: RunRecord) -> int:
        """Insert a run record and its trajectory steps. Returns the run id."""
        return await asyncio.to_thread(self._insert_run_sync, record)

    def _insert_run_sync(self, record: RunRecord) -> int:
        with self._connect() as conn:
            cursor = conn.execute(
                """INSERT INTO agent_runs
                   (session_id, agent_type, model, timestamp, duration_ms,
                    input_tokens, output_tokens, total_tokens, cost_usd,
                    passes, cached, error, status, prompt_version)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    record.session_id, record.agent_type, record.model,
                    record.timestamp, record.duration_ms,
                    record.input_tokens, record.output_tokens, record.total_tokens,
                    record.cost_usd, record.passes,
                    int(record.cached), record.error,
                    record.status, record.prompt_version,
                ),
            )
            run_id = cursor.lastrowid

            if record.trajectory:
                conn.executemany(
                    """INSERT INTO trajectory_steps
                       (run_id, step, kind, tool_name, latency_ms,
                        input_tokens, output_tokens, cached, error)
                       VALUES (?,?,?,?,?,?,?,?,?)""",
                    [
                        (
                            run_id, step["step"], step["kind"],
                            step.get("tool_name"), step.get("latency_ms", 0),
                            step.get("input_tokens", 0), step.get("output_tokens", 0),
                            int(step.get("cached", False)), step.get("error"),
                        )
                        for step in record.trajectory
                    ],
                )
            return run_id

    async def insert_judge_eval(self, record: JudgeEvalRecord) -> None:
        await asyncio.to_thread(self._insert_judge_sync, record)

    def _insert_judge_sync(self, record: JudgeEvalRecord) -> None:
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO judge_evals
                   (session_id, agent_type, judge_type, version_id, score,
                    accuracy, completeness, relevance, conciseness, clarity,
                    gap_identification_accuracy, action_appropriateness,
                    evidence_citation_quality, safety_flag_coverage,
                    inertia_detection_accuracy, escalation_ladder_correctness,
                    gap_stacking_completeness, evidence_anchor_quality,
                    safety_exclusion_coverage,
                    reasoning, question, timestamp)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    record.session_id, record.agent_type, record.judge_type,
                    record.version_id, record.score,
                    record.accuracy, record.completeness, record.relevance,
                    record.conciseness, record.clarity,
                    record.gap_identification_accuracy, record.action_appropriateness,
                    record.evidence_citation_quality, record.safety_flag_coverage,
                    record.inertia_detection_accuracy, record.escalation_ladder_correctness,
                    record.gap_stacking_completeness, record.evidence_anchor_quality,
                    record.safety_exclusion_coverage,
                    record.reasoning, record.question, record.timestamp,
                ),
            )

    async def insert_kpi(self, record: KPIRecord) -> None:
        await asyncio.to_thread(self._insert_kpi_sync, record)

    def _insert_kpi_sync(self, record: KPIRecord) -> None:
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO kpi_events (name, value, tags, timestamp)
                   VALUES (?,?,?,?)""",
                (
                    record.name, record.value,
                    json.dumps(record.tags) if record.tags else None,
                    record.timestamp,
                ),
            )

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    async def query_runs(
        self,
        agent: str | None = None,
        model: str | None = None,
        hours: float = 24,
        status: str | None = None,
        limit: int = 1000,
    ) -> list[dict]:
        return await asyncio.to_thread(
            self._query_runs_sync, agent, model, hours, status, limit
        )

    def _query_runs_sync(
        self,
        agent: str | None,
        model: str | None,
        hours: float,
        status: str | None,
        limit: int,
    ) -> list[dict]:
        since = time.time() - hours * 3600
        clauses = ["timestamp >= ?"]
        params: list[Any] = [since]

        if agent:
            clauses.append("agent_type = ?")
            params.append(agent)
        if model:
            clauses.append("model = ?")
            params.append(model)
        if status:
            clauses.append("status = ?")
            params.append(status)

        where = " AND ".join(clauses)
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM agent_runs WHERE {where} ORDER BY timestamp DESC LIMIT ?",
                params + [limit],
            ).fetchall()
        return [dict(r) for r in rows]

    async def aggregate(
        self,
        agent: str | None = None,
        hours: float = 24,
        judge_type: str | None = None,
    ) -> dict[str, Any]:
        """
        Return a summary dict for dashboard / CLI display.

        Keys:
            total_runs, ok_runs, error_runs, error_rate
            total_tokens, total_cost_usd
            avg_duration_ms, p95_duration_ms
            cache_hit_rate
            avg_judge_score, judge_eval_count
            by_agent: {name: {runs, tokens, cost, avg_latency}}
            by_model: {name: {runs, tokens, cost}}

        judge_type: when set, avg_judge_score only includes evals for that judge type.
            Prevents mixing 10-dim diabetes scores with 5-dim general scores.
        """
        return await asyncio.to_thread(self._aggregate_sync, agent, hours, judge_type)

    def _aggregate_sync(
        self,
        agent: str | None,
        hours: float,
        judge_type: str | None = None,
    ) -> dict[str, Any]:
        since = time.time() - hours * 3600
        params_filter: list[Any] = [since]
        agent_clause = ""
        if agent:
            agent_clause = "AND agent_type = ?"
            params_filter.append(agent)

        with self._connect() as conn:
            runs = conn.execute(
                f"SELECT * FROM agent_runs WHERE timestamp >= ? {agent_clause}",
                params_filter,
            ).fetchall()

            judge_params: list[Any] = [since]
            judge_agent_clause = agent_clause
            judge_type_clause = ""
            if agent:
                judge_params.append(agent)
            if judge_type is not None:
                judge_type_clause = "AND judge_type = ?"
                judge_params.append(judge_type)

            judge_rows = conn.execute(
                f"SELECT score FROM judge_evals "
                f"WHERE timestamp >= ? {judge_agent_clause} {judge_type_clause}",
                judge_params,
            ).fetchall()

        if not runs:
            return {
                "total_runs": 0, "ok_runs": 0, "error_runs": 0, "error_rate": 0.0,
                "total_tokens": 0, "total_cost_usd": 0.0,
                "avg_duration_ms": 0.0, "p95_duration_ms": 0.0,
                "cache_hit_rate": 0.0,
                "avg_judge_score": None, "judge_eval_count": 0,
                "by_agent": {}, "by_model": {},
            }

        durations = sorted(r["duration_ms"] for r in runs)
        n = len(durations)
        p95_idx = max(0, int(n * 0.95) - 1)
        total_tokens = sum(r["total_tokens"] for r in runs)
        total_cost = sum(r["cost_usd"] for r in runs)
        ok_runs = sum(1 for r in runs if r["status"] == "ok")
        error_runs = n - ok_runs
        cached = sum(1 for r in runs if r["cached"])

        judge_scores = [r["score"] for r in judge_rows]

        # By-agent breakdown
        by_agent: dict[str, dict] = {}
        by_model: dict[str, dict] = {}
        for r in runs:
            a = r["agent_type"]
            m = r["model"]
            for bucket, key in ((by_agent, a), (by_model, m)):
                if key not in bucket:
                    bucket[key] = {"runs": 0, "tokens": 0, "cost": 0.0, "latency_sum": 0.0}
                bucket[key]["runs"] += 1
                bucket[key]["tokens"] += r["total_tokens"]
                bucket[key]["cost"] += r["cost_usd"]
                bucket[key]["latency_sum"] += r["duration_ms"]

        for bucket in (by_agent, by_model):
            for key in bucket:
                runs_count = bucket[key]["runs"]
                bucket[key]["avg_latency"] = round(
                    bucket[key].pop("latency_sum") / runs_count, 1
                )

        return {
            "total_runs":       n,
            "ok_runs":          ok_runs,
            "error_runs":       error_runs,
            "error_rate":       round(error_runs / n, 4) if n else 0.0,
            "total_tokens":     total_tokens,
            "total_cost_usd":   round(total_cost, 6),
            "avg_duration_ms":  round(sum(durations) / n, 1),
            "p95_duration_ms":  round(durations[p95_idx], 1),
            "cache_hit_rate":   round(cached / n, 4) if n else 0.0,
            "avg_judge_score":  round(sum(judge_scores) / len(judge_scores), 2) if judge_scores else None,
            "judge_eval_count": len(judge_scores),
            "by_agent":         by_agent,
            "by_model":         by_model,
        }

    async def query_kpis(
        self,
        name: str | None = None,
        hours: float = 24,
        limit: int = 500,
    ) -> list[dict]:
        return await asyncio.to_thread(self._query_kpis_sync, name, hours, limit)

    def _query_kpis_sync(
        self, name: str | None, hours: float, limit: int
    ) -> list[dict]:
        since = time.time() - hours * 3600
        clauses = ["timestamp >= ?"]
        params: list[Any] = [since]
        if name:
            clauses.append("name = ?")
            params.append(name)
        where = " AND ".join(clauses)
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM kpi_events WHERE {where} ORDER BY timestamp DESC LIMIT ?",
                params + [limit],
            ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            if d.get("tags"):
                try:
                    d["tags"] = json.loads(d["tags"])
                except Exception:
                    pass
            result.append(d)
        return result

    # ------------------------------------------------------------------
    # HITL reviews
    # ------------------------------------------------------------------

    async def insert_hitl_review(self, record: "HITLReviewRecord") -> int:
        return await asyncio.to_thread(self._insert_hitl_sync, record)

    def _insert_hitl_sync(self, record: "HITLReviewRecord") -> int:
        import time as _time
        with self._connect() as conn:
            cur = conn.execute(
                """INSERT OR IGNORE INTO hitl_reviews
                   (session_id, agent_type, original_output, action,
                    modified_output, reviewer_notes, reviewed_at, created_at,
                    judge_score_pre, judge_score_post)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (
                    record.session_id, record.agent_type, record.original_output,
                    record.action, record.modified_output, record.reviewer_notes,
                    record.reviewed_at, record.created_at or _time.time(),
                    record.judge_score_pre, record.judge_score_post,
                ),
            )
            return cur.lastrowid or 0

    async def update_hitl_review(
        self, session_id: str, action: str,
        notes: str = "", modified_output: str | None = None,
        judge_score_post: float | None = None,
    ) -> None:
        import time as _time
        await asyncio.to_thread(
            self._update_hitl_sync, session_id, action, notes,
            modified_output, judge_score_post, _time.time(),
        )

    def _update_hitl_sync(
        self, session_id: str, action: str, notes: str,
        modified_output: str | None, judge_score_post: float | None, reviewed_at: float,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """UPDATE hitl_reviews
                   SET action=?, reviewer_notes=?, modified_output=?,
                       judge_score_post=?, reviewed_at=?
                   WHERE session_id=?""",
                (action, notes, modified_output, judge_score_post, reviewed_at, session_id),
            )

    async def query_hitl_queue(self, action: str | None = None, limit: int = 50) -> list[dict]:
        return await asyncio.to_thread(self._query_hitl_sync, action, limit)

    def _query_hitl_sync(self, action: str | None, limit: int) -> list[dict]:
        if action:
            with self._connect() as conn:
                rows = conn.execute(
                    "SELECT * FROM hitl_reviews WHERE action=? ORDER BY created_at DESC LIMIT ?",
                    (action, limit),
                ).fetchall()
        else:
            with self._connect() as conn:
                rows = conn.execute(
                    "SELECT * FROM hitl_reviews ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        return [dict(r) for r in rows]

    async def hitl_stats(self) -> dict:
        return await asyncio.to_thread(self._hitl_stats_sync)

    def _hitl_stats_sync(self) -> dict:
        with self._connect() as conn:
            total = conn.execute("SELECT COUNT(*) FROM hitl_reviews").fetchone()[0]
            pending = conn.execute(
                "SELECT COUNT(*) FROM hitl_reviews WHERE action='pending'"
            ).fetchone()[0]
            approved = conn.execute(
                "SELECT COUNT(*) FROM hitl_reviews WHERE action='approved'"
            ).fetchone()[0]
            rejected = conn.execute(
                "SELECT COUNT(*) FROM hitl_reviews WHERE action='rejected'"
            ).fetchone()[0]
            modified = conn.execute(
                "SELECT COUNT(*) FROM hitl_reviews WHERE action='modified'"
            ).fetchone()[0]
            avg_pre = conn.execute(
                "SELECT AVG(judge_score_pre) FROM hitl_reviews WHERE judge_score_pre IS NOT NULL"
            ).fetchone()[0]
            avg_post = conn.execute(
                "SELECT AVG(judge_score_post) FROM hitl_reviews WHERE judge_score_post IS NOT NULL"
            ).fetchone()[0]
        reviewed = total - pending
        return {
            "total": total, "pending": pending, "approved": approved,
            "rejected": rejected, "modified": modified,
            "approval_rate": approved / reviewed if reviewed > 0 else 0.0,
            "modification_rate": modified / reviewed if reviewed > 0 else 0.0,
            "avg_judge_score_pre": avg_pre or 0.0,
            "avg_judge_score_post": avg_post or 0.0,
        }

    # ------------------------------------------------------------------
    # Production eval: query runs without judge evaluations
    # ------------------------------------------------------------------

    async def query_unjudged_runs(
        self, agent_type: str | None = None, hours: float = 24, limit: int = 20
    ) -> list[dict]:
        """Return recent runs that have no corresponding judge_eval row."""
        return await asyncio.to_thread(self._query_unjudged_sync, agent_type, hours, limit)

    def _query_unjudged_sync(
        self, agent_type: str | None, hours: float, limit: int
    ) -> list[dict]:
        import time as _time
        since = _time.time() - hours * 3600
        agent_clause = "AND r.agent_type = ?" if agent_type else ""
        params = [since] + ([agent_type] if agent_type else []) + [limit]
        with self._connect() as conn:
            rows = conn.execute(
                f"""SELECT r.* FROM agent_runs r
                    LEFT JOIN judge_evals j ON j.session_id = r.session_id
                    WHERE r.timestamp >= ? AND r.status = 'ok'
                    {agent_clause}
                    AND j.id IS NULL
                    ORDER BY r.timestamp DESC LIMIT ?""",
                params,
            ).fetchall()
        result = []
        for row in rows:
            d = dict(row)
            if d.get("trajectory"):
                try:
                    d["trajectory"] = json.loads(d["trajectory"])
                except Exception:
                    pass
            result.append(d)
        return result

    def _query_kpis_latest_sync(self) -> dict[str, float]:
        """
        Return the most recent value for each KPI name from SQLite.

        Used by the Prometheus sync loop so that KPIs written by separate
        processes (e.g. `python -m praktor eval`) are visible on the
        consumer's Prometheus endpoint — both share the same SQLite file.
        """
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT name, value FROM kpi_events
                   WHERE id IN (
                       SELECT MAX(id) FROM kpi_events GROUP BY name
                   )"""
            ).fetchall()
        return {r["name"]: r["value"] for r in rows}
