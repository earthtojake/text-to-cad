"""``cadgen harness snapshot`` — draw a wiring harness document as WireViz draws it, as the CAD Viewer draws it.

A GENERATED CLI over :func:`cadgen.harness.snapshot`. There is no parser here on
purpose: everything the command accepts is derived from the verb function's
signature by :mod:`cadgen._internal.cli_from_function`, so a flag cannot drift
from a parameter (design/format-doors.md). Which input kinds the door accepts
is declared once, beside the verb, in
:data:`cadgen._internal.snapshot_door.DOOR_KINDS`.

A plot is not a scene, so this door binds the drawing's narrow shape
(:func:`cadgen._internal.snapshot_door.plot_snapshot_verb`): where, how big,
and light or dark around the diagram.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from cadgen._internal.cli_from_function import generated_main, generated_parser

DEFAULT_PROG = "cadgen harness snapshot"
VERB = ("cadgen.harness", "snapshot")


def build_parser(prog: str = DEFAULT_PROG) -> argparse.ArgumentParser:
    return generated_parser(VERB, prog=prog)


def main(argv: Sequence[str] | None = None, *, prog: str = DEFAULT_PROG) -> int:
    return generated_main(VERB, argv, prog=prog)


if __name__ == "__main__":
    raise SystemExit(main())
