"""A manufacturing check (``cad <type> dfm``, ``cad.<type>.dfm``) measured where the engine holds the
document: a model's in its warm worker, a STEP's and an xbf's -- and a document no warm worker holds -- in
the engine's checks process, nothing exported or read again (``worker._check``, ``Daemon.check``). Its result
equals the one the same document gets read from a file in a process of its own, for every process, with no
process given and ranking candidates; the same check of an unchanged document is the engine's kept result
(``checks``), measuring nothing; an edit, other options or another file's bytes -- even ones of the same size
and time -- are measured again; a build of the model's script cancels a check running in its worker or
waiting for it, and a cancel landing as a check ends hangs nothing; a worker killed in a check says so. On
an engine, a state and a cache folder of this file's own."""

from __future__ import annotations

import dataclasses
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import textwrap
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest import mock

from tests.python.support import engine_daemon
from tests.python.support.paths import add_sources

SRC = add_sources()  # the three packages' sources, as PYTHONPATH names them

# Two models: a plate with a pocket, and an assembly of a thin sheet and one boss placed twice, once
# turned -- a part with two occurrences, placed off the identity.
MODELS = """
import build123d as bd
from cad import model


@model
def plate():
    part = bd.Box(40, 30, 10) - bd.Pos(0, 0, 3) * bd.Box(20, 10, 4.01)
    part.label = "plate"
    return part


@model
def pair():
    sheet = bd.Box(60, 40, 2) - bd.Pos(10, 0, 0) * bd.Cylinder(3, 2)
    sheet.label = "sheet"
    boss = bd.Cylinder(6, 14) - bd.Cylinder(2.5, 14)
    first = bd.Pos(-15, 0, 8) * boss
    second = bd.Rot(0, 0, 30) * bd.Pos(20, 12, 8) * boss
    first.label, second.label = "boss_a", "boss_b"
    return bd.Compound(children=[sheet, first, second], label="pair")


if __name__ == "__main__":
    print(plate().id)
    print(pair().id)
"""

# A part whose material declares its process (machined aluminum): checked for cnc given none, its material
# read from the engine's document (``material_from_json``) as from the file (the XCAF label's).
DECLARED = """
import build123d as bd
from bd_materials import metals
from bd_materials.processes import machined
from cad import model


@model
def block():
    part = bd.Box(30, 20, 12) - bd.Pos(0, 0, 4) * bd.Box(12, 8, 4.01)
    part.label, part.material = "block", metals.aluminum(process=machined())
    return part


if __name__ == "__main__":
    print(block().id)
"""

PROCESSES = ("cnc", "sheet", "molding", "printing")
JOIN_SECONDS = 120.0


def setUpModule() -> None:
    engine_daemon.isolate(unittest.addModuleCleanup)


def _plain(result: Any) -> Any:
    """A result as its ``--json`` says it: tuples and lists alike."""
    return json.loads(json.dumps(dataclasses.asdict(result), default=str))


def _counts() -> dict[str, int]:
    from cad.engine import api

    return api.status()["checks"]


def _until(case: unittest.TestCase, condition: Any, what: str) -> None:
    """``condition()`` awaited: a test that waits too long fails saying for what."""
    deadline = time.monotonic() + JOIN_SECONDS
    while not condition():
        case.assertLess(time.monotonic(), deadline, f"never: {what}")
        time.sleep(0.02)


class Fixture:
    """A script of ``text`` in a folder of its own, built through the engine; its models' ids."""

    def __init__(self, case: unittest.TestCase, text: str, env: dict[str, str] | None = None) -> None:
        self.case = case
        self.folder = Path(os.path.realpath(tempfile.mkdtemp(prefix="engine-dfm-")))
        case.addCleanup(shutil.rmtree, self.folder, True)
        self.script = self.folder / "parts.py"
        self.env = engine_daemon.watched({**os.environ, "PYTHONPATH": str(SRC), **(env or {})}, case.addCleanup)
        self.ids = self.build(text)

    def build(self, text: str | None = None) -> list[str]:
        if text is not None:
            self.script.write_text(textwrap.dedent(text), encoding="utf-8")
        built = engine_daemon.run([sys.executable, str(self.script)], cwd=self.folder, env=self.env)
        self.case.assertEqual(built.returncode, 0, built.stderr)
        self.said = built.stderr
        ids = [word for word in built.stdout.split() if len(word) == 36 and word.count("-") == 4]
        return list(dict.fromkeys(ids))  # each model once, as its run printed it (its id: line and the script's)


