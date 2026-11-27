"""The project's notices (`cad_server/notices.py`): words the project posts (`/v1/notices`) for every cad older than a
release, read beside PyPI, checked again here as the service checks them (`updates.parse_notices`), kept with what
was last read, and said by a
`cad` command after its own output at most once a day each, by `cad doctor` and by the viewer's server
(`GET /api/v1/server`'s `cadNotices`, its own test file). With none posted, nothing anywhere says anything. No test
reaches the real feed: each feed is written to the state folder as a server keeps it, or handed in."""

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

import cad_server
from cad_server import notices, updates
from cad_server._internal import auto_update

NOTICE = {"id": "install-moved", "below": "0.2.0", "text": "cad now installs another way: run the install command again.",
          "url": "https://texttocad.dev/docs/install"}
PLAIN = {"id": "plain", "below": "1.0.0", "text": "Words alone."}
LINE = "cad: cad now installs another way: run the install command again. (https://texttocad.dev/docs/install)"
FEED = {"latest": "0.1.0", "lines": {"0": "0.1.0"}}


def stand_in(feed: dict):
    """A ``get`` for ``updates.feed``: PyPI's JSON naming ``feed``'s ``latest``, the notices' address ``feed``'s
    ``notices`` (``[]`` where it has none)."""
    def get(url: str):
        if url.endswith("/cad/json"):
            return {"info": {"version": feed["latest"]}, "releases": {feed["latest"]: [{"filename": "cad.whl"}]}}
        return {"notices": feed.get("notices", [])}
    return get


