"""BRIDGE-ONLY: ``cad setup`` (hidden, undocumented) and what carries a computer that a release of 0.10.0 to 0.11.11
updated onto this one. All of it goes in one change once those releases are gone, with install mode in
``cad_server._internal.install_script`` and the ``Tending`` the server holds (``cad_server.engine.daemon``).

The updaters of 0.10.0 to 0.11.11 cannot be changed. They bring a newer release X the old way, and the server then
takes the computer onto the one-cad design by itself:

1. The old updater makes ``<state>/releases/X`` (``cad-server==X``, which installs cad X) and runs its ``cad setup
   --engine-update``, an automatic update first with ``CAD_UPDATE_PREPARE=1`` (nothing to prepare: 0).
2. ``--engine-update`` (``engine_update``) writes the record the old switch starts a server by,
   ``installations/X.json`` naming this environment, owes install mode (``install_script.owe``), keeps how X arrived
   (``arrival.keep``) and exits 0. Nothing else: not ``installations/current``, which the switch reads afterwards as
   the release to go back to, not the ``cad`` command, no server.
3. The old switch points ``current`` at X and starts X's server from ``releases/X`` (``python -P -m
   cad_server._internal.engine_daemon``); where it does not answer, it goes back, and the owed run stays inert
   (``current`` never names X).
4. X's server, five minutes after it started with ``current`` naming X, runs the hosted install command in install
   mode (``install_script``): cad as a uv tool, our plugin in every agent app, both switches on.
4b. Where nothing is owed (a store-only computer, below), or install mode's attempt ended without installing cad, X's
   server installs cad globally itself after the same five minutes, once nothing is in flight (``Tending.carry``):
   ``uv tool install`` on a thread (``tool_install.install``, which sets the old ``cad`` command aside), unless a
   global cad is there already; then step 5. Where that moves nothing, it is tried again a day later, and at each
   start.
5. Once a report said cad was installed, or step 4b ran, and nothing is in flight (``Tending``, ``move``):
   ``installations/current`` and its record name the global cad's environment (a uv tool, or pipx's), and a detached
   helper that is not cad (``auto_update_helper``) stops this server and starts the global cad's (``cad server
   start``). From then on it is a normal computer, whose server updates itself.
6. Every server of a global install, as it starts (``follow``), points ``current`` and its record at its own
   environment, so a client of 0.11.11 or earlier that finds no server (a store's copy that lags, the library in a
   person's own Python, the old ``cad`` command) starts it, and never registers its own release again.
7. A global install's server on a computer where our setup ran before (``ours``) and the person's switch
   ``plugin.auto_update`` was never set -- the new cad arrived by the uv line, typed by a skill or a person, or by an
   app's server line --, at its first quiet tending (``once``): the switch turned on, then the install command run
   once, detached. Not while install mode is owed: that run is the ``Carrier``'s.

On Windows the same holds for 0.10.1 to 0.11.11. 0.10.0 on Windows (``_alone``) keeps its state in the local
application data, apart from this release's, so its switch could only go back: there ``--engine-update`` takes over
(``_take_over``): 0.10.0's server stopped by its own stop command first (where it does not stop, nothing changes), its
data moved out of the local application data once (``places.adopt_earlier``), the records pointed at this release in
both state folders, install mode owed, and this release's server started, serving pages on the port and with the token
it took in.

Plain ``cad setup`` is what ``cad update`` typed on 0.10.0 to 0.11.11 runs of the new release, and what the install
script of those releases ends in (a copy someone kept, or the hosted one until the site is redeployed): the install
command in install mode, in the foreground; its exit status. Typed on 0.10.0 on Windows (``_alone``), it first takes
0.10.0's data over as ``--engine-update`` does (``_adopt``), before anything writes in this release's state folder;
where 0.10.0's server does not stop, nothing of it moves. It starts no server.

Never on a computer that arrives from one of those releases (``SHIPPED``: the release ``arrival.came_from`` names) and
whose agent apps got text-to-cad from a store alone (``ours``): there install mode would add our plugin to apps the
person never asked us into. Everywhere else that is not ours -- no earlier release, or a later one such as a uv tool's
cad that ``follow`` points ``current`` at, or one that is no plain ``X.Y.Z`` -- only an install script reaches plain
``cad setup``, the person asked for an install, and the install command runs. Such a store-only computer's old release
still reaches ``--engine-update``: its automatic update runs where its server was started by a ``cad`` command rather
than by the store's server line (the line's ``CAD_AUTO_UPDATED=1`` reaches only the server it starts), and a typed
``cad update`` runs plain ``cad setup``. Ours is told by what 0.8 to 0.11.11's own setup leaves once it has put our
plugin in the apps -- the install command's, an update button's or an automatic update's alike --, and nothing else
writes: ``install-receipt.json`` or the plugin folder ``plugin/`` in the state folder (or 0.10.0's on Windows). On
such a computer, where neither is there, cad alone moves: the record the switch starts this release's server by is
written (and ``current`` pointed at it by a plain ``cad setup``), and nothing is owed; that server then installs cad
globally (step 4b), and the store's next copy brings the rest. An old install script run there cannot be told from a
typed ``cad update``, and gets cad alone too.

Nothing here deletes anything of a past release: ``releases/`` stays until ``cad cache prune``. The module names
``cad_server._internal.engine_daemon`` and ``cad_server._internal.proxy`` stay too: shipped releases start them.

Exit status of ``--engine-update``: 0 done; 1 failed (the updater stays on its own release).
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Sequence
from typing import Any

DEFAULT_PROG = "cad setup"
# Set by the updater of 0.11.x for an automatic update's first run of ``--engine-update``; it runs it again, without
# it, once its server is idle.
PREPARE_ENV = "CAD_UPDATE_PREPARE"
# The helper's record of the move to the uv tool's server, in the state folder.
MOVE_RECORD = "handover-move.json"
# How long a server of 0.10.0 is given to say what it is, and its own stop to run.
ASK_SECONDS = 5.0
STOP_SECONDS = 60.0
# The shipped releases whose updaters and install scripts reach this bridge, first and last.
SHIPPED = ((0, 10, 0), (0, 11, 11))
# How long step 4b's install may take (``tool_install.install``).
CARRY_SECONDS = 600.0


def build_parser(prog: str = DEFAULT_PROG):
    import argparse

    from cad_server._internal.cli_parser import parser as command_parser

    parser = command_parser(prog=prog, allow_abbrev=False,
                            description="Run the install command once more.")
    parser.add_argument("--engine-update", action="store_true", help=argparse.SUPPRESS)
    return parser


def main(argv: Sequence[str] | None = None, prog: str = DEFAULT_PROG) -> int:
    args = build_parser(prog).parse_args(argv)
    return engine_update() if args.engine_update else setup()


def _say(line: str) -> None:
    """A line on stderr; never a failure where no one reads it any more (an updater that went)."""
    try:
        sys.stderr.write(f"cad: {line}\n")
        sys.stderr.flush()
    except (OSError, ValueError):
        pass


def _name() -> str:
    """The release this process is: the one it is told it runs as (a development version), else its own."""
    import cad_server
    from cad.engine import places

    return os.environ.get(places.INSTALLATION_ENV) or cad_server.__version__


def _ended(name: str, route: str, came: str | None, failed: bool, *, first: bool = False) -> int:
    """The run's end counted (``arrival.setup_ended``): its exit status."""
    from cad_server._internal import arrival

    arrival.setup_ended(name, route, came, arrival.FAILED if failed else arrival.OK, "other" if failed else None,
                        first=first)
    return 1 if failed else 0


