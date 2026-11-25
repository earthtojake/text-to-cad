"""The releases cad's update keeps beside the installed cad (``cad_server._internal.store``): built, run once, named,
pointed at, and removed only where no process runs them.

Every folder is a temporary one: the state folder (``CAD_STATE_DIR``), and environments made of a ``site-packages``
with a stand-in cad's dist-info (``prefix=``). Where a command would run, a stand-in ``run`` answers; where what the
store writes must be read as an interpreter starts, a real environment reads it
(``tests/python/support/release_environment.py``).
"""

from __future__ import annotations

import binascii
import json
import os
import shutil
import subprocess
import sys
import time
import types
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

from cad_server._internal import store
from tests.python.support.release_environment import SECONDS, Environment, child_environment
from tests.python.support.tmp_root import temporary_directory

STORE_SOURCE = Path(store.__file__)


def write(path: Path, text: str = "") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def dist_info(folder: Path, release: str, *, record: bool = True, metadata: bool = True) -> Path:
    """``cad-<release>.dist-info`` in ``folder``, with its ``RECORD`` and ``METADATA`` as asked."""
    info = folder / f"cad-{release}.dist-info"
    info.mkdir(parents=True, exist_ok=True)
    if metadata:
        write(info / "METADATA", f"Name: cad\nVersion: {release}\n")
    if record:
        write(info / "RECORD", f"cad-{release}.dist-info/RECORD,,\n")
    return info


def environment(folder: Path, release: str = "1.0.0") -> tuple[Path, Path]:
    """An environment at ``folder`` holding cad ``release``, laid out as the platform lays one out: its prefix and
    its packages folder."""
    packages = folder / ("Lib/site-packages" if os.name == "nt" else
                         f"lib/python{sys.version_info.major}.{sys.version_info.minor}/site-packages")
    dist_info(packages, release)
    return folder, packages


def listing(folder: Path) -> list[tuple[str, int, int]]:
    """Every file and folder under ``folder``, with its size and time: what a write into it would change."""
    return sorted((path.relative_to(folder).as_posix(), path.stat().st_size, path.stat().st_mtime_ns)
                  for path in folder.rglob("*"))


class Run:
    """A stand-in for a command runner: what it was asked, and the answer it gives (``answer``, or a callable of
    the command)."""

    def __init__(self, answer: Any) -> None:
        self.answer, self.asked = answer, []

    def __call__(self, command: list[str], timeout: float) -> tuple[int | None, str]:
        self.asked.append((command, timeout))
        return self.answer(command) if callable(self.answer) else self.answer


class StoreCase(unittest.TestCase):
    def setUp(self) -> None:
        scratch = temporary_directory(prefix="store-")
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name).resolve()
        self.state = self.root / "state"
        self.enterContext(mock.patch.dict(os.environ, {"CAD_STATE_DIR": str(self.state)}))

    def staged(self, release: str = "1.0.1", name: str = "staged") -> Path:
        """A build of ``release`` as ``build`` leaves one: a folder with cad's dist-info."""
        folder = store.root() / f"{store.BUILDING}{name}"
        dist_info(folder, release)
        write(folder / "cad" / "__init__.py", f"RELEASE = {release!r}\n")
        return folder

    def published(self, release: str = "1.0.1") -> Path:
        return store.publish(self.staged(release, name=release), release)


