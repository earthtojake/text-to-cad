"""Build Orbit's project libraries from KiCad's stock libraries (run once; rerun is harmless).

- orbit.kicad_sym: one symbol per fitted part (an "atomic" symbol: value, footprint, MPN set), copied from
  KiCad's stock symbols, a derived symbol flattened into its parent's drawing and pins.
- power.kicad_sym: the power symbols the sheets use.
- orbit.pretty: the stock footprints, each naming the stock STEP model its library footprint names
  (${KICAD10_3DMODEL_DIR}/...), but for the two KiCad ships without one: those name
  ${KIPRJMOD}/orbit.3dshapes/<footprint>.step, which src/part_models.py writes.
- sym-lib-table, fp-lib-table beside the project.

Usage: cad run scripts/build_libraries.py   (the stock libraries: KICAD_STOCK, default the KiCad.app's)
"""
import os
import re
import sys  # noqa: F401
from pathlib import Path

from cad.engine.formats.kicad import sexpr as S  # noqa: E402

STOCK = Path(os.environ.get("KICAD_STOCK", "/Applications/KiCad/KiCad.app/Contents/SharedSupport"))
HERE = Path(__file__).resolve().parent.parent  # the project folder

# name -> (stock lib, stock symbol, value, footprint "lib:name", MPN, manufacturer)
PARTS = {
    "WS2812B-2020": ("LED", "WS2812B-2020", "WS2812B-2020", "LED_SMD:LED_WS2812B-2020_PLCC4_2.0x2.0mm", "WS2812B-2020", "Worldsemi"),
    "C_100n_0603": ("Device", "C", "100nF", "Capacitor_SMD:C_0603_1608Metric", "CL10B104KB8NNNC", "Samsung"),
    "C_1u_0603": ("Device", "C", "1uF", "Capacitor_SMD:C_0603_1608Metric", "CL10A105KB8NNNC", "Samsung"),
    "C_10u_0805": ("Device", "C", "10uF", "Capacitor_SMD:C_0805_2012Metric", "CL21A106KAYNNNE", "Samsung"),
    "C_22u_1206": ("Device", "C", "22uF", "Capacitor_SMD:C_1206_3216Metric", "CL31A226KAHNNNE", "Samsung"),
    "CP_470u": ("Device", "C_Polarized", "470uF 10V", "Capacitor_SMD:CP_Elec_8x10", "EEE-FK1A471P", "Panasonic"),
    "R_5k1_0603": ("Device", "R", "5.1k", "Resistor_SMD:R_0603_1608Metric", "RC0603FR-075K1L", "Yageo"),
    "R_10k_0603": ("Device", "R", "10k", "Resistor_SMD:R_0603_1608Metric", "RC0603FR-0710KL", "Yageo"),
    "R_4k7_0603": ("Device", "R", "4.7k", "Resistor_SMD:R_0603_1608Metric", "RC0603FR-074K7L", "Yageo"),
    "R_33R_0603": ("Device", "R", "33", "Resistor_SMD:R_0603_1608Metric", "RC0603FR-0733RL", "Yageo"),
    "Polyfuse_3A": ("Device", "Polyfuse", "3A hold", "Fuse:Fuse_1210_3225Metric", "1210L300SLWR", "Littelfuse"),
    "AP2112K-3.3": ("Regulator_Linear", "AP2112K-3.3", "AP2112K-3.3", "Package_TO_SOT_SMD:SOT-23-5", "AP2112K-3.3TRG1", "Diodes Inc."),
    "74AHCT1G125": ("74xGxx", "74AHCT1G125", "74AHCT1G125", "Package_TO_SOT_SMD:SOT-23-5", "SN74AHCT1G125DBVR", "Texas Instruments"),
    "USBLC6-2SC6": ("Power_Protection", "USBLC6-2SC6", "USBLC6-2SC6", "Package_TO_SOT_SMD:SOT-23-6", "USBLC6-2SC6", "STMicroelectronics"),
    "ESP32-C3-WROOM-02": ("RF_Module", "ESP32-C3-WROOM-02", "ESP32-C3-WROOM-02", "RF_Module:ESP32-C3-WROOM-02", "ESP32-C3-WROOM-02-N4", "Espressif"),
    "LTR-303ALS-01": ("Sensor_Optical", "LTR-303ALS-01", "LTR-303ALS-01", "OptoDevice:Lite-On_LTR-303ALS-01", "LTR-303ALS-01", "Lite-On"),
    "USB_C_Receptacle": ("Connector", "USB_C_Receptacle_USB2.0_16P", "USB-C", "Connector_USB:USB_C_Receptacle_GCT_USB4105-xx-A_16P_TopMnt_Horizontal", "USB4105-GF-A", "GCT"),
    "SW_Push": ("Switch", "SW_Push", "SW_Push", "Button_Switch_SMD:SW_SPST_TL3342", "TL3342F160QG", "E-Switch"),
    "TestPoint": ("Connector", "TestPoint", "TestPoint", "TestPoint:TestPoint_Pad_D1.5mm", "", ""),
    "MountingHole": ("Mechanical", "MountingHole", "M3", "MountingHole:MountingHole_3.2mm_M3", "", ""),
}
POWER = ["GND", "+5V", "+3V3", "VBUS", "PWR_FLAG"]
# Footprints KiCad ships without a STEP model; src/part_models.py makes these.
MADE_MODELS = {"LED_WS2812B-2020_PLCC4_2.0x2.0mm", "Lite-On_LTR-303ALS-01"}

_libs = {}


