"""Tests for O2DataConfinement obligation."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from praktor.aigov.event import EnforcementPoint, PredicateResult, Severity
from praktor.aigov.manifests import DataFlowManifest, PrivacyTestDataset
from praktor.aigov.obligations.o2_data_confinement import O2DataConfinement
from praktor.governance.detectors import DetectionResult


def _manifest(**kwargs) -> DataFlowManifest:
    defaults = dict(
        source_systems=["ehr"],
        allowed_egress_destinations=["audit_log"],
        phi_fields=["member_id", "diagnosis_codes"],
        signed_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        deployer="ci-bot",
    )
    defaults.update(kwargs)
    return DataFlowManifest(**defaults)


def _dataset(records, labels) -> PrivacyTestDataset:
    return PrivacyTestDataset(records=records, labels=labels)


def _hit(entity_type="US_SSN") -> DetectionResult:
    return DetectionResult(entity_type=entity_type, start=0, end=11, score=1.0, text="123-45-6789")


class TestCheckBuild:
    @pytest.mark.asyncio
    async def test_complete_manifest_passes(self):
        ob = O2DataConfinement()
        ev = await ob.check_build(_manifest())
        assert ev.predicate_result == PredicateResult.PASS
        assert ev.obligation_id == "O2"
        assert ev.enforcement_point == EnforcementPoint.G_BUILD

    @pytest.mark.asyncio
    async def test_missing_phi_fields_fails(self):
        ob = O2DataConfinement()
        ev = await ob.check_build(_manifest(phi_fields=[]))
        assert ev.predicate_result == PredicateResult.FAIL
        assert ev.severity == Severity.HIGH

    @pytest.mark.asyncio
    async def test_missing_egress_destinations_fails(self):
        ob = O2DataConfinement()
        ev = await ob.check_build(_manifest(allowed_egress_destinations=[]))
        assert ev.predicate_result == PredicateResult.FAIL

    @pytest.mark.asyncio
    async def test_missing_deployer_fails(self):
        ob = O2DataConfinement()
        ev = await ob.check_build(_manifest(deployer=""))
        assert ev.predicate_result == PredicateResult.FAIL

    @pytest.mark.asyncio
    async def test_multiple_issues_all_reported(self):
        ob = O2DataConfinement()
        ev = await ob.check_build(_manifest(phi_fields=[], deployer=""))
        assert ev.predicate_result == PredicateResult.FAIL

    @pytest.mark.asyncio
    async def test_regulatory_tags_present(self):
        ob = O2DataConfinement()
        ev = await ob.check_build(_manifest())
        assert "HIPAA.164.514" in ev.regulatory_tags

    @pytest.mark.asyncio
    async def test_evidence_ref_set(self):
        ob = O2DataConfinement()
        ev = await ob.check_build(_manifest())
        assert ev.evidence is not None
        assert len(ev.evidence.sha256) == 64


class TestCheckTest:
    @pytest.mark.asyncio
    async def test_no_labeled_records_returns_na(self):
        ob = O2DataConfinement()
        ds = _dataset([{"text": "hello"}], ["none"])
        ev = await ob.check_test(ds)
        assert ev.predicate_result == PredicateResult.NA
        assert ev.deferred_reason == "no_labeled_test_records"

    @pytest.mark.asyncio
    async def test_perfect_recall_passes(self):
        mock_detector = AsyncMock()
        mock_detector.detect = AsyncMock(return_value=[_hit()])
        ob = O2DataConfinement(detector=mock_detector)
        ds = _dataset(
            [{"text": "SSN: 123-45-6789"}, {"text": "SSN: 987-65-4321"}],
            ["US_SSN", "US_SSN"],
        )
        ev = await ob.check_test(ds)
        assert ev.predicate_result == PredicateResult.PASS

    @pytest.mark.asyncio
    async def test_zero_recall_fails(self):
        mock_detector = AsyncMock()
        mock_detector.detect = AsyncMock(return_value=[])
        ob = O2DataConfinement(detector=mock_detector)
        ds = _dataset([{"text": "SSN: 123-45-6789"}], ["US_SSN"])
        ev = await ob.check_test(ds)
        assert ev.predicate_result == PredicateResult.FAIL
        assert ev.severity == Severity.HIGH

    @pytest.mark.asyncio
    async def test_real_regex_detects_ssn(self):
        ob = O2DataConfinement()
        ds = _dataset([{"text": "SSN: 123-45-6789"}], ["US_SSN"])
        ev = await ob.check_test(ds)
        assert ev.predicate_result == PredicateResult.PASS

    @pytest.mark.asyncio
    async def test_none_labeled_records_excluded(self):
        """Records with label='none' don't count toward recall denominator."""
        mock_detector = AsyncMock()
        mock_detector.detect = AsyncMock(return_value=[])
        ob = O2DataConfinement(detector=mock_detector)
        ds = _dataset(
            [{"text": "hello"}, {"text": "world"}],
            ["none", "none"],
        )
        ev = await ob.check_test(ds)
        assert ev.predicate_result == PredicateResult.NA


class TestCheckRun:
    @pytest.mark.asyncio
    async def test_clean_response_passes(self):
        ob = O2DataConfinement()
        ev = await ob.check_run("what is the patient status?", "The patient is recovering well.")
        assert ev.predicate_result == PredicateResult.PASS
        assert ev.enforcement_point == EnforcementPoint.G_RUN

    @pytest.mark.asyncio
    async def test_phi_in_response_fails(self):
        ob = O2DataConfinement()
        ev = await ob.check_run(
            "summarize the record",
            "Patient SSN is 123-45-6789 and email is john@example.com",
        )
        assert ev.predicate_result == PredicateResult.FAIL
        assert ev.severity == Severity.CRITICAL

    @pytest.mark.asyncio
    async def test_custom_detector_injected(self):
        mock_detector = AsyncMock()
        mock_detector.detect = AsyncMock(return_value=[_hit()])
        ob = O2DataConfinement(detector=mock_detector)
        ev = await ob.check_run("query", "response text")
        assert ev.predicate_result == PredicateResult.FAIL
        mock_detector.detect.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_evidence_has_detection_count(self):
        ob = O2DataConfinement()
        ev = await ob.check_run(
            "query", "Patient SSN is 123-45-6789"
        )
        assert ev.evidence is not None
        assert ev.evidence.sha256

    @pytest.mark.asyncio
    async def test_measurement_technique_set(self):
        ob = O2DataConfinement()
        ev = await ob.check_run("q", "r")
        assert ev.measurement_technique == "2.1.3"
