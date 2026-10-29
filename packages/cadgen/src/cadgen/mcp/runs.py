"""``cad_run``: a model script run by the engine, as ``cadgen run`` runs it.

The CAD app's hosts have no shell of their own (Claude Desktop's chat), or one whose Python is no
cadgen's. ``cad_run`` hands the engine a script instead, and the engine runs ``cadgen run SCRIPT.py``
with its own installation: the project's environment made as for any run
(``cadgen._internal.projects``), the worker in it, the engine itself on its selected port. The script,
its worker and the engine are one cadgen by construction, and the host keeps nothing to match. The
run's output comes back as the operation's progress, a line at a time, and in its result, with the
documents the script has -- what each model call printed, its id -- for ``cad_show``.

A script is named by its absolute path on this computer (``script``), or handed over as text (``code``)
with a ``name``: the engine keeps it at ``<state>/scripts/<name>/<name>.py``, one folder per name, so a rerun
of the same name is the same document (a model's identity is its script's folder and its function's
name, ``engine.ids``), and an agent edits a model by sending its text again. ``cadgen run`` says what
it cannot do in one line; a run that exits failing is the operation's failure, its exit code and its
output's last lines the error.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from collections import deque
from collections.abc import Callable
from pathlib import Path
from typing import Any

from cadgen.jobs import JobError

NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}")
OUTPUT_BYTES = 64 * 1024  # of the run's output kept: its last lines
SCRIPTS = "scripts"  # under the state folder: the scripts handed over as text, a folder each


class RunFailed(RuntimeError):
    """``cadgen run`` could not run or exited failing: its exit code and its output's last lines."""


def folder() -> Path:
    """Where scripts handed over as text live: ``<state>/scripts``."""
    from cadgen.viewer.recents import state_dir

    return state_dir() / SCRIPTS


def check(arguments: dict[str, Any]) -> Path:
    """What a start names, checked before anything is queued and nothing written: the file at ``script``
    (absolute, a ``.py`` that is there), or the place ``<name>/<name>.py`` a script given as ``code``
    takes under the scripts folder. Refused (``JobError``) where neither can run."""
    if "script" in arguments:
        path = Path(str(arguments["script"]))
        if not path.is_absolute():
            raise JobError("cad_run: script must be an absolute path")
        if path.suffix.lower() != ".py":
            raise JobError(f"cad_run: {path} is not a Python script (.py)")
        if not path.is_file():
            raise JobError(f"cad_run: no script {path}")
        return path.resolve()
    name = str(arguments["name"])
    if not NAME.fullmatch(name):
        raise JobError("cad_run: name is letters, digits, _ and -, up to 64, starting with a letter or digit")
    return folder() / name / f"{name}.py"


def script(arguments: dict[str, Any]) -> Path:
    """The script a start names, ready to run: the file at ``script``, or ``code`` written at its place."""
    path = check(arguments)
    if "script" in arguments:
        return path
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        from cadgen.engine.atomic_replace import put

        put(path, lambda staged: staged.write_text(str(arguments["code"]), encoding="utf-8"))
    except OSError as error:
        raise JobError(f"cad_run: cannot write {path}: {error.strerror or error}") from None
    return path


def command(path: Path, arguments: list[str]) -> list[str]:
    """``cadgen run PATH ARGS`` by this installation's Python: the engine's own command, so the run is
    the engine's release whatever release the host's server line names."""
    return [sys.executable, "-m", "cadgen.cli", "run", str(path), *arguments]


def environment() -> dict[str, str]:
    """The run's environment: this process's, with the engine's own port selected (the run attaches to
    this engine), Python unbuffered (its lines come as they are printed), and this release's command
    run as it is (``installations.NO_DEFER_ENV``)."""
    from cadgen._internal.installations import NO_DEFER_ENV
    from cadgen.engine.daemon import selected_port

    return {**os.environ, "CADGEN_PORT": str(selected_port()), "PYTHONUNBUFFERED": "1", NO_DEFER_ENV: "1"}


def documents(path: Path) -> list[dict[str, Any]]:
    """The engine's documents of this script: each one's id, name and state (``models.listing``), what
    ``cad_show`` takes. A rerun of an unchanged script keeps its documents, so they are the script's,
    not this run's alone."""
    from cadgen.engine import client

    try:
        answer = client.request({"op": "models"}, start=False) or {}
    except (ConnectionError, OSError, ValueError):
        return []
    found = []
    for row in answer.get("models") or []:
        if not isinstance(row, dict) or not isinstance(row.get("script"), str):
            continue
        try:
            same = Path(row["script"]).resolve() == path
        except OSError:
            same = False
        if same:
            found.append({"id": row.get("id"), "name": row.get("name"), "state": row.get("state")})
    return found


def perform(arguments: dict[str, Any], progress: Callable[[dict[str, Any]], None]) -> dict[str, Any]:
    """The run: the script's path (or its text written), ``cadgen run`` of it in a child of this
    process, each line of its output a progress frame (``detail``), and the result -- the script, its
    output's last lines (``OUTPUT_BYTES``) and the script's documents."""
    path = script(arguments)
    extra = [str(item) for item in arguments.get("args") or []]
    frame = {"kind": "run", "stage": f"Running {path.name}", "job": str(path)}
    progress(dict(frame))
    try:
        process = subprocess.Popen(command(path, extra), cwd=str(path.parent), env=environment(),
                                   stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   text=True, encoding="utf-8", errors="replace")
    except OSError as error:
        raise RunFailed(f"cannot run {path.name}: {error.strerror or error}") from None
    kept: deque[str] = deque()
    size = 0
    assert process.stdout is not None
    with process.stdout:
        for raw in process.stdout:
            line = raw.rstrip("\r\n")
            kept.append(line)
            size += len(line) + 1
            while size > OUTPUT_BYTES and len(kept) > 1:
                size -= len(kept.popleft()) + 1
            progress({**frame, "detail": line})
    code = process.wait()
    output = "\n".join(kept)
    if code != 0:
        raise RunFailed(f"cadgen run {path.name} exited {code}" + (f"\n{output}" if output else ""))
    return {"script": str(path), "output": output, "documents": documents(path)}