def setup() -> int:
    """Plain ``cad setup``: the install command in install mode, its output this command's (see the module). Where an
    install command cad started runs it (``install_script.BY_CAD_ENV``), that command is an earlier release's script,
    which would run this again, and so on: nothing runs, a failure."""
    from cad_server._internal import arrival, install_script

    name = _name()
    came = arrival.came_from(name)
    if os.environ.get(install_script.BY_CAD_ENV) == "1":
        _say("the install command online is not yet this release's, so nothing was installed: run the install command "
             "again in a few minutes")
        return _ended(name, arrival.SETUP, came, True)
    if _alone():
        _adopt(name)
    if _shipped(came) and not ours():
        from cad_server._internal import installations

        try:
            installations.register(name)
            installations.point(name)
        except (OSError, ValueError) as error:
            _say(f"cad {name} could not be set up: {error}")
            return _ended(name, arrival.SETUP, came, True)
        _say(f"cad {name} runs from the next start of the cad server")
        return _ended(name, arrival.SETUP, came, False)
    command = install_script.installer()
    if not command:
        return 0
    try:
        code = subprocess.call(command, env=install_script.environment(report=None), stdin=subprocess.DEVNULL)
    except OSError as error:
        _say(f"the install command could not start: {error}")
        code = 1
    _ended(name, arrival.SETUP, came, code != 0)
    return code


