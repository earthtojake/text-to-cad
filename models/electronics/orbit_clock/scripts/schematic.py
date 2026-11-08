"""Orbit's schematic: a root sheet and four sub-sheets (Power, MCU, Minute ring, Hour ring).

Run from the project folder:  cad run scripts/schematic.py

1. The hierarchy (the root's four sheet symbols and their pins, and an empty file per sub-sheet) is written
   as text: a sheet symbol created over KiCad's IPC API makes the save fail on this nightly.
2. Everything else -- every symbol, wire, label, junction, no-connect and note -- is placed through KiCad's
   IPC API in one `kicad_sch.edit` block. A sheet that already holds symbols is left as it is, so a second
   run changes nothing.

The LEDs are drawn as rows of a chain (DOUT of one to DIN of the next), their 100 nF capacitors as a bank
beside them: on the board each capacitor sits beside its LED (scripts/board.py).
"""
from __future__ import annotations

import math
import sys
import uuid
from collections import Counter
from pathlib import Path

from cad import kicad_sch
from cad.engine.formats.kicad import sexpr as S
from kicode.geometry import Vector2
from kicode.schematic_types import (HierarchicalLabel, Junction, LocalLabel, NoConnectMarker, SchematicLine,
                                    SchematicLineType, SchematicLabelShape, SchematicLabelSpinStyle,
                                    SchematicSymbolOrientation, SchematicText)

HERE = Path(__file__).resolve().parent.parent
ROOT = HERE / "orbit.kicad_sch"
N_MINUTE, N_HOUR = 60, 12

# Sheet symbols on the root: name, file, (x, y), (w, h), pins (name, shape, side, offset from top)
SHEETS = [
    ("Power", "power.kicad_sch", (30.48, 50.8), (38.1, 40.64),
     [("USB_D+", "bidirectional", "right", 10.16), ("USB_D-", "bidirectional", "right", 15.24),
      ("CC1", "output", "right", 25.4), ("CC2", "output", "right", 30.48)]),
    ("MCU", "mcu.kicad_sch", (109.22, 50.8), (40.64, 40.64),
     [("USB_D+", "bidirectional", "left", 10.16), ("USB_D-", "bidirectional", "left", 15.24),
      ("CC1", "input", "left", 25.4), ("CC2", "input", "left", 30.48), ("LED_DIN", "output", "right", 10.16)]),
    ("Minute ring", "minutes.kicad_sch", (190.5, 50.8), (40.64, 20.32),
     [("DIN", "input", "left", 10.16), ("DOUT", "output", "right", 10.16)]),
    ("Hour ring", "hours.kicad_sch", (190.5, 106.68), (40.64, 20.32),
     [("DIN", "input", "left", 10.16)]),
]

EMPTY_SHEET = ('(kicad_sch\n\t(version 20261025)\n\t(generator "eeschema")\n\t(generator_version "10.99")\n'
               '\t(uuid "{uuid}")\n\t(paper "{paper}")\n\t(lib_symbols)\n\t(embedded_fonts no)\n)\n')
PAPER = {"power.kicad_sch": "A4", "mcu.kicad_sch": "A3", "minutes.kicad_sch": "A3", "hours.kicad_sch": "A4"}


def mm(v):
    return round(v, 4)


# ---------------------------------------------------------------- 1. the hierarchy, as text (the fallback)

def font(justify=None):
    eff = [S.Sym("effects"), [S.Sym("font"), [S.Sym("size"), 1.27, 1.27]]]
    if justify:
        eff.append([S.Sym("justify"), *[S.Sym(j) for j in justify]])
    return eff


