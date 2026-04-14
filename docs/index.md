# praktor.ai

Local-first agentic framework with built-in governance for regulated industries.

---

## 30-Second Quickstart

No RabbitMQ, no Docker, no cloud API keys. Just Python and a local LLM.

```python
import asyncio
from pydantic import BaseModel
from praktor.core.agent_definition import AgentDefinition, MemoryPolicy, OutputSink
from praktor.core.agent import Agent
from praktor.transport.direct import DirectTransport

# 1. Define your agent (one dataclass)
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

# 2. Run it (no message broker needed)
async def main():
    agent = Agent(definition)
    payload = {"agent_type": "question", "question": "What is HIPAA?"}
    async for chunk in agent.run(payload):
        print(chunk, end="", flush=True)

asyncio.run(main())
```

That's it. One file, one agent, local inference.

---

## Why praktor

**For regulated industries.** Healthcare, defense, finance. Organizations that cannot send data to cloud APIs.

- **Local inference.** Ollama models run on your hardware. PHI never leaves the perimeter.
- **Built-in governance.** PII/PHI detection, REDACT/BLOCK actions, RBAC with HMAC tokens.
- **Tamper-evident audit.** Hash-chained JSONL logs. SHA-256 digests only, never raw PHI.
- **Zero-to-governed in minutes.** Add a `GovernancePolicy` to any `AgentDefinition`.

---

## Installation

### With uv (recommended)

```bash
# 1. Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. Clone and install
git clone https://github.com/wimverleyen/praktor.ai.git
cd praktor.ai
uv venv && uv pip install -e .
```

### With pip

```bash
git clone https://github.com/wimverleyen/praktor.ai.git
cd praktor.ai
python -m venv .venv && source .venv/bin/activate
pip install -e .
```

### With Docker

```bash
git clone https://github.com/wimverleyen/praktor.ai.git
cd praktor.ai
docker build -t praktor .
docker compose up
```

### Optional extras

| Extra | What it adds |
|-------|-------------|
| `presidio` | ML-based PHI detection (names, addresses, medical record numbers) |
| `kafka` | `KafkaAuditSink` for high-throughput audit logs |
| `minio` | `MinIOAuditSink` for S3-compatible object storage |
| `otel` | OpenTelemetry trace export |
| `docs` | mkdocs + mkdocs-material for building this site |
| `dev` | pytest, pytest-asyncio, black |

Install one or many:

```bash
uv pip install -e ".[presidio]"
uv pip install -e ".[kafka,minio,otel]"
uv pip install -e ".[dev,presidio,kafka,minio,otel,docs]"   # everything
```

### Prerequisites

praktor runs local LLMs via [Ollama](https://ollama.ai):

```bash
brew install ollama                              # macOS
curl -fsSL https://ollama.ai/install.sh | sh    # Linux
ollama pull qwen2.5
ollama serve                                    # if not already running
```

Set `PRAKTOR_MODEL` to switch models (`llama3.1`, `mistral`, `phi3`, anything Ollama supports).

---

## Adding Governance

Any agent becomes governed with one field:

```python
from praktor.governance import GovernancePolicy, DetectorConfig, PolicyAction

definition = AgentDefinition(
    name="medical_qa",
    prompt_template="Answer: {question}",
    input_schema=MedicalInput,
    governance_policy=GovernancePolicy(
        pre_execution=[
            DetectorConfig(
                detector_class="governance.detectors.RegexDetector",
                entities=["US_SSN", "PHONE_NUMBER", "EMAIL_ADDRESS"],
                action=PolicyAction.REDACT,
            ),
        ],
        post_execution=[
            DetectorConfig(
                detector_class="governance.detectors.RegexDetector",
                entities=["US_SSN"],
                action=PolicyAction.BLOCK,
            ),
        ],
    ),
)
```

PHI is redacted before the LLM sees it. If the LLM generates PHI in its response, the agent halts.

---

## Documentation

- [Architecture](architecture.md) ... design rationale, dependency order, governance layer
- [API Reference](api/agent.md) ... auto-generated from docstrings
- [HIPAA Deployment Guide](compliance/hipaa.md) ... air-gapped setup, audit retention, Security Rule mapping
- [Contributing](contributing.md) ... adding agents, tools, memory backends
- [Changelog](changelog.md) ... release history
