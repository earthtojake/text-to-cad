"""The public verb surface, and the CLIs that mirror it.

Three properties that only hold if something checks them:

* **The manifest.** Exactly the declared names are public on each robot description's document
  type (``cad.urdf``, ...), and every public verb is fully annotated -- annotation is what makes a CLI derivable, so an unannotated
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
import subprocess
import sys
import unittest

from cad_server import cli
from cad_server._internal.cli_from_function import (JSON_FLAG_DEST, NotDerivable, cli_from_function, function_parameters, parser_dests)

# The manifest: robot namespace -> exactly the verbs it exports. A robot description is an
# authored file, so there is nothing to declare; each format's snapshot is the engine's.
PUBLIC_SURFACE: dict[str, tuple[str, ...]] = {
    "cad.urdf": ("validate",),
    "cad.srdf": ("validate",),
    "cad.sdf": ("validate",),
}

# Commands whose parser is GENERATED from the verb it calls. No allowlist is possible here:
# the parser has no independent existence.
MIRRORS: dict[str, tuple[str, str]] = {
    "sdf validate": ("cad.sdf", "validate"),
    "srdf validate": ("cad.srdf", "validate"),
    # KiCad's design rule check of a saved board: the document type's, run by the kicad integration's kicad-cli.
    "kicad_pcb drc": ("cad.kicad_pcb", "drc"),
    # KiCad's electrical rules check of a saved schematic: the document type's, run by the kicad integration's kicad-cli.
    "kicad_sch erc": ("cad.kicad_sch", "erc"),
    # A 3D type's manufacturing check: the trimesh integration's, one signature for every 3D type.
    **{f"{document_type} dfm": (f"cad.{document_type}", "dfm")
       for document_type in ("model", "xbf", "step", "stl", "glb", "threemf")},
    # A B-rep type's CAM job: read with the kernel, planned by FreeCAD, one signature for every B-rep type.
    **{f"{document_type} cam": (f"cad.{document_type}", "cam") for document_type in ("xbf", "step")},
}

# The engine snapshot's options (``cad.engine.snapshot``).
SNAPSHOT = frozenset({"document", "out", "job", "display", "grid", "camera", "width", "height",
                      "size_profile", "pose", "annotation", "measurements", "json"})

# Commands with a HAND-WRITTEN parser, and the option surface each one owns. An adapter has no
# generated parser to compare against a signature, so the declaration IS the contract, and a
# flag or subcommand that appears without being declared here fails.
ADAPTERS: dict[str, frozenset[str]] = {
    # The one validator that cannot be a mirror: `--packages NAME=PATH` is repeatable, and a
    # repeatable key/value map is outside the derivable set.
    "urdf validate": frozenset({"path", "strict", "packages", "verbose"}),
    # The person's telemetry choice: status, on or off.
    "telemetry": frozenset({"action"}),
    # The engine's verbs (cad_server.engine.cli): each type's operations, and its process control.
    # A document's export (a model's, an xbf's, a STEP's) meshes an STL or a 3MF to a tolerance; a mesh's, to
    # the other mesh kinds, meshes nothing.
    **{f"{document_type} export": frozenset({"source", "destinations", "tolerance", "json"})
       for document_type in ("model", "xbf", "step")},
    **{f"{document_type} export": frozenset({"source", "destinations", "json"})
       for document_type in ("stl", "glb", "threemf")},
    **{f"{document_type} snapshot": SNAPSHOT
       for document_type in ("model", "xbf", "step", "stl", "glb", "threemf", "dxf", "urdf", "srdf", "sdf",
                             "kicad_pcb")},
    # A KiCad board's exports, kicad-cli's, from a fixed list into a folder; and its summary, the library's.
    "kicad_pcb export": frozenset({"board", "to", "out"}),
    "kicad_pcb inspect": frozenset({"board"}),
    # A KiCad schematic's: its exports, kicad-cli's; its summary and what a reference names; its still, the
    # engine's snapshot with the sheet to draw and its page's edge.
    "kicad_sch export": frozenset({"schematic", "to", "out"}),
    "kicad_sch inspect": frozenset({"schematic", "ref"}),
    "kicad_sch snapshot": SNAPSHOT | {"sheet", "border"},
    **{f"{document_type} inspect": frozenset({"document", "ref", "query", "json"})
       for document_type in ("model", "xbf", "step", "glb")},
    "serve": frozenset({"document", "port"}),
    "status": frozenset({"json"}),
    "stop": frozenset({"json"}),
    # A command that destroys asks first, or takes --yes (cad_server._internal.consent); a delete says its plan alone.
    "delete": frozenset({"documents", "dry_run", "yes", "json"}),
    "server": frozenset({"port", "rotate_token", "yes"}),
    # text-to-cad set up in the agent apps, and `update`, the same command: its plan, what it may do,
    # for which apps; and `uninstall`, which takes it out again.
    "setup": frozenset({"dry_run", "only", "no_telemetry", "json", "engine_update"}),
    # `update` runs the newest release's `setup` with its options; the switch's helper is its own.
    "update": frozenset({"dry_run", "only", "no_telemetry", "json", "switch", "port", "previous"}),
    # Automatic updates, the person's setting: status, on or off (a verb of its own, as `update`'s options
    # are what every release hands its newer one).
    "update auto": frozenset({"action"}),
    "uninstall": frozenset({"dry_run", "only", "purge", "yes", "json"}),
    # The plugin folder written from the current installation, and the apps' copies of it with --refresh.
    "plugin": frozenset({"refresh", "json"}),
    # The exact cad requirement for a Python of a program's own: its integrations, and --json.
    "requirement": frozenset({"integrations", "json"}),
}

# Commands that own their parser outright and mirror no function.
UNCLASSIFIED = {
    "doctor",
    # uv run's options and a program's arguments, whatever they are: no parser of its own (uv judges them).
    "run",
    # The viewer launcher owns its parser: the launch contract (reuse, replace or start on its
    # one port, the --json announce line) is not a function signature to mirror.
    "viewer",
}

HEAVY = ("OCP", "build123d", "ezdxf", "shapely")


def _verb(target: tuple[str, str]):
    module, attribute = target
    return getattr(importlib.import_module(module), attribute)


def _commands() -> set[str]:
    """Every command the dispatcher answers: each document type's operations, and the rest."""
    from cad_server.cli.document_types import OPERATIONS

    return {*cli._COMMANDS, *(f"{document_type} {operation}" for document_type, operation in OPERATIONS)}


