"""What a model imports: ``read_step`` and ``read_xbf`` copy a file's geometry with its names,
colours and materials (an xbf's mechanism stays behind); a STEP is parsed in a reader process
of the build's, so the parse's working memory never stays in the worker. ``read_mesh`` reads an
STL as data, keyed by its bytes, as build123d's importers are; a file read past the engine's
readers (OCCT's, driven directly) runs its body on every build, and the build names the call."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock

from cadgen.engine import build as engine_build
from cadgen.engine import cli
from cadgen.engine import document

KIT = """
import build123d as bd
from cadgen.ap242 import mechanism_state
from cadgen.engine import materials, paint, step, xbf


@xbf("XBF/kit.xbf")
@step("kit.step")
def kit():
    base = bd.Box(10, 10, 5)
    base.label, base.color, base.material = "base", bd.Color(0.2, 0.4, 0.6), materials.aluminium
    peg = bd.Pos(20, 0, 0) * bd.Cylinder(3, 8)
    peg.label, peg.color = "peg", bd.Color(0.9, 0.1, 0.1)
    other = peg.moved(bd.Location((0, 20, 0)))
    other.label = "other"
    return bd.Compound(children=[base, peg, other], label="kit")


@xbf("XBF/hinge.xbf")
def hinge():
    base, arm = bd.Box(100, 60, 20), bd.Box(120, 20, 10, align=(bd.Align.MIN, bd.Align.CENTER, bd.Align.MIN))
    base.label, arm.label = "base", "arm"
    paint(base, base.faces().sort_by(bd.Axis.Z)[-1], "#1ae61a")
    bd.RevoluteJoint("elbow", base, axis=bd.Axis((40, 0, 20), (0, 1, 0)), angular_range=(-10, 120))
    bd.RigidJoint("mount", arm)
    base.joints["elbow"].connect_to(arm.joints["mount"], angle=30)
    return mechanism_state(bd.Compound(children=[base, arm], label="hinge"), "raised", elbow=90)
"""

USE = """
from pathlib import Path

from cadgen.engine import read_step, read_xbf, xbf

HERE = Path(__file__).resolve().parent


@xbf("XBF/from_step.xbf")
def from_step():
    return read_step(HERE / "kit.step")


@xbf("XBF/from_xbf.xbf")
def from_xbf():
    return read_xbf(HERE / "XBF/converted.xbf")


@xbf("XBF/twice.xbf")
def twice():
    first = read_step(HERE / "kit.step")
    second = read_step(HERE / "kit.step").moved(__import__("build123d").Location((0, 0, 50)))
    third = read_step(HERE / "again.step")
    return __import__("build123d").Compound(children=[first, second, third], label="twice")


@xbf("XBF/hinge_copy.xbf")
def hinge_copy():
    return read_xbf(HERE / "XBF/hinge.xbf")
