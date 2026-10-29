"""The line under the run line, in an engine of the test's own: a model's parts, bounds, joints and
configuration sequences against its build before (``delta``). A first build has nothing to compare;
an edit that adds parts says how many and the bounds they were; an edit that keeps the bounds says
how many parts' geometry changed, or that only their materials did; a failed build says none; and
the report a build returns carries it as data. The bounds are each part's exact box placed where it
stands, as ``cadgen inspect`` measures it, where the kernel's quick box is wrong: a free-form
face bulging past its edges, a spline edge's poles, a torus's octagons."""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

from cadgen.engine.kernel.bounds import box_limits
from tests.python.support import engine_daemon

SRC = Path(__file__).resolve().parents[5] / "packages" / "cadgen" / "src"

# A row of ``COUNT`` 10 mm cubes, 20 mm apart, each with a hole of radius ``HOLE`` (none at 0) and
# coloured ``COLOR`` (none when None); ``FAIL`` makes the body raise. cadgen is imported
# first, so its lazy kernel binds ``build123d``.
SCRIPT = """
import json
import sys

from cadgen import model

import build123d as bd

COUNT, FAIL, HOLE, COLOR = {count}, {fail}, {hole}, {color!r}


@model
def row():
    assert not FAIL, "the row needs a cube"
    cube = bd.Box(10, 10, 10) - bd.Cylinder(HOLE, 10) if HOLE else bd.Box(10, 10, 10)
    cubes = [bd.Pos(20 * at, 0, 0) * cube for at in range(COUNT)]
    for at, cube in enumerate(cubes):
        cube.label = f"cube{{at}}"
        if COLOR:
            cube.color = bd.Color(COLOR)
    return bd.Compound(children=cubes, label="row")


if __name__ == "__main__":
    if sys.argv[1:] == ["--report"]:
        print(json.dumps(row.build().models[0]["delta"]))
    else:
        row()
"""


class BoundsTest(unittest.TestCase):
    """The facts walk in this process, on trees ``document.collect`` makes of build123d results."""

    def bounds(self, result) -> list:
        from cadgen.engine import delta, document

        tree = document.collect(result, "model")
        for part in tree.parts:
            part.key = document.geometry_key(part.shape)
        return delta._walked(tree)["bounds"]

    @staticmethod
    def exact(*placed) -> list:
        """The world box's size from each (shape, location) pair's exact box (``AddOptimal``) in the
        shape's own frame placed at the location, as ``cadgen inspect`` measures it, to the run line's
        figures."""
        from OCP.Bnd import Bnd_Box
        from OCP.BRepBndLib import BRepBndLib
        from OCP.gp import gp_Pnt

        from cadgen.engine.delta import _shown

        low, high = [float("inf")] * 3, [float("-inf")] * 3
        for shape, location in placed:
            box = Bnd_Box()
            BRepBndLib.AddOptimal_s(shape.wrapped, box, False, False)
            x0, y0, z0, x1, y1, z1 = box_limits(box)
            for x in (x0, x1):
                for y in (y0, y1):
                    for z in (z0, z1):
                        point = gp_Pnt(x, y, z)
                        if location:
                            point = point.Transformed(location.wrapped.Transformation())
                        for axis, value in enumerate((point.X(), point.Y(), point.Z())):
                            low[axis], high[axis] = min(low[axis], value), max(high[axis], value)
        return [_shown(b - a) for a, b in zip(low, high)]

    def test_a_free_form_part_is_measured_where_it_bulges_and_its_shape_is_left_as_it_was(self) -> None:
        import build123d as bd

        loft = bd.loft([bd.Plane.XY.offset(z) * bd.Circle(r) for z, r in ((0, 10), (20, 30), (40, 10))])
        side = next(face for face in loft.faces() if face.geom_type == bd.GeomType.BSPLINE)
        from OCP.BRep import BRep_Tool

        surface = BRep_Tool.Surface_s(side.wrapped)
        poles = [(surface.Pole(i, j).X(), surface.Pole(i, j).Z()) for i in range(1, surface.NbUPoles() + 1)
                 for j in range(1, surface.NbVPoles() + 1)]
        self.assertEqual(self.bounds(loft), [60.0, 60.0, 40.0], "not its edges' 47.88 x 20.75 x 40")
        self.assertEqual(poles, [(surface.Pole(i, j).X(), surface.Pole(i, j).Z())
                                 for i in range(1, surface.NbUPoles() + 1) for j in range(1, surface.NbVPoles() + 1)],
                         "the face's own surface is not cut")
        # A torus's quick box is the octagon about its circles: 43.3 mm across a 40 mm cylinder.
        self.assertEqual(self.bounds(bd.fillet(bd.Cylinder(20, 30).edges(), 3)), [40.0, 40.0, 30.0])

    def test_sweeps_and_spline_edges_are_their_exact_boxes_placed_where_they_stand(self) -> None:
        import build123d as bd

        path = bd.Spline((0, 0, 0), (30, 20, 10), (60, -10, 40), (90, 0, 0))
        sweep = bd.sweep(bd.Plane(path @ 0, z_dir=path % 0) * bd.Circle(3), path)
        outline = bd.Spline((0, 0), (20, 25), (45, -5), (60, 10))
        blob = bd.extrude(bd.make_face(bd.Wire([outline, bd.Line((60, 10), (60, -20)), bd.Line((60, -20), (0, -20)),
                                                bd.Line((0, -20), (0, 0))])), 10)
        self.assertEqual(self.bounds(sweep), self.exact((sweep, None)))
        self.assertEqual(self.bounds(blob), [60.0, 47.49, 10.0], "not its spline's poles' 50.11")
        turned = bd.Rot(20, 0, 35) * bd.Pos(80, 0, 0) * sweep
        turned.label = "turned"
        blob.label = "blob"
        self.assertEqual(self.bounds(bd.Compound(children=[turned, blob], label="pair")),
                         self.exact((sweep, turned.location), (blob, None)))


class DeltaTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.folder = Path(os.path.realpath(tempfile.mkdtemp(prefix="engine-delta-")))
        cls.addClassCleanup(shutil.rmtree, cls.folder, True)
        engine = Path(tempfile.mkdtemp(prefix="eng-", dir="/tmp" if os.name != "nt" else None)).resolve()
        cls.addClassCleanup(shutil.rmtree, engine, True)
        cls.env = engine_daemon.started({**os.environ, "PYTHONPATH": str(SRC), "CADGEN_ENGINE_DIR": str(engine),
                                         "CADGEN_STATE_DIR": str(cls.folder / "state"),
                                         "CADGEN_CACHE_DIR": engine_daemon.unwritable(cls.folder),
                                         "CADGEN_ENGINE_MESH": "inline"},
                                        cls.addClassCleanup)
        cls.addClassCleanup(cls.run_, "-m", "cadgen.engine", "stop")

    @classmethod
    def run_(cls, *args: str):
        return engine_daemon.run([sys.executable, *args], cwd=cls.folder, env=cls.env)

    def built(self, count: int, *args: str, fail: bool = False, hole: float = 0, color: str | None = None):
        (self.folder / "row.py").write_text(textwrap.dedent(SCRIPT.format(count=count, fail=fail, hole=hole, color=color)),
                                            encoding="utf-8")
        return self.run_("row.py", *args)

    def delta(self, done) -> str:
        lines = done.stdout.splitlines()
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertTrue(lines[0].startswith("built row.py::row"), done.stdout)
        return lines[1].replace("×", "x").replace("·", "|")

    def test_a_build_says_its_parts_and_bounds_against_the_build_before(self) -> None:
        self.assertEqual(self.delta(self.built(2)), "  parts 2 | bounds 30 x 10 x 10 mm | joints 0 | sequences 0")
        self.assertEqual(self.delta(self.built(4)),
                         "  parts 4 (+2) | bounds 70 x 10 x 10 mm (was 30 x 10 x 10) | joints 0 | sequences 0")
        failed = self.built(4, fail=True)
        self.assertEqual(failed.returncode, 1)
        self.assertNotIn("parts", failed.stdout + failed.stderr)
        self.assertEqual(json.loads(self.built(5, "--report").stdout.splitlines()[-1]),
                         {"first": False, "parts": {"now": 5, "was": 4}, "bounds": {"now": [90.0, 10.0, 10.0],
                                                                                     "was": [70.0, 10.0, 10.0]},
                          "joints": {"now": 0}, "sequences": {"now": 0}, "warnings": {"now": 0},
                          "changed": {"parts": 0, "looks": False}})
        # Edits that keep the bounds: a hole in every cube, then only a colour.
        self.assertEqual(self.delta(self.built(5, hole=2)),
                         "  parts 5 | bounds 90 x 10 x 10 mm | joints 0 | sequences 0 | changed 5")
        self.assertEqual(self.delta(self.built(5, hole=2, color="red")),
                         "  parts 5 | bounds 90 x 10 x 10 mm | joints 0 | sequences 0 | materials changed")


