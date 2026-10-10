"""``cadgen pcb validate`` — a GENERATED CLI over :func:`cadgen.pcb.validate`.

There is no parser here on purpose; see :mod:`cadgen.cli.step_build`. The
findings document is `--json` (the ValidationResult dataclass): KiCad's own ERC
and DRC of one project, run on a staged copy so the project is never written.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from cadgen._internal.cli_from_function import generated_main, generated_parser

DEFAULT_PROG = "cadgen pcb validate"
VERB = ("cadgen.pcb", "validate")


def build_parser(prog: str = DEFAULT_PROG) -> argparse.ArgumentParser:
    return generated_parser(VERB, prog=prog)


def main(argv: Sequence[str] | None = None, *, prog: str = DEFAULT_PROG) -> int:
    return generated_main(VERB, argv, prog=prog)


if __name__ == "__main__":
    raise SystemExit(main())
