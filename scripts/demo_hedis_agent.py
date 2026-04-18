"""
HEDIS Gap Closure Agent — live demo.

Runs 5 synthetic members through the clinical reasoning ReAct loop
and prints the reasoning trace + Next Best Action for each.

Usage:
    # Dry run (no Ollama needed)
    PYTHONPATH=praktor python scripts/demo_hedis_agent.py --dry-run

    # Real LLM
    PYTHONPATH=praktor python scripts/demo_hedis_agent.py --model qwen2.5

    # Single member
    PYTHONPATH=praktor python scripts/demo_hedis_agent.py --model qwen2.5 --member 0
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "praktor"))
sys.path.insert(0, str(Path(__file__).parent.parent))

# Suppress OTel console span dumps unless an endpoint is configured.
# The SDK writes JSON to stdout when OTLP_ENDPOINT is unset, which clutters demo output.
import os as _os
if not _os.getenv("OTLP_ENDPOINT"):
    _os.environ.setdefault("OTEL_SDK_DISABLED", "true")

# Seed demo data if not already present
from scripts.init_member_brain import seed_demo, DEMO_MEMBERS, hash_member_id, YEAR
from clinical.agents.hedis_gap_agent import HEDISGapDefinition, parse_next_best_action

# ANSI colours
_RESET = "\033[0m"
_BOLD = "\033[1m"
_CYAN = "\033[96m"
_GREEN = "\033[92m"
_YELLOW = "\033[93m"
_RED = "\033[91m"
_DIM = "\033[2m"

STARS_COLOR = {3.0: _GREEN, 2.0: _YELLOW, 1.0: _DIM}


def _stars_label(w: float) -> str:
    color = STARS_COLOR.get(w, _RESET)
    label = f"{w:.0f}x STARS"
    return f"{color}{label}{_RESET}"


def _header(text: str) -> None:
    print(f"\n{_BOLD}{_CYAN}{'═' * 70}{_RESET}")
    print(f"{_BOLD}{_CYAN}  {text}{_RESET}")
    print(f"{_BOLD}{_CYAN}{'═' * 70}{_RESET}")


def _section(text: str) -> None:
    print(f"\n{_BOLD}▸ {text}{_RESET}")


def _print_action(action: dict) -> None:
    color = _GREEN if action.get("closure_probability", 0) >= 0.6 else \
            _YELLOW if action.get("closure_probability", 0) >= 0.4 else _RED
    print(f"\n  {_BOLD}Action:{_RESET} {action.get('action_type', 'unknown')}")
    print(f"  {_BOLD}Measure:{_RESET} {action.get('measure_id', '?')}")
    print(f"  {_BOLD}Priority:{_RESET} {action.get('priority_score', 0):.2f}")
    print(f"  {_BOLD}Closure probability:{_RESET} {color}{action.get('closure_probability', 0):.0%}{_RESET}")
    print(f"  {_BOLD}Language:{_RESET} {action.get('language', 'en')}")
    print(f"\n  {_BOLD}Rationale:{_RESET}")
    print(f"  {action.get('rationale', '—')}")
    print(f"\n  {_BOLD}Draft message ({action.get('language', 'en')}):{_RESET}")
    for line in action.get("draft_content", "").split("\n")[:8]:
        print(f"  {_DIM}{line}{_RESET}")


def _patch_dry_run(agent, member_hash: str, member_data: dict) -> None:
    """Patch agent adapters for dry-run (no Ollama needed)."""
    import dataclasses
    from unittest.mock import AsyncMock, patch

    gaps = member_data["gaps"]
    top_gap = max(gaps, key=lambda g: g["stars_weight"])

    # Simulate a 3-step ReAct trace + Final Answer
    dry_run_responses = [
        # Step 1: discover gaps
        f"""Thought: Let me check what HEDIS gaps are open for this member.
Action: gap_registry
Action Input: {member_hash}
Observation: """,
        # Step 2: check PDC if medication adherence gap
        f"""Thought: The top-priority gap is {top_gap['measure_id']} ({top_gap['stars_weight']:.0f}x STARS). Let me check adherence.
Action: drug_adherence
Action Input: {{"member_id_hash": "{member_hash}", "drug_class": "statin"}}
Observation: """,
        # Step 3: check SDOH
        f"""Thought: Good. Now let me check language and barriers.
Action: sdoh_lookup
Action Input: {member_hash}
Observation: """,
        # Final Answer
        f"""Thought: I have enough information to recommend the best action.
