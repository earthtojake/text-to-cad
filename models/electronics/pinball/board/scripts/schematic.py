# /// script
# dependencies = ["shapely>=2", "scipy"]
# ///
"""SHORT CIRCUIT's playfield schematic, written as text (no KiCad needed; rerunning writes the same files).

    cad run scripts/schematic.py     then   cad kicad_sch erc pinball.kicad_sch

A root sheet (the machine in one look, the board's mechanics) and six sheets: Power, MCU, Inputs (the ball's
switches, the buttons, the tilt), Lighting, Flippers, Audio and backbox. The GPIO map and the LED chain's order come
from the board's geometry (geometry.gpio_map, geometry.leds), so the schematic and the layout agree by construction.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import geometry as G  # noqa: E402
from schlib import Sheet, uid  # noqa: E402

L = G.L
OUT = str(G.PROJECT)
GPIO = G.gpio_map()
SENSORS = G.sensors()
LEDS = G.leds()
HOLES = G.holes()

root_uuid = uid("root", "pinball.kicad_sch")
ROOT = Sheet("SHORT CIRCUIT", "pinball.kicad_sch", f"/{root_uuid}", "SHORT CIRCUIT: the playfield", "A3", root_uuid)
SHEETS: list[Sheet] = []


def child(name, file, title, paper="A3"):
    s = Sheet(name, file, "", title, paper)
    s.path = f"/{root_uuid}/{s.sheet_uuid}"
    SHEETS.append(s)
    return s


P = "pinball:"


def finish(sheet: Sheet):
    """A junction dot wherever three or more ends meet (each tee's wires are split at it)."""
    from collections import Counter
    counts = Counter(sheet.ends)
    for at, n in counts.items():
        if n >= 3:
            sheet.junction(at)


def cap_bank(s: Sheet, rail_y, xs, specs, net, gnd_y=None):
    """Capacitors standing in a row under a rail: the rail joins their top pins, a ground wire their bottom pins."""
    parts = []
    for x, (ref, part) in zip(xs, specs):
        parts.append(s.symbol(P + part, ref, x, rail_y + 3.81))
    tops = [p.pin("1") for p in parts]
    bottoms = [p.pin("2") for p in parts]
    if len(parts) > 1:
        s.wire(*tops)
        s.wire(*bottoms)
    s.power("GND", (bottoms[0][0], bottoms[0][1] + 2.54))
    s.wire(bottoms[0], (bottoms[0][0], bottoms[0][1] + 2.54))
    return tops


# ===================================================================================================== Power

def draw_power(s: Sheet):
    s.box(20.32, 25.4, 134.62, 137.16, "USB-C: 9 V from any PD charger, USB 2.0 data, ESD")
    j1 = s.symbol(P + "USB_C_Receptacle", "J1", 40.64, 88.9, ref_at=(30.48, 60.96), value_at=(30.48, 63.5))
    vb, gnd, sh = j1.pin("A4"), j1.pin("A1"), j1.pin("SH")
    s.wire(sh, (sh[0], gnd[1] + 5.08), (gnd[0], gnd[1] + 5.08))
    s.wire(gnd, (gnd[0], gnd[1] + 5.08))
    s.wire((gnd[0], gnd[1] + 5.08), (gnd[0] + 7.62, gnd[1] + 5.08))
    s.power("PWR_FLAG", (gnd[0] + 7.62, gnd[1] + 5.08))
    s.wire((gnd[0], gnd[1] + 5.08), (gnd[0], gnd[1] + 7.62))
    s.power("GND", (gnd[0], gnd[1] + 7.62))
    # VBUS rail: the connector, its flag, the ESD array's clamp, the polyfuse
    rail = vb[1]
    f1 = s.symbol(P + "Polyfuse_2A", "F1", 106.68, rail, 90, ref_at=(104.14, rail - 5.08), value_at=(104.14, rail - 3.0))
    s.wire(vb, (66.04, rail), (73.66, rail), (81.28, rail), f1.pin("1"))
    s.power("VBUS", (66.04, rail))
    s.power("PWR_FLAG", (73.66, rail))
    s.wire(f1.pin("2"), (116.84, rail), (124.46, rail))
    s.power("+9V", (116.84, rail))
    s.power("PWR_FLAG", (124.46, rail))
    # CC to the PD trigger, on the sheet below
    for pin, net in (("A5", "CC1"), ("B5", "CC2")):
        p = j1.pin(pin)
        s.wire(p, (63.5, p[1]))
        s.label(net, (63.5, p[1]), (1, 0))
    s.nc(j1.pin("A8"))
    s.nc(j1.pin("B8"))
    # D- (A7, B7) and D+ (A6, B6) joined, through the ESD array (flow-through: 1-6 and 3-4)
    u4 = s.symbol(P + "USBLC6-2SC6", "U4", 81.28, 93.98, ref_at=(87.63, 80.01), value_at=(87.63, 82.55))
    a7, b7, a6, b6 = (j1.pin(n) for n in ("A7", "B7", "A6", "B6"))
    s.wire(a7, (58.42, a7[1]), (58.42, b7[1]))
    s.wire(b7, (58.42, b7[1]))
    s.wire((58.42, a7[1]), (71.12, a7[1]), (71.12, u4.pin("1")[1]), u4.pin("1"))
    s.wire(b6, (60.96, b6[1]))
    s.wire(a6, (60.96, a6[1]))
    s.wire((60.96, a6[1]), (60.96, b6[1]))
    s.wire((60.96, b6[1]), (66.04, b6[1]), (66.04, u4.pin("3")[1]), u4.pin("3"))
    s.stub(u4, "2", "GND", 2.54, kind="power")
    s.wire(u4.pin("5"), (u4.pin("5")[0], rail))
    # the array is flow-through (its pins 1-6 and 3-4 one node each): one net each side, the pair runs straight on
    s.label("USB_D-", (59.69, a7[1]), (1, 0))
    s.label("USB_D+", (67.31, u4.pin("3")[1]), (1, 0))
    for number, net in (("6", "USB_D-"), ("4", "USB_D+")):
        p = u4.pin(number)
        s.wire(p, (101.6, p[1]))
        s.label(net, (101.6, p[1]), (1, 0), kind="hier")

    s.box(20.32, 142.24, 134.62, 248.92, "PD trigger: CH224K asks the charger for 9 V")
    u3 = s.symbol(P + "CH224K", "U3", 63.5, 203.2, ref_at=(71.12, 187.96), value_at=(71.12, 190.5))
    for number, net in (("7", "CC1"), ("6", "CC2")):
        p = u3.pin(number)
        s.wire(p, (45.72, p[1]))
        s.label(net, (45.72, p[1]), (-1, 0))
    for number in ("4", "5", "2", "3", "10"):
        s.nc(u3.pin(number))
    s.stub(u3, "11", "GND", 2.54, kind="power")
    # CFG1: 6.8k to ground asks for 9 V (WCH's table: 6.8k 9 V, 24k 12 V, 56k 15 V, open 20 V)
    r3 = s.symbol(P + "R_6k8", "R3", 88.9, 208.28)
    cfg = u3.pin("9")
    s.wire(cfg, (88.9, cfg[1]), r3.pin("1"))
    s.label("PD_CFG1", (80.01, cfg[1]), (1, 0))
    s.stub(r3, "2", "GND", 2.54, kind="power")
    # VDD: from VBUS through 1k (the chip clamps it), 1 uF down; pin 8 senses VBUS
    vdd, vbus = u3.pin("1"), u3.pin("8")
    s.wire(vbus, (vbus[0], 170.18))
    s.power("VBUS", (vbus[0], 170.18))
    r2 = s.symbol(P + "R_1k", "R2", vdd[0] + 12.7, 170.18)
    s.power("VBUS", r2.pin("1"))
    node = (vdd[0] + 12.7, 180.34)
    s.wire(r2.pin("2"), node)
    s.wire(vdd, (vdd[0], 180.34), node)
    s.label("PD_VDD", (vdd[0] + 1.27, 180.34), (1, 0))
    c1 = s.symbol(P + "C_1u", "C1", vdd[0] + 20.32, 184.15)
    s.wire(node, (vdd[0] + 16.51, 180.34), c1.pin("1"))
    s.power("PWR_FLAG", (vdd[0] + 16.51, 180.34))
    s.stub(c1, "2", "GND", 2.54, kind="power")
    s.text("CH224K's DP/DM stay open: the RP2040 owns USB data; PG unused: firmware reads VBUS (VBUS_SENSE).", (22.86, 243.84))

    s.box(142.24, 25.4, 330.2, 137.16, "5 V: TPS563201 buck, 3 A (LEDs, amplifier, the backbox)")
    u5 = s.symbol(P + "TPS563201", "U5", 215.9, 76.2, ref_at=(205.74, 66.04), value_at=(205.74, 68.58))
    vin, en = u5.pin("3"), u5.pin("5")
    x0 = vin[0] - 45.72
    s.power("+9V", (x0, vin[1]))
    c2 = s.symbol(P + "C_10u", "C2", x0 + 12.7, vin[1] + 3.81)
    c3 = s.symbol(P + "C_100n", "C3", x0 + 22.86, vin[1] + 3.81)
    tap = x0 + 33.02
    s.wire((x0, vin[1]), c2.pin("1"), c3.pin("1"), (tap, vin[1]), vin)
    s.wire(c2.pin("2"), c3.pin("2"))
    s.stub(c2, "2", "GND", 2.54, kind="power")
    # EN pulled up to the input: down from the rail, across to the pin
    r4 = s.symbol(P + "R_100k", "R4", tap + 3.81, en[1], 90, ref_at=(tap, en[1] + 3.81), value_at=(tap + 6.35, en[1] + 3.81))
    s.wire((tap, vin[1]), r4.pin("1"))
    s.wire(r4.pin("2"), en)
    s.stub(u5, "1", "GND", 2.54, kind="power")
    sw, bst, fb = u5.pin("2"), u5.pin("6"), u5.pin("4")
    # SW rises to its own rail above the chip; the bootstrap C4 hangs from it down to VBST, so nothing crosses
    y5 = sw[1] - 10.16
    xsw, xc4 = sw[0] + 2.54, sw[0] + 12.7
    # turned over: pin 1 to VBST, pin 2 to SW, as the board has it
    c4 = s.symbol(P + "C_100n", "C4", xc4, y5 + 3.81, 180, ref_at=(xc4 + 2.54, y5 + 2.54), value_at=(xc4 + 2.54, y5 + 5.08))
    l1 = s.symbol(P + "L_4u7", "L1", 259.08, y5, 90, ref_at=(256.54, y5 - 5.08), value_at=(256.54, y5 - 2.54))
    s.wire(sw, (xsw, sw[1]), (xsw, y5), c4.pin("2"), l1.pin("1"))
    s.label("BUCK_SW", (xc4 + 1.27, y5), (1, 0))
    s.wire(bst, (xc4, bst[1]), c4.pin("1"))
    s.label("BUCK_BST", (bst[0] + 1.27, bst[1]), (1, 0))
    # the output: 2 x 22 uF, the divider (0.768 V x (1 + 56k / 10k) = 5.07 V)
    xs = [266.7, 276.86, 287.02]
    yfb = fb[1] + 5.08
    r5 = s.symbol(P + "R_56k", "R5", 287.02, y5 + 3.81)
    r6 = s.symbol(P + "R_10k", "R6", 287.02, yfb + 3.81)
    c5 = s.symbol(P + "C_22u", "C5", xs[0], y5 + 3.81)
    c6 = s.symbol(P + "C_22u", "C6", xs[1], y5 + 3.81)
    s.wire(l1.pin("2"), c5.pin("1"), c6.pin("1"), r5.pin("1"), (304.8, y5), (312.42, y5))
    s.power("+5V", (304.8, y5))
    s.power("PWR_FLAG", (312.42, y5))
    s.wire(c5.pin("2"), c6.pin("2"))
    s.stub(c5, "2", "GND", 2.54, kind="power")
    s.wire(r5.pin("2"), r6.pin("1"))
    s.wire(fb, (xsw + 2.54, fb[1]), (xsw + 2.54, yfb), (287.02, yfb))
    s.label("BUCK_FB", (243.84, yfb), (1, 0))
    s.stub(r6, "2", "GND", 2.54, kind="power")

    s.box(142.24, 142.24, 330.2, 248.92, "3.3 V: AP2112K LDO; VBUS sense for the firmware")
    u6 = s.symbol(P + "AP2112K-3.3", "U6", 215.9, 190.5, ref_at=(223.52, 180.34), value_at=(223.52, 182.88))
    vi, ee, vo = u6.pin("1"), u6.pin("3"), u6.pin("5")
    s.power("+5V", (177.8, vi[1]))
    c7 = s.symbol(P + "C_1u", "C7", 190.5, vi[1] + 3.81)
    s.wire((177.8, vi[1]), c7.pin("1"), (200.66, vi[1]), vi)
    s.wire((200.66, vi[1]), (200.66, ee[1]), ee)
    s.stub(c7, "2", "GND", 2.54, kind="power")
    s.stub(u6, "2", "GND", 2.54, kind="power")
    c8 = s.symbol(P + "C_1u", "C8", 241.3, vo[1] + 3.81)
    s.wire(vo, c8.pin("1"), (254.0, vo[1]))
    s.power("+3V3", (254.0, vo[1]))
    s.stub(c8, "2", "GND", 2.54, kind="power")
    # VBUS sense: 100k over 22k: 9 V reads 1.62 V, 15 V 2.70 V on GPIO29 (ADC3)
    r7 = s.symbol(P + "R_100k", "R7", 279.4, 177.8)
    r8 = s.symbol(P + "R_22k", "R8", 279.4, 193.04)
    s.power("+9V", r7.pin("1"))
    s.wire(r7.pin("2"), (279.4, 185.42), r8.pin("1"))
    s.wire((279.4, 185.42), (292.1, 185.42))
    s.label("VBUS_SENSE", (292.1, 185.42), (1, 0), kind="hier", shape="output")
    s.stub(r8, "2", "GND", 2.54, kind="power")
    s.text("Peak 18.2 W: 2.02 A at 9 V (coils 1.13 A, 5 V rail 1.45 A at 5 V): a 20 W charger or better (physics.py).", (144.78, 243.84))


# ======================================================================================================= MCU

def draw_mcu(s: Sheet):
    s.box(114.3, 30.48, 297.18, 276.86, "RP2040: every GPIO has a job")
    u1 = s.symbol(P + "RP2040", "U1", 215.9, 152.4, ref_at=(181.61, 104.14), value_at=(181.61, 106.68))
    # the right column: each GPIO its signal, in GPIO order
    names = {v: k for k, v in GPIO.items()}
    for g in range(30):
        pad = str(G.GPIO_PAD[g])
        s.stub(u1, pad, names[g], 7.62, kind="hier", shape="bidirectional")
    # ground, TESTEN
    gp = u1.pin("57")
    s.wire(gp, (gp[0], gp[1] + 2.54))
    s.power("GND", (gp[0], gp[1] + 2.54))
    te = u1.pin("19")
    s.wire(te, (te[0] - 7.62, te[1]))
    s.power("GND", (te[0] - 7.62, te[1]))
    # supplies on top: 3V3 to IOVDD, USB_VDD, ADC_AVDD, VREG_VIN; VREG_VOUT to DVDD (1V1)
    top = 86.36
    pins33 = [u1.pin(n) for n in ("48", "43", "1", "44")]
    xs33 = [p[0] for p in pins33]
    s.wire((xs33[0] - 7.62, top), *[(x, top) for x in xs33])
    for p in pins33:
        s.wire((p[0], top), p)
    s.power("+3V3", (xs33[0] - 7.62, top))
    vo, dv = u1.pin("45"), u1.pin("23")
    y11 = top - 5.08
    s.wire(vo, (vo[0], y11), (dv[0], y11), dv)
    s.wire((dv[0], y11), (dv[0] + 7.62, y11))
    s.power("+1V1", (dv[0] + 7.62, y11))
    # decoupling, grouped on one supply and one ground (one per pin on the board)
    y = 53.34
    s.text("3V3: on the board, each 100 nF stands over its pin, on the other side, via to via\n"
           "(U1's pins share vias where adjacent); 1 uF at VREG_VIN", (119.38, 40.64))
    specs = [(f"C{20 + i}", "C_100n") for i in range(8)] + [("C28", "C_1u")]
    xs = [132.08 + 12.7 * i for i in range(len(specs))]
    tops = cap_bank(s, y, xs, specs, "+3V3")
    s.wire((xs[0] - 5.08, tops[0][1]), tops[0])
    s.power("+3V3", (xs[0] - 5.08, tops[0][1]))
    s.text("1V1: 1 uF at VREG_VOUT, 100 nF at each DVDD", (241.3, 40.64))
    specs = [("C29", "C_1u_0402"), ("C30", "C_100n"), ("C31", "C_100n")]
    xs = [248.92 + 12.7 * i for i in range(3)]
    tops = cap_bank(s, y, xs, specs, "+1V1")
    s.wire((xs[0] - 5.08, tops[0][1]), tops[0])
    s.power("+1V1", (xs[0] - 5.08, tops[0][1]))
    # USB: 27 ohm in series, at the chip
    for net, number, ref, dy in (("USB_D-", "46", "R10", -2.54), ("USB_D+", "47", "R11", 3.81)):
        p = u1.pin(number)
        res = s.symbol(P + "R_27R", ref, p[0] - 15.24, p[1], 90, ref_at=(p[0] - 19.05, p[1] + dy), value_at=(p[0] - 13.97, p[1] + dy))
        s.wire(res.pin("2"), p)
        s.wire(res.pin("1"), (res.pin("1")[0] - 5.08, p[1]))
        s.label(net, (res.pin("1")[0] - 5.08, p[1]), (-1, 0), kind="hier")
    # flash, wired by name
    u2 = s.symbol(P + "W25Q128JVS", "U2", 149.86, 228.6, ref_at=(124.46, 210.82), value_at=(124.46, 213.36))
    qspi = {"56": "QSPI_SS", "52": "QSPI_SCLK", "53": "QSPI_SD0", "55": "QSPI_SD1", "54": "QSPI_SD2", "51": "QSPI_SD3"}
    flash = {"QSPI_SS": "1", "QSPI_SCLK": "6", "QSPI_SD0": "5", "QSPI_SD1": "2", "QSPI_SD2": "3", "QSPI_SD3": "7"}
    for number, net in qspi.items():
        s.stub(u1, number, net, 5.08)
        s.stub(u2, flash[net], net, 5.08)
    v8 = u2.pin("8")
    s.wire(v8, (v8[0], v8[1] - 2.54), (v8[0] + 15.24, v8[1] - 2.54))
    s.power("+3V3", (v8[0], v8[1] - 2.54))
    s.wire((v8[0] + 15.24, v8[1] - 2.54), (v8[0] + 22.86, v8[1] - 2.54))
    c32 = s.symbol(P + "C_100n", "C32", v8[0] + 22.86, v8[1] + 1.27)
    s.stub(c32, "2", "GND", 2.54, kind="power")
    s.stub(u2, "4", "GND", 2.54, kind="power")
    # crystal: 12 MHz, 15 pF loads, 1k on XOUT (RP2040's reference design)
    xi, xo = u1.pin("20"), u1.pin("21")
    # the load capacitors' columns stand clear of the crystal's pins, so no dot sits on a pin number
    y1 = s.symbol(P + "Crystal_12M", "Y1", 161.29, xo[1] + 5.08, ref_at=(140.97, xo[1] + 3.81), value_at=(140.97, xo[1] + 6.35))
    xl, xr = 153.67, 168.91
    r12 = s.symbol(P + "R_1k", "R12", 173.99, xo[1], 90, ref_at=(170.18, xo[1] - 2.54), value_at=(175.26, xo[1] - 2.54))
    s.wire(xo, r12.pin("2"))
    s.label("XOUT", (r12.pin("2")[0] + 1.27, xo[1]), (1, 0))
    s.wire(r12.pin("1"), (xr, xo[1]), (xr, y1.pin("3")[1]), y1.pin("3"))
    s.wire(xi, (xl, xi[1]), (xl, y1.pin("1")[1]), y1.pin("1"))
    s.label("XIN", (177.8, xi[1]), (1, 0))
    c33 = s.symbol(P + "C_15p", "C33", xl, y1.pin("1")[1] + 8.89, ref_at=(xl - 8.89, y1.pin("1")[1] + 7.62), value_at=(xl - 8.89, y1.pin("1")[1] + 10.16))
    c34 = s.symbol(P + "C_15p", "C34", xr, y1.pin("3")[1] + 8.89)
    s.wire((xl, y1.pin("1")[1]), c33.pin("1"))
    s.wire((xr, y1.pin("3")[1]), c34.pin("1"))
    s.wire(c33.pin("2"), (y1.pin("2")[0], c33.pin("2")[1]), c34.pin("2"))
    s.wire(y1.pin("2"), (y1.pin("2")[0], c33.pin("2")[1]))
    s.stub(c33, "2", "GND", 2.54, kind="power")
    # RUN, BOOTSEL, SWD
    run = u1.pin("26")
    sw2 = s.symbol(P + "SW_Tactile", "SW2", 165.1, run[1] - 10.16, value="RESET", ref_at=(161.29, run[1] - 13.97), value_at=(166.37, run[1] - 13.97))
    s.wire(run, (172.72, run[1]), (172.72, run[1] - 10.16), sw2.pin("2"))
    s.label("RUN", (173.99, run[1]), (1, 0))
    s.wire(sw2.pin("1"), (154.94, sw2.pin("1")[1]), (154.94, sw2.pin("1")[1] + 2.54))
    s.power("GND", (154.94, sw2.pin("1")[1] + 2.54))
    yb = 133.35
    r13 = s.symbol(P + "R_1k", "R13", 146.05, yb, 90, ref_at=(142.24, yb - 3.81), value_at=(147.32, yb - 3.81))
    s.stub(r13, "2", "QSPI_SS", 2.54)
    sw1 = s.symbol(P + "SW_Tactile", "SW1", 128.27, yb, value="BOOTSEL", ref_at=(120.65, yb - 3.81), value_at=(125.73, yb - 3.81))
    s.wire(r13.pin("1"), sw1.pin("2"))
    s.wire(sw1.pin("1"), (sw1.pin("1")[0] - 2.54, sw1.pin("1")[1]), (sw1.pin("1")[0] - 2.54, sw1.pin("1")[1] + 2.54))
    s.power("GND", (sw1.pin("1")[0] - 2.54, sw1.pin("1")[1] + 2.54))
    for number, net, ref, x in (("24", "SWCLK", "TP1", 147.32), ("25", "SWDIO", "TP2", 157.48)):
        s.stub(u1, number, net, 5.08)
        tp = s.symbol(P + "TestPoint", ref, x, 261.62, value=net, ref_at=(x - 1.27, 256.54), value_at=(x - 1.27, 254.0))
        s.wire(tp.pin("1"), (x, 264.16))
        s.label(net, (x, 264.16), (0, 1))
    tp3 = s.symbol(P + "TestPoint", "TP3", 137.16, 261.62, value="3V3", ref_at=(135.89, 256.54), value_at=(135.89, 254.0))
    s.wire(tp3.pin("1"), (137.16, 264.16))
    s.power("+3V3", (137.16, 264.16), angle=180)
    tp4 = s.symbol(P + "TestPoint", "TP4", 127.0, 261.62, value="GND", ref_at=(125.73, 256.54), value_at=(125.73, 254.0))
    s.wire(tp4.pin("1"), (127.0, 264.16))
    s.power("GND", (127.0, 264.16))
    # I2C pull-ups
    x = 271.78
    for ref, net, xx in (("R14", "I2C_SDA", x), ("R15", "I2C_SCL", x + 10.16)):
        res = s.symbol(P + "R_4k7", ref, xx, 248.92)
        s.power("+3V3", res.pin("1"))
        s.wire(res.pin("2"), (xx, 256.54))
        s.label(net, (xx, 256.54), (0, 1))
    s.text("I2C: to the tilt sensor (Inputs) and the backglass (Audio and backbox)", (220.98, 236.22))


# ==================================================================================================== Inputs

def draw_inputs(s: Sheet):
    s.box(25.4, 25.4, 325.12, 181.61, "THE BALL IS THE SWITCH: 18 gold combs, the steel ball shorts SENSE to GND")
    s.text("A comb's fingers are 0.4 mm on a 0.8 mm pitch; the 8 mm ball sags 5 um, less than the copper's 35 um, so it\n"
           "touches both nets. The combs are exposed metal: at each comb's land a TVS clamps a strike to ground and a 1k beside it\n"
           "limits what reaches the RP2040's pin, whose internal pull-up holds the line. SENSE_* is the comb's side, IN_* the pin's.",
           (27.94, 40.64))
    cols = 3
    for i, sn in enumerate(SENSORS):
        col, row = i % cols, i // cols
        x, y = 96.52 + col * 101.6, 58.42 + row * 20.32
        sw = s.symbol(P + "BallSwitch", sn.ref, x, y, value=sn.name, footprint=f"pinball:Comb_{sn.ref}", in_bom=False,
                      ref_at=(x - 2.54, y - 6.35), value_at=(x - 2.54, y - 3.81))
        a = sw.pin("1")
        node = (a[0] - 5.08, a[1])
        tvs = s.symbol(P + "TVS_5V", f"D{3 + i}", node[0], node[1] + 5.08, 270, hide_value=True, ref_at=(node[0] + 2.54, node[1] + 5.08))
        # the 1k stands well left of the comb's node, so SENSE_* reads on its own wire between them
        rx = node[0] - 25.4 - 3.81
        res = s.symbol(P + "R_1k", f"R{50 + i}", rx, a[1], 90, ref_at=(rx - 3.81, a[1] - 2.54), value_at=(rx + 1.27, a[1] - 2.54))
        s.wire(a, node, res.pin("2"))
        s.wire(node, tvs.pin("1"))
        s.label(sn.net, (res.pin("2")[0] + 1.27, node[1]), (1, 0))
        s.stub(tvs, "2", "GND", 1.27, kind="power")
        s.wire(res.pin("1"), (res.pin("1")[0] - 5.08, a[1]))
        s.label(sn.line, (res.pin("1")[0] - 5.08, a[1]), (-1, 0), kind="hier", shape="output")
        b = sw.pin("2")
        s.wire(b, (b[0] + 5.08, b[1]))
        s.power("GND", (b[0] + 5.08, b[1]))
    s.box(25.4, 187.96, 145.86, 254.0, "The player: flipper buttons in the rails, START on the lockdown bar")
    for i, (ref, part, value, net) in enumerate((("SW3", "SW_Flipper", "FLIP L", "BTN_FLIP_L"), ("SW4", "SW_Flipper", "FLIP R", "BTN_FLIP_R"),
                                                 ("SW5", "SW_Start", "START", "BTN_START"))):
        x, y = 66.04, 205.74 + i * 15.24
        sw = s.symbol(P + part, ref, x, y, value=value, ref_at=(x - 2.54, y - 6.35), value_at=(x - 2.54, y - 3.81))
        a = sw.pin("1")
        s.wire(a, (a[0] - 7.62, a[1]))
        s.label(net, (a[0] - 7.62, a[1]), (-1, 0), kind="hier", shape="output")
        b = sw.pin("2")
        s.wire(b, (b[0] + 5.08, b[1]))
        s.power("GND", (b[0] + 5.08, b[1]))
    s.box(153.48, 187.96, 325.12, 254.0, "Tilt: LIS3DH on I2C (0x19), polled")
    u9 = s.symbol(P + "LIS3DH", "U9", 215.9, 220.98, ref_at=(186.69, 205.74), value_at=(186.69, 208.28))
    vio, vdd = u9.pin("1"), u9.pin("14")
    y = vio[1] - 2.54
    c40 = s.symbol(P + "C_100n", "C40", 241.3, y + 3.81)
    c41 = s.symbol(P + "C_10u", "C41", 255.27, y + 3.81)
    s.wire(vio, (vio[0], y), (vdd[0], y), (vdd[0] + 7.62, y), c40.pin("1"), c41.pin("1"))
    s.wire(vdd, (vdd[0], y))
    s.power("+3V3", (vdd[0] + 7.62, y))
    s.wire(c40.pin("2"), c41.pin("2"))
    s.stub(c40, "2", "GND", 2.54, kind="power")
    g = u9.pin("5")
    s.wire(g, (g[0], g[1] + 2.54))
    s.power("GND", (g[0], g[1] + 2.54))
    for number, net in (("4", "I2C_SCL"), ("6", "I2C_SDA")):
        s.stub(u9, number, net, 10.16, kind="hier")
    cs = u9.pin("8")
    s.wire(cs, (cs[0] - 3.81, cs[1]), (cs[0] - 3.81, cs[1] + 5.08))
    s.power("+3V3", (cs[0] - 3.81, cs[1] + 5.08), angle=180)
    # SDO left open: its internal pull-up sets the address, 0x19
    for number in ("7", "9", "11", "13", "15", "16"):
        s.nc(u9.pin(number))


# ================================================================================================== Lighting

def draw_lighting(s: Sheet):
    s.box(20.32, 20.32, 383.54, 73.66, "3.3 V data up to 5 V: VIH of the chain is 0.7 VDD = 3.5 V")
    u7 = s.symbol(P + "74AHCT1G125", "U7", 73.66, 50.8, ref_at=(78.74, 30.48), value_at=(78.74, 33.02))
    a = u7.pin("2")
    s.wire(a, (a[0] - 5.08, a[1]))
    s.label("LED_DATA", (a[0] - 5.08, a[1]), (-1, 0), kind="hier", shape="input")
    oe = u7.pin("1")
    s.wire(oe, (oe[0] + 7.62, oe[1]), (oe[0] + 7.62, oe[1] + 2.54))
    s.power("GND", (oe[0] + 7.62, oe[1] + 2.54))
    s.stub(u7, "3", "GND", 1.27, kind="power")
    # VCC rises to its +5V; C50 hangs from it on the left, its ground clear of the data line
    vc = u7.pin("5")
    yv = vc[1] - 7.62
    c50 = s.symbol(P + "C_100n", "C50", vc[0] - 10.16, yv + 3.81, ref_at=(vc[0] - 20.32, yv + 2.54), value_at=(vc[0] - 20.32, yv + 5.08))
    s.wire(vc, (vc[0], yv), (vc[0] - 10.16, yv), c50.pin("1"))
    s.power("+5V", (vc[0], yv))
    s.stub(c50, "2", "GND", 2.54, kind="power")
    r20 = s.symbol(P + "R_33R", "R20", 99.06, a[1], 90, ref_at=(96.52, a[1] - 5.08), value_at=(96.52, a[1] - 2.54))
    s.wire(u7.pin("4"), r20.pin("1"))
    s.wire(r20.pin("2"), (109.22, a[1]))
    s.label("CHAIN_1", (109.22, a[1]), (1, 0))
    s.text("33 ohm at U7's output damps the 5 V edge into LED1; U7 stands beside the RP2040, C50 at its supply pin.",
           (27.94, 71.12))
    c51 = s.symbol(P + "CP_220u", "C51", 137.16, a[1], ref_at=(140.97, a[1] - 2.54), value_at=(140.97, a[1] + 2.54))
    s.power("+5V", c51.pin("1"))
    s.stub(c51, "2", "GND", 2.54, kind="power")
    s.text("C51: the rail's reservoir for the chain's surges", (153.67, a[1] + 0.635))

    s.text(f"The chain: LED1 to LED{len(LEDS)}, in the order the data visits them on the board. A label says what each lights\n"
           "(the inserts' reverse-mount SK6812MINI-E sit in cut-outs under the windows; WS2812B-2020 elsewhere).", (215.9, 35.56))
    per_row, dx, dy = 11, 31.75, 38.1
    x0, y0 = 45.72, 96.52
    rows = [LEDS[i:i + per_row] for i in range(0, len(LEDS), per_row)]
    for r_i, row in enumerate(rows):
        y = y0 + r_i * dy
        top, bottom = y - 12.7, y + 12.7
        placed = []
        for c, led in enumerate(row):
            x = x0 + c * dx
            value = led.what
            part = s.symbol(P + led.package, led.ref, x, y, value=value, ref_at=(x + 2.54, y - 8.89), value_at=(x + 1.27, y + 10.16))
            placed.append((part, led))
        pins = {"SK6812MINI-E": dict(VDD="3", VSS="1", DIN="2", DOUT="4"), "WS2812B-2020": dict(DOUT="1", VSS="2", DIN="3", VDD="4")}
        start = x0 - 16.51
        s.wire((start, top), *[(p.x, top) for p, _ in placed])
        s.wire((start + 5.08, bottom), *[(p.x, bottom) for p, _ in placed])
        s.power("+5V", (start, top))
        s.power("GND", (start + 5.08, bottom))
        for p, led in placed:
            pn = pins[led.package]
            s.wire(p.pin(pn["VDD"]), (p.x, top))
            s.wire(p.pin(pn["VSS"]), (p.x, bottom))
        for (a, la), (b, lb) in zip(placed, placed[1:]):
            s.wire(a.pin(pins[la.package]["DOUT"]), b.pin(pins[lb.package]["DIN"]))
        first_part, first_led = placed[0]
        fp = first_part.pin(pins[first_led.package]["DIN"])
        s.wire(fp, (fp[0] - 5.08, fp[1]))
        n_first = LEDS.index(first_led) + 1
        s.label(f"CHAIN_{n_first}", (fp[0] - 5.08, fp[1]), (-1, 0))
        last_part, last_led = placed[-1]
        lp = last_part.pin(pins[last_led.package]["DOUT"])
        n_last = LEDS.index(last_led) + 1
        if n_last < len(LEDS):
            s.wire(lp, (lp[0] + 5.08, lp[1]))
            s.label(f"CHAIN_{n_last + 1}", (lp[0] + 5.08, lp[1]), (1, 0))
        else:
            s.nc(lp)
    s.text("One 100 nF at each LED: C101 beside LED1 ... C138 beside LED38", (27.94, 238.76))
    per_row, dx = 19, 13.97
    for r_i in range(0, len(LEDS), per_row):
        row = LEDS[r_i:r_i + per_row]
        y = 246.38 + (r_i // per_row) * 22.86
        specs = [(f"C{100 + r_i + k + 1}", "C_100n") for k in range(len(row))]
        xs = [38.1 + dx * k for k in range(len(row))]
        tops = cap_bank(s, y, xs, specs, "+5V")
        s.wire((xs[0] - 5.08, tops[0][1]), tops[0])
        s.power("+5V", (xs[0] - 5.08, tops[0][1]))


# ================================================================================================== Flippers

def draw_flippers(s: Sheet):
    s.box(25.4, 25.4, 279.4, 165.1, "Flipper coils: Takaha CA07300160, 16 ohm, 5.06 W at 9 V, a 10.9 ms stroke")
    s.text("Low-side AO3400A on each coil; SS34 catches the flyback; firmware fires, then holds by PWM. 3.3 V gate: Rds(on) ~45 mOhm.", (30.48, 38.1))
    for k, (side, net, q, rg, rd, d, j) in enumerate((("LEFT", "COIL_L", "Q1", "R30", "R31", "D1", "J2"),
                                                       ("RIGHT", "COIL_R", "Q2", "R32", "R33", "D2", "J3"))):
        x0 = 45.72 + k * 116.84
        yq = 114.3
        s.text(f"{side} FLIPPER", (x0, 53.34), size=1.8, bold=True)
        xq = x0 + 48.26
        qq = s.symbol(P + "AO3400A", q, xq, yq, ref_at=(xq + 5.08, yq - 2.54), value_at=(xq + 5.08, yq))
        g = qq.pin("1")
        r_g = s.symbol(P + "R_100R", rg, x0 + 20.32, yq, 90, ref_at=(x0 + 17.78, yq - 5.08), value_at=(x0 + 17.78, yq - 2.54))
        s.wire(r_g.pin("2"), g)
        s.label(f"GATE_{side[0]}", (x0 + 30.48, yq), (1, 0))
        s.wire(r_g.pin("1"), (x0 + 7.62, yq))
        s.label(net, (x0 + 7.62, yq), (-1, 0), kind="hier", shape="input")
        r_d = s.symbol(P + "R_10k", rd, x0 + 27.94, yq + 8.89)
        s.wire((x0 + 27.94, yq), r_d.pin("1"))
        s.junction((x0 + 27.94, yq))
        s.stub(r_d, "2", "GND", 2.54, kind="power")
        s.stub(qq, "2", "GND", 2.54, kind="power")
        dr = qq.pin("3")
        top = 68.58
        # the flyback diode: its cathode (pin 1, up at 270 degrees) to +9V, its anode to the drain
        dd = s.symbol(P + "SS34", d, dr[0] + 12.7, 83.82, 270, ref_at=(dr[0] + 15.24, 82.55), value_at=(dr[0] + 15.24, 85.09))
        jj = s.symbol(P + "Conn_Coil", j, dr[0] - 15.24, 76.2, ref_at=(dr[0] - 20.32, 71.12), value_at=(dr[0] - 20.32, 73.66))
        p1, p2 = jj.pin("1"), jj.pin("2")
        an = dd.pin("2")
        s.wire(dr, (dr[0], an[1]), (dr[0], p2[1]), p2)
        s.wire(an, (dr[0], an[1]))
        s.label(f"COIL_{side[0]}_DRAIN", (dr[0], dr[1] - 2.54), (0, -1))
        s.wire(p1, (dr[0] + 5.08, p1[1]), (dr[0] + 5.08, top), (dd.pin("1")[0], top), dd.pin("1"))
        s.wire((dr[0] + 5.08, top), (dr[0] + 5.08, top - 2.54))
        s.power("+9V", (dr[0] + 5.08, top - 2.54))
    s.box(25.4, 172.72, 279.4, 215.9, "Bulk: the coils' surge, at the drivers")
    c60 = s.symbol(P + "CP_220u", "C60", 66.04, 193.04, ref_at=(69.85, 190.5), value_at=(69.85, 195.58))
    c61 = s.symbol(P + "C_10u", "C61", 86.36, 193.04)
    c62 = s.symbol(P + "C_10u", "C62", 106.68, 193.04)
    s.wire((53.34, c60.pin("1")[1]), c60.pin("1"), c61.pin("1"), c62.pin("1"))
    s.power("+9V", (53.34, c60.pin("1")[1]))
    s.wire(c60.pin("2"), c61.pin("2"), c62.pin("2"))
    s.stub(c60, "2", "GND", 2.54, kind="power")


# ===================================================================================================== Audio

def draw_audio(s: Sheet):
    s.box(25.4, 25.4, 215.9, 165.1, "Sound: MAX98357A class-D (I2S in, 3.2 W), mono mix")
    u8 = s.symbol(P + "MAX98357A", "U8", 111.76, 96.52, ref_at=(99.06, 80.01), value_at=(99.06, 82.55))
    for number, net in (("1", "I2S_DIN"), ("14", "I2S_LRCLK"), ("16", "I2S_BCLK")):
        s.stub(u8, number, net, 10.16, kind="hier", shape="input")
    vdd = u8.pin("7")
    y = vdd[1] - 19.05
    c70 = s.symbol(P + "C_10u", "C70", vdd[0] + 12.7, y + 3.81)
    c71 = s.symbol(P + "C_100n", "C71", vdd[0] + 25.4, y + 3.81)
    s.wire(vdd, (vdd[0], y), c70.pin("1"), c71.pin("1"))
    s.wire((vdd[0] - 12.7, y), (vdd[0], y))
    s.power("+5V", (vdd[0] - 12.7, y))
    s.wire(c70.pin("2"), c71.pin("2"))
    s.stub(c70, "2", "GND", 2.54, kind="power")
    g, pad = u8.pin("3"), u8.pin("17")
    yg = g[1] + 5.08
    s.wire(g, (g[0], yg), (pad[0], yg), pad)
    s.wire((g[0], yg), (g[0], yg + 2.54))
    s.power("GND", (g[0], yg + 2.54))
    # ~SD_MODE: 1M to +5V, over the internal 100k: 0.45 V, (L+R)/2 (datasheet table); GAIN_SLOT open: 9 dB
    sd = u8.pin("4")
    y40 = sd[1] + 7.62
    r40 = s.symbol(P + "R_1M", "R40", sd[0] - 12.7, y40, 90, ref_at=(sd[0] - 15.24, y40 + 2.54), value_at=(sd[0] - 10.16, y40 + 2.54))
    s.wire(r40.pin("2"), (sd[0] - 2.54, y40), (sd[0] - 2.54, sd[1]), sd)
    s.wire(r40.pin("1"), (r40.pin("1")[0] - 5.08, y40))
    s.power("+5V", (r40.pin("1")[0] - 5.08, y40))
    s.nc(u8.pin("2"))
    op, on = u8.pin("9"), u8.pin("10")
    s.wire(op, (op[0] + 12.7, op[1]))
    s.label("SPK+", (op[0] + 12.7, op[1]), (1, 0))
    s.wire(on, (on[0] + 12.7, on[1]))
    s.label("SPK-", (on[0] + 12.7, on[1]), (1, 0))
    j5 = s.symbol(P + "Conn_Speaker", "J5", 147.32, 120.65, ref_at=(142.24, 115.57), value_at=(142.24, 118.11))
    s.wire(j5.pin("1"), (j5.pin("1")[0] + 7.62, j5.pin("1")[1]))
    s.label("SPK+", (j5.pin("1")[0] + 7.62, j5.pin("1")[1]), (1, 0))
    s.wire(j5.pin("2"), (j5.pin("2")[0] + 7.62, j5.pin("2")[1]))
    s.label("SPK-", (j5.pin("2")[0] + 7.62, j5.pin("2")[1]), (1, 0))
    s.text("J5: the speaker's pads; or the backbox speaker through J4", (142.24, 133.35))

    s.box(226.06, 25.4, 374.65, 165.1, "The backbox link: JST SH to the backglass board")
    j4 = s.symbol(P + "Conn_Backbox", "J4", 269.24, 90.17, ref_at=(261.62, 77.47), value_at=(261.62, 80.01))
    wires = {"1": "+5V", "2": "I2C_SDA", "3": "I2C_SCL", "4": "SPK+", "5": "SPK-", "6": "GND"}
    for number, net in wires.items():
        p = j4.pin(number)
        if net.startswith("SPK"):
            # the speaker pair's labels stand further out than the I2C pair's, so the stacked names stay apart
            s.wire(p, (p[0] + 22.86, p[1]))
            s.label(net, (p[0] + 22.86, p[1]), (1, 0))
            continue
        s.wire(p, (p[0] + 7.62, p[1]))
        if net == "+5V":
            s.power(net, (p[0] + 7.62, p[1]))
        elif net == "GND":
            s.wire((p[0] + 7.62, p[1]), (p[0] + 7.62, p[1] + 2.54))
            s.power(net, (p[0] + 7.62, p[1] + 2.54))
        elif net.startswith("I2C"):
            s.label(net, (p[0] + 7.62, p[1]), (1, 0), kind="hier")
        else:
            s.label(net, (p[0] + 7.62, p[1]), (1, 0))
    s.text("The backglass board (IS31FL3741, 351 LEDs, title traces) takes +5V and I2C.", (231.14, 139.7))


# ====================================================================================================== Root

def draw_root(s: Sheet, power, mcu, inputs, lighting, flippers, audio):
    s.text("SHORT CIRCUIT: a pinball machine whose playfield is its circuit board", (30.48, 22.86), size=2.54, bold=True)
    s.text("112 x 236 mm, 4 layers, ENIG. F.Cu: the art and the ball's switches. In1: ground. In2 and B.Cu: the wiring, parts on the back.", (30.48, 27.94))
    y0 = 38.1
    # the MCU's right column, grouped by the sheet each group goes to
    input_pins = [sn.line for sn in SENSORS] + ["BTN_FLIP_L", "BTN_FLIP_R", "BTN_START", "I2C_SDA", "I2C_SCL"]
    pitch = 2.54
    ys = {}
    y = y0 + 5.08
    for n in input_pins:
        ys[n] = y
        y += pitch
    y_input_end = y
    y += 15.24
    ys["LED_DATA"] = y
    y_light = y
    y += 17.78
    ys["COIL_L"] = y
    y_flip = y
    ys["COIL_R"] = y + 2.54
    y += 2.54 + 17.78
    y_audio = y
    for n in ("I2S_BCLK", "I2S_LRCLK", "I2S_DIN"):
        ys[n] = y
        y += pitch
    y_end = y
    # sheet symbols
    x_mcu, w_mcu, x_in, w_in = 139.7, 55.88, 266.7, 55.88
    right_pins = input_pins + ["LED_DATA", "COIL_L", "COIL_R", "I2S_BCLK", "I2S_LRCLK", "I2S_DIN"]
    pins = [(n, "bidirectional", "right", ys[n]) for n in right_pins]
    pins += [("USB_D+", "bidirectional", "left", y0 + 7.62), ("USB_D-", "bidirectional", "left", y0 + 10.16),
             ("VBUS_SENSE", "input", "left", y0 + 12.7)]
    pm = s.sheet_symbol(mcu, x_mcu, y0, w_mcu, y_end - y0 + 5.08, pins, 3)
    pp = s.sheet_symbol(power, 50.8, y0, 50.8, 22.86,
                        [("USB_D+", "bidirectional", "right", y0 + 7.62), ("USB_D-", "bidirectional", "right", y0 + 10.16),
                         ("VBUS_SENSE", "output", "right", y0 + 12.7)], 2)
    for n in ("USB_D+", "USB_D-", "VBUS_SENSE"):
        s.wire(pp[n], pm[n])
    pi = s.sheet_symbol(inputs, x_in, y0, w_in, y_input_end - y0 + 2.54,
                        [(n, "output" if n.startswith(("IN_", "BTN")) else "bidirectional", "left", ys[n]) for n in input_pins], 4)
    for n in input_pins:
        s.wire(pm[n], pi[n])
    pl = s.sheet_symbol(lighting, x_in, y_light - 5.08, w_in, 10.16, [("LED_DATA", "input", "left", ys["LED_DATA"])], 5)
    s.wire(pm["LED_DATA"], pl["LED_DATA"])
    pf = s.sheet_symbol(flippers, x_in, y_flip - 5.08, w_in, 12.7,
                        [("COIL_L", "input", "left", ys["COIL_L"]), ("COIL_R", "input", "left", ys["COIL_R"])], 6)
    s.wire(pm["COIL_L"], pf["COIL_L"])
    s.wire(pm["COIL_R"], pf["COIL_R"])
    audio_pins = [(n, "input", "left", ys[n]) for n in ("I2S_BCLK", "I2S_LRCLK", "I2S_DIN")]
    audio_pins += [("I2C_SDA", "bidirectional", "left", y_end + 2.54), ("I2C_SCL", "bidirectional", "left", y_end + 5.08)]
    pa = s.sheet_symbol(audio, x_in, y_audio - 5.08, w_in, y_end - y_audio + 15.24, audio_pins, 7)
    for n in ("I2S_BCLK", "I2S_LRCLK", "I2S_DIN"):
        s.wire(pm[n], pa[n])
    # I2C joined by name: the wire to Inputs, the stub to Audio
    for n in ("I2C_SDA", "I2C_SCL"):
        s.wire(pa[n], (pa[n][0] - 5.08, pa[n][1]))
        s.label(n, (pa[n][0] - 5.08, pa[n][1]), (-1, 0))
        s.label(n, (pm[n][0] + 12.7, pm[n][1]), (1, 0))

    # the board's mechanics: every hole and fiducial, by what it fixes
    ym = 200.66
    s.box(30.48, ym - 12.7, 391.16, ym + 45.72, "Mechanics: holes (each named for the part it fixes, geometry.py), fiducials")
    per = 17
    for i, h in enumerate(HOLES):
        x, yy = 40.64 + (i % per) * 20.32, ym + (i // per) * 12.7
        fp = f"pinball:NPTH_{h.d:.1f}mm"
        s.symbol(P + "MountingHole", h.ref, x, yy, value=h.fixes, footprint=fp, in_bom=False,
                 ref_at=(x - 7.62, yy - 2.54), value_at=(x - 7.62, yy + 3.81))
    for i, (ref, *_rest) in enumerate(G.FIDUCIALS_TOP + G.FIDUCIALS_BOTTOM):
        x, yy = 40.64 + i * 20.32, ym + 3 * 12.7
        s.symbol(P + "Fiducial", ref, x, yy, in_bom=False, ref_at=(x - 2.54, yy - 2.54), value_at=(x - 7.62, yy + 3.81), hide_value=True)


def main():
    power = child("Power", "power.kicad_sch", "USB-C, the PD trigger, the 5 V buck, the 3.3 V LDO")
    mcu = child("MCU", "mcu.kicad_sch", "RP2040, flash, crystal, reset and boot, SWD")
    inputs = child("Inputs", "inputs.kicad_sch", "The ball's switches, the buttons, the tilt")
    lighting = child("Lighting", "lighting.kicad_sch", f"{len(LEDS)} addressable LEDs and their data")
    flippers = child("Flippers", "flippers.kicad_sch", "Two coil drivers and the coils' bulk capacitance")
    audio = child("Audio and backbox", "audio.kicad_sch", "MAX98357A, the speaker, the backbox link")
    draw_power(power)
    draw_mcu(mcu)
    draw_inputs(inputs)
    draw_lighting(lighting)
    draw_flippers(flippers)
    draw_audio(audio)
    draw_root(ROOT, power, mcu, inputs, lighting, flippers, audio)
    for sheet in SHEETS + [ROOT]:
        finish(sheet)
    ROOT.write(OUT, root=True)
    for sheet in SHEETS:
        sheet.write(OUT)
    print("wrote", ROOT.file, "and", ", ".join(s.file for s in SHEETS))


if __name__ == "__main__":
    main()
