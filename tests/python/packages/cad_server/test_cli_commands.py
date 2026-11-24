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
import tempfile
import unittest
from pathlib import Path

from tests.python.support.agent_apps import a_home_of_its_own
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
    "kicad_pcb": ("export", "snapshot", "inspect", "drc"),
    "kicad_sch": ("export", "snapshot", "inspect", "erc"),
}
COMMANDS = ("serve", "status", "stop", "delete", "server", "mcp", "run", "requirement", "doctor", "cache", "setup",
            "viewer", "telemetry", "update", "plugin")
# Run, never listed by `cad --help`: the bridge's (0.10.0 to 0.11.11's skill text and updaters), the commands for
# programs rather than people, and `xbf`, which the skill text of releases up to 0.11.17 says where `cad model` takes
# the .xbf file now.
UNLISTED = ("status", "stop", "setup", "serve", "requirement", "xbf")


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

    def test_help_lists_the_commands_a_person_uses_and_the_unlisted_still_run(self) -> None:
        self.assertEqual(sorted(UNLISTED), sorted(cli._UNLISTED))  # noqa: SLF001 - the table IS the subject
        code, said, _ = _run(["--help"])
        self.assertEqual(0, code)
        listed = {line.split()[0] for line in said.split("\ncommands:\n", 1)[1].split("\n\n", 1)[0].splitlines()}
        self.assertEqual(listed, set(COMMANDS) - set(UNLISTED))
        self.assertIn("mcp", listed)
        for argv in (["serve", "--help"], ["requirement", "--help"]):
            with self.subTest(argv=argv):
                self.assertEqual(_run(argv)[0], 0, "unlisted, and parsed as ever")

    def test_the_switches_are_update_auto_and_the_old_spellings_are_gone(self) -> None:
        """``cad update auto``, ``cad plugin install`` and ``cad plugin update [auto]``; ``cad auto-update`` and ``cad
        plugin auto-update`` answer as commands that never existed (no release had them), and ``cad plugin install``
        takes no options. Only its help and its usage errors are asked here: the command itself changes the agent apps
        of the computer it runs on (``tests/python/packages/cad_server/plugin`` runs it on a computer of its own). So
        that a parser that one day took one of these lines would not run it on this one, they are asked in a home of
        their own, with nothing on PATH."""
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        root = Path(scratch.name).resolve()
        (root / "bin").mkdir()
        a_home_of_its_own(self, root / "home", root / "bin")
        for argv, usage in ((["update", "--help"], "usage: cad update [-h] [--major]"),
                            (["update", "auto", "--help"], "usage: cad update auto [-h] [{status,on,off}]"),
                            (["plugin", "install", "--help"], "usage: cad plugin install [-h]"),
                            (["plugin", "update", "--help"], "usage: cad plugin update [-h] [auto [{status,on,off}]]"),
                            (["plugin", "update", "auto", "--help"],
                             "usage: cad plugin update auto [-h] [{status,on,off}]")):
            with self.subTest(argv=argv):
                code, said, _ = _run(argv)
                self.assertEqual((code, said.splitlines()[0]), (0, usage))
        for argv in (["auto-update"], ["auto-update", "on"], ["plugin", "install", "--force"],
                     ["plugin", "install", "claude"], ["plugin", "auto-update", "on"],
                     ["update", "auto", "maybe"], ["update", "--major", "auto"], ["update", "auto", "--major"]):
            with self.subTest(argv=argv):
                self.assertEqual(_run(argv)[0], 2)

    def test_help_groups_the_commands_by_type(self) -> None:
        code, said, _ = _run(["--help"])
        self.assertEqual(0, code)
        self.assertIn("document types, the files cad shows (cad <type> <operation> FILE):", said)
        self.assertRegex(said, r"\n  srdf +snapshot, validate +SRDF: \.srdf\n")
        self.assertRegex(said, r"\n  model +export, snapshot, inspect, dfm, interference, solve, ranges +model: a document id, "
                               r"held in memory, or an \.xbf file\n")
        # The xbf type's own command is run and never listed (the 30 days a command the skills used is kept).
        types = said.split("document types, the files cad shows", 1)[1].split("\n\n", 1)[0]
        self.assertEqual([line.split()[0] for line in types.splitlines()[1:]],
                         [name for name in TYPES if name not in UNLISTED])
        code, said, _ = _run(["xbf", "--help"])
        self.assertEqual((code, said.splitlines()[0]), (0, "usage: cad xbf <operation> FILE [options]"))
        code, said, _ = _run(["model", "--help"])
        self.assertEqual((code, said.splitlines()[0]), (0, "usage: cad model <operation> ID|FILE.xbf [options]"))
        self.assertIn("cad model <operation> FILE.xbf takes a model saved as a file, read as the file it is, never as "
                      "the model the engine holds (export, snapshot, inspect, dfm, interference, solve, ranges).", said)
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
        """``cad model`` takes a model's document id and, of files, only the one a model is saved as; a file's type
        takes its file and no id."""
        ident = "0b4c5f1e-1a2b-4c3d-8e9f-0123456789ab"
        code, _, err = _run(["step", "export", ident, "arm.glb"])
        self.assertEqual(2, code)
        self.assertIn(f"{ident} is a model's document id, not a .step file: use cad model export", err)
        code, _, err = _run(["model", "snapshot", "arm.step", "arm.png"])
        self.assertEqual(2, code)
        self.assertIn("arm.step is a step, not a model: use cad step snapshot", err)
        code, _, err = _run(["model", "inspect", "arm"])
        self.assertEqual((code, err), (2, "cad model inspect: cad model takes a model's document id (cad run SCRIPT.py "
                                          "prints it) or an .xbf file, not 'arm'\n"))
        # An .xbf given to another type's command is sent to the one that takes it, which is `cad model`.
        code, _, err = _run(["step", "export", "arm.xbf", "arm.glb"])
        self.assertEqual((code, err), (2, "cad step export: arm.xbf is a xbf, not a step: use cad model export\n"))
        code, _, err = _run(["mujoco", "check", "arm.xbf"])
        self.assertEqual((code, err), (2, "cad mujoco check: arm.xbf is a xbf, not a file cad mujoco check takes (.xml "
                                          "or .mjcf): use cad model dfm\n"))
        # A mesh's export meshes nothing: its parser has no --tolerance or --angle.
        for flag, value in (("--tolerance", "0.01"), ("--angle", "5")):
            err = io.StringIO()
            with contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as refused:
                cli.main(["stl", "export", "part.stl", "part.glb", flag, value])
            self.assertEqual(2, refused.exception.code)
            self.assertIn(f"unrecognized arguments: {flag}", err.getvalue())

    def test_cad_model_runs_the_xbf_s_operation_for_a_model_saved_as_a_file(self) -> None:
        """``cad model <operation> FILE.xbf`` is the xbf type's operation of that name, given the same command line
        (``document_types._or_saved``), for every operation an xbf has: so it writes, says and exits as ``cad xbf
        <operation> FILE.xbf`` does, which still answers. The file is told from a document id by its suffix, as
        the registry reads one, wherever the operation's parser reads its source."""
        from unittest import mock

        from cad_server.cli.document_types import OPERATIONS

        rest = {"export": ["out.xbf"], "snapshot": ["out.png"], "inspect": ["--query", "structure"],
                "dfm": ["--pull", "-z"]}
        for operation in TYPES["xbf"]:
            ran: list[tuple[list[str], str]] = []

            def saved(argv: list[str], prog: str) -> int:
                ran.append((argv, prog))
                return 7

            for source in ("share/arm.xbf", "ARM.XBF", "share/arm.xbf#arm/face 1"):
                # Its options before the file too: the file is the parser's source, never the first word.
                argv = [*rest.get(operation, []), source] if operation in ("inspect", "dfm") else \
                    [source, *rest.get(operation, [])]
                with self.subTest(operation=operation, source=source), \
                        mock.patch.dict(OPERATIONS, {("xbf", operation): saved}):
                    self.assertEqual([_run(["model", operation, *argv])[0], _run(["xbf", operation, *argv])[0]], [7, 7])
                    self.assertEqual(ran, [(argv, f"cad model {operation}"), (argv, f"cad xbf {operation}")])
                    ran.clear()
            # And unpatched, the real operation's own refusal of a file that is not there: the same words, status
            # and JSON by either name.
            for flags in ([], ["--json"]):
                with self.subTest(operation=operation, flags=flags):
                    argv = ["no-such-file.xbf", *rest.get(operation, []), *flags]
                    code, out, err = _run(["model", operation, *argv])
                    self.assertEqual(code, 2)
                    self.assertEqual((code, out, err.replace(f"cad model {operation}", f"cad xbf {operation}")),
                                     _run(["xbf", operation, *argv]))
                    self.assertIn("no such file: no-such-file.xbf", out + err)

    def test_cad_model_reads_only_its_source_as_a_file_and_an_id_stays_the_model_s(self) -> None:
        """A destination is no source: ``cad model export ID out.xbf`` is the model's own export, of what the
        engine holds, however its destinations are spelled."""
        from unittest import mock

        from cad_server.cli.document_types import OPERATIONS

        ident = "0b4c5f1e-1a2b-4c3d-8e9f-0123456789ab"
        asked: list[tuple[str, list[str], str]] = []

        def answered(runner: object, args: object, prog: str) -> int:
            asked.append((args.source, args.destinations, prog))  # type: ignore[attr-defined]
            return 0

        with mock.patch("cad_server.engine.cli.answered", answered), \
                mock.patch.dict(OPERATIONS, {("xbf", "export"): lambda argv, prog: self.fail("the xbf's export ran")}):
            self.assertEqual(_run(["model", "export", ident, "share/arm.xbf"])[0], 0)
        self.assertEqual(asked, [(ident, ["share/arm.xbf"], "cad model export")])

    def test_an_operation_an_xbf_lacks_refuses_the_file_and_says_what_takes_it(self) -> None:
        """An operation ``model`` has and the xbf type has not (none today: the registry gives both the same) refuses
        an ``.xbf``, the command line's failure, naming the operations the file takes and what this one does."""
        from unittest import mock

        from cad_server.cli.document_types import OPERATIONS

        said = ("arm.xbf is an .xbf file, which has no ranges: cad model takes an .xbf file for export, snapshot, "
                "inspect, dfm, interference, solve, and cad model ranges a model's document id, which cad run "
                "SCRIPT.py prints")
        with mock.patch.dict(OPERATIONS):
            del OPERATIONS[("xbf", "ranges")]
            code, out, err = _run(["model", "ranges", "arm.xbf"])
            self.assertEqual((code, out), (2, ""))
            self.assertEqual(err.splitlines()[-1], f"cad model ranges: error: {said}")
            code, out, err = _run(["model", "ranges", "arm.xbf", "--json"])
            self.assertEqual((code, err, json.loads(out)), (2, "", {"ok": False, "error": said, "reason": "usage"}))

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
        self.assertEqual({"mujoco": "cad_server.cli.mujoco", "orcaslicer": "cad_server.cli.orcaslicer"},
                         cli.INTEGRATION_COMMANDS)
        self.assertFalse(set(cli.INTEGRATION_COMMANDS) & set(cli.TYPE_COMMANDS), "a name is a type's or an integration's")
        self.assertEqual(("mujoco check", ["arm.xml"]), cli.resolve(["mujoco", "check", "arm.xml"]))
        self.assertIsNone(cli.resolve(["mujoco", "validate", "arm.xml"]))
        code, said, _ = _run(["--help"])
        self.assertEqual(0, code)
        self.assertIn("integrations, for a tool's own files cad checks or writes and does not show (cad <integration> "
                      "<operation> [FILE]):\n  mujoco  check  compile a MuJoCo model", said)
        # A deprecated integration's commands still run (the 30 days a command the skills used is kept) and are
        # no longer listed: `cad orcaslicer`, deprecated (a project saved from OrcaSlicer's app slices as it is).
        self.assertNotIn("orcaslicer", said.split("integrations, for a tool's own files", 1)[1])
        code, said, _ = _run(["mujoco", "--help"])
        self.assertEqual(0, code)
        self.assertIn("usage: cad mujoco <operation> FILE [options]", said)
        self.assertIn("operations (on .xml, .mjcf):\n  check  ", said)
        # MJCF was never a document type's command: the old spelling is an unknown command, the new one named.
        code, _, err = _run(["mjcf", "validate", str(self.model)])
        self.assertEqual((code, err), (2, "cad: unknown command 'mjcf' (did you mean 'mujoco'?); 'cad --help' lists the "
                                          "commands\n"))

    def test_a_deprecated_integration_still_runs_and_says_so_once_on_stderr(self) -> None:
        line = "cad orcaslicer: deprecated and will be removed: "
        with tempfile.TemporaryDirectory() as folder:
            _, _, err = _run(["orcaslicer", "presets", "machine", "--profiles", folder])
            self.assertEqual(err.count(line), 1, err)
            # A program's reply stays one document: under --json nothing is said beside it.
            _, _, err = _run(["orcaslicer", "presets", "machine", "--profiles", folder, "--json"])
            self.assertNotIn(line, err)

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


