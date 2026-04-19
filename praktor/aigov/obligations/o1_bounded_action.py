"""
O1 Bounded Action Space — AIGov obligation.

The agent SHALL NOT invoke any tool, API, or action not declared in its
signed Action Manifest at deployment time.

G-BUILD: verify Action Manifest exists and is signed; static call-graph analysis.
G-TEST:  AgentBench golden set; adversarial prompts attempting undeclared tools.
G-RUN:   OPA policy engine blocks any undeclared tool call; violations logged.

Deferred: Action Manifest + OPA policy-engine infrastructure not yet built.
All three enforcement points emit NA until that infrastructure ships.
"""
from __future__ import annotations

from praktor.aigov.event import EnforcementPoint
from praktor.aigov.manifests import DataFlowManifest, PrivacyTestDataset
from praktor.aigov.obligations.base import Obligation, ObligationEvent

_REGULATORY_TAGS = ["EU_AI_ACT.Art14", "ISO_IEC_42001.A.6.2.6"]


class O1BoundedAction(Obligation):
    id = "O1"
    name = "Bounded Action Space"
    MEASUREMENT_TECHNIQUES = {
        "G-BUILD": "1.1.1",
        "G-TEST": "1.1.2",
        "G-RUN": "1.1.3",
    }

    async def check_build(self, manifest: DataFlowManifest) -> ObligationEvent:
        return self._na_event(
            EnforcementPoint.G_BUILD,
            "action_manifest_not_implemented",
        )

    async def check_test(self, dataset: PrivacyTestDataset) -> ObligationEvent:
        return self._na_event(
            EnforcementPoint.G_TEST,
            "agentbench_harness_not_implemented",
        )

    async def check_run(self, payload: str, response: str) -> ObligationEvent:
        return self._na_event(
            EnforcementPoint.G_RUN,
            "opa_policy_engine_not_implemented",
        )
