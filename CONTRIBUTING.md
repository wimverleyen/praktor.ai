# Contributing to praktor.ai

One file to add an agent. One command to test. This document covers project setup, adding new agents, tools, and memory backends.

---

## Project setup

praktor uses [`uv`](https://github.com/astral-sh/uv) for dependency management (10x faster than pip, automatic venv, reproducible).

**1. Install uv**

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh   # macOS / Linux
# or: brew install uv
# or: pipx install uv
```

**2. Clone and install**

```bash
git clone https://github.com/wimverleyen/praktor.ai.git
cd praktor.ai

# Create venv + install in editable mode with dev dependencies
uv venv && uv pip install -e ".[dev]"

# Or use the Makefile
make install-dev
```

**3. Configure environment**

```bash
cp .env.example .env
# edit .env with your paths and API keys
```

**4. Install Ollama and pull a model** (for local LLM inference)

```bash
brew install ollama                              # macOS
curl -fsSL https://ollama.ai/install.sh | sh    # Linux
ollama pull qwen2.5
```

**5. Start RabbitMQ** (only needed for queue-based dispatch)

```bash
docker run -d --name rabbitmq -p 5672:5672 rabbitmq:3
```

**6. Run tests** (no live services needed — everything is mocked)

```bash
make test
# or: uv run pytest tests/ -x -v
```

### Install variants

```bash
make install         # core only
make install-dev     # + pytest, black (default for contributors)
make install-all     # + presidio, kafka, minio, otel, docs — everything

# Or individual extras:
uv pip install -e ".[presidio]"        # ML-based PHI detection
uv pip install -e ".[kafka,minio]"     # enterprise audit sinks
uv pip install -e ".[otel]"            # OpenTelemetry trace export
uv pip install -e ".[docs]"            # mkdocs for building docs
```

### Docker-based development

If you prefer not to install Python locally:

```bash
docker build -t praktor --build-arg EXTRAS="dev" .
docker compose up                   # starts RabbitMQ + consumer
```

---

## Adding a new agent

One file. No framework changes required.

**1. Create `praktor/agents/my_agent.py`:**

```python
from pydantic import BaseModel
from core.agent_definition import AgentDefinition, MemoryPolicy, OutputSink

class MyInput(BaseModel):
    agent_type: str = "my_agent"
    topic: str
    session_id: str = ""

MyAgentDefinition = AgentDefinition(
    name="my_agent",
    prompt_template="You are an expert. Answer this: {topic}\n\nHistory: {history}",
    input_schema=MyInput,
    llm_model="qwen2.5",           # or "claude-sonnet-4-6", "gpt-4o"
    temperature=0.0,                # 0.0 = deterministic = cache-eligible
    memory_policy=MemoryPolicy.SHORT_TERM,
    output_sink=OutputSink.BOTH,
    output_file="my_agent_output",
)
```

**2. Register it in `praktor/agents/__init__.py`:**

```python
from agents.my_agent import MyAgentDefinition
_router.register(MyAgentDefinition)
```

**3. Test it:**

```bash
python -m praktor publish --agent my_agent --data '{"topic": "async generators in Python"}'
```

That's it.

---

## Adding improvement passes

Each pass receives the previous LLM response under its `output_key`. The `cover_letter` agent uses three passes as a reference:

```python
from core.agent_definition import AgentDefinition, ImprovementPass

MyAgentDefinition = AgentDefinition(
    name="my_agent",
    prompt_template="Draft a response about: {topic}",
    input_schema=MyInput,
    improvement_passes=[
        ImprovementPass(
            prompt_template="Improve this draft: {response}\n\nFocus on clarity.",
            output_key="response",
        ),
    ],
)
```

Each `ImprovementPass` adds one more LLM call. Passes are sequential — each sees the previous result. All chunks are streamed to the consumer as they arrive.

---

## Adding a tool

A tool is any object with `name`, `description`, and an async `__call__`.

**1. Create `praktor/tools/my_tool.py`:**

```python
from core.tool import register_tool, ToolResult

class MyTool:
    name = "my_tool"
    description = "Does something useful with a string input."

    async def __call__(self, input: str) -> ToolResult:
        result = await do_something(input)
        return ToolResult(output=result)

register_tool(MyTool())  # auto-registers at import time
```

**2. Import it somewhere that runs at startup** (e.g., in `praktor/agents/__init__.py`):

```python
import tools.my_tool  # noqa: F401 — registers the tool
```

**3. Reference the tool by name in an `AgentDefinition`:**

```python
AgentDefinition(
    name="my_agent",
    tools=["my_tool"],
    ...
)
```

The `Agent.__init__` resolves tool names to instances from `_TOOL_REGISTRY`. Tools are currently available for future ReAct loop integration (`max_steps > 1` on `AgentDefinition`).

---

## Adding a memory backend

Implement the `Memory` protocol from `core/memory.py`:

```python
class Memory(Protocol):
    async def load(self, session_id: str) -> list[dict]: ...
    async def save(self, session_id: str, turn: dict) -> None: ...
```

Then wire it to a new `MemoryPolicy` variant in `core/agent.py`'s `_build_memory()`:

```python
elif definition.memory_policy == MemoryPolicy.REDIS:
    return RedisMemory(...)
```

See `memory/buffer.py` (InMemoryBuffer) and `memory/vector.py` (FAISSMemory) for working examples.

---

## Changing the LLM

Per-agent: set `llm_model` on `AgentDefinition`.

Globally: set `PRAKTOR_MODEL` in `.env`.

Supported model strings:

| Prefix | Provider | Key required |
|--------|----------|-------------|
| `claude-*` | Anthropic | `ANTHROPIC_API_KEY` |
| `gpt-*` | OpenAI | `OPENAI_API_KEY` |
| anything else | Ollama (local) | none |

`LLMFactory` in `LLM/llm_factory.py` handles the routing. To add a new provider, add a branch there.

---

## Adding governance to an agent

Any agent becomes governed by adding a `GovernancePolicy`:

```python
from core.agent_definition import AgentDefinition, MemoryPolicy, OutputSink
from governance import GovernancePolicy, DetectorConfig, PolicyAction, AuditSinkType

GovernerDefinition = AgentDefinition(
    name="medical_qa",
    prompt_template="Answer: {question}",
    input_schema=MedicalInput,
    governance_policy=GovernancePolicy(
        pre_execution=[
            DetectorConfig(
                detector_class="governance.detectors.RegexDetector",
                entities=["US_SSN", "PHONE_NUMBER", "EMAIL_ADDRESS"],
                action=PolicyAction.REDACT,  # PHI scrubbed before LLM sees it
            ),
        ],
        post_execution=[
            DetectorConfig(
                detector_class="governance.detectors.RegexDetector",
                entities=["US_SSN"],
                action=PolicyAction.BLOCK,  # Halt if LLM generates PHI
            ),
        ],
        audit_sinks=[AuditSinkType.LOCAL_FILE],
        rbac_required_roles=["hipaa-reader"],
    ),
)
```

**Actions:**

| Action | Pre-execution | Post-execution |
|--------|-------------|---------------|
| `ALLOW` | No-op (default) | No-op |
| `REDACT` | Replace PHI with `[REDACTED]` before LLM | Replace in response text |
| `FLAG` | Audit entry flagged, agent continues | Audit entry flagged |
| `BLOCK` | Raise `GovernancePolicyViolation`, halt | Raise violation, halt |

For evaluation passes (toxicity scoring, relevance checks), see the [Evaluators API docs](https://praktor.ai/api/evaluators/).

---

## Code style

- Python 3.11+
- Black formatting (`black praktor/ tests/`)
- Type hints on all public functions
- New agents: include a Pydantic `Input` model in the same file
- New tests: mock the LLM and filesystem — no live services in tests

---

## Project layout

```
praktor/
├── core/          # Framework: AgentDefinition, Agent, Router, Memory, Tool, Span
├── agents/        # One file per agent — this is where you add new ones
├── memory/        # InMemoryBuffer, FAISSMemory
├── tools/         # web_search, file_io — add new tools here
├── transport/     # aio-pika consumer/producer
└── LLM/           # LLMFactory, AsyncLLMAdapter
```

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full design rationale, dependency order, and concurrency model.
