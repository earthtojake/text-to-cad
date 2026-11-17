"""``cad auto-update`` -- show or change whether cad updates itself (``cad_server._internal.auto_update``), off by
default: ``status`` (the default) says both switches; ``on`` turns it on, refused unless this cad is a uv tool, and with
``--installer`` turns on too that the install command runs again after each update, recording this release as the one
it last ran for; ``off`` turns both off. ``CAD_UPDATE_CHECK=0`` in a process's environment keeps it from updating,
whatever the switches say.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence

DEFAULT_PROG = "cad auto-update"


def build_parser(prog: str = DEFAULT_PROG) -> argparse.ArgumentParser:
    from cad_server._internal.cli_parser import parser as command_parser

    parser = command_parser(prog=prog, description=(
        "Show or change whether cad updates itself to the newest release, as a uv tool: when the server starts, "
        "and once nothing has run for a minute, it stops, installs it with uv and starts again. Off by default. "
        "`off` turns both off."))
    parser.add_argument("action", nargs="?", choices=("status", "on", "off"), default="status")
    parser.add_argument("--installer", action="store_true",
                        help="with `on`: after each update, run the install command again too")
    return parser


def main(argv: Sequence[str] | None = None, *, prog: str = DEFAULT_PROG) -> int:
    parser = build_parser(prog)
    args = parser.parse_args(argv)
    if args.installer and args.action != "on":
        parser.error("--installer goes with `on`")
    from cad_server._internal import auto_update
    from cad_server._internal.cli_errors import Failure, write

    try:
        if args.action == "on":
            if auto_update.uv_tool() is None:
                return write(Failure("refused: this cad is not a uv tool, and only a uv tool updates itself "
                                     "(`uv tool install cad`)"), prog=prog, as_json=False)
            from cad_server import __version__

            auto_update.change(True, True if args.installer else None, __version__ if args.installer else None)
        elif args.action == "off":
            auto_update.change(False, False)
    except OSError as error:
        return write(Failure(f"could not save the choice: {error}"), prog=prog, as_json=False)
    found = auto_update.switches()
    print(f"auto-update: {'on' if found['on'] else 'off'}")
    print(f"installer: {'on' if found['installer'] else 'off'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
