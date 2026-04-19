"""
O9 Change Attestation Currency — AIGov obligation.

No production deployment SHALL run a model, prompt, tool set, or knowledge base
version for which the active Attestation is older than the Change Impact Matrix
requires. Scoped re-evaluation SHALL complete within 48h of a MAJOR-class change.

G-BUILD: CIM rules configured per change type; semver enforced.
G-TEST:  simulation: inject synthetic MAJOR change; pipeline completes in < 48h;
         Attestation currency ≤ 30 days at test-env deploy time.
G-RUN:   CI/CD gate blocks deploy if Attestation out of date; time-based expiry.

Deferred: CIM infrastructure + Attestation-currency gate not yet built.
All three enforcement points emit NA until that infrastructure ships.
"""
from __future__ import annotations

from praktor.aigov.event import EnforcementPoint
from praktor.aigov.manifests import DataFlowManifest, PrivacyTestDataset
from praktor.aigov.obligations.base import Obligation, ObligationEvent

_REGULATORY_TAGS = ["ISO_IEC_42001.Cl9", "NIST_AI_RMF.MANAGE_1.4"]


class O9ChangeAttestation(Obligation):
    id = "O9"
    name = "Change Attestation Currency"
    MEASUREMENT_TECHNIQUES = {
        "G-BUILD": "9.1.1",
        "G-TEST": "9.1.2",
        "G-RUN": "9.1.3",
    }

    async def check_build(self, manifest: DataFlowManifest) -> ObligationEvent:
        return self._na_event(
            EnforcementPoint.G_BUILD,
            "cim_rules_not_implemented",
        )

    async def check_test(self, dataset: PrivacyTestDataset) -> ObligationEvent:
        return self._na_event(
            EnforcementPoint.G_TEST,
            "attestation_currency_simulation_not_implemented",
        )

    async def check_run(self, payload: str, response: str) -> ObligationEvent:
        return self._na_event(
            EnforcementPoint.G_RUN,
            "attestation_expiry_gate_not_implemented",
        )
