"""The daemon's job ledger (``cadgen.daemon.jobs``): every job, whoever asked.

A job is listed with its declared output paths (from the script's decorators,
parsed statically; the document itself for a compile), follows the build tree's
event frames through submitted → building [phase n/total] → done | failed, and
stays listed for a while after it finishes so a failure is still visible.
"""

from __future__ import annotations

import json
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock

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
    def test_named_model_and_multi_model_request_declare_real_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp) / "models.py"
            script.write_text(
                "from cadgen import step\n@step\ndef first(): pass\n@step(out='second.step')\ndef second(): pass\n",
                encoding="utf-8",
            )
            self.assertEqual(declared_outputs(f"{script}::first", "run"), [str((Path(tmp) / "first.step").resolve())])
            self.assertEqual(declared_outputs(str(script), "run"), [str((Path(tmp) / "first.step").resolve()), str((Path(tmp) / "second.step").resolve())])

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

    def test_a_project_read_again_after_another_reads_its_own_lib(self):
        # The daemon reads every project's declarations in one process, and each
        # project keeps its helpers in a package named `lib`: a, then b, then a again
        # once its helper changed must evaluate a's `out=` from a's lib, not b's.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            self.addCleanup(_forget_project_modules, root)
            for name in ("a", "b"):
                src = root / name / "src"
                (src / "lib").mkdir(parents=True)
                (src / "lib" / "__init__.py").write_text("", encoding="utf-8")
                (src / "lib" / "dims.py").write_text(f"SIZE = '{name}1'\n", encoding="utf-8")
                (src / f"{name}.py").write_text(
                    "from cadgen import step\nfrom cadgen import build123d as bd\nfrom lib.dims import SIZE\n\n"
                    f"@step(out='{name}_' + SIZE + '.step')\ndef {name}():\n    return bd.Box(1, 1, 1)\n",
                    encoding="utf-8",
                )

            def declared(name):
                return [Path(path).name for path in declared_outputs(str(root / name / "src" / f"{name}.py"), "run")]

            self.assertEqual(["a_a1.step"], declared("a"))
            self.assertEqual(["b_b1.step"], declared("b"))
            (root / "a" / "src" / "lib" / "dims.py").write_text("SIZE = 'a2'\n", encoding="utf-8")
            self.assertEqual(["a_a2.step"], declared("a"))

    def test_a_script_that_stops_importing_is_listed_against_what_it_declared_last(self):
        # An edit that breaks a helper fails the build at import, which is also where its
        # declarations are read: the job is still listed against the document the script
        # writes, so the viewer showing that document gets the failure, not silence.
        from cadgen.viewer.build_progress import build_progress_snapshot

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            self.addCleanup(_forget_project_modules, root)
            (root / "lib").mkdir()
            (root / "lib" / "__init__.py").write_text("", encoding="utf-8")
            (root / "lib" / "dims.py").write_text("SIZE = 2\n", encoding="utf-8")
            script = root / "part.py"
            script.write_text(
                "from cadgen import step\nfrom cadgen import build123d as bd\nfrom lib.dims import SIZE\n\n"
                "@step\ndef part():\n    return bd.Box(SIZE, SIZE, SIZE)\n",
                encoding="utf-8",
            )
            output = str(script.with_suffix(".step").resolve())
            clock = Clock()
            ledger = JobLedger(clock=clock)
            built = ledger.start(tool="run", subject=str(script))
            self.assertEqual([output], built["outputs"])
            ledger.finish(built, 0)

            (root / "lib" / "dims.py").write_text("SIZE = undefined_name\n", encoding="utf-8")
            clock.now += 1
            broken = ledger.start(tool="run", subject=str(script))
            self.assertEqual([output], broken["outputs"])
            ledger.finish(broken, 1, error="NameError: name 'undefined_name' is not defined")
            status = build_progress_snapshot(output, jobs=ledger.snapshot())
            self.assertEqual("NameError: name 'undefined_name' is not defined", status["failed"]["error"])

            # A daemon that never read the script has nothing to list it against.
            self.assertEqual([], JobLedger(clock=Clock()).start(tool="run", subject=str(script))["outputs"])


