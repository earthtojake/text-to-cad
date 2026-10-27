"""Draw a saved .kicad_pcb into a PNG with the engine's native board renderer."""

from __future__ import annotations

import argparse
from collections.abc import Sequence

DEFAULT_PROG = "cadgen pcb snapshot"
SUFFIXES = (".kicad_pcb",)


def build_parser(prog: str = DEFAULT_PROG) -> argparse.ArgumentParser:
    from cadgen.engine.snapshot import build_parser as snapshot_parser

    return snapshot_parser(prog)


def main(argv: Sequence[str] | None = None, *, prog: str = DEFAULT_PROG) -> int:
    from cadgen.engine.snapshot import main as snapshot

    return snapshot(list(argv) if argv is not None else None, prog=prog, suffixes=SUFFIXES)


if __name__ == "__main__":
    raise SystemExit(main())
