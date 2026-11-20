"""``cad plugin`` -- the plugin in the agent apps on this computer, and the one command that reaches what cad knows of
them (``cad_server.plugin``).

- ``cad plugin install``: the one command that installs the plugin. For every agent app found here, the plugin
  installed or updated with that app's own command, then our older copies there removed (``cad_server.plugin.run``);
  then, where every app it found went well (none failed; none found counts) and this cad is the computer's global
  install, this cad kept as the release the plugin is up to date for (``plugin_catch_up.ended``: a fact about the
  computer, which a run where an app failed, or a cad run from anywhere else, never writes). That is all: it never
  changes ``cad plugin update auto``. It takes no options.
  In a person's terminal it builds the CAD logo first and keeps a live line under the apps' lines; anywhere else, the
  plain lines. Its exit status: 0 where it ended well; 1 where every app it found failed; 2 for a command line it
  does not take; ``plugin_catch_up.BUSY`` (75) where another run was going and a server began this one;
  ``plugin_catch_up.STOPPED`` (124) where a server's run was stopped at its deadline. Where ``CAD_PLUGIN_REPORT``
  names a file, what it did is written there as it ends. The hosted install command hands over to it, and this
  release's server runs it (``plugin_catch_up``).
- ``cad plugin update``: the same command under the name 0.11.12 and 0.11.13 gave it, run exactly as ``install`` is,
  and hidden: no help lists it. Released skills and scripts may run it.
- ``cad plugin update auto [status|on|off]``: whether the server runs ``cad plugin install`` once where this cad is
  newer than the release the plugin is up to date for, however cad got newer (``plugin_catch_up``), off by default.
  The hosted install command turns it on as its last step, and says there whether the plugin's step ended badly or
  an app failed (``plugin_catch_up.FAILED_ENV``): then nothing is taken as up to date; otherwise, and turned on by
  hand, the plugin is taken as up to date for the cad that turned it on, where that cad is the global install
  (``_keep``). Kept by the server where one runs, as ``cad update auto`` is, so a shell whose sandbox may not write
  the state folder needs no permission. It installs nothing, on this release and on every release before it.

A server's run: only one this release's server began (``plugin_catch_up.SERVER_ENV``, which no released cad sets) has
``INSTALL_SECONDS`` (``plugin_catch_up.deadline``): each command it runs is stopped, with every process it started,
when they are up, no further app is begun, and it exits ``STOPPED``. And where the run has not ended by itself a short
while past them, because a step of it never came back, it is ended all the same (``plugin_catch_up.HardStop``,
``_cut_off``): its record closed and the run counted as stopped, and the process gone with that exit status, so the
lock it held is free. It closes the record's run as it ends (``plugin_catch_up.ended``): ``ok`` only where every app
it found went well, so a run where one failed, whose exit status is 0 all the same, is tried again. Any other run has no
deadline, no such stop, and leaves the record's run as it is -- one the hosted install command started under an
earlier cad's server run above all: 0.11.12 and 0.11.13 name their server's run ``CAD_INSTALL_ATTEMPT``, which
everything it starts inherits, and which is not this command's to read (the hosted install command takes it out of
every cad command it starts, too).

One run at a time: a run holds one lock in the state folder for the whole run (``plugin_catch_up.run_lock``); a
second run waits for it, unless a server began it. No run starts an install command, hosted or other, ``cad update``,
or ``cad plugin update``: nothing reachable from here comes back to it. cad's own update begins none while a run is
going. Everything a run uses is imported before it begins (``_load``): an update of cad by hand may replace this
environment's files under it, and a module imported later would be another release's.

Each run is told and counted in the one place every run passes through (``_run``). Told: the dispatcher says the
telemetry notice for no ``cad plugin`` command (``cad_server.cli._UNTOLD``: a server runs ``cad plugin install`` with
its output in a log), so a run says it itself, before its work, where a person reads it (``_tell``): one a person
typed, or one the hosted install command handed over in a person's terminal; never one a server began, one an install
command cad itself started reached, nor ``cad plugin update auto``. Counted: as it ends, from what the run says it was
(``run.Facts``), one ``install`` event, counting the apps it found and those that failed, and one ``install_failure``
for each app where it failed, no other app named (``_count``, ``cad_server.analytics.install``), under every rule
telemetry has -- only once the person was told and never after a no, never in CI or from a development build,
nothing the run began before it was told, never a failure of the run, and nothing of it waits on the network. A crash
of the run is the command's, reported as every command's is (``cad_server.cli._report``).

Bare ``cad plugin`` prints this help. ``--refresh``, hidden, does nothing: the updater of 0.11.10 runs ``cad plugin
--refresh`` after it moves a computer.
"""