def sheet_block(root_uuid, page, name, file, at, size, pins):
    x, y = at
    w, h = size
    block = [S.Sym("sheet"), [S.Sym("at"), x, y], [S.Sym("size"), w, h],
             [S.Sym("exclude_from_sim"), S.Sym("no")], [S.Sym("in_bom"), S.Sym("yes")],
             [S.Sym("on_board"), S.Sym("yes")], [S.Sym("dnp"), S.Sym("no")],
             [S.Sym("fields_autoplaced"), S.Sym("yes")],
             [S.Sym("stroke"), [S.Sym("width"), 0.1524], [S.Sym("type"), S.Sym("solid")]],
             [S.Sym("fill"), [S.Sym("color"), 255, 255, 230, 1]],
             # KiCad saves sheets sorted by uuid; these sort in page order
             [S.Sym("uuid"), f"{page:08x}-0000-4000-8000-0000000000{page:02x}"],
             [S.Sym("property"), "Sheetname", name, [S.Sym("at"), x, mm(y - 0.7116), 0],
              font(["left", "bottom"])],
             [S.Sym("property"), "Sheetfile", file, [S.Sym("at"), x, mm(y + h + 0.5846), 0],
              font(["left", "top"])]]
    for pname, shape, side, dy in pins:
        px = x + w if side == "right" else x
        angle = 0 if side == "right" else 180
        block.append([S.Sym("pin"), pname, S.Sym(shape), [S.Sym("at"), mm(px), mm(y + dy), angle],
                      [S.Sym("uuid"), str(uuid.uuid5(uuid.NAMESPACE_URL, f"orbit-pin-{file}-{pname}"))],
                      font(["right" if side == "right" else "left"])])
    block.append([S.Sym("instances"), [S.Sym("project"), "orbit",
                                       [S.Sym("path"), f"/{root_uuid}", [S.Sym("page"), str(page)]]]])
    return block


def ensure_hierarchy():
    if not ROOT.exists():
        with kicad_sch.edit(str(ROOT)):  # KiCad makes the root and its project
            pass
    tree = S.parse(ROOT.read_text())
    have = set()
    for sheet in S.find_all(tree, "sheet"):
        for prop in S.find_all(sheet, "property"):
            if prop[1] == "Sheetfile":
                have.add(prop[2])
    root_uuid = S.value(tree, "uuid")
    changed = False
    insert_at = next(i for i, x in enumerate(tree) if isinstance(x, list) and S.head(x) == "sheet_instances")
    for page, (name, file, at, size, pins) in enumerate(SHEETS, start=2):
        sub = HERE / file
        if not sub.exists():
            sub.write_text(EMPTY_SHEET.format(uuid=uuid.uuid5(uuid.NAMESPACE_URL, "orbit-file-" + file),
                                              paper=PAPER[file]))
        if file not in have:
            tree.insert(insert_at, sheet_block(root_uuid, page, name, file, at, size, pins))
            insert_at += 1
            changed = True
    if changed:
        ROOT.write_text(S.dumps(tree) + "\n")
        print(f"wrote the hierarchy into {ROOT.name}: {len(SHEETS)} sheets")


# ---------------------------------------------------------------- 2. the contents, through KiCad's IPC API

ROT = {0: SchematicSymbolOrientation.SSO_0, 90: SchematicSymbolOrientation.SSO_90,
       180: SchematicSymbolOrientation.SSO_180, 270: SchematicSymbolOrientation.SSO_270}
SPIN = {"left": SchematicLabelSpinStyle.SLSS_LEFT, "right": SchematicLabelSpinStyle.SLSS_RIGHT,
        "up": SchematicLabelSpinStyle.SLSS_UP, "down": SchematicLabelSpinStyle.SLSS_BOTTOM}
SHAPE = {"input": SchematicLabelShape.SLSH_INPUT, "output": SchematicLabelShape.SLSH_OUTPUT,
         "bidirectional": SchematicLabelShape.SLSH_BIDI, "passive": SchematicLabelShape.SLSH_PASSIVE}


def v(x, y):
    return Vector2.from_xy_mm(mm(x), mm(y))


def turned(dx, dy, rot):
    return {0: (dx, dy), 90: (dy, -dx), 180: (-dx, -dy), 270: (-dy, dx)}[rot]


class Part:
    def __init__(self, ref, x, y, rot, pins):
        self.ref, self.x, self.y, self.rot, self.pins = ref, x, y, rot, pins

    def pin(self, number):
        dx, dy = turned(*self.pins[number], self.rot)
        return (mm(self.x + dx), mm(self.y + dy))


