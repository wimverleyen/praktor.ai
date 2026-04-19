"""
LLM-as-judge evaluator for diabetes HEDIS gap closure recommendations.

10-criterion scoring (0–10 each):

  5 BASE performance dimensions (always evaluated, all agents):
  1. accuracy             — Is the answer factually correct?
  2. completeness         — Is required information included?
  3. relevance            — Does the answer address the question?
  4. conciseness          — Is the response appropriately brief?
  5. clarity              — Is it clear and easy to understand?

  5 DIABETES extensions:
  6. inertia_detection_accuracy     — Therapeutic inertia correctly flagged/unflagged
  7. escalation_ladder_correctness  — Right ADA 2024 escalation step recommended
  8. gap_stacking_completeness      — All closable gaps identified in one action
  9. evidence_anchor_quality        — Trial evidence cited (CREDENCE, UKPDS, CARDS…)
 10. safety_exclusion_coverage      — ESRD, hospice, ASCVD exclusions checked

MY 2026 diabetes measures: GSD, KED, EED-E, SPD-E, BPD-E.
"""

from __future__ import annotations

import json
from typing import Any

from praktor.settings import create_log
from praktor.clinical.evaluation.base_judge import BaseJudge
from praktor.clinical.schemas import DiabetesJudgeScore  # noqa: F401 — re-export for callers

log = create_log()


# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------

_DIABETES_EVAL_PROMPT = """You are a clinical AI evaluator specializing in diabetes care quality at a
Medicare Advantage health plan. Score this diabetes HEDIS gap closure recommendation on 10 criteria.

RECOMMENDATION:
{recommendation}

MEMBER CONTEXT (de-identified):
{member_context}

ACTUAL OUTCOME (if known): {outcome}

MY 2026 DIABETES MEASURES FOR REFERENCE:
- GSD: Glycemic Status Assessment — A1c or GMI result; missing = poor control (3x STARS, INVERSE)
- KED: Kidney Health Evaluation — BOTH eGFR AND uACR required; eGFR-only FAILS
- EED-E: Eye Exam — retinal exam by optometrist/ophthalmologist in MY
- SPD-E: Statin Therapy (ECDS-only) — PDC >= 0.80; applies to diabetics 40-75 w/o ASCVD
- BPD-E: Blood Pressure Control — most recent BP < 140/90

ESCALATION LADDER (ADA 2024):
Step 1: Metformin. Step 2: Add GLP-1 RA (BMI>=27 or CV risk).
Step 3: Add SGLT2i (CKD eGFR 20-60 or HFrEF — CREDENCE, EMPA-KIDNEY, DAPA-CKD).
Step 4: Basal insulin (A1c>10%). Step 5: Basal-bolus insulin (A1c>9% on optimized basal).

--- BASE PERFORMANCE DIMENSIONS (5) ---

1. accuracy (0-10):
   Are clinical facts correct? Measure IDs, A1c thresholds (>8.0% = poor control, >9.0% = inverse),
   eGFR staging, PDC thresholds accurate?

2. completeness (0-10):
   Are all required output fields present? Action type, measures addressed, gaps stacked,
   rationale, draft message, closure probability, language all provided?

3. relevance (0-10):
   Does the recommendation directly address this member's open diabetes gaps?
   Specific to this member's A1c, kidney status, medication history?

4. conciseness (0-10):
   Is the rationale concise (2-4 sentences)? Draft message under 150 words?
   No unnecessary padding or generic disclaimers?

5. clarity (0-10):
   Is the rationale clear to a non-clinician care coordinator?
   Is the draft message in plain, health-literacy appropriate language?
   Well-structured output?

--- DIABETES EXTENSIONS (5) ---

6. inertia_detection_accuracy (0-10):
   If the member has been on the same regimen >12 months with A1c not at goal,
   was therapeutic inertia CORRECTLY flagged?
   If inertia is absent, was it CORRECTLY NOT flagged (false positives also penalized)?
   Score 0 for missed inertia when clearly present; score 0 for false flagging.

7. escalation_ladder_correctness (0-10):
   If inertia was detected, is the recommended escalation step correct per ADA 2024?
   eGFR 20-60 or HFrEF → SGLT2i (Step 3), not GLP-1.
   BMI>=27 with no CKD/HFrEF → GLP-1 (Step 2), not SGLT2i.
   A1c>10% on dual therapy → basal insulin (Step 4).
   Score N/A (10) if no escalation needed.

8. gap_stacking_completeness (0-10):
   Were ALL closable diabetes gaps identified for this member before recommending a single action?
   Should GSD+KED be stacked (one blood draw)? Should SPD-E be included (statin at same visit)?
   Missed stacking when stacking was possible = lower score.

9. evidence_anchor_quality (0-10):
   Are the right trials cited for the recommended action?
   SGLT2i for CKD → CREDENCE/EMPA-KIDNEY/DAPA-CKD (required).
   Statin for T2D → CARDS/HPS.
   A1c control → UKPDS.
   Generic or missing citations = score 0-4. Wrong trial for the indication = score 0-2.

10. safety_exclusion_coverage (0-10):
    Were relevant exclusions checked?
    GSD: hospice, frailty, gestational/steroid-induced diabetes, A1c interference (sickle cell).
    KED: ESRD, dialysis, kidney transplant.
    SPD-E: ASCVD (falls to SPC-E), myopathy, liver disease.
    Missing an exclusion check for the recommended action = score 0-3.

Output ONLY valid JSON (no prose, no markdown):
{{"accuracy": N, "completeness": N, "relevance": N, "conciseness": N, "clarity": N,
  "inertia_detection_accuracy": N, "escalation_ladder_correctness": N,
  "gap_stacking_completeness": N, "evidence_anchor_quality": N,
  "safety_exclusion_coverage": N,
  "reasoning": "one sentence explanation"}}"""


