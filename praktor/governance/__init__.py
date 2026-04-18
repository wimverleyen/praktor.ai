"""
praktor.governance — compliance layer for regulated industry deployments.

Public API:

    GovernancePolicy   — attach to AgentDefinition to enable governance
    DetectorConfig     — configure one PII/PHI detector pass
    PolicyAction       — ALLOW / REDACT / FLAG / BLOCK
    AuditSinkType      — LOCAL_FILE / STDOUT (KAFKA / MINIO: Phase 2)
    GovernancePolicyViolation — raised on BLOCK action

    RegexDetector      — zero-dep pattern-based detector (SSN, email, phone, ...)
    PresidioDetector   — ML-based full PHI detector (pip install praktor[presidio])
    PIIDetector        — protocol to implement custom detectors

    AuditEntry         — one immutable record per agent execution
    LocalFileAuditSink — append-only JSONL log with hash-chaining + filelock
    StdoutAuditSink    — development/testing sink

    CallerIdentity     — authenticated caller + roles
    issue_token        — create an HMAC-SHA256 RBAC token
    verify_token       — verify token, raise RBACError on failure
    RBACError          — raised when token verification fails
    ConfigurationError — raised when RBAC is misconfigured
"""
from praktor.governance.policy import (
    GovernancePolicy,
    DetectorConfig,
    PolicyAction,
    AuditSinkType,
    GovernancePolicyViolation,
    EvaluationFailedError,
)
from praktor.governance.helpers import block_pii
from praktor.governance.detectors import (
    PIIDetector,
    DetectionResult,
    RegexDetector,
    RegexEntities,
    PresidioDetector,
    DetectorUnavailableError,
    load_detector,
)
from praktor.governance.audit import (
    AuditEntry,
    AuditSink,
    LocalFileAuditSink,
    StdoutAuditSink,
)
from praktor.governance.rbac import (
    CallerIdentity,
    issue_token,
    verify_token,
    RBACError,
    ConfigurationError,
)
from praktor.governance.evaluators import (
    Evaluator,
    EvaluationPass,
    EvaluatorUnavailableError,
    load_evaluator,
)

__all__ = [
    # Policy
    "GovernancePolicy",
    "DetectorConfig",
    "PolicyAction",
    "AuditSinkType",
    "GovernancePolicyViolation",
    "EvaluationFailedError",
    # Convenience
    "block_pii",
    # Detectors
    "PIIDetector",
    "DetectionResult",
    "RegexDetector",
    "RegexEntities",
    "PresidioDetector",
    "DetectorUnavailableError",
    "load_detector",
    # Evaluators
    "Evaluator",
    "EvaluationPass",
    "EvaluatorUnavailableError",
    "load_evaluator",
    # Audit
    "AuditEntry",
    "AuditSink",
    "LocalFileAuditSink",
    "StdoutAuditSink",
    # RBAC
    "CallerIdentity",
    "issue_token",
    "verify_token",
    "RBACError",
    "ConfigurationError",
]
