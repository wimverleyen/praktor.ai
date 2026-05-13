# AIGov Framework

**Date:** 2026-05-05
**Version:** 0.8
**Status:** ACTIVE
**Supersedes:** `AIGov_Framework.md` v0.7, v0.6, v0.5, v0.4, `AIGov_Obligations_Framework.md`, `AIGov_Ledger_and_Scoreboard.md`

**Grounded in:** AgenticAI Eval Framework v1.0 (Watchtower), HAI Framework v2 (Watchtower), LLM-as-a-Judge Protocol (Watchtower/ELLMo), AI Observability Framework (Arize/OTel/Watchtower 2026-02-25), Knowledge FAIR — Framework for AI Readiness (Watchtower/KBS 2026-02-26).

---

## TL;DR

1. **Replace criteria with obligations.** 11 canonical **Agent Obligations**, each a testable predicate enforced at four points (build, pre-deploy, runtime, inter-agent handoff). An agent either holds an obligation or it violates it.
2. **Four enforcement points.** G-BUILD (static artifact checks), G-TEST (CI evaluation pipeline), G-RUN (per-inference production monitor), G-DELEGATE (subordinate handoff verification). All four emit typed events.
3. **The deliverable is a live ledger, not a PDF.** Every enforcement check emits a signed event into an append-only store. A **Scoreboard** reads the ledger and shows continuous status per (agent × obligation). Five data products ride on top. An Attestation exists as a signed, point-in-time view of the ledger.
4. **All 11 obligations are implemented.** `compliance_score() = 1.0`, `implementation_coverage() = 1.0`. No declared or planned stubs remain.
5. **The ledger is the moat.** History, benchmarks, drift signatures, and regulatory evidence packs compound with scale and cannot be replicated by a point-in-time competitor.
6. **Knowledge FAIR is the KB quality gate.** For RAG deployments, every knowledge base version must pass a Knowledge FAIR (Framework for AI Readiness) readiness check before it can be cited in evidence for O5 (Grounded Outputs). FAIR emits G-BUILD events to the ledger. A KB that fails FAIR cannot satisfy the faithfulness threshold — the obligation stays RED until the KB is remediated and re-certified. See §30.

---

# PART I — Framework

## 1. Core design principles

**Stop evaluating agents. Certify obligations they hold — continuously — and sell the data.**

An **Agent Obligation** is a single testable predicate about the agent's behavior, enforced at four points. An obligation is either HELD, VIOLATED, or STALE. There is no score.

A deployment holds a **bundle** of obligations selected from a canonical catalog based on risk class, data sensitivity, and regulatory scope. A typical healthcare bundle is 6–10 obligations.

Every enforcement check emits a typed **event** into an append-only **ledger**. The ledger is the source of truth. A **Scoreboard** is a materialized view over the ledger showing live status per (agent × obligation). Five structured-data products derive from the ledger (§16). An **Attestation** is a signed point-in-time projection of the Scoreboard — a receipt for a moment in the ledger, not a standalone document.

**Why this wins:**
- **Predicates are legally meaningful.** Courts and regulators reason about obligations, not scores. EU AI Act Art. 9 asks whether a risk-management system is in place, not what its composite score is.
- **Small catalog = buyer comprehension.** A hospital CRO can hold 10 things in memory.
- **Continuous by construction.** Every agent action emits events; the Scoreboard updates; violations alert. No quarterly surveys.
- **The data compounds.** History, benchmarks, and drift signatures become defensible moats at 20+ customers.

---

## 2. The 11 canonical obligations

All obligations are at `implemented` maturity. See §3 for the maturity ladder definition.

| ID | Name | The obligation (predicate) | Satisfies |
|---|---|---|---|
| **O1** | Bounded Action Space | The agent SHALL NOT invoke any tool, API, or action not declared in its signed Action Manifest at deployment time. | EU AI Act Art. 9, 14; ISO/IEC 42001 A.6.2.6; NIST AI RMF GOVERN 1.6; OWASP LLM07; HIPAA §164.312(a)(1) |
| **O2** | Sensitive Data Confinement | The agent SHALL NOT emit PHI, PII, or other classified data to any destination not listed in its Data Flow Manifest. | HIPAA §164.514, §164.312(e), §164.308(a)(4); GDPR Art. 5, 25, 32, 44; EU AI Act Art. 9, 10; OWASP LLM02; CCPA §1798.100 |
| **O3** | Content Safety | The agent SHALL NOT produce output that violates the deployment's Content Safety Policy, as measured by the configured detector suite on every response. | EU AI Act Art. 5, 9, 13; ISO/IEC 42001 A.6; NIST AI RMF GOVERN 6.1; OWASP LLM01, LLM02, LLM06; ACA §1557 |
| **O4** | Fairness Non-Regression | The agent SHALL NOT exceed the deployment's declared demographic parity and equalized odds gaps across protected attributes. | EU AI Act Art. 9, 10(2)(f); GDPR Art. 22; ACA §1557; NIST AI RMF MAP 5.1, MEASURE 2.5; ISO/IEC 42001 A.9 |
| **O5** | Grounded Outputs | For retrieval-augmented tasks, every factual claim in the agent's output SHALL be traceable to a cited source above the faithfulness threshold. | EU AI Act Art. 9, 13, 15; HIPAA §164.312(b); FDA 21 CFR Part 11, Part 820.30; GDPR Art. 22; NIST AI RMF MEASURE 2.6; OWASP LLM09 |
| **O6** | Goal Integrity | The agent SHALL refuse to pursue any objective not contained in its signed Goal Manifest. Multi-turn manipulation SHALL leave the manifest unchanged. | EU AI Act Art. 9, 15; NIST AI RMF GOVERN 6.1, MANAGE 2.2; OWASP LLM01; MITRE ATLAS AML.T0051, AML.T0054 |
| **O7** | Auditable Decisions | Every agent decision SHALL emit a trace conforming to the OpenTelemetry semantic convention for AI agents. Missing traces are violations. | EU AI Act Art. 12, 13; HIPAA §164.312(b), §164.308(a)(1); NIST AI RMF GOVERN 1.7, MEASURE 4.1; GDPR Art. 22; ISO/IEC 42001 Cl. 9; FDA 21 CFR Part 11 |
| **O8** | Human Oversight Integrity | Every agent action in a HITL-required class SHALL require a documented human decision before execution. Reviewer identity, decision, duration, and outcome SHALL be logged. | EU AI Act Art. 14; Joint Commission clinical decision support standards; NIST AI RMF GOVERN 1.7, MANAGE 2.4; ISO/IEC 42001 A.10; HIPAA §164.308(a)(3); FDA 21 CFR Part 820.30 |
| **O9** | Change Attestation Currency | No production deployment SHALL run a model, prompt, tool set, or knowledge base version for which the active Attestation is older than the Change Impact Matrix requires. | EU AI Act Art. 9, 72; ISO/IEC 42001 Cl. 9, A.7; NIST AI RMF GOVERN 1.2, MANAGE 1.4; FDA 21 CFR Part 820.30 |
| **O10** | Operational Invariants | The deployment SHALL maintain p99 latency ≤ declared ceiling, SLI/SLO for declared dependencies, and zero capability-envelope excursions (SPC Western Electric rules). | EU AI Act Art. 9, 15; ISO/IEC 42001 Cl. 9, A.9; NIST AI RMF MANAGE 3.1, MEASURE 4.1; HIPAA §164.308(a)(7) |
| **O11** | User Interface Transparency | In every interaction, the agent SHALL (a) disclose its AI nature and operational scope before or at first use, and (b) invoke an uncertainty fallback when model confidence falls below the deployment's declared threshold. For retrieval-sourced claims, source attribution SHALL be present. User override controls SHALL be available for any AI suggestion. Calibration to user type (Internal-General, Internal-Expert, External) governs the form of disclosure, not whether disclosure is required. **Pre-requisite:** the deployment's HAI taxonomy classification (§27.1) is determined at Scope phase before O11 applicability is evaluated. | EU AI Act Art. 13, 52; GDPR Art. 13, 22; NIST AI RMF GOVERN 1.3, 1.7; ISO/IEC 42001 A.8; HAI Framework v2 Module E; FTC AI Guidelines; OWASP LLM09; ACA §1557 |

**Selection rule:** Every deployment holds O1, O3, O7, O9, O10 at a minimum. O11 is required for any deployment with an External user type (HAI taxonomy §27.1). Others apply per the Bundle Selection Matrix in §6.

**Catalog growth:** New obligations require governance-committee action and a version bump. Existing obligations never silently change their predicate — any change produces a new obligation ID with a supersedes link.

### Obligation maturity ladder

Each obligation carries a `maturity` classification that separates what the bundle declares from what is operationally enforced:

| Level | Meaning |
|---|---|
| `implemented` | Enforcement logic is live; PASS/FAIL results are authoritative |
| `planned` | Enforcement is scheduled; checks emit NA (deferred) until the infrastructure is operational |
| `declared` | Obligation is catalogued; no enforcement timeline committed |

`compliance_score()` counts only `implemented` obligations toward the numerator. `implementation_coverage()` is the fraction of bundle obligations at `implemented` maturity. As of v0.5, all 11 obligations are `implemented`: `compliance_score() = 1.0`, `implementation_coverage() = 1.0`.

---

## 3. Four enforcement points

The same predicate is checked at four different stages, against four different artifact types.

| Point | When it runs | What it checks | Event cadence |
|---|---|---|---|
| **G-BUILD** | Every commit / CI run | Static properties of the agent artifact: manifest presence, schema conformance, declaration completeness, instrumentation wiring | Every commit |
| **G-TEST** | Before promotion; weekly regression | Behavioral properties against a test dataset: does the agent actually honor the predicate on 500+ held-out inputs? | Pre-release + weekly |
| **G-RUN** | Every agent invocation in production | Live policy decision or monitor: does this specific action honor the predicate? | Every agent run |
| **G-DELEGATE** | Every inter-agent handoff in a multi-agent pipeline | Does the orchestrator correctly scope, attest, and propagate obligations to each subordinate agent? | Per subordinate handoff |

**G-DELEGATE** fires when an orchestrator agent delegates to a subordinate. It emits one ObligationEvent per obligation per handoff, recording: orchestrator identity, subordinate agent_id + version, the delegated obligation subset, and cryptographic evidence. The ledger thereby contains full pipeline provenance for multi-agent workflows — a requirement for EU AI Act Art. 14 oversight and Joint Commission audit trails.

---

## 4. Enforcement matrix — obligation × point

G-TEST cells include pass/fail thresholds. All thresholds are grounded in AgenticAI Eval Framework v1.0 measurement profiles and Watchtower internal calibration data.

| Obligation | G-BUILD | G-TEST | G-RUN | G-DELEGATE |
|---|---|---|---|---|
| **O1** Bounded Action Space | Action Manifest exists + signed; static call-graph analysis proves no undeclared tool reachable | AgentBench tool-selection golden set (200 tasks); adversarial prompts attempting undeclared tools; **threshold: first-attempt accuracy ≥ 0.90; API schema conformance ≥ 0.99** (Pact.io) | OPA policy engine blocks any tool call not in manifest; violations logged | Verifies subordinate agents only inherit the subset of tools scoped to their delegated task |
| **O2** Sensitive Data Confinement | Data Flow Manifest exists; taint analysis on prompt templates + tool specs; **(RAG deployments) Knowledge FAIR pre-ingestion PHI scan required — FAIR PHI flag = FAIL blocks KB ingest** | Privacy & Redaction Suite (500 records); Presidio/RegexDetector on outputs; **threshold: re-identification risk < 0.01** (NIST SP 800-188 / ARX); **0 PHI leaks on Category 5 dataset** | Egress gate with PHI detector on every response; hard block on match | Ensures PHI field scope is not silently expanded when the orchestrator delegates to a subordinate |
| **O3** Content Safety | Content Policy declared with detector suite + thresholds; **(RAG deployments) Knowledge FAIR conflict detection and disclaimer/agent-script scan required before KB ingest — FAIR conflict flag = FAIL blocks ingest** | DeepEval + Giskard + AgentHarm on Adversarial Test Suite (300 prompts); **threshold: safety adherence ≥ 0.98**; **LLM-as-Judge `judge_content_safety` required (§26); human-judge κ ≥ 0.60** | Live detector on every response; block or redact per policy | Applies the same classifier to subordinate agent responses, not just the orchestrator output |
| **O4** Fairness Non-Regression | Protected-attribute schema declared; eval dataset categorized; **(RAG deployments) Knowledge FAIR metadata audit surfaces demographic representation gaps in KB — flagged KBs must be reviewed before they contribute to protected-attribute decisions** | Fairlearn demographic parity + equalized odds on held-out test set; **thresholds: demographic parity gap ≤ 0.05; equalized odds gap ≤ 0.05** | Monthly drift scan on production outputs stratified by protected attribute; proxy-based monitoring where protected attributes unavailable at inference time (see Open Question 5 in §23) | Surfaces fairness signals from subordinate pipelines that handle demographic-sensitive decisions |
| **O5** Grounded Outputs | Retrieval config pinned; KB provenance declared; **Knowledge FAIR readiness check required (§30): FAIR readiness score ≥ deployment threshold across metadata, conflict, staleness, chunking quality checks — FAIR FAIL blocks O5 G-BUILD PASS; FAIR run ID recorded in evidence_uri** | RAGAS faithfulness + context relevance on 500-query benchmark + Golden Dataset (§28); **thresholds: faithfulness ≥ 0.90; citation precision ≥ 0.95**; **LLM-as-Judge `judge_factual_grounding` required (§26); human-judge κ ≥ 0.60**; Memory Freshness: ≤ 5% stale entries; **FAIR staleness score ≤ 5% stale entries (aligns with Memory Freshness gate)** | Live faithfulness score on sampled responses; source-citation completeness on every RAG response | Validates that retrieved context is passed to subordinates and grounding is re-checked on their output |
| **O6** Goal Integrity | Goal Manifest signed; goal-distractor test configured | 100-trajectory CAMEL / Beyond-Task-Completion adversarial suite; **threshold: goal-alignment score ≥ 0.85 across suite**; **LLM-as-Judge `judge_goal_alignment` required (§26); human-judge κ ≥ 0.60**; capability envelope baseline frozen at G-TEST pass | Runtime goal-alignment check per step; SPC on trajectory drift; capability envelope delta monitored against G-TEST baseline; alert if delta exceeds 10% | Re-evaluates goal alignment on subordinate outputs to detect orchestration-layer goal drift |
| **O7** Auditable Decisions | OTel instrumentation required in CI lint; schema validation on span attributes | Trace completeness on 1000-event replay dataset; **thresholds: completeness ≥ 0.95; log schema compliance ≥ 0.99** | Continuous trace completeness monitor; missing-attribute alert within 5 min | Writes one G-DELEGATE event per obligation per subordinate handoff, providing full pipeline provenance |
| **O8** Human Oversight Integrity | HITL workflow wired; reviewer pool configured | Calibration: 50-case labeled library; **threshold: Cohen's κ ≥ 0.75** among active reviewers; block reviewer from high-risk reviews if κ < 0.60; **OVA Score ≥ 0** (§27.4) | Review-duration SPC; monthly κ recomputation; override quality sampling | Propagates the HITL flag from orchestrator to subordinate so high-stakes tasks are not silently auto-approved in the sub-pipeline |
| **O9** Change Attestation Currency | CIM rules configured per change type; semver enforced; **KB version change triggers FAIR re-evaluation (§30) before CIM change-class determination — FAIR score regression on new KB version = MAJOR-class CIM event, requiring O5 re-evaluation before Attestation renewal** | **Simulation-based test:** inject a synthetic CIM MAJOR-class change event; **threshold: scoped re-evaluation pipeline completes within 48h; Attestation currency ≤ 30 days** | CI/CD gate blocks deploy if Attestation out of date; time-based expiry enforced | Checks that subordinate agent versions are attested independently — an orchestrator's attestation does not cover its subordinates |
| **O10** Operational Invariants | SLO targets declared; capability baselines captured | Latency eval on 1000-request window; **thresholds: p99 ≤ 2×p50; dependency health ≥ 0.99**; no SPC out-of-control signals during eval window | Prometheus + SPC chart; alert on Western Electric out-of-control rules | Applies invariant checks to subordinate spans so a budget-busting sub-agent is caught before it inflates the orchestrator's totals |
| **O11** User Interface Transparency | Transparency Manifest exists (disclosure schema, confidence threshold, uncertainty fallback configured); interaction monitoring instrumented; user override control declared | Disclosure rate ≥ 0.95 on adversarial identity-probing prompts; uncertainty fallback triggered correctly when confidence < declared threshold; **3 LLM-as-Judge judges required (§26): `judge_ai_nature_disclosure`, `judge_source_attribution` (RAG deployments only), `judge_uncertainty_fallback`; human-judge κ ≥ 0.60 for each** | Live disclosure rate monitoring; session-level misunderstanding signal rate ≤ 10%; recovery rate ≥ 80% (§27.5); OVA Score ≥ 0; **S-TIAS ≥ 3.5/5.0** measured in first 30-day production window (early warning signal, not a deploy gate) | Ensures end-user-facing outputs from subordinate agents carry the same disclosure requirements as orchestrator outputs |

