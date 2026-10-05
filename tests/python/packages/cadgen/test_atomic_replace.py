"""Every artifact rename retries the Windows errors that are worth retrying.

A cached artifact is written to a temp file and renamed into place. On a Windows SMB share that
rename can lose to ``WinError 32`` -- the redirector still holds the handle Python just closed --
which under a parallel component build fails reliably (issue #241: 8 workers failed every time
on a NAS, one worker succeeded). PR #244 fixed the rename inside the GLB writer; this pins the
policy for all of them, because there are seven in a build's write path and hardening one moves
the failure to the next.

The second is a held DESTINATION: NTFS refuses a rename over a file another process has open with
``WinError 5``, which is how two builds of one model -- each reading back what it just published
-- failed a byte-identical save on the Windows runner.
"""

from __future__ import annotations

import os
import re
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support.paths import REPO_ROOT, add_repo_path

add_repo_path("packages/cadgen/src")

from cadgen._internal import atomic_replace

CADGEN_SRC = REPO_ROOT / "packages" / "cadgen" / "src" / "cadgen"


def sharing_violation() -> PermissionError:
    error = PermissionError(13, "file is being used by another process")
    error.winerror = atomic_replace.WINDOWS_SHARING_VIOLATION
    return error


def access_denied() -> PermissionError:
    error = PermissionError(13, "Access is denied")
    error.winerror = atomic_replace.WINDOWS_ACCESS_DENIED
    return error


