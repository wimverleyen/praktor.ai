from dataclasses import dataclass, field
from enum import Enum, auto
from pydantic import BaseModel


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
