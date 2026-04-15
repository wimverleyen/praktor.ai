# praktor.ai

General-purpose agentic framework built on LangChain, RabbitMQ, and local or hosted LLMs. Ships with a **ReAct tool-use loop**, **OpenTelemetry observability**, **automated prompt optimization**, and a **continuous monitoring stack** (Prometheus, Grafana, SQLite). Comes with built-in agents for job-application workflows — but any agent is one file.

→ [Architecture deep-dive](ARCHITECTURE.md) · [Contributing guide](CONTRIBUTING.md)

---

## How it works

```
Producer (transport/producer.py)
  → RabbitMQ queue "agentic"
  → Async consumer (transport/consumer.py)
  → Router (core/router.py)          ← dynamic dispatch by agent_type
  → Agent.run()                       ← async generator, yields token chunks
      ├─ Single-pass path             ← one LLM call + optional improvement passes
      └─ ReAct loop (max_steps > 1)   ← Thought → Action → Observation → repeat
  → Memory (None | buffer | FAISS)
  → Monitoring (metrics + SQLite + OTel spans)
```

---

## Setup

**1. Install dependencies**

```bash
pip install -r requirements.txt
```

**2. Configure environment**

```bash
cp .env.example .env
```

| Variable | Default | Description |
|----------|---------|-------------|
| `PRAKTOR_MODEL` | `qwen2.5` | Default Ollama model |
| `RABBITMQ_URL` | `amqp://guest:guest@localhost/` | RabbitMQ connection string |
| `PRAKTOR_CONCURRENCY` | `4` | Max concurrent agents |
| `CACHE_DIR` | `/tmp/praktor_cache` | Prompt-response cache directory |
| `CACHE_TTL` | `3600` | Cache TTL in seconds |
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama base URL |
| `OTLP_ENDPOINT` | — | OTLP gRPC collector (Jaeger, Grafana Alloy). Unset → stdout |
| `PRAKTOR_MONITORING_DB` | `~/.praktor/monitoring.db` | SQLite monitoring store |
| `ANTHROPIC_API_KEY` | — | Required for `claude-*` models |
| `OPENAI_API_KEY` | — | Required for `gpt-*` models |
| `MD` | — | Directory for markdown output files |
| `PDF` | — | Directory containing input PDF files |
| `VECTOR_DB` | — | Path for the FAISS vector store |

**3. Start RabbitMQ**

```bash
docker run -d --name rabbitmq -p 5672:5672 rabbitmq:3
```

---

## Running

```bash
# Start the async consumer
python -m praktor receive

# Publish a task
python -m praktor publish --agent cover_letter \
  --data '{"job_title":"VP Engineering","company":"Acme","job_description":"..."}'

# List registered agents and their required fields
python -m praktor list
```

---

## ReAct agent (tool-use loop)

Set `max_steps > 1` and list tools — the agent automatically enters a Thought → Action → Observation loop.

```python
from pydantic import BaseModel
from core.agent_definition import AgentDefinition, MemoryPolicy
from core.agent import Agent
import tools.web_search  # registers at import time

class ResearchInput(BaseModel):
    agent_type: str = "researcher"
    question: str
    session_id: str = ""
    history: str = ""

definition = AgentDefinition(
    name="researcher",
    prompt_template="Answer this question: {question}\n\nHistory: {history}",
    input_schema=ResearchInput,
    llm_model="llama3:8b",
    tools=["web_search"],
    max_steps=4,                         # enables ReAct loop
    memory_policy=MemoryPolicy.NONE,
)
agent = Agent(definition)

async for chunk in agent.run({"question": "What are the latest OTel features for LLMs?"}, session_id="s1"):
    print(chunk, end="", flush=True)
```

**Run the interactive ReAct demo:**

```bash
PYTHONPATH=praktor python scripts/demo_react.py \
  --question "Compare FAISS vs Chroma for vector search" \
  --model llama3:8b
```

---

## Prompt versioning

Every prompt version is content-addressed (SHA-256), stored in `~/.praktor/prompts/`, and queryable by prefix.

```python
from core.prompt_registry import PromptRegistry

registry = PromptRegistry()
v1 = registry.save("cover_letter", template="You are a writer...", notes="baseline", set_active=True)
print(registry.diff("cover_letter", v1_id, v2_id))   # unified diff
```

**CLI:**

```bash
python -m praktor prompt list cover_letter
python -m praktor prompt diff cover_letter abc123 def456
python -m praktor prompt activate cover_letter def456
```

---

## LLM-as-judge evaluation

Score any agent response on four criteria (0–10 each): relevance, accuracy, completeness, conciseness.

```python
from core.judge import JudgeEvaluator

judge = JudgeEvaluator(model="llama3:8b")
score = await judge.evaluate(
    question="What is RAG?",
    response=agent_response,
    expected=reference_answer,   # optional
)
print(score.summary())
# → overall=7.80/10  rel=8.0  acc=8.0  cmp=7.0  con=8.0  | Good structured answer.

# Head-to-head comparison
cmp = await judge.compare(question, response_a, response_b)
print(cmp["winner"], cmp["reasoning"])
```

