"""The views this process serves, and the events waiting for each one.

The host starts one server process per thread, so the registry holds that
thread's views: its tab, the tabs the agent opened, a file view. A view is live
while it keeps polling; one that misses two polls is forgotten.

Nothing here reaches into a view. A view long-polls :meth:`ViewRegistry.poll`;
the server queues events for it -- show this model, capture a PNG, describe what
you show -- and the next poll carries them. A question is a request with a reply:
:meth:`ViewRegistry.ask` waits until the view answers through
:meth:`ViewRegistry.reply`.
"""

from __future__ import annotations

import itertools
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

POLL_SECONDS = 20.0
# A view that has not polled for this long is gone (two missed polls).
LIVE_SECONDS = 2 * POLL_SECONDS + 5.0


@dataclass
class View:
    id: str
    surface: str
    thread_id: str | None
    model: str | None = None
    state: dict[str, Any] = field(default_factory=dict)
    seen: float = 0.0
    focused: float = 0.0
    events: list[dict[str, Any]] = field(default_factory=list)


class NoAnswer(Exception):
    """A view did not answer, or answered with an error."""


class ViewRegistry:
    def __init__(self, *, clock=time.monotonic) -> None:
        self._clock = clock
        self._views: dict[str, View] = {}
        self._cond = threading.Condition()
        self._seq = itertools.count(1)
        self._replies: dict[str, dict[str, Any] | None] = {}

    # -- views -----------------------------------------------------------------

    def register(self, view_id: str, *, surface: str, thread_id: str | None, model: str | None) -> View:
        with self._cond:
            view = self._views.get(view_id)
            if view is None:
                view = View(id=view_id, surface=surface, thread_id=thread_id)
                self._views[view_id] = view
            view.model = model if model is not None else view.model
            view.seen = view.focused = self._clock()
            return view

    def report(self, view_id: str, *, model: str | None, state: dict[str, Any], focused: bool) -> None:
        with self._cond:
            view = self._views.get(view_id)
            if view is None:
                return
            view.model = model
            view.state = dict(state)
            view.seen = self._clock()
            if focused:
                view.focused = view.seen

    def live(self, thread_id: str | None = None) -> list[View]:
        """Live views, most recently focused first."""
        with self._cond:
            self._expire()
            views = [view for view in self._views.values() if thread_id is None or view.thread_id in (None, thread_id)]
            return sorted(views, key=lambda view: view.focused, reverse=True)

    def forget(self, view_id: str) -> None:
        with self._cond:
            self._views.pop(view_id, None)
            self._cond.notify_all()

    def _expire(self) -> None:
        cutoff = self._clock() - LIVE_SECONDS
        for view_id in [view_id for view_id, view in self._views.items() if view.seen < cutoff]:
            del self._views[view_id]

    # -- events ----------------------------------------------------------------

    def post(self, view_ids: list[str], event: dict[str, Any]) -> int:
        """Queue ``event`` for each live view in ``view_ids``; return how many took it."""
        delivered = 0
        with self._cond:
            for view_id in view_ids:
                view = self._views.get(view_id)
                if view is not None:
                    view.events.append({"seq": next(self._seq), **event})
                    delivered += 1
            self._cond.notify_all()
        return delivered

    def poll(self, view_id: str, *, timeout: float = POLL_SECONDS, cancelled=lambda: False) -> list[dict[str, Any]]:
        """Wait up to ``timeout`` for events for ``view_id``, then hand them over."""
        deadline = self._clock() + timeout
        with self._cond:
            while True:
                view = self._views.get(view_id)
                if view is None:
                    return [{"type": "unknown-view"}]
                view.seen = self._clock()
                if view.events or cancelled():
                    events, view.events = view.events, []
                    return events
                remaining = deadline - self._clock()
                if remaining <= 0:
                    return []
                # Wake at least every second so a cancelled poll releases its worker.
                self._cond.wait(min(remaining, 1.0))

    # -- questions -------------------------------------------------------------

    def ask(self, view_id: str, kind: str, *, timeout: float = 10.0) -> dict[str, Any]:
        """Ask ``view_id`` what only it knows (``capture``, ``describe``); wait for its reply."""
        request_id = uuid.uuid4().hex
        with self._cond:
            self._replies[request_id] = None
        try:
            if not self.post([view_id], {"type": kind, "requestId": request_id}):
                raise NoAnswer("that view is not open")
            deadline = self._clock() + timeout
            with self._cond:
                while self._replies.get(request_id) is None:
                    remaining = deadline - self._clock()
                    if remaining <= 0:
                        raise NoAnswer("the view did not answer in time; is its tab still open?")
                    self._cond.wait(min(remaining, 1.0))
                reply = self._replies[request_id] or {}
        finally:
            with self._cond:
                self._replies.pop(request_id, None)
        if reply.get("error"):
            raise NoAnswer(str(reply["error"]))
        return reply

    def reply(self, request_id: str, reply: dict[str, Any]) -> bool:
        with self._cond:
            if request_id not in self._replies:
                return False
            self._replies[request_id] = reply
            self._cond.notify_all()
            return True
