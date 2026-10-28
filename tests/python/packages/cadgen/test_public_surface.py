"""The public verb surface, and the CLIs that mirror it.

Three properties that only hold if something checks them:

* **The manifest.** Exactly the declared names are public on each robot namespace, and every
  public verb is fully annotated -- annotation is what makes a CLI derivable, so an unannotated
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

from cadgen import cli
from cadgen._internal.cli_from_function import (
    JSON_FLAG_DEST,
    NotDerivable,
    cli_from_function,
    function_parameters,
    parser_dests,
)

# The manifest: robot namespace -> exactly the verbs it exports. A robot description is an
# authored file, so there is nothing to declare; each format's snapshot is the engine's.
PUBLIC_SURFACE: dict[str, tuple[str, ...]] = {
    "cadgen.urdf": ("validate",),
    "cadgen.srdf": ("validate",),
    "cadgen.sdf": ("validate",),
}

# Commands whose parser is GENERATED from the verb it calls. No allowlist is possible here:
# the parser has no independent existence.
MIRRORS: dict[str, tuple[str, str]] = {
    "sdf validate": ("cadgen.sdf", "validate"),
    "srdf validate": ("cadgen.srdf", "validate"),
}

# The engine snapshot's options (``cadgen.engine.snapshot``), which every format's snapshot
# command takes: one parser, one picture.
SNAPSHOT = frozenset({"document", "out", "job", "display", "grid", "camera", "width", "height",
                      "size_profile", "pose", "annotation", "measurements", "json"})

# Commands with a HAND-WRITTEN parser, and the option surface each one owns. An adapter has no
# generated parser to compare against a signature, so the declaration IS the contract, and a
# flag or subcommand that appears without being declared here fails.
ADAPTERS: dict[str, frozenset[str]] = {
    # The one validator that cannot be a mirror: `--packages NAME=PATH` is repeatable, and a
    # repeatable key/value map is outside the derivable set.
    "urdf validate": frozenset({"path", "strict", "packages", "verbose"}),
    # Each format's snapshot is the engine's, for that format's files alone.
    "dxf snapshot": SNAPSHOT,
    "urdf snapshot": SNAPSHOT,
    "sdf snapshot": SNAPSHOT,
    # A host starts it and speaks MCP on its standard streams; it takes no options. Where the
    # install came from is in the server's environment, which the plugin's startup config sets.
    "mcp": frozenset(),
    # The person's telemetry choice: status, on or off.
    "telemetry": frozenset({"action"}),
    # The engine's verbs (cadgen.engine.cli), each a command of its own.
    "export": frozenset({"source", "destinations", "json"}),
    "snapshot": SNAPSHOT,
    "serve": frozenset({"document", "port", "three"}),
    "inspect": frozenset({"document", "ref", "query", "json"}),
    "status": frozenset({"json"}),
    "stop": frozenset({"json"}),
    "delete": frozenset({"documents", "json"}),
    "server": frozenset({"port", "rotate_token"}),
}

# Commands that own their parser outright and mirror no function.
UNCLASSIFIED = {
    "doctor",
    # The installation's python with the arguments, whatever they are: no parser of its own.
    "run",
    # The viewer launcher owns its parser: the launch contract (reuse, replace or start on its
    # one port, the --json announce line) is not a function signature to mirror.
    "viewer",
}

HEAVY = ("OCP", "build123d", "ezdxf", "shapely")


def _verb(target: tuple[str, str]):
    module, attribute = target
    return getattr(importlib.import_module(module), attribute)


def _adapter_surface(module) -> frozenset[str]:
    """One adapter command's real option surface, read off the command itself: its destinations
    plus its subcommand names, which is where a subcommand tree's meaning lives."""
    parser = module.build_parser()
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
        for command in ("build", "step build", "step compile", "step snapshot", "stl build", "stl snapshot", "3mf build",
                        "3mf snapshot", "glb build", "glb snapshot", "store", "daemon", "daemon status", "xbf", "where"):
            self.assertNotIn(command, cli._COMMANDS)
        for module in ("cadgen.cli.build", "cadgen.engine.shape_input", "cadgen.cli.step_build", "cadgen.cli.step_snapshot", "cadgen.cli.stl_build",
                       "cadgen.cli.where", "cadgen.cli.store", "cadgen.cli.daemon", "cadgen.cli.daemon_status", "cadgen.step", "cadgen.store", "cadgen.daemon"):
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
        for noun, verbs in {"urdf": ("urdf validate", "urdf snapshot"), "srdf": ("srdf validate",),
                            "dxf": ("dxf snapshot",)}.items():
            for rest in (("bogus",), ()):
                with self.subTest(noun=noun, rest=rest):
                    code, out, err = self._dispatch(noun, *rest)
                    self.assertEqual(2, code)
                    self.assertEqual("", out)
                    # The NOUN is right: it is never reported as the unknown thing.
                    self.assertNotIn(f"unknown command {noun!r}", err)
                    self.assertIn(f"usage: cadgen {noun} <verb>", err)
                    for verb in verbs:
                        self.assertIn(verb, err)
                    self.assertNotIn("sdf validate" if noun == "urdf" else "urdf validate", err)

    def test_a_formats_help_lists_its_verbs_and_exits_zero(self):
        code, out, err = self._dispatch("urdf", "--help")
        self.assertEqual((0, ""), (code, err))
        self.assertIn("urdf validate", out)
        self.assertIn("urdf snapshot", out)
        self.assertNotIn("sdf validate", out)

    def test_an_unknown_noun_lists_every_command(self):
        code, out, err = self._dispatch("frobnicate", "export")
        self.assertEqual(2, code)
        self.assertIn("unknown command 'frobnicate'", err)
        for command in ("export", "snapshot", "dxf snapshot", "urdf validate", "viewer", "inspect"):
            self.assertIn(command, err)

    def test_a_name_that_is_not_a_verb_raises_the_plain_attribute_error(self):
        # No retired-surface recognition: the answer is Python's own error, not a note about history.
        urdf = importlib.import_module("cadgen.urdf")
        with self.assertRaises(AttributeError) as caught:
            urdf.snapshot  # noqa: B018 - the attribute access IS the assertion
        self.assertIn("snapshot", str(caught.exception))
        self.assertNotIn("deleted", str(caught.exception))

    def test_the_engines_verbs_are_commands_of_their_own(self):
        # One parser per verb, the engine's (cadgen.engine.cli), named by the command that runs it.
        for verb in ("export", "snapshot", "serve", "inspect", "status", "stop", "delete", "server"):
            with self.subTest(verb=verb):
                module = importlib.import_module(cli._COMMANDS[verb][0])
                self.assertEqual(module.build_parser().prog, f"cadgen {verb}")

    def test_every_verb_goes_through_the_engine(self):
        # No command runs a build or a verb in its own process: --no-daemon is an unrecognized argument like any
        # other. daemon=False is the Python functions' seam for tests and debugging alone.
        for argv in (("export", "a.xbf", "a.stl", "--no-daemon"), ("snapshot", "a.xbf", "a.png", "--no-daemon"),
                     ("dxf", "snapshot", "a.dxf", "a.png", "--no-daemon")):
            with self.subTest(argv=argv):
                err = io.StringIO()
                with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()), \
                        self.assertRaises(SystemExit) as caught:
                    cli.main(list(argv))
                self.assertEqual(caught.exception.code, 2)
                self.assertIn("unrecognized arguments: --no-daemon", err.getvalue())
        from cadgen.engine import api

        for verb in (api.export, api.snapshot):
            self.assertIn("daemon", inspect.signature(verb).parameters)

    def test_a_format_snapshot_draws_its_own_files_alone(self):
        # `cadgen dxf snapshot` is the engine's snapshot for a .dxf: any other file is refused by
        # name before anything renders.
        code, out, err = self._dispatch("dxf", "snapshot", "part.step", "out.png")
        self.assertEqual((code, out), (2, ""))
        self.assertIn("cadgen dxf snapshot: part.step is not a .dxf file", err)


