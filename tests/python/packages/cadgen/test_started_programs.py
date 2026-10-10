"""A model that starts a program is warned about, root or child, warm or cold.

The file trace sees what the build's own process opens; a program the model
starts reads files no trace sees, so editing them would never rebuild the model.
The build cannot make those files inputs, so it says so, once per model built:
the root prints the warning for itself and for every child, whose own output is
dropped when it succeeds. A program cadgen starts for the build (a child's
worker) is not the model's.
"""

from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path

from tests.python.support.paths import add_repo_path
from tests.python.support.tmp_root import generated_cad_directory
from tests.python.support.warm_daemon import served, warm_entries

CADGEN_SRC = add_repo_path("packages/cadgen/src")

BOLT = '''import subprocess
import sys

from cadgen import build123d as bd
from cadgen import step


@step
def bolt():
    subprocess.run([sys.executable, "-c", "pass"], check=True)
    return bd.Cylinder(2, 10)
'''

FRAME = '''import os

from cadgen import build123d as bd
from cadgen import step
from bolt import bolt


@step
def frame():
    os.system("exit 0")
    return bd.Compound([bd.Box(20, 20, 2), bd.Pos(0, 0, 6) * bolt()])


if __name__ == "__main__":
    frame()
'''

WARNING = "[cadgen] warning: {model} started {program}; files it reads are not inputs, so editing them will not rebuild it"


class StartedPrograms(unittest.TestCase):
    def test_a_program_is_named_by_what_runs_not_by_the_shell_that_runs_it(self) -> None:
        from cadgen._internal import filetrace

        with filetrace.capture() as trace:
            subprocess.run([sys.executable, "-c", "pass"], check=True)
            subprocess.run("exit 0", shell=True, check=True)
            subprocess.run([sys.executable, "-c", "pass"], check=True)  # once, however often
        self.assertEqual(trace.programs, [os.path.basename(sys.executable), "exit"])

    def _warnings(self, *, warm: bool) -> list[str]:
        scratch = generated_cad_directory(prefix="started-programs-")
        self.addCleanup(scratch.cleanup)
        project = Path(scratch.name).resolve()
        (project / "bolt.py").write_text(BOLT, encoding="utf-8")
        (project / "frame.py").write_text(FRAME, encoding="utf-8")
        environment = {**os.environ, "CADGEN_CACHE_DIR": str(project / "store"), "PYTHONPATH": str(CADGEN_SRC),
                       **(warm_entries() if warm else {"CADGEN_DAEMON": "0"})}
        completed = subprocess.run([sys.executable, "frame.py"], cwd=str(project), env=environment,
                                   capture_output=True, text=True, timeout=600)
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        if warm:
            self.assertTrue(served(project.name), "the warm run fell back to cold")
        return sorted(line for line in completed.stderr.splitlines() if " started " in line)

    def _expected(self) -> list[str]:
        return sorted([WARNING.format(model="frame", program="exit"),
                       WARNING.format(model="bolt", program=os.path.basename(sys.executable))])

    def test_the_root_and_a_transient_child_are_each_warned_about_once(self) -> None:
        self.assertEqual(self._warnings(warm=False), self._expected())

    def test_the_root_and_a_daemon_child_are_each_warned_about_once(self) -> None:
        self.assertEqual(self._warnings(warm=True), self._expected())


if __name__ == "__main__":
    unittest.main()
