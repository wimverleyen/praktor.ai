# praktor.ai

Agent framework for job application workflows. Uses LangChain, RabbitMQ, and local or hosted LLMs to automate resume tailoring, cover letter generation, interview prep, and professional communications.

---

## How it works

```
Agent (producer)
  → RabbitMQ queue "agentic"
  → Consumer (receive.py)
  → Agent method (LLM + optional RAG)
  → Markdown output
```

Each producer method publishes a typed message with an `agent_type` field. The consumer validates it with Pydantic and routes it to the right handler — no hardcoded dispatch.

---

## Setup

**1. Install dependencies**

```bash
pip install -r requirements.txt
```

**2. Configure environment**

Copy `.env.example` to `.env` and fill in your values:

```bash
cp .env.example .env
```

| Variable | Description |
|----------|-------------|
| `ANTHROPIC_API_KEY` | Anthropic Claude API key |
| `OPENAI_API_KEY` | OpenAI API key (optional) |
| `MD` | Directory for markdown output files |
| `PDF` | Directory containing input PDF files |
| `VECTOR_DB` | Path for the FAISS vector store |
| `slack_app` | Slack app token (optional) |
| `slack_bot` | Slack bot token (optional) |

**3. Start RabbitMQ**

```bash
docker run -d --name rabbitmq -p 5672:5672 rabbitmq:3
```

**4. Seed the vector store** (required for RAG-based agents)

```bash
python scripts/init_vector_db.py --pdf-dir /path/to/pdfs --db-path /path/to/vector_db
```

Or use the env vars already set in `.env`:

```bash
python scripts/init_vector_db.py
```

---

## Running

**Start the consumer** (listens for incoming agent tasks):

```bash
python -m praktor receive
```

**Fire a producer** (publish a task to the queue):

```bash
python -m praktor agent process       # job application / resume tailoring
python -m praktor agent coverletter   # cover letter generation
python -m praktor agent thankyou      # thank you email
python -m praktor agent search        # research / search
python -m praktor agent message       # professional message
```

The consumer must be running before you fire a producer.

---

## Agent types

| Agent type | Producer method | What it does |
|------------|----------------|--------------|
| `job_application` | `agent process` | Writes a resume tailored to a job description |
| `cover_letter` | `agent coverletter` | Generates and iteratively improves a cover letter (3 passes) |
| `keywords_extraction` | — | Extracts keywords from resume and JD, compares gaps |
| `job_interview` | — | RAG-based interview prep using your document store |
| `thank_you` | `agent thankyou` | Writes a post-interview thank you email |
| `search` | `agent search` | Researches a topic with optional RAG context |
| `message` | `agent message` | Writes a professional message with a specified tone |

---

## Supported LLMs

Configure via the `MODEL` variable in `praktor/settings.py` or pass the model name to `LLMFactory.create_llm()`.

| Provider | Model string | Notes |
|----------|-------------|-------|
| Ollama (default) | `qwen2.5`, `llama3.1` | Runs locally, no API key needed |
| OpenAI | `gpt-3.5-turbo-instruct`, `gpt-3.5-turbo` | Requires `OPENAI_API_KEY` |
| Anthropic Claude | `claude-sonnet-4-6`, `claude-opus-4-6`, any `claude-*` | Requires `ANTHROPIC_API_KEY` |

Example — switch to Claude in an agent method:

```python
from LLM.llm_factory import LLMFactory

factory = LLMFactory()
llm = factory.create_llm('claude-sonnet-4-6')
```

---

## Project structure

```
praktor.ai/
├── praktor/
│   ├── __main__.py          # CLI entry point (python -m praktor)
│   ├── agent.py             # Producer: publishes tasks to RabbitMQ
│   ├── agent_method.py      # Handlers: one function per agent type
│   ├── receive.py           # Consumer: routes messages to handlers
│   ├── retrieve_generate.py # RAG chains (RAGTY, RAGSP)
│   ├── schemas.py           # Pydantic message schemas + parse_message()
│   ├── settings.py          # Config, logging (rotating), env vars
│   ├── utils.py             # read_markdown / save_markdown
│   └── LLM/
│       ├── llm_factory.py   # Creates LLM instances by name
│       ├── llm_interface.py # LLMAdapter: wraps prompt + LLM into a chain
│       └── prompt.py        # All prompt templates (25+)
├── scripts/
│   └── init_vector_db.py    # Seed FAISS store from a PDF directory
├── tests/
│   ├── test_schemas.py      # Schema validation tests
│   ├── test_llm_factory.py  # LLM factory routing tests
│   └── test_agent_methods.py# Agent method integration tests (mocked LLM)
├── .env.example             # Environment variable template
└── requirements.txt         # Python dependencies
```

---

## Tests

```bash
pytest tests/
```

Tests mock the LLM and filesystem — no live Ollama or RabbitMQ needed.

---

## Logging

All activity is logged to `praktor.ai.log` with automatic rotation (10 MB × 5 backups). Pass a `request_id` to `create_log()` to correlate a single request across producer, queue, and handler:

```python
from settings import create_log, new_request_id

request_id = new_request_id()
log = create_log(request_id)
```
