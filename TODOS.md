# TODOs

## [UI] Structured agent output panel (Predict tab)

**What:** Replace the raw `st.code(clean, language="text")` agent output view with a
structured panel: Reasoning steps (collapsible), Final recommendation (highlighted block),
Action type + rationale (prominent). Raw full trace behind a "Show full output" expander.

**Why:** The Predict tab is the demo's "AI thinking" moment — the most emotionally resonant
step in the 5-tab workflow. A raw terminal dump undersells the reasoning the agent does.

**Pros:** Makes the demo audience feel the AI's reasoning depth. Surfaces the most
important output (action + rationale) without scrolling.

**Cons:** Requires parsing the agent stdout format, which currently varies between
`demo_diabetes_agent.py` and `demo_hedis_agent.py`. Need to normalize or add structured
JSON output from the scripts.

**Context:** Identified in `/plan-design-review` Pass 3 (User Journey, 2026-04-17).

**Depends on:** Agent scripts (`scripts/demo_diabetes_agent.py`,
`scripts/demo_hedis_agent.py`) need to emit structured output or a parseable format.

---

## [UI] User-friendly error states ✅

**Completed:** v0.4.2.0 (2026-04-19)

**What:** All `_load_*()` helper functions now use `_safe_load()` — exceptions propagate
as return values (not `[]`), and the UI renders a friendly amber/red banner with the
raw error in an expander.

**Context:** Identified in `/plan-design-review` Pass 2 (Interaction States, 2026-04-17).
Implemented in PR11b.

---

## [Design] Create DESIGN.md via /design-consultation

**What:** Run `/design-consultation` to define a complete design system for praktor.ai
Clinical: typography (font stack, scale), spacing, color semantics, component vocabulary,
interaction patterns.

**Why:** `praktor/ui/theme.py` now provides a color token layer, but there's no higher-level
design spec. Every new screen currently invents its own hierarchy and spacing.

**Pros:** All future UI work has a reference. Design decisions become explicit and
reviewable, not implicit in the code.

**Cons:** ~30 min session. Requires running `/design-consultation` as a dedicated step.

**Context:** Identified in `/plan-design-review` Pass 5 (Design System, 2026-04-17).
`praktor/ui/theme.py` created as a first step — DESIGN.md is the next level.

---

## [Eval] Validate outcome= bias in judge prompts

**What:** A/B test whether `ACTUAL OUTCOME (if known): pending` in the HEDIS and
diabetes judge prompts biases scores downward for on-demand evaluations vs.
outcome-known stored evaluations.

**Why:** On-demand evals always pass `outcome="pending"`. If the LLM interprets
"pending" as uncertainty about correctness, it will hedge on `gap_identification_accuracy`
and `action_appropriateness`, making on-demand scores systematically lower than
stored scores. The two cohorts would be incomparable on those dimensions.

**Pros:** Fixing this makes the historical Evaluate tab directly comparable to
on-demand scores. Critical for any aggregate reporting.

**Cons:** Prompt change without validation could degrade quality if `outcome=closed`
genuinely helps calibration for retrospective evals.

**Context:** Identified by outside voice review (2026-04-17) in `/plan-eng-review`.
Hypothesis only — validate by running 10 same-rec evals with outcome=pending vs.
outcome=closed and comparing the distributions on `gap_identification_accuracy`.

**Depends on:** Enough stored evals with resolved outcomes to form a comparison cohort.

---

## [UI] Improve on-demand eval format contract ✅

**Completed:** v0.4.2.0 (2026-04-19)

**What:** `st.text_area` placeholder in the on-demand eval panel now shows the full
five-field `NextBestAction` format (ACTION_TYPE, RATIONALE, DRAFT_MESSAGE,
CLOSURE_PROBABILITY, LANGUAGE).

**Context:** Identified by outside voice review (2026-04-17) in `/plan-eng-review`.
Implemented in PR11b.

---

## [Monitoring] Add judge_type filter to aggregate queries ✅

**Completed:** v0.4.2.0 (2026-04-19)

**What:** `store.aggregate()` now accepts `judge_type: str | None = None`. `CREATE INDEX
IF NOT EXISTS idx_judge_type ON judge_evals(judge_type)` added. HEDIS and diabetes
scores no longer mix in aggregate histograms.

**Context:** Identified by adversarial review (2026-04-17) during `/ship`.
Implemented in PR11a.

