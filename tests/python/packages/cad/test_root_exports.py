"""What `from cad import ...` offers, and what it costs.

Two properties that are easy to break together. Every name in ``__all__`` must actually
resolve -- the lazy ``__getattr__`` dispatches on hand-written name sets, so adding a name
to ``__all__`` and forgetting the branch advertises an AttributeError. And importing the
package must stay cheap: the whole point of the lazy dispatch is that `import cad`
does not pay for OCP, which costs seconds and is useless to a caller who only wanted
`__version__`.
"""

import subprocess
import sys
import unittest

import cad
import cad.engine.model

HEAVY = ("OCP", "build123d")

# The engine's own surface (``cad.engine``), which the library's namespaces are made of.
ENGINE = ("model", "xbf", "step", "glb", "stl", "threemf", "dxf", "memo", "paint",
          "read_step", "read_xbf", "read_mesh")
# The root: the model, the version, the deprecation's class, and the document types.
TYPES = ("xbf", "step", "stl", "glb", "threemf", "dxf", "urdf", "srdf", "sdf", "kicad_pcb", "kicad_sch")
ROOT = ("model", "__version__", "CadDeprecationWarning", *TYPES)
# The build123d integration's names: our helpers that take build123d's objects.
NAMESPACES = {
    "cad.build123d": ("mechanism_state", "configuration_sequence", "gear_pair", "rack_and_pinion_pair", "screw_pair",
                      "posed", "animation", "memo", "paint", "GeometryError", "GeometryIssue", "ClosestPoints",
                      "MassProperties", "closest_points", "overlap_volume", "is_sound", "topology_errors",
                      "boundary_edges", "self_intersections", "mass_properties", "flat_pattern", "planar_faces",
                      "flatten_face", "flatten_faces", "union_faces", "offset_profile"),
}


