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
    "model": ("export", "snapshot", "inspect", "dfm", "plan"),
    "xbf": ("export", "snapshot", "inspect", "dfm", "plan"),
    "step": ("export", "snapshot", "inspect", "dfm", "plan"),
    "stl": ("export", "snapshot", "dfm"),
    "glb": ("export", "snapshot", "inspect", "dfm"),
    "threemf": ("export", "snapshot", "dfm"),
    "dxf": ("snapshot",),
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
        self.assertIn("document types (cad <type> <operation> FILE):", said)
        self.assertRegex(said, r"\n  srdf +snapshot, validate +SRDF: \.srdf\n")
        self.assertRegex(said, r"\n  model +export, snapshot, inspect, dfm, plan +model: a document id, held in memory\n")
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

        rest = {"export": ["out.step"], "snapshot": ["out.png"], "dfm": ["--process", "printing"]}
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
                self.assertEqual(json.loads(out), {"ok": False, "error": f"no such file: {missing}", "reason": "not_found"})
        code, _, err = _run(["urdf", "validate", "robot.xml"])
        self.assertEqual((code, err), (2, "cad urdf validate: robot.xml is not a urdf file: cad urdf takes .urdf\n"))

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
        # A mesh's export meshes nothing: its parser has no --tolerance.
        err = io.StringIO()
        with contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as refused:
            cli.main(["stl", "export", "part.stl", "part.glb", "--tolerance", "0.01"])
        self.assertEqual(2, refused.exception.code)
        self.assertIn("unrecognized arguments: --tolerance", err.getvalue())

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
            "cad step has no operation 'exprt' (did you mean 'export'?); it has export, snapshot, inspect, dfm, plan; "
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


if __name__ == "__main__":
    unittest.main()
