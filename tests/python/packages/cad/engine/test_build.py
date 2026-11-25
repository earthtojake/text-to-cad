"""Building a model: the decorators, the document it writes, what a warm build does
again, and the law that nothing but the declared files is written."""

from __future__ import annotations

import json

import os
import re
import tempfile
import textwrap
import time
import unittest
from pathlib import Path
from unittest import mock

from cad.engine import build as engine_build
from cad.engine import document
from bd_materials import metals
from cad.engine.colors import linear
from cad.engine.model import SUFFIXES, Model, step, stl, model

MODEL = """
import build123d as bd
from cad.engine import model, step, paint

WIDTH = {width}


@model("XBF/bracket.xbf")
def bracket():
    plate = bd.Box(WIDTH, 10, 2)
    plate = bd.fillet(plate.edges().filter_by(bd.Axis.Z), 1)
    plate = plate - bd.Cylinder(1.5, 5)
    plate.color = bd.Color(0.1, 0.5, 0.9)
    return plate


@model("out/frame.xbf")
@step(out="out/frame.step")
def frame():
    left = bracket().shape
    right = bracket().shape.moved(bd.Location((0, 20, 0)))
    right.label = "right"
    rail = bd.Box(4, 40, 4).moved(bd.Location((WIDTH, 10, 0)))
    rail = paint(rail, rail.faces().sort_by(bd.Axis.Z)[-1], "#ff0000")
    rail.label = "rail"
    return bd.Compound(children=[left, right, rail], label="frame")
"""


def _files(folder: Path) -> set[str]:
    return {path.relative_to(folder).as_posix() for path in folder.rglob("*") if path.is_file()}


class EngineCase(unittest.TestCase):
    def setUp(self) -> None:
        self.folder = Path(tempfile.mkdtemp(prefix="engine-build-")).resolve()
        self.addCleanup(lambda: __import__("shutil").rmtree(self.folder, ignore_errors=True))
        self.script = self.folder / "frame.py"

    def write(self, width: int = 30, text: str = MODEL) -> None:
        self.script.write_text(textwrap.dedent(text.format(width=width)), encoding="utf-8")
        # A rewrite within the same clock tick still reads as a new file.
        os.utime(self.script, ns=(time.time_ns(), time.time_ns()))

    def build(self, *functions: str) -> dict[str, dict]:
        reports = engine_build.build(self.script, list(functions) or None, cwd=self.folder)
        return {report["model"].rsplit("::", 1)[-1]: report for report in reports}


