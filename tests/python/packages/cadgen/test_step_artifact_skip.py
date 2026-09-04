"""``cadgen.step_artifact_cli`` must short-circuit on an already-current package.

This is the module the CAD Viewer's build POST runs, and it is a DIFFERENT path from
``cadgen.generation`` (covered by test_concurrent_generation.py). Its "already current"
fast path was dead: ``_current_artifact_for_spec`` routed a component-GLB package
DIRECTORY through ``validate_step_topology_artifact``, which gates on ``.is_file()`` and
therefore always raised ``missing_glb``. Every viewer-triggered build re-ran ``model()``.

The generator counts its own invocations by appending to a file, so "was the generator
re-run?" is measured rather than inferred from timing.
"""

from __future__ import annotations

import json
import contextlib
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")

_CADGEN_SRC = str(Path(__file__).resolve().parents[4] / "packages" / "cadgen" / "src")


def _child_env() -> dict[str, str]:
    """The environment the CLI actually runs under: inherited, with PYTHONPATH overlaid.

    This used to be a curated ``{"PYTHONPATH": ..., "PATH": "/usr/bin:/bin"}``, which was
    never what it claimed to model -- ``viewer/server_py`` spawns these from
    ``dict(os.environ)`` -- and on Windows it was fatal rather than merely inaccurate.
    Dropping ``SystemRoot`` breaks Winsock initialisation in the child, so ``import asyncio``
    (reached from build123d through IPython) died with WinError 10106 before the generator
    ran at all.
    """
    env = dict(os.environ)
    env["PYTHONPATH"] = _CADGEN_SRC
    return env

# Appends one line per model() call, so the test can count real generator runs.
COUNTING_GENERATOR = """from pathlib import Path

from build123d import Box


from cadgen import step
@step
def model():
    Path(__file__).with_name("gen_calls.log").open("a").write("call\\n")
    return Box(12.0, 8.0, 4.0)


if __name__ == "__main__":
    model()
"""


class StepArtifactSkipTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="cadskip-")
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.generator = self.root / "widget.py"
        self.generator.write_text(COUNTING_GENERATOR, encoding="utf-8")
        self.calls = self.root / "gen_calls.log"

    def _build(self, *extra):
        """Run the module exactly as the warm daemon dispatch does."""
        proc = subprocess.run(
            [
                sys.executable, "-m", "cadgen.step_artifact_cli",
                "--repo-root", str(self.root),
                "--step", str(self.root / "widget.step"),
                "--source-path", str(self.generator),
                *extra,
            ],
            cwd=str(self.root),
            env=_child_env(),
            capture_output=True,
            text=True,
            timeout=600,
        )
        self.assertEqual(0, proc.returncode, f"build failed:\n{proc.stdout}\n{proc.stderr}")
        return json.loads(proc.stdout.strip().splitlines()[-1])

    def _generator_runs(self):
        return len(self.calls.read_text(encoding="utf-8").splitlines()) if self.calls.is_file() else 0

    def test_second_build_of_a_current_package_is_skipped(self):
        first = self._build()
        self.assertFalse(first.get("skipped"), "the first build must actually build")
        self.assertEqual(1, self._generator_runs())

        second = self._build()
        self.assertTrue(
            second.get("skipped"),
            f"an unchanged package must short-circuit, got: {second}",
        )
        self.assertEqual(
            1,
            self._generator_runs(),
            "model() re-ran on an unchanged package -- the fast path is dead again",
        )

    def test_force_rebuilds_and_reruns_the_generator(self):
        self._build()
        forced = self._build("--force")
        self.assertFalse(forced.get("skipped"), "--force must not short-circuit")
        self.assertEqual(2, self._generator_runs())

    def test_edited_generator_invalidates_the_package(self):
        self._build()
        self.generator.write_text(COUNTING_GENERATOR.replace("12.0", "14.0"), encoding="utf-8")
        rebuilt = self._build()
        self.assertFalse(rebuilt.get("skipped"), "an edited generator must rebuild")
        self.assertEqual(2, self._generator_runs())

    def test_two_contenders_on_a_cold_package_both_finish_and_the_result_is_current(self):
        """No lock: both contenders run (STORE.md §7). Whether the loser redoes the
        winner's work is timing -- its run re-checks the gate when it opens -- so what is
        asserted is what the publish rule guarantees: both succeed, the generator ran at
        most twice, and a third run finds the package current."""
        script = [
            sys.executable, "-m", "cadgen.step_artifact_cli",
            "--repo-root", str(self.root),
            "--step", str(self.root / "widget.step"),
            "--source-path", str(self.generator),
        ]
        env = _child_env()
        first = subprocess.Popen(script, cwd=str(self.root), env=env,
                                 stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        time.sleep(0.3)
        second = subprocess.Popen(script, cwd=str(self.root), env=env,
                                  stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        # Drain EVERY contender before asserting on any of them, and kill whatever
        # is left in a finally. The assertion used to sit inside this loop, so the
        # first non-zero contender abandoned the rest -- still running, still
        # holding this temp dir as their cwd, while addCleanup deleted it. On
        # Windows a process's cwd is opened without FILE_SHARE_DELETE, so the pin
        # lasts the child's whole lifetime and the cleanup fails with WinError 32,
        # stacking a misleading tempfile ERROR on top of the real failure. It also
        # threw away the other contenders' output -- in a test about which
        # contender built and which skipped, the one thing worth reading.
        contenders = (first, second)
        drained = []
        try:
            for proc in contenders:
                out, _ = proc.communicate(timeout=600)
                drained.append((proc.returncode, out))
        finally:
            for proc in contenders:
                if proc.poll() is None:
                    proc.kill()
                    with contextlib.suppress(OSError):
                        proc.wait(timeout=30)
        for code, out in drained:
            self.assertEqual(0, code, f"a contender failed:\n{out}")
        outs = [out for _code, out in drained]

        self.assertIn(self._generator_runs(), (1, 2), f"model() ran {self._generator_runs()}x:\n{outs}")
        payloads = [json.loads(out.strip().splitlines()[-1]) for out in outs]
        self.assertTrue(all(p.get("ok") for p in payloads), payloads)
        runs = self._generator_runs()
        third = self._build()
        self.assertTrue(third.get("skipped"), f"a third run must find the package current: {third}")
        self.assertEqual(runs, self._generator_runs(), "the third run re-ran the generator")

    def tearDown(self):
        shutil.rmtree(self.root / "__cadgen__", ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
