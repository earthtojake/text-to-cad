"""Write the Nine macropad's schematic: a root sheet and three hierarchical sheets.

    python3 scripts/gen_schematic.py      (any Python 3.10+; no KiCad needed)

Rerunning writes the same files (every uuid is derived from its item's name). Check with
`cad kicad_sch erc macropad.kicad_sch` and `cad kicad_sch snapshot ... --sheet /mcu/`.
"""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from schlib import Sheet, uid  # noqa: E402

PROJ = os.path.dirname(HERE)

# GPIO of every signal the keys sheet needs (direct wiring: one GPIO per key, no matrix). Chosen from the
# board: each group leaves the RP2040 on the side facing where it goes, in the order it arrives, so no
# two cross (scripts/route.py).
GPIO = {"ENC_SW": 0, "ENC_B": 1, "ENC_A": 2,            # right side, top: out to the encoder
        "KEY9": 3, "KEY6": 4, "KEY3": 5,                 # right side: the right column's channel
        "KEY8": 9, "KEY5": 10, "KEY2": 11,               # right side, below IOVDD: the middle channel
        "KEY7": 26, "KEY4": 27, "LED_DATA": 28, "KEY1": 29}  # left side, top: the left channel
if os.environ.get("MACROPAD_GPIO"):  # a layout step may hand in its own key order
    GPIO.update({k: int(v) for k, v in (kv.split("=") for kv in os.environ["MACROPAD_GPIO"].split(","))})
KEYSIG = [f"KEY{i}" for i in range(1, 10)] + ["ENC_A", "ENC_B", "ENC_SW", "LED_DATA"]

R0402 = "Resistor_SMD:R_0402_1005Metric"
C0402 = "Capacitor_SMD:C_0402_1005Metric"
C0805 = "Capacitor_SMD:C_0805_2012Metric"
CAP100N = {"MPN": "CL05B104KO5NNNC", "LCSC": "C1525"}
CAP1U = {"MPN": "CL05A105KA5NQNC", "LCSC": "C52923"}

root_uuid = uid("root", "macropad.kicad_sch")
ROOT = Sheet("Nine", "macropad.kicad_sch", f"/{root_uuid}", "Nine: 3x3 RP2040 macropad", "A4", root_uuid)
SHEETS = []


def child(name, file, title, paper):
    s = Sheet(name, file, "", title, paper)
    s.sheet_uuid = uid("sheetsym", file)
    s.path = f"/{root_uuid}/{s.sheet_uuid}"
    SHEETS.append(s)
    return s


def cap_row(s: Sheet, x0, y, specs, top_net, bottom_net="GND", pitch=10.16, title=None):
    """Capacitors standing side by side, every top pin on one supply wire, every bottom pin on one ground wire."""
    parts = []
    for i, (ref, value, fp, fields) in enumerate(specs):
        parts.append(s.symbol("Device:C", ref, value, x0 + i * pitch, y, 0, fp, dict(fields)))
    tops = [p.pin("1") for p in parts]
    bots = [p.pin("2") for p in parts]
    lt, lb = (tops[0][0] - pitch / 2 - 2.54, tops[0][1]), (bots[0][0] - pitch / 2 - 2.54, bots[0][1])
    s.wire(lt, *tops)
    s.wire(lb, *bots)
    for p in tops[:-1] + bots[:-1]:
        s.junction(p)
    s.power(top_net, lt)
    s.power(bottom_net, lb)
    if title:
        s.text(title, (x0 - pitch / 2 - 2.54, y - 12.7), size=1.27, bold=False)
    return parts


# ---------------------------------------------------------------------------------------------------
# USB-C and power
# ---------------------------------------------------------------------------------------------------
usb = child("USB & Power", "usb_power.kicad_sch", "USB-C input, ESD, 5 V and 3.3 V rails", "A4")
usb.box(20, 50, 125, 140, "USB-C receptacle (USB 2.0 device), CC pull-downs, ESD")
J1 = usb.symbol("Connector:USB_C_Receptacle_USB2.0_16P", "J1", "USB4105-GF-A", 45, 95, 0,
                "Connector_USB:USB_C_Receptacle_GCT_USB4105-xx-A_16P_TopMnt_Horizontal",
                {"MPN": "USB4105-GF-A", "Manufacturer": "GCT", "Datasheet": "https://gct.co/files/drawings/usb4105.pdf"},
                ref_at=(38, 69), value_at=(38, 71.5))