class DecoratorTest(unittest.TestCase):
    def test_required_out_and_stacked_in_source_order(self) -> None:
        @model("XBF/one.xbf")
        def one():
            return None

        @model("a/b.xbf")
        @stl(out="b.stl")
        @step("two.step")
        def two():
            return None

        self.assertIsInstance(one, Model)
        here = Path(__file__).resolve().parent
        self.assertEqual(one.targets(), [("xbf", here / "XBF/one.xbf")])
        self.assertEqual(two.targets(), [("xbf", here / "a/b.xbf"), ("stl", here / "b.stl"), ("step", here / "two.step")])
        self.assertEqual(two.identity, "test_build.py::two")
        with self.assertRaises(ValueError):
            model("x.step")
        with self.assertRaises(TypeError):
            @model("XBF/takes.xbf")
            def takes(value):
                return value

    def test_a_path_is_optional_and_its_default_is_the_model_name_beside_the_script(self) -> None:
        from cad import dxf, glb, threemf
        here = Path(__file__).resolve().parent
        for decorator, suffix in ((step, ".step"), (glb, ".glb"), (stl, ".stl"), (threemf, ".3mf"), (dxf, ".dxf"),
                                  (model, ".xbf")):
            with self.subTest(kind=decorator.__name__):
                def arm():
                    return None

                kind = "xbf" if suffix == ".xbf" else [k for k, s in SUFFIXES.items() if s == suffix][0]

                def files(name: str, path: Path) -> list:
                    # Each declaration writes its own file: a file decorator alone, that file alone.
                    return [(kind, path)]

                # Bare, with empty parentheses, and with None: each the model's name and the kind's suffix.
                for declared in (decorator(arm), decorator()(arm), decorator(None)(arm)):
                    self.assertEqual(declared.targets(), files("arm", here / f"arm{suffix}"))
                # name= is the default's name; a path given is the file, as ever.
                self.assertEqual(decorator(name="named")(arm).targets(), files("named", here / f"named{suffix}"))
                self.assertEqual(decorator(f"out/given{suffix}")(arm).targets(), files("arm", here / f"out/given{suffix}"))
                self.assertEqual(decorator(out=f"given{suffix}")(arm).targets(), files("arm", here / f"given{suffix}"))
        # A GLB's options take no path to need one.
        self.assertEqual(glb(tolerance=0.1)(lambda: None).plan()[-1].tolerance, 0.1)
        for decorator in (step, glb, stl, threemf, dxf):
            with self.subTest(kind=decorator.__name__), self.assertRaises(TypeError):
                decorator(7)
        # A model's own .xbf is @model's to name: a path, ending in .xbf.
        for given in ("", 7):
            with self.assertRaisesRegex(TypeError, r"@model\('…\.xbf'\) takes a path"):
                model(out=given)
        # Any other file: the suffix check every declaration makes.
        with self.assertRaisesRegex(ValueError, r"@model\('…\.xbf'\): the file must end in \.xbf, not 'arm\.step'"):
            model("arm.step")
        # The path is positional, as every file decorator's is, or out=; given both, the positional one is the path.
        self.assertEqual([output.kind for output in model("XBF/a.xbf")(lambda: None).outputs], ["xbf"])
        self.assertEqual(model("a.xbf", out="b.xbf")(lambda: None).targets(), [("xbf", here / "a.xbf")])
        self.assertEqual(step("a.step", out="b.step")(lambda: None).targets(), [("step", here / "a.step")])
        # A file with no path is <name>.<ext> joined to the script's folder, whatever the name.
        self.assertEqual(step(name="arms/left")(lambda: None).targets(), [("step", here / "arms" / "left.step")])

    def test_declarations_stack_each_adding_its_file_and_one_kind_twice_is_refused(self) -> None:
        from cad import model

        @model
        def plain():
            raise AssertionError("decoration must not execute the body")

        self.assertIsInstance(plain, Model)
        here = Path(__file__).resolve().parent
        self.assertEqual(plain.targets(), [("xbf", here / "plain.xbf")])
        # Over a file decorator, @model gives its .xbf a path; a file decorator alone writes that file alone.
        both = model("XBF/plain.xbf")(step("STEP/plain.step")(lambda: None))
        self.assertEqual(both.targets(), [("xbf", here / "XBF/plain.xbf"), ("step", here / "STEP/plain.step")])

        @step("filed.step")
        def filed():
            raise AssertionError("decoration must not execute the body")

        self.assertIsInstance(filed, Model)
        self.assertEqual(filed.targets(), [("step", here / "filed.step")])
        self.assertEqual([output.kind for output in filed.outputs], ["step"], "declared: the STEP alone")
        # One kind twice: nothing says which file is the model's.
        with self.assertRaisesRegex(TypeError, r"model 'plain' declares its \.xbf twice: keep one @model$"):
            model(plain)
        with self.assertRaisesRegex(TypeError, r"model 'plain' declares its \.xbf twice: keep one @model$"):
            model("other.xbf")(plain)
        with self.assertRaisesRegex(TypeError, r"model 'filed' declares @step twice: keep one @step$"):
            step()(filed)

    def test_two_models_whose_files_are_one_file_are_their_authors(self) -> None:
        # No check of any kind: each declares its own file, and which one a run leaves is its author's business.
        @model
        def part():
            return None

        @model(name="part")
        def other():
            return None

        self.assertEqual(part.targets(), other.targets())
        import cad.engine.model as declaring

        self.assertFalse(hasattr(declaring, "collisions"))


