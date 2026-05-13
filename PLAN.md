# Phase 3: Governance + Evaluation Wiring in Agent.run()

<!-- /autoplan restore point: /Users/wimverleyen/.gstack/projects/wimverleyen-praktor.ai/feat-governance-evaluators-otel-refactor-autoplan-restore-20260417-221751.md -->

## Problem

`Agent.run()` in `praktor/core/agent.py` is completely unaware of `AgentDefinition.governance_policy`. All the governance infrastructure exists (detectors, audit sinks, evaluation passes, RBAC) but nothing calls it. 13 tests are currently xfailed waiting for this wiring.

## What needs to happen in `Agent.run()`

### 1. Pre-execution detection (before LLM call)
- If `definition.governance_policy` is set and has `pre_execution` detectors:
  - For each string field in the payload, run all pre-execution `DetectorConfig`s
  - `BLOCK` → raise `GovernancePolicyViolation`, halt immediately (no LLM call)
  - `REDACT` → replace matched spans with `[REDACTED:<entity_type>]` in the payload before LLM
  - `FLAG` → mark `audit_entry.flagged = True`, continue
  - `ALLOW` → pass through, no audit entry for this detector

### 2. Post-execution detection (after LLM response collected)
- If `policy.post_execution` detectors set:
  - Run each detector on the full buffered response string
  - Same BLOCK/REDACT/FLAG/ALLOW logic
  - `BLOCK` → raise `GovernancePolicyViolation` (response never yielded to caller)

### 3. Evaluation passes (after post-execution detection)
- If `policy.evaluation_passes` set:
  - For each `EvaluationPass`:
    - `load_evaluator(eval_pass.evaluator_class)` → get `Evaluator` instance
    - `score = await evaluator.score(prompt, response)` where `prompt` is the rendered template
    - Append `{evaluator_class, metric_name, score, pass: score >= threshold}` to `audit_entry.evaluation_scores`
    - If `score < pass_threshold`:
      - `FLAG` → `entry.flagged = True`, continue
      - `BLOCK` → raise `EvaluationFailedError(metric_name)`

### 4. Audit entry construction + sink writes
- Build `AuditEntry` at start of run with `agent_type`, `session_id`, `model`, `prompt_hash`
- Set `response_hash` after response collected
- Set `governance_actions` list from detector results
- Set `evaluation_scores` list from evaluation passes
- Set `flagged` if any FLAG action fired
- Instantiate sinks from `policy.audit_sinks` → `LocalFileAuditSink`, `StdoutAuditSink`, `KafkaAuditSink`
- `await sink.write(entry)` for each sink after the run completes (or on error)

### 5. RBAC enforcement (pre-execution, before detectors)
- If `policy.rbac_required_roles` is non-empty:
  - Extract `caller_identity` from payload (field `caller_identity` or `session_id`)
  - Validate via `verify_token()` from `governance.rbac`
  - Missing secret + non-empty roles → `ConfigurationError` (fail-closed)

## Files in scope

| File | Change |
|------|--------|
| `praktor/core/agent.py` | Add governance hook: pre-execution, post-execution, eval passes, audit write |
| `praktor/governance/audit.py` | Already complete — no changes needed |
| `praktor/governance/detectors.py` | Already complete — no changes needed |
| `praktor/governance/evaluators/__init__.py` | Already complete — no changes needed |
| `praktor/governance/policy.py` | Already complete — no changes needed |
| `praktor/governance/rbac.py` | Already complete — check if wire-up needed |

## Tests to un-xfail

- `tests/test_governance.py::TestAgentGovernanceHooks` (class-level xfail → remove)
- `tests/test_evaluation.py::TestAgentEvaluationHooks` (class-level xfail → remove)

## Additional scope (from autoplan review)

### From Eng Review:
- **`finally` block for sink writes**: `AuditEntry` is built at the top of `run()` and written unconditionally in `finally`, even on exception. This ensures pre-execution BLOCK events are audited.
- **Memory saves redacted response**: after post-execution REDACT runs, `memory.save()` receives the redacted text.
- **Evaluator instance caching**: load evaluator instances once in `Agent.__init__` per `EvaluationPass`, not on every run.
- **New tests**: `test_audit_entry_written_on_pre_execution_block`, `test_memory_saves_redacted_response`, `test_governance_runs_in_react_path`

