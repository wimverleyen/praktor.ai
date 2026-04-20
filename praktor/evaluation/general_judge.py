"""
LLM-as-judge for general (non-clinical) agents.

Scores on 5 standard criteria (0–10 each):
  1. accuracy      — Is the answer factually correct and free of hallucinations?
  2. completeness  — Is all required information present?
  3. relevance     — Does the answer directly address the task?
  4. conciseness   — Is the response appropriately brief with no padding?
  5. clarity       — Is the output clear and well-structured?

Works for any agent_type. Registered as "judge_general" in PromptRegistry.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from praktor.settings import MODEL as _DEFAULT_MODEL, create_log
from praktor.clinical.evaluation.base_judge import BaseJudge

log = create_log()


@dataclass
class GeneralJudgeScore:
    recommendation_id: str
    accuracy: float
    completeness: float
    relevance: float
    conciseness: float
    clarity: float
    reasoning: str

    @property
    def overall(self) -> float:
        return (
            self.accuracy + self.completeness + self.relevance
            + self.conciseness + self.clarity
        ) / 5.0


_GENERAL_EVAL_PROMPT = """You are an expert evaluator assessing AI agent outputs.
Score this response on 5 criteria (0–10 each, where 10 is perfect).

TASK CONTEXT:
{member_context}

AGENT RESPONSE:
{recommendation}

SCORING CRITERIA:

1. accuracy (0-10):
   Is the response factually correct? No hallucinations, no fabricated details.
   Does it correctly address the specifics of the task?

2. completeness (0-10):
   Is all required information present? Nothing important omitted?
   Does it fully deliver what the task asked for?

3. relevance (0-10):
   Does the response directly address the stated task?
   Is it specific to the given inputs, not generic boilerplate?

4. conciseness (0-10):
   Is the length appropriate to the task?
   No unnecessary padding, repetition, or filler phrases?

5. clarity (0-10):
   Is the output clearly written and easy to understand?
   Good structure, professional tone, no ambiguous statements?

Output ONLY valid JSON:
{{"accuracy": N, "completeness": N, "relevance": N, "conciseness": N, "clarity": N,
 "reasoning": "one sentence explaining the scores"}}"""


_GENERAL_COMPARE_PROMPT = """You are an expert evaluator. Compare two AI agent responses
and determine which better fulfills the stated task.

TASK CONTEXT: {member_context}

RESPONSE A:
{recommendation_a}

RESPONSE B:
{recommendation_b}

Which response better fulfills the task?
Output ONLY valid JSON:
{{"winner": "A" or "B", "confidence": 0.0-1.0, "reasoning": "one sentence"}}"""


class GeneralJudge(BaseJudge):
    """
    5-criterion LLM judge for any agent type.

    Uses member_context as the task description (prompt + inputs summary).
    """

    _eval_prompt = _GENERAL_EVAL_PROMPT
    _compare_prompt = _GENERAL_COMPARE_PROMPT
    _default_model = _DEFAULT_MODEL

    def __init__(self, model: str | None = None) -> None:
        super().__init__(model=model)

    def _parse_score(self, response: str, recommendation: Any) -> GeneralJudgeScore:
        rec_id = str(id(recommendation))
        defaults = {
            "accuracy": 5.0, "completeness": 5.0, "relevance": 5.0,
            "conciseness": 5.0, "clarity": 5.0, "reasoning": "",
        }
        data = self._parse_json(response, defaults)
        return GeneralJudgeScore(
            recommendation_id=rec_id,
            accuracy=float(data.get("accuracy", 5.0)),
            completeness=float(data.get("completeness", 5.0)),
            relevance=float(data.get("relevance", 5.0)),
            conciseness=float(data.get("conciseness", 5.0)),
            clarity=float(data.get("clarity", 5.0)),
            reasoning=str(data.get("reasoning", "")),
        )

    def _neutral_score(self, reason: str) -> GeneralJudgeScore:
        return GeneralJudgeScore(
            recommendation_id="neutral",
            accuracy=5.0, completeness=5.0, relevance=5.0,
            conciseness=5.0, clarity=5.0,
            reasoning=reason,
        )
