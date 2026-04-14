# Changelog

## v0.3.0 — Phase 2: Governance Polish + Enterprise Readiness (in progress)

### New

- **EvaluationPass** — post-execution scoring protocol with `RegexToxicityEvaluator` and `EmbeddingRelevanceEvaluator`
- **KafkaAuditSink** — Avro messages to configurable topic (`pip install praktor[kafka]`)
- **MinIOAuditSink** — JSON objects partitioned by date (`pip install praktor[minio]`)
- **CI/CD** — GitHub Actions: test on PR/push, benchmark on merge, PyPI release on tag
- **HIPAA deployment guide** — `docs/compliance/hipaa.md`
- **mkdocs API reference** — auto-generated from docstrings

### Fixed

- `PolicyAction.REDACT` now actually replaces matched spans with `[REDACTED:<entity_type>]` in payload fields before LLM execution
- Pre-execution governance runs per-field (not on a detached scratch variable)
- `GovernancePolicyViolation` exception handler now sets `flagged` and `otel_trace_id` before audit write
- `AsyncLLMAdapter.render()` docstring corrected (was claiming usage by `Agent.run()`)

---

## v0.2.0 — Phase 1: Governance Foundation

### New

- **GovernancePolicy** on `AgentDefinition` — declarative compliance config (opt-in, backwards compatible)
- **PII/PHI detection** — `RegexDetector` (zero-dep, 6 patterns) + `PresidioDetector` (optional ML-based)
- **PolicyAction** enum — ALLOW, REDACT, FLAG, BLOCK with pre/post execution hooks
- **AuditEntry** — hash-chained JSONL entries with SHA-256 prompt/response digests (PHI never stored)
- **LocalFileAuditSink** — append-only with `filelock` concurrent write safety
- **StdoutAuditSink** — for development/testing
- **RBAC** — HMAC-SHA256 tokens, 5-min TTL, in-process replay protection, fail-closed
- **OpenTelemetry Span wrapper** — `otel_trace_id` propagated to `AuditEntry`
- **Transport protocol** — `DirectTransport`, `RabbitMQTransport`, `HTTPTransport`
- **Benchmark suite** — framework overhead measurement (baseline, no-governance, regex-detector)
- **pyproject.toml** — hatchling build, `[presidio]`, `[otel]`, `[dev]` extras
- **48 tests** — full governance coverage, all mocked

---

## v2.0.0 — General Agentic Framework

### What changed

praktor.ai was rebuilt from a job-application-specific script collection into a general-purpose agentic framework. The five new core abstractions (`AgentDefinition`, `Agent`, `Router`, `Memory`, `Tool`) compose in a strict dependency order. Adding a new agent now requires one file and one registration line — no framework changes.

### New

- **`AgentDefinition` dataclass** (`core/agent_definition.py`) — declarative unit for all agent config: prompt template, input schema, LLM model, temperature, tools, memory policy, output sink, improvement passes
- **`Agent` async generator** (`core/agent.py`) — executes an `AgentDefinition`; streams token chunks via `AsyncLLMAdapter.astream`; supports multi-pass improvement chains; emits `Span` on completion
- **`Router`** (`core/router.py`) — dynamic dispatch by `agent_type`; validates payloads against per-agent Pydantic schemas; global singleton via `get_global_router()`
- **`AsyncLLMAdapter`** (`LLM/llm_interface.py`) — streaming (`astream`) + non-streaming (`ainvoke`); retry with exponential backoff (3 attempts); `diskcache` prompt-response cache keyed on `sha256(model + prompt)` when `temperature=0.0`
- **`LLMFactory`** (`LLM/llm_factory.py`) — routes `claude-*` → Anthropic, `gpt-*` → OpenAI, anything else → Ollama
- **`InMemoryBuffer`** (`memory/buffer.py`) — short-term, per-session circular deque (`max_turns=10`)
- **`FAISSMemory`** (`memory/vector.py`) — long-term semantic retrieval; gracefully degrades if the store doesn't exist
- **`Span`** (`core/observability.py`) — structured JSON log: `duration_ms`, `token_count`, `passes`, `cached`
- **`WebSearchTool`** (`tools/web_search.py`) — DuckDuckGo search, no API key required
- **`ReadFileTool` / `WriteFileTool`** (`tools/file_io.py`) — filesystem access for agents
- **Async consumer** (`transport/consumer.py`) — `aio-pika` replaces blocking `pika`; `prefetch_count=PRAKTOR_CONCURRENCY` (default 4) for concurrent in-flight messages
- **CLI** (`__main__.py`) — `python -m praktor receive | publish | list | agent`
- **`ImprovementPass`** — multi-pass LLM chains; `cover_letter` uses 3 sequential passes
- **`scripts/init_vector_db.py`** — seed the FAISS store from a PDF directory
- **Tests** — `test_agent_definition`, `test_router`, `test_memory`, `test_async_adapter`; all mocked, no live services

### Changed

- `settings.py` — added `PRAKTOR_MODEL`, `RABBITMQ_URL`, `PRAKTOR_CONCURRENCY`, `CACHE_DIR`, `CACHE_TTL`; rotating log handler (10 MB × 5 backups)
- `requirements.txt` — pinned all deps; added `aio-pika`, `diskcache`, `duckduckgo-search`, `langchain-anthropic`, `langchain-openai`

### Preserved (backwards compatible)

- Legacy `LLMAdapter` in `LLM/llm_interface.py` — still works
- `LLM/prompt.py` legacy prompt templates
- `python -m praktor agent <method>` CLI path

---

## v1.0.0 — Initial release

Job application workflow scripts: resume tailoring, cover letter, interview prep, thank you email, professional message, keyword extraction.
