"""Tests for O7Auditable obligation."""
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from praktor.aigov.event import EnforcementPoint, PredicateResult, Severity
from praktor.aigov.manifests import DataFlowManifest, PrivacyTestDataset
from praktor.aigov.obligations.o7_auditable import O7Auditable


def _manifest() -> DataFlowManifest:
    return DataFlowManifest(
        source_systems=["ehr"],
        allowed_egress_destinations=["audit_log"],
        phi_fields=["member_id"],
        signed_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        deployer="ci-bot",
    )


def _otel_state(sdk_disabled=False, tracer_initialized=False):
    return {"sdk_disabled": sdk_disabled, "tracer_initialized": tracer_initialized}


class TestCheckTest:
    @pytest.mark.asyncio
    async def test_always_na(self):
        ob = O7Auditable()
        ds = PrivacyTestDataset(records=[], labels=[])
        ev = await ob.check_test(ds)
        assert ev.predicate_result == PredicateResult.NA
        assert ev.deferred_reason == "otel_not_testable_from_static_data"
        assert ev.enforcement_point == EnforcementPoint.G_TEST


class TestCheckBuild:
    @pytest.mark.asyncio
    async def test_sdk_disabled_returns_na(self):
        ob = O7Auditable()
        with patch("praktor.aigov.obligations.o7_auditable._otel_state",
                   return_value=_otel_state(sdk_disabled=True)):
            ev = await ob.check_build(_manifest())
        assert ev.predicate_result == PredicateResult.NA
        assert ev.deferred_reason == "otel_sdk_disabled"

    @pytest.mark.asyncio
    async def test_otel_enabled_env_passes(self, monkeypatch):
        monkeypatch.setenv("PRAKTOR_OTEL_ENABLED", "1")
        ob = O7Auditable()
        with patch("praktor.aigov.obligations.o7_auditable._otel_state",
                   return_value=_otel_state()):
            ev = await ob.check_build(_manifest())
        assert ev.predicate_result == PredicateResult.PASS

    @pytest.mark.asyncio
    async def test_otlp_endpoint_set_passes(self, monkeypatch):
        monkeypatch.setenv("PRAKTOR_OTLP_ENDPOINT", "localhost:4317")
        ob = O7Auditable()
        with patch("praktor.aigov.obligations.o7_auditable._otel_state",
                   return_value=_otel_state()):
            ev = await ob.check_build(_manifest())
        assert ev.predicate_result == PredicateResult.PASS

    @pytest.mark.asyncio
    async def test_no_otel_config_fails(self, monkeypatch):
        monkeypatch.delenv("PRAKTOR_OTEL_ENABLED", raising=False)
        monkeypatch.delenv("PRAKTOR_OTLP_ENDPOINT", raising=False)
        ob = O7Auditable()
        with patch("praktor.aigov.obligations.o7_auditable._otel_state",
                   return_value=_otel_state()):
            ev = await ob.check_build(_manifest())
        assert ev.predicate_result == PredicateResult.FAIL
        assert ev.severity == Severity.MEDIUM


class TestCheckRun:
    @pytest.mark.asyncio
    async def test_sdk_disabled_returns_na(self):
        ob = O7Auditable()
        with patch("praktor.aigov.obligations.o7_auditable._otel_state",
                   return_value=_otel_state(sdk_disabled=True)):
            ev = await ob.check_run("payload", "response")
        assert ev.predicate_result == PredicateResult.NA
        assert ev.deferred_reason == "otel_sdk_disabled"

    @pytest.mark.asyncio
    async def test_tracer_initialized_passes(self):
        ob = O7Auditable()
        with patch("praktor.aigov.obligations.o7_auditable._otel_state",
                   return_value=_otel_state(sdk_disabled=False, tracer_initialized=True)):
            ev = await ob.check_run("payload", "response")
        assert ev.predicate_result == PredicateResult.PASS
        assert ev.enforcement_point == EnforcementPoint.G_RUN

    @pytest.mark.asyncio
    async def test_otel_expected_but_not_initialized_fails(self, monkeypatch):
        monkeypatch.setenv("PRAKTOR_OTEL_ENABLED", "1")
        ob = O7Auditable()
        with patch("praktor.aigov.obligations.o7_auditable._otel_state",
                   return_value=_otel_state(sdk_disabled=False, tracer_initialized=False)):
            ev = await ob.check_run("payload", "response")
        assert ev.predicate_result == PredicateResult.FAIL
        assert ev.deferred_reason == "otel_expected_but_not_initialized"

    @pytest.mark.asyncio
    async def test_otel_not_configured_returns_na(self, monkeypatch):
        monkeypatch.delenv("PRAKTOR_OTEL_ENABLED", raising=False)
        ob = O7Auditable()
        with patch("praktor.aigov.obligations.o7_auditable._otel_state",
                   return_value=_otel_state(sdk_disabled=False, tracer_initialized=False)):
            ev = await ob.check_run("payload", "response")
        assert ev.predicate_result == PredicateResult.NA
        assert ev.deferred_reason == "otel_not_configured"

    @pytest.mark.asyncio
    async def test_evidence_ref_set(self):
        ob = O7Auditable()
        with patch("praktor.aigov.obligations.o7_auditable._otel_state",
                   return_value=_otel_state(sdk_disabled=True)):
            ev = await ob.check_run("p", "r")
        assert ev.evidence is not None
        assert len(ev.evidence.sha256) == 64

    @pytest.mark.asyncio
    async def test_measurement_technique_set(self):
        ob = O7Auditable()
        with patch("praktor.aigov.obligations.o7_auditable._otel_state",
                   return_value=_otel_state(sdk_disabled=True)):
            ev = await ob.check_run("p", "r")
        assert ev.measurement_technique == "7.1.3"

    @pytest.mark.asyncio
    async def test_regulatory_tags_present(self):
        ob = O7Auditable()
        with patch("praktor.aigov.obligations.o7_auditable._otel_state",
                   return_value=_otel_state(sdk_disabled=True)):
            ev = await ob.check_run("p", "r")
        assert "EU_AI_ACT.Art17" in ev.regulatory_tags

    @pytest.mark.asyncio
    async def test_in_test_env_with_sdk_disabled(self):
        """In test suite, OTEL_SDK_DISABLED=true is set by conftest → honest NA."""
        ob = O7Auditable()
        ev = await ob.check_run("payload", "response")
        assert ev.predicate_result == PredicateResult.NA
        assert ev.deferred_reason == "otel_sdk_disabled"
