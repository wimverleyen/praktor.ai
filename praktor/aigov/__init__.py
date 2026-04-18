"""
praktor.aigov — AIGov Obligations Framework (v0.5.0)

Implements AIGov Framework v0.3: 11 canonical obligations enforced at
G-BUILD, G-TEST, and G-RUN. Each check emits an ObligationEvent into
an append-only DuckDB ledger. Scoreboard and signed Attestation built on top.

Public API (fully available after PR5):
    ObligationBundle    — declare which obligations an agent holds
    ObligationEvent     — one compliance check result
    PredicateResult     — PASS / FAIL / WAIVED / NA
    AgentPattern        — B1-B7 behavioral pattern classification
    EnforcementPoint    — G-BUILD / G-TEST / G-RUN
    make_evidence       — canonical evidence blob + sha256

PR1 exports (interface contract):
"""
from praktor.aigov.event import (
    ObligationEvent,
    PredicateResult,
    AgentPattern,
    EnforcementPoint,
    DeploymentEnv,
    Severity,
    EvidenceRef,
    ReviewerRef,
    SourceRef,
)
from praktor.aigov.evidence import make_evidence
from praktor.aigov.manifests import DataFlowManifest, PrivacyTestDataset

__all__ = [
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
]
