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

    from cadgen import build123d as bd
    from cadgen import dxf


    @dxf
    def drawing():
        with bd.BuildSketch() as cut:
            bd.Rectangle(40, 20)
        return cut.sketch


    if __name__ == "__main__":
        drawing()
    '''
).strip()


def _write_standalone_source(root: Path, stem: str = "outline") -> Path:
    script_path = root / f"{stem}.py"
    script_path.write_text(STANDALONE_DXF_SOURCE + "\n", encoding="utf-8")
    return script_path


class StandaloneDxfSourceTests(unittest.TestCase):
    def test_metadata_allows_gen_dxf_without_gen_step(self) -> None:
        with temporary_directory(prefix="dxf-skill") as root:
            script_path = _write_standalone_source(Path(root))
            metadata = parse_generator_metadata(script_path)

        assert metadata is not None
        self.assertEqual("dxf", metadata.format)
        self.assertIsNone(metadata.kind)

    def test_metadata_ignores_deprecated_urdf_generators(self) -> None:
        # gen_urdf()/gen_sdf() are hard-deprecated: robot descriptions are
        # authored XML artifacts, so a urdf-only file is not a CAD source.
        with temporary_directory(prefix="dxf-skill") as root:
            script_path = Path(root) / "robot.py"
            script_path.write_text("def gen_urdf():\n    return '<robot/>'\n", encoding="utf-8")
            self.assertIsNone(parse_generator_metadata(script_path))

    def test_explicit_target_resolves_dxf_only_source(self) -> None:
        with temporary_directory(prefix="dxf-skill") as root:
            script_path = _write_standalone_source(Path(root))
            source = cad_catalog.source_from_path(script_path)

            assert source is not None
            self.assertEqual("dxf", source.kind)
            self.assertIsNone(source.step_path)
            self.assertEqual(script_path.with_suffix(".dxf"), source.dxf_path)

    def test_directory_catalog_lists_any_decorated_dxf_source(self) -> None:
        # Library-first: any plain .py declaring a @dxf model is a first-class
        # drawing entry — the retired .dxf.py naming carried no meaning worth
        # keeping once the decorator is the declaration.
        with temporary_directory(prefix="dxf-skill") as root:
            script_path = _write_standalone_source(Path(root))
            sources = cad_catalog.iter_cad_sources(Path(root))

            self.assertEqual(1, len(sources))
            self.assertEqual("dxf", sources[0].kind)
            self.assertEqual(script_path, sources[0].script_path)

    def test_generate_dxf_targets_always_writes_the_sibling(self) -> None:
        # The .dxf IS the product (design/standalone-viewer.md Phase A): every run
        # writes it, no package exists, and only the output record remains — in
        # the store's records/ tier — to make an unchanged source a no-op.
        with temporary_directory(prefix="dxf-skill") as root:
            script_path = _write_standalone_source(Path(root))

            self.assertEqual(0, cad_generation.generate_dxf_targets([str(script_path)]))

            output_path = script_path.with_suffix(".dxf")
            self.assertTrue(output_path.exists())
            self.assertGreater(output_path.stat().st_size, 0)
            from cadgen._internal.dxf_output import dxf_export_record_path

            self.assertTrue(dxf_export_record_path(script_path.with_suffix('.dxf')).exists())
            self.assertFalse((Path(root) / "__cadgen__").exists())

    def test_unchanged_source_is_a_no_op_and_output_is_deterministic(self) -> None:
        with temporary_directory(prefix="dxf-skill") as root:
            script_path = _write_standalone_source(Path(root))
            sibling = script_path.with_suffix(".dxf")

            cad_generation.generate_dxf_targets([str(script_path)])
            first = sibling.read_bytes()
            first_mtime = sibling.stat().st_mtime_ns

            # Unchanged source: the recorded output verifies, nothing is rewritten.
            cad_generation.generate_dxf_targets([str(script_path)])
            self.assertEqual(first_mtime, sibling.stat().st_mtime_ns)

            # Forced rebuild of identical content produces identical bytes.
            cad_generation.generate_dxf_targets([str(script_path)], force=True)
            self.assertEqual(first, sibling.read_bytes())

    def test_source_edit_regenerates_the_sibling(self) -> None:
        # The sibling is the PRODUCT now, not a detached export: an edited source
        # regenerates it on the next run (the viewer renders this file).
        with temporary_directory(prefix="dxf-skill") as root:
            script_path = _write_standalone_source(Path(root))
            sibling = script_path.with_suffix(".dxf")

            cad_generation.generate_dxf_targets([str(script_path)])
            before = sibling.read_bytes()

            script_path.write_text(
                STANDALONE_DXF_SOURCE.replace("bd.Rectangle(40, 20)", "bd.Rectangle(50, 20)") + "\n",
                encoding="utf-8",
            )
            cad_generation.generate_dxf_targets([str(script_path)])
            self.assertNotEqual(before, sibling.read_bytes())

    def test_an_ezdxf_document_return_fails_the_geometry_contract(self) -> None:
        # A @dxf returns build123d 2D geometry. An ezdxf document is not that,
        # so ordinary validation refuses it — nothing recognizes, converts, or
        # explains what the value might once have meant.
        with temporary_directory(prefix="dxf-skill") as root:
            script_path = Path(root) / "legacy.py"
            script_path.write_text(
                "\n".join(
                    [
                        "import ezdxf",
                        "from cadgen import dxf",
                        "@dxf",
                        "def drawing():",
                        "    doc = ezdxf.new()",
                        "    doc.modelspace().add_lwpolyline(",
                        "        [(0, 0), (40, 0), (40, 20), (0, 20)], close=True",
                        "    )",
                        "    return doc",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(TypeError, "build123d 2D geometry"):
                cad_generation.generate_dxf_targets([str(script_path)])
            self.assertFalse(script_path.with_suffix(".dxf").exists())

    def test_the_two_authorities_answer_different_questions_by_design(self) -> None:
        # The CLI's no-op gate (cadgen._internal.dxf_output) reads the output
        # record to decide whether an EXPLICIT run can skip work. The viewer has
        # no gate at all any more: scripts are not catalog entries, the .dxf
        # renders directly, and detached outputs mean a source edit flips the
        # CLI gate while the drawing on disk keeps rendering untouched.
        from cadgen._internal.dxf_output import dxf_output_current

        with temporary_directory(prefix="dxf-skill") as root:
            script_path = _write_standalone_source(Path(root))
            cad_generation.generate_dxf_targets([str(script_path)])
            self.assertTrue(dxf_output_current(script_path))
            sibling = script_path.with_suffix(".dxf")
            rendered = sibling.read_bytes()

            script_path.write_text(
                STANDALONE_DXF_SOURCE.replace("bd.Rectangle(40, 20)", "bd.Rectangle(60, 20)") + "\n",
                encoding="utf-8",
            )
            self.assertFalse(dxf_output_current(script_path))
            self.assertEqual(rendered, sibling.read_bytes(), "a source edit must not touch the drawing")

            # An explicit run regenerates (the CLI gate is why it is not a
            # no-op), after which the gate is current again.
            cad_generation.generate_dxf_targets([str(script_path)])
            self.assertTrue(dxf_output_current(script_path))
            self.assertNotEqual(rendered, sibling.read_bytes())


if __name__ == "__main__":
    unittest.main()