"""


class ImportTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from cadgen.engine import api

        cls.folder = Path(tempfile.mkdtemp(prefix="engine-imports-")).resolve()
        (cls.folder / "kit.py").write_text(textwrap.dedent(KIT), encoding="utf-8")
        (cls.folder / "use.py").write_text(textwrap.dedent(USE), encoding="utf-8")
        for report in engine_build.build(cls.folder / "kit.py", cwd=cls.folder):
            assert report["ok"], report
        shutil.copy(cls.folder / "kit.step", cls.folder / "again.step")
        api.export(cls.folder / "kit.step", cls.folder / "XBF/converted.xbf", daemon=False)

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.folder, ignore_errors=True)

    def built(self, name: str) -> dict:
        (report,) = engine_build.build(self.folder / "use.py", [name], cwd=self.folder)
        self.assertTrue(report["ok"], report)
        return document.Loaded(self.folder / f"XBF/{name}.xbf").structure()

    def test_read_xbf_of_a_converted_step_is_read_step_of_the_step(self) -> None:
        from_step, from_xbf = self.built("from_step"), self.built("from_xbf")
        for field in ("prototypes", "instances", "tree"):
            self.assertEqual(json.dumps(from_step[field], sort_keys=True), json.dumps(from_xbf[field], sort_keys=True),
                             field)
        # The same geometry (each part's key, above); names, colours and materials as the model made them.
        built = document.Loaded(self.folder / "XBF/kit.xbf").structure()
        self.assertEqual([(p["name"], p["color"], p["faceNames"]) for p in from_xbf["prototypes"]],
                         [(p["name"], p["color"], p["faceNames"]) for p in built["prototypes"]])
        self.assertEqual(from_xbf["prototypes"][0]["material"]["name"], built["prototypes"][0]["material"]["name"])
        self.assertEqual([i["path"].split("/")[-1] for i in from_xbf["instances"]], ["base", "peg", "other"])

    def test_read_xbf_copies_parts_and_paints_but_no_mechanism(self) -> None:
        copy = self.built("hinge_copy")
        hinge = document.Loaded(self.folder / "XBF/hinge.xbf").structure()
        self.assertIn("kinematics", hinge)
        self.assertNotIn("kinematics", copy, "a part is a part: joints and configurations stay behind")
        for mine, theirs in zip(copy["prototypes"], hinge["prototypes"]):
            self.assertEqual((mine["name"], mine["faceColors"], mine["faceNames"]),
                             (theirs["name"], theirs["faceColors"], theirs["faceNames"]))
        self.assertTrue(copy["prototypes"][0]["faceColors"], "the painted face")

    def test_a_build_parses_its_steps_in_one_reader_that_exits_with_it(self) -> None:
        from cadgen.engine import reader
        from cadgen.engine.kernel import memo

        memo.clear()
        started = []
        real = reader.Reader._start

        def start(self):
            process = real(self)
            started.append(process)
            return process

        with mock.patch.object(reader.Reader, "_start", start):
            self.built("twice")
        # One reader for two files (the second read of one file is the memo's), gone with the build.
        self.assertEqual(len(started), 1)
        self.assertIsNotNone(started[0].poll(), "the reader exited when the build ended")
        self.assertFalse(reader._SESSION)

    def test_a_step_parse_leaves_the_worker_only_its_result(self) -> None:
        """Measured: the peak resident memory a parse adds to the process that reads, in the
        reader process against in this one (the XCAF reader's working memory)."""
        step = self.folder / "big.step"
        code = textwrap.dedent("""
            import build123d as bd
            parts = []
            for i in range(500):
                part = bd.Pos(i * 30 % 600, (i // 20) * 30, 0) * bd.Cylinder(5 + (i % 7) * 0.1, 10 + i * 0.01)
                part.label = f"p{i}"
                parts.append(part)
            bd.export_step(bd.Compound(children=parts, label="big"), __import__("sys").argv[1])
        """)
        subprocess.run([sys.executable, "-c", code, str(step)], check=True, capture_output=True)
        measure = textwrap.dedent("""
            import sys, json
            import build123d, OCP.STEPCAFControl, OCP.BinTools
            from cadgen.engine import reader
            build123d.Shape  # the kernel loaded before the measure, where cadgen's .pth makes the import lazy

            def parse():
                if sys.argv[2] == "reader":
                    return reader.read_step(sys.argv[1])
                header, data = reader._parse(sys.argv[1])
                shapes, locations = reader.unpack(data, header["shapes"])
                del data
                return reader.assemble(header, shapes, locations)

            try:
                import resource
            except ImportError:  # Windows
                resource = None
            if resource is not None:
                # The process's peak resident memory: what the parse lifted it by.
                before = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
                shape = parse()
                grown = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss - before
            else:
                # Windows keeps no peak a parse can lift past the imports' own (the peak working set
                # and the peak commit both read 0 growth on the runner), so the process's committed
                # private memory (PROCESS_MEMORY_COUNTERS.PagefileUsage) is sampled while it parses.
                import ctypes
                import threading
                from ctypes import wintypes

                class Counters(ctypes.Structure):
                    _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                                *((name, ctypes.c_size_t) for name in (
                                    "PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage",
                                    "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage", "QuotaNonPagedPoolUsage",
                                    "PagefileUsage", "PeakPagefileUsage"))]

                # Typed: the current process's pseudo-handle is -1, a HANDLE, not a C int.
                current = ctypes.windll.kernel32.GetCurrentProcess
                current.restype = wintypes.HANDLE
                info = ctypes.windll.psapi.GetProcessMemoryInfo
                info.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
                info.restype = wintypes.BOOL

                def committed():
                    counters = Counters()
                    counters.cb = ctypes.sizeof(Counters)
                    assert info(current(), ctypes.byref(counters), counters.cb), ctypes.WinError()
                    return counters.PagefileUsage

                before = committed()
                highest = [before]
                finished = threading.Event()

                def sample():
                    while not finished.wait(0.002):
                        highest[0] = max(highest[0], committed())

                sampler = threading.Thread(target=sample)
                sampler.start()
                try:
                    shape = parse()
                finally:
                    finished.set()
                    sampler.join()
                grown = max(highest[0], committed()) - before
            assert len(shape.children) == 500
            print(json.dumps(grown))
        """)
        grown = {}
        for where in ("here", "reader"):
            done = subprocess.run([sys.executable, "-c", measure, str(step), where], capture_output=True, text=True)
            self.assertEqual(done.returncode, 0, done.stderr)
            grown[where] = json.loads(done.stdout.strip().splitlines()[-1])
        # Measured 62 MB here against 14 MB with the reader: the parse's memory is the reader's.
        self.assertLess(grown["reader"], grown["here"] * 0.5, grown)


READS = """
from pathlib import Path

import build123d as bd
from OCP.BRep import BRep_Builder
from OCP.BRepTools import BRepTools
from OCP.gp import gp_Pnt
from OCP.Poly import Poly_Triangle, Poly_Triangulation
from OCP.TopoDS import TopoDS_Face, TopoDS_Shape
from cadgen.engine import model, read_mesh, xbf

HERE = Path(__file__).resolve().parent


@xbf("XBF/enclosure.xbf")
def enclosure():
    pcb = read_mesh(HERE / "scans" / "pcb.stl").bounding_box()
    return bd.Box(pcb.size.X + 6, pcb.size.Y + 6, pcb.size.Z + 4)


@xbf("XBF/by_import_stl.xbf")
def by_import_stl():
    return bd.Box(*bd.import_stl(HERE / "scans" / "pcb.stl").bounding_box().size)


@xbf("XBF/by_import_step.xbf")
def by_import_step():
    return bd.import_step(HERE / "part.step")


@model
def by_import_brep():
    return bd.import_brep(HERE / "part.brep")


@xbf("XBF/by_occt.xbf")
def by_occt():
    shape = TopoDS_Shape()
    BRepTools.Read_s(shape, str(HERE / "part.brep"), BRep_Builder())
    return bd.Solid(shape)


@xbf("XBF/mesh_face.xbf")
def mesh_face():
    mesh = read_mesh(HERE / "scans" / "pcb.stl")
    triangulation = Poly_Triangulation(len(mesh.vertices), len(mesh.triangles), False)
    for at, point in enumerate(mesh.vertices, 1):
        triangulation.SetNode(at, gp_Pnt(*(float(value) for value in point)))
    for at, corners in enumerate(mesh.triangles, 1):
        triangulation.SetTriangle(at, Poly_Triangle(*(int(corner) + 1 for corner in corners)))
    face = TopoDS_Face()
    BRep_Builder().MakeFace(face, triangulation)  # its triangles alone, as import_stl makes a face
    scan = bd.Face(face)
    scan.label = "scan"
    base = bd.Box(50, 40, 2)
    base.label = "base"
    return bd.Compound(children=[base, scan], label="kit")
"""

# A model sized from an STL by build123d's importer, as a user writes one.
SIZED = """
from pathlib import Path

import build123d as bd
from cadgen.engine import xbf

HERE = Path(__file__).resolve().parent


@xbf("XBF/sized.xbf")
def sized():
    scan = bd.import_stl(HERE / "cube.stl")
    return bd.Box(*scan.bounding_box().size)
"""


class ReadsTest(unittest.TestCase):
    """A mesh read as data, keyed by its bytes, as build123d's importers are; a file read past
    the engine's readers, in C++ where no hook hears it, runs its body on every build."""

    def setUp(self) -> None:
        import build123d as bd

        self.folder = Path(tempfile.mkdtemp(prefix="engine-reads-")).resolve()
        self.addCleanup(shutil.rmtree, self.folder, ignore_errors=True)
        (self.folder / "scans").mkdir()
        (self.folder / "reads.py").write_text(textwrap.dedent(READS), encoding="utf-8")
        self.stl = self.folder / "scans" / "pcb.stl"
        self.scan(40)
        box = bd.Box(10, 10, 10)
        bd.export_step(box, str(self.folder / "part.step"))
        bd.export_brep(box, str(self.folder / "part.brep"))
        self.restart()
        self.addCleanup(self.restart)

    def scan(self, length: float) -> None:
        import build123d as bd

        bd.export_stl(bd.Box(length, 30, 2), str(self.stl))

    def restart(self) -> None:
        """What a new worker holds: nothing."""
        from cadgen.engine.kernel import memo

        memo.clear()
        engine_build._WRITTEN.clear()
        engine_build._PARTS.clear()
        engine_build._BUILT.clear()

    def built(self, name: str) -> dict:
        (report,) = engine_build.build(self.folder / "reads.py", [name], cwd=self.folder)
        self.assertTrue(report["ok"], report)
        return report

    def size(self, name: str) -> tuple:
        from OCP.Bnd import Bnd_Box
        from OCP.BRepBndLib import BRepBndLib

        box = Bnd_Box()
        for prototype in document.Loaded(self.folder / f"XBF/{name}.xbf").prototypes:
            BRepBndLib.Add_s(prototype.shape, box)
        low, high = box.CornerMin(), box.CornerMax()
        return tuple(round(b - a, 3) for a, b in ((low.X(), high.X()), (low.Y(), high.Y()), (low.Z(), high.Z())))

    def test_read_mesh_parses_with_the_one_stl_reader_and_names_an_ascii_solid(self) -> None:
        from cadgen.engine.reader import _read_mesh

        ascii_stl = self.folder / "tile.stl"
        ascii_stl.write_text("solid tile plate\nfacet normal 0 0 1\nouter loop\nvertex 0 0 0\nvertex 1 0 0\n"
                             "vertex 0 1 0\nendloop\nendfacet\nendsolid tile plate\n", encoding="ascii")
        mesh = _read_mesh(str(ascii_stl))
        self.assertEqual((mesh.name, mesh.vertices.shape, mesh.triangles.tolist()), ("tile plate", (3, 3), [[0, 1, 2]]))
        ascii_stl.write_text("solid broken\nvertex 0 0 0\nvertex 1 0 0\n", encoding="ascii")
        with self.assertRaisesRegex(ValueError, "come three to a facet"):  # formats/stl.read_stl's words
            _read_mesh(str(ascii_stl))

    def test_read_mesh_is_data_keyed_by_the_file_s_bytes(self) -> None:
        from cadgen.engine import previous, read_mesh

        mesh = read_mesh(self.stl)
        self.assertEqual((mesh.vertices.shape, mesh.triangles.shape, mesh.name), ((8, 3), (12, 3), "pcb"))
        self.assertEqual(tuple(mesh.bounding_box().size), (40.0, 30.0, 2.0))
        with self.assertRaises(ValueError):
            mesh.vertices[0, 0] = 1.0  # read-only: a later build's read of the same bytes is this object
        with self.assertRaisesRegex(ValueError, "read a STEP with read_step"):
            read_mesh(self.folder / "part.step")
        self.built("enclosure")
        self.assertEqual(self.size("enclosure"), (46.0, 36.0, 6.0))
        again = self.built("enclosure")
        self.assertEqual((again["bodies"], again["retention"]["fallbacks"]), ({"reads.py::enclosure": "loaded"}, {}))
        _writer, record = previous.scan(self.folder / "XBF/enclosure.xbf")
        closure = json.loads(record)
        self.assertEqual([row[:2] for row in closure["inputs"]], [["file", "../scans/pcb.stl"]])
        self.assertIsNotNone(closure["key"])
        # Another scan runs the body, warm and after a restart.
        self.scan(50)
        self.assertEqual(self.built("enclosure")["bodies"], {"reads.py::enclosure": "run"})
        self.assertEqual(self.size("enclosure"), (56.0, 36.0, 6.0))
        self.restart()
        self.scan(60)
        self.assertEqual(self.built("enclosure")["cache"]["changed"], ["../scans/pcb.stl changed"])
        self.assertEqual(self.size("enclosure"), (66.0, 36.0, 6.0))

    def test_build123d_s_importers_are_inputs_by_their_bytes_and_their_bodies_replay(self) -> None:
        import build123d as bd

        from cadgen.engine import previous

        for name, path in (("by_import_stl", "scans/pcb.stl"), ("by_import_step", "part.step")):
            report = self.built(name)
            self.assertEqual((report["bodies"], report["retention"]["fallbacks"]), ({f"reads.py::{name}": "run"}, {}))
            _writer, record = previous.scan(self.folder / f"XBF/{name}.xbf")
            closure = json.loads(record)
            self.assertIsNotNone(closure["key"], name)
            self.assertIn(["file", f"../{path}"], [row[:2] for row in closure["inputs"]], name)
        # A model with no file: its body replays while the brep's bytes are the same, and runs
        # once they changed.
        for status in ("run", "replayed"):
            report = self.built("by_import_brep")
            self.assertEqual((report["bodies"], report["retention"]["fallbacks"]),
                             ({"reads.py::by_import_brep": status}, {}))
        bd.export_brep(bd.Box(12, 10, 10), str(self.folder / "part.brep"))
        self.assertEqual(self.built("by_import_brep")["bodies"], {"reads.py::by_import_brep": "run"})
        self.assertEqual(self.built("by_import_brep")["bodies"], {"reads.py::by_import_brep": "replayed"})

    def test_a_file_read_past_the_engine_is_an_input_by_its_bytes_and_its_body_never_retained(self) -> None:
        from cadgen.engine import previous

        for name, call, path in (("by_occt", "OCCT's BRepTools.Read_s", "part.brep"),):
            for status in ("run", "loaded"):
                report = self.built(name)
                self.assertEqual(report["bodies"], {f"reads.py::{name}": status}, name)
                if status == "loaded":
                    break
                self.assertEqual(report["retention"]["fallbacks"], {f"reads.py::{name}": [
                    f"reads {path} through {call}: its body is never retained (any edit runs it whole); use read_step/read_xbf/read_mesh"]})
                # The report is the build's, its memo tally whole: `python model.py` prints it.
                self.assertIn("misses", report["memo"], name)
                self.assertTrue(cli._describe(report, 1.0, None).startswith(f"built reads.py::{name} in"), name)
            # The file is an input all the same, by its bytes: the closure keeps its key, and a
            # restart with nothing changed takes the document.
            _writer, record = previous.scan(self.folder / f"XBF/{name}.xbf")
            closure = json.loads(record)
            self.assertIsNotNone(closure["key"], name)
            self.assertIn(f"../{path}", [row[1] for row in closure["inputs"]], name)
            self.restart()
            self.assertEqual(self.built(name)["cache"], {"used": True, "from": "file"}, name)

    def test_a_model_reading_its_inputs_beside_it_restarts_from_its_file_wherever_it_is_copied(self) -> None:
        # tom reads vendor parts past the engine (import_brep) from beside its sources: copied
        # elsewhere with them, a restart with nothing changed takes the document, and an edited
        # input builds it.
        self.built("by_occt")
        moved = Path(tempfile.mkdtemp(prefix="engine-reads-moved-")).resolve() / "copy"
        self.addCleanup(shutil.rmtree, moved.parent, ignore_errors=True)
        shutil.copytree(self.folder, moved)
        self.restart()
        (report,) = engine_build.build(moved / "reads.py", ["by_occt"], cwd=moved)
        self.assertEqual(report["cache"], {"used": True, "from": "file"}, report)
        import build123d as bd

        bd.export_brep(bd.Box(12, 10, 10), str(moved / "part.brep"))
        self.restart()
        (report,) = engine_build.build(moved / "reads.py", ["by_occt"], cwd=moved)
        self.assertEqual(report["cache"]["changed"], ["../part.brep changed"])

    def test_a_model_sized_by_import_stl_builds_again_when_the_stl_changes(self) -> None:
        """The probe: a model sized from cube.stl by build123d's import_stl kept its 40 mm box
        once the STL was 25 mm -- replayed warm, taken from its xbf after a restart: the STL is
        opened in C++, where nothing heard it. It builds again either way."""
        import build123d as bd

        (self.folder / "sized.py").write_text(textwrap.dedent(SIZED), encoding="utf-8")

        def sized(edge: float) -> tuple:
            bd.export_stl(bd.Box(edge, edge, edge), str(self.folder / "cube.stl"))
            (report,) = engine_build.build(self.folder / "sized.py", ["sized"], cwd=self.folder)
            self.assertTrue(report["ok"], report)
            return self.size("sized"), report["cache"]["used"]

        self.assertEqual(sized(40), ((40.0, 40.0, 40.0), False))
        self.assertEqual(sized(25), ((25.0, 25.0, 25.0), False), "warm: it was replayed, 40 mm")
        self.restart()
        self.assertEqual(sized(30), ((30.0, 30.0, 30.0), False), "a fresh worker: it took the 25 mm xbf")

    def test_a_mesh_face_is_refused_by_name_and_the_worker_builds_on(self) -> None:
        """A face with no surface -- read_mesh's triangles made a face, as import_stl makes one --
        crashed the process in the kernel's face modifier (``ShapeCustom.DirectFaces``). It is
        refused by its occurrence's path, saying what to do, and the next build runs."""
        (report,) = engine_build.build(self.folder / "reads.py", ["mesh_face"], cwd=self.folder)
        self.assertFalse(report["ok"])
        self.assertIn("kit/scan is a mesh, not B-rep: face 1 is a triangulation with no surface", report["error"])
        self.assertIn("read_mesh(path)", report["error"])
        self.assertFalse((self.folder / "XBF/mesh_face.xbf").exists())
        self.assertTrue(self.built("enclosure")["ok"])


if __name__ == "__main__":
    unittest.main()
