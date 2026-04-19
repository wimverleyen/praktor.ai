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

## [UI] User-friendly error states

**What:** All `_load_*()` helper functions currently return `[]` on exception, making DB
errors look identical to "no data yet." Fix: let exceptions propagate (or distinguish them
with a sentinel), and show clinical users a friendly message ("Couldn't load the review
queue") with an expandable "Show details" section for the raw error.

**Why:** Trust erosion — a care manager reporting "the queue is empty" may actually have
a broken database connection. Silent `except: return []` hides failures.

**Pros:** Care managers can diagnose and report real errors. Engineers still get the
raw exception via the toggle.

**Cons:** Requires touching all 6 `_load_*` functions + the tab rendering functions
that interpret empty returns. Medium scope refactor.

**Context:** Identified in `/plan-design-review` Pass 2 (Interaction States, 2026-04-17).
The on-demand eval panel's error state was already fixed (now uses user-friendly message
+ expandable diagnostics). The cached data loaders are not yet fixed.

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

## [UI] Improve on-demand eval format contract

**What:** Update the `st.text_area` placeholder in the on-demand eval panel
(clinical_app.py ~line 699) to show the full NextBestAction key-value format.
Add a note that structured output scores highest on `completeness`.

**Why:** The `completeness` criterion ("all required output fields present") will
always score low unless the care manager knows to include ACTION_TYPE, RATIONALE,
DRAFT_MESSAGE, CLOSURE_PROBABILITY, LANGUAGE in the pasted text. The current
placeholder shows `ACTION_TYPE: pcp_warm_outreach\nRATIONALE: ...` but is
incomplete.

**Pros:** One-line change. Care managers get accurate completeness scores on
first use. Prevents confusion about why "completeness" is always 4-5/10.

**Cons:** Longer placeholder text takes more visual space.

**Context:** Identified by outside voice review (2026-04-17) in `/plan-eng-review`.

---

## [Monitoring] Add judge_type filter to aggregate queries

**What:** `collector.record_judge()` stores a `judge_type` field but `store.query_metrics()`
has no `judge_type` filter. Diabetes (10-dim) and HEDIS (9-dim) scores can mix with general
(5-dim) scores in aggregate histograms if `judge_type` is omitted by callers.

**Why:** The 10-dim diabetes `overall` and 5-dim general `overall` both use the 0–10 scale —
the corruption is invisible in dashboards but makes cross-type comparisons meaningless.

**Fix:** Add `judge_type: str | None = None` param to `store.query_metrics()` and an index
on `judge_evals.judge_type`. Also add a DB index (`CREATE INDEX IF NOT EXISTS ...`).

**Context:** Identified by adversarial review (2026-04-17) during `/ship`.

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
