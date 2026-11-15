"""The layout of 0.11.10 and earlier: what a version imports from where it has no older version to import from, and
what goes once it is safe to remove.

In 0.11.10 and earlier every release on a computer shared one data folder, the state folder itself, one cache folder
(``places.legacy_cache_dir``), and kept its code flat in ``releases/<release>``. A version in its own folder
imports from it at its first setup where no older version is installed (``cad_server._internal.imports``: the same
relative names as a version's ``data/``) and never writes it. The layout's bulk goes once it is safe (``unsafe`` says
why not yet), removed by the newest installed version's server in its cleanup, as it starts and every 24 hours
(``versions.clean``).

Safe means all of: that version has its data imported (its marker); its server runs (``versions.serves``); no server
but that version's own holds the flat engine folder every client of 0.11.10 and earlier finds (``flat_server``: one
of those releases still running, or one started by uvx outside ``releases/``); no process runs from the layout
(``releases.running`` on its release folders and its kernel environments: on Windows a process whose program is
there; and on Windows a rename that the system refuses for a file in use keeps the folder too). A client of 0.11.10 or earlier that starts after
it is gone finds the record ``installations/current`` names gone too, and starts a server of its own, as it would on
a new computer. Nothing of an agent app's is read for it, and no record is kept: the layout's own folders are the
record.

Before anything goes, what the layout holds that the version lacks is carried over into it (``imports.carry``:
records, Recents, settings keys): a client of 0.11.10 still running wrote there after the version imported it. A
carry-over that could not read or write everything removes nothing, and the next cleanup tries again.

What ``remove`` removes, by name (``REMOVED``, ``CACHES``): each flat ``releases/<release>`` (renamed aside first)
with its making's lock and its installation's record, and ``releases/`` once empty; the shared ``documents/``
(the records) and ``recents/`` in the state folder; its kept telemetry batches (``analytics.KEPT``) move, whole, to
the version, which sends them from then on (never copied, so never sent twice, nor imported again from here); in the
cache folder of 0.11.10 and earlier the kernel and ``cad run`` environments (``base``), compiled Python
(``pycache``), documents' bytes (``documents``), ``hulls``, ``mjcf``, ``homes`` and the interference checks' cache
(``interference``), and the cache folder once nothing else is in it.

Arriving from an earlier release (``cad setup``): the servers of 0.8 (and of 0.10.0 on Windows) stopped by their own
stop command (``stop_earlier``); and, on the install command's route rather than an updater's, the mirror written for
the version and a server of 0.11.10 or earlier at the flat door asked to stop once idle (``hand_over``). The updater of
0.10.0 on Windows, whose switch cannot start this version, has its server stopped the same way before anything of
it is taken in (``stop_appdata``, which says whether it held), and the version's setup then takes over as the install
command's route does (``cad_server.cli.setup``). These are cad's own past processes and records, found the way each
release recorded them; nothing of an app's is touched.

What it keeps, because a client of 0.11.10 or earlier may still read it and it is small, or it is the computer's: the
shared ``settings.json`` (a telemetry no is written there too; a version with nothing older to import from imports
these settings alone, ``imports.source``), ``engines/`` (the page token and port where a client of 0.11.10 or earlier
finds them), the other small files there (``settings.lock``, ``install-channels.json``, ``versions.json``, the
telemetry spool, the updaters' records), ``installations/`` (``installations.mirror``), and every global file:
``install.lock``, ``versions/``.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Callable

from cad.engine import places

__all__ = ["CACHES", "REMOVED", "SETTINGS", "cache_root", "hand_over", "importable", "present", "remove", "removable",
           "root", "stop_appdata", "stop_earlier", "unsafe"]

# The settings it keeps, which a version with nothing older to import from imports alone once its bulk is gone.
SETTINGS = "settings.json"
# What goes from the state folder, beside the flat release folders: the records and Recents, carried over first
# (``imports.carry``). Its kept telemetry batches move, whole, to the default's version (``remove``).
REMOVED = ("documents", "recents")
KEPT = "telemetry-batches.jsonl"
# What goes from the cache folder of 0.11.10 and earlier: documents' bytes and their kept checks, convex hulls, MJCF
# assets, integrations' homes, the interference checks' cache, the kernel and ``cad run`` environments, compiled
# Python.
CACHES = ("documents", "hulls", "mjcf", "homes", "interference", "base", "pycache")
RELEASES = "releases"
# How long the flat engine folder's server is given to say what it is (``flat_server``).
ASK_SECONDS = 5.0


def root() -> Path:
    """The layout's data folder: the state folder itself."""
    return places.state_dir()


