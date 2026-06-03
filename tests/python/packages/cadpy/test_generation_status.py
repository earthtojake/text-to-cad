from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadpy/src")

from cadpy.generation_status import GenerationOutput, track_generation_run


class GenerationStatusTests(unittest.TestCase):
    def test_generation_status_uses_hidden_lock_next_to_output_and_cleans_up(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cadpy-generation-status-") as tempdir:
            workspace = Path(tempdir) / "workspace"
            model_dir = workspace / "models"
            skill_dir = Path(tempdir) / "installed-skill"
            source_path = model_dir / "part.py"
            step_path = model_dir / "part.step"
            model_dir.mkdir(parents=True)
            source_path.write_text("def gen_step():\n    return None\n", encoding="utf-8")
            (skill_dir / "scripts").mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text("# skill\n", encoding="utf-8")

            with track_generation_run(
                source_path=source_path,
                generator="gen_step",
                outputs=[GenerationOutput(step_path, "step")],
                repo_root=skill_dir,
            ):
                lock_paths = tuple(model_dir.glob(".part.step.*.generation.lock.json"))
                self.assertEqual(1, len(lock_paths))
                payload = json.loads(lock_paths[0].read_text(encoding="utf-8"))
                self.assertEqual("running", payload["status"])
                self.assertEqual("gen_step", payload["generator"])
                self.assertEqual("part.py", payload["sourcePath"])
                self.assertEqual("part.step", payload["outputs"][0]["path"])
                self.assertFalse(tuple(skill_dir.rglob("*.generation.lock.json")))

            self.assertFalse(lock_paths[0].exists())

    def test_generation_status_writes_one_lock_for_each_output_without_blocking(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cadpy-generation-status-") as tempdir:
            model_dir = Path(tempdir) / "models"
            step_path = model_dir / "part.step"
            glb_path = model_dir / ".part.step.glb"
            model_dir.mkdir(parents=True)

            with track_generation_run(
                source_path=None,
                generator="gen_step",
                outputs=[
                    GenerationOutput(step_path, "step"),
                    GenerationOutput(glb_path, "glb"),
                ],
                repo_root=Path(tempdir),
            ):
                step_locks = tuple(model_dir.glob(".part.step.*.generation.lock.json"))
                glb_locks = tuple(model_dir.glob("..part.step.glb.*.generation.lock.json"))
                self.assertEqual(1, len(step_locks))
                self.assertEqual(1, len(glb_locks))
                self.assertNotEqual(step_locks[0], glb_locks[0])

            self.assertFalse(tuple(model_dir.glob("*.generation.lock.json")))


if __name__ == "__main__":
    unittest.main()
