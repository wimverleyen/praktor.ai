"""
praktor.ai — Clinical Reasoning UI (Streamlit)

HITL review queue for HEDIS gap closure recommendations.

Tabs:
  1. Queue      — care manager review queue ranked by priority
  2. Member     — full member context: gaps, SDOH, outreach, labs
  3. Analytics  — closure rates, STARS impact projection, model performance
  4. Traces     — OTel trajectory waterfall: every ReAct step as a span
  5. Diabetes   — MY 2026 diabetes HEDIS demo: inertia detection, gap-stacking, escalation
  6. Judge      — LLM judge scores: 5 base dimensions + domain extensions, on-demand eval

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

import streamlit as st

_ROOT = Path(__file__).parent.parent          # praktor/
_REPO_ROOT = _ROOT.parent                      # praktor.ai/
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

st.set_page_config(
    page_title="praktor.ai Clinical",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded",
)

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
    """Load pending recommendations for HITL queue. 30s cache."""
    tracker = _get_tracker()
    store = _get_store()
    recs = []
    try:
        with tracker._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM recommendations WHERE care_mgr_action='pending' "
                "ORDER BY priority_score DESC LIMIT ?",
                (limit,),
            ).fetchall()
        recs = [dict(r) for r in rows]
    except Exception:
        pass
    return recs


@st.cache_data(ttl=60)
def _load_member_gaps(member_id_hash: str) -> list[dict]:
    return _get_store().get_open_gaps(member_id_hash)


@st.cache_data(ttl=60)
def _load_member_profile(member_id_hash: str) -> dict | None:
    return _get_store().get_member(member_id_hash)


@st.cache_data(ttl=60)
def _load_labs(member_id_hash: str) -> list[dict]:
    return _get_store().get_labs(member_id_hash, limit=5)


@st.cache_data(ttl=60)
def _load_outreach(member_id_hash: str) -> list[dict]:
    return _get_store().get_outreach(member_id_hash, limit=10)


@st.cache_data(ttl=60)
def _load_pdc(member_id_hash: str) -> list[dict]:
    return _get_store().get_pdc(member_id_hash)


# ---------------------------------------------------------------------------
# Tab 1: HITL Queue
# ---------------------------------------------------------------------------

def tab_queue():
    st.subheader("Care Manager Queue")
    st.caption("Recommendations ranked by STARS priority. Review, modify, and approve.")

    col_filter, col_refresh = st.columns([4, 1])
    with col_filter:
        action_filter = st.selectbox(
            "Filter by action type",
            ["All", "pharmacy_refill_reminder", "pcp_warm_outreach",
             "scheduling_assist", "telehealth_offer", "escalate"],
        )
    with col_refresh:
        if st.button("Refresh", key="queue_refresh", use_container_width=True):
            st.cache_data.clear()

    recs = _load_pending_recs(100)
    if action_filter != "All":
        recs = [r for r in recs if r.get("action_type") == action_filter]

    if not recs:
        st.info(
            "Queue is empty. Run the HEDIS gap agent to generate recommendations:\n\n"
            "```\nPYTHONPATH=praktor python scripts/demo_hedis_agent.py --dry-run\n```"
        )
        return

    triple = sum(1 for r in recs if r.get("measure_id") in ("MAC", "MAD", "MAP"))
    m1, m2, m3 = st.columns(3)
    m1.metric("Pending reviews", len(recs))
    m2.metric("Triple-weighted gaps", triple, help="MAC/MAD/MAP — 3x STARS impact")
    m3.metric("Avg closure prob", f"{sum(r.get('closure_probability', 0) for r in recs)/len(recs):.0%}")

    st.divider()

    for rec in recs:
        measure_id = rec.get("measure_id", "?")
        action = rec.get("action_type", "unknown")
        prob = rec.get("closure_probability", 0.0)
        lang = rec.get("language", "en")
        member_short = rec.get("member_id_hash", "")[:12]

        weight = 3.0 if measure_id in ("MAC", "MAD", "MAP") else \
                 2.0 if measure_id == "CBP" else 1.0

        label = (
            f"{_action_icon(action)} **{measure_id}** · {_stars_badge(weight)} · "
            f"Member `{member_short}…` · "
            f"Prob: :{_prob_color(prob)}[{prob:.0%}] · {lang.upper()}"
        )

        with st.expander(label, expanded=False):
            _render_rec_detail(rec)


def _render_rec_detail(rec: dict):
    cols = st.columns([2, 2, 1])
    cols[0].markdown(f"**Action:** `{rec.get('action_type')}`")
    cols[1].markdown(f"**Measure:** {rec.get('measure_id')} — {rec.get('measure_id')}")
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

    notes = st.text_input(
        "Notes (optional)",
        key=f"notes_{rec['id']}",
        placeholder="Reason for modification or rejection…",
    )

    c1, c2, c3 = st.columns(3)
    if c1.button("✅ Approve", key=f"approve_{rec['id']}", type="primary"):
        _get_tracker().record_care_mgr_action(
            rec["id"], "approved", notes=notes,
            modified_content=edited if edited != rec["draft_content"] else None,
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

    # Show reasoning span if available
    if rec.get("span_id"):
        st.caption(f"Reasoning trace: `{rec['span_id']}`")


# ---------------------------------------------------------------------------
# Tab 2: Member View
# ---------------------------------------------------------------------------

def tab_member():
    st.subheader("Member Context")
    st.caption("Full clinical picture for a specific member. Enter a member hash to load.")

    from clinical.schemas import hash_member_id
    col_input, col_seed = st.columns([3, 1])
    with col_input:
        member_input = st.text_input(
            "Member ID hash (64 chars) or raw ID for demo members",
            placeholder="Enter member_id_hash or DEMO-001 through DEMO-005",
        )
    with col_seed:
        if st.button("Load demo member 1", use_container_width=True):
            member_input = hash_member_id("DEMO-001")
            st.session_state["demo_member"] = member_input

    if "demo_member" in st.session_state:
        member_input = st.session_state["demo_member"]

    if not member_input:
        st.info("Enter a member hash or click 'Load demo member 1'.")
        return

    # Auto-hash short IDs
    if member_input.startswith("DEMO-"):
        member_hash = hash_member_id(member_input)
    elif len(member_input) < 64:
        member_hash = hash_member_id(member_input)
    else:
        member_hash = member_input

    profile = _load_member_profile(member_hash)
    if not profile:
        st.warning(f"Member `{member_hash[:16]}…` not found. Run: `python scripts/init_member_brain.py --seed-demo`")
        return

    # Profile header
    import json
    barriers = json.loads(profile.get("sdoh_barriers") or "[]")
    st.markdown(f"### Member `{member_hash[:16]}…`")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Language", profile.get("language", "en").upper())
    c2.metric("Health literacy", profile.get("health_literacy", "?").title())
    c3.metric("SDOH risk", profile.get("sdoh_risk", "?").title())
    c4.metric("PCP", profile.get("pcp_name", "?"))

    if barriers:
        st.warning(f"SDOH barriers: {', '.join(barriers)}")

    st.divider()

    # Gaps
    gaps = _load_member_gaps(member_hash)
    if gaps:
        st.markdown("**Open HEDIS Gaps**")
        for g in gaps:
            weight = g["stars_weight"]
            pdc_info = f" · PDC={g['pdc_current']:.2f}/{g.get('pdc_threshold', 0.80):.2f}" \
                if g.get("pdc_current") else ""
            st.markdown(
                f"- {_stars_badge(weight)} **{g['measure_id']}**: {g['measure_name']}"
                f" · {g['days_remaining']}d remaining{pdc_info}"
            )

    # PDC scores
    pdc_scores = _load_pdc(member_hash)
    if pdc_scores:
        st.divider()
        st.markdown("**Medication Adherence (PDC)**")
        for s in pdc_scores:
            pdc = s["pdc"]
            threshold = 0.80
            status = "✅ Meets threshold" if pdc >= threshold else "❌ Below threshold"
            col_l, col_bar = st.columns([2, 3])
            col_l.markdown(f"**{s['drug_class']}** [{s['measure_id']}]  \n{status}")
            col_bar.progress(min(pdc, 1.0), text=f"PDC = {pdc:.3f} (need {threshold:.2f})")

    # Labs
    labs = _load_labs(member_hash)
    if labs:
        st.divider()
        st.markdown("**Recent Labs**")
        for lab in labs:
            val = f"{lab['result_value']} {lab.get('result_unit', '')}".strip() \
                if lab.get("result_value") else lab.get("result_text", "N/A")
            ref = f" (ref: {lab['reference_range']})" if lab.get("reference_range") else ""
            st.markdown(f"- `{lab['test_date']}` **{lab['test_name']}**: {val}{ref}")

    # Outreach history
    outreach = _load_outreach(member_hash)
    if outreach:
        st.divider()
        st.markdown("**Outreach History**")
        for o in outreach:
            icon = "✅" if o.get("outcome") == "reached" else \
                   "📵" if o.get("outcome") == "no_answer" else "📋"
            m_id = f" [{o['measure_id']}]" if o.get("measure_id") else ""
            st.markdown(
                f"- {icon} `{o['contact_date']}` {o.get('channel', '?')}{m_id} "
                f"→ {o.get('outcome', '?')}"
                + (f"  \n  *{o['notes']}*" if o.get("notes") else "")
            )

    st.divider()

    # Run agent on this member
    st.markdown("**Run HEDIS Gap Agent**")
    model = st.text_input("Model", value=os.getenv("PRAKTOR_MODEL", "llama3:8b"),
                          key="member_model")
    dry_run = st.checkbox("Dry run (no LLM)", value=True, key="member_dry_run")

    if st.button("Generate recommendation", type="primary"):
        _run_agent_for_member(member_hash, model, dry_run)


def _run_agent_for_member(member_hash: str, model: str, dry_run: bool):
    import dataclasses
    from core.agent import Agent
    from clinical.agents.hedis_gap_agent import HEDISGapDefinition, parse_next_best_action

    defn = dataclasses.replace(HEDISGapDefinition, llm_model=model)
    agent = Agent(defn)

    if dry_run:
        from scripts.demo_hedis_agent import _patch_dry_run, DEMO_MEMBERS, hash_member_id as hmi
        # Find matching demo member
        demo_data = next(
            (m for m in DEMO_MEMBERS if hmi(m["raw_id"]) == member_hash),
            DEMO_MEMBERS[0],
        )
        _patch_dry_run(agent, member_hash, demo_data)

    payload = {
        "agent_type": "hedis_gap",
        "member_id_hash": member_hash,
        "member_id_hash_short": member_hash[:12],
        "measurement_year": 2024,
        "history": "",
    }

    output_area = st.empty()
    status_area = st.empty()
    chunks: list[str] = []
    start = time.time()

    try:
        async def _stream():
            async for chunk in agent.run(payload, session_id=f"ui-{member_hash[:8]}"):
                chunks.append(chunk)
                output_area.markdown("".join(chunks))

        _run_async(_stream())
        elapsed = time.time() - start
        full_response = "".join(chunks)
        action = parse_next_best_action(full_response, member_hash)

        status_area.success(f"Done in {elapsed:.1f}s")

        # Save to tracker
        tracker = _get_tracker()
        rec_id = tracker.record_recommendation(action)
        st.info(f"Recommendation saved to queue (id={rec_id}). Switch to the Queue tab to review.")

        st.cache_data.clear()

    except Exception as e:
        status_area.error(f"Agent failed: {e}")
        st.exception(e)


# ---------------------------------------------------------------------------
# Tab 3: Analytics
# ---------------------------------------------------------------------------

def tab_analytics():
    st.subheader("Analytics")
    st.caption("Closure rates, STARS impact projection, and model performance.")

    stats = _get_tracker().get_stats(hours=24 * 90)

    m1, m2, m3 = st.columns(3)
    m1.metric("Total resolved", stats["total_resolved"])
    m2.metric("Closed", stats["closed"])
    m3.metric("Closure rate", f"{stats['closure_rate']:.0%}")

    if stats["by_action"]:
        st.divider()
        st.markdown("**Closure rate by action type**")
        for action_type, counts in stats["by_action"].items():
            closed = counts.get("closed", 0)
            not_closed = counts.get("not_closed", 0)
            total = closed + not_closed
            if total > 0:
                rate = closed / total
                st.markdown(
                    f"- **{action_type}**: {rate:.0%} closure rate "
                    f"({closed}/{total} resolved)"
                )

    st.divider()
    st.markdown("**STARS impact projection**")
    st.info(
        "For every 1-point improvement in a triple-weighted measure (MAC/MAD/MAP), "
        "a mid-size Medicare Advantage plan captures $50-200M in CMS Quality Bonus Payments. "
        "Close the medication adherence gaps first."
    )

    triple_pending = len([
        r for r in _load_pending_recs(1000)
        if r.get("measure_id") in ("MAC", "MAD", "MAP")
    ])
    if triple_pending > 0:
        st.metric("Triple-weighted gaps pending action", triple_pending,
                  help="MAC (statin), MAD (diabetes), MAP (RASA) — all 3x STARS")


# ---------------------------------------------------------------------------
# Tab 4: Span Tracer
# ---------------------------------------------------------------------------

def _monitoring_db_path() -> str:
    return os.getenv(
        "PRAKTOR_MONITORING_DB",
        str(Path.home() / ".praktor" / "monitoring.db"),
    )


def _tracer_query_runs(hours: float, agent_filter: str | None, limit: int) -> list[dict]:
    db = _monitoring_db_path()
    if not Path(db).exists():
        return []
    since = time.time() - hours * 3600
    clauses = ["timestamp >= ?"]
    params: list[Any] = [since]
    if agent_filter:
        clauses.append("agent_type = ?")
        params.append(agent_filter)
    where = " AND ".join(clauses)
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            f"SELECT * FROM agent_runs WHERE {where} ORDER BY timestamp DESC LIMIT ?",
            params + [limit],
        ).fetchall()
        return [dict(r) for r in rows]
    except Exception:
        return []
    finally:
        conn.close()


def _tracer_query_steps(run_id: int) -> list[dict]:
    db = _monitoring_db_path()
    if not Path(db).exists():
        return []
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT * FROM trajectory_steps WHERE run_id = ? ORDER BY step, id",
            (run_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    except Exception:
        return []
    finally:
        conn.close()


def _tracer_distinct_agents() -> list[str]:
    db = _monitoring_db_path()
    if not Path(db).exists():
        return []
    conn = sqlite3.connect(db)
    try:
        rows = conn.execute(
            "SELECT DISTINCT agent_type FROM agent_runs ORDER BY agent_type"
        ).fetchall()
        return [r[0] for r in rows]
    except Exception:
        return []
    finally:
        conn.close()


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
        return "#d9534f"   # red
    if step.get("cached"):
        return "#5cb85c"   # green
    if step.get("kind") == "tool_call":
        return "#5bc0de"   # cyan-blue
    return "#9b59b6"       # purple for LLM calls


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
            "Run `python scripts/demo_hedis_agent.py --dry-run` to generate data."
        )
        return

    st.markdown("---")
    st.markdown(
        f"**Trajectory — {len(steps)} span{'s' if len(steps) != 1 else ''}**  "
        f"&nbsp;&nbsp; 🧠 LLM call &nbsp; 🔧 tool call &nbsp; 💾 cached &nbsp; 🔴 error"
    )

    # Total wall-clock for proportional bars — use sum of latencies
    total_ms = sum(s.get("latency_ms", 0) for s in steps) or 1.0

    # Accumulate offset for Gantt-style positioning
    offset_ms = 0.0
    for step in steps:
        latency = step.get("latency_ms", 0) or 0
        icon = _step_kind_icon(step.get("kind", ""))
        color = _step_bar_color(step)

        # Label
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
            # Gantt: offset bar + span bar on same row using flex div
            offset_pct = offset_ms / total_ms * 100
            span_pct = max(latency / total_ms * 100, 1.0)   # at least 1% wide
            st.markdown(
                f'<div style="display:flex;align-items:center;height:20px;margin-top:2px">'
                f'<div style="width:{offset_pct:.1f}%;min-width:0"></div>'
                f'<div style="background:{color};height:16px;width:{span_pct:.1f}%;'
                f'border-radius:3px;min-width:4px"></div>'
                f'</div>',
                unsafe_allow_html=True,
            )

        offset_ms += latency

    # Timeline footer
    st.caption(
        f"Total wall time: {_fmt_ms(run['duration_ms'])} · "
        f"Trajectory span sum: {_fmt_ms(sum(s.get('latency_ms', 0) for s in steps))}"
    )


def tab_tracer():
    st.subheader("Span Tracer")
    st.caption(
        "OTel trajectory waterfall — every ReAct step (LLM call or tool call) "
        "recorded as a span in the monitoring store."
    )

    col_f1, col_f2, col_f3, col_refresh = st.columns([2, 2, 1, 1])
    with col_f1:
        hours = st.selectbox(
            "Time window", [1, 6, 24, 72, 168], index=2,
            format_func=lambda h: f"Last {h}h",
        )
    with col_f2:
        agents = _tracer_distinct_agents()
        options = ["All agents"] + agents
        # Default to hedis_gap if present
        default_idx = options.index("hedis_gap") if "hedis_gap" in options else 0
        selected = st.selectbox("Agent", options, index=default_idx)
        agent_filter = None if selected == "All agents" else selected
    with col_f3:
        limit = st.number_input("Max rows", min_value=10, max_value=500, value=50, step=10)
    with col_refresh:
        st.write("")  # vertical align
        if st.button("Refresh", key="tracer_refresh", use_container_width=True):
            st.cache_data.clear()

    runs = _tracer_query_runs(float(hours), agent_filter, int(limit))

    if not runs:
        st.info(
            "No runs in the monitoring store yet.\n\n"
            "Generate data with:\n"
            "```bash\n"
            "PYTHONPATH=praktor python scripts/demo_hedis_agent.py --dry-run\n"
            "```"
        )
        return

    # Summary metrics
    ok = sum(1 for r in runs if r["status"] == "ok")
    errors = len(runs) - ok
    avg_ms = sum(r["duration_ms"] for r in runs) / len(runs)
    p95_idx = max(0, int(len(runs) * 0.95) - 1)
    p95_ms = sorted(r["duration_ms"] for r in runs)[p95_idx]
    total_tokens = sum(r["total_tokens"] for r in runs)
    cache_hits = sum(1 for r in runs if r.get("cached"))

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Runs", len(runs))
    m2.metric("Success rate", f"{ok / len(runs):.0%}", delta=f"{errors} errors" if errors else None,
              delta_color="inverse")
    m3.metric("Avg latency", _fmt_ms(avg_ms))
    m4.metric("P95 latency", _fmt_ms(p95_ms))
    m5.metric("Total tokens", f"{total_tokens:,}")

    # Cache + token breakdown
    if cache_hits:
        st.caption(f"💾 Cache hits: {cache_hits}/{len(runs)} runs  ({cache_hits/len(runs):.0%})")

    st.divider()
    st.markdown(f"**{len(runs)} run{'s' if len(runs) != 1 else ''} — click to expand waterfall**")

    for i, run in enumerate(runs):
        ts = datetime.fromtimestamp(run["timestamp"]).strftime("%Y-%m-%d %H:%M:%S")
        badge = _span_status_badge(run["status"])
        cached_tag = " 💾" if run.get("cached") else ""
        session_short = run["session_id"][:12]

        # Step count from trajectory if available
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
# Diabetes HEDIS tab
# ---------------------------------------------------------------------------

_DIABETES_STORIES = {
    "D001": {
        "persona": "Maria Lopez",
        "story": "Untested GSD — no A1c in MY 2026 (auto-fail, triple-weighted, inverse). One standing lab order closes the highest-Stars gap. Spanish-speaking, high SDOH.",
        "demo_story": "untested_gsd_cheapest_close",
        "gaps": ["GSD"],
        "stars_exposure": 3.0,
        "highlight": "Cheapest gap to close — 3x Stars leverage for zero-cost lab order.",
    },
    "D002": {
        "persona": "James Chen",
        "story": "A1c 8.7% trending up over 18 months on metformin+glipizide (therapeutic inertia). eGFR 52 (CKD 3a), uACR missing → KED gap. SGLT2i eligible (CREDENCE/EMPA-KIDNEY).",
        "demo_story": "therapeutic_inertia_sglt2i",
        "gaps": ["GSD", "KED"],
        "stars_exposure": 4.0,
        "highlight": "Clinical depth: inertia detection + SGLT2i/CREDENCE recommendation.",
    },
    "D003": {
        "persona": "Patricia Williams",
        "story": "Four open gaps: GSD + KED + SPD-E + EED-E. No A1c, no kidney labs, no statin, eye exam expired. One comprehensive PCP visit closes all four.",
        "demo_story": "gap_stacking_four_measures",
        "gaps": ["GSD", "KED", "SPD-E", "EED-E"],
        "stars_exposure": 6.0,
        "highlight": "Gap-stacking: 6x Stars exposure closed in one touchpoint.",
    },
}


def tab_diabetes():
    st.subheader("🩺 Diabetes HEDIS — MY 2026 Demo")
    st.caption(
        "Diabetes-specialist agent with therapeutic inertia detection, "
        "treatment escalation, evidence anchors, and gap-stacking. "
        "Three engineered members illustrate the key clinical reasoning capabilities."
    )

    # Measure reference
    with st.expander("📋 MY 2026 Diabetes Measure Set", expanded=False):
        measures = [
            ("GSD", "Glycemic Status Assessment", "3x", "INVERSE — A1c >9.0% penalizes Stars 3x. Untested = auto-fail."),
            ("KED", "Kidney Health Evaluation", "1x", "eGFR AND uACR BOTH required. eGFR-only = FAIL."),
            ("EED-E", "Eye Exam (ECDS)", "1x", "Retinal/dilated exam by eye care professional."),
            ("SPD-E", "Statin Therapy (ECDS-only)", "1x", "PDC ≥ 0.80 for statins. All T2D age 40–75 w/o ASCVD."),
            ("BPD-E", "Blood Pressure Control (ECDS)", "1x", "Most recent BP <140/90. RPM now measure-compliant."),
        ]
        for mid, name, weight, note in measures:
            col_a, col_b, col_c = st.columns([1, 3, 5])
            col_a.markdown(f"**{mid}**")
            col_b.markdown(name)
            col_c.caption(f"{weight} STARS — {note}")

    st.divider()
    st.markdown("### Demo Members")

    for raw_id, info in _DIABETES_STORIES.items():
        with st.container(border=True):
            c1, c2 = st.columns([2, 3])
            with c1:
                st.markdown(f"**{raw_id} — {info['persona']}**")
                gaps_str = "  ".join(f"`{g}`" for g in info["gaps"])
                st.markdown(f"Gaps: {gaps_str}")
                stars_color = "green" if info["stars_exposure"] >= 5 else "orange" if info["stars_exposure"] >= 3 else "gray"
                st.markdown(
                    f"Stars exposure: :{stars_color}[**{info['stars_exposure']:.0f}x**]"
                )
            with c2:
                st.markdown(info["story"])
                st.caption(f"💡 {info['highlight']}")

    st.divider()

    # Run demo section
    st.markdown("### Run Agent")

    col_m, col_member, col_btn = st.columns([2, 2, 2])
    with col_m:
        model = st.text_input("LLM model", value="llama3:8b", key="dm_model")
    with col_member:
        member_opts = {"All members (D001, D002, D003)": None, "D001 — Maria Lopez": 0,
                       "D002 — James Chen": 1, "D003 — Patricia Williams": 2}
        selected_member = st.selectbox("Member", list(member_opts.keys()), key="dm_member")
    with col_btn:
        st.write("")
        dry_run = st.checkbox("Dry run (no LLM)", value=True, key="dm_dry_run")

    if st.button("▶ Run diabetes HEDIS agent", key="dm_run_btn", use_container_width=True):
        member_idx = member_opts[selected_member]

        with st.spinner("Running diabetes HEDIS agent…"):
            import subprocess
            cmd = [
                "python", "scripts/demo_diabetes_agent.py",
                "--model", model,
            ]
            if dry_run:
                cmd.append("--dry-run")
            if member_idx is not None:
                cmd += ["--member", str(member_idx)]

            env = dict(**os.environ, PYTHONPATH="praktor")
            result = subprocess.run(
                cmd,
                capture_output=True, text=True,
                env=env,
                cwd=str(_REPO_ROOT),
            )

        if result.returncode == 0:
            st.success("Agent run complete.")
            # Strip ANSI for display
            import re as _re
            ansi_escape = _re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
            clean = ansi_escape.sub("", result.stdout)
            st.code(clean, language="text")
        else:
            st.error("Agent run failed.")
            st.code(result.stderr or result.stdout, language="text")

    st.divider()
    st.markdown("### Escalation Ladder (ADA 2024)")
    steps = [
        ("Step 1", "Metformin monotherapy", "First-line for T2D. Reduces A1c ~1.5–2.0%."),
        ("Step 2", "Add GLP-1 RA", "BMI ≥27 or CV benefit needed (Ozempic, Trulicity). A1c reduction ~1.0–1.5%."),
        ("Step 3", "Add SGLT2i", "CKD (eGFR 20–60 + uACR >200) or HFrEF. CREDENCE, EMPA-KIDNEY, DAPA-CKD."),
        ("Step 4", "Basal insulin", "A1c >10% on dual therapy. Titrate to fasting glucose 80–130 mg/dL."),
        ("Step 5", "Basal-bolus insulin", "A1c >9% on optimized basal. Consider endocrinology referral."),
    ]
    for step, name, detail in steps:
        c1, c2, c3 = st.columns([1, 2, 4])
        c1.caption(step)
        c2.markdown(f"**{name}**")
        c3.caption(detail)


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

def _sidebar():
    with st.sidebar:
        st.markdown("### 🏥 praktor.ai Clinical")
        st.caption("HEDIS Gap Closure Agent")
        st.divider()

        try:
            pending = _load_pending_recs(1000)
            triple = sum(1 for r in pending if r.get("measure_id") in ("MAC", "MAD", "MAP"))
            st.metric("Pending reviews", len(pending))
            st.metric("Triple-weighted", triple)
        except Exception:
            st.caption("No queue data yet.")

        st.divider()
        st.markdown("**Quick start:**")
        st.code("python scripts/init_member_brain.py \\\n  --seed-demo", language="bash")
        st.code("python scripts/demo_hedis_agent.py \\\n  --dry-run", language="bash")
        st.divider()
        st.markdown("**Diabetes demo (MY 2026):**")
        st.code("python scripts/demo_diabetes_agent.py \\\n  --dry-run", language="bash")

        st.divider()
        st.caption("**STARS triple-weighted measures:**")
        st.caption("🟢 MAC — Statin adherence (3x)")
        st.caption("🟢 MAD — Diabetes meds (3x)")
        st.caption("🟢 MAP — RASA hypertension (3x)")


# ---------------------------------------------------------------------------
# Judge evaluation tab
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
    if score >= 7.5:
        return "green"
    if score >= 5.0:
        return "orange"
    return "red"


def _score_bar(score: float | None, max_width: int = 100) -> str:
    """HTML progress bar string for a score."""
    if score is None:
        return "—"
    pct = int((score / 10.0) * max_width)
    color = "#5cb85c" if score >= 7.5 else "#f0ad4e" if score >= 5.0 else "#d9534f"
    return f'<div style="background:{color};width:{pct}%;height:10px;border-radius:3px"></div>'


def _load_judge_evals(hours: float = 168, agent: str | None = None,
                      judge_type: str | None = None, limit: int = 200) -> list[dict]:
    """Read judge_evals from monitoring.db."""
    import sqlite3, time as _time
    db_path = os.getenv("PRAKTOR_MONITORING_DB",
                        str(Path.home() / ".praktor" / "monitoring.db"))
    if not Path(db_path).exists():
        return []
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        since = _time.time() - hours * 3600
        clauses = ["timestamp >= ?"]
        params: list = [since]
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


def _judge_distinct_agents() -> list[str]:
    db_path = os.getenv("PRAKTOR_MONITORING_DB",
                        str(Path.home() / ".praktor" / "monitoring.db"))
    if not Path(db_path).exists():
        return []
    try:
        import sqlite3
        conn = sqlite3.connect(db_path)
        rows = conn.execute(
            "SELECT DISTINCT agent_type FROM judge_evals ORDER BY agent_type"
        ).fetchall()
        conn.close()
        return [r[0] for r in rows]
    except Exception:
        return []


def _render_criteria_row(row: dict, criteria: list[str], label: str) -> None:
    """Render a single evaluation row with per-criterion score chips."""
    cols = st.columns([2] + [1] * len(criteria) + [2])
    cols[0].caption(label)
    for i, crit in enumerate(criteria):
        val = row.get(crit)
        color = _score_color(val)
        display = f":{color}[**{val:.1f}**]" if val is not None else ":gray[—]"
        cols[i + 1].markdown(display)
    cols[-1].caption(row.get("reasoning", "")[:80])


def tab_judge():
    st.subheader("⚖️ LLM Judge — Performance Evaluation")
    st.caption(
        "5 base performance dimensions scored for every agent. "
        "Clinical and diabetes agents add domain-specific criteria on top."
    )

    # Dimension reference
    with st.expander("📐 Evaluation Dimensions", expanded=False):
        st.markdown("**Base (all agents)**")
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

        st.markdown("**HEDIS clinical extensions** (`hedis_gap` agent)")
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

        st.markdown("**Diabetes extensions** (`diabetes_hedis` agent)")
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

    # Filters
    col_h, col_a, col_j, col_lim, col_ref = st.columns([1, 2, 2, 1, 1])
    with col_h:
        hours = st.selectbox("Window", [1, 6, 24, 168, 720], index=2,
                             format_func=lambda h: f"{h}h", key="judge_hours")
    with col_a:
        agents = _judge_distinct_agents()
        agent_opts = ["All agents"] + agents
        sel_agent = st.selectbox("Agent", agent_opts, key="judge_agent")
        agent_filter = None if sel_agent == "All agents" else sel_agent
    with col_j:
        jtype_opts = ["All types", "general", "hedis", "diabetes_hedis"]
        sel_jtype = st.selectbox("Judge type", jtype_opts, key="judge_type")
        jtype_filter = None if sel_jtype == "All types" else sel_jtype
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
            "No judge evaluations in the store yet.\n\n"
            "Run the demo, then use the on-demand panel below to score a response."
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
        if len(set(r["agent_type"] for r in evals)) > 1 or not agent_filter:
            st.markdown("### Per-agent average scores")
            agent_groups: dict[str, list[dict]] = {}
            for r in evals:
                agent_groups.setdefault(r["agent_type"], []).append(r)

            # Header row
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
            from datetime import datetime
            ts = datetime.fromtimestamp(row["timestamp"]).strftime("%m-%d %H:%M")
            jtype = row.get("judge_type", "general")
            overall = row.get("score", 0)
            color = _score_color(overall)
            label = (
                f":{color}[**{overall:.1f}**] "
                f"`{row['agent_type']}` · `{jtype}` · {ts}"
            )

            with st.expander(label, expanded=(i == 0)):
                # Base criteria
                st.markdown("**Base performance dimensions**")
                base_cols = st.columns(len(_BASE_CRITERIA))
                for col, crit in zip(base_cols, _BASE_CRITERIA):
                    val = row.get(crit)
                    c = _score_color(val)
                    col.metric(_CRITERION_LABELS[crit],
                               f"{val:.1f}" if val is not None else "—",
                               delta=None)

                # Domain extensions
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
    # On-demand evaluation panel
    # ---------------------------------------------------------------------------
    st.divider()
    st.markdown("### On-demand evaluation")
    st.caption("Paste any agent response to score it immediately with the LLM judge.")

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

                # Base criteria
                st.markdown("**Base performance dimensions**")
                b_cols = st.columns(5)
                for col, crit in zip(b_cols, _BASE_CRITERIA):
                    val = (result.criteria.get(crit)
                           if hasattr(result, "criteria")
                           else getattr(result, crit, None))
                    col.metric(_CRITERION_LABELS[crit],
                               f"{val:.1f}" if val is not None else "—")

                # Domain extensions
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
                st.error(f"Judge evaluation failed: {e}")
                st.caption("Ensure the LLM model is running (Ollama) or ANTHROPIC_API_KEY is set.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    _sidebar()

    st.title("🏥 praktor.ai Clinical")
    st.caption("HEDIS Gap Closure · Clinical Reasoning · Karpathy Second Brain")

    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(
        ["📋 Queue", "👤 Member", "📊 Analytics", "🔍 Traces", "🩺 Diabetes", "⚖️ Judge"]
    )

    with tab1:
        tab_queue()

    with tab2:
        tab_member()

    with tab3:
        tab_analytics()

    with tab4:
        tab_tracer()

    with tab5:
        tab_diabetes()

    with tab6:
        tab_judge()


if __name__ == "__main__":
    main()
