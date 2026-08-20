"""Tests for the viewer-facing cadgen.dxf_artifact build/export command.

The build spans two runtimes -- Python runs the generator and holds the lock, a Node child
bakes ``preview.glb`` inside it -- so the cross-runtime tests here spawn a REAL node child.
They skip when node or the JS dependency graph is unavailable. The test split: Python
owns the package as a coordinated
artifact, JS owns everything downstream of "here is geometry", and the geometry itself is
pinned by ``packages/cadjs/src/lib/dxf/previewGlb.test.js``.
"""

import json
import shutil
import struct
import textwrap
import unittest
from pathlib import Path
from unittest import mock

from cadgen import dxf_artifact
from cadgen._internal import drawing_package
from cadgen._internal.node_runtime import NodeBuilderError
from cadgen.coordination.paths import status_path, write_lock_path
from tests.python.support.tmp_root import temporary_directory

DXF_GENERATOR_SOURCE = textwrap.dedent(
    '''
    """Standalone DXF drawing generator."""

    import ezdxf


    def gen_dxf():
        doc = ezdxf.new()
        msp = doc.modelspace()
        msp.add_lwpolyline([(0, 0), (40, 0), (40, 20), (0, 20)], close=True)
        return doc
    '''
).strip()

_NODE = shutil.which("node")


def _node_graph_available() -> bool:
    """The builder needs `three` and `meshoptimizer`, which the published skill runtime does
    not ship (§4.5). Skip rather than fail where they are absent."""
    if not _NODE:
        return False
    packages = Path(drawing_package.__file__).resolve().parents[4]
    return all(
        (packages / "cadjs" / "node_modules" / name).exists()
        for name in ("three", "meshoptimizer")
    )


_NODE_READY = _node_graph_available()


def _glb_json(path: Path) -> dict:
    """The glTF JSON chunk of a .glb, without a GLTFLoader.

    Python has no loader and is not getting one: this asserts the file IS a GLB and declares
    what the viewer's decoder needs, and the JS round trip proves it renders."""
    data = path.read_bytes()
    magic, _version, _length = struct.unpack_from("<III", data, 0)
    assert magic == 0x46546C67, f"not a GLB: {path}"
    chunk_length, chunk_type = struct.unpack_from("<II", data, 12)
    assert chunk_type == 0x4E4F534A, f"first chunk is not JSON: {path}"
    return json.loads(data[20 : 20 + chunk_length].decode("utf-8"))


