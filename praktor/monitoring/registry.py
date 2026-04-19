"""
In-memory metrics registry — thread-safe counters, histograms, and gauges.

The registry is a module-level singleton. All agent runs automatically push
data here via monitoring.collector.record_run(). Prometheus and OTel exporters
read from this registry.

Usage:
    from praktor.monitoring import configure, record_kpi

    configure(prometheus_port=8080)   # start Prometheus scrape server

    record_kpi("cover_letter_accepted", value=1, tags={"source": "linkedin"})
    record_kpi("search_quality_score", value=8.5, tags={"agent": "researcher"})
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from typing import Any

from praktor.monitoring.store import MonitoringStore, KPIRecord, RunRecord
from praktor.settings import create_log

log = create_log()

# ---------------------------------------------------------------------------
# Internal metric structures
# ---------------------------------------------------------------------------

class _Counter:
    """Monotonically increasing counter with label support."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._values: dict[tuple, float] = defaultdict(float)

    def inc(self, labels: dict[str, str] | None = None, amount: float = 1.0) -> None:
        key = tuple(sorted((labels or {}).items()))
        with self._lock:
            self._values[key] += amount

    def get(self, labels: dict[str, str] | None = None) -> float:
        key = tuple(sorted((labels or {}).items()))
        with self._lock:
            return self._values[key]

    def snapshot(self) -> dict[tuple, float]:
        with self._lock:
            return dict(self._values)


class _Histogram:
    """Rolling window histogram (last N observations per label set)."""

    _BUCKETS = (1, 5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000, float("inf"))

    def __init__(self, window: int = 1000) -> None:
        self._lock = threading.Lock()
        self._window = window
        self._values: dict[tuple, deque] = defaultdict(lambda: deque(maxlen=window))

    def observe(self, value: float, labels: dict[str, str] | None = None) -> None:
        key = tuple(sorted((labels or {}).items()))
        with self._lock:
            self._values[key].append(value)

    def quantile(self, q: float, labels: dict[str, str] | None = None) -> float | None:
        key = tuple(sorted((labels or {}).items()))
        with self._lock:
            data = sorted(self._values[key])
        if not data:
            return None
        idx = max(0, int(len(data) * q) - 1)
        return data[idx]

    def bucket_counts(self, labels: dict[str, str] | None = None) -> dict[float, int]:
        """Return {le_boundary: cumulative_count} for Prometheus histogram format."""
        key = tuple(sorted((labels or {}).items()))
        with self._lock:
            data = sorted(self._values[key])
        counts = {}
        for boundary in self._BUCKETS:
            counts[boundary] = sum(1 for v in data if v <= boundary)
        return counts

    def snapshot(self) -> dict[tuple, list]:
        with self._lock:
            return {k: list(v) for k, v in self._values.items()}


