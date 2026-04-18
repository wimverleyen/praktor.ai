"""Tests for PR4: ObligationBundle, AgentDefinition.agent_pattern/obligation_bundle,
and GovernancePolicy.to_obligation_bundle() shim."""
from datetime import datetime, timezone
from pydantic import BaseModel

import pytest

from praktor.aigov.bundle import ObligationBundle
from praktor.aigov.event import AgentPattern
from praktor.aigov.obligations.o2_data_confinement import O2DataConfinement
from praktor.aigov.obligations.o3_content_safety import O3ContentSafety
from praktor.aigov.obligations.o7_auditable import O7Auditable
from praktor.core.agent_definition import AgentDefinition
from praktor.governance.policy import (
    AuditSinkType,
    DetectorConfig,
    GovernancePolicy,
    PolicyAction,
)


class _Input(BaseModel):
    agent_type: str = "test"
    query: str


def _defn(**kwargs) -> AgentDefinition:
    defaults = dict(name="test", prompt_template="Answer {query}", input_schema=_Input)
    defaults.update(kwargs)
    return AgentDefinition(**defaults)


# ---------------------------------------------------------------------------
# ObligationBundle
# ---------------------------------------------------------------------------

class TestObligationBundle:
    def test_instantiation(self):
        bundle = ObligationBundle(
            obligations=[O2DataConfinement(), O7Auditable()],
            bundle_id="test-v1",
        )
        assert bundle.bundle_id == "test-v1"
        assert len(bundle) == 2

    def test_obligation_ids(self):
        bundle = ObligationBundle(
            obligations=[O2DataConfinement(), O3ContentSafety(), O7Auditable()],
            bundle_id="full",
        )
        ids = bundle.obligation_ids()
        assert "O2" in ids
        assert "O3" in ids
        assert "O7" in ids

    def test_get_by_id(self):
        o2 = O2DataConfinement()
        bundle = ObligationBundle(obligations=[o2, O7Auditable()], bundle_id="x")
        assert bundle.get("O2") is o2
        assert bundle.get("O7") is not None
        assert bundle.get("O99") is None

    def test_iter(self):
        obligations = [O2DataConfinement(), O7Auditable()]
        bundle = ObligationBundle(obligations=obligations, bundle_id="x")
        assert list(bundle) == obligations

    def test_default_bundle_id(self):
        bundle = ObligationBundle(obligations=[])
        assert bundle.bundle_id == "custom"

    def test_empty_bundle(self):
        bundle = ObligationBundle(obligations=[])
        assert len(bundle) == 0
        assert bundle.obligation_ids() == []


# ---------------------------------------------------------------------------
# AgentDefinition.agent_pattern
# ---------------------------------------------------------------------------

class TestAgentPattern:
    def test_default_is_b1(self):
        defn = _defn()
        assert defn.agent_pattern == AgentPattern.B1

    def test_custom_pattern(self):
        defn = _defn(agent_pattern=AgentPattern.B3)
        assert defn.agent_pattern == AgentPattern.B3

    def test_b4_orchestrator(self):
        defn = _defn(agent_pattern=AgentPattern.B4)
        assert defn.agent_pattern == AgentPattern.B4

    def test_all_patterns_accepted(self):
        for pattern in AgentPattern:
            defn = _defn(agent_pattern=pattern)
            assert defn.agent_pattern == pattern


# ---------------------------------------------------------------------------
# AgentDefinition.obligation_bundle
# ---------------------------------------------------------------------------

