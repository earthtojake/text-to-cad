"""``cad cache dir | prune | clean`` (``cad_server.cli.cache``): where cad's cache is; what no file and no release
needs removed (environments of other releases, the release folders of 0.11.11 and earlier but the current one, a
file's folder once its file is gone, or once unwritten for a month where its note names no file, and the meshes kept
by geometry past their cap, the least recently used first); all of it removed, refused while a server runs. The state
folder is never touched, nor a folder a process runs from, nor a file's folder while it is being shared, and each says
what it removed and the disk that freed."""

from __future__ import annotations

import io
import json
import os
import re
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

    def test_prune_and_clean_know_the_webassembly_kernel_s_folders(self) -> None:
        """``prune``: a kernel folder of another lock or Node, a download the lock does not name, a script's own
        packages for a kernel folder that is gone; this release's folder, its downloads and live packages stay.
        ``clean``: all of them."""
        from cad.engine import client
        from cad_server._internal import kernel_folder, kernel_packages

        kernels = self.cache / "kernel"
        mine, other = kernels / "aaaaaaaaaaaaaaaa", kernels / "bbbbbbbbbbbbbbbb"
        for made in (mine, other):
            (made / "bin").mkdir(parents=True)
            (made / "bin" / "python").write_text("#!/bin/sh\n", encoding="utf-8")
        downloads = kernels / "downloads"
        downloads.mkdir()
        named = kernel_folder.lock()["core"][0]["sha256"]
        (downloads / named).write_bytes(b"pyodide")
        (downloads / ("f" * 64)).write_bytes(b"an earlier release's wheel")
        live, orphan = self.cache / "kernel-packages" / "1111", self.cache / "kernel-packages" / "2222"
        for packages, made_for in ((live, mine), (orphan, self.root / "a kernel folder removed")):
            packages.mkdir(parents=True)
            (packages / kernel_packages.MARKER).write_text(json.dumps({"kernel": str(made_for)}), encoding="utf-8")
        with mock.patch.object(kernel_folder, "where", return_value=mine):
            code, out, _err = _run("prune")
        self.assertEqual(code, 0)
        for gone in (other, downloads / ("f" * 64), orphan):
            self.assertIn(f"removed {gone} (", out)
            self.assertFalse(gone.exists(), gone)
        self.assertTrue(all(path.exists() for path in (mine, downloads / named, live)))
        with mock.patch.object(kernel_folder, "where", side_effect=base.Refused("no node on PATH", "other")):
            self.assertEqual(_run("prune")[1], "nothing removed\n", "no Node to say which is this one's: none goes")
        with mock.patch.object(client, "connect", return_value=None):
            code, out, _err = _run("clean")
        self.assertEqual(code, 0)
        self.assertFalse(kernels.exists() or (self.cache / "kernel-packages").exists(), out)

    def note(self, name: str, *, gone: bool = False) -> Path:
        """A file of the work folder, its note written as the engine writes one (``library.Notes``, which names the
        file), and the file then deleted where ``gone``: its folder of the cache."""
        from cad.engine.ids import file_id
        from cad_server.engine.library import Notes

        path = self.root / "work" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"solid")
        Notes(self.cache).count(path, 2)
        if gone:
            path.unlink()
        return self.cache / "documents" / file_id(path)

    @staticmethod
    def aged(folder: Path, days: float) -> None:
        """Every entry of ``folder``, and it, last read and written ``days`` ago."""
        when = time.time() - days * 86400
        for path in sorted(folder.rglob("*"), reverse=True) + [folder]:
            os.utime(path, (when, when))

    def test_prune_removes_a_files_folder_once_its_file_is_gone_and_one_naming_no_file_once_unused(self) -> None:
        """A note names its file (``library.Notes``): its folder goes once the file is gone, a shared file's view and
        where its share's files are with it. One whose note names no file (an earlier build's), or with no note, goes
        once nothing in it was written for ``UNUSED_DAYS``. A file that is there keeps its folder, however old."""
        here, gone = self.note("here.stl"), self.note("gone.stl", gone=True)
        for name in ("view/manifest.json", "view/parts/k/t.xbm", "stored.json", "share.lock"):
            (gone / name).parent.mkdir(parents=True, exist_ok=True)
            (gone / name).write_bytes(b"x" * 4096)
        self.aged(here, 400)
        earlier, fresh, bare = (self.cache / "documents" / ident for ident in (
            "22222222-2222-5222-8222-222222222222", "33333333-3333-5333-8333-333333333333",
            "44444444-4444-5444-8444-444444444444"))
        for folder in (earlier, fresh):  # a note of an earlier build: no path
            folder.mkdir(parents=True)
            (folder / "note.json").write_text(json.dumps({"schema": 1, "version": "1-2", "parts": 3}), encoding="utf-8")
        (bare / "checks").mkdir(parents=True)
        (bare / "checks" / "a.json").write_text("{}", encoding="utf-8")
        self.aged(earlier, cache.UNUSED_DAYS + 1)
        self.aged(bare, cache.UNUSED_DAYS + 1)
        self.aged(fresh, cache.UNUSED_DAYS - 1)
        theirs = self.cache / "documents" / "notes"  # no document's id: not cad's to judge
        theirs.mkdir(parents=True)
        code, out, err = _run("prune")
        self.assertEqual((code, err), (0, ""))
        lines = out.splitlines()
        named = f"what the cache kept of a file no note names, unwritten for {cache.UNUSED_DAYS} days"
        self.assertEqual(sorted(lines[:-1]), sorted([
            f"removed {gone} (what the cache kept of {self.root / 'work' / 'gone.stl'}, which is gone)",
            f"removed {earlier} ({named})", f"removed {bare} ({named})"]))
        self.assertRegex(lines[-1], r"^3 removed, \d+\.\d KB freed$")
        self.assertFalse(any(path.exists() for path in (gone, earlier, bare)))
        self.assertTrue(all(path.is_dir() for path in (here, fresh, theirs)))
        self.assertEqual(json.loads((here / "note.json").read_text(encoding="utf-8"))["path"],
                         str(self.root / "work" / "here.stl"), "a note names its file")
        self.assertEqual(_run("prune"), (0, "nothing removed\n", ""))

    def test_a_files_folder_being_shared_is_kept_with_its_meshes_and_said(self) -> None:
        """A share of the file holds its folder's lock while it is made (``sharing.held``): prune leaves the folder,
        and its view bundle's meshes, as they are, and says so, rather than refuse to run beside a server."""
        from cad_server import sharing

        gone = self.note("gone.stl", gone=True)
        shared = self.note("shared.step")
        mesh = shared / "view" / "parts" / "k" / "t.xbm"
        mesh.parent.mkdir(parents=True)
        mesh.write_bytes(b"m" * 8192)
        with mock.patch.object(cache, "MESH_BYTES", 0), sharing.held(gone), sharing.held(shared):
            code, out, err = _run("prune")
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(sorted(out.splitlines()), sorted([f"kept {gone}: a share of its file is being made",
                                                          f"kept {shared}: a share of its file is being made",
                                                          "nothing removed"]))
        self.assertTrue(gone.is_dir() and mesh.is_file())

    def test_prune_holds_the_meshes_to_their_cap_the_least_recently_used_first(self) -> None:
        """The meshes kept by geometry -- a view bundle's part meshes, a part's hulls -- are held to ``MESH_BYTES``: past
        it the ones used longest ago go, used meaning read as well as written (``places.used``: a read sets a file's
        access time, its modification time kept, which a bundle's writer and a hull's reader each do)."""
        import numpy as np

        from cad.engine import hulls, places
        from cad_server.viewer import bundle

        shared = self.note("shared.step")
        old, read, new = (shared / "view" / "parts" / key / "t.xbm" for key in ("old", "read", "new"))
        hull = self.cache / "hulls" / ("a" * 64 + ".npz")
        hull.parent.mkdir(parents=True)
        hulls._write(hull, [(np.zeros((4, 3), dtype=np.float32), np.zeros((2, 3), dtype=np.uint32))])
        for path in (old, read, new):
            path.parent.mkdir(parents=True)
            path.write_bytes(b"m" * 8192)
        for path, days in ((old, 9), (read, 8), (hull, 7), (new, 1)):
            when = time.time() - days * 86400
            os.utime(path, (when, when))
        written = read.stat().st_mtime_ns
        # Read since it was written: a bundle written again keeps it as it is, and its access time says it was used.
        entry = {"sha256": bundle._digest(read.read_bytes()), "bytes": 8192}
        writer = bundle._Bundle(None, shared / "view", shared / "stage", {"format": bundle.FORMAT, "made": {
            "release": "r", "facts": bundle.FACTS_VERSION}, "files": {"parts/read/t.xbm": entry}}, "r", [])
        self.assertTrue(writer.holds("parts/read/t.xbm"))
        self.assertEqual(read.stat().st_mtime_ns, written, "a read changes no modification time")
        self.assertGreater(read.stat().st_atime, time.time() - 60, "a read is a use")
        hull_written = hull.stat().st_mtime_ns
        self.assertIsNotNone(hulls._read(hull))
        self.assertEqual((hull.stat().st_mtime_ns, hull.stat().st_atime > time.time() - 60), (hull_written, True))
        places.used(self.root / "nowhere")  # a file gone meanwhile keeps nothing from going on
        disk = {path: cache._disk(os.lstat(path)) for path in (old, read, hull, new)}  # as this system allots it
        self.assertEqual(cache.meshes()[1], sum(disk.values()), "every mesh counted")
        cap = disk[read] + disk[hull]  # room for the two used last
        with mock.patch.object(cache, "MESH_BYTES", cap):
            over, _held = cache.meshes()
            code, out, err = _run("prune")
        self.assertEqual([path for path, _disk in over], [old, new], "used longest ago first: the old, then the new")
        self.assertEqual((code, err), (0, ""))
        self.assertTrue(out.startswith("removed 2 meshes last used "), out)
        freed, held = re.escape(cache.size(disk[old] + disk[new])), re.escape(cache.size(cap))
        self.assertRegex(out, rf"\({freed}\): the meshes cad keeps by geometry are held to {held}, the least recently "
                              rf"used going first\n2 removed, {freed} freed\n$")
        self.assertFalse(old.exists() or new.exists() or old.parent.exists())
        self.assertTrue(read.is_file() and hull.is_file())

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
