"""A manufacturing check (``cad <type> dfm``, ``cad.<type>.dfm``) measured where the engine holds the
document: a model's in its warm worker, a STEP's and an xbf's -- and a document no warm worker holds -- in
the engine's checks process, nothing exported or read again (``worker._check``, ``Daemon.check``). Its result
equals the one the same document gets read from a file in a process of its own, for every process, with no
process given and ranking candidates; the same check of an unchanged document is the engine's kept result
(``checks``), measuring nothing; an edit, other options or another file's bytes -- even ones of the same size
and time -- are measured again; a check outlives its caller, and the same check asked while it runs waits for it;
a build of the model's script cancels a check running in its worker or waiting for it, and a cancel landing as a
check ends hangs nothing; a worker killed in a check says so. On an engine, a state and a cache folder of this
file's own."""

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


# What measures here (``contract.measuring``): what a fake daemon's caller and its processes say.
MEASURES = {"code": "c0de", "libraries": {"build123d": "0.13.0", "OCP": "8.0.1", "numpy": "2.0.0"}}


def _fake(records: dict[str, Any], document: Any, call: Any) -> SimpleNamespace:
    """A daemon of ``records`` (its models' versions), whose documents ``document`` reads and whose processes
    ``call`` asks, with ``Daemon.check``'s own helpers: what ``Daemon.check`` runs on, nothing started."""
    from cad_server.engine.checks import Checks
    from cad_server.engine.daemon import Daemon

    fake = SimpleNamespace(models=SimpleNamespace(adopt=lambda _ident: None, lock=threading.Lock(), records=records),
                           checks=Checks(), asked={}, running={}, asked_lock=threading.Lock(), document=document,
                           _call=call, stopping=threading.Event(), draining=False)
    for name in ("_version", "_durable", "_routed"):
        setattr(fake, name, getattr(Daemon, name).__get__(fake))
    # As an installed engine is before any process has said what measures in it (``own`` false): nothing known.
    fake._base_measures = lambda *_said: None
    fake._worker_measures = lambda _key, _python_key: None
    return fake


def _counts() -> dict[str, int]:
    from cad.engine import api

    return api.status()["checks"]


