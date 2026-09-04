"""The viewer's progress comes from the daemon's job ledger, for any job.

A document shows ``compiling · <phase> n/total`` while ANY job whose declared
outputs include it is running — a ``python model.py`` from a terminal, a
parent's child build, or the viewer's own compile alike — ``ready`` when its
tree is published, and ``failed`` when the latest such job failed. The viewer
reads nothing on disk for this and nothing about source: the daemon's ledger
is the only feed, matched by output path.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")

from cadgen.viewer import build_progress  # noqa: E402
from cadgen.viewer.artifact_status import artifact_status  # noqa: E402
from cadgen.viewer.cadgen_ops import CadgenOps  # noqa: E402

from tests.python.support.store_fixtures import seed_result  # noqa: E402

STEP_BYTES = b"ISO-10303-21;\nHEADER;\nENDSEC;\nDATA;\nENDSEC;\nEND-ISO-10303-21;\n"


def job(subject, outputs, state, *, id="job-1", phase=None, done=None, total=None, exit=None, tool="run", started=1.0):
    return {
        "id": id, "tool": tool, "subject": subject, "outputs": outputs, "argv": [], "state": state,
        "phase": phase, "done": done, "total": total, "startedAt": started, "updatedAt": started,
        "finishedAt": None if state in ("submitted", "queued", "building") else started + 1, "exit": exit,
    }


class _NeverCompiles:
    def compile(self, candidate, *, force=False):
        raise AssertionError("no compile should start in these tests")

    def in_flight(self, key):
        return False

    def shutdown(self):
        pass


class ProgressFeed(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.cache = self.root / "store"
        patcher = mock.patch.dict(os.environ, {"CADGEN_CACHE_DIR": str(self.cache)})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.document = self.root / "STEP" / "widget.step"
        self.document.parent.mkdir()
        self.document.write_bytes(STEP_BYTES)
        self.script = str(self.root / "src" / "widget.py")
        self.jobs: list[dict] = []
        feed = mock.patch.object(build_progress, "_daemon_jobs", side_effect=lambda now: list(self.jobs))
        feed.start()
        self.addCleanup(feed.stop)
        self.ops = CadgenOps(str(self.root), client=_NeverCompiles())

    def status(self) -> dict:
        return self.ops.artifact_status("STEP/widget.step")

    def test_a_cli_build_started_outside_the_viewer_shows_as_compiling_with_its_phase(self):
        self.jobs = [job(self.script, [str(self.document)], "building", phase="Meshing components", done=3, total=9)]
        status = self.status()
        self.assertEqual("compiling", status["state"])
        self.assertEqual("job-1", status["runId"])
        self.assertEqual(("Meshing components", 3, 9, True), (status["progress"]["phase"], status["progress"]["done"], status["progress"]["total"], status["progress"]["determinate"]))

    def test_a_parents_child_build_is_matched_by_the_childs_output_path(self):
        rig = str(self.root / "src" / "rig.py")
        self.jobs = [
            job(rig, [str(self.root / "STEP" / "rig.step")], "building", id="job-1", phase="generate"),
            job(self.script, [str(self.document)], "submitted", id="job-2", started=2.0),
        ]
        status = self.status()
        self.assertEqual(("compiling", "job-2"), (status["state"], status["runId"]))
        self.assertEqual("submitted", status["progress"]["phase"])
        self.assertFalse(status["progress"]["determinate"])

    def test_the_viewers_own_compile_shows_the_same_way(self):
        self.jobs = [job(str(self.document), [str(self.document)], "building", tool="step-compile", phase="compile")]
        status = self.status()
        self.assertEqual(("compiling", "compile"), (status["state"], status["progress"]["phase"]))

    def test_a_published_tree_is_ready_even_with_an_older_finished_job_listed(self):
        seed_result(self.document)
        self.jobs = [job(self.script, [str(self.document)], "done", exit=0)]
        self.assertEqual({"state": "rendered"}, self.status())

    def test_a_failed_job_with_no_tree_is_failed(self):
        self.jobs = [job(self.script, [str(self.document)], "failed", exit=1)]
        status = self.status()
        self.assertEqual(("failed", "build_failed"), (status["state"], status["reason"]))
        self.assertEqual({"runId": "job-1", "exit": 1, "tool": "run", "error": ""}, status["failed"])
        # No reason recorded: the generic sentence, and only then.
        self.assertEqual("The last compile of this document failed.", status["error"])

    def test_a_failed_job_reports_its_own_reason(self):
        failed = job(self.script, [str(self.document)], "failed", exit=1, tool="step-compile")
        failed["error"] = "component be20a9eae6b94690 build failed: Unextractable: surface domain does not cover face UV"
        self.jobs = [failed]
        status = self.status()
        self.assertEqual("failed", status["state"])
        # The description a person reads IS the job's last word — never "the last
        # build of this document failed" when the ledger knows more.
        self.assertEqual(failed["error"], status["error"])
        self.assertEqual(failed["error"], status["failed"]["error"])

    def test_a_failed_job_over_a_published_tree_renders_and_says_so(self):
        seed_result(self.document)
        self.jobs = [job(self.script, [str(self.document)], "failed", exit=1)]
        status = self.status()
        self.assertEqual("rendered", status["state"])
        self.assertEqual(1, status["failed"]["exit"])

    def test_a_later_success_clears_an_earlier_failure(self):
        seed_result(self.document)
        self.jobs = [
            job(self.script, [str(self.document)], "failed", id="job-1", exit=1, started=1.0),
            job(self.script, [str(self.document)], "done", id="job-2", exit=0, started=2.0),
        ]
        self.assertEqual({"state": "rendered"}, self.status())

    def test_a_job_for_another_document_is_not_this_documents_build(self):
        self.jobs = [job(str(self.root / "src" / "other.py"), [str(self.root / "STEP" / "other.step")], "building")]
        self.assertEqual("not-compiled", self.status()["state"])

    def test_no_daemon_means_no_feed(self):
        with mock.patch("cadgen.daemon.client.status", return_value=None):
            build_progress._cache = (0.0, [])
            self.assertEqual([], build_progress._daemon_jobs(now=10.0))
        self.assertIsNone(build_progress.build_progress_snapshot(self.document, jobs=[]))

    def test_the_snapshot_shape_the_status_machine_reads(self):
        running = build_progress.build_progress_snapshot(
            self.document, jobs=[job(self.script, [str(self.document)], "building", phase="p", done=1, total=2)]
        )
        self.assertEqual({"writing": True, "busy": False, "runId": "job-1"}, {k: running[k] for k in ("writing", "busy", "runId")})
        self.assertEqual("compiling", artifact_status(str(self.document), str(self.root), snapshot=running)["state"])


if __name__ == "__main__":
    unittest.main()
