# Changelog

## [0.2.0.0] - 2026-04-17

### Added
- **BaseJudge ABC** (`praktor/clinical/evaluation/base_judge.py`) — shared `evaluate()`, `compare()`, `_parse_json()`, and `_init_adapters()` extracted from both clinical judge subclasses. Subclasses now implement two abstract methods (`_parse_score`, `_neutral_score`) and inherit all plumbing. Cuts ~150 lines of duplication. Empty `_eval_prompt` or `_compare_prompt` raises `ValueError` at instantiation (no silent misconfiguration).
- **DiabetesJudgeScore** (`praktor/clinical/schemas.py`) — 10-criterion dataclass with `base_overall`, `diabetes_overall`, `overall`, and `summary()` properties. Co-located with `ClinicalJudgeScore` in the shared schema module.
- **ClosureTracker.get_review_queue()** (`praktor/clinical/evaluation/closure_tracker.py`) — returns pending recommendations ordered by priority score, used by the clinical review queue UI.
- **Color token layer** (`praktor/ui/theme.py`) — semantic color constants for the clinical UI (semantic/warning/error/info).
- **TODOS.md** — tracked backlog for deferred items: structured output panel, error states, DESIGN.md, outcome= bias validation, on-demand eval format contract, judge_type aggregate query fix.

### Changed
- `HEDISJudge` and `DiabetesHEDISJudge` now inherit `BaseJudge`. Duplicate `evaluate()`, `compare()`, `_parse_json()`, and `_init_adapters()` removed from both.
- `collector.record_judge()` accepts both legacy `JudgeScore` (`.criteria` dict) and new clinical score dataclasses (direct attrs). New `judge_type` parameter. All 10 criteria fields populated for diabetes evaluations.
- `_parse_json` uses `JSONDecoder.raw_decode` instead of a greedy regex — correctly handles LLM responses that echo prompt variables before the JSON object.
- `compare()` normalizes `winner` to `{"A", "B"}` — LLM responses of `"tie"`, `"C"`, or null fall back to `"A"`.
- `PRAKTOR_MEMBER_SALT` missing-secret warning moved from module import time to first call of `hash_member_id()`, avoiding `warnings.warn` CI breakage with `-W error::UserWarning`.

### Fixed
- `_score_field` crash when `criteria` attribute exists but is `None` — now guards with `isinstance(score_obj.criteria, dict)`.
- `_overall_score` crash when legacy `JudgeScore.score` is `None` — now uses `score or 0.0`.
- `ClosureTracker` SQLite connection context manager pattern aligned with `MonitoringStore`.

### Tests
- 38 new tests: `test_base_judge.py` (20), `test_hedis_judge.py` (8), `test_diabetes_judge.py` (12), `test_monitoring.py` (6 new for `_score_field`/`_overall_score`/`record_judge`). 232 tests pass, 3 skipped.

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
