"""Several models in one file, and what a top-level call hands back.

A model's identity is ``script::function``. A file holding one model is named by
its path alone everywhere; a file holding several gives each its own record,
output and job, while all of them share the file's closure. Outside a build a
call returns the model's geometry.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.python.support.paths import REPO_ROOT, add_repo_path
from tests.python.support.tmp_root import temporary_directory

add_repo_path("packages/cadgen/src")

PYTHON = sys.executable

FAMILY = """\
from cadgen import build123d as bd
from cadgen import step


@step
def bracket_left():
    return bd.Box(10, 4, 2)


@step
def bracket_right():
    return bd.Box(10, 4, 3)


if __name__ == "__main__":
    bracket_left()
    bracket_right()
"""

PAIR = """\
from cadgen import build123d as bd
from cadgen import step
from family import bracket_left


@step
def pair():
    return bd.Compound(children=[bracket_left(), bd.Pos(20, 0, 0) * bracket_left()], label="pair")


if __name__ == "__main__":
    pair()
"""

RETURNS = """\
import sys
sys.path.insert(0, %r)
from family import bracket_left

shape = bracket_left()
size = shape.bounding_box().size
print(type(shape).__name__, round(size.X, 3), round(size.Y, 3), round(size.Z, 3))
"""


class ModelsPerFile(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = temporary_directory(prefix="cadgen-models-per-file-")
        self.root = Path(self._tmp.name)
        self.src = self.root / "src"
        self.src.mkdir()
        self.store = self.root / "store"
        (self.src / "family.py").write_text(FAMILY, encoding="utf-8")
        (self.src / "pair.py").write_text(PAIR, encoding="utf-8")
        self.env = dict(os.environ)
        self.env.update(
            {
                "CADGEN_DAEMON": "0",
                "CADGEN_CACHE_DIR": str(self.store),
                "PYTHONPATH": str(REPO_ROOT / "packages/cadgen/src"),
            }
        )

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def run_py(self, *argv: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
        completed = subprocess.run(
            [PYTHON, *argv], cwd=str(cwd or self.src), env=self.env, capture_output=True, text=True, timeout=600
        )
        self.assertEqual(completed.returncode, 0, completed.stderr[-3000:])
        return completed

    def cli(self, *argv: str, cwd: Path | None = None) -> str:
        completed = subprocess.run(
            [PYTHON, "-m", "cadgen.cli", *argv],
            cwd=str(cwd or self.src), env=self.env, capture_output=True, text=True, timeout=600,
        )
        return completed.stdout + completed.stderr

    def test_two_models_in_one_file_are_two_records_and_two_outputs(self) -> None:
        out = self.run_py("family.py").stdout
        self.assertIn("built bracket_left.step", out)
        self.assertIn("built bracket_right.step", out)
        self.assertTrue((self.src / "bracket_left.step").is_file())
        self.assertTrue((self.src / "bracket_right.step").is_file())
        records = list((self.store / "index/model").iterdir())
        self.assertEqual(len(records), 2)
        models = sorted(json.loads(p.read_text(encoding="utf-8"))["model"] for p in records)
        self.assertEqual(
            models,
            [f"{(self.src / 'family.py').resolve()}::bracket_left", f"{(self.src / 'family.py').resolve()}::bracket_right"],
        )
        # A second run finds both current.
        rerun = self.run_py("family.py").stdout
        self.assertIn("current bracket_left.step", rerun)
        self.assertIn("current bracket_right.step", rerun)

    def test_store_why_names_every_model_of_the_file_and_accepts_one(self) -> None:
        self.run_py("family.py")
        both = self.cli("store", "why", "family.py")
        self.assertIn("family.py::bracket_left", both)
        self.assertIn("family.py::bracket_right", both)
        self.assertEqual(both.count("verdict current"), 2)
        one = self.cli("store", "why", "family.py::bracket_right")
        self.assertIn("family.py::bracket_right", one)
        self.assertNotIn("bracket_left", one)
        self.assertEqual(one.count("verdict"), 1)

    def test_a_parent_pins_only_the_model_it_called(self) -> None:
        self.run_py("pair.py")
        from cadgen.store.records import read_record

        previous = os.environ.get("CADGEN_CACHE_DIR")
        os.environ["CADGEN_CACHE_DIR"] = str(self.store)
        try:
            record = read_record(f"{(self.src / 'pair.py').resolve()}::pair")
            self.assertIsNotNone(record)
            children = {c["model"] for c in record["children"]}
            self.assertEqual(children, {f"{(self.src / 'family.py').resolve()}::bracket_left"})
            # Only the called model was built beneath the parent.
            self.assertTrue((self.src / "bracket_left.step").is_file())
            self.assertFalse((self.src / "bracket_right.step").exists())
        finally:
            if previous is None:
                os.environ.pop("CADGEN_CACHE_DIR", None)
            else:
                os.environ["CADGEN_CACHE_DIR"] = previous

    def test_models_sharing_a_file_share_its_closure(self) -> None:
        self.run_py("family.py")
        path = self.src / "family.py"
        path.write_text(path.read_text(encoding="utf-8").replace("Box(10, 4, 3)", "Box(10, 4, 5)"), encoding="utf-8")
        why = self.cli("store", "why", "family.py::bracket_left")
        self.assertIn("STALE", why, "an edit to a sibling model's body is an edit to the shared file")
        rerun = self.run_py("family.py").stdout
        self.assertIn("built bracket_left.step", rerun)
        self.assertIn("built bracket_right.step", rerun)

    def test_a_top_level_call_returns_the_geometry(self) -> None:
        self.run_py("family.py")
        script = self.root / "read_it.py"
        script.write_text(RETURNS % str(self.src), encoding="utf-8")
        out = self.run_py(str(script), cwd=self.root).stdout.strip().splitlines()[-1]
        self.assertEqual(out, "Compound 10.0 4.0 2.0")

    def test_a_file_holding_one_model_is_named_by_its_path(self) -> None:
        single = self.src / "solo.py"
        single.write_text(
            "from cadgen import build123d as bd\nfrom cadgen import step\n\n\n@step\ndef solo():\n"
            "    return bd.Box(1, 2, 3)\n\n\nif __name__ == '__main__':\n    solo()\n",
            encoding="utf-8",
        )
        out = self.run_py("solo.py", cwd=self.src)
        events = [json.loads(line) for line in out.stderr.splitlines() if line.startswith("{")]
        self.assertTrue(events)
        self.assertTrue(all(e["model"].endswith("solo.py") for e in events), events[0])
        why = self.cli("store", "why", "solo.py")
        self.assertIn("solo.py::solo", why)
        self.assertEqual(why.count("verdict"), 1)


if __name__ == "__main__":
    unittest.main()
