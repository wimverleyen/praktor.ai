"""
Offline evaluation runner for general (non-clinical) agents.

Runs the GeneralJudge against the 21-sample general golden dataset
(3 samples × 7 agent types).

Usage:
    python -m praktor eval --agent cover_letter
    python -m praktor eval --agent message
    python -m praktor eval --general          # all 7 general agents

    # Programmatic:
    import asyncio
    from praktor.evaluation.general_offline_eval import run_general_eval
    report = asyncio.run(run_general_eval())
"""

from __future__ import annotations

import asyncio
import statistics
import time
from dataclasses import dataclass, field

from praktor.settings import create_log, new_request_id, MODEL

log = create_log()


@dataclass
class GeneralSampleResult:
    sample_id: str
    agent_type: str
    session_id: str
    actual_output: str
    accuracy: float
    completeness: float
    relevance: float
    conciseness: float
    clarity: float
    overall: float
    reasoning: str
    duration_ms: float
    error: str | None = None


@dataclass
class GeneralEvalReport:
    agent_type: str
    n_samples: int
    n_errors: int
    mean_overall: float
    std_overall: float
    mean_accuracy: float
    mean_completeness: float
    mean_relevance: float
    mean_conciseness: float
    mean_clarity: float
    mean_duration_ms: float
    samples: list[GeneralSampleResult] = field(default_factory=list)

    def print_summary(self) -> None:
        print(f"\n{'═'*70}")
        print(f"  General Eval Report — {self.agent_type}  ({self.n_samples} samples)")
        print(f"{'═'*70}")
        print(f"  Errors       : {self.n_errors}/{self.n_samples}")
        print(f"\n  ── Judge Scores (0–10) ─────────────────────────────")
        print(f"  Overall      : {self.mean_overall:.2f}  (σ={self.std_overall:.2f})")
        print(f"  Accuracy     : {self.mean_accuracy:.2f}")
        print(f"  Completeness : {self.mean_completeness:.2f}")
        print(f"  Relevance    : {self.mean_relevance:.2f}")
        print(f"  Conciseness  : {self.mean_conciseness:.2f}")
        print(f"  Clarity      : {self.mean_clarity:.2f}")
        print(f"\n  ── Performance ────────────────────────────────────")
        print(f"  Avg latency  : {self.mean_duration_ms/1000:.1f}s")
        print(f"{'─'*70}\n")


async def _eval_one_general(
    sample,
    agent,
    judge,
    *,
    dry_run: bool = False,
) -> GeneralSampleResult:
    session_id = f"eval-{sample.sample_id}-{new_request_id()}"
    t0 = time.monotonic()
    actual_output = ""
    error_msg = None

    if dry_run:
        actual_output = sample.reference_output
    else:
        try:
            payload = dict(sample.input_data)
            payload["agent_type"] = sample.agent_type
            payload["session_id"] = session_id
            payload.setdefault("history", "")
            chunks: list[str] = []
            async for chunk in agent.run(payload, session_id=session_id):
                chunks.append(chunk)
            actual_output = "".join(chunks)
        except Exception as e:
            error_msg = str(e)
            log.error(f"General agent run failed for {sample.sample_id}: {e}")

    duration_ms = (time.monotonic() - t0) * 1000

    score = await judge.evaluate(
        recommendation=actual_output or "[agent failed — no output]",
        member_context=sample.context,
        outcome=None,
    )

    return GeneralSampleResult(
        sample_id=sample.sample_id,
        agent_type=sample.agent_type,
        session_id=session_id,
        actual_output=actual_output,
        accuracy=score.accuracy,
        completeness=score.completeness,
        relevance=score.relevance,
        conciseness=score.conciseness,
        clarity=score.clarity,
        overall=score.overall,
        reasoning=score.reasoning,
        duration_ms=duration_ms,
        error=error_msg,
    )


async def _persist_general_results(results: list[GeneralSampleResult]) -> None:
    from praktor.monitoring.registry import get_registry
    from praktor.monitoring.store import RunRecord, JudgeEvalRecord
    from praktor.monitoring import record_kpi

    registry = get_registry()
    store = registry._store

    for r in results:
        ts = time.time()
        run = RunRecord(
            session_id=r.session_id,
            agent_type=r.agent_type,
            model=MODEL,
            timestamp=ts,
            duration_ms=r.duration_ms,
            input_tokens=0,
            output_tokens=len(r.actual_output.split()) if r.actual_output else 0,
            total_tokens=len(r.actual_output.split()) if r.actual_output else 0,
            cost_usd=0.0,
            passes=1,
            cached=False,
            error=r.error,
            status="error" if r.error else "ok",
            prompt_version="general-eval-v1",
            trajectory=[],
        )
        registry.record_run(run)
        if store:
            await store.insert_run(run)

        eval_rec = JudgeEvalRecord(
            session_id=r.session_id,
            agent_type=r.agent_type,
            judge_type="general",
            score=r.overall,
            timestamp=ts,
            version_id="general-eval-v1",
            accuracy=r.accuracy,
            completeness=r.completeness,
            relevance=r.relevance,
            conciseness=r.conciseness,
            clarity=r.clarity,
            reasoning=r.reasoning,
            question=f"golden:{r.sample_id}",
        )
        registry.record_judge(r.agent_type, r.overall)
        if store:
            await store.insert_judge_eval(eval_rec)

    if results:
        ok = [r for r in results if not r.error]
        by_agent: dict[str, list[GeneralSampleResult]] = {}
        for r in ok:
            by_agent.setdefault(r.agent_type, []).append(r)
        for atype, agent_results in by_agent.items():
            record_kpi(
                "eval.overall_score",
                statistics.mean(r.overall for r in agent_results),
                tags={"agent": atype},
            )


