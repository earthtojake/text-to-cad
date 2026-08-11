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

import subprocess
import sys
import unittest
from pathlib import Path

from tests.python.support.paths import repo_path

REPO = Path(repo_path("."))
PART = "models/step/parts/cylindrical_spacer_sleeve.step.py"
ROBOT = "models/robots/tom/tom.urdf"


def run(skill: str, tool: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(REPO / "skills" / skill / "scripts" / tool), *args],
        cwd=REPO, capture_output=True, text=True, check=False,
    )


class StdoutIsTheResultTests(unittest.TestCase):
    def test_gen_answers_on_stdout(self):
        result = run("cad", "gen", PART)
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
        result = run("cad", "gen", "--json", PART)
        self.assertEqual(0, result.returncode, result.stderr)
        lines = [line for line in result.stdout.splitlines() if line.strip()]
        self.assertEqual(1, len(lines))
        self.assertNotIn("\n  ", result.stdout, "payloads on stdout are compact")

    def test_validate_answers_on_stdout(self):
        result = run("urdf", "validate", ROBOT)
        self.assertTrue(result.stdout.strip())


class StderrIsEverythingElseTests(unittest.TestCase):
    def test_narration_never_lands_on_stdout(self):
        # The logger prefixes every line it owns. Finding one on stdout means narration and
        # result have been mixed, and `2>/dev/null` no longer yields something parseable.
        for skill, tool in (("cad", "gen"), ("dxf", "gen")):
            with self.subTest(skill=skill):
                target = PART if skill == "cad" else "models/drawings/dxf/gasket_plate.dxf.py"
                result = run(skill, tool, target)
                self.assertNotIn("[scripts/", result.stdout)

    def test_a_result_survives_discarding_stderr(self):
        result = run("cad", "gen", "--json", PART)
        import json

        payload = json.loads(result.stdout.strip())
        self.assertTrue(payload["ok"])
        self.assertIn("outcome", payload)


if __name__ == "__main__":
    unittest.main()
