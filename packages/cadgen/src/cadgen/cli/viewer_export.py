"""``cadgen viewer export`` — a folder's CAD files recorded as a static copy of the viewer's API.

A thin shell over :func:`cadgen.viewer.export.main`, which owns the parser and the export
(``export.json`` and ``objects/`` under ``--out``). ``python -m cadgen.viewer export`` reaches it too.
"""

from __future__ import annotations

from collections.abc import Sequence

DEFAULT_PROG = "cadgen viewer export"


def main(argv: Sequence[str] | None = None, *, prog: str = DEFAULT_PROG) -> int:
    import sys

    from cadgen.viewer.export import main as export_main

    return export_main(list(sys.argv[1:] if argv is None else argv), prog=prog)


if __name__ == "__main__":
    raise SystemExit(main())