def _build_general_report(
    results: list[GeneralSampleResult],
    agent_type: str,
) -> GeneralEvalReport:
    ok = [r for r in results if not r.error]

    def _mean(vals: list[float]) -> float:
        return statistics.mean(vals) if vals else 0.0

    overall_vals = [r.overall for r in ok]
    return GeneralEvalReport(
        agent_type=agent_type,
        n_samples=len(results),
        n_errors=sum(1 for r in results if r.error),
        mean_overall=_mean(overall_vals),
        std_overall=statistics.stdev(overall_vals) if len(overall_vals) > 1 else 0.0,
        mean_accuracy=_mean([r.accuracy for r in ok]),
        mean_completeness=_mean([r.completeness for r in ok]),
        mean_relevance=_mean([r.relevance for r in ok]),
        mean_conciseness=_mean([r.conciseness for r in ok]),
        mean_clarity=_mean([r.clarity for r in ok]),
        mean_duration_ms=_mean([r.duration_ms for r in ok]),
        samples=results,
    )


async def run_general_eval(
    agent_type: str | None = None,
    concurrency: int = 2,
    verbose: bool = True,
    dry_run: bool = False,
) -> list[GeneralEvalReport]:
    """
    Run offline evaluation for general (non-clinical) agents.

    Args:
        agent_type:  specific agent name, or None for all 7 general agents
        concurrency: max parallel agent runs
        verbose:     print progress and report
        dry_run:     judge reference outputs without running the agent

    Returns:
        list of GeneralEvalReport (one per agent_type)
    """
    import praktor.agents  # triggers registration
    from praktor.core.router import get_global_router
    from praktor.core.agent import Agent
    from praktor.evaluation.general_golden_dataset import (
        load_general_golden_samples, GENERAL_AGENT_TYPES,
    )
    from praktor.evaluation.general_judge import GeneralJudge

    if dry_run and verbose:
        print("DRY RUN — agents skipped; reference outputs will be judged.")

    judge = GeneralJudge()
    router = get_global_router()

    types_to_run = [agent_type] if agent_type else GENERAL_AGENT_TYPES
    reports = []

    for atype in types_to_run:
        samples = load_general_golden_samples(agent_type=atype)
        if not samples:
            if verbose:
                print(f"  No golden samples for '{atype}' — skipping.")
            continue

        agent_def = None
        if not dry_run:
            agent_entry = router._agents.get(atype)
            if agent_entry is None:
                if verbose:
                    print(f"  Agent '{atype}' not registered — skipping.")
                continue
            agent_def = Agent(agent_entry.definition)

        if verbose:
            mode = "dry-run" if dry_run else "live"
            print(f"\nRunning {len(samples)} samples [{mode}] agent_type='{atype}'...")

        sem = asyncio.Semaphore(concurrency)
        results: list[GeneralSampleResult | None] = [None] * len(samples)

        async def _run_with_sem(idx: int, sample):
            async with sem:
                if verbose:
                    print(f"  [{idx+1:02d}/{len(samples)}] {sample.sample_id} — "
                          f"{sample.context[:60]}...")
                result = await _eval_one_general(sample, agent_def, judge, dry_run=dry_run)
                if verbose:
                    status = "✓" if not result.error else "✗"
                    print(f"  [{idx+1:02d}] {status} overall={result.overall:.1f} "
                          f"dur={result.duration_ms/1000:.1f}s")
                results[idx] = result

        await asyncio.gather(*(_run_with_sem(i, s) for i, s in enumerate(samples)))
        final: list[GeneralSampleResult] = [r for r in results if r is not None]

        if verbose:
            print(f"  Persisting results to MonitoringStore...")
        await _persist_general_results(final)

        report = _build_general_report(final, atype)
        if verbose:
            report.print_summary()
        reports.append(report)

    return reports


def print_general_per_sample_detail(report: GeneralEvalReport) -> None:
    print(f"\n{'─'*80}")
    print(f"  Per-Sample Detail — {report.agent_type}")
    print(f"{'─'*80}")
    header = (
        f"{'ID':<12} {'Overall':>7} {'Acc':>5} {'Comp':>5} "
        f"{'Rel':>5} {'Con':>5} {'Cla':>5} {'dur(s)':>7}  err"
    )
    print(header)
    print("─" * 80)
    for r in report.samples:
        err = r.error[:20] if r.error else ""
        print(
            f"{r.sample_id:<12} {r.overall:>7.2f} {r.accuracy:>5.1f} {r.completeness:>5.1f} "
            f"{r.relevance:>5.1f} {r.conciseness:>5.1f} {r.clarity:>5.1f} "
            f"{r.duration_ms/1000:>7.1f}  {err}"
        )
    print()
