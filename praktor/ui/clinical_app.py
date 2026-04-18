"""
praktor.ai — Clinical Reasoning UI (Streamlit)

5-step workflow for diabetes HEDIS gap closure with LLM-as-judge evaluation.

Tabs (workflow order):
  1. Dataset   — Synthetic golden dataset: 3 engineered demo members
  2. Predict   — Run the agentic AI to generate gap closure recommendations
  3. Review    — HITL: care manager approves/modifies/rejects recommendations
  4. Evaluate  — LLM judge scores: 5 base dimensions + clinical extensions
  5. Traces    — OTel trajectory waterfall: every ReAct step as a span

Run:
    PYTHONPATH=praktor streamlit run praktor/ui/clinical_app.py
"""

from __future__ import annotations

import asyncio
import os
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).parent.parent          # praktor/
_REPO_ROOT = _ROOT.parent                      # praktor.ai/
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import streamlit as st
from ui.theme import COLORS, urgency_color, urgency_label

st.set_page_config(
    page_title="praktor.ai Clinical",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Agent Skills sidebar metadata
# ---------------------------------------------------------------------------

DEFAULT_TOOLS = [
    "gap_registry", "drug_adherence", "claims_lookup", "ehr_lookup",
    "sdoh_lookup", "outreach_history", "measure_criteria",
]
TOOL_META = {
    "gap_registry":     ("🏥", "Ranked open HEDIS gaps by STARS impact"),
    "drug_adherence":   ("💊", "PDC scores vs 0.80 threshold"),
    "claims_lookup":    ("📋", "Historical claims and service events"),
    "ehr_lookup":       ("🩺", "EHR diagnoses, A1c trend, prescriptions"),
    "sdoh_lookup":      ("🏘️", "Language, barriers, PCP info, pharmacy"),
    "outreach_history": ("📞", "Prior outreach attempts and responses"),
    "measure_criteria": ("📐", "HEDIS measure exclusion criteria"),
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run_async(coro):
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                return pool.submit(asyncio.run, coro).result()
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


def _stars_badge(weight: float) -> str:
    if weight == 3.0:
        return "🟢 3x STARS"
    if weight == 2.0:
        return "🟡 2x STARS"
    return "⚪ 1x STARS"


def _prob_color(p: float) -> str:
    if p >= 0.65:
        return "green"
    if p >= 0.40:
        return "orange"
    return "red"


def _action_icon(action_type: str) -> str:
    icons = {
        "pcp_warm_outreach": "👨‍⚕️",
        "pharmacy_refill_reminder": "💊",
        "scheduling_assist": "📅",
        "telehealth_offer": "💻",
        "member_direct_outreach": "📞",
        "exclusion_flag": "🚫",
        "escalate": "⚠️",
    }
    return icons.get(action_type, "▸")


@st.cache_resource
def _get_store():
    from clinical.data.clinical_store import get_clinical_store
    return get_clinical_store()


@st.cache_resource
def _get_tracker():
    from clinical.evaluation.closure_tracker import get_tracker
    return get_tracker()


@st.cache_data(ttl=30)
def _load_pending_recs(limit: int = 100) -> list[dict]:
    try:
        return _get_tracker().get_review_queue(limit=limit)
    except Exception:
        return []


@st.cache_data(ttl=30)
def _load_member_gaps(member_id_hash: str) -> list[dict]:
    try:
        return _get_store().get_open_gaps(member_id_hash)
    except Exception:
        return []


@st.cache_data(ttl=30)
def _load_member_profile(member_id_hash: str) -> dict | None:
    try:
        return _get_store().get_member(member_id_hash)
    except Exception:
        return None


@st.cache_data(ttl=30)
def _load_labs(member_id_hash: str) -> list[dict]:
    try:
        return _get_store().get_labs(member_id_hash)
    except Exception:
        return []


@st.cache_data(ttl=30)
def _load_outreach(member_id_hash: str) -> list[dict]:
    try:
        return _get_store().get_outreach(member_id_hash)
    except Exception:
        return []


@st.cache_data(ttl=30)
def _load_pdc(member_id_hash: str) -> list[dict]:
    try:
        return _get_store().get_pdc(member_id_hash)
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Tab 1: Dataset
# ---------------------------------------------------------------------------

_DIABETES_STORIES = {
    "D001": {
        "persona": "Maria Lopez",
        "raw_id": "D001",
        "story": "Untested GSD — no A1c in MY 2026 (auto-fail, triple-weighted, inverse). One standing lab order closes the highest-Stars gap. Spanish-speaking, high SDOH.",
        "demo_story": "untested_gsd_cheapest_close",
        "gaps": ["GSD"],
        "stars_exposure": 3.0,
        "highlight": "Cheapest gap to close — 3x Stars leverage for zero-cost lab order.",
        "language": "ES",
        "sdoh": "Housing instability, transportation barrier",
    },
    "D002": {
        "persona": "James Chen",
        "raw_id": "D002",
        "story": "A1c 8.7% trending up over 18 months on metformin+glipizide (therapeutic inertia). eGFR 52 (CKD 3a), uACR missing → KED gap. SGLT2i eligible (CREDENCE/EMPA-KIDNEY).",
        "demo_story": "therapeutic_inertia_sglt2i",
        "gaps": ["GSD", "KED"],
        "stars_exposure": 4.0,
        "highlight": "Clinical depth: inertia detection + SGLT2i/CREDENCE recommendation.",
        "language": "EN",
        "sdoh": "None identified",
    },
    "D003": {
        "persona": "Patricia Williams",
        "raw_id": "D003",
        "story": "Four open gaps: GSD + KED + SPD-E + EED-E. No A1c, no kidney labs, no statin, eye exam expired. One comprehensive PCP visit closes all four.",
        "demo_story": "gap_stacking_four_measures",
        "gaps": ["GSD", "KED", "SPD-E", "EED-E"],
        "stars_exposure": 6.0,
        "highlight": "Gap-stacking: 6x Stars exposure closed in one touchpoint.",
        "language": "EN",
        "sdoh": "Limited English proficiency (secondary)",
    },
}

_MY2026_MEASURES = [
    ("GSD", "Glycemic Status Assessment", "3x ⚠️ INVERSE", "A1c or GMI result required. Missing = poor control = Stars penalty. Untested = auto-fail."),
    ("KED", "Kidney Health Evaluation",  "1x", "BOTH eGFR AND uACR required. eGFR-only = FAIL. Single blood draw closes both."),
    ("EED-E", "Eye Exam (ECDS)", "1x", "Retinal/dilated exam by eye care professional. Teleophthalmology compliant."),
    ("SPD-E", "Statin Therapy (ECDS)", "1x", "PDC ≥ 0.80 for statins. All T2D age 40–75 w/o ASCVD. 90-day fills raise PDC 10–15 pts."),
    ("BPD-E", "Blood Pressure Control (ECDS)", "1x", "Most recent BP < 140/90. RPM readings now measure-compliant in MY 2026."),
]


def tab_dataset():
    st.subheader("📊 Golden Dataset")
    st.caption(
        "**Step 1 of 5** · Three synthetic members engineered to demonstrate "
        "specific clinical reasoning patterns. Seed this data before running the agent."
    )

    # Seed data button
    col_seed, col_spacer = st.columns([2, 3])
    with col_seed:
        if st.button("🌱 Seed demo data", key="seed_btn", use_container_width=True,
                     help="Run init scripts to populate the clinical store"):
            with st.spinner("Seeding demo data…"):
                import subprocess
                env = {**os.environ, "PYTHONPATH": "praktor"}
                r1 = subprocess.run(
                    ["python", "scripts/init_member_brain.py", "--seed-demo"],
                    capture_output=True, text=True, env=env, cwd=str(_REPO_ROOT),
                )
                r2 = subprocess.run(
                    ["python", "scripts/init_diabetes_demo.py"],
                    capture_output=True, text=True, env=env, cwd=str(_REPO_ROOT),
                )
            if r1.returncode == 0 and r2.returncode == 0:
                st.success("Demo data seeded.")
                st.cache_data.clear()
            else:
                st.error("Seed failed — see details below.")
                if r1.returncode != 0:
                    st.code(r1.stderr or r1.stdout, language="text")
                if r2.returncode != 0:
                    st.code(r2.stderr or r2.stdout, language="text")

    st.divider()

    # Member cards
    from clinical.schemas import hash_member_id
    for raw_id, info in _DIABETES_STORIES.items():
        member_hash = hash_member_id(raw_id)
        profile = _load_member_profile(member_hash)
        gaps = _load_member_gaps(member_hash)
        labs = _load_labs(member_hash)

        with st.container(border=True):
            col_profile, col_clinical = st.columns([1, 2])

            with col_profile:
                uc = urgency_color(info["stars_exposure"])
                ul = urgency_label(info["stars_exposure"])
                st.markdown(
                    f'<span style="background:{uc};color:white;padding:2px 8px;'
                    f'border-radius:3px;font-size:12px;font-weight:bold">'
                    f'★ {info["stars_exposure"]:.0f}x STARS · {ul}</span>',
                    unsafe_allow_html=True,
                )
                st.markdown(f"### {raw_id} — {info['persona']}")
                st.markdown(f"Lang: **{info['language']}** · SDOH: _{info['sdoh']}_")
                for g in info["gaps"]:
                    st.markdown(f"- Gap: `{g}`")
                st.caption(f"💡 {info['highlight']}")

            with col_clinical:
                st.markdown(info["story"])

                if gaps:
                    st.markdown("**Open gaps (live)**")
                    for g in gaps:
                        w = g["stars_weight"]
                        pdc_info = f" · PDC={g['pdc_current']:.2f}" if g.get("pdc_current") else ""
                        st.markdown(
                            f"  {_stars_badge(w)} **{g['measure_id']}** "
                            f"· {g['days_remaining']}d remaining{pdc_info}"
                        )

                if labs:
                    st.markdown("**Recent labs**")
                    for lab in labs[:4]:
                        val = (
                            f"{lab['result_value']} {lab.get('result_unit', '')}".strip()
                            if lab.get("result_value") else lab.get("result_text", "N/A")
                        )
                        st.caption(f"`{lab['test_date']}` {lab['test_name']}: {val}")

                if not gaps and not labs:
                    st.caption("No live data — click 'Seed demo data' above.")

    # Reference material (collapsed by default)
    st.divider()
    with st.expander("📋 MY 2026 Diabetes Measure Reference", expanded=False):
        for mid, name, weight, note in _MY2026_MEASURES:
            c1, c2, c3, c4 = st.columns([1, 2, 1, 4])
            c1.markdown(f"**{mid}**")
            c2.markdown(name)
            c3.caption(weight)
            c4.caption(note)

    with st.expander("🪜 ADA 2024 Escalation Ladder", expanded=False):
        steps = [
            ("Step 1", "Metformin monotherapy",   "First-line for T2D. A1c reduction ~1.5–2.0%."),
            ("Step 2", "Add GLP-1 RA",             "BMI ≥27 or CV benefit needed. A1c reduction ~1.0–1.5%."),
            ("Step 3", "Add SGLT2i",               "CKD (eGFR 20–60 + uACR >200) or HFrEF. CREDENCE, EMPA-KIDNEY, DAPA-CKD."),
            ("Step 4", "Basal insulin",            "A1c >10% on dual therapy."),
            ("Step 5", "Basal-bolus insulin",      "A1c >9% on optimized basal. Consider endocrinology referral."),
        ]
        for step, name, detail in steps:
            c1, c2, c3 = st.columns([1, 2, 4])
            c1.caption(step)
            c2.markdown(f"**{name}**")
            c3.caption(detail)


# ---------------------------------------------------------------------------
# Tab 2: Predict
# ---------------------------------------------------------------------------

def tab_predict():
    st.subheader("🤖 Predict")
    st.caption(
        "**Step 2 of 5** · Run the agentic AI system to generate gap closure "
        "recommendations. Predictions are saved to the review queue."
    )

    # Configuration row
    col_agent, col_member, col_model, col_dry = st.columns([2, 2, 2, 1])
    with col_agent:
        agent_choice = st.selectbox(
            "Agent",
            ["Diabetes HEDIS (MY 2026)", "HEDIS Gap"],
            key="pred_agent",
        )
    with col_member:
        member_opts = {
            "All members (D001–D003)": None,
            "D001 — Maria Lopez": 0,
            "D002 — James Chen": 1,
            "D003 — Patricia Williams": 2,
        }
        selected_member_label = st.selectbox("Member", list(member_opts.keys()), key="pred_member")
        member_idx = member_opts[selected_member_label]
    with col_model:
        model = st.text_input("LLM model", value=os.getenv("PRAKTOR_MODEL", "llama3:8b"), key="pred_model")
    with col_dry:
        st.write("")
        dry_run = st.checkbox("Dry run", value=True, key="pred_dry",
                              help="No LLM call — uses pre-defined demo responses")

    run_btn = st.button("▶ Run agent", key="pred_run", type="primary", use_container_width=True)
    active = st.session_state.get("agent_tools", DEFAULT_TOOLS)
    if set(active) != set(DEFAULT_TOOLS):
        st.caption(f"Active tools: {len(active)} / {len(DEFAULT_TOOLS)} — edit in sidebar")

    if run_btn:
        is_diabetes = agent_choice.startswith("Diabetes")
        script = "scripts/demo_diabetes_agent.py" if is_diabetes else "scripts/demo_hedis_agent.py"
        cmd = ["python", script, "--model", model]
        if dry_run:
            cmd.append("--dry-run")
        if member_idx is not None:
            cmd += ["--member", str(member_idx)]
        if set(active) != set(DEFAULT_TOOLS):
            cmd += ["--tools", ",".join(active)]

        env = {**os.environ, "PYTHONPATH": "praktor"}

        with st.spinner(f"Running {agent_choice} agent…"):
            import subprocess
            import re as _re
            result = subprocess.run(
                cmd, capture_output=True, text=True,
                env=env, cwd=str(_REPO_ROOT),
            )

        if result.returncode == 0:
            st.success("Agent run complete. Recommendations saved to the review queue.")
            ansi_escape = _re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
            clean = ansi_escape.sub("", result.stdout)
            with st.expander("▾ Agent output", expanded=True):
                st.code(clean, language="text")
            st.info("Switch to the **✅ Review** tab to approve recommendations.")
            st.cache_data.clear()
        else:
            st.error("Agent run failed.")
            st.code(result.stderr or result.stdout, language="text")
            st.caption(
                "If you see import errors, make sure demo data is seeded: "
                "go to the **📊 Dataset** tab and click 'Seed demo data'."
            )


# ---------------------------------------------------------------------------
# Tab 3: Review (HITL)
# ---------------------------------------------------------------------------

def _render_rec_detail(rec: dict):
    cols = st.columns([2, 2, 1])
    cols[0].markdown(f"**Action:** `{rec.get('action_type')}`")
    cols[1].markdown(f"**Measure:** {rec.get('measure_id')}")
    cols[2].markdown(f"**Priority:** {rec.get('priority_score', 0):.2f}")

    if rec.get("rationale"):
        st.markdown("**Rationale:**")
        st.info(rec["rationale"])

    if rec.get("draft_content"):
        st.markdown(f"**Draft message ({rec.get('language', 'en').upper()}):**")
        edited = st.text_area(
            "Edit message before approving",
            value=rec["draft_content"],
            height=100,
            key=f"draft_{rec['id']}",
            label_visibility="collapsed",
        )
    else:
        edited = ""

    notes = st.text_input(
        "Notes (optional)",
        key=f"notes_{rec['id']}",
        placeholder="Reason for modification or rejection…",
    )

    c1, c2, c3 = st.columns(3)
    if c1.button("✅ Approve", key=f"approve_{rec['id']}", type="primary"):
        _get_tracker().record_care_mgr_action(
            rec["id"], "approved", notes=notes,
            modified_content=edited if edited != rec.get("draft_content", "") else None,
        )
        st.success("Approved and sent to outreach queue.")
        st.cache_data.clear()
        st.rerun()

    if c2.button("✏️ Modify", key=f"modify_{rec['id']}"):
        _get_tracker().record_care_mgr_action(
            rec["id"], "modified", notes=notes, modified_content=edited,
        )
        st.info("Saved with modifications.")
        st.cache_data.clear()
        st.rerun()

    if c3.button("❌ Reject", key=f"reject_{rec['id']}"):
        _get_tracker().record_care_mgr_action(rec["id"], "rejected", notes=notes)
        st.warning("Recommendation rejected.")
        st.cache_data.clear()
        st.rerun()

    if rec.get("span_id"):
        st.caption(f"Reasoning trace: `{rec['span_id']}`")


def tab_review():
    st.subheader("✅ Review")
    st.caption(
        "**Step 3 of 5** · Care manager reviews each recommendation. "
        "Approve to send to outreach, modify to adjust the draft, or reject."
    )

    col_filter, col_refresh = st.columns([4, 1])
    with col_filter:
        action_filter = st.selectbox(
            "Filter by action type",
            ["All", "pharmacy_refill_reminder", "pcp_warm_outreach",
             "scheduling_assist", "telehealth_offer", "escalate"],
            key="review_filter",
        )
    with col_refresh:
        if st.button("Refresh", key="review_refresh", use_container_width=True):
            st.cache_data.clear()

    recs = _load_pending_recs(100)
    if action_filter != "All":
        recs = [r for r in recs if r.get("action_type") == action_filter]

    if not recs:
        st.info(
            "Queue is empty. Go to the **🤖 Predict** tab to run the agent and generate recommendations."
        )
        # Show closure stats if any exist
        try:
            stats = _get_tracker().get_stats(hours=24 * 90)
            if stats["total_resolved"] > 0:
                st.divider()
                st.markdown("**Historical closure summary**")
                m1, m2, m3 = st.columns(3)
                m1.metric("Total resolved", stats["total_resolved"])
                m2.metric("Closed", stats["closed"])
                m3.metric("Closure rate", f"{stats['closure_rate']:.0%}")
        except Exception:
            pass
        return

    # Summary metrics
    triple = sum(1 for r in recs if r.get("measure_id") in ("MAC", "MAD", "MAP", "GSD"))
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Pending reviews", len(recs))
    m2.metric("High-weight gaps", triple, help="Triple-weighted: MAC/MAD/MAP/GSD — 3x Stars impact")
    m3.metric("Avg closure prob", f"{sum(r.get('closure_probability', 0) for r in recs)/len(recs):.0%}")
    try:
        stats = _get_tracker().get_stats(hours=24 * 90)
        m4.metric("Historical closure rate", f"{stats['closure_rate']:.0%}")
    except Exception:
        m4.metric("Historical closure rate", "—")

    st.divider()

    for i, rec in enumerate(recs):
        measure_id = rec.get("measure_id", "?")
        action = rec.get("action_type", "unknown")
        prob = rec.get("closure_probability", 0.0)
        lang = rec.get("language", "en")
        member_short = rec.get("member_id_hash", "")[:12]

        weight = 3.0 if measure_id in ("MAC", "MAD", "MAP", "GSD") else \
                 2.0 if measure_id == "CBP" else 1.0

        label = (
            f"{_action_icon(action)} **{measure_id}** · {_stars_badge(weight)} · "
            f"Member `{member_short}…` · "
            f"Prob: :{_prob_color(prob)}[{prob:.0%}] · {lang.upper()}"
        )

        with st.expander(label, expanded=(i == 0)):
            _render_rec_detail(rec)


# ---------------------------------------------------------------------------
# Tab 4: Evaluate
# ---------------------------------------------------------------------------

_BASE_CRITERIA = ["accuracy", "completeness", "relevance", "conciseness", "clarity"]
_HEDIS_CRITERIA = ["gap_identification_accuracy", "action_appropriateness",
                   "evidence_citation_quality", "safety_flag_coverage"]
_DIABETES_CRITERIA = ["inertia_detection_accuracy", "escalation_ladder_correctness",
                      "gap_stacking_completeness", "evidence_anchor_quality",
                      "safety_exclusion_coverage"]

_CRITERION_LABELS = {
    "accuracy": "Accuracy",
    "completeness": "Completeness",
    "relevance": "Relevance",
    "conciseness": "Conciseness",
    "clarity": "Clarity",
    "gap_identification_accuracy": "Gap ID",
    "action_appropriateness": "Action Fit",
    "evidence_citation_quality": "Evidence",
    "safety_flag_coverage": "Safety",
    "inertia_detection_accuracy": "Inertia",
    "escalation_ladder_correctness": "Escalation",
    "gap_stacking_completeness": "Gap Stack",
    "evidence_anchor_quality": "Evidence Anchor",
    "safety_exclusion_coverage": "Exclusions",
}


def _score_color(score: float | None) -> str:
    if score is None:
        return "gray"
    if score >= 8.0:
        return "green"
    if score >= 6.0:
        return "orange"
    return "red"


def _score_bar(score: float | None, max_width: int = 100) -> str:
    if score is None:
        return ""
    pct = int(score / 10 * max_width)
    hex_map = {
        "green":  COLORS["status_ok"],
        "orange": COLORS["status_warn"],
        "red":    COLORS["status_err"],
        "gray":   COLORS["status_muted"],
    }
    color = hex_map[_score_color(score)]
    label = f"Score: {score:.1f}/10"
    return (
        f'<div style="background:#eee;border-radius:3px;height:8px;width:{max_width}px" '
        f'aria-label="{label}" role="img">'
        f'<div style="background:{color};height:8px;width:{pct}px;border-radius:3px"></div>'
        f'</div>'
    )


@st.cache_data(ttl=30)
def _load_judge_evals(
    hours: float = 168,
    agent: str | None = None,
    judge_type: str | None = None,
    limit: int = 200,
) -> list[dict]:
    db_path = os.getenv(
        "PRAKTOR_MONITORING_DB",
        str(Path.home() / ".praktor" / "monitoring.db"),
    )
    if not Path(db_path).exists():
        return []
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        since = time.time() - hours * 3600
        clauses = ["timestamp >= ?"]
        params: list[Any] = [since]
        if agent:
            clauses.append("agent_type = ?")
            params.append(agent)
        if judge_type:
            clauses.append("judge_type = ?")
            params.append(judge_type)
        where = " AND ".join(clauses)
        rows = conn.execute(
            f"SELECT * FROM judge_evals WHERE {where} ORDER BY timestamp DESC LIMIT ?",
            params + [limit],
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception:
        return []


@st.cache_data(ttl=60)
def _judge_distinct_agents() -> list[str]:
    db_path = os.getenv(
        "PRAKTOR_MONITORING_DB",
        str(Path.home() / ".praktor" / "monitoring.db"),
    )
    if not Path(db_path).exists():
        return []
    try:
        conn = sqlite3.connect(db_path)
        rows = conn.execute(
            "SELECT DISTINCT agent_type FROM judge_evals ORDER BY agent_type"
        ).fetchall()
        conn.close()
        return [r[0] for r in rows]
    except Exception:
        return []


def tab_evaluate():
    st.subheader("⚖️ Evaluate")
    st.caption(
        "**Step 4 of 5** · LLM judge scores predictions on 5 base performance dimensions. "
        "Clinical and diabetes agents add domain-specific criteria on top."
    )

    # Dimension reference
    with st.expander("📐 Evaluation Dimensions", expanded=False):
        st.markdown("**Base (all agents) — 5 criteria**")
        base_cols = st.columns(5)
        descs = {
            "accuracy": "Is the answer correct?",
            "completeness": "Is required info included?",
            "relevance": "Does it address the question?",
            "conciseness": "Is it appropriately brief?",
            "clarity": "Is it clear and easy to understand?",
        }
        for col, crit in zip(base_cols, _BASE_CRITERIA):
            col.metric(_CRITERION_LABELS[crit], "0–10")
            col.caption(descs[crit])

        st.markdown("**HEDIS clinical extensions** (`hedis_gap` agent) — 4 criteria")
        h_cols = st.columns(4)
        h_descs = {
            "gap_identification_accuracy": "Right gap, right reason",
            "action_appropriateness": "Right action for this member",
            "evidence_citation_quality": "Grounded in member record",
            "safety_flag_coverage": "Exclusions + contraindications",
        }
        for col, crit in zip(h_cols, _HEDIS_CRITERIA):
            col.metric(_CRITERION_LABELS[crit], "0–10")
            col.caption(h_descs[crit])

        st.markdown("**Diabetes extensions** (`diabetes_hedis` agent) — 5 criteria")
        d_cols = st.columns(5)
        d_descs = {
            "inertia_detection_accuracy": "Inertia correctly flagged?",
            "escalation_ladder_correctness": "Right ADA 2024 step?",
            "gap_stacking_completeness": "All closable gaps found?",
            "evidence_anchor_quality": "CREDENCE/UKPDS/CARDS cited?",
            "safety_exclusion_coverage": "ESRD/hospice/ASCVD checked?",
        }
        for col, crit in zip(d_cols, _DIABETES_CRITERIA):
            col.metric(_CRITERION_LABELS[crit], "0–10")
            col.caption(d_descs[crit])

    st.divider()

    # On-demand evaluation panel — promoted above the historical log
    with st.expander("🔬 On-demand evaluation", expanded=False):
        st.caption("Paste any agent response to score it with the LLM judge.")
        with st.form("judge_eval_form"):
            col_at, col_jt = st.columns(2)
            with col_at:
                eval_agent = st.selectbox(
                    "Agent type",
                    ["hedis_gap", "diabetes_hedis", "general"],
                    key="eval_agent_type",
                )
            with col_jt:
                eval_model = st.text_input("Judge model", value="llama3:8b", key="eval_model")

            eval_question = st.text_area("Question / task prompt", height=80,
                                         placeholder="What should the care manager do for member X?",
                                         key="eval_question")
            eval_response = st.text_area("Agent response to evaluate", height=200,
                                         placeholder="ACTION_TYPE: pcp_warm_outreach\nRATIONALE: ...",
                                         key="eval_response")
            eval_context = st.text_area("Member context (optional, de-identified)", height=80,
                                        placeholder="Member has GSD open, A1c 8.7%, eGFR 52...",
                                        key="eval_context")
            submitted = st.form_submit_button("▶ Run judge evaluation")

        if submitted and eval_response.strip():
            with st.spinner("Running LLM judge..."):
                try:
                    async def _run_judge():
                        if eval_agent == "diabetes_hedis":
                            from clinical.evaluation.diabetes_hedis_judge import DiabetesHEDISJudge
                            j = DiabetesHEDISJudge(model=eval_model)
                            return await j.evaluate(eval_response, eval_context or "(none)")
                        elif eval_agent == "hedis_gap":
                            from clinical.evaluation.hedis_judge import HEDISJudge
                            j = HEDISJudge(model=eval_model)
                            return await j.evaluate(eval_response, eval_context or "(none)")
                        else:
                            from core.judge import JudgeEvaluator
                            j = JudgeEvaluator(model=eval_model)
                            return await j.evaluate(eval_question, eval_response)

                    result = _run_async(_run_judge())

                    st.success("Evaluation complete")
                    st.metric("Overall score", f"{result.overall:.1f}/10")

                    st.markdown("**Base performance dimensions**")
                    b_cols = st.columns(5)
                    for col, crit in zip(b_cols, _BASE_CRITERIA):
                        val = (result.criteria.get(crit)
                               if hasattr(result, "criteria")
                               else getattr(result, crit, None))
                        col.metric(_CRITERION_LABELS[crit],
                                   f"{val:.1f}" if val is not None else "—")

                    if eval_agent == "hedis_gap":
                        st.markdown("**HEDIS clinical extensions**")
                        h_cols = st.columns(4)
                        for col, crit in zip(h_cols, _HEDIS_CRITERIA):
                            val = getattr(result, crit, None)
                            col.metric(_CRITERION_LABELS[crit],
                                       f"{val:.1f}" if val is not None else "—")
                    elif eval_agent == "diabetes_hedis":
                        st.markdown("**Diabetes extensions**")
                        d_cols = st.columns(5)
                        for col, crit in zip(d_cols, _DIABETES_CRITERIA):
                            val = getattr(result, crit, None)
                            col.metric(_CRITERION_LABELS[crit],
                                       f"{val:.1f}" if val is not None else "—")

                    st.caption(f"Reasoning: {result.reasoning}")

                except Exception as e:
                    st.error("Judge evaluation failed.")
                    with st.expander("Show details"):
                        st.code(str(e), language="text")
                    st.caption("Ensure the LLM model is running (Ollama) or ANTHROPIC_API_KEY is set.")

    st.divider()

    # Historical evaluation log — filters
    col_a, col_j = st.columns([3, 3])
    with col_a:
        agents = _judge_distinct_agents()
        agent_opts = ["All agents"] + agents
        sel_agent = st.selectbox("Agent", agent_opts, key="judge_agent")
        agent_filter = None if sel_agent == "All agents" else sel_agent
    with col_j:
        jtype_opts = ["All types", "general", "hedis", "diabetes_hedis"]
        sel_jtype = st.selectbox("Judge type", jtype_opts, key="judge_type")
        jtype_filter = None if sel_jtype == "All types" else sel_jtype

    col_h, col_lim, col_ref = st.columns([2, 1, 1])
    with col_h:
        hours = st.selectbox("Time window", [1, 6, 24, 168, 720], index=2,
                             format_func=lambda h: f"Last {h}h", key="judge_hours")
    with col_lim:
        limit = st.number_input("Rows", min_value=10, max_value=500, value=100,
                                step=10, key="judge_limit")
    with col_ref:
        st.write("")
        if st.button("Refresh", key="judge_refresh", use_container_width=True):
            st.cache_data.clear()

    evals = _load_judge_evals(float(hours), agent_filter, jtype_filter, int(limit))

    if not evals:
        st.info(
            "No judge evaluations yet.\n\n"
            "Run the agent (**🤖 Predict**), then use the **🔬 On-demand evaluation** panel above to score a response."
        )
    else:
        # Summary metrics
        base_scores = [
            sum(r.get(c) or 0 for c in _BASE_CRITERIA) / len(_BASE_CRITERIA)
            for r in evals if any(r.get(c) is not None for c in _BASE_CRITERIA)
        ]
        overall_scores = [r["score"] for r in evals]
        hedis_evals = [r for r in evals if r.get("judge_type") == "hedis"]
        dm_evals = [r for r in evals if r.get("judge_type") == "diabetes_hedis"]

        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("Total evals", len(evals))
        m2.metric("Avg overall", f"{sum(overall_scores)/len(overall_scores):.1f}/10"
                  if overall_scores else "—")
        m3.metric("Avg base score", f"{sum(base_scores)/len(base_scores):.1f}/10"
                  if base_scores else "—")
        m4.metric("HEDIS evals", len(hedis_evals))
        m5.metric("Diabetes evals", len(dm_evals))

        st.divider()

        # Per-agent heatmap
        if not agent_filter or len(set(r["agent_type"] for r in evals)) > 1:
            st.markdown("### Per-agent average scores")
            agent_groups: dict[str, list[dict]] = {}
            for r in evals:
                agent_groups.setdefault(r["agent_type"], []).append(r)

            header_cols = st.columns([2] + [1] * len(_BASE_CRITERIA))
            header_cols[0].markdown("**Agent**")
            for i, crit in enumerate(_BASE_CRITERIA):
                header_cols[i + 1].markdown(f"**{_CRITERION_LABELS[crit]}**")

            for agent_name, rows in sorted(agent_groups.items()):
                avg_cols = st.columns([2] + [1] * len(_BASE_CRITERIA))
                avg_cols[0].markdown(f"`{agent_name}`  ({len(rows)} evals)")
                for i, crit in enumerate(_BASE_CRITERIA):
                    vals = [r.get(crit) for r in rows if r.get(crit) is not None]
                    avg = sum(vals) / len(vals) if vals else None
                    color = _score_color(avg)
                    avg_cols[i + 1].markdown(
                        f":{color}[**{avg:.1f}**]" if avg is not None else ":gray[—]"
                    )

            st.divider()

        # Evaluation log
        st.markdown(f"### Evaluation log ({len(evals)} entries)")
        for i, row in enumerate(evals):
            ts = datetime.fromtimestamp(row["timestamp"]).strftime("%m-%d %H:%M")
            jtype = row.get("judge_type", "general")
            overall = row.get("score", 0)
            color = _score_color(overall)
            label = (
                f":{color}[**{overall:.1f}**] "
                f"`{row['agent_type']}` · `{jtype}` · {ts}"
            )

            with st.expander(label, expanded=(i == 0)):
                st.markdown("**Base performance dimensions**")
                base_cols = st.columns(len(_BASE_CRITERIA))
                for col, crit in zip(base_cols, _BASE_CRITERIA):
                    val = row.get(crit)
                    col.metric(_CRITERION_LABELS[crit],
                               f"{val:.1f}" if val is not None else "—")

                ext_criteria = []
                if jtype == "hedis":
                    ext_criteria = _HEDIS_CRITERIA
                    st.markdown("**HEDIS clinical extensions**")
                elif jtype == "diabetes_hedis":
                    ext_criteria = _DIABETES_CRITERIA
                    st.markdown("**Diabetes extensions**")

                if ext_criteria:
                    ext_cols = st.columns(len(ext_criteria))
                    for col, crit in zip(ext_cols, ext_criteria):
                        val = row.get(crit)
                        col.metric(_CRITERION_LABELS[crit],
                                   f"{val:.1f}" if val is not None else "—")

                if row.get("reasoning"):
                    st.caption(f"Reasoning: {row['reasoning']}")
                if row.get("question"):
                    st.caption(f"Input: {row['question'][:200]}")



# ---------------------------------------------------------------------------
# Tab 5: Traces
# ---------------------------------------------------------------------------

def _monitoring_db_path() -> str:
    return os.getenv(
        "PRAKTOR_MONITORING_DB",
        str(Path.home() / ".praktor" / "monitoring.db"),
    )


@st.cache_data(ttl=15)
def _tracer_query_runs(
    hours: float, agent_filter: str | None, limit: int
) -> list[dict]:
    db_path = _monitoring_db_path()
    if not Path(db_path).exists():
        return []
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        since = time.time() - hours * 3600
        clauses = ["timestamp >= ?"]
        params: list[Any] = [since]
        if agent_filter:
            clauses.append("agent_type = ?")
            params.append(agent_filter)
        where = " AND ".join(clauses)
        rows = conn.execute(
            f"SELECT * FROM agent_runs WHERE {where} ORDER BY timestamp DESC LIMIT ?",
            params + [limit],
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception:
        return []


@st.cache_data(ttl=15)
def _tracer_query_steps(run_id: int) -> list[dict]:
    db_path = _monitoring_db_path()
    if not Path(db_path).exists():
        return []
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM trajectory_steps WHERE run_id = ? ORDER BY step",
            (run_id,),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception:
        return []


@st.cache_data(ttl=60)
def _tracer_distinct_agents() -> list[str]:
    db_path = _monitoring_db_path()
    if not Path(db_path).exists():
        return []
    try:
        conn = sqlite3.connect(db_path)
        rows = conn.execute(
            "SELECT DISTINCT agent_type FROM agent_runs ORDER BY agent_type"
        ).fetchall()
        conn.close()
        return [r[0] for r in rows]
    except Exception:
        return []


def _fmt_ms(ms: float) -> str:
    if ms >= 1000:
        return f"{ms / 1000:.1f}s"
    return f"{ms:.0f}ms"


def _span_status_badge(status: str) -> str:
    return {"ok": "🟢", "error": "🔴"}.get(status, "🟡")


def _step_kind_icon(kind: str) -> str:
    return {"llm_call": "🧠", "tool_call": "🔧", "improvement_pass": "✨"}.get(kind, "▸")


def _step_bar_color(step: dict) -> str:
    if step.get("error"):
        return COLORS["span_error"]
    if step.get("cached"):
        return COLORS["span_cached"]
    if step.get("kind") == "tool_call":
        return COLORS["span_tool"]
    return COLORS["span_llm"]


def _render_waterfall(run: dict):
    """Render one agent run's span details + trajectory waterfall."""
    c1, c2, c3, c4 = st.columns(4)
    c1.markdown(f"**Session**  \n`{run['session_id'][:16]}…`")
    c2.markdown(f"**Status**  \n{_span_status_badge(run['status'])} {run['status']}")
    c3.markdown(f"**Model**  \n`{run['model']}`")
    c4.markdown(f"**Passes**  \n{run['passes']}")

    token_col, cost_col, cache_col = st.columns(3)
    token_col.markdown(
        f"**Tokens**  \n{run['input_tokens']} in · {run['output_tokens']} out "
        f"· **{run['total_tokens']} total**"
    )
    cost_usd = run.get("cost_usd", 0.0)
    cost_col.markdown(
        f"**Cost**  \n{'$0.00 (local)' if cost_usd == 0 else f'${cost_usd:.5f}'}"
    )
    cache_col.markdown(
        f"**Cache**  \n{'💾 hit' if run.get('cached') else '⚡ miss'}"
    )

    if run.get("error"):
        st.error(f"**Error:** {run['error']}")

    steps = _tracer_query_steps(run["id"])
    if not steps:
        st.caption("No trajectory steps recorded for this run.")
        st.caption(
            "Trajectory steps are written by the monitoring collector. "
            "Run the agent from the **🤖 Predict** tab to generate data."
        )
        return

    st.markdown("---")
    st.markdown(
        f"**Trajectory — {len(steps)} span{'s' if len(steps) != 1 else ''}**  "
        f"&nbsp;&nbsp; 🧠 LLM call &nbsp; 🔧 tool call &nbsp; 💾 cached &nbsp; 🔴 error"
    )

    total_ms = sum(s.get("latency_ms", 0) for s in steps) or 1.0
    offset_ms = 0.0
    for step in steps:
        latency = step.get("latency_ms", 0) or 0
        icon = _step_kind_icon(step.get("kind", ""))
        color = _step_bar_color(step)

        parts = [f"{icon} **step {step['step']}** · `{step['kind']}`"]
        if step.get("tool_name"):
            parts.append(f"tool=**{step['tool_name']}**")
        parts.append(_fmt_ms(latency))
        if step.get("output_tokens"):
            parts.append(f"{step['output_tokens']} tok")
        if step.get("cached"):
            parts.append("💾")
        if step.get("error"):
            parts.append("🔴")

        col_label, col_bar = st.columns([3, 3])
        with col_label:
            st.markdown(" · ".join(parts))
            if step.get("error"):
                st.caption(f"↳ {step['error'][:120]}")

        with col_bar:
            offset_pct = offset_ms / total_ms * 100
            span_pct = max(latency / total_ms * 100, 1.0)
            bar_label = f"Step {step['step']}: {_fmt_ms(latency)} {step.get('kind', '')}"
            st.markdown(
                f'<div style="display:flex;align-items:center;height:20px;margin-top:2px">'
                f'<div style="width:{offset_pct:.1f}%;min-width:0"></div>'
                f'<div style="background:{color};height:16px;width:{span_pct:.1f}%;'
                f'border-radius:3px;min-width:4px" '
                f'aria-label="{bar_label}" role="img"></div>'
                f'</div>',
                unsafe_allow_html=True,
            )

        offset_ms += latency

    st.caption(
        f"Total wall time: {_fmt_ms(run['duration_ms'])} · "
        f"Trajectory span sum: {_fmt_ms(sum(s.get('latency_ms', 0) for s in steps))}"
    )


def tab_tracer():
    st.subheader("🔍 Traces")
    st.caption(
        "**Step 5 of 5** · Every ReAct step (LLM call or tool call) recorded as a span. "
        "Inspect latency, token usage, and cache hits across runs."
    )

    col_f1, col_f2 = st.columns([3, 3])
    with col_f1:
        hours = st.selectbox(
            "Time window", [1, 6, 24, 72, 168], index=2,
            format_func=lambda h: f"Last {h}h",
        )
    with col_f2:
        agents = _tracer_distinct_agents()
        options = ["All agents"] + agents
        default_idx = options.index("hedis_gap") if "hedis_gap" in options else 0
        selected = st.selectbox("Agent", options, index=default_idx)
        agent_filter = None if selected == "All agents" else selected

    col_f3, col_refresh = st.columns([3, 1])
    with col_f3:
        limit = st.number_input("Max rows", min_value=10, max_value=500, value=50, step=10)
    with col_refresh:
        st.write("")
        if st.button("Refresh", key="tracer_refresh", use_container_width=True):
            st.cache_data.clear()

    runs = _tracer_query_runs(float(hours), agent_filter, int(limit))

    if not runs:
        st.info(
            "No runs in the monitoring store yet.\n\n"
            "Go to the **🤖 Predict** tab to run the agent."
        )
        return

    ok = sum(1 for r in runs if r["status"] == "ok")
    errors = len(runs) - ok
    avg_ms = sum(r["duration_ms"] for r in runs) / len(runs)
    p95_idx = max(0, int(len(runs) * 0.95) - 1)
    p95_ms = sorted(r["duration_ms"] for r in runs)[p95_idx]
    total_tokens = sum(r["total_tokens"] for r in runs)
    cache_hits = sum(1 for r in runs if r.get("cached"))

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Runs", len(runs))
    m2.metric("Success rate", f"{ok / len(runs):.0%}",
              delta=f"{errors} errors" if errors else None, delta_color="inverse")
    m3.metric("Avg latency", _fmt_ms(avg_ms))
    m4.metric("P95 latency", _fmt_ms(p95_ms))
    m5.metric("Total tokens", f"{total_tokens:,}")

    if cache_hits:
        st.caption(f"💾 Cache hits: {cache_hits}/{len(runs)} runs  ({cache_hits/len(runs):.0%})")

    st.divider()
    st.markdown(f"**{len(runs)} run{'s' if len(runs) != 1 else ''} — click to expand waterfall**")

    for i, run in enumerate(runs):
        ts = datetime.fromtimestamp(run["timestamp"]).strftime("%Y-%m-%d %H:%M:%S")
        badge = _span_status_badge(run["status"])
        cached_tag = " 💾" if run.get("cached") else ""
        session_short = run["session_id"][:12]
        steps = _tracer_query_steps(run["id"])
        step_tag = f" · {len(steps)} steps" if steps else ""

        label = (
            f"{badge} **{run['agent_type']}** · `{session_short}…` · "
            f"{_fmt_ms(run['duration_ms'])} · {run['total_tokens']} tok"
            f"{cached_tag}{step_tag} · {ts}"
        )

        with st.expander(label, expanded=(i == 0)):
            _render_waterfall(run)


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

def _agent_skills_sidebar():
    has_override = any(
        not st.session_state.get(f"tool_{n}", True) for n in DEFAULT_TOOLS
    )
    with st.expander("🧠 Agent Skills", expanded=has_override):
        if st.button("↺ Reset", key="tool_reset"):
            for name in DEFAULT_TOOLS:
                st.session_state[f"tool_{name}"] = True
            st.rerun()

        for name in DEFAULT_TOOLS:
            emoji, desc = TOOL_META[name]
            c1, c2, c3 = st.columns([1, 4, 1])
            c1.write(emoji)
            c2.markdown(f"**{name}**")
            c2.caption(desc)
            c3.checkbox("", key=f"tool_{name}", value=True, label_visibility="collapsed")

        active = [n for n in DEFAULT_TOOLS if st.session_state.get(f"tool_{n}", True)]
        if not active:
            st.error("Select at least one tool")
            st.session_state["tool_gap_registry"] = True
            active = [n for n in DEFAULT_TOOLS if st.session_state.get(f"tool_{n}", True)]

        if not st.session_state.get("tool_gap_registry", True):
            st.warning("⚠️ Without gap_registry the agent always escalates")

        st.session_state["agent_tools"] = active


def _sidebar():
    with st.sidebar:
        st.markdown("### 🏥 praktor.ai Clinical")
        st.caption("Diabetes HEDIS Gap Closure · MY 2026")
        st.divider()

        st.markdown("**Workflow**")
        st.markdown(
            "1. **📊 Dataset** — view synthetic members\n"
            "2. **🤖 Predict** — run the agent\n"
            "3. **✅ Review** — approve recommendations\n"
            "4. **⚖️ Evaluate** — LLM judge scores\n"
            "5. **🔍 Traces** — inspect spans"
        )
        st.divider()

        try:
            pending = _load_pending_recs(1000)
            triple = sum(
                1 for r in pending
                if r.get("measure_id") in ("MAC", "MAD", "MAP", "GSD")
            )
            st.metric("Pending reviews", len(pending))
            if triple:
                st.metric("High-weight gaps", triple,
                          help="3x Stars: MAC/MAD/MAP/GSD")
        except Exception:
            st.caption("No queue data yet.")

        st.divider()
        st.caption("**Stars triple-weighted:**")
        st.caption("🟢 GSD — Glycemic Status (3x, inverse)")
        st.caption("🟢 MAC — Statin adherence (3x)")
        st.caption("🟢 MAD — Diabetes meds (3x)")
        st.caption("🟢 MAP — RASA hypertension (3x)")
        st.divider()
        _agent_skills_sidebar()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    _sidebar()

    st.title("🏥 praktor.ai Clinical")
    st.caption("Diabetes HEDIS Gap Closure · MY 2026 · Agentic AI with LLM-as-judge")

    tab1, tab2, tab3, tab4, tab5 = st.tabs(
        ["📊 Dataset", "🤖 Predict", "✅ Review", "⚖️ Evaluate", "🔍 Traces"]
    )

    with tab1:
        tab_dataset()

    with tab2:
        tab_predict()

    with tab3:
        tab_review()

    with tab4:
        tab_evaluate()

    with tab5:
        tab_tracer()


if __name__ == "__main__":
    main()
