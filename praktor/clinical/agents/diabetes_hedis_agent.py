"""
Diabetes HEDIS Gap Closure Agent — clinical reasoning for diabetes quality measures.

Specialized ReAct agent for the full MY 2026 diabetes measure set:
  GSD  — Glycemic Status Assessment         (triple-weighted, INVERSE)
  KED  — Kidney Health Evaluation           (eGFR + uACR BOTH required)
  EED-E — Eye Exam for Patients w/ Diabetes (ECDS)
  SPD-E — Statin Therapy for Patients w/ Diabetes (ECDS-only, MY 2026)
  BPD-E — Blood Pressure Control for Patients w/ Diabetes (ECDS)

Core clinical reasoning capabilities:
  - Therapeutic inertia detection: member on same regimen >12 months with A1c not at goal
  - Treatment escalation ladder: metformin → GLP-1 RA → SGLT2i → basal insulin → basal-bolus
  - Evidence anchors: CREDENCE, EMPA-KIDNEY, DAPA-CKD, UKPDS, CARDS, ACCORD-BP
  - Gap-stacking: checks all 5 measures before recommending single action
  - GSD triple-weighted inverse-scoring prioritization

Design: Approach B (dedicated diabetes_hedis AgentDefinition)
Approved: 2026-04-16
"""

from __future__ import annotations

import re
import time

from pydantic import BaseModel, Field

from praktor.core.agent_definition import AgentDefinition, MemoryPolicy
from praktor.aigov.bundle import healthcare_bundle
from praktor.clinical.schemas import hash_member_id

_DEMO_MEMBER_HASH = hash_member_id("D001")

# Register all clinical tools at import time
import praktor.clinical.tools.claims_lookup       # noqa: F401
import praktor.clinical.tools.ehr_lookup          # noqa: F401
import praktor.clinical.tools.gap_registry        # noqa: F401
import praktor.clinical.tools.outreach_history    # noqa: F401
import praktor.clinical.tools.sdoh_lookup         # noqa: F401
import praktor.clinical.tools.measure_criteria    # noqa: F401
import praktor.clinical.tools.drug_adherence      # noqa: F401


# ---------------------------------------------------------------------------
# Input schema
# ---------------------------------------------------------------------------

class DiabetesHEDISInput(BaseModel):
    agent_type: str = "diabetes_hedis"
    member_id_hash: str = Field(default_factory=lambda: _DEMO_MEMBER_HASH, description="Demo: D001")
    measurement_year: int = 2026
    session_id: str = ""
    history: str = ""


# ---------------------------------------------------------------------------
# Specialist prompt
# ---------------------------------------------------------------------------

