"""
Governance metrics — counters for PII/PHI detection events.

Wired into agent.py governance hooks. No import from praktor.governance
(avoids circular dep): callers pass entity/action as plain strings.
"""
from __future__ import annotations

from praktor.monitoring.registry import get_registry


def record_governance_detection(entity_type: str) -> None:
    """Increment governance.detections_total counter."""
    registry = get_registry()
    registry.governance_detections.inc({"entity_type": entity_type})
    registry.record_kpi(
        "governance.detections_total",
        value=1.0,
        tags={"entity_type": entity_type},
    )


def record_governance_violation(action: str, entity_type: str) -> None:
    """Increment governance.violations_total counter."""
    registry = get_registry()
    registry.governance_violations.inc({"action": action, "entity_type": entity_type})
    registry.record_kpi(
        "governance.violations_total",
        value=1.0,
        tags={"action": action, "entity_type": entity_type},
    )


def record_governance_dry_run() -> None:
    """Increment governance.dry_run_hits_total."""
    get_registry().record_kpi("governance.dry_run_hits_total", value=1.0)


def record_aigov_result(
    agent: str,
    obligation: str,
    enforcement_point: str,
    status: str,
) -> None:
    """
    Record an AIGov obligation check result as a Prometheus gauge.

    status values: GREEN | AMBER | RED | GREY
    Mapped to: 1.0 | 0.5 | 0.0 | -1.0
    """
    get_registry().record_aigov_obligation(agent, obligation, enforcement_point, status)
