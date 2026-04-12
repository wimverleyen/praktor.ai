import json
from typing import AsyncGenerator

from core.agent import Agent
from core.agent_definition import AgentDefinition
from settings import new_request_id, create_log

log = create_log()


class Router:
    """
    Dynamic dispatch table for the agentic queue.

    Agents are registered with register() at startup. The Router validates
    each incoming message against the agent's Pydantic input_schema, then
    streams the response back as an async generator.

    Adding a new agent:
        router.register(MyAgentDefinition)
    That's it — no changes to the consumer or dispatch table.
    """

    def __init__(self):
        self._agents: dict[str, Agent] = {}

    def register(self, definition: AgentDefinition) -> None:
        """Compile and register an agent. Call once at process startup."""
        self._agents[definition.name] = Agent(definition)
        log.info(f"Registered agent: '{definition.name}' model={definition.llm_model}")

    def registered(self) -> list[str]:
        """Return names of all registered agents."""
        return list(self._agents.keys())

    async def dispatch(self, raw: bytes) -> AsyncGenerator[str, None]:
        """
        Parse, validate, and route a raw queue message.

        Raises ValueError for unknown agent_type or schema validation errors.
        All other exceptions propagate to the caller (consumer handles nack).
        """
        data = json.loads(raw)
        agent_type = data.get("agent_type")

        if not agent_type:
            raise ValueError("Message missing required field: agent_type")

        if agent_type not in self._agents:
            raise ValueError(
                f"Unknown agent_type '{agent_type}'. "
                f"Registered: {self.registered()}"
            )

        agent = self._agents[agent_type]

        # Validate against the agent's Pydantic input schema
        try:
            validated = agent.definition.input_schema(**data)
        except Exception as e:
            raise ValueError(f"Schema validation failed for '{agent_type}': {e}") from e

        session_id = data.get("session_id") or new_request_id()
        log.debug(f"Dispatching agent_type='{agent_type}' session={session_id}")

        async for chunk in agent.run(validated.model_dump(), session_id):
            yield chunk


# ---------------------------------------------------------------------------
# Global singleton — imported by agents/__init__.py and transport/consumer.py
# ---------------------------------------------------------------------------

_GLOBAL_ROUTER: Router | None = None


def get_global_router() -> Router:
    """Return (or create) the process-wide Router singleton."""
    global _GLOBAL_ROUTER
    if _GLOBAL_ROUTER is None:
        _GLOBAL_ROUTER = Router()
    return _GLOBAL_ROUTER
