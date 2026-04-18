"""
GovernancePolicy — declarative compliance configuration for an AgentDefinition.

Attach a GovernancePolicy to any AgentDefinition to enable:
- Pre-execution PII/PHI detection on agent payload fields
- Post-execution detection on LLM response
- Append-only tamper-evident audit logging
- RBAC enforcement (opt-in via PRAKTOR_RBAC_SECRET env var)
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from enum import Enum
from typing import Union


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
    detector_class: Union[str, type]
    """Class or import path, e.g. RegexDetector or 'praktor.governance.detectors.RegexDetector'"""

    entities: list[str]
    """Entity types to detect, e.g. ['US_SSN', 'PHONE_NUMBER', 'EMAIL_ADDRESS']"""

    action: PolicyAction = PolicyAction.REDACT
    threshold: float = 0.8
    """Confidence threshold 0.0–1.0. RegexDetector always returns 1.0."""

    def __post_init__(self) -> None:
        if isinstance(self.detector_class, type):
            self.detector_class = (
                f"{self.detector_class.__module__}.{self.detector_class.__qualname__}"
            )


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

    evaluation_passes: list = field(default_factory=list)
    """
    Post-execution scoring passes. Each is an EvaluationPass from
    governance.evaluators. Scored after post_execution detection.
    Empty list = no evaluation (Phase 1 default).
    """

    rbac_required_roles: list[str] = field(default_factory=list)
    """
    If non-empty, caller must present a CallerIdentity token with a matching role.
    Requires PRAKTOR_RBAC_SECRET env var. Absent secret + non-empty roles = ConfigurationError.
    """

    dry_run: bool = False
    """
    When True: detectors run and findings are logged (stderr) but no exceptions are
    raised and no audit sinks are written. Useful for unit tests and local development
    without mocking the full sink/detector chain.
    """

    def __post_init__(self) -> None:
        for sink in self.audit_sinks:
            if not isinstance(sink, AuditSinkType):
                raise ValueError(
                    f"Invalid audit_sinks value: {sink!r}. "
                    f"Must be AuditSinkType enum. Got {type(sink).__name__}."
                )

    def to_obligation_bundle(self) -> "ObligationBundle":
        """
        Convert this GovernancePolicy to an ObligationBundle (Decision 11A).

        Mapping:
            pre_execution / post_execution detectors  → O2DataConfinement
            evaluation_passes (any judge)             → O3ContentSafety
            audit_sinks (always present)              → O7Auditable
        """
        from praktor.aigov.bundle import ObligationBundle
        from praktor.aigov.obligations.o7_auditable import O7Auditable

        obligations = []

        if self.pre_execution or self.post_execution:
            from praktor.aigov.obligations.o2_data_confinement import O2DataConfinement
            obligations.append(O2DataConfinement())

        if self.evaluation_passes:
            from praktor.aigov.obligations.o3_content_safety import O3ContentSafety
            obligations.append(O3ContentSafety())

        obligations.append(O7Auditable())

        return ObligationBundle(
            obligations=obligations,
            bundle_id="governance_policy_shim",
            description="Auto-converted from GovernancePolicy (backward-compat shim)",
        )


class GovernancePolicyViolation(Exception):
    """
    Raised when a BLOCK policy action fires. Execution is halted.

    Attributes:
        field_name: payload field where the entity was detected (pre-execution)
                    or "response" (post-execution).
        entity_type: e.g. "US_SSN", "EMAIL_ADDRESS"
        detector_class: import path of the detector that fired
    """

    def __init__(
        self,
        message: str,
        field_name: str = "",
        entity_type: str = "",
        detector_class: str = "",
    ) -> None:
        super().__init__(message)
        self.field_name = field_name
        self.entity_type = entity_type
        self.detector_class = detector_class

    def __str__(self) -> str:
        base = super().__str__()
        if self.field_name and self.entity_type:
            return (
                f"{base} — field='{self.field_name}', entity={self.entity_type}, "
                f"detector={self.detector_class}. Remove PII before calling this agent "
                f"or set action=PolicyAction.REDACT. "
                f"See: https://github.com/wimverleyen/praktor.ai#governance-quickstart"
            )
        return base


class EvaluationFailedError(Exception):
    """Raised when an EvaluationPass with on_fail=BLOCK produces a failing score."""
