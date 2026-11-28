"""The public verb surface, and the CLIs that mirror it.

Three properties that only hold if something checks them:

* **The manifest.** Exactly the declared names are public on each robot description's document
  type (``cad.urdf``, ...), and every check is fully annotated -- annotation is what makes a CLI derivable, so an unannotated
  parameter is a silently undispatchable flag.
* **Signature sync.** For every command, the parser's options ARE the function's parameters
  (a mirror, generated from it) or exactly what the command declares (an adapter, whose parser
  is written by hand). This fails on a one-sided addition in either direction.
* **The import budget.** A public namespace imports without the CAD stack, and so does a
  command's ``--help``.
"""

from __future__ import annotations

import argparse
import contextlib
import importlib
import io
import inspect
import json
import subprocess
import sys
import unittest
import warnings

from cad_server import cli
from cad_server._internal.cli_from_function import (JSON_FLAG_DEST, NotDerivable, cli_from_function, function_parameters, parser_dests)

# The manifest: robot namespace -> exactly the names it exports. A robot description is an authored file, so there
# is nothing to declare; its check is ``cad.inspect``'s (``cad.<type>.validate`` an alias, kept out of ``__all__``),
# and its snapshot the engine's.
PUBLIC_SURFACE: dict[str, tuple[str, ...]] = {
    "cad.urdf": (),
    "cad.srdf": (),
}
# The robot descriptions' checks, what ``cad inspect`` of each runs: fully annotated, the SRDF's derivable (a
# mirror's), the URDF's not (an adapter's: ``--packages NAME=PATH`` repeats).
CHECKS: dict[tuple[str, str], bool] = {("cad.urdf._check", "validate"): False, ("cad.srdf._check", "validate"): True}

# The file each verb's command lines below name, by type: the verb's runner is its type's.
FILE = {"xbf": "part.xbf", "step": "part.step", "stl": "part.stl", "glb": "part.glb", "threemf": "part.3mf",
        "dxf": "part.dxf", "urdf": "robot.urdf", "srdf": "robot.srdf", "kicad_pcb": "board.kicad_pcb",
        "kicad_sch": "sheet.kicad_sch"}

# Commands whose parser is GENERATED from the verb it calls. No allowlist is possible here:
# the parser has no independent existence. A verb's is named for the verb and its file's type (``dfm step``),
# a mode's with its flag too (``inspect step --ranges``), which the parser takes beside the signature.
MIRRORS: dict[str, tuple[str, str]] = {
    # The mujoco integration's check of a MuJoCo model's file, which is no document type: run here, or where
    # mujoco is not installed, in cad[mujoco]'s environment (``cad_server.cli.integrations``).
    "mujoco check": ("cad.mujoco", "check"),
    # KiCad's own checks: its design rule check of a saved board and its electrical rules check of a schematic, the
    # kicad integration's, run by its kicad-cli.
    "kicad drc": ("cad.kicad", "drc"),
    "kicad erc": ("cad.kicad", "erc"),
    "inspect srdf": ("cad.srdf._check", "validate"),
    # A 3D type's manufacturing check, and a DXF's as a sheet's cut file: one signature for every type.
    **{f"dfm {document_type}": (f"cad.{document_type}", "dfm")
       for document_type in ("xbf", "step", "stl", "glb", "threemf", "dxf")},
    # A B-rep type's stress study: the calculix integration's, one signature for every B-rep type.
    **{f"fea {document_type}": (f"cad.{document_type}", "solve") for document_type in ("xbf", "step")},
    # The joint stops of a document with a mechanism: the kernel's, one signature for every B-rep type.
    **{f"inspect {document_type} --ranges": (f"cad.{document_type}", "ranges") for document_type in ("xbf", "step")},
}

# The engine snapshot's options (``cad.engine.snapshot``): ``out_folder`` is ``--out DIR``, a job's folder.
SNAPSHOT = frozenset({"document", "out", "job", "out_folder", "display", "grid", "preview", "camera", "width",
                      "height", "size_profile", "pose", "annotation", "measurements", "json"})

