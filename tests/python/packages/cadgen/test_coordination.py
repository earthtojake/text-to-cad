"""Progress reporting: a run narrates its phases to the sinks it is given.

There is no lock and no record on disk. What remains is the narration: phases and
counts reach the sink as they happen, a terminal ``done`` frame closes a run that
returns, a run that raises sends none, a current artifact is skipped and says so,
and a run with no scope still answers freshness while narrating nowhere. Readers in
other processes get the same narration from the daemon's job ledger
(``test_daemon_jobs.py``).
"""

from __future__ import annotations

import unittest

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")

from cadgen.coordination import (  # noqa: E402
    STEP_PACKAGE,
    artifact_build,
    generator_busy,
)
from cadgen.coordination.phases import PHASE_COMPONENTS, PHASE_DONE  # noqa: E402


class RunNarration(unittest.TestCase):
    def test_phases_and_counts_reach_the_sink_then_a_terminal_done(self):
        frames = []
        with artifact_build(STEP_PACKAGE, "widget-scope", is_current=lambda: False, sink=frames.append) as run:
            run.phase(PHASE_COMPONENTS, total=4)
            run.advance(2)
        self.assertEqual([PHASE_COMPONENTS, PHASE_COMPONENTS, PHASE_DONE], [f.phase for f in frames][-3:])
        self.assertEqual((2, 4), (frames[-2].done, frames[-2].total))
        self.assertTrue(frames[-1].finished)
        self.assertTrue(run.run_id)

    def test_a_failed_run_sends_no_terminal_frame(self):
        frames = []
        with self.assertRaises(RuntimeError):
            with artifact_build(STEP_PACKAGE, "widget-scope", is_current=lambda: False, sink=frames.append) as run:
                run.phase(PHASE_COMPONENTS, total=4)
                raise RuntimeError("boom")
        self.assertFalse(any(f.finished for f in frames))

    def test_a_current_artifact_is_skipped_and_says_so(self):
        with artifact_build(STEP_PACKAGE, "widget-scope", is_current=lambda: True) as run:
            self.assertTrue(run.skipped)

    def test_force_ignores_is_current(self):
        with artifact_build(STEP_PACKAGE, "widget-scope", is_current=lambda: True, force=True) as run:
            self.assertFalse(run.skipped)

    def test_no_scope_means_no_narration_but_freshness_is_still_answered(self):
        with artifact_build(STEP_PACKAGE, None, is_current=lambda: True) as run:
            self.assertTrue(run.skipped)
            self.assertIsNone(run.run_id)

    def test_each_run_has_its_own_id(self):
        with artifact_build(STEP_PACKAGE, "widget-scope") as first:
            pass
        with artifact_build(STEP_PACKAGE, "widget-scope") as second:
            pass
        self.assertNotEqual(first.run_id, second.run_id)

    def test_an_export_narrates_through_the_same_phases(self):
        frames = []
        with generator_busy(STEP_PACKAGE, "widget-scope", sink=frames.append) as run:
            self.assertIsNotNone(run)
            run.phase(PHASE_COMPONENTS, total=1)
            run.advance()
        self.assertEqual(PHASE_DONE, frames[-1].phase)
        with generator_busy(STEP_PACKAGE, None) as none:
            self.assertIsNone(none)


if __name__ == "__main__":
    unittest.main()