class Sheet:
    """One sheet's drawing: symbols placed at once, wires, labels and markers created in one go at the end."""

    def __init__(self, sch, name):
        self.sch, self.name = sch, name
        self.items, self.wires, self.pin_ends = [], [], []
        self.pwr = 0

    def part(self, lib, ref, x, y, rot=0):
        sym = self.sch.place_symbol_from_library(lib, v(x, y), orientation=ROT[rot], reference=ref)
        pins = {p.number: (p.position.x / 1e6, p.position.y / 1e6) for p in sym.definition.pins}
        part = Part(ref, x, y, rot, pins)
        for number in pins:
            self.pin_ends.append(part.pin(number))
        return part

    def power(self, name, at, rot=0):
        """A power symbol (or a PWR_FLAG) whose pin is at `at`."""
        Sheet.counter += 1
        ref = ("#FLG" if name == "PWR_FLAG" else "#PWR") + f"{Sheet.counter:03d}"
        self.part(f"power:{name}", ref, at[0], at[1], rot)

    counter = 0

    def wire(self, *points):
        for a, b in zip(points, points[1:]):
            if a == b:
                continue
            line = SchematicLine()
            line.type = SchematicLineType.SLT_WIRE
            line.start, line.end = v(*a), v(*b)
            self.items.append(line)
            self.wires.append((tuple(map(mm, a)), tuple(map(mm, b))))

    def rail(self, points):
        """A straight run through `points` (in order), a wire between each neighbouring pair."""
        for a, b in zip(points, points[1:]):
            self.wire(a, b)

    def label(self, text, at, spin="left", hier=None):
        item = HierarchicalLabel() if hier else LocalLabel()
        if hier:
            item.shape = SHAPE[hier]
        item.text.value = text
        item.position = v(*at)
        item.spin_style = SPIN[spin]
        item.text.attributes.size = Vector2.from_xy_mm(1.27, 1.27)
        self.items.append(item)

    def note(self, text, at, size=1.27):
        item = SchematicText()
        item.text.value = text
        item.position = v(*at)
        item.text.attributes.size = Vector2.from_xy_mm(size, size)
        self.items.append(item)

    def no_connect(self, at):
        item = NoConnectMarker()
        item.position = v(*at)
        self.items.append(item)

    def finish(self):
        ends = Counter()
        for a, b in self.wires:
            ends[a] += 1
            ends[b] += 1
        pins = Counter(self.pin_ends)
        for point, count in ends.items():
            if count + pins.get(point, 0) >= 3:
                junction = Junction()
                junction.position = v(*point)
                self.items.append(junction)
        if self.items:
            self.sch.create_items(self.items)


# --- the sheets ----------------------------------------------------------------------------------------

def draw_root(sh: Sheet):
    """Wires between the sheet pins, the four mounting holes, a title."""
    pin = {}
    for name, file, (x, y), (w, h), pins in SHEETS:
        for pname, shape, side, dy in pins:
            pin[(name, pname)] = (mm(x + w if side == "right" else x), mm(y + dy))
    for net in ("USB_D+", "USB_D-", "CC1", "CC2"):
        sh.wire(pin[("Power", net)], pin[("MCU", net)])
    a, b = pin[("MCU", "LED_DIN")], pin[("Minute ring", "DIN")]
    sh.wire(a, (175.26, a[1]), (175.26, b[1]), b)
    a, b = pin[("Minute ring", "DOUT")], pin[("Hour ring", "DIN")]
    sh.wire(a, (238.76, a[1]), (238.76, 96.52), (182.88, 96.52), (182.88, b[1]), b)
    for i in range(4):
        sh.part("orbit:MountingHole", f"H{i + 1}", 40.64 + 15.24 * i, 129.54)
    sh.note("Orbit - a round LED ring clock: 60 minute LEDs, 12 hour LEDs, ESP32-C3, USB-C", (30.48, 30.48), 2.54)
    sh.note("H1-H4: M3, the baffle's bosses (src/orbit.py)", (30.48, 139.7))


