"""``cad uninstall``: text-to-cad removed from this computer, and nothing else.

What it removes: every installed version (``versions/<version>`` in the state folder), each version's server
stopped first, and the server of the layout of 0.11.10 and earlier where one still runs; text-to-cad's state folder
(``cad.engine.places.state_dir``: every version, its settings, Recents and documents' records, and what earlier
releases kept there) and the cache folder of 0.11.10 and earlier (``places.legacy_cache_dir``); and the ``cad``
command (``~/.local/bin/cad``, on Windows ``cad.exe`` and its Python) where it is text-to-cad's. Nothing is kept. A
folder of that name that holds nothing text-to-cad made is another program's, and is left alone.

It asks first: at a terminal ``Remove text-to-cad from this computer? (y/N)``; where no one can be asked, nothing
is changed without ``--yes`` (``cad_server._internal.consent``).

Exit status: 0 removed; 1 something stays (a server that would not stop, a folder something still runs from: said,
with what to delete once nothing runs from it), or the person said no; 2 bad arguments, or a yes is needed and no
one can be asked.
"""

from __future__ import annotations

import os
import shutil
import sys
from collections.abc import Sequence
from pathlib import Path

DEFAULT_PROG = "cad uninstall"
# What text-to-cad keeps in the two folders it removes, in every layout so far. A folder of that name that holds
# other things and none of these is another program's that shares the name, and is left alone.
STATE_OURS = frozenset({"versions", "installations", "engines", "documents", "recents", "releases", "plugin",
                        "settings.json", "settings.lock", "plugin.lock", "versions.json", "install-channels.json",
                        "default", "channels", "used", "install-receipt.json", "install.lock"})
CACHE_OURS = frozenset({"base", "documents", "pycache"})


def build_parser(prog: str = DEFAULT_PROG):
    from cad_server._internal.cli_parser import parser as command_parser
    from cad_server._internal.consent import add_yes

    parser = command_parser(
        prog=prog,
        allow_abbrev=False,
        description="Remove text-to-cad from this computer: every installed version, their servers stopped first, "
                    "text-to-cad's state and cache folders (settings, Recents and documents' records among them), "
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


def _ours(folder: Path, names: frozenset[str]) -> bool:
    """Whether ``folder`` is text-to-cad's to remove: there, and empty or holding something text-to-cad made."""
    try:
        held = {entry.name for entry in folder.iterdir()}
    except OSError:
        return False
    return not held or bool(held & names)


def main(argv: Sequence[str] | None = None, prog: str = DEFAULT_PROG) -> int:
    from cad.engine import places
    from cad_server._internal import installations, releases, versions
    from cad_server._internal.cli_errors import Failure, write
    from cad_server._internal.consent import confirm, retry

    args = build_parser(prog).parse_args(argv)
    state, cache = places.state_dir(), places.legacy_cache_dir()
    proxy = installations.proxy_path()
    status = installations.proxy_status(proxy)
    command = status in (installations.OK, installations.STALE, installations.NEWER) \
        or installations.earlier_command() is not None
    folders = [(folder, ours) for folder, ours in ((state, STATE_OURS), (cache, CACHE_OURS))
               if folder.is_dir() and _ours(folder, ours)]
    names = versions.folders()
    plan = [f"  text-to-cad {name}, its server stopped first" for name in names]
    plan += [f"  {folder}" for folder, _ours_ in folders]
    plan += [f"  {proxy}"] if command else []
    if not plan:
        _say("text-to-cad is not installed on this computer: nothing to remove.")
        return 0
    try:
        confirm("removing text-to-cad from this computer", "Remove text-to-cad from this computer?",
                yes=bool(args.yes), as_json=False, command=retry(prog, list(argv or [])),
                preview=["cad uninstall removes, and this cannot be undone:", *plan])
    except Failure as failure:
        return write(failure, prog=prog, as_json=False)

    failed = False
    with versions.install_lock(waiting=lambda: _say("waiting for another install of text-to-cad to finish")):
        names = versions.folders()  # again under the lock: one installed while the question waited among them
        for name in names:
            if versions.ask(name, {"op": "stop"}) is not None or versions.endpoint(name).lock.exists():
                if not versions.gone(name, besides=os.getpid()):
                    _say(f"text-to-cad {name}'s server did not stop")
                    failed = True
        failed = _stop_flat() or failed
    if command:
        failed = _remove_command(proxy) or failed
    running = [str(folder) for folder, _ours_ in folders if releases.running(folder, besides=os.getpid())]
    if failed or running:
        for folder in running:
            _say(f"a process still runs from {folder}")
        _say("text-to-cad's folders stay: " + ", ".join(str(folder) for folder, _ours_ in folders)
             + ". Delete them once nothing runs from them.")
        return 1
    for folder, _ours_ in folders:
        shutil.rmtree(folder, ignore_errors=True)
        if folder.exists():
            # On Windows: a file in use, this command's own among them.
            _say(f"{folder} could not be removed whole: delete it once this command has ended")
            failed = True
        else:
            _say(f"removed {folder}")
    if not failed:
        _say("text-to-cad is removed from this computer.")
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