# VBUS (four pins stacked) up to the VBUS symbol, with its PWR_FLAG
vb = J1.pin("A4")
usb.wire(vb, (vb[0] + 5.08, vb[1]))
usb.power("VBUS", (vb[0] + 5.08, vb[1]))
usb.wire((vb[0] + 5.08, vb[1]), (vb[0] + 15.24, vb[1]))
usb.junction((vb[0] + 5.08, vb[1]))
usb.power("PWR_FLAG", (vb[0] + 15.24, vb[1]))
# CC1 / CC2 to their 5.1k pull-downs (the device's Rd: 5.1 kOhm, USB Type-C spec 4.11)
usb.stub(J1, "A5", "CC1", 5.08)
usb.stub(J1, "B5", "CC2", 5.08)
R1 = usb.symbol("Device:R", "R1", "5.1k", 75, 70, 0, R0402, {"MPN": "0402WGF5101TCE", "LCSC": "C25905"})
R2 = usb.symbol("Device:R", "R2", "5.1k", 85, 70, 0, R0402, {"MPN": "0402WGF5101TCE", "LCSC": "C25905"})
for rr, net in ((R1, "CC1"), (R2, "CC2")):
    t = rr.pin("1")
    usb.wire(t, (t[0], t[1] - 2.54))
    usb.label(net, (t[0], t[1] - 2.54), (0, -1))
    usb.stub(rr, "2", "GND", 2.54, kind="power")
# D- (A7, B7) and D+ (A6, B6) joined, then into the ESD array
a7, b7, a6, b6 = J1.pin("A7"), J1.pin("B7"), J1.pin("A6"), J1.pin("B6")
xm, xp = a7[0] + 5.08, a7[0] + 7.62
usb.wire(a7, (xm, a7[1]), (xm, b7[1]))
usb.wire(b7, (xm, b7[1]))
usb.wire(a6, (xp, a6[1]), (xp, b6[1]))
usb.wire(b6, (xp, b6[1]))
# the pair runs straight to the MCU sheet; U4 (a shunt TVS array) hangs off it
usb.wire((xm, b7[1]), (110, b7[1]))
usb.junction((xm, b7[1]))
usb.label("USB_D-", (110, b7[1]), (1, 0), kind="hier")
usb.wire((xp, a6[1]), (110, a6[1]))
usb.junction((xp, a6[1]))
usb.label("USB_D+", (110, a6[1]), (1, 0), kind="hier")
U4 = usb.symbol("Power_Protection:PRTR5V0U2X", "U4", "PRTR5V0U2X", 92.71, 115, 0, "Package_TO_SOT_SMD:SOT-143",
                {"MPN": "PRTR5V0U2X,215", "Manufacturer": "Nexperia", "LCSC": "C12333",
                 "Datasheet": "https://assets.nexperia.com/documents/data-sheet/PRTR5V0U2X.pdf"},
                ref_at=(95, 104), value_at=(95, 106.5))
i1, i2 = U4.pin("2"), U4.pin("3")
usb.wire(i1, (i1[0] - 2.54, i1[1]))
usb.label("USB_D-", (i1[0] - 2.54, i1[1]), (-1, 0))
usb.wire(i2, (i2[0] + 2.54, i2[1]))
usb.label("USB_D+", (i2[0] + 2.54, i2[1]), (1, 0))
usb.stub(U4, "4", "VBUS", 2.54, kind="power")
usb.stub(U4, "1", "GND", 2.54, kind="power")
for n in ("A8", "B8"):
    usb.nc(J1.pin(n))
g, sh = J1.pin("A1"), J1.pin("SH")
usb.wire(sh, (sh[0], g[1] + 2.54), (g[0], g[1] + 2.54))
usb.wire(g, (g[0], g[1] + 2.54))
usb.junction((g[0], g[1] + 2.54))
usb.wire((g[0], g[1] + 2.54), (g[0], g[1] + 5.08))
usb.power("GND", (g[0], g[1] + 5.08))
usb.wire((g[0], g[1] + 5.08), (g[0] + 7.62, g[1] + 5.08))
usb.junction((g[0], g[1] + 5.08))
usb.power("PWR_FLAG", (g[0] + 7.62, g[1] + 5.08))
usb.text("Shield tied to GND. SBU unused. U4 clamps D+/D- to GND and VBUS.", (22, 136), 1.27, False)

