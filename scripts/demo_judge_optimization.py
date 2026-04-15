"""
LLM-as-Judge + Prompt Optimization — end-to-end demo
═════════════════════════════════════════════════════

Workflow demonstrated:

  1. Register v1 (baseline prompt) in PromptRegistry
  2. Run 5 research questions through the agent
  3. Judge each response: relevance, accuracy, completeness, conciseness
  4. Record scores → registry avg_score + monitoring SQLite
  5. Native optimizer: meta-LLM rewrites the prompt using the eval feedback
  6. [Optional DSPy] BootstrapFewShot compiles a few-shot optimized prompt
  7. Register v2 (optimized prompt) and run the same 5 questions again
  8. Re-judge, compare before/after scores, show unified diff

Usage:
    cd praktor.ai
    PYTHONPATH=praktor python scripts/demo_judge_optimization.py
    PYTHONPATH=praktor python scripts/demo_judge_optimization.py --model mistral
    PYTHONPATH=praktor python scripts/demo_judge_optimization.py --dry-run
"""

from __future__ import annotations

import asyncio
import argparse
import sys
import textwrap
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "praktor"))

# ── ANSI colours ──────────────────────────────────────────────────────────────
R      = "\033[0m"
BOLD   = "\033[1m"
DIM    = "\033[2m"
CYAN   = "\033[36m"
YELLOW = "\033[33m"
GREEN  = "\033[32m"
RED    = "\033[31m"
MAGENTA= "\033[35m"
WHITE  = "\033[97m"
GREY   = "\033[90m"

W = 74  # column width

def hr(char="─"): print(f"{DIM}{char * W}{R}")
def section(title): print(f"\n{CYAN}{BOLD}{'▶'} {title}{R}")
def ok(msg):   print(f"  {GREEN}✓{R}  {msg}")
def info(msg): print(f"  {GREY}·{R}  {msg}")
def warn(msg): print(f"  {YELLOW}⚠{R}  {msg}")

def score_bar(score: float, width: int = 20) -> str:
    color = GREEN if score >= 7.5 else (YELLOW if score >= 5.0 else RED)
    filled = int(width * score / 10)
    return f"{color}{'█' * filled}{GREY}{'░' * (width - filled)}{R}"

def score_str(score: float) -> str:
    color = GREEN if score >= 7.5 else (YELLOW if score >= 5.0 else RED)
    return f"{color}{BOLD}{score:.2f}/10{R}"

def print_score_table(title: str, evals: list[dict]) -> None:
    print(f"\n  {BOLD}{title}{R}")
    print(f"  {DIM}{'#':<4} {'Question':<38} {'Score':>7}  {'Rel':>5} {'Acc':>5} {'Cpl':>5} {'Con':>5}{R}")
    hr("  ·")
    for e in evals:
        c = e["criteria"]
        print(
            f"  {e['idx']:<4} "
            f"{e['question'][:37]:<38} "
            f"{score_str(e['score']):>7}  "
            f"{c.get('relevance',0):>5.1f} "
            f"{c.get('accuracy',0):>5.1f} "
            f"{c.get('completeness',0):>5.1f} "
            f"{c.get('conciseness',0):>5.1f}"
        )
    scores = [e["score"] for e in evals]
    avg = sum(scores) / len(scores)
    print(f"  {DIM}{'─'*4} {'Average':38} {score_str(avg):>7}{R}")


# ── Prompts ───────────────────────────────────────────────────────────────────

PROMPT_V1 = """\
You are a helpful AI assistant.

Answer the following question about machine learning or AI:
{question}

Previous context: {history}

Answer:"""

