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
ENGINE = ("model", "step", "glb", "stl", "threemf", "dxf", "memo", "paint",
          "read_step", "read_xbf", "read_mesh")
# The root: the version, the deprecation's class, and the document types as the library spells them (``model``:
# a model the engine holds, or the ``.xbf`` it is saved as).
TYPES = ("model", "step", "stl", "glb", "threemf", "dxf", "urdf", "srdf", "kicad_pcb", "kicad_sch")
ROOT = ("__version__", "CadDeprecationWarning", *TYPES)
# The build123d integration's names: our helpers that take build123d's objects.
NAMESPACES = {
    "cad.build123d": ("mechanism_state", "configuration_sequence", "gear_pair", "rack_and_pinion_pair", "screw_pair",
                      "posed", "animation", "memo", "paint", "GeometryError", "GeometryIssue", "ClosestPoints",
                      "MassProperties", "closest_points", "overlap_volume", "is_sound", "topology_errors",
                      "boundary_edges", "self_intersections", "mass_properties", "dfm", "cnc",
                      "sheet_metal", "molding", "printing", "unfold", "frame", "leaves", "body", "limits", "mass",
                      "point_mass", "free", "link", "materials"),
}
# The namespaces' public submodules, offered with their names and imported on first use.
SUBMODULES = {"cad.build123d": ("materials",)}


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
        # ``model`` is a type with no file: its decorator is the engine's model, its operations a model's.
        self.assertEqual(cad.model.__call__.__doc__.split(":")[0],
                         '``@model``, ``@model(name=...)`` or ``@model(out="XBF/arm.xbf")``')
        for name in ("Material", "materials"):
            self.assertFalse(hasattr(cad.engine, name), f"materials come from bd_materials: {name}")
        for name in TYPES:
            with self.subTest(name=name):
                self.assertIsInstance(getattr(cad, name), DocumentType)
        self.assertIs(cad.step.read, cad.engine.model.read_step)
        self.assertIs(cad.model.read, cad.engine.read_xbf)
        self.assertIs(cad.stl.read, cad.engine.read_mesh)
        self.assertIs(cad.urdf.validate, cad.urdf.__dict__["validate"])
        self.assertIs(cad.kicad_pcb.read, cad.kicad_pcb.__dict__["read"])
        # An operation's docstring ends with its verb's, without the indentation Python strips by itself only from 3.13.
        import inspect

        self.assertTrue(cad.model.export.__doc__.endswith(inspect.cleandoc(api.export.__doc__)))

    def test_a_types_operations_take_its_own_sources_alone(self):
        """A source of another type is refused by name before anything runs (law 23): a file of another type, a
        model's id given to a file's type, and any file given to ``cad.model`` but the one a model is saved as."""
        ident = "0b4c5f1e-1a2b-4c3d-8e9f-0123456789ab"
        for call, said in (
                (lambda: cad.model.export("arm.step", "arm.glb"), "arm.step is a step, not a model: use cad.step"),
                (lambda: cad.model.inspect("arm"), "cad.model takes a model's handle, its document id (cad run "
                                                   "SCRIPT.py prints it) or an .xbf file, not 'arm'"),
                (lambda: cad.step.export("share/arm.xbf", "arm.glb"), "share/arm.xbf is a xbf, not a step: use cad.model"),
                (lambda: cad.step.export(ident, "arm.glb"), f"{ident} is a model's document id, not a .step file: use "
                                                            "cad.model"),
                (lambda: cad.stl.export("part.glb", "part.3mf"), "part.glb is a glb, not a stl: use cad.glb")):
            with self.subTest(said=said):
                with self.assertRaises(ValueError) as refused:
                    call()
                self.assertEqual(str(refused.exception), said)

    def test_cad_model_is_a_model_held_or_saved_and_its_operations_run_on_the_file_as_the_file_s(self):
        """``cad.model``'s operations take the ``.xbf`` a model is saved as, as ``cad model`` does: the source
        says which of the two it is (``refuse_other``), and the operation is then that file's type's -- the
        engine's verb given the path, a check asked of the engine as an xbf's."""
        from unittest import mock

        from cad._internal.document_type import refuse_other
        from cad.engine import api

        ident = "0b4c5f1e-1a2b-4c3d-8e9f-0123456789ab"
        self.assertEqual([refuse_other("model", source) for source in (ident, "share/arm.xbf", "ARM.XBF", None)],
                         ["model", "xbf", "xbf", "model"])
        for name, rest in (("export", ("arm.glb",)), ("inspect", ()), ("snapshot", ("arm.png",))):
            with self.subTest(operation=name), mock.patch.object(api, name, return_value="done") as verb:
                # ``_operation`` binds the verb when the attribute is first read: a fresh one here.
                from cad._internal.document_type import _operation

                self.assertEqual(_operation("model", name)("share/arm.xbf", *rest), "done")
                verb.assert_called_once_with("share/arm.xbf", *rest)
        with mock.patch.object(api, "check", return_value={"unmeasured": {"message": "gone", "code": "stopped"}}) as check:
            cad.model.interference("share/arm.xbf")
            cad.model.interference(ident)
        self.assertEqual([call.args[1]["type"] for call in check.call_args_list], ["xbf", "model"])

    def test_model_read_reads_the_file_a_model_is_saved_as_and_refuses_any_other_by_name(self):
        """``model.read`` is the engine's one reader of an ``.xbf`` (``cad.engine.read_xbf``), the kernel's
        memo and all; a file of another kind is refused with the reader that takes it."""
        self.assertIs(cad.model.read, cad.engine.read_xbf)
        self.assertIn("read", dir(cad.model))
        for path, said in (("vendor/motor.step", "model.read reads an .xbf, not motor.step: read a STEP with step.read"),
                           ("scan.STL", "model.read reads an .xbf, not scan.STL: read an STL with stl.read"),
                           ("notes.txt", "model.read reads an .xbf, not notes.txt")):
            with self.subTest(path=path):
                with self.assertRaises(ValueError) as refused:
                    cad.model.read(path)
                self.assertEqual(str(refused.exception), said)
        with self.assertRaises(ValueError) as refused:
            cad.stl.read("vendor/motor.xbf")
        self.assertEqual(str(refused.exception), "stl.read reads an .stl, not motor.xbf: read a model saved as a file "
                                                 "with model.read")

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

        from cad.build123d import _dfm_check, _dfm_sheet, _geometry, _leaves
        from cad.engine import declarations, mechanism, model
        from cad.engine.formats.kicad import board_index, geometry, summary

        defined = {"mechanism_state": model, "configuration_sequence": model, "animation": model, "memo": model,
                   "paint": model, "gear_pair": mechanism, "rack_and_pinion_pair": mechanism,
                   "screw_pair": mechanism, "posed": mechanism, "frame": declarations, "leaves": _leaves,
                   "body": declarations, "limits": declarations, "mass": declarations, "point_mass": declarations,
                   "free": declarations, "link": declarations,
                   **{name: _geometry for name in _geometry.__all__},
                   **{name: _dfm_check for name in ("dfm", "cnc", "sheet_metal", "molding", "printing")},
                   "unfold": _dfm_sheet}
        for namespace, names in NAMESPACES.items():
            module = importlib.import_module(namespace)
            self.assertEqual(sorted(names), sorted(module.__all__))
            for name in names:
                with self.subTest(name=f"{namespace}.{name}"):
                    if name in SUBMODULES.get(namespace, ()):
                        self.assertIs(getattr(module, name), importlib.import_module(f"{namespace}.{name}"))
                    else:
                        self.assertIs(getattr(module, name), getattr(defined[name], name))
                    self.assertNotIn(name, cad.__all__, f"{name} is {namespace}'s, not the root's")

    def test_the_blender_namespace_loads_no_bpy_and_a_script_without_it_is_told_the_extra(self):
        """``cad.blender`` is its declared names, loaded on first use: importing it imports no bpy. Where bpy is
        absent -- any Python but the one Blender is built for, an environment made without the extra -- a name of
        it says which extra brings it, in the one line every integration's missing module is said in."""
        import importlib.util

        code = ("import sys, cad.blender\n"
                "print(cad.blender.__all__, 'bpy' in sys.modules, [n for n in dir(cad.blender) if n[0] != '_'])\n")
        proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
        self.assertEqual(proc.stdout.strip(), "['Clip', 'Model', 'load'] False ['Clip', 'Model', 'load']", proc.stderr)
        import cad.blender

        with self.assertRaises(AttributeError):
            cad.blender.cube
        self.assertNotIn("blender", cad.__all__, "an integration's namespace, not a name of the root")
        if importlib.util.find_spec("bpy") is None:
            with self.assertRaises(ModuleNotFoundError) as caught:
                from cad.blender import load  # noqa: F401
            self.assertEqual((str(caught.exception), caught.exception.name),
                             ("bpy comes with cad's blender integration: add `cad[blender]` to the script's header", "bpy"))

    def test_model_declares_a_function_or_hands_a_shape_over_and_a_decorator_takes_its_path(self):
        """``model`` is one name of two forms: a decorator (``@model``, ``@model(name=)``, ``@model(out=)``:
        the ``.xbf`` each run saves it as) and the shape form (``model(shape, name=, animations=)``, which
        declares no file); a file decorator takes its path and its
        name, and an STL's or a 3MF's its mesh tolerance. No ``id=``: an id is derived; no
        ``store=``: every document is kept alike."""
        import inspect

        for declare in (cad.engine.model.model, cad.model.__call__):
            parameters = inspect.signature(declare).parameters
            self.assertEqual([(name, p.kind) for name, p in parameters.items()], [
                ("target", inspect.Parameter.POSITIONAL_ONLY), ("name", inspect.Parameter.KEYWORD_ONLY),
                ("out", inspect.Parameter.KEYWORD_ONLY), ("animations", inspect.Parameter.KEYWORD_ONLY)])
            with self.assertRaisesRegex(TypeError, r"model\(shape, name=\.\.\.\) takes no out=: .* export the document "
                                                   r"it returns"):
                declare(object(), name="arm", out="arm.xbf")
        for kind in ("step", "glb", "stl", "threemf", "dxf"):
            with self.subTest(kind=kind):
                self.assertEqual(list(inspect.signature(getattr(cad.engine, kind)).parameters),
                                 ["out", "name", *(["tolerance", "angle"] if kind in ("glb", "stl", "threemf") else [])])
                # The type's decorator passes a GLB's, an STL's or a 3MF's mesh tolerance and angle to the engine's;
                # any other type's engine decorator refuses them, as Python refuses an unknown keyword.
                self.assertEqual(list(inspect.signature(getattr(cad, kind).__call__).parameters),
                                 ["out", "name", "tolerance", "angle"])

    def test_a_types_decorator_takes_its_path_by_position_or_by_out_as_0_10s_did(self):
        """``@step(out="...")`` is the engine README's own spelling: the type's decorator takes ``out`` either
        way and ``name=`` by keyword, exactly the 0.10 decorator's signature, and a path is required."""
        from cad import step, model

        def arm():
            return None

        def plate():
            return None

        built = model(out="XBF/arm.xbf")(step(out="arm.step", name="arm_named")(arm))
        self.assertEqual(sorted(output.kind for output in built.outputs), ["step", "xbf"])
        self.assertEqual("plate", step("plate.step")(plate).name)
        for call in (lambda: step(), lambda: step("a.step", "b"), lambda: step(path="a.step")):
            with self.subTest(call=call), self.assertRaises(TypeError):
                call()

    def test_a_name_the_root_never_had_is_pythons_own_error(self):
        # No backwards compatibility: a retired name is no name, and says nothing about history.
        # ``build`` among them: a model builds by a decorated function's call, never cad.build (law 11).
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
        """`from cad.build123d import closest_points` sits in a model's MODULE BODY, so the module behind it
        must defer the kernel -- its `import build123d` bound lazily (`_internal/lazy_kernel.py`)
        -- or every such model pays the ~2.5s import in the process that only asks the daemon to
        build it. `_flatten`, which earlier spellings still import from, defers it the same way."""
        code = (
            "import sys, cad.build123d._geometry, cad.build123d._flatten;"
            "from cad.build123d import closest_points;"
            "from cad._internal.lazy_kernel import loaded;"
            f"print('HEAVY:' + ','.join(m for m in {HEAVY!r} if loaded(m)))"
        )
        proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        marked = [ln for ln in proc.stdout.splitlines() if ln.startswith("HEAVY:")]
        self.assertEqual(["HEAVY:"], marked, "a helper's module imported the kernel at module scope")


if __name__ == "__main__":
    unittest.main()
