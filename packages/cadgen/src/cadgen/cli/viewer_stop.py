"""``cadgen viewer stop`` — ask the CAD Viewer on a port (3245 unless ``--port``) to exit."""

from __future__ import annotations

from collections.abc import Sequence

DEFAULT_PROG = "cadgen viewer stop"


def main(argv: Sequence[str] | None = None, *, prog: str = DEFAULT_PROG) -> int:
    import sys

    from cadgen.viewer.main import stop_command

    return stop_command(list(sys.argv[1:] if argv is None else argv), prog=prog)


if __name__ == "__main__":
    raise SystemExit(main())
