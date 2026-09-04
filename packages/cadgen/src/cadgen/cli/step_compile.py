"""``cadgen step compile`` — a GENERATED CLI over :func:`cadgen.step.compile`.

There is no parser here on purpose. Everything the command accepts is derived
from the verb function's signature by
:mod:`cadgen._internal.cli_from_function`, so a flag cannot drift from a
parameter: this module only names which function the command is
(design/format-doors.md).

INTERNAL. Compiling a document into its tree is what every door and
the CAD Viewer do on demand, so nothing a user reads should ever tell them to
run this; it exists for tooling and CI. The user-facing pair is `python
<script>` for source and `cadgen step build IN OUT` for an existing document.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from cadgen._internal.cli_from_function import generated_main, generated_parser

DEFAULT_PROG = "cadgen step compile"
VERB = ("cadgen.step", "compile")


def build_parser(prog: str = DEFAULT_PROG) -> argparse.ArgumentParser:
    return generated_parser(VERB, prog=prog)


def main(argv: Sequence[str] | None = None, *, prog: str = DEFAULT_PROG) -> int:
    return generated_main(VERB, argv, prog=prog)


if __name__ == "__main__":
    raise SystemExit(main())
