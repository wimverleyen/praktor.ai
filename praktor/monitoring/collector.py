"""
Bridge between core.observability.Span and the MetricsRegistry.

Called from Agent.run() after span.finish():
    from monitoring.collector import record_run
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
from typing import TYPE_CHECKING

from monitoring.cost import compute_cost
from monitoring.store import RunRecord, JudgeEvalRecord
from settings import create_log

if TYPE_CHECKING:
    from core.observability import Span
    from core.agent_definition import AgentDefinition

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
        from monitoring.registry import get_registry
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


async def record_judge(
    session_id: str,
    agent_type: str,
    score_obj: Any,
    version_id: str | None = None,
) -> None:
    """
    Record a JudgeScore result.

    Args:
        session_id:  Current session identifier.
        agent_type:  Agent that produced the response.
        score_obj:   JudgeScore dataclass from core.judge.
        version_id:  Active prompt version_id (optional).
    """
    try:
        from monitoring.registry import get_registry
        from monitoring.store import JudgeEvalRecord
        registry = get_registry()

        registry.record_judge(agent_type, score_obj.score, version_id)

        if registry._store:
            record = JudgeEvalRecord(
                session_id=session_id,
                agent_type=agent_type,
                score=score_obj.score,
                timestamp=time.time(),
                version_id=version_id,
                relevance=score_obj.criteria.get("relevance"),
                accuracy=score_obj.criteria.get("accuracy"),
                completeness=score_obj.criteria.get("completeness"),
                conciseness=score_obj.criteria.get("conciseness"),
                reasoning=score_obj.reasoning,
                question=score_obj.question,
            )
            await registry._store.insert_judge_eval(record)

    except Exception as e:
        log.warning(f"monitoring.record_judge failed (non-fatal): {e}")


# For type checking only
from typing import Any
