"""
Diabetes HEDIS Gap Closure Agent — demo script.

Three engineered members for the VP AI Engineering → CIO demo:
  D001 Maria Lopez     — untested GSD (cheapest gap to close, Spanish, high SDOH)
  D002 James Chen      — A1c 8.7% trending up, therapeutic inertia, KED gap (SGLT2i story)
  D003 Patricia Williams — GSD+KED+SPD-E+EED-E all open (gap-stacking economics)

Usage:
    # Dry run (no Ollama needed)
    PYTHONPATH=praktor python scripts/demo_diabetes_agent.py --dry-run

    # Real LLM
    PYTHONPATH=praktor python scripts/demo_diabetes_agent.py --model llama3:8b

    # Single member
    PYTHONPATH=praktor python scripts/demo_diabetes_agent.py --dry-run --member 0
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "praktor"))
sys.path.insert(0, str(Path(__file__).parent.parent))

import os as _os
if not _os.getenv("OTLP_ENDPOINT"):
    _os.environ.setdefault("OTEL_SDK_DISABLED", "true")

from scripts.init_diabetes_demo import seed_diabetes_demo, DIABETES_DEMO_MEMBERS, YEAR
from clinical.schemas import hash_member_id
from clinical.agents.diabetes_hedis_agent import DiabetesHEDISDefinition, parse_diabetes_next_best_action

# ---------------------------------------------------------------------------
# ANSI colours
# ---------------------------------------------------------------------------
_RESET  = "\033[0m"
_BOLD   = "\033[1m"
_CYAN   = "\033[96m"
_GREEN  = "\033[92m"
_YELLOW = "\033[93m"
_RED    = "\033[91m"
_DIM    = "\033[2m"
_MAGENTA = "\033[95m"

STARS_COLOR = {3.0: _GREEN, 2.0: _YELLOW, 1.0: _DIM}

STORY_LABELS = {
    "untested_gsd_cheapest_close": f"{_CYAN}cheapest close{_RESET}",
    "therapeutic_inertia_sglt2i":  f"{_MAGENTA}therapeutic inertia{_RESET}",
    "gap_stacking_four_measures":  f"{_GREEN}gap-stacking{_RESET}",
}


def _stars_label(w: float) -> str:
    color = STARS_COLOR.get(w, _RESET)
    return f"{color}{w:.0f}x STARS{_RESET}"


def _header(text: str) -> None:
    print(f"\n{_BOLD}{_CYAN}{'═' * 72}{_RESET}")
    print(f"{_BOLD}{_CYAN}  {text}{_RESET}")
    print(f"{_BOLD}{_CYAN}{'═' * 72}{_RESET}")


def _section(text: str) -> None:
    print(f"\n{_BOLD}▸ {text}{_RESET}")


def _print_action(action: dict) -> None:
    prob = action.get("closure_probability", 0)
    color = _GREEN if prob >= 0.6 else _YELLOW if prob >= 0.4 else _RED

    measures = action.get("measures_addressed", [action.get("measure_id", "?")])
    gaps_stacked = action.get("gaps_stacked", len(measures))

    print(f"\n  {_BOLD}Action:{_RESET}              {action.get('action_type', 'unknown')}")
    print(f"  {_BOLD}Primary measure:{_RESET}     {action.get('measure_id', '?')}")

    if gaps_stacked > 1:
        print(f"  {_BOLD}Gaps stacked:{_RESET}        {_GREEN}{gaps_stacked} gaps in one action{_RESET}  "
              f"({', '.join(measures)})")
    else:
        print(f"  {_BOLD}Measures addressed:{_RESET}  {', '.join(measures)}")

    print(f"  {_BOLD}Priority score:{_RESET}      {action.get('priority_score', 0):.2f}")
    print(f"  {_BOLD}Closure probability:{_RESET} {color}{prob:.0%}{_RESET}")
    print(f"  {_BOLD}Language:{_RESET}            {action.get('language', 'en')}")

    if action.get("inertia_detected"):
        step = action.get("escalation_ladder_step")
        step_str = f"  → escalation ladder step {step}" if step else ""
        print(f"  {_BOLD}Therapeutic inertia:{_RESET} {_MAGENTA}DETECTED{step_str}{_RESET}")

    print(f"\n  {_BOLD}Rationale:{_RESET}")
    print(f"  {action.get('rationale', '—')}")
    print(f"\n  {_BOLD}Draft message ({action.get('language', 'en')}):{_RESET}")
    for line in action.get("draft_content", "").split("\n")[:8]:
        print(f"  {_DIM}{line}{_RESET}")


def _patch_dry_run(agent, member_hash: str, member_data: dict) -> None:
    """Patch agent adapters for dry-run — no Ollama required."""
    gaps = member_data["gaps"]
    story = member_data.get("demo_story", "")

    # Build gap list string
    gap_summary = "; ".join(
        f"{g['measure_id']} ({g['stars_weight']:.0f}x STARS)"
        for g in gaps
    )
    top_gap = max(gaps, key=lambda g: g["stars_weight"])

    # Story-specific dry-run responses
    if story == "untested_gsd_cheapest_close":
        dry_run_responses = [
            f"""Thought: Let me check all open diabetes gaps for this member.
