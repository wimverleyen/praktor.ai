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

```bash
# Core (local inference via Ollama)
pip install praktor

# With full PHI detection (names, addresses, medical record numbers)
pip install praktor[presidio]

# With enterprise audit sinks
pip install praktor[kafka]   # Kafka audit sink
pip install praktor[minio]   # MinIO/S3 audit sink

# Development
pip install praktor[dev]
```

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
