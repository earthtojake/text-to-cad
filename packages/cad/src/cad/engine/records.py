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
import re
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
# What cmd.exe reads as an operator in a word outside double quotes: ``pandas>=2`` bare is a redirection.
_OPERATORS = frozenset("<>|&^")


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


def rerun(program: str | os.PathLike, python: str | os.PathLike | None = None,
          given: list[str] | None = None) -> str:
    """The command that runs ``program`` again, as a person pastes it into this platform's shell, as its
    run was made: ``cad run`` and the program, absolute -- the base, or the packages its script's header
    names, which it names again. The engine that says it is the one ``cad run`` reaches, and its python
    has the kernel a bare ``python`` may not. With the requirements ``cad run --with`` was given
    (``given``: its record's ``with``), ``cad run --with`` each of them and the program; a program a run in
    a Python of its own built (``python``: a venv's, with packages the base lacks), that Python and the
    program, which ``cad run`` could not build. Each word is quoted for a POSIX shell (``shlex.quote``);
    on Windows in the double quotes cmd.exe and PowerShell both read, and only where a space, a quote or
    an operator of cmd.exe's needs them (``_windows``) -- to cmd.exe a single quote is part of the path."""
    from cad.engine.said import COMMAND

    def said(words: list[str]) -> str:
        return " ".join(_windows(word) if WINDOWS else shlex.quote(word) for word in words)

    if python:
        return said([os.fspath(python), os.fspath(program)])
    options = [word for requirement in given or () for word in ("--with", requirement)]
    return f"{COMMAND} run {said([*options, os.fspath(program)])}"


def _windows(word: str) -> str:
    """One word as cmd.exe and PowerShell pass it on to a program: the C runtime's quoting
    (``subprocess.list2cmdline``: double quotes around a word holding a space), and the double quotes too
    around a word holding an operator of cmd.exe's (``_OPERATORS``), the backslashes that end it doubled
    before the quote that closes it."""
    said = subprocess.list2cmdline([word])
    if said.startswith('"') or not _OPERATORS.intersection(word):
        return said
    return '"' + re.sub(r"(\\+)$", r"\1\1", said) + '"'


def command(registry: Any, record: dict[str, Any]) -> str | None:
    """The command that builds a model's document again (``rerun``): ``cad run`` of its home, the
    script that defines it, never a program that imported it and called it (a check script), with the
    requirements its last run's ``cad run --with`` was given (its record's ``with``) -- or the Python of
    its own its last run built it with (its record's ``python``) and its home. None for a shape handed
    over, which no run built, and for a file's. The engine never runs it."""
    if record.get("kind") != "model":
        return None
    python, given = record.get("python"), record.get("with")
    return rerun(home(registry, record), python if isinstance(python, str) else None,
                 [item for item in given if isinstance(item, str)] if isinstance(given, list) else None)


def detached(registry: Any, record: dict[str, Any]) -> bool:
    """Whether the script or the file a record points at is gone (moved, deleted). A shape handed
    over points at nothing that builds it: never detached."""
    return record.get("kind") != "shape" and not home(registry, record).is_file()