# Commands with a HAND-WRITTEN parser, and the option surface each one owns. An adapter has no
# generated parser to compare against a signature, so the declaration IS the contract, and a
# flag or subcommand that appears without being declared here fails.
ADAPTERS: dict[str, frozenset[str]] = {
    # The one robot check that cannot be a mirror: `--packages NAME=PATH` is repeatable, and a
    # repeatable key/value map is outside the derivable set.
    "inspect urdf": frozenset({"path", "strict", "packages", "verbose"}),
    # The person's telemetry choice: status, on or off.
    "telemetry": frozenset({"action"}),
    # cad updated now to the newest release of its major, by the server that runs; or `auto`, whether cad updates
    # itself (status, on or off).
    "update": frozenset({"command", "auto"}),
    # The install command run now (`update`), or (`update auto`) whether cad's automatic update runs it after it; and
    # the hidden --refresh the updater of 0.11.10 runs, which does nothing.
    "plugin": frozenset({"command", "install", "update", "refresh"}),
    # The engine's verbs (cad_server.engine.cli), each type's: a document's export (a model's, a STEP's) meshes a GLB,
    # an STL or a 3MF to a tolerance and an angle, and takes a robot description's joints from a zero state; a
    # mesh's, to the other mesh kinds, does neither. Each names the kind it writes (--as), agreeing with its file's.
    **{f"export {document_type}": frozenset({"source", "destinations", "as_", "tolerance", "angle", "zero", "json"})
       for document_type in ("xbf", "step")},
    **{f"export {document_type}": frozenset({"source", "destinations", "as_", "json"})
       for document_type in ("stl", "glb", "threemf")},
    **{f"snapshot {document_type}": SNAPSHOT
       for document_type in ("xbf", "step", "stl", "glb", "threemf", "dxf", "urdf", "srdf")},
    # A B-rep type's interference check: its poses and fits repeat, lists no signature derives; its flag picked it.
    **{f"inspect {document_type} --interference": frozenset({"document", "interference", "pose", "fit", "min_volume"})
       for document_type in ("xbf", "step")},
    # A KiCad board's still: the engine's snapshot with the box of the board to frame.
    "snapshot kicad_pcb": SNAPSHOT | {"window"},
    # A KiCad board's exports, kicad-cli's, from a fixed list, to a file, a folder or a .zip (--as naming the kind
    # where it cannot); and its summary, the library's.
    "export kicad_pcb": frozenset({"board", "dst", "as_"}),
    "inspect kicad_pcb": frozenset({"board"}),
    # A KiCad schematic's: its exports, kicad-cli's; its summary and what a reference names; its still, the
    # engine's snapshot with the sheet to draw and its page's edge.
    "export kicad_sch": frozenset({"schematic", "dst", "as_"}),
    "inspect kicad_sch": frozenset({"schematic", "ref"}),
    "snapshot kicad_sch": SNAPSHOT | {"sheet", "border"},
    **{f"inspect {document_type}": frozenset({"document", "ref", "query", "json"})
       for document_type in ("xbf", "step", "glb")},
    # The server's commands (start, stop, status), and the page token replaced, asking first.
    "server": frozenset({"command", "start", "stop", "status", "port", "rotate_token", "yes"}),
    # This version installed on this computer (and the hidden flag the updaters of 0.10.0 to 0.11.11 run).
    "setup": frozenset({"engine_update"}),
    # cad's cache: where it is, what this release cannot use removed, all of it removed.
    "cache": frozenset({"command", "dir", "prune", "clean"}),
    # The exact cad requirement for a Python of a program's own: its integrations, and --json.
    "requirement": frozenset({"integrations", "json"}),
    # One read-only report of this cad.
    "doctor": frozenset({"check", "json"}),
    # The viewer launcher: the launch contract (reuse, replace or start on its one port, the --json announce
    # line) is not a function signature to mirror.
    "viewer": frozenset({"files", "host", "port", "json", "no_open", "dist", "api_only"}),
    # A file shared by its link, or the words status, on, off and delete with the file or link it deletes: the
    # person's agreement (--yes, which a delete asks too) and an upload this process makes mirror no function.
    "share": frozenset({"target", "link", "yes", "json"}),
    # A share's files written into a folder: a download this process makes, and a folder it writes, mirror no function.
    "import": frozenset({"link", "folder", "json"}),
}

# Commands that own their command line outright and mirror no function.
UNCLASSIFIED = {
    # uv run's options and a program's arguments, whatever they are: no parser of its own (uv judges them).
    "run",
    # The CAD app an agent app starts: MCP on stdin and stdout, which no function's signature describes.
    "mcp",
}

HEAVY = ("OCP", "build123d", "ezdxf", "shapely")


