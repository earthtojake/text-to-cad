"""Progress reporting: the record a run publishes, and where a reader finds it.

There is no lock to test any more. What remains is the narration: a run's record goes
from running to done (with stage times) or failed (without), a skipped run says so, an
export's record cannot overwrite a build's, and every producer derives the record's path
from the model's build scope in the daemon's state directory -- never under the store.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")

from cadgen.coordination import (  # noqa: E402
    STEP_PACKAGE,
    artifact_build,
    generator_busy,
)
from cadgen.coordination import record as record_mod  # noqa: E402
from cadgen.coordination.paths import generator_progress_path, progress_path, state_dir  # noqa: E402
from cadgen.coordination.phases import PHASE_COMPONENTS  # noqa: E402


class CoordinationTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="cadcoord-")
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        patcher = mock.patch.dict(os.environ, {"CADGEN_DAEMON_STATE_DIR": str(self.root / "state")})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.scope = "widget-scope"

    def _record(self):
        return record_mod.read_record(progress_path(self.scope))


class RecordLifecycle(CoordinationTestCase):
    def test_a_run_publishes_running_then_done_with_stage_times(self):
        seen = []
        with artifact_build(STEP_PACKAGE, self.scope, is_current=lambda: False) as run:
            seen.append(self._record()["outcome"])
            run.phase(PHASE_COMPONENTS, total=4)
            run.advance(2)
            self.assertEqual(self._record()["done"], 2)
            self.assertEqual(self._record()["total"], 4)
        record = self._record()
        self.assertEqual([None], seen, "the record was not published before the body ran")
        self.assertEqual(record["outcome"], record_mod.OUTCOME_DONE)
        self.assertIn(PHASE_COMPONENTS, record["stageMs"])
        self.assertEqual(record["runId"], run.run_id)

    def test_a_failed_run_publishes_failed_without_stage_times(self):
        with self.assertRaises(RuntimeError):
            with artifact_build(STEP_PACKAGE, self.scope, is_current=lambda: False) as run:
                run.phase(PHASE_COMPONENTS, total=4)
                raise RuntimeError("boom")
        record = self._record()
        self.assertEqual(record["outcome"], record_mod.OUTCOME_FAILED)
        self.assertIsNone(record.get("stageMs"))

    def test_a_current_artifact_is_skipped_and_says_so(self):
        with artifact_build(STEP_PACKAGE, self.scope, is_current=lambda: True) as run:
            self.assertTrue(run.skipped)
        self.assertEqual(self._record()["outcome"], record_mod.OUTCOME_SKIPPED)

    def test_force_ignores_is_current(self):
        with artifact_build(STEP_PACKAGE, self.scope, is_current=lambda: True, force=True) as run:
            self.assertFalse(run.skipped)

    def test_no_scope_means_no_record_but_freshness_is_still_answered(self):
        with artifact_build(STEP_PACKAGE, None, is_current=lambda: True) as run:
            self.assertTrue(run.skipped)
            self.assertIsNone(run.run_id)
        self.assertFalse((self.root / "state").exists())

    def test_each_run_has_its_own_id(self):
        with artifact_build(STEP_PACKAGE, self.scope) as first:
            pass
        with artifact_build(STEP_PACKAGE, self.scope) as second:
            pass
        self.assertNotEqual(first.run_id, second.run_id)


class WherePathsLive(CoordinationTestCase):
    def test_records_live_in_the_daemon_state_dir_never_the_store(self):
        with mock.patch.dict(os.environ, {"CADGEN_CACHE_DIR": str(self.root / "store")}):
            with artifact_build(STEP_PACKAGE, self.scope):
                pass
        self.assertTrue(progress_path(self.scope).is_file())
        self.assertEqual(progress_path(self.scope).parent, state_dir() / "progress")
        self.assertFalse((self.root / "store").exists(), "a progress record reached the store")

    def test_a_generator_run_reports_to_its_own_record(self):
        with artifact_build(STEP_PACKAGE, self.scope, is_current=lambda: False) as build:
            build.phase(PHASE_COMPONENTS, total=10)
            build.advance(7)
            with generator_busy(STEP_PACKAGE, self.scope) as export:
                self.assertIsNotNone(export)
                export.phase(PHASE_COMPONENTS, total=2)
            # The export's record is a different file: the build's position is intact.
            self.assertEqual(self._record()["done"], 7)
            self.assertEqual(self._record()["outcome"], None)
        generator = record_mod.read_record(generator_progress_path(self.scope))
        self.assertEqual(generator["intent"], record_mod.INTENT_GENERATE)
        self.assertEqual(generator["outcome"], record_mod.OUTCOME_DONE)
        self.assertEqual(self._record()["intent"], record_mod.INTENT_WRITE)

    def test_generator_busy_with_no_scope_yields_none(self):
        with generator_busy(STEP_PACKAGE, None) as run:
            self.assertIsNone(run)

    def test_the_viewer_reads_the_record_a_producer_publishes(self):
        from cadgen.viewer.build_progress import build_progress_snapshot

        model = self.root / "src" / "plate.py"
        model.parent.mkdir(parents=True)
        model.write_text("", encoding="utf-8")
        from cadgen.catalog import build_scope

        self.assertIsNone(build_progress_snapshot(model))
        with artifact_build(STEP_PACKAGE, build_scope(model), is_current=lambda: False) as run:
            run.phase(PHASE_COMPONENTS, total=5)
            run.advance(1)
            snapshot = build_progress_snapshot(model)
            self.assertIsNotNone(snapshot, "the viewer looked somewhere the producer did not write")
            self.assertEqual(snapshot["runId"], run.run_id)
            self.assertEqual(snapshot["progress"]["done"], 1)
        self.assertIsNone(build_progress_snapshot(model), "a finished run is not in flight")


class WriteRecord(CoordinationTestCase):
    def test_write_is_atomic_and_survives_an_unwritable_target(self):
        target = self.root / "state" / "progress" / "x.json"
        self.assertTrue(record_mod.write_record(target, {"a": 1}))
        self.assertEqual(record_mod.read_record(target), {"a": 1})
        self.assertEqual([p.name for p in target.parent.iterdir()], ["x.json"], "a temp file was left behind")
        blocked = self.root / "blocked"
        blocked.write_text("not a directory", encoding="utf-8")
        self.assertFalse(record_mod.write_record(blocked / "x.json", {"a": 1}))


if __name__ == "__main__":
    unittest.main()
