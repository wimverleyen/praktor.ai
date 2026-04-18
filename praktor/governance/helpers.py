"""
Convenience helpers for the praktor governance layer.
"""
from __future__ import annotations

import dataclasses
from typing import Union

from praktor.core.agent_definition import AgentDefinition
from praktor.governance.policy import (
    GovernancePolicy,
    DetectorConfig,
    PolicyAction,
    AuditSinkType,
)


def block_pii(
    definition: AgentDefinition,
    entities: list[str],
    action: Union[str, PolicyAction] = "block",
    sink: Union[str, AuditSinkType] = "stdout",
) -> AgentDefinition:
    """
    One-liner governance setup. Returns a new AgentDefinition with pre-execution
    PII detection configured. The original definition is not mutated.

    Example:
        from praktor.governance import block_pii, RegexEntities
        defn = block_pii(defn, [RegexEntities.US_SSN, RegexEntities.EMAIL_ADDRESS])
    """
    action_enum = PolicyAction(action) if isinstance(action, str) else action
    sink_enum = AuditSinkType(sink) if isinstance(sink, str) else sink
    policy = GovernancePolicy(
        pre_execution=[
            DetectorConfig(
                detector_class="praktor.governance.detectors.RegexDetector",
                entities=list(entities),
                action=action_enum,
            )
        ],
        audit_sinks=[sink_enum],
    )
    return dataclasses.replace(definition, governance_policy=policy)
