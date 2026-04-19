"""
PR7 — Tests for Agent.run() G-RUN obligation wiring.

Verifies that when an AgentDefinition has an obligation_bundle:
  - check_run() fires for every obligation after the response is collected
  - events are stamped with agent_id, bundle_id, agent_pattern
  - events are written to the ledger
  - agent output is unchanged (governance must never affect output)
  - obligation failures do NOT crash the agent
"""
import asyncio
import dataclasses
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import BaseModel

from praktor.aigov.bundle import ObligationBundle, minimal_bundle, standard_bundle
from praktor.aigov.event import AgentPattern, EnforcementPoint, PredicateResult
from praktor.aigov.ledger.scoreboard import scoreboard_current
from praktor.aigov.ledger.store import LedgerStore
from praktor.aigov.obligations.o7_auditable import O7Auditable
from praktor.aigov.obligations.o2_data_confinement import O2DataConfinement
from praktor.core.agent import Agent
from praktor.core.agent_definition import AgentDefinition


class _Input(BaseModel):
    agent_type: str = "test"
    query: str
    session_id: str = ""
    history: str = ""


def _defn(bundle: ObligationBundle, **kwargs) -> AgentDefinition:
    defaults = dict(
        name="grun_test",
        prompt_template="Answer {query}",
        input_schema=_Input,
        obligation_bundle=bundle,
    )
    defaults.update(kwargs)
    return AgentDefinition(**defaults)


def _mock_astream(response: str):
    """Return a side_effect for agent._adapter.astream that yields one chunk."""
    async def _gen(payload, call_span=None):
        yield response
    return _gen


# ---------------------------------------------------------------------------
# Core wiring — events reach the ledger
# ---------------------------------------------------------------------------

class TestGRunWiring:
    @pytest.mark.asyncio
    async def test_events_written_for_minimal_bundle(self, tmp_path):
        """O7 check_run fires and event lands in the ledger."""
        db = str(tmp_path / "ledger.duckdb")
        bundle = minimal_bundle()
        defn = _defn(bundle)
        agent = Agent(defn)

        # Point the agent's store at the tmp ledger
        agent._ledger_store = LedgerStore(db_path=db)

        with patch.object(agent._adapter, "astream", side_effect=_mock_astream("hello")):
            chunks = []
            async for chunk in agent.run({"query": "hi", "session_id": ""}, session_id="s1"):
                chunks.append(chunk)

        assert "".join(chunks) == "hello"

        store = LedgerStore(db_path=db)
        rows = scoreboard_current(store)
        # At least O7 G-RUN should be present (NA because OTEL disabled in test env)
        ids = {r.obligation_id for r in rows}
        assert "O7" in ids

    @pytest.mark.asyncio
    async def test_events_stamped_with_agent_id(self, tmp_path):
        db = str(tmp_path / "ledger2.duckdb")
        bundle = minimal_bundle()
        defn = _defn(bundle, name="my_agent")
        agent = Agent(defn)
        agent._ledger_store = LedgerStore(db_path=db)

        with patch.object(agent._adapter, "astream", side_effect=_mock_astream("ok")):
            async for _ in agent.run({"query": "q", "session_id": ""}, session_id="s"):
                pass

        store = LedgerStore(db_path=db)
        rows = scoreboard_current(store, agent_id="my_agent")
        assert len(rows) > 0

    @pytest.mark.asyncio
    async def test_events_stamped_with_bundle_id(self, tmp_path):
        db = str(tmp_path / "ledger3.duckdb")
        bundle = ObligationBundle(
            obligations=[O7Auditable()],
            bundle_id="my-bundle-v1",
        )
        defn = _defn(bundle)
        agent = Agent(defn)
        agent._ledger_store = LedgerStore(db_path=db)

        with patch.object(agent._adapter, "astream", side_effect=_mock_astream("ok")):
            async for _ in agent.run({"query": "q", "session_id": ""}, session_id="s"):
                pass

        # Query directly: bundle_id should be stamped
        store = LedgerStore(db_path=db)
        raw = store.query_sync("SELECT bundle_id FROM fact_obligation_event LIMIT 1")
        assert raw[0][0] == "my-bundle-v1"

    @pytest.mark.asyncio
    async def test_events_stamped_with_agent_pattern(self, tmp_path):
        db = str(tmp_path / "ledger4.duckdb")
        bundle = minimal_bundle()
        defn = _defn(bundle, agent_pattern=AgentPattern.B3)
        agent = Agent(defn)
        agent._ledger_store = LedgerStore(db_path=db)

        with patch.object(agent._adapter, "astream", side_effect=_mock_astream("ok")):
            async for _ in agent.run({"query": "q", "session_id": ""}, session_id="s"):
                pass

        store = LedgerStore(db_path=db)
        raw = store.query_sync("SELECT agent_pattern FROM fact_obligation_event LIMIT 1")
        assert raw[0][0] == "B3"

    @pytest.mark.asyncio
    async def test_multiple_obligations_all_written(self, tmp_path):
        """Standard bundle has 5 obligations — all 5 G-RUN events must land."""
        db = str(tmp_path / "ledger5.duckdb")
        bundle = standard_bundle()
        defn = _defn(bundle)
        agent = Agent(defn)
        agent._ledger_store = LedgerStore(db_path=db)

        with patch.object(agent._adapter, "astream", side_effect=_mock_astream("ok")):
            async for _ in agent.run({"query": "q", "session_id": ""}, session_id="s"):
                pass

        store = LedgerStore(db_path=db)
        rows = scoreboard_current(store)
        written_ids = {r.obligation_id for r in rows}
        # All 5 obligations in standard bundle should have G-RUN events
        for oid in bundle.obligation_ids():
            assert oid in written_ids, f"Missing event for {oid}"

    @pytest.mark.asyncio
    async def test_enforcement_point_is_g_run(self, tmp_path):
        db = str(tmp_path / "ledger6.duckdb")
        bundle = minimal_bundle()
        defn = _defn(bundle)
        agent = Agent(defn)
        agent._ledger_store = LedgerStore(db_path=db)

        with patch.object(agent._adapter, "astream", side_effect=_mock_astream("ok")):
            async for _ in agent.run({"query": "q", "session_id": ""}, session_id="s"):
                pass

        store = LedgerStore(db_path=db)
        rows = scoreboard_current(store)
        for r in rows:
            assert r.enforcement_point == "G-RUN"


