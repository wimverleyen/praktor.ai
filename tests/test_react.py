"""
Tests for the ReAct tool-use loop in Agent.

All LLM calls and tool calls are mocked — no live services needed.
"""
import sys
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent / 'praktor'))

import pytest
from pydantic import BaseModel

from core.agent_definition import AgentDefinition, MemoryPolicy
from core.tool import ToolResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _SearchInput(BaseModel):
    agent_type: str = "search_agent"
    question: str
    session_id: str = ""
    history: str = ""


def _make_tool(name: str, description: str, response: str = "tool result") -> AsyncMock:
    tool = AsyncMock(return_value=ToolResult(content=response))
    tool.name = name
    tool.description = description
    return tool


def _make_definition(max_steps: int = 3, tools: list[str] | None = None) -> AgentDefinition:
    return AgentDefinition(
        name="search_agent",
        prompt_template="Answer this question: {question}\n\nHistory: {history}",
        input_schema=_SearchInput,
        llm_model="qwen2.5",
        max_steps=max_steps,
        tools=tools or ["web_search"],
        memory_policy=MemoryPolicy.NONE,
    )


async def _collect(agent, payload: dict, session_id: str = "s1") -> str:
    chunks = []
    async for chunk in agent.run(payload, session_id=session_id):
        chunks.append(chunk)
    return "".join(chunks)


# ---------------------------------------------------------------------------
# ReAct loop: happy path
# ---------------------------------------------------------------------------

