"""
Tests for Phase 2 evaluation passes: EvaluationPass wiring in Agent.run(),
RegexToxicityEvaluator, and evaluator load/fail behavior.
"""
import sys
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent / 'praktor'))

import pytest
from pydantic import BaseModel

from governance.evaluators import EvaluationPass, load_evaluator, EvaluatorUnavailableError
from governance.evaluators.toxicity import RegexToxicityEvaluator
from governance.policy import (
    GovernancePolicy, PolicyAction, AuditSinkType,
    EvaluationFailedError,
)
from governance.audit import AuditEntry


class _EvalInput(BaseModel):
    agent_type: str = "eval_test"
    text: str
    session_id: str = ""


# ---------------------------------------------------------------------------
# RegexToxicityEvaluator
# ---------------------------------------------------------------------------

class TestRegexToxicityEvaluator:

    @pytest.mark.asyncio
    async def test_clean_text_scores_high(self):
        evaluator = RegexToxicityEvaluator()
        score = await evaluator.score("What is AI?", "AI is artificial intelligence.")
        assert score == 1.0

    @pytest.mark.asyncio
    async def test_toxic_text_scores_low(self):
        evaluator = RegexToxicityEvaluator()
        score = await evaluator.score("Say something", "fuck this shit")
        assert score < 0.5

    @pytest.mark.asyncio
    async def test_empty_response_scores_one(self):
        evaluator = RegexToxicityEvaluator()
        score = await evaluator.score("Hello", "")
        assert score == 1.0

    @pytest.mark.asyncio
    async def test_metric_name(self):
        evaluator = RegexToxicityEvaluator()
        assert evaluator.metric_name == "toxicity"


# ---------------------------------------------------------------------------
# EvaluationPass loading
# ---------------------------------------------------------------------------

class TestEvaluatorLoading:

    def test_load_evaluator_by_path(self):
        evaluator = load_evaluator("governance.evaluators.toxicity.RegexToxicityEvaluator")
        assert isinstance(evaluator, RegexToxicityEvaluator)

    def test_load_evaluator_invalid_path_raises(self):
        with pytest.raises(ValueError, match="Invalid evaluator import path"):
            load_evaluator("InvalidPath")


# ---------------------------------------------------------------------------
# Agent.run() evaluation integration
# ---------------------------------------------------------------------------

class TestAgentEvaluationHooks:

    @pytest.mark.asyncio
    async def test_evaluation_pass_records_score(self):
        """Evaluator passes threshold: score recorded, agent continues."""
        from core.agent import Agent
        from core.agent_definition import AgentDefinition

        written_entries: list[AuditEntry] = []

        class _CaptureSink:
            async def write(self, entry):
                written_entries.append(entry)

        policy = GovernancePolicy(
            evaluation_passes=[
                EvaluationPass(
                    evaluator_class="governance.evaluators.toxicity.RegexToxicityEvaluator",
                    metric_name="toxicity",
                    pass_threshold=0.5,
                    on_fail=PolicyAction.FLAG,
                )
            ],
            audit_sinks=[AuditSinkType.STDOUT],
        )
        defn = AgentDefinition(
            name="eval_test",
            prompt_template="Answer: {text}",
            input_schema=_EvalInput,
            governance_policy=policy,
        )
        agent = Agent(defn)

        async def _fake_stream(payload, call_span=None):
            yield "clean response"

        with patch.object(agent._adapter, "astream", side_effect=_fake_stream):
            with patch("governance.audit.StdoutAuditSink", return_value=_CaptureSink()):
                chunks = []
                async for chunk in agent.run(
                    {"agent_type": "eval_test", "text": "Hello", "session_id": ""},
                    session_id="s1",
                ):
                    chunks.append(chunk)

        assert chunks == ["clean response"]
        assert len(written_entries) == 1
        scores = written_entries[0].evaluation_scores
        assert len(scores) == 1
        assert scores[0]["metric_name"] == "toxicity"
        assert scores[0]["pass"] is True

    @pytest.mark.asyncio
    async def test_evaluation_flag_on_fail(self):
        """Score below threshold with on_fail=FLAG: flagged=True, agent continues."""
        from core.agent import Agent
        from core.agent_definition import AgentDefinition

        written_entries: list[AuditEntry] = []

        class _CaptureSink:
            async def write(self, entry):
                written_entries.append(entry)

        policy = GovernancePolicy(
            evaluation_passes=[
                EvaluationPass(
                    evaluator_class="governance.evaluators.toxicity.RegexToxicityEvaluator",
                    metric_name="toxicity",
                    pass_threshold=1.0,  # impossibly high — forces fail
                    on_fail=PolicyAction.FLAG,
                )
            ],
            audit_sinks=[AuditSinkType.STDOUT],
        )
        defn = AgentDefinition(
            name="eval_test",
            prompt_template="Answer: {text}",
            input_schema=_EvalInput,
            governance_policy=policy,
        )
        agent = Agent(defn)

        # Response has one blocklist word so score < 1.0
        async def _fake_stream(payload, call_span=None):
            yield "this is damn annoying"

        with patch.object(agent._adapter, "astream", side_effect=_fake_stream):
            with patch("governance.audit.StdoutAuditSink", return_value=_CaptureSink()):
                chunks = []
                async for chunk in agent.run(
                    {"agent_type": "eval_test", "text": "test", "session_id": ""},
                    session_id="s1",
                ):
                    chunks.append(chunk)

        assert len(written_entries) == 1
        scores = written_entries[0].evaluation_scores
        assert len(scores) == 1
        assert scores[0]["pass"] is False

    @pytest.mark.asyncio
    async def test_evaluation_block_on_fail(self):
        """Score below threshold with on_fail=BLOCK: raises EvaluationFailedError."""
        from core.agent import Agent
        from core.agent_definition import AgentDefinition

        policy = GovernancePolicy(
            evaluation_passes=[
                EvaluationPass(
                    evaluator_class="governance.evaluators.toxicity.RegexToxicityEvaluator",
                    metric_name="toxicity",
                    pass_threshold=1.0,  # impossibly high
                    on_fail=PolicyAction.BLOCK,
                )
            ],
            audit_sinks=[AuditSinkType.STDOUT],
        )
        defn = AgentDefinition(
            name="eval_test",
            prompt_template="Answer: {text}",
            input_schema=_EvalInput,
            governance_policy=policy,
        )
        agent = Agent(defn)

        async def _fake_stream(payload, call_span=None):
            yield "damn this is bad"

        with patch.object(agent._adapter, "astream", side_effect=_fake_stream):
            with patch("governance.audit.StdoutAuditSink", return_value=MagicMock(write=AsyncMock())):
                with pytest.raises(EvaluationFailedError, match="toxicity"):
                    async for _ in agent.run(
                        {"agent_type": "eval_test", "text": "test", "session_id": ""},
                        session_id="s1",
                    ):
                        pass
