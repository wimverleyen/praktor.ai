import asyncio
import re
from typing import AsyncGenerator

from core.agent_definition import AgentDefinition, MemoryPolicy, OutputSink
from core.memory import NullMemory
from core.observability import Span
from core.tool import get_tool
from LLM.llm_interface import AsyncLLMAdapter

from settings import MD, create_log

log = create_log()

# ---------------------------------------------------------------------------
# ReAct prompt format injected automatically when max_steps > 1.
# The agent's own prompt_template renders first as {user_prompt}; this
# wrapper adds tool descriptions and the Thought/Action/Observation format.
# ---------------------------------------------------------------------------

_REACT_WRAPPER = """{user_prompt}

You have access to the following tools:
{tool_descriptions}

Respond using this format (repeat Thought/Action/Observation as needed):

Thought: [your reasoning]
Action: [one of: {tool_names}]
Action Input: [input string to pass to the tool]
Observation: [tool result will be inserted here]

When you have enough information to answer, respond with:

Thought: I have enough information to answer.
Final Answer: [your complete response]

{scratchpad}"""

# Patterns for parsing a single ReAct step
_ACTION_RE = re.compile(r"Action:\s*(.+)", re.IGNORECASE)
_ACTION_INPUT_RE = re.compile(r"Action Input:\s*(.+)", re.IGNORECASE | re.DOTALL)
_FINAL_ANSWER_RE = re.compile(r"Final Answer:\s*(.+)", re.IGNORECASE | re.DOTALL)


