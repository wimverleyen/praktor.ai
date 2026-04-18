"""Tests for O3ContentSafety obligation."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from praktor.aigov.event import EnforcementPoint, PredicateResult, Severity
from praktor.aigov.manifests import DataFlowManifest, PrivacyTestDataset
from praktor.aigov.obligations.o3_content_safety import O3ContentSafety
from praktor.governance.evaluators.llm_judge import JudgeResult


def _manifest() -> DataFlowManifest:
    return DataFlowManifest(
        source_systems=["ehr"],
        allowed_egress_destinations=["audit_log"],
        phi_fields=["member_id"],
        signed_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        deployer="ci-bot",
    )


def _make_judge(value: float = 8.0, pass_: bool = True, timed_out: bool = False):
    judge = MagicMock()
    judge.threshold = 7.0
    judge.score = AsyncMock(
        return_value=JudgeResult(value=value, pass_=pass_, reasoning="ok", timed_out=timed_out)
    )
    return judge


class TestCheckBuild:
    @pytest.mark.asyncio
    async def test_passes_when_judge_configured(self):
        ob = O3ContentSafety(judge=_make_judge())
        ev = await ob.check_build(_manifest())
        assert ev.predicate_result == PredicateResult.PASS
        assert ev.obligation_id == "O3"
        assert ev.enforcement_point == EnforcementPoint.G_BUILD

    @pytest.mark.asyncio
    async def test_regulatory_tags_present(self):
        ob = O3ContentSafety(judge=_make_judge())
        ev = await ob.check_build(_manifest())
        assert "EU_AI_ACT.Art9" in ev.regulatory_tags

    @pytest.mark.asyncio
    async def test_evidence_ref_set(self):
        ob = O3ContentSafety(judge=_make_judge())
        ev = await ob.check_build(_manifest())
        assert ev.evidence is not None
        assert len(ev.evidence.sha256) == 64


class TestCheckTest:
    @pytest.mark.asyncio
    async def test_empty_dataset_returns_na(self):
        ob = O3ContentSafety(judge=_make_judge())
        ds = PrivacyTestDataset(records=[], labels=[])
        ev = await ob.check_test(ds)
        assert ev.predicate_result == PredicateResult.NA
        assert ev.deferred_reason == "no_test_records"

    @pytest.mark.asyncio
    async def test_all_passing_records_pass(self):
        judge = _make_judge(value=8.0, pass_=True)
        ob = O3ContentSafety(judge=judge)
        ds = PrivacyTestDataset(
            records=[{"text": "safe"}, {"text": "also safe"}],
            labels=["none", "none"],
        )
        ev = await ob.check_test(ds)
        assert ev.predicate_result == PredicateResult.PASS

    @pytest.mark.asyncio
    async def test_all_failing_records_fail(self):
        judge = _make_judge(value=3.0, pass_=False)
        ob = O3ContentSafety(judge=judge)
        ds = PrivacyTestDataset(
            records=[{"text": "unsafe"}],
            labels=["none"],
        )
        ev = await ob.check_test(ds)
        assert ev.predicate_result == PredicateResult.FAIL
        assert ev.severity == Severity.HIGH

    @pytest.mark.asyncio
    async def test_timeout_records_do_not_count_as_pass(self):
        judge = _make_judge(timed_out=True)
        ob = O3ContentSafety(judge=judge)
        ds = PrivacyTestDataset(records=[{"text": "x"}], labels=["none"])
        ev = await ob.check_test(ds)
        assert ev.predicate_result == PredicateResult.FAIL


class TestCheckRun:
    @pytest.mark.asyncio
    async def test_passing_score_emits_pass(self):
        ob = O3ContentSafety(judge=_make_judge(value=8.5, pass_=True))
        ev = await ob.check_run("question", "safe response")
        assert ev.predicate_result == PredicateResult.PASS
        assert ev.enforcement_point == EnforcementPoint.G_RUN

    @pytest.mark.asyncio
    async def test_failing_score_emits_fail(self):
        ob = O3ContentSafety(judge=_make_judge(value=3.0, pass_=False))
        ev = await ob.check_run("question", "unsafe response")
        assert ev.predicate_result == PredicateResult.FAIL
        assert ev.severity == Severity.HIGH

    @pytest.mark.asyncio
    async def test_timeout_emits_fail_severity_medium(self):
        """Decision 5A: LLM timeout → FAIL, severity=MEDIUM, run continues."""
        ob = O3ContentSafety(judge=_make_judge(timed_out=True))
        ev = await ob.check_run("question", "response")
        assert ev.predicate_result == PredicateResult.FAIL
        assert ev.severity == Severity.MEDIUM
        assert ev.deferred_reason == "judge_timeout"

    @pytest.mark.asyncio
    async def test_judge_called_with_payload_and_response(self):
        judge = _make_judge()
        ob = O3ContentSafety(judge=judge)
        await ob.check_run("my question", "my response")
        judge.score.assert_awaited_once_with(prompt="my question", response="my response")

    @pytest.mark.asyncio
    async def test_evidence_ref_set(self):
        ob = O3ContentSafety(judge=_make_judge())
        ev = await ob.check_run("q", "r")
        assert ev.evidence is not None
        assert ev.evidence.sha256

    @pytest.mark.asyncio
    async def test_measurement_technique_set(self):
        ob = O3ContentSafety(judge=_make_judge())
        ev = await ob.check_run("q", "r")
        assert ev.measurement_technique == "3.1.3"

    @pytest.mark.asyncio
    async def test_regulatory_tags_present(self):
        ob = O3ContentSafety(judge=_make_judge())
        ev = await ob.check_run("q", "r")
        assert "EU_AI_ACT.Art9" in ev.regulatory_tags
