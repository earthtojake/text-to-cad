"""Concurrent builds of the same model must serialize AND deduplicate.

Real subprocesses running the real generator. Before the generation lock became a
POSIX advisory lock, all contenders built at once into the same package directory;
before the post-lock currency re-check, they serialized but each still redid the
full generator+mesh+emit the previous holder had just finished.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")

_REPO_ROOT = Path(__file__).resolve().parents[4]
_CADGEN_SRC = str(_REPO_ROOT / "packages" / "cadgen" / "src")
_GEN_CLI = _REPO_ROOT / "skills" / "cad" / "scripts" / "gen"

BOX_GENERATOR = """from build123d import Box


def gen_step():
    return Box(12.0, 8.0, 4.0)
"""

# Each contender runs the same in-process build the CLI runs.
_BUILDER = """
import sys
sys.path.insert(0, {src!r})
from cadgen.generation import generate_step_targets
raise SystemExit(generate_step_targets([{target!r}]))
"""


class ConcurrentGenerationTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="cadconc-")
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.generator = self.root / "widget.step.py"
        self.generator.write_text(BOX_GENERATOR)

    def _run_contenders(self, count):
        script = _BUILDER.format(src=_CADGEN_SRC, target=str(self.generator))
        procs = [
            subprocess.Popen(
                [sys.executable, "-c", script],
                cwd=str(self.root),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            for _ in range(count)
        ]
        outputs = []
        for proc in procs:
            out, _ = proc.communicate(timeout=600)
            self.assertEqual(0, proc.returncode, f"a concurrent build failed:\n{out}")
            outputs.append(out)
        return outputs

    def test_exactly_one_contender_builds_the_package(self):
        outputs = self._run_contenders(3)
        built = [out for out in outputs if "GLB/topology artifact" in out]
        skipped = [out for out in outputs if "concurrent run; skipped" in out]
        self.assertEqual(
            1, len(built), f"expected exactly one real build, got {len(built)}:\n{outputs}"
        )
        self.assertEqual(
            2, len(skipped), f"expected two deduped runs, got {len(skipped)}:\n{outputs}"
        )

    def test_package_is_intact_after_concurrent_builds(self):
        self._run_contenders(3)
        package = self.root / "__cadgen__" / "models" / "widget.step.py"
        descriptor = package / "assembly.json"
        self.assertTrue(descriptor.is_file(), "no descriptor after concurrent builds")
        # The viewer's freshness gate must accept the package the race produced.
        add_repo_path("viewer")
        from server_py.artifact import validate_step_freshness

        self.assertEqual(
            (True, None), validate_step_freshness(str(self.root), str(self.generator))
        )

    def test_second_run_after_completion_is_a_plain_no_op(self):
        self._run_contenders(1)
        outputs = self._run_contenders(1)
        # Not the concurrent-skip path — the ordinary pre-lock fast path.
        self.assertIn("is current; skipped recompose", outputs[0])

    def _package_dir(self):
        return self.root / "__cadgen__" / "models" / "widget.step.py"

    def _run_gen_cli(self, *extra):
        """The skill CLI itself, not the library call the other tests use: the flag under
        test is an argparse question, and `--lock-timeout` was documented in SKILL.md while
        the parser rejected it."""
        return subprocess.run(
            [sys.executable, str(_GEN_CLI), str(self.generator), *extra],
            cwd=str(self.root),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=600,
        )

    def test_lock_timeout_reports_the_peer_instead_of_waiting_for_it(self):
        from cadgen.coordination.lock import exclusive
        from cadgen.coordination.paths import write_lock_path

        # A REAL peer: this process holds the same advisory lock the CLI will ask for.
        with exclusive(write_lock_path(self._package_dir())) as held:
            self.assertIsNotNone(held, "the test never acquired the lock it means to hold")
            result = self._run_gen_cli("--lock-timeout", "0.25", "--json")

        self.assertEqual(0, result.returncode, f"contention is not a failure:\n{result.stderr}")
        payload = json.loads(result.stdout.strip())
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["contended"], "SKILL.md documents contended:true for this case")
        self.assertEqual("contended", payload["outcome"])
        self.assertIn("not waiting", result.stderr)
        # It declined to build, so it must not claim the peer's work either: no descriptor
        # was written by this run, and nothing reports as built.
        self.assertFalse((self._package_dir() / "assembly.json").exists())
        self.assertNotIn("built", payload["outcome"])

    def tearDown(self):
        shutil.rmtree(self.root / "__cadgen__", ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
