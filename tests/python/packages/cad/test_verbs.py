"""The library's verbs (``cad.export``, ``cad.inspect``, ``cad.snapshot``, ``cad.dfm``, ``cad.fea``, ``cad.save``) and
the earlier spellings they replace: each type's operations (``cad.xbf.export``, ``cad.stl.dfm``,
``cad.kicad_pcb.drc``, ...) and the file types' callable forms (``xbf(shape, path)``, ``step(shape, path)``), which
answer as their verbs do and say once that they are deprecated, naming the verb -- where a program calls them, never
where the library or the server calls its own (``cad._internal.aliases.spelled``, the one switch).

Nothing here builds or needs the CAD kernel: the engine's verbs and the writers are stood in for where a call
would reach them.
"""

from __future__ import annotations

import re
import tempfile
import unittest
import warnings
import zipfile
from pathlib import Path
from unittest import mock

import cad
from cad._internal import aliases, verbs
from cad._internal.refused import ArgumentRefused
from cad.engine import api


def _fresh(document_type: str, name: str) -> None:
    """Forget a type's alias and the operation it wraps, so the next lookup binds what a test stands in."""
    verbs._MADE.pop((document_type, name), None)
    getattr(cad, document_type).__dict__.pop(name, None)


class _Shape:
    """A stand-in for build123d's ``Shape``, told apart as the library tells one (by its class's name and module):
    nothing of the kernel is loaded."""


_Shape.__name__ = _Shape.__qualname__ = "Shape"
_Shape.__module__ = "build123d.topology.shape_core"
# A live shape a script holds, as ``cad.dfm`` tells one: a Part, whose ancestry is build123d's Shape.
LIVE = type("Part", (_Shape,), {"__module__": "build123d.topology.composite"})()


class Said:
    """What the deprecations said meanwhile: each warning's message and the file it named."""

    def __init__(self, case: unittest.TestCase) -> None:
        self.case = case

    def __enter__(self) -> list[warnings.WarningMessage]:
        aliases._WARNED.clear()  # each name is said once a process: once more in each test
        self._catcher = warnings.catch_warnings(record=True)
        self.caught = self._catcher.__enter__()
        warnings.simplefilter("always")
        return self.caught

    def __exit__(self, *exc: object) -> None:
        self._catcher.__exit__(*exc)


def _deprecations(caught: list[warnings.WarningMessage]) -> list[str]:
    return [str(found.message) for found in caught if issubclass(found.category, cad.CadDeprecationWarning)]