def _forget_project_modules(root: Path) -> None:
    """Drop what a test's projects left in this process: their modules, sys.path roots."""
    import sys

    prefix = str(root)
    for name, module in list(sys.modules.items()):
        paths = [getattr(module, "__file__", None), *[str(entry) for entry in getattr(module, "__path__", None) or ()]]
        if any(path and str(path).startswith(prefix) for path in paths):
            sys.modules.pop(name, None)
    sys.path[:] = [entry for entry in sys.path if not entry.startswith(prefix)]


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

    def test_simultaneous_requests_for_same_model_remain_distinct(self):
        first = self.ledger.start(tool="run", subject=self.model, store_root="/one")
        second = self.ledger.start(
            tool="run", subject=self.model, store_root="/two", adopt_announced=True,
        )
        self.assertNotEqual(first["id"], second["id"])
        self.assertEqual(len(self.ledger.snapshot()), 2)
        self.ledger.observe(self._event(self.model, "building", job=first["id"], phase="first only"))
        self.assertEqual(first["phase"], "first only")
        self.assertIsNone(second["phase"])
        self.assertNotEqual(first["storeRoot"], second["storeRoot"])

    def test_producer_updates_are_ordered_and_snapshot_is_not_mutable(self):
        job = self.ledger.start(tool="run", subject=self.model)
        output = str(Path(self.model).with_suffix(".step"))
        for sequence, tree in ((4, "latest"), (2, "late")):
            self.ledger.observe(self._event(self.model, "building", job=job["id"], sequence=sequence,
                                           preview={"output": output, "tree": tree, "kinematics": {"mates": []}}))
        snapshot = self.ledger.snapshot()[0]
        self.assertEqual(snapshot["previews"][output]["tree"], "latest")
        snapshot["previews"][output]["tree"] = "mutation"
        self.assertEqual(self.ledger.snapshot()[0]["previews"][output]["tree"], "latest")
        self.ledger.observe(self._event(self.model, "done", job=job["id"]))
        self.assertEqual(job["state"], "building", "one model completing does not finish a multi-model request")
        self.ledger.finish(job, 0)
        self.assertEqual(job["state"], "done")
        self.ledger.observe(self._event(self.model, "building", job=job["id"], sequence=100))
        self.assertEqual(job["state"], "done", "late forwarded events cannot reopen completed requests")

    def test_a_job_keeps_only_what_its_readers_read_of_a_result(self):
        # The viewer's status reads a saved result's tree and digest; nothing reads
        # a preview's annotations, so a payload carrying them keeps none.
        job = self.ledger.start(tool="run", subject=self.model)
        output = str(Path(self.model).with_suffix(".step"))
        self.ledger.observe(self._event(self.model, "building", job=job["id"], sequence=1, preview={
            "output": output, "tree": "source", "kinematics": {"mates": [1] * 1000}, "appearance": {},
            "animation": "export const clips = {};", "surfaceProducer": {"scheme": 19}}))
        self.ledger.observe(self._event(self.model, "building", job=job["id"], sequence=2, saved={
            "output": output, "tree": "document", "documentHash": "abc", "appearance": {"materials": {}}}))
        snapshot = self.ledger.snapshot()[0]
        self.assertEqual(snapshot["previews"][output], {"output": output, "tree": "source", "sequence": 1})
        self.assertEqual(snapshot["savedResults"][output],
                         {"output": output, "tree": "document", "documentHash": "abc", "sequence": 2})

    def test_parent_announcements_cannot_claim_child_preview_and_epochs_are_unique(self):
        parent = self.ledger.start(tool="run", subject=self.model)
        child_path = str(Path(self.model).with_name("child.py"))
        self.ledger.observe(self._event(child_path, "building", job=parent["id"],
                                       preview={"output": "child.step", "tree": "child"}))
        self.assertNotIn("previews", parent)
        self.assertNotEqual(self.ledger.epoch, JobLedger().epoch)

    def test_a_job_follows_its_event_frames_to_done(self):
        job = self.ledger.start(tool="run", subject=self.model, argv=[self.model])
        self.assertEqual("submitted", job["state"])
        self.assertEqual([str(Path(self.model).with_suffix(".step"))], job["outputs"])
        self.ledger.observe(self._event(
            self.model, "building", phase="Meshing components", detail="finger linkage", done=3, total=9,
        ))
        listed = self.ledger.snapshot()[0]
        self.assertEqual(("building", "Meshing components", 3, 9), (listed["state"], listed["phase"], listed["done"], listed["total"]))
        self.assertEqual("finger linkage", listed["detail"])
        self.ledger.observe(self._event(self.model, "done"))
        self.ledger.finish(job, 0)
        listed = self.ledger.snapshot()[0]
        self.assertEqual(("done", 0), (listed["state"], listed["exit"]))

    def test_a_job_waiting_for_a_worker_says_so_until_it_has_one(self):
        # Nothing the job runs can say this: its worker does not exist yet.
        job = self.ledger.start(tool="run", subject=self.model)
        self.ledger.waiting(job, "Starting a geometry kernel")
        listed = self.ledger.snapshot()[0]
        self.assertEqual(("queued", "queued", "Starting a geometry kernel"),
                         (listed["state"], listed["phase"], listed["detail"]))
        self.ledger.waiting(job, None)
        self.ledger.observe(self._event(self.model, "building", job=job["id"], phase="generate"))
        listed = self.ledger.snapshot()[0]
        self.assertEqual(("building", "generate", ""), (listed["state"], listed["phase"], listed["detail"]))

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
        before = self.ledger.watch(timeout=0)
        announced = self.ledger.snapshot()[1]
        child = self.ledger.start(
            tool="run", subject=self.model, argv=[self.model], store_root=self.tmp.name,
            adopt_announced=True,
        )
        self.assertEqual(2, len(self.ledger.snapshot()))
        self.assertEqual(announced["id"], child["id"])
        self.assertNotIn("announced", child)
        self.assertEqual(str(Path(self.tmp.name).resolve()), child["storeRoot"])
        after = self.ledger.watch(before["jobsCursor"], timeout=0)
        self.assertEqual(int(before["jobsCursor"].rsplit(":", 1)[1]) + 1,
                         int(after["jobsCursor"].rsplit(":", 1)[1]),
                         "adoption is one atomic published mutation, without a phantom row")
        self.ledger.observe(self._event(self.model, "building", phase="generate"))
        self.ledger.finish(child, 0)
        self.assertEqual("done", [j for j in self.ledger.snapshot() if j["subject"] == self.model][0]["state"])

    def test_a_concurrent_request_cannot_orphan_a_childs_announced_row(self):
        self.ledger.observe(self._event(self.model, "submitted", parent="rig.py"))
        announced = self.ledger.snapshot()[0]
        self.clock.now += 1
        concurrent = self.ledger.start(tool="run", subject=self.model, store_root="/other")
        self.clock.now += 1

        child = self.ledger.start(
            tool="run", subject=self.model, store_root=self.tmp.name,
            adopt_announced=True,
        )

        jobs = self.ledger.snapshot()
        self.assertEqual(2, len(jobs), "the announcement must not remain submitted forever")
        self.assertEqual(announced["id"], child["id"])
        self.assertNotIn("announced", child)
        self.assertGreater(child["sequence"], concurrent["sequence"])
        self.assertEqual(self.clock.now, child["startedAt"])

    def test_finished_jobs_are_retained_then_swept(self):
        job = self.ledger.start(tool="step-compile", subject=str(Path(self.tmp.name) / "vendor.step"))
        self.ledger.finish(job, 1)
        self.assertEqual(1, len(self.ledger.snapshot()))
        self.clock.now += 61.0
        self.assertEqual([], self.ledger.snapshot())

    def test_a_transition_for_an_unknown_finished_job_is_ignored(self):
        self.ledger.observe(self._event(self.model, "done"))
        self.assertEqual([], self.ledger.snapshot())


