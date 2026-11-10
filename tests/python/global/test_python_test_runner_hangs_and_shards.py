"""The Python test runner (``scripts/test/unittest_files.py``) when a file hangs, while files run,
and split into shards.

A hung file once held a Windows job for four 15-minute guards in a row, until the job's timeout
killed it with nothing said: so the run starts no file after one hangs, a runner's own backstop ends
a file whose guard never fires, a heartbeat names the files running, and ``--shard I/N`` splits a
suite across CI jobs, every file in exactly one shard."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest import mock

from tests.python.support.paths import REPO_ROOT

spec = importlib.util.spec_from_file_location("sharded_unittest_runner", REPO_ROOT / "scripts/test/unittest_files.py")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)

PASSED = "Ran 1 test in 0.001s\n\nOK\n"

WAITS_FOREVER = (
    "import threading, unittest\n\n\n"
    "class Hung(unittest.TestCase):\n"
    "    def test_waits_forever(self):\n"
    "        threading.Event().wait()\n"
)

# A file that leaves word that it started, which a file the run never started cannot.
LEAVES_WORD = (
    "import pathlib, unittest\n\n"
    "pathlib.Path(__file__).with_suffix('.started').touch()\n\n\n"
    "class Passing(unittest.TestCase):\n"
    "    def test_passes(self):\n"
    "        pass\n"
)


class _Said(io.StringIO):
    """stderr that sets ``heard[words]`` once a write carrying ``words`` arrives."""

    def __init__(self, *words: str) -> None:
        super().__init__()
        self.heard = {word: threading.Event() for word in words}

    def write(self, text: str) -> int:
        written = super().write(text)
        for word, event in self.heard.items():
            if word in text:
                event.set()
        return written


class _Quiet(unittest.TestCase):
    def setUp(self) -> None:
        # Where nothing names an engine's folder, and the developer's own state: none, here.
        for name, value in (("default_engine_door", None), ("person_places", ([], [], ""))):
            patched = mock.patch.object(runner, name, return_value=value)
            patched.start()
            self.addCleanup(patched.stop)


class StopsAtTheFirstHang(_Quiet):
    def real_run(self, files: dict[str, str], **kwargs) -> tuple[int, str, Path]:
        """``files`` (name: source) written to a fresh folder and run there, in order, one at a time."""
        with tempfile.TemporaryDirectory() as scratch:
            top = os.path.realpath(scratch)
            for name, source in files.items():
                Path(top, name).write_text(source, encoding="utf-8")
            said = io.StringIO()
            with contextlib.chdir(top), mock.patch.object(runner.sys, "stderr", said):
                code = runner.run_files([str(Path(top, name)) for name in files], top, 1, False, **kwargs)
            started = sorted(path.stem for path in Path(top).glob("*.started"))
        return code, said.getvalue(), started

    def test_a_file_whose_guard_fires_stops_the_run_and_the_summary_says_it_was_cut_short(self):
        code, said, started = self.real_run({"test_a_hung.py": WAITS_FOREVER, "test_b_later.py": LEAVES_WORD,
                                             "test_c_later.py": LEAVES_WORD}, hang_seconds=1)
        self.assertEqual((code, started), (runner.HUNG_EXIT, []), said)
        self.assertRegex(said, r"hung: \S+test_a_hung\.py: its guard fired 1 s after it started; "
                               r"the run starts no further file\n")
        self.assertIn("in test_waits_forever", said, "its stacks")
        self.assertTrue(said.endswith("RUN CUT SHORT: 2 of the 3 files given never started, because a file hung; "
                                      "the counts above are of the 1 that ran\n"), said)

    def test_a_file_whose_guard_never_fires_is_ended_by_the_runner(self):
        # The runner's backstop ends it long before the guard it gave the file (a minute) could fire,
        # as it would one whose guard a test cancelled or replaced.
        with mock.patch.object(runner, "FILE_BACKSTOP_SECONDS", -59.5):
            code, said, started = self.real_run({"test_a_hung.py": WAITS_FOREVER, "test_b_later.py": LEAVES_WORD},
                                                hang_seconds=60)
        self.assertEqual((code, started), (runner.HUNG_EXIT, []), said)
        self.assertRegex(said, r"hung: \S+test_a_hung\.py: the runner killed it 0\.5 s after it started: "
                               r"its own 60 s guard never fired")
        self.assertIn("failing modules:", said)
        self.assertTrue(said.endswith("RUN CUT SHORT: 1 of the 2 files given never started, because a file hung; "
                                      "the counts above are of the 1 that ran\n"), said)

    def test_the_files_running_beside_a_hang_finish_and_none_starts_after_it(self):
        beside_started = threading.Event()
        said = _Said("hung: ")
        ran: list[str] = []

        def run(path, top, verbose, env, **_):
            ran.append(path)
            if path == "a_hangs.py":
                beside_started.wait()
                return path, 1, "Timeout (0:10:00)!\n", 600.0, "its guard fired 600 s after it started"
            if path == "b_beside.py":
                beside_started.set()
                said.heard["hung: "].wait()  # still running as the hang is found
            return path, 0, PASSED, 0.0, None

        with mock.patch.object(runner, "_run_one_file", side_effect=run), mock.patch.object(runner.sys, "stderr", said):
            code = runner.run_files(["a_hangs.py", "b_beside.py", "c_later.py", "d_later.py"], str(REPO_ROOT), 2, False)
        report = said.getvalue()
        self.assertEqual((code, sorted(ran)), (runner.HUNG_EXIT, ["a_hangs.py", "b_beside.py"]), report)
        self.assertIn("hung: a_hangs.py: its guard fired 600 s after it started; the run starts no further file "
                      "(1 already running will finish first)\n", report)
        self.assertIn("failing modules:\n  a_hangs.py\n", report)
        self.assertIn("hung (each one's stacks are with its output above):\n  a_hangs.py: its guard fired", report)
        self.assertTrue(report.endswith("RUN CUT SHORT: 2 of the 4 files given never started, because a file hung; "
                                        "the counts above are of the 2 that ran\n"), report)


class Heartbeat(_Quiet):
    def test_a_file_running_past_a_beat_is_named_and_a_short_run_says_nothing(self):
        said = _Said("still running: ")

        def run(path, top, verbose, env, **_):
            if path == "slow.py":
                said.heard["still running: "].wait()
            return path, 0, PASSED, 0.0, None

        with mock.patch.object(runner, "_run_one_file", side_effect=run), mock.patch.object(runner.sys, "stderr", said):
            with mock.patch.object(runner, "HEARTBEAT_SECONDS", 0.01):
                self.assertEqual(runner.run_files(["slow.py"], str(REPO_ROOT), 1, False), 0)
            beat = said.getvalue()
            said.truncate(0)
            said.seek(0)
            self.assertEqual(runner.run_files(["quick.py"], str(REPO_ROOT), 1, False), 0)
        self.assertRegex(beat, r"(?m)^still running: \S*slow\.py \(\d+s\)$")
        self.assertNotIn("still running", said.getvalue())


class FileBudget(_Quiet):
    """A shard is no shorter than its slowest file, so the runner names the files over the budget:
    said, on a GitHub Actions run as a warning too, and never a failure."""

    def test_a_file_over_the_budget_is_named_and_the_run_still_passes(self):
        def run(path, top, verbose, env, **_):
            return path, 0, PASSED, {"slow.py": 130.4, "quick.py": 3.0}[path], None

        said, plain = io.StringIO(), io.StringIO()
        with mock.patch.object(runner, "_run_one_file", side_effect=run):
            with mock.patch.dict(os.environ, {"GITHUB_ACTIONS": "true"}), mock.patch.object(runner.sys, "stderr", said):
                code = runner.run_files(["slow.py", "quick.py"], str(REPO_ROOT), 2, False, file_budget=120)
            with mock.patch.dict(os.environ, {"GITHUB_ACTIONS": ""}), mock.patch.object(runner.sys, "stderr", plain):
                unbudgeted = runner.run_files(["slow.py", "quick.py"], str(REPO_ROOT), 2, False)
        self.assertEqual((code, unbudgeted), (0, 0), said.getvalue())
        self.assertIn("OVER BUDGET (120 s a test file; split what outgrows it):\n  slow.py  130s\n", said.getvalue())
        self.assertIn("::warning file=slow.py,title=Test file over its time budget::130 s, over the 120 s",
                      said.getvalue())
        self.assertNotIn("quick.py  ", said.getvalue())
        self.assertNotIn("OVER BUDGET", plain.getvalue())


class Shards(unittest.TestCase):
    FILES = [f"tests/python/{group}/test_{name}.py" for group in ("b", "a") for name in "zyxwvu"]

    def test_every_file_falls_to_exactly_one_shard_round_robin_by_path(self):
        for count in range(1, len(self.FILES) + 2):
            with self.subTest(count=count):
                shards = [runner.shard(self.FILES, index, count) for index in range(1, count + 1)]
                every = [path for files in shards for path in files]
                self.assertEqual(sorted(every), sorted(self.FILES), "the union is every file, each once")
                self.assertEqual(len(every), len(set(every)))
        ordered = sorted(self.FILES)
        self.assertEqual(runner.shard(self.FILES, 2, 3), ordered[1::3])

    def test_a_shard_must_name_one_of_n(self):
        for bad in ("0/3", "4/3", "1/0", "3", "a/b", "-1/2", ""):
            with self.subTest(shard=bad), mock.patch.object(runner.sys, "stderr", io.StringIO()) as err:
                with self.assertRaises(SystemExit) as refused:
                    runner.main(["--top", str(REPO_ROOT), f"--shard={bad}", "test_x.py"])
                self.assertEqual(refused.exception.code, 2)
                self.assertIn("--shard: wants I/N, a shard I of N with 1 <= I <= N", err.getvalue())

    def test_only_the_shard_s_files_run_and_an_empty_shard_passes_saying_so(self):
        with mock.patch.object(runner, "run_files", return_value=0) as run, \
                mock.patch.object(runner.sys, "stderr", io.StringIO()) as err:
            self.assertEqual(runner.main(["--top", str(REPO_ROOT), "--shard", "2/2", "c.py", "a.py", "b.py"]), 0)
            self.assertEqual(run.call_args.args[0], ["b.py"])
            self.assertIn("shard 2/2: 1 of the 3 files given\n", err.getvalue())
            run.reset_mock()
            self.assertEqual(runner.main(["--top", str(REPO_ROOT), "--shard", "3/3", "a.py", "b.py"]), 0)
        run.assert_not_called()
        self.assertIn("shard 3/3: none of the 2 files given is this shard's; nothing to run (OK)\n", err.getvalue())


if __name__ == "__main__":
    unittest.main()
