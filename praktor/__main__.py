"""
CLI entry point for praktor.ai.

New async runtime:
  python -m praktor receive              # start async consumer (recommended)
  python -m praktor publish <agent_type> # fire a one-shot message (JSON from stdin)
  python -m praktor list                 # list registered agents and their fields

Legacy sync runtime (backwards compat):
  python -m praktor agent <method>       # process | thankyou | search | message | coverletter
"""

import argparse
import sys
import json


def cmd_receive(args):
    """Start the async RabbitMQ consumer."""
    import asyncio
    import os
    import praktor.agents  # noqa: F401 — triggers auto-registration of all agents
    from praktor.core.observability import init_tracer_provider
    from praktor.core.router import get_global_router
    from praktor.transport.consumer import run_consumer

    # Start Prometheus scrape endpoint in the same process so it shares
    # the in-memory registry that agents write to.
    prom_port = int(os.getenv("PRAKTOR_PROMETHEUS_PORT", "0"))
    if prom_port:
        from praktor.monitoring import configure
        configure(prometheus_port=prom_port)

    # Start background production eval scheduler (judges new runs every 15min)
    try:
        from praktor.clinical.evaluation.production_eval import ProductionEvalScheduler
        scheduler = ProductionEvalScheduler(interval_minutes=15, limit_per_run=10)
        scheduler.start()
    except Exception:
        pass

    init_tracer_provider()
    router = get_global_router()
    asyncio.run(run_consumer(router))


def cmd_publish(args):
    """
    Publish a message to the queue.

    Usage:
        echo '{"agent_type": "thank_you", "adjective": "professional", ...}' | python -m praktor publish
        python -m praktor publish --agent thank_you --data '{"adjective": "professional", ...}'
    """
    import asyncio
    import praktor.agents  # noqa: F401
    from praktor.transport.producer import publish

    if args.data:
        raw = args.data
    else:
        raw = sys.stdin.read().strip()

    if not raw:
        print("Error: provide JSON via --data or stdin", file=sys.stderr)
        sys.exit(1)

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"Error: invalid JSON: {e}", file=sys.stderr)
        sys.exit(1)

    if args.agent:
        data["agent_type"] = args.agent

    sid = asyncio.run(publish(data))
    print(f"Published session_id={sid}")


def cmd_list(args):
    """List all registered agents and their required input fields."""
    import praktor.agents  # noqa: F401
    from praktor.transport.schemas import list_schemas

    schemas = list_schemas()
    if not schemas:
        print("No agents registered.")
        return

    print(f"{'Agent':<25} {'Required fields'}")
    print("-" * 60)
    for name, fields in sorted(schemas.items()):
        visible = [f for f in fields if f not in ("agent_type", "session_id")]
        print(f"{name:<25} {', '.join(visible)}")


def cmd_agent(args):
    """Legacy: fire a synchronous producer method."""
    from agent import Agent

    method = args.method
    a = Agent()
    if hasattr(a, method):
        getattr(a, method)()
    else:
        print(
            f"Unknown agent method '{method}'. "
            f"Available: process, thankyou, search, message, coverletter",
            file=sys.stderr,
        )
        sys.exit(1)


