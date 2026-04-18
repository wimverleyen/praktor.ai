"""
Tests for LLM-as-judge evaluators in governance/evaluators/llm_judge.py.

All tests mock AsyncLLMAdapter.ainvoke so no live LLM is required.
"""

import asyncio
import json
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "praktor"))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_adapter_mock(payload: dict):
    """Return a mock AsyncLLMAdapter whose ainvoke returns a JSON string."""
    mock = MagicMock()
    mock.ainvoke = AsyncMock(return_value=json.dumps(payload))
    return mock


# ---------------------------------------------------------------------------
# PHI guard
# ---------------------------------------------------------------------------

class TestPHIGuard:
    def test_local_model_no_warning(self, caplog):
        import logging
        from governance.evaluators.llm_judge import FaithfulnessJudge

        with patch("governance.evaluators.llm_judge.AsyncLLMAdapter"):
            with caplog.at_level(logging.WARNING, logger="praktor"):
                judge = FaithfulnessJudge(model="qwen2.5")
        assert "off-device" not in caplog.text

    def test_cloud_model_emits_warning(self):
        from governance.evaluators.llm_judge import FaithfulnessJudge

        env_clean = {k: v for k, v in os.environ.items() if k != "PRAKTOR_AIR_GAPPED"}
        with patch.dict(os.environ, env_clean, clear=True):
            with patch("governance.evaluators.llm_judge.AsyncLLMAdapter"):
                with patch("governance.evaluators.llm_judge.log") as mock_log:
                    FaithfulnessJudge(model="claude-sonnet-4-6")
        mock_log.warning.assert_called_once()
        assert "off-device" in mock_log.warning.call_args[0][0]

    def test_air_gapped_cloud_model_raises(self):
        from governance.evaluators.llm_judge import FaithfulnessJudge

        with patch.dict(os.environ, {"PRAKTOR_AIR_GAPPED": "1"}):
            with patch("governance.evaluators.llm_judge.AsyncLLMAdapter"):
                with pytest.raises(RuntimeError, match="air-gapped"):
                    FaithfulnessJudge(model="claude-sonnet-4-6")

    def test_air_gapped_local_model_ok(self):
        from governance.evaluators.llm_judge import SafetyJudge

        with patch.dict(os.environ, {"PRAKTOR_AIR_GAPPED": "1"}):
            with patch("governance.evaluators.llm_judge.AsyncLLMAdapter"):
                judge = SafetyJudge(model="qwen2.5")
        assert judge._model == "qwen2.5"


# ---------------------------------------------------------------------------
# LLMJudgeEvaluator base
# ---------------------------------------------------------------------------

class TestLLMJudgeEvaluator:

    @pytest.mark.asyncio
    async def test_score_pass(self):
        from governance.evaluators.llm_judge import FaithfulnessJudge

        with patch("governance.evaluators.llm_judge.AsyncLLMAdapter") as Adapter:
            Adapter.return_value = _make_adapter_mock({"score": 8.0, "reasoning": "well grounded"})
            judge = FaithfulnessJudge()

        result = await judge.score(prompt="p", response="r")
        assert result.value == 8.0
        assert result.pass_ is True
        assert result.reasoning == "well grounded"
        assert result.timed_out is False

    @pytest.mark.asyncio
    async def test_score_fail(self):
        from governance.evaluators.llm_judge import FaithfulnessJudge

        with patch("governance.evaluators.llm_judge.AsyncLLMAdapter") as Adapter:
            Adapter.return_value = _make_adapter_mock({"score": 4.0, "reasoning": "fabricated"})
            judge = FaithfulnessJudge()

        result = await judge.score(prompt="p", response="r")
        assert result.pass_ is False

    @pytest.mark.asyncio
    async def test_timeout_fail_open(self):
        from governance.evaluators.llm_judge import FaithfulnessJudge

        async def _slow(*_a, **_kw):
            await asyncio.sleep(9999)

        with patch("governance.evaluators.llm_judge.AsyncLLMAdapter") as Adapter:
            Adapter.return_value.ainvoke = _slow
            judge = FaithfulnessJudge()

        with patch("governance.evaluators.llm_judge._JUDGE_TIMEOUT_S", 0.01):
            result = await judge.score(prompt="p", response="r")

        assert result.timed_out is True
        assert result.pass_ is False
        assert result.value == 5.0

    @pytest.mark.asyncio
    async def test_parse_error_fail_closed(self):
        from governance.evaluators.llm_judge import HelpfulnessJudge

        with patch("governance.evaluators.llm_judge.AsyncLLMAdapter") as Adapter:
            Adapter.return_value.ainvoke = AsyncMock(return_value="NOT JSON AT ALL !!!")
            judge = HelpfulnessJudge()

        result = await judge.score(prompt="p", response="r")
        assert result.value == 0.0
        assert result.pass_ is False

    @pytest.mark.asyncio
    async def test_parse_json_in_markdown_fence(self):
        from governance.evaluators.llm_judge import HelpfulnessJudge

        fenced = '```json\n{"score": 7.5, "reasoning": "good answer"}\n```'
        with patch("governance.evaluators.llm_judge.AsyncLLMAdapter") as Adapter:
            Adapter.return_value.ainvoke = AsyncMock(return_value=fenced)
            judge = HelpfulnessJudge()

        result = await judge.score(prompt="p", response="r")
        assert result.value == 7.5

    @pytest.mark.asyncio
    async def test_parse_embedded_json_object(self):
        from governance.evaluators.llm_judge import HelpfulnessJudge

        raw = 'Here is my evaluation: {"score": 6.0, "reasoning": "ok"} done.'
        with patch("governance.evaluators.llm_judge.AsyncLLMAdapter") as Adapter:
            Adapter.return_value.ainvoke = AsyncMock(return_value=raw)
            judge = HelpfulnessJudge()

        result = await judge.score(prompt="p", response="r")
        assert result.value == 6.0