def cache_root() -> Path:
    """The layout's cache folder (``places.legacy_cache_dir``)."""
    return places.legacy_cache_dir()


def importable() -> bool:
    """Whether the layout still holds what a version imports beyond its kept settings: its bulk is there
    (``removable``). Once that is removed, only its settings are read (``imports.source``)."""
    return removable()


def _releases() -> list[str]:
    try:
        return sorted(entry.name for entry in os.scandir(root() / RELEASES) if entry.is_dir(follow_symlinks=False))
    except OSError:
        return []


def removable() -> bool:
    """Whether anything ``remove`` removes, or moves, is here."""
    return (bool(_releases()) or any(os.path.lexists(root() / name) for name in (*REMOVED, KEPT))
            or any(os.path.lexists(cache_root() / name) for name in CACHES))


def present() -> bool:
    """Whether this device has the layout: anything ``remove`` removes. Its kept small files alone are not it."""
    return removable()


def unsafe(version: str, *, read_only: bool = False) -> str | None:
    """Why the layout cannot be removed yet by version ``version``, in words; None when it is safe: ``version``'s data
    is imported, its server runs, no other server holds the flat door, and no process runs from the layout (see the
    module). ``read_only`` (``cad doctor``'s report): the flat engine folder's lock is read, never taken or made
    (``flat_server``)."""
    from cad_server._internal import imports, releases, versions

    if not imports.imported(version):
        return f"cad {version}'s data is not imported yet"
    if not versions.serves(version):
        return f"cad {version} has not started yet"
    flat = flat_server(take=not read_only)
    if flat is not None and not _within(flat, places.code_dir(version)):
        return f"a server other than cad {version}'s holds the flat engine folder {places.engines_dir()}"
    for folder in (*(root() / RELEASES / name for name in _releases()), cache_root() / "base"):
        if folder.exists() and releases.running(folder):
            return f"a process of 0.11.10 or earlier still runs from {folder}"
    return None


def flat_server(*, take: bool = True) -> str | None:
    """The environment of the server that holds the flat engine folder every client of 0.11.10 and earlier finds
    (``places.engines_dir``: its ``engine.lock``, and its door, on Windows its port file), as it says it in its
    ``status`` (``prefix``), read and nothing started; ``""`` for one that holds the lock and does not answer or
    say; None when none holds it. The default version's own server holds it too, as the bridge. ``take`` false
    (``cad doctor --check``): nothing made or taken -- no lock file and no door there is none; a door that does not
    answer, ``""`` -- as ``versions.serves`` asks."""
    import threading

    from cad.engine import client
    from cad_server._internal.versions import _drop, _take

    engines = places.engines_dir()
    address = engines / f"{places.NAME}.{'port' if places.WINDOWS else 'door'}"
    if not take:
        if not (engines / f"{places.NAME}.lock").exists() or not address.exists():
            return None
    else:
        try:
            held = _take(engines)
        except OSError:
            return ""
        if held is not None:
            _drop(held, engines)
            return None
    answers: list = []

    def ask() -> None:
        try:
            connection = client._connect(address)
            if connection is not None:
                answers.append(client._exchange(connection, {"op": "status", "internal": True}, address=address))
        except (OSError, ValueError, ConnectionError, IndexError):
            pass

    asking = threading.Thread(target=ask, daemon=True)
    asking.start()
    asking.join(ASK_SECONDS)
    answer = answers[0] if answers and isinstance(answers[0], dict) else {}
    prefix = answer.get("prefix")
    return prefix if isinstance(prefix, str) else ""


def _within(prefix: str, folder: Path) -> bool:
    inside = os.path.normcase(os.path.realpath(folder)).rstrip(os.sep) + os.sep
    return bool(prefix) and os.path.normcase(os.path.realpath(prefix)).startswith(inside)


