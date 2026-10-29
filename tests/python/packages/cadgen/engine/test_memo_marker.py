"""``@memo``: a function the engine replays instead of executing when what it is made of --
its code, the symbols it uses, the files it reads, its arguments -- is what it was; a call
it cannot key runs and is reported; a verifying build (``Model.build(verify=True)``,
``cadgen build SOURCE --verify``) runs every replayable call again and marks a function whose
result differs."""

from __future__ import annotations

import os
import shutil
import tempfile
import textwrap
import time
import unittest
from pathlib import Path
from unittest import mock

from cadgen.engine import build as engine_build
from cadgen.engine import document
from cadgen.engine.kernel import memo

SHARED = """
WIDTH = {width}
"""

PARTS = """
import os
from pathlib import Path

import build123d as bd
from cadgen.engine import memo
from shared import WIDTH

HERE = Path(__file__).resolve().parent


def _note(name):
    with open(HERE / "calls.log", "a") as handle:  # an output: not one of its inputs
        handle.write(name + "\\n")


@memo
def plate(length, holes=2):
    _note("plate")
    body = bd.Box(length, WIDTH, {thickness})
    for i in range(holes):
        body = body - bd.Pos(i * 3, 0, 0) * bd.Cylinder(1, 5)
    return body


@memo
def tagged():
    _note("tagged")
    height = float((HERE / "height.txt").read_text())
    part = bd.Box(4, 4, height)
    return part


@memo
def offset(shape, by):
    _note("offset")
    moved = shape.moved(bd.Location((0, 0, by)))
    return {{"moved": moved}}


@memo
def faces(shape):
    _note("faces")
    return len(shape.faces())


@memo
def through(make):
    _note("through")
    made = make()
    return made


@memo
def jitter():
    _note("jitter")
    # An input the engine cannot see: a lookup, not an open.
    grown = bd.Box(2, 2, 1 + os.stat(HERE / "size.bin").st_size)
    return grown
"""

ROOT = """
import build123d as bd
from cadgen.engine import xbf
from parts import faces, jitter, offset, plate, tagged, through

HOLE = {hole}


@xbf("XBF/root.xbf")
def root():
    a = plate({length})
    a.label = "a"
    again = plate({length}).moved(bd.Location((0, 30, 0)))
    again.label = "again"
    b = tagged()
    b.label = "b"
    c = offset(a, 5.0)["moved"]
    c.label = "c"
    n = faces(a)
    d = through(lambda: bd.Box(1, 1, n))
    d.label = "d"
    j = jitter()
    j.label = "j"
    e = bd.Box(2, 2, 2) - bd.Cylinder(HOLE, 5)
    e.label = "e"
    return bd.Compound(children=[a, again, b, c, d, j, e], label="root")
"""

STAGES = """
import build123d as bd
{import_line}


{marker}
def stage_one(size):
    body = bd.Box(size, size, 6)
    body = bd.fillet(body.edges().filter_by(bd.Axis.Z), 1)
    return body


{marker}
def stage_two(base, depth):
    cut = base - bd.Pos(0, 0, 3) * bd.Cylinder(2, depth)
    cut = bd.chamfer(cut.edges().group_by(bd.Axis.Z)[-1], 0.3)
    return cut


@xbf("XBF/staged.xbf")
def staged():
    one = stage_one(12)
    two = stage_two(one, 4).moved(bd.Location((20, 0, 0)))
    one.label, two.label = "one", "two"
    spare = bd.Box({spare}, 1, 1).moved(bd.Location((0, 20, 0)))
    spare.label = "spare"
    return bd.Compound(children=[one, two, spare], label="staged")
"""


