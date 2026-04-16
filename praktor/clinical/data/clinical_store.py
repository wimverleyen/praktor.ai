"""
Lightweight SQLite store for clinical demo data.

In production, replace each _query_* method with calls to your data warehouse
(Snowflake, Databricks, BigQuery) or FHIR R4 API. The tool interfaces remain
identical — only the data backend changes.

Populated by: scripts/init_member_brain.py --seed-demo
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path

_DEFAULT_CLINICAL_DB = os.getenv(
    "PRAKTOR_CLINICAL_DB",
    str(Path.home() / ".praktor" / "clinical_data.db"),
)

_SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS members (
    member_id_hash  TEXT PRIMARY KEY,
    plan_id         TEXT,
    measurement_year INTEGER,
    language        TEXT DEFAULT 'en',
    health_literacy TEXT DEFAULT 'medium',  -- low/medium/high
    pcp_id          TEXT,
    pcp_name        TEXT,
    pcp_language    TEXT DEFAULT 'en',
    sdoh_risk       TEXT DEFAULT 'low',     -- low/medium/high
    sdoh_barriers   TEXT,                   -- JSON list
    pharmacy_name   TEXT,
    pharmacy_miles  REAL DEFAULT 1.0
);

CREATE TABLE IF NOT EXISTS hedis_gaps (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    member_id_hash  TEXT NOT NULL,
    measure_id      TEXT NOT NULL,
    measure_name    TEXT NOT NULL,
    stars_weight    REAL NOT NULL,
    measurement_year INTEGER NOT NULL,
    days_remaining  INTEGER NOT NULL,
    last_service_date TEXT,
    pdc_current     REAL,
    pdc_threshold   REAL DEFAULT 0.80,
    status          TEXT DEFAULT 'open'     -- open/closed/excluded
);

CREATE TABLE IF NOT EXISTS claims (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    member_id_hash  TEXT NOT NULL,
    service_date    TEXT NOT NULL,
    icd_codes       TEXT,   -- JSON list
    cpt_codes       TEXT,   -- JSON list
    ndc_code        TEXT,
    drug_name       TEXT,
    drug_class      TEXT,
    days_supply     INTEGER DEFAULT 0,
    quantity        REAL DEFAULT 0,
    provider_id     TEXT,
    claim_type      TEXT    -- rx/medical/lab
);

CREATE TABLE IF NOT EXISTS labs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    member_id_hash  TEXT NOT NULL,
    test_date       TEXT NOT NULL,
    test_name       TEXT NOT NULL,
    result_value    REAL,
    result_unit     TEXT,
    result_text     TEXT,
    loinc_code      TEXT,
    reference_range TEXT
);

CREATE TABLE IF NOT EXISTS vitals (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    member_id_hash  TEXT NOT NULL,
    recorded_date   TEXT NOT NULL,
    systolic_bp     INTEGER,
    diastolic_bp    INTEGER,
    weight_kg       REAL,
    bmi             REAL
);

CREATE TABLE IF NOT EXISTS outreach_history (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    member_id_hash  TEXT NOT NULL,
    contact_date    TEXT NOT NULL,
    channel         TEXT,   -- phone/letter/portal/sms
    measure_id      TEXT,
    outcome         TEXT,   -- reached/no_answer/refused/closed
    notes           TEXT
);

CREATE TABLE IF NOT EXISTS pdc_scores (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    member_id_hash  TEXT NOT NULL,
    drug_class      TEXT NOT NULL,
    measure_id      TEXT NOT NULL,
    pdc             REAL NOT NULL,
    fills_count     INTEGER DEFAULT 0,
    last_fill_date  TEXT,
    next_fill_due   TEXT,
    days_until_gap  INTEGER DEFAULT 0,
    computed_date   TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_gaps_member   ON hedis_gaps(member_id_hash);
CREATE INDEX IF NOT EXISTS idx_claims_member ON claims(member_id_hash);
CREATE INDEX IF NOT EXISTS idx_labs_member   ON labs(member_id_hash);
CREATE INDEX IF NOT EXISTS idx_pdc_member    ON pdc_scores(member_id_hash);
CREATE INDEX IF NOT EXISTS idx_outreach_member ON outreach_history(member_id_hash);
"""