from __future__ import annotations

import argparse
import dataclasses
import os
import sys
import time
from collections.abc import Sequence
from typing import Any

DEFAULT_PROG = "cad plugin"


def build_parser(prog: str = DEFAULT_PROG) -> argparse.ArgumentParser:
    from cad_server._internal.cli_parser import parser as command_parser

    parser = command_parser(prog, description="The plugin in your agent apps: install or update it in every app found "
                                              "on this computer, or say whether cad's own updates update it too.")
    parser.add_argument("--refresh", action="store_true", help=argparse.SUPPRESS)
    commands = parser.add_subparsers(dest="command", metavar="{install}")
    commands.add_parser("install", help="install the plugin in every agent app found on this computer, or update it "
                                        "there",
                        description="Install the plugin in every agent app found on this computer, each with that "
                                    "app's own command, or update it where it is installed; then remove the older "
                                    "copies of it there. One line is printed per app. It exits 1 where every app it "
                                    "found failed.")
    # The name 0.11.12 and 0.11.13 gave the same run, and the switch under it: parsed, and listed by no help (a parser
    # added with no ``help`` is left out of its parent's list, and the metavar above names ``install`` alone).
    update = commands.add_parser("update", usage="%(prog)s [-h] [auto [{status,on,off}]]",
                                 description="The same as `cad plugin install`. `cad plugin update auto` shows or "
                                             "changes whether cad's updates update the plugin too.")
    automatic = update.add_subparsers(dest="what", metavar="{auto}")
    switch = automatic.add_parser("auto", prog=f"{update.prog} auto",
                                  help="show or change whether cad's updates update the plugin too",
                                  description="Show or change whether cad runs `cad plugin install` once each time it "
                                              "is newer than the release the plugin is up to date for, however it "
                                              "was updated, so the plugin stays as new as cad. Off by default; the "
                                              "install command turns it on.")
    switch.add_argument("action", nargs="?", choices=("status", "on", "off"), default="status")
    return parser


def main(argv: Sequence[str] | None = None, *, prog: str = DEFAULT_PROG) -> int:
    parser = build_parser(prog)
    args = parser.parse_args(list(sys.argv[1:] if argv is None else argv))
    if args.command == "update" and args.what == "auto":
        return _switch(args.action, f"{prog} update auto")
    if args.command in ("install", "update"):  # one command, by either name
        return _install(f"{prog} {args.command}")
    if not args.refresh:
        parser.print_help()
    return 0


# What a run uses of cad, beside this module: the apps and the run itself, the lock and the record (and what tells a
# global install, and the deadline it takes), what those write by, and what counts the run as it ends (telemetry, the
# sender it starts, and what they read: whether this is a development build, the app the command runs in, this cad's
# version).
_USES = ("cad_server.plugin.run", "cad_server._internal.plugin_catch_up", "cad_server._internal.auto_update",
         "cad_server._internal.auto_update_helper", "cad_server._internal.file_lock", "cad_server._internal.cli_errors",
         "cad_server.settings", "cad.engine.places", "cad._internal.atomic_replace", "cad_server.analytics",
         "cad_server._internal.telemetry_send", "cad_server._internal.editable", "cad_server._internal.engine_host",
         "cad_server._internal.apps", "cad_server._internal.api", "cad.engine.previous")