class TheVerbs(unittest.TestCase):
    def test_the_root_holds_the_verbs(self) -> None:
        for name in ("export", "inspect", "snapshot", "dfm", "fea", "save"):
            with self.subTest(name=name):
                self.assertIn(name, cad.__all__)
                self.assertIs(getattr(cad, name), getattr(verbs, name))

    def test_a_source_whose_type_lacks_the_verb_is_refused_naming_the_types_that_have_it(self) -> None:
        for call, said in (
                (lambda: cad.export("drawing.dxf", "drawing.step"),
                 "drawing.dxf is a dxf, which has no export: cad.export takes xbf, step, stl, glb, threemf, kicad_pcb, "
                 "kicad_sch"),
                (lambda: cad.inspect("part.stl"), "part.stl is an stl, which has no inspect: cad.inspect takes xbf, "
                                                  "step, glb, urdf, srdf, kicad_pcb, kicad_sch"),
                (lambda: cad.inspect("part.glb", ranges=True), "part.glb is a glb, which has no inspect with "
                                                               "ranges=True: cad.inspect(ranges=True) takes xbf, step"),
                (lambda: cad.fea("robot.urdf"), "robot.urdf is a urdf, which has no fea: cad.fea takes xbf, step"),
                (lambda: cad.dfm("board.kicad_pcb"), "board.kicad_pcb is a kicad_pcb: cad.dfm checks that a part can be "
                                                     "made; KiCad's own check of it is cad.kicad.drc"),
                (lambda: cad.dfm("sheet.kicad_sch"), "sheet.kicad_sch is a kicad_sch: cad.dfm checks that a part can be "
                                                     "made; KiCad's own check of it is cad.kicad.erc"),
                (lambda: cad.dfm("arm.py"), "arm.py is a model's script, not a document: running it builds its models "
                                            "(cad run arm.py), and cad.dfm takes the handle a model's call returns or "
                                            "the .xbf it writes")):
            with self.subTest(said=said[:40]), self.assertRaises(ValueError) as refused:
                call()
            self.assertEqual(said, str(refused.exception))

    def test_an_option_a_source_s_inspection_does_not_take_is_refused_naming_what_it_takes(self) -> None:
        with self.assertRaisesRegex(TypeError, r"cad.inspect\(\) of an xbf with interference=True takes poses, fits, "
                                               r"min_volume; not step"):
            cad.inspect("arm.xbf", interference=True, step=2)
        with self.assertRaisesRegex(TypeError, "takes interference=True or ranges=True, not both"):
            cad.inspect("arm.xbf", interference=True, ranges=True)
        with self.assertRaisesRegex(TypeError, "takes no ref or query"):
            cad.inspect("robot.urdf", "base_link")

    def test_inspect_s_modes_are_the_checks_today_s_operations_answer(self) -> None:
        """``cad.inspect(..., interference=True)`` is the interference check a model's or a STEP's ``interference``
        was: asked of the engine as before, its result finished the same way."""
        ident = "0b4c5f1e-1a2b-4c3d-8e9f-0123456789ab"
        answer = {"unmeasured": {"message": "its process went", "code": "stopped"}}
        with mock.patch.object(api, "check", return_value=answer) as check:
            found = cad.inspect(ident, interference=True, poses=["open"], min_volume=0.01)
        self.assertEqual((check.call_args.args[0], check.call_args.args[1]["type"],
                          check.call_args.args[1]["resolved"]["min_volume"]), (ident, "xbf", 0.01))
        with mock.patch.object(api, "check", return_value=answer):
            before = verbs.operation("xbf", "interference")(ident, poses=["open"], min_volume=0.01)
        self.assertEqual((found.status, found.reason, found.summary), (before.status, before.reason, before.summary))
        self.assertEqual("not_checked", found.status)


