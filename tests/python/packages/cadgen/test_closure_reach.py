"""Functions by reach (STORE.md §3): a helper module is hashed by the part of
it a model can execute, whole wherever the analysis cannot see."""

from __future__ import annotations

import os
import textwrap
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support.tmp_root import generated_cad_directory


GEO = """
import math
from lib import spec

SCALE = 2.0
UNUSED_TABLE = [1, 2, 3]


def _unit(v):
    n = math.sqrt(sum(c * c for c in v))
    return tuple(c / n for c in v)


def plane(origin, z_dir):
    return (origin, _unit(z_dir), SCALE * spec.BORE)


def unrelated(x):
    return x + 1


def also_unrelated():
    return unrelated(2)
"""

SPEC = """
BORE = 140.0
STROKE = 160.0
"""

MODEL = """
from cadgen import step
from cadgen import build123d as bd
from lib import geo


@step
def part():
    origin, z, size = geo.plane((0, 0, 0), (0, 0, 1))
    return bd.Box(size, 1, 1)
"""


# Each edit changes import-time state despite assigning an otherwise unused name.
# These exercise the real closure/gate, without a CAD kernel or sample corpus.
IMPORT_EFFECTS = {
    'class method default': (
        'class Setup:\n'
        '    def method(self, value=DIMS.append(3)): pass',
        'append(3)', 'append(5)',
    ),
    'class body store': (
        'class Setup:\n'
        '    DIMS[0] = 3',
        '= 3', '= 5',
    ),
    'imported mutator': (
        'from operator import setitem\n'
        'unused = setitem(DIMS, 0, 3)',
        '0, 3', '0, 5',
    ),
    'walrus binding': (
        'unused = (DIMS := [3])',
        '[3]', '[5]',
    ),
    'augmented alias': (
        'alias = DIMS\n'
        'alias += [3]',
        '[3]', '[5]',
    ),
    'decorator argument': (
        'from functools import lru_cache\n'
        '@lru_cache(maxsize=DIMS.append(3))\n'
        'def unused(): return 0',
        'append(3)', 'append(5)',
    ),
    'variable annotation': (
        'unused: DIMS.append(3) = 0',
        'append(3)', 'append(5)',
    ),
    'property access': (
        'class Setup:\n'
        '    @property\n'
        '    def apply(self):\n'
        '        DIMS.append(3)\n'
        '        return 0\n'
        'setup = Setup()\n'
        'unused = setup.apply',
        'unused = setup.apply', 'unused = 0',
    ),
    'subscription': (
        'class Setup:\n'
        '    def __getitem__(self, key):\n'
        '        DIMS.append(3)\n'
        '        return 0\n'
        'setup = Setup()\n'
        'unused = setup[0]',
        'unused = setup[0]', 'unused = 0',
    ),
    'operator dispatch': (
        'class Setup:\n'
        '    def __add__(self, value):\n'
        '        DIMS.append(3)\n'
        '        return 0\n'
        'setup = Setup()\n'
        'unused = setup + 1',
        'unused = setup + 1', 'unused = 0',
    ),
    'truth test': (
        'class Setup:\n'
        '    def __bool__(self):\n'
        '        DIMS.append(3)\n'
        '        return True\n'
        'setup = Setup()\n'
        'unused = setup and 1',
        'unused = setup and 1', 'unused = 0',
    ),
    'format dispatch': (
        'class Setup:\n'
        '    def __format__(self, spec):\n'
        '        DIMS.append(3)\n'
        "        return ''\n"
        'setup = Setup()\n'
        "unused = f'{setup}'",
        "unused = f'{setup}'", "unused = ''",
    ),
    'builtin protocol': (
        'class Setup:\n'
        '    def __int__(self):\n'
        '        DIMS.append(3)\n'
        '        return 0\n'
        'setup = Setup()\n'
        'unused = int(setup)',
        'unused = int(setup)', 'unused = 0',
    ),
    'destructuring': (
        'class Setup:\n'
        '    def __iter__(self):\n'
        '        DIMS.append(3)\n'
        '        yield 0\n'
        'setup = Setup()\n'
        'unused, = setup',
        'unused, = setup', 'unused = 0',
    ),
    'container key protocol': (
        'class Setup:\n'
        '    def __hash__(self):\n'
        '        DIMS.append(3)\n'
        '        return 0\n'
        'setup = Setup()\n'
        'unused = {setup: 0}',
        'unused = {setup: 0}', 'unused = {}',
    ),
    'literal rebinding finalizer': (
        'class Setup:\n'
        '    def __del__(self): DIMS.append(3)\n'
        'unused = Setup()\n'
        'unused = 0',
        'unused = 0', 'kept = 0',
    ),
    'function rebinding finalizer': (
        'class Setup:\n'
        '    def __del__(self): DIMS.append(3)\n'
        'unused = Setup()\n'
        'def unused(): return 0',
        'def unused()', 'def kept()',
    ),
    'default retains object': (
        'class Setup:\n'
        '    def __del__(self): DIMS.append(3)\n'
        'setup = Setup()\n'
        'def unused(value=setup): pass\n'
        'setup = 0',
        'value=setup', 'value=None',
    ),
    'annotation retains object': (
        'class Setup:\n'
        '    def __del__(self): DIMS.append(3)\n'
        'setup = Setup()\n'
        'def unused(value: setup): pass\n'
        'setup = 0',
        'value: setup', 'value: None',
    ),
    'annotation-only': (
        'unused: DIMS.append(3)',
        'append(3)', 'append(5)',
    ),
    'comprehension walrus': (
        'unused = [(DIMS := [3]) for _ in [0]]',
        '[3]', '[5]',
    ),
}