def engine_update() -> int:
    """``cad setup --engine-update`` (see the module, steps 1 and 2, and 0.10.0 on Windows)."""
    from cad_server._internal import arrival, install_script, installations

    name = _name()
    if os.environ.get(PREPARE_ENV) == "1":
        return 0
    came = arrival.came_from(name)
    if _alone():
        return _take_over(name, came)
    try:
        installations.register(name)
        if ours():
            install_script.owe(name)
    except (OSError, ValueError) as error:
        _say(f"cad {name} could not take over: {error}")
        return _ended(name, arrival.UPDATER, came, True)
    return _ended(name, arrival.UPDATER, came, False, first=_keep(name, came))


def ours() -> bool:
    """Whether text-to-cad's own setup (0.8 to 0.11.11) ever put our plugin in this computer's agent apps: its
    receipt or its plugin folder in the state folder, or in 0.10.0's on Windows (see the module)."""
    from cad.engine import places

    return any(folder is not None and ((folder / "install-receipt.json").is_file() or (folder / "plugin").is_dir())
               for folder in (places.state_dir(), places.appdata_state_dir()))


def _shipped(came: str | None) -> bool:
    """Whether ``came`` is one of the shipped releases ``SHIPPED`` spans, a plain ``X.Y.Z``."""
    from cad_server._internal.auto_update import release

    found = release(came)
    return found is not None and SHIPPED[0] <= found <= SHIPPED[1]


def _keep(name: str, came: str | None) -> bool:
    from cad_server._internal import arrival

    try:
        return arrival.keep(name, arrival.UPDATER, came)
    except OSError:
        return False


# --- 0.10.0 on Windows ------------------------------------------------------------------------------------------


def _alone() -> bool:
    """Whether the updater that runs this ``--engine-update`` cannot switch the computer to this release: 0.10.0 on
    Windows, whose state -- the records its switch starts a server by -- is in the local application data
    (``places.appdata_state_dir``). Told by where its folder for this release is: its ``releases`` there."""
    from cad.engine import places

    folder = places.appdata_state_dir()
    if folder is None:
        return False
    inside = os.path.normcase(os.path.realpath(folder / "releases")).rstrip(os.sep) + os.sep
    return os.path.normcase(os.path.realpath(sys.prefix)).startswith(inside)


def _take_over(name: str, came: str | None) -> int:
    """``--engine-update`` for 0.10.0 on Windows (see the module): its exit status."""
    from cad.engine import places
    from cad_server._internal import arrival, install_script, installations

    if not stop_appdata(_say):
        _say(f"cad {name} did not take over: the server of cad-server 0.10.0 did not stop, and keeps what it has")
        return _ended(name, arrival.UPDATER, came, True)
    try:
        places.adopt_earlier()
        found = installations.targets()
        _point(name, found, take_over=True)
        if ours():
            install_script.owe(name)
    except (OSError, ValueError) as error:
        _say(f"cad {name} could not take over: {error}")
        return _ended(name, arrival.UPDATER, came, True)
    first = _keep(name, came)
    _serve(name)
    return _ended(name, arrival.UPDATER, came, False, first=first)


