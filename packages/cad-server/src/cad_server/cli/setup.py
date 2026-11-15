"""``cad setup``: this version of cad installed on this computer, and nothing else.

It is run as ``uvx --no-config --managed-python --python 3.14 --from cad-server==<version> cad setup`` (or by the
version's own ``cad``), and sets up the version that runs it, in six steps, each skipped where it is done already,
so running it again is quick and changes nothing:

1. the version's folder, ``versions/<version>`` in the state folder (``cad_server._internal.versions``);
2. its server installed into it (``code/server``: ``cad-server==<version>``, or, for this process's own version,
   from where this process's server came);
3. a check that it runs: its own Python asked which version it is;
4. the CAD kernel installed into it (``cad[build123d]`` at the version);
5. its "complete" marker written (``code/cad-version.json``);
6. the ``cad`` command, ``~/.local/bin/cad``, written where it is missing or was written by an older release
   (``cad_server._internal.installations.write_proxy``).

Steps 1 to 5 are ``versions.make_present``. The first setup of a version also gives it its own settings and store,
copied ONCE from the newest older installed version, or, on a computer coming from 0.11.10 and earlier, from that
layout, what 0.7 and 0.8 kept in their own folder taken into it first (``cad_server._internal.imports.ensure``;
nothing once they are there). On a computer an earlier release ran on, what it left running is handed over
(``cad_server._internal.legacy``: ``stop_earlier``, ``hand_over``): 0.8's server (and 0.10.0's on Windows) stopped by
its own stop command BEFORE that copy, so nothing it writes after it is lost, and a server of 0.11.10 or earlier asked
to stop once idle. The records a process with no version starts a server by (``installations/current`` and the
record it names: a client of 0.11.10 and earlier, the library in a person's own Python) are written for this version
where they name nothing yet, a version not installed, or an older one (``legacy.hand_over``).

Last, setup starts the version's own server, detached, where none runs (``_serve``): setup always runs outside an
agent's sandbox, since it installs, and a sandboxed shell cannot start a server, so every later session -- an agent's
sandboxed ``cad`` command among them -- finds it running (a server never stops on a timer). Waited for only until its
door answers; a server that cannot start is said, and never fails the setup. Where a server of 0.11.10 or earlier
still holds the flat door and was just asked to stop once idle (``legacy.hand_over``), none is started: its pages'
port is still taken, and the next command starts this version's server once it is free, as before. Nothing else on
the computer is changed.

``--engine-update`` (hidden, absent from the help) is how releases 0.10.0 to 0.11.10 update themselves: their
updater makes a flat folder of the newer release and runs its ``cad setup --engine-update``, reading its exit status
(0: go on and switch the computer's server to it). It then reads the release ``installations/current`` names as the
one to go back to, and its switch points ``current`` at the newer release, starts that release's server through the
records and the door of its own layout, checks it answers on the pages' port, and points ``current`` back and starts
its own server again where it does not: so this run starts no server and leaves ``current`` and the ``cad`` command
as they are -- the shipped release's command runs what ``current`` names, so it follows the switch either way. It does
steps 1 to 5 (from the flat folder, the version made present and the same command run again from the version's own
``cad``; with ``CAD_UPDATE_PREPARE=1``, an automatic update's first half, it stops once the version is present), then
the hand-over from that layout (the installation record naming the version's server, which the switch starts once it
has pointed ``current`` at it: ``installations.register``), and last owes the computer the hosted install script's
run (``cad_server._internal.install_script.owe``): the version's own server runs it once it serves, and again until it
has worked. It starts nothing.

But for one updater, whose switch cannot start this version: 0.10.0 on Windows keeps its state, the records its switch
starts a server by among it, in the local application data, apart from this version's, so its switch would only go
back to 0.10.0 (``_alone``: the flat folder is there). There the run from the flat folder first stops 0.10.0's server
by its own stop command -- the updater that runs it among it -- and takes nothing in where it would not stop, so
0.10.0 runs on with what it has; then, once the version is present with what it took in from 0.10.0, the version's own
run takes the computer over as a plain setup does (``_take_over``): the ``cad`` command, the records clients find a
server by, in this layout and in 0.10.0's own state folder, so none of its clients starts it again, the install
script's run owed, and this version's server started and serving pages on the port and with the token it took in.

How a version arrived -- by which route, from which version -- is kept for its server, and each run's end is told
once (``cad_server._internal.arrival``: ``keep``, ``setup_ended``).

Exit status: 0 done; 1 a step failed; 2 bad arguments; 3 this version cannot be installed from this shell (no uv, no
network for what uv's cache lacks, a folder it may not write: an agent's sandbox).
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Sequence
from typing import NamedTuple

DEFAULT_PROG = "cad setup"
# Set by the updater of 0.11.x for an automatic update's first run of ``--engine-update``: the version made present,
# and nothing else; it runs ``--engine-update`` again, without it, once its server is idle.
PREPARE_ENV = "CAD_UPDATE_PREPARE"
# Set by a run of ``--engine-update`` from the flat folder of an updater that cannot switch to this version (``_alone``:
# 0.10.0 on Windows) for the version's own run it hands on to, which then takes the computer over (``_take_over``).
ALONE_ENV = "CAD_ENGINE_UPDATE_ALONE"
# How long setup waits for the server it started to answer at its door (``_serve``): a server answers there within a
# second or two of starting; its kernel processes start with its first build, never here.
SERVE_SECONDS = 30.0


def build_parser(prog: str = DEFAULT_PROG):
    import argparse

    from cad_server._internal.cli_parser import parser as command_parser

    parser = command_parser(
        prog=prog,
        allow_abbrev=False,
        description="Install this version of cad on this computer: its own folder, its server and the CAD "
                    "kernel, and the cad command (~/.local/bin/cad) where it is missing or older. Nothing else is "
                    "changed. Running it again is quick and harmless.",
    )
    parser.add_argument("--engine-update", action="store_true", help=argparse.SUPPRESS)
    return parser


class Failed(NamedTuple):
    """A run's step that failed, said already: the exit status, and why, for a count of it
    (``arrival.setup_ended``): ``uv``, ``network`` or ``denied`` where the version cannot be made from this shell
    (``versions.CANNOT``), else ``other``."""

    code: int
    reason: str = "other"


def main(argv: Sequence[str] | None = None, prog: str = DEFAULT_PROG) -> int:
    args = build_parser(prog).parse_args(argv)
    if args.engine_update:
        return engine_update()
    return setup()


def _say(line: str) -> None:
    """A line on stderr; never a failure where no one reads it any more (an updater that went)."""
    try:
        sys.stderr.write(f"cad: {line}\n")
        sys.stderr.flush()
    except (OSError, ValueError):
        pass


def _name() -> str | None:
    """The version this process sets up: the one it is told it runs as (a development version), else its release;
    None for a source tree that was not told one."""
    import cad_server
    from cad.engine import places
    from cad_server._internal import installations

    told = os.environ.get(places.INSTALLATION_ENV)
    if told:
        return told
    if installations.editable():
        return None
    return cad_server.__version__


def _no_name(route: str) -> int:
    """A source tree that was not told its version: said, and its end told; 1."""
    from cad.engine import places
    from cad_server._internal import arrival
    from cad_server._internal.cli_errors import FAILED

    _say("this cad-server is a source tree: it is set up only as a version it is named "
         f"({places.INSTALLATION_ENV})")
    arrival.setup_ended("", route, None, arrival.FAILED, "other")
    return FAILED


def _ended(name: str, route: str, came: str | None, failed: Failed | None, *, first: bool = False) -> int:
    """The run's end told (``arrival.setup_ended``; ``first``: this run kept the version's arrival record): its exit
    status."""
    from cad_server._internal import arrival

    arrival.setup_ended(name, route, came, arrival.OK if failed is None else arrival.FAILED,
                        None if failed is None else failed.reason, first=first)
    return 0 if failed is None else failed.code


def _keep(name: str, route: str, came: str | None) -> bool:
    """How version ``name`` arrived, kept for its server where nothing is kept yet (``arrival.keep``): whether this
    run kept it. A folder it cannot write keeps nothing, and fails nothing."""
    from cad_server._internal import arrival

    try:
        return arrival.keep(name, route, came)
    except OSError:
        return False


def _present(name: str) -> Failed | None:
    """Steps 1 to 5 for ``name``, then its data copied in once (``imports.ensure``): None once it is present, else
    what failed, said."""
    from cad_server._internal import imports, versions
    from cad_server._internal.cli_errors import FAILED, REASONS

    found = versions.make_present(name, told=_say)
    if not found.ok:
        if found.cannot is not None:
            _say(f"cad {name} could not be installed from this shell: {found.error}. Run this command again "
                 "outside the sandbox.")
            return Failed(REASONS["cannot_install_here"],
                          found.cannot if found.cannot in versions.CANNOT else "other")
        _say(f"cad {name} could not be installed: {found.error}")
        return Failed(FAILED)
    try:
        copied = imports.ensure(name, told=_say)
    except OSError as error:  # never a failed setup: the version's server imports at its first start
        _say(f"cad {name}'s settings and store were not copied in yet: {error.strerror or error}")
        return None
    if copied.done and copied.source is not None:
        _say(f"cad {name} took its settings and store from {copied.source.words()}")
    return None


def _command(name: str) -> Failed | None:
    """Step 6: the ``cad`` command written where it is missing or older. None when it is there; else what failed,
    said."""
    from cad_server._internal import installations
    from cad_server._internal.cli_errors import FAILED

    path, status, error = installations.write_proxy()
    if error is not None or status == installations.FOREIGN:
        why = error or "a file of that name there is not cad's, and is left alone"
        _say(f"cad {name} is installed, but the cad command could not be written at {path}: {why}")
        return Failed(FAILED)
    return None


def setup() -> int:
    """``cad setup``: the six steps (see the module), said in a line or two."""
    from cad.engine import places
    from cad_server._internal import arrival

    name = _name()
    if name is None:
        return _no_name(arrival.SETUP)
    came = arrival.came_from(name)
    was = places.version_record(name) is not None
    _stop_earlier()
    failed = _present(name) or _command(name)
    if failed is not None:
        return _ended(name, arrival.SETUP, came, failed)
    first = _keep(name, arrival.SETUP, came)
    handing_over = _arrive(name, engine_update=False)
    _out(f"cad {name} is {'installed' if was else 'installed now'}: {places.version_dir(name)}")
    if not handing_over:  # else said: this version's server starts at the next command (``legacy.hand_over``)
        _serve(name)
    return _ended(name, arrival.SETUP, came, None, first=first)


def _out(line: str) -> None:
    """A line on stdout; never a failure where no one reads it any more (an updater that went)."""
    try:
        sys.stdout.write(f"{line}\n")
        sys.stdout.flush()
    except (OSError, ValueError):
        pass


def _serve(name: str, *, pages: bool = False) -> None:
    """Version ``name``'s own server started, detached, where none runs (see the module), the way its ``cad``
    starts it (``cad.engine.client.connect``, with this version's name and the environment another program runs
    in, ``_environment``), waited for only until its door answers: one line, said. ``pages``: then asked to serve
    pages (``{"op": "http"}``), on the port and with the token it took in, as a page's link asks it, so a page an
    earlier release served finds it there. Never a failed setup."""
    from cad.engine import client, places

    saved, environment = dict(os.environ), {**_environment(), places.INSTALLATION_ENV: name}
    try:
        os.environ.clear()
        os.environ.update(environment)
        connection = client.connect(start=True, timeout=SERVE_SECONDS)
        if connection is not None:
            connection.close()
        if pages:
            client.request({"op": "http"}, start=False)
    except (ConnectionError, OSError, ValueError) as error:
        _say(f"cad {name}'s server is not running: {error}")
        return
    finally:
        os.environ.clear()
        os.environ.update(saved)
    _out(f"cad {name}'s server is running")


# --- --engine-update --------------------------------------------------------------------------------------------


def engine_update() -> int:
    """``cad setup --engine-update``: steps 1 to 5, the hand-over from the layout of 0.11.10 and earlier, and the
    install script's run owed (see the module). Its end is told once: by the run that fails, or by the version's own
    whole run; a prepare run that succeeds and a run from the flat folder that hands on tell none."""
    from cad.engine import places
    from cad_server._internal import arrival

    name = _name()
    if name is None:
        return _no_name(arrival.UPDATER)
    came = arrival.came_from(name)
    prepare = os.environ.get(PREPARE_ENV) == "1"
    alone = os.environ.pop(ALONE_ENV, "") == "1"
    if places.versioned() is None and not os.environ.get(places.INSTALLATION_ENV):
        # Run from the flat folder an updater of 0.11.10 or earlier made (or by uvx): the version made present,
        # then this command run again from the version's own code, which the hand-over runs from (it removes the
        # flat folders of that layout once nothing runs from them). An updater whose switch cannot start this
        # version (``_alone``) has its server stopped first, before its data is taken in: the run takes over.
        alone = _alone()
        failed = _stop_alone(name) if alone else None
        failed = failed or _present(name)
        if failed is not None:
            return _ended(name, arrival.UPDATER, came, failed)
        if prepare:
            return 0
        record = places.version_record(name)
        assert record is not None
        return _again(record["cad"], alone=alone)
    failed = _present(name)
    if prepare:
        return 0 if failed is None else _ended(name, arrival.UPDATER, came, failed)
    if alone:
        return _ended(name, arrival.UPDATER, came, failed, first=failed is None and _take_over(name, came))
    failed = failed or _hand_over(name)
    if failed is None:
        _arrive(name, engine_update=True)
        failed = _owe(name)
    first = failed is None and _keep(name, arrival.UPDATER, came)
    return _ended(name, arrival.UPDATER, came, failed, first=first)


def _alone() -> bool:
    """Whether the updater that runs this ``--engine-update`` from its flat folder cannot switch the computer to this
    version: 0.10.0 on Windows, which keeps its state -- the records its switch starts a server by among it -- in the
    local application data (``places.appdata_state_dir``), apart from this version's, so its switch never finds this
    version, and goes back to 0.10.0. Told by where that flat folder is: its ``releases`` there."""
    from cad.engine import places

    folder = places.appdata_state_dir()
    if folder is None:
        return False
    inside = os.path.normcase(os.path.realpath(folder / "releases")).rstrip(os.sep) + os.sep
    return os.path.normcase(os.path.realpath(sys.prefix)).startswith(inside)


def _stop_alone(name: str) -> Failed | None:
    """0.10.0's servers on Windows stopped by its own stop command (``legacy.stop_appdata``), the updater that runs
    this among them, before anything of 0.10.0's is taken in: None when none runs; else what failed, said, and nothing
    taken in, so 0.10.0 runs on with what it has."""
    from cad_server._internal import legacy
    from cad_server._internal.cli_errors import FAILED

    if legacy.stop_appdata(_say):
        return None
    _say(f"cad {name} did not take over: the server of cad-server 0.10.0 did not stop, and keeps what it has")
    return Failed(FAILED)


def _take_over(name: str, came: str | None) -> bool:
    """The whole run of ``--engine-update`` for an updater that cannot switch to version ``name`` (``_alone``: 0.10.0
    on Windows, whose server its run from the flat folder stopped before 0.10.0's data was taken in): the computer
    taken over as a plain ``cad setup`` takes it over -- the ``cad`` command (a file it cannot write is said, and the
    run goes on: 0.10.0's data is this version's now), the records clients start a server by (``legacy.hand_over``),
    and the same records in 0.10.0's own state folder (``installations.mirror``), so none of its clients starts 0.10.0
    again --, the install script's run owed, and this version's server started and serving pages on the port and
    with the token it took in. Whether this run kept the version's arrival record. Never a failure: what could not be
    done is said."""
    from cad.engine import places
    from cad_server._internal import arrival, installations
    from cad_server.engine.registry import Folder

    _command(name)
    first = _keep(name, arrival.UPDATER, came)
    _arrive(name, engine_update=False)
    try:
        installations.mirror(name, Folder(places.appdata_state_dir()))
    except (OSError, TypeError, ValueError) as error:
        _say(f"the records cad-server 0.10.0's clients read could not be written: {error}")
    _owe(name)
    _serve(name, pages=True)
    return first


def _owe(name: str) -> Failed | None:
    """The hosted install script's run owed for version ``name``, which its server carries out
    (``install_script.owe``): None when it is recorded; else what failed, said: the updater then stays on its own
    release, and tries again."""
    from cad_server._internal import install_script
    from cad_server._internal.cli_errors import FAILED

    try:
        install_script.owe(name)
    except OSError as error:
        _say(f"cad {name} could not record what it still owes this computer: {error.strerror or error}")
        return Failed(FAILED)
    return None


def _stop_earlier() -> None:
    """The servers of 0.8 (and of 0.10.0 on Windows) stopped by their own stop command (``legacy.stop_earlier``),
    before this version's data is copied in: what such a server wrote after the copy would be lost. Never a failed
    setup."""
    from cad_server._internal import legacy

    try:
        legacy.stop_earlier(_say)
    except Exception as error:  # noqa: BLE001 - what an earlier release left never fails this version's setup
        _say(f"what an earlier release left running was not stopped: {type(error).__name__}: {error}")


def _arrive(name: str, *, engine_update: bool) -> bool:
    """What earlier releases left running, handed over to version ``name`` (``cad_server._internal.legacy``): for
    ``--engine-update``, the servers of 0.8 (and of 0.10.0 on Windows) stopped by their own stop command (plain setup
    stops them before its copy, ``_stop_earlier``); and, by the install command's route (not an updater's, whose own
    switch stops its server), the mirror written where it names nothing, a version not installed or an older one, and
    a server of 0.11.10 or earlier at the flat door asked to stop once idle. Whether such a server was asked to stop
    (it still runs). Never a failed setup."""
    from cad_server._internal import legacy

    try:
        if engine_update:
            legacy.stop_earlier(_say)
        else:
            return legacy.hand_over(name, _say)
    except Exception as error:  # noqa: BLE001 - what an earlier release left never fails this version's setup
        _say(f"what an earlier release left running was not handed over: {type(error).__name__}: {error}")
    return False


def _environment() -> dict[str, str]:
    """The environment another program runs in from here: this one's, without this process's import path, its
    version's name, its channel, the automatic update's first half, the take-over's mark (``ALONE_ENV``), and with the
    person's own PATH (uvx puts its
    own environment's folder first on PATH for the command it runs)."""
    from cad.engine.places import INSTALLATION_ENV, RUN_WITH
    from cad_server._internal.installations import lasting

    environment = {key: value for key, value in os.environ.items()
                   if key not in ("PYTHONPATH", "PYTHONHOME", INSTALLATION_ENV, RUN_WITH, PREPARE_ENV, ALONE_ENV)}
    environment["PATH"] = lasting(os.environ.get("PATH", os.defpath))
    return environment


