"""The drawings' deliverables: the DXF of each, rewritten from its model on every run.

A DXF's bytes are a function of its geometry, so an unchanged drawing rewrites nothing.
"""
from pathlib import Path

from cadgen import export

from angled_tab import angled_tab
from cabinet_panel_drawing import cabinet_panel_drawing
from clamp_plate import clamp_plate
from gasket_plate import gasket_plate
from l_bracket_flat import l_bracket_flat
from label_plate import label_plate
from multi_bend_test_panel import multi_bend_test_panel
from u_channel_bracket import u_channel_bracket

ROOT = Path(__file__).resolve().parent.parent      # models/drawings
DRAWINGS = (angled_tab, cabinet_panel_drawing, clamp_plate, gasket_plate, l_bracket_flat, label_plate,
            multi_bend_test_panel, u_channel_bracket)

if __name__ == "__main__":
    for drawing in DRAWINGS:
        export(drawing, ROOT / "DXF" / f"{drawing.__name__}.dxf")
