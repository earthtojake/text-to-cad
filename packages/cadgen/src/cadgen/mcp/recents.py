"""Recently opened models, shared by every server process of every version.

The store is an append-only log of events -- ``open``, ``pin``, ``unpin``,
``remove``, ``thumb`` -- folded into a list on read. It is user state, not a
derived artifact, so it lives in the state directory and never in the cadgen
cache (the cache holds only what file bytes imply).

Several processes append at once: one per thread, and after an update, old and
new versions side by side. So each write appends one line under an exclusive
lock, readers skip lines they cannot parse and events they do not know, and
compaction writes a new file and renames it into place under the same lock.
Nothing is ever migrated in place.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

SCHEMA = 1
LIMIT = 200
COMPACT_AFTER = 2000


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

    def public(self) -> dict[str, Any]:
        exists = os.path.isfile(self.path)
        return {
            "path": self.path,
            "name": os.path.basename(self.path),
            "folder": os.path.dirname(self.path),
            "opened": self.opened,
            "pinned": self.pinned,
            "missing": not exists,
            "thumbnail": self.thumbnail,
        }


class RecentStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = (root or state_dir()) / "codex"
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
        self.thumbnails.mkdir(parents=True, exist_ok=True)
        target = self.thumbnails / name
        if not target.exists():
            partial = target.with_suffix(f".{os.getpid()}.tmp")
            partial.write_bytes(png)
            os.replace(partial, target)
        self._append({"op": "thumb", "path": path, "thumbnail": name})
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
            elif op == "thumb" and path in entries and isinstance(event.get("thumbnail"), str):
                entries[path].thumbnail = event["thumbnail"]
        ordered = sorted(entries.values(), key=lambda entry: (not entry.pinned, -entry.opened))
        return ordered[:LIMIT]

    def _events(self) -> Iterator[dict[str, Any]]:
        try:
            lines = self.log.read_text(encoding="utf-8").splitlines()
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

    def _append(self, event: dict[str, Any]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        line = json.dumps({"v": SCHEMA, "t": time.time(), **event}, separators=(",", ":")) + "\n"
        with self._locked():
            with open(self.log, "a", encoding="utf-8") as handle:
                handle.write(line)
            self._compact_if_long()

    def _compact_if_long(self) -> None:
        try:
            with open(self.log, encoding="utf-8") as handle:
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
                folded.append({"v": SCHEMA, "t": entry.opened, "op": "thumb", "path": entry.path, "thumbnail": entry.thumbnail})
        partial = self.log.with_suffix(f".{os.getpid()}.tmp")
        partial.write_text("".join(json.dumps(event, separators=(",", ":")) + "\n" for event in folded), encoding="utf-8")
        os.replace(partial, self.log)

    @contextlib.contextmanager
    def _locked(self):
        lock_path = self.root / "recents.lock"
        with open(lock_path, "a+b") as handle:
            if sys.platform == "win32":
                import msvcrt

                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
                try:
                    yield
                finally:
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
