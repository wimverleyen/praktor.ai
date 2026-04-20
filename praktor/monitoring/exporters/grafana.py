"""
Grafana dashboard JSON builder.

Generates a production-ready Grafana 10+ dashboard with 9 rows and 40 panels
covering all praktor monitoring dimensions that produce real data.

Usage:
    from praktor.monitoring.exporters.grafana import build_dashboard
    import json
    print(json.dumps(build_dashboard(), indent=2))

    # CLI:
    python -m praktor monitor export grafana > monitoring/grafana-dashboard.json
    # Then: docker compose up  (auto-provisioned) or Grafana → Import → Upload JSON

Dashboard structure:
    Row 1: Overview          — total runs, success rate, cost, avg latency, judge score, error rate
    Row 2: Traffic           — run rate by agent, token rate (input vs output)
    Row 3: Performance       — latency percentiles, cost by model
    Row 4: Quality           — judge score distribution, judge score avg by agent
    Row 5: AIGov Compliance  — obligation status by agent, business KPIs
    Row 6: Offline Eval      — per-criterion stat panels (accuracy, completeness, relevance, conciseness, clarity)
    Row 7: Judge Calibration — score before/after, calibration delta, actual vs required sample count,
                               per-criterion trend over time
    Row 8: Production Eval   — score by agent over time, overall score, demo runs judged
    Row 9: HITL Review       — pending queue, approval rate, queue trend
"""

from __future__ import annotations

import json
from typing import Any