class ClinicalStore:
    """Read/write interface for clinical demo data."""

    def __init__(self, db_path: str | None = None) -> None:
        self._db_path = db_path or _DEFAULT_CLINICAL_DB
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    # ------------------------------------------------------------------
    # Member
    # ------------------------------------------------------------------

    def get_member(self, member_id_hash: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM members WHERE member_id_hash = ?", (member_id_hash,)
            ).fetchone()
        return dict(row) if row else None

    def upsert_member(self, data: dict) -> None:
        with self._connect() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO members
                   (member_id_hash, plan_id, measurement_year, language,
                    health_literacy, pcp_id, pcp_name, pcp_language,
                    sdoh_risk, sdoh_barriers, pharmacy_name, pharmacy_miles)
                   VALUES (:member_id_hash, :plan_id, :measurement_year, :language,
                    :health_literacy, :pcp_id, :pcp_name, :pcp_language,
                    :sdoh_risk, :sdoh_barriers, :pharmacy_name, :pharmacy_miles)""",
                data,
            )

    # ------------------------------------------------------------------
    # HEDIS gaps
    # ------------------------------------------------------------------

    def get_open_gaps(self, member_id_hash: str) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM hedis_gaps WHERE member_id_hash = ? AND status = 'open' "
                "ORDER BY stars_weight DESC, days_remaining ASC",
                (member_id_hash,),
            ).fetchall()
        return [dict(r) for r in rows]

    def insert_gap(self, data: dict) -> None:
        with self._connect() as conn:
            conn.execute(
                """INSERT OR IGNORE INTO hedis_gaps
                   (member_id_hash, measure_id, measure_name, stars_weight,
                    measurement_year, days_remaining, last_service_date,
                    pdc_current, pdc_threshold, status)
                   VALUES (:member_id_hash, :measure_id, :measure_name, :stars_weight,
                    :measurement_year, :days_remaining, :last_service_date,
                    :pdc_current, :pdc_threshold, :status)""",
                data,
            )

    def close_gap(self, member_id_hash: str, measure_id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE hedis_gaps SET status = 'closed' WHERE member_id_hash = ? AND measure_id = ?",
                (member_id_hash, measure_id),
            )

    # ------------------------------------------------------------------
    # Claims
    # ------------------------------------------------------------------

    def get_claims(self, member_id_hash: str, drug_class: str | None = None,
                   limit: int = 50) -> list[dict]:
        if drug_class:
            with self._connect() as conn:
                rows = conn.execute(
                    "SELECT * FROM claims WHERE member_id_hash = ? AND drug_class = ? "
                    "ORDER BY service_date DESC LIMIT ?",
                    (member_id_hash, drug_class, limit),
                ).fetchall()
        else:
            with self._connect() as conn:
                rows = conn.execute(
                    "SELECT * FROM claims WHERE member_id_hash = ? "
                    "ORDER BY service_date DESC LIMIT ?",
                    (member_id_hash, limit),
                ).fetchall()
        return [dict(r) for r in rows]

    def insert_claim(self, data: dict) -> None:
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO claims
                   (member_id_hash, service_date, icd_codes, cpt_codes,
                    ndc_code, drug_name, drug_class, days_supply, quantity,
                    provider_id, claim_type)
                   VALUES (:member_id_hash, :service_date, :icd_codes, :cpt_codes,
                    :ndc_code, :drug_name, :drug_class, :days_supply, :quantity,
                    :provider_id, :claim_type)""",
                data,
            )

    # ------------------------------------------------------------------
    # Labs
    # ------------------------------------------------------------------

    def get_labs(self, member_id_hash: str, test_name: str | None = None,
                 limit: int = 20) -> list[dict]:
        if test_name:
            with self._connect() as conn:
                rows = conn.execute(
                    "SELECT * FROM labs WHERE member_id_hash = ? AND test_name LIKE ? "
                    "ORDER BY test_date DESC LIMIT ?",
                    (member_id_hash, f"%{test_name}%", limit),
                ).fetchall()
        else:
            with self._connect() as conn:
                rows = conn.execute(
                    "SELECT * FROM labs WHERE member_id_hash = ? "
                    "ORDER BY test_date DESC LIMIT ?",
                    (member_id_hash, limit),
                ).fetchall()
        return [dict(r) for r in rows]

    def insert_lab(self, data: dict) -> None:
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO labs
                   (member_id_hash, test_date, test_name, result_value,
                    result_unit, result_text, loinc_code, reference_range)
                   VALUES (:member_id_hash, :test_date, :test_name, :result_value,
                    :result_unit, :result_text, :loinc_code, :reference_range)""",
                data,
            )

    # ------------------------------------------------------------------
    # Outreach history
    # ------------------------------------------------------------------

    def get_outreach(self, member_id_hash: str, measure_id: str | None = None,
                     limit: int = 10) -> list[dict]:
        if measure_id:
            with self._connect() as conn:
                rows = conn.execute(
                    "SELECT * FROM outreach_history WHERE member_id_hash = ? AND measure_id = ? "
                    "ORDER BY contact_date DESC LIMIT ?",
                    (member_id_hash, measure_id, limit),
                ).fetchall()
        else:
            with self._connect() as conn:
                rows = conn.execute(
                    "SELECT * FROM outreach_history WHERE member_id_hash = ? "
                    "ORDER BY contact_date DESC LIMIT ?",
                    (member_id_hash, limit),
                ).fetchall()
        return [dict(r) for r in rows]

    def insert_outreach(self, data: dict) -> None:
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO outreach_history
                   (member_id_hash, contact_date, channel, measure_id, outcome, notes)
                   VALUES (:member_id_hash, :contact_date, :channel, :measure_id, :outcome, :notes)""",
                data,
            )

    # ------------------------------------------------------------------
    # PDC scores (pre-computed in ingestion)
    # ------------------------------------------------------------------

    def get_pdc(self, member_id_hash: str, drug_class: str | None = None) -> list[dict]:
        if drug_class:
            with self._connect() as conn:
                rows = conn.execute(
                    "SELECT * FROM pdc_scores WHERE member_id_hash = ? AND drug_class = ?",
                    (member_id_hash, drug_class),
                ).fetchall()
        else:
            with self._connect() as conn:
                rows = conn.execute(
                    "SELECT * FROM pdc_scores WHERE member_id_hash = ?",
                    (member_id_hash,),
                ).fetchall()
        return [dict(r) for r in rows]

    def upsert_pdc(self, data: dict) -> None:
        with self._connect() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO pdc_scores
                   (member_id_hash, drug_class, measure_id, pdc, fills_count,
                    last_fill_date, next_fill_due, days_until_gap, computed_date)
                   VALUES (:member_id_hash, :drug_class, :measure_id, :pdc, :fills_count,
                    :last_fill_date, :next_fill_due, :days_until_gap, :computed_date)""",
                data,
            )

    def get_vitals(self, member_id_hash: str, limit: int = 5) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM vitals WHERE member_id_hash = ? "
                "ORDER BY recorded_date DESC LIMIT ?",
                (member_id_hash, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def insert_vital(self, data: dict) -> None:
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO vitals
                   (member_id_hash, recorded_date, systolic_bp, diastolic_bp, weight_kg, bmi)
                   VALUES (:member_id_hash, :recorded_date, :systolic_bp, :diastolic_bp,
                    :weight_kg, :bmi)""",
                data,
            )


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_store: ClinicalStore | None = None


def get_clinical_store() -> ClinicalStore:
    global _store
    if _store is None:
        _store = ClinicalStore()
    return _store
