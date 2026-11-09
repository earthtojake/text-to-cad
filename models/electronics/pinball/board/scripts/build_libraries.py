# /// script
# dependencies = ["shapely>=2"]
# ///
"""SHORT CIRCUIT's playfield libraries, carried by the project so ERC and DRC need no library of the person's.

- pinball.kicad_sym: one symbol per fitted part (value, footprint, MPN and LCSC set), copied from KiCad's stock
  symbols, a derived symbol flattened into its parent's drawing and pins.
- power.kicad_sym: the power symbols the sheets use.
- pinball.pretty: the stock footprints, each naming the stock STEP model its library footprint names, but for
  the parts KiCad's 3D library lacks: those name ${KIPRJMOD}/pinball.3dshapes/<footprint>.step, which
  scripts/part_models.py writes. And the project's own: every sensor comb (a footprint per sensor, from
  playfield.sensors(), so the ball's switches are real pads on real nets), the NPTH fixing holes, the speaker pads.
- sym-lib-table, fp-lib-table beside the project.

Usage: cad run scripts/build_libraries.py   (the stock libraries: KICAD_STOCK, default the KiCad.app's)
"""
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from cad.engine.formats.kicad import sexpr as S  # noqa: E402
from shapely.ops import unary_union  # noqa: E402

import geometry as G  # noqa: E402

STOCK = Path(os.environ.get("KICAD_STOCK", "/Applications/KiCad/KiCad.app/Contents/SharedSupport"))
HERE = G.PROJECT
R0402, C0402 = "Resistor_SMD:R_0402_1005Metric", "Capacitor_SMD:C_0402_1005Metric"
R0603, C0603 = "Resistor_SMD:R_0603_1608Metric", "Capacitor_SMD:C_0603_1608Metric"
C0805 = "Capacitor_SMD:C_0805_2012Metric"

