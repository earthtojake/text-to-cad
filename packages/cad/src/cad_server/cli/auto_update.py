"""``cad auto-update`` -- show or change whether cad updates itself (``cad_server._internal.auto_update``), on by
default: ``status`` (the default) says it; ``on`` turns it on, refused unless this cad is a global install; ``off``
turns it off. A cad that is no global install never updates itself, and ``status`` says so. Where a server runs, of any
release that knows how, it keeps the switch (``_by_the_server``), so a shell whose sandbox may not write the state
folder needs no permission; with none, this command writes it. ``CAD_UPDATE_CHECK=0`` in a process's environment keeps
it from updating, whatever the switch says.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence

DEFAULT_PROG = "cad auto-update"
NOT_GLOBAL = "this cad is not a global install, so it does not update itself (`uv tool install cad` makes one)"
REFUSED = "refused: this cad is not a global install, and only a global install updates itself (`uv tool install cad`)"


def build_parser(prog: str = DEFAULT_PROG) -> argparse.ArgumentParser:
    from cad_server._internal.cli_parser import parser as command_parser

    parser = command_parser(prog=prog, description=(
        "Show or change whether cad updates itself to the newest release: once nothing has run for a minute, the cad "
        "server stops, installs it and starts again. On by default, for a global install (`uv tool install cad`)."))
    parser.add_argument("action", nargs="?", choices=("status", "on", "off"), default="status")
    return parser


def main(argv: Sequence[str] | None = None, *, prog: str = DEFAULT_PROG) -> int:
    args = build_parser(prog).parse_args(argv)
    from cad_server._internal import auto_update
    from cad_server._internal.cli_errors import Failure, write

    found = None
    if args.action == "on" and auto_update.global_install() is None:  # this command's own cad, wherever it is written
        return write(Failure(REFUSED), prog=prog, as_json=False)
    if args.action != "status":
        on = args.action == "on"
        try:
            found = _by_the_server("auto_update", on)
            found = auto_update.change(on)["on"] if found is None else found
        except OSError as error:
            return write(Failure(f"could not save the choice: {error}"), prog=prog, as_json=False)
    elif auto_update.global_install() is None:
        print(NOT_GLOBAL)
        return 0
    print(f"auto-update: {'on' if (auto_update.switches()['on'] if found is None else found) else 'off'}")
    return 0


def _by_the_server(op: str, on: bool, **more: str) -> bool | None:
    """A switch changed by the server running, of any release that knows the request (``{"op": "auto_update"}``,
    ``{"op": "plugin_auto_update"}``, with ``more`` beside it: the plugin's switch names the release of the cad that
    asks), as every other command a skill runs has the server do its writing: so a shell
    whose sandbox may not write cad's state folder (an agent app's) changes it with no permission asked. The switch as
    it kept it; None where no server answers, or one too old to know the request: then the command writes it itself.
    ``OSError`` in the server's words where it could not keep it."""
    from cad.engine import client

    try:
        answer = client.request({"op": op, "on": on, **more}, start=False, timeout=STATUS_SECONDS)
    except ConnectionError:
        return None  # none this shell may reach: written here, as with none running
    if not isinstance(answer, dict) or str(answer.get("failed", "")).startswith("unknown request"):
        return None
    kept = answer.get("on") if op != "auto_update" else (answer.get("switches") or {}).get("on")
    if answer.get("ok") is True and isinstance(kept, bool):
        return kept
    raise OSError(str(answer.get("failed") or "the server did not keep it"))


# How long the server may take to keep a switch: one that never answers is not waited on.
STATUS_SECONDS = 10.0


if __name__ == "__main__":
    raise SystemExit(main())