def _adopt(name: str) -> None:
    """Plain ``cad setup`` run by 0.10.0's typed ``cad update`` on Windows (see the module): 0.10.0's server stopped by
    its own stop, its data moved into this release's state folder (``places.adopt_earlier``, which skips a name the
    folder has already: so before the install command writes there) and the records pointed at this release in both
    state folders. Where 0.10.0's server does not stop, nothing moves. Never a failure of the command."""
    from cad.engine import places
    from cad_server._internal import installations

    if not stop_appdata(_say):
        _say(f"cad {name} left the data of cad-server 0.10.0 where it is: its server did not stop")
        return
    try:
        places.adopt_earlier()
        _point(name, installations.targets(), take_over=True)
    except (OSError, ValueError) as error:
        _say(f"cad {name} could not take over the data of cad-server 0.10.0: {error}")


def _serve(name: str) -> None:
    """This release's server started from this environment (``client.start``) and asked to serve pages, on the port
    and with the token it took in, so a page 0.10.0 served finds it there. Never a failed run. Its environment is this
    process's without what only this run goes by (``install_script.environment``), computed before ``os.environ`` is
    replaced: from an empty one, Windows' Python could not open a socket, and the server never started."""
    from cad.engine import client
    from cad_server._internal import install_script

    saved = dict(os.environ)
    try:
        served = {key: value for key, value in install_script.environment(report=None).items()
                  if key not in ("UV_NO_MODIFY_PATH", install_script.BY_CAD_ENV)}
        os.environ.clear()
        os.environ.update(served)
        client.start()
        client.request({"op": "http"}, start=False)
    except (ConnectionError, OSError, ValueError) as error:
        _say(f"cad {name}'s server is not running: {error}")
    finally:
        os.environ.clear()
        os.environ.update(saved)


def stop_appdata(told: Callable[[str], None]) -> bool:
    """0.10.0's servers on Windows stopped by 0.10.0's own ``cad stop --json``, found by its installation records in
    the local application data, run in its own environment with its telemetry off: whether every one held (ran and
    exited 0, which for 0.10.0 means its server is gone), or there was none. 0.10.0's stop stops whatever answers at its
    port file, which every later server writes a copy of its own to (``daemon._mirror``): it runs only where nothing
    answers there, or 0.10.0's own server does (``_appdata_serving``)."""
    import json

    from cad_server._internal import installations

    environment = {key: value for key, value in os.environ.items() if key not in ("PYTHONPATH", "PYTHONHOME")}
    environment.update({"CADGEN_TELEMETRY": "0", "CAD_TELEMETRY": "0"})
    held, serving = True, []
    for record in installations.appdata():
        console = record.get("cad")
        if not (isinstance(console, str) and os.path.isfile(record["python"]) and os.path.isfile(console)):
            continue
        if not serving:  # asked once, where there is a 0.10.0 to stop
            serving.append(_appdata_serving())
        if serving[0] is not None and not installations._same_place(serving[0], record["prefix"]):
            continue  # another release's server answers there: never stopped by 0.10.0's stop
        try:
            done = subprocess.run([console, "stop", "--json"], env=environment, stdin=subprocess.DEVNULL,
                                  capture_output=True, text=True, encoding="utf-8", errors="replace",
                                  timeout=STOP_SECONDS)
        except (OSError, subprocess.SubprocessError) as error:
            told(f"cad-server {record['version']}'s `cad stop` could not run ({error}): its server may still run")
            held = False
            continue
        if done.returncode != 0:
            told(f"cad-server {record['version']}'s `cad stop` failed (exit status {done.returncode}): its server "
                 "may still run")
            held = False
            continue
        try:
            stopped = json.loads(done.stdout).get("stopped")
        except (ValueError, AttributeError):
            stopped = None
        if stopped:
            told(f"stopped cad-server {record['version']}'s server (its own `cad stop`)")
    return held