usb.box(140, 50, 280, 140, "5 V: polyfuse; 3.3 V: AP2112K LDO (600 mA)")
F1 = usb.symbol("Device:Polyfuse", "F1", "500mA", 160, 70, 90, "Fuse:Fuse_1206_3216Metric",
                {"MPN": "0ZCJ0050FF2E", "Manufacturer": "Bel Fuse"}, ref_at=(160, 64), value_at=(160, 76))
p1, p2 = F1.pin("1"), F1.pin("2")
usb.wire((p1[0] - 7.62, p1[1]), p1)
usb.power("VBUS", (p1[0] - 7.62, p1[1]))
n5 = (p2[0] + 7.62, p2[1])
usb.wire(p2, n5)
usb.power("+5V", n5)
usb.wire(n5, (n5[0], n5[1] + 5.08))
usb.junction(n5)
usb.power("PWR_FLAG", (n5[0], n5[1] + 5.08), 180)
U3 = usb.symbol("Regulator_Linear:AP2112K-3.3", "U3", "AP2112K-3.3", 220, 75, 0, "Package_TO_SOT_SMD:SOT-23-5",
                {"MPN": "AP2112K-3.3TRG1", "LCSC": "C51118"}, ref_at=(215, 66), value_at=(215, 68.5))
vin, en, vout = U3.pin("1"), U3.pin("3"), U3.pin("5")
xj = vin[0] - 5.08
usb.wire((vin[0] - 12.7, vin[1]), (xj, vin[1]), vin)
usb.power("+5V", (vin[0] - 12.7, vin[1]))
usb.wire(en, (xj, en[1]), (xj, vin[1]))
usb.junction((xj, vin[1]))
usb.text("EN tied to VIN: always on", (vin[0] - 14, en[1] + 12), 1.27, False)
usb.wire(vout, (vout[0] + 7.62, vout[1]))
usb.power("+3V3", (vout[0] + 7.62, vout[1]))
usb.nc(U3.pin("4"))
usb.stub(U3, "2", "GND", 2.54, kind="power")
cap_row(usb, 175, 110, [("C1", "1uF", C0402, CAP1U)], "+5V", title="LDO input")
cap_row(usb, 225, 110, [("C2", "10uF", C0805, {"MPN": "CL21A106KAYNNNE", "LCSC": "C15850"}),
                        ("C3", "100nF", C0402, CAP100N)], "+3V3", title="LDO output, 3.3 V bulk")

# ---------------------------------------------------------------------------------------------------
# MCU
# ---------------------------------------------------------------------------------------------------
mcu = child("MCU", "mcu.kicad_sch", "RP2040, QSPI flash, 12 MHz crystal, boot and reset, SWD", "A3")
mcu.box(150, 85, 265, 210, "RP2040")
U1 = mcu.symbol("MCU_RaspberryPi:RP2040", "U1", "RP2040", 205, 150, 0,
                "Package_DFN_QFN:QFN-56-1EP_7x7mm_P0.4mm_EP3.2x3.2mm",
                {"MPN": "RP2040", "LCSC": "C2040", "Datasheet": "https://datasheets.raspberrypi.com/rp2040/rp2040-datasheet.pdf"},
                ref_at=(232, 95), value_at=(232, 97.5))
# supply pins along the top: 3V3 group and 1V1 group
top3 = [U1.pin(n) for n in ("48", "43", "1", "44")]  # USB_VDD, ADC_AVDD, IOVDD, VREG_VIN
yb = top3[0][1] - 5.08
for p in top3:
    mcu.wire(p, (p[0], yb))
mcu.wire((top3[0][0] - 5.08, yb), *[(p[0], yb) for p in sorted(top3)])
for p in sorted(top3)[:-1]:
    mcu.junction((p[0], yb))
mcu.power("+3V3", (top3[0][0] - 5.08, yb))
top1 = [U1.pin(n) for n in ("45", "23")]  # VREG_VOUT, DVDD
for p in top1:
    mcu.wire(p, (p[0], yb))
