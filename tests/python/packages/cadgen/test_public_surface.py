"""The public verb surface, and the CLIs that mirror it (design/format-doors.md).

Three properties that only hold if something checks them:

* **The manifest.** Exactly the declared names are public on each format
  namespace, and every public verb is fully annotated — annotation is what
  makes a CLI derivable, so an unannotated parameter is a silently
  undispatchable flag.
* **Signature sync.** For every command, the parser's options ARE the
  function's parameters, modulo an explicit per-command allowlist that is
  EMPTY for mirrors. This fails on a one-sided addition in either direction,
  which doubles as shell-thinness enforcement: a CLI that grew a flag its verb
  cannot express has stopped being a shell.
* **The import budget.** A public namespace must import without the CAD stack.
  A model script pays this import before its freshness gate runs (~0.2s), and
  waking OCP there would cost seconds on every already-current model.
"""

from __future__ import annotations

import argparse
import importlib
import inspect
import subprocess
import sys
import unittest
from pathlib import Path

from cadgen import cli
from cadgen._internal.cli_from_function import (
    JSON_FLAG_DEST,
    NotDerivable,
    cli_from_function,
    function_parameters,
    parser_dests,
)

# The manifest: format namespace -> exactly the verbs it exports.
PUBLIC_SURFACE: dict[str, tuple[str, ...]] = {
    "cadgen.step": ("build", "compile", "inspect", "snapshot"),
    "cadgen.stl": ("build", "snapshot"),
    "cadgen.threemf": ("build", "snapshot"),
    "cadgen.glb": ("build", "snapshot"),
    "cadgen.dxf": ("snapshot",),
    "cadgen.urdf": ("snapshot", "validate"),
    # An SRDF's geometry comes from the URDF beside it, so it has no snapshot
    # door of its own; `cadgen snapshot` still routes one by suffix.
    "cadgen.srdf": ("validate",),
    "cadgen.sdf": ("snapshot", "validate"),
}

# The format namespaces that are ALSO their declaration decorator. The robot
# families are not: a description is an authored file, so there is nothing to
# declare and nothing to decorate.
DECORATOR_NAMESPACES = ("step", "dxf", "stl", "threemf", "glb")

# Commands whose parser is GENERATED from the verb it calls. No allowlist is
# possible here: the parser has no independent existence.
MIRRORS: dict[str, tuple[str, str]] = {
    "step build": ("cadgen.step", "build"),
    "step compile": ("cadgen.step", "compile"),
    "stl build": ("cadgen.stl", "build"),
    "3mf build": ("cadgen.threemf", "build"),
    "glb build": ("cadgen.glb", "build"),
    "sdf validate": ("cadgen.sdf", "validate"),
    "srdf validate": ("cadgen.srdf", "validate"),
    # Snapshot was the schema's LAST adapter. Its rich options are typed
    # `str | dict | None` — one string CLI-side, a real dict library-side — so
    # there is nothing left to declare: the structural check below is the whole
    # contract, and the seven doors differ by SIGNATURE rather than by a
    # runtime kind gate on one shared surface.
    "step snapshot": ("cadgen.step", "snapshot"),
    "stl snapshot": ("cadgen.stl", "snapshot"),
    "3mf snapshot": ("cadgen.threemf", "snapshot"),
    "glb snapshot": ("cadgen.glb", "snapshot"),
    "dxf snapshot": ("cadgen.dxf", "snapshot"),
    "urdf snapshot": ("cadgen.urdf", "snapshot"),
    "sdf snapshot": ("cadgen.sdf", "snapshot"),
    # The polymorphic door's verb has no format namespace to live on: there is
    # no polymorphic FORMAT, only a routing convenience over the seven real
    # doors, so it is bound beside its command.
    "snapshot": ("cadgen.cli.snapshot", "snapshot"),
}

# Commands with a HAND-WRITTEN parser, and the option surface each one owns. An
# adapter has no generated parser to compare against a signature — inspect's
# subcommand tree is exactly what disqualifies it from mirror status — so the
# declaration IS the contract, and a flag or subcommand that appears without
# being declared here fails.
#
# For a parser with subcommands the surface is its top-level options plus the
# subcommand names: pinning every leaf flag of `step inspect` would be a copy of
# the CLI in a test file, which is churn rather than a guard.
ADAPTERS: dict[str, frozenset[str]] = {
    # The one validator that cannot be a mirror: `--packages NAME=PATH` is
    # repeatable, and a repeatable key/value map is outside the derivable set.
    "urdf validate": frozenset({"path", "strict", "packages", "verbose"}),
    "step inspect": frozenset(
        {
            "verbose",
            "command",
            "refs",
            "diff",
            "frame",
            "measure",
            "align",
            "interfere",
            "validate",
        }
    ),
}

# Commands not yet re-homed under the schema. This set only shrinks.
UNCLASSIFIED = {
    "doctor",
    "cache",
    "daemon",
    "daemon status",
    # The viewer launcher owns its parser: the launch contract (reuse-or-start,
    # port roll, the --json announce line) is not a function signature to mirror.
    "viewer",
    "viewer list",
    "viewer stop",
}