### SLO windows

Staleness thresholds per enforcement point (tunable per tenant):

| Point | Default SLO | If stale → status |
|---|---|---|
| G-BUILD | 7 days | AMBER |
| G-TEST | 14 days | AMBER |
| G-RUN | 1 hour | AMBER |
| G-DELEGATE | 1 hour | AMBER |

O11 G-RUN has an additional 30-day window for the S-TIAS early-warning measurement. This is not an SLO gate — it is an observational window that, if missed, emits an AMBER advisory event.

### Sampling and retention

| Point | Sample rate | Hot retention | Cold retention |
|---|---|---|---|
| G-BUILD | 100% | 90 days | 7 years |
| G-TEST | 100% | 180 days | 7 years |
| G-RUN PASS | 100% tail, 1% head-sampled on unchanged policies | 30 days | 7 years |
| G-RUN FAIL / WAIVED | 100% always | 7 years | 7 years |
| G-DELEGATE | 100% | 90 days | 7 years |

Head sampling on G-RUN PASS keeps warehouse cost linear in violations, not in traffic.

---

## 5. Personas

Four roles interact with the AIGov framework at different enforcement points. Each has primary accountability over a subset of obligations and activities at each phase.

| Persona | Primary obligations | Focus |
|---|---|---|
| AI Researcher | O3, O4, O5, O6 | Evaluation framework · thresholds · datasets |
| AI Engineer | O1, O2, O5, O7, O9, O10 | Implementation · CI gates · observability |
| Product Manager | O1, O3, O6, O8, O11 | Use case scope · compliance health · escalation |
| Business Executive | O2, O4, O7, O8, O9 | Regulatory accountability · sign-off · audit |

### Ownership matrix — obligation × persona

| Obligation | Researcher | Engineer | PM | Executive |
|---|---|---|---|---|
| O1 Bounded Action Space | | ✓ | ✓ | |
| O2 Sensitive Data Confinement | | ✓ | | ✓ |
| O3 Content Safety | ✓ | | ✓ | |
| O4 Fairness Non-Regression | ✓ | | | ✓ |
| O5 Grounded Outputs | ✓ | ✓ | | |
| O6 Goal Integrity | ✓ | | ✓ | |
| O7 Auditable Decisions | | ✓ | | ✓ |
| O8 Human Oversight Integrity | | | ✓ | ✓ |
| O9 Change Attestation Currency | | ✓ | | ✓ |
| O10 Operational Invariants | | ✓ | | |
| O11 User Interface Transparency | | | ✓ | |

### Persona activities per enforcement point

**AI Researcher**

| Phase | Activity |
|---|---|
| G-BUILD | Define GoalManifest and FairnessManifest — goal statements, prohibited behaviors, parity gap thresholds, and alignment thresholds. Design the golden dataset schema for each use case. |
| G-TEST | Curate golden datasets and adversarial test suites (30+ cases per use case). Analyze demographic parity gaps across protected attributes. Set and justify alignment threshold values. |
| G-RUN | Monitor obligation event streams for behavioral drift in production. Refine thresholds based on live data. Publish updated adversarial case sets when new manipulation patterns emerge. |
| G-DELEGATE | Review obligation event coverage across multi-agent pipelines. Ensure subordinate agents inherit ObligationBundles appropriate to their task scope, not just the orchestrator's full bundle. |

**AI Engineer**

| Phase | Activity |
|---|---|
| G-BUILD | Implement ObligationBundle and wire DataFlowManifest, GoalManifest, and FairnessManifest into the deployment pipeline. Ensure `check_build()` passes on every deploy artifact. |
| G-TEST | Run the evaluation pipeline in CI — golden dataset scoring, judge scoring, fairlearn parity checks. Fix failing obligations. Maintain the pytest suite covering all four enforcement points. |
| G-RUN | Operate the event ledger and span store. Respond to FAIL and DEFERRED alerts. Keep tracing, latency, and token budgets within declared Operational Invariants (O10). |
| G-DELEGATE | Implement OrchestratorAgent with G-DELEGATE event emission. Configure ledger_sink on the orchestrator so every subordinate handoff is written to the ledger. Verify each subordinate's ObligationBundle matches its task scope. |

**Product Manager**

| Phase | Activity |
|---|---|
| G-BUILD | Approve the use case definition and risk classification. Confirm PHI field scope, allowed egress destinations, and content-safety thresholds are appropriate for the product context. |
| G-TEST | Review compliance scorecard before production sign-off. Prioritize obligation failures by user-impact severity. Ensure Human Oversight (O8) and UI Transparency (O11) tests pass. |
| G-RUN | Monitor the Scoreboard dashboard daily. Track and triage the Human Oversight review queue. Escalate sustained FAIL patterns to engineering and flag regulatory risk to leadership. |
| G-DELEGATE | Approve which subordinate agents an orchestrator may delegate to. Confirm the G-DELEGATE audit trail covers the full multi-agent workflow so regulatory reporting reflects the complete pipeline. |

**Business Executive**

| Phase | Activity |
|---|---|
| G-BUILD | Sign off on the DataFlowManifest — which PHI fields the agent touches and where data is permitted to flow. Approve the AI use case for production under EU AI Act, HIPAA, and ACA 1557. |
| G-TEST | Review the pre-production compliance scorecard. Ensure fairness gaps (O4) and audit completeness (O7) meet regulatory thresholds before granting deployment approval. |
| G-RUN | Review cryptographic audit trails (O7). Approve or escalate model change attestations (O9). Provide signed attestations to regulators. Authorize Human Oversight override decisions. |
| G-DELEGATE | Review G-DELEGATE ledger records to confirm full pipeline provenance — every orchestrator-to-subordinate handoff is captured. Use these records as evidence in regulatory audits of multi-agent workflows. |

---

## 6. Bundle Selection Matrix

| Deployment profile | Baseline | Add |
|---|---|---|
| Any production deployment | O1, O3, O7, O9, O10 | — |
| Processes PHI / PII | | + O2 |
| Retrieval-augmented (RAG) | | + O5 |
| Uses HITL workflow | | + O8 |
| Fairness-regulated outcomes (hiring, credit, clinical triage) | | + O4 |
| Autonomous pattern (B6/B7) | | + O6 |
| Vendor / black-box agent | baseline | observable-only variants per §7 |
| External user type (HAI taxonomy) | | + O11 |
| Internal-Expert user type + Elevated risk | | + O11 |
| Internal-Expert or Internal-General + Minimal risk | | O11 Deferred¹ |

¹ **Deferred:** O11 is not required at initial deployment but MUST be included at the next MAJOR CIM event if: the agent is promoted to Elevated risk, the user base expands to External, or 12 months elapse. Deferred O11 is not an obligation status in the ledger — the Attestation records O11 as "N/A — Deferred".

> **HAI User Taxonomy (§27):** All deployments are classified along three axes — Risk Level (Minimal/Elevated), AI Interaction Type (Tool/Mediator/Conversation Partner), and User Type (Internal-General, Internal-Expert, External). This classification drives O11 bundle inclusion and O8 HITL tier selection. Classification is captured as a required field in the Scope phase (§19 Phase 1), before O11 applicability is evaluated.

**Current bundle versions:**

| Bundle | ID | Obligations |
|---|---|---|
| Standard | `standard-v2` | O1, O3, O7, O9, O10 |
| Healthcare (external member-facing) | `healthcare-v5` | O1, O2, O3, O5, O7, O8, O9, O10, O11 |
| External | `external-v3` | O1, O3, O7, O9, O10, O11 |

**Healthcare default bundle:** O1, O2, O3, O5, O7, O8, O9, O10, O11. Nine obligations. Fits on one page.

---

## 7. Vendor / black-box deployments

Vendor deployments hold the baseline bundle using **observable-only** enforcement variants:

- **G-BUILD → Documentation Evidence.** Vendor model card scored against Foundation Model Transparency Index schema (≥ 50/100 standard, ≥ 70/100 safety-critical).
- **G-TEST → External Behavioral Testing.** AgentHarm, Adversarial Test Suite, and RAGAS benchmarks run against the live vendor endpoint.
- **G-RUN → Egress-layer Enforcement.** The enterprise runs its own detectors, policy engine, and audit logging on the network boundary in front of the vendor API.
- **G-DELEGATE → N/A.** Vendor black-box agents cannot be subordinates in a G-DELEGATE chain — the subordinate's internal workings must be observable to emit a valid G-DELEGATE event.

Contractual clauses become **Attestation preconditions**: vendor contract must include right-to-audit, 72-hour incident disclosure, and 30-day material-change notice. Absence blocks Attestation issuance regardless of test results.

Same 11 obligations. Different enforcement. One framework.

---

## 8. Crosswalk — 34 criteria → 11 obligations

Nothing from AgenticAI Eval Framework v1.0 is thrown away. The 34 criteria become **measurement techniques** producing evidence for the 11 obligations.

| Obligation | v1.0 criteria absorbed | Measurement techniques |
|---|---|---|
| O1 | 1.1.3, 2.3.1, 2.3.2, 2.4.1, 2.4.2, 3.1.3 | AgentBench tool-selection (≥ 0.90), Pact.io contract testing (≥ 0.99), QuadSentinel handoff tracking, SPC capability envelope |
| O2 | 1.2.1, 1.2.2, 1.2.3 | Presidio / RegexDetector, NIST SP 800-188 re-identification (< 0.01), differential privacy accounting |
| O3 | 1.1.1, 1.1.5 | DeepEval, Giskard, AgentHarm (safety adherence ≥ 0.98), Perspective API, MLCommons AI Safety; LLaJ `judge_content_safety` (§26) |
| O4 | 1.1.2 | Fairlearn, IBM AIF360; demographic parity gap ≤ 0.05; equalized odds gap ≤ 0.05 |
| O5 | 2.1.1, 2.1.2, 2.1.3, 2.5.1 | RAGAS faithfulness (≥ 0.90) + citation precision (≥ 0.95), TruLens, Golden Dataset (§28), Memory Freshness ≤ 5% stale; LLaJ `judge_factual_grounding` (§26) |
| O6 | 1.3.1, 1.3.2, 1.3.3 | CAMEL, Beyond-Task-Completion (goal-alignment ≥ 0.85), multi-turn adversarial suites, OWASP LLM01; LLaJ `judge_goal_alignment` (§26); capability envelope baseline (SPC) |
| O7 | 1.1.4, 3.1.1, 3.1.2 | OpenTelemetry semantic conventions for AI agents (completeness ≥ 0.95; schema compliance ≥ 0.99), NIST SP 800-92 |
| O8 | 3.2.3 | Cohen's κ calibration (κ ≥ 0.75 reviewers; κ ≥ 0.60 human-judge); review duration SPC; override quality sampling; OVA Score (§27.4); HAI Module C/D metrics |
| O9 | 3.3.3 | Change Impact Matrix, semantic versioning, MLflow-style registry; CIM simulation test (48h completion) |
| O10 | 3.2.1, 3.2.2, 3.3.1, 3.3.2, 3.1.3 | SRE SLI/SLO (p99 ≤ 2×p50; dependency health ≥ 0.99), Prometheus histograms, SPC Western Electric rules, MITRE ATLAS |
| O11 | 1.1.4 (Action Transparency & Identity Disclosure) | HAI SUS, S-TIAS (≥ 3.5/5.0 early warning), CSAT, NPS; disclosure rate ≥ 0.95; misunderstanding rate ≤ 10%; recovery rate ≥ 80%; OVA Score ≥ 0; LLaJ judges: `judge_ai_nature_disclosure`, `judge_source_attribution`, `judge_uncertainty_fallback` (κ ≥ 0.60 each per §26) |

**Value criteria (4.1.x, 4.2.x)** become **business outcomes** tracked alongside the ledger but not gating. Adoption, cost, efficiency are important but are not obligations.

**Reasoning Quality (2.2.1) and Error Recovery (4.1.3)** become **quality targets** — reported, not gating.

---

# PART II — Data Platform

## 9. Data model overview

```
  Emitters                 Ingestion             Warehouse                Products
  ────────                 ─────────             ─────────                ────────
  CI (G-BUILD)     ─┐                      ┌─ fact_obligation_event ─┐
  Test harness     ─┼─► ingestion API ─►   │  dim_agent              ├─► Scoreboard UI
  praktor governance│    /v1/events        │  dim_obligation         ├─► Event Stream API
  OTel collector   ─┘    Kafka: ob.events  │  dim_cim_version        ├─► Benchmarks
                                           │  fact_status_snapshot   ├─► Drift signatures
                                           └─ fact_violation        ─┴─► Evidence packs
```

