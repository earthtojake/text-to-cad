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
from cadgen._internal.glb_topology import read_step_topology_manifest_from_glb
from cadgen._internal.cache_schema import CACHE_SCHEMA_VERSION
from cadgen._internal.glb_topology import STEP_TOPOLOGY_SCHEMA_VERSION
from cadgen._internal.step_scene import LoadedStepScene, OccurrenceNode, SelectorBundle
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
        unified tree emit skips its ``import_step`` fallback (the tree build
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
            root_name,
            force=False,
            progress=None,
            extra=None,
        ):
            from cadgen.store.build import compound_has_children

            single_component = not compound_has_children(shape)
            entry_kind = "part" if single_component else "assembly"
            from cadgen.store.objects import put_object
            from cadgen.store.trees import put_tree

            calls.append(
                {
                    "single_component": single_component,
                    "force": force,
                    "provenance": {"entryKind": entry_kind},
                    "root_name": root_name,
                }
            )
            surf = put_object(b"SURF\x00fake")
            tree = {
                "label": root_name,
                "entryKind": entry_kind,
                "units": "mm",
                "components": {"c0": {"surf": surf, "brep": surf, "contentHash": "c0"}},
                "occurrences": [{"id": "o1", "name": root_name, "component": "c0", "transform": [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]}],
                "links": [],
                "stats": {"occurrenceCount": 1, "linkCount": 0},
            }
            tree.update(extra or {})
            stats = {
                "occurrences": 1,
                "unique_components": 1,
                "components_built": 1,
                "components_reused": 0,
            }
            return put_tree(tree), tree, stats

        return (
            mock.patch("cadgen.store.build.build_tree_from_compound", side_effect=_fake),
            calls,
        )

    def test_imported_step_assembly_force_writes_component_package(self) -> None:
        """Regression: an imported/committed STEP built with force must actually emit
        the tree. ``_generate_step_outputs`` previously routed only
        ``source == "generated"`` specs into the build pipeline and fell off the end for an
        imported/committed STEP — silently returning None (no package written) while the
        caller still reported success. Model-script runs no longer accept direct STEP targets,
        so this now drives the live on-demand path (`cadgen.step_artifact_cli`) that inspect,
        snapshot, the CAD Viewer, and `cadgen import` all share.
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

        package_dir = cad_catalog.result_view_dir(step_path)
        self.assertFalse(
            (package_dir / "assembly.json").exists(),
            "precondition: the tree must not exist before the build",
        )

        from cadgen.step_artifact_cli import build_step_artifact

        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            payload = build_step_artifact(
                repo_root=self.temp_root,
                step=step_path,
                force=True,
            )
        self.assertTrue(payload["ok"])
        self.assertEqual("assembly", payload["entryKind"])

        # The view is laid out for the tree the build wrote, so resolve it again.
        package_dir = cad_catalog.result_view_dir(step_path)
        descriptor_path = package_dir / "assembly.json"
        self.assertTrue(
            descriptor_path.is_file(),
            "imported STEP --force must write a tree (not a silent no-op)",
        )
        descriptor = json.loads(descriptor_path.read_text(encoding="utf-8"))
        self.assertEqual("assembly-package", descriptor["kind"])
        self.assertEqual("assembly", descriptor.get("entryKind"))
        components = descriptor["components"]
        self.assertTrue(components, "the tree must reference at least one component")
        for entry in components.values():
            ref = str(entry["surf"])
            # Self-contained, flat refs into the tree's own components/ dir.
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
        dict_return: dict[str, str] | None = None,
    ) -> Path:
        # A @step returns a bare shape. ``dict_return`` writes the retired dict
        # envelope instead, for the one test that asserts it is refused.
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
        if dict_return is None:
            return_lines = ["    return _shape()"]
        else:
            return_lines = [
                "    return {",
                "        'shape': _shape(),",
                *[f"        {key!r}: {value!r}," for key, value in dict_return.items()],
                "    }",
            ]
        step_block = [
            "from cadgen import step",
            "@step",
            "def model():",
            "    _record('gen_step')",
            *return_lines,
            "",
        ]
        del dxf_before_step  # gen_dxf lives in a dedicated <name>.py sibling now
        blocks = [prologue, step_block]

        script_path = self.temp_root / f"{name}.py"
        script_path.write_text("\n".join(line for block in blocks for line in block), encoding="utf-8")
        if with_dxf:
            self._dxf_generator_script(name)
        return script_path

    def _dxf_generator_script(self, name: str) -> Path:
        # A dedicated drawing MODEL beside the step model (one model per file, so
        # the drawing gets its own script). Records calls into the SAME
        # `<name>.calls` file as the step generator so cross-generator execution
        # would be visible.
        dxf_path = self.temp_root / f"{name}_drawing.py"
        dxf_path.write_text(
            "\n".join(
                [
                    "from pathlib import Path",
                    "from cadgen import build123d as bd",
                    "from cadgen import dxf",
                    f"CALLS = Path(__file__).with_name('{name}.calls')",
                    "def _record(record_name):",
                    "    with CALLS.open('a', encoding='utf-8') as handle:",
                    "        handle.write(record_name + '\\n')",
                    "@dxf",
                    "def drawing():",
                    "    _record('gen_dxf')",
                    "    with bd.BuildSketch() as cut:",
                    "        bd.Rectangle(10, 5)",
                    "    return {'CUT': cut.sketch}",
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
    ) -> Path:
        # model() returns an inline multi-child Compound literal, which the build
        # packages as occurrences. The instance list controls the count/names of
        # child boxes.
        instance_names = [str(inst.get("name", f"part_{idx}")) for idx, inst in enumerate(instances)]
        shape_expr = (
            "Compound("
            f"children=[Box(1, 1, 1) for _ in {instance_names!r}], "
            f"label={name!r}"
            ")"
        )
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
            "from cadgen import step",
            "@step",
            "def model():",
            "    _record('gen_step')",
            f"    return {shape_expr}",
            "",
        ]
        assembly_path = self.temp_root / f"{name}.py"
        assembly_path.write_text("\n".join(lines), encoding="utf-8")
        if with_dxf:
            self._dxf_generator_script(name)
        return assembly_path

    def test_generated_part_discovery_includes_missing_step_output(self) -> None:
        script_path = self._generator_script("flat")

        specs = [spec for spec in cad_generation.list_entry_specs() if spec.cad_ref == self._cad_ref("flat")]

        self.assertEqual(1, len(specs))
        self.assertIsNotNone(specs[0].step_path)
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
                    "from cadgen import step",
                    "@step",
                    "def model():",
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
            "def model():\n"
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
                    "from cadgen import step",
                    "@step",
                    "def model():",
                    "    return object()",
                    "",
                ]
            ),
            encoding="utf-8",
        )

        spec = next(spec for spec in cad_generation.list_entry_specs() if spec.source_path == script_path)

        self.assertEqual(script_path.with_suffix(".step"), spec.step_path)
        self.assertEqual(self._cad_ref("missing_output"), spec.cad_ref)

    def test_generated_source_rejects_a_dict_return(self) -> None:
        # The dict envelope is gone: a @step returns a bare shape, and any dict
        # -- whatever it carries -- is refused with the decorators to use instead.
        for extra in ({"step_output": "custom/renamed.step"}, {"stl": "flat.stl"}, {}):
            with self.subTest(extra=sorted(extra)):
                self._generator_script("flat", dict_return=extra)
                with self.assertRaisesRegex(ValueError, r"returns a dict.*@stl/@threemf/@glb"):
                    cad_generation.list_entry_specs()

    def test_generated_dxf_defaults_output_to_sibling_stem(self) -> None:
        script_path = self._dxf_generator_script("flat")

        spec = next(spec for spec in cad_generation.list_entry_specs() if spec.source_path == script_path)

        self.assertIsNotNone(spec.dxf_path)
        self.assertEqual(self.temp_root / "flat_drawing.dxf", spec.dxf_path)
        self.assertEqual(self._cad_ref("flat_drawing") + ".dxf", spec.cad_ref)

    def test_explicit_target_rejects_gen_dxf_beside_gen_step(self) -> None:
        script_path = self.temp_root / "flat.py"
        script_path.write_text(
            "\n".join(
                [
                    "from cadgen import step",
                    "@step",
                    "def model():",
                    "    return object()",
                    "",
                    "from cadgen import dxf",
                    "@dxf",
                    "def drawing():",
                    "    return {'document': object()}",
                    "",
                ]
            ),
            encoding="utf-8",
        )

        # A file may hold several models; asking for "the" model of one names none.
        with self.assertRaisesRegex(ValueError, "declares several models"):
            cad_catalog.source_from_path(script_path)

    def test_explicit_dxf_generator_target_rejects_gen_step(self) -> None:
        script_path = self.temp_root / "flat.py"
        script_path.write_text(
            "\n".join(
                [
                    "from cadgen import step",
                    "@step",
                    "def model():",
                    "    return object()",
                    "",
                    "from cadgen import dxf",
                    "@dxf",
                    "def drawing():",
                    "    return {'document': object()}",
                    "",
                ]
            ),
            encoding="utf-8",
        )

        # A file may hold several models; asking for "the" model of one names none.
        with self.assertRaisesRegex(ValueError, "declares several models"):
            cad_catalog.source_from_path(script_path)

    def test_directory_discovery_skips_invalid_generator_sources(self) -> None:
        # A source that cannot be read (here: a syntax error) is skipped with a
        # warning instead of aborting the whole catalog, so unrelated targets keep
        # working.
        invalid_path = self.temp_root / "unmigrated.py"
        invalid_path.write_text(
            "\n".join(
                [
                    "from cadgen import step",
                    "@step",
                    "def model(:",
                    "    return object()",
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
                    "from cadgen import step",
                    "@step",
                    "def model():",
                    "    return object()",
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

        self.assertEqual(("model",), spec.generator_metadata.generator_names)

    def test_subroutine_generator_prints_go_to_stderr_not_stdout(self) -> None:
        # The CLI contract is "stdout carries the result; stderr carries
        # progress". When a generator runs as a SUBROUTINE of another verb
        # (inspect/snapshot/export), its own print() ahead of the verb's JSON
        # broke every `| jq` pipeline — the documented `2>/dev/null` then read
        # as a parse error on a successful inspection. Default: stderr.
        script_path = self.temp_root / "printing_part.py"
        script_path.write_text(
            "\n".join(
                [
                    "from cadgen import step",
                    "@step",
                    "def model():",
                    "    import build123d",
                    "    print('printing_part: 1 box placed')",
                    "    return build123d.Box(1, 1, 1)",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        spec = next(spec for spec in cad_generation.list_entry_specs() if spec.source_path == script_path)

        captured_out, captured_err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(captured_out), contextlib.redirect_stderr(captured_err):
            scene = cad_generation.run_script_generator(spec, "step")
        self.assertIsNotNone(scene)
        self.assertNotIn("printing_part: 1 box placed", captured_out.getvalue())
        self.assertIn("printing_part: 1 box placed", captured_err.getvalue())

        # The direct build flows own stdout and say so explicitly.
        captured_out, captured_err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(captured_out), contextlib.redirect_stderr(captured_err):
            scene = cad_generation.run_script_generator(
                spec, "step", model_prints_to_stdout=True
            )
        self.assertIsNotNone(scene)
        self.assertIn("printing_part: 1 box placed", captured_out.getvalue())

    def test_bare_shape_return_is_supported_for_step_generation(self) -> None:
        script_path = self.temp_root / "bare_part.py"
        script_path.write_text(
            "\n".join(
                [
                    "from cadgen import step",
                    "@step",
                    "def model():",
                    "    import build123d",
                    "    return build123d.Box(1, 1, 1)",
                    "",
                ]
            ),
            encoding="utf-8",
        )

        spec = next(spec for spec in cad_generation.list_entry_specs() if spec.source_path == script_path)
        scene = cad_generation.run_script_generator(spec, "step")

        # A @step run builds the render scene in memory and writes no STEP by default.
        self.assertIsNotNone(spec.step_path)
        self.assertIsNotNone(scene)
        self.assertFalse(script_path.with_suffix(".step").exists())
        self.assertEqual("python", scene.source_kind)
        self.assertEqual(cad_generation.python_source_hash(script_path).source_hash, scene.source_hash)
        self.assertIsNotNone(scene)
        self.assertEqual("python", scene.source_kind)
        self.assertEqual(cad_generation.python_source_hash(script_path).source_hash, scene.source_hash)

    def test_bare_shape_return_is_supported(self) -> None:
        # The CLI stays naming-agnostic: a plain `.py` defining only drawing() is a
        # valid EXPLICIT target. The product is the sibling .dxf, always written.
        # A bare shape is the whole contract for a one-layer drawing: no layer map,
        # no envelope, and the engine puts it on CUT.
        script_path = self.temp_root / "bare_dxf.py"
        script_path.write_text(
            "\n".join(
                [
                    "from cadgen import build123d as bd",
                    "from cadgen import dxf",
                    "@dxf",
                    "def drawing():",
                    "    with bd.BuildSketch() as cut:",
                    "        bd.Rectangle(10, 5)",
                    "    return cut.sketch",
                    "",
                ]
            ),
            encoding="utf-8",
        )

        cad_generation.generate_dxf_targets([str(script_path)])

        from cadgen.store.records import read_record

        # No drawing package exists: the .dxf beside the source is the product,
        # and the drawing's MODEL record (tree: null) is what makes a rerun a no-op.
        written = self.temp_root / "bare_dxf.dxf"
        self.assertTrue(written.exists())
        record = read_record(script_path) or {}
        self.assertIsNone(record.get("tree"))
        self.assertIn(str(written.resolve()), record.get("outputs") or {})

    def test_dxf_generation_always_writes_the_sibling(self) -> None:
        script_path = self._dxf_generator_script("flat")

        cad_generation.generate_dxf_targets([str(script_path)])

        self.assertTrue((self.temp_root / "flat_drawing.dxf").exists())
        from cadgen.store.records import read_record

        self.assertIsNotNone(read_record(script_path), "a drawing is a model: it has a record")

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

    def test_a_dxf_return_that_is_not_geometry_is_refused(self) -> None:
        # There is no drawing envelope any more: a @dxf function returns build123d
        # geometry, so a dict of anything else is a layer map holding the wrong
        # thing. Refused at the emitter, with nothing written.
        script_path = self.temp_root / "projection.py"
        script_path.write_text(
            "\n".join(
                [
                    "from cadgen import dxf",
                    "@dxf",
                    "def drawing():",
                    "    return {'CUT': 'imported-part.step'}",
                    "",
                ]
            ),
            encoding="utf-8",
        )

        with self.assertRaisesRegex(TypeError, "must hold build123d geometry"):
            cad_generation.generate_dxf_targets([str(script_path)])
        self.assertFalse((self.temp_root / "projection.dxf").exists())

    def test_direct_step_is_discovered_as_imported_part(self) -> None:
        self._write_step("loose")

        specs = [spec for spec in cad_generation.list_entry_specs() if spec.cad_ref == self._cad_ref("loose")]

        self.assertEqual(1, len(specs))
        self.assertIsNotNone(specs[0].step_path)
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

        # Generated-vs-imported rides the merged-in source sidecar
        # (_sourceSidecar), never an assembly.json field. A GENERATED spec still
        # requires its sidecar (a sidecar-less package means the model was
        # never generated here); an IMPORTED spec accepts any resolved
        # package — content keying guarantees it is these bytes' render.
        generated_manifest = {"_sourceSidecar": {"sourceKind": "python"}}
        imported_manifest = {}
        self.assertTrue(
            cad_generation._artifact_source_kind_matches_spec(
                generated_spec,
                generated_manifest,
            )
        )
        self.assertFalse(
            cad_generation._artifact_source_kind_matches_spec(
                generated_spec,
                imported_manifest,
            )
        )
        self.assertTrue(
            cad_generation._artifact_source_kind_matches_spec(
                direct_specs[0],
                imported_manifest,
            )
        )
        self.assertTrue(
            cad_generation._artifact_source_kind_matches_spec(
                direct_specs[0],
                generated_manifest,
            )
        )

    def test_step_generation_dispatches_the_assembly_target(self) -> None:
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
            calls.append(spec.script_path.resolve())

        with mock.patch.object(cad_generation, "_generate_step_outputs", side_effect=fake_generate):
            cad_generation.generate_step_targets([str(assembly_path)])

        self.assertEqual([Path(assembly_path).resolve()], calls)

    def test_dxf_generation_rejects_source_without_dxf(self) -> None:
        script_path = self._generator_script("part")

        with self.assertRaisesRegex(ValueError, "is not a @dxf model"):
            cad_generation.generate_dxf_targets([str(script_path)])

    def test_step_generator_does_not_run_sidecars(self) -> None:
        script_path = self._generator_script("flat", with_dxf=True, dxf_before_step=True)
        spec = next(spec for spec in cad_generation.list_entry_specs() if spec.cad_ref == self._cad_ref("flat"))

        cad_generation.run_script_generator(spec, "step")

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

        # A current model reuses its tree: the topology options match, the tree is
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

        # `.py` drawings are their own catalog entries, keyed with the `.dxf`
        # suffix so they never collide with the same-stem STEP entry.
        self.assertIn(self._cad_ref("flat"), cad_refs)
        self.assertIn(self._cad_ref("robot"), cad_refs)
        self.assertIn(self._cad_ref("flat_drawing") + ".dxf", cad_refs)
        self.assertIn(self._cad_ref("robot_drawing") + ".dxf", cad_refs)

    def test_step_toml_target_is_not_supported(self) -> None:
        (self.temp_root / "broken.step.toml").write_text('kind = "part"\n', encoding="utf-8")

        with self.assertRaisesRegex(FileNotFoundError, "Python generator or STEP/STP file path"):
            cad_generation.generate_step_targets([str(self.temp_root / "broken.step.toml")])

    def test_direct_step_targets_are_rejected(self) -> None:
        # model-script runs build model() sources only; an imported STEP gets its render
        # artifacts on demand (inspect/snapshot/viewer) or via cadgen import.
        step_path = self._write_step("source")

        with self.assertRaisesRegex(ValueError, "builds @step Python sources only"):
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
                    "from cadgen import step",
                    "@step",
                    "def model():",
                    "    return None",
                ]
            )
            + "\n", encoding="utf-8"
        )

        with self.assertRaisesRegex(ValueError, "must return a build123d shape"):
            cad_generation.list_entry_specs()

    def test_decorated_dxf_scripts_are_first_class_entries(self) -> None:
        # Library-first: any plain .py declaring a @dxf model is a drawing entry
        # (the old rule keyed drawing-entry status to the retired .dxf.py name).
        script_path = self.temp_root / "flat.py"
        script_path.write_text(
            "\n".join(
                [
                    "from cadgen import dxf",
                    "@dxf",
                    "def drawing():",
                    "    return {'document': object()}",
                    "",
                ]
            ),
            encoding="utf-8",
        )

        specs = cad_generation.list_entry_specs()

        spec = next(spec for spec in specs if spec.source_path == script_path)
        self.assertIsNotNone(spec.dxf_path)
        self.assertEqual(self.temp_root / "flat.dxf", spec.dxf_path)

    def test_imported_step_defaults_to_part(self) -> None:
        self._write_step("imported")

        specs = [spec for spec in cad_generation.list_entry_specs() if spec.cad_ref == self._cad_ref("imported")]

        self.assertEqual(1, len(specs))
        self.assertIsNotNone(specs[0].step_path)

    def test_imported_stp_defaults_to_part(self) -> None:
        self._write_step("imported-stp", suffix=".stp")

        specs = [spec for spec in cad_generation.list_entry_specs() if spec.cad_ref == self._cad_ref("imported-stp")]

        self.assertEqual(1, len(specs))
        self.assertIsNotNone(specs[0].step_path)

    def test_imported_step_specifies_no_mesh_tolerances(self) -> None:
        # Nothing specified is ``None``, which is what lets the adaptive
        # resolver supply the values. There is no default-value sentinel.
        self._write_step("imported-mesh")

        specs = [spec for spec in cad_generation.list_entry_specs() if spec.cad_ref == self._cad_ref("imported-mesh")]

        self.assertEqual(1, len(specs))
        self.assertIsNone(specs[0].mesh_tolerance)
        self.assertIsNone(specs[0].mesh_angular_tolerance)

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
        # A part emits a single-component view directory; the build path returns no
        # whole-model selector bundle (selectors are extracted on demand by inspect).
        self.assertEqual(1, len(package_calls))
        self.assertTrue(package_calls[0]["single_component"])
        self.assertTrue(cad_catalog.result_view_dir(step_path).is_dir())
        self.assertIsNone(result.selector_bundle)





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
        self.assertTrue(cad_catalog.result_view_dir(step_path).is_dir())

    # --- Incremental-regen freshness gate (D) --------------------------------

    def _write_part_with_dependency(self, prefix: str) -> tuple[Path, Path]:
        """A generated part whose generator imports a sibling helper module, so
        its captured source closure spans more than its own file."""
        helper = self.temp_root / f"{prefix}_dims.py"
        helper.write_text("WIDTH = 3.0\n", encoding="utf-8")
        script = self.temp_root / f"{prefix}.py"
        script.write_text(
            f"import {prefix}_dims as dims\n"
            "from cadgen import step\n"
            "@step\n"
            "def model():\n"
            "    import build123d\n"
            "    return build123d.Box(dims.WIDTH, 2.0, 1.0)\n",
            encoding="utf-8",
        )
        return script, helper

    def _part_spec(self, script: Path) -> cad_generation.EntrySpec:
        _all, selected = cad_generation._selected_specs_for_targets([str(script)])
        return selected[0]



    def _spec(self, ref: str, step_name: str) -> cad_generation.EntrySpec:
        return cad_generation.EntrySpec(
            source_ref=ref,
            cad_ref=ref,
            source_path=self.temp_root / f"{ref}.py",
            display_name=ref,
            source="generated",
            script_path=self.temp_root / f"{ref}.py",
            step_path=self.temp_root / step_name,
        )

if __name__ == "__main__":
    unittest.main()
