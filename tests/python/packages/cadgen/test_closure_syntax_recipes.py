"""Shared syntax never substitutes old bytes or a resolved dependency graph."""

from __future__ import annotations

import os
from pathlib import Path
import sys
import unittest
from unittest import mock

from tests.python.support.tmp_root import generated_cad_directory


class ClosureSyntaxRecipes(unittest.TestCase):
    def setUp(self):
        from cadgen.store import closure

        self.closure = closure
        self.scratch = generated_cad_directory(prefix="closure-syntax-")
        self.addCleanup(self.scratch.cleanup)
        self.root = Path(self.scratch.name)
        closure.forget_model_files()
        self.addCleanup(closure.forget_model_files)

    def write(self, name, source):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")
        return path.resolve()

    def test_one_build_shares_syntax_but_another_build_starts_fresh(self):
        shared = self.write("shared.py", "def helper():\n    return 3\n")
        children = [self.write(f"{name}.py", "from cadgen import step\nfrom shared import helper\n"
                               f"@step\ndef {name}():\n    return helper()\n") for name in ("left", "right")]
        root = self.write("root.py", "from left import left\nfrom right import right\n")
        executed = {str(path): self.closure._semantic_source_hash(path) for path in [root, shared, *children]}
        with mock.patch.object(self.closure, "_IMPORT_SYNTAX_MAX_ENTRIES", 0):
            expected = self.closure.build_closure(root, executed=executed, children=children)
        payload = shared.read_bytes()
        with mock.patch.object(self.closure, "_parse_import_syntax", wraps=self.closure._parse_import_syntax) as parse:
            first = self.closure.build_closure(root, executed=executed, children=children)
            self.assertEqual(sum(call.args[0] == payload for call in parse.call_args_list), 1)
            second = self.closure.build_closure(root, executed=executed, children=children)
            self.assertEqual(sum(call.args[0] == payload for call in parse.call_args_list), 2)
        self.assertEqual(first, expected)
        self.assertEqual(second, expected)
        self.assertEqual(first.files, ("root.py",))

    def test_hit_rereads_same_size_source_even_with_restored_mtime(self):
        first = self.write("first.py", "value = 1\n")
        other = self.write("other.py", "value = 2\n")
        script = self.write("root.py", "from first import value\n")
        stat = script.stat()
        memo = self.closure._ImportSyntaxMemo()
        self.assertEqual(self.closure.static_imports(script, _syntax=memo).source_files, (first,))
        script.write_text("from other import value\n", encoding="utf-8")
        os.utime(script, ns=(stat.st_atime_ns, stat.st_mtime_ns))
        self.assertEqual(script.stat().st_size, stat.st_size)
        self.assertEqual(self.closure.static_imports(script, _syntax=memo).source_files, (other,))
        script.unlink()
        self.assertEqual(self.closure.static_imports(script, _syntax=memo), self.closure.StaticImports((), ()))

    def test_identical_bytes_resolve_relative_imports_from_each_current_directory(self):
        first = self.write("first/helper.py", "value = 1\n")
        other = self.write("other/helper.py", "value = 2\n")
        scripts = [self.write(f"{name}/root.py", "from .helper import value\n") for name in ("first", "other")]
        memo = self.closure._ImportSyntaxMemo()
        with mock.patch.object(self.closure, "_parse_import_syntax", wraps=self.closure._parse_import_syntax) as parse:
            self.assertEqual(self.closure.static_imports(scripts[0], _syntax=memo).source_files, (first,))
            self.assertEqual(self.closure.static_imports(scripts[1], _syntax=memo).source_files, (other,))
        self.assertEqual(parse.call_count, 1)

    def test_hit_rechecks_module_creation_deletion_and_changed_search_roots(self):
        script = self.write("root.py", "from helper import value\n")
        memo = self.closure._ImportSyntaxMemo()
        self.assertEqual(self.closure.static_imports(script, _syntax=memo).source_files, ())
        helper = self.write("helper.py", "value = 1\n")
        self.assertEqual(self.closure.static_imports(script, _syntax=memo).source_files, (helper,))
        helper.unlink()
        self.assertEqual(self.closure.static_imports(script, _syntax=memo).source_files, ())
        alternate = self.write("alternate/helper.py", "value = 2\n")
        with mock.patch.object(self.closure, "_search_roots", return_value=[alternate.parent]):
            self.assertEqual(self.closure.static_imports(script, _syntax=memo).source_files, (alternate,))
        self.assertEqual(self.closure.static_imports(script, _syntax=memo).source_files, ())

    def test_cached_result_collections_are_private_and_syntax_is_immutable(self):
        family = self.write("family.py", "from cadgen import step\nWIDTH = 3\n@step\ndef part():\n    pass\n")
        script = self.write("root.py", "from family import part, WIDTH\n")
        memo = self.closure._ImportSyntaxMemo()
        first = self.closure.static_imports(script, _syntax=memo)
        first.constants[str(family)]["WIDTH"] = "changed"
        second = self.closure.static_imports(script, _syntax=memo)
        self.assertNotEqual(first.constants, second.constants)
        recipe = next(iter(memo.entries.values()))[1]
        with self.assertRaises(AttributeError):
            recipe.imports = ()
        self.assertIsInstance(recipe.imports, tuple)
        self.assertIsInstance(recipe.taken, tuple)

    def test_invalid_source_is_not_admitted_and_empty_syntax_is_a_hit(self):
        memo = self.closure._ImportSyntaxMemo()
        with self.assertRaises(SyntaxError):
            memo.get(b"def (\n", "invalid.py")
        self.assertFalse(memo.entries)
        with mock.patch.object(self.closure, "_parse_import_syntax", wraps=self.closure._parse_import_syntax) as parse:
            first = memo.get(b"# comment\n", "one.py")
            second = memo.get(b"# comment\n", "two.py")
        self.assertIs(first, second)
        self.assertEqual(first.imports, ())
        self.assertEqual(parse.call_count, 1)

    def test_recipe_memo_enforces_byte_and_entry_bounds(self):
        payloads = [f"import module_{index}\n".encode() for index in range(3)]
        memo = self.closure._ImportSyntaxMemo()
        with mock.patch.object(self.closure, "_IMPORT_SYNTAX_MAX_ENTRIES", 2):
            memo.get(payloads[0], "one.py")
            memo.get(payloads[1], "two.py")
            memo.get(payloads[0], "one.py")
            memo.get(payloads[2], "three.py")
        self.assertEqual(list(memo.entries), [payloads[0], payloads[2]])
        memo = self.closure._ImportSyntaxMemo()
        memo.get(payloads[0], "one.py")
        one_charge = memo.size
        with mock.patch.object(self.closure, "_IMPORT_SYNTAX_MAX_BYTES", one_charge + 1):
            memo.get(payloads[1], "two.py")
            self.assertEqual(list(memo.entries), [payloads[1]])
            self.assertLessEqual(memo.size, one_charge + 1)
        memo = self.closure._ImportSyntaxMemo()
        with mock.patch.object(self.closure, "_IMPORT_SYNTAX_MAX_BYTES", 1):
            self.assertTrue(memo.get(payloads[0], "one.py").imports)
        self.assertFalse(memo.entries)
        self.assertEqual(memo.size, 0)

    def test_accounting_covers_retained_bytes_tuples_and_recipe_values(self):
        memo = self.closure._ImportSyntaxMemo()
        empty_bytes = sys.getsizeof(memo.entries)
        payload = b"from package import child as alias\nvalue = alias.part()\n"
        recipe = memo.get(payload, "model.py")
        seen = set()

        def size(value):
            if id(value) in seen:
                return 0
            seen.add(id(value))
            return sys.getsizeof(value) + (sum(size(item) for item in value) if isinstance(value, tuple) else 0)

        retained = (sys.getsizeof(memo.entries) - empty_bytes + size(payload)
                    + size(memo.entries[payload]) + size(recipe.imports) + size(recipe.taken))
        self.assertGreaterEqual(memo.size, retained)


if __name__ == "__main__":
    unittest.main()
