"""
Offline evaluation runner for clinical agents.

Runs the full eval pipeline against the 20-sample golden dataset:
  1. Seed golden members into ClinicalStore
  2. For each sample: run the agent, parse output
  3. Run AI judges (standard quality + domain-specific)
  4. Store RunRecord + JudgeEvalRecord into MonitoringStore
  5. Record KPI metrics for Grafana dashboard
  6. Print a report with all scores

Usage:
    python -m praktor eval                      # all 20 samples
    python -m praktor eval --agent hedis_gap    # 10 HEDIS samples only
    python -m praktor eval --agent diabetes_hedis

    # Programmatic:
    import asyncio
    from praktor.clinical.evaluation.offline_eval import run_offline_eval
    result = asyncio.run(run_offline_eval())
"""

from __future__ import annotations

import asyncio
import json
import statistics
import time
from dataclasses import dataclass, field
from typing import Any

from praktor.settings import create_log, new_request_id

log = create_log()


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class SampleResult:
    sample_id: str
    agent_type: str
    member_hash: str
    session_id: str
    actual_output: str
    parsed_action: str | None
    parsed_measures: list[str]
    action_correct: bool       # matches expected_action
    measures_correct: bool     # parsed ⊇ expected
    duration_ms: float
    cost_usd: float
    input_tokens: int
    output_tokens: int
    # Judge scores
    accuracy: float
    completeness: float
    relevance: float
    conciseness: float
    clarity: float
    domain_scores: dict[str, float]
    overall: float
    reasoning: str
    error: str | None = None


@dataclass
class EvalReport:
    agent_type: str
    n_samples: int
    n_errors: int
    action_accuracy: float           # fraction correct
    measure_accuracy: float
    mean_overall: float
    std_overall: float
    mean_accuracy: float
    mean_completeness: float
    mean_relevance: float
    mean_conciseness: float
    mean_clarity: float
    mean_domain: dict[str, float]
    mean_duration_ms: float
    total_cost_usd: float
    samples: list[SampleResult] = field(default_factory=list)

    def print_summary(self) -> None:
        print(f"\n{'═'*70}")
        print(f"  Offline Eval Report — {self.agent_type}  ({self.n_samples} samples)")
        print(f"{'═'*70}")
        print(f"  Errors          : {self.n_errors}/{self.n_samples}")
        print(f"  Action Accuracy : {self.action_accuracy:.1%}")
        print(f"  Measure Accuracy: {self.measure_accuracy:.1%}")
        print(f"\n  ── Judge Scores (0–10) ──────────────────────────────")
        print(f"  Overall         : {self.mean_overall:.2f}  (σ={self.std_overall:.2f})")
        print(f"  Accuracy        : {self.mean_accuracy:.2f}")
        print(f"  Completeness    : {self.mean_completeness:.2f}")
        print(f"  Relevance       : {self.mean_relevance:.2f}")
        print(f"  Conciseness     : {self.mean_conciseness:.2f}")
        print(f"  Clarity         : {self.mean_clarity:.2f}")
        for k, v in self.mean_domain.items():
            label = k.replace("_", " ").title()
            print(f"  {label:<22}: {v:.2f}")
        print(f"\n  ── Performance ──────────────────────────────────────")
        print(f"  Avg latency     : {self.mean_duration_ms/1000:.1f}s")
        print(f"  Total cost      : ${self.total_cost_usd:.4f}")
        print(f"{'─'*70}\n")


# ---------------------------------------------------------------------------
# Core eval function
# ---------------------------------------------------------------------------

