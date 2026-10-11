"""Where a build's time went: the split, the slowdown rule and the profile report.

The split is measured with a scripted clock, never a sleep: what is under test is
which windows count as model code, not how long anything takes. The profile report
runs the real cProfile over a test-owned project file.
"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")

from cadgen._internal import build_timing  # noqa: E402
from cadgen._internal.build_timing import (  # noqa: E402
    cadgen_work,
    format_duration,
    measuring,
    model_body,
    record_fields,
    slowdown_warning,
    time_line,
    waiting_for_children,
)


class _Clock:
    """``perf_counter`` that returns the times a test scripts, in order."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


class Formatting(unittest.TestCase):
    def test_durations_read_at_a_glance(self):
        self.assertEqual(
            [format_duration(s) for s in (0.0004, 0.82, 0.9996, 14.24, 59.96, 582.0, 3900.0)],
            ["0ms", "820ms", "1.0s", "14.2s", "1m00s", "9m42s", "1h05m"],
        )

    def test_the_time_line_names_the_split_and_only_the_waits_that_happened(self):
        timings = {"seconds": 582.0, "modelSeconds": 500.0, "cadgenSeconds": 82.0,
                   "childrenSeconds": 0.0, "queuedSeconds": 0.0}
        self.assertEqual(
            time_line("STEP/tom.step", timings),
            "built STEP/tom.step in 9m42s: model code 8m20s, cadgen 1m22s",
        )
        timings.update(childrenSeconds=40.0, queuedSeconds=3.0)
        self.assertTrue(time_line("a.step", timings).endswith(
            "cadgen 1m22s, waiting on children 40.0s, queued for a build slot 3.0s"))


class SlowdownRule(unittest.TestCase):
    def test_it_takes_both_twice_the_time_and_thirty_seconds_more(self):
        self.assertIsNone(slowdown_warning("m", 500.0, None), "a first build has nothing to compare")
        self.assertIsNone(slowdown_warning("m", 0.9, 0.1), "9x, but under a second: noise")
        self.assertIsNone(slowdown_warning("m", 190.0, 100.0), "90 s more, but under 2x")
        self.assertEqual(
            slowdown_warning("tom", 500.0, 138.0),
            "warning: tom's model code took 8m20s, 3.6x its last build (2m18s); the time is "
            "in the model script, not cadgen. Rerun with --profile to see where.",
        )


class Measuring(unittest.TestCase):
    def test_model_code_is_the_body_minus_the_windows_cadgen_worked_or_waited_for_it(self):
        clock = _Clock()
        with mock.patch.object(build_timing.time, "perf_counter", clock):
            with measuring(model_ref="/m/a.py::a", last_model_seconds=None) as measured:
                clock.now = 1.0
                with model_body(None):
                    clock.now = 2.0
                    with waiting_for_children():  # a child's build: 3 s
                        clock.now = 5.0
                    clock.now = 6.0
                    with cadgen_work():  # loading a child: 1 s, of which 0.5 s waiting
                        clock.now = 6.2
                        with waiting_for_children():
                            clock.now = 6.7
                        clock.now = 7.0
                    clock.now = 10.0
                    self.assertEqual(record_fields(), {}, "the body is not finished")
                clock.now = 11.0
                with waiting_for_children():  # the outputs it owes after the body: 1 s
                    clock.now = 12.0
                measured.queued = 0.25
                clock.now = 14.0
                timings = measured.timings()
                fields = record_fields()
        self.assertEqual(measured.model_seconds, 5.0)  # 9 s body - 3 s - 1 s
        self.assertEqual(fields, {"modelSeconds": 5.0})
        self.assertEqual(timings.payload(), {
            "seconds": 14.0, "modelSeconds": 5.0, "cadgenSeconds": 4.25,
            "childrenSeconds": 4.5, "queuedSeconds": 0.25,
        })

    def test_a_profiled_build_keeps_the_last_unprofiled_time(self):
        with measuring(model_ref=None, last_model_seconds=42.0, profile=True):
            with model_body(None):
                pass
            self.assertEqual(record_fields(), {"modelSeconds": 42.0})
        with measuring(model_ref=None, last_model_seconds=None, profile=True):
            with model_body(None):
                pass
            self.assertEqual(record_fields(), {})

    def test_nothing_is_measured_outside_a_build(self):
        with model_body(None), waiting_for_children(), cadgen_work():
            pass
        self.assertIsNone(build_timing.current())
        self.assertEqual(record_fields(), {})


class ProfileReport(unittest.TestCase):
    def test_the_report_names_the_slow_function_in_the_project_with_file_line_and_calls(self):
        project = Path(tempfile.mkdtemp(prefix="build-timing-")).resolve()
        self.addCleanup(__import__("shutil").rmtree, project, ignore_errors=True)
        (project / "lib").mkdir()
        (project / "lib" / "shapes.py").write_text(textwrap.dedent("""\
            def churn(n):
                total = 0
                for i in range(n):
                    total += i * i
                return total


            def model():
                return [churn(200_000) for _ in range(3)]
            """), encoding="utf-8")
        spec = importlib.util.spec_from_file_location("build_timing_fixture_shapes", project / "lib" / "shapes.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)  # type: ignore[union-attr]
        self.addCleanup(sys.modules.pop, "build_timing_fixture_shapes", None)

        with measuring(model_ref=None, last_model_seconds=None, profile=True) as measured:
            with model_body(project):
                module.model()
        report = measured.profile_report or ""
        lines = report.splitlines()
        self.assertTrue(lines[0].startswith("profile of the model code ("), report)
        project_rows = lines[lines.index("  in this project, by cumulative time:") + 1:
                             lines.index("  everywhere, by own time:")]
        self.assertTrue(any(row.endswith("lib/shapes.py:1 churn") and "3 calls" in row for row in project_rows), report)
        overall = lines[lines.index("  everywhere, by own time:") + 1:-1]
        self.assertTrue(overall[0].endswith("lib/shapes.py:1 churn"), report)
        self.assertRegex(lines[-1], r"^  those \d+ functions account for \d+% of the profiled time")
        self.assertNotIn("build_timing.py", report, "the profiler's own switching is not the model's")


if __name__ == "__main__":
    unittest.main()
