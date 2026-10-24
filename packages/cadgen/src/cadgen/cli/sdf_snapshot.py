"""``cadgen sdf snapshot`` -- draw an SDFormat world or model into a PNG, where the CAD Viewer
opens it, its link meshes placed by forward kinematics.

``cadgen snapshot`` (``cadgen.engine.snapshot``) for a ``.sdf`` alone: the same parser and the
same picture, by OCCT; any other file is refused by name before anything renders.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence

DEFAULT_PROG = "cadgen sdf snapshot"
SUFFIXES = (".sdf",)


def build_parser(prog: str = DEFAULT_PROG) -> argparse.ArgumentParser:
    from cadgen.engine.snapshot import build_parser as snapshot_parser

    return snapshot_parser(prog)


def main(argv: Sequence[str] | None = None, *, prog: str = DEFAULT_PROG) -> int:
    from cadgen.engine.snapshot import main as snapshot

    return snapshot(list(argv) if argv is not None else None, prog=prog, suffixes=SUFFIXES)


if __name__ == "__main__":
    raise SystemExit(main())