Final Answer:
ACTION_TYPE: pharmacy_refill_reminder
PRIORITY_SCORE: {top_gap['stars_weight'] * 3.0:.1f}
MEASURE: {top_gap['measure_id']}
CLOSURE_PROBABILITY: {0.72 if top_gap.get('pdc_current') else 0.55:.2f}
RATIONALE: Member has an open {top_gap['measure_id']} gap ({top_gap['stars_weight']:.0f}x STARS weighted). PDC is below the 0.80 threshold. PCP speaks same language as member. A pharmacy refill reminder coordinated through PCP is the highest-probability closure action given member's profile and prior outreach history.
DRAFT_MESSAGE: Hello! This is a friendly reminder from your health plan. Your doctor has prescribed medication that helps protect your health. Please refill your prescription at your pharmacy soon — it is important for your annual health goals.
LANGUAGE: {member_data['language']}""",
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

    # Force-initialize the ReAct adapter now (it's built lazily on first run).
    # Without this, the patch below has nothing to patch and Ollama gets called.
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
    # Also patch primary adapter (used to render the base user prompt)
    agent._adapter.ainvoke = mock_ainvoke


async def run_member(
    member_index: int,
    model: str,
    dry_run: bool,
    measurement_year: int,
    active_tools: list[str] | None = None,
) -> dict | None:
    """Run one member through the HEDIS gap agent."""
    from core.agent import Agent
    import dataclasses

    m = DEMO_MEMBERS[member_index]
    member_hash = hash_member_id(m["raw_id"])
    gaps = m["gaps"]

    _section(f"Member {member_index + 1}/5 — {m['raw_id']}")
    print(f"  Language: {m['language']} | SDOH: {m['sdoh_risk']} | "
          f"PCP: {m['pcp_name']} ({m['pcp_language']})")
    print(f"  Open gaps:")
    for g in gaps:
        pdc = f" | PDC={g['pdc_current']:.2f}" if g.get("pdc_current") else ""
        print(f"    {_stars_label(g['stars_weight'])} {g['measure_id']}: {g['measure_name']}{pdc}")

    defn = dataclasses.replace(HEDISGapDefinition, llm_model=model)
    if active_tools:
        defn = dataclasses.replace(defn, tools=active_tools)
    agent = Agent(defn)

    if dry_run:
        _patch_dry_run(agent, member_hash, m)

    payload = {
        "agent_type": "hedis_gap",
        "member_id_hash": member_hash,
        "member_id_hash_short": member_hash[:12],
        "measurement_year": measurement_year,
        "history": "",
    }

    print(f"\n  {_DIM}Running ReAct reasoning loop…{_RESET}")
    start = time.time()
    chunks: list[str] = []

    try:
        async for chunk in agent.run(payload, session_id=f"demo-{member_hash[:8]}"):
            chunks.append(chunk)
            print(f"{_DIM}.{_RESET}", end="", flush=True)
    except Exception as e:
        print(f"\n  {_RED}Agent failed: {e}{_RESET}")
        return None

    elapsed = time.time() - start
    full_response = "".join(chunks)
    print(f" done ({elapsed:.1f}s)")

    action = parse_next_best_action(full_response, member_hash)
    _print_action(action)

    try:
        from clinical.evaluation.closure_tracker import get_tracker
        rec_id = get_tracker().record_recommendation(action)
        print(f"  {_DIM}Saved to review queue (id={rec_id}){_RESET}")
    except Exception as e:
        print(f"  {_DIM}Warning: could not save to tracker: {e}{_RESET}")

    return action


async def main_async(args) -> None:
    _header("praktor.ai — HEDIS Gap Closure Agent Demo")
    print(f"  Model: {'dry-run' if args.dry_run else args.model} | Mode: {'DRY RUN' if args.dry_run else 'LIVE'}")
    print(f"  Measurement year: {YEAR}")

    # Seed demo data
    print(f"\n{_DIM}Seeding demo member data…{_RESET}")
    seed_demo(verbose=False)
    print(f"{_GREEN}✓ Demo data ready{_RESET}")

    active_tools = [t.strip() for t in args.tools.split(",") if t.strip()] if args.tools else None

    members_to_run = [args.member] if args.member is not None else range(len(DEMO_MEMBERS))

    actions = []
    for i in members_to_run:
        action = await run_member(
            i, args.model, args.dry_run, YEAR, active_tools
        )
        if action:
            actions.append(action)

    # Summary
    _header("Summary")
    triple_weighted = [a for a in actions if a.get("measure_id") in ("MAC", "MAD", "MAP")]
    escalations = [a for a in actions if a.get("action_type") == "escalate"]
    print(f"  Members processed: {len(actions)}")
    print(f"  Triple-weighted gaps targeted: {len(triple_weighted)}")
    print(f"  Escalations: {len(escalations)}")
    if actions:
        avg_prob = sum(a.get("closure_probability", 0) for a in actions) / len(actions)
        print(f"  Avg closure probability: {avg_prob:.0%}")

    print(f"\n{_GREEN}✓ Demo complete.{_RESET}")
    print(f"{_DIM}Next: run PYTHONPATH=praktor streamlit run praktor/ui/clinical_app.py{_RESET}")


def main():
    parser = argparse.ArgumentParser(description="HEDIS Gap Closure Agent Demo")
    parser.add_argument("--model", default="llama3:8b", help="LLM model (default: llama3:8b)")
    parser.add_argument("--dry-run", action="store_true", help="Skip LLM calls (instant demo)")
    parser.add_argument("--member", type=int, default=None,
                        help="Run single member by index 0-4 (default: all)")
    parser.add_argument("--tools", default="",
                        help="Comma-separated active tool names (default: all)")
    args = parser.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
