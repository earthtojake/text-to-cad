"""``cadgen viewer`` ensures the engine, prints or opens its page URL, and exits.

The parser and launcher contract live in ``cadgen.viewer.main``.
"""

from __future__ import annotations

from collections.abc import Sequence

DEFAULT_PROG = "cadgen viewer"


def main(argv: Sequence[str] | None = None, *, prog: str = DEFAULT_PROG) -> int:
    import sys

    from cadgen.viewer.main import main as launch

    return launch(list(sys.argv[1:] if argv is None else argv), prog=prog)


if __name__ == "__main__":
    raise SystemExit(main())