def _today(document_type: str, source: Any, label: Path, process: str | None, candidates: bool = False,
           **given: Any) -> Any:
    """The check as it was before the engine measured it: the document read from its file in this process
    (a model's exported to an xbf first), then measured and finished here."""
    from cad._internal import manufacturing
    from cad.build123d import _dfm_check

    resolved = manufacturing.options(document_type, process, given, candidates=candidates)
    if process is None:
        process, resolved, report = _dfm_check.measure_declared(document_type, source, given, candidates)
    else:
        report = _dfm_check.measure(document_type, source, process, resolved, candidates)
    return manufacturing.finish(label, {"process": process, **report}, process, resolved, candidates)


class Checking(threading.Thread):
    """A check run in a thread: what it answered, or raised."""

    def __init__(self, check: Any) -> None:
        super().__init__(daemon=True)
        self.check, self.answered = check, None

    def run(self) -> None:
        try:
            self.answered = self.check()
        except Exception as error:  # noqa: BLE001 - what the check raised is the test's to read
            self.answered = error

    def result(self, case: unittest.TestCase) -> Any:
        self.join(JOIN_SECONDS)
        case.assertFalse(self.is_alive(), f"the check did not answer within {JOIN_SECONDS:.0f} s")
        return self.answered


class SameResultTest(unittest.TestCase):
    """The engine's check of a document equals the check of it read from a file, process by process, and
    every finding's ref resolves in the engine's inspect."""

    def test_a_model_and_its_files_measure_as_they_read(self) -> None:
        import build123d as bd

        import cad
        from cad.engine import api

        fixture = Fixture(self, MODELS)
        for ident in fixture.ids:
            exported = fixture.folder / f"{ident}.xbf"
            api.export(ident, exported, progress=False)
            for process in PROCESSES:
                with self.subTest(model=ident, process=process):
                    held = cad.model.dfm(ident, process=process)
                    self.assertEqual(_plain(held), _plain(_today("model", exported, Path(ident), process)))
                    for finding in [f for f in held.findings if f.location and "/" in f.location][:2]:
                        self.assertIn(cad.model.inspect(ident, finding.location)["kind"], ("face", "edge"))
        plate = fixture.ids[0]
        exported = fixture.folder / f"{plate}.xbf"
        for process in ("molding", "printing"):
            with self.subTest(candidates=process):
                self.assertEqual(_plain(cad.model.dfm(plate, process=process, candidates=True)),
                                 _plain(_today("model", exported, Path(plate), process, candidates=True)))
        step = fixture.folder / "part.step"
        bd.export_step(bd.Box(30, 20, 6) - bd.Pos(5, 0, 0) * bd.Cylinder(2, 6), str(step))
        xbf = fixture.folder / f"{fixture.ids[1]}.xbf"
        for document_type, path in (("step", step), ("xbf", xbf)):
            for process in PROCESSES:
                with self.subTest(file=path.name, process=process):
                    held = getattr(cad, document_type).dfm(path, process=process)
                    self.assertEqual(_plain(held), _plain(_today(document_type, path, path.resolve(), process)))
                    for finding in [f for f in held.findings if f.location and "face " in f.location][:1]:
                        self.assertEqual(getattr(cad, document_type).inspect(path, finding.location)["kind"], "face")

    def test_a_declared_process_and_material_read_as_the_file_reads_them(self) -> None:
        """No process given: the part's declared process and material, read from the engine's document as from
        its xbf (``material_from_json`` against the XCAF label), a document held by no worker -- the engine
        stopped, then its cache -- measured in the checks process alike."""
        import cad
        from cad.engine import api

        fixture = Fixture(self, DECLARED)
        (block,) = fixture.ids
        exported = fixture.folder / "block.xbf"
        api.export(block, exported, progress=False)
        held = cad.model.dfm(block)
        today = _today("model", exported, Path(block), None)
        self.assertEqual(_plain(held), _plain(today))
        self.assertEqual(held.measurements["process"], "cnc")
        self.assertTrue({"process_declared", "material_declared"} <= {f.code for f in held.findings})
        self.assertEqual(_plain(cad.xbf.dfm(exported)), _plain(_today("xbf", exported, exported.resolve(), None)))
        api.stop()  # its worker gone: the next check reads the document the engine's cache holds
        self.assertEqual(_plain(cad.model.dfm(block)), _plain(today))
        self.assertEqual(_counts()["measured"], 1, "measured again by the restarted engine, in its checks process")