Grain of the core fact: **one row per enforcement event per (agent, obligation, enforcement_point)**. Everything else is a materialized view, a rollup, or a dimension.

---

## 10. Event Schema v1.1

Canonical JSON, versioned with `schema_version`. Every emitter produces this shape.

```json
{
  "schema_version": "1.1",
  "event_id": "01HX7K8QYR4ZVP6GQ9F2E3C0NB",
  "event_ts": "2026-04-14T13:22:07.431Z",
  "ingest_ts": "2026-04-14T13:22:07.612Z",

  "tenant_id": "acme-health",
  "agent_id": "clinical-triage-v2",
  "agent_version": "2.3.1",
  "agent_pattern": "B3",
  "deployment_env": "prod",

  "cim_version": "2.3.0",
  "bundle_id": "healthcare-v5",

  "obligation_id": "O2",
  "enforcement_point": "G-RUN",
  "measurement_technique": "1.2.1",

  "obligation_maturity": "implemented",
  "predicate_result": "PASS",
  "severity": "info",
  "waiver_id": null,

  "evidence": {
    "uri": "s3://aigov-evidence/acme-health/2026/04/14/01HX7K8QYR.json",
    "sha256": "9f4e...c1",
    "size_bytes": 2841,
    "redacted": true
  },

  "reviewer": null,
  "regulatory_tags": ["HIPAA.164.514", "EU_AI_ACT.Art10", "GDPR.Art32"],
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "span_id": "00f067aa0ba902b7",

  "source": {
    "kind": "praktor_governance",
    "version": "0.6.0",
    "host": "agent-worker-07"
  }
}
```

### Field reference

| Field | Type | Notes |
|---|---|---|
| `schema_version` | string | SemVer. Breaking changes require new ingestion route. |
| `event_id` | ULID | Monotonic, sortable, globally unique. |
| `event_ts` | RFC3339 | When the check fired. Source of truth for ordering. |
| `ingest_ts` | RFC3339 | When the warehouse received it. For lag monitoring. |
| `tenant_id` | string | Customer. Partition key for multi-tenant isolation. |
| `agent_id` | string | Stable identifier for the agent under governance. |
| `agent_version` | string | SemVer of the agent build. |
| `agent_pattern` | enum B1–B7 | Drives bundle selection. |
| `deployment_env` | enum | `dev`, `staging`, `canary`, `prod`. |
| `cim_version` | string | Change Impact Matrix version active at event time. |
| `bundle_id` | string | Which obligation bundle is in force. |
| `obligation_id` | enum O1–O11 | From §2. |
| `enforcement_point` | enum | `G-BUILD`, `G-TEST`, `G-RUN`, `G-DELEGATE`. |
| `measurement_technique` | string | v1.0 criterion id (e.g. `1.2.1`). Preserves crosswalk. |
| `obligation_maturity` | enum | Maturity level stamped at event creation: `implemented`, `planned`, `declared`. Read from the obligation class definition at emit time. Used by `scoreboard_as_of()` for historical reconstruction. |
| `predicate_result` | enum | `PASS`, `FAIL`, `WAIVED`, `NA`. |
| `severity` | enum | `info`, `low`, `medium`, `high`, `critical`. |
| `waiver_id` | nullable string | Reference to an active waiver record. |
| `evidence.uri` | string | Immutable blob (S3/MinIO). Contains redacted payload + check trace. |
| `evidence.sha256` | hex | Hash for tamper detection. |
| `reviewer` | nullable object | Human reviewer identity, if applicable. |
| `regulatory_tags` | string[] | Machine-readable regulator citations. Drives evidence packs. Tag format: `FRAMEWORK.ControlID`. Supported vocabularies: `EU_AI_ACT.*`, `HIPAA.*`, `GDPR.*`, `ISO42001.*`, `NIST_AI_RMF.*`, `FDA.*`, `OWASP.*`, `MITRE_ATLAS.*`, `ACA.*`, `CCPA.*`, `SOC2.*`, `HITRUST.*`. See §10.4 for full vocabulary and obligation crosswalk. |
| `trace_id` / `span_id` | hex | OTel correlation to the underlying agent run. |
| `source` | object | Which emitter produced the event. |

**Invariants:**
- Events are **append-only**. Corrections are new events that supersede.
- `evidence.uri` must resolve for 7 years (regulatory retention). Bucket is WORM.
- `(tenant_id, event_id)` is globally unique.

### 10.4 `regulatory_tags` vocabulary

Tag format: `FRAMEWORK.ControlID`. Tags are additive — multiple frameworks can appear on a single event.

| Framework | Tag prefix | Covered controls |
|---|---|---|
| EU AI Act | `EU_AI_ACT.*` | Art. 5, 9, 10, 12, 13, 14, 15, 52, 72 |
| HIPAA | `HIPAA.*` | §164.308(a)(1), §164.308(a)(3), §164.308(a)(4), §164.308(a)(7), §164.312(a)(1), §164.312(b), §164.312(e), §164.514 |
| GDPR | `GDPR.*` | Art. 5, 13, 22, 25, 32, 44 |
| ISO/IEC 42001 | `ISO42001.*` | Cl. 9; A.6, A.6.2.6, A.7, A.8, A.9, A.10 |
| NIST AI RMF | `NIST_AI_RMF.*` | GOVERN 1.2, 1.3, 1.6, 1.7, 6.1; MANAGE 1.4, 2.2, 2.4, 3.1; MAP 5.1; MEASURE 2.5, 2.6, 4.1 |
| FDA | `FDA.*` | 21 CFR Part 11; 21 CFR Part 820.30 |
| OWASP LLM Top 10 | `OWASP.*` | LLM01, LLM02, LLM06, LLM07, LLM09 |
| MITRE ATLAS | `MITRE_ATLAS.*` | AML.T0051, AML.T0054 |
| ACA | `ACA.*` | §1557 |
| CCPA | `CCPA.*` | §1798.100 |
| Knowledge FAIR (Watchtower/KBS) | `FAIR.*` | METADATA, CONFLICT, STALENESS, CHUNKING, PHI, DOC_QUALITY |
| SOC 2 (AICPA TSC 2017 rev.2022) | `SOC2.*` | CC6.1, CC6.3, CC6.7, CC7.2, CC7.3, CC8.1, A1.1, A1.2, P5.1 |
| HITRUST CSF v11.3 | `HITRUST.*` | 01.b, 01.c, 02.e, 09.aa, 09.ad, 09.s, 10.k, 12.c, 13.j |

**Full obligation crosswalk** — all frameworks:

| Obligation | EU AI Act | HIPAA | GDPR | ISO/IEC 42001 | NIST AI RMF | FAIR gate | Other |
|---|---|---|---|---|---|---|---|
| **O1** Bounded Action Space | Art. 9, 14 | §164.312(a)(1) | — | A.6.2.6 | GOVERN 1.6 | — | OWASP.LLM07 |
| **O2** Sensitive Data Confinement | Art. 9, 10 | §164.514, §164.312(e), §164.308(a)(4) | Art. 5, 25, 32, 44 | — | — | PHI scan (blocks ingest) | OWASP.LLM02; CCPA §1798.100 |
| **O3** Content Safety | Art. 5, 9, 13 | — | — | A.6 | GOVERN 6.1 | CONFLICT, DOC_QUALITY (blocks ingest) | OWASP.LLM01, LLM02, LLM06; ACA §1557 |
| **O4** Fairness Non-Regression | Art. 9, 10(2)(f) | — | Art. 22 | A.9 | MAP 5.1; MEASURE 2.5 | METADATA (demographic representation review) | ACA §1557 |
| **O5** Grounded Outputs | Art. 9, 13, 15 | §164.312(b) | Art. 22 | — | MEASURE 2.6 | METADATA, CONFLICT, STALENESS, CHUNKING (all required; FAIL blocks G-BUILD PASS) | FDA Part 11, Part 820.30; OWASP.LLM09 |
| **O6** Goal Integrity | Art. 9, 15 | — | — | — | GOVERN 6.1; MANAGE 2.2 | — | OWASP.LLM01; MITRE ATLAS AML.T0051, AML.T0054 |
| **O7** Auditable Decisions | Art. 12, 13 | §164.312(b), §164.308(a)(1) | Art. 22 | Cl. 9 | GOVERN 1.7; MEASURE 4.1 | — | FDA Part 11 |
| **O8** Human Oversight Integrity | Art. 14 | §164.308(a)(3) | — | A.10 | GOVERN 1.7; MANAGE 2.4 | — | FDA Part 820.30; Joint Commission CDS |
| **O9** Change Attestation Currency | Art. 9, 72 | — | — | Cl. 9; A.7 | GOVERN 1.2; MANAGE 1.4 | STALENESS, CHUNKING (score regression = MAJOR CIM event) | FDA Part 820.30 |
| **O10** Operational Invariants | Art. 9, 15 | §164.308(a)(7) | — | Cl. 9; A.9 | MANAGE 3.1; MEASURE 4.1 | — | — |
| **O11** UI Transparency | Art. 13, 52 | — | Art. 13, 22 | A.8 | GOVERN 1.3, 1.7 | — | FTC AI Guidelines; HAI v2 Module E; OWASP.LLM09; ACA §1557 |

**SOC 2 crosswalk** (CPA firm validation required before use as customer-facing evidence):

| Obligation | SOC 2 controls |
|---|---|
| O1 Bounded Action Space | CC6.1, CC6.3 |
| O2 Sensitive Data Confinement | CC6.7, P5.1 |
| O3 Content Safety | CC7.2 |
| O4 Fairness Non-Regression | CC7.2 |
| O5 Grounded Outputs | CC7.2 |
| O6 Goal Integrity | CC6.1, CC6.3 |
| O7 Auditable Decisions | CC7.2, CC7.3 |
| O8 Human Oversight Integrity | CC6.3 |
| O9 Change Attestation Currency | CC8.1 |
| O10 Operational Invariants | CC7.2, A1.1, A1.2 |
| O11 UI Transparency | P5.1 |

**HITRUST CSF crosswalk** (CCSFP assessor validation required before use as customer-facing evidence):

| Obligation | HITRUST controls |
|---|---|
| O1 Bounded Action Space | 01.c, 12.c |
| O2 Sensitive Data Confinement | 01.b, 09.s |
| O3 Content Safety | 09.s |
| O4 Fairness Non-Regression | 09.s |
| O5 Grounded Outputs | 09.aa |
| O6 Goal Integrity | 01.c |
| O7 Auditable Decisions | 09.aa, 09.ad, 13.j |
| O8 Human Oversight Integrity | 01.b, 02.e |
| O9 Change Attestation Currency | 10.k |
| O10 Operational Invariants | 09.s |
| O11 UI Transparency | 02.e |

> **Validation requirement:** The SOC 2 and HITRUST crosswalk mappings above are engineering-level drafts. A licensed CPA firm (SOC 2) and a HITRUST CCSFP assessor must validate the obligation→control mapping before these tags are used as customer-facing compliance evidence artifacts. The underlying event data is authoritative; only the claim that a given event satisfies a specific control requires auditor sign-off.

---

## 11. Status state machine

Status is **derived**, never stored as ground truth. Computed from latest events per key.

```
        ┌────────────────────────────────────────────┐
        ▼                                            │
   ┌─────────┐    latest FAIL     ┌─────────┐        │
   │  GREEN  │ ─────────────────► │   RED   │        │
   │         │                    │         │        │
   │ all 4   │ ◄───── passing     │ any     │        │
   │ points  │      retest        │ point   │        │
   │ PASS &  │                    │ FAIL    │        │
   │ fresh   │                    └─────────┘        │
   └─────────┘                         │             │
        │                              │             │
        │ stale evidence               │ waiver      │
        │ (> SLO)                      │ issued      │
        ▼                              ▼             │
   ┌─────────┐                    ┌─────────┐        │
   │  AMBER  │ ──── retest ──────►│  AMBER  │────────┘
   │ (stale) │                    │(waived) │
   └─────────┘                    └─────────┘

   NA (not in bundle) ─► GREY (visible but not scored)
```

**Rules:**
- **GREEN**: every required enforcement point has a PASS within its SLO window.
- **AMBER**: stale evidence OR active waiver OR WAIVED predicate.
- **RED**: any required enforcement point is the latest FAIL.
- **GREY**: obligation not in this agent's bundle. Displayed, not scored.

Status transitions themselves emit **derived events** into `fact_violation` for MTTR tracking.

---

## 12. Warehouse model

Target platform: any columnar warehouse (Snowflake / BigQuery / DuckDB / ClickHouse). dbt for transforms. Kafka → object storage → warehouse via Snowpipe-style ingestion.

### 12.1 Staging

```
stg_obligation_events_raw     -- JSON landing from Kafka / direct POST
stg_obligation_events         -- parsed, typed, validated
```

### 12.2 Fact tables

```sql
-- fact_obligation_event — grain: one row per enforcement event
create table fact_obligation_event (
  event_id              varchar primary key,
  event_ts              timestamp not null,
  ingest_ts             timestamp not null,
  tenant_id             varchar not null,
  agent_id              varchar not null,
  agent_version         varchar not null,
  cim_version           varchar not null,
  bundle_id             varchar not null,
  obligation_id         varchar not null,
  enforcement_point     varchar not null,
  measurement_technique varchar not null,
  predicate_result      varchar not null,
  severity              varchar,
  waiver_id             varchar,
  evidence_uri          varchar not null,
  evidence_sha256       varchar not null,
  reviewer_id           varchar,
  regulatory_tags       array<varchar>,
  trace_id              varchar,
  span_id               varchar,
  source_kind           varchar not null,
  source_version        varchar
)
partition by date(event_ts)
cluster by (tenant_id, agent_id, obligation_id);
```

```sql
-- fact_obligation_status_snapshot — grain: (tenant, agent, obligation, day)
create table fact_obligation_status_snapshot (
  snapshot_date     date not null,
  tenant_id         varchar not null,
  agent_id          varchar not null,
  obligation_id     varchar not null,
  status            varchar not null,       -- GREEN/AMBER/RED/GREY
  pass_events       int not null,
  fail_events       int not null,
  waived_events     int not null,
  na_events         int not null,
  pass_rate         float,
  last_evidence_ts  timestamp,
  mttr_seconds      int,
  primary key (snapshot_date, tenant_id, agent_id, obligation_id)
);
```

```sql
-- fact_violation — grain: one row per RED interval
create table fact_violation (
  violation_id       varchar primary key,
  tenant_id          varchar,
  agent_id           varchar,
  obligation_id      varchar,
  enforcement_point  varchar,
  opened_ts          timestamp,
  closed_ts          timestamp,
  mttr_seconds       int,
  root_cause_tag    varchar,
  opening_event_id   varchar,
  closing_event_id   varchar,
  severity           varchar,
  regulatory_tags    array<varchar>
);
```

### 12.3 Dimensions

