"""Which release is newest (`cad_server/updates.py`): PyPI and the project's notices (`/v1/notices`), read at most once
an hour by a server, in the background, for cad's own update, never the version feed's addresses (`/v1/releases`,
`/v1/versions`, which earlier releases read); and PyPI, asked at once for `cad update`; never said to anyone. No test
reaches the real PyPI or service: each answer is handed in, kept as just read, or a stand-in's on loopback."""

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


def pypi_answer(*releases: str, yanked: tuple[str, ...] = ()) -> dict:
    """PyPI's JSON for cad listing ``releases``, each with one file, yanked where it is in ``yanked``."""
    return {"info": {"version": max(releases, key=lambda r: tuple(map(int, r.split("."))))},
            "releases": {release: [{"filename": f"cad-{release}-py3-none-any.whl", "yanked": release in yanked}]
                         for release in releases}}


def stand_in(feed: dict | None, notices: list | None = None, asked: list | None = None):
    """A ``get`` for ``updates.feed``: PyPI's JSON naming ``feed``'s ``latest``, the notices' address ``{"notices":
    ...}`` (``feed``'s own by default); None for what is None. ``asked``: each URL."""
    def get(url: str):
        if asked is not None:
            asked.append(url)
        if url.endswith("/cad/json"):
            return None if feed is None else pypi_answer(feed["latest"])
        said = (feed or {}).get("notices", []) if notices is None else notices
        return None if said is False else {"notices": said}
    return get


class UpdatesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        # A release's process (a checkout is a development build unless told the version it runs as).
        self.environment({"CAD_STATE_DIR": str(self.tmp), "CAD_INSTALLATION_VERSION": "0.8.1", "CI": "",
                          "CAD_UPDATE_CHECK": ""})
        version = mock.patch.object(cad_server, "__version__", "0.8.1")
        version.start()
        self.addCleanup(version.stop)

    def environment(self, values: dict[str, str]) -> None:
        patched = mock.patch.dict(os.environ, values)
        patched.start()
        self.addCleanup(patched.stop)

    def just_read(self, feed: dict) -> None:
        (self.tmp / updates.FILE).write_text(json.dumps({"checked": time.time(), "feed": feed}), encoding="utf-8")

    def test_every_release_reads_the_feed_but_a_development_build(self) -> None:
        # A development build -- a development version's name, or a source tree not told the version it runs as --
        # reads none. CAD_INSTALL_CHANNEL and CAD_AUTO_UPDATED, which configs of 0.11.11 and earlier set, decide nothing.
        for values, source_tree, expected in (
            ({"CAD_INSTALL_CHANNEL": "claude-directory", "CAD_AUTO_UPDATED": "1"}, False, True),
            ({"CAD_INSTALL_CHANNEL": "dev", "CAD_INSTALLATION_VERSION": ""}, False, True),
            ({"CAD_INSTALLATION_VERSION": ""}, True, False),
            ({"CAD_INSTALLATION_VERSION": "0.8.1"}, True, True),
            ({"CAD_INSTALLATION_VERSION": "0.8.1-dev.20261113120000"}, False, False),
        ):
            with self.subTest(values=values, source_tree=source_tree), mock.patch.dict(os.environ, values), \
                    mock.patch("cad_server._internal.editable._source_tree", return_value=source_tree):
                self.assertEqual(updates.checking(), expected)

    def test_pypi_and_the_notices_are_read_at_most_once_an_hour_and_kept_when_unreachable(self) -> None:
        asked: list[str] = []
        answers = [pypi_answer("0.9.0"), None, pypi_answer("0.9.0", "0.9.1")]
        get = lambda url: asked.append(url) or (answers.pop(0) if url.endswith("/cad/json") else {"notices": []})  # noqa: E731
        start = 1_000_000.0
        self.assertEqual(updates.feed(get=get, now=start), {"latest": "0.9.0"})
        # PyPI's own JSON and the notices: neither address of the version feed, which earlier releases read.
        self.assertEqual(asked, ["https://pypi.org/pypi/cad/json", "https://api.texttocad.dev/v1/notices"])
        updates.feed(get=get, now=start + updates.CHECK_SECONDS - 60)
        self.assertEqual(len(asked), 2)
        # Unreachable an hour later: what was last read stands, and is not asked again that hour.
        self.assertEqual(updates.feed(get=get, now=start + updates.CHECK_SECONDS)["latest"], "0.9.0")
        self.assertEqual(updates.feed(get=get, now=start + updates.CHECK_SECONDS + 60)["latest"], "0.9.0")
        self.assertEqual(len(asked), 4)
        self.assertEqual(updates.feed(get=get, now=start + 2 * updates.CHECK_SECONDS)["latest"], "0.9.1")

    def test_a_yanked_release_is_held_back_and_either_address_failing_leaves_what_it_last_said(self) -> None:
        """Holding a release is yanking it on PyPI: it is never named, no hour waited. PyPI out of reach keeps the
        releases last read and takes the notices; the notices out of reach keep theirs; neither read, nothing new."""
        notice = {"id": "moved", "below": "0.10.0", "text": "Words."}
        yanked = pypi_answer("0.9.0", "0.9.1", "1.0.0", yanked=("0.9.1", "1.0.0"))
        get = lambda url: yanked if url.endswith("/cad/json") else {"notices": [notice]}  # noqa: E731
        self.assertEqual(updates.feed(get=get, now=1_000_000.0), {"latest": "0.9.0", "notices": [notice]})
        self.assertEqual(updates.feed(get=stand_in(None, notices=[]), force=True), {"latest": "0.9.0"},
                         "PyPI down: its release kept, notices taken")
        self.assertEqual(updates.feed(get=stand_in({"latest": "0.9.2"}, notices=False), force=True),
                         {"latest": "0.9.2"})
        self.just_read({"latest": "0.9.2", "notices": [notice]})
        self.assertEqual(updates.feed(get=stand_in({"latest": "0.9.3"}, notices=False), force=True)["notices"],
                         [notice], "the notices down: theirs kept")
        (self.tmp / updates.FILE).unlink()
        self.assertIsNone(updates.feed(get=stand_in(None, notices=[notice]), force=True),
                          "notices alone, no release ever read: nothing kept")
        self.assertIsNone(updates.feed(get=stand_in(None, notices=False), force=True))

    def test_cad_update_asks_pypi_for_the_newest_release_not_yanked_and_keeps_nothing(self) -> None:
        asked: list[str] = []
        answer = lambda found: lambda url: asked.append(url) or found  # noqa: E731
        file = lambda yanked=False: {"filename": "cad.whl", "yanked": yanked, "yanked_reason": None}  # noqa: E731
        releases = {"0.11.11": [file()], "0.12.0": [file(), file()], "0.12.1": [file(True), file()],  # one file left
                    "0.12.2": [file(True)], "0.13.0rc1": [file()], "1.0": [file(True)], "1.1.2": [file(True)],
                    "1.0.0": [file()], "2.0.0": [], "0.12.3": [{"filename": "cad.whl"}]}  # no `yanked`: not yanked
        self.assertEqual(updates.pypi(get=answer({"info": {"version": "1.0.0"}, "releases": releases})),
                         {"latest": "1.0.0"},
                         "a release every file of which is yanked, or that has none, or a pre-release, is none")
        self.assertEqual(asked, ["https://pypi.org/pypi/cad/json"])
        self.assertEqual(updates.pypi(get=answer({"releases": {**releases, "1.0.0": [file(True)]}})),
                         {"latest": "0.12.3"}, "the newest yanked: the newest that is not")
        self.assertEqual(updates.pypi(get=answer({"info": {"version": "0.9.1"}})), {"latest": "0.9.1"},
                         "no list of releases: PyPI's own newest, which leaves yanked ones out")
        for found in (None, {}, {"info": None}, {"info": {"version": "0.9.2rc1"}}, {"info": {"version": 1}},
                      {"info": {"version": "0.9.1"}, "releases": {"0.9.1": [file(True)]}}, {"releases": []}):
            with self.subTest(found=found):
                self.assertIsNone(updates.pypi(get=answer(found)))
        self.environment({updates.PYPI_ENV: "http://127.0.0.1:9/pypi/"})
        updates.pypi(get=answer(None))
        self.assertEqual(asked[-1], "http://127.0.0.1:9/pypi/cad/json", "a test's stand-in")
        self.assertFalse((self.tmp / updates.FILE).exists(), "the feed's file untouched")

    def test_pypi_is_read_from_a_stand_in_and_never_waited_on_past_its_bound(self) -> None:
        import http.server

        quiet, hold = threading.Event(), threading.Event()

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802 - http.server's name
                if self.path.startswith("/slow/"):
                    quiet.set()
                    hold.wait(30)
                body = json.dumps({"info": {"version": "0.9.3"},
                                   "releases": {"0.9.3": [{"filename": "cad.whl", "yanked": False}]}}).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *_args) -> None:
                pass

        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        self.addCleanup(hold.set)  # first: the slow request let go
        self.environment({updates.PYPI_ENV: f"http://127.0.0.1:{server.server_port}/pypi"})
        self.assertEqual(updates.pypi(), {"latest": "0.9.3"})
        self.assertIsNone(updates._get_within(f"http://127.0.0.1:{server.server_port}/slow/cad/json", 0.2))
        self.assertTrue(quiet.is_set(), "asked, and given up on")

    def test_the_feed_is_asked_for_as_cad(self) -> None:
        """The request names cad, the product (``apps/api`` keys nothing on it)."""
        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = b'{"latest": "0.9.1"}'
        with mock.patch("urllib.request.urlopen", return_value=response) as opened:
            self.assertEqual(updates._get("http://127.0.0.1:9/v1/releases"), {"latest": "0.9.1"})
        request = opened.call_args.args[0]
        self.assertEqual((request.get_header("User-agent"), request.get_header("Accept")), ("cad", "application/json"))

    def test_what_is_kept_is_read_for_what_this_cad_knows(self) -> None:
        self.assertEqual(updates.parse_feed({"latest": "1.2.3", "minimum": {"claude-directory": "1.0.0"}, "notices": [],
                                             "lines": {"0": "0.12.3", "1": "1.2.3"}}),  # a release before's: left out
                         {"latest": "1.2.3"})
        for broken in (None, [], {}, {"latest": "v1.2.3"}, {"latest": 1}, {"lines": {"0": "0.12.0"}}):
            with self.subTest(broken=broken):
                self.assertIsNone(updates.parse_feed(broken))

    def test_the_newest_release_is_kept_in_a_file_of_its_own(self) -> None:
        answer = {"latest": "1.4.0"}
        self.assertEqual(updates.feed(get=stand_in(answer), now=1_000_000.0), answer)
        kept = json.loads((self.tmp / updates.FILE).read_text(encoding="utf-8"))
        self.assertEqual(kept, {"checked": 1_000_000.0, "feed": answer}, "kept in a file of its own")
        self.assertEqual(updates.feed(fetch=False), answer)
        # What 0.11.12 to 0.11.18 kept there, with each major's newest: read for its newest alone.
        self.just_read({"latest": "0.11.18", "lines": {"0": "0.11.18"}})
        self.assertEqual(updates.feed(fetch=False), {"latest": "0.11.18"})
        self.assertEqual(updates.feed(get=lambda url: {"info": {"version": "0.11.19"}} if url.endswith("/cad/json")
                                      else None, force=True), {"latest": "0.11.19"}, "PyPI naming its newest alone")

    def test_the_feed_is_kept_where_no_earlier_release_reads_it(self) -> None:
        """Releases 0.10.0 to 0.11.11 keep their feed (``/v1/versions``'s) in ``versions.json`` in the same state
        folder, and read it while a computer is carried over: this build's answer, which may name 0.12.0 or later, is
        kept in a file of its own, and that one is neither read nor written."""
        self.assertEqual(updates.FILE, "releases.json")
        theirs = json.dumps({"checked": 5.0, "feed": {"latest": "0.11.11"}, "dismissed": "0.11.10"})
        (self.tmp / "versions.json").write_text(theirs, encoding="utf-8")
        self.assertIsNone(updates.feed(fetch=False), "theirs is not read")
        answer = {"latest": "1.0.0"}
        self.assertEqual(updates.feed(get=stand_in(answer), now=1_000_000.0), answer)
        self.assertEqual((self.tmp / "versions.json").read_text(encoding="utf-8"), theirs, "nor written")
        self.assertEqual(json.loads((self.tmp / updates.FILE).read_text(encoding="utf-8"))["feed"], answer)

    def test_nothing_is_checked_when_turned_off_in_ci_or_for_a_development_build(self) -> None:
        self.just_read(FEED)
        for values in ({"CAD_UPDATE_CHECK": "0"}, {"CI": "true"}, {"CAD_INSTALLATION_VERSION": "0.8.1-dev.1"}):
            with self.subTest(values=values), mock.patch.dict(os.environ, values):
                asked: list[str] = []
                updates.feed(now=time.time() + 2 * updates.CHECK_SECONDS, get=asked.append)
                self.assertEqual((asked, updates.refresh()), ([], None))

    def test_nothing_waits_on_the_feed(self) -> None:
        # A feed that is due is read in the background, and whatever asks meanwhile is told the feed as last read:
        # offline or slow, nothing waits.
        (self.tmp / updates.FILE).write_text(json.dumps({"checked": 0, "feed": FEED}), encoding="utf-8")
        reading, answer = threading.Event(), threading.Event()

        def get(url: str, _seconds: float = 0) -> dict:
            reading.set()
            answer.wait(30)
            return pypi_answer("0.9.1") if url.endswith("/cad/json") else {"notices": []}

        with mock.patch.object(updates, "_get", get), mock.patch.object(updates, "_get_within", get):
            thread = updates.refresh()
            self.assertTrue(reading.wait(30))
            self.assertEqual(updates.feed(fetch=False)["latest"], "0.9.0")
            self.assertIsNone(updates.refresh(), "an hour's read is not asked for twice")
            answer.set()
            thread.join(30)
        self.assertEqual(updates.feed(fetch=False)["latest"], "0.9.1")

    def test_no_command_reads_the_feed_or_says_a_newer_release_is_out(self) -> None:
        # A server reads the feed, in the background, for cad's own update, which is silent: no command reads it, and
        # none says a newer release is out, `cad --version` included. (Telemetry's notice is not this test's.)
        self.environment({"DO_NOT_TRACK": "1"})
        self.just_read({"latest": "9.9.9"})
        for argv in (["telemetry"], ["--version"]):
            out, err = io.StringIO(), io.StringIO()
            with self.subTest(argv=argv), mock.patch.object(updates, "_get") as get, \
                    mock.patch.object(updates, "_get_within") as asked, contextlib.redirect_stdout(out), \
                    contextlib.redirect_stderr(err):
                self.assertEqual(cadgen_main(argv), 0)
                get.assert_not_called()
                asked.assert_not_called()
                self.assertEqual(err.getvalue(), "")
                self.assertNotIn("9.9.9", out.getvalue())


if __name__ == "__main__":
    unittest.main()
