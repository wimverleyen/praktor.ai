"""
AIGov Obligation abstract base class.

Every obligation (O1-O11) subclasses Obligation and implements three
async check methods — one per enforcement point.

Class-level constants (Decision 4A):
    id:                    Obligation identifier (e.g. "O2")
    name:                  Human-readable name
    MEASUREMENT_TECHNIQUES: AIGov measurement technique codes per enforcement point
                           {'G-BUILD': '2.1.1', 'G-TEST': '2.1.2', 'G-RUN': '2.1.3'}

All check methods are async (Decision 8A) so they can await detectors, LLM
judges, or I/O without blocking the event loop.

Deferred obligations (no infrastructure yet) MUST return predicate_result=NA
with a non-empty deferred_reason. Never return PASS for an unevaluated obligation.
(Decision 10A — prevents false attestation in the ledger.)
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar

from praktor.aigov.event import (
    AgentPattern,
    DeploymentEnv,
    EnforcementPoint,
    ObligationEvent,
    PredicateResult,
    Severity,
)
from praktor.aigov.manifests import DataFlowManifest, PrivacyTestDataset


class Obligation(ABC):
    """
    Abstract base for all AIGov obligations.

    Subclass this, set the class-level constants, and implement the three
    check methods. The _event() helper pre-stamps obligation_id,
    enforcement_point, and measurement_technique — use it in implementations
    to reduce boilerplate and ensure consistency.

    Agent context fields (agent_id, tenant_id, bundle_id, etc.) are stamped
    by the ObligationBundle caller, not by the obligation itself.
    """

    id: ClassVar[str]
    name: ClassVar[str]
    MEASUREMENT_TECHNIQUES: ClassVar[dict[str, str]]

    @abstractmethod
    async def check_build(self, manifest: DataFlowManifest) -> ObligationEvent:
        """G-BUILD enforcement: static analysis at deploy/CI time."""

    @abstractmethod
    async def check_test(self, dataset: PrivacyTestDataset) -> ObligationEvent:
        """G-TEST enforcement: evaluation against labelled test data at CI time."""

    @abstractmethod
    async def check_run(self, payload: str, response: str) -> ObligationEvent:
        """G-RUN enforcement: runtime check on a live payload/response pair."""

    # ------------------------------------------------------------------
    # Protected helper
    # ------------------------------------------------------------------

    def _event(
        self,
        enforcement_point: EnforcementPoint,
        predicate_result: PredicateResult,
        *,
        severity: Severity = Severity.INFO,
        deferred_reason: str = "",
        **kwargs,
    ) -> ObligationEvent:
        """
        Build an ObligationEvent pre-stamped with this obligation's id,
        enforcement_point, and measurement_technique.

        Pass any additional ObligationEvent fields as keyword args.
        Agent context (agent_id, tenant_id, etc.) is left at defaults —
        the ObligationBundle stamps those before ledger write.
        """
        return ObligationEvent(
            obligation_id=self.id,
            enforcement_point=enforcement_point,
            predicate_result=predicate_result,
            measurement_technique=self.MEASUREMENT_TECHNIQUES.get(
                enforcement_point.value, ""
            ),
            severity=severity,
            deferred_reason=deferred_reason,
            **kwargs,
        )

    def _na_event(
        self,
        enforcement_point: EnforcementPoint,
        deferred_reason: str,
    ) -> ObligationEvent:
        """Convenience: emit a NA event for a deferred/unimplemented check."""
        return self._event(
            enforcement_point=enforcement_point,
            predicate_result=PredicateResult.NA,
            severity=Severity.INFO,
            deferred_reason=deferred_reason,
        )
