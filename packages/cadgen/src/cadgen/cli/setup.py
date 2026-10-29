"""``cadgen setup`` (and ``cadgen update``, the same command): text-to-cad set up, or brought up to
date, in every agent app on this machine; and ``cadgen uninstall`` (``cadgen.cli.uninstall``, this
module's uninstall path with a parser of its own), which takes it out again.

The install command runs it (``cadgen.updates.INSTALL``: ``curl -fsSL https://texttocad.dev/install.sh |
sh``; on Windows ``INSTALL_WINDOWS``, ``irm https://www.texttocad.dev/install.ps1 | iex``) after finding or
installing uv: the newest release's cadgen, run through ``uvx``. Running it again is the update, and
from then on the engine runs it itself, within the hour of each release
(``cadgen._internal.auto_update``). An app's server line is written once, with the release that
installed it, and never rewritten for a release: it is a floor, and every entry defers to the
release the device runs (``<state>/current``, ``cadgen._internal.installations``), which this
command points at itself. So an update restarts nothing: the next session an app starts runs it.
In order, each step said as it runs:

1. **Plan.** Under a lock in the state folder, every agent app is read
   (``cadgen._internal.providers``), and the plan printed: per app, ``install``, ``update``,
   ``remove duplicate`` or ``leave``, with each command it runs and each file it edits.
   ``--dry-run`` stops there and writes nothing; otherwise the run goes on. Nothing is asked.
2. **Engine.** An older cadgen's engine serving the selected port is retired once it is idle
   (``cadgen.engine.client.retire_older``); one still in use is said, and converges on its next start.
3. **Apps.** Each app's own command installs or updates the plugin, which refreshes its skills (and
   may move its server's floor); Claude Desktop's config gets CAD's server where it has none, written
   atomically with a ``.bak`` beside it, and keeps the one it has whatever release that names; every
   second copy goes. The agents
   with no plugin that the Skills CLI knows get the skills, copied into their own skills folders by
   one ``npx skills add`` (Node needed); an app with a plugin never does. A command that fails is
   said with its output, and the other apps go on; the exit status is then 1.
4. **The cadgen command.** This installation registered, made the release the device runs when it is
   one past the current one (``--version``, the install command's when it was asked for a release by
   name: whatever the current one is), and ``~/.local/bin/cadgen`` written, as ``cadgen doctor`` does
   it (``cadgen._internal.installations``).
5. **Receipt.** What was done, in ``<state>/install-receipt.json``, for ``cadgen uninstall`` to take back;
   and which agents got which skills (those the Skills CLI's ``--json`` says it installed) from which
   release (``skills``), since that CLI keeps no versions: the next run adds them again for an agent
   that got them from another release or has lost one of them. It also keeps what the self-update
   runs the next release's setup with: the apps ``--only`` named (``only``, none when it named none)
   and the PATH this run found their commands on (``path``), recorded at every run.
6. **Report.** The doctor's read-only report for each app (``cadgen._internal.diagnostics``), the
   telemetry notice (``--no-telemetry`` turns it off, as ``cadgen telemetry off`` does), and the apps
   to restart to load a plugin this run installed (an update needs none); ``already up to date`` when
   a run found nothing to do and changed nothing. Its last line
   says that text-to-cad updates itself from now on, and how to turn that off
   (``cadgen._internal.auto_update.said``).

``cadgen uninstall`` takes back what the receipt says was done, newest first -- with no receipt, every
copy of text-to-cad found but a store's -- removes the ``cadgen`` command when it is cadgen's own,
and stops the engine on the selected port; with ``--purge`` it then removes the state and cache
folders. ``--only`` limits either to some apps (and then leaves the command and the engine alone).
Neither asks: the plan is printed and done, and ``--dry-run`` prints it alone.

Never done here: restarting an app, anything that needs sudo or a password, removing a ``cadgen``
command that is not cadgen's, editing a config that is not plain JSON, touching a store's copy.

Exit status: 0 done, or nothing to do; 1 a step failed; 2 bad arguments.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

DEFAULT_PROG = "cadgen setup"
SCHEMA = 1
RECEIPT = "install-receipt.json"
LOCK = "install.lock"
# Where loose copies of the skills are moved, rather than deleted.
ASIDE = "install-aside"
# How long an older engine is given to finish what it is doing before it is left to converge later.
RETIRE_SECONDS = 10.0
# The server's install channel in Claude Desktop's config (``cadgen._internal.channel``).
DESKTOP_CHANNEL = "claude-desktop"


def build_parser(prog: str = DEFAULT_PROG, *, uninstall: bool = False) -> argparse.ArgumentParser:
    """``cadgen setup``'s parser, or with ``uninstall`` ``cadgen uninstall``'s."""
    from cadgen._internal.providers import APPS, SKILLS_AGENTS
    from cadgen.updates import INSTALL, INSTALL_WINDOWS

    if uninstall:
        parser = argparse.ArgumentParser(
            prog=prog,
            allow_abbrev=False,
            description="Take text-to-cad out of every agent app on this machine: what earlier `cadgen setup` runs "
                        "did (their receipt), newest first, or with no receipt every copy of text-to-cad found; the "
                        "cadgen command when it is cadgen's own; the engine on the selected port stopped.",
        )
    else:
        parser = argparse.ArgumentParser(
            prog=prog,
            allow_abbrev=False,
            description="Set up text-to-cad in every agent app on this machine, or bring it up to date there: each "
                        "app's own command, Claude Desktop's config, second copies removed, an older engine retired. "
                        "Run it again to update; `cadgen uninstall` takes it out.",
            epilog=f"The install command runs this with the newest release: {INSTALL} (on Windows: {INSTALL_WINDOWS}).",
        )
    parser.add_argument("--dry-run", action="store_true", help="print the plan and stop: nothing is changed")
    parser.add_argument("--only", action="append", metavar="APP[,APP...]",
                        help=f"only these apps: {', '.join(APPS)}; and the agents the skills go to through "
                             f"the Skills CLI: {', '.join(SKILLS_AGENTS)}")
    if uninstall:
        parser.add_argument("--purge", action="store_true", help="remove cadgen's state and cache folders too")
        parser.add_argument("--port", type=int, metavar="PORT",
                            help="the engine port whose engine is stopped (default: CADGEN_PORT, else 3245)")
    else:
        parser.add_argument("--no-telemetry", action="store_true",
                            help="turn telemetry off, as `cadgen telemetry off` does")
        parser.add_argument("--version", metavar="X.Y.Z", dest="release",
                            help="the release the install command was asked for by name, this one: it becomes "
                                 "the one this device runs even when a newer one is installed")
        parser.add_argument("--port", type=int, metavar="PORT",
                            help="the engine port the apps' configs name (default: CADGEN_PORT, else 3245)")
    parser.add_argument("--json", action="store_true",
                        help="print the plan and what was done as JSON on stdout (progress goes to stderr)")
    return parser


def main(argv: Sequence[str] | None = None, prog: str = DEFAULT_PROG, *, uninstall: bool = False) -> int:
    """``cadgen setup``, or with ``uninstall`` ``cadgen uninstall`` (``cadgen.cli.uninstall`` calls it so)."""
    from cadgen._internal.providers import APPS, SKILLS_AGENTS

    parser = build_parser(prog, uninstall=uninstall)
    args = parser.parse_args(argv)
    only = []
    for given in args.only or ():
        only += [name.strip() for name in given.split(",") if name.strip()]
    unknown = sorted(set(only) - set(APPS) - set(SKILLS_AGENTS))
    if unknown:
        parser.error(f"--only: no app named {', '.join(unknown)} (the apps: {', '.join(APPS)}; "
                     f"the Skills CLI agents: {', '.join(SKILLS_AGENTS)})")
    from cadgen.engine.daemon import DEFAULT_PORT, environment_port

    if args.port is not None and not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535")
    try:
        port = args.port or environment_port() or DEFAULT_PORT
    except ValueError as error:
        parser.error(str(error))
    if not uninstall and args.release is not None:
        from cadgen import __version__

        if args.release != __version__:
            parser.error(f"--version {args.release}: this is cadgen {__version__}; run the install command "
                         f"with --version {args.release}")
    installer = Installer(args, only, port)
    return installer.uninstall() if uninstall else installer.install()


class Installer:
    """One run of ``cadgen setup`` or ``cadgen uninstall``: its plan, what it did, and how it says so."""

    def __init__(self, args: argparse.Namespace, only: list[str], port: int) -> None:
        from cadgen import __version__
        from cadgen._internal import providers
        from cadgen.engine.daemon import DEFAULT_PORT

        self.args, self.only, self.port, self.default_port = args, only, port, DEFAULT_PORT
        self.providers = providers
        self.machine = providers.Machine.here()
        self.release = __version__
        # Under --json the result is the one thing on stdout: what is said goes to stderr.
        self.out = sys.stderr if args.json else sys.stdout
        self.actions: list[dict[str, Any]] = []
        self.retired: dict[str, Any] | None = None
        # Whether Claude Code has the plugin after this run, so Cursor and Grok Build load it.
        self.fed = False

    # --- saying -----------------------------------------------------------------------------

    def say(self, line: str = "") -> None:
        self.out.write(line + "\n")
        self.out.flush()

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
            document = {"schema": SCHEMA, "plan": plan, "actions": self.actions, "retired": self.retired,
                        "verified": verified, "restart": restart}
            sys.stdout.write(json.dumps(document, ensure_ascii=False, separators=(",", ":")) + "\n")
            sys.stdout.flush()
        return code

    # --- where things are ---------------------------------------------------------------------

    def _state(self) -> Path:
        from cadgen.viewer.recents import state_dir

        return Path(state_dir())

    def _aside(self) -> Path:
        return self._state() / ASIDE / self.providers.stamp().replace(":", "")

    def _desktop_entry(self) -> dict[str, Any] | None:
        """CAD's server for Claude Desktop's chat: the plugins' exact command, uvx by its absolute path."""
        from cadgen._internal.launch import LAUNCHER

        uvx = self.providers.uvx(self.machine)
        if uvx is None:
            return None
        environment = {"CADGEN_INSTALL_CHANNEL": DESKTOP_CHANNEL}
        if self.port != self.default_port:
            environment["CADGEN_PORT"] = str(self.port)
        return {"command": uvx, "args": [*LAUNCHER[1:], f"cadgen=={self.release}", "cadgen", "mcp"],
                "env": environment}

    # --- the receipt ----------------------------------------------------------------------------

    def _folder(self):
        from cadgen.engine.registry import Folder

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

    def _engine(self) -> dict[str, Any]:
        """What serves the selected port, asked read-only (a hello, a status request to an older
        engine's own door, the system's word on a listener), and what the install does about it."""
        from cadgen._internal import diagnostics
        from cadgen._internal.providers import version_key
        from cadgen.engine import client

        port, release = self.port, self.release
        row = {"app": "engine", "label": "engine", "action": "leave"}
        probe = diagnostics.engine(port)
        status, other = probe.get("status"), probe.get("release")
        if status in ("missing", "stale_endpoint"):
            return {**row, "subject": f"port {port}: no engine running; the first CAD view or build starts one"}
        # An engine that answers says its release, met by protocol or not: an older one is retired.
        if status in ("compatible", "incompatible") and other:
            if other == release:
                return {**row, "subject": f"port {port}: this release's engine, cadgen {release}"}
            if version_key(other) < version_key(release):
                return {**row, "action": "retire", "release": other,
                        "subject": f"cadgen {other}'s engine on port {port}, once it is idle"}
            if version_key(other) > version_key(release):
                return {**row, "subject": f"port {port}: cadgen {other}'s engine, newer than {release}, left alone"}
            return {**row, "subject": f"port {port}: cadgen {other}'s engine"}
        try:
            older = client.legacy(port)
        except (OSError, ConnectionError):
            older = None
        if older is not None:
            return {**row, "action": "retire", "release": older.get("installation") or older["release"],
                    "pid": older["pid"], "subject": f"{older['said']} on port {port}, once it is idle"}
        try:
            holder = client.holder(port)
        except (OSError, ConnectionError, ValueError):
            holder = None
        if holder is not None:
            return {**row, "subject": client.held_words(holder)}
        return {**row, "subject": f"port {port}: {status or 'unknown'}"}

    def _converge(self, engine: dict[str, Any]) -> None:
        """An older engine on the selected port retired once idle, through its own door: the engine's
        ``retire_older`` where this cadgen has it, else an older protocol's stop."""
        from cadgen.engine import client

        retire = getattr(client, "retire_older", None)
        try:
            found = retire(self.port, wait=RETIRE_SECONDS) if retire is not None else self._retire(engine)
        except ConnectionError as error:
            self.say(f"engine   {error}")
            return
        if found:
            self.retired = {**found, "at": self.providers.stamp()}
            self.say(f"engine   retired cadgen {found.get('release')}'s engine (pid {found.get('pid')})")

    def _retire(self, engine: dict[str, Any]) -> dict[str, Any] | None:
        """Before the engine could retire an older one itself: an older protocol's engine stopped
        through its own door, as ``cadgen stop`` does; one of this protocol said, with its own stop."""
        from cadgen.engine import client

        older = client.legacy(self.port)
        if older is None:
            if engine.get("release"):
                raise ConnectionError(f"cadgen {engine['release']}'s engine serves port {self.port}: stop it with "
                                      f"`cadgen +{engine['release']} stop`, and the next start is this release's")
            return None
        if not client.stop_legacy(older, timeout=RETIRE_SECONDS):
            raise ConnectionError(f"{older['said']} did not take the stop request: stop it with "
                                  f"`cadgen +{older.get('installation') or older['release']} stop`")
        return {"release": older.get("installation") or older["release"], "pid": older["pid"], "port": self.port}

    # --- the cadgen command -------------------------------------------------------------------

    def _register(self) -> dict[str, Any]:
        """This installation registered, the device pointed at it (``installations.point``) and the
        proxy written: ``cadgen doctor``'s setup."""
        from cadgen._internal import installations
        from cadgen.cli.doctor import _command_path_hint

        version = installations.own_version()
        pointed, point_error = installations.NOT_RELEASE, None
        if version:
            (record, recorded, record_error), (proxy, before, proxy_error), (pointed, point_error) = \
                installations.setup(version, explicit=self.args.release is not None)
        else:
            record, recorded, record_error = None, None, None
            proxy, before, proxy_error = installations.proxy_path(), installations.proxy_status(), None
            self.say("cadgen   not registered: a source tree registers only as a version it is named "
                     f"({installations.NAME_ENV})")
        if record_error:
            self.say(f"cadgen   {record} cannot be written here ({record_error}): run this outside any sandbox")
        elif recorded == installations.REGISTERED:
            self.say(f"cadgen   registered {version} ({self.providers.shown(record, self.machine)})")
        if point_error:
            self.say(f"current  cannot be written here ({point_error}): run this outside any sandbox")
        elif pointed == installations.POINTED:
            self.say(f"current  cadgen {version}: what every app's next session runs")
        elif pointed == installations.BEHIND:
            found = installations.current() or {}
            self.say(f"current  cadgen {found.get('release')}, newer than {version}, left as it is "
                     "(the install command's --version makes an older release current)")
        wrote = bool(version) and not proxy_error and before in (installations.MISSING, installations.STALE)
        where = self.providers.shown(proxy, self.machine)
        if proxy_error:
            self.say(f"command  {where} cannot be written here ({proxy_error})")
        elif wrote:
            self.say(f"command  {where} written{_command_path_hint(proxy)}")
        elif before == installations.FOREIGN:
            self.say(f"command  {where} is not cadgen's, left alone: remove it to run cadgen by it")
        return {"registered": record if recorded and not record_error else None,
                "record_written": recorded == installations.REGISTERED,
                "pointed": pointed == installations.POINTED,
                "launcher": {"path": proxy, "status": before, "written": wrote, "error": proxy_error}}

    # --- the report ---------------------------------------------------------------------------

    def _verify(self, apps: dict[str, Any]) -> dict[str, Any]:
        """The doctor's read-only report, a line per app: the cadgen each app's config names, a floor
        the release the device runs stands in for (``ok`` at or below this release)."""
        from cadgen._internal import diagnostics

        try:
            data = diagnostics.report(None, None)
        except Exception as error:  # noqa: BLE001 - a report line, never a failure of the setup
            self.say(f"verify   unknown ({type(error).__name__}: {error})")
            return {"status": "unknown"}
        found: dict[str, set[str]] = {}
        for source in (data.get("hosts") or {}).get("sources") or []:
            release = source.get("release") or source.get("installation")
            if source.get("provider") in apps and release and source.get("status") == "ok":
                found.setdefault(source["provider"], set()).add(release)
        verdicts = {}
        for name, app in apps.items():
            if not app.present or (self.only and name not in self.only):
                continue
            releases = sorted(found.get(name, ()), key=self.providers.version_key)
            floors = [release for release in releases if release != self.release]
            newer = [release for release in releases
                     if self.providers.version_key(release) > self.providers.version_key(self.release)]
            verdict = ("newer" if newer else "ok" if releases
                       else "served" if name in self.providers.FED_BY and self.fed
                       else "not seen" if name in self.providers.INVENTORIED else "not read")
            verdicts[name] = {"verdict": verdict, "releases": releases}
            said = {"ok": f"cadgen {self.release}" + (f" (its config names {', '.join(floors)}, a floor)" if floors
                                                      else ""),
                    "newer": f"cadgen {', '.join(newer)}, newer than {self.release}",
                    "served": f"by the {self.providers.LABELS['claude']} plugin",
                    "not seen": "no copy of CAD's server found in what the report reads",
                    "not read": "not among what the report reads"}[verdict]
            self.say(f"verify   {app.label}: {said}")
        # The engine on the port this run set up, which the report's own selection (CADGEN_PORT, else
        # the default) need not be.
        try:
            engine = diagnostics.engine(self.port)
        except Exception as error:  # noqa: BLE001 - a report line, never a failure of the setup
            self.say(f"verify   engine port {self.port}: unknown ({type(error).__name__}: {error})")
            engine = None
        if engine is not None:
            state = {"compatible": f"cadgen {engine.get('release')} running", "missing": "not running yet",
                     "stale_endpoint": "not running yet"}.get(engine.get("status"),
                                                              f"{engine.get('status')}" + (f", cadgen {engine['release']}"
                                                                                         if engine.get("release") else ""))
            self.say(f"verify   engine port {engine.get('port')}: {state}")
        return {"status": data.get("status"), "apps": verdicts,
                "engine": {key: engine[key] for key in ("port", "status", "release") if key in engine} if engine else None}

    def _telemetry(self) -> str:
        """The telemetry line: the notice the first time, else what is sent and why; ``--no-telemetry``
        turns it off first, as ``cadgen telemetry off`` does."""
        from cadgen import analytics
        from cadgen.cli.telemetry import describe

        if self.args.no_telemetry:
            chosen = analytics.choose(False, by="cli", forget=analytics.request_deletion)
            said = describe() if chosen.get("saved") else "unchanged: the choice could not be saved in the state folder"
        elif analytics.notify(self.out):
            return describe()
        else:
            said = describe()
        self.say(f"telemetry {said}" + ("; turn it off with `cadgen telemetry off`" if said.startswith("on") else ""))
        return said

    def _restart(self, apps: dict[str, Any], changed: set[str]) -> list[str]:
        """What to restart to load what this run did (``changed``: the apps and agents that got it for
        the first time, and a config it edited, which its app reads as it opens); an update needs
        nothing, as the next session runs it."""
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

    def install(self) -> int:
        providers = self.providers
        title = f"text-to-cad {self.release} for this machine (engine port {self.port}):"
        if self.args.dry_run:
            apps = providers.detect(self.machine)
            steps = providers.plan(apps, release=self.release, desktop_entry=self._desktop_entry(), only=self.only,
                                   machine=self.machine, skills=(self._receipt() or {}).get("skills"))
            extra = [self._engine()]
            self._plan_lines(title, apps, steps, extra)
            self.say("Dry run: nothing was changed.")
            return self._result(steps, extra, None, [], 0)
        from cadgen.engine.file_lock import exclusive

        state = self._state()
        state.mkdir(parents=True, exist_ok=True)
        with exclusive(state / LOCK, waiting=lambda: self.say("waiting for another cadgen setup or uninstall to finish")):
            receipt = self._receipt() or {"schema": SCHEMA, "created": providers.stamp(), "actions": [], "retired": []}
            apps = providers.detect(self.machine)
            steps = providers.plan(apps, release=self.release, desktop_entry=self._desktop_entry(), only=self.only,
                                   machine=self.machine, skills=receipt.get("skills"))
            self.fed = providers.feeds(apps, self.only or providers.APPS)
            engine = self._engine()
            extra = [engine]
            self._plan_lines(title, apps, steps, extra)
            work = [step for step in steps if step.changes]
            if engine["action"] == "retire":
                self._converge(engine)
            # A config's first .bak is the one an uninstall restores: a later run keeps it.
            backed_up = {action["path"] for action in receipt.get("actions") or []
                         if action.get("kind") == "edit" and action.get("ok")
                         and (action.get("created") or (action.get("backup") and Path(action["backup"]).is_file()))}
            failed, changed = False, set()
            aside = self._aside()
            for step in work:
                self.say(f"{step.label}: {step.action} {step.subject}")
                ok, records = providers.apply(step, self.machine, say=lambda line: self.say(f"  {line}"),
                                              aside=aside, backed_up=backed_up)
                self.actions += records
                failed = failed or not ok
                # An update loads in the next session; Claude Desktop reads its config only as it opens.
                if ok and records and (step.action == "install" or step.edit):
                    changed.add(step.app)
                if ok and step.agents:  # the Skills CLI keeps no versions: the receipt says which release
                    actions = {other.app: other.action for other in steps}
                    changed.update(agent for agent in step.agents if actions.get(agent) == "install")
                    said = next((record["skills"] for record in records if record.get("skills") is not None), None)
                    got = dict(receipt.get("skills") or {})
                    for agent in step.agents:
                        folder = providers.skills_folder(agent, self.machine)
                        # The skills it said it installed; when it said nothing readable, what is there now.
                        names = said if said is not None else [path.name for path in providers.ours_in(folder)]
                        got[agent] = {"release": self.release, "folder": str(folder), "skills": names,
                                      "at": providers.stamp()}
                    receipt["skills"] = got
            registered = self._register()
            launcher = registered["launcher"]
            # What the self-update runs the next release's setup with: these apps, found on this PATH.
            remembered = {"path": self.machine.environ.get("PATH", ""), **({"only": self.only} if self.only else {})}
            moved = any(receipt.get(key) != remembered.get(key) for key in ("path", "only"))
            for key in ("path", "only"):
                receipt.pop(key, None)
            receipt.update(remembered)
            if self.actions or self.retired or registered["record_written"] or registered["pointed"] \
                    or launcher["written"]:
                receipt.update({"release": self.release, "updated": providers.stamp(), "port": self.port})
                receipt["actions"] = list(receipt.get("actions") or []) + self.actions
                if self.retired:
                    receipt["retired"] = list(receipt.get("retired") or []) + [self.retired]
                if launcher["written"]:
                    receipt["launcher"] = {"path": launcher["path"], "written": True, "at": providers.stamp()}
                if registered["registered"]:
                    receipt["registered"] = registered["registered"]
                self._keep(receipt)
            else:
                if moved and receipt.get("release"):
                    self._keep(receipt)
                self.say(f"text-to-cad {self.release} is already up to date here.")
        verified = self._verify(apps)
        self._telemetry_into(verified)
        restart = self._restart(apps, changed)
        if failed:
            from cadgen.updates import command

            self.say(f"Some steps failed (said above); the rest were done. Once they are fixed, run the install "
                     f"command again: {command()}")
        from cadgen._internal.auto_update import said

        self.say(said())
        return self._result(steps, extra, verified, restart, 1 if failed else 0)

    def _telemetry_into(self, verified: dict[str, Any]) -> None:
        try:
            verified["telemetry"] = self._telemetry()
        except Exception as error:  # noqa: BLE001 - the notice never fails the setup
            self.say(f"telemetry unknown ({type(error).__name__}: {error})")

    # --- uninstall ------------------------------------------------------------------------------

    def uninstall(self) -> int:
        providers = self.providers
        from cadgen._internal import installations
        from cadgen.viewer.recents import cache_dir

        receipt = self._receipt()
        apps = providers.detect(self.machine)
        steps = providers.uninstall_plan(apps, receipt, self.only or None, self.machine)
        extra: list[dict[str, Any]] = []
        proxy = installations.proxy_path()
        status = installations.proxy_status(proxy)
        # The cadgen command goes with a whole uninstall when it is cadgen's: its first lines carry the
        # proxy's mark. A file of that name that is not (``uv tool install``'s link) stays.
        ours = status in (installations.OK, installations.STALE, installations.NEWER)
        whole = not self.only
        launcher = whole and ours
        if launcher:
            extra.append({"app": "command", "label": "command", "action": "remove",
                          "subject": f"{providers.shown(proxy, self.machine)} (cadgen's)"})
        elif whole and status == installations.FOREIGN:
            extra.append({"app": "command", "label": "command", "action": "leave",
                          "subject": f"{providers.shown(proxy, self.machine)}: not cadgen's"})
        if whole:
            extra.append({"app": "engine", "label": "engine", "action": "stop", "subject": f"the engine on port {self.port}"})
        state, cache = self._state(), Path(cache_dir())
        if self.args.purge:
            extra.append({"app": "cadgen", "label": "cadgen", "action": "remove",
                          "subject": f"{providers.shown(state, self.machine)} and {providers.shown(cache, self.machine)}"})
        where = "what earlier runs did, newest first" if receipt else "no receipt: every copy of text-to-cad found"
        self._plan_lines(f"text-to-cad: cadgen uninstall takes back {where}:", apps, steps, extra)
        if self.args.dry_run:
            self.say("Dry run: nothing was changed.")
            return self._result(steps, extra, None, [], 0)
        failed, changed = False, set()
        from cadgen.engine.file_lock import exclusive

        state.mkdir(parents=True, exist_ok=True)
        with exclusive(state / LOCK, waiting=lambda: self.say("waiting for another cadgen setup or uninstall to finish")):
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
                from cadgen._internal import installations

                try:
                    installations.remove_proxy(proxy)
                    self.say(f"command  removed {providers.shown(proxy, self.machine)}")
                    self.actions.append({"app": "command", "action": "remove", "kind": "remove", "path": proxy,
                                         "ok": True, "at": providers.stamp()})
                except OSError as error:
                    failed = True
                    self.say(f"command  {providers.shown(proxy, self.machine)} could not be removed: {error}")
            if whole:
                failed = self._stop() or failed
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

    def _stop(self) -> bool:
        """``cadgen stop`` for the selected port, said in this run's words; True when it failed."""
        from cadgen.cli import stop

        with contextlib.redirect_stdout(self.out):
            try:
                code = stop.main(["--port", str(self.port)])
            except SystemExit as exit_:
                code = exit_.code if isinstance(exit_.code, int) else 1
        self.actions.append({"app": "engine", "action": "stop", "kind": "command",
                             "command": ["cadgen", "stop", "--port", str(self.port)], "code": code, "ok": code == 0,
                             "at": self.providers.stamp()})
        return code != 0

    def _purge(self, state: Path, cache: Path) -> None:
        import shutil

        shown = self.providers.shown
        for folder in (state, cache):
            shutil.rmtree(folder, ignore_errors=True)
            self.say(f"cadgen   removed {shown(folder, self.machine)}" if not folder.exists()
                     else f"cadgen   {shown(folder, self.machine)} could not be removed whole")


if __name__ == "__main__":
    raise SystemExit(main())
