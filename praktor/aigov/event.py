"""
AIGov Framework v0.3 §10 — ObligationEvent schema.

One event per enforcement check per (agent, obligation, enforcement_point).
Events are append-only. Corrections emit new events; never mutate existing ones.
"""
from __future__ import annotations

import socket
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from ulid import ULID


def _new_ulid() -> str:
    return str(ULID())


def _now_rfc3339() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class PredicateResult(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    WAIVED = "WAIVED"
    NA = "NA"


class AgentPattern(str, Enum):
    """AIGov §7 Bundle Selection Matrix — agent behavioral pattern B1-B7."""
    B1 = "B1"  # Simple retrieval-augmented QA
    B2 = "B2"  # Multi-step reasoning chain
    B3 = "B3"  # ReAct tool-use loop
    B4 = "B4"  # Multi-agent orchestrator
    B5 = "B5"  # Human-in-the-loop supervised
    B6 = "B6"  # Autonomous long-horizon task
    B7 = "B7"  # Adversarial / red-team


class EnforcementPoint(str, Enum):
    G_BUILD = "G-BUILD"
    G_TEST = "G-TEST"
    G_RUN = "G-RUN"


class DeploymentEnv(str, Enum):
    DEV = "dev"
    STAGING = "staging"
    CANARY = "canary"
    PROD = "prod"


class Severity(str, Enum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class EvidenceRef:
    """Pointer to an immutable evidence blob (MinIO / local filesystem)."""
    uri: str
    sha256: str
    size_bytes: int = 0
    redacted: bool = True


@dataclass
class ReviewerRef:
    """Human reviewer identity, if applicable (O8 HITL)."""
    reviewer_id: str
    name: str = ""
    role: str = ""


@dataclass
class SourceRef:
    """Which praktor emitter produced this event."""
    kind: str = "praktor_aigov"
    version: str = "0.5.0"
    host: str = field(default_factory=lambda: socket.gethostname())


@dataclass
class ObligationEvent:
    """
    AIGov Framework v0.3 §10 canonical event.

    Minimum required fields: obligation_id, enforcement_point, predicate_result.
    All other fields have sensible defaults and should be populated before ledger write.

    Deferred obligations (no infrastructure yet) use predicate_result=NA with a
    non-empty deferred_reason. Never use PASS for an unevaluated obligation.
    """

    # Core classification (required)
    obligation_id: str
    enforcement_point: EnforcementPoint
    predicate_result: PredicateResult

    # Agent context — populate from AgentDefinition before writing to ledger
    agent_id: str = ""
    agent_version: str = "0.0.0"
    agent_pattern: AgentPattern = AgentPattern.B1
    deployment_env: DeploymentEnv = DeploymentEnv.DEV
    tenant_id: str = "default"
    bundle_id: str = "unknown"
    cim_version: str = "0.0.0"

    # Obligation classification
    measurement_technique: str = ""
    severity: Severity = Severity.INFO
    waiver_id: Optional[str] = None
    deferred_reason: str = ""

    # Evidence and review
    evidence: Optional[EvidenceRef] = None
    reviewer: Optional[ReviewerRef] = None
    regulatory_tags: list[str] = field(default_factory=list)

    # OTel correlation
    trace_id: str = ""
    span_id: str = ""

    # Emitter
    source: SourceRef = field(default_factory=SourceRef)

    # Auto-populated — do not set manually in production
    schema_version: str = field(default="1.0", init=False, repr=False)
    event_id: str = field(default="", init=True)
    event_ts: str = field(default="", init=True)
    ingest_ts: str = field(default="", init=True)

    def __post_init__(self) -> None:
        if not self.event_id:
            self.event_id = _new_ulid()
        now = _now_rfc3339()
        if not self.event_ts:
            self.event_ts = now
        if not self.ingest_ts:
            self.ingest_ts = now