class SignatureSync(unittest.TestCase):
    def test_every_command_is_classified(self):
        classified = set(MIRRORS) | set(ADAPTERS) | UNCLASSIFIED
        self.assertEqual(set(cli._COMMANDS), classified,
                         "a new command must be declared a mirror, an adapter, or explicitly unclassified")

    def test_a_mirrors_parser_is_exactly_its_signature(self):
        for command, target in MIRRORS.items():
            with self.subTest(command=command):
                module_name, _ = cli._COMMANDS[command]
                module = importlib.import_module(module_name)
                dests = set(parser_dests(module.build_parser())) - {JSON_FLAG_DEST}
                self.assertEqual(set(function_parameters(_verb(target))), dests)

    def test_an_adapters_option_surface_is_exactly_what_it_declares(self):
        for command, declared in ADAPTERS.items():
            with self.subTest(command=command):
                module_name, _ = cli._COMMANDS[command]
                module = importlib.import_module(module_name)
                self.assertEqual(declared, _adapter_surface(module))


class ImportBudget(unittest.TestCase):
    """Run in a subprocess: this one has the CAD stack loaded already."""

    def test_public_namespaces_import_without_the_cad_stack(self):
        imports = "; ".join(f"import {name}" for name in (*PUBLIC_SURFACE, "cadgen.geometry"))
        code = f"import sys; {imports}; print('HEAVY:' + ','.join(m for m in {HEAVY!r} if m in sys.modules))"
        proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("HEAVY:\n", proc.stdout)

    def test_a_commands_help_does_not_wake_the_cad_stack(self):
        # Every command's help in one interpreter, in turn: the first that loads the stack is named
        # (the ones after it cannot be told apart, and the run fails on the first).
        modules = [cli._COMMANDS[command][0] for command in (*MIRRORS, *ADAPTERS)]
        code = (
            "import importlib, sys\n"
            f"for name in {modules!r}:\n"
            "    importlib.import_module(name).build_parser().format_help()\n"
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
