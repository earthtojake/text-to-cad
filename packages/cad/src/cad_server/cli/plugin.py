"""``cad plugin`` -- the one thing cad knows about plugins: the hosted install command, which puts text-to-cad's plugin
into every agent app it finds.

- ``cad plugin update``: the install command run in the foreground (``install_script.run``), its output and exit
  status this command's. ``CAD_INSTALL_BY_CAD=1`` is set for it, as for every run of it cad starts. Where it ends with
  exit status 0, this cad is kept as the release the install command is up to date for (``plugin_catch_up.ended``); a
  run that fails writes none. Where a server began this run (``plugin_catch_up.ATTEMPT_ENV``), the install command is
  stopped, with every process it started, after ``INSTALL_SECONDS``, and this command exits non-zero
  (``plugin_catch_up.deadline``); a person's own run has no deadline.
- ``cad plugin update auto [status|on|off]``: whether the server runs ``cad plugin update`` once where this cad is
  newer than the release the install command is up to date for, however cad got newer (``plugin_catch_up``), off by
  default; the install command turns it on wherever cad is there, and turning it on takes the install command as up
  to date for the cad that turned it on -- unless the install command that runs it says its run is ending badly
  (``plugin_catch_up.FAILED_ENV``): then nothing is taken as up to date. Kept by the server where one runs, as ``cad
  update auto`` is, so a shell whose sandbox may not write the state folder needs no permission.

Bare ``cad plugin`` prints this help. ``--refresh``, hidden, does nothing: the updater of 0.11.10 runs ``cad plugin
--refresh`` after it moves a computer.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

DEFAULT_PROG = "cad plugin"


def build_parser(prog: str = DEFAULT_PROG) -> argparse.ArgumentParser:
    from cad_server._internal.cli_parser import parser as command_parser

    parser = command_parser(prog, description="The plugin in your agent apps: install or update it with the install "
                                              "command, or say whether cad's own updates run that command again.")
    parser.add_argument("--refresh", action="store_true", help=argparse.SUPPRESS)
    commands = parser.add_subparsers(dest="command", metavar="{update}")
    update = commands.add_parser("update", usage="%(prog)s [-h] [auto [{status,on,off}]]",
                                 help="run the install command, which installs or updates the plugin in every agent "
                                      "app it finds; `update auto` shows or changes whether cad's updates run it",
                                 description="Run the install command (curl -fsSL https://texttocad.dev/install.sh | "
                                             "sh; on Windows irm https://www.texttocad.dev/install.ps1 | iex), which "
                                             "installs or updates the plugin in every agent app it finds. Its output "
                                             "and exit status are this command's.")
    automatic = update.add_subparsers(dest="what", metavar="{auto}")
    switch = automatic.add_parser("auto", prog=f"{update.prog} auto",
                                  help="show or change whether cad's updates run the install command",
                                  description="Show or change whether cad runs the install command once each time it "
                                              "is newer than the release that command is up to date for, however it "
                                              "was updated, so the plugin stays as new as cad. Off by default; the "
                                              "install command turns it on.")
    switch.add_argument("action", nargs="?", choices=("status", "on", "off"), default="status")
    return parser


def main(argv: Sequence[str] | None = None, *, prog: str = DEFAULT_PROG) -> int:
    parser = build_parser(prog)
    args = parser.parse_args(list(sys.argv[1:] if argv is None else argv))
    if args.command == "update" and args.what == "auto":
        return _switch(args.action, f"{prog} update auto")
    if args.command == "update":
        return _update(f"{prog} update")
    if not args.refresh:
        parser.print_help()
    return 0


def _update(prog: str) -> int:
    from cad_server._internal import install_script, plugin_catch_up
    from cad_server._internal.cli_errors import Failure, write

    try:
        code = install_script.run(seconds=plugin_catch_up.deadline())
    except OSError as error:
        plugin_catch_up.ended(None)
        return write(Failure(f"the install command could not start: {error}"), prog=prog, as_json=False)
    plugin_catch_up.ended(code)
    return code


def _switch(action: str, prog: str) -> int:
    from cad_server._internal import auto_update, plugin_catch_up
    from cad_server._internal.cli_errors import Failure, write
    from cad_server.cli.auto_update import _by_the_server

    found = None
    if action != "status":
        on = action == "on"
        note = not plugin_catch_up.failing()  # the install command's run ending badly: nothing taken as up to date
        try:
            found = _by_the_server("plugin_auto_update", on, release=auto_update._version(),
                                   **({} if note else {"note": False}))
            found = auto_update.change_plugin(on, note=note) if found is None else found
        except OSError as error:
            return write(Failure(f"could not save the choice: {error}"), prog=prog, as_json=False)
    print(f"plugin update auto: {'on' if (auto_update.plugin_switch() if found is None else found) else 'off'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
