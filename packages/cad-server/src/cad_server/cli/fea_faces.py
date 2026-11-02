"""``cad fea faces`` — a GENERATED CLI over :func:`cad.fea.faces`.

No parser here on purpose: everything the command accepts is derived from the
verb function's signature by :mod:`cad_server._internal.cli_from_function`, so a
flag cannot drift from a parameter. The verb runs where the CAD kernel is: here, or in
the installation's base (:mod:`cad_server._internal.kernel_call`).
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from cad_server._internal.cli_from_function import generated_parser, run_cli

DEFAULT_PROG = "cad fea faces"
VERB = ("cad.fea", "faces")


def build_parser(prog: str = DEFAULT_PROG) -> argparse.ArgumentParser:
    return generated_parser(VERB, prog=prog)


def main(argv: Sequence[str] | None = None, *, prog: str = DEFAULT_PROG) -> int:
    from cad_server._internal.kernel_call import in_kernel

    return run_cli(in_kernel(VERB, prog=prog), argv, prog=prog)


if __name__ == "__main__":
    raise SystemExit(main())
