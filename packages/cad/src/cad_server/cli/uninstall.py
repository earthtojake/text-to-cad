"""``cad uninstall``: cad removed from this computer, and nothing else.

What it removes: every installed version (``versions/<version>`` in the state folder), each version's server
stopped first, and the server of the layout of 0.11.10 and earlier where one still runs; cad's state folder
(``cad.engine.places.state_dir``: every version, its settings, Recents and documents' records, and what earlier
releases kept there) and the cache folder of 0.11.10 and earlier (``places.legacy_cache_dir``); and the ``cad``
command (``~/.local/bin/cad``, on Windows ``cad.exe`` and its Python) where it is cad's; and what the servers kept
in the engines' folder (``places.engines_dir``: each version's door and lock, the door of 0.11.10 and earlier), on
Windows a folder beside the state folder, elsewhere in the temporary folder. Nothing is kept. A folder of that name
that holds no mark of cad's (``_cad_state``, ``_cad_cache``) is another program's, and is left alone; in the engines'
folder only cad's own entries go (``_engine_entries``).

Each version's server is asked its process id, then to stop, and waited for: its lock let go, then no process left
running from the version's folder (``versions.gone``; on Windows the processes whose program is there), and on
Windows the server's own process, opened before the stop (``releases.exits``), ended -- a folder is not removed
while a file in it is in use there. A removal Windows still refuses (a scanner holding a file a moment) is tried
again for a few seconds (``REMOVE_SECONDS``) before it is said.

It asks first: at a terminal ``Remove cad from this computer? (y/N)``; where no one can be asked, nothing
is changed without ``--yes`` (``cad_server._internal.consent``).

Exit status: 0 removed; 1 something stays (a server that would not stop, a folder something still runs from: said,
with what to delete once nothing runs from it), or the person said no; 2 bad arguments, or a yes is needed and no
one can be asked.
"""

from __future__ import annotations

import contextlib
import os
import shutil
import sys
from collections.abc import Sequence
from pathlib import Path

DEFAULT_PROG = "cad uninstall"
# How long a folder Windows refuses to remove whole is tried again (``_remove_tree``): a file a process that has ended
# held, which a scanner or the indexer may hold a moment longer.
REMOVE_SECONDS = 5.0
# What cad's legacy cache folder holds (``legacy.CACHES``): a folder of that name holding these alone is cad's.
CACHE_NAMES = frozenset({"documents", "hulls", "mjcf", "homes", "interference", "base", "pycache"})


def build_parser(prog: str = DEFAULT_PROG):
    from cad_server._internal.cli_parser import parser as command_parser
    from cad_server._internal.consent import add_yes

    parser = command_parser(
        prog=prog,
        allow_abbrev=False,
        description="Remove cad from this computer: every installed version, their servers stopped first, "
                    "cad's state and cache folders (settings, Recents and documents' records among them), "
                    "and the cad command. Nothing is kept, and nothing else is changed.",
    )
    add_yes(parser, "remove it")
    return parser


def _say(line: str) -> None:
    try:
        sys.stdout.write(line + "\n")
        sys.stdout.flush()
    except (OSError, ValueError):
        pass


def _entries(folder: Path) -> list[str] | None:
    try:
        return sorted(entry.name for entry in os.scandir(folder))
    except OSError:
        return None


