"""``cad plugin``: the plugin folder every agent app here is pointed at, written from this installation,
and its path printed.

The folder (``cad_server._internal.plugin``) follows the release that is current: run by the current
installation (as the ``cad`` command runs it), or on a device with none current, this writes it again in
place -- nothing is touched when it already holds this release's plugin -- and prints its path; run by
another installation, it prints the path and says which one writes it. ``--refresh``, which the switch
of the device's engine runs (``cad_server._internal.switch``), also brings the copies apps keep of the
folder to it when this changed it -- an app's copy of the plugin, added or copied again, and the skills
the Skills CLI copied for the agents without a plugin (``cad_server.cli.setup.refresh_copies``,
``cad_server._internal.providers.refresh_plan``); an app that reads the folder in place needs nothing.

Exit status: 0 done; 1 the folder could not be written; 2 bad arguments.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence

DEFAULT_PROG = "cad plugin"


def build_parser(prog: str = DEFAULT_PROG) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=prog,
        allow_abbrev=False,
        description="Write text-to-cad's plugin folder, which every agent app here is pointed at, from this "
                    "installation (when it is the current one), and print its path.",
    )
    parser.add_argument("--refresh", action="store_true",
                        help="also, when the folder changed, bring the copies apps keep of it to it (an app's "
                             "copy of the plugin, the skills the Skills CLI copied)")
    parser.add_argument("--json", action="store_true", help="print what was done as JSON")
    return parser


def main(argv: Sequence[str] | None = None, prog: str = DEFAULT_PROG) -> int:
    args = build_parser(prog).parse_args(argv)
    from cad_server._internal import installations, plugin

    path = str(plugin.folder())
    current = installations.current()
    result: dict = {"path": path, "written": None, "refreshed": None}
    if current is not None and not installations.mine(current):
        print(f"text-to-cad {current['version']} is the current installation: its `cad plugin` writes the folder",
              file=sys.stderr)
    else:
        try:
            result["written"] = plugin.write()
        except (plugin.Missing, OSError, ValueError) as error:
            print(f"cad plugin: {path} could not be written: {error}", file=sys.stderr)
            return 1
        plugin.say_written(result["written"], lambda line: print(line, file=sys.stderr))
        done = result["written"]
        if args.refresh and (done["created"] or done["changed"] or done["removed"]):
            from cad_server.cli.setup import refresh_copies

            ok, steps = refresh_copies(told=lambda line: print(line, file=sys.stderr))
            result["refreshed"] = steps
            if not ok:
                _say(args, result)
                return 1
    _say(args, result)
    return 0


def _say(args: argparse.Namespace, result: dict) -> None:
    if args.json:
        sys.stdout.write(json.dumps(result, ensure_ascii=False, separators=(",", ":")) + "\n")
    else:
        sys.stdout.write(result["path"] + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
