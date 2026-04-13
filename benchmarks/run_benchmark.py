"""
praktor framework overhead benchmark.

Measures wall-clock time from dispatch entry to first yielded chunk across
three configurations:
  - baseline:       bare Ollama HTTP call (no praktor)
  - no_governance:  praktor Router, GovernancePolicy=None
  - regex_detector: praktor Router, RegexDetector pre-execution (5 entities)

Reports overhead delta vs. baseline (ms). Commits results to results.md if
--commit flag is passed.

Usage:
  python benchmarks/run_benchmark.py [--commit] [--trials N] [--warmup N]

Requires:
  - Ollama running locally (OLLAMA_URL env var, default http://localhost:11434)
  - qwen2.5 model pulled: ollama pull qwen2.5
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Add praktor to path
sys.path.insert(0, str(Path(__file__).parent.parent / "praktor"))

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
BENCH_MODEL = os.getenv("BENCH_MODEL", "qwen2.5")
BENCH_PROMPT = "Hello. Reply in one word."
RESULTS_FILE = Path(__file__).parent / "results.md"


# ---------------------------------------------------------------------------
# Baseline: bare Ollama call
# ---------------------------------------------------------------------------

async def _baseline_first_chunk_ms() -> float:
    """Time from request send to first streamed token byte. No praktor."""
    try:
        import aiohttp
    except ImportError:
        raise SystemExit("aiohttp required: pip install aiohttp")

    payload = json.dumps({
        "model": BENCH_MODEL,
        "prompt": BENCH_PROMPT,
        "stream": True,
    }).encode()

    t0 = time.perf_counter()
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{OLLAMA_URL}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
        ) as resp:
            async for line in resp.content:
                if line.strip():
                    return (time.perf_counter() - t0) * 1000
    return (time.perf_counter() - t0) * 1000


# ---------------------------------------------------------------------------
# praktor configurations
# ---------------------------------------------------------------------------

def _build_routers():
    from pydantic import BaseModel
    from core.agent_definition import AgentDefinition
    from core.router import Router
    from governance.policy import GovernancePolicy, DetectorConfig, PolicyAction

    class BenchInput(BaseModel):
        agent_type: str
        text: str
        session_id: str = ""

    # Config A: no governance
    defn_plain = AgentDefinition(
        name="bench_plain",
        prompt_template=BENCH_PROMPT,
        input_schema=BenchInput,
        llm_model=BENCH_MODEL,
    )
    router_plain = Router()
    router_plain.register(defn_plain)

    # Config B: regex detector (5 entities, pre-execution)
    policy = GovernancePolicy(
        pre_execution=[
            DetectorConfig(
                detector_class="governance.detectors.RegexDetector",
                entities=["US_SSN", "EMAIL_ADDRESS", "PHONE_NUMBER", "DATE_OF_BIRTH", "CREDIT_CARD"],
                action=PolicyAction.FLAG,
            )
        ],
    )
    defn_regex = AgentDefinition(
        name="bench_regex",
        prompt_template=BENCH_PROMPT,
        input_schema=BenchInput,
        llm_model=BENCH_MODEL,
        governance_policy=policy,
    )
    router_regex = Router()
    router_regex.register(defn_regex)

    return router_plain, router_regex, BenchInput


async def _praktor_first_chunk_ms(router, agent_type: str) -> float:
    """Time from router.dispatch() entry to first yielded chunk."""
    raw = json.dumps({"agent_type": agent_type, "text": BENCH_PROMPT}).encode()
    t0 = time.perf_counter()
    async for _ in router.dispatch(raw):
        return (time.perf_counter() - t0) * 1000
    return (time.perf_counter() - t0) * 1000


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

async def run(trials: int = 10, warmup: int = 3) -> dict[str, dict]:
    router_plain, router_regex, _ = _build_routers()

    configs = {
        "baseline": lambda: _baseline_first_chunk_ms(),
        "no_governance": lambda: _praktor_first_chunk_ms(router_plain, "bench_plain"),
        "regex_detector": lambda: _praktor_first_chunk_ms(router_regex, "bench_regex"),
    }

    results: dict[str, dict] = {}

    for name, fn in configs.items():
        print(f"\n[{name}] warming up ({warmup} reqs)...")
        for _ in range(warmup):
            try:
                await fn()
            except Exception as e:
                print(f"  warmup error: {e}")

        print(f"[{name}] timing {trials} trials...")
        samples: list[float] = []
        for i in range(trials):
            try:
                ms = await fn()
                samples.append(ms)
                print(f"  trial {i+1}: {ms:.1f}ms")
            except Exception as e:
                print(f"  trial {i+1}: ERROR {e}")

        if samples:
            results[name] = {
                "median_ms": round(statistics.median(samples), 1),
                "mean_ms": round(statistics.mean(samples), 1),
                "p90_ms": round(sorted(samples)[int(len(samples) * 0.9)], 1),
                "min_ms": round(min(samples), 1),
                "max_ms": round(max(samples), 1),
                "trials": len(samples),
            }
        else:
            results[name] = {"error": "all trials failed"}

    return results


def _format_results(results: dict) -> str:
    baseline_ms = results.get("baseline", {}).get("median_ms")
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lines = [
        f"## Benchmark results — {ts}",
        "",
        f"Model: `{BENCH_MODEL}` | Prompt: `{BENCH_PROMPT!r}`",
        "",
        "| Config | Median (ms) | P90 (ms) | Overhead vs. baseline |",
        "|--------|-------------|----------|-----------------------|",
    ]

    for name, r in results.items():
        if "error" in r:
            lines.append(f"| {name} | ERROR | — | — |")
            continue
        median = r["median_ms"]
        p90 = r["p90_ms"]
        if baseline_ms and name != "baseline":
            overhead = round(median - baseline_ms, 1)
            target = "50ms" if name == "no_governance" else "100ms"
            ok = "✓" if overhead < float(target[:-2]) else "✗"
            overhead_str = f"{overhead:+.1f}ms {ok} (target <{target})"
        else:
            overhead_str = "baseline"
        lines.append(f"| {name} | {median} | {p90} | {overhead_str} |")

    lines += [
        "",
        "Overhead = framework delta vs. bare Ollama baseline on same hardware.",
        "See [METHODOLOGY.md](METHODOLOGY.md) for details.",
        "",
    ]
    return "\n".join(lines)


def _update_results_md(content: str) -> None:
    existing = RESULTS_FILE.read_text() if RESULTS_FILE.exists() else ""
    # Prepend new results
    RESULTS_FILE.write_text(content + "\n---\n\n" + existing)
    print(f"\nResults written to {RESULTS_FILE}")


def _git_commit_results() -> None:
    try:
        subprocess.run(
            ["git", "add", str(RESULTS_FILE)],
            check=True, capture_output=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "chore: update benchmark results [ci skip]"],
            check=True, capture_output=True,
        )
        print("Results committed to git.")
    except subprocess.CalledProcessError as e:
        print(f"git commit skipped: {e.stderr.decode().strip()}")


def main():
    parser = argparse.ArgumentParser(description="praktor framework overhead benchmark")
    parser.add_argument("--commit", action="store_true", help="Commit results.md to git")
    parser.add_argument("--trials", type=int, default=10)
    parser.add_argument("--warmup", type=int, default=3)
    args = parser.parse_args()

    print(f"Running benchmark: {args.trials} trials, {args.warmup} warmup")
    print(f"Ollama URL: {OLLAMA_URL}")
    print(f"Model: {BENCH_MODEL}")

    results = asyncio.run(run(trials=args.trials, warmup=args.warmup))

    print("\n" + "=" * 60)
    formatted = _format_results(results)
    print(formatted)

    _update_results_md(formatted)

    if args.commit:
        _git_commit_results()


if __name__ == "__main__":
    main()