class TheEarlierSpellings(unittest.TestCase):
    """Each type's operations: an alias of its verb, which answers as the verb does and warns once, naming it."""

    def test_each_type_s_operation_is_its_verb_s_alias_and_says_so_once(self) -> None:
        from cad.registry import DOCUMENT_TYPES

        cases = [(entry.id, name) for entry in DOCUMENT_TYPES.values() for name in entry.operation_names]
        cases += [("kicad_pcb", "drc"), ("kicad_sch", "erc")]
        self.assertGreater(len(cases), 30)
        for document_type, name in cases:
            with self.subTest(alias=f"cad.{document_type}.{name}"):
                alias = getattr(getattr(cad, document_type), name)
                # The same work as the verb's: the type's own operation, its signature and words.
                self.assertIs(alias.__wrapped__, verbs.operation(document_type, name))
                with Said(self) as caught:
                    try:
                        alias("not-its-type.xyz", *(("out.step",) if name == "export" else ()))
                    except (ValueError, TypeError):
                        pass  # refused by name, as the verb refuses it
                said = _deprecations(caught)
                self.assertEqual([f"cad.{document_type}.{name} is deprecated; use {aliases.OPERATION_VERBS[name]}"],
                                 said)
                self.assertEqual(Path(__file__).name, Path(caught[0].filename).name, "the line that spelled it")

    def test_an_alias_still_works(self) -> None:
        """A type's operation answers what the verb answers: the engine's export, given the same, and a robot
        description's check and a board's contents, read by the library's own code."""
        from tests.python.support.kicad_board import write_board

        _fresh("step", "export")
        with mock.patch.object(api, "export", return_value=["written"]) as export, Said(self) as caught:
            self.assertEqual(["written"], cad.step.export("part.step", "part.glb", "part.stl", tolerance=0.1))
        export.assert_called_once_with("part.step", "part.glb", "part.stl", tolerance=0.1)
        self.assertEqual(["cad.step.export is deprecated; use cad.export"], _deprecations(caught))
        _fresh("step", "export")
        with tempfile.TemporaryDirectory() as folder:
            robot = Path(folder) / "robot.urdf"
            robot.write_text('<robot name="r"><link name="base"/></robot>', encoding="utf-8")
            with Said(self):
                self.assertEqual(cad.inspect(robot).summary, cad.urdf.validate(robot).summary)
            board = write_board(Path(folder))
            with Said(self):
                self.assertEqual(cad.inspect(board), cad.kicad_pcb.inspect(board))

    def test_the_library_and_the_server_calling_their_own_say_nothing(self) -> None:
        """A spelling one of the library's, the server's or the transport's own modules calls is no program's: the
        command line's parsers are made of these functions, and the runner of an operation calls them."""
        _fresh("urdf", "validate")
        with tempfile.TemporaryDirectory() as folder:
            robot = Path(folder) / "robot.urdf"
            robot.write_text('<robot name="r"><link name="base"/></robot>', encoding="utf-8")
            for owner in ("cad_server.cli.document_types", "cad._internal.operation", "cad_mcp.shim"):
                with self.subTest(owner=owner), Said(self) as caught:
                    exec(compile("validate(robot)", "<own>", "exec"),  # noqa: S102 - a module's frame, named
                         {"__name__": owner, "validate": cad.urdf.validate, "robot": robot})
                    self.assertEqual([], _deprecations(caught))

    def test_the_runner_of_an_operation_in_another_environment_says_nothing(self) -> None:
        """The command runs an operation in an integration's environment by ``python -m cad._internal.operation``,
        which is ``__main__`` there, no module of the library's by its name: it runs the type's operation, never the
        alias, so nothing is said to the person who typed the command."""
        import json
        import os
        import subprocess
        import sys

        with tempfile.TemporaryDirectory() as folder:
            robot = Path(folder) / "robot.urdf"
            robot.write_text('<robot name="r"><link name="base"/></robot>', encoding="utf-8")
            request = json.dumps({"type": "urdf", "operation": "validate", "args": [str(robot)], "kwargs": {}})
            done = subprocess.run([sys.executable, "-W", "always", "-m", "cad._internal.operation"], input=request,
                                  text=True, capture_output=True, check=True, timeout=120,
                                  env={**os.environ, "PYTHONPATH": os.pathsep.join(path for path in sys.path if path)})
        self.assertTrue(json.loads(done.stdout.strip().splitlines()[-1])["result"]["ok"], done.stdout)
        self.assertNotIn("deprecated", done.stderr)

    def test_the_switch_turns_every_warning_off(self) -> None:
        with mock.patch.object(aliases, "SPELLINGS_WARN", False), Said(self) as caught:
            try:
                cad.stl.dfm("not-its-type.xyz")
            except (ValueError, TypeError):
                pass
        self.assertEqual([], _deprecations(caught))

    def test_a_check_s_alias_keeps_the_annotations_its_command_line_is_made_from(self) -> None:
        """Each check's alias answers ``typing.get_type_hints`` as the operation it runs does, a hint for every
        parameter of its signature: the command line is generated from them (``cad dfm --help``). Python 3.14's
        ``functools.wraps`` copies ``__annotate__`` and no ``__annotations__``, and a check whose annotations were
        set by hand has none to copy (``aliases.ASSIGNED``)."""
        import inspect
        import typing

        from cad.registry import DOCUMENT_TYPES

        checks = [(entry.id, name) for entry in DOCUMENT_TYPES.values() for name in entry.operation_names
                  if name in ("dfm", "interference", "solve", "ranges", "validate")]
        checks += [("kicad_pcb", "drc"), ("kicad_sch", "erc")]
        self.assertGreater(len(checks), 10)
        for document_type, name in checks:
            with self.subTest(alias=f"cad.{document_type}.{name}"):
                alias = getattr(getattr(cad, document_type), name)
                hints = typing.get_type_hints(alias)
                self.assertEqual(typing.get_type_hints(verbs.operation(document_type, name)), hints)
                self.assertLessEqual(set(inspect.signature(alias).parameters), set(hints), "a hint for each parameter")


