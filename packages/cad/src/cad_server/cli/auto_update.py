"""``cad auto-update`` -- show or change whether cad updates itself (``cad_server._internal.auto_update``), off by
default: ``status`` (the default) says both switches; ``on`` turns it on, refused unless this cad is a uv tool, and with
``--installer`` turns on too that the install command runs again after each update, recording this release as the one
it last ran for; ``off`` turns both off. Where a server runs, of any release that knows how, it keeps them
(``_by_the_server``), so a shell whose sandbox may not write the state folder needs no permission; with none, this
command writes them. ``CAD_UPDATE_CHECK=0`` in a process's environment keeps it from updating, whatever the switches
say.
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

    found = None
    if args.action != "status":
        if args.action == "on" and auto_update.uv_tool() is None:  # this command's own cad, wherever it is written
            return write(Failure("refused: this cad is not a uv tool, and only a uv tool updates itself "
                                 "(`uv tool install cad`)"), prog=prog, as_json=False)
        from cad_server import __version__

        on = args.action == "on"
        installer = (True if args.installer else None) if on else False
        ran_for = __version__ if on and args.installer else None
        try:
            found = _by_the_server(on, installer, ran_for)
            if found is None:
                found = auto_update.change(on, installer, ran_for)
        except OSError as error:
            return write(Failure(f"could not save the choice: {error}"), prog=prog, as_json=False)
    found = found or auto_update.switches()
    print(f"auto-update: {'on' if found['on'] else 'off'}")
    print(f"installer: {'on' if found['installer'] else 'off'}")
    return 0


def _by_the_server(on: bool, installer: bool | None, ran_for: str | None) -> dict | None:
    """The switches changed by the server running, of any release that knows how (``{"op": "auto_update"}``), as
    every other command a skill runs has the server do its writing: so a shell whose sandbox may not write cad's state
    folder (an agent app's) changes them with no permission asked. The switches as it kept them; None where no server answers,
    or one too old to know the request: then this command writes them itself. ``OSError`` in the server's words where
    it could not keep them."""
    from cad.engine import client

    request = {"op": "auto_update", "on": on, "installer": installer, "ran_for": ran_for}
    try:
        answer = client.request(request, start=False, timeout=STATUS_SECONDS)
    except ConnectionError:
        return None  # none this shell may reach: written here, as with none running
    if not isinstance(answer, dict) or str(answer.get("failed", "")).startswith("unknown request"):
        return None
    if answer.get("ok") is True and isinstance(answer.get("switches"), dict):
        return answer["switches"]
    raise OSError(str(answer.get("failed") or "the server did not keep it"))


# How long the server may take to keep the switches: one that never answers is not waited on.
STATUS_SECONDS = 10.0


if __name__ == "__main__":
    raise SystemExit(main())
