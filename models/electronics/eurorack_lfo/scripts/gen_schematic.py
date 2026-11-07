"""Writes Twin Orbit's schematic: the root sheet (the shared LM13700 dual OTA and the three sheet symbols),
one LFO sheet used twice (LFO A and LFO B, references 1xx and 2xx), and the power sheet.

Run: python3 scripts/gen_schematic.py   (standard library only; then `cad kicad_sch erc twin_orbit.kicad_sch`)

The circuit, per LFO: a PNP exponential current source (Q1/Q2 and op-amp C as its servo) sets the LM13700
OTA's bias current from the RATE pot and the CV input; the OTA, hard-switched by the square, charges C2
(100 nF C0G) with +-Iabc, op-amp B buffers that triangle, op-amp A is a Schmitt trigger whose output a
dual 5.1 V zener clamps to about +-5.8 V. f = Iabc / (4 * C2 * Vp), Vp = 5.8 V * R6 / R7 = 4.87 V.
The SHAPE pot crossfades triangle and square into op-amp D, the MIX output."""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import schlib  # noqa: E402
from schlib import snap as snapf  # noqa: E402
from schlib import Sheet, uid  # noqa: E402

ROOT = HERE.parent
R_UUID = uid("root")
SA, SB, SP = uid("sheet", "A"), uid("sheet", "B"), uid("sheet", "P")
LFO_PATHS = [f"/{R_UUID}/{SA}", f"/{R_UUID}/{SB}"]

FP = {
    "R": "Resistor_SMD:R_0603_1608Metric",
    "C": "Capacitor_SMD:C_0603_1608Metric",
    "C1206": "Capacitor_SMD:C_1206_3216Metric",
    "C1210": "Capacitor_SMD:C_1210_3225Metric",
    "SOIC14": "Package_SO:SOIC-14_3.9x8.7mm_P1.27mm",
    "SOIC16": "Package_SO:SOIC-16_3.9x9.9mm_P1.27mm",
    "SOT23": "Package_TO_SOT_SMD:SOT-23",
    "SOD123": "Diode_SMD:D_SOD-123",
    "SMA": "Diode_SMD:D_SMA",
    "FB": "Inductor_SMD:L_0805_2012Metric",
    "JACK": "twin_orbit:Jack_3.5mm_QingPu_WQP-PJ398SM_Vertical_CircularHoles",
    "POT": "twin_orbit:Potentiometer_Alpha_RD901F-40-00D_Single_Vertical",
    "LED": "twin_orbit:LED_D3.0mm_Spacer3.5mm",
    "IDC": "Connector_IDC:IDC-Header_2x05_P2.54mm_Vertical",
    "TP": "TestPoint:TestPoint_Keystone_5005-5009_Compact",
}


def lfo_refs(prefix: str, n: int) -> dict[str, str]:
    return {LFO_PATHS[0]: f"{prefix}1{n:02d}", LFO_PATHS[1]: f"{prefix}2{n:02d}"}


def res(s, n, value, at, rot, mpn, fp="R"):
    return s.part("Device", "R", lfo_refs("R", n), value, at, rot=rot, footprint=FP[fp],
                  fields={"MPN": mpn, "Manufacturer": "Yageo"},
                  ref_offset=(2.54, -1.27) if rot == 0 else (-2.54, -2.54),
                  value_offset=(2.54, 1.27) if rot == 0 else (-2.54, 3.81))