_COMPARE_PROMPT = """You are a clinical AI evaluator. Compare two diabetes HEDIS recommendations.

MEMBER CONTEXT: {member_context}

RECOMMENDATION A:
{recommendation_a}

RECOMMENDATION B:
{recommendation_b}

Which recommendation would more likely result in the highest Stars improvement for this member?
Consider: correct gap identification, gap-stacking, therapeutic inertia handling, SGLT2i appropriateness.
Output ONLY valid JSON:
{{"winner": "A" or "B", "confidence": 0.0-1.0, "reasoning": "one sentence"}}"""


# ---------------------------------------------------------------------------
# Judge
# ---------------------------------------------------------------------------

class DiabetesHEDISJudge(BaseJudge):
    """
    LLM-as-judge for diabetes HEDIS recommendation quality.

    10 criteria: 5 base performance dimensions + 5 diabetes-specific.
    temperature=0.0 for deterministic scoring.
    """

    _eval_prompt = _DIABETES_EVAL_PROMPT
    _compare_prompt = _COMPARE_PROMPT
    def __init__(self, model: str | None = None) -> None:
        super().__init__(model=model)

    def _parse_score(self, response: str, recommendation: Any) -> DiabetesJudgeScore:
        rec_id = str(id(recommendation))
        defaults = {
            "accuracy": 5.0, "completeness": 5.0, "relevance": 5.0,
            "conciseness": 5.0, "clarity": 5.0,
            "inertia_detection_accuracy": 5.0,
            "escalation_ladder_correctness": 5.0,
            "gap_stacking_completeness": 5.0,
            "evidence_anchor_quality": 5.0,
            "safety_exclusion_coverage": 5.0,
            "reasoning": "",
        }
        data = self._parse_json(response, defaults)
        return DiabetesJudgeScore(
            recommendation_id=rec_id,
            accuracy=float(data.get("accuracy", 5.0)),
            completeness=float(data.get("completeness", 5.0)),
            relevance=float(data.get("relevance", 5.0)),
            conciseness=float(data.get("conciseness", 5.0)),
            clarity=float(data.get("clarity", 5.0)),
            inertia_detection_accuracy=float(data.get("inertia_detection_accuracy", 5.0)),
            escalation_ladder_correctness=float(data.get("escalation_ladder_correctness", 5.0)),
            gap_stacking_completeness=float(data.get("gap_stacking_completeness", 5.0)),
            evidence_anchor_quality=float(data.get("evidence_anchor_quality", 5.0)),
            safety_exclusion_coverage=float(data.get("safety_exclusion_coverage", 5.0)),
            reasoning=str(data.get("reasoning", "")),
        )

    def _neutral_score(self, reason: str) -> DiabetesJudgeScore:
        return DiabetesJudgeScore(
            recommendation_id="neutral",
            accuracy=5.0, completeness=5.0, relevance=5.0,
            conciseness=5.0, clarity=5.0,
            inertia_detection_accuracy=5.0,
            escalation_ladder_correctness=5.0,
            gap_stacking_completeness=5.0,
            evidence_anchor_quality=5.0,
            safety_exclusion_coverage=5.0,
            reasoning=reason,
        )
