"""
O2 Sensitive Data Confinement — AIGov obligation.

Verifies that PHI/PII does not escape the declared egress boundary.

G-BUILD: lint the DataFlowManifest for completeness (phi_fields, egress declared).
G-TEST:  run the PII detector over labelled test records; measure recall.
G-RUN:   run the PII detector over each LLM response; FAIL on any detection.

Wraps praktor.governance.detectors.RegexDetector by default.
Swap in PresidioDetector for full HIPAA recall:
    O2DataConfinement(detector=PresidioDetector())
"""
from __future__ import annotations

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
from praktor.governance.detectors import PIIDetector, RegexDetector, RegexEntities

_DEFAULT_ENTITIES = [
    RegexEntities.US_SSN,
    RegexEntities.EMAIL_ADDRESS,
    RegexEntities.PHONE_NUMBER,
    RegexEntities.DATE_OF_BIRTH,
    RegexEntities.CREDIT_CARD,
]
_RECALL_THRESHOLD = 0.8
_REGULATORY_TAGS = ["HIPAA.164.514", "EU_AI_ACT.Art10"]


class O2DataConfinement(Obligation):
    id = "O2"
    name = "Sensitive Data Confinement"
    MEASUREMENT_TECHNIQUES = {
        "G-BUILD": "2.1.1",
        "G-TEST": "2.1.2",
        "G-RUN": "2.1.3",
    }

    def __init__(
        self,
        detector: PIIDetector | None = None,
        entities: list[str] | None = None,
    ) -> None:
        self.detector = detector or RegexDetector()
        self.entities = entities or _DEFAULT_ENTITIES

    async def check_build(self, manifest: DataFlowManifest) -> ObligationEvent:
        """Lint the DataFlowManifest: phi_fields, egress destinations, and deployer must all be declared."""
        issues: list[str] = []
        if not manifest.phi_fields:
            issues.append("phi_fields_not_declared")
        if not manifest.allowed_egress_destinations:
            issues.append("allowed_egress_destinations_not_declared")
        if not manifest.deployer:
            issues.append("deployer_not_declared")

        passed = not issues
        evidence_bytes, sha256 = make_evidence({
            "obligation": self.id,
            "enforcement_point": "G-BUILD",
            "phi_fields_count": len(manifest.phi_fields),
            "egress_destinations": manifest.allowed_egress_destinations,
            "deployer_set": bool(manifest.deployer),
            "signed_at": str(manifest.signed_at),
            "issues": issues,
        })
        return self._event(
            EnforcementPoint.G_BUILD,
            PredicateResult.PASS if passed else PredicateResult.FAIL,
            severity=Severity.HIGH if not passed else Severity.INFO,
            regulatory_tags=_REGULATORY_TAGS,
            evidence=EvidenceRef(uri="", sha256=sha256, size_bytes=len(evidence_bytes)),
        )

    async def check_test(self, dataset: PrivacyTestDataset) -> ObligationEvent:
        """Measure detector recall on labelled records. Records with label='none' are excluded."""
        labeled = [
            (record, label)
            for record, label in zip(dataset.records, dataset.labels)
            if label != "none"
        ]
        if not labeled:
            return self._na_event(EnforcementPoint.G_TEST, "no_labeled_test_records")

        detected = 0
        for record, _label in labeled:
            text = " ".join(str(v) for v in record.values())
            hits = await self.detector.detect(text, self.entities)
            if hits:
                detected += 1

        recall = detected / len(labeled)
        passed = recall >= _RECALL_THRESHOLD

        evidence_bytes, sha256 = make_evidence({
            "obligation": self.id,
            "enforcement_point": "G-TEST",
            "labeled_records": len(labeled),
            "detected": detected,
            "recall": round(recall, 3),
            "threshold": _RECALL_THRESHOLD,
        })
        return self._event(
            EnforcementPoint.G_TEST,
            PredicateResult.PASS if passed else PredicateResult.FAIL,
            severity=Severity.HIGH if not passed else Severity.INFO,
            regulatory_tags=_REGULATORY_TAGS,
            evidence=EvidenceRef(uri="", sha256=sha256, size_bytes=len(evidence_bytes)),
        )

    async def check_run(self, payload: str, response: str) -> ObligationEvent:
        """Detect PHI in the LLM response. Any detection → FAIL."""
        results = await self.detector.detect(response, self.entities)
        detections = [
            {"entity_type": r.entity_type, "score": r.score}
            for r in results
        ]
        passed = len(detections) == 0

        evidence_bytes, sha256 = make_evidence({
            "obligation": self.id,
            "enforcement_point": "G-RUN",
            "entities_checked": self.entities,
            "detection_count": len(detections),
            "detections": detections[:20],
            "response_length": len(response),
        })
        return self._event(
            EnforcementPoint.G_RUN,
            PredicateResult.PASS if passed else PredicateResult.FAIL,
            severity=Severity.CRITICAL if not passed else Severity.INFO,
            regulatory_tags=_REGULATORY_TAGS,
            evidence=EvidenceRef(uri="", sha256=sha256, size_bytes=len(evidence_bytes)),
        )