class BuildTest(StoreCase):
    def test_the_build_is_uv_s_install_into_a_new_folder_of_the_store(self) -> None:
        run = Run((0, "Installed 40 packages"))
        staged = store.build("cad==1.0.1", uv="/bin/uv", run=run)
        [(command, timeout)] = run.asked
        self.assertEqual(command, ["/bin/uv", "pip", "install", "--python", sys.executable, "--target", str(staged),
                                   "--link-mode", "hardlink", "--refresh-package", "cad", "cad==1.0.1"])
        self.assertEqual(timeout, store.BUILD_SECONDS)
        self.assertEqual(staged.parent, store.root())
        self.assertTrue(staged.name.startswith(".building-"), staged.name)
        self.assertIsNone(store.marker(staged), "no release yet")
        other = store.build("cad>=1.0,<2", uv="uv", run=run, timeout=5.0)
        self.assertNotEqual(other, staged)
        self.assertEqual((run.asked[-1][0][-1], run.asked[-1][1]), ("cad>=1.0,<2", 5.0))

    def test_a_build_that_fails_says_what_uv_said_and_leaves_no_folder(self) -> None:
        for code in (2, None):
            with self.subTest(code=code):
                def half(command: list[str]) -> tuple[int | None, str]:
                    write(Path(command[command.index("--target") + 1]) / "cad" / "__init__.py")
                    return code, "error: no release satisfies cad==9"
                with self.assertRaises(store.Failed) as caught:
                    store.build("cad==9", uv="uv", run=Run(half))
                failed = caught.exception
                self.assertEqual((failed.step, failed.code, failed.output), ("build", code, "error: no release satisfies cad==9"))
                self.assertEqual(list(store.root().iterdir()), [], "the half-made folder is gone")


class VerifyTest(StoreCase):
    def test_the_release_runs_once_with_nothing_on_its_path_but_the_standard_library_and_its_folder(self) -> None:
        staged = self.staged()
        run = Run((0, "loaded\ncad 1.0.1\n\n"))
        self.assertEqual(store.verify(staged, run=run), "1.0.1")
        [(command, timeout)] = run.asked
        self.assertEqual(command, [sys.executable, "-I", "-S", "-c", store.VERIFY, str(staged)])
        self.assertEqual(timeout, store.VERIFY_SECONDS)
        self.assertTrue(staged.is_dir(), "a release that ran is kept for publish")

    def test_anything_but_exit_0_and_its_own_release_last_fails_and_removes_the_folder(self) -> None:
        def missing_record(folder: Path) -> None:
            (folder / "cad-1.0.1.dist-info" / "RECORD").unlink()

        def no_dist_info(folder: Path) -> None:
            shutil.rmtree(folder / "cad-1.0.1.dist-info")

        cases = {"exit 1": ((1, "cad 1.0.1\n"), None), "no end": ((None, "cad 1.0.1\n"), None),
                 "another release": ((0, "cad 1.0.2\n"), None), "no release said": ((0, "cad \n"), None),
                 "not said last": ((0, "cad 1.0.1\nTraceback\n"), None), "nothing": ((0, ""), None),
                 "output None": ((0, None), None), "a prefix": ((0, "xcad 1.0.1\n"), None),
                 "no RECORD": ((0, "cad 1.0.1\n"), missing_record), "no dist-info": ((0, "cad 1.0.1\n"), no_dist_info)}
        for name, (answer, change) in cases.items():
            with self.subTest(case=name):
                staged = self.staged(name=name.replace(" ", "-"))
                if change is not None:
                    change(staged)
                with self.assertRaises(store.Failed) as caught:
                    store.verify(staged, run=Run(answer))
                self.assertEqual((caught.exception.step, caught.exception.code, caught.exception.output),
                                 ("verify", answer[0], answer[1]))
                self.assertFalse(staged.exists())

    def test_the_command_really_runs_the_release_s_own_check_as_its_main(self) -> None:
        staged = self.staged()
        write(staged / "cad_server" / "__init__.py")
        write(staged / "cad_server" / "_internal" / "__init__.py")
        write(staged / "cad_server" / "_internal" / "selftest.py", "\n".join((
            "import sys",
            "assert __name__ == '__main__' and sys.flags.isolated and sys.flags.no_site, 'not as verify runs it'",
            "assert sys.path[-1] == sys.argv[1] and not any('site-packages' in entry for entry in sys.path), sys.path",
            "print('checked')",
            "print('cad 1.0.1')", "")))

        def run(command: list[str], timeout: float) -> tuple[int | None, str]:
            done = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
            return done.returncode, done.stdout + done.stderr

        self.assertEqual(store.verify(staged, run=run), "1.0.1")