async def _eval_one(sample, agent, judge, *, dry_run: bool = False) -> SampleResult:
    """
    Run one golden sample through the agent + judge.

    dry_run=True: skips the agent LLM call and evaluates the reference
    output instead. Useful for testing the eval pipeline without API calls.
    """
    from praktor.clinical.schemas import hash_member_id
    from praktor.clinical.agents.hedis_gap_agent import parse_next_best_action
    from praktor.clinical.agents.diabetes_hedis_agent import parse_diabetes_next_best_action

    member_hash = hash_member_id(sample.raw_member_id)
    session_id = f"eval-{sample.sample_id}-{new_request_id()}"

    t0 = time.monotonic()
    actual_output = ""
    error_msg = None

    if dry_run:
        actual_output = sample.reference_output
    else:
        try:
            chunks = []
            async for chunk in agent.run(
                {"agent_type": sample.agent_type, "member_id_hash": member_hash,
                 "measurement_year": sample.measurement_year, "session_id": session_id,
                 "history": ""},
                session_id,
            ):
                chunks.append(chunk)
            actual_output = "".join(chunks)
        except Exception as e:
            error_msg = str(e)
            log.error(f"Agent run failed for {sample.sample_id}: {e}")

    duration_ms = (time.monotonic() - t0) * 1000

    # Parse agent output
    parsed_action = None
    parsed_measures: list[str] = []
    if actual_output:
        try:
            if sample.agent_type == "hedis_gap":
                parsed = parse_next_best_action(actual_output, member_hash)
                parsed_action = parsed.get("action_type")
                m = parsed.get("measure_id", "")
                parsed_measures = [m] if m else []
            else:
                parsed = parse_diabetes_next_best_action(actual_output, member_hash)
                parsed_action = parsed.get("action_type")
                parsed_measures = parsed.get("measures_addressed", [])
        except Exception:
            pass

    action_correct = parsed_action == sample.expected_action
    measures_correct = all(m in parsed_measures for m in sample.expected_measures)

    # Build member context for judge
    member_context = sample.clinical_scenario

    # Run judge (instance passed in — reused across samples)
    score = await judge.evaluate(
        recommendation=actual_output or "[agent failed — no output]",
        member_context=member_context,
        outcome=sample.outcome,
    )

    # Extract domain-specific scores
    domain_keys_hedis = [
        "gap_identification_accuracy", "action_appropriateness",
        "evidence_citation_quality", "safety_flag_coverage",
    ]
    domain_keys_diabetes = [
        "inertia_detection_accuracy", "escalation_ladder_correctness",
        "gap_stacking_completeness", "evidence_anchor_quality",
        "safety_exclusion_coverage",
    ]
    domain_keys = domain_keys_diabetes if sample.agent_type == "diabetes_hedis" else domain_keys_hedis
    domain_scores = {k: getattr(score, k, 5.0) for k in domain_keys}

    # Approximate token/cost from output length (real values come from span)
    out_tokens = len(actual_output.split()) if actual_output else 0
    in_tokens = len(sample.reference_output.split()) * 3  # prompt approximation

    # Cost approximation for claude-sonnet-4-6
    cost = (in_tokens * 3.0 + out_tokens * 15.0) / 1_000_000

    return SampleResult(
        sample_id=sample.sample_id,
        agent_type=sample.agent_type,
        member_hash=member_hash,
        session_id=session_id,
        actual_output=actual_output,
        parsed_action=parsed_action,
        parsed_measures=parsed_measures,
        action_correct=action_correct,
        measures_correct=measures_correct,
        duration_ms=duration_ms,
        cost_usd=cost,
        input_tokens=in_tokens,
        output_tokens=out_tokens,
        accuracy=getattr(score, "accuracy", 5.0),
        completeness=getattr(score, "completeness", 5.0),
        relevance=getattr(score, "relevance", 5.0),
        conciseness=getattr(score, "conciseness", 5.0),
        clarity=getattr(score, "clarity", 5.0),
        domain_scores=domain_scores,
        overall=score.overall,
        reasoning=getattr(score, "reasoning", ""),
        error=error_msg,
    )


