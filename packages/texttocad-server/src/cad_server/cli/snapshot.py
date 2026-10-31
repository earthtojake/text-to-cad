"""``cadgen snapshot SRC OUT.png``: a document, a mesh file, a robot or a drawing drawn by OCCT
as the CAD Viewer draws it (``cad_server.engine.cli``).

The parser and the run are the engine's (``cad_server.engine.cli.parser_for``, ``run``), the same
verb ``python -m cad_server.engine snapshot`` takes.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence

DEFAULT_PROG = "cadgen snapshot"
ENGINE_VERB = "snapshot"


def build_parser(prog: str = DEFAULT_PROG) -> argparse.ArgumentParser:
    from cad_server.engine.cli import parser_for

    return parser_for(ENGINE_VERB, prog)


def main(argv: Sequence[str] | None = None, *, prog: str = DEFAULT_PROG) -> int:
    from cad_server.engine.cli import run

    return run(ENGINE_VERB, list(argv) if argv is not None else None, prog)


if __name__ == "__main__":
    raise SystemExit(main())
