"""``cad setup``: text-to-cad set up, or brought up to date, in every agent app on this machine,
as this release; ``cad update`` (``cad_server.cli.update``) runs the newest release's; and ``cad
uninstall`` (``cad_server.cli.uninstall``, this module's uninstall path with a parser of its own) takes it
out again.

The install command runs it (``cad_server.updates.INSTALL``: ``curl -fsSL https://texttocad.dev/install.sh |
sh``; on Windows ``INSTALL_WINDOWS``, ``irm https://www.texttocad.dev/install.ps1 | iex``) after finding or
installing uv: the newest release's server (``texttocad-server``), run through ``uvx``. Running it again
is the update, and ``cad update`` and the update button take the same steps. Each app's plugin pins the
release its CAD app's transport runs (``texttocad-mcp==X``), which attaches to the device's engine, the
current installation's
(``cad_server._internal.installations``), whatever release it is. In order, each step said as it runs:

1. **Its release's folder.** A release from the index (or the wheel it was installed from) sets itself
   up from ``<state>/releases/<release>`` (``cad_server._internal.releases``): run from anywhere else --
   uvx's environment, as the install command runs it --, it makes that folder with uv, from uv's cache
   where it holds it, and runs the same command from there. A development install or a source tree
   sets itself up where it is.
2. **Plan.** Under a lock in the state folder, every agent app is read (``cad_server._internal.providers``),
   and the plan printed: per app, ``install``, ``update``, ``remove duplicate`` or ``leave``, with each
   command it runs and each file it edits; what serves the engine's port (``CAD_ENGINE_PORT``, else
   3245); and build123d, the CAD kernel. ``--dry-run`` stops there and writes nothing. Nothing is asked.
3. **An earlier release's engine.** An engine of an earlier release serving that port (one whose door
   is not the device's engine's) that nothing uses (no app server holds it, no page watches it, no
   request is underway) is stopped by that installation's own ``stop``, found by its record -- an 0.8
   one's among the records this release moved from the earlier state folder
   (``cad.engine.places.adopt_earlier``, before the plan). One still in use, or one no record names, is
   left running and said, with how to stop it.
4. **The cad command.** This installation registered and ``~/.local/bin/cad`` written, as
   ``cad doctor`` does it (``installations.setup``); on a device with no current installation it
   becomes the current one.
5. **build123d.** The environment every build and the engine's own kernel processes start from,
   ``texttocad[build123d]`` at this release (``cad_server._internal.base``), made now when it is not, so the
   first build after an install or an update waits on nothing: its line said while uv works, and a step
   that fails when it cannot be made. An installation that carries the kernel itself makes none.
6. **Apps.** The plugin folder, ``<state>/plugin``, is written from this release
   (``cad_server._internal.plugin``), and each app is pointed at it by its own command, the way it keeps
   a local plugin (``cad_server._internal.providers``): one reads the folder in place, one links it, one
   keeps a copy of it, which gets it again for this release; Claude Desktop's config gets CAD's server,
   this release's, written atomically with a ``.bak`` beside it; every second copy goes, an earlier
   release's from the repository on GitHub among them. The agents with no plugin that the Skills CLI
   knows get the skills, copied from the folder into their own skills folders by one ``npx skills add``
   (Node needed); an app with a plugin never does. A command that fails is said with its output, and
   the other apps go on; the exit status is then 1. A folder that cannot be written changes no app that
   would point at it.
7. **Receipt.** What was done, in ``<state>/install-receipt.json``, for ``cad uninstall`` to take
   back; and which agents got which skills (those the Skills CLI's ``--json`` says it installed) from
   which release (``skills``), since that CLI keeps no versions: the next run adds them again for an
   agent that got them from another release or has lost one of them.
8. **The switch.** The device's engine moves to this release (``cad_server._internal.switch.handover``):
   one running drains -- nothing in flight -- and this release's takes its place on the same port, with
   the same token, or the release before's comes back should it fail, and with it its plugin folder and
   the apps' copies of it (its own ``cad plugin --refresh``); with none running, ``current`` points at
   this release and the next client starts its engine.
9. **Report.** Each app's copy as it is now, the engine on the port, the telemetry notice
   (``--no-telemetry`` turns it off, as ``cad telemetry off`` does), and the apps to restart to
   load what this run installed or updated; ``already up to date`` when a run found nothing to do
   and changed nothing.

``--engine-update`` is the engine's own run of it, for its update button (``cad_server._internal.update``):
steps 2 to 7, from the release's folder, with no switch -- the engine drains and its helper switches --,
each stage a progress frame on stdout (``{"progress": ...}``) and its words on stderr.

``cad uninstall`` takes back what the receipt says was done, newest first -- each app's copy of the
plugin folder the way it was put in: the catalog removed with its plugin, the extension uninstalled,
Cursor's copy deleted, the skills removed by ``npx skills remove``; with no receipt, every copy of
text-to-cad found but a store's -- removes the ``cad`` command when it is text-to-cad's own, stops the
engine (``cad stop``), and removes the release folders and the plugin folder; with ``--purge`` it then
removes the state and cache folders. ``--only`` limits either to some apps (and then leaves the
command, the engine, the releases and the plugin folder alone). Neither asks: the plan is printed and
done, and ``--dry-run`` prints it alone.

Never done here: restarting an app, anything that needs sudo or a password, removing a ``cad``
command that is not text-to-cad's, editing a config that is not plain JSON, touching a store's copy.

Exit status: 0 done, or nothing to do; 1 a step failed; 2 bad arguments.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

DEFAULT_PROG = "cad setup"
SCHEMA = 1
RECEIPT = "install-receipt.json"
LOCK = "install.lock"
# Where loose copies of the skills are moved, rather than deleted.
ASIDE = "install-aside"
# How long an older installation's ``cad stop`` may take.
STOP_SECONDS = 60.0
# The server's install channel in Claude Desktop's config (``cad_server._internal.channel``).
DESKTOP_CHANNEL = "claude-desktop"


def build_parser(prog: str = DEFAULT_PROG, *, uninstall: bool = False, update: bool = False) -> argparse.ArgumentParser:
    """``cad setup``'s parser, or with ``uninstall`` ``cad uninstall``'s, or with ``update``
    ``cad update``'s (``cad_server.cli.update``): setup's options, and the switch helper's own."""
    from cad_server._internal.providers import APPS, SKILLS_AGENTS
    from cad_server.updates import INSTALL, INSTALL_WINDOWS

    if uninstall:
        parser = argparse.ArgumentParser(
            prog=prog,
            allow_abbrev=False,
            description="Take text-to-cad out of every agent app on this machine: what earlier `cad setup` runs "
                        "did (their receipt), newest first, or with no receipt every copy of text-to-cad found; the "
                        "cad command when it is text-to-cad's own; this installation's engine stopped.",
        )
    elif update:
        parser = argparse.ArgumentParser(
            prog=prog,
            allow_abbrev=False,
            description="Install the newest release of text-to-cad and set it up in every agent app on this machine, "
                        "as the update button does: its release folder, build123d, each app's own command, and "
                        "the engine switched to it. With the version feed out of reach, this release's setup.",
            epilog=f"The install command does the same: {INSTALL} (on Windows: {INSTALL_WINDOWS}).",
        )
    else:
        parser = argparse.ArgumentParser(
            prog=prog,
            allow_abbrev=False,
            description="Set up text-to-cad in every agent app on this machine as this release, or bring it up to "
                        "date there: its release folder, build123d, each app's own command, Claude Desktop's "
                        "config, second copies removed, and the engine switched to this release. `cad update` "
                        "runs the newest release's; `cad uninstall` takes it out.",
            epilog=f"The install command runs this with the newest release: {INSTALL} (on Windows: {INSTALL_WINDOWS}).",
        )
    parser.add_argument("--dry-run", action="store_true", help="print the plan and stop: nothing is changed")
    parser.add_argument("--only", action="append", metavar="APP[,APP...]",
                        help=f"only these apps: {', '.join(APPS)}; and the agents the skills go to through "
                             f"the Skills CLI: {', '.join(SKILLS_AGENTS)}")
    if uninstall:
        parser.add_argument("--purge", action="store_true", help="remove text-to-cad's state and cache folders too")
    else:
        parser.add_argument("--no-telemetry", action="store_true",
                            help="turn telemetry off, as `cad telemetry off` does")
        if update:
            # The switch's helper (``cad_server._internal.switch``), which the engine starts as it drains.
            parser.add_argument("--switch", metavar="RELEASE", default=None, help=argparse.SUPPRESS)
            parser.add_argument("--port", type=int, default=None, help=argparse.SUPPRESS)
            parser.add_argument("--previous", default=None, help=argparse.SUPPRESS)
        else:
            # The engine's own run, for its update button (``cad_server._internal.update``): no switch, progress on stdout.
            parser.add_argument("--engine-update", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--json", action="store_true",
                        help="print the plan and what was done as JSON on stdout (progress goes to stderr)")
    return parser


