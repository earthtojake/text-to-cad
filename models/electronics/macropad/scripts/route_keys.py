"""The key grid: each key's ground and its line to the RP2040's channel; the LED chain, its 5 V rows
and decoupling. Channels (F.Cu) run between the key columns, where only the switches' plastic is."""
from board_common import LED_KEY, PITCH, key_xy

FEED_X = 71.6          # the 5 V feeder down the left edge (B.Cu)
ROW_BUS = {0: 90.8, 1: 104.4, 2: 129.1}   # each LED row's 5 V bus (rows 1 and 3 below, row 2 above)
CH = {0: 88.6, 1: 107.6, 2: 126.65}      # each column's pad-side via, just right of its socket pad 1


def build(M):
    t, v, P = M.t, M.v, M.P
    # --- keys: ground via under each socket's pad 2; pad 1 to its channel via -----------------------
    for i in range(9):
        x, y = key_xy(i)
        g = M.P(f"SW{i + 1}", 2)
        gv = (g[0], round(y - 0.75, 4))
        t("GND", g, gv, w=0.5)
        v("GND", gv)
    # left column: KEY1 on B.Cu from the strip; KEY4, KEY7 and LED_DATA on F.Cu
    p1 = P("SW1", 1)
    t("/Keys & LEDs/KEY1", (CH[0], M.LEFT_VIA_Y), (CH[0], p1[1]), p1)
    k4, k7 = P("SW4", 1), P("SW7", 1)
    t("/Keys & LEDs/KEY4", (90.2, M.LEFT_VIA_Y), (90.2, 88.0), (CH[0], 89.6), (CH[0], k4[1]), layer="F.Cu")
    v("/Keys & LEDs/KEY4", (CH[0], k4[1]))
    t("/Keys & LEDs/KEY4", (CH[0], k4[1]), k4)
    t("/Keys & LEDs/KEY7", (91.0, M.LEFT_VIA_Y), (91.0, 87.5), (92.0, 88.5), (92.0, k7[1] - 1.47), (90.53, k7[1]),
      (CH[0], k7[1]), layer="F.Cu")
    v("/Keys & LEDs/KEY7", (CH[0], k7[1]))
    t("/Keys & LEDs/KEY7", (CH[0], k7[1]), k7)
    # LED_DATA: down the channel, along under the first row of LEDs' holes, up to U5
    u5 = P("U5", 2)
    ld = (u5[0], 83.4)
    t("/Keys & LEDs/LED_DATA", (89.4, M.LEFT_VIA_Y), (89.4, 85.2), (75.4, 85.2), (74.6, 84.4), ld, layer="F.Cu")
    v("/Keys & LEDs/LED_DATA", ld)
    t("/Keys & LEDs/LED_DATA", ld, u5)
    # middle column: KEY2 on B.Cu, KEY5/KEY8 on F.Cu
    p2, k5, k8 = P("SW2", 1), P("SW5", 1), P("SW8", 1)
    t("/Keys & LEDs/KEY2", (108.0, M.MID_TOP), (108.0, p2[1]), p2)
    a5 = M.MID_VIA["KEY5"]
    t("/Keys & LEDs/KEY5", a5, (CH[1], a5[1] + (a5[0] - CH[1])), (CH[1], k5[1]), layer="F.Cu")
    v("/Keys & LEDs/KEY5", (CH[1], k5[1]))
    t("/Keys & LEDs/KEY5", (CH[1], k5[1]), k5)
    k8v = M.MID_VIA["KEY8"]
    t("/Keys & LEDs/KEY8", k8v, (111.2, k8v[1]), (111.2, k8[1] - 2.97), (108.23, k8[1]), (CH[1], k8[1]), layer="F.Cu")
    v("/Keys & LEDs/KEY8", (CH[1], k8[1]))
    t("/Keys & LEDs/KEY8", (CH[1], k8[1]), k8)
    # right column: KEY3 on B.Cu, KEY6/KEY9 on F.Cu down the right edge
    p3, k6, k9 = P("SW3", 1), P("SW6", 1), P("SW9", 1)
    t("/Keys & LEDs/KEY3", M.RIGHT_END["KEY3"], (CH[2], p3[1]), p3)
    a6 = M.RIGHT_VIA["KEY6"]
    t("/Keys & LEDs/KEY6", a6, (a6[0], 78.0), (CH[2], 78.0 + (a6[0] - CH[2])), (CH[2], k6[1]), layer="F.Cu")
    v("/Keys & LEDs/KEY6", (CH[2], k6[1]))
    t("/Keys & LEDs/KEY6", (CH[2], k6[1]), k6)
    a9 = M.RIGHT_VIA["KEY9"]
    t("/Keys & LEDs/KEY9", a9, (a9[0], k9[1] - (a9[0] - CH[2])), (CH[2], k9[1]), layer="F.Cu")
    v("/Keys & LEDs/KEY9", (CH[2], k9[1]))
    t("/Keys & LEDs/KEY9", (CH[2], k9[1]), k9)

    # --- LEDs ---------------------------------------------------------------------------------------
    # U5 (the 3.3 V -> 5 V buffer) into D1, then each LED's DOUT to the next one's DIN
    u4p, din = P("U5", 4), P("D1", 2)
    t("Net-(D1-DIN)", u4p, (u4p[0] + (din[1] - u4p[1]), din[1]), din)
    for k in range(8):
        a, b = P(f"D{k + 1}", 4), P(f"D{k + 2}", 2)
        net = f"Net-(D{k + 1}-DOUT)"
        row_a, row_b = LED_KEY[k] // 3, LED_KEY[k + 1] // 3
        if row_a == row_b:
            dy = b[1] - a[1]           # 1.5 mm between the rows of pads
            sgn = 1 if b[0] > a[0] else -1
            knee = (b[0] - sgn * abs(dy), a[1])
            t(net, a, knee, b)
        elif row_a == 0:               # D3 -> D4 down the right edge
            t(net, a, (127.4, a[1]), (127.4, b[1] - 0.93), (126.47, b[1]), b)
        else:                          # D6 -> D7 down the left edge
            t(net, a, (73.3, a[1]), (72.3, a[1] + 1.0), (72.3, b[1] - 1.0), (73.3, b[1]), b)
    # 5 V: the feeder from the strip down the left edge, a bus along each LED row
    t("+5V", (FEED_X, M.FEED_TOP), (FEED_X, ROW_BUS[2]), w=0.5)
    for row, y in ROW_BUS.items():
        leds = [k for k in range(9) if LED_KEY[k] // 3 == row]
        xs = [P(f"D{k + 1}", 3)[0] for k in leds]
        pts = [(FEED_X, y)]
        if row == 0:                   # step over the two mounting holes between the rows
            for hx in (90.475, 109.525):     # H1, H2
                pts += [(hx - 2.0, y), (hx - 1.1, y - 0.9), (hx + 1.1, y - 0.9), (hx + 2.0, y)]
        pts.append((max(xs), y))
        t("+5V", *pts, w=0.5)
    for k in range(9):
        vdd, cap1, cap2 = P(f"D{k + 1}", 3), P(f"C{19 + k}", 1), P(f"C{19 + k}", 2)
        row = LED_KEY[k] // 3
        bus = ROW_BUS[row]
        if row % 2 == 0:               # VDD bottom right; the cap under it
            t("+5V", vdd, (vdd[0], cap1[1] - 0.6), (cap1[0], cap1[1] - 0.6 + (vdd[0] - cap1[0])), cap1, w=0.3)
            t("+5V", cap1, (cap1[0], bus), w=0.3)
            gv = (cap2[0] + 0.95, cap2[1])
        else:                          # VDD top left; the cap beside it, the bus above
            d = vdd[1] - cap1[1]
            t("+5V", vdd, (vdd[0] - d, cap1[1]), cap1, w=0.3)
            t("+5V", (vdd[0], vdd[1]), (vdd[0], bus), w=0.3)
            gv = (cap2[0] - 0.95, cap2[1])
        t("GND", cap2, gv, w=0.3)
        v("GND", gv)
        vss = P(f"D{k + 1}", 1)
        side = -1 if row % 2 == 0 else 1          # VSS: top left (rows 1, 3) or bottom right (row 2)
        gv = (vss[0] + side * 1.2, vss[1] + (-0.95 if row % 2 == 0 else 0.95))
        t("GND", vss, (vss[0] + side * 0.25, vss[1]), gv, w=0.3)
        v("GND", gv)
    # U5's supply and ground; its cap C28
    t("+5V", P("U5", 5), (FEED_X, P("U5", 5)[1]), w=0.3)
    t("+5V", P("C28", 1), (P("C28", 1)[0], P("U5", 5)[1]), P("U5", 5), w=0.3)
    u1p, c28g = P("U5", 1), P("C28", 2)
    t("GND", u1p, (c28g[0] + (c28g[1] - u1p[1]), c28g[1]) if False else (u1p[0] - (c28g[1] - u1p[1]), c28g[1]), c28g, w=0.3)
    for pin, gv in ((1, (72.85, 83.8)), (3, (76.4, 83.8))):
        p = P("U5", pin)
        t("GND", p, (p[0], gv[1] + abs(gv[0] - p[0])), gv, w=0.3)
        v("GND", gv)
