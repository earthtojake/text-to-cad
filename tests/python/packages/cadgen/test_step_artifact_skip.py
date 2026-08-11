"""``cadgen.step_artifact`` must short-circuit on an already-current package.

This is the module the CAD Viewer's build POST runs, and it is a DIFFERENT path from
``cadgen.generation`` (covered by test_concurrent_generation.py). Its "already current"
fast path was dead: ``_current_artifact_for_spec`` routed a component-GLB package
DIRECTORY through ``validate_step_topology_artifact``, which gates on ``.is_file()`` and
therefore always raised ``missing_glb``. Every viewer-triggered build re-ran ``gen_step()``.

The generator counts its own invocations by appending to a file, so "was the generator
re-run?" is measured rather than inferred from timing.
"""

from __future__ import annotations

import json
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

# Appends one line per gen_step() call, so the test can count real generator runs.
COUNTING_GENERATOR = """from pathlib import Path

from build123d import Box


def gen_step():
    Path(__file__).with_name("gen_calls.log").open("a").write("call\\n")
    return Box(12.0, 8.0, 4.0)
"""


class StepArtifactSkipTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="cadskip-")
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.generator = self.root / "widget.step.py"
        self.generator.write_text(COUNTING_GENERATOR)
        self.calls = self.root / "gen_calls.log"

    def _build(self, *extra):
        """Run the module exactly as viewer/server_py/backend.py does."""
        proc = subprocess.run(
            [
                sys.executable, "-m", "cadgen.step_artifact",
                "--repo-root", str(self.root),
                "--step", str(self.root / "widget.step"),
                "--source-path", str(self.generator),
                *extra,
            ],
            cwd=str(self.root),
            env={"PYTHONPATH": _CADGEN_SRC, "PATH": "/usr/bin:/bin"},
            capture_output=True,
            text=True,
            timeout=600,
        )
        self.assertEqual(0, proc.returncode, f"build failed:\n{proc.stdout}\n{proc.stderr}")
        return json.loads(proc.stdout.strip().splitlines()[-1])

    def _generator_runs(self):
        return len(self.calls.read_text().splitlines()) if self.calls.is_file() else 0

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
            "gen_step() re-ran on an unchanged package -- the fast path is dead again",
        )

    def test_force_rebuilds_and_reruns_the_generator(self):
        self._build()
        forced = self._build("--force")
        self.assertFalse(forced.get("skipped"), "--force must not short-circuit")
        self.assertEqual(2, self._generator_runs())

    def test_edited_generator_invalidates_the_package(self):
        self._build()
        self.generator.write_text(COUNTING_GENERATOR.replace("12.0", "14.0"))
        rebuilt = self._build()
        self.assertFalse(rebuilt.get("skipped"), "an edited generator must rebuild")
        self.assertEqual(2, self._generator_runs())

    def test_a_queued_producer_finds_the_package_current_and_skips(self):
        """Two contenders on a COLD package must run gen_step() exactly once between them.

        This is the concurrent case the pre-lock fast path structurally cannot cover: it
        runs before the peer's build exists, so the loser used to wait for the lock and
        then redo the entire generator+mesh the winner had just finished. artifact_build
        re-evaluates is_current() under the lock, which turns the loser into a no-op.
        """
        script = [
            sys.executable, "-m", "cadgen.step_artifact",
            "--repo-root", str(self.root),
            "--step", str(self.root / "widget.step"),
            "--source-path", str(self.generator),
        ]
        env = {"PYTHONPATH": _CADGEN_SRC, "PATH": "/usr/bin:/bin"}
        first = subprocess.Popen(script, cwd=str(self.root), env=env,
                                 stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        time.sleep(0.3)
        second = subprocess.Popen(script, cwd=str(self.root), env=env,
                                  stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        outs = []
        for proc in (first, second):
            out, _ = proc.communicate(timeout=600)
            self.assertEqual(0, proc.returncode, f"a contender failed:\n{out}")
            outs.append(out)

        self.assertEqual(
            1,
            self._generator_runs(),
            f"gen_step() ran {self._generator_runs()}x across two contenders; the loser "
            f"redid the winner's work:\n{outs}",
        )
        payloads = [json.loads(out.strip().splitlines()[-1]) for out in outs]
        self.assertEqual(
            1,
            sum(1 for p in payloads if p.get("skipped")),
            f"exactly one contender must short-circuit: {payloads}",
        )

    def tearDown(self):
        shutil.rmtree(self.root / "__cadgen__", ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
