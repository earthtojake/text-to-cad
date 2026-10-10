"""An environment variable a model's own code reads is an input, warm or cold.

A model that reads ``os.environ["SIZE"]`` builds a different part for a different
SIZE, and used to stay "current" when SIZE changed: plausible-wrong output at exit
0. Its closure now holds the variable with the value it read (a digest, never the
value), so a changed value rebuilds it, while an unchanged one -- or a change to a
variable it never read -- leaves it current. Under the warm daemon a job runs in
its caller's environment, not the daemon's, so the same holds there. What cadgen,
the standard library or an installed package reads for itself is no input.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import sysconfig
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support.paths import add_repo_path
from tests.python.support.tmp_root import generated_cad_directory
from tests.python.support.warm_daemon import served, warm_entries

CADGEN_SRC = add_repo_path("packages/cadgen/src")

MODEL = '''import os

from cadgen import build123d as bd
from cadgen import step


@step
def plate():
    size = float(os.environ["SIZE"])
    print(f"read SIZE={size:g}")
    return bd.Box(size, 10, 2)


if __name__ == "__main__":
    plate()
'''


class ReadsTheModelMakes(unittest.TestCase):
    def test_the_models_own_reads_are_inputs_and_nobody_elses_are(self) -> None:
        from cadgen._internal import filetrace

        # An installed package's code, as the trace sees it: a frame from a file in
        # site-packages.
        library: dict = {}
        exec(compile("import os\n\ndef configure():\n    return os.environ.get('LIBRARY_KNOB')\n",
                     str(Path(sysconfig.get_paths()["purelib"]) / "a_library.py"), "exec"), library)
        with mock.patch.dict(os.environ, {"SIZE": "10", "COLUMNS": "80", "LIBRARY_KNOB": "1"}):
            for name in ("DEPTH", "WIDTH", "MINE"):
                os.environ.pop(name, None)
            with filetrace.capture() as trace:
                os.environ["SIZE"]
                os.getenv("DEPTH")
                "WIDTH" in os.environ
                shutil.get_terminal_size()  # the standard library reads COLUMNS for itself
                library["configure"]()
                dict(os.environ), os.environ.copy()  # a copy of all of it reads no one variable
                os.environ["MINE"] = "1"
                os.environ["MINE"]  # the build's own
        self.assertEqual(trace.environment, {"SIZE": "10", "DEPTH": None, "WIDTH": None})


class EnvironmentInputs(unittest.TestCase):
    def setUp(self) -> None:
        scratch = generated_cad_directory(prefix="environment-inputs-")
        self.addCleanup(scratch.cleanup)
        self.project = Path(scratch.name).resolve()
        (self.project / "plate.py").write_text(MODEL, encoding="utf-8")
        self.environment = {**os.environ, "CADGEN_CACHE_DIR": str(self.project / "store"),
                            "PYTHONPATH": str(CADGEN_SRC)}
        self.environment.pop("UNRELATED", None)

    def _run(self, argv: list[str], *, warm: bool, **variables: str) -> subprocess.CompletedProcess:
        environment = {**self.environment, **(warm_entries() if warm else {"CADGEN_DAEMON": "0"}), **variables}
        return subprocess.run([sys.executable, *argv], cwd=str(self.project), env=environment,
                              capture_output=True, text=True, timeout=600)

    def _build(self, *, warm: bool, **variables: str) -> tuple[str, str]:
        completed = self._run(["plate.py", "--json"], warm=warm, **variables)
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        return json.loads(completed.stdout.strip().splitlines()[-1])["outcome"], completed.stdout

    def _sizes_rebuild_it_and_nothing_else_does(self, *, warm: bool) -> None:
        outcome, printed = self._build(warm=warm, SIZE="10")
        self.assertEqual((outcome, "read SIZE=10" in printed), ("built", True))
        self.assertEqual(self._build(warm=warm, SIZE="10")[0], "current")
        self.assertEqual(self._build(warm=warm, SIZE="10", UNRELATED="1")[0], "current",
                         "a variable the model never read is no input")
        outcome, printed = self._build(warm=warm, SIZE="20")
        self.assertEqual((outcome, "read SIZE=20" in printed), ("built", True), printed)
        why = self._run(["-m", "cadgen.cli", "store", "why", "plate.py"], warm=False, SIZE="30")
        self.assertEqual(why.returncode, 1, why.stdout + why.stderr)
        self.assertIn("environment variable SIZE changed", why.stdout)

    def test_a_variable_the_model_reads_is_an_input(self) -> None:
        self._sizes_rebuild_it_and_nothing_else_does(warm=False)
        from cadgen.store.records import read_record

        with mock.patch.dict(os.environ, {"CADGEN_CACHE_DIR": self.environment["CADGEN_CACHE_DIR"]}):
            files = read_record(self.project / "plate.py")["closure"]["files"]
        # cadgen, the standard library and the kernel read many variables as it builds.
        self.assertEqual([entry for entry in files if entry.startswith("<environment ")], ["<environment SIZE>"])

    def test_a_warm_job_runs_in_its_callers_environment(self) -> None:
        # The first run starts the daemon with SIZE=10 in its environment; the run with
        # SIZE=20 must build what its caller asked for.
        self._sizes_rebuild_it_and_nothing_else_does(warm=True)
        self.assertTrue(served(self.project.name), "the warm runs fell back to cold")


if __name__ == "__main__":
    unittest.main()
