"""
Post-production AI evaluation runner.

Automatically judges every production agent run using the same AI judges
as offline evaluation. Results are stored in MonitoringStore and pushed to
Prometheus so they appear on the Grafana dashboard.

Three execution modes:
  1. CLI one-shot:  python -m praktor eval --production
  2. Background:   ProductionEvalScheduler starts inside the consumer process
  3. After demo:   run_demo() calls this after running demo cases

Judge selection is automatic by agent_type:
  hedis_gap      → HEDISJudge       (9 criteria)
  diabetes_hedis → DiabetesHEDISJudge (10 criteria)
  other          → skipped (log warning)
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from praktor.settings import create_log, new_request_id

log = create_log()

# Judges are created once at module level to avoid repeated adapter init
_JUDGES: dict[str, Any] = {}


def _get_judge(agent_type: str):
    if agent_type not in _JUDGES:
        if agent_type == "hedis_gap":
            from praktor.clinical.evaluation.hedis_judge import HEDISJudge
            _JUDGES[agent_type] = HEDISJudge()
        elif agent_type == "diabetes_hedis":
            from praktor.clinical.evaluation.diabetes_hedis_judge import DiabetesHEDISJudge
            _JUDGES[agent_type] = DiabetesHEDISJudge()
    return _JUDGES.get(agent_type)


async def judge_run(run: dict) -> bool:
    """
    Judge one production run and persist the result.

    Args:
        run: dict from MonitoringStore.query_unjudged_runs() — must have
             session_id, agent_type, and the agent output embedded as
             the last trajectory step or fetched from session store.

    Returns True if judged, False if skipped (unsupported agent_type).
    """
    from praktor.monitoring.registry import get_registry
    from praktor.monitoring.store import JudgeEvalRecord
    from praktor.monitoring import record_kpi

    agent_type = run.get("agent_type", "")
    judge = _get_judge(agent_type)
    if judge is None:
        return False

    session_id = run["session_id"]

    # Reconstruct the agent output: look in trajectory for the final output
    output_text = _extract_output(run)
    if not output_text:
        log.debug(f"production_eval: no output found for session={session_id}, skipping")
        return False

    # Build a minimal member context from the run record
    member_context = (
        f"agent_type={agent_type} model={run.get('model','unknown')} "
        f"duration={run.get('duration_ms',0):.0f}ms "
        f"tokens={run.get('total_tokens',0)}"
    )

    try:
        score = await judge.evaluate(
            recommendation=output_text,
            member_context=member_context,
            outcome="pending",
        )
    except Exception as e:
        log.warning(f"production_eval: judge failed for session={session_id}: {e}")
        return False

    # Persist
    registry = get_registry()
    overall = score.overall
    registry.record_judge(agent_type, overall)

    judge_type = "diabetes_hedis" if agent_type == "diabetes_hedis" else "hedis"
    domain = {}
    if agent_type == "hedis_gap":
        domain = {
            "gap_identification_accuracy": getattr(score, "gap_identification_accuracy", None),
            "action_appropriateness": getattr(score, "action_appropriateness", None),
            "evidence_citation_quality": getattr(score, "evidence_citation_quality", None),
            "safety_flag_coverage": getattr(score, "safety_flag_coverage", None),
        }
    elif agent_type == "diabetes_hedis":
        domain = {
            "inertia_detection_accuracy": getattr(score, "inertia_detection_accuracy", None),
            "escalation_ladder_correctness": getattr(score, "escalation_ladder_correctness", None),
            "gap_stacking_completeness": getattr(score, "gap_stacking_completeness", None),
            "evidence_anchor_quality": getattr(score, "evidence_anchor_quality", None),
            "safety_exclusion_coverage": getattr(score, "safety_exclusion_coverage", None),
        }

    rec = JudgeEvalRecord(
        session_id=session_id,
        agent_type=agent_type,
        judge_type=judge_type,
        score=overall,
        timestamp=time.time(),
        version_id="production-eval-v1",
        accuracy=getattr(score, "accuracy", None),
        completeness=getattr(score, "completeness", None),
        relevance=getattr(score, "relevance", None),
        conciseness=getattr(score, "conciseness", None),
        clarity=getattr(score, "clarity", None),
        gap_identification_accuracy=domain.get("gap_identification_accuracy"),
        action_appropriateness=domain.get("action_appropriateness"),
        evidence_citation_quality=domain.get("evidence_citation_quality"),
        safety_flag_coverage=domain.get("safety_flag_coverage"),
        inertia_detection_accuracy=domain.get("inertia_detection_accuracy"),
        escalation_ladder_correctness=domain.get("escalation_ladder_correctness"),
        gap_stacking_completeness=domain.get("gap_stacking_completeness"),
        evidence_anchor_quality=domain.get("evidence_anchor_quality"),
        safety_exclusion_coverage=domain.get("safety_exclusion_coverage"),
        reasoning=getattr(score, "reasoning", ""),
        question=f"production:{session_id}",
    )

    if registry._store:
        await registry._store.insert_judge_eval(rec)

    # Also create HITL review record (pending)
    try:
        from praktor.monitoring.store import HITLReviewRecord
        hitl_rec = HITLReviewRecord(
            session_id=session_id,
            agent_type=agent_type,
            original_output=output_text,
            action="pending",
            judge_score_pre=overall,
        )
        if registry._store:
            await registry._store.insert_hitl_review(hitl_rec)
    except Exception as e:
        log.debug(f"HITL review insert failed (non-fatal): {e}")

    # KPI for Grafana
    record_kpi(f"production_eval.score.{agent_type}", overall, tags={"agent": agent_type})
    record_kpi("production_eval.score.overall", overall)

    log.debug(f"production_eval: session={session_id} agent={agent_type} score={overall:.2f}")
    return True


def _extract_output(run: dict) -> str:
    """Extract the agent's final output text from a run record."""
    traj = run.get("trajectory") or []
    # Walk trajectory in reverse — the last step often has the final answer
    for step in reversed(traj):
        if isinstance(step, dict):
            content = step.get("output") or step.get("content") or step.get("tool_name", "")
            if content and len(str(content)) > 20:
                return str(content)
    # Fallback: reconstruct from session_id via store
    return ""


