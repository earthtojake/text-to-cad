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
        from cadgen.store.closure import forget_model_files

        forget_model_files()
        self.addCleanup(forget_model_files)

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
        self.assertEqual(list(self.root.glob(".part-*")), [], "private stages are cleaned")

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


if __name__ == "__main__":
    unittest.main()
