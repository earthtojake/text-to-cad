"""Which apps' CAD views never called back: remembered per app, so an app that says it shows views and shows none
is offered no tools for a while (``Server._initialize``), and tried again after.

A view calls back when it syncs (``cad_sync``) or reaches the viewer's routes (``cad_http``): only a view an app
drew can. A session of an app that claimed to show views (it declared them, or Codex's app launched it: never a
Codex nothing speaks for) that showed a model (``cad_show``, ``cad_open``) and had no call back by a later moment is
a miss, decided with no timer: at the session's next agent call, or as the session ends, and only where that moment
is ``GRACE_SECONDS`` or more after the first show, so a card still loading is never taken for one that never
loads. An app is judged once ``MISSES`` sessions missed with no call back between them (one slow chat, a card
scrolled away before it mounted, a person who closed the chat at once, never condemns an app on its own); it is
then offered no tools for ``RETRY_SECONDS`` from its last miss, and tried again after: one more miss judges it
again, and any call back forgets it.

The record is ``mcp-apps.json`` in the data folder of the version that serves (``places.data_dir``), one entry
per app by the name its MCP client gives, ``{"misses": <count>, "at": <seconds since the epoch of the last>}``.
Deleting the file forgets every app. A file that cannot be read or written is no record: a miss is then
forgotten, never a reason a call fails.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

LOG = logging.getLogger("cad_server.mcp")

FILE = "mcp-apps.json"
# How long after the first unanswered show a later moment must come to count the session as a miss: a card
# syncs within a second or two of being drawn, and a slow first page load stays well inside this.
GRACE_SECONDS = 120.0
# How many sessions in a row must miss before an app is offered no tools.
MISSES = 2
# How long a judged app is offered no tools from its last miss, before it is tried again.
RETRY_SECONDS = 7 * 24 * 3600.0
# The longest app name kept (a client names itself; nothing longer is a name).
NAME_LIMIT = 128


def default_path() -> Path:
    """The record of the version this process belongs to: ``mcp-apps.json`` in its data folder."""
    from cad.engine.places import data_dir

    return data_dir() / FILE


class Outcomes:
    """The apps whose views never called back, kept in ``path`` (None: in memory alone, for one process), read
    and written by the clock ``clock`` (seconds since the epoch; a test's own)."""

    def __init__(self, path: Path | None = None, clock: Callable[[], float] = time.time) -> None:
        self.path = path
        self.clock = clock
        self._memory: dict[str, Any] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _name(app: Any) -> str | None:
        return app if isinstance(app, str) and 0 < len(app) <= NAME_LIMIT else None

    def _read(self) -> dict[str, Any]:
        if self.path is None:
            return dict(self._memory)
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def _change(self, app: str, change: Callable[[dict[str, Any] | None], dict[str, Any] | None]) -> None:
        with self._lock:
            if self.path is None:
                after = change(self._memory.get(app))
                if after is None:
                    self._memory.pop(app, None)
                else:
                    self._memory[app] = after
                return
            try:
                from cad._internal.atomic_replace import write_bytes_atomic
                from cad_server._internal.file_lock import state

                self.path.parent.mkdir(parents=True, exist_ok=True)
                with state(self.path.parent):
                    record = self._read()
                    before = record.get(app) if isinstance(record.get(app), dict) else None
                    after = change(before)
                    if after == before:
                        return
                    if after is None:
                        record.pop(app, None)
                    else:
                        record[app] = after
                    write_bytes_atomic(self.path, (json.dumps(record, indent=2, sort_keys=True) + "\n").encode("utf-8"))
            except OSError as error:
                LOG.info("could not keep what %s's views did: %s", app, error)

    def failing(self, app: Any) -> bool:
        """Whether ``app`` is judged (``MISSES`` misses in a row) and its last miss is under ``RETRY_SECONDS`` old."""
        name = self._name(app)
        entry = self._read().get(name) if name else None
        if not isinstance(entry, dict):
            return False
        misses, at = entry.get("misses"), entry.get("at")
        if not isinstance(misses, int) or not isinstance(at, (int, float)):
            return False
        return misses >= MISSES and 0 <= self.clock() - at < RETRY_SECONDS

    def missed(self, app: Any) -> None:
        """A session of ``app`` showed a model and no view called back: one more miss, now. A count that never reached
        ``MISSES`` starts again once its last miss is ``RETRY_SECONDS`` old; a judged app's stays judged."""
        name = self._name(app)
        if name is None:
            return
        now = self.clock()

        def change(entry: dict[str, Any] | None) -> dict[str, Any]:
            misses = entry.get("misses") if isinstance(entry, dict) else None
            at = entry.get("at") if isinstance(entry, dict) else None
            misses = misses if isinstance(misses, int) and misses > 0 else 0
            if misses < MISSES and not (isinstance(at, (int, float)) and 0 <= now - at < RETRY_SECONDS):
                misses = 0
            return {"misses": misses + 1, "at": now}

        self._change(name, change)
        LOG.info("%s showed a model and no CAD view called back", name)

    def answered(self, app: Any) -> None:
        """A view of ``app`` called back: whatever was kept of it is forgotten."""
        name = self._name(app)
        if name is not None and name in self._read():
            self._change(name, lambda _entry: None)
