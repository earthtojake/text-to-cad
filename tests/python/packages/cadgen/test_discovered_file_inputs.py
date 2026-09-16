"""A file a model READS is a freshness input, for `@step` and `@dxf` alike.

Freshness used to follow a model's Python import reach only. That is the half
of a model's dependencies that announces itself: modules register, and an audit
hook sees every one. A file read as DATA announces nothing, so a model built
from a vendor STEP kept reporting itself current after that STEP was replaced,
and the only way to get the truth back was ``--force`` — a flag whose whole job
was to say "the gate is lying to you".

``cadgen.read_step`` closes that (design/dxf-build123d.md). It records the file
it read into the run's closure, byte-hashed like any non-Python input, and the
next run's gate re-hashes it.

The failure mode this phase guards against is SILENT: the wrong answer is a
build that does nothing and says everything is fine. So the three cases are
tested from the outside, on the bytes actually written:

* different bytes at the same path -> the model rebuilds;
* identical bytes replaced in place -> still a no-op (mtime is not the input);
* the file gone -> a loud error, not a silent skip.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support.paths import add_repo_path

CADGEN_SRC = add_repo_path("packages/cadgen/src")


_DXF_MODEL = '''from pathlib import Path

from cadgen import build123d as bd
from cadgen import dxf, read_step

HERE = Path(__file__).resolve().parent


@dxf
def profile():
    part = read_step(HERE / "vendor.step")
    top_z = part.bounding_box().max.Z
    face = [
        f for f in part.faces()
        if abs(f.normal_at(f.center()).Z - 1) < 1e-6 and abs(f.center().Z - top_z) < 1e-6
    ][0]
    return bd.Location((0, 0, -top_z)) * face


if __name__ == "__main__":
    profile()
'''

_STEP_MODEL = '''from pathlib import Path

from cadgen import read_step, step

HERE = Path(__file__).resolve().parent


@step
def wrapped():
    return read_step(HERE / "vendor.step")


if __name__ == "__main__":
    wrapped()
'''


_JSON_MODEL = '''import json
from pathlib import Path

from cadgen import build123d as bd
from cadgen import declare_input, step

HERE = Path(__file__).resolve().parent


def _atlas():
    return json.loads(declare_input(HERE / "atlas.json").read_text(encoding="utf-8"))


@step
def plate():
    atlas = _atlas()
    return bd.Box(atlas["width"], 20, 4)


if __name__ == "__main__":
    plate()
'''


class DiscoveredFileInputTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="discovered-inputs-")
        self.addCleanup(self._tmp.cleanup)
        self.project = Path(self._tmp.name).resolve()
        self.environment = dict(os.environ)
        self.environment.update(
            {
                # A warm worker would serve another checkout's code.
                "CADGEN_DAEMON": "0",
                "CADGEN_COMPONENT_WORKERS": "1",
                "CADGEN_CACHE_DIR": str(self.project / "store"),
                "PYTHONPATH": str(CADGEN_SRC),
            }
        )

    # The vendor STEP is an INPUT: what matters is that some tool other than the model
    # under test wrote it, and that the two widths are different bytes at the same path.
    # Writing each width once for the class and copying the bytes in keeps both of those
    # true and stops four tests paying a cold build123d import each to re-emit a box.
    _vendor_bytes: dict[float, bytes] = {}

    @classmethod
    def _vendor_step(cls, width: float) -> bytes:
        if width not in cls._vendor_bytes:
            with tempfile.TemporaryDirectory(prefix="discovered-vendor-") as scratch:
                target = Path(scratch) / "vendor.step"
                subprocess.run(
                    [
                        sys.executable, "-c",
                        "import build123d as bd, sys\n"
                        f"bd.export_step(bd.Box({width}, 8, 3), sys.argv[1])\n",
                        str(target),
                    ],
                    env={**os.environ, "PYTHONPATH": str(CADGEN_SRC)},
                    capture_output=True, text=True, check=True,
                )
                cls._vendor_bytes[width] = target.read_bytes()
        return cls._vendor_bytes[width]

    def _write_vendor_step(self, width: float) -> None:
        (self.project / "vendor.step").write_bytes(self._vendor_step(width))

    def _run(self, model: str) -> str:
        completed = subprocess.run(
            [sys.executable, str(self.project / model)],
            cwd=str(self.project),
            env=self.environment,
            capture_output=True,
            text=True,
            timeout=600,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        return completed.stdout + completed.stderr

    def _write_model(self, name: str, source: str) -> str:
        (self.project / name).write_text(source, encoding="utf-8")
        return name

    def test_input_bytes_control_drawing_rebuild_and_missing_input_fails(self) -> None:
        """The input is its content, while absence remains a loud error."""
        model = self._write_model("bracket_profile.py", _DXF_MODEL)
        self._write_vendor_step(20.0)
        vendor = self.project / "vendor.step"
        payload = vendor.read_bytes()
        self._run(model)
        drawing = self.project / "bracket_profile.dxf"
        first = drawing.read_bytes()
        before = drawing.stat().st_mtime_ns

        # A checkout or sync may replace an input without changing its bytes.
        # The artifact remains current even though the input looks newer.
        vendor.unlink()
        vendor.write_bytes(payload)
        self.assertNotEqual(
            before,
            vendor.stat().st_mtime_ns,
            "precondition: the input must look newer than the artifact",
        )
        self._run(model)
        self.assertEqual(before, drawing.stat().st_mtime_ns)
        self.assertEqual(first, drawing.read_bytes())

        # The vendor part changes. Nothing in the model's Python changed, so the
        # old gate would have called this current and skipped.
        self._write_vendor_step(30.0)
        self._run(model)
        self.assertNotEqual(
            first,
            drawing.read_bytes(),
            "a replaced vendor STEP must make the drawing stale",
        )

        vendor.unlink()
        completed = subprocess.run(
            [sys.executable, str(self.project / model)],
            cwd=str(self.project),
            env=self.environment,
            capture_output=True,
            text=True,
            timeout=600,
        )
        self.assertNotEqual(completed.returncode, 0, "a missing input must not pass silently")
        self.assertIn("read_step", completed.stdout + completed.stderr)

    def test_the_same_mechanism_serves_step_models(self) -> None:
        """`read_step` is not a drawing feature: composing a vendor part into a
        @step model records it the same way."""
        model = self._write_model("wrapped.py", _STEP_MODEL)
        self._write_vendor_step(20.0)
        self._run(model)
        first = (self.project / "wrapped.step").read_bytes()

        # Only the half that is about the decorator: that a replaced input makes a @step
        # model stale. Bytes-not-mtime is one mechanism, proven once, above.
        self._write_vendor_step(30.0)
        self._run(model)
        self.assertNotEqual(
            first,
            (self.project / "wrapped.step").read_bytes(),
            "a replaced vendor STEP must make the model stale",
        )


class OwnOutputAsInputTests(unittest.TestCase):
    """A model must not read a file it writes.

    `read_step` on the model's own `.step` is not a loop: it is an input that
    changes on every run, so the gate can never say "current" and the geometry
    depends on what the previous run left on disk. A body that re-wraps its own
    output grew by one box per run and exited 0 each time -- plausible-wrong
    output at exit 0, the one outcome the engine refuses to produce. The rule
    was written down (step-generation.md, "Never `read_step` your own output")
    and enforced nowhere.
    """

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="own-output-input-")
        self.addCleanup(self._tmp.cleanup)
        self.project = Path(self._tmp.name).resolve()
        self.environment = dict(os.environ)
        self.environment.update({
            "CADGEN_DAEMON": "0",
            "CADGEN_CACHE_DIR": str(self.project / "store"),
            "PYTHONPATH": str(CADGEN_SRC),
        })

    def _run(self, name: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(self.project / name)], cwd=str(self.project),
            env=self.environment, capture_output=True, text=True, timeout=600,
        )

    def test_read_step_of_the_models_own_step_is_refused(self) -> None:
        (self.project / "ouro.py").write_text(textwrap.dedent('''
            from pathlib import Path

            from cadgen import build123d as bd
            from cadgen import read_step, step

            HERE = Path(__file__).resolve().parent

            @step
            def ouro():
                previous = read_step(HERE / "ouro.step")
                return bd.Compound(children=[previous, bd.Pos(0, 0, 20) * bd.Box(4, 4, 4)], label="ouro")


            if __name__ == "__main__":
                ouro()
            '''), encoding="utf-8")
        # Seed the output so the refusal is about ownership, not a missing file.
        seed = "import build123d as bd, sys\nbd.export_step(bd.Box(6, 6, 6), sys.argv[1])\n"
        subprocess.run([sys.executable, "-c", seed, str(self.project / "ouro.step")],
                       env=self.environment, capture_output=True, text=True, check=True)
        before = (self.project / "ouro.step").read_bytes()

        completed = self._run("ouro.py")

        self.assertEqual(1, completed.returncode, completed.stdout + completed.stderr)
        self.assertIn("is an output this model writes", completed.stderr)
        self.assertEqual(before, (self.project / "ouro.step").read_bytes())

    def test_declare_input_on_a_declared_mesh_export_is_refused(self) -> None:
        (self.project / "selfmesh.py").write_text(textwrap.dedent('''
            from pathlib import Path

            from cadgen import build123d as bd
            from cadgen import declare_input, stl

            HERE = Path(__file__).resolve().parent

            @stl(out="selfmesh.stl")
            def selfmesh():
                declare_input(HERE / "selfmesh.stl")
                return bd.Box(5, 5, 5)


            if __name__ == "__main__":
                selfmesh()
            '''), encoding="utf-8")
        (self.project / "selfmesh.stl").write_bytes(b"")

        completed = self._run("selfmesh.py")

        self.assertEqual(1, completed.returncode, completed.stdout + completed.stderr)
        self.assertIn("is an output this model writes", completed.stderr)

    def test_reading_another_models_output_is_still_allowed(self) -> None:
        (self.project / "vendorsrc.py").write_text(textwrap.dedent('''
            from cadgen import build123d as bd
            from cadgen import step

            @step(out="vendor.step")
            def vendorsrc():
                box = bd.Box(12, 8, 5)
                box.label = "vendor"
                return box


            if __name__ == "__main__":
                vendorsrc()
            '''), encoding="utf-8")
        (self.project / "rig.py").write_text(textwrap.dedent('''
            from pathlib import Path

            from cadgen import build123d as bd
            from cadgen import read_step, step

            HERE = Path(__file__).resolve().parent

            @step
            def rig():
                part = read_step(HERE / "vendor.step")
                part.label = "vendor"
                base = bd.Box(40, 20, 4)
                base.label = "base"
                return bd.Compound(children=[base, part.moved(bd.Location((0, 0, 6)))], label="rig")


            if __name__ == "__main__":
                rig()
            '''), encoding="utf-8")

        self.assertEqual(0, self._run("vendorsrc.py").returncode)
        completed = self._run("rig.py")

        self.assertEqual(0, completed.returncode, completed.stdout + completed.stderr)
        self.assertTrue((self.project / "rig.step").exists())


class ReaderSurfaceTests(unittest.TestCase):
    """`read_step` is the STEP reader. Names that are not on the surface get
    Python's own AttributeError — no recognition of what a name once meant."""

    def test_a_name_that_is_not_exported_gets_the_plain_error(self) -> None:
        import cadgen
        from cadgen import step_scene

        for module in (cadgen, step_scene):
            with self.subTest(module=module.__name__):
                with self.assertRaises(AttributeError) as caught:
                    module.import_step
                message = str(caught.exception)
                self.assertIn("import_step", message)
                self.assertNotIn("read_step", message)

    def test_an_unrelated_missing_name_keeps_the_plain_error(self) -> None:
        from cadgen import step_scene

        with self.assertRaises(AttributeError) as caught:
            step_scene.no_such_helper
        self.assertNotIn("read_step", str(caught.exception))


