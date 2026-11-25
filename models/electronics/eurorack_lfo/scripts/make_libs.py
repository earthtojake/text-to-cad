"""Writes the project's library tables and its own footprint library, twin_orbit.pretty:

- the Thonkiconn and Alpha 9 mm pot footprints, copied from KiCad's stock library unchanged but for
  their 3D model, which the installed library does not ship: ``${KIPRJMOD}/3dmodels/*.step``, drawn by
  src/footprint_models.py;
- LED_D3.0mm_Spacer3.5mm: the stock LED_D3.0mm with its 3D model raised 3.6 mm, the height of the LED
  spacer that brings a 3 mm LED's dome into the panel's hole.

Run: python3 scripts/make_libs.py   (standard library only)"""

from __future__ import annotations

import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import kilib  # noqa: E402

ROOT = HERE.parent
LIB = ROOT / "twin_orbit.pretty"
STOCK_FP = ["Resistor_SMD", "Capacitor_SMD", "Package_SO", "Package_TO_SOT_SMD", "Diode_SMD", "Inductor_SMD",
            "Connector_IDC", "TestPoint", "LED_THT", "Connector_Audio", "Potentiometer_THT"]
STOCK_SYM = ["Device", "Amplifier_Operational", "Transistor_BJT", "Diode", "Connector", "Connector_Audio",
             "Connector_Generic", "power"]


def copy(lib: str, name: str, new_name: str, model: str | None = None, offset_z: float | None = None) -> None:
    text = (kilib.FOOTPRINTS / f"{lib}.pretty" / f"{name}.kicad_mod").read_text(encoding="utf-8")
    text = text.replace(f'(footprint "{name}"', f'(footprint "{new_name}"', 1)
    if model:
        text = re.sub(r'\(model "[^"]+"', f'(model "{model}"', text, count=1)
    if offset_z is not None:
        text = re.sub(r'(\(model "[^"]+"\s*\(offset\s*\(xyz) [-\d.]+ [-\d.]+ [-\d.]+', rf'\1 0 0 {offset_z:g}', text, count=1)
    if new_name != name:
        text = text.replace(f'(property "Value" "{name}"', f'(property "Value" "{new_name}"', 1)
    (LIB / f"{new_name}.kicad_mod").write_text(text, encoding="utf-8")


def main() -> None:
    LIB.mkdir(exist_ok=True)
    copy("Connector_Audio", "Jack_3.5mm_QingPu_WQP-PJ398SM_Vertical_CircularHoles",
         "Jack_3.5mm_QingPu_WQP-PJ398SM_Vertical_CircularHoles", model="${KIPRJMOD}/3dmodels/Thonkiconn_PJ398SM.step")
    copy("Potentiometer_THT", "Potentiometer_Alpha_RD901F-40-00D_Single_Vertical",
         "Potentiometer_Alpha_RD901F-40-00D_Single_Vertical", model="${KIPRJMOD}/3dmodels/Alpha_RD901F-40_9mm.step")
    copy("LED_THT", "LED_D3.0mm", "LED_D3.0mm_Spacer3.5mm", offset_z=3.6)
    fp = ["(fp_lib_table", "  (version 7)",
          '  (lib (name "twin_orbit")(type "KiCad")(uri "${KIPRJMOD}/twin_orbit.pretty")(options "")(descr "Twin Orbit project footprints"))']
    fp += [f'  (lib (name "{n}")(type "KiCad")(uri "${{KICAD10_FOOTPRINT_DIR}}/{n}.pretty")(options "")(descr ""))' for n in STOCK_FP]
    (ROOT / "fp-lib-table").write_text("\n".join(fp + [")"]) + "\n", encoding="utf-8")
    sym = ["(sym_lib_table", "  (version 7)"]
    sym += [f'  (lib (name "{n}")(type "KiCad")(uri "${{KICAD10_SYMBOL_DIR}}/{n}.kicad_sym")(options "")(descr ""))' for n in STOCK_SYM]
    (ROOT / "sym-lib-table").write_text("\n".join(sym + [")"]) + "\n", encoding="utf-8")
    print("wrote", sorted(p.name for p in LIB.iterdir()), "fp-lib-table, sym-lib-table")


if __name__ == "__main__":
    main()
