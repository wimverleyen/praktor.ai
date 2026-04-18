"""
ObligationBundle — the primary governance abstraction for an AIGov-compliant agent.

Replace GovernancePolicy on AgentDefinition with ObligationBundle to get a
Scoreboard-visible, Attestation-eligible compliance record (PR5).

A bundle is a plain list of Obligation instances plus a bundle_id string.
Pre-built bundles (HEALTHCARE_DEFAULT, MINIMAL, etc.) are added in PR5.

Usage (direct):
    from praktor.aigov.bundle import ObligationBundle
    from praktor.aigov.obligations.o2_data_confinement import O2DataConfinement
    from praktor.aigov.obligations.o7_auditable import O7Auditable

    bundle = ObligationBundle(
        obligations=[O2DataConfinement(), O7Auditable()],
        bundle_id="my-agent-v1",
    )
    defn = AgentDefinition(..., obligation_bundle=bundle)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from praktor.aigov.obligations.base import Obligation


@dataclass
class ObligationBundle:
    """
    Declares which AIGov obligations an agent holds.

    Attributes:
        obligations:  List of Obligation instances to evaluate.
        bundle_id:    Stable identifier written into every ObligationEvent.
                      Use a versioned string (e.g. 'healthcare-v1.2').
        description:  Human-readable description for the Scoreboard.
    """

    obligations: list[Obligation]
    bundle_id: str = "custom"
    description: str = ""

    def obligation_ids(self) -> list[str]:
        """Return the obligation IDs held by this bundle."""
        return [ob.id for ob in self.obligations]

    def get(self, obligation_id: str) -> Obligation | None:
        """Look up an obligation by its ID. Returns None if not held."""
        return next((ob for ob in self.obligations if ob.id == obligation_id), None)

    def __len__(self) -> int:
        return len(self.obligations)

    def __iter__(self):
        return iter(self.obligations)
