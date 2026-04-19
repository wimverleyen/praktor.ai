"""Tests for O1, O4-O6, O8-O11 NA-stub obligations."""
import pytest

from praktor.aigov.event import EnforcementPoint, PredicateResult
from praktor.aigov.manifests import DataFlowManifest, PrivacyTestDataset
from praktor.aigov.obligations.o1_bounded_action import O1BoundedAction
from praktor.aigov.obligations.o4_fairness import O4Fairness
from praktor.aigov.obligations.o5_grounded_outputs import O5GroundedOutputs
from praktor.aigov.obligations.o6_goal_integrity import O6GoalIntegrity
from praktor.aigov.obligations.o8_human_oversight import O8HumanOversight
from praktor.aigov.obligations.o9_change_attestation import O9ChangeAttestation
from praktor.aigov.obligations.o10_operational_invariants import O10OperationalInvariants
from praktor.aigov.obligations.o11_ui_transparency import O11UITransparency
from datetime import datetime, timezone


_ALL_STUBS = [
    O1BoundedAction,
    O4Fairness,
    O5GroundedOutputs,
    O6GoalIntegrity,
    O8HumanOversight,
    O9ChangeAttestation,
    O10OperationalInvariants,
    O11UITransparency,
]

_EXPECTED_IDS = ["O1", "O4", "O5", "O6", "O8", "O9", "O10", "O11"]


def _manifest():
    return DataFlowManifest(
        source_systems=["ehr"],
        allowed_egress_destinations=["audit_log"],
        phi_fields=["member_id"],
        signed_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        deployer="ci-bot",
    )


def _dataset():
    return PrivacyTestDataset(records=[], labels=[])


class TestObligationIds:
    def test_ids_are_correct(self):
        for cls, expected_id in zip(_ALL_STUBS, _EXPECTED_IDS):
            assert cls.id == expected_id

    def test_names_are_nonempty(self):
        for cls in _ALL_STUBS:
            assert cls.name

    def test_measurement_techniques_have_all_three_points(self):
        for cls in _ALL_STUBS:
            mt = cls.MEASUREMENT_TECHNIQUES
            assert "G-BUILD" in mt
            assert "G-TEST" in mt
            assert "G-RUN" in mt


class TestAllNAAtBuild:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("cls", _ALL_STUBS)
    async def test_check_build_returns_na(self, cls):
        ob = cls()
        ev = await ob.check_build(_manifest())
        assert ev.predicate_result == PredicateResult.NA
        assert ev.enforcement_point == EnforcementPoint.G_BUILD
        assert ev.deferred_reason

    @pytest.mark.asyncio
    @pytest.mark.parametrize("cls", _ALL_STUBS)
    async def test_check_test_returns_na(self, cls):
        ob = cls()
        ev = await ob.check_test(_dataset())
        assert ev.predicate_result == PredicateResult.NA
        assert ev.enforcement_point == EnforcementPoint.G_TEST
        assert ev.deferred_reason

    @pytest.mark.asyncio
    @pytest.mark.parametrize("cls", _ALL_STUBS)
    async def test_check_run_returns_na(self, cls):
        ob = cls()
        ev = await ob.check_run("payload", "response")
        assert ev.predicate_result == PredicateResult.NA
        assert ev.enforcement_point == EnforcementPoint.G_RUN
        assert ev.deferred_reason


class TestObligationEventShape:
    @pytest.mark.asyncio
    async def test_event_has_obligation_id(self):
        ob = O1BoundedAction()
        ev = await ob.check_run("p", "r")
        assert ev.obligation_id == "O1"

    @pytest.mark.asyncio
    async def test_event_has_measurement_technique(self):
        ob = O8HumanOversight()
        ev = await ob.check_build(_manifest())
        assert ev.measurement_technique == "8.1.1"

    @pytest.mark.asyncio
    async def test_event_id_is_ulid_format(self):
        ob = O11UITransparency()
        ev = await ob.check_run("p", "r")
        assert len(ev.event_id) == 26

    @pytest.mark.asyncio
    async def test_event_ts_is_rfc3339(self):
        ob = O4Fairness()
        ev = await ob.check_build(_manifest())
        assert ev.event_ts.endswith("Z")