class BuildTest(EngineCase):
    def test_the_document_holds_names_colours_instances_and_element_names(self) -> None:
        self.write()
        reports = self.build()
        self.assertTrue(all(report["ok"] for report in reports.values()), reports)
        self.assertEqual(_files(self.folder), {"frame.py", "XBF/bracket.xbf", "out/frame.xbf", "out/frame.step"})
        loaded = document.load(self.folder / "out/frame.xbf")
        structure = loaded.structure()
        self.assertEqual(structure["name"], "frame")
        self.assertEqual(structure["units"], "mm")
        self.assertEqual([child["name"] for child in structure["tree"]["children"]], ["bracket", "right", "rail"])
        # A child used twice is one prototype placed twice.
        self.assertEqual([i["prototype"] for i in structure["instances"]], [0, 0, 1])
        self.assertEqual(structure["instances"][1]["matrix"][12:15], [0.0, 20.0, 0.0])
        bracket, rail = loaded.prototypes
        self.assertEqual(bracket.name, "bracket")
        # A build123d Color's channels are sRGB, held linear (``colors``).
        import build123d as bd

        self.assertEqual(bracket.color, tuple(linear(bd.Color(0.1, 0.5, 0.9))))
        self.assertEqual(list(rail.face_colors.values()), [(1.0, 0.0, 0.0, 1.0)])
        self.assertTrue(bracket.face_names and all(name.startswith("f:bracket.") for name in bracket.face_names.values()))
        # The third assignment to ``plate``, a reassignment: the target and its statement's tag.
        self.assertTrue(any(re.search(r"bracket\.plate_[a-p]{6}", name) for name in bracket.face_names.values()))
        self.assertTrue(bracket.edge_names)
        self.assertEqual(len(bracket.key), 32)
        # What wrote it is on the document's main label; where its code is, in its build closure
        # alone, relative to the document; no absolute path anywhere.
        self.assertRegex(loaded.writer, r"^cadgen\.engine xbf/9 \(cadgen .+\)$")
        raw = (self.folder / "out/frame.xbf").read_bytes()
        self.assertEqual(loaded.closure["source"]["path"], "../frame.py")
        self.assertNotIn(b"frame.py", raw.replace(json.dumps(loaded.closure, separators=(",", ":")).encode(), b""))
        self.assertNotIn(str(self.folder).encode(), raw)
        self.assertIsNone(document.Loaded(self.folder / "out/frame.step").writer, "a STEP names no engine writer")
        # The STEP is a translation: names, and every face's element name.
        text = (self.folder / "out/frame.step").read_text(encoding="utf-8")
        self.assertIn("PRODUCT('frame'", text)
        for name in bracket.face_names.values():
            # The writer may break a long entity's line before its name.
            self.assertRegex(text, rf"ADVANCED_FACE\(\s*'{re.escape(name)}'")
        self.assertNotRegex(text, r"ADVANCED_FACE\(\s*''")

    def test_a_step_read_back_names_each_occurrence_as_the_file_does(self) -> None:
        # Two placements of one part are told apart by their own names, not their product's.
        self.write()
        self.build("frame")
        read = document.read_step_shape(self.folder / "out/frame.step")
        self.assertEqual([child.label for child in read.children], ["bracket", "right", "rail"])
        self.assertTrue(read.children[0].wrapped.TShape() == read.children[1].wrapped.TShape())
        # Each placed where the file places it: the second bracket 20 along y.
        offset = read.children[1].center() - read.children[0].center()
        self.assertAlmostEqual(offset.Y, 20.0, places=6)
        self.assertAlmostEqual(abs(offset.X) + abs(offset.Z), 0.0, places=6)

    def test_a_warm_build_hits_and_rewrites_nothing(self) -> None:
        self.write()
        self.build()
        target = self.folder / "out/frame.xbf"
        written = [target, self.folder / "out/frame.step"]
        before = [path.stat().st_mtime_ns for path in written]
        reports = self.build()
        frame = reports["frame"]
        self.assertEqual(frame["memo"]["misses"], 0)
        self.assertEqual((frame["memo"]["bodies_run"], frame["memo"]["bodies_skipped"], frame["cache"]), (0, 0, {
            "used": True, "from": "memory"}), "an unchanged model is not run nor replayed: its key is its document's")
        self.assertFalse(any(row["written"] for row in frame["files"].values()))
        self.assertEqual([path.stat().st_mtime_ns for path in written], before)

    def test_an_assembly_made_again_around_the_same_parts_rewrites_nothing(self) -> None:
        # A child holding what the memo cannot key (a stand-in for a joint) is not keyed: the
        # compound above it is made afresh on every build, around the very parts the memo handed back.
        self.write(text=MODEL.replace('    rail.label = "rail"', '    rail.label = "rail"\n    rail.joints = {{"slide": object()}}'))
        self.build("frame")
        # Its key unchanged, its file is taken and the body is not run at all (``previous``).
        self.assertEqual(self.build("frame")["frame"]["cache"], {"used": True, "from": "memory"})
        # Run, with retention off: made afresh around the same parts, and nothing rewritten.
        with mock.patch.dict(os.environ, {"CAD_ENGINE_BODIES": "0"}):
            self.build("frame")
            frame = self.build("frame")["frame"]
        self.assertGreater(frame["memo"]["uncached"], 0)
        self.assertFalse(any(row["written"] for row in frame["files"].values()))

    def test_an_edit_misses_from_where_it_changed_and_rewrites(self) -> None:
        self.write(30)
        self.build()
        names_before = document.load(self.folder / "out/frame.xbf").prototypes[0].face_names
        self.write(34)
        frame = self.build("frame")["frame"]
        self.assertGreater(frame["memo"]["misses"], 0)
        self.assertTrue(frame["files"][str(self.folder / "out/frame.xbf")]["written"])
        loaded = document.load(self.folder / "out/frame.xbf")
        self.assertEqual(loaded.prototypes[0].face_names, names_before, "faces keep their names across an edit")
        self.write(30)
        frame = self.build("frame")["frame"]
        self.assertEqual(frame["memo"]["misses"], 0, "a revert is the first build's entries")

    def test_a_document_made_or_read_is_not_left_open_in_the_kernel_application(self) -> None:
        # The kernel's application keeps every document opened in it until it is closed;
        # the engine opens none there, so a warm worker's builds and reads leave nothing.
        application = document._application()
        open_before = application.NbDocuments()
        for width in (30, 34, 30):
            self.write(width)
            frame = self.build("frame")["frame"]
            self.assertTrue(frame["files"][str(self.folder / "out/frame.xbf")]["written"])
            document.Loaded(self.folder / "out/frame.xbf")
        self.assertEqual(application.NbDocuments(), open_before)

    def test_a_fresh_process_keeps_a_file_with_the_same_bytes(self) -> None:
        self.write()
        self.build()
        target = self.folder / "out/frame.xbf"
        stamp = target.stat().st_mtime_ns
        engine_build._WRITTEN.clear()
        engine_build._PARTS.clear()
        frame = self.build("frame")["frame"]
        self.assertFalse(frame["files"][str(target)]["written"])
        self.assertEqual(target.stat().st_mtime_ns, stamp)

    def test_a_body_that_raises_reports_the_model_frame_and_keeps_the_file(self) -> None:
        self.write()
        self.build()
        target = self.folder / "out/frame.xbf"
        stamp = target.stat().st_mtime_ns
        self.write(text=MODEL.replace("    rail.label = \"rail\"", "    raise ValueError('rail too short')"))
        frame = self.build("frame")["frame"]
        self.assertFalse(frame["ok"])
        self.assertIn("rail too short", frame["error"])
        self.assertIn("frame.py", frame["error"])
        self.assertNotIn("build123d", frame["error"])
        self.assertEqual(target.stat().st_mtime_ns, stamp)

    def test_a_build123d_warning_in_a_wrapped_call_names_the_model_s_line(self) -> None:
        # build123d's ``clean`` warns at its caller (``stacklevel=2``), which, for a call the memo
        # wraps, is the memo's frame: the warning names the model's file and line instead.
        import warnings

        from build123d.topology import shape_core

        self.write(text="""
            import build123d as bd
            from cad.engine import model


            @model
            def plate():
                box = bd.Box(1, 2, 3)
                return box.clean()
        """)

        class Refusing(shape_core.ShapeUpgrade_UnifySameDomain):
            def Build(self) -> None:  # noqa: N802 - OCCT's name
                raise RuntimeError("refused")

        with mock.patch.object(shape_core, "ShapeUpgrade_UnifySameDomain", Refusing), \
                warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            report = self.build("plate")["plate"]
        self.assertTrue(report["ok"], report)
        [warned] = [found for found in caught if "Unable to clean" in str(found.message)]
        self.assertEqual((Path(warned.filename), warned.lineno), (self.script, 9))

    def test_a_file_read_hits_whether_or_not_a_child_reading_it_ran_alone(self) -> None:
        # A child's body runs inline in every build of its parent, so the n-th read of
        # one file in a build is fixed by the code: building the child alone in between
        # shifts no ordinal of the parent's.
        import build123d as bd

        bd.export_step(bd.Compound(children=[bd.Solid.make_box(3, 4, 5)]), str(self.folder / "bought.step"))
        self.write(text="""
            from pathlib import Path

            import build123d as bd
            from cad.engine import model, read_step

            BOUGHT = Path(__file__).parent / "bought.step"


            @model("XBF/holder.xbf")
            def holder():
                return read_step(BOUGHT) - bd.Cylinder(1, 20)


            @model("XBF/stand.xbf")
            def stand():
                part = read_step(BOUGHT).moved(bd.Location((10, 0, 0)))
                return bd.Compound(children=[holder().shape, part])
        """)
        self.assertTrue(self.build("stand")["stand"]["ok"])
        holder = self.build("holder")["holder"]
        self.assertTrue(holder["ok"], holder)
        self.assertEqual(holder["memo"]["misses"], 0)
        stand = self.build("stand")["stand"]
        self.assertTrue(stand["ok"], stand)
        self.assertEqual((stand["memo"]["misses"], stand["memo"]["uncached"]), (0, 0))

    def test_a_missing_function_is_the_request_s_error(self) -> None:
        self.write()
        with self.assertRaises(engine_build.BuildError):
            self.build("nothing")

    def test_no_bytecode_and_no_other_file(self) -> None:
        self.write()
        (self.folder / "helper.py").write_text("WIDTH = 3\n", encoding="utf-8")
        self.script.write_text(self.script.read_text(encoding="utf-8").replace("WIDTH = 30", "from helper import WIDTH"), encoding="utf-8")
        self.build()
        self.assertFalse(any("__pycache__" in name for name in _files(self.folder)))
        # The declared outputs and nothing else: no sidecar, no record of the build.
        self.assertEqual(_files(self.folder), {"frame.py", "helper.py", "XBF/bracket.xbf", "out/frame.xbf", "out/frame.step"})
        self.assertFalse([name for name in _files(self.folder) if name.endswith(".json")])

    def test_a_declaration_with_no_path_writes_the_model_name_beside_the_script(self) -> None:
        self.write(text=DEFAULTS)
        reports = self.build()
        self.assertTrue(all(report["ok"] for report in reports.values()), reports)
        # Bare @model its .xbf; @step alone its STEP alone, a file decorator writing its own file; name= the
        # default's name; @model over a given path both files.
        self.assertEqual(_files(self.folder), {"frame.py", "plate.xbf", "peg.step", "pin.xbf", "pin.stl",
                                               "arm.xbf", "STEP/arm.step"})
        self.assertEqual(reports["peg"]["warnings"], ["peg saves no .xbf (no @model): once the CAD server restarts, "
                                                      "its next run builds it again from scratch; add @model to save it"])
        self.assertTrue(all("warnings" not in reports[name] for name in reports if name != "peg"), "@model: none")
        self.assertEqual(document.Loaded(self.folder / "plate.xbf").structure()["name"], "plate")
        # A run that changes nothing keeps every file and its time.
        before = {name: (self.folder / name).stat().st_mtime_ns for name in _files(self.folder)}
        reports = self.build()
        self.assertTrue(all(report["ok"] for report in reports.values()), reports)
        self.assertEqual({name: (self.folder / name).stat().st_mtime_ns for name in _files(self.folder)}, before)
        self.assertFalse(any(row["written"] for report in reports.values() for row in report["files"].values()))

    def test_two_models_of_a_run_whose_files_are_one_file_both_build(self) -> None:
        # A script and one it imports, in one folder, each with a model ``part``: both write part.xbf, as their
        # author wrote them; the run checks nothing of it.
        (self.folder / "other.py").write_text(textwrap.dedent("""
            import build123d as bd
            from cad.engine import model


            @model
            def part():
                return bd.Box(1, 1, 1)
        """), encoding="utf-8")
        self.write(text="""
import build123d as bd
from cad.engine import model
import other


@model
def part():
    return other.part().shape.moved(bd.Location((2, 0, 0)))
""")
        reports = engine_build.build(self.script, None, cwd=self.folder)
        self.assertTrue(all(report["ok"] for report in reports), reports)
        self.assertIn("part.xbf", _files(self.folder))


