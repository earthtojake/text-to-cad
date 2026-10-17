"""A build's source result: the tree its run published, named before its files are
written and never replaced by a later record. A top-level call hands back exactly that
tree; a child a parent's body called owes its declared outputs and its failure to the run."""

from __future__ import annotations

import os
import contextlib
import io
import json
import runpy
import sys
import unittest
from pathlib import Path
from unittest import mock

from cadgen.daemon import executors
from tests.python.support.tmp_root import generated_cad_directory


class SourceJobResults(unittest.TestCase):
    def setUp(self):
        temporary = generated_cad_directory(prefix="source-job-results-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        environment = mock.patch.dict(os.environ, {
            "CADGEN_CACHE_DIR": str(self.root / "store"),
            "CADGEN_DAEMON": "0", "CADGEN_JOBS": "2", "CADGEN_COMPONENT_WORKERS": "1",
        })
        environment.start()
        self.addCleanup(environment.stop)

    def event(self, model, tree):
        return executors.model_event(model, "building", sourceResult={"model": str(model), "tree": tree})

    def test_a_result_announced_before_completion_stands_whatever_the_exit(self):
        model = f"{self.root / 'child.py'}::child"
        job = executors.Job(model)
        job._observe(self.event(model, "tree-1"))
        self.assertFalse(job.done)
        self.assertTrue(job.result_ready)
        job._observe(self.event(model, "tree-2"))  # a later announcement never replaces the first
        job._finish(1)
        self.assertEqual(job.wait_result(), "tree-1", "failed persistence cannot rewrite the published source result")

    def test_wrong_function_result_and_success_without_a_result_do_not_resolve(self):
        model = f"{self.root / 'child.py'}::left"
        job = executors.Job(model)
        job._observe(self.event(f"{self.root / 'child.py'}::right", "other-tree"))
        job._finish(0)
        with self.assertRaisesRegex(RuntimeError, "source result"):
            job.wait_result()

    def test_top_level_return_keeps_the_completed_jobs_exact_tree(self):
        import cadgen.authoring as authoring
        from cadgen.store.build import build_tree_from_compound
        from cadgen.store.records import read_record, write_record
        from build123d import Box

        script = self.root / "part.py"
        script.write_text("from cadgen import step, build123d as bd\n@step\ndef part():\n    return bd.Box(4, 3, 2)\n", encoding="utf-8")
        namespace = runpy.run_path(str(script))
        original = authoring._build

        def finish_then_newer(definition):
            code = original(definition)
            record = read_record(definition.ref)
            record["tree"] = build_tree_from_compound(Box(40, 3, 2), root_name="part")[0]
            write_record(definition.ref, record)
            return code

        with mock.patch.object(sys, "argv", [str(script)]), \
             mock.patch.object(authoring, "_build", side_effect=finish_then_newer), \
             contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            result = namespace["part"]()
        self.assertAlmostEqual(sum(solid.volume for solid in result.solids()), 24)

    def test_current_call_emits_source_result_and_returns_independent_geometry(self):
        from cadgen.store.materialize import TREE_TAG

        script = self.root / "part.py"
        script.write_text(
            "from cadgen import step, build123d as bd\n@step\ndef part():\n"
            "    return bd.Box(4, 3, 2)\n",
            encoding="utf-8",
        )
        namespace = runpy.run_path(str(script))
        with mock.patch.object(sys, "argv", [str(script)]), \
             mock.patch("cadgen._internal.generation._assembly_glb_package_current",
                        side_effect=AssertionError("generated outputs repeated an unused package gate")), \
             contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            first = namespace["part"]()
            second = namespace["part"]()
        self.assertEqual(getattr(first, TREE_TAG), getattr(second, TREE_TAG))
        self.assertFalse(first.wrapped.IsPartner(second.wrapped))

    def test_current_gate_and_cli_keep_the_checked_tree_when_the_record_moves(self):
        from cadgen.cli._run_model import run_model_argv
        from cadgen.store import gate
        from cadgen.store.build import build_tree_from_compound
        from cadgen.store.records import read_record, write_record
        from build123d import Box

        script = self.root / "part.py"
        script.write_text("from cadgen import step, build123d as bd\n@step\ndef part():\n    return bd.Box(4, 3, 2)\n", encoding="utf-8")
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(run_model_argv([str(script)]), 0)
        record = read_record(script)
        checked_tree = record["tree"]
        newer_tree = build_tree_from_compound(Box(40, 3, 2), root_name="part")[0]
        original = gate.stale

        def check_then_replace(model, **kwargs):
            verdict = original(model, **kwargs)
            self.assertFalse(verdict.stale)
            record["tree"] = newer_tree
            write_record(script, record)
            return verdict

        output = io.StringIO()
        with mock.patch.object(gate, "stale", side_effect=check_then_replace), \
             executors.capture_source_result(f"{script}::part") as captured, \
             contextlib.redirect_stdout(output), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(run_model_argv([str(script), "--json"]), 0)
        captured._finish(0)
        self.assertEqual(captured.wait_result(), checked_tree)
        result = [json.loads(line) for line in output.getvalue().splitlines() if line.startswith('{"ok":')][-1]
        self.assertEqual(result["tree"], checked_tree)
        self.assertEqual(read_record(script)["tree"], newer_tree)

    def test_mesh_only_export_uses_its_source_result_after_a_newer_record(self):
        from build123d import Box
        from cadgen._internal.generation import _produce_declared_mesh_exports
        from cadgen._internal.generation_spec import _entry_spec_from_source
        from cadgen.catalog import source_from_path
        from cadgen.store.build import build_tree_from_compound
        from cadgen.store.records import write_record

        script = self.root / "part.py"
        script.write_text("from cadgen import stl, build123d as bd\n@stl\ndef part():\n    return bd.Box(4, 3, 2)\n", encoding="utf-8")
        old = build_tree_from_compound(Box(4, 3, 2), root_name="part")[0]
        newer = build_tree_from_compound(Box(40, 3, 2), root_name="part")[0]
        write_record(script, {"tree": newer, "outputs": {}})
        seen = []

        def export(source, jobs, **kwargs):
            seen.append(source.tree)
            for job in jobs:
                job.out.write_bytes(b"requested mesh result")
            return {"ok": True, "files": [{"path": str(job.out), "format": job.fmt, "triangleCount": 12} for job in jobs]}

        spec = _entry_spec_from_source(source_from_path(script))
        with mock.patch("cadgen._internal.mesh_export.run_mesh_exporter", side_effect=export):
            _produce_declared_mesh_exports(spec, logger=None, source_tree=old)
        self.assertEqual(seen, [old])

    def _nested(self, *, discard: bool, child_fails: bool) -> tuple[int, str]:
        child = self.root / "child.py"
        parent = self.root / "parent.py"
        child.write_text(
            "from cadgen import step, build123d as bd\n@step\ndef child():\n"
            + ("    raise RuntimeError('the child is wrong on purpose')\n" if child_fails else "    return bd.Box(4, 3, 2)\n"),
            encoding="utf-8",
        )
        parent.write_text(
            "from cadgen import step, build123d as bd\nfrom child import child\n@step\ndef parent():\n"
            + ("    try:\n        piece = child()\n    except Exception:\n        piece = None\n" if child_fails
               else "    piece = child()\n")
            + ("    return bd.Box(7, 3, 2)\n" if discard
               else "    return bd.Compound(children=[bd.Pos(8, 0, 0) * piece, bd.Pos(-8, 0, 0) * piece])\n"),
            encoding="utf-8",
        )
        (self.root / "parent.step").write_bytes(b"previous parent document")
        from cadgen.cli._run_model import run_model_argv

        err = io.StringIO()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
            code = run_model_argv([str(parent)])
        return code, err.getvalue()

    def test_a_discarded_child_is_still_built_whole_and_is_the_parents_dependency(self):
        # The body called it, so its declared outputs are written and the parent's
        # record lists it, whatever the body made of the geometry.
        from cadgen.store.records import read_record

        code, err = self._nested(discard=True, child_fails=False)
        self.assertEqual(code, 0, err)
        self.assertTrue((self.root / "child.step").is_file(), "the discarded child's declared STEP was not written")
        self.assertNotEqual((self.root / "parent.step").read_bytes(), b"previous parent document")
        self.assertEqual(read_record(self.root / "parent.py")["children"],
                         [{"model": f"{self.root / 'child.py'}::child", "key": read_record(self.root / "child.py")["key"]}])

    def test_a_child_failure_the_body_catches_still_fails_the_run_and_keeps_the_parents_file(self):
        from cadgen.store.records import read_record

        code, err = self._nested(discard=True, child_fails=True)
        self.assertNotEqual(code, 0)
        self.assertIn("a child model failed to build", err)
        self.assertIn("the child is wrong on purpose", err)
        self.assertEqual((self.root / "parent.step").read_bytes(), b"previous parent document")
        self.assertIsNone(read_record(self.root / "parent.py"))
        self.assertIsNone(read_record(self.root / "child.py"))


if __name__ == "__main__":
    unittest.main()
