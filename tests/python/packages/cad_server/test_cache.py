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

    def stored(self, release: str, size: int = 4096) -> Path:
        """A release cad's update keeps in its store (``store.folder``), with a file of ``size`` bytes."""
        from cad_server._internal import store

        folder = store.folder(release)
        (folder / "cad").mkdir(parents=True)
        (folder / "cad" / "data").write_bytes(b"r" * size)
        (folder / store.MARKER).write_text(json.dumps({"store": 1, "release": release, "python": store.tag(),
                                                       "built": 0.0}), encoding="utf-8")
        return folder

    def test_prune_also_tidies_the_store_of_cad_s_update_and_says_what_a_process_runs(self) -> None:
        """The store is in the state folder, not the cache: ``prune`` tidies it as cad's update does
        (``store.clean``), each release removed said with the room that freed; one a process runs is kept and said,
        one a pointer names kept for what it is; and nothing while an update is underway."""
        from cad_server._internal import auto_update, store

        old, running, named = self.stored("0.0.1", 2 * MB), self.stored("0.0.2", MB), self.stored("0.0.3")
        building = store.root() / f"{store.BUILDING}1-dead"
        building.mkdir()
        os.utime(building, (0, 0))
        auto_update._keep(store.root() / "pointer-00000000.json", {"pointer": 1, "path": str(named), "previous": None})
        theirs = self.environment("theirs00", OTHER, MB)
        # As a process that runs the release holds it (``store``, "In use"): its marker open, which on Windows
        # refuses the folder's rename, and elsewhere under the marker's shared lock.
        held = open(running / store.MARKER, "rb")  # noqa: SIM115 - held until the test lets go of it
        self.addCleanup(held.close)
        if os.name != "nt":
            import fcntl

            fcntl.flock(held, fcntl.LOCK_SH)
        record = self.state / auto_update.RECORD
        auto_update._keep(record, {"release": "0.0.4", "from": version(), "at": time.time(), "beat": time.time(),
                                   "outcome": "underway", "phase": "building"})
        code, out, err = _run("prune")
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(out.splitlines(), [f"removed {theirs} (an environment of cad {OTHER})",
                                            "1 removed, 1.0 MB freed; cad's update is underway, so the releases it "
                                            "keeps are left as they are"])
        self.assertTrue(all(path.exists() for path in (old, running, named, building)), "the store left alone")
        record.unlink()
        code, out, err = _run("prune")
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(out.splitlines(), [f"removed {building} (a build of cad's update that did not end)",
                                            f"removed {old} (cad 0.0.1, kept by cad's update)",
                                            f"kept {running}: a process runs it",
                                            "2 removed, 2.0 MB freed"])
        self.assertFalse(old.exists() or building.exists())
        self.assertTrue(running.exists() and named.exists(), "a process runs one, a pointer names the other")
        held.close()
        self.assertEqual(_run("prune")[1].splitlines(), [f"removed {running} (cad 0.0.2, kept by cad's update)",
                                                         "1 removed, 1.0 MB freed"])
        self.assertTrue(named.exists())
        self.assertEqual(_run("clean")[1], "nothing removed\n", "clean is the cache's alone")

    def test_prune_keeps_the_release_cad_s_update_has_ready(self) -> None:
        """Built, run once and pointed at by nothing until cad restarts on it (``auto_update.kept``): never tidied
        away while its record is the last attempt's."""
        import cad_server
        from cad_server._internal import auto_update, store

        ready, other = self.stored("0.0.5"), self.stored("0.0.6")
        (ready / store.MARKER).write_text(json.dumps({"store": 1, "release": "0.0.5", "python": store.tag(),
                                                      "for": store.built_for(), "built": 0.0}), encoding="utf-8")
        auto_update._keep(self.state / auto_update.RECORD, {
            "release": "0.0.5", "wanted": "0.0.5", "from": cad_server.__version__, "at": 1.0, "tries": 1,
            "outcome": "ready", "switch": False, "ended": 2.0})
        code, out, err = _run("prune")
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(out.splitlines()[:-1], [f"removed {other} (cad 0.0.6, kept by cad's update)"],
                         "the release ready kept, and not said as one a process runs")
        self.assertTrue(ready.exists())
        self.assertFalse(other.exists())

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