class TheDestination(unittest.TestCase):
    """``cad.export(source, dst, as_=None)``: what is written is what ``dst`` says -- a file by its suffix; of a KiCad
    file a folder or a ``.zip`` too -- and ``as_`` names the kind only where ``dst`` cannot, agreeing with it where
    ``dst`` says it. Each refusal comes before anything runs, naming what fits."""

    def test_a_document_s_export_is_one_file_and_as_agrees_with_its_suffix(self) -> None:
        _fresh("xbf", "export")
        self.addCleanup(_fresh, "xbf", "export")
        with mock.patch.object(api, "export", return_value=["written"]) as export:
            self.assertEqual(["written"], cad.export("arm.xbf", "arm.step", as_="step"))
            self.assertEqual(["written"], cad.export("arm.xbf", "arm.3mf", "3mf"))
            self.assertEqual(["written"], cad.export("arm.xbf", "arm.xml", as_="mjcf"))
        self.assertEqual([call.args for call in export.call_args_list],
                         [("arm.xbf", "arm.step"), ("arm.xbf", "arm.3mf"), ("arm.xbf", "arm.xml")])
        with tempfile.TemporaryDirectory() as folder, mock.patch.object(api, "export", side_effect=AssertionError("ran")):
            for dst, as_, said in (
                    ("out/", None, "out/ is a folder, and the export is one file: name the file"),
                    (folder, None, f"{folder} is a folder, and the export is one file"),
                    ("arm.step", "glb", "arm.step's suffix says STEP, and as_=glb says GLB: they must agree"),
                    ("arm.urdf", "mjcf", "arm.urdf's suffix says URDF, and as_=mjcf says MJCF: they must agree"),
                    ("arm.step", "gerbers", "as_=gerbers: the export is one of step, glb, stl, 3mf, dxf, xbf, mjcf, "
                                            "urdf")):
                with self.subTest(dst=dst, as_=as_), self.assertRaisesRegex(ArgumentRefused, re.escape(said)):
                    cad.export("arm.xbf", dst, as_=as_)
        with self.assertRaisesRegex(TypeError, r"cad.export\(source, dst, as_=KIND\): as_ names the kind where dst "
                                               "cannot"):
            cad.export("b.kicad_pcb", "fab", to="gerbers")

    def test_a_kicad_file_s_export_is_put_where_dst_says(self) -> None:
        """KiCad writes into a folder of its own, as it names its files (stood in for here: the KiCad suite runs it),
        and its files are put where ``dst`` says: one file at the file named, several into the folder named or zipped
        into the ``.zip``, an ODB++ into a folder its tree. What cannot say what to write is refused before it runs."""
        ran: list[tuple[str, bool]] = []

        def kicad(board: Path, to: str, out_dir: Path, *, warn: object = None, compressed: bool = True) -> list[Path]:
            ran.append((to, compressed))
            names = {"step": ["b.step"], "gerbers": ["b-F_Cu.gbr", "b-job.gbrjob"],
                     "odb": ["b-odb.zip"] if compressed else ["matrix/matrix", "steps/pcb/profile"]}[to]
            for name in names:
                (out_dir / name).parent.mkdir(parents=True, exist_ok=True)
                (out_dir / name).write_text(name, encoding="utf-8")
            return sorted((out_dir / name).resolve() for name in names)

        with tempfile.TemporaryDirectory() as folder, mock.patch("cad.kicad._export.export", kicad):
            root = Path(folder).resolve()
            board = root / "b.kicad_pcb"
            board.write_text("(kicad_pcb)", encoding="utf-8")
            done = cad.export(board, root / "3d" / "board.step")
            self.assertEqual((done.to, done.written), ("step", (root / "3d" / "board.step",)))
            self.assertEqual("b.step", (root / "3d" / "board.step").read_text(encoding="utf-8"))
            done = cad.export(board, f"{root}/fab/gerbers/", as_="gerbers")
            self.assertEqual(done.written, (root / "fab" / "gerbers" / "b-F_Cu.gbr",
                                            root / "fab" / "gerbers" / "b-job.gbrjob"))
            done = cad.export(board, root / "fab" / "gerbers.zip", "gerbers")
            self.assertEqual(done.written, (root / "fab" / "gerbers.zip",))
            with zipfile.ZipFile(root / "fab" / "gerbers.zip") as archive:
                self.assertEqual(archive.namelist(), ["b-F_Cu.gbr", "b-job.gbrjob"])
            done = cad.export(board, f"{root}/fab/odb/", as_="odb")
            self.assertEqual(done.written, (root / "fab" / "odb" / "matrix" / "matrix",
                                            root / "fab" / "odb" / "steps" / "pcb" / "profile"))
            cad.export(board, root / "fab" / "odb.zip", as_="odb")
            self.assertEqual("b-odb.zip", (root / "fab" / "odb.zip").read_text(encoding="utf-8"))
            self.assertEqual(ran, [("step", True), ("gerbers", True), ("gerbers", True), ("odb", False), ("odb", True)])
            for dst, as_, said in (
                    (f"{root}/out/", None, "out/ is a folder, which takes a board's Gerbers, drill files, ODB++ or PDF: "
                                           "name which, as_=gerbers, as_=drill, as_=odb or as_=pdf"),
                    (root / "out.csv", None, "out.csv is a .csv, which takes a board's placement or BOM: name which, "
                                             "as_=pos or as_=bom"),
                    (root / "out.glb", "step", "out.glb is a board's GLB, and as_=step names its STEP: they must agree")):
                with self.subTest(dst=dst), self.assertRaisesRegex(ArgumentRefused, re.escape(said)):
                    cad.export(board, dst, as_=as_)
            self.assertFalse((root / "out").exists(), "a refused export writes nothing")
            with self.assertRaisesRegex(TypeError, "cad.export of a kicad_pcb takes as_ alone"):
                cad.export(board, root / "b.step", tolerance=0.1)
        self.assertEqual(len(ran), 5, "KiCad ran for no refused export")