def main(argv: Sequence[str] | None = None, prog: str = DEFAULT_PROG, *, uninstall: bool = False) -> int:
    """``cad setup``, or with ``uninstall`` ``cad uninstall`` (``cad_server.cli.uninstall`` calls it so)."""
    from cad_server._internal.providers import APPS, SKILLS_AGENTS
    from cad_server.engine.daemon import default_port, environment_port

    parser = build_parser(prog, uninstall=uninstall)
    args = parser.parse_args(argv)
    only = []
    for given in args.only or ():
        only += [name.strip() for name in given.split(",") if name.strip()]
    unknown = sorted(set(only) - set(APPS) - set(SKILLS_AGENTS))
    if unknown:
        parser.error(f"--only: no app named {', '.join(unknown)} (the apps: {', '.join(APPS)}; "
                     f"the Skills CLI agents: {', '.join(SKILLS_AGENTS)})")
    try:
        named = environment_port()
    except ValueError as error:
        parser.error(str(error))
    port, source = (named, "CAD_ENGINE_PORT") if named is not None else (default_port(), "default")
    installer = Installer(args, only, port, source, list(argv if argv is not None else sys.argv[1:]))
    return installer.uninstall() if uninstall else installer.install()


# --- the engine on the port, as the engine says it of itself -----------------------------------------


def engine_on(port: int) -> dict[str, Any] | None:
    """The ``status`` of the engine in this engine folder whose HTTP server is on ``port``, asked
    read-only (``cad_server.engine.daemon._ask``, bounded), or None when no engine there serves it; with
    ``device`` true when it is the device's engine (``cad.engine.places.NAME``'s door), false for an
    earlier release's."""
    from cad_server.engine import daemon
    from cad.engine import places

    try:
        doors = sorted(places.engine_dir().glob("*.port" if places.WINDOWS else "*.door"))
    except OSError:
        return None
    for door in doors:
        status = daemon._ask(door, {"op": "status"})
        serving = (status or {}).get("serving")
        if isinstance(serving, dict) and serving.get("port") == port:
            return {**status, "device": door.stem == places.NAME}
    return None


def port_held(port: int) -> str | None:
    """Who listens on ``port`` when no engine of this engine folder does, in words, or None."""
    from cad_server.engine import daemon

    if not daemon._answers("127.0.0.1", port):
        return None
    return daemon._who(port)


def stop_installation(record: dict[str, Any]) -> tuple[bool, str]:
    """That installation's own ``stop``, run by its console script as the ``cad`` command
    runs it (told the version it is registered as when it cannot know it: ``installations.named``):
    whether it stopped, and what it said."""
    from cad_server._internal import installations

    environment = dict(os.environ)
    told = installations.named(record)
    if told:
        environment[installations.NAME_ENV] = told
    else:
        environment.pop(installations.NAME_ENV, None)
    try:
        done = subprocess.run([record["cadgen"], "stop"], env=environment, stdin=subprocess.DEVNULL,
                              capture_output=True, text=True, timeout=STOP_SECONDS)
    except (OSError, subprocess.SubprocessError) as error:
        return False, f"{type(error).__name__}: {error}"
    said = "\n".join(part.strip() for part in (done.stdout, done.stderr) if part and part.strip())
    return done.returncode == 0, said