def build_dashboard(
    datasource: str = "${datasource}",
    title: str = "praktor.ai — Agent Monitoring",
    uid: str = "praktor-monitoring",
    refresh: str = "30s",
) -> dict[str, Any]:
    """
    Build a complete Grafana dashboard dict.

    Args:
        datasource: Grafana datasource name or variable reference.
        title:      Dashboard title.
        uid:        Unique dashboard identifier (used for linking).
        refresh:    Auto-refresh interval.

    Returns:
        Dict that can be serialized to JSON and imported into Grafana.
    """
    panels = []
    _id = _counter()

    # ----------------------------------------------------------------
    # Row 1: Overview stats (6 stat panels, each w=4)
    # ----------------------------------------------------------------
    panels.append(_row(next(_id), "Overview", y=0))

    panels.append(_stat(
        next(_id), "Total Runs (24h)",
        expr=f'sum(increase(praktor_agent_runs_total{{agent=~"$agent",model=~"$model"}}[24h]))',
        datasource=datasource, x=0, y=1, w=4, h=4,
        color_mode="background",
        thresholds=[{"color": "blue", "value": None}],
        unit="short",
    ))
    panels.append(_stat(
        next(_id), "Success Rate (24h)",
        expr=(
            f'1 - clamp_min('
            f'sum(rate(praktor_agent_runs_total{{agent=~"$agent",model=~"$model",status="error"}}[24h]))'
            f' / sum(rate(praktor_agent_runs_total{{agent=~"$agent",model=~"$model"}}[24h])), 0)'
        ),
        datasource=datasource, x=4, y=1, w=4, h=4,
        color_mode="background",
        thresholds=[
            {"color": "red", "value": None},
            {"color": "yellow", "value": 0.90},
            {"color": "green", "value": 0.99},
        ],
        unit="percentunit",
    ))
    panels.append(_stat(
        next(_id), "Total Cost USD (24h)",
        expr=f'sum(increase(praktor_cost_usd_total{{agent=~"$agent",model=~"$model"}}[24h]))',
        datasource=datasource, x=8, y=1, w=4, h=4,
        color_mode="background",
        thresholds=[
            {"color": "green", "value": None},
            {"color": "yellow", "value": 1.0},
            {"color": "red", "value": 5.0},
        ],
        unit="currencyUSD",
        decimals=4,
    ))
    panels.append(_stat(
        next(_id), "Avg Latency (24h)",
        expr=(
            f'sum(rate(praktor_agent_duration_ms_sum{{agent=~"$agent",model=~"$model"}}[24h]))'
            f' / sum(rate(praktor_agent_duration_ms_count{{agent=~"$agent",model=~"$model"}}[24h]))'
        ),
        datasource=datasource, x=12, y=1, w=4, h=4,
        color_mode="background",
        thresholds=[
            {"color": "green", "value": None},
            {"color": "yellow", "value": 5000},
            {"color": "red", "value": 15000},
        ],
        unit="ms",
    ))
    panels.append(_stat(
        next(_id), "Avg Judge Score (24h)",
        expr=f'avg(praktor_judge_score_avg{{agent=~"$agent"}})',
        datasource=datasource, x=16, y=1, w=4, h=4,
        color_mode="background",
        thresholds=[
            {"color": "red", "value": None},
            {"color": "yellow", "value": 5},
            {"color": "green", "value": 7},
        ],
        unit="short",
        decimals=1,
    ))
    panels.append(_stat(
        next(_id), "Error Rate (24h)",
        expr=(
            f'sum(rate(praktor_agent_runs_total{{agent=~"$agent",model=~"$model",status="error"}}[24h]))'
            f' / sum(rate(praktor_agent_runs_total{{agent=~"$agent",model=~"$model"}}[24h]))'
        ),
        datasource=datasource, x=20, y=1, w=4, h=4,
        color_mode="background",
        thresholds=[
            {"color": "green", "value": None},
            {"color": "yellow", "value": 0.01},
            {"color": "red", "value": 0.05},
        ],
        unit="percentunit",
    ))

    # ----------------------------------------------------------------
    # Row 2: Traffic
    # ----------------------------------------------------------------
    panels.append(_row(next(_id), "Traffic", y=6))

    panels.append(_timeseries(
        next(_id), "Run Rate by Agent",
        exprs=[{
            "expr": f'sum by(agent) (rate(praktor_agent_runs_total{{agent=~"$agent",model=~"$model"}}[$__rate_interval]))',
            "legendFormat": "{{agent}}",
        }],
        datasource=datasource, x=0, y=7, w=12, h=8,
        unit="reqps",
    ))
    panels.append(_timeseries(
        next(_id), "Token Throughput: Input vs Output",
        exprs=[
            {
                "expr": f'sum(rate(praktor_tokens_total{{agent=~"$agent",model=~"$model",direction="input"}}[$__rate_interval]))',
                "legendFormat": "input tokens/s",
            },
            {
                "expr": f'sum(rate(praktor_tokens_total{{agent=~"$agent",model=~"$model",direction="output"}}[$__rate_interval]))',
                "legendFormat": "output tokens/s",
            },
        ],
        datasource=datasource, x=12, y=7, w=12, h=8,
        unit="short",
        stacking=True,
    ))

    # ----------------------------------------------------------------
    # Row 3: Performance
    # ----------------------------------------------------------------
    panels.append(_row(next(_id), "Performance", y=16))

    panels.append(_timeseries(
        next(_id), "Latency by Agent (P50 / P95 / P99)",
        exprs=[
            {
                "expr": f'histogram_quantile(0.50, sum by(le,agent) (rate(praktor_agent_duration_ms_bucket{{agent=~"$agent",model=~"$model"}}[$__rate_interval])))',
                "legendFormat": "p50 {{agent}}",
            },
            {
                "expr": f'histogram_quantile(0.95, sum by(le,agent) (rate(praktor_agent_duration_ms_bucket{{agent=~"$agent",model=~"$model"}}[$__rate_interval])))',
                "legendFormat": "p95 {{agent}}",
            },
            {
                "expr": f'histogram_quantile(0.99, sum by(le,agent) (rate(praktor_agent_duration_ms_bucket{{agent=~"$agent",model=~"$model"}}[$__rate_interval])))',
                "legendFormat": "p99 {{agent}}",
            },
        ],
        datasource=datasource, x=0, y=17, w=12, h=8,
        unit="ms",
    ))
    panels.append(_timeseries(
        next(_id), "Cost by Model (per hour)",
        exprs=[{
            "expr": f'sum by(model) (increase(praktor_cost_usd_total{{agent=~"$agent"}}[1h]))',
            "legendFormat": "{{model}}",
        }],
        datasource=datasource, x=12, y=17, w=12, h=8,
        unit="currencyUSD",
    ))

    # ----------------------------------------------------------------
    # Row 4: Quality
    # ----------------------------------------------------------------
    panels.append(_row(next(_id), "Quality", y=26))

    panels.append(_timeseries(
        next(_id), "Judge Score Distribution (P25 / P50 / P75)",
        exprs=[
            {
                "expr": f'histogram_quantile(0.25, sum by(le,agent) (rate(praktor_judge_score_bucket{{agent=~"$agent"}}[$__rate_interval])))',
                "legendFormat": "p25 {{agent}}",
            },
            {
                "expr": f'histogram_quantile(0.50, sum by(le,agent) (rate(praktor_judge_score_bucket{{agent=~"$agent"}}[$__rate_interval])))',
                "legendFormat": "p50 {{agent}}",
            },
            {
                "expr": f'histogram_quantile(0.75, sum by(le,agent) (rate(praktor_judge_score_bucket{{agent=~"$agent"}}[$__rate_interval])))',
                "legendFormat": "p75 {{agent}}",
            },
        ],
        datasource=datasource, x=0, y=27, w=12, h=8,
        unit="short",
        min_val=0, max_val=10,
    ))
    panels.append(_timeseries(
        next(_id), "Judge Score Average by Agent",
        exprs=[{
            "expr": f'praktor_judge_score_avg{{agent=~"$agent"}}',
            "legendFormat": "{{agent}}",
        }],
        datasource=datasource, x=12, y=27, w=12, h=8,
        unit="short",
        min_val=0, max_val=10,
    ))

    # ----------------------------------------------------------------
    # Row 5: AIGov Compliance
    # ----------------------------------------------------------------
    panels.append(_row(next(_id), "AIGov Compliance", y=36))

    panels.append(_timeseries(
        next(_id), "Obligation Status by Agent (PASS=1 / FAIL=0)",
        exprs=[{
            "expr": f'praktor_aigov_obligation_status{{agent=~"$agent"}}',
            "legendFormat": "{{agent}} / {{obligation}} ({{enforcement_point}})",
        }],
        datasource=datasource, x=0, y=37, w=16, h=8,
        unit="short",
        min_val=0, max_val=1,
    ))
    panels.append(_timeseries(
        next(_id), "Business KPIs",
        exprs=[{
            "expr": 'praktor_kpi{name!~"eval\\..*"}',
            "legendFormat": "{{name}}",
        }],
        datasource=datasource, x=16, y=37, w=8, h=8,
        unit="short",
    ))

    # ----------------------------------------------------------------
    # Row 6: Offline Eval Results
    # ----------------------------------------------------------------
    panels.append(_row(next(_id), "Offline Eval Results", y=46))

    panels.append(_stat(
        next(_id), "Action Accuracy",
        expr='praktor_kpi{name="eval.action_accuracy"}',
        datasource=datasource, x=0, y=47, w=4, h=4,
        color_mode="background",
        thresholds=[
            {"color": "red", "value": None},
            {"color": "yellow", "value": 0.70},
            {"color": "green", "value": 0.85},
        ],
        unit="percentunit",
    ))
    panels.append(_stat(
        next(_id), "Measure Accuracy",
        expr='praktor_kpi{name="eval.measure_accuracy"}',
        datasource=datasource, x=4, y=47, w=4, h=4,
        color_mode="background",
        thresholds=[
            {"color": "red", "value": None},
            {"color": "yellow", "value": 0.70},
            {"color": "green", "value": 0.85},
        ],
        unit="percentunit",
    ))
    panels.append(_stat(
        next(_id), "Overall Judge Score",
        expr='praktor_kpi{name="eval.overall_score"}',
        datasource=datasource, x=8, y=47, w=4, h=4,
        color_mode="background",
        thresholds=[
            {"color": "red", "value": None},
            {"color": "yellow", "value": 5},
            {"color": "green", "value": 7},
        ],
        unit="short",
        decimals=2,
    ))
    panels.append(_stat(
        next(_id), "Accuracy Score",
        expr='praktor_kpi{name="eval.accuracy_score"}',
        datasource=datasource, x=12, y=47, w=3, h=4,
        color_mode="value",
        thresholds=[
            {"color": "red", "value": None},
            {"color": "yellow", "value": 6},
            {"color": "green", "value": 8},
        ],
        unit="short", decimals=1,
    ))
    panels.append(_stat(
        next(_id), "Completeness Score",
        expr='praktor_kpi{name="eval.completeness_score"}',
        datasource=datasource, x=15, y=47, w=3, h=4,
        color_mode="value",
        thresholds=[
            {"color": "red", "value": None},
            {"color": "yellow", "value": 6},
            {"color": "green", "value": 8},
        ],
        unit="short", decimals=1,
    ))
    panels.append(_stat(
        next(_id), "Relevance Score",
        expr='praktor_kpi{name="eval.relevance_score"}',
        datasource=datasource, x=18, y=47, w=3, h=4,
        color_mode="value",
        thresholds=[
            {"color": "red", "value": None},
            {"color": "yellow", "value": 6},
            {"color": "green", "value": 8},
        ],
        unit="short", decimals=1,
    ))
    panels.append(_stat(
        next(_id), "Clarity Score",
        expr='praktor_kpi{name="eval.clarity_score"}',
        datasource=datasource, x=21, y=47, w=3, h=4,
        color_mode="value",
        thresholds=[
            {"color": "red", "value": None},
            {"color": "yellow", "value": 6},
            {"color": "green", "value": 8},
        ],
        unit="short", decimals=1,
    ))

    # ----------------------------------------------------------------
    # Row 7: Judge Calibration
    # ----------------------------------------------------------------
    panels.append(_row(next(_id), "Judge Calibration", y=52))

    # Score before/after calibration per judge type
    panels.append(_timeseries(
        next(_id), "Calibration Score — Before vs After",
        exprs=[
            {
                "expr": 'praktor_kpi{name=~"judge\\.calibration\\.score_before\\..*"}',
                "legendFormat": "before · {{name}}",
            },
            {
                "expr": 'praktor_kpi{name=~"judge\\.calibration\\.score_after\\..*"}',
                "legendFormat": "after · {{name}}",
            },
        ],
        datasource=datasource, x=0, y=53, w=12, h=8,
        unit="short", min_val=0, max_val=10,
    ))

    # Calibration delta (improvement)
    panels.append(_timeseries(
        next(_id), "Calibration Delta (after − before)",
        exprs=[{
            "expr": 'praktor_kpi{name=~"judge\\.calibration\\.delta\\..*"}',
            "legendFormat": "{{name}}",
        }],
        datasource=datasource, x=12, y=53, w=12, h=8,
        unit="short", min_val=-2, max_val=5,
    ))

    # Sample count vs required
    panels.append(_timeseries(
        next(_id), "Golden Dataset — Actual vs Required Samples",
        exprs=[
            {
                "expr": 'praktor_kpi{name=~"judge\\.calibration\\.n_samples\\..*"}',
                "legendFormat": "actual · {{name}}",
            },
            {
                "expr": 'praktor_kpi{name=~"judge\\.calibration\\.n_required\\..*"}',
                "legendFormat": "required · {{name}}",
            },
        ],
        datasource=datasource, x=0, y=61, w=12, h=8,
        unit="short", min_val=0,
    ))

    # Per-criterion offline eval scores (all 5 base + conciseness)
    panels.append(_timeseries(
        next(_id), "Offline Eval — Per-Criterion Scores",
        exprs=[
            {"expr": 'praktor_kpi{name="eval.overall_score"}',      "legendFormat": "overall"},
            {"expr": 'praktor_kpi{name="eval.accuracy_score"}',     "legendFormat": "accuracy"},
            {"expr": 'praktor_kpi{name="eval.completeness_score"}', "legendFormat": "completeness"},
            {"expr": 'praktor_kpi{name="eval.relevance_score"}',    "legendFormat": "relevance"},
            {"expr": 'praktor_kpi{name="eval.conciseness_score"}',  "legendFormat": "conciseness"},
            {"expr": 'praktor_kpi{name="eval.clarity_score"}',      "legendFormat": "clarity"},
        ],
        datasource=datasource, x=12, y=61, w=12, h=8,
        unit="short", min_val=0, max_val=10,
    ))

    # ----------------------------------------------------------------
    # Row 8: Production Eval
    # ----------------------------------------------------------------
    panels.append(_row(next(_id), "Production Eval", y=70))

    panels.append(_timeseries(
        next(_id), "Production Eval Score by Agent",
        exprs=[{
            "expr": 'praktor_production_eval_score',
            "legendFormat": "{{agent}}",
        }],
        datasource=datasource, x=0, y=71, w=12, h=8,
        unit="short", min_val=0, max_val=10,
    ))
    panels.append(_stat(
        next(_id), "Production Eval Overall",
        expr='praktor_kpi{name="production_eval.score.overall"}',
        datasource=datasource, x=12, y=71, w=6, h=4,
        color_mode="background",
        thresholds=[
            {"color": "red", "value": None},
            {"color": "yellow", "value": 5},
            {"color": "green", "value": 7},
        ],
        unit="short", decimals=2,
    ))
    panels.append(_stat(
        next(_id), "Demo Runs Judged",
        expr='sum(increase(praktor_agent_runs_total{agent=~"hedis_gap|diabetes_hedis"}[7d]))',
        datasource=datasource, x=18, y=71, w=6, h=4,
        color_mode="background",
        thresholds=[{"color": "blue", "value": None}],
        unit="short",
    ))

    # ----------------------------------------------------------------
    # Row 8: HITL Review
    # ----------------------------------------------------------------
    panels.append(_row(next(_id), "HITL Review", y=80))

    panels.append(_stat(
        next(_id), "Pending Reviews",
        expr='praktor_hitl_pending',
        datasource=datasource, x=0, y=81, w=6, h=4,
        color_mode="background",
        thresholds=[
            {"color": "green", "value": None},
            {"color": "yellow", "value": 5},
            {"color": "red", "value": 20},
        ],
        unit="short",
    ))
    panels.append(_stat(
        next(_id), "Approval Rate",
        expr='praktor_hitl_approval_rate',
        datasource=datasource, x=6, y=81, w=6, h=4,
        color_mode="background",
        thresholds=[
            {"color": "red", "value": None},
            {"color": "yellow", "value": 0.7},
            {"color": "green", "value": 0.85},
        ],
        unit="percentunit",
    ))
    panels.append(_timeseries(
        next(_id), "HITL Review Queue (pending over time)",
        exprs=[{
            "expr": 'praktor_hitl_pending',
            "legendFormat": "pending reviews",
        }],
        datasource=datasource, x=12, y=81, w=12, h=8,
        unit="short",
    ))

    # ----------------------------------------------------------------
    # Assemble dashboard
    # ----------------------------------------------------------------
    return {
        "uid":    uid,
        "title":  title,
        "tags":   ["praktor", "llm", "clinical", "aigov"],
        "style":  "dark",
        "refresh": refresh,
        "schemaVersion": 38,
        "version": 2,
        "time": {"from": "now-24h", "to": "now"},
        "timepicker": {},
        "fiscalYearStartMonth": 0,
        "graphTooltip": 1,
        "links": [],
        "templating": {
            "list": [
                {
                    "name": "datasource",
                    "type": "datasource",
                    "pluginId": "prometheus",
                    "label": "Data source",
                    "current": {},
                    "hide": 0,
                    "includeAll": False,
                    "multi": False,
                },
                {
                    "name": "agent",
                    "type": "query",
                    "datasource": {"type": "prometheus", "uid": "${datasource}"},
                    "definition": "label_values(praktor_agent_runs_total, agent)",
                    "query": "label_values(praktor_agent_runs_total, agent)",
                    "label": "Agent",
                    "includeAll": True,
                    "allValue": ".*",
                    "multi": True,
                    "current": {"text": "All", "value": "$__all"},
                    "hide": 0,
                    "refresh": 2,
                    "sort": 1,
                },
                {
                    "name": "model",
                    "type": "query",
                    "datasource": {"type": "prometheus", "uid": "${datasource}"},
                    "definition": "label_values(praktor_agent_runs_total, model)",
                    "query": "label_values(praktor_agent_runs_total, model)",
                    "label": "Model",
                    "includeAll": True,
                    "allValue": ".*",
                    "multi": True,
                    "current": {"text": "All", "value": "$__all"},
                    "hide": 0,
                    "refresh": 2,
                    "sort": 1,
                },
            ]
        },
        "annotations": {
            "list": [
                {
                    "builtIn": 1,
                    "datasource": {"type": "grafana", "uid": "-- Grafana --"},
                    "enable": True,
                    "hide": True,
                    "iconColor": "rgba(0, 211, 255, 1)",
                    "name": "Annotations & Alerts",
                    "type": "dashboard",
                }
            ]
        },
        "panels": panels,
    }


