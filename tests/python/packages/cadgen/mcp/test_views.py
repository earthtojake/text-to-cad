"""The view registry: long-poll delivery, liveness, and question round trips."""

from __future__ import annotations

import threading
import unittest

from cadgen.mcp import views
from cadgen.mcp.views import NoAnswer, ViewRegistry


class _Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


class ViewRegistryTest(unittest.TestCase):
    def test_a_posted_event_wakes_the_waiting_poll(self) -> None:
        registry = ViewRegistry()
        registry.register("v1", surface="tab", thread_id="t", model=None)
        got: list = []
        poller = threading.Thread(target=lambda: got.extend(registry.poll("v1", timeout=5)))
        poller.start()
        self.assertEqual(registry.post(["v1"], {"type": "show", "model": "/a.step"}), 1)
        poller.join(5)
        self.assertEqual([(event["type"], event["model"]) for event in got], [("show", "/a.step")])

    def test_live_views_are_most_recently_focused_first_and_stale_ones_expire(self) -> None:
        clock = _Clock()
        registry = ViewRegistry(clock=clock)
        registry.register("old", surface="tab", thread_id="t", model=None)
        clock.now += 1
        registry.register("new", surface="agent", thread_id="t", model="/b.step")
        self.assertEqual([view.id for view in registry.live("t")], ["new", "old"])
        clock.now += views.LIVE_SECONDS + 1
        registry.report("new", model="/b.step", state={}, focused=False)
        self.assertEqual([view.id for view in registry.live("t")], ["new"])

    def test_a_question_returns_the_views_reply(self) -> None:
        registry = ViewRegistry()
        registry.register("v1", surface="tab", thread_id="t", model="/a.step")

        def answer() -> None:
            (event,) = registry.poll("v1", timeout=5)
            self.assertEqual(event["type"], "capture")
            registry.reply(event["requestId"], {"png": "iVBOR"})

        threading.Thread(target=answer).start()
        self.assertEqual(registry.ask("v1", "capture", timeout=5), {"png": "iVBOR"})

    def test_a_question_fails_loudly_for_a_missing_view_or_an_error_reply(self) -> None:
        registry = ViewRegistry()
        with self.assertRaises(NoAnswer):
            registry.ask("nobody", "capture", timeout=0.1)
        registry.register("v1", surface="tab", thread_id="t", model=None)

        def refuse() -> None:
            (event,) = registry.poll("v1", timeout=5)
            registry.reply(event["requestId"], {"error": "no model is open"})

        threading.Thread(target=refuse).start()
        with self.assertRaisesRegex(NoAnswer, "no model is open"):
            registry.ask("v1", "describe", timeout=5)


if __name__ == "__main__":
    unittest.main()
