"""
Prometheus metrics exporter.

Starts a lightweight HTTP server on a configurable port that serves
Prometheus text-format metrics at /metrics.

Requires:  prometheus-client>=0.20.0

All praktor metrics are prefixed with `praktor_`.

Metric catalogue:
    praktor_agent_runs_total{agent, model, status}          counter
    praktor_tokens_total{agent, model, direction}            counter
    praktor_cost_usd_total{agent, model}                     counter
    praktor_tool_calls_total{tool, agent, status}            counter
    praktor_agent_duration_ms_bucket{agent, model, le}       histogram
    praktor_judge_score_bucket{agent, le}                    histogram
    praktor_cache_hit_ratio{agent, model}                    gauge
    praktor_judge_score_avg{agent}                           gauge
    praktor_kpi{name, ...tags}                               gauge (latest value)

Usage:
    from monitoring.exporters.prometheus import start_prometheus_server
    from monitoring.registry import get_registry
    start_prometheus_server(get_registry(), port=8080)

    # Metrics then available at http://localhost:8080/metrics
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from monitoring.registry import MetricsRegistry


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

    # --- Sync thread: pushes registry state to prometheus_client objects ---
    # We override the collect() mechanism by patching the sync function
    # to map internal counters → prometheus_client metrics.

    _synced_runs: dict[tuple, float] = {}
    _synced_tokens: dict[tuple, float] = {}
    _synced_cost: dict[tuple, float] = {}
    _synced_tools: dict[tuple, float] = {}
    _synced_durations: dict[tuple, list] = {}
    _synced_scores: dict[tuple, list] = {}

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

        # KPIs — latest value per name
        for name, observations in registry.kpi_snapshot().items():
            if observations:
                latest = observations[-1]["value"]
                kpi_gauge.labels(name=name).set(latest)

    def _background_sync_loop() -> None:
        import time
        while True:
            try:
                _sync_once()
            except Exception as e:
                pass  # Never crash the sync thread
            time.sleep(5)  # Sync every 5s; Prometheus scrapes typically every 15s

    sync_thread = threading.Thread(
        target=_background_sync_loop,
        daemon=True,
        name="praktor-prom-sync",
    )
    sync_thread.start()

    # Start the Prometheus HTTP server
    prom.start_http_server(port)
