"""AIGov obligation implementations — O1 through O11."""
from praktor.aigov.obligations.o1_bounded_action import O1BoundedAction
from praktor.aigov.obligations.o2_data_confinement import O2DataConfinement
from praktor.aigov.obligations.o3_content_safety import O3ContentSafety
from praktor.aigov.obligations.o4_fairness import O4Fairness
from praktor.aigov.obligations.o5_grounded_outputs import O5GroundedOutputs
from praktor.aigov.obligations.o6_goal_integrity import O6GoalIntegrity
from praktor.aigov.obligations.o7_auditable import O7Auditable
from praktor.aigov.obligations.o8_human_oversight import O8HumanOversight
from praktor.aigov.obligations.o9_change_attestation import O9ChangeAttestation
from praktor.aigov.obligations.o10_operational_invariants import O10OperationalInvariants
from praktor.aigov.obligations.o11_ui_transparency import O11UITransparency

__all__ = [
    "O1BoundedAction",
    "O2DataConfinement",
    "O3ContentSafety",
    "O4Fairness",
    "O5GroundedOutputs",
    "O6GoalIntegrity",
    "O7Auditable",
    "O8HumanOversight",
    "O9ChangeAttestation",
    "O10OperationalInvariants",
    "O11UITransparency",
]
