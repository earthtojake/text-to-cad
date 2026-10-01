"""A file a model READS is a freshness input, for `@step` and `@dxf` alike.

Freshness used to follow a model's Python import reach only. That is the half
of a model's dependencies that announces itself: modules register, and an audit
hook sees every one. A file read as DATA announces nothing, so a model built
from a vendor STEP kept reporting itself current after that STEP was replaced,
and the only way to get the truth back was ``--force`` — a flag whose whole job
was to say "the gate is lying to you".

Nothing is declared: the build's trace (cadgen._internal.filetrace) sees every
file the build opens -- Python's open, numpy, an OCCT reader in C++ -- and the
next run's gate re-hashes what it read.

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
    # This process writes it: it imports build123d for its own tests anyway.
    def _write_vendor_step(self, width: float) -> None:
        import build123d

        build123d.export_step(build123d.Box(width, 8, 3), str(self.project / "vendor.step"))

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

    def _run_json(self, model: str) -> str:
        completed = subprocess.run(
            [sys.executable, str(self.project / model), "--json"], cwd=str(self.project),
            env=self.environment, capture_output=True, text=True, timeout=600,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        return json.loads(completed.stdout.strip().splitlines()[-1])["outcome"]

    def test_a_file_the_model_reads_without_declaring_it_is_an_input(self) -> None:
        """A plain ``read_text`` joins the closure. Reading the model's own
        previous output is not an input, or the model could never be current."""
        model = self._write_model("plate.py", '''import json
from pathlib import Path

from cadgen import build123d as bd
from cadgen import step

HERE = Path(__file__).resolve().parent


@step
def plate():
    width = json.loads((HERE / "atlas.json").read_text(encoding="utf-8"))["width"]
    own = HERE / "plate.step"
    if own.exists():
        own.read_bytes()
    return bd.Box(width, 20, 4)


if __name__ == "__main__":
    plate()
''')
        atlas = self.project / "atlas.json"
        atlas.write_text('{"width": 10}', encoding="utf-8")
        self.assertEqual(self._run_json(model), "built")
        first = (self.project / "plate.step").read_bytes()
        self.assertEqual(self._run_json(model), "current", "its own last output is no input")
        atlas.write_text('{"width": 30}', encoding="utf-8")
        self.assertEqual(self._run_json(model), "built", "a replaced data file makes the model stale")
        self.assertNotEqual(first, (self.project / "plate.step").read_bytes())

    def test_a_childs_reads_and_output_stay_in_the_childs_record(self) -> None:
        """A child is the parent's input by its result. Checking whether it is
        current reads its files inside the parent's build; none of that is the
        parent's."""
        (self.project / "data").mkdir()
        (self.project / "data" / "size.txt").write_text("10\n", encoding="utf-8")
        self._write_model("leg.py", '''from pathlib import Path

from cadgen import build123d as bd
from cadgen import step

HERE = Path(__file__).resolve().parent


@step
def leg():
    return bd.Cylinder(2, float((HERE / "data" / "size.txt").read_text()))
''')
        table = self._write_model("table.py", '''from cadgen import build123d as bd
from cadgen import step
from leg import leg


@step
def table():
    return bd.Compound([bd.Box(20, 20, 2), bd.Pos(0, 0, -5) * leg()])


if __name__ == "__main__":
    table()
''')
        self.assertEqual(self._run_json(table), "built")
        # Rebuild the parent alone: the child has a record now, so checking it
        # inside the parent's build reads its data file and its .step.
        (self.project / table).write_text(
            (self.project / table).read_text(encoding="utf-8").replace("Box(20,", "Box(22,"), encoding="utf-8")
        self.assertEqual(self._run_json(table), "built")
        from cadgen.store.records import read_record

        with mock.patch.dict(os.environ, {"CADGEN_CACHE_DIR": self.environment["CADGEN_CACHE_DIR"]}):
            parent, child = (read_record(self.project / name) for name in ("table.py", "leg.py"))
        self.assertIn("data/size.txt", child["closure"]["files"])
        self.assertFalse({"data/size.txt", "leg.step"} & set(parent["closure"]["files"]))