class ReachClosure(unittest.TestCase):
    def setUp(self):
        from cadgen.store.closure import forget_model_files

        scratch = generated_cad_directory(prefix="closure-reach-")
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name)
        env = mock.patch.dict(os.environ, {"CADGEN_CACHE_DIR": str(self.root / "store")})
        env.start()
        self.addCleanup(env.stop)
        forget_model_files()
        self.addCleanup(forget_model_files)
        (self.root / "lib").mkdir()
        self.write("lib/__init__.py", "")
        self.geo = self.write("lib/geo.py", GEO)
        self.spec = self.write("lib/spec.py", SPEC)
        self.model = self.write("part.py", MODEL)

    def write(self, name, source):
        path = self.root / name
        path.write_text(textwrap.dedent(source).lstrip() + "\n", encoding="utf-8")
        return path.resolve()

    def edit(self, path, old, new):
        text = path.read_text(encoding="utf-8")
        self.assertIn(old, text)
        path.write_text(text.replace(old, new), encoding="utf-8")

    def executed(self, *paths):
        from cadgen._internal.source_hash import _semantic_source_hash

        return {str(path.resolve()): _semantic_source_hash(path) for path in paths}

    def record(self, script="part.py", function="part", *, executed=None):
        from cadgen.store.closure import build_closure
        from cadgen.store.index import model_ref
        from cadgen.store.records import write_record

        script = self.root / script
        closure = build_closure(script, executed=executed if executed is not None else {})
        reference = model_ref(script, function)
        write_record(reference, {
            "entryKind": "part", "sourceKind": "python", "tree": None,
            "closure": closure.as_json(), "constants": closure.constants,
            "children": [], "outputs": {},
        })
        return reference, closure

    def verdict(self, reference):
        from cadgen.store.gate import stale

        return stale(reference)

    def assert_clause_two(self, reference, is_stale, why=None):
        verdict = self.verdict(reference)
        clause = next(c for c in verdict.clauses if c["clause"] == 2)
        self.assertEqual(clause["stale"], is_stale, verdict.reason())
        if why is not None:
            self.assertIn(why, verdict.reason())

    # --- what the record says ---------------------------------------------------

    def test_the_record_names_what_the_model_reaches_in_each_helper(self):
        reference, closure = self.record()
        self.assertEqual(closure.files, ("lib/__init__.py", "lib/geo.py", "lib/spec.py", "part.py"))
        self.assertEqual(closure.names["lib/geo.py"], ("SCALE", "_unit", "plane"))
        self.assertEqual(closure.names["lib/spec.py"], ("BORE",))
        self.assertEqual(closure.names["lib/__init__.py"], ())
        self.assertNotIn("part.py", closure.names, "the script is always whole")
        self.assertTrue(closure.shas["lib/geo.py"].startswith("slice4:"))
        self.assertTrue(closure.shas["part.py"].startswith("ast1:"))
        from cadgen._internal.source_hash import _semantic_source_hash

        self.assertEqual(closure.wholes["lib/geo.py"], _semantic_source_hash(self.geo), "the bytes the slice was taken from")
        self.assertEqual(set(closure.wholes), set(closure.names))
        self.assertFalse(self.verdict(reference).stale)

    # --- the gate ----------------------------------------------------------------

    def test_editing_an_unreached_helper_leaves_the_importer_current(self):
        reference, _closure = self.record()
        self.edit(self.geo, "return x + 1", "return x + 2")
        self.edit(self.geo, "UNUSED_TABLE = [1, 2, 3]", "UNUSED_TABLE = [1, 2, 3, 4]")
        self.edit(self.spec, "STROKE = 160.0", "STROKE = 170.0")
        # A new helper beside the reached ones changes nothing the model hashes.
        self.geo.write_text(self.geo.read_text(encoding="utf-8") + "\n\ndef brand_new():\n    return 7\n", encoding="utf-8")
        self.assert_clause_two(reference, False)

    def test_editing_a_reached_helper_directly_makes_it_stale(self):
        reference, _closure = self.record()
        self.edit(self.geo, "return (origin, _unit(z_dir), SCALE * spec.BORE)", "return (origin, _unit(z_dir), SCALE * spec.BORE + 1)")
        self.assert_clause_two(reference, True, "closure changed: lib/geo.py")

    def test_editing_a_transitively_reached_helper_makes_it_stale(self):
        reference, _closure = self.record()
        self.edit(self.geo, "n = math.sqrt(sum(c * c for c in v))", "n = math.sqrt(sum(c * c for c in v)) + 1e-9")
        self.assert_clause_two(reference, True, "lib/geo.py")

    def test_editing_a_constant_a_reached_function_reads_makes_it_stale(self):
        reference, _closure = self.record()
        self.edit(self.geo, "SCALE = 2.0", "SCALE = 3.0")
        self.assert_clause_two(reference, True, "lib/geo.py")
        self.edit(self.geo, "SCALE = 3.0", "SCALE = 2.0")
        self.assert_clause_two(reference, False)
        # ...also across modules: a constant read through an alias.
        self.edit(self.spec, "BORE = 140.0", "BORE = 150.0")
        self.assert_clause_two(reference, True, "lib/spec.py")

    def test_a_reached_helper_calling_a_new_helper_is_stale_until_rebuilt(self):
        reference, first = self.record()
        self.edit(self.geo, "return (origin, _unit(z_dir), SCALE * spec.BORE)", "return (origin, _unit(z_dir), SCALE * spec.BORE + unrelated(0))")
        self.assert_clause_two(reference, True)
        reference, second = self.record()
        self.assertEqual(second.names["lib/geo.py"], ("SCALE", "_unit", "plane", "unrelated"))
        self.assertFalse(self.verdict(reference).stale)
        # The newly reached helper is now tracked; the still-unreached one is not.
        self.edit(self.geo, "return x + 1", "return x + 3")
        self.assert_clause_two(reference, True)
        reference, _third = self.record()
        self.edit(self.geo, "return unrelated(2)", "return unrelated(3)")
        self.assert_clause_two(reference, False)

    def test_a_new_module_binding_that_shadows_a_builtin_is_stale(self):
        self.edit(self.geo, "n = math.sqrt(sum(c * c for c in v))", "n = math.sqrt(sum(abs(c) * abs(c) for c in v))")
        reference, _closure = self.record()
        self.geo.write_text(self.geo.read_text(encoding="utf-8") + "\n\ndef abs(x):\n    return x\n", encoding="utf-8")
        self.assert_clause_two(reference, True)

    def test_comments_and_formatting_in_a_reached_helper_do_not_count(self):
        reference, _closure = self.record()
        self.edit(self.geo, "def plane(origin, z_dir):", "def plane(origin, z_dir):  # a comment\n")
        self.assert_clause_two(reference, False)

    def test_module_reads_survive_bindings_in_other_lexical_scopes(self):
        cases = {
            "default": "def plane(WIDTH=WIDTH):\n    return WIDTH\n",
            "keyword default": "def plane(*, WIDTH=WIDTH):\n    return WIDTH\n",
            "annotation": "def plane(WIDTH: WIDTH):\n    return WIDTH\n",
            "nested parameter": "def plane():\n    def inner(WIDTH): return WIDTH\n    return WIDTH\n",
            "comprehension": "def plane():\n    values = [WIDTH for WIDTH in range(3)]\n    return WIDTH\n",
            "comprehension iterable": "def plane():\n    return [WIDTH for WIDTH in range(WIDTH)]\n",
            "class body": "class plane:\n    WIDTH = WIDTH\n",
            "class method": "class plane:\n    WIDTH = 9\n    def size(self): return WIDTH\n",
        }
        for scope, source in cases.items():
            with self.subTest(scope=scope):
                self.write("lib/geo.py", "WIDTH = 2\n" + source)
                reference, _closure = self.record()
                self.edit(self.geo, "WIDTH = 2", "WIDTH = 3")
                self.assert_clause_two(reference, True, "lib/geo.py")

    def test_a_local_binding_is_no_module_read_but_every_load_is_an_edge(self):
        """Scopes decide what must be bound (the unresolved-name check); every
        name a statement loads is still followed, so reach never rests on
        scope analysis alone."""
        from cadgen.store.reach import analyze

        self.write("lib/geo.py", "WIDTH = 2\ndef plane(WIDTH):\n    return [WIDTH for WIDTH in range(WIDTH)]\n")
        plane = analyze(self.geo.read_bytes()).statements[1]
        self.assertNotIn("WIDTH", plane.reads)
        self.assertIn(("WIDTH", ()), plane.loads)
        reference, _closure = self.record()
        self.edit(self.geo, "WIDTH = 2", "WIDTH = 3")
        self.assert_clause_two(reference, True, "lib/geo.py")

    def test_nested_imports_with_the_same_alias_keep_both_dependencies(self):
        self.write("lib/geo.py", """
            def plane():
                def first():
                    from lib import left as dims
                    return dims.size()
                def second():
                    from lib import right as dims
                    return dims.size()
                return first() + second()
        """)
        left = self.write("lib/left.py", "def size(): return 2")
        right = self.write("lib/right.py", "def size(): return 3")
        for path, old, new in ((left, "return 2", "return 4"), (right, "return 3", "return 5")):
            with self.subTest(module=path.name):
                reference, closure = self.record()
                self.assertIn("size", closure.names[f"lib/{path.name}"])
                self.edit(path, old, new)
                self.assert_clause_two(reference, True, f"lib/{path.name}")

    def test_legacy_slice_records_rebuild_even_without_a_source_edit(self):
        from cadgen.store.closure import closure_hash
        from cadgen.store.records import read_record, write_record

        self.write("lib/geo.py", "def plane(): return 1")
        reference, _closure = self.record()
        record = read_record(reference)
        import ast
        import hashlib

        for version in ("slice1", "slice2", "slice3"):
            with self.subTest(version=version):
                digest = hashlib.sha256(version.encode())
                digest.update(b"\0plane=")
                digest.update(b"\0\0" + ast.dump(ast.parse("def plane(): return 1").body[0]).encode())
                record["closure"]["shas"]["lib/geo.py"] = version + ":" + digest.hexdigest()
                record["closure"]["hash"] = closure_hash(record["closure"]["shas"].items())
                write_record(reference, record)
                self.assert_clause_two(reference, True, "lib/geo.py")

    def test_module_level_side_effects_are_always_hashed(self):
        self.geo.write_text(self.geo.read_text(encoding="utf-8") + "\n\nREGISTRY = {}\nREGISTRY['k'] = unrelated(1)\n", encoding="utf-8")
        reference, closure = self.record()
        self.assertIn("unrelated", closure.names["lib/geo.py"], "a module-level call reaches what it names")
        self.edit(self.geo, "REGISTRY['k'] = unrelated(1)", "REGISTRY['k'] = unrelated(2)")
        self.assert_clause_two(reference, True)

    def test_a_decorated_or_calling_definition_is_preamble(self):
        self.write("lib/geo.py", GEO + "\n\ndef register(f):\n    return f\n\n\n@register\ndef plugin():\n    return 1\n\n\ndef defaulted(v=unrelated(1)):\n    return v\n")
        reference, closure = self.record()
        names = closure.names["lib/geo.py"]
        self.assertIn("register", names)
        self.assertIn("unrelated", names)
        self.edit(self.geo, "def plugin():\n    return 1", "def plugin():\n    return 2")
        self.assert_clause_two(reference, True)

    def test_import_effects_invalidate_even_when_the_bound_name_is_unused(self):
        for name, (effect, old, new) in IMPORT_EFFECTS.items():
            with self.subTest(effect=name):
                self.write("lib/geo.py", "DIMS = [2]\n" + effect + "\ndef plane(*args): return sum(DIMS)\n")
                reference, _closure = self.record()
                self.assert_clause_two(reference, False)
                self.edit(self.geo, old, new)
                self.assert_clause_two(reference, True, "lib/geo.py")

    def test_import_effects_reach_other_modules_before_any_edit(self):
        self.write("lib/geo.py", """
            from operator import setitem
            from lib import spec
            DIMS = [2]
            unused = setitem(DIMS, 0, spec.width())
            def plane(*args): return sum(DIMS)
        """)
        self.write("lib/spec.py", "def width(): return 3")
        reference, closure = self.record()
        self.assertIn("width", closure.names["lib/spec.py"])
        self.edit(self.spec, "return 3", "return 5")
        self.assert_clause_two(reference, True, "lib/spec.py")

    # --- the fallbacks -------------------------------------------------------------

    def assert_whole(self, source, *, files=("lib/geo.py",), reason=""):
        self.write("lib/geo.py", source)
        _reference, closure = self.record()
        for rel in files:
            self.assertNotIn(rel, closure.names, f"{rel} must be tracked whole: {reason}")
            self.assertTrue(closure.shas[rel].startswith("ast1:"), rel)

    def test_dynamic_modules_fall_back_to_the_whole_file(self):
        cases = {
            "star import": GEO.replace("from lib import spec", "from lib.spec import *").replace("spec.BORE", "BORE"),
            "globals()": GEO + "\n\ndef lookup(name):\n    return globals()[name]\n",
            "exec": GEO + "\n\ndef run(code):\n    exec(code)\n",
            "eval": GEO + "\n\ndef run(code):\n    return eval(code)\n",
            "importlib": GEO + "\nimport importlib\n",
            "sys.modules": GEO + "\nimport sys\n\n\ndef here():\n    return sys.modules[__name__]\n",
            "module __getattr__": GEO + "\n\ndef __getattr__(name):\n    return 1\n",
            "unresolved name": GEO + "\n\ndef broken():\n    return never_bound\n",
        }
        for reason, source in cases.items():
            with self.subTest(reason=reason):
                self.assert_whole(source, reason=reason)

    def test_a_module_alias_used_bare_makes_its_target_whole(self):
        for expression in ("getattr(spec, 'BORE')", "vars(spec)['BORE']", "(lambda m: m.BORE)(spec)"):
            with self.subTest(expression=expression):
                self.write("lib/geo.py", GEO.replace("spec.BORE", expression))
                _reference, closure = self.record()
                self.assertNotIn("lib/spec.py", closure.names, "the escaped module is whole")
                self.assertIn("lib/geo.py", closure.names, "the escaping module itself stays sliced")

    def test_writing_a_module_attribute_makes_target_and_writer_whole(self):
        self.write("lib/geo.py", GEO.replace("    return (origin, _unit(z_dir), SCALE * spec.BORE)", "    spec.BORE = 1.0\n    return (origin, _unit(z_dir), SCALE * spec.BORE)"))
        _reference, closure = self.record()
        self.assertNotIn("lib/spec.py", closure.names)
        self.assertNotIn("lib/geo.py", closure.names)

    def test_a_package_alias_used_bare_makes_the_whole_package_whole(self):
        self.write("part.py", MODEL.replace("from lib import geo", "import lib\nimport lib.geo").replace("geo.plane", "getattr(lib, 'geo').plane"))
        _reference, closure = self.record()
        self.assertNotIn("lib/geo.py", closure.names)
        self.assertNotIn("lib/spec.py", closure.names)
        self.assertNotIn("lib/__init__.py", closure.names)

    def test_a_reached_name_a_module_does_not_bind_makes_it_whole(self):
        self.write("part.py", MODEL.replace("geo.plane(", "geo.injected_plane("))
        _reference, closure = self.record()
        self.assertNotIn("lib/geo.py", closure.names)

    def test_a_namespace_read_makes_the_module_and_every_module_it_imports_whole(self):
        for expression in ("globals()[name]", "vars()[name]", "locals()[name]"):
            with self.subTest(expression=expression):
                self.write("lib/geo.py", GEO + f"\n\ndef lookup(name):\n    return {expression}\n")
                _reference, closure = self.record()
                self.assertNotIn("lib/geo.py", closure.names)
                self.assertNotIn("lib/spec.py", closure.names, "its module objects expose every name")
                self.assertIn("lib/__init__.py", closure.names, "the rest of the closure stays sliced")
        self.write("lib/geo.py", GEO + "\n\ndef measure(obj):\n    return vars(obj)\n")
        _reference, closure = self.record()
        self.assertIn("lib/geo.py", closure.names, "vars(obj) reads an object, not this module")

    def test_reflection_anywhere_hashes_the_whole_closure_whole(self):
        from cadgen.store.reach import analyze

        self.write("part.py", MODEL.replace("from lib import geo", "import importlib\nfrom lib import geo"))
        _reference, closure = self.record()
        self.assertEqual(closure.names, {}, "importlib can reach any module by string")
        self.assertEqual(closure.wholes, {})
        self.assertTrue(all(sha.startswith("ast1:") for sha in closure.shas.values()), closure.shas)
        # What counts as reflection: string execution and imports, every alias of
        # sys.modules and frames, function globals, introspection modules.
        for source in ("exec(code)", "eval(code)", "__import__(code)", "import importlib.util",
                       "from importlib import import_module", "import sys as s\ns.modules[code]",
                       "from sys import modules", "import sys\nsys._getframe().f_globals", "f.__globals__",
                       "import os\nos.sys.modules", "import inspect", "import pydoc", "import gc",
                       "import pickle", "__builtins__", "import sys\ngetattr(sys, code)"):
            with self.subTest(source=source):
                self.assertIsNotNone(analyze(source.encode()).reflective)
        for source in ("import sys\nsys.path.insert(0, code)", "def f(exec):\n    return exec(1)",
                       "def eval(x):\n    return x\ny = eval(1)", "if __name__ == '__main__':\n    import importlib"):
            with self.subTest(source=source):
                self.assertIsNone(analyze(source.encode()).reflective)

    def test_a_file_reached_only_by_execution_is_whole(self):
        loaded = self.write("lib/loaded.py", "VALUE = 1\n")
        _reference, closure = self.record(executed=self.executed(loaded))
        self.assertIn("lib/loaded.py", closure.files)
        self.assertNotIn("lib/loaded.py", closure.names)

    def test_a_sliced_file_that_turns_dynamic_reads_stale(self):
        reference, _closure = self.record()
        self.geo.write_text(self.geo.read_text(encoding="utf-8") + "\n\ndef lookup(name):\n    return globals()[name]\n", encoding="utf-8")
        self.assert_clause_two(reference, True, "lib/geo.py")

    # --- what executes, and what reaches a namespace ------------------------------

    SHAPES = "def make_a():\n    return 10.0\n\n\ndef make_b():\n    return 20.0\n"

    def write_model(self, imports, expression):
        return self.write("part.py", f"from cadgen import step\n{imports}\n\n\n@step\ndef part():\n    return {expression}\n")

    def assert_make_b_edit_is_stale(self, *, executed=(), sources=False):
        """Record (with ``executed`` as the files the build ran), edit the
        unreached-looking ``make_b``, and require the gate to see it."""
        from cadgen.store.closure import build_closure
        from cadgen.store.index import model_ref
        from cadgen.store.records import write_record

        script = self.root / "part.py"
        ran = self.executed(script, *executed)
        closure = build_closure(script, executed=ran,
                                sources={key: Path(key).read_bytes() for key in ran} if sources else None)
        reference = model_ref(script, "part")
        write_record(reference, {"entryKind": "part", "sourceKind": "python", "tree": None,
                                 "closure": closure.as_json(), "constants": closure.constants,
                                 "children": [], "outputs": {}})
        self.assert_clause_two(reference, False)
        self.edit(self.root / "lib/shapes.py", "return 20.0", "return 25.0")
        self.assert_clause_two(reference, True, "lib/shapes.py")
        return closure

    def test_a_dotted_import_executes_every_module_on_the_way(self):
        self.write("lib/shapes.py", self.SHAPES)
        self.write("lib/registry.py", "REGISTRY = []\n")
        (self.root / "lib/plugins").mkdir()
        self.write("lib/plugins/__init__.py", "")
        self.write("lib/plugins/gear.py", "from lib.registry import REGISTRY\nfrom lib.shapes import make_b\n\nREGISTRY.append(make_b)\n")
        self.write_model("import lib.plugins.gear\nfrom lib.registry import REGISTRY\nfrom lib import shapes",
                   "shapes.make_a() + REGISTRY[0]()")
        closure = self.assert_make_b_edit_is_stale()
        self.assertIn("lib/plugins/gear.py", closure.files)
        self.assertIn("make_b", closure.names["lib/shapes.py"])

    def test_a_file_the_build_executed_but_never_reached_is_walked_whole(self):
        self.write("lib/shapes.py", self.SHAPES)
        self.write("lib/registry.py", "REGISTRY = []\n")
        (self.root / "vendor").mkdir()
        plugin = self.write("vendor/vplug.py", "from lib.registry import REGISTRY\nfrom lib.shapes import make_b\n\nREGISTRY.append(make_b)\n")
        self.write_model("import sys\nsys.path.insert(0, 'vendor')\nimport vplug\nfrom lib.registry import REGISTRY\nfrom lib import shapes",
                   "shapes.make_a() + REGISTRY[0]()")
        closure = self.assert_make_b_edit_is_stale(executed=[plugin, self.root / "lib/shapes.py"], sources=True)
        self.assertIn("vendor/vplug.py", closure.files)
        self.assertNotIn("vendor/vplug.py", closure.names, "an executed root is hashed whole")

    def test_reaching_a_namespace_by_string_or_introspection_is_stale_on_any_edit(self):
        """Each bypass of name-level reach, with the lookup in the sliced module
        itself or in a helper that takes a name at run time."""
        build = "\n\ndef build(kind):\n    return {}\n"
        variants = {
            "vars() at module scope": ("", "_NS = vars()\n" + build.format("_NS['make_' + kind]()")),
            "aliased sys.modules": ("", "import sys as _sys\n" + build.format("getattr(_sys.modules[__name__], 'make_' + kind)()")),
            "from sys import modules": ("", "from sys import modules\n" + build.format("getattr(modules[__name__], 'make_' + kind)()")),
            "function globals": ("", build.format("build.__globals__['make_' + kind]()")),
            "frame globals": ("", "import sys\n" + build.format("sys._getframe().f_globals['make_' + kind]()")),
            "inspect": ("", "import inspect\n" + build.format("getattr(inspect.getmodule(build), 'make_' + kind)()")),
            "pydoc": ("", "import pydoc\n" + build.format("pydoc.locate('lib.shapes.make_' + kind)()")),
            "importlib in a loader": ("lib/loader.py", "import importlib\n\n\ndef get(module, name):\n    return getattr(importlib.import_module(module), name)\n"),
            "sys.modules in a registry": ("lib/loader.py", "import sys\n\n\ndef get(module, name):\n    return getattr(sys.modules[module], name)\n"),
            "globals() in a menu": ("lib/loader.py", "from lib import shapes\n\n\ndef get(module, name):\n    return getattr(globals()[module.rpartition('.')[2]], name)\n"),
        }
        for label, (helper, source) in variants.items():
            with self.subTest(variant=label):
                if helper:
                    self.write("lib/shapes.py", self.SHAPES)
                    self.write(helper, source)
                    self.write_model("from lib import loader, shapes", "shapes.make_a() + loader.get('lib.shapes', 'make_b')()")
                else:
                    self.write("lib/shapes.py", source + self.SHAPES)
                    self.write_model("from lib import shapes", "shapes.build('b')")
                self.assert_make_b_edit_is_stale()

    def test_an_escaped_module_exposes_every_module_bound_in_it(self):
        self.write("lib/shapes.py", "from lib import parts\n\n\ndef make_a():\n    return 10.0\n")
        self.write("lib/parts.py", self.SHAPES)
        for expression in ("getattr(getattr(shapes, 'parts'), 'make_b')()", "shapes.__dict__['parts'].make_b()"):
            with self.subTest(expression=expression):
                self.write_model("from lib import shapes", expression)
                _reference, closure = self.record()
                self.assertNotIn("lib/shapes.py", closure.names)
                self.assertNotIn("lib/parts.py", closure.names, "reachable by name through shapes")

    def test_a_class_body_comprehension_reads_the_module_name(self):
        self.write("lib/geo.py", """
            WIDTH = 2.0


            class Dims:
                WIDTH = 9.0
                sizes = [WIDTH * 5 for _ in range(2)]


            def size():
                return Dims.sizes[0]
        """)
        self.write_model("from lib import geo", "geo.size()")
        reference, closure = self.record()
        self.assertIn("WIDTH", closure.names["lib/geo.py"])
        self.edit(self.geo, "WIDTH = 2.0", "WIDTH = 3.0")
        self.assert_clause_two(reference, True, "lib/geo.py")

    def test_an_init_binding_that_shadows_a_submodule_is_reached(self):
        self.write("lib/__init__.py", "def geo():\n    return 30.0\n")
        self.write("lib/geo.py", "X = 1\n")
        self.write_model("from lib import geo", "geo()")
        reference, closure = self.record()
        self.assertIn("geo", closure.names["lib/__init__.py"])
        self.edit(self.root / "lib/__init__.py", "return 30.0", "return 35.0")
        self.assert_clause_two(reference, True, "lib/__init__.py")

    def test_a_childs_import_time_effects_on_shared_helpers_are_reached(self):
        """A child module runs in the parent's process when imported: what its
        import-time code calls in a helper the parent also reads is the parent's
        dependency, although the child's own files are not in the closure."""
        self.write("lib/shapes.py", "CONFIG = [10.0]\n\n\ndef setup():\n    CONFIG[0] = 20.0\n\n\ndef size():\n    return CONFIG[0]\n\n\ndef unused():\n    return 1\n")
        self.write("lib/boot.py", "from lib import shapes\n\nshapes.setup()\n")
        self.write("arm.py", "from cadgen import step\nimport lib.boot\n\n\n@step\ndef arm():\n    return 1\n")
        self.write_model("from arm import arm\nfrom lib import shapes", "(arm(), shapes.size())")
        reference, closure = self.record()
        self.assertNotIn("lib/boot.py", closure.files, "the child's own helper stays the child's")
        self.assertIn("setup", closure.names["lib/shapes.py"])
        self.edit(self.root / "lib/shapes.py", "return 1", "return 2")
        self.assert_clause_two(reference, False)
        self.edit(self.root / "lib/shapes.py", "CONFIG[0] = 20.0", "CONFIG[0] = 25.0")
        self.assert_clause_two(reference, True, "lib/shapes.py")

    # --- what a helper may carry without losing its reach -------------------------

    def test_a_main_guard_leaves_its_helper_sliced(self):
        self.write("lib/geo.py", GEO + "\n\nif __name__ == '__main__':\n    import time\n    t0 = time.time()\n    shown = plane((0, 0, 0), (0, 0, 1))\n    print(shown, time.time() - t0, also_unrelated())\n")
        reference, closure = self.record()
        self.assertEqual(closure.names["lib/geo.py"], ("SCALE", "_unit", "plane"))
        self.edit(self.geo, "return x + 1", "return x + 2")
        self.assert_clause_two(reference, False)

    def test_lazy_annotations_leave_typed_helpers_optional(self):
        typed = "from __future__ import annotations\n\nimport math\nfrom lib import spec\n\nSCALE: float = 2.0\n\n\ndef plane(origin: tuple, z_dir: tuple) -> tuple:\n    return (origin, z_dir, SCALE * spec.BORE * math.pi)\n\n\ndef unrelated(x: float) -> float:\n    return x + 1\n"
        self.write("lib/geo.py", typed)
        reference, closure = self.record()
        self.assertEqual(closure.names["lib/geo.py"], ("SCALE", "plane"))
        self.edit(self.geo, "return x + 1", "return x + 2")
        self.geo.write_text(self.geo.read_text(encoding="utf-8") + "\n\ndef added(width: float = 3.0) -> float:\n    return width\n", encoding="utf-8")
        self.assert_clause_two(reference, False)
        self.edit(self.geo, "SCALE: float = 2.0", "SCALE: float = 3.0")
        self.assert_clause_two(reference, True, "lib/geo.py")

    def test_an_unanalysable_helper_is_hashed_whole_and_kept(self):
        from cadgen.store.closure import execution_digest
        from cadgen._internal.source_hash import _semantic_source_bytes

        deep = "def deep():\n    return " + " + ".join(["1"] * 1000) + "\n"
        path = self.write("lib/deep.py", deep)
        self.assertEqual(execution_digest(path.read_bytes()), _semantic_source_bytes(path.read_bytes()))
        self.write_model("from lib.deep import deep", "deep()")
        reference, closure = self.record(executed=self.executed(path))
        self.assertIn("lib/deep.py", closure.files)
        self.assertNotIn("lib/deep.py", closure.names)
        self.assert_clause_two(reference, False)
        self.edit(path, "return 1 + 1", "return 2 + 1")
        self.assert_clause_two(reference, True, "lib/deep.py")

    # --- the gate's cost ------------------------------------------------------------

    def test_the_gate_reuses_recorded_slices_of_unchanged_files(self):
        from cadgen.store import closure as module
        from cadgen.store.records import read_record, write_record

        reference, _closure = self.record()
        with mock.patch.object(module, "_SYNTAX", module._ImportSyntaxMemo()), \
                mock.patch.object(module, "_parse_import_syntax", wraps=module._parse_import_syntax) as parse:
            self.assert_clause_two(reference, False)
            self.assertEqual(parse.call_count, 0, "an unchanged file keeps its recorded slice")
            self.edit(self.geo, "return x + 1", "return x + 2")  # outside the slice
            self.assert_clause_two(reference, False)
            self.assertEqual([Path(call.args[1]).name for call in parse.call_args_list], ["geo.py"])
            record = read_record(reference)
            record["closure"].pop("wholes")  # a record without whole-file hashes re-slices
            write_record(reference, record)
            self.assert_clause_two(reference, False)
            self.assertEqual(sorted(Path(call.args[1]).name for call in parse.call_args_list[1:]),
                             ["__init__.py", "spec.py"])

    # --- determinism -------------------------------------------------------------------

    def test_hit_and_miss_runs_record_identical_closures(self):
        """The closure is a function of the sources alone: whatever executed,
        whatever the bytes captured at execution say, the reach is the same."""
        from cadgen.store.closure import build_closure

        cold = build_closure(self.model, executed={})
        warm = build_closure(self.model, executed=self.executed(self.model, self.geo, self.spec, self.root / "lib/__init__.py"))
        captured = build_closure(
            self.model, executed=self.executed(self.model, self.geo, self.spec),
            sources={str(path): path.read_bytes() for path in (self.model, self.geo, self.spec)},
        )
        self.assertEqual(cold, warm)
        self.assertEqual(cold, captured)
        self.assertEqual(cold.as_json(), captured.as_json())

    def test_the_slice_hashes_the_bytes_that_ran(self):
        """An edit landing mid-build: the reach and the hash both describe the
        revision the exec hook captured, never the file as it is afterwards."""
        import sys

        from cadgen.store.closure import ExecutionHashes, build_closure

        with ExecutionHashes() as executed, mock.patch.object(sys, "path", [str(self.root), *sys.path]):
            exec(compile(self.geo.read_bytes(), str(self.geo), "exec"), {"__name__": "lib.geo"})  # noqa: S102
            sys.modules.pop("lib.spec", None)
            sys.modules.pop("lib", None)
            self.edit(self.geo, "SCALE = 2.0", "SCALE = 9.0")  # edited mid-build
        self.assertIn(str(self.geo), executed.sources)
        recorded = build_closure(self.model, executed=executed.hashes, sources=executed.sources)
        self.edit(self.geo, "SCALE = 9.0", "SCALE = 2.0")
        original = build_closure(self.model, executed={})
        self.assertEqual(recorded.shas["lib/geo.py"], original.shas["lib/geo.py"])
        self.edit(self.geo, "SCALE = 2.0", "SCALE = 9.0")
        edited = build_closure(self.model, executed={})
        self.assertNotEqual(recorded.shas["lib/geo.py"], edited.shas["lib/geo.py"])

    def test_the_publish_rule_compares_slices(self):
        from cadgen.store.publish import decide

        reference, older = self.record()
        self.edit(self.geo, "return x + 1", "return x + 2")  # unreached: still the same slice
        self.assertTrue(decide(reference, ran_closure_hash=older.hash, ran_files=older.files, ran_names=older.names).publish_outputs)
        self.edit(self.geo, "SCALE = 2.0", "SCALE = 3.0")  # reached: the sources moved on
        reference, current = self.record()  # a record that reflects the sources as they are now
        self.assertNotEqual(older.hash, current.hash)
        self.assertFalse(decide(reference, ran_closure_hash=older.hash, ran_files=older.files, ran_names=older.names).publish_outputs)
        self.assertTrue(decide(reference, ran_closure_hash=current.hash, ran_files=current.files, ran_names=current.names).publish_outputs)


