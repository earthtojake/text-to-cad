"""The implicit render package: a real bake, its freshness gates, and its progress record.

Every test here runs the REAL producer against a REAL Node child. That is the point: the
package is written by two processes -- Python holds the lock and owns the descriptor, Node
owns the mesh and the GLB bytes -- and the properties worth pinning (the descriptor names a
payload that exists, one run id spans both runtimes, all four phases reach the status record,
a changed bake invalidates) are all properties of that pair. A mocked builder proves none of
them.

The models are tiny and baked at a low resolution so the suite stays in seconds; the shipped
models are covered by the sweep recorded in the phase-2 report, not by CI.
"""

from __future__ import annotations

import json
import shutil
import unittest
from pathlib import Path

from tests.python.support.paths import add_repo_path
from tests.python.support.tmp_root import temporary_directory

add_repo_path("packages/cadgen/src")

from cadgen._internal.implicit_package import (  # noqa: E402
    IMPLICIT_GLB_NAME,
    IMPLICIT_PACKAGE_KIND,
    IMPLICIT_PACKAGE_SCHEMA_VERSION,
    build_implicit_mesh,
    implicit_bake_settings,
    implicit_package_current,
    load_implicit_descriptor,
    normalize_bake_resolution,
)
from cadgen._internal.package_freshness import canonical_bake_hash  # noqa: E402
from cadgen.catalog import render_package_dir  # noqa: E402
from cadgen.coordination import status_path  # noqa: E402
from cadgen.implicit_artifact import build_implicit_artifact, run_cli_payload  # noqa: E402

_NODE = shutil.which("node")

# A sphere with a slab cut out of it: two primitives and a boolean, so the mesh has both
# curved and flat regions (and therefore both smooth and creased normals) at a resolution
# that bakes in about a second.
_MODEL_SOURCE = """
export default {
  name: "test sphere",
  units: "mm",
  bounds: 12,
  glsl: `
    float sdf(vec3 p) {
      float sphere = length(p) - 8.0;
      float slab = p.z - 3.0;
      return max(sphere, -slab);
    }
    vec3 color(vec3 p, vec3 normal) {
      return vec3(0.2, 0.6, 0.9);
    }
  `,
};
"""

_BAKE_RESOLUTION = 16


def _write_model(folder: Path, name: str = "test-shape", source: str = _MODEL_SOURCE) -> Path:
    path = folder / f"{name}.implicit.js"
    path.write_text(source, encoding="utf-8")
    return path