### From DX Review:
- **Structured `GovernancePolicyViolation`**: add `field_name`, `entity_type`, `detector_class` fields + helpful `__str__`. E.g. "Field 'text' blocked by RegexDetector: US_SSN detected."
- **`GovernancePolicy(dry_run=True)`**: runs detectors but only logs (stderr), never raises, never writes to sinks. Test ergonomics escape hatch.
- **README governance quickstart**: 10-line snippet showing STDOUT sink + REDACT policy. No new docs file.

## Non-goals (Phase 4)

- KafkaAuditSink production config (it must not crash; graceful write failure is acceptable)
- MinioAuditSink (Phase 4)
- ML-based detectors (spaCy, Presidio) — RegexDetector covers Phase 3
- Streaming governance (mid-stream REDACT) — post-stream detection is the contract

## Constraints

- Governance must NEVER crash the agent. All sink writes are wrapped in try/except.
- Audit entry is written even when the agent fails (error path).
- Pre-execution BLOCK raises BEFORE the LLM call (no tokens burned on blocked payloads).
- Post-execution BLOCK raises AFTER the response is fully buffered (already the case since all_chunks is collected before yielding in single-pass mode — VERIFY this).
- The existing `Agent.run()` single-pass and ReAct paths must both run governance.

<!-- AUTONOMOUS DECISION LOG -->
## Decision Audit Trail

| # | Phase | Decision | Classification | Principle | Rationale | Rejected |
|---|-------|----------|----------------|-----------|-----------|---------|
| 1 | CEO | Buffer full response before yielding when governance_policy is set | Mechanical | P5, P1 | Medical data context; post-execution BLOCK must fire before caller receives PHI | Yield-then-govern (security gap) |
| 2 | CEO | Governance is internal scaffolding completeness, not product launch scope | Mechanical | P3 | Tests define the contract; no external validation needed | Defer all Phase 3 |
| 3 | DX | Add `field_name`, `entity_type`, `detector_class` to `GovernancePolicyViolation` | Mechanical | P1, P5 | Actionable errors are table stakes for a framework API | Bare exception with no context |
| 4 | DX | Add `dry_run: bool = False` to `GovernancePolicy` | Mechanical | P1 | Test ergonomics; without this devs mock internals | No bypass |
| 5 | DX | Add governance quickstart snippet to README | Mechanical | P1 | TTHW unbounded without it; one code block | Separate docs file |
| 6 | Eng | Cache evaluator instances in Agent.__init__ per EvaluationPass | Mechanical | P3 | importlib.import_module on every run is unnecessary overhead | Per-run import |
| 7 | Eng | Use finally block for audit sink.write() to cover exception paths | Mechanical | P1 | Pre-execution BLOCK events are most important to audit; must not be skipped | Only write on success |

## Resolved Decisions

1. **Buffer-then-yield when `governance_policy` is set.** Non-policy agents: zero latency impact (yield immediately as before). Policy agents: accumulate full response, run post-execution detection + evaluation, then yield. This resolves Open Q1.
2. **Evaluation passes run on final answer in both single-pass and ReAct paths.** This resolves Open Q2.
3. **Sink factory** lives inside `agent.py` as a private helper `_make_audit_sinks(policy)`. No separate module needed at this scope.

## Open Questions (RESOLVED)

1. Post-execution in streaming: currently `agent.run()` yields chunks as they arrive. For post-execution detection, we need the full response. The current code DOES collect `all_chunks` but yields them WHILE collecting. This means post-execution detection happens AFTER yield. Is that acceptable, or do we need to buffer-then-yield?
2. Should `evaluation_passes` also run in the ReAct path (on the final answer chunk)?

---

## DX Review — Phase 3 Governance Surface

_Added by /plan-devex-review, 2026-04-18. All decisions confirmed by user._

### Developer Persona
```
TARGET DEVELOPER PERSONA
========================
Who:       ML engineer adding governance as a safety layer to their AI app
Context:   Integrating praktor.ai; governance is a "ship before prod" checkbox
Tolerance: ~20-30 minutes before abandoning
Expects:   Copy-paste snippet that works, structured errors, dry_run=True to test safely
```