class _Gauge:
    """Current-value gauge with label support."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._values: dict[tuple, float] = defaultdict(float)

    def set(self, value: float, labels: dict[str, str] | None = None) -> None:
        key = tuple(sorted((labels or {}).items()))
        with self._lock:
            self._values[key] = value

    def get(self, labels: dict[str, str] | None = None) -> float:
        key = tuple(sorted((labels or {}).items()))
        with self._lock:
            return self._values.get(key, 0.0)

    def snapshot(self) -> dict[tuple, float]:
        with self._lock:
            return dict(self._values)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

class MetricsRegistry:
    """
    Central in-memory registry for all monitoring metrics.

    Metrics are grouped by category:
        runs          — counter per (agent, model, status)
        tokens        — counter per (agent, model, direction)
        cost_usd      — counter per (agent, model)
        duration_ms   — histogram per (agent, model)
        tool_calls    — counter per (tool, agent, status)
        judge_score   — histogram + gauge per (agent)
        cache_hits    — counter per (agent, model)
        kpis          — recent observations per name
    """

    def __init__(self, store: MonitoringStore | None = None) -> None:
        self._store = store
        self._lock = threading.Lock()

        # Counters
        self.runs = _Counter()
        self.tokens = _Counter()
        self.cost_usd = _Counter()
        self.tool_calls = _Counter()
        self.cache_hits = _Counter()
        self.react_steps = _Counter()          # per (agent, model)
        self.governance_detections = _Counter()  # per (entity_type)
        self.governance_violations = _Counter()  # per (action, entity_type)

        # Histograms
        self.duration_ms = _Histogram()
        self.judge_score = _Histogram(window=500)
        self.react_step_count = _Histogram(window=500)  # steps-per-run distribution

        # Gauges (derived, updated after each run batch)
        self.cache_hit_ratio = _Gauge()
        self.judge_score_avg = _Gauge()
        self.aigov_obligation = _Gauge()  # per (agent, obligation, enforcement_point) → 1/0.5/0/-1
        self.hitl_pending = _Gauge()      # count of pending HITL reviews
        self.hitl_approval_rate = _Gauge()  # fraction approved (0-1)
        self.production_eval_score = _Gauge()  # latest score per agent_type

        # KPI: name → deque of (timestamp, value, tags)
        self._kpis: dict[str, deque] = defaultdict(lambda: deque(maxlen=500))
        self._kpi_lock = threading.Lock()

    # ------------------------------------------------------------------
    # Record a completed run
    # ------------------------------------------------------------------

    def record_run(self, record: RunRecord) -> None:
        """Update all in-memory metrics from one RunRecord."""
        agent = record.agent_type
        model = record.model
        status = record.status

        self.runs.inc({"agent": agent, "model": model, "status": status})
        self.tokens.inc({"agent": agent, "model": model, "direction": "output"}, record.output_tokens)
        self.tokens.inc({"agent": agent, "model": model, "direction": "input"}, record.input_tokens)
        self.cost_usd.inc({"agent": agent, "model": model}, record.cost_usd)
        self.duration_ms.observe(record.duration_ms, {"agent": agent, "model": model})

        if record.cached:
            self.cache_hits.inc({"agent": agent, "model": model})

        # Update cache hit ratio gauge
        total = self.runs.get({"agent": agent, "model": model, "status": status})
        cached_count = self.cache_hits.get({"agent": agent, "model": model})
        all_runs = sum(
            v for k, v in self.runs.snapshot().items()
            if dict(k).get("agent") == agent and dict(k).get("model") == model
        )
        if all_runs > 0:
            self.cache_hit_ratio.set(cached_count / all_runs, {"agent": agent, "model": model})

        # Record tool calls and ReAct steps from trajectory
        if record.trajectory:
            step_count = 0
            for step in record.trajectory:
                if step.get("kind") == "tool_call":
                    tool = step.get("tool_name", "unknown")
                    tool_status = "error" if step.get("error") else "ok"
                    self.tool_calls.inc({"tool": tool, "agent": agent, "status": tool_status})
                if step.get("kind") in ("tool_call", "llm_call"):
                    step_count += 1
            if step_count > 0:
                self.react_steps.inc({"agent": agent, "model": model}, step_count)
                self.react_step_count.observe(step_count, {"agent": agent, "model": model})

    def record_judge(self, agent: str, score: float, version_id: str | None = None) -> None:
        """Record a judge evaluation score."""
        labels = {"agent": agent}
        if version_id:
            labels["version"] = version_id
        self.judge_score.observe(score, labels)

        # Update rolling average gauge
        p50 = self.judge_score.quantile(0.5, {"agent": agent})
        if p50 is not None:
            self.judge_score_avg.set(p50, {"agent": agent})

    _AIGOV_STATUS_NUMERIC = {"GREEN": 1.0, "PASS": 1.0, "AMBER": 0.5, "RED": 0.0, "FAIL": 0.0, "GREY": -1.0}

    def record_aigov_obligation(
        self,
        agent: str,
        obligation: str,
        enforcement_point: str,
        status: str,
    ) -> None:
        """Record AIGov obligation status as a gauge (GREEN=1, AMBER=0.5, RED=0, GREY=-1)."""
        numeric = self._AIGOV_STATUS_NUMERIC.get(status.upper(), -1.0)
        self.aigov_obligation.set(
            numeric,
            {"agent": agent, "obligation": obligation, "enforcement_point": enforcement_point},
        )

    def record_governance_detection(self, entity_type: str) -> None:
        """Increment governance detection counter."""
        self.governance_detections.inc({"entity_type": entity_type})

    def record_governance_violation(self, action: str, entity_type: str) -> None:
        """Increment governance violation counter."""
        self.governance_violations.inc({"action": action, "entity_type": entity_type})

    def record_kpi(
        self,
        name: str,
        value: float,
        tags: dict[str, str] | None = None,
    ) -> None:
        """Record a business KPI observation."""
        ts = time.time()
        with self._kpi_lock:
            self._kpis[name].append((ts, value, tags or {}))

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def kpi_snapshot(self, name: str | None = None) -> dict[str, list[dict]]:
        """Return recent KPI observations. If name is None, returns all."""
        with self._kpi_lock:
            keys = [name] if name else list(self._kpis.keys())
            return {
                k: [
                    {"timestamp": ts, "value": v, "tags": t}
                    for ts, v, t in self._kpis[k]
                ]
                for k in keys
                if k in self._kpis
            }

    def summary_text(self) -> str:
        """One-page text summary for CLI output."""
        lines = ["praktor.ai — Metrics Summary", "═" * 60]

        # Runs
        run_snap = self.runs.snapshot()
        total_runs = sum(run_snap.values())
        error_runs = sum(v for k, v in run_snap.items() if dict(k).get("status") == "error")
        ok_runs = total_runs - error_runs
        lines.append(f"\nRuns:  total={total_runs}  ok={ok_runs}  error={error_runs}  "
                     f"err_rate={error_runs/total_runs:.1%}" if total_runs else "\nRuns: (none)")

        # Tokens
        tok_snap = self.tokens.snapshot()
        total_out = sum(v for k, v in tok_snap.items() if dict(k).get("direction") == "output")
        total_in = sum(v for k, v in tok_snap.items() if dict(k).get("direction") == "input")
        lines.append(f"Tokens: input={total_in:,}  output={total_out:,}  total={total_in + total_out:,}")

        # Cost
        cost_snap = self.cost_usd.snapshot()
        total_cost = sum(cost_snap.values())
        from praktor.monitoring.cost import format_cost
        lines.append(f"Cost:   {format_cost(total_cost)} total")

        # Latency
        all_durations: list[float] = []
        for vals in self.duration_ms.snapshot().values():
            all_durations.extend(vals)
        if all_durations:
            all_sorted = sorted(all_durations)
            n = len(all_sorted)
            lines.append(
                f"Latency: p50={all_sorted[n//2]:.0f}ms  "
                f"p95={all_sorted[max(0,int(n*0.95)-1)]:.0f}ms  "
                f"p99={all_sorted[max(0,int(n*0.99)-1)]:.0f}ms"
            )

        # Judge
        all_scores: list[float] = []
        for vals in self.judge_score.snapshot().values():
            all_scores.extend(vals)
        if all_scores:
            lines.append(f"Judge:  avg={sum(all_scores)/len(all_scores):.2f}/10  n={len(all_scores)}")

        # Cache
        cache_snap = self.cache_hit_ratio.snapshot()
        if cache_snap:
            avg_cache = sum(cache_snap.values()) / len(cache_snap)
            lines.append(f"Cache:  hit_rate={avg_cache:.1%}")

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_registry: MetricsRegistry | None = None
_registry_lock = threading.Lock()


def get_registry() -> MetricsRegistry:
    """Return the global MetricsRegistry, creating it if needed."""
    global _registry
    if _registry is None:
        with _registry_lock:
            if _registry is None:
                _registry = MetricsRegistry(store=MonitoringStore())
    return _registry


def configure(
    prometheus_port: int | None = None,
    sqlite_path: str | None = None,
    otel_metrics: bool = False,
) -> MetricsRegistry:
    """
    Configure the global metrics registry and start exporters.

    Args:
        prometheus_port: If set, starts a Prometheus HTTP scrape server on this port.
        sqlite_path:     Override the SQLite database path.
        otel_metrics:    If True, sets up OTel metrics export via OTLP_ENDPOINT.

    Returns:
        The configured MetricsRegistry.
    """
    global _registry
    with _registry_lock:
        store = MonitoringStore(db_path=sqlite_path)
        _registry = MetricsRegistry(store=store)

    if prometheus_port:
        from praktor.monitoring.exporters.prometheus import start_prometheus_server
        start_prometheus_server(_registry, port=prometheus_port)
        log.info(f"Prometheus metrics available at http://localhost:{prometheus_port}/metrics")

    if otel_metrics:
        from praktor.monitoring.exporters.otel import setup_otel_metrics
        setup_otel_metrics(_registry)
        log.info("OTel metrics configured")

    return _registry


def record_kpi(
    name: str,
    value: float,
    tags: dict[str, str] | None = None,
) -> None:
    """
    Record a business KPI measurement.

    This is the primary public API for custom business metrics.

    Args:
        name:  KPI name (e.g., "cover_letter_accepted", "search_relevance")
        value: Numeric value (count, score, rate, etc.)
        tags:  Optional label dict for filtering (e.g., {"source": "linkedin"})

    Example:
        from praktor.monitoring import record_kpi
        record_kpi("cover_letter_accepted", 1, tags={"source": "linkedin"})
        record_kpi("search_quality", 8.5, tags={"agent": "researcher"})
    """
    registry = get_registry()
    registry.record_kpi(name, value, tags)

    # Persist to SQLite async-style (fire and forget)
    if registry._store:
        import asyncio
        record = KPIRecord(name=name, value=value, timestamp=time.time(), tags=tags)
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.ensure_future(registry._store.insert_kpi(record))
            else:
                loop.run_until_complete(registry._store.insert_kpi(record))
        except RuntimeError:
            # No event loop — write sync
            registry._store._insert_kpi_sync(record)
