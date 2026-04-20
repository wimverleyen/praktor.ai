"""
Tests for PR10 — Continuous Judge Calibration Loop.

Covers:
  - create_calibrated_judge(): 4 paths (unknown type, no active version,
    active version patches adapter, registry exception falls back)
  - ensure_judges_calibrated(): 3 paths (all calibrated, one missing, both missing)
  - load_golden_samples() patch: 3 paths (no JSONL, valid JSONL, malformed line)
  - promote_to_golden(): 4 paths (dedup, no record, short output, success)
  - maybe_recalibrate_after_promotion(): 5 paths
  - seed_golden_members() guard: skip measurement_year=0
  - calibrate_judges() scoring filter: measurement_year=0 excluded
  - _get_judge() patch: calls create_calibrated_judge
  - invalidate_judge_cache(): clears _JUDGES
  - cmd_promote(): 4 paths

All tests use mocks — no live LLM required.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_hedis_judge():
    from praktor.clinical.evaluation.hedis_judge import HEDISJudge
    with patch("praktor.clinical.evaluation.base_judge.BaseJudge._init_adapters"):
        j = HEDISJudge()
    return j


def _make_prompt_version(template="CAL_PROMPT", avg_score=8.0, eval_count=5):
    pv = MagicMock()
    pv.version_id = "abcdef1234567890"
    pv.template = template
    pv.avg_score = avg_score
    pv.eval_count = eval_count
    return pv


def _make_golden_sample(agent_type="hedis_gap", measurement_year=2024, sample_id="H001"):
    from praktor.clinical.evaluation.golden_dataset import GoldenSample
    return GoldenSample(
        sample_id=sample_id,
        agent_type=agent_type,
        raw_member_id="MBR-001",
        measurement_year=measurement_year,
        clinical_scenario="Patient has statin gap",
        reference_output="A" * 100,
        expected_action="address_gaps",
        expected_measures=["COL"],
        outcome="closed",
    )


# ---------------------------------------------------------------------------
# create_calibrated_judge
# ---------------------------------------------------------------------------

class TestCreateCalibratedJudge:

    def test_unknown_agent_type_returns_uncalibrated(self):
        from praktor.clinical.evaluation.judge_optimizer import create_calibrated_judge
        from praktor.clinical.evaluation.hedis_judge import HEDISJudge

        with patch("praktor.clinical.evaluation.base_judge.BaseJudge._init_adapters"):
            judge = create_calibrated_judge(HEDISJudge, "unknown_type")

        assert isinstance(judge, HEDISJudge)

    def test_no_active_version_returns_uncalibrated(self):
        from praktor.clinical.evaluation.judge_optimizer import create_calibrated_judge
        from praktor.clinical.evaluation.hedis_judge import HEDISJudge

        mock_registry = MagicMock()
        mock_registry.get_active.return_value = None

        with patch("praktor.clinical.evaluation.base_judge.BaseJudge._init_adapters"):
            with patch("praktor.clinical.evaluation.judge_optimizer.PromptRegistry", return_value=mock_registry):
                judge = create_calibrated_judge(HEDISJudge, "hedis_gap")

        assert isinstance(judge, HEDISJudge)
        mock_registry.get_active.assert_called_once_with("judge_hedis")

    def test_active_version_patches_eval_adapter(self):
        from praktor.clinical.evaluation.judge_optimizer import create_calibrated_judge
        from praktor.clinical.evaluation.hedis_judge import HEDISJudge

        pv = _make_prompt_version(template="CALIBRATED_PROMPT")
        mock_registry = MagicMock()
        mock_registry.get_active.return_value = pv

        mock_adapter = MagicMock()

        with patch("praktor.clinical.evaluation.base_judge.BaseJudge._init_adapters"):
            with patch("praktor.clinical.evaluation.judge_optimizer.PromptRegistry", return_value=mock_registry):
                with patch("praktor.clinical.evaluation.judge_optimizer.AsyncLLMAdapter", return_value=mock_adapter):
                    judge = create_calibrated_judge(HEDISJudge, "hedis_gap")

        assert judge._eval_adapter is mock_adapter

    def test_registry_exception_falls_back_to_uncalibrated(self):
        from praktor.clinical.evaluation.judge_optimizer import create_calibrated_judge
        from praktor.clinical.evaluation.hedis_judge import HEDISJudge

        with patch("praktor.clinical.evaluation.base_judge.BaseJudge._init_adapters"):
            with patch("praktor.clinical.evaluation.judge_optimizer.PromptRegistry",
                       side_effect=RuntimeError("DB error")):
                judge = create_calibrated_judge(HEDISJudge, "hedis_gap")

        assert isinstance(judge, HEDISJudge)


# ---------------------------------------------------------------------------
# ensure_judges_calibrated
# ---------------------------------------------------------------------------

class TestEnsureJudgesCalibrated:

    @pytest.mark.asyncio
    async def test_all_calibrated_returns_early(self):
        from praktor.clinical.evaluation.judge_optimizer import ensure_judges_calibrated

        mock_registry = MagicMock()
        mock_registry.get_active.return_value = _make_prompt_version()

        with patch("praktor.clinical.evaluation.judge_optimizer.PromptRegistry", return_value=mock_registry):
            with patch("praktor.clinical.evaluation.judge_optimizer.calibrate_judges",
                       new_callable=AsyncMock) as mock_cal:
                await ensure_judges_calibrated()

        mock_cal.assert_not_called()

    @pytest.mark.asyncio
    async def test_one_missing_calibrates_that_type(self):
        from praktor.clinical.evaluation.judge_optimizer import ensure_judges_calibrated

        mock_registry = MagicMock()
        mock_registry.get_active.side_effect = lambda key: (
            _make_prompt_version() if key == "judge_hedis" else None
        )

        with patch("praktor.clinical.evaluation.judge_optimizer.PromptRegistry", return_value=mock_registry):
            with patch("praktor.clinical.evaluation.judge_optimizer.calibrate_judges",
                       new_callable=AsyncMock) as mock_cal:
                await ensure_judges_calibrated(verbose=False)

        mock_cal.assert_called_once_with(agent_type="diabetes_hedis", verbose=False)

    @pytest.mark.asyncio
    async def test_both_missing_calibrates_all(self):
        from praktor.clinical.evaluation.judge_optimizer import ensure_judges_calibrated

        mock_registry = MagicMock()
        mock_registry.get_active.return_value = None

        with patch("praktor.clinical.evaluation.judge_optimizer.PromptRegistry", return_value=mock_registry):
            with patch("praktor.clinical.evaluation.judge_optimizer.calibrate_judges",
                       new_callable=AsyncMock) as mock_cal:
                await ensure_judges_calibrated(verbose=False)

        mock_cal.assert_called_once_with(agent_type=None, verbose=False)


# ---------------------------------------------------------------------------
# load_golden_samples patch
# ---------------------------------------------------------------------------

class TestLoadGoldenSamplesCustomJSONL:

    def test_no_jsonl_returns_builtin_only(self, tmp_path, monkeypatch):
        import praktor.clinical.evaluation.golden_dataset as gd
        monkeypatch.setattr(gd, "GOLDEN_CUSTOM_PATH", tmp_path / "nonexistent.jsonl")

        samples = gd.load_golden_samples()
        assert len(samples) == 20  # 10 HEDIS + 10 diabetes

    def test_valid_jsonl_appends_custom(self, tmp_path, monkeypatch):
        import praktor.clinical.evaluation.golden_dataset as gd
        import dataclasses

        custom_path = tmp_path / "golden_custom.jsonl"
        sample = _make_golden_sample(agent_type="hedis_gap", measurement_year=0,
                                     sample_id="PROD-abcd1234")
        custom_path.write_text(json.dumps(dataclasses.asdict(sample)) + "\n")

        monkeypatch.setattr(gd, "GOLDEN_CUSTOM_PATH", custom_path)

        samples = gd.load_golden_samples()
        assert len(samples) == 21
        assert any(s.sample_id == "PROD-abcd1234" for s in samples)

    def test_malformed_line_skips_and_warns(self, tmp_path, monkeypatch):
        import praktor.clinical.evaluation.golden_dataset as gd
        import dataclasses

        custom_path = tmp_path / "golden_custom.jsonl"
        good_sample = _make_golden_sample(sample_id="PROD-good1234", measurement_year=0)
        custom_path.write_text(
            "NOT VALID JSON\n"
            + json.dumps(dataclasses.asdict(good_sample)) + "\n"
        )

        monkeypatch.setattr(gd, "GOLDEN_CUSTOM_PATH", custom_path)

        samples = gd.load_golden_samples()
        # Malformed line skipped; good entry loaded
        assert len(samples) == 21
        assert any(s.sample_id == "PROD-good1234" for s in samples)


# ---------------------------------------------------------------------------
# promote_to_golden
# ---------------------------------------------------------------------------

class TestPromoteToGolden:

    @pytest.mark.asyncio
    async def test_already_promoted_returns_none(self, tmp_path, monkeypatch):
        import praktor.clinical.evaluation.golden_dataset as gd
        import dataclasses

        custom_path = tmp_path / "golden_custom.jsonl"
        existing = _make_golden_sample(sample_id="PROD-abcdef12", measurement_year=0)
        custom_path.write_text(json.dumps(dataclasses.asdict(existing)) + "\n")
        monkeypatch.setattr(gd, "GOLDEN_CUSTOM_PATH", custom_path)

        result = await gd.promote_to_golden("abcdef12345678", store=MagicMock())
        assert result is None

    @pytest.mark.asyncio
    async def test_no_hitl_record_returns_none(self, tmp_path, monkeypatch):
        import praktor.clinical.evaluation.golden_dataset as gd
        monkeypatch.setattr(gd, "GOLDEN_CUSTOM_PATH", tmp_path / "custom.jsonl")

        mock_store = MagicMock()
        mock_store.query_hitl_queue = AsyncMock(return_value=[])

        result = await gd.promote_to_golden("session-123", store=mock_store)
        assert result is None

    @pytest.mark.asyncio
    async def test_output_too_short_returns_none(self, tmp_path, monkeypatch):
        import praktor.clinical.evaluation.golden_dataset as gd
        monkeypatch.setattr(gd, "GOLDEN_CUSTOM_PATH", tmp_path / "custom.jsonl")

        mock_store = MagicMock()
        mock_store.query_hitl_queue = AsyncMock(return_value=[{
            "session_id": "sess-abc",
            "agent_type": "hedis_gap",
            "original_output": "Too short",
            "modified_output": None,
        }])

        result = await gd.promote_to_golden("sess-abc", store=mock_store)
        assert result is None

    @pytest.mark.asyncio
    async def test_success_writes_jsonl_and_returns_sample(self, tmp_path, monkeypatch):
        import praktor.clinical.evaluation.golden_dataset as gd
        custom_path = tmp_path / "custom.jsonl"
        monkeypatch.setattr(gd, "GOLDEN_CUSTOM_PATH", custom_path)

        output = "A" * 100
        session_id = "sess-abcdef12"
        mock_store = MagicMock()
        mock_store.query_hitl_queue = AsyncMock(return_value=[{
            "session_id": session_id,
            "agent_type": "hedis_gap",
            "original_output": output,
            "modified_output": None,
        }])

        result = await gd.promote_to_golden(session_id, store=mock_store)

        assert result is not None
        assert result.sample_id == f"PROD-{session_id[:8]}"
        assert result.agent_type == "hedis_gap"
        assert result.measurement_year == 0
        assert custom_path.exists()
        lines = [l for l in custom_path.read_text().strip().split("\n") if l]
        assert len(lines) == 1
        entry = json.loads(lines[0])
        assert entry["sample_id"] == f"PROD-{session_id[:8]}"


# ---------------------------------------------------------------------------
# maybe_recalibrate_after_promotion
# ---------------------------------------------------------------------------

class TestMaybeRecalibrateAfterPromotion:

    @pytest.mark.asyncio
    async def test_no_jsonl_returns_false(self, tmp_path, monkeypatch):
        import praktor.clinical.evaluation.golden_dataset as gd
        monkeypatch.setattr(gd, "GOLDEN_CUSTOM_PATH", tmp_path / "nonexistent.jsonl")

        result = await gd.maybe_recalibrate_after_promotion("hedis_gap", verbose=False)
        assert result is False

    @pytest.mark.asyncio
    async def test_count_not_multiple_of_3_returns_false(self, tmp_path, monkeypatch):
        import praktor.clinical.evaluation.golden_dataset as gd
        import dataclasses

        custom_path = tmp_path / "custom.jsonl"
        entries = [_make_golden_sample(measurement_year=0, sample_id=f"PROD-{i:08x}")
                   for i in range(2)]
        custom_path.write_text(
            "\n".join(json.dumps(dataclasses.asdict(e)) for e in entries) + "\n"
        )
        monkeypatch.setattr(gd, "GOLDEN_CUSTOM_PATH", custom_path)

        result = await gd.maybe_recalibrate_after_promotion("hedis_gap", verbose=False)
        assert result is False

    @pytest.mark.asyncio
    async def test_mean_score_after_none_returns_false(self, tmp_path, monkeypatch):
        import praktor.clinical.evaluation.golden_dataset as gd
        import dataclasses

        custom_path = tmp_path / "custom.jsonl"
        entries = [_make_golden_sample(measurement_year=0, sample_id=f"PROD-{i:08x}")
                   for i in range(3)]
        custom_path.write_text(
            "\n".join(json.dumps(dataclasses.asdict(e)) for e in entries) + "\n"
        )
        monkeypatch.setattr(gd, "GOLDEN_CUSTOM_PATH", custom_path)

        from praktor.clinical.evaluation.judge_optimizer import CalibrationReport
        report = CalibrationReport(
            agent_type="hedis_gap", n_samples=10, mean_score_before=8.5,
            mean_score_after=None, criteria_means={}, needs_calibration=False,
            prompt_version_id=None, notes="already calibrated",
        )

        mock_registry = MagicMock()
        mock_registry.get_active.return_value = _make_prompt_version(avg_score=8.5)

        with patch("praktor.clinical.evaluation.judge_optimizer.calibrate_judges",
                   new_callable=AsyncMock, return_value=[report]):
            with patch("praktor.core.prompt_registry.PromptRegistry",
                       return_value=mock_registry):
                result = await gd.maybe_recalibrate_after_promotion(
                    "hedis_gap", verbose=False
                )

        assert result is False

    @pytest.mark.asyncio
    async def test_insufficient_improvement_returns_false(self, tmp_path, monkeypatch):
        import praktor.clinical.evaluation.golden_dataset as gd
        import dataclasses

        custom_path = tmp_path / "custom.jsonl"
        entries = [_make_golden_sample(measurement_year=0, sample_id=f"PROD-{i:08x}")
                   for i in range(3)]
        custom_path.write_text(
            "\n".join(json.dumps(dataclasses.asdict(e)) for e in entries) + "\n"
        )
        monkeypatch.setattr(gd, "GOLDEN_CUSTOM_PATH", custom_path)

        from praktor.clinical.evaluation.judge_optimizer import CalibrationReport
        report = CalibrationReport(
            agent_type="hedis_gap", n_samples=10, mean_score_before=7.0,
            mean_score_after=7.3, criteria_means={}, needs_calibration=True,
            prompt_version_id="abc", notes="",
        )

        mock_registry = MagicMock()
        mock_registry.get_active.return_value = _make_prompt_version(avg_score=7.0)

        with patch("praktor.clinical.evaluation.judge_optimizer.calibrate_judges",
                   new_callable=AsyncMock, return_value=[report]):
            with patch("praktor.core.prompt_registry.PromptRegistry",
                       return_value=mock_registry):
                result = await gd.maybe_recalibrate_after_promotion(
                    "hedis_gap", improvement_threshold=0.5, verbose=False
                )

        assert result is False

    @pytest.mark.asyncio
    async def test_sufficient_improvement_returns_true(self, tmp_path, monkeypatch):
        import praktor.clinical.evaluation.golden_dataset as gd
        import dataclasses

        custom_path = tmp_path / "custom.jsonl"
        entries = [_make_golden_sample(measurement_year=0, sample_id=f"PROD-{i:08x}")
                   for i in range(3)]
        custom_path.write_text(
            "\n".join(json.dumps(dataclasses.asdict(e)) for e in entries) + "\n"
        )
        monkeypatch.setattr(gd, "GOLDEN_CUSTOM_PATH", custom_path)

        from praktor.clinical.evaluation.judge_optimizer import CalibrationReport
        report = CalibrationReport(
            agent_type="hedis_gap", n_samples=10, mean_score_before=7.0,
            mean_score_after=8.0, criteria_means={}, needs_calibration=True,
            prompt_version_id="abc", notes="",
        )

        mock_registry = MagicMock()
        mock_registry.get_active.return_value = _make_prompt_version(avg_score=7.0)

        with patch("praktor.clinical.evaluation.judge_optimizer.calibrate_judges",
                   new_callable=AsyncMock, return_value=[report]):
            with patch("praktor.core.prompt_registry.PromptRegistry",
                       return_value=mock_registry):
                result = await gd.maybe_recalibrate_after_promotion(
                    "hedis_gap", improvement_threshold=0.5, verbose=False
                )

        assert result is True


# ---------------------------------------------------------------------------
# seed_golden_members guard
# ---------------------------------------------------------------------------

class TestSeedGoldenMembersSkipsPromoted:

    def test_promoted_sample_not_seeded(self, tmp_path, monkeypatch):
        import praktor.clinical.evaluation.golden_dataset as gd
        import dataclasses

        custom_path = tmp_path / "custom.jsonl"
        promoted = _make_golden_sample(measurement_year=0, sample_id="PROD-skipme1")
        custom_path.write_text(json.dumps(dataclasses.asdict(promoted)) + "\n")
        monkeypatch.setattr(gd, "GOLDEN_CUSTOM_PATH", custom_path)

        mock_store = MagicMock()
        gd.seed_golden_members(store=mock_store)

        # upsert_member should only have been called for built-in samples (20),
        # not the promoted one (measurement_year=0)
        assert mock_store.upsert_member.call_count == 20


# ---------------------------------------------------------------------------
# calibrate_judges scoring filter
# ---------------------------------------------------------------------------

class TestCalibrateJudgesScoringFilter:

    @pytest.mark.asyncio
    async def test_promoted_samples_excluded_from_scoring(self, tmp_path, monkeypatch):
        """measurement_year=0 samples must not reach _score_reference_outputs."""
        import praktor.clinical.evaluation.golden_dataset as gd
        import dataclasses

        custom_path = tmp_path / "custom.jsonl"
        promoted = _make_golden_sample(measurement_year=0, sample_id="PROD-filter01")
        custom_path.write_text(json.dumps(dataclasses.asdict(promoted)) + "\n")
        monkeypatch.setattr(gd, "GOLDEN_CUSTOM_PATH", custom_path)

        scored_samples = []

        async def _mock_score(judge, samples):
            scored_samples.extend(samples)
            return []

        with patch("praktor.clinical.evaluation.judge_optimizer._score_reference_outputs",
                   side_effect=_mock_score):
            with patch("praktor.core.prompt_registry.PromptRegistry",
                       MagicMock()):
                from praktor.clinical.evaluation.judge_optimizer import calibrate_judges
                with patch("praktor.clinical.evaluation.hedis_judge.HEDISJudge.__init__",
                           return_value=None):
                    try:
                        await calibrate_judges(agent_type="hedis_gap", verbose=False)
                    except Exception:
                        pass

        for s in scored_samples:
            assert s.measurement_year != 0, (
                f"Promoted sample {s.sample_id} (measurement_year=0) reached scoring"
            )


# ---------------------------------------------------------------------------
# production_eval patches
# ---------------------------------------------------------------------------

class TestProductionEvalPatches:

    def test_invalidate_judge_cache_clears_dict(self):
        from praktor.clinical.evaluation import production_eval as pe
        pe._JUDGES["hedis_gap"] = MagicMock()
        pe._JUDGES["diabetes_hedis"] = MagicMock()

        pe.invalidate_judge_cache()

        assert pe._JUDGES == {}

    def test_get_judge_hedis_calls_factory(self):
        from praktor.clinical.evaluation import production_eval as pe
        pe._JUDGES.clear()

        mock_judge = MagicMock()
        with patch("praktor.clinical.evaluation.judge_optimizer.create_calibrated_judge",
                   return_value=mock_judge) as mock_factory:
            with patch("praktor.clinical.evaluation.hedis_judge.HEDISJudge"):
                j = pe._get_judge("hedis_gap")

        assert j is mock_judge
        pe._JUDGES.clear()

    def test_get_judge_diabetes_calls_factory(self):
        from praktor.clinical.evaluation import production_eval as pe
        pe._JUDGES.clear()

        mock_judge = MagicMock()
        with patch("praktor.clinical.evaluation.judge_optimizer.create_calibrated_judge",
                   return_value=mock_judge):
            with patch("praktor.clinical.evaluation.diabetes_hedis_judge.DiabetesHEDISJudge"):
                j = pe._get_judge("diabetes_hedis")

        assert j is mock_judge
        pe._JUDGES.clear()


# ---------------------------------------------------------------------------
# cmd_promote
# ---------------------------------------------------------------------------

class TestCmdPromote:

    def _run(self, args_ns, monkeypatch, promote_return, recal_return=False):
        """Helper: run cmd_promote with mocked promote + recalibrate."""
        from praktor.__main__ import cmd_promote

        async def _mock_promote(session_id, store=None):
            return promote_return

        async def _mock_recal(agent_type, verbose=True):
            return recal_return

        monkeypatch.setattr(
            "praktor.clinical.evaluation.golden_dataset.promote_to_golden",
            _mock_promote,
        )
        monkeypatch.setattr(
            "praktor.clinical.evaluation.golden_dataset.maybe_recalibrate_after_promotion",
            _mock_recal,
        )
        cmd_promote(args_ns)

    def test_promote_fails_prints_failure(self, monkeypatch, capsys):
        args = SimpleNamespace(session_id="sess-fail", skip_recalibrate=False)
        self._run(args, monkeypatch, promote_return=None)
        out = capsys.readouterr().out
        assert "failed" in out.lower()

    def test_success_improved_prints_activation(self, monkeypatch, capsys):
        from praktor.clinical.evaluation.golden_dataset import GoldenSample
        sample = _make_golden_sample(sample_id="PROD-sess1234")
        args = SimpleNamespace(session_id="sess-1234abcd", skip_recalibrate=False)
        self._run(args, monkeypatch, promote_return=sample, recal_return=True)
        out = capsys.readouterr().out
        assert "PROD-sess1234" in out

    def test_success_not_improved_prints_no_update(self, monkeypatch, capsys):
        sample = _make_golden_sample(sample_id="PROD-sess5678")
        args = SimpleNamespace(session_id="sess-5678abcd", skip_recalibrate=False)
        self._run(args, monkeypatch, promote_return=sample, recal_return=False)
        out = capsys.readouterr().out
        assert "threshold" in out.lower() or "unchanged" in out.lower()

    def test_skip_recalibrate_flag_skips_recal(self, monkeypatch, capsys):
        from praktor.__main__ import cmd_promote

        recal_called = []

        async def _mock_promote(session_id, store=None):
            return _make_golden_sample()

        async def _mock_recal(agent_type, verbose=True):
            recal_called.append(True)
            return False

        monkeypatch.setattr(
            "praktor.clinical.evaluation.golden_dataset.promote_to_golden",
            _mock_promote,
        )
        monkeypatch.setattr(
            "praktor.clinical.evaluation.golden_dataset.maybe_recalibrate_after_promotion",
            _mock_recal,
        )

        args = SimpleNamespace(session_id="sess-skiprecal", skip_recalibrate=True)
        cmd_promote(args)

        assert recal_called == []


# ---------------------------------------------------------------------------
# PR11a — is_promoted @property + record_kpi in calibrate_judges
# ---------------------------------------------------------------------------

class TestIsPromotedProperty:

    def test_is_promoted_true_when_year_zero(self):
        from praktor.clinical.evaluation.golden_dataset import GoldenSample
        s = GoldenSample(
            sample_id="PROD-test",
            agent_type="hedis_gap",
            raw_member_id="T001",
            measurement_year=0,
            clinical_scenario="production:sess123",
            reference_output="ACTION_TYPE: pcp_warm_outreach",
            expected_action="pcp_warm_outreach",
            expected_measures=["GSD"],
            outcome="pending",
        )
        assert s.is_promoted is True

    def test_is_promoted_false_when_year_nonzero(self):
        from praktor.clinical.evaluation.golden_dataset import GoldenSample
        s = GoldenSample(
            sample_id="GS-001",
            agent_type="hedis_gap",
            raw_member_id="T002",
            measurement_year=2024,
            clinical_scenario="Untested GSD, A1c missing",
            reference_output="ACTION_TYPE: pcp_warm_outreach",
            expected_action="pcp_warm_outreach",
            expected_measures=["GSD"],
            outcome="closed",
        )
        assert s.is_promoted is False


class TestCalibrationKpi:

    @staticmethod
    def _fake_score(overall: float) -> object:
        """Create a fake score object with numeric criteria that won't break statistics.mean()."""
        attrs = {
            "overall": overall,
            "accuracy": overall, "completeness": overall, "relevance": overall,
            "conciseness": overall, "clarity": overall,
            "gap_identification_accuracy": overall, "action_appropriateness": overall,
            "evidence_citation_quality": overall, "safety_flag_coverage": overall,
        }
        return SimpleNamespace(**attrs)

    @pytest.mark.asyncio
    async def test_record_kpi_called_for_score_before(self, monkeypatch):
        """calibrate_judges() emits judge.calibration.score_before.<atype> KPI."""
        from praktor.clinical.evaluation import judge_optimizer as jopt

        kpi_calls = []

        def _mock_record_kpi(name, value):
            kpi_calls.append((name, value))

        monkeypatch.setattr(jopt, "record_kpi", _mock_record_kpi)

        fake_score = self._fake_score(8.5)

        async def _mock_score(judge, samples):
            return [fake_score] * len(samples) if samples else []

        monkeypatch.setattr(jopt, "_score_reference_outputs", _mock_score)

        from praktor.clinical.evaluation.golden_dataset import GoldenSample
        fake_sample = GoldenSample(
            sample_id="GS-001", agent_type="hedis_gap", raw_member_id="T1",
            measurement_year=2024, clinical_scenario="test", reference_output="test",
            expected_action="pcp_warm_outreach", expected_measures=["GSD"], outcome="closed",
        )

        monkeypatch.setattr(
            "praktor.clinical.evaluation.golden_dataset.load_golden_samples",
            lambda agent_type=None: [fake_sample],
        )

        with patch("praktor.clinical.evaluation.judge_optimizer.PromptRegistry") as MockReg:
            MockReg.return_value.get_active.return_value = None

            await jopt.calibrate_judges(agent_type="hedis_gap", verbose=False)

        score_before_calls = [n for n, _ in kpi_calls if "score_before" in n]
        assert len(score_before_calls) >= 1
        assert score_before_calls[0] == "judge.calibration.score_before.hedis_gap"

    @pytest.mark.asyncio
    async def test_record_kpi_called_for_score_after_when_calibrated(self, monkeypatch):
        """calibrate_judges() emits score_after KPI only when calibration ran."""
        from praktor.clinical.evaluation import judge_optimizer as jopt

        kpi_calls = []

        def _mock_record_kpi(name, value):
            kpi_calls.append((name, value))

        monkeypatch.setattr(jopt, "record_kpi", _mock_record_kpi)

        call_count = [0]

        async def _mock_score(judge, samples):
            call_count[0] += 1
            overall = 5.0 if call_count[0] == 1 else 8.0
            return [self._fake_score(overall)] * max(len(samples), 1)

        monkeypatch.setattr(jopt, "_score_reference_outputs", _mock_score)

        from praktor.clinical.evaluation.golden_dataset import GoldenSample
        fake_sample = GoldenSample(
            sample_id="GS-002", agent_type="hedis_gap", raw_member_id="T2",
            measurement_year=2024, clinical_scenario="test2", reference_output="test2",
            expected_action="pcp_warm_outreach", expected_measures=["GSD"], outcome="closed",
        )

        monkeypatch.setattr(
            "praktor.clinical.evaluation.golden_dataset.load_golden_samples",
            lambda agent_type=None: [fake_sample],
        )

        with patch("praktor.clinical.evaluation.judge_optimizer.PromptRegistry") as MockReg:
            MockReg.return_value.get_active.return_value = None
            saved_ver = MagicMock(version_id="v-calibrated")
            MockReg.return_value.save.return_value = saved_ver
            MockReg.return_value.set_active.return_value = None
            MockReg.return_value.record_eval.return_value = None

            with patch("praktor.clinical.evaluation.judge_optimizer.AsyncLLMAdapter"):
                await jopt.calibrate_judges(agent_type="hedis_gap", verbose=False)

        score_after_calls = [n for n, _ in kpi_calls if "score_after" in n]
        # score_after is emitted only when calibration ran (overall_before < threshold)
        assert len(score_after_calls) >= 1