# ---------------------------------------------------------------------------
# Panel builders
# ---------------------------------------------------------------------------

def _counter():
    n = 0
    while True:
        n += 1
        yield n


def _row(panel_id: int, title: str, y: int) -> dict:
    return {
        "id": panel_id,
        "type": "row",
        "title": title,
        "collapsed": False,
        "gridPos": {"x": 0, "y": y, "w": 24, "h": 1},
        "panels": [],
    }


def _datasource_ref(datasource: str) -> dict:
    return {"type": "prometheus", "uid": datasource}


def _stat(
    panel_id: int,
    title: str,
    expr: str,
    datasource: str,
    x: int, y: int, w: int, h: int,
    color_mode: str = "background",
    thresholds: list | None = None,
    unit: str = "short",
    decimals: int | None = None,
) -> dict:
    panel: dict[str, Any] = {
        "id": panel_id,
        "type": "stat",
        "title": title,
        "gridPos": {"x": x, "y": y, "w": w, "h": h},
        "datasource": _datasource_ref(datasource),
        "targets": [{"expr": expr, "instant": True, "datasource": _datasource_ref(datasource)}],
        "options": {
            "colorMode": color_mode,
            "graphMode": "area",
            "justifyMode": "auto",
            "orientation": "auto",
            "textMode": "auto",
            "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
        },
        "fieldConfig": {
            "defaults": {
                "unit": unit,
                "thresholds": {
                    "mode": "absolute",
                    "steps": thresholds or [{"color": "green", "value": None}],
                },
                "color": {"mode": "thresholds"},
            },
            "overrides": [],
        },
    }
    if decimals is not None:
        panel["fieldConfig"]["defaults"]["decimals"] = decimals
    return panel