mcu.wire((top1[0][0], yb), (top1[1][0], yb), (top1[1][0] + 5.08, yb))
mcu.junction((top1[1][0], yb))
mcu.power("+1V1", (top1[1][0] + 5.08, yb))
mcu.stub(U1, "57", "GND", 2.54, kind="power")
mcu.stub(U1, "19", "GND", 5.08, kind="power", power_angle=270)  # TESTEN low
# GPIO: every used one to a hierarchical label, the rest marked unconnected
used = {v: k for k, v in GPIO.items()}
for gpio in range(30):
    num = {0: 2, 1: 3, 2: 4, 3: 5, 4: 6, 5: 7, 6: 8, 7: 9, 8: 11, 9: 12, 10: 13, 11: 14, 12: 15, 13: 16, 14: 17,
           15: 18, 16: 27, 17: 28, 18: 29, 19: 30, 20: 31, 21: 32, 22: 34, 23: 35, 24: 36, 25: 37, 26: 38,
           27: 39, 28: 40, 29: 41}[gpio]
    if gpio in used:
        mcu.stub(U1, str(num), used[gpio], 5.08, kind="hier", shape="output" if used[gpio] == "LED_DATA" else "input")
    else:
        mcu.nc(U1.pin(str(num)))
# QSPI flash
mcu.box(85, 120, 145, 175, "QSPI flash, 16 MB")
for num, net in (("56", "QSPI_SS"), ("52", "QSPI_SCLK"), ("53", "QSPI_SD0"), ("55", "QSPI_SD1"),
                 ("54", "QSPI_SD2"), ("51", "QSPI_SD3")):
    mcu.stub(U1, num, net, 5.08)
U2 = mcu.symbol("Memory_Flash:W25Q128JVS", "U2", "W25Q128JVS", 125, 150, 0, "Package_SO:SOIC-8_5.3x5.3mm_P1.27mm",
                {"MPN": "W25Q128JVSIQ", "LCSC": "C97521"}, ref_at=(128, 133), value_at=(128, 135.5))
for num, net in (("1", "QSPI_SS"), ("6", "QSPI_SCLK"), ("5", "QSPI_SD0"), ("2", "QSPI_SD1"),
                 ("3", "QSPI_SD2"), ("7", "QSPI_SD3")):
    mcu.stub(U2, num, net, 5.08)
mcu.stub(U2, "8", "+3V3", 2.54, kind="power")
mcu.stub(U2, "4", "GND", 2.54, kind="power")
cap_row(mcu, 100, 166, [("C4", "100nF", C0402, CAP100N)], "+3V3", title="flash VCC")
# USB data: 27 ohm series resistors (Hardware design with RP2040, section 2.4)
mcu.box(85, 180, 145, 205, "USB data: 27R series")
dp, dm = U1.pin("47"), U1.pin("46")
R3 = mcu.symbol("Device:R", "R3", "27", 120, 190, 90, R0402, {"MPN": "0402WGF270JTCE", "LCSC": "C25100"},
                ref_at=(120, 186.5), value_at=(120, 193.5))
R4 = mcu.symbol("Device:R", "R4", "27", 120, 196, 90, R0402, {"MPN": "0402WGF270JTCE", "LCSC": "C25100"},
                ref_at=(120, 201.5), value_at=(120, 204.5))
mcu.wire(R3.pin("2"), (128, 190))
mcu.label("RP_D-", (128, 190), (1, 0))
mcu.wire(R4.pin("2"), (128, 196))
mcu.label("RP_D+", (128, 196), (1, 0))
mcu.wire(R3.pin("1"), (105, 190))
mcu.label("USB_D-", (105, 190), (-1, 0), kind="hier")
mcu.wire(R4.pin("1"), (105, 196))
mcu.label("USB_D+", (105, 196), (-1, 0), kind="hier")
mcu.stub(U1, "46", "RP_D-", 5.08)
mcu.stub(U1, "47", "RP_D+", 5.08)
# crystal
mcu.box(85, 212, 175, 262, "12 MHz crystal (ABM8-272-T3, CL 10 pF): 15 pF loads, 1k on XOUT")
mcu.stub(U1, "20", "XIN", 5.08)
mcu.stub(U1, "21", "XOUT", 5.08)
Y1 = mcu.symbol("Device:Crystal_GND24", "Y1", "12MHz", 125, 230, 0, "Crystal:Crystal_SMD_3225-4Pin_3.2x2.5mm",
                {"MPN": "ABM8-272-T3", "Manufacturer": "Abracon"}, ref_at=(122, 223), value_at=(122, 225.5))
