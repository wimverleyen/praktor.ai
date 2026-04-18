from __future__ import annotations

import json
from typing import AsyncGenerator

from praktor.core.agent import Agent
from praktor.core.agent_definition import AgentDefinition
from praktor.settings import PRAKTOR_RBAC_SECRET, new_request_id, create_log

log = create_log()


class Router:
    """
    Dynamic dispatch table for the agentic queue.

    Agents are registered with register() at startup. The Router validates
    each incoming message against the agent's Pydantic input_schema, then
    streams the response back as an async generator.

    RBAC: if an agent's GovernancePolicy has rbac_required_roles, the caller
    must include a "caller_token" field in the message. The token is verified
    via HMAC-SHA256 against PRAKTOR_RBAC_SECRET. Fail-closed: missing secret
    + non-empty roles = ConfigurationError (never silently open access).

    Adding a new agent:
        router.register(MyAgentDefinition)
    That's it — no changes to the consumer or dispatch table.
    """

    def __init__(self):
        self._agents: dict[str, Agent] = {}

    def register(self, definition: AgentDefinition) -> None:
        """
        Compile and register an agent. Call once at process startup.

        ConfigurationError raised at registration time if:
        - rbac_required_roles is non-empty AND PRAKTOR_RBAC_SECRET is absent.
        Fail-closed at startup, not at request time.
        """
        from praktor.governance.rbac import ConfigurationError

        if definition.governance_policy:
            policy = definition.governance_policy
            if policy.rbac_required_roles and not PRAKTOR_RBAC_SECRET:
                raise ConfigurationError(
                    f"Agent '{definition.name}' requires RBAC roles "
                    f"{policy.rbac_required_roles} but PRAKTOR_RBAC_SECRET is not set. "
                    "Set PRAKTOR_RBAC_SECRET in the environment to enable RBAC."
                )

        self._agents[definition.name] = Agent(definition)
        log.info(f"Registered agent: '{definition.name}' model={definition.llm_model}")

    def registered(self) -> list[str]:
        """Return names of all registered agents."""
        return list(self._agents.keys())

    async def dispatch(self, raw: bytes) -> AsyncGenerator[str, None]:
        """
        Parse, validate, and route a raw queue message.

        Message format:
            {
                "agent_type": "...",
                "session_id": "...",          # optional
                "caller_token": "...",         # required if agent has rbac_required_roles
                ... agent-specific fields ...
            }

        Raises:
            ValueError: unknown agent_type or schema validation failure
            RBACError:  invalid/expired/replayed token, missing required role
            GovernancePolicyViolation: pre-execution policy BLOCK
        """
        from praktor.governance.rbac import verify_token, RBACError

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

        # ----------------------------------------------------------------
        # RBAC check (only when governance_policy has rbac_required_roles)
        # ----------------------------------------------------------------
        caller_identity = "anonymous"
        policy = agent.definition.governance_policy

        if policy and policy.rbac_required_roles:
            caller_token = data.get("caller_token", "")
            if not caller_token:
                raise RBACError(
                    f"Agent '{agent_type}' requires RBAC token but 'caller_token' "
                    "field is missing from the message."
                )
            identity = verify_token(
                token=caller_token,
                secret=PRAKTOR_RBAC_SECRET,
                required_roles=policy.rbac_required_roles,
            )
            caller_identity = identity.caller_id
            log.debug(
                f"RBAC verified caller='{caller_identity}' "
                f"roles={identity.roles} agent='{agent_type}'"
            )

        # ----------------------------------------------------------------
        # Schema validation
        # ----------------------------------------------------------------
        try:
            validated = agent.definition.input_schema(**data)
        except Exception as e:
            raise ValueError(f"Schema validation failed for '{agent_type}': {e}") from e

        session_id = data.get("session_id") or new_request_id()
        log.debug(f"Dispatching agent_type='{agent_type}' session={session_id}")

        async for chunk in agent.run(
            validated.model_dump(),
            session_id,
            caller_identity=caller_identity,
        ):
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
