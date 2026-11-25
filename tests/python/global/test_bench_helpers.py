"""The manual benchmarks' pure helpers (``scripts/bench``): AGENTS.md runs only those in a test
runner, never a batch. ``dfm_bench.py``'s choice of files and its table.
Nothing here builds, serves or draws: the fixtures are files in a temporary folder and rows
written by hand."""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

from tests.python.support.paths import REPO_ROOT
from tests.python.support.tmp_root import temporary_directory

BENCH = REPO_ROOT / "scripts" / "bench"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"bench_{name}", BENCH / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


dfm_bench = _load("dfm_bench")


class DfmTableTest(unittest.TestCase):
    """``dfm_bench.py``'s table: per process, the parts, their seconds, what raised and the rules that fail most."""

    def test_the_table_counts_each_process(self):
        rows = [{"process": "cnc", "seconds": 1.0, "failed_rules": ["cnc.corner"], "unmeasured": []},
                {"process": "cnc", "seconds": 3.0, "failed_rules": ["cnc.corner", "cnc.wall"], "unmeasured": ["holes"]},
                {"process": "cnc", "seconds": 0.5, "error": "boom"},
                {"process": "printing", "seconds": 2.0, "failed_rules": [], "unmeasured": []}]
        table = dfm_bench.summarize(rows).splitlines()
        self.assertEqual(len(table), 4)
        self.assertIn("| cnc | 3 | 2.0 | 3.0 | 3.0 | 1 | 1 | cnc.corner (2), cnc.wall (1) |", table)
        self.assertIn("| printing | 1 | 2.0 | 2.0 | 2.0 | 0 | 0 | - |", table)

    def test_files_are_taken_smallest_first(self):
        with temporary_directory(prefix="dfm-bench-") as folder:
            root = Path(folder)
            for name, size in (("b.step", 30), ("a.stp", 10), ("c.STEP", 20), ("d.txt", 1)):
                (root / name).write_bytes(b"x" * size)
            self.assertEqual([path.name for path in dfm_bench.files([root], 2, 1.0)], ["a.stp", "c.STEP"])
            self.assertEqual([path.name for path in dfm_bench.files([root], 2, 1.0, spread=True)], ["a.stp", "b.step"])


if __name__ == "__main__":
    unittest.main()