def _load() -> None:
    """Everything a run uses, imported before it begins (see the module)."""
    import importlib

    for name in _USES:
        importlib.import_module(name)


def _run(prog: str, *, seconds: float | None = None, stop: Any = None) -> Any:
    """One run of the plugin's install (``cad_server.plugin.run.install``): what it was (``run.Facts``, the one
    account of a run), its ``code`` the command's exit status. Told before it begins (``_tell``) and counted as it
    ends (``_count``), here and nowhere else -- but a run a server began that never ends by itself, which its hard
    stop (``stop``: ``plugin_catch_up.HardStop``) counts in its place (``_cut_off``), never both."""
    _load()
    from cad_server import analytics
    from cad_server.plugin import run

    began = time.monotonic()
    _tell(run.began_by(os.environ))
    under = analytics.in_force()  # the answer the run begins under: one that ends under another is not counted
    going: list[Any] = []  # the run's facts, from the moment it has any
    if stop is not None:
        stop.last = lambda: _cut_off(prog, seconds, going, under, began)

    facts = run.install(prog=prog, seconds=seconds, going=going.append)
    if stop is not None:
        stop.over()  # ended by itself: its own to count, and where the stop has begun this does not return
    _count(facts, under)
    return facts


def _cut_off(prog: str, seconds: float | None, going: Sequence[Any], under: Any, began: float) -> None:
    """The last words of a run a server began that its hard stop is ending (``plugin_catch_up.HardStop``, which has
    closed its record, and ends the process whatever becomes of this): one line where the run's lines go, and the
    run counted as one its deadline stopped (``_count``), with the apps it had done by then."""
    from cad_server.plugin import run

    took = time.monotonic() - began
    try:
        print(f"{prog}: ended after {took:.0f} seconds, past the {seconds:g} a run the cad server began may take: a "
              "step of it never came back, and what it had not done was left as it was", file=sys.stderr, flush=True)
    except (OSError, ValueError):
        pass
    facts = going[0] if going else run.Facts(by=run.began_by(os.environ))
    _count(dataclasses.replace(facts, outcome=run.FAILED, code=run.STOPPED, stopped=True, seconds=took,
                               apps=list(facts.apps)), under)
    try:
        sys.stdout.flush()  # the lines the run had said: the process exits without closing anything
    except (OSError, ValueError):
        pass


def _tell(by: str) -> None:
    """The telemetry notice (``cad_server.analytics.notify``: one line on stderr, once, kept as said), before a run
    whose output a person reads: one a person began, or one the hosted install command handed over (``by``:
    ``run.PERSON``, ``run.SCRIPT``). Never before a run a server began (``run.SERVER``), nor one reached from an
    install command cad itself started (``install_script.BY_CAD_ENV``: the bridge's, its output nowhere or in a log,
    and the one ``cad plugin update`` of 0.11.12 and 0.11.13 runs): a notice kept as said where nobody read it would
    have everything after it sent with no one told. Such a run is counted only where a person was told before it.
    Never raises: the notice never fails the run it rides on."""
    try:
        from cad_server import analytics
        from cad_server._internal.install_script import BY_CAD_ENV
        from cad_server.plugin import run

        if by in (run.PERSON, run.SCRIPT) and os.environ.get(BY_CAD_ENV) != "1":
            analytics.notify()
    except Exception:  # noqa: BLE001 - see above
        pass


