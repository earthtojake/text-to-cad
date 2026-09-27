"""``cadgen dxf snapshot`` — draw a ``.dxf`` flat, as the CAD Viewer draws it.

A GENERATED CLI over :func:`cadgen.dxf.snapshot`. There is no parser here on
purpose: everything the command accepts is derived from the verb function's
signature by :mod:`cadgen._internal.cli_from_function`, so a flag cannot drift
from a parameter (design/format-doors.md). Which input kinds the door accepts
is declared once, beside the verb, in
:data:`cadgen._internal.snapshot_door.DOOR_KINDS`.

A drawing is not a scene, so this door binds the narrowest shape of the seven
(:func:`cadgen._internal.snapshot_door.drawing_snapshot_verb`): where, how big,
and light or dark. Everything that describes a camera, a surface or a light is
absent from the signature and therefore from the command.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from cadgen._internal.cli_from_function import generated_main, generated_parser

DEFAULT_PROG = "cadgen dxf snapshot"
VERB = ("cadgen.dxf", "snapshot")


def build_parser(prog: str = DEFAULT_PROG) -> argparse.ArgumentParser:
    return generated_parser(VERB, prog=prog)


def main(argv: Sequence[str] | None = None, *, prog: str = DEFAULT_PROG) -> int:
    return generated_main(VERB, argv, prog=prog)


if __name__ == "__main__":
    raise SystemExit(main())
