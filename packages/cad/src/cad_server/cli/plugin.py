"""``cad plugin`` -- the one thing cad knows about plugins: the hosted install command, which puts text-to-cad's plugin
into every agent app it finds.

- ``cad plugin install``: the install command run in the foreground (``install_script.run``), its output and exit
  status this command's. ``CAD_INSTALL_BY_CAD=1`` is set for it, as for every run of it cad starts. As it ends, the
  release it ended well for is kept, or the one before put back where it failed (``plugin_catch_up.ended``).
- ``cad plugin auto-update [status|on|off]``: whether the server runs ``cad plugin install`` once where this cad is
  newer than the release the install command last ended well for, however cad got newer (``plugin_catch_up``), off by
  default; the install command turns it on, and turning it on takes the install command as up to date for the cad
  that turned it on. Kept by the server where one runs, as ``cad auto-update`` is, so a shell whose sandbox may not
  write the state folder needs no permission.

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

    parser = command_parser(prog, description="The plugin in your agent apps: install it with the install command, or "
                                              "say whether cad's own updates run that command again.")
    parser.add_argument("--refresh", action="store_true", help=argparse.SUPPRESS)
    commands = parser.add_subparsers(dest="command", metavar="{install,auto-update}")
    commands.add_parser("install", help="run the install command, which puts the plugin into every agent app it finds",
                        description="Run the install command (curl -fsSL https://texttocad.dev/install.sh | sh; on "
                                    "Windows irm https://www.texttocad.dev/install.ps1 | iex), which puts the plugin "
                                    "into every agent app it finds. Its output and exit status are this command's.")
    switch = commands.add_parser("auto-update", help="show or change whether cad's updates run the install command",
                                 description="Show or change whether cad runs the install command once each time it "
                                             "is newer than the release that command last ran for, however it was "
                                             "updated, so the plugin stays as new as cad. Off by default; the install "
                                             "command turns it on.")
    switch.add_argument("action", nargs="?", choices=("status", "on", "off"), default="status")
    return parser


def main(argv: Sequence[str] | None = None, *, prog: str = DEFAULT_PROG) -> int:
    parser = build_parser(prog)
    args = parser.parse_args(list(sys.argv[1:] if argv is None else argv))
    if args.command == "install":
        from cad_server._internal import install_script, plugin_catch_up
        from cad_server._internal.cli_errors import Failure, write

        before = plugin_catch_up.read().get("for")
        try:
            code = install_script.run()
        except OSError as error:
            plugin_catch_up.ended(None, before)
            return write(Failure(f"the install command could not start: {error}"), prog=f"{prog} install",
                         as_json=False)
        plugin_catch_up.ended(code, before)
        return code
    if args.command == "auto-update":
        return _switch(args.action, f"{prog} auto-update")
    if not args.refresh:
        parser.print_help()
    return 0


def _switch(action: str, prog: str) -> int:
    from cad_server._internal import auto_update
    from cad_server._internal.cli_errors import Failure, write
    from cad_server.cli.auto_update import _by_the_server

    found = None
    if action != "status":
        on = action == "on"
        try:
            found = _by_the_server("plugin_auto_update", on, release=auto_update._version())
            found = auto_update.change_plugin(on) if found is None else found
        except OSError as error:
            return write(Failure(f"could not save the choice: {error}"), prog=prog, as_json=False)
    print(f"plugin auto-update: {'on' if (auto_update.plugin_switch() if found is None else found) else 'off'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