def draw_power(sh: Sheet):
    j1 = sh.part("orbit:USB_C_Receptacle", "J1", 40.64, 101.6)
    vbus, gnd = j1.pin("A4"), j1.pin("A1")
    sh.power("GND", gnd)
    sh.wire(j1.pin("SH"), gnd)
    sh.power("PWR_FLAG", j1.pin("SH"), 180)
    for p in ("A8", "B8"):
        sh.no_connect(j1.pin(p))
    # CC pull-downs (5.1k, the USB Type-C sink's Rd), the CC nets also go to the MCU's ADC.
    sh.wire(j1.pin("A5"), (71.12, j1.pin("A5")[1]))
    sh.label("CC1", (71.12, j1.pin("A5")[1]), "right", hier="output")
    sh.wire(j1.pin("B5"), (71.12, j1.pin("B5")[1]))
    sh.label("CC2", (71.12, j1.pin("B5")[1]), "right", hier="output")
    for ref, x, net in (("R1", 22.86, "CC1"), ("R2", 33.02, "CC2")):
        r = sh.part("orbit:R_5k1_0603", ref, x, 55.88)
        sh.wire(r.pin("1"), (x, 49.53))
        sh.label(net, (x, 49.53), "up", hier="output")
        sh.power("GND", r.pin("2"))
    # D-: A7 and B7 joined; D+: A6 and B6 joined; both through the ESD array U3 (flow-through: 1-6, 3-4)
    u3 = sh.part("orbit:USBLC6-2SC6", "U3", 93.98, 101.6)
    a7, b7, a6, b6 = (j1.pin(p) for p in ("A7", "B7", "A6", "B6"))
    sh.wire(a7, (63.5, a7[1]), (63.5, b7[1]))
    sh.wire(b7, (63.5, b7[1]))
    sh.wire((63.5, b7[1]), (71.12, b7[1]), u3.pin("1"))
    sh.label("USB_D-", (71.12, b7[1]), "right")
    sh.wire(a6, (66.04, a6[1]), (66.04, b6[1]))
    sh.wire(b6, (66.04, b6[1]))
    sh.wire((66.04, a6[1]), (71.12, a6[1]), u3.pin("3"))
    sh.wire(u3.pin("6"), (109.22, u3.pin("6")[1]))
    sh.label("USB_D-", (109.22, u3.pin("6")[1]), "right", hier="bidirectional")
    sh.wire(u3.pin("4"), (109.22, u3.pin("4")[1]))
    sh.label("USB_D+", (109.22, u3.pin("4")[1]), "right", hier="bidirectional")
    sh.label("USB_D+", (71.12, a6[1]), "right")
    sh.power("GND", u3.pin("2"))
    # VBUS: the connector, the ESD array's VBUS pin, the polyfuse
    rail_y = 73.66
    f1 = sh.part("orbit:Polyfuse_3A", "F1", 110.49, rail_y, 90)
    sh.wire(vbus, (vbus[0], rail_y))
    # The ESD array's VBUS pin biases its clamps; it sits on +5V, 3 mOhm past the polyfuse, where the board has a plane
    sh.wire(u3.pin("5"), (u3.pin("5")[0], 91.44))
    sh.power("+5V", (u3.pin("5")[0], 91.44))
    sh.rail([(vbus[0], rail_y), (71.12, rail_y), f1.pin("1")])
    sh.power("VBUS", (vbus[0], rail_y))
    sh.power("PWR_FLAG", (71.12, rail_y))
    # +5V: bulk capacitance for 72 LEDs, the 3.3 V regulator
    x5 = [f1.pin("2")[0], 116.84, 124.46, 134.62, 149.86, 162.56, 172.72]
    sh.rail([(x, rail_y) for x in x5])
    sh.power("+5V", (116.84, rail_y))
    sh.power("PWR_FLAG", (124.46, rail_y), 180)
    for ref, lib, x in (("C1", "orbit:CP_470u", 134.62), ("C2", "orbit:C_22u_1206", 149.86),
                        ("C3", "orbit:C_1u_0603", 162.56)):
        c = sh.part(lib, ref, x, rail_y + 3.81)
        sh.power("GND", c.pin("2"))
    u2 = sh.part("orbit:AP2112K-3.3", "U2", 187.96, 81.28)
    sh.wire((172.72, rail_y), (172.72, u2.pin("1")[1]), u2.pin("1"))
    sh.wire((172.72, u2.pin("1")[1]), (172.72, u2.pin("3")[1]), u2.pin("3"))
    sh.no_connect(u2.pin("4"))
    sh.power("GND", u2.pin("2"))
    out = u2.pin("5")
    sh.rail([out, (203.2, out[1]), (210.82, out[1])])
    c4 = sh.part("orbit:C_1u_0603", "C4", 203.2, out[1] + 3.81)
    sh.power("GND", c4.pin("2"))
    sh.power("+3V3", (210.82, out[1]))
    sh.note("USB-C sink: 5.1k Rd on CC1/CC2; the CC voltages go to the ESP32's ADC so firmware can\n"
            "cap LED brightness to what the source advertises (0.9/1.5/3.0 A).", (22.86, 142.24))
    sh.note("Worst case 72 x 3 x 12 mA = 2.6 A + ESP32 0.35 A = ~3 A: F1 holds 3 A (trips at 6 A).",
            (22.86, 152.4))
    sh.note("Power in", (22.86, 38.1), 2.54)


