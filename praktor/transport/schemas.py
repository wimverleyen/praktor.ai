from __future__ import annotations
"""
Dynamic message schema registry.

The Router builds its own validation from AgentDefinition.input_schema,
so this module is thin: it just re-exports parse_message() for backwards
compatibility and provides a helper to list all registered schemas.
"""

from core.router import get_global_router


def parse_message(data: dict):
    """
    Validate a raw dict against the registered agent's input schema.

    Raises ValueError for unknown agent_type or validation errors.
    """
    router = get_global_router()
    agent_type = data.get("agent_type")

    if not agent_type:
        raise ValueError("Missing required field: agent_type")

    agents = {a: router._agents[a] for a in router.registered()}
    if agent_type not in agents:
        raise ValueError(
            f"Unknown agent_type '{agent_type}'. "
            f"Registered: {list(agents.keys())}"
        )

    agent = agents[agent_type]
    return agent.definition.input_schema(**data)


def list_schemas() -> dict[str, list[str]]:
    """Return a map of agent_type → required input fields."""
    router = get_global_router()
    result = {}
    for name in router.registered():
        agent = router._agents[name]
        schema = agent.definition.input_schema
        result[name] = list(schema.model_fields.keys())
    return result
