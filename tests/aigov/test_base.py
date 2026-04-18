"""Tests for praktor.aigov.obligations.base — Obligation ABC."""
import pytest

from praktor.aigov.event import (
    EnforcementPoint,
    ObligationEvent,
    PredicateResult,
    Severity,
)
from praktor.aigov.manifests import DataFlowManifest, PrivacyTestDataset
from praktor.aigov.obligations.base import Obligation
from datetime import datetime, timezone


# ---------------------------------------------------------------------------
# Minimal concrete subclass for testing
# ---------------------------------------------------------------------------

class _DummyObligation(Obligation):
    id = "O99"
    name = "Dummy Test Obligation"
    MEASUREMENT_TECHNIQUES = {
        "G-BUILD": "99.1.0",
        "G-TEST": "99.2.0",
        "G-RUN": "99.3.0",
    }

    async def check_build(self, manifest: DataFlowManifest) -> ObligationEvent:
        return self._event(EnforcementPoint.G_BUILD, PredicateResult.PASS)

    async def check_test(self, dataset: PrivacyTestDataset) -> ObligationEvent:
        return self._event(EnforcementPoint.G_TEST, PredicateResult.NA,
                           deferred_reason="no_test_data")

    async def check_run(self, payload: str, response: str) -> ObligationEvent:
        result = PredicateResult.FAIL if "bad" in response else PredicateResult.PASS
        return self._event(EnforcementPoint.G_RUN, result)


class _DeferredObligation(Obligation):
    """Represents a fully-deferred obligation (like O4, O8, O10, O11)."""
    id = "O88"
    name = "Deferred Obligation"
    MEASUREMENT_TECHNIQUES = {"G-BUILD": "", "G-TEST": "", "G-RUN": ""}

    async def check_build(self, manifest: DataFlowManifest) -> ObligationEvent:
        return self._na_event(EnforcementPoint.G_BUILD, "not_applicable_at_build")

    async def check_test(self, dataset: PrivacyTestDataset) -> ObligationEvent:
        return self._na_event(EnforcementPoint.G_TEST, "no_test_suite")

    async def check_run(self, payload: str, response: str) -> ObligationEvent:
        return self._na_event(EnforcementPoint.G_RUN, "platform_not_wired")


_MANIFEST = DataFlowManifest(
    source_systems=["ehr"],
    allowed_egress_destinations=["audit_log"],
    phi_fields=["member_id"],
    signed_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
)
_DATASET = PrivacyTestDataset(records=[{"text": "hello"}], labels=["none"])


class TestObligationAbstract:
    def test_cannot_instantiate_abstract(self):
        with pytest.raises(TypeError):
            Obligation()  # type: ignore[abstract]

    def test_concrete_subclass_instantiates(self):
        ob = _DummyObligation()
        assert ob.id == "O99"
        assert ob.name == "Dummy Test Obligation"

    def test_measurement_techniques_dict(self):
        ob = _DummyObligation()
        assert ob.MEASUREMENT_TECHNIQUES["G-BUILD"] == "99.1.0"
        assert ob.MEASUREMENT_TECHNIQUES["G-RUN"] == "99.3.0"


class TestEventHelper:
    @pytest.mark.asyncio
    async def test_check_build_event_fields(self):
        ob = _DummyObligation()
        ev = await ob.check_build(_MANIFEST)
        assert ev.obligation_id == "O99"
        assert ev.enforcement_point == EnforcementPoint.G_BUILD
        assert ev.predicate_result == PredicateResult.PASS
        assert ev.measurement_technique == "99.1.0"

    @pytest.mark.asyncio
    async def test_check_run_pass(self):
        ob = _DummyObligation()
        ev = await ob.check_run("user query", "good response")
        assert ev.predicate_result == PredicateResult.PASS
        assert ev.enforcement_point == EnforcementPoint.G_RUN

    @pytest.mark.asyncio
    async def test_check_run_fail(self):
        ob = _DummyObligation()
        ev = await ob.check_run("user query", "bad response")
        assert ev.predicate_result == PredicateResult.FAIL

    @pytest.mark.asyncio
    async def test_check_test_na(self):
        ob = _DummyObligation()
        ev = await ob.check_test(_DATASET)
        assert ev.predicate_result == PredicateResult.NA
        assert ev.deferred_reason == "no_test_data"

    def test_event_helper_measurement_technique(self):
        ob = _DummyObligation()
        ev = ob._event(EnforcementPoint.G_RUN, PredicateResult.PASS)
        assert ev.measurement_technique == "99.3.0"

    def test_event_helper_unknown_point_empty_technique(self):
        ob = _DummyObligation()
        ev = ob._event(EnforcementPoint.G_BUILD, PredicateResult.PASS)
        assert ev.measurement_technique == "99.1.0"

    def test_event_helper_extra_kwargs_forwarded(self):
        ob = _DummyObligation()
        ev = ob._event(
            EnforcementPoint.G_RUN,
            PredicateResult.PASS,
            severity=Severity.HIGH,
            agent_id="test-agent",
        )
        assert ev.severity == Severity.HIGH
        assert ev.agent_id == "test-agent"


class TestNaEventHelper:
    def test_na_event_predicate(self):
        ob = _DeferredObligation()
        ev = ob._na_event(EnforcementPoint.G_RUN, "platform_not_wired")
        assert ev.predicate_result == PredicateResult.NA
        assert ev.deferred_reason == "platform_not_wired"
        assert ev.severity == Severity.INFO

    @pytest.mark.asyncio
    async def test_deferred_obligation_all_na(self):
        ob = _DeferredObligation()
        build_ev = await ob.check_build(_MANIFEST)
        test_ev = await ob.check_test(_DATASET)
        run_ev = await ob.check_run("payload", "response")
        for ev in (build_ev, test_ev, run_ev):
            assert ev.predicate_result == PredicateResult.NA
            assert ev.deferred_reason

    @pytest.mark.asyncio
    async def test_obligation_id_on_na_event(self):
        ob = _DeferredObligation()
        ev = await ob.check_run("x", "y")
        assert ev.obligation_id == "O88"
