"""The file a view's build feed is about has its catalog row computed as its save is announced,
off the request threads, so the catalog read that follows the build finds it (``cadgen.viewer.warm``)."""
from __future__ import annotations

import hashlib
import os
import threading
import unittest
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from cadgen import catalog
from cadgen.viewer import scanner, warm
from cadgen.viewer.http_app import create_cad_app
from tests.python.support.store_fixtures import seed_result
from tests.python.support.tmp_root import generated_cad_directory

# A guard against a hang, never a measurement: every wait below is for a condition.
HANG = 60.0


class _Watched:
    """A single-flight event that also says when someone starts waiting on it."""

    def __init__(self, inner: threading.Event, waiting: threading.Event) -> None:
        self.inner, self.waiting = inner, waiting

    def wait(self, timeout=None):
        self.waiting.set()
        return self.inner.wait(timeout)


def _watch_flight(flights: dict, lock, match, waiting: threading.Event) -> None:
    with lock:
        (key,) = [key for key in flights if match(key)]
        flights[key] = _Watched(flights[key], waiting)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class _WindowsFstat:
    """``os`` as ``catalog`` sees it on Windows: since Python 3.12 a read handle's ``st_ctime``
    is the file's last change, where its path's is its creation. Here they are a clock tick apart."""

    def __getattr__(self, name):
        return getattr(os, name)

    @staticmethod
    def fstat(fd):
        stat = os.fstat(fd)
        fields = {name: getattr(stat, name) for name in dir(stat) if name.startswith("st_")}
        return SimpleNamespace(**{**fields, "st_ctime_ns": stat.st_ctime_ns + 15_625_000})