y1, y3, yg = Y1.pin("1"), Y1.pin("3"), Y1.pin("2")
na, nb = (y1[0] - 7.62, y1[1]), (y3[0] + 7.62, y3[1])
mcu.wire(y1, na)
mcu.wire(y3, nb)
C5 = mcu.symbol("Device:C", "C5", "15pF", na[0], na[1] + 10.16, 0, C0402, {"MPN": "CL05C150JB5NNNC", "LCSC": "C1548"})
C6 = mcu.symbol("Device:C", "C6", "15pF", nb[0], nb[1] + 10.16, 0, C0402, {"MPN": "CL05C150JB5NNNC", "LCSC": "C1548"})
mcu.wire(na, C5.pin("1"))
mcu.wire(nb, C6.pin("1"))
mcu.stub(C5, "2", "GND", 2.54, kind="power")
mcu.stub(C6, "2", "GND", 2.54, kind="power")
mcu.stub(Y1, "2", "GND", 2.54, kind="power")
mcu.wire(na, (na[0] - 7.62, na[1]))
mcu.junction(na)
mcu.label("XIN", (na[0] - 7.62, na[1]), (-1, 0))
R5 = mcu.symbol("Device:R", "R5", "1k", nb[0] + 10.16, nb[1], 90, R0402, {"MPN": "0402WGF1001TCE", "LCSC": "C11702"},
                ref_at=(nb[0] + 10, nb[1] - 3.5), value_at=(nb[0] + 10, nb[1] + 3.5))
mcu.wire(nb, R5.pin("1"))
mcu.junction(nb)
mcu.wire(R5.pin("2"), (R5.pin("2")[0] + 5.08, nb[1]))
mcu.label("XOUT", (R5.pin("2")[0] + 5.08, nb[1]), (1, 0))
# boot, reset, SWD
mcu.box(20, 40, 80, 160, "BOOTSEL, RESET, SWD pads")
mcu.stub(U1, "26", "RUN", 5.08)
mcu.stub(U1, "24", "SWCLK", 5.08)
mcu.stub(U1, "25", "SWDIO", 5.08)
R6 = mcu.symbol("Device:R", "R6", "1k", 35, 60, 0, R0402, {"MPN": "0402WGF1001TCE", "LCSC": "C11702"})
t = R6.pin("1")
mcu.wire(t, (t[0], t[1] - 2.54))
mcu.label("QSPI_SS", (t[0], t[1] - 2.54), (0, -1))
SW11 = mcu.symbol("Switch:SW_Push", "SW11", "BOOTSEL", 35, 75, 270, "Button_Switch_SMD:SW_SPST_B3U-1000P",
                  {"MPN": "B3U-1000P", "Manufacturer": "Omron"}, ref_at=(39, 73), value_at=(39, 77))
mcu.wire(R6.pin("2"), SW11.pin("1"))
mcu.stub(SW11, "2", "GND", 2.54, kind="power")
R7 = mcu.symbol("Device:R", "R7", "10k", 60, 60, 0, R0402, {"MPN": "0402WGF1002TCE", "LCSC": "C25744"})
mcu.stub(R7, "1", "+3V3", 2.54, kind="power")
SW12 = mcu.symbol("Switch:SW_Push", "SW12", "RESET", 60, 80, 270, "Button_Switch_SMD:SW_SPST_B3U-1000P",
                  {"MPN": "B3U-1000P", "Manufacturer": "Omron"}, ref_at=(64, 78), value_at=(64, 82))
nr = (R7.pin("2")[0], R7.pin("2")[1] + 3.81)
mcu.wire(R7.pin("2"), nr, SW12.pin("1"))
mcu.wire(nr, (nr[0] + 7.62, nr[1]))
mcu.junction(nr)
mcu.label("RUN", (nr[0] + 7.62, nr[1]), (1, 0))
mcu.stub(SW12, "2", "GND", 2.54, kind="power")
for i, net in enumerate(("SWCLK", "SWDIO", "GND", "+3V3")):
    x = 30 + i * 12.7
    tp = mcu.symbol("Connector:TestPoint", f"TP{i + 1}", net if net[0] != "+" else "3V3", x, 120, 0,
                    "TestPoint:TestPoint_Pad_D1.5mm", ref_at=(x + 1.5, 115), value_at=(x + 1.5, 117))
    if net in ("GND", "+3V3"):
        p = tp.pin("1")
        mcu.wire(p, (p[0], p[1] + 5.08))
        mcu.power(net, (p[0], p[1] + 5.08), 0 if net == "GND" else 180)
    else:
        mcu.stub(tp, "1", net, 5.08)
