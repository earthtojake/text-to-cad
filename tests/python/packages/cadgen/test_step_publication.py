"""A failed or superseded build must not replace the last saved document."""

from __future__ import annotations

import contextlib
import io
import os
import shutil
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support.tmp_root import generated_cad_directory


class StepPublicationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = generated_cad_directory(prefix="step-publication-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.model = self.root / "part.py"
        self.step = self.root / "part.step"
        self.sidecar = self.root / "part.step.json"
        env = mock.patch.dict(os.environ, {
            "CADGEN_CACHE_DIR": str(self.root / "store"),
            "CADGEN_DAEMON": "0", "CADGEN_JOBS": "1",
        })
        env.start()
        self.addCleanup(env.stop)

    def build(self, size: int, *, force: bool = False, annotated: bool = False) -> int:
        from cadgen.cli._run_model import run_model_argv

        source = (
            "from cadgen import step\nfrom cadgen import build123d as bd\n"
            f"SIZE = {size}\n@step\ndef part():\n    return bd.Box(SIZE, 8, 6)\n"
            "if __name__ == '__main__':\n    part()\n"
        )
        if annotated:
            source = (
                "from cadgen import step, revolute\nfrom cadgen import build123d as bd\n"
                f"SIZE = {size}\n"
                "@step(kinematics={'mates': [revolute('swing', parent='#base', child='#arm', "
                "origin=(0, 0, 6), direction=(0, 0, 1), limits=(0, 90))]})\n"
                "def part():\n"
                "    base = bd.Box(SIZE, 20, 4)\n    base.label = 'base'\n"
                "    arm = bd.Pos(10, 0, 6) * bd.Box(16, 4, 4)\n    arm.label = 'arm'\n"
                "    return bd.Compound(children=[base, arm])\n"
                "if __name__ == '__main__':\n    part()\n"
            )
        self.model.write_text(source, encoding="utf-8")
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            result = run_model_argv([str(self.model), *(["--force"] if force else [])])
        self.output = output.getvalue()
        return result

    def test_rejected_publication_keeps_document_sidecar_and_record(self) -> None:
        from cadgen.store.publish import PublishDecision
        from cadgen.store.records import read_record

        self.assertEqual(self.build(10), 0, self.output)
        before = self.step.read_bytes()
        self.sidecar.write_text('{"kinematics":{"authored":"previous"}}', encoding="utf-8")
        annotation = self.sidecar.read_bytes()
        record = read_record(f"{self.model}::part")

        def reject(*args, **kwargs):
            self.assertEqual(self.step.read_bytes(), before, "the decision must precede target replacement")
            self.assertEqual(self.sidecar.read_bytes(), annotation)
            return PublishDecision(False, "a newer result is current")

        with mock.patch("cadgen.store.publish.decide", side_effect=reject) as decide:
            self.assertNotEqual(self.build(12), 0, "a superseded explicit save must not report success")
        decide.assert_called_once()
        self.assertEqual(self.step.read_bytes(), before)
        self.assertEqual(self.sidecar.read_bytes(), annotation)
        self.assertEqual(read_record(f"{self.model}::part"), record)
        self.assertEqual(list(self.root.glob(".cadgen-stage-*")), [], "private stages are cleaned")

    def test_a_build_removes_the_stage_a_killed_build_left_and_names_its_own_by_owner(self) -> None:
        # A build killed while it saves (its caller left, so the daemon ended its worker)
        # leaves its staging folder, a full STEP copy, in the project. The next build there
        # removes it; a live build's and another machine's stay.
        import subprocess
        import sys

        from cadgen._internal import atomic_replace, temp_leftovers

        exited = subprocess.Popen([sys.executable, "-c", "pass"])
        exited.wait()
        host = temp_leftovers._host()
        other = "0" * 8 if host != "0" * 8 else "1" * 8
        dead = self.root / f".cadgen-stage-{exited.pid}-{host}-part-ab12cd34"
        live = self.root / f".cadgen-stage-{os.getpid()}-{host}-part-ef56gh78"
        elsewhere = self.root / f".cadgen-stage-{exited.pid}-{other}-part-ab12cd34"
        for stage in (dead, live, elsewhere):
            stage.mkdir()
            (stage / "part.step").write_text("ISO-10303-21;", encoding="utf-8")
        own: list[str] = []
        replace = atomic_replace.replace_atomic

        def publish(temp_path, target_path):
            staged = Path(temp_path).parent
            if Path(target_path) == self.step and staged != self.root:
                own.append(staged.name)
            replace(temp_path, target_path)

        with mock.patch.object(atomic_replace, "replace_atomic", publish):
            self.assertEqual(self.build(10), 0, self.output)
        self.assertFalse(dead.exists())
        self.assertTrue(live.is_dir() and elsewhere.is_dir())
        [stage] = own
        self.assertTrue(stage.startswith(f".cadgen-stage-{os.getpid()}-{host}-part-"), stage)
        self.assertFalse((self.root / stage).exists())

    def test_a_stale_build_skips_the_saved_tree_reuse_check(self) -> None:
        # The gate already called this build stale. The reuse check hashes the
        # saved STEP, and for a model with kinematics its sidecar's binding to
        # it: work only a current model can use.
        from cadgen._internal import generation

        self.assertEqual(self.build(10, annotated=True), 0, self.output)
        with mock.patch.object(generation, "_existing_topology_artifact_matches_spec_without_scene",
                               side_effect=AssertionError("reuse check on a stale build")) as check:
            self.assertEqual(self.build(12, annotated=True), 0, self.output)
        check.assert_not_called()

    def test_tree_metadata_does_not_hash_the_saved_step(self) -> None:
        # The tree takes its edge capabilities and classes from the provenance
        # manifest and nothing else; hashing the saved document for it read the
        # whole file once per build.
        from cadgen._internal import generation
        from cadgen.store.records import read_record
        from cadgen.store.trees import get_tree

        self.assertEqual(self.build(10), 0, self.output)
        with mock.patch.object(generation, "step_file_hash",
                               side_effect=AssertionError("hashed the saved STEP for tree metadata")):
            self.assertEqual(self.build(12), 0, self.output)
        tree = get_tree(read_record(f"{self.model}::part")["tree"])
        self.assertTrue(tree["edgeRendering"]["visibilityClasses"])
        self.assertIn("edgeClassification", tree["capabilities"])
        self.assertNotIn("stepHash", tree)

    def test_a_job_reads_its_saved_step_at_most_once(self) -> None:
        # Every digest a job takes of its saved document goes through the
        # gate's settled-stamp memo, and a document the build renamed into
        # place is known by the digest its writer took. A label edit keeps a
        # STEP of hundreds of megabytes and used to read it once per check.
        from cadgen._internal import generation
        from cadgen.cli._run_model import run_model_argv
        from cadgen.store import gate

        self.assertEqual(self.build(10), 0, self.output)
        reads: list[Path] = []
        hash_file, sha256_of = gate._hash_file, generation._sha256_of

        def counted(original):
            def read(path):
                reads.append(Path(path).resolve())
                return original(path)
            return read

        def step_reads() -> int:
            return sum(path == self.step.resolve() for path in reads)

        with mock.patch.object(gate, "_stamp_is_settled", return_value=True), \
                mock.patch.object(gate, "_hash_file", side_effect=counted(hash_file)), \
                mock.patch.object(generation, "_sha256_of", side_effect=counted(sha256_of)):
            # A new document: the previous one may be read once, the new one never.
            self.assertEqual(self.build(12), 0, self.output)
            self.assertLessEqual(step_reads(), 1, reads)
            reads.clear()
            # A label edit keeps the document, and nothing reads it.
            self.model.write_text(self.model.read_text(encoding="utf-8").replace(
                "    return bd.Box(SIZE, 8, 6)\n", "    box = bd.Box(SIZE, 8, 6)\n    box.label = 'renamed'\n    return box\n"),
                encoding="utf-8")
            output = io.StringIO()
            with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
                self.assertEqual(run_model_argv([str(self.model)]), 0, output.getvalue())
            self.assertIn("kept STEP", output.getvalue())
            self.assertEqual(step_reads(), 0, reads)

    def test_a_job_takes_one_gate_verdict_before_its_body(self) -> None:
        # The fast path's verdict serves the peer check, the annotation refresh
        # and the reuse check of the same job; only the already-stale notice
        # after publishing asks the gate again.
        from cadgen.store import gate

        self.assertEqual(self.build(10, annotated=True), 0, self.output)
        asked: list[str] = []
        original = gate.stale

        def counted(model, *, memo=None):
            if memo is None:
                asked.append(str(model))
            return original(model, memo=memo)

        with mock.patch.object(gate, "stale", side_effect=counted):
            self.assertEqual(self.build(12, annotated=True), 0, self.output)
        self.assertEqual(len(asked), 2, asked)

    def test_failed_readback_keeps_the_saved_pair(self) -> None:
        self.assertEqual(self.build(10), 0, self.output)
        before = self.step.read_bytes()
        self.sidecar.write_text('{"kinematics":{"authored":"previous"}}', encoding="utf-8")
        annotation = self.sidecar.read_bytes()
        with mock.patch("cadgen.store.build._reread_component", side_effect=RuntimeError("injected read-back failure")):
            self.assertNotEqual(self.build(12), 0)
        self.assertEqual(self.step.read_bytes(), before)
        self.assertEqual(self.sidecar.read_bytes(), annotation)
        self.assertEqual(list(self.root.glob(".part-*")), [])

    def test_preview_is_complete_before_readback_and_saved_file_is_still_previous(self) -> None:
        from cadgen.daemon import executors
        from cadgen.store import build as store_build
        from cadgen.store.trees import tree_complete

        self.assertEqual(self.build(10), 0, self.output)
        before = self.step.read_bytes()
        events = []
        executors.set_event_sink(events.append)
        self.addCleanup(executors.set_event_sink, None)
        original = store_build._reread_component

        def reread(*args, **kwargs):
            previews = [event["preview"] for event in events if "preview" in event]
            self.assertTrue(previews, "preview must precede STEP read-back")
            self.assertTrue(tree_complete(previews[-1]["tree"]))
            self.assertEqual(self.step.read_bytes(), before)
            return original(*args, **kwargs)

        with mock.patch.object(store_build, "_reread_component", side_effect=reread):
            self.assertEqual(self.build(12), 0, self.output)
        saved = [event["saved"] for event in events if "saved" in event]
        self.assertEqual(len(saved), 1)
        self.assertTrue(tree_complete(saved[0]["tree"]))
        self.assertNotEqual(self.step.read_bytes(), before)

    def test_external_document_edit_during_build_is_not_overwritten(self) -> None:
        from cadgen._internal import generation
        from cadgen.store.records import read_record

        self.assertEqual(self.build(10), 0, self.output)
        record = read_record(f"{self.model}::part")
        original = generation.run_script_generator

        def generate(*args, **kwargs):
            result = original(*args, **kwargs)
            self.step.write_bytes(b"externally replaced STEP")
            return result

        with mock.patch.object(generation, "run_script_generator", side_effect=generate):
            self.assertNotEqual(self.build(12), 0)
        self.assertEqual(self.step.read_bytes(), b"externally replaced STEP")
        self.assertIn("changed during the build", self.output)
        self.assertEqual(read_record(f"{self.model}::part"), record)

    def test_incomplete_saved_tree_keeps_last_document(self) -> None:
        from cadgen.store import build as store_build
        from cadgen.store import trees

        self.assertEqual(self.build(10), 0, self.output)
        before = self.step.read_bytes()
        original = store_build.build_tree_through_step

        def lose_component(*args, **kwargs):
            result = original(*args, **kwargs)
            # Simulate cache deletion after the prepared STEP has been read
            # back, before the saved root is admitted for publication.
            from cadgen.store.objects import object_path
            tree = trees.get_tree(result[0])
            component = next(iter(tree["components"].values()))
            object_path(component["brep"]).unlink()
            return result

        with mock.patch.object(store_build, "build_tree_through_step", side_effect=lose_component):
            self.assertNotEqual(self.build(12), 0)
        self.assertEqual(self.step.read_bytes(), before)
        self.assertIn("pinned geometry disappeared", self.output)

    def test_failure_after_each_publication_boundary_is_readable_by_saved_bytes(self) -> None:
        from cadgen._internal import atomic_replace
        from cadgen._internal.doors import document_tree
        from cadgen._internal.source_sidecar import SidecarBindingError, read_source_sidecar
        from cadgen.store import records
        from cadgen.store.trees import tree_complete

        for boundary in ("document-index", "step", "sidecar", "output-index", "model-record"):
            with self.subTest(boundary=boundary):
                self.assertEqual(self.build(10, force=True, annotated=True), 0, self.output)
                old_bytes = self.step.read_bytes()
                old_sidecar = self.sidecar.read_bytes()
                old_record = records.read_record(f"{self.model}::part")
                fired = []

                def after_write(original, *args, **kwargs):
                    result = original(*args, **kwargs)
                    fired.append(boundary)
                    raise RuntimeError(f"injected failure after {boundary}")

                if boundary in ("step", "sidecar"):
                    original = atomic_replace.replace_atomic
                    destination = self.step if boundary == "step" else self.sidecar

                    def replace(source, target):
                        if Path(target).resolve() == destination:
                            return after_write(original, source, target)
                        return original(source, target)

                    injection = mock.patch.object(atomic_replace, "replace_atomic", side_effect=replace)
                else:
                    name = {"document-index": "note_document_tree", "output-index": "note_output",
                            "model-record": "write_record"}[boundary]
                    original = getattr(records, name)
                    injection = mock.patch.object(records, name, side_effect=lambda *a, **kw: after_write(original, *a, **kw))
                with injection:
                    self.assertNotEqual(self.build(12, force=True, annotated=True), 0, self.output)
                self.assertEqual(fired, [boundary])
                self.assertIn(f"injected failure after {boundary}", self.output)
                self.assertEqual(list(self.root.glob(".part-*")), [])
                if boundary == "document-index":
                    self.assertEqual(self.step.read_bytes(), old_bytes)
                    self.assertEqual(self.sidecar.read_bytes(), old_sidecar)
                else:
                    self.assertNotEqual(self.step.read_bytes(), old_bytes)
                if boundary == "step":
                    self.assertEqual(self.sidecar.read_bytes(), old_sidecar)
                    with self.assertRaises(SidecarBindingError):
                        read_source_sidecar(self.step)
                else:
                    self.assertIsNotNone(read_source_sidecar(self.step))
                if boundary != "model-record":
                    self.assertEqual(records.read_record(f"{self.model}::part"), old_record)
                else:
                    self.assertNotEqual(records.read_record(f"{self.model}::part"), old_record)
                with mock.patch.object(records, "read_record", side_effect=AssertionError("saved reader read a record")), \
                        mock.patch.object(records, "model_for_output", side_effect=AssertionError("saved reader read output ownership")):
                    self.assertTrue(tree_complete(document_tree(self.step)))

    def test_whole_store_deletion_after_step_replacement_recovers_without_source(self) -> None:
        from cadgen._internal import atomic_replace
        from cadgen._internal.doors import document_tree
        from cadgen.store import records
        from cadgen.store.trees import tree_complete

        self.assertEqual(self.build(10), 0, self.output)
        source_bytes = self.model.read_bytes()
        original = atomic_replace.replace_atomic

        def replace(source, target):
            original(source, target)
            if Path(target).resolve() == self.step:
                shutil.rmtree(self.root / "store")
                raise RuntimeError("cache deleted after document rename")

        with mock.patch.object(atomic_replace, "replace_atomic", side_effect=replace):
            self.assertNotEqual(self.build(12), 0)
        edited_source = self.model.read_bytes()
        self.assertNotEqual(edited_source, source_bytes)
        saved_bytes = self.step.read_bytes()
        self.assertTrue(saved_bytes.startswith(b"ISO-10303-21;"))
        # A saved artifact does not require its source to be available. Keep the
        # edited source aside so the test can also prove cache loss lost no edit.
        parked = self.model.with_suffix(".source")
        self.model.rename(parked)
        with mock.patch.object(records, "read_record", side_effect=AssertionError("saved reader read a record")), \
                mock.patch.object(records, "model_for_output", side_effect=AssertionError("saved reader read output ownership")):
            tree = document_tree(self.step)
        self.assertTrue(tree_complete(tree))
        self.assertEqual(self.step.read_bytes(), saved_bytes)
        self.assertEqual(parked.read_bytes(), edited_source)

    def test_source_location_and_preview_session_do_not_enter_geometry_identity(self) -> None:
        from cadgen.catalog import result_tree_for
        from cadgen.daemon import executors
        from cadgen.store.objects import object_path
        from cadgen.store.trees import tree_objects

        identities = []
        self.addCleanup(executors.set_event_sink, None)
        for name in ("session-first", "session-second"):
            directory = self.root / name
            directory.mkdir()
            self.model = directory / "part.py"
            self.step = directory / "part.step"
            self.sidecar = directory / "part.step.json"
            events = []
            executors.set_event_sink(events.append)
            self.assertEqual(self.build(10, force=True), 0, self.output)
            previews = [event["preview"]["tree"] for event in events if "preview" in event]
            self.assertEqual(len(previews), 1)
            identities.append((self.step.read_bytes(), result_tree_for(self.step), previews[0]))
            for root_hash in (identities[-1][1], previews[0]):
                for digest in tree_objects(root_hash):
                    payload = object_path(digest).read_bytes()
                    for forbidden in (str(directory).encode(), b"sourcePath", b"generatedAt", b"session-first", b"session-second"):
                        self.assertNotIn(forbidden, payload)
        self.assertEqual(identities[0], identities[1])

    def test_cold_compile_ignores_code_records_and_declared_outputs(self) -> None:
        from cadgen.catalog import result_tree_for
        from cadgen.step import compile as compile_step
        from cadgen.store import index, records
        from cadgen.store.trees import tree_complete

        self.assertEqual(self.build(10), 0, self.output)
        saved_bytes = self.step.read_bytes()
        expected_tree = result_tree_for(self.step)
        self.model.unlink()
        shutil.rmtree(self.root / "store")
        self.assertIsNone(result_tree_for(self.step))
        # Even leftover compiler bookkeeping cannot supply a tree or resurrect
        # mesh declarations when the document's geometry cache is absent.
        phantom = self.root / "phantom.stl"
        records.write_record(self.step, {
            "tree": "0" * 64,
            "outputs": {str(phantom): {"declared": "stl", "sha256": "old"}},
        })
        read_entry = index.read_entry

        def artifact_read(kind, key):
            self.assertNotIn(kind, ("model", "output"), "cold compile consulted a code record")
            return read_entry(kind, key)

        output = io.StringIO()
        with mock.patch.object(index, "read_entry", side_effect=artifact_read), \
                mock.patch.object(records, "read_entry", side_effect=artifact_read), \
                contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            # Calling the compiler directly keeps the guard in its process;
            # patching only a parent document reader misses worker-side reads.
            result = compile_step(self.step)
        self.assertTrue(result.ok, output.getvalue())
        self.assertEqual(result.tree, expected_tree)
        self.assertTrue(tree_complete(result.tree))
        self.assertEqual(self.step.read_bytes(), saved_bytes)
        self.assertEqual(records.read_record(self.step)["outputs"], {})
        self.assertFalse(phantom.exists())

    def test_competing_write_observed_after_rename_does_not_publish_success(self) -> None:
        from cadgen._internal import atomic_replace
        from cadgen._internal.doors import document_tree
        from cadgen._internal.source_sidecar import SidecarBindingError, read_source_sidecar
        from cadgen.store.records import read_record

        self.assertEqual(self.build(10, annotated=True), 0, self.output)
        previous_bytes = self.step.read_bytes()
        previous_tree = document_tree(self.step)
        previous_record = read_record(f"{self.model}::part")
        original = atomic_replace.replace_atomic
        replaced = []

        def competing_replace(source, target):
            original(source, target)
            if Path(target).resolve() == self.step:
                replaced.append(True)
                # An external writer won the check-to-rename race. The final
                # verification may detect this; it cannot claim exclusion.
                self.step.write_bytes(previous_bytes)

        with mock.patch.object(atomic_replace, "replace_atomic", side_effect=competing_replace):
            self.assertNotEqual(self.build(12, annotated=True), 0, self.output)
        self.assertEqual(replaced, [True])
        self.assertIn("saved files changed during publication", self.output)
        self.assertEqual(self.step.read_bytes(), previous_bytes)
        self.assertEqual(document_tree(self.step), previous_tree)
        self.assertEqual(read_record(f"{self.model}::part"), previous_record)
        with self.assertRaises(SidecarBindingError):
            read_source_sidecar(self.step)


PIN_SOURCE = """\
from cadgen import step
from cadgen import build123d as bd


@step(out="../STEP/pin.step")
def pin():
    return bd.Cylinder(radius=2.0, height=12.0)


if __name__ == "__main__":
    pin()
"""

ARM_SOURCE = """\
from cadgen import step
from cadgen import build123d as bd

from pin import pin


@step(out="../STEP/arm.step")
def arm():
    bar = bd.Box(40.0, 8.0, 4.0)
    bar.label = "bar"
    left = pin().moved(bd.Location((-15.0, 0.0, 2.0)))
    left.label = "pin_left"
    right = pin().moved(bd.Location((15.0, 0.0, 2.0)))
    right.label = "pin_right"
    return bd.Compound(children=[bar, left, right], label="arm")


if __name__ == "__main__":
    arm()
"""


class AssemblyJobReads(unittest.TestCase):
    """A job verifies each object of a pinned closure once (STORE.md §4, §10):
    the gate's clauses share one verification, a publish claims what the job
    verified without reading it again, and a child another process rebuilt
    costs the parent's next job that child's closure, not the whole closure."""

    def setUp(self) -> None:
        import sys

        self.temp = generated_cad_directory(prefix="assembly-reads-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "src").mkdir()
        (self.root / "STEP").mkdir()
        self.pin = self.root / "src/pin.py"
        self.arm = self.root / "src/arm.py"
        self.pin.write_text(PIN_SOURCE, encoding="utf-8")
        self.arm.write_text(ARM_SOURCE, encoding="utf-8")
        self.env = {"CADGEN_CACHE_DIR": str(self.root / "store"), "CADGEN_DAEMON": "0", "CADGEN_JOBS": "1"}
        patch = mock.patch.dict(os.environ, self.env)
        patch.start()
        self.addCleanup(patch.stop)
        self.python = sys.executable
        from cadgen.store import trees

        trees._reset_metadata_capture_cache()
        self.addCleanup(trees._reset_metadata_capture_cache)

    def run_here(self, script: Path, *flags: str) -> str:
        """A job in this process (its children in subprocesses): the outcome word."""
        from cadgen.cli._run_model import run_model_argv

        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            code = run_model_argv([str(script), *flags])
        self.assertEqual(code, 0, output.getvalue())
        return output.getvalue().strip().splitlines()[-1].split(" ", 1)[0]

    def run_elsewhere(self, script: Path, *flags: str) -> str:
        """The same job in another process, as another worker would run it."""
        import subprocess

        from tests.python.support.paths import repo_path

        env = {**os.environ, **self.env, "PYTHONPATH": str(repo_path("packages/cadgen/src"))}
        done = subprocess.run([self.python, script.name, *flags], cwd=str(script.parent), env=env,
                              capture_output=True, text=True, timeout=600)
        self.assertEqual(done.returncode, 0, done.stderr[-2000:])
        return done.stdout.strip().splitlines()[-1].split(" ", 1)[0]

    def closure(self, model: Path) -> dict[str, str]:
        """Every object of the model's result closure, by digest."""
        from cadgen.store.records import read_record
        from cadgen.store.trees import tree_objects

        tree = read_record(f"{model}::{model.stem}")["tree"]
        return {digest: tree for digest in tree_objects(tree)}

    def counted_reads(self):
        from cadgen.store import trees

        reads: list[str] = []
        original = trees.read_verified_object

        def read(digest):
            reads.append(digest)
            return original(digest)

        return reads, mock.patch.object(trees, "read_verified_object", side_effect=read)

    def test_a_cold_no_op_reads_each_object_of_the_closure_once(self) -> None:
        from collections import Counter

        self.assertEqual(self.run_elsewhere(self.arm), "built")
        closure = self.closure(self.arm)
        root = next(digest for digest, tree in closure.items() if digest == tree)
        reads, counted = self.counted_reads()
        with counted:
            self.assertEqual(self.run_here(self.arm), "current")
        counts = Counter(reads)
        self.assertEqual(set(counts), set(closure))
        # Clause 3 verifies each child's closure; clause 4 takes those verified
        # subtrees as they are and reads only the parent's own objects. The
        # parent's tree is read once more, to report its kind.
        self.assertEqual({digest: n for digest, n in counts.items() if digest != root},
                         {digest: 1 for digest in closure if digest != root})
        self.assertLessEqual(counts[root], 2)

    def test_a_parent_job_verifies_a_pinned_closure_once(self) -> None:
        from cadgen.store import gate, trees

        self.assertEqual(self.run_here(self.arm), "built")
        pinned = self.closure(self.pin)
        self.arm.write_text(self.arm.read_text(encoding="utf-8").replace("40.0, 8.0, 4.0", "40.0, 8.0, 4.5"), encoding="utf-8")
        verifying = [0]
        verified: list[str] = []
        read = trees.read_verified_object

        def counting(original):
            def call(*args, **kwargs):
                verifying[0] += 1
                try:
                    return original(*args, **kwargs)
                finally:
                    verifying[0] -= 1
            return call

        def counted_read(digest):
            if verifying[0] and digest in pinned:
                verified.append(digest)
            return read(digest)

        # The gate verified the child's closure before the body. The build's own
        # checks of its result (tree_complete) and its publish (claim_tree) take
        # that verification as it stands: nothing of the child is read again.
        with mock.patch.object(trees, "tree_complete", side_effect=counting(trees.tree_complete)), \
                mock.patch.object(gate, "tree_complete", side_effect=counting(trees.tree_complete)), \
                mock.patch.object(trees, "claim_tree", side_effect=counting(trees.claim_tree)), \
                mock.patch.object(trees, "read_verified_object", side_effect=counted_read):
            self.assertEqual(self.run_here(self.arm), "built")
        self.assertEqual(verified, [])

    def test_a_childs_rebuild_elsewhere_costs_the_parent_that_childs_closure(self) -> None:
        from collections import Counter

        self.assertEqual(self.run_here(self.arm), "built")
        self.assertEqual(self.run_here(self.arm), "current")
        pinned = self.closure(self.pin)
        whole = self.closure(self.arm)
        self.assertLess(len(pinned), len(whole))
        # Another worker's forced rebuild of the child publishes the same tree
        # and claims its closure, which moves every stamp this process verified.
        self.assertEqual(self.run_elsewhere(self.pin, "--force"), "built")
        self.assertEqual(self.closure(self.pin), pinned)
        reads, counted = self.counted_reads()
        with counted:
            self.assertEqual(self.run_here(self.arm), "current")
        counts = Counter(reads)
        self.assertEqual(max(counts.values()), 1, counts)
        root = next(digest for digest, tree in whole.items() if digest == tree)
        self.assertEqual(set(reads), {*pinned, root}, counts)


if __name__ == "__main__":
    unittest.main()