def stock_lib(name):
    if name not in _libs:
        _libs[name] = S.parse((STOCK / "symbols" / f"{name}.kicad_sym").read_text())
    return _libs[name]


def stock_symbol(lib, name):
    for sym in S.find_all(stock_lib(lib), "symbol"):
        if sym[1] == name:
            return sym
    raise KeyError(f"{lib}:{name}")


def renamed(sym, old, new):
    """A deep copy of a symbol, its own name and its units' names (old_U_B) renamed."""
    def walk(node):
        if isinstance(node, list):
            out = [walk(x) for x in node]
            if out and S.head(out) == "symbol" and isinstance(out[1], str):
                if out[1] == old:
                    out[1] = new
                elif out[1].startswith(old + "_"):
                    out[1] = new + out[1][len(old):]
            return out
        return node
    return walk(sym)


def flattened(lib, name):
    """The stock symbol, a derived one merged into its parent: the parent's units, the child's properties."""
    sym = stock_symbol(lib, name)
    ext = S.find(sym, "extends")
    if not ext:
        return renamed(sym, name, name)
    parent = flattened(lib, ext[1])
    flat = renamed(parent, ext[1], name)
    child_props = {p[1]: p for p in S.find_all(sym, "property")}
    flat = [x if not (isinstance(x, list) and S.head(x) == "property" and x[1] in child_props) else child_props[x[1]]
            for x in flat]
    have = {p[1] for p in S.find_all(flat, "property")}
    idx = max(i for i, x in enumerate(flat) if isinstance(x, list) and S.head(x) == "property")
    for key, prop in child_props.items():
        if key not in have:
            idx += 1
            flat.insert(idx, prop)
    return flat


def set_property(sym, key, text, hide=True):
    for prop in S.find_all(sym, "property"):
        if prop[1] == key:
            prop[2] = text
            return
    at = [S.Sym("at"), 0, 0, 0]
    effects = [S.Sym("effects"), [S.Sym("font"), [S.Sym("size"), 1.27, 1.27]]]
    if hide:
        effects.append([S.Sym("hide"), S.Sym("yes")])
    idx = max(i for i, x in enumerate(sym) if isinstance(x, list) and S.head(x) == "property")
    sym.insert(idx + 1, [S.Sym("property"), key, text, at, effects])


def header(kind):
    return [S.Sym(kind), [S.Sym("version"), 20241209], [S.Sym("generator"), "orbit_build_libraries"],
            [S.Sym("generator_version"), "1.0"]]


def main():
    lib = header("kicad_symbol_lib")
    footprints = {}
    for new, (slib, sname, value, fp, mpn, mfr) in PARTS.items():
        sym = renamed(flattened(slib, sname), sname, new)
        fp_lib, fp_name = fp.split(":")
        footprints[fp_name] = fp_lib
        set_property(sym, "Value", value, hide=False)
        set_property(sym, "Footprint", f"orbit:{fp_name}")
        if mpn:
            set_property(sym, "MPN", mpn)
            set_property(sym, "Manufacturer", mfr)
        lib.append(sym)
    (HERE / "orbit.kicad_sym").write_text(S.dumps(lib) + "\n")

    plib = header("kicad_symbol_lib")
    for name in POWER:
        plib.append(renamed(stock_symbol("power", name), name, name))
    (HERE / "power.kicad_sym").write_text(S.dumps(plib) + "\n")

    pretty = HERE / "orbit.pretty"
    pretty.mkdir(exist_ok=True)
    for fp_name, fp_lib in sorted(footprints.items()):
        text = (STOCK / "footprints" / f"{fp_lib}.pretty" / f"{fp_name}.kicad_mod").read_text()
        tree = S.parse(text)
        models = list(S.find_all(tree, "model"))
        if fp_name in MADE_MODELS and not models:
            tree.append([S.Sym("model"), "", [S.Sym("offset"), [S.Sym("xyz"), 0, 0, 0]],
                         [S.Sym("scale"), [S.Sym("xyz"), 1, 1, 1]], [S.Sym("rotate"), [S.Sym("xyz"), 0, 0, 0]]])
            models = list(S.find_all(tree, "model"))
        for model in models:
            if fp_name in MADE_MODELS:
                model[1] = "${KIPRJMOD}/orbit.3dshapes/" + f"{fp_name}.step"
                continue
            # The stock model where the library footprint names it: KiCad's 3D library holds its STEP.
            stock = (STOCK / "3dmodels" / re.sub(r"^\$\{KICAD\d*_3DMODEL_DIR\}/", "", model[1])).with_suffix(".step")
            if not stock.exists():
                raise SystemExit(f"no STEP model for {fp_name}: {stock}")
        (pretty / f"{fp_name}.kicad_mod").write_text(S.dumps(tree) + "\n")

    (HERE / "sym-lib-table").write_text(
        "(sym_lib_table\n  (version 7)\n"
        '  (lib (name "orbit")(type "KiCad")(uri "${KIPRJMOD}/orbit.kicad_sym")(options "")(descr "Orbit\'s parts"))\n'
        '  (lib (name "power")(type "KiCad")(uri "${KIPRJMOD}/power.kicad_sym")(options "")(descr "power symbols"))\n)\n')
    (HERE / "fp-lib-table").write_text(
        "(fp_lib_table\n  (version 7)\n"
        '  (lib (name "orbit")(type "KiCad")(uri "${KIPRJMOD}/orbit.pretty")(options "")(descr "Orbit\'s footprints"))\n)\n')
    print(f"{len(PARTS)} symbols, {len(POWER)} power symbols, {len(footprints)} footprints")


if __name__ == "__main__":
    main()