mcu.text("SWD: 1.5 mm pads on the bottom, 2.54 mm pitch", (22, 140), 1.27, False)
# decoupling (Hardware design with RP2040, 2.2: 100 nF at every IOVDD, 1 uF at VREG_VIN and VREG_VOUT)
mcu.box(280, 40, 405, 120, "RP2040 decoupling")
cap_row(mcu, 300, 65, [("C7", "100nF", C0402, CAP100N), ("C8", "100nF", C0402, CAP100N),
                       ("C9", "100nF", C0402, CAP100N), ("C10", "100nF", C0402, CAP100N),
                       ("C11", "100nF", C0402, CAP100N), ("C12", "100nF", C0402, CAP100N),
                       ("C13", "100nF", C0402, CAP100N), ("C14", "100nF", C0402, CAP100N),
                       ("C15", "1uF", C0402, CAP1U)], "+3V3",
        title="IOVDD x6, USB_VDD, ADC_AVDD, VREG_VIN (1 uF)")
cap_row(mcu, 300, 100, [("C16", "1uF", C0402, CAP1U), ("C17", "100nF", C0402, CAP100N)], "+1V1",
        title="VREG_VOUT (1 uF), DVDD 23 (100 nF); DVDD 50 joins them round the package")

# ---------------------------------------------------------------------------------------------------
# Keys, LEDs, encoder
# ---------------------------------------------------------------------------------------------------
keys = child("Keys & LEDs", "keys.kicad_sch", "3x3 hot-swap keys, per-key SK6812MINI-E, EC11 encoder", "A3")
keys.box(20, 30, 200, 120, "Keys: Kailh MX hot-swap sockets, wired direct to GPIO (internal pull-ups)")
for i in range(9):
    row, col = divmod(i, 3)
    x, y = 45 + col * 55, 50 + row * 25
    sw = keys.symbol("Switch:SW_Push", f"SW{i + 1}", "MX", x, y, 0, "macropad:SW_Kailh_HotSwap_MX_1.00u",
                     {"MPN": "CPG151101S11", "Manufacturer": "Kailh"}, ref_at=(x - 2, y - 4), value_at=(x - 2, y + 3.5))
    keys.stub(sw, "1", f"KEY{i + 1}", 7.62, kind="hier", shape="output")
    keys.stub(sw, "2", "GND", 5.08, kind="power", power_angle=0)
keys.box(215, 30, 400, 120, "Rotary encoder with push switch")
SW10 = keys.symbol("Device:RotaryEncoder_Switch", "SW10", "EC11E", 300, 70, 0,
                   "macropad:RotaryEncoder_Alps_EC11E-Switch_Vertical_H20mm",
                   {"MPN": "EC11E18244A5", "Manufacturer": "Alps"}, ref_at=(297, 61), value_at=(297, 63.5))
a, b, c = SW10.pin("A"), SW10.pin("B"), SW10.pin("C")
keys.wire(a, (a[0] - 2.54, a[1]), (a[0] - 2.54, a[1] - 5.08), (a[0] - 10.16, a[1] - 5.08))
keys.label("ENC_A", (a[0] - 10.16, a[1] - 5.08), (-1, 0), kind="hier", shape="output")
keys.wire(b, (b[0] - 2.54, b[1]), (b[0] - 2.54, b[1] + 5.08), (b[0] - 10.16, b[1] + 5.08))
keys.label("ENC_B", (b[0] - 10.16, b[1] + 5.08), (-1, 0), kind="hier", shape="output")
keys.wire(c, (c[0] - 7.62, c[1]))
keys.power("GND", (c[0] - 7.62, c[1]), 270)
keys.stub(SW10, "S1", "ENC_SW", 7.62, kind="hier", shape="output")
s2 = SW10.pin("S2")
keys.wire(s2, (s2[0] + 5.08, s2[1]))
keys.power("GND", (s2[0] + 5.08, s2[1]))
keys.text("A, B and the switch pull up inside the RP2040; C and S2 to ground.", (220, 110), 1.27, False)

