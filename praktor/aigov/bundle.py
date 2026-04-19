"""
ObligationBundle — the primary governance abstraction for an AIGov-compliant agent.

Replace GovernancePolicy on AgentDefinition with ObligationBundle to get a
Scoreboard-visible, Attestation-eligible compliance record.

A bundle is a plain list of Obligation instances plus a bundle_id string.

Pre-built factory functions follow the AIGov §3 selection rule:
  "Every deployment holds O1, O3, O7, O9, O10 at a minimum.
   O11 is required for any External user-type deployment."

    MINIMAL            — O7 only (internal tooling, auditing gate)
    standard_bundle()  — O1 + O3 + O7 + O9 + O10 (minimum required set)
    healthcare_bundle()— O1 + O2 + O3 + O7 + O8 + O9 + O10 (PHI + HITL)
    external_bundle()  — O1 + O3 + O7 + O9 + O10 + O11 (external-facing)

Usage (direct):
    from praktor.aigov.bundle import ObligationBundle, healthcare_bundle
    from praktor.aigov.obligations.o2_data_confinement import O2DataConfinement
    from praktor.aigov.obligations.o7_auditable import O7Auditable

    bundle = ObligationBundle(
        obligations=[O2DataConfinement(), O7Auditable()],
        bundle_id="my-agent-v1",
    )
    defn = AgentDefinition(..., obligation_bundle=bundle)

    # or use a pre-built bundle:
    defn = AgentDefinition(..., obligation_bundle=healthcare_bundle())
"""
from __future__ import annotations

from dataclasses import dataclass
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


# ---------------------------------------------------------------------------
# Pre-built bundle factories
# Lazy imports keep module load fast and avoid circular-import issues.
# Each factory returns a fresh ObligationBundle with new Obligation instances.
# ---------------------------------------------------------------------------

def minimal_bundle() -> ObligationBundle:
    """O7 only — auditing gate for simple internal tooling."""
    from praktor.aigov.obligations.o7_auditable import O7Auditable
    return ObligationBundle(
        obligations=[O7Auditable()],
        bundle_id="minimal-v1",
        description="Minimum viable: auditing only (O7).",
    )


def standard_bundle() -> ObligationBundle:
    """O1+O3+O7+O9+O10 — minimum required set per AIGov §3 selection rule."""
    from praktor.aigov.obligations.o1_bounded_action import O1BoundedAction
    from praktor.aigov.obligations.o3_content_safety import O3ContentSafety
    from praktor.aigov.obligations.o7_auditable import O7Auditable
    from praktor.aigov.obligations.o9_change_attestation import O9ChangeAttestation
    from praktor.aigov.obligations.o10_operational_invariants import O10OperationalInvariants
    return ObligationBundle(
        obligations=[
            O1BoundedAction(),
            O3ContentSafety(),
            O7Auditable(),
            O9ChangeAttestation(),
            O10OperationalInvariants(),
        ],
        bundle_id="standard-v1",
        description="Standard bundle: O1+O3+O7+O9+O10 (minimum required set).",
    )


def healthcare_bundle() -> ObligationBundle:
    """O1+O2+O3+O7+O8+O9+O10 — healthcare deployments handling PHI + HITL oversight."""
    from praktor.aigov.obligations.o1_bounded_action import O1BoundedAction
    from praktor.aigov.obligations.o2_data_confinement import O2DataConfinement
    from praktor.aigov.obligations.o3_content_safety import O3ContentSafety
    from praktor.aigov.obligations.o7_auditable import O7Auditable
    from praktor.aigov.obligations.o8_human_oversight import O8HumanOversight
    from praktor.aigov.obligations.o9_change_attestation import O9ChangeAttestation
    from praktor.aigov.obligations.o10_operational_invariants import O10OperationalInvariants
    return ObligationBundle(
        obligations=[
            O1BoundedAction(),
            O2DataConfinement(),
            O3ContentSafety(),
            O7Auditable(),
            O8HumanOversight(),
            O9ChangeAttestation(),
            O10OperationalInvariants(),
        ],
        bundle_id="healthcare-v1",
        description="Healthcare bundle: O1+O2+O3+O7+O8+O9+O10 (PHI + HITL).",
    )


def external_bundle() -> ObligationBundle:
    """O1+O3+O7+O9+O10+O11 — external-facing deployments (HAI taxonomy External user type)."""
    from praktor.aigov.obligations.o1_bounded_action import O1BoundedAction
    from praktor.aigov.obligations.o3_content_safety import O3ContentSafety
    from praktor.aigov.obligations.o7_auditable import O7Auditable
    from praktor.aigov.obligations.o9_change_attestation import O9ChangeAttestation
    from praktor.aigov.obligations.o10_operational_invariants import O10OperationalInvariants
    from praktor.aigov.obligations.o11_ui_transparency import O11UITransparency
    return ObligationBundle(
        obligations=[
            O1BoundedAction(),
            O3ContentSafety(),
            O7Auditable(),
            O9ChangeAttestation(),
            O10OperationalInvariants(),
            O11UITransparency(),
        ],
        bundle_id="external-v1",
        description="External-facing bundle: O1+O3+O7+O9+O10+O11 (UI transparency required).",
    )
