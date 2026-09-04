"""The daemon's job ledger (``cadgen.daemon.jobs``): every job, whoever asked.

A job is listed with its declared output paths (from the script's decorators,
parsed statically; the document itself for a compile), follows the build tree's
event frames through submitted → building [phase n/total] → done | failed, and
stays listed for a while after it finishes so a failure is still visible.
"""

from __future__ import annotations

import tempfile
import textwrap
import unittest
from pathlib import Path

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")

from cadgen.daemon.jobs import JobLedger, declared_outputs  # noqa: E402

MODEL = """
from cadgen import step, stl
from cadgen import build123d as bd


@stl(out="../MESH/widget.stl")
@step(out="../STEP/widget.step")
def widget():
    return bd.Box(1, 1, 1)
"""


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


class DeclaredOutputs(unittest.TestCase):
    def test_a_model_scripts_outputs_are_its_declared_document_and_meshes(self):
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp) / "src" / "widget.py"
            script.parent.mkdir()
            script.write_text(textwrap.dedent(MODEL), encoding="utf-8")
            outputs = declared_outputs(str(script), "run")
        self.assertEqual(
            [str((Path(tmp) / "STEP" / "widget.step").resolve()), str((Path(tmp) / "MESH" / "widget.stl").resolve())],
            [str(Path(p)) for p in outputs],
        )

    def test_a_sibling_default_and_a_compiles_document(self):
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp) / "plain.py"
            script.write_text("from cadgen import step\nfrom cadgen import build123d as bd\n\n@step\ndef plain():\n    return bd.Box(1, 1, 1)\n", encoding="utf-8")
            self.assertEqual([str(script.with_suffix(".step").resolve())], [str(Path(p)) for p in declared_outputs(str(script), "run")])
            document = Path(tmp) / "vendor.step"
            self.assertEqual([str(document.resolve())], [str(Path(p)) for p in declared_outputs(str(document), "step-compile")])

    def test_an_unparseable_script_declares_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp) / "broken.py"
            script.write_text("def (\n", encoding="utf-8")
            self.assertEqual([], declared_outputs(str(script), "run"))


class Lifecycle(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = Clock()
        self.ledger = JobLedger(retain_seconds=60.0, clock=self.clock)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.model = str((Path(self.tmp.name) / "widget.py").resolve())
        Path(self.model).write_text("from cadgen import step\nfrom cadgen import build123d as bd\n\n@step\ndef widget():\n    return bd.Box(1, 1, 1)\n", encoding="utf-8")

    def _event(self, model, state, **extra):
        return {"event": {"model": model, "state": state, **extra}}

    def test_a_job_follows_its_event_frames_to_done(self):
        job = self.ledger.start(tool="run", subject=self.model, argv=[self.model])
        self.assertEqual("submitted", job["state"])
        self.assertEqual([str(Path(self.model).with_suffix(".step"))], job["outputs"])
        self.ledger.observe(self._event(self.model, "building", phase="Meshing components", done=3, total=9))
        listed = self.ledger.snapshot()[0]
        self.assertEqual(("building", "Meshing components", 3, 9), (listed["state"], listed["phase"], listed["done"], listed["total"]))
        self.ledger.observe(self._event(self.model, "done"))
        self.ledger.finish(job, 0)
        listed = self.ledger.snapshot()[0]
        self.assertEqual(("done", 0), (listed["state"], listed["exit"]))

    def test_a_non_zero_exit_is_a_failed_job(self):
        job = self.ledger.start(tool="run", subject=self.model)
        self.ledger.observe(self._event(self.model, "building", phase="generate"))
        self.ledger.finish(job, 1)
        self.assertEqual(("failed", 1), (self.ledger.snapshot()[0]["state"], self.ledger.snapshot()[0]["exit"]))

    def test_a_childs_announcement_lists_it_before_its_own_request_arrives(self):
        parent = str((Path(self.tmp.name) / "rig.py").resolve())
        self.ledger.start(tool="run", subject=parent)
        # The parent's worker announces the child it submitted (executors.submit).
        self.ledger.observe(self._event(self.model, "submitted", parent=parent))
        subjects = [job["subject"] for job in self.ledger.snapshot()]
        self.assertEqual([parent, self.model], subjects)
        # The child's own request arrives: it is the SAME row, not a second one.
        child = self.ledger.adopt(self.ledger.start(tool="run", subject=self.model, argv=[self.model]), subject=self.model, tool="run", argv=[self.model])
        self.assertEqual(2, len(self.ledger.snapshot()))
        self.ledger.observe(self._event(self.model, "building", phase="generate"))
        self.ledger.finish(child, 0)
        self.assertEqual("done", [j for j in self.ledger.snapshot() if j["subject"] == self.model][0]["state"])

    def test_finished_jobs_are_retained_then_swept(self):
        job = self.ledger.start(tool="step-compile", subject=str(Path(self.tmp.name) / "vendor.step"))
        self.ledger.finish(job, 1)
        self.assertEqual(1, len(self.ledger.snapshot()))
        self.clock.now += 61.0
        self.assertEqual([], self.ledger.snapshot())

    def test_a_transition_for_an_unknown_finished_job_is_ignored(self):
        self.ledger.observe(self._event(self.model, "done"))
        self.assertEqual([], self.ledger.snapshot())


if __name__ == "__main__":
    unittest.main()
