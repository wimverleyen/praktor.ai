import asyncio
import re
import sys
from typing import AsyncGenerator

from praktor.core.agent_definition import AgentDefinition, MemoryPolicy, OutputSink
from praktor.core.memory import NullMemory
from praktor.core.observability import Span
from praktor.core.tool import get_tool
from praktor.LLM.llm_interface import AsyncLLMAdapter

from praktor.settings import MD, create_log

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

        # AIGov — LedgerStore opened once per Agent when obligation_bundle is set
        self._ledger_store = None
        if definition.obligation_bundle:
            try:
                import os
                from praktor.aigov.ledger.store import LedgerStore
                db_path = os.environ.get("AIGOV_LEDGER_PATH") or None
                self._ledger_store = LedgerStore(db_path=db_path)
            except Exception as exc:
                log.warning(f"AIGov LedgerStore init failed — obligation checks disabled: {exc}")

        # Governance — cache evaluator instances so import_module is not called per run
        self._evaluators: list[tuple] = []  # list of (EvaluationPass, Evaluator)
        if definition.governance_policy:
            from praktor.governance.evaluators import load_evaluator, EvaluatorUnavailableError
            for eval_pass in definition.governance_policy.evaluation_passes:
                try:
                    evaluator = load_evaluator(eval_pass.evaluator_class)
                    self._evaluators.append((eval_pass, evaluator))
                except Exception as exc:
                    log.warning(f"Could not load evaluator '{eval_pass.evaluator_class}': {exc}")

        # Memory
        if definition.memory_policy == MemoryPolicy.NONE:
            self._memory = NullMemory()
        elif definition.memory_policy == MemoryPolicy.SHORT_TERM:
            from praktor.memory.buffer import InMemoryBuffer
            self._memory = InMemoryBuffer()
        elif definition.memory_policy == MemoryPolicy.LONG_TERM:
            from praktor.memory.vector import FAISSMemory
            self._memory = FAISSMemory()

    @property
    def definition(self) -> AgentDefinition:
        return self._definition

    async def run(self, payload: dict, session_id: str) -> AsyncGenerator[str, None]:
        """
        Execute the agent and yield response chunks.

        Routes to _react_loop() when max_steps > 1 and tools are registered,
        otherwise runs the single-pass (+ improvement passes) path.

        When governance_policy is set: pre-execution detection runs before the LLM
        call; the response is fully buffered before any chunks are yielded so that
        post-execution detection and evaluation can fire before data leaves this
        process boundary.
        """
        policy = self._definition.governance_policy
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
        audit_entry = None
        audit_sinks = []

        if policy:
            from praktor.governance.audit import AuditEntry, LocalFileAuditSink, StdoutAuditSink
            from praktor.governance.policy import AuditSinkType, GovernancePolicyViolation
            import hashlib, time

            prompt_text = str(payload)
            audit_entry = AuditEntry(
                agent_type=self._definition.name,
                session_id=session_id,
                model=self._definition.llm_model,
                prompt_hash=AuditEntry.hash_text(prompt_text),
                caller_identity=str(payload.get("caller_identity", "anonymous")),
            )

            if not policy.dry_run:
                for sink_type in policy.audit_sinks:
                    if sink_type == AuditSinkType.LOCAL_FILE:
                        audit_sinks.append(LocalFileAuditSink())
                    elif sink_type == AuditSinkType.STDOUT:
                        audit_sinks.append(StdoutAuditSink())
                    elif sink_type == AuditSinkType.KAFKA:
                        try:
                            from praktor.governance.audit_kafka import KafkaAuditSink
                            audit_sinks.append(KafkaAuditSink())
                        except Exception as exc:
                            log.warning(f"KafkaAuditSink init failed: {exc}")
                    elif sink_type == AuditSinkType.MINIO:
                        log.warning("MinioAuditSink not yet implemented (Phase 4)")

        try:
            # --- Pre-execution governance ---
            if policy and policy.pre_execution:
                from praktor.governance.detectors import load_detector
                from praktor.governance.policy import PolicyAction, GovernancePolicyViolation

                for det_cfg in policy.pre_execution:
                    detector = load_detector(det_cfg.detector_class)
                    for field_name, field_value in list(payload.items()):
                        if not isinstance(field_value, str):
                            continue
                        results = await detector.detect(field_value, det_cfg.entities)
                        for r in results:
                            if r.score < det_cfg.threshold:
                                continue
                            action_record = {
                                "detector_class": det_cfg.detector_class,
                                "entity_type": r.entity_type,
                                "action": det_cfg.action.value,
                                "count": 1,
                                "field": field_name,
                            }
                            if audit_entry is not None:
                                audit_entry.governance_actions.append(action_record)

                            from praktor.monitoring.governance import record_governance_detection, record_governance_violation, record_governance_dry_run
                            record_governance_detection(r.entity_type)

                            if det_cfg.action == PolicyAction.BLOCK:
                                msg = f"BLOCK: {r.entity_type} detected in field '{field_name}'"
                                if audit_entry is not None:
                                    audit_entry.flagged = True
                                if policy.dry_run:
                                    sys.stderr.write(f"[governance dry_run] {msg}\n")
                                    record_governance_dry_run()
                                else:
                                    record_governance_violation("block", r.entity_type)
                                    raise GovernancePolicyViolation(
                                        msg,
                                        field_name=field_name,
                                        entity_type=r.entity_type,
                                        detector_class=det_cfg.detector_class,
                                    )
                            elif det_cfg.action == PolicyAction.REDACT:
                                record_governance_violation("redact", r.entity_type)
                                payload[field_name] = payload[field_name].replace(
                                    r.text, f"[REDACTED:{r.entity_type}]"
                                )
                            elif det_cfg.action == PolicyAction.FLAG:
                                record_governance_violation("flag", r.entity_type)
                                if audit_entry is not None:
                                    audit_entry.flagged = True

            # --- LLM execution ---
            if self._definition.max_steps > 1 and self._tools:
                # --- ReAct loop (always buffers — final answer is a single string) ---
                async for chunk in self._react_loop(payload, span):
                    all_chunks.append(chunk)
                passes = len(span._trajectory)
            else:
                # --- Single-pass ---
                current_response: list[str] = []

                with span.child_llm_call(pass_number=1, kind="llm_call") as call_span:
                    async for chunk in self._adapter.astream(payload, call_span=call_span):
                        current_response.append(chunk)
                        all_chunks.append(chunk)

                # --- Improvement passes ---
                for improve_adapter, output_key in self._improvement_adapters:
                    passes += 1
                    payload[output_key] = "".join(current_response)
                    current_response = []
                    with span.child_llm_call(pass_number=passes, kind="improvement_pass") as call_span:
                        async for chunk in improve_adapter.astream(payload, call_span=call_span):
                            current_response.append(chunk)
                            all_chunks.append(chunk)

            final_response = "".join(all_chunks)

            # --- Post-execution governance ---
            if policy and policy.post_execution:
                from praktor.governance.detectors import load_detector
                from praktor.governance.policy import PolicyAction, GovernancePolicyViolation

                for det_cfg in policy.post_execution:
                    detector = load_detector(det_cfg.detector_class)
                    results = await detector.detect(final_response, det_cfg.entities)
                    for r in results:
                        if r.score < det_cfg.threshold:
                            continue
                        action_record = {
                            "detector_class": det_cfg.detector_class,
                            "entity_type": r.entity_type,
                            "action": det_cfg.action.value,
                            "count": 1,
                            "field": "response",
                        }
                        if audit_entry is not None:
                            audit_entry.governance_actions.append(action_record)

                        from praktor.monitoring.governance import record_governance_detection, record_governance_violation, record_governance_dry_run
                        record_governance_detection(r.entity_type)

                        if det_cfg.action == PolicyAction.BLOCK:
                            msg = f"BLOCK: {r.entity_type} detected in response"
                            if audit_entry is not None:
                                audit_entry.flagged = True
                            if policy.dry_run:
                                sys.stderr.write(f"[governance dry_run] {msg}\n")
                                record_governance_dry_run()
                            else:
                                record_governance_violation("block", r.entity_type)
                                raise GovernancePolicyViolation(
                                    msg,
                                    field_name="response",
                                    entity_type=r.entity_type,
                                    detector_class=det_cfg.detector_class,
                                )
                        elif det_cfg.action == PolicyAction.REDACT:
                            record_governance_violation("redact", r.entity_type)
                            final_response = final_response.replace(
                                r.text, f"[REDACTED:{r.entity_type}]"
                            )
                        elif det_cfg.action == PolicyAction.FLAG:
                            record_governance_violation("flag", r.entity_type)
                            if audit_entry is not None:
                                audit_entry.flagged = True

            # --- Evaluation passes ---
            if policy and self._evaluators:
                from praktor.governance.policy import PolicyAction, EvaluationFailedError

                for eval_pass, evaluator in self._evaluators:
                    try:
                        score = await evaluator.score(str(payload), final_response)
                    except Exception as exc:
                        log.warning(f"Evaluator '{eval_pass.evaluator_class}' failed: {exc}. score=0.0")
                        score = 0.0

                    passed = score >= eval_pass.pass_threshold
                    score_record = {
                        "evaluator_class": eval_pass.evaluator_class,
                        "metric_name": eval_pass.metric_name,
                        "score": score,
                        "pass": passed,
                    }
                    if audit_entry is not None:
                        audit_entry.evaluation_scores.append(score_record)

                    if not passed:
                        if eval_pass.on_fail == PolicyAction.FLAG:
                            if audit_entry is not None:
                                audit_entry.flagged = True
                        elif eval_pass.on_fail == PolicyAction.BLOCK:
                            if audit_entry is not None:
                                audit_entry.flagged = True
                            if not (policy and policy.dry_run):
                                raise EvaluationFailedError(
                                    f"Evaluation failed: metric={eval_pass.metric_name} "
                                    f"score={score:.3f} < threshold={eval_pass.pass_threshold}"
                                )

            # --- AIGov G-RUN obligation checks ---
            if self._definition.obligation_bundle and self._ledger_store:
                await self._run_grun_checks(str(payload), final_response)

            # --- Yield buffered response ---
            # (if no policy: chunks were collected but not yielded; yield them now)
            # (if policy: governance has run; safe to yield)
            if policy:
                # Re-split final_response in case REDACT changed it
                yield final_response
            else:
                for chunk in all_chunks:
                    yield chunk

            token_count = len(final_response.split())

            if audit_entry is not None:
                audit_entry.response_hash = AuditEntry.hash_text(final_response)
                audit_entry.token_count = token_count

            # Memory stores the post-governance (possibly redacted) response
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

        finally:
            # Audit entry written unconditionally — covers BLOCK and error paths
            if audit_entry is not None and audit_sinks:
                for sink in audit_sinks:
                    try:
                        await sink.write(audit_entry)
                    except Exception as exc:
                        log.error(f"Audit sink write failed: {exc}")

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

    async def _run_grun_checks(self, payload_str: str, response: str) -> None:
        """
        Run G-RUN obligation checks for every obligation in the bundle.

        Each obligation's check_run() is called concurrently. Results are stamped
        with agent context then written to the ledger in one batch. All failures
        are caught and logged — obligation checks must never crash the agent.
        """
        import asyncio
        import dataclasses

        bundle = self._definition.obligation_bundle

        async def _check_one(ob):
            try:
                ev = await ob.check_run(payload_str, response)
                return dataclasses.replace(
                    ev,
                    agent_id=self._definition.name,
                    bundle_id=bundle.bundle_id,
                    agent_pattern=self._definition.agent_pattern,
                )
            except Exception as exc:
                log.warning(f"AIGov {ob.id}.check_run() raised: {exc}")
                return None

        results = await asyncio.gather(
            *(_check_one(ob) for ob in bundle),
            return_exceptions=False,
        )
        events = [ev for ev in results if ev is not None]

        if events:
            try:
                await self._ledger_store.write_events(events)
            except Exception as exc:
                log.warning(f"AIGov ledger write failed: {exc}")

    def _monitoring_hook(
        self, span: Span, token_count: int, passes: int, error: str | None = None
    ) -> None:
        """
        Record monitoring data synchronously so no dangling async tasks are left.

        Uses direct SQLite writes (< 5ms) rather than scheduling background tasks,
        ensuring the monitoring path is safe to call from any context.
        """
        try:
            from praktor.monitoring.collector import _span_to_run_record
            from praktor.monitoring.registry import get_registry
            record = _span_to_run_record(span, self._definition, token_count, passes, error)
            registry = get_registry()
            registry.record_run(record)
            if registry._store:
                registry._store._insert_run_sync(record)
        except Exception:
            pass  # monitoring must never affect agent output

    def _write_file(self, stem: str, content: str) -> None:
        try:
            from praktor.utils import save_markdown
            path = f"{MD}{stem}.md" if MD else f"{stem}.md"
            save_markdown(path, content)
            log.debug(f"Wrote output to {path}")
        except Exception as e:
            log.error(f"Failed to write output file '{stem}': {e}")
