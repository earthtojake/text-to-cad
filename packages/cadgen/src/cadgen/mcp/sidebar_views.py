"""The CAD sidebar's views, which every server process of the person's app can reach.

The host runs one server process per thread, and the sidebar page in a thread of its own, so an
agent's thread never syncs with the sidebar view the person may have used. Each process publishes
its live sidebar views here -- ``<view>.json``: the model, the state ``cad_view`` reads, when a
person last touched it -- and hands each the requests left in its inbox (``<view>.inbox/``) on its
next sync. An agent reads and captures the sidebar view a person touched last, as it does its own
thread's tabs; a capture's answer comes back as ``replies/<request>.json``. A model it shows goes
to its thread's tab instead, unless it names the sidebar's view: the host keeps the sidebar page
running while the person is in a thread, so a model sent there lands where nobody is looking.

Only sidebar views are shared. A thread's tabs are that conversation's, and no other drives them.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cadgen._internal.atomic_replace import write_bytes_atomic

from .views import LIVE_SECONDS

# A sidebar view that says nothing new still refreshes its file this often, which is how others
# know it is open (a file not refreshed for LIVE_SECONDS belongs to a view that has gone).
HEARTBEAT_SECONDS = 5.0


@dataclass
class SidebarView:
    """A sidebar view another process serves, as it last published itself."""

    id: str
    model: str | None
    state: dict[str, Any] = field(default_factory=dict)
    touched: float = 0.0


class SidebarViews:
    def __init__(self, root: Path, *, clock=time.time) -> None:
        self.root = Path(root)
        self._clock = clock
        self._published: dict[str, tuple[str, float]] = {}
        self._touched: dict[str, float] = {}
        self._asked: set[str] = set()

    # -- the process that serves the view ----------------------------------------

    def publish(self, view_id: str, *, model: str | None, state: dict[str, Any] | None, touched: bool) -> None:
        """Say what this process's sidebar view shows; a quiet one only refreshes its file now and then."""
        now = self._clock()
        if touched or view_id not in self._touched:
            self._touched[view_id] = now
        text = json.dumps({"view": view_id, "model": model, "state": state or {}, "touched": self._touched[view_id],
                           "pid": os.getpid()}, sort_keys=True)
        last = self._published.get(view_id)
        if last is not None and last[0] == text and now - last[1] < HEARTBEAT_SECONDS:
            return
        _write(self.root / f"{_name(view_id)}.json", text)
        self._published[view_id] = (text, now)

    def take(self, view_id: str) -> list[dict[str, Any]]:
        """The requests other processes left for this process's sidebar view, oldest first."""
        inbox = self.root / f"{_name(view_id)}.inbox"
        try:
            paths = sorted(inbox.glob("*.json"))
        except OSError:
            return []
        events = []
        for path in paths:
            try:
                event = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                event = None
            path.unlink(missing_ok=True)
            if isinstance(event, dict):
                if event.get("type") == "capture" and isinstance(event.get("requestId"), str):
                    self._asked.add(event["requestId"])
                events.append(event)
        return events

    def answer(self, request_id: str, reply: dict[str, Any]) -> bool:
        """Pass a capture's answer back to the process that asked for it; False if none did."""
        if request_id not in self._asked:
            return False
        self._asked.discard(request_id)
        _write(self.root / "replies" / f"{_name(request_id)}.json", json.dumps(reply))
        return True

    def forget(self, view_id: str) -> None:
        self._published.pop(view_id, None)
        self._touched.pop(view_id, None)
        (self.root / f"{_name(view_id)}.json").unlink(missing_ok=True)
        shutil.rmtree(self.root / f"{_name(view_id)}.inbox", ignore_errors=True)

    # -- any process --------------------------------------------------------------

    def live(self) -> list[SidebarView]:
        """Sidebar views seen lately, the one a person touched last first: another process's only,
        for this process's own are its registry's."""
        now = self._clock()
        views = []
        try:
            paths = list(self.root.glob("*.json"))
        except OSError:
            return []
        for path in paths:
            try:
                age = now - path.stat().st_mtime
                record = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if age > LIVE_SECONDS:
                path.unlink(missing_ok=True)
                shutil.rmtree(path.with_suffix(".inbox"), ignore_errors=True)
                continue
            if not isinstance(record, dict) or not isinstance(record.get("view"), str):
                continue
            if record["view"] in self._published:
                continue
            views.append(SidebarView(id=record["view"], model=record.get("model") if isinstance(record.get("model"), str) else None,
                                     state=record.get("state") if isinstance(record.get("state"), dict) else {},
                                     touched=float(record.get("touched") or 0.0)))
        self._sweep(now)
        return sorted(views, key=lambda view: view.touched, reverse=True)

    def _sweep(self, now: float) -> None:
        """What a view gone some other way, or an ask that timed out, left behind: an inbox with no
        view beside it, and a reply nobody waits for."""
        try:
            leftovers = [*self.root.glob("*.inbox"), *(self.root / "replies").glob("*.json")]
        except OSError:
            return
        for leftover in leftovers:
            try:
                if leftover.suffix == ".inbox" and leftover.with_suffix(".json").exists():
                    continue
                if now - leftover.stat().st_mtime <= LIVE_SECONDS:
                    continue
                if leftover.is_dir():
                    shutil.rmtree(leftover, ignore_errors=True)
                else:
                    leftover.unlink(missing_ok=True)
            except OSError:
                continue

    def post(self, view_id: str, event: dict[str, Any]) -> None:
        """Leave ``event`` for a sidebar view another process serves: it takes it on its next sync."""
        _write(self.root / f"{_name(view_id)}.inbox" / f"{time.time_ns():020d}-{uuid.uuid4().hex}.json", json.dumps(event))

    def ask(self, view_id: str, *, timeout: float = 10.0) -> dict[str, Any] | None:
        """Ask a sidebar view another process serves for a capture; its answer, or None in time."""
        request_id = uuid.uuid4().hex
        reply_path = self.root / "replies" / f"{request_id}.json"
        self.post(view_id, {"type": "capture", "requestId": request_id})
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                reply = json.loads(reply_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                time.sleep(0.05)
                continue
            reply_path.unlink(missing_ok=True)
            return reply if isinstance(reply, dict) else {}
        return None


def _name(identifier: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "_", str(identifier))[:128] or "_"


def _write(path: Path, text: str) -> None:
    # Through a temp file ending .tmp, so a reader globbing *.json never sees half a record.
    write_bytes_atomic(path, text.encode("utf-8"))