def _adapter_surface(name: str) -> frozenset[str]:
    """One adapter command's real option surface, read off the command itself: its destinations
    plus its subcommand names, which is where a subcommand tree's meaning lives."""
    parser = cli.build_parser_for(name)
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

    def test_every_public_verb_is_fully_annotated_and_derivable(self):
        for module_name, verbs in PUBLIC_SURFACE.items():
            for verb in verbs:
                with self.subTest(verb=f"{module_name}.{verb}"):
                    func = _verb((module_name, verb))
                    signature = inspect.signature(func)
                    unannotated = [name for name, parameter in signature.parameters.items()
                                   if parameter.annotation is parameter.empty]
                    self.assertEqual([], unannotated)
                    self.assertIsNot(signature.return_annotation, signature.empty)
                    # Derivability is the CLASSIFICATION: a mirror's parser is generated from this
                    # signature, and an adapter exists precisely because its verb cannot be.
                    if (module_name, verb) in set(MIRRORS.values()):
                        cli_from_function(func, prog="probe")
                    else:
                        with self.assertRaises(NotDerivable):
                            cli_from_function(func, prog="probe")

    def test_the_retired_commands_are_gone(self):
        # No backwards compatibility: a retired command has no entry and no module, so it gets the
        # same answer as any unknown command.
        for command in ("build", "step build", "step compile", "stl build", "3mf build", "3mf snapshot", "glb build",
                        "store", "daemon", "daemon status", "where", "install", "mcp", "export", "snapshot", "inspect",
                        "urdf check", "sdf check", "srdf check", "stl check", "xbf check", "kicad_pcb check",
                        "kicad_sch check", "pcb drc"):
            self.assertNotIn(command, _commands())
        for module in ("cad_server.cli.build", "cad.engine.shape_input", "cad_server.cli.step_build", "cad_server.cli.step_snapshot", "cad_server.cli.stl_build",
                       "cad_server.cli.where", "cad_server.cli.store", "cad_server.cli.daemon", "cad_server.cli.daemon_status", "cadgen.store", "cadgen.daemon",
                       "cad_server.cli.install", "cad_server.cli.mcp", "cad_server.cli.export", "cad_server.cli.snapshot",
                       "cad_server.cli.inspect", "cad_server.cli.urdf_validate", "cad_server.cli.sdf_validate",
                       "cad_server.cli.srdf_validate", "cad_server.kicad.schematic"):
            with self.subTest(module=module), self.assertRaises(ModuleNotFoundError):
                importlib.import_module(module)

    def _dispatch(self, *argv: str) -> tuple[int, str, str]:
        import contextlib
        import io

        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def test_a_known_format_with_a_wrong_verb_lists_that_formats_verbs(self):
        for noun, verbs in {"urdf": ("validate", "snapshot"), "srdf": ("validate", "snapshot")}.items():
            for rest in (("bogus",), ()):
                with self.subTest(noun=noun, rest=rest):
                    code, out, err = self._dispatch(noun, *rest)
                    self.assertEqual(2, code)
                    self.assertEqual("", out)
                    # The NOUN is right: it is never reported as the unknown thing.
                    self.assertNotIn(f"unknown command {noun!r}", err)
                    # Its verbs and no other: in the one line said of a verb it does not have, which points at
                    # the type's help, never prints it; in that help after a command line that names none.
                    listed = (err.partition("; it has ")[2].partition(";")[0] if rest
                              else err.split("operations:")[1])
                    for verb in verbs:
                        self.assertIn(verb, listed)
                    self.assertNotIn("export", listed)
                    if rest:
                        self.assertNotIn("usage:", err)
                        self.assertIn(f"'cad {noun} --help' says what each does", err)
                    else:
                        self.assertIn(f"usage: cad {noun} <operation>", err)

    def test_a_formats_help_lists_its_verbs_and_exits_zero(self):
        code, out, err = self._dispatch("urdf", "--help")
        self.assertEqual((0, ""), (code, err))
        self.assertIn("\n  validate ", out)
        self.assertNotIn("export", out.split("operations:")[1])

    def test_an_unknown_noun_names_it_and_where_the_commands_are(self):
        # Never the whole list: the word, at most one suggestion, and the help that lists them.
        code, out, err = self._dispatch("frobnicate", "export")
        self.assertEqual((2, ""), (code, out))
        self.assertEqual("cad: unknown command 'frobnicate'; 'cad --help' lists the commands\n", err)
        code, out, err = self._dispatch("stauts")
        self.assertEqual(2, code)
        self.assertEqual("cad: unknown command 'stauts' (did you mean 'status'?); 'cad --help' lists the commands\n",
                         err)

    def test_a_name_that_is_not_a_verb_raises_the_plain_attribute_error(self):
        # No retired-surface recognition: the answer is Python's own error, not a note about history.
        urdf = importlib.import_module("cad.urdf")
        with self.assertRaises(AttributeError) as caught:
            urdf.export  # noqa: B018 - the attribute access IS the assertion
        self.assertIn("export", str(caught.exception))
        self.assertNotIn("deleted", str(caught.exception))

    def test_the_engines_verbs_are_commands_of_their_own(self):
        # One parser per verb, the engine's (cad_server.engine.cli), named by the command that runs it.
        for verb in ("xbf export", "stl snapshot", "serve", "step inspect", "status", "stop", "delete", "server"):
            with self.subTest(verb=verb):
                self.assertEqual(cli.build_parser_for(verb).prog, f"cad {verb}")

    def test_every_verb_goes_through_the_engine(self):
        # No command runs a build or a verb in its own process: --no-daemon is an unrecognized argument like any
        # other. daemon=False is the Python functions' seam for tests and debugging alone.
        for argv in (("xbf", "export", "a.xbf", "a.stl", "--no-daemon"), ("xbf", "snapshot", "a.xbf", "a.png", "--no-daemon")):
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
                dests = set(parser_dests(cli.build_parser_for(command))) - {JSON_FLAG_DEST}
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
            f"for name in {commands!r}:\n"
            "    cli.build_parser_for(name).format_help()\n"
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
