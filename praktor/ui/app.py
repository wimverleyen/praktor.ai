"""
praktor.ai — Streamlit demo UI

Three tabs:
  1. Span Tracer  — waterfall view of agent runs + trajectory steps from SQLite
  2. Skills       — browse and run any registered AgentDefinition
  3. Documents    — upload PDFs → build/update FAISS vector store

Run:
    cd praktor.ai
    PYTHONPATH=praktor streamlit run praktor/ui/app.py
"""

from __future__ import annotations

import asyncio
import os
import sqlite3
import sys
import tempfile
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

    if st.button("Refresh", use_container_width=True):
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
        return

    st.markdown("**Trajectory**")

    total_ms = max(s["latency_ms"] for s in steps) if steps else 1
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


# ---------------------------------------------------------------------------
# Tab 2: Skills (run agents)
# ---------------------------------------------------------------------------

@st.cache_resource
def _get_all_definitions():
    """Load all registered AgentDefinitions from the global router."""
    import praktor.agents  # triggers registration
    from praktor.core.router import get_global_router
    router = get_global_router()
    # _agents maps name → Agent; expose the definition from each
    return {name: agent.definition for name, agent in router._agents.items()}


def _field_input(field_name: str, field_info, key_prefix: str) -> Any:
    """Render a Streamlit widget for one Pydantic field and return its value."""
    annotation = field_info.annotation
    default = field_info.default if field_info.default is not None else ""
    title = field_name.replace("_", " ").title()
    key = f"{key_prefix}_{field_name}"

    # Skip internal fields
    if field_name in ("agent_type", "session_id", "history"):
        return None

    # Choose widget by annotation
    if annotation in (str, str | None):
        if field_name in ("job_description", "prompt_template", "topic", "question", "message", "notes"):
            return st.text_area(title, value=str(default) if default else "", key=key, height=120)
        return st.text_input(title, value=str(default) if default else "", key=key)
    if annotation in (int, float):
        return st.number_input(title, value=default or 0, key=key)
    if annotation == bool:
        return st.checkbox(title, value=bool(default), key=key)
    # Fallback
    return st.text_input(title, value=str(default) if default else "", key=key)


def tab_skills():
    st.subheader("Skills")
    st.caption("Select an agent, fill in its inputs, and run it directly in the browser.")

    try:
        definitions = _get_all_definitions()
    except Exception as e:
        st.error(f"Failed to load agent definitions: {e}")
        return

    if not definitions:
        st.warning("No agents registered.")
        return

    selected = st.selectbox(
        "Agent",
        list(definitions.keys()),
        format_func=lambda n: n.replace("_", " ").title(),
    )

    defn = definitions[selected]

    with st.expander("Agent definition", expanded=False):
        st.markdown(f"**Model:** `{defn.llm_model}`")
        st.markdown(f"**Memory:** `{defn.memory_policy.name}`")
        st.markdown(f"**Max steps:** `{defn.max_steps}`")
        if defn.tools:
            st.markdown(f"**Tools:** {', '.join(f'`{t}`' for t in defn.tools)}")
        if defn.improvement_passes:
            st.markdown(f"**Improvement passes:** {len(defn.improvement_passes)}")
        st.caption("Prompt template:")
        st.code(defn.prompt_template[:500] + ("…" if len(defn.prompt_template) > 500 else ""), language="text")

    st.markdown("**Inputs**")
    schema = defn.input_schema
    payload: dict[str, Any] = {}

    with st.form(key=f"agent_form_{selected}"):
        for fname, finfo in schema.model_fields.items():
            val = _field_input(fname, finfo, key_prefix=selected)
            if val is not None:
                payload[fname] = val

        model_override = st.text_input(
            "Model override (optional)",
            value="",
            placeholder=defn.llm_model,
            key=f"{selected}_model_override",
        )
        submitted = st.form_submit_button("Run agent", use_container_width=True, type="primary")

    if submitted:
        payload["agent_type"] = selected
        payload.setdefault("session_id", "ui-" + str(int(time.time())))
        payload.setdefault("history", "")

        # Optionally override model
        if model_override.strip():
            import dataclasses
            defn = dataclasses.replace(defn, llm_model=model_override.strip())

        _run_agent(defn, payload)


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
# Tab 3: Documents (FAISS ingestion)
# ---------------------------------------------------------------------------

