from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import TYPE_CHECKING

from pydantic import BaseModel

from praktor.aigov.event import AgentPattern

if TYPE_CHECKING:
    from praktor.aigov.bundle import ObligationBundle
    from praktor.governance.policy import GovernancePolicy


class MemoryPolicy(Enum):
    NONE = auto()         # Stateless — no history between calls
    SHORT_TERM = auto()   # In-memory circular buffer, keyed by session_id
    LONG_TERM = auto()    # FAISS semantic retrieval from document store


class OutputSink(Enum):
    STREAM = auto()  # Yield chunks to caller (stdout / WebSocket)
    FILE = auto()    # Write final response to markdown file
    BOTH = auto()    # Stream AND write to file


@dataclass
class ImprovementPass:
    """A follow-up LLM pass that receives the previous response as input."""
    prompt_template: str
    output_key: str = "previous_response"


@dataclass
class AgentDefinition:
    """
    Declarative unit for a single agent.

    Adding a new agent = one file with one AgentDefinition instance.
    No changes to schemas, dispatch tables, or consumers required.

    governance_policy: attach a GovernancePolicy to enable PII/PHI detection,
    audit logging, and RBAC for this agent. Default None = governance disabled,
    existing behavior unchanged (fully backwards compatible).
    """

    name: str
    """Unique identifier. Must match the agent_type field in queue messages."""

    prompt_template: str
    """Jinja2/f-string prompt. Variables must match input_schema fields."""

    input_schema: type[BaseModel]
    """Pydantic model used to validate incoming messages."""

    llm_model: str = "qwen2.5"
    """LLM model string passed to LLMFactory.create_llm()."""

    temperature: float = 0.0
    """0.0 = deterministic (cache-eligible). >0 = creative."""

    tools: list[str] = field(default_factory=list)
    """Tool names from the ToolRegistry. Empty = no tool use."""

    memory_policy: MemoryPolicy = MemoryPolicy.NONE
    """Controls which Memory implementation is injected."""

    output_sink: OutputSink = OutputSink.STREAM
    """Where to send the final response."""

    output_file: str = ""
    """Filename stem for FILE / BOTH output (relative to MD env path)."""

    improvement_passes: list[ImprovementPass] = field(default_factory=list)
    """
    Optional follow-up LLM passes (e.g., cover letter improvement).
    Each pass receives the previous response under the pass's output_key.
    """

    max_steps: int = 1
    """1 = single linear chain. >1 = ReAct tool-use loop (requires tools)."""

    prompt_version: str = ""
    """Optional explicit version label (e.g. 'v1.2.0'). Defaults to first 12 chars of hash."""

    # Auto-computed at post-init — do not set manually.
    prompt_template_hash: str = field(default="", init=False, repr=False)

    governance_policy: GovernancePolicy | None = None
    """
    Optional compliance governance for this agent.

    When set, Agent.run() will:
    - Run pre_execution DetectorConfigs on all string fields in the payload
    - Run post_execution DetectorConfigs on the full LLM response
    - Write an AuditEntry to all configured audit sinks
    - Raise GovernancePolicyViolation on BLOCK actions

    Governance boundary: detection covers the rendered prompt (all payload string
    fields) and the final LLM response. Intermediate tool call outputs inside LCEL
    chains are NOT governed — documented limitation.

    Default None = governance disabled. Backwards compatible with all existing agents.
    """

    agent_pattern: AgentPattern = AgentPattern.B1
    """
    AIGov §7 behavioral pattern classification (B1-B7). Written into every
    ObligationEvent so the Scoreboard can group agents by risk profile.

    Default B1 (simple retrieval-augmented QA). Override for:
        B3 — ReAct tool-use loop (max_steps > 1 with tools)
        B4 — Multi-agent orchestrator
        B5 — Human-in-the-loop supervised
        B6 — Autonomous long-horizon task
    """

    obligation_bundle: ObligationBundle | None = None
    """
    AIGov obligation bundle for this agent. When set, obligation checks are
    run at G-RUN and results emitted to the ledger. Replaces governance_policy
    as the primary compliance abstraction (Decision 2A).

    If obligation_bundle is None and governance_policy is set, __post_init__
    auto-converts governance_policy to an ObligationBundle via the shim
    (Decision 11A). obligation_bundle always wins if both are provided.
    """

    def __post_init__(self) -> None:
        template_bytes = self.prompt_template.encode("utf-8", errors="replace")
        self.prompt_template_hash = hashlib.sha256(template_bytes).hexdigest()
        if not self.prompt_version:
            self.prompt_version = self.prompt_template_hash[:12]

        # Decision 2A: auto-convert governance_policy → obligation_bundle when
        # obligation_bundle is not explicitly set.
        if self.obligation_bundle is None and self.governance_policy is not None:
            self.obligation_bundle = self.governance_policy.to_obligation_bundle()