def _appdata_serving() -> str | None:
    """The environment of the server that answers where 0.10.0's clients look for one on Windows (the port file in
    ``places.appdata_engine_dir``; where ``CAD_ENGINE_DIR`` names the engines' folder, its own port file), as its
    ``status`` says (``prefix``); None where none answers."""
    import threading

    from cad.engine import client, places

    folder = places.appdata_engine_dir()
    if folder is None and places.WINDOWS and os.environ.get("CAD_ENGINE_DIR"):
        folder = places.engine_dir()
    if folder is None:
        return None
    door = folder / f"{places.NAME}.port"
    answers: list = []

    def ask() -> None:
        try:
            connection = client._connect(door)
            if connection is not None:
                answers.append(client._exchange(connection, {"op": "status", "internal": True}))
        except (OSError, ValueError, ConnectionError):
            pass

    asking = threading.Thread(target=ask, daemon=True)
    asking.start()
    asking.join(ASK_SECONDS)
    prefix = answers[0].get("prefix") if answers and isinstance(answers[0], dict) else None
    return prefix if isinstance(prefix, str) and prefix else None


# --- the records old clients start a server by ------------------------------------------------------------------


def _appdata_ours():
    """0.10.0's state folder on Windows as a ``Folder`` where its ``installations/current`` names a release after
    0.10 (one ``_take_over`` pointed it at), else None."""
    from cad.engine import places
    from cad_server._internal import installations
    from cad_server.engine.registry import Folder

    folder = places.appdata_state_dir()
    if folder is None:
        return None
    named = installations.current_version(Folder(folder))
    return Folder(folder) if named is not None and _later(named, "0.10.99") else None


def _point(version: str, found: tuple[str, str, str] | None, *, take_over: bool = False) -> None:
    """``installations/<version>.json`` naming ``found`` (console script, python, environment) and ``current`` naming
    it, in the state folder and in 0.10.0's where ours (``_appdata_ours``), or by a take-over. ``OSError``,
    ``ValueError``."""
    from cad.engine import places
    from cad_server._internal import installations
    from cad_server.engine.registry import Folder

    appdata = places.appdata_state_dir() if take_over else None
    for folder in (Folder(places.state_dir()), Folder(appdata) if appdata is not None else _appdata_ours()):
        if folder is not None:
            installations.register(version, found, folder)
            installations.point(version, folder)


def _later(one: str, other: str) -> bool:
    from cad_server._internal.install_script import _later as later

    return later(one, other)


def follow(told: Callable[[str], None]) -> bool:
    """Step 6 (see the module): where this server is a global install's, ``current`` and its record pointed at its
    environment unless they name it already, or a later release. Whether they were. Never raises."""
    try:
        from cad_server._internal import auto_update, installations

        found = installations.targets()
        if auto_update.global_install() is None or found is None:
            return False
        version = _name()
        current = installations.current()
        if current is not None and (_later(current["version"], version) or (
                current["version"] == version and installations._same_place(current["prefix"], found[2]))):
            return False
        _point(version, found)
        told(f"the clients of 0.11.11 and earlier start this cad {version} where none runs")
        return True
    except Exception as error:  # noqa: BLE001 - the records never fail the server
        told(f"the records the clients of 0.11.11 and earlier read could not be written: {error}")
        return False


