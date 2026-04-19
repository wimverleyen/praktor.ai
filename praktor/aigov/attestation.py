"""
AIGov Attestation — signed point-in-time projection of the Scoreboard.

An Attestation is a receipt for a moment in the ledger, not a standalone document.
It captures the current obligation status for an agent bundle and signs the snapshot
with a sha256 content hash (placeholder until signing-key infrastructure ships).

Usage:
    from praktor.aigov.attestation import create_attestation
    from praktor.aigov.ledger.scoreboard import scoreboard_current

    store = LedgerStore()
    rows = scoreboard_current(store, agent_id="my-agent")
    att = create_attestation(agent_id="my-agent", bundle_id="healthcare-v1", rows=rows)
    print(att.is_current())        # True if created_at < valid_until
    print(att.all_obligations_held())  # True if all rows are PASS/WAIVED/NA
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from ulid import ULID

_DEFAULT_VALIDITY_DAYS = 30


@dataclass
class AttestationRecord:
    """
    Point-in-time snapshot of obligation status for one agent bundle.

    Attributes:
        attestation_id:     ULID, auto-generated.
        agent_id:           Agent this attestation covers.
        tenant_id:          Tenant scope (empty = default).
        bundle_id:          ObligationBundle.bundle_id.
        created_at:         RFC3339 timestamp of creation.
        valid_until:        RFC3339 expiry timestamp.
        obligation_statuses: List of {obligation_id, enforcement_point, status, event_ts}.
        signature_hex:      sha256 of the canonical payload (real signing key future work).
        signer_key_id:      Key identifier (empty until signing-key infra ships).
        notes:              Free-text, e.g. "CI gate pass — build 4812".
    """
    attestation_id: str
    agent_id: str
    bundle_id: str
    created_at: str
    valid_until: str
    obligation_statuses: list[dict[str, Any]]
    signature_hex: str
    tenant_id: str = ""
    signer_key_id: str = "sha256-content-hash"
    notes: str = ""

    def is_current(self) -> bool:
        """True if this attestation has not yet expired."""
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        return now <= self.valid_until

    def all_obligations_held(self) -> bool:
        """
        True when no obligation has status RED (i.e. all are GREEN or AMBER).

        GREEN = PASS or WAIVED; AMBER = NA; RED = FAIL.
        An attestation with all-AMBER is weaker than all-GREEN but not a violation —
        it means all obligations are deferred (na_stubs). Callers can check
        has_any_green() if they need at least one concrete pass.
        """
        red_statuses = {"RED", "FAIL"}
        return all(row.get("status") not in red_statuses for row in self.obligation_statuses)

    def has_any_green(self) -> bool:
        """True if at least one obligation row has status GREEN."""
        return any(row.get("status") == "GREEN" for row in self.obligation_statuses)


def create_attestation(
    agent_id: str,
    bundle_id: str,
    rows: list[Any],
    *,
    tenant_id: str = "",
    validity_days: int = _DEFAULT_VALIDITY_DAYS,
    notes: str = "",
) -> AttestationRecord:
    """
    Build an AttestationRecord from scoreboard rows.

    ``rows`` is the output of ``scoreboard_current()`` — a list of ScoreboardRow
    namedtuples or dicts with keys: obligation_id, enforcement_point, status, event_ts.
    """
    now = datetime.now(timezone.utc)
    created_at = now.isoformat().replace("+00:00", "Z")
    valid_until = (now + timedelta(days=validity_days)).isoformat().replace("+00:00", "Z")

    statuses = []
    for row in rows:
        if hasattr(row, "_asdict"):
            d = row._asdict()
        elif isinstance(row, dict):
            d = row
        else:
            d = dict(row)
        statuses.append({
            "obligation_id": d.get("obligation_id", ""),
            "enforcement_point": d.get("enforcement_point", ""),
            "status": d.get("status", ""),
            "event_ts": str(d.get("event_ts", "")),
        })

    payload = {
        "attestation_schema": "aigov-v0.5",
        "agent_id": agent_id,
        "tenant_id": tenant_id,
        "bundle_id": bundle_id,
        "created_at": created_at,
        "valid_until": valid_until,
        "obligation_statuses": statuses,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    signature_hex = hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    return AttestationRecord(
        attestation_id=str(ULID()),
        agent_id=agent_id,
        tenant_id=tenant_id,
        bundle_id=bundle_id,
        created_at=created_at,
        valid_until=valid_until,
        obligation_statuses=statuses,
        signature_hex=signature_hex,
        notes=notes,
    )
