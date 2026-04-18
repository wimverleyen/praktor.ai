"""
AIGov Scoreboard — materialized view over the obligation event ledger.

scoreboard_current() returns the latest predicate_result per
(tenant, agent, obligation, enforcement_point) and maps it to a
GREEN/AMBER/RED status the ERM team reads.

Status mapping (AIGov §11):
    PASS   → GREEN
    FAIL   → RED
    WAIVED → GREEN  (waiver accepted)
    NA     → AMBER  (deferred / infrastructure not yet wired)
    <no events> → GREY (obligation not yet evaluated)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from praktor.aigov.ledger.store import LedgerStore


# Status constants
GREEN = "GREEN"
AMBER = "AMBER"
RED = "RED"
GREY = "GREY"

_PREDICATE_TO_STATUS: dict[str, str] = {
    "PASS": GREEN,
    "FAIL": RED,
    "WAIVED": GREEN,
    "NA": AMBER,
}

_LATEST_PER_KEY_SQL = """
SELECT
    tenant_id,
    agent_id,
    obligation_id,
    enforcement_point,
    predicate_result,
    deferred_reason,
    event_ts
FROM fact_obligation_event
{where}
QUALIFY ROW_NUMBER() OVER (
    PARTITION BY tenant_id, agent_id, obligation_id, enforcement_point
    ORDER BY event_ts DESC
) = 1
ORDER BY agent_id, obligation_id, enforcement_point
"""


@dataclass
class ScoreboardRow:
    tenant_id: str
    agent_id: str
    obligation_id: str
    enforcement_point: str
    status: str
    predicate_result: str
    deferred_reason: str
    last_event_ts: str


def scoreboard_current(
    store: LedgerStore,
    agent_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
) -> list[ScoreboardRow]:
    """
    Return the current scoreboard: latest status per (agent × obligation × point).

    Args:
        store: LedgerStore instance to query.
        agent_id: Filter to a single agent. None = all agents.
        tenant_id: Filter to a single tenant. None = all tenants.

    Returns:
        List of ScoreboardRow, one per (agent, obligation, enforcement_point) key
        that has at least one event.
    """
    conditions: list[str] = []
    params: list[str] = []
    if agent_id is not None:
        conditions.append("agent_id = ?")
        params.append(agent_id)
    if tenant_id is not None:
        conditions.append("tenant_id = ?")
        params.append(tenant_id)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    sql = _LATEST_PER_KEY_SQL.format(where=where)

    rows = store.query_sync(sql, params)
    return [
        ScoreboardRow(
            tenant_id=row[0],
            agent_id=row[1],
            obligation_id=row[2],
            enforcement_point=row[3],
            status=_PREDICATE_TO_STATUS.get(row[4], GREY),
            predicate_result=row[4],
            deferred_reason=row[5] or "",
            last_event_ts=str(row[6]),
        )
        for row in rows
    ]


def status_summary(rows: list[ScoreboardRow]) -> str:
    """
    Roll up a list of ScoreboardRows to overall status.

    RED if any obligation is RED. AMBER if any is AMBER. GREEN if all GREEN.
    GREY if no rows.
    """
    if not rows:
        return GREY
    statuses = {r.status for r in rows}
    if RED in statuses:
        return RED
    if AMBER in statuses:
        return AMBER
    return GREEN
