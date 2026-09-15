"""``cadgen 3mf snapshot`` — render a 3MF mesh.

A GENERATED CLI over :func:`cadgen.threemf.snapshot`. There is no parser here on
purpose: everything the command accepts is derived from the verb function's
signature by :mod:`cadgen._internal.cli_from_function`, so a flag cannot drift
from a parameter (design/format-doors.md). Which input kinds the door accepts
is declared once, beside the verb, in
:data:`cadgen._internal.snapshot_door.DOOR_KINDS`.

The mesh half of ``cadgen step snapshot``, re-homed: 3MF is a format with a
door (``cadgen 3mf build``), so its snapshot belongs behind the same door. Its
verb is the MESH shape — normal-CAD display settings, but no kinematics,
section mode or selection. ``--display`` accepts mesh-neutral modes; options
that require CAD topology are absent from ``--help``.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from cadgen._internal.cli_from_function import generated_main, generated_parser

DEFAULT_PROG = "cadgen 3mf snapshot"
VERB = ("cadgen.threemf", "snapshot")


def build_parser(prog: str = DEFAULT_PROG) -> argparse.ArgumentParser:
    return generated_parser(VERB, prog=prog)


def main(argv: Sequence[str] | None = None, *, prog: str = DEFAULT_PROG) -> int:
    return generated_main(VERB, argv, prog=prog)


if __name__ == "__main__":
    raise SystemExit(main())