def lfo_sheet() -> Sheet:
    s = Sheet("lfo", uid("file", "lfo"), LFO_PATHS, "Twin Orbit: one LFO (used twice)")
    c = s.connect

    # ---- Block 1: rate and CV, exponential current source ------------------------------------
    s.box(12.7, 20.32, 101.6, 118.11, "RATE + CV: exponential current source (Iabc)")
    rv1 = s.part("Device", "R_Potentiometer", lfo_refs("RV", 1), "B100k RATE", (25.4, 43.18),
                 footprint=FP["POT"], fields={"MPN": "RD901F-40-15R1-B100K", "Manufacturer": "Alpha"},
                 ref_offset=(-12.7, -1.27), value_offset=(-17.78, 1.27))
    c(rv1.pin("1"), "-12V")
    c(rv1.pin("3"), "+12V")
    r1 = res(s, 1, "33k", (43.18, 43.18), 90, "RC0603FR-0733KL")
    s.wire(rv1.pin("2").at, r1.pin("1").at)
    s.label("RATE_W", (rv1.pin("2").at[0] + 1.27, 43.18))
    s.connections += [(next(iter(rv1.refs.values())), "2", "RATE_W"), (next(iter(r1.refs.values())), "1", "RATE_W")]
    # the CV jack, turned so its pins face right: TN (normal) and S (sleeve) both to ground
    j1 = s.part("Connector_Audio", "AudioJack2_SwitchT", lfo_refs("J", 1), "CV IN", (22.86, 71.12),
                footprint=FP["JACK"], fields={"MPN": "PJ398SM", "Manufacturer": "Thonk/QingPu"},
                ref_offset=(-5.08, -5.08), value_offset=(-5.08, 6.35))
    r2 = res(s, 2, "33k", (43.18, 71.12), 90, "RC0603FR-0733KL")
    s.wire(j1.pin("T").at, r2.pin("1").at)
    s.label("CV_IN", (j1.pin("T").at[0] + 2.54, 71.12))
    s.connections += [(next(iter(j1.refs.values())), "T", "CV_IN"), (next(iter(r2.refs.values())), "1", "CV_IN")]
    sx, sy = j1.pin("S").at
    tx, ty = j1.pin("TN").at
    s.wire((sx, sy), (sx + 2.54, sy), (sx + 2.54, sy - 2.54))
    s.wire((tx, ty), (tx + 7.62, ty), (tx + 7.62, ty + 5.08))
    s.power("GND", (tx + 7.62, ty + 5.08), (0, 1))
    s.power("GND", (sx + 2.54, sy - 2.54), (0, -1))
    s.connections += [(next(iter(j1.refs.values())), "S", "GND"), (next(iter(j1.refs.values())), "TN", "GND")]
    # the base node QB: R1.2 and R2.2 on a vertical bus, R3 to ground, Q1's base
    q1 = s.part("Transistor_BJT", "BC857", lfo_refs("Q", 1), "BC857B", (66.04, 50.8), footprint=FP["SOT23"],
                fields={"MPN": "BC857B,215", "Manufacturer": "Nexperia"}, ref_offset=(5.08, -1.27), value_offset=(5.08, 1.27))
    bus_x = 53.34
    r3 = res(s, 3, "220", (bus_x, 63.5), 0, "RC0603FR-07220RL")
    s.wire(r1.pin("2").at, (bus_x, 43.18), (bus_x, 50.8), r3.pin("1").at)
    s.wire(r2.pin("2").at, (bus_x - 5.08, 71.12), (bus_x - 5.08, 55.88), (bus_x, 55.88))
    s.junction((bus_x, 55.88))
    s.wire((bus_x, 50.8), q1.pin("1").at)
    s.junction((bus_x, 50.8))
    s.label("QB", (bus_x + 1.27, 50.8))
    s.connections += [(next(iter(r1.refs.values())), "2", "QB"), (next(iter(r2.refs.values())), "2", "QB"),
                      (next(iter(q1.refs.values())), "1", "QB"), (next(iter(r3.refs.values())), "1", "QB")]
    s.wire(r3.pin("2").at, (bus_x, 69.85))
    s.power("GND", (bus_x, 69.85), (0, 1))
    s.connections.append((next(iter(r3.refs.values())), "2", "GND"))
    q2 = s.part("Transistor_BJT", "BC857", lfo_refs("Q", 2), "BC857B", (88.9, 50.8), footprint=FP["SOT23"],
                fields={"MPN": "BC857B,215", "Manufacturer": "Nexperia"}, ref_offset=(5.08, -1.27), value_offset=(5.08, 1.27))
    c(q2.pin("1"), "GND")
    e1, e2 = q1.pin("2").at, q2.pin("2").at
    s.wire(e1, (e1[0], 63.5), (e2[0], 63.5), e2)
    s.junction((e1[0] + 10.16, 63.5))
    s.wire((e1[0] + 10.16, 63.5), (e1[0] + 10.16, 88.9))
    s.label("EXPO_E", (e1[0] + 10.16, 66.04), (0, 1))
    c(q1.pin("3"), "EXPO_SUM", label_dir=(0, -1))
    c(q2.pin("3"), "IABC")
    # the servo: op-amp C holds Q1's collector current at 12 V / R5 = 2.1 uA
    u1c = s.part("Amplifier_Operational", "TL074", lfo_refs("U", 1), "TL074", (45.72, 93.98), unit=1, mirror="x",
                 footprint=FP["SOIC14"], fields={"MPN": "TL074CDR", "Manufacturer": "Texas Instruments"},
                 ref_offset=(2.54, -6.35), value_offset=(2.54, 6.35))
    neg, pos, out = u1c.pin("2").at, u1c.pin("3").at, u1c.pin("1").at
    node = (neg[0] - 7.62, neg[1])
    s.wire(neg, node, (node[0] - 5.08, node[1]))
    s.junction(node)
    s.label("EXPO_SUM", (node[0] - 5.08, node[1]), (0, -1))
    r5 = res(s, 5, "5.6M", (node[0] - 5.08, node[1] + 7.62), 0, "RC0603FR-075M6L")
    s.wire((node[0] - 5.08, node[1]), r5.pin("1").at)
    c(r5.pin("2"), "-12V")
    c1 = s.part("Device", "C", lfo_refs("C", 1), "100p C0G", (45.72, 83.82), rot=90, footprint=FP["C"],
                fields={"MPN": "GRM1885C1H101JA01D", "Manufacturer": "Murata"}, ref_offset=(-2.54, -2.54), value_offset=(3.81, -2.54))
    s.wire(node, (node[0], 83.82), c1.pin("1").at)
    r4 = res(s, 4, "1k", (66.04, out[1]), 90, "RC0603FR-071KL")
    s.wire(out, r4.pin("1").at)
    s.wire(c1.pin("2").at, (out[0] + 2.54, 83.82), (out[0] + 2.54, out[1]))
    s.junction((out[0] + 2.54, out[1]))
    s.label("EXPO_OA", (out[0] + 3.81, out[1]))
    c(u1c.pin("3"), "GND")
    ex = e1[0] + 10.16
    s.wire(r4.pin("2").at, (ex, out[1]))
    d1 = s.part("Diode", "1N4148W", lfo_refs("D", 1), "1N4148W", (ex, out[1] + 7.62), rot=270, footprint=FP["SOD123"],
                fields={"MPN": "1N4148W-7-F", "Manufacturer": "Diodes Inc."}, ref_offset=(2.54, -1.27), value_offset=(2.54, 1.27))
    for pin, net in ((u1c.pin("2"), "EXPO_SUM"), (r5.pin("1"), "EXPO_SUM"), (c1.pin("1"), "EXPO_SUM"),
                     (u1c.pin("1"), "EXPO_OA"), (r4.pin("1"), "EXPO_OA"), (c1.pin("2"), "EXPO_OA"),
                     (r4.pin("2"), "EXPO_E"), (q1.pin("2"), "EXPO_E"), (q2.pin("2"), "EXPO_E"), (d1.pin("1"), "EXPO_E")):
        s.connections.append((next(iter(pin.part.refs.values())), pin.number, net))
    s.wire((ex, 88.9), (ex, out[1]))
    s.wire((ex, out[1]), d1.pin("1").at)
    s.junction((ex, out[1]))
    c(d1.pin("2"), "GND")
    s.text("Iabc = 2.1 uA x exp(V(QB) / 26 mV): RATE sweeps 0.013 to 80 Hz, CV +-5 V spans x13", (15.24, 115.57))

    # ---- Block 2: triangle core ------------------------------------------------------------------
    s.box(104.14, 20.32, 200.66, 118.11, "TRIANGLE CORE: OTA integrator, buffer, Schmitt trigger")
    u1b = s.part("Amplifier_Operational", "TL074", lfo_refs("U", 1), "TL074", (127.0, 50.8), unit=4,
                 footprint=FP["SOIC14"], fields={"MPN": "TL074CDR", "Manufacturer": "Texas Instruments"},
                 ref_offset=(-2.54, -6.35), value_offset=(-2.54, 6.35))
    c2 = s.part("Device", "C", lfo_refs("C", 2), "100n C0G", (114.3, 58.42), footprint=FP["C1206"],
                fields={"MPN": "GRM31C5C1H104JA01L", "Manufacturer": "Murata"}, ref_offset=(2.54, -1.27), value_offset=(2.54, 1.27))
    pin_p = u1b.pin("12").at
    s.wire(pin_p, (114.3, pin_p[1]), c2.pin("1").at)
    s.junction((114.3, pin_p[1]))
    s.wire((114.3, pin_p[1]), (109.22, pin_p[1]))
    s.label("INTEG", (109.22, pin_p[1]), (-1, 0))
    s.connections.append((next(iter(c2.refs.values())), "1", "INTEG"))
    c(c2.pin("2"), "GND")
    out_b, neg_b = u1b.pin("14").at, u1b.pin("13").at
    s.wire(out_b, (out_b[0] + 5.08, out_b[1]))
    s.wire((out_b[0] + 2.54, out_b[1]), (out_b[0] + 2.54, neg_b[1] + 5.08), (neg_b[0] - 2.54, neg_b[1] + 5.08),
           (neg_b[0] - 2.54, neg_b[1]), neg_b)
    s.junction((out_b[0] + 2.54, out_b[1]))
    s.label("TRI", (out_b[0] + 5.08, out_b[1]))
    u1a = s.part("Amplifier_Operational", "TL074", lfo_refs("U", 1), "TL074", (170.18, 50.8), unit=2,
                 footprint=FP["SOIC14"], fields={"MPN": "TL074CDR", "Manufacturer": "Texas Instruments"},
                 ref_offset=(-2.54, -6.35), value_offset=(-2.54, 6.35))
    r6 = res(s, 6, "47k", (151.13, 48.26), 90, "RC0603FR-0747KL")
    c(r6.pin("1"), "TRI")
    pa = u1a.pin("5").at
    s.wire(r6.pin("2").at, pa)
    s.label("SCH_IN", (r6.pin("2").at[0] + 1.27, pa[1]))
    r7 = res(s, 7, "56k", (157.48, 38.1), 0, "RC0603FR-0756KL")
    s.wire(r7.pin("2").at, (157.48, pa[1]))
    s.junction((157.48, pa[1]))
    c(r7.pin("1"), "SQ")
    c(u1a.pin("6"), "GND")
    r10 = res(s, 10, "1k", (185.42, 50.8), 90, "RC0603FR-071KL")
    s.wire(u1a.pin("7").at, r10.pin("1").at)
    s.label("COMP", (u1a.pin("7").at[0] + 1.27, u1a.pin("7").at[1]))
    dz = s.part("Device", "D_Zener_Dual_CommonAnode_KKA", lfo_refs("D", 2), "AZ23C5V1", (193.04, 71.12), rot=270,
                footprint=FP["SOT23"], fields={"MPN": "AZ23C5V1-7-F", "Manufacturer": "Diodes Inc."},
                ref_offset=(2.54, -1.27), value_offset=(2.54, 1.27))
    sq = r10.pin("2").at
    k1 = dz.pin("1").at
    s.wire(sq, (k1[0], sq[1]), k1)
    s.junction((k1[0], sq[1]))
    s.wire((k1[0], sq[1]), (k1[0] + 3.81, sq[1]))
    s.label("SQ", (k1[0] + 3.81, sq[1]))
    s.connections.append((next(iter(r10.refs.values())), "2", "SQ"))
    s.connections.append((next(iter(dz.refs.values())), "1", "SQ"))
    c(dz.pin("2"), "GND")
    c(dz.pin("3"), "NC")
    # OTA drive: SQ / (10k + 470R) = +-260 mV, which saturates the OTA (Iout = +-Iabc)
    r11 = res(s, 11, "10k", (124.46, 91.44), 90, "RC0603FR-0710KL")
    c(r11.pin("1"), "SQ")
    r13 = res(s, 13, "470", (134.62, 99.06), 0, "RC0603FR-07470RL")
    p2 = r11.pin("2").at
    s.wire(p2, (134.62, p2[1]), r13.pin("1").at)
    s.junction((134.62, p2[1]))
    s.wire((134.62, p2[1]), (139.7, p2[1]))
    s.label("OTA_DRV", (139.7, p2[1]), (1, 0))
    s.connections.append((next(iter(r11.refs.values())), "2", "OTA_DRV"))
    c(r13.pin("2"), "GND")
    s.text("Vp = 5.8 V x R6/R7 = 4.87 V;  f = Iabc / (4 C2 Vp) = 1.0 Hz at Iabc = 2 uA", (106.68, 115.57))

    # ---- Block 3: outputs, shape, LED ------------------------------------------------------------
    s.box(203.2, 20.32, 284.48, 118.11, "OUTPUTS: SHAPE crossfade, jacks, rate LED")
    rv2 = s.part("Device", "R_Potentiometer", lfo_refs("RV", 2), "B100k SHAPE", (215.9, 43.18),
                 footprint=FP["POT"], fields={"MPN": "RD901F-40-15R1-B100K", "Manufacturer": "Alpha"},
                 ref_offset=(-12.7, -2.54), value_offset=(-17.78, 2.54))
    c(rv2.pin("1"), "TRI")
    c(rv2.pin("3"), "SQ")
    u1d = s.part("Amplifier_Operational", "TL074", lfo_refs("U", 1), "TL074", (236.22, 45.72), unit=3,
                 footprint=FP["SOIC14"], fields={"MPN": "TL074CDR", "Manufacturer": "Texas Instruments"},
                 ref_offset=(-2.54, -6.35), value_offset=(-2.54, 6.35))
    s.wire(rv2.pin("2").at, (224.79, 43.18), u1d.pin("10").at)
    s.label("MIX_W", (rv2.pin("2").at[0] + 1.27, 43.18))
    out_d, neg_d = u1d.pin("8").at, u1d.pin("9").at
    s.wire(out_d, (out_d[0] + 2.54, out_d[1]))
    s.wire((out_d[0] + 2.54, out_d[1]), (out_d[0] + 2.54, neg_d[1] + 5.08), (neg_d[0] - 2.54, neg_d[1] + 5.08),
           (neg_d[0] - 2.54, neg_d[1]), neg_d)
    s.junction((out_d[0] + 2.54, out_d[1]))
    r14 = res(s, 14, "1k", (251.46, 45.72), 90, "RC0603FR-071KL")
    s.wire((out_d[0] + 2.54, out_d[1]), r14.pin("1").at)
    s.label("MIX", (out_d[0] + 3.81, out_d[1]))
    jack_x = 271.78
    outs = [(r14, None, "MIX_OUT", 4, "MIX OUT", 45.72),
            (None, 8, "TRI_OUT", 2, "TRI OUT", 68.58),
            (None, 12, "SQR_OUT", 3, "SQR OUT", 91.44)]
    for r, rn, net, jn, name, y in outs:
        if r is None:
            r = res(s, rn, "1k", (251.46, y), 90, "RC0603FR-071KL")
            c(r.pin("1"), "TRI" if net == "TRI_OUT" else "SQ")
        j = s.part("Connector_Audio", "AudioJack2_SwitchT", lfo_refs("J", jn), name, (jack_x, y), rot=180,
                   footprint=FP["JACK"], fields={"MPN": "PJ398SM", "Manufacturer": "Thonk/QingPu"},
                   ref_offset=(-5.08, -6.35), value_offset=(-5.08, -8.89))
        s.wire(r.pin("2").at, j.pin("T").at)
        s.label(net, (r.pin("2").at[0] + 1.27, y))
        s.connections += [(next(iter(r.refs.values())), "2", net), (next(iter(j.refs.values())), "T", net)]
        c(j.pin("S"), "GND")
        c(j.pin("TN"), "NC")
    r9 = res(s, 9, "2.2k", (220.98, 99.06), 90, "RC0603FR-072K2L")
    c(r9.pin("1"), "TRI")
    led = s.part("Device", "LED_Dual_Bidirectional", lfo_refs("D", 3), "red/green", (236.22, 99.06),
                 footprint=FP["LED"], fields={"MPN": "WP3VEGW", "Manufacturer": "Kingbright"},
                 ref_offset=(-2.54, -3.81), value_offset=(-2.54, 5.08))
    s.wire(r9.pin("2").at, led.pin("2").at)
    s.label("LED_A", (r9.pin("2").at[0] + 1.27, r9.pin("2").at[1]))
    s.connections.append((next(iter(r9.refs.values())), "2", "LED_A"))
    s.connections.append((next(iter(led.refs.values())), "2", "LED_A"))
    c(led.pin("1"), "GND")
    s.text("LED glows red on the rising half, green on the falling half", (205.74, 115.57))

    # ---- Block 5: the OTA integrator ---------------------------------------------------------------
    s.box(104.14, 124.46, 200.66, 177.8, "OTA INTEGRATOR: U102 (LM13700) charges C102 with +-Iabc")
    fields = {"MPN": "LM13700MX/NOPB", "Manufacturer": "Texas Instruments"}
    ota = s.part("Amplifier_Operational", "LM13700", lfo_refs("U", 2), "LM13700", (132.08, 144.78), unit=3,
                 footprint=FP["SOIC16"], fields=fields, ref_offset=(-2.54, -7.62), value_offset=(-2.54, 7.62))
    c(ota.pin("1"), "IABC")
    c(ota.pin("2"), "NC")
    c(ota.pin("3"), "GND")
    c(ota.pin("4"), "OTA_DRV")
    c(ota.pin("5"), "INTEG")
    buf = s.part("Amplifier_Operational", "LM13700", lfo_refs("U", 2), "LM13700", (167.64, 144.78), unit=4,
                 footprint=FP["SOIC16"], fields=fields, ref_offset=(-2.54, -5.08), value_offset=(-2.54, 5.08))
    c(buf.pin("7"), "-12V")
    c(buf.pin("8"), "NC")
    spare = s.part("Amplifier_Operational", "LM13700", lfo_refs("U", 2), "LM13700", (132.08, 165.1), unit=1,
                   footprint=FP["SOIC16"], fields=fields, ref_offset=(-2.54, -7.62), value_offset=(-2.54, 7.62))
    c(spare.pin("12"), "NC")
    m13, m14 = spare.pin("13").at, spare.pin("14").at
    s.wire(m13, (m13[0] - 2.54, m13[1]), (m14[0] - 2.54, m14[1]), m14)
    s.junction((m14[0] - 2.54, m14[1]))
    s.wire((m14[0] - 2.54, m14[1]), (m14[0] - 2.54, m14[1] + 2.54))
    s.power("GND", (m14[0] - 2.54, m14[1] + 2.54), (0, 1))
    s.connections += [(next(iter(spare.refs.values())), "13", "GND"), (next(iter(spare.refs.values())), "14", "GND")]
    c(spare.pin("15"), "NC")
    c(spare.pin("16"), "NC")
    sbuf = s.part("Amplifier_Operational", "LM13700", lfo_refs("U", 2), "LM13700", (167.64, 165.1), unit=2,
                  footprint=FP["SOIC16"], fields=fields, ref_offset=(-2.54, -5.08), value_offset=(-2.54, 5.08))
    c(sbuf.pin("10"), "-12V")
    c(sbuf.pin("9"), "NC")
    s.text("Spare OTA: inputs grounded, no bias current, output open; spare buffers: inputs to V-", (106.68, 175.26))

    # ---- Block 4: op-amp supply ----------------------------------------------------------------
    s.box(12.7, 124.46, 101.6, 177.8, "U101 + U102 SUPPLY, DECOUPLING")
    u1e = s.part("Amplifier_Operational", "TL074", lfo_refs("U", 1), "TL074", (38.1, 151.13), unit=5,
                 footprint=FP["SOIC14"], fields={"MPN": "TL074CDR", "Manufacturer": "Texas Instruments"},
                 ref_offset=(2.54, -1.27), value_offset=(2.54, 1.27))
    c(u1e.pin("4"), "+12V")
    c(u1e.pin("11"), "-12V")
    c3 = s.part("Device", "C", lfo_refs("C", 3), "100n", (58.42, 144.78), footprint=FP["C"],
                fields={"MPN": "CL10B104KB8NNNC", "Manufacturer": "Samsung"}, ref_offset=(2.54, -1.27), value_offset=(2.54, 1.27))
    c(c3.pin("1"), "+12V")
    c(c3.pin("2"), "GND")
    c4 = s.part("Device", "C", lfo_refs("C", 4), "100n", (68.58, 144.78), footprint=FP["C"],
                fields={"MPN": "CL10B104KB8NNNC", "Manufacturer": "Samsung"}, ref_offset=(2.54, -1.27), value_offset=(2.54, 1.27))
    c(c4.pin("1"), "-12V")
    c(c4.pin("2"), "GND")
    u2e = s.part("Amplifier_Operational", "LM13700", lfo_refs("U", 2), "LM13700", (25.4, 151.13), unit=5,
                 footprint=FP["SOIC16"], fields={"MPN": "LM13700MX/NOPB", "Manufacturer": "Texas Instruments"},
                 ref_offset=(2.54, -1.27), value_offset=(2.54, 1.27))
    c(u2e.pin("11"), "+12V")
    c(u2e.pin("6"), "-12V")
    for n, x, top, bot in ((5, 78.74, "+12V", "GND"), (6, 88.9, "-12V", "GND")):
        cap = s.part("Device", "C", lfo_refs("C", n), "100n", (x, 144.78), footprint=FP["C"],
                     fields={"MPN": "CL10B104KB8NNNC", "Manufacturer": "Samsung"}, ref_offset=(2.54, -1.27), value_offset=(2.54, 1.27))
        c(cap.pin("1"), top)
        c(cap.pin("2"), bot)
    s.text("C103/C104 at U101 pins 4/11, C105/C106 at U102 pins 11/6 (LFO B: 2xx)", (15.24, 175.26))
    return s


