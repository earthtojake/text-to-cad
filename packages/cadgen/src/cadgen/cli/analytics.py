"""``cadgen analytics`` -- show or change whether ``cadgen mcp`` sends anonymous usage analytics.

``status`` (the default) says whether counts are sent and why; ``on`` and ``off`` keep the
person's choice in the state directory, which every agent app's CAD server reads.
``DO_NOT_TRACK=1`` or ``CADGEN_ANALYTICS=0`` in an app's environment still turns it off there.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence

DEFAULT_PROG = "cadgen analytics"

_REASONS = {
    "environment": "set by DO_NOT_TRACK or CADGEN_ANALYTICS in this environment",
    "choice": "your choice",
    "unasked": "off until you answer the CAD app's prompt, or run `cadgen analytics on`",
    "unavailable": "off: the analytics setting could not be read",
}


def build_parser(prog: str = DEFAULT_PROG) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=prog,
        description=(
            "Show or change whether CAD's agent app (cadgen mcp) sends anonymous usage analytics: a random "
            "install id, versions, the OS and agent app, counts of CAD tool calls and view activity, and a "
            "one-way code and the format of each distinct file shown. Never file names, paths, contents or prompts."
        ),
    )
    parser.add_argument("action", nargs="?", choices=("status", "on", "off"), default="status")
    return parser


def main(argv: Sequence[str] | None = None, *, prog: str = DEFAULT_PROG) -> int:
    args = build_parser(prog).parse_args(argv)
    from cadgen.analytics import PRIVACY_URL, choose, request_deletion, status

    if args.action == "on":
        choose(True, by="cli")
    elif args.action == "off":
        chosen = choose(False, by="cli", forget=request_deletion)  # a person at a terminal waits for it
        print("Analytics are off; the install id was deleted"
              + (" and the data sent under it was deleted." if chosen.get("forgotten")
                 else ". The data sent under it will be deleted the next time CAD can reach its server."))
    found = status()
    if args.action != "off":
        print(f"Analytics are {'on' if found['sharing'] else 'off'}: {_REASONS[found['reason']]}.")
        if found["id"]:
            print(f"Install id: {found['id']}")
    if found["reason"] == "environment" and args.action in ("on", "off"):
        print("Note: this environment's DO_NOT_TRACK or CADGEN_ANALYTICS overrides the choice here.")
    print(f"Privacy policy: {PRIVACY_URL}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