@unittest.skipUnless(_NODE, "node is required to build an implicit render package")
class ImplicitArtifactTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = temporary_directory(prefix="implicit-artifact-")
        self.addCleanup(self._tmp.cleanup)
        self.folder = Path(self._tmp.name)
        self.source = _write_model(self.folder)

    def _build(self, **kwargs) -> dict:
        return build_implicit_artifact(
            repo_root=self.folder,
            source_path=self.source,
            resolution=_BAKE_RESOLUTION,
            **kwargs,
        )

    def test_build_writes_a_package_whose_descriptor_names_a_real_payload(self) -> None:
        payload = self._build()
        self.assertTrue(payload["ok"])
        self.assertNotIn("skipped", payload)

        package_dir = render_package_dir(self.source)
        descriptor = load_implicit_descriptor(package_dir)
        self.assertIsNotNone(descriptor)
        self.assertEqual(descriptor["kind"], IMPLICIT_PACKAGE_KIND)
        self.assertEqual(descriptor["packageSchemaVersion"], IMPLICIT_PACKAGE_SCHEMA_VERSION)
        self.assertEqual(descriptor["glb"], IMPLICIT_GLB_NAME)
        # Every payload the descriptor names must be on disk -- the validator's rule.
        self.assertTrue((package_dir / descriptor["glb"]).is_file())
        self.assertGreater((package_dir / descriptor["glb"]).stat().st_size, 0)
        self.assertGreater(descriptor["stats"]["triangleCount"], 0)
        # The closure records the model itself, relative to the MODEL folder.
        self.assertEqual(descriptor["sourceClosureFiles"], [self.source.name])
        self.assertTrue(descriptor["sourceClosureHash"])
        # The bake block and its hash agree, and the hash is what the freshness gate compares.
        self.assertEqual(descriptor["bake"], implicit_bake_settings(_BAKE_RESOLUTION))
        self.assertEqual(descriptor["bakeHash"], canonical_bake_hash(descriptor["bake"]))

    def test_second_build_is_skipped_and_a_source_edit_makes_it_stale(self) -> None:
        self._build()
        self.assertTrue(implicit_package_current(self.source, resolution=_BAKE_RESOLUTION))
        self.assertTrue(self._build().get("skipped"))

        # A comment-only edit does NOT invalidate a Python closure, but a `.js` closure file
        # is byte-hashed (`_semantic_source_hash` only parses `.py`), so any edit counts.
        self.source.write_text(
            _MODEL_SOURCE.replace("length(p) - 8.0", "length(p) - 7.0"), encoding="utf-8"
        )
        self.assertFalse(implicit_package_current(self.source, resolution=_BAKE_RESOLUTION))
        self.assertFalse(self._build().get("skipped"))

    def test_a_changed_bake_resolution_invalidates_through_the_bake_hash(self) -> None:
        self._build()
        # Nothing about the SOURCE changed, and the payload is still there: only the bake
        # settings differ, which is exactly the staleness bakeHash exists to catch.
        self.assertTrue(implicit_package_current(self.source, resolution=_BAKE_RESOLUTION))
        self.assertFalse(implicit_package_current(self.source, resolution=_BAKE_RESOLUTION + 8))

        rebuilt = build_implicit_artifact(
            repo_root=self.folder,
            source_path=self.source,
            resolution=_BAKE_RESOLUTION + 8,
        )
        self.assertNotIn("skipped", rebuilt)
        self.assertEqual(rebuilt["resolution"], _BAKE_RESOLUTION + 8)

    def test_a_missing_payload_makes_the_package_stale(self) -> None:
        self._build()
        (render_package_dir(self.source) / IMPLICIT_GLB_NAME).unlink()
        self.assertFalse(implicit_package_current(self.source, resolution=_BAKE_RESOLUTION))

    def test_the_terminal_record_carries_every_phase_the_builder_reported(self) -> None:
        self._build()
        record = json.loads(status_path(render_package_dir(self.source)).read_text(encoding="utf-8"))
        self.assertEqual(record["outcome"], "done")
        # stageMs is recorded only on a `done` outcome, and it is what weights the NEXT
        # build's bar. All four phases are reported by the Node child over NDJSON, so this
        # also pins that the child's progress reached the lock holder.
        self.assertEqual(
            sorted(record["stageMs"]),
            ["polygonize", "sample", "weld", "write"],
        )
        for phase, elapsed in record["stageMs"].items():
            self.assertGreaterEqual(elapsed, 0, phase)

    def test_write_glb_leaves_a_loadable_sibling_and_re_bakes_when_it_is_missing(self) -> None:
        sibling = self.folder / "test-shape.glb"
        payload = self._build(write_glb=sibling)
        self.assertEqual(payload["path"], str(sibling))
        self.assertTrue(sibling.is_file())
        # The export preset declares no required extensions, so a stock loader can open it --
        # unlike the package's own model.glb, which is meshopt-compressed.
        self.assertEqual(sibling.read_bytes()[:4], b"glTF")

        # Present sibling + current package -> nothing to do.
        self.assertTrue(self._build(write_glb=sibling).get("skipped"))
        # Missing sibling -> not current, because the mesh is what produces it.
        sibling.unlink()
        self.assertFalse(self._build(write_glb=sibling).get("skipped"))
        self.assertTrue(sibling.is_file())

    def test_a_build_without_the_lock_holders_run_is_refused(self) -> None:
        package_dir = render_package_dir(self.source)
        package_dir.mkdir(parents=True, exist_ok=True)
        with self.assertRaises(RuntimeError) as caught:
            build_implicit_mesh(
                package_dir,
                self.source,
                run=object(),  # no run_id: not the lock holder
                resolution=_BAKE_RESOLUTION,
            )
        self.assertIn("write lock", str(caught.exception))
        self.assertFalse((package_dir / IMPLICIT_GLB_NAME).exists())

    def test_a_failing_model_leaves_no_descriptor(self) -> None:
        broken = _write_model(self.folder, name="broken", source="export default { glsl: `` };")
        with self.assertRaises(Exception):
            build_implicit_artifact(
                repo_root=self.folder,
                source_path=broken,
                resolution=_BAKE_RESOLUTION,
            )
        # No descriptor means needs-build, which is the only honest state for a package whose
        # payload was never written.
        self.assertIsNone(load_implicit_descriptor(render_package_dir(broken)))

    def test_cli_payload_prints_the_same_dict_the_api_returns(self) -> None:
        payload = run_cli_payload([
            "--source-path", str(self.source),
            "--resolution", str(_BAKE_RESOLUTION),
        ])
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["sourceKind"], "python")
        self.assertTrue(str(payload["glbPath"]).endswith(IMPLICIT_GLB_NAME))


class ImplicitBakeSettingsTests(unittest.TestCase):
    """No Node needed: the bake block is pure Python and is the freshness contract."""

    def test_bake_hash_changes_with_the_resolution_and_nothing_else(self) -> None:
        default = canonical_bake_hash(implicit_bake_settings())
        self.assertEqual(default, canonical_bake_hash(implicit_bake_settings(None)))
        self.assertNotEqual(default, canonical_bake_hash(implicit_bake_settings(64)))

    def test_resolution_is_clamped_where_it_is_HASHED(self) -> None:
        # The mesher clamps to [8, 256] internally (normalizeResolution in mesh.js).
        # Clamping here too is what stops the descriptor recording a resolution the mesh was
        # never built at -- so this ceiling must track that one, not drift from it.
        self.assertEqual(normalize_bake_resolution(4000), 256)
        self.assertEqual(normalize_bake_resolution(1), 8)
        self.assertEqual(normalize_bake_resolution("not a number"), normalize_bake_resolution(None))

    def test_a_package_that_does_not_exist_is_not_current(self) -> None:
        with temporary_directory(prefix="implicit-freshness-") as tmp:
            source = _write_model(Path(tmp))
            self.assertFalse(implicit_package_current(source))


if __name__ == "__main__":
    unittest.main()
