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
    import agents  # noqa: F401 — triggers auto-registration of all agents
    from core.router import get_global_router
    from transport.consumer import run_consumer

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
    import agents  # noqa: F401
    from transport.producer import publish

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
    import agents  # noqa: F401
    from transport.schemas import list_schemas

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
        from monitoring.store import MonitoringStore
        from monitoring.cost import format_cost
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
        from monitoring import configure
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
            from monitoring.exporters.grafana import print_dashboard
            print_dashboard(datasource=datasource)
        else:
            print(f"Unknown export format '{fmt}'. Available: grafana", file=sys.stderr)
            sys.exit(1)

    elif subcmd == "kpi":
        from monitoring.store import MonitoringStore
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
    from core.prompt_registry import PromptRegistry

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
        from core.judge import JudgeEvaluator
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
        from core.prompt_optimizer import PromptOptimizer

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

    args = parser.parse_args()

    dispatch = {
        "receive":  cmd_receive,
        "publish":  cmd_publish,
        "list":     cmd_list,
        "agent":    cmd_agent,
        "monitor":  cmd_monitor,
        "prompt":   cmd_prompt,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