DEFAULTS = """
import build123d as bd
from cad.engine import model, step, stl


@model
def plate():
    return bd.Box(4, 4, 1)


@step
def peg():
    return bd.Cylinder(1, 3)


@model(name="pin")
@stl()
def pin_body():
    return bd.Cylinder(0.5, 4)


@model
@step("STEP/arm.step")
def arm():
    return bd.Box(1, 1, 6)
"""


BRACKET = """
import build123d as bd
from cad.engine import stl, model


@model("XBF/bracket.xbf")
@stl("bracket.stl")
def bracket():
    return bd.Box(10, 4, 2) - bd.Cylinder(1, 5)
"""

RIG = """
import build123d as bd
from cad.engine import stl, model
from bracket import bracket


@stl("peg.stl")
def peg():
    return bd.Cylinder(1, 6)


@model("XBF/rig.xbf")
def rig():
    left = bracket().shape
    right = bracket().shape.moved(bd.Location((0, 20, 0)))
    right.label = "right"
    {last}
    return bd.Compound(children=[left, right, peg().shape], label="rig")
"""


class ChildFilesTest(EngineCase):
    """A file decorator defines an output file (law 11): every model that runs in a build, its
    target or a child another model's body calls, writes the files it declares, once."""

    def setUp(self) -> None:
        super().setUp()
        (self.folder / "bracket.py").write_text(textwrap.dedent(BRACKET), encoding="utf-8")
        self.script = self.folder / "rig.py"
        self.write(text=RIG.replace("{last}", "pass"))

    def rig(self, *functions: str) -> list[dict]:
        reports = engine_build.build(self.script, list(functions) or None, cwd=self.folder)
        self.assertTrue(all(report["ok"] for report in reports), reports)
        return reports

    def test_every_model_that_runs_writes_its_files_once(self) -> None:
        [report] = self.rig("rig")
        # A child of another file and one of the same file with no @model, the bracket called twice:
        # each written once, after the target, reported under it, and only the files each declares.
        children = report["child_models"]
        self.assertEqual(list(children), ["bracket.py::bracket", "rig.py::peg"])
        self.assertEqual([Path(path).name for path in children["bracket.py::bracket"]["files"]],
                         ["bracket.xbf", "bracket.stl"])
        self.assertEqual(_files(self.folder), {"bracket.py", "rig.py", "XBF/rig.xbf", "XBF/bracket.xbf", "bracket.stl",
                                               "peg.stl"})
        self.assertEqual(document.load(self.folder / "XBF/bracket.xbf").name, "bracket", "its own document")
        # A target the build also runs as a child writes once, as the target (the rig edited, so it runs).
        self.write(text=RIG.replace("{last}", "right.label = 'right'"))
        peg, rig = self.rig()
        self.assertEqual((peg["model"], list(rig["child_models"])), ("rig.py::peg", ["bracket.py::bracket"]))
        # A child that ran before its caller failed writes its files all the same.
        (self.folder / "bracket.stl").unlink()
        self.write(text=RIG.replace("{last}", "raise ValueError('no rig')"))
        [failed] = engine_build.build(self.script, ["rig"], cwd=self.folder)
        self.assertIn("no rig", failed["error"])
        self.assertTrue(failed["child_models"]["bracket.py::bracket"]["files"][str(self.folder / "bracket.stl")]["written"])

    def test_a_child_s_files_are_its_own_build_s_and_a_taken_parent_writes_its_own_alone(self) -> None:
        from cad.engine import api
        from tests.python.support import engine_restart

        self.rig("rig")
        written = (self.folder / "XBF/bracket.xbf").read_bytes()
        # Taken by its key, nothing runs: the rig writes its own files, and a child's file gone is
        # its own model's to write.
        (self.folder / "bracket.stl").unlink()
        [warm] = self.rig("rig")
        self.assertEqual((warm["cache"], warm["bodies"]), ({"used": True, "from": "memory"}, {"rig.py::rig": "loaded"}))
        self.assertEqual({Path(path).name: row["written"] for path, row in api.Report([warm]).files.items()},
                         {"rig.xbf": False})
        self.assertFalse((self.folder / "bracket.stl").exists())
        # The bracket's own build, in a fresh worker, takes the document its parent's build made (its
        # .xbf, a child's as any model's), writing the file that went, nothing run.
        engine_restart.restart()
        [own] = engine_restart.build(self.folder / "bracket.py", None, cwd=self.folder)
        self.assertEqual((own["cache"], own["memo"]["bodies_run"]), ({"used": True, "from": "xbf"}, 0))
        self.assertEqual({Path(path).name: row["written"] for path, row in own["files"].items()},
                         {"bracket.xbf": False, "bracket.stl": True})
        # Built cold, it writes the same bytes.
        engine_restart.restart()
        (self.folder / "XBF/bracket.xbf").unlink()
        engine_restart.build(self.folder / "bracket.py", None, cwd=self.folder)
        self.assertEqual((self.folder / "XBF/bracket.xbf").read_bytes(), written)