def cmd_monitor(args):
    """
    Monitoring and observability commands.

    Usage:
        python -m praktor monitor summary [--agent X] [--hours 24]
        python -m praktor monitor serve [--port 8080]
        python -m praktor monitor export grafana [--datasource "Prometheus"]
        python -m praktor monitor kpi [--name my_kpi] [--hours 24]
    """
    import asyncio

    subcmd = args.monitor_cmd

    if subcmd == "summary":
        from praktor.monitoring.store import MonitoringStore
        from praktor.monitoring.cost import format_cost
        store = MonitoringStore()

        async def _run():
            summary = await store.aggregate(
                agent=getattr(args, "agent", None),
                hours=getattr(args, "hours", 24),
            )
            hours = getattr(args, "hours", 24)
            print(f"\npraktor.ai — Monitoring Summary (last {hours}h)")
            print("═" * 60)
            print(f"  Runs:     total={summary['total_runs']:,}  "
                  f"ok={summary['ok_runs']:,}  "
                  f"error={summary['error_runs']:,}  "
                  f"err_rate={summary['error_rate']:.1%}")
            print(f"  Tokens:   {summary['total_tokens']:,} total")
            print(f"  Cost:     {format_cost(summary['total_cost_usd'])}")
            print(f"  Latency:  avg={summary['avg_duration_ms']:.0f}ms  "
                  f"p95={summary['p95_duration_ms']:.0f}ms")
            print(f"  Cache:    hit_rate={summary['cache_hit_rate']:.1%}")
            if summary["avg_judge_score"] is not None:
                print(f"  Judge:    avg={summary['avg_judge_score']:.2f}/10  "
                      f"n={summary['judge_eval_count']}")

            if summary["by_agent"]:
                print("\n  By agent:")
                for name, s in sorted(summary["by_agent"].items()):
                    print(f"    {name:<25} runs={s['runs']:>5}  "
                          f"tokens={s['tokens']:>8,}  "
                          f"cost={format_cost(s['cost']):<16}  "
                          f"avg_latency={s['avg_latency']:.0f}ms")

            if summary["by_model"]:
                print("\n  By model:")
                for name, s in sorted(summary["by_model"].items()):
                    print(f"    {name:<30} runs={s['runs']:>5}  "
                          f"cost={format_cost(s['cost'])}")
            print()

        asyncio.run(_run())

    elif subcmd == "serve":
        port = getattr(args, "port", 8080)
        from praktor.monitoring import configure
        configure(prometheus_port=port)
        print(f"Prometheus metrics scrape endpoint: http://localhost:{port}/metrics")
        print("Press Ctrl+C to stop.")
        try:
            import time
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass

    elif subcmd == "export":
        fmt = getattr(args, "format", "grafana")
        if fmt == "grafana":
            datasource = getattr(args, "datasource", "${datasource}")
            from praktor.monitoring.exporters.grafana import print_dashboard
            print_dashboard(datasource=datasource)
        else:
            print(f"Unknown export format '{fmt}'. Available: grafana", file=sys.stderr)
            sys.exit(1)

    elif subcmd == "kpi":
        from praktor.monitoring.store import MonitoringStore
        store = MonitoringStore()

        async def _run():
            rows = await store.query_kpis(
                name=getattr(args, "name", None),
                hours=getattr(args, "hours", 24),
            )
            if not rows:
                print("No KPI events found.")
                return
            import datetime
            print(f"\n{'Timestamp':<22} {'Name':<30} {'Value':>10}  Tags")
            print("─" * 80)
            for r in rows:
                ts = datetime.datetime.fromtimestamp(r["timestamp"]).strftime("%Y-%m-%d %H:%M:%S")
                tags = str(r.get("tags", "") or "")
                print(f"  {ts}  {r['name']:<30} {r['value']:>10.4f}  {tags}")
            print()

        asyncio.run(_run())


def cmd_demo_governance(args):
    """Run the governance demo (no Ollama required by default)."""
    import sys as _sys
    import os
    _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if _root not in _sys.path:
        _sys.path.insert(0, _root)
    from scripts.demo_governance import main as _demo_main
    import sys as _sys2
    _sys2.argv = ["demo-governance"]
    if getattr(args, "model", ""):
        _sys2.argv += ["--model", args.model]
    _demo_main()


def cmd_prompt(args):
    """
    Manage prompt versions.

    Usage:
        python -m praktor prompt list <agent>
        python -m praktor prompt diff <agent> <v1> <v2>
        python -m praktor prompt activate <agent> <version_id>
        python -m praktor prompt eval <agent> <version_id> --question Q --response R
        python -m praktor prompt optimize <agent> --examples examples.json [--goal "..."] [--model llama3:8b]
    """
    import asyncio
    from praktor.core.prompt_registry import PromptRegistry

    registry = PromptRegistry()

    subcmd = args.prompt_cmd

    if subcmd == "list":
        versions = registry.list(args.agent)
        if not versions:
            print(f"No versions stored for agent '{args.agent}'.")
            return
        print(f"{'ID':10} {'Date':12} {'Score':>8}  {'Evals':>5}  {'Active':>6}  Notes")
        print("─" * 70)
        for v in versions:
            print(f"  {v.summary()}")

    elif subcmd == "diff":
        print(registry.diff(args.agent, args.v1, args.v2))

    elif subcmd == "activate":
        registry.set_active(args.agent, args.version_id)
        print(f"Activated {args.version_id} for agent '{args.agent}'.")

    elif subcmd == "eval":
        from praktor.core.judge import JudgeEvaluator
        model = getattr(args, "model", None) or "qwen2.5"
        judge = JudgeEvaluator(model=model)

        async def _run():
            score = await judge.evaluate(
                question=args.question,
                response=args.response,
                expected=getattr(args, "expected", "") or "",
            )
            registry.record_eval(args.agent, args.version_id, score.score, latency_ms=0.0)
            print(score.summary())

        asyncio.run(_run())

    elif subcmd == "optimize":
        from praktor.core.prompt_optimizer import PromptOptimizer

        if args.examples:
            try:
                with open(args.examples) as f:
                    examples = json.load(f)
            except Exception as e:
                print(f"Error reading examples file: {e}", file=sys.stderr)
                sys.exit(1)
        else:
            print("Error: --examples is required", file=sys.stderr)
            sys.exit(1)

        model = getattr(args, "model", None) or "qwen2.5"
        goal = getattr(args, "goal", None) or "Improve clarity, accuracy, and response quality."

        async def _run():
            opt = PromptOptimizer(agent_name=args.agent, model=model, registry=registry)
            result = await opt.optimize(examples, goal=goal)
            print(result.summary())
            if result.improved():
                print(f"\nNew version saved: {result.version.version_id}")
                print("Activate with:")
                print(f"  python -m praktor prompt activate {args.agent} {result.version.version_id}")

        asyncio.run(_run())


