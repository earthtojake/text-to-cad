"""A manufacturing check (``cad <type> dfm``, ``cad.<type>.dfm``) measured where the engine holds the
document: a model's in its warm worker, a STEP's and an xbf's in the documents worker, nothing exported or
read again (``worker._check``, ``Daemon.check``). Its result equals the one the same document gets read
from a file in a process of its own, for every process; the same check of an unchanged document is the
engine's kept result (``checks``), measuring nothing; an edit, other options or another file's bytes are
measured again; a build of the model's script cancels a check running in its worker; and a worker killed
in a check says so. On an engine, a state and a cache folder of this file's own."""

from __future__ import annotations

import dataclasses
import json
import os
import shutil
import signal
import sys
import tempfile
import textwrap
import threading
import time
import unittest
from pathlib import Path
from typing import Any

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

PROCESSES = ("cnc", "sheet", "molding", "printing")


def setUpModule() -> None:
    engine_daemon.isolate(unittest.addModuleCleanup)


def _plain(result: Any) -> Any:
    """A result as its ``--json`` says it: tuples and lists alike."""
    return json.loads(json.dumps(dataclasses.asdict(result), default=str))


def _counts() -> dict[str, int]:
    from cad.engine import api

    return api.status()["checks"]


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
        return [line for line in built.stdout.split() if len(line) == 36 and line.count("-") == 4]


def _today(document_type: str, source: Any, label: Path, process: str, **given: Any) -> Any:
    """The check as it was before the engine measured it: the document read from its file in this process
    (a model's exported to an xbf first), then measured and finished here."""
    from cad._internal import manufacturing
    from cad.build123d import _dfm_check

    resolved = manufacturing.options(document_type, process, given)
    report = _dfm_check.measure(document_type, source, process, resolved, False)
    return manufacturing.finish(label, {"process": process, **report}, process, resolved, False)


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


class KeptResultTest(unittest.TestCase):
    """The same check of the same document version is the engine's kept result: no worker measures it."""

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

        step = fixture.folder / "part.step"
        bd.export_step(bd.Box(30, 20, 6), str(step))
        cad.step.dfm(step, process="printing")
        cad.step.dfm(step, process="printing")
        self.assertEqual(_counts()["measured"], before["measured"] + 3, "an unchanged file is not read again")
        bd.export_step(bd.Box(30, 20, 9), str(step))
        changed = cad.step.dfm(step, process="printing")
        self.assertEqual(_counts()["measured"], before["measured"] + 4)
        self.assertAlmostEqual(changed.measurements["bodies"][0]["volume_mm3"], 5400.0, delta=1e-6)

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


class WorkerTest(unittest.TestCase):
    """What a check's worker does beside it: a build of its script cancels it, and a worker killed in one
    says so. A check waits at its seam (``CAD_ENGINE_CHECK_WAIT``, in the build's environment its worker
    adopts) until the test lets it go."""

    def waiting(self) -> tuple[Fixture, Path]:
        hold = Path(tempfile.mkdtemp(prefix="engine-dfm-hold-")) / "go"
        self.addCleanup(shutil.rmtree, hold.parent, True)
        self.addCleanup(lambda: hold.write_text("", encoding="utf-8"))  # whatever happens, no check waits on
        return Fixture(self, MODELS, {"CAD_ENGINE_CHECK_WAIT": str(hold)}), hold

    def started(self, ident: str, hold: Path) -> tuple[threading.Thread, list[Any], int]:
        """A check of ``ident`` running in a thread, once its worker says it is measuring: the thread,
        what it answered or raised, and the worker's pid."""
        import cad

        answered: list[Any] = []

        def check() -> None:
            try:
                answered.append(cad.model.dfm(ident, process="cnc"))
            except Exception as error:  # noqa: BLE001 - what the check raised is the test's to read
                answered.append(error)

        thread = threading.Thread(target=check, daemon=True)
        thread.start()
        reached = Path(f"{hold}.reached")
        deadline = time.monotonic() + engine_daemon.TIMEOUT_SECONDS
        while not reached.exists() or not reached.read_text(encoding="utf-8"):
            self.assertTrue(thread.is_alive(), answered)
            self.assertLess(time.monotonic(), deadline, "the check never reached its seam")
            time.sleep(0.02)
        return thread, answered, int(reached.read_text(encoding="utf-8"))

    def test_a_build_of_the_script_cancels_its_check(self) -> None:
        from cad.engine.api import EngineError

        fixture, hold = self.waiting()
        thread, answered, _pid = self.started(fixture.ids[0], hold)
        fixture.build()  # waits for no measurement: the check is cancelled, never released
        thread.join(engine_daemon.TIMEOUT_SECONDS)
        self.assertIn("cancelled the manufacturing check", fixture.said)
        self.assertIsInstance(answered[0], EngineError)
        self.assertIn("the manufacturing check was cancelled", str(answered[0]))
        self.assertFalse(hold.exists(), "the build did not wait for the check to be let go")

    def test_a_worker_killed_in_a_check_says_so_and_the_next_build_starts_another(self) -> None:
        from cad.engine.api import EngineError

        fixture, hold = self.waiting()
        thread, answered, pid = self.started(fixture.ids[0], hold)
        os.kill(pid, signal.SIGKILL if hasattr(signal, "SIGKILL") else signal.SIGTERM)
        thread.join(engine_daemon.TIMEOUT_SECONDS)
        self.assertIsInstance(answered[0], EngineError)
        said = str(answered[0])
        self.assertIn("during a manufacturing check", said)
        self.assertIn("the check is not run again", said)
        hold.write_text("", encoding="utf-8")
        self.assertEqual(fixture.build(), fixture.ids, "a fresh worker builds the same models")


if __name__ == "__main__":
    unittest.main()
