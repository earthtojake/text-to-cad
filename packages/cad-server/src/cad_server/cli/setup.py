"""``cad setup``: text-to-cad installed, or brought up to date, on this machine as this release -- the default
channel moved to it and every agent app given its text --; ``cad update`` (``cad_server.cli.update``) runs the newest
release's; and ``cad uninstall`` (``cad_server.cli.uninstall``, this module's uninstall path with a parser of its
own) takes it out again.

The install command runs it (``cad_server.updates.INSTALL``: ``curl -fsSL https://texttocad.dev/install.sh |
sh``; on Windows ``INSTALL_WINDOWS``, ``irm https://www.texttocad.dev/install.ps1 | iex``) after finding or
installing uv: the newest release's server (``cad-server``), run through ``uvx``. Running it again is the update,
and ``cad update``, the update button and the automatic update take the same steps (``cad_server._internal.update``,
whose docstring is the contract between releases). In order, each step said as it runs:

1. **This release present.** Run from anywhere but its own folder -- uvx's environment, as the install command runs
   it, or the flat ``releases/<release>`` an updater of 0.11.10 or earlier made --, a release makes itself present
   in ``versions/<release>`` (``cad_server._internal.versions.make_present``: its server and kernel environments,
   from uv's cache where it holds them) and runs the same command from there. A development install, named
   (``CAD_INSTALLATION_VERSION``), or a source tree sets itself up where it is.
2. **Plan.** Under the device's install lock (``versions.install_lock``), every agent app is read from its own files,
   no app's command run (``cad_server._internal.providers``), and the plan printed: per app, ``install``,
   ``update``, ``remove duplicate``, ``remove server`` or ``leave``, with each command it runs and each file it
   edits; what serves the server's port (``CAD_ENGINE_PORT``, else 3245); and build123d, the CAD kernel.
   ``--dry-run`` stops there and writes nothing. Nothing is asked.
3. **0.8's server.** Where 0.8 is installed -- an installation's record in 0.8's own state folder whose Python and
   console script are still there (``cad_server._internal.installations.earlier``) -- that installation's own stop,
   ``cadgen stop``, is run, with its telemetry off (``NO_TELEMETRY``), and what it did is said. On Windows 0.10.0's
   installations, kept in the local application data (``installations.appdata``), are stopped the same way.
4. **The cad command.** ``~/.local/bin/cad`` written where it is missing or of an older revision
   (``installations.write_proxy``). First, once per device, whether it was updated or is a new person's, for
   What's new (``cad_server/whats_new.py``).
5. **The default channel.** Moved to this release (``versions.move``): its data imported from the version it
   replaces (or from the layout of 0.11.10 and earlier), the pointer written, the mirror those releases' clients
   read, every version no pointer names removed where nothing is connected to it, and the server's port handed to
   this release's server where the old one stopped. Where a server of 0.11.10 or earlier holds the flat door
   (``legacy``), this run -- the install command, ``cad update`` -- asks it to drain, waits for it, and starts this
   release's server on its port with the page token it imported, so pages open on it reload into this release;
   then that layout's code and caches go (``legacy.remove``). A source tree that is no version moves nothing. A
   move that fails changes no pointer and ends the run, before any app is changed.
6. **Apps.** The plugin folder, ``<state>/plugin``, is written from this release (``cad_server._internal.plugin``),
   and each app is pointed at it by its own command, the way it keeps a local plugin
   (``cad_server._internal.providers``): one reads the folder in place, one links it, one keeps a copy of it, which
   gets it again for this release. Claude gets no CAD server: the one releases through 0.11.10 wrote into Claude
   Desktop's config is taken out, written atomically with a ``.bak`` beside it. Every second copy goes, an earlier
   release's from the repository on GitHub among them; a plugin directory's copy (a store's: claude.ai's
   directory, a store in another app, or a marketplace added in Cursor) is the app's to deliver, and stays,
   with nothing of ours beside it, as do the named channels' pointers and versions. The agents with no plugin that
   the Skills CLI knows get the skills, copied from the folder by one ``npx skills add`` (Node needed). A command
   that fails is said with its output, and the other apps go on; the exit status is then 1. A folder that cannot be
   written changes no app that would point at it.
7. **Receipt.** What was done, in ``<state>/install-receipt.json``, for ``cad uninstall`` to take back; its
   presence says the install command ran here, which is what gives the default channel its updater; which
   agents got which skills from which release (``skills``), since the Skills CLI keeps no versions; and each app a
   step of 6 could not give this release's text (``behind``: the release, why, when), until a run gives it the text.
   ``cad doctor`` names such an app, ``cad update`` (this release's setup again, when it is the newest) does the apps
   step again, and so does the default version's server by itself, once a day at most while it is idle
   (``cad_server._internal.update.Update.catch_up``).
8. **Report.** Each app's copy as it is now, the server, the telemetry notice (``--no-telemetry`` turns it off, as
   ``cad telemetry off`` does), and the apps to restart; ``already up to date`` when a run found nothing to do and
   changed nothing. An agent whose folder lacks a skill the receipt says it got is a failure of the run.

``--engine-update`` is an updater's run of it (``cad_server._internal.update``): steps 1, 2, 4, 5, 6 and 7, each
stage a progress frame on stdout (``{"progress": ...}``, written for as long as someone reads it) and its words on
stderr. Its exit status is 0 once the default channel moved, an app that failed said on stderr; 1 when it did not.
Two updaters run it: this release's and later ones', and 0.11.10's and earlier ones' (the legacy caller), which run
it from the flat ``releases/<release>`` they made -- with ``CAD_UPDATE_PREPARE=1`` first for an automatic update,
which stops after step 1 (``PREPARE_ENV``) --, then drain their own server and have their helper start this
release's through the ``installations/current`` mirror and the flat door it holds (``daemon.Bridge``). So
``--engine-update`` never stops a server of 0.11.10 or earlier: their updater does.

``--add [--quiet]`` installs this release and stops (``cad_server._internal.versions.add``): ``versions/<release>``
made present and the ``cad`` command written where it is missing or of an older revision; nothing else: no pointer,
no app, no setting, no receipt. A skill's setup block and the install command's ``--add X`` run it, and the ``cad``
command does for a pinned version it lacks. Exit 3 where this shell cannot install it, with the command to run
outside it.

``cad uninstall`` takes back what the install command put here and nothing else: our plugin copies the receipt
says were made, newest first (the catalog removed with its plugin, the extension uninstalled, Cursor's copy deleted,
the skills removed by ``npx skills remove``, Claude Desktop's server an earlier release wrote taken out; with no
receipt, every copy of ours found); the plugin folder; the default pointer and the mirror; the default channel's
version's code, its server stopped, unless another pointer names it -- its data (settings, Recents, the documents'
records, the page token and port) stays for a later install, which finds it (``versions.remove_code``); the layout
of 0.11.10 and earlier; and the receipt.
A named channel's pointer, version and data stay -- a store delivered them -- and so does the ``cad`` command while
one is there, with a line saying which channel still uses it and to remove that plugin in its app. ``--purge``
removes everything: every version and channel, their data with them, the state and cache folders, and the ``cad``
command. ``--only``
limits it to some apps (and then leaves the command, the versions and the plugin folder alone). ``cad setup`` asks
nothing: the plan is printed and done -- installing is what was asked. ``cad uninstall`` destroys, so after its plan
it asks (``cad_server._internal.consent``): at a terminal ``Take text-to-cad out as planned? (y/N)``, and where no
one can be asked it changes nothing without ``--yes`` (``confirmation_required``, exit 2); the install command's
``--uninstall`` passes ``--yes``, the person's own word. ``--dry-run`` prints either plan alone.

Never done here: restarting an app, anything that needs sudo or a password, removing a ``cad`` command that is not
text-to-cad's, editing a config that is not plain JSON, removing a store's copy (a plugin directory's, an
administrator's or claude.ai's in Claude Code, one Cursor installed from a marketplace added in Cursor).

The first install never runs inside a Windows app package (an MSIX app's shell, the Claude desktop app's among
them): it installs nothing and says so (``installations.packaged``). ``--dry-run`` says it before the plan.

Exit status: 0 done, or nothing to do; 1 a step failed, an agent lacks its skills, or nothing was installed inside
an app package; 2 bad arguments; 3 this release could not be installed from this shell.
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
# The receipt's record of the apps a run could not give this release's text (``Installer._behind``): per app, the
# release it should have got, why it did not, and when. A later run that gives it the text takes it out. The default
# version's server, as it tends itself, runs the apps step again for an app behind (``update.Update.catch_up``), and
# ``cad doctor`` names it.
BEHIND = "behind"
# The steps that give an app this release's text: an app whose step of these fails is behind.
GIVES = frozenset({"install", "update"})
LOCK = "install.lock"  # ``cad_server._internal.versions.LOCK``: the device's install lock
# What text-to-cad keeps in the two folders ``--purge`` removes. A folder of that name that holds other things
# and none of these is another program's that shares the name, and purge leaves it as it is (the engine's own
# cache touches only its ``documents/``, ``engine/cache.py``).
STATE_OURS = frozenset({"versions", "installations", "engines", "documents", "recents", "releases", "plugin", "settings.json",
                        "settings.lock", "plugin.lock", "versions.json", "install-channels.json", "default", "channels", "used",
                        RECEIPT})
CACHE_OURS = frozenset({"base", "documents", "pycache"})
# Where loose copies of the skills are moved, rather than deleted.
ASIDE = "install-aside"
# The distribution 0.8's server was: no ``cad-server`` was published before 0.10.
EARLIER_SERVER = "cadgen"
# How long 0.8's own ``cadgen stop`` may take.
STOP_SECONDS = 60.0
# How long setup waits for the device's engine to say what it serves: a wedged engine never wedges setup.
ASK_SECONDS = 5.0
# Set by the updater of 0.11.10 and earlier for an automatic update's first run of ``--engine-update``: this release
# made present, and nothing else (the legacy caller; this release's own updater installs by ``--add`` instead).
PREPARE_ENV = "CAD_UPDATE_PREPARE"
# How long this run waits for a server of 0.11.10 or earlier to drain, its work in flight running to its end, before
# this release's server takes its port: as long as that release's own switch waited.
DRAIN_SECONDS = 3600.0
# How long an uninstall tries again to remove a channel's pointer the system refuses for a moment (``_unlink``): on
# Windows, while a launcher has the file open to read it, as every one does on each request.
POINTER_SECONDS = 2.0


def build_parser(prog: str = DEFAULT_PROG, *, uninstall: bool = False, update: bool = False) -> argparse.ArgumentParser:
    """``cad setup``'s parser, or with ``uninstall`` ``cad uninstall``'s, or with ``update``
    ``cad update``'s (``cad_server.cli.update``): setup's options."""
    from cad_server._internal.cli_parser import parser as command_parser
    from cad_server._internal.providers import APPS, SKILLS_AGENTS
    from cad_server.updates import INSTALL, INSTALL_WINDOWS

    if uninstall:
        parser = command_parser(
            prog=prog,
            allow_abbrev=False,
            description="Take out what the install command put on this machine: our copies of the plugin in every "
                        "agent app (with no receipt, every copy of ours found), the default channel and its version's "
                        "code, its server stopped; the cad command when no store's copy still uses it. Your settings, "
                        "Recents and documents' records stay for a later install. A copy a store delivered stays, "
                        "with its version; --purge removes everything.",
        )
    elif update:
        parser = command_parser(
            prog=prog,
            allow_abbrev=False,
            description="Install the newest release of text-to-cad and run its setup, as the update button does: the "
                        "default channel moved to it, its server on the same port, and every agent app given its "
                        "text. With the version feed out of reach, or this the newest, this release's setup.",
            epilog=f"The install command does the same: {INSTALL} (on Windows: {INSTALL_WINDOWS}).",
        )
    else:
        parser = command_parser(
            prog=prog,
            allow_abbrev=False,
            description="Set up text-to-cad on this machine as this release, or bring it up to date: this release "
                        "installed in its own folder, the default channel moved to it, and every agent app given "
                        "its text, second copies removed. `cad update` runs the newest release's; `cad uninstall` "
                        "takes it out.",
            epilog=f"The install command runs this with the newest release: {INSTALL} (on Windows: {INSTALL_WINDOWS}).",
        )
    parser.add_argument("--dry-run", action="store_true", help="print the plan and stop: nothing is changed")
    parser.add_argument("--only", action="append", metavar="APP[,APP...]",
                        help=f"only these apps: {', '.join(APPS)}; and the agents the skills go to through "
                             f"the Skills CLI: {', '.join(SKILLS_AGENTS)}")
    if uninstall:
        from cad_server._internal.consent import add_yes

        parser.add_argument("--purge", action="store_true",
                            help="remove everything: every version and channel, a store's among them, your "
                                 "settings, Recents and documents' records, and text-to-cad's state and cache folders")
        add_yes(parser, "take it out as planned")
    else:
        parser.add_argument("--no-telemetry", action="store_true",
                            help="turn telemetry off, as `cad telemetry off` does")
        if not update:
            # An updater's run (``cad_server._internal.update``, and 0.11.10's): progress frames on stdout.
            parser.add_argument("--engine-update", action="store_true", help=argparse.SUPPRESS)
            parser.add_argument("--add", action="store_true",
                                help="install this release in its own folder, and the cad command, and stop: no "
                                     "app, no default, no setting changed (a skill's setup block, and the install "
                                     "command's --add)")
            parser.add_argument("--quiet", action="store_true", help="with --add: say nothing unless it fails")
    parser.add_argument("--json", action="store_true",
                        help="print the plan and what was done as JSON on stdout (progress goes to stderr)")
    return parser


def main(argv: Sequence[str] | None = None, prog: str = DEFAULT_PROG, *, uninstall: bool = False,
         update: dict[str, Any] | None = None) -> int:
    """``cad setup``, or with ``uninstall`` ``cad uninstall`` (``cad_server.cli.uninstall`` calls it so);
    ``update``: what ``cad update --dry-run`` read of the version feed, which its ``--json`` carries."""
    from cad_server._internal.providers import APPS, SKILLS_AGENTS
    from cad_server.engine.daemon import default_port, environment_port

    parser = build_parser(prog, uninstall=uninstall)
    args = parser.parse_args(argv)
    if getattr(args, "add", False) or getattr(args, "quiet", False):
        given = [option for option, on in (("--dry-run", args.dry_run), ("--only", args.only),
                                           ("--no-telemetry", args.no_telemetry), ("--engine-update", args.engine_update),
                                           ("--json", args.json)) if on]
        if not args.add or given:
            parser.error("--quiet goes with --add alone" if not args.add else f"--add takes no {', '.join(given)}")
        from cad_server._internal import versions

        return versions.add(quiet=args.quiet)
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
    if getattr(args, "engine_update", False):
        # An updater's run outlives the server that reads its output when its move stops that server: whatever is
        # written after that, by this module or any other, is for no one, and never ends the run.
        streams = sys.stdout, sys.stderr
        sys.stdout, sys.stderr = Unread(sys.stdout), Unread(sys.stderr)
        try:
            return Installer(args, only, port, source, list(argv if argv is not None else sys.argv[1:]), prog).install()
        finally:
            sys.stdout, sys.stderr = streams
    installer = Installer(args, only, port, source, list(argv if argv is not None else sys.argv[1:]), prog)
    installer.update = update
    return installer.uninstall() if uninstall else installer.install()


class Unread:
    """A stream whose reader may go (``--engine-update``'s, read by the updater whose server the run stops): written
    as long as it is read, and quietly not once it is not."""

    def __init__(self, stream: Any) -> None:
        self.stream = stream
        self.gone = False

    def write(self, text: str) -> int:
        if not self.gone:
            try:
                return self.stream.write(text)
            except (OSError, ValueError):
                self.gone = True
        return len(text)

    def flush(self) -> None:
        if not self.gone:
            try:
                self.stream.flush()
            except (OSError, ValueError):
                self.gone = True

    def __getattr__(self, name: str) -> Any:
        return getattr(self.stream, name)


# --- the engine on the port, as the engine says it of itself -----------------------------------------


def running_engine() -> dict[str, Any] | None:
    """The ``status`` of the server the default channel runs now, asked read-only at the flat door and bounded
    (``ASK_SECONDS``), or None when none runs there: the default version's server holds that door (``daemon.Bridge``),
    and a server of 0.11.10 or earlier holds it as its own. One with no HTTP port yet (``serving`` empty: a command
    started it, and no page has asked for one) runs all the same."""
    from cad_server._internal import versions

    answer = versions.ask_flat({"op": "status"}, seconds=ASK_SECONDS)
    return answer if isinstance(answer, dict) and answer.get("ok") else None


def legacy_server(status: dict[str, Any] | None) -> bool:
    """Whether the server ``status`` describes runs from no version's folder: one of 0.11.10 or earlier (or a source
    tree's), which holds the flat door as its own."""
    from cad.engine import places

    prefix = (status or {}).get("prefix")
    if not isinstance(prefix, str) or not prefix:
        return False
    inside = os.path.normcase(os.path.realpath(places.versions_dir())).rstrip(os.sep) + os.sep
    return not os.path.normcase(os.path.realpath(prefix)).startswith(inside)


def serving_words(status: dict[str, Any]) -> str:
    """Where an engine that runs serves HTTP, in words: its port, or none yet."""
    serving = status.get("serving")
    port = serving.get("port") if isinstance(serving, dict) else None
    return f"on port {port}" if port else "with no HTTP port yet (the first CAD view opens one)"


def port_held(port: int) -> str | None:
    """Who listens on ``port`` when the device's engine does not, in words, or None."""
    from cad_server.engine import daemon

    if not daemon._answers("127.0.0.1", port):
        return None
    return daemon._who(port)


# The switch that keeps 0.8's ``cadgen`` (and 0.10.0's ``cad``) from counting, sending or telling its telemetry
# notice: set for its stop, which runs on the person's behalf, its words read by no one -- a notice it told
# there would read to it as told, so as their yes.
NO_TELEMETRY = {"CADGEN_TELEMETRY": "0", "CAD_TELEMETRY": "0"}


def stop_earlier(record: dict[str, Any]) -> tuple[bool, list[str] | None, str]:
    """0.8's own stop, ``cadgen stop --json`` -- or on Windows 0.10.0's, ``cad stop --json`` --, run by the
    console script of the installation ``record`` names (``installations.earlier``, ``installations.appdata``)
    in its own environment -- no import path of this release's -- with telemetry off for it
    (``NO_TELEMETRY``): whether it ran, the servers it says it stopped (None when it said nothing this
    reads), and what it said."""
    from cad_server._internal import installations

    environment = {key: value for key, value in os.environ.items() if key not in ("PYTHONPATH", "PYTHONHOME")}
    environment.update(NO_TELEMETRY)
    console = record.get(installations.EARLIER_CONSOLE) or record["cad"]
    try:
        done = subprocess.run([console, "stop", "--json"], env=environment,
                              stdin=subprocess.DEVNULL, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=STOP_SECONDS)
    except (OSError, subprocess.SubprocessError) as error:
        return False, None, f"{type(error).__name__}: {error}"
    said = "\n".join(part.strip() for part in (done.stdout, done.stderr) if part and part.strip())
    try:
        stopped = json.loads(done.stdout).get("stopped")
    except (ValueError, AttributeError):
        stopped = None
    return done.returncode == 0, stopped if isinstance(stopped, list) else None, said


class Installer:
    """One run of ``cad setup`` or ``cad uninstall``: its plan, what it did, and how it says so."""

    def __init__(self, args: argparse.Namespace, only: list[str], port: int, source: str,
                 argv: list[str] | None = None, prog: str = DEFAULT_PROG) -> None:
        from cad_server import __version__
        from cad_server._internal import plugin, providers

        self.args, self.only, self.port, self.source = args, only, port, source
        self.argv = list(argv or [])
        self.prog = prog
        # What `cad update --dry-run` read of the version feed (``cad_server.cli.update``), for its --json.
        self.update: dict[str, Any] | None = None
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
        # The servers of 0.8 this run stopped (``_stop_earlier``).
        self.stopped: list[dict[str, Any]] = []
        # Whether Claude Code has the plugin after this run, so Cursor and Grok Build load it.
        self.fed = False
        # Whether this run asked Claude Code's listing (``providers.read_for``), so reads it again the same way.
        self.listed = False
        # Whether the progress frames' reader has gone (``stage``).
        self.unread = False
        # Whether this run moved the default channel (``_move``).
        self.moved = False
        # Whether this is a pinned command's run (``update_own``), which never goes back from a development install.
        self.pinned = False

    # --- saying -----------------------------------------------------------------------------

    def say(self, line: str = "") -> None:
        try:
            self.out.write(line + "\n")
            self.out.flush()
        except (OSError, ValueError):
            pass  # an updater's run whose updater has gone: what it says is for no one now

    def _failed(self, words: str) -> int:
        """A run that stops before its plan, said already in its lines: exit 1, and under ``--json`` its one
        JSON document on stdout (``cad_server._internal.cli_errors``), so a caller reading it finds an answer."""
        if not self.args.json:
            return 1
        from cad_server._internal.cli_errors import Failure, write

        return write(Failure(words), prog=self.prog, as_json=True)

    def stage(self, stage: str, detail: str = "") -> None:
        """The engine's own run (``--engine-update``): the update's stage it reached, a progress frame
        on stdout (``cad.engine.progress``, kind ``update``), which the engine passes to the page."""
        if not self.engine_update:
            return
        from cad_server._internal.update import STAGES
        from cad.engine.progress import event

        if self.unread:
            return
        frame = event("update", stage, job=self.release, detail=detail, done=STAGES.index(stage), total=len(STAGES))
        try:
            sys.stdout.write(json.dumps({"progress": frame}) + "\n")
            sys.stdout.flush()
        except (OSError, ValueError):
            # The updater that read them is gone (its server stopped by this run's move): no one reads them now.
            self.unread = True

    # --- this release present --------------------------------------------------------------------

    def _home(self) -> str | None:
        """The version this run makes present and sets itself up from (``versions/<release>``): None for one that
        sets itself up where it is -- a process of a version already (its own code), a development install named
        (``installations.NAME_ENV``), a source tree, a name that is no release."""
        from cad.engine import places
        from cad_server._internal import installations

        if places.versioned() is not None or os.environ.get(installations.NAME_ENV) or installations.editable() \
                or not installations.RELEASE.fullmatch(self.release):
            return None
        return self.release

    def _relocated(self) -> int | None:
        """Step 1: run from anywhere but this release's own folder, this release made present
        (``versions.make_present``, from uv's cache where it holds it) and this command run again from there, its
        exit status returned; None when this run is already there (or sets itself up where it is). An updater of
        0.11.10 or earlier's first run (``PREPARE_ENV``) stops once it is present."""
        from cad.engine import places
        from cad_server._internal import versions
        from cad_server._internal.cli_errors import REASONS

        name = self._home()
        if name is None:
            return 0 if self._prepare() else None
        self.stage("install", f"text-to-cad {name}")
        found = versions.make_present(name, told=lambda line: self.say(f"version  {line}"))
        if not found.ok:
            self.say(f"version  {found.error}")
            from cad_server.updates import command

            self.say(f"Once that is fixed, run the install command again: {command()}")
            failed = self._failed(f"text-to-cad {name} could not be installed: {found.error}")
            return REASONS["cannot_install_here"] if found.cannot is not None and not self.args.json else failed
        self.stage("build123d", f"cad[build123d] {name}")
        if self._prepare():
            return 0
        assert found.record is not None
        run = [found.record["cad"], "setup", *self.argv]
        self.say(f"version  text-to-cad {name} in {self.providers.shown(str(places.version_dir(name)), self.machine)}")
        # uvx puts its own environment's folder first on PATH for the command it runs: uv's cache's, not the
        # person's, holding a uvx and a `cad` of its own. The release's run is given the person's PATH
        # (``providers.lasting``), so what it writes into the apps' configs and says of the `cad` command is theirs.
        environment = {key: value for key, value in os.environ.items() if key != PREPARE_ENV}
        environment["PATH"] = self.providers.lasting(os.environ.get("PATH", os.defpath))
        if os.name == "nt":
            return subprocess.call(run, env=environment)
        try:
            sys.stdout.flush()
            sys.stderr.flush()
        except (OSError, ValueError):
            pass
        os.execve(run[0], run, environment)
        return 1  # not reached

    def _prepare(self) -> bool:
        """Whether this is an updater of 0.11.10 or earlier's first run, ``--engine-update`` with ``PREPARE_ENV``
        (an automatic update getting ready while that release's server works): this release made present is all it
        asks, so the run stops there."""
        return self.engine_update and os.environ.get(PREPARE_ENV) == "1"

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
                        "verified": verified, "restart": restart,
                        **({"update": self.update} if self.update is not None else {})}
            sys.stdout.write(json.dumps(document, ensure_ascii=False, separators=(",", ":")) + "\n")
            sys.stdout.flush()
        return code

    # --- where things are ---------------------------------------------------------------------

    def _state(self) -> Path:
        from cad.engine.places import state_dir

        return Path(state_dir())

    def _aside(self) -> Path:
        return self._state() / ASIDE / self.providers.stamp().replace(":", "")

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

    @staticmethod
    def _backed_up(receipt: dict[str, Any]) -> set[str]:
        """The configs an earlier run already kept the ``.bak`` of (or made): a config's first ``.bak`` is the
        one an uninstall restores, so a later edit keeps it."""
        return {action["path"] for action in receipt.get("actions") or []
                if action.get("kind") == "edit" and action.get("ok")
                and (action.get("created") or (action.get("backup") and Path(action["backup"]).is_file()))}

    # --- the engine ---------------------------------------------------------------------------

    def _earlier(self) -> list[dict[str, Any]]:
        """Step 3's rows: each 0.8 installation still here (``installations.earlier``: its Python and console
        script there), whose own ``cadgen stop`` stops its server (``_stop_earlier``) if it runs -- which no
        process of this release asks it --; and on Windows each 0.10.0 one in the local application data
        (``installations.appdata``), whose own ``cad stop`` stops the engine it serves from the temporary
        folder, so this release's takes the port as it would on a computer that never had it."""
        from cad_server._internal import installations

        rows: list[dict[str, Any]] = []
        for label, records, key, name in (("0.8", installations.earlier(), installations.EARLIER_CONSOLE, EARLIER_SERVER),
                                          ("0.10", installations.appdata(), "cad", "cad-server")):
            for record in records:
                console = record[key]
                if not (os.path.isfile(record["python"]) and os.path.isfile(console)):
                    continue
                rows.append({"app": label, "label": label, "action": "stop", "release": record["version"],
                             "record": record, "server": name,
                             "subject": f"{name} {record['version']}'s server, if it runs: "
                                        f"`{self.providers.shown(console, self.machine)} stop`"})
        return rows

    def _engine(self, earlier: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        """What serves the engine's port, asked read-only, and what this run does about it: the default channel's
        server is handed to this release's (``_move``: the old version's where nothing is in flight there, one of
        0.11.10 or earlier drained, ``_take_over``); another program on the port is said, and what
        the engine does about it -- once ``earlier``'s stops (0.8's servers) are done, when there are any."""
        port = self.port
        row: dict[str, Any] = {"app": "engine", "label": "engine", "action": "leave"}
        if not port:
            return {**row, "subject": "CAD_ENGINE_PORT=0: the engine takes any free port"}
        status = running_engine()
        if status is None:
            held = port_held(port)
            if held is None:
                return {**row, "subject": f"port {port}: no engine running; the first CAD view or build starts one"}
            then = ("the engine serves on the next free port, and says so" if self.source == "default"
                    else "stop it, or set another CAD_ENGINE_PORT")
            if earlier:
                then = f"if the stop above does not free it, {then}"
            return {**row, "subject": f"port {port} is held by {held}: {then}"}
        name = status.get("installation") or status.get("version") or "?"
        who = f"cad-server {name}'s engine (pid {status.get('pid')}) {serving_words(status)}"
        prefix = status.get("prefix")
        if isinstance(prefix, str) and os.path.normcase(os.path.realpath(prefix)) == \
                os.path.normcase(os.path.realpath(sys.prefix)):
            return {**row, "subject": f"{who}: this installation's"}
        return {**row, "action": "switch", "subject": f"{who}: drains, then cad-server {self.release}'s takes its place"
                                                      " once nothing is in flight there"}

    def _kernel(self) -> dict[str, Any] | None:
        """The CAD kernel environment, the base the engine's own kernel processes start from
        (``cad_server._internal.base``), as the plan says it: made, made with the version this run installs, or (a
        process with no version) made on first need -- never by this row. None for an installation that carries the
        kernel itself."""
        from cad.engine import places
        from cad_server._internal import base

        row: dict[str, Any] = {"app": "build123d", "label": "build123d", "action": "leave"}
        home = self._home()
        try:
            installation = base.Installation.here()
            if home is not None:
                # Run from anywhere but this release's own folder (uvx's environment): the real run moves into
                # versions/<release> first, and the version is made present with its base there
                # (``versions.make_present``), whose key is read from the version's own server, not known before it
                # is there. A dry run names the folder.
                shown = self.providers.shown(str(places.code_dir(home) / base.BASE), self.machine)
                if places.version_record(home) is not None:
                    return {**row, "subject": f"cad[{base.EXTRA}] {self.release} in {shown}, made with the version"}
                return {**row, "subject": f"cad[{base.EXTRA}] {self.release}, made with the version in {shown}"}
            if installation.kernel:
                return None
            found = base.ensure(installation, make=False)
            folder = base.where(installation)
        except (base.Refused, OSError) as error:
            return {**row, "subject": f"unknown ({error})"}
        shown = self.providers.shown(str(folder), self.machine)
        if found is not None:
            return {**row, "subject": f"cad[{base.EXTRA}] {installation.release} in {shown}"}
        return {**row, "subject": f"cad[{base.EXTRA}] {installation.release}, made on first need in {shown}"}

    def _stop_earlier(self, row: dict[str, Any]) -> None:
        """Step 3: a 0.8 installation's server stopped by its own ``cadgen stop`` (``stop_earlier``), and what
        it did said; a stop that fails is said, and the run goes on."""
        release, label, name = row["release"], row["label"].ljust(8), row["server"]
        verb = "cadgen stop" if row["label"] == "0.8" else "cad stop"
        ok, stopped, said = stop_earlier(row["record"])
        last = f": {said.splitlines()[-1]}" if said else ""
        if not ok:
            self.say(f"{label} {name} {release}'s `{verb}` failed{last}; its server may still run")
        elif stopped is None:
            self.say(f"{label} ran {name} {release}'s `{verb}`{last}")
        elif not stopped:
            self.say(f"{label} {name} {release}'s server was not running")
        else:
            self.stopped.append({"release": release, "servers": stopped, "at": self.providers.stamp()})
            self.say(f"{label} stopped {name} {release}'s server (its own `{verb}`)")

    # --- the cad command -------------------------------------------------------------------

    def _register(self) -> dict[str, Any]:
        """Step 4: the ``cad`` command written where it is missing or of an older revision
        (``installations.write_proxy``), said; and once per device, What's new settled. Nothing is registered: the
        records 0.11.10 and earlier read are the mirror the default channel's move writes."""
        from cad_server import whats_new
        from cad_server._internal import installations
        from cad_server.cli.doctor import _command_path_hint

        version = installations.own_version()
        # Whether this device was updated or is a new person's, decided once while the records of the
        # releases before are still there (``cad_server/whats_new.py``): its What's new, or none.
        whats_new.settle(release=whats_new.minor(version))
        proxy, before, proxy_error = installations.write_proxy()
        wrote = not proxy_error and before in (installations.MISSING, installations.STALE)
        where = self.providers.shown(proxy, self.machine)
        if proxy_error:
            self.say(f"command  {where} cannot be written here ({proxy_error})")
        elif wrote:
            self.say(f"command  {where} written{_command_path_hint(proxy)}")
        elif before == installations.FOREIGN:
            self.say(f"command  {where} is not text-to-cad's, left alone: remove it to run cad by it")
        return {"registered": None, "record_written": False,
                "launcher": {"path": proxy, "status": before, "written": wrote, "error": proxy_error}}

    # --- the default channel -----------------------------------------------------------------------------------

    def _move(self, before: dict[str, Any] | None) -> tuple[bool, Any]:
        """Step 5: the default channel moved to this run's version (``versions.move``), said in its lines; then,
        where a server of 0.11.10 or earlier held the flat door as this run began (``before``, ``legacy_server``)
        and this is no updater's run, its port handed to this version's server (``_take_over``), once the install
        lock is let go (``taking_over``). ``(failed, what the move did, or None for a process that is no version)``."""
        from cad.engine import places
        from cad_server._internal import versions

        name = places.versioned()
        if name is None:
            self.say("default  left as it is: this cad-server is a source tree that runs as no version "
                     "(scripts/install/dev_install.py installs a checkout as one)")
            return False, None
        self.stage("restart", f"text-to-cad {name}")
        try:
            # A person's install goes back from a development install (``dev_install.py``) to a release.
            moved = versions.move(None, name, told=lambda line: self.say(f"default  {line}"),
                                  from_development=not self.engine_update and not self.pinned,
                                  mend=not self.pinned)
        except (OSError, ValueError) as error:
            self.say(f"default  the default channel could not be moved to text-to-cad {name}: {error}")
            return True, None
        if moved.kind == "same":
            self.say(f"default  text-to-cad {name}, as before")
        elif moved.kind == "moved":
            self.say(f"default  text-to-cad {name}" + (f" (was {moved.old})" if moved.old else ""))
            self.moved = True
        elif moved.kind == "stale":
            self.say(f"default  the default channel is on text-to-cad {moved.old}, newer than this release: nothing "
                     "changed (going back to an older release is not supported)")
            return True, moved
        else:
            self.say(f"default  the default channel stays where it was: {moved.error}")
            return True, moved
        if before is not None and not self.engine_update and legacy_server(before):
            # Done once the install lock is let go (``install``): its wait for the old server to drain may be long,
            # and no other channel's move waits on it.
            self.taking_over = (name, before)
        return False, moved

    def _take_over(self, name: str, before: dict[str, Any]) -> None:
        """A server of 0.11.10 or earlier, which held the flat door as this run began (``before``, its ``status``),
        asked to drain -- ``{"op": "stop", "drain": true}``, which every release since 0.10 speaks -- and waited for
        while its work in flight ends (``DRAIN_SECONDS`` at most); then the default channel's version read again --
        ``name``, this run's, unless an update moved it meanwhile -- and its server started, holding that door now
        (``daemon.Bridge``), on the port the old one served pages on, with the page token it imported,
        so a page open on it reloads into this version and every link still opens; then the layout of 0.11.10 and
        earlier removed, now that nothing of it runs (``versions.sweep``, ``legacy.remove``). What did not happen is
        said, and fails nothing: the next command starts this version's server, on the next free port. Run with no
        lock held, its sweep taking the install lock as it does."""
        from cad.engine import client
        from cad_server._internal import versions

        serving = before.get("serving")
        port = serving.get("port") if isinstance(serving, dict) else None
        old = before.get("installation") or before.get("version") or "0.11.10 or earlier"
        self.say(f"engine   cad-server {old}'s server (pid {before.get('pid')}) drains once nothing is in flight, "
                 f"then text-to-cad {name}'s takes its place" + (f" on port {port}" if port else ""))
        if versions.ask_flat({"op": "stop", "drain": True}) is None:
            self.say(f"engine   cad-server {old}'s server did not answer: it keeps running until it stops")
            return
        try:
            gone = client.wait_gone(timeout=DRAIN_SECONDS, endpoint=versions.flat_endpoint())
        except ConnectionError:
            gone = False
        if not gone:
            self.say(f"engine   cad-server {old}'s server is still busy: it stops once its work ends")
            return
        # The wait may have been long: the default channel may be on another version now (an update meanwhile). Its
        # server takes the old one's place, or none does.
        from cad_server._internal import pointers

        try:
            name = pointers.default().version
        except OSError as error:
            self.say(f"engine   the default channel cannot be read now ({error}): the next command starts its server")
            return
        if name is None or not versions.start_server(name):
            self.say(f"engine   text-to-cad {name}'s server did not start: the next command starts it" if name else
                     "engine   the default channel is on no version now: no server takes its place")
            return
        versions.ask(name, {"op": "bridge"})
        if port:
            answer = versions.ask(name, {"op": "http", "port": port}, seconds=versions.START_SECONDS)
            if not isinstance(answer, dict) or "failed" in answer or not answer.get("url"):
                why = (answer or {}).get("failed") or "it did not answer"
                self.say(f"engine   text-to-cad {name}'s server could not take port {port}: {why}")
            elif versions.answered_port(answer) != port:
                self.say(f"engine   text-to-cad {name} serves pages on port {versions.answered_port(answer)}: port "
                         f"{port} is still held")
            else:
                self.say(f"engine   text-to-cad {name} serves pages on port {port}, as cad-server {old} did")
        versions.sweep(told=lambda line: self.say(f"default  {line}"))

    def _done(self, step: Any) -> str | None:
        """What the app ``step`` installs this release in has of it now, read again, when a command of the step
        failed (``providers.apply``): this release's copy, ours, in words -- a tool that exits non-zero after
        doing its work (``gemini extensions link`` once its integrity store warns) did it -- else None."""
        providers = self.providers
        if step.action not in ("install", "update") or step.app not in providers.APPS:
            return None
        try:
            app = providers.detect(self.machine, [step.app], folder=self.folder, listed=self.listed)[step.app]
        except Exception:  # noqa: BLE001 - a check that cannot read the app finds nothing: the failure stands
            return None
        ours = app.ours()
        if ours is None or ours.version != self.release:
            return None
        origin = ours.origin(self.machine)
        return ours.words(self.machine) + (f", {origin}" if origin else "")

    # --- the report ---------------------------------------------------------------------------

    def _verify(self) -> dict[str, Any]:
        """Each selected app's copy as the apps say it now, read again, and the engine on the port."""
        providers = self.providers
        try:
            apps = providers.detect(self.machine, folder=self.folder, listed=self.listed)
        except Exception as error:  # noqa: BLE001 - a report line, never a failure of the setup
            self.say(f"verify   unknown ({type(error).__name__}: {error})")
            return {"apps": {}, "engine": None}
        verdicts: dict[str, Any] = {}
        for name, app in apps.items():
            if not app.present or (self.only and name not in self.only):
                continue
            ours, stores = app.ours(), app.stores()
            if name == "claude-desktop":
                # Claude gets no CAD server: an earlier release's entry still there is said, never a failure.
                found = {"verdict": "server", "release": ours.version} if ours is not None else {"verdict": "none"}
                said = (f"CAD's server text-to-cad {ours.version or '?'} is still in its config" if ours is not None
                        else f"{app.unreadable}: left alone" if app.unreadable
                        else f"no CAD server: Claude gets the skills alone, through {providers.LABELS['claude']}'s plugin")
            elif ours is not None:
                found = {"verdict": "ok", "release": ours.version}
                said = ours.words(self.machine)
                origin = ours.origin(self.machine)
                said += f", {origin}" if origin else ""
            elif stores:
                found = {"verdict": "store"}
                said = f"{stores[0].words(self.machine)}, {stores[0].updater()}"
            elif name in providers.FED_BY and self.fed:
                found = {"verdict": "served"}
                said = f"served by the {providers.LABELS['claude']} plugin"
            else:
                found = {"verdict": "none"}
                said = "no copy of text-to-cad"
            verdicts[name] = found
            self.say(f"verify   {app.label}: {said}")
        verdicts.update(self._verify_skills())
        engine: dict[str, Any] | None = None
        if self.port:
            try:
                status = running_engine()
            except Exception as error:  # noqa: BLE001 - a report line, never a failure of the setup
                self.say(f"verify   engine port {self.port}: unknown ({type(error).__name__}: {error})")
            else:
                name = (status or {}).get("installation") or (status or {}).get("version")
                engine = {"port": self.port, "release": name}
                self.say(f"verify   engine port {self.port}: not running; the next CAD session starts one"
                         if status is None else f"verify   engine: cad-server {name} running, {serving_words(status)}")
        return {"apps": verdicts, "engine": engine}

    def _verify_skills(self) -> dict[str, Any]:
        """The Skills CLI agents the receipt says got the skills, each read again: its folder holds them, in
        the words of ``cad doctor`` (``providers.skills_words``), or the line says it failed and which it
        lacks: verdict ``missing``, which fails the run."""
        providers = self.providers
        verdicts: dict[str, Any] = {}
        for agent, got in ((self._receipt() or {}).get("skills") or {}).items():
            if agent not in providers.SKILLS_AGENTS or not isinstance(got, dict) or (self.only and agent not in self.only):
                continue
            missing = providers.skills_lost(agent, got, self.machine)
            verdicts[agent] = {"verdict": "missing" if missing else "ok", "release": got.get("release"),
                               **({"missing": missing} if missing else {})}
            if missing:
                where = providers.shown(providers.skills_folder(agent, self.machine), self.machine)
                self.say(f"verify   {providers.label(agent)}: failed: {', '.join(missing)} not in {where}, where the "
                         f"Skills CLI was to copy the skills of text-to-cad {got.get('release') or '?'}")
            else:
                self.say(f"verify   {providers.label(agent)}: {providers.skills_words(agent, got, self.machine)}")
        return verdicts

    def _telemetry(self) -> str:
        """The telemetry line: the notice the first time, else what is sent and why; ``--no-telemetry``
        turns it off first, as ``cad telemetry off`` does. Under ``--json`` the notice is not said: an answer
        a program reads tells no person, so it waits for a run a person reads, and nothing is sent by
        default until then."""
        from cad_server import analytics
        from cad_server.cli.telemetry import describe

        if self.args.no_telemetry:
            chosen = analytics.choose(False, by="cli", forget=analytics.request_deletion)
            said = describe() if chosen.get("saved") else "unchanged: the choice could not be saved in the state folder"
        elif not self.args.json and analytics.notify(self.out):
            return describe()
        else:
            said = describe()
        self.say(f"telemetry {said}" + ("; turn it off with `cad telemetry off`" if said.startswith("on") else ""))
        return said

    def _restart(self, apps: dict[str, Any], changed: set[str], heading: str = "Next, restart to load it:") -> list[str]:
        """What to restart for what this run did to take hold (``changed``: the apps it installed or updated
        the plugin in, a config it edited, and the agents that got the skills, or lost them to an uninstall),
        under ``heading``."""
        providers = self.providers
        names = [name for name in providers.APPS if name in changed]
        if "claude" in changed:  # Cursor and Grok Build load the Claude Code plugin
            names += [name for name in providers.FED_BY if self.fed and apps[name].present and name not in names]
        lines = [providers.restart(name, self.machine) for name in names]
        agents = [providers.label(name) for name in providers.SKILLS_AGENTS if name in changed]
        if agents:
            lines.append(f"{', '.join(agents)}: start a new session for the skills")
        if lines:
            self.say(heading)
            for line in lines:
                self.say(f"  {line}")
        return lines

    # --- install --------------------------------------------------------------------------------

    @staticmethod
    def _public(row: dict[str, Any]) -> dict[str, Any]:
        """A plan row as the plan shows it: without the installation record it acts by."""
        return {key: value for key, value in row.items() if key != "record"}

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
        """After the plugin folder was written again (``cad plugin --refresh``, which the updater of 0.11.10 and
        earlier runs once its helper has started this release's server): the
        copies the apps keep of it brought to it (``providers.refresh_plan``), under the installer's lock, the receipt kept. ``(ok, the steps run)``."""
        from cad_server._internal import versions

        providers = self.providers
        failed, changed = False, set()
        with versions.install_lock(waiting=lambda: told("waiting for another cad setup or uninstall to finish")):
            receipt = self._receipt() or {"schema": SCHEMA, "created": providers.stamp(), "actions": [], "stopped": []}
            apps, steps, self.listed = providers.read_for(
                lambda apps: providers.refresh_plan(apps, release=self.release, folder=self.folder, machine=self.machine,
                                                    skills=receipt.get("skills")),
                self.machine, folder=self.folder)
            backed_up = self._backed_up(receipt)
            for step in steps:
                told(f"{step.label}: {step.action} {step.subject}")
                ok, records = providers.apply(step, self.machine, say=lambda line: told(f"  {line}"),
                                              backed_up=backed_up)
                self.actions += records
                failed = failed or not ok
                if ok and step.agents:
                    self._record_skills(receipt, step, steps, records, changed)
            if self.actions:
                receipt.update({"release": self.release, "updated": providers.stamp()})
                receipt["actions"] = list(receipt.get("actions") or []) + self.actions
                self._keep(receipt)
        due = list(dict.fromkeys(step.app for step in steps if providers.needs_restart(step)))
        if due:
            told("Next, restart to load it: " + "; ".join(providers.restart(app, self.machine) for app in due))
        return not failed, [step.data() for step in steps]

    def install(self) -> int:
        from cad_server._internal import installations, versions

        providers = self.providers
        where = f"engine port {self.port}" if self.port else "engine on any free port"
        title = f"text-to-cad {self.release} for this machine ({where}):"
        if not self.engine_update and (package := installations.packaged()) and installations.current() is None:
            from cad_server.updates import command

            self.say(f"Not installed: {installations.packaged_words(package)}. Run the install command from "
                     f"a terminal of its own (Windows Terminal or PowerShell), not from an app's: {command()}")
            if not self.args.dry_run:
                return self._failed(f"Not installed: {installations.packaged_words(package)}")
        if self.args.dry_run:
            apps = providers.detect(self.machine, folder=self.folder)
            steps = providers.plan(apps, release=self.release, folder=self.folder,
                                   only=self.only, machine=self.machine, skills=(self._receipt() or {}).get("skills"))
            kernel = self._kernel()
            earlier = self._earlier()
            extra = [*self._version_rows(), self._plugin_row(), *map(self._public, earlier),
                     self._public(self._engine(earlier)), *([kernel] if kernel else [])]
            self._plan_lines(title, apps, steps, extra)
            self.say("Dry run: nothing was changed.")
            return self._result(steps, extra, None, [], 0)
        relocated = self._relocated()
        if relocated is not None:
            return relocated
        from cad.engine.places import adopt_earlier

        # What this release keeps of 0.8's state folder, moved into its own first: the person's settings,
        # the documents' records and Recents, and the receipt.
        adopt_earlier()
        with versions.install_lock(waiting=lambda: self.say("waiting for another cad setup or uninstall to finish")):
            receipt = self._receipt() or {"schema": SCHEMA, "created": providers.stamp(), "actions": [], "stopped": []}
            apps, steps, self.listed = providers.read_for(
                lambda apps: providers.plan(apps, release=self.release, folder=self.folder,
                                            only=self.only, machine=self.machine,
                                            skills=receipt.get("skills")),
                self.machine, folder=self.folder)
            self.fed = providers.feeds(apps, self.only or providers.APPS)
            earlier = self._earlier() if not self.engine_update else []
            before = running_engine() if not self.engine_update else None
            engine = self._engine(earlier) if not self.engine_update else {
                "app": "engine", "label": "engine", "action": "leave", "subject": "an updater's run"}
            kernel = self._kernel()
            extra = [*self._version_rows(), self._plugin_row(), *map(self._public, earlier), self._public(engine),
                     *([kernel] if kernel else [])]
            self._plan_lines(title, apps, steps, extra)
            for row in earlier:
                self._stop_earlier(row)
            registered = self._register()
            failed, moved = self._move(before)
            if failed:
                # The default channel stays where it was, and so does every app: their text runs the version
                # the channel is on.
                if self.engine_update:
                    return 1
                from cad_server.updates import command

                self.say(f"Nothing else was changed. Once that is fixed, run the install command again: {command()}")
                return self._result(steps, extra, None, [], 1)
            self.stage("apps")
            failed, changed = self._apps(receipt, steps)
            self._record(receipt, registered)
            # An agent left without the skills for want of Node is not up to date, though nothing was done.
            if not (self.actions or self.stopped or registered["launcher"]["written"] or self.moved
                    or any(step.subject == providers.NEED_NODE for step in steps)):
                self.say(f"text-to-cad {self.release} is already up to date here.")
        taking_over = getattr(self, "taking_over", None)
        if taking_over is not None:  # outside the install lock: the drain it waits for may take an hour
            self._take_over(*taking_over)
        if self.engine_update:
            # The default channel moved: an app that failed is said on stderr, and done again by the next update.
            return 0
        verified = self._verify()
        self._telemetry_into(verified)
        restart = self._restart(apps, changed)
        # An agent whose folder lacks a skill the Skills CLI said it copied has not got them: the run failed.
        failed = failed or any(found.get("verdict") == "missing" for found in verified["apps"].values())
        if failed:
            from cad_server.updates import command

            self.say(f"Some steps failed (said above); the rest were done. Once they are fixed, run the install "
                     f"command again: {command()}")
        return self._result(steps, extra, verified, restart, 1 if failed else 0)

    def update_own(self) -> Any:
        """A pinned command's update of the default channel to this process's version
        (``cad_server._internal.pins.update_default``): steps 4 to 7 -- the ``cad`` command, the move, the apps, the
        receipt -- with no plan and no report, each line said on stderr, and no server of 0.11.10 or earlier asked
        to stop (that release's own updater, or the install command, does). What the move did
        (``versions.Moved``), or None for a process that is no version."""
        from cad_server._internal import versions

        providers = self.providers
        self.pinned = True
        with versions.install_lock(waiting=lambda: self.say("waiting for another install of text-to-cad to finish")):
            receipt = self._receipt() or {"schema": SCHEMA, "created": providers.stamp(), "actions": [], "stopped": []}
            _apps, steps, self.listed = providers.read_for(
                lambda apps: providers.plan(apps, release=self.release, folder=self.folder, only=self.only,
                                            machine=self.machine, skills=receipt.get("skills")),
                self.machine, folder=self.folder)
            self.fed = providers.feeds(_apps, providers.APPS)
            registered = self._register()
            failed, moved = self._move(None)
            if failed or moved is None:
                return moved
            self._apps(receipt, steps)
            self._record(receipt, registered)
            return moved

    def _version_rows(self) -> list[dict[str, Any]]:
        """The plan's rows for steps 1 and 5: this release made present, where it is not; and the default
        channel, moved to it or on it already."""
        from cad.engine import places
        from cad_server._internal import pointers

        rows: list[dict[str, Any]] = []
        name = self._home() or places.versioned()
        if name is None:
            return rows
        where = self.providers.shown(str(places.version_dir(name)), self.machine)
        if places.version_record(name) is None:
            rows.append({"app": "version", "label": "version", "action": "install",
                         "subject": f"text-to-cad {name} in {where}, once"})
        try:
            leaving = pointers.leaving()
        except OSError:
            leaving = pointers.Default(None, None)
        if leaving.version == name and leaving.source == "pointer":
            rows.append({"app": "default", "label": "default", "action": "leave", "subject": f"text-to-cad {name}"})
        else:
            was = ("" if leaving.version is None else
                   f" (from {leaving.version}" + (", of 0.11.10 or earlier: its data imported, its code and caches "
                                                 "removed once nothing runs from them)" if leaving.legacy else ")"))
            rows.append({"app": "default", "label": "default", "action": "move", "subject": f"text-to-cad {name}{was}"})
        return rows

    def _apps(self, receipt: dict[str, Any], steps: list[Any]) -> tuple[bool, set[str]]:
        """Step 6: the plugin folder written from this release, then each app's step of the plan (``steps``) that
        changes something, said as it runs. ``(failed, the apps and agents to restart)``."""
        providers = self.providers
        failed = False
        work = [step for step in steps if step.changes]
        # Per app given this release's text, None where it got it, else why not (``_behind``).
        outcome: dict[str, str | None] = {}
        # The folder the apps are pointed at, this release's, before they are: a folder that cannot be
        # written changes no app that would point at it.
        if self._write_plugin() is None:
            failed = True
            for step in [step for step in work if self._needs_folder(step)]:
                self.say(f"{step.label}: {step.action} {step.subject}: not done, with no plugin folder")
                work.remove(step)
                if step.action in GIVES:
                    outcome[step.app] = "the plugin folder could not be written"
        backed_up = self._backed_up(receipt)
        changed: set[str] = set()
        aside = self._aside()
        for step in work:
            self.say(f"{step.label}: {step.action} {step.subject}")
            ok, records = providers.apply(step, self.machine, say=lambda line: self.say(f"  {line}"),
                                          aside=aside, backed_up=backed_up, done=self._done)
            self.actions += records
            failed = failed or not ok
            # A plugin installed or updated loads in the app's next session; a config, as the app opens.
            if ok and records and providers.needs_restart(step):
                changed.add(step.app)
            if ok and step.agents:  # the Skills CLI keeps no versions: the receipt says which release
                self._record_skills(receipt, step, steps, records, changed)
            if step.action in GIVES:
                why = None if ok else _why(records)
                for app in step.agents or [step.app]:  # one Skills CLI command gives every agent its skills
                    if outcome.get(app) is None:  # a step "in the command above" never clears that command's failure
                        outcome[app] = why
        for step in steps:  # left with an older copy for want of its command here: behind, not up to date
            if step.behind and step.app not in outcome:
                outcome[step.app] = step.behind
        self._behind(receipt, steps, outcome)
        return failed, changed

    def _behind(self, receipt: dict[str, Any], steps: list[Any], outcome: dict[str, str | None]) -> None:
        """The receipt's record of the apps behind (``BEHIND``) brought up to this run: an app whose step to give it
        this release's text failed (``outcome``: why) recorded with the release, why and when; one that got it, or
        whose copy the plan left as it is (up to date, or a store's), taken out. An app this run did not plan for
        (``--only``) keeps what it had."""
        behind = {app: row for app, row in (receipt.get(BEHIND) or {}).items() if isinstance(row, dict)}
        for step in steps:
            if step.app not in outcome and step.action == "leave" and step.subject != self.providers.NEED_NODE:
                behind.pop(step.app, None)
        for app, why in outcome.items():
            if why is None:
                behind.pop(app, None)
            else:
                behind[app] = {"release": self.release, "why": why, "at": self.providers.stamp()}
        if behind:
            receipt[BEHIND] = behind
        else:
            receipt.pop(BEHIND, None)

    def _record(self, receipt: dict[str, Any], registered: dict[str, Any]) -> None:
        """Step 7: the receipt kept, with what this run did; written whenever none was here, since its presence
        says the install command ran here (the default channel's updater)."""
        providers = self.providers
        launcher = registered["launcher"]
        kept = self._receipt()
        if self.actions or self.stopped or launcher["written"] or kept is None \
                or (kept or {}).get(BEHIND) != receipt.get(BEHIND):
            receipt.update({"release": self.release, "updated": providers.stamp()})
            receipt["actions"] = list(receipt.get("actions") or []) + self.actions
            if self.stopped:
                receipt["stopped"] = list(receipt.get("stopped") or []) + self.stopped
            if launcher["written"]:
                receipt["launcher"] = {"path": launcher["path"], "written": True, "at": providers.stamp()}
            self._keep(receipt)

    def _telemetry_into(self, verified: dict[str, Any]) -> None:
        try:
            verified["telemetry"] = self._telemetry()
        except Exception as error:  # noqa: BLE001 - the notice never fails the setup
            self.say(f"telemetry unknown ({type(error).__name__}: {error})")

    # --- uninstall ------------------------------------------------------------------------------

    def uninstall(self) -> int:
        providers = self.providers
        from cad.engine import places
        from cad_server._internal import installations, pointers, versions
        from cad.engine.places import legacy_cache_dir

        receipt = self._receipt()
        apps = providers.detect(self.machine, folder=self.folder)
        steps = providers.uninstall_plan(apps, receipt, self.only or None, self.machine, folder=self.folder)
        extra: list[dict[str, Any]] = []
        proxy = installations.proxy_path()
        status = installations.proxy_status(proxy)
        # The cad command goes with a whole uninstall when it is text-to-cad's: its first lines (on Windows,
        # cad.exe's __main__.py's) carry the proxy's mark, or it is a cad.cmd an earlier revision wrote. A
        # file of that name that is not (``uv tool install``'s) stays.
        earlier = installations.earlier_command()
        ours = status in (installations.OK, installations.STALE, installations.NEWER) or earlier is not None
        if status == installations.MISSING and earlier is not None:
            proxy = earlier
        whole = not self.only
        purge = bool(self.args.purge)
        # The named channels: a store delivered each, and each stays (``--purge`` aside), with its version.
        channels = [pointer for pointer in pointers.listing() if pointer.channel is not None]
        default = pointers.read(None)
        kept_by = {pointer.version: pointer.channel for pointer in channels}
        # The versions whose code (with --purge, whole folders) a whole uninstall removes.
        names = versions.folders() if purge else [default] if default and default not in kept_by else []
        launcher = whole and ours and (purge or not channels)
        if launcher:
            extra.append({"app": "command", "label": "command", "action": "remove",
                          "subject": f"{providers.shown(proxy, self.machine)} (text-to-cad's)"})
        elif whole and ours:
            extra.append({"app": "command", "label": "command", "action": "leave",
                          "subject": f"{providers.shown(proxy, self.machine)}: {self._still_used(channels)}"})
        elif whole and status == installations.FOREIGN:
            extra.append({"app": "command", "label": "command", "action": "leave",
                          "subject": f"{providers.shown(proxy, self.machine)}: not text-to-cad's"})
        if whole:
            extra.append({"app": "engine", "label": "engine", "action": "stop",
                          "subject": "the default channel's server (`cad stop`)" if not purge
                          else "every version's server"})
            if default is not None:
                extra.append({"app": "default", "label": "default", "action": "remove",
                              "subject": f"the default channel (on text-to-cad {default}) and the record clients of "
                                         "0.11.10 and earlier read"})
                if default in kept_by and not purge:
                    extra.append({"app": "version", "label": "version", "action": "leave",
                                  "subject": f"text-to-cad {default}: the {kept_by[default]} channel is on it"})
            for name in names:
                extra.append({"app": "version", "label": "version", "action": "remove",
                              "subject": providers.shown(str(places.version_dir(name)), self.machine) if purge else
                              f"the code of text-to-cad {name} (its data -- settings, Recents, documents' records -- "
                              "stays for a later install; --purge removes it)"})
            for pointer in channels if not purge else ():
                extra.append({"app": "channel", "label": "channel", "action": "leave",
                              "subject": f"{pointer.channel}, on text-to-cad {pointer.version}: its store delivered it"})
            from cad_server._internal import releases

            if releases.listing():
                extra.append({"app": "releases", "label": "releases", "action": "remove",
                              "subject": providers.shown(str(releases.root()), self.machine)})
            if os.path.lexists(self.folder):
                extra.append({"app": "plugin", "label": "plugin folder", "action": "remove",
                              "subject": providers.shown(str(self.folder), self.machine)})
        state, cache = self._state(), Path(legacy_cache_dir())  # the versions' own caches are in the state folder
        if purge:
            extra.append({"app": "folders", "label": "folders", "action": "remove",
                          "subject": f"{providers.shown(state, self.machine)} and {providers.shown(cache, self.machine)}"})
        title = ("text-to-cad: cad uninstall takes back what earlier runs did, newest first:" if receipt else
                 "text-to-cad: cad uninstall finds no record of an earlier run, so it takes out every copy of "
                 "text-to-cad here:")
        self._plan_lines(title, apps, steps, extra)
        if self.args.dry_run:
            self.say("Dry run: nothing was changed.")
            return self._result(steps, extra, None, [], 0)
        # The plan above is what it does: asked of a person at a terminal, else said yes to by --yes
        # (``cad_server._internal.consent``).
        from cad_server._internal.cli_errors import Failure, write
        from cad_server._internal.consent import confirm, retry

        try:
            confirm("taking text-to-cad out" + (f" of {', '.join(self.only)}" if self.only else " of this computer")
                    + (" and removing its state and cache folders" if purge else ""),
                    "Take text-to-cad out as planned?", yes=bool(self.args.yes), as_json=bool(self.args.json),
                    command=retry(self.prog, self.argv),
                    preview=["This cannot be undone: --purge removes every installed version of text-to-cad, a "
                             "store's among them, and its state folder (your settings, the documents' records, "
                             "Recents) and its cache folder."] if purge else [])
        except Failure as failure:
            return write(failure, prog=self.prog, as_json=bool(self.args.json))
        failed, changed = False, set()
        state.mkdir(parents=True, exist_ok=True)
        with versions.install_lock(waiting=lambda: self.say("waiting for another cad setup or uninstall to finish")):
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
                failed = self._remove_command(proxy) or failed
            elif whole and ours:
                self.say(f"command  {providers.shown(proxy, self.machine)} stays: {self._still_used(channels)}")
            if whole:
                if purge:
                    # Read again under the lock: the folders and the channels there now, one that came while the
                    # question waited among them.
                    names = versions.folders()
                    channels = [pointer for pointer in pointers.listing() if pointer.channel is not None]
                # The channels first, then the servers: a thread's transport whose server stops finds its channel gone
                # and starts nothing again (``cad_mcp.engine.stale``).
                failed = self._take_channels_off(default, names, channels, purge) or failed
                failed = self._stop() or failed
                failed = self._stop_flat(names) or failed
                failed = self._remove_versions(names, purge) or failed
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
        if purge:
            failed = self._purge(state, cache) or failed
        restart = self._restart(apps, changed, "Next, restart to unload it:")
        return self._result(steps, extra, None, restart, 1 if failed else 0)

    @staticmethod
    def _still_used(channels: list[Any]) -> str:
        """Why the ``cad`` command stays: which channels are still installed, on which version, and that their
        store's plugin runs it; ``--purge`` removes them too. (Removing a store's plugin in its app leaves its channel
        installed: only ``cad doctor --prune``, after 30 days unused, or ``--purge`` takes a channel out.)"""
        named = ", ".join(f"{pointer.channel} (on text-to-cad {pointer.version})" for pointer in channels)
        many = len(channels) != 1
        return (f"the {named} channel{'s are' if many else ' is'} still installed, and {'their' if many else 'its'} "
                "store's copy of the plugin runs this command; `cad uninstall --purge` removes "
                f"{'them' if many else 'it'} too")

    def _take_channels_off(self, default: str | None, names: list[str], channels: list[Any], purge: bool) -> bool:
        """The channels a whole uninstall takes off this computer, before any server is asked to stop: the default
        channel's pointer and the mirror 0.11.10 and earlier read (``installations/current`` and the records naming a
        version, or the default's), and with ``purge`` every named channel's pointer (``channels``) too. A thread's
        transport that notices its server stopping then finds its channel gone and starts nothing again
        (``cad_mcp.engine.stale``); else it would start the server again at once, from the code being removed. Run under
        the install lock, so no server's tending decides on the pointers meanwhile (``versions.retiring``). True when a
        pointer could not be removed (``_unlink``: said, and the run goes on)."""
        from cad.engine import places
        from cad_server._internal import installations, pointers

        failed = False
        if self._unlink(self._folder().path(pointers.DEFAULT), "default "):
            if default is not None:
                self.say(f"default  removed the default channel (on text-to-cad {default})")
        else:
            failed = True
        inside = os.path.normcase(os.path.realpath(places.versions_dir())).rstrip(os.sep) + os.sep
        for record in installations.records():
            if os.path.normcase(os.path.realpath(record["prefix"])).startswith(inside) \
                    or (default is not None and record["version"] == default):
                installations.forget(record["version"])
        if installations.current_version() in (*names, default):
            installations.state().remove(installations.CURRENT)
        for pointer in channels if purge else ():
            if not self._unlink(pointer.path, "channel "):
                failed = True
                continue
            pointers.forget(pointer.channel)  # its last-use stamp with it
            self.say(f"channel  removed the {pointer.channel} channel (on text-to-cad {pointer.version})")
        return failed

    def _unlink(self, path: Path, label: str) -> bool:
        """The pointer file ``path`` removed, tried again for ``POINTER_SECONDS`` while the system refuses it (on Windows,
        while a launcher has it open to read): whether it is gone. One that stays is said, with the system's words, under
        ``label``; never a traceback that ends the run."""
        import time

        deadline = time.monotonic() + POINTER_SECONDS
        while True:
            try:
                path.unlink()
                return True
            except FileNotFoundError:
                return True
            except OSError as error:
                if not isinstance(error, PermissionError) or time.monotonic() >= deadline:
                    self.say(f"{label} {self.providers.shown(str(path), self.machine)} could not be removed: "
                             f"{error.strerror or error}")
                    return False
            time.sleep(0.05)

    def _remove_versions(self, names: list[str], purge: bool) -> bool:
        """The versions ``names`` taken out, their channels taken off already (``_take_channels_off``), each one's
        server stopped first: the default channel's version's code, its data kept for a later install
        (``versions.remove_code``); with ``purge``, every version whole. Run under the install lock. True when a
        version could not be removed (something still runs from it, or the system refused it: said, with what the
        person can do, ``_left``); the code this command itself runs from, which Windows refuses to remove while it
        runs, is said the same way and is no failure."""
        from cad.engine import places
        from cad_server._internal import versions

        failed = False
        for name in names:
            # Its lock is awaited whether or not the stop is answered: a server this command already asked to stop
            # (``_stop``) answers nothing more on its way out, and holds its lock until its workers are gone. Then the
            # end of its processes: a server lets its lock go, and removes it, a moment before its own process and its
            # workers' have ended, and the removal below looks once (seen on Linux: the look came first, and the code
            # was left). This command does not count: typed in a terminal, it runs from the folder it removes.
            if versions.endpoint(name).lock.exists():  # a server there, or on its way out
                versions.ask(name, {"op": "stop"})
                versions.gone(name, besides=os.getpid())
            else:
                versions.quiet(places.version_dir(name), besides=os.getpid())
            said: list[str] = []
            why: list[versions.Refusal] = []
            # Without --purge the version's data stays for a later install (``versions.remove_code``). A person waits on
            # this run: a rename the system refuses is tried again for a while (on Windows, a stopped server's process
            # keeps its files a moment), unless this command runs from the folder (``versions.runs_from``).
            done = (versions.remove_now if purge else versions.remove_code)(
                name, told=said.append, wait=versions.QUIET_SECONDS, why=why)
            if done in ("removed", "absent"):
                for line in said:
                    self.say(f"version  {line}")
                self.actions.append({"app": "version", "action": "remove", "kind": "remove",
                                     "path": str(places.version_dir(name) if purge else places.code_dir(name)),
                                     "ok": True, "at": self.providers.stamp()})
                continue
            refusal = why[0] if why else None
            # Refused because this command runs from it (``cad uninstall`` typed on Windows): all else is done, and
            # deleting the folder once it has ended finishes it. Anything else that stays is a failure.
            failed = failed or not (refusal is not None and refusal.here)
            self.say(f"version  {self._left(name, done, purge, refusal)}")
        return failed

    def _left(self, name: str, done: str, purge: bool, refusal: Any = None) -> str:
        """What a version this uninstall could not remove (``done``: ``in use``, ``connected``, ``refused``) leaves, and
        what the person can do, in one line. Without ``purge`` its code stays in its folder and its data is kept:
        deleting that code folder once nothing runs from it finishes the uninstall, as a later install would (the same
        release takes the code it finds, a newer one carries the data in and removes the folder: ``versions.fate``).
        With ``purge``, the version's folder. Why, as it is: a refusal's own words (``versions.Refusal``: the lock, or
        the system's refusal of the rename, and that this command runs from it where it does); else what still runs,
        named where the system lists it (``releases.processes``), or its server, where its lock is held
        (``connected``). Never "run this again": the ``cad`` command may be gone by now, and a second uninstall would
        find no channel on this version; nor a sweep, which no one may run."""
        from cad.engine import places
        from cad_server._internal import releases

        shown = lambda path: self.providers.shown(str(path), self.machine)  # noqa: E731
        found = releases.processes(places.version_dir(name), besides=os.getpid()) if refusal is None else []
        if refusal is not None:
            what = refusal.words
        elif found:
            ids = ", ".join(str(pid) for pid in found[:-1]) + (" and " if len(found) > 1 else "") + str(found[-1])
            what = f"process{'es' if len(found) > 1 else ''} {ids} still run{'' if len(found) > 1 else 's'} from it"
        elif done == "connected":
            what = "its server still runs"
        else:
            what = "a process still runs from it"
        once = "once this command has ended" if refusal is not None and refusal.here else "once nothing runs from it"
        if purge:
            return f"{shown(places.version_dir(name))} stays: {what}. Delete that folder {once}"
        return (f"the code of text-to-cad {name} stays, in {shown(places.code_dir(name))}: {what}. Its data is kept. "
                f"Delete that code folder {once} to finish the uninstall; a later install of text-to-cad {name} uses it "
                "instead, and of a newer release removes it")

    def _remove_command(self, proxy: str) -> bool:
        """The cad command removed, with its Python on Windows (``installations.remove_proxy``): True when it
        could not be. A ``cad.exe`` that runs this uninstall is set aside, no command any more, and said."""
        from cad_server._internal import installations

        providers = self.providers
        try:
            removed, left = installations.remove_proxy()
        except OSError as error:
            self.say(f"command  {providers.shown(proxy, self.machine)} could not be removed: {error}")
            return True
        for path in removed:
            self.say(f"command  removed {providers.shown(path, self.machine)}")
            self.actions.append({"app": "command", "action": "remove", "kind": "remove", "path": path, "ok": True,
                                 "at": providers.stamp()})
        for path in left:
            self.say(f"command  {providers.shown(path, self.machine)} runs this uninstall: set aside, delete it "
                     "once this ends")
        return False

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
        one of them: what the device runs from goes with an uninstall. One a process still runs from stays, said
        (``releases.running``). True when one could not be removed whole (a process runs from it; on Windows, the
        folder this command runs from)."""
        import shutil

        from cad_server._internal import installations, releases

        root = releases.root()
        if not root.exists():
            return False
        busy = [entry for entry in sorted(root.iterdir()) if entry.is_dir() and not entry.is_symlink()
                and releases.running(entry, besides=os.getpid())]
        for folder in busy:
            self.say(f"releases {self.providers.shown(str(folder), self.machine)} stays: a process still runs from it "
                     "(delete that folder once nothing runs from it)")
        for record in installations.records():
            if installations._same_place(os.path.dirname(record["prefix"]), root) and not any(
                    installations._same_place(record["prefix"], folder) for folder in busy):
                installations.forget(record["version"])
                if installations.current_version() == record["version"]:
                    installations.state().remove(installations.CURRENT)
        if busy:
            for entry in root.iterdir():
                if entry not in busy:
                    (shutil.rmtree(entry, ignore_errors=True) if entry.is_dir() and not entry.is_symlink()
                     else entry.unlink(missing_ok=True))
            return True
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

    def _stop_flat(self, names: list[str]) -> bool:
        """Whoever holds the flat door of 0.11.10 and earlier -- a server of those releases still running, as while
        it drains after an update, or the server of a version this uninstall removes (``names``) -- asked to stop, and
        its lock awaited (``versions.STOP_SECONDS``): nothing it runs from is removed under it. A version that stays (a
        store's channel is on it) is left alone, unsaid: with the default channel gone, its server takes the flat door
        at its next tending (``versions.flat``), and the plan says it stays. True when one still runs."""
        from cad.engine import client
        from cad_server._internal import versions

        holder = versions.ask_flat({"op": "pid"}, seconds=versions.SERVES_SECONDS)
        if holder is None:
            return False
        pid = holder.get("pid")
        for kept in (name for name in versions.folders() if name not in names):
            if type(pid) is int and (versions.ask(kept, {"op": "pid"}, seconds=versions.SERVES_SECONDS)
                                     or {}).get("pid") == pid:
                return False
        versions.ask_flat({"op": "stop"})
        try:
            gone = client.wait_gone(timeout=versions.STOP_SECONDS, endpoint=versions.flat_endpoint())
        except ConnectionError:
            gone = False
        if not gone:
            self.say(f"engine   the server at {versions.flat_endpoint().address} did not stop: what it runs from stays")
        return not gone

    def _running(self, state: Path, cache: Path) -> list[str]:
        """What still runs from the state or cache folder, in words: a version's server, the flat door's, or any
        process (this one aside: ``cad uninstall`` runs from a version it removes)."""
        from cad_server._internal import releases, versions

        found = [f"text-to-cad {name}'s server" for name in versions.folders() if versions.serves(name)]
        if versions.ask_flat({"op": "pid"}, seconds=versions.SERVES_SECONDS) is not None:
            found.append(f"the server at {versions.flat_endpoint().address}")
        for folder in (state, cache):
            if folder.is_dir() and releases.running(folder, besides=os.getpid()):
                found.append(f"a process running from {self.providers.shown(str(folder), self.machine)}")
        return found

    def _purge(self, state: Path, cache: Path) -> bool:
        """The state and cache folders removed, where nothing runs from them any more (``_running``): else nothing of
        them is, said. True when they could not be removed."""
        import shutil

        shown = self.providers.shown
        running = self._running(state, cache)
        if running:
            self.say(f"folders  {shown(state, self.machine)} and {shown(cache, self.machine)} stay: "
                     f"{'; '.join(running)} still runs. Delete those two folders once nothing runs from them")
            return True
        for folder, ours in ((state, STATE_OURS), (cache, CACHE_OURS)):
            held = {entry.name for entry in folder.iterdir()} - {LOCK} if folder.is_dir() else set()
            if held and not held & ours:
                with contextlib.suppress(OSError):
                    (folder / LOCK).unlink()  # only the lock this uninstall took there
                self.say(f"folders  left {shown(folder, self.machine)}: it holds nothing text-to-cad made")
                continue
            shutil.rmtree(folder, ignore_errors=True)
            self.say(f"folders  removed {shown(folder, self.machine)}" if not folder.exists()
                     else f"folders  {shown(folder, self.machine)} could not be removed whole")
        return False


def _why(records: list[dict[str, Any]]) -> str:
    """Why an app's step failed, in one line, from what it did (``providers.apply``'s records): the last line the
    failing command or edit said, else its exit status."""
    for record in reversed(records):
        if record.get("ok") is False:
            lines = [line.strip() for line in str(record.get("output") or "").splitlines() if line.strip()]
            if lines:
                return lines[-1][:300]
            if record.get("code") is not None:
                return f"{Path(str((record.get('command') or ['it'])[0])).name} exited {record['code']}"
    return "it failed"


def refresh_copies(told: Any) -> tuple[bool, list[dict[str, Any]]]:
    """The copies the apps keep of the plugin folder brought to it, after ``cad plugin --refresh`` wrote it
    again (``Installer.refresh``): ``(ok, the steps run)``, each line said to ``told``."""
    args = argparse.Namespace(dry_run=False, json=False, only=None, no_telemetry=False)
    return Installer(args, [], 0, "default").refresh(told)


if __name__ == "__main__":
    raise SystemExit(main())