class MemoCase(unittest.TestCase):
    def setUp(self) -> None:
        self.restart()
        self.addCleanup(self.restart)
        patch = mock.patch.dict(os.environ)
        patch.start()
        self.addCleanup(patch.stop)
        os.environ.pop("CADGEN_ENGINE_BODIES", None)
        os.environ.pop("CADGEN_ENGINE_MEMO", None)
        self.folder = Path(tempfile.mkdtemp(prefix="engine-memo-marker-")).resolve()
        self.addCleanup(shutil.rmtree, self.folder, ignore_errors=True)
        self.write("shared.py", SHARED.format(width=10))
        self.write("parts.py", PARTS.format(thickness=2))
        self.write("root.py", ROOT.format(hole=1.0, length=20))
        self.write("height.txt", "3")
        self.write("size.bin", "x")

    def restart(self) -> None:
        """What a new worker holds: nothing."""
        memo.clear()
        engine_build._WRITTEN.clear()
        engine_build._PARTS.clear()
        engine_build._BUILT.clear()

    def write(self, name: str, text: str) -> None:
        path = self.folder / name
        path.write_text(textwrap.dedent(text), encoding="utf-8")
        os.utime(path, ns=(time.time_ns(), time.time_ns()))

    def build(self, script: str = "root.py", *, verify: bool = False) -> dict:
        report = engine_build.build(self.folder / script, None, cwd=self.folder, verify=verify)[-1]
        self.assertTrue(report["ok"], report)
        return report

    def calls(self) -> list[str]:
        """The functions that ran since the last call, in order (the log they append to)."""
        path = self.folder / "calls.log"
        found = path.read_text(encoding="utf-8").split() if path.exists() else []
        path.unlink(missing_ok=True)
        return found

    def statuses(self, report: dict) -> dict[str, list[str]]:
        found: dict[str, list[str]] = {}
        for name, status in report["bodies"].items():
            found.setdefault(name.split("(")[0], []).append(status)
        return found


