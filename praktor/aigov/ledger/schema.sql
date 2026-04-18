-- AIGov Framework v0.3 §12 — DuckDB Warehouse Schema
-- Adapted from the canonical AIGov spec for DuckDB syntax.
-- Load with: praktor/aigov/ledger/store.py on first connection.
--
-- Grain of core fact: one row per enforcement event per (agent, obligation, enforcement_point).
-- Everything else is a derived view or rollup.

-- ---------------------------------------------------------------------------
-- Core fact table
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS fact_obligation_event (
  event_id              VARCHAR PRIMARY KEY,
  schema_version        VARCHAR NOT NULL DEFAULT '1.0',
  event_ts              TIMESTAMP NOT NULL,
  ingest_ts             TIMESTAMP NOT NULL,

  tenant_id             VARCHAR NOT NULL,
  agent_id              VARCHAR NOT NULL,
  agent_version         VARCHAR NOT NULL DEFAULT '0.0.0',
  agent_pattern         VARCHAR NOT NULL DEFAULT 'B1',
  deployment_env        VARCHAR NOT NULL DEFAULT 'dev',
  cim_version           VARCHAR NOT NULL DEFAULT '0.0.0',
  bundle_id             VARCHAR NOT NULL DEFAULT 'unknown',

  obligation_id         VARCHAR NOT NULL,
  enforcement_point     VARCHAR NOT NULL,  -- G-BUILD, G-TEST, G-RUN
  measurement_technique VARCHAR NOT NULL DEFAULT '',

  predicate_result      VARCHAR NOT NULL,  -- PASS, FAIL, WAIVED, NA
  severity              VARCHAR DEFAULT 'info',
  waiver_id             VARCHAR,
  deferred_reason       VARCHAR DEFAULT '',

  evidence_uri          VARCHAR NOT NULL DEFAULT '',
  evidence_sha256       VARCHAR NOT NULL DEFAULT '',
  evidence_size_bytes   INTEGER DEFAULT 0,
  evidence_redacted     BOOLEAN DEFAULT TRUE,

  reviewer_id           VARCHAR,
  regulatory_tags       VARCHAR[],
  trace_id              VARCHAR DEFAULT '',
  span_id               VARCHAR DEFAULT '',

  source_kind           VARCHAR NOT NULL DEFAULT 'praktor_aigov',
  source_version        VARCHAR DEFAULT '0.5.0',
  source_host           VARCHAR DEFAULT ''
);

-- Index for scoreboard queries: latest event per (tenant, agent, obligation, point)
CREATE INDEX IF NOT EXISTS idx_fact_event_key
  ON fact_obligation_event (tenant_id, agent_id, obligation_id, enforcement_point, event_ts);

-- Index for evidence pack queries (regulatory tag lookup)
CREATE INDEX IF NOT EXISTS idx_fact_event_agent_ts
  ON fact_obligation_event (agent_id, event_ts);

-- ---------------------------------------------------------------------------
-- Status snapshot — daily grain for trend analysis
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS fact_obligation_status_snapshot (
  snapshot_date     DATE NOT NULL,
  tenant_id         VARCHAR NOT NULL,
  agent_id          VARCHAR NOT NULL,
  obligation_id     VARCHAR NOT NULL,
  status            VARCHAR NOT NULL,  -- GREEN, AMBER, RED, GREY
  pass_events       INTEGER NOT NULL DEFAULT 0,
  fail_events       INTEGER NOT NULL DEFAULT 0,
  waived_events     INTEGER NOT NULL DEFAULT 0,
  na_events         INTEGER NOT NULL DEFAULT 0,
  pass_rate         DOUBLE,
  last_evidence_ts  TIMESTAMP,
  mttr_seconds      INTEGER,
  PRIMARY KEY (snapshot_date, tenant_id, agent_id, obligation_id)
);

-- ---------------------------------------------------------------------------
-- Violation intervals — one row per RED interval per (agent, obligation, point)
-- Opened on first FAIL event; closed when next PASS event arrives.
-- MTTR = closed_ts - opened_ts.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS fact_violation (
  violation_id       VARCHAR PRIMARY KEY,
  tenant_id          VARCHAR,
  agent_id           VARCHAR,
  obligation_id      VARCHAR,
  enforcement_point  VARCHAR,
  opened_ts          TIMESTAMP,
  closed_ts          TIMESTAMP,
  mttr_seconds       INTEGER,
  root_cause_tag     VARCHAR,
  opening_event_id   VARCHAR NOT NULL,
  closing_event_id   VARCHAR,
  severity           VARCHAR,
  regulatory_tags    VARCHAR[]
);

CREATE INDEX IF NOT EXISTS idx_violation_key
  ON fact_violation (tenant_id, agent_id, obligation_id, enforcement_point);
