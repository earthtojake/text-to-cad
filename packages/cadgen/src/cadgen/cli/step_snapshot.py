"""``cadgen step snapshot`` — render a STEP/STP document or the model script behind one.

A GENERATED CLI over :func:`cadgen.step.snapshot`. There is no parser here on
purpose: everything the command accepts is derived from the verb function's
signature by :mod:`cadgen._internal.cli_from_function`, so a flag cannot drift
from a parameter (README law 6). Which input kinds the door accepts
is declared once, beside the verb, in
:data:`cadgen._internal.snapshot_door.DOOR_KINDS`.

Its verb is the FULL surface — section mode, display, kinematics, animation, focus/hide —
because STEP is the only input that has topology to act on.

Mesh inputs are NOT this door's: ``.stl``, ``.3mf`` and ``.glb`` go through
``cadgen stl|3mf|glb snapshot``, which is where their `build` doors already
live. Handing one here is refused by name with the door that takes it.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from cadgen._internal.cli_from_function import generated_main, generated_parser

DEFAULT_PROG = "cadgen step snapshot"
VERB = ("cadgen.step", "snapshot")


def build_parser(prog: str = DEFAULT_PROG) -> argparse.ArgumentParser:
    return generated_parser(VERB, prog=prog)


def main(argv: Sequence[str] | None = None, *, prog: str = DEFAULT_PROG) -> int:
    return generated_main(VERB, argv, prog=prog)


if __name__ == "__main__":
    raise SystemExit(main())
