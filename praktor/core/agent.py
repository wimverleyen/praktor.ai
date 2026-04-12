from typing import AsyncGenerator

from core.agent_definition import AgentDefinition, MemoryPolicy, OutputSink, ImprovementPass
from core.memory import NullMemory
from core.observability import Span
from core.tool import get_tool
from LLM.llm_interface import AsyncLLMAdapter

from settings import MD, create_log

log = create_log()


class Agent:
    """
    Runtime execution unit for a single AgentDefinition.

    - Runs all LLM passes as an async generator (yields token chunks)
    - Injects conversation history from memory before each call
    - Saves the assistant response to memory after completion
    - Writes to a markdown file if output_sink is FILE or BOTH
    - Emits a structured observability Span on every run
    """

    def __init__(self, definition: AgentDefinition):
        self._definition = definition

        # Primary LLM adapter (compiled once at construction)
        self._adapter = AsyncLLMAdapter(
            prompt_template=definition.prompt_template,
            model=definition.llm_model,
            temperature=definition.temperature,
        )

        # Improvement-pass adapters (e.g., cover letter multi-pass)
        self._improvement_adapters: list[tuple[AsyncLLMAdapter, str]] = [
            (
                AsyncLLMAdapter(
                    prompt_template=p.prompt_template,
                    model=definition.llm_model,
                    temperature=definition.temperature,
                ),
                p.output_key,
            )
            for p in definition.improvement_passes
        ]

        # Tools
        self._tools = {name: get_tool(name) for name in definition.tools}

        # Memory
        if definition.memory_policy == MemoryPolicy.NONE:
            self._memory = NullMemory()
        elif definition.memory_policy == MemoryPolicy.SHORT_TERM:
            from memory.buffer import InMemoryBuffer
            self._memory = InMemoryBuffer()
        elif definition.memory_policy == MemoryPolicy.LONG_TERM:
            from memory.vector import FAISSMemory
            self._memory = FAISSMemory()

    @property
    def definition(self) -> AgentDefinition:
        return self._definition

    async def run(self, payload: dict, session_id: str) -> AsyncGenerator[str, None]:
        """
        Execute the agent and yield response chunks.

        If improvement_passes are defined, runs each in sequence, injecting
        the previous response under that pass's output_key.

        Saves the final response to memory and optionally to a markdown file.
        """
        span = Span(
            agent_type=self._definition.name,
            session_id=session_id,
            model=self._definition.llm_model,
        )

        # Inject memory context
        history = await self._memory.load(session_id)
        if history:
            payload["history"] = "\n".join(
                f"{t['role']}: {t['content']}" for t in history
            )
        else:
            payload.setdefault("history", "")

        all_chunks: list[str] = []
        current_response: list[str] = []
        passes = 1

        try:
            # --- Initial pass ---
            async for chunk in self._adapter.astream(payload):
                current_response.append(chunk)
                all_chunks.append(chunk)
                yield chunk

            # --- Improvement passes ---
            for improve_adapter, output_key in self._improvement_adapters:
                passes += 1
                payload[output_key] = "".join(current_response)
                current_response = []
                async for chunk in improve_adapter.astream(payload):
                    current_response.append(chunk)
                    all_chunks.append(chunk)
                    yield chunk

            final_response = "".join(all_chunks)
            token_count = len(final_response.split())

            # --- Persist to memory ---
            await self._memory.save(
                session_id, {"role": "assistant", "content": final_response}
            )

            # --- File output ---
            if (
                self._definition.output_file
                and self._definition.output_sink in (OutputSink.FILE, OutputSink.BOTH)
            ):
                self._write_file(self._definition.output_file, final_response)

            span.finish(token_count=token_count, passes=passes)
            log.debug(
                f"Agent '{self._definition.name}' completed "
                f"session={session_id} tokens={token_count} passes={passes}"
            )

        except Exception as e:
            span.finish(error=str(e))
            log.error(f"Agent '{self._definition.name}' failed: {e}", exc_info=True)
            raise

    def _write_file(self, stem: str, content: str) -> None:
        try:
            from utils import save_markdown
            path = f"{MD}{stem}.md" if MD else f"{stem}.md"
            save_markdown(path, content)
            log.debug(f"Wrote output to {path}")
        except Exception as e:
            log.error(f"Failed to write output file '{stem}': {e}")
