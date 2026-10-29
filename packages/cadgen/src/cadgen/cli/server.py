"""``cadgen server``: the engine server, run in this process (``cadgen.engine.cli``).

The parser and the run are the engine's (``cadgen.engine.cli.parser_for``, ``run``), the same
verb ``python -m cadgen.engine server`` takes.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence

DEFAULT_PROG = "cadgen server"
ENGINE_VERB = "server"


def build_parser(prog: str = DEFAULT_PROG) -> argparse.ArgumentParser:
    from cadgen.engine.cli import parser_for

    return parser_for(ENGINE_VERB, prog)


def main(argv: Sequence[str] | None = None, *, prog: str = DEFAULT_PROG) -> int:
    from cadgen.engine.cli import VERBS, answered
    from cadgen._internal.installations import startup

    args = build_parser(prog).parse_args(argv)
    if args.port is None or 1 <= args.port <= 65535:
        startup()
    return answered(VERBS[ENGINE_VERB][2], args, prog)


if __name__ == "__main__":
    raise SystemExit(main())