class CatalogWarmTests(unittest.TestCase):
    def setUp(self):
        temporary = generated_cad_directory(prefix="catalog-warm-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve() / "project"
        self.root.mkdir()
        self.store = str(Path(temporary.name).resolve() / "store")
        env = mock.patch.dict(os.environ, {"CADGEN_CACHE_DIR": self.store})
        env.start()
        self.addCleanup(env.stop)
        self.part = self.root / "part.step"
        self.part.write_bytes(b"first version\n")
        self.app = create_cad_app(host="127.0.0.1", port=0)

    def replace(self, data: bytes) -> None:
        staged = self.root / ".part.step.staged"
        staged.write_bytes(data)
        os.replace(staged, self.part)

    @contextmanager
    def ledger(self, tree: str, phase: str = "STEP saved"):
        """The daemon's ledger, listing a build of part.step that has saved it."""
        output = str(self.part)
        job = {"id": "epoch:job-1", "epoch": "epoch", "sequence": 1, "tool": "run", "storeRoot": self.store,
               "outputs": [output], "state": "building", "phase": phase,
               "savedResults": {output: {"tree": tree, "documentHash": _sha(self.part), "output": output}}}
        with mock.patch("cadgen.daemon.client.watch_jobs", return_value={"jobsCursor": "epoch:2", "jobs": [job]}):
            yield

    def entry(self) -> dict:
        [row] = self.app.read_catalog(str(self.part))["entries"]
        return row

    def test_a_save_the_feed_lists_is_warmed_on_a_thread_of_its_own_and_the_read_finds_it(self):
        tree = seed_result(self.part, {"label": "saved"})
        with self.ledger(tree):
            self.assertEqual(self.app.build_status(str(self.part), after="epoch:1")["phase"], "STEP saved")
        self.assertTrue(self.app.catalog_warm.wait_settled(HANG))
        with mock.patch.object(catalog, "open_shared_for_read", side_effect=AssertionError("read the file again")), \
                mock.patch.object(scanner, "_build_step_entry", side_effect=AssertionError("built the row again")):
            entry = self.entry()
        # The row is the file's: its digest, and the tree its bytes name.
        self.assertEqual((entry["documentHash"], entry["hash"]), (_sha(self.part), tree))

    def test_the_feed_answers_before_the_warm_and_a_version_is_warmed_once(self):
        tree = seed_result(self.part, {"label": "saved"})
        entered, release, finished = threading.Event(), threading.Event(), threading.Event()
        warmed = []

        def warm_row(path):
            warmed.append((threading.current_thread().name, os.path.basename(path)))
            entered.set()
            release.wait(HANG)
            finished.set()

        with mock.patch.object(warm, "catalog_entry", warm_row), self.ledger(tree):
            self.app.build_status(str(self.part), after="epoch:1")
            self.assertFalse(finished.is_set())  # answered while its save waits to be warmed
            self.assertTrue(entered.wait(HANG))
            self.app.build_status(str(self.part), after="epoch:1")  # the feed lists the save again
            release.set()
            self.assertTrue(self.app.catalog_warm.wait_settled(HANG))
            self.app.build_status(str(self.part), after="epoch:1")
            self.assertTrue(self.app.catalog_warm.wait_settled(HANG))
            self.assertEqual(warmed, [("cadgen-viewer-catalog-warm", "part.step")])
            self.replace(b"second version\n")
            self.app.build_status(str(self.part), after="epoch:1")
            self.assertTrue(self.app.catalog_warm.wait_settled(HANG))
        self.assertEqual(len(warmed), 2)

    def test_a_catalog_read_joins_the_row_its_warm_is_building(self):
        tree = seed_result(self.part, {"label": "saved"})
        building, release, waiting = threading.Event(), threading.Event(), threading.Event()
        builders, read = [], []
        build = scanner._build_step_entry

        def held_build(*args, **kwargs):
            builders.append(threading.current_thread().name)
            building.set()
            release.wait(HANG)
            return build(*args, **kwargs)

        with mock.patch.object(scanner, "_build_step_entry", held_build):
            self.app.catalog_warm.saved({str(self.part): tree}, str(self.part))
            self.assertTrue(building.wait(HANG))
            _watch_flight(scanner._STEP_ENTRY_FLIGHTS, scanner._STEP_ENTRY_CACHE_LOCK,
                          lambda key: key[1] == str(self.part), waiting)
            reader = threading.Thread(target=lambda: read.append(self.entry()))
            reader.start()
            self.assertTrue(waiting.wait(HANG))
            release.set()
            reader.join(HANG)
            self.assertTrue(self.app.catalog_warm.wait_settled(HANG))
        self.assertEqual(builders, ["cadgen-viewer-catalog-warm"])
        self.assertEqual(read[0]["hash"], tree)

    def test_readers_of_one_file_version_share_one_read(self):
        opened, release, waiting = threading.Event(), threading.Event(), threading.Event()
        reads, answers = [], []
        real_open = catalog.open_shared_for_read

        def held_open(path):
            reads.append(path)
            opened.set()
            release.wait(HANG)
            return real_open(path)

        flight = (str(self.part), *catalog._file_version(self.part.stat()))
        with mock.patch.object(catalog, "open_shared_for_read", held_open):
            readers = [threading.Thread(target=lambda: answers.append(catalog.artifact_file_hash(self.part))) for _ in range(2)]
            readers[0].start()
            self.assertTrue(opened.wait(HANG))
            _watch_flight(catalog._ARTIFACT_HASH_FLIGHTS, catalog._ARTIFACT_HASH_MEMO_LOCK, lambda key: key == flight, waiting)
            readers[1].start()
            self.assertTrue(waiting.wait(HANG))
            release.set()
            for reader in readers:
                reader.join(HANG)
        self.assertEqual(len(reads), 1)
        self.assertEqual(answers, [_sha(self.part)] * 2)

    def test_a_file_replaced_during_its_warm_is_read_afresh_and_never_served_stale(self):
        first = seed_result(self.part, {"label": "first"})
        held, release, resumed = threading.Event(), threading.Event(), threading.Event()
        real_open = catalog.open_shared_for_read
        opens = []

        class HeldOnceRead:
            """The warm's read of the first version, held after its bytes are read and the file
            is closed but before the warm checks the path still names that version (Windows
            refuses to replace a file someone holds open)."""

            def __init__(self, handle) -> None:
                self.handle = handle

            def __enter__(self):
                return self.handle.__enter__()

            def __exit__(self, *exc):
                closed = self.handle.__exit__(*exc)
                held.set()
                release.wait(HANG)
                resumed.set()
                return closed

        def holding_open(path):
            handle = real_open(path)
            opens.append(path)
            return HeldOnceRead(handle) if len(opens) == 1 else handle

        with mock.patch.object(catalog, "open_shared_for_read", holding_open):
            self.app.catalog_warm.saved({str(self.part): first}, str(self.part))
            self.assertTrue(held.wait(HANG))
            self.replace(b"second version\n")
            second = seed_result(self.part, {"label": "second"})
            # The read neither waits for the warm (still held when it answers) nor takes its version.
            self.assertEqual((self.entry()["documentHash"], self.entry()["hash"]), (_sha(self.part), second))
            self.assertFalse(resumed.is_set())
            release.set()
            self.assertTrue(self.app.catalog_warm.wait_settled(HANG))
        # Nor does what the warm read of the first version answer for the second.
        self.assertEqual((self.entry()["documentHash"], self.entry()["hash"]), (_sha(self.part), second))
        self.assertNotEqual(first, second)

    def test_saves_waiting_to_be_warmed_are_bounded(self):
        held, release = threading.Event(), threading.Event()
        warmed = []

        def warm_row(path):
            warmed.append(os.path.basename(path))
            held.set()
            release.wait(HANG)

        paths = [str(self.root / f"part{index:02d}.step") for index in range(warm.WARM_PENDING_LIMIT + 4)]
        for path in paths:
            Path(path).write_bytes(os.path.basename(path).encode("ascii"))
        with mock.patch.object(warm, "catalog_entry", warm_row):
            self.app.catalog_warm.saved({paths[0]: ""}, paths[0])
            self.assertTrue(held.wait(HANG))
            for path in paths[1:]:  # each view's feed, about its own file
                self.app.catalog_warm.saved({path: ""}, path)
            release.set()
            self.assertTrue(self.app.catalog_warm.wait_settled(HANG))
        # The one being warmed, then as many as wait at once; the rest are left to the reads.
        self.assertEqual(warmed, [os.path.basename(path) for path in paths[: 1 + warm.WARM_PENDING_LIMIT]])

    def test_only_the_file_the_feed_is_about_is_warmed(self):
        # A parent's build saves its children too: each view's own feed warms its own file.
        others = [self.root / "a.step", self.root / "b.step"]
        for other in others:
            other.write_bytes(other.name.encode("ascii"))
        saves = {str(path): "" for path in [*others, self.part]}
        warmed = []
        with mock.patch.object(warm, "catalog_entry", lambda path: warmed.append(os.path.basename(path))):
            self.app.catalog_warm.saved(saves, str(self.part))
            self.assertTrue(self.app.catalog_warm.wait_settled(HANG))
            # A file the feed is about that no listed build saved is not warmed.
            self.app.catalog_warm.saved({str(others[0]): ""}, str(others[1]))
            self.assertTrue(self.app.catalog_warm.wait_settled(HANG))
        self.assertEqual(warmed, ["part.step"])

    def test_a_warm_that_fails_never_reaches_the_feed_nor_stops_the_next(self):
        tree = seed_result(self.part, {"label": "saved"})
        with mock.patch.object(warm, "catalog_entry", side_effect=OSError("disk gone")), self.ledger(tree), \
                self.assertLogs("cadgen.viewer.warm", "WARNING"):
            self.assertEqual(self.app.build_status(str(self.part), after="epoch:1")["phase"], "STEP saved")
            self.assertTrue(self.app.catalog_warm.wait_settled(HANG))
        with mock.patch.object(warm.CatalogWarmer, "saved", side_effect=RuntimeError("warm is broken")), \
                self.ledger(tree), self.assertLogs("cadgen.viewer.preview", "WARNING"):
            self.assertEqual(self.app.build_status(str(self.part), after="epoch:1")["phase"], "STEP saved")
        self.replace(b"second version\n")
        with mock.patch.object(warm.threading, "Thread", side_effect=RuntimeError("can't start new thread")), \
                self.assertLogs("cadgen.viewer.warm", "WARNING"):
            self.app.catalog_warm.saved({str(self.part): ""}, str(self.part))
        self.assertTrue(self.app.catalog_warm.wait_settled(HANG))
        # None of it wedged the warmer: the save left waiting goes with the next one.
        warmed = []
        with mock.patch.object(warm, "catalog_entry", lambda path: warmed.append(os.path.basename(path))):
            self.replace(b"third version\n")
            self.app.catalog_warm.saved({str(self.part): ""}, str(self.part))
            self.assertTrue(self.app.catalog_warm.wait_settled(HANG))
        self.assertEqual(warmed, ["part.step"])

    def test_a_same_size_save_inside_one_mtime_tick_is_a_new_version(self):
        # A coarse-mtime filesystem (HFS+, FAT, some shares) can give a rename-save the old file's
        # mtime: the digest of the old bytes must not answer for the new ones.
        old = self.part.stat()
        self.assertEqual(catalog.artifact_file_hash(self.part), _sha(self.part))
        self.replace(b"other version\n")  # the same size as "first version\n"
        os.utime(self.part, ns=(old.st_atime_ns, old.st_mtime_ns))
        self.assertEqual((self.part.stat().st_size, self.part.stat().st_mtime_ns), (old.st_size, old.st_mtime_ns))
        self.assertEqual(catalog.artifact_file_hash(self.part), _sha(self.part))

    def test_a_digest_is_remembered_where_a_handle_reports_another_ctime_than_its_path(self):
        # On Windows the two ctimes differ for every save by rename over an earlier file, and for
        # setUp's file when its write lands a clock tick after its creation: the memo compared them
        # and never remembered such a file, so the warmed save's catalog read read it again
        # (Windows CI, 2026-10-03).
        with mock.patch.object(catalog, "os", _WindowsFstat()):
            self.assertEqual(catalog.artifact_file_hash(self.part), _sha(self.part))
            with mock.patch.object(catalog, "open_shared_for_read", side_effect=AssertionError("read the file again")):
                self.assertEqual(catalog.artifact_file_hash(self.part), _sha(self.part))

    def test_an_unbuilt_file_is_read_once_for_its_row(self):
        reads = []

        def counting(real):
            return lambda path: (reads.append(path), real(path))[1]

        with mock.patch.object(catalog, "open_shared_for_read", counting(catalog.open_shared_for_read)), \
                mock.patch.object(scanner, "open_shared_for_read", counting(scanner.open_shared_for_read)):
            entry = self.entry()  # nothing built it: no tree names its digest
        self.assertEqual((entry["documentHash"], len(reads)), (_sha(self.part), 1))

    def test_only_a_file_with_a_row_is_warmed(self):
        # A file under a hidden folder has a row (named, never found); a hidden file, a file
        # gone again and one CAD does not open do not.
        inside = self.root / ".worktree" / "part.step"
        inside.parent.mkdir()
        inside.write_bytes(b"inside\n")
        hidden = self.root / ".hidden.step"
        hidden.write_bytes(b"hidden\n")
        notes = self.root / "notes.txt"
        notes.write_bytes(b"notes\n")
        warmed = []
        with mock.patch.object(warm, "catalog_entry", lambda path: warmed.append(path)):
            for path in (inside, hidden, notes, self.root / "gone.step"):
                self.app.catalog_warm.saved({str(path): ""}, str(path))
            self.assertTrue(self.app.catalog_warm.wait_settled(HANG))
        self.assertEqual(warmed, [str(inside)])

if __name__ == "__main__":
    unittest.main()
