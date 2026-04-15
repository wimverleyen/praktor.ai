"""
LLM-as-judge evaluator for prompt quality assessment.

Scores agent outputs on four dimensions (0–10 each):
  relevance    — does the response address what was asked?
  accuracy     — is the content factually correct / logically sound?
  completeness — does it cover all key points?
  conciseness  — is it appropriately concise without padding?

Overall score = mean of the four dimensions.

Usage:
    judge = JudgeEvaluator(model="llama3:8b")
    score = await judge.evaluate(
        question="What is FAISS?",
        response="FAISS is a library for efficient similarity search...",
    )
    print(score.summary())

    cmp = await judge.compare(question, response_a, response_b)
    print(cmp["winner"])   # "a", "b", or "tie"
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from LLM.llm_interface import AsyncLLMAdapter
from settings import MODEL, create_log

log = create_log()

# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------

_EVAL_PROMPT = """\
You are an expert evaluator assessing the quality of an AI assistant's response.

QUESTION:
{question}

RESPONSE TO EVALUATE:
{response}

REFERENCE ANSWER (may be empty):
{expected}

Score the response on each criterion from 0.0 to 10.0:
- relevance:    Does the response directly address the question?
- accuracy:     Is the content factually correct and logically sound?
- completeness: Are all key points covered without major gaps?
- conciseness:  Is the response appropriately brief without unnecessary padding?

Reply ONLY with a JSON object — no prose, no markdown fences:
{{
  "relevance": <float>,
  "accuracy": <float>,
  "completeness": <float>,
  "conciseness": <float>,
  "reasoning": "<one sentence explaining the scores>"
}}"""

_COMPARE_PROMPT = """\
You are an expert evaluator comparing two AI assistant responses.

QUESTION:
{question}

RESPONSE A:
{response_a}

RESPONSE B:
{response_b}

Decide which response is better overall. Reply ONLY with a JSON object:
{{
  "winner": "<a|b|tie>",
  "score_a": <float 0-10>,
  "score_b": <float 0-10>,
  "reasoning": "<one sentence>"
}}"""


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class JudgeScore:
    """Evaluation result for a single response."""
    score: float                   # mean of four criteria (0–10)
    reasoning: str
    criteria: dict[str, float]     # {"relevance": x, "accuracy": x, ...}
    question: str = ""
    response: str = ""

    def summary(self) -> str:
        c = self.criteria
        return (
            f"overall={self.score:.1f}/10  "
            f"rel={c.get('relevance', 0):.1f}  "
            f"acc={c.get('accuracy', 0):.1f}  "
            f"cmp={c.get('completeness', 0):.1f}  "
            f"con={c.get('conciseness', 0):.1f}  "
            f"| {self.reasoning[:80]}"
        )


# ---------------------------------------------------------------------------
# Evaluator
# ---------------------------------------------------------------------------

class JudgeEvaluator:
    """
    Evaluates agent responses using an LLM as a judge.

    The evaluator is stateless — each call creates a fresh adapter invocation.
    Use a temperature=0 model for deterministic scoring (default).

    Args:
        model:       LLM model identifier (Ollama, OpenAI, Claude, etc.)
        temperature: Judge LLM temperature (default 0.0 for determinism)
    """

    _CRITERIA = ("relevance", "accuracy", "completeness", "conciseness")

    def __init__(
        self,
        model: str = MODEL,
        temperature: float = 0.0,
    ) -> None:
        self._model = model
        self._adapter = AsyncLLMAdapter(
            prompt_template=_EVAL_PROMPT,
            model=model,
            temperature=temperature,
        )
        self._compare_adapter = AsyncLLMAdapter(
            prompt_template=_COMPARE_PROMPT,
            model=model,
            temperature=temperature,
        )

    async def evaluate(
        self,
        question: str,
        response: str,
        expected: str = "",
    ) -> JudgeScore:
        """
        Score a single response.

        Args:
            question: The original question / task prompt.
            response: The agent response to evaluate.
            expected: Optional reference answer (improves accuracy scoring).

        Returns:
            JudgeScore with per-criterion scores and overall mean.
        """
        raw = await self._adapter.ainvoke({
            "question": question,
            "response": response,
            "expected": expected or "(none provided)",
        })

        parsed = self._parse_json(raw)
        criteria = {k: float(parsed.get(k, 5.0)) for k in self._CRITERIA}
        score = sum(criteria.values()) / len(criteria)
        reasoning = str(parsed.get("reasoning", ""))

        log.debug(f"JudgeEvaluator: score={score:.2f} model={self._model}")
        return JudgeScore(
            score=round(score, 2),
            reasoning=reasoning,
            criteria=criteria,
            question=question,
            response=response,
        )

    async def compare(
        self,
        question: str,
        response_a: str,
        response_b: str,
    ) -> dict[str, Any]:
        """
        Compare two responses head-to-head.

        Returns a dict with keys:
            winner   — "a", "b", or "tie"
            score_a  — float 0–10
            score_b  — float 0–10
            reasoning — one-sentence explanation
        """
        raw = await self._compare_adapter.ainvoke({
            "question": question,
            "response_a": response_a,
            "response_b": response_b,
        })

        parsed = self._parse_json(raw)
        return {
            "winner":    str(parsed.get("winner", "tie")).lower().strip(),
            "score_a":   float(parsed.get("score_a", 5.0)),
            "score_b":   float(parsed.get("score_b", 5.0)),
            "reasoning": str(parsed.get("reasoning", "")),
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_json(raw: str) -> dict:
        """
        Extract the first JSON object from an LLM response.

        Handles models that wrap JSON in markdown code fences.
        Falls back to a neutral (5.0) score on failure.
        """
        # Strip markdown fences
        text = re.sub(r"```(?:json)?", "", raw).strip()

        # Try full parse first
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Grab the first {...} block
        m = re.search(r"\{[^{}]+\}", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group())
            except json.JSONDecodeError:
                pass

        log.warning(f"JudgeEvaluator: failed to parse JSON from response: {raw[:200]}")
        return {}