### Developer Empathy Narrative
An ML engineer lands on the README. They scroll through ReAct, judge, monitoring,
clinical AI — 795 lines — before finding the governance quickstart at the very bottom.
They copy the snippet, run it, get `ModuleNotFoundError: No module named 'core'`.
They grep source, find the `PYTHONPATH=praktor` pattern. They add it. Now it runs.
They send a payload with a fake SSN — nothing visible happens (REDACT is silent).
They switch to BLOCK, get `GovernancePolicyViolation` with a good message (post-Phase 3).
They find `dry_run=True` in a text footnote. Total: ~15 minutes of confusion.
After fixes below: < 5 minutes.

### Competitive DX Benchmark
```
Tool              | TTHW      | Notable DX Choice
NeMo Guardrails   | ~8 min    | Declarative Colang rules, config file
Guardrails AI     | ~3 min    | Validator hub, @guard decorator (BENCHMARK)
Presidio          | ~5 min    | Named entity constants, clear enums
praktor.ai (now)  | ~15-20 min| Policy class, must read source
praktor.ai (plan) | ~3-5 min  | After fixes below
```
**Target tier: Champion (< 5 min).** Guardrails AI at ~3 min is the benchmark.

### Magical Moment
For a governance SDK: the developer sends a payload with fake PHI, the policy fires,
the error message tells them exactly what was caught (field + entity type + fix).
**Delivery vehicle: copy-paste demo command** (`python -m praktor demo-governance`).

### DX Fixes to Implement

_Implementation order matters — write docs/governance.md first as the spec (item 1), then implement against it._