def draw_mcu(sh: Sheet):
    u1 = sh.part("orbit:ESP32-C3-WROOM-02", "U1", 134.62, 127.0)
    # Pins chosen for the board: the module's two pad rows fan out without a crossing:
    # CC1 IO4 and CC2 IO3 (ADC1), I2C on IO5/IO6, LED data on IO7.
    left = {"2": ("EN", None), "3": ("CC1", "input"), "15": ("CC2", "input"), "16": ("IO2", None),
            "4": ("I2C_SDA", None), "5": ("I2C_SCL", None), "7": ("IO8", None), "8": ("BOOT", None),
            "6": ("LED_DATA_3V3", None), "13": ("USB_D-", "bidirectional"), "14": ("USB_D+", "bidirectional")}
    for number, (net, hier) in left.items():
        p = u1.pin(number)
        sh.wire(p, (p[0] - 7.62, p[1]))
        sh.label(net, (p[0] - 7.62, p[1]), "left", hier=hier)
    for number in ("18", "17", "10"):
        sh.no_connect(u1.pin(number))
    for number, net in (("11", "UART_RX"), ("12", "UART_TX")):
        p = u1.pin(number)
        sh.wire(p, (p[0] + 7.62, p[1]))
        sh.label(net, (p[0] + 7.62, p[1]), "right")
    sh.power("GND", u1.pin("9"))
    top = u1.pin("1")
    ry = top[1] - 15.24
    sh.wire(top, (top[0], ry))
    sh.rail([(top[0], ry), (124.46, ry), (114.3, ry)])
    sh.power("+3V3", (top[0], ry))
    for ref, lib, x in (("C5", "orbit:C_10u_0805", 124.46), ("C6", "orbit:C_100n_0603", 114.3)):
        c = sh.part(lib, ref, x, ry + 3.81)
        sh.power("GND", c.pin("2"))
    # EN: 10k up, 1uF down (Espressif's RC delay), RESET to ground. BOOT (IO9): 10k up, BOOT to ground.
    for y, net, rref, sref, cref in ((68.58, "EN", "R3", "SW2", "C7"), (99.06, "BOOT", "R4", "SW1", None)):
        r = sh.part("orbit:R_10k_0603", rref, 45.72, y - 7.62)
        sh.power("+3V3", r.pin("1"))
        node = (45.72, y)
        sh.wire(r.pin("2"), node)
        sw = sh.part("orbit:SW_Push", sref, 63.5, y)
        sh.wire(node, (53.34, y), sw.pin("1"))
        sh.label(net, (53.34, y), "up")
        sh.power("GND", sw.pin("2"))
        if cref:
            c = sh.part("orbit:C_1u_0603", cref, 45.72, y + 3.81)
            sh.power("GND", c.pin("2"))
    # IO2 and IO8: strapping pins, held high for a normal SPI boot and for download mode
    for ref, x, net in (("R5", 22.86, "IO2"), ("R6", 30.48, "IO8")):
        r = sh.part("orbit:R_10k_0603", ref, x, 129.54)
        sh.power("+3V3", r.pin("1"))
        sh.wire(r.pin("2"), (x, 139.7))
        sh.label(net, (x, 139.7), "down")
    # LED data: 3.3 V in, 5 V out (74AHCT: TTL input thresholds, 5 V supply), 33 ohm at the driver
    u4 = sh.part("orbit:74AHCT1G125", "U4", 233.68, 101.6)
    sh.wire(u4.pin("2"), (210.82, 101.6))
    sh.label("LED_DATA_3V3", (210.82, 101.6), "left")
    vcc = u4.pin("5")
    sh.wire(vcc, (vcc[0], 83.82))
    sh.rail([(vcc[0], 83.82), (218.44, 83.82)])
    sh.power("+5V", (vcc[0], 83.82))
    c8 = sh.part("orbit:C_100n_0603", "C8", 218.44, 87.63)
    sh.power("GND", c8.pin("2"))
    oe = u4.pin("1")
    sh.wire(oe, (oe[0], 88.9), (243.84, 88.9))
    sh.power("GND", (243.84, 88.9))
    sh.power("GND", u4.pin("3"))
    r7 = sh.part("orbit:R_33R_0603", "R7", 256.54, 101.6, 90)
    sh.wire(u4.pin("4"), r7.pin("1"))
    sh.wire(r7.pin("2"), (271.78, 101.6))
    sh.label("LED_DIN", (271.78, 101.6), "right", hier="output")
    # Ambient light: LTR-303ALS-01 on I2C, on the board's front behind the diffuser's window
    u5 = sh.part("orbit:LTR-303ALS-01", "U5", 238.76, 177.8)
    sh.no_connect(u5.pin("2"))
    sh.no_connect(u5.pin("5"))
    sh.power("GND", u5.pin("3"))
    vdd = u5.pin("1")
    sh.wire(vdd, (vdd[0], 160.02))
    sh.rail([(vdd[0], 160.02), (251.46, 160.02), (259.08, 160.02)])
    sh.power("+3V3", (vdd[0], 160.02))
    for ref, lib, x in (("C9", "orbit:C_100n_0603", 251.46), ("C10", "orbit:C_1u_0603", 259.08)):
        c = sh.part(lib, ref, x, 163.83)
        sh.power("GND", c.pin("2"))
    for number, net in (("6", "I2C_SDA"), ("4", "I2C_SCL")):
        p = u5.pin(number)
        sh.wire(p, (p[0] - 10.16, p[1]))
        sh.label(net, (p[0] - 10.16, p[1]), "left")
    for ref, x, net in (("R8", 190.5, "I2C_SDA"), ("R9", 198.12, "I2C_SCL")):
        r = sh.part("orbit:R_4k7_0603", ref, x, 172.72)
        sh.power("+3V3", r.pin("1"))
        sh.wire(r.pin("2"), (x, 182.88))
        sh.label(net, (x, 182.88), "down")
    # Test points: power, ground and the console UART
    for i, (ref, net) in enumerate((("TP1", "+5V"), ("TP2", "+3V3"), ("TP3", "GND"), ("TP4", "UART_TX"),
                                    ("TP5", "UART_RX"))):
        x = 30.48 + 15.24 * i
        tp = sh.part("orbit:TestPoint", ref, x, 180.34)
        sh.wire(tp.pin("1"), (x, 185.42))
        if net in ("+5V", "+3V3"):
            sh.power(net, (x, 185.42), 180)
        elif net == "GND":
            sh.power("GND", (x, 185.42))
        else:
            sh.label(net, (x, 185.42), "down")
    sh.note("ESP32-C3 (native USB on IO18/IO19)", (22.86, 38.1), 2.54)
    sh.note("Reset and boot", (22.86, 50.8))
    sh.note("Strapping pins IO2, IO8: high", (17.78, 119.38))
    sh.note("LED data level shift, 3.3 V to 5 V", (205.74, 76.2))
    sh.note("Ambient light (auto-dimming)", (205.74, 152.4))
    sh.note("Test points", (25.4, 167.64))