def _again(cad: str, *, alone: bool = False) -> int:
    """``cad setup --engine-update`` run again by the version's own ``cad``, its exit status this run's (``alone``:
    told so, ``ALONE_ENV``)."""
    run = [cad, "setup", "--engine-update"]
    environment = {**_environment(), **({ALONE_ENV: "1"} if alone else {})}
    if os.name == "nt":
        return subprocess.call(run, env=environment, stdin=subprocess.DEVNULL)
    try:
        sys.stdout.flush()
        sys.stderr.flush()
    except (OSError, ValueError):
        pass
    os.execve(run[0], run, environment)
    return 1  # not reached


def _hand_over(name: str) -> Failed | None:
    """The hand-over from the layout of 0.11.10 and earlier to version ``name``: the installation record that layout's
    switch starts a server by, written for the version's server environment (``installations.register``). Not
    ``installations/current``: the switch reads it after this run as the release to go back to should this version's
    server not answer, then points it here itself, under its engine's lock. None when done; else what failed, said:
    the updater then stays on its own release."""
    from cad.engine.places import version_record
    from cad_server._internal import installations
    from cad_server._internal.cli_errors import FAILED

    record = version_record(name)
    try:
        if record is not None:
            installations.register(name, (record["cad"], record["python"], record["prefix"]))
            return None
        why = "it is not installed"
    except (OSError, ValueError) as error:
        why = str(error)
    _say(f"cad {name} could not take over: {why}")
    return Failed(FAILED)


if __name__ == "__main__":
    raise SystemExit(main())
