"""
Tests for DiabetesHEDISJudge subclass methods and DiabetesJudgeScore properties.

Covers: _parse_score (all 10 fields + defaults), _neutral_score,
DiabetesJudgeScore.base_overall, diabetes_overall, overall, summary().
No live LLM or Ollama required.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "praktor"))


def _make_judge():
    from clinical.evaluation.diabetes_hedis_judge import DiabetesHEDISJudge
    with patch("clinical.evaluation.base_judge.BaseJudge._init_adapters"):
        j = DiabetesHEDISJudge()
    return j


class TestDiabetesJudgeScore:

    def _score(self, **kwargs):
        from clinical.schemas import DiabetesJudgeScore
        return DiabetesJudgeScore(recommendation_id="test", **kwargs)

    def test_base_overall_is_mean_of_5_base(self):
        s = self._score(accuracy=8.0, completeness=6.0, relevance=10.0, conciseness=4.0, clarity=7.0)
        assert s.base_overall == pytest.approx(7.0)

    def test_diabetes_overall_is_mean_of_5_diabetes(self):
        s = self._score(
            inertia_detection_accuracy=8.0,
            escalation_ladder_correctness=6.0,
            gap_stacking_completeness=10.0,
            evidence_anchor_quality=4.0,
            safety_exclusion_coverage=7.0,
        )
        assert s.diabetes_overall == pytest.approx(7.0)

    def test_overall_is_mean_of_all_10(self):
        s = self._score(
            accuracy=10.0, completeness=10.0, relevance=10.0, conciseness=10.0, clarity=10.0,
            inertia_detection_accuracy=10.0, escalation_ladder_correctness=10.0,
            gap_stacking_completeness=10.0, evidence_anchor_quality=10.0,
            safety_exclusion_coverage=10.0,
        )
        assert s.overall == pytest.approx(10.0)

    def test_overall_default_is_5(self):
        from clinical.schemas import DiabetesJudgeScore
        s = DiabetesJudgeScore(recommendation_id="x")
        assert s.overall == pytest.approx(5.0)

    def test_summary_contains_overall(self):
        from clinical.schemas import DiabetesJudgeScore
        s = DiabetesJudgeScore(recommendation_id="x")
        summary = s.summary()
        assert "overall=" in summary
        assert "base:" in summary
        assert "diabetes:" in summary


class TestDiabetesHEDISJudgeParseScore:

    def setup_method(self):
        self.judge = _make_judge()

    def test_all_10_fields_parsed(self):
        raw = (
            '{"accuracy": 8.0, "completeness": 7.0, "relevance": 9.0, '
            '"conciseness": 6.0, "clarity": 7.5, '
            '"inertia_detection_accuracy": 8.5, "escalation_ladder_correctness": 7.0, '
            '"gap_stacking_completeness": 6.5, "evidence_anchor_quality": 9.0, '
            '"safety_exclusion_coverage": 8.0, "reasoning": "good escalation"}'
        )
        from clinical.schemas import DiabetesJudgeScore
        score = self.judge._parse_score(raw, "rec")
        assert isinstance(score, DiabetesJudgeScore)
        assert score.accuracy == pytest.approx(8.0)
        assert score.inertia_detection_accuracy == pytest.approx(8.5)
        assert score.escalation_ladder_correctness == pytest.approx(7.0)
        assert score.gap_stacking_completeness == pytest.approx(6.5)
        assert score.evidence_anchor_quality == pytest.approx(9.0)
        assert score.safety_exclusion_coverage == pytest.approx(8.0)
        assert score.reasoning == "good escalation"

    def test_missing_fields_default_to_5(self):
        score = self.judge._parse_score("{}", "rec")
        assert score.inertia_detection_accuracy == pytest.approx(5.0)
        assert score.gap_stacking_completeness == pytest.approx(5.0)
        assert score.safety_exclusion_coverage == pytest.approx(5.0)

    def test_malformed_json_defaults_all_to_5(self):
        score = self.judge._parse_score("not valid json", "rec")
        assert score.overall == pytest.approx(5.0)

    def test_overall_computed_from_all_10_criteria(self):
        raw = (
            '{"accuracy": 10.0, "completeness": 10.0, "relevance": 10.0, '
            '"conciseness": 10.0, "clarity": 10.0, '
            '"inertia_detection_accuracy": 10.0, "escalation_ladder_correctness": 10.0, '
            '"gap_stacking_completeness": 10.0, "evidence_anchor_quality": 10.0, '
            '"safety_exclusion_coverage": 10.0}'
        )
        score = self.judge._parse_score(raw, "rec")
        assert score.overall == pytest.approx(10.0)


class TestDiabetesHEDISJudgeNeutralScore:

    def setup_method(self):
        self.judge = _make_judge()

    def test_neutral_score_all_fields_at_5(self):
        score = self.judge._neutral_score("test reason")
        assert score.accuracy == pytest.approx(5.0)
        assert score.inertia_detection_accuracy == pytest.approx(5.0)
        assert score.safety_exclusion_coverage == pytest.approx(5.0)
        assert score.overall == pytest.approx(5.0)

    def test_neutral_score_reason_in_reasoning(self):
        score = self.judge._neutral_score("adapter_unavailable")
        assert score.reasoning == "adapter_unavailable"

    def test_neutral_score_recommendation_id_is_neutral(self):
        score = self.judge._neutral_score("x")
        assert score.recommendation_id == "neutral"