# name -> (stock lib, stock symbol, value, footprint "lib:name", MPN, manufacturer, LCSC).
# An LCSC number is given where it was checked against JLCPCB's parts library; the rest are from memory of
# that library (the README names them), to verify before ordering.
PARTS = {
    "RP2040": ("MCU_RaspberryPi", "RP2040", "RP2040", "Package_DFN_QFN:QFN-56-1EP_7x7mm_P0.4mm_EP3.2x3.2mm", "RP2040", "Raspberry Pi", "C2040"),
    "W25Q128JVS": ("Memory_Flash", "W25Q128JVS", "W25Q128JVS", "Package_SO:SOIC-8_5.3x5.3mm_P1.27mm", "W25Q128JVSIQ", "Winbond", "C97521"),
    "Crystal_12M": ("Device", "Crystal_GND24", "12MHz", "Crystal:Crystal_SMD_3225-4Pin_3.2x2.5mm", "X322512MSB4SI", "Yangxing", "C9002"),
    "CH224K": ("Interface_USB", "CH224K", "CH224K", "Package_SO:SSOP-10-1EP_3.9x4.9mm_P1mm_EP2.1x3.3mm", "CH224K", "WCH", "C970725"),
    "TPS563201": ("Regulator_Switching", "TPS563201", "TPS563201", "Package_TO_SOT_SMD:SOT-23-6", "TPS563201DDCR", "Texas Instruments", "C116592"),
    "AP2112K-3.3": ("Regulator_Linear", "AP2112K-3.3", "AP2112K-3.3", "Package_TO_SOT_SMD:SOT-23-5", "AP2112K-3.3TRG1", "Diodes Inc.", "C51118"),
    "USBLC6-2SC6": ("Power_Protection", "USBLC6-2SC6", "USBLC6-2SC6", "Package_TO_SOT_SMD:SOT-23-6", "USBLC6-2SC6", "STMicroelectronics", "C7519"),
    "USB_C_Receptacle": ("Connector", "USB_C_Receptacle_USB2.0_16P", "USB-C", "Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12", "TYPE-C-31-M-12", "HRO", "C165948"),
    "AO3400A": ("Transistor_FET", "AO3400A", "AO3400A", "Package_TO_SOT_SMD:SOT-23", "AO3400A", "Alpha & Omega", "C20917"),
    "SS34": ("Diode", "SS34", "SS34", "Diode_SMD:D_SMA", "SS34", "MDD", "C8678"),
    "SK6812MINI-E": ("LED", "SK6812MINI-E", "SK6812MINI-E", "LED_SMD:LED_SK6812MINI-E_3.2x2.8mm_P1.5mm_ReverseMount", "SK6812MINI-E", "OPSCO", "C5149201"),
    "WS2812B-2020": ("LED", "WS2812B-2020", "WS2812B-2020", "LED_SMD:LED_WS2812B-2020_PLCC4_2.0x2.0mm", "WS2812B-2020", "Worldsemi", "C965555"),
    "74AHCT1G125": ("74xGxx", "74AHCT1G125", "74AHCT1G125", "Package_TO_SOT_SMD:SOT-23-5", "SN74AHCT1G125DBVR", "Texas Instruments", "C7484"),
    "MAX98357A": ("Audio", "MAX98357A", "MAX98357A", "Package_DFN_QFN:TQFN-16-1EP_3x3mm_P0.5mm_EP1.23x1.23mm", "MAX98357AETE+T", "Analog Devices", "C910544"),
    "LIS3DH": ("Sensor_Motion", "LIS3DH", "LIS3DH", "Package_LGA:LGA-16_3x3mm_P0.5mm_LayoutBorder3x5y", "LIS3DHTR", "STMicroelectronics", "C15134"),
    "Conn_Coil": ("Connector", "Conn_01x02_Pin", "Coil", "Connector_JST:JST_PH_B2B-PH-K_1x02_P2.00mm_Vertical", "B2B-PH-K-S", "JST", "C131337"),
    "Conn_Backbox": ("Connector", "Conn_01x06_Pin", "Backbox", "Connector_JST:JST_SH_SM06B-SRSS-TB_1x06-1MP_P1.00mm_Horizontal", "SM06B-SRSS-TB", "JST", "C160404"),
    "Conn_Speaker": ("Connector", "Conn_01x02_Pin", "Speaker", "pinball:SpeakerPads_2x3mm", "", "", ""),
    "L_4u7": ("Device", "L", "4.7uH", "Inductor_SMD:L_Changjiang_FNR4020S", "FNR4020S4R7MT", "cjiang", "C167219"),
    "Polyfuse_2A": ("Device", "Polyfuse", "2A hold", "Fuse:Fuse_1210_3225Metric", "1210L200SLYR", "Littelfuse", ""),
    "CP_220u": ("Device", "C_Polarized", "220uF 16V", "Capacitor_SMD:CP_Elec_8x10", "EEE-FK1C221P", "Panasonic", ""),
    "C_22u": ("Device", "C", "22uF", C0805, "CL21A226MAQNNNE", "Samsung", "C45783"),
    "C_10u": ("Device", "C", "10uF", C0805, "CL21A106KAYNNNE", "Samsung", "C15850"),
    "C_1u": ("Device", "C", "1uF", C0603, "CL10A105KB8NNNC", "Samsung", "C15849"),
    "C_1u_0402": ("Device", "C", "1uF", C0402, "CL05A105KA5NQNC", "Samsung", "C52923"),
    "TVS_5V": ("Device", "D_TVS", "PESD5V0S1BA", "Diode_SMD:D_SOD-323", "PESD5V0S1BA,115", "Nexperia", ""),
    "C_100n": ("Device", "C", "100nF", C0402, "CL05B104KO5NNNC", "Samsung", "C1525"),
    "C_15p": ("Device", "C", "15pF", C0402, "0402CG150J500NT", "FH", "C1548"),
    "R_27R": ("Device", "R", "27", R0402, "0402WGF270JTCE", "UNI-ROYAL", "C25092"),
    "R_33R": ("Device", "R", "33", R0402, "0402WGF330JTCE", "UNI-ROYAL", "C25105"),
    "R_100R": ("Device", "R", "100", R0402, "0402WGF1000TCE", "UNI-ROYAL", "C25076"),
    "R_1k": ("Device", "R", "1k", R0402, "0402WGF1001TCE", "UNI-ROYAL", "C11702"),
    "R_4k7": ("Device", "R", "4.7k", R0402, "0402WGF4701TCE", "UNI-ROYAL", "C25900"),
    "R_6k8": ("Device", "R", "6.8k", R0402, "0402WGF6801TCE", "UNI-ROYAL", "C25917"),
    "R_10k": ("Device", "R", "10k", R0402, "0402WGF1002TCE", "UNI-ROYAL", "C25744"),
    "R_22k": ("Device", "R", "22k", R0402, "0402WGF2202TCE", "UNI-ROYAL", "C25768"),
    "R_56k": ("Device", "R", "56k", R0402, "0402WGF5602TCE", "UNI-ROYAL", "C25796"),
    "R_100k": ("Device", "R", "100k", R0402, "0402WGF1003TCE", "UNI-ROYAL", "C25741"),
    "R_1M": ("Device", "R", "1M", R0402, "0402WGF1004TCE", "UNI-ROYAL", "C26083"),
    "SW_Tactile": ("Switch", "SW_Push", "SW_Push", "Button_Switch_SMD:SW_SPST_TL3342", "TL3342F160QG", "E-Switch", ""),
    "SW_Flipper": ("Switch", "SW_Push", "FLIP", "Button_Switch_THT:SW_Tactile_SPST_Angled_PTS645Vx58-2LFS", "PTS645VL58-2 LFS", "C&K", ""),
    "SW_Start": ("Switch", "SW_Push", "START", "Button_Switch_THT:SW_PUSH_6mm_H9.5mm", "", "", ""),
    "BallSwitch": ("Switch", "SW_Push", "ball", "", "", "", ""),       # a comb: its footprint is set per sensor
    "TestPoint": ("Connector", "TestPoint", "TestPoint", "TestPoint:TestPoint_Pad_D1.5mm", "", "", ""),
    "Fiducial": ("Mechanical", "Fiducial", "Fiducial", "Fiducial:Fiducial_1mm_Mask2mm", "", "", ""),
    "MountingHole": ("Mechanical", "MountingHole", "M2", "pinball:NPTH_2.2mm", "", "", ""),
}
POWER = ["GND", "+1V1", "+3V3", "+5V", "+9V", "VBUS", "PWR_FLAG"]
# Footprints KiCad ships without a STEP model: scripts/part_models.py writes these.
MADE_MODELS = {"LED_WS2812B-2020_PLCC4_2.0x2.0mm", "USB_C_Receptacle_HRO_TYPE-C-31-M-12"}
# Footprints whose named model is missing but KiCad holds the same package under another name.
MODEL_STANDINS = {"TQFN-16-1EP_3x3mm_P0.5mm_EP1.23x1.23mm":
                  "${KICAD10_3DMODEL_DIR}/Package_DFN_QFN.3dshapes/TQFN-16-1EP_3x3mm_P0.5mm_EP1.6x1.6mm.step"}

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
    return [S.Sym(kind), [S.Sym("version"), 20241209], [S.Sym("generator"), "pinball_build_libraries"],
            [S.Sym("generator_version"), "1.0"]]


