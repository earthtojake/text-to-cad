"""The catalog is fresh on every request, and a warm request does not re-list the tree.

The client polls the catalog every 2s, and the artifact-status route reads it on
every 400ms build poll, so a served root holding a project's scratch — thousands
of renders, BREPs and logs under ``tmp/`` — used to cost one full walk per
request (two, on the steady path). The scanner now memoises each directory's
relevant rows on that directory's own identity. These pin both halves of that
bargain: nothing a walk can observe goes stale (a new model appears on the next
request, a deleted or renamed one leaves, a retargeted link is followed), a
directory whose stamps cannot vouch for it is never trusted for long, and a warm
walk re-lists nothing that has not changed.

The scanner's two clocks are held by the fixture — wall time decides whether a
directory has settled, monotonic time how old a remembered listing is — so no
assertion here depends on how fast the machine runs.
"""

from __future__ import annotations

import contextlib
import os
import shutil
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from cadgen import catalog
from cadgen._internal.shared_read import open_shared_for_read
from cadgen.viewer import scanner
from cadgen.viewer.backend import LocalAssetBackend
from cadgen.viewer.scanner import scan_cad_directory

JUNK_DIRECTORIES = 10
JUNK_PER_DIRECTORY = 50
SECOND_NS = 1_000_000_000


def stamp(path: str) -> int:
    """A directory's newer stamp: what the settle rule measures from."""
    result = os.stat(path)
    return max(result.st_mtime_ns, result.st_ctime_ns)


def with_stamps(result: os.stat_result, *, mtime_ns: int, ctime_ns: int) -> os.stat_result:
    """``result`` reporting other modification and change times."""
    values = list(result)
    values[8], values[9] = mtime_ns // SECOND_NS, ctime_ns // SECOND_NS
    named = {
        name: getattr(result, name)
        for name in dir(result)
        if name.startswith("st_")
        and name not in ("st_mode", "st_ino", "st_dev", "st_nlink", "st_uid", "st_gid", "st_size")
    }
    named.update(
        st_mtime=mtime_ns / SECOND_NS, st_mtime_ns=mtime_ns,
        st_ctime=ctime_ns / SECOND_NS, st_ctime_ns=ctime_ns,
    )
    return os.stat_result(values, named)


