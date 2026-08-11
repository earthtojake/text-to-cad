import textwrap
import unittest
from pathlib import Path

from cadgen import catalog as cad_catalog
from cadgen._internal import generation as cad_generation
from cadgen.metadata import parse_generator_metadata
from tests.python.support.tmp_root import temporary_directory

STANDALONE_DXF_SOURCE = textwrap.dedent(
    '''
    """Standalone DXF drafting source."""

    import ezdxf


    def gen_dxf():
        doc = ezdxf.new()
        msp = doc.modelspace()
        msp.add_lwpolyline([(0, 0), (40, 0), (40, 20), (0, 20)], close=True)
        return doc
    '''
).strip()


def _write_standalone_source(root: Path, stem: str = "outline") -> Path:
    script_path = root / f"{stem}.py"
    script_path.write_text(STANDALONE_DXF_SOURCE + "\n")
    return script_path


class StandaloneDxfSourceTests(unittest.TestCase):
    def test_metadata_allows_gen_dxf_without_gen_step(self) -> None:
        with temporary_directory(prefix="dxf-skill") as root:
            script_path = _write_standalone_source(Path(root))
            metadata = parse_generator_metadata(script_path)

        assert metadata is not None
        self.assertTrue(metadata.has_gen_dxf)
        self.assertFalse(metadata.has_gen_step)
        self.assertIsNone(metadata.kind)

    def test_metadata_ignores_deprecated_urdf_generators(self) -> None:
        # gen_urdf()/gen_sdf() are hard-deprecated: robot descriptions are
        # authored XML artifacts, so a urdf-only file is not a CAD source.
        with temporary_directory(prefix="dxf-skill") as root:
            script_path = Path(root) / "robot.py"
            script_path.write_text("def gen_urdf():\n    return '<robot/>'\n")
            self.assertIsNone(parse_generator_metadata(script_path))

    def test_explicit_target_resolves_dxf_only_source(self) -> None:
        with temporary_directory(prefix="dxf-skill") as root:
            script_path = _write_standalone_source(Path(root))
            source = cad_catalog.source_from_path(script_path)

            assert source is not None
            self.assertEqual("dxf", source.kind)
            self.assertIsNone(source.step_path)
            self.assertEqual(script_path.with_suffix(".dxf"), source.dxf_path)

    def test_directory_catalog_skips_plain_py_dxf_only_source(self) -> None:
        # Plain `<name>.py` drawing sources stay explicit-target-only; catalog
        # entries require the `.dxf.py` naming.
        with temporary_directory(prefix="dxf-skill") as root:
            _write_standalone_source(Path(root))
            self.assertEqual((), cad_catalog.iter_cad_sources(Path(root)))

    def test_directory_catalog_lists_dxf_generator_entry(self) -> None:
        with temporary_directory(prefix="dxf-skill") as root:
            script_path = _write_standalone_source(Path(root), stem="outline.dxf")
            sources = cad_catalog.iter_cad_sources(Path(root))

            self.assertEqual(1, len(sources))
            self.assertEqual("dxf", sources[0].kind)
            self.assertEqual(script_path, sources[0].script_path)

    def test_generate_dxf_targets_builds_drawing_package(self) -> None:
        with temporary_directory(prefix="dxf-skill") as root:
            script_path = _write_standalone_source(Path(root))

            self.assertEqual(0, cad_generation.generate_dxf_targets([str(script_path)]))

            package_dir = Path(root) / "__cadgen__" / "models" / script_path.name
            self.assertTrue((package_dir / "drawing.json").exists())
            preview_path = package_dir / "preview.glb"
            self.assertTrue(preview_path.exists())
            self.assertGreater(preview_path.stat().st_size, 0)
            # The package caches the render artifact and nothing else -- no DXF, because a
            # generated drawing's DXF is reproducible from its generator on demand.
            self.assertFalse((package_dir / "drawing.dxf").exists())
            # No sibling export unless requested.
            self.assertFalse(script_path.with_suffix(".dxf").exists())

    def test_generate_dxf_targets_writes_sibling_output_on_demand(self) -> None:
        with temporary_directory(prefix="dxf-skill") as root:
            script_path = _write_standalone_source(Path(root))

            self.assertEqual(0, cad_generation.generate_dxf_targets([str(script_path)], write_dxf=True))

            output_path = script_path.with_suffix(".dxf")
            self.assertTrue(output_path.exists())
            self.assertGreater(output_path.stat().st_size, 0)

    def test_rebuild_leaves_sibling_export_untouched(self) -> None:
        # An exported <name>.dxf is a point-in-time deliverable, totally detached from
        # its generator: rebuilds never delete, rewrite, or staleness-track it. Only an
        # explicit re-export refreshes it.
        with temporary_directory(prefix="dxf-skill") as root:
            script_path = _write_standalone_source(Path(root))
            sibling = script_path.with_suffix(".dxf")

            cad_generation.generate_dxf_targets([str(script_path)], write_dxf=True)
            self.assertTrue(sibling.exists())
            exported_bytes = sibling.read_bytes()

            # Source edit -> rebuild -> export untouched, byte for byte.
            script_path.write_text(
                script_path.read_text(encoding="utf-8") + "\n# changed\n", encoding="utf-8"
            )
            cad_generation.generate_dxf_targets([str(script_path)])
            self.assertTrue(sibling.exists())
            self.assertEqual(exported_bytes, sibling.read_bytes())

    def test_generate_dxf_targets_rejects_non_document_payload(self) -> None:
        # Fail closed: an object that only implements saveas is not a drawing and
        # must be rejected, not silently written without validation.
        with temporary_directory(prefix="dxf-skill") as root:
            script_path = Path(root) / "fake.dxf.py"
            script_path.write_text(
                "\n".join(
                    [
                        "class _FakeDxf:",
                        "    def saveas(self, output_path):",
                        "        pass",
                        "def gen_dxf():",
                        "    return {'document': _FakeDxf()}",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(TypeError, "must return an ezdxf document"):
                cad_generation.generate_dxf_targets([str(script_path)])

    def test_generate_dxf_targets_bakes_the_3d_preview(self) -> None:
        # What replaced the SVG snapshot this test used to assert: visual review of a
        # drawing is the 3D flat pattern now, and preview.glb is the package member that
        # carries it — for both the viewer and scripts/snapshot.
        with temporary_directory(prefix="dxf-skill") as root:
            script_path = _write_standalone_source(Path(root))

            self.assertEqual(0, cad_generation.generate_dxf_targets([str(script_path)]))

            package_dir = Path(root) / "__cadgen__" / "models" / script_path.name
            self.assertTrue((package_dir / "preview.glb").is_file())
            self.assertFalse((package_dir / "drawing.svg").exists())


if __name__ == "__main__":
    unittest.main()
