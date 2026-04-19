"""
O8 Human Oversight Integrity — AIGov obligation.

Every agent action in a HITL-required class SHALL require a documented human
decision before execution. Reviewer identity, decision, duration, and outcome
SHALL be logged. Cohen's κ ≥ 0.75 among active reviewers.

G-BUILD: HITL workflow wired; reviewer pool configured.
G-TEST:  calibration on 50-case labeled library; κ ≥ 0.75; OVA Score ≥ 0.
G-RUN:   review-duration SPC; monthly κ recomputation; override quality sampling.

Deferred: HITL platform + reviewer-calibration infrastructure not yet built.
All three enforcement points emit NA until that infrastructure ships.
"""
from __future__ import annotations

from praktor.aigov.event import EnforcementPoint
from praktor.aigov.manifests import DataFlowManifest, PrivacyTestDataset
from praktor.aigov.obligations.base import Obligation, ObligationEvent

_REGULATORY_TAGS = ["EU_AI_ACT.Art14", "JOINT_COMMISSION.CDS"]


class O8HumanOversight(Obligation):
    id = "O8"
    name = "Human Oversight Integrity"
    MEASUREMENT_TECHNIQUES = {
        "G-BUILD": "8.1.1",
        "G-TEST": "8.1.2",
        "G-RUN": "8.1.3",
    }

    async def check_build(self, manifest: DataFlowManifest) -> ObligationEvent:
        return self._na_event(
            EnforcementPoint.G_BUILD,
            "hitl_platform_not_implemented",
        )

    async def check_test(self, dataset: PrivacyTestDataset) -> ObligationEvent:
        return self._na_event(
            EnforcementPoint.G_TEST,
            "reviewer_calibration_not_implemented",
        )

    async def check_run(self, payload: str, response: str) -> ObligationEvent:
        return self._na_event(
            EnforcementPoint.G_RUN,
            "hitl_review_monitor_not_implemented",
        )
