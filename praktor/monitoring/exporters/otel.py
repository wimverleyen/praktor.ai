"""
OpenTelemetry metrics exporter.

Uses the same OTLP_ENDPOINT that trace spans use, so a single collector
(Grafana Alloy, OpenTelemetry Collector, Jaeger) receives both traces and
metrics.

Metric names follow OTel semantic conventions:
    praktor.agent.runs           UpDownCounter (int)
    praktor.agent.tokens         Counter (int)
    praktor.agent.cost_usd       Counter (float)
    praktor.agent.duration_ms    Histogram
    praktor.agent.judge_score    Histogram
    praktor.agent.cache_hits     Counter (int)
    praktor.tool.calls           Counter (int)
    praktor.kpi                  Gauge (float)

Requires: opentelemetry-sdk>=1.20.0 (already in requirements.txt)
          opentelemetry-exporter-otlp-proto-grpc (already in requirements.txt)
"""

from __future__ import annotations

import os
import threading
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from monitoring.registry import MetricsRegistry

from settings import create_log

log = create_log()


def setup_otel_metrics(registry: "MetricsRegistry") -> None:
    """
    Configure an OTel MeterProvider and start a background push loop.

    The push interval is 30 seconds (configurable via OTEL_METRIC_EXPORT_INTERVAL_MS).
    Metrics are exported via OTLP gRPC if OTLP_ENDPOINT is set, otherwise
    logs to the console.
    """
    try:
        from opentelemetry import metrics
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
        from opentelemetry.sdk.resources import Resource
    except ImportError:
        log.warning("opentelemetry-sdk not available — OTel metrics disabled")
        return

    endpoint = os.getenv("OTLP_ENDPOINT", "")
    interval_ms = int(os.getenv("OTEL_METRIC_EXPORT_INTERVAL_MS", "30000"))

    if endpoint:
        try:
            from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
            exporter = OTLPMetricExporter(endpoint=endpoint, insecure=True)
        except Exception as e:
            log.warning(f"OTel metric exporter init failed ({e}), falling back to console")
            from opentelemetry.sdk.metrics.export import ConsoleMetricExporter
            exporter = ConsoleMetricExporter()
    else:
        from opentelemetry.sdk.metrics.export import ConsoleMetricExporter
        exporter = ConsoleMetricExporter()

    resource = Resource.create({"service.name": "praktor.ai"})
    reader = PeriodicExportingMetricReader(exporter, export_interval_millis=interval_ms)
    provider = MeterProvider(resource=resource, metric_readers=[reader])
    metrics.set_meter_provider(provider)

    meter = metrics.get_meter("praktor.ai")

    # --- Instrument definitions ---
    run_counter    = meter.create_counter("praktor.agent.runs",       unit="1",  description="Total agent runs")
    token_counter  = meter.create_counter("praktor.agent.tokens",     unit="1",  description="Tokens processed")
    cost_counter   = meter.create_counter("praktor.agent.cost_usd",   unit="USD", description="Cost in USD")
    tool_counter   = meter.create_counter("praktor.tool.calls",       unit="1",  description="Tool invocations")
    cache_counter  = meter.create_counter("praktor.agent.cache_hits", unit="1",  description="Cache hits")
    duration_hist  = meter.create_histogram("praktor.agent.duration_ms", unit="ms", description="Agent run duration")
    score_hist     = meter.create_histogram("praktor.agent.judge_score", unit="1",  description="Judge score 0-10")

    # Observable gauges — read from registry snapshot at export time
    def _observe_cache(options):
        for k, v in registry.cache_hit_ratio.snapshot().items():
            d = dict(k)
            yield metrics.Observation(v, attributes={"agent": d.get("agent", ""), "model": d.get("model", "")})

    def _observe_judge_avg(options):
        for k, v in registry.judge_score_avg.snapshot().items():
            d = dict(k)
            yield metrics.Observation(v, attributes={"agent": d.get("agent", "")})

    def _observe_kpi(options):
        for name, obs in registry.kpi_snapshot().items():
            if obs:
                yield metrics.Observation(obs[-1]["value"], attributes={"name": name})

    meter.create_observable_gauge("praktor.agent.cache_hit_ratio", callbacks=[_observe_cache],
                                  unit="1", description="Cache hit ratio")
    meter.create_observable_gauge("praktor.agent.judge_score_avg", callbacks=[_observe_judge_avg],
                                  unit="1", description="Rolling median judge score")
    meter.create_observable_gauge("praktor.kpi", callbacks=[_observe_kpi],
                                  unit="1", description="Business KPIs")

    # --- Background push loop for counters and histograms ---
    _prev_runs: dict[tuple, float] = {}
    _prev_tokens: dict[tuple, float] = {}
    _prev_cost: dict[tuple, float] = {}
    _prev_tools: dict[tuple, float] = {}
    _prev_cache: dict[tuple, float] = {}
    _prev_dur_len: dict[tuple, int] = {}
    _prev_score_len: dict[tuple, int] = {}

    def _push_once() -> None:
        for k, v in registry.runs.snapshot().items():
            d = dict(k)
            prev = _prev_runs.get(k, 0.0)
            if v > prev:
                run_counter.add(int(v - prev), attributes={"agent": d.get("agent", ""), "model": d.get("model", ""), "status": d.get("status", "")})
                _prev_runs[k] = v

        for k, v in registry.tokens.snapshot().items():
            d = dict(k)
            prev = _prev_tokens.get(k, 0.0)
            if v > prev:
                token_counter.add(int(v - prev), attributes={"agent": d.get("agent", ""), "model": d.get("model", ""), "direction": d.get("direction", "")})
                _prev_tokens[k] = v

        for k, v in registry.cost_usd.snapshot().items():
            d = dict(k)
            prev = _prev_cost.get(k, 0.0)
            if v > prev:
                cost_counter.add(v - prev, attributes={"agent": d.get("agent", ""), "model": d.get("model", "")})
                _prev_cost[k] = v

        for k, v in registry.tool_calls.snapshot().items():
            d = dict(k)
            prev = _prev_tools.get(k, 0.0)
            if v > prev:
                tool_counter.add(int(v - prev), attributes={"tool": d.get("tool", ""), "agent": d.get("agent", ""), "status": d.get("status", "")})
                _prev_tools[k] = v

        for k, v in registry.cache_hits.snapshot().items():
            d = dict(k)
            prev = _prev_cache.get(k, 0.0)
            if v > prev:
                cache_counter.add(int(v - prev), attributes={"agent": d.get("agent", ""), "model": d.get("model", "")})
                _prev_cache[k] = v

        for k, vals in registry.duration_ms.snapshot().items():
            d = dict(k)
            prev_len = _prev_dur_len.get(k, 0)
            for val in vals[prev_len:]:
                duration_hist.record(val, attributes={"agent": d.get("agent", ""), "model": d.get("model", "")})
            _prev_dur_len[k] = len(vals)

        for k, vals in registry.judge_score.snapshot().items():
            d = dict(k)
            prev_len = _prev_score_len.get(k, 0)
            for val in vals[prev_len:]:
                score_hist.record(val, attributes={"agent": d.get("agent", "")})
            _prev_score_len[k] = len(vals)

    def _loop():
        push_interval = interval_ms / 1000
        while True:
            try:
                _push_once()
            except Exception:
                pass
            time.sleep(push_interval)

    t = threading.Thread(target=_loop, daemon=True, name="praktor-otel-metrics")
    t.start()
    log.info(f"OTel metrics push loop started (interval={interval_ms}ms)")
