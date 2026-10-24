"""The manual benchmarks' pure helpers (``scripts/bench``): AGENTS.md runs only those in a test
runner, never a batch. ``corpus_bench.py``'s config check, a build step's row and the batch's
table; ``compare.py``'s JSONL reading, its check of the old engine's numbers and its table.
Nothing here builds, serves or draws: the fixtures are a file in a temporary folder and rows
written by hand."""

from __future__ import annotations

import importlib.util
import json
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


corpus_bench = _load("corpus_bench")
compare = _load("compare")


def model(**overrides):
    return {"name": "part", "root": "proj", "cwd": "src", "targets": ["part.py"], "xbf": "XBF/part.xbf",
            "edit": {"file": "src/part.py", "from": "WIDTH = 8.0", "to": "WIDTH = 9.0"}, **overrides}


SCRIPT = "from __future__ import annotations\nfrom cadgen import model\nWIDTH = 8.0\nDEPTH = 8.0\n\n\n@model\ndef part():\n    return WIDTH\n"


def step(model_name, name, **row):
    return {"kind": "step", "model": model_name, "step": name, "ok": True, **row}


class ConfigTest(unittest.TestCase):
    def test_the_committed_config_is_well_formed(self):
        # Its shape only: whether its edits occur once is the dry run's to say (no test reads the corpus).
        config = json.loads((BENCH / "corpus.json").read_text(encoding="utf-8"))
        self.assertEqual(corpus_bench.problems(config), [])

    def test_each_problem_is_named(self):
        with temporary_directory(prefix="bench-config-") as folder:
            root = Path(folder)
            (root / "proj" / "src").mkdir(parents=True)
            (root / "proj" / "src" / "part.py").write_text(SCRIPT, encoding="utf-8")
            (root / "proj" / "src" / "loose.py").write_text("WIDTH = 8.0\n", encoding="utf-8")
            self.assertEqual(corpus_bench.problems({"models": [model()]}, root), [])
            cases = {
                "part: a second model of this name": [model(), model()],
                "part: unknown key `target`": [model(target="part.py")],
                "part: `targets` is a list of `script.py` or `script.py::model`": [model(targets=["part"])],
                "part: `xbf` names an .xbf": [model(xbf="XBF/part.step")],
                "part: `root` is a relative path inside the repository": [model(root="/proj")],
                "part: the edit's `to` is its `from`": [model(edit={"file": "src/part.py", "from": "A", "to": "A"})],
                "part: no script gone.py in proj/src": [model(targets=["gone.py"])],
                "part: no STEP/imported: an input the build reads": [model(needs=["STEP/imported"])],
                "part: loose.py has no `@model` directly above `def loose(`": [
                    model(targets=["loose.py"], xbf="XBF/loose.xbf")],
                "part: the edit's `from` occurs 0 times in src/part.py": [
                    model(edit={"file": "src/part.py", "from": "HEIGHT", "to": "LENGTH"})],
                "part: the edit's `from` occurs 2 times in src/part.py": [
                    model(edit={"file": "src/part.py", "from": "= 8.0", "to": "= 9.0"})],
            }
            for expected, models in cases.items():
                with self.subTest(expected=expected):
                    found = corpus_bench.problems({"models": models}, root)
                    self.assertTrue(any(text.startswith(expected) for text in found), found)


class WorkCopyTest(unittest.TestCase):
    def test_the_work_copy_declares_the_xbf_its_stem_names(self):
        declared = corpus_bench.with_xbf(SCRIPT, "part", "../XBF/part.xbf")
        self.assertEqual(declared.splitlines()[1:3], ["from cadgen import model", corpus_bench.XBF_IMPORT])
        self.assertEqual(declared.splitlines()[-4:-2], ["@_corpus_bench_xbf(out='../XBF/part.xbf')", "@model"])
        self.assertIsNone(corpus_bench.with_xbf(SCRIPT, "other", "../XBF/other.xbf"))
        self.assertEqual(corpus_bench.declared_script(model(targets=["a.py", "b.py::part"])), "b.py")


