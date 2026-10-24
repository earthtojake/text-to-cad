"""Recents: the engine's registry of documents, as every CAD view's home lists it.

Every CAD view writes here -- the MCP app's views and the CAD Viewer -- and every
home shows all of it (``GET /__cad/recents``, which the MCP app's views reach
through its tunnel).

Recents is a view of the registry (``cadgen.engine.registry``, ``<state>/documents/<id>/document.json``):
a CAD file opened on a page is a record of its own (``kind: "file"``: its path, when it was opened,
whether it is pinned), and every model a script built is one already (``kind: "model"``, which the
engine writes when it registers the build). ``memory`` documents have none, so they are never
listed. The home's picture of each is UI state on its record (``preview``), the PNG under
``recents/thumbnails`` named by its content. Removing an entry deletes its record, and a copied
model's bundle with it; nothing is removed on its own: a model whose script is gone stays listed,
``missing``, until the person removes it.

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
    opened: float
    pinned: bool = False
    thumbnail: str | None = None
    # When the picture was taken, in seconds: a file changed since has an old one.
    pictured: float | None = None
    kind: str = "file"
    # A model's: its name, its script, and the command that builds it again.
    name: str | None = None
    script: str | None = None
    rebuild: str | None = None
    # A shape handed over (``store: "shape"``): its home is the script or the folder it was handed
    # over from, nothing builds it again, and ``shown`` says so; ``built`` is when it was handed over.
    store: str | None = None
    shown: str | None = None
    built: float | None = None

    def public(self) -> dict[str, Any]:
        on_disk = self.script if self.kind == "model" else self.path
        try:
            status = os.stat(on_disk) if on_disk else None
        except OSError:
            status = None
        exists = status is not None and stat.S_ISREG(status.st_mode)
        shape = self.kind == "model" and self.store == "shape"
        if shape:
            # Its document is the engine's, not its home's: a folder home (a REPL's) is where it came
            # from, and nothing of it goes missing (``registry.detached``).
            exists = True
            status = status if status is not None and stat.S_ISREG(status.st_mode) else None
        found = {
            "path": self.path,
            "name": self.name or os.path.basename(self.path),
            "folder": os.path.dirname(on_disk or ""),
            "opened": self.opened,
            # When the file (a model's script) last changed, in seconds, for "Edited 16h ago"; None once it is gone.
            "modified": (status.st_mtime if status is not None else self.built) if shape else
            status.st_mtime if exists else None,
            "pinned": self.pinned,
            # A file that is gone, or a model whose script is (``detached``): listed, and removable.
            "missing": not exists,
            "thumbnail": self.thumbnail,
            "pictured": self.pictured,
        }
        if self.kind == "model":
            found.update(kind="model", id=self.path, script=self.script, rebuild=self.rebuild)
        if shape:
            found.update(store="shape", shown=self.shown or "a shape handed over: no script to rerun")
        return found


class RecentStore:
    """Recents over the registry of the state folder ``root`` (``state_dir()`` by default)."""

    def __init__(self, root: Path | None = None) -> None:
        from cadgen.engine.registry import Folder, Registry

        self.state = Folder(root or state_dir())
        self.registry = Registry(self.state, cache=cache_dir())
        self.root = self.state.root / "recents"
        self.thumbnails = self.state.path(THUMBNAILS)

    # -- writes ----------------------------------------------------------------

    def opened(self, path: str) -> None:
        """A CAD file opened on a page: its record, opened now."""
        from cadgen.engine.ids import canonical, file_id

        found = canonical(path)
        now = time.time()

        def change(record):
            record = dict(record or {"id": file_id(found), "kind": "file"})
            record.update(root=os.path.dirname(found), home=os.path.basename(found),
                          format=os.path.splitext(found)[1].lower().lstrip("."), opened=now)
            return record

        self.registry.update(file_id(found), change)

    def pin(self, path: str, pinned: bool) -> None:
        self._change(path, lambda record: {**record, "pinned": bool(pinned)})

    def remove(self, path: str) -> None:
        """Forget an entry: its record."""
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

    def _change(self, path: str, change) -> None:
        """A change to an entry's record, when it has one (a file not opened has none)."""
        self.registry.update(self._ident(path), lambda record: change(record) if record is not None else None)

    # -- reads -----------------------------------------------------------------

    def list(self) -> list[Recent]:
        """Pinned first, then most recently opened or built; at most ``LIMIT``."""
        from cadgen.engine import registry as registering

        entries = []
        for record in self.registry.list():
            preview = record.get("preview") or {}
            common = {"pinned": bool(record.get("pinned")), "thumbnail": preview.get("thumbnail"),
                      "pictured": preview.get("pictured")}
            if record.get("kind") == "file" and record.get("opened"):
                entries.append(Recent(path=str(registering.home(self.registry, record)), opened=float(record["opened"]),
                                      **common))
            elif record.get("kind") == "model":
                entries.append(Recent(path=record["id"], kind="model", name=record.get("label") or record.get("entry"),
                                      script=str(registering.home(self.registry, record)),
                                      rebuild=registering.command(self.registry, record),
                                      store=record.get("store"), shown=record.get("shown"), built=record.get("built"),
                                      opened=float(max(record.get("opened") or 0, record.get("built") or 0)), **common))
        ordered = sorted(entries, key=lambda entry: (not entry.pinned, -entry.opened))
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

