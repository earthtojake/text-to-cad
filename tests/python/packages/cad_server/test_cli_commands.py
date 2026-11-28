"""The ``cad`` command's table: the verbs on a file, by the file's type (``cad export``, ``cad inspect``,
``cad snapshot``, ``cad dfm``, ``cad fea``), the integrations' operations on their tools' files, and the commands;
how each refuses a source it cannot take, by name and before anything runs.
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
from cad_server.cli.verbs import VERBS  # noqa: E402

#: The verbs each type takes, by the table's order: what ``cad --help`` says of it.
TYPES = {
    "xbf": ("export", "inspect", "snapshot", "dfm", "fea"),
    "step": ("export", "inspect", "snapshot", "dfm", "fea"),
    "stl": ("export", "snapshot", "dfm"),
    "glb": ("export", "inspect", "snapshot", "dfm"),
    "threemf": ("export", "snapshot", "dfm"),
    "dxf": ("snapshot", "dfm"),
    "urdf": ("inspect", "snapshot"),
    "srdf": ("inspect", "snapshot"),
    "kicad_pcb": ("export", "inspect", "snapshot"),
    "kicad_sch": ("export", "inspect", "snapshot"),
}
COMMANDS = ("export", "inspect", "snapshot", "dfm", "fea", "viewer", "server", "mcp", "run", "requirement", "doctor",
            "cache", "setup", "share", "import", "telemetry", "update", "plugin")
# Run, never listed by `cad --help`: the bridge's (0.10.0 to 0.11.11's updaters run `cad setup`), and the command
# for programs rather than people (`requirement`, whose output a program reads).
UNLISTED = ("setup", "requirement")


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
        from cad.registry import operation_for

        self.assertEqual(TYPES, {name: tuple(verb for verb in VERBS if operation_for(verb, name) is not None)
                                 for name in DOCUMENT_TYPES})
        self.assertEqual(sorted(COMMANDS), sorted(cli._COMMANDS))  # noqa: SLF001 - the table IS the subject
        self.assertEqual(VERBS, cli.VERB_COMMANDS)

    def test_help_lists_the_commands_a_person_uses_and_the_unlisted_still_run(self) -> None:
        self.assertEqual(sorted(UNLISTED), sorted(cli._UNLISTED))  # noqa: SLF001 - the table IS the subject
        code, said, _ = _run(["--help"])
        self.assertEqual(0, code)
        listed = {line.split()[0] for line in said.split("\ncommands:\n", 1)[1].split("\n\n", 1)[0].splitlines()}
        self.assertEqual(listed, set(COMMANDS) - set(UNLISTED) - set(VERBS))
        verbs = [line.split()[0] for line in said.split("its type by its suffix (cad <verb> FILE):\n", 1)[1]
                 .split("\n\n", 1)[0].splitlines()]
        self.assertEqual(verbs, list(VERBS))
        self.assertIn("mcp", listed)
        self.assertEqual(_run(["requirement", "--help"])[0], 0, "unlisted, and parsed as ever")

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
        for argv, usage in ((["update", "--help"], "usage: cad update [-h]"),
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
                     ["update", "auto", "maybe"], ["update", "--major"], ["update", "--major", "auto"],
                     ["update", "auto", "--major"]):
            with self.subTest(argv=argv):
                self.assertEqual(_run(argv)[0], 2)

    def test_help_says_the_verbs_and_the_files_each_takes(self) -> None:
        code, said, _ = _run(["--help"])
        self.assertEqual(0, code)
        self.assertIn("verbs, on a file, its type by its suffix (cad <verb> FILE):", said)
        self.assertRegex(said, r"\n  srdf +inspect, snapshot +SRDF: \.srdf\n")
        self.assertRegex(said, r"\n  xbf +export, inspect, snapshot, dfm, fea +XBF: a model's \.xbf file\n")
        types = said.split("the files they take, by document type:", 1)[1].split("\n\n", 1)[0]
        self.assertEqual([line.split()[0] for line in types.splitlines()[1:]], list(TYPES))
        code, said, _ = _run(["export", "--help"])
        self.assertEqual((code, said.splitlines()[0]),
                         (0, "usage: cad export SRC DST [--as KIND] [--tolerance MM] [--angle DEG] [--zero STATE] "
                             "[--json]"))
        # Its DST and --as are every type's: a KiCad file's folder and .zip, and the kinds they need named.
        said = " ".join(said.split())
        self.assertIn("or of a KiCad file a folder (ending in /, or one that is there: made when missing) or a .zip",
                      said)
        self.assertIn("a board's gerbers, drill, odb or pdf into a folder or a .zip, its pos or bom into a .csv", said)

    def test_a_verb_s_help_names_every_file_its_source_may_be(self) -> None:
        # `cad dfm --help` is every type's options in one: its source is every file the verb takes, not the first
        # type's alone (a model's .xbf), as its refusal of another file names them.
        from cad.registry import types_for
        from cad_server.cli.verbs import build_parser

        for verb in VERBS:
            with self.subTest(verb=verb):
                [source, *_rest] = build_parser(verb)._get_positional_actions()
                for document_type in types_for(verb):
                    for suffix in DOCUMENT_TYPES[document_type].extensions:
                        self.assertRegex(source.help, rf"{suffix}\b", f"cad {verb} --help names no {suffix}")
                code, said, _ = _run([verb, "--help"])
                self.assertEqual(code, 0)
                self.assertIn(" ".join(source.help.split()[:4]), " ".join(said.split()))
        [own, *_rest] = build_parser("dfm", ["part.xbf"])._get_positional_actions()
        self.assertIn("the .xbf file a model is saved as", own.help, "a file's own type's help is its own")

    def test_a_file_s_help_lists_every_option_its_type_takes_for_the_verb(self) -> None:
        """``cad <verb> FILE --help`` is the file's type's: each option a parser of that type's runs for the verb reads,
        a mode's too (``cad inspect FILE --interference``, ``--ranges``), which the file's help names without the flag."""
        import re

        from cad.registry import MODES, operation_for
        from cad_server.cli.document_types import build_parser as type_parser

        for document_type, verbs in TYPES.items():
            for verb in verbs:
                suffix = DOCUMENT_TYPES[document_type].extensions[0]
                with self.subTest(verb=verb, type=document_type):
                    code, said, err = _run([verb, f"no-such-file{suffix}", "--help"])
                    self.assertEqual((code, err), (0, ""))
                    taken = set()
                    for mode in (None, *(MODES if verb == "inspect" else ())):
                        operation = operation_for(verb, document_type, mode)
                        if operation is not None:
                            parser = type_parser(document_type, operation, f"cad {verb}")
                            taken |= {flag for action in parser._actions for flag in action.option_strings  # noqa: SLF001
                                      if flag.startswith("--")}
                    self.assertGreater(len(taken), 1, f"cad {verb} takes options of {document_type}")
                    for flag in sorted(taken):
                        self.assertRegex(said, rf"(?<![\w-]){re.escape(flag)}(?![\w-])",
                                         f"cad {verb} {suffix} --help does not list {flag}")
        # A B-rep's inspect says each mode's forms in its usage, and groups the options of each
        _, said, _ = _run(["inspect", "part.xbf", "--help"])
        self.assertIn("\n       cad inspect FILE --interference [--pose POSE]", said)
        self.assertIn("\nwith --ranges:\n", said)
        # and a mode's own help is that mode's alone
        _, said, _ = _run(["inspect", "part.xbf", "--ranges", "--help"])
        self.assertNotIn("--interference", said)

    def test_a_file_that_is_not_there_is_the_same_failure_for_every_type(self) -> None:
        """Every verb of every file's type refuses a file that is not there before anything runs, alike:
        ``not_found``, exit 2, with ``--json`` and without; and a file of no type as ``wrong_type``."""
        from cad.registry import DOCUMENT_TYPES as TYPES_TABLE, MODES, operation_for

        rest = {"export": ["out.step"], "snapshot": ["out.png"]}
        for document_type, verbs in TYPES.items():
            for verb in verbs:
                for mode in (None, *(MODES if verb == "inspect" else ())):
                    if mode is not None and operation_for(verb, document_type, mode) is None:
                        continue
                    missing = f"no-such-file{TYPES_TABLE[document_type].extensions[0]}"
                    extra = rest.get(verb, []) + ([f"--{mode}"] if mode else [])
                    with self.subTest(command=f"{verb} {document_type} {mode or ''}"):
                        code, out, err = _run([verb, missing, *extra])
                        self.assertEqual((code, out, err), (2, "", f"cad {verb}: no such file: {missing}\n"))
                        code, out, err = _run([verb, missing, *extra, "--json"])
                        self.assertEqual((code, err), (2, ""))
                        # a manufacturing check's answers all carry the state, a command-line mistake's too
                        state = {"status": "usage"} if verb == "dfm" else {}
                        self.assertEqual(json.loads(out),
                                         {"ok": False, "error": f"no such file: {missing}", "reason": "not_found",
                                          **state})
        code, _, err = _run(["inspect", "robot.txt"])
        self.assertEqual((code, err), (2, "cad inspect: robot.txt is not a file cad inspect takes: it takes .xbf, "
                                          ".step, .stp, .glb, .urdf, .srdf, .kicad_pcb or .kicad_sch\n"))
        # An .xml is no document type: a MuJoCo model's file, which its integration's command takes.
        code, _, err = _run(["inspect", "robot.xml"])
        self.assertEqual((code, err), (2, "cad inspect: robot.xml is not a file cad inspect takes: it takes .xbf, "
                                          ".step, .stp, .glb, .urdf, .srdf, .kicad_pcb or .kicad_sch (cad mujoco check "
                                          "takes .xml and .mjcf)\n"))

    def test_a_file_whose_path_holds_a_hash_is_its_type_s(self) -> None:
        """A folder or a file named with a '#' (project#1) is the file whole, as ``cad.engine.addresses.parts``
        reads a ``FILE#REF``: every operation takes it, where each once refused it as no file of its type."""
        from cad_server.cli.document_types import _refuse_other_type
        from cad_server.cli.verbs import resolve

        with tempfile.TemporaryDirectory() as folder:
            part = Path(folder) / "project#1" / "bracket#2.step"
            part.parent.mkdir()
            part.write_text("ISO-10303-21;", encoding="utf-8")
            for operation in ("snapshot", "export", "inspect"):
                _refuse_other_type("step", operation, str(part))
                _refuse_other_type("step", operation, f"{part}#arm")
            self.assertEqual(("step", "inspect", None), resolve("inspect", [f"{part}#arm"]))

    def test_a_script_where_a_document_is_wanted_says_cad_run_builds_it(self) -> None:
        """A model's script is never a source: the refusal says the command that builds it and writes its .xbf,
        the skills' own form, and the help says the same -- never ``python SCRIPT.py``."""
        for argv, said in (
                (["inspect", "part.py"], "part.py is a model's script, not a document: `cad run part.py` builds its "
                                         "models, writes each one's .xbf and prints each one's id, which cad inspect "
                                         "takes"),
                (["snapshot", "src/my part.py::part", "out.png"],
                 "src/my part.py::part is a model's script, not a document: `cad run 'src/my part.py'` builds its "
                 "models, writes each one's .xbf and prints each one's id, which cad snapshot takes")):
            with self.subTest(argv=argv):
                code, out, err = _run(argv)
                self.assertEqual((code, out), (2, ""))
                self.assertEqual(err, f"cad {argv[0]}: {said}\n")
        # And the command that takes a file but is no verb's: the page it opens.
        code, out, err = _run(["viewer", "part.py"])
        self.assertEqual((code, out, err), (2, "", "cad viewer: part.py is a model's script, not a CAD file: `cad run "
                                                   "part.py` builds its models and prints each one's page\n"))
        from cad_server.cli.document_types import OPERATIONS, build_parser
        from cad_server.cli.verbs import build_parser as verb_parser

        helps = [" ".join(text.split()) for text in  # each help as words: argparse wraps its lines
                 [verb_parser(verb).format_help() for verb in VERBS]
                 + [build_parser(*key).format_help() for key in sorted(OPERATIONS)]]
        self.assertEqual([text for text in helps if "python SCRIPT" in text], [])
        # A path, never an id, is what the help tells a person to give.
        self.assertEqual([text for text in helps if "cad run SCRIPT.py prints" in text], [])

    def test_a_model_s_id_is_its_xbf_s_and_a_file_is_its_type_s(self) -> None:
        """A model's document id is an xbf's source as its .xbf is; any other word is a file by its suffix."""
        from cad_server.cli.verbs import resolve

        ident = "0b4c5f1e-1a2b-4c3d-8e9f-0123456789ab"
        self.assertEqual(("xbf", "export", None), resolve("export", [ident, "arm.glb"]))
        self.assertEqual(("xbf", "interference", "interference"), resolve("inspect", [ident, "--interference"]))
        self.assertEqual(("step", "solve", None), resolve("fea", ["arm.STP"]))
        code, _, err = _run(["inspect", "arm"])
        self.assertEqual((code, err), (2, "cad inspect: arm is not a file cad inspect takes: it takes .xbf, .step, "
                                          ".stp, .glb, .urdf, .srdf, .kicad_pcb or .kicad_sch\n"))
        code, _, err = _run(["mujoco", "check", "arm.xbf"])
        self.assertEqual((code, err), (2, "cad mujoco check: arm.xbf is a xbf, not a file cad mujoco check takes (.xml "
                                          "or .mjcf): cad dfm takes it\n"))
        # A mesh's export meshes nothing: its parser has no --tolerance or --angle.
        for flag, value in (("--tolerance", "0.01"), ("--angle", "5")):
            err = io.StringIO()
            with contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as refused:
                cli.main(["export", "part.stl", "part.glb", flag, value])
            self.assertEqual(2, refused.exception.code)
            self.assertIn(f"unrecognized arguments: {flag}", err.getvalue())

    def test_export_writes_one_file_like_cp(self) -> None:
        """``cad export SRC DST``: one destination, its format by its suffix; a second is the command line's mistake,
        named, and nothing runs."""
        from unittest import mock

        with tempfile.TemporaryDirectory() as folder, \
                mock.patch("cad_server.engine.cli.answered", side_effect=AssertionError("ran")):
            saved = Path(folder) / "arm.xbf"
            saved.write_bytes(b"")
            code, out, err = _run(["export", str(saved), "arm.glb", "arm.stl"])
            self.assertEqual((code, out), (2, ""))
            self.assertTrue(err.endswith("cad export: error: cad export writes one file, DST: run it once for each of "
                                         "arm.glb, arm.stl\n"), err)
            code, out, err = _run(["export", str(saved), "arm.glb", "arm.stl", "--json"])
            self.assertEqual((code, err), (2, ""))
            self.assertEqual(json.loads(out)["reason"], "usage")
            code, _, err = _run(["export", str(saved)])
            self.assertEqual(code, 2)
            self.assertIn("the following arguments are required: DST", err)

    def test_a_model_s_export_is_one_file_named_and_as_agrees_with_its_suffix(self) -> None:
        """A model's, a STEP's or a mesh's export is one file: a folder is refused, no name being made up for it, and
        ``--as`` names the kind DST's suffix says, or is refused naming both -- before the engine is asked."""
        from unittest import mock

        from cad.engine import api

        with tempfile.TemporaryDirectory() as folder, \
                mock.patch.object(api, "export", side_effect=AssertionError("ran")):
            saved = Path(folder) / "arm.xbf"
            saved.write_bytes(b"")
            for dst, rest, said in (
                    ("out/", [], "out/ is a folder, and the export is one file: name the file (its format by its "
                                 "suffix: part.step, part.glb, ...)"),
                    (folder, [], f"{folder} is a folder, and the export is one file"),
                    ("arm.step", ["--as", "glb"], "arm.step's suffix says STEP, and --as glb says GLB: they must "
                                                  "agree"),
                    ("arm.xml", ["--as", "urdf"], "arm.xml's suffix says MJCF, and --as urdf says URDF")):
                with self.subTest(dst=dst, rest=rest):
                    code, out, err = _run(["export", str(saved), dst, *rest])
                    self.assertEqual((code, out), (2, ""))
                    self.assertTrue(err.startswith(f"cad export: {said}"), err)
                    code, out, _ = _run(["export", str(saved), dst, *rest, "--json"])
                    self.assertEqual((code, json.loads(out)["reason"]), (2, "invalid_argument"))
            code, _, err = _run(["export", str(saved), "arm.step", "--as", "gerbers"])
            self.assertEqual(code, 2)
            self.assertIn("argument --as: invalid choice: 'gerbers'", err)
        with tempfile.TemporaryDirectory() as folder, mock.patch.object(api, "export", return_value=[]) as export:
            saved = Path(folder) / "arm.xbf"
            saved.write_bytes(b"")
            for dst, kind in (("arm.step", "step"), ("arm.stp", "step"), ("arm.3mf", "3mf"), ("arm.xml", "mjcf")):
                with self.subTest(dst=dst):
                    self.assertEqual(_run(["export", str(saved), dst, "--as", kind])[0], 0)
        self.assertEqual([call.args for call in export.call_args_list],
                         [(str(saved), dst) for dst in ("arm.step", "arm.stp", "arm.3mf", "arm.xml")])

    def test_an_xbf_takes_a_model_by_its_id_or_saved_as_a_file(self) -> None:
        """Every verb of an xbf takes the ``.xbf`` a model is saved as beside a document id: the file is told by its
        suffix, as the registry reads one, where the operation's parser reads its source, and its help says so. A file
        that is not there is refused before anything runs, as every type's is; a destination is no source."""
        from cad_server.cli.document_types import _refuse_other_type, build_parser

        ident = "0b4c5f1e-1a2b-4c3d-8e9f-0123456789ab"
        with tempfile.TemporaryDirectory() as folder:
            saved = Path(folder) / "Arm.XBF"
            saved.write_bytes(b"")
            for operation in ("export", "snapshot", "inspect", "dfm", "interference", "solve", "ranges"):
                with self.subTest(operation=operation):
                    for source in (ident, str(saved), f"{saved}#arm/face 1"):
                        _refuse_other_type("xbf", operation, source)  # taken: no refusal
                    said = " ".join(build_parser("xbf", operation).format_help().split())
                    self.assertTrue("the .xbf file a model is saved as" in said or "a .xbf, .step or .stp" in said, said)

    def test_an_xbf_reads_only_its_source_as_a_file_and_an_id_stays_the_model_s(self) -> None:
        """A destination is no source: ``cad export ID out.xbf`` is the export of what the engine holds, however its
        destination is spelled; and a file is handed on as the path it is."""
        from unittest import mock

        ident = "0b4c5f1e-1a2b-4c3d-8e9f-0123456789ab"
        asked: list[tuple[str, list[str], str]] = []

        def answered(runner: object, args: object, prog: str) -> int:
            asked.append((args.source, args.destinations, prog))  # type: ignore[attr-defined]
            return 0

        with tempfile.TemporaryDirectory() as folder, mock.patch("cad_server.engine.cli.answered", answered):
            saved = str(Path(folder) / "arm.xbf")
            Path(saved).write_bytes(b"")
            self.assertEqual(_run(["export", ident, "share/arm.xbf"])[0], 0)
            self.assertEqual(_run(["export", saved, "arm.glb"])[0], 0)
        self.assertEqual(asked, [(ident, ["share/arm.xbf"], "cad export"), (saved, ["arm.glb"], "cad export")])

    def test_a_types_own_option_before_its_file_is_no_file(self) -> None:
        """``--urdf robot.urdf`` is an SRDF check's own option, wherever it stands: the file it checks is the one the
        parser takes as its file, never the first word without a dash."""
        with tempfile.TemporaryDirectory() as folder:
            urdf, srdf = Path(folder) / "robot.urdf", Path(folder) / "robot.srdf"
            urdf.write_text('<robot name="r"><link name="a"/></robot>', encoding="utf-8")
            srdf.write_text('<robot name="r"><group name="arm"><link name="a"/></group></robot>', encoding="utf-8")
            for argv in (["inspect", "--urdf", str(urdf), str(srdf)], ["inspect", str(srdf), "--urdf", str(urdf)]):
                with self.subTest(argv=argv):
                    code, said, err = _run([*argv, "--json"])
                    self.assertNotIn("is a urdf", said + err)
                    self.assertIn('"path"', said)
            # A URDF's inspection is its own check, which takes no --urdf.
            code, said, _ = _run(["inspect", "--urdf", str(urdf), str(urdf), "--json"])
            self.assertEqual(2, code)
            self.assertIn("unrecognized arguments: --urdf", said)


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
        self.assertEqual({"kicad": "cad_server.cli.kicad", "mujoco": "cad_server.cli.mujoco"},
                         cli.INTEGRATION_COMMANDS)
        self.assertFalse(set(cli.INTEGRATION_COMMANDS) & set(DOCUMENT_TYPES), "a name is a type's or an integration's")
        self.assertEqual(("mujoco check", ["arm.xml"]), cli.resolve(["mujoco", "check", "arm.xml"]))
        self.assertEqual(("kicad drc", ["b.kicad_pcb"]), cli.resolve(["kicad", "drc", "b.kicad_pcb"]))
        self.assertIsNone(cli.resolve(["mujoco", "validate", "arm.xml"]))
        code, said, _ = _run(["--help"])
        self.assertEqual(0, code)
        self.assertIn("integrations, a tool's own operations on its files (cad <integration> <operation> FILE):\n"
                      "  kicad   drc, erc  KiCad's design rule check of a board (.kicad_pcb); KiCad's electrical rules "
                      "check of a schematic (.kicad_sch)\n  mujoco  check     compile a MuJoCo model", said)
        # A deprecated integration has no command: `cad orcaslicer` answers with what to do instead (test_cli).
        self.assertNotIn("orcaslicer", said.split("integrations, a tool's own operations", 1)[1])
        code, said, _ = _run(["mujoco", "--help"])
        self.assertEqual(0, code)
        self.assertIn("usage: cad mujoco <operation> FILE [options]", said)
        self.assertIn("operations (on .xml, .mjcf):\n  check  ", said)
        # MJCF was never a document type's command: the old spelling is an unknown command, the new one named.
        code, _, err = _run(["mjcf", "validate", str(self.model)])
        self.assertEqual((code, err), (2, "cad: unknown command 'mjcf' (did you mean 'mujoco'?); 'cad --help' lists the "
                                          "commands\n"))
        # `serve` is removed with nothing in its place: no suggestion (it is as near `share`, which shares a file),
        # and a typo of `server` is not sent to bare `cad server`, itself an earlier spelling that runs nothing.
        for word in ("serve", "servr"):
            code, _, err = _run([word, "x.xbf"])
            self.assertEqual((code, err), (2, f"cad: unknown command {word!r}; 'cad --help' lists the commands\n"))

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
                                                  "takes (.xml or .mjcf): cad inspect takes it\n"),
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




