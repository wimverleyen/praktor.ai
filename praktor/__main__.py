"""
CLI entry point for praktor.ai.

Usage:
  python -m praktor receive          # start the RabbitMQ consumer
  python -m praktor agent <method>   # fire a one-shot agent producer
                                     # method: process | thankyou | search | message | coverletter
"""

import argparse
import sys


def cmd_receive(args):
    import receive  # noqa: F401 — starts consuming on import


def cmd_agent(args):
    from agent import Agent

    method = args.method
    a = Agent()
    if hasattr(a, method):
        getattr(a, method)()
    else:
        print(f"Unknown agent method '{method}'. "
              f"Available: process, thankyou, search, message, coverletter",
              file=sys.stderr)
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        prog='praktor',
        description='praktor.ai — agent framework for job application workflows',
    )
    sub = parser.add_subparsers(dest='command', required=True)

    sub.add_parser('receive', help='Start the RabbitMQ consumer')

    agent_parser = sub.add_parser('agent', help='Fire a producer method')
    agent_parser.add_argument(
        'method',
        choices=['process', 'thankyou', 'search', 'message', 'coverletter'],
        help='Producer method to invoke',
    )

    args = parser.parse_args()

    if args.command == 'receive':
        cmd_receive(args)
    elif args.command == 'agent':
        cmd_agent(args)


if __name__ == '__main__':
    main()