class ReachEndToEnd(unittest.TestCase):
    """Over a real model run: the record carries the reached names, an
    unreached helper edit leaves the model current, a reached one rebuilds it."""

    def setUp(self):
        import sys

        from cadgen.store.closure import forget_model_files

        scratch = generated_cad_directory(prefix="closure-reach-e2e-")
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name)
        env = mock.patch.dict(os.environ, {"CADGEN_CACHE_DIR": str(self.root / "store")})
        env.start()
        self.addCleanup(env.stop)
        forget_model_files()
        self.addCleanup(forget_model_files)
        self.repo = Path(__file__).resolve().parents[4]
        self.python = sys.executable
        (self.root / "src" / "lib").mkdir(parents=True)
        (self.root / "src" / "lib" / "__init__.py").write_text("", encoding="utf-8")
        self.geo = self.root / "src" / "lib" / "geo.py"
        self.geo.write_text(textwrap.dedent("""
            SIZE = 10.0


            def size():
                return SIZE


            def unrelated():
                return 1
        """).lstrip(), encoding="utf-8")
        self.model = self.root / "src" / "part.py"
        self.model.write_text(textwrap.dedent("""
            from cadgen import step
            from cadgen import build123d as bd
            from lib import geo


            @step
            def part():
                return bd.Box(geo.size(), 1, 1)


            if __name__ == "__main__":
                part()
        """).lstrip(), encoding="utf-8")

    def run_model(self):
        import subprocess

        env = dict(os.environ)
        env.update({"CADGEN_DAEMON": "0", "PYTHONPATH": str(self.repo / "packages/cadgen/src")})
        completed = subprocess.run(
            [self.python, self.model.name], cwd=str(self.model.parent), env=env,
            capture_output=True, text=True, timeout=600,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr[-2000:])
        return completed.stdout.strip().splitlines()[-1].split(" ", 1)[0]

    def edit(self, old, new):
        text = self.geo.read_text(encoding="utf-8")
        self.assertIn(old, text)
        self.geo.write_text(text.replace(old, new), encoding="utf-8")

    def test_an_unreached_helper_edit_leaves_a_built_model_current(self):
        from cadgen.store.gate import stale
        from cadgen.store.records import read_record

        self.assertEqual(self.run_model(), "built")
        record = read_record(self.model)
        self.assertEqual(record["closure"]["names"], {"lib/__init__.py": [], "lib/geo.py": ["SIZE", "size"]})
        self.assertTrue(record["closure"]["shas"]["lib/geo.py"].startswith("slice4:"))
        self.assertEqual(set(record["closure"]["wholes"]), {"lib/__init__.py", "lib/geo.py"})
        self.assertEqual(self.run_model(), "current")

        self.edit("return 1", "return 2")
        self.assertFalse(stale(self.model).stale, "an unreached helper edit")
        self.assertEqual(self.run_model(), "current")

        self.edit("SIZE = 10.0", "SIZE = 12.0")
        verdict = stale(self.model)
        self.assertTrue(verdict.stale)
        self.assertEqual(verdict.reason(), "closure changed: lib/geo.py")
        self.assertEqual(self.run_model(), "built", "a reached constant edit")
        self.assertEqual(self.run_model(), "current")

    def test_store_why_prints_the_reached_names(self):
        import subprocess

        self.assertEqual(self.run_model(), "built")
        env = dict(os.environ)
        env["PYTHONPATH"] = str(self.repo / "packages/cadgen/src")
        completed = subprocess.run(
            [self.python, "-m", "cadgen.cli", "store", "why", str(self.model)],
            env=env, capture_output=True, text=True, timeout=120,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr[-2000:])
        self.assertIn("lib/geo.py[SIZE, size]", completed.stdout)
        self.assertIn("verdict current", completed.stdout)


