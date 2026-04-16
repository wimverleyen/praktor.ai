"""
LLM-as-judge evaluator for HEDIS gap closure recommendations.

4-criterion scoring (0–10 each):
  1. gap_identification_accuracy — right gap, right reason it's open
  2. action_appropriateness — right action for this specific member
  3. evidence_citation_quality — reasoning grounded in actual record
  4. safety_flag_coverage — exclusions and contraindications checked

Uses the existing JudgeEvaluator pattern from core/judge.py.
Outcome tracking (closed/not_closed) filled in by closure_tracker.py.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from settings import create_log
from clinical.schemas import ClinicalJudgeScore

log = create_log()


_CLINICAL_EVAL_PROMPT = """You are a senior clinical quality evaluator at a Medicare Advantage health plan.
Score this HEDIS gap closure recommendation on four criteria (0–10 each).

RECOMMENDATION:
{recommendation}

MEMBER CONTEXT (de-identified):
{member_context}

ACTUAL OUTCOME (if known): {outcome}

Score each criterion:

1. gap_identification_accuracy (0-10):
   Was the right gap prioritized? Is the reason it's open correctly identified
   from the member record? Does the measure ID match the clinical evidence?

2. action_appropriateness (0-10):
   Is the recommended action right for THIS specific member?
   Consider: language match, health literacy level, PCP relationship,
   outreach history (don't repeat a failed channel), pharmacy proximity.

3. evidence_citation_quality (0-10):
   Is the rationale grounded in specific data from the member record?
   Generic advice = low score. "PDC=0.68, last fill 47 days ago,
   next fill due in 13 days" = high score.

4. safety_flag_coverage (0-10):
   Were all relevant exclusion criteria checked for this measure?
   Any contraindications or clinical risk flags surfaced?
   Missing an exclusion check = score 0-3.

Output ONLY valid JSON:
{{"gap_identification_accuracy": N, "action_appropriateness": N,
 "evidence_citation_quality": N, "safety_flag_coverage": N,
 "reasoning": "one sentence explanation of the scores"}}"""


_COMPARE_PROMPT = """You are a clinical quality expert. Compare two HEDIS gap closure recommendations
and determine which is better for the member.

MEMBER CONTEXT: {member_context}

RECOMMENDATION A:
{recommendation_a}

RECOMMENDATION B:
{recommendation_b}

Which recommendation would more likely result in the HEDIS gap being closed?
Output ONLY valid JSON:
{{"winner": "A" or "B", "confidence": 0.0-1.0, "reasoning": "one sentence"}}"""


class HEDISJudge:
    """
    LLM-as-judge for clinical recommendation quality.

    Uses temperature=0.0 for deterministic scoring.
    Wraps the existing AsyncLLMAdapter pattern.
    """

    def __init__(self, model: str = "qwen2.5") -> None:
        self._model = model
        self._eval_adapter = None
        self._compare_adapter = None
        self._init_adapters()

    def _init_adapters(self) -> None:
        try:
            from LLM.llm_interface import AsyncLLMAdapter
            self._eval_adapter = AsyncLLMAdapter(
                prompt_template=_CLINICAL_EVAL_PROMPT,
                model=self._model,
                temperature=0.0,
            )
            self._compare_adapter = AsyncLLMAdapter(
                prompt_template=_COMPARE_PROMPT,
                model=self._model,
                temperature=0.0,
            )
        except Exception as e:
            log.error(f"HEDISJudge: adapter init failed: {e}")

    async def evaluate(
        self,
        recommendation: str | dict,
        member_context: str,
        outcome: str | None = None,
    ) -> ClinicalJudgeScore:
        """Score a recommendation. Returns ClinicalJudgeScore."""
        if self._eval_adapter is None:
            return self._neutral_score("adapter_unavailable")

        rec_text = json.dumps(recommendation, indent=2) \
            if isinstance(recommendation, dict) else str(recommendation)

        try:
            response = await self._eval_adapter.ainvoke({
                "recommendation": rec_text,
                "member_context": member_context,
                "outcome": outcome or "pending",
            })
            return self._parse_score(response, recommendation)
        except Exception as e:
            log.error(f"HEDISJudge.evaluate failed: {e}")
            return self._neutral_score(str(e))

    async def compare(
        self,
        recommendation_a: str,
        recommendation_b: str,
        member_context: str,
    ) -> dict:
        """Head-to-head comparison. Returns {winner, confidence, reasoning}."""
        if self._compare_adapter is None:
            return {"winner": "A", "confidence": 0.5, "reasoning": "adapter unavailable"}

        try:
            response = await self._compare_adapter.ainvoke({
                "recommendation_a": recommendation_a,
                "recommendation_b": recommendation_b,
                "member_context": member_context,
            })
            return self._parse_json(response, {"winner": "A", "confidence": 0.5, "reasoning": ""})
        except Exception as e:
            log.error(f"HEDISJudge.compare failed: {e}")
            return {"winner": "A", "confidence": 0.5, "reasoning": str(e)}

    def _parse_score(self, response: str, recommendation: Any) -> ClinicalJudgeScore:
        rec_id = str(id(recommendation))
        defaults = {
            "gap_identification_accuracy": 5.0,
            "action_appropriateness": 5.0,
            "evidence_citation_quality": 5.0,
            "safety_flag_coverage": 5.0,
            "reasoning": "",
        }
        data = self._parse_json(response, defaults)
        return ClinicalJudgeScore(
            recommendation_id=rec_id,
            gap_identification_accuracy=float(data.get("gap_identification_accuracy", 5.0)),
            action_appropriateness=float(data.get("action_appropriateness", 5.0)),
            evidence_citation_quality=float(data.get("evidence_citation_quality", 5.0)),
            safety_flag_coverage=float(data.get("safety_flag_coverage", 5.0)),
            reasoning=str(data.get("reasoning", "")),
        )

    def _parse_json(self, text: str, default: dict) -> dict:
        # Strip markdown fences
        text = re.sub(r"```(?:json)?", "", text).strip().rstrip("`").strip()
        # Find first JSON object
        m = re.search(r"\{.+\}", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group())
            except json.JSONDecodeError:
                pass
        return default

    def _neutral_score(self, reason: str) -> ClinicalJudgeScore:
        return ClinicalJudgeScore(
            recommendation_id="neutral",
            gap_identification_accuracy=5.0,
            action_appropriateness=5.0,
            evidence_citation_quality=5.0,
            safety_flag_coverage=5.0,
            reasoning=reason,
        )
