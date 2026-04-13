from __future__ import annotations
from dataclasses import dataclass, field
from typing import Protocol, Any


@dataclass
class ToolResult:
    """Standardised return type for all tools."""
    content: str
    metadata: dict = field(default_factory=dict)
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


class Tool(Protocol):
    """
    Protocol for pluggable agent tools.

    Implement this protocol and call register_tool() to make a tool
    available to any AgentDefinition via its tools: list[str] field.
    """

    name: str
    """Unique key used in AgentDefinition.tools and ToolRegistry lookup."""

    description: str
    """Human-readable description injected into the ReAct system prompt."""

    async def __call__(self, input: str) -> ToolResult:
        """Execute the tool. Input is a plain string (query, filename, JSON, etc.)."""
        ...


# --- Global registry ---

_TOOL_REGISTRY: dict[str, Any] = {}


def register_tool(tool: Any) -> None:
    """Register a tool instance. Called once at module load time."""
    _TOOL_REGISTRY[tool.name] = tool


def get_tool(name: str) -> Any:
    if name not in _TOOL_REGISTRY:
        raise KeyError(
            f"Tool '{name}' not registered. Available: {list(_TOOL_REGISTRY.keys())}"
        )
    return _TOOL_REGISTRY[name]


def list_tools() -> list[str]:
    return list(_TOOL_REGISTRY.keys())
