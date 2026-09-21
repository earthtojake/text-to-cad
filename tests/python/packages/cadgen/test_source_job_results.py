"""A job's final authored geometry precedes, but never substitutes for, its saves."""

from __future__ import annotations

import os
import contextlib
import io
import json
import runpy
import sys
import threading
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

    def geometry_tree(self):
        from build123d import Solid
        from cadgen.store.build import build_tree_from_compound
        return build_tree_from_compound(Solid.make_box(1, 1, 1), root_name="child")[0]

    def test_result_is_available_before_completion_and_never_reads_a_newer_record(self):
        from cadgen.authoring import BuildFrame
        from cadgen.store.lazy import LazyCompound

        model = f"{self.root / 'child.py'}::child"
        tree = self.geometry_tree()
        job = executors.Job(model)
        job._observe(self.event(model, tree))
        self.assertFalse(job.done)
        with mock.patch("cadgen.store.records.read_record", side_effect=AssertionError("latest record read")):
            child = LazyCompound(model, job, frame=BuildFrame(None), label="child")
            self.assertEqual(child.tree_hash(), tree)
        job._finish(1)
        self.assertEqual(job.wait_result(), tree, "failed persistence cannot rewrite the published source result")
        with self.assertRaisesRegex(RuntimeError, "failed"):
            child.wait_outputs()

    def test_wrong_function_result_and_success_without_a_result_do_not_resolve(self):
        model = f"{self.root / 'child.py'}::left"
        job = executors.Job(model)
        job._observe(self.event(f"{self.root / 'child.py'}::right", "other-tree"))
        job._finish(0)
        with self.assertRaisesRegex(RuntimeError, "source result"):
            job.wait_result()

    def test_cache_loss_does_not_replace_the_job_pin(self):
        from cadgen.authoring import BuildFrame
        from cadgen.store.lazy import LazyCompound
        from cadgen.store.objects import object_path

        model = f"{self.root / 'child.py'}::child"
        tree = self.geometry_tree()
        job = executors.Job(model)
        job._observe(self.event(model, tree))
        object_path(tree).unlink()
        child = LazyCompound(model, job, frame=BuildFrame(None), label="child")
        with mock.patch("cadgen.store.records.read_record", side_effect=AssertionError("latest record read")):
            with self.assertRaisesRegex(RuntimeError, "disappeared|missing"):
                child.tree_hash()
        job._finish(0)

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

    def test_failure_cleanup_waits_every_called_child_even_after_the_first_failure(self):
        from cadgen.authoring import building, settle_child_builds

        waited = []
        first = mock.Mock()
        first.wait_outputs.side_effect = RuntimeError("first child save failed")
        second = mock.Mock()
        second.wait_outputs.side_effect = lambda: waited.append("second")
        with self.assertRaisesRegex(RuntimeError, "parent body failed") as error:
            with settle_child_builds():
                with building(None) as frame:
                    frame.children.extend([("first", first), ("second", second)])
                    raise RuntimeError("parent body failed")
        self.assertEqual(waited, ["second"])
        self.assertIn("first child save failed", error.exception.__notes__[0])

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

        def export(directory, jobs, **kwargs):
            seen.append(json.loads((directory / "assembly.json").read_text(encoding="utf-8"))["tree"])
            for job in jobs:
                job.out.write_bytes(b"requested mesh result")

        spec = _entry_spec_from_source(source_from_path(script))
        with mock.patch("cadgen._internal.mesh_export.run_mesh_exporter", side_effect=export):
            _produce_declared_mesh_exports(spec, logger=None, announce=False, source_tree=old)
        self.assertEqual(seen, [old])

    def exercise_nested(self, *, discard=False, fail=False, mesh_parent=False, block_mesh=False):
        from cadgen.store.records import read_record
        from cadgen.store.trees import tree_complete

        child = self.root / "child.py"
        parent = self.root / "parent.py"
        blocked, release = self.root / "blocked", self.root / "release"
        child.write_text(
            "from cadgen import step, stl, build123d as bd\n"
            + ("@stl\n" if block_mesh else "")
            + "@step\ndef child():\n"
            "    import time\n    from pathlib import Path\n"
            + ("    import cadgen._internal.generation as writer\n    original = writer._produce_declared_mesh_exports\n" if block_mesh else
               "    import cadgen.step_export as writer\n    original = writer.export_build123d_step_file\n")
            +
            "    def save(*args, **kwargs):\n"
            f"        Path({str(blocked)!r}).write_text('blocked', encoding='utf-8')\n"
            "        deadline = time.monotonic() + 35\n"
            f"        while not Path({str(release)!r}).exists():\n"
            "            if time.monotonic() > deadline: raise RuntimeError('save barrier timed out')\n"
            "            time.sleep(.02)\n"
            + ("        raise RuntimeError('injected child save failure')\n" if fail else
               "        return original(*args, **kwargs)\n")
            + ("    writer._produce_declared_mesh_exports = save\n" if block_mesh else
               "    writer.export_build123d_step_file = save\n")
            +
            "    return bd.Box(4, 3, 2)\n",
            encoding="utf-8",
        )
        parent.write_text(
            "from cadgen import step, stl, build123d as bd\nfrom child import child\n"
            + ("@stl\n" if mesh_parent else "@step\n")
            + "def parent():\n    piece = child()\n"
            + ("    return bd.Box(7, 3, 2)\n" if discard else
               "    return bd.Compound(children=[bd.Pos(8, 0, 0) * piece, bd.Pos(-8, 0, 0) * piece])\n"),
            encoding="utf-8",
        )
        output = self.root / "parent.step"
        output.write_bytes(b"previous parent document")
        preview = threading.Event()
        events = []

        def observe(event):
            events.append(event)
            if event.get("preview", {}).get("output") == str(output):
                preview.set()

        executors.set_event_sink(observe)
        self.addCleanup(executors.set_event_sink, None)
        with executors.root_context():
            job = executors.submit(f"{parent}::parent")
            try:
                source = job.wait_result(timeout=30)
                self.assertTrue(tree_complete(source))
                if not mesh_parent:
                    self.assertTrue(preview.wait(5), job.output())
                import time

                deadline = time.monotonic() + 5
                while not blocked.is_file() and time.monotonic() < deadline:
                    time.sleep(.01)
                self.assertTrue(blocked.is_file(), "the child never entered its STEP exporter")
                self.assertFalse(job.done, "the explicit parent completed while its child save was blocked")
                self.assertEqual(output.read_bytes(), b"previous parent document")
                self.assertIsNone(read_record(f"{parent}::parent"))
            finally:
                release.write_text("continue", encoding="utf-8")
                code = job.wait(timeout=40)
        self.assertEqual(code != 0, fail, job.output())
        if fail:
            self.assertEqual(output.read_bytes(), b"previous parent document")
            self.assertIsNone(read_record(f"{parent}::parent"))
            if block_mesh:
                self.assertTrue((self.root / "child.step").is_file(), "child STEP succeeded but its declared mesh did not")
        else:
            self.assertNotEqual(output.read_bytes(), b"previous parent document")
            self.assertEqual(read_record(f"{parent}::parent")["tree"], source)
            self.assertTrue((self.root / "child.step").is_file())

    def test_parent_preview_precedes_child_save_and_explicit_completion_waits(self):
        self.exercise_nested()

    def test_discarded_child_still_has_to_finish_its_declared_outputs(self):
        self.exercise_nested(discard=True)

    def test_child_save_failure_preserves_parent_file_after_parent_preview(self):
        self.exercise_nested(fail=True)

    def test_mesh_only_parent_publishes_source_then_waits_its_child_outputs(self):
        self.exercise_nested(mesh_parent=True, fail=True)

    def test_child_mesh_failure_after_step_save_still_prevents_parent_save(self):
        self.exercise_nested(block_mesh=True, fail=True)
