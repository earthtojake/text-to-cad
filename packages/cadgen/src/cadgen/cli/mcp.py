"""``cadgen mcp`` -- serve CAD to an agent host over MCP, on standard input and output.

An agent host that renders MCP Apps starts this process itself, one per thread;
it is not a command to run by hand. Standard output carries the protocol alone,
so diagnostics go to standard error. The plugin that starts it names where it
came from, and whether something keeps it up to date (``--channel``,
``--auto-updated``: ``cadgen/_internal/channel.py``).
"""

from __future__ import annotations

import argparse
import os
from collections.abc import Sequence

DEFAULT_PROG = "cadgen mcp"


def _channel(value: str) -> str:
    from cadgen._internal.channel import is_channel

    if not is_channel(value):
        raise argparse.ArgumentTypeError(f"{value!r} is not a channel: a short lowercase token")
    return value


def build_parser(prog: str = DEFAULT_PROG) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=prog,
        description=(
            "Serve CAD's viewer to an agent host over MCP (stdio). The host starts one "
            "process per thread, from its plugin's startup command."
        ),
    )
    parser.add_argument(
        "--channel", type=_channel, metavar="ID",
        help="where this install came from, as its plugin names it: what analytics report",
    )
    parser.add_argument(
        "--auto-updated", action="store_true",
        help="something other than the person keeps this install up to date (its store, or the "
             "app that installed it), so never say when a new release is out",
    )
    return parser


def main(argv: Sequence[str] | None = None, *, prog: str = DEFAULT_PROG) -> int:
    args = build_parser(prog).parse_args(argv)
    if args.channel or args.auto_updated:
        from cadgen._internal.channel import AUTO_UPDATED_ENV, ENV

        # In the environment, where every process the server starts (the CAD Viewer, the build
        # daemon) reads them too: what the plugin's startup command says, and nothing inherited.
        if args.channel:
            os.environ[ENV] = args.channel
        os.environ[AUTO_UPDATED_ENV] = "1" if args.auto_updated else ""
    from cadgen.mcp.server import serve

    return serve()


if __name__ == "__main__":
    raise SystemExit(main())
