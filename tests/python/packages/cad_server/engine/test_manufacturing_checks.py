"""A manufacturing check (``cad <type> dfm``, ``cad.<type>.dfm``) measured in the engine's checks processes
(``checks_runner.Runner``, ``worker._check``): a STEP's and an xbf's from its file, a model's from the bytes the
engine holds of it, never in the model's worker -- so a build or an inspection of the model waits for no check
of it, and a build cancels none. Its result equals the one the same document gets read from a file in a
process of its own, for every process, with no process given and ranking candidates; the same check of an
unchanged document is the engine's kept result (``checks``), measuring nothing; an edit, other options or
another file's bytes -- even ones of the same size and time -- are measured again; a check outlives its caller,
and the same check asked while it runs waits for it. A check that does not complete says why in one word
(``api.EngineError.reason``): its process lost, over a check's limits, the engine stopped, its callers all gone,
its document built again under it. On an engine, a state and a cache folder of this file's own."""

from __future__ import annotations

import dataclasses
import itertools
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
import uuid
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


# What measures in a process (``contract.measuring``), as a test's callers and its checks processes say it.
MEASURES = {"code": "c0de", "libraries": {"build123d": "0.13.0", "OCP": "8.0.1", "numpy": "2.0.0"}}


def _counts() -> dict[str, int]:
    from cad.engine import api

    return api.status()["checks"]


def _busy() -> list[int]:
    """The pids of the checks processes measuring now."""
    return [row["pid"] for row in _counts()["pool"]["processes"] if row["busy"]]


def _restarted() -> dict[str, int]:
    """The engine stopped and started again: its counts as it starts, which a test's own are counted from."""
    from cad.engine import api, client

    api.stop()
    return client.request({"op": "status"})["checks"]


def _until(case: unittest.TestCase, condition: Any, what: str) -> None:
    """``condition()`` awaited: a test that waits too long fails saying for what."""
    deadline = time.monotonic() + JOIN_SECONDS
    while not condition():
        case.assertLess(time.monotonic(), deadline, f"never: {what}")
        time.sleep(0.02)


# A test's seam, in the checks processes of an engine started with it (``held_engine``): a ``sitecustomize``
# first on ``PYTHONPATH`` that makes each check say it is measuring (``<hold>.reached``, holding the pid of its
# process) and wait until the file ``CAD_TEST_CHECK_HOLD`` names is there, so a test can build, inspect, kill or
# stop while a check measures. Nothing of it is in the library. The suite's own ``sitecustomize`` (the
# journal's, which this one would hide) runs after it.
SEAM = """
import os
import sys


def _seam():
    hold = os.environ.get("CAD_TEST_CHECK_HOLD")
    if not hold or "cad.engine.worker" not in " ".join(getattr(sys, "orig_argv", sys.argv)):
        return
    import time

    import cad.registry as registry

    integration = registry.manufacturing_check

    class Held:
        def __getattr__(self, name):
            return getattr(integration(), name)

        def held(self, *args, **kwargs):
            with open(hold + ".reached", "w", encoding="utf-8") as handle:
                handle.write(str(os.getpid()))
            deadline = time.monotonic() + SECONDS
            while not os.path.exists(hold) and time.monotonic() < deadline:
                time.sleep(0.01)
            return integration().held(*args, **kwargs)

    registry.manufacturing_check = Held


_seam()
if os.path.isfile(JOURNAL):
    with open(JOURNAL, encoding="utf-8") as _source:
        exec(compile(_source.read(), JOURNAL, "exec"))
"""


def held_engine(case: unittest.TestCase, env: dict[str, str] | None = None) -> tuple[dict[str, str], Path]:
    """An engine of the test's own whose checks wait at the seam (``SEAM``), started in ``env`` beside it: the
    environment it was started in, which a command of the test's runs in, and the file a check waits for.
    Stopped at the test's end, any check still waiting let go first."""
    from cad.engine import api

    api.stop()
    case.addCleanup(api.stop)
    folder = Path(os.path.realpath(tempfile.mkdtemp(prefix="engine-dfm-seam-")))
    case.addCleanup(shutil.rmtree, folder, True)
    hold = folder / "go"
    case.addCleanup(lambda: hold.write_text("", encoding="utf-8"))  # whatever happens, no check waits on
    (folder / "site").mkdir()
    (folder / "site" / "sitecustomize.py").write_text(
        f"SECONDS = {JOIN_SECONDS}\nJOURNAL = {str(engine_daemon.SITE / 'sitecustomize.py')!r}\n{SEAM}", encoding="utf-8")
    found = engine_daemon.watched({**os.environ, "PYTHONPATH": str(SRC), "CAD_TEST_CHECK_HOLD": str(hold),
                                   **(env or {})}, case.addCleanup)
    found["PYTHONPATH"] = os.pathsep.join((str(folder / "site"), found["PYTHONPATH"]))
    started = engine_daemon.run([sys.executable, "-c", "from cad.engine import client; client.connect()"], env=found)
    case.assertEqual(started.returncode, 0, started.stderr)
    return found, hold


