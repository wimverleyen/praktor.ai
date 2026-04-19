"""
O4 Fairness Non-Regression — AIGov obligation.

The agent SHALL NOT exceed the deployment's declared demographic parity
and equalized odds gaps across protected attributes.

G-BUILD: protected-attribute schema declared; eval dataset categorized.
G-TEST:  Fairlearn gaps on held-out test set; parity gap ≤ 0.05; odds gap ≤ 0.05.
G-RUN:   monthly drift scan; proxy-based monitoring when attributes unavailable.

Deferred: Fairlearn integration + protected-attribute schema not yet built.
All three enforcement points emit NA until that infrastructure ships.
"""
from __future__ import annotations

from praktor.aigov.event import EnforcementPoint
from praktor.aigov.manifests import DataFlowManifest, PrivacyTestDataset
from praktor.aigov.obligations.base import Obligation, ObligationEvent

_REGULATORY_TAGS = ["EU_AI_ACT.Art10.2f", "GDPR.Art22", "ACA.1557"]


class O4Fairness(Obligation):
    id = "O4"
    name = "Fairness Non-Regression"
    MEASUREMENT_TECHNIQUES = {
        "G-BUILD": "4.1.1",
        "G-TEST": "4.1.2",
        "G-RUN": "4.1.3",
    }

    async def check_build(self, manifest: DataFlowManifest) -> ObligationEvent:
        return self._na_event(
            EnforcementPoint.G_BUILD,
            "protected_attribute_schema_not_implemented",
        )

    async def check_test(self, dataset: PrivacyTestDataset) -> ObligationEvent:
        return self._na_event(
            EnforcementPoint.G_TEST,
            "fairlearn_harness_not_implemented",
        )

    async def check_run(self, payload: str, response: str) -> ObligationEvent:
        return self._na_event(
            EnforcementPoint.G_RUN,
            "fairness_drift_monitor_not_implemented",
        )
