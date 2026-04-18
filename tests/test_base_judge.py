"""
Tests for BaseJudge shared plumbing.

Covers: _parse_json, evaluate() template method, compare() fallback/exception
paths, ABC enforcement.
All tests use a concrete stub subclass — no live LLM or Ollama required.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "praktor"))


# ---------------------------------------------------------------------------
# Concrete stub for testing abstract methods
# ---------------------------------------------------------------------------

def _make_stub_judge(model: str = "test-model"):
    """Return a concrete BaseJudge subclass with no-op abstract methods."""
    from clinical.evaluation.base_judge import BaseJudge

    class _StubJudge(BaseJudge):
        _eval_prompt = "evaluate: {response}"
        _compare_prompt = "compare: {recommendation_a} vs {recommendation_b}"
        _default_model = "test-model"

        def _parse_score(self, response, recommendation):
            return {"score": 7.0}

        def _neutral_score(self, reason):
            return {"score": 0.0, "reason": reason}

    with patch("clinical.evaluation.base_judge.BaseJudge._init_adapters"):
        j = _StubJudge(model=model)
    j._eval_adapter = MagicMock()
    j._compare_adapter = MagicMock()
    return j


# ---------------------------------------------------------------------------
# ABC enforcement
# ---------------------------------------------------------------------------

class TestInitAdaptersGuard:

    def test_missing_eval_prompt_raises(self):
        from clinical.evaluation.base_judge import BaseJudge

        class _NoPrompt(BaseJudge):
            _eval_prompt = ""
            _compare_prompt = "compare: {recommendation_a} vs {recommendation_b}"
            _default_model = "test"

            def _parse_score(self, r, rec): return {}
            def _neutral_score(self, reason): return {}

        with pytest.raises(ValueError, match="_eval_prompt"):
            _NoPrompt()

    def test_missing_compare_prompt_raises(self):
        from clinical.evaluation.base_judge import BaseJudge

        class _NoCompare(BaseJudge):
            _eval_prompt = "evaluate: {response}"
            _compare_prompt = ""
            _default_model = "test"

            def _parse_score(self, r, rec): return {}
            def _neutral_score(self, reason): return {}

        with pytest.raises(ValueError, match="_compare_prompt"):
            _NoCompare()


class TestAbstractEnforcement:

    def test_cannot_instantiate_base_judge_directly(self):
        from clinical.evaluation.base_judge import BaseJudge
        with pytest.raises(TypeError):
            BaseJudge()  # type: ignore

    def test_subclass_missing_parse_score_raises(self):
        from clinical.evaluation.base_judge import BaseJudge
        class _Incomplete(BaseJudge):
            _eval_prompt = ""
            _compare_prompt = ""
            _default_model = "test"

            def _neutral_score(self, reason):
                return {}

        with pytest.raises(TypeError):
            _Incomplete()  # type: ignore

    def test_subclass_missing_neutral_score_raises(self):
        from clinical.evaluation.base_judge import BaseJudge
        class _Incomplete(BaseJudge):
            _eval_prompt = ""
            _compare_prompt = ""
            _default_model = "test"

            def _parse_score(self, response, recommendation):
                return {}

        with pytest.raises(TypeError):
            _Incomplete()  # type: ignore


# ---------------------------------------------------------------------------
# _parse_json
# ---------------------------------------------------------------------------

class TestParseJson:

    def setup_method(self):
        self.judge = _make_stub_judge()
        self._default = {"winner": "A", "confidence": 0.5}

    def test_plain_json_object(self):
        result = self.judge._parse_json('{"winner": "B", "confidence": 0.9}', self._default)
        assert result == {"winner": "B", "confidence": 0.9}

    def test_json_wrapped_in_code_block(self):
        text = '```json\n{"winner": "A", "confidence": 0.7}\n```'
        result = self.judge._parse_json(text, self._default)
        assert result["winner"] == "A"
        assert result["confidence"] == pytest.approx(0.7)

    def test_json_wrapped_in_plain_code_block(self):
        text = '```\n{"winner": "B", "confidence": 0.6}\n```'
        result = self.judge._parse_json(text, self._default)
        assert result["winner"] == "B"

    def test_json_embedded_in_prose(self):
        text = 'The winner is clearly {"winner": "A", "confidence": 0.8} based on evidence.'
        result = self.judge._parse_json(text, self._default)
        assert result["winner"] == "A"

    def test_malformed_json_returns_default(self):
        result = self.judge._parse_json('{"winner": "A", broken', self._default)
        assert result == self._default

    def test_no_json_returns_default(self):
        result = self.judge._parse_json("No JSON here at all.", self._default)
        assert result == self._default

    def test_empty_string_returns_default(self):
        result = self.judge._parse_json("", self._default)
        assert result == self._default

    def test_prose_before_json_does_not_corrupt_result(self):
        # Regression: greedy regex matched from first { in prose to last }
        text = 'Evaluating {recommendation}: result is {"winner": "B", "confidence": 0.7}'
        result = self.judge._parse_json(text, self._default)
        assert result.get("winner") == "B"


# ---------------------------------------------------------------------------
# compare()
# ---------------------------------------------------------------------------

class TestCompare:

    @pytest.mark.asyncio
    async def test_compare_adapter_none_returns_fallback(self):
        judge = _make_stub_judge()
        judge._compare_adapter = None
        result = await judge.compare("rec_a", "rec_b", "context")
        assert result["winner"] == "A"
        assert result["confidence"] == 0.5
        assert "unavailable" in result["reasoning"]

    @pytest.mark.asyncio
    async def test_compare_happy_path(self):
        judge = _make_stub_judge()
        judge._compare_adapter.ainvoke = AsyncMock(
            return_value='{"winner": "B", "confidence": 0.85, "reasoning": "B is more specific"}'
        )
        result = await judge.compare("rec_a", "rec_b", "context")
        assert result["winner"] == "B"
        assert result["confidence"] == pytest.approx(0.85)

    @pytest.mark.asyncio
    async def test_compare_exception_returns_fallback(self):
        judge = _make_stub_judge()
        judge._compare_adapter.ainvoke = AsyncMock(side_effect=RuntimeError("LLM unavailable"))
        result = await judge.compare("rec_a", "rec_b", "context")
        assert result["winner"] == "A"
        assert "LLM unavailable" in result["reasoning"]

    @pytest.mark.asyncio
    async def test_compare_normalizes_invalid_winner(self):
        judge = _make_stub_judge()
        judge._compare_adapter.ainvoke = AsyncMock(
            return_value='{"winner": "tie", "confidence": 0.5, "reasoning": "equal"}'
        )
        result = await judge.compare("rec_a", "rec_b", "context")
        assert result["winner"] == "A"  # normalized from "tie"

    @pytest.mark.asyncio
    async def test_compare_normalizes_lowercase_winner(self):
        judge = _make_stub_judge()
        judge._compare_adapter.ainvoke = AsyncMock(
            return_value='{"winner": "b", "confidence": 0.9, "reasoning": "B wins"}'
        )
        result = await judge.compare("rec_a", "rec_b", "context")
        assert result["winner"] == "B"


# ---------------------------------------------------------------------------
# evaluate() — template method
# ---------------------------------------------------------------------------

class TestEvaluate:

    @pytest.mark.asyncio
    async def test_evaluate_adapter_none_returns_neutral(self):
        judge = _make_stub_judge()
        judge._eval_adapter = None
        result = await judge.evaluate("some recommendation", "member context")
        assert result["score"] == 0.0
        assert result["reason"] == "adapter_unavailable"

    @pytest.mark.asyncio
    async def test_evaluate_str_recommendation_passes_through(self):
        judge = _make_stub_judge()
        judge._eval_adapter.ainvoke = AsyncMock(return_value='{"score": 8.0}')
        result = await judge.evaluate("plain string rec", "ctx")
        assert result["score"] == 7.0  # stub _parse_score always returns 7.0

    @pytest.mark.asyncio
    async def test_evaluate_dict_recommendation_serialized_to_json(self):
        judge = _make_stub_judge()
        captured = {}

        async def _capture(payload, **_):
            captured["rec"] = payload.get("recommendation", "")
            return "{}"

        judge._eval_adapter.ainvoke = _capture
        await judge.evaluate({"action": "outreach"}, "ctx")
        assert '"action"' in captured["rec"]
        assert '"outreach"' in captured["rec"]

    @pytest.mark.asyncio
    async def test_evaluate_happy_path_calls_parse_score(self):
        judge = _make_stub_judge()
        judge._eval_adapter.ainvoke = AsyncMock(return_value='{"ok": true}')
        result = await judge.evaluate("rec", "ctx", outcome="closed")
        assert result["score"] == 7.0

    @pytest.mark.asyncio
    async def test_evaluate_exception_returns_neutral(self):
        judge = _make_stub_judge()
        judge._eval_adapter.ainvoke = AsyncMock(side_effect=RuntimeError("timeout"))
        result = await judge.evaluate("rec", "ctx")
        assert result["score"] == 0.0
        assert "timeout" in result["reason"]