Action: gap_registry
Action Input: {member_hash}
Observation: """,
            f"""Thought: GSD is open — member has no A1c in MY 2026. This is an auto-fail for the triple-weighted inverse measure. Let me check labs.
Action: ehr_lookup
Action Input: {{"member_id_hash": "{member_hash}", "data_type": "labs"}}
Observation: """,
            f"""Thought: Last A1c was in 2025 — does not satisfy MY 2026 requirement. Let me check SDOH and language.
Action: sdoh_lookup
Action Input: {member_hash}
Observation: """,
            f"""Thought: Spanish-speaking member, high SDOH. PCP (Dr. Morales) is Spanish-speaking. GSD gap can be closed with one standing lab order at next PCP visit. No inertia — only metformin, A1c was 7.4% in 2025 (controlled). Cheapest closure: warm outreach to Dr. Morales for standing A1c order.
Final Answer:
ACTION_TYPE: pcp_warm_outreach
PRIORITY_SCORE: 9.0
MEASURES_ADDRESSED: GSD
GAPS_STACKED: 1
CLOSURE_PROBABILITY: 0.85
INERTIA_DETECTED: no
ESCALATION_LADDER_STEP: N/A
RATIONALE: Member has no A1c in MY 2026 — GSD auto-fails (triple-weighted, inverse-scored). Last A1c 7.4% in 2025 suggests she is controlled; a standing lab order at next visit closes the highest-Stars gap at near-zero cost. PCP Dr. Morales speaks Spanish — warm outreach in member's language maximizes response. One lab order = 3x Stars leverage.
DRAFT_MESSAGE: Hola, estamos llamando de su plan de salud. Su médico, el Dr. Morales, puede pedir un análisis de hemoglobina A1c en su próxima visita para cumplir con sus metas de salud anuales. Por favor llame al consultorio para programar su visita. ¡Es un análisis sencillo y muy importante para su salud!
LANGUAGE: es""",
        ]

    elif story == "therapeutic_inertia_sglt2i":
        dry_run_responses = [
            f"""Thought: Let me check all open diabetes gaps.
Action: gap_registry
Action Input: {member_hash}
Observation: """,
            f"""Thought: GSD open — A1c 8.7% in MY 2026 (poor control, triple-weighted). KED open — need to check if both eGFR and uACR are present.
Action: ehr_lookup
Action Input: {{"member_id_hash": "{member_hash}", "data_type": "labs"}}
Observation: """,
            f"""Thought: eGFR is 52 (CKD stage 3a), but NO uACR — KED fails. A1c 8.7% trending up from 8.1% → 8.4% → 8.7% over 18 months. Let me check the pharmacy fill history.
Action: claims_lookup
Action Input: {{"member_id_hash": "{member_hash}", "claim_type": "rx"}}
Observation: """,
            f"""Thought: Member has been on metformin + glipizide for 18+ months with A1c rising. This is a classic therapeutic inertia pattern. eGFR 52 + missing uACR → KED gap + potential SGLT2i indication (CREDENCE: CKD + T2D). Let me verify KED exclusion criteria.
Action: measure_criteria
Action Input: KED
Observation: """,
            f"""Thought: No ESRD exclusion — dialysis or transplant absent. uACR missing is the closure gap. If uACR >30 mg/g (microalbuminuria), empagliflozin or dapagliflozin should be initiated (EMPA-KIDNEY, DAPA-CKD). Recommend PCP warm outreach: add uACR to next lab draw + medication review for GLP-1 or SGLT2i escalation given therapeutic inertia.
