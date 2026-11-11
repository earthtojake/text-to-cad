"""A manufacturing check's result (``cad <type> dfm``, ``cad.<type>.dfm``) as the engine's checks processes
measure it (``checks_runner.Runner``, ``worker._check``): a STEP's and an xbf's from its file, a model's from
the bytes the engine holds of it. It equals the one the same document gets read from a file in a process of its
own, for every process, with no process given and ranking candidates; the same check of an unchanged document
is the engine's kept result (``checks``), measuring nothing, in memory and on disk across a restart; an edit,
other options or another file's bytes -- even ones of the same size and time -- are measured again. On an
engine, a state and a cache folder of this file's own."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest import mock

from tests.python.support import engine_daemon
from tests.python.support.manufacturing_fixtures import (DECLARED, MEASURES, MODELS, SRC, Fixture, _counts,
                                                         _plain, _today, _until)

PROCESSES = ("cnc", "sheet", "molding", "printing")


def setUpModule() -> None:
    engine_daemon.isolate(unittest.addModuleCleanup)


def _restarted() -> dict[str, int]:
    """The engine stopped and started again: its counts as it starts, which a test's own are counted from."""
    from cad.engine import api, client

    api.stop()
    return client.request({"op": "status"})["checks"]


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
        # A file's reader is what differs from a model's, not its process (every process was compared above):
        # each file type by two processes, each process by one file.
        for document_type, path, processes in (("step", step, ("cnc", "molding")), ("xbf", xbf, ("sheet", "printing"))):
            for process in processes:
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
        # The runner answers a check's caller and then lets the check go: asked again before it has, the same
        # check is joined, not read from what was kept. So the first is awaited gone before the second is asked.
        _until(self, lambda: _counts()["asked"] == 0, "the first check is let go")
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


if __name__ == "__main__":
    unittest.main()
