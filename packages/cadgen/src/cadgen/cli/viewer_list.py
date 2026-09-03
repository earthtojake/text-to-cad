"""``cadgen viewer list`` — show running CAD Viewers and what each serves."""

from __future__ import annotations

from collections.abc import Sequence

DEFAULT_PROG = "cadgen viewer list"


def main(argv: Sequence[str] | None = None, *, prog: str = DEFAULT_PROG) -> int:
    import sys

    from cadgen.viewer.main import list_command

    return list_command(list(sys.argv[1:] if argv is None else argv), prog=prog)


if __name__ == "__main__":
    raise SystemExit(main())