_DIABETES_AGENT_PROMPT = """You are a clinical care manager and diabetes specialist at a Medicare Advantage health plan.
Your expertise: HEDIS MY 2026 diabetes quality measures, therapeutic inertia, treatment escalation, and gap-stacking.

MEMBER: {member_id_hash_short} | Measurement Year: {measurement_year}

━━━ DIABETES MEASURE SET (MY 2026) ━━━
GSD  — Glycemic Status Assessment     [3x STARS, INVERSE-SCORED]
       A1c or GMI >9.0% = POOR CONTROL = Star Rating PENALTY (triple-weighted)
       Untested members auto-fail → one lab order is the cheapest closure.
KED  — Kidney Health Evaluation       [1x STARS]
       REQUIRES eGFR AND uACR — eGFR-only FAILS. uACR-positive → consider SGLT2i.
EED-E — Eye Exam                      [1x STARS]
        Retinal/dilated exam by eye care professional. Negative exam in prior year satisfies.
SPD-E — Statin Therapy (ECDS-only)    [1x STARS]
        Rate (a) statin dispensing; Rate (b) PDC >= 0.80. All diabetics 40–75 w/o ASCVD.
BPD-E — Blood Pressure Control        [1x STARS]
        Most recent BP < 140/90. RPM/home BP now measure-compliant via ECDS MY 2026.

━━━ STARS PRIORITY ORDER ━━━
1. GSD (3x, inverse — A1c >9.0% penalizes Stars 3x; untested is cheapest and highest leverage)
2. KED (1x but highest clinical consequence — CKD progression, SGLT2i window)
3. SPD-E (1x — statin start = 90-day fill, mail-order → PDC improvement)
4. EED-E (1x — referral leakage most common failure; teleophthalmology accelerates closure)
5. BPD-E (1x — data-capture problem; RPM ingestion via ECDS)

━━━ GAP-STACKING RULE ━━━
ALWAYS check ALL FIVE measures before recommending a single action.
One PCP visit can close: GSD (standing lab order) + KED (add uACR to same draw) + EED-E (referral).
Stacking 3 closures from one touchpoint multiplies Stars ROI.
Output: recommend the action that closes the most gaps, not just the top-priority gap.

━━━ THERAPEUTIC INERTIA DETECTION ━━━
Flag inertia when: member is on the same diabetes regimen for >12 months AND A1c is NOT at goal (<8.0%).
Inertia pattern: "same DX + same Rx class for 12+ months with A1c consistently elevated"
When inertia detected, escalate the clinical recommendation:

TREATMENT ESCALATION LADDER (ADA 2024 Standards):
Step 1: Metformin monotherapy (or equivalent first-line)
Step 2: Add GLP-1 RA — if BMI ≥27 OR cardiovascular benefit needed (Ozempic, Trulicity, Victoza)
Step 3: Add SGLT2i — if CKD (eGFR 20–60 + uACR >200) OR HFrEF (CREDENCE, EMPA-KIDNEY, DAPA-CKD)
Step 4: Basal insulin — if A1c >10% on dual therapy (titrate to fasting glucose 80–130 mg/dL)
Step 5: Basal-bolus insulin — if A1c >9.0% on optimized basal (consider endocrinology referral)

━━━ EVIDENCE ANCHORS (cite when relevant) ━━━
UKPDS: Intensive glycemic control in T2D reduces microvascular complications ~25%; legacy effect persists.
ACCORD: A1c <6.0% increased mortality — HEDIS A1c >9.0% inverse rate reflects this floor.
CARDS: Atorvastatin 10 mg reduced first CV event 37% in T2D without prior CVD → SPD-E rationale.
HPS: Statin benefit regardless of baseline LDL in high-risk patients → SPD-E rationale.
CREDENCE: Canagliflozin reduced renal composite 30% in T2D + CKD (eGFR 30–90).
DAPA-CKD: Dapagliflozin reduced CKD progression 39% — efficacy even without T2D.
EMPA-KIDNEY: Empagliflozin reduced kidney disease progression/CV death 28%.
ACCORD-BP: BP <140/90 is the evidence-based floor for HEDIS BPD-E compliance.

Available tools:
{{tool_descriptions}}

━━━ REASONING SEQUENCE ━━━
1. gap_registry      → Identify ALL open diabetes gaps (GSD, KED, EED-E, SPD-E, BPD-E)
2. ehr_lookup        → Get latest A1c/GMI, eGFR, uACR, BP readings; detect inertia pattern
3. drug_adherence    → PDC for statins (SPD-E) and any oral hypoglycemics (MAD co-morbid)
4. claims_lookup     → Pharmacy fills history — identify current regimen + duration
5. sdoh_lookup       → Language, health literacy, PCP contact, pharmacy access
6. outreach_history  → Prior contact attempts and responses
7. measure_criteria  → Verify specific exclusion criteria for any gap you plan to close

━━━ SAFETY RULES ━━━
- If gap_registry or ehr_lookup returns an error → ESCALATE immediately
- closure_probability < 0.40 → ESCALATE
- A1c >9.0% with no PCP contact in >180 days → ESCALATE to care manager
- Therapeutic inertia + A1c >9.0% → recommend clinical escalation in rationale
- NEVER recommend insulin initiation without PCP/endocrinologist involvement — flag for escalate
- ALWAYS check exclusions (hospice, ESRD, frailty) before recommending any action

━━━ OUTPUT FORMAT ━━━
ACTION_TYPE: [pcp_warm_outreach | pharmacy_refill_reminder | scheduling_assist | telehealth_offer | member_direct_outreach | exclusion_flag | escalate]
PRIORITY_SCORE: [float 0-10]
MEASURES_ADDRESSED: [comma-separated measure IDs closed by this action]
GAPS_STACKED: [integer count of gaps this single action closes]
CLOSURE_PROBABILITY: [float 0.0-1.0]
INERTIA_DETECTED: [yes | no]
ESCALATION_LADDER_STEP: [1-5 | N/A]
RATIONALE: [2-4 sentences: name the gaps, cite clinical evidence, explain the gap-stacking logic]
DRAFT_MESSAGE: [ready-to-send outreach message, <150 words, health-literacy appropriate, member language]
LANGUAGE: [ISO 639-1 code]

{history}"""