# ------------------------------------------------------------------------------------- the project's footprints

def _xy(pts):
    return [S.Sym("pts"), *[[S.Sym("xy"), round(x, 4), round(y, 4)] for x, y in pts]]


def _effects(size=1.0, thick=0.15):
    return [S.Sym("effects"), [S.Sym("font"), [S.Sym("size"), size, size], [S.Sym("thickness"), thick]]]


def _fields(name, ref_layer="F.Fab"):
    ref = [S.Sym("property"), "Reference", "REF**", [S.Sym("at"), 0, 0, 0], [S.Sym("layer"), ref_layer], _effects()]
    val = [S.Sym("property"), "Value", name, [S.Sym("at"), 0, 1.5, 0], [S.Sym("layer"), "F.Fab"], _effects()]
    return [ref, val]


def comb_footprint(sensor):
    """A sensor's comb as a footprint: a plated land at each spine's end, pad 1 on the SENSE net, pad 2 on GND:
    the switch's two terminals, the way down to the inner layers. The comb's own copper is the board's art
    (scripts/board.py draws it on the land's net, from playfield.py), with a soldermask opening of its own for
    each finger, so the ball touches gold across black."""
    ax, ay = sensor.anchor

    def loc(p):
        return (p[0] - ax, -(p[1] - ay))
    name = f"Comb_{sensor.ref}"
    fp = [S.Sym("footprint"), name, [S.Sym("version"), 20241229], [S.Sym("generator"), "pinball_build_libraries"],
          [S.Sym("layer"), "F.Cu"], [S.Sym("descr"), f"Ball switch {sensor.ref} ({sensor.name}): its comb's plated lands; "
                                                     f"the comb is drawn on the board from playfield.py, {G.FINGER} mm "
                                                     f"fingers on a {G.PITCH} mm pitch"],
          [S.Sym("tags"), "pinball sensor comb"], *_fields(name),
          [S.Sym("attr"), S.Sym("smd"), S.Sym("exclude_from_pos_files"), S.Sym("exclude_from_bom")]]
    hull = unary_union([sensor.sense, sensor.gnd]).convex_hull
    fp.append([S.Sym("fp_poly"), _xy([loc(p) for p in list(hull.exterior.coords)[:-1]]),
               [S.Sym("stroke"), [S.Sym("width"), 0.05], [S.Sym("type"), S.Sym("solid")]],
               [S.Sym("fill"), S.Sym("no")], [S.Sym("layer"), "F.Fab"]])
    for number, land in (("1", sensor.land_sense), ("2", sensor.land_gnd)):
        lx, ly = loc(land)
        fp.append([S.Sym("pad"), number, S.Sym("thru_hole"), S.Sym("circle"), [S.Sym("at"), round(lx, 4), round(ly, 4)],
                   [S.Sym("size"), G.LAND_PAD, G.LAND_PAD], [S.Sym("drill"), G.LAND_DRILL],
                   [S.Sym("layers"), "*.Cu", "F.Mask"], [S.Sym("remove_unused_layers"), S.Sym("no")]])
    return name, fp