class KicadChecks(unittest.TestCase):
    """``cad kicad drc BOARD`` and ``cad kicad erc SCHEMATIC``: KiCad's own checks, the kicad integration's operations
    (``cad.kicad.drc``, ``cad.kicad.erc``), each of its own kind of file. What they find is the KiCad suite's
    (``tests/python/packages/kicad``); here, what each takes and refuses."""

    def test_each_takes_its_own_kind_of_file_and_names_the_other(self) -> None:
        for argv, words in (
                (["kicad", "drc", "sheet.kicad_sch"], "cad kicad drc: sheet.kicad_sch is not a file cad kicad drc takes "
                                                      "(.kicad_pcb): cad kicad erc checks it\n"),
                (["kicad", "erc", "board.kicad_pcb"], "cad kicad erc: board.kicad_pcb is not a file cad kicad erc takes "
                                                      "(.kicad_sch): cad kicad drc checks it\n"),
                (["kicad", "drc", "part.step"], "cad kicad drc: part.step is a step, not a file cad kicad drc takes "
                                                "(.kicad_pcb): cad dfm takes it\n"),
                (["kicad", "drc", "nowhere.kicad_pcb"], "cad kicad drc: no such file: nowhere.kicad_pcb\n"),
                (["kicad", "check", "board.kicad_pcb"], "cad kicad: cad kicad has no operation 'check'")):
            with self.subTest(argv=argv):
                code, out, err = _run(argv)
                self.assertEqual((code, out), (2, ""))
                self.assertTrue(err.startswith(words), err)

    def test_the_parsers_are_the_generated_ones(self) -> None:
        from cad_server.cli.integrations import build_parser

        for operation, file in (("drc", "BOARD"), ("erc", "SCHEMATIC")):
            text = " ".join(build_parser("kicad", operation).format_help().split())
            self.assertIn(f"usage: cad kicad {operation} [-h] [--json] {file}", text)


