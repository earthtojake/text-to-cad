"""The manual benchmarks' pure helpers (``scripts/bench``): AGENTS.md runs only those in a test
runner, never a batch. ``corpus_bench.py``'s config check, a build step's row and the batch's
table.
Nothing here builds, serves or draws: the fixtures are a file in a temporary folder and rows
written by hand."""

from __future__ import annotations

import importlib.util
import json
import os
import unittest
from unittest.mock import patch
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


def model(**overrides):
    return {"name": "part", "root": "proj", "cwd": "src", "targets": ["part.py"], "document": "part.py::part", "xbf": "XBF/part.xbf",
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
            # A project kept in a repository of its own sits beside this one: only a root may climb.
            self.assertEqual(corpus_bench.problems({"models": [model(root="../beside")]}), [])
            cases = {
                "part: a second model of this name": [model(), model()],
                "part: unknown key `target`": [model(target="part.py")],
                "part: `targets` is a list of Python scripts (`script.py`)": [model(targets=["part.py::part"])],
                "part: `document` selects a built model": [model(document="part.py")],
                "part: `xbf` names an .xbf": [model(xbf="XBF/part.step")],
                "part: `root` is a relative path from the repository": [model(root="/proj")],
                "part: `cwd` is a relative path inside the project": [model(cwd="../src")],
                "part: the edit's `to` is its `from`": [model(edit={"file": "src/part.py", "from": "A", "to": "A"})],
                "part: no script gone.py in proj/src": [model(targets=["gone.py"])],
                "part: no STEP/imported: an input the build reads": [model(needs=["STEP/imported"])],
                "part: no document script gone.py::part": [model(document="gone.py::part")],
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
    def test_copy_keeps_source_and_pinned_inputs_without_local_state(self):
        with temporary_directory(prefix="bench-copy-") as folder:
            root = Path(folder)
            source, work = root / "source", root / "work"
            (source / "src").mkdir(parents=True)
            (source / "src/part.py").write_text(SCRIPT, encoding="utf-8")
            (source / "STEP/imported").mkdir(parents=True)
            (source / "STEP/imported/input.step").write_bytes(b"pinned fixture")
            for name in (".git", ".venv", "node_modules", ".pio", "tmp", "XBF", "src/__pycache__"):
                (source / name).mkdir()
                (source / name / "local").write_bytes(b"must not copy")
            corpus_bench.copy_project(source, work)
            self.assertEqual((work / "src/part.py").read_text(encoding="utf-8"), SCRIPT)
            self.assertEqual((work / "STEP/imported/input.step").read_bytes(), b"pinned fixture")
            self.assertEqual(sorted(path.relative_to(work).as_posix() for path in work.rglob("*") if path.is_file()),
                             ["STEP/imported/input.step", "src/part.py"])
            with self.assertRaises(FileExistsError):
                corpus_bench.copy_project(source, work)
            self.assertEqual((source / "src/part.py").read_text(encoding="utf-8"), SCRIPT)

    def test_symlinks_cannot_turn_a_copy_or_edit_into_an_original_write(self):
        with temporary_directory(prefix="bench-link-") as folder:
            root = Path(folder)
            source = root / "source"
            source.mkdir()
            outside = root / "original.py"
            outside.write_text(SCRIPT, encoding="utf-8")
            (source / "part.py").symlink_to(outside)
            with self.assertRaisesRegex(ValueError, "refuses symlink"):
                corpus_bench.copy_project(source, root / "work")
            with self.assertRaisesRegex(ValueError, "escapes the work copy"):
                corpus_bench.inside(source, source / "part.py")
            self.assertEqual(outside.read_text(encoding="utf-8"), SCRIPT)

    def test_every_mutable_engine_path_is_private_even_with_owner_overrides(self):
        with temporary_directory(prefix="bench-private-") as folder:
            out = Path(folder).resolve() / "batch"
            cadgen = Path(folder).resolve() / "cadgen/src"
            keys = ("CADGEN_ENGINE_DIR", "CADGEN_STATE_DIR", "CADGEN_CACHE_DIR", "CADGEN_LAUNCHER_DIR")
            with patch.dict(os.environ, {**{key: "/owner/normal" for key in keys}, "PYTHONDONTWRITEBYTECODE": "1"}):
                prepared = corpus_bench.prepare(model(pythonpath=["src"]), out, out / "doors", cadgen)
            for key in keys:
                self.assertTrue(Path(prepared.env[key]).is_relative_to(out), key)
            self.assertEqual(len({prepared.env[key] for key in keys}), len(keys))
            self.assertEqual(prepared.env["CADGEN_ENGINE_PORT"], "0")
            self.assertEqual(prepared.env["DO_NOT_TRACK"], "1")
            self.assertNotIn("PYTHONDONTWRITEBYTECODE", prepared.env)
            self.assertTrue(Path(prepared.env["PYTHONPYCACHEPREFIX"]).is_relative_to(out))
            self.assertIn(str(out / "no-browser.py"), prepared.env["BROWSER"])
            self.assertEqual(prepared.env["PYTHONPATH"], os.pathsep.join([str(cadgen), str(prepared.work / "src")]))
            self.assertEqual(prepared.selection, (str(prepared.cwd / "part.py"), "part"))


class DocumentTest(unittest.TestCase):
    def test_selection_uses_actual_script_function_and_id_including_children(self):
        child = {"ok": True, "id": "actual-child-id", "source": {"script": "/work/parts.py", "name": "part"}}
        other = {"ok": True, "id": "other-id", "source": {"script": "/elsewhere/parts.py", "name": "part"},
                 "child_models": {"child": child}}
        answer = {"builds": [{"models": [other]}]}
        self.assertEqual(corpus_bench.document_id(answer, "/work/parts.py", "part"), "actual-child-id")
        with self.assertRaisesRegex(ValueError, "found 0"):
            corpus_bench.document_id(answer, "/work/parts.py", "uncalled")
        answer["builds"].append({"models": [{**child, "id": "conflicting-id"}]})
        with self.assertRaisesRegex(ValueError, "found 2"):
            corpus_bench.document_id(answer, "/work/parts.py", "part")

    def test_a_failed_model_cannot_supply_the_selected_document(self):
        answer = {"builds": [{"models": [{"ok": False, "id": "previous-id",
                   "source": {"script": "/work/parts.py", "name": "part"}}]}]}
        with self.assertRaisesRegex(ValueError, "found 0"):
            corpus_bench.document_id(answer, "/work/parts.py", "part")


class BuildRowTest(unittest.TestCase):
    def test_a_build_row_sums_every_model_its_targets_built(self):
        built = {"ok": True, "model": "a.py::a", "parts": 3, "timings": {"body": 1.5, "xbf": 0.25},
                 "memo": {"hits": 10, "misses": 4, "uncached": 1, "bodies_run": 1, "bodies_skipped": 2},
                 "cache": {"used": False, "reason": "no cached document"},
                 "files": {"/w/XBF/a.xbf": {"kind": "xbf", "written": True, "bytes": 2_000_000, "seconds": 0.25}},
                 "child_models": {"b.py::b": {"files": {"/w/XBF/b.xbf": {"kind": "xbf", "written": False,
                                                                          "bytes": 500, "seconds": 0.0}}}}}
        taken = {"ok": True, "model": "c.py::c", "timings": {"key": 0.1, "read": 0.2}, "bodies": {"c.py::c": "loaded"},
                 "memo": {"hits": 0, "misses": 0, "bodies_loaded": 1}, "cache": {"used": True, "from": "cache"},
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
        self.assertEqual((row["cache"], row["cache_reason"]), (None, "no cached document"))  # one model of two taken whole
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
        self.assertEqual(corpus_bench.build_row({"builds": []})["error"], "the scripts made no model calls")
        self.assertEqual(corpus_bench.build_row({"builds": [], "error": "script stopped before a call"})["error"],
                         "script stopped before a call")
        called = {"builds": [{"models": [{"ok": True}]}], "error": "script failed after its model call"}
        self.assertFalse(corpus_bench.build_row(called)["ok"])


class TableTest(unittest.TestCase):
    def test_a_line_per_model_from_its_steps(self):
        rows = [{"kind": "run"},
                step("arm", "cold", wall=146.05, timings={"body": 127.55}, xbf_bytes=58_940_000, rss_mb=3700, load=17.2),
                step("arm", "noop", wall=1.48, load=8.9),
                step("arm", "edit", wall=8.27, timings={"body": 3.71}, misses=110, bodies_run=1, bodies_replayed=7,
                     rss_mb=3800, load=8.9),
                step("arm", "revert", wall=7.01), step("arm", "restart", wall=6.11, load=8.6, cache="cache"),
                step("arm", "restart-cold", wall=150.2),
                step("arm", "mesh-cold", wall=1.85), step("arm", "mesh-warm", wall=0.88), step("arm", "snapshot", wall=1.04),
                {"kind": "step", "model": "plate", "step": "cold", "ok": False, "wall": 3.0, "error": "boom"}]
        lines = corpus_bench.table(rows).splitlines()
        self.assertEqual(lines[0], "| " + " | ".join(corpus_bench.COLUMNS) + " |")
        self.assertEqual(lines[2], "| arm | 146 / 128 | 1.48 | 8.27 / 3.71 (110; 1+7) | 7.01 | 6.11 (cache) | 150 | 58.9 | "
                                   "1.85 / 0.88 | 1.04 | 3800 | 8.6–17.2 |")
        self.assertEqual(lines[3], "| plate | failed | — | — | — | — | — | — | — | — | — | — |")



if __name__ == "__main__":
    unittest.main()
