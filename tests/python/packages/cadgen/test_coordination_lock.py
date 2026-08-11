"""Mutual-exclusion tests for the per-model generation lock.

The lock guards a render package against two builders writing it at once, so the
tests that matter drive REAL concurrency (separate processes, separate threads,
SIGKILL) rather than asserting on a status payload. The previous JSON+heartbeat
scheme passed unit tests while failing every one of these.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import textwrap
import threading
import time
import unittest
from pathlib import Path

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")

from cadgen.coordination.lock import exclusive  # noqa: E402
from cadgen.coordination.paths import WRITE_LOCK_SUFFIX, write_lock_path  # noqa: E402

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

        with exclusive(self.lock):
            threading.Thread(target=run, daemon=True).start()
            self.assertTrue(done.wait(10), "an unrelated model blocked on this one's lock")

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
        probing the sentinel from a second descriptor while the check is executing."""
        import fcntl

        from cadgen.coordination import STEP_PACKAGE, artifact_build
        from cadgen.coordination.paths import write_lock_path

        package = self.root / "__cadgen__" / "models" / "part.step.py"
        lock = write_lock_path(package)
        observed = []

        def _is_current():
            handle = open(lock, "a+b")
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                observed.append("locked")
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
                observed.append("UNLOCKED")
            finally:
                handle.close()
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


if __name__ == "__main__":
    unittest.main()
