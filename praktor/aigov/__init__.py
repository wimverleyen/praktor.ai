"""
praktor.aigov — AIGov Obligations Framework (v0.5.0)

Implements AIGov Framework v0.3: 11 canonical obligations enforced at
G-BUILD, G-TEST, and G-RUN. Each check emits an ObligationEvent into
an append-only DuckDB ledger. Scoreboard and signed Attestation built on top.

Public API:
    ObligationBundle    — declare which obligations an agent holds
    ObligationEvent     — one compliance check result
    PredicateResult     — PASS / FAIL / WAIVED / NA
    AgentPattern        — B1-B7 behavioral pattern classification
    EnforcementPoint    — G-BUILD / G-TEST / G-RUN
    make_evidence       — canonical evidence blob + sha256

    AttestationRecord   — signed point-in-time scoreboard snapshot
    create_attestation  — build an AttestationRecord from scoreboard rows

    Pre-built bundle factories (each returns a fresh ObligationBundle):
        minimal_bundle()     — O7 only
        standard_bundle()    — O1+O3+O7+O9+O10
        healthcare_bundle()  — O1+O2+O3+O7+O8+O9+O10
        external_bundle()    — O1+O3+O7+O9+O10+O11
"""
from praktor.aigov.attestation import AttestationRecord, create_attestation
from praktor.aigov.bundle import (
    ObligationBundle,
    external_bundle,
    healthcare_bundle,
    minimal_bundle,
    standard_bundle,
)
from praktor.aigov.event import (
    AgentPattern,
    DeploymentEnv,
    EnforcementPoint,
    EvidenceRef,
    ObligationEvent,
    PredicateResult,
    ReviewerRef,
    Severity,
    SourceRef,
)
from praktor.aigov.evidence import make_evidence
from praktor.aigov.manifests import DataFlowManifest, PrivacyTestDataset

__all__ = [
    # Core event types
    "ObligationEvent",
    "PredicateResult",
    "AgentPattern",
    "EnforcementPoint",
    "DeploymentEnv",
    "Severity",
    "EvidenceRef",
    "ReviewerRef",
    "SourceRef",
    "make_evidence",
    "DataFlowManifest",
    "PrivacyTestDataset",
    # Bundle
    "ObligationBundle",
    "minimal_bundle",
    "standard_bundle",
    "healthcare_bundle",
    "external_bundle",
    # Attestation
    "AttestationRecord",
    "create_attestation",
]
