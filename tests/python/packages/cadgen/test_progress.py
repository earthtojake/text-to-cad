"""The two shapes a phase can report, and the generator-facing API that produces them."""

from __future__ import annotations

import unittest

from cadgen.coordination import BuildRun, current_build, reporting_as
from cadgen.coordination.phases import PHASE_COMPONENTS, PHASE_GENERATE, ProgressReporter
from cadgen.progress import report, track


def _recording_reporter() -> tuple[ProgressReporter, list]:
    events: list = []
    return ProgressReporter(sinks=[events.append]), events


class PhaseShapeTest(unittest.TestCase):
    def test_a_phase_with_a_total_reports_a_real_fraction(self):
        reporter, events = _recording_reporter()
        reporter.phase(PHASE_COMPONENTS, total=4)
        reporter.advance(detail="a1b2")
        self.assertTrue(events[-1].determinate)
        self.assertEqual(0.25, events[-1].fraction)
        self.assertEqual(1, events[-1].done)
        self.assertEqual(4, events[-1].total)

    def test_a_phase_without_a_total_has_no_fraction_to_report(self):
        reporter, events = _recording_reporter()
        reporter.phase(PHASE_GENERATE)
        self.assertFalse(events[-1].determinate)
        self.assertIsNone(events[-1].fraction, "a phase with no denominator must not imply one")

    def test_a_changed_label_is_published_even_inside_the_throttle_window(self):
        """The bug this pairing was written for.

        `detail` is throttled so a chatty caller cannot spend the build's time on reporting.
        But a phase's FIRST label lands microseconds after the phase/set_total that opened
        it, so a blanket throttle swallowed it -- and because an uncountable phase emits
        nothing else, the label then stayed empty for the entire phase.
        """
        reporter, events = _recording_reporter()
        reporter.phase(PHASE_GENERATE)
        reporter.detail("airframe")
        self.assertEqual("airframe", events[-1].detail)

    def test_repeating_the_label_already_showing_is_throttled(self):
        reporter, events = _recording_reporter()
        reporter.phase(PHASE_GENERATE)
        reporter.detail("airframe")
        before = len(events)
        for _ in range(50):
            reporter.detail("airframe")
        self.assertEqual(before, len(events), "a repeat says nothing new and must not be written")

    def test_a_phase_reports_its_position_in_the_run(self):
        reporter, events = _recording_reporter()
        reporter.phase(PHASE_COMPONENTS)
        self.assertEqual((3, 4), (events[-1].index, events[-1].count))

    def test_an_undeclared_phase_reports_no_position_rather_than_a_wrong_one(self):
        reporter, events = _recording_reporter()
        reporter.phase("polishing")
        self.assertEqual(0, events[-1].index)


class GeneratorApiTest(unittest.TestCase):
    def test_track_outside_a_build_is_a_transparent_pass_through(self):
        # The same generator runs under the CLI, the viewer's worker, a test, and a plain
        # `python model.step.py`. Instrumentation must never need guarding.
        self.assertIsNone(current_build())
        self.assertEqual([1, 2, 3], list(track([1, 2, 3])))

    def test_report_outside_a_build_does_nothing(self):
        report("airframe")  # must not raise

    def test_track_counts_completed_work_and_labels_what_is_in_flight(self):
        reporter, events = _recording_reporter()
        reporter.phase(PHASE_GENERATE)
        run = BuildRun(reporter, "run-1")
        seen = []
        with reporting_as(run):
            for name in track(["airframe", "cockpit"], label=lambda item: item):
                # Mid-item: this one is named, and NOT yet counted.
                seen.append((events[-1].detail, events[-1].done))
        self.assertEqual([("airframe", 0), ("cockpit", 1)], seen)
        self.assertEqual(2, events[-1].done, "the last item is counted once its work returns")
        self.assertEqual(2, events[-1].total)

    def test_track_leaves_a_lazy_iterable_lazy_and_reports_it_by_label_alone(self):
        # Consuming it here to obtain a denominator would change WHEN the caller's work runs.
        reporter, events = _recording_reporter()
        reporter.phase(PHASE_GENERATE)
        with reporting_as(BuildRun(reporter, "run-1")):
            list(track((name for name in ["airframe"]), label=lambda item: item))
        # The label is the only event: with no denominator the count says nothing, so its
        # tick stays throttled while the label — which does say something — is published.
        self.assertFalse(events[-1].determinate)
        self.assertEqual("airframe", events[-1].detail)

    def test_a_nested_bind_does_not_retarget_the_outer_run(self):
        # A model that composes child generators would otherwise have the child's loop
        # overwrite the parent's phase, and the outer count is the one a reader can use.
        outer = BuildRun(ProgressReporter(), "outer")
        with reporting_as(outer):
            with reporting_as(BuildRun(ProgressReporter(), "inner")):
                self.assertIs(outer, current_build())
        self.assertIsNone(current_build())

    def test_a_label_callable_that_raises_cannot_break_a_build(self):
        reporter, events = _recording_reporter()
        reporter.phase(PHASE_GENERATE)
        with reporting_as(BuildRun(reporter, "run-1")):
            self.assertEqual([1], list(track([1], label=lambda item: 1 / 0)))


if __name__ == "__main__":
    unittest.main()