class Installer:
    """One run of ``cad setup`` or ``cad uninstall``: its plan, what it did, and how it says so."""

    def __init__(self, args: argparse.Namespace, only: list[str], port: int, source: str,
                 argv: list[str] | None = None) -> None:
        from cad_server import __version__
        from cad_server._internal import plugin, providers

        self.args, self.only, self.port, self.source = args, only, port, source
        self.argv = list(argv or [])
        self.providers = providers
        self.machine = providers.Machine.here()
        self.release = __version__
        # The plugin folder every app is pointed at (``cad_server._internal.plugin``).
        self.folder = plugin.folder()
        # The engine's own run (``--engine-update``): progress frames on stdout, words on stderr.
        self.engine_update = bool(getattr(args, "engine_update", False))
        # Under --json the result is the one thing on stdout: what is said goes to stderr.
        self.out = sys.stderr if args.json or self.engine_update else sys.stdout
        self.actions: list[dict[str, Any]] = []
        self.stopped: dict[str, Any] | None = None
        # Whether Claude Code has the plugin after this run, so Cursor and Grok Build load it.
        self.fed = False

    # --- saying -----------------------------------------------------------------------------

    def say(self, line: str = "") -> None:
        self.out.write(line + "\n")
        self.out.flush()

    def stage(self, stage: str, detail: str = "") -> None:
        """The engine's own run (``--engine-update``): the update's stage it reached, a progress frame
        on stdout (``cad.engine.progress``, kind ``update``), which the engine passes to the page."""
        if not self.engine_update:
            return
        from cad_server._internal.update import STAGES
        from cad.engine.progress import event

        frame = event("update", stage, job=self.release, detail=detail, done=STAGES.index(stage), total=len(STAGES))
        sys.stdout.write(json.dumps({"progress": frame}) + "\n")
        sys.stdout.flush()

    # --- its release's folder -----------------------------------------------------------------

    def _home(self) -> Path | None:
        """The release folder this run sets itself up from (``releases.where``): None for an installation
        that sets itself up where it is -- a development install or a source tree (one that names its
        version, ``installations.NAME_ENV``, or imports the server from outside its environment)."""
        from cad_server._internal import installations, releases

        if os.environ.get(installations.NAME_ENV) or installations.editable() \
                or not installations.RELEASE.fullmatch(self.release):
            return None
        return releases.where(self.release)

    def _relocated(self) -> int | None:
        """Step 1: run from anywhere but its release's folder, that folder made (from uv's cache where it
        holds it) and this command run again from there, its exit status returned; None when this run is
        already there (or sets itself up where it is)."""
        from cad_server._internal import base, releases

        home = self._home()
        if home is None or os.path.normcase(os.path.realpath(home)) == os.path.normcase(os.path.realpath(sys.prefix)):
            return None
        try:
            made = releases.make(self.release, source=base.server_source(),
                                 told=lambda line: self.say(f"release  {line}"))
        except base.Refused as refused:
            self.say(f"release  {refused}")
            from cad_server.updates import command

            self.say(f"Once that is fixed, run the install command again: {command()}")
            return 1
        run = [made["cadgen"], "setup", *self.argv]
        self.say(f"release  text-to-cad {self.release} in {self.providers.shown(str(home), self.machine)}")
        if os.name == "nt":
            return subprocess.call(run)
        sys.stdout.flush()
        sys.stderr.flush()
        os.execv(run[0], run)
        return 1  # not reached

    def _plan_lines(self, title: str, apps: dict[str, Any], steps: list[Any], extra: list[dict[str, Any]]) -> None:
        """The plan, a line per step: the app, the action, what it acts on; under it each command it
        runs and the file it edits."""
        shown = self.providers.shown
        self.say(title)
        rows = [(step.label, step.action, step.subject, step) for step in steps]
        rows += [(row["label"], row["action"], row["subject"], None) for row in extra]
        if not rows:
            self.say("  nothing: no agent app was found here")
        width = max((len(label) for label, _a, _s, _st in rows), default=0) + 2
        action_width = max((len(action) for _l, action, _s, _st in rows), default=0) + 2
        indent = " " * (2 + width + action_width)
        for label, action, subject, step in rows:
            self.say(f"  {label.ljust(width)}{action.ljust(action_width)}{subject}")
            if step is None:
                continue
            for argv in step.commands:
                self.say(f"{indent}$ {self.providers.command_text(argv, self.machine)}")
            if step.note:
                self.say(f"{indent}({step.note})")
            edit = step.edit or {}
            if edit.get("op") == "servers":
                self.say(f"{indent}edits {shown(edit['path'], self.machine)}, keeping a .bak beside it")
            elif edit.get("op") == "move":
                self.say(f"{indent}moved to {shown(self._aside(), self.machine)}, not deleted")
            elif edit.get("op") == "remove" and "paths" in edit:
                self.say(f"{indent}removes the {len(edit['paths'])} skill folders of ours"
                         + (" that the command leaves" if step.commands or step.note else ""))
            elif edit.get("op") == "remove":
                self.say(f"{indent}removes {shown(edit['path'], self.machine)}")
            elif edit.get("op") == "copy":
                self.say(f"{indent}copies {shown(edit['from'], self.machine)} to {shown(edit['path'], self.machine)}, "
                         "real files")
            elif edit.get("op") == "restore":
                self.say(f"{indent}restores its .bak if nothing else changed since, else removes only that entry")
        absent = [app.label for app in apps.values() if not app.present and (not self.only or app.id in self.only)]
        if absent:
            self.say(f"  not found here: {', '.join(absent)}")
        for app in apps.values():
            for note in app.notes if app.id != "claude-desktop" else ():
                self.say(f"  note: {app.label}: {note}")

    def _result(self, steps: list[Any], extra: list[dict[str, Any]], verified: dict[str, Any] | None,
                restart: list[str], code: int) -> int:
        if self.args.json:
            plan = [step.data() for step in steps] + [
                {"app": row["app"], "label": row["label"], "action": row["action"], "subject": row["subject"],
                 "commands": [], "edit": None} for row in extra]
            document = {"schema": SCHEMA, "plan": plan, "actions": self.actions, "stopped": self.stopped,
                        "verified": verified, "restart": restart}
            sys.stdout.write(json.dumps(document, ensure_ascii=False, separators=(",", ":")) + "\n")
            sys.stdout.flush()
        return code

    # --- where things are ---------------------------------------------------------------------

    def _state(self) -> Path:
        from cad.engine.places import state_dir

        return Path(state_dir())

    def _aside(self) -> Path:
        return self._state() / ASIDE / self.providers.stamp().replace(":", "")

    def _desktop_entry(self) -> dict[str, Any] | None:
        """CAD's server for Claude Desktop's chat: the plugins' exact command, uvx by its absolute path."""
        from cad_server._internal.launch import LAUNCHER, SHIM, SHIM_COMMAND

        uvx = self.providers.uvx(self.machine)
        if uvx is None:
            return None
        return {"command": uvx, "args": [*LAUNCHER[1:], f"{SHIM}=={self.release}", SHIM_COMMAND],
                "env": {"CAD_INSTALL_CHANNEL": DESKTOP_CHANNEL}}

    # --- the receipt ----------------------------------------------------------------------------

    def _folder(self):
        from cad_server.engine.registry import Folder

        return Folder(self._state())

    def _receipt(self) -> dict[str, Any] | None:
        data = self._folder().read(RECEIPT)
        try:
            receipt = json.loads(data) if data is not None else None
        except ValueError:
            self.say(f"note: {self._state() / RECEIPT} cannot be read; it is not used")
            return None
        if not isinstance(receipt, dict) or receipt.get("schema") != SCHEMA:
            return None
        return receipt

    def _keep(self, receipt: dict[str, Any]) -> None:
        text = json.dumps(receipt, ensure_ascii=False, separators=(",", ":")) + "\n"
        self._folder().write(RECEIPT, text.encode("utf-8"))

    # --- the engine ---------------------------------------------------------------------------

    def _record_of(self, status: dict[str, Any]) -> dict[str, Any] | None:
        """The installation record naming the environment an engine runs in (its ``prefix``), when
        that installation is still there (``installations.alive``)."""
        from cad_server._internal import installations

        prefix = status.get("prefix")
        if not isinstance(prefix, str):
            return None
        try:
            found = installations.records()
        except OSError:
            return None
        mine = [record for record in found if installations._same_place(record["prefix"], prefix)
                and installations.alive(record)]
        named = status.get("installation") or status.get("version")
        return next((record for record in mine if record["version"] == named), None) or (mine[0] if mine else None)

    def _engine(self) -> dict[str, Any]:
        """What serves the engine's port, asked read-only, and what this run does about it: the device's
        engine is switched to this release (``_switch``), and an earlier release's that nothing uses is
        stopped by its own ``stop``."""
        from cad_server.engine import daemon

        port = self.port
        row: dict[str, Any] = {"app": "engine", "label": "engine", "action": "leave"}
        if not port:
            return {**row, "subject": "CAD_ENGINE_PORT=0: the engine takes any free port"}
        status = engine_on(port)
        if status is None:
            held = port_held(port)
            if held is None:
                return {**row, "subject": f"port {port}: no engine running; the first CAD view or build starts one"}
            then = ("the engine serves on the next free port, and says so" if self.source == "default"
                    else "stop it, or set another CAD_ENGINE_PORT")
            return {**row, "subject": f"port {port} is held by {held}: {then}"}
        name = status.get("installation") or status.get("version") or "?"
        who = f"text-to-cad {name}'s engine (pid {status.get('pid')}) on port {port}"
        prefix = status.get("prefix")
        if isinstance(prefix, str) and os.path.normcase(os.path.realpath(prefix)) == \
                os.path.normcase(os.path.realpath(sys.prefix)):
            return {**row, "subject": f"{who}: this installation's"}
        if status.get("device"):
            return {**row, "action": "switch", "subject": f"{who}: drains, then text-to-cad {self.release}'s takes its place"}
        record = self._record_of(status)
        # Its own command's stop, the one that reaches it whatever its release: the `cad` command runs the
        # current installation, and an earlier release's engine (0.8's) is no door the current one stops.
        stop = f"`{record['cadgen']} stop`" if record else f"the stop command of that installation ({prefix})"
        uses = daemon._uses(status)
        if uses is None:
            return {**row, "subject": f"{who}: it cannot be asked whether it is in use; {stop} stops it"}
        if uses:
            return {**row, "subject": f"{who}: in use by {' and '.join(uses)}, left running; once that is "
                                      f"closed, {stop} stops it"}
        if record is None:
            return {**row, "subject": f"{who}: idle, and no installation record names it; {stop} stops it"}
        return {**row, "action": "stop", "release": name, "pid": status.get("pid"), "record": record,
                "subject": f"{who}, idle: stopped by its own `cad stop`"}

    def _kernel(self) -> dict[str, Any] | None:
        """The CAD kernel environment, the base every build and the engine's own kernel processes start
        from (``cad_server._internal.base``): made by this run when it is not, so the first build
        after an install waits on nothing. None for an installation that carries the kernel itself."""
        from cad_server._internal import base

        row: dict[str, Any] = {"app": "build123d", "label": "build123d", "action": "leave"}
        try:
            installation = base.Installation.here()
            if installation.kernel:
                return None
            found = base.ensure(installation, make=False)
            folder = base.where(installation)
        except (base.Refused, OSError) as error:
            return {**row, "subject": f"unknown ({error})"}
        shown = self.providers.shown(str(folder), self.machine)
        if found is not None:
            return {**row, "subject": f"texttocad[{base.EXTRA}] {installation.release} in {shown}"}
        return {**row, "action": "make", "subject": f"texttocad[{base.EXTRA}] {installation.release} in {shown}, once"}

    def _make_kernel(self) -> bool:
        """The CAD kernel environment made (``_kernel``'s ``make``), each line uv's work says as it goes;
        False, said in its line, when it cannot be."""
        from cad_server._internal import base

        try:
            base.ensure(told=lambda line: self.say(f"build123d {line}"))
        except base.Refused as refused:
            self.say(f"build123d {refused}")
            return False
        return True

    def _switch(self) -> tuple[bool, dict[str, Any] | None]:
        """Step 8: the device's engine moved to this release (``switch.handover``), said in its lines:
        ``(failed, what the switch did or None when there was nothing to do)``."""
        from cad_server._internal import installations, switch

        version = installations.own_version()
        if not version:
            return False, None
        try:
            done = switch.handover(version, told=lambda line: self.say(f"engine   {line}"))
        except (OSError, ValueError, ConnectionError) as error:
            self.say(f"engine   the switch to text-to-cad {version} could not run: {error}")
            return True, None
        if done is None:
            return False, None
        if done.get("ok"):
            gap = f" ({done['gapMs']} ms without an engine)" if done.get("gapMs") is not None else ""
            self.say(f"engine   text-to-cad {version} is the current installation{gap}")
            return False, done
        self.say(f"engine   the switch to text-to-cad {version} failed: {done.get('error')}"
                 + ("; the release before runs again" if done.get("restored") else ""))
        return True, done

    def _stop_older(self, engine: dict[str, Any]) -> None:
        """An earlier release's idle engine on the port stopped by its installation's own ``stop``."""
        ok, said = stop_installation(engine["record"])
        if ok:
            self.stopped = {"release": engine["release"], "pid": engine["pid"], "port": self.port,
                            "at": self.providers.stamp()}
            self.say(f"engine   stopped text-to-cad {engine['release']}'s engine (pid {engine['pid']})")
            return
        self.say(f"engine   text-to-cad {engine['release']}'s `cad stop` failed; it is left running"
                 + (f": {said.splitlines()[-1]}" if said else ""))

    # --- the cad command -------------------------------------------------------------------

    def _register(self) -> dict[str, Any]:
        """This installation registered and the proxy written: what ``cad doctor`` and the CAD app's
        server do (``installations.setup``)."""
        from cad_server._internal import installations
        from cad_server.cli.doctor import _command_path_hint

        version = installations.own_version()
        if version:
            (record, recorded, record_error), (proxy, before, proxy_error) = installations.setup(version)
        else:
            record, recorded, record_error = None, None, None
            proxy, before, proxy_error = installations.proxy_path(), installations.proxy_status(), None
            self.say("server   not registered: a source tree registers only as a version it is named "
                     f"({installations.NAME_ENV})")
        if record_error:
            self.say(f"server   {record} cannot be written here ({record_error}): run this outside any sandbox")
        elif recorded == installations.REGISTERED:
            self.say(f"server   registered {version} ({self.providers.shown(record, self.machine)})")
        wrote = bool(version) and not proxy_error and before in (installations.MISSING, installations.STALE)
        where = self.providers.shown(proxy, self.machine)
        if proxy_error:
            self.say(f"command  {where} cannot be written here ({proxy_error})")
        elif wrote:
            self.say(f"command  {where} written{_command_path_hint(proxy)}")
        elif before == installations.FOREIGN:
            self.say(f"command  {where} is not text-to-cad's, left alone: remove it to run cad by it")
        return {"registered": record if recorded and not record_error else None,
                "record_written": recorded == installations.REGISTERED,
                "launcher": {"path": proxy, "status": before, "written": wrote, "error": proxy_error}}

    # --- the report ---------------------------------------------------------------------------

    def _verify(self) -> dict[str, Any]:
        """Each selected app's copy as the apps say it now, read again, and the engine on the port."""
        providers = self.providers
        try:
            apps = providers.detect(self.machine, folder=self.folder)
        except Exception as error:  # noqa: BLE001 - a report line, never a failure of the setup
            self.say(f"verify   unknown ({type(error).__name__}: {error})")
            return {"apps": {}, "engine": None}
        verdicts: dict[str, Any] = {}
        for name, app in apps.items():
            if not app.present or (self.only and name not in self.only):
                continue
            ours, stores = app.ours(), app.stores()
            if ours is not None:
                found = {"verdict": "ok", "release": ours.version}
                said = f"text-to-cad {ours.version or '?'}" if name == "claude-desktop" else ours.words(self.machine)
                origin = ours.origin(self.machine)
                said += f", {origin}" if origin else ""
            elif stores:
                found = {"verdict": "store"}
                said = f"{stores[0].words(self.machine)}, which its store updates"
            elif name in providers.FED_BY and self.fed:
                found = {"verdict": "served"}
                said = f"served by the {providers.LABELS['claude']} plugin"
            else:
                found = {"verdict": "none"}
                said = "no copy of text-to-cad"
            verdicts[name] = found
            self.say(f"verify   {app.label}: {said}")
        engine: dict[str, Any] | None = None
        if self.port:
            try:
                status = engine_on(self.port)
            except Exception as error:  # noqa: BLE001 - a report line, never a failure of the setup
                self.say(f"verify   engine port {self.port}: unknown ({type(error).__name__}: {error})")
            else:
                name = (status or {}).get("installation") or (status or {}).get("version")
                engine = {"port": self.port, "release": name}
                self.say(f"verify   engine port {self.port}: " + (f"text-to-cad {name} running" if status is not None
                                                                   else "not running; the next CAD session starts one"))
        return {"apps": verdicts, "engine": engine}

    def _telemetry(self) -> str:
        """The telemetry line: the notice the first time, else what is sent and why; ``--no-telemetry``
        turns it off first, as ``cad telemetry off`` does."""
        from cad_server import analytics
        from cad_server.cli.telemetry import describe

        if self.args.no_telemetry:
            chosen = analytics.choose(False, by="cli", forget=analytics.request_deletion)
            said = describe() if chosen.get("saved") else "unchanged: the choice could not be saved in the state folder"
        elif analytics.notify(self.out):
            return describe()
        else:
            said = describe()
        self.say(f"telemetry {said}" + ("; turn it off with `cad telemetry off`" if said.startswith("on") else ""))
        return said

    def _restart(self, apps: dict[str, Any], changed: set[str]) -> list[str]:
        """What to restart to load what this run did (``changed``: the apps it installed or updated
        the plugin in, a config it edited, and the agents that got the skills)."""
        providers = self.providers
        names = [name for name in providers.APPS if name in changed]
        if "claude" in changed:  # Cursor and Grok Build load the Claude Code plugin
            names += [name for name in providers.FED_BY if self.fed and apps[name].present and name not in names]
        lines = [providers.RESTART[name] for name in names]
        agents = [providers.label(name) for name in providers.SKILLS_AGENTS if name in changed]
        if agents:
            lines.append(f"{', '.join(agents)}: start a new session for the skills")
        if lines:
            self.say("Restart to load it:")
            for line in lines:
                self.say(f"  {line}")
        return lines

    # --- install --------------------------------------------------------------------------------

    @staticmethod
    def _public(engine: dict[str, Any]) -> dict[str, Any]:
        """The engine's plan row as the plan shows it: without the installation record it acts by."""
        return {key: value for key, value in engine.items() if key != "record"}

    # --- the plugin folder ----------------------------------------------------------------------

    def _plugin_row(self) -> dict[str, Any]:
        """The plugin folder's plan row: written from this release, or already its (``plugin.pending``)."""
        from cad_server._internal import plugin

        row: dict[str, Any] = {"app": "plugin", "label": "plugin folder", "action": "leave"}
        where = self.providers.shown(str(self.folder), self.machine)
        try:
            found = plugin.pending(self.folder)
        except (plugin.Missing, OSError, ValueError) as error:
            return {**row, "subject": f"{where} cannot be written: {error}"}
        if found["created"]:
            return {**row, "action": "write", "subject": f"{where}: text-to-cad {self.release}, which the apps read"}
        count = len(found["changed"]) + len(found["removed"])
        if count:
            return {**row, "action": "write",
                    "subject": f"{where}: text-to-cad {self.release} ({count} file{'s' if count != 1 else ''})"}
        return {**row, "subject": f"{where}: text-to-cad {self.release}, up to date"}

    def _write_plugin(self) -> dict[str, Any] | None:
        """The plugin folder written from this release, before the apps are pointed at it; said when that
        changed it. None, said, when it cannot be."""
        from cad_server._internal import plugin

        shown = self.providers.shown
        try:
            done = plugin.write(self.folder)
        except (plugin.Missing, OSError, ValueError) as error:
            self.say(f"plugin   {shown(str(self.folder), self.machine)} could not be written: {error}")
            return None
        if done["created"] or done["changed"] or done["removed"]:
            plugin.say_written(done, lambda line: self.say(f"plugin   {line}"), lambda path: shown(path, self.machine))
            self.actions.append({"app": "plugin", "action": "write", "kind": "plugin", "path": done["path"],
                                 "version": done["version"], "ok": True, "at": self.providers.stamp()})
        return done

    def _needs_folder(self, step: Any) -> bool:
        """Whether a step points an app at the plugin folder, or copies from it (its app's removals with it:
        an app is never left with its duplicate gone and nothing in its place)."""
        return step.app in self.providers.POINTED or step.app in self.providers.SKILLS_AGENTS

    def _record_skills(self, receipt: dict[str, Any], step: Any, steps: list[Any], records: list[dict[str, Any]],
                       changed: set[str]) -> None:
        """The Skills CLI keeps no versions: the receipt says which release each agent ``step`` added the
        skills for now has, and which skills (those the CLI said it installed)."""
        providers = self.providers
        actions = {other.app: other.action for other in steps}
        changed.update(agent for agent in step.agents if actions.get(agent) in ("install", "update"))
        said = next((record["skills"] for record in records if record.get("skills") is not None), None)
        got = dict(receipt.get("skills") or {})
        for agent in step.agents:
            folder = providers.skills_folder(agent, self.machine)
            # The skills it said it installed; when it said nothing readable, what is there now.
            names = said if said is not None else [path.name for path in providers.ours_in(folder)]
            got[agent] = {"release": self.release, "folder": str(folder), "skills": names, "at": providers.stamp()}
        receipt["skills"] = got

    def refresh(self, told: Any) -> tuple[bool, list[dict[str, Any]]]:
        """After the plugin folder was written again (``cad plugin --refresh``, which a switch runs): the
        copies the apps keep of it brought to it (``providers.refresh_plan``), under the installer's lock,
        the receipt kept. ``(ok, the steps run)``."""
        from cad_server._internal.file_lock import exclusive

        providers = self.providers
        state = self._state()
        state.mkdir(parents=True, exist_ok=True)
        failed, changed = False, set()
        with exclusive(state / LOCK, waiting=lambda: told("waiting for another cad setup or uninstall to finish")):
            receipt = self._receipt() or {"schema": SCHEMA, "created": providers.stamp(), "actions": [], "stopped": []}
            apps = providers.detect(self.machine, folder=self.folder)
            steps = providers.refresh_plan(apps, release=self.release, folder=self.folder, machine=self.machine,
                                           skills=receipt.get("skills"))
            for step in steps:
                told(f"{step.label}: {step.action} {step.subject}")
                ok, records = providers.apply(step, self.machine, say=lambda line: told(f"  {line}"))
                self.actions += records
                failed = failed or not ok
                if ok and step.agents:
                    self._record_skills(receipt, step, steps, records, changed)
            if self.actions:
                receipt.update({"release": self.release, "updated": providers.stamp()})
                receipt["actions"] = list(receipt.get("actions") or []) + self.actions
                self._keep(receipt)
        if steps:
            told("Restart to load it: " + "; ".join(providers.RESTART[step.app] for step in steps
                                                     if step.app in providers.RESTART))
        return not failed, [step.data() for step in steps]

    def install(self) -> int:
        providers = self.providers
        where = f"engine port {self.port}" if self.port else "engine on any free port"
        title = f"text-to-cad {self.release} for this machine ({where}):"
        if not self.args.dry_run and not self.engine_update:
            relocated = self._relocated()
            if relocated is not None:
                return relocated
        if self.args.dry_run:
            apps = providers.detect(self.machine, folder=self.folder)
            steps = providers.plan(apps, release=self.release, folder=self.folder, desktop_entry=self._desktop_entry(),
                                   only=self.only, machine=self.machine, skills=(self._receipt() or {}).get("skills"))
            kernel = self._kernel()
            home = self._home()
            release = ([{"app": "release", "label": "release", "action": "make",
                         "subject": f"text-to-cad {self.release} in {providers.shown(str(home), self.machine)}, once"}]
                       if home is not None and not os.path.isdir(home) else [])
            extra = [*release, self._plugin_row(), self._public(self._engine()), *([kernel] if kernel else [])]
            self._plan_lines(title, apps, steps, extra)
            self.say("Dry run: nothing was changed.")
            return self._result(steps, extra, None, [], 0)
        from cad.engine.places import adopt_earlier
        from cad_server._internal.file_lock import exclusive

        # What this release keeps of an earlier release's state folder, moved into its own first: the
        # person's settings, the installations' records (an earlier engine on the port is stopped by its
        # own, found by its record), the engines' with the page token, the documents' and the receipt.
        adopt_earlier()
        state = self._state()
        state.mkdir(parents=True, exist_ok=True)
        with exclusive(state / LOCK, waiting=lambda: self.say("waiting for another cad setup or uninstall to finish")):
            receipt = self._receipt() or {"schema": SCHEMA, "created": providers.stamp(), "actions": [], "stopped": []}
            apps = providers.detect(self.machine, folder=self.folder)
            steps = providers.plan(apps, release=self.release, folder=self.folder, desktop_entry=self._desktop_entry(),
                                   only=self.only, machine=self.machine, skills=receipt.get("skills"))
            self.fed = providers.feeds(apps, self.only or providers.APPS)
            engine = self._engine() if not self.engine_update else {"app": "engine", "label": "engine",
                                                                     "action": "leave", "subject": "this engine's own update"}
            kernel = self._kernel()
            extra = [self._plugin_row(), self._public(engine), *([kernel] if kernel else [])]
            self._plan_lines(title, apps, steps, extra)
            work = [step for step in steps if step.changes]
            if engine["action"] == "stop":
                self._stop_older(engine)
            registered = self._register()
            made = kernel is not None and kernel["action"] == "make"
            # The kernel that cannot be made fails the run and keeps the engine where it is; an app whose
            # command fails fails the run too, and the rest goes on: the switch among it.
            kernel_failed = False
            if made:
                self.stage("build123d", f"texttocad[build123d] {self.release}")
                kernel_failed = not self._make_kernel()
            failed = kernel_failed
            self.stage("apps")
            # The folder the apps are pointed at, this release's, before they are: a folder that cannot be
            # written changes no app that would point at it.
            if self._write_plugin() is None:
                failed = True
                for step in [step for step in work if self._needs_folder(step)]:
                    self.say(f"{step.label}: {step.action} {step.subject}: not done, with no plugin folder")
                    work.remove(step)
            # A config's first .bak is the one an uninstall restores: a later run keeps it.
            backed_up = {action["path"] for action in receipt.get("actions") or []
                         if action.get("kind") == "edit" and action.get("ok")
                         and (action.get("created") or (action.get("backup") and Path(action["backup"]).is_file()))}
            changed: set[str] = set()
            aside = self._aside()
            for step in work:
                self.say(f"{step.label}: {step.action} {step.subject}")
                ok, records = providers.apply(step, self.machine, say=lambda line: self.say(f"  {line}"),
                                              aside=aside, backed_up=backed_up)
                self.actions += records
                failed = failed or not ok
                # A plugin installed or updated loads in the app's next session; a config, as the app opens.
                if ok and records and step.action in ("install", "update") and step.app in providers.APPS:
                    changed.add(step.app)
                if ok and step.agents:  # the Skills CLI keeps no versions: the receipt says which release
                    self._record_skills(receipt, step, steps, records, changed)
            launcher = registered["launcher"]
            if self.actions or self.stopped or registered["record_written"] or launcher["written"]:
                receipt.update({"release": self.release, "updated": providers.stamp()})
                receipt["actions"] = list(receipt.get("actions") or []) + self.actions
                if self.stopped:
                    receipt["stopped"] = list(receipt.get("stopped") or []) + [self.stopped]
                if launcher["written"]:
                    receipt["launcher"] = {"path": launcher["path"], "written": True, "at": providers.stamp()}
                self._keep(receipt)
            switched = None
            if not self.engine_update and not kernel_failed:
                switch_failed, switched = self._switch()
                failed = failed or switch_failed
            if not (self.actions or self.stopped or registered["record_written"] or launcher["written"] or made
                    or switched):
                self.say(f"text-to-cad {self.release} is already up to date here.")
        if switched is not None and switched.get("restored"):
            # The release before runs again: its plugin folder, and the apps' copies of it, come back with
            # it -- its own `cad plugin --refresh`, once this run's lock is let go.
            from cad_server._internal import switch

            switch.follow(told=lambda line: self.say(f"plugin   {line}"))
        if self.engine_update:
            return 1 if kernel_failed else 0
        verified = self._verify()
        self._telemetry_into(verified)
        restart = self._restart(apps, changed)
        if failed:
            from cad_server.updates import command

            self.say(f"Some steps failed (said above); the rest were done. Once they are fixed, run the install "
                     f"command again: {command()}")
        return self._result(steps, extra, verified, restart, 1 if failed else 0)

    def _telemetry_into(self, verified: dict[str, Any]) -> None:
        try:
            verified["telemetry"] = self._telemetry()
        except Exception as error:  # noqa: BLE001 - the notice never fails the setup
            self.say(f"telemetry unknown ({type(error).__name__}: {error})")

    # --- uninstall ------------------------------------------------------------------------------

    def uninstall(self) -> int:
        providers = self.providers
        from cad_server._internal import installations
        from cad.engine.places import cache_dir

        receipt = self._receipt()
        apps = providers.detect(self.machine, folder=self.folder)
        steps = providers.uninstall_plan(apps, receipt, self.only or None, self.machine, folder=self.folder)
        extra: list[dict[str, Any]] = []
        proxy = installations.proxy_path()
        status = installations.proxy_status(proxy)
        # The cad command goes with a whole uninstall when it is text-to-cad's: its first lines carry the
        # proxy's mark. A file of that name that is not (``uv tool install``'s link) stays.
        ours = status in (installations.OK, installations.STALE, installations.NEWER)
        whole = not self.only
        launcher = whole and ours
        if launcher:
            extra.append({"app": "command", "label": "command", "action": "remove",
                          "subject": f"{providers.shown(proxy, self.machine)} (text-to-cad's)"})
        elif whole and status == installations.FOREIGN:
            extra.append({"app": "command", "label": "command", "action": "leave",
                          "subject": f"{providers.shown(proxy, self.machine)}: not text-to-cad's"})
        if whole:
            extra.append({"app": "engine", "label": "engine", "action": "stop",
                          "subject": "the engine (`cad stop`)"})
            from cad_server._internal import releases

            if releases.listing():
                extra.append({"app": "releases", "label": "releases", "action": "remove",
                              "subject": providers.shown(str(releases.root()), self.machine)})
            if os.path.lexists(self.folder):
                extra.append({"app": "plugin", "label": "plugin folder", "action": "remove",
                              "subject": providers.shown(str(self.folder), self.machine)})
        state, cache = self._state(), Path(cache_dir())
        if self.args.purge:
            extra.append({"app": "folders", "label": "folders", "action": "remove",
                          "subject": f"{providers.shown(state, self.machine)} and {providers.shown(cache, self.machine)}"})
        where = "what earlier runs did, newest first" if receipt else "no receipt: every copy of text-to-cad found"
        self._plan_lines(f"text-to-cad: cad uninstall takes back {where}:", apps, steps, extra)
        if self.args.dry_run:
            self.say("Dry run: nothing was changed.")
            return self._result(steps, extra, None, [], 0)
        failed, changed = False, set()
        from cad_server._internal.file_lock import exclusive

        state.mkdir(parents=True, exist_ok=True)
        with exclusive(state / LOCK, waiting=lambda: self.say("waiting for another cad setup or uninstall to finish")):
            for step in steps:
                if not step.changes:
                    continue
                self.say(f"{step.label}: {step.action} {step.subject}")
                ok, records = providers.apply(step, self.machine, say=lambda line: self.say(f"  {line}"),
                                              aside=self._aside())
                self.actions += records
                failed = failed or not ok
                if ok:
                    changed.add(step.app)
                    changed.update(step.agents)
            if launcher:
                try:
                    os.unlink(proxy)
                    self.say(f"command  removed {providers.shown(proxy, self.machine)}")
                    self.actions.append({"app": "command", "action": "remove", "kind": "remove", "path": proxy,
                                         "ok": True, "at": providers.stamp()})
                except OSError as error:
                    failed = True
                    self.say(f"command  {providers.shown(proxy, self.machine)} could not be removed: {error}")
            if whole:
                failed = self._stop() or failed
                failed = self._remove_releases() or failed
                failed = self._remove_plugin() or failed
            if receipt is not None:
                if whole:
                    self._folder().remove(RECEIPT)
                else:
                    receipt["actions"] = [action for action in receipt.get("actions") or []
                                          if action.get("app") not in self.only]
                    receipt["skills"] = {agent: got for agent, got in (receipt.get("skills") or {}).items()
                                         if agent not in self.only}
                    receipt["updated"] = providers.stamp()
                    self._keep(receipt)
        if self.args.purge:
            self._purge(state, cache)
        restart = self._restart(apps, changed)
        return self._result(steps, extra, None, restart, 1 if failed else 0)

    def _remove_plugin(self) -> bool:
        """The plugin folder removed, after every app's copy of it: True when it could not be removed whole."""
        from cad_server._internal import plugin

        shown = self.providers.shown(str(self.folder), self.machine)
        if not plugin.remove(self.folder):
            return False
        if os.path.lexists(self.folder):
            self.say(f"plugin   {shown} could not be removed whole")
            return True
        self.say(f"plugin   removed {shown}")
        self.actions.append({"app": "plugin", "action": "remove", "kind": "remove", "path": str(self.folder),
                             "ok": True, "at": self.providers.stamp()})
        return False

    def _remove_releases(self) -> bool:
        """The release folders removed, with their installations' records and ``current`` when it named
        one of them: what the device runs from goes with an uninstall. True when one could not be removed
        whole (on Windows, the folder this command runs from)."""
        import shutil

        from cad_server._internal import installations, releases

        root = releases.root()
        if not root.exists():
            return False
        for record in installations.records():
            if installations._same_place(os.path.dirname(record["prefix"]), root):
                installations.forget(record["version"])
                if installations.current_version() == record["version"]:
                    installations.state().remove(installations.CURRENT)
        shutil.rmtree(root, ignore_errors=True)
        shown = self.providers.shown(str(root), self.machine)
        if root.exists():
            self.say(f"releases {shown} could not be removed whole")
            return True
        self.say(f"releases removed {shown}")
        self.actions.append({"app": "releases", "action": "remove", "kind": "remove", "path": str(root), "ok": True,
                             "at": self.providers.stamp()})
        return False

    def _stop(self) -> bool:
        """``cad stop`` for the engine, said in this run's words; True when it failed."""
        from cad_server.cli import stop

        with contextlib.redirect_stdout(self.out):
            try:
                code = stop.main([])
            except SystemExit as exit_:
                code = exit_.code if isinstance(exit_.code, int) else 1
        self.actions.append({"app": "engine", "action": "stop", "kind": "command", "command": ["cad", "stop"],
                             "code": code, "ok": code == 0, "at": self.providers.stamp()})
        return code != 0

    def _purge(self, state: Path, cache: Path) -> None:
        import shutil

        shown = self.providers.shown
        for folder in (state, cache):
            shutil.rmtree(folder, ignore_errors=True)
            self.say(f"folders  removed {shown(folder, self.machine)}" if not folder.exists()
                     else f"folders  {shown(folder, self.machine)} could not be removed whole")


def refresh_copies(told: Any) -> tuple[bool, list[dict[str, Any]]]:
    """The copies the apps keep of the plugin folder brought to it, after ``cad plugin --refresh`` wrote it
    again (``Installer.refresh``): ``(ok, the steps run)``, each line said to ``told``."""
    args = argparse.Namespace(dry_run=False, json=False, only=None, no_telemetry=False)
    return Installer(args, [], 0, "default").refresh(told)


if __name__ == "__main__":
    raise SystemExit(main())
