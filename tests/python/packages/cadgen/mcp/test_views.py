"""The view registry: polled delivery, liveness, focus, and question round trips."""

from __future__ import annotations

import threading
import time
import unittest

from cadgen.mcp import views
from cadgen.mcp.views import NoAnswer, ViewRegistry


class _Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def _answer_next(registry: ViewRegistry, view_id: str, respond) -> threading.Thread:
    """A view polling as the page does, every few milliseconds here, until one event comes."""

    def page() -> None:
        while not (events := registry.poll(view_id)):
            time.sleep(0.002)
        (event,) = events
        respond(event)

    thread = threading.Thread(target=page, daemon=True)
    thread.start()
    return thread


class ViewRegistryTest(unittest.TestCase):
    def test_a_poll_hands_over_what_waits_at_once_and_never_holds_the_call(self) -> None:
        registry = ViewRegistry()
        registry.register("v1", surface="tab", thread_id="t", model=None)
        self.assertEqual(registry.poll("v1"), [])
        self.assertEqual(registry.post(["v1"], {"type": "show", "model": "/a.step"}), 1)
        self.assertEqual([(event["type"], event["model"]) for event in registry.poll("v1")], [("show", "/a.step")])
        self.assertEqual(registry.poll("v1"), [])
        self.assertEqual(registry.poll("gone"), [{"type": "unknown-view"}])

    def test_live_views_are_most_recently_focused_first_and_stale_ones_expire(self) -> None:
        clock = _Clock()
        registry = ViewRegistry(clock=clock)
        registry.register("old", surface="tab", thread_id="t", model=None)
        clock.now += 1
        registry.register("new", surface="agent", thread_id="t", model="/b.step")
        self.assertEqual([view.id for view in registry.live("t")], ["new", "old"])
        # Polling is not focus: every view polls each second. A view says when it has focus.
        clock.now += 1
        registry.register("old", surface="tab", thread_id="t", model=None)
        self.assertEqual([view.id for view in registry.live("t")], ["new", "old"])
        registry.report("old", model=None, state={}, focused=True)
        self.assertEqual([view.id for view in registry.live("t")], ["old", "new"])
        # A tab in the background, whose page the browser wakes about once a minute, stays live.
        clock.now += 61
        registry.report("new", model="/b.step", state={}, focused=False)
        registry.report("old", model=None, state={}, focused=False)
        clock.now += views.LIVE_SECONDS - 1
        registry.report("new", model="/b.step", state={}, focused=False)
        self.assertEqual([view.id for view in registry.live("t")], ["old", "new"])
        clock.now += 2
        self.assertEqual([view.id for view in registry.live("t")], ["new"])

    def test_a_question_returns_the_views_reply(self) -> None:
        registry = ViewRegistry()
        registry.register("v1", surface="tab", thread_id="t", model="/a.step")
        seen: list = []

        def answer(event) -> None:
            seen.append(event["type"])
            registry.reply(event["requestId"], {"png": "iVBOR"})

        _answer_next(registry, "v1", answer)
        self.assertEqual(registry.ask("v1", "capture", timeout=5), {"png": "iVBOR"})
        self.assertEqual(seen, ["capture"])

    def test_a_question_fails_loudly_for_a_missing_view_or_an_error_reply(self) -> None:
        registry = ViewRegistry()
        with self.assertRaises(NoAnswer):
            registry.ask("nobody", "capture", timeout=0.1)
        registry.register("v1", surface="tab", thread_id="t", model=None)
        _answer_next(registry, "v1", lambda event: registry.reply(event["requestId"], {"error": "no model is open"}))
        with self.assertRaisesRegex(NoAnswer, "no model is open"):
            registry.ask("v1", "capture", timeout=5)
        # A view that closes with the question unanswered fails it then, not at its timeout.
        _answer_next(registry, "v1", lambda event: registry.forget("v1"))
        with self.assertRaisesRegex(NoAnswer, "closed before it answered"):
            registry.ask("v1", "capture", timeout=60)


if __name__ == "__main__":
    unittest.main()