---

## [AIGov] Signing key registration for production Attestations

**What:** Before any Attestation leaves a dev environment, the enterprise needs a registered public key for verification. Define how the public key is registered with ERM, how key rotation works, and whether AWS KMS / HSM is available.

**Why:** An attestation signed with an unregistered ephemeral key is unverifiable as a risk assessment artifact. The CISO will ask "how do I verify this signature?" on first demo.

**Pros:** Attestations become genuine compliance artifacts, not just signed JSON.

**Cons:** Requires infrastructure conversation with CISO / ERM before production deployment.

**Context:** Identified in `/plan-eng-review` (2026-04-18). Design Open Question 4. Current plan adds a WARNING log when using the dev ephemeral key. Prod path: `AIGOV_SIGNING_KEY_PATH` env var (PEM) or `AIGOV_KMS_KEY_ARN` for KMS-backed signing.

**Depends on / blocked by:** Conversation with CISO / ERM about available KMS infrastructure. Must resolve before PR5 (Attestation) is deployed to production.

---

## [AIGov] Batch DuckDB writes for obligation events

**What:** Add `write_events(events: list[ObligationEvent])` batch path to `praktor/aigov/ledger/store.py` — wraps all inserts in one transaction, acquires filelock once per run.

**Why:** Current plan acquires filelock once per event. For 11 obligations per run, that's 11× filelock acquisitions. Batch write = ~5ms vs ~55ms for 11 individual writes.

**Pros:** Significant latency reduction with no observable behavior change.

**Cons:** Slightly more complex `store.py` (two write methods).

**Context:** Identified in `/plan-eng-review` (2026-04-18). v0.5.0 ships `write_event()` per-event via `asyncio.to_thread()`. Batch path is a v0.5.1 optimization.

**Depends on / blocked by:** PR2 (ledger/store.py) must land first.

---

## [AIGov] Per-agent SLO overrides for low-frequency agents

**What:** Add `govrun_slo_hours: int = 1` field to `AgentDefinition`. Overnight batch agents can set `govrun_slo_hours=24` so their G-RUN evidence is not stale after 1 hour.

**Why:** The AIGov spec sets G-RUN SLO at 1 hour globally. Clinical agents running once a day will show permanent AMBER, making the scoreboard useless for batch deployment patterns.

**Pros:** Enterprise scoreboard is meaningful for all agent cadences.

**Cons:** Deviates from AIGov spec SLO defaults. Requires documenting override semantics.

**Context:** Identified in `/plan-eng-review` (2026-04-18). High priority before first ERM demo with batch agents.

**Depends on / blocked by:** PR4 (AgentDefinition changes) + PR2 (scoreboard SLO query).

---

## [Eval] O(n) JSONL dedup scan in promote_to_golden()

**What:** `promote_to_golden()` in `golden_dataset.py` does a full linear scan of `~/.praktor/golden_custom.jsonl` on every call to check for duplicate `sample_id`s.

**Why:** At <100 promotions, this is <1ms. At 1000+ HITL approvals in a busy production system, the per-promotion file scan accumulates.

**Pros:** Fix makes promotion O(1) per call (load sample_id set once into memory, or migrate to SQLite-backed dedup).

**Cons:** Requires a schema decision: in-memory set (lost on restart) vs SQLite table (durable, heavier).

**Context:** Identified in `/plan-eng-review` (2026-04-19). Not a problem at current scale. Revisit when HITL approval queue regularly exceeds 500 records.

**Depends on:** `promote_to_golden()` implementation in PR10.

---

## [Eval] Defensive ordering in _build_few_shot_block() for promoted samples

**What:** `_build_few_shot_block()` selects `samples[:n]` (first 3). Since promoted samples are appended after built-in samples in `load_golden_samples()`, this works correctly now (10 built-in per type guarantees first 3 are built-in). If future work adds < 3 built-in samples for a new agent type, promoted samples with `clinical_scenario="production:{session_id}"` could appear in the few-shot block.

**Why:** Prevents degraded calibration examples when built-in sample counts are low for new agent types.

**Fix:** Sort samples in `_build_few_shot_block()` input: built-in first (`measurement_year > 0`), promoted last (`measurement_year == 0`).

**Context:** Identified in `/plan-eng-review` (2026-04-19). Currently safe with 10 built-in per type.

