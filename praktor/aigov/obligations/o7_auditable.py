"""
O7 Auditable — AIGov obligation.

Verifies that OTel tracing is configured and active so every agent run
produces a complete, tamper-evident audit trail.

G-BUILD: PASS if OTel is configured (PRAKTOR_OTEL_ENABLED or OTLP endpoint set).
         NA if OTel is explicitly disabled (OTEL_SDK_DISABLED=true).
G-TEST:  NA — span completeness cannot be verified from a static test dataset.
G-RUN:   PASS if the OTel tracer is initialized and active.
         NA if OTEL_SDK_DISABLED=true (explicitly opted out).
         FAIL if OTel was expected (PRAKTOR_OTEL_ENABLED) but not initialized.

Wraps praktor.core.observability module-level state.
"""
from __future__ import annotations

import os

from praktor.aigov.evidence import make_evidence
from praktor.aigov.event import (
    EnforcementPoint,
    EvidenceRef,
    ObligationEvent,
    PredicateResult,
    Severity,
)
from praktor.aigov.manifests import DataFlowManifest, PrivacyTestDataset
from praktor.aigov.obligations.base import Obligation

_REGULATORY_TAGS = ["EU_AI_ACT.Art17", "NIST_AI_RMF.MANAGE_4"]


def _otel_state() -> dict:
    """Read current OTel initialization state from the observability module."""
    try:
        import praktor.core.observability as _obs
        return {
            "sdk_disabled": _obs._OTEL_SDK_DISABLED,
            "tracer_initialized": _obs._tracer_initialized,
        }
    except Exception as exc:
        return {"sdk_disabled": False, "tracer_initialized": False, "import_error": str(exc)}


class O7Auditable(Obligation):
    id = "O7"
    name = "Auditable"
    MEASUREMENT_TECHNIQUES = {
        "G-BUILD": "7.1.1",
        "G-TEST": "7.1.2",
        "G-RUN": "7.1.3",
    }

    async def check_build(self, manifest: DataFlowManifest) -> ObligationEvent:
        """PASS if OTel is configured in the environment. NA if explicitly disabled."""
        state = _otel_state()

        if state.get("sdk_disabled"):
            evidence_bytes, sha256 = make_evidence({
                "obligation": self.id,
                "enforcement_point": "G-BUILD",
                **state,
            })
            return self._event(
                EnforcementPoint.G_BUILD,
                PredicateResult.NA,
                severity=Severity.INFO,
                deferred_reason="otel_sdk_disabled",
                regulatory_tags=_REGULATORY_TAGS,
                evidence=EvidenceRef(uri="", sha256=sha256, size_bytes=len(evidence_bytes)),
            )

        otel_enabled = os.environ.get("PRAKTOR_OTEL_ENABLED", "").lower() in ("1", "true", "yes")
        otlp_endpoint = bool(os.environ.get("PRAKTOR_OTLP_ENDPOINT", ""))
        configured = otel_enabled or otlp_endpoint

        evidence_bytes, sha256 = make_evidence({
            "obligation": self.id,
            "enforcement_point": "G-BUILD",
            "otel_enabled_env": otel_enabled,
            "otlp_endpoint_set": otlp_endpoint,
            **state,
        })
        return self._event(
            EnforcementPoint.G_BUILD,
            PredicateResult.PASS if configured else PredicateResult.FAIL,
            severity=Severity.MEDIUM if not configured else Severity.INFO,
            regulatory_tags=_REGULATORY_TAGS,
            evidence=EvidenceRef(uri="", sha256=sha256, size_bytes=len(evidence_bytes)),
        )

    async def check_test(self, dataset: PrivacyTestDataset) -> ObligationEvent:
        """NA — OTel span completeness cannot be verified from static test data."""
        return self._na_event(EnforcementPoint.G_TEST, "otel_not_testable_from_static_data")

    async def check_run(self, payload: str, response: str) -> ObligationEvent:
        """PASS if tracer is initialized, NA if SDK disabled, FAIL if expected but inactive."""
        state = _otel_state()
        sdk_disabled = state.get("sdk_disabled", False)
        initialized = state.get("tracer_initialized", False)
        otel_expected = os.environ.get("PRAKTOR_OTEL_ENABLED", "").lower() in ("1", "true", "yes")

        evidence_bytes, sha256 = make_evidence({
            "obligation": self.id,
            "enforcement_point": "G-RUN",
            **state,
            "otel_expected": otel_expected,
        })
        ev_ref = EvidenceRef(uri="", sha256=sha256, size_bytes=len(evidence_bytes))

        if sdk_disabled:
            return self._event(
                EnforcementPoint.G_RUN,
                PredicateResult.NA,
                severity=Severity.INFO,
                deferred_reason="otel_sdk_disabled",
                regulatory_tags=_REGULATORY_TAGS,
                evidence=ev_ref,
            )

        if initialized:
            return self._event(
                EnforcementPoint.G_RUN,
                PredicateResult.PASS,
                severity=Severity.INFO,
                regulatory_tags=_REGULATORY_TAGS,
                evidence=ev_ref,
            )

        if otel_expected:
            return self._event(
                EnforcementPoint.G_RUN,
                PredicateResult.FAIL,
                severity=Severity.MEDIUM,
                deferred_reason="otel_expected_but_not_initialized",
                regulatory_tags=_REGULATORY_TAGS,
                evidence=ev_ref,
            )

        return self._event(
            EnforcementPoint.G_RUN,
            PredicateResult.NA,
            severity=Severity.INFO,
            deferred_reason="otel_not_configured",
            regulatory_tags=_REGULATORY_TAGS,
            evidence=ev_ref,
        )
