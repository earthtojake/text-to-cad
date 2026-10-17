import contextlib
import io
import json
import types
import unittest
from pathlib import Path
from tests.python.support.tree_ids import tokenized
from unittest import mock

from cadgen._internal import generation as cad_generation
from cadgen import catalog as cad_catalog
from cadgen._internal import source_hash as cad_source_hash
from tests.python.support.cad_test_roots import IsolatedCadRoots


IDENTITY_TRANSFORM = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]


class CadGenerationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._isolated_roots = IsolatedCadRoots(self, prefix="cad-generation-")
        tempdir = self._isolated_roots.temporary_cad_directory(prefix="tmp-cad-")
        self._tempdir = tempdir
        self.temp_root = Path(tempdir.name)
        self.relative_dir = self.temp_root.relative_to(Path.cwd()).as_posix()

    def tearDown(self) -> None:
        self._tempdir.cleanup()

    def _cad_ref(self, name: str) -> str:
        return f"{self.relative_dir}/{name}"

    def _spec(self, path: Path):
        """The entry a run builds for ``path``, resolved as ``generate_step_targets`` resolves a target."""
        _, specs = cad_generation._selected_specs_for_targets([str(path)])
        return specs[0]

    def _fixture_tree(self, label: str):
        """A mocked producer publishes a real, complete native result."""
        from build123d import Solid
        from cadgen._internal.component_package import prepare_geometry_component
        from cadgen.store.objects import put_object
        from cadgen.store.trees import put_tree

        prepared = prepare_geometry_component(Solid.make_box(1, 1, 1))
        put_object(prepared["payload"])
        if prepared["topology"] is not None:
            put_object(prepared["topology"])
        entry = prepared["entry"]
        cid = entry["contentHash"][:16]
        tree = {
            "label": label, "entryKind": "part", "units": "mm",
            "components": {cid: entry},
            "occurrences": [{"id": "o1", "name": label, "component": cid,
                             "transform": list(IDENTITY_TRANSFORM)}],
            "links": [],
            "assembly": {"root": {"id": "o1", "name": label, "nodeType": "part", "children": []}},
            "stats": {"occurrenceCount": 1, "linkCount": 0},
        }
        tree = tokenized(tree)[0]
        return put_tree(tree), tree

    def _generated_result(self, spec, scene=None):
        """A mocked producer still delivers its complete, exact job result."""
        from cadgen.daemon.executors import emit_source_result

        tree, _ = self._fixture_tree(spec.step_path.stem)
        emit_source_result(cad_generation._model_for_spec(spec), tree)
        return cad_generation.GeneratedStepResult(spec=spec, scene=scene, tree=tree)

    def _write_step(self, name: str, *, suffix: str = ".step") -> Path:
        step_path = self.temp_root / f"{name}{suffix}"
        step_path.write_text("ISO-10303-21; END-ISO-10303-21;\n", encoding="utf-8")
        return step_path

    def _fake_scene(self, step_path: Path) -> types.SimpleNamespace:
        """A minimal stand-in for an already-parsed imported STEP scene.

        ``source_compound`` avoids the intermediate mesh-compound fallback;
        ``_patch_package_build`` replaces canonical document-tree packaging.
        """
        return types.SimpleNamespace(
            step_path=step_path.expanduser().resolve(),
            source_compound=object(),
        )

    def _patch_package_build(self):
        """Patch canonical imported-document packaging without meshing.

        Returns ``(patcher, calls)`` where ``calls`` records the parsed scene
        that ``build_document_tree`` receives.
        """
        calls: list[dict] = []

        def _fake(
            scene,
            *,
            force=False,
            progress=None,
        ):
            calls.append(
                {
                    "scene": scene,
                    "force": force,
                }
            )
            tree_hash, tree = self._fixture_tree(scene.step_path.stem)
            stats = {
                "occurrences": 1,
                "unique_components": 1,
                "components_built": 1,
                "components_reused": 0,
            }
            return tree_hash, tree, stats

        return (
            mock.patch("cadgen.store.build.build_document_tree", side_effect=_fake),
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
        from cadgen.step_export import export_build123d_step_file

        # A real multi-part STEP on disk standing in for a committed assembly input.
        block_a = Pos(0, 0, 0) * Box(10, 10, 10)
        block_a.label = "block_a"
        block_b = Pos(30, 0, 0) * Box(6, 6, 6)
        block_b.label = "block_b"
        assembly = Compound(children=[block_a, block_b], label="imported_fixture")
        step_path = self.temp_root / "imported_fixture.step"
        export_build123d_step_file(assembly, step_path)
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
            # Self-contained, flat refs into the tree's own components/ dir: the component's
            # BREP and its part's selector table.
            for ref in (str(entry["brep"]), str(entry["selectors"])):
                self.assertTrue(ref.startswith("components/"), ref)
                self.assertNotIn("..", ref)
                self.assertTrue((package_dir / ref).is_file(), f"missing component file {ref}")
        # components/ holds only flat files — no nested __cadgen__ scaffolding.
        self.assertEqual(
            [],
            [child.name for child in (package_dir / "components").iterdir() if child.is_dir()],
        )

    def _generator_script(
        self,
        name: str,
        *,
        with_dxf: bool = False,
        dxf_before_step: bool = False,
    ) -> Path:
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
            "from cadgen import step",
            "@step",
            "def model():",
            "    _record('gen_step')",
            "    return _shape()",
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
        return assembly_path

    def test_generated_part_spec_names_its_unwritten_step(self) -> None:
        script_path = self._generator_script("flat")

        spec = self._spec(script_path)

        self.assertEqual(self._cad_ref("flat"), spec.cad_ref)
        self.assertIsNotNone(spec.step_path)
        self.assertEqual(script_path, spec.source_path)
        self.assertFalse(spec.step_path.exists())

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

        spec = self._spec(script_path)

        self.assertEqual(script_path.with_suffix(".step"), spec.step_path)
        self.assertEqual(self._cad_ref("missing_output"), spec.cad_ref)

    def test_generated_dxf_defaults_output_to_sibling_stem(self) -> None:
        script_path = self._dxf_generator_script("flat")

        spec = self._spec(script_path)

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

        spec = self._spec(script_path)

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
        spec = self._spec(script_path)

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

    def test_an_empty_shape_is_refused_as_the_models_mistake_not_a_crash(self) -> None:
        # build123d asserts on an empty shape's geometry; unchecked, that
        # AssertionError surfaced from inside the STEP export as cadgen's bug.
        from cadgen import analytics

        script_path = self.temp_root / "empty_part.py"
        script_path.write_text(
            "\n".join(
                [
                    "from cadgen import step",
                    "@step",
                    "def model():",
                    "    import build123d",
                    "    return build123d.Part()",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        spec = self._spec(script_path)
        # Caught by hand: assertRaises drops the traceback, which is what telemetry reads.
        try:
            cad_generation.run_script_generator(spec, "step")
        except ValueError as error:
            refusal = error
        else:
            self.fail("an empty shape built")
        self.assertRegex(str(refusal), r"empty_part\.py @step returned an empty shape: it holds no geometry")
        self.assertEqual("refused", analytics.build_failure(refusal))
        self.assertIsNone(analytics.signature(refusal, "build", bugs_only=True))

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

        spec = self._spec(script_path)
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

    def test_a_step_or_stp_target_is_an_imported_document(self) -> None:
        for name, suffix in (("loose", ".step"), ("loose-stp", ".stp")):
            with self.subTest(suffix=suffix):
                step_path = self._write_step(name, suffix=suffix)

                spec = self._spec(step_path)

                self.assertEqual("imported", spec.source)
                self.assertEqual(self._cad_ref(name), spec.cad_ref)
                self.assertEqual(step_path, spec.step_path)

    def test_generation_regenerates_selected_entries_in_supplied_order(self) -> None:
        first_path = self._generator_script("first")
        second_path = self._generator_script("second")
        calls: list[str] = []

        def fake_generate(spec, **_extra):
            calls.append(spec.cad_ref)
            return self._generated_result(spec)

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
            return self._generated_result(spec, scene)

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
        generated_spec = self._spec(script_path)
        direct_spec = self._spec(self._write_step("direct_kind"))

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
                direct_spec,
                imported_manifest,
            )
        )
        self.assertTrue(
            cad_generation._artifact_source_kind_matches_spec(
                direct_spec,
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

        def fake_generate(spec, **_extra):
            calls.append(spec.script_path.resolve())
            return self._generated_result(spec)

        with mock.patch.object(cad_generation, "_generate_step_outputs", side_effect=fake_generate):
            cad_generation.generate_step_targets([str(assembly_path)])

        self.assertEqual([Path(assembly_path).resolve()], calls)

    def test_dxf_generation_rejects_source_without_dxf(self) -> None:
        script_path = self._generator_script("part")

        with self.assertRaisesRegex(ValueError, "is not a @dxf model"):
            cad_generation.generate_dxf_targets([str(script_path)])

    def test_step_generator_does_not_run_sidecars(self) -> None:
        script_path = self._generator_script("flat", with_dxf=True, dxf_before_step=True)
        spec = self._spec(script_path)

        cad_generation.run_script_generator(spec, "step")

        self.assertEqual("gen_step\n", script_path.with_suffix(".calls").read_text(encoding="utf-8"))
        self.assertFalse(script_path.with_suffix(".dxf").exists())
        self.assertFalse(script_path.with_suffix(".step").exists())

    def test_generated_step_outputs_reuses_generated_scene(self) -> None:
        script_path = self._generator_script("flat")
        spec = self._spec(script_path)
        step_path = script_path.with_suffix(".step")
        observed_scene = None

        def fake_outputs(spec_arg, *, preloaded_scene=None, force=False, **_extra):
            nonlocal observed_scene
            observed_scene = preloaded_scene
            self.assertIs(spec, spec_arg)
            return self._generated_result(spec, preloaded_scene)

        with mock.patch.object(cad_generation, "_generate_part_outputs", side_effect=fake_outputs):
            cad_generation._generate_step_outputs(spec)

        self.assertIsNotNone(observed_scene)
        self.assertEqual(step_path.resolve(), observed_scene.step_path)
        # The run's shape, which the tree is built from: no document of it is assembled.
        self.assertIsNotNone(observed_scene.source_compound)
        self.assertEqual("python", observed_scene.source_kind)
        self.assertEqual(cad_generation.python_source_hash(script_path).source_hash, observed_scene.source_hash)
        # gen_step writes no STEP, so there is no on-disk STEP to hash.
        self.assertFalse(step_path.exists())

    def test_normal_python_generation_reuses_current_package(self) -> None:
        script_path = self._generator_script("flat")
        spec = self._spec(script_path)
        tree, _ = self._fixture_tree("flat")

        # A current model reuses its tree: the topology options match, the tree is
        # complete, and its source closure is unchanged -> no run, no remesh; what the
        # model may still owe (its files, its display data) is queued for the run to finish.
        with (
            mock.patch.object(cad_generation, "_checked_source_tree", return_value=tree),
            mock.patch.object(cad_generation, "_existing_topology_artifact_matches_spec_without_scene", return_value=True),
            mock.patch.object(cad_generation, "run_script_generator") as run_generator,
            mock.patch.object(cad_generation, "_generate_part_outputs") as package,
            mock.patch.object(cad_generation, "_Export") as queued,
            ):
            result = cad_generation._generate_step_outputs(spec, force=False)

        run_generator.assert_not_called()
        package.assert_not_called()
        queued.assert_called_once()
        self.assertEqual(queued.call_args.args[:2], (spec, tree))
        self.assertEqual(tree, result.tree)
        self.assertIsNone(result.scene)


    def test_step_toml_target_is_not_supported(self) -> None:
        (self.temp_root / "broken.step.toml").write_text('kind = "part"\n', encoding="utf-8")

        with self.assertRaisesRegex(FileNotFoundError, "not a model script cadgen can build.*python <model>.py"):
            cad_generation.generate_step_targets([str(self.temp_root / "broken.step.toml")])

    def test_direct_step_targets_are_rejected(self) -> None:
        # model-script runs build model scripts only; a STEP document needs no build --
        # every command that reads one compiles its tree on demand.
        step_path = self._write_step("source")

        with self.assertRaisesRegex(ValueError, "builds model scripts only.*is a document"):
            cad_generation.generate_step_targets([str(step_path)])

    def test_a_step_model_returning_none_is_refused(self) -> None:
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
            self._spec(script_path)

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

        spec = self._spec(script_path)

        self.assertIsNotNone(spec.dxf_path)
        self.assertEqual(self.temp_root / "flat.dxf", spec.dxf_path)

    def test_generate_part_outputs_emits_package(self) -> None:
        step_path = self._write_step("selector-output")
        spec = self._spec(step_path)
        scene = self._fake_scene(step_path)
        package_patch, package_calls = self._patch_package_build()

        with mock.patch.object(cad_generation, "load_step_scene_cached", return_value=scene) as load_scene, package_patch:
            cad_generation._generate_part_outputs(spec)

        load_scene.assert_called_once_with(step_path)
        # An imported STEP packages the parsed document itself.
        self.assertEqual(1, len(package_calls))
        self.assertIs(scene, package_calls[0]["scene"])
        self.assertFalse(package_calls[0]["force"])
        self.assertTrue(cad_catalog.result_view_dir(step_path).is_dir())





    def test_generate_part_outputs_uses_preloaded_scene_without_reloading(self) -> None:
        step_path = self._write_step("preloaded")
        spec = self._spec(step_path)
        scene = self._fake_scene(step_path)

        package_patch, package_calls = self._patch_package_build()
        with mock.patch.object(cad_generation, "load_step_scene_cached") as load_scene, package_patch:
            cad_generation._generate_part_outputs(spec, preloaded_scene=scene)

        load_scene.assert_not_called()
        self.assertEqual(1, len(package_calls))
        self.assertIs(scene, package_calls[0]["scene"])
        self.assertTrue(cad_catalog.result_view_dir(step_path).is_dir())


if __name__ == "__main__":
    unittest.main()
