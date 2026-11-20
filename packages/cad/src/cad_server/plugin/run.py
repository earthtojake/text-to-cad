"""One run of ``cad plugin install`` (``install``), and what it was (``Facts``).

A run holds the one lock of such runs from its start to its end (``plugin_catch_up.run_lock``): where another run
holds it (still, after the moment a run tries for it), a run a server began ends with exit status
``plugin_catch_up.BUSY`` and one line, and any other (a person's, the hosted install command's) says it waits, waits,
then runs. Then, for every app of ``apps.APPS`` found here: ours in, then old copies out (``apps.install_apps``), a
line said per app. In a person's terminal (``terminal.Screen``) it first builds the CAD logo, marks each app's line
and keeps a live line under them; anywhere else the plain lines alone. That is all it does: it never changes ``cad
plugin update auto`` (the hosted install command a person ran turns it on) and keeps nothing of how it ended, which
is the command's to keep (``cad_server.cli.plugin``).

It ends with exit status 0 where it ended well, 1 where every app it found failed, ``computer.STOPPED`` where its
deadline passed before it was done (a run a server began: ``seconds``), and
``plugin_catch_up.BUSY`` where it ran nothing. Where ``CAD_PLUGIN_REPORT`` names a file (``REPORT_ENV``), what it did
is written there as it ends, whole (a file beside it, renamed into place): ``{"schema": "cad plugin install/1",
"apps": {<APPS key>: "installed" | "updated" | "removed" | "skipped" | "failed" | "not found"}}``; nothing is written
by a run that ran nothing. Writing it never fails the run, and nothing is said about it.

``Facts`` is everything a count of the run needs, made here and nowhere else: who began it, how it ended, each app
found with its status, the word for why it failed and its seconds, and what the terminal was shown. It is made as the
run begins and filled as it goes, each app as it is done, so what ends a run that never comes back
(``plugin_catch_up.HardStop``) can still say how far it got (``install``'s ``going``).
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from cad._internal.atomic_replace import replace_atomic
from cad_server._internal import plugin_catch_up

from . import computer, terminal
from .apps import NOT_FOUND, QUIET, Outcome, Report, install_apps
from .computer import STOPPED, Here
from .source import Source

# Run by cad, every rename the apps' rows make is cad's one rename, as every file cad writes goes through it.
computer.rename = replace_atomic

# Where the run says what it did, for the program that started it (the hosted install command).
REPORT_ENV = "CAD_PLUGIN_REPORT"
REPORT_SCHEMA = "cad plugin install/1"
# Who began the run: the hosted install command says so (``BY_ENV``: ``script``), this release's server names its run
# (``plugin_catch_up.SERVER_ENV``), and anything else is a person's own.
BY_ENV = "CAD_PLUGIN_BY"
PERSON, SCRIPT, SERVER = "person", "script", "server"
# How the run ended: well; every app it found failed (or its deadline stopped it); or another run held the lock.
OK, FAILED, BUSY = "ok", "failed", "busy"
# What the terminal was shown of the logo, beside ``terminal.PLAYED``, ``STILL`` and ``NONE``: drawing it failed.
LOGO_FAILED = "failed"


@dataclass
class AppFact:
    """One app found here, in one run: its ``APPS`` key, its status (``installed``, ``updated``, ``removed``,
    ``skipped``, ``failed``), with ``failed`` the word for why (``computer.REASONS``, else empty), and the seconds its
    row took."""

    app: str
    status: str
    reason: str
    seconds: float


@dataclass
class Facts:
    """What one run was (see the module). ``by``: ``PERSON``, ``SCRIPT`` or ``SERVER``. ``outcome``: ``OK``,
    ``FAILED`` or ``BUSY``, and ``code`` the exit status that says it. ``stopped``: its deadline passed before it was
    done. ``logo``: ``played``, ``still``, ``none`` or ``failed``. ``colour``: ``24bit``, ``256`` or ``none``.
    ``seconds``: the whole run's, a wait for the lock included. ``apps``: one ``AppFact`` per app found, in the
    table's order. ``statuses``: every app the run reached, by key, as the report's file gives them."""

    by: str
    outcome: str = OK
    code: int = 0
    stopped: bool = False
    logo: str = terminal.NONE
    colour: str = "none"
    seconds: float = 0.0
    apps: List[AppFact] = field(default_factory=list)
    statuses: Dict[str, str] = field(default_factory=dict)

    @property
    def found(self) -> int:
        return len(self.apps)

    @property
    def failed(self) -> int:
        return sum(1 for app in self.apps if app.status == "failed")


def began_by(environ: Dict[str, str]) -> str:
    """Who began a run in ``environ``: this release's server (its run is named), the hosted install command (it says
    so), else a person. The name an earlier release gives its server's run (``plugin_catch_up.ATTEMPT_ENV``) is no
    server's run of this command."""
    if environ.get(plugin_catch_up.SERVER_ENV):
        return SERVER
    return SCRIPT if environ.get(BY_ENV) == SCRIPT else PERSON


