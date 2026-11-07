"""Twin Orbit's standing deliverables, rewritten on each run (paths in the project folder):
  DXF/twin_orbit_panel_cut.dxf     the laser-cut profile alone (CUT), for SendCutSend 5052 H32 0.080"
  DXF/twin_orbit_panel_art.dxf     CUT + ENGRAVE (labels as outlines), for print / engraving
  STEP/twin_orbit_panel.step       the 3D panel with its legend
  STEP/twin_orbit_assembly.step and GLB/twin_orbit_assembly.glb (the GLB carries the "explode" animation)
  STEP/knob.step, jack_nut.step, jack_spacer.step, pot_nut.step
Run: cad run src/exports.py"""

from pathlib import Path

from cad import model

from assembly import twin_orbit_assembly
from hardware import jack_nut, jack_spacer, knob, pot_nut
from panel import panel, panel_art, panel_cut

ROOT = Path(__file__).resolve().parent.parent      # the project folder

if __name__ == "__main__":
    model.export(panel_cut, ROOT / "DXF" / "twin_orbit_panel_cut.dxf")
    model.export(panel_art, ROOT / "DXF" / "twin_orbit_panel_art.dxf")
    model.export(panel, ROOT / "STEP" / "twin_orbit_panel.step")
    model.export(twin_orbit_assembly, ROOT / "STEP" / "twin_orbit_assembly.step")
    model.export(twin_orbit_assembly, ROOT / "GLB" / "twin_orbit_assembly.glb")
    for name, m in (("knob", knob), ("jack_nut", jack_nut), ("jack_spacer", jack_spacer), ("pot_nut", pot_nut)):
        model.export(m, ROOT / "STEP" / f"{name}.step")
