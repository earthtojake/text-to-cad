"""Mutual-exclusion tests for the per-model generation lock.

The lock guards a render package against two builders writing it at once, so the
tests that matter drive REAL concurrency (separate processes, separate threads,
SIGKILL) rather than asserting on a status payload. The previous JSON+heartbeat
scheme passed unit tests while failing every one of these.
"""

from __future__ import annotations

import errno
import os
import subprocess
import sys
import tempfile
import textwrap
import threading
import time
import unittest
import warnings
from pathlib import Path
from unittest import mock

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")

from cadgen.coordination.lock import exclusive  # noqa: E402
from cadgen.coordination.paths import WRITE_LOCK_SUFFIX, write_lock_path  # noqa: E402

import cadgen.coordination.lock as lock  # noqa: E402

# Each child takes the lock, marks entry, holds briefly, marks exit, releases.
# If mutual exclusion holds, the marks can never interleave.
_CONTENDER = """
import sys, time
sys.path.insert(0, {src!r})
from cadgen.coordination.lock import exclusive
lock, log, tag = sys.argv[1], sys.argv[2], sys.argv[3]
with exclusive(lock):
    with open(log, "a") as handle:
        handle.write("S" + tag)
        handle.flush()
    time.sleep(0.20)
    with open(log, "a") as handle:
        handle.write("E" + tag)
        handle.flush()
"""

_CADGEN_SRC = str(Path(__file__).resolve().parents[4] / "packages" / "cadgen" / "src")


class GenerationLockPathTest(unittest.TestCase):
    def test_lock_is_a_hidden_sibling_of_the_package_dir(self):
        package = Path("/models/robot/__cadgen__/models/arm.step.py")
        self.assertEqual(
            Path("/models/robot/__cadgen__/models/.arm.step.py.generation.lock"),
            write_lock_path(package),
        )

    def test_sentinel_carries_the_holders_run_id(self):
        """The sentinel is not a status file -- the KERNEL owns liveness -- but it does
        carry the holder's run id, which is what lets a reader tell whether the status
        record on disk belongs to the run that is actually running."""
        from cadgen.coordination.lock import read_run_id

        self.assertEqual(".generation.lock", WRITE_LOCK_SUFFIX)
        with tempfile.TemporaryDirectory() as tmp:
            lock = write_lock_path(Path(tmp) / "__cadgen__" / "models" / "part.step.py")
            with exclusive(lock) as run_id:
                self.assertTrue(run_id)
                self.assertEqual(run_id, read_run_id(lock))

    def test_distinct_models_get_distinct_locks(self):
        base = Path("/m/__cadgen__/models")
        self.assertNotEqual(
            write_lock_path(base / "a.step.py"), write_lock_path(base / "b.step.py")
        )


class GenerationLockBehaviourTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.lock = write_lock_path(self.root / "__cadgen__" / "models" / "part.step.py")

    def test_none_lock_path_is_a_noop(self):
        with exclusive(None):
            pass

    def test_lock_file_survives_release(self):
        """The sentinel must NOT be unlinked: a waiter holding a descriptor to an
        unlinked inode would 'acquire' a lock no other process can see."""
        with exclusive(self.lock):
            pass
        self.assertTrue(self.lock.is_file())

    def test_exception_inside_the_block_still_releases(self):
        with self.assertRaises(RuntimeError):
            with exclusive(self.lock):
                raise RuntimeError("build blew up")
        # A fresh acquire must not block.
        done = threading.Event()
        threading.Thread(target=lambda: (self._acquire_release(), done.set()), daemon=True).start()
        self.assertTrue(done.wait(10), "lock was not released after an exception")

    def _acquire_release(self):
        with exclusive(self.lock):
            pass

    def test_nested_same_model_in_one_thread_does_not_deadlock(self):
        """A parent build that triggers a child build of the same model in-process
        must not block on its own lock (flock is per-descriptor)."""
        done = threading.Event()

        def run():
            with exclusive(self.lock):
                with exclusive(self.lock):
                    pass
            done.set()

        threading.Thread(target=run, daemon=True).start()
        self.assertTrue(done.wait(10), "nested acquire of the same model deadlocked")

    def test_different_models_do_not_contend(self):
        other = write_lock_path(self.root / "__cadgen__" / "models" / "other.step.py")
        done = threading.Event()

        def run():
            with exclusive(other):
                done.set()
                time.sleep(0.05)

        thread = threading.Thread(target=run, daemon=True)
        with exclusive(self.lock):
            thread.start()
            self.assertTrue(done.wait(10), "an unrelated model blocked on this one's lock")
        # Join before the temp dir is removed. The thread is still inside exclusive() with
        # the sentinel open when the assertion passes, and on Windows a file cannot be
        # unlinked while a handle is open -- so leaving it running failed the CLEANUP, not
        # the test. POSIX unlinks open files happily, which is why this never showed here.
        thread.join(10)
        self.assertFalse(thread.is_alive(), "the unrelated model's lock was never released")

    def test_threads_in_one_process_serialize(self):
        order = []
        gate = threading.Lock()

        def run(tag):
            with exclusive(self.lock):
                with gate:
                    order.append("S" + tag)
                time.sleep(0.05)
                with gate:
                    order.append("E" + tag)

        threads = [threading.Thread(target=run, args=(str(i),)) for i in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)
            self.assertFalse(thread.is_alive(), "a contending thread never finished")
        self._assert_no_interleaving("".join(order))

    def test_processes_serialize(self):
        log = self.root / "order.log"
        script = _CONTENDER.format(src=_CADGEN_SRC)
        procs = [
            subprocess.Popen([sys.executable, "-c", script, str(self.lock), str(log), str(i)])
            for i in range(4)
        ]
        for proc in procs:
            self.assertEqual(0, proc.wait(timeout=60), "a contending build process failed")
        self._assert_no_interleaving(log.read_text())

    def test_killed_holder_releases_the_lock(self):
        ready = self.root / "ready"
        script = textwrap.dedent(
            f"""
            import sys, time
            sys.path.insert(0, {_CADGEN_SRC!r})
            from cadgen.coordination.lock import exclusive
            with exclusive({str(self.lock)!r}):
                open({str(ready)!r}, "wb").close()
                time.sleep(120)
            """
        )
        proc = subprocess.Popen([sys.executable, "-c", script])
        try:
            for _ in range(500):
                if ready.exists():
                    break
                time.sleep(0.02)
            self.assertTrue(ready.exists(), "helper never acquired the lock")
            proc.kill()
            proc.wait(timeout=30)
        finally:
            if proc.poll() is None:
                proc.kill()
        # No heartbeat window to wait out — the kernel released it at process death.
        done = threading.Event()
        threading.Thread(target=lambda: (self._acquire_release(), done.set()), daemon=True).start()
        self.assertTrue(done.wait(15), "a SIGKILLed builder left a stale lock")

    @unittest.skipIf(
        os.name == "nt",
        "chmod only toggles the read-only bit on Windows and does not stop a directory "
        "being written, so this would pass without ever reaching the degradation it claims "
        "to cover. Making a directory truly unwritable there needs an ACL edit.",
    )
    def test_unwritable_lock_directory_does_not_fail_the_build(self):
        blocked = self.root / "ro"
        blocked.mkdir()
        lock = blocked / "sub" / ".part.step.py.generation.lock"
        os.chmod(blocked, 0o500)
        self.addCleanup(os.chmod, blocked, 0o700)
        ran = []
        with exclusive(lock):
            ran.append(True)
        self.assertEqual([True], ran, "an unwritable package dir must not fail the build")

    def test_skip_if_current_is_evaluated_under_the_lock(self):
        """The pre-lock fast path cannot see a peer that started after it ran, so the
        currency check is repeated once the lock is held."""
        from cadgen._internal.generation import (
            _SkippedGeneration,
            _run_with_spec_generation_status,
        )

        calls = []
        result = _run_with_spec_generation_status(
            None,
            "unknown-generator",  # no package -> no-op lock, still exercises the ordering
            lambda spec, run: calls.append("built"),
            skip_if_current=lambda spec: True,
        )
        self.assertIsInstance(result, _SkippedGeneration)
        self.assertEqual([], calls, "action ran despite the package already being current")

    def test_skip_if_current_false_still_builds(self):
        from cadgen._internal.generation import _run_with_spec_generation_status

        calls = []
        _run_with_spec_generation_status(
            None,
            "unknown-generator",
            lambda spec, run: calls.append("built"),
            skip_if_current=lambda spec: False,
        )
        self.assertEqual(["built"], calls)

    def test_skip_if_current_is_evaluated_while_the_lock_is_actually_held(self):
        """The two tests above pass "unknown-generator", which resolves to NO output dir
        and therefore no lock at all -- they pin call ordering, not mutual exclusion. This
        one asserts the currency check really does run inside the critical section, by
        probing the sentinel from a second descriptor while the check is executing.

        Probes through ``lock.probe`` rather than raw ``fcntl``: it asks the same question
        through whichever backend is compiled in, and a bare ``import fcntl`` here is an
        ImportError on Windows -- where this assertion is worth more, not less."""
        from cadgen.coordination import STEP_PACKAGE, artifact_build
        from cadgen.coordination.paths import write_lock_path

        package = self.root / "__cadgen__" / "models" / "part.step.py"
        lock_path = write_lock_path(package)
        observed = []

        def _is_current():
            observed.append("locked" if lock.probe(lock_path).held else "UNLOCKED")
            return True

        with artifact_build(STEP_PACKAGE, package, is_current=_is_current) as run:
            self.assertTrue(run.skipped)
        self.assertEqual(["locked"], observed, "the currency check ran outside the lock")

    def _assert_no_interleaving(self, marks: str, contenders: int = 4) -> None:
        # Each contender contributes "S<tag>" + "E<tag>" = 4 characters.
        self.assertEqual(
            contenders * 4, len(marks), f"expected {contenders} paired enter/exit marks, got {marks!r}"
        )
        for index in range(0, len(marks), 4):
            enter, tag, leave, leave_tag = marks[index : index + 4]
            self.assertEqual("S", enter, f"interleaved critical sections: {marks!r}")
            self.assertEqual("E", leave, f"interleaved critical sections: {marks!r}")
            self.assertEqual(tag, leave_tag, f"interleaved critical sections: {marks!r}")


