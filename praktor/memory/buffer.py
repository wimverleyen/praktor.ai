from collections import defaultdict, deque


class InMemoryBuffer:
    """
    Short-term conversation memory backed by an in-process circular buffer.

    Keyed by session_id. Each entry is a turn dict:
        {"role": "user"|"assistant"|"context", "content": str}

    When the buffer reaches max_turns, the oldest turn is discarded.
    Process-local only — resets on restart. Use FAISSMemory for persistence.
    """

    def __init__(self, max_turns: int = 10):
        self._store: dict[str, deque[dict]] = defaultdict(
            lambda: deque(maxlen=max_turns)
        )

    async def load(self, session_id: str) -> list[dict]:
        return list(self._store[session_id])

    async def save(self, session_id: str, turn: dict) -> None:
        self._store[session_id].append(turn)

    async def clear(self, session_id: str) -> None:
        self._store[session_id].clear()

    def active_sessions(self) -> list[str]:
        return [sid for sid, buf in self._store.items() if buf]
