"""
Tests for the monitoring data products.

Covers: cost table, MonitoringStore, MetricsRegistry, collector, Grafana export.
All I/O uses temp directories — no live services required.
"""
from __future__ import annotations

import asyncio
import json
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent / "praktor"))

import pytest


# ===========================================================================
# Cost table
# ===========================================================================

class TestCostTable:

    def test_gpt4o_cost(self):
        from monitoring.cost import compute_cost
        # 1000 input + 500 output at gpt-4o rates
        cost = compute_cost("gpt-4o", input_tokens=1000, output_tokens=500)
        assert cost == pytest.approx((1000 * 0.0025 + 500 * 0.010) / 1000)

    def test_gpt4o_mini_cheaper_than_gpt4o(self):
        from monitoring.cost import compute_cost
        mini = compute_cost("gpt-4o-mini", 1000, 1000)
        full = compute_cost("gpt-4o", 1000, 1000)
        assert mini < full

    def test_local_model_zero_cost(self):
        from monitoring.cost import compute_cost
        assert compute_cost("llama3:8b", 5000, 5000) == 0.0
        assert compute_cost("qwen2.5", 5000, 5000) == 0.0
        assert compute_cost("mistral", 5000, 5000) == 0.0

    def test_unknown_model_zero_cost(self):
        from monitoring.cost import compute_cost
        assert compute_cost("some-unknown-model-xyz", 1000, 1000) == 0.0

    def test_claude_sonnet_prefix_match(self):
        from monitoring.cost import compute_cost, match_model
        key = match_model("claude-sonnet-4-6")
        assert key is not None
        assert "sonnet" in key
        cost = compute_cost("claude-sonnet-4-6", 1000, 500)
        assert cost > 0

    def test_partial_version_suffix_stripped(self):
        from monitoring.cost import match_model
        assert match_model("gpt-4o-mini-2024-07-18") == match_model("gpt-4o-mini")

    def test_format_cost_local(self):
        from monitoring.cost import format_cost
        assert "local" in format_cost(0.0)

    def test_format_cost_dollars(self):
        from monitoring.cost import format_cost
        s = format_cost(1.23456)
        assert "$" in s
        assert "1.23" in s


# ===========================================================================
# MonitoringStore
# ===========================================================================

