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

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

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

    def _write_vendor_step(self, width: float) -> None:
        """Write the 'vendor' STEP with a tool that is not the model under test."""
        script = (
            "import build123d as bd, sys\n"
            f"bd.export_step(bd.Box({width}, 8, 3), sys.argv[1])\n"
        )
        subprocess.run(
            [sys.executable, "-c", script, str(self.project / "vendor.step")],
            env=self.environment,
            capture_output=True,
            text=True,
            check=True,
        )

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

    def test_new_bytes_at_the_same_path_rebuild_the_drawing(self) -> None:
        model = self._write_model("bracket_profile.py", _DXF_MODEL)
        self._write_vendor_step(20.0)
        self._run(model)
        first = (self.project / "bracket_profile.dxf").read_bytes()

        self._run(model)
        self.assertEqual(first, (self.project / "bracket_profile.dxf").read_bytes())

        # The vendor part changes. Nothing in the model's Python changed, so the
        # old gate would have called this current and skipped.
        self._write_vendor_step(30.0)
        self._run(model)
        self.assertNotEqual(
            first,
            (self.project / "bracket_profile.dxf").read_bytes(),
            "a replaced vendor STEP must make the drawing stale",
        )

    def test_identical_bytes_replaced_in_place_stay_a_no_op(self) -> None:
        """The input is the file's CONTENT, not its mtime.

        Rewriting a file with the same bytes — a checkout, a sync, an rsync —
        must not rebuild anything, or every `git checkout` would invalidate every
        model that reads a committed STEP.

        The bytes are replayed rather than re-exported on purpose: build123d's
        STEP writer stamps its own header, so a re-export of identical geometry
        is a genuinely different file and SHOULD rebuild.
        """
        model = self._write_model("bracket_profile.py", _DXF_MODEL)
        self._write_vendor_step(20.0)
        vendor = self.project / "vendor.step"
        payload = vendor.read_bytes()
        self._run(model)
        drawing = self.project / "bracket_profile.dxf"
        before = drawing.stat().st_mtime_ns

        vendor.unlink()
        vendor.write_bytes(payload)
        self.assertNotEqual(
            before,
            vendor.stat().st_mtime_ns,
            "precondition: the input must look newer than the artifact",
        )
        self._run(model)
        self.assertEqual(before, drawing.stat().st_mtime_ns)

    def test_a_missing_input_fails_loudly(self) -> None:
        model = self._write_model("bracket_profile.py", _DXF_MODEL)
        self._write_vendor_step(20.0)
        self._run(model)

        (self.project / "vendor.step").unlink()
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

        artifact = self.project / "wrapped.step"
        unchanged = artifact.stat().st_mtime_ns
        self._run(model)
        self.assertEqual(unchanged, artifact.stat().st_mtime_ns)

        self._write_vendor_step(30.0)
        self._run(model)
        self.assertNotEqual(
            first,
            (self.project / "wrapped.step").read_bytes(),
            "a replaced vendor STEP must make the model stale",
        )

    def test_a_model_that_reads_nothing_is_unaffected(self) -> None:
        """The recording window must not disturb a model with no data inputs:
        @step's existing no-op path is the one thing this phase must not touch."""
        model = self._write_model(
            "plain.py",
            "from cadgen import build123d as bd\n"
            "from cadgen import step\n\n\n"
            "@step\n"
            "def plain():\n"
            "    return bd.Box(10, 10, 10)\n\n\n"
            "if __name__ == '__main__':\n"
            "    plain()\n",
        )
        self._run(model)
        artifact = self.project / "plain.step"
        before = artifact.stat().st_mtime_ns
        self._run(model)
        self.assertEqual(before, artifact.stat().st_mtime_ns)


_ANIMATED_MODEL = '''import cadgen
from cadgen import label_shape, step
from cadgen import build123d as bd

KINEMATICS = {
    "mates": [
        cadgen.revolute("swing", parent="#base", child="#arm",
                        origin=(0, 0, 6), direction=(0, 0, 1), limits=(0, 90)),
    ],
}


@step(kinematics=KINEMATICS)
def hinge():
    base = label_shape(bd.Box(20, 20, 4), "base")
    arm = label_shape(bd.Pos(10, 0, 6) * bd.Box(16, 4, 4), "arm")
    return bd.Compound(children=[base, arm])


if __name__ == "__main__":
    hinge()
'''


def _clip(label: str) -> str:
    return f'export const clips = {{ demo: {{ label: "{label}", duration: 2, update(t, m) {{}} }} }};\n'


class RenderModuleIsNotABuildInputTests(unittest.TestCase):
    """The render module beside the document (`hinge.step.js`) is the viewer's.

    Choreography never touches geometry or the tree, so it is not a build
    input: no decorator names it, no build reads it, the sidecar carries no
    copy of it, and editing it is a reload in the viewer — never a rebuild.
    The model stays `current` through any edit of the module.
    """

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="render-module-")
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
        (self.project / "hinge.py").write_text(_ANIMATED_MODEL, encoding="utf-8")
        # Beside the DOCUMENT (the output), not the script: hinge.step.js.
        self.render_module = self.project / "hinge.step.js"
        self.render_module.write_text(_clip("Showcase"), encoding="utf-8")

    def _run(self, *args: str) -> str:
        import json

        completed = subprocess.run(
            [sys.executable, str(self.project / "hinge.py"), "--json", *args],
            cwd=str(self.project),
            env=self.environment,
            capture_output=True,
            text=True,
            timeout=600,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        return json.loads(completed.stdout.strip().splitlines()[-1])["outcome"]

    def _sidecar(self) -> dict:
        import json

        return json.loads((self.project / "hinge.step.json").read_text(encoding="utf-8"))

    def test_editing_the_render_module_never_makes_the_model_stale(self) -> None:
        self.assertEqual(self._run(), "built")
        self.assertEqual(self._run(), "current")
        self.assertNotIn("animation", self._sidecar(), "the sidecar carries no copy of the module")

        self.render_module.write_text(_clip("Showcase EDITED"), encoding="utf-8")
        self.assertEqual(self._run(), "current", "choreography is a reload, never a rebuild")
        self.render_module.unlink()
        self.assertEqual(self._run(), "current", "nor is its absence a build concern")

    def test_force_still_rebuilds_a_current_model(self) -> None:
        self.assertEqual(self._run(), "built")
        self.assertEqual(self._run("--force"), "built")

    def test_the_render_module_is_not_in_the_closure(self) -> None:
        self._run()
        from unittest import mock

        from cadgen.store.records import read_record

        with mock.patch.dict(os.environ, {"CADGEN_CACHE_DIR": self.environment["CADGEN_CACHE_DIR"]}):
            recorded = read_record(self.project / "hinge.py")
        self.assertIsNotNone(recorded, "the build must leave a record for the model")
        files = sorted(os.path.basename(f) for f in recorded["closure"]["files"])
        self.assertEqual(files, ["hinge.py"])


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


if __name__ == "__main__":
    unittest.main()
