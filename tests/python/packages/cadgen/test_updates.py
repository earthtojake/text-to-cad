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
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

import cadgen
from cadgen import updates
from cadgen.cli import main as cadgen_main

FEED = {"latest": "0.9.0"}


class UpdatesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.environment({"CADGEN_STATE_DIR": str(self.tmp), "CADGEN_INSTALL_CHANNEL": "claude-github",
                          "CADGEN_AUTO_UPDATED": "", "CI": "", "CADGEN_UPDATE_CHECK": ""})
        version = mock.patch.object(cadgen, "__version__", "0.8.1")
        version.start()
        self.addCleanup(version.stop)

    def environment(self, values: dict[str, str]) -> None:
        patched = mock.patch.dict(os.environ, values)
        patched.start()
        self.addCleanup(patched.stop)

    def read_today(self, feed: dict) -> None:
        (self.tmp / updates.FILE).write_text(json.dumps({"checked": time.time(), "feed": feed}), encoding="utf-8")

    def test_a_copy_that_is_told_is_offered_the_newest_release_while_behind(self) -> None:
        feed = updates.parse_feed(FEED)
        self.assertEqual(updates.offer(feed, "0.8.1", True), "0.9.0")
        for version in ("0.9.0", "1.0.0", "0.9.0.dev1"):  # current, ahead, or not a release to compare
            with self.subTest(version=version):
                self.assertIsNone(updates.offer(feed, version, True))
        self.assertIsNone(updates.offer(feed, "0.1.0", False))  # never, however far behind

    def test_who_is_told_is_what_the_plugins_startup_config_says(self) -> None:
        # A plugin's server environment names its channel, and CADGEN_AUTO_UPDATED=1 where its store
        # or the app that installed it keeps the copy up to date: cadgen decides by that, never by the
        # channel's name. A Viewer a skill opens names nothing, a skills-only install; a development
        # install is never told.
        from cadgen._internal.channel import told

        for values, expected in (
            ({"CADGEN_INSTALL_CHANNEL": "claude-github"}, True),
            ({"CADGEN_INSTALL_CHANNEL": "claude-directory", "CADGEN_AUTO_UPDATED": "1"}, False),
            ({"CADGEN_INSTALL_CHANNEL": "gemini-github", "CADGEN_AUTO_UPDATED": "1"}, False),
            ({"CADGEN_INSTALL_CHANNEL": "a-store-of-tomorrow", "CADGEN_AUTO_UPDATED": "1"}, False),
            ({"CADGEN_INSTALL_CHANNEL": "a-store-of-tomorrow"}, True),
            ({"CADGEN_INSTALL_CHANNEL": ""}, True),
            ({"CADGEN_INSTALL_CHANNEL": "dev"}, False),
        ):
            with self.subTest(values=values), mock.patch.dict(os.environ, values), \
                    mock.patch("cadgen._internal.channel._source_tree", return_value=False):
                self.assertEqual(told(), expected)

    def test_the_notice_reads_the_same_everywhere_like_the_install_message(self) -> None:
        self.read_today(FEED)
        found = updates.notice()
        text = "A new version v0.9.0 of text-to-cad is available (currently on v0.8.1)"
        prompt = "Update text-to-cad to 0.9.0 from https://github.com/earthtojake/text-to-cad"
        self.assertEqual(found, {"latest": "0.9.0", "version": "0.8.1", "text": text, "prompt": prompt,
                                 "instructions": "https://www.texttocad.dev/install"})
        self.assertEqual(updates.line(found), f'{text}. Ask your agent to update to the latest version ("{prompt}"), '
                                              'or install manually (https://www.texttocad.dev/install).')
        # The same words in the CAD Viewer a skill opens, which no plugin names a channel for.
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
        self.assertEqual(updates.parse_feed({"latest": "1.2.3", "minimum": {"claude-directory": "1.0.0"}, "notices": []}),
                         {"latest": "1.2.3"})
        for broken in (None, [], {}, {"latest": "v1.2.3"}, {"latest": 1}):
            with self.subTest(broken=broken):
                self.assertIsNone(updates.parse_feed(broken))

    def test_the_newest_release_is_offered_until_the_install_has_it(self) -> None:
        # Nothing the person does with the update button is kept: the notice stays while behind.
        self.read_today(FEED)
        self.assertEqual([updates.notice()["latest"], updates.notice()["latest"]], ["0.9.0", "0.9.0"])
        self.read_today({"latest": "0.9.1"})
        self.assertEqual(updates.notice()["latest"], "0.9.1")
        with mock.patch.object(cadgen, "__version__", "0.9.1"):
            self.assertIsNone(updates.notice())

    def test_nothing_is_checked_when_turned_off_in_ci_or_for_a_copy_that_is_not_told(self) -> None:
        self.read_today(FEED)
        for values in ({"CADGEN_UPDATE_CHECK": "0"}, {"CI": "true"}, {"CADGEN_INSTALL_CHANNEL": "dev"},
                       {"CADGEN_INSTALL_CHANNEL": "claude-directory", "CADGEN_AUTO_UPDATED": "1"}):
            with self.subTest(values=values), mock.patch.dict(os.environ, values):
                asked: list[str] = []
                self.assertIsNone(updates.notice())
                updates.feed(now=time.time() + 2 * updates.CHECK_SECONDS, get=asked.append)
                self.assertEqual((asked, updates.refresh()), ([], None))

    def test_nothing_waits_on_the_feed(self) -> None:
        # A feed that is due is read in the background, and whatever asks meanwhile -- a page, a launch,
        # a tool's result -- is told from the feed as last read: offline or slow, nothing waits.
        (self.tmp / updates.FILE).write_text(json.dumps({"checked": 0, "feed": FEED}), encoding="utf-8")
        reading, answer = threading.Event(), threading.Event()

        def get(url: str) -> dict:
            reading.set()
            answer.wait(30)
            return {"latest": "0.9.1"}

        with mock.patch.object(updates, "_get", get):
            thread = updates.refresh()
            self.assertTrue(reading.wait(30))
            self.assertEqual(updates.notice()["latest"], "0.9.0")
            self.assertIsNone(updates.refresh(), "a day's read is not asked for twice")
            answer.set()
            thread.join(30)
        self.assertEqual(updates.notice()["latest"], "0.9.1")

    def test_no_command_says_it_or_reads_the_feed(self) -> None:
        # A skill's command cannot tell which plugin, if any, it came with: the CAD app and the CAD
        # Viewer say it, by their channel. (What a command does say once, telemetry's notice, is not this
        # test's: ``cadgen/analytics.py``.)
        self.environment({"DO_NOT_TRACK": "1"})
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(updates, "_get") as get, contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            self.assertEqual(cadgen_main(["telemetry"]), 0)
        get.assert_not_called()
        self.assertEqual(err.getvalue(), "")

if __name__ == "__main__":
    unittest.main()