def power_sheet() -> Sheet:
    s = Sheet("power", uid("file", "power"), [f"/{R_UUID}/{SP}"], "Twin Orbit: Eurorack power entry", pwr_bases=(8,))
    c = s.connect
    one = lambda prefix, n: {f"/{R_UUID}/{SP}": f"{prefix}{n}"}  # noqa: E731
    s.box(25.4, 25.4, 200.66, 127.0, "EURORACK POWER: 10-pin header, reverse-polarity diodes, ferrites, bulk")
    j = s.part("Connector_Generic", "Conn_02x05_Odd_Even", one("J", 1), "Eurorack 2x5", (55.88, 76.2), rot=90,
               footprint=FP["IDC"], fields={"MPN": "SBH11-PBPC-D05-ST-BK", "Manufacturer": "Sullins"},
               ref_offset=(8.89, -3.81), value_offset=(8.89, -1.27))
    for n in ("1", "2"):
        c(j.pin(n), "-12V_IN")
    for n in ("9", "10"):
        c(j.pin(n), "+12V_IN")
    top = [j.pin(n) for n in ("4", "6", "8")]
    bot = [j.pin(n) for n in ("3", "5", "7")]
    yt, yb = top[0].at[1] - 5.08, bot[0].at[1] + 5.08
    for p_ in top:
        s.wire(p_.at, (p_.at[0], yt))
    for p_ in bot:
        s.wire(p_.at, (p_.at[0], yb))
    s.wire((top[-1].at[0], yt), (top[0].at[0], yt))
    s.wire((bot[0].at[0], yb), (bot[-1].at[0], yb))
    for p_ in top[1:-1] + bot[1:-1]:
        s.junction((p_.at[0], yt if p_ in top else yb))
    s.wire((top[1].at[0], yt), (top[1].at[0], yt - 2.54))
    s.power("GND", (top[1].at[0], yt - 2.54), (0, -1))
    s.wire((bot[1].at[0], yb), (bot[1].at[0], yb + 2.54))
    s.power("GND", (bot[1].at[0], yb + 2.54), (0, 1))
    s.connections += [("J1", p_.number, "GND") for p_ in top + bot]
    s.text("pins 1-2 = -12 V (red stripe)", (33.02, 101.6))
    for n, (rail_in, rail_mid, rail, y, rev) in enumerate([("+12V_IN", "+12V_F", "+12V", 50.8, False),
                                                             ("-12V_IN", "-12V_F", "-12V", 101.6, True)], start=1):
        d = s.part("Diode", "SS14", one("D", n), "SS14", (91.44, y), rot=180 if not rev else 0, footprint=FP["SMA"],
                   fields={"MPN": "SS14", "Manufacturer": "onsemi"}, ref_offset=(-2.54, -3.81), value_offset=(-2.54, 3.81))
        # +12: anode (2) at the header, cathode (1) toward the board; -12: cathode at the header
        a_in, a_out = (d.pin("2"), d.pin("1")) if not rev else (d.pin("1"), d.pin("2"))
        c(a_in, rail_in)
        fb = s.part("Device", "FerriteBead", one("FB", n), "220R@100MHz", (116.84, y), rot=90, footprint=FP["FB"],
                    fields={"MPN": "BLM21PG221SN1D", "Manufacturer": "Murata"}, ref_offset=(-2.54, -5.08), value_offset=(-5.08, 6.35))
        s.wire(a_out.at, fb.pin("1").at)
        s.label(rail_mid, ((a_out.at[0] + fb.pin("1").at[0]) / 2, y))
        s.connections.append((f"D{n}", a_out.number, rail_mid))
        s.connections.append((f"FB{n}", "1", rail_mid))
        cb = s.part("Device", "C", one("C", n), "10u 25V", (139.7, y + 7.62), footprint=FP["C1206"],
                    fields={"MPN": "CL31B106KAHNNNE", "Manufacturer": "Samsung"}, ref_offset=(2.54, -1.27), value_offset=(2.54, 1.27))
        node = (139.7, y)
        s.wire(fb.pin("2").at, node, cb.pin("1").at)
        s.junction(node)
        s.wire(node, (160.02, y))
        s.connections.append((f"FB{n}", "2", rail))
        s.connections.append((f"C{n}", "1", rail))
        s.power(rail, (160.02, y), (0, -1) if not rev else (0, 1))
        c(cb.pin("2"), "GND")
        flag_x = 152.4
        s.wire((flag_x, y), (flag_x, y - 5.08))
        s.junction((flag_x, y))
        s.power("PWR_FLAG", (flag_x, y - 5.08), (0, -1))
        tp = s.part("Connector", "TestPoint", one("TP", n), "TP " + rail, (172.72, y), footprint=FP["TP"],
                    fields={"MPN": "5005" if n == 1 else "5007", "Manufacturer": "Keystone"}, ref_offset=(2.54, -2.54), value_offset=(2.54, -5.08))
        s.wire((160.02, y), (172.72, y))
        s.connections.append((f"TP{n}", "1", rail))
    tp3 = s.part("Connector", "TestPoint", one("TP", 3), "TP GND", (172.72, 73.66), rot=0, footprint=FP["TP"],
                 fields={"MPN": "5006", "Manufacturer": "Keystone"}, ref_offset=(2.54, -1.27), value_offset=(2.54, -3.81))
    c(tp3.pin("1"), "GND", stub=2.54)
    gx = bot[-1].at[0] + 5.08
    s.wire((bot[-1].at[0], yb), (gx, yb), (gx, yb - 2.54))
    s.power("PWR_FLAG", (gx, yb - 2.54), (0, -1))
    s.text("SS14 Schottkys block a reversed ribbon (0.35 V drop at 25 mA);", (27.94, 116.84))
    s.text("BLM21 ferrites and 10 uF 25 V X7R 1206 (about 4 uF at 12 V) filter each rail.", (27.94, 120.65))
    return s


