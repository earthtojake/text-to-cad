"""The engine's rename waits out a Windows handle about to close and nothing else, as cadgen's
own does (``tests/python/packages/cadgen/test_atomic_replace.py`` holds that policy)."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from cadgen.engine import atomic_replace


def refusal(winerror: int) -> PermissionError:
    error = PermissionError(13, "refused")
    error.winerror = winerror
    return error


class ReplaceAtomicTest(unittest.TestCase):
    def setUp(self) -> None:
        folder = tempfile.TemporaryDirectory(prefix="cadgen-engine-rename-")
        self.addCleanup(folder.cleanup)
        self.folder = Path(folder.name)
        self.source = self.folder / ".part.tmp.xbf"
        self.source.write_bytes(b"new")
        self.target = self.folder / "part.xbf"

    def test_a_sharing_violation_is_waited_out(self) -> None:
        real, attempts = os.replace, []

        def flaky(source, target):
            attempts.append(source)
            if len(attempts) < 3:
                raise refusal(atomic_replace.WINDOWS_SHARING_VIOLATION)
            real(source, target)

        with mock.patch.object(atomic_replace.os, "replace", side_effect=flaky), \
                mock.patch.object(atomic_replace.time, "sleep") as sleep:
            atomic_replace.replace_atomic(self.source, self.target)
        self.assertEqual(b"new", self.target.read_bytes())
        self.assertEqual([(0.05,), (0.1,)], [call.args for call in sleep.call_args_list])

    def test_a_held_destination_is_waited_out_and_a_denial_with_no_file_there_is_not(self) -> None:
        real, attempts = os.replace, []

        def held_once(source, target):
            attempts.append(source)
            if len(attempts) < 2:
                raise refusal(atomic_replace.WINDOWS_ACCESS_DENIED)
            real(source, target)

        self.target.write_bytes(b"old")
        with mock.patch.object(atomic_replace.os, "replace", side_effect=held_once), \
                mock.patch.object(atomic_replace.time, "sleep"):
            atomic_replace.replace_atomic(self.source, self.target)
        self.assertEqual(b"new", self.target.read_bytes())

        error = refusal(atomic_replace.WINDOWS_ACCESS_DENIED)
        with mock.patch.object(atomic_replace.os, "replace", side_effect=error), \
                mock.patch.object(atomic_replace.time, "sleep") as sleep:
            with self.assertRaises(PermissionError):
                atomic_replace.replace_atomic(self.folder / "absent.tmp", self.folder / "absent")
        sleep.assert_not_called()

    def test_an_exhausted_ladder_retries_from_a_fresh_copy_then_gives_up(self) -> None:
        real, seen = os.replace, []

        def blocked_until_a_new_file(source, target):
            seen.append(Path(source).name)
            if Path(source) == self.source:
                raise refusal(atomic_replace.WINDOWS_SHARING_VIOLATION)
            real(source, target)

        with mock.patch.object(atomic_replace.os, "replace", side_effect=blocked_until_a_new_file), \
                mock.patch.object(atomic_replace.time, "sleep"):
            atomic_replace.replace_atomic(self.source, self.target)
        self.assertEqual(b"new", self.target.read_bytes())
        self.assertNotEqual(self.source.name, seen[-1])
        self.assertEqual([self.target.name], [entry.name for entry in self.folder.iterdir()])

        self.source.write_bytes(b"newer")
        error = refusal(atomic_replace.WINDOWS_SHARING_VIOLATION)
        with mock.patch.object(atomic_replace.os, "replace", side_effect=error) as replace, \
                mock.patch.object(atomic_replace.time, "sleep"):
            with self.assertRaises(PermissionError) as raised:
                atomic_replace.replace_atomic(self.source, self.target)
        self.assertIs(error, raised.exception)
        self.assertEqual(2 * (len(atomic_replace.RETRY_DELAYS_SECONDS) + 1), replace.call_count)


if __name__ == "__main__":
    unittest.main()


class StagingTest(unittest.TestCase):
    """Every engine writer stages its file in a folder made beside the target for it alone: a
    name no one knows first, closed to others, so a link or file someone else left in the target's
    folder is never written through or moved into place."""

    def setUp(self) -> None:
        folder = tempfile.TemporaryDirectory(prefix="cadgen-engine-staging-")
        self.addCleanup(folder.cleanup)
        self.folder = Path(folder.name)

    def test_a_stage_is_in_a_private_folder_of_its_own_that_goes_with_the_block(self) -> None:
        target = self.folder / "part.glb"
        with atomic_replace.staging(target) as stage:
            self.assertEqual(stage.name, target.name)
            self.assertEqual(stage.parent.parent, self.folder)
            self.assertTrue(stage.parent.name.startswith(".part.") and stage.parent.name.endswith(".tmp"))
            if os.name != "nt":
                self.assertEqual(stage.parent.stat().st_mode & 0o077, 0)
            stage.write_bytes(b"glTF")
            atomic_replace.replace_atomic(stage, target)
        self.assertEqual(target.read_bytes(), b"glTF")
        self.assertEqual(sorted(path.name for path in self.folder.iterdir()), ["part.glb"])

    @unittest.skipIf(os.name == "nt", "a symbolic link another user leaves is a POSIX folder's")
    def test_writers_never_write_through_or_move_a_link_left_at_a_predictable_name(self) -> None:
        import threading

        from cadgen.engine import snapshot
        from cadgen.engine.export import dxf

        kept = self.folder / "kept.txt"
        kept.write_text("MARKER", encoding="utf-8")
        planted = []
        for name in (f".view.{os.getpid()}.tmp.png", f".plan.{os.getpid()}.{threading.get_ident()}.tmp.dxf"):
            link = self.folder / name
            link.symlink_to(kept)
            planted.append(link)
        snapshot.write_png(self.folder / "view.png", b"\x89PNG\r\n\x1a\nfixture")
        with mock.patch.object(dxf, "dxf_bytes", return_value=b"0\nEOF\n"):
            dxf.write(object(), self.folder / "plan.dxf")
        self.assertEqual(kept.read_text(encoding="utf-8"), "MARKER")
        self.assertTrue(all(link.is_symlink() for link in planted))
        self.assertEqual((self.folder / "view.png").read_bytes(), b"\x89PNG\r\n\x1a\nfixture")
        self.assertFalse((self.folder / "view.png").is_symlink())
        self.assertEqual((self.folder / "plan.dxf").read_bytes(), b"0\nEOF\n")