def _count(facts: Any, under: Any) -> None:
    """The run counted (``cad_server.analytics.install``), from what it says it was (``run.Facts``) and nothing else: who
    began it, what its terminal was shown, its seconds, and each app it found with what was done there, the word for why
    it failed and its seconds -- of which only the failed ones are kept by name, the rest counted. One another run kept
    from running (``run.BUSY``) is counted as that, and names no app; one its deadline stopped (``Facts.stopped``, whose
    exit status says it failed) as stopped, with the apps it had found by then. Whether any other run ended well is not
    passed on but decided there from its apps, so no run is counted as ended in a way its own apps deny: failed exactly
    where every app it found failed -- the reading the receiver takes, which refuses any other with its whole batch.
    ``under``: the answer in force as the run began. Never raises: a count never fails the run."""
    try:
        from cad_server import analytics
        from cad_server.plugin import run

        busy = facts.outcome == run.BUSY
        apps = [] if busy else [(app.app, app.status, app.reason or None, app.seconds) for app in facts.apps]
        analytics.install(by=facts.by, busy=busy, stopped=bool(facts.stopped) and not busy, logo=facts.logo,
                          colour=facts.colour, seconds=facts.seconds, apps=apps, under=under)
    except Exception:  # noqa: BLE001 - see above
        pass


def _install(prog: str) -> int:
    """``cad plugin install``, by either name: one run (``_run``), then how it ended kept (``plugin_catch_up.ended``:
    this cad as the release the plugin is up to date for where every app it found went well on the global install;
    the record's run closed where this release's server began it, as failed where an app did). A server's run
    (``plugin_catch_up.deadline``) has its deadline and its hard stop; any other has neither."""
    _load()  # before the hard stop is armed: what it says and counts by is this release's, as the run's is
    from cad_server._internal import plugin_catch_up

    seconds = plugin_catch_up.deadline()
    stop = None if seconds is None else plugin_catch_up.HardStop(seconds)  # a run a server began: ended for certain
    try:
        try:
            facts = _run(prog, seconds=seconds, stop=stop)
        except Exception:
            plugin_catch_up.ended(1)  # a crash: the status Python gives it
            raise
        plugin_catch_up.ended(facts.code, failed=facts.failed > 0)
        return facts.code
    finally:
        if stop is not None:
            stop.cancel()


def _keep(on: bool, *, note: bool) -> bool:
    """``cad plugin update auto on|off``: the switch kept as ``on`` -- by the server where one runs
    (``_by_the_server``), else here -- and, turned on with ``note`` by this computer's global install of cad
    (``plugin_catch_up.tool``), this cad's release kept as the one the plugin is up to date for: the switch as it is
    now. ``OSError`` where it could not be kept.

    A cad that is no global install keeps no release, as a run that ended badly keeps none: the newest release run
    from uv's cache, a project's, a checkout's. Its release is not the installed cad's, and may be one that cad never
    reaches by itself (a higher major): kept, the server of the installed cad, which runs ``cad plugin install`` only
    where it is newer than the release kept, would never run it again. Where nothing is kept, the next server keeps
    its own (``plugin_catch_up.due``)."""
    from cad_server._internal import auto_update, plugin_catch_up
    from cad_server.cli.auto_update import _by_the_server

    if on and note and plugin_catch_up.tool() is None:
        note = False
    release = auto_update._version()
    found = _by_the_server("plugin_auto_update", on, release=release, **({} if note else {"note": False}))
    return auto_update.change_plugin(on, release, note=note) if found is None else found


def _line(on: bool) -> str:
    return f"plugin update auto: {'on' if on else 'off'}"


def _switch(action: str, prog: str) -> int:
    """``cad plugin update auto``: the switch said, or changed and said. It installs nothing (see the module)."""
    from cad_server._internal import auto_update, plugin_catch_up
    from cad_server._internal.cli_errors import Failure, write

    if action == "status":
        print(_line(auto_update.plugin_switch()))
        return 0
    try:  # the hosted install command's plugin step ended badly, or an app failed: nothing taken as up to date
        kept = _keep(action == "on", note=not plugin_catch_up.failing())
    except OSError as error:
        return write(Failure(f"could not save the choice: {error}"), prog=prog, as_json=False)
    print(_line(kept))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
