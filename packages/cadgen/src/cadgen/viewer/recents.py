"""Recents: the engine's registry of documents, as every CAD view's home lists it.

Every CAD view writes here, across engine ports: the MCP app's views and the CAD Viewer.
Each home lists the shared registry through ``GET /__cad/recents``.

Recents is a view of ``cadgen.engine.registry``:
``<state>/documents/<id>/document.json``.
A CAD file opened on a page is a record of its own (``kind: "file"``: its path, when it was first
opened, ``created``, and last, ``opened``, whether it is pinned), and every model a script built is one already (``kind: "model"``, which the
engine writes when it registers the build), as is every shape a program handed over (``kind:
"shape"``). The home's picture of each is UI state on its record (``preview``), the PNG under
``recents/thumbnails`` named by its content. Removing a file's entry forgets its record, the file
untouched; a model's entry is deleted with its document (``cadgen.engine.models.delete``: its record
and its document in the engine's cache). Nothing goes on its own: a model whose script is gone stays
listed, ``missing``, until the person deletes it.

A file is named by its canonical path (``cadgen.engine.ids.canonical``), the engine's, and its
record by that path's id, so a symlink and its target, or two spellings of one file, are one
entry. A model is named by its id, which is also the ``path`` the home opens it by (``/<id>``).

Every write goes through the registry's one owner of the state folder (``registry.Folder``), and
lands whole. Each record is its own file, so two processes opening different files never meet; a
change of one record is a read and a write under the registry's lock.
"""

from __future__ import annotations

import hashlib
import os
import stat
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

LIMIT = 200
MAX_THUMBNAIL_BYTES = 512 * 1024
THUMBNAIL_GRACE_SECONDS = 600
THUMBNAILS = "recents/thumbnails"


def thumbnail_png(encoded) -> bytes:
    """A thumbnail as a view sends it, base64; ``ValueError`` for anything but a small PNG."""
    import base64
    import binascii

    try:
        png = base64.b64decode(encoded or "", validate=True)
    except (ValueError, binascii.Error) as error:
        raise ValueError("the thumbnail is not base64") from error
    if not png.startswith(b"\x89PNG") or len(png) > MAX_THUMBNAIL_BYTES:
        raise ValueError("a thumbnail is a PNG of at most 512 KiB")
    return png


def state_dir() -> Path:
    """Where this user's CAD state lives (``CADGEN_STATE_DIR`` overrides it)."""
    override = os.environ.get("CADGEN_STATE_DIR")
    if override:
        return Path(override)
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "cadgen"
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / "cadgen-state"
    return Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state") / "cadgen"


def cache_dir() -> Path:
    """Where the engine caches documents' bytes (``documents/<id>/document.xbf``): the platform's
    cache location, which the system and the person treat as disposable -- wiping it loses no
    state, the records stay in ``state_dir``. ``CADGEN_CACHE_DIR`` when set (a relative one made
    absolute once, and written back, so a worker after a ``chdir`` names the same folder), else
    ``$XDG_CACHE_HOME/cadgen`` on POSIX or ``%LOCALAPPDATA%\\cadgen`` on Windows when set, else
    ``~/.cache/cadgen``: the folder cadgen 0.7 kept its store in, by the same rule."""
    override = os.environ.get("CADGEN_CACHE_DIR", "").strip()
    if override:
        root = Path(override).expanduser()
        if not root.is_absolute():
            root = (Path.cwd() / root).resolve()
            os.environ["CADGEN_CACHE_DIR"] = str(root)
        return root
    if os.name == "nt":
        local = os.environ.get("LOCALAPPDATA", "").strip()
        if local:
            return Path(local) / "cadgen"
    else:
        xdg = os.environ.get("XDG_CACHE_HOME", "").strip()
        if xdg:
            return Path(xdg) / "cadgen"
    return Path.home() / ".cache" / "cadgen"


@dataclass
class Recent:
    """One entry of Recents: a file's (``path`` its canonical path) or a model's (``path`` its id)."""

    path: str
    # When a page last opened it (the record's ``opened``); None for a model no page has opened.
    opened: float | None
    # When it last changed: a file's mtime (the file itself; None once it is gone), a model's or a
    # shape's run (the record's ``built``). A model's script is never read for it.
    updated: float | None = None
    # When its record was first made (the record's ``created``): a model's first run, a file's first
    # open, a shape's first hand-over; None for a record from before the engine kept it.
    created: float | None = None
    pinned: bool = False
    thumbnail: str | None = None
    # When the picture was taken, in seconds: a document updated since has an old one.
    pictured: float | None = None
    # ``file``, ``model`` or ``shape`` (the record's ``kind``).
    kind: str = "file"
    # A model's (and a shape's): its name, its script, and the command that builds it again.
    name: str | None = None
    namespace: str | None = None
    script: str | None = None
    rebuild: str | None = None
    # A shape handed over: its home is the script or the folder it was handed over from, nothing
    # builds it again, and ``shown`` says so, from the program that handed it over.
    shown: str | None = None

    @property
    def activity(self) -> float:
        """Its last activity, the library's order: the later of when it was opened and updated."""
        return max(self.opened or 0, self.updated or 0)

    def public(self) -> dict[str, Any]:
        """The row a home reads: its times (``opened``, ``updated``, ``created``). Of a model's script only whether
        it is still there is asked (``missing``), never its contents or its times: the engine reads a
        script in a run alone."""
        if self.kind == "file":
            present, folder = self.updated is not None, os.path.dirname(self.path)
        else:
            # A shape's document is the engine's, not its home's: a folder home (a REPL's) is where it
            # came from, and nothing of it goes missing (``registry.detached``).
            present = self.kind == "shape" or bool(self.script and os.path.isfile(self.script))
            folder = self.script if self.script and self.kind == "shape" and os.path.isdir(self.script) \
                else os.path.dirname(self.script or "")
        found = {
            "path": self.path,
            "name": self.name or os.path.basename(self.path),
            # Where it is, as the person reads it: a file's folder, a model's script's.
            "folder": folder,
            "namespace": self.namespace or folder,
            "opened": self.opened,
            "updated": self.updated,
            "created": self.created,
            "pinned": self.pinned,
            # A file that is gone, or a model whose script is (``detached``): listed, and removable.
            "missing": not present,
            "thumbnail": self.thumbnail,
            "pictured": self.pictured,
        }
        found["kind"] = self.kind
        if self.kind != "file":
            found.update(id=self.path, script=self.script, rebuild=self.rebuild)
        if self.kind == "shape":
            found.update(shown=self.shown or "a shape handed over: no script to rerun")
        return found


