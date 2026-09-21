"""Source ownership is by file; result dependencies name exact model calls."""

from __future__ import annotations

import os
import textwrap
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support.tmp_root import generated_cad_directory


FAMILY = """
from cadgen import step
from cadgen import build123d as bd

WIDTH = 4

def helper():
    return WIDTH

@step
def left():
    return bd.Box(1, 1, 1)

@step
def right():
    return bd.Box(2, 2, 2)
"""


class ModelClosureBoundaries(unittest.TestCase):
    def setUp(self):
        from cadgen.store.closure import forget_model_files

        scratch = generated_cad_directory(prefix="closure-model-boundaries-")
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name)
        env = mock.patch.dict(os.environ, {"CADGEN_CACHE_DIR": str(self.root / "store")})
        env.start()
        self.addCleanup(env.stop)
        forget_model_files()
        self.addCleanup(forget_model_files)
        self.family = self.write("family.py", FAMILY)

    def geometry_tree(self, label):
        from build123d import Solid
        from cadgen.store.build import build_tree_from_compound
        return build_tree_from_compound(Solid.make_box(1, 1, 1), root_name=label)[0]

    def write(self, name, source):
        path = self.root / name
        path.write_text(textwrap.dedent(source).strip() + "\n", encoding="utf-8")
        return path

    def parent(self, imports="", body="return left()"):
        return self.write(
            "parent.py",
            "from cadgen import step\n" + imports + "\n\n@step\ndef parent():\n"
            + textwrap.indent(body, "    "),
        )

    def executed(self, *paths):
        from cadgen._internal.source_hash import _semantic_source_hash

        return {str(path.resolve()): _semantic_source_hash(path) for path in paths}

    def record(self, script, function, *, tree, children=()):
        from cadgen.store.closure import build_closure
        from cadgen.store.index import model_ref
        from cadgen.store.records import write_record

        closure = build_closure(script, executed={}, children=[child for child, _pin in children])
        reference = model_ref(script, function)
        write_record(reference, {
            "entryKind": "part", "sourceKind": "python", "tree": tree,
            "closure": closure.as_json(), "constants": closure.constants,
            "children": [{"model": child, "tree": pin} for child, pin in children],
            "outputs": {},
        })
        return reference

    def test_imported_model_names_from_a_multi_model_file_are_result_edges(self):
        from cadgen.store.closure import is_model_file, static_closure

        cases = (
            ("from family import left", "return left()"),
            ("from family import left, right", "return left()"),
            ("from family import left as selected", "return selected()"),
            ("import family as parts", "return parts.left()"),
        )
        # Result-only classification is AST work and must not import the model
        # merely to choose one of its declarations.
        with mock.patch("cadgen.metadata.imported_model", side_effect=AssertionError("model imported")):
            self.assertTrue(is_model_file(self.family))
            for imports, body in cases:
                with self.subTest(imports=imports):
                    closure = static_closure(self.parent(imports, body))
                    self.assertEqual(closure.child_models, (self.family,))
                    self.assertEqual(closure.source_files, ())
                    self.assertEqual(closure.constants, {})

    def test_a_later_helper_import_promotes_the_whole_file_to_source(self):
        from cadgen.store.closure import static_closure

        for imports in (
            "from family import left\nfrom family import helper",
            "from family import helper\nfrom family import left",
            "from family import left, helper",
            "from family import left\nfrom family import *",
        ):
            with self.subTest(imports=imports):
                closure = static_closure(self.parent(imports))
                self.assertEqual(closure.source_files, (self.family,))
                self.assertEqual(closure.child_models, ())
                self.assertEqual(closure.constants, {})

    def test_an_unrelated_plain_helper_remains_a_source_dependency(self):
        from cadgen.store.closure import build_closure, static_closure

        helper = self.write("utility.py", "def helper():\n    return 1\n")
        parent = self.parent("from family import left\nfrom utility import helper")
        statics = static_closure(parent)
        self.assertEqual(statics.child_models, (self.family,))
        self.assertEqual(statics.source_files, (helper,))
        closure = build_closure(parent, executed=self.executed(parent, self.family, helper),
                                children=[str(self.family) + "::left"])
        self.assertEqual(closure.files, ("parent.py", "utility.py"))

    def test_multi_model_constants_keep_value_dependencies(self):
        from cadgen.store.closure import build_closure, changed_constant

        parent = self.parent("from family import left, WIDTH")
        closure = build_closure(parent, executed={})
        self.assertEqual(closure.files, ("parent.py",))
        self.assertEqual(set(closure.constants), {"family.py"})
        self.assertEqual(set(closure.constants["family.py"]), {"WIDTH"})
        self.family.write_text(FAMILY.replace("WIDTH = 4", "WIDTH = 5"), encoding="utf-8")
        self.assertEqual(changed_constant(parent, closure.constants), "family.py:WIDTH")

    def test_named_runtime_child_refs_retain_unproven_dynamic_source(self):
        from cadgen.store.closure import build_closure, static_closure

        helper = self.write("utility.py", "def helper():\n    return 1\n")
        self.family.write_text("from utility import helper\n" + FAMILY, encoding="utf-8")
        parent = self.parent(body="import importlib\nreturn importlib.import_module('family').left()")
        self.assertEqual(static_closure(parent).child_models, ())
        closure = build_closure(parent, executed=self.executed(parent, self.family, helper),
                                children=[str(self.family) + "::left"])
        self.assertEqual(closure.files, ("family.py", "parent.py", "utility.py"))
        # A helper reached directly by the parent belongs to both closures.
        parent = self.parent("from utility import helper", body="import importlib\nreturn importlib.import_module('family').left()")
        closure = build_closure(parent, executed=self.executed(parent, self.family, helper),
                                children=[str(self.family) + "::left"])
        self.assertEqual(closure.files, ("family.py", "parent.py", "utility.py"))

    def test_dynamic_helper_edit_is_stale_even_after_the_child_rebuilds_identically(self):
        from cadgen.store.gate import stale
        from cadgen.store.records import read_record

        child_tree = self.geometry_tree("child")
        left = self.record(self.family, "left", tree=child_tree)
        parent_script = self.parent(
            "from cadgen import build123d as bd",
            body="import importlib\nparts = importlib.import_module('family')\n"
                 "return bd.Compound(children=[parts.left(), bd.Box(parts.helper(), 1, 1)])",
        )
        parent = self.record(parent_script, "parent", tree=child_tree, children=[(left, child_tree)])
        self.assertIn("family.py", read_record(parent)["closure"]["files"])
        self.assertFalse(stale(parent).stale)
        self.family.write_text(FAMILY.replace("WIDTH = 4", "WIDTH = 5"), encoding="utf-8")
        # left() does not read WIDTH, so its newly current result is identical.
        self.record(self.family, "left", tree=child_tree)
        self.assertFalse(stale(left).stale)
        verdict = stale(parent)
        self.assertTrue(verdict.stale, "an identical child pin must not hide the parent's direct helper input")
        self.assertTrue(any(clause["clause"] == 2 and clause["stale"] for clause in verdict.clauses))

    def assert_alias_helper_edit_is_stale(self, family, imports, alias, helper_expression):
        from cadgen.store.gate import stale
        from cadgen.store.records import read_record

        family.write_text(FAMILY, encoding="utf-8")
        child_tree = self.geometry_tree("child")
        left = self.record(family, "left", tree=child_tree)
        parent_script = self.parent(
            imports,
            body=f"result = {alias}.left()\nresult.label = str({helper_expression})\nreturn result",
        )
        parent = self.record(parent_script, "parent", tree=child_tree, children=[(left, child_tree)])
        self.assertEqual(read_record(parent)["children"], [{"model": left, "tree": child_tree}])
        self.assertFalse(stale(parent).stale)
        family.write_text(FAMILY.replace("WIDTH = 4", "WIDTH = 5"), encoding="utf-8")
        # Only the helper changes. Rebuilding left makes its exact result pin
        # current again, so the parent's source edge must detect the change.
        self.record(family, "left", tree=child_tree)
        self.assertFalse(stale(left).stale)
        verdict = stale(parent)
        self.assertTrue(verdict.stale, "an escaped module must not hide a helper edit behind an unchanged child")
        self.assertTrue(any(clause["clause"] == 2 and clause["stale"] for clause in verdict.clauses))
        self.assertIn(family.relative_to(self.root).as_posix(), read_record(parent)["closure"]["files"])

    def test_module_alias_escapes_cannot_hide_helper_edits_after_identical_child_rebuilds(self):
        cases = (
            ("import family", "family", "getattr(family, 'helper')()"),
            ("import family as parts", "parts", "(lambda module: module.helper())(parts)"),
            ("import family as parts", "parts", "vars(parts)['helper']()"),
        )
        for imports, alias, expression in cases:
            with self.subTest(imports=imports, expression=expression):
                self.assert_alias_helper_edit_is_stale(self.family, imports, alias, expression)

    def test_static_module_model_call_keeps_an_exact_result_only_dependency(self):
        from cadgen.store.gate import stale
        from cadgen.store.records import read_record

        child_tree = self.geometry_tree("child")
        left = self.record(self.family, "left", tree=child_tree)
        script = self.parent("import family as parts", body="return parts.left()")
        parent = self.record(script, "parent", tree=child_tree, children=[(left, child_tree)])
        self.assertEqual(read_record(parent)["closure"]["files"], ["parent.py"])
        self.assertEqual(read_record(parent)["children"], [{"model": left, "tree": child_tree}])
        self.family.write_text(FAMILY.replace("WIDTH = 4", "WIDTH = 5"), encoding="utf-8")
        self.assertTrue(stale(parent).stale, "the called child's whole-file source is stale until rebuilt")
        self.record(self.family, "left", tree=child_tree)
        self.assertFalse(stale(parent).stale, "a static model call depends on its result, not an unused helper")

    def test_aliased_package_submodule_uses_the_bound_name_for_result_and_source_edges(self):
        from cadgen.store.closure import static_closure

        (self.root / "parts").mkdir()
        self.write("parts/__init__.py", "")
        family = self.write("parts/family.py", FAMILY)
        imports = "from parts import family as models"
        with mock.patch("cadgen.metadata.imported_model", side_effect=AssertionError("model imported")):
            control = static_closure(self.parent(imports, body="return models.left()"))
        self.assertEqual(control.child_models, (family,))
        self.assertEqual(control.source_files, ())
        for expression in (
            "models.helper()",
            "getattr(models, 'helper')()",
            "(lambda module: module.helper())(models)",
        ):
            with self.subTest(expression=expression):
                self.assert_alias_helper_edit_is_stale(family, imports, "models", expression)

    def test_writing_or_deleting_a_module_attribute_is_source_owned(self):
        from cadgen.store.closure import static_closure

        for statement in ("family.left = family.right", "del family.left"):
            with self.subTest(statement=statement):
                closure = static_closure(self.parent("import family", body=statement + "\nreturn family.right()"))
                self.assertEqual(closure.source_files, (self.family,))
                self.assertEqual(closure.child_models, ())

    def test_nested_model_imports_do_not_hide_nested_helper_dependencies(self):
        from cadgen.store.closure import build_closure, static_closure

        parent = self.parent(body="from family import left\nreturn left()")
        self.assertEqual(static_closure(parent).child_models, (self.family,))
        parent = self.parent("from family import left", body="from family import helper\nreturn left()")
        closure = build_closure(parent, executed=self.executed(parent, self.family),
                                children=[str(self.family) + "::left"])
        self.assertEqual(closure.files, ("family.py", "parent.py"))

    def test_a_grandchilds_files_belong_to_the_child_that_calls_it(self):
        """Ownership is transitive, and the whole subtree executes in this process.

        A body importing its child imports the child's child and that child's
        helpers too, and every one of them is in ``executed``. Subtracting only
        one level of child ownership put the grandchild's script and helper in
        the ROOT's closure, so a geometry-neutral edit two levels down rebuilt
        the root — while the same edit one level down correctly left it current,
        because a pinned tree that does not move is what "models by result"
        means.
        """
        from cadgen.store.closure import build_closure

        self.write("helper_lib.py", "SPAN = 3\n\ndef span():\n    return SPAN\n")
        leaf = self.write("leaf.py", """
            from cadgen import step
            from cadgen import build123d as bd
            from helper_lib import span

            @step
            def leaf():
                return bd.Box(span(), 1, 1)
        """)
        middle = self.write("middle.py", """
            from cadgen import step
            from leaf import leaf

            @step
            def middle():
                return leaf()
        """)
        root = self.write("root.py", """
            from cadgen import step
            from middle import middle

            @step
            def root():
                return middle()
        """)
        executed = self.executed(root, middle, leaf, self.root / "helper_lib.py")

        closure = build_closure(root, executed=executed, children=[str(middle) + "::middle"])

        self.assertEqual(closure.files, ("root.py",))

    def test_exact_function_pins_and_whole_file_sibling_invalidation_remain(self):
        from cadgen.store.closure import build_closure
        from cadgen.store.gate import stale
        from cadgen.store.index import model_ref
        from cadgen.store.records import read_record

        own = build_closure(self.family, executed=self.executed(self.family),
                            children=[str(self.family) + "::left"])
        self.assertEqual(own.files, ("family.py",), "a same-file child cannot remove the caller's own source")
        # Empty artifact graphs suffice for a gate/closure test; no CAD body or
        # kernel operation runs. Tree identity distinguishes the two results.
        left_tree = self.geometry_tree("left")
        right_tree = self.geometry_tree("right")
        left = self.record(self.family, "left", tree=left_tree)
        right = self.record(self.family, "right", tree=right_tree)
        parent_script = self.parent("from family import left")
        parent = self.record(parent_script, "parent", tree=left_tree, children=[(left, left_tree)])
        self.assertEqual(read_record(parent)["children"], [{"model": model_ref(self.family, "left"), "tree": left_tree}])
        self.assertFalse(stale(parent).stale)
        # The uncalled sibling's result does not enter the parent's pins.
        self.record(self.family, "right", tree=left_tree)
        self.assertFalse(stale(parent).stale)
        self.family.write_text(FAMILY.replace("def right():\n    return bd.Box(2, 2, 2)", "def right():\n    return bd.Box(3, 3, 3)"), encoding="utf-8")
        self.assertTrue(stale(left).stale, "sibling source edits still invalidate the whole file")
        self.assertTrue(stale(right).stale)
        self.assertTrue(stale(parent).stale, "the exact called child's stale source must still reach its parent")


if __name__ == "__main__":
    unittest.main()
