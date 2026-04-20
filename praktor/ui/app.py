"""
praktor.ai — Streamlit demo UI

Five tabs:
  1. Agents       — registry of all registered agents with judge scores, golden dataset coverage, and run form
  2. Span Tracer  — waterfall view of agent runs + trajectory steps from SQLite
  3. AIGov        — obligation status per agent × obligation × enforcement point
  4. Eval Monitor — offline + production eval scores and HITL review queue
  5. Clinical Data — browse members, HEDIS gaps, claims, labs, outreach from the clinical store

Run:
    cd praktor.ai
    PYTHONPATH=praktor streamlit run praktor/ui/app.py
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

# ── path fix so we can import from praktor/ without installation ──────────────
_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# ── page config (must be first Streamlit call) ────────────────────────────────
st.set_page_config(
    page_title="praktor.ai",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _db_path() -> str:
    return os.getenv(
        "PRAKTOR_MONITORING_DB",
        str(Path.home() / ".praktor" / "monitoring.db"),
    )


@st.cache_resource
def _get_store():
    """Return a MonitoringStore; cached across reruns."""
    from praktor.monitoring.store import MonitoringStore
    return MonitoringStore(db_path=_db_path())


def _run_async(coro):
    """Run an async coroutine from sync Streamlit context."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, coro)
                return future.result()
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


def _fmt_ms(ms: float) -> str:
    if ms >= 1000:
        return f"{ms/1000:.1f}s"
    return f"{ms:.0f}ms"


def _fmt_cost(usd: float) -> str:
    if usd == 0:
        return "$0.00"
    if usd < 0.001:
        return f"${usd*1000:.3f}m"
    return f"${usd:.4f}"


def _status_badge(status: str) -> str:
    if status == "ok":
        return "🟢"
    if status == "error":
        return "🔴"
    return "🟡"


def _kind_icon(kind: str) -> str:
    icons = {
        "llm_call": "🧠",
        "tool_call": "🔧",
        "improvement_pass": "✨",
    }
    return icons.get(kind, "▸")


# ---------------------------------------------------------------------------
# Tab 1: Span Tracer
# ---------------------------------------------------------------------------

def _query_runs(hours: float, agent_filter: str | None, limit: int) -> list[dict]:
    """Synchronous query against SQLite."""
    db = _db_path()
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
    finally:
        conn.close()


def _query_trajectory(run_id: int) -> list[dict]:
    db = _db_path()
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
    finally:
        conn.close()