class RootExports(unittest.TestCase):
    def test_every_advertised_name_resolves(self):
        unresolvable = [name for name in cad.__all__ if not hasattr(cad, name)]
        self.assertEqual([], unresolvable, "in __all__ but not handled by __getattr__")

    def test_the_root_is_exactly_its_declared_names(self):
        """A model imports ``model`` and the document types from ``cad`` itself: each type one object,
        its decorator, its reader and its operations (``cad._internal.document_type``)."""
        import cad.engine
        from cad._internal.document_type import DocumentType
        from cad.engine import api

        self.assertEqual(sorted(ROOT), sorted(cad.__all__))
        self.assertEqual(sorted(cad.engine.__all__), sorted(ENGINE))
        self.assertIs(cad.model, cad.engine.model)
        for name in ("Material", "materials"):
            self.assertFalse(hasattr(cad.engine, name), f"materials come from bd_materials: {name}")
        for name in TYPES:
            with self.subTest(name=name):
                self.assertIsInstance(getattr(cad, name), DocumentType)
        self.assertIs(cad.step.read, cad.engine.model.read_step)
        self.assertIs(cad.xbf.read, cad.engine.read_xbf)
        self.assertIs(cad.stl.read, cad.engine.read_mesh)
        self.assertIs(cad.urdf.check, cad.urdf.__dict__["check"])
        self.assertTrue(cad.xbf.export.__doc__.endswith(api.export.__doc__))

    def test_what_the_root_says_of_its_types_is_what_it_has(self):
        """Every type is in the root's docstring and in the imports type checkers read, and no type that
        has a decorator says it has none."""
        import ast
        import inspect

        from cad.registry import DOCUMENT_TYPES

        tree = ast.parse(inspect.getsource(cad))
        checked = {alias.asname or alias.name for node in ast.walk(tree) if isinstance(node, ast.If)
                   and getattr(node.test, "id", "") == "_TYPE_CHECKING" for child in node.body
                   if isinstance(child, ast.ImportFrom) for alias in child.names}
        for name in TYPES:
            with self.subTest(name=name):
                self.assertIn(name, checked, "a type type checkers do not see")
                self.assertIn(f"``{name}``", cad.__doc__)
                if DOCUMENT_TYPES[name].decorator:
                    self.assertNotIn("no decorator", " ".join(getattr(cad, name).__doc__.split()))

    def test_snapshot_is_one_verb_of_two_input_shapes(self):
        """One picture (``source``, ``out``) or every picture a job names (``job``, ``source`` in place of its
        input); no ``snapshot_job``, and any other call refused as Python refuses one."""
        import inspect

        from cad.engine import api

        parameters = inspect.signature(api.snapshot).parameters
        self.assertEqual(list(parameters)[:3], ["source", "out", "job"])
        self.assertEqual(parameters["job"].kind, inspect.Parameter.KEYWORD_ONLY)
        self.assertFalse(hasattr(api, "snapshot_job"))
        self.assertNotIn("snapshot_job", api.__all__)
        for call in (lambda: api.snapshot(), lambda: api.snapshot("a.xbf"),
                     lambda: api.snapshot("a.xbf", "a.png", job={"jobs": []})):
            with self.subTest(call=call), self.assertRaises(TypeError):
                call()

    def test_each_namespace_is_exactly_its_declared_names(self):
        import importlib

        from cad.build123d import _flatten, _geometry
        from cad.engine import mechanism, model
        from cad.engine.formats.kicad import board_index, geometry, summary

        defined = {"mechanism_state": model, "configuration_sequence": model, "animation": model, "memo": model,
                   "paint": model, "gear_pair": mechanism, "rack_and_pinion_pair": mechanism,
                   "screw_pair": mechanism, "posed": mechanism,
                   **{name: _geometry for name in _geometry.__all__},
                   **{name: _flatten for name in NAMESPACES["cad.build123d"] if hasattr(_flatten, name)}}
        for namespace, names in NAMESPACES.items():
            module = importlib.import_module(namespace)
            self.assertEqual(sorted(names), sorted(module.__all__))
            for name in names:
                with self.subTest(name=f"{namespace}.{name}"):
                    self.assertIs(getattr(module, name), getattr(defined[name], name))
                    self.assertNotIn(name, cad.__all__, f"{name} is {namespace}'s, not the root's")

    def test_model_declares_a_function_or_hands_a_shape_over_and_a_decorator_takes_its_path(self):
        """``model`` is one name of two forms: a decorator (``@model``, ``@model(name=)``) and the
        shape form (``model(shape, name=, animations=)``); a file decorator takes its path and its
        name, and an STL's or a 3MF's its mesh tolerance. No ``id=``: an id is derived; no
        ``store=``: every document is kept alike."""
        import inspect

        parameters = inspect.signature(cad.engine.model.model).parameters
        self.assertEqual([(name, p.kind) for name, p in parameters.items()], [
            ("target", inspect.Parameter.POSITIONAL_ONLY), ("name", inspect.Parameter.KEYWORD_ONLY),
            ("animations", inspect.Parameter.KEYWORD_ONLY)])
        for kind in ("xbf", "step", "glb", "stl", "threemf", "dxf", "kicad_pcb"):
            with self.subTest(kind=kind):
                if kind != "kicad_pcb":  # a board script's decorator is the kicad integration's, not the engine's
                    self.assertEqual(list(inspect.signature(getattr(cad.engine, kind)).parameters),
                                     ["out", "name", *(["tolerance"] if kind in ("stl", "threemf") else [])])
                # The type's decorator passes an STL's or a 3MF's mesh tolerance to the engine's; any other
                # type's engine decorator refuses it, as Python refuses an unknown keyword.
                self.assertEqual(list(inspect.signature(getattr(cad, kind).__call__).parameters), ["out", "name", "tolerance"])

    def test_a_types_decorator_takes_its_path_by_position_or_by_out_as_0_10s_did(self):
        """``@step(out="...")`` is the engine README's own spelling: the type's decorator takes ``out`` either
        way and ``name=`` by keyword, exactly the 0.10 decorator's signature, and a path is required."""
        from cad import step, xbf

        def arm():
            return None

        def plate():
            return None

        built = xbf(out="XBF/arm.xbf")(step(out="arm.step", name="arm_named")(arm))
        self.assertEqual(sorted(output.kind for output in built.outputs), ["step", "xbf"])
        self.assertEqual("plate", step("plate.step")(plate).name)
        for call in (lambda: step(), lambda: step("a.step", "b"), lambda: step(path="a.step")):
            with self.subTest(call=call), self.assertRaises(TypeError):
                call()

    def test_a_board_script_takes_no_decorator_but_its_own(self):
        """A @kicad_pcb board script is never made a model: a decorator no producer of its type declares for
        it is refused at decoration, naming the ones that take it."""
        from cad import glb, kicad_pcb, step, stl, xbf

        script = kicad_pcb("board.kicad_pcb")(lambda board: None)
        for decorator in (xbf, glb, stl):
            with self.subTest(decorator=decorator), self.assertRaises(TypeError) as caught:
                decorator(f"board{decorator.entry.suffix}")(script)
            self.assertIn("one takes @step", str(caught.exception))
        self.assertIs(script, step("board.step")(script))

    def test_a_name_the_root_never_had_is_pythons_own_error(self):
        # No backwards compatibility: a retired name is no name, and says nothing about history.
        # ``build`` among them: a model builds by a decorated function's call, never cad.build (law 12).
        for name in ("Material", "materials", "build", "read_scene", "AssemblyHelper", "label_shape", "revolute", "compound_from_instances",
                     "mechanism_state", "animation", "select", "report", "track", "serve", "status", "stop",
                     "daemon", "server", "srgb", "srgb_to_linear", "linear_to_srgb", "validate", "check"):
            with self.subTest(name=name), self.assertRaises(AttributeError) as caught:
                getattr(cad, name)
            self.assertEqual(str(caught.exception), f"module 'cad' has no attribute {name!r}")

    def test_importing_cadgen_does_not_import_the_cad_stack(self):
        """Run in a subprocess: this one almost certainly has OCP loaded already."""
        code = (
            "import sys, cadgen, cad.build123d, cad.step, cad.urdf, cad.registry;"
            f"print('HEAVY:' + ','.join(m for m in {HEAVY!r} if m in sys.modules))"
        )
        proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        marked = [ln for ln in proc.stdout.splitlines() if ln.startswith("HEAVY:")]
        self.assertEqual(["HEAVY:"], marked, "importing cadgen pulled in the CAD stack")

    def test_model_body_helpers_do_not_import_the_cad_stack(self):
        """`from cad.build123d import flat_pattern` sits in a model's MODULE BODY, so the module behind it
        must defer the kernel -- its `import build123d` bound lazily (`_internal/lazy_kernel.py`)
        -- or every such model pays the ~2.5s import in the process that only asks the daemon to
        build it."""
        code = (
            "import sys, cad.build123d._flatten;"
            "from cad.build123d import flat_pattern;"
            "from cad._internal.lazy_kernel import loaded;"
            f"print('HEAVY:' + ','.join(m for m in {HEAVY!r} if loaded(m)))"
        )
        proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        marked = [ln for ln in proc.stdout.splitlines() if ln.startswith("HEAVY:")]
        self.assertEqual(["HEAVY:"], marked, "cad.build123d._flatten imported the kernel at module scope")


if __name__ == "__main__":
    unittest.main()