# ---------------------------------------------------------------------------
# Output correctness — obligation checks must not change agent output
# ---------------------------------------------------------------------------

class TestOutputUnchanged:
    @pytest.mark.asyncio
    async def test_response_unchanged_with_bundle(self, tmp_path):
        db = str(tmp_path / "ledger_out.duckdb")
        bundle = minimal_bundle()
        defn = _defn(bundle)
        agent = Agent(defn)
        agent._ledger_store = LedgerStore(db_path=db)

        with patch.object(agent._adapter, "astream", side_effect=_mock_astream("expected output")):
            chunks = []
            async for chunk in agent.run({"query": "q", "session_id": ""}, session_id="s"):
                chunks.append(chunk)

        assert "".join(chunks) == "expected output"

    @pytest.mark.asyncio
    async def test_no_bundle_agent_unchanged(self, tmp_path):
        """Agent without bundle still works normally."""
        defn = AgentDefinition(
            name="no_bundle",
            prompt_template="Answer {query}",
            input_schema=_Input,
        )
        agent = Agent(defn)
        assert agent._ledger_store is None

        with patch.object(agent._adapter, "astream", side_effect=_mock_astream("no bundle output")):
            chunks = []
            async for chunk in agent.run({"query": "q", "session_id": ""}, session_id="s"):
                chunks.append(chunk)

        assert "".join(chunks) == "no bundle output"


# ---------------------------------------------------------------------------
# Resilience — obligation failures must not crash the agent
# ---------------------------------------------------------------------------