class RunLineTest(unittest.TestCase):
    def test_a_declared_file_written_by_a_run_is_sized_as_export_sizes_it(self) -> None:
        from types import SimpleNamespace

        from cadgen.engine import build

        heard: list[str] = []
        target = SimpleNamespace(kind="xbf", path=Path(tempfile.gettempdir()) / "sized.xbf")
        build._outputs([target], {}, heard.append, lambda _path: (True, 21_990), lambda: None)
        self.assertRegex(heard[0], r"^wrote .*sized\.xbf \(21\.5 KB\) in \d+\.\d\ds$")

    def test_a_run_s_report_is_flushed_as_it_is_said(self) -> None:
        # Through a pipe stdout is block-buffered: the `view:` line would wait for whatever the script
        # does after the call (a self-check loading the kernel), and the page with it.
        import io
        from unittest import mock

        from cadgen.engine import cli

        class Pipe(io.StringIO):
            flushed = ""

            def flush(self) -> None:
                self.flushed = self.getvalue()

        pipe = Pipe()
        report = {"ok": True, "model": "m.py::m", "memo": {"bodies_loaded": 1}, "timings": {}, "bodies": {},
                  "cache": {"from": "memory"}, "id": "an-id", "url": "http://127.0.0.1:1/an-id"}
        with mock.patch("sys.stdout", pipe):
            cli._reported([report], 0.1, None, False)
        self.assertTrue(pipe.flushed.endswith("  view: http://127.0.0.1:1/an-id\n"), pipe.flushed)

    def test_a_stopped_run_names_unbuilt_models_only_where_its_code_calls_one_after(self) -> None:
        from types import SimpleNamespace

        from cadgen.engine import model as engine_model

        folder = Path(tempfile.mkdtemp(prefix="engine-after-"))
        self.addCleanup(shutil.rmtree, folder, True)
        script = folder / "parts.py"
        script.write_text("first()\nsecond()\nprint('done')\n", encoding="utf-8")
        models = {"first": engine_model.Model(lambda: None), "second": engine_model.Model(lambda: None), "print": print}
        frame = lambda line: SimpleNamespace(f_code=SimpleNamespace(co_filename=str(script)), f_lineno=line, f_globals=models)  # noqa: E731
        self.assertTrue(engine_model._calls_after(frame(1)), "second() comes after first()")
        self.assertFalse(engine_model._calls_after(frame(2)), "only a print after the last model")

    def test_one_miss_and_one_hit_are_singular(self) -> None:
        from cadgen.engine import cli

        report = {"ok": True, "model": "m.py::m", "memo": {"misses": 1, "hits": 1}, "bodies": {"m": "run"},
                  "timings": {}}
        self.assertEqual(cli._describe(report, 0.1, None), "built m.py::m in 0.10s: bodies 1 run; 1 miss, 1 hit")
        report["memo"] = {"misses": 2, "hits": 0}
        self.assertEqual(cli._describe(report, 0.1, None), "built m.py::m in 0.10s: bodies 1 run; 2 misses, 0 hits")
        took = {"ok": True, "model": "m.py::m", "memo": {"bodies_loaded": 3}, "timings": {}, "bodies": {}, "cache": {"from": "memory"}}
        self.assertEqual(cli._describe(took, 0.1, None), "took m.py::m in 0.10s: its document in memory holds the model's key, "
                                                          "3 bodies loaded, nothing ran")

    def test_a_build_that_waited_for_its_scripts_running_one_says_what_it_did_with_it(self) -> None:
        from cadgen.engine import cli

        waited = {"script": "turbine.py", "ago": 21, "seconds": 206}
        took = {"ok": True, "model": "turbine.py::turbine", "memo": {"bodies_loaded": 1}, "timings": {},
                "bodies": {"turbine.py::turbine": "loaded"}, "cache": {"used": True, "from": "memory"}, "waited": waited}
        self.assertEqual(cli._describe(took, 3.61, False),
                         "took turbine.py::turbine warm in 3.61s: its document in memory holds the model's key, "
                         "1 body loaded, nothing ran; took the build of turbine.py it waited 206s for")
        replayed = {"ok": True, "model": "turbine.py::turbine", "memo": {"misses": 0, "hits": 0}, "timings": {},
                    "bodies": {"turbine.py::turbine": "replayed"}, "waited": waited}
        self.assertEqual(cli._describe(replayed, 3.61, False),
                         "built turbine.py::turbine warm in 3.61s: bodies 1 replayed; 0 misses, 0 hits; replayed "
                         "the build of turbine.py it waited 206s for")


if __name__ == "__main__":
    unittest.main()