def _query_judge_evals_for_session(session_id: str) -> list[dict]:
    db = _db_path()
    if not Path(db).exists():
        return []
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT * FROM judge_evals WHERE session_id = ? ORDER BY timestamp DESC LIMIT 5",
            (session_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def _distinct_agents() -> list[str]:
    db = _db_path()
    if not Path(db).exists():
        return []
    conn = sqlite3.connect(db)
    try:
        rows = conn.execute(
            "SELECT DISTINCT agent_type FROM agent_runs ORDER BY agent_type"
        ).fetchall()
        return [r[0] for r in rows]
    finally:
        conn.close()


def tab_tracer():
    st.subheader("Span Tracer")
    st.caption("Waterfall view of every agent run recorded in the monitoring store.")

    col_f1, col_f2, col_f3 = st.columns([2, 2, 1])
    with col_f1:
        hours = st.selectbox("Time window", [1, 6, 24, 72, 168], index=2, format_func=lambda h: f"Last {h}h")
    with col_f2:
        agents = _distinct_agents()
        agent_options = ["All agents"] + agents
        selected_agent = st.selectbox("Agent", agent_options)
        agent_filter = None if selected_agent == "All agents" else selected_agent
    with col_f3:
        limit = st.number_input("Max rows", min_value=10, max_value=500, value=100, step=10)

    if st.button("Refresh", width="stretch", key="refresh_span_tracer"):
        st.cache_data.clear()

    runs = _query_runs(float(hours), agent_filter, int(limit))

    if not runs:
        st.info("No runs found. Start the consumer (`python -m praktor receive`) and publish a task, or run a demo script.")
        return

    # ── summary metrics ──────────────────────────────────────────────────────
    ok = sum(1 for r in runs if r["status"] == "ok")
    total_tokens = sum(r["total_tokens"] for r in runs)
    total_cost = sum(r["cost_usd"] for r in runs)
    avg_ms = sum(r["duration_ms"] for r in runs) / len(runs) if runs else 0

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Runs", len(runs), help="Runs in selected window")
    m2.metric("Success rate", f"{ok/len(runs)*100:.0f}%" if runs else "—")
    m3.metric("Total tokens", f"{total_tokens:,}")
    m4.metric("Total cost", _fmt_cost(total_cost))

    st.divider()

    # ── run list ─────────────────────────────────────────────────────────────
    st.markdown("**Select a run to view its span waterfall**")

    for i, run in enumerate(runs):
        ts = datetime.fromtimestamp(run["timestamp"]).strftime("%H:%M:%S")
        badge = _status_badge(run["status"])
        cached_tag = " 💾" if run["cached"] else ""
        label = (
            f"{badge} **{run['agent_type']}** · {run['model']} · "
            f"{_fmt_ms(run['duration_ms'])} · {run['total_tokens']} tok{cached_tag} · {ts}"
        )
        with st.expander(label, expanded=(i == 0 and len(runs) <= 5)):
            _render_run_detail(run)


def _render_run_detail(run: dict):
    cols = st.columns(4)
    cols[0].markdown(f"**Session**  \n`{run['session_id'][:12]}…`")
    cols[1].markdown(f"**Status**  \n{_status_badge(run['status'])} {run['status']}")
    cols[2].markdown(f"**Cost**  \n{_fmt_cost(run['cost_usd'])}")
    cols[3].markdown(f"**Passes**  \n{run['passes']}")

    if run.get("error"):
        st.error(f"Error: {run['error']}")

    steps = _query_trajectory(run["id"])
    if not steps:
        st.caption("No trajectory steps recorded for this run.")
    else:
        st.markdown("**Trajectory**")
        max_latency = sum(s["latency_ms"] for s in steps) or 1

        for step in steps:
            icon = _kind_icon(step["kind"])
            label_parts = [f"{icon} step {step['step']} · **{step['kind']}**"]
            if step.get("tool_name"):
                label_parts.append(f"tool=`{step['tool_name']}`")
            label_parts.append(_fmt_ms(step["latency_ms"]))
            if step.get("output_tokens"):
                label_parts.append(f"{step['output_tokens']} tok out")
            if step.get("cached"):
                label_parts.append("💾 cached")
            if step.get("error"):
                label_parts.append("🔴 error")
            has_prompt = bool(step.get("prompt_text") or step.get("output_text"))
            if has_prompt:
                label_parts.append("📄 prompt")

            pct = min(step["latency_ms"] / max_latency, 1.0)

            col_label, col_bar = st.columns([3, 2])
            with col_label:
                st.markdown(" · ".join(label_parts))
            with col_bar:
                bar_color = "#d9534f" if step.get("error") else ("#5cb85c" if step.get("cached") else "#5bc0de")
                st.markdown(
                    f'<div style="background:{bar_color};height:16px;width:{pct*100:.0f}%;'
                    f'border-radius:3px;margin-top:4px"></div>',
                    unsafe_allow_html=True,
                )

            if step.get("prompt_text"):
                with st.expander(f"Agent prompt — step {step['step']}", expanded=False):
                    st.code(step["prompt_text"], language="text")
            if step.get("output_text"):
                with st.expander(f"Agent output — step {step['step']}", expanded=False):
                    st.markdown(step["output_text"])

    # ── Judge evaluation prompts ──────────────────────────────────────────
    judge_evals = _query_judge_evals_for_session(run["session_id"])
    if judge_evals:
        st.markdown("**Judge Evaluation**")
        for je in judge_evals:
            score_str = f"overall={je['score']:.2f}" if je.get("score") is not None else ""
            with st.expander(
                f"🧑‍⚖️ {je['judge_type']} judge · {score_str} · {je['agent_type']}",
                expanded=False,
            ):
                if je.get("judge_prompt_text"):
                    st.markdown("**Judge prompt (rendered)**")
                    st.code(je["judge_prompt_text"], language="text")
                if je.get("judge_response_text"):
                    st.markdown("**Judge raw response**")
                    st.code(je["judge_response_text"], language="json")
                if je.get("reasoning"):
                    st.markdown(f"**Reasoning:** {je['reasoning']}")


# ---------------------------------------------------------------------------
# Tab 1: Agents (registry + golden coverage + judge scores + run)
# ---------------------------------------------------------------------------

@st.cache_resource
def _get_all_definitions():
    """Load all registered AgentDefinitions from the global router."""
    import praktor.agents  # triggers registration
    from praktor.core.router import get_global_router
    router = get_global_router()
    # _agents maps name → Agent; expose the definition from each
    return {name: agent.definition for name, agent in router._agents.items()}


_AGENT_SPECIFIC_CRITERIA: dict[str, list[str]] = {
    "hedis_gap": [
        "gap_identification_accuracy", "action_appropriateness",
        "evidence_citation_quality", "safety_flag_coverage",
    ],
    "diabetes_hedis": [
        "inertia_detection_accuracy", "escalation_ladder_correctness",
        "gap_stacking_completeness", "evidence_anchor_quality",
        "safety_exclusion_coverage",
    ],
}

_STANDARD_CRITERIA = ["accuracy", "completeness", "relevance", "conciseness", "clarity"]

_CLINICAL_AGENT_TYPES = {"hedis_gap", "diabetes_hedis"}


@st.cache_data(ttl=60)
def _load_agent_judge_scores(agent_name: str, hours: float = 168) -> dict[str, float | None]:
    """Per-criterion average scores from judge_evals for a specific agent (last N hours)."""
    db = _db_path()
    if not Path(db).exists():
        return {}
    since = time.time() - hours * 3600
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    try:
        rows = [dict(r) for r in conn.execute(
            "SELECT * FROM judge_evals WHERE agent_type = ? AND timestamp >= ? ORDER BY timestamp DESC LIMIT 500",
            (agent_name, since),
        ).fetchall()]
    except Exception:
        rows = []
    finally:
        conn.close()

    if not rows:
        return {}

    result: dict[str, float | None] = {}
    overall = [r["score"] for r in rows if r.get("score") is not None]
    result["overall"] = sum(overall) / len(overall) if overall else None
    result["n"] = len(rows)

    all_criteria = _STANDARD_CRITERIA + _AGENT_SPECIFIC_CRITERIA.get(agent_name, [])
    for crit in all_criteria:
        vals = [r[crit] for r in rows if r.get(crit) is not None]
        result[crit] = sum(vals) / len(vals) if vals else None
    return result


@st.cache_data(ttl=60)
def _load_golden_counts() -> dict[str, int]:
    """Return {agent_type: scoring_sample_count} for clinical agents."""
    try:
        from praktor.clinical.evaluation.golden_dataset import load_golden_samples
    except Exception:
        return {}
    counts = {}
    for atype in _CLINICAL_AGENT_TYPES:
        try:
            samples = load_golden_samples(agent_type=atype)
            counts[atype] = sum(1 for s in samples if getattr(s, "measurement_year", 1) != 0)
        except Exception:
            counts[atype] = 0
    return counts


def _required_n_default() -> int:
    try:
        from praktor.clinical.evaluation.judge_optimizer import compute_required_n
        return compute_required_n()
    except Exception:
        return 56


def _score_color(v: float | None) -> str:
    if v is None:
        return "—"
    if v >= 8.0:
        return f"🟢 {v:.1f}"
    if v >= 6.0:
        return f"🟡 {v:.1f}"
    return f"🔴 {v:.1f}"


def _field_input(field_name: str, field_info, key_prefix: str) -> Any:
    """Render a Streamlit widget for one Pydantic field and return its value."""
    from pydantic_core import PydanticUndefined
    annotation = field_info.annotation
    raw_default = field_info.default
    if raw_default is PydanticUndefined or raw_default is None:
        if field_info.default_factory is not None:
            raw_default = field_info.default_factory()
        else:
            raw_default = ""
    default = raw_default
    title = field_name.replace("_", " ").title()
    key = f"{key_prefix}_{field_name}"
    help_text = field_info.description or None

    # Skip internal fields
    if field_name in ("agent_type", "session_id", "history"):
        return None

    # Choose widget by annotation
    if annotation in (str, str | None):
        if field_name in ("job_description", "prompt_template", "topic", "question", "message", "notes"):
            return st.text_area(title, value=str(default) if default else "", key=key, height=120, help=help_text)
        return st.text_input(title, value=str(default) if default else "", key=key, help=help_text)
    if annotation in (int, float):
        return st.number_input(title, value=default or 0, key=key, help=help_text)
    if annotation == bool:
        return st.checkbox(title, value=bool(default), key=key, help=help_text)
    # Fallback
    return st.text_input(title, value=str(default) if default else "", key=key, help=help_text)


def tab_agents():
    st.subheader("Agent Registry")
    st.caption(
        "All registered agents — configuration, golden dataset coverage, "
        "judge scores (last 7 days), and an inline run form."
    )

    try:
        definitions = _get_all_definitions()
    except Exception as e:
        st.error(f"Failed to load agent definitions: {e}")
        return

    if not definitions:
        st.warning("No agents registered.")
        return

    golden_counts = _load_golden_counts()
    req_n = _required_n_default()

    # ── summary metrics ───────────────────────────────────────────────────────
    n_clinical = sum(1 for n in definitions if n in _CLINICAL_AGENT_TYPES)
    adequate = sum(1 for t, cnt in golden_counts.items() if cnt >= req_n)
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Registered Agents", len(definitions))
    m2.metric("Clinical Agents", n_clinical)
    m3.metric("With Golden Data", len(golden_counts))
    m4.metric("Sample Adequate", f"{adequate}/{len(golden_counts)}" if golden_counts else "—")

    st.divider()

    if st.button("Refresh scores", key="refresh_agents"):
        st.cache_data.clear()
        st.rerun()

    # ── per-agent cards ───────────────────────────────────────────────────────
    for name in sorted(definitions.keys()):
        defn = definitions[name]
        scores = _load_agent_judge_scores(name)
        n_golden = golden_counts.get(name)
        is_clinical = name in _CLINICAL_AGENT_TYPES

        overall_badge = _score_color(scores.get("overall"))
        n_evals = scores.get("n", 0)
        sample_badge = "—"
        if is_clinical and n_golden is not None:
            sample_badge = (
                f"✅ {n_golden}/{req_n}" if n_golden >= req_n
                else f"⚠️ {n_golden}/{req_n}"
            )

        with st.expander(
            f"🤖 **{name.replace('_', ' ').title()}** "
            f"· `{defn.llm_model}` "
            f"· Judge: {overall_badge} ({n_evals} evals) "
            f"· Samples: {sample_badge}",
            expanded=False,
        ):
            col_meta, col_judges = st.columns([1, 2])

            # ── configuration ─────────────────────────────────────────────────
            with col_meta:
                st.markdown("**Configuration**")
                st.markdown(f"- Model: `{defn.llm_model}`")
                st.markdown(f"- Memory: `{defn.memory_policy.name}`")
                st.markdown(f"- Max steps: `{defn.max_steps}`")
                if defn.tools:
                    st.markdown(f"- Tools: {', '.join(f'`{t}`' for t in defn.tools)}")
                if defn.improvement_passes:
                    st.markdown(f"- Improvement passes: {len(defn.improvement_passes)}")

            # ── judge scores ──────────────────────────────────────────────────
            with col_judges:
                st.markdown(f"**Judge Scores** (last 7 days · {n_evals} evals)")
                if scores:
                    st.markdown("*Standard criteria:*")
                    std_cols = st.columns(5)
                    for col, crit in zip(std_cols, _STANDARD_CRITERIA):
                        v = scores.get(crit)
                        col.metric(crit.title(), f"{v:.1f}" if v is not None else "—")

                    spec = _AGENT_SPECIFIC_CRITERIA.get(name, [])
                    if spec:
                        st.markdown("*Agent-specific criteria:*")
                        spec_cols = st.columns(len(spec))
                        for i, crit in enumerate(spec):
                            v = scores.get(crit)
                            label = crit.replace("_", " ").replace("accuracy", "acc").title()
                            spec_cols[i].metric(label, f"{v:.1f}" if v is not None else "—")
                else:
                    st.info("No judge evals in the last 7 days. Run the agent or `python -m praktor eval`.")

            # ── golden dataset (clinical only) ────────────────────────────────
            if is_clinical:
                st.divider()
                st.markdown("**Golden Dataset**")
                g1, g2, g3 = st.columns(3)
                g1.metric("Samples", n_golden if n_golden is not None else 0)
                g2.metric("Required (80% power, δ=0.5)", req_n)
                if n_golden is not None and n_golden >= req_n:
                    g3.metric("Status", "Adequate ✅")
                else:
                    need = req_n - (n_golden or 0)
                    g3.metric("Status", f"Need {need} more ⚠️")

            # ── run form ──────────────────────────────────────────────────────
            st.divider()
            st.markdown("**Run this agent**")
            schema = defn.input_schema
            payload: dict[str, Any] = {}
            with st.form(key=f"agent_form_{name}"):
                for fname, finfo in schema.model_fields.items():
                    val = _field_input(fname, finfo, key_prefix=name)
                    if val is not None:
                        payload[fname] = val
                model_override = st.text_input(
                    "Model override (optional)", value="",
                    placeholder=defn.llm_model, key=f"{name}_model_override",
                )
                submitted = st.form_submit_button("Run agent", width="stretch", type="primary")

            if submitted:
                payload["agent_type"] = name
                payload.setdefault("session_id", "ui-" + str(int(time.time())))
                payload.setdefault("history", "")
                run_defn = defn
                if model_override.strip():
                    import dataclasses
                    run_defn = dataclasses.replace(defn, llm_model=model_override.strip())
                _run_agent(run_defn, payload)


def _run_agent(defn, payload: dict):
    from praktor.core.agent import Agent

    st.divider()
    st.markdown(f"**Running `{defn.name}`…**")

    output_area = st.empty()
    status_area = st.empty()

    collected: list[str] = []
    start = time.time()

    agent = Agent(defn)
    session_id = payload.get("session_id", "ui-session")

    try:
        async def _stream():
            async for chunk in agent.run(payload, session_id=session_id):
                collected.append(chunk)
                output_area.markdown("".join(collected))

        _run_async(_stream())
        elapsed = time.time() - start
        status_area.success(f"Done in {_fmt_ms(elapsed * 1000)} · {len(' '.join(collected).split())} words")
    except Exception as e:
        status_area.error(f"Agent failed: {e}")
        st.exception(e)


# ---------------------------------------------------------------------------
# Tab 3: Clinical Data Browser
# ---------------------------------------------------------------------------

@st.cache_data(ttl=30)
def _clinical_summary() -> dict:
    """Row counts per table in the clinical SQLite store."""
    import sqlite3
    db = os.getenv("PRAKTOR_CLINICAL_DB", str(Path.home() / ".praktor" / "clinical_data.db"))
    if not Path(db).exists():
        return {}
    try:
        con = sqlite3.connect(db)
        tables = ["members", "hedis_gaps", "claims", "labs", "vitals", "pdc_scores", "outreach_history"]
        return {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in tables}
    except Exception:
        return {}
    finally:
        con.close()


@st.cache_data(ttl=30)
def _clinical_members() -> list[dict]:
    import sqlite3
    db = os.getenv("PRAKTOR_CLINICAL_DB", str(Path.home() / ".praktor" / "clinical_data.db"))
    if not Path(db).exists():
        return []
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    rows = con.execute("SELECT * FROM members ORDER BY plan_id").fetchall()
    con.close()
    return [dict(r) for r in rows]


@st.cache_data(ttl=30)
def _clinical_member_detail(member_id_hash: str) -> dict:
    import sqlite3, json as _json
    db = os.getenv("PRAKTOR_CLINICAL_DB", str(Path.home() / ".praktor" / "clinical_data.db"))
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row

    gaps = [dict(r) for r in con.execute(
        "SELECT measure_id, measure_name, stars_weight, status, days_remaining, pdc_current "
        "FROM hedis_gaps WHERE member_id_hash = ? ORDER BY stars_weight DESC",
        (member_id_hash,),
    ).fetchall()]

    claims = [dict(r) for r in con.execute(
        "SELECT service_date, drug_name, drug_class, claim_type, days_supply "
        "FROM claims WHERE member_id_hash = ? ORDER BY service_date DESC LIMIT 10",
        (member_id_hash,),
    ).fetchall()]

    labs = [dict(r) for r in con.execute(
        "SELECT test_date, test_name, result_value, result_unit, result_text "
        "FROM labs WHERE member_id_hash = ? ORDER BY test_date DESC LIMIT 10",
        (member_id_hash,),
    ).fetchall()]

    outreach = [dict(r) for r in con.execute(
        "SELECT contact_date, channel, outcome, measure_id "
        "FROM outreach_history WHERE member_id_hash = ? ORDER BY contact_date DESC LIMIT 10",
        (member_id_hash,),
    ).fetchall()]

    con.close()
    return {"gaps": gaps, "claims": claims, "labs": labs, "outreach": outreach}


def tab_documents():
    st.subheader("Clinical Data")
    st.caption("Browse the agent data store — members, HEDIS gaps, claims, labs, and outreach history.")

    summary = _clinical_summary()

    # ── seed / refresh controls ───────────────────────────────────────────────
    col_seed, col_refresh, _ = st.columns([2, 1, 3])
    with col_seed:
        if st.button("Seed demo data", width="stretch",
                     help="Populate the clinical store with synthetic demo members"):
            with st.spinner("Seeding…"):
                import subprocess
                env = {**os.environ, "PYTHONPATH": "praktor"}
                repo_root = str(Path(__file__).parent.parent.parent)
                r1 = subprocess.run(
                    ["python", "scripts/init_member_brain.py", "--seed-demo"],
                    capture_output=True, text=True, env=env, cwd=repo_root,
                )
                r2 = subprocess.run(
                    ["python", "scripts/init_diabetes_demo.py"],
                    capture_output=True, text=True, env=env, cwd=repo_root,
                )
            if r1.returncode == 0 and r2.returncode == 0:
                st.success("Demo data seeded.")
                st.cache_data.clear()
                st.rerun()
            else:
                st.error("Seed failed.")
                for r in (r1, r2):
                    if r.returncode != 0:
                        st.code(r.stderr or r.stdout, language="text")
    with col_refresh:
        if st.button("Refresh", width="stretch"):
            st.cache_data.clear()
            st.rerun()

    if not summary:
        st.warning("Clinical store not found. Click **Seed demo data** to create it.")
        return

    # ── summary metrics ───────────────────────────────────────────────────────
    cols = st.columns(len(summary))
    labels = {
        "members": "Members", "hedis_gaps": "HEDIS Gaps", "claims": "Claims",
        "labs": "Labs", "vitals": "Vitals", "pdc_scores": "PDC Scores",
        "outreach_history": "Outreach",
    }
    for col, (table, count) in zip(cols, summary.items()):
        col.metric(labels.get(table, table), count)

    st.divider()

    # ── member browser ────────────────────────────────────────────────────────
    members = _clinical_members()
    if not members:
        st.info("No members in the store. Click **Seed demo data** above.")
        return

    st.markdown(f"**{len(members)} member(s)**")
    for m in members:
        h = m["member_id_hash"]
        short_hash = h[:12]
        sdoh_barriers = []
        try:
            import json as _json
            sdoh_barriers = _json.loads(m.get("sdoh_barriers") or "[]")
        except Exception:
            pass

        sdoh_str = ", ".join(sdoh_barriers) if sdoh_barriers else "none"
        label = (
            f"`{short_hash}…` · Plan `{m.get('plan_id', '—')}` · "
            f"Lang `{m.get('language','?').upper()}` · "
            f"SDOH risk `{m.get('sdoh_risk','?')}` · "
            f"PCP `{m.get('pcp_name','—')}`"
        )
        with st.expander(label):
            col_a, col_b = st.columns(2)
            with col_a:
                st.markdown(f"**Full hash:** `{h}`")
                st.markdown(f"**Plan:** `{m.get('plan_id','—')}` · **Year:** {m.get('measurement_year','—')}")
                st.markdown(f"**Language:** {m.get('language','?').upper()} · **Health literacy:** {m.get('health_literacy','?')}")
                st.markdown(f"**SDOH risk:** {m.get('sdoh_risk','?')} · **Barriers:** {sdoh_str}")
                st.markdown(f"**Pharmacy:** {m.get('pharmacy_name','—')} ({m.get('pharmacy_miles','?')} mi)")
            with col_b:
                st.markdown(f"**PCP:** {m.get('pcp_name','—')} (`{m.get('pcp_id','—')}`)")

            detail = _clinical_member_detail(h)

            if detail["gaps"]:
                st.markdown("**HEDIS Gaps**")
                for g in detail["gaps"]:
                    status_icon = "🟢" if g["status"] == "closed" else "🔴"
                    pdc = f" · PDC {g['pdc_current']:.0%}" if g.get("pdc_current") else ""
                    st.markdown(
                        f"{status_icon} `{g['measure_id']}` {g['measure_name']} "
                        f"· ★ {g['stars_weight']}x · {g['days_remaining']}d remaining{pdc}"
                    )

            if detail["claims"]:
                st.markdown("**Recent Claims**")
                import pandas as pd
                st.dataframe(pd.DataFrame(detail["claims"]), width="stretch", hide_index=True)

            if detail["labs"]:
                st.markdown("**Recent Labs**")
                import pandas as pd
                st.dataframe(pd.DataFrame(detail["labs"]), width="stretch", hide_index=True)

            if detail["outreach"]:
                st.markdown("**Outreach History**")
                import pandas as pd
                st.dataframe(pd.DataFrame(detail["outreach"]), width="stretch", hide_index=True)


# ---------------------------------------------------------------------------
# Tab 4: AIGov Scoreboard
# ---------------------------------------------------------------------------

_AIGOV_STATUS_ICON = {"GREEN": "🟢", "AMBER": "🟡", "RED": "🔴", "GREY": "⬜"}
_AIGOV_STATUS_COLOR = {
    "GREEN": "#d4edda",
    "AMBER": "#fff3cd",
    "RED": "#f8d7da",
    "GREY": "#e2e3e5",
}


@st.cache_resource
def _get_ledger_store():
    """Return a LedgerStore; cached across reruns."""
    import os
    from praktor.aigov.ledger.store import LedgerStore
    db_path = os.getenv("AIGOV_LEDGER_PATH") or None
    return LedgerStore(db_path=db_path)


def tab_aigov():
    st.subheader("AIGov Scoreboard")
    st.caption(
        "Live obligation status per agent × obligation × enforcement point. "
        "Reads from the append-only DuckDB ledger."
    )

    try:
        store = _get_ledger_store()
    except Exception as e:
        st.error(f"Could not open AIGov ledger: {e}")
        return

    from praktor.aigov.ledger.scoreboard import scoreboard_current, status_summary

    col_f1, col_f2, col_f3 = st.columns([2, 2, 1])
    with col_f1:
        agent_filter = st.text_input("Filter by agent ID", value="", placeholder="all agents")
    with col_f2:
        point_options = ["All points", "G-BUILD", "G-TEST", "G-RUN"]
        point_filter = st.selectbox("Enforcement point", point_options)
    with col_f3:
        if st.button("Refresh", width="stretch", key="refresh_aigov"):
            st.cache_resource.clear()
            st.rerun()

    rows = scoreboard_current(
        store,
        agent_id=agent_filter.strip() or None,
    )

    if point_filter != "All points":
        rows = [r for r in rows if r.enforcement_point == point_filter]

    if not rows:
        st.info(
            "No obligation events found. Run agents with an `obligation_bundle` set, "
            "or use `python -m praktor aigov build-check` to populate the ledger."
        )
        return

    # ── summary metrics ──────────────────────────────────────────────────────
    overall = status_summary(rows)
    green_n = sum(1 for r in rows if r.status == "GREEN")
    amber_n = sum(1 for r in rows if r.status == "AMBER")
    red_n   = sum(1 for r in rows if r.status == "RED")

    icon = _AIGOV_STATUS_ICON.get(overall, "?")
    color = _AIGOV_STATUS_COLOR.get(overall, "#e2e3e5")
    st.markdown(
        f'<div style="background:{color};padding:10px 16px;border-radius:6px;margin-bottom:12px">'
        f'<b>Overall: {icon} {overall}</b> &nbsp;·&nbsp; '
        f'🟢 {green_n} &nbsp; 🟡 {amber_n} &nbsp; 🔴 {red_n}'
        f'</div>',
        unsafe_allow_html=True,
    )

    st.divider()

    # ── scoreboard table ──────────────────────────────────────────────────────
    # Group by agent
    agents: dict[str, list] = {}
    for r in rows:
        agents.setdefault(r.agent_id, []).append(r)

    for agent_id, agent_rows in sorted(agents.items()):
        agent_status = status_summary(agent_rows)
        agent_icon = _AIGOV_STATUS_ICON.get(agent_status, "?")
        with st.expander(f"{agent_icon} **{agent_id}** — {agent_status}", expanded=(agent_status == "RED")):
            for r in sorted(agent_rows, key=lambda x: (x.obligation_id, x.enforcement_point)):
                row_icon = _AIGOV_STATUS_ICON.get(r.status, "?")
                ts = r.last_event_ts[:19].replace("T", " ") if r.last_event_ts else "—"
                note = f"  ← *{r.deferred_reason}*" if r.deferred_reason else ""
                st.markdown(
                    f"{row_icon} &nbsp; `{r.obligation_id}` &nbsp; "
                    f"**{r.enforcement_point}** &nbsp; {r.status} &nbsp; "
                    f"<small style='color:#888'>{ts}{note}</small>",
                    unsafe_allow_html=True,
                )

    st.divider()

    # ── attestation section ───────────────────────────────────────────────────
    st.markdown("**Create Attestation**")
    st.caption("Generates a signed point-in-time snapshot of the current scoreboard.")

    with st.form("attest_form"):
        col_a, col_b, col_c = st.columns([2, 2, 1])
        with col_a:
            att_agent = st.text_input("Agent ID", value=agent_filter.strip() or "all")
        with col_b:
            att_bundle = st.text_input("Bundle ID", value="custom-v1")
        with col_c:
            att_days = st.number_input("Validity (days)", min_value=1, max_value=365, value=30)
        att_notes = st.text_input("Notes (optional)", value="")
        submitted = st.form_submit_button("Generate Attestation", width="stretch")

    if submitted:
        from praktor.aigov.attestation import create_attestation
        att = create_attestation(
            agent_id=att_agent,
            bundle_id=att_bundle,
            rows=rows,
            validity_days=int(att_days),
            notes=att_notes,
        )
        held = att.all_obligations_held()
        held_icon = "🟢" if held else "🔴"
        st.success(
            f"**Attestation `{att.attestation_id[:12]}…`** · "
            f"{held_icon} Held={held} · "
            f"Valid until `{att.valid_until[:10]}`"
        )
        with st.expander("Full attestation record"):
            import dataclasses, json as _json
            st.json(_json.dumps(dataclasses.asdict(att), indent=2))


# ---------------------------------------------------------------------------
# Tab 5: Eval Monitor (offline + production + HITL)
# ---------------------------------------------------------------------------

@st.cache_data(ttl=30)
def _query_judge_evals(hours: float = 168, agent: str | None = None) -> list[dict]:
    db = _db_path()
    if not Path(db).exists():
        return []
    since = time.time() - hours * 3600
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    try:
        q = "SELECT * FROM judge_evals WHERE timestamp >= ?"
        params: list = [since]
        if agent:
            q += " AND agent_type = ?"
            params.append(agent)
        q += " ORDER BY timestamp DESC LIMIT 200"
        return [dict(r) for r in conn.execute(q, params).fetchall()]
    except Exception:
        return []
    finally:
        conn.close()


@st.cache_data(ttl=30)
def _query_hitl_queue(limit: int = 50) -> list[dict]:
    db = _db_path()
    if not Path(db).exists():
        return []
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM hitl_reviews ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()]
    except Exception:
        return []
    finally:
        conn.close()