# What a "good" answer looks like — used as expected output signal for the judge
REFERENCE_ANSWERS = {
    "What is the difference between RAG and fine-tuning?":
        "RAG (Retrieval-Augmented Generation) retrieves relevant context at inference time "
        "without modifying model weights, making it fast to update and cost-effective. "
        "Fine-tuning updates model weights on domain data, improving fluency in a specific style "
        "but requiring expensive retraining when knowledge changes. RAG is preferred for dynamic "
        "knowledge; fine-tuning for stable task-specific behavior.",

    "Explain the ReAct agent pattern in 3 sentences.":
        "ReAct interleaves reasoning (Thought) and acting (Action/Observation) steps, "
        "allowing an LLM to call tools and update its reasoning based on results. "
        "Each step produces a Thought explaining the plan, an Action invoking a tool, "
        "and an Observation with the tool's result. This loop continues until the model "
        "produces a Final Answer, enabling multi-step problem solving.",

    "What are the main trade-offs of using FAISS vs Chroma for vector search?":
        "FAISS is a C++ library optimized for high-throughput similarity search with "
        "fine-grained index control (IVF, HNSW, PQ), best for large-scale offline workloads. "
        "Chroma is a developer-friendly Python-native store with built-in metadata filtering, "
        "persistence, and embeddings, better suited for prototyping and smaller datasets. "
        "FAISS wins on raw speed and scale; Chroma wins on ease of use and document management.",

    "How does DSPy differ from LangChain for building LLM applications?":
        "DSPy treats prompt engineering as a compilation problem — you declare a program "
        "structure and an optimizer automatically tunes prompts and few-shot examples against "
        "a metric. LangChain is a composable toolkit for chaining LLM calls, tools, and memory, "
        "leaving prompt engineering to the developer. DSPy optimizes the prompt; "
        "LangChain orchestrates the pipeline.",

    "What is OpenTelemetry and why does it matter for LLM observability?":
        "OpenTelemetry is a vendor-neutral CNCF standard for collecting traces, metrics, and "
        "logs from distributed systems. For LLM applications it enables per-request tracing of "
        "prompt rendering, model latency, token counts, and tool calls in a format that any "
        "collector (Jaeger, Grafana, Honeycomb) can ingest. This is critical for debugging "
        "multi-step agent behaviors and tracking cost/quality trends at scale.",
}

TEST_QUESTIONS = list(REFERENCE_ANSWERS.keys())


# ── Agent construction ────────────────────────────────────────────────────────

from pydantic import BaseModel
from core.agent_definition import AgentDefinition, MemoryPolicy
from core.agent import Agent


class ResearchInput(BaseModel):
    agent_type: str = "researcher"
    question: str
    session_id: str = ""
    history: str = ""


def make_agent(prompt_template: str, model: str) -> Agent:
    definition = AgentDefinition(
        name="researcher",
        prompt_template=prompt_template,
        input_schema=ResearchInput,
        llm_model=model,
        temperature=0.1,
        memory_policy=MemoryPolicy.NONE,
    )
    return Agent(definition)


# ── Dry-run patch ─────────────────────────────────────────────────────────────

_DRY_RUN_RESPONSES = {
    "What is the difference between RAG and fine-tuning?":
        "RAG retrieves documents at query time without changing weights. "
        "Fine-tuning trains model weights on domain data. "
        "Use RAG for dynamic knowledge, fine-tuning for fixed task styles.",

    "Explain the ReAct agent pattern in 3 sentences.":
        "ReAct combines reasoning and acting in a Thought/Action/Observation loop. "
        "The model thinks, calls a tool, observes the result, and repeats. "
        "It ends with a Final Answer when it has enough information.",

    "What are the main trade-offs of using FAISS vs Chroma for vector search?":
        "FAISS is fast and scalable for large datasets but complex to set up. "
        "Chroma is easier to use with built-in Python support and metadata filtering. "
        "Choose FAISS for production scale and Chroma for development.",

    "How does DSPy differ from LangChain for building LLM applications?":
        "DSPy automatically optimizes prompts and few-shot examples. "
        "LangChain provides composable building blocks for LLM pipelines. "
        "DSPy is about optimization; LangChain is about orchestration.",

    "What is OpenTelemetry and why does it matter for LLM observability?":
        "OpenTelemetry is a standard for collecting traces and metrics. "
        "For LLMs it enables tracing of prompt calls, token counts, and latency. "
        "This helps debug agents and track cost and quality over time.",
}