KIT = """
import build123d as bd
from cad.engine import paint, step, model
from bd_materials import FinishedMaterial, metals

LEFT = {left}
RIGHT = {right}
PIN = {pin}
TOP = bd.Color({top})
PINS = {pins}


@model("XBF/left.xbf")
def left():
    plate = bd.Box(LEFT, 8, 3) - bd.Cylinder(1.5, 10)
    plate.label = "plate"
    plate.color = bd.Color(0.2, 0.4, 0.8)
    paint(plate, plate.faces().sort_by(bd.Axis.Z)[-1], TOP)
    pin = bd.Pos(0, 0, 4) * bd.Cylinder(1, 4)
    pin.label = "pin"
    pin.material = PIN
    peg = bd.Pos(3, 0, 4) * bd.Cylinder(1, 4)
    peg.label = "peg"
    peg.material = metals.mild_steel(metals.MildSteel.G1018_COLD_DRAWN)
    return bd.Compound(children=[plate, pin, peg][:PINS + 1], label="left")


@model("XBF/right.xbf")
def right():
    block = bd.Box(RIGHT, 4, 4)
    block.label = "block"
    block.color = bd.Color(0.8, 0.1, 0.1)
    cap = bd.Pos(0, 0, 3) * bd.Box(2, 2, 2)
    cap.label = "cap"
    cap.material = metals.aluminum()
    bd.RevoluteJoint("hinge", block, axis=bd.Axis((0, 0, 2), (0, 1, 0)), angular_range=(-10, 90))
    bd.RigidJoint("seat", cap)
    block.joints["hinge"].connect_to(cap.joints["seat"], angle=20)
    return bd.Compound(children=[block, cap], label="right")


@model("XBF/kit.xbf")
@step(out="kit.step")
def kit():
    one = right().shape.moved(bd.Location((30, 0, 0)))
    one.label = "one"
    two = right().shape.moved(bd.Location((0, 30, 0)))
    two.label = "two"
    return bd.Compound(children=[left().shape, one, two], label="kit")
"""