def _update_hitl_review(session_id: str, action: str, notes: str, modified_output: str) -> bool:
    db = _db_path()
    if not Path(db).exists():
        return False
    conn = sqlite3.connect(db)
    try:
        conn.execute(
            "UPDATE hitl_reviews SET action=?, reviewer_notes=?, modified_output=?, reviewed_at=? "
            "WHERE session_id=?",
            (action, notes, modified_output or None, time.time(), session_id),
        )
        conn.commit()
        return True
    except Exception:
        return False
    finally:
        conn.close()


def tab_eval_monitor():
    st.subheader("Eval Monitor")
    st.caption(
        "Unified view of offline evaluation results, production AI-judge scores, "
        "and the HITL (Human-in-the-Loop) review queue."
    )

    subtab_offline, subtab_prod, subtab_hitl = st.tabs(
        ["📐 Offline Eval", "🏭 Production Eval", "👤 HITL Review"]
    )

    # ── Offline Eval ─────────────────────────────────────────────────────────
    with subtab_offline:
        st.markdown("**Offline evaluation results from the 20-sample golden dataset.**")

        col1, col2 = st.columns([2, 1])
        with col1:
            hours_off = st.selectbox("Time window", [24, 72, 168, 720], index=2,
                                     format_func=lambda h: f"Last {h}h", key="off_hours")
        with col2:
            if st.button("Run Offline Eval", key="run_offline_eval",
                         help="python -m praktor eval"):
                st.info("Run in terminal: `python -m praktor eval --detail`")

        evals = _query_judge_evals(hours=float(hours_off))
        offline = [e for e in evals if e.get("question", "").startswith("golden:")]

        if not offline:
            st.info(
                "No offline eval results found. Run: `python -m praktor eval`\n\n"
                "Or in dry-run mode: `python -m praktor eval --dry-run`"
            )
        else:
            # Summary metrics
            scores = [e["score"] for e in offline if e.get("score") is not None]
            acc = [e["accuracy"] for e in offline if e.get("accuracy") is not None]
            comp = [e["completeness"] for e in offline if e.get("completeness") is not None]
            rel = [e["relevance"] for e in offline if e.get("relevance") is not None]
            clar = [e["clarity"] for e in offline if e.get("clarity") is not None]

            m1, m2, m3, m4, m5 = st.columns(5)
            m1.metric("Samples", len(offline))
            m2.metric("Overall", f"{sum(scores)/len(scores):.2f}/10" if scores else "—")
            m3.metric("Accuracy", f"{sum(acc)/len(acc):.1f}" if acc else "—")
            m4.metric("Completeness", f"{sum(comp)/len(comp):.1f}" if comp else "—")
            m5.metric("Clarity", f"{sum(clar)/len(clar):.1f}" if clar else "—")

            st.divider()
            import pandas as pd
            df = pd.DataFrame(offline)[
                ["session_id", "agent_type", "score", "accuracy", "completeness",
                 "relevance", "clarity", "reasoning", "timestamp"]
            ].copy()
            df["timestamp"] = df["timestamp"].apply(
                lambda t: datetime.fromtimestamp(t).strftime("%m-%d %H:%M") if t else ""
            )
            df["session_id"] = df["session_id"].str[:14]
            st.dataframe(df, width="stretch", hide_index=True)

    # ── Production Eval ────────────────────────────────────────────────────────
    with subtab_prod:
        st.markdown("**AI-judge scores on production and demo runs.**")

        col1, col2 = st.columns([2, 1])
        with col1:
            hours_prod = st.selectbox("Time window", [24, 72, 168], index=0,
                                      format_func=lambda h: f"Last {h}h", key="prod_hours")
        with col2:
            if st.button("Run Demo", key="run_demo_btn",
                         help="Seeds + runs all 10 demo cases"):
                st.info("Run in terminal: `python -m praktor demo`")

        evals = _query_judge_evals(hours=float(hours_prod))
        prod = [e for e in evals if not e.get("question", "").startswith("golden:")]

        if not prod:
            st.info(
                "No production eval results. Run: `python -m praktor demo`\n\n"
                "Or: `python -m praktor eval --production`"
            )
        else:
            scores = [e["score"] for e in prod if e.get("score") is not None]
            by_agent: dict[str, list] = {}
            for e in prod:
                by_agent.setdefault(e["agent_type"], []).append(e.get("score", 0))

            m1, m2 = st.columns(2)
            m1.metric("Judged runs", len(prod))
            m2.metric("Overall avg", f"{sum(scores)/len(scores):.2f}/10" if scores else "—")

            for agent, agent_scores in sorted(by_agent.items()):
                avg = sum(agent_scores) / len(agent_scores)
                st.metric(agent.replace("_", " ").title(), f"{avg:.2f}/10",
                          help=f"{len(agent_scores)} runs")

            st.divider()
            import pandas as pd
            df = pd.DataFrame(prod)[
                ["session_id", "agent_type", "score", "accuracy", "completeness",
                 "relevance", "reasoning", "timestamp"]
            ].copy()
            df["timestamp"] = df["timestamp"].apply(
                lambda t: datetime.fromtimestamp(t).strftime("%m-%d %H:%M") if t else ""
            )
            df["session_id"] = df["session_id"].str[:16]
            st.dataframe(df, width="stretch", hide_index=True)

    # ── HITL Review Queue ──────────────────────────────────────────────────────
    with subtab_hitl:
        st.markdown("**Human-in-the-Loop review queue — approve, reject, or modify agent outputs.**")

        if st.button("Refresh queue", key="refresh_hitl"):
            st.cache_data.clear()
            st.rerun()

        reviews = _query_hitl_queue(limit=50)
        if not reviews:
            st.info(
                "No reviews in queue. Run demo cases to populate: `python -m praktor demo`"
            )
        else:
            pending = [r for r in reviews if r.get("action") == "pending"]
            done = [r for r in reviews if r.get("action") != "pending"]

            m1, m2, m3 = st.columns(3)
            m1.metric("Pending", len(pending))
            approved = sum(1 for r in done if r.get("action") == "approved")
            m2.metric("Approved", approved)
            rejected = sum(1 for r in done if r.get("action") == "rejected")
            m3.metric("Rejected", rejected)

            if pending:
                st.divider()
                st.markdown("**Pending reviews:**")
                for r in pending:
                    sid = r["session_id"]
                    agent = r.get("agent_type", "unknown")
                    score = r.get("judge_score_pre")
                    score_str = f" · Judge score: {score:.1f}/10" if score else ""
                    created = r.get("created_at", "")
                    if created:
                        try:
                            created = datetime.fromtimestamp(float(created)).strftime("%m-%d %H:%M")
                        except Exception:
                            pass

                    with st.expander(
                        f"🟡 `{sid[:16]}` · {agent}{score_str} · {created}",
                        expanded=False,
                    ):
                        output = r.get("original_output", "")
                        st.markdown("**Agent output:**")
                        st.text_area("Output", value=output, height=200, disabled=True,
                                     key=f"hitl_out_{sid}")

                        with st.form(key=f"hitl_form_{sid}"):
                            action = st.radio(
                                "Decision",
                                ["approved", "rejected", "modified"],
                                horizontal=True,
                                key=f"hitl_action_{sid}",
                            )
                            modified = st.text_area(
                                "Modified output (only if action=modified)",
                                value="", height=100,
                                key=f"hitl_modified_{sid}",
                            )
                            notes = st.text_input(
                                "Reviewer notes", value="",
                                key=f"hitl_notes_{sid}",
                            )
                            if st.form_submit_button("Submit review", type="primary"):
                                ok = _update_hitl_review(sid, action, notes, modified)
                                if ok:
                                    st.success(f"Review submitted: {action}")
                                    st.cache_data.clear()
                                    st.rerun()
                                else:
                                    st.error("Failed to save review.")

            if done:
                st.divider()
                st.markdown("**Completed reviews:**")
                import pandas as pd
                df = pd.DataFrame(done)[
                    ["session_id", "agent_type", "action", "judge_score_pre",
                     "reviewer_notes", "reviewed_at"]
                ].copy()
                df["session_id"] = df["session_id"].str[:16]
                df["reviewed_at"] = df["reviewed_at"].apply(
                    lambda t: datetime.fromtimestamp(float(t)).strftime("%m-%d %H:%M")
                    if t else ""
                )
                st.dataframe(df, width="stretch", hide_index=True)


