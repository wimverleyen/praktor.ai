"""
Evaluation pass protocol and reference implementations.

Evaluator protocol: implement score(prompt, response) -> float (0.0-1.0).
EvaluationPass: configuration for one evaluator in a GovernancePolicy.

Phase 2 ships two reference evaluators:
- RegexToxicityEvaluator: blocklist-based, zero ML deps
- EmbeddingRelevanceEvaluator: cosine similarity via OllamaEmbeddings
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from governance.policy import PolicyAction


@runtime_checkable
class Evaluator(Protocol):
    """Protocol for post-execution response evaluators."""

    metric_name: str

    async def score(self, prompt: str, response: str) -> float:
        """
        Score the response quality. Returns 0.0-1.0 (higher = better).

        Implementations must be deterministic for the same input.
        If the evaluator cannot produce a score (e.g., missing model),
        it should raise EvaluatorUnavailableError (fail-closed).
        """
        ...


@dataclass
class EvaluationPass:
    """
    Configuration for one post-execution evaluation pass.

    Appended to AuditEntry.evaluation_scores after scoring.
    If score < pass_threshold, the on_fail action fires:
    - FLAG: audit_entry.flagged = True, agent continues
    - BLOCK: raise EvaluationFailedError, agent halts
    """

    evaluator_class: str
    """Import path, e.g. 'governance.evaluators.toxicity.RegexToxicityEvaluator'"""

    metric_name: str
    """e.g. 'toxicity', 'relevance', 'groundedness'"""

    pass_threshold: float = 0.8
    """Score >= threshold = pass. Default: 0.8"""

    on_fail: PolicyAction = PolicyAction.FLAG
    """FLAG: surface in metadata, continue. BLOCK: raise EvaluationFailedError."""


class EvaluatorUnavailableError(Exception):
    """Raised when an evaluator cannot initialize. Fails closed."""


def load_evaluator(import_path: str) -> Evaluator:
    """
    Import an evaluator class by dotted path and return an instance.

    Example: load_evaluator("governance.evaluators.toxicity.RegexToxicityEvaluator")
    """
    parts = import_path.rsplit(".", 1)
    if len(parts) != 2:
        raise ValueError(f"Invalid evaluator import path: {import_path!r}")
    module_path, class_name = parts
    import importlib
    mod = importlib.import_module(module_path)
    cls = getattr(mod, class_name)
    return cls()