**Depends on:** PR10 (golden dataset extension).

---

## [Design] Formalize design system via /design-consultation

**What:** Run `/design-consultation` to produce a DESIGN.md covering: typography scale (Inter as body, JetBrains Mono as code), spacing rhythm (4/8/12/16/24/32px), component vocabulary (expander, metric, badge, pill, criteria cell, promote panel), color semantics (status, promote, warn, urgency — now in theme.py but no spec for usage rules).

**Why:** PR11b designed 5 new component types (calibration badge, promote panel, AIGov scoreboard, criteria grid, obligation pills) from first principles using the finalized.html mockup. Without a DESIGN.md, the next engineer designing a new component has no reference and will invent a 6th visual language.

**Pros:** All future UI PRs start from a defined system instead of first principles. Design review passes become faster (calibrate against DESIGN.md instead of universal principles). theme.py tokens become meaningful in context.

**Cons:** ~30 min session with `/design-consultation`. The finalized.html mockup already exists and encodes most of the decisions — DESIGN.md is a formalization step.

**Context:** Identified in `/plan-design-review` (2026-04-19). `theme.py` now has 21 color tokens (including PR11b promote_* and warn_* families). DESIGN.md is the natural next level.

---

## [UI] Update 5-tab workflow description after Training Data rename

**What:** `clinical_app.py` line ~1204 contains a hard-coded workflow description string referencing "📊 Dataset". After PR11b renames the tab to "📚 Training Data", this copy becomes stale. Also update the welcome screen sidebar copy at line ~1246 where tab names are listed.

**Why:** The onboarding workflow copy ("1. 📊 Dataset — view synthetic members") will show the old tab name after the rename. A care manager reading the step list will see "Dataset" but the tab says "Training Data".

**Pros:** One-line fix. Keeps onboarding copy in sync with actual tab labels.

**Cons:** None — trivial change. Can be done in the same PR11b commit.

**Context:** Identified in `/plan-design-review` (2026-04-19). Part of the Dataset→Training Data rename decision made during this review.

---

## [P1] Phase 3: Fix all internal package imports (pip install -e . broken)

**What:** Change every `from governance.policy import`, `from core.agent_definition import`, etc. throughout `praktor/` to absolute `praktor.` prefix paths. Also remove `sys.path.insert(0, .../praktor)` from test files.

**Why:** Without this, `pip install -e .` results in `ModuleNotFoundError` for every governance/core/monitoring path. Every item below is blocked until this is fixed.