class PublishTest(StoreCase):
    def test_the_marker_is_written_and_the_folder_named_for_its_release(self) -> None:
        staged = self.staged()
        before = time.time()
        final = store.publish(staged, "1.0.1")
        self.assertEqual(final, store.folder("1.0.1"))
        self.assertEqual(final.name, f"1.0.1-{store.built_for()}")
        self.assertFalse(staged.exists())
        found = json.loads((final / "cad-store.json").read_text(encoding="utf-8"))
        self.assertEqual({key: found[key] for key in ("store", "release", "python", "for")},
                         {"store": 1, "release": "1.0.1", "python": sys.implementation.cache_tag,
                          "for": store.built_for()})
        self.assertGreaterEqual(found["built"], before - 1)
        self.assertEqual(store.marker(final), found)
        self.assertTrue((final / "cad" / "__init__.py").is_file())

    def test_a_stored_release_is_named_for_the_interpreter_that_can_load_it(self) -> None:
        """Two interpreters of one Python version that cannot load each other's compiled files never share one."""
        import importlib.machinery

        mine = store.built_for()
        suffix = importlib.machinery.EXTENSION_SUFFIXES[0]
        self.assertTrue(suffix.startswith("." + mine.split("-")[0]) and mine.split("-")[0] in suffix, (mine, suffix))
        self.assertIn(f"{sys.version_info.major}{sys.version_info.minor}", mine)
        if hasattr(os, "uname"):
            self.assertIn(os.uname().machine, mine, "the processor, which macOS's suffix does not name")
        for theirs, name in ((".cpython-312-x86_64-linux-gnu.so", "cpython-312-x86_64-linux-gnu"),
                             (".cpython-312-x86_64-linux-musl.so", "cpython-312-x86_64-linux-musl"),
                             (".cpython-313t-aarch64-linux-gnu.so", "cpython-313t-aarch64-linux-gnu"),
                             (".cpython-312-darwin.so", "cpython-312-darwin-arm64"),
                             (".cp312-win_amd64.pyd", "cp312-win_amd64")):
            machine = {"cpython-312-darwin-arm64": "arm64", "cpython-313t-aarch64-linux-gnu": "aarch64"}.get(name, "x86_64")
            uname = None if theirs.endswith(".pyd") else mock.Mock(return_value=mock.Mock(machine=machine))
            with self.subTest(suffix=theirs), mock.patch.object(importlib.machinery, "EXTENSION_SUFFIXES", [theirs, ".so"]), \
                    mock.patch.object(store, "os", types.SimpleNamespace(**({"uname": uname} if uname else {}))):
                self.assertEqual(store.built_for(), name)
        final = self.published()
        kept = json.loads((final / "cad-store.json").read_text(encoding="utf-8"))
        for changes in ({"for": "cpython-312-x86_64-linux-musl"}, {"python": "cpython-27"}, {"store": 2}):
            with self.subTest(changes=changes):
                write(final / "cad-store.json", json.dumps({**kept, **changes}))
                self.assertIsNone(store.marker(final), "not this interpreter's: no release to it")
        write(final / "cad-store.json", json.dumps(kept))
        self.assertEqual(store.marker(final), kept)

    def test_a_release_already_stored_stays_and_the_new_build_goes(self) -> None:
        final = self.published()
        marker = (final / "cad-store.json").read_bytes()
        again = self.staged(name="again")
        write(again / "only-in-the-second-build")
        self.assertEqual(store.publish(again, "1.0.1"), final)
        self.assertFalse(again.exists())
        self.assertFalse((final / "only-in-the-second-build").exists())
        self.assertEqual((final / "cad-store.json").read_bytes(), marker)

    def test_a_folder_of_that_name_with_no_marker_is_replaced(self) -> None:
        write(store.folder("1.0.1") / "left-by-a-crash")
        final = store.publish(self.staged(), "1.0.1")
        self.assertIsNotNone(store.marker(final))
        self.assertFalse((final / "left-by-a-crash").exists())
        self.assertEqual(sorted(entry.name for entry in store.root().iterdir()), [final.name], "nothing left aside")

    def test_a_release_stored_earlier_is_sound_only_while_it_runs_and_says_its_own_release(self) -> None:
        final = self.published()
        before = listing(final)
        run = Run((0, "cad 1.0.1\n"))
        self.assertTrue(store.sound(final, run=run))
        [(command, timeout)] = run.asked
        self.assertEqual(command, [sys.executable, "-I", "-S", "-c", store.VERIFY, str(final)], "as a build is run")
        self.assertEqual(timeout, store.VERIFY_SECONDS)
        for name, answer in {"exit 1": (1, "ImportError: DLL load failed"), "no end": (None, "TimeoutExpired"),
                             "another release": (0, "cad 1.0.2\n"), "nothing": (0, "")}.items():
            with self.subTest(case=name):
                self.assertFalse(store.sound(final, run=Run(answer)))
        self.assertEqual(listing(final), before, "asking changes nothing, sound or not")
        never = Run(lambda command: self.fail("nothing is run for a folder that is no stored release"))
        self.assertFalse(store.sound(self.staged(name="unpublished"), run=never))
        self.assertFalse(store.sound(self.root / "nothing", run=never))

    def test_any_folder_of_packages_is_checked_as_a_build_is_and_says_the_check_s_last_line(self) -> None:
        """``checks``, for ``cad doctor``: a stored release or an environment's own packages, run once by its own
        check; whether it passed, and its last line, the error where it did not. Changes nothing."""
        _prefix, packages = environment(self.root / "env", "1.0.0")
        before = listing(packages)
        run = Run((0, "selftest\ncad 1.0.0\n"))
        self.assertEqual(store.checks(packages, run=run, timeout=5.0), (True, "cad 1.0.0"))
        self.assertEqual(run.asked, [([sys.executable, "-I", "-S", "-c", store.VERIFY, str(packages)], 5.0)])
        for answer, said in (((1, "Traceback\nImportError: cannot import name 'x' from 'cad_server.y'\n"),
                              (False, "ImportError: cannot import name 'x' from 'cad_server.y'")),
                             ((0, "cad 1.0.2\n"), (False, "cad 1.0.2")), ((None, ""), (False, "exit None"))):
            with self.subTest(answer=answer):
                self.assertEqual(store.checks(packages, run=Run(answer)), said)
        self.assertEqual(listing(packages), before, "asking changes nothing")

    def test_a_stored_release_that_no_longer_runs_gives_way_to_the_new_build(self) -> None:
        final = self.published()
        write(final / "only-in-the-first-build")
        again = self.staged(name="again")
        write(again / "only-in-the-second-build")
        self.assertEqual(store.publish(again, "1.0.1", run=Run((1, "ImportError: DLL load failed"))), final)
        self.assertTrue((final / "only-in-the-second-build").is_file())
        self.assertFalse((final / "only-in-the-first-build").exists())
        self.assertIsNotNone(store.marker(final))
        self.assertEqual(sorted(entry.name for entry in store.root().iterdir()), [final.name], "nothing left aside")
        # One that runs stays, as with no ``run``.
        third = self.staged(name="third")
        write(third / "only-in-the-third-build")
        self.assertEqual(store.publish(third, "1.0.1", run=Run((0, "cad 1.0.1\n"))), final)
        self.assertFalse((final / "only-in-the-third-build").exists())
        self.assertFalse(third.exists())

    def test_a_stored_release_that_no_longer_runs_and_is_still_run_by_a_process_stops_the_build(self) -> None:
        final = self.published()
        child = holding(final / "cad-store.json")
        self.addCleanup(lambda: child.poll() is None and child.kill())
        again = self.staged(name="again")
        with self.assertRaises(OSError) as refused:
            store.publish(again, "1.0.1", run=Run((1, "ImportError: DLL load failed")))
        self.assertIn("resource busy", str(refused.exception), "a cause the update's worker tells: in use")
        self.assertFalse(again.exists(), "the build is gone")
        self.assertIsNotNone(store.marker(final), "what a process runs is never taken from it")
        release(child)