keys.box(20, 135, 400, 230, "Per-key RGB: SK6812MINI-E (5 V), data level-shifted from 3.3 V by U5 (VIH 0.7 VDD = 3.5 V)")
U5 = keys.symbol("74xGxx:74AHCT1G125", "U5", "74AHCT1G125", 45, 175, 0, "Package_TO_SOT_SMD:SOT-23-5",
                 {"MPN": "74AHCT1G125GV,125", "Manufacturer": "Nexperia"}, ref_at=(50, 162), value_at=(50, 164.5))
a_in = U5.pin("2")
keys.wire(a_in, (a_in[0] - 5.08, a_in[1]))
keys.label("LED_DATA", (a_in[0] - 5.08, a_in[1]), (-1, 0), kind="hier", shape="input")
oe = U5.pin("1")
keys.wire(oe, (oe[0], oe[1] - 2.54))
keys.power("GND", (oe[0], oe[1] - 2.54), 180)
keys.stub(U5, "5", "+5V", 2.54, kind="power")
keys.stub(U5, "3", "GND", 2.54, kind="power")
prev = U5.pin("4")
for i in range(9):
    x = 85 + i * 33
    d = keys.symbol("LED:SK6812MINI-E", f"D{i + 1}", "SK6812MINI-E", x, 175, 0,
                    "LED_SMD:LED_SK6812MINI-E_3.2x2.8mm_P1.5mm_ReverseMount",
                    {"MPN": "SK6812MINI-E", "LCSC": "C5149201"}, ref_at=(x + 3, 165), value_at=(x + 3, 167.5))
    keys.wire(prev, d.pin("2"))
    keys.stub(d, "3", "+5V", 2.54, kind="power")
    keys.stub(d, "1", "GND", 2.54, kind="power")
    prev = d.pin("4")
keys.nc(prev)
cap_row(keys, 45, 210, [(f"C{19 + i}", "100nF", C0402, CAP100N) for i in range(10)], "+5V", pitch=10.16,
        title="One 100 nF at each LED (datasheet section 16), one at U5")
keys.box(215, 240, 400, 270, "Mounting holes: M2, between the keys")
for i in range(6):
    keys.symbol("Mechanical:MountingHole", f"H{i + 1}", "M2", 230 + i * 28, 255, 0, "MountingHole:MountingHole_2.2mm_M2",
                ref_at=(233 + i * 28, 254), value_at=(233 + i * 28, 256.5))

# ---------------------------------------------------------------------------------------------------
# root
# ---------------------------------------------------------------------------------------------------
ROOT.text("Nine: a 3x3 macropad", (25, 30), 3.0)
ROOT.text("RP2040, 9 hot-swap MX keys with per-key RGB, an EC11 encoder, USB-C. Each key is wired to its own GPIO.",
          (25, 37), 1.5, False)
sy = 70.0
usb_pins = [("USB_D+", "bidirectional", "right", sy), ("USB_D-", "bidirectional", "right", sy + 2.54)]
e_usb = ROOT.sheet_symbol(usb, 25, 60, 45, 25, usb_pins, 2)
mcu_pins = [("USB_D+", "bidirectional", "left", sy), ("USB_D-", "bidirectional", "left", sy + 2.54)]
mcu_pins += [(n, "output" if n == "LED_DATA" else "input", "right", 60 + 2.54 * (i + 1)) for i, n in enumerate(KEYSIG)]
e_mcu = ROOT.sheet_symbol(mcu, 110, 55, 45, 45, mcu_pins, 3)
keys_pins = [(n, "input" if n == "LED_DATA" else "output", "left", 60 + 2.54 * (i + 1)) for i, n in enumerate(KEYSIG)]
e_keys = ROOT.sheet_symbol(keys, 200, 55, 45, 45, keys_pins, 4)
for n in ("USB_D+", "USB_D-"):
    ROOT.wire(e_usb[n], e_mcu[n])
for n in KEYSIG:
    ROOT.wire(e_mcu[n], e_keys[n])
ROOT.text("Power: VBUS -> 500 mA polyfuse -> +5V (LEDs, level shifter) -> AP2112K -> +3V3 -> RP2040 core regulator -> +1V1",
          (25, 120), 1.4, False)
ROOT.text(f"GPIO: " + ", ".join(f"{k}=GP{v}" for k, v in sorted(GPIO.items(), key=lambda kv: kv[1])), (25, 126), 1.4, False)

for s in [ROOT, *SHEETS]:
    s.write(PROJ, root=(s is ROOT))
print("wrote", ", ".join(s.file for s in [ROOT, *SHEETS]))
