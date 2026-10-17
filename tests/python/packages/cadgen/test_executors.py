"""The transient executor: a real subprocess per job, and the events a job emits.

``CADGEN_DAEMON=0`` is the path tests and CI run, so it is tested with a real worker on
a real (temporary) store. The one job a build hands to the pool is a document compile
(``submit_compile``): what it must do is compile into the store the job names, report
the document's transitions through the event sink, capture a failed job's output for
the error, and never block the caller until ``wait()``.
"""

from __future__ import annotations

import hashlib
import os
import threading
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support.paths import add_repo_path
from tests.python.support.tmp_root import temporary_directory

add_repo_path("packages/cadgen/src")

from cadgen.daemon import executors  # noqa: E402


class TransientCompile(unittest.TestCase):
    def setUp(self):
        self.tmp = temporary_directory(prefix="cadgen-executors-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.store = self.root / "store"
        self.state = self.root / "state"
        env = {"CADGEN_DAEMON": "0", "CADGEN_CACHE_DIR": str(self.store), "CADGEN_DAEMON_STATE_DIR": str(self.state)}
        patcher = mock.patch.dict(os.environ, env)
        patcher.start()
        self.addCleanup(patcher.stop)
        os.environ.pop("CADGEN_DAEMON_CHILD", None)
        self.events: list[dict] = []
        self.closed = threading.Event()  # the tree's line for the document closed: done or failed

        def observe(event: dict) -> None:
            self.events.append(event)
            if event.get("state") in ("done", "failed"):
                self.closed.set()

        executors.set_event_sink(observe)
        self.addCleanup(executors.set_event_sink, None)

    def _vendor_document(self) -> Path:
        # A document whose bytes the store has no tree for: written by the kernel's
        # own exporter, never by a build.
        from build123d import Box, export_step

        document = self.root / "vendor.step"
        export_step(Box(10.0, 4.0, 2.0), str(document))
        return document

    def test_a_compile_lands_its_tree_in_the_jobs_store_and_closes_its_line(self):
        from cadgen.store.records import tree_for_document_hash

        document = self._vendor_document()
        other = self.root / "other-store"
        job = executors.submit_compile(document, store_root=other, parent=Path("/models/parent.py"))
        self.assertFalse(job.done, "submit must return before the compile finishes")
        self.assertEqual(job.wait(timeout=300), 0, job.output())
        self.assertTrue(self.closed.wait(30), "the document's line never closed")
        digest = hashlib.sha256(document.read_bytes()).hexdigest()
        with mock.patch.dict(os.environ, {"CADGEN_CACHE_DIR": str(other)}):
            self.assertIsNotNone(tree_for_document_hash(digest), "the tree did not land in the job's store")
        self.assertIsNone(tree_for_document_hash(digest), "the compile wrote into the environment's store")
        states = [(e["model"], e["state"]) for e in self.events]
        self.assertEqual(states[0], (str(document), "submitted"))
        self.assertEqual(Path(self.events[0]["parent"]), Path(os.path.abspath("/models/parent.py")))
        self.assertEqual(states[1], (str(document), "building"))
        self.assertEqual(self.events[1]["phase"], "compile")
        self.assertEqual(states[-1], (str(document), "done"))

    def test_a_failed_compile_reports_failed_and_keeps_its_output(self):
        document = self.root / "broken.step"
        document.write_text("ISO-10303-21;\nHEADER;\nENDSEC;\nDATA;\nthis is not a document\n", encoding="utf-8")
        job = executors.submit_compile(document)
        self.assertNotEqual(job.wait(timeout=300), 0)
        self.assertIn("broken.step", job.output())
        self.assertTrue(self.closed.wait(30), "the document's line never closed")
        self.assertEqual((self.events[-1]["model"], self.events[-1]["state"]), (str(document), "failed"))

    def test_use_daemon_is_false_when_opted_out(self):
        self.assertFalse(executors.use_daemon())


if __name__ == "__main__":
    unittest.main()