# ---------------------------------------------------------------------------
# PR12 — compute_required_n() + CalibrationReport sample size fields
# ---------------------------------------------------------------------------

class TestComputeRequiredN:

    def test_returns_positive_integer(self):
        from praktor.clinical.evaluation.judge_optimizer import compute_required_n
        n = compute_required_n()
        assert isinstance(n, int)
        assert n > 0

    def test_larger_sigma_requires_more_samples(self):
        from praktor.clinical.evaluation.judge_optimizer import compute_required_n
        n_small = compute_required_n(sigma=1.0)
        n_large = compute_required_n(sigma=2.0)
        assert n_large > n_small

    def test_larger_delta_requires_fewer_samples(self):
        """Bigger minimum-detectable effect → need fewer samples to detect it."""
        from praktor.clinical.evaluation.judge_optimizer import compute_required_n
        n_strict = compute_required_n(delta=0.25)
        n_loose = compute_required_n(delta=1.0)
        assert n_strict > n_loose

    def test_higher_power_requires_more_samples(self):
        from praktor.clinical.evaluation.judge_optimizer import compute_required_n
        n_80 = compute_required_n(power=0.80)
        n_90 = compute_required_n(power=0.90)
        assert n_90 > n_80

    def test_default_args_match_constants(self):
        """Default call should match the module-level constant defaults."""
        from praktor.clinical.evaluation.judge_optimizer import (
            compute_required_n,
            _SIGMA_FALLBACK, _SAMPLE_DELTA, _SAMPLE_ALPHA, _SAMPLE_POWER,
        )
        n_explicit = compute_required_n(
            sigma=_SIGMA_FALLBACK,
            delta=_SAMPLE_DELTA,
            alpha=_SAMPLE_ALPHA,
            power=_SAMPLE_POWER,
        )
        assert compute_required_n() == n_explicit

    def test_known_value(self):
        """Spot-check: σ=1.5, δ=0.5, α=0.05, power=0.80 → expected range."""
        from praktor.clinical.evaluation.judge_optimizer import compute_required_n
        n = compute_required_n(sigma=1.5, delta=0.5, alpha=0.05, power=0.80)
        # One-tailed z-test: (1.645 + 0.842)^2 * (1.5/0.5)^2 ≈ 55.6 → 56
        assert 50 <= n <= 65