def hole_footprint(d):
    name = f"NPTH_{d:.1f}mm"
    fp = [S.Sym("footprint"), name, [S.Sym("version"), 20241229], [S.Sym("generator"), "pinball_build_libraries"],
          [S.Sym("layer"), "F.Cu"], [S.Sym("descr"), f"Non-plated hole, {d} mm"], [S.Sym("tags"), "hole NPTH"],
          *_fields(name),
          [S.Sym("attr"), S.Sym("exclude_from_pos_files"), S.Sym("exclude_from_bom")],
          [S.Sym("fp_circle"), [S.Sym("center"), 0, 0], [S.Sym("end"), d / 2 + 0.25, 0],
           [S.Sym("stroke"), [S.Sym("width"), 0.05], [S.Sym("type"), S.Sym("solid")]], [S.Sym("fill"), S.Sym("no")],
           [S.Sym("layer"), "F.CrtYd"]],
          [S.Sym("pad"), "", S.Sym("np_thru_hole"), S.Sym("circle"), [S.Sym("at"), 0, 0], [S.Sym("size"), d, d],
           [S.Sym("drill"), d], [S.Sym("layers"), "*.Cu", "*.Mask"]]]
    return name, fp


def speaker_footprint():
    name = "SpeakerPads_2x3mm"
    fp = [S.Sym("footprint"), name, [S.Sym("version"), 20241229], [S.Sym("generator"), "pinball_build_libraries"],
          [S.Sym("layer"), "F.Cu"], [S.Sym("descr"), "Two solder pads for the speaker's wires"],
          [S.Sym("tags"), "speaker pads"], *_fields(name),
          [S.Sym("attr"), S.Sym("smd"), S.Sym("exclude_from_pos_files"), S.Sym("exclude_from_bom")],
          [S.Sym("fp_rect"), [S.Sym("start"), -3.2, -2.0], [S.Sym("end"), 3.2, 2.0],
           [S.Sym("stroke"), [S.Sym("width"), 0.05], [S.Sym("type"), S.Sym("solid")]], [S.Sym("fill"), S.Sym("no")],
           [S.Sym("layer"), "F.CrtYd"]],
          [S.Sym("pad"), "1", S.Sym("smd"), S.Sym("rect"), [S.Sym("at"), -1.6, 0], [S.Sym("size"), 2.0, 3.0],
           [S.Sym("layers"), "F.Cu", "F.Paste", "F.Mask"]],
          [S.Sym("pad"), "2", S.Sym("smd"), S.Sym("rect"), [S.Sym("at"), 1.6, 0], [S.Sym("size"), 2.0, 3.0],
           [S.Sym("layers"), "F.Cu", "F.Paste", "F.Mask"]]]
    return name, fp


