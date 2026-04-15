"""
praktor.ai monitoring — continuous observability for agentic AI.

Quick start:

    # 1. Configure once at startup (optional — defaults work out of the box)
    from monitoring import configure
    configure(prometheus_port=8080)   # enables Prometheus scrape server

    # 2. Record business KPIs anywhere in your code
    from monitoring import record_kpi
    record_kpi("cover_letter_accepted", value=1, tags={"source": "linkedin"})
    record_kpi("search_quality",        value=8.5)

    # 3. Record judge evaluations
    from monitoring.collector import record_judge
    await record_judge(session_id, agent_type, judge_score_object)

    # 4. All agent.run() completions are recorded automatically —
    #    no extra code needed if you use Agent from core.agent.

Data products:

    Prometheus:     http://localhost:8080/metrics  (after configure())
    Grafana JSON:   python -m praktor monitor export grafana > dashboard.json
    CLI summary:    python -m praktor monitor summary
    SQLite:         ~/.praktor/monitoring.db  (always)

Environment variables:

    PRAKTOR_MONITORING_DB   SQLite path (default: ~/.praktor/monitoring.db)
    OTLP_ENDPOINT           OTel collector endpoint — used for both traces and metrics
    OTEL_METRIC_EXPORT_INTERVAL_MS  OTel push interval (default: 30000)
"""

from monitoring.registry import configure, get_registry, record_kpi
from monitoring.collector import record_run, record_judge
from monitoring.store import RunRecord, JudgeEvalRecord, KPIRecord, MonitoringStore

__all__ = [
    "configure",
    "get_registry",
    "record_kpi",
    "record_run",
    "record_judge",
    "RunRecord",
    "JudgeEvalRecord",
    "KPIRecord",
    "MonitoringStore",
]