class DxfArtifactTests(unittest.TestCase):
    def _write_generator(self, root: Path) -> Path:
        script_path = root / "outline.dxf.py"
        script_path.write_text(DXF_GENERATOR_SOURCE + "\n", encoding="utf-8")
        return script_path

    def _package_dir(self, root: Path, name: str) -> Path:
        return root / "__cadgen__" / "models" / name

    @unittest.skipUnless(_NODE_READY, "node + the cadjs dependency graph are required")
    def test_builds_drawing_package_and_skips_when_current(self) -> None:
        with temporary_directory(prefix="dxf-artifact") as root:
            script_path = self._write_generator(Path(root))

            payload = dxf_artifact.build_dxf_artifact(repo_root=Path(root), source_path=script_path)
            self.assertTrue(payload["ok"])
            self.assertNotIn("skipped", payload)
            package_dir = self._package_dir(Path(root), "outline.dxf.py")
            # One payload. The cache holds what was computed; the DXF is exported on demand.
            self.assertTrue((package_dir / "preview.glb").is_file())
            self.assertFalse((package_dir / "drawing.dxf").exists())

            payload = dxf_artifact.build_dxf_artifact(repo_root=Path(root), source_path=script_path)
            self.assertTrue(payload.get("skipped"))

            payload = dxf_artifact.build_dxf_artifact(
                repo_root=Path(root), source_path=script_path, force=True
            )
            self.assertNotIn("skipped", payload)

    def test_rejects_plain_py_generator(self) -> None:
        with temporary_directory(prefix="dxf-artifact") as root:
            script_path = Path(root) / "outline.py"
            script_path.write_text(DXF_GENERATOR_SOURCE + "\n", encoding="utf-8")

            with self.assertRaisesRegex(RuntimeError, "dedicated <name>.dxf.py generator"):
                dxf_artifact.build_dxf_artifact(repo_root=Path(root), source_path=script_path)

    @unittest.skipUnless(_NODE_READY, "node + the cadjs dependency graph are required")
    def test_rebuilds_are_byte_deterministic(self) -> None:
        with temporary_directory(prefix="dxf-artifact") as root:
            script_path = self._write_generator(Path(root))
            package_dir = self._package_dir(Path(root), "outline.dxf.py")

            dxf_artifact.build_dxf_artifact(repo_root=Path(root), source_path=script_path)
            first_glb = (package_dir / "preview.glb").read_bytes()
            dxf_artifact.build_dxf_artifact(repo_root=Path(root), source_path=script_path, force=True)

            # The bake is deterministic, or every rebuild would churn the cached payload.
            self.assertEqual(first_glb, (package_dir / "preview.glb").read_bytes())

    @unittest.skipUnless(_NODE_READY, "node + the cadjs dependency graph are required")
    def test_export_writes_fresh_dxf_with_relocated_identity(self) -> None:
        with temporary_directory(prefix="dxf-artifact") as root:
            script_path = self._write_generator(Path(root))
            export_path = Path(root) / "exports" / "outline.dxf"

            payload = dxf_artifact.build_dxf_artifact(
                repo_root=Path(root), source_path=script_path, export=export_path
            )

            self.assertTrue(payload["ok"])
            self.assertEqual(str(export_path), payload["path"])
            self.assertEqual("outline.dxf", payload["filename"])
            self.assertTrue(export_path.is_file())
            text = export_path.read_text(encoding="utf-8")
            # The identity comment points at the generator relative to the export.
            self.assertIn("cadgen:sourcePath=../outline.dxf.py", text)
            descriptor = json.loads(
                (self._package_dir(Path(root), "outline.dxf.py") / "drawing.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertIn(f"cadgen:sourceHash={descriptor['sourceHash']}", text)


@unittest.skipUnless(_NODE_READY, "node + the cadjs dependency graph are required")
class DrawingPreviewBakeTests(unittest.TestCase):
    """`preview.glb` -- the payload that replaces the browser's DXF parser and mesher."""

    def _build_generated(self, root: Path) -> Path:
        script_path = root / "outline.dxf.py"
        script_path.write_text(DXF_GENERATOR_SOURCE + "\n", encoding="utf-8")
        dxf_artifact.build_dxf_artifact(repo_root=root, source_path=script_path)
        return root / "__cadgen__" / "models" / "outline.dxf.py"

    def _build_imported(self, root: Path) -> Path:
        # An imported .dxf: produced by the generator once, then treated as a plain file the
        # way a vendor drawing dropped in the folder is.
        self._build_generated(root)
        imported = root / "vendor.dxf"
        # Exported on demand, since the package no longer caches a DXF to copy.
        drawing_package.export_drawing_dxf(root / "outline.dxf.py", imported)
        dxf_artifact.build_dxf_artifact(repo_root=root, source_path=imported)
        return root / "__cadgen__" / "models" / "vendor.dxf"

    def test_generated_drawing_bakes_a_loadable_preview(self) -> None:
        with temporary_directory(prefix="dxf-preview") as root:
            package_dir = self._build_generated(Path(root))
            gltf = _glb_json(package_dir / "preview.glb")
            self.assertIn("EXT_meshopt_compression", gltf.get("extensionsRequired", []))
            self.assertEqual(1, len(gltf["nodes"]))
            self.assertEqual("dxf:0", gltf["nodes"][0]["extras"]["cadOccurrenceId"])

    def test_imported_drawing_bakes_the_same_package(self) -> None:
        with temporary_directory(prefix="dxf-preview") as root:
            package_dir = self._build_imported(Path(root))
            descriptor = json.loads((package_dir / "drawing.json").read_text(encoding="utf-8"))
            # Same payloads and same bake; only the provenance differs (a content digest of
            # the imported file instead of a source closure), exactly like imported STEP.
            self.assertEqual("dxf", descriptor["sourceKind"])
            self.assertTrue(descriptor["sourceDigest"])
            self.assertNotIn("sourceClosureHash", descriptor)
            self.assertEqual("preview.glb", descriptor["preview"])
            self.assertTrue((package_dir / "preview.glb").is_file())
            self.assertIn(
                "EXT_meshopt_compression", _glb_json(package_dir / "preview.glb")["extensionsRequired"]
            )

    def test_imported_drawing_rebuilds_when_its_bytes_change(self) -> None:
        with temporary_directory(prefix="dxf-preview") as root:
            self._build_imported(Path(root))
            imported = Path(root) / "vendor.dxf"
            self.assertTrue(drawing_package.drawing_package_current(imported))
            imported.write_text(
                imported.read_text(encoding="utf-8") + "999\nchanged\n", encoding="utf-8"
            )
            self.assertFalse(drawing_package.drawing_package_current(imported))

    def test_one_run_id_and_one_record_span_python_and_node(self) -> None:
        # The whole reason the Python parent holds the lock: the Node child is INSIDE the
        # critical section, reporting into the same run. If the child ever ran under its own
        # id (or its own record) a reader would see two builds, and the second would look
        # like a build nobody was holding a lock for.
        with temporary_directory(prefix="dxf-runid") as root:
            package_dir = self._build_generated(Path(root))
            record = json.loads(status_path(package_dir).read_text(encoding="utf-8"))
            sentinel = write_lock_path(package_dir).read_bytes()[:32].decode("ascii").strip()

            self.assertEqual("done", record["outcome"])
            self.assertEqual(sentinel, record["runId"])
            self.assertEqual("drawing-package", record["kind"])
            # The child's phases are in THIS run's measured stage times, so the next build's
            # bar is weighted over the work both runtimes did.
            for phase in ("generate", "parse", "mesh", "write", "finalize"):
                self.assertIn(phase, record["stageMs"])

    def test_a_node_failure_fails_the_run_and_leaves_no_descriptor(self) -> None:
        # A half-written package must never look current. The descriptor is dropped before
        # the payloads are rewritten and written back only after the child exits 0, so a
        # failed bake reports needs-build rather than rendering a stale or absent preview.
        with temporary_directory(prefix="dxf-failure") as root:
            root_path = Path(root)
            script_path = root_path / "outline.dxf.py"
            script_path.write_text(DXF_GENERATOR_SOURCE + "\n", encoding="utf-8")
            broken = root_path / "broken-builder.mjs"
            broken.write_text(
                'process.stderr.write("no preview for you\\n");\nprocess.exit(1);\n',
                encoding="utf-8",
            )

            with mock.patch.object(
                drawing_package, "node_builder_script", return_value=broken
            ):
                with self.assertRaises(NodeBuilderError):
                    dxf_artifact.build_dxf_artifact(repo_root=root_path, source_path=script_path)

            package_dir = root_path / "__cadgen__" / "models" / "outline.dxf.py"
            self.assertFalse((package_dir / "drawing.json").exists())
            self.assertFalse((package_dir / "preview.glb").exists())
            self.assertFalse(drawing_package.drawing_package_current(script_path))
            record = json.loads(status_path(package_dir).read_text(encoding="utf-8"))
            self.assertEqual("failed", record["outcome"])
            # A failed run teaches the next build's bar nothing.
            self.assertIsNone(record["stageMs"])

    def test_the_gen_cli_is_the_same_producer(self) -> None:
        # `dxf <target>` is the OTHER producer of this package, and it does not go through
        # dxf_artifact. If it wrote a package with no preview, its own no-op fast path would
        # never fire again and the viewer would rebuild on every open -- so the mesh step
        # lives in write_drawing_package, which both producers reach.
        from cadgen._internal.generation import generate_dxf_targets

        with temporary_directory(prefix="dxf-cli") as root:
            root_path = Path(root)
            script_path = root_path / "outline.dxf.py"
            script_path.write_text(DXF_GENERATOR_SOURCE + "\n", encoding="utf-8")

            self.assertEqual(0, generate_dxf_targets([str(script_path)]))
            package_dir = root_path / "__cadgen__" / "models" / "outline.dxf.py"
            self.assertTrue((package_dir / "preview.glb").is_file())
            self.assertTrue(drawing_package.drawing_package_current(script_path))

    def test_a_builder_run_outside_the_lock_is_refused(self) -> None:
        # The Node half of require_write_lock: a run id only reaches the sentinel from inside
        # exclusive(), so a builder invoked by hand cannot forge one.
        with temporary_directory(prefix="dxf-lock") as root:
            package_dir = self._build_generated(Path(root))
            with self.assertRaises(RuntimeError):
                drawing_package.build_drawing_preview(
                    package_dir, dxf_text="0\nSECTION\n", run=_FakeRun("not-the-holder")
                )


class _FakeRun:
    """A BuildRun-shaped object that holds no lock."""

    def __init__(self, run_id: str) -> None:
        self.run_id = run_id

    def phase(self, *args, **kwargs) -> None:
        return None

    def set_total(self, *args, **kwargs) -> None:
        return None

    def advance(self, *args, **kwargs) -> None:
        return None


class DrawingPreviewBakeSettingsTests(unittest.TestCase):
    """The bake block is what the two freshness authorities compare; it must be hashable
    without reading the drawing."""

    def test_settings_are_json_canonicalizable_and_stable(self) -> None:
        settings = drawing_package.drawing_preview_bake_settings()
        self.assertEqual(settings, drawing_package.drawing_preview_bake_settings())
        self.assertEqual(
            settings["format"], drawing_package.DRAWING_PREVIEW_BAKE_FORMAT
        )
        json.dumps(settings, sort_keys=True, allow_nan=False)


if __name__ == "__main__":
    unittest.main()
