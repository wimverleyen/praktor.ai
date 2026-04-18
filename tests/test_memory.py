import sys
import asyncio
from pathlib import Path

import pytest
from praktor.core.memory import NullMemory
from praktor.memory.buffer import InMemoryBuffer


class TestNullMemory:

    @pytest.mark.asyncio
    async def test_load_returns_empty(self):
        mem = NullMemory()
        result = await mem.load("session1")
        assert result == []

    @pytest.mark.asyncio
    async def test_save_is_noop(self):
        mem = NullMemory()
        await mem.save("session1", {"role": "user", "content": "hello"})
        result = await mem.load("session1")
        assert result == []


class TestInMemoryBuffer:

    @pytest.mark.asyncio
    async def test_save_and_load(self):
        buf = InMemoryBuffer()
        await buf.save("s1", {"role": "user", "content": "hello"})
        await buf.save("s1", {"role": "assistant", "content": "world"})
        history = await buf.load("s1")
        assert len(history) == 2
        assert history[0]["content"] == "hello"
        assert history[1]["content"] == "world"

    @pytest.mark.asyncio
    async def test_session_isolation(self):
        buf = InMemoryBuffer()
        await buf.save("s1", {"role": "user", "content": "session 1"})
        await buf.save("s2", {"role": "user", "content": "session 2"})
        assert len(await buf.load("s1")) == 1
        assert len(await buf.load("s2")) == 1
        assert (await buf.load("s1"))[0]["content"] == "session 1"

    @pytest.mark.asyncio
    async def test_max_turns_circular_eviction(self):
        buf = InMemoryBuffer(max_turns=3)
        for i in range(5):
            await buf.save("s1", {"role": "user", "content": str(i)})
        history = await buf.load("s1")
        assert len(history) == 3
        # Oldest entries evicted — only last 3 remain
        assert [t["content"] for t in history] == ["2", "3", "4"]

    @pytest.mark.asyncio
    async def test_clear(self):
        buf = InMemoryBuffer()
        await buf.save("s1", {"role": "user", "content": "hello"})
        await buf.clear("s1")
        assert await buf.load("s1") == []

    @pytest.mark.asyncio
    async def test_empty_session_returns_empty_list(self):
        buf = InMemoryBuffer()
        result = await buf.load("nonexistent")
        assert result == []

    def test_active_sessions(self):
        buf = InMemoryBuffer()
        asyncio.run(buf.save("s1", {"role": "user", "content": "hi"}))
        asyncio.run(buf.save("s2", {"role": "user", "content": "yo"}))
        assert set(buf.active_sessions()) == {"s1", "s2"}
