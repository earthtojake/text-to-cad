"""``cadgen viewer`` — serve the current directory in the CAD Viewer.

A thin shell over :func:`cadgen.viewer.main.serve`, which owns the parser and the
launcher contract (reuse-or-start, port roll, the ``--json`` announce line). The
instance manager verbs are :mod:`cadgen.cli.viewer_list` and
:mod:`cadgen.cli.viewer_stop`; ``python -m cadgen.viewer`` reaches all three.
"""

from __future__ import annotations

from collections.abc import Sequence

DEFAULT_PROG = "cadgen viewer"


def main(argv: Sequence[str] | None = None, *, prog: str = DEFAULT_PROG) -> int:
    import sys

    from cadgen.viewer.main import serve

    return serve(list(sys.argv[1:] if argv is None else argv), prog=prog)


if __name__ == "__main__":
    raise SystemExit(main())
