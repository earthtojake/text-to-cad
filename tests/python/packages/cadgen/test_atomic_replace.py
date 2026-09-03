"""Every artifact rename retries the one Windows error that is worth retrying.

A cached artifact is written to a temp file and renamed into place. On a Windows SMB share that
rename can lose to ``WinError 32`` -- the redirector still holds the handle Python just closed --
which under a parallel component build fails reliably (issue #241: 8 workers failed every time
on a NAS, one worker succeeded). PR #244 fixed the rename inside the GLB writer; this pins the
policy for all of them, because there are seven in a build's write path and hardening one moves
the failure to the next.
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

    def test_the_window_covers_the_measured_tail_not_the_median(self) -> None:
        """Issue #274, and the reason this number is not free to shrink.

        Measured on a Synology SMB share over two 84-component builds: 126 of 168 renames
        blocked at all, median 31 ms, p90 118 ms, max 389 ms. The budget is spent per rename
        but the BUILD only succeeds if every one of them wins, so the window has to clear the
        tail rather than the middle -- at 168 draws, a 1% per-rename loss rate is roughly a
        1-in-5 chance of a clean build.
        """
        self.assertGreater(
            sum(atomic_replace.RETRY_DELAYS_SECONDS),
            0.389,
            "the retry window must outlast the longest rename actually measured on SMB",
        )
        # ...and the first retry still has to be short, or the median rename pays for the tail.
        self.assertLessEqual(atomic_replace.RETRY_DELAYS_SECONDS[0], 0.05)

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

    def test_temp_suffix_is_unique_without_a_clock(self) -> None:
        # Two calls inside one clock tick must still differ: the rescue's premise is a name the
        # server has never seen, which must not rest on timer resolution.
        with mock.patch.object(atomic_replace.time, "time_ns", return_value=1):
            suffixes = {atomic_replace.temp_suffix() for _ in range(200)}
        self.assertEqual(200, len(suffixes))
        self.assertTrue(all(suffix.endswith(".tmp") for suffix in suffixes))

    def test_the_happy_path_does_not_sleep(self) -> None:
        with mock.patch.object(atomic_replace.os, "replace") as replace, \
             mock.patch.object(atomic_replace.time, "sleep") as sleep:
            atomic_replace.replace_atomic("from.tmp", "to.glb")
        replace.assert_called_once_with("from.tmp", "to.glb")
        sleep.assert_not_called()


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

    def test_every_step_writer_reopen_goes_through_the_ladder(self) -> None:
        """The rule the atomic_replace docstring states: harden one and the
        failure moves to the next. Pins that no reopen of the written STEP was
        left on a bare open()."""
        import re as _re

        for relative in ("cadgen/step_export.py", "cadgen/_internal/step_hash.py"):
            source = (REPO_ROOT / "packages" / "cadgen" / "src" / relative).read_text(encoding="utf-8")
            body = source.split('"""', 2)[-1] if source.count('"""') >= 2 else source
            bare = _re.findall(r"^(?!.*ladder).*\b(?:read_bytes\(\)|write_bytes\(|\.open\(\s*[\"']r)", body, _re.M)
            self.assertEqual([], bare, f"{relative} reopens its output without the ladder: {bare}")


if __name__ == "__main__":
    unittest.main()