def _verb(target: tuple[str, str]):
    module, attribute = target
    return getattr(importlib.import_module(module), attribute)


def _commands() -> set[str]:
    """Every command the dispatcher answers: each verb's runner of each type (``dfm step``, a mode's with its flag:
    ``inspect step --ranges``), each integration's operation on its tool's own files, and the rest."""
    from cad.registry import MODES, operation_for, types_for
    from cad_server.cli.integrations import OPERATIONS as INTEGRATION_OPERATIONS
    from cad_server.cli.verbs import VERBS

    found = {name for name in cli._COMMANDS if name not in VERBS}
    for verb in VERBS:
        for mode in (None, *(MODES if verb == "inspect" else ())):
            found.update(f"{verb} {document_type}" + (f" --{mode}" if mode else "") for document_type in
                         types_for(verb, mode) if mode is None or operation_for(verb, document_type, mode) == MODES[mode])
    return {*found, *(f"{name} {operation}" for name, operation in INTEGRATION_OPERATIONS)}


def _parser(name: str):
    """A command's parser, as the dispatcher reads its command line: a verb's of its type's file, with a mode's
    flag (``inspect step --ranges``)."""
    words = name.split()
    from cad_server.cli.verbs import VERBS

    if words[0] in VERBS:
        return cli.build_parser_for(words[0], [FILE[words[1]], *words[2:]])
    return cli.build_parser_for(name)


def _adapter_surface(name: str) -> frozenset[str]:
    """One adapter command's real option surface, read off the command itself: its destinations
    plus its subcommand names, which is where a subcommand tree's meaning lives."""
    parser = _parser(name)
    names = set(parser_dests(parser)) - {JSON_FLAG_DEST}
    for action in parser._actions:  # noqa: SLF001 - argparse exposes no public view
        if action.nargs == argparse.PARSER:
            names |= set(action.choices or ())
    return frozenset(names)