# ---------------------------------------------------------------------------
# AgentDefinition
# ---------------------------------------------------------------------------

DiabetesHEDISDefinition = AgentDefinition(
    name="diabetes_hedis",
    prompt_template=_DIABETES_AGENT_PROMPT,
    input_schema=DiabetesHEDISInput,
    temperature=0.0,
    tools=[
        "gap_registry",
        "drug_adherence",
        "claims_lookup",
        "ehr_lookup",
        "sdoh_lookup",
        "outreach_history",
        "measure_criteria",
    ],
    max_steps=8,
    memory_policy=MemoryPolicy.NONE,
    obligation_bundle=healthcare_bundle(),
)


# ---------------------------------------------------------------------------
# Output parser
# ---------------------------------------------------------------------------

def parse_diabetes_next_best_action(final_answer: str, member_id_hash: str) -> dict:
    """
    Parse the structured Final Answer from the diabetes HEDIS agent into a dict.
    Extends parse_next_best_action with diabetes-specific fields.
    """
    def extract(field: str, text: str, default: str = "") -> str:
        pattern = rf"^{field}:\s*(.+)$"
        m = re.search(pattern, text, re.MULTILINE | re.IGNORECASE)
        return m.group(1).strip() if m else default

    def extract_float(field: str, text: str, default: float = 0.0) -> float:
        val = extract(field, text, str(default))
        try:
            return float(val)
        except ValueError:
            return default

    def extract_int(field: str, text: str, default: int = 0) -> int:
        val = extract(field, text, str(default))
        try:
            return int(val)
        except ValueError:
            return default

    # Extract DRAFT_MESSAGE (may be multi-line)
    draft_match = re.search(
        r"^DRAFT_MESSAGE:\s*(.+?)(?=^[A-Z_]+:|$)", final_answer,
        re.MULTILINE | re.DOTALL
    )
    draft = draft_match.group(1).strip() if draft_match else ""

    action_type = extract("ACTION_TYPE", final_answer, "escalate")
    closure_prob = extract_float("CLOSURE_PROBABILITY", final_answer, 0.0)

    # Safety override — low confidence → escalate
    if closure_prob < 0.4 and action_type != "escalate":
        action_type = "escalate"

    # Parse MEASURES_ADDRESSED into a list
    measures_raw = extract("MEASURES_ADDRESSED", final_answer, "")
    measures_addressed = [m.strip() for m in measures_raw.split(",") if m.strip()]

    inertia_raw = extract("INERTIA_DETECTED", final_answer, "no").lower()
    inertia_detected = inertia_raw in ("yes", "true", "1")

    escalation_step_raw = extract("ESCALATION_LADDER_STEP", final_answer, "N/A")
    try:
        escalation_step = int(escalation_step_raw)
    except ValueError:
        escalation_step = None

    return {
        "member_id_hash": member_id_hash,
        "agent_type": "diabetes_hedis",
        "action_type": action_type,
        "measure_id": measures_addressed[0] if measures_addressed else extract("PRIORITY_MEASURE", final_answer, "GSD"),
        "measures_addressed": measures_addressed,
        "gaps_stacked": extract_int("GAPS_STACKED", final_answer, len(measures_addressed)),
        "priority_score": extract_float("PRIORITY_SCORE", final_answer, 0.0),
        "closure_probability": closure_prob,
        "inertia_detected": inertia_detected,
        "escalation_ladder_step": escalation_step,
        "rationale": extract("RATIONALE", final_answer),
        "draft_content": draft,
        "language": extract("LANGUAGE", final_answer, "en"),
        "raw_response": final_answer,
        "timestamp": time.time(),
    }