class ReplaceAtomicTest(unittest.TestCase):
    def test_a_sharing_violation_is_retried_until_it_wins(self) -> None:
        attempts = []

        def flaky(source, target):
            attempts.append((source, target))
            if len(attempts) < 3:
                raise sharing_violation()

        with mock.patch.object(atomic_replace.os, "replace", side_effect=flaky), \
             mock.patch.object(atomic_replace.time, "sleep") as sleep:
            atomic_replace.replace_atomic("from.tmp", "to.glb")

        self.assertEqual(3, len(attempts))
        self.assertEqual(
            [(0.05,), (0.1,)],
            [call.args for call in sleep.call_args_list],
            "the backoff must grow, and must not sleep after the winning attempt",
        )


    def test_it_gives_up_rather_than_hanging(self) -> None:
        # A rename that cannot win inside the window is not a deferred close. Failing beats a
        # build that retries forever.
        error = sharing_violation()
        with mock.patch.object(atomic_replace.os, "replace", side_effect=error), \
             mock.patch.object(atomic_replace.time, "sleep") as sleep:
            with self.assertRaises(PermissionError) as raised:
                atomic_replace.replace_atomic("from.tmp", "to.glb")
        self.assertIs(error, raised.exception, "the original error must survive the retries")
        self.assertEqual(len(atomic_replace.RETRY_DELAYS_SECONDS), sleep.call_count)

    def test_every_other_error_surfaces_at_once(self) -> None:
        # "to.glb" does not exist: a denial with no file at the target is a real one.
        for winerror in (5, 2, None):
            error = PermissionError(13, "denied")
            if winerror is not None:
                error.winerror = winerror
            with self.subTest(winerror=winerror):
                with mock.patch.object(atomic_replace.os, "replace", side_effect=error), \
                     mock.patch.object(atomic_replace.time, "sleep") as sleep:
                    with self.assertRaises(PermissionError):
                        atomic_replace.replace_atomic("from.tmp", "to.glb")
                sleep.assert_not_called()

    def test_a_denial_onto_an_existing_file_is_a_held_destination_and_is_retried(self) -> None:
        """What NTFS answers a rename over a file another process has open.

        Two builds of one model publish the same record, entries and document, and each reads
        back what it wrote, so the loser of the race finds the winner's read open on its target.
        That ``5`` is a handle about to close, not a denial.
        """
        import tempfile

        with tempfile.TemporaryDirectory(prefix="cad-atomic-") as temp_dir:
            source = Path(temp_dir) / "record.tmp"
            source.write_bytes(b"new")
            target = Path(temp_dir) / "record"
            target.write_bytes(b"old")
            attempts = []
            real_replace = os.replace

            def held_twice(src, dst):
                attempts.append(src)
                if len(attempts) <= 2:
                    raise access_denied()
                real_replace(src, dst)

            with mock.patch.object(atomic_replace.os, "replace", side_effect=held_twice), \
                 mock.patch.object(atomic_replace.time, "sleep") as sleep:
                atomic_replace.replace_atomic(source, target)

            self.assertEqual(b"new", target.read_bytes())
            self.assertEqual(3, len(attempts))
            self.assertEqual([(0.05,), (0.1,)], [call.args for call in sleep.call_args_list])

    def test_a_denial_onto_a_directory_surfaces_at_once(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory(prefix="cad-atomic-") as temp_dir:
            target = Path(temp_dir) / "in-the-way"
            target.mkdir()
            error = access_denied()
            with mock.patch.object(atomic_replace.os, "replace", side_effect=error), \
                 mock.patch.object(atomic_replace.time, "sleep") as sleep:
                with self.assertRaises(PermissionError) as raised:
                    atomic_replace.replace_atomic(Path(temp_dir) / "from.tmp", target)
            self.assertIs(error, raised.exception)
            sleep.assert_not_called()

    def test_a_destination_held_past_both_ladders_reports_the_denial(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory(prefix="cad-atomic-") as temp_dir:
            source = Path(temp_dir) / "record.tmp"
            source.write_bytes(b"new")
            target = Path(temp_dir) / "record"
            target.write_bytes(b"old")
            error = access_denied()
            with mock.patch.object(atomic_replace.os, "replace", side_effect=error) as replace, \
                 mock.patch.object(atomic_replace.time, "sleep"):
                with self.assertRaises(PermissionError) as raised:
                    atomic_replace.replace_atomic(source, target)
            self.assertIs(error, raised.exception)
            self.assertEqual(2 * (len(atomic_replace.RETRY_DELAYS_SECONDS) + 1), replace.call_count)
            self.assertEqual(b"old", target.read_bytes())

    def test_an_exhausted_ladder_retries_from_a_copy_the_server_has_not_seen(self) -> None:
        """Issue #274 after 0.4.13, and the gate run on #283.

        The remeasured tail is long and thin (p99 265 ms, max 797 ms), so a bigger window only
        creeps. The violation is pinned to the handle the server holds on the temp file, and a
        copy carries no handle of its own.
        """
        import tempfile

        with tempfile.TemporaryDirectory(prefix="cad-atomic-") as temp_dir:
            source = Path(temp_dir) / "artifact.glb.tmp"
            source.write_bytes(b"glTF")
            target = Path(temp_dir) / "artifact.glb"
            seen = []
            real_replace = os.replace

            def blocked_until_a_new_file(src, dst):
                seen.append(Path(src).name)
                if len(seen) <= len(atomic_replace.RETRY_DELAYS_SECONDS) + 1:
                    raise sharing_violation()
                real_replace(src, dst)

            with mock.patch.object(atomic_replace.os, "replace",
                                   side_effect=blocked_until_a_new_file), \
                 mock.patch.object(atomic_replace.time, "sleep"):
                atomic_replace.replace_atomic(source, target)

            self.assertEqual(b"glTF", target.read_bytes())
            first_ladder = set(seen[: len(atomic_replace.RETRY_DELAYS_SECONDS) + 1])
            self.assertEqual(1, len(first_ladder), "the first ladder must reuse one file")
            self.assertNotIn(
                seen[-1], first_ladder,
                "the retry must use a file the server has never seen",
            )
            self.assertTrue(seen[-1].endswith(".tmp"), seen[-1] + " must stay gitignored")
            self.assertEqual([target.name], [q.name for q in Path(temp_dir).iterdir()])

    def test_the_copy_survives_a_pinned_source(self) -> None:
        """The rescue must not depend on deleting the file that blocked the rename.

        That delete hits the same handle, so requiring it would abort the retry in exactly the
        case it was written for.
        """
        import tempfile

        with tempfile.TemporaryDirectory(prefix="cad-atomic-") as temp_dir:
            source = Path(temp_dir) / "artifact.glb.tmp"
            source.write_bytes(b"glTF")
            target = Path(temp_dir) / "artifact.glb"
            seen = []
            real_replace = os.replace
            real_unlink = Path.unlink

            def blocked_until_a_new_file(src, dst):
                seen.append(Path(src).name)
                if len(seen) <= len(atomic_replace.RETRY_DELAYS_SECONDS) + 1:
                    raise sharing_violation()
                real_replace(src, dst)

            def pinned_unlink(self, missing_ok=False):
                if self.name == source.name:
                    raise sharing_violation()
                return real_unlink(self, missing_ok=missing_ok)

            with mock.patch.object(atomic_replace.os, "replace",
                                   side_effect=blocked_until_a_new_file), \
                 mock.patch.object(atomic_replace.time, "sleep"), \
                 mock.patch.object(Path, "unlink", pinned_unlink):
                atomic_replace.replace_atomic(source, target)

            self.assertEqual(b"glTF", target.read_bytes())

    def test_the_rescue_is_bounded_and_reports_the_rename_failure(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory(prefix="cad-atomic-") as temp_dir:
            source = Path(temp_dir) / "artifact.glb.tmp"
            source.write_bytes(b"glTF")
            target = Path(temp_dir) / "artifact.glb"
            error = sharing_violation()

            with mock.patch.object(atomic_replace.os, "replace", side_effect=error) as replace, \
                 mock.patch.object(atomic_replace.time, "sleep"):
                with self.assertRaises(PermissionError) as raised:
                    atomic_replace.replace_atomic(source, target)

            self.assertIs(error, raised.exception, "the original error must survive")
            self.assertEqual(
                2 * (len(atomic_replace.RETRY_DELAYS_SECONDS) + 1),
                replace.call_count,
                "two ladders, then give up -- a build that retries forever is worse",
            )
            # Both the copy and the original are cleaned up when the delete is permitted; only
            # a genuinely pinned file survives, which the case above covers.
            self.assertEqual(
                [], [q.name for q in Path(temp_dir).iterdir()],
                "the copy must not be left behind",
            )

    def test_a_source_that_cannot_be_copied_reports_the_rename_failure(self) -> None:
        error = sharing_violation()
        with mock.patch.object(atomic_replace.os, "replace", side_effect=error), \
             mock.patch.object(atomic_replace.time, "sleep"), \
             mock.patch.object(atomic_replace.shutil, "copyfile", side_effect=OSError("pinned")):
            with self.assertRaises(PermissionError) as raised:
                atomic_replace.replace_atomic("from.tmp", "to.glb")
        self.assertIs(error, raised.exception)


class WriteBytesAtomicTest(unittest.TestCase):
    def test_it_writes_through_a_temp_file_in_the_SAME_directory(self) -> None:
        # A temp file on another volume would turn the rename into a copy, which is not atomic.
        import tempfile

        with tempfile.TemporaryDirectory(prefix="cad-atomic-") as temp_dir:
            target = Path(temp_dir) / "nested" / "artifact.glb"
            seen = {}

            real_replace = os.replace

            def record(source, destination):
                seen["source_parent"] = Path(source).parent
                real_replace(source, destination)

            with mock.patch.object(atomic_replace.os, "replace", side_effect=record):
                atomic_replace.write_bytes_atomic(target, b"glTF")

            self.assertEqual(b"glTF", target.read_bytes())
            self.assertEqual(target.parent, seen["source_parent"])

    def test_the_temp_file_does_not_survive_a_failure(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory(prefix="cad-atomic-") as temp_dir:
            target = Path(temp_dir) / "artifact.glb"
            with mock.patch.object(atomic_replace.os, "replace", side_effect=OSError("nope")):
                with self.assertRaises(OSError):
                    atomic_replace.write_bytes_atomic(target, b"glTF")
            self.assertEqual([], list(Path(temp_dir).iterdir()), "a temp file was left behind")

    def test_a_pinned_temp_file_may_survive_rather_than_mask_the_failure(self) -> None:
        """Knowingly weaker than the case above, and the better half of the trade.

        On Windows the handle that refuses the rename refuses the delete too. Letting that
        escape replaces the rename failure with a cleanup error, and aborts the rescue in
        exactly the case it was written for. Today that case leaks the file AND fails the
        build, so both halves improve.
        """
        import tempfile

        with tempfile.TemporaryDirectory(prefix="cad-atomic-") as temp_dir:
            target = Path(temp_dir) / "artifact.glb"
            with mock.patch.object(atomic_replace.os, "replace", side_effect=sharing_violation()), \
                 mock.patch.object(atomic_replace.time, "sleep"), \
                 mock.patch.object(atomic_replace.shutil, "copyfile", side_effect=OSError("pinned")), \
                 mock.patch.object(Path, "unlink", side_effect=sharing_violation()):
                with self.assertRaises(PermissionError) as raised:
                    atomic_replace.write_bytes_atomic(target, b"glTF")
            self.assertEqual(
                atomic_replace.WINDOWS_SHARING_VIOLATION,
                raised.exception.winerror,
                "the rename failure must reach the caller, not the cleanup failure",
            )


class EveryRenameGoesThroughTheHelperTest(unittest.TestCase):
    """The point of the helper: one policy, not one per writer.

    Hardening a single rename is what left the reporter's next build to fail somewhere else, so
    a direct ``os.replace`` in cadgen is the regression this test exists to catch.
    """

    def test_no_cadgen_module_renames_directly(self) -> None:
        offenders = []
        for path in sorted(CADGEN_SRC.rglob("*.py")):
            if path.name == "atomic_replace.py" or "__pycache__" in path.parts:
                continue
            source = re.sub(r"#[^\n]*", "", path.read_text(encoding="utf-8"))
            if re.search(r"\bos\.replace\(|\.replace\(\s*target", source):
                offenders.append(str(path.relative_to(REPO_ROOT)))
        self.assertEqual(
            [],
            offenders,
            "use cadgen._internal.atomic_replace.replace_atomic: a bare os.replace loses to "
            "WinError 32 on an SMB share (issue #241)",
        )


class OpenWithLadderTest(unittest.TestCase):
    """Reopening a file we just wrote gets the same narrow wait the renames get.

    The STEP writer reopens its own output up to three times per export -- read
    it, rewrite the tail in place, hash it -- and on Windows each of those is
    refused while a deferred close or a scanner still holds the handle. Only
    WinError 32 waits; a denial or a missing file must surface at once, and off
    Windows this is plain open().
    """

    def setUp(self) -> None:
        import tempfile

        self._tmp = tempfile.TemporaryDirectory(prefix="cadgen-ladder-")
        self.addCleanup(self._tmp.cleanup)
        self.path = Path(self._tmp.name) / "payload.step"
        self.path.write_bytes(b"ISO-10303-21;\n")

    def test_a_clean_open_reads_the_file(self) -> None:
        with atomic_replace.open_with_ladder(self.path, "rb") as handle:
            self.assertEqual(b"ISO-10303-21;\n", handle.read())
        self.assertEqual(b"ISO-10303-21;\n", atomic_replace.read_bytes_with_ladder(self.path))

    def test_a_sharing_violation_is_waited_out_then_the_open_succeeds(self) -> None:
        real_open = Path.open
        attempts = []

        def flaky(self_path, mode, *args, **kwargs):
            attempts.append(mode)
            if len(attempts) <= 2:
                raise sharing_violation()
            return real_open(self_path, mode, *args, **kwargs)

        with mock.patch.object(Path, "open", flaky), mock.patch("time.sleep") as sleep:
            with atomic_replace.open_with_ladder(self.path, "rb") as handle:
                self.assertEqual(b"ISO-10303-21;\n", handle.read())
        self.assertEqual(3, len(attempts))
        self.assertEqual(list(atomic_replace.RETRY_DELAYS_SECONDS[:2]), [c.args[0] for c in sleep.call_args_list])

    def test_the_ladder_is_bounded_and_the_violation_propagates(self) -> None:
        with mock.patch.object(Path, "open", side_effect=sharing_violation()), mock.patch("time.sleep") as sleep:
            with self.assertRaises(PermissionError) as raised:
                atomic_replace.open_with_ladder(self.path, "rb")
        self.assertEqual(atomic_replace.WINDOWS_SHARING_VIOLATION, raised.exception.winerror)
        self.assertEqual(len(atomic_replace.RETRY_DELAYS_SECONDS), sleep.call_count)

    def test_any_other_error_surfaces_at_once(self) -> None:
        denied = PermissionError(13, "Access is denied")
        denied.winerror = 5
        with mock.patch.object(Path, "open", side_effect=denied), mock.patch("time.sleep") as sleep:
            with self.assertRaises(PermissionError) as raised:
                atomic_replace.open_with_ladder(self.path, "rb")
        self.assertEqual(5, raised.exception.winerror)
        self.assertEqual(0, sleep.call_count)

    def test_a_missing_file_is_not_retried(self) -> None:
        with mock.patch("time.sleep") as sleep:
            with self.assertRaises(FileNotFoundError):
                atomic_replace.open_with_ladder(self.path.with_name("absent.step"), "rb")
        self.assertEqual(0, sleep.call_count)

    def test_windows_reports_a_held_file_through_errno_alone_and_it_is_waited_out(self) -> None:
        """What Windows' open() really raises for a file a peer is renaming over:
        EACCES and no winerror. Two builds of one model, each reading back the
        .step the other was replacing, failed a save on the Windows runner so."""
        import errno

        real_open = Path.open
        attempts = []

        def held(self_path, mode, *args, **kwargs):
            attempts.append(mode)
            if len(attempts) <= 2:
                raise PermissionError(errno.EACCES, "Permission denied")
            return real_open(self_path, mode, *args, **kwargs)

        with mock.patch.object(atomic_replace, "_OPEN_REFUSAL_IS_ERRNO_ONLY", True), \
                mock.patch.object(Path, "open", held), mock.patch("time.sleep") as sleep:
            with atomic_replace.open_with_ladder(self.path, "rb") as handle:
                self.assertEqual(b"ISO-10303-21;\n", handle.read())
        self.assertEqual(3, len(attempts))
        self.assertEqual(2, sleep.call_count)

    def test_an_errno_denial_with_no_file_there_or_off_windows_surfaces_at_once(self) -> None:
        import errno

        denied = PermissionError(errno.EACCES, "Permission denied")
        for windows, path in ((True, self.path.with_name("absent.step")), (False, self.path)):
            with self.subTest(windows=windows), \
                    mock.patch.object(atomic_replace, "_OPEN_REFUSAL_IS_ERRNO_ONLY", windows), \
                    mock.patch.object(Path, "open", side_effect=denied), mock.patch("time.sleep") as sleep:
                with self.assertRaises(PermissionError):
                    atomic_replace.open_with_ladder(path, "rb")
                self.assertEqual(0, sleep.call_count)

    def test_every_step_writer_reopen_goes_through_the_ladder(self) -> None:
        """The rule the atomic_replace docstring states: harden one and the
        failure moves to the next. Pins that no reopen of the written STEP was
        left on a bare open()."""
        for relative in ("cadgen/step_export.py", "cadgen/_internal/step_hash.py"):
            bare = _bare_reads(relative)
            self.assertEqual([], bare, f"{relative} reopens its output without the ladder: {bare}")

    def test_every_read_of_an_imported_document_goes_through_the_ladder(self) -> None:
        """#529: importing a STEP on Windows failed with "[Errno 13] Permission
        denied" while another program held or replaced it -- the refusal the
        ladder waits out for cadgen's own STEPs. Pins that the import's reads of
        the document (the closure hash before the job, the scene loads in it)
        are not left on a bare read."""
        for relative in ("cadgen/_internal/step_scene_package.py", "cadgen/daemon/executors.py"):
            bare = _bare_reads(relative)
            self.assertEqual([], bare, f"{relative} reads a document without the ladder: {bare}")


def _bare_reads(relative: str) -> list[str]:
    """Reads and reopens in a cadgen module that are not on a ladder line."""
    import re as _re

    source = (REPO_ROOT / "packages" / "cadgen" / "src" / relative).read_text(encoding="utf-8")
    body = source.split('"""', 2)[-1] if source.count('"""') >= 2 else source
    return _re.findall(r"^(?!.*ladder).*\b(?:read_bytes\(\)|write_bytes\(|\.open\(\s*[\"']r)", body, _re.M)


if __name__ == "__main__":
    unittest.main()