class Manifest(unittest.TestCase):
    def test_each_namespace_exports_exactly_its_declared_verbs(self):
        for module_name, verbs in PUBLIC_SURFACE.items():
            with self.subTest(module=module_name):
                module = importlib.import_module(module_name)
                self.assertEqual(sorted(verbs), sorted(module.__all__))
                for verb in verbs:
                    self.assertTrue(callable(getattr(module, verb)))

    def test_every_check_is_fully_annotated_and_derivable(self):
        for target, derivable in CHECKS.items():
            with self.subTest(check=".".join(target)):
                func = _verb(target)
                signature = inspect.signature(func)
                unannotated = [name for name, parameter in signature.parameters.items()
                               if parameter.annotation is parameter.empty]
                self.assertEqual([], unannotated)
                self.assertIsNot(signature.return_annotation, signature.empty)
                # Derivability is the CLASSIFICATION: a mirror's parser is generated from this
                # signature, and an adapter exists precisely because its verb cannot be.
                if derivable:
                    cli_from_function(func, prog="probe")
                else:
                    with self.assertRaises(NotDerivable):
                        cli_from_function(func, prog="probe")

    def test_the_retired_commands_are_gone(self):
        # A retired command has no entry and no module: it gets the answer of any unknown command, or, for a spelling
        # the skills of 0.11 used, the one line naming the spelling it has now (``test_cli``).
        for command in ("build", "step build", "step compile", "stl build", "3mf build", "3mf snapshot", "glb build",
                        "store", "daemon", "daemon status", "where", "install", "serve", "status", "stop",
                        "urdf check", "sdf check", "srdf check", "stl check", "xbf check", "kicad_pcb check",
                        "kicad_sch check", "pcb drc", "mjcf validate", "mjcf snapshot", "mjcf", "uninstall",
                        "sdf", "sdf validate", "sdf snapshot", "xbf export", "step export", "urdf validate",
                        "kicad_pcb drc", "kicad_sch erc", "model export", "orcaslicer presets"):
            self.assertNotIn(command, _commands())
        for module in ("cad_server.cli.build", "cad.engine.shape_input", "cad_server.cli.step_build", "cad_server.cli.step_snapshot", "cad_server.cli.stl_build",
                       "cad_server.cli.where", "cad_server.cli.store", "cad_server.cli.daemon", "cad_server.cli.daemon_status", "cadgen.store", "cadgen.daemon",
                       "cad_server.cli.install", "cad_server.cli.mcp", "cad_server.cli.inspect", "cad_server.cli.urdf_validate",
                       "cad_server.cli.sdf_validate", "cad_server.cli.srdf_validate", "cad_server.kicad.schematic",
                       "cad_server.cli.mjcf", "cad.mjcf", "cad.engine.mjcf_source", "cad_server.cli.retired",
                       "cad_server._internal.leftovers", "cad_server.cli.sdf", "cad.sdf", "cad.engine.sdf_source",
                       "cad_server.cli.xbf", "cad_server.cli.step", "cad_server.cli.urdf", "cad_server.cli.model",
                       "cad_server.cli.serve", "cad_server.cli.status", "cad_server.cli.stop",
                       "cad_server.cli.orcaslicer"):
            with self.subTest(module=module), self.assertRaises(ModuleNotFoundError), warnings.catch_warnings():
                warnings.simplefilter("ignore", FutureWarning)  # cadgen's deprecation, not this test's subject
                importlib.import_module(module)

    def _dispatch(self, *argv: str) -> tuple[int, str, str]:
        import contextlib
        import io

        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def test_a_file_whose_type_lacks_the_verb_is_refused_naming_the_types_that_have_it(self):
        for argv, line in (
                (("export", "robot.urdf", "robot.step"),
                 "robot.urdf is a urdf, which has no export: cad export takes xbf, step, stl, glb, threemf, kicad_pcb "
                 "and kicad_sch files"),
                (("dfm", "robot.urdf"), "robot.urdf is a urdf, which has no dfm: cad dfm takes xbf, step, stl, glb, "
                                        "threemf and dxf files"),
                (("fea", "part.stl"), "part.stl is an stl, which has no fea: cad fea takes xbf and step files"),
                (("inspect", "part.stl"), "part.stl is an stl, which has no inspect: cad inspect takes xbf, step, glb, "
                                          "urdf, srdf, kicad_pcb and kicad_sch files"),
                (("inspect", "part.glb", "--ranges"), "part.glb is a glb, which has no inspect --ranges: cad inspect "
                                                      "--ranges takes xbf and step files"),
                (("dfm", "board.kicad_pcb"), "board.kicad_pcb is a kicad_pcb: cad dfm checks that a part can be made; "
                                             "KiCad's own check of it is cad kicad drc"),
                (("dfm", "sheet.kicad_sch"), "sheet.kicad_sch is a kicad_sch: cad dfm checks that a part can be made; "
                                             "KiCad's own check of it is cad kicad erc")):
            with self.subTest(argv=argv):
                code, out, err = self._dispatch(*argv)
                self.assertEqual((2, ""), (code, out))
                self.assertEqual(f"cad {argv[0]}: {line}\n", err)
                code, out, err = self._dispatch(*argv, "--json")
                self.assertEqual((2, ""), (code, err))
                self.assertEqual({"ok": False, "error": line, "reason": "wrong_type"}, json.loads(out))

    def test_a_verbs_help_says_its_forms_and_every_types_options_and_exits_zero(self):
        code, out, err = self._dispatch("inspect", "--help")
        self.assertEqual((0, ""), (code, err))
        for form in ("cad inspect FILE [REF]", "cad inspect FILE --interference", "cad inspect FILE --ranges",
                     "cad inspect ROBOT.urdf", "cad inspect ROBOT.srdf"):
            self.assertIn(form, out)
        for flag in ("--query", "--interference", "--pose", "--fit", "--ranges", "--joint", "--strict", "--packages",
                     "--urdf"):
            self.assertIn(flag, out)

    def test_an_unknown_noun_names_it_and_where_the_commands_are(self):
        # Never the whole list: the word, at most one suggestion, and the help that lists them.
        code, out, err = self._dispatch("frobnicate", "export")
        self.assertEqual((2, ""), (code, out))
        self.assertEqual("cad: unknown command 'frobnicate'; 'cad --help' lists the commands\n", err)
        # A command a release took away is one more unknown word, with no note about history.
        code, out, err = self._dispatch("delete", "6f1c2a4e-1b2c-5d3e-8f4a-0123456789ab", "--yes")
        self.assertEqual((2, ""), (code, out))
        self.assertTrue(err.startswith("cad: unknown command 'delete'"), err)
        code, out, err = self._dispatch("expotr")
        self.assertEqual(2, code)
        self.assertEqual("cad: unknown command 'expotr' (did you mean 'export'?); 'cad --help' lists the commands\n",
                         err)

    def test_a_name_that_is_not_a_verb_raises_the_plain_attribute_error(self):
        # No retired-surface recognition: the answer is Python's own error, not a note about history.
        urdf = importlib.import_module("cad.urdf")
        with self.assertRaises(AttributeError) as caught:
            urdf.export  # noqa: B018 - the attribute access IS the assertion
        self.assertIn("export", str(caught.exception))
        self.assertNotIn("deleted", str(caught.exception))

    def test_the_engines_verbs_are_commands_of_their_own(self):
        # One parser per verb, named by the command that runs it: every type's options (cad_server.cli.verbs), and
        # the server's process control (cad_server.engine.cli).
        for verb in ("export", "snapshot", "inspect", "dfm", "fea", "server"):
            with self.subTest(verb=verb):
                self.assertEqual(cli.build_parser_for(verb).prog, f"cad {verb}")
        for argv in (["part.step", "part.glb"], ["part.stl", "out.png"], ["part.step"]):
            with self.subTest(argv=argv):
                self.assertTrue(cli.build_parser_for("export", argv).prog.startswith("cad export"))

    def test_every_verb_goes_through_the_engine(self):
        # No command runs a build or a verb in its own process: --no-daemon is an unrecognized argument like any
        # other. daemon=False is the Python functions' seam for tests and debugging alone.
        for argv in (("export", "a.xbf", "a.stl", "--no-daemon"), ("snapshot", "a.xbf", "a.png", "--no-daemon")):
            with self.subTest(argv=argv):
                err = io.StringIO()
                with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()), \
                        self.assertRaises(SystemExit) as caught:
                    cli.main(list(argv))
                self.assertEqual(caught.exception.code, 2)
                self.assertIn("unrecognized arguments: --no-daemon", err.getvalue())
        from cad.engine import api

        for verb in (api.export, api.snapshot):
            self.assertIn("daemon", inspect.signature(verb).parameters)


