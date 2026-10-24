"""What `from cadgen import ...` offers, and what it costs.

Two properties that are easy to break together. Every name in ``__all__`` must actually
resolve -- the lazy ``__getattr__`` dispatches on hand-written name sets, so adding a name
to ``__all__`` and forgetting the branch advertises an AttributeError. And importing the
package must stay cheap: the whole point of the lazy dispatch is that `import cadgen`
does not pay for OCP, which costs seconds and is useless to a caller who only wanted
`__version__`.
"""

import subprocess
import sys
import unittest

import cadgen
import cadgen.engine.model

HEAVY = ("OCP", "build123d")

# The engine's names the root re-exports, and the operations on documents as functions; process
# control (serve, status, stop, daemon) is the CLI's alone.
ENGINE = ("model", "xbf", "step", "glb", "stl", "threemf", "dxf", "memo", "Material", "materials", "paint",
          "read_step", "read_xbf", "read_mesh")
VERBS = ("export", "snapshot", "inspect")
ROOT = (*ENGINE, *VERBS, "__version__")
# The names that are the standards' rather than the engine's.
NAMESPACES = {
    "cadgen.ap242": ("mechanism_state", "configuration_sequence", "gear_pair", "rack_and_pinion_pair", "screw_pair",
                     "posed"),
    "cadgen.gltf": ("animation",),
}


class RootExports(unittest.TestCase):
    def test_every_advertised_name_resolves(self):
        unresolvable = [name for name in cadgen.__all__ if not hasattr(cadgen, name)]
        self.assertEqual([], unresolvable, "in __all__ but not handled by __getattr__")

    def test_the_root_is_exactly_its_declared_names(self):
        """A model imports what it needs from ``cadgen`` itself: the engine's names, each the very
        object ``cadgen.engine`` exports, and the verbs on documents as functions."""
        import cadgen.engine
        from cadgen.engine import api

        self.assertEqual(sorted(ROOT), sorted(cadgen.__all__))
        self.assertEqual(sorted(cadgen.engine.__all__), sorted(ENGINE))
        for name in ENGINE:
            with self.subTest(name=name):
                self.assertIs(getattr(cadgen, name), getattr(cadgen.engine, name))
        for verb in VERBS:
            with self.subTest(verb=verb):
                self.assertIs(getattr(cadgen, verb), getattr(api, verb))

    def test_snapshot_is_one_verb_of_two_input_shapes(self):
        """One picture (``source``, ``out``) or every picture a job names (``job``, ``source`` in place of its
        input); no ``snapshot_job``, and any other call refused as Python refuses one."""
        import inspect

        from cadgen.engine import api

        parameters = inspect.signature(cadgen.snapshot).parameters
        self.assertEqual(list(parameters)[:3], ["source", "out", "job"])
        self.assertEqual(parameters["job"].kind, inspect.Parameter.KEYWORD_ONLY)
        self.assertFalse(hasattr(api, "snapshot_job"))
        self.assertNotIn("snapshot_job", api.__all__)
        for call in (lambda: cadgen.snapshot(), lambda: cadgen.snapshot("a.xbf"),
                     lambda: cadgen.snapshot("a.xbf", "a.png", job={"jobs": []})):
            with self.subTest(call=call), self.assertRaises(TypeError):
                call()

    def test_each_namespace_is_exactly_its_declared_names(self):
        import importlib

        from cadgen.engine import mechanism, model

        defined = {"mechanism_state": model, "configuration_sequence": model, "animation": model,
                   "gear_pair": mechanism, "rack_and_pinion_pair": mechanism, "screw_pair": mechanism,
                   "posed": mechanism}
        for namespace, names in NAMESPACES.items():
            module = importlib.import_module(namespace)
            self.assertEqual(sorted(names), sorted(module.__all__))
            for name in names:
                with self.subTest(name=f"{namespace}.{name}"):
                    self.assertIs(getattr(module, name), getattr(defined[name], name))
                    self.assertFalse(hasattr(cadgen, name), f"{name} is {namespace}'s, not the root's")

    def test_model_declares_a_function_or_hands_a_shape_over_and_a_decorator_takes_its_path(self):
        """``model`` is one name of two forms: a decorator (``@model``, ``@model(store=, key=)``) and the
        shape form (``model(shape, name=, key=, animations=)``); a file decorator takes its path, its
        store and its key. No ``id=``: an id is derived, or a key's."""
        import inspect

        parameters = inspect.signature(cadgen.engine.model.model).parameters
        self.assertEqual([(name, p.kind) for name, p in parameters.items()], [
            ("target", inspect.Parameter.POSITIONAL_ONLY), ("store", inspect.Parameter.KEYWORD_ONLY),
            ("key", inspect.Parameter.KEYWORD_ONLY), ("name", inspect.Parameter.KEYWORD_ONLY),
            ("animations", inspect.Parameter.KEYWORD_ONLY)])
        for kind in ("xbf", "step", "glb", "stl", "threemf", "dxf"):
            with self.subTest(kind=kind):
                self.assertEqual(list(inspect.signature(getattr(cadgen, kind)).parameters), ["out", "store", "key"])

    def test_a_name_the_root_never_had_is_pythons_own_error(self):
        # No backwards compatibility: a retired name is no name, and says nothing about history.
        # ``build`` among them: a model builds by a decorated function's call, never cadgen.build (law 12).
        for name in ("build", "read_scene", "AssemblyHelper", "label_shape", "revolute", "compound_from_instances",
                     "mechanism_state", "animation", "select", "report", "track", "serve", "status", "stop",
                     "daemon", "server", "srgb", "srgb_to_linear", "linear_to_srgb", "build123d"):
            with self.subTest(name=name), self.assertRaises(AttributeError) as caught:
                getattr(cadgen, name)
            self.assertEqual(str(caught.exception), f"module 'cadgen' has no attribute {name!r}")

    def test_importing_cadgen_does_not_import_the_cad_stack(self):
        """Run in a subprocess: this one almost certainly has OCP loaded already."""
        code = (
            "import sys, cadgen, cadgen.ap242, cadgen.gltf;"
            f"print('HEAVY:' + ','.join(m for m in {HEAVY!r} if m in sys.modules))"
        )
        proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        marked = [ln for ln in proc.stdout.splitlines() if ln.startswith("HEAVY:")]
        self.assertEqual(["HEAVY:"], marked, "importing cadgen pulled in the CAD stack")

    def test_model_body_helpers_do_not_import_the_cad_stack(self):
        """`from cadgen import flatten` sits in a model's MODULE BODY, so the module behind it
        must defer the kernel -- its `import build123d` bound lazily (`_internal/lazy_kernel.py`)
        -- or every such model pays the ~2.5s import in the process that only asks the daemon to
        build it."""
        code = (
            "import sys, cadgen.flatten;"
            "from cadgen import flatten;"
            "from cadgen._internal.lazy_kernel import loaded;"
            f"print('HEAVY:' + ','.join(m for m in {HEAVY!r} if loaded(m)))"
        )
        proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        marked = [ln for ln in proc.stdout.splitlines() if ln.startswith("HEAVY:")]
        self.assertEqual(["HEAVY:"], marked, "cadgen.flatten imported the kernel at module scope")


if __name__ == "__main__":
    unittest.main()