_DRY_RUN_JUDGE_BASE = {
    "What is the difference between RAG and fine-tuning?":
        {"relevance": 7.0, "accuracy": 7.5, "completeness": 6.0, "conciseness": 8.0},
    "Explain the ReAct agent pattern in 3 sentences.":
        {"relevance": 8.0, "accuracy": 7.0, "completeness": 6.5, "conciseness": 8.5},
    "What are the main trade-offs of using FAISS vs Chroma for vector search?":
        {"relevance": 7.5, "accuracy": 7.0, "completeness": 6.0, "conciseness": 7.5},
    "How does DSPy differ from LangChain for building LLM applications?":
        {"relevance": 8.0, "accuracy": 7.5, "completeness": 6.5, "conciseness": 8.0},
    "What is OpenTelemetry and why does it matter for LLM observability?":
        {"relevance": 7.0, "accuracy": 7.0, "completeness": 6.5, "conciseness": 7.5},
}

_DRY_RUN_JUDGE_OPT = {
    q: {k: min(10.0, v + 1.2) for k, v in c.items()}
    for q, c in _DRY_RUN_JUDGE_BASE.items()
}


def _patch_dry_run(agent: Agent, judge, improved: bool = False) -> None:
    """Replace LLM and judge calls with instant deterministic stubs."""
    async def _fake_astream(data, call_span=None):
        q = data.get("question", "")
        response = _DRY_RUN_RESPONSES.get(q, "This is a mock response.")
        for word in response.split():
            yield word + " "
            await asyncio.sleep(0.001)
        if call_span is not None:
            call_span.output_tokens = len(response.split())

    agent._adapter.astream = _fake_astream

    # Patch judge
    from core.judge import JudgeScore
    async def _fake_evaluate(question, response, expected=""):
        table = _DRY_RUN_JUDGE_OPT if improved else _DRY_RUN_JUDGE_BASE
        criteria = table.get(question, {"relevance": 7.0, "accuracy": 7.0,
                                        "completeness": 7.0, "conciseness": 7.0})
        score = sum(criteria.values()) / len(criteria)
        return JudgeScore(
            score=round(score, 2), reasoning="Dry-run mock evaluation.",
            criteria=criteria, question=question, response=response,
        )

    # Also patch the meta-LLM in optimizer
    async def _fake_meta_invoke(data, call_span=None):
        return (
            "You are an expert AI research assistant specializing in ML and AI systems.\n\n"
            "Answer the following question with precision, using concrete examples and "
            "technical depth appropriate for an experienced ML practitioner.\n\n"
            "Question: {question}\n\n"
            "Previous context: {history}\n\n"
            "Provide a structured answer covering: (1) core concept, "
            "(2) practical implications, (3) key trade-offs or considerations.\n\n"
            "Answer:"
        )

    judge.evaluate = _fake_evaluate
    return _fake_meta_invoke  # caller patches optimizer's meta adapter


# ── Core evaluation loop ──────────────────────────────────────────────────────

async def evaluate_prompt(
    prompt_template: str,
    version_id: str,
    model: str,
    registry,
    judge,
    dry_run: bool,
    improved: bool = False,
) -> list[dict]:
    """Run all test questions, judge each, record scores. Returns eval dicts."""
    agent = make_agent(prompt_template, model)
    dry_meta = None
    if dry_run:
        dry_meta = _patch_dry_run(agent, judge, improved=improved)

    evals = []
    for idx, question in enumerate(TEST_QUESTIONS, 1):
        t0 = time.time()
        chunks = []
        async for chunk in agent.run({"question": question}, session_id=f"eval-{version_id[:6]}-{idx}"):
            chunks.append(chunk)
        latency_ms = (time.time() - t0) * 1000
        response = "".join(chunks).strip()

        expected = REFERENCE_ANSWERS[question]
        score_obj = await judge.evaluate(question=question, response=response, expected=expected)

        registry.record_eval(
            "researcher", version_id,
            score=score_obj.score, latency_ms=latency_ms,
        )

        evals.append({
            "idx": idx,
            "question": question,
            "response": response,
            "score": score_obj.score,
            "criteria": score_obj.criteria,
            "reasoning": score_obj.reasoning,
            "latency_ms": latency_ms,
        })

        info(
            f"Q{idx}: {score_str(score_obj.score)}  "
            f"rel={score_obj.criteria.get('relevance',0):.1f}  "
            f"acc={score_obj.criteria.get('accuracy',0):.1f}  "
            f"cpl={score_obj.criteria.get('completeness',0):.1f}  "
            f"con={score_obj.criteria.get('conciseness',0):.1f}  "
            f"{latency_ms:.0f}ms"
        )

    return evals, dry_meta


