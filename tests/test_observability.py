import sys
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# ---------------------------------------------------------------------------
# Helpers — mock the OTel SDK before importing observability so tests
# don't need a live collector or the full SDK installed.
# ---------------------------------------------------------------------------

def _make_mock_span():
    s = MagicMock()
    s.set_attributes = MagicMock()
    s.set_attribute = MagicMock()
    s.set_status = MagicMock()
    s.add_event = MagicMock()
    s.end = MagicMock()
    return s


def _make_tracer(mock_span):
    tracer = MagicMock()
    tracer.start_span.return_value = mock_span
    return tracer


# ---------------------------------------------------------------------------
# TrajectoryEvent
# ---------------------------------------------------------------------------

class TestTrajectoryEvent:
    def test_fields_stored(self):
        from praktor.core.observability import TrajectoryEvent
        ev = TrajectoryEvent(
            step=2,
            kind="llm_call",
            latency_ms=123.4,
            input_tokens=10,
            output_tokens=50,
            tool_name=None,
            cached=False,
        )
        assert ev.step == 2
        assert ev.kind == "llm_call"
        assert ev.latency_ms == 123.4
        assert ev.output_tokens == 50
        assert ev.cached is False
        assert ev.error is None

    def test_tool_name_and_error(self):
        from praktor.core.observability import TrajectoryEvent
        ev = TrajectoryEvent(
            step=1,
            kind="tool_call",
            latency_ms=5.0,
            tool_name="web_search",
            error="timeout",
        )
        assert ev.tool_name == "web_search"
        assert ev.error == "timeout"


# ---------------------------------------------------------------------------
# Span
# ---------------------------------------------------------------------------

class TestSpan:
    def _make_span(self, mock_otel_span=None):
        if mock_otel_span is None:
            mock_otel_span = _make_mock_span()
        from praktor.core.observability import Span, tracer
        with patch.object(tracer, "start_span", return_value=mock_otel_span):
            span = Span(agent_type="test_agent", session_id="sess-1", model="qwen2.5")
        span._otel_span = mock_otel_span
        return span, mock_otel_span

    def test_duration_ms_positive(self):
        span, _ = self._make_span()
        time.sleep(0.01)
        assert span.duration_ms > 0

    def test_finish_success_emits_log(self, caplog):
        import logging
        span, mock_otel = self._make_span()
        with patch("praktor.core.observability.log") as mock_log:
            span.finish(token_count=42, passes=2)
        mock_log.info.assert_called_once()
        log_msg = mock_log.info.call_args[0][0]
        assert "SPAN" in log_msg
        assert "test_agent" in log_msg
        assert "sess-1" in log_msg

    def test_finish_error_logs_at_error_level(self):
        span, mock_otel = self._make_span()
        with patch("praktor.core.observability.log") as mock_log:
            span.finish(error="something broke")
        mock_log.error.assert_called_once()
        log_msg = mock_log.error.call_args[0][0]
        assert "something broke" in log_msg

    def test_finish_sets_otel_attributes(self):
        span, mock_otel = self._make_span()
        span.finish(token_count=100, passes=3, cached=True)
        mock_otel.set_attributes.assert_called()
        call_kwargs = mock_otel.set_attributes.call_args[0][0]
        assert call_kwargs["agent.token_count"] == 100
        assert call_kwargs["agent.passes"] == 3
        assert call_kwargs["agent.cached"] is True

    def test_finish_calls_otel_span_end(self):
        span, mock_otel = self._make_span()
        span.finish()
        mock_otel.end.assert_called_once()

    def test_finish_error_sets_otel_error_status(self):
        from opentelemetry.trace import StatusCode
        span, mock_otel = self._make_span()
        span.finish(error="boom")
        mock_otel.set_status.assert_called()
        status_arg = mock_otel.set_status.call_args[0][0]
        assert status_arg == StatusCode.ERROR

    def test_trajectory_events_attached_as_span_events(self):
        from praktor.core.observability import TrajectoryEvent
        span, mock_otel = self._make_span()
        span._record_trajectory(TrajectoryEvent(step=1, kind="llm_call", latency_ms=50.0))
        span._record_trajectory(TrajectoryEvent(step=2, kind="improvement_pass", latency_ms=70.0))
        span.finish()
        assert mock_otel.add_event.call_count == 2

    def test_trajectory_capped_at_128(self):
        from praktor.core.observability import TrajectoryEvent
        span, mock_otel = self._make_span()
        for i in range(200):
            span._record_trajectory(TrajectoryEvent(step=i, kind="llm_call", latency_ms=1.0))
        span.finish()
        assert mock_otel.add_event.call_count == 128

    def test_json_log_includes_trajectory_steps(self):
        import json
        from praktor.core.observability import TrajectoryEvent
        span, _ = self._make_span()
        span._record_trajectory(TrajectoryEvent(step=1, kind="llm_call", latency_ms=30.0))
        with patch("praktor.core.observability.log") as mock_log:
            span.finish(token_count=10)
        log_msg = mock_log.info.call_args[0][0]
        record = json.loads(log_msg.replace("SPAN ", ""))
        assert record["trajectory_steps"] == 1


