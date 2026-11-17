"""Read the game with --look, check connectivity with --status, or serve MCP."""

from __future__ import annotations

import argparse
import json
import sys

from .descriptions import CLI_DESCRIPTION, CLI_HELP
from .messages import error_text


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="message-from-aliens-mcp", description=CLI_DESCRIPTION
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--look", action="store_true", help=CLI_HELP["look"])
    mode.add_argument("--status", action="store_true", help=CLI_HELP["status"])
    parser.add_argument("--json", action="store_true", help=CLI_HELP["json"])
    parser.add_argument(
        "--format", choices=("markdown", "text", "json"), default="markdown"
    )
    parser.add_argument("--raw", action="store_true", help=CLI_HELP["raw"])
    args = parser.parse_args(argv)
    if not (args.look or args.status):
        if args.json or args.raw or args.format != "markdown":
            parser.error(error_text("CLI_LOOK_REQUIRED"))
        from .server import run

        run()
        return 0

    from . import tools
    from .errors import GameError
    from .rendering.table import render

    try:
        if args.status:
            print(json.dumps(tools.status()))
        else:
            snapshot = tools.look_json(raw=args.raw)
            style = "json" if args.json else args.format
            print(
                json.dumps(snapshot, ensure_ascii=False, indent=1)
                if style == "json"
                else render(snapshot, style=style)
            )
        return 0
    except GameError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    finally:
        tools.reset_session()


if __name__ == "__main__":
    sys.exit(main())
