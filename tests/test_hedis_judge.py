"""
Tests for HEDISJudge subclass methods.

Covers: _parse_score (all 9 fields + defaults), _neutral_score.
No live LLM or Ollama required.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "praktor"))


def _make_judge():
    from clinical.evaluation.hedis_judge import HEDISJudge
    with patch("clinical.evaluation.base_judge.BaseJudge._init_adapters"):
        j = HEDISJudge()
    return j


class TestHEDISJudgeParseScore:

    def setup_method(self):
        self.judge = _make_judge()

    def test_all_9_fields_parsed(self):
        raw = (
            '{"accuracy": 8.0, "completeness": 7.0, "relevance": 9.0, '
            '"conciseness": 6.0, "clarity": 7.5, '
            '"gap_identification_accuracy": 8.5, "action_appropriateness": 7.0, '
            '"evidence_citation_quality": 6.5, "safety_flag_coverage": 9.0, '
            '"reasoning": "solid recommendation"}'
        )
        from clinical.schemas import ClinicalJudgeScore
        score = self.judge._parse_score(raw, "rec")
        assert isinstance(score, ClinicalJudgeScore)
        assert score.accuracy == pytest.approx(8.0)
        assert score.completeness == pytest.approx(7.0)
        assert score.relevance == pytest.approx(9.0)
        assert score.conciseness == pytest.approx(6.0)
        assert score.clarity == pytest.approx(7.5)
        assert score.gap_identification_accuracy == pytest.approx(8.5)
        assert score.action_appropriateness == pytest.approx(7.0)
        assert score.evidence_citation_quality == pytest.approx(6.5)
        assert score.safety_flag_coverage == pytest.approx(9.0)
        assert score.reasoning == "solid recommendation"

    def test_missing_fields_default_to_5(self):
        score = self.judge._parse_score("{}", "rec")
        assert score.accuracy == pytest.approx(5.0)
        assert score.gap_identification_accuracy == pytest.approx(5.0)
        assert score.safety_flag_coverage == pytest.approx(5.0)

    def test_malformed_json_defaults_all_to_5(self):
        score = self.judge._parse_score("not json at all", "rec")
        assert score.accuracy == pytest.approx(5.0)
        assert score.overall == pytest.approx(5.0)

    def test_recommendation_id_is_string(self):
        score = self.judge._parse_score("{}", "rec")
        assert isinstance(score.recommendation_id, str)

    def test_overall_computed_from_all_9_criteria(self):
        raw = (
            '{"accuracy": 10.0, "completeness": 10.0, "relevance": 10.0, '
            '"conciseness": 10.0, "clarity": 10.0, '
            '"gap_identification_accuracy": 10.0, "action_appropriateness": 10.0, '
            '"evidence_citation_quality": 10.0, "safety_flag_coverage": 10.0}'
        )
        score = self.judge._parse_score(raw, "rec")
        assert score.overall == pytest.approx(10.0)


class TestHEDISJudgeNeutralScore:

    def setup_method(self):
        self.judge = _make_judge()

    def test_neutral_score_all_fields_at_5(self):
        score = self.judge._neutral_score("test reason")
        assert score.accuracy == pytest.approx(5.0)
        assert score.completeness == pytest.approx(5.0)
        assert score.gap_identification_accuracy == pytest.approx(5.0)
        assert score.safety_flag_coverage == pytest.approx(5.0)
        assert score.overall == pytest.approx(5.0)

    def test_neutral_score_reason_in_reasoning(self):
        score = self.judge._neutral_score("adapter_unavailable")
        assert score.reasoning == "adapter_unavailable"

    def test_neutral_score_recommendation_id_is_neutral(self):
        score = self.judge._neutral_score("x")
        assert score.recommendation_id == "neutral"