| # | Fix | Why | Files |
|---|-----|-----|-------|
| 1 | **Write `docs/governance.md` as the implementation spec FIRST** — entity types, PolicyAction semantics, AuditSink options, PresidioDetector setup, custom detector protocol, `RegexEntities` vs `PresidioEntities` namespaces, dry_run guide, `block_pii()` API | All other items implement against this spec — write last = docs describe code rather than design | docs/governance.md |
| 2 | **Fix ALL internal package imports** — change `from governance.policy import`, `from core.agent_definition import`, etc. throughout `praktor/` to absolute `praktor.` prefix paths. Currently `from praktor.governance.policy import GovernancePolicy` raises `ModuleNotFoundError` — the package is broken as an installed package. **Full blast radius: 32 files** (governance/, core/, monitoring/, tools/, transport/, agents/, clinical/). **Also remove `sys.path.insert(0, .../praktor)` from all 20 test files** — dead code after fix | Without this, every item below is moot — pip install doesn't work | praktor/governance/*.py, praktor/core/*.py, praktor/monitoring/*.py, praktor/tools/*.py, praktor/transport/*.py, praktor/agents/*.py, praktor/clinical/**/*.py + tests/*.py (20 files) |
| 3 | Move governance quickstart to top third of README (after 30-second quickstart) | Buried at line 795 of 821 | README.md |
| 4 | Fix governance quickstart imports to use `from praktor.core.` and `from praktor.governance.` (follows from item 2) | Quickstart must work after `pip install -e .` | README.md |
| 5 | Add `block_pii(definition, entities, action='block', sink='stdout') -> AgentDefinition` convenience function in **new `praktor/governance/helpers.py`** — returns new AgentDefinition via `dataclasses.replace` (immutable). Re-export from `praktor/governance/__init__.py`. Accepts `action` as `str \| PolicyAction` and `sink` as `str \| AuditSinkType` (coerce in body). Avoids circular import risk (agent.py → governance.policy; helpers.py → core.agent_definition, not agent.py) | 4 concepts before first value → 1 call. Gets TTHW to ~3 min (Guardrails AI tier) | praktor/governance/helpers.py, praktor/governance/__init__.py |
| 6 | Add full working example with expected output (BLOCK + REDACT + dry_run cases) including `block_pii()` one-liner | ML engineer has no way to verify governance is working | README.md |
| 7 | Add `dry_run=True` code example with expected stderr output to quickstart | Most important escape hatch is a text footnote — should be front-and-center in code | README.md |
| 8 | Add `scripts/demo_governance.py` as **detector-only** demo (no Ollama needed) with `--model` flag for full agent path | Detector-only: `python -m praktor demo-governance` runs in < 2 min on any machine; add `--model llama3:8b` for full agent path | scripts/demo_governance.py, praktor/__main__.py |
| 9 | Add `RegexEntities` constants class (not `SupportedEntities`) — `RegexEntities.US_SSN` etc. | Named for the detector it belongs to; prevents confusion with PresidioDetector's different entity set | praktor/governance/detectors.py |
| 10 | `DetectorConfig.detector_class` accepts `str \| type[PIIDetector]` — in `__post_init__`, if input is a type, coerce to qualified string: `f"{cls.__module__}.{cls.__qualname__}"`. Field stays `str` internally. Both `DetectorConfig(detector_class=RegexDetector, ...)` and `DetectorConfig(detector_class='praktor.governance.detectors.RegexDetector', ...)` work | Dotted string import path is ceremonious; class-first is more ergonomic. Backwards compatible (string still works) | praktor/governance/policy.py |
| 11 | Add doc_url to `GovernancePolicyViolation.__str__`: `See: https://github.com/wimverleyen/praktor.ai#governance-quickstart` | Stripe-tier errors link to docs | praktor/governance/policy.py |
| 12 | Add `praktor/py.typed` marker (top-level, not governance-only) — PEP 561, covers entire package (core, governance, monitoring). Add to `[tool.hatch.build.targets.wheel]` includes in pyproject.toml | mypy/pyright users get no type checking without it; top-level marker covers all sub-packages | praktor/py.typed, pyproject.toml |
| 13 | Add governance metrics: `governance.violations_total{action,entity_type}`, `governance.dry_run_hits_total`, `governance.detections_total{entity_type}` — wire into monitoring/__init__.py (agent.py already imports monitoring) | No visibility into governance activity; avoids hard dep from monitoring→governance | praktor/monitoring/__init__.py, praktor/core/agent.py |
| 14 | Add `log.warning('Unknown entity: %s', name)` in `RegexDetector.detect()` for entities not in `_PATTERNS` | `entities=['SSN']` silently detects nothing — PHI leak with false confidence. Does NOT fire for PresidioDetector | praktor/governance/detectors.py |
| 15 | **Add `tests/test_governance_dx.py`** with 5 test groups: `block_pii()` returns new AgentDefinition; `RegexEntities` constants match `_PATTERNS` keys; `DetectorConfig(detector_class=RegexDetector)` coerces to qualified string; unknown entity logs WARNING (not PresidioDetector); `GovernancePolicyViolation.__str__` includes doc_url | New DX API surface has zero test coverage in existing suite | tests/test_governance_dx.py |

### Developer Journey Map
```
STAGE          | DEVELOPER DOES                    | FRICTION POINTS             | STATUS
---------------|-----------------------------------|-----------------------------|--------
1. Discover    | Lands on README, scans sections   | Quickstart buried at end    | fixed (#1)
2. Install     | pip install -e . / uv             | None                        | ok
3. Hello World | Copies governance snippet, runs   | Broken imports, no output   | fixed (#2,#3)
4. Real Usage  | Tests PHI detection               | Magic strings, dry_run note | fixed (#4,#5,#6)
5. Debug       | Hits GovernancePolicyViolation    | Error structured ✓, +url    | fixed (#8)
6. Upgrade     | Reads CHANGELOG                   | None — well documented ✓    | ok
```

### NOT in Scope
- Interactive playground (hosted) — no infrastructure to host, Phase 4
- Multi-language SDK (JS/Go) — Python-only is the right call for now
- ML-based entity detection defaults — RegexDetector is correct default

### What Already Exists
- `GovernancePolicyViolation` with `field_name`, `entity_type`, `detector_class`, `__str__` with fix hint ✓
- `GovernancePolicy(dry_run=True)` escape hatch ✓
- CHANGELOG with detailed governance entry ✓
- `praktor/governance/__init__.py` with clean `__all__` and docstring ✓
- 52 governance tests, all passing ✓