def led_rows(sh: Sheet, refs, caps, per_row, x0, y0, dx, dy, din, dout):
    """LEDs in rows, each row's DOUT to the next one's DIN; +5V and GND rails above and below each row."""
    rows = [refs[i:i + per_row] for i in range(0, len(refs), per_row)]
    for r, row in enumerate(rows):
        y = y0 + r * dy
        leds = [sh.part("orbit:WS2812B-2020", ref, x0 + c * dx, y) for c, ref in enumerate(row)]
        top, bottom = y - 12.7, y + 12.7
        start = x0 - 12.7
        sh.rail([(start, top)] + [(led.x, top) for led in leds])
        sh.rail([(start, bottom)] + [(led.x, bottom) for led in leds])
        sh.power("+5V", (start, top))
        sh.power("GND", (start, bottom))
        for led in leds:
            sh.wire(led.pin("4"), (led.x, top))
            sh.wire(led.pin("2"), (led.x, bottom))
        for a, b in zip(leds, leds[1:]):
            sh.wire(a.pin("1"), b.pin("3"))
        first, last = leds[0].pin("3"), leds[-1].pin("1")
        sh.wire(first, (first[0] - 5.08, first[1]))
        sh.wire(last, (last[0] + 5.08, last[1]))
        in_name = din if r == 0 else f"CHAIN_{row[0]}"
        out_name = dout if r == len(rows) - 1 else f"CHAIN_{rows[r + 1][0]}"
        sh.label(in_name, (first[0] - 5.08, first[1]), "left", hier="input" if r == 0 else None)
        if out_name:
            sh.label(out_name, (last[0] + 5.08, last[1]), "right",
                     hier="output" if r == len(rows) - 1 and out_name == "DOUT" else None)
        else:
            sh.no_connect((last[0] + 5.08, last[1]))
    return rows