def move(name: str, told: Callable[[str], None]) -> bool:
    """Step 5 (see the module), from this server of release ``name`` that is no global install: whether the helper
    started. The global cad is the one ``auto_update.installed_tool`` finds (uv's tool first, then pipx's), handed
    over to with its installer's commands and variables. Never older: a global cad older than this release stays
    where it is, and this server runs on."""
    from cad.engine.places import detached, state_dir
    from cad_server._internal import auto_update
    from cad_server._internal.auto_update_helper import installed

    environment = auto_update.installed_tool()
    held = installed(str(environment)) if environment is not None else None
    found = auto_update.global_install(str(environment)) if environment is not None and held is not None else None
    if environment is None or held is None or found is None:
        told("no global cad was found: this server runs on")
        return False
    release = ".".join(map(str, held))
    if _later(name, release):
        told(f"the global cad {release} is older than this cad {name}: this server runs on")
        return False
    windows = os.name == "nt"
    scripts = environment / ("Scripts" if windows else "bin")
    try:
        _point(release, (str(scripts / ("cad.exe" if windows else "cad")),
                         str(scripts / ("python.exe" if windows else "python")), str(environment)))
        command = auto_update.helper_command(release, now=time.time(), version=name, install=found,
                                             record=str(state_dir() / MOVE_RECORD))
        inside = os.path.normcase(os.path.realpath(sys.prefix)).rstrip(os.sep) + os.sep
        if os.path.normcase(os.path.realpath(command[0])).startswith(inside):
            told("no Python outside this environment to hand over with: this server runs on")
            return False
        _start(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
               env={**{key: value for key, value in os.environ.items() if key not in auto_update._UNSET},
                    **found.installer.environ(found.prefix)},
               cwd=str(state_dir()), **detached())
    except (OSError, ValueError) as error:
        told(f"could not hand over to the global cad {release}: {error}")
        return False
    told(f"handing over to the global cad {release}: this server stops, and that cad starts the next")
    return True


def _start(command: list[str], **options) -> None:
    """The helper started (a seam for a test, which records it instead)."""
    subprocess.Popen(command, **options)


def _brought() -> bool:
    """Whether this process runs from a folder a shipped updater made: ``releases`` in the state folder, or in
    0.10.0's on Windows. Never a project's Python, a checkout or uv's cache."""
    from cad.engine import places

    here = os.path.normcase(os.path.realpath(sys.prefix))
    for folder in (places.state_dir(), places.appdata_state_dir()):
        if folder is not None:
            inside = os.path.normcase(os.path.realpath(folder / "releases")).rstrip(os.sep) + os.sep
            if here.startswith(inside):
                return True
    return False


def _due(name: str, record: dict[str, Any] | None, began: float) -> bool:
    """Whether step 4b begins (see the module): this server of release ``name`` runs from a shipped updater's folder
    (``_brought``) and is no global install; ``current`` names it, and install mode's wait has passed since the server
    began (``began``, monotonic); and install mode's ``record`` owes nothing for it, or an attempt ended without
    installing cad."""
    from cad_server._internal import auto_update, install_script, installations

    if not _brought() or auto_update.global_install() is not None:
        return False
    if installations.current_version() != name or time.monotonic() - began < install_script.first_seconds():
        return False
    if record is None or record["version"] != name or record.get("state") != install_script.OWED:
        return True
    return (install_script._count(record.get("attempts")) >= 1 and not record.get("installed")
            and record.get("outcome") in install_script.FAILURES)


def _carry(told: Callable[[str], None]) -> None:
    """Step 4b's install, on a thread: cad installed globally with uv (``tool_install.install``), unless a global cad
    is there already. uv's lines, and why it failed, go to ``told``. Never raises."""
    from cad_server._internal import auto_update, tool_install

    try:
        if auto_update.installed_tool() is not None:
            return
        told("this cad runs from an earlier release's folder: installing cad with uv")
        for line in tool_install.install(timeout=CARRY_SECONDS):
            told(f"uv: {line}")
    except tool_install.Failed as error:
        told(f"could not install cad with uv: {error}")
    except Exception as error:  # noqa: BLE001 - a line in the server's log, never a crash of its thread
        told(f"could not install cad with uv: {type(error).__name__}: {error}")