def root_sheet() -> Sheet:
    s = Sheet("root", R_UUID, [f"/{R_UUID}"], "Twin Orbit: dual analog LFO, Eurorack 8HP", pwr_bases=(9,))
    s.box(12.7, 20.32, 284.48, 177.8, "TWIN ORBIT: two exponential OTA LFOs, one sheet used twice")
    sheets = []
    for name, uuid, x, y, w, h, file, page in (("LFO A", SA, 38.1, 50.8, 50.8, 35.56, "lfo.kicad_sch", "2"),
                                               ("LFO B", SB, 114.3, 50.8, 50.8, 35.56, "lfo.kicad_sch", "3"),
                                               ("Power", SP, 190.5, 50.8, 50.8, 35.56, "power.kicad_sch", "4")):
        sheets.append(f'(sheet (at {schlib.f(x)} {schlib.f(y)}) (size {schlib.f(w)} {schlib.f(h)}) (exclude_from_sim no) (in_bom yes) (on_board yes) (dnp no) '
                      f'(fields_autoplaced yes) (stroke (width 0.1524) (type solid)) (fill (color 0 0 0 0.0000)) (uuid "{uuid}")\n'
                      f'    (property "Sheetname" "{name}" (at {schlib.f(x)} {schlib.f(y - 0.7)} 0) (effects (font (size 1.778 1.778)) (justify left bottom)))\n'
                      f'    (property "Sheetfile" "{file}" (at {schlib.f(x)} {schlib.f(y + h + 0.6)} 0) (effects (font (size 1.27 1.27)) (justify left top)))\n'
                      f'    (instances (project "{schlib.PROJECT}" (path "/{R_UUID}" (page "{page}")))))')
    s.sheets_text = "\n  ".join(sheets)
    lines = ["Each LFO: a PNP exponential current source sets an LM13700 OTA's bias current (RATE pot + CV);",
             "the OTA, switched by the square, charges 100 nF C0G with +-Iabc into a triangle, a TL074",
             "buffers it and a Schmitt trigger squares it (clamped to +-5.8 V). SHAPE crossfades TRI and SQR.",
             "Rates 0.013 Hz to 80 Hz; outputs TRI +-4.9 V, SQR +-5.8 V, MIX between them, 1 k each.",
             "Power: Eurorack 10-pin, SS14 reverse protection, ferrites, 10 uF bulk per rail; about 25 mA each rail."]
    for i, line in enumerate(lines):
        s.text(line, (38.1, 106.68 + i * 5.08), size=1.778)
    return s


def write() -> None:
    lfo, power, root = lfo_sheet(), power_sheet(), root_sheet()
    for sheet, name in ((root, "twin_orbit.kicad_sch"), (lfo, "lfo.kicad_sch"), (power, "power.kicad_sch")):
        text = sheet.sexpr()
        text = text.replace("@@SHEETS@@", getattr(sheet, "sheets_text", "") + ("\n  (sheet_instances (path \"/\" (page \"1\")))" if sheet is root else ""))
        (ROOT / name).write_text(text, encoding="utf-8")
    import json
    intent = {"lfo": lfo.connections, "power": power.connections, "root": root.connections}
    (HERE / "schematic_intent.json").write_text(json.dumps(intent, indent=0), encoding="utf-8")
    print("wrote", [str(ROOT / n) for n in ("twin_orbit.kicad_sch", "lfo.kicad_sch", "power.kicad_sch")])


if __name__ == "__main__":
    write()