```
dim_tenant                  -- customer, industry, region, plan tier, benchmark_opt_in
dim_agent                   -- agent_id, name, owner, pattern B1-B7, env, bundle_id
dim_obligation              -- O1..O11, predicate text, default bundles
dim_bundle                  -- bundle_id, name, obligation set, industry
dim_enforcement_point       -- G-BUILD/G-TEST/G-RUN/G-DELEGATE metadata
dim_measurement_technique   -- crosswalk to v1.0 criterion ids (all 34)
dim_cim_version             -- cim_version, semver parts, change summary
dim_reviewer                -- human reviewers, credentials, advisory role
dim_date                    -- calendar
dim_regulation              -- regulation_tag → article, clause, text, source
dim_knowledge_source        -- KB version → FAIR run ID, readiness score, staleness %, conflict count, PHI flag, ingest date
```

`dim_measurement_technique` is the crosswalk from v1.0 criteria to obligations. Referenced by every event — makes evidence packs automatic.

`dim_knowledge_source` is populated by the Knowledge FAIR pipeline (§30) on every KB ingest run. Each row is one KB version. O5 and O9 G-BUILD events join to `dim_knowledge_source` on `kb_version` to make FAIR readiness visible in evidence packs and the Scoreboard.

`dim_regulation` seed data covers: EU AI Act (Art. 5, 9, 10, 12, 13, 14, 15, 52, 72), HIPAA (§164.308 + §164.312 + §164.514), GDPR (Art. 5, 13, 22, 25, 32, 44), ISO/IEC 42001 (Cl. 9; A.6–A.10), NIST AI RMF (GOVERN, MANAGE, MAP, MEASURE), FDA (21 CFR Part 11 + Part 820.30), OWASP LLM Top 10 (LLM01/02/06/07/09), MITRE ATLAS (AML.T0051/T0054), ACA §1557, CCPA §1798.100, SOC 2 TSC 2017 rev.2022, HITRUST CSF v11.3. See §10.4 for the full obligation→control crosswalk.

### 12.4 dbt project layout

```
models/
├── staging/
│   ├── stg_obligation_events.sql
│   └── stg_waivers.sql
├── intermediate/
│   ├── int_events_enriched.sql
│   ├── int_status_per_key.sql            -- latest event per (agent, obligation, point)
│   └── int_status_transitions.sql        -- detects GREEN↔RED flips
├── marts/
│   ├── core/
│   │   ├── fact_obligation_event.sql
│   │   ├── fact_obligation_status_snapshot.sql
│   │   ├── fact_violation.sql
│   │   ├── dim_agent.sql
│   │   ├── dim_obligation.sql
│   │   ├── dim_bundle.sql
│   │   ├── dim_measurement_technique.sql
│   │   └── dim_cim_version.sql
│   ├── scoreboard/
│   │   ├── scoreboard_current.sql         -- live, agent × obligation matrix
│   │   ├── scoreboard_fleet.sql           -- tenant-wide rollup
│   │   └── scoreboard_trend_daily.sql
│   ├── benchmarks/
│   │   ├── benchmark_pass_rate_by_industry.sql
│   │   ├── benchmark_pass_rate_by_pattern.sql
│   │   └── benchmark_mttr_distribution.sql
│   ├── drift/
│   │   ├── drift_signal_obligation.sql
│   │   └── drift_signal_fleet.sql
│   └── evidence/
│       ├── evidence_pack_eu_ai_act_art12.sql
│       ├── evidence_pack_hipaa_164312b.sql
│       ├── evidence_pack_iso42001_cl9.sql
│       ├── evidence_pack_soc2_cc6_access_control.sql         -- SOC 2 CC6.x logical access
│       ├── evidence_pack_soc2_cc7_cc8_monitoring_change.sql  -- SOC 2 CC7/CC8/A1 monitoring + change
│       ├── evidence_pack_hitrust_09_audit_logging.sql        -- HITRUST 09.x audit logging domain
│       └── evidence_pack_fair_kb_quality.sql                 -- Knowledge FAIR KB readiness + O5 link
seeds/
│   ├── dim_regulation.csv                 -- regulation_tag → article, clause, text, source
│   └── dim_knowledge_source.csv           -- KB version → FAIR run, readiness score, staleness
tests/
├── assert_event_schema_version_known.sql
├── assert_cim_version_exists.sql
├── assert_no_orphan_obligation_ids.sql
├── assert_soc2_cc8_tags_on_o9_events.sql  -- O9 events must carry SOC2.CC8.1
└── assert_fair_gate_on_o5_build_events.sql -- O5 G-BUILD PASS events must reference a FAIR run ID
```

dbt tests enforce referential integrity on every ingest batch — a new event with an unknown `obligation_id`, `cim_version`, or `bundle_id` fails the run and pages on-call.

---

## 13. Scoreboard views

### 13.1 Live scoreboard (per agent × obligation)

```sql
-- models/marts/scoreboard/scoreboard_current.sql
{{ config(materialized='table') }}

with latest_per_point as (
  select
    tenant_id,
    agent_id,
    obligation_id,
    enforcement_point,
    max(event_ts)                       as last_event_ts,
    max_by(predicate_result, event_ts)  as last_result,
    max_by(severity, event_ts)          as last_severity,
    max_by(event_id, event_ts)          as last_event_id
  from {{ ref('fact_obligation_event') }}
  where event_ts >= current_timestamp - interval '30 days'
  group by 1,2,3,4
),

slo_windows as (
  select 'G-BUILD'    as enforcement_point, interval '7 days'  as slo union all
  select 'G-TEST',                          interval '14 days'      union all
  select 'G-RUN',                           interval '1 hour'       union all
  select 'G-DELEGATE',                      interval '1 hour'
),

stale_flagged as (
  select
    l.*,
    (current_timestamp - l.last_event_ts) > s.slo as is_stale
  from latest_per_point l
  join slo_windows s using (enforcement_point)
),

rolled as (
  select
    tenant_id,
    agent_id,
    obligation_id,
    case
      when bool_or(last_result = 'FAIL')                  then 'RED'
      when bool_or(last_result = 'WAIVED' or is_stale)    then 'AMBER'
      when bool_and(last_result = 'PASS')                 then 'GREEN'
      else 'AMBER'
    end                                                      as status,
    max(last_event_ts)                                       as last_evidence_ts,
    array_agg(distinct enforcement_point)
      filter (where last_result = 'FAIL')                    as failing_points,
    array_agg(distinct last_event_id)                        as latest_event_ids
  from stale_flagged
  group by 1,2,3
)

select
  r.*,
  b.bundle_id,
  case when ob.obligation_id = any(b.obligation_set) then false else true end as is_na
from rolled r
join {{ ref('dim_agent') }}      a  using (agent_id)
join {{ ref('dim_bundle') }}     b  on a.bundle_id = b.bundle_id
join {{ ref('dim_obligation') }} ob using (obligation_id);
```

One row per (agent, obligation). Refreshes every 60 seconds. Drives the customer-facing dashboard.

### 13.2 Fleet scoreboard

```sql
-- scoreboard_fleet.sql
select
  tenant_id,
  count(distinct agent_id)                                  as agents,
  sum(case when status = 'GREEN' then 1 else 0 end)         as green_cells,
  sum(case when status = 'AMBER' then 1 else 0 end)         as amber_cells,
  sum(case when status = 'RED'   then 1 else 0 end)         as red_cells,
  count(*)                                                  as total_cells,
  sum(case when status = 'GREEN' then 1 else 0 end)::float
    / nullif(count(*) filter (where not is_na), 0)          as fleet_pass_rate
from {{ ref('scoreboard_current') }}
group by tenant_id;
```

One number per customer. This is what the CISO looks at every morning.

### 13.3 Trend

```sql
-- scoreboard_trend_daily.sql
select
  snapshot_date,
  tenant_id,
  obligation_id,
  avg(pass_rate)                                                as fleet_pass_rate,
  sum(fail_events)                                              as fleet_fail_events,
  percentile_cont(0.9) within group (order by mttr_seconds)     as p90_mttr
from {{ ref('fact_obligation_status_snapshot') }}
group by 1,2,3;
```

Fuel for alerts like "O4 Fairness drifted 12% this week."

### 13.4 Historical reconstruction (scoreboard_as_of)

`scoreboard_current()` always reads obligation maturity from the live Python registry — so the moment an obligation is promoted from `planned` to `implemented` in code, the scoreboard reflects the new maturity immediately. This is correct for live dashboards and fresh attestations.

For audit trails and historical attestation re-issuance, a different query is needed: one that answers "what did the scoreboard say at time T?" without relying on the current code state. That is `scoreboard_as_of(ts)`.

```python
from praktor.aigov.ledger.scoreboard import scoreboard_as_of
from datetime import datetime, timezone

# What did the scoreboard look like on the date of a prior attestation?
as_of = datetime(2026, 3, 1, 9, 0, 0, tzinfo=timezone.utc)
rows = scoreboard_as_of(as_of, store, agent_id="clinical-triage-v2")
```

Key differences from `scoreboard_current()`:

| | `scoreboard_current()` | `scoreboard_as_of(ts)` |
|---|---|---|
| Maturity source | Live Python registry | `obligation_maturity` column stamped at event creation |
| Event window | All events up to now | Events with `event_ts ≤ ts` only |
| SLO downgrade | Supported via `slo_hours_per_agent` | Not supported (SLO would have been different at time T) |
| Use case | Live dashboards, fresh attestations | Audit trails, historical attestation re-issuance |

`scoreboard_as_of()` reads maturity from the event field (schema v1.1, `obligation_maturity` column) rather than the registry. This makes the ledger self-interpreting: the maturity at any historical point can be reconstructed without the current codebase. See §10 for the `obligation_maturity` field definition.

---

## 14. Event ingestion

Two paths. Customers pick one or both.

### 14.1 Direct SDK emit (primary)

```python
# aigov-sdk, Python
from aigov import LedgerClient, ObligationEvent, PredicateResult

client = LedgerClient(api_key=os.environ["AIGOV_API_KEY"])

client.emit(ObligationEvent(
    agent_id="clinical-triage-v2",
    agent_version="2.3.1",
    cim_version="2.3.0",
    bundle_id="healthcare-v5",
    obligation_id="O2",
    enforcement_point="G-RUN",
    measurement_technique="1.2.1",
    predicate_result=PredicateResult.PASS,
    evidence={"uri": evidence_uri, "sha256": sha},
    regulatory_tags=["HIPAA.164.514", "EU_AI_ACT.Art10"],
    trace_id=span.trace_id,
    span_id=span.span_id,
))
```

Language SDKs: Python, TypeScript, Go. Thin wrappers that POST to `/v1/events` or produce to Kafka.

### 14.2 OTel span extraction (zero-touch)

Customers already instrumented with OpenTelemetry ship a collector processor that extracts events from spans carrying `aigov.*` attributes:

```
aigov.obligation_id         = "O2"
aigov.enforcement_point     = "G-RUN"
aigov.measurement_technique = "1.2.1"
aigov.predicate_result      = "PASS"
aigov.evidence_uri          = "s3://..."
aigov.regulatory_tags       = "HIPAA.164.514,EU_AI_ACT.Art10,SOC2.CC6.7,HITRUST.09.s"
```

The processor translates matching spans to events and ships them to the ingestion endpoint. No code change in the agent. The `aigov.regulatory_tags` attribute value is a comma-separated list; the ingestion endpoint splits it into the `regulatory_tags` array.

---

## 15. Contract with praktor.ai

praktor.ai implements runtime enforcement and is the **reference G-RUN emitter**.

| praktor.ai component | Emits for | Obligation | Technique | SOC 2 tags | HITRUST tags |
|---|---|---|---|---|---|
| `RegexDetector` / `PresidioDetector` | Pre- and post-execution PHI/PII | O2 | 1.2.1, 1.2.2 | CC6.7, P5.1 | 01.b, 09.s |
| `LocalFileAuditSink` (hash-chained) | Every agent execution | O7 | 3.1.1 | CC7.2, CC7.3 | 09.aa, 09.ad, 13.j |
| `CallerIdentity` + `verify_token` | RBAC check | O1 | 1.3.1 | CC6.1, CC6.3 | 01.c, 12.c |
| `GovernancePolicyViolation` raised | Any BLOCK | O1, O2, O3 | varies | CC7.3 | 09.s |
| Attestation / CIM version check | Deployment lifecycle | O9 | varies | CC8.1 | 10.k |

`AuditSinkType.AIGOV_LEDGER` posts events to the ingestion endpoint using the §10 schema. The audit sink appends SOC 2 and HITRUST tags using the `SOC2_HITRUST_TAGS` mapping dict (keyed by `obligation_id`) before emission — no downstream change required.

```python
# praktor.ai audit sink — regulatory_tags enrichment
# Add to the event builder in AuditSinkType.AIGOV_LEDGER emit path
SOC2_HITRUST_TAGS: dict[str, list[str]] = {
    "O1":  ["SOC2.CC6.1", "SOC2.CC6.3", "HITRUST.01.c", "HITRUST.12.c"],
    "O2":  ["SOC2.CC6.7", "SOC2.P5.1",  "HITRUST.01.b", "HITRUST.09.s"],
    "O3":  ["SOC2.CC7.2",               "HITRUST.09.s"],
    "O4":  ["SOC2.CC7.2",               "HITRUST.09.s"],
    "O5":  ["SOC2.CC7.2",               "HITRUST.09.aa"],
    "O6":  ["SOC2.CC6.1", "SOC2.CC6.3", "HITRUST.01.c"],
    "O7":  ["SOC2.CC7.2", "SOC2.CC7.3", "HITRUST.09.aa", "HITRUST.09.ad", "HITRUST.13.j"],
    "O8":  ["SOC2.CC6.3",               "HITRUST.01.b",  "HITRUST.02.e"],
    "O9":  ["SOC2.CC8.1",               "HITRUST.10.k"],
    "O10": ["SOC2.CC7.2", "SOC2.A1.1",  "SOC2.A1.2",     "HITRUST.09.s"],
    "O11": ["SOC2.P5.1",                "HITRUST.02.e"],
}

def build_regulatory_tags(obligation_id: str, existing_tags: list[str]) -> list[str]:
    """Append SOC 2 + HITRUST tags to existing obligation-level tags."""
    addl = SOC2_HITRUST_TAGS.get(obligation_id, [])
    return sorted(set(existing_tags + addl))
```

Zero coupling beyond the HTTP/Kafka contract. `schema_version` stays at `1.1` — the `regulatory_tags` field is already `array<varchar>`.

praktor.ai is the canonical, open-source G-RUN emitter for the AIGov ledger. Customers running other frameworks (LangGraph, AutoGen, custom) emit via the SDK.

---

## 16. Data products

Five products, same ledger. Each unlocks a different buyer.

### 16.1 Obligation Scoreboard (primary)