def cmd_eval(args):
    """
    Run offline or production evaluation.

    Usage:
        python -m praktor eval                      # offline: all 20 golden samples
        python -m praktor eval --agent hedis_gap    # offline: 10 HEDIS samples
        python -m praktor eval --production         # judge recent production runs
        python -m praktor eval --dry-run            # offline: judge reference outputs only (fast)
    """
    import asyncio

    if getattr(args, "production", False):
        from praktor.clinical.evaluation.production_eval import run_production_eval

        async def _run_prod():
            n = await run_production_eval(
                agent_type=getattr(args, "agent", None) or None,
                hours=getattr(args, "hours", 24),
                limit=getattr(args, "limit", 20),
                verbose=True,
            )
            print(f"\nProduction eval complete: {n} run(s) judged.")

        asyncio.run(_run_prod())
    else:
        from praktor.clinical.evaluation.offline_eval import run_offline_eval, print_per_sample_detail

        async def _run():
            reports = await run_offline_eval(
                agent_type=getattr(args, "agent", None) or None,
                concurrency=getattr(args, "concurrency", 2),
                verbose=True,
                dry_run=getattr(args, "dry_run", False),
            )
            if getattr(args, "detail", False):
                for report in reports:
                    print_per_sample_detail(report)

        asyncio.run(_run())


def cmd_demo(args):
    """
    Seed and run all 10 synthetic demo cases, then AI-judge each output.

    Usage:
        python -m praktor demo
        python -m praktor demo --seed-only
        python -m praktor demo --concurrency 3
    """
    import asyncio
    from praktor.clinical.evaluation.production_eval import run_demo
    from praktor.clinical.evaluation.demo_cases import seed_demo_members

    if getattr(args, "seed_only", False):
        seed_demo_members()
        print("Demo members seeded (10 cases). Run without --seed-only to execute agents.")
        return

    asyncio.run(run_demo(
        concurrency=getattr(args, "concurrency", 2),
        verbose=True,
        skip_production_eval=getattr(args, "skip_production_eval", False),
    ))


def cmd_judge_optimize(args):
    """
    Calibrate AI judges using the golden dataset.

    Usage:
        python -m praktor judge-optimize
        python -m praktor judge-optimize --agent hedis_gap
    """
    import asyncio
    from praktor.clinical.evaluation.judge_optimizer import calibrate_judges

    asyncio.run(calibrate_judges(
        agent_type=getattr(args, "agent", None) or None,
        model=getattr(args, "model", None) or None,
        verbose=True,
    ))