class KeptResultTest(unittest.TestCase):
    """The same check of the same document version is the engine's kept result: no process measures it."""

    def test_a_check_is_kept_by_its_document_version_and_its_options(self) -> None:
        import build123d as bd

        import cad

        fixture = Fixture(self, MODELS)
        plate = fixture.ids[0]
        first = cad.model.dfm(plate, process="cnc", material="aluminum")
        before = _counts()
        again = cad.model.dfm(plate, process="cnc", material="aluminum")
        self.assertEqual(_plain(again), _plain(first))
        self.assertEqual((_counts()["measured"], _counts()["reused"]), (before["measured"], before["reused"] + 1))

        cad.model.dfm(plate, process="cnc", material="steel")  # other options: measured
        self.assertEqual(_counts()["measured"], before["measured"] + 1)

        fixture.build()  # the same code run again in the worker that holds it: the same version, kept
        cad.model.dfm(plate, process="cnc", material="aluminum")
        self.assertEqual(_counts()["measured"], before["measured"] + 1)

        fixture.build(MODELS.replace("bd.Box(40, 30, 10)", "bd.Box(44, 30, 10)"))  # an edit: a new version
        edited = cad.model.dfm(plate, process="cnc", material="aluminum")
        self.assertEqual(_counts()["measured"], before["measured"] + 2)
        self.assertNotEqual(edited.measurements["bodies"][0]["bbox_mm"], first.measurements["bodies"][0]["bbox_mm"])

        # Two boxes' STEPs of one size (spaces after the end), the second written over the first at its time:
        # its digest, not its stat, says it changed.
        step, other = fixture.folder / "part.step", fixture.folder / "other.step"
        bd.export_step(bd.Box(30, 20, 6), str(step))
        bd.export_step(bd.Box(30, 20, 9), str(other))
        thin, thick = step.read_bytes(), other.read_bytes()
        width = max(len(thin), len(thick)) + 8
        step.write_bytes(thin + b" " * (width - len(thin)))
        cad.step.dfm(step, process="printing")
        cad.step.dfm(step, process="printing")
        self.assertEqual(_counts()["measured"], before["measured"] + 3, "an unchanged file is not read again")
        stat = step.stat()
        step.write_bytes(thick + b" " * (width - len(thick)))
        os.utime(step, ns=(stat.st_atime_ns, stat.st_mtime_ns))
        self.assertEqual((step.stat().st_size, step.stat().st_mtime_ns), (stat.st_size, stat.st_mtime_ns))
        changed = cad.step.dfm(step, process="printing")
        self.assertEqual(_counts()["measured"], before["measured"] + 4)
        self.assertAlmostEqual(changed.measurements["bodies"][0]["volume_mm3"], 5400.0, delta=1e-6)

    def test_a_file_is_read_once_across_checks_and_only_a_clean_result_is_kept(self) -> None:
        import build123d as bd

        import cad
        from cad_server.engine.daemon import _clean

        folder = Path(tempfile.mkdtemp(prefix="engine-dfm-read-"))
        self.addCleanup(shutil.rmtree, folder, True)
        step = folder / "part.step"
        bd.export_step(bd.Box(30, 20, 6), str(step))
        before = _counts()["read"]
        for technology in ("fdm", "sls", "sla"):
            cad.step.dfm(step, process="printing", technology=technology)
        self.assertEqual(_counts()["read"], before + 1, "other options measure again and read nothing")
        bd.export_step(bd.Box(30, 20, 9), str(step))
        cad.step.dfm(step, process="printing", technology="fdm")
        self.assertEqual(_counts()["read"], before + 2, "other bytes are read")
        self.assertTrue(_clean({"measured": {"report": {"partial": False}}}))
        for unkept in ({"unmeasured": {"code": "c", "message": "m"}}, {"refused": "no"},
                       {"measured": {"report": {"partial": True}}},
                       {"measured": {"report": {"partial_sections": ["holes"]}}}):
            self.assertFalse(_clean(unkept), unkept)

    def test_the_store_is_bounded_and_holds_one_version_of_a_document(self) -> None:
        from cad_server.engine.checks import Checks

        store = Checks(limit=2, budget=10_000)
        store.keep("model:a", "v1", "cnc", {"x": 1})
        store.keep("model:a", "v1", "sheet", {"x": 2})
        self.assertEqual(store.get("model:a", "v1", "cnc"), {"x": 1})
        self.assertIsNone(store.get("model:a", "v2", "sheet"), "another version is no result")
        self.assertIsNone(store.get("model:a", "v1", "cnc"), "the old version's results went with the ask")
        for name in ("one", "two", "three"):
            store.keep(f"file:{name}", "d", "cnc", {"x": name})
        self.assertEqual((store.status()["held"], store.get("file:one", "d", "cnc")), (2, None))


