"""``cadgen stl build`` — a GENERATED CLI over :func:`cadgen.stl.build`.

There is no parser here on purpose: everything the command accepts is derived
from the verb function's signature by
:mod:`cadgen._internal.cli_from_function`, so a flag cannot drift from a
parameter (design/format-doors.md).

One of the three per-format doors that replace the retired
``cadgen step export``. A door takes a STEP DOCUMENT and writes ONLY its own
format: it tessellates the tree behind the document's bytes (compiled on demand
when the store has none), reads no model declaration, never runs a script and
writes no ``.step`` — ``python <model>.py`` and ``cadgen step build`` are how
documents get written.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from cadgen._internal.cli_from_function import generated_main, generated_parser

DEFAULT_PROG = "cadgen stl build"
VERB = ("cadgen.stl", "build")


def build_parser(prog: str = DEFAULT_PROG) -> argparse.ArgumentParser:
    return generated_parser(VERB, prog=prog)


def main(argv: Sequence[str] | None = None, *, prog: str = DEFAULT_PROG) -> int:
    return generated_main(VERB, argv, prog=prog)


if __name__ == "__main__":
    raise SystemExit(main())