def _mtime(path: str) -> float | None:
    """A CAD file's time on disk; None once it is gone (or is no file)."""
    try:
        status = os.stat(path)
    except OSError:
        return None
    return status.st_mtime if stat.S_ISREG(status.st_mode) else None


class RecentStore:
    """Recents over the registry of the state folder ``root`` (``state_dir()`` by default)."""

    def __init__(self, root: Path | None = None) -> None:
        from cadgen.engine.registry import Registry

        self.registry = Registry(root or state_dir(), cache=cache_dir())
        self.state = self.registry.state
        self.root = self.state.root / "recents"
        self.thumbnails = self.state.path(THUMBNAILS)

    # -- writes ----------------------------------------------------------------

    def opened(self, path: str) -> dict | None:
        """A CAD file opened on a page: its record, opened now, and made now (``created``) when it had
        none. A model's id: its record (the engine's, written by its run) says when a page opened it,
        and nothing else of it changes. The record as it is now: None for an id no document has."""
        from cadgen.engine.ids import canonical, file_id, is_id

        now = time.time()
        if is_id(path):
            return self._change(path, lambda record: {**record, "opened": now})
        found = canonical(path)

        def change(record):
            record = dict(record or {"id": file_id(found), "kind": "file", "created": now})
            record.update(root=os.path.dirname(found), home=os.path.basename(found), opened=now,
                          namespace=os.path.dirname(found), name=os.path.basename(found))
            return record

        return self.registry.update(file_id(found), change)

    def pin(self, path: str, pinned: bool) -> None:
        self._change(path, lambda record: {**record, "pinned": bool(pinned)})

    def remove(self, path: str) -> None:
        """Forget a file's entry: its record. The file stays where it is."""
        self.registry.delete(self._ident(path))

    def thumbnail(self, path: str, png: bytes) -> str:
        """Keep a PNG for an entry (a file's path, or a model's id): its content name."""
        name = hashlib.sha256(png).hexdigest()[:32] + ".png"
        if not (self.thumbnails / name).exists():
            self.state.write(f"{THUMBNAILS}/{name}", png)
        self._change(path, lambda record: {**record, "preview": {"thumbnail": name, "pictured": time.time()}})
        self._sweep_thumbnails()
        return name

    def read_thumbnail(self, name: str) -> bytes | None:
        if not name or "/" in name or "\\" in name or not name.endswith(".png"):
            return None
        return self.state.read(f"{THUMBNAILS}/{name}")

    def _ident(self, path: str) -> str:
        from cadgen.engine.ids import file_id, is_id

        return path if is_id(path) else file_id(path)

    def _change(self, path: str, change) -> dict | None:
        """A change to an entry's record, when it has one (a file not opened has none): the record as it is now."""
        return self.registry.update(self._ident(path), lambda record: change(record) if record is not None else None)

    # -- reads -----------------------------------------------------------------

    def list(self) -> list[Recent]:
        """Pinned first, then by last activity (``Recent.activity``), newest first; at most ``LIMIT``."""
        from cadgen.engine import registry as registering
        from cadgen.engine.models import Models

        entries = []
        for record in self.registry.list():
            preview = record.get("preview") or {}
            common = {"pinned": bool(record.get("pinned")), "thumbnail": preview.get("thumbnail"),
                      "pictured": preview.get("pictured"), "created": record.get("created")}
            if record.get("kind") == "file" and record.get("opened"):
                path = str(registering.home(self.registry, record))
                entries.append(Recent(path=path, opened=float(record["opened"]), updated=_mtime(path), **common))
            elif record.get("kind") in ("model", "shape"):
                program = registering.program(self.registry, record)
                entries.append(Recent(path=record["id"], kind=record["kind"], name=record.get("name") or record.get("entry"),
                                      namespace=record.get("namespace") or record.get("root"),
                                      script=str(registering.home(self.registry, record)),
                                      rebuild=registering.command(self.registry, record),
                                      shown=Models.shown(str(program) if program else None)
                                      if record["kind"] == "shape" else None, updated=record.get("built"),
                                      opened=record.get("opened"), **common))
        ordered = sorted(entries, key=lambda entry: (not entry.pinned, -entry.activity))
        return ordered[:LIMIT]

    def _sweep_thumbnails(self) -> None:
        """A picture no record shows goes once it is old enough that no writer can still be about to
        name it (a writer saves the PNG, then writes its record)."""
        shown = {(record.get("preview") or {}).get("thumbnail") for record in self.registry.list()}
        cutoff = time.time() - THUMBNAIL_GRACE_SECONDS
        for name in self.state.names(THUMBNAILS):
            try:
                if name.endswith(".png") and name not in shown and (self.thumbnails / name).stat().st_mtime < cutoff:
                    self.state.remove(f"{THUMBNAILS}/{name}")
            except OSError:
                continue