class ReleaseTest(unittest.TestCase):
    """A worker of an older release is never sent a check: its document is checked from the bytes its
    ``result`` gives. A library meeting an engine that measures no check, or another release's report,
    measures a file itself and a model as before (exported, read back)."""

    def test_only_a_worker_of_a_release_with_checks_is_sent_one(self) -> None:
        from cad.engine.contract import CHECKS_SINCE, answers_checks
        from cad.engine.previous import version
        from cad_server.engine import daemon

        self.assertTrue(answers_checks(CHECKS_SINCE) and answers_checks("9.0.0"))
        self.assertFalse(answers_checks("0.11.3") or answers_checks("0.10.0") or answers_checks("not a release"))
        self.assertTrue(daemon._answers_checks(None), "the server's own environment's worker")
        self.assertTrue(daemon._answers_checks(f"/env\0{version()}"), "a worker of the server's own release")
        self.assertFalse(daemon._answers_checks("/env\0" + "0.10.0"))

    def test_who_measures_is_decided_before_anything_is_measured(self) -> None:
        """The worker when its library is the caller's; the checks process, the server's library, when that is
        the caller's (a command at the server's release, of a project built at another); otherwise no one."""
        from cad_server.engine.daemon import CHECKS, _measurer

        new, newer, old = "0.12.0", "0.12.1", "0.11.2"
        for python_key, in_worker, caller, server, who in (
                (None, True, new, new, "worker"),  # the server's own environment
                (f"/env\0{new}", True, new, newer, "worker"),  # a project's script calling its own library
                (f"/env\0{new}", True, newer, newer, CHECKS),  # N1: the command, its model built at another release
                (f"/env\0{new}", True, old, newer, None),  # neither's library
                (f"/env\0{old}", True, newer, newer, CHECKS),  # an older worker, never sent one
                (None, False, newer, newer, CHECKS),  # a file: the server's library
                (None, False, new, newer, None)):  # a file, from another release's Python: measured there
            with self.subTest(python_key=python_key, caller=caller, server=server):
                self.assertEqual(_measurer(python_key, in_worker, caller, server), who)

    def test_another_releases_check_is_answered_at_once_and_measures_nothing(self) -> None:
        import build123d as bd

        import cad
        from cad.engine import api

        folder = Path(tempfile.mkdtemp(prefix="engine-dfm-other-"))
        self.addCleanup(shutil.rmtree, folder, True)
        step = folder / "box.step"
        bd.export_step(bd.Box(20, 20, 15), str(step))
        cad.step.dfm(step, process="cnc")
        before = _counts()
        check = {"type": "step", "process": "cnc", "candidates": False,
                 "resolved": cad._internal.manufacturing.options("step", "cnc", {}), "token": "t"}
        done = api._ask({"op": "export", "source": {"path": str(step)}, "destinations": [], "caller": "0.0.1",
                         "check": check})["done"]
        self.assertNotIn("checked", done)
        self.assertEqual(_counts()["measured"], before["measured"])

    def test_the_process_lost_says_what_it_held(self) -> None:
        from cad_server.engine.daemon import CHECKS, _check_lost

        lost = _check_lost("the checks process exited (-9) during a manufacturing check", CHECKS)
        self.assertIn("the checks process exited (-9)", lost)
        self.assertIn("held nothing but the files it had read for checks", lost)
        self.assertNotIn("warm memo", lost)
        worker = _check_lost("the worker for m.py exited (-9) during the build", "/m.py")
        self.assertIn("exited (-9) during a manufacturing check", worker)
        self.assertIn("warm memo is gone", worker)

    def test_an_older_workers_document_is_the_bytes_its_result_gives(self) -> None:
        from cad_server.engine.daemon import Daemon

        asked: list[dict[str, Any]] = []
        worker = SimpleNamespace(
            request=lambda order, _sink: (asked.append(order) or
                                          {"done": {"shapes": [["k1", 3], ["k2", 2]], "xbf": 4}, "payload": b"aaabbXBF!"}))
        models = SimpleNamespace(lock=threading.Lock(), records={"id": {"version": "v"}},
                                 held_bytes=lambda _ident, _version: None, not_held=lambda ident: ValueError(ident))
        released: list[Any] = []
        fake = SimpleNamespace(models=models, supervisor=SimpleNamespace(live=lambda *_args: SimpleNamespace(
            environment={}, python="/old/python")), lease=lambda *_args, **_kwargs: worker, release=released.append)
        source, data = Daemon._whole(fake, "id", {"script": "/m/parts.py", "function": "plate", "via": "/m/parts.py",
                                                  "python_key": "/old\0" + "0.10.0"})
        self.assertEqual((source, data, released), ({"document": "id", "name": "plate"}, b"XBF!", [worker]))
        self.assertEqual((asked[0]["op"], asked[0]["whole"]), ("result", True), "protocol 1's request, nothing new")

    def test_an_engine_without_checks_or_of_another_release_is_measured_here(self) -> None:
        import build123d as bd

        import cad
        from cad.engine import api

        folder = Path(tempfile.mkdtemp(prefix="engine-dfm-old-"))
        self.addCleanup(shutil.rmtree, folder, True)
        step = folder / "box.step"
        bd.export_step(bd.Box(20, 20, 15), str(step))
        expected = _plain(_today("step", step, step.resolve(), "printing"))
        for answer in (api.Unanswered("old"), {"measured": {}, "release": "0.10.0"},
                       api.Unreached("no engine here")):
            with self.subTest(answer=answer), mock.patch.object(
                    api, "check", side_effect=answer if isinstance(answer, Exception) else None,
                    return_value=None if isinstance(answer, Exception) else answer):
                self.assertEqual(_plain(cad.step.dfm(step, process="printing")), expected)
        fixture = Fixture(self, DECLARED)
        (block,) = fixture.ids
        with mock.patch.object(api, "check", side_effect=api.Unanswered("old")):
            exported = cad.model.dfm(block, process="cnc")
        held = cad.model.dfm(block, process="cnc")
        self.assertEqual(_plain(exported), _plain(held), "exported and read back, as before")