# ── Main ──────────────────────────────────────────────────────────────────────

async def main(model: str, dry_run: bool, use_dspy: bool):
    print(f"\n{BOLD}{WHITE}praktor.ai — LLM Judge + Prompt Optimization Demo{R}")
    print(f"{DIM}Model: {model}   Dry-run: {dry_run}   DSPy: {use_dspy}{R}")
    hr("═")

    import tempfile, os
    tmp_dir = tempfile.mkdtemp(prefix="praktor_opt_")
    registry = __import__("core.prompt_registry", fromlist=["PromptRegistry"]).PromptRegistry(
        store_dir=tmp_dir
    )

    from core.judge import JudgeEvaluator
    from core.prompt_optimizer import PromptOptimizer
    from monitoring import record_kpi, get_registry as get_mon_registry

    judge = JudgeEvaluator(model=model, temperature=0.0)
    mon_registry = get_mon_registry()

    # ──────────────────────────────────────────────────────────────────────────
    section("Step 1 — Register baseline prompt (v1)")
    # ──────────────────────────────────────────────────────────────────────────
    v1 = registry.save(
        "researcher",
        template=PROMPT_V1,
        notes="baseline: generic helpful assistant",
        set_active=True,
    )
    ok(f"Saved version {CYAN}{v1.version_id}{R}  (active)")
    print(f"\n  {DIM}Prompt preview:{R}")
    for line in PROMPT_V1.strip().splitlines():
        print(f"  {GREY}{line}{R}")

    # ──────────────────────────────────────────────────────────────────────────
    section("Step 2 — Evaluate baseline with LLM judge")
    # ──────────────────────────────────────────────────────────────────────────
    print(f"\n  Running {len(TEST_QUESTIONS)} questions through researcher agent...")
    print(f"  {DIM}Judge model: {model}  Criteria: relevance, accuracy, completeness, conciseness{R}\n")

    v1_evals, dry_meta = await evaluate_prompt(
        PROMPT_V1, v1.version_id, model, registry, judge,
        dry_run=dry_run, improved=False,
    )

    print_score_table("Baseline scores (v1)", v1_evals)

    v1_avg = sum(e["score"] for e in v1_evals) / len(v1_evals)
    print(f"\n  {DIM}Baseline mean:{R} {score_str(v1_avg)}  {score_bar(v1_avg)}")

    # Record to monitoring
    for e in v1_evals:
        mon_registry.record_judge("researcher", e["score"], version_id=v1.version_id)
        record_kpi("judge_score_v1", e["score"], tags={"model": model})

    # Weakest criteria across all questions
    all_criteria = [e["criteria"] for e in v1_evals]
    avg_by_criterion = {
        k: sum(c.get(k, 0) for c in all_criteria) / len(all_criteria)
        for k in ("relevance", "accuracy", "completeness", "conciseness")
    }
    weakest = min(avg_by_criterion, key=avg_by_criterion.get)
    print(f"\n  {YELLOW}Weakest criterion:{R} {BOLD}{weakest}{R} "
          f"(avg {avg_by_criterion[weakest]:.2f})  → optimization target")

    # ──────────────────────────────────────────────────────────────────────────
    section("Step 3 — Build optimization examples from eval data")
    # ──────────────────────────────────────────────────────────────────────────
    examples = [
        {
            "input":  {"question": e["question"], "history": ""},
            "output": e["response"],
            "score":  e["score"],
        }
        for e in v1_evals
    ]
    ok(f"Built {len(examples)} examples  (mean score {v1_avg:.2f}/10)")
    for ex in examples:
        info(f"Q: {ex['input']['question'][:55]}  score={ex['score']:.1f}")

    # ──────────────────────────────────────────────────────────────────────────
    section("Step 4 — Run prompt optimizer")
    # ──────────────────────────────────────────────────────────────────────────
    optimizer = PromptOptimizer(
        agent_name="researcher",
        model=model,
        registry=registry,
        judge=judge,
        use_dspy=use_dspy,
    )

    if dry_run and dry_meta:
        # Patch meta adapter to return the predefined improved prompt
        optimizer._meta_adapter.ainvoke = dry_meta
        # Also patch judge.evaluate used inside optimizer._eval_on_examples
        from core.judge import JudgeScore
        async def _fake_eval_improved(question, response, expected=""):
            criteria = {k: min(10.0, v + 1.2)
                        for k, v in _DRY_RUN_JUDGE_BASE.get(question, {
                            "relevance": 7.0, "accuracy": 7.0,
                            "completeness": 7.0, "conciseness": 7.0,
                        }).items()}
            return JudgeScore(score=round(sum(criteria.values())/len(criteria), 2),
                              reasoning="Mock improved.", criteria=criteria,
                              question=question, response=response)
        optimizer.judge.evaluate = _fake_eval_improved

    goal = (
        f"Improve {weakest}. Make the agent give more precise, structured answers "
        f"with concrete examples and technical depth for ML practitioners."
    )
    print(f"\n  {DIM}Goal:{R} {goal}\n")

    t0 = time.time()
    result = await optimizer.optimize(examples, goal=goal)
    opt_ms = (time.time() - t0) * 1000

    ok(f"Optimizer mode: {CYAN}{result.mode}{R}  ({opt_ms:.0f}ms)")
    ok(f"New version:    {CYAN}{result.version.version_id}{R}  {result.notes[:50]}")
    if result.score_after is not None:
        ok(f"Quick-eval score: {score_str(result.score_after)}")

    # ──────────────────────────────────────────────────────────────────────────
    section("Step 5 — Inspect the optimized prompt (diff)")
    # ──────────────────────────────────────────────────────────────────────────
    diff = registry.diff("researcher", v1.version_id, result.version.version_id)
    if diff == "(no differences)":
        warn("Optimizer returned no change (model may need more examples or iterations)")
        v2_template = PROMPT_V1
        v2_id = v1.version_id
    else:
        print()
        for line in diff.splitlines():
            if line.startswith("---") or line.startswith("+++"):
                print(f"  {BOLD}{line}{R}")
            elif line.startswith("-"):
                print(f"  {RED}{line}{R}")
            elif line.startswith("+"):
                print(f"  {GREEN}{line}{R}")
            elif line.startswith("@@"):
                print(f"  {CYAN}{line}{R}")
            else:
                print(f"  {DIM}{line}{R}")
        v2_template = result.version.template
        v2_id = result.version.version_id

    # ──────────────────────────────────────────────────────────────────────────
    section("Step 6 — Activate optimized prompt and re-evaluate")
    # ──────────────────────────────────────────────────────────────────────────
    if v2_id != v1.version_id:
        registry.set_active("researcher", v2_id)
        ok(f"Activated v2: {CYAN}{v2_id}{R}")

    print(f"\n  Re-running {len(TEST_QUESTIONS)} questions with optimized prompt...\n")

    v2_evals, _ = await evaluate_prompt(
        v2_template, v2_id, model, registry, judge,
        dry_run=dry_run, improved=True,
    )

    print_score_table("Optimized scores (v2)", v2_evals)

    v2_avg = sum(e["score"] for e in v2_evals) / len(v2_evals)
    print(f"\n  {DIM}Optimized mean:{R} {score_str(v2_avg)}  {score_bar(v2_avg)}")

    for e in v2_evals:
        mon_registry.record_judge("researcher", e["score"], version_id=v2_id)
        record_kpi("judge_score_v2", e["score"], tags={"model": model})

    # ──────────────────────────────────────────────────────────────────────────
    section("Step 7 — Before / After comparison")
    # ──────────────────────────────────────────────────────────────────────────
    delta = v2_avg - v1_avg
    delta_color = GREEN if delta > 0 else (YELLOW if delta == 0 else RED)
    delta_sym   = "↑" if delta > 0 else ("→" if delta == 0 else "↓")

    print(f"""
  ┌────────────────────────────────────────────────────────┐
  │  Version  Score      Bar                               │
  ├────────────────────────────────────────────────────────┤
  │  v1 (baseline)   {score_str(v1_avg)}  {score_bar(v1_avg, 16)}         │
  │  v2 (optimized)  {score_str(v2_avg)}  {score_bar(v2_avg, 16)}         │
  │                                                        │
  │  Δ improvement   {delta_color}{BOLD}{delta_sym} {abs(delta):.2f} pts{R}                           │
  └────────────────────────────────────────────────────────┘""")

    print(f"\n  {BOLD}Per-criterion delta:{R}")
    v1_crit_avg = {k: sum(e["criteria"].get(k, 0) for e in v1_evals) / len(v1_evals)
                   for k in ("relevance", "accuracy", "completeness", "conciseness")}
    v2_crit_avg = {k: sum(e["criteria"].get(k, 0) for e in v2_evals) / len(v2_evals)
                   for k in ("relevance", "accuracy", "completeness", "conciseness")}
    for criterion in ("relevance", "accuracy", "completeness", "conciseness"):
        d = v2_crit_avg[criterion] - v1_crit_avg[criterion]
        col = GREEN if d > 0.05 else (YELLOW if abs(d) <= 0.05 else RED)
        sym = "↑" if d > 0.05 else ("→" if abs(d) <= 0.05 else "↓")
        is_target = " ← optimization target" if criterion == weakest else ""
        print(f"    {criterion:<14} {v1_crit_avg[criterion]:.2f} → "
              f"{v2_crit_avg[criterion]:.2f}  {col}{sym} {abs(d):.2f}{R}{GREY}{is_target}{R}")

    # ──────────────────────────────────────────────────────────────────────────
    section("Step 8 — Registry history")
    # ──────────────────────────────────────────────────────────────────────────
    print()
    for v in registry.list("researcher"):
        print(f"  {CYAN}{v.summary()}{R}")

    # ──────────────────────────────────────────────────────────────────────────
    section("Summary")
    # ──────────────────────────────────────────────────────────────────────────
    print(f"""
  {BOLD}What happened:{R}

  1. Prompt v1 registered in PromptRegistry (sha256 content-addressed)
  2. 5 questions evaluated → judge scored {len(v1_evals)} responses on 4 criteria
  3. Weakest criterion identified: {YELLOW}{weakest}{R} (avg {avg_by_criterion[weakest]:.2f})
  4. Native optimizer rewrote the prompt using meta-LLM + eval feedback
     {'  [DSPy BootstrapFewShot also available — pass --dspy to enable]' if not use_dspy else
      '  [DSPy BootstrapFewShot compiled few-shot examples into the prompt]'}
  5. v2 registered, diff computed, active version updated
  6. Same 5 questions re-evaluated with v2
  7. Score delta: {delta_color}{BOLD}{delta_sym} {abs(delta):.2f} pts{R} ({v1_avg:.2f} → {v2_avg:.2f})

  {BOLD}Key APIs used:{R}

  {GREY}from core.judge import JudgeEvaluator{R}
  {GREY}score = await judge.evaluate(question, response, expected){R}
  {GREY}  → JudgeScore(score, reasoning, criteria{{relevance,accuracy,completeness,conciseness}}){R}

  {GREY}from core.prompt_registry import PromptRegistry{R}
  {GREY}registry.save(agent, template, notes, set_active=True){R}
  {GREY}registry.record_eval(agent, version_id, score, latency_ms){R}
  {GREY}registry.diff(agent, v1_id, v2_id)  # unified diff{R}

  {GREY}from core.prompt_optimizer import PromptOptimizer{R}
  {GREY}result = await optimizer.optimize(examples, goal="...")  # native or DSPy{R}
  {GREY}  → OptimizationResult(version, score_before, score_after, mode){R}

  {BOLD}Monitoring:{R}
  {GREY}All judge scores recorded to ~/.praktor/monitoring.db{R}
  {GREY}python -m praktor monitor summary   # view aggregated metrics{R}
""")


def parse_args():
    p = argparse.ArgumentParser(description="LLM Judge + Prompt Optimization demo")
    p.add_argument("--model",    "-m", default="llama3:8b",
                   help="LLM model (default: llama3:8b)")
    p.add_argument("--dry-run",  action="store_true",
                   help="Mock LLM — runs instantly without Ollama")
    p.add_argument("--dspy",     action="store_true",
                   help="Enable DSPy BootstrapFewShot optimizer (requires dspy-ai)")
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(main(model=args.model, dry_run=args.dry_run, use_dspy=args.dspy))
