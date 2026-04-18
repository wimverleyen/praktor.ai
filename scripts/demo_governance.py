"""
demo_governance.py — governance demo (no Ollama required by default).

Runs RegexDetector directly against sample PHI payloads without an LLM.
Add --model llama3:8b to run the full agent path (requires Ollama).

Usage:
    python scripts/demo_governance.py
    python -m praktor demo-governance
    python -m praktor demo-governance --model llama3:8b
"""

import asyncio
import sys
import argparse


DEMO_CASES = [
    {
        "label": "SSN blocked",
        "text": "Patient SSN is 123-45-6789. Schedule follow-up.",
        "entities": ["US_SSN"],
        "action": "block",
    },
    {
        "label": "Email redacted",
        "text": "Contact patient at john.doe@hospital.org",
        "entities": ["EMAIL_ADDRESS"],
        "action": "redact",
    },
    {
        "label": "Phone flagged",
        "text": "Callback: (555) 867-5309",
        "entities": ["PHONE_NUMBER"],
        "action": "flag",
    },
    {
        "label": "Clean payload — no detection",
        "text": "Patient reported mild discomfort. Prescribed ibuprofen 400mg.",
        "entities": ["US_SSN", "EMAIL_ADDRESS"],
        "action": "block",
    },
]


async def run_detector_demo() -> None:
    from praktor.governance.detectors import RegexDetector, RegexEntities
    from praktor.governance.policy import PolicyAction

    detector = RegexDetector()
    print("\npraktor.ai — Governance Demo (detector-only, no LLM needed)\n")
    print("=" * 60)

    for case in DEMO_CASES:
        results = await detector.detect(case["text"], case["entities"])
        action = PolicyAction(case["action"])
        print(f"\n[{case['label']}]")
        print(f"  input:    {case['text']}")
        print(f"  entities: {case['entities']}  action: {action.value}")

        if not results:
            print("  result:   ✓ no PHI detected — payload is clean")
            continue

        for r in results:
            if action == PolicyAction.BLOCK:
                print(f"  result:   ✗ BLOCKED — {r.entity_type} '{r.text}' at [{r.start}:{r.end}]")
            elif action == PolicyAction.REDACT:
                redacted = case["text"].replace(r.text, f"[REDACTED:{r.entity_type}]")
                print(f"  result:   ✎ REDACTED → {redacted}")
            elif action == PolicyAction.FLAG:
                print(f"  result:   ⚑ FLAGGED — {r.entity_type} '{r.text}' (execution continues, audit written)")

    print("\n" + "=" * 60)
    print("dry_run=True demo:\n")
    from praktor.governance.policy import GovernancePolicy, DetectorConfig
    policy = GovernancePolicy(
        pre_execution=[DetectorConfig(
            detector_class=RegexDetector,
            entities=[RegexEntities.US_SSN],
            action=PolicyAction.BLOCK,
        )],
        dry_run=True,
    )
    print("  GovernancePolicy(dry_run=True) — findings logged to stderr, nothing raised")
    print("  Sending: 'SSN is 123-45-6789'")
    import sys as _sys
    _results = await detector.detect("SSN is 123-45-6789", [RegexEntities.US_SSN])
    for r in _results:
        _sys.stderr.write(f"[governance dry_run] pre_execution: field='text', entity={r.entity_type}, detector=RegexDetector, action=block\n")
    print("  (check stderr above)")
    print()


async def run_agent_demo(model: str) -> None:
    from pydantic import BaseModel
    from praktor.core.agent_definition import AgentDefinition
    from praktor.core.agent import Agent
    from praktor.governance import block_pii, RegexEntities

    class Input(BaseModel):
        agent_type: str = "demo"
        text: str
        session_id: str = ""

    defn = AgentDefinition(
        name="demo",
        prompt_template="Summarize in one sentence: {text}",
        input_schema=Input,
        llm_model=model,
    )
    defn = block_pii(defn, [RegexEntities.US_SSN, RegexEntities.EMAIL_ADDRESS])

    print(f"\n[Agent demo — model={model}]")
    print("  Sending clean payload...")
    agent = Agent(defn)
    payload = {"agent_type": "demo", "text": "Patient reported mild headache.", "session_id": "demo1"}
    async for chunk in agent.run(payload):
        print(chunk, end="", flush=True)
    print()

    print("\n  Sending blocked payload (SSN present)...")
    from praktor.governance.policy import GovernancePolicyViolation
    payload2 = {"agent_type": "demo", "text": "SSN 123-45-6789 — schedule follow-up.", "session_id": "demo2"}
    try:
        async for chunk in agent.run(payload2):
            print(chunk, end="", flush=True)
    except GovernancePolicyViolation as e:
        print(f"  Caught: {e}")


def main() -> None:
    parser = argparse.ArgumentParser(description="praktor.ai governance demo")
    parser.add_argument("--model", default="", help="LLM model (e.g. llama3:8b). Omit for detector-only mode.")
    args = parser.parse_args()

    if args.model:
        asyncio.run(run_agent_demo(args.model))
    else:
        asyncio.run(run_detector_demo())


if __name__ == "__main__":
    main()
