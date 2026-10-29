"""Actual function profiles across Python, workers, cold builds and cache hits."""
from __future__ import annotations

import contextlib
import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock

from cadgen.engine.api import build_script, stop
from cadgen.engine.profiling import describe


class ProfilingTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="engine-profile-")
        cls.addClassCleanup(temporary.cleanup)
        cls.root = Path(temporary.name).resolve()
        state = tempfile.TemporaryDirectory(prefix="eng-", dir="/tmp" if os.name != "nt" else None)
        cls.addClassCleanup(state.cleanup)
        cls.enterClassContext(mock.patch.dict(os.environ, {"CADGEN_ENGINE_DIR": state.name}))
        # A warm worker keeps its cwd open on Windows. Stop this class's own engine
        # before removing any fixture directory; all cases still share its warm daemon.
        cls.addClassCleanup(stop)
        from tests.python.support import engine_daemon
        engine_daemon.started(dict(os.environ), cls.addClassCleanup)

    def setUp(self) -> None:
        self.folder = self.root / self._testMethodName
        self.folder.mkdir()
        self.enterContext(contextlib.chdir(self.folder))

    def assert_profile(self, report: dict, *, worker: bool = True) -> dict:
        self.assertTrue(report["ok"], report.get("error"))
        profile = report["profile"]
        self.assertEqual((profile["scope"], profile["mode"], profile["builtins"]),
                         ("build_request", "actual_execution", False))
        self.assertEqual(profile["process"] == os.getpid(), not worker)
        self.assertTrue(profile["top_self"])
        for table, timing in (("project_cumulative", "cumulative_seconds"), ("top_self", "self_seconds")):
            rows = profile[table]
            self.assertLessEqual(len(rows), 20)
            self.assertEqual([row[timing] for row in rows], sorted((row[timing] for row in rows), reverse=True))
            for row in rows:
                self.assertGreater(row["calls"], 0, row)
                self.assertGreaterEqual(row["cumulative_seconds"], row["self_seconds"],
                                        f"{table}: {row['function']} at {row['file']}:{row['line']}, {row['calls']} calls "
                                        f"({row['primitive_calls']} primitive): {json.dumps(profile, indent=1)}")
        json.dumps(profile)  # the worker's result and Python's result have the same JSON surface
        return profile

    def test_plain_python_script_profiles_decorated_model_and_preserves_warm_hits(self) -> None:
        script = self.folder / "model.py"
        script.write_text(textwrap.dedent('''
            import json
            import build123d as bd
            from cadgen import xbf

            def make_block():
                return bd.Box(3, 4, 5)

            @xbf("part.xbf")
            def part():
                return make_block()

            if __name__ == "__main__":
                print(json.dumps(part.build(profile=True).models[0]))
                print(json.dumps(part.build(profile=True).models[0]))
                print(json.dumps(part.build().models[0]))
        '''), encoding="utf-8")
        result = subprocess.run([sys.executable, str(script)], capture_output=True, text=True, check=True)
        cold, warm, ordinary = map(json.loads, result.stdout.splitlines())
        first = self.assert_profile(cold)
        second = self.assert_profile(warm)
        self.assertIn("make_block", {row["function"] for row in first["project_cumulative"]})
        self.assertNotIn("make_block", {row["function"] for row in second["project_cumulative"]})
        self.assertEqual(warm["memo"]["bodies_run"], 0)
        self.assertFalse(warm["files"][str(self.folder / "part.xbf")]["written"])
        self.assertNotIn("profile", ordinary)
        self.assertEqual({p.name for p in self.folder.iterdir()}, {"model.py", "part.xbf"})

    def test_a_cold_build_and_a_failing_body_are_profiled_and_described(self) -> None:
        script = self.folder / "pin.py"
        script.write_text(textwrap.dedent('''
            import build123d as bd
            from cadgen import model

            def make_pin():
                return bd.Cylinder(2, 5)

            @model
            def pin():
                return make_pin()

            @model
            def broken():
                raise ValueError("broken")
        '''), encoding="utf-8")
        built = build_script(script, ["pin"], profile=True, daemon=False, progress=False).models[0]
        profile = self.assert_profile(built, worker=False)
        functions = {row["function"] for row in profile["project_cumulative"]}
        self.assertTrue({"pin", "make_pin"} <= functions, functions)
        described = describe(profile)
        self.assertIn("project functions by cumulative time", described)
        self.assertIn("cache hits preserved", described)
        failed = build_script(script, ["broken"], profile=True, daemon=False, progress=False).models[0]
        self.assertFalse(failed["ok"])
        self.assertIn("broken", {row["function"] for row in failed["profile"]["project_cumulative"]})
        ordinary = build_script(script, ["pin"], daemon=False, progress=False).models[0]
        self.assertNotIn("profile", ordinary)
        self.assertEqual([path.name for path in self.folder.iterdir()], ["pin.py"])


class QuietTest(unittest.TestCase):
    """cProfile records every thread's calls on one stack (Python 3.12+), so a call another thread
    made while a build was profiled was booked against the build's frames: once, a row of 0.12 s
    self time and 0.0 cumulative. The worker's other threads run their Python inside ``quiet``,
    which waits while a profile records."""

    def test_a_thread_s_work_waits_while_a_profile_records_and_none_of_it_is_in_the_profile(self) -> None:
        import threading
        import time

        from cadgen.engine.profiling import Profile, quiet

        recording = [False]
        ran: list[bool] = []

        def elsewhere() -> None:
            ran.append(recording[0])

        def other() -> None:
            with quiet():
                elsewhere()

        def held(thread: threading.Thread) -> bool:  # the thread stands at quiet's door
            frame = sys._current_frames().get(thread.ident)
            while frame is not None:
                if frame.f_code.co_name == "quiet":
                    return True
                frame = frame.f_back
            return False

        with Profile(project=Path(__file__).parent) as measured:
            recording[0] = True
            thread = threading.Thread(target=other)
            thread.start()
            deadline = time.monotonic() + 30
            while not (ran or held(thread)):  # it ran, or it waits
                self.assertLess(time.monotonic(), deadline, "the other thread got to its work")
                time.sleep(0.005)
            recording[0] = False
        thread.join(30)
        self.assertEqual(ran, [False], "the other thread's work ran once the profile had recorded, not during it")
        self.assertNotIn("elsewhere", {row["function"] for row in measured.report()["top_self"]})


def setUpModule() -> None:
    # The registry and cache of every engine this module starts are its own, never the developer's
    # (``engine_daemon.isolate``); each test still names its own engine folder.
    from tests.python.support import engine_daemon

    engine_daemon.isolate(unittest.addModuleCleanup)