class WaitingForAWorker(unittest.TestCase):
    def test_a_request_is_listed_as_starting_a_worker_until_it_has_one(self):
        from cadgen.daemon import server

        ledger, seen, sent = JobLedger(), {}, []

        class Worker:  # runs the job at once
            pid, extra = 7, False

            def send(self, request):
                seen["sent"] = ledger.snapshot()[0]

            def frames(self, **_kwargs):
                yield {"exit": 0, "pid": self.pid}

            def alive(self):
                return True

        def acquire(model, *, dependency, on_start):
            on_start()  # no warm worker: the pool starts one for this request
            seen["starting"] = ledger.snapshot()[0]
            return Worker()

        worker_pool = mock.Mock()
        worker_pool.acquire.side_effect = acquire
        conn = mock.Mock()
        conn.send.side_effect = lambda raw: sent.append(json.loads(raw))
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(server, "_POOL", worker_pool), \
                mock.patch.object(server, "_JOBS", ledger), mock.patch.object(server, "_watch_client"), \
                mock.patch.object(server, "_log"):
            server._handle_request(conn, {"tool": "run", "argv": ["widget.py"], "cwd": tmp})
        self.assertEqual(("queued", "Starting a geometry kernel"),
                         (seen["starting"]["state"], seen["starting"]["detail"]))
        self.assertEqual("", seen["sent"]["detail"], "the wait was over before the job reached its worker")
        self.assertEqual({"exit": 0}, sent[-1])
        self.assertEqual("done", ledger.snapshot()[0]["state"])


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