class FreshnessFixture(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.root = os.path.join(self.tmp, "models")
        os.makedirs(self.root)
        previous = os.environ.get("CADGEN_CACHE_DIR")
        os.environ["CADGEN_CACHE_DIR"] = os.path.join(self.tmp, "cache")
        self.addCleanup(self._restore, previous)
        self.write("gripper/base.stl", "solid base\nendsolid base\n")
        self.write("gripper/finger.stl", "solid finger\nendsolid finger\n")
        # A project's scratch: nothing here is an artifact, and all of it used
        # to be re-listed on every request.
        for directory in range(JUNK_DIRECTORIES):
            for index in range(JUNK_PER_DIRECTORY):
                self.write(f"gripper/tmp/renders/r{directory}/frame{index}.png", "x")
        # The scanner's clocks, held still: `self.wall` is the time a listing is
        # read at, `self.age` the monotonic clock a remembered listing ages by.
        self.wall = stamp(self.root)
        self.age = 0
        for name, clock in (("_wall_ns", lambda: self.wall), ("_monotonic_ns", lambda: self.age)):
            patcher = mock.patch.object(scanner, name, clock)
            patcher.start()
            self.addCleanup(patcher.stop)

    @staticmethod
    def _restore(previous) -> None:
        if previous is None:
            os.environ.pop("CADGEN_CACHE_DIR", None)
        else:
            os.environ["CADGEN_CACHE_DIR"] = previous

    def write(self, relative: str, text: str) -> str:
        path = os.path.join(self.root, *relative.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        Path(path).write_text(text, encoding="utf-8")
        return path

    def settle(self, *tops: str) -> None:
        """Move the wall clock past the settle window of every directory under ``tops``.

        A listing is trusted only once its directory has been quiet for a while
        (timestamp granularity), so a fixture built a millisecond ago would never
        be remembered at all. ctime cannot be backdated, so time moves instead.
        """
        newest = max(
            stamp(directory) for top in (tops or (self.root,)) for directory, _, _ in os.walk(top)
        )
        self.wall = max(self.wall, newest + scanner._LISTING_SETTLE_NS)

    def files(self) -> list[str]:
        return [entry["file"] for entry in scan_cad_directory(self.root, defer_unpreferred=True)["entries"]]

    def listed(self) -> list[str]:
        """The directories a walk actually lists, in order."""
        with mock.patch.object(scanner.os, "scandir", wraps=os.scandir) as scandir:
            self.files()
        return [os.path.relpath(str(call.args[0]), self.root) for call in scandir.call_args_list]

    @contextlib.contextmanager
    def reported_stamps(self, directory: str, stamps):
        """Make ``os.stat`` report ``stamps(real_result) -> (mtime_ns, ctime_ns)``
        for ``directory``, the way another filesystem would."""
        real_stat = os.stat
        target = os.path.abspath(directory)

        def fake_stat(path, *args, **kwargs):
            result = real_stat(path, *args, **kwargs)
            if isinstance(path, (str, os.PathLike)) and os.path.abspath(os.fspath(path)) == target:
                mtime_ns, ctime_ns = stamps(result)
                return with_stamps(result, mtime_ns=mtime_ns, ctime_ns=ctime_ns)
            return result

        with mock.patch.object(scanner.os, "stat", fake_stat):
            yield


class WarmWalks(FreshnessFixture):
    def test_a_warm_walk_lists_no_settled_directory_again(self) -> None:
        self.settle()
        cold = self.listed()
        self.assertEqual(len(cold), 4 + JUNK_DIRECTORIES, cold)
        self.assertEqual(self.listed(), [], "a warm walk re-listed directories that had not changed")
        self.assertEqual(self.files(), ["gripper/base.stl", "gripper/finger.stl"])

    def test_only_the_changed_directory_is_listed_again(self) -> None:
        self.settle()
        self.listed()
        self.write("gripper/tmp/renders/r3/frame_new.png", "x")
        self.assertEqual(self.listed(), [os.path.join("gripper", "tmp", "renders", "r3")])

    def test_a_directory_written_within_the_settle_window_is_never_trusted(self) -> None:
        # Its stamps may not move again for a change landing in the same clock
        # tick, so a listing taken while it is this fresh must not be reused.
        self.settle()
        self.listed()
        self.write("gripper/tmp/renders/r5/frame_new.png", "x")
        fresh = os.path.join("gripper", "tmp", "renders", "r5")
        self.wall = stamp(os.path.join(self.root, fresh))  # the walks run as the write lands
        self.assertIn(fresh, self.listed())
        self.assertEqual(self.listed(), [fresh], "a still-settling directory must be re-listed every walk")

    def test_an_mtime_put_back_does_not_make_a_fresh_directory_look_settled(self) -> None:
        # An extractor that restores the directory's recorded mtime leaves only
        # ctime saying the directory just changed; settling is measured from it.
        self.settle()
        self.listed()
        self.write("gripper/tmp/renders/r5/frame_new.png", "x")
        fresh = os.path.join("gripper", "tmp", "renders", "r5")
        an_hour_ago = self.wall - 3600 * SECOND_NS
        os.utime(os.path.join(self.root, fresh), ns=(an_hour_ago, an_hour_ago))
        self.wall = stamp(os.path.join(self.root, fresh))
        self.assertIn(fresh, self.listed())
        self.assertEqual(self.listed(), [fresh])


class StampsThatCannotVouch(FreshnessFixture):
    """Where the directory's identity can fail to move, the memo must not trust it."""

    def test_a_directory_whose_stamps_are_not_times_is_listed_on_every_walk(self) -> None:
        # A macOS exFAT volume root reports mtime and ctime 0 forever, FAT
        # cannot store a time before 1980, and an archive can zero an mtime:
        # an identity built on those never changes, so it is never remembered.
        fat_epoch = 315_532_800 * SECOND_NS  # 1980-01-01T00:00:00Z
        cases = {
            "exFAT volume root": lambda real: (0, 0),
            "FAT epoch": lambda real: (fat_epoch, fat_epoch),
            "mtime zeroed by an archive": lambda real: (0, real.st_ctime_ns),
        }
        for label, stamps in cases.items():
            with self.subTest(label), self.reported_stamps(self.root, stamps):
                self.settle()
                self.listed()
                self.assertEqual(self.listed(), ["."], "the untrustworthy root must be re-listed every walk")
                added = self.write(f"{label.split()[0]}.stl", "solid x\nendsolid x\n")
                self.assertIn(os.path.basename(added), self.files())
                os.unlink(added)
                self.assertNotIn(os.path.basename(added), self.files())

    def test_a_directory_whose_stamps_come_back_is_listed_again_after_the_ttl(self) -> None:
        # tar, unzip, rsync -a and cp -p put a directory's mtime back after
        # filling it. FAT and exFAT keep no ctime of their own (modelled here
        # by reporting mtime in its place), so the whole identity then repeats
        # and only the listing's age can catch the change.
        gripper = os.path.join(self.root, "gripper")
        recorded = os.stat(gripper).st_mtime_ns
        with self.reported_stamps(gripper, lambda real: (real.st_mtime_ns, real.st_mtime_ns)):
            self.settle()
            self.assertEqual(self.files(), ["gripper/base.stl", "gripper/finger.stl"])
            self.write("gripper/extracted.stl", "solid x\nendsolid x\n")
            os.utime(gripper, ns=(recorded, recorded))
            self.assertEqual(
                self.listed(), [], "premise: the identity came back, so nothing on disk shows the change"
            )
            self.age += scanner._LISTING_TTL_NS - 1
            self.assertEqual(self.listed(), [], "a listing younger than the TTL is still served")
            self.age += 1
            self.assertIn("gripper", self.listed())
            self.assertIn("gripper/extracted.stl", self.files())


class MemoHygiene(FreshnessFixture):
    def remembered(self) -> list[str]:
        inside = self.root + os.sep
        return [
            os.path.relpath(key, self.root)
            for key in scanner._LISTING_CACHE
            if key == self.root or key.startswith(inside)
        ]

    def test_a_deleted_subtree_is_forgotten_with_it(self) -> None:
        self.settle()
        self.files()
        scratch = os.path.join("gripper", "tmp")
        self.assertIn(os.path.join(scratch, "renders", "r3"), self.remembered())
        shutil.rmtree(os.path.join(self.root, scratch))
        self.assertEqual(self.files(), ["gripper/base.stl", "gripper/finger.stl"])
        self.assertEqual([key for key in self.remembered() if key.startswith(scratch)], [])

    def test_the_memo_is_bounded_and_keeps_the_most_recently_walked(self) -> None:
        self.settle()
        with mock.patch.object(scanner, "_LISTING_CACHE_LIMIT", 5):
            walked = self.listed()
            self.assertEqual(len(scanner._LISTING_CACHE), 5)
        # Least recently walked out first, rather than everything at once.
        self.assertEqual(self.remembered(), walked[-5:])


def join_catalog_refreshes() -> None:
    """Wait out the background refresh a stale ``read_catalog`` starts.

    That thread hashes every model while the test goes on mutating the tree.
    Those reads no longer block a delete (``ReadsNeverBlockDeletion`` pins it),
    but NTFS still refuses a rename onto a file any handle has open, and without
    POSIX delete semantics a file deleted under an open handle stays listed
    until it closes, so a mutation raced against the refresh would make the
    next request's answer depend on thread timing. Joining first keeps each
    request's expected answer exact.
    """
    for thread in threading.enumerate():
        if thread.name == "cadgen-viewer-catalog":
            thread.join(timeout=60)
            if thread.is_alive():
                raise AssertionError("the catalog refresh did not finish within 60s")


class CatalogFreshness(FreshnessFixture):
    def catalog_files(self, backend: LocalAssetBackend) -> list[str]:
        return [entry["rootRelativeFile"] for entry in backend.read_catalog()["entries"]]

    def test_a_new_model_appears_and_a_deleted_one_disappears_on_the_next_request(self) -> None:
        backend = LocalAssetBackend(self.root)
        self.settle()
        self.assertEqual(self.catalog_files(backend), ["gripper/base.stl", "gripper/finger.stl"])
        self.catalog_files(backend)  # warm

        # Deep inside the scratch tree the walk no longer re-lists.
        new_model = self.write("gripper/tmp/renders/r7/probe.stl", "solid probe\nendsolid probe\n")
        self.assertIn("gripper/tmp/renders/r7/probe.stl", self.catalog_files(backend))
        self.settle()  # its listing is now trusted and cached
        self.assertIn("gripper/tmp/renders/r7/probe.stl", self.catalog_files(backend))

        join_catalog_refreshes()
        os.unlink(new_model)
        self.assertNotIn("gripper/tmp/renders/r7/probe.stl", self.catalog_files(backend))

        # A new directory, and a rename.
        self.write("gripper/tmp/renders/r7/deeper/part.step", "ISO-10303-21;\n")
        self.assertIn("gripper/tmp/renders/r7/deeper/part.step", self.catalog_files(backend))
        self.settle()
        join_catalog_refreshes()
        os.replace(
            os.path.join(self.root, "gripper", "finger.stl"),
            os.path.join(self.root, "gripper", "thumb.stl"),
        )
        files = self.catalog_files(backend)
        self.assertIn("gripper/thumb.stl", files)
        self.assertNotIn("gripper/finger.stl", files)

    def test_a_retargeted_directory_link_is_followed_to_its_new_target(self) -> None:
        first = os.path.join(self.tmp, "library_a")
        second = os.path.join(self.tmp, "library_b")
        for directory, name in ((first, "bolt.stl"), (second, "nut.stl")):
            os.makedirs(directory)
            Path(directory, name).write_text("solid x\nendsolid x\n", encoding="utf-8")
        link = os.path.join(self.root, "library")
        os.symlink(first, link)
        self.settle(self.root, first, second)
        self.assertIn("library/bolt.stl", self.files())

        # A file added to the link's target, whose parent listing did not change.
        Path(first, "washer.stl").write_text("solid w\nendsolid w\n", encoding="utf-8")
        self.assertIn("library/washer.stl", self.files())

        os.unlink(link)
        os.symlink(second, link)
        files = self.files()
        self.assertIn("library/nut.stl", files)
        self.assertNotIn("library/bolt.stl", files)


class ReadsNeverBlockDeletion(FreshnessFixture):
    """A catalog read that has a model open must not stop the user deleting it.

    The catalog hashes every model, on a background thread, while the user is
    free to delete any of them. POSIX never lets a reader's handle
    refuse an unlink; Windows does, unless the reader asked for delete sharing,
    and a plain ``open()`` does not. On Windows these fail with ``WinError 32``
    the moment a hash goes back to a plain ``open``; off Windows they pin the
    scan's tolerance of a file that vanishes mid-read.
    """

    def delete_while_open(self, target, *, before_open: bool = False):
        """An opener that deletes ``target`` while (or just before) it is read."""
        def opener(path):
            if os.path.realpath(path) != os.path.realpath(target):
                return open_shared_for_read(path)
            if before_open:
                os.unlink(path)
                return open_shared_for_read(path)
            handle = open_shared_for_read(path)
            os.unlink(path)
            self.deleted.append(path)
            return handle
        self.deleted = []
        return opener

    def test_a_model_deleted_while_the_scan_hashes_it_is_deleted(self) -> None:
        model = self.write("gripper/probe.stl", "solid probe\nendsolid probe\n")
        with mock.patch.object(scanner, "open_shared_for_read", self.delete_while_open(model)):
            scan_cad_directory(self.root)
        self.assertEqual(self.deleted, [model])
        self.assertFalse(os.path.exists(model))
        self.assertNotIn("gripper/probe.stl", self.files())

    def test_a_model_gone_before_the_scan_opens_it_leaves_the_scan_standing(self) -> None:
        model = self.write("gripper/probe.stl", "solid probe\nendsolid probe\n")
        opener = self.delete_while_open(model, before_open=True)
        with mock.patch.object(scanner, "open_shared_for_read", opener):
            entries = scan_cad_directory(self.root)["entries"]
        probe = next(entry for entry in entries if entry["file"] == "gripper/probe.stl")
        self.assertEqual(probe["hash"], "")
        self.assertNotIn("gripper/probe.stl", self.files())

    def test_a_step_deleted_while_its_digest_is_read_is_deleted(self) -> None:
        document = self.write("gripper/part.step", "ISO-10303-21;\nEND-ISO-10303-21;\n")
        with mock.patch.object(catalog, "open_shared_for_read", self.delete_while_open(document)):
            catalog.artifact_file_hash(Path(document))
        self.assertEqual(len(self.deleted), 1)
        self.assertFalse(os.path.exists(document))


if __name__ == "__main__":
    unittest.main()