class ScenePathRecordingTests(unittest.TestCase):
    """`load_step_scene` records too.

    It is the other public STEP reader, and a model that walks a vendor STEP's
    occurrence tree depends on that file's bytes exactly as much as one that
    takes its shape. Which cadgen reader records what it reads must not be
    something anyone has to remember.
    """

    def test_the_public_scene_loader_declares_its_file(self) -> None:
        import build123d

        from cadgen import step_scene
        from cadgen._internal.source_hash import record_discovered_inputs

        with tempfile.TemporaryDirectory(prefix="scene-recording-") as tmp:
            path = Path(tmp) / "part.step"
            build123d.export_step(build123d.Box(4, 3, 2), path)
            with record_discovered_inputs() as recorded:
                step_scene.load_step_scene(path)
            self.assertEqual(recorded, {path.resolve()})

    def test_the_engines_own_loads_do_not_record(self) -> None:
        """A build must never record its own output as its input."""
        import build123d

        from cadgen._internal import step_scene as engine
        from cadgen._internal.source_hash import record_discovered_inputs

        with tempfile.TemporaryDirectory(prefix="scene-recording-") as tmp:
            path = Path(tmp) / "part.step"
            build123d.export_step(build123d.Box(4, 3, 2), path)
            with record_discovered_inputs() as recorded:
                engine.load_step_scene(path)
            self.assertEqual(recorded, set())

    def test_a_missing_scene_file_fails_loudly(self) -> None:
        from cadgen import step_scene

        with self.assertRaises(FileNotFoundError) as caught:
            step_scene.load_step_scene(Path("/nonexistent/part.step"))
        self.assertIn("load_step_scene", str(caught.exception))


