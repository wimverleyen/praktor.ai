"""
Tests for prompt versioning: PromptRegistry, JudgeEvaluator, PromptOptimizer.

All LLM calls are mocked — no live services needed.
"""
import sys
import asyncio
import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent / "praktor"))

import pytest

from core.prompt_registry import PromptRegistry, PromptVersion


# ===========================================================================
# PromptRegistry
# ===========================================================================

class TestPromptRegistry:

    def setup_method(self):
        """Each test gets its own temp directory."""
        self._tmp = tempfile.TemporaryDirectory()
        self.registry = PromptRegistry(store_dir=self._tmp.name)

    def teardown_method(self):
        self._tmp.cleanup()

    def test_save_and_list(self):
        v = self.registry.save("agent1", "Hello {question}", notes="first")
        versions = self.registry.list("agent1")
        assert len(versions) == 1
        assert versions[0].version_id == v.version_id
        assert versions[0].notes == "first"

    def test_dedup_same_content(self):
        v1 = self.registry.save("agent1", "Same template")
        v2 = self.registry.save("agent1", "Same template")
        assert v1.version_id == v2.version_id
        assert len(self.registry.list("agent1")) == 1

    def test_different_content_creates_new_version(self):
        self.registry.save("agent1", "Template A")
        self.registry.save("agent1", "Template B")
        assert len(self.registry.list("agent1")) == 2

    def test_set_active_marks_one(self):
        v1 = self.registry.save("agent1", "Prompt A")
        v2 = self.registry.save("agent1", "Prompt B")
        self.registry.set_active("agent1", v1.version_id)
        active = self.registry.get_active("agent1")
        assert active is not None
        assert active.version_id == v1.version_id

    def test_set_active_clears_others(self):
        v1 = self.registry.save("agent1", "Prompt A")
        v2 = self.registry.save("agent1", "Prompt B")
        self.registry.set_active("agent1", v1.version_id)
        self.registry.set_active("agent1", v2.version_id)
        versions = self.registry.list("agent1")
        active_count = sum(1 for v in versions if v.is_active)
        assert active_count == 1

    def test_get_active_none_when_not_set(self):
        self.registry.save("agent1", "Prompt X")
        assert self.registry.get_active("agent1") is None

    def test_set_active_nonexistent_raises(self):
        self.registry.save("agent1", "Prompt A")
        with pytest.raises(KeyError):
            self.registry.set_active("agent1", "nonexistent")

    def test_get_by_prefix(self):
        v = self.registry.save("agent1", "Template for prefix test")
        short = v.version_id[:6]
        result = self.registry.get("agent1", short)
        assert result.version_id == v.version_id

    def test_get_ambiguous_prefix_raises(self):
        # Force a collision by using a 1-char prefix (very likely ambiguous with 2+ versions)
        self.registry.save("agent1", "Prompt Alpha")
        self.registry.save("agent1", "Prompt Beta")
        versions = self.registry.list("agent1")
        ids = [v.version_id for v in versions]
        # Find a common prefix of length 1 that matches both
        for prefix_len in range(1, 12):
            prefix = ids[0][:prefix_len]
            if all(v.startswith(prefix) for v in ids):
                with pytest.raises(ValueError, match="Ambiguous"):
                    self.registry.get("agent1", prefix)
                break

    def test_record_eval_updates_avg_score(self):
        v = self.registry.save("agent1", "Template E")
        self.registry.record_eval("agent1", v.version_id, score=8.0, latency_ms=100.0)
        self.registry.record_eval("agent1", v.version_id, score=6.0, latency_ms=200.0)
        updated = self.registry.get("agent1", v.version_id)
        assert updated.eval_count == 2
        assert abs(updated.avg_score - 7.0) < 0.01
        assert abs(updated.avg_latency_ms - 150.0) < 0.01

    def test_delete_inactive_version(self):
        v1 = self.registry.save("agent1", "Prompt Del")
        v2 = self.registry.save("agent1", "Prompt Keep")
        self.registry.set_active("agent1", v2.version_id)
        self.registry.delete("agent1", v1.version_id)
        assert len(self.registry.list("agent1")) == 1

    def test_delete_active_version_raises(self):
        v = self.registry.save("agent1", "Active Prompt")
        self.registry.set_active("agent1", v.version_id)
        with pytest.raises(ValueError, match="active"):
            self.registry.delete("agent1", v.version_id)

    def test_diff_returns_unified_diff(self):
        v1 = self.registry.save("agent1", "Line A\nLine B\n")
        v2 = self.registry.save("agent1", "Line A\nLine C\n")
        diff = self.registry.diff("agent1", v1.version_id, v2.version_id)
        assert "-Line B" in diff
        assert "+Line C" in diff

    def test_diff_identical_returns_no_differences(self):
        v = self.registry.save("agent1", "Same content")
        diff = self.registry.diff("agent1", v.version_id, v.version_id)
        assert diff == "(no differences)"

    def test_save_set_active_flag(self):
        v = self.registry.save("agent1", "Active on save", set_active=True)
        assert self.registry.get_active("agent1").version_id == v.version_id

    def test_agents_lists_names(self):
        self.registry.save("alpha", "t1")
        self.registry.save("beta", "t2")
        names = self.registry.agents()
        assert "alpha" in names
        assert "beta" in names

    def test_short_id(self):
        v = self.registry.save("agent1", "Short ID test")
        assert len(v.short_id()) == 8
        assert v.version_id.startswith(v.short_id())


