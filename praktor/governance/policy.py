"""
GovernancePolicy — declarative compliance configuration for an AgentDefinition.

Attach a GovernancePolicy to any AgentDefinition to enable:
- Pre-execution PII/PHI detection on agent payload fields
- Post-execution detection on LLM response
- Append-only tamper-evident audit logging
- RBAC enforcement (opt-in via PRAKTOR_RBAC_SECRET env var)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class PolicyAction(Enum):
    ALLOW = "allow"    # Pass through. No audit entry for this detector.
    REDACT = "redact"  # Replace matched spans with [REDACTED:<entity_type>]. Audit written.
    BLOCK = "block"    # Raise GovernancePolicyViolation. Execution halts. Audit written.
    FLAG = "flag"      # Pass through. AuditEntry.flagged=True. Audit written.


class AuditSinkType(Enum):
    LOCAL_FILE = "local_file"
    KAFKA = "kafka"    # Phase 2 — raises NotImplementedError if configured in Phase 1
    MINIO = "minio"    # Phase 2 — raises NotImplementedError if configured in Phase 1
    STDOUT = "stdout"  # Development/testing


@dataclass
class DetectorConfig:
    """Configuration for one PII/PHI detector pass."""
    detector_class: str
    """Import path, e.g. 'praktor.governance.detectors.RegexDetector'"""

    entities: list[str]
    """Entity types to detect, e.g. ['US_SSN', 'PHONE_NUMBER', 'EMAIL_ADDRESS']"""

    action: PolicyAction = PolicyAction.REDACT
    threshold: float = 0.8
    """Confidence threshold 0.0–1.0. RegexDetector always returns 1.0."""


@dataclass
class GovernancePolicy:
    """
    Declarative governance configuration. Attach to AgentDefinition.governance_policy.

    Governance boundary: detection runs on individual payload field values (pre-execution)
    and on the full LLM response string (post-execution). It does NOT govern intermediate
    tool call outputs inside LCEL chains — documented limitation.

    RBAC fail-closed rule: if rbac_required_roles is non-empty and PRAKTOR_RBAC_SECRET
    is absent, the Router raises ConfigurationError. Never silently open access.
    """

    pre_execution: list[DetectorConfig] = field(default_factory=list)
    """Run on each string field of the agent payload before calling astream()."""

    post_execution: list[DetectorConfig] = field(default_factory=list)
    """Run on the full LLM response before yielding it to the caller."""

    audit_sinks: list[AuditSinkType] = field(default_factory=lambda: [AuditSinkType.LOCAL_FILE])
    """Where to write audit entries. KAFKA and MINIO raise NotImplementedError in Phase 1."""

    rbac_required_roles: list[str] = field(default_factory=list)
    """
    If non-empty, caller must present a CallerIdentity token with a matching role.
    Requires PRAKTOR_RBAC_SECRET env var. Absent secret + non-empty roles = ConfigurationError.
    """

    def __post_init__(self) -> None:
        for sink in self.audit_sinks:
            if not isinstance(sink, AuditSinkType):
                raise ValueError(
                    f"Invalid audit_sinks value: {sink!r}. "
                    f"Must be AuditSinkType enum. Got {type(sink).__name__}."
                )


class GovernancePolicyViolation(Exception):
    """Raised when a BLOCK policy action fires. Execution is halted."""


class EvaluationFailedError(Exception):
    """Raised when an EvaluationPass with on_fail=BLOCK produces a failing score."""
