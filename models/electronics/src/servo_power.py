"""USB-C servo power board: 5 V through a polyfuse to three servo headers, and 3.3 V for logic.

Every connection is autorouted at build time over two ground pours; the build writes the KiCad
project, JLCPCB's Gerbers, BOM and placement files, and the populated board in 3D for the case.
"""

from cadgen import pcb, step
from cadgen import build123d as bd

WIDTH, HEIGHT, CORNER = 50.0, 35.0, 3.0
THICKNESS = 1.6
HOLE_INSET, HOLE_DIAMETER = 3.5, 3.2
HOLES = [(x * (WIDTH / 2 - HOLE_INSET), y * (HEIGHT / 2 - HOLE_INSET)) for x in (-1, 1) for y in (-1, 1)]
USB_AT = (-21.5, 0.0)  # the USB-C receptacle's opening faces the left edge (the case cuts it out)

R_0603 = "Resistor_SMD:R_0603_1608Metric"
C_0805 = "Capacitor_SMD:C_0805_2012Metric"
HEADER_1X3 = "Connector_PinHeader_2.54mm:PinHeader_1x03_P2.54mm_Vertical"


def usb_power(c, vusb, gnd):
    """A USB-C sink for 5 V: power pins, 5.1k CC pull-downs, data unused."""
    j = c.part("Connector:USB_C_Receptacle_USB2.0_16P",
               footprint="Connector_USB:USB_C_Receptacle_GCT_USB4105-xx-A_16P_TopMnt_Horizontal", ref="J1")
    for pin in j.pins():
        if pin.name == "GND":
            c.connect(gnd, pin)
        elif pin.name == "VBUS":
            c.connect(vusb, pin)
    cc1 = c.part("Device:R", footprint=R_0603, value="5.1k")
    cc2 = c.part("Device:R", footprint=R_0603, value="5.1k")
    c.connect(c.net("CC1"), j["CC1"], cc1[1])
    c.connect(c.net("CC2"), j["CC2"], cc2[1])
    c.connect(gnd, cc1[2], cc2[2], j["SHIELD"])
    c.no_connect(*j.unconnected())
    return j, cc1, cc2


def ldo(c, vin, vout, gnd):
    u = c.part("Regulator_Linear:AMS1117-3.3", footprint="Package_TO_SOT_SMD:SOT-223-3_TabPin2")
    cin = c.part("Device:C", footprint=C_0805, value="10u")
    cout = c.part("Device:C", footprint=C_0805, value="22u")
    c.connect(vin, u["VI"], cin[1])
    c.connect(vout, u["VO"], cout[1])
    c.connect(gnd, u["GND"], cin[2], cout[2])
    return u, cin, cout


@step(out="../STEP/servo_power.step")
@pcb(out="../PCB/servo_power.kicad_pcb", gerber=True, bom=True, pos=True)
def servo_power():
    with bd.BuildSketch() as outline:
        bd.RectangleRounded(WIDTH, HEIGHT, CORNER)
    board = pcb.Board(outline=outline.sketch, thickness=THICKNESS, title="Servo power")

    board.netclass("Power", track_width=0.5, clearance=0.2)
    vusb = board.net("VUSB", netclass="Power", power_flag=True)
    vbus = board.net("+5V", netclass="Power", power_flag=True)  # fed through the fuse
    v33 = board.net("+3V3")
    gnd = board.net("GND", power_flag=True)

    j1, cc1, cc2 = usb_power(board, vusb, gnd)
    f1 = board.part("Device:Polyfuse", footprint="Fuse:Fuse_1206_3216Metric", value="2A")
    board.connect(vusb, f1[1])
    board.connect(vbus, f1[2])
    u1, c1, c2 = ldo(board, vbus, v33, gnd)

    led = board.part("Device:LED", footprint="LED_SMD:LED_0603_1608Metric", value="green")
    rled = board.part("Device:R", footprint=R_0603, value="1k")
    board.connect(v33, rled[1])
    board.connect(board.net(), rled[2], led["A"])
    board.connect(gnd, led["K"])

    signals = board.part("Connector_Generic:Conn_01x05",
                         footprint="Connector_PinHeader_2.54mm:PinHeader_1x05_P2.54mm_Vertical", ref="J5")
    servos = []
    for index in range(3):
        header = board.part("Connector_Generic:Conn_01x03", footprint=HEADER_1X3, ref=f"J{index + 2}")
        board.connect(board.net(f"SERVO{index + 1}"), header[1], signals[index + 1])
        board.connect(vbus, header[2])
        board.connect(gnd, header[3])
        servos.append(header)
    board.connect(v33, signals[4])
    board.connect(gnd, signals[5])

    board.place(j1, at=USB_AT, rotation=-90)
    board.place(cc1, at=(-14, 6), rotation=90)
    board.place(cc2, at=(-14, -6), rotation=90)
    board.place(f1, at=(-10, 0), rotation=90)
    board.place(c1, at=(-4, 8), rotation=90)
    board.place(u1, at=(2, 0))
    board.place(c2, at=(8, 8), rotation=90)
    board.place(rled, at=(-4, -11))
    board.place(led, at=(2, -11))
    board.place(signals, at=(-6, -14), rotation=90)
    for index, header in enumerate(servos):
        board.place(header, at=(16, 11 - index * 9))
    for at in HOLES:
        board.hole(at=at, diameter=HOLE_DIAMETER)

    # GCT's land pattern puts the receptacle's GND pads 0.19 mm from its own locating pegs.
    board.rule("""(rule "J1 land pattern" (constraint hole_clearance (min 0.15mm))
        (condition "A.memberOfFootprint('J1') && B.memberOfFootprint('J1')"))""")
    # The receptacle's GND pads sit too close together for thermal spokes: the top pour meets them solid.
    board.zone(gnd, layers=["F.Cu"], pads="solid")
    board.zone(gnd, layers=["B.Cu"])
    board.text("SERVO PWR", at=(0, 14), size=1.2)
    board.autoroute()
    return board


if __name__ == "__main__":
    servo_power()
