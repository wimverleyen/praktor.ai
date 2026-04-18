"""Tests for praktor.aigov.ledger.store — LedgerStore DuckDB write path."""
import pytest

from praktor.aigov.event import (
    EnforcementPoint,
    ObligationEvent,
    PredicateResult,
    Severity,
)
from praktor.aigov.ledger.store import LedgerStore


def _event(**kwargs) -> ObligationEvent:
    defaults = dict(
        obligation_id="O2",
        enforcement_point=EnforcementPoint.G_RUN,
        predicate_result=PredicateResult.PASS,
    )
    defaults.update(kwargs)
    return ObligationEvent(**defaults)


@pytest.fixture()
def store(tmp_path):
    return LedgerStore(db_path=tmp_path / "test.duckdb")


class TestLedgerStoreInit:
    def test_creates_db_file(self, tmp_path):
        db_path = tmp_path / "ledger.duckdb"
        assert not db_path.exists()
        LedgerStore(db_path=db_path)
        assert db_path.exists()

    def test_creates_parent_dirs(self, tmp_path):
        db_path = tmp_path / "nested" / "dir" / "ledger.duckdb"
        LedgerStore(db_path=db_path)
        assert db_path.exists()

    def test_schema_tables_exist(self, store):
        rows = store.query_sync(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'main' ORDER BY table_name"
        )
        names = {r[0] for r in rows}
        assert "fact_obligation_event" in names
        assert "fact_obligation_status_snapshot" in names
        assert "fact_violation" in names

    def test_reinit_is_idempotent(self, tmp_path):
        db_path = tmp_path / "idempotent.duckdb"
        LedgerStore(db_path=db_path)
        LedgerStore(db_path=db_path)  # second init — IF NOT EXISTS should not fail


class TestWriteEvent:
    @pytest.mark.asyncio
    async def test_write_single_event(self, store):
        ev = _event(agent_id="agent-1", tenant_id="acme")
        await store.write_event(ev)

        rows = store.query_sync(
            "SELECT event_id, obligation_id, predicate_result FROM fact_obligation_event"
        )
        assert len(rows) == 1
        assert rows[0][0] == ev.event_id
        assert rows[0][1] == "O2"
        assert rows[0][2] == "PASS"

    @pytest.mark.asyncio
    async def test_write_multiple_events(self, store):
        events = [_event(agent_id=f"agent-{i}") for i in range(5)]
        for ev in events:
            await store.write_event(ev)

        (count,) = store.query_sync("SELECT COUNT(*) FROM fact_obligation_event")[0]
        assert count == 5

    @pytest.mark.asyncio
    async def test_duplicate_event_id_ignored(self, store):
        ev = _event()
        await store.write_event(ev)
        await store.write_event(ev)  # same event_id — should not error or duplicate

        (count,) = store.query_sync("SELECT COUNT(*) FROM fact_obligation_event")[0]
        assert count == 1

    @pytest.mark.asyncio
    async def test_all_predicate_results_stored(self, store):
        for pr in PredicateResult:
            await store.write_event(_event(predicate_result=pr))

        rows = store.query_sync(
            "SELECT predicate_result FROM fact_obligation_event ORDER BY predicate_result"
        )
        stored = {r[0] for r in rows}
        assert stored == {"PASS", "FAIL", "WAIVED", "NA"}

    @pytest.mark.asyncio
    async def test_enforcement_point_stored(self, store):
        for ep in EnforcementPoint:
            await store.write_event(_event(enforcement_point=ep))

        rows = store.query_sync(
            "SELECT DISTINCT enforcement_point FROM fact_obligation_event"
        )
        stored = {r[0] for r in rows}
        assert stored == {"G-BUILD", "G-TEST", "G-RUN"}

    @pytest.mark.asyncio
    async def test_regulatory_tags_stored(self, store):
        ev = _event(regulatory_tags=["HIPAA", "EU-AI-ACT"])
        await store.write_event(ev)

        rows = store.query_sync(
            "SELECT regulatory_tags FROM fact_obligation_event WHERE event_id = ?",
            [ev.event_id],
        )
        assert rows[0][0] == ["HIPAA", "EU-AI-ACT"]

    @pytest.mark.asyncio
    async def test_null_optional_fields(self, store):
        ev = _event()  # no evidence, no reviewer, no waiver
        await store.write_event(ev)

        rows = store.query_sync(
            "SELECT waiver_id, reviewer_id FROM fact_obligation_event WHERE event_id = ?",
            [ev.event_id],
        )
        assert rows[0][0] is None
        assert rows[0][1] is None

    @pytest.mark.asyncio
    async def test_deferred_reason_stored(self, store):
        ev = _event(
            predicate_result=PredicateResult.NA,
            deferred_reason="fairlearn_not_configured",
        )
        await store.write_event(ev)

        rows = store.query_sync(
            "SELECT deferred_reason FROM fact_obligation_event WHERE event_id = ?",
            [ev.event_id],
        )
        assert rows[0][0] == "fairlearn_not_configured"


class TestWriteEvents:
    @pytest.mark.asyncio
    async def test_batch_write(self, store):
        events = [_event(obligation_id=f"O{i}") for i in range(1, 6)]
        await store.write_events(events)

        (count,) = store.query_sync("SELECT COUNT(*) FROM fact_obligation_event")[0]
        assert count == 5