def remove(version: str, told: Callable[[str], None] | None = None) -> bool:
    """The layout's bulk removed (see the module) by version ``version``, the newest installed, when it is safe
    (``unsafe``), once what it holds that ``version`` lacks is carried over (``imports.carry``): whether nothing of it
    is left to remove. Each folder is renamed aside before it is removed: one the system refuses to rename (a file
    in use, on Windows) stays, said to ``told``, for the next cleanup. Run under the install lock
    (``versions.clean``)."""
    say = told or (lambda _line: None)
    if not removable():
        return True
    why = unsafe(version)
    if why is not None:
        say(f"the code and caches of 0.11.10 and earlier stay for now: {why}")
        return False
    from cad_server._internal import imports, installations

    carried = imports.carry(imports.of_legacy(), version, told=say)
    if not carried.complete:
        say("the code and caches of 0.11.10 and earlier stay for now: what they hold could not all be carried into "
            f"cad {version}")
        return False
    from cad_server import analytics
    from cad_server.settings import FILE

    # Its kept batches: one owner at a time, so moved, never copied (``analytics.hand_on`` would move its spool too,
    # which clients of 0.11.10 and earlier still write and send: this moves the batches alone).
    try:
        for entry in analytics._take_spool(root() / FILE, KEPT, "batch"):
            analytics._keep(places.data_dir(version) / FILE, KEPT, entry)
    except OSError as error:
        say(f"the telemetry 0.11.10 and earlier kept for sending could not be handed on: {error.strerror or error}")
        return False
    complete = True
    folder = root() / RELEASES
    for name in _releases():
        path = folder / name
        if _gone(path, say):
            (folder / f"{name}.lock").unlink(missing_ok=True)
            for record in installations.records():
                if installations._same_place(record["prefix"], path):
                    installations.forget(record["version"])
        else:
            complete = False
    for entry in _names(folder):  # the locks of releases gone already
        if entry.endswith(".lock") and not (folder / entry[:-5]).exists():
            (folder / entry).unlink(missing_ok=True)
    _rmdir(folder)
    for parent in (root(), cache_root()):  # what an earlier removal cut short left aside
        for entry in _names(parent):
            if entry.startswith(".removing-"):
                shutil.rmtree(parent / entry, ignore_errors=True)
    for path in (*(root() / name for name in REMOVED), *(cache_root() / name for name in CACHES)):
        complete = _gone(path, say) and complete
    _rmdir(cache_root())
    if complete:
        say("removed the code, records and caches of 0.11.10 and earlier")
    return complete


def _names(folder: Path) -> list[str]:
    try:
        return sorted(os.listdir(folder))
    except OSError:
        return []


# --- arriving from an earlier release ---------------------------------------------------------------------------

# The switch that keeps 0.8's ``cadgen`` (and 0.10.0's ``cad``) from counting, sending or telling its telemetry notice
# while its own stop runs on the person's behalf, its words read by no one.
NO_TELEMETRY = {"CADGEN_TELEMETRY": "0", "CAD_TELEMETRY": "0"}
# How long such a stop may take.
STOP_SECONDS = 60.0


def stop_earlier(told: Callable[[str], None] | None = None) -> list[str]:
    """The server of each 0.8 installation (``cadgen``), and on Windows of each 0.10.0 one in the local application
    data, stopped by that release's own stop command, ``<its console script> stop --json``, found the way that release
    recorded it (its installation record, ``installations.earlier``, ``installations.appdata``, whose Python and
    console script are still there), run in its own environment with its telemetry off (``NO_TELEMETRY``). Those
    releases have no updater, and their servers stop on no timer: one left running would serve beside this version's
    for as long as the computer runs. A stop that fails fails nothing; what one did is said to ``told``. The versions
    whose stop ran."""
    from cad_server._internal import installations

    return _stop((("cadgen", installations.earlier(), installations.EARLIER_CONSOLE),
                  ("cad-server", installations.appdata(), "cad")), told)[0]


def stop_appdata(told: Callable[[str], None] | None = None) -> bool:
    """0.10.0's servers on Windows (``installations.appdata``) stopped by its own stop command, as ``stop_earlier``
    stops them: whether every one held -- its stop ran and exited 0, which for 0.10.0 means its server is gone (its
    ``cad stop`` waits until it is, and fails where it is not) --, or there was none to stop."""
    from cad_server._internal import installations

    return _stop((("cad-server", installations.appdata(), "cad"),), told)[1]