**Blast radius:** praktor/governance/*.py, praktor/core/*.py, praktor/monitoring/*.py, praktor/tools/*.py, praktor/transport/*.py, praktor/agents/*.py, praktor/clinical/**/*.py (~32 files), tests/*.py (~20 files).

**Context:** Identified in PLAN.md Phase 3 review (2026-04-29).

---

## [P1] Phase 3: Write docs/governance.md as the authoritative spec

**What:** Create `docs/governance.md` covering: `GovernancePolicy` API, `block_pii()` quickstart, `RegexEntities` constants, `dry_run=True` escape hatch, `GovernancePolicyViolation` fields, PresidioDetector vs RegexDetector tradeoffs.

**Why:** Governance is a new framework surface — without a spec doc, API consumers have no contract to code against and reviewers can't verify correctness.

**Context:** PLAN.md Phase 3, item 1 (2026-04-29). Must be written before wiring governance into Agent.run().

---

## [P1] Phase 3: Structured GovernancePolicyViolation (field_name, entity_type, detector_class, doc_url)

**What:** Add `field_name`, `entity_type`, `detector_class` fields + helpful `__str__` to `GovernancePolicyViolation`. Example: "Field 'text' blocked by RegexDetector: US_SSN detected. See: https://github.com/wimverleyen/praktor.ai#governance-quickstart".

**Why:** Bare exceptions with no context are unusable in production. Actionable errors are table stakes for a framework API.

**Context:** PLAN.md Phase 3, DX item 3/11 (2026-04-29).

---

## [P1] Phase 3: Add GovernancePolicy(dry_run=True) escape hatch

**What:** Add `dry_run: bool = False` to `GovernancePolicy`. When True, detectors run but only log to stderr — never raise, never block sink writes.

**Why:** Without this, devs must mock internals to test governance-adjacent code. Standard test-ergonomics escape hatch.

**Context:** PLAN.md Phase 3, DX item 4 (2026-04-29).

---

## [P1] Phase 3: Wire pre-call governance check into Agent.run()

**What:** Before each LLM call in `Agent.run()`, iterate `policy.pre_call_detectors` over the prompt. On `BLOCK` → raise `GovernancePolicyViolation`, halt immediately (no LLM call). On `REDACT` → replace the flagged field with `[REDACTED]` before calling.

**Why:** Core governance contract. Without this, the policy object exists but has no effect.

**Context:** PLAN.md Phase 3, item 3 (2026-04-29).

---

## [P1] Phase 3: Wire post-call governance check into Agent.run()

**What:** After each LLM response in `Agent.run()`, iterate `policy.post_call_detectors` over the output. On `BLOCK` → raise `GovernancePolicyViolation` (response never yielded). On `REDACT` → replace fields before returning.

**Why:** Completes the governance loop — pre-call covers input, post-call covers output.

**Context:** PLAN.md Phase 3, item 4 (2026-04-29).

---

## [P1] Phase 3: RegexEntities constants class (no magic strings)

**What:** Add `RegexEntities` class with named constants matching `RegexDetector._PATTERNS` keys (e.g. `RegexEntities.US_SSN`, `RegexEntities.CREDIT_CARD`). Re-export from `praktor.governance`.

**Why:** Magic strings in detector configs cause silent misses. Named constants let IDEs autocomplete and catch typos at import time.

**Context:** PLAN.md Phase 3, DX item (2026-04-29).

---

## [P1] Phase 3: block_pii() convenience function

**What:** Add `block_pii() -> AgentDefinition` helper in `praktor/governance/helpers.py`, re-exported from `praktor/__init__.py`. Returns a pre-configured `AgentDefinition` with `GovernancePolicy` blocking US_SSN, CREDIT_CARD, EMAIL_ADDRESS.

**Why:** The "magical moment" for new users. One import + one call should block PII — no config required.

**Context:** PLAN.md Phase 3, DX item 6 / quickstart goal (2026-04-29).

---

## [P1] Phase 3: Add tests/test_governance_dx.py

**What:** New test file with 5 test groups: `block_pii()` returns new AgentDefinition; `RegexEntities` constants match `_PATTERNS` keys; `DetectorConfig(detector_class=RegexDetector)` coerces to qualified string; unknown entity logs WARNING (not PresidioDetector); `GovernancePolicyViolation.__str__` includes doc_url.

**Why:** New DX API surface has zero test coverage. These tests define the contract.

**Context:** PLAN.md Phase 3, item 15 (2026-04-29).

---

## [P1] Phase 3: Governance metrics in monitoring stack

**What:** Emit `governance.block_count`, `governance.redact_count`, `governance.detector_latency_ms` KPIs on each pre/post-call check. Wire into the Grafana dashboard as a new "Governance" row.

**Why:** Without metrics, governance violations are silent in production monitoring.

**Context:** PLAN.md Phase 3 (2026-04-29).

---

## [P1] Phase 3: DetectorConfig accepts class OR string for detector_class

**What:** `DetectorConfig.__post_init__` should coerce a class reference to its qualified string name (e.g. `RegexDetector` → `"praktor.governance.detectors.RegexDetector"`). Stored as string in audit log for serializability.

**Why:** Passing a class directly is ergonomic; storing a string is required for JSON audit logs.

**Context:** PLAN.md Phase 3, DX items (2026-04-29).

---

## [P1] Phase 3: demo-governance CLI command (< 2 min, no Ollama needed)

**What:** Add `python -m praktor demo-governance` subcommand that runs a standalone RegexDetector blocking US_SSN on a test string. Should print a `GovernancePolicyViolation` with structured fields. No LLM required.

**Why:** Zero-to-BLOCK in under 2 minutes is the DX north star. Devs must see governance work before wiring it into an agent.

**Context:** PLAN.md Phase 3, DX magical moment (2026-04-29).

---

## [P1] Phase 3: Add py.typed marker (PEP 561)

**What:** Add an empty `praktor/py.typed` file to declare the package as typed. Required for mypy strict mode and IDE type inference.

**Why:** Without this, all type annotations in the package are invisible to external type checkers.

**Context:** PLAN.md Phase 3, item 13 (2026-04-29).
