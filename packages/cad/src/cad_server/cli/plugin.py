"""``cad plugin`` -- the plugin in the agent apps on this computer, and the one command that reaches what cad knows of
them (``cad_server.plugin``).

- ``cad plugin install``: for every agent app found here, the plugin installed or updated with that app's own
  command, then our older copies there removed (``cad_server.plugin.run``); then ``cad plugin update auto`` turned on,
  and this cad kept as the release the plugin is up to date for only where the run ended well -- what ``cad plugin
  update auto on`` does, done in this process by the same code (``_keep``). It takes no options. In a person's
  terminal it builds the CAD logo first and keeps a live line under the apps' lines; anywhere else, the plain lines.
  Its exit status: 0 where it ended well; 1 where every app it found failed; 2 for a command line it does not take;
  ``plugin_catch_up.BUSY`` (75) where another run was going and a server began this one. Where ``CAD_PLUGIN_REPORT``
  names a file, what it did is written there as it ends. The hosted install command hands over to it.
- ``cad plugin update``: the same run, and what the server runs once where this cad is newer than the release the
  plugin is up to date for (``plugin_catch_up``). Where it ends with exit status 0, this cad is kept as that release
  (``plugin_catch_up.ended``); a run that fails writes none. Where a server began this run
  (``plugin_catch_up.ATTEMPT_ENV``), it has ``INSTALL_SECONDS`` (``plugin_catch_up.deadline``): each command it runs is
  stopped, with every process it started, when they are up, no further app is begun, and it exits non-zero; a
  person's own run has no deadline. ``cad plugin install`` keeps nothing of a server's run and has no deadline: one
  started under the install command an earlier cad's server ran carries that run's name, and must not end its record.
- ``cad plugin update auto [status|on|off]``: whether the server runs ``cad plugin update`` once where this cad is
  newer than the release the plugin is up to date for, however cad got newer (``plugin_catch_up``), off by default; a
  run of ``install`` or ``update`` turns it on, and turning it on takes the plugin as up to date for the cad that
  turned it on -- unless the install command of 0.11.12 or 0.11.13 that runs it says its run is ending badly
  (``plugin_catch_up.FAILED_ENV``): then nothing is taken as up to date. Kept by the server where one runs, as ``cad
  update auto`` is, so a shell whose sandbox may not write the state folder needs no permission.

One run at a time: ``install`` and ``update`` hold one lock in the state folder for the whole run
(``plugin_catch_up.run_lock``); a second run waits for it, unless a server began it. Neither runs an install command,
hosted or other, nor cad's own update, which begins none while a run is going. Everything a run uses is imported
before it begins (``_load``): an update of cad by hand may replace this environment's files under it, and a module
imported later would be another release's.

Bare ``cad plugin`` prints this help. ``--refresh``, hidden, does nothing: the updater of 0.11.10 runs ``cad plugin
--refresh`` after it moves a computer.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from typing import Any

DEFAULT_PROG = "cad plugin"


def build_parser(prog: str = DEFAULT_PROG) -> argparse.ArgumentParser:
    from cad_server._internal.cli_parser import parser as command_parser

    parser = command_parser(prog, description="The plugin in your agent apps: install or update it in every app found "
                                              "on this computer, or say whether cad's own updates update it too.")
    parser.add_argument("--refresh", action="store_true", help=argparse.SUPPRESS)
    commands = parser.add_subparsers(dest="command", metavar="{install,update}")
    commands.add_parser("install", help="install the plugin in every agent app found on this computer, or update it "
                                        "there",
                        description="Install the plugin in every agent app found on this computer, each with that "
                                    "app's own command, or update it where it is installed; then remove the older "
                                    "copies of it there, and turn on `cad plugin update auto`. One line is printed "
                                    "per app. It exits 1 where every app it found failed.")
    update = commands.add_parser("update", usage="%(prog)s [-h] [auto [{status,on,off}]]",
                                 help="update the plugin in every agent app found on this computer, as `install` "
                                      "does; `update auto` shows or changes whether cad's updates do",
                                 description="Update the plugin in every agent app found on this computer, or install "
                                             "it where it is not: what `cad plugin install` does, and what cad runs "
                                             "by itself after its own update where `cad plugin update auto` is on.")
    automatic = update.add_subparsers(dest="what", metavar="{auto}")
    switch = automatic.add_parser("auto", prog=f"{update.prog} auto",
                                  help="show or change whether cad's updates update the plugin too",
                                  description="Show or change whether cad runs `cad plugin update` once each time it "
                                              "is newer than the release the plugin is up to date for, however it "
                                              "was updated, so the plugin stays as new as cad. Off by default; "
                                              "`cad plugin install` and `cad plugin update` turn it on.")
    switch.add_argument("action", nargs="?", choices=("status", "on", "off"), default="status")
    return parser


def main(argv: Sequence[str] | None = None, *, prog: str = DEFAULT_PROG) -> int:
    parser = build_parser(prog)
    args = parser.parse_args(list(sys.argv[1:] if argv is None else argv))
    if args.command == "update" and args.what == "auto":
        return _switch(args.action, f"{prog} update auto")
    if args.command == "update":
        return _update(f"{prog} update")
    if args.command == "install":
        return _run(f"{prog} install").code
    if not args.refresh:
        parser.print_help()
    return 0


# What a run uses of cad, beside this module: the apps and the run itself, the lock and the record, the switch and the
# server asked to keep it, and what those write by.
_USES = ("cad_server.plugin.run", "cad_server._internal.plugin_catch_up", "cad_server._internal.auto_update",
         "cad_server._internal.auto_update_helper", "cad_server._internal.file_lock", "cad_server._internal.cli_errors",
         "cad_server.cli.auto_update", "cad_server.settings", "cad.engine.client", "cad.engine.places",
         "cad._internal.atomic_replace")


def _load() -> str:
    """Everything a run uses, imported before it begins (see the module), and this cad's release read: the release."""
    import importlib

    for name in _USES:
        importlib.import_module(name)
    from cad_server._internal import auto_update

    return auto_update._version()


