"""Removal of 0.3.x-era artifacts that sat beside a model's source file.

These tests delete files, so they lean on the narrow side: the point of most of
them is what the pruner REFUSES to touch.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from cadgen._internal.legacy_artifacts import (
    find_legacy_artifacts,
    legacy_explorer_dir,
    legacy_glb_path,
    legacy_lock_paths,
    prune_legacy_artifacts,
)


class LegacyArtifactPathTest(unittest.TestCase):
    def test_paths_follow_the_0_3_x_naming(self) -> None:
        entry = Path("/models/parts/bracket.step")
        self.assertEqual(Path("/models/parts/.bracket.step.glb"), legacy_glb_path(entry))
        self.assertEqual(Path("/models/parts/.bracket.step"), legacy_explorer_dir(entry))

    def test_generator_entries_use_the_full_name_not_the_stem(self) -> None:
        # `.step.py` entries keep both suffixes: the sidecar was `.<name>.glb`, so a
        # stem-based path would miss every generated model.
        entry = Path("/models/parts/bracket.step.py")
        self.assertEqual(Path("/models/parts/.bracket.step.py.glb"), legacy_glb_path(entry))


class LegacyArtifactPruneTest(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.root = Path(self._temp.name)
        self.entry = self.root / "bracket.step"
        self.entry.write_bytes(b"ISO-10303-21;")

    def tearDown(self) -> None:
        self._temp.cleanup()

    def _write_explorer_dir(self) -> Path:
        explorer = legacy_explorer_dir(self.entry)
        (explorer / "components").mkdir(parents=True)
        (explorer / "model.glb").write_bytes(b"glb")
        (explorer / "topology.json").write_text("{}")
        (explorer / "topology.bin").write_bytes(b"bin")
        (explorer / "components" / "abc123.glb").write_bytes(b"component")
        return explorer

    def test_removes_the_hidden_glb_the_explorer_dir_and_stale_locks(self) -> None:
        glb = legacy_glb_path(self.entry)
        glb.write_bytes(b"x" * 2048)
        explorer = self._write_explorer_dir()
        lock = self.root / f".{glb.name}.run7.generation.lock.json"
        lock.write_text("{}")

        result = prune_legacy_artifacts(self.entry)

        self.assertFalse(glb.exists())
        self.assertFalse(explorer.exists())
        self.assertFalse(lock.exists())
        self.assertEqual({glb, explorer, lock}, set(result["removed"]))
        self.assertGreater(result["bytes"], 2048)
        # The source itself is never a candidate.
        self.assertTrue(self.entry.exists())

    def test_leaves_the_current_cache_and_sibling_models_alone(self) -> None:
        legacy_glb_path(self.entry).write_bytes(b"glb")
        cache = self.root / "__cadgen__" / "models" / "bracket.step"
        cache.mkdir(parents=True)
        (cache / "assembly.json").write_text("{}")
        other = self.root / "flange.step"
        other.write_bytes(b"ISO-10303-21;")
        other_glb = legacy_glb_path(other)
        other_glb.write_bytes(b"glb")

        prune_legacy_artifacts(self.entry)

        self.assertTrue((cache / "assembly.json").exists())
        self.assertTrue(other_glb.exists(), "pruning one entry must not touch another's")

    def test_keeps_hand_authored_sidecars(self) -> None:
        # 0.3.x sidecar SOURCE files, and the 0.4.x parameter sidecar. None of these
        # are generated output and deleting one would destroy the user's work.
        keepers = [
            self.root / ".bracket.step.js",
            self.root / "bracket.step.js",
            self.root / "bracket.params.js",
            self.root / "bracket.step.py",
        ]
        for path in keepers:
            path.write_text("// authored")
        legacy_glb_path(self.entry).write_bytes(b"glb")

        prune_legacy_artifacts(self.entry)

        for path in keepers:
            self.assertTrue(path.exists(), f"{path.name} must survive")

    def test_refuses_an_explorer_dir_holding_anything_unrecognized(self) -> None:
        explorer = self._write_explorer_dir()
        (explorer / "notes.txt").write_text("mine")

        result = prune_legacy_artifacts(self.entry)

        self.assertTrue(explorer.exists(), "one unknown name protects the whole directory")
        self.assertEqual([explorer], result["skipped"])
        self.assertEqual([], result["removed"])

    def test_refuses_an_explorer_dir_with_an_unexpected_subdirectory(self) -> None:
        explorer = self._write_explorer_dir()
        (explorer / "renders").mkdir()

        prune_legacy_artifacts(self.entry)

        self.assertTrue(explorer.exists())

    def test_refuses_symlinked_artifacts(self) -> None:
        outside = self.root / "keep-me.glb"
        outside.write_bytes(b"precious")
        link = legacy_glb_path(self.entry)
        link.symlink_to(outside)

        result = prune_legacy_artifacts(self.entry)

        self.assertTrue(outside.exists(), "must never delete through a symlink")
        self.assertEqual([], result["removed"])

    def test_does_nothing_when_the_source_entry_is_gone(self) -> None:
        # Without the source there is no evidence these hidden files were ever ours.
        legacy_glb_path(self.entry).write_bytes(b"glb")
        orphan_glb = legacy_glb_path(self.entry)
        self.entry.unlink()

        result = prune_legacy_artifacts(self.entry)

        self.assertTrue(orphan_glb.exists())
        self.assertEqual([], result["removed"])

    def test_is_a_no_op_on_a_clean_0_4_x_model(self) -> None:
        result = prune_legacy_artifacts(self.entry)
        self.assertEqual([], result["removed"])
        self.assertEqual([], result["skipped"])
        self.assertEqual(0, result["bytes"])

    def test_find_reports_without_deleting(self) -> None:
        glb = legacy_glb_path(self.entry)
        glb.write_bytes(b"glb")

        found = find_legacy_artifacts(self.entry)

        self.assertEqual([glb], found["paths"])
        self.assertTrue(glb.exists(), "find must not delete")

    def test_lock_glob_ignores_directories_and_other_names(self) -> None:
        glb_name = legacy_glb_path(self.entry).name
        real = self.root / f".{glb_name}.run1.generation.lock.json"
        real.write_text("{}")
        (self.root / f".{glb_name}.run2.generation.lock.json").mkdir()
        (self.root / "unrelated.generation.lock.json").write_text("{}")

        self.assertEqual([real], legacy_lock_paths(self.entry))


if __name__ == "__main__":
    unittest.main()