def cmd_aigov(args):
    """
    AIGov obligation commands.

    Usage:
        python -m praktor aigov scoreboard [--agent A] [--tenant T] [--format table|json]
        python -m praktor aigov attest     [--agent A] [--bundle B] [--validity-days 30]
        python -m praktor aigov build-check [--bundle minimal|standard|healthcare|external]
    """
    import asyncio
    import os
    from praktor.aigov.ledger.store import LedgerStore

    subcmd = args.aigov_cmd

    _STATUS_ICON = {"GREEN": "🟢", "AMBER": "🟡", "RED": "🔴", "GREY": "⬜"}

    if subcmd == "scoreboard":
        from praktor.aigov.ledger.scoreboard import scoreboard_current, status_summary

        db_path = os.getenv("AIGOV_LEDGER_PATH") or None
        store = LedgerStore(db_path=db_path)
        rows = scoreboard_current(
            store,
            agent_id=getattr(args, "agent", None) or None,
            tenant_id=getattr(args, "tenant", None) or None,
        )

        fmt = getattr(args, "format", "table")
        no_fail = getattr(args, "no_fail_on_empty", False)

        if not rows:
            if no_fail:
                print("Scoreboard: no events found (ledger empty).")
                return
            print("Scoreboard: no events found. Run obligation checks first.", file=sys.stderr)
            sys.exit(0)

        if fmt == "json":
            import dataclasses
            print(json.dumps([dataclasses.asdict(r) for r in rows], indent=2))
        else:
            overall = status_summary(rows)
            icon = _STATUS_ICON.get(overall, "?")
            print(f"\nAIGov Scoreboard — overall {icon} {overall}")
            print("─" * 80)
            print(f"  {'Agent':<22} {'Obligation':<8} {'Point':<10} {'Status':<8}  Last event")
            print("  " + "─" * 76)
            for r in rows:
                icon_s = _STATUS_ICON.get(r.status, "?")
                note = f"  ← {r.deferred_reason}" if r.deferred_reason else ""
                ts = r.last_event_ts[:19].replace("T", " ") if r.last_event_ts else ""
                print(
                    f"  {r.agent_id:<22} {r.obligation_id:<8} {r.enforcement_point:<10}"
                    f" {icon_s} {r.status:<6}  {ts}{note}"
                )
            print()

        if status_summary(rows) == "RED":
            sys.exit(1)

    elif subcmd == "attest":
        from praktor.aigov.ledger.scoreboard import scoreboard_current
        from praktor.aigov.attestation import create_attestation

        db_path = os.getenv("AIGOV_LEDGER_PATH") or None
        store = LedgerStore(db_path=db_path)
        agent_id = getattr(args, "agent", None) or "unknown"
        bundle_id = getattr(args, "bundle", None) or "custom"
        validity_days = getattr(args, "validity_days", 30)
        notes = getattr(args, "notes", "") or ""

        rows = scoreboard_current(store, agent_id=agent_id if agent_id != "unknown" else None)
        att = create_attestation(
            agent_id=agent_id,
            bundle_id=bundle_id,
            rows=rows,
            validity_days=validity_days,
            notes=notes,
        )

        print(f"\nAttestation {att.attestation_id}")
        print(f"  Agent:       {att.agent_id}")
        print(f"  Bundle:      {att.bundle_id}")
        print(f"  Created:     {att.created_at}")
        print(f"  Valid until: {att.valid_until}")
        print(f"  Obligations: {len(att.obligation_statuses)} rows")
        held = att.all_obligations_held()
        icon = "🟢" if held else "🔴"
        print(f"  Held:        {icon} {'YES' if held else 'NO'}")
        print(f"  Signature:   {att.signature_hex[:16]}… (sha256-content-hash)")
        if notes:
            print(f"  Notes:       {notes}")
        print()
        if not held:
            sys.exit(1)

    elif subcmd == "build-check":
        from praktor.aigov.bundle import (
            minimal_bundle, standard_bundle, healthcare_bundle, external_bundle,
        )
        from praktor.aigov.manifests import DataFlowManifest
        from datetime import datetime, timezone

        bundle_name = getattr(args, "bundle", "standard") or "standard"
        _bundle_map = {
            "minimal": minimal_bundle,
            "standard": standard_bundle,
            "healthcare": healthcare_bundle,
            "external": external_bundle,
        }
        factory = _bundle_map.get(bundle_name, standard_bundle)
        bundle = factory()

        # Default manifest for CI smoke check — not real data, just structural lint
        manifest_json = getattr(args, "manifest", None)
        if manifest_json:
            try:
                d = json.loads(manifest_json)
                from datetime import datetime, timezone
                if "signed_at" in d and isinstance(d["signed_at"], str):
                    d["signed_at"] = datetime.fromisoformat(d["signed_at"])
                manifest = DataFlowManifest(**d)
            except Exception as e:
                print(f"Error: invalid --manifest JSON: {e}", file=sys.stderr)
                sys.exit(1)
        else:
            manifest = DataFlowManifest(
                source_systems=["ci-default"],
                allowed_egress_destinations=["audit_log"],
                phi_fields=["sample_field"],
                signed_at=datetime.now(timezone.utc),
                deployer="ci-bot",
            )

        print(f"\nAIGov G-BUILD check — bundle '{bundle.bundle_id}'")
        print("─" * 60)

        any_fail = False

        async def _run_checks():
            nonlocal any_fail
            for ob in bundle:
                ev = await ob.check_build(manifest)
                icon = _STATUS_ICON.get(
                    {"PASS": "GREEN", "FAIL": "RED", "WAIVED": "GREEN", "NA": "AMBER"}.get(
                        ev.predicate_result.value, "GREY"
                    ), "?"
                )
                note = f"  ({ev.deferred_reason})" if ev.deferred_reason else ""
                print(f"  {icon} {ob.id:<6} {ob.name:<35} {ev.predicate_result.value}{note}")
                if ev.predicate_result.value == "FAIL":
                    any_fail = True

        asyncio.run(_run_checks())
        print()
        if any_fail:
            print("❌ Build check FAILED — one or more obligations did not pass.", file=sys.stderr)
            sys.exit(1)
        else:
            print("✅ Build check passed (FAIL=0; NA obligations are deferred, not failures).")