class DiscoveredInputRecordingTests(unittest.TestCase):
    """The recorder itself, at the unit level."""

    def test_recording_outside_a_build_is_a_no_op(self) -> None:
        """Reading a STEP from a REPL, a test, or a tool is not a build."""
        from cadgen._internal.source_hash import note_discovered_input

        note_discovered_input(Path("/nonexistent/whatever.step"))  # must not raise

    def test_nested_windows_propagate_upward(self) -> None:
        """A nested capture hands its inputs to the enclosing one, so a build
        that runs a sub-build does not lose the sub-build's data reach."""
        from cadgen._internal.source_hash import note_discovered_input, record_discovered_inputs

        with tempfile.TemporaryDirectory(prefix="discovered-nesting-") as tmp:
            outer_file = Path(tmp) / "outer.step"
            inner_file = Path(tmp) / "inner.step"
            outer_file.write_text("outer", encoding="utf-8")
            inner_file.write_text("inner", encoding="utf-8")
            with record_discovered_inputs() as outer:
                note_discovered_input(outer_file)
                with record_discovered_inputs() as inner:
                    note_discovered_input(inner_file)
                self.assertEqual(inner, {inner_file.resolve()})
                self.assertEqual(outer, {outer_file.resolve(), inner_file.resolve()})

    def test_a_recorded_input_joins_the_closure_and_is_byte_hashed(self) -> None:
        from cadgen._internal.source_hash import closure_for_files, closure_hash_matches

        with tempfile.TemporaryDirectory(prefix="discovered-closure-") as tmp:
            root = Path(tmp)
            script = root / "model.py"
            script.write_text("x = 1\n", encoding="utf-8")
            data = root / "vendor.step"
            data.write_text("ISO-10303-21;\n", encoding="utf-8")

            closure = closure_for_files(script, [data], base=root)
            self.assertIn("vendor.step", closure.files)
            self.assertTrue(closure_hash_matches(closure.closure_hash, closure.files, base=root))

            # A non-.py input is hashed by its BYTES: the AST pass has nothing to
            # say about a STEP file, and a comment there is content.
            data.write_text("ISO-10303-21;\n/* a comment */\n", encoding="utf-8")
            self.assertFalse(closure_hash_matches(closure.closure_hash, closure.files, base=root))


