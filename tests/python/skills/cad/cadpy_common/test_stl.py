import shutil
import unittest
from pathlib import Path

from cadpy_common import render as cad_render
from tests.python.support.cad_test_roots import IsolatedCadRoots


class CadpyRenderTests(unittest.TestCase):
    def setUp(self) -> None:
        self._isolated_roots = IsolatedCadRoots(self, prefix="cadjs-")
        tempdir = self._isolated_roots.temporary_cad_directory(prefix="tmp-cadjs-")
        self._tempdir = tempdir
        self.temp_root = Path(tempdir.name)
        self.relative_dir = self.temp_root.relative_to(cad_render.CAD_ROOT).as_posix()
        self.cleanup_paths: set[Path] = set()

    def tearDown(self) -> None:
        for path in self.cleanup_paths:
            path.unlink(missing_ok=True)
        shutil.rmtree(self.temp_root, ignore_errors=True)
        self._tempdir.cleanup()

    def _write_step(self, name: str, *, extension: str = ".step") -> Path:
        step_path = self.temp_root / f"{name}{extension}"
        step_path.write_text("ISO-10303-21; END-ISO-10303-21;\n")
        self.cleanup_paths.update(
            (
                cad_render.part_glb_path(step_path),
            )
        )
        return step_path

    def test_direct_step_has_no_persistent_stl_path(self) -> None:
        step_path = self._write_step("part")

        with self.assertRaisesRegex(ValueError, "no configured STL output"):
            cad_render.part_stl_path(step_path)

    def test_glb_path_uses_adjacent_hidden_step_glb(self) -> None:
        step_path = self._write_step("part")

        glb_path = cad_render.part_glb_path(step_path)

        self.assertEqual(self.temp_root / ".part.step.glb", glb_path)
        self.assertEqual(self.temp_root / ".part.step" / "model.glb", cad_render.legacy_part_glb_path(step_path))

    def test_glb_path_preserves_stp_extension(self) -> None:
        step_path = self._write_step("part-stp", extension=".stp")

        glb_path = cad_render.part_glb_path(step_path)

        self.assertEqual(self.temp_root / ".part-stp.stp.glb", glb_path)
        self.assertEqual(self.temp_root / ".part-stp.stp" / "model.glb", cad_render.legacy_part_glb_path(step_path))


if __name__ == "__main__":
    unittest.main()
