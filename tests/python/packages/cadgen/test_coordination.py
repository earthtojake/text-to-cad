"""The coordination primitives: locking, probing, run attribution, freshness re-check.

Everything here drives the real modules. Where the claim is about cross-process behaviour
it uses real subprocesses and real ``fcntl`` -- a mocked lock proves nothing about a
protocol whose entire job is to survive being observed by another process.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import warnings
from pathlib import Path

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")

from cadgen.coordination import (  # noqa: E402
    STEP_PACKAGE,
    Contended,
    artifact_build,
    generator_busy,
    require_write_lock,
    snapshot,
)
from cadgen.coordination import record as record_mod  # noqa: E402
from cadgen.coordination.lock import exclusive, probe  # noqa: E402
from cadgen.coordination.paths import status_path, write_lock_path  # noqa: E402
from cadgen.coordination.phases import PHASE_COMPONENTS  # noqa: E402

_CADGEN_SRC = str(Path(__file__).resolve().parents[4] / "packages" / "cadgen" / "src")

# Holds the write lock for a while so the parent can observe it from outside.
_HOLDER = """
import sys, time
sys.path.insert(0, {src!r})
from cadgen.coordination import STEP_PACKAGE, artifact_build
with artifact_build(STEP_PACKAGE, {out!r}, is_current=lambda: False) as run:
    run.phase("components", total=4)
    run.advance()
    print("HELD", flush=True)
    time.sleep({hold})