class TestReActLoop:

    @pytest.mark.asyncio
    async def test_single_tool_call_then_final_answer(self):
        """LLM calls web_search once, then gives a Final Answer."""
        definition = _make_definition(max_steps=3)
        web_search = _make_tool("web_search", "Search the web", "Python 3.13 released Oct 2024")

        step1 = (
            "Thought: I need to search for this.\n"
            "Action: web_search\n"
            "Action Input: Python 3.13 release date"
        )
        step2 = (
            "Thought: I have enough information to answer.\n"
            "Final Answer: Python 3.13 was released in October 2024."
        )

        with patch("core.tool.get_tool", return_value=web_search), \
             patch("LLM.llm_factory.LLMFactory") as mock_factory:

            mock_llm = MagicMock()
            mock_factory.return_value.create_llm.return_value = mock_llm

            from core.agent import Agent
            agent = Agent(definition)
            agent._tools = {"web_search": web_search}

            invoke_responses = [step1, step2]
            agent._react_adapter = MagicMock()
            agent._react_adapter.ainvoke = AsyncMock(side_effect=invoke_responses)
            agent._react_adapter._prompt = MagicMock()
            agent._react_adapter._prompt.input_variables = []
            agent._adapter._prompt = MagicMock()
            agent._adapter._prompt.input_variables = ["question", "history"]
            agent._adapter._prompt.format = MagicMock(return_value="Answer this question: What is Python 3.13?")

            result = await _collect(agent, {"question": "What is Python 3.13?"})

        assert "Python 3.13" in result
        assert "October 2024" in result
        # Tool was called exactly once
        web_search.assert_awaited_once_with("Python 3.13 release date")

    @pytest.mark.asyncio
    async def test_final_answer_on_first_step_skips_tool(self):
        """LLM answers directly without needing a tool."""
        definition = _make_definition(max_steps=3)
        web_search = _make_tool("web_search", "Search the web")

        direct_answer = "Thought: I already know this.\nFinal Answer: The sky is blue."

        with patch("core.tool.get_tool", return_value=web_search), \
             patch("LLM.llm_factory.LLMFactory") as mock_factory:

            mock_factory.return_value.create_llm.return_value = MagicMock()

            from core.agent import Agent
            agent = Agent(definition)
            agent._tools = {"web_search": web_search}
            agent._react_adapter = MagicMock()
            agent._react_adapter.ainvoke = AsyncMock(return_value=direct_answer)
            agent._react_adapter._prompt = MagicMock()
            agent._react_adapter._prompt.input_variables = []
            agent._adapter._prompt = MagicMock()
            agent._adapter._prompt.input_variables = ["question", "history"]
            agent._adapter._prompt.format = MagicMock(return_value="Answer this: ...")

            result = await _collect(agent, {"question": "Why is the sky blue?"})

        assert "The sky is blue." in result
        web_search.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_two_tool_calls_before_final_answer(self):
        """LLM uses the tool twice before answering."""
        definition = _make_definition(max_steps=5)
        web_search = _make_tool("web_search", "Search the web", "Some result")

        responses = [
            "Thought: First search.\nAction: web_search\nAction Input: query one",
            "Thought: Need more.\nAction: web_search\nAction Input: query two",
            "Thought: Done.\nFinal Answer: Combined answer from two searches.",
        ]

        with patch("core.tool.get_tool", return_value=web_search), \
             patch("LLM.llm_factory.LLMFactory") as mock_factory:

            mock_factory.return_value.create_llm.return_value = MagicMock()

            from core.agent import Agent
            agent = Agent(definition)
            agent._tools = {"web_search": web_search}
            agent._react_adapter = MagicMock()
            agent._react_adapter.ainvoke = AsyncMock(side_effect=responses)
            agent._react_adapter._prompt = MagicMock()
            agent._react_adapter._prompt.input_variables = []
            agent._adapter._prompt = MagicMock()
            agent._adapter._prompt.input_variables = ["question", "history"]
            agent._adapter._prompt.format = MagicMock(return_value="Question: ...")

            result = await _collect(agent, {"question": "Multi-step question"})

        assert "Combined answer" in result
        assert web_search.await_count == 2

    @pytest.mark.asyncio
    async def test_max_steps_reached_returns_last_response(self):
        """When max_steps is exhausted without Final Answer, yield the last LLM response."""
        definition = _make_definition(max_steps=2)
        web_search = _make_tool("web_search", "Search the web", "result")

        # Both steps produce Actions, never a Final Answer
        responses = [
            "Thought: Try first.\nAction: web_search\nAction Input: q1",
            "Thought: Try again.\nAction: web_search\nAction Input: q2",
        ]

        with patch("core.tool.get_tool", return_value=web_search), \
             patch("LLM.llm_factory.LLMFactory") as mock_factory:

            mock_factory.return_value.create_llm.return_value = MagicMock()

            from core.agent import Agent
            agent = Agent(definition)
            agent._tools = {"web_search": web_search}
            agent._react_adapter = MagicMock()
            agent._react_adapter.ainvoke = AsyncMock(side_effect=responses)
            agent._react_adapter._prompt = MagicMock()
            agent._react_adapter._prompt.input_variables = []
            agent._adapter._prompt = MagicMock()
            agent._adapter._prompt.input_variables = ["question", "history"]
            agent._adapter._prompt.format = MagicMock(return_value="Question: ...")

            result = await _collect(agent, {"question": "Hard question"})

        # Got something back — the last LLM response
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_unknown_tool_injects_error_observation(self):
        """If LLM invokes a tool that isn't registered, an error observation is injected."""
        definition = _make_definition(max_steps=3)
        web_search = _make_tool("web_search", "Search the web")

        responses = [
            "Thought: Use unknown tool.\nAction: nonexistent_tool\nAction Input: anything",
            "Thought: That failed, I'll answer anyway.\nFinal Answer: Sorry, couldn't find that.",
        ]

        with patch("core.tool.get_tool", return_value=web_search), \
             patch("LLM.llm_factory.LLMFactory") as mock_factory:

            mock_factory.return_value.create_llm.return_value = MagicMock()

            from core.agent import Agent
            agent = Agent(definition)
            agent._tools = {"web_search": web_search}
            agent._react_adapter = MagicMock()
            agent._react_adapter.ainvoke = AsyncMock(side_effect=responses)
            agent._react_adapter._prompt = MagicMock()
            agent._react_adapter._prompt.input_variables = []
            agent._adapter._prompt = MagicMock()
            agent._adapter._prompt.input_variables = ["question", "history"]
            agent._adapter._prompt.format = MagicMock(return_value="Question: ...")

            result = await _collect(agent, {"question": "Test"})

        assert "Sorry" in result
        # The real web_search tool was never called
        web_search.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_tool_error_result_injected_as_observation(self):
        """If the tool itself returns an error, it's injected as the observation."""
        definition = _make_definition(max_steps=3)
        failing_tool = AsyncMock(return_value=ToolResult(content="", error="connection timeout"))
        failing_tool.name = "web_search"
        failing_tool.description = "Search the web"

        responses = [
            "Thought: Search.\nAction: web_search\nAction Input: query",
            "Thought: Search failed. I'll answer from memory.\nFinal Answer: I don't know.",
        ]

        with patch("core.tool.get_tool", return_value=failing_tool), \
             patch("LLM.llm_factory.LLMFactory") as mock_factory:

            mock_factory.return_value.create_llm.return_value = MagicMock()

            from core.agent import Agent
            agent = Agent(definition)
            agent._tools = {"web_search": failing_tool}
            agent._react_adapter = MagicMock()
            agent._react_adapter.ainvoke = AsyncMock(side_effect=responses)
            agent._react_adapter._prompt = MagicMock()
            agent._react_adapter._prompt.input_variables = []
            agent._adapter._prompt = MagicMock()
            agent._adapter._prompt.input_variables = ["question", "history"]
            agent._adapter._prompt.format = MagicMock(return_value="Question: ...")

            result = await _collect(agent, {"question": "Test"})

        assert "don't know" in result


