"""One contract, every CLI: stdout is the RESULT, stderr is everything else.

An agent reads these two streams apart. `2>/dev/null` must leave a parseable answer and
`>/dev/null` must leave a readable log -- which only works if no CLI mixes them. The rule
was already true in most places and false in one that mattered: `gen` printed nothing to
stdout at all, so a caller got an exit code and no answer, while export, snapshot, validate
and inspect all replied there.

These run the real CLIs against real fixtures. That is slower than inspecting source, and
it is the only way to catch a stream that drifts through a library three layers down.
"""

from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path

from tests.python.support.paths import repo_path

REPO = Path(repo_path("."))
PART = "models/examples/src/cylindrical_spacer_sleeve.py"
ROBOT = "models/juno/juno.urdf"


def run(*args: str) -> subprocess.CompletedProcess:
    # Skills are instruction-only; every verb lives behind the one cadgen front door.
    # Point the child at THIS checkout's source so the contract is tested against the
    # code under review, not against whatever cadgen the interpreter happens to have
    # (in a worktree, that is another branch's).
    env = dict(os.environ)
    own_cadgen = str(REPO / "packages" / "cadgen" / "src")
    env["PYTHONPATH"] = os.pathsep.join(
        [own_cadgen, *([env["PYTHONPATH"]] if env.get("PYTHONPATH") else [])]
    )
    return subprocess.run(
        [sys.executable, "-m", "cadgen.cli", *args],
        cwd=REPO, capture_output=True, text=True, check=False, env=env,
    )


def run_script(script: str, *args: str) -> subprocess.CompletedProcess:
    # Library-first: the model script IS the entrypoint; same stream contract
    # as every CLI. Cold keeps the child self-contained.
    env = dict(os.environ)
    own_cadgen = str(REPO / "packages" / "cadgen" / "src")
    env["PYTHONPATH"] = os.pathsep.join(
        [own_cadgen, *([env["PYTHONPATH"]] if env.get("PYTHONPATH") else [])]
    )
    env["CADGEN_DAEMON"] = "0"
    return subprocess.run(
        [sys.executable, str(REPO / script), *args],
        cwd=REPO, capture_output=True, text=True, check=False, env=env,
    )


def run_model(*args: str) -> subprocess.CompletedProcess:
    return run_script(PART, *args)


class StdoutIsTheResultTests(unittest.TestCase):
    def test_gen_answers_on_stdout(self):
        result = run_model()
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertTrue(
            result.stdout.strip(),
            "gen printed nothing to stdout; an agent reading the streams apart gets no answer",
        )
        # `<outcome> <package path>` -- parseable without JSON.
        outcome, _, path = result.stdout.strip().partition(" ")
        self.assertIn(outcome, {"built", "current", "skipped-peer"})
        self.assertTrue(path.strip())

    def test_gen_json_is_one_compact_line_per_target(self):
        result = run_model("--json")
        self.assertEqual(0, result.returncode, result.stderr)
        lines = [line for line in result.stdout.splitlines() if line.strip()]
        self.assertEqual(1, len(lines))
        self.assertNotIn("\n  ", result.stdout, "payloads on stdout are compact")

    def test_validate_answers_on_stdout(self):
        result = run("urdf", "validate", ROBOT)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertTrue(result.stdout.strip())


class StderrIsEverythingElseTests(unittest.TestCase):
    def test_narration_never_lands_on_stdout(self):
        # The logger prefixes every line it owns. Finding one on stdout means narration and
        # result have been mixed, and `2>/dev/null` no longer yields something parseable.
        # Library-first: the model script is the build entrypoint for STEP and DXF alike.
        for kind, target in (("step", PART), ("dxf", "models/drawings/src/gasket_plate.py")):
            with self.subTest(kind=kind):
                result = run_script(target)
                self.assertNotIn("[cadgen]", result.stdout)
                self.assertNotIn("[scripts/", result.stdout)

    def test_a_result_survives_discarding_stderr(self):
        result = run_model("--json")
        import json

        payload = json.loads(result.stdout.strip())
        self.assertTrue(payload["ok"])
        self.assertIn("outcome", payload)


if __name__ == "__main__":
    unittest.main()