Scores are recorded back to `PromptRegistry.record_eval()` and the monitoring SQLite store.

---

## Automated prompt optimization

Two modes, one interface. Picks the best available backend automatically.

```python
from core.prompt_optimizer import PromptOptimizer

optimizer = PromptOptimizer(agent_name="researcher", model="llama3:8b")

# Build examples from past runs
examples = [{"input": {"question": "What is RAG?"}, "output": agent_response}]

result = await optimizer.optimize(
    examples,
    goal="Improve completeness and technical depth for ML practitioners.",
)
print(result.summary())
# → [native] 7.22 → 8.42 ↑  version=813efcd6  native-opt: Improve completeness...
```

| Mode | When | How |
|------|------|-----|
| **Native** | Always available | Meta-LLM rewrites the prompt using examples + judge scores (COPRO-style) |
| **DSPy** | `dspy-ai` installed | `BootstrapFewShot` compiles few-shot examples into the prompt |

**Run the full judge + optimization demo:**

```bash
# Dry run (no Ollama needed)
PYTHONPATH=praktor python scripts/demo_judge_optimization.py --dry-run

# Real Ollama
PYTHONPATH=praktor python scripts/demo_judge_optimization.py --model llama3:8b
```

The demo runs 8 steps: register v1 → judge 5 questions → identify weakest criterion → optimize → diff → re-evaluate → before/after comparison.

---

## Continuous monitoring

Every `Agent.run()` is automatically recorded — no code changes required.

```python
# Optional: start Prometheus scrape server at startup
from monitoring import configure, record_kpi
configure(prometheus_port=8080)

# Record business KPIs anywhere
record_kpi("cover_letter_accepted", 1.0, tags={"source": "linkedin"})
record_kpi("search_quality", 8.5, tags={"agent": "researcher"})
```

**Data products:**

| Product | How to access |
|---------|--------------|
| SQLite store | `~/.praktor/monitoring.db` — always written |
| CLI summary | `python -m praktor monitor summary [--agent X] [--hours 24]` |
| Prometheus | `python -m praktor monitor serve --port 8080` → `http://localhost:8080/metrics` |
| Grafana JSON | `python -m praktor monitor export grafana > dashboard.json` then import |
| KPI log | `python -m praktor monitor kpi --name cover_letter_accepted` |

**Metrics collected per run:**

- Cost (USD) from token pricing table (35+ models; local = $0.00)
- Input/output tokens, total tokens
- Duration (P50/P95/P99 histograms)
- Tool call counts and error rates
- Cache hit ratio
- LLM judge scores (if evaluated)
- Custom business KPIs

**Run the live monitoring demo:**

```bash
# Dry run — instant, no Ollama
PYTHONPATH=praktor python scripts/demo_monitoring.py --dry-run --no-judge

# Real Ollama — 12 agent tasks with live terminal dashboard
PYTHONPATH=praktor python scripts/demo_monitoring.py --model llama3:8b
```

**Grafana dashboard (21 panels, auto-generated):**

```bash
python -m praktor monitor export grafana > praktor-dashboard.json
# Grafana → Dashboards → Import → Upload JSON
```

Panels cover: run rate, token throughput, cost by model, latency percentiles, error rate, judge score distribution, cache efficiency, tool call breakdown, and business KPIs — all with `agent` and `model` template variables.

---

## Observability (OpenTelemetry)

Every agent run emits OTel traces with child spans per LLM call and tool call. Set `OTLP_ENDPOINT` to export to any collector; unset → stdout for local dev.

```
SPAN {"agent_type": "cover_letter", "session_id": "a3f1b2c4", "model": "qwen2.5",
      "duration_ms": 4821.3, "token_count": 312, "passes": 3, "cached": false,
      "trajectory_steps": 3}
```

Child span attributes: `llm.pass`, `llm.kind`, `llm.output_tokens`, `llm.latency_ms`, `llm.cached`, `tool.name`.

---

## Built-in agents

| Agent type | What it does | Memory | Passes |
|------------|-------------|--------|--------|
| `job_application` | Resume tailored to a job description | None | 1 |
| `cover_letter` | Cover letter with two rounds of automated improvement | None | 3 |
| `keywords_extraction` | Keyword gap analysis across resume and job description | None | 1 |
| `job_interview` | Interview prep using your FAISS document store | Long-term (FAISS) | 1 |
| `thank_you` | Post-interview thank you email | None | 1 |
| `search` | Research a topic with conversation context | Short-term | 1 |
| `message` | Professional message with a specified tone | None | 1 |

---

## Adding a new agent

One file. No other changes required.

