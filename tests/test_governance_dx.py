"""
DX smoke tests for governance API surface.

These verify the developer-facing contracts: block_pii(), RegexEntities constants,
DetectorConfig class coercion, unknown entity warnings, and violation message format.
No live LLM required.
"""
import logging
import dataclasses
import pytest
from pydantic import BaseModel
from unittest.mock import MagicMock, patch

from praktor.core.agent_definition import AgentDefinition
from praktor.governance import block_pii, RegexEntities
from praktor.governance.detectors import RegexDetector, _PATTERNS
from praktor.governance.policy import (
    DetectorConfig,
    GovernancePolicy,
    GovernancePolicyViolation,
    PolicyAction,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _Input(BaseModel):
    agent_type: str = "test"
    text: str
    session_id: str = ""


def _base_defn() -> AgentDefinition:
    return AgentDefinition(
        name="test",
        prompt_template="Answer: {text}",
        input_schema=_Input,
        llm_model="qwen2.5",
    )


# ---------------------------------------------------------------------------
# Group 1 — block_pii() returns a new AgentDefinition
# ---------------------------------------------------------------------------

def test_block_pii_returns_new_definition():
    original = _base_defn()
    updated = block_pii(original, [RegexEntities.US_SSN])
    assert updated is not original


def test_block_pii_original_is_unchanged():
    original = _base_defn()
    block_pii(original, [RegexEntities.US_SSN])
    assert original.governance_policy is None


def test_block_pii_sets_governance_policy():
    updated = block_pii(_base_defn(), [RegexEntities.US_SSN])
    assert updated.governance_policy is not None


def test_block_pii_policy_has_pre_execution_detector():
    updated = block_pii(_base_defn(), [RegexEntities.US_SSN, RegexEntities.EMAIL_ADDRESS])
    assert len(updated.governance_policy.pre_execution) == 1
    cfg = updated.governance_policy.pre_execution[0]
    assert "US_SSN" in cfg.entities
    assert "EMAIL_ADDRESS" in cfg.entities


def test_block_pii_action_defaults_to_block():
    updated = block_pii(_base_defn(), [RegexEntities.US_SSN])
    cfg = updated.governance_policy.pre_execution[0]
    assert cfg.action == PolicyAction.BLOCK


def test_block_pii_custom_action():
    updated = block_pii(_base_defn(), [RegexEntities.EMAIL_ADDRESS], action="redact")
    cfg = updated.governance_policy.pre_execution[0]
    assert cfg.action == PolicyAction.REDACT


# ---------------------------------------------------------------------------
# Group 2 — RegexEntities constants match _PATTERNS keys
# ---------------------------------------------------------------------------

def test_regex_entities_us_ssn_in_patterns():
    assert RegexEntities.US_SSN in _PATTERNS


def test_regex_entities_email_in_patterns():
    assert RegexEntities.EMAIL_ADDRESS in _PATTERNS


def test_regex_entities_phone_in_patterns():
    assert RegexEntities.PHONE_NUMBER in _PATTERNS


def test_regex_entities_dob_in_patterns():
    assert RegexEntities.DATE_OF_BIRTH in _PATTERNS


def test_regex_entities_passport_in_patterns():
    assert RegexEntities.US_PASSPORT in _PATTERNS


def test_regex_entities_credit_card_in_patterns():
    assert RegexEntities.CREDIT_CARD in _PATTERNS


# ---------------------------------------------------------------------------
# Group 3 — DetectorConfig accepts class and coerces to qualified string
# ---------------------------------------------------------------------------

def test_detector_config_accepts_class():
    cfg = DetectorConfig(
        detector_class=RegexDetector,
        entities=[RegexEntities.US_SSN],
        action=PolicyAction.BLOCK,
    )
    assert isinstance(cfg.detector_class, str)


def test_detector_config_coerces_to_qualified_name():
    cfg = DetectorConfig(
        detector_class=RegexDetector,
        entities=[RegexEntities.US_SSN],
        action=PolicyAction.BLOCK,
    )
    assert cfg.detector_class == "praktor.governance.detectors.RegexDetector"


def test_detector_config_accepts_string_unchanged():
    fqn = "praktor.governance.detectors.RegexDetector"
    cfg = DetectorConfig(
        detector_class=fqn,
        entities=[RegexEntities.US_SSN],
        action=PolicyAction.BLOCK,
    )
    assert cfg.detector_class == fqn


# ---------------------------------------------------------------------------
# Group 4 — Unknown entity logs WARNING (not PresidioDetector)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_unknown_entity_logs_warning(caplog):
    detector = RegexDetector()
    with caplog.at_level(logging.WARNING, logger="praktor.governance.detectors"):
        results = await detector.detect("some text", ["NOT_A_REAL_ENTITY_XYZ"])
    assert any("unknown entity" in r.message.lower() for r in caplog.records)


@pytest.mark.asyncio
async def test_unknown_entity_returns_empty(caplog):
    detector = RegexDetector()
    with caplog.at_level(logging.WARNING, logger="praktor.governance.detectors"):
        results = await detector.detect("Patient SSN 123-45-6789", ["NOT_A_REAL_ENTITY_XYZ"])
    assert results == []


@pytest.mark.asyncio
async def test_known_entity_does_not_warn(caplog):
    detector = RegexDetector()
    with caplog.at_level(logging.WARNING, logger="praktor.governance.detectors"):
        await detector.detect("some text", [RegexEntities.US_SSN])
    assert not any("unknown entity" in r.message.lower() for r in caplog.records)


# ---------------------------------------------------------------------------
# Group 5 — GovernancePolicyViolation.__str__ includes doc_url
# ---------------------------------------------------------------------------

def test_violation_str_includes_doc_url():
    exc = GovernancePolicyViolation(
        "pre_execution BLOCK",
        field_name="text",
        entity_type="US_SSN",
        detector_class="RegexDetector",
    )
    assert "https://" in str(exc)


def test_violation_str_includes_entity_type():
    exc = GovernancePolicyViolation(
        "pre_execution BLOCK",
        field_name="text",
        entity_type="US_SSN",
        detector_class="RegexDetector",
    )
    assert "US_SSN" in str(exc)


def test_violation_str_includes_field_name():
    exc = GovernancePolicyViolation(
        "pre_execution BLOCK",
        field_name="text",
        entity_type="EMAIL_ADDRESS",
        detector_class="RegexDetector",
    )
    assert "text" in str(exc)


# ---------------------------------------------------------------------------
# Group 6 — Governance monitoring metrics record_kpi correctly
# ---------------------------------------------------------------------------

def test_record_governance_detection_calls_record_kpi():
    mock_registry = MagicMock()
    with patch("praktor.monitoring.governance.get_registry", return_value=mock_registry):
        from praktor.monitoring.governance import record_governance_detection
        record_governance_detection("US_SSN")
    mock_registry.record_kpi.assert_called_once_with(
        "governance.detections_total", value=1.0, tags={"entity_type": "US_SSN"}
    )


def test_record_governance_violation_calls_record_kpi():
    mock_registry = MagicMock()
    with patch("praktor.monitoring.governance.get_registry", return_value=mock_registry):
        from praktor.monitoring.governance import record_governance_violation
        record_governance_violation("block", "EMAIL_ADDRESS")
    mock_registry.record_kpi.assert_called_once_with(
        "governance.violations_total",
        value=1.0,
        tags={"action": "block", "entity_type": "EMAIL_ADDRESS"},
    )


def test_record_governance_dry_run_calls_record_kpi():
    mock_registry = MagicMock()
    with patch("praktor.monitoring.governance.get_registry", return_value=mock_registry):
        from praktor.monitoring.governance import record_governance_dry_run
        record_governance_dry_run()
    mock_registry.record_kpi.assert_called_once_with(
        "governance.dry_run_hits_total", value=1.0
    )


# ---------------------------------------------------------------------------
# Group 7 — GovernancePolicyViolation __str__ edge: empty field_name falls back
# ---------------------------------------------------------------------------

def test_violation_str_no_field_name_falls_back_to_message():
    exc = GovernancePolicyViolation("pre_execution BLOCK")
    # No field_name set — __str__ returns the base message without extended context
    assert "pre_execution BLOCK" in str(exc)
    assert "https://" not in str(exc)
