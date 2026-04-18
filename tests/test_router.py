import sys
import json
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

import pytest
from pydantic import BaseModel

from praktor.core.agent_definition import AgentDefinition, MemoryPolicy
from praktor.core.router import Router


class _SearchInput(BaseModel):
    agent_type: str = "search"
    query: str
    session_id: str = ""


_SEARCH_DEF = AgentDefinition(
    name="search",
    prompt_template="Answer: {query}",
    input_schema=_SearchInput,
)


class TestRouter:

    def setup_method(self):
        self.router = Router()

    def test_register_agent(self):
        self.router.register(_SEARCH_DEF)
        assert "search" in self.router.registered()

    def test_registered_returns_names(self):
        self.router.register(_SEARCH_DEF)
        assert self.router.registered() == ["search"]

    @pytest.mark.asyncio
    async def test_dispatch_unknown_agent_type_raises(self):
        raw = json.dumps({"agent_type": "nonexistent", "query": "hello"}).encode()
        with pytest.raises(ValueError, match="Unknown agent_type"):
            async for _ in self.router.dispatch(raw):
                pass

    @pytest.mark.asyncio
    async def test_dispatch_missing_agent_type_raises(self):
        raw = json.dumps({"query": "hello"}).encode()
        with pytest.raises(ValueError, match="missing required field"):
            async for _ in self.router.dispatch(raw):
                pass

    @pytest.mark.asyncio
    async def test_dispatch_schema_validation_error(self):
        self.router.register(_SEARCH_DEF)
        # Missing required field 'query'
        raw = json.dumps({"agent_type": "search"}).encode()
        with pytest.raises(ValueError, match="Schema validation failed"):
            async for _ in self.router.dispatch(raw):
                pass

    @pytest.mark.asyncio
    async def test_dispatch_routes_to_agent(self):
        self.router.register(_SEARCH_DEF)

        async def _fake_run(payload, session_id, caller_identity="anonymous"):
            yield "chunk1"
            yield "chunk2"

        with patch.object(
            self.router._agents["search"], "run", side_effect=_fake_run
        ):
            raw = json.dumps({"agent_type": "search", "query": "test"}).encode()
            chunks = []
            async for chunk in self.router.dispatch(raw):
                chunks.append(chunk)

        assert chunks == ["chunk1", "chunk2"]

    @pytest.mark.asyncio
    async def test_dispatch_injects_session_id(self):
        self.router.register(_SEARCH_DEF)

        captured_session: list[str] = []

        async def _fake_run(payload, session_id, caller_identity="anonymous"):
            captured_session.append(session_id)
            yield "ok"

        with patch.object(
            self.router._agents["search"], "run", side_effect=_fake_run
        ):
            raw = json.dumps({"agent_type": "search", "query": "test", "session_id": "abc123"}).encode()
            async for _ in self.router.dispatch(raw):
                pass

        assert captured_session == ["abc123"]

    @pytest.mark.asyncio
    async def test_dispatch_generates_session_id_if_absent(self):
        self.router.register(_SEARCH_DEF)

        captured_session: list[str] = []

        async def _fake_run(payload, session_id, caller_identity="anonymous"):
            captured_session.append(session_id)
            yield "ok"

        with patch.object(
            self.router._agents["search"], "run", side_effect=_fake_run
        ):
            raw = json.dumps({"agent_type": "search", "query": "test"}).encode()
            async for _ in self.router.dispatch(raw):
                pass

        assert len(captured_session) == 1
        assert len(captured_session[0]) == 8  # new_request_id() returns 8-char hex
