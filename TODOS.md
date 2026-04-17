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
