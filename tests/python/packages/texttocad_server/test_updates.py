"""cadgen's version check (`cad_server/updates.py`): what each install is told about a newer text-to-cad,
from a feed read at most once an hour or an agent app's newer CAD server, said the same way wherever it
shows, and which release an update moves to. No test reaches the real feed: each one is handed in, or
kept as just read."""

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

import cad_server
from cad_server import updates
from cad_server.cli import main as cadgen_main

FEED = {"latest": "0.9.0"}


class UpdatesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.environment({"CAD_STATE_DIR": str(self.tmp), "CAD_INSTALL_CHANNEL": "claude-github",
                          "CAD_AUTO_UPDATED": "", "CI": "", "CAD_UPDATE_CHECK": ""})
        version = mock.patch.object(cad_server, "__version__", "0.8.1")
        version.start()
        self.addCleanup(version.stop)
        seen = mock.patch.object(updates, "_seen", set())
        seen.start()
        self.addCleanup(seen.stop)

    def environment(self, values: dict[str, str]) -> None:
        patched = mock.patch.dict(os.environ, values)
        patched.start()
        self.addCleanup(patched.stop)

    def just_read(self, feed: dict) -> None:
        (self.tmp / updates.FILE).write_text(json.dumps({"checked": time.time(), "feed": feed}), encoding="utf-8")

    def test_a_copy_that_is_told_is_offered_the_newest_release_while_behind(self) -> None:
        feed = updates.parse_feed(FEED)
        self.assertEqual(updates.offer(feed, "0.8.1", True), "0.9.0")
        for version in ("0.9.0", "1.0.0", "0.9.0.dev1"):  # current, ahead, or not a release to compare
            with self.subTest(version=version):
                self.assertIsNone(updates.offer(feed, version, True))
        self.assertIsNone(updates.offer(feed, "0.1.0", False))  # never, however far behind

    def test_who_is_told_is_what_the_plugins_startup_config_says(self) -> None:
        # A plugin's server environment names its channel, and CAD_AUTO_UPDATED=1 where its store
        # or the app that installed it keeps the copy up to date: cadgen decides by that, never by the
        # channel's name. A Viewer a skill opens names nothing, a skills-only install; a development
        # install is never told.
        from cad_server._internal.channel import told

        for values, expected in (
            ({"CAD_INSTALL_CHANNEL": "claude-github"}, True),
            ({"CAD_INSTALL_CHANNEL": "claude-directory", "CAD_AUTO_UPDATED": "1"}, False),
            ({"CAD_INSTALL_CHANNEL": "gemini-github", "CAD_AUTO_UPDATED": "1"}, False),
            ({"CAD_INSTALL_CHANNEL": "a-store-of-tomorrow", "CAD_AUTO_UPDATED": "1"}, False),
            ({"CAD_INSTALL_CHANNEL": "a-store-of-tomorrow"}, True),
            ({"CAD_INSTALL_CHANNEL": ""}, True),
            ({"CAD_INSTALL_CHANNEL": "dev"}, False),
        ):
            with self.subTest(values=values), mock.patch.dict(os.environ, values), \
                    mock.patch("cad_server._internal.channel._source_tree", return_value=False):
                self.assertEqual(told(), expected)

    def test_the_notice_is_the_release_and_a_text_app_s_line_names_the_install_command(self) -> None:
        self.just_read(FEED)
        found = updates.notice()
        self.assertEqual(found, {"latest": "0.9.0", "version": "0.8.1"})
        self.assertEqual(updates.line(found, "posix"), "text-to-cad 0.9.0 is out (this is 0.8.1); to update every agent "
                                                       "app here, run: curl -fsSL https://texttocad.dev/install.sh | sh")
        self.assertTrue(updates.line(found, "nt").endswith("run: irm https://www.texttocad.dev/install.ps1 | iex"))
        # The same in the CAD Viewer a skill opens, which no plugin names a channel for.
        with mock.patch.dict(os.environ, {"CAD_INSTALL_CHANNEL": ""}), \
                mock.patch("cad_server._internal.channel._source_tree", return_value=False):
            self.assertEqual(updates.notice(), found)

    def test_an_app_s_newer_server_shows_the_release_with_no_network(self) -> None:
        """A shim whose release is newer than the engine's proves a release exists: the button shows,
        with no feed read, and an update moves to it; an older or a broken one is no release."""
        with mock.patch.object(updates, "_get", side_effect=AssertionError("the network")), \
                mock.patch.dict(os.environ, {"CAD_UPDATE_CHECK": "0"}):
            self.assertIsNone(updates.notice())
            for said in ("0.8.0", "0.8.1", "not a release", None):
                updates.see(said)
            self.assertIsNone(updates.notice())
            updates.see("0.9.2")
            self.assertEqual(updates.notice(), {"latest": "0.9.2", "version": "0.8.1"})
            self.assertEqual(updates.newest(), "0.9.2")

    def test_a_store_s_copy_is_offered_the_release_its_plugin_moved_to_and_reads_the_feed_when_asked(self) -> None:
        """A store updates the plugin, never the device's engine: a newer server's release is offered to
        its copy too (never the feed's), and an update the person asks for reads the feed; a development
        install is offered nothing."""
        self.just_read({"latest": "0.9.5"})
        updates.see("0.9.2")
        with mock.patch.dict(os.environ, {"CAD_INSTALL_CHANNEL": "claude-directory", "CAD_AUTO_UPDATED": "1"}):
            self.assertEqual(updates.notice(), {"latest": "0.9.2", "version": "0.8.1"})
            asked: list[str] = []
            with mock.patch.object(updates, "_get", lambda url: asked.append(url) or {"latest": "0.9.6"}):
                self.assertEqual(updates.newest(), "0.9.6")
            self.assertEqual(len(asked), 1)
        with mock.patch.dict(os.environ, {"CAD_INSTALL_CHANNEL": "dev"}):
            self.assertIsNone(updates.notice())

    def test_an_update_reads_the_feed_now_and_moves_to_the_newest_it_knows(self) -> None:
        self.just_read(FEED)  # just read: a click reads it again all the same
        asked: list[str] = []
        with mock.patch.object(updates, "_get", lambda url: asked.append(url) or {"latest": "0.9.1"}):
            self.assertEqual(updates.newest(), "0.9.1")
            self.assertEqual(len(asked), 1)
            updates.see("0.10.0")
            self.assertEqual(updates.newest(), "0.10.0")
        with mock.patch.object(updates, "_get", return_value=None), mock.patch.object(updates, "_seen", set()):
            self.assertEqual(updates.newest(), "0.9.1", "a feed out of reach: the feed as last read")
        with mock.patch.object(cad_server, "__version__", "0.10.0"), mock.patch.object(updates, "_get", return_value=None):
            self.assertIsNone(updates.newest(), "this is the newest")

    def test_the_feed_is_read_at_most_once_an_hour_and_kept_when_unreachable(self) -> None:
        asked: list[str] = []
        answers = [FEED, None, {"latest": "0.9.1"}]
        get = lambda url: asked.append(url) or answers.pop(0)  # noqa: E731
        start = 1_000_000.0
        self.assertEqual(updates.feed(get=get, now=start)["latest"], "0.9.0")
        self.assertEqual(asked, ["https://api.texttocad.dev/v1/versions"])
        updates.feed(get=get, now=start + updates.CHECK_SECONDS - 60)
        self.assertEqual(len(asked), 1)
        # Unreachable an hour later: the feed as last read stands, and is not asked again that hour.
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
        self.just_read(FEED)
        self.assertEqual([updates.notice()["latest"], updates.notice()["latest"]], ["0.9.0", "0.9.0"])
        self.just_read({"latest": "0.9.1"})
        self.assertEqual(updates.notice()["latest"], "0.9.1")
        with mock.patch.object(cad_server, "__version__", "0.9.1"):
            self.assertIsNone(updates.notice())

    def test_nothing_is_checked_when_turned_off_in_ci_or_for_a_copy_that_is_not_told(self) -> None:
        self.just_read(FEED)
        for values in ({"CAD_UPDATE_CHECK": "0"}, {"CI": "true"}, {"CAD_INSTALL_CHANNEL": "dev"},
                       {"CAD_INSTALL_CHANNEL": "claude-directory", "CAD_AUTO_UPDATED": "1"}):
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
            self.assertIsNone(updates.refresh(), "an hour's read is not asked for twice")
            answer.set()
            thread.join(30)
        self.assertEqual(updates.notice()["latest"], "0.9.1")

    def test_no_command_says_it_or_reads_the_feed(self) -> None:
        # A skill's command cannot tell which plugin, if any, it came with: the CAD app and the CAD
        # Viewer say it, by their channel. (What a command does say once, telemetry's notice, is not this
        # test's: ``cad_server/analytics.py``.)
        self.environment({"DO_NOT_TRACK": "1"})
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(updates, "_get") as get, contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            self.assertEqual(cadgen_main(["telemetry"]), 0)
        get.assert_not_called()
        self.assertEqual(err.getvalue(), "")

if __name__ == "__main__":
    unittest.main()
