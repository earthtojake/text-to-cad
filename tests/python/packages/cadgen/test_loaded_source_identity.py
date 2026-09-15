"""A revision records the source bytes actually compiled, including module load."""

from __future__ import annotations

import builtins
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


class LoadedSourceIdentity(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory(prefix="cadgen-loaded-source-")
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name).resolve()
        self.script = self.root / "model.py"
        old_path = list(sys.path)
        old_modules = set(sys.modules)

        def restore():
            sys.path[:] = old_path
            for name in set(sys.modules) - old_modules:
                module_path = getattr(sys.modules[name], "__file__", None)
                if module_path and Path(module_path).is_relative_to(self.root):
                    sys.modules.pop(name, None)

        self.addCleanup(restore)

    def test_loader_records_compiled_bytes_even_if_replaced_before_exec(self):
        from cadgen._internal.generation_runner import _load_generator_module
        from cadgen._internal.source_hash import _semantic_source_bytes, _semantic_source_hash
        from cadgen.store.closure import ExecutionHashes

        original = b"VALUE = 1\n"
        self.script.write_bytes(original)
        real_compile = builtins.compile

        def compile_then_replace(source, filename, *args, **kwargs):
            code = real_compile(source, filename, *args, **kwargs)
            if filename == str(self.script):
                self.script.write_bytes(b"VALUE = 2\n")
            return code

        with ExecutionHashes() as hashes, mock.patch("builtins.compile", compile_then_replace):
            module = _load_generator_module(self.script)
        self.assertEqual(module.VALUE, 1)
        self.assertEqual(hashes.hashes[str(self.script)], _semantic_source_bytes(original))
        self.assertNotEqual(hashes.hashes[str(self.script)], _semantic_source_hash(self.script))

    def test_load_and_body_window_keeps_import_hash_before_module_changes_it(self):
        from cadgen._internal.generation_runner import _run_script_generator_body
        from cadgen._internal.source_hash import _semantic_source_bytes
        from cadgen.store.closure import ExecutionHashes

        # Exercise the runner's real load/body window without generating CAD.
        # Its post-body payload handling is irrelevant to the captured closure.
        from cadgen._internal import generation_runner

        helper = self.root / "loaded_identity_helper.py"
        original = b"VALUE = 1\n"
        helper.write_bytes(original)
        self.script.write_text(
            "from pathlib import Path\n"
            "import loaded_identity_helper as helper\n"
            "Path(helper.__file__).write_text('VALUE = 2\\n')\n"
            "def model():\n"
            "    return helper.VALUE\n",
            encoding="utf-8",
        )
        import contextlib
        from types import SimpleNamespace

        captured = []

        class CaptureHashes(ExecutionHashes):
            def __exit__(self, *exc):
                captured.append(dict(self.hashes))
                super().__exit__(*exc)

        spec = SimpleNamespace(
            script_path=self.script,
            source_ref=str(self.script),
            generator_metadata=SimpleNamespace(entry_function="model"),
            step_path=self.root / "unused.step",
        )
        logger = SimpleNamespace(timed=lambda *a, **k: contextlib.nullcontext())
        with (
            mock.patch("cadgen.store.closure.ExecutionHashes", CaptureHashes),
            mock.patch.object(generation_runner, "_normalize_step_payload", side_effect=RuntimeError("after body")),
            mock.patch.dict(os.environ, {"CADGEN_CACHE_DIR": str(self.root / "store")}),
        ):
            with self.assertRaisesRegex(RuntimeError, "after body"):
                _run_script_generator_body(spec, model_format="step", logger=logger)
        self.assertEqual(len(captured), 1)
        self.assertEqual(captured[0][str(helper)], _semantic_source_bytes(original))

    def test_byte_hash_matches_path_hash_for_python_and_invalid_source(self):
        from cadgen._internal.source_hash import _semantic_source_bytes, _semantic_source_hash

        for source in (b"VALUE = 1\n", b"# comment\nVALUE=1\n", b"def broken(:\n"):
            with self.subTest(source=source):
                self.script.write_bytes(source)
                self.assertEqual(_semantic_source_bytes(source), _semantic_source_hash(self.script))


if __name__ == "__main__":
    unittest.main()
