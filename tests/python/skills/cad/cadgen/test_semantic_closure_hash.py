import tempfile
import unittest
from pathlib import Path

from cadgen._internal import source_hash


def _closure(script: Path, base: Path):
    return source_hash.closure_for_files(script, [], base=base)


class SemanticClosureHashTests(unittest.TestCase):
    def _write(self, root: Path, name: str, text: str) -> Path:
        path = root / name
        path.write_text(text, encoding="utf-8")
        return path

    def test_comment_and_whitespace_edits_do_not_change_hash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            a = self._write(root, "gen.py", "def gen_step():\n    return build(radius=5)\n")
            hash_a = _closure(a, root).closure_hash
            # add a comment, blank lines, and reindent-free formatting
            a.write_text(
                "# a new comment\n\n"
                "def gen_step():\n"
                "    return build(radius=5)   # trailing comment\n\n\n",
                encoding="utf-8",
            )
            self.assertEqual(hash_a, _closure(a, root).closure_hash)

    def test_docstring_change_changes_hash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            a = self._write(root, "gen.py", 'def gen_step():\n    "one"\n    return 1\n')
            hash_a = _closure(a, root).closure_hash
            a.write_text('def gen_step():\n    "two"\n    return 1\n', encoding="utf-8")
            self.assertNotEqual(hash_a, _closure(a, root).closure_hash)

    def test_real_code_change_changes_hash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            a = self._write(root, "gen.py", "R = 5\ndef gen_step():\n    return R\n")
            hash_a = _closure(a, root).closure_hash
            a.write_text("R = 6\ndef gen_step():\n    return R\n", encoding="utf-8")
            self.assertNotEqual(hash_a, _closure(a, root).closure_hash)

    def test_syntax_error_falls_back_to_byte_hash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            a = self._write(root, "broken.py", "def gen_step(:\n    return 1\n")
            hash_a = _closure(a, root).closure_hash
            # a comment edit on an unparseable file DOES change the (byte) hash
            a.write_text("# c\ndef gen_step(:\n    return 1\n", encoding="utf-8")
            self.assertNotEqual(hash_a, _closure(a, root).closure_hash)

    def test_matches_rejects_legacy_byte_recorded_hash(self) -> None:
        """A byte-recorded digest reports STALE and rebuilds — the fallback is gone.

        There is one digest now. A descriptor written before comment-insensitive hashing
        reports stale exactly once, rebuilds, and re-records a semantic digest; the old
        dual-hash acceptance cost a second full-content re-read of every closure file on
        every miss and was the last data-compatibility path in the freshness stack.
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write(root, "gen.py", "def gen_step():\n    return 1\n")
            legacy = source_hash._recompute_closure_hash(
                ["gen.py"], base=root, hasher=source_hash._sha256_file
            )
            self.assertIsNotNone(legacy, "the byte recompute must still be reachable")
            self.assertFalse(source_hash.closure_hash_matches(legacy, ["gen.py"], base=root))

    def test_matches_accepts_semantic_hash_after_comment_edit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            a = self._write(root, "gen.py", "def gen_step():\n    return 1\n")
            semantic = _closure(a, root).closure_hash
            a.write_text("# comment\ndef gen_step():\n    return 1\n", encoding="utf-8")
            self.assertTrue(source_hash.closure_hash_matches(semantic, ["gen.py"], base=root))

    def test_matches_rejects_missing_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertFalse(source_hash.closure_hash_matches("abc", ["gone.py"], base=root))

    def test_deep_but_importable_source_falls_back_instead_of_raising(self) -> None:
        # 'x = 1 + 1 + ... + 1' compiles and imports fine, but ast.dump on the
        # deep tree can exceed the recursion limit (the exact depth depends on
        # the ambient stack, so pin the limit low to force it). The freshness
        # gate must degrade to byte sensitivity, never abort the build.
        import sys

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            deep = self._write(root, "deep.py", "x = 1" + " + 1" * 2000 + "\n")
            compile(deep.read_text(encoding="utf-8"), str(deep), "exec")  # importable
            limit = sys.getrecursionlimit()
            sys.setrecursionlimit(200)
            try:
                hash_a = source_hash._semantic_source_hash(deep)
            finally:
                sys.setrecursionlimit(limit)
            self.assertEqual(hash_a, source_hash._sha256_file(deep))  # byte fallback

    def test_pathological_nesting_falls_back_instead_of_raising(self) -> None:
        # A unary-minus chain overflows the CPython parser stack (MemoryError);
        # the hash must fall back to bytes, not propagate out of the gate.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            nested = self._write(root, "nested.py", "x = " + "-" * 100000 + "1\n")
            hash_a = source_hash._semantic_source_hash(nested)
            self.assertFalse(hash_a.startswith("ast1:"))
            self.assertFalse(source_hash.closure_hash_matches("abc", ["nested.py"], base=root))


class SemanticHashMemoTests(unittest.TestCase):
    def setUp(self) -> None:
        source_hash._SEMANTIC_HASH_CACHE.clear()

    tearDown = setUp

    def test_settled_file_is_cached_and_fresh_file_is_not(self) -> None:
        import os

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "gen.py"
            path.write_text("R = 5\n", encoding="utf-8")
            # Freshly written (mtime = now): hashed but not cached — a same-size
            # rewrite within one coarse filesystem clock tick must stay visible.
            source_hash._semantic_source_hash(path)
            self.assertNotIn(str(path), source_hash._SEMANTIC_HASH_CACHE)
            # Settled (mtime in the past): cached under (mtime_ns, size).
            os.utime(path, ns=(path.stat().st_atime_ns, path.stat().st_mtime_ns - 10**10))
            first = source_hash._semantic_source_hash(path)
            self.assertIn(str(path), source_hash._SEMANTIC_HASH_CACHE)
            self.assertEqual(first, source_hash._semantic_source_hash(path))

    def test_same_size_edit_with_new_mtime_recomputes(self) -> None:
        import os

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "gen.py"
            path.write_text("R = 5\n", encoding="utf-8")
            os.utime(path, ns=(path.stat().st_atime_ns, path.stat().st_mtime_ns - 10**10))
            first = source_hash._semantic_source_hash(path)
            self.assertIn(str(path), source_hash._SEMANTIC_HASH_CACHE)
            # Same byte length, different semantics, different (settled) mtime.
            path.write_text("R = 6\n", encoding="utf-8")
            os.utime(path, ns=(path.stat().st_atime_ns, path.stat().st_mtime_ns - 10**9 * 5))
            self.assertNotEqual(first, source_hash._semantic_source_hash(path))


class RuntimeRootsStdinFootgunTests(unittest.TestCase):
    def test_placeholder_main_file_does_not_mark_cwd_as_runtime(self) -> None:
        # A stdin / `-c` driven build sets __main__.__file__ to '<stdin>', whose
        # resolve().parent is the CWD; that must NOT be treated as a runtime root
        # (which would exclude the model + its sibling helpers from the closure
        # and silently disable staleness detection).
        import sys

        main = sys.modules["__main__"]
        original = getattr(main, "__file__", None)
        source_hash._runtime_roots.cache_clear()
        try:
            main.__file__ = "<stdin>"
            source_hash._runtime_roots.cache_clear()
            roots = source_hash._runtime_roots()
            self.assertNotIn(Path.cwd().resolve(), roots)
        finally:
            if original is None:
                if hasattr(main, "__file__"):
                    del main.__file__
            else:
                main.__file__ = original
            source_hash._runtime_roots.cache_clear()
            # _excluded_roots composes _runtime_roots and caches independently:
            # drop it too so no classification computed inside the mutation
            # window can outlive the restore.
            source_hash._excluded_roots.cache_clear()

    def test_real_launcher_file_is_a_runtime_root(self) -> None:
        import sys

        main = sys.modules["__main__"]
        original = getattr(main, "__file__", None)
        with tempfile.TemporaryDirectory() as tmp:
            launcher = Path(tmp) / "__main__.py"
            launcher.write_text("# launcher\n", encoding="utf-8")
            source_hash._runtime_roots.cache_clear()
            try:
                main.__file__ = str(launcher)
                source_hash._runtime_roots.cache_clear()
                roots = source_hash._runtime_roots()
                self.assertIn(launcher.parent.resolve(), roots)
            finally:
                if original is None:
                    if hasattr(main, "__file__"):
                        del main.__file__
                else:
                    main.__file__ = original
                source_hash._runtime_roots.cache_clear()


if __name__ == "__main__":
    unittest.main()
