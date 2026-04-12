# praktor.ai

General-purpose agentic framework built on LangChain, RabbitMQ, and local or hosted LLMs. Comes with built-in agents for job application workflows — resume tailoring, cover letter generation, interview prep, and professional communications — but the framework is generic. Any agent is one file.

→ [Architecture deep-dive](ARCHITECTURE.md) · [Contributing guide](CONTRIBUTING.md)

---

## How it works

```
Producer (transport/producer.py)
  → RabbitMQ queue "agentic"
  → Async consumer (transport/consumer.py)
  → Router (core/router.py)  ← dynamic dispatch by agent_type
  → Agent.run()              ← async generator, yields token chunks
  → LLM (streaming)
  → Memory + File output
```

The consumer runs `PRAKTOR_CONCURRENCY` (default: 4) agents concurrently. Each agent streams tokens as they arrive — no waiting for the full response.

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
| `ANTHROPIC_API_KEY` | — | Required for `claude-*` models |
| `OPENAI_API_KEY` | — | Required for `gpt-*` models |
| `MD` | — | Directory for markdown output files |
| `PDF` | — | Directory containing input PDF files |
| `VECTOR_DB` | — | Path for the FAISS vector store |

**3. Start RabbitMQ**

```bash
docker run -d --name rabbitmq -p 5672:5672 rabbitmq:3
```

**4. Seed the vector store** (only needed for `job_interview` agent)

```bash
python scripts/init_vector_db.py --pdf-dir /path/to/pdfs --db-path /path/to/vector_db
```

---

## Running

**Start the async consumer:**

```bash
python -m praktor receive
```

**Publish a task:**

```bash
# From JSON string
python -m praktor publish --agent thank_you --data '{"adjective":"professional","position":"VP Data Science","content":"Great conversation about GenAI strategy"}'

# From stdin
echo '{"agent_type":"search","search":"concept drift","content":"production ML systems"}' | python -m praktor publish

# Legacy producer methods (still work)
python -m praktor agent thankyou
python -m praktor agent search
python -m praktor agent message
```

**List registered agents and their required fields:**

```bash
python -m praktor list
```

---

## Built-in agents

| Agent type | What it does | Memory | Passes |
|------------|-------------|--------|--------|
| `job_application` | Resume tailored to a job description with impact metrics | None | 1 |
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
    llm_model="qwen2.5",           # or "claude-sonnet-4-6", "gpt-3.5-turbo"
    memory_policy=MemoryPolicy.SHORT_TERM,
    output_sink=OutputSink.BOTH,
    output_file="my_agent_output",
)
```

Then register it in `praktor/agents/__init__.py`:

```python
from agents.my_agent import MyAgentDefinition
_router.register(MyAgentDefinition)
```

That's it. The consumer picks it up automatically on next start.

---

## Supported LLMs

| Provider | Model string | Notes |
|----------|-------------|-------|
| Ollama (default) | `qwen2.5`, `llama3.1`, any Ollama model | Runs locally, no API key |
| Anthropic Claude | any `claude-*` string | Requires `ANTHROPIC_API_KEY` |
| OpenAI | `gpt-3.5-turbo-instruct`, `gpt-3.5-turbo` | Requires `OPENAI_API_KEY` |

Switch model per-agent via `AgentDefinition.llm_model`, or globally via `PRAKTOR_MODEL`.

```python
from LLM.llm_factory import LLMFactory

llm = LLMFactory().create_llm("claude-sonnet-4-6")
```

---

## Project structure

```
praktor.ai/
├── praktor/
│   ├── __main__.py              # CLI: receive | publish | list | agent
│   ├── settings.py              # Config, rotating logs, env vars
│   ├── utils.py                 # read_markdown / save_markdown
│   │
│   ├── core/                    # Framework abstractions
│   │   ├── agent_definition.py  # AgentDefinition dataclass
│   │   ├── agent.py             # Agent: async generator run()
│   │   ├── router.py            # Dynamic dispatch + global singleton
│   │   ├── memory.py            # Memory protocol + NullMemory
│   │   ├── tool.py              # Tool protocol + ToolRegistry
│   │   └── observability.py     # Span: latency + token + cache logging
│   │
│   ├── agents/                  # Built-in agent definitions (one file each)
│   │   ├── __init__.py          # Auto-registers all agents
│   │   ├── job_application.py
│   │   ├── cover_letter.py      # 3-pass improvement
│   │   ├── keywords_extraction.py
│   │   ├── job_interview.py     # Uses FAISS long-term memory
│   │   ├── thank_you.py
│   │   ├── search.py
│   │   └── message.py
│   │
│   ├── memory/
│   │   ├── buffer.py            # InMemoryBuffer (short-term, session-keyed)
│   │   └── vector.py            # FAISSMemory (long-term semantic retrieval)
│   │
│   ├── tools/
│   │   ├── web_search.py        # DuckDuckGo (no API key needed)
│   │   └── file_io.py           # ReadFileTool + WriteFileTool
│   │
│   ├── transport/
│   │   ├── consumer.py          # aio-pika async consumer
│   │   ├── producer.py          # publish() + publish_many()
│   │   └── schemas.py           # Dynamic schema registry
│   │
│   └── LLM/                     # LangChain wrappers (kept for legacy compat)
│       ├── llm_factory.py       # Creates LLM instances by model string
│       ├── llm_interface.py     # AsyncLLMAdapter (streaming + retry + cache)
│       └── prompt.py            # Legacy prompt templates
│
├── scripts/
│   └── init_vector_db.py        # Seed FAISS store from a PDF directory
├── tests/                       # pytest, all mocked (no live LLM needed)
├── .env.example
└── requirements.txt
```

---

## Tests

```bash
pytest tests/
```

All tests mock the LLM and filesystem. No live Ollama, RabbitMQ, or FAISS needed.

---

## Observability

Every agent run emits a structured log line to `praktor.ai.log`:

```
SPAN {"agent_type": "cover_letter", "session_id": "a3f1b2c4", "model": "qwen2.5",
      "duration_ms": 4821.3, "token_count": 312, "passes": 3, "cached": false}
```

The log rotates at 10 MB (5 backups). To correlate a request end-to-end:

```python
from settings import create_log, new_request_id

request_id = new_request_id()
log = create_log(request_id)
```