**Buyer:** Head of AI governance, CISO, compliance officer.
**Surface:** Web dashboard, Slack alerts, PagerDuty integration.
**Views:** `scoreboard_current`, `scoreboard_fleet`, `scoreboard_trend_daily`.
**Price anchor:** Per agent, per month. Tiered by volume.

What makes it defensible: shows *time-since-last-evidence* per cell. A competitor running point-in-time assessments cannot produce this number.

**Metrics Tier Hierarchy (AI Observability, Watchtower 2026):**
The Scoreboard surfaces obligation status organized across three tiers, matching the Watchtower enterprise AI evaluation SOP:

| Tier | What it answers | Obligations |
|---|---|---|
| Tier 1 — Response Quality | Is the AI producing good answers? | O3, O5, O11 |
| Tier 2 — System Behavior | Is the AI behaving as designed? | O1, O6, O7, O8, O10 |
| Tier 3 — Business Impact | Is the AI delivering the outcomes it was built for? | O2, O4, O9 |

The fleet CISO view leads with Tier 2 + Tier 3 RED cells. The product team view leads with Tier 1. Evidence packs map regulatory citations to tiers automatically.

### 16.2 Event Stream API (raw)

**Buyer:** Platform engineering, data science, internal GRC tools.
**Surface:** REST `/v1/events` and Kafka topic `aigov.events.{tenant}`.
**Price anchor:** Platform add-on. Zero marginal cost; high lock-in.

Shipping the raw stream makes AIGov the system of record. Customers build dashboards on top, deepening lock-in.

### 16.3 Cross-customer Benchmarks

**Buyer:** Board-reporting CISOs doing peer comparison.
**Dataset:** Anonymized pass rates by industry × agent pattern × obligation × week.
**Opt-in:** Customers contribute in exchange for access.

```sql
-- benchmark_pass_rate_by_industry.sql
with agent_weekly as (
  select
    t.industry,
    a.agent_pattern,
    s.obligation_id,
    date_trunc('week', s.snapshot_date) as week,
    s.tenant_id,
    s.agent_id,
    avg(s.pass_rate) as agent_week_pass_rate
  from {{ ref('fact_obligation_status_snapshot') }} s
  join {{ ref('dim_tenant') }} t using (tenant_id)
  join {{ ref('dim_agent') }}  a using (agent_id)
  where t.benchmark_opt_in = true
  group by 1,2,3,4,5,6
)

select
  industry,
  agent_pattern,
  obligation_id,
  week,
  count(distinct tenant_id)                                          as tenants,
  count(distinct agent_id)                                           as agents,
  percentile_cont(0.5) within group (order by agent_week_pass_rate)  as p50_pass_rate,
  percentile_cont(0.9) within group (order by agent_week_pass_rate)  as p90_pass_rate,
  percentile_cont(0.1) within group (order by agent_week_pass_rate)  as p10_pass_rate
from agent_weekly
group by 1,2,3,4
having count(distinct tenant_id) >= 5;  -- k-anon threshold
```

K-anon ≥ 5 tenants per cell. This dataset **only exists with scale**. First to 20 healthcare customers has a product nobody else can build.

### 16.4 Drift Signatures

**Buyer:** Same as Scoreboard; this is the upsell.
**Model:** Sequence / anomaly detector over the event stream, trained per obligation, flagging patterns that preceded historical RED transitions.

Example: "O4 Fairness fail rate in the training-eval set increased 8% WoW while O5 Grounded pass rate dropped 3% → 73% probability of O3 Content Safety violation within 14 days."

**Surface:** Predictive alert in the Scoreboard.
**Price anchor:** Premium module. Margin multiplier on the core scoreboard.

### 16.5 Regulatory Evidence Packs

**Buyer:** Legal, external auditor (Joint Commission, EU notified body, SOC 2 CPA firm, HITRUST CCSFP assessor).
**Surface:** One-click export. JSON + PDF + signed manifest.
**Driver:** `dim_regulation` ↔ `regulatory_tags` on every event.

Six packs ship: EU AI Act Art. 12, HIPAA §164.312(b), ISO/IEC 42001 Cl. 9, SOC 2 CC6 (logical access), SOC 2 CC7/CC8/A1 (monitoring + change management), and HITRUST Category 09 (audit logging).

```sql
-- evidence_pack_eu_ai_act_art12.sql
-- Art. 12: automatic logging of high-risk AI system events
select
  f.event_ts,
  f.agent_id,
  f.agent_version,
  f.obligation_id,
  f.measurement_technique,
  f.predicate_result,
  f.evidence_uri,
  f.evidence_sha256,
  f.trace_id
from {{ ref('fact_obligation_event') }} f
where 'EU_AI_ACT.Art12' = any(f.regulatory_tags)
  and f.tenant_id = {{ var('tenant_id') }}
  and f.event_ts between {{ var('period_start') }} and {{ var('period_end') }}
order by f.event_ts;
```

```sql
-- evidence_pack_soc2_cc6_access_control.sql
-- SOC 2 TSC CC6: Logical and physical access controls
-- Obligations in scope: O1 (Bounded Action Space), O2 (Sensitive Data Confinement), O6 (Goal Integrity)
-- REQUIRED: CPA firm validation before shipping as customer-facing compliance evidence
select
  f.event_ts,
  f.agent_id,
  f.agent_version,
  f.obligation_id,
  f.enforcement_point,
  f.measurement_technique,
  f.predicate_result,
  f.severity,
  f.evidence_uri,
  f.evidence_sha256,
  f.trace_id,
  filter(f.regulatory_tags, t -> t like 'SOC2.CC6%') as soc2_cc6_tags
from {{ ref('fact_obligation_event') }} f
where exists(
    select 1 from unnest(f.regulatory_tags) as t where t like 'SOC2.CC6%'
  )
  and f.tenant_id = {{ var('tenant_id') }}
  and f.event_ts between {{ var('period_start') }} and {{ var('period_end') }}
order by f.event_ts;
```

```sql
-- evidence_pack_soc2_cc7_cc8_monitoring_change.sql
-- SOC 2 TSC CC7: System monitoring / CC8: Change management / A1: Availability
-- Obligations in scope: O7 (Auditable Decisions), O9 (Change Attestation Currency), O10 (Operational Invariants)
-- REQUIRED: CPA firm validation before shipping as customer-facing compliance evidence
select
  f.event_ts,
  f.agent_id,
  f.agent_version,
  f.cim_version,
  f.obligation_id,
  f.enforcement_point,
  f.measurement_technique,
  f.predicate_result,
  f.severity,
  f.waiver_id,
  f.evidence_uri,
  f.evidence_sha256,
  f.reviewer_id,
  f.trace_id,
  filter(f.regulatory_tags, t -> t like 'SOC2.CC7%' or t like 'SOC2.CC8%' or t like 'SOC2.A1%') as soc2_monitoring_change_tags
from {{ ref('fact_obligation_event') }} f
where exists(
    select 1 from unnest(f.regulatory_tags) as t
    where t like 'SOC2.CC7%' or t like 'SOC2.CC8%' or t like 'SOC2.A1%'
  )
  and f.tenant_id = {{ var('tenant_id') }}
  and f.event_ts between {{ var('period_start') }} and {{ var('period_end') }}
order by f.event_ts;
```

```sql
-- evidence_pack_hitrust_09_audit_logging.sql
-- HITRUST CSF v11.3 Category 09: Audit logging, log protection, system monitoring
-- Obligations in scope: O7 (Auditable Decisions), O5 (Grounded Outputs), O10 (Operational Invariants)
-- REQUIRED: HITRUST CCSFP assessor validation before shipping as customer-facing compliance evidence
select
  f.event_ts,
  f.agent_id,
  f.agent_version,
  f.obligation_id,
  f.enforcement_point,
  f.measurement_technique,
  f.predicate_result,
  f.severity,
  f.waiver_id,
  f.evidence_uri,
  f.evidence_sha256,
  f.trace_id,
  f.span_id,
  filter(f.regulatory_tags, t -> t like 'HITRUST.09%') as hitrust_09_tags
from {{ ref('fact_obligation_event') }} f
where exists(
    select 1 from unnest(f.regulatory_tags) as t where t like 'HITRUST.09%'
  )
  and f.tenant_id = {{ var('tenant_id') }}
  and f.event_ts between {{ var('period_start') }} and {{ var('period_end') }}
order by f.event_ts;
```

The pack is a query plus a signing step. The regulator gets a zip of the query result + a signed JWS manifest proving it was generated from an immutable ledger against a specific `cim_version`. Replaces the hand-written audit binder that costs $80K/year of compliance labor.

> **SOC 2 / HITRUST evidence packs: validation gate.** The SOC 2 and HITRUST evidence pack exports must be gated behind a `cpa_validated: true` feature flag in the UI until a licensed CPA firm (SOC 2) and a HITRUST CCSFP assessor have reviewed the obligation→control crosswalk in §10.4. The underlying event data is authoritative; the compliance claim requires auditor sign-off.

---

## 17. Attestation as a ledger view

The signed Attestation still exists. It is now a **point-in-time projection** of the Scoreboard, signed, time-bounded, exported on demand.

```sql
-- called on demand, not materialized
select
  tenant_id,
  agent_id,
  agent_version,
  cim_version,
  bundle_id,
  obligation_id,
  status,
  last_evidence_ts,
  latest_event_ids
from {{ ref('scoreboard_current') }}
where tenant_id = :tenant
  and agent_id  = :agent;
```

Wrapped in:

```json
{
  "attestation_schema": "aigov-v0.6",
  "attestation_id": "ATT-2026-0142",
  "issued_at": "2026-04-29T09:00:00Z",
  "valid_until": "2026-07-29T09:00:00Z",
  "tenant_id": "acme-health",
  "agent": {
    "name": "clinical-triage-v2",
    "version": "2.3.1",
    "deployment": "epic-prod-us-east-1",
    "vendor": "first-party"
  },
  "bundle": ["O1","O2","O3","O4","O5","O6","O7","O8","O9","O10","O11"],
  "hai_taxonomy": {
    "risk_level": "Elevated",
    "ai_interaction_type": "Conversation Partner",
    "user_type": "External"
  },
  "cim_version": "2.3.0",
  "status_per_obligation": [
    {"obligation_id":"O1", "status":"GREEN","last_evidence_ts":"2026-04-29T08:55:12Z","obligation_maturity":"implemented"},
    {"obligation_id":"O2", "status":"GREEN","last_evidence_ts":"2026-04-29T08:55:12Z","obligation_maturity":"implemented"},
    {"obligation_id":"O3", "status":"GREEN","last_evidence_ts":"2026-04-29T08:55:12Z","obligation_maturity":"implemented"},
    {"obligation_id":"O4", "status":"GREEN","last_evidence_ts":"2026-04-29T08:55:12Z","obligation_maturity":"implemented"},
    {"obligation_id":"O5", "status":"GREEN","last_evidence_ts":"2026-04-29T08:55:12Z","obligation_maturity":"implemented"},
    {"obligation_id":"O6", "status":"GREEN","last_evidence_ts":"2026-04-29T08:55:12Z","obligation_maturity":"implemented"},
    {"obligation_id":"O7", "status":"GREEN","last_evidence_ts":"2026-04-29T08:55:12Z","obligation_maturity":"implemented"},
    {"obligation_id":"O8", "status":"GREEN","last_evidence_ts":"2026-04-29T08:55:12Z","obligation_maturity":"implemented"},
    {"obligation_id":"O9", "status":"GREEN","last_evidence_ts":"2026-04-29T08:55:12Z","obligation_maturity":"implemented"},
    {"obligation_id":"O10","status":"GREEN","last_evidence_ts":"2026-04-29T08:55:12Z","obligation_maturity":"implemented"},
    {"obligation_id":"O11","status":"GREEN","last_evidence_ts":"2026-04-29T08:55:12Z","obligation_maturity":"implemented"}
  ],
  "ledger_anchor": {
    "warehouse": "snowflake://aigov/prod",
    "query_sha256": "9f4e...c1",
    "row_count": 11,
    "as_of_ts": "2026-04-29T09:00:00Z"
  },
  "golden_dataset_version": "1.0.0",
  "independence_tier": "internal-red-team",
  "has_no_active_violations": true,
  "compliance_score": 1.0,
  "implementation_coverage": 1.0,
  "reviewers": [{"name":"...","role":"...","signature":"..."}],
  "change_log": [],
  "revocation_uri": "https://aigov.example/att/ATT-2026-0142"
}
```

**Legal properties:**
- Time-bounded. No "valid forever."
- Revocable via CRL-style URI. Consumers must check before relying.
- Signed (JWS). Reviewer identities are cryptographic.
- Versioned. Supersedes chain links back to prior Attestations.
- **Ledger-anchored.** Proves it came from an immutable ledger at a specific moment.

The Attestation is a receipt. The ledger is the truth.

**Note on obligation_maturity and computed fields:** Each `status_per_obligation` entry carries the maturity level stamped at event creation time (schema v1.1). Three computed summary fields appear at the attestation level:

- `has_no_active_violations` — `true` when no `implemented` obligation is RED or FAIL. Deferred obligations (`planned` / `declared`) with AMBER status are excluded.
- `compliance_score` — fraction of `implemented` obligations currently passing (0.0–1.0). G-RUN row takes precedence over G-BUILD when both exist for the same obligation. Returns 0.0 when no implemented obligations are present.
- `implementation_coverage` — fraction of distinct bundle obligations at `implemented` maturity. As of v0.5, all 11 obligations are `implemented`: `implementation_coverage = 1.0`.

---

## 18. Continuous monitoring loop

```
    ┌────────────────────────────────────────────────────────┐
    │                                                        │
    ▼                                                        │
Agent runs in prod                                           │
    │                                                        │
    ▼                                                        │
praktor.ai governance plane checks predicates                │
    │                                                        │
    ▼                                                        │
Emits event → ingestion API → Kafka → S3 → warehouse         │
    │                                                        │
    ▼                                                        │
int_status_per_key recomputes (streaming or 60s batch)       │
    │                                                        │
    ▼                                                        │
scoreboard_current updates                                   │
    │                                                        │
    ├──► status transition RED → Slack/PagerDuty             │
    │                                                        │
    ├──► drift_signal_obligation ML scan                     │
    │                                                        │
    ├──► benchmark_*   (nightly)                             │
    │                                                        │
    └──► on demand: evidence_pack_* export                   │
                                                             │
    feedback: waiver issued, reviewer notes, fix deployed ───┘
```

Loop time from agent run to dashboard update: ~90 seconds in v1. Sub-10-second possible with streaming materialization.

---

# PART III — Operations & GTM

## 19. AIGov work for agents — the lifecycle

"AIGov work" is the set of activities required to produce and maintain a valid Attestation over an agent's lifetime.

```
Scope → Author → Wire → Attest → Verify → Re-attest
  ↑                                            │
  └────────────────────────────────────────────┘
                  (on change or expiry)
```

