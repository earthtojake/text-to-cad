"""Recently opened models: one library for everywhere a person opens models.

Every CAD view writes here -- the MCP app's views and the CAD Viewer -- and every
home shows all of it (``GET /__cad/recents``, which the MCP app's views reach
through its tunnel).

The store is an append-only log of events -- ``open``, ``pin``, ``unpin``,
``remove``, ``picture`` -- folded into a list on read. It is user state, not a
derived artifact, so it lives in the state directory and never in the cadgen
cache (the cache holds only what file bytes imply).

Several processes append at once: an MCP server per thread, the Viewer, and
after an update, old and new versions side by side. So each write appends
one line under an exclusive lock, readers skip lines they cannot parse and events
they do not know, and compaction writes a new file and renames it into place
under the same lock. Nothing is ever migrated in place.

A model's picture is a ``picture`` event: the model framed whole from the default
direction at a card's size, on transparency, taken once its view has settled; its
time is when it was taken (``pictured``), so a file changed since has an old one.
Every rebuilt revision a view pictures adds a PNG, so a picture no listed model
shows is deleted once it is old enough that no writer can still be about to name
it (a writer saves the PNG, then appends its event). The
screenshots of whatever the view showed that came before it were ``thumb`` events,
which this reader does not know, so a model shows no picture until a view shows it
again -- then its canonical one.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

from cadgen._internal.atomic_replace import write_bytes_atomic
from cadgen._internal.file_lock import exclusive

SCHEMA = 1
LIMIT = 200
COMPACT_AFTER = 2000
MAX_THUMBNAIL_BYTES = 512 * 1024
THUMBNAIL_GRACE_SECONDS = 600


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


@dataclass
class Recent:
    path: str
    opened: float
    pinned: bool = False
    thumbnail: str | None = None
    # When the picture was taken, in seconds: a file changed since has an old one.
    pictured: float | None = None

    def public(self) -> dict[str, Any]:
        try:
            status = os.stat(self.path)
        except OSError:
            status = None
        exists = status is not None and stat.S_ISREG(status.st_mode)
        return {
            "path": self.path,
            "name": os.path.basename(self.path),
            "folder": os.path.dirname(self.path),
            "opened": self.opened,
            # When the file last changed, in seconds, for "Edited 16h ago"; None once it is gone.
            "modified": status.st_mtime if exists else None,
            "pinned": self.pinned,
            "missing": not exists,
            "thumbnail": self.thumbnail,
            "pictured": self.pictured,
        }


class RecentStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = (root or state_dir()) / "recents"
        self.log = self.root / "recents.jsonl"
        self.thumbnails = self.root / "thumbnails"

    # -- writes ----------------------------------------------------------------

    def opened(self, path: str) -> None:
        self._append({"op": "open", "path": path})

    def pin(self, path: str, pinned: bool) -> None:
        self._append({"op": "pin" if pinned else "unpin", "path": path})

    def remove(self, path: str) -> None:
        self._append({"op": "remove", "path": path})

    def thumbnail(self, path: str, png: bytes) -> str:
        """Keep a PNG for ``path``; return its content name."""
        name = hashlib.sha256(png).hexdigest()[:32] + ".png"
        target = self.thumbnails / name
        if not target.exists():
            write_bytes_atomic(target, png)
        self._append({"op": "picture", "path": path, "thumbnail": name}, sweep=True)
        return name

    def read_thumbnail(self, name: str) -> bytes | None:
        if not name or "/" in name or "\\" in name or not name.endswith(".png"):
            return None
        try:
            return (self.thumbnails / name).read_bytes()
        except OSError:
            return None

    # -- reads -----------------------------------------------------------------

    def list(self) -> list[Recent]:
        """Pinned first, then most recently opened; at most ``LIMIT``."""
        entries: dict[str, Recent] = {}
        for event in self._events():
            path, op = event.get("path"), event.get("op")
            if not isinstance(path, str):
                continue
            if op == "open":
                entry = entries.get(path)
                if entry is None:
                    entries[path] = Recent(path=path, opened=float(event.get("t", 0)))
                else:
                    entry.opened = float(event.get("t", entry.opened))
            elif op in ("pin", "unpin") and path in entries:
                entries[path].pinned = op == "pin"
            elif op == "remove":
                entries.pop(path, None)
            elif op == "picture" and path in entries and isinstance(event.get("thumbnail"), str):
                entries[path].thumbnail = event["thumbnail"]
                entries[path].pictured = float(event.get("t", 0)) or None
        ordered = sorted(entries.values(), key=lambda entry: (not entry.pinned, -entry.opened))
        return ordered[:LIMIT]

    def _events(self) -> Iterator[dict[str, Any]]:
        try:
            lines = self.log.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            return
        for line in lines:
            try:
                event = json.loads(line)
            except ValueError:
                continue  # a torn or foreign line
            if isinstance(event, dict) and event.get("v") == SCHEMA:
                yield event

    # -- the log ---------------------------------------------------------------

    def _append(self, event: dict[str, Any], *, sweep: bool = False) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        line = json.dumps({"v": SCHEMA, "t": time.time(), **event}, separators=(",", ":")) + "\n"
        with self._locked():
            with open(self.log, "a", encoding="utf-8") as handle:
                handle.write(line)
            self._compact_if_long()
            if sweep:
                self._sweep_thumbnails()

    def _sweep_thumbnails(self) -> None:
        shown = {entry.thumbnail for entry in self.list() if entry.thumbnail}
        cutoff = time.time() - THUMBNAIL_GRACE_SECONDS
        try:
            pictures = list(self.thumbnails.glob("*.png"))
        except OSError:
            return
        for picture in pictures:
            try:
                if picture.name not in shown and picture.stat().st_mtime < cutoff:
                    picture.unlink()
            except OSError:
                continue

    def _compact_if_long(self) -> None:
        try:
            with open(self.log, encoding="utf-8", errors="replace") as handle:
                count = sum(1 for _ in handle)
        except OSError:
            return
        if count <= COMPACT_AFTER:
            return
        folded = []
        for entry in reversed(self.list()):
            folded.append({"v": SCHEMA, "t": entry.opened, "op": "open", "path": entry.path})
            if entry.pinned:
                folded.append({"v": SCHEMA, "t": entry.opened, "op": "pin", "path": entry.path})
            if entry.thumbnail:
                folded.append({"v": SCHEMA, "t": entry.pictured or entry.opened, "op": "picture", "path": entry.path, "thumbnail": entry.thumbnail})
        write_bytes_atomic(self.log, "".join(json.dumps(event, separators=(",", ":")) + "\n" for event in folded).encode("utf-8"))

    def _locked(self):
        return exclusive(self.root / "recents.lock")
