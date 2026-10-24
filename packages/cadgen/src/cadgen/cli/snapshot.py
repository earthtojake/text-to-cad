"""``cadgen snapshot SRC OUT.png``: a document, a mesh file, a robot or a drawing drawn by OCCT
as the CAD Viewer draws it (``cadgen.engine.cli``).

The parser and the run are the engine's (``cadgen.engine.cli.parser_for``, ``run``), the same
verb ``python -m cadgen.engine snapshot`` takes.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence

DEFAULT_PROG = "cadgen snapshot"
ENGINE_VERB = "snapshot"


def build_parser(prog: str = DEFAULT_PROG) -> argparse.ArgumentParser:
    from cadgen.engine.cli import parser_for

    return parser_for(ENGINE_VERB, prog)


def main(argv: Sequence[str] | None = None, *, prog: str = DEFAULT_PROG) -> int:
    from cadgen.engine.cli import run

    return run(ENGINE_VERB, list(argv) if argv is not None else None, prog)


if __name__ == "__main__":
    raise SystemExit(main())