```python
# praktor/agents/my_agent.py
from pydantic import BaseModel
from core.agent_definition import AgentDefinition, MemoryPolicy, OutputSink

class MyInput(BaseModel):
    agent_type: str = "my_agent"
    topic: str
    session_id: str = ""

MyAgentDefinition = AgentDefinition(
    name="my_agent",
    prompt_template="You are an expert. Answer this: {topic}",
    input_schema=MyInput,
    llm_model="qwen2.5",           # or "claude-sonnet-4-6", "gpt-4o"
    memory_policy=MemoryPolicy.SHORT_TERM,
    tools=["web_search"],          # add tools to enable ReAct loop
    max_steps=3,                   # > 1 enables ReAct
    output_sink=OutputSink.BOTH,
    output_file="my_agent_output",
)
```

Register it in `praktor/agents/__init__.py`:

```python
from agents.my_agent import MyAgentDefinition
_router.register(MyAgentDefinition)
```

---

## Supported LLMs

| Provider | Model string examples | Notes |
|----------|-----------------------|-------|
| Ollama | `qwen2.5`, `llama3:8b`, `mistral` | Local, no API key, zero cost |
| Anthropic | `claude-sonnet-4-6`, `claude-opus-4` | Requires `ANTHROPIC_API_KEY` |
| OpenAI | `gpt-4o`, `gpt-4o-mini`, `o3-mini` | Requires `OPENAI_API_KEY` |

Switch model per-agent via `AgentDefinition.llm_model`, or globally via `PRAKTOR_MODEL`.

---

## Project structure

```
praktor.ai/
├── praktor/
│   ├── __main__.py              # CLI: receive | publish | list | monitor | prompt
│   ├── settings.py              # Config, rotating logs, env vars
│   │
│   ├── core/                    # Framework abstractions
│   │   ├── agent_definition.py  # AgentDefinition dataclass
│   │   ├── agent.py             # Agent: run() → single-pass or ReAct loop
│   │   ├── router.py            # Dynamic dispatch + global singleton
│   │   ├── memory.py            # Memory protocol + NullMemory
│   │   ├── tool.py              # Tool protocol + ToolRegistry
│   │   ├── observability.py     # OTel spans + TrajectoryEvent per LLM/tool call
│   │   ├── prompt_registry.py   # JSONL version store (content-addressed)
│   │   ├── judge.py             # LLM-as-judge: 4-criterion scoring + comparison
│   │   └── prompt_optimizer.py  # Native COPRO-style + optional DSPy optimizer
│   │
│   ├── monitoring/              # Continuous monitoring data products
│   │   ├── __init__.py          # configure(), record_kpi(), record_run()
│   │   ├── cost.py              # Token pricing table (35+ models)
│   │   ├── store.py             # SQLite persistent store
│   │   ├── registry.py          # In-memory counters, histograms, gauges
│   │   ├── collector.py         # Span → RunRecord bridge
│   │   └── exporters/
│   │       ├── prometheus.py    # Prometheus HTTP scrape server
│   │       ├── otel.py          # OTel metrics via OTLP_ENDPOINT
│   │       └── grafana.py       # 21-panel Grafana dashboard JSON builder
│   │
│   ├── agents/                  # Built-in agent definitions (one file each)
│   ├── memory/                  # InMemoryBuffer + FAISSMemory
│   ├── tools/                   # web_search (DuckDuckGo), file_io
│   ├── transport/               # aio-pika consumer + producer
│   └── LLM/                     # AsyncLLMAdapter (streaming + retry + cache)
│
├── scripts/
│   ├── demo_react.py            # Interactive ReAct loop demo (colour output)
│   ├── demo_monitoring.py       # Live terminal dashboard + Prometheus
│   ├── demo_judge_optimization.py  # Judge eval + prompt optimization pipeline
│   └── init_vector_db.py        # Seed FAISS store from PDF directory
│
├── tests/                       # pytest — all mocked, no live services needed
│   ├── test_observability.py    # 17 tests: Span, TrajectoryEvent, LLMCallSpan
│   ├── test_react.py            # 8 tests: ReAct loop + observability
│   ├── test_prompt_versioning.py # 27 tests: registry, judge, optimizer
│   └── test_monitoring.py       # 47 tests: cost, store, registry, Grafana
│
├── praktor-dashboard.json       # Grafana dashboard (import-ready)
├── .env.example
└── requirements.txt
```

---

## Tests

```bash
pytest tests/
# 99 tests across observability, ReAct, prompt versioning, and monitoring
```

All tests mock the LLM and filesystem. No live Ollama, RabbitMQ, or FAISS needed.

---

## CLI reference

```bash
# Agent runtime
python -m praktor receive                    # start async consumer
python -m praktor publish --agent X --data '{}' # publish a task
python -m praktor list                       # list registered agents

# Monitoring
python -m praktor monitor summary            # print last-24h summary
python -m praktor monitor serve --port 8080  # start Prometheus endpoint
python -m praktor monitor export grafana     # print Grafana dashboard JSON
python -m praktor monitor kpi --name X       # list KPI events

# Prompt management
python -m praktor prompt list <agent>        # list versions
python -m praktor prompt diff <agent> v1 v2  # unified diff
python -m praktor prompt activate <agent> <version_id>
python -m praktor prompt eval <agent> <version_id> -q "..." -r "..."
python -m praktor prompt optimize <agent> -x examples.json --goal "..."
```
