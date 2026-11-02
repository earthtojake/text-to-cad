"""``cad cam plan`` — a GENERATED CLI over :func:`cad.cam.plan`, run in the CAD kernel's environment.

No parser here on purpose: everything the command accepts is derived from the
verb function's signature by :mod:`cad_server._internal.cli_from_function`, so a
flag cannot drift from a parameter. The verb reads the part with the CAD kernel,
which this process does not have: it runs where the kernel is
(:mod:`cad_server._internal.kernel_verb`).
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from cad_server._internal.cli_from_function import cli_from_function, run_cli
from cad_server._internal.kernel_verb import in_kernel

DEFAULT_PROG = "cad cam plan"
VERB = ("cad.cam", "plan")


def build_parser(prog: str = DEFAULT_PROG) -> argparse.ArgumentParser:
    return cli_from_function(in_kernel(VERB, prog=prog), prog=prog)


def main(argv: Sequence[str] | None = None, *, prog: str = DEFAULT_PROG) -> int:
    return run_cli(in_kernel(VERB, prog=prog), argv, prog=prog)


if __name__ == "__main__":
    raise SystemExit(main())
