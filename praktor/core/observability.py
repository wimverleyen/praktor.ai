import time
import json
import os
from typing import Any

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.trace import StatusCode

from settings import create_log

log = create_log()

# ---------------------------------------------------------------------------
# Tracer setup — configured once at module load.
#
# Set OTLP_ENDPOINT to enable gRPC export to a collector (Jaeger, Grafana, etc.).
# If unset, falls back to ConsoleSpanExporter for local dev.
# ---------------------------------------------------------------------------

_OTLP_ENDPOINT = os.getenv("OTLP_ENDPOINT", "")

_resource = Resource.create({"service.name": "praktor.ai"})
_provider = TracerProvider(resource=_resource)

if _OTLP_ENDPOINT:
    try:
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        _exporter = OTLPSpanExporter(endpoint=_OTLP_ENDPOINT, insecure=True)
        log.info(f"OTel: exporting spans to {_OTLP_ENDPOINT}")
    except Exception as e:
        log.warning(f"OTel: OTLP exporter failed to init ({e}), falling back to console")
        _exporter = ConsoleSpanExporter()
else:
    _exporter = ConsoleSpanExporter()

_provider.add_span_processor(BatchSpanProcessor(_exporter))
trace.set_tracer_provider(_provider)

tracer = trace.get_tracer("praktor.ai")


# ---------------------------------------------------------------------------
# TrajectoryEvent — one entry per step in a multi-pass or ReAct run.
# ---------------------------------------------------------------------------

class TrajectoryEvent:
    """Records a single step in an agent run (LLM call, tool call, improvement pass)."""

    __slots__ = (
        "step", "kind", "latency_ms", "input_tokens",
        "output_tokens", "tool_name", "cached", "error",
    )

    def __init__(
        self,
        step: int,
        kind: str,
        latency_ms: float,
        input_tokens: int = 0,
        output_tokens: int = 0,
        tool_name: str | None = None,
        cached: bool = False,
        error: str | None = None,
    ):
        self.step = step
        self.kind = kind                    # "llm_call" | "tool_call" | "improvement_pass"
        self.latency_ms = latency_ms
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.tool_name = tool_name
        self.cached = cached
        self.error = error


# ---------------------------------------------------------------------------
# Span — OTel-backed wrapper for a single agent request.
#
# Call sites in agent.py are unchanged:
#   span = Span(agent_type=..., session_id=..., model=...)
#   span.finish(token_count=N, passes=N)
#   span.finish(error="...")
#
# Child spans for per-LLM-call timing: use span.child_llm_call() as a context manager.
# ---------------------------------------------------------------------------

class Span:
    """
    OTel-backed observability span for a single agent request.

    - Root span uses session_id as a trace attribute for cross-agent correlation
    - Child spans record each LLM call with per-call latency and token counts
    - Trajectory events (capped at 128) are attached as OTel span events
    - JSON log line emitted as a secondary sink regardless of OTel export status
    """

    def __init__(self, agent_type: str, session_id: str, model: str):
        self.agent_type = agent_type
        self.session_id = session_id
        self.model = model
        self._start_time = time.time()
        self._trajectory: list[TrajectoryEvent] = []

        self._otel_span = tracer.start_span(
            name=f"agent.{agent_type}",
            attributes={
                "agent.type": agent_type,
                "agent.session_id": session_id,
                "llm.model": model,
            },
        )

    @property
    def duration_ms(self) -> float:
        return (time.time() - self._start_time) * 1000

    def child_llm_call(
        self,
        pass_number: int,
        kind: str = "llm_call",
        tool_name: str | None = None,
    ) -> "LLMCallSpan":
        """Return a context manager that records one LLM or tool call as a child span."""
        return LLMCallSpan(
            parent=self,
            pass_number=pass_number,
            kind=kind,
            tool_name=tool_name,
        )

    def finish(
        self,
        token_count: int = 0,
        cached: bool = False,
        passes: int = 1,
        error: str | None = None,
    ) -> None:
        duration = self.duration_ms

        # Attach trajectory as span events (OTel collectors typically cap at 128)
        for event in self._trajectory[:128]:
            attrs: dict[str, Any] = {
                "step": event.step,
                "latency_ms": round(event.latency_ms, 2),
                "input_tokens": event.input_tokens,
                "output_tokens": event.output_tokens,
                "cached": event.cached,
            }
            if event.tool_name:
                attrs["tool_name"] = event.tool_name
            if event.error:
                attrs["error"] = event.error
            self._otel_span.add_event(event.kind, attributes=attrs)

        self._otel_span.set_attributes({
            "agent.token_count": token_count,
            "agent.passes": passes,
            "agent.cached": cached,
            "agent.duration_ms": round(duration, 2),
        })

        if error:
            self._otel_span.set_status(StatusCode.ERROR, error)
            self._otel_span.set_attribute("agent.error", error)
        else:
            self._otel_span.set_status(StatusCode.OK)

        self._otel_span.end()

        # Secondary sink: structured JSON log line (always emitted).
        record: dict[str, Any] = {
            "agent_type": self.agent_type,
            "session_id": self.session_id,
            "model": self.model,
            "duration_ms": round(duration, 2),
            "token_count": token_count,
            "passes": passes,
            "cached": cached,
            "trajectory_steps": len(self._trajectory),
        }
        if error:
            record["error"] = error
            log.error(f"SPAN {json.dumps(record)}")
        else:
            log.info(f"SPAN {json.dumps(record)}")

    def _record_trajectory(self, event: TrajectoryEvent) -> None:
        self._trajectory.append(event)


# ---------------------------------------------------------------------------
# LLMCallSpan — child span context manager.
# ---------------------------------------------------------------------------

class LLMCallSpan:
    """Context manager that wraps one LLM or tool call in a child OTel span."""

    def __init__(
        self,
        parent: Span,
        pass_number: int,
        kind: str,
        tool_name: str | None,
    ):
        self._parent = parent
        self._pass_number = pass_number
        self._kind = kind
        self._tool_name = tool_name
        self._start = 0.0
        self._otel_span: Any = None
        self.output_tokens = 0
        self.input_tokens = 0
        self.cached = False

    def __enter__(self) -> "LLMCallSpan":
        self._start = time.time()
        name = f"tool.{self._tool_name}" if self._tool_name else f"llm.{self._kind}"
        self._otel_span = tracer.start_span(
            name=name,
            attributes={
                "llm.pass": self._pass_number,
                "llm.kind": self._kind,
                **({"tool.name": self._tool_name} if self._tool_name else {}),
            },
        )
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        latency = (time.time() - self._start) * 1000
        error = str(exc_val) if exc_val else None

        if self._otel_span:
            self._otel_span.set_attributes({
                "llm.output_tokens": self.output_tokens,
                "llm.input_tokens": self.input_tokens,
                "llm.cached": self.cached,
                "llm.latency_ms": round(latency, 2),
            })
            if error:
                self._otel_span.set_status(StatusCode.ERROR, error)
            else:
                self._otel_span.set_status(StatusCode.OK)
            self._otel_span.end()

        self._parent._record_trajectory(TrajectoryEvent(
            step=self._pass_number,
            kind=self._kind,
            latency_ms=latency,
            input_tokens=self.input_tokens,
            output_tokens=self.output_tokens,
            tool_name=self._tool_name,
            cached=self.cached,
            error=error,
        ))
