# praktor.ai

General-purpose agentic framework built on LangChain, RabbitMQ, and local or hosted LLMs. Ships with a **ReAct tool-use loop**, **OpenTelemetry observability**, **automated prompt optimization**, and a **continuous monitoring stack** (Prometheus, Grafana, SQLite). Comes with built-in agents for job-application workflows — but any agent is one file.

→ [Architecture deep-dive](ARCHITECTURE.md) · [Contributing guide](CONTRIBUTING.md) · [API Docs](https://praktor.ai)

---

## 30-Second Quickstart

No RabbitMQ, no Docker, no cloud API keys. Just Python and a local LLM.

```python
import asyncio
from pydantic import BaseModel
from praktor.core.agent_definition import AgentDefinition, MemoryPolicy, OutputSink
from praktor.core.agent import Agent

class QuestionInput(BaseModel):
    agent_type: str = "question"
    question: str
    session_id: str = ""

definition = AgentDefinition(
    name="question",
    prompt_template="Answer concisely: {question}",
    input_schema=QuestionInput,
    llm_model="qwen2.5",
    memory_policy=MemoryPolicy.NONE,
    output_sink=OutputSink.STDOUT,
)

async def main():
    agent = Agent(definition)
    payload = {"agent_type": "question", "question": "What is HIPAA?"}
    async for chunk in agent.run(payload):
        print(chunk, end="", flush=True)

asyncio.run(main())
```

That's it. One file, one agent, local inference.

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

## Installation

praktor supports three install paths. **`uv` is recommended** (10x faster than pip, reproducible lockfiles, automatic venv).

### Option 1: uv (recommended)

```bash
# Install uv if you don't have it
curl -LsSf https://astral.sh/uv/install.sh | sh   # macOS / Linux
# or: brew install uv
# or: pipx install uv

# Clone and install
git clone https://github.com/wimverleyen/praktor.ai.git
cd praktor.ai
uv venv && uv pip install -e .

# Or via Makefile
make install         # core
make install-dev     # + pytest, black
make install-all     # + presidio, kafka, minio, otel, docs
```

### Option 2: pip

```bash
git clone https://github.com/wimverleyen/praktor.ai.git
cd praktor.ai
python -m venv .venv && source .venv/bin/activate
pip install -e .
```

### Option 3: Docker

No Python install required. See [Docker section](#running-with-docker) below.

```bash
docker build -t praktor .
docker compose up
```

### Optional extras

| Extra | Adds | Install |
|-------|------|---------|
| `presidio` | ML-based PHI detection (names, addresses, MRN) | `uv pip install -e ".[presidio]"` |
| `kafka` | KafkaAuditSink for high-throughput audit logs | `uv pip install -e ".[kafka]"` |
| `minio` | MinIO/S3 audit sink with date partitioning | `uv pip install -e ".[minio]"` |
| `otel` | OpenTelemetry trace export | `uv pip install -e ".[otel]"` |
| `docs` | mkdocs + mkdocs-material for building docs | `uv pip install -e ".[docs]"` |
| `dev` | pytest, pytest-asyncio, black | `uv pip install -e ".[dev]"` |

Combine with commas: `uv pip install -e ".[dev,kafka,minio,presidio]"`

---

## Setup

**1. Install Ollama** (for local LLM inference)

```bash
brew install ollama                                    # macOS
curl -fsSL https://ollama.ai/install.sh | sh           # Linux
ollama pull qwen2.5                                    # download a model
ollama serve                                           # start the daemon (if not running)
```

Other models work too: `llama3.1`, `mistral`, `phi3`, anything Ollama supports. Set `PRAKTOR_MODEL` to switch.

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
| `PRAKTOR_AUDIT_LOG` | `praktor_audit.jsonl` | Governance audit log path |
| `PRAKTOR_RBAC_SECRET` | — | HMAC secret for RBAC tokens (opt-in) |

**3. Start RabbitMQ** (only needed for queue-based dispatch)

```bash
docker run -d --name rabbitmq -p 5672:5672 rabbitmq:3
```

Skip this step if you only use `DirectTransport` (in-process, see [30-second quickstart](#30-second-quickstart)).

**4. Seed the vector store** (only needed for `job_interview` agent)

```bash
uv run python scripts/init_vector_db.py --pdf-dir /path/to/pdfs --db-path /path/to/vector_db
```


---

## Running

```bash
uv run python -m praktor receive
```

# Publish a task
python -m praktor publish --agent cover_letter \
  --data '{"job_title":"VP Engineering","company":"Acme","job_description":"..."}'

```bash
# From JSON string
uv run python -m praktor publish --agent thank_you \
  --data '{"adjective":"professional","position":"VP Data Science","content":"Great conversation about GenAI strategy"}'

# From stdin
echo '{"agent_type":"search","search":"concept drift","content":"production ML systems"}' \
  | uv run python -m praktor publish

# Legacy producer methods (still work)
uv run python -m praktor agent thankyou
uv run python -m praktor agent search
uv run python -m praktor agent message
```

**List registered agents and their required fields:**

```bash
uv run python -m praktor list
```

> **Tip:** if you've activated the venv with `source .venv/bin/activate`, you can drop the `uv run` prefix and just use `python -m praktor ...`.

---

## Running with Docker

Docker bundles praktor with no Python install required. The image uses `uv` for fast, reproducible builds and runs as a non-root user.

### Build

```bash
# Core image (~250 MB)
docker build -t praktor .

# With enterprise audit sinks
docker build -t praktor --build-arg EXTRAS="kafka,minio" .

# With ML-based PHI detection
docker build -t praktor --build-arg EXTRAS="presidio" .
```

### Run standalone

`--network host` lets the container reach Ollama on the host machine.

```bash
# Start consumer
docker run --rm --network host praktor receive

# Publish a task
docker run --rm --network host praktor publish --agent thank_you \
  --data '{"adjective":"warm","position":"CTO","content":"Great chat about AI governance"}'

# List agents
docker run --rm --network host praktor list
```

### Run with docker-compose (RabbitMQ + consumer + audit volume)

```bash
docker compose up                    # start RabbitMQ + consumer
docker compose run --rm praktor publish --agent search \
  --data '{"search":"HIPAA compliance","content":"healthcare AI"}'
```

`docker-compose.yml` provisions a named `praktor-audit` volume so audit logs survive container restarts.

### Override config

```bash
docker run --rm --network host \
  -e PRAKTOR_MODEL=llama3.1 \
  -e PRAKTOR_CONCURRENCY=8 \
  -v $(pwd)/audit:/app/audit \
  praktor receive
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

## Clinical reasoning — HEDIS gap closure

A full clinical AI layer for Medicare Advantage care management, built directly on the praktor.ai framework. Closes HEDIS quality gaps by running a clinical ReAct reasoning loop per member and surfacing a ranked Next Best Action to a care manager.

**STARS impact:** Targeting triple-weighted measures (MAC statin, MAD diabetes, MAP hypertension) first — each closed gap drives CMS Quality Bonus Payment improvement.

### Quick demo (no Ollama required)

```bash
# 1. Seed 5 synthetic members (Spanish, Vietnamese, Mandarin, English profiles)
PYTHONPATH=praktor python scripts/init_member_brain.py --seed-demo

# 2. Run the HEDIS gap agent (dry run — instant, no LLM needed)
PYTHONPATH=praktor python scripts/demo_hedis_agent.py --dry-run

# 3. Real LLM (requires Ollama running locally)
PYTHONPATH=praktor python scripts/demo_hedis_agent.py --model qwen2.5

# 4. Clinical HITL review UI
PYTHONPATH=praktor streamlit run praktor/ui/clinical_app.py
```

### Clinical agent

| Agent type | What it does | Memory | ReAct steps |
|------------|-------------|--------|-------------|
| `hedis_gap` | Prioritize open HEDIS gaps, reason over PDC/labs/SDOH, produce Next Best Action | None | 7 |

**7 clinical tools** the agent uses in its ReAct loop:

| Tool | Input | What it returns |
|------|-------|----------------|
| `gap_registry` | `member_id_hash` | Open HEDIS gaps ranked by priority score |
| `drug_adherence` | `{member_id_hash, drug_class}` | Pre-computed PDC scores vs. 0.80 threshold |
| `claims_lookup` | `{member_id_hash, drug_class?}` | Rx fill history, days supply, NDC codes |
| `ehr_lookup` | `{member_id_hash, data_type}` | Labs (HbA1c, LDL) and vitals |
| `sdoh_lookup` | `member_id_hash` | Language, health literacy, PCP, pharmacy distance |
| `outreach_history` | `{member_id_hash, measure_id?}` | Prior contact attempts and outcomes |
| `measure_criteria` | `measure_id` | NCQA public spec — thresholds, exclusions, drug classes |

### PHI gate — IRON RULE

Every note, claim, or lab entering the vector store passes through a hard PHI gate:

```python
from clinical.privacy.deidentifier import validate_phi_scrubbed

# HARD RAISE — never log and continue (HIPAA requirement)
validate_phi_scrubbed(phi_scrubbed=chunk.phi_scrubbed, context="ingest:claim")
```

If `phi_scrubbed=False`, a `ValueError` is raised and ingestion aborts. The gate is enforced at `MemberBrain.add_chunk()` and all ingestion pipelines.

```bash
# PHI gate tests — must pass before any FAISS write path ships
PYTHONPATH=praktor pytest tests/test_clinical_privacy.py -v
# 23 passed
```

### Member brain (per-member FAISS shards)

Three-layer longitudinal retrieval per member:
1. **Member shard** — personal claims, labs, outreach history
2. **Cohort shard** — aggregate patterns for similar member profiles
3. **Clinical literature shard** — NCQA specs, clinical guidelines

LRU cache capped at 128 hot shards (configurable via `PRAKTOR_BRAIN_CACHE_SIZE`).

### Ingestion pipelines

```bash
# Claims (Rx + medical)
PYTHONPATH=praktor python -m clinical.ingestion.claims_ingest --csv claims.csv

# EHR labs and vitals
PYTHONPATH=praktor python -m clinical.ingestion.ehr_ingest --labs labs.csv --vitals vitals.csv

# Clinical notes (highest PHI risk — all text scrubbed before vectorization)
PYTHONPATH=praktor python -m clinical.ingestion.notes_ingest --csv notes.csv
```

CSV formats accept a `raw_member_id` column — the raw ID is hashed (SHA-256 + salt) on entry and never stored.

### Human-in-the-loop (HITL) review

Every agent recommendation is staged for care manager review before action:

```
Agent output → ClosureTracker (pending) → Care manager approves/modifies/rejects
                                         → Outcome tracked at 30/60/90 days
                                         → Feeds PromptOptimizer with closure ground truth
```

Run `streamlit run praktor/ui/clinical_app.py` for the review queue UI.

### Environment variables (clinical)

| Variable | Default | Description |
|----------|---------|-------------|
| `PRAKTOR_CLINICAL_DB` | `~/.praktor/clinical_data.db` | SQLite store for members, gaps, labs, claims |
| `PRAKTOR_MEMBER_SALT` | `praktor-dev` | HMAC salt for member ID hashing — **change in production** |
| `PRAKTOR_BRAIN_DIR` | `~/.praktor/member_brains` | Root directory for per-member FAISS shards |
| `PRAKTOR_BRAIN_CACHE_SIZE` | `128` | Max hot FAISS shards in LRU cache |

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
│   ├── LLM/                     # AsyncLLMAdapter (streaming + retry + cache)
│   │
│   └── clinical/                # Clinical AI — HEDIS gap closure
│       ├── schemas.py           # HEDISGap, ClinicalBrainChunk, hash_member_id
│       ├── agents/
│       │   └── hedis_gap_agent.py  # HEDISGapDefinition + parse_next_best_action
│       ├── tools/               # 7 clinical tools (gap_registry, drug_adherence, …)
│       ├── memory/
│       │   └── member_brain.py  # Per-member FAISS shards + LRU cache
│       ├── data/
│       │   └── clinical_store.py  # SQLite store (swap for Snowflake/FHIR in prod)
│       ├── privacy/
│       │   ├── deidentifier.py  # Presidio + regex PHI scrubber + PHI gate
│       │   └── audit.py         # Append-only audit log (HIPAA)
│       ├── ingestion/
│       │   ├── claims_ingest.py # Rx + medical claims → clinical store
│       │   ├── ehr_ingest.py    # Labs + vitals → clinical store
│       │   └── notes_ingest.py  # Clinical notes → member FAISS brain (PHI gate)
│       └── evaluation/
│           ├── hedis_judge.py   # LLM-as-judge for clinical reasoning quality
│           └── closure_tracker.py  # Outcome tracking → PromptOptimizer feedback
│
├── scripts/
│   └── init_vector_db.py        # Seed FAISS store from a PDF directory
├── tests/                       # pytest, all mocked (no live LLM needed)
├── docs/                        # mkdocs site + compliance guides
├── .github/workflows/           # CI/CD: test, benchmark, release
├── Dockerfile                   # Multi-stage build with uv
├── docker-compose.yml           # RabbitMQ + consumer stack
├── Makefile                     # Dev task runner (test, lint, docs, docker)
├── pyproject.toml               # Hatchling build + optional extras
└── .env.example
```

---

## Streamlit UI

A browser-based demo with three tabs:

| Tab | What it shows |
|-----|--------------|
| **Span Tracer** | Waterfall view of every agent run: latency bars, token counts, pass breakdown, error highlighting |
| **Skills** | Browse all registered agents, auto-generated input forms, run any agent and stream the response |
| **Documents** | Upload PDFs → embed with Ollama → build/update the FAISS vector store |

```bash
# Install Streamlit (included in requirements.txt)
pip install streamlit

# Launch
./scripts/run_ui.sh
# or
PYTHONPATH=praktor streamlit run praktor/ui/app.py
```

The UI reads from `~/.praktor/monitoring.db` — start the consumer and publish tasks to populate the Span Tracer.

---

## Tests

```bash
make test                           # runs pytest via uv
# or: uv run pytest tests/ -x -v
```

All tests mock the LLM and filesystem. No live Ollama, RabbitMQ, or FAISS needed.

### Dev commands (Makefile)

```bash
make help            # show all targets
make install-dev     # install with dev deps via uv
make test            # run full test suite
make lint            # black format check
make benchmark       # governance overhead benchmarks
make docs            # build mkdocs site
make serve-docs      # preview docs at localhost:8000
make docker          # build Docker image
make docker-up       # start RabbitMQ + consumer stack
make clean           # remove build artifacts
```

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
