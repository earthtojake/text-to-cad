"""``cadgen mcp`` -- serve CAD to an agent host over MCP, on standard input and output.

An agent host that renders MCP Apps starts this process itself, one per thread;
it is not a command to run by hand. Standard output carries the protocol alone,
so diagnostics go to standard error.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence

DEFAULT_PROG = "cadgen mcp"


def build_parser(prog: str = DEFAULT_PROG) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=prog,
        description=(
            "Serve CAD's viewer to an agent host over MCP (stdio). The host starts one "
            "process per thread; there is nothing to configure."
        ),
    )
    return parser


def main(argv: Sequence[str] | None = None, *, prog: str = DEFAULT_PROG) -> int:
    build_parser(prog).parse_args(argv)
    from cadgen.mcp.server import serve

    return serve()


if __name__ == "__main__":
    raise SystemExit(main())
