"""
LLM-as-judge evaluator for HEDIS gap closure recommendations.

9-criterion scoring (0–10 each):

  5 BASE performance dimensions (always evaluated, all agents):
  1. accuracy             — Is the answer factually correct?
  2. completeness         — Is required information included?
  3. relevance            — Does the answer address the question?
  4. conciseness          — Is the response appropriately brief?
  5. clarity              — Is it clear and easy to understand?

  4 CLINICAL extensions (HEDIS-specific):
  6. gap_identification_accuracy — right gap, right reason it's open
  7. action_appropriateness — right action for this specific member
  8. evidence_citation_quality — reasoning grounded in actual record
  9. safety_flag_coverage — exclusions and contraindications checked

Uses the existing JudgeEvaluator pattern from core/judge.py.
Outcome tracking (closed/not_closed) filled in by closure_tracker.py.
"""

from __future__ import annotations

import json
from typing import Any

from praktor.settings import create_log
from praktor.clinical.schemas import ClinicalJudgeScore
from praktor.clinical.evaluation.base_judge import BaseJudge

log = create_log()


_CLINICAL_EVAL_PROMPT = """You are a senior clinical quality evaluator at a Medicare Advantage health plan.
Score this HEDIS gap closure recommendation on 9 criteria (0–10 each).

RECOMMENDATION:
{recommendation}

MEMBER CONTEXT (de-identified):
{member_context}

ACTUAL OUTCOME (if known): {outcome}

--- BASE PERFORMANCE DIMENSIONS (5) ---

1. accuracy (0-10):
   Is the recommendation factually correct? Are clinical facts, measure IDs,
   PDC thresholds, and drug classes accurate?

2. completeness (0-10):
   Is all required information present? Action type, rationale, draft message,
   closure probability, and language all provided?

3. relevance (0-10):
   Does the recommendation directly address the member's open gaps?
   Is it specific to this member's situation, not generic advice?

4. conciseness (0-10):
   Is the rationale appropriately brief? Does the draft message stay under
   150 words and avoid unnecessary padding?

5. clarity (0-10):
   Is the rationale and draft message clear and easy to understand?
   Health-literacy appropriate language? Well-structured output?

--- CLINICAL EXTENSIONS (4) ---

6. gap_identification_accuracy (0-10):
   Was the right gap prioritized? Is the reason it's open correctly identified
   from the member record? Does the measure ID match the clinical evidence?

7. action_appropriateness (0-10):
   Is the recommended action right for THIS specific member?
   Consider: language match, health literacy level, PCP relationship,
   outreach history (don't repeat a failed channel), pharmacy proximity.

8. evidence_citation_quality (0-10):
   Is the rationale grounded in specific data from the member record?
   Generic advice = low score. "PDC=0.68, last fill 47 days ago,
   next fill due in 13 days" = high score.

9. safety_flag_coverage (0-10):
   Were all relevant exclusion criteria checked for this measure?
   Any contraindications or clinical risk flags surfaced?
   Missing an exclusion check = score 0-3.

Output ONLY valid JSON:
{{"accuracy": N, "completeness": N, "relevance": N, "conciseness": N, "clarity": N,
 "gap_identification_accuracy": N, "action_appropriateness": N,
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


class HEDISJudge(BaseJudge):
    """
    LLM-as-judge for clinical recommendation quality.

    9 criteria: 5 base performance dimensions + 4 HEDIS clinical extensions.
    temperature=0.0 for deterministic scoring.
    """

    _eval_prompt = _CLINICAL_EVAL_PROMPT
    _compare_prompt = _COMPARE_PROMPT
    _default_model = "llama3:8b"

    def __init__(self, model: str = "llama3:8b") -> None:
        super().__init__(model=model)

    def _parse_score(self, response: str, recommendation: Any) -> ClinicalJudgeScore:
        rec_id = str(id(recommendation))
        defaults = {
            "accuracy": 5.0, "completeness": 5.0, "relevance": 5.0,
            "conciseness": 5.0, "clarity": 5.0,
            "gap_identification_accuracy": 5.0,
            "action_appropriateness": 5.0,
            "evidence_citation_quality": 5.0,
            "safety_flag_coverage": 5.0,
            "reasoning": "",
        }
        data = self._parse_json(response, defaults)
        return ClinicalJudgeScore(
            recommendation_id=rec_id,
            accuracy=float(data.get("accuracy", 5.0)),
            completeness=float(data.get("completeness", 5.0)),
            relevance=float(data.get("relevance", 5.0)),
            conciseness=float(data.get("conciseness", 5.0)),
            clarity=float(data.get("clarity", 5.0)),
            gap_identification_accuracy=float(data.get("gap_identification_accuracy", 5.0)),
            action_appropriateness=float(data.get("action_appropriateness", 5.0)),
            evidence_citation_quality=float(data.get("evidence_citation_quality", 5.0)),
            safety_flag_coverage=float(data.get("safety_flag_coverage", 5.0)),
            reasoning=str(data.get("reasoning", "")),
        )

    def _neutral_score(self, reason: str) -> ClinicalJudgeScore:
        return ClinicalJudgeScore(
            recommendation_id="neutral",
            accuracy=5.0, completeness=5.0, relevance=5.0,
            conciseness=5.0, clarity=5.0,
            gap_identification_accuracy=5.0,
            action_appropriateness=5.0,
            evidence_citation_quality=5.0,
            safety_flag_coverage=5.0,
            reasoning=reason,
        )
