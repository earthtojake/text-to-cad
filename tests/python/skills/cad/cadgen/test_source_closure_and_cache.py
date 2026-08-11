"""Regression tests for incremental-regen building blocks:

- source import-closure capture/check (cadgen.source_hash)
- the binary (BinTools) scene cache round-trip
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

import build123d
from OCP.TopAbs import TopAbs_FACE
from OCP.TopExp import TopExp_Explorer

from cadgen._internal import source_hash as cad_source_hash
from cadgen._internal import step_scene
from cadgen._internal.step_scene import LoadedStepScene, OccurrenceNode
from tests.python.support.tmp_root import temporary_directory


def _face_count(shape: object) -> int:
    explorer = TopExp_Explorer(shape, TopAbs_FACE)
    count = 0
    while explorer.More():
        count += 1
        explorer.Next()
    return count


class SourceClosureTests(unittest.TestCase):
    def test_closure_round_trip_detects_dependency_changes(self) -> None:
        with temporary_directory(prefix="closure-") as raw_dir:
            base = Path(raw_dir)
            script = base / "part.py"
            dep = base / "helper.py"
            script.write_text("import helper\n", encoding="utf-8")
            dep.write_text("VALUE = 1\n", encoding="utf-8")

            closure = cad_source_hash.closure_for_files(script, [dep], base=base)
            # The script and its dependency are both recorded.
            self.assertEqual(2, len(closure.files))

            # Re-checking the recorded file list against the recorded hash matches.
            self.assertTrue(
                cad_source_hash.closure_hash_matches(closure.closure_hash, closure.files, base=base)
            )

            # A semantic edit to a dependency invalidates the recorded hash (stale).
            dep.write_text("VALUE = 2\n", encoding="utf-8")
            self.assertFalse(
                cad_source_hash.closure_hash_matches(closure.closure_hash, closure.files, base=base)
            )

            # A missing recorded file is never a match (callers treat as stale).
            dep.unlink()
            self.assertFalse(
                cad_source_hash.closure_hash_matches(closure.closure_hash, closure.files, base=base)
            )

    def test_capture_runtime_closure_includes_imported_repo_local_modules(self) -> None:
        with temporary_directory(prefix="closure-capture-") as raw_dir:
            base = Path(raw_dir)
            script = base / "widget.py"
            dep = base / "shared_helper.py"
            script.write_text("import shared_helper\n", encoding="utf-8")
            dep.write_text("X = 1\n", encoding="utf-8")

            # Ensure a clean import so the sys.modules delta actually captures it.
            sys.modules.pop("shared_helper", None)
            before = set(sys.modules)
            sys.path.insert(0, str(base))
            try:
                import shared_helper  # noqa: F401  (exercise a real import)
                closure = cad_source_hash.capture_runtime_closure(before, script, base=base)
            finally:
                sys.path.remove(str(base))
                sys.modules.pop("shared_helper", None)

            self.assertIn("shared_helper.py", " ".join(closure.files))
            self.assertTrue(any(f.endswith("widget.py") for f in closure.files))

    def test_repo_local_modules_key_on_interpreter_not_cwd(self) -> None:
        """First-party detection keys on the interpreter's stdlib/site-packages layout, NOT a
        repo-root global or the process working directory. So the dependency closure a generator
        records is identical no matter which directory the build runs from, while build123d / OCP /
        stdlib stay excluded. Guards against reintroducing a repo-root containment filter (which
        silently truncated the closure when a build ran from a subdirectory)."""
        import json  # noqa: F401  (a stdlib module: must always be excluded)
        import os

        with temporary_directory(prefix="closure-root-indep-") as raw_dir:
            base = Path(raw_dir)
            (base / "first_party_mod.py").write_text("Y = 1\n", encoding="utf-8")
            sys.modules.pop("first_party_mod", None)
            sys.path.insert(0, str(base))
            previous_cwd = Path.cwd()
            try:
                import first_party_mod  # noqa: F401  (a real first-party import)
                names = ["json", "build123d", "first_party_mod"]
                # Capture from two unrelated working directories; the result must be identical
                # because the filter consults neither the cwd nor any repo-root global.
                results = []
                for cwd in (base, base.parent):
                    os.chdir(cwd)
                    results.append(cad_source_hash.repo_local_loaded_modules(names))
            finally:
                os.chdir(previous_cwd)
                sys.path.remove(str(base))
                sys.modules.pop("first_party_mod", None)

        self.assertEqual(results[0], results[1])
        captured = results[0]
        self.assertIn("first_party_mod", captured)   # first-party temp module: included
        self.assertNotIn("json", captured)           # stdlib: excluded
        self.assertNotIn("build123d", captured)      # site-packages: excluded


class BinarySceneCacheTests(unittest.TestCase):
    _IDENTITY = (1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, 1.0)

    def _scene(self, step_path: Path) -> LoadedStepScene:
        shape = build123d.Box(3, 2, 1).wrapped
        node = OccurrenceNode(
            path=(1,),
            name="box",
            source_name="box",
            transform=self._IDENTITY,
            local_transform=self._IDENTITY,
            prototype_key=7,
        )
        return LoadedStepScene(
            step_path=step_path,
            roots=[node],
            prototype_shapes={7: shape},
            prototype_names={7: "box"},
        )

    def test_cache_round_trip_is_binary_and_preserves_geometry(self) -> None:
        with temporary_directory(prefix="scene-cache-") as raw_dir:
            step_path = Path(raw_dir) / "box.step"
            step_path.write_text("ISO-10303-21;\n", encoding="utf-8")
            scene = self._scene(step_path)
            expected_faces = _face_count(scene.prototype_shapes[7])

            step_scene._write_step_scene_cache(scene, step_hash="hash-abc")

            # The cache is written inline beside the STEP in __cadgen__, as binary
            # BREP (.bin), not ASCII (.brep).
            cadgen_dir = step_path.parent / "__cadgen__"
            self.assertTrue(cadgen_dir.is_dir())
            self.assertEqual(1, len(list(cadgen_dir.rglob("*.bin"))))
            self.assertEqual([], list(cadgen_dir.rglob("*.brep")))

            cached = step_scene._read_step_scene_cache(step_path, step_hash="hash-abc")
            self.assertIsNotNone(cached)
            assert cached is not None
            self.assertEqual(1, len(cached.prototype_shapes))
            (restored_shape,) = cached.prototype_shapes.values()
            self.assertEqual(expected_faces, _face_count(restored_shape))

    def test_cache_misses_on_schema_version_bump(self) -> None:
        with temporary_directory(prefix="scene-cache-schema-") as raw_dir:
            step_path = Path(raw_dir) / "box.step"
            step_path.write_text("ISO-10303-21;\n", encoding="utf-8")
            step_scene._write_step_scene_cache(self._scene(step_path), step_hash="hash-xyz")

            with mock.patch.object(
                step_scene, "STEP_SCENE_CACHE_SCHEMA_VERSION", step_scene.STEP_SCENE_CACHE_SCHEMA_VERSION + 1
            ):
                self.assertIsNone(
                    step_scene._read_step_scene_cache(step_path, step_hash="hash-xyz")
                )


class ImportStepCachedTests(unittest.TestCase):
    """cadgen import_step: build123d shape identical to build123d.import_step, served from cache."""

    def test_matches_import_step_and_reuses_cache(self) -> None:
        with temporary_directory(prefix="import-cached-") as raw_dir:
            step_path = Path(raw_dir) / "widget.step"
            build123d.export_step(build123d.Box(4, 3, 2), step_path)

            raw = build123d.import_step(step_path)
            cached = step_scene.import_step(step_path)  # cold: parses + writes cache

            self.assertEqual(_face_count(raw.wrapped), _face_count(cached.wrapped))
            self.assertAlmostEqual(raw.volume, cached.volume, places=4)
            self.assertTrue((step_path.parent / "__cadgen__").is_dir())

            # Second call must hit the inline cache — no re-parse — and still match.
            with mock.patch.object(step_scene, "load_step_scene", side_effect=AssertionError("cache miss")):
                cached_warm = step_scene.import_step(step_path)
            self.assertAlmostEqual(raw.volume, cached_warm.volume, places=4)


if __name__ == "__main__":
    unittest.main()
