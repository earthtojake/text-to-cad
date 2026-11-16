"""The ``cad`` command's table, pinned: every document type's operations and every other command.

The shape is ``cad <document_type> <operation> <file>``, one id per type everywhere (the registry,
``cad.registry``), one set of operation names every type shares; the commands that are no
document's are the engine's process control, ``run`` and the installation's. A command added,
renamed or taken out is a change to what every agent reads, made here on purpose. The old
spellings are gone, a hard cutover: each answers as a command that never existed does.
"""

from __future__ import annotations

import contextlib
import io
import json
import unittest

from tests.python.support.paths import add_sources

add_sources()

from cad.registry import DOCUMENT_TYPES  # noqa: E402

import cad_server.cli as cli  # noqa: E402
from cad_server.cli.document_types import operations_of, type_main  # noqa: E402

TYPES = {
    "model": ("export", "snapshot", "inspect", "dfm", "interference", "solve", "ranges"),
    "xbf": ("export", "snapshot", "inspect", "dfm", "interference", "solve", "ranges"),
    "step": ("export", "snapshot", "inspect", "dfm", "interference", "solve", "ranges"),
    "stl": ("export", "snapshot", "dfm"),
    "glb": ("export", "snapshot", "inspect", "dfm"),
    "threemf": ("export", "snapshot", "dfm"),
    "dxf": ("snapshot", "dfm"),
    "urdf": ("snapshot", "validate"),
    "srdf": ("snapshot", "validate"),
    "sdf": ("snapshot", "validate"),
    "kicad_pcb": ("export", "snapshot", "inspect", "drc"),
    "kicad_sch": ("export", "snapshot", "inspect", "erc"),
}
COMMANDS = ("serve", "status", "stop", "delete", "server", "run", "requirement", "doctor", "setup", "update", "update auto", "uninstall", "plugin",
            "viewer", "telemetry")