"""


class CoordinationTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="cadcoord-")
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.out = self.root / "__cadgen__" / "models" / "widget.step.py"

    def _spawn_holder(self, hold=3.0):
        proc = subprocess.Popen(
            [sys.executable, "-c", _HOLDER.format(src=_CADGEN_SRC, out=str(self.out), hold=hold)],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )

        def _reap():
            proc.kill()
            proc.wait(timeout=30)
            if proc.stdout is not None:
                proc.stdout.close()

        self.addCleanup(_reap)
        self.assertEqual("HELD", (proc.stdout.readline() or "").strip(), "holder never started")
        return proc


class SnapshotTest(CoordinationTestCase):
    def test_idle_when_nothing_has_ever_run(self):
        snap = snapshot(self.out)
        self.assertEqual("idle", snap.state)
        self.assertIsNone(snap.progress)

    def test_probing_does_not_create_the_sentinel(self):
        snapshot(self.out)
        self.assertFalse(
            write_lock_path(self.out).exists(),
            "a status read must not materialise files for a never-built artifact",
        )

    def test_reports_writing_while_a_peer_holds_the_lock(self):
        self._spawn_holder()
        snap = snapshot(self.out)
        self.assertEqual("writing", snap.state)
        self.assertIsNotNone(snap.run_id)
        self.assertIsNotNone(snap.progress, "a live run's progress must be visible")
        self.assertEqual(PHASE_COMPONENTS, snap.progress["phase"])

    def test_generator_busy_does_not_read_as_a_build(self):
        with generator_busy(STEP_PACKAGE, self.out):
            snap = snapshot(self.out)
        # An export occupies the generator but rewrites nothing, so the artifact on disk is
        # still whatever it was -- reporting `writing` here would hide a renderable model.
        self.assertEqual("busy", snap.state)


class GeneratorRecordIsolationTest(CoordinationTestCase):
    """The two sentinels do NOT exclude each other, so a generator run and a writer run
    overlap by design. They must not share a record file: while they did, an export landed
    on top of a live build's progress and the viewer's bar vanished mid-build."""

    def test_a_generator_run_does_not_touch_the_writers_record(self):
        with exclusive(write_lock_path(self.out)) as write_run:
            record_mod.write_record(
                status_path(self.out),
                record_mod.build_record(
                    run_id=write_run,
                    kind="step-package",
                    intent="write",
                    started_at_ms=0.0,
                    outcome=None,
                    progress={"phase": "components", "done": 7, "total": 9, "ratio": 0.5},
                ),
            )
            with generator_busy(STEP_PACKAGE, self.out):
                snap = snapshot(self.out)
            self.assertEqual("writing", snap.state, "the writer still holds its sentinel")
            self.assertIsNotNone(
                snap.progress, "an overlapping export must not erase the build's bar"
            )
            self.assertEqual("components", snap.progress["phase"])

    def test_a_generator_run_does_not_erase_the_learned_stage_times(self):
        # An export leaves a terminal record with no stageMs. Sharing the writer's file made
        # that record the one the NEXT build read, so the model forgot its phase weighting.
        with artifact_build(STEP_PACKAGE, self.out, is_current=lambda: False) as run:
            run.phase(PHASE_COMPONENTS, total=2)
            run.advance()
        learned = record_mod.read_stage_ms(status_path(self.out))
        self.assertTrue(learned, "a successful build records what its phases cost")

        with generator_busy(STEP_PACKAGE, self.out):
            pass
        self.assertEqual(
            learned,
            record_mod.read_stage_ms(status_path(self.out)),
            "an export must not cost the next build its learned phase weighting",
        )


class RunAttributionTest(CoordinationTestCase):
    def test_a_dead_runs_record_is_not_shown_as_the_live_runs_progress(self):
        # Simulate a SIGKILLed build: a non-terminal record left behind forever.
        status_path(self.out).parent.mkdir(parents=True, exist_ok=True)
        record_mod.write_record(
            status_path(self.out),
            record_mod.build_record(
                run_id="deadbeef",
                kind="step-package",
                intent="write",
                started_at_ms=0.0,
                outcome=None,
                progress={"phase": "components", "done": 31, "total": 50, "ratio": 0.77},
            ),
        )
        with exclusive(write_lock_path(self.out)) as run_id:
            self.assertIsNotNone(run_id)
            snap = snapshot(self.out)
            self.assertEqual("writing", snap.state)
            self.assertIsNone(
                snap.progress,
                "the corpse of a killed run must not be rendered as this run's position",
            )

    def test_stage_ms_is_absent_after_a_failed_run(self):
        with self.assertRaises(RuntimeError):
            with artifact_build(STEP_PACKAGE, self.out, is_current=lambda: False) as run:
                run.phase(PHASE_COMPONENTS, total=2)
                run.advance()
                raise RuntimeError("boom")
        payload = record_mod.read_record(status_path(self.out))
        self.assertEqual("failed", payload["outcome"])
        self.assertIsNone(
            payload["stageMs"],
            "a failed run must not teach the next build's bar from partial stage times",
        )

    def test_stage_ms_is_recorded_after_a_successful_run(self):
        with artifact_build(STEP_PACKAGE, self.out, is_current=lambda: False) as run:
            run.phase(PHASE_COMPONENTS, total=2)
            run.advance()
        payload = record_mod.read_record(status_path(self.out))
        self.assertEqual("done", payload["outcome"])
        self.assertIsInstance(payload["stageMs"], dict)

    def test_the_next_run_learns_the_previous_runs_stage_times(self):
        """The bar is weighted from the LAST build of this artifact.

        artifact_build publishes a `starting` record before yielding, and that record carries
        stageMs: None by construction. Reading the previous run's times AFTER publishing
        therefore read the record just written and learned nothing -- silently reverting every
        build to the default phase split. That matters most for a long indeterminate phase,
        which is interpolated against the learned duration.
        """
        with artifact_build(STEP_PACKAGE, self.out, is_current=lambda: False) as run:
            run.phase("generate")
            time.sleep(0.05)
            run.phase(PHASE_COMPONENTS, total=1)
            run.advance()
        recorded = record_mod.read_stage_ms(status_path(self.out))
        self.assertTrue(recorded, "the first run must record its stage times")

        with artifact_build(STEP_PACKAGE, self.out, is_current=lambda: False) as run:
            learned = dict(run._reporter._expected)
        self.assertEqual(
            sorted(recorded), sorted(learned), "the next run did not learn the previous times"
        )

    def test_a_finished_run_reports_no_progress(self):
        with artifact_build(STEP_PACKAGE, self.out, is_current=lambda: False) as run:
            run.phase(PHASE_COMPONENTS, total=2)
        self.assertEqual("idle", snapshot(self.out).state)
        self.assertIsNone(snapshot(self.out).progress)


class WriteLockGuardTest(CoordinationTestCase):
    """require_write_lock is the backstop that makes D1 unrepeatable.

    The lock used to be taken at call sites, so whether a package write was coordinated
    depended on which producer you arrived through -- and ensure_step_topology_artifact
    arrived through one that took none, making a cold `cad inspect` build invisible to the
    viewer and letting it race a viewer build into the same directory. The assertion lives
    at the mutation boundary so a future producer cannot reintroduce that.
    """

    def setUp(self):
        super().setUp()
        self._prev = os.environ.get("CADGEN_STRICT_LOCKS")
        os.environ["CADGEN_STRICT_LOCKS"] = "1"

    def tearDown(self):
        if self._prev is None:
            os.environ.pop("CADGEN_STRICT_LOCKS", None)
        else:
            os.environ["CADGEN_STRICT_LOCKS"] = self._prev

    def test_holding_the_lock_satisfies_the_guard(self):
        with artifact_build(STEP_PACKAGE, self.out, is_current=lambda: False):
            self.assertTrue(require_write_lock(self.out))

    def test_writing_without_the_lock_raises_under_strict_mode(self):
        with self.assertRaises(RuntimeError):
            require_write_lock(self.out)

    def test_a_different_artifacts_lock_does_not_satisfy_the_guard(self):
        other = self.root / "__cadgen__" / "models" / "other.step.py"
        with artifact_build(STEP_PACKAGE, other, is_current=lambda: False):
            with self.assertRaises(RuntimeError):
                require_write_lock(self.out)

    def test_production_only_warns(self):
        os.environ.pop("CADGEN_STRICT_LOCKS", None)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            self.assertFalse(require_write_lock(self.out))
        self.assertTrue(any(issubclass(w.category, RuntimeWarning) for w in caught))


class ProbeConcurrencyTest(CoordinationTestCase):
    def test_concurrent_probes_do_not_report_a_phantom_build(self):
        """flock conflicts per open file description, not per process.

        The previous reader probed with LOCK_EX, so two concurrent probes of an UNHELD
        sentinel conflicted with EACH OTHER and one reported a build in flight. Measured at
        ~6% false positives with four threads.
        """
        lock = write_lock_path(self.out)
        lock.parent.mkdir(parents=True, exist_ok=True)
        lock.touch()

        false_positives = []
        lock_guard = threading.Lock()

        def worker():
            hits = sum(1 for _ in range(2000) if probe(lock).held)
            with lock_guard:
                false_positives.append(hits)

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(
            0,
            sum(false_positives),
            "a shared-mode probe must never conflict with another probe",
        )


class PostLockFreshnessTest(CoordinationTestCase):
    def test_is_current_is_evaluated_under_the_lock(self):
        order = []

        with artifact_build(
            STEP_PACKAGE,
            self.out,
            is_current=lambda: (order.append("check"), False)[1],
        ) as run:
            order.append("body")
            self.assertFalse(run.skipped)
        self.assertEqual(["check", "body"], order)

    def test_a_current_artifact_skips_the_body(self):
        ran = []
        with artifact_build(STEP_PACKAGE, self.out, is_current=lambda: True) as run:
            if not run.skipped:
                ran.append("body")
        self.assertEqual([], ran)
        self.assertEqual("skipped", record_mod.read_record(status_path(self.out))["outcome"])

    def test_force_bypasses_the_currency_check_but_not_the_lock(self):
        checked = []
        with artifact_build(
            STEP_PACKAGE, self.out, is_current=lambda: checked.append(1) or True, force=True
        ) as run:
            self.assertFalse(run.skipped)
        self.assertEqual([], checked, "force must not consult is_current at all")


class BoundedWaitTest(CoordinationTestCase):
    def test_deadline_reports_contended_instead_of_blocking(self):
        self._spawn_holder(hold=10.0)
        started = time.monotonic()
        with artifact_build(
            STEP_PACKAGE, self.out, is_current=lambda: False, deadline_ms=300
        ) as run:
            self.assertTrue(run.contended, "a peer holds the lock; this run got nothing")
            self.assertIsNone(run.run_id, "a contended run never became a run")
        self.assertLess(
            time.monotonic() - started, 5.0, "a bounded wait must not block for the full run"
        )

    def test_an_acquired_run_is_not_contended(self):
        with artifact_build(
            STEP_PACKAGE, self.out, is_current=lambda: False, deadline_ms=5000
        ) as run:
            self.assertFalse(run.contended)
            self.assertIsNotNone(run.run_id)

    def test_exclusive_still_raises_contended_for_lower_level_callers(self):
        # artifact_build turns a lost race into run.contended; the primitive underneath it
        # keeps raising, so a caller with no BuildRun to inspect still cannot miss it.
        self._spawn_holder(hold=10.0)
        with self.assertRaises(Contended):
            with exclusive(write_lock_path(self.out), deadline_ms=300):
                pass

    def test_a_contended_run_writes_no_record(self):
        # The peer owns the record. A run that never took the lock must not touch it --
        # overwriting it is exactly how a live build's bar used to disappear.
        self._spawn_holder(hold=10.0)
        before = status_path(self.out).read_bytes() if status_path(self.out).exists() else None
        with artifact_build(
            STEP_PACKAGE, self.out, is_current=lambda: False, deadline_ms=300
        ) as run:
            self.assertTrue(run.contended)
        after = status_path(self.out).read_bytes() if status_path(self.out).exists() else None
        self.assertEqual(before, after)

    def test_a_blocked_acquire_reports_that_it_is_waiting(self):
        # Without this a contended acquire emits nothing at all for as long as the peer
        # holds the lock, which is indistinguishable from a hung process.
        self._spawn_holder(hold=1.5)
        waits = []
        with artifact_build(
            STEP_PACKAGE, self.out, is_current=lambda: False, on_wait=waits.append
        ) as run:
            self.assertFalse(run.contended, "no deadline: it must wait the peer out")
        self.assertTrue(waits, "a wait long enough to notice must be reported")
        self.assertGreater(waits[0], 0.0)

    def test_reentrant_acquire_in_one_thread_does_not_deadlock(self):
        with exclusive(write_lock_path(self.out)) as outer:
            with exclusive(write_lock_path(self.out)) as inner:
                self.assertEqual(outer, inner)


if __name__ == "__main__":
    unittest.main()
