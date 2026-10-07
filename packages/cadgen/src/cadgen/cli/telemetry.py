"""``cadgen telemetry`` -- show or change the usage stats cadgen sends: from CAD's apps (``cadgen mcp`` and
``cadgen viewer``) and its build daemon.

They are sent by default once a ``cadgen`` command has said so (``cadgen/analytics.py``). ``status`` (the
default) says what is sent and why, and says that notice itself if no command has yet; ``on`` and ``off``
keep the person's choice in the state directory, which every cadgen process reads: ``on`` sends what the
default does, as the person's own answer, and ``off`` sends nothing. ``DO_NOT_TRACK=1`` or
``CADGEN_TELEMETRY=0`` in an app's environment still turns it off there.
"""

from __future__ import annotations

import argparse
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

DEFAULT_PROG = "cadgen telemetry"

_REASONS = {
    "environment": "set by DO_NOT_TRACK or CADGEN_TELEMETRY in this environment",
    "choice": "your choice",
    "default": "by default, since cadgen said so{when}",
    "untold": "not until a cadgen command says so, which none does in CI or from a development install",
    "unavailable": "the telemetry setting could not be read",
}


def describe(found: dict[str, Any] | None = None, *, path: Path | None = None) -> str:
    """``on`` or ``off``, and why: what ``cadgen telemetry`` and ``cadgen doctor`` say."""
    from cadgen.analytics import status, told_at

    found = found if found is not None else status(path=path)
    told = told_at(path) if found["reason"] == "default" else None
    when = time.strftime(" on %Y-%m-%d", time.localtime(told)) if told else ""
    return f"{'on' if found['sharing'] else 'off'}: {_REASONS.get(found['reason'], _REASONS['unavailable']).format(when=when)}"


def build_parser(prog: str = DEFAULT_PROG) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=prog,
        description=(
            "Show or change the usage stats cadgen sends from CAD's apps (the CAD app in an agent app, and the CAD "
            "Viewer) and its build daemon. By default, once a cadgen command has said so: a random install id, "
            "versions, the OS and agent app, and counts of CAD tool calls, view activity, files shown by format, "
            "builds and snapshots, how they ended and how long they took. `off` sends nothing. Never file names, "
            "paths, contents or prompts."
        ),
    )
    parser.add_argument("action", nargs="?", choices=("status", "on", "off"), default="status")
    return parser


def main(argv: Sequence[str] | None = None, *, prog: str = DEFAULT_PROG) -> int:
    args = build_parser(prog).parse_args(argv)
    from cadgen.analytics import PRIVACY_URL, choose, notify, request_deletion, status
    from cadgen.settings import settings_path

    if args.action in ("on", "off"):
        # An off is kept before the receiver is asked to delete (a person at a terminal waits for that).
        chosen = choose(args.action == "on", by="cli", forget=request_deletion if args.action == "off" else None)
        if not chosen["saved"]:
            print(f"Could not save the choice: cadgen's state directory ({settings_path().parent}) could not be written. "
                  "Telemetry is unchanged; DO_NOT_TRACK=1 in an app's environment keeps it off there.")
            return 1
        if args.action == "off":
            print("Telemetry is off; the install id was deleted"
                  + (" and the data sent under it was deleted." if chosen.get("forgotten")
                     else ". The data sent under it will be deleted the next time cadgen can reach its server."))
    else:
        notify()  # where a person looks for it: said here when no command has said it yet
    found = status()
    if args.action != "off":
        print(f"Telemetry is {describe(found)}.")
        if found["reason"] == "default":
            print("It counts CAD's tool calls, views, files shown, builds and snapshots -- never what they hold: "
                  "`cadgen telemetry off` turns it off.")
        if found["id"]:
            print(f"Install id: {found['id']}")
    if found["reason"] == "environment" and args.action in ("on", "off"):
        print("Note: this environment's DO_NOT_TRACK or CADGEN_TELEMETRY overrides the choice here.")
    print(f"Privacy policy: {PRIVACY_URL}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