# What `cad orcaslicer ...` runs, in a process of its own: the preset folders are the test's alone (the app's own
# profiles left out), and it says what it loaded of cad's and whether the engine's folder was made.
_ORCASLICER = """
import json, os, sys
before = set(sys.modules)
from cad.orcaslicer import _presets
_presets.app_profiles = lambda: []
import cad_server.cli as cli
code = cli.main(sys.argv[1:])
loaded = sorted(name for name in set(sys.modules) - before if name.split(".")[0] in ("OCP", "build123d", "socket")
                or name.startswith("cad.engine"))
print(json.dumps({"code": code, "loaded": loaded, "engine": os.path.exists(os.environ["CAD_ENGINE_DIR"])}),
      file=sys.stderr)
"""


class OrcaslicerCommands(unittest.TestCase):
    """``cad orcaslicer presets`` and ``complete``: an integration's operations on its tool's own files found by
    name, no FILE. The integration has no extra, so they run in the command's own process: no engine, no kernel,
    no environment made."""

    def test_the_presets_are_listed_and_written_complete_in_the_command_s_own_process(self) -> None:
        import os
        import subprocess
        import sys
        import tempfile
        from pathlib import Path

        from tests.python.support.paths import SOURCE_PATH

        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            for relative, preset in (
                    ("Acme/machine/acme.json", {"type": "machine", "name": "Acme One 0.4 nozzle", "from": "system",
                                                "instantiation": "true", "bed_shape": "0x0,200x200"}),
                    ("Acme/process/fine.json", {"type": "process", "name": "0.20mm @Acme", "from": "system",
                                                "instantiation": "true"}),
                    ("Acme/filament/pla.json", {"type": "filament", "name": "Generic PLA", "from": "system",
                                                "instantiation": "true"})):
                (root / "profiles" / relative).parent.mkdir(parents=True, exist_ok=True)
                (root / "profiles" / relative).write_text(json.dumps(preset), encoding="utf-8")
            (root / "home").mkdir()
            env = {key: value for key, value in os.environ.items() if key not in ("APPDATA", "XDG_CONFIG_HOME")}
            env.update(PYTHONPATH=SOURCE_PATH, HOME=str(root / "home"), USERPROFILE=str(root / "home"),
                       CAD_ENGINE_DIR=str(root / "engine"), CAD_STATE_DIR=str(root / "state"),
                       CAD_CACHE_DIR=str(root / "cache"), CAD_UPDATE_CHECK="0", CAD_API_URL="http://127.0.0.1:9")

            def cad(*argv: str) -> tuple[str, dict]:
                done = subprocess.run([sys.executable, "-c", _ORCASLICER, "orcaslicer", *argv,
                                       "--profiles", str(root / "profiles")],
                                      capture_output=True, text=True, encoding="utf-8", env=env, cwd=root, timeout=60)
                return done.stdout, json.loads(done.stderr.strip().splitlines()[-1])

            said, ran = cad("presets", "machine", "--match", "ACME")
            self.assertEqual(("Acme One 0.4 nozzle\n", {"code": 0, "loaded": [], "engine": False}), (said, ran))
            said, ran = cad("complete", "--printer", "Acme One 0.4 nozzle", "--process", "0.20mm @Acme",
                            "--filament", "Generic PLA", "--out", "presets", "--json")
            self.assertEqual({"code": 0, "loaded": [], "engine": False}, ran)
            out = (root / "presets").resolve()
            self.assertEqual({"printer": str(out / "printer.json"), "process": str(out / "process.json"),
                              "filaments": [str(out / "filament-1.json")]}, json.loads(said))
            process = json.loads((out / "process.json").read_text(encoding="utf-8"))
            self.assertEqual((["Acme One 0.4 nozzle"], "User"), (process["compatible_printers"], process["from"]))
        code, said, _ = _run(["orcaslicer", "--help"])
        self.assertEqual(0, code)
        self.assertIn("usage: cad orcaslicer <operation> [options]", said)
        self.assertIn("operations:\n  presets   ", said)
        code, _, err = _run(["orcaslicer", "complete", "--process", "x", "--filament", "y"])
        self.assertEqual(2, code)
        self.assertIn("the following arguments are required: --printer", err)


if __name__ == "__main__":
    unittest.main()