class BuildRowTest(unittest.TestCase):
    def test_a_build_row_sums_every_model_its_targets_built(self):
        built = {"ok": True, "model": "a.py::a", "parts": 3, "timings": {"body": 1.5, "xbf": 0.25},
                 "memo": {"hits": 10, "misses": 4, "uncached": 1, "bodies_run": 1, "bodies_skipped": 2},
                 "cache": {"used": False, "reason": "no file yet"},
                 "files": {"/w/XBF/a.xbf": {"kind": "xbf", "written": True, "bytes": 2_000_000, "seconds": 0.25}},
                 "child_models": {"b.py::b": {"files": {"/w/XBF/b.xbf": {"kind": "xbf", "written": False,
                                                                          "bytes": 500, "seconds": 0.0}}}}}
        taken = {"ok": True, "model": "c.py::c", "timings": {"key": 0.1, "read": 0.2}, "bodies": {"c.py::c": "loaded"},
                 "memo": {"hits": 0, "misses": 0, "bodies_loaded": 1}, "cache": {"used": True, "from": "file"},
                 "files": {"/w/XBF/c.glb": {"kind": "glb", "written": False, "bytes": 100, "seconds": 0.0}}}
        answer = corpus_bench.driver_answer("a log line\n" + corpus_bench.MARK + json.dumps({"builds": [
            {"target": "a.py", "wall": 2.0, "fresh": True, "models": [built]},
            {"target": "c.py", "wall": 0.5, "fresh": False, "models": [taken]}]}) + "\n")
        row = corpus_bench.build_row(answer, "/w/XBF/a.xbf")
        self.assertTrue(row["ok"])
        self.assertEqual((row["models"], row["wall_api"], row["fresh"], row["parts"]), (2, 2.5, True, 3))
        self.assertEqual(row["timings"], {"body": 1.5, "xbf": 0.25, "key": 0.1, "read": 0.2})
        self.assertEqual((row["hits"], row["misses"], row["uncached"]), (10, 4, 1))
        self.assertEqual((row["bodies_run"], row["bodies_replayed"], row["bodies_loaded"]), (1, 2, 1))
        self.assertEqual((row["cache"], row["cache_reason"]), (None, "no file yet"))  # one model of two taken whole
        self.assertEqual(row["files"], {"xbf": {"written": 1, "kept": 1, "bytes": 2_000_500, "seconds": 0.25},
                                        "glb": {"written": 0, "kept": 1, "bytes": 100, "seconds": 0.0}})
        self.assertEqual(row["xbf_bytes"], 2_000_000)
        self.assertEqual(corpus_bench.worker_memory(
            {"workers": [{"script": "/w/a.py", "rssMb": 400.4}, {"script": "/w/c.py", "rssMb": 100},
                         {"script": "/x/d.py", "rssMb": 9}]}, ["/w/a.py", "/w/c.py"]), 500)

    def test_a_failed_build_is_a_failed_row(self):
        row = corpus_bench.build_row({"builds": [
            {"target": "a.py", "models": [{"ok": False, "model": "a.py::a", "error": "ValueError: no"}]},
            {"target": "b.py", "error": "EngineError: no engine daemon"}]})
        self.assertFalse(row["ok"])
        self.assertEqual(row["error"], "ValueError: no\nb.py: EngineError: no engine daemon")
        self.assertFalse(corpus_bench.build_row(corpus_bench.driver_answer("Traceback (most recent call last):\n"))["ok"])


