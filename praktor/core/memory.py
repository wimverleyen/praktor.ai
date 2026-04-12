from typing import Protocol, runtime_checkable


@runtime_checkable
class Memory(Protocol):
    """
    Protocol for agent memory backends.

    Short-term: InMemoryBuffer (praktor/memory/buffer.py)
    Long-term:  FAISSMemory   (praktor/memory/vector.py)
    """

    async def load(self, session_id: str) -> list[dict]:
        """Return conversation history for this session as a list of turn dicts."""
        ...

    async def save(self, session_id: str, turn: dict) -> None:
        """Append a turn dict to this session's history."""
        ...

    async def clear(self, session_id: str) -> None:
        """Discard all history for this session."""
        ...


class NullMemory:
    """No-op memory for stateless agents (MemoryPolicy.NONE)."""

    async def load(self, session_id: str) -> list[dict]:
        return []

    async def save(self, session_id: str, turn: dict) -> None:
        pass

    async def clear(self, session_id: str) -> None:
        pass