class KicadExports(unittest.TestCase):
    """``cad export FILE DST [--as KIND]`` of a KiCad board or schematic: DST says what is written, ``--as`` naming it
    where DST cannot. Every refusal is said before KiCad runs and writes nothing; the earlier spelling, ``cad export
    FILE DIR --to KIND``, runs nothing and names this one. What KiCad writes is the KiCad suite's
    (``tests/python/packages/kicad``)."""

    def setUp(self) -> None:
        self._tempdir = tempfile.TemporaryDirectory(prefix="kicad-exports-")
        self.addCleanup(self._tempdir.cleanup)
        self.root = Path(self._tempdir.name)
        self.board, self.schematic = self.root / "b.kicad_pcb", self.root / "b.kicad_sch"
        for file in (self.board, self.schematic):
            file.write_text("(kicad_pcb)" if file.suffix == ".kicad_pcb" else "(kicad_sch)", encoding="utf-8")

    def test_a_destination_that_cannot_say_what_to_write_is_refused_and_nothing_runs(self) -> None:
        from unittest import mock

        fab = self.root / "fab"
        refusals = (
            ([str(self.board), f"{fab}/"], f"{fab}/ is a folder, which takes a board's Gerbers, drill files, ODB++ or "
                                           "PDF: name which, --as gerbers, --as drill, --as odb or --as pdf"),
            ([str(self.board), f"{fab}.zip"], f"{fab}.zip is a .zip, which takes a board's Gerbers, drill files, "
                                              "ODB++ or PDF: name which, --as gerbers, --as drill, --as odb or --as "
                                              "pdf"),
            ([str(self.board), f"{fab}/b.csv"], f"{fab}/b.csv is a .csv, which takes a board's placement or BOM: name "
                                                "which, --as pos or --as bom"),
            ([str(self.board), f"{fab}/", "--as", "glb"], f"{fab}/ is a folder, and a board's GLB is one file: name "
                                                          f"the file ({fab}/b.glb)"),
            ([str(self.board), f"{fab}.zip", "--as", "pos"], f"{fab}.zip is a .zip, and a board's placement is one "
                                                             f"file: name the file ({fab}.csv)"),
            ([str(self.board), f"{fab}/b.glb", "--as", "step"], f"{fab}/b.glb is a board's GLB, and --as step names "
                                                                "its STEP: they must agree"),
            ([str(self.board), f"{fab}/b.glb", "--as", "gerbers"], "--as gerbers writes several files: name a folder "
                                                                   f"(ending in /) or a .zip, not {fab}/b.glb"),
            ([str(self.board), f"{fab}/b.pdf"], f"{fab}/b.pdf: a board's PDF is two files, a drawing of each side: "
                                                "name a folder or a .zip, with --as pdf"),
            ([str(self.board), str(self.board), "--as", "step"], f"{self.board} is the board itself: an export never "
                                                                 "writes over its source"),
            ([str(self.schematic), f"{fab}/", "--as", "netlist"], f"{fab}/ is a folder, and a schematic's netlist is "
                                                                  f"one file: name the file ({fab}/b.net)"),
            ([str(self.schematic), f"{fab}/b.svg"], f"{fab}/b.svg: a schematic's export is a .pdf, .net or .csv "
                                                    "file, a folder or a .zip"))
        with mock.patch("cad.kicad._destination.scratch", side_effect=AssertionError("ran")):
            for argv, said in refusals:
                with self.subTest(argv=argv[1:]):
                    code, out, err = _run(["export", *argv])
                    self.assertEqual((code, out, err), (2, "", f"cad export: {said}\n"))
                    code, out, err = _run(["export", *argv, "--json"])
                    self.assertEqual((code, err), (2, ""))
                    self.assertEqual(json.loads(out), {"ok": False, "error": said, "reason": "invalid_argument"})
        self.assertFalse(fab.exists(), "a refused export writes nothing")
        code, _, err = _run(["export", str(self.board), f"{fab}/", "--as", "svg"])
        self.assertEqual(code, 2)
        self.assertIn("argument --as: invalid choice: 'svg'", err)

    def test_the_earlier_spelling_runs_nothing_and_names_the_one_it_has_now(self) -> None:
        from unittest import mock

        said = ("'cad export FILE DIR --to KIND' is 'cad export FILE DST --as KIND' now; 'cad export --help' says its "
                "options")
        with mock.patch("cad.kicad._destination.scratch", side_effect=AssertionError("ran")):
            for argv in ([str(self.board), "fab", "--to", "gerbers"], ["--to=pdf", str(self.schematic), "sheets"],
                         [str(self.board), "fab", "--to", "glb", "--json"]):
                with self.subTest(argv=argv):
                    code, out, err = _run(["export", *argv])
                    self.assertEqual(code, 2)
                    if "--json" in argv:
                        self.assertEqual((json.loads(out), err), ({"ok": False, "error": said, "reason": "usage"}, ""))
                    else:
                        self.assertEqual((out, err), ("", f"cad export: {said}\n"))


if __name__ == "__main__":
    unittest.main()