def cap_bank(sh: Sheet, caps, per_row, x0, y0, dx, dy):
    for r in range(0, len(caps), per_row):
        row = caps[r:r + per_row]
        y = y0 + (r // per_row) * dy
        cs = [sh.part("orbit:C_100n_0603", ref, x0 + c * dx, y) for c, ref in enumerate(row)]
        start = x0 - 7.62
        sh.rail([(start, y - 3.81)] + [c.pin("1") for c in cs])
        sh.rail([(start, y + 3.81)] + [c.pin("2") for c in cs])
        sh.power("+5V", (start, y - 3.81))
        sh.power("GND", (start, y + 3.81))


def draw_minutes(sh: Sheet):
    leds = [f"D{i + 1}" for i in range(N_MINUTE)]
    caps = [f"C{101 + i}" for i in range(N_MINUTE)]
    led_rows(sh, leds, caps, 12, 38.1, 50.8, 30.48, 38.1, "DIN", "DOUT")
    cap_bank(sh, caps, 20, 40.64, 236.22, 15.24, 20.32)
    sh.note("Minute ring: D1-D60 on a 50 mm radius, D1 at 12 o'clock, data clockwise", (25.4, 25.4), 2.54)
    sh.note("C101-C160: 100 nF, one beside each LED (C101 at D1 ... C160 at D60)", (25.4, 226.06))


def draw_hours(sh: Sheet):
    leds = [f"D{N_MINUTE + i + 1}" for i in range(N_HOUR)]
    caps = [f"C{101 + N_MINUTE + i}" for i in range(N_HOUR)]
    led_rows(sh, leds, caps, 6, 38.1, 50.8, 30.48, 38.1, "DIN", "LED_DOUT")
    cap_bank(sh, caps, 12, 40.64, 142.24, 15.24, 22.86)
    tp = sh.part("orbit:TestPoint", "TP6", 236.22, 106.68)
    sh.wire(tp.pin("1"), (236.22, 111.76))
    sh.label("LED_DOUT", (236.22, 111.76), "down")
    sh.note("Hour ring: D61-D72 on a 38 mm radius, D61 at 12 o'clock, data clockwise", (25.4, 25.4), 2.54)
    sh.note("C161-C172: 100 nF, one beside each LED", (25.4, 129.54))
    sh.note("TP6: the chain's end, for a test or a second ring", (218.44, 127.0))


DRAW = {"/": draw_root, "Power": draw_power, "MCU": draw_mcu, "Minute ring": draw_minutes, "Hour ring": draw_hours}


def main():
    ensure_hierarchy()
    with kicad_sch.edit(str(ROOT)) as s:
        hierarchy = s.get_hierarchy()
        sheets = {"/": hierarchy.root}
        for child in hierarchy.root.children:
            sheets[child.name] = child
        existing = [sym.reference for sym in s.get_symbols()]
        Sheet.counter = max([int(r[4:]) for r in existing if r.startswith(("#PWR", "#FLG"))] or [0])
        for name, instance in sheets.items():
            sub = s if name == "/" else s.for_sheet(instance)
            if [sym for sym in sub.get_symbols()]:
                print(f"{name}: has symbols, left as it is")
                continue
            sheet = Sheet(sub, name)
            DRAW[name](sheet)
            sheet.finish()
            print(f"{name}: {len(sheet.items)} items, {len(sheet.pin_ends)} pins")


if __name__ == "__main__":
    main()
