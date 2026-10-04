"""cadgen's version check (`cadgen/updates.py`): what each install is told about a newer text-to-cad,
from a feed read at most once a day, said the same way wherever it shows. No test reaches the real
feed: each one is handed in, or kept as already read today."""

from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import cadgen
from cadgen import updates
from cadgen.cli import main as cadgen_main

FEED = {"latest": "0.9.0", "minimum": {"claude-directory": "0.8.2"}}


class UpdatesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.environment({"CADGEN_STATE_DIR": str(self.tmp), "CADGEN_INSTALL_CHANNEL": "github", "CI": "",
                          "CADGEN_UPDATE_CHECK": ""})
        version = mock.patch.object(cadgen, "__version__", "0.8.1")
        version.start()
        self.addCleanup(version.stop)

    def environment(self, values: dict[str, str]) -> None:
        patched = mock.patch.dict(os.environ, values)
        patched.start()
        self.addCleanup(patched.stop)

    def read_today(self, feed: dict) -> None:
        (self.tmp / updates.FILE).write_text(json.dumps({"checked": time.time(), "feed": feed}), encoding="utf-8")

    def test_each_channel_is_offered_what_its_install_needs(self) -> None:
        feed = updates.parse_feed(FEED)
        for where, version, offered in (
            ("github", "0.8.1", "0.9.0"),
            ("unknown", "0.8.1", "0.9.0"),
            ("github", "0.9.0", None),
            ("github", "1.0.0", None),
            # A store's copy is its store's to update, until it falls below the store's minimum.
            ("claude-directory", "0.8.2", None),
            ("claude-directory", "0.8.1", "0.9.0"),
            ("cursor-marketplace", "0.1.0", None),  # no minimum named: never told
            ("a-store-of-tomorrow", "0.1.0", None),  # a channel cadgen never heard of is a store's too
            ("dev", "0.1.0", None),
            ("github", "0.9.0.dev1", None),  # not a release: nothing to compare
        ):
            with self.subTest(where=where, version=version):
                self.assertEqual(updates.offer(feed, version, where), offered)

    def test_the_notice_reads_the_same_everywhere_like_the_install_message(self) -> None:
        self.read_today(FEED)
        found = updates.notice()
        prompt = "Update text-to-cad to 0.9.0 from https://github.com/earthtojake/text-to-cad"
        self.assertEqual(found, {"latest": "0.9.0", "version": "0.8.1",
                                 "text": "text-to-cad 0.9.0 is available (you have 0.8.1)", "prompt": prompt,
                                 "instructions": "https://www.texttocad.dev/install"})
        self.assertEqual(updates.line(found), f'text-to-cad 0.9.0 is available (you have 0.8.1). To update, ask your agent: "{prompt}"')
        # The same words from a store's copy below its minimum, and from a skill's command, which names no channel.
        with mock.patch.dict(os.environ, {"CADGEN_INSTALL_CHANNEL": "claude-directory"}), \
                mock.patch.object(cadgen, "__version__", "0.8.0"):
            self.assertEqual(updates.notice()["prompt"], prompt)
        with mock.patch.dict(os.environ, {"CADGEN_INSTALL_CHANNEL": ""}), \
                mock.patch("cadgen._internal.channel._source_tree", return_value=False):
            self.assertEqual(updates.notice()["prompt"], prompt)

    def test_the_feed_is_read_at_most_once_a_day_and_kept_when_unreachable(self) -> None:
        asked: list[str] = []
        answers = [FEED, None, {"latest": "0.9.1"}]
        get = lambda url: asked.append(url) or answers.pop(0)  # noqa: E731
        start = 1_000_000.0
        self.assertEqual(updates.feed(get=get, now=start)["latest"], "0.9.0")
        self.assertEqual(asked, ["https://api.texttocad.dev/v1/versions"])
        updates.feed(get=get, now=start + 3600)
        self.assertEqual(len(asked), 1)
        # Unreachable a day later: the feed as last read stands, and is not asked again that day.
        self.assertEqual(updates.feed(get=get, now=start + updates.CHECK_SECONDS)["latest"], "0.9.0")
        self.assertEqual(updates.feed(get=get, now=start + updates.CHECK_SECONDS + 60)["latest"], "0.9.0")
        self.assertEqual(len(asked), 2)
        self.assertEqual(updates.feed(get=get, now=start + 2 * updates.CHECK_SECONDS)["latest"], "0.9.1")

    def test_a_feed_is_read_for_what_this_cadgen_knows(self) -> None:
        minimum = {"claude-directory": "1.0.0", "a-new-store": "1.0.0", "openai-directory": "soon", "github": "1.0.0",
                   "Not a channel": "1.0.0"}
        self.assertEqual(updates.parse_feed({"latest": "1.2.3", "minimum": minimum, "notices": []}),
                         {"latest": "1.2.3", "minimum": {"claude-directory": "1.0.0", "a-new-store": "1.0.0"}})
        for broken in (None, [], {}, {"latest": "v1.2.3"}, {"latest": 1}):
            with self.subTest(broken=broken):
                self.assertIsNone(updates.parse_feed(broken))

    def test_a_release_set_aside_is_not_offered_again_but_the_next_is(self) -> None:
        self.read_today(FEED)
        self.assertTrue(updates.dismiss("0.9.0"))
        self.assertIsNone(updates.notice())
        self.read_today({"latest": "0.9.1"})
        self.assertEqual(updates.notice()["latest"], "0.9.1")

    def test_nothing_is_checked_when_turned_off_in_ci_or_from_a_source_tree(self) -> None:
        self.read_today(FEED)
        for values in ({"CADGEN_UPDATE_CHECK": "0"}, {"CI": "true"}, {"CADGEN_INSTALL_CHANNEL": "dev"}):
            with self.subTest(values=values), mock.patch.dict(os.environ, values):
                asked: list[str] = []
                self.assertIsNone(updates.notice(now=time.time() + 2 * updates.CHECK_SECONDS, get=asked.append))
                self.assertEqual(asked, [])

    def test_a_command_says_it_on_stderr_once_a_day(self) -> None:
        self.read_today(FEED)

        def run() -> str:
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                self.assertEqual(cadgen_main(["analytics"]), 0)
            return err.getvalue()

        self.assertIn('ask your agent: "Update text-to-cad to 0.9.0 from https://github.com/earthtojake/text-to-cad"', run())
        self.assertEqual(run(), "")


if __name__ == "__main__":
    unittest.main()
