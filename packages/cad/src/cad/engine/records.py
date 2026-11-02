"""The documents' records, read: what a model's run asks of the engine's registry in its own process.

Each document the engine knows has one record, ``<state>/documents/<id>/document.json`` in the user's state
folder (``places.state_dir``), which the engine's registry writes (``cad_server.engine.registry``, the server's).
A model's script and its worker read a record of it now and then -- the file that claims an explicit name
(``identity.claimed``), where a moved script's document was built (``build._relocation``) -- and write none:
so the library reads them here, by the registry's one shape (``parse``), and the words the engine says of a
record (``home``, ``rerun``) are worked out here too. A model's document's bytes, as the engine's cache keeps
them, are ``<cache>/documents/<id>/document.xbf`` (``FILE``), regenerable and never a record.
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
from pathlib import Path
from typing import Any

from cad.engine.ids import is_id

__all__ = ["DOCUMENTS", "FILE", "RECORD", "SCHEMA", "Records", "command", "current", "detached", "home", "parse",
           "program", "relative", "rerun"]

SCHEMA = 1
DOCUMENTS = "documents"
RECORD = "document.json"
# A model document's bytes in the engine's cache folder (``cache``): ``documents/<id>/document.xbf``.
FILE = "document.xbf"
WINDOWS = os.name == "nt"


def parse(ident: str, data: bytes | None) -> dict[str, Any] | None:
    """The record of document ``ident`` its file's bytes hold, or None: none, or a file this schema does
    not read."""
    if data is None:
        return None
    try:
        record = json.loads(data)
    except ValueError:
        return None
    if not isinstance(record, dict) or record.get("schema") != SCHEMA or record.get("id") != ident:
        return None
    return record


class Records:
    """The documents' records under ``<state>/documents``, read alone."""

    def __init__(self, state: Path | str) -> None:
        self.root_folder = Path(state)

    def get(self, ident: str) -> dict[str, Any] | None:
        """The record of document ``ident``, or None (none, or a file this schema does not read)."""
        if not is_id(ident):
            return None
        try:
            data = (self.root_folder / DOCUMENTS / ident / RECORD).read_bytes()
        except OSError:
            return None
        return parse(ident, data)

    def root(self, record: dict[str, Any]) -> Path:
        """The folder a record's paths are relative to: its ``root``."""
        return Path(record["root"])


def current() -> Records:
    """The records of the user's state folder, where it is now (``CAD_STATE_DIR`` is read each time)."""
    from cad.engine.places import state_dir

    return Records(state_dir())


def relative(path: Path | str, root: Path | str) -> str:
    """``path`` as a record keeps it: relative to ``root``, with ``/``; absolute where it cannot be
    (another drive)."""
    try:
        return Path(os.path.relpath(os.fspath(path), os.fspath(root))).as_posix()
    except ValueError:
        return Path(path).as_posix()


def home(registry: Any, record: dict[str, Any]) -> Path:
    """A record's script (a model's) or file (a file's), absolute."""
    return Path(os.path.normpath(registry.root(record) / record["home"]))


def program(registry: Any, record: dict[str, Any]) -> Path | None:
    """The program that handed a shape over, absolute; None for any other record, and for a shape
    handed over from a Python session (a REPL, a notebook)."""
    given = record.get("program") if record.get("kind") == "shape" else None
    return Path(os.path.normpath(registry.root(record) / given)) if given else None


def rerun(program: str | os.PathLike, python: str | os.PathLike | None = None) -> str:
    """The command that runs ``program`` again, as a person pastes it into this platform's shell:
    ``cad run`` and the program, absolute. The engine that says it is the one ``cad run``
    reaches, and its python has the kernel a bare ``python`` may not. A program a run in a Python of
    its own built (its record's ``python``: a venv's, with packages the base lacks) is run again by
    that Python, which ``cad run`` is not: that Python and the program. Each word is quoted for a
    POSIX shell (``shlex.quote``); on Windows in the double quotes cmd.exe and PowerShell both read,
    and only where a space or a quote needs them (``subprocess.list2cmdline``) -- to cmd.exe a
    single quote is part of the path."""
    from cad.engine.said import COMMAND

    words = [os.fspath(python), os.fspath(program)] if python else [os.fspath(program)]
    said = subprocess.list2cmdline(words) if WINDOWS else " ".join(shlex.quote(word) for word in words)
    return said if python else f"{COMMAND} run {said}"


def command(registry: Any, record: dict[str, Any]) -> str | None:
    """The command that builds a model's document again (``rerun``): ``cad run`` of its home, the
    script that defines it, never a program that imported it and called it (a check script) -- or the
    Python of its own its last run built it with (its record's ``python``) and its home. None for a
    shape handed over, which no run built, and for a file's. The engine never runs it."""
    if record.get("kind") != "model":
        return None
    python = record.get("python")
    return rerun(home(registry, record), python if isinstance(python, str) else None)


def detached(registry: Any, record: dict[str, Any]) -> bool:
    """Whether the script or the file a record points at is gone (moved, deleted). A shape handed
    over points at nothing that builds it: never detached."""
    return record.get("kind") != "shape" and not home(registry, record).is_file()
