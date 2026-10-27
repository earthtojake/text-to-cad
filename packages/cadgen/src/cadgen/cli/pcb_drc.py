"""``cadgen pcb drc`` — run KiCad's design rule check on a saved board file.

A GENERATED CLI over :func:`cadgen.pcb.drc`: everything the command accepts
is derived from the verb function's signature by
:mod:`cadgen._internal.cli_from_function`, so a flag cannot drift from a
parameter. This command runs ``kicad-cli`` on the saved board and its companion project rules.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from cadgen._internal.cli_from_function import generated_main, generated_parser

DEFAULT_PROG = "cadgen pcb drc"
VERB = ("cadgen.pcb", "drc")


def build_parser(prog: str = DEFAULT_PROG) -> argparse.ArgumentParser:
    return generated_parser(VERB, prog=prog)


def main(argv: Sequence[str] | None = None, *, prog: str = DEFAULT_PROG) -> int:
    return generated_main(VERB, argv, prog=prog)


if __name__ == "__main__":
    raise SystemExit(main())
