"""A model's STEP is an export of its result (STORE.md §3, *Exports*).

The build publishes its result and its preview first; the build pool writes the file from
the stored tree and a parse of it is compared with the tree. A file that verifies is the
result; one that does not shows its own content, the build or the next door that touches it
says so, and the model's next run writes it again without names -- without running its body.
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support.cad_test_roots import IsolatedCadRoots
from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")

MODEL = """
from cadgen import step, label_shape
from cadgen import build123d as bd

@step()
def rig():
    plate = label_shape(bd.Box(20, 10, 4) - bd.Pos(5, 0, 0) * bd.Cylinder(2, 4), "plate")
    pin = label_shape(bd.Pos(15, 0, 6) * bd.Cylinder(2, 12), "pin")
    return bd.Compound(children=[plate, pin], label="rig")


if __name__ == "__main__":
    rig()
"""


class FilesAsExportsTest(unittest.TestCase):
    def setUp(self) -> None:
        import os

        roots = IsolatedCadRoots(self, prefix="files-as-exports-")
        self.enterContext(mock.patch.dict(os.environ, {"CADGEN_DAEMON": "0"}))
        self.root = roots.cad_root
        self.script = self.root / "rig.py"
        self.script.write_text(MODEL, encoding="utf-8")
        self.step = self.root / "rig.step"

    def build(self, *, force: bool = False) -> tuple[str, str]:
        """The run's outcome (``built``, or ``current`` where the body did not run) and
        what it said on stderr, as ``python rig.py --json`` says them."""
        from cadgen.cli._run_model import run_model_argv

        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            self.assertEqual(0, run_model_argv([str(self.script), "--json", *(["--force"] if force else [])]),
                             stderr.getvalue())
        (line,) = [line for line in stdout.getvalue().splitlines() if line.startswith("{")]
        return json.loads(line)["outcome"], stderr.getvalue()

    def record(self) -> dict:
        from cadgen.store.index import model_ref
        from cadgen.store.records import read_record

        return read_record(model_ref(self.script, "rig"))

    def entry(self) -> dict:
        from cadgen.store.records import document_entry_for_hash

        return document_entry_for_hash(hashlib.sha256(self.step.read_bytes()).hexdigest())

    def test_the_file_is_the_result_and_says_so_once_verified(self) -> None:
        from cadgen._internal.step_scene_loader import load_step_scene
        from cadgen.step_export import STEP_WRITER_SCHEME

        self.build()
        record, entry = self.record(), self.entry()
        self.assertEqual(record["tree"], entry["tree"], "the bytes map to the result they were written from")
        self.assertNotIn("verified", entry, "a build with no daemon waits for its verify")
        digest = hashlib.sha256(self.step.read_bytes()).hexdigest()
        self.assertEqual({"sha256": digest, "writer": STEP_WRITER_SCHEME}, record["outputs"][str(self.step.resolve())])
        names = load_step_scene(self.step).prototype_step_names.values()
        self.assertTrue(names and all(component.part and component.faces for component in names),
                        "the file names its parts and their elements")

    def test_the_preview_precedes_the_one_document_the_export_assembles(self) -> None:
        """The build assembles no XCAF document of its result before its preview is
        published: the export, on the pool, assembles the one document a build makes, after
        the preview -- so the result is on screen before any STEP-writer step runs."""
        from cadgen import step_export
        from cadgen.daemon import executors

        documents, previews = [], []
        assemble, emit = step_export._create_bin_xcaf_doc, executors.emit_event

        def assembled(*args, **kwargs):
            documents.append(len(previews))  # the preview events published before this document
            return assemble(*args, **kwargs)

        def emitted(event):
            if event.get("preview"):
                previews.append(len(documents))  # the documents assembled before this preview
            return emit(event)

        with mock.patch.object(step_export, "_create_bin_xcaf_doc", side_effect=assembled), \
                mock.patch.object(executors, "emit_event", side_effect=emitted):
            self.assertEqual("built", self.build()[0])
        self.assertTrue(previews, "the build published its preview")
        self.assertEqual(0, previews[0], "a document was assembled before the first preview")
        self.assertEqual(1, len(documents), "the export assembles the one document")
        self.assertGreaterEqual(documents[0], 1, "the export's document came after the preview")

    def test_a_door_confirms_a_pending_entry_before_it_answers(self) -> None:
        from cadgen.step_scene import read_scene
        from cadgen.store.records import note_document_tree

        self.build()
        entry = self.entry()
        digest = hashlib.sha256(self.step.read_bytes()).hexdigest()
        note_document_tree(digest, entry["tree"], producer=entry["producer"], verified=False)
        with mock.patch("cadgen.store.exports.verify_document", wraps=__import__(
                "cadgen.store.exports", fromlist=["verify_document"]).verify_document) as verify:
            scene = read_scene(self.step)
        self.assertEqual(1, verify.call_count)
        self.assertNotIn("verified", self.entry())
        self.assertEqual({"plate", "pin"}, {leaf.label for leaf in scene.leaves()})

    def test_a_file_that_does_not_hold_its_result_is_its_own_and_is_written_again_plain(self) -> None:
        from cadgen._internal.step_scene_loader import load_step_scene
        from cadgen._internal.step_verify import Mismatch

        # A writer that loses a face's place: what the verify finds is the file's.
        lost = [Mismatch(None, None, "faces off their place")]
        with mock.patch("cadgen._internal.step_verify.verify_scene", return_value=lost):
            outcome, said = self.build()
        self.assertEqual("built", outcome)
        self.assertIn("does not hold the result it was written from", said)
        record, entry = self.record(), self.entry()
        self.assertNotEqual(record["tree"], entry["tree"], "the file shows its own content")
        self.assertTrue(entry["differ"])
        written = self.step.read_bytes()

        # The next run writes it again without names, and never runs the body.
        self.assertEqual("current", self.build()[0])
        self.assertNotEqual(written, self.step.read_bytes())
        record, entry = self.record(), self.entry()
        self.assertTrue(record["outputs"][str(self.step.resolve())]["plain"])
        self.assertEqual(record["tree"], entry["tree"], "the plain file holds the result")
        self.assertTrue(all(not component.part and not component.faces
                            for component in load_step_scene(self.step).prototype_step_names.values()))
        # And it is kept from then on, plain.
        plain = self.step.read_bytes()
        self.assertEqual("current", self.build()[0])
        self.assertEqual(plain, self.step.read_bytes())

    def test_a_plain_file_that_does_not_hold_its_result_is_kept_as_its_own(self) -> None:
        """Written plain, a result is written to the same bytes again: a plain file that
        does not hold its result shows its own content, and the next run keeps it rather
        than write and verify it again -- the warning promises no rewrite."""
        from cadgen._internal.step_verify import Mismatch

        lost = [Mismatch(None, None, "faces off their place")]
        with mock.patch("cadgen._internal.step_verify.verify_scene", return_value=lost):
            said = self.build()[1]
            self.assertIn("the model's next run writes it without names", said)
            outcome, said = self.build()
            self.assertEqual("current", outcome)
            self.assertIn("does not hold the result it was written from, so it shows its own content: ", said)
            self.assertNotIn("next run", said)
            entry = self.entry()
            self.assertTrue(entry["differ"] and entry["plain"])
            plain = self.step.read_bytes()
            with mock.patch("cadgen.store.exports.export_step") as export:
                outcome, said = self.build()
            self.assertEqual(("current", 0), (outcome, export.call_count))
            self.assertEqual(plain, self.step.read_bytes())
            self.assertNotIn("does not hold the result", said)

    def test_a_declared_mesh_export_joins_the_build_without_a_doors_lookup_of_its_file(self) -> None:
        """A model's declared meshes are cut from its result and keyed on its STEP's bytes
        as its record names them -- the build's own knowledge -- so the command returns
        without a door's lookup of the file it just wrote, and without waiting on the
        file's verify."""
        self.script.write_text(MODEL.replace("from cadgen import step, label_shape", "from cadgen import step, stl, label_shape")
                               .replace("@step()", "@step()\n@stl"), encoding="utf-8")
        door = AssertionError("a door's lookup of the model's own file")
        with mock.patch("cadgen.store.exports.confirm_document", side_effect=door), \
                mock.patch("cadgen._internal.doors.document_snapshot", side_effect=door):
            outcome, said = self.build()
        self.assertEqual("built", outcome)
        self.assertIn("wrote STL", said)
        digest = hashlib.sha256(self.step.read_bytes()).hexdigest()
        stl = self.record()["outputs"][str(self.step.with_suffix(".stl").resolve())]
        self.assertEqual(digest, stl["document"])
        self.assertTrue(self.step.with_suffix(".stl").is_file())

    def test_a_runtime_that_cannot_name_its_producer_writes_plain_and_the_record_says_so(self) -> None:
        """A part key names its producer, so a runtime that cannot name its own writes the
        file plain, and the record's output entry and the file's entry say plain -- as
        written, not as planned -- so no door verifies the plain file as a named one."""
        from cadgen._internal.step_scene_loader import load_step_scene

        with mock.patch("cadgen.store.parts.producer_identity", side_effect=ValueError("no kernel version")):
            outcome, said = self.build()
        self.assertEqual("built", outcome)
        self.assertNotIn("does not hold the result", said)
        self.assertTrue(self.record()["outputs"][str(self.step.resolve())]["plain"])
        entry = self.entry()
        self.assertEqual((self.record()["tree"], False), (entry["tree"], "verified" in entry))
        self.assertTrue(all(not component.part and not component.faces
                            for component in load_step_scene(self.step).prototype_step_names.values()))
        self.assertEqual("current", self.build()[0])
        self.assertEqual("current", self.build()[0])

    def test_a_file_whose_entry_the_store_lost_is_mapped_and_verified_again(self) -> None:
        """A current model's file the store has no entry for is exported again by its next
        run: the same bytes, which keep the file and its stamp, mapped to the result and
        verified -- never left for a door to compile the result's own file as a foreign one."""
        import os

        from cadgen.store.index import remove_entry
        from cadgen.store.records import document_key

        self.build()
        digest = hashlib.sha256(self.step.read_bytes()).hexdigest()
        stamp = os.stat(self.step)
        producer = self.entry().get("producer")
        self.assertIsNotNone(producer, "the build's entry names no producer")
        remove_entry("document", document_key(digest))
        self.assertIsNone(self.entry())
        outcome, said = self.build()
        self.assertEqual("current", outcome)
        self.assertIn("rig.step has no entry in the store; writing it again", said)
        self.assertEqual(digest, hashlib.sha256(self.step.read_bytes()).hexdigest())
        after = os.stat(self.step)
        self.assertEqual((stamp.st_mtime_ns, stamp.st_ino), (after.st_mtime_ns, after.st_ino), "the file kept its stamp")
        entry = self.entry()
        self.assertEqual(self.record()["tree"], entry["tree"])
        self.assertNotIn("verified", entry)
        self.assertEqual(producer, entry.get("producer"), "the entry says what the file written again carries")
        self.assertEqual("current", self.build()[0])

    def test_a_verify_that_cannot_compare_leaves_the_file_its_own_content(self) -> None:
        """A verify that raises comparing the file with the result (a component the store
        cannot decode) has not verified it: the entry maps the bytes to the file's own content
        and says why, the build warns, and the next run writes the file plain."""
        error = RuntimeError("a component the store cannot decode")
        with mock.patch("cadgen._internal.step_verify.verify_scene", side_effect=error):
            outcome, said = self.build()
        self.assertEqual("built", outcome)
        self.assertIn("could not be verified against the result (RuntimeError: a component the store cannot decode)",
                      said)
        record, entry = self.record(), self.entry()
        self.assertNotEqual(record["tree"], entry["tree"], "the file shows its own content")
        self.assertNotIn("verified", entry, "nothing stays pending on a verify that ran")
        self.assertTrue(entry["differ"][0].startswith("the file could not be verified"))
        self.assertEqual("current", self.build()[0])
        self.assertTrue(self.record()["outputs"][str(self.step.resolve())]["plain"])
        self.assertEqual(self.record()["tree"], self.entry()["tree"], "the plain file holds the result")

    def test_a_door_compiles_a_file_whose_verify_could_not_answer(self) -> None:
        """A verify that cannot parse the file raises, and the entry stays pending: a door
        given it warns, naming the error, and has the bytes compiled as for a miss, so it
        answers from an entry a verify or a compile settled, never from the pending one."""
        from cadgen.step_scene import read_scene
        from cadgen.store.records import note_document_tree

        self.build()
        entry = self.entry()
        digest = hashlib.sha256(self.step.read_bytes()).hexdigest()
        note_document_tree(digest, entry["tree"], producer=entry["producer"], verified=False)
        stderr = io.StringIO()
        with mock.patch("cadgen._internal.step_scene_package._scene_from_selected_bytes",
                        side_effect=RuntimeError("the reader refused the file")), \
                mock.patch("cadgen.daemon.executors.submit_compile", wraps=__import__(
                    "cadgen.daemon.executors", fromlist=["submit_compile"]).submit_compile) as compiled, \
                contextlib.redirect_stderr(stderr):
            scene = read_scene(self.step)
        self.assertEqual({"plate", "pin"}, {leaf.label for leaf in scene.leaves()})
        self.assertEqual(1, compiled.call_count)
        self.assertIn("rig.step could not be verified against the result it was written from "
                      "(RuntimeError: the reader refused the file); it is compiled from its bytes", stderr.getvalue())
        self.assertNotIn("verified", self.entry())

    def test_a_door_asks_again_for_its_own_file_when_the_job_read_another_copy(self) -> None:
        """A verify is keyed by the bytes and the tree, so a door joins the job another door
        started for a copy of the same bytes; when that copy was replaced meanwhile the job
        answers nothing, and the door asks again for its own file -- unless that too has
        moved on, when it compiles the file's new bytes instead."""
        from cadgen.store.exports import confirm_document
        from cadgen.store.records import note_document_tree

        self.build()
        entry = self.entry()
        digest = hashlib.sha256(self.step.read_bytes()).hexdigest()
        note_document_tree(digest, entry["tree"], producer=entry["producer"], verified=False)
        asked: list[str] = []

        def resolve(request, **_kwargs):
            asked.append(request["document"])
            if len(asked) == 1:
                return {"ok": None}
            note_document_tree(digest, entry["tree"], producer=entry["producer"])
            return {"ok": True}

        with mock.patch("cadgen.daemon.artifacts.resolve_artifact", side_effect=resolve):
            self.assertEqual(entry["tree"], confirm_document(self.step, digest, entry["tree"]))
        self.assertEqual([str(self.step.resolve())] * 2, asked)
        self.assertNotIn("verified", self.entry())
        note_document_tree(digest, entry["tree"], producer=entry["producer"], verified=False)
        self.step.write_bytes(b"other bytes")
        with mock.patch("cadgen.daemon.artifacts.resolve_artifact", return_value={"ok": None}) as once:
            self.assertIsNone(confirm_document(self.step, digest, entry["tree"]))
        self.assertEqual(1, once.call_count)

    def test_a_daemon_build_hears_a_verify_that_failed(self) -> None:
        """Through the daemon the build returns before its verify; the verify's answer is
        heard when it comes, and a verify that failed is a warning naming the file and the
        error -- never an answer dropped with the entry left pending for good."""
        import threading

        from cadgen._internal import generation
        from cadgen.daemon.artifacts import ArtifactJobError

        heard, said = threading.Event(), []

        def noted(texts):
            said.extend(texts)
            heard.set()

        with mock.patch("cadgen.daemon.executors.use_daemon", return_value=True), \
                mock.patch("cadgen.daemon.client.artifact_payload", side_effect=lambda request, **_kw: {"artifact": request}), \
                mock.patch("cadgen.daemon.client.run_artifact",
                           side_effect=ArtifactJobError("artifact request failed: The geometry service failed (exit 1).")), \
                mock.patch.object(generation, "_note_warnings", side_effect=noted):
            generation._verify_saved("a" * 64, self.step.resolve(), "b" * 64, producer=None)
            self.assertTrue(heard.wait(30), "the verify's failure was never heard")
        self.assertEqual(["rig.step could not be verified against the result it was written from "
                          "(ArtifactJobError: artifact request failed: The geometry service failed (exit 1).)"], said)