Final Answer:
ACTION_TYPE: pcp_warm_outreach
PRIORITY_SCORE: 8.7
MEASURES_ADDRESSED: GSD, KED
GAPS_STACKED: 2
CLOSURE_PROBABILITY: 0.78
INERTIA_DETECTED: yes
ESCALATION_LADDER_STEP: 3
RATIONALE: Therapeutic inertia detected — member on metformin+glipizide for 18+ months with A1c rising from 8.1% to 8.7% (UKPDS: early intensification reduces microvascular complications). GSD is open (A1c >8.0%, triple-weighted inverse). KED fails — eGFR 52 present but uACR absent; adding uACR to the next lab draw closes the KED gap and screens for SGLT2i eligibility (CREDENCE/EMPA-KIDNEY: 28-30% renal composite reduction in CKD + T2D). Escalation ladder step 3 (SGLT2i) is indicated if uACR >30 mg/g — recommend Dr. Patel review treatment escalation.
DRAFT_MESSAGE: Dear James, your care team has reviewed your recent health data. Your blood sugar levels have been trending higher over the past year, and your doctor may want to discuss adjusting your treatment. We'd like to schedule a medication review visit with Dr. Patel. During the visit, a simple urine test (kidney check) can also be added to your lab draw. Please call our care coordination team at 1-800-555-PLAN to schedule — we can often get you an appointment within the week.
LANGUAGE: en""",
        ]

    else:  # gap_stacking_four_measures
        dry_run_responses = [
            f"""Thought: Let me check all open diabetes gaps for this member.
Action: gap_registry
Action Input: {member_hash}
Observation: """,
            f"""Thought: Four gaps open: GSD (3x, no A1c in MY), KED (no labs), SPD-E (no statin), EED-E (eye exam >24 months ago). Let me check labs and claims.
Action: ehr_lookup
Action Input: {{"member_id_hash": "{member_hash}", "data_type": "labs"}}
Observation: """,
            f"""Thought: No labs in MY 2026. Last A1c 8.2% in June 2025. No eGFR or uACR. No statin in claims. Eye exam expired >24 months ago. This is a 4-gap open member — ideal gap-stacking opportunity. Let me check SDOH.
Action: sdoh_lookup
Action Input: {member_hash}
Observation: """,
            f"""Thought: English-speaking, medium literacy, work schedule and cost barriers. Dr. Rodriguez is PCP. One comprehensive visit can close all 4 gaps: A1c + kidney labs (same blood draw), statin start (prescribe at visit), eye exam referral (or in-office imaging). Gap-stacking economics: 3x + 1x + 1x + 1x = 6x Stars leverage from one appointment.