class RealBackendRegressionTests(unittest.TestCase):
    """Field regressions, asserted against the REAL backend of whatever platform runs them.

    Everything in ``WindowsLockBackendTests`` drives a fake, because ``msvcrt`` is not
    importable on the CI box that has always run these. A fake cannot reproduce either of the
    two bugs Windows users actually hit -- a backend that silently is not there, and a lock
    that makes its own file unreadable -- so these assert the invariants directly and are
    worth exactly what the platform running them is worth. On POSIX they pass trivially; on a
    Windows runner they are the regression tests for #260 and #269.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.lock = write_lock_path(self.root / "__cadgen__" / "models" / "part.step.py")

    def test_this_platform_really_has_a_locking_backend(self):
        """#260: before it, Windows had no ``fcntl``, took no lock, and said nothing.

        Every build proceeded unserialized and the degradation was invisible -- `exclusive()`
        is designed to yield None rather than fail, which is right for a filesystem that
        cannot lock and wrong as a description of the whole platform. Any OS the tests run on
        is an OS someone builds on, so a missing backend is a bug there, not a degradation.
        """
        self.assertTrue(
            lock.locking_available(),
            f"no locking backend on {os.name}: builds here are not serialized at all",
        )
        with exclusive(self.lock) as run_id:
            self.assertTrue(run_id, "a real backend must record a run id, not degrade to None")

    def test_another_process_can_read_the_sentinel_while_the_lock_is_held(self):
        """#269: Windows byte-range locks are MANDATORY, POSIX ``flock`` is advisory.

        Locking byte 0 of the sentinel made it unreadable to every other process for the whole
        build. The Node builders read it to prove they were started by the holder, and Python's
        own ``read_run_id`` reads it to attribute progress -- both precisely while a lock is
        held. So the sentinel must stay readable FROM ANOTHER PROCESS, which is the only place
        the distinction shows up: the holder can always read its own locked region.
        """
        ready = self.root / "ready"
        script = textwrap.dedent(
            f"""
            import sys, time
            sys.path.insert(0, {_CADGEN_SRC!r})
            from cadgen.coordination.lock import exclusive
            with exclusive({str(self.lock)!r}):
                open({str(ready)!r}, "wb").close()
                time.sleep(120)
            """
        )
        proc = subprocess.Popen([sys.executable, "-c", script])
        try:
            for _ in range(500):
                if ready.exists():
                    break
                time.sleep(0.02)
            self.assertTrue(ready.exists(), "helper never acquired the lock")

            # The lock really is held, so this is not "readable because nothing ran".
            self.assertTrue(lock.probe(self.lock).held, "the helper is not holding the lock")

            # What the Node builders do (a whole-file read), and what read_run_id does.
            raw = self.lock.read_bytes()[:32].decode("ascii").strip()
            self.assertEqual(32, len(raw), f"sentinel unreadable or unstamped: {raw!r}")
            self.assertEqual(raw, lock.read_run_id(self.lock))
        finally:
            proc.kill()
            proc.wait(timeout=30)


# The errno the real CRT reports for a region another handle holds. Taken from the module
# under test on purpose: if the backend ever stops treating this value as contention, these
# tests must move with it rather than quietly keep testing a value nothing produces.
WINDOWS_LOCK_CONTENTION_ERRNO = lock.WINDOWS_LOCK_CONTENTION_ERRNO


class _FakeMsvcrt:
    """In-process stand-in for ``msvcrt.locking``: a 1-byte region lock keyed by file
    identity (dev+inode), non-blocking acquire raising the CONTENTION errno when another
    handle holds the region -- the exact contract the Windows backend relies on.

    That errno used to be EACCES here, and EACCES is what made this fake useless for the one
    thing it exists to catch. The real ``_locking`` reports contention as EDEADLOCK, which was
    missing from the backend's busy set, so on Windows the loser of a race fell through to the
    degradation branch and ran with no lock at all. Every test passed, because the fake was
    faithful to everything except the errno that decides which branch is taken."""

    LK_NBLCK = 1
    LK_UNLCK = 2
    LK_LOCK = 3

    def __init__(self) -> None:
        self._held: set[tuple[int, int]] = set()

    def locking(self, fd, mode, nbytes: int = 1) -> None:
        info = os.fstat(fd)
        key = (info.st_dev, info.st_ino)
        if mode == self.LK_NBLCK:
            if key in self._held:
                raise OSError(WINDOWS_LOCK_CONTENTION_ERRNO, "Resource deadlock avoided")
            self._held.add(key)
        elif mode == self.LK_UNLCK:
            self._held.discard(key)
        else:
            raise AssertionError(f"unexpected msvcrt mode {mode}")


class DegradationIsAnnouncedTest(unittest.TestCase):
    """Degrading to no lock must never be silent again.

    The Windows contention errno was missing from the busy set, so a contended acquire fell
    through to the degradation branch and the build ran unserialized. Nothing said so -- not a
    log line, not a warning -- which is why it presented as "the lock does not work on Windows"
    with no way to tell that from "the lock was never taken". The errno in the message is the
    difference between those two, and it is what makes the next unrecognised one self-naming.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.lock_path = write_lock_path(Path(self._tmp.name) / "__cadgen__" / "models" / "p.step.py")

    def test_an_unrecognised_lock_error_warns_and_names_the_errno(self):
        def refuse(handle, path, **kwargs):
            raise OSError(errno.ENOLCK, "no locks available")

        with mock.patch.object(lock, "_acquire", refuse):
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                with exclusive(self.lock_path) as run_id:
                    self.assertIsNone(run_id, "a degraded acquire yields no run id")
        messages = [str(w.message) for w in caught if issubclass(w.category, RuntimeWarning)]
        self.assertTrue(messages, "degrading to no mutual exclusion said nothing")
        self.assertIn("ENOLCK", messages[0], "the warning must name the errno")
        self.assertIn("not serialized", messages[0])

    def test_a_successful_acquire_is_quiet(self):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            with exclusive(self.lock_path) as run_id:
                self.assertTrue(run_id)
        self.assertEqual([], [w for w in caught if issubclass(w.category, RuntimeWarning)])