def install(*, prog: str, seconds: Optional[float] = None, going: Optional[Callable[[Facts], None]] = None) -> Facts:
    """One run (see the module), said as it goes on this process's output: what it was, ``Facts.code`` the exit status
    of the command that ran it. ``prog``: the command's name, for a line on stderr. ``seconds``: the run's deadline,
    counted from here. ``going``: given the run's ``Facts`` as it begins, the ones it fills as it goes and returns."""
    began = time.monotonic()
    here = Here()
    here.until = None if seconds is None else began + seconds
    facts = Facts(by=began_by(here.environ))
    if going is not None:
        going(facts)

    def waiting() -> None:
        print("Another run is setting up the plugin in the agent apps now: this one waits for it to end, then runs.",
              flush=True)

    with plugin_catch_up.run_lock(wait=facts.by != SERVER, waiting=waiting) as mine:
        if mine:
            _run(here, facts, prog, seconds)
        else:
            facts.outcome, facts.code = BUSY, plugin_catch_up.BUSY
            print(f"{prog}: another run is setting up the plugin in the agent apps now, so this one ran nothing",
                  file=sys.stderr, flush=True)
    facts.seconds = time.monotonic() - began
    return facts


def _run(here: Here, facts: Facts, prog: str, seconds: Optional[float]) -> None:
    """The run itself, the lock held: on a person's terminal, the logo first and every line printed over the live
    one."""
    screen = terminal.Screen(here, sys.stdout)
    facts.colour = screen.colour
    if not screen.live:
        _steps(here, facts, prog, seconds, None)
        return
    plain = sys.stdout
    try:
        facts.logo = terminal.play_logo(screen, plain)
    except Exception:  # noqa: BLE001 - the logo is only for show: a terminal it fails in still gets the install
        facts.logo = LOGO_FAILED
        plain.write("\x1b[0m\n")
    live = terminal.Live(screen, plain, str(here.home)).start()
    sys.stdout = live  # every line printed goes over the live one
    here.watch = live.watch
    try:
        _steps(here, facts, prog, seconds, live)
    finally:
        sys.stdout = plain
        live.close()


def _steps(here: Here, facts: Facts, prog: str, seconds: Optional[float], live: Optional[terminal.Live]) -> None:
    """The apps, then what to do next, said as they go; the report written as it ends."""
    print("Setting up the plugin in each agent app found here:", flush=True)
    source = Source()
    try:
        report = install_apps(here, source, live=live,
                              each=lambda key, outcome, took: facts.apps.extend(_found(key, outcome, took)))
    finally:
        source.close()
    try:
        print("", flush=True)
        facts.statuses = report.statuses()
        facts.apps = [fact for key, outcome in report.outcomes.items()  # as the run left them, the loose skills done
                      for fact in _found(key, outcome, report.seconds.get(key, 0.0))]
        if report.stopped:
            facts.stopped, facts.outcome, facts.code = True, FAILED, STOPPED
            print(f"{prog}: stopped after {seconds:g} seconds, all a run the cad server began may take; the apps it "
                  "had not reached were left as they were", file=sys.stderr, flush=True)
            return
        if report.all_failed:
            facts.outcome, facts.code = FAILED, 1
            print("No app got the plugin: see each app's line above, then run this again.", flush=True)
        if report.changed:
            print("Start a new session in each app to use it.", flush=True)
    finally:
        write_report(here, report)


def _found(key: str, outcome: Outcome, seconds: float) -> List[AppFact]:
    """One app's fact from its outcome, as a report of the run words it (``Report.statuses``); none for an app that
    is not here, or that has nothing to say."""
    if outcome is NOT_FOUND or outcome is QUIET:
        return []
    return [AppFact(key, "skipped" if outcome.status == "note" else outcome.status,
                    outcome.reason if outcome.status == "failed" else "", seconds)]


def write_report(here: Here, report: Report) -> None:
    """What the run did, written to the file ``REPORT_ENV`` names, where it names one (see the module). Never a
    failure of the run, and never said."""
    target = here.environ.get(REPORT_ENV)
    if not target:
        return
    temporary = None
    try:
        text = json.dumps({"schema": REPORT_SCHEMA, "apps": report.statuses()}, indent=1, sort_keys=True) + "\n"
        handle, temporary = tempfile.mkstemp(prefix=".plugin-report-", dir=os.path.dirname(os.path.abspath(target)))
        with os.fdopen(handle, "w", encoding="utf-8") as out:
            out.write(text)
        replace_atomic(temporary, target)
        temporary = None
    except Exception:  # noqa: BLE001 - the report is for the program that asked; the run is the person's
        pass
    finally:
        if temporary is not None:
            try:
                os.remove(temporary)
            except OSError:
                pass