Final Answer:
ACTION_TYPE: pcp_warm_outreach
PRIORITY_SCORE: 9.5
MEASURES_ADDRESSED: GSD, KED, SPD-E, EED-E
GAPS_STACKED: 4
CLOSURE_PROBABILITY: 0.72
INERTIA_DETECTED: no
ESCALATION_LADDER_STEP: N/A
RATIONALE: Four open diabetes gaps (GSD 3x + KED + SPD-E + EED-E = 6x Stars exposure) can all be closed in a single comprehensive PCP visit: (1) A1c order closes GSD; (2) uACR + eGFR on same blood draw closes KED; (3) statin prescription at visit closes SPD-E dispensing rate (CARDS trial: 37% CV event reduction in T2D without prior CVD); (4) in-office retinal imaging or eye care referral closes EED-E. Gap-stacking converts one touchpoint into maximum Stars ROI — recommend scheduling a diabetes comprehensive care visit with Dr. Rodriguez.
DRAFT_MESSAGE: Dear Patricia, your health plan has reviewed your care records and identified an opportunity to improve your health and meet your annual wellness goals in a single visit. Dr. Rodriguez can order a comprehensive diabetes check — including a blood sugar test, kidney health labs, and a medication review — and provide a referral for your eye exam, all in one appointment. Please call Dr. Rodriguez's office to schedule your diabetes care visit. We can help coordinate if needed — call 1-800-555-PLAN.
LANGUAGE: en""",
        ]

    call_count = [0]

    async def mock_ainvoke(payload, call_span=None):
        idx = min(call_count[0], len(dry_run_responses) - 1)
        call_count[0] += 1
        return dry_run_responses[idx]

    async def mock_astream(payload, call_span=None):
        text = await mock_ainvoke(payload, call_span)
        for chunk in text.split(" "):
            yield chunk + " "

    # Force-initialize the ReAct adapter (lazy init — None before first run)
    if agent._react_adapter is None:
        from LLM.llm_interface import AsyncLLMAdapter
        from core.agent import _REACT_WRAPPER
        agent._react_adapter = AsyncLLMAdapter(
            prompt_template=_REACT_WRAPPER,
            model=agent._definition.llm_model,
            temperature=agent._definition.temperature,
        )

    agent._react_adapter.ainvoke = mock_ainvoke
    agent._react_adapter.astream = mock_astream
    agent._adapter.ainvoke = mock_ainvoke


async def run_member(
    member_index: int,
    model: str,
    dry_run: bool,
    measurement_year: int,
) -> dict | None:
    """Run one diabetes member through the HEDIS gap agent."""
    from core.agent import Agent
    import dataclasses

    m = DIABETES_DEMO_MEMBERS[member_index]
    member_hash = hash_member_id(m["raw_id"])
    story_label = STORY_LABELS.get(m.get("demo_story", ""), "")

    _section(
        f"Member {member_index + 1}/{len(DIABETES_DEMO_MEMBERS)} — "
        f"{m['persona']} ({m['raw_id']})  {story_label}"
    )
    print(f"  Language: {m['language']} | SDOH: {m['sdoh_risk']} | "
          f"PCP: {m['pcp_name']}")
    print(f"  Open gaps:")
    for g in m["gaps"]:
        stars = _stars_label(g["stars_weight"])
        pdc = f" | PDC={g['pdc_current']:.2f}" if g.get("pdc_current") else ""
        print(f"    {stars} {g['measure_id']}: {g['measure_name']}{pdc}")

    defn = dataclasses.replace(DiabetesHEDISDefinition, llm_model=model)
    agent = Agent(defn)

    if dry_run:
        _patch_dry_run(agent, member_hash, m)

    payload = {
        "agent_type": "diabetes_hedis",
        "member_id_hash": member_hash,
        "member_id_hash_short": member_hash[:12],
        "measurement_year": measurement_year,
        "history": "",
    }

    print(f"\n  {_DIM}Running ReAct reasoning loop…{_RESET}")
    start = time.time()
    chunks: list[str] = []

    try:
        async for chunk in agent.run(payload, session_id=f"dm-demo-{member_hash[:8]}"):
            chunks.append(chunk)
            print(f"{_DIM}.{_RESET}", end="", flush=True)
    except Exception as e:
        print(f"\n  {_RED}Agent failed: {e}{_RESET}")
        return None

    elapsed = time.time() - start
    full_response = "".join(chunks)
    print(f" done ({elapsed:.1f}s)")

    action = parse_diabetes_next_best_action(full_response, member_hash)
    _print_action(action)
    return action


async def main_async(args) -> None:
    _header("praktor.ai — Diabetes HEDIS Gap Closure Agent  (MY 2026)")
    print(f"  Model: {'dry-run' if args.dry_run else args.model} | "
          f"Mode: {'DRY RUN' if args.dry_run else 'LIVE'}")
    print(f"  Measurement year: {YEAR}")
    print(f"\n  Demo members:")
    for m in DIABETES_DEMO_MEMBERS:
        gaps = [g["measure_id"] for g in m["gaps"]]
        story = STORY_LABELS.get(m.get("demo_story", ""), "")
        print(f"    {m['raw_id']} {m['persona']:22s} gaps={gaps}  {story}")

    print(f"\n{_DIM}Seeding diabetes demo member data…{_RESET}")
    seed_diabetes_demo(verbose=False)
    print(f"{_GREEN}✓ Demo data ready{_RESET}")

    members_to_run = (
        [args.member] if args.member is not None
        else range(len(DIABETES_DEMO_MEMBERS))
    )

    actions = []
    for i in members_to_run:
        action = await run_member(i, args.model, args.dry_run, YEAR)
        if action:
            actions.append(action)

    # Summary
    _header("Summary — Diabetes HEDIS Demo")
    if actions:
        total_gaps_stacked = sum(a.get("gaps_stacked", 1) for a in actions)
        inertia_detected = [a for a in actions if a.get("inertia_detected")]
        escalations = [a for a in actions if a.get("action_type") == "escalate"]
        avg_prob = sum(a.get("closure_probability", 0) for a in actions) / len(actions)

        print(f"  Members processed:       {len(actions)}")
        print(f"  Total gaps addressed:    {_GREEN}{total_gaps_stacked}{_RESET}  "
              f"(from {len(actions)} recommendations)")
        print(f"  Inertia cases detected:  {_MAGENTA}{len(inertia_detected)}{_RESET}")
        print(f"  Escalations:             {len(escalations)}")
        print(f"  Avg closure probability: {avg_prob:.0%}")

        print(f"\n  Stars leverage:")
        for a in actions:
            measures = a.get("measures_addressed", [a.get("measure_id", "?")])
            stacked = a.get("gaps_stacked", 1)
            print(f"    {a['member_id_hash'][:12]}  →  {stacked} gap(s): {', '.join(measures)}")

    print(f"\n{_GREEN}✓ Demo complete.{_RESET}")
    print(f"{_DIM}Next: PYTHONPATH=praktor streamlit run praktor/ui/clinical_app.py{_RESET}")


def main():
    parser = argparse.ArgumentParser(description="Diabetes HEDIS Gap Closure Agent Demo")
    parser.add_argument("--model", default="llama3:8b", help="LLM model (default: llama3:8b)")
    parser.add_argument("--dry-run", action="store_true", help="Skip LLM calls (instant demo)")
    parser.add_argument("--member", type=int, default=None,
                        help="Run single member by index 0-2 (default: all)")
    args = parser.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
