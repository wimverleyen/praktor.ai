"""
ReAct Demo — praktor.ai

Runs a multi-step research question through the ReAct (Reason + Act) loop.
Shows each Thought, Action, Observation, and Final Answer as they occur.

Usage:
    python scripts/demo_react.py
    python scripts/demo_react.py --question "How does FAISS work?"
    python scripts/demo_react.py --model mistral
"""
import sys
import asyncio
import argparse
import textwrap
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent / "praktor"))

from pydantic import BaseModel
from core.agent_definition import AgentDefinition, MemoryPolicy
from core.agent import Agent
import core.agent as _agent_mod
import re

# ── ANSI colours ─────────────────────────────────────────────────────────────
RESET  = "\033[0m"
BOLD   = "\033[1m"
DIM    = "\033[2m"
CYAN   = "\033[36m"
YELLOW = "\033[33m"
GREEN  = "\033[32m"
BLUE   = "\033[34m"
RED    = "\033[31m"
GREY   = "\033[90m"

def _wrap(text: str, indent: int = 4) -> str:
    prefix = " " * indent
    return textwrap.fill(text, width=88, initial_indent=prefix, subsequent_indent=prefix)


def _print_step(step: int, llm_response: str, observation: str | None = None) -> None:
    """Pretty-print one ReAct step."""
    # Split out Thought lines vs Action lines
    lines = llm_response.strip().splitlines()
    for line in lines:
        stripped = line.strip()
        if stripped.lower().startswith("thought:"):
            content = stripped[len("thought:"):].strip()
            print(f"\n{CYAN}{BOLD}  Thought{RESET}{CYAN} (step {step}){RESET}")
            print(_wrap(content))
        elif stripped.lower().startswith("action:"):
            content = stripped[len("action:"):].strip()
            print(f"\n{YELLOW}{BOLD}  Action{RESET}{YELLOW}  → {content}{RESET}")
        elif stripped.lower().startswith("action input:"):
            content = stripped[len("action input:"):].strip()
            print(f"{GREY}           input: {content}{RESET}")
        elif stripped.lower().startswith("final answer:"):
            content = stripped[len("final answer:"):].strip()
            print(f"\n{GREEN}{BOLD}  Final Answer{RESET}")
            print(_wrap(content))

    if observation is not None:
        print(f"\n{BLUE}{BOLD}  Observation{RESET}")
        # Truncate long observations for readability
        obs_preview = observation.strip()[:400]
        if len(observation) > 400:
            obs_preview += f"\n  {DIM}... ({len(observation)} chars total){RESET}"
        for obs_line in obs_preview.splitlines():
            print(f"    {GREY}{obs_line}{RESET}")


# ── Instrumented ReAct loop ───────────────────────────────────────────────────

