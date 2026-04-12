# Architecture

praktor.ai is built around five abstractions that compose in a strict dependency order. Understanding them is enough to add new agents, tools, or memory backends without touching the framework core.

---

## The five abstractions

```
Runtime (asyncio event loop + aio-pika connection)
  └── Router   ← validates messages, selects agents
        └── Agent   ← async generator, yields token chunks
              ├── AsyncLLMAdapter  ← streaming + retry + cache
              ├── Memory           ← NullMemory | InMemoryBuffer | FAISSMemory
              └── Tool             ← web_search | read_file | write_file
```

### 1. AgentDefinition (`core/agent_definition.py`)

The single declarative unit. One instance = one agent. No registration boilerplate beyond `router.register(definition)`.

```python
@dataclass
class AgentDefinition:
    name: str                          # maps to agent_type in queue messages
    prompt_template: str               # f-string with {variable} placeholders
    input_schema: type[BaseModel]      # Pydantic model for validation
    llm_model: str = "qwen2.5"
    temperature: float = 0.0           # 0.0 = deterministic = cache-eligible
    tools: list[str] = []              # names from ToolRegistry
    memory_policy: MemoryPolicy = NONE
    output_sink: OutputSink = STREAM
    output_file: str = ""
    improvement_passes: list[ImprovementPass] = []
    max_steps: int = 1                 # >1 = ReAct tool-use loop (future)
```

### 2. Agent (`core/agent.py`)

Executes an `AgentDefinition`. The `run()` method is an async generator — it yields token chunks as they arrive from the LLM.

```
run(payload, session_id) → AsyncGenerator[str, None]
  1. Load memory context → inject into payload as {history}
  2. Stream initial pass (AsyncLLMAdapter.astream)
  3. For each improvement pass: inject previous response, stream again
  4. Save final response to memory
  5. Write to file if OutputSink.FILE or BOTH
  6. Emit Span (latency, tokens, passes, cached)
```

The improvement pass chain is how `cover_letter` does three sequential LLM calls — each pass receives the previous result under `cover_letter` key. No special framework code needed; it's just `ImprovementPass` entries on the definition.

### 3. Router (`core/router.py`)

Owns the agent registry. Dispatches raw queue bytes → validated payload → correct `Agent.run`.

```
dispatch(raw: bytes) → AsyncGenerator[str, None]
  1. JSON parse
  2. Look up agent by agent_type
  3. Validate payload against agent.definition.input_schema
  4. Generate or pass through session_id
  5. Delegate to agent.run()
```

A global singleton is available via `get_global_router()`. Importing `praktor.agents` auto-registers all built-in agents against it.

### 4. Memory (`core/memory.py`, `memory/`)

Three implementations, injected at `Agent.__init__` based on `MemoryPolicy`:

| Policy | Implementation | Use case |
|--------|---------------|----------|
| `NONE` | `NullMemory` | Stateless one-shot agents |
| `SHORT_TERM` | `InMemoryBuffer` | Conversation context within a session |
| `LONG_TERM` | `FAISSMemory` | Semantic retrieval from document store |

`InMemoryBuffer` is a per-session circular deque (default `max_turns=10`). `FAISSMemory` wraps the FAISS index seeded by `scripts/init_vector_db.py` — it uses similarity search, not session keying.

### 5. Tool (`core/tool.py`, `tools/`)

Protocol + global registry. A tool is any object with `name`, `description`, and an async `__call__(input: str) -> ToolResult`.

Tools register themselves at module import time via `register_tool()`. An agent gains access by listing the tool's `name` in `AgentDefinition.tools`. The `Agent.__init__` resolves names to instances from `_TOOL_REGISTRY`.

---

## Data flow: message to output

```
1. Producer publishes JSON to queue "agentic"
   {"agent_type": "cover_letter", "job_title": "...", ..., "session_id": "a3f1b2c4"}

2. aio-pika consumer receives message (non-blocking, up to CONCURRENCY in flight)
   → asyncio.create_task(handle_message)

3. Router.dispatch(raw_bytes)
   → JSON parse
   → Pydantic validation via CoverLetterInput schema
   → Agent.run(validated_payload, session_id)

4. Agent.run (async generator)
   → Load memory (NullMemory for cover_letter → [])
   → AsyncLLMAdapter.astream(payload)      ← pass 1
   → yield chunks to consumer
   → AsyncLLMAdapter.astream(payload)      ← pass 2 (improvement)
   → yield chunks
   → AsyncLLMAdapter.astream(payload)      ← pass 3 (final polish)
   → yield chunks
   → save_markdown("cover_letter_final.md", full_response)
   → emit Span

5. Consumer acks message
   → stdout: token chunks printed as they arrive
```

---

## AsyncLLMAdapter (`LLM/llm_interface.py`)

The key latency component. Wraps any LangChain LLM with:

- **`astream(data)`** — yields token chunks via LCEL's `chain.astream()`. Falls back to `asyncio.to_thread(chain.invoke)` if the LLM doesn't natively support streaming.
- **Retry** — 3 attempts with exponential backoff (1s, 2s) on any exception.
- **Cache** — `diskcache` keyed on `sha256(model + rendered_prompt_text)`. Only active when `temperature=0.0`. Cache hit = 0ms response time.

The `LLMFactory` handles model routing: `claude-*` → `ChatAnthropic`, `gpt-*` → `OpenAI`, anything else → `OllamaLLM`.

---

## Concurrency model

Single process, single asyncio event loop. `aio-pika` replaces `pika.BlockingConnection`. The consumer sets `prefetch_count=PRAKTOR_CONCURRENCY` (default 4), which allows that many unacknowledged messages in-flight simultaneously.

Each message becomes an `asyncio.Task`. Tasks run concurrently because LLM calls are I/O-bound (HTTP to Ollama or remote API). A slow agent on one task doesn't block others.

`OllamaLLM` uses synchronous HTTP internally. `asyncio.to_thread()` wraps the sync call, releasing the event loop during the wait.

---

## Observability

Every `Agent.run()` creates a `Span` and calls `span.finish()` on completion or error. The span emits a structured JSON log line:

```json
{"agent_type": "cover_letter", "session_id": "a3f1b2c4", "model": "qwen2.5",
 "duration_ms": 4821.3, "token_count": 312, "passes": 3, "cached": false}
```

Swap in OpenTelemetry later by replacing `Span._emit()` — the call sites in `core/agent.py` don't need to change.

---

## What's deferred (intentionally)

- **Multi-agent orchestration** — agents calling other agents requires a message graph, not a dispatch dict
- **Sandboxed code execution** — `tools/code_exec.py` stub exists; needs container isolation before enabling
- **Persistent session storage** — `InMemoryBuffer` resets on restart; Redis/Postgres backend is a drop-in `Memory` implementation
- **HTTP/WebSocket streaming endpoint** — FastAPI + SSE would mount on the same event loop; API contract not decided yet
- **ReAct loop** — `max_steps > 1` in `AgentDefinition` is the hook; `create_react_agent` integration is next
