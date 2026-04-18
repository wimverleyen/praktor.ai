"""
Bridge between core.observability.Span and the MetricsRegistry.

Called from Agent.run() after span.finish():
    from praktor.monitoring.collector import record_run
    await record_run(span, definition, token_count, passes)

This module handles:
- Converting a Span + trajectory into a RunRecord
- Computing cost from token counts + model
- Pushing the RunRecord to both in-memory registry and SQLite store
- Persisting judge evaluations when available
"""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, Any

from praktor.monitoring.cost import compute_cost
from praktor.monitoring.store import RunRecord, JudgeEvalRecord
from praktor.settings import create_log

if TYPE_CHECKING:
    from praktor.core.observability import Span
    from praktor.core.agent_definition import AgentDefinition

log = create_log()


def _span_to_run_record(
    span: "Span",
    definition: "AgentDefinition",
    token_count: int,
    passes: int,
    error: str | None,
    prompt_version: str | None = None,
) -> RunRecord:
    """
    Convert an observability Span into a persisted RunRecord.

    Token counting:
        output_tokens = sum of trajectory event output_tokens
        input_tokens  = estimated from trajectory input_tokens (often 0 from
                        local models; use word-count approximation as fallback)

    Cost is computed from the model pricing table.
    """
    trajectory = span._trajectory  # list[TrajectoryEvent]

    output_tokens = sum(e.output_tokens for e in trajectory)
    input_tokens = sum(e.input_tokens for e in trajectory)

    # Fallback: estimate from total word count if no input token data
    if input_tokens == 0 and token_count > output_tokens:
        input_tokens = max(0, token_count - output_tokens)

    total_tokens = input_tokens + output_tokens
    if total_tokens == 0:
        total_tokens = token_count  # use the word-split approximation

    cost = compute_cost(definition.llm_model, input_tokens, output_tokens)

    traj_dicts = [
        {
            "step": e.step,
            "kind": e.kind,
            "tool_name": e.tool_name,
            "latency_ms": e.latency_ms,
            "input_tokens": e.input_tokens,
            "output_tokens": e.output_tokens,
            "cached": e.cached,
            "error": e.error,
        }
        for e in trajectory
    ]

    any_cached = any(e.cached for e in trajectory)

    return RunRecord(
        session_id=span.session_id,
        agent_type=span.agent_type,
        model=span.model,
        timestamp=span._start_time,
        duration_ms=round(span.duration_ms, 2),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        cost_usd=cost,
        passes=passes,
        cached=any_cached,
        error=error,
        status="error" if error else "ok",
        prompt_version=prompt_version,
        trajectory=traj_dicts,
    )


async def record_run(
    span: "Span",
    definition: "AgentDefinition",
    token_count: int = 0,
    passes: int = 1,
    error: str | None = None,
    prompt_version: str | None = None,
) -> None:
    """
    Persist and register a completed agent run. Non-blocking.

    Called from Agent.run() via asyncio.create_task() — runs concurrently
    with the response stream so it never adds latency to the agent.

    Args:
        span:           The finished Span object (trajectory already recorded).
        definition:     The AgentDefinition that executed.
        token_count:    Total approximate token count (word-split).
        passes:         Number of LLM passes executed.
        error:          Error message if the run failed, else None.
        prompt_version: Active prompt version_id at run time (optional).
    """
    try:
        from praktor.monitoring.registry import get_registry
        registry = get_registry()

        record = _span_to_run_record(
            span, definition, token_count, passes, error, prompt_version
        )

        # 1. Update in-memory metrics
        registry.record_run(record)

        # 2. Persist to SQLite
        if registry._store:
            await registry._store.insert_run(record)

        log.debug(
            f"monitoring.record_run: agent={span.agent_type} "
            f"tokens={record.total_tokens} cost={record.cost_usd:.6f} "
            f"duration={record.duration_ms:.0f}ms"
        )

    except Exception as e:
        log.warning(f"monitoring.record_run failed (non-fatal): {e}")


def _score_field(score_obj: Any, field: str) -> float | None:
    """
    Extract a named criterion from either score API:
      - old JudgeScore:              score_obj.criteria.get(field)
      - new ClinicalJudgeScore etc.: getattr(score_obj, field, None)
    """
    if hasattr(score_obj, "criteria") and isinstance(score_obj.criteria, dict):
        return score_obj.criteria.get(field)
    return getattr(score_obj, field, None)


def _overall_score(score_obj: Any) -> float:
    """
    Extract overall score from either score API:
      - old JudgeScore:  score_obj.score
      - new dataclasses: score_obj.overall
    """
    if hasattr(score_obj, "score"):
        return float(score_obj.score or 0.0)
    return float(getattr(score_obj, "overall", 0.0))


async def record_judge(
    session_id: str,
    agent_type: str,
    score_obj: Any,
    version_id: str | None = None,
    judge_type: str = "general",
) -> None:
    """
    Record a judge evaluation result.

    Accepts both the legacy JudgeScore (core.judge) and the new
    ClinicalJudgeScore / DiabetesJudgeScore dataclasses.
    """
    try:
        from praktor.monitoring.registry import get_registry
        from praktor.monitoring.store import JudgeEvalRecord
        registry = get_registry()

        overall = _overall_score(score_obj)
        registry.record_judge(agent_type, overall, version_id)

        if registry._store:
            record = JudgeEvalRecord(
                session_id=session_id,
                agent_type=agent_type,
                judge_type=judge_type,
                score=overall,
                timestamp=time.time(),
                version_id=version_id,
                accuracy=_score_field(score_obj, "accuracy"),
                completeness=_score_field(score_obj, "completeness"),
                relevance=_score_field(score_obj, "relevance"),
                conciseness=_score_field(score_obj, "conciseness"),
                clarity=_score_field(score_obj, "clarity"),
                # HEDIS clinical extensions
                gap_identification_accuracy=_score_field(score_obj, "gap_identification_accuracy"),
                action_appropriateness=_score_field(score_obj, "action_appropriateness"),
                evidence_citation_quality=_score_field(score_obj, "evidence_citation_quality"),
                safety_flag_coverage=_score_field(score_obj, "safety_flag_coverage"),
                # Diabetes extensions
                inertia_detection_accuracy=_score_field(score_obj, "inertia_detection_accuracy"),
                escalation_ladder_correctness=_score_field(score_obj, "escalation_ladder_correctness"),
                gap_stacking_completeness=_score_field(score_obj, "gap_stacking_completeness"),
                evidence_anchor_quality=_score_field(score_obj, "evidence_anchor_quality"),
                safety_exclusion_coverage=_score_field(score_obj, "safety_exclusion_coverage"),
                reasoning=getattr(score_obj, "reasoning", ""),
                question=getattr(score_obj, "question", ""),
            )
            await registry._store.insert_judge_eval(record)

    except Exception as e:
        log.warning(f"monitoring.record_judge failed (non-fatal): {e}")