# ---------------------------------------------------------------------------
# Sidebar — live summary
# ---------------------------------------------------------------------------

def _sidebar():
    with st.sidebar:
        st.markdown("### praktor.ai")
        st.caption("Agentic framework · local + hosted LLMs")
        st.divider()

        try:
            runs_1h = _query_runs(1.0, None, 1000)
            st.metric("Runs (last 1h)", len(runs_1h))
            if runs_1h:
                ok = sum(1 for r in runs_1h if r["status"] == "ok")
                st.metric("Success rate", f"{ok/len(runs_1h)*100:.0f}%")
                total_cost = sum(r["cost_usd"] for r in runs_1h)
                st.metric("Cost (1h)", _fmt_cost(total_cost))
        except Exception:
            st.caption("No monitoring data yet.")

        st.divider()
        db = _db_path()
        if Path(db).exists():
            size_kb = Path(db).stat().st_size / 1024
            st.caption(f"DB: `{Path(db).name}` ({size_kb:.0f} KB)")
        else:
            st.caption("DB: not yet created")

        st.divider()
        st.caption("**Quick start:**")
        st.code("python -m praktor receive", language="bash")
        st.code("python -m praktor publish \\\n  --agent cover_letter \\\n  --data '{...}'", language="bash")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    _sidebar()

    st.title("⚡ praktor.ai")
    st.caption("General-purpose agentic framework · ReAct · OTel · Prometheus · Grafana")

    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "🤖 Agents", "📡 Span Tracer", "🛡️ AIGov", "📊 Eval Monitor", "🏥 Clinical Data",
    ])

    with tab1:
        tab_agents()

    with tab2:
        tab_tracer()

    with tab3:
        tab_aigov()

    with tab4:
        tab_eval_monitor()

    with tab5:
        tab_documents()


if __name__ == "__main__":
    main()
