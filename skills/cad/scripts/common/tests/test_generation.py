import hashlib
import shutil
import unittest
from pathlib import Path
from unittest import mock

from common import generation as cad_generation
from common import render as cad_render
from common import catalog as cad_catalog
from common import source_hash as cad_source_hash
from common.assembly_spec import (
    AssemblyInstanceSpec,
    AssemblyNodeSpec,
    AssemblySpec,
)
from common.catalog import StepImportOptions
from common.glb_topology import STEP_TOPOLOGY_SCHEMA_VERSION
from common.step_scene import LoadedStepScene, OccurrenceNode, SelectorBundle
from common.step_metadata import TEXT_TO_CAD_GENERATOR, read_text_to_cad_step_metadata
from common.tests.cad_test_roots import IsolatedCadRoots


IDENTITY_TRANSFORM = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]


def _summary_manifest(cad_ref: str) -> dict[str, object]:
    return {
        "schemaVersion": STEP_TOPOLOGY_SCHEMA_VERSION,
        "profile": "summary",
        "cadPath": cad_ref,
        "stepPath": f"{cad_ref}.step",
        "stepHash": "step-hash-123",
        "bbox": {"min": [0.0, 0.0, 0.0], "max": [1.0, 1.0, 1.0]},
        "stats": {
            "occurrenceCount": 1,
            "leafOccurrenceCount": 1,
            "shapeCount": 1,
            "faceCount": 6,
            "edgeCount": 12,
        },
        "tables": {
            "occurrenceColumns": [
                "id",
                "path",
                "name",
                "sourceName",
                "parentId",
                "transform",
                "bbox",
                "shapeStart",
                "shapeCount",
                "faceStart",
                "faceCount",
                "edgeStart",
                "edgeCount",
            ],
            "shapeColumns": [],
            "faceColumns": [],
            "edgeColumns": [],
        },
        "occurrences": [
            [
                "o1",
                "1",
                "Part",
                "Part",
                None,
                IDENTITY_TRANSFORM,
                {"min": [0.0, 0.0, 0.0], "max": [1.0, 1.0, 1.0]},
                0,
                1,
                0,
                6,
                0,
                12,
            ]
        ],
        "shapes": [],
        "faces": [],
        "edges": [],
    }


class CadGenerationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._isolated_roots = IsolatedCadRoots(self, prefix="cad-generation-")
        tempdir = self._isolated_roots.temporary_cad_directory(prefix="tmp-cad-")
        self._tempdir = tempdir
        self.temp_root = Path(tempdir.name)
        self.relative_dir = self.temp_root.relative_to(cad_generation.CAD_ROOT).as_posix()

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_root, ignore_errors=True)
        self._tempdir.cleanup()

    def _cad_ref(self, name: str) -> str:
        return f"{self.relative_dir}/{name}"

    def _write_step_at(
        self,
        directory: Path,
        name: str,
        *,
        suffix: str = ".step",
    ) -> Path:
        step_path = directory / f"{name}{suffix}"
        step_path.write_text("ISO-10303-21; END-ISO-10303-21;\n", encoding="utf-8")
        return step_path

    def _step_options(
        self,
        *,
        stl: str | None = None,
        three_mf: str | None = None,
        glb: str | None = None,
        mesh_tolerance: float | None = None,
        mesh_angular_tolerance: float | None = None,
    ) -> StepImportOptions:
        return StepImportOptions(
            stl=stl,
            three_mf=three_mf,
            glb=glb,
            mesh_tolerance=mesh_tolerance,
            mesh_angular_tolerance=mesh_angular_tolerance,
        )

    def _write_step(
        self,
        name: str,
        *,
        suffix: str = ".step",
    ) -> Path:
        return self._write_step_at(self.temp_root, name, suffix=suffix)

    def test_catalog_discovery_ignores_urdf_only_generators(self) -> None:
        self._write_step("sample")
        (self._isolated_roots.cad_root / "sample_urdf.py").write_text(
            "def gen_urdf():\n"
            "    return {'xml': '<robot name=\"sample\" />', 'urdf_output': 'sample.urdf'}\n",
            encoding="utf-8",
        )
        (self._isolated_roots.cad_root / "sample_sdf.py").write_text(
            "def gen_sdf():\n"
            "    return {'xml': '<sdf version=\"1.12\"><model name=\"sample\" /></sdf>', 'sdf_output': 'sample.sdf'}\n",
            encoding="utf-8",
        )

        sources = cad_catalog.iter_cad_sources()

        self.assertIn(self._cad_ref("sample"), {source.cad_ref for source in sources})
        self.assertNotIn("sample_urdf", {source.cad_ref for source in sources})
        self.assertNotIn("sample_sdf", {source.cad_ref for source in sources})

    def _generator_script(
        self,
        name: str,
        *,
        with_dxf: bool = False,
        with_urdf: bool = False,
        with_sdf: bool = False,
        dxf_before_step: bool = False,
        step_output: str | None = None,
        stl: str | None = None,
        three_mf: str | None = None,
        dxf_output: str | None = None,
        urdf_output: str | None = None,
        sdf_output: str | None = None,
        mesh_tolerance: float | None = None,
        mesh_angular_tolerance: float | None = None,
    ) -> Path:
        fields: list[str] = ["'shape': _shape()"]
        fields.append(f"'step_output': {(step_output or f'{name}.step')!r}")
        if stl is not None:
            fields.append(f"'stl': {stl!r}")
        if three_mf is not None:
            fields.append(f"'3mf': {three_mf!r}")
        if mesh_tolerance is not None:
            fields.append(f"'mesh_tolerance': {mesh_tolerance!r}")
        if mesh_angular_tolerance is not None:
            fields.append(f"'mesh_angular_tolerance': {mesh_angular_tolerance!r}")
        if with_dxf and dxf_output is None:
            dxf_output = f"{name}.dxf"
        if with_urdf and urdf_output is None:
            urdf_output = f"{name}.urdf"
        if with_sdf and sdf_output is None:
            sdf_output = f"{name}.sdf"

        prologue = [
            "from pathlib import Path",
            f'DISPLAY_NAME = "{name}"',
            "CALLS = Path(__file__).with_suffix('.calls')",
            "def _output_path(suffix, output):",
            "    path = Path(__file__).parent / output if output else Path(__file__).with_suffix(suffix)",
            "    path.parent.mkdir(parents=True, exist_ok=True)",
            "    return path",
            "def _record(name):",
            "    with CALLS.open('a', encoding='utf-8') as handle:",
            "        handle.write(name + '\\n')",
            "class _FakeDxf:",
            "    def saveas(self, output_path):",
            "        Path(output_path).write_text('0\\nEOF\\n', encoding='utf-8')",
            "def _shape():",
            "    import build123d",
            "    return build123d.Box(1, 1, 1)",
            "",
        ]
        step_block = [
            "def gen_step():",
            "    _record('gen_step')",
            "    return {",
            *[f"        {field}," for field in fields],
            "    }",
            "",
        ]
        dxf_block = [
            "def gen_dxf():",
            "    _record('gen_dxf')",
            "    return {",
            "        'document': _FakeDxf(),",
            f"        'dxf_output': {dxf_output!r},",
            "    }",
            "",
        ]
        urdf_block = [
            "def gen_urdf():",
            "    _record('gen_urdf')",
            "    return {",
            "        'xml': '<robot name=\"part\"><link name=\"base\" /></robot>',",
            f"        'urdf_output': {urdf_output!r},",
            "    }",
            "",
        ]
        sdf_block = [
            "def gen_sdf():",
            "    _record('gen_sdf')",
            "    return {",
            "        'xml': '<sdf version=\"1.12\"><model name=\"part\"><link name=\"base\" /></model></sdf>',",
            f"        'sdf_output': {sdf_output!r},",
            "    }",
            "",
        ]

        blocks = [prologue]
        if with_dxf and dxf_before_step:
            blocks.append(dxf_block)
        blocks.append(step_block)
        if with_dxf and not dxf_before_step:
            blocks.append(dxf_block)
        if with_urdf:
            blocks.append(urdf_block)
        if with_sdf:
            blocks.append(sdf_block)

        script_path = self.temp_root / f"{name}.py"
        script_path.write_text("\n".join(line for block in blocks for line in block), encoding="utf-8")
        return script_path

    def _write_assembly_generator(
        self,
        name: str,
        *,
        instances: list[dict[str, object]],
        with_dxf: bool = False,
        with_urdf: bool = False,
        with_sdf: bool = False,
        step_output: str | None = None,
        stl: str | None = None,
        three_mf: str | None = None,
        dxf_output: str | None = None,
        urdf_output: str | None = None,
        sdf_output: str | None = None,
        mesh_tolerance: float | None = None,
        mesh_angular_tolerance: float | None = None,
    ) -> Path:
        fields: list[str] = [f"'instances': {instances!r}"]
        fields.append(f"'step_output': {(step_output or f'{name}.step')!r}")
        if stl is not None:
            fields.append(f"'stl': {stl!r}")
        if three_mf is not None:
            fields.append(f"'3mf': {three_mf!r}")
        if mesh_tolerance is not None:
            fields.append(f"'mesh_tolerance': {mesh_tolerance!r}")
        if mesh_angular_tolerance is not None:
            fields.append(f"'mesh_angular_tolerance': {mesh_angular_tolerance!r}")
        if with_dxf and dxf_output is None:
            dxf_output = f"{name}.dxf"
        if with_urdf and urdf_output is None:
            urdf_output = f"{name}.urdf"
        if with_sdf and sdf_output is None:
            sdf_output = f"{name}.sdf"

        lines = [
            "from pathlib import Path",
            "CALLS = Path(__file__).with_suffix('.calls')",
            "def _output_path(suffix, output):",
            "    path = Path(__file__).parent / output if output else Path(__file__).with_suffix(suffix)",
            "    path.parent.mkdir(parents=True, exist_ok=True)",
            "    return path",
            "def _record(name):",
            "    with CALLS.open('a', encoding='utf-8') as handle:",
            "        handle.write(name + '\\n')",
            "class _FakeDxf:",
            "    def saveas(self, output_path):",
            "        Path(output_path).write_text('0\\nEOF\\n', encoding='utf-8')",
            "",
            "def gen_step():",
            "    _record('gen_step')",
            "    return {",
            *[f"        {field}," for field in fields],
            "    }",
            "",
        ]
        if with_dxf:
            lines.extend(
                [
                    "def gen_dxf():",
                    "    _record('gen_dxf')",
                    "    return {",
                    "        'document': _FakeDxf(),",
                    f"        'dxf_output': {dxf_output!r},",
                    "    }",
                    "",
                ]
            )
        if with_urdf:
            lines.extend(
                [
                    "def gen_urdf():",
                    "    _record('gen_urdf')",
                    "    return {",
                    "        'xml': '<robot name=\"sample\"><link name=\"base\" /></robot>',",
                    f"        'urdf_output': {urdf_output!r},",
                    "    }",
                    "",
                ]
            )
        if with_sdf:
            lines.extend(
                [
                    "def gen_sdf():",
                    "    _record('gen_sdf')",
                    "    return {",
                    "        'xml': '<sdf version=\"1.12\"><model name=\"sample\"><link name=\"base\" /></model></sdf>',",
                    f"        'sdf_output': {sdf_output!r},",
                    "    }",
                    "",
                ]
            )
        assembly_path = self.temp_root / f"{name}.py"
        assembly_path.write_text("\n".join(lines), encoding="utf-8")
        return assembly_path

    def test_generated_part_discovery_includes_missing_step_output(self) -> None:
        script_path = self._generator_script("flat")

        specs = [spec for spec in cad_generation.list_entry_specs() if spec.cad_ref == self._cad_ref("flat")]

        self.assertEqual(1, len(specs))
        self.assertEqual("part", specs[0].kind)
        self.assertEqual(script_path, specs[0].source_path)
        self.assertFalse(specs[0].step_path.exists())

    def test_generated_part_discovery_ignores_virtualenv_python(self) -> None:
        self._generator_script("flat")
        dependency_dir = self.temp_root / ".venv" / "lib" / "python3.13" / "site-packages"
        dependency_dir.mkdir(parents=True)
        (dependency_dir / "dependency.py").write_bytes(b"\xe9")

        specs = [spec for spec in cad_generation.list_entry_specs() if spec.cad_ref == self._cad_ref("flat")]

        self.assertEqual(1, len(specs))

    def test_generated_part_discovery_ignores_non_generator_decode_failures(self) -> None:
        self._generator_script("flat")
        (self.temp_root / "notes.py").write_bytes(b"\xe9")

        specs = [spec for spec in cad_generation.list_entry_specs() if spec.cad_ref == self._cad_ref("flat")]

        self.assertEqual(1, len(specs))

    def test_python_source_hash_includes_local_imports(self) -> None:
        script_path = self.temp_root / "uses_helper.py"
        helper_path = self.temp_root / "helper.py"
        helper_path.write_text("SIZE = 1\n", encoding="utf-8")
        script_path.write_text(
            "\n".join(
                [
                    "from helper import SIZE",
                    "def gen_step():",
                    "    import build123d",
                    "    return build123d.Box(SIZE, 1, 1)",
                    "",
                ]
            ),
            encoding="utf-8",
        )

        before = cad_generation.python_source_hash(script_path)
        helper_path.write_text("SIZE = 2\n", encoding="utf-8")
        after = cad_generation.python_source_hash(script_path)

        source_paths = {entry.path for entry in before.files}
        self.assertIn(script_path.relative_to(cad_generation.CAD_ROOT).as_posix(), source_paths)
        self.assertIn(helper_path.relative_to(cad_generation.CAD_ROOT).as_posix(), source_paths)
        self.assertNotEqual(before.digest, after.digest)

    def test_python_source_hash_keeps_dynamic_dependency_files_out_of_manifest_payloads(self) -> None:
        script_path = cad_source_hash._PACKAGE_REPO_ROOT / "models/simple/square_mounting_block.py"
        if not script_path.is_file():
            self.skipTest(f"fixture missing: {script_path}")
        identity = cad_source_hash.python_source_hash(script_path)

        self.assertTrue(identity.files)
        self.assertFalse(hasattr(identity, "manifest_files"))

    def test_generated_step_output_is_not_discovered_as_imported_step(self) -> None:
        self._generator_script("flat")
        (self.temp_root / "flat.step").write_text("ISO-10303-21; END-ISO-10303-21;\n", encoding="utf-8")

        specs = [spec for spec in cad_generation.list_entry_specs() if spec.cad_ref == self._cad_ref("flat")]

        self.assertEqual(1, len(specs))
        self.assertEqual("generated", specs[0].source)

    def test_generated_source_defaults_step_output_to_sibling_stem(self) -> None:
        script_path = self.temp_root / "missing_output.py"
        script_path.write_text(
            "\n".join(
                [
                    "def gen_step():",
                    "    return {'shape': object()}",
                    "",
                ]
            ),
            encoding="utf-8",
        )

        spec = next(spec for spec in cad_generation.list_entry_specs() if spec.source_path == script_path)

        self.assertEqual(script_path.with_suffix(".step"), spec.step_path)
        self.assertEqual(self._cad_ref("missing_output"), spec.cad_ref)

    def test_generated_part_ignores_legacy_output_and_sidecar_metadata(self) -> None:
        script_path = self._generator_script(
            "flat",
            with_dxf=True,
            with_sdf=True,
            step_output="custom/renamed.step",
            stl="../meshes/renamed.stl",
            three_mf="../meshes/renamed.3mf",
            dxf_output="../drawings/renamed.dxf",
            sdf_output="robot/flat.sdf",
        )

        spec = next(spec for spec in cad_generation.list_entry_specs() if spec.source_path == script_path)

        self.assertEqual(self._cad_ref("flat"), spec.cad_ref)
        self.assertEqual(self.temp_root / "flat.step", spec.step_path)
        self.assertEqual(self.temp_root / "flat.dxf", spec.dxf_path)
        self.assertEqual(self.temp_root / "flat.sdf", spec.sdf_path)
        self.assertIsNone(spec.stl_path)
        self.assertIsNone(spec.three_mf_path)

    def test_generated_sdf_legacy_output_collision_is_ignored(self) -> None:
        self._generator_script("first", with_sdf=True, sdf_output="shared/robot.sdf")
        self._generator_script("second", with_sdf=True, sdf_output="shared/robot.sdf")

        specs = {
            spec.cad_ref: spec
            for spec in cad_generation.list_entry_specs()
            if spec.cad_ref.startswith(f"{self.relative_dir}/")
        }

        self.assertEqual(self.temp_root / "first.sdf", specs[self._cad_ref("first")].sdf_path)
        self.assertEqual(self.temp_root / "second.sdf", specs[self._cad_ref("second")].sdf_path)

    def test_generated_source_ignores_legacy_parent_output(self) -> None:
        self._generator_script("flat", step_output="../../../flat.step")

        spec = next(spec for spec in cad_generation.list_entry_specs() if spec.source_path == self.temp_root / "flat.py")

        self.assertEqual(self.temp_root / "flat.step", spec.step_path)

    def test_generated_source_ignores_invalid_legacy_output_suffix(self) -> None:
        self._generator_script("flat", step_output="flat.stp")

        spec = next(spec for spec in cad_generation.list_entry_specs() if spec.source_path == self.temp_root / "flat.py")

        self.assertEqual(self.temp_root / "flat.step", spec.step_path)

    def test_generated_dxf_defaults_output_to_sibling_stem(self) -> None:
        script_path = self.temp_root / "flat.py"
        script_path.write_text(
            "\n".join(
                [
                    "def gen_step():",
                    "    return {'shape': object(), 'step_output': 'flat.step'}",
                    "",
                    "def gen_dxf():",
                    "    return {'document': object()}",
                    "",
                ]
            ),
            encoding="utf-8",
        )

        spec = next(spec for spec in cad_generation.list_entry_specs() if spec.source_path == script_path)

        self.assertEqual(script_path.with_suffix(".dxf"), spec.dxf_path)

    def test_generated_urdf_and_sdf_direct_returns_default_to_sibling_stems(self) -> None:
        script_path = self.temp_root / "robot.py"
        script_path.write_text(
            "\n".join(
                [
                    "def gen_step():",
                    "    return {'shape': object()}",
                    "",
                    "def gen_urdf():",
                    "    return '<robot name=\"sample\" />'",
                    "",
                    "def gen_sdf():",
                    "    return '<sdf version=\"1.12\"><model name=\"sample\" /></sdf>'",
                    "",
                ]
            ),
            encoding="utf-8",
        )

        spec = next(spec for spec in cad_generation.list_entry_specs() if spec.source_path == script_path)

        self.assertEqual(script_path.with_suffix(".urdf"), spec.urdf_path)
        self.assertEqual(script_path.with_suffix(".sdf"), spec.sdf_path)

    def test_bare_shape_return_is_supported_for_step_generation(self) -> None:
        script_path = self.temp_root / "bare_part.py"
        script_path.write_text(
            "\n".join(
                [
                    "def gen_step():",
                    "    import build123d",
                    "    return build123d.Box(1, 1, 1)",
                    "",
                ]
            ),
            encoding="utf-8",
        )

        spec = next(spec for spec in cad_generation.list_entry_specs() if spec.source_path == script_path)
        scene = cad_generation.run_script_generator(spec, "gen_step")

        self.assertEqual("part", spec.kind)
        self.assertTrue(script_path.with_suffix(".step").exists())
        metadata = read_text_to_cad_step_metadata(script_path.with_suffix(".step"))
        self.assertEqual(TEXT_TO_CAD_GENERATOR, metadata.get("generator"))
        self.assertEqual("part", metadata.get("entryKind"))
        self.assertEqual(cad_generation.python_source_hash(script_path).digest, metadata.get("sourceHash"))
        self.assertIsNotNone(scene)
        self.assertEqual("python", scene.source_kind)
        self.assertEqual(cad_generation.python_source_hash(script_path).digest, scene.source_hash)

    def test_bare_assembly_children_return_is_supported(self) -> None:
        self._write_step("leaf")
        script_path = self.temp_root / "bare_assembly.py"
        script_path.write_text(
            "\n".join(
                [
                    f"IDENTITY = {IDENTITY_TRANSFORM!r}",
                    "def gen_step():",
                    "    return [{'path': 'leaf.step', 'name': 'leaf', 'transform': IDENTITY}]",
                    "",
                ]
            ),
            encoding="utf-8",
        )

        spec = next(spec for spec in cad_generation.list_entry_specs() if spec.source_path == script_path)
        assembly_spec = cad_generation.read_assembly_spec(script_path)

        self.assertEqual("assembly", spec.kind)
        self.assertEqual(1, len(assembly_spec.children))
        self.assertEqual("leaf", assembly_spec.children[0].name)

    def test_bare_dxf_document_return_is_supported(self) -> None:
        script_path = self.temp_root / "bare_dxf.py"
        script_path.write_text(
            "\n".join(
                [
                    "from pathlib import Path",
                    "class _FakeDxf:",
                    "    def saveas(self, output_path):",
                    "        Path(output_path).write_text('0\\nEOF\\n', encoding='utf-8')",
                    "def gen_step():",
                    "    import build123d",
                    "    return build123d.Box(1, 1, 1)",
                    "def gen_dxf():",
                    "    return _FakeDxf()",
                    "",
                ]
            ),
            encoding="utf-8",
        )

        cad_generation.generate_dxf_targets([str(script_path)])

        self.assertTrue(script_path.with_suffix(".dxf").exists())

    def test_generator_stl_sidecar_paths_are_ignored_by_catalog(self) -> None:
        self._generator_script("left", stl="shared.stl")
        self._generator_script("right", stl="shared.stl")

        specs = {
            spec.cad_ref: spec
            for spec in cad_generation.list_entry_specs()
            if spec.cad_ref.startswith(f"{self.relative_dir}/")
        }

        self.assertIsNone(specs[self._cad_ref("left")].stl_path)
        self.assertIsNone(specs[self._cad_ref("right")].stl_path)

    def test_generator_3mf_sidecar_paths_are_ignored_by_catalog(self) -> None:
        self._generator_script("left", three_mf="shared.3mf")
        self._generator_script("right", three_mf="shared.3mf")

        specs = {
            spec.cad_ref: spec
            for spec in cad_generation.list_entry_specs()
            if spec.cad_ref.startswith(f"{self.relative_dir}/")
        }

        self.assertIsNone(specs[self._cad_ref("left")].three_mf_path)
        self.assertIsNone(specs[self._cad_ref("right")].three_mf_path)

    def test_direct_step_is_discovered_as_imported_part(self) -> None:
        self._write_step("loose")

        specs = [spec for spec in cad_generation.list_entry_specs() if spec.cad_ref == self._cad_ref("loose")]

        self.assertEqual(1, len(specs))
        self.assertEqual("part", specs[0].kind)
        self.assertEqual(self.temp_root / "loose.step", specs[0].step_path)

    def test_list_entry_specs_can_use_custom_root(self) -> None:
        scoped_root = self.temp_root / "scoped"
        scoped_root.mkdir()
        self._write_step_at(scoped_root, "only")
        self._write_step("outside")

        specs = cad_generation.list_entry_specs(scoped_root)

        self.assertEqual([f"{self.relative_dir}/scoped/only"], [spec.cad_ref for spec in specs])

    def test_selection_requires_explicit_targets(self) -> None:
        scoped_root = self.temp_root / "scoped"
        scoped_root.mkdir()
        self._write_step_at(scoped_root, "leaf")
        self._write_assembly_generator(
            "dependent-assembly",
            instances=[
                {
                    "path": "scoped/leaf.step",
                    "name": "leaf",
                    "transform": IDENTITY_TRANSFORM,
                }
            ],
        )
        all_specs = [
            spec
            for spec in cad_generation.list_entry_specs()
            if spec.cad_ref.startswith(f"{self.relative_dir}/")
        ]

        with self.assertRaisesRegex(ValueError, "At least one CAD target is required"):
            cad_generation.selected_entry_specs(all_specs, [])

    def test_entry_selection_is_exact_and_ordered(self) -> None:
        self._write_step("first")
        self._write_step("second")
        specs = [
            spec
            for spec in cad_generation.list_entry_specs()
            if spec.cad_ref.startswith(f"{self.relative_dir}/")
        ]

        selected = cad_generation.selected_entry_specs(
            specs,
            [self._cad_ref("second"), self._cad_ref("first"), self._cad_ref("second")],
        )

        self.assertEqual(
            [self._cad_ref("second"), self._cad_ref("first"), self._cad_ref("second")],
            [spec.cad_ref for spec in selected],
        )

    def test_direct_step_generation_regenerates_selected_entries_in_supplied_order(self) -> None:
        first_path = self._write_step("first")
        second_path = self._write_step("second")
        calls: list[str] = []

        def fake_generate(spec, *, entries_by_step_path):
            self.assertIn(spec.step_path.resolve(), entries_by_step_path)
            calls.append(spec.cad_ref)

        with mock.patch.object(cad_generation, "_generate_step_outputs", side_effect=fake_generate):
            cad_generation.generate_step_targets(
                [str(second_path), str(first_path)],
                direct_step_kind="part",
            )

        self.assertEqual([self._cad_ref("second"), self._cad_ref("first")], calls)

    def test_step_generation_passes_skip_step_write_flag(self) -> None:
        script_path = self._generator_script("fast")
        calls: list[bool] = []

        def fake_generate(spec, *, entries_by_step_path, skip_step_write=False):
            self.assertIn(spec.step_path.resolve(), entries_by_step_path)
            calls.append(skip_step_write)

        with mock.patch.object(cad_generation, "_generate_step_outputs", side_effect=fake_generate):
            cad_generation.generate_step_targets(
                [str(script_path)],
                skip_step_write=True,
            )

        self.assertEqual([True], calls)

    def test_step_generation_rejects_skip_step_write_for_direct_step_target(self) -> None:
        step_path = self._write_step("direct")

        with self.assertRaisesRegex(ValueError, "--skip-step-write is valid only for Python gen_step"):
            cad_generation.generate_step_targets(
                [str(step_path)],
                direct_step_kind="part",
                skip_step_write=True,
            )

    def test_step_generation_rejects_skip_step_write_with_output_override(self) -> None:
        script_path = self._generator_script("artifact-only")

        with self.assertRaisesRegex(ValueError, "--skip-step-write cannot be combined with STEP output overrides"):
            cad_generation.generate_step_targets(
                [str(script_path)],
                output=str(self.temp_root / "artifact-only.step"),
                skip_step_write=True,
            )

    def test_step_generation_skip_step_write_allows_missing_logical_step(self) -> None:
        script_path = self._generator_script("artifact_only")
        logical_step_path = script_path.with_suffix(".step")
        self.assertFalse(logical_step_path.exists())
        calls: list[dict[str, object]] = []
        scene = mock.Mock()
        scene.step_path = logical_step_path.resolve()

        def fake_outputs(spec, **kwargs):
            calls.append(kwargs)
            return cad_generation.GeneratedStepResult(spec=spec, scene=scene)

        with mock.patch.object(cad_generation, "run_script_generator", return_value=scene) as run_generator, mock.patch.object(
            cad_generation,
            "_generate_part_outputs",
            side_effect=fake_outputs,
        ):
            cad_generation.generate_step_targets(
                [str(script_path)],
                skip_step_write=True,
            )

        run_generator.assert_called_once()
        self.assertEqual(False, calls[0]["require_step_file"])
        self.assertIs(scene, calls[0]["preloaded_scene"])
        self.assertFalse(calls[0]["force"])

    def test_generated_step_targets_expect_python_backed_topology_artifacts(self) -> None:
        script_path = self._generator_script("generated_kind")
        generated_spec = next(spec for spec in cad_generation.list_entry_specs() if spec.source_path == script_path)
        direct_path = self._write_step("direct_kind")
        _, direct_specs = cad_generation._selected_specs_for_targets(
            [str(direct_path)],
            direct_step_kind="part",
        )

        self.assertTrue(
            cad_generation._artifact_source_kind_matches_spec(
                generated_spec,
                {"sourceKind": "python"},
            )
        )
        self.assertFalse(
            cad_generation._artifact_source_kind_matches_spec(
                generated_spec,
                {"sourceKind": "step"},
            )
        )
        self.assertTrue(
            cad_generation._artifact_source_kind_matches_spec(
                direct_specs[0],
                {"sourceKind": "step"},
            )
        )
        self.assertFalse(
            cad_generation._artifact_source_kind_matches_spec(
                direct_specs[0],
                {"sourceKind": "python"},
            )
        )

    def test_step_output_override_retargets_single_generated_source(self) -> None:
        script_path = self._generator_script("flat")
        output_path = self.temp_root / "custom" / "flat-output.step"
        calls: list[cad_generation.EntrySpec] = []

        def fake_generate(spec, *, entries_by_step_path, preloaded_scene=None, force=False):
            self.assertIn(output_path.resolve(), entries_by_step_path)
            self.assertIsNotNone(preloaded_scene)
            self.assertEqual(output_path.resolve(), preloaded_scene.step_path)
            calls.append(spec)

        with mock.patch.object(cad_generation, "_generate_part_outputs", side_effect=fake_generate):
            cad_generation.generate_step_targets([str(script_path)], output=str(output_path))

        self.assertEqual(1, len(calls))
        self.assertEqual(output_path, calls[0].step_path)
        self.assertEqual(f"{self.relative_dir}/custom/flat-output", calls[0].cad_ref)
        self.assertTrue(output_path.exists())
        self.assertFalse(script_path.with_suffix(".step").exists())

    def test_step_output_pairs_retarget_generated_sources(self) -> None:
        first_path = self._generator_script("first")
        second_path = self._generator_script("second")
        first_output = self.temp_root / "custom" / "first-output.step"
        second_output = self.temp_root / "custom" / "second-output.step"
        calls: list[cad_generation.EntrySpec] = []

        def fake_generate(spec, *, entries_by_step_path, preloaded_scene=None, force=False):
            self.assertIn(spec.step_path.resolve(), entries_by_step_path)
            self.assertIsNotNone(preloaded_scene)
            calls.append(spec)

        with mock.patch.object(cad_generation, "_generate_part_outputs", side_effect=fake_generate):
            cad_generation.generate_step_targets(
                [f"{first_path}={first_output}", f"{second_path}={second_output}"],
            )

        self.assertEqual([first_output, second_output], [call.step_path for call in calls])
        self.assertTrue(first_output.exists())
        self.assertTrue(second_output.exists())
        self.assertFalse(first_path.with_suffix(".step").exists())
        self.assertFalse(second_path.with_suffix(".step").exists())

    def test_step_output_pairs_allow_mixed_plain_and_paired_targets(self) -> None:
        first_path = self._generator_script("first")
        second_path = self._generator_script("second")
        second_output = self.temp_root / "custom" / "second-output.step"
        calls: list[cad_generation.EntrySpec] = []

        def fake_generate(spec, *, entries_by_step_path, preloaded_scene=None, force=False):
            calls.append(spec)

        with mock.patch.object(cad_generation, "_generate_part_outputs", side_effect=fake_generate):
            cad_generation.generate_step_targets([str(first_path), f"{second_path}={second_output}"])

        self.assertEqual([first_path.with_suffix(".step"), second_output], [call.step_path for call in calls])
        self.assertTrue(first_path.with_suffix(".step").exists())
        self.assertTrue(second_output.exists())
        self.assertFalse(second_path.with_suffix(".step").exists())

    def test_step_output_override_rejects_pair_targets(self) -> None:
        script_path = self._generator_script("flat")

        with self.assertRaisesRegex(ValueError, "cannot be combined"):
            cad_generation.generate_step_targets(
                [f"{script_path}={self.temp_root / 'custom' / 'flat-output.step'}"],
                output=str(self.temp_root / "other.step"),
            )

    def test_step_output_override_requires_single_target(self) -> None:
        first_path = self._generator_script("first")
        second_path = self._generator_script("second")

        with self.assertRaisesRegex(ValueError, "--output can only be used with exactly one target"):
            cad_generation.generate_step_targets(
                [str(first_path), str(second_path)],
                output=str(self.temp_root / "first-output.step"),
            )

    def test_step_sidecar_flags_are_relative_to_output_override(self) -> None:
        script_path = self._generator_script("flat")
        output_path = self.temp_root / "custom" / "flat-output.step"
        calls: list[cad_generation.EntrySpec] = []

        def fake_generate(spec, *, entries_by_step_path, preloaded_scene=None, force=False):
            calls.append(spec)

        with mock.patch.object(cad_generation, "_generate_part_outputs", side_effect=fake_generate):
            cad_generation.generate_step_targets(
                [str(script_path)],
                output=str(output_path),
                step_options=self._step_options(
                    stl="flat-output.stl",
                    three_mf="flat-output.3mf",
                    glb="flat-output.glb",
                ),
            )

        self.assertEqual(1, len(calls))
        self.assertEqual(output_path.parent / "flat-output.stl", calls[0].stl_path)
        self.assertEqual(output_path.parent / "flat-output.3mf", calls[0].three_mf_path)
        self.assertEqual(output_path.parent / "flat-output.glb", calls[0].native_glb_path)

    def test_step_output_override_rejects_direct_step_target(self) -> None:
        step_path = self._write_step("imported")

        with self.assertRaisesRegex(ValueError, "--output can only be used with generated Python targets"):
            cad_generation.generate_step_targets(
                [str(step_path)],
                direct_step_kind="part",
                output=str(self.temp_root / "imported-output.step"),
            )

    def test_step_output_pair_rejects_direct_step_target(self) -> None:
        step_path = self._write_step("imported")

        with self.assertRaisesRegex(ValueError, "output pairs can only be used with generated Python targets"):
            cad_generation.generate_step_targets(
                [f"{step_path}={self.temp_root / 'imported-output.step'}"],
                direct_step_kind="part",
            )

    def test_step_output_pairs_reject_duplicate_output_paths(self) -> None:
        first_path = self._generator_script("first")
        second_path = self._generator_script("second")
        output_path = self.temp_root / "shared.step"

        with self.assertRaisesRegex(ValueError, "used more than once"):
            cad_generation.generate_step_targets([f"{first_path}={output_path}", f"{second_path}={output_path}"])

    def test_entry_selection_does_not_execute_unrelated_assembly_generators(self) -> None:
        selected_path = self._write_step("selected")
        assembly_path = self.temp_root / "unrelated.py"
        assembly_path.write_text(
            "\n".join(
                [
                    "def gen_step():",
                    "    raise RuntimeError('unrelated assembly should not run')",
                    "    return {'instances': [], 'step_output': 'unrelated.step'}",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        calls: list[str] = []

        def fake_generate(spec, *, entries_by_step_path):
            self.assertNotIn(assembly_path.with_suffix(".step").resolve(), entries_by_step_path)
            calls.append(spec.cad_ref)

        with mock.patch.object(cad_generation, "_generate_step_outputs", side_effect=fake_generate):
            cad_generation.generate_step_targets([str(selected_path)], direct_step_kind="part")

        self.assertEqual([self._cad_ref("selected")], calls)

    def test_step_generation_infers_assembly_target(self) -> None:
        self._write_step("imported-part")
        assembly_path = self._write_assembly_generator(
            "robot",
            instances=[
                {
                    "path": "imported-part.step",
                    "name": "leaf",
                    "transform": IDENTITY_TRANSFORM,
                }
            ],
        )
        calls: list[str] = []

        def fake_generate(spec, *, entries_by_step_path):
            calls.append(spec.kind)

        with mock.patch.object(cad_generation, "_generate_step_outputs", side_effect=fake_generate):
            cad_generation.generate_step_targets([str(assembly_path)])

        self.assertEqual(["assembly"], calls)

    def test_assembly_dependency_expansion_uses_one_source_lookup(self) -> None:
        child_step_paths: list[Path] = []
        instances: list[dict[str, object]] = []
        for index in range(6):
            child_script = self._generator_script(f"leaf_{index}")
            child_step = self._write_step(f"leaf_{index}")
            child_step_paths.append(child_step.resolve())
            instances.append(
                {
                    "path": child_step.name,
                    "name": f"leaf_{index}",
                    "transform": IDENTITY_TRANSFORM,
                }
            )
            self.assertEqual(child_script.with_suffix(".step"), child_step)

        assembly_path = self._write_assembly_generator("robot", instances=instances)
        iter_calls: list[Path | None] = []
        real_iter_cad_sources = cad_generation.iter_cad_sources

        def tracked_iter_cad_sources(root=None):
            iter_calls.append(root)
            return real_iter_cad_sources(root)

        def fake_generate(spec, *, entries_by_step_path):
            self.assertEqual("assembly", spec.kind)
            for child_step in child_step_paths:
                self.assertEqual("generated", entries_by_step_path[child_step].source)

        with (
            mock.patch.object(cad_generation, "iter_cad_sources", side_effect=tracked_iter_cad_sources),
            mock.patch.object(cad_generation, "find_source_by_path", side_effect=AssertionError("unexpected repeated source scan")),
            mock.patch.object(cad_generation, "_generate_step_outputs", side_effect=fake_generate),
        ):
            cad_generation.generate_step_targets([str(assembly_path)])

        self.assertEqual(1, len(iter_calls))

    def test_dxf_generation_rejects_source_without_dxf(self) -> None:
        script_path = self._generator_script("part")

        with self.assertRaisesRegex(ValueError, "does not define gen_dxf\\(\\)"):
            cad_generation.generate_dxf_targets([str(script_path)])

    def test_dxf_output_override_retargets_single_generated_source(self) -> None:
        script_path = self._generator_script("flat", with_dxf=True)
        output_path = self.temp_root / "drawings" / "flat-output.dxf"

        cad_generation.generate_dxf_targets([str(script_path)], output=str(output_path))

        self.assertTrue(output_path.exists())
        self.assertFalse(script_path.with_suffix(".dxf").exists())

    def test_dxf_output_pair_retargets_generated_source(self) -> None:
        first_path = self._generator_script("first", with_dxf=True)
        second_path = self._generator_script("second", with_dxf=True)
        first_output = self.temp_root / "drawings" / "first-output.dxf"
        second_output = self.temp_root / "drawings" / "second-output.dxf"

        cad_generation.generate_dxf_targets([f"{first_path}={first_output}", f"{second_path}={second_output}"])

        self.assertTrue(first_output.exists())
        self.assertTrue(second_output.exists())
        self.assertFalse(first_path.with_suffix(".dxf").exists())
        self.assertFalse(second_path.with_suffix(".dxf").exists())

    def test_dxf_output_pair_allows_mixed_plain_and_paired_targets(self) -> None:
        first_path = self._generator_script("first", with_dxf=True)
        second_path = self._generator_script("second", with_dxf=True)
        second_output = self.temp_root / "drawings" / "second-output.dxf"

        cad_generation.generate_dxf_targets([str(first_path), f"{second_path}={second_output}"])

        self.assertTrue(first_path.with_suffix(".dxf").exists())
        self.assertTrue(second_output.exists())
        self.assertFalse(second_path.with_suffix(".dxf").exists())

    def test_dxf_output_override_rejects_pair_targets(self) -> None:
        script_path = self._generator_script("flat", with_dxf=True)

        with self.assertRaisesRegex(ValueError, "cannot be combined"):
            cad_generation.generate_dxf_targets(
                [f"{script_path}={self.temp_root / 'drawings' / 'flat-output.dxf'}"],
                output=str(self.temp_root / "other.dxf"),
            )

    def test_dxf_output_pairs_reject_duplicate_output_paths(self) -> None:
        first_path = self._generator_script("first", with_dxf=True)
        second_path = self._generator_script("second", with_dxf=True)
        output_path = self.temp_root / "shared.dxf"

        with self.assertRaisesRegex(ValueError, "used more than once"):
            cad_generation.generate_dxf_targets([f"{first_path}={output_path}", f"{second_path}={output_path}"])

    def test_dxf_output_override_requires_single_target(self) -> None:
        first_path = self._generator_script("first", with_dxf=True)
        second_path = self._generator_script("second", with_dxf=True)

        with self.assertRaisesRegex(ValueError, "--output can only be used with exactly one target"):
            cad_generation.generate_dxf_targets(
                [str(first_path), str(second_path)],
                output=str(self.temp_root / "first-output.dxf"),
            )

    def test_step_generator_does_not_run_sidecars(self) -> None:
        script_path = self._generator_script("flat", with_dxf=True, with_urdf=True, with_sdf=True, dxf_before_step=True)
        spec = next(spec for spec in cad_generation.list_entry_specs() if spec.cad_ref == self._cad_ref("flat"))

        cad_generation.run_script_generator(spec, "gen_step")

        self.assertEqual("gen_step\n", script_path.with_suffix(".calls").read_text(encoding="utf-8"))
        self.assertFalse(script_path.with_suffix(".dxf").exists())
        self.assertTrue(script_path.with_suffix(".step").exists())
        self.assertFalse(script_path.with_suffix(".urdf").exists())
        self.assertFalse(script_path.with_suffix(".sdf").exists())

    def test_generated_step_outputs_reuses_generated_scene(self) -> None:
        script_path = self._generator_script("flat")
        spec = next(spec for spec in cad_generation.list_entry_specs() if spec.cad_ref == self._cad_ref("flat"))
        step_path = script_path.with_suffix(".step")
        observed_scene = None

        def fake_outputs(spec_arg, *, entries_by_step_path, preloaded_scene=None, force=False):
            nonlocal observed_scene
            observed_scene = preloaded_scene
            self.assertIs(spec, spec_arg)

        with mock.patch.object(cad_generation, "_generate_part_outputs", side_effect=fake_outputs):
            cad_generation._generate_step_outputs(spec, entries_by_step_path={spec.step_path.resolve(): spec})

        self.assertIsNotNone(observed_scene)
        self.assertEqual(step_path.resolve(), observed_scene.step_path)
        self.assertIsNotNone(observed_scene.doc)
        self.assertEqual("python", observed_scene.source_kind)
        self.assertEqual(cad_generation.python_source_hash(script_path).digest, observed_scene.source_hash)
        digest = hashlib.sha256(step_path.read_bytes()).hexdigest()
        self.assertEqual(digest, observed_scene.step_hash)

    def test_normal_python_generation_reuses_current_glb_after_skip_step_write(self) -> None:
        script_path = self._generator_script("flat")
        spec = next(spec for spec in cad_generation.list_entry_specs() if spec.cad_ref == self._cad_ref("flat"))
        step_path = script_path.with_suffix(".step")
        step_path.write_text("ISO-10303-21; END-ISO-10303-21;\n", encoding="utf-8")
        source_identity = cad_generation.python_source_hash(script_path)
        scene = LoadedStepScene(
            step_path=step_path.resolve(),
            roots=[],
            prototype_shapes={},
            source_kind="python",
            source_hash=source_identity.digest,
            source_path=cad_generation.relative_to_repo(script_path),
        )

        with (
            mock.patch.object(cad_generation, "_existing_topology_artifact_matches_options", return_value=True),
            mock.patch.object(
                cad_generation,
                "mesh_step_scene",
                side_effect=AssertionError("current Python-backed GLB should be reused"),
            ),
        ):
            result = cad_generation._generate_part_outputs(
                spec,
                entries_by_step_path={spec.step_path.resolve(): spec},
                preloaded_scene=scene,
                force=False,
            )

        self.assertIs(scene, result.scene)
        self.assertIsNone(result.selector_bundle)

    def test_skip_step_write_reuses_current_glb_without_running_generator(self) -> None:
        script_path = self._generator_script("flat")
        spec = next(spec for spec in cad_generation.list_entry_specs() if spec.cad_ref == self._cad_ref("flat"))
        artifact = mock.Mock()
        artifact.manifest = {
            "sourceKind": "python",
            "sourceHash": cad_generation.python_source_hash(script_path).digest,
            "edgeRendering": {
                "visibilityClasses": ["feature", "tangent", "seam", "degenerate"],
            },
            "mesh": {
                "linearDeflection": 0.006,
                "angularDeflection": 0.2,
                "relative": True,
                "resolution": {
                    "mode": "auto",
                    "hints": {
                        "bboxDiag": 10.0,
                        "prototypeFaceCount": 6,
                        "prototypeEdgeCount": 12,
                        "prototypeCurvedFaceCount": 0,
                        "prototypeCurvedEdgeCount": 0,
                        "occurrenceFaceCount": 6,
                        "occurrenceEdgeCount": 12,
                        "occurrenceCurvedFaceCount": 0,
                        "occurrenceCurvedEdgeCount": 0,
                        "leafOccurrenceCount": 1,
                        "complexityScore": 17.2,
                        "effectiveComplexityScore": 11.18,
                        "curvaturePressureScore": 0.0,
                        "profile": "extra-fine",
                    },
                },
            },
        }

        with (
            mock.patch(
                "common.step_targets.validate_step_topology_artifact",
                return_value=artifact,
            ),
            mock.patch.object(
                cad_generation,
                "run_script_generator",
                side_effect=AssertionError("current Python-backed GLB should be reused before gen_step"),
            ),
        ):
            result = cad_generation._generate_step_outputs(
                spec,
                entries_by_step_path={spec.step_path.resolve(): spec},
                skip_step_write=True,
                force=False,
            )

        self.assertIsNone(result.scene)
        self.assertIsNone(result.selector_bundle)
        self.assertEqual(script_path.with_suffix(".step"), result.spec.step_path)

    def test_skip_step_write_runs_generator_when_python_hash_is_stale(self) -> None:
        script_path = self._generator_script("flat")
        spec = next(spec for spec in cad_generation.list_entry_specs() if spec.cad_ref == self._cad_ref("flat"))
        scene = LoadedStepScene(
            step_path=spec.step_path.resolve(),
            roots=[],
            prototype_shapes={},
            source_kind="python",
            source_hash=cad_generation.python_source_hash(script_path).digest,
            source_path=cad_generation.relative_to_repo(script_path),
        )
        artifact = mock.Mock()
        artifact.manifest = {
            "sourceKind": "python",
            "sourceHash": "stale-python-source-hash",
            "edgeRendering": {
                "visibilityClasses": ["feature", "tangent", "seam", "degenerate"],
            },
            "mesh": {
                "linearDeflection": spec.mesh_tolerance,
                "angularDeflection": spec.mesh_angular_tolerance,
                "relative": True,
            },
        }

        with mock.patch(
            "common.step_targets.validate_step_topology_artifact",
            return_value=artifact,
        ), mock.patch.object(
            cad_generation,
            "run_script_generator",
            return_value=scene,
        ) as run_generator, mock.patch.object(
            cad_generation,
            "_generate_part_outputs",
            return_value=cad_generation.GeneratedStepResult(spec=spec, scene=scene),
        ) as generate_outputs:
            result = cad_generation._generate_step_outputs(
                spec,
                entries_by_step_path={spec.step_path.resolve(): spec},
                skip_step_write=True,
                force=False,
            )

        run_generator.assert_called_once()
        generate_outputs.assert_called_once()
        self.assertIs(scene, result.scene)

    def test_generated_assembly_step_reuses_current_fingerprint(self) -> None:
        child_step = self._write_step("leaf")
        instances = [
            {
                "path": child_step.name,
                "name": "leaf",
                "transform": IDENTITY_TRANSFORM,
            }
        ]
        script_path = self._write_assembly_generator("robot", instances=instances)
        output_path = script_path.with_suffix(".step")
        output_path.write_text("ISO-10303-21; END-ISO-10303-21;\n", encoding="utf-8")
        scene = LoadedStepScene(step_path=output_path.resolve(), roots=[], prototype_shapes={})

        with (
            mock.patch("common.assembly_export.assembly_source_fingerprint", return_value="fingerprint-123"),
            mock.patch.object(
                cad_generation,
                "read_text_to_cad_step_metadata",
                return_value={"entryKind": "assembly", "sourceFingerprint": "fingerprint-123"},
            ),
            mock.patch.object(cad_generation, "load_step_scene", return_value=scene) as load_scene,
            mock.patch(
                "common.assembly_export.export_assembly_step_scene",
                side_effect=AssertionError("fresh assembly STEP should not be exported"),
            ),
        ):
            result = cad_generation._write_assembly_step_payload(
                {"instances": instances},
                output_path=output_path,
                script_path=script_path,
                logger=cad_generation.CliLogger("test"),
            )

        self.assertIs(scene, result)
        self.assertEqual("python", result.source_kind)
        self.assertEqual(cad_generation.python_source_hash(script_path).digest, result.source_hash)
        load_scene.assert_called_once_with(output_path)

    def test_generated_assembly_step_exports_stale_fingerprint(self) -> None:
        child_step = self._write_step("leaf")
        instances = [
            {
                "path": child_step.name,
                "name": "leaf",
                "transform": IDENTITY_TRANSFORM,
            }
        ]
        script_path = self._write_assembly_generator("robot", instances=instances)
        output_path = script_path.with_suffix(".step")
        output_path.write_text("ISO-10303-21; END-ISO-10303-21;\n", encoding="utf-8")
        scene = LoadedStepScene(step_path=output_path.resolve(), roots=[], prototype_shapes={})

        with (
            mock.patch("common.assembly_export.assembly_source_fingerprint", return_value="fingerprint-123"),
            mock.patch.object(
                cad_generation,
                "read_text_to_cad_step_metadata",
                return_value={"entryKind": "assembly", "sourceFingerprint": "old-fingerprint"},
            ),
            mock.patch("common.assembly_export.export_assembly_step_scene", return_value=scene) as export_scene,
        ):
            result = cad_generation._write_assembly_step_payload(
                {"instances": instances},
                output_path=output_path,
                script_path=script_path,
                logger=cad_generation.CliLogger("test"),
            )

        self.assertIs(scene, result)
        self.assertEqual("python", result.source_kind)
        self.assertEqual(cad_generation.python_source_hash(script_path).digest, result.source_hash)
        export_scene.assert_called_once()
        self.assertEqual("fingerprint-123", export_scene.call_args.kwargs.get("source_fingerprint"))

    def test_generated_assembly_step_force_ignores_current_fingerprint(self) -> None:
        child_step = self._write_step("leaf")
        instances = [
            {
                "path": child_step.name,
                "name": "leaf",
                "transform": IDENTITY_TRANSFORM,
            }
        ]
        script_path = self._write_assembly_generator("robot", instances=instances)
        output_path = script_path.with_suffix(".step")
        output_path.write_text("ISO-10303-21; END-ISO-10303-21;\n", encoding="utf-8")
        scene = LoadedStepScene(step_path=output_path.resolve(), roots=[], prototype_shapes={})

        with (
            mock.patch("common.assembly_export.assembly_source_fingerprint", return_value="fingerprint-123"),
            mock.patch.object(
                cad_generation,
                "read_text_to_cad_step_metadata",
                return_value={"entryKind": "assembly", "sourceFingerprint": "fingerprint-123"},
            ) as read_metadata,
            mock.patch("common.assembly_export.export_assembly_step_scene", return_value=scene) as export_scene,
        ):
            result = cad_generation._write_assembly_step_payload(
                {"instances": instances},
                output_path=output_path,
                script_path=script_path,
                logger=cad_generation.CliLogger("test"),
                force=True,
            )

        self.assertIs(scene, result)
        read_metadata.assert_not_called()
        export_scene.assert_called_once()

    def test_sidecars_are_not_separate_generation_specs(self) -> None:
        self._generator_script("flat", with_dxf=True)
        self._write_step("imported-part")
        self._write_assembly_generator(
            "robot",
            instances=[
                {
                    "path": "imported-part.step",
                    "name": "leaf",
                    "transform": IDENTITY_TRANSFORM,
                }
            ],
            with_urdf=True,
            with_sdf=True,
        )

        cad_refs = {
            spec.cad_ref
            for spec in cad_generation.list_entry_specs()
            if spec.cad_ref.startswith(f"{self.relative_dir}/")
        }

        self.assertIn(self._cad_ref("flat"), cad_refs)
        self.assertIn(self._cad_ref("robot"), cad_refs)
        self.assertNotIn(self._cad_ref("flat") + ".dxf", cad_refs)
        self.assertNotIn(self._cad_ref("robot") + ".urdf", cad_refs)
        self.assertNotIn(self._cad_ref("robot") + ".sdf", cad_refs)

    def test_step_toml_target_is_not_supported(self) -> None:
        (self.temp_root / "broken.step.toml").write_text('kind = "part"\n', encoding="utf-8")

        with self.assertRaisesRegex(FileNotFoundError, "Python generator or STEP/STP file path"):
            cad_generation.generate_step_targets([str(self.temp_root / "broken.step.toml")])

    def test_direct_step_generation_requires_kind(self) -> None:
        step_path = self._write_step("source")

        with self.assertRaisesRegex(ValueError, "--kind is required for direct STEP/STP targets"):
            cad_generation.generate_step_targets([str(step_path)])

    def test_direct_step_generation_reads_configured_stl(self) -> None:
        step_path = self._write_step("source")
        calls: list[Path | None] = []

        def fake_generate(spec, *, entries_by_step_path):
            calls.append(spec.stl_path)

        with mock.patch.object(cad_generation, "_generate_step_outputs", side_effect=fake_generate):
            cad_generation.generate_step_targets(
                [str(step_path)],
                direct_step_kind="part",
                step_options=self._step_options(
                    stl="../meshes/source.stl",
                ),
            )

        self.assertEqual([cad_generation.CAD_ROOT / "meshes" / "source.stl"], calls)

    def test_direct_step_generation_reads_configured_3mf(self) -> None:
        step_path = self._write_step("source")
        calls: list[Path | None] = []

        def fake_generate(spec, *, entries_by_step_path):
            calls.append(spec.three_mf_path)

        with mock.patch.object(cad_generation, "_generate_step_outputs", side_effect=fake_generate):
            cad_generation.generate_step_targets(
                [str(step_path)],
                direct_step_kind="part",
                step_options=self._step_options(
                    three_mf="../meshes/source.3mf",
                ),
            )

        self.assertEqual([cad_generation.CAD_ROOT / "meshes" / "source.3mf"], calls)

    def test_direct_step_stl_flag_sets_stl_path(self) -> None:
        step_path = self._write_step("source")
        calls: list[cad_generation.EntrySpec] = []

        def fake_generate(spec, *, entries_by_step_path):
            calls.append(spec)

        with mock.patch.object(cad_generation, "_generate_step_outputs", side_effect=fake_generate):
            cad_generation.generate_step_targets(
                [str(step_path)],
                direct_step_kind="part",
                step_options=self._step_options(stl="source.stl"),
            )

        self.assertEqual(step_path.parent / "source.stl", calls[0].stl_path)

    def test_direct_step_3mf_flag_sets_3mf_path(self) -> None:
        step_path = self._write_step("source")
        calls: list[cad_generation.EntrySpec] = []

        def fake_generate(spec, *, entries_by_step_path):
            calls.append(spec)

        with mock.patch.object(cad_generation, "_generate_step_outputs", side_effect=fake_generate):
            cad_generation.generate_step_targets(
                [str(step_path)],
                direct_step_kind="part",
                step_options=self._step_options(three_mf="source.3mf"),
            )

        self.assertEqual(step_path.parent / "source.3mf", calls[0].three_mf_path)

    def test_direct_step_glb_flag_sets_native_glb_path(self) -> None:
        step_path = self._write_step("source")
        calls: list[cad_generation.EntrySpec] = []

        def fake_generate(spec, *, entries_by_step_path):
            calls.append(spec)

        with mock.patch.object(cad_generation, "_generate_step_outputs", side_effect=fake_generate):
            cad_generation.generate_step_targets(
                [str(step_path)],
                direct_step_kind="part",
                step_options=self._step_options(glb="source.glb"),
            )

        self.assertEqual(step_path.parent / "source.glb", calls[0].native_glb_path)

    def test_direct_step_rejects_invalid_stl_suffix(self) -> None:
        step_path = self._write_step("source")

        with self.assertRaisesRegex(ValueError, "stl must end in .stl"):
            cad_generation.generate_step_targets(
                [str(step_path)],
                direct_step_kind="part",
                step_options=self._step_options(stl="source.txt"),
            )

    def test_direct_step_rejects_invalid_3mf_suffix(self) -> None:
        step_path = self._write_step("source")

        with self.assertRaisesRegex(ValueError, "3mf must end in .3mf"):
            cad_generation.generate_step_targets(
                [str(step_path)],
                direct_step_kind="part",
                step_options=self._step_options(three_mf="source.txt"),
            )

    def test_direct_step_rejects_invalid_glb_suffix(self) -> None:
        step_path = self._write_step("source")

        with self.assertRaisesRegex(ValueError, "glb must end in .glb"):
            cad_generation.generate_step_targets(
                [str(step_path)],
                direct_step_kind="part",
                step_options=self._step_options(glb="source.txt"),
            )

    def test_direct_step_rejects_native_glb_topology_artifact_collision(self) -> None:
        step_path = self._write_step("source")

        with self.assertRaisesRegex(ValueError, "Native GLB output would overwrite"):
            cad_generation.generate_step_targets(
                [str(step_path)],
                direct_step_kind="part",
                step_options=self._step_options(glb=".source.step.glb"),
            )

    def test_direct_step_rejects_duplicate_native_glb_sidecars(self) -> None:
        first_path = self._write_step("first")
        second_path = self._write_step("second")

        with self.assertRaisesRegex(ValueError, "Native GLB output collision"):
            cad_generation.generate_step_targets(
                [str(first_path), str(second_path)],
                direct_step_kind="part",
                step_options=self._step_options(glb="../meshes/shared.glb"),
            )

    def test_direct_step_allows_file_relative_parent_stl(self) -> None:
        step_path = self._write_step("source")
        calls: list[Path | None] = []

        def fake_generate(spec, *, entries_by_step_path):
            calls.append(spec.stl_path)

        with mock.patch.object(cad_generation, "_generate_step_outputs", side_effect=fake_generate):
            cad_generation.generate_step_targets(
                [str(step_path)],
                direct_step_kind="part",
                step_options=self._step_options(
                    stl="../../../../source.stl",
                ),
            )

        self.assertEqual([(self.temp_root / "../../../../source.stl").resolve()], calls)

    def test_direct_step_reuses_mesh_numeric_validation(self) -> None:
        step_path = self._write_step("broken")

        with self.assertRaisesRegex(ValueError, "mesh_tolerance must be greater than 0"):
            cad_generation.generate_step_targets(
                [str(step_path)],
                direct_step_kind="part",
                step_options=self._step_options(mesh_tolerance=-0.1),
            )

    def test_step_cli_flags_apply_to_generated_python_targets(self) -> None:
        script_path = self._generator_script("generated")
        calls: list[cad_generation.EntrySpec] = []

        def fake_generate(spec, *, entries_by_step_path):
            calls.append(spec)

        with mock.patch.object(cad_generation, "_generate_step_outputs", side_effect=fake_generate):
            cad_generation.generate_step_targets(
                [str(script_path)],
                step_options=self._step_options(
                    stl="generated.stl",
                    three_mf="generated.3mf",
                    mesh_tolerance=0.2,
                    mesh_angular_tolerance=0.3,
                ),
            )

        self.assertEqual(1, len(calls))
        self.assertEqual(script_path.with_suffix(".stl"), calls[0].stl_path)
        self.assertEqual(script_path.with_suffix(".3mf"), calls[0].three_mf_path)
        self.assertEqual(0.2, calls[0].mesh_tolerance)
        self.assertEqual(0.3, calls[0].mesh_angular_tolerance)

    def test_step_cli_flags_apply_to_mixed_imported_and_generated_targets(self) -> None:
        step_path = self._write_step("imported")
        script_path = self._generator_script("generated")
        calls: list[cad_generation.EntrySpec] = []

        def fake_generate(spec, *, entries_by_step_path):
            calls.append(spec)

        with mock.patch.object(cad_generation, "_generate_step_outputs", side_effect=fake_generate):
            cad_generation.generate_step_targets(
                [str(step_path), str(script_path)],
                direct_step_kind="part",
                step_options=self._step_options(mesh_tolerance=0.2),
            )

        self.assertEqual([0.2, 0.2], [spec.mesh_tolerance for spec in calls])

    def test_generator_discovery_rejects_none_gen_step(self) -> None:
        script_path = self.temp_root / "broken.py"
        script_path.write_text(
            "\n".join(
                [
                    'DISPLAY_NAME = "broken"',
                    "def gen_step():",
                    "    return None",
                ]
            )
            + "\n"
        )

        with self.assertRaisesRegex(ValueError, "must return a shape, assembly list, or legacy envelope dict"):
            cad_generation.list_entry_specs()

    def test_generator_discovery_ignores_sidecar_only_scripts(self) -> None:
        script_path = self.temp_root / "flat.py"
        script_path.write_text(
            "\n".join(
                [
                    "def gen_dxf():",
                    "    return {'document': object(), 'dxf_output': 'flat.dxf'}",
                    "",
                ]
            ),
            encoding="utf-8",
        )

        specs = cad_generation.list_entry_specs()

        self.assertFalse(any(spec.source_path == script_path for spec in specs))

    def test_generated_part_ignores_mesh_settings_from_envelope_metadata(self) -> None:
        self._generator_script(
            "meshy",
            stl="meshy.stl",
            three_mf="meshy.3mf",
            mesh_tolerance=0.2,
            mesh_angular_tolerance=0.25,
        )

        specs = {
            spec.cad_ref: spec
            for spec in cad_generation.list_entry_specs()
            if spec.cad_ref.startswith(f"{self.relative_dir}/")
        }

        self.assertIsNone(specs[self._cad_ref("meshy")].stl_path)
        self.assertIsNone(specs[self._cad_ref("meshy")].three_mf_path)
        self.assertEqual(cad_generation.DEFAULT_MESH_TOLERANCE, specs[self._cad_ref("meshy")].mesh_tolerance)
        self.assertEqual(cad_generation.DEFAULT_MESH_ANGULAR_TOLERANCE, specs[self._cad_ref("meshy")].mesh_angular_tolerance)

    def test_generated_assembly_paths_use_sibling_defaults_and_ignore_legacy_sidecars(self) -> None:
        self._write_step("imported-part")
        self._write_assembly_generator(
            "assembly",
            instances=[
                {
                    "path": "imported-part.step",
                    "name": "leaf",
                    "transform": IDENTITY_TRANSFORM,
                }
            ],
            with_dxf=True,
            with_urdf=True,
            with_sdf=True,
            stl="assembly.stl",
            three_mf="assembly.3mf",
            mesh_tolerance=0.3,
            mesh_angular_tolerance=0.2,
        )

        spec = next(
            spec
            for spec in cad_generation.list_entry_specs()
            if spec.cad_ref == self._cad_ref("assembly")
        )

        self.assertEqual("assembly", spec.kind)
        self.assertEqual(self.temp_root / "assembly.step", spec.step_path)
        self.assertEqual(self.temp_root / "assembly.dxf", spec.dxf_path)
        self.assertEqual(self.temp_root / "assembly.urdf", spec.urdf_path)
        self.assertEqual(self.temp_root / "assembly.sdf", spec.sdf_path)
        self.assertIsNone(spec.stl_path)
        self.assertIsNone(spec.three_mf_path)
        self.assertEqual(cad_generation.DEFAULT_MESH_TOLERANCE, spec.mesh_tolerance)
        self.assertEqual(cad_generation.DEFAULT_MESH_ANGULAR_TOLERANCE, spec.mesh_angular_tolerance)

    def test_imported_step_defaults_to_part(self) -> None:
        self._write_step("imported")

        specs = [spec for spec in cad_generation.list_entry_specs() if spec.cad_ref == self._cad_ref("imported")]

        self.assertEqual(1, len(specs))
        self.assertEqual("part", specs[0].kind)

    def test_imported_stp_defaults_to_part(self) -> None:
        self._write_step("imported-stp", suffix=".stp")

        specs = [spec for spec in cad_generation.list_entry_specs() if spec.cad_ref == self._cad_ref("imported-stp")]

        self.assertEqual(1, len(specs))
        self.assertEqual("part", specs[0].kind)

    def test_imported_step_uses_default_mesh_settings(self) -> None:
        self._write_step("imported-mesh")

        specs = [spec for spec in cad_generation.list_entry_specs() if spec.cad_ref == self._cad_ref("imported-mesh")]

        self.assertEqual(1, len(specs))
        self.assertIsNone(specs[0].stl_path)
        self.assertIsNone(specs[0].three_mf_path)
        self.assertEqual(cad_generation.DEFAULT_MESH_TOLERANCE, specs[0].mesh_tolerance)
        self.assertEqual(cad_generation.DEFAULT_MESH_ANGULAR_TOLERANCE, specs[0].mesh_angular_tolerance)

    def test_imported_step_reads_mesh_settings_from_cli_options(self) -> None:
        step_path = self._write_step("imported-heavy")
        calls: list[cad_generation.EntrySpec] = []

        def fake_generate(spec, *, entries_by_step_path):
            calls.append(spec)

        with mock.patch.object(cad_generation, "_generate_step_outputs", side_effect=fake_generate):
            cad_generation.generate_step_targets(
                [str(step_path)],
                direct_step_kind="part",
                step_options=self._step_options(
                    stl="imported-heavy.stl",
                    three_mf="imported-heavy.3mf",
                    mesh_tolerance=0.9,
                    mesh_angular_tolerance=0.45,
                ),
            )

        self.assertEqual(1, len(calls))
        self.assertEqual(step_path.parent / "imported-heavy.stl", calls[0].stl_path)
        self.assertEqual(step_path.parent / "imported-heavy.3mf", calls[0].three_mf_path)
        self.assertEqual(0.9, calls[0].mesh_tolerance)
        self.assertEqual(0.45, calls[0].mesh_angular_tolerance)

    def test_script_step_material_colors_accepts_tuple_rgba(self) -> None:
        script_path = self.temp_root / "colored_assembly.py"
        script_path.write_text(
            "\n".join(
                [
                    "URDF_MATERIALS = {'black_aluminum': (0.168627, 0.184314, 0.2, 1.0)}",
                    "URDF_STEP_MATERIALS = {'imports/sample_component.step': 'black_aluminum'}",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        spec = cad_generation.EntrySpec(
            source_ref=self._cad_ref("colored_assembly.py"),
            cad_ref=self._cad_ref("colored_assembly"),
            kind="assembly",
            source_path=script_path,
            display_name="colored_assembly",
            source="generated",
            script_path=script_path,
        )

        self.assertEqual(
            {"imports/sample_component.step": (0.168627, 0.184314, 0.2, 1.0)},
            cad_generation._script_step_material_colors(spec),
        )

    def test_generated_assembly_source_colors_use_loaded_scene_before_child_step_loads(self) -> None:
        child_step = self._write_step("colored_leaf")
        assembly_path = self._write_assembly_generator(
            "colored_robot",
            instances=[
                {
                    "path": child_step.name,
                    "name": "colored_leaf",
                    "transform": IDENTITY_TRANSFORM,
                }
            ],
        )
        spec = cad_generation.EntrySpec(
            source_ref=self._cad_ref("colored_robot.py"),
            cad_ref=self._cad_ref("colored_robot"),
            kind="assembly",
            source_path=assembly_path,
            display_name="colored_robot",
            source="generated",
            step_path=assembly_path.with_suffix(".step"),
            script_path=assembly_path,
        )
        color = (0.168627, 0.184314, 0.2, 1.0)
        scene = LoadedStepScene(
            step_path=spec.step_path,
            roots=[
                OccurrenceNode(
                    path=(1,),
                    name="colored_leaf",
                    source_name="colored_leaf",
                    transform=tuple(float(value) for value in IDENTITY_TRANSFORM),
                    prototype_key=1,
                )
            ],
            prototype_shapes={},
            prototype_colors={1: color},
        )

        with mock.patch.object(
            cad_generation,
            "_uniform_source_step_color",
            side_effect=AssertionError("child STEP should not be loaded when assembly scene already has a uniform color"),
        ):
            occurrence_colors = cad_generation._generated_assembly_source_occurrence_colors(
                spec,
                scene,
                entries_by_step_path={child_step.resolve(): cad_generation.EntrySpec(
                    source_ref=self._cad_ref("colored_leaf.py"),
                    cad_ref=self._cad_ref("colored_leaf"),
                    kind="part",
                    source_path=child_step,
                    display_name="colored_leaf",
                    source="generated",
                    step_path=child_step,
                )},
            )

        self.assertEqual({"o1": color}, occurrence_colors)

    def test_generate_part_outputs_embeds_selector_artifacts_in_glb(self) -> None:
        step_path = self._write_step("selector-output")
        _, selected_specs = cad_generation._selected_specs_for_targets(
            [str(step_path)],
            step_options=self._step_options(mesh_tolerance=0.3, mesh_angular_tolerance=0.2),
        )
        spec = selected_specs[0]
        artifact_dir = cad_render.native_component_glb_dir(step_path).parent
        selector_manifest_path = artifact_dir / "topology.json"
        stale_binary_path = artifact_dir / "topology.bin"
        stale_extra_path = artifact_dir / "stale-artifact.txt"
        stale_extra_path.parent.mkdir(parents=True, exist_ok=True)
        selector_manifest_path.write_text("old topology", encoding="utf-8")
        stale_binary_path.write_bytes(b"old topology")
        stale_extra_path.write_text("old artifact", encoding="utf-8")
        scene = object()

        def fake_export_glb(
            step_path_arg,
            scene_arg,
            *,
            linear_deflection,
            angular_deflection,
            color=None,
            selector_bundle=None,
            include_selector_topology=True,
        ):
            self.assertIs(scene, scene_arg)
            self.assertLessEqual(linear_deflection, spec.mesh_tolerance)
            self.assertLessEqual(angular_deflection, spec.mesh_angular_tolerance)
            self.assertIsInstance(selector_bundle, SelectorBundle)
            self.assertTrue(include_selector_topology)
            glb_path = cad_render.part_glb_path(step_path_arg)
            glb_path.parent.mkdir(parents=True, exist_ok=True)
            glb_path.write_bytes(b"glb")
            return glb_path

        def fake_extract(scene_arg, *, cad_ref, profile, options, **kwargs):
            self.assertIs(scene, scene_arg)
            self.assertEqual(spec.cad_ref, cad_ref)
            self.assertEqual(cad_generation.SelectorProfile.ARTIFACT, profile)
            self.assertLessEqual(options.linear_deflection, spec.mesh_tolerance)
            self.assertLessEqual(options.angular_deflection, spec.mesh_angular_tolerance)
            return SelectorBundle(manifest={"schemaVersion": 1, "cadPath": spec.cad_ref}, buffers={})

        with mock.patch.object(cad_generation, "load_step_scene", return_value=scene) as load_scene, mock.patch.object(
            cad_generation, "export_part_stl_from_scene"
        ) as stl_export_mock, mock.patch.object(
            cad_generation,
            "export_part_glb_from_scene",
            side_effect=fake_export_glb,
        ), mock.patch.object(
            cad_generation,
            "mesh_step_scene",
        ), mock.patch.object(
            cad_generation,
            "scene_export_shape",
        ), mock.patch.object(
            cad_generation,
            "extract_selectors_from_scene",
            side_effect=fake_extract,
        ) as extract_selectors:
            result = cad_generation._generate_part_outputs(spec, entries_by_step_path={spec.step_path.resolve(): spec})

        load_scene.assert_called_once_with(step_path)
        stl_export_mock.assert_not_called()
        self.assertTrue(cad_render.part_glb_path(step_path).exists())
        self.assertIsNotNone(result.selector_bundle)
        self.assertFalse(selector_manifest_path.exists())
        self.assertFalse(stale_binary_path.exists())
        self.assertFalse(stale_extra_path.exists())

    def test_generate_part_outputs_reuses_current_topology_artifact(self) -> None:
        step_path = self._write_step("current-topology")
        _, selected_specs = cad_generation._selected_specs_for_targets(
            [str(step_path)],
            step_options=self._step_options(mesh_tolerance=0.3, mesh_angular_tolerance=0.2),
        )
        spec = selected_specs[0]
        scene = object()
        artifact = mock.Mock()
        artifact.manifest = {
            "stepHash": hashlib.sha256(step_path.read_bytes()).hexdigest(),
            "edgeRendering": {
                "visibilityClasses": ["feature", "tangent", "seam", "degenerate"],
            },
            "mesh": {
                "linearDeflection": 0.3,
                "angularDeflection": 0.2,
                "relative": True,
            }
        }

        with mock.patch.object(cad_generation, "load_step_scene", return_value=scene) as load_scene, mock.patch(
            "common.step_targets.validate_step_topology_artifact",
            return_value=artifact,
        ) as validate_artifact, mock.patch.object(
            cad_generation,
            "mesh_step_scene",
        ) as mesh_scene, mock.patch.object(
            cad_generation,
            "scene_export_shape",
        ) as export_shape, mock.patch.object(
            cad_generation,
            "extract_selectors_from_scene",
        ) as extract_selectors, mock.patch.object(
            cad_generation,
            "export_part_glb_from_scene",
        ) as export_glb:
            result = cad_generation._generate_part_outputs(
                spec,
                entries_by_step_path={spec.step_path.resolve(): spec},
            )

        self.assertIsNone(result.scene)
        self.assertIsNone(result.selector_bundle)
        validate_artifact.assert_called_once()
        load_scene.assert_not_called()
        mesh_scene.assert_not_called()
        export_shape.assert_not_called()
        extract_selectors.assert_not_called()
        export_glb.assert_not_called()

    def test_generate_part_outputs_rebuilds_stale_step_topology_artifact(self) -> None:
        step_path = self._write_step("stale-topology")
        _, selected_specs = cad_generation._selected_specs_for_targets(
            [str(step_path)],
            step_options=self._step_options(mesh_tolerance=0.3, mesh_angular_tolerance=0.2),
        )
        spec = selected_specs[0]
        scene = object()
        artifact = mock.Mock()
        artifact.manifest = {
            "stepHash": "stale-step-hash",
            "edgeRendering": {
                "visibilityClasses": ["feature", "tangent", "seam", "degenerate"],
            },
            "mesh": {
                "linearDeflection": 0.3,
                "angularDeflection": 0.2,
                "relative": True,
            },
        }

        def fake_export_glb(
            step_path_arg,
            scene_arg,
            *,
            linear_deflection,
            angular_deflection,
            color=None,
            selector_bundle=None,
            include_selector_topology=True,
        ):
            glb_path = cad_render.part_glb_path(step_path_arg)
            glb_path.parent.mkdir(parents=True, exist_ok=True)
            glb_path.write_bytes(b"glb")
            return glb_path

        with mock.patch.object(cad_generation, "load_step_scene", return_value=scene) as load_scene, mock.patch(
            "common.step_targets.validate_step_topology_artifact",
            return_value=artifact,
        ) as validate_artifact, mock.patch.object(
            cad_generation,
            "mesh_step_scene",
        ) as mesh_scene, mock.patch.object(
            cad_generation,
            "scene_export_shape",
        ), mock.patch.object(
            cad_generation,
            "extract_selectors_from_scene",
            return_value=SelectorBundle(manifest={"schemaVersion": STEP_TOPOLOGY_SCHEMA_VERSION, "cadPath": spec.cad_ref}, buffers={}),
        ) as extract_selectors, mock.patch.object(
            cad_generation,
            "export_part_glb_from_scene",
            side_effect=fake_export_glb,
        ) as export_glb:
            result = cad_generation._generate_part_outputs(
                spec,
                entries_by_step_path={spec.step_path.resolve(): spec},
            )

        self.assertIs(scene, result.scene)
        self.assertIsNotNone(result.selector_bundle)
        self.assertGreaterEqual(validate_artifact.call_count, 1)
        load_scene.assert_called_once_with(step_path)
        mesh_scene.assert_called_once()
        extract_selectors.assert_called_once()
        export_glb.assert_called_once()

    def test_generate_part_outputs_reuses_current_auto_topology_artifact_without_scene_load(self) -> None:
        step_path = self._write_step("current-auto-topology")
        _, selected_specs = cad_generation._selected_specs_for_targets([str(step_path)])
        spec = selected_specs[0]
        artifact = mock.Mock()
        artifact.manifest = {
            "stepHash": hashlib.sha256(step_path.read_bytes()).hexdigest(),
            "edgeRendering": {
                "visibilityClasses": ["feature", "tangent", "seam", "degenerate"],
            },
            "mesh": {
                "linearDeflection": 0.006,
                "angularDeflection": 0.2,
                "relative": True,
                "resolution": {
                    "mode": "auto",
                    "hints": {
                        "bboxDiag": 10.0,
                        "prototypeFaceCount": 6,
                        "prototypeEdgeCount": 12,
                        "prototypeCurvedFaceCount": 0,
                        "prototypeCurvedEdgeCount": 0,
                        "occurrenceFaceCount": 6,
                        "occurrenceEdgeCount": 12,
                        "occurrenceCurvedFaceCount": 0,
                        "occurrenceCurvedEdgeCount": 0,
                        "leafOccurrenceCount": 1,
                        "complexityScore": 17.2,
                        "effectiveComplexityScore": 11.18,
                        "curvaturePressureScore": 0.0,
                        "profile": "extra-fine",
                    },
                },
            }
        }

        with mock.patch.object(cad_generation, "load_step_scene") as load_scene, mock.patch(
            "common.step_targets.validate_step_topology_artifact",
            return_value=artifact,
        ), mock.patch.object(
            cad_generation,
            "extract_selectors_from_scene",
        ) as extract_selectors:
            result = cad_generation._generate_part_outputs(
                spec,
                entries_by_step_path={spec.step_path.resolve(): spec},
            )

        self.assertIsNone(result.scene)
        load_scene.assert_not_called()
        extract_selectors.assert_not_called()

    def test_generate_part_outputs_force_ignores_current_topology_artifact(self) -> None:
        step_path = self._write_step("force-topology")
        _, selected_specs = cad_generation._selected_specs_for_targets(
            [str(step_path)],
            step_options=self._step_options(mesh_tolerance=0.3, mesh_angular_tolerance=0.2),
        )
        spec = selected_specs[0]
        scene = object()
        artifact = mock.Mock()
        artifact.manifest = {
            "stepHash": hashlib.sha256(step_path.read_bytes()).hexdigest(),
            "mesh": {
                "linearDeflection": 0.3,
                "angularDeflection": 0.2,
                "relative": True,
            }
        }

        def fake_export_glb(
            step_path_arg,
            scene_arg,
            *,
            linear_deflection,
            angular_deflection,
            color=None,
            selector_bundle=None,
            include_selector_topology=True,
        ):
            glb_path = cad_render.part_glb_path(step_path_arg)
            glb_path.parent.mkdir(parents=True, exist_ok=True)
            glb_path.write_bytes(b"glb")
            return glb_path

        with mock.patch.object(cad_generation, "load_step_scene", return_value=scene), mock.patch(
            "common.step_targets.validate_step_topology_artifact",
            return_value=artifact,
        ) as validate_artifact, mock.patch.object(
            cad_generation,
            "mesh_step_scene",
        ) as mesh_scene, mock.patch.object(
            cad_generation,
            "scene_export_shape",
        ), mock.patch.object(
            cad_generation,
            "extract_selectors_from_scene",
            return_value=SelectorBundle(manifest={"schemaVersion": STEP_TOPOLOGY_SCHEMA_VERSION, "cadPath": spec.cad_ref}, buffers={}),
        ) as extract_selectors, mock.patch.object(
            cad_generation,
            "export_part_glb_from_scene",
            side_effect=fake_export_glb,
        ) as export_glb:
            result = cad_generation._generate_part_outputs(
                spec,
                entries_by_step_path={spec.step_path.resolve(): spec},
                force=True,
            )

        self.assertIs(scene, result.scene)
        self.assertIsNotNone(result.selector_bundle)
        validate_artifact.assert_not_called()
        mesh_scene.assert_called_once()
        extract_selectors.assert_called_once()
        export_glb.assert_called_once()

    def test_generate_part_outputs_writes_requested_sidecar_and_topology(self) -> None:
        step_path = self._write_step("stl-fast")
        _, selected_specs = cad_generation._selected_specs_for_targets(
            [str(step_path)],
            step_options=self._step_options(stl="stl-fast.stl"),
        )
        spec = selected_specs[0]
        scene = object()

        def fake_export(step_path_arg, scene_arg, *, target_path=None):
            self.assertEqual(step_path, step_path_arg)
            self.assertIs(scene, scene_arg)
            self.assertEqual(spec.stl_path, target_path)
            target_path.write_text("solid ok\nendsolid ok\n", encoding="utf-8")
            return target_path

        with mock.patch.object(cad_generation, "load_step_scene", return_value=scene), mock.patch.object(
            cad_generation,
            "export_part_stl_from_scene",
            side_effect=fake_export,
        ) as stl_export_mock, mock.patch.object(
            cad_generation,
            "export_part_glb_from_scene",
        ) as export_glb, mock.patch.object(
            cad_generation,
            "extract_selectors_from_scene",
            return_value=SelectorBundle(manifest={"schemaVersion": STEP_TOPOLOGY_SCHEMA_VERSION}, buffers={}),
        ) as extract_selectors, mock.patch.object(
            cad_generation,
            "mesh_step_scene",
        ), mock.patch.object(
            cad_generation,
            "scene_export_shape",
        ):
            result = cad_generation._generate_part_outputs(
                spec,
                entries_by_step_path={spec.step_path.resolve(): spec},
            )

        stl_export_mock.assert_called_once()
        export_glb.assert_called_once()
        extract_selectors.assert_called_once()
        self.assertIs(scene, result.scene)
        self.assertIsNotNone(result.selector_bundle)
        self.assertIsNotNone(spec.stl_path)
        self.assertTrue(spec.stl_path.exists())

    def test_generate_part_outputs_uses_preloaded_scene_without_reloading(self) -> None:
        step_path = self._write_step("preloaded")
        _, selected_specs = cad_generation._selected_specs_for_targets(
            [str(step_path)],
            step_options=self._step_options(mesh_tolerance=0.3, mesh_angular_tolerance=0.2),
        )
        spec = selected_specs[0]
        scene = mock.Mock()
        scene.step_path = step_path.resolve()

        def fake_export_glb(
            step_path_arg,
            scene_arg,
            *,
            linear_deflection,
            angular_deflection,
            color=None,
            selector_bundle=None,
            include_selector_topology=True,
        ):
            self.assertIs(scene, scene_arg)
            self.assertIsInstance(selector_bundle, SelectorBundle)
            self.assertTrue(include_selector_topology)
            glb_path = cad_render.part_glb_path(step_path_arg)
            glb_path.parent.mkdir(parents=True, exist_ok=True)
            glb_path.write_bytes(b"glb")
            return glb_path

        def fake_extract(scene_arg, *, cad_ref, profile, options, **kwargs):
            self.assertIs(scene, scene_arg)
            return SelectorBundle(manifest={"schemaVersion": STEP_TOPOLOGY_SCHEMA_VERSION, "cadPath": spec.cad_ref}, buffers={})

        with mock.patch.object(cad_generation, "load_step_scene") as load_scene, mock.patch.object(
            cad_generation,
            "export_part_glb_from_scene",
            side_effect=fake_export_glb,
        ), mock.patch.object(
            cad_generation,
            "mesh_step_scene",
        ), mock.patch.object(
            cad_generation,
            "scene_export_shape",
        ), mock.patch.object(
            cad_generation,
            "extract_selectors_from_scene",
            side_effect=fake_extract,
        ):
            cad_generation._generate_part_outputs(
                spec,
                entries_by_step_path={spec.step_path.resolve(): spec},
                preloaded_scene=scene,
            )

        load_scene.assert_not_called()
        self.assertTrue(cad_render.part_glb_path(step_path).exists())
        self.assertFalse(cad_render.native_component_glb_dir(step_path).parent.exists())

    def test_generate_part_outputs_always_embeds_topology_with_stl_sidecar(self) -> None:
        step_path = self._write_step("summary-only")
        _, selected_specs = cad_generation._selected_specs_for_targets(
            [str(step_path)],
            step_options=self._step_options(
                stl="summary-only.stl",
            ),
        )
        spec = selected_specs[0]
        artifact_dir = cad_render.native_component_glb_dir(step_path).parent
        selector_manifest_path = artifact_dir / "topology.json"
        selector_binary_path = artifact_dir / "topology.bin"
        selector_manifest_path.parent.mkdir(parents=True, exist_ok=True)
        selector_manifest_path.write_text("stale", encoding="utf-8")
        selector_binary_path.write_bytes(b"stale")
        scene = object()

        def fake_export(step_path_arg, scene_arg, *, target_path=None):
            self.assertIs(scene, scene_arg)
            stl_path = target_path
            self.assertIsNotNone(stl_path)
            stl_path.parent.mkdir(parents=True, exist_ok=True)
            stl_path.write_text("solid ok\nendsolid ok\n")
            return stl_path

        def fake_export_glb(
            step_path_arg,
            scene_arg,
            *,
            linear_deflection,
            angular_deflection,
            color=None,
            selector_bundle=None,
            include_selector_topology=True,
        ):
            self.assertIs(scene, scene_arg)
            self.assertIsInstance(selector_bundle, SelectorBundle)
            self.assertTrue(include_selector_topology)
            glb_path = cad_render.part_glb_path(step_path_arg)
            glb_path.parent.mkdir(parents=True, exist_ok=True)
            glb_path.write_bytes(b"glb")
            return glb_path

        def fake_extract(scene_arg, *, cad_ref, profile, options, **kwargs):
            self.assertIs(scene, scene_arg)
            self.assertEqual(cad_generation.SelectorProfile.ARTIFACT, profile)
            return SelectorBundle(manifest={"schemaVersion": 1, "cadPath": cad_ref}, buffers={})

        with mock.patch.object(cad_generation, "load_step_scene", return_value=scene), mock.patch.object(
            cad_generation,
            "export_part_stl_from_scene",
            side_effect=fake_export,
        ), mock.patch.object(
            cad_generation,
            "export_part_glb_from_scene",
            side_effect=fake_export_glb,
        ), mock.patch.object(
            cad_generation,
            "mesh_step_scene",
        ), mock.patch.object(
            cad_generation,
            "scene_export_shape",
        ), mock.patch.object(
            cad_generation,
            "extract_selectors_from_scene",
            side_effect=fake_extract,
        ) as extract_selectors:
            result = cad_generation._generate_part_outputs(spec, entries_by_step_path={spec.step_path.resolve(): spec})

        extract_selectors.assert_called_once()
        self.assertIsNotNone(spec.stl_path)
        self.assertTrue(spec.stl_path.exists())
        self.assertTrue(cad_render.part_glb_path(step_path).exists())
        self.assertIsNotNone(result.selector_bundle)
        self.assertFalse(selector_manifest_path.exists())
        self.assertFalse(selector_binary_path.exists())

    def test_generate_part_outputs_writes_3mf_sidecar(self) -> None:
        step_path = self._write_step("printable")
        _, selected_specs = cad_generation._selected_specs_for_targets(
            [str(step_path)],
            step_options=self._step_options(
                three_mf="printable.3mf",
                mesh_tolerance=0.4,
                mesh_angular_tolerance=0.3,
            ),
        )
        spec = selected_specs[0]
        scene = object()

        def fake_three_mf_export(step_path_arg, scene_arg, *, target_path=None, color=None):
            self.assertEqual(step_path, step_path_arg)
            self.assertIs(scene, scene_arg)
            self.assertEqual(spec.three_mf_path, target_path)
            self.assertIsNone(color)
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_bytes(b"3mf")
            return target_path

        def fake_export_glb(
            step_path_arg,
            scene_arg,
            *,
            linear_deflection,
            angular_deflection,
            color=None,
            selector_bundle=None,
            include_selector_topology=True,
        ):
            self.assertIs(scene, scene_arg)
            self.assertIsInstance(selector_bundle, SelectorBundle)
            self.assertTrue(include_selector_topology)
            glb_path = cad_render.part_glb_path(step_path_arg)
            glb_path.parent.mkdir(parents=True, exist_ok=True)
            glb_path.write_bytes(b"glb")
            return glb_path

        def fake_extract(scene_arg, *, cad_ref, profile, options, **kwargs):
            self.assertIs(scene, scene_arg)
            self.assertEqual(cad_generation.SelectorProfile.ARTIFACT, profile)
            return SelectorBundle(manifest={"schemaVersion": 1, "cadPath": cad_ref}, buffers={})

        with mock.patch.object(cad_generation, "load_step_scene", return_value=scene), mock.patch.object(
            cad_generation,
            "export_part_3mf_from_scene",
            side_effect=fake_three_mf_export,
        ) as three_mf_export_mock, mock.patch.object(
            cad_generation,
            "export_part_glb_from_scene",
            side_effect=fake_export_glb,
        ), mock.patch.object(
            cad_generation,
            "mesh_step_scene",
        ) as mesh_scene, mock.patch.object(
            cad_generation,
            "scene_export_shape",
        ), mock.patch.object(
            cad_generation,
            "extract_selectors_from_scene",
            side_effect=fake_extract,
        ):
            cad_generation._generate_part_outputs(spec, entries_by_step_path={spec.step_path.resolve(): spec})

        three_mf_export_mock.assert_called_once()
        self.assertTrue(any(
            call.kwargs.get("linear_deflection") <= 0.4 and call.kwargs.get("angular_deflection") == 0.3
            for call in mesh_scene.mock_calls
        ))
        self.assertIsNotNone(spec.three_mf_path)
        self.assertTrue(spec.three_mf_path.exists())

    def test_generate_part_outputs_writes_native_glb_sidecar(self) -> None:
        step_path = self._write_step("native")
        _, selected_specs = cad_generation._selected_specs_for_targets(
            [str(step_path)],
            step_options=self._step_options(
                glb="native.glb",
                mesh_tolerance=0.4,
                mesh_angular_tolerance=0.3,
            ),
        )
        spec = selected_specs[0]
        scene = object()

        def fake_native_glb_export(
            step_path_arg,
            scene_arg,
            *,
            target_path=None,
            linear_deflection=None,
            angular_deflection=None,
            color=None,
        ):
            self.assertEqual(step_path, step_path_arg)
            self.assertIs(scene, scene_arg)
            self.assertEqual(spec.native_glb_path, target_path)
            self.assertLessEqual(linear_deflection, 0.4)
            self.assertEqual(0.3, angular_deflection)
            self.assertIsNone(color)
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_bytes(b"native glb")
            return target_path

        def fake_export_glb(
            step_path_arg,
            scene_arg,
            *,
            linear_deflection,
            angular_deflection,
            color=None,
            selector_bundle=None,
            include_selector_topology=True,
        ):
            self.assertIs(scene, scene_arg)
            self.assertIsInstance(selector_bundle, SelectorBundle)
            self.assertTrue(include_selector_topology)
            glb_path = cad_render.part_glb_path(step_path_arg)
            glb_path.parent.mkdir(parents=True, exist_ok=True)
            glb_path.write_bytes(b"topology glb")
            return glb_path

        def fake_extract(scene_arg, *, cad_ref, profile, options, **kwargs):
            self.assertIs(scene, scene_arg)
            self.assertEqual(cad_generation.SelectorProfile.ARTIFACT, profile)
            return SelectorBundle(manifest={"schemaVersion": 1, "cadPath": cad_ref}, buffers={})

        with mock.patch.object(cad_generation, "load_step_scene", return_value=scene), mock.patch.object(
            cad_generation,
            "export_native_glb_from_scene",
            side_effect=fake_native_glb_export,
        ) as native_glb_export_mock, mock.patch.object(
            cad_generation,
            "export_part_glb_from_scene",
            side_effect=fake_export_glb,
        ), mock.patch.object(
            cad_generation,
            "mesh_step_scene",
        ), mock.patch.object(
            cad_generation,
            "scene_export_shape",
        ), mock.patch.object(
            cad_generation,
            "extract_selectors_from_scene",
            side_effect=fake_extract,
        ):
            cad_generation._generate_part_outputs(spec, entries_by_step_path={spec.step_path.resolve(): spec})

        native_glb_export_mock.assert_called_once()
        self.assertIsNotNone(spec.native_glb_path)
        self.assertTrue(spec.native_glb_path.exists())
        self.assertTrue(cad_render.part_glb_path(step_path).exists())

    def test_generate_assembly_outputs_writes_self_contained_glb_and_removes_stale_components(self) -> None:
        step_path = self._write_step("imported-assembly")
        _, selected_specs = cad_generation._selected_specs_for_targets(
            [str(step_path)],
            direct_step_kind="assembly",
        )
        spec = selected_specs[0]
        scene = object()
        components_dir = cad_render.native_component_glb_dir(step_path)
        components_dir.mkdir(parents=True, exist_ok=True)
        (components_dir / "stale.glb").write_bytes(b"stale")

        def fake_export_assembly_glb(
            step_path_arg,
            scene_arg,
            *,
            linear_deflection,
            angular_deflection,
            color=None,
            occurrence_colors=None,
            selector_bundle=None,
            include_selector_topology=True,
        ):
            self.assertEqual(step_path, step_path_arg)
            self.assertIs(scene, scene_arg)
            self.assertIsInstance(selector_bundle, SelectorBundle)
            self.assertTrue(include_selector_topology)
            glb_path = cad_render.part_glb_path(step_path_arg)
            glb_path.parent.mkdir(parents=True, exist_ok=True)
            glb_path.write_bytes(b"assembly glb")
            return glb_path

        def fake_extract(scene_arg, *, cad_ref, profile, options, **kwargs):
            self.assertIs(scene, scene_arg)
            return SelectorBundle(manifest=_summary_manifest(cad_ref), buffers={})

        with mock.patch.object(cad_generation, "load_step_scene", return_value=scene), mock.patch.object(
            cad_generation,
            "export_assembly_glb_from_scene",
            side_effect=fake_export_assembly_glb,
        ), mock.patch.object(
            cad_generation,
            "mesh_step_scene",
        ), mock.patch.object(
            cad_generation,
            "scene_export_shape",
        ), mock.patch.object(
            cad_generation,
            "extract_selectors_from_scene",
            side_effect=fake_extract,
        ):
            result = cad_generation._generate_part_outputs(spec, entries_by_step_path={spec.step_path.resolve(): spec})

        self.assertIs(scene, result.scene)
        self.assertTrue(cad_render.part_glb_path(step_path).exists())
        self.assertFalse(components_dir.exists())
        self.assertIsNotNone(result.selector_bundle)
        assert result.selector_bundle is not None
        topology = result.selector_bundle.manifest
        self.assertEqual("gltf-node-extras", topology["assembly"]["mesh"]["addressing"])
        self.assertEqual(".imported-assembly.step.glb", topology["assembly"]["mesh"]["url"])
        leaves = topology["assembly"]["root"]["children"]
        self.assertTrue(leaves)
        self.assertNotIn("assets", leaves[0])

    def test_generate_assembly_outputs_passes_occurrence_colors_to_glb(self) -> None:
        step_path = self._write_step("colored-assembly")
        script_path = self.temp_root / "colored_assembly.py"
        script_path.write_text("", encoding="utf-8")
        spec = cad_generation.EntrySpec(
            source_ref=self._cad_ref("colored_assembly.py"),
            cad_ref=self._cad_ref("colored_assembly"),
            kind="assembly",
            source_path=script_path,
            display_name="colored_assembly",
            source="generated",
            step_path=step_path,
            script_path=script_path,
        )
        scene = object()
        occurrence_colors = {"o1.1": (0.1, 0.2, 0.3, 1.0)}
        export_calls: list[dict[str, object]] = []

        def fake_export_assembly_glb(
            step_path_arg,
            scene_arg,
            *,
            linear_deflection,
            angular_deflection,
            color=None,
            occurrence_colors=None,
            selector_bundle=None,
            include_selector_topology=True,
        ):
            self.assertEqual(step_path, step_path_arg)
            self.assertIs(scene, scene_arg)
            self.assertIsInstance(selector_bundle, SelectorBundle)
            self.assertTrue(include_selector_topology)
            export_calls.append({"occurrence_colors": occurrence_colors})
            glb_path = cad_render.part_glb_path(step_path_arg)
            glb_path.parent.mkdir(parents=True, exist_ok=True)
            glb_path.write_bytes(b"assembly glb")
            return glb_path

        def fake_extract(scene_arg, *, cad_ref, profile, options, **kwargs):
            self.assertIs(scene, scene_arg)
            self.assertEqual(occurrence_colors, kwargs.get("occurrence_colors"))
            return SelectorBundle(manifest=_summary_manifest(cad_ref), buffers={})

        assembly_composition = {
            "schemaVersion": 1,
            "mode": "linked",
            "mesh": {
                "url": "model.glb",
                "hash": "",
                "addressing": "gltf-node-extras",
                "occurrenceIdKey": "cadOccurrenceId",
            },
            "root": {
                "id": "root",
                "occurrenceId": "o1",
                "children": [{"id": "o1.1", "occurrenceId": "o1.1", "children": []}],
            },
        }

        with mock.patch.object(cad_generation, "load_step_scene", return_value=scene), mock.patch.object(
            cad_generation,
            "export_assembly_glb_from_scene",
            side_effect=fake_export_assembly_glb,
        ), mock.patch.object(
            cad_generation,
            "mesh_step_scene",
        ), mock.patch.object(
            cad_generation,
            "scene_export_shape",
        ), mock.patch.object(
            cad_generation,
            "extract_selectors_from_scene",
            side_effect=fake_extract,
        ) as extract_selectors, mock.patch.object(
            cad_generation,
            "_assembly_composition_for_spec",
            return_value=assembly_composition,
        ), mock.patch.object(
            cad_generation,
            "_generated_assembly_source_occurrence_colors",
            return_value=occurrence_colors,
        ) as generated_colors:
            cad_generation._generate_part_outputs(spec, entries_by_step_path={step_path.resolve(): spec})

        self.assertEqual([{"occurrence_colors": occurrence_colors}], export_calls)
        extract_selectors.assert_called_once()
        generated_colors.assert_called_once()

    def test_generated_assembly_3mf_uses_shared_occurrence_colors_without_topology_deferral(self) -> None:
        step_path = self._write_step("colored-printable-assembly")
        script_path = self.temp_root / "colored_printable_assembly.py"
        script_path.write_text("", encoding="utf-8")
        three_mf_path = self.temp_root / "colored_printable_assembly.3mf"
        spec = cad_generation.EntrySpec(
            source_ref=self._cad_ref("colored_printable_assembly.py"),
            cad_ref=self._cad_ref("colored_printable_assembly"),
            kind="assembly",
            source_path=script_path,
            display_name="colored_printable_assembly",
            source="generated",
            step_path=step_path,
            script_path=script_path,
            three_mf_path=three_mf_path,
        )
        scene = object()
        occurrence_colors = {"o1.1": (0.1, 0.2, 0.3, 1.0)}
        expected_occurrence_colors = occurrence_colors
        events: list[str] = []

        def fake_three_mf_export(step_path_arg, scene_arg, *, target_path=None, color=None, occurrence_colors=None):
            self.assertEqual(step_path, step_path_arg)
            self.assertIs(scene, scene_arg)
            self.assertEqual(three_mf_path, target_path)
            self.assertIsNone(color)
            self.assertEqual(expected_occurrence_colors, occurrence_colors)
            events.append("3mf")
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_bytes(b"3mf")
            return target_path

        def fake_export_assembly_glb(
            step_path_arg,
            scene_arg,
            *,
            linear_deflection,
            angular_deflection,
            color=None,
            occurrence_colors=None,
            selector_bundle=None,
            include_selector_topology=True,
        ):
            self.assertEqual(step_path, step_path_arg)
            self.assertIs(scene, scene_arg)
            self.assertEqual(expected_occurrence_colors, occurrence_colors)
            self.assertIsInstance(selector_bundle, SelectorBundle)
            self.assertTrue(include_selector_topology)
            glb_path = cad_render.part_glb_path(step_path_arg)
            glb_path.parent.mkdir(parents=True, exist_ok=True)
            glb_path.write_bytes(b"assembly glb")
            events.append("glb")
            return glb_path

        def fake_extract(scene_arg, *, cad_ref, profile, options, **kwargs):
            self.assertIs(scene, scene_arg)
            self.assertEqual(occurrence_colors, kwargs.get("occurrence_colors"))
            events.append("topology")
            return SelectorBundle(manifest=_summary_manifest(cad_ref), buffers={})

        with mock.patch.object(
            cad_generation,
            "load_step_scene",
            return_value=scene,
        ), mock.patch.object(
            cad_generation,
            "export_part_3mf_from_scene",
            side_effect=fake_three_mf_export,
        ) as three_mf_export_mock, mock.patch.object(
            cad_generation,
            "export_assembly_glb_from_scene",
            side_effect=fake_export_assembly_glb,
        ), mock.patch.object(
            cad_generation,
            "mesh_step_scene",
        ), mock.patch.object(
            cad_generation,
            "scene_export_shape",
        ), mock.patch.object(
            cad_generation,
            "extract_selectors_from_scene",
            side_effect=fake_extract,
        ), mock.patch.object(
            cad_generation,
            "_assembly_composition_for_spec",
            return_value=None,
        ), mock.patch.object(
            cad_generation,
            "_generated_assembly_source_occurrence_colors",
            return_value=occurrence_colors,
        ) as generated_colors:
            cad_generation._generate_part_outputs(spec, entries_by_step_path={step_path.resolve(): spec})

        three_mf_export_mock.assert_called_once()
        generated_colors.assert_called_once()
        self.assertIn("3mf", events)
        self.assertIn("topology", events)
        self.assertLess(events.index("3mf"), events.index("topology"))
        self.assertTrue(three_mf_path.exists())

    def test_expand_specs_walks_leaves_through_compound_grouping_nodes(self):
        """Compound grouping AssemblyNodeSpec (``source_path=None`` with
        nested children) is a valid pattern per the data model:
        ``AssemblyNodeSpec.source_path`` is typed ``Path | None`` and
        ``_leaf_instances_from_nodes`` recursively flattens nested groups.

        Dependency expansion must therefore skip the compound itself
        without crashing on ``compound.source_path.resolve()``, while still
        discovering the nested leaf sources by way of
        ``assembly_spec.instances`` (which is the flattened leaf view).
        """

        # Real part on disk so source resolution finds it.
        leaf_script = self._generator_script("nested_part")

        assembly_path = self.temp_root / "compound_root.py"
        assembly_path.write_text("# noop\n", encoding="utf-8")

        identity = tuple(IDENTITY_TRANSFORM)
        leaf_step_rel = "nested_part.step"

        leaf_instance = AssemblyInstanceSpec(
            instance_id="nested_part",
            source_path=leaf_script.resolve(),
            path=leaf_step_rel,
            name="nested_part",
            transform=identity,
        )
        leaf_node = AssemblyNodeSpec(
            instance_id="nested_part",
            name="nested_part",
            transform=identity,
            source_path=leaf_script.resolve(),
            path=leaf_step_rel,
            children=(),
        )
        compound = AssemblyNodeSpec(
            instance_id="leg_FR",
            name="leg_FR",
            transform=identity,
            source_path=None,
            path=None,
            children=(leaf_node,),
        )
        fake_spec = AssemblySpec(
            assembly_path=assembly_path.resolve(),
            instances=(leaf_instance,),
            children=(compound,),
        )

        entry = cad_generation.EntrySpec(
            source_ref=self._cad_ref("compound_root"),
            cad_ref=self._cad_ref("compound_root"),
            kind="assembly",
            source_path=assembly_path.resolve(),
            display_name="compound_root",
            source="generator",
        )

        with mock.patch.object(
            cad_generation, "read_assembly_spec", return_value=fake_spec
        ):
            result = cad_generation._expand_specs_with_file_dependencies([entry])

        discovered_paths = {spec.source_path for spec in result}
        self.assertIn(assembly_path.resolve(), discovered_paths)
        self.assertIn(leaf_script.resolve(), discovered_paths)


if __name__ == "__main__":
    unittest.main()