class PatchTest(EngineCase):
    """A warm build patches the document it last wrote: the prototypes it changed are made
    again in place, the rest keep their labels, and the file is the cold build's bytes."""

    BASE = dict(left=10, right=6, pin="metals.mild_steel(metals.MildSteel.G1018_COLD_DRAWN)", top="0.1, 0.9, 0.1", pins=2)

    def setUp(self) -> None:
        from cad.engine.kernel import memo

        super().setUp()
        self.script = self.folder / "kit.py"
        self.xbf = self.folder / "XBF/kit.xbf"
        memo.install()
        self.addCleanup(memo.clear)

    def source(self, text: str) -> None:
        self.script.write_text(textwrap.dedent(text), encoding="utf-8")
        os.utime(self.script, ns=(time.time_ns(), time.time_ns()))

    def kit(self, **values) -> dict:
        self.source(KIT.format(**{**self.BASE, **values}))
        report = self.build("kit")["kit"]
        self.assertTrue(report["ok"], report)
        return report

    def cold(self, **values) -> bytes:
        """The kit built by a process that never built it: its bytes."""
        from cad.engine.kernel import memo

        memo.clear()
        engine_build._WRITTEN.clear()
        engine_build._PARTS.clear()
        self.xbf.unlink()
        self.assertFalse(self.kit(**values)["converted"]["patched"])
        return self.xbf.read_bytes()

    def patched(self, **values) -> dict:
        report = self.kit(**values)
        self.assertTrue(report["converted"]["patched"], report["converted"])
        self.assertLess(report["converted"]["converted"], report["converted"]["prototypes"])
        return report

    def test_an_edit_patches_the_document_to_the_cold_bytes(self) -> None:
        self.kit()
        kept = engine_build._WRITTEN[f"{self.script}::kit"].kept
        doc = kept.doc
        edited = self.patched(left=12)
        # The plate, the left body and the kit: the right bodies' labels are untouched.
        self.assertEqual(edited["converted"]["converted"], 3)
        first = self.xbf.read_bytes()
        self.source(KIT.format(**self.BASE).replace("    cap.label", "    raise ValueError('no cap')\n    cap.label"))
        self.assertFalse(self.build("kit")["kit"]["ok"])
        self.assertEqual(self.xbf.read_bytes(), first, "a build that fails leaves the file")
        self.patched(left=12, right=7)
        self.assertIs(kept.doc, doc, "the one document, patched build after build")
        self.assertEqual(self.xbf.read_bytes(), self.cold(left=12, right=7))
        self.assertEqual(self.cold(left=12), first)

    def test_a_removed_part_leaves_no_label(self) -> None:
        from OCP.XCAFDoc import XCAFDoc_DocumentTool

        self.kit()
        report = self.patched(pins=1)
        kept = engine_build._WRITTEN[f"{self.script}::kit"].kept
        shapes = XCAFDoc_DocumentTool.ShapeTool_s(kept.doc.Main()).Label()
        self.assertEqual(len(document._held_children(shapes)), report["converted"]["prototypes"])
        loaded = document.Loaded(self.xbf)
        self.assertNotIn("peg", {prototype.name for prototype in loaded.prototypes})
        self.assertEqual(self.xbf.read_bytes(), self.cold(pins=1))
        self.patched()
        self.assertIn("peg", {prototype.name for prototype in document.Loaded(self.xbf).prototypes})
        self.assertEqual(self.xbf.read_bytes(), self.cold())

    def test_a_changed_material_or_paint_converts_its_prototype(self) -> None:
        self.kit()
        # Aluminium is the cap's too, and now comes first: the materials are numbered anew.
        self.assertEqual(self.patched(pin="metals.aluminum()")["converted"]["converted"], 3)
        pin = next(p for p in document.Loaded(self.xbf).prototypes if p.name == "pin")
        self.assertEqual(pin.material.name, metals.aluminum().name)
        self.assertEqual(self.xbf.read_bytes(), self.cold(pin="metals.aluminum()"))
        self.patched(pin="metals.aluminum()", top="0.9, 0.9, 0.1")
        plate = next(p for p in document.Loaded(self.xbf).prototypes if p.name == "plate")
        import build123d as bd

        self.assertIn(tuple(linear(bd.Color(0.9, 0.9, 0.1))), plate.face_colors.values())
        self.assertEqual(self.xbf.read_bytes(), self.cold(pin="metals.aluminum()", top="0.9, 0.9, 0.1"))
        # A field the file keeps beside XCAF's own (a coat) converts it too.
        self.patched(pin="FinishedMaterial(metals.aluminum().material, pbr=metals.aluminum().pbr.override(clearcoat=0.5))", top="0.9, 0.9, 0.1")
        pin = next(p for p in document.Loaded(self.xbf).prototypes if p.name == "pin")
        self.assertEqual(pin.material.pbr.values.clearcoat, 0.5)
        self.assertEqual(self.xbf.read_bytes(), self.cold(pin="FinishedMaterial(metals.aluminum().material, pbr=metals.aluminum().pbr.override(clearcoat=0.5))", top="0.9, 0.9, 0.1"))

    def test_the_served_document_is_the_written_one(self) -> None:
        import json

        self.kit()
        self.patched(right=8)
        made = document.tree_structure(document.saved(self.xbf), self.xbf)
        read = document.Loaded(self.xbf).structure()
        self.assertEqual(json.loads(json.dumps(made)), json.loads(json.dumps(read)))
        self.assertEqual(len(read["kinematics"]["pairs"]), 2, "each right body's hinge")


