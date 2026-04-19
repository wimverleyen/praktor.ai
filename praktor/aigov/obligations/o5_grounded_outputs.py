"""
O5 Grounded Outputs — AIGov obligation.

For retrieval-augmented tasks, every factual claim in the agent's output
SHALL be traceable to a cited source above the faithfulness threshold.

G-BUILD: retrieval config pinned; KB provenance declared.
G-TEST:  RAGAS faithfulness + citation precision on 500-query benchmark;
         faithfulness ≥ 0.90; citation precision ≥ 0.95.
G-RUN:   live faithfulness score on sampled responses; source-citation check.

Deferred: RAGAS integration + Golden Dataset not yet built.
All three enforcement points emit NA until that infrastructure ships.
"""
from __future__ import annotations

from praktor.aigov.event import EnforcementPoint
from praktor.aigov.manifests import DataFlowManifest, PrivacyTestDataset
from praktor.aigov.obligations.base import Obligation, ObligationEvent

_REGULATORY_TAGS = ["EU_AI_ACT.Art13", "EU_AI_ACT.Art15", "HIPAA.164.312b", "FDA.21CFR_Part11"]


class O5GroundedOutputs(Obligation):
    id = "O5"
    name = "Grounded Outputs"
    MEASUREMENT_TECHNIQUES = {
        "G-BUILD": "5.1.1",
        "G-TEST": "5.1.2",
        "G-RUN": "5.1.3",
    }

    async def check_build(self, manifest: DataFlowManifest) -> ObligationEvent:
        return self._na_event(
            EnforcementPoint.G_BUILD,
            "retrieval_config_manifest_not_implemented",
        )

    async def check_test(self, dataset: PrivacyTestDataset) -> ObligationEvent:
        return self._na_event(
            EnforcementPoint.G_TEST,
            "ragas_harness_not_implemented",
        )

    async def check_run(self, payload: str, response: str) -> ObligationEvent:
        return self._na_event(
            EnforcementPoint.G_RUN,
            "faithfulness_monitor_not_implemented",
        )