class TableTest(unittest.TestCase):
    def test_a_line_per_model_from_its_steps(self):
        rows = [{"kind": "run"},
                step("arm", "cold", wall=146.05, timings={"body": 127.55}, xbf_bytes=58_940_000, rss_mb=3700, load=17.2),
                step("arm", "noop", wall=1.48, load=8.9),
                step("arm", "edit", wall=8.27, timings={"body": 3.71}, misses=110, bodies_run=1, bodies_replayed=7,
                     rss_mb=3800, load=8.9),
                step("arm", "revert", wall=7.01), step("arm", "restart", wall=6.11, load=8.6, cache="file"),
                step("arm", "restart-cold", wall=150.2),
                step("arm", "mesh-cold", wall=1.85), step("arm", "mesh-warm", wall=0.88), step("arm", "snapshot", wall=1.04),
                {"kind": "step", "model": "plate", "step": "cold", "ok": False, "wall": 3.0, "error": "boom"}]
        lines = corpus_bench.table(rows).splitlines()
        self.assertEqual(lines[0], "| " + " | ".join(corpus_bench.COLUMNS) + " |")
        self.assertEqual(lines[2], "| arm | 146 / 128 | 1.48 | 8.27 / 3.71 (110; 1+7) | 7.01 | 6.11 (file) | 150 | 58.9 | "
                                   "1.85 / 0.88 | 1.04 | 3800 | 8.6–17.2 |")
        self.assertEqual(lines[3], "| plate | failed | — | — | — | — | — | — | — | — | — | — |")


class CompareTest(unittest.TestCase):
    def test_rows_are_read_line_by_line(self):
        rows, bad = compare.read_rows(['{"kind": "run"}\n', "\n", "not json\n", "[1]\n", '{"kind": "step"}'])
        self.assertEqual(rows, [{"kind": "run"}, {"kind": "step"}])
        self.assertEqual(bad, [3, 4])

    def test_the_seeded_old_numbers_hold_their_sources(self):
        old = json.loads((BENCH / "old-engine-numbers.json").read_text(encoding="utf-8"))
        self.assertEqual(compare.old_problems(old), [])
        self.assertEqual(sorted(old["models"]), ["hypercar", "juno", "tom"])

    def test_a_bad_old_number_is_named(self):
        self.assertEqual(compare.old_problems({"models": {"arm": {
            "cold": {"seconds": [5, 3], "source": "notes.md:1", "line": "cold 5 s"},
            "speed": {},
            "file": {"kind": "step", "line": "STEP 4 MB"}}}}),
            ["arm.cold: `seconds` is [low, high], 0 < low <= high", "arm.speed: no such measure (cold, noop, edit, file)",
             "arm.file: no `source`", "arm.file: `MB` is its size"])

    def test_old_beside_new_with_the_speedup(self):
        old = {"models": {
            "arm": {"cold": {"seconds": [420, 600], "source": "notes.md:3", "line": "cold 7–10 min"},
                    "edit": {"seconds": [24, 29], "source": "notes.md:3", "line": "cold 7–10 min", "note": "answered"},
                    "file": {"kind": "step", "MB": 419, "seconds": [24, 26], "source": "notes.md:4", "line": "STEP 419 MB"}},
            "car": {"cold": {"seconds": [240, 240], "approx": True, "source": "notes.md:5", "line": "cold ~4 min"}}}}
        rows = [step("arm", "cold", wall=150.0, xbf_bytes=59_000_000, files={"xbf": {"seconds": 3.5}}),
                step("arm", "cold", wall=140.0, xbf_bytes=59_000_000, files={"xbf": {"seconds": 3.1}}),  # a second batch
                step("arm", "noop", wall=1.5), step("arm", "edit", wall=8.0),
                step("wing", "cold", wall=12.0, xbf_bytes=2_000_000),
                {"kind": "step", "model": "car", "step": "cold", "ok": False}]
        text = compare.table(old, rows)
        for line in ("| arm | cold | 420–600 s [1] | 145 s | 2.9–4.1× |",
                     f"| arm | no-op | {compare.NO_OLD} | 1.50 s | — |",
                     "| arm | edit | 24–29 s [1] | 8.00 s | 3.0–3.6× |",
                     "| arm | file | STEP 419 MB, written in 24–26 s [2] | xbf 59.0 MB, written in 3.30 s | 7.1× smaller |",
                     f"| wing | all | {compare.NO_OLD} | cold 12.0 s · xbf 2.0 MB | — |",
                     "| car | cold | ~240 s [3] | failed | — |",
                     "1. notes.md:3: “cold 7–10 min”",
                     "- arm edit: answered"):
            with self.subTest(line=line):
                self.assertIn(line + "\n", text)


if __name__ == "__main__":
    unittest.main()
