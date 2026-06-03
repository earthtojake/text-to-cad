import shutil
import unittest
from pathlib import Path

from cadpy_common import assembly_flatten
from cadpy_common import assembly_spec
from cadpy_common.render import part_glb_path
from tests.python.support.cad_test_roots import IsolatedCadRoots


def _translation(x: float, y: float, z: float) -> list[float]:
    return [
        1.0,
        0.0,
        0.0,
        x,
        0.0,
        1.0,
        0.0,
        y,
        0.0,
        0.0,
        1.0,
        z,
        0.0,
        0.0,
        0.0,
        1.0,
    ]


IDENTITY_TRANSFORM = _translation(0.0, 0.0, 0.0)


class AssemblyFlattenTests(unittest.TestCase):
    def setUp(self) -> None:
        self._isolated_roots = IsolatedCadRoots(self, prefix="assembly_flatten-")
        tempdir = self._isolated_roots.temporary_cad_directory(prefix="tmp-assembly_flatten-")
        self._tempdir = tempdir
        self.temp_root = Path(tempdir.name)
        self.relative_dir = self.temp_root.relative_to(assembly_spec.CAD_ROOT).as_posix()
        self.render_paths: list[Path] = []

    def tearDown(self) -> None:
        for render_path in self.render_paths:
            render_path.unlink(missing_ok=True)
        shutil.rmtree(self.temp_root, ignore_errors=True)
        self._tempdir.cleanup()

    def _cad_ref(self, name: str) -> str:
        return f"{self.relative_dir}/{name}"

    def _write_part(self, name: str) -> None:
        step_path = self.temp_root / f"{name}.step"
        step_path.write_text("ISO-10303-21; END-ISO-10303-21;\n")
        glb_path = part_glb_path(step_path)
        glb_path.parent.mkdir(parents=True, exist_ok=True)
        glb_path.write_bytes(b"glb")
        self.render_paths.append(glb_path)

    def _write_assembly(self, name: str, *, instances: list[dict[str, object]]) -> None:
        (self.temp_root / f"{name}.py").write_text(
            "\n".join(
                [
                    "def gen_step():",
                    f"    return {{'instances': {instances!r}}}",
                    "",
                ]
            )
        )

    def test_flatten_source_path_resolves_python_assembly_parts(self) -> None:
        self._write_part("part-a")
        self._write_part("part-b")
        self._write_assembly(
            "root-assembly",
            instances=[
                {
                    "path": "part-a.step",
                    "name": "left-leaf",
                    "transform": _translation(1.0, 2.0, 3.0),
                },
                {
                    "path": "part-b.step",
                    "name": "right-leaf",
                    "transform": _translation(0.0, 5.0, 0.0),
                },
            ],
        )

        resolved = assembly_flatten.flatten_source_path(self.temp_root / "root-assembly.py")

        self.assertEqual(2, len(resolved))
        self.assertEqual(
            [
                ("left-leaf",),
                ("right-leaf",),
            ],
            [part.instance_path for part in resolved],
        )
        self.assertEqual(
            [
                self._cad_ref("part-a"),
                self._cad_ref("part-b"),
            ],
            [part.cad_ref for part in resolved],
        )
        self.assertEqual("left-leaf", resolved[0].name)
        self.assertEqual("right-leaf", resolved[1].name)
        self.assertEqual(
            tuple(_translation(1.0, 2.0, 3.0)),
            resolved[0].transform,
        )
        self.assertEqual(
            tuple(_translation(0.0, 5.0, 0.0)),
            resolved[1].transform,
        )

    def test_flatten_source_path_resolves_paths_relative_to_assembly_source(self) -> None:
        step_dir = self.temp_root / "parts"
        step_dir.mkdir(parents=True)
        step_path = step_dir / "part.step"
        step_path.write_text("ISO-10303-21; END-ISO-10303-21;\n")
        glb_path = part_glb_path(step_path)
        glb_path.parent.mkdir(parents=True, exist_ok=True)
        glb_path.write_bytes(b"glb")
        self.render_paths.append(glb_path)

        (step_dir / "sample_assembly.py").write_text(
            "\n".join(
                [
                    "def gen_step():",
                    "    return {'instances': [",
                    "        {'path': 'part.step', 'name': 'leaf', 'transform': "
                    f"{IDENTITY_TRANSFORM!r}}}",
                    "    ]}",
                    "",
                ]
            ),
            encoding="utf-8",
        )

        resolved = assembly_flatten.flatten_source_path(step_dir / "sample_assembly.py")

        self.assertEqual(1, len(resolved))
        self.assertEqual(f"{self.relative_dir}/parts/part", resolved[0].cad_ref)
        self.assertEqual(step_path.resolve(), resolved[0].step_path.resolve())
        self.assertEqual(part_glb_path(step_path).resolve(), resolved[0].glb_path.resolve())

    def test_flatten_source_path_rejects_duplicate_instance_names(self) -> None:
        self._write_part("part")
        self._write_assembly(
            "assembly",
            instances=[
                {
                    "path": "part.step",
                    "name": "duplicate",
                    "transform": IDENTITY_TRANSFORM,
                },
                {
                    "path": "part.step",
                    "name": "duplicate",
                    "transform": IDENTITY_TRANSFORM,
                },
            ],
        )

        with self.assertRaisesRegex(assembly_flatten.AssemblyResolutionError, "duplicates"):
            assembly_flatten.flatten_source_path(self.temp_root / "assembly.py")


if __name__ == "__main__":
    unittest.main()
