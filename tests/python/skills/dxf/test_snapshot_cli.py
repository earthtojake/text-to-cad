import json
import subprocess
import sys
import unittest

from cadgen.assets import browser_runtime_dir
from pathlib import Path
from unittest import mock

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")

# Job resolution is shared (cadgen.snapshot_cli); `cadgen dxf snapshot`
# (cadgen.cli.dxf_snapshot) is the DXF entrypoint, a GENERATED CLI over
# cadgen.dxf.snapshot. Which kinds the door accepts is declared beside the verbs.
# What is DXF-specific -- resolving a .dxf or a drawing() source to its built package --
# is what these tests cover.
import cadgen.snapshot_cli as snapshot
from cadgen._internal.snapshot_door import DOOR_KINDS
import cadgen.cli.dxf_snapshot as dxf_snapshot_entry


class DxfSnapshotCliTests(unittest.TestCase):
    """A drawing snapshot is an on-demand mesh of the .dxf, then a mesh render.

    The render half is shared with the CAD skill; what is DXF-specific — meshing
    the drawing through the bundled dxf-mesh.mjs one-shot (no package, matching
    the viewer's client-side parse) — is what these tests cover.
    """

    def test_meshes_the_dxf_on_demand(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            dxf = Path(tmp) / "x.dxf"
            dxf.write_text("0\nSECTION\n2\nENTITIES\n0\nENDSEC\n0\nEOF\n")

            def fake_run(cmd, **kwargs):
                out = Path(cmd[cmd.index("--out") + 1])
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_bytes(b"glTF")
                # json.dumps, not %s: a Windows path interpolated raw into a
                # JSON string literal produces invalid escapes ("\\U", "\\c")
                # and the caller's json.loads silently fell back to "no payload".
                return mock.Mock(
                    returncode=0,
                    stdout=json.dumps({"ok": True, "path": str(out)}),
                    stderr="",
                )

            with mock.patch("subprocess.run", side_effect=fake_run):
                resolved = snapshot.drawing_mesh_path(dxf, force=False)
            self.assertTrue(str(resolved).endswith(".glb"))
            self.assertTrue(resolved.is_file())

    def test_a_script_is_not_a_snapshot_input(self) -> None:
        # A .dxf has no derived state a door materializes, so the resolver
        # never ran a generator here again: drawings are made by running their
        # script, and snapshot meshes the DOCUMENT.
        import tempfile

        self.assertFalse(hasattr(snapshot, "generate_dxf_for_snapshot"))
        with tempfile.TemporaryDirectory() as tmp:
            py = Path(tmp) / "x.py"
            py.write_text("def drawing():\n    raise NotImplementedError\n")
            with self.assertRaisesRegex(snapshot.SnapshotError, "must be a .dxf document"):
                snapshot.drawing_mesh_path(py, force=True)

    def test_a_mesh_failure_is_an_error_not_a_blank_image(self) -> None:
        # The one-shot's error (a drawing with nothing renderable at all —
        # dimensioned drawings render as line work since FEEDBACK 14) is relayed
        # verbatim instead of rendering nothing.
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            dxf = Path(tmp) / "x.dxf"
            dxf.write_text("0\nEOF\n")
            failed = mock.Mock(returncode=1, stdout='{"ok": false, "error": "no cut geometry"}', stderr="")
            with mock.patch("subprocess.run", return_value=failed):
                with self.assertRaisesRegex(snapshot.SnapshotError, "no cut geometry"):
                    snapshot.drawing_mesh_path(dxf, force=False)

    def test_rejects_a_non_drawing_input(self) -> None:
        with self.assertRaises(snapshot.SnapshotError):
            snapshot.drawing_mesh_path(Path("/models/part.step"), force=False)

    def test_reports_a_missing_input(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(snapshot.SnapshotError):
                snapshot.drawing_mesh_path(Path(tmp) / "definitely-absent.dxf", force=False)

    def test_section_mode_is_rejected_for_a_drawing(self) -> None:
        # Drawings have no CAD topology, so section has nothing to work with.
        # `--mode` is one string across every door, so section is refused per KIND
        # at resolve time -- which is what keeps the message specific instead of
        # "invalid choice". (`--kinematics` is a different case: it is absent
        # from this door's SIGNATURE, so it never parses at all.)
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            (root / "a.dxf").write_text("0\nSECTION\n", encoding="utf-8")
            with self.assertRaisesRegex(snapshot.SnapshotError, "section mode requires STEP topology"):
                snapshot.resolve_render_job_packet(
                    {"input": "a.dxf", "mode": "section", "outputs": [{"path": "a.png"}]},
                    cwd=root,
                    kinds=snapshot.enabled_kinds(DOOR_KINDS["dxf"]),
                )

    def test_a_drawing_refuses_the_display_settings_made_of_cad_edges(self) -> None:
        import tempfile

        # A drawing's preview is a mesh: it has no CAD edges for Hidden line to draw, and the
        # "hidden" surface style without them is an empty picture.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            (root / "a.dxf").write_text("0\nSECTION\n", encoding="utf-8")
            mesh = root / "drawing.glb"
            mesh.write_bytes(b"glTF")
            kinds = snapshot.enabled_kinds(DOOR_KINDS["dxf"])
            for display, named in (({"mode": "hidden-line"}, r"display\.mode 'hidden-line'"),
                                   ({"mode": "solid", "surfaces": {"style": "hidden"}}, r"display\.surfaces\.style 'hidden'")):
                with self.subTest(display=display), mock.patch.object(snapshot, "drawing_mesh_path", return_value=mesh), \
                        self.assertRaisesRegex(snapshot.SnapshotError, named + r" applies to STEP models only; a\.dxf"):
                    snapshot.resolve_render_job_packet({"input": "a.dxf", "display": display, "outputs": [{"path": "a.png"}]}, cwd=root, kinds=kinds)
            with mock.patch.object(snapshot, "drawing_mesh_path", return_value=mesh):
                packet = snapshot.resolve_render_job_packet({
                    "input": "a.dxf", "display": {"mode": "solid", "surfaces": {"style": "flat"}}, "outputs": [{"path": "a.png"}],
                }, cwd=root, kinds=kinds)
            self.assertEqual({"appearance": "light", "mode": "solid", "surfaces": {"style": "flat"}}, packet["jobs"][0]["display"])

    def test_cadgen_dxf_snapshot_help_names_drawings(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "cadgen.cli", "dxf", "snapshot", "--help"],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.assertEqual("", result.stderr)
        self.assertEqual(0, result.returncode)
        # The help is GENERATED from cadgen.dxf.snapshot's signature, so what it
        # names is what the verb takes: a positional TARGET that accepts .dxf.
        self.assertIn("usage: cadgen dxf snapshot", result.stdout)
        self.assertIn("[TARGET] [OUT]", result.stdout)
        self.assertIn(".dxf", result.stdout)
        self.assertIn("--display", result.stdout)
        self.assertNotIn("--render", result.stdout)
        for absent in ("--kinematics", "--focus", "--input", "--output"):
            self.assertNotIn(absent, result.stdout, f"{absent} is not a drawing's business")

    def test_runtime_is_bundled_beside_the_cli(self) -> None:
        # The skill must carry its own render runtime: it may not reach into the CAD
        # skill's copy, and a published skill ships no node_modules.
        runtime = browser_runtime_dir()
        self.assertTrue((Path(runtime) / "render.html").is_file())
        self.assertTrue((Path(runtime) / "snapshot-render.js").is_file())


if __name__ == "__main__":
    unittest.main()