async def _persist_results(results: list[SampleResult], agent_type: str) -> None:
    """Write RunRecords, JudgeEvalRecords, and KPIs to MonitoringStore."""
    from praktor.monitoring.registry import get_registry
    from praktor.monitoring.store import RunRecord, JudgeEvalRecord
    from praktor.monitoring import record_kpi

    registry = get_registry()
    store = registry._store

    for r in results:
        ts = time.time()

        # RunRecord
        run = RunRecord(
            session_id=r.session_id,
            agent_type=r.agent_type,
            model="claude-sonnet-4-6",
            timestamp=ts,
            duration_ms=r.duration_ms,
            input_tokens=r.input_tokens,
            output_tokens=r.output_tokens,
            total_tokens=r.input_tokens + r.output_tokens,
            cost_usd=r.cost_usd,
            passes=1,
            cached=False,
            error=r.error,
            status="error" if r.error else "ok",
            prompt_version="offline-eval-v1",
            trajectory=[],
        )
        registry.record_run(run)
        if store:
            await store.insert_run(run)

        # JudgeEvalRecord
        domain = r.domain_scores
        judge_type = "diabetes_hedis" if r.agent_type == "diabetes_hedis" else "hedis"
        eval_rec = JudgeEvalRecord(
            session_id=r.session_id,
            agent_type=r.agent_type,
            judge_type=judge_type,
            score=r.overall,
            timestamp=ts,
            version_id="offline-eval-v1",
            accuracy=r.accuracy,
            completeness=r.completeness,
            relevance=r.relevance,
            conciseness=r.conciseness,
            clarity=r.clarity,
            gap_identification_accuracy=domain.get("gap_identification_accuracy"),
            action_appropriateness=domain.get("action_appropriateness"),
            evidence_citation_quality=domain.get("evidence_citation_quality"),
            safety_flag_coverage=domain.get("safety_flag_coverage"),
            inertia_detection_accuracy=domain.get("inertia_detection_accuracy"),
            escalation_ladder_correctness=domain.get("escalation_ladder_correctness"),
            gap_stacking_completeness=domain.get("gap_stacking_completeness"),
            evidence_anchor_quality=domain.get("evidence_anchor_quality"),
            safety_exclusion_coverage=domain.get("safety_exclusion_coverage"),
            reasoning=r.reasoning,
            question=f"golden:{r.sample_id}",
        )
        registry.record_judge(r.agent_type, r.overall)
        if store:
            await store.insert_judge_eval(eval_rec)

    # KPI metrics for Grafana
    ok_results = [r for r in results if not r.error]
    if ok_results:
        record_kpi("eval.action_accuracy", sum(r.action_correct for r in ok_results) / len(ok_results),
                   tags={"agent": agent_type})
        record_kpi("eval.measure_accuracy", sum(r.measures_correct for r in ok_results) / len(ok_results),
                   tags={"agent": agent_type})
        record_kpi("eval.overall_score", statistics.mean(r.overall for r in ok_results),
                   tags={"agent": agent_type})
        record_kpi("eval.accuracy_score", statistics.mean(r.accuracy for r in ok_results),
                   tags={"agent": agent_type})
        record_kpi("eval.completeness_score", statistics.mean(r.completeness for r in ok_results),
                   tags={"agent": agent_type})
        record_kpi("eval.relevance_score", statistics.mean(r.relevance for r in ok_results),
                   tags={"agent": agent_type})
        record_kpi("eval.conciseness_score", statistics.mean(r.conciseness for r in ok_results),
                   tags={"agent": agent_type})
        record_kpi("eval.clarity_score", statistics.mean(r.clarity for r in ok_results),
                   tags={"agent": agent_type})


def _build_report(samples_list: list, results: list[SampleResult], agent_type: str) -> EvalReport:
    ok = [r for r in results if not r.error]
    n_errors = sum(1 for r in results if r.error)

    def _mean(vals):
        return statistics.mean(vals) if vals else 0.0

    overall_vals = [r.overall for r in ok]
    domain_keys = (
        ["inertia_detection_accuracy", "escalation_ladder_correctness",
         "gap_stacking_completeness", "evidence_anchor_quality", "safety_exclusion_coverage"]
        if agent_type == "diabetes_hedis" else
        ["gap_identification_accuracy", "action_appropriateness",
         "evidence_citation_quality", "safety_flag_coverage"]
    )

    return EvalReport(
        agent_type=agent_type,
        n_samples=len(results),
        n_errors=n_errors,
        action_accuracy=_mean([r.action_correct for r in ok]),
        measure_accuracy=_mean([r.measures_correct for r in ok]),
        mean_overall=_mean(overall_vals),
        std_overall=statistics.stdev(overall_vals) if len(overall_vals) > 1 else 0.0,
        mean_accuracy=_mean([r.accuracy for r in ok]),
        mean_completeness=_mean([r.completeness for r in ok]),
        mean_relevance=_mean([r.relevance for r in ok]),
        mean_conciseness=_mean([r.conciseness for r in ok]),
        mean_clarity=_mean([r.clarity for r in ok]),
        mean_domain={k: _mean([r.domain_scores.get(k, 0.0) for r in ok]) for k in domain_keys},
        mean_duration_ms=_mean([r.duration_ms for r in ok]),
        total_cost_usd=sum(r.cost_usd for r in results),
        samples=results,
    )