class Agent:
    """
    Runtime execution unit for a single AgentDefinition.

    Single-pass (max_steps=1):
        Initial LLM call → optional improvement passes → stream to caller.

    ReAct loop (max_steps>1, requires tools):
        LLM call → parse Action/Final Answer → execute tool → inject Observation
        → repeat up to max_steps times → stream final answer to caller.
        Each step (LLM call and tool call) is recorded as a child OTel span.
    """

    def __init__(self, definition: AgentDefinition):
        self._definition = definition

        # Primary LLM adapter (compiled once at construction)
        self._adapter = AsyncLLMAdapter(
            prompt_template=definition.prompt_template,
            model=definition.llm_model,
            temperature=definition.temperature,
        )

        # ReAct adapter — wraps the user prompt with tool descriptions + scratchpad.
        # Built lazily on first ReAct run so tool descriptions are always current.
        self._react_adapter: AsyncLLMAdapter | None = None

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

        # Tools — resolved from the global registry at construction time
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

        Routes to _react_loop() when max_steps > 1 and tools are registered,
        otherwise runs the single-pass (+ improvement passes) path.
        """
        span = Span(
            agent_type=self._definition.name,
            session_id=session_id,
            model=self._definition.llm_model,
        )

        history = await self._memory.load(session_id)
        if history:
            payload["history"] = "\n".join(
                f"{t['role']}: {t['content']}" for t in history
            )
        else:
            payload.setdefault("history", "")

        all_chunks: list[str] = []
        passes = 1

        try:
            if self._definition.max_steps > 1 and self._tools:
                # --- ReAct loop ---
                async for chunk in self._react_loop(payload, span):
                    all_chunks.append(chunk)
                    yield chunk
                passes = len(span._trajectory)
            else:
                # --- Single-pass ---
                current_response: list[str] = []

                with span.child_llm_call(pass_number=1, kind="llm_call") as call_span:
                    async for chunk in self._adapter.astream(payload, call_span=call_span):
                        current_response.append(chunk)
                        all_chunks.append(chunk)
                        yield chunk

                # --- Improvement passes ---
                for improve_adapter, output_key in self._improvement_adapters:
                    passes += 1
                    payload[output_key] = "".join(current_response)
                    current_response = []
                    with span.child_llm_call(pass_number=passes, kind="improvement_pass") as call_span:
                        async for chunk in improve_adapter.astream(payload, call_span=call_span):
                            current_response.append(chunk)
                            all_chunks.append(chunk)
                            yield chunk

            final_response = "".join(all_chunks)
            token_count = len(final_response.split())

            await self._memory.save(
                session_id, {"role": "assistant", "content": final_response}
            )

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

            # Non-blocking monitoring hook — fire and forget
            self._monitoring_hook(span, token_count, passes)

        except Exception as e:
            span.finish(error=str(e))
            self._monitoring_hook(span, 0, 1, error=str(e))
            log.error(f"Agent '{self._definition.name}' failed: {e}", exc_info=True)
            raise

    async def _react_loop(
        self, payload: dict, span: Span
    ) -> AsyncGenerator[str, None]:
        """
        ReAct Thought/Action/Observation loop.

        Runs up to self._definition.max_steps iterations. Each iteration:
          1. LLM call (buffered — we must parse the full response before acting)
          2. Parse: if Final Answer → stream it and return
          3. Parse: if Action → execute tool, inject Observation, continue
          4. If neither found → treat full response as final answer and return

        Each LLM call and each tool call gets its own child OTel span.
        """
        tool_descriptions = "\n".join(
            f"- {name}: {tool.description}"
            for name, tool in self._tools.items()
        )
        tool_names = ", ".join(self._tools.keys())

        # Render the base user prompt once using the primary adapter's template.
        # We pass payload through the template to get a plain string, then inject
        # that string into the ReAct wrapper at each step.
        try:
            user_prompt = self._adapter._prompt.format(
                **{k: v for k, v in payload.items()
                   if k in self._adapter._prompt.input_variables}
            )
        except Exception:
            user_prompt = str(payload)

        # Lazily build the ReAct adapter the first time (or if tools changed).
        if self._react_adapter is None:
            self._react_adapter = AsyncLLMAdapter(
                prompt_template=_REACT_WRAPPER,
                model=self._definition.llm_model,
                temperature=self._definition.temperature,
            )

        scratchpad = ""
        step = 0

        while step < self._definition.max_steps:
            step += 1

            react_payload = {
                "user_prompt": user_prompt,
                "tool_descriptions": tool_descriptions,
                "tool_names": tool_names,
                "scratchpad": scratchpad,
            }

            # LLM call — buffered so we can parse Action vs Final Answer
            with span.child_llm_call(pass_number=step, kind="llm_call") as llm_span:
                llm_response = await self._react_adapter.ainvoke(
                    react_payload, call_span=llm_span
                )

            log.debug(f"ReAct step {step}/{self._definition.max_steps}: {llm_response[:120]}")

            # --- Parse Action first: if the LLM outputs both an Action and a Final Answer
            # in the same response, honour the Action. Some models try to shortcut by
            # answering without actually calling the tool they promised to call.
            action_match = _ACTION_RE.search(llm_response)
            action_input_match = _ACTION_INPUT_RE.search(llm_response)

            # --- Parse Final Answer (only if no Action found) ---
            final_match = _FINAL_ANSWER_RE.search(llm_response)
            if final_match and not (action_match and action_input_match):
                final_answer = final_match.group(1).strip()
                yield final_answer
                return

            if action_match and action_input_match:
                tool_name = action_match.group(1).strip()
                tool_input = action_input_match.group(1).strip()

                # Append the LLM's Thought/Action to the scratchpad
                scratchpad += f"\n{llm_response.strip()}\nObservation: "

                if tool_name not in self._tools:
                    observation = f"Error: unknown tool '{tool_name}'. Available: {tool_names}"
                    log.warning(f"ReAct: unknown tool '{tool_name}'")
                else:
                    with span.child_llm_call(
                        pass_number=step, kind="tool_call", tool_name=tool_name
                    ) as tool_span:
                        result = await self._tools[tool_name](tool_input)
                        tool_span.output_tokens = len(result.content.split()) if result.content else 0

                    observation = result.content if result.ok else f"Error: {result.error}"
                    log.debug(f"ReAct tool '{tool_name}' → {len(observation)} chars")

                scratchpad += observation
                continue

            # No Action and no Final Answer — treat the whole response as the answer.
            log.debug(f"ReAct: no action or final answer found at step {step}, returning as-is")
            yield llm_response
            return

        # Reached max_steps without a Final Answer — yield whatever the last response was.
        log.warning(
            f"Agent '{self._definition.name}' reached max_steps={self._definition.max_steps} "
            f"without a Final Answer"
        )
        yield llm_response

    def _monitoring_hook(
        self, span: Span, token_count: int, passes: int, error: str | None = None
    ) -> None:
        """
        Record monitoring data synchronously so no dangling async tasks are left.

        Uses direct SQLite writes (< 5ms) rather than scheduling background tasks,
        ensuring the monitoring path is safe to call from any context.
        """
        try:
            from monitoring.collector import _span_to_run_record
            from monitoring.registry import get_registry
            record = _span_to_run_record(span, self._definition, token_count, passes, error)
            registry = get_registry()
            registry.record_run(record)
            if registry._store:
                registry._store._insert_run_sync(record)
        except Exception:
            pass  # monitoring must never affect agent output

    def _write_file(self, stem: str, content: str) -> None:
        try:
            from utils import save_markdown
            path = f"{MD}{stem}.md" if MD else f"{stem}.md"
            save_markdown(path, content)
            log.debug(f"Wrote output to {path}")
        except Exception as e:
            log.error(f"Failed to write output file '{stem}': {e}")