def held_check(case: unittest.TestCase, hold: Path, check: Any) -> tuple["Checking", int]:
    """``check`` running in a thread, once its checks process says it is measuring: the thread, and that
    process's pid."""
    reached = Path(f"{hold}.reached")
    reached.unlink(missing_ok=True)
    thread = Checking(check)
    thread.start()
    _until(case, lambda: (reached.exists() and reached.read_text(encoding="utf-8")) or not thread.is_alive(),
           "the check reached its seam")
    case.assertTrue(thread.is_alive(), thread.answered)
    return thread, int(reached.read_text(encoding="utf-8"))


def box(case: unittest.TestCase, *heights: float) -> list[Path]:
    """A STEP of a box of each height, in a folder of the test's own."""
    import build123d as bd

    folder = Path(os.path.realpath(tempfile.mkdtemp(prefix="engine-dfm-box-")))
    case.addCleanup(shutil.rmtree, folder, True)
    steps = [folder / f"part{index}.step" for index in range(len(heights))]
    for height, step in zip(heights, steps):
        bd.export_step(bd.Box(30, 20, height), str(step))
    return steps


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
        its xbf (``material_from_json`` against the XCAF label), from the bytes its worker gives and, the engine
        stopped, from those its cache holds, alike."""
        import cad
        from cad.engine import api

        fixture = Fixture(self, DECLARED)
        (block,) = fixture.ids
        exported = fixture.folder / "block.xbf"
        api.export(block, exported, progress=False)
        self.assertEqual(api.check(block, {"type": "model", "process": None, "resolved": None, "candidates": False,
                                           "given": {}})["measured_in"], api.IN_ENGINE)
        held = cad.model.dfm(block)
        today = _today("model", exported, Path(block), None)
        self.assertEqual(_plain(held), _plain(today))
        self.assertEqual(held.measurements["process"], "cnc")
        self.assertTrue({"process_declared", "material_declared"} <= {f.code for f in held.findings})
        self.assertEqual(_plain(cad.xbf.dfm(exported)), _plain(_today("xbf", exported, exported.resolve(), None)))
        before = _restarted()  # its worker gone: the restarted engine answers from the result it kept on disk
        self.assertEqual(_plain(cad.model.dfm(block)), _plain(today))
        self.assertEqual((_counts()["measured"], _counts()["restored"]), (before["measured"], before["restored"] + 1))
        # Other checks: measured by the restarted engine from the bytes its cache holds, read once for both.
        for process in ("cnc", "sheet"):
            with self.subTest(process=process):
                self.assertEqual(_plain(cad.model.dfm(block, process=process, material="steel")),
                                 _plain(_today("model", exported, Path(block), process, material="steel")))
        self.assertEqual((_counts()["measured"], _counts()["read"]), (before["measured"] + 2, before["read"] + 1))


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
        from cad_server.engine.checks_runner import _clean

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

    def test_a_model_is_read_once_per_version_for_every_process(self) -> None:
        """A model's bytes are read once per version by the checks process that measures it (``worker._document``):
        a second process checked reads nothing, and an edit is read anew."""
        import cad

        fixture = Fixture(self, MODELS)
        plate = fixture.ids[0]
        read = _counts()["read"]
        for process in ("cnc", "sheet"):
            cad.model.dfm(plate, process=process)
        self.assertEqual(_counts()["read"], read + 1)
        fixture.build(MODELS.replace("bd.Box(40, 30, 10)", "bd.Box(42, 30, 10)"))
        edited = cad.model.dfm(plate, process="cnc")
        self.assertEqual(_counts()["read"], read + 2)
        self.assertAlmostEqual(edited.measurements["bodies"][0]["bbox_mm"][0], 42.0, delta=1e-6)

    def test_a_kept_result_outlives_the_engine(self) -> None:
        """Kept on disk beside the engine's cache: after a restart the same check of the same file or model
        measures nothing; another file's bytes, an edited model or an entry that does not read measure again."""
        import build123d as bd

        import cad
        fixture = Fixture(self, MODELS)
        plate = fixture.ids[0]
        step = fixture.folder / "kept.step"
        bd.export_step(bd.Box(30, 20, 6), str(step))
        first = cad.step.dfm(step, process="printing")
        model = cad.model.dfm(plate, process="cnc", tools="11")
        before = _restarted()
        self.assertEqual(_plain(cad.step.dfm(step, process="printing")), _plain(first))
        self.assertEqual(_plain(cad.model.dfm(plate, process="cnc", tools="11")), _plain(model))
        self.assertEqual((_counts()["measured"], _counts()["restored"]), (before["measured"], before["restored"] + 2),
                         "the restarted engine measured none")

        kept = list((Path(os.environ["CAD_CACHE_DIR"]) / "documents" / plate / "checks").glob("*.json"))
        self.assertEqual(len(kept), 1)
        kept[0].write_bytes(b"{not json")
        before = _restarted()
        self.assertEqual(_plain(cad.model.dfm(plate, process="cnc", tools="11")), _plain(model))
        self.assertEqual(_counts()["measured"], before["measured"] + 1, "an entry that does not read is measured again")
        self.assertEqual(json.loads(kept[0].read_text(encoding="utf-8"))["result"]["measured"]["process"], "cnc")

        bd.export_step(bd.Box(30, 20, 9), str(step))
        fixture.build(MODELS.replace("bd.Box(40, 30, 10)", "bd.Box(46, 30, 10)"))
        before = _restarted()
        cad.step.dfm(step, process="printing")
        cad.model.dfm(plate, process="cnc", tools="11")
        self.assertEqual((_counts()["measured"], _counts()["restored"]), (before["measured"] + 2, before["restored"]),
                         "other bytes, another build")

    def test_the_disk_store_holds_one_version_and_its_bounds_and_drops_what_does_not_read(self) -> None:
        from cad_server.engine.checks import Disk
        from cad_server.engine.registry import Folder

        folder = Folder(tempfile.mkdtemp(prefix="engine-dfm-disk-"))
        self.addCleanup(shutil.rmtree, folder.root, True)
        a, b, c = (str(uuid.uuid4()) for _ in range(3))  # ids, as the cache folder's are named
        store = Disk(lambda: folder, limit=2)
        store.keep(a, "r1", "cnc", {"x": 1}, MEASURES)
        store.keep(a, "r1", "sheet", {"x": 2})
        self.assertEqual((store.get(a, "r1", "cnc"), store.get(a, "r2", "cnc")), (({"x": 1}, MEASURES), None),
                         "kept with what measured it")
        store.keep(a, "r2", "cnc", {"x": 3})
        self.assertEqual(len(folder.names(f"documents/{a}/checks")), 1, "another version's results went")
        store.keep(b, "r", "cnc", {"x": 4})
        store.keep(c, "r", "cnc", {"x": 5})
        self.assertEqual((store.status()["held"], store.get(a, "r2", "cnc")), (2, None), "the least recently used went")
        self.assertEqual(folder.names(f"documents/{a}"), [], "its checks/ folder, empty, went with its last result")
        (place,) = folder.names(f"documents/{c}/checks")
        folder.write(f"documents/{c}/checks/{place}", json.dumps({"format": 1, "version": "other", "check": "cnc",
                                                                   "result": {}, "by": {}}).encode())
        self.assertIsNone(store.get(c, "r", "cnc"))
        self.assertEqual(folder.names(f"documents/{c}"), [], "never served, and removed")
        self.assertIsNone(Disk(lambda: None).get(a, "r", "cnc"), "no cache folder: nothing on disk")

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

    def test_a_deleted_document_keeps_nothing_and_its_entries_leave_the_index(self) -> None:
        """Deleting a document (``Registry.delete``) drops its results from memory and from the disk's index, and a
        check of it that began before keeps nothing. The half-written files a stopped engine left are swept as the
        folder is listed; a result gone since (its folder wiped) leaves the index as it is asked for; and a folder
        that takes no write keeps nothing, with nothing remembered of it."""
        from cad_server.engine import registry
        from cad_server.engine.checks import Checks, Disk
        from cad_server.engine.registry import Folder, Registry

        root = Path(tempfile.mkdtemp(prefix="engine-dfm-deleted-"))
        self.addCleanup(shutil.rmtree, root, True)
        held = Registry(root / "state", cache=root / "cache")
        store = Checks(folder=lambda: held)
        registry.FORGOTTEN.append(store.deleted)
        self.addCleanup(registry.FORGOTTEN.remove, store.deleted)
        a, b = str(uuid.uuid4()), str(uuid.uuid4())
        store.keep(f"model:{a}", "v", "cnc", {"x": 1}, (a, "r"))
        store.keep("file:2:3", "d", "cnc", {"x": 2}, (b, "d"))
        self.assertEqual(store.status()["disk"]["held"], 2)
        since = store.epoch(b)
        held.delete(b)
        self.assertEqual((store.status()["held"], store.status()["disk"]["held"]), (1, 1), "its entries went")
        store.keep("file:2:3", "d", "cnc", {"x": 2}, (b, "d"), since)
        self.assertEqual(held.cache.names(f"documents/{b}"), [], "a check that began before its deletion keeps nothing")
        self.assertIsNone(store.get("file:2:3", "d", "cnc"))

        shutil.rmtree(held.cache.path("documents"))  # a person wiping the cache folder
        self.assertIsNone(store.disk.get(a, "r", "cnc"))
        self.assertEqual(store.status()["disk"]["held"], 0, "gone with its folder: out of the index as it is asked for")

        sealed = {"on": True}

        class Sealed(Folder):
            def write(self, inside: str, data: bytes, mode: int | None = None) -> Path:
                if sealed["on"]:
                    raise PermissionError(inside)
                return super().write(inside, data, mode)

        folder = Sealed(root / "sealed")
        folder.path(f"documents/{a}/checks").mkdir(parents=True)
        folder.path(f"documents/{a}/checks/0-0.json.1.ab.tmp").write_bytes(b"{")
        disk = Disk(lambda: folder)
        disk.keep(a, "r", "cnc", {"x": 1})
        self.assertEqual((disk.get(a, "r", "cnc"), disk.status()["held"]), (None, 0), "no write taken: nothing kept")
        self.assertEqual(folder.names(f"documents/{a}/checks"), [], "the half-written file swept as it was listed")
        sealed["on"] = False
        disk.keep(a, "r", "cnc", {"x": 1})
        self.assertEqual(disk.get(a, "r", "cnc"), ({"x": 1}, {}), "kept as soon as it takes one")

    def test_the_code_is_in_the_key_and_what_measured_it_is_kept_with_it(self) -> None:
        """A result is kept under its check, its release and its library's code -- another code is another
        check -- with what measured it beside it, served to a caller its measurer measures for: never one of
        another library's version, always one with no kernel, which names no library."""
        from cad.engine.contract import measures_for
        from cad_server.engine.checks import Checks

        other = {**MEASURES, "code": "other"}
        newer = {**MEASURES, "libraries": {**MEASURES["libraries"], "build123d": "0.13.1"}}
        bare = {**MEASURES, "libraries": {}}
        keys = {Checks.key({"type": "step", "token": "t"}, "1.0.0", measures["code"])
                for measures in (MEASURES, other, newer, bare)}
        self.assertEqual(len(keys), 2, "the code alone of what measures it")
        self.assertEqual(Checks.key({"type": "step", "token": "a", "measures": other}, "1.0.0", "c0de"),
                         Checks.key({"type": "step", "token": "b"}, "1.0.0", "c0de"), "never its token or own")
        self.assertTrue(measures_for(MEASURES, MEASURES) and measures_for(bare, MEASURES))
        self.assertFalse(measures_for(other, MEASURES) or measures_for(newer, MEASURES) or measures_for(None, MEASURES))
        store = Checks()
        store.keep("model:a", "v1", "k", {"x": 1}, by=MEASURES)
        self.assertEqual(store.get("model:a", "v1", "k", serves=lambda by: measures_for(bare, by)), {"x": 1})
        self.assertIsNone(store.get("model:a", "v1", "k", serves=lambda by: measures_for(newer, by)))

    def test_what_measures_is_the_code_as_it_loaded_and_the_b_rep_checks_libraries(self) -> None:
        """Taken when a check is first asked, never as ``cad.engine`` is imported, of every source file -- a
        ``.py``, or the ``.pyc`` an install of bytecode alone has in its place, never ``__pycache__`` -- read again
        only once one's size or time changes; a code edited since the library loaded is no other process's. The
        libraries a B-rep check measures with, each read from the path's listings (two of one name in a folder:
        the one written last); a process with no kernel names no library."""
        import importlib.metadata
        import importlib.util

        import cad
        from cad.engine import _measuring, contract

        imported = subprocess.run([sys.executable, "-c", "import sys, cad.engine; print('cad.engine._measuring' in "
                                   "sys.modules)"], env={**os.environ, "PYTHONPATH": str(SRC)}, capture_output=True,
                                  text=True, check=True)
        self.assertEqual(imported.stdout.strip(), "False", "nothing of it loads, nor is taken, on import")
        self.assertFalse(contract.measuring()["code"].endswith(_measuring.EDITED), "the code as this process loaded it")
        with mock.patch.dict(_measuring._TAKEN, clear=True), mock.patch.object(cad, "_LOADED_NS", 0):
            self.assertTrue(contract.measuring()["code"].endswith(_measuring.EDITED), "edited since it loaded")
        self.assertEqual(set(contract.measure()["libraries"]), {"build123d", "OCP", "bd_materials", "numpy"})
        with mock.patch.object(importlib.metadata, "version", side_effect=AssertionError("the long way")):
            self.assertEqual(_measuring._version("OCP", _measuring.MEASURING["OCP"], {"cadquery_ocp": "8.0.1"}),
                             "8.0.1", "cadquery-ocp as well as its -novtk, from the listings")
            self.assertIsNone(_measuring._version("bd_materials_not_here", ("bd-materials-not-here",), {}),
                              "a library not installed: None, never asked the long way")
        site = Path(tempfile.mkdtemp(prefix="engine-dfm-site-"))
        self.addCleanup(shutil.rmtree, site, True)
        for said, when in (("1.1", 2_000_000_000), ("1.0", 1_000_000_000)):
            (site / f"twice-{said}.dist-info").mkdir()
            (site / f"twice-{said}.dist-info" / "METADATA").write_text("Name: twice\n", encoding="utf-8")
            os.utime(site / f"twice-{said}.dist-info" / "METADATA", ns=(when, when))
        with mock.patch.object(sys, "path", [str(site)]):
            self.assertEqual(_measuring._installed(), {"twice": "1.1"}, "the one written last")
        with mock.patch.object(importlib.util, "find_spec", return_value=None):
            self.assertEqual(contract.measure()["libraries"], {}, "no kernel: no library named")
        root = Path(tempfile.mkdtemp(prefix="engine-dfm-code-"))
        self.addCleanup(shutil.rmtree, root, True)
        (root / "__pycache__").mkdir()
        for name, data in (("a.py", b"a"), ("b.pyc", b"b"), ("a.pyc", b"x"), ("__pycache__/a.cpython.pyc", b"y")):
            (root / name).write_bytes(data)
        first = contract.measure(root)["code"]
        with mock.patch("builtins.open", side_effect=AssertionError("read again")):
            self.assertEqual(_measuring._code(root)[0], first, "the same files, sizes and times: none read")
        for name, changes in (("a.pyc", False), ("__pycache__/a.cpython.pyc", False), ("b.pyc", True), ("a.py", True)):
            with self.subTest(name=name):
                (root / name).write_bytes(b"edited " + name.encode())
                self.assertEqual(contract.measure(root)["code"] != first, changes)
                first = contract.measure(root)["code"]