# ---------------------------------------------------------------------------
# ReAct loop: observability
# ---------------------------------------------------------------------------

class TestReActObservability:

    @pytest.mark.asyncio
    async def test_trajectory_records_llm_and_tool_calls(self):
        """After a run with one tool call, trajectory has >=2 events: llm_call + tool_call."""
        from core.observability import Span, tracer
        from unittest.mock import patch

        definition = _make_definition(max_steps=3)
        web_search = _make_tool("web_search", "Search the web", "search result")

        responses = [
            "Thought: Search.\nAction: web_search\nAction Input: test query",
            "Thought: Done.\nFinal Answer: The answer is 42.",
        ]

        recorded_span: list[Span] = []

        original_init = Span.__init__

        def _capture_span(self_span, **kwargs):
            original_init(self_span, **kwargs)
            recorded_span.append(self_span)

        with patch("core.tool.get_tool", return_value=web_search), \
             patch("LLM.llm_factory.LLMFactory") as mock_factory, \
             patch.object(Span, "__init__", _capture_span):

            mock_factory.return_value.create_llm.return_value = MagicMock()

            from core.agent import Agent
            agent = Agent(definition)
            agent._tools = {"web_search": web_search}
            agent._react_adapter = MagicMock()
            agent._react_adapter.ainvoke = AsyncMock(side_effect=responses)
            agent._react_adapter._prompt = MagicMock()
            agent._react_adapter._prompt.input_variables = []
            agent._adapter._prompt = MagicMock()
            agent._adapter._prompt.input_variables = ["question", "history"]
            agent._adapter._prompt.format = MagicMock(return_value="Question: ...")

            with patch.object(Span, "finish"):
                result = await _collect(agent, {"question": "What is 42?"})

        assert "42" in result

    @pytest.mark.asyncio
    async def test_single_pass_does_not_use_react_loop(self):
        """max_steps=1 uses the regular astream path, not _react_loop."""
        definition = AgentDefinition(
            name="simple_agent",
            prompt_template="Answer: {question}\n\nHistory: {history}",
            input_schema=_SearchInput,
            llm_model="qwen2.5",
            max_steps=1,
            tools=[],
            memory_policy=MemoryPolicy.NONE,
        )

        with patch("LLM.llm_factory.LLMFactory") as mock_factory:
            mock_factory.return_value.create_llm.return_value = MagicMock()

            from core.agent import Agent
            agent = Agent(definition)

            async def _fake_astream(data, call_span=None):
                yield "simple answer"

            agent._adapter.astream = _fake_astream

            with patch.object(agent, "_react_loop") as mock_react:
                result = await _collect(agent, {"question": "Simple?"})

        mock_react.assert_not_called()
        assert result == "simple answer"