# ===========================================================================
# JudgeEvaluator
# ===========================================================================

class TestJudgeEvaluator:

    def _make_judge(self, response_json: str):
        """Create a JudgeEvaluator with a mocked LLM response."""
        from core.judge import JudgeEvaluator
        with patch("LLM.llm_factory.LLMFactory") as mock_factory:
            mock_factory.return_value.create_llm.return_value = MagicMock()
            judge = JudgeEvaluator(model="test-model")
        judge._adapter.ainvoke = AsyncMock(return_value=response_json)
        judge._compare_adapter.ainvoke = AsyncMock(return_value=response_json)
        return judge

    @pytest.mark.asyncio
    async def test_evaluate_parses_scores(self):
        payload = json.dumps({
            "relevance": 9.0,
            "accuracy": 8.0,
            "completeness": 7.0,
            "conciseness": 8.0,
            "reasoning": "Good answer.",
        })
        judge = self._make_judge(payload)
        score = await judge.evaluate("What is Python?", "Python is a language.")
        assert score.score == pytest.approx(8.0)
        assert score.criteria["relevance"] == 9.0
        assert score.reasoning == "Good answer."

    @pytest.mark.asyncio
    async def test_evaluate_handles_markdown_fences(self):
        payload = '```json\n{"relevance":7,"accuracy":7,"completeness":7,"conciseness":7,"reasoning":"ok"}\n```'
        judge = self._make_judge(payload)
        score = await judge.evaluate("q", "a")
        assert score.score == pytest.approx(7.0)

    @pytest.mark.asyncio
    async def test_evaluate_fallback_on_bad_json(self):
        judge = self._make_judge("This is not JSON at all.")
        # Should not raise; defaults to 5.0 for all criteria
        score = await judge.evaluate("q", "a")
        assert score.score == pytest.approx(5.0)

    @pytest.mark.asyncio
    async def test_compare_returns_winner(self):
        payload = json.dumps({
            "winner": "a",
            "score_a": 8.5,
            "score_b": 6.0,
            "reasoning": "A was more accurate.",
        })
        judge = self._make_judge(payload)
        result = await judge.compare("q", "response A", "response B")
        assert result["winner"] == "a"
        assert result["score_a"] == pytest.approx(8.5)

    def test_summary_format(self):
        from core.judge import JudgeScore
        score = JudgeScore(
            score=7.5,
            reasoning="Good.",
            criteria={"relevance": 8.0, "accuracy": 7.0, "completeness": 7.5, "conciseness": 7.5},
        )
        summary = score.summary()
        assert "7.5/10" in summary
        assert "rel=8.0" in summary


