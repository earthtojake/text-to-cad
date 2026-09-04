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

from cadgen.daemon.jobs import JobLedger, declared_outputs, failure_message  # noqa: E402

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


class FailureMessageTest(unittest.TestCase):
    """The one line the ledger keeps about a failed job — what a reader shows as
    the reason, so the viewer never has to say only that "the last build failed"."""

    def test_the_cli_failed_line_wins_over_its_own_hint(self) -> None:
        output = (
            "[step-artifact] compile started\n"
            "[cadgen step compile] FAILED: RuntimeError: component be20 build failed: Unextractable: domain\n"
            "[cadgen step compile]   raised in cadgen/store/build.py:259\n"
            "[cadgen step compile] re-run with --verbose for the full traceback\n"
        )
        self.assertEqual(
            ("component be20 build failed: Unextractable: domain", "RuntimeError"),
            failure_message(output),
        )

    def test_a_verbose_traceback_ends_in_the_exception_line(self) -> None:
        output = (
            "Traceback (most recent call last):\n"
            '  File "x.py", line 1, in <module>\n'
            "    raise RuntimeError('failed to read STEP file: not a STEP')\n"
            "RuntimeError: failed to read STEP file: not a STEP\n"
        )
        self.assertEqual(("failed to read STEP file: not a STEP", "RuntimeError"), failure_message(output))

    def test_anything_else_is_the_last_line_that_is_not_the_hint(self) -> None:
        self.assertEqual(("and then died", None), failure_message("the worker said something\nand then died\n"))
        self.assertEqual(("", None), failure_message(""))
        self.assertEqual(
            ("something broke", None),
            failure_message("something broke\n[cadgen step compile] re-run with --verbose for the full traceback\n"),
        )

    def test_finish_records_the_reason_on_a_failed_job_only(self) -> None:
        ledger = JobLedger()
        job = ledger.start(tool="step-compile", subject="/tmp/x.step")
        ledger.finish(job, 1, error="failed to read STEP file: not a STEP")
        self.assertEqual("failed to read STEP file: not a STEP", ledger.snapshot()[0]["error"])
        ok = ledger.start(tool="step-compile", subject="/tmp/y.step")
        ledger.finish(ok, 0, error="ignored on success")
        self.assertIsNone([j for j in ledger.snapshot() if j["id"] == ok["id"]][0]["error"])


if __name__ == "__main__":
    unittest.main()