class WindowsLockBackendTests(unittest.TestCase):
    """The Windows backend is not importable here, so it is driven with a faithful fake:
    ``fcntl=None`` + a fake ``msvcrt``. These pin the backend contract -- region locking, no
    shared mode, the sibling mutex that keeps the sentinel readable, waiting semantics --
    which is exactly what the two production modules diverge on."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.lock_path = write_lock_path(self.root / "__cadgen__" / "models" / "part.step.py")
        self._fcntl = mock.patch.object(lock, "fcntl", None)
        self._msvcrt = mock.patch.object(lock, "msvcrt", _FakeMsvcrt())
        self._fcntl.start()
        self._msvcrt.start()
        self.addCleanup(self._msvcrt.stop)
        self.addCleanup(self._fcntl.stop)

    @staticmethod
    def _inode_key(path: Path) -> tuple[int, int]:
        """The key _FakeMsvcrt uses: file identity, so a lock is attributable to a path."""
        info = os.stat(path)
        return (info.st_dev, info.st_ino)

    def test_locking_available_with_windows_backend(self) -> None:
        self.assertTrue(lock.locking_available())
        # A missing sentinel means no run has ever held it: idle, not degraded.
        self.assertEqual((False, False), lock.probe(self.lock_path))

    def test_probe_reports_free_without_a_holder(self) -> None:
        with exclusive(self.lock_path):
            pass
        result = lock.probe(self.lock_path)
        self.assertEqual((False, False), result)

    def test_probe_reports_held_while_a_peer_holds(self) -> None:
        done = threading.Event()
        release = threading.Event()

        def hold():
            with exclusive(self.lock_path):
                done.set()
                release.wait(10)

        thread = threading.Thread(target=hold, daemon=True)
        thread.start()
        self.assertTrue(done.wait(10), "holder never acquired")
        try:
            result = lock.probe(self.lock_path)
            self.assertEqual((True, False), result)
        finally:
            release.set()
            thread.join(10)

    def test_an_empty_mutex_reads_as_idle(self) -> None:
        # A 0-byte file cannot carry a Windows region lock at all. The MUTEX is padded before
        # the lock is taken, so 0 bytes means no run ever held it -- idle, and specifically not
        # a state that wedges future builds. (The old rule had to say "unknown" here, because
        # the lock lived on the sentinel and a crash before stamping left it legitimately empty.)
        mutex = lock.mutex_path(self.lock_path)
        mutex.parent.mkdir(parents=True, exist_ok=True)
        mutex.write_bytes(b"")
        self.assertEqual((False, False), lock.probe(self.lock_path))

    def test_nothing_locks_the_file_the_builders_read(self) -> None:
        """Issue #269: Windows byte-range locks are MANDATORY.

        Locking byte 0 of the sentinel made it unreadable to every other process for the whole
        build -- the Node child's readFileSync got EBUSY, its catch turned that into an empty
        string, and the run-id comparison failed against a sentinel holding exactly the right
        run id. Python's own read_run_id broke the same way.

        Mandatory locking cannot be emulated on POSIX: the fake tracks which files are locked,
        it cannot make a real read fail. So this asserts the INVARIANT that prevents the bug --
        the sentinel is never among the locked files -- by checking the fake's own ledger
        against both inodes, rather than pretending a successful read here proves anything.
        """
        holding = threading.Event()
        release = threading.Event()
        observed = {}

        def hold():
            with exclusive(self.lock_path) as run_id:
                observed["run_id"] = run_id
                holding.set()
                release.wait(10)

        thread = threading.Thread(target=hold, daemon=True)
        thread.start()
        self.assertTrue(holding.wait(10), "holder never acquired")
        try:
            sentinel_key = self._inode_key(self.lock_path)
            mutex_key = self._inode_key(lock.mutex_path(self.lock_path))
            locked = set(lock.msvcrt._held)
            self.assertIn(mutex_key, locked, "the mutex must be the locked file")
            self.assertNotIn(sentinel_key, locked, "the sentinel must never be locked")
            # And the stamp is there to be read, from both readers that need it.
            self.assertEqual(observed["run_id"], lock.read_run_id(self.lock_path))
            self.assertEqual(observed["run_id"], self.lock_path.read_bytes()[:32].decode().strip())
            # The lock really is held -- so this is not "unlocked because nothing ran".
            self.assertEqual((True, False), lock.probe(self.lock_path))
        finally:
            release.set()
            thread.join(10)

    def test_the_lock_is_taken_on_a_sibling_mutex_not_the_sentinel(self) -> None:
        mutex = lock.mutex_path(self.lock_path)
        self.assertNotEqual(mutex, self.lock_path)
        self.assertEqual(f"{self.lock_path.name}.mutex", mutex.name)
        with exclusive(self.lock_path):
            self.assertTrue(mutex.is_file(), "the mutex must exist while held")
        # The run id lives in the sentinel; the mutex carries no run id at all.
        self.assertTrue(self.lock_path.is_file())
        self.assertNotIn(
            (lock.read_run_id(self.lock_path) or ""),
            mutex.read_bytes().decode("ascii", "ignore"),
        )

    def test_run_id_is_still_stamped(self) -> None:
        from cadgen.coordination.lock import read_run_id

        with exclusive(self.lock_path) as run_id:
            self.assertTrue(run_id)
            self.assertEqual(run_id, read_run_id(self.lock_path))

    def test_waiting_acquire_waits_for_the_peer(self) -> None:
        release = threading.Event()
        acquired_second = threading.Event()

        def hold():
            with exclusive(self.lock_path):
                release.wait(10)

        def wait_then_acquire():
            with exclusive(self.lock_path):
                acquired_second.set()

        thread = threading.Thread(target=hold, daemon=True)
        thread.start()
        for _ in range(500):
            if lock.probe(self.lock_path).held:
                break
            time.sleep(0.01)
        second = threading.Thread(target=wait_then_acquire, daemon=True)
        second.start()
        time.sleep(0.1)
        self.assertFalse(acquired_second.is_set(), "second acquirer did not wait for the peer")
        release.set()
        self.assertTrue(acquired_second.wait(10), "second acquirer never got the lock")
        thread.join(10)
        second.join(10)

    def test_bounded_wait_raises_contended(self) -> None:
        from cadgen.coordination.lock import Contended

        done = threading.Event()
        release = threading.Event()

        def hold():
            with exclusive(self.lock_path):
                done.set()
                release.wait(10)

        thread = threading.Thread(target=hold, daemon=True)
        thread.start()
        self.assertTrue(done.wait(10))
        try:
            with self.assertRaises(Contended):
                with exclusive(self.lock_path, deadline_ms=100):
                    pass
        finally:
            release.set()
            thread.join(10)


class NoLockingBackendTests(unittest.TestCase):
    """Neither backend available: coordination is a transparent no-op everywhere."""

    def setUp(self) -> None:
        self._fcntl = mock.patch.object(lock, "fcntl", None)
        self._msvcrt = mock.patch.object(lock, "msvcrt", None)
        self._fcntl.start()
        self._msvcrt.start()
        self.addCleanup(self._msvcrt.stop)
        self.addCleanup(self._fcntl.stop)

    def test_probe_is_degraded_not_held(self) -> None:
        from cadgen.coordination.lock import ProbeResult

        result = lock.probe("/nonexistent/.lock")
        self.assertEqual(ProbeResult(held=False, degraded=True), result)

    def test_locking_unavailable_and_exclusive_is_a_noop(self) -> None:
        self.assertFalse(lock.locking_available())
        with exclusive("/tmp/whatever.lock") as run_id:
            self.assertIsNone(run_id)


if __name__ == "__main__":
    unittest.main()