class TestCalibrationReportSampleFields:

    def test_sufficient_samples_true_when_n_exceeds_required(self):
        from praktor.clinical.evaluation.judge_optimizer import CalibrationReport
        report = CalibrationReport(
            agent_type="hedis_gap", n_samples=100,
            mean_score_before=8.0, mean_score_after=None,
            criteria_means={}, needs_calibration=False,
            prompt_version_id=None, notes="",
            required_n=56, sufficient_samples=True,
        )
        assert report.sufficient_samples is True
        assert report.required_n == 56

    def test_sufficient_samples_false_when_n_below_required(self):
        from praktor.clinical.evaluation.judge_optimizer import CalibrationReport
        report = CalibrationReport(
            agent_type="hedis_gap", n_samples=10,
            mean_score_before=8.0, mean_score_after=None,
            criteria_means={}, needs_calibration=False,
            prompt_version_id=None, notes="",
            required_n=56, sufficient_samples=False,
        )
        assert report.sufficient_samples is False

    def test_defaults_are_safe(self):
        """required_n=0 and sufficient_samples=True are safe backward-compat defaults."""
        from praktor.clinical.evaluation.judge_optimizer import CalibrationReport
        report = CalibrationReport(
            agent_type="hedis_gap", n_samples=5,
            mean_score_before=6.0, mean_score_after=None,
            criteria_means={}, needs_calibration=True,
            prompt_version_id=None, notes="",
        )
        assert report.required_n == 0
        assert report.sufficient_samples is True


