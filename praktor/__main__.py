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

    args = parser.parse_args()

    dispatch = {
        "receive": cmd_receive,
        "publish": cmd_publish,
        "list": cmd_list,
        "agent": cmd_agent,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
