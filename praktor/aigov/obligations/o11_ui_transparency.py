"""
O11 User Interface Transparency — AIGov obligation.

In every interaction, the agent SHALL (a) disclose its AI nature and operational
scope before or at first use, (b) invoke an uncertainty fallback when model
confidence falls below the deployment's declared threshold, and (c) provide source
attribution for retrieval-sourced claims. User override controls SHALL be available.

Applicability is gated on the HAI taxonomy classification (§27.1): O11 is required
for any External user-type deployment. Internal-only deployments may waive.

G-BUILD: Transparency Manifest exists; disclosure schema declared; fallback configured.
G-TEST:  disclosure rate ≥ 0.95 on identity-probing prompts; 3 LLM-as-Judge judges.
G-RUN:   live disclosure rate; misunderstanding signal rate ≤ 10%; S-TIAS ≥ 3.5/5.0.

Deferred: HAI taxonomy classification + Transparency Manifest not yet built.
All three enforcement points emit NA until that infrastructure ships.
"""
from __future__ import annotations

from praktor.aigov.event import EnforcementPoint
from praktor.aigov.manifests import DataFlowManifest, PrivacyTestDataset
from praktor.aigov.obligations.base import Obligation, ObligationEvent

_REGULATORY_TAGS = ["EU_AI_ACT.Art13", "NIST_AI_RMF.GOVERN_1.7", "HAI_FRAMEWORK_V2.ModuleE", "FTC.AI_GUIDELINES"]


class O11UITransparency(Obligation):
    id = "O11"
    name = "User Interface Transparency"
    MEASUREMENT_TECHNIQUES = {
        "G-BUILD": "11.1.1",
        "G-TEST": "11.1.2",
        "G-RUN": "11.1.3",
    }

    async def check_build(self, manifest: DataFlowManifest) -> ObligationEvent:
        return self._na_event(
            EnforcementPoint.G_BUILD,
            "transparency_manifest_not_implemented",
        )

    async def check_test(self, dataset: PrivacyTestDataset) -> ObligationEvent:
        return self._na_event(
            EnforcementPoint.G_TEST,
            "hai_taxonomy_judges_not_implemented",
        )

    async def check_run(self, payload: str, response: str) -> ObligationEvent:
        return self._na_event(
            EnforcementPoint.G_RUN,
            "stias_monitor_not_implemented",
        )