async def run_offline_eval(
    agent_type: str | None = None,
    concurrency: int = 2,
    verbose: bool = True,
    dry_run: bool = False,
) -> list[EvalReport]:
    """
    Run the full offline evaluation pipeline.

    Args:
        agent_type:  "hedis_gap" | "diabetes_hedis" | None (both)
        concurrency: max parallel agent runs (default 2 — API rate limits)
        verbose:     print progress + final report
        dry_run:     evaluate reference outputs instead of running agents.
                     Use this to test the pipeline without LLM agent calls
                     (judges still run — ANTHROPIC_API_KEY still needed).

    Returns:
        list of EvalReport (one per agent_type evaluated)
    """
    from praktor.clinical.evaluation.golden_dataset import load_golden_samples, seed_golden_members
    from praktor.clinical.agents.hedis_gap_agent import HEDISGapDefinition
    from praktor.clinical.agents.diabetes_hedis_agent import DiabetesHEDISDefinition
    from praktor.clinical.evaluation.hedis_judge import HEDISJudge
    from praktor.clinical.evaluation.diabetes_hedis_judge import DiabetesHEDISJudge
    from praktor.clinical.evaluation.judge_optimizer import (
        create_calibrated_judge, ensure_judges_calibrated,
    )
    from praktor.core.agent import Agent

    if dry_run and verbose:
        print("DRY RUN — agents skipped; reference outputs will be judged.")

    # 0. Auto-calibrate judges if no active calibrated version exists
    await ensure_judges_calibrated(
        agent_type=agent_type,
        verbose=verbose,
    )

    # 1. Seed all golden members into the clinical store
    if verbose:
        print("Seeding golden members into ClinicalStore...")
    seed_golden_members()

    # 2. Build agent + judge map — load calibrated prompts from PromptRegistry
    agent_map = {
        "hedis_gap": (Agent(HEDISGapDefinition), create_calibrated_judge(HEDISJudge, "hedis_gap")),
        "diabetes_hedis": (Agent(DiabetesHEDISDefinition), create_calibrated_judge(DiabetesHEDISJudge, "diabetes_hedis")),
    }

    types_to_run = [agent_type] if agent_type else ["hedis_gap", "diabetes_hedis"]
    reports = []

    for atype in types_to_run:
        agent_obj, judge = agent_map[atype]
        samples = load_golden_samples(agent_type=atype)

        if verbose:
            mode = "dry-run" if dry_run else "live"
            print(f"\nRunning {len(samples)} samples [{mode}] agent_type='{atype}'...")

        # 3. Run with limited concurrency (API rate limits)
        semaphore = asyncio.Semaphore(concurrency)
        results: list[SampleResult | None] = [None] * len(samples)

        async def _run_with_sem(idx: int, sample):
            async with semaphore:
                if verbose:
                    print(f"  [{idx+1:02d}/{len(samples)}] {sample.sample_id} — "
                          f"{sample.clinical_scenario[:60]}...")
                result = await _eval_one(sample, agent_obj, judge, dry_run=dry_run)
                if verbose:
                    status = "✓" if not result.error else "✗"
                    action_ok = "✓" if result.action_correct else "✗"
                    print(f"  [{idx+1:02d}] {status} overall={result.overall:.1f} "
                          f"action={action_ok}({result.parsed_action}) "
                          f"dur={result.duration_ms/1000:.1f}s")
                results[idx] = result

        await asyncio.gather(*(_run_with_sem(i, s) for i, s in enumerate(samples)))
        final_results: list[SampleResult] = [r for r in results if r is not None]

        # 4. Persist to monitoring store
        if verbose:
            print(f"  Persisting results to MonitoringStore...")
        await _persist_results(final_results, atype)

        # 5. Build report
        report = _build_report(samples, final_results, atype)
        if verbose:
            report.print_summary()

        reports.append(report)

    return reports


def print_per_sample_detail(report: EvalReport) -> None:
    """Print a detailed per-sample table."""
    print(f"\n{'─'*90}")
    print(f"  Per-Sample Detail — {report.agent_type}")
    print(f"{'─'*90}")
    header = f"{'ID':<8} {'Action':5} {'Meas':5} {'Overall':7} {'Acc':5} {'Comp':5} {'Rel':5} {'Con':5} {'Cla':5} {'dur(s)':7} {'err'}"
    print(header)
    print("─" * 90)
    for r in report.samples:
        ac = "✓" if r.action_correct else "✗"
        mc = "✓" if r.measures_correct else "✗"
        err = r.error[:20] if r.error else ""
        print(f"{r.sample_id:<8} {ac:<5} {mc:<5} {r.overall:7.2f} "
              f"{r.accuracy:5.1f} {r.completeness:5.1f} {r.relevance:5.1f} "
              f"{r.conciseness:5.1f} {r.clarity:5.1f} "
              f"{r.duration_ms/1000:7.1f} {err}")
    print()