def _run(prog: str, *, seconds: float | None = None) -> Any:
    """One run of the plugin's install (``cad_server.plugin.run.install``), by ``install`` and ``update`` alike: what
    it was (``run.Facts``, the one account of a run), its ``code`` the command's exit status."""
    release = _load()
    from cad_server.plugin import run

    def switch(well: bool) -> str:
        return _line(_keep(True, note=well, release=release))

    return run.install(switch, prog=prog, seconds=seconds)


def _update(prog: str) -> int:
    from cad_server._internal import plugin_catch_up

    try:
        code = _run(prog, seconds=plugin_catch_up.deadline()).code
    except Exception:
        plugin_catch_up.ended(1)  # a crash: the status Python gives it
        raise
    plugin_catch_up.ended(code)
    return code


def _keep(on: bool, *, note: bool, release: str | None = None) -> bool:
    """The switch kept as ``on`` -- by the server where one runs (``_by_the_server``), else here -- and, turned on with
    ``note``, ``release`` (this cad's by default) kept as the one the plugin is up to date for: the switch as it is
    now. ``OSError`` where it could not be kept."""
    from cad_server._internal import auto_update
    from cad_server.cli.auto_update import _by_the_server

    release = release or auto_update._version()
    found = _by_the_server("plugin_auto_update", on, release=release, **({} if note else {"note": False}))
    return auto_update.change_plugin(on, release, note=note) if found is None else found


def _line(on: bool) -> str:
    return f"plugin update auto: {'on' if on else 'off'}"


def _switch(action: str, prog: str) -> int:
    from cad_server._internal import auto_update, plugin_catch_up
    from cad_server._internal.cli_errors import Failure, write

    if action == "status":
        print(_line(auto_update.plugin_switch()))
        return 0
    try:  # an install command's run ending badly (0.11.12, 0.11.13): nothing taken as up to date
        kept = _keep(action == "on", note=not plugin_catch_up.failing())
    except OSError as error:
        return write(Failure(f"could not save the choice: {error}"), prog=prog, as_json=False)
    print(_line(kept))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