def main():
    parser = argparse.ArgumentParser(
        prog="praktor",
        description="praktor.ai — general agentic framework",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # --- receive ---
    sub.add_parser("receive", help="Start the async RabbitMQ consumer")

    # --- publish ---
    pub = sub.add_parser("publish", help="Publish a message to the queue")
    pub.add_argument("--agent", "-a", help="agent_type (overrides JSON field)")
    pub.add_argument("--data", "-d", help="JSON payload string")

    # --- list ---
    sub.add_parser("list", help="List registered agents and their input fields")

    # --- agent (legacy) ---
    ag = sub.add_parser("agent", help="Legacy: fire a producer method directly")
    ag.add_argument(
        "method",
        choices=["process", "thankyou", "search", "message", "coverletter"],
    )

    # --- monitor ---
    mon = sub.add_parser("monitor", help="Monitoring: summary, Prometheus server, export")
    mon_sub = mon.add_subparsers(dest="monitor_cmd", required=True)

    # monitor summary
    ms = mon_sub.add_parser("summary", help="Print monitoring summary")
    ms.add_argument("--agent", "-a", help="Filter by agent name")
    ms.add_argument("--hours", type=float, default=24, help="Time window in hours (default: 24)")

    # monitor serve
    msv = mon_sub.add_parser("serve", help="Start Prometheus metrics scrape server")
    msv.add_argument("--port", "-p", type=int, default=8080, help="HTTP port (default: 8080)")

    # monitor export
    mex = mon_sub.add_parser("export", help="Export dashboard configuration")
    mex.add_argument("format", choices=["grafana"], help="Export format")
    mex.add_argument("--datasource", default="${datasource}", help="Grafana data source name/variable")

    # monitor kpi
    mkpi = mon_sub.add_parser("kpi", help="List recorded business KPI events")
    mkpi.add_argument("--name", "-n", help="Filter by KPI name")
    mkpi.add_argument("--hours", type=float, default=24, help="Time window in hours (default: 24)")

    # --- demo-governance ---
    dg = sub.add_parser("demo-governance", help="Run governance demo (detector + optional agent)")
    dg.add_argument("--model", default="", help="LLM model (e.g. llama3:8b). Omit for detector-only mode.")

    # --- prompt ---
    pr = sub.add_parser("prompt", help="Manage prompt versions")
    pr_sub = pr.add_subparsers(dest="prompt_cmd", required=True)

    # prompt list
    pl = pr_sub.add_parser("list", help="List all versions for an agent")
    pl.add_argument("agent", help="Agent name")

    # prompt diff
    pd = pr_sub.add_parser("diff", help="Diff two prompt versions")
    pd.add_argument("agent", help="Agent name")
    pd.add_argument("v1", help="First version ID (prefix ok)")
    pd.add_argument("v2", help="Second version ID (prefix ok)")

    # prompt activate
    pa = pr_sub.add_parser("activate", help="Activate a prompt version")
    pa.add_argument("agent", help="Agent name")
    pa.add_argument("version_id", help="Version ID to activate (prefix ok)")

    # prompt eval
    pe = pr_sub.add_parser("eval", help="Score a response and record it")
    pe.add_argument("agent", help="Agent name")
    pe.add_argument("version_id", help="Version ID that produced the response")
    pe.add_argument("--question", "-q", required=True, help="Original question")
    pe.add_argument("--response", "-r", required=True, help="Agent response to score")
    pe.add_argument("--expected", "-e", default="", help="Reference answer (optional)")
    pe.add_argument("--model", "-m", default="qwen2.5", help="Judge model")

    # prompt optimize
    po = pr_sub.add_parser("optimize", help="Run automated prompt optimization")
    po.add_argument("agent", help="Agent name")
    po.add_argument("--examples", "-x", required=True, help="JSON file with [{input, output}] examples")
    po.add_argument("--goal", "-g", default="", help="Optimization goal description")
    po.add_argument("--model", "-m", default="qwen2.5", help="LLM model for optimization")

    # --- eval ---
    ev = sub.add_parser("eval", help="Run offline or production evaluation")
    ev.add_argument("--agent", "-a",
                    choices=["hedis_gap", "diabetes_hedis"],
                    default=None, help="Filter to one agent type (default: both)")
    ev.add_argument("--concurrency", "-c", type=int, default=2,
                    help="Max parallel agent runs for offline eval (default: 2)")
    ev.add_argument("--detail", action="store_true",
                    help="Print per-sample score table after summary")
    ev.add_argument("--dry-run", action="store_true", dest="dry_run",
                    help="Judge reference outputs only — skip agent LLM calls (fast CI mode)")
    ev.add_argument("--production", action="store_true",
                    help="Judge recent unjudged production runs instead of golden dataset")
    ev.add_argument("--hours", type=float, default=24,
                    help="For --production: look back this many hours (default: 24)")
    ev.add_argument("--limit", type=int, default=20,
                    help="For --production: max runs to judge (default: 20)")

    # --- demo ---
    dm = sub.add_parser("demo", help="Seed + run 10 synthetic demo cases and AI-judge outputs")
    dm.add_argument("--seed-only", action="store_true", dest="seed_only",
                    help="Only seed demo members, do not run agents")
    dm.add_argument("--concurrency", "-c", type=int, default=2,
                    help="Max parallel agent runs (default: 2)")
    dm.add_argument("--skip-production-eval", action="store_true", dest="skip_production_eval",
                    help="Skip final production eval pass after demo runs")

    # --- judge-optimize ---
    jo = sub.add_parser("judge-optimize", help="Calibrate AI judges using the golden dataset")
    jo.add_argument("--agent", "-a",
                    choices=["hedis_gap", "diabetes_hedis"],
                    default=None, help="Calibrate only this judge (default: both)")
    jo.add_argument("--model", "-m", default=None,
                    help="Override LLM model for judge (default: from settings)")

    # --- aigov ---
    aig = sub.add_parser("aigov", help="AIGov obligation checks, scoreboard, and attestation")
    aig_sub = aig.add_subparsers(dest="aigov_cmd", required=True)

    # aigov scoreboard
    asb = aig_sub.add_parser("scoreboard", help="Show current obligation status from the ledger")
    asb.add_argument("--agent", "-a", help="Filter by agent ID")
    asb.add_argument("--tenant", "-t", help="Filter by tenant ID")
    asb.add_argument("--format", "-f", choices=["table", "json"], default="table")
    asb.add_argument("--no-fail-on-empty", action="store_true", dest="no_fail_on_empty",
                     help="Exit 0 (not error) when the ledger has no events yet")

    # aigov attest
    aat = aig_sub.add_parser("attest", help="Create a signed attestation from the current scoreboard")
    aat.add_argument("--agent", "-a", default="unknown", help="Agent ID to attest")
    aat.add_argument("--bundle", "-b", default="custom", help="Bundle ID label")
    aat.add_argument("--validity-days", type=int, default=30, dest="validity_days",
                     help="Days until attestation expires (default: 30)")
    aat.add_argument("--notes", "-n", default="", help="Free-text notes")

    # aigov build-check
    abc = aig_sub.add_parser("build-check", help="Run G-BUILD obligation checks (CI gate)")
    abc.add_argument("--bundle", "-b", default="standard",
                     choices=["minimal", "standard", "healthcare", "external"],
                     help="Pre-built bundle to check (default: standard)")
    abc.add_argument("--manifest", "-m", default="",
                     help="DataFlowManifest as JSON string (omit for CI default)")

    args = parser.parse_args()

    dispatch = {
        "receive":  cmd_receive,
        "publish":  cmd_publish,
        "list":     cmd_list,
        "agent":    cmd_agent,
        "eval":             cmd_eval,
        "demo":             cmd_demo,
        "judge-optimize":   cmd_judge_optimize,
        "monitor":          cmd_monitor,
        "demo-governance":  cmd_demo_governance,
        "prompt":           cmd_prompt,
        "aigov":            cmd_aigov,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
