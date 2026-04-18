"""Tests for praktor.aigov.ledger.scoreboard."""
import pytest

from praktor.aigov.event import EnforcementPoint, ObligationEvent, PredicateResult
from praktor.aigov.ledger.scoreboard import (
    AMBER,
    GREEN,
    GREY,
    RED,
    ScoreboardRow,
    scoreboard_current,
    status_summary,
)
from praktor.aigov.ledger.store import LedgerStore


def _event(
    obligation_id="O2",
    enforcement_point=EnforcementPoint.G_RUN,
    predicate_result=PredicateResult.PASS,
    agent_id="agent-1",
    tenant_id="acme",
    **kwargs,
) -> ObligationEvent:
    return ObligationEvent(
        obligation_id=obligation_id,
        enforcement_point=enforcement_point,
        predicate_result=predicate_result,
        agent_id=agent_id,
        tenant_id=tenant_id,
        **kwargs,
    )


@pytest.fixture()
def store(tmp_path):
    return LedgerStore(db_path=tmp_path / "test.duckdb")


class TestScoreboardCurrent:
    @pytest.mark.asyncio
    async def test_empty_store_returns_empty(self, store):
        rows = scoreboard_current(store)
        assert rows == []

    @pytest.mark.asyncio
    async def test_pass_maps_to_green(self, store):
        await store.write_event(_event(predicate_result=PredicateResult.PASS))
        rows = scoreboard_current(store)
        assert len(rows) == 1
        assert rows[0].status == GREEN
        assert rows[0].predicate_result == "PASS"

    @pytest.mark.asyncio
    async def test_fail_maps_to_red(self, store):
        await store.write_event(_event(predicate_result=PredicateResult.FAIL))
        rows = scoreboard_current(store)
        assert rows[0].status == RED

    @pytest.mark.asyncio
    async def test_na_maps_to_amber(self, store):
        await store.write_event(
            _event(predicate_result=PredicateResult.NA, deferred_reason="no_infra")
        )
        rows = scoreboard_current(store)
        assert rows[0].status == AMBER
        assert rows[0].deferred_reason == "no_infra"

    @pytest.mark.asyncio
    async def test_waived_maps_to_green(self, store):
        await store.write_event(_event(predicate_result=PredicateResult.WAIVED))
        rows = scoreboard_current(store)
        assert rows[0].status == GREEN

    @pytest.mark.asyncio
    async def test_latest_event_wins(self, store):
        """Older FAIL + newer PASS → GREEN."""
        await store.write_event(
            _event(predicate_result=PredicateResult.FAIL, event_ts="2024-01-01T00:00:00Z")
        )
        await store.write_event(
            _event(predicate_result=PredicateResult.PASS, event_ts="2024-01-02T00:00:00Z")
        )
        rows = scoreboard_current(store)
        assert len(rows) == 1
        assert rows[0].status == GREEN

    @pytest.mark.asyncio
    async def test_latest_event_wins_reverse(self, store):
        """Older PASS + newer FAIL → RED."""
        await store.write_event(
            _event(predicate_result=PredicateResult.PASS, event_ts="2024-01-01T00:00:00Z")
        )
        await store.write_event(
            _event(predicate_result=PredicateResult.FAIL, event_ts="2024-01-02T00:00:00Z")
        )
        rows = scoreboard_current(store)
        assert rows[0].status == RED

    @pytest.mark.asyncio
    async def test_separate_keys_distinct_rows(self, store):
        """Different (obligation, enforcement_point) combinations → separate rows."""
        await store.write_event(_event(obligation_id="O2", enforcement_point=EnforcementPoint.G_RUN))
        await store.write_event(_event(obligation_id="O3", enforcement_point=EnforcementPoint.G_RUN))
        await store.write_event(_event(obligation_id="O2", enforcement_point=EnforcementPoint.G_BUILD))
        rows = scoreboard_current(store)
        assert len(rows) == 3

    @pytest.mark.asyncio
    async def test_filter_by_agent_id(self, store):
        await store.write_event(_event(agent_id="agent-A"))
        await store.write_event(_event(agent_id="agent-B"))
        rows = scoreboard_current(store, agent_id="agent-A")
        assert all(r.agent_id == "agent-A" for r in rows)
        assert len(rows) == 1

    @pytest.mark.asyncio
    async def test_filter_by_tenant_id(self, store):
        await store.write_event(_event(tenant_id="acme"))
        await store.write_event(_event(tenant_id="globex"))
        rows = scoreboard_current(store, tenant_id="globex")
        assert all(r.tenant_id == "globex" for r in rows)
        assert len(rows) == 1

    @pytest.mark.asyncio
    async def test_filter_by_agent_and_tenant(self, store):
        await store.write_event(_event(agent_id="a1", tenant_id="acme"))
        await store.write_event(_event(agent_id="a2", tenant_id="acme"))
        await store.write_event(_event(agent_id="a1", tenant_id="globex"))
        rows = scoreboard_current(store, agent_id="a1", tenant_id="acme")
        assert len(rows) == 1
        assert rows[0].agent_id == "a1"
        assert rows[0].tenant_id == "acme"

    @pytest.mark.asyncio
    async def test_row_fields(self, store):
        await store.write_event(_event(
            obligation_id="O3",
            enforcement_point=EnforcementPoint.G_TEST,
            predicate_result=PredicateResult.FAIL,
            agent_id="myagent",
            tenant_id="mytenant",
        ))
        rows = scoreboard_current(store)
        r = rows[0]
        assert r.obligation_id == "O3"
        assert r.enforcement_point == "G-TEST"
        assert r.agent_id == "myagent"
        assert r.tenant_id == "mytenant"
        assert r.last_event_ts


class TestStatusSummary:
    def test_empty_is_grey(self):
        assert status_summary([]) == GREY

    def test_all_green_is_green(self):
        rows = [
            ScoreboardRow("t", "a", "O2", "G-RUN", GREEN, "PASS", "", "2024-01-01"),
            ScoreboardRow("t", "a", "O3", "G-RUN", GREEN, "PASS", "", "2024-01-01"),
        ]
        assert status_summary(rows) == GREEN

    def test_any_amber_is_amber(self):
        rows = [
            ScoreboardRow("t", "a", "O2", "G-RUN", GREEN, "PASS", "", "2024-01-01"),
            ScoreboardRow("t", "a", "O4", "G-RUN", AMBER, "NA", "deferred", "2024-01-01"),
        ]
        assert status_summary(rows) == AMBER

    def test_any_red_beats_amber(self):
        rows = [
            ScoreboardRow("t", "a", "O2", "G-RUN", GREEN, "PASS", "", "2024-01-01"),
            ScoreboardRow("t", "a", "O3", "G-RUN", RED, "FAIL", "", "2024-01-01"),
            ScoreboardRow("t", "a", "O4", "G-RUN", AMBER, "NA", "deferred", "2024-01-01"),
        ]
        assert status_summary(rows) == RED
