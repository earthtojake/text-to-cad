import unittest
from pathlib import Path

from cadpy_common.step_metadata import (
    TEXT_TO_CAD_GENERATOR,
    inject_text_to_cad_step_metadata,
    read_text_to_cad_step_metadata,
)
from tests.python.support.tmp_root import temporary_directory


MINIMAL_STEP = """ISO-10303-21;
HEADER;
FILE_DESCRIPTION(('Open CASCADE Model'),'2;1');
ENDSEC;
DATA;
#1=PRODUCT_DEFINITION('design','',#2,#3);
#4=PRODUCT_DEFINITION_SHAPE('','',#1);
#5=SHAPE_REPRESENTATION('',(#6),#7);
#7=(GEOMETRIC_REPRESENTATION_CONTEXT(3) REPRESENTATION_CONTEXT('Context #1','3D'));
ENDSEC;
END-ISO-10303-21;
"""


class TextToCadStepMetadataTests(unittest.TestCase):
    def test_injects_and_reads_text_to_cad_metadata(self) -> None:
        with temporary_directory(prefix="cad-step-metadata-") as temp_dir:
            step_path = Path(temp_dir) / "fixture.step"
            step_path.write_text(MINIMAL_STEP, encoding="utf-8")

            inject_text_to_cad_step_metadata(
                step_path,
                entry_kind="assembly",
                source_hash="source-hash-123",
            )

            metadata = read_text_to_cad_step_metadata(step_path)
            self.assertEqual(TEXT_TO_CAD_GENERATOR, metadata.get("generator"))
            self.assertEqual("assembly", metadata.get("entryKind"))
            self.assertEqual("source-hash-123", metadata.get("sourceHash"))
            step_text = step_path.read_text(encoding="utf-8")
            self.assertIn("PROPERTY_DEFINITION('cadpy metadata','cadpy:entryKind'", step_text)

    def test_reads_tail_metadata_without_full_file_scan(self) -> None:
        with temporary_directory(prefix="cad-step-metadata-tail-") as temp_dir:
            step_path = Path(temp_dir) / "large-fixture.step"
            metadata_block = "\n".join(
                [
                    "#100=DESCRIPTIVE_REPRESENTATION_ITEM('cadpy:generator','cadpy');",
                    "#101=REPRESENTATION('cadpy:generator',(#100),#7);",
                    "#102=PROPERTY_DEFINITION('cadpy metadata','cadpy:generator',#1);",
                    "#103=PROPERTY_DEFINITION_REPRESENTATION(#102,#101);",
                    "#104=DESCRIPTIVE_REPRESENTATION_ITEM('cadpy:entryKind','assembly');",
                    "#105=REPRESENTATION('cadpy:entryKind',(#104),#7);",
                    "#106=PROPERTY_DEFINITION('cadpy metadata','cadpy:entryKind',#1);",
                    "#107=PROPERTY_DEFINITION_REPRESENTATION(#106,#105);",
                    "#112=DESCRIPTIVE_REPRESENTATION_ITEM('cadpy:sourceHash','source-hash-tail');",
                    "#113=REPRESENTATION('cadpy:sourceHash',(#112),#7);",
                    "#114=PROPERTY_DEFINITION('cadpy metadata','cadpy:sourceHash',#1);",
                    "#115=PROPERTY_DEFINITION_REPRESENTATION(#114,#113);",
                ]
            )
            step_path.write_text(
                "ISO-10303-21;\nDATA;\n"
                + ("#9=PRODUCT('padding','padding','',(#7));\n" * 40000)
                + metadata_block
                + "\nENDSEC;\nEND-ISO-10303-21;\n",
                encoding="utf-8",
            )

            metadata = read_text_to_cad_step_metadata(step_path)

            self.assertEqual(TEXT_TO_CAD_GENERATOR, metadata.get("generator"))
            self.assertEqual("assembly", metadata.get("entryKind"))
            self.assertEqual("source-hash-tail", metadata.get("sourceHash"))


if __name__ == "__main__":
    unittest.main()