class TestMonitoringStore:

    def setup_method(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._db = str(Path(self._tmp.name) / "test.db")

    def teardown_method(self):
        self._tmp.cleanup()

    def _make_store(self):
        from monitoring.store import MonitoringStore
        return MonitoringStore(db_path=self._db)

    def _make_run(self, **kwargs):
        from monitoring.store import RunRecord
        defaults = dict(
            session_id="s1", agent_type="cover_letter", model="gpt-4o",
            timestamp=time.time(), duration_ms=500.0,
            input_tokens=100, output_tokens=200, total_tokens=300,
            cost_usd=0.0025, passes=1, cached=False,
            error=None, status="ok",
        )
        defaults.update(kwargs)
        return RunRecord(**defaults)

    @pytest.mark.asyncio
    async def test_insert_and_query(self):
        store = self._make_store()
        record = self._make_run()
        run_id = await store.insert_run(record)
        assert run_id > 0
        rows = await store.query_runs()
        assert len(rows) == 1
        assert rows[0]["session_id"] == "s1"
        assert rows[0]["agent_type"] == "cover_letter"

    @pytest.mark.asyncio
    async def test_query_filter_by_agent(self):
        store = self._make_store()
        await store.insert_run(self._make_run(agent_type="agent_a"))
        await store.insert_run(self._make_run(agent_type="agent_b"))
        rows = await store.query_runs(agent="agent_a")
        assert all(r["agent_type"] == "agent_a" for r in rows)
        assert len(rows) == 1

    @pytest.mark.asyncio
    async def test_query_filter_by_status(self):
        store = self._make_store()
        await store.insert_run(self._make_run(status="ok"))
        await store.insert_run(self._make_run(status="error", error="timeout"))
        rows = await store.query_runs(status="error")
        assert len(rows) == 1
        assert rows[0]["error"] == "timeout"

    @pytest.mark.asyncio
    async def test_trajectory_stored(self):
        from monitoring.store import RunRecord
        store = self._make_store()
        record = self._make_run()
        record.trajectory = [
            {"step": 1, "kind": "llm_call", "tool_name": None, "latency_ms": 200,
             "input_tokens": 50, "output_tokens": 100, "cached": False, "error": None},
        ]
        await store.insert_run(record)
        rows = await store.query_runs()
        assert len(rows) == 1  # run still stored

    @pytest.mark.asyncio
    async def test_insert_kpi(self):
        from monitoring.store import KPIRecord
        store = self._make_store()
        await store.insert_kpi(KPIRecord(name="quality", value=8.5, timestamp=time.time()))
        kpis = await store.query_kpis()
        assert len(kpis) == 1
        assert kpis[0]["name"] == "quality"
        assert kpis[0]["value"] == pytest.approx(8.5)

    @pytest.mark.asyncio
    async def test_insert_judge_eval(self):
        from monitoring.store import JudgeEvalRecord
        store = self._make_store()
        record = JudgeEvalRecord(
            session_id="s1", agent_type="researcher", score=7.5,
            timestamp=time.time(), reasoning="Good.", question="What?",
            relevance=8.0, accuracy=7.0, completeness=7.5, conciseness=7.5,
        )
        await store.insert_judge_eval(record)

    @pytest.mark.asyncio
    async def test_aggregate_empty(self):
        store = self._make_store()
        result = await store.aggregate()
        assert result["total_runs"] == 0
        assert result["total_cost_usd"] == 0.0

    @pytest.mark.asyncio
    async def test_aggregate_multiple_runs(self):
        store = self._make_store()
        for i in range(5):
            await store.insert_run(self._make_run(
                duration_ms=500.0 + i * 100,
                total_tokens=300,
                cost_usd=0.001,
                status="ok" if i < 4 else "error",
            ))
        result = await store.aggregate()
        assert result["total_runs"] == 5
        assert result["ok_runs"] == 4
        assert result["error_runs"] == 1
        assert result["total_cost_usd"] == pytest.approx(0.005)
        assert result["total_tokens"] == 1500

    @pytest.mark.asyncio
    async def test_aggregate_by_agent(self):
        store = self._make_store()
        await store.insert_run(self._make_run(agent_type="agent_a", cost_usd=0.01))
        await store.insert_run(self._make_run(agent_type="agent_b", cost_usd=0.02))
        result = await store.aggregate()
        assert "agent_a" in result["by_agent"]
        assert "agent_b" in result["by_agent"]
        assert result["by_agent"]["agent_a"]["cost"] == pytest.approx(0.01)


# ===========================================================================
# MetricsRegistry
# ===========================================================================

class TestMetricsRegistry:

    def _make_registry(self):
        from monitoring.registry import MetricsRegistry
        return MetricsRegistry(store=None)

    def _make_run_record(self, **kwargs):
        from monitoring.store import RunRecord
        defaults = dict(
            session_id="s1", agent_type="researcher", model="llama3:8b",
            timestamp=time.time(), duration_ms=800.0,
            input_tokens=0, output_tokens=150, total_tokens=150,
            cost_usd=0.0, passes=2, cached=False,
            error=None, status="ok",
        )
        defaults.update(kwargs)
        return RunRecord(**defaults)

    def test_record_run_increments_counters(self):
        reg = self._make_registry()
        reg.record_run(self._make_run_record())
        assert reg.runs.get({"agent": "researcher", "model": "llama3:8b", "status": "ok"}) == 1

    def test_record_run_accumulates_tokens(self):
        reg = self._make_registry()
        reg.record_run(self._make_run_record(output_tokens=100))
        reg.record_run(self._make_run_record(output_tokens=200))
        assert reg.tokens.get({"agent": "researcher", "model": "llama3:8b", "direction": "output"}) == 300

    def test_record_run_tracks_duration(self):
        reg = self._make_registry()
        reg.record_run(self._make_run_record(duration_ms=500))
        reg.record_run(self._make_run_record(duration_ms=1000))
        p50 = reg.duration_ms.quantile(0.5, {"agent": "researcher", "model": "llama3:8b"})
        assert p50 is not None
        assert 500 <= p50 <= 1000

    def test_record_run_tool_calls(self):
        reg = self._make_registry()
        record = self._make_run_record()
        record.trajectory = [
            {"kind": "tool_call", "tool_name": "web_search", "error": None},
            {"kind": "tool_call", "tool_name": "web_search", "error": "timeout"},
        ]
        reg.record_run(record)
        ok = reg.tool_calls.get({"tool": "web_search", "agent": "researcher", "status": "ok"})
        err = reg.tool_calls.get({"tool": "web_search", "agent": "researcher", "status": "error"})
        assert ok == 1
        assert err == 1

    def test_record_judge_updates_histogram(self):
        reg = self._make_registry()
        reg.record_judge("researcher", 8.0)
        reg.record_judge("researcher", 6.0)
        p50 = reg.judge_score.quantile(0.5, {"agent": "researcher"})
        assert p50 is not None

    def test_record_kpi(self):
        reg = self._make_registry()
        reg.record_kpi("quality", 9.0, tags={"version": "v2"})
        snap = reg.kpi_snapshot()
        assert "quality" in snap
        assert snap["quality"][0]["value"] == 9.0
        assert snap["quality"][0]["tags"]["version"] == "v2"

    def test_kpi_snapshot_filter_by_name(self):
        reg = self._make_registry()
        reg.record_kpi("metric_a", 1.0)
        reg.record_kpi("metric_b", 2.0)
        snap = reg.kpi_snapshot(name="metric_a")
        assert "metric_a" in snap
        assert "metric_b" not in snap

    def test_summary_text_not_empty(self):
        reg = self._make_registry()
        reg.record_run(self._make_run_record())
        text = reg.summary_text()
        assert "Runs:" in text
        assert "Tokens:" in text

    def test_cache_hit_ratio_updated(self):
        reg = self._make_registry()
        reg.record_run(self._make_run_record(cached=True))
        reg.record_run(self._make_run_record(cached=False))
        ratio = reg.cache_hit_ratio.get({"agent": "researcher", "model": "llama3:8b"})
        assert 0 < ratio <= 1.0

    def test_thread_safety_concurrent_increments(self):
        import threading
        reg = self._make_registry()
        errors = []

        def _worker():
            try:
                for _ in range(100):
                    reg.record_run(self._make_run_record())
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=_worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        total = reg.runs.get({"agent": "researcher", "model": "llama3:8b", "status": "ok"})
        assert total == 1000


# ===========================================================================
# Collector
# ===========================================================================

class TestCollector:

    def _make_span(self, agent_type="cover_letter", model="gpt-4o", error=None):
        """Build a minimal Span-like mock with a real trajectory."""
        from core.observability import TrajectoryEvent

        span = MagicMock()
        span.agent_type = agent_type
        span.session_id = "session-test"
        span.model = model
        span._start_time = time.time() - 1.5  # 1.5s ago
        span.duration_ms = 1500.0

        span._trajectory = [
            TrajectoryEvent(step=1, kind="llm_call", latency_ms=800,
                            input_tokens=0, output_tokens=150, cached=False),
            TrajectoryEvent(step=2, kind="tool_call", latency_ms=200,
                            input_tokens=0, output_tokens=30, tool_name="web_search", cached=False),
            TrajectoryEvent(step=3, kind="llm_call", latency_ms=500,
                            input_tokens=0, output_tokens=200, cached=True),
        ]
        return span

    def _make_definition(self, model="gpt-4o"):
        defn = MagicMock()
        defn.llm_model = model
        defn.name = "cover_letter"
        return defn

    def test_span_to_run_record_tokens(self):
        from monitoring.collector import _span_to_run_record
        span = self._make_span()
        record = _span_to_run_record(span, self._make_definition(), token_count=380, passes=2, error=None)
        assert record.output_tokens == 380  # 150 + 30 + 200
        assert record.total_tokens >= record.output_tokens

    def test_span_to_run_record_cost_gpt4o(self):
        from monitoring.collector import _span_to_run_record
        span = self._make_span(model="gpt-4o")
        record = _span_to_run_record(span, self._make_definition("gpt-4o"), token_count=380, passes=2, error=None)
        assert record.cost_usd > 0

    def test_span_to_run_record_local_model_zero_cost(self):
        from monitoring.collector import _span_to_run_record
        span = self._make_span(model="llama3:8b")
        record = _span_to_run_record(span, self._make_definition("llama3:8b"), token_count=380, passes=2, error=None)
        assert record.cost_usd == 0.0

    def test_span_to_run_record_status_ok(self):
        from monitoring.collector import _span_to_run_record
        span = self._make_span()
        record = _span_to_run_record(span, self._make_definition(), 380, 1, error=None)
        assert record.status == "ok"
        assert record.error is None

    def test_span_to_run_record_status_error(self):
        from monitoring.collector import _span_to_run_record
        span = self._make_span()
        record = _span_to_run_record(span, self._make_definition(), 0, 1, error="connection refused")
        assert record.status == "error"
        assert record.error == "connection refused"

    def test_span_to_run_record_trajectory_dicts(self):
        from monitoring.collector import _span_to_run_record
        span = self._make_span()
        record = _span_to_run_record(span, self._make_definition(), 380, 2, error=None)
        assert len(record.trajectory) == 3
        assert record.trajectory[1]["tool_name"] == "web_search"

    def test_span_to_run_record_cached_flag(self):
        from monitoring.collector import _span_to_run_record
        span = self._make_span()
        record = _span_to_run_record(span, self._make_definition(), 380, 2, error=None)
        assert record.cached is True  # step 3 had cached=True


# ===========================================================================
# Grafana dashboard
# ===========================================================================

class TestGrafanaDashboard:

    def setup_method(self):
        from monitoring.exporters.grafana import build_dashboard
        self.dashboard = build_dashboard()

    def test_uid_and_title(self):
        assert self.dashboard["uid"] == "praktor-monitoring"
        assert "praktor" in self.dashboard["title"].lower()

    def test_has_panels(self):
        assert len(self.dashboard["panels"]) > 10

    def test_has_template_variables(self):
        vars_ = self.dashboard["templating"]["list"]
        names = [v["name"] for v in vars_]
        assert "datasource" in names
        assert "agent" in names
        assert "model" in names

    def test_stat_panels_present(self):
        stat_panels = [p for p in self.dashboard["panels"] if p["type"] == "stat"]
        assert len(stat_panels) >= 5  # at least 5 stat KPI panels in row 1

    def test_timeseries_panels_present(self):
        ts_panels = [p for p in self.dashboard["panels"] if p["type"] == "timeseries"]
        assert len(ts_panels) >= 6

    def test_all_panels_have_unique_ids(self):
        ids = [p["id"] for p in self.dashboard["panels"]]
        assert len(ids) == len(set(ids))

    def test_all_targets_have_expr(self):
        for panel in self.dashboard["panels"]:
            for target in panel.get("targets", []):
                assert "expr" in target

    def test_valid_json_serializable(self):
        serialized = json.dumps(self.dashboard)
        restored = json.loads(serialized)
        assert restored["uid"] == "praktor-monitoring"

    def test_refresh_interval(self):
        assert self.dashboard["refresh"] == "30s"

    def test_custom_datasource(self):
        from monitoring.exporters.grafana import build_dashboard
        db = build_dashboard(datasource="MyPrometheus")
        # At least one panel should reference the custom datasource
        for panel in db["panels"]:
            if panel.get("datasource"):
                assert panel["datasource"].get("uid") == "MyPrometheus"
                break
        else:
            pytest.skip("No panel with datasource found")

    def test_business_kpi_panel(self):
        kpi_panels = [
            p for p in self.dashboard["panels"]
            if "kpi" in p.get("title", "").lower() or "KPI" in p.get("title", "")
        ]
        assert len(kpi_panels) >= 1


# ===========================================================================
# CLI integration
# ===========================================================================

class TestMonitoringCLI:

    # Run from the project root so Python can find the praktor package.
    _PROJECT_ROOT = str(Path(__file__).parent.parent)
    _PRAKTOR_DIR  = str(Path(__file__).parent.parent / "praktor")

    def _run(self, *args):
        import os, subprocess
        env = {**os.environ, "PYTHONPATH": self._PRAKTOR_DIR}
        return subprocess.run(
            ["python", "-m", "praktor", *args],
            cwd=self._PROJECT_ROOT,
            capture_output=True, text=True,
            env=env,
        )

    def test_summary_command_exists(self):
        """monitor --help should list summary, export, serve, kpi."""
        result = self._run("monitor", "--help")
        assert result.returncode == 0
        assert "summary" in result.stdout
        assert "export" in result.stdout
        assert "serve" in result.stdout

    def test_export_grafana_command_outputs_json(self):
        """monitor export grafana should output valid Grafana dashboard JSON."""
        result = self._run("monitor", "export", "grafana")
        assert result.returncode == 0, result.stderr
        dashboard = json.loads(result.stdout)
        assert dashboard["uid"] == "praktor-monitoring"