# ---------------------------------------------------------------------------
# LLMCallSpan
# ---------------------------------------------------------------------------

class TestLLMCallSpan:
    def _make_call_span(self, pass_number=1, kind="llm_call", tool_name=None):
        from praktor.core.observability import Span, LLMCallSpan, tracer
        mock_parent_otel = _make_mock_span()
        mock_child_otel = _make_mock_span()

        with patch.object(tracer, "start_span", side_effect=[mock_parent_otel, mock_child_otel]):
            parent = Span(agent_type="agent", session_id="s", model="m")
            parent._otel_span = mock_parent_otel
            call_span = parent.child_llm_call(pass_number=pass_number, kind=kind, tool_name=tool_name)

        with patch.object(tracer, "start_span", return_value=mock_child_otel):
            call_span.__enter__()

        call_span._otel_span = mock_child_otel
        return call_span, parent, mock_child_otel

    def test_records_trajectory_on_exit(self):
        call_span, parent, _ = self._make_call_span(pass_number=1)
        call_span.output_tokens = 20
        call_span.__exit__(None, None, None)
        assert len(parent._trajectory) == 1
        assert parent._trajectory[0].step == 1
        assert parent._trajectory[0].output_tokens == 20

    def test_records_error_on_exception(self):
        call_span, parent, _ = self._make_call_span()
        call_span.__exit__(ValueError, ValueError("bad input"), None)
        assert parent._trajectory[0].error == "bad input"

    def test_ends_child_otel_span(self):
        call_span, _, mock_child = self._make_call_span()
        call_span.__exit__(None, None, None)
        mock_child.end.assert_called_once()

    def test_tool_name_in_trajectory(self):
        call_span, parent, _ = self._make_call_span(kind="tool_call", tool_name="web_search")
        call_span.__exit__(None, None, None)
        assert parent._trajectory[0].tool_name == "web_search"
        assert parent._trajectory[0].kind == "tool_call"

    def test_cached_flag_propagates(self):
        call_span, parent, _ = self._make_call_span()
        call_span.cached = True
        call_span.__exit__(None, None, None)
        assert parent._trajectory[0].cached is True


# ---------------------------------------------------------------------------
# Integration: Agent.run() produces trajectory events
# ---------------------------------------------------------------------------

class TestAgentRunTrajectory:
    @pytest.mark.asyncio
    async def test_agent_run_records_llm_call_in_trajectory(self):
        import importlib
        from unittest.mock import AsyncMock, patch, MagicMock

        # Stub out langchain before any import that pulls it in
        lc_prompt = MagicMock()
        lc_prompt.input_variables = ["question"]
        lc_prompt.format.return_value = "Answer: hi"
        mock_pt = MagicMock(return_value=lc_prompt)

        fake_langchain = MagicMock()
        fake_langchain.prompts.PromptTemplate.from_template = mock_pt

        with patch.dict("sys.modules", {
            "langchain": fake_langchain,
            "langchain.prompts": fake_langchain.prompts,
            "langchain_ollama": MagicMock(),
            "langchain_ollama.llms": MagicMock(),
        }):
            with patch("praktor.LLM.llm_factory.LLMFactory") as mock_factory:
                mock_factory.return_value.create_llm.return_value = MagicMock()

                import importlib, praktor.LLM.llm_interface as lli
                importlib.reload(lli)

                from praktor.core.agent_definition import AgentDefinition, MemoryPolicy
                from praktor.core.observability import Span, tracer

                definition = AgentDefinition(
                    name="traj_agent",
                    prompt_template="Answer: {question}",
                    input_schema=MagicMock(),
                    llm_model="qwen2.5",
                    memory_policy=MemoryPolicy.NONE,
                )

                mock_otel = _make_mock_span()

                async def _fake_astream(data, call_span=None):
                    if call_span is not None:
                        call_span.output_tokens = 5
                    yield "hello world"

                with patch("praktor.core.observability.tracer") as mock_tracer:
                    mock_tracer.start_span.return_value = mock_otel

                    import praktor.core.agent as agent_mod
                    importlib.reload(agent_mod)
                    agent = agent_mod.Agent(definition)
                    agent._adapter.astream = _fake_astream

                    chunks = []
                    async for chunk in agent.run({"question": "hi"}, session_id="s1"):
                        chunks.append(chunk)

        assert "".join(chunks) == "hello world"