def _stop(kinds: tuple[tuple[str, list[dict], str], ...], told: Callable[[str], None] | None) -> tuple[list[str], bool]:
    """Each record's server of ``kinds`` (its name, its records, the key naming its console script) stopped by its own
    ``stop --json`` (``stop_earlier``): the versions whose stop ran, and whether every one ran and exited 0."""
    import json
    import subprocess

    from cad_server._internal import installations

    say = told or (lambda _line: None)
    environment = {key: value for key, value in os.environ.items() if key not in ("PYTHONPATH", "PYTHONHOME")}
    environment.update(NO_TELEMETRY)
    ran: list[str] = []
    held = True
    for name, records, key in kinds:
        for record in records:
            console = record.get(key)
            if not (isinstance(console, str) and os.path.isfile(record["python"]) and os.path.isfile(console)):
                continue
            verb = f"{'cadgen' if key == installations.EARLIER_CONSOLE else 'cad'} stop"
            try:
                done = subprocess.run([console, "stop", "--json"], env=environment, stdin=subprocess.DEVNULL,
                                      capture_output=True, text=True, encoding="utf-8", errors="replace",
                                      timeout=STOP_SECONDS)
            except (OSError, subprocess.SubprocessError) as error:
                say(f"{name} {record['version']}'s `{verb}` could not run ({error}): its server may still run")
                held = False
                continue
            ran.append(record["version"])
            try:
                stopped = json.loads(done.stdout).get("stopped")
            except (ValueError, AttributeError):
                stopped = None
            if done.returncode != 0:
                say(f"{name} {record['version']}'s `{verb}` failed (exit status {done.returncode}): its server may "
                    "still run")
                held = False
            elif stopped:
                say(f"stopped {name} {record['version']}'s server (its own `{verb}`)")
    return ran, held


def _flat_legacy(status: dict | None) -> bool:
    """Whether ``status`` is the answer of a server of 0.11.10 or earlier at the flat door: one that answers, from an
    environment outside ``versions/`` (a release folder of that layout, or uvx's)."""
    prefix = (status or {}).get("prefix")
    if not (isinstance(status, dict) and status.get("ok") and isinstance(prefix, str) and prefix):
        return False
    inside = os.path.normcase(os.path.realpath(places.versions_dir())).rstrip(os.sep) + os.sep
    return not os.path.normcase(os.path.realpath(prefix)).startswith(inside)


def hand_over(version: str, told: Callable[[str], None] | None = None) -> bool:
    """``cad setup`` of version ``version``, reached by the install command rather than by the updater of the layout of
    0.11.10 and earlier (whose ``cad setup --engine-update`` writes the version's record, and whose switch points
    ``installations/current`` and stops its own server):

    - the records clients of those releases start a server by written for ``version`` (``installations.mirror``)
      where ``installations/current`` names nothing (a new computer, one coming from 0.8), a release of that layout,
      a version no longer installed, or an older one, so such a client -- an app session still open on that release,
      or the library in a person's own Python, a process with no version, which starts the server ``current`` names
      -- starts or finds ``version``'s server, which holds the flat door once it is free (``daemon.Bridge``), rather
      than one of its own, or none;
    - a server of 0.11.10 or earlier that holds the flat door (``_flat_legacy``: it answers there, from outside
      ``versions/``) asked to stop once nothing is in flight there (``{"op": "stop", "drain": true}``, which every
      release since 0.10 speaks), never waited for: its work runs to its end, and the next client starts
      ``version``'s server, which takes the page token and port it imported. The layout itself goes by the newest
      version's cleanup once nothing of it runs (``remove``).

    Quiet but for what it did, said to ``told``; never a failure: ``OSError`` writing the mirror is said. Whether a
    server of 0.11.10 or earlier was asked to stop (it runs on until it is idle)."""
    from cad_server._internal import installations, versions

    say = told or (lambda _line: None)
    status = versions.ask_flat({"op": "status"}, seconds=ASK_SECONDS)
    serving = _flat_legacy(status)
    current = installations.current_version()
    stale = current is None or current != version and (current not in versions.present()
                                                        or versions.older(current, version))
    if serving or stale:
        try:
            installations.mirror(version)
        except (OSError, ValueError) as error:
            say(f"the records clients of 0.11.10 and earlier read could not be written: {error}")
    if serving and versions.ask_flat({"op": "stop", "drain": True}, seconds=ASK_SECONDS) is not None:
        old = (status or {}).get("installation") or (status or {}).get("version") or "0.11.10 or earlier"
        say(f"cad-server {old}'s server stops once nothing is in flight there; cad {version}'s takes its "
            "place at the next command")
        return True
    return False


def _rmdir(folder: Path) -> None:
    try:
        folder.rmdir()  # only when nothing else is in it
    except OSError:
        pass


def _gone(path: Path, say: Callable[[str], None]) -> bool:
    """What is at ``path`` renamed aside, then removed: whether nothing is left there. A rename the system refuses
    leaves it."""
    if not os.path.lexists(path):
        return True
    aside = path.with_name(f".removing-{path.name}-{os.getpid()}-{os.urandom(4).hex()}")
    try:
        os.rename(path, aside)
    except OSError as error:
        say(f"{path} stays for now: {error.strerror or error}")
        return False
    if aside.is_dir() and not aside.is_symlink():
        shutil.rmtree(aside, ignore_errors=True)
    else:
        aside.unlink(missing_ok=True)
    return True