def tab_documents():
    st.subheader("Documents")
    st.caption("Upload PDF files to build or update the FAISS vector store used by the `job_interview` agent.")

    vector_db_path = st.text_input(
        "FAISS store path",
        value=os.getenv("VECTOR_DB", str(Path.home() / ".praktor" / "vector_db")),
        help="Directory where the FAISS index will be saved.",
    )

    model = st.text_input(
        "Embedding model (Ollama)",
        value=os.getenv("PRAKTOR_MODEL", "qwen2.5"),
        help="Ollama model used to generate embeddings.",
    )

    uploaded = st.file_uploader(
        "Upload PDF files",
        type=["pdf"],
        accept_multiple_files=True,
    )

    if uploaded:
        st.markdown(f"**{len(uploaded)} file(s) selected:**")
        for f in uploaded:
            st.markdown(f"- {f.name} ({f.size / 1024:.1f} KB)")

    if not uploaded:
        st.info("Upload one or more PDF files to begin ingestion.")
        return

    col_build, col_info = st.columns([1, 2])
    with col_build:
        build_btn = st.button("Build vector store", type="primary", use_container_width=True)

    with col_info:
        if Path(vector_db_path).exists():
            st.success(f"Existing store found at `{vector_db_path}` — will be overwritten.")
        else:
            st.info(f"New store will be created at `{vector_db_path}`.")

    if not build_btn:
        return

    progress = st.progress(0, text="Saving uploaded files…")
    log_area = st.empty()
    logs: list[str] = []

    def _log(msg: str):
        logs.append(msg)
        log_area.code("\n".join(logs[-30:]))

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            _log(f"Saving {len(uploaded)} file(s) to temp directory…")
            for i, f in enumerate(uploaded):
                dest = Path(tmpdir) / f.name
                dest.write_bytes(f.read())
                _log(f"  ✓ {f.name}")
                progress.progress((i + 1) / (len(uploaded) + 3), text=f"Saved {f.name}")

            progress.progress(0.5, text="Loading PDFs…")
            from langchain_community.document_loaders import PyPDFLoader
            from langchain.text_splitter import RecursiveCharacterTextSplitter
            from langchain_community.embeddings import OllamaEmbeddings
            from langchain_community.vectorstores import FAISS

            documents = []
            for pdf_path in Path(tmpdir).glob("*.pdf"):
                _log(f"Loading {pdf_path.name}…")
                loader = PyPDFLoader(str(pdf_path))
                pages = loader.load()
                documents.extend(pages)
                _log(f"  → {len(pages)} page(s)")

            _log(f"Total: {len(documents)} pages")
            progress.progress(0.6, text="Splitting into chunks…")

            splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=150)
            chunks = splitter.split_documents(documents)
            _log(f"Split into {len(chunks)} chunks")

            progress.progress(0.7, text=f"Embedding with '{model}'…")
            _log(f"Embedding with model '{model}' — this may take a while…")
            embeddings = OllamaEmbeddings(model=model)

            vector_store = FAISS.from_documents(chunks, embeddings)
            _log("Embedding complete.")

            progress.progress(0.9, text="Saving FAISS index…")
            Path(vector_db_path).mkdir(parents=True, exist_ok=True)
            vector_store.save_local(vector_db_path)
            _log(f"Vector store saved to: {vector_db_path}")

        progress.progress(1.0, text="Done!")
        st.success(
            f"Built FAISS store from {len(documents)} pages / {len(chunks)} chunks "
            f"→ `{vector_db_path}`"
        )
        st.balloons()

    except Exception as e:
        progress.empty()
        st.error(f"Ingestion failed: {e}")
        st.exception(e)


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
        if st.button("Refresh", use_container_width=True):
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
        submitted = st.form_submit_button("Generate Attestation", use_container_width=True)

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

    tab1, tab2, tab3, tab4 = st.tabs(["📡 Span Tracer", "🤖 Skills", "📄 Documents", "🛡️ AIGov"])

    with tab1:
        tab_tracer()

    with tab2:
        tab_skills()

    with tab3:
        tab_documents()

    with tab4:
        tab_aigov()


if __name__ == "__main__":
    main()