# ===========================================================================
# PromptOptimizer
# ===========================================================================

class TestPromptOptimizer:

    def setup_method(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.registry = PromptRegistry(store_dir=self._tmp.name)
        # Seed an active version
        self.registry.save("test_agent", "Answer this: {question}\n\nHistory: {history}", set_active=True)

    def teardown_method(self):
        self._tmp.cleanup()

    def _make_optimizer(self, new_prompt: str = "Improved: {question}\n\nHistory: {history}"):
        from core.prompt_optimizer import PromptOptimizer
        with patch("LLM.llm_factory.LLMFactory") as mock_factory:
            mock_factory.return_value.create_llm.return_value = MagicMock()
            opt = PromptOptimizer(
                agent_name="test_agent",
                model="test-model",
                registry=self.registry,
                use_dspy=False,
            )
        # Mock meta adapter to return the new prompt
        opt._meta_adapter.ainvoke = AsyncMock(return_value=new_prompt)
        # Mock judge to return a fixed score
        opt.judge.evaluate = AsyncMock(return_value=MagicMock(score=8.5))
        return opt

    @pytest.mark.asyncio
    async def test_optimize_native_saves_new_version(self):
        opt = self._make_optimizer("Better prompt: {question}\n\nHistory: {history}")
        examples = [{"input": {"question": "What is AI?"}, "output": "AI is..."}]
        result = await opt.optimize(examples, goal="Be more precise")
        assert result.mode == "native"
        assert result.version.version_id != self.registry.get_active("test_agent").version_id
        # New version exists in registry
        versions = self.registry.list("test_agent")
        assert len(versions) == 2

    @pytest.mark.asyncio
    async def test_optimize_returns_same_version_on_no_change(self):
        active = self.registry.get_active("test_agent")
        opt = self._make_optimizer(active.template)  # same template = no change
        examples = [{"input": {"question": "q"}, "output": "a"}]
        result = await opt.optimize(examples)
        assert result.notes == "no change"
        # Still only one version in the registry
        assert len(self.registry.list("test_agent")) == 1

    @pytest.mark.asyncio
    async def test_optimize_raises_without_active_version(self):
        empty_registry = PromptRegistry(store_dir=self._tmp.name + "/empty")
        from core.prompt_optimizer import PromptOptimizer
        with patch("LLM.llm_factory.LLMFactory") as mock_factory:
            mock_factory.return_value.create_llm.return_value = MagicMock()
            opt = PromptOptimizer(
                agent_name="no_agent",
                registry=empty_registry,
                use_dspy=False,
            )
        with pytest.raises(ValueError, match="No active prompt"):
            await opt.optimize([{"input": {"question": "q"}, "output": "a"}])

    @pytest.mark.asyncio
    async def test_evaluate_and_record_updates_registry(self):
        active = self.registry.get_active("test_agent")
        opt = self._make_optimizer()
        score = await opt.evaluate_and_record(
            version_id=active.version_id,
            question="What is Python?",
            response="Python is a language.",
        )
        assert score.score == pytest.approx(8.5)
        updated = self.registry.get("test_agent", active.version_id)
        assert updated.eval_count == 1
        assert updated.avg_score == pytest.approx(8.5)

    @pytest.mark.asyncio
    async def test_dspy_fallback_to_native_on_import_error(self):
        """When dspy is not importable, native fallback kicks in."""
        opt = self._make_optimizer("Native fallback prompt: {question}\n\nHistory: {history}")
        opt._use_dspy = True  # Enable DSPy preference

        import builtins
        real_import = builtins.__import__

        def _block_dspy(name, *args, **kwargs):
            if name == "dspy":
                raise ImportError("dspy not installed")
            return real_import(name, *args, **kwargs)

        examples = [{"input": {"question": "q"}, "output": "a"}]
        with patch("builtins.__import__", side_effect=_block_dspy):
            result = await opt.optimize(examples)

        assert result.mode == "native"
