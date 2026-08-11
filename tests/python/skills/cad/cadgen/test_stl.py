import shutil
import unittest
from pathlib import Path

from cadgen import catalog as cad_catalog
from tests.python.support.cad_test_roots import IsolatedCadRoots


class CadpyRenderTests(unittest.TestCase):
    def setUp(self) -> None:
        self._isolated_roots = IsolatedCadRoots(self, prefix="cadjs-")
        tempdir = self._isolated_roots.temporary_cad_directory(prefix="tmp-cadjs-")
        self._tempdir = tempdir
        self.temp_root = Path(tempdir.name)
        self.relative_dir = self.temp_root.relative_to(Path.cwd()).as_posix()
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
                cad_catalog.render_package_dir(step_path),
            )
        )
        return step_path

    def test_glb_path_resolves_into_cadgen_dir(self) -> None:
        step_path = self._write_step("part")

        glb_path = cad_catalog.render_package_dir(step_path)

        # The render artifact (a component-GLB package dir) lives inside __cadgen__,
        # keyed by the STEP filename, so the model folder holds only source.
        self.assertEqual(self.temp_root / "__cadgen__" / "models" / "part.step", glb_path)

    def test_glb_path_preserves_stp_extension(self) -> None:
        step_path = self._write_step("part-stp", extension=".stp")

        glb_path = cad_catalog.render_package_dir(step_path)

        self.assertEqual(self.temp_root / "__cadgen__" / "models" / "part-stp.stp", glb_path)


if __name__ == "__main__":
    unittest.main()