async def _instrumented_react_loop(self, payload: dict, span):
    """
    Wraps the real _react_loop to intercept and display each step.
    Yields the same chunks as the original.
    """
    from core.agent import _REACT_WRAPPER, _ACTION_RE, _ACTION_INPUT_RE, _FINAL_ANSWER_RE
    from LLM.llm_interface import AsyncLLMAdapter

    tool_descriptions = "\n".join(
        f"- {name}: {tool.description}"
        for name, tool in self._tools.items()
    )
    tool_names = ", ".join(self._tools.keys())

    try:
        user_prompt = self._adapter._prompt.format(
            **{k: v for k, v in payload.items()
               if k in self._adapter._prompt.input_variables}
        )
    except Exception:
        user_prompt = str(payload)

    if self._react_adapter is None:
        self._react_adapter = AsyncLLMAdapter(
            prompt_template=_REACT_WRAPPER,
            model=self._definition.llm_model,
            temperature=self._definition.temperature,
        )

    scratchpad = ""
    step = 0

    while step < self._definition.max_steps:
        step += 1

        react_payload = {
            "user_prompt": user_prompt,
            "tool_descriptions": tool_descriptions,
            "tool_names": tool_names,
            "scratchpad": scratchpad,
        }

        print(f"\n{DIM}{'─' * 72}{RESET}")

        with span.child_llm_call(pass_number=step, kind="llm_call") as llm_span:
            llm_response = await self._react_adapter.ainvoke(
                react_payload, call_span=llm_span
            )

        action_match = _ACTION_RE.search(llm_response)
        action_input_match = _ACTION_INPUT_RE.search(llm_response)

        final_match = _FINAL_ANSWER_RE.search(llm_response)
        if final_match and not (action_match and action_input_match):
            _print_step(step, llm_response)
            final_answer = final_match.group(1).strip()
            yield final_answer
            return

        if action_match and action_input_match:
            tool_name = action_match.group(1).strip()
            tool_input = action_input_match.group(1).strip()

            scratchpad += f"\n{llm_response.strip()}\nObservation: "

            if tool_name not in self._tools:
                observation = f"Error: unknown tool '{tool_name}'. Available: {tool_names}"
            else:
                with span.child_llm_call(pass_number=step, kind="tool_call", tool_name=tool_name) as ts:
                    result = await self._tools[tool_name](tool_input)
                    ts.output_tokens = len(result.content.split()) if result.content else 0
                observation = result.content if result.ok else f"Error: {result.error}"

            _print_step(step, llm_response, observation)
            scratchpad += observation
            continue

        # No action, no final answer
        _print_step(step, llm_response)
        yield llm_response
        return

    print(f"\n{RED}  Warning: reached max_steps={self._definition.max_steps} without a Final Answer{RESET}")
    yield llm_response


# ── Agent definition ──────────────────────────────────────────────────────────

class ResearchInput(BaseModel):
    agent_type: str = "researcher"
    question: str
    session_id: str = ""
    history: str = ""


def make_researcher(model: str, max_steps: int) -> Agent:
    definition = AgentDefinition(
        name="researcher",
        prompt_template=(
            "You are a research assistant. Answer this question accurately and concisely.\n\n"
            "Question: {question}\n\n"
            "Previous context: {history}"
        ),
        input_schema=ResearchInput,
        llm_model=model,
        temperature=0.0,
        tools=["web_search"],
        max_steps=max_steps,
        memory_policy=MemoryPolicy.NONE,
    )
    # Register the web_search tool
    import tools.web_search  # noqa: F401 — registers at import time
    return Agent(definition)


# ── Main ──────────────────────────────────────────────────────────────────────

async def run(question: str, model: str, max_steps: int) -> None:
    print(f"\n{BOLD}praktor.ai — ReAct Demo{RESET}")
    print(f"{DIM}Model: {model}   Max steps: {max_steps}{RESET}")
    print(f"\n{BOLD}Question:{RESET} {question}")

    agent = make_researcher(model, max_steps)

    # Patch _react_loop with our instrumented version
    agent._react_loop = _instrumented_react_loop.__get__(agent, Agent)

    print(f"\n{DIM}{'═' * 72}{RESET}")

    chunks = []
    async for chunk in agent.run({"question": question}, session_id="demo"):
        chunks.append(chunk)

    # Final answer was already printed inside _instrumented_react_loop
    print(f"\n{DIM}{'═' * 72}{RESET}")
    print(f"\n{GREY}Trajectory: {len(agent._definition.tools)} tool(s) available, "
          f"up to {max_steps} steps.{RESET}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="ReAct loop demo")
    parser.add_argument(
        "--question", "-q",
        default="What are the latest OpenTelemetry features for LLM observability in 2025?",
        help="Research question to answer",
    )
    parser.add_argument(
        "--model", "-m",
        default="llama3:8b",
        help="LLM model (llama3:8b, mistral, claude-sonnet-4-6, etc.)",
    )
    parser.add_argument(
        "--steps", "-s",
        type=int,
        default=4,
        help="Max ReAct steps (default: 4)",
    )
    args = parser.parse_args()
    asyncio.run(run(args.question, args.model, args.steps))


if __name__ == "__main__":
    main()