class AShape(unittest.TestCase):
    """A shape a program holds: saved as a model's ``.xbf`` (``cad.save``), exported to any other file
    (``cad.export``); the file types' callable forms are their earlier spellings."""

    SHAPE = object()  # a stand-in: the writers that take it are stood in for too

    def test_save_hands_a_shape_over_as_its_xbf_and_refuses_any_other_file(self) -> None:
        with mock.patch.object(api, "hand_over", return_value="handle") as hand_over:
            self.assertEqual("handle", cad.save(self.SHAPE, "part.xbf"))
        (shape, name), options = hand_over.call_args
        self.assertEqual((shape, name, options["out"]), (self.SHAPE, None, "part.xbf"))
        self.assertEqual(Path(__file__).name, Path(options["frame"].f_code.co_filename).name, "the caller's script")
        for call, said in ((lambda: cad.save(self.SHAPE), "give the model's .xbf"),
                           (lambda: cad.save(self.SHAPE, "part.step"), r"cad.export\(shape, 'part.step'\)"),
                           (lambda: cad.save("part.xbf", "copy.xbf"), "a model's document is its .xbf already")):
            with self.subTest(said=said), self.assertRaisesRegex((TypeError, ValueError), said):
                call()

    def test_export_writes_a_shape_s_other_files_and_names_save_for_its_xbf(self) -> None:
        with mock.patch.object(api, "write_shape", return_value=Path("part.step")) as write:
            self.assertEqual(Path("part.step"), cad.export(self.SHAPE, "part.step"))
            cad.export(self.SHAPE, "part.stl", tolerance=0.02)
        self.assertEqual(write.call_args_list[0].args[:4], (self.SHAPE, "step", "part.step", None))
        self.assertEqual(write.call_args_list[1].args[5:], (0.02, None))
        with self.assertRaisesRegex(ValueError, r"cad.save\(shape, 'part.xbf'\)"):
            cad.export(self.SHAPE, "part.xbf")
        with self.assertRaisesRegex(TypeError, "give where to write it"):
            cad.export(self.SHAPE)
        with self.assertRaisesRegex(TypeError, "takes no tolerance or angle"):
            cad.export(self.SHAPE, "part.step", tolerance=0.02)
        # One file, named: as_ agrees with its suffix, and a folder is no file -- each refused before it is written.
        with mock.patch.object(api, "write_shape", return_value=Path("part.3mf")) as write:
            self.assertEqual(Path("part.3mf"), cad.export(self.SHAPE, "part.3mf", as_="3mf"))
        self.assertEqual(write.call_args.args[:3], (self.SHAPE, "threemf", "part.3mf"))
        with mock.patch.object(api, "write_shape", side_effect=AssertionError("written")):
            for dst, as_, said in (("part.step", "glb", "part.step's suffix says STEP, and as_=glb says GLB: they must "
                                                        "agree"),
                                   ("parts/", None, "parts/ is a folder, and the export is one file: name the file")):
                with self.subTest(dst=dst), self.assertRaisesRegex(ArgumentRefused, re.escape(said)):
                    cad.export(self.SHAPE, dst, as_=as_)

    def test_a_handle_or_a_file_exports_a_copy_of_its_xbf(self) -> None:
        _fresh("xbf", "export")
        with mock.patch.object(api, "export", return_value=["copy"]) as export:
            self.assertEqual(["copy"], cad.export("arm.xbf", "copy.xbf"))
        export.assert_called_once_with("arm.xbf", "copy.xbf")
        _fresh("xbf", "export")

    def test_the_callable_forms_still_work_and_name_save_and_export(self) -> None:
        with mock.patch.object(api, "hand_over", return_value="handle"), \
                mock.patch.object(api, "write_shape", return_value=Path("plate.step")), Said(self) as caught:
            self.assertEqual("handle", cad.xbf(self.SHAPE, "plate.xbf"))
            self.assertEqual("handle", cad.xbf(self.SHAPE, name="plate"))
            self.assertEqual(Path("plate.step"), cad.step(self.SHAPE, "plate.step"))
        self.assertEqual(["cad.xbf(shape, ...) is deprecated; use cad.save(shape, 'part.xbf')",
                          "cad.step(shape, ...) is deprecated; use cad.export(shape, 'part.step')"],
                         _deprecations(caught))

    def test_dfm_checks_a_live_shape_in_this_process_as_the_integration_s_check_did(self) -> None:
        """``cad.dfm(shape, ...)``: the build123d integration's check of a live shape, in the caller's process, given
        the same options and flags; nothing of the engine asked. Anything else that is no file nor handle is refused,
        naming a shape among what the verb takes."""
        from cad.build123d import _dfm_check

        with mock.patch.object(_dfm_check, "dfm", return_value="checked") as checked, \
                mock.patch.object(api, "check", side_effect=AssertionError("asked the engine")):
            self.assertEqual("checked", cad.dfm(LIVE, process="molding", pull="z", candidates=True, strict=True))
            self.assertEqual("checked", cad.dfm(LIVE))
        self.assertEqual([mock.call(LIVE, process="molding", pull="z", candidates=True, strict=True), mock.call(LIVE)],
                         checked.call_args_list)
        with self.assertRaises(TypeError) as refused:
            cad.dfm(self.SHAPE)
        self.assertEqual("cad.dfm takes a model's handle, or a .xbf, .step, .stp, .stl, .glb, .3mf or .dxf file, or a "
                         "build123d shape, not object", str(refused.exception))
        with self.assertRaisesRegex(TypeError, r"not Part; a shape is saved as a model by cad.save\(shape, "
                                               r"'part.xbf'\)"):
            cad.inspect(LIVE)

    def test_the_integration_s_check_is_the_verb_s_earlier_spelling_and_says_so_once(self) -> None:
        """``cad.build123d.dfm``: kept out of its namespace's names, one object at every lookup, running what it ran
        (``_dfm_check.dfm``) and saying once, at the line that called it, that ``cad.dfm`` does it now; nothing where
        the switch is off."""
        import cad.build123d
        from cad.build123d import _dfm_check

        self.assertNotIn("dfm", cad.build123d.__all__)
        alias = cad.build123d.dfm
        self.assertIs(alias, cad.build123d.dfm)
        self.assertEqual(("dfm", "cad.build123d"), (alias.__name__, alias.__module__))
        with mock.patch.object(_dfm_check, "dfm", return_value="checked") as checked, Said(self) as caught:
            self.assertEqual("checked", alias(LIVE, process="cnc", tools=[3, 6]))
            alias(LIVE)
        self.assertEqual([mock.call(LIVE, process="cnc", tools=[3, 6]), mock.call(LIVE)], checked.call_args_list)
        self.assertEqual(["cad.build123d.dfm is deprecated; use cad.dfm"], _deprecations(caught))
        self.assertEqual(Path(__file__).name, Path(caught[0].filename).name, "the line that spelled it")
        with mock.patch.object(_dfm_check, "dfm"), mock.patch.object(aliases, "SPELLINGS_WARN", False), \
                Said(self) as caught:
            alias(LIVE)
        self.assertEqual([], _deprecations(caught))

    def test_the_decorators_and_the_readers_say_nothing(self) -> None:
        with Said(self) as caught:
            def arm():
                return None

            cad.xbf(arm)
            cad.xbf("XBF/arm.xbf")
            cad.step("STEP/arm.step")
            cad.step()
            self.assertTrue(callable(cad.xbf.read) and callable(cad.step.read))
        self.assertEqual([], _deprecations(caught))


if __name__ == "__main__":
    unittest.main()