BLOCK = """
import build123d as bd
from cad.engine import model


@model("XBF/block.xbf")
def block():
    return bd.Box(3, 2, 1) - bd.Cylinder(0.5, 2)
"""

COLD = """
import sys
from pathlib import Path
from cad.engine import build
folder = Path(sys.argv[1])
reports = build.build(folder / "block.py", ["block"], cwd=folder)
sys.exit(0 if all(report["ok"] for report in reports) else 1)
"""


class DateTest(unittest.TestCase):
    """The file is a function of the code and the geometry alone: the creation date the
    BinXCAF driver writes is a constant (``document.WRITTEN_DATE``), whatever the day."""

    def test_two_cold_builds_a_day_apart_write_the_same_bytes(self) -> None:
        import shutil
        import subprocess
        import sys

        files = []
        # Twenty-six hours apart: the two processes' local dates always differ.
        for zone in ("Etc/GMT+12", "Etc/GMT-14"):
            folder = Path(tempfile.mkdtemp(prefix="engine-date-")).resolve()
            self.addCleanup(shutil.rmtree, folder, ignore_errors=True)
            (folder / "block.py").write_text(textwrap.dedent(BLOCK), encoding="utf-8")
            done = subprocess.run([sys.executable, "-c", COLD, str(folder)], env={**os.environ, "TZ": zone},
                                  capture_output=True, text=True)
            self.assertEqual(done.returncode, 0, done.stderr)
            files.append(folder / "XBF/block.xbf")
        first, second = (path.read_bytes() for path in files)
        self.assertEqual(first, second)
        self.assertIn(b"\x0a\x00\x00\x00" + document.WRITTEN_DATE, first[:1024])
        loaded = document.load(files[0])
        self.assertEqual(len(loaded.prototypes), 1)
        self.assertEqual(len(loaded.prototypes[0].face_names), 7, "the block's six faces and its bore")


if __name__ == "__main__":
    unittest.main()