# ------------------------------------------------------------------------------------------------------- main

def main():
    lib = header("kicad_symbol_lib")
    footprints = {}
    for new, (slib, sname, value, fp, mpn, mfr, lcsc) in PARTS.items():
        sym = renamed(flattened(slib, sname), sname, new)
        set_property(sym, "Value", value, hide=False)
        if fp:
            fp_lib, fp_name = fp.split(":")
            if fp_lib != "pinball":
                footprints[fp_name] = fp_lib
            set_property(sym, "Footprint", f"pinball:{fp_name}")
        else:
            set_property(sym, "Footprint", "")
        if mpn:
            set_property(sym, "MPN", mpn)
            set_property(sym, "Manufacturer", mfr)
        if lcsc:
            set_property(sym, "LCSC", lcsc)
        if new == "MAX98357A":          # its exposed pad is ground: a passive pin, so ERC takes the tie
            for unit in S.find_all(sym, "symbol"):
                for pin in S.find_all(unit, "pin"):
                    if S.find(pin, "number")[1] == "17":
                        pin[1] = S.Sym("passive")
        lib.append(sym)
    (HERE / "pinball.kicad_sym").write_text(S.dumps(lib) + "\n")

    plib = header("kicad_symbol_lib")
    for name in POWER:
        plib.append(renamed(stock_symbol("power", name), name, name))
    (HERE / "power.kicad_sym").write_text(S.dumps(plib) + "\n")

    pretty = HERE / "pinball.pretty"
    pretty.mkdir(exist_ok=True)
    for old in pretty.glob("*.kicad_mod"):
        old.unlink()
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
                model[1] = "${KIPRJMOD}/pinball.3dshapes/" + f"{fp_name}.step"
                continue
            if fp_name in MODEL_STANDINS:
                model[1] = MODEL_STANDINS[fp_name]
            stock = (STOCK / "3dmodels" / re.sub(r"^\$\{KICAD\d*_3DMODEL_DIR\}/", "", model[1])).with_suffix(".step")
            if not stock.exists():
                raise SystemExit(f"no STEP model for {fp_name}: {stock}")
        (pretty / f"{fp_name}.kicad_mod").write_text(S.dumps(tree) + "\n")
    made = [comb_footprint(s) for s in G.sensors()] + [hole_footprint(2.2), hole_footprint(6.0), speaker_footprint()]
    for name, fp in made:
        (pretty / f"{name}.kicad_mod").write_text(S.dumps(fp) + "\n")

    (HERE / "sym-lib-table").write_text(
        "(sym_lib_table\n  (version 7)\n"
        '  (lib (name "pinball")(type "KiCad")(uri "${KIPRJMOD}/pinball.kicad_sym")(options "")(descr "SHORT CIRCUIT\'s parts"))\n'
        '  (lib (name "power")(type "KiCad")(uri "${KIPRJMOD}/power.kicad_sym")(options "")(descr "power symbols"))\n)\n')
    (HERE / "fp-lib-table").write_text(
        "(fp_lib_table\n  (version 7)\n"
        '  (lib (name "pinball")(type "KiCad")(uri "${KIPRJMOD}/pinball.pretty")(options "")(descr "SHORT CIRCUIT\'s footprints"))\n)\n')
    print(f"{len(PARTS)} symbols, {len(POWER)} power symbols, {len(footprints)} stock footprints, {len(made)} of its own")


if __name__ == "__main__":
    main()