### Phase 1 — Scope
**Input:** agent description, intended use, data flows, regulatory context.
**Activity:** apply the Bundle Selection Matrix (§6). Produce the Bundle with thresholds.
**Output:** `bundle.yaml` — obligations + thresholds + regulatory citations.
**Owner:** Enterprise Governance + App Dev, reviewed per Independence Tier.

### Phase 2 — Author
**Input:** `bundle.yaml`.
**Activity:** for each obligation, write the Action Manifest / Data Flow Manifest / Goal Manifest / Content Policy / protected-attribute schema / SLO targets.
**Output:** `manifests/` directory with signed manifests.
**Owner:** App Dev, with Enterprise templates.

### Phase 3 — Wire
**Input:** manifests + bundle.
**Activity:** connect each obligation to its four enforcement points. Add CI checks (G-BUILD), test suite runners (G-TEST), runtime policies and monitors (G-RUN), and G-DELEGATE event emission for orchestrators. Wire the emitter (praktor.ai or SDK) to ship events to the AIGov ledger.
**Output:** green CI, passing test suite, running monitors, events flowing.
**Owner:** App Dev + Enterprise SRE.

### Phase 4 — Attest
**Input:** wired deployment with events flowing.
**Activity:** run the full Bundle against the Attestation Test Protocol. Independent reviewer per Independence Tier Model inspects the Scoreboard and signs the Attestation (ledger projection).
**Output:** signed Attestation JSON + human summary + live Scoreboard link.
**Owner:** Independent reviewer + Enterprise Governance.

### Phase 5 — Verify continuously
**Input:** active Attestation + live ledger.
**Activity:** Scoreboard updates in real time. Drift signatures scan for predictive signals. Violation alerts fire on RED transitions. Evidence packs generated on demand.
**Output:** live status; violation incidents; predictive alerts; audit exports.
**Owner:** Enterprise SRE + Governance, on-call rotation.

### Phase 6 — Re-attest
**Trigger:** change event (per CIM), violation, or time-based expiry.
**Activity:** scoped re-evaluation per CIM; on violation, rollback per Phased Rollout Protocol; on expiry, full Attestation Test Protocol.
**Output:** updated Attestation (new ID, supersedes prior) or revocation notice.
**Owner:** App Dev for scoped re-attestation; Independent Reviewer for full re-attestation.

### Roles

| Role | Owns |
|---|---|
| **App Dev** | Manifests, test harnesses, runtime instrumentation, emitter wiring (phases 2, 3) |
| **Enterprise Governance** | Bundle Selection Matrix, CIM, Attestation registry, independence routing |
| **Enterprise SRE** | Runtime monitors, Scoreboard ops, violation alerting (phase 5) |
| **Independent Reviewer** | Phase 4 sign-off; scope set by Independence Tier Model |
| **Vendor (if applicable)** | Model card, incident notifications, contractual Attestation preconditions |

---

## 20. What stays from v1.0 verbatim

Do not rewrite. Link to:

- **Regulatory Crosswalk CSV** — used as `dim_regulation`.
- **Change Impact Matrix** — used as Phase 6 trigger table.
- **Independence Tier Model** — used as Phase 4 reviewer-routing rule.
- **Phased Rollout Evaluation Protocol** — used as runtime-ramp policy (canary → limited → scaled). Each phase requires a valid Attestation for the scope of traffic.
- **Test Dataset Categories** — used as evidence datasets cited by G-TEST per obligation.
- **Tool catalog and fallback configurations** — used as the enforcement-technique library.

This framework is a restructuring of v1.0, not a greenfield replacement. It preserves the measurement investments and repackages the commercial surface.

---

## 21. Commercial rationale and competitive moat

### Why it sells better

1. **The deliverable has legal weight.** A signed, time-bounded, revocable, ledger-anchored Attestation is something a hospital general counsel can rely on. A scorecard is not.
2. **The offering is memorable.** "We certify your agent holds 8 obligations continuously, and we revoke if any fail." That fits a 30-second elevator pitch.
3. **Buyers compare it to things they already buy.** SOC 2, HITRUST, ISO 27001 are all attestation-shaped + monitoring-backed.
4. **Independent review becomes a clean SKU.** Price scales with Independence Tier.
5. **Continuous verification becomes recurring revenue.** Phase 5 is a managed-service line — Scoreboard + Event Stream API + drift signatures + evidence packs.
6. **Joint Commission / CHAI conversation gets simpler.** "We are the technical backbone of agentic AI certification" lands when the backbone is a standard Event Schema + Attestation format.
7. **Category name writes itself.** "Agent Obligations." "Clinical Agent Attestation." Either is stronger than "Agentic AI Readiness Assessment."
8. **Calibrated compliance scores replace raw obligation counts.** `compliance_score()` counts PASS + GREEN events only for `implemented` obligations. `implementation_coverage()` is the fraction of bundle obligations at `implemented` maturity. As of v0.5, all 11 obligations are `implemented` — `compliance_score() = 1.0`, `implementation_coverage() = 1.0`. This separates "what we certify" from "what we're working toward," which is exactly the framing Joint Commission buyers need.

### Moat (compounding with scale)

| # | Moat | Unlocked at | Why defensible |
|---|---|---|---|
| 1 | Ledger accrual | Day 1 | Customer cannot take their history elsewhere |
| 2 | Evidence pack automation | Month 1 | Replaces $80K/yr compliance labor — sticky |
| 3 | Drift signatures | ~10 customers | ML needs historical RED transitions; we have the only labeled set |
| 4 | Cross-customer benchmarks | ~20 customers / industry | k-anon requires scale; first mover wins |
| 5 | Regulatory schema authority | Year 2 | If the Event Schema becomes the crosswalk everyone uses, we are the schema registry |

Moat #5 is the endgame. If the Event Schema (§10) becomes the de-facto format for agent governance events, every competitor ends up emitting in our shape and we are the warehouse they all feed.

**Shape transition:**
- v1.0: **methodology** — you pay for a report.
- v0.1 Obligations: **standard** — you pay for a signed artifact.
- v0.2 Ledger + Scoreboard: **platform** — you pay per agent per month, forever, and your history is worthless to anyone else.

The methodology is the moat for the first 3 customers. The platform is the moat for the next 300.

---

## 22. Roadmap

**Week 1 — Lock the contract.** ✅ DONE
- Finalized the 11 obligations; `obligations_catalog_v1.yaml` committed.
- Published Bundle Selection Matrix; current bundles: `standard-v2`, `healthcare-v5`, `external-v3`.
- Published Event Schema v1.1.

**Week 2 — Minimum ledger.** ✅ DONE
- DuckDB-backed reference ingestion + `fact_obligation_event`.
- Python SDK with synchronous `emit`.
- praktor.ai ships `AuditSinkType.AIGOV_LEDGER` emitting O2 and O7 events.

**Week 3 — Scoreboard v0.** ✅ DONE
- dbt project with `stg`, `int_status_per_key`, `scoreboard_current`.
- React gov UI: Scoreboard, Obligations, Traces, Docs pages.
- RED-transition alerting via Actions Required panel.

**Week 4 — First paid assessment as pilot.** ✅ DONE
- Scope → Attest loop exercised with healthcare default bundle.
- Signed Attestation JSON + live Scoreboard + evidence pack export.

**Month 2 — Data products v0.** ✅ DONE
- `fact_obligation_status_snapshot`, `fact_violation`, trend view.
- Evidence pack #1: EU AI Act Art. 12 export.
- Benchmark view skeleton (opt-in flag in `dim_tenant`).

**Month 3 — Multi-tenant + drift v0.**
- Snowflake backend with row-access policies.
- `drift_signal_obligation` v0 (anomaly detector, not ML yet).
- OTel collector processor shipped.
- Customers 2 and 3 onboarded.

**Quarter 2 — Scale-out.**
- Drift signatures → ML model trained on labeled violations.
- Evidence packs #2 (HIPAA §164.312(b)) and #3 (ISO/IEC 42001 Cl. 9).
- Benchmark product gated at k-anon ≥ 5.
- Publish Event Schema as an open spec. Invite other frameworks to emit.
- Arxiv preprint: "Agent Obligations: a continuous-attestation framework for enterprise agentic AI."

---

## 23. Open questions

### Framework

1. **O4 Fairness thresholds are contextual.** ACA §1557 in healthcare has different legal standards than EEOC fairness. Vertical variants or per-deployment configurable? Recommend: configurable with healthcare defaults published.
2. **Vendor obligation parity.** Can O6 Goal Integrity ever be attested for a black-box vendor agent? Probably not without vendor cooperation. Some deployments are uncertifiable with a given vendor — should be stated explicitly in the Bundle Selection Matrix.
3. **Multi-agent systems.** Orchestrator + three subordinates — one deployment or four? Recommend: Attestations per-orchestrator; sub-agents covered under O1 Bounded Action Space as declared tools, with G-DELEGATE evidence per handoff.
4. **Violation runbook.** Must exist before the first Attestation issues. Current proposal: automatic policy-engine block + incident ticket + rollback per Phased Rollout Protocol + re-attestation required before re-enable.
5. **O4 G-RUN fairness monitoring without protected attributes.** At G-RUN time, protected attributes are typically unavailable (privacy constraint). Options: (a) proxy-based monitoring with stated limitations, (b) O4 is G-TEST only with mandatory 90-day re-evaluation cadence, (c) synthetic re-evaluation using stored test set. Decision needed before O4 G-RUN cell is finalized.
6. **O11 S-TIAS threshold calibration.** S-TIAS ≥ 3.5/5.0 is an early warning target drawn from HAI Framework "above-average trust" benchmark. After first 3 O11 deployments, convene a calibration review to determine if 3.5 is right for the member population. Recommend: calibration checkpoint at month 6 of first O11 deployment.
7. **Misunderstanding rate classifier.** §27.5 requires a classifier (precision ≥ 0.80) to detect implicit correction signals in conversation. This classifier must be defined, trained on labeled data, and validated before O11 G-RUN monitoring is meaningful.
8. **OVA Score in Attestation.** Should the Attestation (§17) include the OVA Score as a field visible to external auditors? Recommend: include as an informational field (not a compliance gate) in the Attestation header.

### Platform

9. **Warehouse choice.** DuckDB for pilot, Snowflake for GA, or ClickHouse for G-RUN event economics?
10. **Streaming vs micro-batch.** Is 60-second Scoreboard latency acceptable, or does the CISO dashboard need sub-5-second updates?
11. **Evidence blob retention cost.** 7-year WORM retention of every G-RUN blob could be millions at scale. Tier, summarize, or bill pass-through?
12. **Schema versioning.** How do we evolve `obligation_event` without breaking 7-year-old replay? Probably additive-only + `schema_version` discriminator + compactor jobs.
13. **Benchmark consent mechanics.** `dim_tenant.benchmark_opt_in` a checkbox at sign-up or a contract clause? K-anon floor of 5, 10, or 20?
14. **PII in evidence blobs.** `evidence_uri` may contain redacted PHI. Customer holds the bucket (less liability, more friction) or we hold it (more liability, lower friction)? Probably customer with us holding only the hash.
15. **Drift model cold-start.** Before we have historical RED transitions, drift signatures are rules-based. When do we switch to ML without a feedback loop where the rules teach the model?
16. **Revocation distribution.** CRL-style URI works for push consumers but not for CI/CD pipelines caching Attestations. Webhook for Phase 2 SaaS.
17. **Golden Dataset ownership at commercial scale.** Watchtower owns it today. As external customers use the framework, does each customer own their own Golden Dataset (customer-managed), or does the platform maintain a shared registry?

---

## 26. LLM-as-Judge Protocol (G-TEST methodology)

When an obligation's predicate requires semantic evaluation of agent output, the G-TEST enforcement technique SHALL use an LLM-as-Judge (LLaJ) system conforming to this protocol. The protocol is grounded in the Watchtower LLM-as-a-Judge guide and implemented via ELLMo (go/ellmo).

### 26.1 Core principles

- **One judge per criterion.** A single LLaJ evaluates exactly one predicate dimension. Multi-criterion judges are prohibited — they contaminate scores and make validation intractable.
- **Binary Pass/Fail scale.** Each judge produces PASS or FAIL per evaluated item. Likert scales are not permitted at the judge layer. Aggregate statistics (pass rate, confidence interval) are computed over binary results.
- **Rubric-first.** The scoring rubric is written before the prompt is designed. The prompt is a direct translation of the rubric, verbatim where possible. The rubric is the contract between the LLaJ and human validators.

### 26.2 Required judges per obligation

Per §26.1, one judge per criterion. O11 requires three separate judges because its predicate has three independently testable dimensions.

| Obligation | Judge name | Criterion evaluated (one per judge) |
|---|---|---|
| O3 Content Safety | `judge_content_safety` | Does the output violate the Content Safety Policy? |
| O5 Grounded Outputs | `judge_factual_grounding` | Does every factual claim trace to a cited source? |
| O6 Goal Integrity | `judge_goal_alignment` | Does each trajectory step pursue only the signed Goal Manifest? |
| O11 | `judge_ai_nature_disclosure` | Does the output disclose the agent's AI nature and operational scope? |
| O11 | `judge_source_attribution` | For retrieval-sourced claims, is source attribution present and accurate? |
| O11 | `judge_uncertainty_fallback` | Is the uncertainty fallback invoked when model confidence falls below the declared threshold? |

`judge_source_attribution` applies only to RAG-enabled deployments. All judges are registered in `ellmo_judges.yaml` with the criterion, rubric version, and current κ score.

### 26.3 Rubric structure

Each rubric MUST contain:
1. **Definition** — plain-language description of what is being evaluated
2. **Scale** — Pass or Fail, with exact definitions for each
3. **Pass examples** — 2–3 outputs that clearly Pass, with explanation
4. **Fail examples** — 2–3 outputs that clearly Fail, with explanation
5. **Boundary guidance** — what to do with ambiguous cases (default: "when in doubt, Fail")
6. **What to ignore** — factors that MUST NOT influence the score (e.g., writing quality, length)

### 26.4 Judge prompt structure

Required prompt elements (in order):
1. Role: "You are an evaluator assessing [criterion name]."
2. Task description: inputs the judge receives, what it must produce
3. **Context injection block** (required for deployment-parameterized judges): named variables passed at evaluation time, e.g., `{{user_type}}`, `{{confidence_threshold}}`, `{{disclosure_template}}`.
4. Rubric: copy the rubric verbatim — do not paraphrase
5. Output format: structured JSON with `score` (PASS/FAIL) and `reasoning` (required)
6. Examples: at least one Pass example and one Fail example from the rubric

The `reasoning` field is non-negotiable. It is the audit trail for human-judge disagreement review.

### 26.5 Validation before production

**Step 1 — Developer smoke test.** 15–30 items hand-selected to cover clear Pass, clear Fail, and boundary cases.

**Step 2 — Human annotation.** Minimum 5 independent human validators score the same evaluation set without seeing judge scores. Run a calibration session first (10–20 shared items). If calibration session κ falls below 0.50, halt and revise the rubric.