class TestObligationFailureResilience:
    @pytest.mark.asyncio
    async def test_obligation_check_exception_does_not_crash_agent(self, tmp_path):
        """If check_run() raises, the agent still returns its response."""
        db = str(tmp_path / "ledger_err.duckdb")

        # Create an obligation whose check_run always raises
        from praktor.aigov.obligations.base import Obligation
        from praktor.aigov.manifests import DataFlowManifest, PrivacyTestDataset

        class _BrokenObligation(Obligation):
            id = "O99"
            name = "Broken"
            MEASUREMENT_TECHNIQUES = {"G-BUILD": "", "G-TEST": "", "G-RUN": ""}

            async def check_build(self, manifest: DataFlowManifest):
                return self._na_event(EnforcementPoint.G_BUILD, "stub")

            async def check_test(self, dataset: PrivacyTestDataset):
                return self._na_event(EnforcementPoint.G_TEST, "stub")

            async def check_run(self, payload: str, response: str):
                raise RuntimeError("intentional test failure")

        bundle = ObligationBundle(obligations=[_BrokenObligation()], bundle_id="broken")
        defn = _defn(bundle)
        agent = Agent(defn)
        agent._ledger_store = LedgerStore(db_path=db)

        with patch.object(agent._adapter, "astream", side_effect=_mock_astream("safe response")):
            chunks = []
            async for chunk in agent.run({"query": "q", "session_id": ""}, session_id="s"):
                chunks.append(chunk)

        assert "".join(chunks) == "safe response"

    @pytest.mark.asyncio
    async def test_ledger_write_failure_does_not_crash_agent(self, tmp_path):
        """If the ledger write fails, the agent still returns its response."""
        db = str(tmp_path / "ledger_wfail.duckdb")
        bundle = minimal_bundle()
        defn = _defn(bundle)
        agent = Agent(defn)
        agent._ledger_store = LedgerStore(db_path=db)

        with patch.object(
            agent._ledger_store, "write_events", side_effect=RuntimeError("disk full")
        ):
            with patch.object(agent._adapter, "astream", side_effect=_mock_astream("ok")):
                chunks = []
                async for chunk in agent.run({"query": "q", "session_id": ""}, session_id="s"):
                    chunks.append(chunk)

        assert "".join(chunks) == "ok"

    @pytest.mark.asyncio
    async def test_no_ledger_store_skips_checks(self):
        """If LedgerStore init failed (self._ledger_store is None), checks are skipped."""
        bundle = minimal_bundle()
        defn = _defn(bundle)
        agent = Agent(defn)
        # Deliberately null out the store
        agent._ledger_store = None

        with patch.object(agent._adapter, "astream", side_effect=_mock_astream("ok")):
            chunks = []
            async for chunk in agent.run({"query": "q", "session_id": ""}, session_id="s"):
                chunks.append(chunk)

        assert "".join(chunks) == "ok"


# ---------------------------------------------------------------------------
# O2 FAIL scenario — FAIL event written, agent output still returned
# ---------------------------------------------------------------------------

class TestO2FailEvent:
    @pytest.mark.asyncio
    async def test_phi_in_response_writes_fail_event(self, tmp_path):
        """O2 check_run detects PHI in response → FAIL event in ledger, response still returned."""
        db = str(tmp_path / "ledger_o2.duckdb")
        bundle = ObligationBundle(
            obligations=[O2DataConfinement()],
            bundle_id="o2-test",
        )
        defn = _defn(bundle)
        agent = Agent(defn)
        agent._ledger_store = LedgerStore(db_path=db)

        # Response contains a real SSN — O2 should detect it and write FAIL
        phi_response = "Patient SSN is 123-45-6789. Enjoy."

        with patch.object(agent._adapter, "astream", side_effect=_mock_astream(phi_response)):
            chunks = []
            async for chunk in agent.run({"query": "q", "session_id": ""}, session_id="s"):
                chunks.append(chunk)

        # Agent output is still returned — O2 doesn't block by default
        assert "".join(chunks) == phi_response

        store = LedgerStore(db_path=db)
        rows = scoreboard_current(store)
        o2_rows = [r for r in rows if r.obligation_id == "O2"]
        assert len(o2_rows) == 1
        assert o2_rows[0].predicate_result == "FAIL"
        assert o2_rows[0].status == "RED"