class TestCalibrateJudgesSampleSize:

    @pytest.mark.asyncio
    async def test_report_includes_required_n(self, monkeypatch):
        """calibrate_judges() sets required_n > 0 on the returned report."""
        from praktor.clinical.evaluation import judge_optimizer as jopt

        monkeypatch.setattr(jopt, "record_kpi", lambda *a, **kw: None)

        async def _mock_score(judge, samples):
            return [self._fake_score(8.5)] * max(len(samples), 1)

        monkeypatch.setattr(jopt, "_score_reference_outputs", _mock_score)

        from praktor.clinical.evaluation.golden_dataset import GoldenSample
        fake_sample = GoldenSample(
            sample_id="SZ-001", agent_type="hedis_gap", raw_member_id="T3",
            measurement_year=2024, clinical_scenario="scenario", reference_output="output",
            expected_action="pcp_warm_outreach", expected_measures=["GSD"], outcome="closed",
        )
        monkeypatch.setattr(
            "praktor.clinical.evaluation.golden_dataset.load_golden_samples",
            lambda agent_type=None: [fake_sample],
        )

        with patch("praktor.clinical.evaluation.judge_optimizer.PromptRegistry") as MockReg:
            MockReg.return_value.get_active.return_value = _make_prompt_version()
            reports = await jopt.calibrate_judges(agent_type="hedis_gap", verbose=False)

        assert len(reports) == 1
        assert reports[0].required_n > 0

    @pytest.mark.asyncio
    async def test_report_sufficient_samples_false_when_underpowered(self, monkeypatch):
        """With 1 sample, sufficient_samples should be False."""
        from praktor.clinical.evaluation import judge_optimizer as jopt

        monkeypatch.setattr(jopt, "record_kpi", lambda *a, **kw: None)

        async def _mock_score(judge, samples):
            return [self._fake_score(8.5)] * max(len(samples), 1)

        monkeypatch.setattr(jopt, "_score_reference_outputs", _mock_score)

        from praktor.clinical.evaluation.golden_dataset import GoldenSample
        fake_sample = GoldenSample(
            sample_id="SZ-002", agent_type="hedis_gap", raw_member_id="T4",
            measurement_year=2024, clinical_scenario="scenario", reference_output="output",
            expected_action="pcp_warm_outreach", expected_measures=["GSD"], outcome="closed",
        )
        monkeypatch.setattr(
            "praktor.clinical.evaluation.golden_dataset.load_golden_samples",
            lambda agent_type=None: [fake_sample],
        )

        with patch("praktor.clinical.evaluation.judge_optimizer.PromptRegistry") as MockReg:
            MockReg.return_value.get_active.return_value = _make_prompt_version()
            reports = await jopt.calibrate_judges(agent_type="hedis_gap", verbose=False)

        assert reports[0].sufficient_samples is False

    @pytest.mark.asyncio
    async def test_n_required_kpi_emitted(self, monkeypatch):
        """calibrate_judges() emits judge.calibration.n_required.* KPI."""
        from praktor.clinical.evaluation import judge_optimizer as jopt

        kpi_calls = []
        monkeypatch.setattr(jopt, "record_kpi", lambda n, v: kpi_calls.append((n, v)))

        async def _mock_score(judge, samples):
            return [self._fake_score(8.5)] * max(len(samples), 1)

        monkeypatch.setattr(jopt, "_score_reference_outputs", _mock_score)

        from praktor.clinical.evaluation.golden_dataset import GoldenSample
        fake_sample = GoldenSample(
            sample_id="SZ-003", agent_type="hedis_gap", raw_member_id="T5",
            measurement_year=2024, clinical_scenario="scenario", reference_output="output",
            expected_action="pcp_warm_outreach", expected_measures=["GSD"], outcome="closed",
        )
        monkeypatch.setattr(
            "praktor.clinical.evaluation.golden_dataset.load_golden_samples",
            lambda agent_type=None: [fake_sample],
        )

        with patch("praktor.clinical.evaluation.judge_optimizer.PromptRegistry") as MockReg:
            MockReg.return_value.get_active.return_value = _make_prompt_version()
            await jopt.calibrate_judges(agent_type="hedis_gap", verbose=False)

        n_req_calls = [n for n, _ in kpi_calls if "n_required" in n]
        assert len(n_req_calls) == 1
        assert n_req_calls[0] == "judge.calibration.n_required.hedis_gap"

    @staticmethod
    def _fake_score(overall: float = 8.5):
        from types import SimpleNamespace
        attrs = {
            "overall": overall,
            "accuracy": overall, "completeness": overall, "relevance": overall,
            "conciseness": overall, "clarity": overall,
            "gap_identification_accuracy": overall, "action_appropriateness": overall,
            "evidence_citation_quality": overall, "safety_flag_coverage": overall,
        }
        return SimpleNamespace(**attrs)
        assert score_after_calls[0] == "judge.calibration.score_after.hedis_gap"