# ---------------------------------------------------------------------------
# Domain judges — thresholds and names
# ---------------------------------------------------------------------------

class TestDomainJudges:

    @pytest.mark.asyncio
    async def test_faithfulness_threshold_6(self):
        from governance.evaluators.llm_judge import FaithfulnessJudge

        with patch("governance.evaluators.llm_judge.AsyncLLMAdapter") as A:
            A.return_value = _make_adapter_mock({"score": 5.9, "reasoning": "x"})
            j = FaithfulnessJudge()
        r = await j.score("p", "r")
        assert r.pass_ is False

        with patch("governance.evaluators.llm_judge.AsyncLLMAdapter") as A:
            A.return_value = _make_adapter_mock({"score": 6.0, "reasoning": "x"})
            j = FaithfulnessJudge()
        r = await j.score("p", "r")
        assert r.pass_ is True

    @pytest.mark.asyncio
    async def test_safety_threshold_7(self):
        from governance.evaluators.llm_judge import SafetyJudge

        with patch("governance.evaluators.llm_judge.AsyncLLMAdapter") as A:
            A.return_value = _make_adapter_mock({"score": 6.9, "reasoning": "x"})
            j = SafetyJudge()
        r = await j.score("p", "r")
        assert r.pass_ is False  # higher bar than faithfulness

        with patch("governance.evaluators.llm_judge.AsyncLLMAdapter") as A:
            A.return_value = _make_adapter_mock({"score": 7.0, "reasoning": "x"})
            j = SafetyJudge()
        r = await j.score("p", "r")
        assert r.pass_ is True

    def test_judge_names(self):
        from governance.evaluators.llm_judge import (
            FaithfulnessJudge,
            HelpfulnessJudge,
            SafetyJudge,
        )
        with patch("governance.evaluators.llm_judge.AsyncLLMAdapter"):
            assert FaithfulnessJudge().name == "FaithfulnessJudge"
            assert HelpfulnessJudge().name == "HelpfulnessJudge"
            assert SafetyJudge().name == "SafetyJudge"

    def test_safety_threshold_higher_than_others(self):
        from governance.evaluators.llm_judge import (
            FaithfulnessJudge,
            HelpfulnessJudge,
            SafetyJudge,
        )
        with patch("governance.evaluators.llm_judge.AsyncLLMAdapter"):
            assert SafetyJudge().threshold > FaithfulnessJudge().threshold
            assert SafetyJudge().threshold > HelpfulnessJudge().threshold


# ---------------------------------------------------------------------------
# __init__ exports
# ---------------------------------------------------------------------------

class TestEvaluatorsInit:
    def test_all_exports_importable(self):
        from governance.evaluators import (
            JudgeResult,
            LLMJudgeEvaluator,
            FaithfulnessJudge,
            HelpfulnessJudge,
            SafetyJudge,
        )
        assert JudgeResult is not None
        assert LLMJudgeEvaluator is not None

    def test_judge_result_dataclass(self):
        from governance.evaluators import JudgeResult
        r = JudgeResult(value=7.5, pass_=True, reasoning="good")
        assert r.value == 7.5
        assert r.pass_ is True
        assert r.timed_out is False
