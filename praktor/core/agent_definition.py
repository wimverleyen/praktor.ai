from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import TYPE_CHECKING

from pydantic import BaseModel

if TYPE_CHECKING:
    from governance.policy import GovernancePolicy


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

    def __post_init__(self) -> None:
        template_bytes = self.prompt_template.encode("utf-8", errors="replace")
        self.prompt_template_hash = hashlib.sha256(template_bytes).hexdigest()
        if not self.prompt_version:
            self.prompt_version = self.prompt_template_hash[:12]