def _cad_state(folder: Path) -> bool:
    """Whether ``folder`` is cad's state folder, to remove whole: empty, or holding a mark only cad writes -- a
    version's code marker or cache tag (``versions/<version>/code``), an installation record or ``current``
    (``installations/``), a release folder's marker (``releases/<release>/cad-release.json``), or cad's settings
    (``settings.json`` with its ``telemetry`` section). A name alone (``documents``, ``settings.json``) is not one:
    another program may keep a folder of the same name."""
    import json

    from cad.engine import places
    from cad_server._internal import releases

    held = _entries(folder)
    if held is None:
        return False
    if not held:
        return True
    for name in _entries(folder / places.VERSIONS) or ():
        code = folder / places.VERSIONS / name / places.CODE
        if (code / places.VERSION_MARKER).is_file() or (code / "CACHEDIR.TAG").is_file():
            return True
    installations = folder / places.INSTALLATIONS
    if (installations / "current").is_file() or any(name.endswith(".json") for name in _entries(installations) or ()):
        return True
    if any((folder / releases.FOLDER / name / releases.MARKER).is_file() for name in _entries(folder / releases.FOLDER)
           or ()):
        return True
    try:
        settings = json.loads((folder / "settings.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return isinstance(settings, dict) and isinstance(settings.get("telemetry"), dict)


def _cad_cache(folder: Path) -> bool:
    """Whether ``folder`` is the cache folder of 0.11.10 and earlier, to remove whole: empty, holding an environment
    cad made (``base/<key>/cad-env.json``), or holding nothing but the folders that cache has (``CACHE_NAMES``)."""
    from cad.engine import places

    held = _entries(folder)
    if held is None:
        return False
    if not held or set(held) <= CACHE_NAMES:
        return True
    return any((folder / "base" / name / places.MARKER).is_file() for name in _entries(folder / "base") or ())


def _engine_entries(folder: Path, versions: list[str]) -> list[Path]:
    """What cad's servers keep in the engines' folder ``folder``, to remove: the door, lock, port file and notes of
    0.11.10 and earlier (``engine.*``) and its clients' pipes (``clients``), and each version's folder -- one named as
    a version that holds nothing but those, or one of ``versions``, the versions this command removes. Nothing else
    there: ``CAD_ENGINE_DIR`` may name a folder others use."""
    from cad.engine import places

    def own(name: str) -> bool:
        return name == "clients" or name.startswith(f"{places.NAME}.")

    found = []
    for name in _entries(folder) or ():
        path = folder / name
        if own(name):
            found.append(path)
        elif places.VERSION.fullmatch(name) and path.is_dir() and not path.is_symlink():
            inside = _entries(path)
            if name in versions or (inside and all(own(entry) for entry in inside)):
                found.append(path)
    return found


def _remove_tree(path: Path) -> bool:
    """``path`` removed (a folder with all it holds): whether it is gone. On Windows a removal it refuses is tried
    again until ``REMOVE_SECONDS`` have passed (a file in use a moment longer than the process that held it); a
    folder something still runs from stays, and is said."""
    import time

    deadline = time.monotonic() + REMOVE_SECONDS
    while True:
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path, ignore_errors=True)
        else:
            try:
                path.unlink()
            except FileNotFoundError:
                pass
            except OSError:
                pass
        if not os.path.lexists(path):
            return True
        if os.name != "nt" or time.monotonic() >= deadline:
            return False
        time.sleep(0.1)

def main(argv: Sequence[str] | None = None, prog: str = DEFAULT_PROG) -> int:
    from cad.engine import places
    from cad_server._internal import installations, releases, versions
    from cad_server._internal.cli_errors import Failure, write
    from cad_server._internal.consent import confirm, retry

    args = build_parser(prog).parse_args(argv)
    state, cache, engines = places.state_dir(), places.legacy_cache_dir(), places.engines_dir()
    proxy = installations.proxy_path()
    status = installations.proxy_status(proxy)
    command = status in (installations.OK, installations.STALE, installations.NEWER) \
        or installations.earlier_command() is not None
    folders = [folder for folder, ours in ((state, _cad_state), (cache, _cad_cache)) if folder.is_dir() and ours(folder)]
    names = versions.folders()
    plan = [f"  cad {name}, its server stopped first" for name in names]
    plan += [f"  {folder}" for folder in folders]
    plan += [f"  {engines}: what cad's servers keep there"] if _engine_entries(engines, names) else []
    plan += [f"  {proxy}"] if command else []
    if not plan:
        _say("cad is not installed on this computer: nothing to remove.")
        return 0
    try:
        confirm("removing cad from this computer", "Remove cad from this computer?",
                yes=bool(args.yes), as_json=False, command=retry(prog, list(argv or [])),
                preview=["cad uninstall removes, and this cannot be undone:", *plan])
    except Failure as failure:
        return write(failure, prog=prog, as_json=False)

    failed = False
    with versions.install_lock(waiting=lambda: _say("waiting for another install of cad to finish")):
        names = versions.folders()  # again under the lock: one installed while the question waited among them
        for name in names:
            # Its process opened before it is asked to stop: on Windows its files stay in use until it has ended.
            answer = versions.ask(name, {"op": "pid"}, seconds=versions.SERVES_SECONDS)
            pid = answer.get("pid") if isinstance(answer, dict) else None
            ended = releases.exits(pid) if type(pid) is int and pid != os.getpid() else None
            if versions.ask(name, {"op": "stop"}) is not None or versions.endpoint(name).lock.exists():
                if not versions.gone(name, asking=os.getpid()) or (ended is not None
                                                                   and not ended(versions.STOP_SECONDS)):
                    _say(f"cad {name}'s server did not stop")
                    failed = True
        failed = _stop_flat() or failed
    if command:
        failed = _remove_command(proxy) or failed
    running = [str(folder) for folder in folders if releases.running(folder, asking=os.getpid())]
    if failed or running:
        for folder in running:
            _say(f"a process still runs from {folder}")
        _say("cad's folders stay: " + ", ".join(str(folder) for folder in folders)
             + ". Delete them once nothing runs from them.")
        return 1
    for folder in folders:
        if _remove_tree(folder):
            _say(f"removed {folder}")
        else:
            # On Windows: a file in use, this command's own among them.
            _say(f"{folder} could not be removed whole: delete it once this command has ended")
            failed = True
    left = [path for path in _engine_entries(engines, names) if not _remove_tree(path)]
    for path in left:
        _say(f"{path} could not be removed: delete it once this command has ended")
    if _entries(engines) == []:  # nothing else is kept there: the folder goes too
        with contextlib.suppress(OSError):
            engines.rmdir()
    failed = failed or bool(left)
    if not failed:
        _say("cad is removed from this computer.")
    return 1 if failed else 0

def _stop_flat() -> bool:
    """The server that holds the door of 0.11.10 and earlier, where one still runs, asked to stop and awaited: True
    when it did not stop."""
    from cad.engine import client
    from cad_server._internal import versions

    if versions.ask_flat({"op": "stop"}, seconds=versions.SERVES_SECONDS) is None:
        return False
    try:
        gone = client.wait_gone(timeout=versions.STOP_SECONDS, endpoint=versions.flat_endpoint())
    except ConnectionError:
        gone = False
    if not gone:
        _say(f"the server at {versions.flat_endpoint().address} did not stop")
    return not gone


def _remove_command(proxy: str) -> bool:
    """The ``cad`` command removed (``installations.remove_proxy``): True when it could not be. A ``cad.exe`` that
    runs this command is set aside, said."""
    from cad_server._internal import installations

    try:
        removed, left = installations.remove_proxy()
    except OSError as error:
        _say(f"{proxy} could not be removed: {error}")
        return True
    for path in removed:
        _say(f"removed {path}")
    for path in left:
        _say(f"{path} runs this command: set aside, delete it once this command has ended")
    return False


if __name__ == "__main__":
    raise SystemExit(main())