class ReleaseTest(unittest.TestCase):
    """A library of another release than the engine's is answered at once with nothing measured, and measures a
    file itself and a model as before (exported, read back), as one that reaches no engine does a file, saying
    so; the pool of checks processes; and what a checks process holds of what it read."""

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

    def test_an_engine_that_stops_mid_check_says_to_check_again_and_measures_nothing_here(self) -> None:
        import build123d as bd

        import cad
        from cad.build123d import _dfm_check
        from cad.engine import api, client

        folder = Path(tempfile.mkdtemp(prefix="engine-dfm-stop-"))
        self.addCleanup(shutil.rmtree, folder, True)
        step = folder / "box.step"
        bd.export_step(bd.Box(20, 20, 15), str(step))
        with mock.patch.object(client, "connect", return_value=object()), \
                mock.patch.object(api, "_ask", side_effect=ConnectionError("the engine server closed the connection")), \
                mock.patch.object(_dfm_check, "measure", side_effect=AssertionError("measured here")):
            with self.assertRaises(api.Stopped) as stopped:
                cad.step.dfm(step, process="printing")
        self.assertIn("run the check again", str(stopped.exception))

    def test_the_pool_runs_a_check_per_slot_and_one_past_it_waits_saying_so(self) -> None:
        from cad_server.engine.checks import Pool, Withdrawn

        live: list[Any] = []
        room = {"cap": None}
        supervisor = SimpleNamespace(processes=lambda _service: list(live), pressed=lambda: False,
                                     memory=lambda: room["cap"], resident=lambda: 900.0)
        pool = Pool(supervisor, 2)
        self.assertEqual((pool.take("file:a"), pool.take("file:b")), ("checks", "checks-2"))
        said: list[str] = []
        third = Checking(lambda: pool.take("file:c", waiting=said.append))
        third.start()
        _until(self, lambda: said, "the third says it waits")
        self.assertIn("waiting for another manufacturing check", said[0])
        self.assertIn("the 2 checks processes are all busy", said[0])
        self.assertTrue(third.is_alive())
        pool.give("checks")
        self.assertEqual(third.result(self), "checks")
        self.assertEqual(len(said), 1, "said once")
        pool.give("checks")
        pool.give("checks-2")
        live.extend(SimpleNamespace(key=key, pid=1, rss=400.0, retired=False, alive=lambda: True)
                    for key in ("checks", "checks-2"))
        self.assertEqual(pool.take("file:b"), "checks-2", "the slot that last read it")
        pool.give("checks-2")
        del live[1]
        room["cap"] = 1000.0  # no room for another of 400 MB beside 900
        self.assertEqual(pool.take("file:a"), "checks")
        before = len(said)
        with self.assertRaises(Withdrawn):  # given up once it has said what it waits for
            pool.take("file:b", gave_up=lambda: len(said) > before, waiting=said.append)
        self.assertIn("the engine's memory has no room for another checks process", said[-1])

    def test_a_waiter_the_memory_has_no_room_for_reaps_as_one_past_a_full_pool_does(self) -> None:
        """A slot free but no room for another checks process: the waiter asks its ``reap`` as it waits, as it
        does with every slot busy; a waiter deferring to another asks nothing."""
        from cad_server.engine.checks import Pool, Withdrawn

        pool = Pool(SimpleNamespace(processes=lambda _service: [], pressed=lambda: False, memory=lambda: 1000.0,
                                    resident=lambda: 900.0, standby=lambda _service: SimpleNamespace(rss=400.0)), 2)
        self.assertEqual(pool.take("file:a"), "checks")
        reaped: list[str] = []
        with self.assertRaises(Withdrawn):
            pool.take("file:b", gave_up=lambda: bool(reaped), reap=lambda: reaped.append("b"))
        self.assertEqual(reaped, ["b"], "no room beside the one measuring: an abandoned one's process is wanted")
        reaped.clear()
        with self.assertRaises(Withdrawn):
            calls = iter((False, True))
            pool.take("file:c", gave_up=lambda: next(calls), reap=lambda: reaped.append("c"), defer=lambda: True)
        self.assertEqual(reaped, [], "deferring, it reaps nothing")

    def test_the_pool_counts_a_process_it_has_not_heard_from_and_those_starting(self) -> None:
        """No checks process has said its memory: the last one's, else the standby's, else the smallest worker's
        stands for it, and each slot being started counts, so a burst of checks never starts past the cap."""
        from cad_server.engine.checks import Pool, Withdrawn

        live: list[Any] = []
        workers: list[Any] = []
        spare = {"rss": None}
        supervisor = SimpleNamespace(processes=lambda service: list(live if service == "checks" else workers),
                                     pressed=lambda: False, memory=lambda: 1000.0, resident=lambda: 500.0,
                                     standby=lambda _service: SimpleNamespace(rss=spare["rss"]))
        pool = Pool(supervisor, 3)
        self.assertEqual(pool.size_of({}), 0.0, "nothing said: no floor")
        workers.append(SimpleNamespace(rss=300.0, alive=lambda: True, retired=False))
        self.assertEqual(pool.size_of({}), 300.0, "the smallest worker's")
        spare["rss"] = 200.0
        self.assertEqual(pool.size_of({}), 200.0, "the standby's: a kernel loaded, nothing built")
        self.assertEqual(pool.take("file:a"), "checks", "one of 200 MB beside 500")
        self.assertEqual(pool.take("file:b"), "checks-2", "two being started, 900 of 1000")
        said: list[str] = []
        with self.assertRaises(Withdrawn):  # a third would be 1100: it waits, and gives up once it has said so
            pool.take("file:c", gave_up=lambda: bool(said), waiting=said.append)
        self.assertIn("no room for another checks process", said[0])
        live.append(SimpleNamespace(key="checks", pid=1, rss=450.0, retired=False, alive=lambda: True))
        pool.size_of({"checks": live[0]})
        live.clear()
        self.assertEqual(pool.size_of({}), 450.0, "the last one's, after it is gone")

    def test_the_pool_is_half_the_cores_and_its_setting_held_to_them(self) -> None:
        from cad_server.engine import checks

        for cores, given, size, said in ((16, "", 4, False), (2, "", 1, False), (1, "", 1, False), (8, "3", 3, False),
                                         (8, "0", 1, True), (8, "64", 8, True), (8, "many", 4, True)):
            with self.subTest(cores=cores, given=given), mock.patch.object(os, "cpu_count", return_value=cores), \
                    mock.patch.dict(os.environ, {"CAD_ENGINE_CHECKS": given}):
                found, line = checks.pool_size()
                self.assertEqual((found, line is not None), (size, said))

    def test_a_file_is_one_key_by_any_of_its_names(self) -> None:
        from cad_server.engine.checks_runner import file_key as _file_key
        from cad_server.engine.models import durable, revision

        folder = Path(tempfile.mkdtemp(prefix="engine-dfm-names-"))
        self.addCleanup(shutil.rmtree, folder, True)
        first = folder / "Part.step"
        first.write_bytes(b"x")
        other = folder / "link.step"
        os.link(first, other)
        self.assertEqual(_file_key(str(first)), _file_key(str(other)), "a hard link")
        if (folder / "part.step").exists():  # a file system that folds case: the other spelling is the file
            self.assertEqual(_file_key(str(folder / "part.step")), _file_key(str(first)))
        self.assertNotEqual(_file_key(str(first)), _file_key(str(folder / "elsewhere.step")))
        self.assertTrue(durable(revision({"closure": {"key": "ab12"}})))
        self.assertFalse(durable(revision({})) or durable(None) or durable(""))

    def test_what_a_checks_process_read_is_bounded_by_bytes_and_shed_over_the_cap(self) -> None:
        from cad.engine import contract, worker

        memo = {name: (name, None, size) for name, size in (("a", 10), ("b", worker.KEPT_BYTES - 5), ("c", 10))}
        worker._bounded(memo, 4, lambda row: row[2])
        self.assertEqual(list(memo), ["c"], "held to its bytes, the least recently used going first")
        worker._FILES["x"] = ("d", None, 1)
        worker._DOCUMENTS["y"] = ("v", None, 1)
        with mock.patch.object(worker, "resident_mb", return_value=5000.0):
            worker.resident_after_check(1000.0)
        self.assertEqual((worker._FILES, worker._DOCUMENTS), ({}, {}), "dropped where the process is over its cap")
        # A caller of other code is measured nothing, before anything is read; and a file rewritten while it was
        # read is measured nothing either, and says so.
        check = {"type": "step", "process": "cnc", "resolved": {}, "token": "t", "measures": contract.measuring()}
        unlike = {**check, "measures": {**contract.measuring(), "code": "other"}}
        self.assertNotIn("checked", worker._check({"source": {"path": "/nowhere/part.step"}, "check": unlike}))
        with mock.patch.object(worker, "_file", return_value=(object(), None, True)):
            torn = worker._check({"source": {"path": "/nowhere/part.step"}, "check": check})["checked"]
        self.assertEqual((torn["changed"], "measured" in torn), (True, False))

    def test_status_says_each_check_running_and_whether_its_caller_waits(self) -> None:
        from cad_server.engine.cli import status_text

        text = status_text({"pid": 1, "workers": [], "cap": 4, "checks": {"running": [
            {"type": "step", "process": "printing", "file": "/p/box.step", "state": "measuring", "where": "checks-2",
             "seconds": 21.0, "attached": False, "waiting": False},
            {"type": "model", "process": "cnc", "document": "abc", "state": "waiting", "where": None,
             "seconds": 3.0, "attached": True, "waiting": True}]}})
        self.assertIn("check    printing of box.step in checks-2 · 21s · its caller gone", text)
        self.assertIn("check    cnc of abc waiting for its process · 3s", text)

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

    def test_a_file_checked_with_no_engine_to_reach_is_measured_here_and_one_line_says_so(self) -> None:
        """No engine can be reached or started (a sandbox, no installation): a file's check is measured in the
        calling process, and one line on stderr says why and that nothing keeps it, so it is measured again each
        time; the failure itself carries its reason."""
        from contextlib import redirect_stderr
        from io import StringIO

        import cad
        from cad.engine import api, client

        (step,) = box(self, 6)
        expected = _plain(_today("step", step, step.resolve(), "printing"))
        check = {"type": "step", "process": "printing", "candidates": False,
                 "resolved": cad._internal.manufacturing.options("step", "printing", {})}
        said = StringIO()
        with mock.patch.object(client, "connect", side_effect=ConnectionError("cad-server is not installed here")), \
                redirect_stderr(said):
            self.assertEqual(_plain(cad.step.dfm(step, process="printing")), expected)
            with self.assertRaises(api.Unreached) as unreached:
                api.check(step, check)
        self.assertEqual(unreached.exception.reason, "unreachable")
        lines = [line for line in said.getvalue().splitlines() if line.startswith("cad: ")]
        self.assertEqual(len(lines), 2, "one line a check")
        self.assertIn("no CAD server could be reached (cad-server is not installed here)", lines[0])
        self.assertIn("measured again each time", lines[0])
        self.assertEqual(api.check(step, check)["measured_in"], api.IN_ENGINE)


