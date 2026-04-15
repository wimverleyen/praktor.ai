"""
Grafana dashboard JSON builder.

Generates a production-ready Grafana 10+ dashboard with 6 rows and 14 panels
covering all praktor monitoring dimensions.

Usage:
    from monitoring.exporters.grafana import build_dashboard
    import json
    print(json.dumps(build_dashboard(), indent=2))

    # CLI:
    python -m praktor monitor export grafana > praktor-dashboard.json
    # Then: Grafana → Dashboards → Import → Upload JSON file

Dashboard structure:
    Row 1: Overview stats   — total runs, tokens, cost, avg latency (stat panels)
    Row 2: Traffic          — run rate by agent, token rate over time
    Row 3: Performance      — latency percentiles (P50/P95/P99), error rate
    Row 4: Quality          — judge scores, cache hit ratio
    Row 5: Cost & Tools     — cost by model, tool call breakdown
    Row 6: Business KPIs    — custom KPI time series
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
    # Row 1: Overview stats
    # ----------------------------------------------------------------
    panels.append(_row(next(_id), "Overview", y=0))

    panels.append(_stat(
        next(_id), "Total Runs (24h)",
        expr=f'sum(increase(praktor_agent_runs_total{{agent=~"$agent",model=~"$model"}}[24h]))',
        datasource=datasource, x=0, y=1, w=3, h=4,
        color_mode="background", thresholds=[
            {"color": "blue", "value": None},
        ],
        unit="short",
    ))
    panels.append(_stat(
        next(_id), "Total Tokens (24h)",
        expr=f'sum(increase(praktor_tokens_total{{agent=~"$agent",model=~"$model"}}[24h]))',
        datasource=datasource, x=3, y=1, w=3, h=4,
        color_mode="background", thresholds=[
            {"color": "green", "value": None},
        ],
        unit="short",
    ))
    panels.append(_stat(
        next(_id), "Total Cost USD (24h)",
        expr=f'sum(increase(praktor_cost_usd_total{{agent=~"$agent",model=~"$model"}}[24h]))',
        datasource=datasource, x=6, y=1, w=3, h=4,
        color_mode="background", thresholds=[
            {"color": "yellow", "value": None},
            {"color": "red", "value": 1.0},
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
        datasource=datasource, x=9, y=1, w=3, h=4,
        color_mode="background", thresholds=[
            {"color": "green", "value": None},
            {"color": "yellow", "value": 2000},
            {"color": "red", "value": 5000},
        ],
        unit="ms",
    ))
    panels.append(_stat(
        next(_id), "Avg Judge Score (24h)",
        expr=f'avg(praktor_judge_score_avg{{agent=~"$agent"}})',
        datasource=datasource, x=12, y=1, w=3, h=4,
        color_mode="background", thresholds=[
            {"color": "red", "value": None},
            {"color": "yellow", "value": 5},
            {"color": "green", "value": 7},
        ],
        unit="short",
        decimals=1,
        suffix="/10",
    ))
    panels.append(_stat(
        next(_id), "Error Rate (24h)",
        expr=(
            f'sum(rate(praktor_agent_runs_total{{agent=~"$agent",model=~"$model",status="error"}}[24h]))'
            f' / sum(rate(praktor_agent_runs_total{{agent=~"$agent",model=~"$model"}}[24h]))'
        ),
        datasource=datasource, x=15, y=1, w=3, h=4,
        color_mode="background", thresholds=[
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
        next(_id), "Token Rate",
        exprs=[
            {
                "expr": f'sum by(direction) (rate(praktor_tokens_total{{agent=~"$agent",model=~"$model"}}[$__rate_interval]))',
                "legendFormat": "{{direction}}",
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
        next(_id), "Latency Percentiles",
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
        next(_id), "Error Rate",
        exprs=[{
            "expr": (
                f'sum by(agent) (rate(praktor_agent_runs_total{{agent=~"$agent",model=~"$model",status="error"}}[$__rate_interval]))'
                f' / sum by(agent) (rate(praktor_agent_runs_total{{agent=~"$agent",model=~"$model"}}[$__rate_interval]))'
            ),
            "legendFormat": "{{agent}}",
        }],
        datasource=datasource, x=12, y=17, w=12, h=8,
        unit="percentunit",
    ))

    # ----------------------------------------------------------------
    # Row 4: Quality
    # ----------------------------------------------------------------
    panels.append(_row(next(_id), "Quality", y=26))

    panels.append(_timeseries(
        next(_id), "Judge Score Distribution (P25/P50/P75)",
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
        next(_id), "Cache Hit Ratio",
        exprs=[{
            "expr": f'praktor_cache_hit_ratio{{agent=~"$agent",model=~"$model"}}',
            "legendFormat": "{{agent}} / {{model}}",
        }],
        datasource=datasource, x=12, y=27, w=12, h=8,
        unit="percentunit",
        min_val=0, max_val=1,
    ))

    # ----------------------------------------------------------------
    # Row 5: Cost & Tools
    # ----------------------------------------------------------------
    panels.append(_row(next(_id), "Cost & Tools", y=36))

    panels.append(_timeseries(
        next(_id), "Cost by Model (per hour)",
        exprs=[{
            "expr": f'sum by(model) (increase(praktor_cost_usd_total{{agent=~"$agent"}}[1h]))',
            "legendFormat": "{{model}}",
        }],
        datasource=datasource, x=0, y=37, w=12, h=8,
        unit="currencyUSD",
    ))
    panels.append(_barchart(
        next(_id), "Tool Calls (24h)",
        expr=f'sum by(tool,status) (increase(praktor_tool_calls_total{{agent=~"$agent"}}[24h]))',
        legend_format="{{tool}} ({{status}})",
        datasource=datasource, x=12, y=37, w=12, h=8,
    ))

    # ----------------------------------------------------------------
    # Row 6: Business KPIs
    # ----------------------------------------------------------------
    panels.append(_row(next(_id), "Business KPIs", y=46))

    panels.append(_timeseries(
        next(_id), "Business KPI Values",
        exprs=[{
            "expr": 'praktor_kpi',
            "legendFormat": "{{name}}",
        }],
        datasource=datasource, x=0, y=47, w=24, h=8,
        unit="short",
    ))

    # ----------------------------------------------------------------
    # Assemble dashboard
    # ----------------------------------------------------------------
    return {
        "uid":    uid,
        "title":  title,
        "tags":   ["praktor", "llm", "agents", "monitoring"],
        "style":  "dark",
        "refresh": refresh,
        "schemaVersion": 38,
        "version": 1,
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
    if datasource.startswith("${"):
        return {"type": "prometheus", "uid": datasource}
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
    suffix: str = "",
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
    if suffix:
        panel["fieldConfig"]["defaults"]["custom"] = {"unitPrefix": suffix}
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


def _barchart(
    panel_id: int,
    title: str,
    expr: str,
    legend_format: str,
    datasource: str,
    x: int, y: int, w: int, h: int,
) -> dict:
    return {
        "id": panel_id,
        "type": "barchart",
        "title": title,
        "gridPos": {"x": x, "y": y, "w": w, "h": h},
        "datasource": _datasource_ref(datasource),
        "targets": [
            {
                "expr": expr,
                "legendFormat": legend_format,
                "instant": True,
                "datasource": _datasource_ref(datasource),
            }
        ],
        "options": {
            "barWidth": 0.7,
            "groupWidth": 0.7,
            "orientation": "auto",
            "stacking": "none",
            "legend": {"displayMode": "list", "placement": "bottom"},
            "tooltip": {"mode": "single"},
        },
        "fieldConfig": {
            "defaults": {"unit": "short", "color": {"mode": "palette-classic"}},
            "overrides": [],
        },
    }


def print_dashboard(datasource: str = "${datasource}") -> None:
    """Print the Grafana dashboard JSON to stdout."""
    print(json.dumps(build_dashboard(datasource=datasource), indent=2))