class WorkerTest(unittest.TestCase):
    """What a check's worker does beside it: a build of its script cancels a check running there or waiting
    for it, a cancel landing as a check ends hangs nothing, and a worker killed in one says so. A check waits
    at its seam (``CAD_ENGINE_CHECK_WAIT``, read as its worker starts: the build's environment) until the
    test lets it go."""

    def waiting(self) -> tuple[Fixture, Path]:
        hold = Path(tempfile.mkdtemp(prefix="engine-dfm-hold-")) / "go"
        self.addCleanup(shutil.rmtree, hold.parent, True)
        self.addCleanup(lambda: hold.write_text("", encoding="utf-8"))  # whatever happens, no check waits on
        return Fixture(self, MODELS, {"CAD_ENGINE_CHECK_WAIT": str(hold)}), hold

    def started(self, ident: str, hold: Path, tools: str = "3") -> tuple[Checking, int]:
        """A check of ``ident`` running in a thread, once its worker says it is measuring: the thread and the
        worker's pid. ``tools`` makes it a check the engine has kept no result of."""
        import cad

        reached = Path(f"{hold}.reached")
        reached.unlink(missing_ok=True)
        thread = Checking(lambda: cad.model.dfm(ident, process="cnc", tools=tools))
        thread.start()
        _until(self, lambda: (reached.exists() and reached.read_text(encoding="utf-8")) or not thread.is_alive(),
               "the check reached its seam")
        self.assertTrue(thread.is_alive(), thread.answered)
        return thread, int(reached.read_text(encoding="utf-8"))

    def test_a_build_cancels_its_scripts_checks_running_and_waiting(self) -> None:
        import cad
        from cad.engine.api import EngineError

        fixture, hold = self.waiting()
        running, _pid = self.started(fixture.ids[0], hold)
        waiting = Checking(lambda: cad.model.dfm(fixture.ids[1], process="printing"))
        waiting.start()
        _until(self, lambda: _counts()["asked"] >= 2, "the second check waits for the worker")
        fixture.build()  # waits for no measurement: both are cancelled, the seam never let go
        self.assertIn("cancelled the manufacturing check", fixture.said)
        for thread in (running, waiting):
            answered = thread.result(self)
            self.assertIsInstance(answered, EngineError)
            self.assertIn("the manufacturing check was cancelled", str(answered))
        self.assertFalse(hold.exists(), "the build did not wait for a check to be let go")
        self.assertIn("asking the manufacturing check", fixture.said, "said before the wait")

        # A cancel landing as a check ends: whichever wins, nothing hangs, and a build says it cancelled only
        # a check that was.
        for tools in ("4", "5", "6"):
            thread, _pid = self.started(fixture.ids[0], hold, tools)
            hold.write_text("", encoding="utf-8")
            fixture.build()
            answered = thread.result(self)
            if isinstance(answered, EngineError):
                self.assertIn("cancelled", str(answered))
            else:
                self.assertNotIn("cancelled the manufacturing check", fixture.said)
            hold.unlink()

    def test_a_checks_caller_going_cancels_it_and_costs_a_warm_worker_nothing(self) -> None:
        """Its caller killed: a model's check stops at a checkpoint in its warm worker, which lives on; a file's
        stops the checks process outright, and the next check starts a fresh one."""
        import build123d as bd

        import cad
        from cad.engine import api

        def caller(call: str, env: dict[str, str], reached: Path) -> tuple[subprocess.Popen, int]:
            reached.unlink(missing_ok=True)
            process = subprocess.Popen([sys.executable, "-c", f"import cad; {call}"], env=env,
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.addCleanup(process.wait)
            self.addCleanup(process.kill)
            _until(self, lambda: reached.exists() and reached.read_text(encoding="utf-8"), "the check reached its seam")
            return process, int(reached.read_text(encoding="utf-8"))

        api.stop()  # no checks process stands: the next starts with the seam of the caller that asks for it
        fixture, hold = self.waiting()
        reached = Path(f"{hold}.reached")
        process, worker = caller(f"cad.model.dfm({fixture.ids[0]!r}, process='cnc')", fixture.env, reached)
        process.kill()
        _until(self, lambda: _counts()["asked"] == 0, "the check of a caller gone stops")
        self.assertIn(worker, [row["pid"] for row in api.status()["workers"] if row["alive"]], "the warm worker lives on")

        step = fixture.folder / "part.step"
        bd.export_step(bd.Box(30, 20, 6), str(step))
        process, checks = caller(f"cad.step.dfm({str(step)!r}, process='printing')", fixture.env, reached)
        self.assertNotEqual(checks, worker)
        self.assertEqual(_counts()["process"]["pid"], checks)
        process.kill()
        _until(self, lambda: _counts()["asked"] == 0, "the check of a caller gone stops")
        _until(self, lambda: (_counts()["process"] or {}).get("pid") != checks, "the checks process is stopped")
        self.assertIn(worker, [row["pid"] for row in api.status()["workers"] if row["alive"]], "and no warm worker with it")
        hold.write_text("", encoding="utf-8")
        self.assertAlmostEqual(cad.step.dfm(step, process="printing").measurements["bodies"][0]["volume_mm3"], 3600.0,
                               delta=1e-6)
        api.stop()  # the seam goes with its engine's processes

    def test_a_build_behind_a_build_is_not_silent_and_a_check_queued_there_goes_at_once(self) -> None:
        """A check waiting for a worker a build holds: the next build of the script cancels it and it answers at
        once, with that build still running, and the next build says what it waits for."""
        import cad
        from cad.engine.api import EngineError

        folder = Path(tempfile.mkdtemp(prefix="engine-dfm-behind-"))
        self.addCleanup(shutil.rmtree, folder, True)
        marker, go = folder / "building", folder / "go"
        self.addCleanup(lambda: go.write_text("", encoding="utf-8"))
        slow = MODELS.replace("    part.label = \"plate\"\n", f"""    part.label = "plate"
    import pathlib, time
    pathlib.Path({str(marker)!r}).write_text("", encoding="utf-8")
    deadline = time.monotonic() + {JOIN_SECONDS}
    while not pathlib.Path({str(go)!r}).exists() and time.monotonic() < deadline:
        time.sleep(0.01)
""")
        fixture = Fixture(self, MODELS)
        fixture.script.write_text(textwrap.dedent(slow), encoding="utf-8")
        run = [sys.executable, str(fixture.script)]
        first = subprocess.Popen(run, cwd=fixture.folder, env=fixture.env, stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL)
        self.addCleanup(first.wait)
        _until(self, marker.exists, "the first build runs")
        queued = Checking(lambda: cad.model.dfm(fixture.ids[1], process="printing"))
        queued.start()
        _until(self, lambda: _counts()["asked"] >= 1, "the check waits for the worker")
        second = subprocess.Popen(run, cwd=fixture.folder, env=fixture.env, stdout=subprocess.DEVNULL,
                                  stderr=subprocess.PIPE, text=True)
        self.addCleanup(second.stderr.close)
        self.addCleanup(second.wait)
        answered = queued.result(self)
        self.assertIsNone(first.poll(), "the check answered with the first build still running")
        self.assertIsInstance(answered, EngineError)
        self.assertIn("the manufacturing check was cancelled", str(answered))
        go.write_text("", encoding="utf-8")
        said = second.communicate(timeout=JOIN_SECONDS)[1]
        self.assertIn("waiting for the build", said)
        self.assertNotIn("cancelled the manufacturing check", said, "only one that ran is said cancelled")

    def test_a_process_over_its_memory_cap_after_a_check_is_retired_and_says_so(self) -> None:
        """A real cap: the checks process goes over it, its caller told on stderr, and the next check starts
        another. The cap is the engine's, so an engine of this test's own."""
        from contextlib import redirect_stderr
        from io import StringIO

        import build123d as bd

        import cad
        from cad.engine import api

        folder = Path(tempfile.mkdtemp(prefix="engine-dfm-cap-"))
        self.addCleanup(shutil.rmtree, folder, True)
        step = folder / "box.step"
        bd.export_step(bd.Box(20, 20, 15), str(step))
        api.stop()
        self.addCleanup(api.stop)
        said = StringIO()
        with mock.patch.dict(os.environ, {"CAD_ENGINE_WORKER_RSS_MB": "1"}), redirect_stderr(said):
            first = cad.step.dfm(step, process="printing")
            second = cad.step.dfm(step, process="sheet")
        self.assertIn("the checks process held", said.getvalue())
        self.assertIn("it is retired, and the next check starts a fresh one", said.getvalue())
        self.assertEqual(first.measurements["process"], "printing")
        self.assertEqual(second.measurements["process"], "sheet")

    def test_a_worker_killed_in_a_check_says_so_and_the_next_build_starts_another(self) -> None:
        from cad.engine.api import EngineError

        fixture, hold = self.waiting()
        thread, pid = self.started(fixture.ids[0], hold)
        os.kill(pid, signal.SIGKILL if hasattr(signal, "SIGKILL") else signal.SIGTERM)
        answered = thread.result(self)
        self.assertIsInstance(answered, EngineError)
        self.assertIn("during a manufacturing check", str(answered))
        self.assertIn("the check is not run again", str(answered))
        hold.write_text("", encoding="utf-8")
        self.assertEqual(fixture.build(), fixture.ids, "a fresh worker builds the same models")


if __name__ == "__main__":
    unittest.main()
