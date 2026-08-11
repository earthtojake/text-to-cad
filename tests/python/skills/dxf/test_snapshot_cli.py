import importlib.util
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support.paths import add_repo_path, repo_path

add_repo_path("skills/dxf/scripts")
add_repo_path("packages/cadgen/src")

# The CLI is shared (cadgen.snapshot_cli); this skill's entrypoint declares that it accepts
# drawings and where its runtime lives. What is DXF-specific -- resolving a .dxf or a
# gen_dxf() source to its built package -- is what these tests cover.
import cadgen.snapshot_cli as snapshot

# Loaded BY PATH, not by module name: every skill names its entry package `snapshot`, so
# `import snapshot.__main__` resolves to whichever skill's scripts dir landed on sys.path
# first. With the CAD snapshot tests in the same process that is CAD's, and this test then
# silently asserts against the wrong skill's kinds.
_dxf_entry_spec = importlib.util.spec_from_file_location(
    "dxf_skill_snapshot_entry",
    Path(repo_path("skills/dxf/scripts/snapshot/__main__.py")),
)
dxf_snapshot_entry = importlib.util.module_from_spec(_dxf_entry_spec)
_dxf_entry_spec.loader.exec_module(dxf_snapshot_entry)


class DxfSnapshotCliTests(unittest.TestCase):
    """A drawing snapshot is a package build followed by a mesh render.

    The render half is cadgen.snapshot_core, shared with the CAD skill, so these tests
    cover only what is specific here: that the input is resolved to the package's
    preview.glb, and that drawing-shaped inputs are the ones accepted.
    """

    def test_renders_the_packages_preview_glb(self) -> None:
        payload = {"previewPath": "models/drawings/dxf/__cadgen__/models/x.dxf/preview.glb"}
        with mock.patch.object(snapshot, "build_dxf_artifact", return_value=payload) as build:
            with mock.patch.object(Path, "is_file", return_value=True):
                resolved = snapshot.drawing_preview_path(Path("/models/x.dxf"), force=False)

        self.assertTrue(str(resolved).endswith("preview.glb"))
        self.assertFalse(build.call_args.kwargs["force"])

    def test_force_reaches_the_package_build(self) -> None:
        payload = {"previewPath": "p/preview.glb"}
        with mock.patch.object(snapshot, "build_dxf_artifact", return_value=payload) as build:
            with mock.patch.object(Path, "is_file", return_value=True):
                snapshot.drawing_preview_path(Path("/models/x.dxf"), force=True)

        self.assertTrue(build.call_args.kwargs["force"])

    def test_a_package_without_a_preview_is_an_error(self) -> None:
        # Rendering a package that predates preview.glb would silently show nothing;
        # saying so is better than a blank image.
        with mock.patch.object(snapshot, "build_dxf_artifact", return_value={"ok": True}):
            with mock.patch.object(Path, "is_file", return_value=True):
                with self.assertRaises(snapshot.SnapshotError):
                    snapshot.drawing_preview_path(Path("/models/x.dxf"), force=False)

    def test_rejects_a_non_drawing_input(self) -> None:
        with self.assertRaises(snapshot.SnapshotError):
            snapshot.drawing_preview_path(Path("/models/part.step"), force=False)

    def test_reports_a_missing_input(self) -> None:
        with self.assertRaises(snapshot.SnapshotError):
            snapshot.drawing_preview_path(Path("/models/definitely-absent.dxf"), force=False)

    def test_section_mode_is_rejected_for_a_drawing(self) -> None:
        # Drawings have no CAD topology, so section has nothing to work with. The shared
        # CLI accepts the flag for every skill and refuses it per KIND at resolve time,
        # which is what keeps the message specific instead of "invalid choice".
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            (root / "a.dxf").write_text("0\nSECTION\n", encoding="utf-8")
            with self.assertRaisesRegex(snapshot.SnapshotError, "section mode requires STEP topology"):
                snapshot.resolve_render_job_packet(
                    {"input": "a.dxf", "mode": "section", "outputs": [{"path": "a.png"}]},
                    cwd=root,
                    kinds=snapshot.enabled_kinds(dxf_snapshot_entry.KINDS),
                )

    def test_scripts_snapshot_directory_invokes_cli(self) -> None:
        skill_root = repo_path("skills/dxf")
        result = subprocess.run(
            [sys.executable, "scripts/snapshot", "--help"],
            cwd=skill_root,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.assertEqual("", result.stderr)
        self.assertEqual(0, result.returncode)
        self.assertIn("Usage:", result.stdout)
        self.assertIn(".dxf", result.stdout)

    def test_runtime_is_bundled_beside_the_cli(self) -> None:
        # The skill must carry its own render runtime: it may not reach into the CAD
        # skill's copy, and a published skill ships no node_modules.
        runtime = repo_path("skills/dxf/scripts/snapshot/runtime")
        self.assertTrue((Path(runtime) / "render.html").is_file())
        self.assertTrue((Path(runtime) / "snapshot-render.js").is_file())


if __name__ == "__main__":
    unittest.main()