**Step 3 — Measure agreement.**
- **Inter-annotator agreement:** Cohen's κ among humans. Must be ≥ 0.60.
- **Human-to-judge agreement:** Cohen's κ between human majority vote and judge:

| Deployment context | Required κ |
|---|---|
| Advisory monitoring | ≥ 0.60 |
| G-TEST enforcement gate | ≥ 0.60 |
| O8 HITL review calibration | ≥ 0.75 |

**Step 4 — Diagnose misalignment.** If κ < threshold:
- Ambiguity flag rate > 15% → rubric problem → add examples, tighten boundary guidance
- Ambiguity flag rate ≤ 15% → judge prompt problem → compare prompt to rubric, retranslate

### 26.6 Production monitoring

- **Spot-checks:** 5–10% of judge scores reviewed weekly by human evaluators
- **Score distribution monitoring:** alert if pass rate shifts > 10% without a known cause
- **Re-validation triggers:** new model version, prompt change, or input distribution shift
- **Drift events** are logged to `fact_obligation_event` with `source.kind = "llm_judge_drift_check"`

### 26.7 ELLMo integration

ELLMo (go/ellmo) provides pre-built judges for factual grounding, content safety, and goal alignment; plug-and-play templates; agreement measurement tooling; and calibration session infrastructure. Pre-built judges MUST be calibrated to the specific deployment context before use in G-TEST enforcement.

### 26.8 Multiple-criterion evaluation

1. Define each dimension as a separate criterion
2. Build and validate one judge per criterion (§26.1)
3. Prioritize by risk — blocking criteria get full validation
4. Share the same sample pool across judges; validators score one criterion per pass
5. Monitor each judge independently in production

---

## 27. HAI Overlay — Human-AI Interaction Governance

The Human-AI Interaction (HAI) Framework v2 (Watchtower) provides the user-facing governance layer for the AIGov obligations. It classifies deployments on three axes that determine which obligations apply and at what intensity.

### 27.1 HAI Taxonomy (3-axis classification)

**Axis 1 — Risk Level**

| Level | Characteristics |
|---|---|
| **Minimal** | Failures impact one or few people; high visibility; user-correctable; not externally facing; no delays to clinical or financial decisions |
| **Elevated** | Failures may impact company or members; lower visibility; may quietly fail; requires credentialed correction; delays to business operations or care |

**Axis 2 — AI Interaction Type**

| Type | Definition | Example |
|---|---|---|
| **AI as Tool** | AI assists human during decision-making | Prior authorization assistant, claims summary |
| **AI as Mediator** | AI assists communication between two humans/groups | Provider handoff documentation, complaint routing |
| **AI as Conversation Partner** | AI acts as a human alternate in turn-based conversation | Member support chatbot, clinical differential diagnostic assistant |

**Axis 3 — User Type**

| Type | Definition |
|---|---|
| **Internal-General** | Humana employee; general use; no domain-specific requirement |
| **Internal-Expert** | Humana employee; high domain expertise (clinician, data analyst, legal) |
| **External** | Member, patient, auditor, regulatory representative |

### 27.2 HAI-to-obligation mapping

| Axis 1 | Axis 2 | Axis 3 | O11 Required | O8 Tier | HITL Type |
|---|---|---|---|---|---|
| Minimal | Tool | Internal-General | No | Advisory | HOTL (sampling) |
| Minimal | Tool | Internal-Expert | Deferred¹ | Standard | HOTL |
| Minimal | Mediator | Internal-General | No | Standard | HOTL |
| Minimal | Mediator | Internal-Expert | Deferred¹ | Standard | HOTL |
| Minimal | Conversation Partner | Internal-General | No | Standard | HOTL |
| Minimal | Conversation Partner | Internal-Expert | Deferred¹ | Standard | HOTL |
| Minimal | Any | External | Yes | Standard | HITL (sampling) |
| Elevated | Any | Internal-General | Deferred¹ | Standard | HOTL |
| Elevated | Any | Internal-Expert | Yes | Enhanced | HITL |
| Elevated | Any | External | Yes | Enhanced | HITL (all) |
| Any | Conversation Partner | External | Yes | Enhanced | HITL with escalation |

¹ **Deferred:** O11 not required at initial deployment. Must be included at the next MAJOR CIM event if risk escalates to Elevated, user base expands to External, or 12 months elapse. Attestation records O11 as "N/A — Deferred".

### 27.3 HAI Oversight Modules

| HAI Module | Description | AIGov Obligation |
|---|---|---|
| A — User Experience | Subjective ratings (CSAT, NPS, SUS, S-TIAS) | O11 G-RUN (S-TIAS ≥ 3.5 early warning; monthly spot-check) |
| B — Gold Standard Evaluation | Expert-validated golden dataset (see §28) | G-TEST anchor for O3, O5, O6, O11 |
| C — Human Oversight (HITL/HOTL) | Meaningful human review; not rubber-stamp | O8; OVA Score |
| D — Interaction Monitoring | Turn-level quality metrics | O7 G-RUN; O11 G-RUN |
| E — Transparency & User Controls | Disclosure, source attribution, uncertainty fallback | O11 predicate |
| F — Observability | Session traces, input/output logging, time-on-task | O7 G-RUN; §29 |

### 27.4 OVA Score — Oversight Value Assessment

The OVA Score quantifies the value added by HITL or HOTL oversight relative to AI-alone baseline. Required for O8 compliance when the deployment uses HITL.

**Formula (weighted, risk-adjusted):**
```
OVA = w_time × ΔTimenorm + w_CSAT × ΔCSATnorm + w_STIAS × ΔS-TIASnorm + w_SUS × ΔSUSnorm

where:
  Δ = (with-oversight value) − (baseline/AI-alone value)
  ΔTimenorm = 1 − (time_with_oversight / time_baseline), capped at [−1, +1]
               (positive = faster with oversight; negative = slower)
  ΔCSATnorm = (CSAT_with_oversight − CSAT_baseline) / 4   [CSAT is 1–5 scale]
  ΔS-TIASnorm = (S-TIAS_with_oversight − S-TIAS_baseline) / 4  [S-TIAS is 1–5 scale]
  ΔSUSnorm = (SUS_with_oversight − SUS_baseline) / 100    [SUS is 0–100 scale]
  OVA range: [−1, +1]
```

**Risk-adjusted weights (must sum to 1.0):**

| Risk Level | Priority | w_time | w_CSAT | w_STIAS | w_SUS |
|---|---|---|---|---|---|
| Minimal | Efficiency | 0.40 | 0.30 | 0.10 | 0.20 |
| Elevated | Quality > speed | 0.10 | 0.30 | 0.40 | 0.20 |

**O8 compliance:** OVA Score ≥ 0 is required to hold O8 HELD status for HITL-enabled deployments. OVA < 0 indicates oversight is adding cost without quality — triggers review of the HITL workflow design, not automatic violation. OVA events are emitted to `fact_obligation_event` with `obligation_id = "O8"` and `measurement_technique = "OVA"`. OVA Score is re-measured quarterly and may be included as an informational field in the Attestation (§17).

### 27.5 Interaction Monitoring Metrics (O11 G-RUN)

Captured at G-RUN for AI Conversation Partner and AI Mediator deployments:

| Metric | Definition | O11 G-RUN threshold | Detection method |
|---|---|---|---|
| Misunderstanding rate | % of turns with correction signals | ≤ 10% | Classifier-based (precision ≥ 0.80 required) |
| Recovery rate | % of misunderstood intents where AI recovered on next turn | ≥ 80% | Requires misunderstanding detection as prerequisite |
| Retry rate | # of semantically similar sequential queries | ≤ 15% of sessions | Embedding similarity + session window |
| Session abandon signature | % of sessions abandoned after low-confidence or miscommunication signal | Monitor; alert on > 2× baseline | Session completion + confidence flag correlation |

Before implementing these metrics, the Watchtower team must define and validate the misunderstanding classifier, document it in the Transparency Manifest, and demonstrate precision ≥ 0.80 on a labeled sample.

Events are emitted as `obligation_id = "O11"`, `enforcement_point = "G-RUN"` in the ledger.

### 27.6 Transparency Manifest — O11 Implementation Requirements

For each deployment holding O11, a Transparency Manifest MUST specify:

1. **Disclosure schema:** exact disclosure text or template, calibrated to user type
2. **Confidence threshold:** model confidence level below which the uncertainty fallback fires
3. **Uncertainty fallback template:** the exact fallback message invoked when confidence < threshold
4. **User override mechanism:** how users invoke override and what happens when they do
5. **Source attribution policy:** whether and how retrieval sources are displayed; click-through rate target
6. **Misunderstanding classifier spec:** method, precision floor, and labeled sample used for G-RUN interaction monitoring (§27.5)

The Transparency Manifest is a G-BUILD artifact, signed at deploy time. Changes trigger a scoped re-evaluation per CIM.

---

## 28. Golden Dataset Protocol

A Golden Dataset is a curated, expert-validated collection of questions and expected outputs that serves as the primary deployment-specific anchor for G-TEST evaluation. It is a living organizational standard — not a static snapshot.

Grounded in the AI Observability Framework (Watchtower/Arize 2026-02-25) and the AgenticAI Eval Framework v1.0 test dataset categories.

### 28.1 What a Golden Dataset is (and is not)

**Is:** Expert-consensus validated Q&A pairs (or task-completion pairs) with metadata, covering the full question space the agent is expected to handle, including edge cases.

**Is not:** A convenience sample of easy cases. Not output from a single annotator. Not static — it is updated as the question space evolves and as new edge cases are discovered.

**Relationship to third-party benchmarks:** Third-party benchmarks serve as supplementary validation against public standards. The Golden Dataset is the deployment-specific anchor. Both must pass. Every G-TEST evaluation report MUST cite both the Golden Dataset version AND any third-party benchmark suites used.

### 28.2 Dataset structure

| Field | Type | Description |
|---|---|---|
| `question_id` | ULID | Stable identifier |
| `question_text` | string | The input to the agent |
| `expected_output` | string | The expert-consensus ideal response |
| `metadata` | object | Domain category, complexity level, regulatory tags, TTL, created date, last_verified date |
| `obligation_ids` | string[] | Which obligations this entry evaluates |
| `difficulty` | enum | `clear_pass`, `clear_fail`, `boundary` — for judge calibration |
| `annotator_ids` | string[] | Human validators who contributed (blind annotation) |
| `consensus_method` | enum | `majority_vote`, `adjudication`, `unanimous` |

### 28.3 Construction process

**Step 1 — Question space mapping.** Map the complete space of questions the agent handles before adding a single entry. Coverage is complete when the distribution of new edge cases identified per 100 additional expert-reviewed interactions drops below 5%.

**Step 2 — Build expert consensus, not expert opinion.** Minimum 3 domain experts annotate each item independently. No annotation is canonical until at minimum 2 of 3 experts agree.

**Step 3 — TTL management.**

| Content category | Default TTL |
|---|---|
| Regulatory citations, clinical guidelines | 90 days |
| Product/plan information | 30 days |
| Static reference (drug names, anatomy) | 365 days |
| Member-specific derived facts | Per interaction (no caching) |

Entries past TTL emit an `obligation_id = "O5"` AMBER event in the ledger.

**Step 4 — Sample size calibration.** Size to achieve ≥ 95% confidence with ±5% margin of error per obligation. For a binary pass rate near 0.90, this requires approximately 138 items per obligation being evaluated.

### 28.4 Maintenance and governance

- The Golden Dataset is versioned using SemVer. MAJOR bumps when ≥ 20% of entries change.
- Every G-TEST evaluation report MUST cite the Golden Dataset version used.
- A MAJOR CIM event triggers mandatory Golden Dataset review.
- The Watchtower team owns the Golden Dataset registry.

### 28.5 Bootstrapping — first deployment

**For the first G-TEST of a new agent (no Golden Dataset yet):**

1. Third-party benchmarks are the sole G-TEST anchor.
2. The first G-TEST evaluation report MUST include a note: "Golden Dataset not yet established."
3. The Golden Dataset v1.0 is built from canary traffic.
4. Golden Dataset v1.0 MUST be complete before the next MAJOR CIM event triggers G-TEST re-evaluation.

The first Attestation is slightly weaker — third-party-benchmark-anchored, not deployment-specific. The Attestation states it: `"golden_dataset_version": null` on first issuance, then `"golden_dataset_version": "1.0.0"` on every subsequent one.

### 28.6 Relationship to enforcement points

| Enforcement point | Golden Dataset role |
|---|---|
| G-BUILD | Verify the agent's declared scope matches the question space map |
| G-TEST (first cycle) | Third-party benchmarks only; Golden Dataset not yet required |
| G-TEST (subsequent cycles) | **Primary LLaJ calibration anchor** for O3, O5, O6, O11 |
| G-RUN | Spot-check sampling; new user queries assessed against Golden Dataset distribution |

---

## 29. Observability Platform Requirements

The AIGov ledger (§9–18) is the governance record. The Observability Platform is the infrastructure that feeds it and provides real-time visibility into G-RUN enforcement.

### 29.1 Platform options

| Platform | Strengths | Gaps | Decision |
|---|---|---|---|
| **Arize** | Centralized evaluation dashboards; full response traceability; continuous quality monitoring; native LLM-as-Judge integration | Proprietary; cost at scale; less granular control over event schema | Optional: pilot for teams prioritizing dashboard velocity |
| **OpenTelemetry/OTLP** | Open standard; universal language/runtime support; integrates directly with AIGov event schema (§10); OTel semantic conventions for AI agents | No native LLM evaluation; requires additional evaluation layer | **Default for all new deployments** |
| **LangSmith** | Strong LangChain integration; good tracing UX | LangChain-specific; limited multi-vendor support | Acceptable for LangChain-native agents only (explicit waiver required) |

**Enterprise decision:** OTel/OTLP is the standard for G-RUN event emission. Arize may be layered on top as the dashboard and evaluation layer. LangSmith is acceptable only for LangChain-native deployments with explicit waiver. The AIGov event schema (§10) is the authoritative record regardless of which dashboard tool is in use.

### 29.2 Minimum viable observability signals per obligation (G-RUN)

| Obligation | Required G-RUN observability signals |
|---|---|
| O1 | Per-tool-call event with tool name, input parameters (redacted), and outcome |
| O2 | PHI detector hit/miss per response; egress destination per API call |
| O3 | Content safety score per response; policy rule triggered (if any) |
| O4 | Protected attribute of requester (where available); fairness-sensitive outcome flag |
| O5 | Source citation count per response; faithfulness score (sampled) |
| O6 | Goal-manifest check result per agent step; capability envelope delta vs G-TEST baseline |
| O7 | Full OTel span per decision; span completeness score (automated) |
| O8 | Review event (reviewer ID, duration, decision, timestamp) per HITL interaction |
| O9 | Attestation expiry check at deploy time; CIM trigger event on change |
| O10 | p50/p95/p99 latency per request; dependency health per external call |
| O11 | Disclosure event per session start; uncertainty fallback invocation count; user override events; misunderstanding signal events (classifier-based) |