class Case(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.state = self.tmp / "state"
        self.state.mkdir()
        for patch in (mock.patch.dict(os.environ, {"CAD_STATE_DIR": str(self.state), "CAD_CACHE_DIR": str(self.tmp / "cache"),
                                                   "CAD_ENGINE_DIR": str(self.tmp / "engine"), "DO_NOT_TRACK": "1"}),
                      mock.patch.object(cad_server, "__version__", "0.1.0"),
                      mock.patch.object(updates, "checking", return_value=True),
                      # No command reads the feed; were one to, it would find no network.
                      mock.patch.object(updates, "_get", side_effect=AssertionError("no feed is read here"))):
            patch.start()
            self.addCleanup(patch.stop)

    def keep(self, feed: dict | None) -> None:
        """The feed as a server keeps it after its hourly read."""
        (self.state / updates.FILE).write_text(json.dumps({"checked": time.time(), **({"feed": feed} if feed else {})}),
                                               encoding="utf-8")


class ParseTest(Case):
    def test_a_feed_s_notices_are_kept_through_the_cache_and_a_feed_without_any_is_kept_as_before(self) -> None:
        answer = {**FEED, "notices": [NOTICE, PLAIN]}
        self.assertEqual(updates.feed(get=stand_in(answer), force=True, now=1_000_000.0), answer)
        kept = json.loads((self.state / updates.FILE).read_text(encoding="utf-8"))
        self.assertEqual(kept, {"checked": 1_000_000.0, "feed": answer})
        self.assertEqual(updates.feed(fetch=False), answer, "read back from the cache as it was kept")
        # A feed with no notices, or an empty list, is kept exactly as a feed was before notices existed.
        for none in ({}, {"notices": []}, {"notices": [{"id": "BAD"}]}):
            with self.subTest(none=none):
                self.assertEqual(updates.feed(get=stand_in({**FEED, **none}), force=True, now=2_000_000.0), FEED)
                self.assertEqual((self.state / updates.FILE).read_text(encoding="utf-8"),
                                 json.dumps({"checked": 2_000_000.0, "feed": FEED}, sort_keys=True))

    def test_each_notice_is_checked_again_and_one_that_breaks_a_rule_is_dropped_never_raising(self) -> None:
        bad = [
            {**NOTICE, "id": "Install"}, {**NOTICE, "id": ""}, {**NOTICE, "id": "a" * 41}, {**NOTICE, "id": 7},
            {**NOTICE, "below": "0.2"}, {**NOTICE, "below": "v0.2.0"}, {**NOTICE, "below": "0.2.0rc1"}, {**NOTICE, "below": None},
            {**NOTICE, "text": "x" * 241}, {**NOTICE, "text": "two\nlines"}, {**NOTICE, "text": "a\rb"},
            {**NOTICE, "text": "a b"}, {**NOTICE, "text": "tab\there"}, {**NOTICE, "text": "bell\x07"},
            {**NOTICE, "text": "c1\x85"}, {**NOTICE, "text": ""}, {**NOTICE, "text": "   "}, {**NOTICE, "text": None},
            {**NOTICE, "url": "http://texttocad.dev/docs"}, {**NOTICE, "url": "https://example.com/"},
            {**NOTICE, "url": "https://texttocad.dev.example.com/"}, {**NOTICE, "url": "https://texttocad.dev@example.com/"},
            {**NOTICE, "url": "https://www.texttocad.dev/"}, {**NOTICE, "url": "https://github.com/earthtojake/text-to-cad-x"},
            {**NOTICE, "url": "https://github.com/someone/text-to-cad"}, {**NOTICE, "url": "javascript:alert(1)"},
            {**NOTICE, "url": "https://texttocad.dev/a b"}, {**NOTICE, "url": None}, {**NOTICE, "url": 5},
            {**NOTICE, "url": "https://texttocad.dev/" + "a" * 500}, "words", None, [NOTICE],
        ]
        for entry in bad:
            with self.subTest(entry=entry):
                self.assertEqual(updates.parse_notices([entry, {**PLAIN}]), [PLAIN])
        for given in (None, "x", {"id": "a"}, 5):
            with self.subTest(given=given):
                self.assertEqual(updates.parse_notices(given), [])
                self.assertEqual(updates.parse_feed({**FEED, "notices": given}), FEED)
        # What passes: the longest text (an emoji is one character), each kind of link, and only the keys it knows.
        self.assertEqual(updates.parse_notices([{**PLAIN, "text": "\U0001F527" * 240, "more": 1}]),
                         [{**PLAIN, "text": "\U0001F527" * 240}])
        for url in ("https://texttocad.dev", "https://texttocad.dev/docs?x=1#y", "https://github.com/earthtojake/text-to-cad",
                    "https://github.com/earthtojake/text-to-cad/issues/1"):
            with self.subTest(url=url):
                self.assertEqual(updates.parse_notices([{**NOTICE, "url": url}]), [{**NOTICE, "url": url}])
        # An id named twice: the first stands; past the most, none.
        self.assertEqual(updates.parse_notices([NOTICE, {**NOTICE, "text": "again"}]), [NOTICE])
        many = [{**PLAIN, "id": f"n{at}"} for at in range(updates.NOTICES_MAX + 2)]
        self.assertEqual(len(updates.parse_notices(many)), updates.NOTICES_MAX)

    def test_a_notice_is_for_every_cad_older_than_its_release(self) -> None:
        known = {**FEED, "notices": [NOTICE, PLAIN, {**PLAIN, "id": "old", "below": "0.0.9"}]}
        for version, expected in (("0.1.0", [NOTICE, PLAIN]), ("0.1.99", [NOTICE, PLAIN]), ("0.2.0", [PLAIN]),
                                  ("0.10.0", [PLAIN]), ("1.0.0", []), ("2.0.0", []),
                                  ("0.1.0.dev1", []), ("0.1.0-dev.20261113120000", [])):
            with self.subTest(version=version):
                self.assertEqual(updates.notices_for(version, known), expected)
        # Checked again where it is read: a cache another hand wrote is trusted no more than the feed.
        self.assertEqual(updates.notices_for("0.1.0", {**FEED, "notices": [{**NOTICE, "url": "https://example.com/"}]}), [])
        for nothing in (None, {}, FEED, {**FEED, "notices": "x"}):
            with self.subTest(nothing=nothing):
                self.assertEqual(updates.notices_for("0.1.0", nothing), [])

    def test_only_where_this_cad_reads_the_feed(self) -> None:
        self.keep({**FEED, "notices": [NOTICE]})
        self.assertEqual(notices.applying(), [NOTICE])
        self.assertEqual(notices.for_viewer(), [{"id": NOTICE["id"], "text": NOTICE["text"], "url": NOTICE["url"]}])
        with mock.patch.object(updates, "checking", return_value=False):
            self.assertEqual((notices.applying(), notices.for_viewer(), notices.lines()), ([], [], []))
        with mock.patch.object(updates, "feed", side_effect=RuntimeError("x")):
            self.assertEqual((notices.applying(), notices.lines()), ([], []), "never raises")


class LinesTest(Case):
    T0 = 1_000_000.0

    def said(self, at: float) -> list[str]:
        return notices.lines(now=self.T0 + at)

    def test_each_notice_is_said_at_most_once_a_day_by_its_id(self) -> None:
        day = notices.DAY
        self.keep({**FEED, "notices": [NOTICE]})
        self.assertEqual(self.said(0), [LINE])
        self.assertEqual(json.loads((self.state / notices.FILE).read_text(encoding="utf-8")),
                         {"said": {NOTICE["id"]: self.T0}}, "noted as said")
        for at in (1.0, day - 1):
            self.assertEqual(self.said(at), [], at)
        # Another notice posted meanwhile is said at once; the first waits out its day.
        self.keep({**FEED, "notices": [NOTICE, PLAIN]})
        self.assertEqual(self.said(day / 2), ["cad: Words alone."])
        self.assertEqual(self.said(day), [LINE])
        self.assertEqual(self.said(day / 4), [LINE, "cad: Words alone."], "said later than now (a clock set back): long ago")
        # A notice taken down is forgotten; one posted again under its id is said again.
        self.keep({**FEED, "notices": [PLAIN]})
        self.assertEqual(self.said(3 * day), ["cad: Words alone."])
        self.assertEqual(json.loads((self.state / notices.FILE).read_text(encoding="utf-8")),
                         {"said": {"plain": self.T0 + 3 * day}})

    def test_a_record_that_cannot_be_written_says_nothing(self) -> None:
        self.keep({**FEED, "notices": [NOTICE]})
        with mock.patch("cad._internal.atomic_replace.write_bytes_atomic", side_effect=OSError("read-only")):
            self.assertEqual(self.said(0), [])
        (self.state / notices.FILE).write_text("not json", encoding="utf-8")
        self.assertEqual(self.said(0), [LINE], "a record that cannot be read is none")

    def test_with_no_notice_nothing_is_said_or_written(self) -> None:
        for feed in (None, FEED, {**FEED, "notices": []}, {**FEED, "notices": [{**NOTICE, "below": "0.1.0"}]}):
            with self.subTest(feed=feed):
                self.keep(feed)
                self.assertEqual(self.said(0), [])
                self.assertFalse((self.state / notices.FILE).exists())


class CommandTest(Case):
    def run_cad(self, *argv: str) -> tuple[int, str, str]:
        from cad_server import cli

        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), \
                mock.patch("cad_server.cli.doctor._probe_kernel", return_value=("ok", "/site/OCP.pyd")):
            try:
                code = cli.main(list(argv))
            except SystemExit as leaving:
                code = leaving.code
        return code, out.getvalue(), err.getvalue()

    def test_a_command_says_it_on_stderr_after_its_output_once_a_day_and_never_where_it_should_not(self) -> None:
        self.keep({**FEED, "notices": [NOTICE]})
        cache = os.environ["CAD_CACHE_DIR"]
        for argv in (("cache", "dir", "--help"), ("cache", "dir", "--json"), ("doctor",), ("telemetry",), ("requirement",),
                     ("update", "--help")):
            with self.subTest(argv=argv):
                _code, out, err = self.run_cad(*argv)
                self.assertNotIn(LINE, out + err)
        self.assertFalse((self.state / notices.FILE).exists(), "none of them noted it said")
        with mock.patch("cad_server.cli._output_gone", return_value=True):
            self.assertNotIn(LINE, self.run_cad("cache", "dir")[2], "its output's reader gone")
        # Whatever automatic updates are set to.
        auto_update.change(False)
        code, out, err = self.run_cad("cache", "dir")
        self.assertEqual((code, out), (0, f"{cache}\n"), "never on stdout")
        self.assertEqual(err.splitlines()[-1], LINE, "the last line on stderr, after the command's output")
        self.assertNotIn(LINE, self.run_cad("cache", "dir")[2], "once a day")
        (self.state / notices.FILE).unlink()
        code, out, err = self.run_cad("cache", "nope")
        self.assertEqual((code, out, err.splitlines()[-1]), (2, "", LINE), "whatever the command's exit status")

    def test_doctor_lists_each_notice_in_its_report_and_its_json(self) -> None:
        self.keep({**FEED, "notices": [NOTICE, PLAIN]})
        code, out, err = self.run_cad("doctor")
        self.assertEqual(code, 0, err)
        self.assertIn(f"  notice   {LINE[len('cad: '):]}\n  notice   Words alone.\n", out)
        code, out, _err = self.run_cad("doctor", "--json")
        found = [check for check in json.loads(out)["checks"] if check["name"] == "notice"]
        self.assertEqual(found, [{"name": "notice", "status": "warning", "detail": LINE[len("cad: "):]},
                                 {"name": "notice", "status": "warning", "detail": "Words alone."}])
        self.assertFalse((self.state / notices.FILE).exists(), "the report writes nothing")

    def test_with_no_notice_no_command_says_one_and_doctor_lists_none(self) -> None:
        for feed in (None, FEED, {**FEED, "notices": [{**NOTICE, "below": "0.0.1"}]}):
            with self.subTest(feed=feed):
                self.keep(feed)
                cache = os.environ["CAD_CACHE_DIR"]
                self.assertEqual(self.run_cad("cache", "dir"), (0, f"{cache}\n", ""))
                _code, out, _err = self.run_cad("doctor", "--json")
                self.assertNotIn("notice", [check["name"] for check in json.loads(out)["checks"]])
                self.assertNotIn("notice ", self.run_cad("doctor")[1])
                self.assertFalse((self.state / notices.FILE).exists())


if __name__ == "__main__":
    unittest.main()
