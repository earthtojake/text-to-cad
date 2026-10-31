"""``cad update auto`` -- show or change automatic updates (``cad_server/auto_updates.py``).

``status`` (the default) says whether the engine updates by itself and why, when the version feed was
last read and when it is next due, and a release the engine is getting ready to switch to. ``on`` and
``off`` keep the person's answer in their settings, which every CAD app and release reads, the CAD
Viewer's and the CAD app's Automatic updates among them. ``CAD_UPDATE_CHECK=0`` in an engine's
environment turns it off there whatever is kept here.

A verb of its own beside ``cad update`` rather than an option of it: ``cad update``'s options are what an
update hands to the release it installs (``cad setup``'s), the same in every release.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence

DEFAULT_PROG = "cad update auto"


def build_parser(prog: str = DEFAULT_PROG) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=prog,
        description="Show or change automatic updates. While they are on (by default), the engine reads the version "
                    "feed once an hour and, when a newer release is out, installs it in the background and switches to "
                    "it once nothing has run for a minute, as the update button does. `off` leaves every update to you: "
                    "the update button, `cad update` or the install command.",
    )
    parser.add_argument("action", nargs="?", choices=("status", "on", "off"), default="status")
    return parser


def main(argv: Sequence[str] | None = None, *, prog: str = DEFAULT_PROG) -> int:
    args = build_parser(prog).parse_args(argv)
    from cad_server import auto_updates
    from cad_server.settings import settings_path

    if args.action in ("on", "off"):
        try:
            auto_updates.change({"automatic": args.action == "on"})
        except OSError as error:
            print(f"Could not save the choice: the state directory ({settings_path().parent}) could not be written "
                  f"({error.strerror or error}). Automatic updates are unchanged.")
            return 1
    engine = None
    try:
        from cad.engine.client import request

        answer = request({"op": "status"}, start=False)
        engine = answer.get("update") if isinstance(answer, dict) else None
    except Exception:  # noqa: BLE001 - what the engine is getting ready is said when it can be asked
        engine = None
    print(f"Automatic updates are {auto_updates.describe(engine)}.")
    if auto_updates.read()["reason"] == "environment" and args.action == "on":
        print("Note: this environment's CAD_UPDATE_CHECK or CI keeps them off here.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
