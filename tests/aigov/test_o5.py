"""Tests for O5GroundedOutputs obligation."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from praktor.aigov.event import EnforcementPoint, PredicateResult, Severity
from praktor.aigov.manifests import DataFlowManifest, PrivacyTestDataset
from praktor.aigov.obligations.o5_grounded_outputs import O5GroundedOutputs


def _manifest(source_systems=None) -> DataFlowManifest:
    return DataFlowManifest(
        source_systems=["ehr", "claims_db"] if source_systems is None else source_systems,
        allowed_egress_destinations=["audit_log"],
        phi_fields=["member_id"],
        signed_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        deployer="ci-bot",
    )


def _mock_judge_result(value: float, pass_: bool, timed_out: bool = False):
    from praktor.governance.evaluators.llm_judge import JudgeResult
    result = JudgeResult(value=value, pass_=pass_, reasoning="test", timed_out=timed_out)
    return result


class TestCheckBuild:
    @pytest.mark.asyncio
    async def test_sources_declared_passes(self):
        ob = O5GroundedOutputs()
        ev = await ob.check_build(_manifest(["ehr"]))
        assert ev.predicate_result == PredicateResult.PASS
        assert ev.enforcement_point == EnforcementPoint.G_BUILD

    @pytest.mark.asyncio
    async def test_no_sources_fails(self):
        ob = O5GroundedOutputs()
        ev = await ob.check_build(_manifest([]))
        assert ev.predicate_result == PredicateResult.FAIL
        assert ev.severity == Severity.MEDIUM
        assert ev.deferred_reason == "no_retrieval_sources_in_manifest"

    @pytest.mark.asyncio
    async def test_evidence_ref_set(self):
        ob = O5GroundedOutputs()
        ev = await ob.check_build(_manifest())
        assert ev.evidence is not None
        assert len(ev.evidence.sha256) == 64

    @pytest.mark.asyncio
    async def test_regulatory_tags_present(self):
        ob = O5GroundedOutputs()
        ev = await ob.check_build(_manifest())
        assert "EU_AI_ACT.Art13" in ev.regulatory_tags


class TestCheckTest:
    @pytest.mark.asyncio
    async def test_empty_dataset_na(self):
        ob = O5GroundedOutputs()
        ds = PrivacyTestDataset(records=[], labels=[])
        ev = await ob.check_test(ds)
        assert ev.predicate_result == PredicateResult.NA
        assert ev.deferred_reason == "test_dataset_missing_prompt_response_fields"

    @pytest.mark.asyncio
    async def test_records_without_prompt_response_na(self):
        ob = O5GroundedOutputs()
        ds = PrivacyTestDataset(
            records=[{"ssn": "123-45-6789"}, {"email": "a@b.com"}],
            labels=["US_SSN", "EMAIL"],
        )
        ev = await ob.check_test(ds)
        assert ev.predicate_result == PredicateResult.NA

    @pytest.mark.asyncio
    async def test_all_passing_records_pass(self):
        ob = O5GroundedOutputs()
        records = [{"prompt": "What is X?", "response": "X is Y."} for _ in range(5)]
        ds = PrivacyTestDataset(records=records, labels=[""] * 5)
        passing_result = _mock_judge_result(8.0, True)
        with patch(
            "praktor.governance.evaluators.llm_judge.FaithfulnessJudge.score",
            new_callable=AsyncMock,
            return_value=passing_result,
        ):
            ev = await ob.check_test(ds)
        assert ev.predicate_result == PredicateResult.PASS
        assert ev.enforcement_point == EnforcementPoint.G_TEST

    @pytest.mark.asyncio
    async def test_mostly_failing_records_fail(self):
        ob = O5GroundedOutputs()
        records = [{"prompt": "Q", "response": "A"} for _ in range(10)]
        ds = PrivacyTestDataset(records=records, labels=[""] * 10)
        failing_result = _mock_judge_result(3.0, False)
        with patch(
            "praktor.governance.evaluators.llm_judge.FaithfulnessJudge.score",
            new_callable=AsyncMock,
            return_value=failing_result,
        ):
            ev = await ob.check_test(ds)
        assert ev.predicate_result == PredicateResult.FAIL
        assert ev.severity == Severity.HIGH

    @pytest.mark.asyncio
    async def test_supports_query_answer_keys(self):
        ob = O5GroundedOutputs()
        records = [{"query": "What?", "answer": "This."}]
        ds = PrivacyTestDataset(records=records, labels=[""])
        passing_result = _mock_judge_result(9.0, True)
        with patch(
            "praktor.governance.evaluators.llm_judge.FaithfulnessJudge.score",
            new_callable=AsyncMock,
            return_value=passing_result,
        ):
            ev = await ob.check_test(ds)
        assert ev.predicate_result == PredicateResult.PASS


class TestCheckRun:
    @pytest.mark.asyncio
    async def test_high_score_passes(self):
        ob = O5GroundedOutputs()
        passing = _mock_judge_result(8.5, True)
        with patch(
            "praktor.governance.evaluators.llm_judge.FaithfulnessJudge.score",
            new_callable=AsyncMock,
            return_value=passing,
        ):
            ev = await ob.check_run("context payload", "grounded response")
        assert ev.predicate_result == PredicateResult.PASS
        assert ev.enforcement_point == EnforcementPoint.G_RUN

    @pytest.mark.asyncio
    async def test_low_score_fails(self):
        ob = O5GroundedOutputs()
        failing = _mock_judge_result(2.0, False)
        with patch(
            "praktor.governance.evaluators.llm_judge.FaithfulnessJudge.score",
            new_callable=AsyncMock,
            return_value=failing,
        ):
            ev = await ob.check_run("payload", "hallucinated response")
        assert ev.predicate_result == PredicateResult.FAIL
        assert ev.severity == Severity.MEDIUM

    @pytest.mark.asyncio
    async def test_timeout_fails_with_deferred_reason(self):
        ob = O5GroundedOutputs()
        timed_out = _mock_judge_result(5.0, False, timed_out=True)
        with patch(
            "praktor.governance.evaluators.llm_judge.FaithfulnessJudge.score",
            new_callable=AsyncMock,
            return_value=timed_out,
        ):
            ev = await ob.check_run("payload", "response")
        assert ev.predicate_result == PredicateResult.FAIL
        assert ev.deferred_reason == "judge_timeout"

    @pytest.mark.asyncio
    async def test_judge_exception_returns_na(self):
        ob = O5GroundedOutputs()
        with patch(
            "praktor.governance.evaluators.llm_judge.FaithfulnessJudge.score",
            side_effect=RuntimeError("ollama not running"),
        ):
            ev = await ob.check_run("payload", "response")
        assert ev.predicate_result == PredicateResult.NA
        assert "judge_unavailable" in ev.deferred_reason

    @pytest.mark.asyncio
    async def test_evidence_ref_set(self):
        ob = O5GroundedOutputs()
        passing = _mock_judge_result(7.0, True)
        with patch(
            "praktor.governance.evaluators.llm_judge.FaithfulnessJudge.score",
            new_callable=AsyncMock,
            return_value=passing,
        ):
            ev = await ob.check_run("p", "r")
        assert ev.evidence is not None
        assert ev.evidence.sha256 != ""
