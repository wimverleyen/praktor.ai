# Diabetes HEDIS Gap Closure — Clinical AI Demo
### praktor.ai · MY 2026 · Approach B

> **Audience:** VP of AI Engineering (primary) → CIO (executive brief) · Business stakeholders (NBA context)
>
> **Demo date:** April 2026 · **Status:** Built, tested, running

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Business Case](#2-business-case)
3. [The AI Innovation: Agentic Clinical Reasoning](#3-the-ai-innovation-agentic-clinical-reasoning)
4. [Demo Walkthrough](#4-demo-walkthrough)
5. [Clinical Perspectives](#5-clinical-perspectives)
6. [Workflow Architecture and Assumptions](#6-workflow-architecture-and-assumptions)
7. [Privacy and Compliance](#7-privacy-and-compliance)
8. [Limitations and What This Demo Does Not Claim](#8-limitations-and-what-this-demo-does-not-claim)
9. [Roadmap](#9-roadmap)
10. [Running the Demo](#10-running-the-demo)

---

## 1. Executive Summary

Medicare Advantage (MA) plans are financially rated on a 1–5 Star scale by the Centers for Medicare and Medicaid Services (CMS). A one-half-star improvement can unlock tens of millions of dollars in Quality Bonus Payments (QBPs). The largest single driver of Stars improvement is closing open HEDIS quality gaps — and for most MA plans, **diabetes is the highest-leverage disease category**.

This demo shows a different kind of AI than a chatbot or a nudge engine. It shows an **AI clinical agent that reasons** — reading a member's longitudinal record, detecting that a physician has not adjusted treatment despite rising A1c values for 18 months, identifying which specific lab order closes two quality gaps simultaneously, anchoring a recommendation to a specific cardiovascular outcomes trial, and composing a culturally appropriate outreach message in the member's preferred language. All of this in a single, auditable reasoning trace.

**The demo runs three engineered members through the agent in under 10 seconds** — with no LLM call required in dry-run mode — and produces:

| Member | Story | Gaps Closed | Stars Leverage |
|--------|-------|-------------|----------------|
| D001 Maria Lopez | Untested GSD — cheapest gap to close | 1 (GSD) | 3x |
| D002 James Chen | Therapeutic inertia + KED gap | 2 (GSD, KED) | 4x |
| D003 Patricia Williams | Gap-stacking — 4 open measures | 4 (GSD, KED, SPD-E, EED-E) | 6x |

---

## 2. Business Case

### 2.1 Why Diabetes?

Diabetes is the defining condition in Medicare Advantage Stars. The MY 2026 diabetes measure set covers five distinct quality indicators, three of which are new or substantially revised:

| Measure | Stars Weight | What Moves It |
|---------|-------------|----------------|
| GSD — Glycemic Status Assessment | **3x (inverse)** | A1c or GMI result in the measurement year |
| KED — Kidney Health Evaluation | 1x | eGFR **and** uACR both present |
| EED-E — Eye Exam | 1x | Retinal exam by eye care professional |
| SPD-E — Statin Therapy | 1x | PDC ≥ 0.80 for statins |
| BPD-E — Blood Pressure Control | 1x | Most recent BP < 140/90 |

- **~30% of Medicare Advantage members have diabetes** — the largest single chronic disease cohort.
- **GSD is triple-weighted and inverse-scored**: every member with A1c >9.0% or no A1c result penalizes Stars 3x. An uncontrolled diabetic is not just a missed opportunity — it is an active Stars drag.
- **KED is the highest-clinical-consequence gap**: missing uACR is common (most labs run eGFR automatically but not uACR), and identifying uACR-positive members opens a SGLT2i prescribing window supported by three landmark renal outcomes trials.
- **Gap-stacking multiplies ROI**: a single comprehensive PCP visit can close GSD (standing A1c order), KED (add uACR to the same blood draw), SPD-E (statin prescription), and EED-E (eye care referral) — four gaps from one touchpoint.

### 2.2 Where Current Approaches Fall Short

Most health plan AI investments in this space produce a **nudge engine**: a rule-based or predictive model that outputs a ranked list of members to call and a templated script for the care coordinator to read. Nudge engines are valuable but have a structural ceiling:

| Nudge Engine | Clinical Reasoning Agent |
|---|---|
| Outputs: "Call this member about their A1c" | Outputs: "Member on metformin+glipizide 18mo, A1c 8.7% trending up — therapeutic inertia. Recommend PCP medication review + uACR add-on to next lab draw. CREDENCE trial: SGLT2i reduces renal composite 30% in this profile." |
| Tells care coordinator *who* to contact | Tells care coordinator *what* the clinical situation is and *why* it matters |
| Static script | Dynamic rationale grounded in the member's specific record |
| Closure rate improvement: incremental | Closure rate improvement: meaningful — because actions are matched to clinical reality |
| Black box to physician | Auditable reasoning trace — physician can review the chain |

The gap is not a better model. It is a different architecture: an agent that reads, reasons, cites, and recommends — rather than a classifier that ranks.

### 2.3 Financial Framing

A half-star improvement in Medicare Advantage typically yields:
- **$500 per-member-per-year** in Quality Bonus Payment uplift (varies by plan size and benchmark)
- For a 50,000-member MA plan: ~$25M annually
- For a 500,000-member plan: ~$250M annually

Every HEDIS gap closed is a fractional contribution to that improvement. The triple-weighted, inverse-scored GSD measure has the highest per-gap dollar value in the diabetes set. Identifying and closing untested members (D001 story) is the highest-ROI action in the portfolio: one standing lab order, zero cost, closes a 3x-weighted gap.

### 2.4 Strategic Positioning

This demo is intentionally scoped as a **Wave 1 artifact** for a specific audience path:

```
VP AI Engineering  →  CIO  →  Business stakeholders (next best action context)
```

The VP AI Engineering uses this to demonstrate that praktor.ai has clinical depth, not just general AI capability. The CIO sees a concrete, quantifiable case for investment. The business stakeholders see a path from "nudge engine" to "clinical reasoning layer" — a roadmap, not a replacement.

---

## 3. The AI Innovation: Agentic Clinical Reasoning

### 3.1 What Makes This Agentic

The diabetes HEDIS agent is not a prompt sent to a language model. It is a **ReAct reasoning loop** — an agent that interleaves thinking, tool use, and observation in multiple steps before producing a recommendation.

```
Thought → Action (tool call) → Observation → Thought → Action → … → Final Answer
```

Each step is recorded as an OpenTelemetry span. The full reasoning trace is auditable — a physician or clinical reviewer can read exactly what data the agent consulted and why it reached its conclusion.

The agent runs 7 clinical tools in sequence:

| Tool | What the Agent Learns |
|------|-----------------------|
| `gap_registry` | Which HEDIS gaps are open and their Stars weight |
| `ehr_lookup` | A1c history, eGFR, uACR, BP readings — trend analysis |
| `drug_adherence` | PDC scores for statin, oral hypoglycemics, RASA |
| `claims_lookup` | Full Rx fill history — identifies current regimen and duration |
| `sdoh_lookup` | Language, health literacy, PCP contact, pharmacy access |
| `outreach_history` | Prior contact attempts and member responses |
| `measure_criteria` | NCQA exclusion criteria — rules out contraindications |

### 3.2 Three Differentiating Capabilities

#### A. Therapeutic Inertia Detection

Therapeutic inertia is the clinical term for a physician (or system) failing to escalate treatment when a patient's condition is not at goal. It is pervasive in primary care diabetes management — studies estimate 50–75% of patients with uncontrolled A1c experience a delay of more than 12 months before treatment is intensified.

The agent detects inertia by cross-referencing the Rx fill history (`claims_lookup`) with the A1c trend (`ehr_lookup`):

> "Member on metformin+glipizide for 18 consecutive months. A1c progression: 8.1% → 8.4% → 8.7%. Same drug class throughout. This is a therapeutic inertia pattern."

When inertia is detected, the recommendation is not just "call the member." It is: inform the PCP that treatment escalation should be considered, identify the appropriate rung on the ADA 2024 escalation ladder given the member's specific profile (eGFR 52 → SGLT2i, not GLP-1), and cite the trial evidence that supports that specific choice.

**Why this matters for Stars:** Inertia-detected members have A1c values that land in the GSD poor-control band (>8.0%), penalizing Stars 3x. Moving these members to the GSD good-control band (A1c <8.0%) is the highest-value clinical intervention in the diabetes Stars portfolio.

#### B. Gap-Stacking

Gap-stacking is the recognition that multiple HEDIS measures can be closed from a single member encounter — if the action is designed to address all of them simultaneously.

The agent is explicitly instructed to check all five diabetes measures before recommending a single action:

> "Before recommending a single action, verify all five diabetes measures (GSD, KED, EED-E, SPD-E, BPD-E). Stacking 3 closures from one touchpoint multiplies Stars ROI."

For D003 Patricia Williams (4 open gaps), the agent recommends one PCP visit with four simultaneous closures:
1. Standing A1c order → closes GSD
2. uACR added to the same blood draw → closes KED (eGFR already on file)
3. Statin prescription at the visit → closes SPD-E (dispensing rate)
4. Eye care referral at the same visit → initiates EED-E closure pathway

This is not a heuristic. It is the agent reasoning over what each gap requires and recognizing that a single visit can satisfy all four — a judgment a care coordinator making 80 calls per day is unlikely to make consistently.

#### C. Evidence-Anchored Recommendations

Every clinical recommendation is grounded in trial evidence that the agent is trained to cite when relevant:

| Trial | What It Supports |
|-------|-----------------|
| **CREDENCE** (canagliflozin, 2019) | SGLT2i in CKD + T2D: 30% reduction in renal composite endpoint |
| **EMPA-KIDNEY** (empagliflozin, 2022) | SGLT2i in CKD: 28% reduction in kidney disease progression or CV death |
| **DAPA-CKD** (dapagliflozin, 2020) | SGLT2i efficacy in CKD even without T2D: 39% reduction |
| **UKPDS** (1998) | Intensive glycemic control reduces microvascular complications ~25%; legacy effect persists |
| **ACCORD** (2008) | A1c <6.0% increased mortality — sets the floor for the GSD inverse rate design |
| **CARDS** (atorvastatin, 2004) | Statin reduced first CV event 37% in T2D without prior CVD → SPD-E rationale |
| **HPS** (2002) | Statin benefit independent of baseline LDL in high-risk patients |
| **ACCORD-BP** (2010) | BP <140/90 is the evidence-based floor for BPD-E compliance |

A care manager reading the D002 rationale gets: *"Therapeutic inertia detected — SGLT2i is indicated if uACR >30 mg/g (CREDENCE/EMPA-KIDNEY: 28–30% renal composite reduction in CKD + T2D)"* — a sentence that takes a senior clinical pharmacist 10 minutes to synthesize from primary literature. The agent does it in the reasoning loop.

### 3.3 How It Is Built

The agent runs on **praktor.ai** — a general-purpose agentic framework using:

- **LangChain** for LLM abstraction and LCEL chain composition
- **ReAct loop** (`max_steps=8`) — the Thought/Action/Observation pattern runs as an async generator
- **AsyncLLMAdapter** — streaming + 3-attempt retry with exponential backoff + SHA-256 cache (temperature=0.0 → deterministic → cache-eligible)
- **7 clinical SQLite-backed tools** — real data reads, no mocking in production
- **OpenTelemetry spans** — every LLM call and tool call recorded as a child span; full trajectory waterfall visible in the Streamlit UI
- **LLM-as-judge** — `ClinicalJudgeScore` evaluates recommendations on 4 criteria: gap identification accuracy, action appropriateness, evidence citation quality, safety flag coverage
- **Prompt optimizer** — `PromptOptimizer` uses judge scores as ground truth to iteratively improve the prompt; closure outcomes at 30/60/90 days feed the next optimization cycle

The agent works with any LLM — local Ollama (`llama3:8b`, `mistral`), Anthropic (`claude-sonnet-4-6`), or OpenAI (`gpt-4o`). The dry-run mode requires no LLM at all and runs in under 1 second.

### 3.4 Human-in-the-Loop by Design

Every agent recommendation is staged for care manager review before any action is taken:

```
Agent recommendation → HITL review queue (Streamlit UI)
                     → Care manager: approve / modify / reject
                     → Action executed (call, message, referral)
                     → Outcome tracked at 30/60/90 days
                     → Closure ground truth → PromptOptimizer
```

The agent does not take action autonomously. This is intentional — HIPAA, clinical safety, and organizational trust all require a human to remain in the decision loop. The agent's job is to dramatically improve the *quality* of what the care manager reviews, not to replace the care manager.

---

## 4. Demo Walkthrough

### Member 1 — Maria Lopez (D001)
**Story: Cheapest gap to close**

Maria is 65, Spanish-speaking, high SDOH (transportation barriers, food insecurity). She takes metformin 500mg. Her last A1c was 7.4% — in October 2025. That result does not count for MY 2026. She has no A1c in the current measurement year.

**Clinical situation:** Under the GSD measure, a missing A1c is indistinguishable from an uncontrolled A1c — both are scored as poor control. Maria's Stars contribution is the same as a member with A1c of 11%. Yet her actual glycemic status is probably fine.

**Agent reasoning:**
1. Identifies GSD as the only open gap (3x Stars, inverse)
2. Confirms via ehr_lookup: last A1c 7.4% in 2025, nothing in 2026
3. Detects no therapeutic inertia (single-agent, A1c previously controlled)
4. Notes via sdoh_lookup: PCP Dr. Morales is Spanish-speaking
5. Recommends: warm outreach to Dr. Morales for a standing A1c order at next visit, draft message in Spanish

**Why this is the "cheapest close" story:** One lab order. Zero clinical intervention. 3x Stars leverage. The agent identifies that the gap is an administrative failure, not a clinical one — and routes accordingly.

---

### Member 2 — James Chen (D002)
**Story: Therapeutic inertia + SGLT2i recommendation**

James is 68, English-speaking, low SDOH. He has been on metformin 1000mg + glipizide 5mg for 18 months. His A1c has risen: 8.1% → 8.4% → 8.7%. His eGFR is 52 (CKD stage 3a). His uACR has never been ordered.

**Clinical situation:** Two gaps. GSD is open because A1c >8.0% puts him in the poor-control band (triple-weighted penalty). KED is open because eGFR is present but uACR is absent — eGFR-alone fails the measure. The combination is particularly significant: eGFR 52 + CKD stage 3a is exactly the population where SGLT2i therapy (CREDENCE, EMPA-KIDNEY) has the most compelling evidence for renal protection.

**Agent reasoning:**
1. Identifies GSD (open, A1c 8.7% > 8.0%) and KED (open, uACR missing)
2. Detects therapeutic inertia: same drug class for 18 months, A1c trending up
3. Notes KED gap: eGFR 52 present, uACR absent → eGFR-only fails KED
4. Verifies KED exclusion criteria: no ESRD, no dialysis, no transplant
5. Identifies escalation ladder step 3 (SGLT2i): eGFR 52 + expected uACR positivity → CREDENCE/EMPA-KIDNEY indication
6. Recommends: PCP warm outreach — medication review visit + uACR add-on to next lab draw
7. Closes 2 gaps from one PCP interaction (GSD via A1c documentation, KED via uACR)

**This is the "wow" moment for the CIO.** The agent reads a rising A1c trend, recognizes it as inertia, connects missing uACR to a landmark outcomes trial, and delivers a clinically specific recommendation that a care coordinator would need a clinical pharmacist to compose. The reasoning trace is fully auditable.

> ⚠️ **Pre-demo clinical sign-off required:** The empagliflozin/SGLT2i recommendation for D002 should be reviewed by a Medical Director or clinical pharmacist before this demo is presented to external stakeholders. See [Section 8](#8-limitations-and-what-this-demo-does-not-claim).

---

### Member 3 — Patricia Williams (D003)
**Story: Gap-stacking economics**

Patricia is 62, English-speaking, medium SDOH (cost and work schedule barriers). She takes metformin 500mg. She has four open diabetes measures: GSD (no A1c in MY), KED (no kidney labs at all), SPD-E (no statin ever), EED-E (eye exam expired >24 months ago).

**Clinical situation:** 6x Stars exposure from one member — GSD (3x) + KED (1x) + SPD-E (1x) + EED-E (1x). Her last A1c was 8.2% in June 2025 and she has had no follow-up. She has never been prescribed a statin despite being 62 with diabetes (ADA guidelines recommend statin for virtually all diabetics 40–75 without ASCVD).

**Agent reasoning:**
1. Identifies all 4 open gaps and their total Stars exposure (6x)
2. Confirms via ehr_lookup: no labs in MY 2026
3. Confirms via claims_lookup: no statin in fill history
4. Applies gap-stacking logic: all 4 gaps can be closed from one comprehensive PCP visit
5. Calculates closure plan: A1c order (GSD) + uACR+eGFR same draw (KED) + statin prescription (SPD-E) + eye care referral (EED-E)
6. Cites CARDS trial: statin reduces first CV event 37% in T2D without prior CVD
7. Recommends: PCP warm outreach for comprehensive diabetes care visit

**This is the "economics" story for the business audience.** Four quality closures from one care coordinator call and one PCP visit. The agent doesn't recommend calling Patricia four times for four separate gaps — it recognizes the full picture and designs one high-efficiency action.

---

## 5. Clinical Perspectives

### 5.1 MY 2026 Measure Changes and Why They Matter

**GSD replaces CDC-HbA1c-Control (MY 2025 and prior)**

The old measure reported a binary: did the member get an A1c test? The new GSD measure reports three rates:
- A1c <8.0% (good control)
- A1c <7.0% (tighter control subgroup)
- A1c >9.0% (poor control — **inverse-scored, triple-weighted**)

The inverse rate change is the most significant measurement architecture shift in diabetes Stars in a decade. Under the old measure, an untested member was a missed numerator event. Under GSD, an untested member is treated as poor control — the worst possible Stars outcome. Every member without an A1c in the measurement year is now an active Stars penalty.

**KED requires both tests — a common failure point**

Most clinical labs run a basic metabolic panel (BMP) that includes creatinine for eGFR calculation. Most do not automatically run uACR unless specifically ordered. The result: a large fraction of diabetic members have eGFR documented but no uACR — and they fail KED. The fix is operationally simple (standing uACR order, or add uACR to the next blood draw) but requires the care team to know the gap exists.

**SPD-E is ECDS-only as of MY 2026**

The hybrid reporting option (admin + ECDS) was retired for SPD-E. Plans must now report via Electronic Clinical Data Systems. This creates a data infrastructure requirement that most plans are still working through — statin fills may exist in pharmacy claims but not be accessible via ECDS. For plans without a mature ECDS pipeline, SPD-E compliance will be artificially low in MY 2026.

**BPD-E introduces RPM as measure-compliant data**

Remote Patient Monitoring (RPM) blood pressure readings are now acceptable for BPD-E under voluntary ECDS reporting. This is significant for plans with Livongo, Omada, or Withings RPM programs — those readings, previously invisible to HEDIS, can now count. Plans that have already deployed RPM have a structural advantage in BPD-E that will widen over time.

### 5.2 The Treatment Escalation Ladder (ADA 2024)

The escalation ladder is not specific to this demo — it is the current standard of care for type 2 diabetes management. Understanding it is essential context for any clinician reviewing an agent recommendation.

```
Step 1: Metformin monotherapy
        └── A1c not at goal after 3 months?
Step 2: Add GLP-1 receptor agonist
        └── Preferred if: BMI ≥27, or CV risk, or cost-accessible
        └── Options: semaglutide (Ozempic), dulaglutide (Trulicity), liraglutide (Victoza)
Step 3: Add SGLT2 inhibitor
        └── Preferred if: CKD (eGFR 20–60, uACR >200), or HFrEF
        └── Options: empagliflozin (Jardiance), dapagliflozin (Farxiga), canagliflozin (Invokana)
        └── Evidence: CREDENCE, DAPA-CKD, EMPA-KIDNEY
Step 4: Add basal insulin
        └── When: A1c >10% on dual oral therapy
        └── Target fasting glucose: 80–130 mg/dL
Step 5: Basal-bolus insulin
        └── When: A1c >9% on optimized basal insulin
        └── Consider endocrinology referral
```

The agent uses this ladder to determine the appropriate escalation recommendation when inertia is detected. It does not recommend insulin initiation autonomously — that always triggers an escalation flag requiring physician involvement.

### 5.3 Why Untested Members Are the Highest-Leverage Target

The clinical intuition is counterintuitive: why prioritize a member who has *no* A1c over a member whose A1c is demonstrably high?

Under GSD's inverse rate design, **the answer is Stars mathematics**:

1. An untested member automatically counts as poor control (A1c >9.0%) — the worst possible Stars position
2. A single lab order, costing approximately $10–15, converts that member from a 3x Stars penalty to a potential 3x Stars positive
3. If the member's actual A1c comes back <8.0%, the plan moves from -3 to +3 on that member — a 6-point swing from one lab order
4. No clinical intervention required — just documentation

For a plan with 5,000 untested diabetic members, closing this gap across the cohort is a Stars improvement campaign that requires zero medication changes, zero specialist referrals, and minimal care coordinator time. The agent identifies untested members, determines the appropriate outreach vector (language, PCP contact, SDOH barriers), and drafts the outreach message in one pass.

### 5.4 The Inertia Problem in Practice

Therapeutic inertia is one of the most-studied failures in chronic disease management. The mechanism is well understood:

- A primary care physician sees a diabetic patient with A1c of 8.5%
- The A1c has been 8.5% for 6 months
- The visit is 15 minutes; the patient has five other issues to discuss
- Changing a diabetes regimen requires patient education, insurance prior auth, follow-up titration
- The physician moves on to the next issue and documents "continue current medications"
- Six months later, the A1c is 8.7%

From the health plan's perspective, this is not a compliance failure by the patient — it is a system failure. The member is taking their medications (PDC may be fine). The problem is that the medications are no longer sufficient and nobody has escalated the regimen.

The agent detects this pattern algorithmically: same drug classes in the fill history for >12 months, A1c not at goal, no step-up prescription filled. When detected, it surfaces the finding to the care coordinator with specific clinical context — enabling a targeted PCP outreach about treatment escalation rather than a generic "your member has an A1c gap" notification.

---

## 6. Workflow Architecture and Assumptions

### 6.1 System Architecture

```
Data Layer (SQLite / production: Snowflake or FHIR R4)
  ├── clinical_data.db: members, gaps, labs, claims, PDC, outreach
  └── monitoring.db: agent runs, trajectory steps, OTel spans

Clinical Tools (7 read-only tools)
  ├── gap_registry     ← reads gaps table, computes priority_score
  ├── ehr_lookup       ← reads labs + vitals, detects trends
  ├── drug_adherence   ← reads pdc_scores table
  ├── claims_lookup    ← reads claims table, reconstructs Rx history
  ├── sdoh_lookup      ← reads members table (language, SDOH, PCP)
  ├── outreach_history ← reads outreach table
  └── measure_criteria ← in-memory NCQA spec lookup (no DB read)

diabetes_hedis Agent (ReAct loop, max_steps=8)
  └── AsyncLLMAdapter (llama3:8b local / claude-sonnet-4-6 production)
      └── Prompt: specialist diabetes context + gap-stacking + escalation ladder

Output
  ├── Structured Final Answer (ACTION_TYPE, MEASURES_ADDRESSED, GAPS_STACKED, …)
  ├── OTel trajectory spans → monitoring.db → Streamlit Traces tab
  └── HITL review queue → care manager approval → action execution
```

### 6.2 Workflow Assumptions

The following assumptions are built into the demo design. In production deployment, each assumption should be validated against the health plan's actual data environment.

#### Data Assumptions

| Assumption | Demo implementation | Production requirement |
|------------|--------------------|-----------------------|
| Gap data is available | SQLite seed from `init_diabetes_demo.py` | HEDIS gap file from vendor (e.g., Cotiviti, Episource) or internal analytics |
| A1c, eGFR, uACR values are queryable | SQLite lab table | EHR integration (HL7 FHIR R4 Observation resource) or lab vendor feed |
| Pharmacy fill history is available | SQLite claims table | PBM claims feed (e.g., Express Scripts, CVS Caremark) via 835 or NCPDP |
| PDC is pre-computed | Static seed values | Daily PDC computation from rolling fill history |
| SDOH data is available | Static seed (language, literacy, PCP) | Member enrollment data + supplemental SDOH assessment (e.g., PRAPARE) |
| Outreach history is queryable | SQLite outreach table | CRM or care management platform (Salesforce Health Cloud, Health Catalyst) |
| Member IDs are de-identified | SHA-256 hash + env salt | Production salt must be a secret managed via KMS (e.g., AWS Secrets Manager) |

#### Clinical Assumptions

| Assumption | Rationale | Caveats |
|------------|-----------|---------|
| GSD is the highest-priority gap | Triple-weighted, inverse-scored — highest Stars leverage | True only if the member has no ASCVD (SPD-E ASCVD exclusion check) |
| eGFR-only KED gap is addressable by adding uACR | Most common KED failure mode is missing uACR | Requires PCP engagement; mail-in urine kits are an alternative for no-contact members |
| SGLT2i is appropriate for eGFR 52 + CKD | CREDENCE, EMPA-KIDNEY, DAPA-CKD inclusion criteria (eGFR ≥20) | Contraindications (DKA history, recurrent UTI, prior amputation) must be checked by prescribing physician |
| Escalation ladder follows ADA 2024 Standards | Most current guideline | Individual plan formulary may prefer different agents; prior auth requirements vary |
| Untested member has no clinical barrier to lab order | Most untested members have no documented clinical reason for avoiding A1c | Some members on chronic erythropoietin, sickle cell, or hemolytic anemia have A1c interference — GMI/fructosamine is the alternative |
| One PCP visit can close 4 gaps (D003) | All 4 gaps require PCP-ordered or PCP-referred actions | Requires PCP buy-in and a structured diabetes care visit protocol |

#### Technical Assumptions

| Assumption | Current state |
|------------|--------------|
| LLM model available | `llama3:8b` via local Ollama; `claude-sonnet-4-6` for production quality |
| No live LLM required for dry-run demo | Dry-run patches the ReAct adapter with pre-scripted responses |
| OTel spans available | Recorded to `monitoring.db`; Streamlit Traces tab renders waterfall |
| PHI is scrubbed before any LLM call | Hard gate in `clinical/privacy/deidentifier.py` — `ValueError` on `phi_scrubbed=False` |
| Member IDs are hashed before storage | `hash_member_id()` in `clinical/schemas.py` — SHA-256 + PRAKTOR_MEMBER_SALT |

### 6.3 Out-of-Scope for This Demo

The following were explicitly excluded from Wave 1 to keep the demo focused:

- **ECDS pipeline simulation** — SPD-E and BPD-E are ECDS-only measures; this demo does not simulate the supplemental data pipeline. In production, EHR or lab vendor data feeds replace claims-based proxies.
- **Multi-agent orchestration** — A production system might use separate agents for stratification, clinical reasoning, outreach orchestration, and supplemental data retrieval. This demo uses a single agent for simplicity.
- **Population stratification** — The demo runs one member at a time. A production workflow would stratify the full member population by gap priority before running individual agents.
- **Auto-prescription or autonomous action** — The agent never takes action without human approval. Automated prescription generation is out of scope permanently (clinical safety + regulatory).
- **Prior authorization automation** — SGLT2i initiation for CKD+T2D often requires prior auth. This demo flags the recommendation but does not simulate the PA workflow.

---

## 7. Privacy and Compliance

### 7.1 PHI Gate — IRON RULE

The PHI gate is the most important single engineering decision in the clinical layer. Every data path that touches a language model or a vector store passes through:

```python
from clinical.privacy.deidentifier import validate_phi_scrubbed

# HARD RAISE — never log and continue
validate_phi_scrubbed(phi_scrubbed=chunk.phi_scrubbed, context="ingest:claim")
```

If `phi_scrubbed=False`, ingestion aborts with a `ValueError`. There is no "log and continue" path. This is enforced at:
- `MemberBrain.add_chunk()` — every FAISS write
- `ClaimsIngestor`, `EHRIngestor`, `NotesIngestor` — every ingestion pipeline
- The LLM prompt renderer — member data in prompts uses `member_id_hash_short` (first 12 chars of SHA-256), never raw member ID

### 7.2 Member Identification

Raw member IDs are never stored. On ingestion, `hash_member_id(raw_id)` is called immediately:

```python
def hash_member_id(raw_member_id: str) -> str:
    salted = f"{PRAKTOR_MEMBER_SALT}:{raw_member_id}"
    return hashlib.sha256(salted.encode()).hexdigest()
```

The salt is set via `PRAKTOR_MEMBER_SALT` environment variable. In production:
- Use a secret managed by KMS (AWS Secrets Manager, HashiCorp Vault)
- Rotate annually; rebuild the hash table after rotation
- Never log or print raw member IDs

### 7.3 Audit Trail

All PHI gate events and ingestion operations write to an append-only audit log:

```
2026-04-16T14:23:11Z  GATE_PASS  context=ingest:claim  member=d746f96fd788...
2026-04-16T14:23:11Z  GATE_PASS  context=ingest:lab    member=d746f96fd788...
```

The audit log is the HIPAA access audit record. It is append-only and should be stored in a WORM-compliant location in production.

### 7.4 Regulatory Considerations for Production Deployment

| Area | Consideration |
|------|--------------|
| **HIPAA** | Clinical data in transit must be encrypted (TLS 1.2+); at rest must be encrypted (AES-256). Business Associate Agreement (BAA) required with any cloud LLM provider. |
| **FDA** | If recommendations are used to directly influence prescribing decisions without physician review, the system may qualify as a Clinical Decision Support (CDS) software device under 21 CFR Part 820. HITL design mitigates this risk. |
| **CMS Stars audit** | HEDIS gap closures must be documented with valid NCQA service codes. The agent recommendation is not itself a closure event — the underlying clinical service (lab result, prescription fill) is. |
| **State insurance regulations** | Some states require disclosure when AI is used in care management outreach. Legal review recommended before production deployment. |

---

## 8. Limitations and What This Demo Does Not Claim

This section is included because intellectual honesty about limitations is a prerequisite for trust — especially in a clinical context.

### 8.1 The Demo Uses Synthetic Data

All three members (D001, D002, D003) are engineered synthetic profiles. They are designed to illustrate specific clinical reasoning patterns, not to represent the statistical distribution of a real plan's diabetic population. Real member populations have:

- More complex comorbidities (heart failure, ESRD, dementia)
- More ambiguous lab trend patterns
- More varied Rx histories that do not fit cleanly on the escalation ladder
- Exclusion criteria that eliminate a significant fraction of the apparent denominator

A production deployment will require validation on real (de-identified) member data before clinical use.

### 8.2 The LLM Reasoning Chain Is Not Deterministic

The dry-run mode uses pre-scripted responses. In live LLM mode with `temperature=0.0`, the prompt cache ensures reproducibility for the same input. However, different LLM models will produce different reasoning chains, and the same model may reason differently on edge cases not represented in the prompt.

Clinical recommendations from a live LLM should always pass through:
1. The HITL review queue (human approval before action)
2. The `ClinicalJudgeScore` evaluation (automated quality check)
3. Periodic audits of approved recommendations vs. actual closure outcomes

### 8.3 The SGLT2i Recommendation Requires Clinical Sign-Off

The D002 empagliflozin recommendation is clinically sound based on the published trial evidence and ADA 2024 guidelines. However:

- It is based on eGFR alone (uACR not yet run)
- Contraindications (DKA history, recurrent UTI, volume depletion, amputation risk) are not present in the demo data but must be checked in a real clinical record
- The recommendation is to evaluate for SGLT2i — not to prescribe it. The prescribing decision belongs to the physician.

**Action required before external CIO presentation:** Obtain sign-off from a Medical Director or clinical pharmacist confirming the D002 reasoning chain is clinically appropriate as presented.

### 8.4 Gap Closure vs. Stars Credit

Closing a HEDIS gap (as the agent defines it) is not the same as receiving Stars credit. Stars credit requires:

- A numerator-eligible service event documented in NCQA-compliant data sources
- Reporting through the correct data submission pathway (admin, hybrid, or ECDS depending on measure)
- Compliance with NCQA's code sets (CPT, LOINC, NDC, ICD-10) for that specific measure year

The agent recommends actions that, when completed, should produce Stars-eligible service events. But the data capture, coding, and submission are downstream steps outside the agent's scope.

---

## 9. Roadmap

### Wave 1 (Current)
- ✅ `diabetes_hedis` AgentDefinition — therapeutic inertia, gap-stacking, escalation ladder
- ✅ 5 MY 2026 measures: GSD, KED, EED-E, SPD-E, BPD-E
- ✅ 3 engineered demo members (D001/D002/D003)
- ✅ Dry-run demo (no LLM required)
- ✅ HITL review queue (Streamlit)
- ✅ OTel trajectory waterfall (Streamlit Traces tab)
- ✅ LLM-as-judge (`ClinicalJudgeScore`)
- ✅ PHI gate (IRON RULE)

### Wave 2 — Clinical Data Integration
- FHIR R4 EHR adapter (Observation, MedicationRequest, Condition)
- PBM claims feed parser (NCPDP D.0 / 835)
- ECDS pipeline for SPD-E and BPD-E (replaces claims-based proxy)
- Mail-in uACR kit integration (Healthy.io, Siemens) for no-contact KED closure
- RPM feed ingestion for BPD-E (Livongo/Teladoc, Omada, Withings)
- Per-member FAISS second brain (longitudinal retrieval, not just current-year data)

### Wave 3 — Multi-Agent Orchestration
- Stratification agent: population-level gap prioritization before individual reasoning
- Outreach orchestration agent: channel selection, timing, language model fine-tuning
- Supplemental data agent: autonomous ECDS gap detection from clinical data sources
- Prior auth agent: identifies and initiates PA workflows for SGLT2i/GLP-1 recommendations
- Endocrinology referral agent: identifies members who should be referred out of PCP care

### Wave 4 — Closed-Loop Learning
- Closure outcome tracking at 30/60/90 days feeds PromptOptimizer
- Judge score calibration against actual closure rates
- Per-measure prompt variants optimized on real plan data
- Population-level Stars simulation: project QBP impact of agent recommendations before deployment

---

## 10. Running the Demo

### Prerequisites

```bash
# Python 3.11+, pip, git
pip install -r requirements.txt

# For live LLM (dry-run needs none of this)
# Option A: Local Ollama
ollama pull llama3:8b

# Option B: Anthropic API (production quality)
export ANTHROPIC_API_KEY=sk-ant-...
```

### 1. Seed the diabetes demo members

```bash
PYTHONPATH=praktor python scripts/init_diabetes_demo.py
# Seeding D001 (Maria Lopez) → d746f96fd788…
# Seeding D002 (James Chen)  → f80257a72081…
# Seeding D003 (Patricia Williams) → 0dc0a177cfd5…
# Seeded 3 diabetes demo members (MY 2026)
```

### 2. Run the agent (dry-run — no LLM required)

```bash
PYTHONPATH=praktor python scripts/demo_diabetes_agent.py --dry-run
```

Expected output shows:
- Three members processed
- 7 total gaps addressed from 3 recommendations
- 1 therapeutic inertia case detected (D002)
- Avg closure probability: 78%

### 3. Run a single member

```bash
# D001 — cheapest close
PYTHONPATH=praktor python scripts/demo_diabetes_agent.py --dry-run --member 0

# D002 — therapeutic inertia (the "wow" member)
PYTHONPATH=praktor python scripts/demo_diabetes_agent.py --dry-run --member 1

# D003 — gap-stacking
PYTHONPATH=praktor python scripts/demo_diabetes_agent.py --dry-run --member 2
```

### 4. Live LLM run

```bash
# Local Ollama
PYTHONPATH=praktor python scripts/demo_diabetes_agent.py --model llama3:8b

# Anthropic (production quality — requires ANTHROPIC_API_KEY)
PYTHONPATH=praktor python scripts/demo_diabetes_agent.py --model claude-sonnet-4-6
```

### 5. Launch the Streamlit UI

```bash
PYTHONPATH=praktor streamlit run praktor/ui/clinical_app.py
```

Navigate to the **🩺 Diabetes** tab to see:
- MY 2026 measure reference
- Demo member profiles and stories
- In-browser demo runner
- ADA 2024 escalation ladder

Navigate to **🔍 Traces** to see the OTel span waterfall for each agent run.

### 6. Run the tests

```bash
# All tests
PYTHONPATH=praktor pytest tests/ -v

# PHI gate (IRON RULE — must pass before demo)
PYTHONPATH=praktor pytest tests/test_clinical_privacy.py -v

# HEDIS agent (parser, escalation guardrails)
PYTHONPATH=praktor pytest tests/test_hedis_agent.py -v
```

---

## Key Contacts and Sign-Off Requirements

| Action | Required before |
|--------|----------------|
| Clinical sign-off on D002 SGLT2i recommendation | CIO presentation or external demo |
| Medical Director review of escalation ladder prompt | Production deployment |
| Legal review of outreach message language | Any member-facing communication |
| BAA with cloud LLM provider | Production deployment with real member data |
| `PRAKTOR_MEMBER_SALT` rotation to production secret | Any non-dev environment |

---

*Built on [praktor.ai](https://github.com/wimverleyen/praktor.ai) — a general-purpose agentic framework for clinical and non-clinical AI use cases.*

*MY 2026 measure specifications: NCQA HEDIS 2026 Technical Specifications (public). Clinical evidence citations: published peer-reviewed literature (NEJM, JAMA, Lancet). ADA Standards of Medical Care in Diabetes 2024.*
