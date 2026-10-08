"""The views this process serves, and the events waiting for each one.

The host starts one server process per thread, so the registry holds that
thread's views: its tab, the tabs the agent opened, a file view. A view is live
while it keeps syncing; one that has not synced for :data:`LIVE_SECONDS` is
forgotten.

Nothing here reaches into a view. A view syncs about once a second (``cad_sync``):
it reports what it shows -- its model, and its state whenever that changed, which
is what the agent reads -- and :meth:`ViewRegistry.poll` hands it the events the
server queued for it since (show this model, capture a PNG). A poll never
waits: a host relays every call its views make through a few slots they all
share (Codex holds a call until one frees), so a request held open is a slot
taken from every view's model loads. A capture is a request with a reply:
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

# How often a view polls (the page's own pace, written here once for its docs and tests).
POLL_SECONDS = 1.0
# A view that has not polled for this long is gone. A browser wakes a page hidden for minutes about
# once a minute, so a tab in the background still polls well inside it.
LIVE_SECONDS = 75.0


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

    def __contains__(self, view_id: object) -> bool:
        with self._cond:
            return view_id in self._views

    def view(self, view_id: str) -> View | None:
        with self._cond:
            return self._views.get(view_id)

    def wall(self, moment: float) -> float:
        """A moment on this registry's clock, as wall time: what another process can compare."""
        return time.time() - (self._clock() - moment)

    def register(self, view_id: str, *, surface: str, thread_id: str | None, model: str | None) -> View:
        with self._cond:
            view = self._views.get(view_id)
            if view is None:
                view = View(id=view_id, surface=surface, thread_id=thread_id)
                self._views[view_id] = view
                # New, it is the one the person just opened; after that, focus is what the view reports.
                view.focused = self._clock()
            view.model = model if model is not None else view.model
            view.seen = self._clock()
            return view

    def report(self, view_id: str, *, model: str | None, state: dict[str, Any] | None, focused: bool) -> None:
        """What the view shows now; ``state`` None keeps the last one it sent."""
        with self._cond:
            view = self._views.get(view_id)
            if view is None:
                return
            view.model = model
            if state is not None:
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
            # A capture waiting on this view is answered now, not when it times out.
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
        return delivered

    def poll(self, view_id: str) -> list[dict[str, Any]]:
        """Hand over the events waiting for ``view_id``, at once: a poll never waits (see above). A
        view forgotten while its sync was in flight (it closed) has none."""
        with self._cond:
            view = self._views.get(view_id)
            if view is None:
                return []
            view.seen = self._clock()
            events, view.events = view.events, []
            return events

    # -- captures --------------------------------------------------------------

    def ask(self, view_id: str, kind: str, *, timeout: float = 10.0) -> dict[str, Any]:
        """Ask ``view_id`` for what only it can make (a ``capture``); wait for its reply."""
        request_id = uuid.uuid4().hex
        with self._cond:
            self._replies[request_id] = None
        try:
            if not self.post([view_id], {"type": kind, "requestId": request_id}):
                raise NoAnswer("that view is not open")
            deadline = self._clock() + timeout
            with self._cond:
                while self._replies.get(request_id) is None:
                    if view_id not in self._views:
                        raise NoAnswer("that view closed before it answered")
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