class TestObligationBundleField:
    def test_default_is_none(self):
        defn = _defn()
        assert defn.obligation_bundle is None

    def test_explicit_bundle_preserved(self):
        bundle = ObligationBundle(
            obligations=[O2DataConfinement(), O7Auditable()],
            bundle_id="my-bundle",
        )
        defn = _defn(obligation_bundle=bundle)
        assert defn.obligation_bundle is bundle
        assert defn.obligation_bundle.bundle_id == "my-bundle"

    def test_bundle_wins_over_governance_policy(self):
        """Decision 2A: obligation_bundle wins if both are provided."""
        explicit_bundle = ObligationBundle(
            obligations=[O7Auditable()],
            bundle_id="explicit",
        )
        policy = GovernancePolicy(
            pre_execution=[DetectorConfig(
                detector_class="praktor.governance.detectors.RegexDetector",
                entities=["US_SSN"],
            )],
        )
        defn = _defn(obligation_bundle=explicit_bundle, governance_policy=policy)
        assert defn.obligation_bundle is explicit_bundle
        assert defn.obligation_bundle.bundle_id == "explicit"


# ---------------------------------------------------------------------------
# GovernancePolicy.to_obligation_bundle() shim
# ---------------------------------------------------------------------------

class TestGovernancePolicyShim:
    def test_auto_convert_on_post_init(self):
        """Decision 11A: governance_policy → obligation_bundle auto-converted."""
        policy = GovernancePolicy(
            pre_execution=[DetectorConfig(
                detector_class="praktor.governance.detectors.RegexDetector",
                entities=["US_SSN"],
            )],
        )
        defn = _defn(governance_policy=policy)
        assert defn.obligation_bundle is not None
        assert defn.obligation_bundle.bundle_id == "governance_policy_shim"

    def test_shim_always_includes_o7(self):
        policy = GovernancePolicy()
        defn = _defn(governance_policy=policy)
        assert defn.obligation_bundle is not None
        assert "O7" in defn.obligation_bundle.obligation_ids()

    def test_shim_includes_o2_when_detectors_present(self):
        policy = GovernancePolicy(
            pre_execution=[DetectorConfig(
                detector_class="praktor.governance.detectors.RegexDetector",
                entities=["US_SSN"],
            )],
        )
        defn = _defn(governance_policy=policy)
        assert "O2" in defn.obligation_bundle.obligation_ids()

    def test_shim_excludes_o2_when_no_detectors(self):
        policy = GovernancePolicy()
        defn = _defn(governance_policy=policy)
        assert "O2" not in defn.obligation_bundle.obligation_ids()

    def test_shim_includes_o3_when_evaluation_passes_present(self):
        from unittest.mock import MagicMock
        mock_pass = MagicMock()
        policy = GovernancePolicy(evaluation_passes=[mock_pass])
        defn = _defn(governance_policy=policy)
        assert "O3" in defn.obligation_bundle.obligation_ids()

    def test_shim_excludes_o3_when_no_evaluation_passes(self):
        policy = GovernancePolicy()
        defn = _defn(governance_policy=policy)
        assert "O3" not in defn.obligation_bundle.obligation_ids()

    def test_no_policy_no_bundle(self):
        defn = _defn()
        assert defn.obligation_bundle is None
        assert defn.governance_policy is None

    def test_post_execution_detectors_trigger_o2(self):
        policy = GovernancePolicy(
            post_execution=[DetectorConfig(
                detector_class="praktor.governance.detectors.RegexDetector",
                entities=["EMAIL_ADDRESS"],
            )],
        )
        defn = _defn(governance_policy=policy)
        assert "O2" in defn.obligation_bundle.obligation_ids()

    def test_shim_bundle_obligation_types(self):
        policy = GovernancePolicy(
            pre_execution=[DetectorConfig(
                detector_class="praktor.governance.detectors.RegexDetector",
                entities=["US_SSN"],
            )],
        )
        defn = _defn(governance_policy=policy)
        o2 = defn.obligation_bundle.get("O2")
        o7 = defn.obligation_bundle.get("O7")
        assert isinstance(o2, O2DataConfinement)
        assert isinstance(o7, O7Auditable)

    def test_direct_to_obligation_bundle_call(self):
        policy = GovernancePolicy(dry_run=True)
        bundle = policy.to_obligation_bundle()
        assert isinstance(bundle, ObligationBundle)
        assert "O7" in bundle.obligation_ids()