def _busy() -> list[int]:
    """The pids of the checks processes measuring now."""
    return [row["pid"] for row in _counts()["pool"]["processes"] if row["busy"]]


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
        api.stop()  # its worker gone: the restarted engine answers from the result it kept on disk
        self.assertEqual(_plain(cad.model.dfm(block)), _plain(today))
        self.assertEqual((_counts()["measured"], _counts()["restored"]), (0, 1))
        # Other checks: measured by the restarted engine in a checks process, from the bytes its cache holds,
        # read there once for both.
        for process in ("cnc", "sheet"):
            with self.subTest(process=process):
                self.assertEqual(_plain(cad.model.dfm(block, process=process, material="steel")),
                                 _plain(_today("model", exported, Path(block), process, material="steel")))
        self.assertEqual((_counts()["measured"], _counts()["read"]), (2, 1))


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

    def test_a_model_is_read_once_per_version_for_every_process(self) -> None:
        """A warm worker reads a build's parts back once per version (``_dfm_brep.of_source``'s ``keep``): a
        second process checked reads nothing, and an edit reads its parts anew."""
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
        from cad.engine import api

        fixture = Fixture(self, MODELS)
        plate = fixture.ids[0]
        step = fixture.folder / "kept.step"
        bd.export_step(bd.Box(30, 20, 6), str(step))
        first = cad.step.dfm(step, process="printing")
        model = cad.model.dfm(plate, process="cnc", tools="11")
        api.stop()
        self.assertEqual(_plain(cad.step.dfm(step, process="printing")), _plain(first))
        self.assertEqual(_plain(cad.model.dfm(plate, process="cnc", tools="11")), _plain(model))
        self.assertEqual((_counts()["measured"], _counts()["restored"]), (0, 2), "the restarted engine measured none")

        kept = list((Path(os.environ["CAD_CACHE_DIR"]) / "documents" / plate / "checks").glob("*.json"))
        self.assertEqual(len(kept), 1)
        kept[0].write_bytes(b"{not json")
        api.stop()
        self.assertEqual(_plain(cad.model.dfm(plate, process="cnc", tools="11")), _plain(model))
        self.assertEqual(_counts()["measured"], 1, "an entry that does not read is measured again")
        self.assertEqual(json.loads(kept[0].read_text(encoding="utf-8"))["result"]["measured"]["process"], "cnc")

        bd.export_step(bd.Box(30, 20, 9), str(step))
        fixture.build(MODELS.replace("bd.Box(40, 30, 10)", "bd.Box(46, 30, 10)"))
        api.stop()
        cad.step.dfm(step, process="printing")
        cad.model.dfm(plate, process="cnc", tools="11")
        self.assertEqual((_counts()["measured"], _counts()["restored"]), (2, 0), "other bytes, another build")

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
        check of it that began before keeps nothing; a cache folder wiped is indexed again, the half-written files
        a stopped engine left swept."""
        from cad_server.engine import registry
        from cad_server.engine.checks import Checks
        from cad_server.engine.registry import Registry

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

        half = held.cache.path(f"documents/{a}/checks/0-0.json.1.ab.tmp")
        half.write_bytes(b"{")
        shutil.rmtree(held.cache.path("documents"))  # a person wiping the cache folder
        held.cache.write(f"documents/{a}/checks/0-0.json.1.ab.tmp", b"{")
        store.keep(f"model:{a}", "w", "cnc", {"x": 3}, (a, "s"))
        self.assertEqual(store.status()["disk"]["held"], 1, "indexed again: the wiped entries gone")
        self.assertEqual([name for name in held.cache.names(f"documents/{a}/checks") if name.endswith(".tmp")], [],
                         "the half-written file swept")

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
            (site / f"twice-{said}.dist-info" / "METADATA").write_text("Name: twice\n")
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

    def test_a_check_is_measured_again_by_other_code_and_reused_by_the_same(self) -> None:
        """The probe's case on a daemon of fakes: the same check of the same version, asked by a library of other
        code at the same release, is measured again and kept beside the first; the same code reuses its own."""
        from cad.engine.previous import version
        from cad_server.engine.daemon import Daemon

        asked: list[Any] = []

        def call(_routed: Any, order: Any, answered: Any, _payload: bytes) -> None:
            asked.append(order["check"]["measures"])
            answered({"done": {"checked": {"measured": {"report": {"by": order["check"]["measures"]["code"]}},
                                           "release": version(), "measures": order["check"]["measures"]}}})

        fake = _fake({"id": {"version": "v1", "revision": "k1"}},
                     lambda _ident: ({"document": "id", "name": "plate"}, b"bytes"), call)
        other = {**MEASURES, "code": "edited"}
        found = []
        for measures in (MEASURES, other, MEASURES, other):
            said: list[dict[str, Any]] = []
            Daemon.check(fake, {"source": {"id": "id"}, "check": {"type": "model", "token": "t"}, "caller": version(),
                                "measures": measures}, said.append)
            found.append(said[-1]["done"]["checked"]["measured"]["report"]["by"])
        self.assertEqual(asked, [MEASURES, other], "each code measured once")
        self.assertEqual(found, ["c0de", "edited", "c0de", "edited"], "and each served its own")

    def test_a_kept_result_serves_every_caller_its_measurer_measures_for_across_a_restart(self) -> None:
        """As an installed engine is (its kernel environment not the server's, so nothing is known of what
        measures until a process says it): a result a script's check kept is served, after a restart, to the
        ``cad`` command, which has no kernel and names no library, and to the script again; a caller of another
        library's version is measured again, and its result serves the command from then on."""
        from cad.engine.previous import version
        from cad_server.engine.checks import Checks
        from cad_server.engine.daemon import Daemon
        from cad_server.engine.registry import Folder

        folder = Folder(tempfile.mkdtemp(prefix="engine-dfm-restart-"))
        self.addCleanup(shutil.rmtree, folder.root, True)
        ident = str(uuid.uuid4())
        measured: list[Any] = []

        def call(_routed: Any, order: Any, answered: Any, _payload: bytes) -> None:
            asked = order["check"]["measures"]
            by = asked if asked["libraries"] else MEASURES  # the process measuring says its own
            measured.append(by)
            answered({"done": {"checked": {"measured": {"report": {"by": by["libraries"]}}, "release": version(),
                                           "measures": by}}})

        def ask(measures: dict[str, Any]) -> dict[str, Any]:
            engine = _fake({ident: {"version": "v1", "revision": "k1"}},
                           lambda _ident: ({"document": ident, "name": "plate"}, b"bytes"), call)
            engine.checks = Checks(folder=lambda: folder)  # a fresh engine on the same cache folder
            said: list[dict[str, Any]] = []
            Daemon.check(engine, {"source": {"id": ident}, "check": {"type": "model", "process": "cnc", "token": "t"},
                                  "caller": version(), "measures": measures}, said.append)
            return said[-1]["done"]

        bare = {"code": MEASURES["code"], "libraries": {}}
        newer = {**MEASURES, "libraries": {**MEASURES["libraries"], "numpy": "2.1.0"}}
        self.assertNotIn("reused", ask(MEASURES))
        for measures in (bare, MEASURES):
            with self.subTest(measures=measures):
                self.assertTrue(ask(measures).get("reused"), "measured once, served after a restart")
        self.assertEqual(measured, [MEASURES])
        self.assertNotIn("reused", ask(newer), "another numpy: measured again")
        served = ask(bare)
        self.assertEqual((measured, served["checked"]["measured"]["report"]["by"]),
                         ([MEASURES, newer], newer["libraries"]))

    def test_a_reused_check_reads_none_of_its_documents_bytes(self) -> None:
        """A model document's kept result is looked for by the version its record says before its bytes are read:
        reused, they never are."""
        from cad.engine.previous import version
        from cad_server.engine.daemon import Daemon

        read: list[str] = []

        def document(ident: str) -> tuple[dict[str, Any], bytes]:
            read.append(ident)
            return {"document": "id", "name": "plate"}, b"bytes"

        def call(_routed: Any, _order: Any, answered: Any, _payload: bytes) -> None:
            answered({"done": {"checked": {"measured": {"report": {}}, "release": version(), "measures": MEASURES}}})

        fake = _fake({"id": {"version": "v1"}}, document, call)
        for _ in range(3):
            said: list[dict[str, Any]] = []
            Daemon.check(fake, {"source": {"id": "id"}, "check": {"type": "model", "token": "t"}, "caller": version(),
                                "measures": MEASURES}, said.append)
            self.assertIn("checked", said[-1]["done"])
        self.assertEqual((read, fake.checks.status()["reused"]), (["id"], 2), "read once, by the one check measured")

    def test_an_unwritable_cache_folder_is_tried_again_after_a_write_there_and_a_cache_files_removal_takes_its_checks(
            self) -> None:
        """A cache folder that takes no mark keeps nothing and is not tried, nor walked, again until it has taken a
        write since (the engine's cache file written, ``cache.WRITTEN``; the base made again) or the cache folder is
        another -- tried by the next result kept, never by a read; a document's cache file found unreadable takes its
        folder, and the results the disk index held there, with it (``cache.Cache.remove``)."""
        from cad_server.engine import cache
        from cad_server.engine.checks import Checks, Disk
        from cad_server.engine.registry import Folder, Registry

        root = Path(tempfile.mkdtemp(prefix="engine-dfm-sealed-"))
        self.addCleanup(shutil.rmtree, root, True)
        read: list[str] = []
        sealed = {"on": True}

        class Sealed(Folder):
            def write(self, inside: str, data: bytes, mode: int | None = None) -> Path:
                if sealed["on"]:
                    raise PermissionError(inside)
                return super().write(inside, data, mode)

            def read(self, inside: str) -> bytes | None:
                read.append(inside)
                return super().read(inside)

        a = str(uuid.uuid4())
        held: dict[str, Any] = {"folder": Sealed(root / "sealed")}
        store = Disk(lambda: held["folder"])
        for _ in range(3):
            store.keep(a, "r", "cnc", {"x": 1})
        self.assertEqual((read, store.status().get("unwritable")), (["documents/.checks-index"], True))
        store.writable()  # a write there succeeded: the next result kept tries the mark again, still refused
        self.assertIsNone(store.get(a, "r", "cnc"), "a read tries nothing")
        for _ in range(2):
            store.keep(a, "r", "cnc", {"x": 1})
        self.assertEqual((read, store.status().get("unwritable")), (["documents/.checks-index"] * 2, True))
        sealed["on"] = False
        store.keep(a, "r", "cnc", {"x": 1})
        self.assertEqual(len(read), 2, "writable now, but no write there since: not tried")
        store.writable()
        store.keep(a, "r", "cnc", {"x": 1})
        self.assertEqual((store.get(a, "r", "cnc"), "unwritable" in store.status()), (({"x": 1}, {}), False))
        sealed["on"] = True
        held["folder"] = Sealed(root / "other")
        store.keep(a, "r", "cnc", {"x": 1})
        self.assertTrue(store.status().get("unwritable"))
        held["folder"] = Folder(root / "open")  # another cache folder: tried again
        store.keep(a, "r", "cnc", {"x": 1})
        self.assertEqual((store.get(a, "r", "cnc"), "unwritable" in store.status()), (({"x": 1}, {}), False))
        # The engine's cache file written tells the store (``cache.WRITTEN``), as a daemon registers it.
        told: list[bool] = []
        cache.WRITTEN.append(lambda: told.append(True))
        self.addCleanup(cache.WRITTEN.pop)
        written = Registry(root / "state-w", cache=root / "cache-w")
        written.put({"id": a, "kind": "model", "root": str(root), "home": "m.py", "entry": "m", "revision": "r1"})
        cache.Cache(SimpleNamespace(registry=lambda: written))._write(a, "r1", b"xbf")
        self.assertEqual(told, [True])

        registry = Registry(root / "state", cache=root / "cache")
        checks = Checks(folder=lambda: registry)
        cache.DROPPED.append(checks.dropped)
        self.addCleanup(cache.DROPPED.remove, checks.dropped)
        checks.keep(f"model:{a}", "v", "cnc", {"x": 1}, (a, "r"))
        self.assertEqual(checks.status()["disk"]["held"], 1)
        cache.Cache(SimpleNamespace(registry=lambda: registry)).remove(a)
        self.assertEqual((checks.status()["disk"]["held"], checks.status()["held"]), (0, 1),
                         "gone from the disk's index with its folder; memory keeps it")
        self.assertEqual(registry.cache.names("documents"), [".checks-index"])

    def test_a_check_s_record_is_cleared_whatever_its_store_raises(self) -> None:
        """Its lookup inside the check's own ``try``: a store that raises leaves no check running, and every caller
        attached to it answered."""
        from cad.engine.previous import version
        from cad_server.engine.daemon import Daemon

        fake = _fake({"id": {"version": "v1"}}, lambda _ident: ({"document": "id", "name": "plate"}, b""),
                     lambda *_args: None)
        fake.checks.get = mock.Mock(side_effect=OSError("disk gone"))
        with self.assertRaises(OSError):
            Daemon.check(fake, {"source": {"id": "id"}, "check": {"type": "model", "token": "t"}, "caller": version(),
                                "measures": MEASURES}, lambda _message: None)
        self.assertEqual((fake.asked, fake.running), ({}, {}))


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

    def test_a_result_is_kept_under_no_version_a_build_landed_on(self) -> None:
        """A build landing between the version read and the document's bytes: the bytes are the new version's and
        the version read the old one's, so the result is answered and kept under neither."""
        from cad.engine.previous import version
        from cad_server.engine.daemon import Daemon

        records = {"id": {"version": "v1"}}

        def document(_ident: str) -> tuple[dict[str, Any], bytes]:
            records["id"]["version"] = "v2"
            return {"document": "id", "name": "plate"}, b"bytes"

        def call(_routed: Any, _order: Any, answered: Any, _payload: bytes) -> None:
            answered({"done": {"checked": {"measured": {"report": {}}, "release": version(), "measures": MEASURES}}})

        fake = _fake(records, document, call)
        said: list[dict[str, Any]] = []
        Daemon.check(fake, {"source": {"id": "id"}, "check": {"type": "model", "token": "t"}, "caller": version(),
                            "measures": MEASURES}, said.append)
        self.assertIn("checked", said[-1]["done"])
        self.assertEqual((fake.checks.status()["measured"], fake.checks.status()["held"]), (1, 0))
        self.assertEqual((fake.asked, fake.running), ({}, {}))

    def test_a_worker_retired_as_its_check_was_leased_is_checked_from_the_bytes_held(self) -> None:
        """Its worker gone between the document read and the lease (refused as not held): the document is read
        once more -- the server or the cache holds it now -- and checked in a checks process, never said not found."""
        from cad.engine.previous import version
        from cad.engine.serve import NotHeld
        from cad_server.engine.daemon import Daemon, refused

        records = {"id": {"version": "v1", "revision": "k1"}}
        held = iter([({"script": "/m/parts.py", "function": "plate", "held": "id", "via": "/m/parts.py"}, b""),
                     ({"document": "id", "name": "plate"}, b"bytes")])
        asked: list[tuple[dict[str, Any], bytes]] = []

        def call(routed: Any, _order: Any, answered: Any, payload: bytes) -> None:
            asked.append((routed["source"], payload))
            if "script" in routed["source"]:
                answered(refused(NotHeld("plate (id) is not held", "unsaved", "python parts.py")))
            else:
                answered({"done": {"checked": {"measured": {"report": {}}, "release": version(), "read": True,
                                               "measures": MEASURES}}})

        fake = _fake(records, lambda _ident: next(held), call)
        said: list[dict[str, Any]] = []
        Daemon.check(fake, {"source": {"id": "id"}, "check": {"type": "model", "token": "t"}, "caller": version(),
                            "measures": MEASURES}, said.append)
        self.assertEqual([source for source, _payload in asked][1], {"document": "id", "name": "plate", "version": "v1"})
        self.assertEqual(asked[1][1], b"bytes")
        self.assertEqual([message for message in said if "failed" in message], [], "no refusal said")
        self.assertIn("checked", said[-1]["done"])
        self.assertEqual(fake.checks.status()["held"], 1)

    def test_a_check_routed_on_from_a_script_s_worker_never_stops_that_worker(self) -> None:
        """Its worker retired as it was leased, the check goes on to the checks processes: while it waits for a
        slot, its callers gone, it is no reaping's victim -- the script's worker it was first asked of, a person's
        warm worker, is not its process -- and status says it waits. Killed between its lease and its request, it
        is answered reaped, no fresh checks process started for it."""
        from cad.engine.previous import version
        from cad.engine.serve import NotHeld
        from cad_server.engine.daemon import CHECKS, REAPED, Daemon, _Asked, refused
        from cad_server.engine.supervisor import Gone

        killed: list[str] = []
        leased: list[str] = []

        def process(key: str, request: Any) -> Any:
            return SimpleNamespace(key=key, environment={}, popen=SimpleNamespace(kill=lambda: killed.append(key)),
                                   kill=lambda: None, request=request, progress=None)

        def not_held(_order: Any, _send: Any, _payload: bytes) -> dict[str, Any]:
            return refused(NotHeld("plate (id) is not held", "unsaved", "python parts.py"))

        script = process("/m/parts.py", not_held)
        gone = threading.Event()
        rows: list[dict[str, Any]] = []

        def take(_document: str, _gave_up: Any, _waiting: Any, _reap: Any, _defer: Any) -> str:
            gone.set()  # its caller hangs up while it waits; another check waits with its caller there
            other = _Asked("other", CHECKS, None, gone=threading.Event())
            other.waiting = True
            fake.asked["other"] = other
            rows.extend(Daemon.running_checks(fake))
            Daemon._reap(fake, other)
            fake.asked.pop("other")
            return "checks"

        def killed_in_lease(_order: Any, _send: Any, _payload: bytes) -> dict[str, Any]:
            asked = fake.asked["t"]
            asked.reaped = True
            asked.stopped.set()  # killed by a reaping as it was leased: its pipe is broken
            raise Gone("the checks process's pipe broke")

        def lease(key: str, *_args: Any, **_kwargs: Any) -> Any:
            leased.append(key)
            return script if key != CHECKS else process(CHECKS, killed_in_lease)

        records = {"id": {"version": "v1", "revision": "k1"}}
        held = iter([({"script": "/m/parts.py", "function": "plate", "held": "id", "via": "/m/parts.py"}, b""),
                     ({"document": "id", "name": "plate"}, b"bytes")])
        fake = _fake(records, lambda _ident: next(held), None)
        fake.supervisor = SimpleNamespace(live=lambda _service, _key, _python_key: script)
        fake.pool = SimpleNamespace(take=take, give=lambda _slot: None)
        fake.busy, fake.busy_lock = 0, threading.Lock()
        fake.lease, fake.release, fake.environment = lease, lambda _worker: None, lambda: {}
        fake._behind_check, fake.touch = (lambda *_args: None), (lambda: None)
        fake._learn = lambda *_args: False
        fake._built = lambda *_args, **_kwargs: None
        for name in ("_call", "_kill", "_reap", "_defers"):
            setattr(fake, name, getattr(Daemon, name).__get__(fake))
        said: list[dict[str, Any]] = []
        Daemon.check(fake, {"source": {"id": "id"}, "check": {"type": "model", "token": "t"}, "caller": version(),
                            "measures": MEASURES}, said.append, gone)
        self.assertEqual(killed, [], "the script's worker it was first asked of is never killed through it")
        mine = [row for row in rows if row["route"] == "checks" and row.get("document") == "id"]
        self.assertEqual([(row["where"], row["waiting"]) for row in mine], [(None, True)], "it waits, of no process")
        self.assertEqual(leased, ["/m/parts.py", CHECKS], "no fresh checks process after the kill")
        self.assertEqual(said[-1], {"failed": REAPED, "reaped": True})
        self.assertEqual((fake.asked, fake.running), ({}, {}))

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

    def test_a_build_says_it_is_asking_before_the_worker_answers(self) -> None:
        from cad_server.engine.daemon import Daemon, _Asked

        asked = _Asked("t", "/m/parts.py", None)
        asked.worker = SimpleNamespace(label="/m/parts.py")
        order: list[str] = []

        def stop(check: Any) -> bool:
            order.append("stop")
            check.finished.set()
            return True

        fake = SimpleNamespace(asked={"t": asked}, asked_lock=threading.Lock(), _stop=stop)
        Daemon._cancel_check(fake, "/m/parts.py", None, lambda message: order.append(message["log"]))
        self.assertEqual(order[1], "stop")
        self.assertIn("asking the manufacturing check", order[0])

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
            environment={}, python="/old/python")), lease=lambda *_args, **_kwargs: worker, release=released.append,
            wholes={}, wholes_lock=threading.Lock())
        spec = {"script": "/m/parts.py", "function": "plate", "via": "/m/parts.py", "python_key": "/old\0" + "0.10.0"}
        for _ in range(2):
            source, data = Daemon._whole(fake, "id", spec)
            self.assertEqual((source, data), ({"document": "id", "name": "plate"}, b"XBF!"))
        self.assertEqual((len(asked), released), (1, [worker]), "asked once for its version")
        self.assertEqual((asked[0]["op"], asked[0]["whole"]), ("result", True), "protocol 1's request, nothing new")
        models.records["id"]["version"] = "w"
        Daemon._whole(fake, "id", spec)
        self.assertEqual(len(asked), 2, "another version is asked for")

    def test_the_pool_runs_a_check_per_slot_and_one_past_it_waits_saying_so(self) -> None:
        from cad_server.engine.checks import Pool
        from cad_server.engine.supervisor import Withdrawn

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

    def test_the_pool_counts_a_process_it_has_not_heard_from_and_those_starting(self) -> None:
        """No checks process has said its memory: the last one's, else the standby's, else the smallest worker's
        stands for it, and each slot being started counts, so a burst of checks never starts past the cap."""
        from cad_server.engine.checks import Pool
        from cad_server.engine.supervisor import Withdrawn

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

    def test_an_abandoned_check_gives_its_slot_to_one_someone_waits_for(self) -> None:
        """Only a check whose callers have all gone, one for each waiter whose caller is there, the oldest first;
        never one with a caller, nor for a waiter no one waits for."""
        from cad_server.engine.daemon import CHECKS, Daemon, _Asked

        def asked(token: str, *callers: bool, running: bool = True) -> _Asked:
            found = _Asked(token, CHECKS, None, gone=None)
            found.callers = [threading.Event() for _ in callers]
            for event, there in zip(found.callers, callers):
                if not there:
                    event.set()
            found.worker = SimpleNamespace(key="checks") if running else None
            return found

        stopped: list[str] = []
        fake = SimpleNamespace(asked={}, running={}, asked_lock=threading.Lock(),
                               _kill=lambda found: stopped.extend(each.token for each in found))
        held, gone, waiter, idle = asked("held", True, False), asked("gone", False, False), asked("w", True, running=False), \
            asked("idle", False, running=False)
        older = asked("older", False)
        older.began = gone.began + 1  # asked after it: the oldest goes first
        waiter.waiting = idle.waiting = True
        fake.asked = {found.token: found for found in (held, gone, older, waiter, idle)}
        gone.same, older.same = ("model:a", "v", "k"), ("model:b", "v", "k")
        fake.running = {gone.same: gone, older.same: older}
        Daemon._reap(fake, idle)
        self.assertEqual(stopped, [], "a waiter no one waits for reaps nothing")
        Daemon._reap(fake, waiter)
        self.assertEqual(stopped, ["gone"], "one for the one waiter, and never the check a caller is attached to")
        self.assertNotIn(gone.same, fake.running, "out of running as it is reaped: the same check asked now runs anew")
        gone.answered = True  # answered as its process is killed, its slot not yet given back
        Daemon._reap(fake, waiter)
        self.assertEqual(stopped, ["gone"], "counted until its slot is free again: no second for the one waiter")
        gone.freed = True
        Daemon._reap(fake, waiter)
        self.assertEqual(stopped, ["gone", "older"])

    def test_a_check_cut_short_says_why(self) -> None:
        """A stop under a model's worker's check says the engine stopped (``api.Stopped``), as one under a checks
        process's does; a check reaped for another's slot, to any caller still reading, says that."""
        from cad.engine.previous import version
        from cad_server.engine.daemon import REAPED, STOPPED, Daemon

        def stopped(_routed: Any, _order: Any, answered: Any, _payload: bytes) -> None:
            fake.stopping.set()
            answered({"failed": "the worker for parts.py exited (-15) during a manufacturing check"})

        held = {"script": "/m/parts.py", "function": "plate", "held": "id", "via": "/m/parts.py"}
        fake = _fake({"id": {"version": "v1"}}, lambda _ident: (dict(held), b""), stopped)
        said: list[dict[str, Any]] = []
        Daemon.check(fake, {"source": {"id": "id"}, "check": {"type": "model", "token": "t"}, "caller": version(),
                            "measures": MEASURES}, said.append)
        self.assertEqual(said[-1], {"failed": STOPPED, "stopped": True})

        def reaped(_routed: Any, order: Any, answered: Any, _payload: bytes) -> None:
            fake.asked[order["check"]["token"]].reaped = True
            answered({"failed": "the checks process exited (-9) during a manufacturing check"})

        fake = _fake({"id": {"version": "v1"}}, lambda _ident: ({"document": "id", "name": "plate"}, b"x"), reaped)
        said = []
        Daemon.check(fake, {"source": {"id": "id"}, "check": {"type": "model", "token": "t"}, "caller": version(),
                            "measures": MEASURES}, said.append)
        self.assertEqual(said[-1], {"failed": REAPED, "reaped": True})

    def test_what_measures_is_each_processs_own_and_a_checks_process_of_a_base_gone_is_retired(self) -> None:
        """Said by each process, kept with it and gone with it: a fresh worker, and a fresh checks process, says
        for itself. The base's is the latest checks process's started since the base was made; one unlike it (of
        a base made before) is retired, never a model's worker; and a base made again retires every checks process
        and is unknown until a fresh one says."""
        from cad_server.engine import daemon
        from cad_server.engine.daemon import CHECKS, Daemon

        retired: list[tuple[str, str]] = []
        workers: dict[str, Any] = {}
        checking: list[Any] = []
        supervisor = SimpleNamespace(retire=lambda process, why: retired.append((process.key, why)),
                                     processes=lambda _service: list(checking), stand=lambda *_args: None,
                                     live=lambda _service, key, _python_key: workers.get(key))
        writable: list[bool] = []
        fake = SimpleNamespace(asked_lock=threading.Lock(), base_since=100.0, base_measures=None,
                               supervisor=supervisor, stopping=threading.Event(), environment=lambda: {},
                               checks=SimpleNamespace(writable=lambda: writable.append(True)))
        fake._base_measures = Daemon._base_measures.__get__(fake)

        def answer(measures: dict[str, Any]) -> dict[str, Any]:
            return {"done": {"checked": {"measures": measures}}}

        def process(key: str, started: float) -> Any:
            return SimpleNamespace(key=key, started=started, state={}, retired=False, alive=lambda: True)

        newer = {**MEASURES, "libraries": {**MEASURES["libraries"], "numpy": "2.1.0"}}
        with mock.patch.object(daemon._places, "kernel", return_value={"own": False}):
            self.assertIsNone(fake._base_measures(), "nothing said yet: a fresh process decides")
            fresh, old = process("checks", 150.0), process("checks-2", 50.0)
            self.assertFalse(Daemon._learn(fake, CHECKS, fresh, answer(MEASURES)))
            self.assertEqual((fake.base_measures, fresh.state["measures"]), (MEASURES, MEASURES))
            self.assertTrue(Daemon._learn(fake, CHECKS, old, answer(newer)), "started before the base was made")
            self.assertEqual((retired, fake.base_measures), ([("checks-2", "base")], MEASURES))
            worker = workers["/m.py"] = process("/m.py", 0.0)
            self.assertFalse(Daemon._learn(fake, "/m.py", worker, answer(newer)), "a model's worker is never retired")
            self.assertEqual(Daemon._worker_measures(fake, "/m.py", None), newer)
            worker.retired = True
            self.assertIsNone(Daemon._worker_measures(fake, "/m.py", None), "gone with its process")
            checking.append(fresh)
            Daemon.made_base(fake)
            self.assertEqual((retired[-1], fake.base_measures), (("checks", "base"), None), "made again: unknown")
            self.assertEqual(writable, [True], "and an unwritable cache folder tried again by the next result kept")
        with mock.patch.object(daemon._places, "kernel", return_value={"own": True}):
            from cad.engine.contract import measure

            self.assertEqual(fake._base_measures(), measure(), "the server's own, read now")

    def test_a_drain_kills_the_checks_processes_measuring_all_at_once_and_a_cancel_waits_for_no_answer(self) -> None:
        from cad_server.engine.daemon import CHECKS, Daemon, _Asked

        order: list[tuple[str, str]] = []

        def process(name: str) -> Any:
            return SimpleNamespace(popen=SimpleNamespace(kill=lambda: order.append(("signalled", name))),
                                   kill=lambda: order.append(("waited", name)))

        first, second, queued, model = (_Asked(token, key, None) for token, key in
                                        (("a", CHECKS), ("b", CHECKS), ("c", CHECKS), ("d", "/m.py")))
        first.worker, second.worker, model.worker = process("a"), process("b"), process("d")
        queued.worker, queued.waiting = process("c"), True  # waiting for a slot: what it was leased before is not its own
        fake = SimpleNamespace(asked={found.token: found for found in (first, second, queued, model)},
                               asked_lock=threading.Lock())
        fake._kill = Daemon._kill.__get__(fake)
        Daemon._halt_checks(fake)
        self.assertEqual(order, [("signalled", "a"), ("signalled", "b"), ("waited", "a"), ("waited", "b")])
        self.assertTrue(all(found.halted and found.stopped.is_set() for found in (first, second, queued)))
        self.assertFalse(model.halted or model.stopped.is_set(), "a model's worker's check is never killed")
        waited: list[float] = []
        model.worker = SimpleNamespace(question=lambda _message, timeout: waited.append(timeout))
        Daemon._stop(fake, model)
        self.assertEqual((waited, model.stopped.is_set()), ([0], True), "told, its answer not waited for")

    def test_a_waiter_whose_callers_have_gone_leaves_a_free_slot_to_one_someone_waits_for(self) -> None:
        from cad_server.engine.checks import Pool
        from cad_server.engine.daemon import CHECKS, Daemon, _Asked
        from cad_server.engine.supervisor import Withdrawn

        pool = Pool(SimpleNamespace(processes=lambda _service: [], pressed=lambda: False, memory=lambda: None,
                                    resident=lambda: 0.0), 1)
        with self.assertRaises(Withdrawn):
            pool.take("file:a", gave_up=lambda: True, defer=lambda: True)
        self.assertEqual(pool.busy, {}, "deferring, it took no slot")
        self.assertEqual(pool.take("file:a", gave_up=lambda: True, defer=lambda: False), "checks")
        gone, there = _Asked("g", CHECKS, None, gone=threading.Event()), _Asked("t", CHECKS, None, gone=threading.Event())
        gone.callers[0].set()
        gone.waiting = True
        fake = SimpleNamespace(asked={"g": gone}, asked_lock=threading.Lock())
        self.assertFalse(Daemon._defers(fake, gone), "no one else waits: it takes the slot, and keeps its result")
        there.waiting = True
        fake.asked["t"] = there
        self.assertTrue(Daemon._defers(fake, gone))
        self.assertFalse(Daemon._defers(fake, there))

    def test_a_file_is_one_key_by_any_of_its_names(self) -> None:
        from cad_server.engine.daemon import _file_key
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

    def test_a_fresh_worker_refuses_a_document_it_does_not_hold_as_not_held(self) -> None:
        """A retired worker's place taken by a fresh one, which holds nothing: its refusal is the daemon's own
        not-held refusal, so the check reads the document again rather than failing."""
        from cad.engine import contract, worker
        from cad.engine.serve import NotHeld
        from cad_server.engine.daemon import _not_held

        request = {"source": {"held": "id", "script": "/nowhere/parts.py", "function": "plate"},
                   "check": {"type": "model", "token": "t", "measures": contract.measuring()}}
        with self.assertRaises(NotHeld) as raised:
            worker._check(request)
        self.assertTrue(_not_held({"id": 1, **worker.failure(raised.exception)}))
        unlike = {**request, "check": {**request["check"], "measures": {**contract.measuring(), "code": "other"}}}
        self.assertNotIn("checked", worker._check(unlike), "another code's caller: nothing measured")

    def test_what_a_check_read_is_bounded_by_bytes_and_shed_over_the_cap(self) -> None:
        from cad.build123d import _dfm_brep
        from cad.engine import worker

        memo = {name: (name, None, size) for name, size in (("a", 10), ("b", worker.KEPT_BYTES - 5), ("c", 10))}
        worker._bounded(memo, 4, lambda row: row[2])
        self.assertEqual(list(memo), ["c"], "held to its bytes, the least recently used going first")
        worker._FILES["x"] = ("d", None, 1)
        worker._DOCUMENTS["y"] = ("v", None, 1)
        _dfm_brep._PRISTINE["z"], _dfm_brep._PRISTINE_BYTES["z"] = {}, {}
        with mock.patch.object(worker, "resident_mb", return_value=5000.0):
            worker.resident_after_build(1000.0)
        self.assertEqual((worker._FILES, worker._DOCUMENTS, _dfm_brep._PRISTINE), ({}, {}, {}),
                         "dropped where the process is over its cap")

    def test_status_says_each_check_running_and_whether_its_caller_waits(self) -> None:
        from cad_server.engine.cli import status_text

        text = status_text({"pid": 1, "workers": [], "cap": 4, "checks": {"running": [
            {"type": "step", "process": "printing", "file": "/p/box.step", "route": "checks", "where": "checks-2",
             "seconds": 21.0, "attached": False, "waiting": False},
            {"type": "model", "process": "cnc", "document": "abc", "route": "worker", "where": None,
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


class WorkerTest(unittest.TestCase):
    """What a check's worker does beside it: a build of its script cancels a check running there or waiting
    for it, a cancel landing as a check ends hangs nothing, and a worker killed in one says so. A check waits
    at its seam (``CAD_ENGINE_CHECK_WAIT``, read at each check from the environment it runs in: a worker's,
    the build's it adopted; a checks process's, the daemon's) until the test lets it go."""

    def waiting(self, env: dict[str, str] | None = None) -> tuple[Fixture, Path]:
        hold = Path(tempfile.mkdtemp(prefix="engine-dfm-hold-")) / "go"
        self.addCleanup(shutil.rmtree, hold.parent, True)
        self.addCleanup(lambda: hold.write_text("", encoding="utf-8"))  # whatever happens, no check waits on
        return Fixture(self, MODELS, {"CAD_ENGINE_CHECK_WAIT": str(hold), **(env or {})}), hold

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

    def caller(self, call: str, env: dict[str, str], reached: Path) -> tuple[subprocess.Popen, int]:
        """A process that calls a check, once its check says it is measuring: the process and the pid measuring."""
        reached.unlink(missing_ok=True)
        process = subprocess.Popen([sys.executable, "-c", f"import cad; {call}"], env=env,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(process.wait)
        self.addCleanup(process.kill)
        _until(self, lambda: reached.exists() and reached.read_text(encoding="utf-8"), "the check reached its seam")
        return process, int(reached.read_text(encoding="utf-8"))

    def test_a_check_outlives_its_caller_and_the_next_call_reuses_its_result(self) -> None:
        """Its caller killed (a shell's time limit), a model's check runs to its end and keeps its result: the same
        call again measures nothing. A file's check waiting behind another says so (a pool of one checks process),
        and `cad status` lists the one running; once that one's caller is gone, its process is killed for the one
        waiting, which a fresh one measures, and it keeps nothing."""
        import build123d as bd

        import cad
        from cad.engine import api

        api.stop()  # no checks process stands: the next starts with the seam of the engine this file's builds start
        self.addCleanup(api.stop)  # the seam goes with its engine's processes
        fixture, hold = self.waiting({"CAD_ENGINE_CHECKS": "1"})
        reached = Path(f"{hold}.reached")
        process, worker = self.caller(f"cad.model.dfm({fixture.ids[0]!r}, process='cnc')", fixture.env, reached)
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
        self.assertIn(worker, [row["pid"] for row in api.status()["workers"] if row["alive"]], "the warm worker lives on")

        hold.unlink()
        step = fixture.folder / "part.step"
        bd.export_step(bd.Box(30, 20, 6), str(step))
        process, checks = self.caller(f"cad.step.dfm({str(step)!r}, process='printing')", fixture.env, reached)
        self.assertEqual(_busy(), [checks])
        (row,) = _counts()["running"]
        self.assertEqual((row["file"], row["process"], row["route"], row["where"], row["attached"]),
                         (str(step), "printing", "checks", "checks", True))
        behind = subprocess.Popen([sys.executable, "-c", f"import cad; cad.step.dfm({str(step)!r}, process='sheet')"],
                                  env=fixture.env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
        self.addCleanup(behind.stderr.close)  # last: once it is gone, its reader is done
        self.addCleanup(behind.wait)
        self.addCleanup(behind.kill)
        said: list[str] = []
        reader = threading.Thread(target=lambda: said.extend(behind.stderr), daemon=True)  # its stderr as it comes
        reader.start()
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

        self.assertIn("check    sheet of part.step in checks", status_text(api.status()))
        hold.write_text("", encoding="utf-8")
        self.assertEqual(behind.wait(JOIN_SECONDS), 0, said)
        reader.join(JOIN_SECONDS)
        _until(self, lambda: _counts()["asked"] == 0, "both checks end")
        self.assertEqual(_counts()["measured"], before["measured"] + 1, "the abandoned one measured nothing")
        self.assertNotIn(checks, [row["pid"] for row in _counts()["pool"]["processes"]],
                         "its process killed at once, and a fresh one measured the one waiting")
        cad.step.dfm(step, process="printing")
        self.assertEqual(_counts()["measured"], before["measured"] + 2, "nothing of it was kept")

    def test_an_update_s_drain_waits_for_no_checks_process_and_its_checks_say_stopped(self) -> None:
        """A drain for an update with a check running in the checks process and another waiting for it: neither is
        waited for, and both callers are told the engine stopped (``api.Stopped``: run the check again)."""
        import build123d as bd

        from cad.engine import api, client

        api.stop()
        self.addCleanup(api.stop)
        fixture, hold = self.waiting({"CAD_ENGINE_CHECKS": "1"})
        reached = Path(f"{hold}.reached")
        reached.unlink(missing_ok=True)
        callers = []
        for height in (6, 7):
            step = fixture.folder / f"part{height}.step"
            bd.export_step(bd.Box(30, 20, height), str(step))
            code = (f"import cad\nfrom cad.engine import api\ntry:\n    cad.step.dfm({str(step)!r}, process='printing')\n"
                    "except api.Stopped as error:\n    print('stopped:', error)")
            callers.append(subprocess.Popen([sys.executable, "-c", code], env=fixture.env, stdout=subprocess.PIPE,
                                            stderr=subprocess.DEVNULL, text=True))
            self.addCleanup(callers[-1].stdout.close)
            self.addCleanup(callers[-1].wait)
            self.addCleanup(callers[-1].kill)
            if height == 6:
                _until(self, reached.exists, "the first check runs")
        _until(self, lambda: _counts()["asked"] == 2, "the second waits for the checks process")
        self.assertIsNotNone(client.request({"op": "stop", "drain": True}, start=False))
        self.assertTrue(client.wait_gone(), "the engine drained and stopped with the checks under way")
        for caller in callers:
            out = caller.communicate(timeout=JOIN_SECONDS)[0]
            self.assertIn("stopped: the CAD server stopped while it measured the manufacturing check", out)
        self.assertFalse(hold.exists(), "neither check was let go")

    def test_different_checks_run_at_once_in_the_pool_and_one_past_it_waits_saying_so(self) -> None:
        """Two files' checks measured at once, in two checks processes; a third, the pool full, says it waits
        and runs once one is done."""
        import build123d as bd

        from cad.engine import api

        api.stop()  # an engine with a pool of two and the seam
        self.addCleanup(api.stop)
        fixture, hold = self.waiting({"CAD_ENGINE_CHECKS": "2"})
        steps = []
        for height in (6, 7, 8):
            steps.append(fixture.folder / f"part{height}.step")
            bd.export_step(bd.Box(30, 20, height), str(steps[-1]))
        before = _counts()["measured"]
        callers = []
        for step in steps:
            callers.append(subprocess.Popen([sys.executable, "-c", f"import cad; cad.step.dfm({str(step)!r}, process='printing')"],
                                            env=fixture.env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True))
            self.addCleanup(callers[-1].stderr.close)
            self.addCleanup(callers[-1].wait)
            self.addCleanup(callers[-1].kill)
            if len(callers) == 2:
                _until(self, lambda: len(_busy()) == 2, "two checks measure at once")
        self.assertEqual(len(set(_busy())), 2, "in two processes")
        said: list[str] = []
        reader = threading.Thread(target=lambda: said.extend(callers[2].stderr), daemon=True)
        reader.start()
        _until(self, lambda: any("the 2 checks processes are all busy" in line for line in said), "the third waits")
        self.assertIn("waiting for another manufacturing check", "".join(said))
        hold.write_text("", encoding="utf-8")
        for caller in callers[:2]:
            self.assertEqual(caller.wait(JOIN_SECONDS), 0, caller.stderr.read())
        self.assertEqual(callers[2].wait(JOIN_SECONDS), 0, said)
        self.assertEqual(_counts()["measured"], before + 3)

    def test_a_caller_of_other_code_or_libraries_is_measured_by_no_process_here(self) -> None:
        """A library whose code or measuring libraries are not the engine's (a checkout's edited copy at the same
        release, a base made again with a newer build123d) is measured by no process here and served nothing the
        engine kept: it measures the file itself; the same code is served the result kept."""
        import build123d as bd

        import cad
        from cad.engine import contract

        folder = Path(tempfile.mkdtemp(prefix="engine-dfm-unlike-"))
        self.addCleanup(shutil.rmtree, folder, True)
        step = folder / "box.step"
        bd.export_step(bd.Box(24, 18, 7), str(step))
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
        fixture, hold = self.waiting()
        before = _counts()
        first, _pid = self.started(fixture.ids[0], hold, "7")
        code = (f"import cad, dataclasses, json; found = cad.model.dfm({fixture.ids[0]!r}, process='cnc', tools='7'); "
                "print(json.dumps(dataclasses.asdict(found), default=str))")
        second = subprocess.Popen([sys.executable, "-c", code], env=fixture.env, stdout=subprocess.PIPE,
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
        self.assertIn("checks", [row.get("process") for row in api.status()["retired"]], "listed as what it is")

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