### 29.3 Continuous monitoring loop (extended)

```
KB version ingested (RAG deployments)
    │
    ├──► Knowledge FAIR pipeline: readiness checks → O2/O3/O4/O5/O9 G-BUILD events → ledger
    │    (source.kind = "knowledge_fair"; blocks ingest on PHI/conflict FAIL)
    │
Agent runs in prod
    │
    ├──► praktor.ai: O1/O2/O3/O6/O7 enforcement → ledger (source.kind = "praktor")
    │
    ├──► HAI Interaction Monitor: O11 signals → ledger
    │    (disclosure events, uncertainty fallback, override events,
    │     misunderstanding classifier, recovery rate, abandon signature)
    │
    ├──► Latency/SLO monitor: O10 signals → ledger
    │
    └──► Tier 1/2/3 rollup (§16.1) → Scoreboard
         ├── Tier 1 (O3, O5, O11): Response Quality alerts
         ├── Tier 2 (O1, O6, O7, O8, O10): Behavior alerts
         └── Tier 3 (O2, O4, O9): Compliance/business alerts
```

Loop time from agent run to dashboard update: ~90 seconds in v1. Sub-10-second possible with streaming materialization.

### 29.4 Authority boundary: praktor.ai vs Grover

| Source | Authority | `source.kind` | Deduplication rule |
|---|---|---|---|
| praktor.ai | Primary G-RUN emitter | `"praktor"` | Primary record; Scoreboard uses this |
| Knowledge FAIR | G-BUILD gate for RAG obligations (O2, O3, O4, O5, O9) | `"knowledge_fair"` | G-BUILD enforcement point only; additive to praktor events |
| Grover | Secondary: monitoring and spot-checks only | `"grover"` | Never overwrites praktor events; additive only |
| ELLMo | G-TEST judge evaluation only | `"ellmo"` | G-TEST enforcement point only |

**Deduplication rule:** If two events share the same `(obligation_id, enforcement_point, agent_version, window_start)` tuple, the event with `source.kind = "praktor"` is authoritative. Grover events with the same tuple are stored with `duplicate_flag = true` and excluded from Scoreboard aggregation.

### 29.5 Grover integration

Grover is the Humana continuous monitoring agent deployed by IT/Platform. Its responsibilities, distinct from praktor.ai:

- Polling the AIGov ledger for AMBER and RED status transitions
- Routing violation alerts to Slack/PagerDuty per §18
- Scheduling spot-check reviews for O3, O5, O11 LLaJ monitoring (§26.6)
- Triggering Golden Dataset TTL checks (§28.4)

Grover emits monitoring events to `fact_obligation_event` with `source.kind = "grover"` per the authority boundary in §29.4.

---

## 30. Knowledge FAIR Integration

**Knowledge FAIR (Framework for AI Readiness)** is the enterprise-scale AI readiness and ingestion pipeline for generative AI knowledge retrieval use cases (Watchtower/KBS, Matt Rockwood, 2026-02-26). It is "the first stop for any data desired in a Gen AI knowledge retrieval use case."

FAIR checks knowledge before it enters the retrieval pipeline. AIGov records whether those checks passed. The obligations stay the same — FAIR is the upstream precondition that makes the RAG-facing obligations achievable.

### 30.1 What FAIR checks

| FAIR check | Description | AIGov tag |
|---|---|---|
| File extension | Supported format for parsing and chunking | `FAIR.DOC_QUALITY` |
| Metadata schema | Conformation to required metadata fields | `FAIR.METADATA` |
| Inter/intra-document conflict | Contradictions within or across documents | `FAIR.CONFLICT` |
| Undefined acronyms | Unexplained abbreviations that degrade retrieval | `FAIR.DOC_QUALITY` |
| Agent scripts / disclaimers / sample text | Boilerplate content that contaminates retrieval | `FAIR.DOC_QUALITY` |
| Post-parsing quality | Parsing fidelity; tables, graphics without captions | `FAIR.DOC_QUALITY` |
| Post-chunking quality | Chunk coherence and retrieval fitness | `FAIR.CHUNKING` |
| Staleness detection | Document freshness vs. declared TTL | `FAIR.STALENESS` |
| PHI / PII scan | Personal or protected health information in knowledge content | `FAIR.PHI` |
| Demographic representation | Balance across protected attributes in knowledge corpus | `FAIR.METADATA` |

FAIR runs produce a **readiness score** (0–1 per check category) and an overall **FAIR readiness grade** for the KB version. A FAIR run ID is issued per ingest batch.

### 30.2 FAIR → obligation wiring

FAIR integrates at **G-BUILD** as an upstream precondition. It does not add new obligations; it gates existing ones for RAG deployments.

| FAIR check | O2 | O3 | O4 | O5 | O9 | Consequence if FAIL |
|---|---|---|---|---|---|---|
| PHI scan | ✓ | | | | | KB ingest **blocked**; O2 G-BUILD = FAIL |
| CONFLICT | | ✓ | | ✓ | | KB ingest **blocked** (O3); O5 G-BUILD = FAIL |
| DOC_QUALITY | | ✓ | | ✓ | | KB ingest **blocked** (O3); O5 G-BUILD = FAIL |
| METADATA | | | ✓ | ✓ | ✓ | O4: demographic review required; O5/O9: G-BUILD = FAIL |
| STALENESS | | | | ✓ | ✓ | O5 Memory Freshness gate triggers; O9: MAJOR CIM event |
| CHUNKING | | | | ✓ | ✓ | O5 G-BUILD = FAIL; O9: MAJOR CIM event |

**KB ingest blocked** means the FAIR pipeline halts document ingestion to the Knowledge Base Service. The existing KB version remains in production. An AIGov G-BUILD FAIL event is emitted with `source.kind = "knowledge_fair"`.

### 30.3 FAIR events in the ledger

FAIR runs emit standard AIGov `ObligationEvent` records. No schema change required.

```json
{
  "schema_version": "1.1",
  "event_id": "01HY3K9QZR...",
  "event_ts": "2026-05-05T08:00:00Z",
  "tenant_id": "acme-health",
  "agent_id": "clinical-triage-v2",
  "agent_version": "2.3.1",
  "obligation_id": "O5",
  "enforcement_point": "G-BUILD",
  "measurement_technique": "FAIR.1.0",
  "predicate_result": "PASS",
  "evidence": {
    "uri": "s3://aigov-evidence/acme-health/fair-runs/2026/05/05/fair-run-0142.json",
    "sha256": "a3f1...d9",
    "size_bytes": 14820,
    "redacted": false
  },
  "regulatory_tags": ["FAIR.METADATA", "FAIR.CONFLICT", "FAIR.STALENESS", "FAIR.CHUNKING", "EU_AI_ACT.Art9"],
  "source": {
    "kind": "knowledge_fair",
    "version": "1.0.0",
    "host": "fair-pipeline-worker-01"
  },
  "kb_version": "mentor-docs-v2026-05-05",
  "fair_run_id": "FAIR-2026-0142",
  "fair_readiness_score": 0.94
}
```

Note: `kb_version` and `fair_run_id` are stored in the event's evidence JSON, not as top-level schema fields. The `dim_knowledge_source` dimension joins on `kb_version`.

`source.kind = "knowledge_fair"` follows the authority boundary pattern from §29.4. FAIR events are additive — they do not overwrite praktor.ai events for the same `(obligation_id, enforcement_point)` key.

### 30.4 `dim_knowledge_source` schema

```sql
create table dim_knowledge_source (
  kb_version          varchar primary key,    -- e.g. "mentor-docs-v2026-05-05"
  kb_name             varchar not null,        -- logical KB name
  tenant_id           varchar not null,
  fair_run_id         varchar not null,        -- FAIR-YYYY-NNNN
  ingest_date         date not null,
  fair_readiness_score float,                  -- 0–1 composite score
  metadata_score      float,
  conflict_score      float,
  staleness_pct       float,                   -- % stale entries
  chunking_score      float,
  phi_flag            boolean not null,        -- true = PHI detected, ingest blocked
  doc_quality_score   float,
  doc_count           int,
  chunk_count         int,
  fair_result         varchar not null,        -- PASS / FAIL / PARTIAL
  notes               text
);
```

### 30.5 FAIR evidence pack query

```sql
-- evidence_pack_fair_kb_quality.sql
-- Knowledge FAIR readiness for all KB versions used in evidence-generating O5 events
-- Auditor use: verify that every KB version cited in O5 G-BUILD PASS events
-- met the FAIR readiness threshold at ingest time
select
  f.event_ts,
  f.agent_id,
  f.agent_version,
  f.obligation_id,
  f.enforcement_point,
  f.predicate_result,
  f.evidence_uri,
  f.evidence_sha256,
  ks.kb_version,
  ks.kb_name,
  ks.fair_run_id,
  ks.fair_readiness_score,
  ks.metadata_score,
  ks.conflict_score,
  ks.staleness_pct,
  ks.chunking_score,
  ks.phi_flag,
  ks.fair_result
from {{ ref('fact_obligation_event') }} f
left join {{ ref('dim_knowledge_source') }} ks
  on f.measurement_technique = 'FAIR.1.0'
  and f.tenant_id = ks.tenant_id
where exists(
    select 1 from unnest(f.regulatory_tags) as t where t like 'FAIR.%'
  )
  and f.tenant_id = {{ var('tenant_id') }}
  and f.event_ts between {{ var('period_start') }} and {{ var('period_end') }}
order by f.event_ts;
```

### 30.6 FAIR assertion (dbt test)

```sql
-- assert_fair_gate_on_o5_build_events.sql
-- Every O5 G-BUILD PASS event must reference a FAIR run ID
-- A passing O5 without FAIR provenance is a gap in the governance chain
select
  f.event_id,
  f.agent_id,
  f.event_ts
from {{ ref('fact_obligation_event') }} f
where f.obligation_id = 'O5'
  and f.enforcement_point = 'G-BUILD'
  and f.predicate_result = 'PASS'
  and not exists(
    select 1 from unnest(f.regulatory_tags) as t where t like 'FAIR.%'
  )
```

This test fails if any O5 G-BUILD PASS event lacks a `FAIR.*` regulatory tag. The CI pipeline pages on-call when it fails.

### 30.7 FAIR deployment phases vs. AIGov readiness

| FAIR Phase | Target date | What it delivers | AIGov dependency |
|---|---|---|---|
| Phase 1 — Backend MVP | 2026-03-31 | Automated readiness checks for ~250 Agent Assist KB documents; DB + ADLS pipeline; conflict detection; metadata, chunking, PHI scan | O5 G-BUILD gate can be wired for Agent Assist deployments. FAIR events can be emitted to the ledger once `fair_run_id` is returned by the pipeline. |
| Phase 2 — UI MVP | 2026-07-07 | Self-service web UI; post-parsing/chunking quality; staleness detection; metadata enrichment; doc type identification | O9 KB-version CIM trigger can be automated: FAIR runs on KB update → staleness/chunking score delta → CIM event. |
| Phase 3 — Eval Framework | 2026-09-29 | Semi-automated retrieval evaluation (chunking, embedding, retrieval benchmarks); evaluation report generation | O5 G-TEST can be partially automated using FAIR retrieval benchmarks as the RAGAS faithfulness corpus. FAIR and Golden Dataset (§28) converge here. |

### 30.8 FAIR × Golden Dataset convergence

Knowledge FAIR (Phase 3) produces retrieval evaluation benchmarks across chunking and embedding strategies. The Golden Dataset (§28) is the labeled query set for O5 G-TEST faithfulness measurement. These two are structurally related:

- FAIR generates candidate Q&A pairs from KB content at ingest time (Phase 1: Q&A Generation endpoint).
- Golden Dataset curates and labels a subset of those Q&A pairs with human review.
- FAIR Phase 3 evaluation benchmarks become the automated corpus against which new KB versions are scored.

**Operational recommendation:** Route FAIR Q&A Generation output directly into the Golden Dataset candidate pool (§28). Human reviewers label the candidates. This eliminates the manual effort of writing Golden Dataset queries from scratch and ensures the evaluation set always reflects the live KB.

### 30.9 FAIR × O5 × O9 state diagram

```
New KB version ingested
        │
        ▼
  Knowledge FAIR run
        │
  ┌─────┴──────┐
  │ FAIR PASS  │ FAIR FAIL ──────────────────────────────────────────┐
  └─────┬──────┘                                                     │
        │                                                            │
        ▼                                                            ▼
 O5 G-BUILD PASS event emitted          O5 G-BUILD FAIL event emitted
 source.kind = "knowledge_fair"         O2/O3 ingest BLOCKED (if PHI/conflict)
        │                               Obligation stays RED until remediation
        ▼
 CIM: KB version change assessment
        │
  ┌─────┴──────────────────────┐
  │ FAIR score ≥ prior version │  FAIR score regression
  └─────┬──────────────────────┘    (staleness ↑ or chunking ↓)
        │                                    │
        ▼                                    ▼
 MINOR CIM event                     MAJOR CIM event
 Existing Attestation valid          O5 re-evaluation required (48h)
                                     Attestation renewal blocked until done
```

---

## Change log

| Version | Date | Summary |
|---|---|---|
| 0.8 | 2026-05-05 | Knowledge FAIR integrated as upstream KB quality gate (§30); FAIR wired into O2/O3/O4/O5/O9 enforcement matrix at G-BUILD; dim_knowledge_source and FAIR evidence pack added; FAIR vocabulary (FAIR.*) added to §10.4; TL;DR updated. |
| 0.7 | 2026-05-05 | Full regulatory_tags crosswalk review: EU AI Act Art. 9 added to all obligations; Art. 52/72 added; NIST AI RMF expanded; OWASP LLM Top 10 expanded; GDPR Art. 5/13/44 added; HIPAA §164.308 administrative safeguards added; ISO/IEC 42001 A.6–A.10 expanded; CCPA, ACA §1557, MITRE ATLAS AML.T0054 added. |
| 0.6 | 2026-05-05 | SOC 2 TSC + HITRUST CSF v11.3 crosswalk added; dim_regulation 18 new rows; 3 new evidence pack queries; praktor.ai audit sink SOC2_HITRUST_TAGS mapping. |
| 0.5 | 2026-04-29 | G-DELEGATE promoted to formal 4th enforcement point; all 11 obligations at `implemented`; persona model added (§5); bundle IDs updated; attestation example updated; §24 "Assignment" retired. |
| 0.4 | 2026-04-25 | O11 User Interface Transparency added; maturity ladder introduced; v1.0 crosswalk expanded. |
| 0.3 | 2026-04-14 | Initial obligations catalog O1–O10; Ledger + Scoreboard data model; evidence packs. |
