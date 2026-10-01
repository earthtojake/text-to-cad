"""The update button's answer: GitHub's latest release, kept for a few hours, and nothing on failure."""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from cadgen.mcp.releases import FRESH_SECONDS, latest_release

RELEASE = {"tag_name": "v0.7.5", "html_url": "https://github.com/earthtojake/text-to-cad/releases/tag/v0.7.5"}


class LatestReleaseTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.cache = self.tmp / "state" / "release.json"
        self.asked = 0

    def fetch(self, reply=RELEASE):
        def ask():
            self.asked += 1
            if isinstance(reply, Exception):
                raise reply
            return reply
        return ask

    def test_a_newer_release_is_said_and_kept_for_hours_then_asked_again(self) -> None:
        found = latest_release("0.7.4", cache=self.cache, fetch=self.fetch(), now=1000)
        self.assertEqual(found, {"version": "0.7.5", "url": RELEASE["html_url"], "newer": True})
        # Kept: every view and process shares the one answer while it is fresh.
        self.assertEqual(latest_release("0.7.5", cache=self.cache, fetch=self.fetch(), now=1000 + FRESH_SECONDS - 1)["newer"], False)
        self.assertEqual(self.asked, 1)
        latest_release("0.7.4", cache=self.cache, fetch=self.fetch(), now=1000 + FRESH_SECONDS)
        self.assertEqual(self.asked, 2)

    def test_no_answer_is_none_and_keeps_nothing(self) -> None:
        self.assertIsNone(latest_release("0.7.4", cache=self.cache, fetch=self.fetch(OSError("offline")), now=1000))
        self.assertIsNone(latest_release("0.7.4", cache=self.cache, fetch=self.fetch({"tag_name": "nightly"}), now=1000))
        self.assertFalse(self.cache.exists())
        # A cache someone broke is asked past, not trusted.
        self.cache.parent.mkdir(parents=True)
        self.cache.write_text("{", encoding="utf-8")
        self.assertEqual(latest_release("0.7.4", cache=self.cache, fetch=self.fetch(), now=1000)["version"], "0.7.5")
        self.assertEqual(json.loads(self.cache.read_text(encoding="utf-8"))["version"], "0.7.5")


if __name__ == "__main__":
    unittest.main()
