"""
Prometheus metrics exporter.

Starts a lightweight HTTP server on a configurable port that serves
Prometheus text-format metrics at /metrics.

Requires:  prometheus-client>=0.20.0

All praktor metrics are prefixed with `praktor_`.

Metric catalogue:
    praktor_agent_runs_total{agent, model, status}                    counter
    praktor_tokens_total{agent, model, direction}                      counter
    praktor_cost_usd_total{agent, model}                               counter
    praktor_tool_calls_total{tool, agent, status}                      counter
    praktor_react_steps_total{agent, model}                            counter
    praktor_governance_detections_total{entity_type}                   counter
    praktor_governance_violations_total{action, entity_type}           counter
    praktor_agent_duration_ms_bucket{agent, model, le}                 histogram
    praktor_judge_score_bucket{agent, le}                              histogram
    praktor_react_step_count_bucket{agent, model, le}                  histogram
    praktor_cache_hit_ratio{agent, model}                              gauge
    praktor_judge_score_avg{agent}                                     gauge
    praktor_aigov_obligation_status{agent, obligation, enforcement_point} gauge
    praktor_kpi{name, ...tags}                                         gauge (latest value)

Usage:
    from praktor.monitoring.exporters.prometheus import start_prometheus_server
    from praktor.monitoring.registry import get_registry
    start_prometheus_server(get_registry(), port=8080)

    # Metrics then available at http://localhost:8080/metrics
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from praktor.monitoring.registry import MetricsRegistry


def start_prometheus_server(registry: "MetricsRegistry", port: int = 8080) -> None:
    """
    Start a Prometheus scrape endpoint in a background thread.

    Raises ImportError if prometheus-client is not installed.
    The server runs as a daemon thread — it stops when the main process exits.
    """
    try:
        import prometheus_client as prom
    except ImportError:
        raise ImportError(
            "prometheus-client is required for Prometheus export. "
            "Install it with: pip install prometheus-client"
        )

    # --- Define metrics ---
    runs_counter = prom.Counter(
        "praktor_agent_runs",
        "Total agent runs",
        ["agent", "model", "status"],
        registry=prom.REGISTRY,
    )
    tokens_counter = prom.Counter(
        "praktor_tokens",
        "Total tokens processed",
        ["agent", "model", "direction"],
        registry=prom.REGISTRY,
    )
    cost_counter = prom.Counter(
        "praktor_cost_usd",
        "Total cost in USD",
        ["agent", "model"],
        registry=prom.REGISTRY,
    )
    tool_counter = prom.Counter(
        "praktor_tool_calls",
        "Total tool invocations",
        ["tool", "agent", "status"],
        registry=prom.REGISTRY,
    )
    duration_hist = prom.Histogram(
        "praktor_agent_duration_ms",
        "Agent run duration in milliseconds",
        ["agent", "model"],
        buckets=[10, 50, 100, 250, 500, 1000, 2500, 5000, 10000, 30000],
        registry=prom.REGISTRY,
    )
    judge_hist = prom.Histogram(
        "praktor_judge_score",
        "LLM judge score distribution",
        ["agent"],
        buckets=[1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
        registry=prom.REGISTRY,
    )
    cache_gauge = prom.Gauge(
        "praktor_cache_hit_ratio",
        "Cache hit ratio per agent/model",
        ["agent", "model"],
        registry=prom.REGISTRY,
    )
    judge_avg_gauge = prom.Gauge(
        "praktor_judge_score_avg",
        "Rolling median judge score per agent",
        ["agent"],
        registry=prom.REGISTRY,
    )
    kpi_gauge = prom.Gauge(
        "praktor_kpi",
        "Business KPI measurements",
        ["name"],
        registry=prom.REGISTRY,
    )
    react_steps_counter = prom.Counter(
        "praktor_react_steps",
        "Total ReAct steps executed",
        ["agent", "model"],
        registry=prom.REGISTRY,
    )
    react_step_count_hist = prom.Histogram(
        "praktor_react_step_count",
        "ReAct steps per agent run",
        ["agent", "model"],
        buckets=[1, 2, 3, 5, 8, 13, 21, 34],
        registry=prom.REGISTRY,
    )
    gov_detections_counter = prom.Counter(
        "praktor_governance_detections",
        "Total governance PII/PHI detections",
        ["entity_type"],
        registry=prom.REGISTRY,
    )
    gov_violations_counter = prom.Counter(
        "praktor_governance_violations",
        "Total governance policy violations",
        ["action", "entity_type"],
        registry=prom.REGISTRY,
    )
    aigov_gauge = prom.Gauge(
        "praktor_aigov_obligation_status",
        "AIGov obligation check status (GREEN=1, AMBER=0.5, RED=0, GREY=-1)",
        ["agent", "obligation", "enforcement_point"],
        registry=prom.REGISTRY,
    )
    hitl_pending_gauge = prom.Gauge(
        "praktor_hitl_pending",
        "Number of HITL reviews currently in pending state",
        registry=prom.REGISTRY,
    )
    hitl_approval_rate_gauge = prom.Gauge(
        "praktor_hitl_approval_rate",
        "Fraction of HITL reviews approved (0-1)",
        registry=prom.REGISTRY,
    )
    prod_eval_score_gauge = prom.Gauge(
        "praktor_production_eval_score",
        "Latest AI judge score from production eval",
        ["agent"],
        registry=prom.REGISTRY,
    )

    # --- Sync thread: pushes registry state to prometheus_client objects ---
    # We override the collect() mechanism by patching the sync function
    # to map internal counters → prometheus_client metrics.

    _synced_runs: dict[tuple, float] = {}
    _synced_tokens: dict[tuple, float] = {}
    _synced_cost: dict[tuple, float] = {}
    _synced_tools: dict[tuple, float] = {}
    _synced_durations: dict[tuple, list] = {}
    _synced_scores: dict[tuple, list] = {}
    _synced_react_steps: dict[tuple, float] = {}
    _synced_react_hist: dict[tuple, list] = {}
    _synced_gov_detections: dict[tuple, float] = {}
    _synced_gov_violations: dict[tuple, float] = {}

    def _sync_once() -> None:
        """Diff internal counters against last-synced state and inc() deltas."""
        # Runs
        for k, v in registry.runs.snapshot().items():
            d = dict(k)
            prev = _synced_runs.get(k, 0.0)
            delta = v - prev
            if delta > 0:
                runs_counter.labels(
                    agent=d.get("agent", ""),
                    model=d.get("model", ""),
                    status=d.get("status", ""),
                ).inc(delta)
                _synced_runs[k] = v

        # Tokens
        for k, v in registry.tokens.snapshot().items():
            d = dict(k)
            prev = _synced_tokens.get(k, 0.0)
            delta = v - prev
            if delta > 0:
                tokens_counter.labels(
                    agent=d.get("agent", ""),
                    model=d.get("model", ""),
                    direction=d.get("direction", ""),
                ).inc(delta)
                _synced_tokens[k] = v

        # Cost
        for k, v in registry.cost_usd.snapshot().items():
            d = dict(k)
            prev = _synced_cost.get(k, 0.0)
            delta = v - prev
            if delta > 0:
                cost_counter.labels(
                    agent=d.get("agent", ""),
                    model=d.get("model", ""),
                ).inc(delta)
                _synced_cost[k] = v

        # Tool calls
        for k, v in registry.tool_calls.snapshot().items():
            d = dict(k)
            prev = _synced_tools.get(k, 0.0)
            delta = v - prev
            if delta > 0:
                tool_counter.labels(
                    tool=d.get("tool", ""),
                    agent=d.get("agent", ""),
                    status=d.get("status", ""),
                ).inc(delta)
                _synced_tools[k] = v

        # Duration histograms — observe new values since last sync
        for k, vals in registry.duration_ms.snapshot().items():
            d = dict(k)
            prev_len = len(_synced_durations.get(k, []))
            new_vals = vals[prev_len:]
            for v in new_vals:
                duration_hist.labels(
                    agent=d.get("agent", ""),
                    model=d.get("model", ""),
                ).observe(v)
            if new_vals:
                _synced_durations[k] = list(vals)

        # Judge score histograms
        for k, vals in registry.judge_score.snapshot().items():
            d = dict(k)
            prev_len = len(_synced_scores.get(k, []))
            new_vals = vals[prev_len:]
            for v in new_vals:
                judge_hist.labels(agent=d.get("agent", "")).observe(v)
            if new_vals:
                _synced_scores[k] = list(vals)

        # ReAct steps counter
        for k, v in registry.react_steps.snapshot().items():
            d = dict(k)
            prev = _synced_react_steps.get(k, 0.0)
            delta = v - prev
            if delta > 0:
                react_steps_counter.labels(
                    agent=d.get("agent", ""),
                    model=d.get("model", ""),
                ).inc(delta)
                _synced_react_steps[k] = v

        # ReAct step count histogram
        for k, vals in registry.react_step_count.snapshot().items():
            d = dict(k)
            prev_len = len(_synced_react_hist.get(k, []))
            new_vals = vals[prev_len:]
            for v in new_vals:
                react_step_count_hist.labels(
                    agent=d.get("agent", ""),
                    model=d.get("model", ""),
                ).observe(v)
            if new_vals:
                _synced_react_hist[k] = list(vals)

        # Governance detections
        for k, v in registry.governance_detections.snapshot().items():
            d = dict(k)
            prev = _synced_gov_detections.get(k, 0.0)
            delta = v - prev
            if delta > 0:
                gov_detections_counter.labels(entity_type=d.get("entity_type", "")).inc(delta)
                _synced_gov_detections[k] = v

        # Governance violations
        for k, v in registry.governance_violations.snapshot().items():
            d = dict(k)
            prev = _synced_gov_violations.get(k, 0.0)
            delta = v - prev
            if delta > 0:
                gov_violations_counter.labels(
                    action=d.get("action", ""),
                    entity_type=d.get("entity_type", ""),
                ).inc(delta)
                _synced_gov_violations[k] = v

        # AIGov obligation status gauge
        for k, v in registry.aigov_obligation.snapshot().items():
            d = dict(k)
            aigov_gauge.labels(
                agent=d.get("agent", ""),
                obligation=d.get("obligation", ""),
                enforcement_point=d.get("enforcement_point", ""),
            ).set(v)

        # Gauges — always set to current value
        for k, v in registry.cache_hit_ratio.snapshot().items():
            d = dict(k)
            cache_gauge.labels(
                agent=d.get("agent", ""),
                model=d.get("model", ""),
            ).set(v)

        for k, v in registry.judge_score_avg.snapshot().items():
            d = dict(k)
            judge_avg_gauge.labels(agent=d.get("agent", "")).set(v)

        # KPIs — in-memory observations (current process only)
        for name, observations in registry.kpi_snapshot().items():
            if observations:
                latest = observations[-1]["value"]
                kpi_gauge.labels(name=name).set(latest)

    def _sync_kpis_from_sqlite() -> None:
        """
        Read the latest KPI value for each name from SQLite MonitoringStore.

        This makes eval results (written by `python -m praktor eval` in a
        separate process) visible on the Prometheus endpoint running inside
        the consumer process — both share the same SQLite file.
        """
        if registry._store is None:
            return
        try:
            rows = registry._store._query_kpis_latest_sync()
            for name, value in rows.items():
                kpi_gauge.labels(name=name).set(value)
        except Exception:
            pass

        # Sync HITL stats from SQLite
        try:
            import asyncio
            loop = asyncio.new_event_loop()
            stats = loop.run_until_complete(registry._store.hitl_stats())
            loop.close()
            hitl_pending_gauge.set(stats.get("pending", 0))
            total = stats.get("total", 0)
            approved = stats.get("approved", 0)
            if total > 0:
                hitl_approval_rate_gauge.set(approved / total)
        except Exception:
            pass

        # Sync production eval scores per agent from latest KPI events
        try:
            rows2 = registry._store._query_kpis_latest_sync()
            for name, value in rows2.items():
                if name.startswith("production_eval.score.") and name != "production_eval.score.overall":
                    agent = name[len("production_eval.score."):]
                    prod_eval_score_gauge.labels(agent=agent).set(value)
        except Exception:
            pass

    def _background_sync_loop() -> None:
        import time
        tick = 0
        while True:
            try:
                _sync_once()
                # Sync SQLite KPIs every 30s (less frequent — disk read)
                if tick % 6 == 0:
                    _sync_kpis_from_sqlite()
                tick += 1
            except Exception:
                pass
            time.sleep(5)

    sync_thread = threading.Thread(
        target=_background_sync_loop,
        daemon=True,
        name="praktor-prom-sync",
    )
    sync_thread.start()

    # Start the Prometheus HTTP server
    prom.start_http_server(port)
