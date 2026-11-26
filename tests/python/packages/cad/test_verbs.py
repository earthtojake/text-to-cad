"""The library's verbs (``cad.export``, ``cad.inspect``, ``cad.snapshot``, ``cad.dfm``, ``cad.fea``, ``cad.save``) and
the earlier spellings they replace: each type's operations (``cad.xbf.export``, ``cad.stl.dfm``,
``cad.kicad_pcb.drc``, ...) and the file types' callable forms (``xbf(shape, path)``, ``step(shape, path)``), which
answer as their verbs do and say once that they are deprecated, naming the verb -- where a program calls them, never
where the library or the server calls its own (``cad._internal.aliases.spelled``, the one switch).

Nothing here builds or needs the CAD kernel: the engine's verbs and the writers are stood in for where a call
would reach them.
"""

from __future__ import annotations

import tempfile
import unittest
import warnings
from pathlib import Path
from unittest import mock

import cad
from cad._internal import aliases, verbs
from cad.engine import api


def _fresh(document_type: str, name: str) -> None:
    """Forget a type's alias and the operation it wraps, so the next lookup binds what a test stands in."""
    verbs._MADE.pop((document_type, name), None)
    getattr(cad, document_type).__dict__.pop(name, None)


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
        with self.assertRaisesRegex(TypeError, "give the one file to write"):
            cad.export(self.SHAPE)
        with self.assertRaisesRegex(TypeError, "takes no tolerance or angle"):
            cad.export(self.SHAPE, "part.step", tolerance=0.02)

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
