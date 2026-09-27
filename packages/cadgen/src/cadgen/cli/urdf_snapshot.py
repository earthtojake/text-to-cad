"""``cadgen urdf snapshot`` — render URDF robot descriptions.

A GENERATED CLI over :func:`cadgen.urdf.snapshot`. There is no parser here on
purpose: everything the command accepts is derived from the verb function's
signature by :mod:`cadgen._internal.cli_from_function`, so a flag cannot drift
from a parameter (design/format-doors.md). Which input kinds the door accepts
is declared once, beside the verb, in
:data:`cadgen._internal.snapshot_door.DOOR_KINDS`.

The verb is the ROBOT shape: the mesh surface plus ``--joint-values``, which is
how a description gets posed. STEP-only flags (selection, kinematics, section
mode) are not in this signature at all, and ``--display`` takes ``solid`` or
``render``: the settings that describe a CAD model (edges, clip, exploded, the
edge-made modes, hidden/off surfaces) are refused by name.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from cadgen._internal.cli_from_function import generated_main, generated_parser

DEFAULT_PROG = "cadgen urdf snapshot"
VERB = ("cadgen.urdf", "snapshot")


def build_parser(prog: str = DEFAULT_PROG) -> argparse.ArgumentParser:
    return generated_parser(VERB, prog=prog)


def main(argv: Sequence[str] | None = None, *, prog: str = DEFAULT_PROG) -> int:
    return generated_main(VERB, argv, prog=prog)


if __name__ == "__main__":
    raise SystemExit(main())
