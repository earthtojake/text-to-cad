import contextlib
import hashlib
import io
import json
import shutil
import types
import unittest
from dataclasses import replace
from pathlib import Path
from unittest import mock

from cadgen._internal import generation as cad_generation
from cadgen import catalog as cad_catalog
from cadgen._internal import source_hash as cad_source_hash
from cadgen.catalog import StepImportOptions
from cadgen._internal.glb import read_step_topology_manifest_from_glb
from cadgen._internal.glb_topology import STEP_TOPOLOGY_SCHEMA_VERSION
from cadgen._internal.step_scene import LoadedStepScene, OccurrenceNode, SelectorBundle
from cadgen._internal.step_metadata import TEXT_TO_CAD_GENERATOR, read_text_to_cad_step_metadata
from tests.python.support.cad_test_roots import IsolatedCadRoots


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
        self.relative_dir = self.temp_root.relative_to(Path.cwd()).as_posix()

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
        mesh_tolerance: float | None = None,
        mesh_angular_tolerance: float | None = None,
    ) -> StepImportOptions:
        return StepImportOptions(
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

    def _fake_scene(self, step_path: Path) -> types.SimpleNamespace:
        """A minimal stand-in scene carrying a sentinel ``source_compound`` so the
        unified package emit skips its ``import_step`` fallback (the package build
        itself is patched by ``_patch_package_build``)."""
        return types.SimpleNamespace(
            step_path=step_path.expanduser().resolve(),
            source_compound=object(),
        )

    def _patch_package_build(self):
        """Patch the component-package emit to materialize a minimal package
        directory (``.{model}.step.glb/`` + ``assembly.json``), mirroring the real
        unified emit without meshing. Returns ``(patcher, calls)`` where ``calls``
        records each ``build_package_from_compound`` invocation's key arguments."""
        calls: list[dict] = []

        def _fake(
            shape,
            *,
            package_dir,
            root_name,
            single_component=False,
            force=False,
            provenance=None,
            linear_deflection=None,
            angular_deflection=None,
            progress=None,
        ):
            calls.append(
                {
                    "single_component": single_component,
                    "force": force,
                    "provenance": provenance or {},
                    "root_name": root_name,
                }
            )
            package_dir.mkdir(parents=True, exist_ok=True)
            (package_dir / "assembly.json").write_text(
                json.dumps(
                    {
                        "kind": "assembly-package",
                        "entryKind": (provenance or {}).get("entryKind", "part"),
                        "occurrences": [],
                        "components": {},
                    }
                ),
                encoding="utf-8",
            )
            return {
                "occurrences": 1,
                "unique_components": 1,
                "components_built": 1,
                "components_reused": 0,
            }

        return (
            mock.patch("cadgen._internal.component_package.build_package_from_compound", side_effect=_fake),
            calls,
        )

    def test_imported_step_assembly_force_writes_component_package(self) -> None:
        """Regression: an imported/committed STEP built with force must actually emit
        the component-GLB package. ``_generate_step_outputs`` previously routed only
        ``source == "generated"`` specs into the build pipeline and fell off the end for an
        imported/committed STEP — silently returning None (no package written) while the
        caller still reported success. `scripts/gen` no longer accepts direct STEP targets,
        so this now drives the live on-demand path (`cadgen.step_artifact`) that inspect,
        snapshot, the CAD Viewer, and `scripts/artifact` all share.
        """
        from build123d import Box, Compound, Pos
        from cadgen.step_export import export_build123d_step_scene

        # A real multi-part STEP on disk standing in for a committed assembly input.
        block_a = Pos(0, 0, 0) * Box(10, 10, 10)
        block_a.label = "block_a"
        block_b = Pos(30, 0, 0) * Box(6, 6, 6)
        block_b.label = "block_b"
        assembly = Compound(children=[block_a, block_b], label="imported_fixture")
        step_path = self.temp_root / "imported_fixture.step"
        export_build123d_step_scene(assembly, step_path)
        self.assertTrue(step_path.is_file())

        package_dir = cad_catalog.render_package_dir(step_path)
        self.assertFalse(
            (package_dir / "assembly.json").exists(),
            "precondition: the package must not exist before the build",
        )

        from cadgen.step_artifact import build_step_artifact

        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            payload = build_step_artifact(
                repo_root=self.temp_root,
                step=step_path,
                kind="assembly",
                force=True,
            )
        self.assertTrue(payload["ok"])
        self.assertEqual("assembly", payload["entryKind"])

        descriptor_path = package_dir / "assembly.json"
        self.assertTrue(
            descriptor_path.is_file(),
            "imported STEP --kind assembly --force must write assembly.json (not a silent no-op)",
        )
        descriptor = json.loads(descriptor_path.read_text())
        self.assertEqual("assembly-package", descriptor["kind"])
        self.assertEqual("assembly", descriptor.get("entryKind"))
        components = descriptor["components"]
        self.assertTrue(components, "the package must reference at least one component")
        for entry in components.values():
            ref = str(entry["glb"])
            # Self-contained, flat refs into the package's own components/ dir.
            self.assertTrue(ref.startswith("components/"), ref)
            self.assertNotIn("..", ref)
            self.assertTrue((package_dir / ref).is_file(), f"missing component GLB {ref}")
        # components/ holds only flat GLB files — no nested __cadgen__ scaffolding.
        self.assertEqual(
            [],
            [child.name for child in (package_dir / "components").iterdir() if child.is_dir()],
        )

    def test_catalog_discovery_ignores_urdf_only_generators(self) -> None:
        self._write_step("sample")
        (self._isolated_roots.cad_root / "sample_urdf.py").write_text(
            "def gen_urdf():\n"
            "    return {'xml': '<robot name=\"sample\" />'}\n",
            encoding="utf-8",
        )
        (self._isolated_roots.cad_root / "sample_sdf.py").write_text(
            "def gen_sdf():\n"
            "    return {'xml': '<sdf version=\"1.12\"><model name=\"sample\" /></sdf>'}\n",
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
        dxf_before_step: bool = False,
        step_output: str | None = None,
        stl: str | None = None,
        three_mf: str | None = None,
        dxf_output: str | None = None,
        mesh_tolerance: float | None = None,
        mesh_angular_tolerance: float | None = None,
    ) -> Path:
        fields: list[str] = ["'shape': _shape()"]
        if step_output is not None:
            fields.append(f"'step_output': {step_output!r}")
        if stl is not None:
            fields.append(f"'stl': {stl!r}")
        if three_mf is not None:
            fields.append(f"'3mf': {three_mf!r}")
        if mesh_tolerance is not None:
            fields.append(f"'mesh_tolerance': {mesh_tolerance!r}")
        if mesh_angular_tolerance is not None:
            fields.append(f"'mesh_angular_tolerance': {mesh_angular_tolerance!r}")
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
        del dxf_before_step  # gen_dxf lives in a dedicated <name>.dxf.py sibling now
        blocks = [prologue, step_block]

        script_path = self.temp_root / f"{name}.py"
        script_path.write_text("\n".join(line for block in blocks for line in block), encoding="utf-8")
        if with_dxf:
            self._dxf_generator_script(name, dxf_output=dxf_output)
        return script_path

    def _dxf_generator_script(self, name: str, *, dxf_output: str | None = None) -> Path:
        # A dedicated `<name>.dxf.py` drawing generator (the only gen_dxf shape the
        # catalog accepts). Records calls into the SAME `<name>.calls` file as the
        # step generator so cross-generator execution would be visible.
        dxf_path = self.temp_root / f"{name}.dxf.py"
        dxf_path.write_text(
            "\n".join(
                [
                    "from pathlib import Path",
                    "import ezdxf",
                    f"CALLS = Path(__file__).with_name('{name}.calls')",
                    "def _record(record_name):",
                    "    with CALLS.open('a', encoding='utf-8') as handle:",
                    "        handle.write(record_name + '\\n')",
                    "def _make_doc():",
                    "    doc = ezdxf.new('R2010')",
                    "    doc.units = ezdxf.units.MM",
                    "    doc.modelspace().add_lwpolyline(",
                    "        [(0, 0), (10, 0), (10, 5), (0, 5)], close=True, dxfattribs={'layer': 'CUT'}",
                    "    )",
                    "    return doc",
                    "def gen_dxf():",
                    "    _record('gen_dxf')",
                    "    return {",
                    "        'document': _make_doc(),",
                    *([f"        'dxf_output': {dxf_output!r}," ] if dxf_output is not None else []),
                    "    }",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        return dxf_path

    def _write_assembly_generator(
        self,
        name: str,
        *,
        instances: list[dict[str, object]],
        with_dxf: bool = False,
        step_output: str | None = None,
        stl: str | None = None,
        three_mf: str | None = None,
        dxf_output: str | None = None,
        mesh_tolerance: float | None = None,
        mesh_angular_tolerance: float | None = None,
    ) -> Path:
        # gen_step() returns an inline multi-child Compound literal so the static AST
        # classifier (which looks for Compound(children=...)) sees kind=assembly. The
        # instance list controls the count/names of child boxes — a stand-in for the
        # legacy {'instances': ...} envelope.
        instance_names = [str(inst.get("name", f"part_{idx}")) for idx, inst in enumerate(instances)]
        shape_expr = (
            "Compound("
            f"children=[Box(1, 1, 1) for _ in {instance_names!r}], "
            f"label={name!r}"
            ")"
        )
        fields: list[str] = [f"'shape': {shape_expr}"]
        if step_output is not None:
            fields.append(f"'step_output': {step_output!r}")
        if stl is not None:
            fields.append(f"'stl': {stl!r}")
        if three_mf is not None:
            fields.append(f"'3mf': {three_mf!r}")
        if mesh_tolerance is not None:
            fields.append(f"'mesh_tolerance': {mesh_tolerance!r}")
        if mesh_angular_tolerance is not None:
            fields.append(f"'mesh_angular_tolerance': {mesh_angular_tolerance!r}")
        lines = [
            "from pathlib import Path",
            "from build123d import Box, Compound",
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
        assembly_path = self.temp_root / f"{name}.py"
        assembly_path.write_text("\n".join(lines), encoding="utf-8")
        if with_dxf:
            self._dxf_generator_script(name, dxf_output=dxf_output)
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

    def test_python_source_hash_uses_generator_file_contents(self) -> None:
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
        script_path.write_text(script_path.read_text(encoding="utf-8") + "\n# changed\n", encoding="utf-8")
        script_changed = cad_generation.python_source_hash(script_path)

        self.assertEqual(before.source_hash, after.source_hash)
        self.assertNotEqual(before.source_hash, script_changed.source_hash)

    def test_python_source_hash_has_no_manifest_payloads(self) -> None:
        script_path = self.temp_root / "source.py"
        script_path.write_text(
            "def gen_step():\n"
            "    return object()\n",
            encoding="utf-8",
        )
        identity = cad_source_hash.python_source_hash(script_path)

        self.assertTrue(identity.source_hash)
        self.assertFalse(hasattr(identity, "files"))
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

    def test_generated_source_rejects_legacy_step_output_field(self) -> None:
        self._generator_script("flat", step_output="custom/renamed.step")

        with self.assertRaisesRegex(ValueError, "unsupported field\\(s\\): step_output"):
            cad_generation.list_entry_specs()

    def test_generated_dxf_rejects_legacy_dxf_output_field(self) -> None:
        self._generator_script("flat", with_dxf=True, dxf_output="../drawings/renamed.dxf")

        with self.assertRaisesRegex(ValueError, "unsupported field\\(s\\): dxf_output"):
            cad_generation.list_entry_specs()

    def test_generated_source_rejects_legacy_parent_output(self) -> None:
        self._generator_script("flat", step_output="../../../flat.step")

        with self.assertRaisesRegex(ValueError, "unsupported field\\(s\\): step_output"):
            cad_generation.list_entry_specs()

    def test_generated_source_rejects_invalid_legacy_output_suffix(self) -> None:
        self._generator_script("flat", step_output="flat.stp")

        with self.assertRaisesRegex(ValueError, "unsupported field\\(s\\): step_output"):
            cad_generation.list_entry_specs()

    def test_generated_dxf_defaults_output_to_sibling_stem(self) -> None:
        script_path = self._dxf_generator_script("flat")

        spec = next(spec for spec in cad_generation.list_entry_specs() if spec.source_path == script_path)

        self.assertEqual("dxf", spec.kind)
        self.assertEqual(self.temp_root / "flat.dxf", spec.dxf_path)
        self.assertEqual(self._cad_ref("flat") + ".dxf", spec.cad_ref)

    def test_explicit_target_rejects_gen_dxf_beside_gen_step(self) -> None:
        script_path = self.temp_root / "flat.py"
        script_path.write_text(
            "\n".join(
                [
                    "def gen_step():",
                    "    return {'shape': object()}",
                    "",
                    "def gen_dxf():",
                    "    return {'document': object()}",
                    "",
                ]
            ),
            encoding="utf-8",
        )

        with self.assertRaisesRegex(ValueError, "dedicated <name>.dxf.py drawing generator"):
            cad_catalog.source_from_path(script_path)

    def test_explicit_dxf_generator_target_rejects_gen_step(self) -> None:
        script_path = self.temp_root / "flat.dxf.py"
        script_path.write_text(
            "\n".join(
                [
                    "def gen_step():",
                    "    return {'shape': object()}",
                    "",
                    "def gen_dxf():",
                    "    return {'document': object()}",
                    "",
                ]
            ),
            encoding="utf-8",
        )

        with self.assertRaisesRegex(ValueError, "must not define gen_step"):
            cad_catalog.source_from_path(script_path)

    def test_directory_discovery_skips_invalid_generator_sources(self) -> None:
        # An unmigrated source (gen_dxf beside gen_step) is skipped with a warning
        # instead of aborting the whole catalog, so unrelated targets keep working.
        invalid_path = self.temp_root / "unmigrated.py"
        invalid_path.write_text(
            "\n".join(
                [
                    "def gen_step():",
                    "    return {'shape': object()}",
                    "",
                    "def gen_dxf():",
                    "    return {'document': object()}",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        self._generator_script("flat")

        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            specs = cad_generation.list_entry_specs()

        cad_refs = {spec.cad_ref for spec in specs}
        self.assertIn(self._cad_ref("flat"), cad_refs)
        self.assertNotIn(self._cad_ref("unmigrated"), cad_refs)
        self.assertIn("skipping invalid CAD source", stderr.getvalue())

    def test_deprecated_urdf_and_sdf_generators_are_ignored(self) -> None:
        # gen_urdf()/gen_sdf() are hard-deprecated: robot descriptions are
        # authored XML artifacts, so leftover definitions are not generators.
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

        self.assertEqual(("gen_step",), spec.generator_metadata.generator_names)

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

        # gen_step builds the render scene in memory and writes no STEP by default.
        self.assertEqual("part", spec.kind)
        self.assertIsNotNone(scene)
        self.assertFalse(script_path.with_suffix(".step").exists())
        self.assertEqual("python", scene.source_kind)
        self.assertEqual(cad_generation.python_source_hash(script_path).source_hash, scene.source_hash)
        self.assertIsNotNone(scene)
        self.assertEqual("python", scene.source_kind)
        self.assertEqual(cad_generation.python_source_hash(script_path).source_hash, scene.source_hash)

    def test_bare_dxf_document_return_is_supported(self) -> None:
        # The CLI stays naming-agnostic: a plain `.py` defining only gen_dxf() is a
        # valid EXPLICIT target. The default build product is the drawing package;
        # no sibling .dxf is written.
        script_path = self.temp_root / "bare_dxf.py"
        script_path.write_text(
            "\n".join(
                [
                    "import ezdxf",
                    "def gen_dxf():",
                    "    doc = ezdxf.new('R2010')",
                    "    doc.units = ezdxf.units.MM",
                    "    doc.modelspace().add_lwpolyline(",
                    "        [(0, 0), (10, 0), (10, 5), (0, 5)], close=True, dxfattribs={'layer': 'CUT'}",
                    "    )",
                    "    return doc",
                    "",
                ]
            ),
            encoding="utf-8",
        )

        cad_generation.generate_dxf_targets([str(script_path)])

        package_dir = self.temp_root / "__cadgen__" / "models" / "bare_dxf.py"
        # The package caches only what was computed. A generated drawing's DXF is
        # reproducible from its generator, so it is exported on demand, never cached.
        self.assertTrue((package_dir / "preview.glb").exists())
        self.assertFalse((package_dir / "drawing.dxf").exists())
        self.assertTrue((package_dir / "drawing.json").exists())
        self.assertFalse((self.temp_root / "bare_dxf.dxf").exists())

    def test_dxf_generation_writes_sibling_export_on_demand(self) -> None:
        script_path = self._dxf_generator_script("flat")

        cad_generation.generate_dxf_targets([str(script_path)], write_dxf=True)

        self.assertTrue((self.temp_root / "flat.dxf").exists())
        package_dir = self.temp_root / "__cadgen__" / "models" / "flat.dxf.py"
        self.assertTrue((package_dir / "drawing.json").exists())

    def test_dxf_generation_skips_current_drawing_package(self) -> None:
        script_path = self._dxf_generator_script("flat")
        calls_path = self.temp_root / "flat.calls"

        cad_generation.generate_dxf_targets([str(script_path)])
        self.assertEqual("gen_dxf\n", calls_path.read_text(encoding="utf-8"))

        # Unchanged source closure -> the second run skips regeneration entirely.
        cad_generation.generate_dxf_targets([str(script_path)])
        self.assertEqual("gen_dxf\n", calls_path.read_text(encoding="utf-8"))

        # A comment-only edit does NOT change the semantic closure -> still skips.
        script_path.write_text(
            script_path.read_text(encoding="utf-8") + "\n# changed\n", encoding="utf-8"
        )
        cad_generation.generate_dxf_targets([str(script_path)])
        self.assertEqual("gen_dxf\n", calls_path.read_text(encoding="utf-8"))

        # A semantic source edit invalidates the recorded closure -> rebuild.
        script_path.write_text(
            script_path.read_text(encoding="utf-8") + "\n_EDIT_MARKER = 1\n", encoding="utf-8"
        )
        cad_generation.generate_dxf_targets([str(script_path)])
        self.assertEqual("gen_dxf\ngen_dxf\n", calls_path.read_text(encoding="utf-8"))

    def test_dxf_envelope_rejects_unknown_fields(self) -> None:
        # The gen_dxf envelope is {"document"} only. Non-Python inputs (e.g. an
        # imported .step the drawing projects) are deliberately not freshness
        # inputs — code reuse is the staleness link, not data files.
        script_path = self.temp_root / "projection.dxf.py"
        script_path.write_text(
            "\n".join(
                [
                    "from pathlib import Path",
                    "class _FakeDxf:",
                    "    def saveas(self, output_path):",
                    "        Path(output_path).write_text('0\\nEOF\\n', encoding='utf-8')",
                    "def gen_dxf():",
                    "    return {",
                    "        'document': _FakeDxf(),",
                    "        'sources': ['imported-part.step'],",
                    "    }",
                    "",
                ]
            ),
            encoding="utf-8",
        )

        with self.assertRaisesRegex(ValueError, "unsupported field\\(s\\): sources"):
            cad_generation.list_entry_specs()

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

    def test_generation_regenerates_selected_entries_in_supplied_order(self) -> None:
        first_path = self._generator_script("first")
        second_path = self._generator_script("second")
        calls: list[str] = []

        def fake_generate(spec, *, entries_by_step_path, **_extra):
            self.assertIn(spec.step_path.resolve(), entries_by_step_path)
            calls.append(spec.cad_ref)

        with mock.patch.object(cad_generation, "_generate_step_outputs", side_effect=fake_generate):
            cad_generation.generate_step_targets([str(second_path), str(first_path)])

        self.assertEqual([self._cad_ref("second"), self._cad_ref("first")], calls)

    def test_current_target_with_explicit_exports_still_runs(self) -> None:
        # A current compose must not swallow an explicitly requested export (the
        # --write-step SOURCE=OUTPUT pair): the no-op fast path previously dropped
        # such specs as current and wrote nothing.
        script_path = self._generator_script("current_exports")
        calls: list[object] = []

        def fake_generate(spec, **kwargs):
            calls.append(spec)
            return cad_generation.GeneratedStepResult(spec=spec, scene=None)

        with mock.patch.object(
            cad_generation, "_assembly_is_current", return_value=True
        ), mock.patch.object(
            cad_generation, "_assembly_glb_package_current", return_value=True
        ), mock.patch.object(
            cad_generation, "_rebuild_stale_assembly_children"
        ), mock.patch.object(
            cad_generation, "_generate_step_outputs", side_effect=fake_generate
        ):
            # Baseline: with no export requests the current target no-ops.
            cad_generation.generate_step_targets([str(script_path)])
            self.assertEqual([], calls)

            step_output = self.temp_root / "exports" / "current_exports.step"
            cad_generation.generate_step_targets([f"{script_path}={step_output}"])

        self.assertEqual(1, len(calls))
        self.assertIsNotNone(calls[0].step_export_path)
        self.assertTrue(str(calls[0].step_export_path).endswith("current_exports.step"))

    def test_step_generation_default_allows_missing_logical_step(self) -> None:
        # gen_step builds GLB render artifacts and never writes a text STEP, so the
        # logical .step path need not exist and the artifact pipeline must not require it.
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
            )

        run_generator.assert_called_once()
        self.assertEqual(False, calls[0]["require_step_file"])
        self.assertIs(scene, calls[0]["preloaded_scene"])
        self.assertFalse(calls[0]["force"])

    def test_generated_step_targets_expect_python_backed_topology_artifacts(self) -> None:
        script_path = self._generator_script("generated_kind")
        generated_spec = next(spec for spec in cad_generation.list_entry_specs() if spec.source_path == script_path)
        direct_path = self._write_step("direct_kind")
        _, direct_specs = cad_generation._selected_specs_for_targets([str(direct_path)])

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

    def test_step_output_pairs_retarget_generated_sources(self) -> None:
        first_path = self._generator_script("first")
        second_path = self._generator_script("second")
        first_output = self.temp_root / "custom" / "first-output.step"
        second_output = self.temp_root / "custom" / "second-output.step"
        calls: list[cad_generation.EntrySpec] = []

        def fake_generate(spec, *, entries_by_step_path, preloaded_scene=None, force=False, **_extra):
            self.assertIn(spec.step_path.resolve(), entries_by_step_path)
            self.assertIsNotNone(preloaded_scene)
            calls.append(spec)

        with mock.patch.object(cad_generation, "_generate_part_outputs", side_effect=fake_generate):
            cad_generation.generate_step_targets(
                [f"{first_path}={first_output}", f"{second_path}={second_output}"],
            )

        self.assertEqual([first_output, second_output], [call.step_path for call in calls])
        self.assertEqual([first_output, second_output], [call.step_export_path for call in calls])
        self.assertFalse(first_path.with_suffix(".step").exists())
        self.assertFalse(second_path.with_suffix(".step").exists())

    def test_step_output_pairs_allow_mixed_plain_and_paired_targets(self) -> None:
        first_path = self._generator_script("first")
        second_path = self._generator_script("second")
        second_output = self.temp_root / "custom" / "second-output.step"
        calls: list[cad_generation.EntrySpec] = []

        def fake_generate(spec, *, entries_by_step_path, preloaded_scene=None, force=False, **_extra):
            calls.append(spec)

        with mock.patch.object(cad_generation, "_generate_part_outputs", side_effect=fake_generate):
            cad_generation.generate_step_targets([str(first_path), f"{second_path}={second_output}"])

        self.assertEqual([first_path.with_suffix(".step"), second_output], [call.step_path for call in calls])
        # A SOURCE=OUTPUT.step pair requests an on-demand STEP export to that path.
        self.assertEqual([None, second_output], [call.step_export_path for call in calls])
        self.assertFalse(second_path.with_suffix(".step").exists())

    def test_step_output_pairs_reject_duplicate_output_paths(self) -> None:
        first_path = self._generator_script("first")
        second_path = self._generator_script("second")
        output_path = self.temp_root / "shared.step"

        with self.assertRaisesRegex(ValueError, "used more than once"):
            cad_generation.generate_step_targets([f"{first_path}={output_path}", f"{second_path}={output_path}"])

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

        def fake_generate(spec, *, entries_by_step_path, **_extra):
            calls.append(spec.kind)

        with mock.patch.object(cad_generation, "_generate_step_outputs", side_effect=fake_generate):
            cad_generation.generate_step_targets([str(assembly_path)])

        self.assertEqual(["assembly"], calls)

    def test_dxf_generation_rejects_source_without_dxf(self) -> None:
        script_path = self._generator_script("part")

        with self.assertRaisesRegex(ValueError, "does not define gen_dxf\\(\\)"):
            cad_generation.generate_dxf_targets([str(script_path)])

    def test_dxf_output_override_retargets_single_generated_source(self) -> None:
        script_path = self._dxf_generator_script("flat")
        output_path = self.temp_root / "drawings" / "flat-output.dxf"

        cad_generation.generate_dxf_targets([str(script_path)], output=str(output_path))

        self.assertTrue(output_path.exists())
        self.assertFalse((self.temp_root / "flat.dxf").exists())

    def test_dxf_output_pair_retargets_generated_source(self) -> None:
        first_path = self._dxf_generator_script("first")
        second_path = self._dxf_generator_script("second")
        first_output = self.temp_root / "drawings" / "first-output.dxf"
        second_output = self.temp_root / "drawings" / "second-output.dxf"

        cad_generation.generate_dxf_targets([f"{first_path}={first_output}", f"{second_path}={second_output}"])

        self.assertTrue(first_output.exists())
        self.assertTrue(second_output.exists())
        self.assertFalse((self.temp_root / "first.dxf").exists())
        self.assertFalse((self.temp_root / "second.dxf").exists())

    def test_dxf_output_pair_allows_mixed_plain_and_paired_targets(self) -> None:
        first_path = self._dxf_generator_script("first")
        second_path = self._dxf_generator_script("second")
        second_output = self.temp_root / "drawings" / "second-output.dxf"

        cad_generation.generate_dxf_targets([str(first_path), f"{second_path}={second_output}"])

        # The plain target builds its drawing package (no sibling export by default).
        package_dir = self.temp_root / "__cadgen__" / "models" / "first.dxf.py"
        # The package caches only what was computed. A generated drawing's DXF is
        # reproducible from its generator, so it is exported on demand, never cached.
        self.assertTrue((package_dir / "preview.glb").exists())
        self.assertFalse((package_dir / "drawing.dxf").exists())
        self.assertFalse((self.temp_root / "first.dxf").exists())
        self.assertTrue(second_output.exists())
        self.assertFalse((self.temp_root / "second.dxf").exists())

    def test_dxf_output_override_rejects_pair_targets(self) -> None:
        script_path = self._dxf_generator_script("flat")

        with self.assertRaisesRegex(ValueError, "cannot be combined"):
            cad_generation.generate_dxf_targets(
                [f"{script_path}={self.temp_root / 'drawings' / 'flat-output.dxf'}"],
                output=str(self.temp_root / "other.dxf"),
            )

    def test_dxf_output_pairs_reject_duplicate_output_paths(self) -> None:
        first_path = self._dxf_generator_script("first")
        second_path = self._dxf_generator_script("second")
        output_path = self.temp_root / "shared.dxf"

        with self.assertRaisesRegex(ValueError, "used more than once"):
            cad_generation.generate_dxf_targets([f"{first_path}={output_path}", f"{second_path}={output_path}"])

    def test_dxf_output_override_requires_single_target(self) -> None:
        first_path = self._dxf_generator_script("first")
        second_path = self._dxf_generator_script("second")

        with self.assertRaisesRegex(ValueError, "--output can only be used with exactly one target"):
            cad_generation.generate_dxf_targets(
                [str(first_path), str(second_path)],
                output=str(self.temp_root / "first-output.dxf"),
            )

    def test_step_generator_does_not_run_sidecars(self) -> None:
        script_path = self._generator_script("flat", with_dxf=True, dxf_before_step=True)
        spec = next(spec for spec in cad_generation.list_entry_specs() if spec.cad_ref == self._cad_ref("flat"))

        cad_generation.run_script_generator(spec, "gen_step")

        self.assertEqual("gen_step\n", script_path.with_suffix(".calls").read_text(encoding="utf-8"))
        self.assertFalse(script_path.with_suffix(".dxf").exists())
        self.assertFalse(script_path.with_suffix(".step").exists())

    def test_generated_step_outputs_reuses_generated_scene(self) -> None:
        script_path = self._generator_script("flat")
        spec = next(spec for spec in cad_generation.list_entry_specs() if spec.cad_ref == self._cad_ref("flat"))
        step_path = script_path.with_suffix(".step")
        observed_scene = None

        def fake_outputs(spec_arg, *, entries_by_step_path, preloaded_scene=None, force=False, **_extra):
            nonlocal observed_scene
            observed_scene = preloaded_scene
            self.assertIs(spec, spec_arg)

        with mock.patch.object(cad_generation, "_generate_part_outputs", side_effect=fake_outputs):
            cad_generation._generate_step_outputs(spec, entries_by_step_path={spec.step_path.resolve(): spec})

        self.assertIsNotNone(observed_scene)
        self.assertEqual(step_path.resolve(), observed_scene.step_path)
        self.assertIsNotNone(observed_scene.doc)
        self.assertEqual("python", observed_scene.source_kind)
        self.assertEqual(cad_generation.python_source_hash(script_path).source_hash, observed_scene.source_hash)
        # gen_step writes no STEP, so there is no on-disk STEP to hash.
        self.assertFalse(step_path.exists())

    def test_normal_python_generation_reuses_current_package(self) -> None:
        script_path = self._generator_script("flat")
        spec = next(spec for spec in cad_generation.list_entry_specs() if spec.cad_ref == self._cad_ref("flat"))
        step_path = script_path.with_suffix(".step")
        source_identity = cad_generation.python_source_hash(script_path)
        scene = LoadedStepScene(
            step_path=step_path.resolve(),
            roots=[],
            prototype_shapes={},
            source_kind="python",
            source_hash=source_identity.source_hash,
            source_path=cad_generation.relative_to_cwd(script_path),
        )

        # A current model reuses its package: the topology options match, the package is
        # complete, and its source closure is unchanged -> no remesh.
        with (
            mock.patch.object(cad_generation, "_existing_topology_artifact_matches_options", return_value=True),
            mock.patch.object(cad_generation, "_assembly_glb_package_current", return_value=True),
            mock.patch.object(cad_generation, "_generated_assembly_glb_closure_current", return_value=True),
            ):
            result = cad_generation._generate_part_outputs(
                spec,
                entries_by_step_path={spec.step_path.resolve(): spec},
                preloaded_scene=scene,
                require_step_file=False,
                force=False,
            )

        self.assertIs(scene, result.scene)
        self.assertIsNone(result.selector_bundle)

    def test_python_generation_reuses_current_package_without_running_gen_step(self) -> None:
        script_path = self._generator_script("flat")
        spec = next(spec for spec in cad_generation.list_entry_specs() if spec.cad_ref == self._cad_ref("flat"))
        artifact = mock.Mock()
        artifact.manifest = {
            "sourceKind": "python",
            "sourceHash": "old-python-source-hash",
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
                "cadgen.step_targets.validate_step_topology_artifact",
                return_value=artifact,
            ),
            mock.patch.object(cad_generation, "_assembly_glb_package_current", return_value=True),
            mock.patch.object(cad_generation, "_generated_assembly_glb_closure_current", return_value=True),
            mock.patch.object(
                cad_generation,
                "run_script_generator",
                side_effect=AssertionError("current Python-backed package should be reused before gen_step"),
            ),
        ):
            result = cad_generation._generate_step_outputs(
                spec,
                entries_by_step_path={spec.step_path.resolve(): spec},
                force=False,
            )

        self.assertIsNone(result.scene)
        self.assertIsNone(result.selector_bundle)
        self.assertEqual(script_path.with_suffix(".step"), result.spec.step_path)

    def test_dxf_generators_are_separate_generation_specs(self) -> None:
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
            with_dxf=True,
        )

        cad_refs = {
            spec.cad_ref
            for spec in cad_generation.list_entry_specs()
            if spec.cad_ref.startswith(f"{self.relative_dir}/")
        }

        # `.dxf.py` drawings are their own catalog entries, keyed with the `.dxf`
        # suffix so they never collide with the same-stem STEP entry.
        self.assertIn(self._cad_ref("flat"), cad_refs)
        self.assertIn(self._cad_ref("robot"), cad_refs)
        self.assertIn(self._cad_ref("flat") + ".dxf", cad_refs)
        self.assertIn(self._cad_ref("robot") + ".dxf", cad_refs)

    def test_step_toml_target_is_not_supported(self) -> None:
        (self.temp_root / "broken.step.toml").write_text('kind = "part"\n', encoding="utf-8")

        with self.assertRaisesRegex(FileNotFoundError, "Python generator or STEP/STP file path"):
            cad_generation.generate_step_targets([str(self.temp_root / "broken.step.toml")])

    def test_direct_step_targets_are_rejected(self) -> None:
        # scripts/gen builds gen_step() sources only; an imported STEP gets its render
        # artifacts on demand (inspect/snapshot/viewer) or via scripts/artifact.
        step_path = self._write_step("source")

        with self.assertRaisesRegex(ValueError, "builds gen_step\\(\\) Python sources only"):
            cad_generation.generate_step_targets([str(step_path)])

    def test_step_cli_flags_apply_to_generated_python_targets(self) -> None:
        script_path = self._generator_script("generated")
        calls: list[cad_generation.EntrySpec] = []

        def fake_generate(spec, *, entries_by_step_path, **_extra):
            calls.append(spec)

        with mock.patch.object(cad_generation, "_generate_step_outputs", side_effect=fake_generate):
            cad_generation.generate_step_targets(
                [str(script_path)],
                step_options=self._step_options(
                    mesh_tolerance=0.2,
                    mesh_angular_tolerance=0.3,
                ),
            )

        self.assertEqual(1, len(calls))
        self.assertEqual(0.2, calls[0].mesh_tolerance)
        self.assertEqual(0.3, calls[0].mesh_angular_tolerance)

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

        with self.assertRaisesRegex(ValueError, "must return a build123d shape or a \\{'shape': \\.\\.\\.\\} envelope"):
            cad_generation.list_entry_specs()

    def test_generator_discovery_ignores_sidecar_only_scripts(self) -> None:
        script_path = self.temp_root / "flat.py"
        script_path.write_text(
            "\n".join(
                [
                    "def gen_dxf():",
                    "    return {'document': object()}",
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

        self.assertEqual(cad_generation.DEFAULT_MESH_TOLERANCE, specs[self._cad_ref("meshy")].mesh_tolerance)
        self.assertEqual(cad_generation.DEFAULT_MESH_ANGULAR_TOLERANCE, specs[self._cad_ref("meshy")].mesh_angular_tolerance)

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
        self.assertEqual(cad_generation.DEFAULT_MESH_TOLERANCE, specs[0].mesh_tolerance)
        self.assertEqual(cad_generation.DEFAULT_MESH_ANGULAR_TOLERANCE, specs[0].mesh_angular_tolerance)

    def test_imported_step_reads_mesh_settings_from_cli_options(self) -> None:
        step_path = self._write_step("imported-heavy")

        _all, selected = cad_generation._selected_specs_for_targets(
            [str(step_path)],
            step_options=self._step_options(mesh_tolerance=0.9, mesh_angular_tolerance=0.45),
        )

        self.assertEqual(1, len(selected))
        self.assertEqual(0.9, selected[0].mesh_tolerance)
        self.assertEqual(0.45, selected[0].mesh_angular_tolerance)

    def test_generate_part_outputs_emits_package(self) -> None:
        step_path = self._write_step("selector-output")
        _, selected_specs = cad_generation._selected_specs_for_targets(
            [str(step_path)],
            step_options=self._step_options(mesh_tolerance=0.3, mesh_angular_tolerance=0.2),
        )
        spec = selected_specs[0]
        scene = self._fake_scene(step_path)
        package_patch, package_calls = self._patch_package_build()

        with mock.patch.object(cad_generation, "load_step_scene_cached", return_value=scene) as load_scene, package_patch:
            result = cad_generation._generate_part_outputs(spec, entries_by_step_path={spec.step_path.resolve(): spec})

        load_scene.assert_called_once_with(step_path)
        # A part emits a single-component package directory; the build path returns no
        # whole-model selector bundle (selectors are extracted on demand by inspect).
        self.assertEqual(1, len(package_calls))
        self.assertTrue(package_calls[0]["single_component"])
        self.assertTrue(cad_catalog.render_package_dir(step_path).is_dir())
        self.assertIsNone(result.selector_bundle)

    def test_generate_part_outputs_reuses_current_topology_artifact(self) -> None:
        step_path = self._write_step("current-topology")
        _, selected_specs = cad_generation._selected_specs_for_targets(
            [str(step_path)],
            step_options=self._step_options(mesh_tolerance=0.3, mesh_angular_tolerance=0.2),
        )
        spec = selected_specs[0]
        scene = self._fake_scene(step_path)
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

        package_patch, package_calls = self._patch_package_build()
        with mock.patch.object(cad_generation, "load_step_scene_cached", return_value=scene) as load_scene, mock.patch(
            "cadgen.step_targets.validate_step_topology_artifact",
            return_value=artifact,
        ) as validate_artifact, package_patch:
            result = cad_generation._generate_part_outputs(
                spec,
                entries_by_step_path={spec.step_path.resolve(): spec},
            )

        # The current topology artifact is reused: no scene load, no remesh, no package build.
        self.assertIsNone(result.scene)
        self.assertIsNone(result.selector_bundle)
        validate_artifact.assert_called_once()
        load_scene.assert_not_called()
        self.assertEqual(0, len(package_calls))

    def test_generate_part_outputs_rebuilds_stale_step_topology_artifact(self) -> None:
        step_path = self._write_step("stale-topology")
        _, selected_specs = cad_generation._selected_specs_for_targets(
            [str(step_path)],
            step_options=self._step_options(mesh_tolerance=0.3, mesh_angular_tolerance=0.2),
        )
        spec = selected_specs[0]
        scene = self._fake_scene(step_path)
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

        package_patch, package_calls = self._patch_package_build()
        with mock.patch.object(cad_generation, "load_step_scene_cached", return_value=scene) as load_scene, mock.patch(
            "cadgen.step_targets.validate_step_topology_artifact",
            return_value=artifact,
        ) as validate_artifact, package_patch:
            result = cad_generation._generate_part_outputs(
                spec,
                entries_by_step_path={spec.step_path.resolve(): spec},
            )

        self.assertIs(scene, result.scene)
        self.assertIsNone(result.selector_bundle)
        self.assertGreaterEqual(validate_artifact.call_count, 1)
        load_scene.assert_called_once_with(step_path)
        # No sidecar outputs requested: the whole-scene mesh is skipped and the
        # package build meshes exactly the components it emits.
        self.assertEqual(1, len(package_calls))

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

        package_patch, package_calls = self._patch_package_build()
        with mock.patch.object(cad_generation, "load_step_scene_cached") as load_scene, mock.patch(
            "cadgen.step_targets.validate_step_topology_artifact",
            return_value=artifact,
        ), package_patch:
            result = cad_generation._generate_part_outputs(
                spec,
                entries_by_step_path={spec.step_path.resolve(): spec},
            )

        # The current auto-tolerance artifact is reused without even loading the scene.
        self.assertIsNone(result.scene)
        load_scene.assert_not_called()
        self.assertEqual(0, len(package_calls))

    def test_generate_part_outputs_force_ignores_current_topology_artifact(self) -> None:
        step_path = self._write_step("force-topology")
        _, selected_specs = cad_generation._selected_specs_for_targets(
            [str(step_path)],
            step_options=self._step_options(mesh_tolerance=0.3, mesh_angular_tolerance=0.2),
        )
        spec = selected_specs[0]
        scene = self._fake_scene(step_path)
        artifact = mock.Mock()
        artifact.manifest = {
            "stepHash": hashlib.sha256(step_path.read_bytes()).hexdigest(),
            "mesh": {
                "linearDeflection": 0.3,
                "angularDeflection": 0.2,
                "relative": True,
            }
        }

        package_patch, package_calls = self._patch_package_build()
        with mock.patch.object(cad_generation, "load_step_scene_cached", return_value=scene), mock.patch(
            "cadgen.step_targets.validate_step_topology_artifact",
            return_value=artifact,
        ) as validate_artifact, package_patch:
            result = cad_generation._generate_part_outputs(
                spec,
                entries_by_step_path={spec.step_path.resolve(): spec},
                force=True,
            )

        self.assertIs(scene, result.scene)
        self.assertIsNone(result.selector_bundle)
        validate_artifact.assert_not_called()
        # No sidecar outputs requested: even a forced rebuild skips the
        # whole-scene mesh; the package build re-meshes every component.
        # force propagates into the package build (content-addressed cache bypass).
        self.assertEqual(1, len(package_calls))
        self.assertTrue(package_calls[0]["force"])

    def test_generate_part_outputs_uses_preloaded_scene_without_reloading(self) -> None:
        step_path = self._write_step("preloaded")
        _, selected_specs = cad_generation._selected_specs_for_targets(
            [str(step_path)],
            step_options=self._step_options(mesh_tolerance=0.3, mesh_angular_tolerance=0.2),
        )
        spec = selected_specs[0]
        scene = self._fake_scene(step_path)

        package_patch, package_calls = self._patch_package_build()
        with mock.patch.object(cad_generation, "load_step_scene_cached") as load_scene, package_patch:
            cad_generation._generate_part_outputs(
                spec,
                entries_by_step_path={spec.step_path.resolve(): spec},
                preloaded_scene=scene,
            )

        load_scene.assert_not_called()
        self.assertEqual(1, len(package_calls))
        self.assertTrue(cad_catalog.render_package_dir(step_path).is_dir())

    # --- Incremental-regen freshness gate (D) --------------------------------

    def _write_part_with_dependency(self, prefix: str) -> tuple[Path, Path]:
        """A generated part whose generator imports a sibling helper module, so
        its captured source closure spans more than its own file."""
        helper = self.temp_root / f"{prefix}_dims.py"
        helper.write_text("WIDTH = 3.0\n", encoding="utf-8")
        script = self.temp_root / f"{prefix}.py"
        script.write_text(
            f"import {prefix}_dims as dims\n"
            "def gen_step():\n"
            "    import build123d\n"
            "    return {'shape': build123d.Box(dims.WIDTH, 2.0, 1.0)}\n",
            encoding="utf-8",
        )
        return script, helper

    def _part_spec(self, script: Path) -> cad_generation.EntrySpec:
        _all, selected, _outs = cad_generation._selected_specs_for_targets(
            [str(script)],
            expected_output_suffixes=(".step",),
            tool_name="scripts/gen",
            include_output_paths=True,
        )
        return selected[0]

    def test_generated_part_records_source_closure(self) -> None:
        script, _helper = self._write_part_with_dependency("record")
        cad_generation.generate_step_targets([str(script)])
        spec = self._part_spec(script)

        # The render package is keyed by the entry filename (the generator), not the
        # logical .step — read the manifest from the entry-keyed package.
        manifest = read_step_topology_manifest_from_glb(
            cad_catalog.render_package_dir(spec.entry_path)
        )
        self.assertIsNotNone(manifest)
        assert manifest is not None
        self.assertTrue(manifest.get("sourceClosureHash"))
        joined = " ".join(manifest.get("sourceClosureFiles") or [])
        self.assertIn("record.py", joined)
        self.assertIn("record_dims.py", joined)

    def test_generated_child_is_stale_tracks_own_and_transitive_edits(self) -> None:
        script, helper = self._write_part_with_dependency("stalecheck")
        cad_generation.generate_step_targets([str(script)])
        spec = self._part_spec(script)

        self.assertFalse(cad_generation._generated_child_is_stale(spec, force=False))
        self.assertTrue(cad_generation._generated_child_is_stale(spec, force=True))

        original = script.read_text(encoding="utf-8")
        # A comment-only edit is semantically invisible -> NOT stale.
        script.write_text(original + "\n# tweak\n", encoding="utf-8")
        self.assertFalse(cad_generation._generated_child_is_stale(spec, force=False))
        # A semantic own-file edit IS detected.
        script.write_text(original + "\n_EDIT_MARKER = 1\n", encoding="utf-8")
        self.assertTrue(cad_generation._generated_child_is_stale(spec, force=False))
        script.write_text(original, encoding="utf-8")
        self.assertFalse(cad_generation._generated_child_is_stale(spec, force=False))

        # Editing a transitive dependency (reached via import) is detected.
        helper.write_text("WIDTH = 4.0\n", encoding="utf-8")
        self.assertTrue(cad_generation._generated_child_is_stale(spec, force=False))
        helper.write_text("WIDTH = 3.0\n", encoding="utf-8")
        self.assertFalse(cad_generation._generated_child_is_stale(spec, force=False))

        # A missing render artifact (the package directory) forces a rebuild — gen_step
        # writes no STEP, so the render package, not the STEP, is the freshness anchor.
        # The package is keyed by the entry filename (the generator), not the logical .step.
        shutil.rmtree(cad_catalog.render_package_dir(spec.entry_path))
        self.assertTrue(cad_generation._generated_child_is_stale(spec, force=False))

    def _spec(self, ref: str, kind: str, step_name: str) -> cad_generation.EntrySpec:
        return cad_generation.EntrySpec(
            source_ref=ref,
            cad_ref=ref,
            kind=kind,
            source_path=self.temp_root / f"{ref}.py",
            display_name=ref,
            source="generated",
            script_path=self.temp_root / f"{ref}.py",
            step_path=self.temp_root / step_name,
        )

    def test_rebuild_stale_assembly_children_rebuilds_only_stale_leaf_first(self) -> None:
        assembly = self._spec("robot", "assembly", "robot.step")
        leaf_a = self._spec("leaf_a", "part", "leaf_a.step")
        leaf_b = self._spec("leaf_b", "part", "leaf_b.step")
        all_specs = [assembly, leaf_a, leaf_b]  # parents listed before children

        stale_refs = {"leaf_b"}

        def fake_stale(spec, *, force):
            return force or spec.source_ref in stale_refs

        rebuilt: list[str] = []

        def record_rebuild(child):
            rebuilt.append(child.source_ref)

        with (
            mock.patch.object(cad_generation, "_generated_child_is_stale", side_effect=fake_stale),
            mock.patch.object(cad_generation, "_rebuild_child_in_subprocess", side_effect=record_rebuild),
        ):
            result = cad_generation._rebuild_stale_assembly_children(
                all_specs, [assembly], force=False, logger=None
            )
        # Only the stale leaf is rebuilt; the assembly target itself is not.
        self.assertEqual(["leaf_b"], rebuilt)
        self.assertEqual(["leaf_b"], result)

        # force rebuilds every generated child. Independent leaves run in
        # parallel, so the side-effect call order is not deterministic, but the
        # returned refs follow the deterministic leaf-first (reversed) input order.
        rebuilt.clear()
        with (
            mock.patch.object(cad_generation, "_generated_child_is_stale", side_effect=fake_stale),
            mock.patch.object(cad_generation, "_rebuild_child_in_subprocess", side_effect=record_rebuild),
        ):
            result = cad_generation._rebuild_stale_assembly_children(
                all_specs, [assembly], force=True, logger=None
            )
        self.assertEqual({"leaf_a", "leaf_b"}, set(rebuilt))
        self.assertEqual(["leaf_b", "leaf_a"], result)

    def test_rebuild_stale_assembly_children_noop_without_assembly_target(self) -> None:
        leaf = self._spec("solo", "part", "solo.step")
        with mock.patch.object(
            cad_generation, "_rebuild_child_in_subprocess", side_effect=AssertionError("should not rebuild")
        ):
            result = cad_generation._rebuild_stale_assembly_children(
                [leaf], [leaf], force=True, logger=None
            )
        self.assertEqual([], result)

    # --- Assembly-level no-op skip -------------------------------------------

    def test_is_current_tracks_source_closure(self) -> None:
        step_path = self.temp_root / "asm.step"
        dep = self.temp_root / "asm_src.py"
        dep.write_text("X = 1\n", encoding="utf-8")
        closure = cad_source_hash.closure_for_files(dep, [], base=self.temp_root)

        spec = cad_generation.EntrySpec(
            source_ref="asm",
            cad_ref="asm",
            kind="assembly",
            source_path=self.temp_root / "asm.py",
            display_name="asm",
            source="generated",
            script_path=self.temp_root / "asm.py",
            step_path=step_path,
        )
        # gen_step writes no STEP — the package directory is the freshness anchor, so
        # currency rides on the recorded source closure, not an on-disk STEP hash. The
        # package is keyed by the entry filename (the generator), not the logical .step.
        glb_path = cad_catalog.render_package_dir(spec.entry_path)
        glb_path.mkdir(parents=True, exist_ok=True)
        manifest = {
            "sourceClosureHash": closure.closure_hash,
            "sourceClosureFiles": list(closure.files),
        }

        with mock.patch.object(cad_generation, "read_step_topology_manifest_from_glb", return_value=manifest):
            self.assertTrue(cad_generation._assembly_is_current(spec))

            # A changed composition/source input invalidates the closure.
            dep.write_text("X = 2\n", encoding="utf-8")
            self.assertFalse(cad_generation._assembly_is_current(spec))
            dep.write_text("X = 1\n", encoding="utf-8")
            self.assertTrue(cad_generation._assembly_is_current(spec))

            # A generated part is also a package and shares the closure gate.
            part_spec = replace(spec, source_ref="p", cad_ref="p", kind="part")
            self.assertTrue(cad_generation._assembly_is_current(part_spec))

            # An imported model has no source closure and is not skippable via this gate.
            imported_spec = replace(part_spec, source="imported")
            self.assertFalse(cad_generation._assembly_is_current(imported_spec))

    def test_generated_glb_closure_current_tracks_children(self) -> None:
        # The GLB-reuse gate: a child STEP change must be detected via the recorded
        # source closure even though the assembly STEP is never (re)written.
        step_path = self.temp_root / "asm.step"
        child_step = self.temp_root / "child.step"  # stand-in for a composed child STEP
        child_step.write_text("child v1\n", encoding="utf-8")
        closure = cad_source_hash.closure_for_files(child_step, [], base=self.temp_root)

        spec = cad_generation.EntrySpec(
            source_ref="asm",
            cad_ref="asm",
            kind="assembly",
            source_path=self.temp_root / "asm.py",
            display_name="asm",
            source="generated",
            script_path=self.temp_root / "asm.py",
            step_path=step_path,
        )
        # The package directory is keyed by the entry filename (the generator), not the
        # logical .step.
        glb_path = cad_catalog.render_package_dir(spec.entry_path)
        glb_path.mkdir(parents=True, exist_ok=True)  # package directory
        manifest = {
            "sourceClosureHash": closure.closure_hash,
            "sourceClosureFiles": list(closure.files),
        }
        with mock.patch.object(cad_generation, "read_step_topology_manifest_from_glb", return_value=manifest):
            self.assertTrue(cad_generation._generated_assembly_glb_closure_current(spec))
            # A composed child STEP changing invalidates the GLB (unlike step_hash,
            # this is detected even though asm.step itself was not rewritten).
            child_step.write_text("child v2\n", encoding="utf-8")
            self.assertFalse(cad_generation._generated_assembly_glb_closure_current(spec))

            # A generated part is also a package and shares the closure gate.
            child_step.write_text("child v1\n", encoding="utf-8")
            part_spec = replace(spec, source_ref="p", cad_ref="p", kind="part")
            self.assertTrue(cad_generation._generated_assembly_glb_closure_current(part_spec))

        # An imported model carries no closure and is never blocked by this gate.
        imported_spec = replace(spec, source="imported")
        self.assertTrue(cad_generation._generated_assembly_glb_closure_current(imported_spec))


if __name__ == "__main__":
    unittest.main()