def _timeseries(
    panel_id: int,
    title: str,
    exprs: list[dict],
    datasource: str,
    x: int, y: int, w: int, h: int,
    unit: str = "short",
    stacking: bool = False,
    min_val: float | None = None,
    max_val: float | None = None,
) -> dict:
    targets = [
        {
            "expr": e["expr"],
            "legendFormat": e.get("legendFormat", ""),
            "datasource": _datasource_ref(datasource),
        }
        for e in exprs
    ]
    defaults: dict[str, Any] = {"unit": unit, "color": {"mode": "palette-classic"}}
    if min_val is not None:
        defaults["min"] = min_val
    if max_val is not None:
        defaults["max"] = max_val

    return {
        "id": panel_id,
        "type": "timeseries",
        "title": title,
        "gridPos": {"x": x, "y": y, "w": w, "h": h},
        "datasource": _datasource_ref(datasource),
        "targets": targets,
        "options": {
            "legend": {"displayMode": "list", "placement": "bottom"},
            "stacking": {"group": "A", "mode": "normal" if stacking else "none"},
            "tooltip": {"mode": "multi"},
        },
        "fieldConfig": {
            "defaults": defaults,
            "overrides": [],
        },
    }


def print_dashboard(datasource: str = "${datasource}") -> None:
    """Print the Grafana dashboard JSON to stdout."""
    print(json.dumps(build_dashboard(datasource=datasource), indent=2))