### DX Scorecard
```
+====================================================================+
|              DX PLAN REVIEW — SCORECARD                             |
+====================================================================+
| Dimension            | Before | After  |
|----------------------|--------|--------|
| Getting Started      |  2/10  |  9/10  |
| API/CLI/SDK          |  7/10  |  9/10  |
| Error Messages       |  8/10  |  9/10  |
| Documentation        |  5/10  |  9/10  |
| Upgrade Path         |  8/10  |  8/10  |
| Dev Environment      |  4/10  |  8/10  |
| Community            |  5/10  |  5/10  |
| DX Measurement       |  2/10  |  7/10  |
+--------------------------------------------------------------------+
| TTHW                 | ~15 min | ~3 min |
| Competitive Rank     | Red Flag → Champion                          |
| Magical Moment       | designed via demo-governance command         |
| Product Type         | Library/SDK                                  |
| Mode                 | DX EXPANSION                                 |
| Overall DX           |  5/10  |  8/10  |
+====================================================================+
| DX PRINCIPLE COVERAGE                                               |
| Zero Friction         | gap → covered (#1,#2,#6)                    |
| Learn by Doing        | gap → covered (#3,#6)                       |
| Fight Uncertainty     | gap → covered (#4,#8,#12)                   |
| Opinionated + Escapes | covered (dry_run ✓, fixed in #5)            |
| Code in Context       | gap → covered (#3,#9)                       |
| Magical Moments       | gap → covered (#6)                          |
+====================================================================+
```

### DX Implementation Checklist
```
[ ] docs/governance.md written first as the spec (item 1)
[ ] ALL internal imports fixed — pip install -e . actually works (item 2)
[ ] Time to hello world < 3 min (block_pii() one-liner + demo command)
[ ] Governance quickstart in top third of README
[ ] Imports use praktor. prefix — work after pip install -e .
[ ] block_pii() convenience function available
[ ] First run produces meaningful output (BLOCK error, dry_run stderr)
[ ] Magical moment: python -m praktor demo-governance runs detector-only in < 2 min (no Ollama needed)
[ ] GovernancePolicyViolation includes field + entity + detector + doc_url
[ ] RegexEntities constants class — no magic strings (namespaced, not SupportedEntities)
[ ] PresidioEntities documented separately in governance.md
[ ] DetectorConfig accepts class OR string (class stored in audit log as qualified name)
[ ] py.typed marker at praktor/ top-level (PEP 561, covers entire package)
[ ] Governance metrics in monitoring stack
[ ] Unknown entity name logs a warning in RegexDetector only
[ ] CHANGELOG entry exists ✓ (already done)
[ ] dry_run=True example with expected stderr output in quickstart
[ ] tests/test_governance_dx.py: block_pii, RegexEntities, class-or-string, warning, doc_url
[ ] sys.path.insert removed from all 20 test files (done as part of item 2)
[ ] block_pii() in helpers.py, re-exported from __init__.py (no circular import)
[ ] DetectorConfig accepts class OR string via __post_init__ coercion
```

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` | Scope & strategy | 0 | — | — |
| Codex Review | `/codex review` | Independent 2nd opinion | 0 | — | — |
| Eng Review | `/plan-eng-review` | Architecture & tests (required) | 3 | cleared | 6 issues resolved: import scope 32 files+20 tests, block_pii in helpers.py, DetectorConfig union type, py.typed top-level, test_governance_dx.py added, sys.path.insert removal scoped |
| Design Review | `/plan-design-review` | UI/UX gaps | 0 | — | — |
| DX Review | `/plan-devex-review` | Developer experience gaps | 1 | issues_found | score: 5/10 → 8/10, TTHW: 15min → 3min |

**OUTSIDE VOICE:** Claude subagent — 7 findings including broken package imports (pip install fails), demo Ollama dependency, SupportedEntities namespace conflict, convenience function gap, and docs sequencing. All resolved.

**UNRESOLVED:** 0 decisions pending

**VERDICT:** CLEARED — Eng Review complete. All 6 architecture/test issues resolved. Plan is implementation-ready. Start with item 1 (docs/governance.md spec), then item 2 (import fix across all 32 files + 20 test files).
