"""
praktor.ai — Clinical Reasoning UI (Streamlit)

HITL review queue for HEDIS gap closure recommendations.

Tabs:
  1. Queue      — care manager review queue ranked by priority
  2. Member     — full member context: gaps, SDOH, outreach, labs
  3. Analytics  — closure rates, STARS impact projection, model performance
  4. Traces     — OTel trajectory waterfall: every ReAct step as a span

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
        st.caption("**STARS triple-weighted measures:**")
        st.caption("🟢 MAC — Statin adherence (3x)")
        st.caption("🟢 MAD — Diabetes meds (3x)")
        st.caption("🟢 MAP — RASA hypertension (3x)")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    _sidebar()

    st.title("🏥 praktor.ai Clinical")
    st.caption("HEDIS Gap Closure · Clinical Reasoning · Karpathy Second Brain")

    tab1, tab2, tab3, tab4 = st.tabs(["📋 Queue", "👤 Member", "📊 Analytics", "🔍 Traces"])

    with tab1:
        tab_queue()

    with tab2:
        tab_member()

    with tab3:
        tab_analytics()

    with tab4:
        tab_tracer()


if __name__ == "__main__":
    main()