def _run(argv: list[str]) -> tuple[int, str, str]:
    """A command line run as the ``cad`` command runs it: its exit status, its stdout and its stderr (a
    command line its parser refuses exits, as argparse's do)."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = cli.main(argv)
        except SystemExit as exited:
            code = exited.code
    return code, out.getvalue(), err.getvalue()


class TheCommandTable(unittest.TestCase):
    def test_the_table_is_pinned(self) -> None:
        self.assertEqual(TYPES, {name: operations_of(name) for name in DOCUMENT_TYPES})
        self.assertEqual(sorted(TYPES), sorted(cli.TYPE_COMMANDS))
        self.assertEqual(sorted(COMMANDS), sorted(cli._COMMANDS))  # noqa: SLF001 - the table IS the subject
        for name, module in cli.TYPE_COMMANDS.items():
            self.assertEqual(f"cad_server.cli.{name}", module)

    def test_help_groups_the_commands_by_type(self) -> None:
        code, said, _ = _run(["--help"])
        self.assertEqual(0, code)
        self.assertIn("document types, the files cad shows (cad <type> <operation> FILE):", said)
        self.assertRegex(said, r"\n  srdf +snapshot, validate +SRDF: \.srdf\n")
        self.assertRegex(said, r"\n  model +export, snapshot, inspect, dfm, interference, solve, ranges +model: a document id, "
                               r"held in memory\n")
        code, said, _ = _run(["step", "--help"])
        self.assertEqual(0, code)
        self.assertIn("operations:\n  export ", said)
        self.assertIn("(.step, .stp)", said)

    def test_a_file_of_another_type_is_refused_by_name(self) -> None:
        code, _, err = _run(["stl", "snapshot", "part.glb", "out.png"])
        self.assertEqual(2, code)
        self.assertIn("part.glb is a glb, not a stl: use cad glb snapshot", err)
        # The same failure with --json: the same status, its one document on stdout and nothing else.
        code, said, err = _run(["urdf", "validate", "robot.srdf", "--json"])
        self.assertEqual(2, code)
        self.assertEqual({"ok": False, "error": "robot.srdf is a srdf, not a urdf: use cad srdf validate",
                          "reason": "wrong_type"}, json.loads(said))
        self.assertEqual("", err)

    def test_a_file_that_is_not_there_is_the_same_failure_for_every_type(self) -> None:
        """Every operation of every file's type refuses a file that is not there before anything runs, alike:
        ``not_found``, exit 2, with ``--json`` and without; and a file of no type as ``wrong_type``."""
        from cad.registry import DOCUMENT_TYPES as TYPES_TABLE
        from cad_server.cli.document_types import OPERATIONS

        rest = {"export": ["out.step"], "snapshot": ["out.png"], "dfm": []}
        for document_type, operation in sorted(OPERATIONS):
            entry = TYPES_TABLE[document_type]
            if not entry.has_file:
                continue
            missing = f"no-such-file{entry.extensions[0]}"
            extra = (["--to", "pdf", "-o", "out"] if document_type.startswith("kicad_") and operation == "export"
                     else rest.get(operation, []))
            with self.subTest(command=f"{document_type} {operation}"):
                code, out, err = _run([document_type, operation, missing, *extra])
                self.assertEqual((code, out, err), (2, "", f"cad {document_type} {operation}: no such file: {missing}\n"))
                code, out, err = _run([document_type, operation, missing, *extra, "--json"])
                self.assertEqual((code, err), (2, ""))
                # a manufacturing check's answers all carry the state, a command-line mistake's too
                state = {"status": "usage"} if operation == "dfm" else {}
                self.assertEqual(json.loads(out),
                                 {"ok": False, "error": f"no such file: {missing}", "reason": "not_found", **state})
        code, _, err = _run(["urdf", "validate", "robot.txt"])
        self.assertEqual((code, err), (2, "cad urdf validate: robot.txt is not a urdf file: cad urdf takes .urdf\n"))
        # An .xml is no document type: a MuJoCo model's file, which its integration's command takes.
        code, _, err = _run(["urdf", "validate", "robot.xml"])
        self.assertEqual((code, err), (2, "cad urdf validate: robot.xml is not a urdf file: cad urdf takes .urdf "
                                          "(cad mujoco check takes .xml and .mjcf)\n"))

    def test_a_file_whose_path_holds_a_hash_is_its_type_s(self) -> None:
        """A folder or a file named with a '#' (project#1) is the file whole, as ``cad.engine.addresses.parts``
        reads a ``FILE#REF``: every operation takes it, where each once refused it as no file of its type."""
        import tempfile
        from pathlib import Path

        from cad_server.cli.document_types import _refuse_other_type

        with tempfile.TemporaryDirectory() as folder:
            part = Path(folder) / "project#1" / "bracket#2.step"
            part.parent.mkdir()
            part.write_text("ISO-10303-21;", encoding="utf-8")
            for operation in ("snapshot", "export", "inspect"):
                _refuse_other_type("step", operation, str(part))
                _refuse_other_type("step", operation, f"{part}#arm")

    def test_a_script_where_a_document_is_wanted_says_cad_run_builds_it(self) -> None:
        """A model's script is never a source: the refusal says the command that builds it and prints its id,
        the skills' own form, and the help says the same -- never ``python SCRIPT.py``."""
        for argv, said in (
                (["model", "inspect", "part.py"], "part.py is a model's script, not a document id: `cad run part.py` "
                                                  "builds its models and prints each one's id, which cad model inspect "
                                                  "takes"),
                (["step", "snapshot", "src/my part.py::part", "out.png"],
                 "src/my part.py::part is a model's script, not a step file: `cad run 'src/my part.py'` builds its "
                 "models and prints each one's id, which cad model snapshot takes"),
                (["urdf", "validate", "robot.py"], "robot.py is a model's script, not a urdf file: `cad run robot.py` "
                                                   "builds its models and prints each one's id")):
            with self.subTest(argv=argv):
                code, out, err = _run(argv)
                self.assertEqual((code, out), (2, ""))
                self.assertEqual(err, f"cad {argv[0]} {argv[1]}: {said}\n")
        # And the commands that take a document but are no type's: the document it serves, the page it opens.
        for argv, said in ((["serve", "part.py"], "part.py is no document: serve reads an .xbf, a .step or a document "
                                                  "id; run `cad run part.py` first, then serve its document by id"),
                           (["viewer", "part.py"], "part.py is a model's script, not a CAD file: `cad run part.py` "
                                                   "builds its models and prints each one's page")):
            with self.subTest(argv=argv):
                code, out, err = _run(argv)
                self.assertEqual((code, out, err), (2, "", f"cad {argv[0]}: {said}\n"))
        from cad_server.cli.document_types import OPERATIONS, build_parser, type_usage

        helps = [" ".join(text.split()) for text in  # each help as words: argparse wraps its lines
                 [type_usage(name) for name in TYPES] + [build_parser(*key).format_help() for key in sorted(OPERATIONS)]]
        self.assertEqual([text for text in helps if "python SCRIPT" in text], [])
        self.assertIn("a model's document id, which cad run SCRIPT.py prints",
                      " ".join(build_parser("model", "export").format_help().split()))

    def test_a_model_is_its_id_and_a_file_is_its_types(self) -> None:
        """``cad model`` takes a model's document id and no file; a file's type takes its file and no id."""
        ident = "0b4c5f1e-1a2b-4c3d-8e9f-0123456789ab"
        code, _, err = _run(["xbf", "export", ident, "arm.step"])
        self.assertEqual(2, code)
        self.assertIn(f"{ident} is a model's document id, not a .xbf file: use cad model export", err)
        code, _, err = _run(["model", "snapshot", "arm.xbf", "arm.png"])
        self.assertEqual(2, code)
        self.assertIn("arm.xbf is a xbf, not a model: use cad xbf snapshot", err)
        code, _, err = _run(["model", "inspect", "arm"])
        self.assertEqual(2, code)
        self.assertIn("cad model takes a model's document id", err)
        # A mesh's export meshes nothing: its parser has no --tolerance or --angle.
        for flag, value in (("--tolerance", "0.01"), ("--angle", "5")):
            err = io.StringIO()
            with contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as refused:
                cli.main(["stl", "export", "part.stl", "part.glb", flag, value])
            self.assertEqual(2, refused.exception.code)
            self.assertIn(f"unrecognized arguments: {flag}", err.getvalue())

    def test_a_types_own_option_before_its_file_is_no_file(self) -> None:
        """``--urdf robot.urdf`` is srdf validate's own option, wherever it stands: the file it validates is
        the one the parser takes as its file, never the first word without a dash."""
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as folder:
            urdf, srdf = Path(folder) / "robot.urdf", Path(folder) / "robot.srdf"
            urdf.write_text('<robot name="r"><link name="a"/></robot>', encoding="utf-8")
            srdf.write_text('<robot name="r"><group name="arm"><link name="a"/></group></robot>', encoding="utf-8")
            for argv in (["srdf", "validate", "--urdf", str(urdf), str(srdf)],
                         ["srdf", "validate", str(srdf), "--urdf", str(urdf)]):
                with self.subTest(argv=argv):
                    code, said, err = _run([*argv, "--json"])
                    self.assertNotIn("is a urdf, not a srdf", said + err)
                    self.assertIn('"path"', said)
            code, said, _ = _run(["srdf", "validate", "--urdf", str(urdf), str(urdf), "--json"])
            self.assertEqual(2, code)
            self.assertIn("is a urdf, not a srdf", said)

    def test_an_operation_a_type_lacks_names_the_ones_it_has(self) -> None:
        # Said as an unknown command is: one line, at most one suggestion, and where the operations are told,
        # never the type's whole help after it; a type named with no operation at all shows its help.
        code, out, err = _run(["stl", "inspect", "part.stl"])
        self.assertEqual((code, out), (2, ""))
        self.assertEqual(err, "cad stl: cad stl has no operation 'inspect'; it has export, snapshot, dfm; "
                              "'cad stl --help' says what each does\n")
        code, out, err = _run(["step", "exprt", "--json"])
        self.assertEqual((code, err), (2, ""))
        self.assertEqual(json.loads(out), {"ok": False, "reason": "usage", "error": (
            "cad step has no operation 'exprt' (did you mean 'export'?); it has export, snapshot, inspect, dfm, interference, "
            "solve, ranges; "
            "'cad step --help' says what each does")})
        self.assertEqual(2, type_main("dxf", ["export", "a.dxf"]))
        code, out, err = _run(["stl"])
        self.assertEqual((code, out), (2, ""))
        self.assertTrue(err.startswith("cad stl: cad stl needs an operation\n\nusage: cad stl <operation> FILE"), err)

    def test_the_old_spellings_are_commands_that_never_existed(self) -> None:
        for argv in (["export", "a.xbf", "a.step"], ["snapshot", "a.xbf", "a.png"], ["inspect", "a.xbf"]):
            with self.subTest(argv=argv):
                code, _, err = _run(argv)
                self.assertEqual(2, code)
                self.assertIn(f"cad: unknown command {argv[0]!r}", err)
        # The operations named for what they do: the old shared ``check`` is an operation no type has.
        for argv in (["urdf", "check", "robot.urdf"], ["stl", "check", "part.stl"], ["kicad_pcb", "check", "b.kicad_pcb"]):
            with self.subTest(argv=argv):
                code, _, err = _run(argv)
                self.assertEqual(2, code)
                self.assertIn(f"cad {argv[0]} has no operation 'check'; it has ", err)


_MJCF = ('<mujoco model="arm"><worldbody><body name="a"><joint name="j" type="hinge" range="-90 90"/>'
         '<geom type="box" size=".1 .1 .1"/></body></worldbody></mujoco>')


class MujocoCheck(unittest.TestCase):
    """``cad mujoco check``: an integration's operation on a file of its tool's own, which is no document type
    (``cad_server.cli.integrations``). The generated mirror of ``cad.mujoco.check``, run here where this
    environment holds mujoco, else in the environment of ``cad[mujoco]``."""

    def setUp(self) -> None:
        import tempfile
        from pathlib import Path

        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.model = Path(folder.name) / "arm.xml"
        self.model.write_text(_MJCF, encoding="utf-8")

    def test_the_command_table_names_the_integration_apart_from_the_types(self) -> None:
        self.assertEqual({"mujoco": "cad_server.cli.mujoco"}, cli.INTEGRATION_COMMANDS)
        self.assertFalse(set(cli.INTEGRATION_COMMANDS) & set(cli.TYPE_COMMANDS), "a name is a type's or an integration's")
        self.assertEqual(("mujoco check", ["arm.xml"]), cli.resolve(["mujoco", "check", "arm.xml"]))
        self.assertIsNone(cli.resolve(["mujoco", "validate", "arm.xml"]))
        code, said, _ = _run(["--help"])
        self.assertEqual(0, code)
        self.assertIn("integrations, for a tool's own file cad checks and does not show (cad <integration> <operation> "
                      "FILE):\n  mujoco  check  ", said)
        code, said, _ = _run(["mujoco", "--help"])
        self.assertEqual(0, code)
        self.assertIn("usage: cad mujoco <operation> FILE [options]", said)
        self.assertIn("operations (on .xml, .mjcf):\n  check  ", said)
        # MJCF was never a document type's command: the old spelling is an unknown command, the new one named.
        code, _, err = _run(["mjcf", "validate", str(self.model)])
        self.assertEqual((code, err), (2, "cad: unknown command 'mjcf' (did you mean 'mujoco'?); 'cad --help' lists the "
                                          "commands\n"))

    def test_the_parser_is_the_generated_one(self) -> None:
        from cad_server.cli.integrations import build_parser

        text = " ".join(build_parser("mujoco", "check").format_help().split())
        for option in ("--strict", "--verbose", "--json", "PATH"):
            self.assertIn(option, text)
        self.assertNotIn("--compile", text, "the check is MuJoCo's compile: there is no mode without it")

    def test_a_wrong_operation_a_wrong_file_and_a_missing_one_are_the_command_line_s(self) -> None:
        for argv, words in (
                (["mujoco"], "cad mujoco: cad mujoco needs an operation\n"),
                (["mujoco", "chek", "arm.xml"], "cad mujoco: cad mujoco has no operation 'chek' (did you mean 'check'?); "
                                                "it has check; 'cad mujoco --help' says what each does\n"),
                (["mujoco", "check", "arm.urdf"], "cad mujoco check: arm.urdf is a urdf, not a file cad mujoco check "
                                                  "takes (.xml or .mjcf): use cad urdf validate\n"),
                (["mujoco", "check", "notes.txt"], "cad mujoco check: notes.txt is not a file cad mujoco check takes: "
                                                   "it takes .xml or .mjcf\n"),
                (["mujoco", "check", "nowhere.xml"], "cad mujoco check: no such file: nowhere.xml\n")):
            with self.subTest(argv=argv):
                code, out, err = _run(argv)
                self.assertEqual((code, out), (2, ""))
                self.assertTrue(err.startswith(words), err)
        code, out, err = _run(["mujoco", "check", "nowhere.xml", "--json"])
        self.assertEqual((code, err), (2, ""))
        self.assertEqual(json.loads(out), {"ok": False, "error": "no such file: nowhere.xml", "reason": "not_found"})

    def test_without_mujoco_here_the_check_runs_in_its_environment(self) -> None:
        from unittest import mock

        from cad_server._internal import integration_env

        calls: list[tuple] = []

        def call(python, name, operation, args, kwargs):
            calls.append((python, name, operation, args, kwargs))
            return {"ok": True, "path": args[0], "summary": "OK elsewhere", "measurements": {"collisions": {"geoms": 1}},
                    "findings": [{"severity": "info", "code": "compiled", "message": "compiled by MuJoCo",
                                  "location": "arm.xml", "hint": None}]}

        with mock.patch.object(integration_env, "carries", lambda name: False), \
                mock.patch.object(integration_env, "environment", lambda name, told: f"/env/{name}/python"), \
                mock.patch.object(integration_env, "call", call):
            code, said, _ = _run(["mujoco", "check", str(self.model), "--strict", "--json"])
        self.assertEqual(0, code)
        answer = json.loads(said)
        self.assertEqual(("OK elsewhere", {"collisions": {"geoms": 1}}), (answer["summary"], answer["measurements"]))
        self.assertEqual([("/env/mujoco/python", "mujoco", "check", [str(self.model.resolve())], {"strict": True})], calls)


if __name__ == "__main__":
    unittest.main()