def once(told: Callable[[str], None]) -> subprocess.Popen | None:
    """Step 7 (see the module), at a server's first quiet tending: where this server is a global install's, our setup
    ran on this computer before (``ours``), install mode is not owed, there is an install command, and the person's
    switch ``plugin.auto_update`` was never set: the switch turned on, under the settings' lock, then the install
    command started, detached, its output in ``auto_update.INSTALL_LOG``. The switch goes on first: it being set is
    how this runs once, and where this run fails, the next newer cad runs the command (``plugin_catch_up``, which
    takes this release as up to date, the switch being on with no record of its own). The command's process,
    where it started; else None. Never raises."""
    try:
        from cad.engine.places import detached, state_dir
        from cad_server._internal import auto_update, install_script
        from cad_server.settings import update_section

        command = install_script.installer()
        record = install_script.read()
        if (not command or auto_update.global_install() is None or not ours()
                or (record is not None and record.get("state") == install_script.OWED)):
            return None
        turned: list[bool] = []

        def turn_on(kept: dict[str, Any]) -> dict[str, Any]:
            if "auto_update" in kept:
                return kept
            turned.append(True)
            return {**kept, "auto_update": True}

        update_section(auto_update.PLUGIN_SECTION, turn_on)
        if not turned:
            return None
        told("the install command set up this computer before: it runs once now, in the background")
        with open(state_dir() / auto_update.INSTALL_LOG, "w", encoding="utf-8") as out:
            return subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=out, stderr=subprocess.STDOUT,
                                    env=install_script.environment(report=None), **detached())
    except Exception as error:  # noqa: BLE001 - never a failure of the server's tending
        told(f"the install command could not start: {error}")
        return None


class Tending:
    """The bridge's part of a server's tending (``daemon.Daemon.tend``): ``follow`` once, at the first; the rest only
    where nothing is in flight (``quiet``): ``once`` (step 7) at the first such; ``move`` once, where install mode's
    report said cad was installed and no attempt runs; else step 4b (``carry``)."""

    def __init__(self) -> None:
        self.followed = False
        self.offered = False
        self.command: subprocess.Popen | None = None  # the install command ``once`` started, held while it runs
        self.moved = False
        self.began = time.monotonic()
        self.carrying: threading.Thread | None = None
        self.next = 0.0  # monotonic: when step 4b may begin again

    def tend(self, name: str, told: Callable[[str], None], *, quiet: bool) -> None:
        from cad_server._internal import install_script

        if not self.followed:
            self.followed = True
            follow(told)
        if self.moved or not quiet:
            return
        if not self.offered:
            self.offered = True
            self.command = once(told)
        record = install_script.read()
        if (record is None or record["mode"] != install_script.INSTALL or not record.get("installed")
                or record.get("outcome") == install_script.RUNNING or record["version"] != name):
            self.carry(name, record, told)
            return
        from cad_server._internal import auto_update

        self.moved = True
        if auto_update.global_install() is None:
            move(name, told)

    def carry(self, name: str, record: dict[str, Any] | None, told: Callable[[str], None]) -> None:
        """Step 4b (see the module): the install begun on a thread where it is due (``_due``); at the first quiet
        tending after it ended, ``move``. Where nothing moved, begun again a day later; a new server begins afresh."""
        from cad_server._internal import install_script

        if self.carrying is None:
            if time.monotonic() >= self.next and _due(name, record, self.began):
                self.carrying = threading.Thread(target=_carry, args=(told,), name="cad-bridge-install", daemon=True)
                self.carrying.start()
            return
        if self.carrying.is_alive() or (record is not None and record.get("outcome") == install_script.RUNNING):
            return
        self.carrying = None
        self.next = time.monotonic() + install_script.DAY_SECONDS
        self.moved = move(name, told)


if __name__ == "__main__":
    raise SystemExit(main())
