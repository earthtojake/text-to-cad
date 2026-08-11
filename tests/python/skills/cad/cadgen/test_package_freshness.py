import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from cadgen._internal import drawing_package, generation
from cadgen._internal.component_package import PACKAGE_KIND
from cadgen._internal.drawing_package import (
    DRAWING_PACKAGE_KIND,
    DRAWING_PACKAGE_SCHEMA_VERSION,
    drawing_package_current,
    drawing_preview_bake_settings,
)
from cadgen._internal.glb_topology import read_step_topology_manifest_from_glb
from cadgen._internal.package_freshness import (
    ASSEMBLY_PACKAGE_SCHEMA_VERSION,
    canonical_bake_hash,
)
from cadgen._internal.source_hash import closure_for_files

# Sentinel for "remove this key from the descriptor entirely".
_DROP = object()


def _write_package(model_dir: Path, entry_name: str, descriptor: dict) -> Path:
    package_dir = model_dir / "__cadgen__" / "models" / entry_name
    (package_dir / "components").mkdir(parents=True)
    (package_dir / "assembly.json").write_text(json.dumps(descriptor), encoding="utf-8")
    return package_dir


class DirAwareManifestReaderTests(unittest.TestCase):
    def test_package_directory_returns_descriptor(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            descriptor = {"kind": PACKAGE_KIND, "sourceKind": "python", "schemaVersion": 2}
            package_dir = _write_package(root, "part.step.py", descriptor)
            manifest = read_step_topology_manifest_from_glb(package_dir)
            self.assertIsInstance(manifest, dict)
            self.assertEqual(manifest.get("kind"), PACKAGE_KIND)

    def test_directory_without_descriptor_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            self.assertIsNone(read_step_topology_manifest_from_glb(Path(temp)))


class PackageFreshnessGateTests(unittest.TestCase):
    def _generated_spec(self, model_dir: Path) -> generation.EntrySpec:
        script = model_dir / "part.step.py"
        script.write_text("def gen_step():\n    return None\n", encoding="utf-8")
        return generation.EntrySpec(
            source_ref="part.step.py",
            cad_ref="part",
            kind="assembly",
            source_path=script,
            display_name="part",
            source="generated",
            step_path=model_dir / "part.step",
            script_path=script,
        )

    def test_assembly_glb_package_current_keys_by_entry_filename(self) -> None:
        # The package lives at __cadgen__/models/part.step.py (entry filename);
        # keying by the logical step path (part.step) must not be required.
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            spec = self._generated_spec(root)
            package_dir = _write_package(
                root,
                "part.step.py",
                {
                    "kind": PACKAGE_KIND,
                    "components": {"abc": {"glb": "components/abc.glb"}},
                },
            )
            (package_dir / "components" / "abc.glb").write_bytes(b"glTF-fake")
            self.assertTrue(generation._assembly_glb_package_current(spec))

    def test_assembly_glb_package_current_false_when_component_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            spec = self._generated_spec(root)
            _write_package(
                root,
                "part.step.py",
                {
                    "kind": PACKAGE_KIND,
                    "components": {"abc": {"glb": "components/abc.glb"}},
                },
            )
            self.assertFalse(generation._assembly_glb_package_current(spec))

    def test_package_descriptor_matches_spec_returns_none_without_package(self) -> None:
        # No package on disk: the gate must fall back to the monolith validator
        # rather than deciding freshness itself.
        with tempfile.TemporaryDirectory() as temp:
            spec = self._generated_spec(Path(temp))
            self.assertIsNone(generation._package_descriptor_matches_spec(spec))


class ProducerGateMirrorsTheViewerTests(unittest.TestCase):
    """The producer's currency predicate is the OTHER freshness authority: it decides
    whether a build no-ops. A gate the viewer makes and this one does not turns a stale
    package into a silent `ready`; a gate this one makes and the viewer does not rebuilds
    forever. These pin the schema-version and bake gates on this side."""

    def _spec(self, model_dir: Path) -> generation.EntrySpec:
        script = model_dir / "part.step.py"
        script.write_text("def gen_step():\n    return None\n", encoding="utf-8")
        return generation.EntrySpec(
            source_ref="part.step.py",
            cad_ref="part",
            kind="assembly",
            source_path=script,
            display_name="part",
            source="generated",
            # No .step on disk: this entry's artifact IS the package.
            step_path=model_dir / "part.step",
            script_path=script,
        )

    def _descriptor(self, options) -> dict:
        return {
            "kind": PACKAGE_KIND,
            "packageSchemaVersion": ASSEMBLY_PACKAGE_SCHEMA_VERSION,
            "sourceKind": "python",
            "components": {"abc": {"glb": "components/abc.glb"}},
            "mesh": {
                "linearDeflection": options.linear_deflection,
                "angularDeflection": options.angular_deflection,
                "relative": options.relative,
            },
            "edgeRendering": {"visibilityClasses": list(options.edge_visibility_classes)},
        }

    def _match(self, descriptor: dict) -> bool:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            spec = self._spec(root)
            _write_package(root, "part.step.py", descriptor)
            return generation._package_descriptor_matches_spec(spec, self.options)

    def setUp(self) -> None:
        from cadgen._internal.step_scene import SelectorOptions

        self.options = SelectorOptions()

    def test_a_well_formed_package_descriptor_is_current(self) -> None:
        self.assertTrue(self._match(self._descriptor(self.options)))

    def test_missing_schema_version_is_not_current(self) -> None:
        descriptor = self._descriptor(self.options)
        del descriptor["packageSchemaVersion"]
        self.assertFalse(self._match(descriptor))

    def test_older_schema_version_is_not_current(self) -> None:
        descriptor = self._descriptor(self.options)
        descriptor["packageSchemaVersion"] = ASSEMBLY_PACKAGE_SCHEMA_VERSION - 1
        self.assertFalse(self._match(descriptor))

    def test_recorded_bake_hash_is_not_current_because_step_bakes_nothing(self) -> None:
        descriptor = self._descriptor(self.options)
        descriptor["bakeHash"] = canonical_bake_hash({"detailMode": "full"})
        self.assertFalse(self._match(descriptor))


class DrawingPackageCurrencyGateTests(unittest.TestCase):
    """Same two gates on the drawing package's producer predicate."""

    def _write(self, root: Path, **overrides) -> Path:
        script = root / "outline.dxf.py"
        script.write_text("def gen_dxf():\n    return None\n", encoding="utf-8")
        package_dir = root / "__cadgen__" / "models" / "outline.dxf.py"
        package_dir.mkdir(parents=True)
        (package_dir / "drawing.dxf").write_text("0\nEOF\n", encoding="utf-8")
        (package_dir / "preview.glb").write_bytes(b"glTF\x02\x00\x00\x00")
        (package_dir / "geometry.json").write_text("{}", encoding="utf-8")
        closure = closure_for_files(script, [], base=root)
        descriptor = {
            "kind": DRAWING_PACKAGE_KIND,
            "packageSchemaVersion": DRAWING_PACKAGE_SCHEMA_VERSION,
            "sourceKind": "python",
            "sourcePath": script.name,
            "dxf": "drawing.dxf",
            "preview": "preview.glb",
            "geometry": "geometry.json",
            "bakeHash": canonical_bake_hash(drawing_preview_bake_settings()),
            "sourceClosureHash": closure.closure_hash,
            "sourceClosureFiles": list(closure.files),
        }
        descriptor.update(overrides)
        for key, value in list(descriptor.items()):
            if value is _DROP:
                del descriptor[key]
        (package_dir / "drawing.json").write_text(json.dumps(descriptor), encoding="utf-8")
        return script

    def test_well_formed_package_is_current(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            script = self._write(Path(temp))
            self.assertTrue(drawing_package_current(script))

    def test_missing_schema_version_is_not_current(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            script = self._write(Path(temp), packageSchemaVersion=_DROP)
            self.assertFalse(drawing_package_current(script))

    def test_wrong_schema_version_is_not_current(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            script = self._write(
                Path(temp), packageSchemaVersion=DRAWING_PACKAGE_SCHEMA_VERSION + 1
            )
            self.assertFalse(drawing_package_current(script))

    def test_a_different_bake_is_not_current(self) -> None:
        # The preview bake IS a freshness input now: preview.glb froze a thickness and a
        # bend state, and no other signal can see either change.
        with tempfile.TemporaryDirectory() as temp:
            script = self._write(Path(temp), bakeHash=canonical_bake_hash({"thicknessMm": 3.0}))
            self.assertFalse(drawing_package_current(script))

    def test_missing_bake_hash_is_not_current(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            script = self._write(Path(temp), bakeHash=_DROP)
            self.assertFalse(drawing_package_current(script))

    def test_a_changed_bake_format_is_not_current(self) -> None:
        # Drive it through the real setting rather than a hand-written hash: an edit to the
        # producer's bake must invalidate packages built under the old one, in this
        # authority AND in the viewer's (viewer/server_py/tests/test_artifact.py pins the
        # other half).
        #
        # The format is now the ONLY thing in the bake block. Thickness used to sit here as a
        # frozen 2.0 mm; it is a render-time scale on the baked prism now, so changing it
        # must NOT invalidate a package -- a slider cannot make a cache stale.
        with tempfile.TemporaryDirectory() as temp:
            script = self._write(Path(temp))
            self.assertTrue(drawing_package_current(script))
            with mock.patch.object(
                drawing_package, "DRAWING_PREVIEW_BAKE_FORMAT", "dxf-preview-glb-vNEXT"
            ):
                self.assertFalse(drawing_package_current(script))

    def test_missing_preview_glb_is_not_current(self) -> None:
        # The package carries two payloads with different jobs; a missing render artifact
        # has to be as stale as a missing exchange artifact, or the CLI reports "current"
        # over a package the viewer cannot render.
        with tempfile.TemporaryDirectory() as temp:
            script = self._write(Path(temp))
            (Path(temp) / "__cadgen__" / "models" / "outline.dxf.py" / "preview.glb").unlink()
            self.assertFalse(drawing_package_current(script))

    def test_descriptor_naming_no_preview_is_not_current(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            script = self._write(Path(temp), preview=_DROP)
            self.assertFalse(drawing_package_current(script))


class TopologySidecarGateTests(unittest.TestCase):
    def _match(self, manifest, descriptor):
        from cadgen.step_artifacts import _topology_sidecar_matches_descriptor

        return _topology_sidecar_matches_descriptor(manifest, descriptor)

    def test_matches_on_same_closure_regardless_of_mesh_drift(self) -> None:
        descriptor = {"sourceClosureHash": "abc", "mesh": {"linearDeflection": 1.0}}
        manifest = {"sourceClosureHash": "abc", "mesh": {"linearDeflection": 2.0}}
        self.assertTrue(self._match(manifest, descriptor))

    def test_rejects_closure_mismatch(self) -> None:
        self.assertFalse(
            self._match({"sourceClosureHash": "old"}, {"sourceClosureHash": "new"})
        )

    def test_rejects_when_no_provenance_recorded(self) -> None:
        self.assertFalse(self._match({}, {}))

    def test_imported_entry_matches_on_step_hash(self) -> None:
        self.assertTrue(
            self._match({"stepHash": "s1"}, {"stepHash": "s1"})
        )
        self.assertFalse(
            self._match({"stepHash": "s1"}, {"stepHash": "s2"})
        )

    def test_rejects_non_dict_manifest(self) -> None:
        self.assertFalse(self._match(None, {"sourceClosureHash": "abc"}))


if __name__ == "__main__":
    unittest.main()