class SignatureSync(unittest.TestCase):
    def test_every_command_is_classified(self):
        classified = set(MIRRORS) | set(ADAPTERS) | UNCLASSIFIED
        self.assertEqual(_commands(), classified,
                         "a new command must be declared a mirror, an adapter, or explicitly unclassified")

    def test_a_mirrors_parser_is_exactly_its_signature(self):
        for command, target in MIRRORS.items():
            with self.subTest(command=command):
                # A mode's flag (--ranges) picked the runner: the parser takes it beside the signature.
                flags = {word.removeprefix("--") for word in command.split() if word.startswith("--")}
                dests = set(parser_dests(_parser(command))) - {JSON_FLAG_DEST} - flags
                self.assertEqual(set(function_parameters(_verb(target))), dests)

    def test_an_adapters_option_surface_is_exactly_what_it_declares(self):
        for command, declared in ADAPTERS.items():
            with self.subTest(command=command):
                self.assertEqual(declared, _adapter_surface(command))


class ImportBudget(unittest.TestCase):
    """Run in a subprocess: this one has the CAD stack loaded already."""

    def test_public_namespaces_import_without_the_cad_stack(self):
        imports = "; ".join(f"import {name}" for name in (*PUBLIC_SURFACE, "cad.build123d._geometry"))
        code = f"import sys; {imports}; print('HEAVY:' + ','.join(m for m in {HEAVY!r} if m in sys.modules))"
        proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("HEAVY:\n", proc.stdout)

    def test_a_commands_help_does_not_wake_the_cad_stack(self):
        # Every command's help in one interpreter, in turn: the first that loads the stack is named
        # (the ones after it cannot be told apart, and the run fails on the first).
        commands = [*MIRRORS, *ADAPTERS]
        code = (
            "import sys\n"
            "from cad_server import cli\n"
            f"files = {FILE!r}\n"
            f"verbs = {('export', 'inspect', 'snapshot', 'dfm', 'fea')!r}\n"
            f"for name in {commands!r}:\n"
            "    words = name.split()\n"
            "    parser = (cli.build_parser_for(words[0], [files[words[1]], *words[2:]]) if words[0] in verbs\n"
            "              else cli.build_parser_for(name))\n"
            "    parser.format_help()\n"
            f"    woke = [x for x in {HEAVY!r} if x in sys.modules]\n"
            "    if woke:\n"
            "        print(f'WOKE {name}: {woke}')\n"
            "        break\n"
        )
        proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout, "", "a command's help loaded the CAD stack")


if __name__ == "__main__":
    unittest.main()
