"""A manufacturing check on a running engine with what goes on beside it (``checks_runner.Runner``,
``worker._check``): a model's is measured from the bytes the engine holds of it, never in the model's
worker -- so a build or an inspection of the model waits for no check of it, and a build cancels none, but
one that changes the model supersedes the check of the version gone; a check outlives its caller, and the
same check asked while it runs waits for it; checks of other documents run at once in the pool, one past
it waiting and saying so; and a check whose callers are all gone gives its process to one someone waits
for. Through engines whose checks wait at the test's seam, and through the runner's own methods on an
engine of the test's. On an engine, a state and a cache folder of this file's own."""

from __future__ import annotations

import itertools
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest import mock

from tests.python.support import engine_daemon
from tests.python.support.manufacturing_fixtures import (JOIN_SECONDS, MEASURES, MODELS, Checking, Fixture, _counts,
                                                         _plain, _until, box, held_check, held_engine)


def setUpModule() -> None:
    engine_daemon.isolate(unittest.addModuleCleanup)


def _busy() -> list[int]:
    """The pids of the checks processes measuring now."""
    return [row["pid"] for row in _counts()["pool"]["processes"] if row["busy"]]


class EngineTest(unittest.TestCase):
    """A check on a running engine, with what goes on beside it: a build and an inspection of its model, its
    caller going, a second caller, other checks in the pool. A check waits at the test's seam
    (``held_engine``) until the test lets it go."""

    def caller(self, call: str, env: dict[str, str], hold: Path) -> tuple[subprocess.Popen, int]:
        """A process that calls a check, once its check says it is measuring: the process and the pid measuring."""
        reached = Path(f"{hold}.reached")
        reached.unlink(missing_ok=True)
        process = subprocess.Popen([sys.executable, "-c", f"import cad; {call}"], env=env,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(process.wait)
        self.addCleanup(process.kill)
        _until(self, lambda: reached.exists() and reached.read_text(encoding="utf-8"), "the check reached its seam")
        return process, int(reached.read_text(encoding="utf-8"))

    def behind(self, call: str, env: dict[str, str]) -> tuple[subprocess.Popen, list[str]]:
        """A process that calls a check, and its stderr as it comes."""
        process = subprocess.Popen([sys.executable, "-c", f"import cad; {call}"], env=env, stdout=subprocess.DEVNULL,
                                   stderr=subprocess.PIPE, text=True)
        said: list[str] = []
        reader = threading.Thread(target=lambda: said.extend(process.stderr), daemon=True)
        reader.start()
        self.addCleanup(process.stderr.close)  # last: once it is gone, its reader is done
        self.addCleanup(reader.join, JOIN_SECONDS)
        self.addCleanup(process.wait)
        self.addCleanup(process.kill)
        return process, said

    def test_a_models_build_and_inspection_wait_for_no_check_of_it_and_only_a_new_version_supersedes_one(self) -> None:
        """A model's check is measured in a checks process: while it measures, an inspection of the model answers
        and a run of its script that changes nothing leaves the check alone, its result kept; a build that
        changes the model lands at once too, and the check of the version gone is stopped as the build registers
        -- its process killed, nothing of it measured to the end -- and its caller answered with the check of
        the model as it is now, never a result of the version gone."""
        import cad

        _env, hold = held_engine(self)
        fixture = Fixture(self, MODELS)
        plate = fixture.ids[0]
        before = _counts()
        check, _pid = held_check(self, hold, lambda: cad.model.dfm(plate, process="cnc", tools="3"))
        inspected = Checking(lambda: cad.model.inspect(plate))
        inspected.start()
        self.assertNotIsInstance(inspected.result(self), Exception)
        fixture.build()  # the same code run again: the same version
        self.assertTrue(check.is_alive(), "neither waited for the check nor stopped it")
        hold.write_text("", encoding="utf-8")
        self.assertEqual(check.result(self).measurements["process"], "cnc")
        cad.model.dfm(plate, process="cnc", tools="3")
        self.assertEqual((_counts()["measured"], _counts()["reused"]), (before["measured"] + 1, before["reused"] + 1))

        hold.unlink()
        check, pid = held_check(self, hold, lambda: cad.model.dfm(plate, process="cnc", tools="4"))
        measured = _counts()["measured"]
        fixture.build(MODELS.replace("bd.Box(40, 30, 10)", "bd.Box(44, 30, 10)"))  # an edit, built under the check
        _until(self, lambda: pid not in _busy(), "the check of the version gone was stopped, still held at its seam")
        self.assertTrue(check.is_alive(), "its caller waits for the check of the model as it is now")
        hold.write_text("", encoding="utf-8")
        edited = check.result(self)
        self.assertAlmostEqual(edited.measurements["bodies"][0]["bbox_mm"][0], 44.0, delta=1e-6)
        self.assertEqual(_counts()["measured"], measured + 1, "the version gone was never measured to its end")
        again = cad.model.dfm(plate, process="cnc", tools="4")
        self.assertEqual((_plain(again), _counts()["measured"]), (_plain(edited), measured + 1), "and it is kept")

    def test_a_check_outlives_its_caller_and_the_next_call_reuses_its_result(self) -> None:
        """Its caller killed (a shell's time limit), a check runs to its end and keeps its result: the same call
        again measures nothing. A check waiting behind another says so (a pool of one checks process), and
        `cad status` lists the one running; once that one's caller is gone, its process is killed for the one
        waiting, which a fresh one measures, and it keeps nothing."""
        import cad
        from cad.engine import api

        env, hold = held_engine(self, {"CAD_ENGINE_CHECKS": "1"})
        fixture = Fixture(self, MODELS)
        process, _pid = self.caller(f"cad.model.dfm({fixture.ids[0]!r}, process='cnc')", env, hold)
        process.kill()
        process.wait()
        before = _counts()
        hold.write_text("", encoding="utf-8")
        _until(self, lambda: _counts()["asked"] == 0, "the check of a caller gone ends")
        self.assertEqual(_counts()["measured"], before["measured"] + 1, "it ran to its end")
        held = cad.model.dfm(fixture.ids[0], process="cnc")
        self.assertEqual(_counts()["measured"], before["measured"] + 1, "and the next call reuses its result")
        self.assertEqual(_counts()["reused"], before["reused"] + 1)
        self.assertEqual(held.measurements["process"], "cnc")

        hold.unlink()
        (step,) = box(self, 6)
        process, checks = self.caller(f"cad.step.dfm({str(step)!r}, process='printing')", env, hold)
        self.assertEqual(_busy(), [checks])
        (row,) = _counts()["running"]
        self.assertEqual((row["file"], row["process"], row["state"], row["where"], row["attached"]),
                         (str(step), "printing", "measuring", "checks", True))
        behind, said = self.behind(f"cad.step.dfm({str(step)!r}, process='sheet')", env)
        _until(self, lambda: any("waiting for another manufacturing check" in line for line in said),
               "the other check says it waits")
        self.assertEqual([row["process"] for row in _counts()["running"] if not row["waiting"]], ["printing"],
                         "a check whose caller is there keeps its process")
        before = _counts()
        process.kill()
        process.wait()
        _until(self, lambda: [(row["process"], row["waiting"]) for row in _counts()["running"]] == [("sheet", False)],
               "the abandoned check gives its process up to the one waiting")
        from cad_server.engine.cli import status_text

        self.assertIn("check    sheet of part0.step in checks", status_text(api.status()))
        hold.write_text("", encoding="utf-8")
        self.assertEqual(behind.wait(JOIN_SECONDS), 0, said)
        _until(self, lambda: _counts()["asked"] == 0, "both checks end")
        self.assertEqual(_counts()["measured"], before["measured"] + 1, "the abandoned one measured nothing")
        self.assertNotIn(checks, [row["pid"] for row in _counts()["pool"]["processes"]],
                         "its process killed at once, and a fresh one measured the one waiting")
        cad.step.dfm(step, process="printing")
        self.assertEqual(_counts()["measured"], before["measured"] + 2, "nothing of it was kept")

    def test_a_killed_command_s_check_is_seen_gone_and_gives_its_process_to_a_caller_memory_has_no_room_for(
            self) -> None:
        """`cad step dfm` killed (SIGKILL, as a shell's or `subprocess.run`'s time limit kills it): `cad status`
        says at once that no caller of its check is there. A check whose caller is there, waiting with a slot of
        the pool free but no room in the engine's memory for another checks process (a cap of 1 MB), takes the
        abandoned check's place: its process killed, a fresh one measures the one waited for."""
        env, hold = held_engine(self, {"CAD_ENGINE_CHECKS": "2", "CAD_ENGINE_WORKER_RSS_MB": "1",
                                       "CAD_ENGINE_CHECK_RSS_MB": "0"})  # no limit of a check's own: the cap's alone
        reached = Path(f"{hold}.reached")
        steps = box(self, 6, 7)
        command = subprocess.Popen([sys.executable, "-m", "cad_server.cli", "step", "dfm", str(steps[0]),
                                    "--process", "printing", "--json"], env=env, stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL)
        self.addCleanup(command.wait)
        self.addCleanup(command.kill)
        _until(self, lambda: reached.exists() and reached.read_text(encoding="utf-8"), "the check reached its seam")
        abandoned = int(reached.read_text(encoding="utf-8"))
        (row,) = _counts()["running"]
        self.assertEqual((row["attached"], row["callers"], row["waiting"], row["where"]), (True, 1, False, "checks"))
        command.kill()
        command.wait()
        _until(self, lambda: [(row["attached"], row["callers"]) for row in _counts()["running"]] == [(False, 0)],
               "its caller is seen gone")
        reached.unlink()
        behind, said = self.behind(f"cad.step.dfm({str(steps[1])!r}, process='printing')", env)
        _until(self, lambda: reached.exists() and reached.read_text(encoding="utf-8"),
               "the check someone waits for measures")
        _until(self, lambda: any("no room for another checks process" in line for line in said), "it said why it waited")
        (row,) = _counts()["running"]
        self.assertEqual((row["file"], row["attached"], row["callers"], row["waiting"]), (str(steps[1]), True, 1, False))
        self.assertNotEqual(int(reached.read_text(encoding="utf-8")), abandoned, "in a fresh checks process")
        self.assertNotIn(abandoned, [row["pid"] for row in _counts()["pool"]["processes"]], "the abandoned one's killed")
        hold.write_text("", encoding="utf-8")
        self.assertEqual(behind.wait(JOIN_SECONDS), 0, said)

    def test_different_checks_run_at_once_in_the_pool_and_one_past_it_waits_saying_so(self) -> None:
        """Two files' checks measured at once, in two checks processes; a third, the pool full, says it waits
        and runs once one is done."""
        env, hold = held_engine(self, {"CAD_ENGINE_CHECKS": "2"})
        before = _counts()["measured"]
        callers = []
        for step in box(self, 6, 7, 8):
            callers.append(self.behind(f"cad.step.dfm({str(step)!r}, process='printing')", env))
            if len(callers) == 2:
                _until(self, lambda: len(_busy()) == 2, "two checks measure at once")
        self.assertEqual(len(set(_busy())), 2, "in two processes")
        _until(self, lambda: any("the 2 checks processes are all busy" in line for line in callers[2][1]),
               "the third waits")
        self.assertIn("waiting for another manufacturing check", "".join(callers[2][1]))
        hold.write_text("", encoding="utf-8")
        for process, said in callers:
            self.assertEqual(process.wait(JOIN_SECONDS), 0, said)
        self.assertEqual(_counts()["measured"], before + 3)

    def test_the_same_check_asked_while_it_runs_waits_for_it_and_measures_once(self) -> None:
        import cad

        env, hold = held_engine(self)
        fixture = Fixture(self, MODELS)
        before = _counts()
        first, _pid = held_check(self, hold, lambda: cad.model.dfm(fixture.ids[0], process="cnc", tools="7"))
        code = (f"import cad, dataclasses, json; found = cad.model.dfm({fixture.ids[0]!r}, process='cnc', tools='7'); "
                "print(json.dumps(dataclasses.asdict(found), default=str))")
        second = subprocess.Popen([sys.executable, "-c", code], env=env, stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE, text=True)
        self.addCleanup(second.stdout.close)
        self.addCleanup(second.stderr.close)
        self.addCleanup(second.wait)
        _until(self, lambda: _counts()["waited"] == before["waited"] + 1, "the second waits for the first")
        hold.write_text("", encoding="utf-8")
        out, said = second.communicate(timeout=JOIN_SECONDS)
        self.assertIn("waiting for the same manufacturing check", said)
        self.assertEqual(json.loads(out), _plain(first.result(self)))
        self.assertEqual(_counts()["measured"], before["measured"] + 1, "measured once")


class Process:
    """A checks process as a ``Runner`` has one: its requests answered by its engine's ``answer``, each held
    while the engine holds; killed, its request raises as one whose process exited under it."""

    pids = itertools.count(100)

    def __init__(self, key: str, engine: "Engine") -> None:
        self.key, self.pid, self.started, self.engine = key, next(Process.pids), time.time(), engine
        self.killed = self.retired = False
        self.rss = None
        self.popen = SimpleNamespace(kill=self.kill)

    def kill(self) -> None:
        with self.engine.changed:
            self.killed = True
            self.engine.killed.append(self.pid)
            self.engine.changed.notify_all()

    def alive(self) -> bool:
        return not self.killed

    def request(self, order: dict[str, Any], _sink: Any, payload: bytes = b"") -> dict[str, Any]:
        from cad_server.engine.supervisor import Gone

        engine = self.engine
        with engine.changed:
            engine.requests.append((self.key, order, payload))
            engine.changed.notify_all()
            engine.changed.wait_for(lambda: not engine.holding or self.killed)
            if self.killed:
                raise Gone("the checks process exited (-9) during a manufacturing check", during=True, code=-9)
        return engine.answer(order)


class Supervised:
    """What the pool asks of its supervisor (``Supervisor``'s own methods), of an ``Engine``'s processes."""

    def __init__(self, engine: "Engine") -> None:
        self.engine = engine

    def processes(self, _service: str) -> list[Process]:
        return [process for process in self.engine.processes.values() if process.alive()]

    def pressed(self) -> bool:
        return False

    def memory(self) -> float | None:
        return None

    def resident(self) -> float:
        return 0.0

    def retire(self, process: Process, why: str) -> None:
        self.engine.retired.append((process.key, why))


class Engine:
    """What a ``Runner`` takes of its daemon, in a test's hands: a model document (``DOC``, at ``versions``),
    files, the checks processes its pool's slots lease (a killed one's place taken by a fresh one) and what each
    answers (``answer``: by default the check measured by what its caller says measures); ``holding``: every
    request waits until ``let_go``."""

    def __init__(self, size: int = 1, limits: Any = None, resident: Any = lambda _pid: None,
                 store: Any = None) -> None:
        from cad_server.engine.checks import Checks, Pool
        from cad_server.engine.checks_runner import Limits, Runner

        self.versions = {DOC: "v1"}
        self.read: list[str] = []
        self.requests: list[tuple[str, dict[str, Any], bytes]] = []
        self.released: list[Process] = []
        self.killed: list[int] = []
        self.retired: list[tuple[str, str]] = []
        self.processes: dict[str, Process] = {}
        self.changed = threading.Condition()
        self.holding = self.stopping = False
        self.answer = self.measured
        self.pool = Pool(Supervised(self), size)
        # Each asked of the engine as it is then: a test puts its own ``lease``, ``release`` or ``document``.
        self.runner = Runner(Checks() if store is None else store, self.pool, lease=lambda slot: self.lease(slot),
                             release=lambda process: self.release(process),
                             version=lambda ident: self.versions.get(ident), read=lambda ident: self.document(ident),
                             durable=lambda ident, version: (ident, f"r-{version}") if version else None,
                             stopping=lambda: self.stopping, limits=limits or Limits(None), resident=resident)

    def release(self, process: Process) -> None:
        self.released.append(process)

    def lease(self, slot: str) -> Process:
        held = self.processes.get(slot)
        if held is None or held.killed:
            held = self.processes[slot] = Process(slot, self)
        return held

    def document(self, ident: str) -> tuple[dict[str, Any], bytes]:
        self.read.append(ident)
        return {"document": ident, "name": "plate"}, b"bytes"

    def measured(self, order: dict[str, Any], **more: Any) -> dict[str, Any]:
        from cad.engine.previous import version
        from cad_server.engine.checks import digest

        source, check = order["source"], order["check"]
        file = {"digest": digest(Path(source["path"]))} if "path" in source else {}
        return {"id": 1, "done": {"reports": [], "files": [], "checked": {
            "measured": {"process": check.get("process"), "resolved": {}, "report": {"of": source.get("version")}},
            "release": version(), "read": True, "measures": check["measures"], **file, **more}}}

    def request(self, source: dict[str, Any], measures: Any = MEASURES, caller: str | None = None,
                **check: Any) -> dict[str, Any]:
        from cad.engine.previous import version

        return {"op": "export", "source": source, "destinations": [], "caller": caller or version(),
                "measures": measures, "check": {"type": "model" if "id" in source else "step", "process": "cnc",
                                                "resolved": {}, **check}}

    def check(self, source: dict[str, Any], **request: Any) -> dict[str, Any]:
        """A check asked and answered: its answer."""
        said: list[dict[str, Any]] = []
        self.runner.check(self.request(source, **request), said.append)
        return said[-1]

    def ask(self, source: dict[str, Any], gone: threading.Event | None = None, **request: Any) -> Checking:
        """A check asked in a thread of its own: its answer once it has one (``Checking.result``)."""
        said: list[dict[str, Any]] = []

        def run() -> dict[str, Any]:
            self.runner.check(self.request(source, **request), said.append, gone)
            return said[-1]

        thread = Checking(run)
        thread.start()
        return thread

    def states(self) -> list[str]:
        return [row["state"] for row in self.runner.status()["running"]]

    def let_go(self) -> None:
        with self.changed:
            self.holding = False
            self.changed.notify_all()


# A model document's id, as the kept results' folders are named.
DOC = str(uuid.UUID(int=7))


class RunnerTest(unittest.TestCase):
    """A check's life in the engine (``checks_runner.Runner``), through its own methods, on an engine of the
    test's (``Engine``): what the daemon gives it and the checks processes it leases are the test's, nothing
    started. As an installed engine is: what measures in the checks processes is known once one has said it."""

    def setUp(self) -> None:
        from cad.engine import places

        patch = mock.patch.object(places, "kernel", return_value={"own": False})
        patch.start()
        self.addCleanup(patch.stop)

    def file(self, name: str = "part.step") -> dict[str, str]:
        folder = Path(os.path.realpath(tempfile.mkdtemp(prefix="engine-dfm-runner-")))
        self.addCleanup(shutil.rmtree, folder, True)
        (folder / name).write_bytes(name.encode())
        return {"path": str(folder / name)}

    def test_the_same_check_is_measured_once_and_a_kept_result_reads_none_of_its_document(self) -> None:
        engine = Engine()
        answers = [engine.check({"id": DOC}) for _ in range(3)]
        self.assertEqual([answer["done"].get("reused", False) for answer in answers], [False, True, True])
        self.assertEqual((len(engine.requests), engine.read), (1, [DOC]), "measured, and its bytes read, once")
        _slot, order, payload = engine.requests[0]
        self.assertEqual((order["source"], payload), ({"document": DOC, "name": "plate", "version": "v1"}, b"bytes"),
                         "from the bytes the engine holds, at their version")
        self.assertNotIn("measures", answers[1]["done"]["checked"], "kept without what only its first caller is told")
        engine.check({"id": DOC}, process="sheet")
        self.assertEqual(len(engine.requests), 2, "another check of it is measured")
        counts = engine.runner.status()
        self.assertEqual((counts["measured"], counts["reused"], counts["asked"]), (2, 2, 0))

    def test_another_release_other_code_or_no_word_of_what_measures_is_answered_at_once_unmeasured(self) -> None:
        engine = Engine()
        self.assertIn("checked", engine.check({"id": DOC})["done"])  # the checks processes say what measures there
        for unlike in ({"caller": "0.0.1"}, {"measures": None}, {"measures": {**MEASURES, "code": "edited"}},
                       {"measures": {**MEASURES, "libraries": {**MEASURES["libraries"], "numpy": "2.1.0"}}}):
            with self.subTest(unlike=unlike):
                self.assertNotIn("checked", engine.check({"id": DOC}, **unlike)["done"])
        self.assertEqual((len(engine.requests), engine.runner.status()["reused"]), (1, 0), "nothing measured or served")
        bare = {"code": MEASURES["code"], "libraries": {}}
        self.assertTrue(engine.check({"id": DOC}, measures=bare)["done"]["reused"], "no kernel: served its code's")

    def test_a_kept_result_serves_every_caller_its_measurer_measures_for_across_a_restart(self) -> None:
        """A result a script's check kept is served, after a restart (nothing known yet of what measures), to the
        ``cad`` command, which names no library, and to the script again; a caller of another library's version
        is measured again, and its result serves the command from then on."""
        from cad_server.engine.checks import Checks
        from cad_server.engine.registry import Folder

        folder = Folder(tempfile.mkdtemp(prefix="engine-dfm-restart-"))
        self.addCleanup(shutil.rmtree, folder.root, True)
        measured: list[Any] = []

        def ask(measures: dict[str, Any]) -> dict[str, Any]:
            engine = Engine(store=Checks(folder=lambda: folder))  # a fresh engine on the same cache folder
            engine.answer = lambda order: (measured.append(order["check"]["measures"]), engine.measured(order))[1]
            return engine.check({"id": DOC}, measures=measures)["done"]

        bare = {"code": MEASURES["code"], "libraries": {}}
        newer = {**MEASURES, "libraries": {**MEASURES["libraries"], "numpy": "2.1.0"}}
        self.assertNotIn("reused", ask(MEASURES))
        for measures in (bare, MEASURES):
            with self.subTest(measures=measures):
                self.assertTrue(ask(measures).get("reused"), "measured once, served after a restart")
        self.assertNotIn("reused", ask(newer), "another numpy: measured again")
        self.assertTrue(ask(bare).get("reused"))
        self.assertEqual(measured, [MEASURES, newer])

    def test_a_document_built_again_is_read_again_before_it_is_measured_and_superseded_after(self) -> None:
        from cad_server.engine.checks_runner import READS, SUPERSEDED

        engine = Engine()
        read = engine.document

        def built_as_it_is_read(ident: str) -> tuple[dict[str, Any], bytes]:
            engine.versions[DOC] = f"v{len(engine.read) + 2}"
            return read(ident)

        engine.document = built_as_it_is_read
        self.assertEqual(engine.check({"id": DOC}), {"failed": SUPERSEDED, "reason": "superseded"})
        self.assertEqual((len(engine.read), engine.requests), (READS, []), "built again each time: nothing measured")

        engine.document = read
        engine.read.clear()
        answer = engine.check({"id": DOC})
        self.assertEqual(answer["done"]["checked"]["measured"]["report"], {"of": engine.versions[DOC]})
        self.assertTrue(engine.check({"id": DOC})["done"]["reused"], "kept under the version it was measured at")

        def built_under_it(order: dict[str, Any]) -> dict[str, Any]:
            engine.versions[DOC] = f"later-{len(engine.requests)}"  # a build the runner was not told of
            return engine.measured(order)

        engine.answer = built_under_it
        engine.requests.clear()
        self.assertEqual(engine.check({"id": DOC}, process="sheet"), {"failed": SUPERSEDED, "reason": "superseded"})
        self.assertEqual(len(engine.requests), READS, "asked again of each version, each one gone as it answered")
        engine.answer = engine.measured
        self.assertNotIn("reused", engine.check({"id": DOC}, process="sheet")["done"], "nothing of it was kept")

        file = self.file()
        engine.answer = lambda order: engine.measured(order, digest=None, changed=True)
        self.assertEqual(engine.check(file)["reason"], "superseded", "a file rewritten each time it was read")
        engine.answer = lambda order: engine.measured(order, digest="another")
        self.assertIn("checked", engine.check(file)["done"], "rewritten before it was read: measured as it is now")
        engine.answer = engine.measured
        self.assertNotIn("reused", engine.check(file)["done"], "and kept under no digest but the one measured")
        self.assertTrue(engine.check(file)["done"]["reused"])

    def test_a_build_of_its_model_stops_a_check_at_once_and_its_callers_get_the_new_version_s(self) -> None:
        """The daemon says a document was built (``Runner.built``): a check measuring a generation now gone is
        stopped there -- its process killed, its slot free -- and asked again of the document as it is now for
        the callers still there, the one attached to it too, measured once; a build that kept the generation,
        or of another document, stops nothing; and a check no one waits for ends ``superseded``, not run again."""
        from cad_server.engine.checks_runner import SUPERSEDED

        other = str(uuid.UUID(int=8))
        engine = Engine()
        engine.versions[other] = "o1"
        engine.holding = True
        first = engine.ask({"id": DOC})
        _until(self, lambda: len(engine.requests) == 1, "the check measures")
        second = engine.ask({"id": DOC})
        _until(self, lambda: engine.runner.store.status()["waited"] == 1, "the same check attached to it")
        engine.runner.built(DOC)  # the same code run again: the same generation
        engine.versions[other] = "o2"
        engine.runner.built(other)  # another model of the script
        self.assertEqual((engine.killed, engine.states()), ([], ["measuring"]), "neither is this check's document")

        engine.versions[DOC] = "v2"
        engine.runner.built(DOC)
        _until(self, lambda: len(engine.requests) == 2, "the check asked again, of the document as it is now")
        self.assertEqual(len(engine.killed), 1, "the process measuring the version gone was killed")
        self.assertEqual(engine.requests[1][1]["source"]["version"], "v2")
        engine.let_go()
        answers = [first.result(self), second.result(self)]
        self.assertEqual([answer["done"]["checked"]["measured"]["report"] for answer in answers], [{"of": "v2"}] * 2)
        self.assertEqual((len(engine.requests), engine.runner.store.status()["measured"]), (2, 1),
                         "measured once for both, and the version gone counted as no measurement")
        self.assertTrue(engine.check({"id": DOC})["done"]["reused"], "kept under the generation it was measured at")

        engine.holding = True
        gone = threading.Event()
        abandoned = engine.ask({"id": DOC}, gone, process="sheet")
        _until(self, lambda: len(engine.requests) == 3, "a check measures")
        gone.set()
        engine.versions[DOC] = "v3"
        engine.runner.built(DOC)
        self.assertEqual(abandoned.result(self), {"failed": SUPERSEDED, "reason": "superseded"})
        self.assertEqual((len(engine.requests), len(engine.killed), engine.runner.status()["asked"]), (3, 2, 0),
                         "stopped, and asked again for no one")

    def test_an_abandoned_check_gives_its_process_to_one_someone_waits_for_and_no_other_does(self) -> None:
        """A check whose callers have all gone is stopped only when a check whose caller is there can take no slot:
        its process killed, nothing of it kept, a fresh one measuring the waiter. A check a caller waits for --
        its own, or one attached since -- is never cut short; and a waiter whose own caller has gone leaves a free
        slot to one someone waits for."""
        engine = Engine()
        engine.holding = True
        files = [self.file(f"part{index}.step") for index in range(4)]
        gone = [threading.Event() for _ in range(4)]
        first = engine.ask(files[0], gone[0])
        _until(self, lambda: engine.states() == ["measuring"], "the first measures")
        attached = engine.ask(files[0], gone[1])  # the same check: a caller of the first too
        _until(self, lambda: engine.runner.status()["waited"] == 1, "a second caller waits for the first")
        second = engine.ask(files[1], gone[2])
        _until(self, lambda: engine.states() == ["measuring", "waiting"], "the second waits for the slot")
        gone[0].set()
        self.assertEqual(engine.runner.status()["running"][0]["callers"], 1)
        (waiter,) = [asked for asked in engine.runner.asked.values() if asked.state.value == "waiting"]
        engine.runner.reap(waiter)
        self.assertEqual(engine.killed, [], "a caller attached to it is still there")
        gone[1].set()
        self.assertEqual(first.result(self)["reason"], "cancelled")
        self.assertEqual(attached.result(self)["reason"], "cancelled")
        _until(self, lambda: engine.states() == ["measuring"], "the second measures, in a fresh process")
        self.assertEqual(len(engine.killed), 1)

        third = engine.ask(files[2], gone[3])
        gone[3].set()  # waiting, its caller gone
        _until(self, lambda: engine.states() == ["measuring", "waiting"], "the third waits")
        fourth = engine.ask(files[3], threading.Event())
        _until(self, lambda: engine.states() == ["measuring", "waiting", "waiting"], "and the fourth, its caller there")
        self.assertEqual(len(engine.killed), 1, "the one measuring has its caller: never cut short")
        engine.let_go()
        for thread in (second, third, fourth):
            self.assertIn("checked", thread.result(self)["done"])
        self.assertEqual([order["source"]["path"] for _key, order, _payload in engine.requests],
                         [files[index]["path"] for index in (0, 1, 3, 2)], "the one someone waits for first")
        self.assertEqual(engine.runner.store.status()["held"], 3, "nothing kept of the one stopped")

    def test_a_stop_never_reaches_a_process_its_check_no_longer_has(self) -> None:
        """The engine stopping at the moment a check lets its process go, the next check's from then on: nothing is
        killed, and the check's answer stands. One stopped as its process started sends it no request."""
        from cad_server.engine.checks_runner import STOPPED

        engine = Engine()

        def released(process: Process) -> None:
            engine.runner.halt()  # as the next check would lease it
            engine.released.append(process)

        engine.release = released
        self.assertIn("checked", engine.check(self.file())["done"])
        self.assertEqual((engine.killed, len(engine.released)), ([], 1))

        lease = engine.lease

        def stopped_as_it_started(slot: str) -> Process:
            engine.runner.halt()
            return lease(slot)

        engine.lease = stopped_as_it_started
        self.assertEqual(engine.check(self.file("other.step")), {"failed": STOPPED, "reason": "stopped", "stopped": True})
        self.assertEqual((engine.killed, len(engine.requests), len(engine.released)), ([], 1, 2))

    def test_the_engine_stopping_answers_every_check_stopped(self) -> None:
        from cad_server.engine.checks_runner import STOPPED

        engine = Engine()
        engine.holding = True
        measuring = engine.ask(self.file("a.step"))
        _until(self, lambda: engine.states() == ["measuring"], "one measures")
        waiting = engine.ask(self.file("b.step"))
        _until(self, lambda: engine.states() == ["measuring", "waiting"], "one waits")
        engine.runner.halt()
        stopped = {"failed": STOPPED, "reason": "stopped", "stopped": True}
        self.assertEqual((measuring.result(self), waiting.result(self)), (stopped, stopped))
        self.assertEqual((len(engine.killed), len(engine.requests)), (1, 1), "the one measuring killed, the other never asked")
        engine.stopping = True
        self.assertEqual(engine.check(self.file("c.step")), stopped, "asked of an engine that stops: at once")
        self.assertEqual(engine.runner.status()["asked"], 0)

    def test_a_check_past_its_time_or_its_memory_is_stopped_and_says_which(self) -> None:
        """The watchdog reads the time a check has measured and its process's memory from outside it: one over
        either is stopped -- its process killed, whatever call it is in -- with the limit and what to do in its
        words; one under both runs to its end."""
        from cad_server.engine import checks_runner
        from cad_server.engine.checks_runner import Limits

        patch = mock.patch.object(checks_runner, "WATCH_SECONDS", 0.01)  # how often it looks: the test waits on it
        patch.start()
        self.addCleanup(patch.stop)
        engine = Engine(limits=Limits(3600.0, lambda: 100.0), resident=lambda _pid: 99.0)
        engine.holding = True
        under = engine.ask(self.file())
        _until(self, lambda: [process.rss for process in engine.processes.values()] == [99.0],
               "its memory, read from outside, is what the supervisor counts for it")
        engine.let_go()
        self.assertIn("checked", under.result(self)["done"])
        self.assertEqual(engine.killed, [])

        engine = Engine(limits=Limits(None, lambda: 100.0), resident=lambda _pid: 512.0)
        engine.holding = True
        answer = engine.check(self.file())
        self.assertEqual((answer["reason"], len(engine.killed)), ("over_memory", 1))
        self.assertIn("at 512 MB, over a check's memory limit of 100 MB", answer["failed"])
        self.assertIn("CAD_ENGINE_CHECK_RSS_MB", answer["failed"])

        engine = Engine(limits=Limits(1e-9))
        engine.holding = True
        first = engine.ask(self.file())
        second = engine.ask(self.file())  # another file: a check of its own, waiting for the slot
        answer = first.result(self)
        self.assertEqual(answer["reason"], "over_time")
        self.assertIn("over a check's time limit of 1e-09 s", answer["failed"])
        self.assertIn("CAD_ENGINE_CHECK_SECONDS", answer["failed"])
        self.assertEqual(second.result(self)["reason"], "over_time", "and its slot is the next check's")
        self.assertEqual((engine.runner.status()["asked"], engine.runner.store.status()["held"]), (0, 0))

    def test_a_setting_that_is_no_number_keeps_the_default_and_zero_is_no_limit(self) -> None:
        from cad_server.engine.checks_runner import SECONDS, Limits

        for given, seconds, memory, noted in (({}, SECONDS, 4096.0, 0),
                                              ({"CAD_ENGINE_CHECK_SECONDS": "90", "CAD_ENGINE_CHECK_RSS_MB": "512"}, 90.0, 512.0, 0),
                                              ({"CAD_ENGINE_CHECK_SECONDS": "0", "CAD_ENGINE_CHECK_RSS_MB": "0"}, None, None, 0),
                                              ({"CAD_ENGINE_CHECK_SECONDS": "soon", "CAD_ENGINE_CHECK_RSS_MB": "-1"}, SECONDS, 4096.0, 2)):
            with self.subTest(given=given), mock.patch.dict(os.environ, given):
                for name in ("CAD_ENGINE_CHECK_SECONDS", "CAD_ENGINE_CHECK_RSS_MB"):
                    if name not in given:
                        os.environ.pop(name, None)
                limits = Limits.of_environment(lambda: 4096.0)
                self.assertEqual((limits.seconds, limits.memory(), len(limits.notes)), (seconds, memory, noted))

    def test_a_checks_process_lost_says_so_and_one_the_system_killed_says_what_that_usually_means(self) -> None:
        from cad.engine.serve import KernelProcessesUnavailable
        from cad_server.engine.supervisor import Gone

        engine = Engine()

        def lost(error: BaseException) -> dict[str, Any]:
            def raises(_order: dict[str, Any]) -> dict[str, Any]:
                raise error

            engine.answer = raises
            return engine.check(self.file())

        exited = "the checks process exited ({}) during a manufacturing check"
        answer = lost(Gone(exited.format(1), during=True, code=1))
        self.assertEqual(answer["reason"], "process_lost")
        self.assertIn("The check is not run again", answer["failed"])
        self.assertNotIn("usually for memory", answer["failed"])
        if hasattr(signal, "SIGKILL"):
            answer = lost(Gone(exited.format(-9), during=True, code=-9))
            self.assertIn("exited (-9) during a manufacturing check: killed by the system, usually for memory -- "
                          "the part may be too large to check on this machine. The check is not run again", answer["failed"])
        for error in (Gone("the checks process did not start", unready=True),
                      KernelProcessesUnavailable("the CAD kernel's environment could not be made")):
            with self.subTest(error=error):
                answer = lost(error)
                self.assertEqual((answer["reason"], answer["failed"]), ("no_kernel", str(error)))
        self.assertEqual((engine.runner.status()["asked"], engine.pool.busy), (0, {}), "each slot given back")

    def test_a_request_that_is_no_check_is_refused_in_one_line_and_nothing_is_read(self) -> None:
        engine = Engine()
        for request, said in (
                (engine.request({"id": DOC}, process="nope"), "a check's process is cnc, sheet, molding or printing"),
                (engine.request({"id": DOC}, resolved=None), "a check's resolved options are a table"),
                (engine.request({"id": DOC}, type="stl"), "the engine measures a manufacturing check of a model"),
                (engine.request({"script": "/m/parts.py"}), "a check reads a document the engine holds")):
            with self.subTest(said=said):
                answers: list[dict[str, Any]] = []
                engine.runner.check(request, answers.append)
                self.assertIn(said, answers[-1]["failed"])
                self.assertEqual(answers[-1]["kind"], "builtins:ValueError")
        self.assertEqual((engine.read, engine.requests), ([], []))

    def test_a_check_s_record_is_cleared_whatever_its_store_raises(self) -> None:
        from cad_server.engine.checks import Checks

        class Broken(Checks):
            def get(self, *_args: Any, **_kwargs: Any) -> Any:
                raise OSError("disk gone")

        engine = Engine(store=Broken())
        with self.assertRaises(OSError):
            engine.check({"id": DOC})
        self.assertEqual((engine.runner.asked, engine.runner.running), ({}, {}))

    def test_what_measures_in_the_checks_processes_is_the_base_s_and_one_of_a_base_gone_is_retired(self) -> None:
        """Said by the checks processes started since the base was made; one unlike it (of a base made before)
        is retired; and a base made again retires them all and is unknown until a fresh one says. Where the
        kernel environment is the server's own, the server's, read now."""
        from cad.engine import places
        from cad.engine.contract import measure

        engine = Engine(size=2)
        pool = engine.pool
        newer = {**MEASURES, "libraries": {**MEASURES["libraries"], "numpy": "2.1.0"}}
        self.assertIsNone(pool.known(), "nothing said yet: a fresh process decides")
        fresh, old = engine.lease("checks"), engine.lease("checks-2")
        old.started = pool.since - 1
        pool.learn(fresh, {"done": {"checked": {"measures": MEASURES}}})
        self.assertEqual((pool.known(), engine.retired), (MEASURES, []))
        pool.learn(old, {"done": {"measures": newer}})
        self.assertEqual((pool.known(), engine.retired), (MEASURES, [("checks-2", "base")]), "started before the base")
        pool.rebased()
        self.assertEqual((pool.known(), engine.retired[1:]), (None, [("checks", "base"), ("checks-2", "base")]))
        with mock.patch.object(places, "kernel", return_value={"own": True}):
            self.assertEqual(pool.known(), measure(), "the server's own, read now")


if __name__ == "__main__":
    unittest.main()
