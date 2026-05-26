from __future__ import annotations

import argparse
import asyncio
import logging

logger = logging.getLogger(__name__)


def cmd_serve(_args: argparse.Namespace) -> None:
    import uvicorn

    from src.gateway.api_server import create_app

    app = create_app()
    uvicorn.run(app, host="0.0.0.0", port=8000)


def cmd_repl(_args: argparse.Namespace) -> None:
    from src.gateway.cli_repl import run_repl

    asyncio.run(run_repl())


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="shuyuancore",
        description="ShuyuanCore - 智能进化、风格一致、深度记忆、自主行动的开源AI Agent",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    serve_parser = subparsers.add_parser("serve", help="Start the API server")
    serve_parser.set_defaults(func=cmd_serve)

    repl_parser = subparsers.add_parser("repl", help="Start the interactive REPL")
    repl_parser.set_defaults(func=cmd_repl)

    args = parser.parse_args()

    if hasattr(args, "func"):
        args.func(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()