class ReachAnalysis(unittest.TestCase):
    """The per-module analysis, on bytes alone."""

    def analyze(self, source):
        from cadgen.store.reach import analyze

        return analyze(textwrap.dedent(source).encode("utf-8"), "m.py")

    def test_definitions_and_preamble(self):
        syntax = self.analyze("""
            import math
            from functools import lru_cache
            A = 1
            B = math.pi
            C = compute()
            D, E = 1, 2
            F: int = 3
            X.y = 2
            for i in range(3):
                pass

            def f(a=1):
                return a

            @lru_cache(maxsize=4)
            def g():
                return 1

            @register
            def h():
                return 1

            def k(v=compute()):
                return v

            class P:
                Q = 1

            class R(Base):
                pass

            class S(Exception):
                pass
        """)
        definitions = {name for name, _ in syntax.definitions.items()}
        self.assertEqual(definitions, {"A", "f"})
        preamble = {syntax.statements[i].binds for i in syntax.preamble}
        self.assertIn(("C",), preamble)
        self.assertIn(("h",), preamble)
        self.assertIn(("k",), preamble)
        self.assertIn(("R",), preamble)
        self.assertIn(("i",), preamble)
        self.assertTrue(syntax.dynamic.startswith("unresolved name"), syntax.dynamic)

    def test_familiar_modules_and_builtins_do_not_prove_call_purity(self):
        syntax = self.analyze("""
            import math
            from cadgen import build123d as bd, srgb
            from lib import registry
            COLOR = srgb("#fff")
            AXIS = bd.Vector(0, 0, 1).normalized()
            R = math.hypot(3, 4)
            NAMES = tuple(sorted(["b", "a"]))
            PARTS = "a b".split()
            TABLE = registry.load()
            ROWS = REGISTRY.get("k")
            REGISTRY = {}
        """)
        self.assertEqual(set(syntax.definitions), {"REGISTRY"})
        preamble_binds = {b for i in syntax.preamble for b in syntax.statements[i].binds}
        self.assertEqual(preamble_binds & {"TABLE", "ROWS"}, {"TABLE", "ROWS"})

    def test_a_main_guard_is_in_no_slice(self):
        from cadgen.store.reach import close_names, slice_hash

        source = textwrap.dedent("""
            def a():
                return 1

            def b():
                return 2

            if __name__ == "__main__":
                b()
        """)
        syntax = self.analyze(source)
        self.assertEqual(close_names(syntax, ["a"]), frozenset({"a"}))
        before = slice_hash(syntax, ["a"])
        self.assertEqual(before, slice_hash(self.analyze(source.replace("    b()", "    a()\n    b()")), ["a"]))

    def test_reads_resolve_locals_and_follow_globals(self):
        syntax = self.analyze("""
            import lib.geo as geo
            TOTAL = 0

            def f(x):
                global TOTAL
                y = [c for c in x]
                z = geo.plane(y)
                return z, TOTAL, len(y)
        """)
        f = syntax.statements[[i for i, s in enumerate(syntax.statements) if "f" in s.binds][0]]
        self.assertIn("TOTAL", f.reads)
        self.assertIn("len", f.reads)
        self.assertNotIn("y", f.reads)
        self.assertNotIn("c", f.reads)
        self.assertEqual(f.chains, (("geo", ("plane",)),))
        self.assertIsNone(syntax.dynamic)

    def test_slice_hash_is_stable_under_unreached_edits_and_moves_with_reached_ones(self):
        from cadgen.store.reach import slice_hash

        base = textwrap.dedent("""
            import math
            K = 2

            def a():
                return K

            def b():
                return 1
        """)
        before = slice_hash(self.analyze(base), ["a"])
        self.assertEqual(before, slice_hash(self.analyze(base.replace("return 1", "return 2")), ["a"]))
        self.assertEqual(before, slice_hash(self.analyze(base + "\ndef c():\n    return 3\n"), ["a"]))
        self.assertNotEqual(before, slice_hash(self.analyze(base.replace("K = 2", "K = 3")), ["a"]))
        self.assertNotEqual(before, slice_hash(self.analyze(base.replace("return K", "return K + 1")), ["a"]))
        self.assertNotEqual(before, slice_hash(self.analyze(base.replace("import math", "import math, os")), ["a"]))
        self.assertNotEqual(before, slice_hash(self.analyze(base), ["a", "b"]))
        self.assertTrue(before.startswith("slice4:"))
        self.assertTrue(slice_hash(self.analyze(base + "\nfrom os import *\n"), ["a"]).startswith("ast1:"))


if __name__ == "__main__":
    unittest.main()
