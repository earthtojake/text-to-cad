"""``/__cad/drawings-of``: the sheets that document a model, found by header."""

from __future__ import annotations

import unittest
from pathlib import Path

import ezdxf

from cadgen.viewer.drawing_links import drawings_of, dxf_source_model
from tests.python.support.tmp_root import temporary_directory


def _dxf(path: Path, source: str | None) -> None:
    doc = ezdxf.new("R2010")
    if source:
        doc.header.custom_vars.append("CADGEN_SOURCE", source)
    doc.modelspace().add_line((0, 0), (1, 1))
    path.parent.mkdir(parents=True, exist_ok=True)
    doc.saveas(path)


class DrawingLinksTests(unittest.TestCase):
    def test_finds_the_sheets_that_name_the_model_and_ignores_the_rest(self) -> None:
        with temporary_directory(prefix="tmp-cad-drawing-links-") as td:
            root = Path(td)
            (root / "STEP").mkdir()
            (root / "STEP" / "bracket.step").write_text("ISO-10303-21;")
            (root / "STEP" / "other.step").write_text("ISO-10303-21;")
            _dxf(root / "DXF" / "bracket_drawing.dxf", "../STEP/bracket.step")
            _dxf(root / "DXF" / "sheets" / "bracket_sheet2.dxf", "../../STEP/bracket.step")
            _dxf(root / "DXF" / "other_drawing.dxf", "../STEP/other.step")
            _dxf(root / "DXF" / "cut_layout.dxf", None)
            self.assertEqual(
                drawings_of(root / "STEP" / "bracket.step", root),
                ["DXF/bracket_drawing.dxf", "DXF/sheets/bracket_sheet2.dxf"],
            )
            self.assertEqual(drawings_of(root / "STEP" / "other.step", root), ["DXF/other_drawing.dxf"])
            self.assertEqual(dxf_source_model(root / "DXF" / "cut_layout.dxf"), "")


if __name__ == "__main__":
    unittest.main()