async def run_production_eval(
    agent_type: str | None = None,
    hours: float = 24,
    limit: int = 20,
    verbose: bool = True,
) -> int:
    """
    Judge all recent unjudged production runs.

    Args:
        agent_type: filter to one agent type (None = all)
        hours:      look back this many hours (default 24)
        limit:      max runs to judge per call (default 20)
        verbose:    print progress

    Returns:
        Number of runs judged.
    """
    from praktor.monitoring.registry import get_registry

    registry = get_registry()
    if registry._store is None:
        log.warning("production_eval: no MonitoringStore, skipping")
        return 0

    runs = await registry._store.query_unjudged_runs(
        agent_type=agent_type, hours=hours, limit=limit
    )

    if verbose:
        print(f"Production eval: found {len(runs)} unjudged runs (last {hours:.0f}h)")

    judged = 0
    for run in runs:
        ok = await judge_run(run)
        if ok:
            judged += 1
            if verbose:
                print(f"  ✓ {run['session_id']} ({run['agent_type']})")

    if verbose:
        print(f"Production eval complete: {judged}/{len(runs)} judged.")
    return judged


async def run_demo(
    concurrency: int = 2,
    verbose: bool = True,
    skip_production_eval: bool = False,
) -> None:
    """
    Seed + run the 10 synthetic demo cases, then judge all outputs.

    Workflow:
      1. Seed demo members into ClinicalStore
      2. Run each agent (concurrency-limited)
      3. AI-judge every output
      4. Create HITL review records (pending)
      5. Write KPIs to MonitoringStore / Prometheus
    """
    from praktor.clinical.evaluation.demo_cases import DEMO_CASES, seed_demo_members
    from praktor.clinical.agents.hedis_gap_agent import HEDISGapDefinition
    from praktor.clinical.agents.diabetes_hedis_agent import DiabetesHEDISDefinition
    from praktor.clinical.schemas import hash_member_id
    from praktor.core.agent import Agent
    from praktor.monitoring.registry import get_registry
    from praktor.monitoring.store import RunRecord, HITLReviewRecord

    if verbose:
        print("Demo: seeding 10 synthetic members into ClinicalStore...")
    seed_demo_members()

    agents = {
        "hedis_gap": Agent(HEDISGapDefinition),
        "diabetes_hedis": Agent(DiabetesHEDISDefinition),
    }
    registry = get_registry()
    sem = asyncio.Semaphore(concurrency)

    async def _run_one(case):
        async with sem:
            mhash = hash_member_id(case.raw_member_id)
            sid = f"demo-{case.case_id}-{new_request_id()}"
            agent = agents[case.agent_type]

            if verbose:
                print(f"  [{case.case_id}] {case.description[:65]}...")

            t0 = time.monotonic()
            output = ""
            error = None
            try:
                chunks = []
                async for chunk in agent.run(
                    {"agent_type": case.agent_type, "member_id_hash": mhash,
                     "measurement_year": case.measurement_year,
                     "session_id": sid, "history": ""},
                    sid,
                ):
                    chunks.append(chunk)
                output = "".join(chunks)
            except Exception as e:
                error = str(e)
                log.error(f"demo run {case.case_id} failed: {e}")

            dur = (time.monotonic() - t0) * 1000
            out_tok = len(output.split()) if output else 0
            in_tok = out_tok * 4
            cost = (in_tok * 3.0 + out_tok * 15.0) / 1_000_000

            # Persist RunRecord
            run = RunRecord(
                session_id=sid, agent_type=case.agent_type,
                model="claude-sonnet-4-6", timestamp=time.time(),
                duration_ms=dur, input_tokens=in_tok, output_tokens=out_tok,
                total_tokens=in_tok + out_tok, cost_usd=cost,
                passes=1, cached=False, error=error,
                status="error" if error else "ok",
                prompt_version="demo-v1", trajectory=[],
            )
            registry.record_run(run)
            if registry._store:
                await registry._store.insert_run(run)

            # Judge output
            if output and not error:
                await judge_run({
                    "session_id": sid, "agent_type": case.agent_type,
                    "model": "claude-sonnet-4-6", "duration_ms": dur,
                    "total_tokens": in_tok + out_tok,
                    "trajectory": [{"output": output}],
                })

            score_str = ""
            if output:
                judge = _get_judge(case.agent_type)
                if judge:
                    try:
                        sc = await judge.evaluate(output, case.description, "pending")
                        score_str = f" score={sc.overall:.1f}"
                    except Exception:
                        pass

            if verbose:
                status = "✓" if not error else "✗"
                print(f"  [{case.case_id}] {status} dur={dur/1000:.1f}s{score_str}")

    await asyncio.gather(*(_run_one(c) for c in DEMO_CASES))

    if not skip_production_eval:
        if verbose:
            print("\nRunning production eval on demo outputs...")
        await run_production_eval(hours=0.1, limit=10, verbose=verbose)

    if verbose:
        print("\nDemo complete. HITL review queue updated.")


class ProductionEvalScheduler:
    """
    Background scheduler that judges new production runs every N minutes.

    Start inside the consumer process to continuously monitor output quality:
        scheduler = ProductionEvalScheduler(interval_minutes=15)
        scheduler.start()
    """

    def __init__(self, interval_minutes: float = 15, limit_per_run: int = 10):
        self._interval = interval_minutes * 60
        self._limit = limit_per_run
        self._thread = None
        self._stop = False

    def start(self) -> None:
        import threading
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="praktor-prod-eval"
        )
        self._thread.start()
        log.info(f"ProductionEvalScheduler started (interval={self._interval/60:.0f}min)")

    def stop(self) -> None:
        self._stop = True

    def _loop(self) -> None:
        import time as _time
        while not self._stop:
            try:
                asyncio.run(run_production_eval(hours=1, limit=self._limit, verbose=False))
            except Exception as e:
                log.warning(f"ProductionEvalScheduler error: {e}")
            _time.sleep(self._interval)