class MemoTest(MemoCase):
    def test_an_unchanged_function_is_replayed_and_an_unkeyable_call_runs_and_is_reported(self) -> None:
        self.build()
        self.assertEqual(self.calls(), ["plate", "tagged", "offset", "faces", "through", "jitter"],
                         "a second call with the same arguments places the first's result: plate ran once")
        self.write("root.py", ROOT.format(hole=1.25, length=20))
        report = self.build()
        self.assertEqual(self.calls(), ["faces", "through"], "only the calls the memo cannot replay ran")
        statuses = self.statuses(report)
        self.assertEqual(statuses["root.py::root"], ["run"])
        for name in ("parts.py::plate", "parts.py::tagged", "parts.py::offset", "parts.py::jitter"):
            self.assertEqual(statuses[name], ["replayed"], name)
        fallbacks = report["retention"]["fallbacks"]
        self.assertIn("callable argument", " ".join(fallbacks["parts.py::through"]))
        self.assertIn("returned int, not geometry", " ".join(fallbacks["parts.py::faces"]))

    def test_an_argument_code_symbol_or_file_change_runs_the_function(self) -> None:
        self.build()
        self.calls()
        self.write("root.py", ROOT.format(hole=1.0, length=21))
        self.build()
        self.assertEqual(self.calls(), ["plate", "offset", "faces", "through"], "an argument changed")
        self.write("parts.py", PARTS.format(thickness=3))
        self.build()
        self.assertEqual(self.calls(), ["plate", "offset", "faces", "through"], "plate's code changed")
        self.write("shared.py", SHARED.format(width=11))
        self.build()
        self.assertEqual(self.calls(), ["plate", "offset", "faces", "through"], "a symbol plate uses changed")
        self.write("height.txt", "5")
        self.build()
        self.assertEqual(self.calls(), ["tagged", "faces", "through"], "a file tagged reads changed")

    def test_a_method_is_refused_at_decoration(self) -> None:
        from cadgen.engine import memo as marker

        with self.assertRaisesRegex(TypeError, "a method is not markable"):
            class Kit:  # noqa: F841 - refused before the class exists
                @marker
                def part(self, size):
                    return size
        with self.assertRaisesRegex(TypeError, "takes no arguments"):
            marker(out="x.xbf")

    def test_verify_catches_an_impure_function_and_marks_it(self) -> None:
        self.build()
        self.write("size.bin", "xx")  # what jitter reads, unseen: its replay is stale
        self.write("root.py", ROOT.format(hole=1.25, length=20))
        self.build()
        self.calls()
        report = self.build(verify=True)
        found = report["verify"]
        self.assertEqual(found["mismatches"], ["parts.py::jitter"], found)
        self.assertIn("other geometry", found["checked"]["parts.py::jitter"])
        self.assertEqual(found["checked"]["root.py::root"], "follows parts.py::jitter",
                         "the root holds jitter's result: it differs with it, and is not marked")
        plate = [found["checked"][name] for name in found["checked"] if name.startswith("parts.py::plate(")]
        self.assertEqual(plate, ["same"], "a call with arguments is named by them: plate(<digest>)")
        self.assertEqual(found["always_run"], ["parts.py::jitter"])
        self.assertEqual(self.calls(), ["plate", "tagged", "offset", "faces", "through", "jitter"],
                         "a verifying build runs everything the memo would replay")
        report = self.build()
        self.assertEqual(self.calls(), ["faces", "through", "jitter"],
                         "marked, jitter runs on every build, and so does the root that calls it")
        self.assertEqual(self.statuses(report)["parts.py::jitter"], ["run"])
        self.assertEqual(report["cache"]["reason"], "it calls parts.py::jitter, which a verification found impure")

    def test_verify_reads_an_order_only_difference_as_the_same_geometry(self) -> None:
        # One shape's sub-shapes in another order (as a parallel boolean or a replay can write
        # them): another BRep, the same geometry -- `same`. Moved, it is other geometry.
        import build123d as bd
        from OCP.BRep import BRep_Builder
        from OCP.TopoDS import TopoDS_Compound

        def compound(*solids):
            made, builder = TopoDS_Compound(), BRep_Builder()
            builder.MakeCompound(made)
            for solid in solids:
                builder.Add(made, solid.wrapped)
            return made

        box, ball = bd.Box(4, 5, 6), bd.Pos(10, 0, 0) * bd.Sphere(2)
        one, other = compound(box, ball), compound(ball, box)
        self.assertNotEqual(document.geometry_key(one), document.geometry_key(other), "another BRep")
        self.assertTrue(memo._Leaf(one).same(memo._Leaf(other)))
        self.assertIsNone(memo._differs(memo._Leaf(one), memo._Leaf(other)))
        moved = compound(box, bd.Pos(10, 0, 0.5) * bd.Sphere(2))
        self.assertEqual(memo._differs(memo._Leaf(one), memo._Leaf(moved)), "the result has other geometry")

    def test_verify_reaches_the_build_through_the_api(self) -> None:
        import contextlib
        import io

        from cadgen.engine import api
        from cadgen.engine.model import xbf

        self.build()
        self.write("size.bin", "xx")
        self.write("root.py", ROOT.format(hole=1.25, length=20))
        self.build()
        here = Path.cwd()
        os.chdir(self.folder)
        self.addCleanup(os.chdir, here)
        # A model calling the model: a verifying build of it runs the called model's bodies again too.
        self.write("caller.py", "from cadgen.engine import xbf\nfrom root import root\n\n\n"
                                "@xbf(\"XBF/caller.xbf\")\ndef caller():\n    return root().shape\n")
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            report = api.build_script(self.folder / "caller.py", ["caller"], verify=True, daemon=False)
        self.assertTrue(report.ok, report.models)
        found = report.models[0]["verify"]
        self.assertEqual(found["mismatches"], ["parts.py::jitter"], found)

        @xbf("XBF/probe.xbf")
        def probe():
            return None

        # Through the daemon, the request carries it to the worker's build.
        asked = []
        answer = {"done": [{"ok": True, "model": "probe"}], "worker": {}}
        with mock.patch.object(api, "_ask", side_effect=lambda message, *_relays: asked.append(message) or answer), \
                contextlib.redirect_stdout(io.StringIO()):
            probe.build(verify=True)
            probe.build()
            probe.build(verify=True)
        self.assertEqual([message["verify"] for message in asked], [True, False, True])

    def test_the_restart_cache_folds_a_memo_function_into_the_model_key(self) -> None:
        from tests.python.support import engine_cache

        cache = self.folder / "cache"

        def build() -> dict:
            report = engine_build.build(self.folder / "root.py", None, cwd=self.folder, cache=str(cache))[-1]
            self.assertTrue(report["ok"], report)
            return report

        build()
        engine_cache.restart(cache)
        report = build()
        self.assertEqual(report["cache"], {"used": True, "from": "cache"})
        self.assertEqual(report["memo"]["bodies_loaded"], 6)
        self.write("parts.py", PARTS.format(thickness=3))
        engine_cache.restart(cache)
        report = build()
        self.assertEqual(report["cache"]["reason"], "../parts.py: plate changed")


# A shape made with OCCT's own makers, which no key names: alone in a model's body it keeps
# the body running; marked @memo, the call keys it.
NATIVE = """
from pathlib import Path

import build123d as bd
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
from cadgen.engine import memo, model

HERE = Path(__file__).resolve().parent
HOLE = {hole}


def _note(name):
    with open(HERE / "calls.log", "a") as handle:
        handle.write(name + "\\n")


{marker}
def native_block(size):
    _note("native_block")
    return bd.Solid(BRepPrimAPI_MakeBox(size, size, size).Shape())


@model
def drilled():
    _note("drilled")
    part = native_block(4.0) - bd.Pos(2, 2, 0) * bd.Cylinder(HOLE, 10)
    part.label = "part"
    return bd.Compound(children=[part], label="drilled")
"""