class KeptRuleTest(unittest.TestCase):
    """A build keeps its STEP -- writes and verifies nothing -- only while its record's last
    build had the same tree, wrote the file with this writer, the file still has the bytes
    it recorded, the store maps those bytes to a tree, and they held the result; a file that
    did not is written plain, and the plan says why a file is written again."""

    TREE, DIGEST, STEP = "a" * 64, "b" * 64, "/work/STEP/part.step"

    def setUp(self) -> None:
        from cadgen.store.records import note_document_tree

        IsolatedCadRoots(self, prefix="kept-rule-")
        # The file's bytes map to the tree they were written from, verified.
        note_document_tree(self.DIGEST, self.TREE)

    def plan(self, *, output: dict | None = None, tree: str | None = None, on_disk: str | None = None,
             force: bool = False):
        from cadgen._internal.generation import _export_plan
        from cadgen.step_export import STEP_WRITER_SCHEME

        output = {"sha256": self.DIGEST, "writer": STEP_WRITER_SCHEME} if output is None else output
        return _export_plan({"tree": self.TREE, "outputs": {self.STEP: output}}, self.STEP, tree or self.TREE,
                            force=force, on_disk=on_disk or self.DIGEST)

    def test_a_file_is_kept_while_its_tree_writer_and_bytes_agree(self) -> None:
        from cadgen.step_export import STEP_WRITER_SCHEME

        kept = self.plan()
        self.assertEqual(({"sha256": self.DIGEST, "writer": STEP_WRITER_SCHEME}, ""), (kept.kept, kept.why))
        for why, plan, said in (("another result", self.plan(tree="c" * 64), ""),
                                ("other bytes on disk", self.plan(on_disk="f" * 64), "is not the file the record names"),
                                ("never written", self.plan(output={"sha256": "", "writer": STEP_WRITER_SCHEME}),
                                 "was never written"),
                                ("forced", self.plan(force=True), ""),
                                ("another writer", self.plan(output={"sha256": self.DIGEST, "writer": "cadgen-step-writer-3"}),
                                 "was written by another writer")):
            with self.subTest(why):
                self.assertIsNone(plan.kept)
                self.assertFalse(plan.plain)
                self.assertEqual(said, plan.why)

    def test_a_file_whose_entry_the_store_lost_is_written_again_to_the_same_bytes(self) -> None:
        from cadgen.store.index import remove_entry
        from cadgen.store.records import document_key

        remove_entry("document", document_key(self.DIGEST))
        plan = self.plan()
        self.assertEqual((None, False, "has no entry in the store"), (plan.kept, plan.plain, plan.why))

    def test_a_file_that_did_not_hold_its_result_is_written_plain(self) -> None:
        from cadgen.step_export import STEP_WRITER_SCHEME
        from cadgen.store.records import note_document_tree

        note_document_tree(self.DIGEST, "d" * 64, differ=["the file: faces off their place"])
        marked = self.plan()
        self.assertIsNone(marked.kept)
        self.assertTrue(marked.plain)
        self.assertEqual("did not hold its result", marked.why)
        self.assertEqual({"sha256": "", "writer": STEP_WRITER_SCHEME, "plain": True}, marked.output())
        # Another result, a forced build and another writer write the names again.
        for why, plan in (("another result", self.plan(tree="c" * 64)), ("forced", self.plan(force=True)),
                          ("another writer", self.plan(output={"sha256": self.DIGEST, "writer": "cadgen-step-writer-3"}))):
            with self.subTest(why):
                self.assertFalse(plan.plain)

    def test_a_plain_file_that_did_not_hold_its_result_is_kept(self) -> None:
        """The same result is written plain to the same bytes: nothing is gained by writing
        and verifying them again."""
        from cadgen.step_export import STEP_WRITER_SCHEME
        from cadgen.store.records import note_document_tree

        note_document_tree(self.DIGEST, "d" * 64, plain=True, differ=["the file: faces off their place"])
        output = {"sha256": self.DIGEST, "writer": STEP_WRITER_SCHEME, "plain": True}
        kept = self.plan(output=output)
        self.assertEqual(output, kept.kept)
        self.assertTrue(kept.plain)
        forced = self.plan(output=output, force=True)
        self.assertEqual((None, False), (forced.kept, forced.plain), "a forced build writes the names again")


if __name__ == "__main__":
    unittest.main()
