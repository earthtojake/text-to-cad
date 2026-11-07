"""The back strip: USB-C, its protection and pull-downs, the 5 V and 3.3 V rails, the RP2040's power,
flash, crystal, boot, reset and SWD, and the fan-out of the key and encoder lines toward the grid.

The RP2040's own ring (between its pads and its exposed pad) carries two rails: 1V1 from VREG_VOUT
(45) to both DVDD pins (50, 23), and 3V3 to the IOVDD pins 1, 10 and 22. Everything else reaches
the package from outside."""
KEYS = "/Keys & LEDs/"


def build(M):
    t, v, P, hop, diag = M.t, M.v, M.P, M.hop, M.diag
    o, i = M.u1_out, M.u1_in
    cx, cy, L = M.U1x, M.U1y, M.LANE
    S = M.W_SIG

    # --- exposed pad: ground vias; TESTEN to ground outside -----------------------------------------
    for dx in (-0.8, 0.8):
        for dy in (-0.8, 0.8):
            v("GND", (cx + dx, cy + dy))
    v("GND", (cx, cy))
    p19 = o(19)
    tv = (p19[0] + 0.6, p19[1] + 0.68)
    t("GND", p19, (p19[0], p19[1] + 0.08), tv)
    v("GND", tv)

    # --- the ring: 1V1 and 3V3 -------------------------------------------------------------------
    top, left, front, right = cy - L, cx - L, cy + L, cx + L
    t("+1V1", i(45), (i(45)[0], top), (i(50)[0], top), i(50))                     # 45 -> 50 along the top
    t("+1V1", (i(45)[0], top), (left, top), (left, front), (i(23)[0], front), i(23))  # 45 -> 23 round the left
    t("+3V3", i(22), (i(22)[0], front), (right, front), (right, i(1)[1]), i(1))     # 22 -> 10 -> 1 round the right
    t("+3V3", (right, i(10)[1]), i(10))

    # --- USB-C: the pair, CC, VBUS, shield -------------------------------------------------------
    b7, a7, a6, b6 = P("J1", "B7"), P("J1", "A7"), P("J1", "A6"), P("J1", "B6")
    top_y = b7[1] - 0.575          # the pads' outer (edge-side) ends
    bot_y = b7[1] + 0.575
    t("/USB & Power/USB_D-", (b7[0], top_y), (b7[0], 53.75), (a7[0], 53.75), (a7[0], top_y))   # B7-A7 over A6
    t("/USB & Power/USB_D+", (a6[0], bot_y), (a6[0], 56.4), (b6[0], 56.4), (b6[0], bot_y))     # A6-B6 under A7
    u2, u3 = P("U4", 2), P("U4", 3)
    t("/USB & Power/USB_D-", (b7[0], bot_y), (b7[0], 56.65), (u2[0], 57.4), u2, (u2[0], P("R3", 1)[1]), P("R3", 1))
    t("/USB & Power/USB_D+", (b6[0], 56.4), (u3[0], 57.65), P("R4", 1))
    r3b, r4b = P("R3", 2), P("R4", 2)
    t("/MCU/RP_D-", r3b, (98.2, r3b[1]), (o(46)[0], r3b[1] + (o(46)[0] - 98.2)), o(46))
    t("/MCU/RP_D+", r4b, (98.2, r4b[1]), (o(47)[0], r4b[1] + (o(47)[0] - 98.2)), o(47))
    # CC1 down to R1; CC2 jumps to R2 under the receptacle
    a5, b5 = P("J1", "A5"), P("J1", "B5")
    r1 = P("R1", 1)
    t("/USB & Power/CC1", (a5[0], bot_y), (a5[0], r1[1] - 0.32 - (a5[0] - r1[0])), (r1[0], r1[1] - 0.32), r1)
    cc2v, r2 = (91.6, 56.05), P("R2", 1)
    t("/USB & Power/CC2", (b5[0], bot_y), (b5[0], cc2v[1] - (b5[0] - cc2v[0])), cc2v)
    hop("/USB & Power/CC2", cc2v, (r2[0], 51.2), (cc2v[0], 51.6), (r2[0] - 0.4, 51.6))
    t("/USB & Power/CC2", (r2[0], 51.2), r2)
    for ref, num, gv in (("R1", 2, (88.1, 59.45)), ("R2", 2, (95.8, 54.2))):
        t("GND", P(ref, num), gv)
        v("GND", gv)
    # ground pads to the planes
    for num, gv in (("A1", (86.8, 56.1)), ("A12", (93.2, 56.1))):
        t("GND", (P("J1", num)[0], bot_y), gv, w=0.5)
        v("GND", gv)
    u1g = P("U4", 1)
    t("GND", u1g, diag(u1g, -0.8, 0.8))
    v("GND", diag(u1g, -0.8, 0.8))
    # VBUS: both pairs of pins joined above the pads (under the receptacle), to the polyfuse; and
    # round below U4 to its VCC pin
    a4, a9, f1 = P("J1", "A4"), P("J1", "A9"), P("F1", 1)
    # (up the pads' inner halves: the receptacle's locating holes sit just outside them)
    t("VBUS", (a9[0] - 0.2, top_y), (a9[0] - 0.2, 52.4), (a4[0] + 0.2, 52.4), (a4[0] + 0.2, top_y), w=0.2)
    t("VBUS", (a4[0] + 0.2, 52.4), (83.4, 52.4), (f1[0], 53.0), w=0.5)
    u4v = P("U4", 4)
    t("VBUS", f1, (f1[0], 60.2), (f1[0] + 0.8, 61.0), (u4v[0] - 0.6, 61.0), (u4v[0], 60.4), u4v, w=0.4)

    # --- 5 V: polyfuse -> LDO and down the left edge ---------------------------------------------
    f2, ui, ue, c1 = P("F1", 2), P("U3", 1), P("U3", 3), P("C1", 1)
    t("+5V", f2, (f2[0], ui[1]), w=0.5)
    t("+5V", (f2[0], ui[1]), ui, w=0.4)
    t("+5V", (f2[0], ui[1]), (f2[0], ue[1]), ue, w=0.4)
    t("+5V", c1, (c1[0], ui[1] - (ui[0] - c1[0])), ui, w=0.4)
    t("+5V", f2, (71.6, f2[1]), w=0.5)
    M.FEED_TOP = f2[1]
    ug = P("U3", 2)
    gv = (77.6, ug[1])         # under the regulator: its ground pin sits between the two 5 V pins
    t("GND", ug, gv)
    v("GND", gv)
    gv = (76.3, P("C1", 2)[1])
    t("GND", P("C1", 2), gv)
    v("GND", gv)

    # --- 3.3 V: LDO -> trunk along the strip (B.Cu) to the RP2040's top-left; a copper hop for the
    # pocket by pin 33; the back edge (F.Cu) to the flash, the USB_VDD/IOVDD pair and the right side
    uo, c2, c3 = P("U3", 5), P("C2", 1), P("C3", 1)
    TR = 62.2
    # C2 (10 uF) and C3 (100 nF) at the regulator's output; the trunk leaves from C2
    t("+3V3", uo, (c2[0], uo[1]), c2, w=0.4)
    t("+3V3", (c3[0], uo[1]), c3, w=0.4)
    t("+3V3", c2, (73.0, c2[1]), (73.0, TR - 0.6), (73.6, TR), (P("C11", 1)[0], TR), P("C11", 1), w=0.3)
    gv = (P("C2", 2)[0], P("C2", 2)[1] + 1.05)
    t("GND", P("C2", 2), gv, w=0.4)
    v("GND", gv)
    gv = (73.9, P("C3", 2)[1])
    t("GND", P("C3", 2), gv)
    v("GND", gv)
    # the top-left: IOVDD 42 (C11), ADC_AVDD 43 + VREG_VIN 44 (C14, C15), spare C12; VREG_VOUT 45 (C16)
    c11, c12, c14, c15, c16 = (P(r, 1) for r in ("C11", "C12", "C14", "C15", "C16"))
    t("+3V3", o(42), (o(42)[0] - 1.0, o(42)[1] - 1.0), c11)
    t("+3V3", o(43), o(44))
    t("+3V3", o(43), (c15[0], o(43)[1] - (o(43)[0] - c15[0])), c15)
    t("+3V3", c12, c14, c15)
    t("+3V3", c12, c11)
    t("+1V1", o(45), (o(45)[0], c16[1] + (o(45)[0] - c16[0])), c16)
    g12, g16 = P("C12", 2), P("C16", 2)
    t("GND", g12, g16, w=0.3)
    t("GND", g12, (94.3, g12[1]), w=0.3)
    v("GND", (94.3, g12[1]))
    g11 = P("C11", 2)
    t("GND", g11, (93.3, g11[1]))
    v("GND", (93.3, g11[1]))
    # the pocket by pin 33: C10, C9 (spare), R7 (RUN pull-up), TP4 (3V3), fed by an F.Cu hop
    c10, c9, r7, tp4 = P("C10", 1), P("C9", 1), P("R7", 1), P("TP4", 1)
    t("+3V3", o(33), c10)
    t("+3V3", c9, c10, (c10[0], r7[1] - (c10[0] - r7[0])), r7)
    vb = (94.1, 67.9)
    t("+3V3", r7, (vb[0] + (vb[1] - r7[1]), r7[1]), vb)
    t("+3V3", tp4, (tp4[0], TR))        # TP4 (the probe's 3V3) hangs off the trunk
    hop("+3V3", (92.4, TR), vb, (92.4, vb[1] - (vb[0] - 92.4)))
    for ref, gv in (("C10", (93.82, 66.5)), ("C9", (93.52, 65.05))):
        t("GND", P(ref, 2), gv)
        v("GND", gv)
    # the back edge (F.Cu): from the LDO's output to the flash, the wedge and the right side
    BE = 48.3
    lv = (73.0, 60.0)
    v("+3V3", lv)
    wv = (99.6, 59.6)          # on the USB_VDD/IOVDD stub, between the pair and the flash lines
    fv = (P("U2", 8)[0], 49.45)
    rv = (104.45, 66.0)        # pin 10's node
    t("+3V3", lv, (73.0, 53.6), (75.2, 51.4), (75.2, 49.5), (76.4, BE), (wv[0], BE), (111.0, BE), (111.0, 65.0), (105.45, 65.0), rv,
      w=0.4, layer="F.Cu")
    t("+3V3", (wv[0], BE), wv, w=0.4, layer="F.Cu")
    t("+3V3", (fv[0], BE), fv, w=0.4, layer="F.Cu")
    for xy in (wv, fv, rv):
        v("+3V3", xy)
    # the wedge: USB_VDD 48 + IOVDD 49 together, to C13
    c13, g13 = P("C13", 1), P("C13", 2)
    t("+3V3", o(48), o(49))
    t("+3V3", (wv[0], o(48)[1]), wv, (wv[0], 58.3), (c13[0], 58.3 - (c13[0] - wv[0])), c13)
    t("GND", g13, diag(g13, -0.65, -0.65))
    v("GND", diag(g13, -0.65, -0.65))
    # right side: C7 at IOVDD 1, C8 at IOVDD 10 (both fed through the ring)
    c7, c8 = P("C7", 1), P("C8", 1)
    t("+3V3", o(1), (o(1)[0] + (o(1)[1] - c7[1]), c7[1]), c7)
    t("+3V3", o(10), rv, c8)
    for ref, gv in (("C7", (106.6, 61.6)), ("C8", (106.9, 66.0))):
        t("GND", P(ref, 2), gv)
        v("GND", gv)
    # flash supply and its cap
    u8, c4 = P("U2", 8), P("C4", 1)
    t("+3V3", fv, u8)
    t("+3V3", u8, c4)
    gv = (P("C4", 2)[0] - 0.4, P("C4", 2)[1] + 0.72)
    t("GND", P("C4", 2), (gv[0], P("C4", 2)[1] + 0.4), gv)
    v("GND", gv)

    # --- QSPI flash ------------------------------------------------------------------------------
    pad_bot = P("U2", 1)[1] + 0.81           # the bottom row's pad ends (toward the RP2040)
    pad_top = P("U2", 5)[1] - 0.81           # the top row's (toward the board's edge)
    for n, net, y in ((56, "/MCU/QSPI_SS", 60.45), (55, "/MCU/QSPI_SD1", 60.05), (54, "/MCU/QSPI_SD2", 59.65)):
        pin = {56: 1, 55: 2, 54: 3}[n]
        x = P("U2", pin)[0]
        t(net, o(n), (o(n)[0], y), (x, y), (x, pad_bot))
    sd0 = 105.725                              # under the flash, between pads 4 and 3
    inner_top = P("U2", 5)[1] + 0.81
    t("/MCU/QSPI_SD0", o(53), (o(53)[0], 59.25), (sd0, 59.25), (sd0, inner_top + 0.635), (P("U2", 5)[0], inner_top))
    t("/MCU/QSPI_SCLK", o(52), (o(52)[0], 58.4), (103.8, 58.4), (103.8, 49.7), (P("U2", 6)[0], 49.7),
      (P("U2", 6)[0], pad_top))
    t("/MCU/QSPI_SD3", o(51), (o(51)[0], 58.0), (103.4, 58.0), (103.4, 49.3), (P("U2", 7)[0], 49.3),
      (P("U2", 7)[0], pad_top))
    g4 = P("U2", 4)
    t("GND", g4, (g4[0], 55.0))
    v("GND", (g4[0], 55.0))
    # BOOTSEL: SS through R6 (1k) to SW11
    r6a, r6b, sw = P("R6", 1), P("R6", 2), P("SW11", 1)
    t("/MCU/QSPI_SS", (P("U2", 1)[0], 60.45), (r6a[0], 60.45), r6a)
    t("Net-(R6-Pad2)", r6b, (111.9, r6b[1] - (111.9 - r6b[0])), (111.9, sw[1] + 0.4), sw)
    gv = (P("SW11", 2)[0] + 1.0, P("SW11", 2)[1])
    t("GND", P("SW11", 2), gv)
    v("GND", gv)

    # --- crystal ---------------------------------------------------------------------------------
    x1, x3 = P("Y1", 1), P("Y1", 3)
    t("/MCU/XIN", o(20), (o(20)[0], 70.35), (x1[0], 70.35), x1)
    t("/MCU/XIN", (P("C5", 1)[0], 70.35), P("C5", 1))
    r5x, r5n = P("R5", 2), P("R5", 1)
    t("/MCU/XOUT", o(21), (o(21)[0], r5x[1]), r5x)
    t("Net-(C6-Pad1)", r5n, (x3[0] - 0.9, r5n[1]), (x3[0], r5n[1] - 0.9), x3)
    c6 = P("C6", 1)
    t("Net-(C6-Pad1)", x3, (c6[0] - (x3[1] - c6[1]), x3[1]), c6)
    for a, gv in ((P("C5", 2), (P("C5", 2)[0], 72.6)), (P("Y1", 2), (106.05, 70.4)), (P("C6", 2), (P("C6", 2)[0], 74.3))):
        t("GND", a, gv)
        v("GND", gv)
    y4 = P("Y1", 4)
    t("GND", y4, (y4[0] - 0.25, 72.6), (P("C5", 2)[0], 72.6))

    # --- 1V1 at the front: C17 at DVDD 23 ----------------------------------------------------------
    c17 = P("C17", 1)
    t("+1V1", o(23), (o(23)[0], c17[1] - 0.32 - (c17[0] - o(23)[0])), (c17[0], c17[1] - 0.32), c17)
    gv = (c17[0], 71.6)
    t("GND", P("C17", 2), gv)
    v("GND", gv)

    # --- SWD, RUN, reset -----------------------------------------------------------------------------
    r7r, swr = P("R7", 2), P("SW12", 1)
    t("/MCU/RUN", o(26), (o(26)[0], 69.3), (r7r[0] + (69.3 - r7r[1]), 69.3), r7r)
    t("/MCU/RUN", r7r, (swr[0] + 0.6 + (r7r[1] - swr[1] - 0.1), r7r[1]), (swr[0] + 0.6, swr[1] + 0.1))
    tp2, tp1 = P("TP2", 1), P("TP1", 1)
    t("/MCU/SWDIO", o(25), (o(25)[0], 69.7), (tp2[0] + 1.0, 69.7), (tp2[0], 70.7), tp2)
    t("/MCU/SWCLK", o(24), (o(24)[0], tp1[1]), tp1)
    gv = (P("SW12", 2)[0], P("TP3", 1)[1] - (P("TP3", 1)[0] - P("SW12", 2)[0]))
    t("GND", P("SW12", 2), gv)
    t("GND", P("TP3", 1), (gv[0] + (P("TP3", 1)[0] - gv[0]), gv[1] + (P("TP3", 1)[0] - gv[0])), gv)
    v("GND", gv)

    # --- encoder ---------------------------------------------------------------------------------
    s1, ea, eb = P("SW10", "S1"), P("SW10", "A"), P("SW10", "B")
    t(KEYS + "ENC_SW", o(2), (117.0, o(2)[1]), (117.0, s1[1] + 2.1), (s1[0], s1[1] + 2.1), s1)
    t(KEYS + "ENC_B", o(3), (eb[0], o(3)[1]), eb)
    t(KEYS + "ENC_A", o(4), (ea[0], o(4)[1]), ea)

    # --- the key lines toward the grid -------------------------------------------------------------
    # left column (the RP2040's left side): along under the trunk, down beside the pocket
    M.LEFT_VIA_Y = 74.0
    for n, net, x in ((41, "KEY1", 88.6), (40, "LED_DATA", 89.4), (39, "KEY4", 90.2), (38, "KEY7", 91.0)):
        end = (x, M.LEFT_VIA_Y)
        t(KEYS + net, o(n), (x, o(n)[1]), end)
        if net != "KEY1":
            v(KEYS + net, end)
    # right column: out the right side, down at 109.7-110.5, along above the sockets
    lanes = {"KEY9": (5, 110.9, 73.8, 128.25), "KEY6": (6, 110.5, 74.2, 127.45), "KEY3": (7, 110.1, 74.6, 126.65)}
    M.RIGHT_VIA, M.RIGHT_END = {}, {}
    for net, (n, x, y, xe) in lanes.items():
        if net == "KEY3":
            t(KEYS + net, o(n), (x, o(n)[1]), (x, y), (xe, y))
            M.RIGHT_END[net] = (xe, y)
        else:
            end = (xe, y + 0.5)
            t(KEYS + net, o(n), (x, o(n)[1]), (x, y), (xe - 0.5, y), end)
            v(KEYS + net, end)
            M.RIGHT_VIA[net] = end
    # middle column: out the right side's lower pins, down at 107.6-108.8
    M.MID_TOP = 67.6
    for net, (n, x, vy) in {"KEY8": (12, 109.2, 73.0), "KEY5": (13, 108.6, 74.2), "KEY2": (14, 108.0, None)}.items():
        if vy is None:
            t(KEYS + net, o(n), (x, o(n)[1]))
            M.MID_TOP = o(n)[1]
        else:
            t(KEYS + net, o(n), (x, o(n)[1]), (x, vy))
            v(KEYS + net, (x, vy))
    M.MID_VIA = {"KEY8": (109.2, 73.0), "KEY5": (108.6, 74.2)}
