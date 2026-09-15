"""The editing feed cannot replace saved-byte resolution or cross a served root."""
from __future__ import annotations

import os
import unittest
from pathlib import Path
from unittest import mock

from cadgen.store.trees import get_tree, put_tree
from cadgen.store.objects import put_object
from cadgen.viewer.backend import ForbiddenAssetError
from cadgen.viewer.preview import preview_status, preview_update
from tests.python.support.tmp_root import generated_cad_directory


class EditingPreviewTests(unittest.TestCase):
    def setUp(self):
        temporary = generated_cad_directory(prefix="preview-feed-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.output = str(self.root / "new.step")
        self.store = str(self.root / "store")
        env = mock.patch.dict(os.environ, {"CADGEN_CACHE_DIR": self.store})
        env.start()
        self.addCleanup(env.stop)
        from build123d import Solid
        from cadgen.store.build import build_tree_from_compound
        self.tree = build_tree_from_compound(Solid.make_box(1, 1, 1), root_name="preview")[0]

    def missing_tree(self):
        tree = get_tree(self.tree)
        tree["components"][next(iter(tree["components"]))]["brep"] = "f" * 64
        # Corrupt persistence is injected as raw CAS bytes, bypassing the
        # writer's validation deliberately to exercise a reader's refusal.
        import json
        return put_object(json.dumps(tree).encode())

    def job(self, revision=1, **extra):
        return {"id": f"epoch:job-{revision}", "epoch": "epoch", "sequence": revision,
                "tool": "run",
                "storeRoot": self.store, "outputs": [self.output], "state": "building",
                "subject": "/private/source.py", **extra}

    def preview(self):
        return {self.output: {"tree": self.tree, "kinematics": {"mates": []}, "sequence": 4}}

    def test_first_build_serves_complete_tree_without_a_saved_file_or_record(self):
        result = preview_status(str(self.root), self.output, jobs=[self.job(previews=self.preview())])
        self.assertFalse(Path(self.output).exists())
        self.assertEqual(result["preview"]["tree"], self.tree)
        self.assertEqual(result["file"], "new.step")
        self.assertEqual(result["preview"]["url"], f"/__cad/store?file={self.tree}")
        self.assertNotIn("subject", result)
        self.assertNotIn("storeRoot", result)
        self.assertNotIn("saved", result)

    def test_changed_feed_uses_its_atomic_job_snapshot_and_only_exposes_cursor(self):
        payload = {"jobsCursor": "epoch:8", "jobs": [self.job(previews=self.preview())]}
        with mock.patch("cadgen.daemon.client.watch_jobs", return_value=payload) as watch, \
                mock.patch("cadgen.viewer.preview._daemon_jobs", side_effect=AssertionError("extra poll")):
            result = preview_update(str(self.root), self.output, after="epoch:7")
        watch.assert_called_once_with("epoch:7", output=self.output, store_root=self.store)
        self.assertEqual(result["feedCursor"], "epoch:8")
        self.assertEqual(result["preview"]["tree"], self.tree)
        self.assertNotIn("jobs", result)
        self.assertNotIn("subject", result)

    def test_saturated_feed_keeps_cursor_and_requests_slow_client_retry(self):
        payload = {"jobsCursor": "epoch:8", "jobs": [], "jobsWatchLimited": True}
        with mock.patch("cadgen.daemon.client.watch_jobs", return_value=payload):
            result = preview_update(str(self.root), self.output, after="epoch:8")
        self.assertEqual(result["feedCursor"], "epoch:8")
        self.assertTrue(result["feedLimited"])

    def test_one_response_verifies_shared_tree_once_without_retaining_brep_payloads(self):
        from cadgen.catalog import artifact_file_hash
        from cadgen.store.records import note_document_tree
        from cadgen.store.trees import capture_tree

        Path(self.output).write_bytes(b"saved document")
        digest = artifact_file_hash(Path(self.output))
        note_document_tree(digest, self.tree)
        jobs = [self.job(previews=self.preview(), savedResults={
            self.output: {"tree": self.tree, "documentHash": digest}})]
        with mock.patch("cadgen.viewer.preview.capture_tree", wraps=capture_tree) as capture:
            result = preview_status(str(self.root), self.output, jobs=jobs)
        capture.assert_called_once_with(self.tree, retain_payloads=False)
        self.assertEqual(result["preview"]["tree"], result["saved"]["tree"])

    def test_notification_heartbeat_rechecks_missing_geometry(self):
        payload = {"jobsCursor": "epoch:8", "jobs": [self.job(previews=self.preview())]}
        with mock.patch("cadgen.daemon.client.watch_jobs", return_value=payload):
            first = preview_update(str(self.root), self.output)
            self.assertIn("preview", first)
            from cadgen.store.objects import object_path
            entry = next(iter(get_tree(self.tree)["components"].values()))
            object_path(entry["brep"]).unlink()
            second = preview_update(str(self.root), self.output, after=first["feedCursor"])
        self.assertNotIn("preview", second)
        self.assertTrue(second["previewUnavailable"])

    def test_invalid_output_is_rejected_before_waiting_on_the_daemon(self):
        with mock.patch("cadgen.daemon.client.watch_jobs", side_effect=AssertionError("invalid wait")):
            with self.assertRaises(ValueError):
                preview_update(str(self.root), ".hidden/new.step", after="epoch:7")

    def test_newest_request_wins_even_when_old_one_finishes_later(self):
        jobs = [self.job(1, state="done", updatedAt=1000, previews=self.preview()),
                self.job(2, updatedAt=999)]
        result = preview_status(str(self.root), self.output, jobs=jobs)
        self.assertEqual(result["revision"], 2)
        self.assertNotIn("preview", result)

    def test_compiling_saved_bytes_cannot_supersede_an_editing_request(self):
        jobs = [self.job(1, previews=self.preview()),
                self.job(2, tool="step-compile", state="done")]
        result = preview_status(str(self.root), self.output, jobs=jobs)
        self.assertEqual(result["revision"], 1)
        self.assertEqual(result["preview"]["tree"], self.tree)
        self.assertNotIn("saved", result)

    def test_coalesced_subscriber_does_not_advance_edit_ordering(self):
        from cadgen.daemon.jobs import JobLedger

        ledger = JobLedger()
        producer = ledger.start(tool="run", subject="model.py", store_root=self.store)
        producer.update(outputs=[self.output], previews=self.preview(), state="building")
        follower = ledger.start(tool="run", subject="model.py", store_root=self.store, editing_producer=False)
        follower.update(outputs=[self.output])
        result = preview_status(str(self.root), self.output, jobs=ledger.snapshot())
        self.assertEqual(result["request"], producer["id"])
        ledger.accept_editing_producer(follower)
        result = preview_status(str(self.root), self.output, jobs=ledger.snapshot())
        self.assertEqual(result["request"], follower["id"])

    def test_other_store_and_output_are_not_visible(self):
        result = preview_status(str(self.root), self.output, jobs=[
            self.job(previews=self.preview(), storeRoot=str(self.root / "other")),
            self.job(outputs=[str(self.root / "other.step")]),
        ])
        self.assertEqual(result["state"], "disconnected")

    def test_missing_component_does_not_publish_an_incomplete_preview(self):
        missing = self.missing_tree()
        result = preview_status(str(self.root), self.output, jobs=[self.job(
            previews={self.output: {"tree": missing}})])
        self.assertNotIn("preview", result)
        self.assertIn("no longer available", result["error"])
        self.assertTrue(result["previewUnavailable"])

    def test_expired_preview_preserves_a_separately_validated_saved_result(self):
        from cadgen.catalog import artifact_file_hash
        from cadgen.store.records import note_document_tree

        Path(self.output).write_bytes(b"saved document")
        digest = artifact_file_hash(Path(self.output))
        note_document_tree(digest, self.tree)
        missing = self.missing_tree()
        job = self.job(state="done", previews={self.output: {"tree": missing}},
                       savedResults={self.output: {"tree": self.tree, "documentHash": digest}})
        with mock.patch("cadgen.store.records.read_record", side_effect=AssertionError("model read")), \
             mock.patch("cadgen.store.records.model_for_output", side_effect=AssertionError("output read")):
            result = preview_status(str(self.root), self.output, jobs=[job])
        self.assertNotIn("preview", result)
        self.assertTrue(result["previewUnavailable"])
        self.assertEqual(result["saved"]["documentHash"], digest)
        self.assertEqual(result["saved"]["tree"], self.tree)

    def test_outside_root_and_hidden_paths_are_rejected(self):
        with self.assertRaises(ForbiddenAssetError):
            preview_status(str(self.root), str(self.root.parent / "outside.step"), jobs=[])
        with self.assertRaises(ValueError):
            preview_status(str(self.root), ".hidden/new.step", jobs=[])

    def test_completed_event_cannot_label_different_disk_bytes_as_saved(self):
        Path(self.output).write_text("different saved bytes", encoding="utf-8")
        result = preview_status(str(self.root), self.output, jobs=[self.job(savedResults={
            self.output: {"tree": self.tree, "documentHash": "f" * 64}})])
        self.assertNotIn("saved", result)
        self.assertIn("changed", result["error"])

    def test_saved_validation_selects_digest_and_tree_from_one_file_revision(self):
        from cadgen.store.records import note_document_tree

        old_digest = "a" * 64
        Path(self.output).write_bytes(b"old saved document")
        note_document_tree(old_digest, self.tree)
        hashes = 0

        def replace_after_selection(_path):
            nonlocal hashes
            hashes += 1
            Path(self.output).write_bytes(b"new saved document")
            return old_digest if hashes == 1 else "b" * 64

        job = self.job(state="done", savedResults={
            self.output: {"tree": self.tree, "documentHash": old_digest},
        })
        with mock.patch("cadgen.catalog.artifact_file_hash", side_effect=replace_after_selection):
            result = preview_status(str(self.root), self.output, jobs=[job])
        self.assertEqual(1, hashes, "saved validation must not hash a replacement revision")
        self.assertEqual((old_digest, self.tree),
                         (result["saved"]["documentHash"], result["saved"]["tree"]))

    def test_noop_completion_resolves_current_saved_bytes_without_a_record(self):
        from cadgen.catalog import artifact_file_hash
        from cadgen.store.records import note_document_tree

        Path(self.output).write_bytes(b"saved document")
        digest = artifact_file_hash(Path(self.output))
        note_document_tree(digest, self.tree)
        result = preview_status(str(self.root), self.output, jobs=[self.job(state="done")])
        self.assertEqual(result["saved"]["documentHash"], digest)
        self.assertEqual(result["saved"]["tree"], self.tree)
