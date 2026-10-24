"""One contract, every CLI: stdout is the RESULT, stderr is everything else.

An agent reads these two streams apart. `2>/dev/null` must leave a parseable answer and
`>/dev/null` must leave a readable log -- which only works if no CLI mixes them: a model
script prints each model's report on stdout and its build's log on stderr, and a command's
`--json` is its answer, one compact line.

These run the real CLIs against real fixtures. That is slower than inspecting source, and
it is the only way to catch a stream that drifts through a library three layers down.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import sys
import unittest
from pathlib import Path

from tests.python.support.paths import repo_path

REPO = Path(repo_path("."))

# The fixtures are the test's own: a box part and a rectangle drawing written into a
# temporary project, so the run reads nothing under models/ and leaves nothing there.
PART_SOURCE = """\
from cadgen.engine import step
import build123d as bd


@step(out="../STEP/part.step")
def part():
    return bd.Box(10.0, 6.0, 2.0)

if __name__ == "__main__":
    part()
"""

DRAWING_SOURCE = """\
from cadgen.engine import dxf
import build123d as bd


@dxf(out="../DXF/plate.dxf")
def plate():
    return bd.Rectangle(30.0, 20.0)

if __name__ == "__main__":
    plate()
"""

_PROJECT: tempfile.TemporaryDirectory | None = None
PART = ""
DRAWING = ""
ENGINE = ""


def setUpModule() -> None:
    global _PROJECT, PART, DRAWING, ENGINE
    _PROJECT = tempfile.TemporaryDirectory(prefix="stream-contract-")
    root = Path(_PROJECT.name)
    (root / "src").mkdir()
    (root / "src" / "part.py").write_text(PART_SOURCE, encoding="utf-8")
    (root / "src" / "plate.py").write_text(DRAWING_SOURCE, encoding="utf-8")
    PART = str(root / "src" / "part.py")
    DRAWING = str(root / "src" / "plate.py")
    # The builds below run on an engine daemon of this module's own, never the developer's.
    ENGINE = str(root / "engine")


def tearDownModule() -> None:
    if ENGINE:
        subprocess.run([sys.executable, "-P", "-c", "from cadgen.engine import api; api.stop()"],
                       env=_env(), capture_output=True, check=False, timeout=120)
    if _PROJECT is not None:
        _PROJECT.cleanup()


def _env() -> dict[str, str]:
    # Point the child at THIS checkout's source so the contract is tested against the code
    # under review, not against whatever cadgen the interpreter happens to have (in a
    # worktree, that is another branch's).
    env = dict(os.environ)
    own_cadgen = str(REPO / "packages" / "cadgen" / "src")
    env["PYTHONPATH"] = os.pathsep.join([own_cadgen, *([env["PYTHONPATH"]] if env.get("PYTHONPATH") else [])])
    env["CADGEN_ENGINE_DIR"] = ENGINE
    return env


# A self-contained robot: primitive visuals, no mesh files, so the test needs nothing
# generated or LFS-fetched in the checkout.
ROBOT_URDF = """<?xml version="1.0"?>
<robot name="stream_contract">
  <link name="base"><visual><geometry><box size="0.1 0.1 0.02"/></geometry></visual></link>
  <link name="arm"><visual><geometry><cylinder radius="0.01" length="0.1"/></geometry></visual></link>
  <joint name="shoulder" type="revolute">
    <parent link="base"/><child link="arm"/>
    <origin xyz="0 0 0.01"/><axis xyz="0 0 1"/>
    <limit lower="-1.57" upper="1.57" effort="1" velocity="1"/>
  </joint>
</robot>
"""


def run(*args: str) -> subprocess.CompletedProcess:
    # Every verb lives behind the one cadgen front door.
    return subprocess.run([sys.executable, "-m", "cadgen.cli", *args], cwd=REPO, capture_output=True, text=True,
                          check=False, env=_env())


def run_script(script: str) -> subprocess.CompletedProcess:
    # The model script IS the entrypoint, with no options (it is Python); same stream contract.
    return subprocess.run([sys.executable, script], cwd=REPO, capture_output=True, text=True, check=False, env=_env())


def run_export_json() -> subprocess.CompletedProcess:
    # A command answering as JSON: the part's STEP, which its script writes, exported to a GLB.
    built = run_script(PART)
    assert built.returncode == 0, built.stderr
    step = Path(PART).parent.parent / "STEP" / "part.step"
    return run("export", str(step), str(step.with_suffix(".glb")), "--json")


class StdoutIsTheResultTests(unittest.TestCase):
    def test_a_model_script_answers_on_stdout(self):
        result = run_script(PART)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertTrue(result.stdout.strip(),
                        "the script printed nothing to stdout; an agent reading the streams apart gets no answer")
        # Each model's report leads with what happened to it: built, or taken from its file.
        self.assertIn(result.stdout.split()[0], {"built", "took"}, result.stdout)
        self.assertIn("part.py::part", result.stdout)

    def test_a_json_answer_is_one_compact_line(self):
        result = run_export_json()
        self.assertEqual(0, result.returncode, result.stderr)
        lines = [line for line in result.stdout.splitlines() if line.strip()]
        self.assertEqual(1, len(lines), result.stdout)
        self.assertNotIn("\n  ", result.stdout, "payloads on stdout are compact")

    def test_validate_answers_on_stdout(self):
        with tempfile.TemporaryDirectory() as tmp:
            robot = Path(tmp) / "stream_contract.urdf"
            robot.write_text(ROBOT_URDF, encoding="utf-8")
            result = run("urdf", "validate", str(robot))
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertTrue(result.stdout.strip())


class StderrIsEverythingElseTests(unittest.TestCase):
    def test_narration_never_lands_on_stdout(self):
        # Narration on stdout means narration and result have been mixed, and `2>/dev/null` no
        # longer yields something parseable. The model script is the build entrypoint for a STEP
        # and a DXF alike.
        for kind, target in (("step", PART), ("dxf", DRAWING)):
            with self.subTest(kind=kind):
                result = run_script(target)
                self.assertEqual(0, result.returncode, result.stderr)
                for line in result.stdout.splitlines():
                    self.assertFalse(line.startswith(("[", "Traceback")), f"narration on stdout: {line!r}")

    def test_a_result_survives_discarding_stderr(self):
        result = run_export_json()
        payload = json.loads(result.stdout.strip())
        self.assertTrue(payload["ok"])
        self.assertIn("files", payload)


if __name__ == "__main__":
    unittest.main()
