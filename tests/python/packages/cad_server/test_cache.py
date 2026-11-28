"""``cad cache dir | prune | clean`` (``cad_server.cli.cache``): where cad's cache is; what this release cannot use
removed (environments of other releases, the release folders of 0.11.11 and earlier but the current one); all of it
removed, refused while a server runs. Data -- the documents the engine keeps there, the state folder -- is never
touched, nor a folder a process runs from, and each says what it removed and the disk that freed."""

from __future__ import annotations

import io
import json
import os
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cad/src")

from cad.engine.previous import version  # noqa: E402
from cad_server._internal import base, installations, releases  # noqa: E402
from cad_server.cli import cache  # noqa: E402

OTHER = "0.11.9"
MB = 1024 * 1024


def _run(*argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = cache.main(list(argv))
    return code, out.getvalue(), err.getvalue()


class CacheTest(unittest.TestCase):
    def setUp(self) -> None:
        root = TemporaryDirectory()
        self.addCleanup(root.cleanup)
        self.root = Path(root.name).resolve()
        self.state, self.cache = self.root / "state", self.root / "cache"
        (self.root / "engine").mkdir(mode=0o700)
        environment = mock.patch.dict("os.environ", {"CAD_STATE_DIR": str(self.state), "CAD_CACHE_DIR": str(self.cache),
                                                     "CAD_ENGINE_DIR": str(self.root / "engine")})
        environment.start()
        self.addCleanup(environment.stop)

    def environment(self, key: str, release: str | None, size: int = 4096) -> Path:
        env = base.folder() / key
        python = base.interpreter(env)
        python.parent.mkdir(parents=True)
        python.write_bytes(b"p" * size)
        marker = {"schema": base.SCHEMA, "key": key, **({} if release is None else {"inputs": {"release": release}})}
        (env / base.MARKER).write_text(json.dumps(marker), encoding="utf-8")
        return env

    def release(self, name: str) -> Path:
        folder = releases.root() / name
        python, command = base.interpreter(folder), releases.console(folder)
        python.parent.mkdir(parents=True)
        for path in (python, command):
            path.write_text("", encoding="utf-8")
        return folder

    def data(self) -> list[Path]:
        """The data a cache command never touches: a document the engine keeps in the cache folder, its record, and
        another program's folder there."""
        kept = [self.cache / "documents" / "11111111-1111-5111-8111-111111111111" / "document.xbf",
                self.state / "documents" / "11111111-1111-5111-8111-111111111111" / "document.json",
                self.state / "settings.json", self.cache / "objects" / "ab" / "theirs"]
        for path in kept:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("{}", encoding="utf-8")
        return kept

    def test_dir_says_where_the_cache_is(self) -> None:
        self.assertEqual(_run("dir"), (0, f"{self.cache}\n", ""))

    def test_prune_removes_what_this_release_cannot_use_and_says_what_that_freed(self) -> None:
        mine, theirs = self.environment("mine0000", version()), self.environment("theirs00", OTHER, 2 * 1024 * 1024)
        unmarked = base.folder() / "making00"  # an environment being made: no marker yet, no release to judge by
        unmarked.mkdir()
        old, current, running = self.release(OTHER), self.release("0.11.10"), self.release("0.11.8")
        installations.register("0.11.10", (str(releases.console(current)), str(base.interpreter(current)), str(current)))
        installations.point("0.11.10")
        kept = self.data()
        with mock.patch.object(releases, "running", side_effect=lambda path, **_: Path(path) == running):
            code, out, err = _run("prune")
            again = _run("prune")
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(out.splitlines(), [
            f"removed {theirs} (an environment of cad {OTHER})",
            f"removed {old} (cad {OTHER}, of the layout of 0.11.11 and earlier)",
            f"kept {current}: the release 0.11.11 and earlier start (installations/current)",
            f"kept {running}: a process runs from it",
            "2 removed, 2.0 MB freed"])
        self.assertFalse(theirs.exists() or old.exists())
        self.assertTrue(all(path.exists() for path in (mine, unmarked, current, running, *kept)))
        self.assertEqual(again, (0, f"kept {current}: the release 0.11.11 and earlier start "
                                            f"(installations/current)\nkept {running}: a process runs from it\n"
                                            "nothing removed\n", ""))

    def test_prune_also_removes_on_windows_what_cad_s_update_moved_aside_but_never_while_one_is_underway(self):
        """Each ``cad.exe`` the update moved aside in uv's bin folder and could not remove then (``auto_update.tidy``),
        said; nothing while an update is underway."""
        from cad_server._internal import auto_update

        theirs = self.environment("theirs00", OTHER, MB)
        moved = str(self.root / "bin" / ".cad-12.exe.old")
        record = self.state / auto_update.RECORD
        auto_update._keep(record, {"release": "0.0.4", "from": version(), "at": time.time(), "beat": time.time(),
                                   "outcome": "underway", "phase": "switching"})
        with mock.patch.object(auto_update, "tidy", return_value=[moved]) as tidy:
            code, out, err = _run("prune")
            self.assertEqual((code, err), (0, ""))
            self.assertEqual(out.splitlines(), [f"removed {theirs} (an environment of cad {OTHER})",
                                                "1 removed, 1.0 MB freed"])
            tidy.assert_not_called()
            record.unlink()
            self.assertEqual(_run("prune")[1].splitlines(),
                             [f"removed {moved} (a cad command cad's update moved aside)", "1 removed, 0 B freed"])
        self.assertEqual(_run("clean")[1], "nothing removed\n", "clean is the cache's alone")

    def test_clean_is_refused_while_a_server_runs_and_removes_all_of_the_cache_after(self) -> None:
        from cad.engine import client

        env, other = self.environment("mine0000", version()), self.environment("theirs00", OTHER)
        (base.folder() / "mine0000.lock").write_text("", encoding="utf-8")
        for name in ("pycache", "hulls", "homes"):
            (self.cache / name / "x").mkdir(parents=True)
        old = self.release(OTHER)
        kept = self.data()
        before = sorted(self.root.rglob("*"))
        server = mock.Mock()
        with mock.patch.object(client, "connect", return_value=server):
            self.assertEqual(_run("clean"), (1, "", "cad cache clean: the cad server is running, from cad's cache: run "
                                                    "`cad server stop` first\n"))
        server.close.assert_called_once_with()
        self.assertEqual(sorted(self.root.rglob("*")), before, "nothing removed")
        code, out, err = _run("clean")
        self.assertEqual((code, err), (0, ""))
        for path in (env, other, self.cache / "pycache", self.cache / "hulls", self.cache / "homes", old):
            self.assertIn(f"removed {path} (", out)
            self.assertFalse(path.exists(), path)
        self.assertFalse(base.folder().exists(), "the environments' folder, its locks with it")
        self.assertTrue(out.endswith(" freed\n"), out)
        self.assertTrue(all(path.exists() for path in kept), "data and another program's folder stay")

    def test_the_server_s_tidying_removes_other_releases_environments_by_itself_as_prune_does(self) -> None:
        """At the server's start and at its hourly tidying (``Daemon.caught_up``), quietly: an environment of another
        release goes; one a process runs from stays, and goes at the next tidying once it is free; this release's stay,
        whatever integrations they hold, and one with no release named; nothing goes while an update is underway."""
        import threading
        import types

        from cad_server._internal import auto_update
        from cad_server.engine import daemon
        from cad_server.engine.daemon import Daemon

        mine, integrations = self.environment("mine0000", version()), self.environment("mine0001", version())
        theirs, held = self.environment("theirs00", OTHER), self.environment("theirs01", "0.11.8")
        unmarked = self.environment("unmarked", None)
        busy = {held}
        stand_in = types.SimpleNamespace(draining=False, stopping=threading.Event(), tidied=float("-inf"),
                                         catching=types.SimpleNamespace(tend=lambda told: None))
        clock, underway = [10_000.0], [None]
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(auto_update, "tidy"), mock.patch.object(auto_update, "report"), \
                mock.patch.object(daemon.time, "monotonic", side_effect=lambda: clock[0]), \
                mock.patch.object(auto_update, "underway", side_effect=lambda: underway[0]), \
                mock.patch.object(releases, "running", side_effect=lambda path, **_: Path(path) in busy), \
                redirect_stdout(out), redirect_stderr(err):
            Daemon.caught_up(stand_in, starting=True)
            self.assertFalse(theirs.exists(), "another release's environment, gone at the start")
            self.assertTrue(all(path.exists() for path in (mine, integrations, unmarked, held)))
            busy.clear()
            later = self.environment("theirs02", OTHER)
            clock[0] += daemon.TIDY_SECONDS - 1
            Daemon.caught_up(stand_in)
            self.assertTrue(held.exists() and later.exists(), "nothing within the hour")
            clock[0] += 1
            underway[0] = {"outcome": "underway"}
            Daemon.caught_up(stand_in)
            self.assertTrue(held.exists() and later.exists(), "nothing while an update is underway")
            underway[0] = None
            Daemon.caught_up(stand_in)
        self.assertFalse(held.exists() or later.exists(), "an hour on: the one a process ran from too, now free")
        self.assertTrue(all(path.exists() for path in (mine, integrations, unmarked)), "this release's stay")
        self.assertEqual((out.getvalue(), err.getvalue()), ("", ""), "quiet")

    def test_the_server_s_tidying_removes_the_release_folders_of_0_11_11_and_earlier_by_itself(self) -> None:
        """As ``cad cache prune`` removes them: the one ``installations/current`` names stays, and one a process runs
        from, which goes at a later tidying; the folder that held them goes with the last. Never by a server that
        itself runs from a release folder: the updater that brought it may yet go back to the release before."""
        old, current, held = self.release(OTHER), self.release("0.11.10"), self.release("0.11.8")
        installations.register("0.11.10", (str(releases.console(current)), str(base.interpreter(current)), str(current)))
        installations.point("0.11.10")
        kept = self.data()
        busy = {held}
        with mock.patch.object(releases, "running", side_effect=lambda path, **_: Path(path) in busy):
            with mock.patch.object(releases.sys, "prefix", str(current)):
                self.assertEqual(releases.tidy(), [], "a server that runs from a release folder removes none")
            self.assertEqual(releases.tidy(), [old])
            self.assertTrue(current.exists() and held.exists() and not old.exists())
            busy.clear()
            self.assertEqual(releases.tidy(), [held])
            self.assertEqual(releases.tidy(), [])
        self.assertTrue(current.exists(), "what the clients of 0.11.11 and earlier start")
        # The computer moves to the global cad: ``current`` names an environment that is no release folder.
        tool = self.root / "tools" / "cad"
        for path in (base.interpreter(tool), releases.console(tool)):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("", encoding="utf-8")
        installations.register(version(), (str(releases.console(tool)), str(base.interpreter(tool)), str(tool)))
        installations.point(version())
        with mock.patch.object(releases, "running", return_value=False):
            self.assertEqual(releases.tidy(), [current])
        self.assertFalse(releases.root().exists(), "the folder that held them, empty now")
        self.assertTrue(all(path.exists() for path in kept), "data stays")
        with mock.patch.object(base, "_remove", side_effect=base.Refused("held")):
            self.release("0.11.9")
            self.assertEqual(releases.tidy(), [])
        with mock.patch.object(releases, "past", side_effect=OSError("unreadable")):
            self.assertEqual(releases.tidy(), [])

    def test_cad_s_own_entries_in_uv_s_cache_are_removed_once_for_each_release(self) -> None:
        """Every update leaves the release before unpacked in uv's cache, which nothing else removes. ``uv cache clean
        cad``, once for each release: by the server's tidying once this release's kernel environment is made (its
        making takes cad from the cache), and by ``cad cache prune`` whenever it is typed; only for a global install
        with a uv; never where cad's files are links into the cache; never forced: uv waits while another uv process
        is alive (measured: an app's ``uvx`` server line holds it for a whole session), so it is given a moment and
        tried again at a later tidying; a uv that fails changes nothing either."""
        import subprocess
        import types

        from cad_server._internal import auto_update

        tool = self.root / "tools" / "cad"
        site = tool / ("Lib/site-packages" if os.name == "nt" else "lib/python3.14/site-packages")
        (site / "cad").mkdir(parents=True)
        (site / "cad" / "__init__.py").write_text("", encoding="utf-8")
        kernel = self.root / "cache" / "base" / "abc"
        made: list = [None]
        ran: list = []
        outcome: list = [0]

        def run(command, **options):
            ran.append((command, options["timeout"]))
            if outcome[0] == "waits":
                raise subprocess.TimeoutExpired(command, options["timeout"])
            return types.SimpleNamespace(returncode=outcome[0])

        mark = self.state / auto_update.CACHE_MARK
        with mock.patch.object(auto_update, "global_install", return_value=auto_update.Global(tool, "/u/uv")), \
                mock.patch.object(base, "ensure", side_effect=lambda make=True: made[0]), \
                mock.patch.object(auto_update.subprocess, "run", side_effect=run):
            self.assertIsNone(auto_update.tidy_cache(), "the kernel environment is not made yet: its making needs cad")
            self.assertEqual(ran, [])
            made[0] = base.Environment("python", str(kernel), False)
            for failing, came in ((2, None), ("waits", auto_update.BUSY)):
                outcome[0] = failing
                self.assertEqual(auto_update.tidy_cache(), came)
                self.assertFalse(mark.exists(), "nothing noted: a later tidying tries again")
            outcome[0] = 0
            ran.clear()
            self.assertEqual(auto_update.tidy_cache(), auto_update.CLEANED)
            self.assertEqual(ran, [(["/u/uv", "cache", "clean", "cad"], auto_update.CACHE_SECONDS)],
                             "uv's own command for one package, never forced, given a moment")
            self.assertEqual(json.loads(mark.read_text(encoding="utf-8"))["release"], version())
            self.assertIsNone(auto_update.tidy_cache(), "once for this release")
            self.assertEqual(len(ran), 1)
            self.assertEqual(auto_update.tidy_cache(asked=True), auto_update.CLEANED, "typed: whenever it is asked")
            self.assertEqual(ran[-1][1], auto_update.CACHE_ASKED_SECONDS, "a person who asked waits a little longer")
            # The next release: done again, once.
            with mock.patch.object(auto_update, "_version", return_value="99.0.0"):
                self.assertEqual(auto_update.tidy_cache(), auto_update.CLEANED)
                self.assertIsNone(auto_update.tidy_cache())
            # Asked before the kernel environment is made, or where it cannot be told: done all the same.
            made[0] = None
            mark.unlink()
            self.assertEqual(auto_update.tidy_cache(asked=True), auto_update.CLEANED)
            with mock.patch.object(base, "ensure", side_effect=RuntimeError("no installation here")):
                self.assertEqual(auto_update.tidy_cache(asked=True), auto_update.CLEANED)
                mark.unlink()
                self.assertIsNone(auto_update.tidy_cache())
            # cad's files are links into the cache (uv's link mode `symlink`): never, and not tried again.
            if os.name != "nt":
                made[0] = base.Environment("python", str(kernel), False)
                real = self.root / "uv-cache" / "cad" / "__init__.py"
                real.parent.mkdir(parents=True)
                real.write_text("", encoding="utf-8")
                (site / "cad" / "__init__.py").unlink()
                (site / "cad" / "__init__.py").symlink_to(real)
                ran.clear()
                self.assertEqual(auto_update.tidy_cache(), auto_update.LINKED)
                self.assertIsNone(auto_update.tidy_cache(), "noted for this release")
                self.assertEqual(auto_update.tidy_cache(asked=True), auto_update.LINKED)
                self.assertEqual(ran, [], "uv is never asked")
                self.assertEqual(json.loads(mark.read_text(encoding="utf-8"))["skipped"], "linked")
        # No global install (pip, a checkout, a test), or no uv: nothing.
        with mock.patch.object(auto_update.subprocess, "run", side_effect=AssertionError("never run")):
            self.assertIsNone(auto_update.tidy_cache(asked=True))
            with mock.patch.object(auto_update, "global_install", return_value=auto_update.Global(tool, None)):
                self.assertIsNone(auto_update.tidy_cache(asked=True))
            with mock.patch.object(auto_update, "global_install", side_effect=OSError("unreadable")):
                self.assertIsNone(auto_update.tidy_cache(), "never raises")

    def test_prune_says_what_came_of_uv_s_cache(self) -> None:
        from cad_server._internal import auto_update

        for came, said in ((auto_update.CLEANED, "removed cad's releases from uv's cache (`uv cache clean cad`)\n"
                                                 "1 removed, 0 B freed\n"),
                           (auto_update.BUSY, "kept cad's releases in uv's cache: another uv process is running, and uv "
                                              "waits for it (run this again once it has ended, or `uv cache clean "
                                              "cad`)\nnothing removed\n"),
                           (auto_update.LINKED, "kept cad's releases in uv's cache: cad's files are links into it "
                                                "(uv's link mode symlink)\nnothing removed\n"),
                           (None, "nothing removed\n")):
            with self.subTest(came=came), mock.patch.object(auto_update, "tidy_cache", return_value=came) as asked:
                self.assertEqual(_run("prune"), (0, said, ""))
                asked.assert_called_once_with(asked=True)

    def test_the_tidying_never_raises(self) -> None:
        self.environment("theirs00", OTHER)
        with mock.patch.object(base, "_remove", side_effect=base.Refused("held")):
            self.assertEqual(base.tidy(), [])
        with mock.patch.object(base, "others", side_effect=OSError("unreadable")):
            self.assertEqual(base.tidy(), [])

    def test_what_a_removal_frees_counts_no_file_another_link_keeps(self) -> None:
        env = self.environment("theirs00", OTHER, 8192)
        outside = self.root / "uv-cache" / "file"
        outside.parent.mkdir()
        outside.write_bytes(b"u" * 65536)
        try:
            os.link(outside, env / "linked")
        except OSError:
            self.skipTest("no hard links here")
        alone, both = cache.freed([env]), cache.freed([env, outside.parent])
        self.assertGreaterEqual(alone, 8192, "the environment's own files")
        self.assertLess(alone, 65536, "a file uv's cache links to frees nothing")
        self.assertGreaterEqual(both - alone, 65536, "every link to it removed: it is freed, once")


if __name__ == "__main__":
    unittest.main()