class DeclaredDataInputTests(unittest.TestCase):
    """A model's own data file is a build input once it says so.

    `read_step` covers the files cadgen reads for the model. A JSON routing
    atlas, a CSV table, a solved-offsets dump -- cadgen has no reader for
    those, so it cannot record them, and a model that computes its geometry
    from one used to report itself current forever after the file changed
    (PR #370 bug record 012, whose workaround was to re-export the data as a
    Python literal module so the IMPORT closure would carry it).

    `cadgen.declare_input` is the declaration: the model still parses the file
    itself, and the path it declares joins the closure. The three properties
    are the same three that matter for `read_step`, because the failure being
    guarded is the same silent one -- a build that does nothing and says
    everything is fine.
    """

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="declared-inputs-")
        self.addCleanup(self._tmp.cleanup)
        self.project = Path(self._tmp.name).resolve()
        self.environment = dict(os.environ)
        self.environment.update(
            {
                "CADGEN_DAEMON": "0",
                "CADGEN_COMPONENT_WORKERS": "1",
                "CADGEN_CACHE_DIR": str(self.project / "store"),
                "PYTHONPATH": str(CADGEN_SRC),
            }
        )
        (self.project / "plate.py").write_text(_JSON_MODEL, encoding="utf-8")
        self.atlas = self.project / "atlas.json"

    def _write_atlas(self, width: float) -> None:
        self.atlas.write_text(json.dumps({"width": width}) + "\n", encoding="utf-8")

    def _run_outcome(self) -> str:
        completed = subprocess.run(
            [sys.executable, str(self.project / "plate.py"), "--json"],
            cwd=str(self.project),
            env=self.environment,
            capture_output=True,
            text=True,
            timeout=600,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        return json.loads(completed.stdout.strip().splitlines()[-1])["outcome"]

    def test_declared_input_is_content_addressed_recorded_and_required(self) -> None:
        self._write_atlas(30.0)
        self.assertEqual(self._run_outcome(), "built")
        from cadgen.store.records import read_record

        with mock.patch.dict(os.environ, {"CADGEN_CACHE_DIR": self.environment["CADGEN_CACHE_DIR"]}):
            recorded = read_record(self.project / "plate.py")
        self.assertIsNotNone(recorded, "the build must leave a record for the model")
        self.assertIn("atlas.json", sorted(recorded["closure"]["files"]))
        # Bytes-not-mtime is one mechanism, proven once, above (read_step) and at
        # unit level below; a declared input rides the same recorder.

        self._write_atlas(45.0)
        self.assertEqual(
            self._run_outcome(), "built", "a changed data file must make the model stale"
        )
        self.assertEqual(self._run_outcome(), "current")

        self.atlas.unlink()
        completed = subprocess.run(
            [sys.executable, str(self.project / "plate.py")],
            cwd=str(self.project),
            env=self.environment,
            capture_output=True,
            text=True,
            timeout=600,
        )
        self.assertNotEqual(completed.returncode, 0, "a missing input must not pass silently")
        self.assertIn("declare_input", completed.stdout + completed.stderr)

    def test_declaring_outside_a_build_resolves_but_records_nothing(self) -> None:
        """A REPL, a test or a tool reading a data file is not a build."""
        from cadgen import declare_input
        from cadgen._internal.source_hash import record_discovered_inputs

        self._write_atlas(30.0)
        self.assertEqual(declare_input(self.atlas), self.atlas.resolve())
        with record_discovered_inputs() as recorded:
            declare_input(self.atlas)
        self.assertEqual(recorded, {self.atlas.resolve()})

    def test_edit_after_declared_read_keeps_step_and_drawing_closures_stale(self) -> None:
        from unittest import mock

        from cadgen import declare_input
        from cadgen._internal.source_hash import capture_runtime_closure, record_discovered_inputs
        from cadgen.store.closure import ExecutionHashes, build_closure, current_closure_hash
        from cadgen.store.gate import stale
        from cadgen.store.publish import decide

        script = self.project / "plain.py"
        script.write_text("def model():\n    return None\n", encoding="utf-8")
        self._write_atlas(30.0)
        with record_discovered_inputs() as inputs, ExecutionHashes() as hashes:
            consumed = json.loads(declare_input(self.atlas).read_text(encoding="utf-8"))
            first_hash = hashes.hashes[str(self.atlas)]
            self._write_atlas(45.0)
            declare_input(self.atlas)  # A later declaration cannot erase the first read.
        self.assertEqual(consumed["width"], 30.0)
        for path in inputs:
            hashes.note(path)  # The runner's post-body fallback must not overwrite it.

        step_closure = build_closure(script, executed=hashes.hashes, discovered_inputs=inputs)
        drawing_closure = capture_runtime_closure(
            set(sys.modules), script, base=self.project, discovered_inputs=inputs,
            executed_hashes=hashes.hashes,
        )
        for label, digest, files, shas in (
            ("step", step_closure.hash, step_closure.files, step_closure.shas),
            ("drawing", drawing_closure.closure_hash, drawing_closure.files, drawing_closure.file_hashes),
        ):
            with self.subTest(format=label):
                self.assertEqual(shas["atlas.json"], first_hash)
                self.assertNotEqual(digest, current_closure_hash(script, files))
                record = {"tree": None, "closure": {"hash": digest, "files": files, "shas": shas}}
                with mock.patch("cadgen.store.gate.read_record", return_value=record):
                    verdict = stale(script)
                self.assertTrue(verdict.stale)
                self.assertIn("atlas.json", verdict.clauses[1]["why"])
                # An older build cannot replace a current record that a newer
                # build published while this body was still running.
                with mock.patch("cadgen.store.publish.stale", return_value=mock.Mock(stale=False)):
                    decision = decide(script, ran_closure_hash=digest, ran_files=files)
                self.assertFalse(decision.publish_outputs)

    def test_pre_declaration_hash_records_miss_without_invalidating_saved_artifacts(self) -> None:
        import hashlib
        from unittest import mock

        from cadgen.catalog import result_snapshot_for
        from cadgen.store.closure import build_closure
        from cadgen.store.gate import stale
        from cadgen.store.objects import put_object, read_verified_object
        from cadgen.store.records import note_document_tree, read_record, write_record
        from tests.python.support.tmp_root import generated_cad_directory

        with generated_cad_directory(prefix="declared-input-admission-") as folder:
            root = Path(folder)
            script = root / "model.py"
            script.write_text("def model():\n    return None\n", encoding="utf-8")
            data = root / "dimensions.json"
            data.write_text('{"width":30}', encoding="utf-8")
            consumed_width = json.loads(data.read_text(encoding="utf-8"))["width"]
            data.write_text('{"width":45}', encoding="utf-8")
            # Reproduce the old late-hash record: its closure falsely agrees
            # with the edited input, although the body consumed width 30.
            closure = build_closure(script, executed={}, discovered_inputs=[data])
            document = root / "saved.step"
            document.write_bytes(f"saved geometry width {consumed_width}".encode())
            document_hash = hashlib.sha256(document.read_bytes()).hexdigest()
            with mock.patch.dict(os.environ, {"CADGEN_CACHE_DIR": str(root / "store")}):
                payload = b"immutable saved geometry"
                tree = put_object(payload)
                note_document_tree(document_hash, tree)
                record = {"tree": None, "closure": closure.as_json(), "children": [], "outputs": {}}
                with mock.patch("cadgen.store.records.RECORD_SCHEMA_VERSION", 5):
                    write_record(script, record)
                    self.assertFalse(stale(script).stale, "precondition: the old record falsely passes")
                self.assertIsNone(read_record(script))
                self.assertTrue(stale(script).stale)
                self.assertEqual(result_snapshot_for(document), (document_hash, tree))
                self.assertEqual(read_verified_object(tree), payload)


if __name__ == "__main__":
    unittest.main()