HEAVY = ("OCP", "build123d", "ezdxf", "shapely")


def _verb(target: tuple[str, str]):
    module, attribute = target
    return getattr(importlib.import_module(module), attribute)


def _adapter_surface(module) -> frozenset[str]:
    """One adapter command's real option surface, read off the command itself.

    Every adapter left is an argparse command, so it answers with its
    destinations plus its subcommand names — which is where a subcommand tree's
    meaning lives. There is no longer a command that parses argv by hand.
    """
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
                    unannotated = [
                        name
                        for name, parameter in signature.parameters.items()
                        if parameter.annotation is parameter.empty
                    ]
                    self.assertEqual([], unannotated)
                    self.assertIsNot(signature.return_annotation, signature.empty)
                    # Derivability is the CLASSIFICATION: a mirror's parser is
                    # generated from this signature, and an adapter exists
                    # precisely because its verb cannot be. Asserting both
                    # directions keeps the classification honest — an adapter
                    # whose verb became derivable should go back to being a
                    # mirror rather than keep a hand-written parser.
                    if (module_name, verb) in set(MIRRORS.values()):
                        cli_from_function(func, prog="probe")
                    else:
                        with self.assertRaises(NotDerivable):
                            cli_from_function(func, prog="probe")

    def test_a_format_namespace_is_also_its_decorator(self):
        # `from cadgen import step` must keep declaring models: the namespace
        # module and the decorator are ONE object, so importing the verbs can
        # never shadow the authoring API.
        import cadgen

        for name in DECORATOR_NAMESPACES:
            with self.subTest(format=name):
                namespace = getattr(cadgen, name)
                self.assertIs(namespace, importlib.import_module(f"cadgen.{name}"))
                self.assertTrue(callable(namespace))

    def test_a_decorated_namespace_still_declares(self):
        # The callable module must reach the SAME decorator `cadgen.authoring`
        # exports, or a model script would declare into a different registry.
        import cadgen
        from cadgen import authoring

        def model():
            return None

        this_file = Path(__file__).resolve()
        self.addCleanup(authoring._REGISTRY.pop, this_file, None)
        cadgen.stl(out="declared.stl")(model)
        cadgen.step(model)
        declared = authoring.registered_model(this_file)
        self.assertEqual({d.fmt for d in declared.mesh_exports}, {"stl"})

    def test_the_retired_commands_are_gone(self):
        # No backwards compatibility: `cadgen import` folded into the STEP
        # door, `cadgen step export` into the three per-format doors, and
        # `cadgen dxf build` was deleted outright.
        self.assertNotIn("import", cli._COMMANDS)
        self.assertNotIn("step export", cli._COMMANDS)
        self.assertNotIn("dxf build", cli._COMMANDS)
        for module in ("cadgen.cli.step_import", "cadgen.cli.step_export", "cadgen.cli.dxf_build"):
            with self.subTest(module=module), self.assertRaises(ModuleNotFoundError):
                importlib.import_module(module)

    def test_a_name_that_is_not_a_door_raises_the_plain_attribute_error(self):
        # No retired-surface recognition: `cadgen.dxf` has no `build` door, and
        # the answer is Python's own error, not a note about history.
        dxf = importlib.import_module("cadgen.dxf")
        with self.assertRaises(AttributeError) as caught:
            dxf.build  # noqa: B018 - the attribute access IS the assertion
        message = str(caught.exception)
        self.assertIn("build", message)
        self.assertNotIn("was deleted", message)


class SignatureSync(unittest.TestCase):
    def test_every_command_is_classified(self):
        classified = set(MIRRORS) | set(ADAPTERS) | UNCLASSIFIED
        self.assertEqual(
            set(cli._COMMANDS),
            classified,
            "a new command must be declared a mirror, an adapter, or explicitly unclassified",
        )

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
        imports = "; ".join(f"import {name}" for name in PUBLIC_SURFACE)
        code = (
            f"import sys; {imports};"
            f"print('HEAVY:' + ','.join(m for m in {HEAVY!r} if m in sys.modules))"
        )
        proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("HEAVY:\n", proc.stdout)

    def test_a_generated_clis_help_does_not_wake_the_cad_stack(self):
        for command in MIRRORS:
            with self.subTest(command=command):
                module_name, _ = cli._COMMANDS[command]
                code = (
                    "import sys, contextlib, io;"
                    f"import {module_name} as m;"
                    "err=io.StringIO();"
                    "contextlib.suppress(SystemExit).__enter__();"
                    "m.build_parser().format_help();"
                    f"print('HEAVY:' + ','.join(x for x in {HEAVY!r} if x in sys.modules))"
                )
                proc = subprocess.run(
                    [sys.executable, "-c", code], capture_output=True, text=True
                )
                self.assertEqual(proc.returncode, 0, proc.stderr)
                self.assertIn("HEAVY:\n", proc.stdout)


if __name__ == "__main__":
    unittest.main()