class OwnTest(StoreCase):
    def test_the_dist_info_with_its_record_and_metadata_written_last(self) -> None:
        packages = self.root / "packages"
        self.assertIsNone(store.own(packages), "no folder")
        packages.mkdir()
        self.assertIsNone(store.own(packages), "no cad")
        dist_info(packages, "0.9.0", record=False, metadata=False)
        dist_info(packages, "0.9.1", record=False)
        dist_info(packages, "0.9.2", metadata=False)
        write(packages / "cadquery-2.0.dist-info" / "RECORD")
        write(packages / "cadquery-2.0.dist-info" / "METADATA")
        self.assertIsNone(store.own(packages), "an install stopped midway is no install")
        first = dist_info(packages, "1.0.0") / "RECORD"
        second = dist_info(packages, "0.11.0") / "RECORD"
        stamp = first.stat().st_mtime_ns
        os.utime(second, ns=(stamp, stamp - 1_000_000_000))
        self.assertEqual(store.own(packages), ("1.0.0", first))
        os.utime(second, ns=(stamp, stamp + 1_000_000_000))
        self.assertEqual(store.own(packages), ("0.11.0", second), "the RECORD written last")


class PointerTest(StoreCase):
    def setUp(self) -> None:
        super().setUp()
        self.prefix, self.packages = environment(self.root / "env")
        self.stored = self.published()

    def test_the_pointer_round_trips_and_is_kept_in_the_state_folder_never_in_the_environment(self) -> None:
        before = listing(self.prefix)
        self.assertIsNone(store.pointer(self.prefix))
        self.assertIsNone(store.pointed(self.prefix))
        self.assertEqual(store.active(self.prefix), "1.0.0", "no pointer: the cad installed there")
        written = store.point(self.stored, previous="elsewhere", prefix=self.prefix)
        folder = os.path.normcase(os.path.realpath(self.prefix))
        name = "pointer-%08x.json" % (binascii.crc32(folder.encode("utf-8", "surrogatepass")) & 0xFFFFFFFF)
        self.assertEqual(store.pointer_path(self.prefix), self.state / "store" / name)
        record = self.packages / "cad-1.0.0.dist-info" / "RECORD"
        stamp = record.stat()
        self.assertEqual({key: value for key, value in written.items() if key != "at"},
                         {"pointer": 1, "python": sys.implementation.cache_tag, "prefix": folder,
                          "record": "cad-1.0.0.dist-info/RECORD", "stamp": [stamp.st_mtime_ns, stamp.st_size],
                          "path": str(self.stored), "release": "1.0.1", "previous": "elsewhere"})
        self.assertEqual(json.loads((self.state / "store" / name).read_text(encoding="utf-8")), written)
        self.assertEqual(store.pointer(self.prefix), written)
        self.assertEqual(store.pointed(self.prefix), written)
        self.assertEqual(store.active(self.prefix), "1.0.1")
        kept = store.pointer(self.prefix)
        store.point(None, prefix=self.prefix)
        self.assertFalse(store.pointer_path(self.prefix).exists())
        store.point(None, prefix=self.prefix)  # no pointer to remove: nothing to do
        store.restore(kept, prefix=self.prefix)
        self.assertEqual(store.pointer(self.prefix), kept)
        self.assertEqual(store.active(self.prefix), "1.0.1")
        store.restore(None, prefix=self.prefix)
        self.assertIsNone(store.pointer(self.prefix))
        store.restore(None, prefix=self.prefix)
        store.restore(kept, prefix=self.prefix)
        store.clean()
        self.assertEqual(listing(self.prefix), before, "nothing of cad's written into the environment")

    def test_a_pointer_means_nothing_once_cad_is_installed_again_or_for_another_environment(self) -> None:
        store.point(self.stored, prefix=self.prefix)
        record = self.packages / "cad-1.0.0.dist-info" / "RECORD"
        stamp = record.stat()
        os.utime(record, ns=(stamp.st_atime_ns, stamp.st_mtime_ns + 1_000_000_000))
        self.assertIsNone(store.pointed(self.prefix))
        self.assertEqual(store.active(self.prefix), "1.0.0", "the release installed there")
        self.assertIsNotNone(store.pointer(self.prefix), "kept as it is, whatever it is for")
        written = store.point(self.stored, prefix=self.prefix)
        self.assertIsNotNone(store.pointed(self.prefix))
        for changes in ({"prefix": os.path.normcase(str(self.root))}, {"python": "cpython-27"}, {"pointer": 2},
                        {"path": str(self.root / "gone")}, {"stamp": "now"}):
            with self.subTest(changes=changes):
                store.restore({**written, **changes}, prefix=self.prefix)
                self.assertIsNone(store.pointed(self.prefix))
                self.assertEqual(store.active(self.prefix), "1.0.0")

    def test_the_newest_release_an_environment_holds_whatever_python_asks_and_however_whole_it_is(self) -> None:
        """``held``: what an installer that must never move cad down asks."""
        self.assertIsNone(store.held(self.root / "nothing"))
        self.assertEqual(store.held(self.prefix), "1.0.0", "the cad installed there")
        half_made = dist_info(self.packages, "2.0.1", record=False, metadata=False)
        self.assertEqual(store.held(self.prefix), "2.0.1", "an install left half made is read by its name")
        shutil.rmtree(half_made)
        written = store.point(self.published("3.1.0"), prefix=self.prefix)
        self.assertEqual(store.held(self.prefix), "3.1.0", "the stored release its pointer names")
        store.restore({**written, "python": "cpython-27"}, prefix=self.prefix)
        self.assertIsNone(store.pointed(self.prefix), "not this interpreter's to take")
        self.assertEqual(store.held(self.prefix), "3.1.0", "and held all the same")
        record = self.packages / "cad-1.0.0.dist-info" / "RECORD"
        stamp = record.stat()
        os.utime(record, ns=(stamp.st_atime_ns, stamp.st_mtime_ns + 1_000_000_000))
        self.assertEqual(store.held(self.prefix), "1.0.0", "cad installed again since: the pointer means nothing")

    def test_point_refuses_a_folder_that_is_no_stored_release_and_an_environment_with_no_cad(self) -> None:
        with self.assertRaises(OSError):
            store.point(self.root / "nothing", prefix=self.prefix)
        unmarked = self.staged(name="unmarked")
        with self.assertRaises(OSError):
            store.point(unmarked, prefix=self.prefix)
        empty, _packages = environment(self.root / "empty")
        shutil.rmtree(_packages / "cad-1.0.0.dist-info")
        with self.assertRaises(OSError):
            store.point(self.stored, prefix=empty)
        self.assertFalse(any(store.root().glob("pointer-*.json")), "nothing written")