class EngineTest(unittest.TestCase):
    """A check on a running engine, with what goes on beside it: a build and an inspection of its model, its
    caller going, a second caller, its checks process killed, the engine stopping, a check's limits. A check
    waits at the test's seam (``held_engine``) until the test lets it go."""

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
        changes the model lands at once too, and the check of the version gone answers ``superseded``, never a
        result."""
        import cad
        from cad.engine.api import EngineError

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
        check, _pid = held_check(self, hold, lambda: cad.model.dfm(plate, process="cnc", tools="4"))
        fixture.build(MODELS.replace("bd.Box(40, 30, 10)", "bd.Box(44, 30, 10)"))  # an edit, built under the check
        hold.write_text("", encoding="utf-8")
        answered = check.result(self)
        self.assertIsInstance(answered, EngineError)
        self.assertEqual(answered.reason, "superseded")
        edited = cad.model.dfm(plate, process="cnc", tools="4")
        self.assertAlmostEqual(edited.measurements["bodies"][0]["bbox_mm"][0], 44.0, delta=1e-6)

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

    def test_an_update_s_drain_waits_for_no_check_and_its_checks_say_stopped(self) -> None:
        """A drain for an update with a check measuring and another waiting for its process: neither is waited
        for, and both callers are told the engine stopped (``api.Stopped``: run the check again)."""
        from cad.engine import client

        env, hold = held_engine(self, {"CAD_ENGINE_CHECKS": "1"})
        reached = Path(f"{hold}.reached")
        callers = []
        for step in box(self, 6, 7):
            code = (f"import cad\nfrom cad.engine import api\ntry:\n    cad.step.dfm({str(step)!r}, process='printing')\n"
                    "except api.Stopped as error:\n    print('stopped:', error.reason, error)")
            callers.append(subprocess.Popen([sys.executable, "-c", code], env=env, stdout=subprocess.PIPE,
                                            stderr=subprocess.DEVNULL, text=True))
            self.addCleanup(callers[-1].stdout.close)
            self.addCleanup(callers[-1].wait)
            self.addCleanup(callers[-1].kill)
            if len(callers) == 1:
                _until(self, reached.exists, "the first check runs")
        _until(self, lambda: _counts()["asked"] == 2, "the second waits for the checks process")
        self.assertIsNotNone(client.request({"op": "stop", "drain": True}, start=False))
        self.assertTrue(client.wait_gone(), "the engine drained and stopped with the checks under way")
        for caller in callers:
            out = caller.communicate(timeout=JOIN_SECONDS)[0]
            self.assertIn("stopped: stopped the CAD server stopped while it measured the manufacturing check", out)
        self.assertFalse(hold.exists(), "neither check was let go")

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

    def test_a_caller_of_other_code_or_libraries_is_measured_by_no_process_here(self) -> None:
        """A library whose code or measuring libraries are not the engine's (a checkout's edited copy at the same
        release, a base made again with a newer build123d) is measured by no process here and served nothing the
        engine kept: it measures the file itself; the same code is served the result kept."""
        import cad
        from cad.engine import contract

        (step,) = box(self, 7)
        first = cad.step.dfm(step, process="printing")
        before = _counts()
        real = contract.measuring()
        for unlike in ({**real, "code": "edited"}, {**real, "libraries": {**real["libraries"], "build123d": "0.0.1"}}):
            with self.subTest(unlike=unlike), mock.patch.object(contract, "measuring", return_value=unlike):
                self.assertEqual(_plain(cad.step.dfm(step, process="printing")), _plain(first), "measured here")
        self.assertEqual((_counts()["measured"], _counts()["reused"]), (before["measured"], before["reused"]))
        cad.step.dfm(step, process="printing")
        self.assertEqual(_counts()["reused"], before["reused"] + 1, "the same code reuses its result")

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

    def test_a_checks_process_killed_in_a_check_tells_every_caller_and_the_next_check_starts_another(self) -> None:
        """Its checks process killed under it (as the system's out-of-memory killer does), the check is not run
        again: its caller and one that waited for it are both told, with what a kill by the system usually
        means, and the next check is a fresh process's."""
        import cad
        from cad.engine.api import EngineError

        _env, hold = held_engine(self)
        (step,) = box(self, 6)
        before = _counts()
        first, pid = held_check(self, hold, lambda: cad.step.dfm(step, process="printing"))
        second = Checking(lambda: cad.step.dfm(step, process="printing"))
        second.start()
        _until(self, lambda: _counts()["waited"] == before["waited"] + 1, "the second waits for the first")
        killed = hasattr(signal, "SIGKILL")
        os.kill(pid, signal.SIGKILL if killed else signal.SIGTERM)
        for thread in (first, second):
            answered = thread.result(self)
            self.assertIsInstance(answered, EngineError)
            self.assertEqual(answered.reason, "process_lost")
            self.assertIn("The check is not run again", str(answered))
            if killed:
                self.assertIn("killed by the system, usually for memory", str(answered))
        hold.write_text("", encoding="utf-8")
        self.assertEqual(cad.step.dfm(step, process="printing").measurements["process"], "printing")
        self.assertNotIn(pid, [row["pid"] for row in _counts()["pool"]["processes"]], "a fresh checks process")

    def test_a_check_over_its_memory_limit_is_stopped_and_says_so(self) -> None:
        """A check's own memory limit (1 MB, which any checks process is over), read from outside the process: the
        check is stopped where it is -- never let go here -- and its caller told why and what to do."""
        import cad
        from cad.engine.api import EngineError
        from cad_server.engine.checks_runner import resident_of

        if resident_of(os.getpid()) is None:
            self.skipTest("this system does not say a process's memory from outside it")
        _env, hold = held_engine(self, {"CAD_ENGINE_CHECK_RSS_MB": "1"})
        (step,) = box(self, 6)
        check = Checking(lambda: cad.step.dfm(step, process="printing"))
        check.start()
        answered = check.result(self)
        self.assertIsInstance(answered, EngineError)
        self.assertEqual(answered.reason, "over_memory")
        self.assertIn("over a check's memory limit of 1 MB", str(answered))
        self.assertIn("CAD_ENGINE_CHECK_RSS_MB", str(answered))
        self.assertFalse(hold.exists(), "stopped by the engine, not let go")
        self.assertEqual((_counts()["asked"], _counts()["pool"]["busy"]), (0, 0), "its slot is free again")

    def test_a_checks_process_over_the_memory_cap_after_a_check_is_retired(self) -> None:
        """A real cap: the checks process is over it after its check, so the next check starts another. The cap is
        the engine's, so an engine of this test's own, with no limit of a check's own under it."""
        import cad
        from cad.engine import api

        (step,) = box(self, 15)
        api.stop()
        self.addCleanup(api.stop)
        with mock.patch.dict(os.environ, {"CAD_ENGINE_WORKER_RSS_MB": "1", "CAD_ENGINE_CHECK_RSS_MB": "0"}):
            first = cad.step.dfm(step, process="printing")
            second = cad.step.dfm(step, process="sheet")
        self.assertEqual((first.measurements["process"], second.measurements["process"]), ("printing", "sheet"))
        retired = [row for row in api.status()["retired"] if row.get("process")]
        self.assertEqual(len(retired), 2, "each retired after its check, listed as what it is")
        self.assertNotEqual(retired[0]["pid"], retired[1]["pid"])

    def test_a_request_that_is_no_check_is_refused_and_a_check_that_fails_there_answers_one_line(self) -> None:
        """What a caller that speaks the protocol by hand meets: a process the type has none of is refused in one
        line before anything is read, and a check whose measuring raises answers its type and words (reason
        ``error``), its stack never sent."""
        import cad
        from cad.engine import api
        from cad.engine.contract import measuring, release

        (step,) = box(self, 6)
        cad.step.dfm(step, process="cnc")
        order = {"op": "export", "source": {"path": str(step)}, "destinations": [], "caller": release(),
                 "measures": measuring()}
        before = _counts()["measured"]
        with self.assertRaises(ValueError) as refused:
            api._ask({**order, "check": {"type": "step", "process": "nope", "resolved": {}, "token": "t"}})
        self.assertIn("a check's process is cnc, sheet, molding or printing, not 'nope'", str(refused.exception))
        with self.assertRaises(api.EngineError) as failed:  # options no caller resolved: the measuring raises there
            api._ask({**order, "check": {"type": "step", "process": "printing", "resolved": {}, "token": "t"}})
        self.assertEqual(failed.exception.reason, "error")
        self.assertNotIn("Traceback", str(failed.exception))
        self.assertEqual(len(str(failed.exception).splitlines()), 1)
        self.assertEqual(_counts()["measured"], before, "neither is a check measured")


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
            engine.versions[DOC] = "later"
            return engine.measured(order)

        engine.answer = built_under_it
        self.assertEqual(engine.check({"id": DOC}, process="sheet"), {"failed": SUPERSEDED, "reason": "superseded"})
        engine.answer = engine.measured
        self.assertNotIn("reused", engine.check({"id": DOC}, process="sheet")["done"], "nothing of it was kept")

        file = self.file()
        engine.answer = lambda order: engine.measured(order, digest=None, changed=True)
        self.assertEqual(engine.check(file)["reason"], "superseded", "a file rewritten while it was read")
        engine.answer = lambda order: engine.measured(order, digest="another")
        self.assertIn("checked", engine.check(file)["done"], "rewritten before it was read: measured as it is now")
        engine.answer = engine.measured
        self.assertNotIn("reused", engine.check(file)["done"], "and kept under no digest but the one measured")
        self.assertTrue(engine.check(file)["done"]["reused"])

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
        self.assertIn("checked", engine.check(self.file())["done"])
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
