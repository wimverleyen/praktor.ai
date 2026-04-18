"""
HEDIS Gap Closure Agent — clinical reasoning with ReAct loop.

Combines gap prioritization and Next Best Action into a single agent.
The ReAct loop maps clinical reasoning steps:

  Thought: What gaps exist and which matters most?
  Action: gap_registry(member_id_hash)
  Observation: [ranked open gaps]
  Thought: What's the PDC status for the top-priority gap?
  Action: drug_adherence({"member_id_hash": ..., "drug_class": "statin"})
  Observation: [PDC score, threshold, gap status]
  Thought: Why hasn't the member refilled? Check barriers.
  Action: sdoh_lookup(member_id_hash)
  Observation: [language, health literacy, PCP info, pharmacy]
  Thought: Has outreach been tried?
  Action: outreach_history(member_id_hash)
  Observation: [prior attempts]
  Thought: Is there a valid exclusion?
  Action: measure_criteria(MAC)
  Observation: [exclusion criteria]
  Final Answer: [NextBestAction with priority, draft content, closure_probability]

Safety guardrails (eng review findings 1.4 + 2.4):
  - critical tool failure → ESCALATE
  - closure_probability < 0.4 → ESCALATE
  - max_steps without Final Answer → ESCALATE (not garbage output)
"""

from __future__ import annotations

import json
import re
from pydantic import BaseModel

from praktor.core.agent_definition import AgentDefinition, MemoryPolicy

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

class HEDISGapInput(BaseModel):
    agent_type: str = "hedis_gap"
    member_id_hash: str
    measurement_year: int = 2024
    session_id: str = ""
    history: str = ""


# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------

_GAP_AGENT_PROMPT = """You are a clinical care manager assistant at a Medicare Advantage health plan.
Your goal is to determine the single highest-impact action to close the most valuable open HEDIS
quality gap for member {member_id_hash_short} before the measurement year {measurement_year} ends
on December 31.

STARS WEIGHT GUIDANCE:
- 3x weight (triple-weighted): MAC (statin adherence), MAD (diabetes meds), MAP (hypertension RASA)
- 2x weight: CBP (blood pressure control)
- 1x weight: CDC-HbA1c, BCS (mammogram), COL (colorectal screening)
Always prioritize triple-weighted gaps first.

Available tools:
{{tool_descriptions}}

REASONING STEPS — follow this sequence:
1. gap_registry: Identify and rank all open gaps by priority score
2. drug_adherence or ehr_lookup: Get clinical data for the top-priority gap
3. claims_lookup: Check prescription fills or service history
4. sdoh_lookup: Understand language, health literacy, PCP, pharmacy access
5. outreach_history: Check prior contact attempts
6. measure_criteria: Verify exclusion criteria if any exclusion is suspected

SAFETY RULES:
- If ANY critical tool (gap_registry, drug_adherence, claims_lookup) returns an error,
  output: "CRITICAL_DATA_UNAVAILABLE — escalate to senior care manager"
- If closure_probability is below 0.40, recommend escalation to senior care manager
- ALWAYS check for exclusions before recommending action on preventive measures

OUTPUT FORMAT for Final Answer:
ACTION_TYPE: [pcp_warm_outreach | pharmacy_refill_reminder | scheduling_assist | telehealth_offer | member_direct_outreach | exclusion_flag | escalate]
PRIORITY_SCORE: [float 0-10]
MEASURE: [measure_id]
CLOSURE_PROBABILITY: [float 0.0-1.0]
RATIONALE: [1-3 sentences citing specific evidence from tool outputs]
DRAFT_MESSAGE: [ready-to-send outreach message, <150 words, health literacy appropriate]
LANGUAGE: [ISO 639-1 code]

{history}"""


# ---------------------------------------------------------------------------
# AgentDefinition
# ---------------------------------------------------------------------------

HEDISGapDefinition = AgentDefinition(
    name="hedis_gap",
    prompt_template=_GAP_AGENT_PROMPT,
    input_schema=HEDISGapInput,
    llm_model="llama3:8b",      # override with claude-sonnet-4-6 for production
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
    max_steps=7,
    memory_policy=MemoryPolicy.NONE,
)


# ---------------------------------------------------------------------------
# Output parser
# ---------------------------------------------------------------------------

def parse_next_best_action(final_answer: str, member_id_hash: str) -> dict:
    """
    Parse the structured Final Answer from the HEDIS gap agent into a dict
    suitable for the HITL review queue.
    """
    import time

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

    # Extract DRAFT_MESSAGE (may be multi-line)
    draft_match = re.search(
        r"^DRAFT_MESSAGE:\s*(.+?)(?=^[A-Z_]+:|$)", final_answer,
        re.MULTILINE | re.DOTALL
    )
    draft = draft_match.group(1).strip() if draft_match else final_answer

    action_type = extract("ACTION_TYPE", final_answer, "escalate")
    closure_prob = extract_float("CLOSURE_PROBABILITY", final_answer, 0.0)

    # Safety override — low confidence → escalate
    if closure_prob < 0.4 and action_type != "escalate":
        action_type = "escalate"

    return {
        "member_id_hash": member_id_hash,
        "action_type": action_type,
        "measure_id": extract("MEASURE", final_answer, "unknown"),
        "priority_score": extract_float("PRIORITY_SCORE", final_answer, 0.0),
        "closure_probability": closure_prob,
        "rationale": extract("RATIONALE", final_answer),
        "draft_content": draft,
        "language": extract("LANGUAGE", final_answer, "en"),
        "raw_response": final_answer,
        "timestamp": time.time(),
    }