class MemoNativeTest(MemoCase):
    def native(self, marker: str, hole: float = 1.0) -> dict:
        self.write("native.py", NATIVE.format(marker=marker, hole=hole))
        return self.build("native.py")

    def test_a_memo_call_keys_the_shapes_it_made_with_occt_s_own_makers(self) -> None:
        # Unmarked, the box no key names keeps the body from being kept: a no-op takes the document
        # by its key, but an edit runs the body whole, the box made again, and the report says why.
        self.native("")
        self.calls()
        report = self.native("")
        self.assertEqual((self.calls(), report["cache"]), ([], {"used": True, "from": "memory"}))
        report = self.native("", hole=1.25)
        self.assertEqual((self.calls(), self.statuses(report)), (["drilled", "native_block"],
                                                                 {"native.py::drilled": ["run"]}))
        self.assertIn("no keyed call made", " ".join(report["retention"]["fallbacks"]["native.py::drilled"]))
        # Marked, the call keys its result, with no fallback: an edit of the caller runs it on the
        # very box the replayed call hands back; then a no-op takes the document.
        self.native("@memo")
        self.calls()
        report = self.native("@memo", hole=1.5)
        self.assertEqual((self.calls(), report["retention"]["fallbacks"]), (["drilled"], {}))
        self.assertEqual(self.statuses(report)["native.py::native_block"], ["replayed"])
        self.native("@memo", hole=1.5)
        self.assertEqual(self.calls(), [])
        # A worker that holds nothing runs both, keyed again.
        self.restart()
        report = self.native("@memo", hole=1.5)
        self.assertEqual((self.calls(), report["retention"]["fallbacks"]), (["drilled", "native_block"], {}))
        report = self.native("@memo", hole=1.5)
        self.assertEqual((self.calls(), report["memo"]["bodies_run"]), ([], 0))


class MemoNamesTest(MemoCase):
    def stage(self, marker: str, spare: float = 1.0) -> None:
        imports = "from cadgen.engine import memo, xbf" if marker else "from cadgen.engine import xbf"
        self.write("staged.py", STAGES.format(import_line=imports, marker=marker, spare=spare))

    def names(self) -> dict:
        loaded = document.load(self.folder / "XBF" / "staged.xbf")
        return {p.name: (dict(p.face_names), dict(p.edge_names), dict(p.vertex_names)) for p in loaded.prototypes}

    def test_names_are_the_same_with_and_without_memo_and_when_replayed(self) -> None:
        from tests.python.support import engine_daemon
        engine_daemon.isolate(self.addCleanup)
        self.stage("")
        self.build("staged.py")
        plain = self.names()
        self.assertTrue(plain["two"][0], "the second stage's faces are named")
        self.restart()
        self.stage("@memo")
        self.build("staged.py")
        self.assertEqual(self.names(), plain)
        # The root edited, both stages replayed: the same names again.
        self.stage("@memo", spare=2.0)
        report = self.build("staged.py")
        self.assertEqual(self.statuses(report), {"staged.py::staged": ["run"], "staged.py::stage_one": ["replayed"],
                                                 "staged.py::stage_two": ["replayed"]})
        found = self.names()
        self.assertEqual({name: found[name] for name in ("one", "two")}, {name: plain[name] for name in ("one", "two")})
        replayed = self.measured(plain)
        # A second cold build, in a worker that holds nothing: each ref measures the same again.
        self.restart()
        (self.folder / "XBF" / "staged.xbf").unlink()
        report = self.build("staged.py")
        self.assertEqual(report["memo"]["hits"], 0, "cold: nothing replayed, nothing taken from a file")
        self.assertEqual(self.measured(plain), replayed)

    def measured(self, names: dict) -> list:
        """What `cadgen inspect` measures of each named face of stage two, by its ref."""
        from cadgen.engine import api

        xbf = self.folder / "XBF" / "staged.xbf"
        found = []
        for name in sorted(names["two"][0].values()):
            facts = dict(api.inspect(xbf, f"two/{name}"))
            found.append((facts["ref"], round(facts["area"], 9), facts.get("kind")))
        return found


if __name__ == "__main__":
    unittest.main()
