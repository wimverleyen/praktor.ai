"""
praktor.ai — Monitoring Demo
════════════════════════════════════════════════════════════════════
Runs a live agent workload against Ollama and shows a real-time
terminal dashboard of cost, tokens, latency, judge scores, and
business KPIs.

What this demo does:
  1. Starts a Prometheus scrape server on :8080
  2. Runs 3 agent types (cover letter, search/research, code review)
     across a mix of scenarios — some succeed, some intentionally fail
  3. Evaluates responses with an LLM judge
  4. Records business KPIs (acceptance rate, quality score)
  5. Redraws a rich terminal dashboard after every completed run
  6. Exports praktor-dashboard.json (import into Grafana)

Usage:
    cd praktor.ai
    PYTHONPATH=praktor python scripts/demo_monitoring.py
    PYTHONPATH=praktor python scripts/demo_monitoring.py --model mistral --no-judge
    PYTHONPATH=praktor python scripts/demo_monitoring.py --dry-run   # mock LLM, instant
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
import json
import random
import textwrap
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "praktor"))

# ── ANSI palette ─────────────────────────────────────────────────────────────
R      = "\033[0m"
BOLD   = "\033[1m"
DIM    = "\033[2m"
CYAN   = "\033[36m"
YELLOW = "\033[33m"
GREEN  = "\033[32m"
BLUE   = "\033[34m"
RED    = "\033[31m"
MAGENTA= "\033[35m"
WHITE  = "\033[97m"
GREY   = "\033[90m"
BG_DARK= "\033[48;5;235m"

# ── Scenarios ─────────────────────────────────────────────────────────────────

COVER_LETTER_SCENARIOS = [
    {
        "job_title": "VP of Engineering",
        "company": "Anthropic",
        "job_description": (
            "Lead 200+ engineers building safe AI systems. "
            "Deep expertise in distributed systems, LLM infrastructure, and technical leadership required."
        ),
    },
    {
        "job_title": "Principal ML Engineer",
        "company": "OpenAI",
        "job_description": (
            "Design and scale training infrastructure for frontier models. "
            "Strong background in PyTorch, CUDA, and large-scale distributed training."
        ),
    },
    {
        "job_title": "Head of AI Product",
        "company": "Mistral AI",
        "job_description": (
            "Define the product roadmap for open-source and API offerings. "
            "Bridge technical research and commercial product strategy."
        ),
    },
]

SEARCH_SCENARIOS = [
    {"search": "Vector databases", "content": "FAISS vs Chroma vs Pinecone comparison"},
    {"search": "OpenTelemetry for LLMs", "content": "Tracing, metrics, and observability patterns"},
    {"search": "ReAct agent pattern", "content": "Implementation and best practices"},
    {"search": "DSPy framework", "content": "Automated prompt optimization techniques"},
    {"search": "Multi-agent systems", "content": "Coordination, memory, and tool use"},
]

CODE_REVIEW_SCENARIOS = [
    {
        "code": textwrap.dedent("""\
            async def fetch_data(url):
                import requests
                r = requests.get(url)
                return r.json()
        """),
        "context": "FastAPI endpoint helper",
    },
    {
        "code": textwrap.dedent("""\
            def compute_embeddings(texts):
                results = []
                for t in texts:
                    results.append(model.encode(t))
                return results
        """),
        "context": "Batch embedding pipeline",
    },
    {
        "code": textwrap.dedent("""\
            class Cache:
                def __init__(self):
                    self.data = {}
                def get(self, key):
                    return self.data[key]
                def set(self, key, value):
                    self.data[key] = value
        """),
        "context": "In-memory LRU cache stub",
    },
]


# ── Agent definitions for the demo ────────────────────────────────────────────

from pydantic import BaseModel
from core.agent_definition import AgentDefinition, MemoryPolicy, OutputSink, ImprovementPass


class CoverLetterInput(BaseModel):
    agent_type: str = "cover_letter"
    job_title: str
    company: str
    job_description: str
    session_id: str = ""


class SearchInput(BaseModel):
    agent_type: str = "search"
    search: str
    content: str
    session_id: str = ""
    history: str = ""


class CodeReviewInput(BaseModel):
    agent_type: str = "code_review"
    code: str
    context: str
    session_id: str = ""
    history: str = ""


def make_agents(model: str) -> dict:
    cover_letter_def = AgentDefinition(
        name="cover_letter",
        prompt_template=(
            "You are an expert resume writer.\n\n"
            "Write a compelling 3-paragraph cover letter for the {job_title} role at {company}.\n\n"
            "Job Description: {job_description}\n\nCover Letter:"
        ),
        input_schema=CoverLetterInput,
        llm_model=model,
        temperature=0.3,
        memory_policy=MemoryPolicy.NONE,
    )
    improve_def = AgentDefinition(
        name="cover_letter",
        prompt_template=(
            "You are an expert resume writer.\n\n"
            "Write a compelling 3-paragraph cover letter for the {job_title} role at {company}.\n\n"
            "Job Description: {job_description}\n\nCover Letter:"
        ),
        input_schema=CoverLetterInput,
        llm_model=model,
        temperature=0.3,
        memory_policy=MemoryPolicy.NONE,
        improvement_passes=[
            ImprovementPass(
                prompt_template=(
                    "Improve this cover letter to be more compelling. "
                    "Lead with a specific achievement.\n\n"
                    "Job: {job_title} at {company}\n\n"
                    "Current:\n{cover_letter}\n\nImproved:"
                ),
                output_key="cover_letter",
            )
        ],
    )
    search_def = AgentDefinition(
        name="search",
        prompt_template=(
            "You are an expert in ML and AI.\n\n"
            "Topic: {search}\nFocus: {content}\n\n"
            "Give a clear, structured explanation covering key concepts, "
            "practical applications, and trade-offs.\n\nResponse:"
        ),
        input_schema=SearchInput,
        llm_model=model,
        temperature=0.1,
        memory_policy=MemoryPolicy.NONE,
    )
    code_review_def = AgentDefinition(
        name="code_review",
        prompt_template=(
            "You are a senior software engineer.\n\n"
            "Review this code ({context}) and identify issues, suggest improvements.\n\n"
            "```python\n{code}\n```\n\nCode Review:"
        ),
        input_schema=CodeReviewInput,
        llm_model=model,
        temperature=0.0,
        memory_policy=MemoryPolicy.NONE,
    )

    from core.agent import Agent
    return {
        "cover_letter":       Agent(cover_letter_def),
        "cover_letter_multi": Agent(improve_def),
        "search":             Agent(search_def),
        "code_review":        Agent(code_review_def),
    }


# ── Dry-run mock patch ────────────────────────────────────────────────────────

def _patch_agents_dry_run(agents: dict) -> None:
    """
    Patch all adapters on already-constructed agents to return instant mock responses.
    Operates on adapter objects directly — no import reload needed.
    """
    _RESPONSE = (
        "This is a mock response demonstrating the praktor.ai agent framework. "
        "In production this would be a real LLM response from Ollama, OpenAI, or Anthropic. "
        "The monitoring layer captures tokens, cost, latency, and judge scores automatically."
    )

    async def _fake_astream(data, call_span=None):
        words = _RESPONSE.split()
        for w in words:
            yield w + " "
            await asyncio.sleep(0.001)
        if call_span is not None:
            call_span.output_tokens = len(words)

    async def _fake_ainvoke(data, call_span=None):
        await asyncio.sleep(0.05)
        if call_span is not None:
            call_span.output_tokens = len(_RESPONSE.split())
        return _RESPONSE

    for agent in agents.values():
        agent._adapter.astream = _fake_astream
        agent._adapter.ainvoke = _fake_ainvoke
        for improve_adapter, _ in agent._improvement_adapters:
            improve_adapter.astream = _fake_astream
            improve_adapter.ainvoke = _fake_ainvoke
        if agent._react_adapter:
            agent._react_adapter.astream = _fake_astream
            agent._react_adapter.ainvoke = _fake_ainvoke

    print(f"{GREY}[dry-run] LLM adapters mocked — no real Ollama calls{R}")


# ── Dashboard renderer ────────────────────────────────────────────────────────

def _bar(value: float, max_val: float, width: int = 20, color: str = GREEN) -> str:
    filled = int(width * min(value, max_val) / max_val) if max_val > 0 else 0
    return f"{color}{'█' * filled}{GREY}{'░' * (width - filled)}{R}"


def _score_color(score: float) -> str:
    if score >= 7.5:
        return GREEN
    if score >= 5.0:
        return YELLOW
    return RED


def render_dashboard(store, registry, runs_log: list[dict], kpis: list[dict], start_time: float) -> str:
    """Render the full terminal dashboard as a string."""
    elapsed = time.time() - start_time
    from monitoring.cost import format_cost

    snap_runs    = registry.runs.snapshot()
    snap_tokens  = registry.tokens.snapshot()
    snap_cost    = registry.cost_usd.snapshot()
    snap_tools   = registry.tool_calls.snapshot()

    total_runs   = sum(snap_runs.values())
    ok_runs      = sum(v for k, v in snap_runs.items() if dict(k).get("status") == "ok")
    error_runs   = total_runs - ok_runs
    total_out    = sum(v for k, v in snap_tokens.items() if dict(k).get("direction") == "output")
    total_cost   = sum(snap_cost.values())

    all_dur: list[float] = []
    for vals in registry.duration_ms.snapshot().values():
        all_dur.extend(vals)
    all_dur.sort()
    n = len(all_dur)
    avg_ms   = sum(all_dur) / n if n else 0
    p95_ms   = all_dur[max(0, int(n * 0.95) - 1)] if n else 0

    all_scores: list[float] = []
    for vals in registry.judge_score.snapshot().values():
        all_scores.extend(vals)
    avg_score = sum(all_scores) / len(all_scores) if all_scores else None

    cache_snap = registry.cache_hit_ratio.snapshot()
    avg_cache  = sum(cache_snap.values()) / len(cache_snap) if cache_snap else 0

    W = 78
    lines = []

    def box_top(title: str = "") -> str:
        if title:
            pad = W - len(title) - 4
            return f"{CYAN}╔══ {BOLD}{WHITE}{title}{R}{CYAN} {'═' * pad}╗{R}"
        return f"{CYAN}╔{'═' * (W)}╗{R}"

    def box_bot() -> str:
        return f"{CYAN}╚{'═' * W}╝{R}"

    def box_row(content: str = "") -> str:
        # Strip ANSI for width calculation
        import re
        plain = re.sub(r'\033\[[0-9;]*m', '', content)
        pad = max(0, W - len(plain) - 2)
        return f"{CYAN}║{R} {content}{' ' * pad} {CYAN}║{R}"

    # ── Header ──
    lines.append("")
    lines.append(box_top("praktor.ai — Live Monitoring Dashboard"))
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    lines.append(box_row(
        f"{GREY}Elapsed: {elapsed:.0f}s{R}   "
        f"{GREY}Prometheus:{R} {CYAN}http://localhost:8080/metrics{R}   "
        f"{GREY}Time:{R} {WHITE}{ts}{R}"
    ))
    lines.append(box_bot())
    lines.append("")

    # ── Overview stats ──
    err_color = RED if error_runs > 0 else GREEN
    lines.append(box_top("Overview"))
    lines.append(box_row(
        f"{WHITE}Runs{R}     total={BOLD}{total_runs}{R}  "
        f"ok={GREEN}{ok_runs}{R}  "
        f"error={err_color}{error_runs}{R}  "
        f"err_rate={err_color}{error_runs/total_runs:.0%}{R}" if total_runs else
        f"{WHITE}Runs{R}     {GREY}(none yet){R}"
    ))
    lines.append(box_row(
        f"{WHITE}Tokens{R}   output={BOLD}{total_out:,}{R}  "
        f"{WHITE}Cost{R}  {BOLD}{YELLOW}{format_cost(total_cost)}{R}  "
        f"{WHITE}Cache{R}  {GREEN}{avg_cache:.0%}{R} hit rate"
    ))
    if all_dur:
        lines.append(box_row(
            f"{WHITE}Latency{R}  avg={BOLD}{avg_ms:.0f}ms{R}  p95={YELLOW}{p95_ms:.0f}ms{R}  "
            f"{_bar(avg_ms, 5000, 18, CYAN)}"
        ))
    if avg_score is not None:
        sc = avg_score
        lines.append(box_row(
            f"{WHITE}Judge{R}    avg={_score_color(sc)}{BOLD}{sc:.2f}/10{R}  n={len(all_scores)}  "
            f"{_bar(sc, 10, 18, _score_color(sc))}"
        ))
    lines.append(box_bot())
    lines.append("")

    # ── Per-agent breakdown ──
    by_agent: dict[str, dict] = {}
    for k, v in snap_runs.items():
        d = dict(k)
        a = d.get("agent", "?")
        if a not in by_agent:
            by_agent[a] = {"runs": 0, "ok": 0, "tokens": 0, "cost": 0.0, "latencies": []}
        by_agent[a]["runs"] += int(v)
        if d.get("status") == "ok":
            by_agent[a]["ok"] += int(v)
    for k, v in snap_tokens.items():
        d = dict(k)
        if d.get("direction") == "output":
            a = d.get("agent", "?")
            if a in by_agent:
                by_agent[a]["tokens"] += int(v)
    for k, v in snap_cost.items():
        d = dict(k)
        a = d.get("agent", "?")
        if a in by_agent:
            by_agent[a]["cost"] += v
    for k, vals in registry.duration_ms.snapshot().items():
        d = dict(k)
        a = d.get("agent", "?")
        if a in by_agent:
            by_agent[a]["latencies"].extend(vals)

    if by_agent:
        lines.append(box_top("By Agent"))
        lines.append(box_row(
            f"{DIM}{'Agent':<20} {'Runs':>5} {'OK':>4} {'Tokens':>8}  {'Cost':<16} {'Avg ms':>7}{R}"
        ))
        for name in sorted(by_agent):
            s = by_agent[name]
            avg_lat = sum(s["latencies"]) / len(s["latencies"]) if s["latencies"] else 0
            ok_rate = s["ok"] / s["runs"] if s["runs"] else 0
            ok_col = GREEN if ok_rate == 1.0 else (YELLOW if ok_rate >= 0.8 else RED)
            lines.append(box_row(
                f"{CYAN}{name:<20}{R} {s['runs']:>5} "
                f"{ok_col}{s['ok']:>4}{R} {s['tokens']:>8,}  "
                f"{YELLOW}{format_cost(s['cost']):<16}{R} {avg_lat:>7.0f}"
            ))
        lines.append(box_bot())
        lines.append("")

    # ── Live activity log ──
    if runs_log:
        lines.append(box_top("Recent Activity"))
        for entry in runs_log[-8:]:
            status_sym = f"{GREEN}✓{R}" if entry["status"] == "ok" else f"{RED}✗{R}"
            score_str  = f"{_score_color(entry['score'])}{entry['score']:.1f}{R}" if entry.get("score") else f"{GREY}—{R}"
            lines.append(box_row(
                f"{status_sym} {CYAN}{entry['agent']:<20}{R} "
                f"{GREY}{entry['duration_ms']:>5.0f}ms{R}  "
                f"tokens={entry['tokens']:>5}  "
                f"judge={score_str}  "
                f"{DIM}{entry['label'][:22]}{R}"
            ))
        lines.append(box_bot())
        lines.append("")

    # ── Business KPIs ──
    if kpis:
        lines.append(box_top("Business KPIs"))
        for kpi in kpis[-6:]:
            tag_str = " ".join(f"{k}={v}" for k, v in (kpi.get("tags") or {}).items())
            val_col = GREEN if kpi["value"] >= 7 else (YELLOW if kpi["value"] >= 4 else RED)
            lines.append(box_row(
                f"{MAGENTA}{kpi['name']:<28}{R} "
                f"{val_col}{BOLD}{kpi['value']:>6.2f}{R}  "
                f"{GREY}{tag_str}{R}"
            ))
        lines.append(box_bot())
        lines.append("")

    # ── Footer ──
    lines.append(
        f"  {GREY}Grafana dashboard exported → {WHITE}praktor-dashboard.json{R}  "
        f"  {GREY}Ctrl+C to stop{R}"
    )
    return "\n".join(lines)


# ── Main demo loop ────────────────────────────────────────────────────────────

async def run_demo(model: str, run_judge: bool, dry_run: bool):
    # Exports Grafana JSON
    from monitoring.exporters.grafana import build_dashboard
    dashboard_path = Path(__file__).parent.parent / "praktor-dashboard.json"
    with open(dashboard_path, "w") as f:
        json.dump(build_dashboard(), f, indent=2)
    print(f"{GREEN}✓{R} Grafana dashboard exported → {WHITE}{dashboard_path}{R}")

    # Start Prometheus scrape server
    try:
        from monitoring import configure
        registry = configure(prometheus_port=8080)
        print(f"{GREEN}✓{R} Prometheus metrics scrape endpoint: {CYAN}http://localhost:8080/metrics{R}")
    except Exception as e:
        print(f"{YELLOW}⚠{R}  Prometheus server failed to start ({e}) — continuing without it")
        from monitoring.registry import get_registry
        registry = get_registry()

    from monitoring.store import MonitoringStore
    store = MonitoringStore()

    agents = make_agents(model)

    if dry_run:
        _patch_agents_dry_run(agents)

    from core.judge import JudgeEvaluator
    judge = JudgeEvaluator(model=model) if run_judge else None

    from monitoring import record_kpi

    runs_log: list[dict] = []
    kpis_log: list[dict] = []
    start_time = time.time()

    # Build task queue: mix of scenarios
    tasks = []
    for s in COVER_LETTER_SCENARIOS:
        tasks.append(("cover_letter", s, s["job_title"]))
    for s in COVER_LETTER_SCENARIOS[:1]:
        tasks.append(("cover_letter_multi", s, s["job_title"] + " (multi-pass)"))
    for s in SEARCH_SCENARIOS:
        tasks.append(("search", s, s["search"]))
    for s in CODE_REVIEW_SCENARIOS:
        tasks.append(("code_review", s, s["context"]))

    random.shuffle(tasks)

    print(f"\n{BOLD}Starting demo: {len(tasks)} tasks across 4 agent types, model={model}{R}")
    print(f"{DIM}{'─' * 70}{R}\n")

    def _clear_and_render():
        # Move cursor to top of terminal
        print("\033[2J\033[H", end="", flush=True)
        print(render_dashboard(store, registry, runs_log, kpis_log, start_time), flush=True)

    for i, (agent_name, payload, label) in enumerate(tasks, 1):
        print(f"{DIM}[{i}/{len(tasks)}] Running {agent_name}: {label[:45]}...{R}", flush=True)

        agent = agents[agent_name]
        t0 = time.time()
        response_chunks: list[str] = []
        run_error: str | None = None

        try:
            async for chunk in agent.run(payload, session_id=f"demo-{i}"):
                response_chunks.append(chunk)
        except Exception as e:
            run_error = str(e)

        duration_ms = (time.time() - t0) * 1000
        response = "".join(response_chunks)
        tokens = len(response.split())
        status = "error" if run_error else "ok"

        # Judge evaluation (optional)
        judge_score: float | None = None
        if run_judge and judge and response and not run_error:
            try:
                question = label
                score_obj = await judge.evaluate(question=question, response=response)
                judge_score = score_obj.score
                registry.record_judge(agent_name, judge_score)

                # Record KPI: quality score per agent
                record_kpi(
                    "response_quality",
                    value=judge_score,
                    tags={"agent": agent_name, "model": model},
                )
                kpis_log.append({
                    "name": "response_quality",
                    "value": judge_score,
                    "tags": {"agent": agent_name},
                })
            except Exception as e:
                print(f"{GREY}  judge skipped: {e}{R}")

        # Business KPI: simulated acceptance signal
        if agent_name.startswith("cover_letter") and not run_error:
            accepted = random.random() > 0.4  # 60% acceptance rate
            record_kpi(
                "cover_letter_submitted",
                value=1.0,
                tags={"agent": agent_name, "company": payload.get("company", "")},
            )
            if accepted:
                record_kpi(
                    "cover_letter_interview_rate",
                    value=1.0,
                    tags={"company": payload.get("company", "")},
                )
                kpis_log.append({
                    "name": "interview_rate",
                    "value": 1.0,
                    "tags": {"company": payload.get("company", "")},
                })

        runs_log.append({
            "agent":       agent_name,
            "label":       label,
            "duration_ms": duration_ms,
            "tokens":      tokens,
            "status":      status,
            "score":       judge_score,
        })

        status_sym = f"{GREEN}✓{R}" if status == "ok" else f"{RED}✗{R}"
        score_str  = f"  judge={_score_color(judge_score or 0)}{judge_score:.1f}{R}" if judge_score else ""
        print(f"  {status_sym} {duration_ms:.0f}ms  {tokens} tokens{score_str}")

        # Redraw dashboard every 3 runs
        if i % 3 == 0 or i == len(tasks):
            await asyncio.sleep(0.1)
            _clear_and_render()

    # Final dashboard render
    _clear_and_render()

    # Save final summary to SQLite and print path
    summary = await store.aggregate()
    print(f"\n{BOLD}Demo complete.{R}  {summary['total_runs']} runs recorded.")
    print(f"{GREY}SQLite store:{R} {WHITE}{store._db_path}{R}")
    print(f"{GREY}Grafana JSON:{R} {WHITE}{dashboard_path}{R}")
    print(f"\n{DIM}To view in Grafana:{R}")
    print(f"  1. Start Prometheus with praktor.ai as a scrape target")
    print(f"  2. Import praktor-dashboard.json into your Grafana instance")
    print(f"  3. Or query the SQLite store directly:")
    print(f"     {CYAN}sqlite3 {store._db_path} 'SELECT agent_type, COUNT(*), AVG(duration_ms), SUM(cost_usd) FROM agent_runs GROUP BY agent_type;'{R}")
    print()


def main():
    parser = argparse.ArgumentParser(description="praktor.ai monitoring demo")
    parser.add_argument("--model", "-m", default="llama3:8b",
                        help="Ollama model (default: llama3:8b)")
    parser.add_argument("--no-judge", action="store_true",
                        help="Skip LLM judge evaluation (faster)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Mock LLM responses — no Ollama required")
    args = parser.parse_args()

    run_judge = not args.no_judge
    asyncio.run(run_demo(args.model, run_judge, args.dry_run))


if __name__ == "__main__":
    main()
