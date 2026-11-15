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
(0: go on and switch the computer's server to it), then starts that release's server through the records and the
door of their own layout: so this run starts no server itself. So this run does the six steps (from the flat folder, the version made present and the
same command run again from the version's own ``cad``; with ``CAD_UPDATE_PREPARE=1``, an automatic update's first
half, it stops once the version is present), then the hand-over from that layout (the records its switch reads,
``installations.mirror``: the installation record naming the version's server and ``installations/current`` naming
the version, so the switch starts this version's server, which holds the flat door its clients find), and then
starts the hosted install script once, detached, never waited on: ``curl -fsSL https://texttocad.dev/install.sh | sh`` (Windows PowerShell: ``irm
https://www.texttocad.dev/install.ps1 | iex``), by a program of its own that first waits, up to about an hour, until
the site's ``install.py`` names this release or a later one (``cad_server._internal.install_script``): the site is
deployed after the version feed names a release, and the script of the release before would set up cad alone.
``CAD_ENGINE_UPDATE_INSTALLER`` names a command to run instead (a test names a stand-in), and empty, runs nothing;
``CAD_ENGINE_UPDATE_INSTALL_PY`` names the ``install.py`` that wait reads (a test's own server), and empty, waits for
none, as a command ``CAD_ENGINE_UPDATE_INSTALLER`` names waits for none unless it is set.

Exit status: 0 done; 1 a step failed; 2 bad arguments; 3 this version cannot be installed from this shell (no uv, no
network for what uv's cache lacks, a folder it may not write: an agent's sandbox).
"""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
from collections.abc import Sequence

DEFAULT_PROG = "cad setup"
# Set by the updater of 0.11.x for an automatic update's first run of ``--engine-update``: the version made present,
# and nothing else; it runs ``--engine-update`` again, without it, once its server is idle.
PREPARE_ENV = "CAD_UPDATE_PREPARE"
# What ``--engine-update`` starts once it is done: a command line, split as a shell splits it; empty runs nothing.
INSTALLER_ENV = "CAD_ENGINE_UPDATE_INSTALLER"
INSTALLER = ("sh", "-c", "curl -fsSL https://texttocad.dev/install.sh | sh")
INSTALLER_WINDOWS = ("powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
                     "irm https://www.texttocad.dev/install.ps1 | iex")
# The ``install.py`` the installer is started after, once it names this release (``install_script``): its address.
INSTALL_PY_ENV = "CAD_ENGINE_UPDATE_INSTALL_PY"
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


def _present(name: str) -> int | None:
    """Steps 1 to 5 for ``name``, then its data copied in once (``imports.ensure``): None once it is present, else
    the exit status, said."""
    from cad_server._internal import imports, versions
    from cad_server._internal.cli_errors import FAILED, REASONS

    found = versions.make_present(name, told=_say)
    if not found.ok:
        if found.cannot is not None:
            _say(f"cad {name} could not be installed from this shell: {found.error}. Run this command again "
                 "outside the sandbox.")
            return REASONS["cannot_install_here"]
        _say(f"cad {name} could not be installed: {found.error}")
        return FAILED
    try:
        copied = imports.ensure(name, told=_say)
    except OSError as error:  # never a failed setup: the version's server imports at its first start
        _say(f"cad {name}'s settings and store were not copied in yet: {error.strerror or error}")
        return None
    if copied.done and copied.source is not None:
        _say(f"cad {name} took its settings and store from {copied.source.words()}")
    return None


def _command(name: str, *, engine_update: bool = False) -> int | None:
    """Step 6: the ``cad`` command written where it is missing or older. None when it is there; else 1, said. For
    ``--engine-update`` (``engine_update``) a command that could not be written -- a file of that name that is not
    cad's, a folder it may not write -- is said and the run goes on: the shipped updater that runs it needs the
    hand-over and the install script, not the command, and would otherwise fail the same way every day."""
    from cad_server._internal import installations
    from cad_server._internal.cli_errors import FAILED

    path, status, error = installations.write_proxy()
    if error is not None or status == installations.FOREIGN:
        why = error or "a file of that name there is not cad's, and is left alone"
        _say(f"cad {name} is installed, but the cad command could not be written at {path}: {why}")
        return None if engine_update else FAILED
    return None


def setup() -> int:
    """``cad setup``: the six steps (see the module), said in a line or two."""
    from cad.engine import places
    from cad_server._internal.cli_errors import FAILED

    name = _name()
    if name is None:
        _say("this cad-server is a source tree: it is set up only as a version it is named "
             f"({places.INSTALLATION_ENV})")
        return FAILED
    was = places.version_record(name) is not None
    _stop_earlier()
    failed = _present(name)
    if failed is not None:
        return failed
    failed = _command(name)
    if failed is not None:
        return failed
    handing_over = _arrive(name, engine_update=False)
    sys.stdout.write(f"cad {name} is {'installed' if was else 'installed now'}: {places.version_dir(name)}\n")
    if not handing_over:  # else said: this version's server starts at the next command (``legacy.hand_over``)
        _serve(name)
    return 0


def _serve(name: str) -> None:
    """Version ``name``'s own server started, detached, where none runs (see the module), the way its ``cad``
    starts it (``cad.engine.client.connect``, with this version's name and the environment another program runs
    in, ``_environment``), waited for only until its door answers: one line, said. Never a failed setup."""
    from cad.engine import client, places

    saved, environment = dict(os.environ), {**_environment(), places.INSTALLATION_ENV: name}
    try:
        os.environ.clear()
        os.environ.update(environment)
        connection = client.connect(start=True, timeout=SERVE_SECONDS)
    except (ConnectionError, OSError, ValueError) as error:
        _say(f"cad {name}'s server is not running: {error}")
        return
    finally:
        os.environ.clear()
        os.environ.update(saved)
    if connection is not None:
        connection.close()
    sys.stdout.write(f"cad {name}'s server is running\n")


# --- --engine-update --------------------------------------------------------------------------------------------


def engine_update() -> int:
    """``cad setup --engine-update``: the six steps, the hand-over from the layout of 0.11.10 and earlier, then the
    install script started once (see the module)."""
    from cad.engine import places
    from cad_server._internal.cli_errors import FAILED

    name = _name()
    if name is None:
        _say("this cad-server is a source tree: it is set up only as a version it is named "
             f"({places.INSTALLATION_ENV})")
        return FAILED
    prepare = os.environ.get(PREPARE_ENV) == "1"
    if places.versioned() is None and not os.environ.get(places.INSTALLATION_ENV):
        # Run from the flat folder an updater of 0.11.10 or earlier made (or by uvx): the version made present,
        # then this command run again from the version's own code, which the hand-over runs from (it removes the
        # flat folders of that layout once nothing runs from them).
        failed = _present(name)
        if failed is not None:
            return failed
        if prepare:
            return 0
        record = places.version_record(name)
        assert record is not None
        return _again(record["cad"])
    if prepare:
        return _present(name) or 0
    failed = _present(name) or _command(name, engine_update=True)
    if failed is not None:
        return failed
    failed = _hand_over(name)
    if failed is not None:
        return failed
    _arrive(name, engine_update=True)
    start_installer(name)
    return 0


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
    version's name, its channel, the automatic update's first half, and with the person's own PATH (uvx puts its
    own environment's folder first on PATH for the command it runs)."""
    from cad.engine.places import INSTALLATION_ENV, RUN_WITH
    from cad_server._internal.installations import lasting

    environment = {key: value for key, value in os.environ.items()
                   if key not in ("PYTHONPATH", "PYTHONHOME", INSTALLATION_ENV, RUN_WITH, PREPARE_ENV)}
    environment["PATH"] = lasting(os.environ.get("PATH", os.defpath))
    return environment


def _again(cad: str) -> int:
    """``cad setup --engine-update`` run again by the version's own ``cad``, its exit status this run's."""
    run = [cad, "setup", "--engine-update"]
    if os.name == "nt":
        return subprocess.call(run, env=_environment(), stdin=subprocess.DEVNULL)
    try:
        sys.stdout.flush()
        sys.stderr.flush()
    except (OSError, ValueError):
        pass
    os.execve(run[0], run, _environment())
    return 1  # not reached


def _hand_over(name: str) -> int | None:
    """The hand-over from the layout of 0.11.10 and earlier to version ``name``: the records that layout's updater
    and clients read written (``installations.mirror``), so its switch starts this version's server. None when done;
    else 1, said: the updater then stays on its own release."""
    from cad_server._internal import installations
    from cad_server._internal.cli_errors import FAILED

    try:
        if installations.mirror(name):
            return None
        why = "it is not installed"
    except (OSError, ValueError) as error:
        why = str(error)
    _say(f"cad {name} could not take over: {why}")
    return FAILED


def installer() -> list[str] | str:
    """The command ``--engine-update`` starts once it is done: ``CAD_ENGINE_UPDATE_INSTALLER``'s where it is set
    (empty: none), else the hosted install script for this computer. On Windows the variable's command line is
    started as it is written, one string that Windows splits as its programs do: ``shlex`` there keeps a quoted
    word's quotes, naming a program that is not there."""
    if INSTALLER_ENV in os.environ:
        named = os.environ[INSTALLER_ENV].strip()
        return named if os.name == "nt" else shlex.split(named)
    return list(INSTALLER_WINDOWS if os.name == "nt" else INSTALLER)


def install_py() -> str | None:
    """The ``install.py`` whose fallback release the installer waits for (``install_script``):
    ``CAD_ENGINE_UPDATE_INSTALL_PY``'s where it is set (empty: none), else none for a command
    ``CAD_ENGINE_UPDATE_INSTALLER`` names, else the site's."""
    from cad_server._internal import install_script

    if INSTALL_PY_ENV in os.environ:
        return os.environ[INSTALL_PY_ENV].strip() or None
    return None if INSTALLER_ENV in os.environ else install_script.URL


def start_installer(name: str | None = None) -> int | None:
    """The install script (``installer``) started once, detached -- a session of its own, its output nowhere --
    and never waited on: the updater that runs this command reads its output until it ends. Started by a program of
    this version's Python that first waits until ``install_py`` names version ``name`` (this one's by default) or a
    later one (``cad_server._internal.install_script``), where there is one to wait for. Its process id, or None
    where there is none to start, or it could not start (said)."""
    from cad.engine.places import detached

    command = installer()
    if not command:
        return None
    version, url = name or _name(), install_py()
    if url and version:
        command = [sys.executable, "-P", "-m", "cad_server._internal.install_script", version, url, "--",
                   *([command] if isinstance(command, str) else command)]
    try:
        started = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL, env=_environment(), close_fds=True, **detached())
    except OSError as error:
        _say(f"the install script could not be started: {error}")
        return None
    return started.pid


if __name__ == "__main__":
    raise SystemExit(main())