def holding(marker: Path) -> subprocess.Popen:
    """A process that holds ``marker`` as ``_cad_release`` does (open, and on POSIX its shared lock) until its
    standard input closes; returned once it holds it."""
    code = ("import os, sys\nhandle = open(sys.argv[1], 'rb')\nif os.name != 'nt':\n    import fcntl\n"
            "    fcntl.flock(handle, fcntl.LOCK_SH | fcntl.LOCK_NB)\nprint('held', flush=True)\nsys.stdin.readline()\n")
    child = subprocess.Popen([sys.executable, "-c", code, str(marker)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             text=True)
    if child.stdout.readline().strip() != "held":
        child.kill()
        raise AssertionError("the holder did not hold the marker")
    return child


def release(child: subprocess.Popen) -> None:
    child.stdin.close()
    child.wait(SECONDS)
    child.stdout.close()


class RemoveTest(StoreCase):
    def test_a_release_no_process_runs_is_removed_whole(self) -> None:
        stored = self.published()
        self.assertTrue(store.remove(stored))
        self.assertFalse(stored.exists())
        self.assertEqual(list(store.root().iterdir()), [], "nothing left aside")

    def test_a_release_a_process_runs_stays_until_it_ends(self) -> None:
        stored = self.published()
        child = holding(stored / "cad-store.json")
        self.addCleanup(release, child)
        self.assertFalse(store.remove(stored))
        self.assertIsNotNone(store.marker(stored), "whole")
        self.assertEqual(store.clean(), [])
        self.assertTrue(stored.is_dir())
        release(child)
        self.assertTrue(store.remove(stored))
        self.assertFalse(stored.exists())

    def test_a_folder_with_no_marker_is_no_release_and_goes(self) -> None:
        folder = write(store.root() / "1.0.1-half" / "cad" / "__init__.py").parents[1]
        self.assertTrue(store.remove(folder))
        self.assertFalse(folder.exists())


class CleanTest(StoreCase):
    def test_what_clean_keeps_and_what_it_takes(self) -> None:
        here, _here_packages = environment(self.root / "here")
        other, _other_packages = environment(self.root / "other")
        gone, _gone_packages = environment(self.root / "gone")
        replaced, replaced_packages = environment(self.root / "replaced")
        fresh, _fresh_packages = environment(self.root / "fresh")
        releases = {name: self.published(name) for name in
                    ("1.0.0", "1.0.1", "1.0.2", "1.0.3", "1.0.4", "1.0.5", "1.0.6", "1.0.7", "1.0.8")}
        now = time.time()
        old = now - store.STALE_SECONDS - 60
        store.point(releases["1.0.1"], previous=str(releases["1.0.2"]), prefix=here)
        store.point(releases["1.0.3"], prefix=other)  # another environment's, which lasts
        store.point(releases["1.0.4"], prefix=gone)
        shutil.rmtree(gone)  # its environment is gone
        store.point(releases["1.0.5"], prefix=replaced)
        record = replaced_packages / "cad-1.0.0.dist-info" / "RECORD"
        os.utime(record, ns=(0, record.stat().st_mtime_ns + 1_000_000_000))  # cad installed there again since
        for prefix in (here, other, gone, replaced):
            os.utime(store.pointer_path(prefix), (old, old))  # written long ago
        # A pointer that means nothing as yet, written a moment ago: an update may be writing it.
        store.point(releases["1.0.7"], previous=str(releases["1.0.8"]), prefix=fresh)
        shutil.rmtree(fresh)
        unreadable = [write(store.root() / "pointer-00000000.json", "{not json"),
                      write(store.root() / "pointer-00000001.json", "[1, 2]")]
        for path in unreadable:
            os.utime(path, (old, old))
        unmarked = write(store.root() / "1.0.9-half" / "cad" / "__init__.py").parents[1]
        trash = write(store.root() / ".trash-1.0.10-abcd" / "cad" / "__init__.py").parents[1]
        abandoned = write(store.root() / ".building-1-old" / "cad" / "__init__.py").parents[1]
        building = write(store.root() / ".building-2-new" / "cad" / "__init__.py").parents[1]
        os.utime(abandoned, (now - store.ABANDONED_SECONDS - 60, now - store.ABANDONED_SECONDS - 60))
        write(store.root() / "1.0.11-a-file", "a file where a release's folder would be")
        removed = store.clean(keep=[releases["1.0.0"]], now=now)
        self.assertEqual(sorted(removed), sorted([
            store.pointer_path(gone).name, store.pointer_path(replaced).name, releases["1.0.4"].name,
            releases["1.0.5"].name, releases["1.0.6"].name, unmarked.name, trash.name, abandoned.name]))
        for name in ("1.0.0", "1.0.1", "1.0.2", "1.0.3", "1.0.7", "1.0.8"):
            self.assertIsNotNone(store.marker(releases[name]), f"{name} is kept")
        self.assertTrue(building.is_dir(), "a build that may still run is left")
        self.assertTrue((store.root() / "1.0.11-a-file").is_file())
        self.assertEqual(sorted(path.name for path in store.root().glob("pointer-*.json")), sorted([
            store.pointer_path(here).name, store.pointer_path(other).name, store.pointer_path(fresh).name,
            *(path.name for path in unreadable)]), "what cannot be read is left: an update may be writing it")
        self.assertEqual(store.clean(keep=[releases["1.0.0"]], now=now), [], "nothing more to take")
        later = now + store.STALE_SECONDS + 1
        self.assertEqual(sorted(store.clean(keep=[releases["1.0.0"]], now=later)), sorted([
            store.pointer_path(fresh).name, releases["1.0.7"].name, releases["1.0.8"].name]),
            "the same pointer, once old, and the releases it alone named")

    def test_clean_never_raises(self) -> None:
        self.assertEqual(store.clean(), [], "no store at all")
        write(self.state / "store", "a file where the store would be")
        self.assertEqual(store.clean(), [])


class SwitchesTest(unittest.TestCase):
    """``packages``, ``switches`` and ``running`` ask what ``_cad_release`` did as this interpreter started."""

    def test_in_a_process_the_bootstrap_did_not_run_in_or_ran_from_a_checkout(self) -> None:
        with mock.patch.dict(sys.modules):
            sys.modules.pop("_cad_release", None)
            self.assertEqual((store.packages(), store.switches(), store.running()), (None, False, None))
            self.assertNotIn("_cad_release", sys.modules, "asked, never imported")
            checkout = types.SimpleNamespace(HERE=str(STORE_SOURCE.parents[2]), STORED=None)
            sys.modules["_cad_release"] = checkout  # type: ignore[assignment]
            self.assertEqual((store.packages(), store.switches(), store.running()),
                             (STORE_SOURCE.parents[2], False, None), "a checkout's source is no environment's")


class RealEnvironmentTest(unittest.TestCase):
    """What the store writes, read by a real interpreter as it starts; what the store reads of a real one."""

    @classmethod
    def setUpClass(cls) -> None:
        scratch = temporary_directory(prefix="store-env-")
        cls.addClassCleanup(scratch.cleanup)
        cls.root = Path(scratch.name).resolve()
        cls.env = Environment(cls.root / "env")

    def setUp(self) -> None:
        self.env.install()
        self.state = self.root / f"state-{self._testMethodName}"
        self.enterContext(mock.patch.dict(os.environ, {"CAD_STATE_DIR": str(self.state)}))
        self.stored = self.env.store(store.folder("1.0.1"))

    def asked(self, *flags: str) -> list[Any]:
        """``switches``, ``packages`` and ``running`` as a process of the environment answers them, with the store's
        own source loaded from this checkout by its path (nothing else of cad's is on that process's path)."""
        code = ("import importlib.util, json, sys\n"
                f"spec = importlib.util.spec_from_file_location('store', {str(STORE_SOURCE)!r})\n"
                "store = importlib.util.module_from_spec(spec); spec.loader.exec_module(store)\n"
                "print(json.dumps([store.switches(), *(str(f) if f else None for f in (store.packages(), "
                "store.running()))]))\n")
        found = self.env.run(*flags, "-c", code, state=self.state)
        self.assertEqual((found.returncode, found.stderr), (0, ""))
        return json.loads(found.stdout)

    def test_what_point_writes_the_bootstrap_takes_and_switches_says_so(self) -> None:
        before = listing(self.env.prefix)
        packages = str(self.env.packages)
        self.assertEqual(self.asked(), [True, packages, None])
        self.assertEqual(self.asked("-S"), [False, None, None], "no .pth line ran: nothing would take a pointer")
        store.point(self.stored, prefix=self.env.prefix)
        self.assertEqual(store.pointed(self.env.prefix)["release"], "1.0.1")
        self.assertEqual(store.active(self.env.prefix), "1.0.1")
        found = self.env.probe(state=self.state)
        self.assertEqual((found["cad"], found["stored"], found["held"]), ("stored", str(self.stored), True))
        self.assertEqual(self.asked(), [True, packages, str(self.stored)])
        self.assertEqual(listing(self.env.prefix), before, "nothing of cad's written into the environment")
        (self.env.record).unlink()
        self.assertEqual(self.asked()[0], False, "an install with no RECORD: no pointer could be tied to it")

    def test_a_release_the_bootstrap_holds_is_not_removed_until_its_process_ends(self) -> None:
        store.point(self.stored, prefix=self.env.prefix)
        child = subprocess.Popen([self.env.python, "-c", "import sys, _cad_release as r; print(r.STORED, flush=True); "
                                  "sys.stdin.readline()"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True,
                                 env=child_environment(self.state), cwd=self.env.prefix)
        self.addCleanup(release, child)
        self.assertEqual(child.stdout.readline().strip(), str(self.stored))
        self.assertFalse(store.remove(self.stored))
        store.point(None, prefix=self.env.prefix)
        self.assertEqual(store.clean(), [], "pointed at by nothing, and still run")
        release(child)
        self.assertEqual(store.clean(), [self.stored.name])


if __name__ == "__main__":
    unittest.main()