class OwnOutputAsInputTests(unittest.TestCase):
    """A model must not read a file it writes.

    `read_step` on the model's own `.step` builds the model from what the
    previous run left on disk (the build never counts its own output as an
    input, so nothing else catches it). A body that re-wraps its own
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


class ReadSceneTests(unittest.TestCase):
    def test_the_document_read_scene_opens_is_traced(self) -> None:
        import build123d

        from cadgen import step_scene
        from cadgen._internal import filetrace

        with tempfile.TemporaryDirectory(prefix="scene-recording-") as tmp:
            path = Path(tmp) / "part.step"
            build123d.export_step(build123d.Box(4, 3, 2), path)
            with mock.patch.dict(os.environ, {
                "CADGEN_CACHE_DIR": str(Path(tmp) / "store"),
                "CADGEN_DAEMON": "0",
            }):
                with filetrace.capture() as trace:
                    step_scene.read_scene(path)
                files, _folders = trace.inputs()
            self.assertEqual(set(files), {path.resolve()})

    def test_a_missing_scene_file_fails_loudly(self) -> None:
        from cadgen import step_scene

        with self.assertRaises(FileNotFoundError) as caught:
            step_scene.read_scene(Path("/nonexistent/part.step"))
        self.assertIn("read_scene", str(caught.exception))


class FileTraceTests(unittest.TestCase):
    """The trace at the unit level: what one capture calls an input."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="file-trace-")
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name).resolve()

    def _file(self, name: str, text: str = "x") -> Path:
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def test_what_is_read_is_an_input_and_what_is_written_code_or_cadgens_is_not(self) -> None:
        from cadgen._internal import filetrace
        from cadgen._internal.source_hash import _sha256_file

        data, table, code, engine = (self._file(name, "1") for name in ("dims.json", "table.csv", "helper.py", "engine.bin"))
        scratch = self.root / "scratch.txt"
        with filetrace.capture() as trace:
            json.loads(data.read_text(encoding="utf-8"))
            with open(table, newline="", encoding="utf-8") as handle:
                handle.read()
            code.read_text(encoding="utf-8")  # code is tracked by reach
            with filetrace.paused():
                _sha256_file(engine)  # cadgen reading for itself
            scratch.write_text("x", encoding="utf-8")  # the build's own file
            scratch.read_text(encoding="utf-8")
        files, folders = trace.inputs()
        self.assertEqual(files, {data: _sha256_file(data), table: _sha256_file(table)})
        self.assertEqual(folders, set())

    def test_a_file_opened_only_in_native_code_is_traced(self) -> None:
        import build123d

        from cadgen._internal import filetrace

        part = self.root / "part.step"
        build123d.export_step(build123d.Box(1, 2, 3), part)
        with filetrace.capture() as trace:
            build123d.import_step(str(part))
        self.assertEqual(set(trace.inputs()[0]), {part})

    def test_a_file_that_changed_or_vanished_after_its_read_is_recorded_changed(self) -> None:
        from cadgen._internal import filetrace

        edited, removed = self._file("edited.json", "1"), self._file("removed.json", "1")
        with filetrace.capture() as trace:
            edited.read_text(encoding="utf-8")
            removed.read_text(encoding="utf-8")
            with filetrace.paused():  # another process, as far as the build can tell
                edited.write_text("22", encoding="utf-8")
                removed.unlink()
        files, _folders = trace.inputs()
        self.assertEqual(files, {edited: filetrace.CHANGED, removed: filetrace.CHANGED})

    def test_the_daemon_key_read_on_a_job_thread_is_not_an_input(self) -> None:
        """A parent submitting a child connects to the daemon on a job thread,
        reading its key; that is cadgen's, on any thread."""
        import threading

        from cadgen._internal import filetrace
        from cadgen.daemon import transport

        address = str(self.root / "d.sock")
        with mock.patch.dict(os.environ, {"CADGEN_DAEMON_STATE_DIR": str(self.root / "state")}):
            transport.ensure_authkey(address)
            with filetrace.capture() as trace:
                thread = threading.Thread(target=transport.read_authkey, args=(address,))
                thread.start()
                thread.join()
        self.assertEqual(trace.inputs(), ({}, set()))

    def test_a_file_opened_to_read_and_write_is_an_input_until_the_build_changes_it(self) -> None:
        """A database or an ``r+`` read keeps what it holds: an input. One the
        build writes is its own, and so is the journal a write leaves behind."""
        import sqlite3

        from cadgen._internal import filetrace

        catalog, notes, scratch = self.root / "parts.db", self._file("notes.json", "1"), self.root / "scratch.db"
        with sqlite3.connect(catalog) as db:
            db.execute("create table part (name text)")
            db.execute("insert into part values ('bolt')")
        db.close()
        with filetrace.capture() as trace:
            with sqlite3.connect(catalog) as db:
                rows = db.execute("select name from part").fetchall()
            db.close()
            with open(notes, "r+", encoding="utf-8") as handle:
                handle.read()
            with sqlite3.connect(scratch) as db:
                db.execute("create table t (x)")
            db.close()
        self.assertEqual(rows, [("bolt",)])
        self.assertEqual(set(trace.inputs()[0]), {catalog, notes})

    def test_a_folder_listed_through_a_descriptor_is_an_input(self) -> None:
        if not hasattr(os, "fwalk"):
            self.skipTest("os.fwalk lists folders by descriptor on POSIX only")
        from cadgen._internal import filetrace

        profiles = self.root / "profiles"
        self._file("profiles/a.json", "{}")
        with filetrace.capture() as trace:
            list(os.fwalk(profiles))
        self.assertEqual(trace.inputs()[1], {profiles})

    def test_captures_nest(self) -> None:
        from cadgen._internal import filetrace

        outer_file, inner_file = self._file("outer.txt"), self._file("inner.txt")
        with filetrace.capture() as outer:
            outer_file.read_text(encoding="utf-8")
            with filetrace.capture() as inner:
                inner_file.read_text(encoding="utf-8")
        self.assertEqual(set(inner.inputs()[0]), {inner_file})
        self.assertEqual(set(outer.inputs()[0]), {outer_file, inner_file})

    def test_a_folder_the_model_code_lists_is_an_input_and_an_import_listing_is_not(self) -> None:
        import importlib

        from cadgen._internal import filetrace

        profiles, package = self.root / "profiles", self.root / "pkg"
        self._file("profiles/a.json", "{}")
        self._file("pkg/helper_for_listing_test.py", "X = 1\n")
        sys.path.insert(0, str(package))
        self.addCleanup(sys.path.remove, str(package))
        self.addCleanup(sys.modules.pop, "helper_for_listing_test", None)
        with filetrace.capture() as trace:
            sorted(profiles.glob("*.json"))
            importlib.import_module("helper_for_listing_test")  # the import system lists pkg/
        self.assertEqual(trace.inputs()[1], {profiles})

    def test_an_input_edited_mid_build_leaves_the_result_stale_and_unpublished(self) -> None:
        """The geometry came from the first bytes: the record must not pair it
        with the second, so the next gate rebuilds."""
        from cadgen._internal import filetrace
        from cadgen.store.closure import build_closure, current_closure_hash
        from cadgen.store.gate import stale
        from cadgen.store.publish import decide

        script = self._file("plain.py", "def model():\n    return None\n")
        atlas = self._file("atlas.json", '{"width": 30}')
        with filetrace.capture() as trace:
            consumed = json.loads(atlas.read_text(encoding="utf-8"))
            with filetrace.paused():
                atlas.write_text('{"width": 45}', encoding="utf-8")
        self.assertEqual(consumed["width"], 30)
        files, folders = trace.inputs()
        closure = build_closure(script, executed={}, inputs=files, listings=folders)
        self.assertEqual(closure.shas["atlas.json"], filetrace.CHANGED)
        self.assertNotEqual(closure.hash, current_closure_hash(script, closure.files))
        record = {"tree": None, "closure": {"hash": closure.hash, "files": closure.files, "shas": closure.shas}}
        with mock.patch("cadgen.store.gate.read_record", return_value=record):
            verdict = stale(script)
        self.assertTrue(verdict.stale)
        self.assertIn("atlas.json", verdict.clauses[1]["why"])
        # An older build cannot replace a current record that a newer
        # build published while this body was still running.
        with mock.patch("cadgen.store.publish.stale", return_value=mock.Mock(stale=False)):
            decision = decide(script, ran_closure_hash=closure.hash, ran_files=closure.files)
        self.assertFalse(decision.publish_outputs)


class OldRecordTests(unittest.TestCase):
    def test_an_old_late_hash_record_misses_without_invalidating_saved_artifacts(self) -> None:
        import hashlib

        from cadgen._internal.source_hash import _sha256_file
        from cadgen.catalog import result_snapshot_for
        from cadgen.store.closure import build_closure
        from cadgen.store.gate import stale
        from cadgen.store.objects import put_object, read_verified_object
        from cadgen.store.records import note_document_tree, read_record, write_record
        from tests.python.support.tmp_root import generated_cad_directory

        with generated_cad_directory(prefix="old-record-admission-") as folder:
            root = Path(folder)
            script = root / "model.py"
            script.write_text("def model():\n    return None\n", encoding="utf-8")
            data = root / "dimensions.json"
            data.write_text('{"width":30}', encoding="utf-8")
            consumed_width = json.loads(data.read_text(encoding="utf-8"))["width"]
            data.write_text('{"width":45}', encoding="utf-8")
            # Reproduce the old late-hash record: its closure falsely agrees
            # with the edited input, although the body consumed width 30.
            closure = build_closure(script, executed={}, inputs={data: _sha256_file(data)})
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
