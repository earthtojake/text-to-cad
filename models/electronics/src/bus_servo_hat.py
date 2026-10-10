"""Bus servo HAT: a Raspberry Pi HAT that drives serial bus servos and powers the Pi from their supply.

A version of Waveshare's Bus Servo Adapter (A) on the Pi's HAT outline. 9-12.6 V comes in on a
barrel jack, or on a screw terminal behind a reverse-polarity P-FET, and goes straight to four
servo ports. A 5 V / 5 A buck powers the Pi through its 5V header pins, behind an ideal diode
so a Pi powered from its own USB-C never back-feeds the servo supply. The servo bus is
half-duplex on one wire: while the host's TX is low a PNP enables a 74LVC1G126 that pulls DATA
low and disables the 74LVC1G125 that passes DATA back to the host's RX, so no direction pin is
needed. The host is the Pi's UART (GPIO14/15) or the 3-pin UART header with the jumpers on A,
or a PC over USB-C through a CH343P with the jumpers on B.

The circuits are `bus_servo_hat_circuits.py`'s, which `bus_servo_hat_sim.py` simulates; this script
lays them out.
"""

from cadgen import build123d as bd
from cadgen import glb, pcb, step

import bus_servo_hat_circuits as circuits

# The Pi HAT outline (KiCad's RaspberryPi-HAT template): 65 x 56 mm, 3 mm corners, M2.5 holes
# on the Pi's 58 x 49 mm pattern, the display-cable notch and the camera-cable slot.
WIDTH, HEIGHT, CORNER = 65.0, 56.0, 3.0
HOLES = [(3.5, 3.5), (61.5, 3.5), (3.5, 52.5), (61.5, 52.5)]
PI_PIN1 = (8.37, 51.23)  # the 40-pin socket, on the underside


def outline():
    with bd.BuildSketch() as sketch:
        with bd.Locations((WIDTH / 2, HEIGHT / 2)):
            bd.RectangleRounded(WIDTH, HEIGHT, CORNER)
        with bd.Locations((2.0, 28.0)):  # display-cable notch: x 0..5, y 19.5..36.5
            bd.Rectangle(6.0, 17.0, mode=bd.Mode.SUBTRACT)
        with bd.Locations((45.0, 11.5)):  # camera-cable slot: x 44..46, y 3..20
            bd.SlotCenterToCenter(15.0, 2.0, rotation=90, mode=bd.Mode.SUBTRACT)
    return sketch.sketch


def power_input(board, vin, gnd):
    """The jack and the terminal on the left edge, the FET between them and the servo trunk."""
    p = circuits.power_input(board, vin, gnd)
    board.place(p.jack, at=(14.0, 13.5))  # mouth on the left edge, below the display notch
    board.place(p.terminal, at=(19.0, 4.5))  # wires in from the bottom edge
    board.place(p.fet, at=(29.0, 5.5), rotation=180)  # drains face the terminal
    board.place(p.zener, at=(34.2, 6.5), rotation=90)
    board.place(p.r_gate, at=(34.2, 10.0), rotation=90)
    board.place(p.tvs, at=(39.5, 4.8))
    board.place(p.bulk, at=(39.5, 12.6), rotation=-90)  # + at the top, toward the servo trunk
    fet, jack, terminal, tvs, bulk = p.fet, p.jack, p.terminal, p.tvs, p.bulk
    # Each SO-8 pin row is one net: join its pads at pad width, clear of the gate pad.
    board.track(p.vin_raw, [fet["8"], fet["5"]], width=0.6)
    board.track(vin, [fet["1"], fet["3"]], width=0.6)
    # The servos' current, by hand: the jack to the bulk capacitor, 2 mm wide (the buck's input
    # branches off at x = 20); the terminal through the FET, past the TVS, to the same capacitor.
    board.track(vin, [jack[1], (16.0, 13.5), (18.35, 15.85), (20.025, 15.85), bulk[1]], width=2.0)
    board.track(p.vin_raw, [terminal[2], (24.5, 4.5), fet["7"]], width=1.5)
    board.track(vin, [fet["1"], (35.9, 3.595), tvs[1], (36.2, 6.1), (36.2, 14.6), bulk[1]], width=1.5)
    return bulk


def buck(board, vin, v5, gnd):
    """The buck between the input and the Pi's corner: the switch node short, the input loop tight."""
    b = circuits.buck(board, vin, v5, gnd)
    u, inductor, c_in, c_out = b.u, b.inductor, b.c_in, b.c_out
    board.place(u, at=(20.0, 28.0))
    board.place(inductor, at=(11.5, 28.0), rotation=180)  # pin 1 (SW) faces the IC's SW pin
    board.place(b.c_hf, at=(17.5, 24.4), rotation=180)
    for capacitor, y in zip(c_in, (23.0, 20.3)):
        board.place(capacitor, at=(21.5, y))
    for capacitor, x in zip(c_out, (8.5, 11.0)):
        board.place(capacitor, at=(x, 34.2), rotation=90)
    board.place(b.c_bst, at=(20.0, 31.0))
    # EN divider beside the input capacitors, where VIN is; EN runs from there to its pin.
    board.place(b.r_en_top, at=(17.6, 19.0), rotation=180)
    board.place(b.r_en_bot, at=(14.6, 19.0), rotation=180)
    board.place(b.r_fb_top, at=(25.0, 25.5), rotation=90)
    board.place(b.r_fb_bot, at=(27.0, 25.5), rotation=90)

    # The switch node by hand: out of the pad at its width, then short and wide to the inductor,
    # and round the GND pin to the boost capacitor.
    x, y = u["SW"].position
    board.track(b.sw, [u["SW"], (x - 1.8, y)], width=0.6)
    board.track(b.sw, [(x - 1.8, y), inductor[1]], width=1.5)
    board.track(b.sw, [(x - 1.8, y), (x - 1.8, 31.0), b.c_bst[1]], width=0.4)
    # The input loop: from the jack's track up through both input capacitors to the VIN pin.
    x, y = u["VIN"].position
    board.track(vin, [u["VIN"], (x, y - 1.4)], width=0.6)
    board.track(vin, [(20.025, 15.85), (20.025, 19.0), c_in[1][1], c_in[0][1], b.c_hf[1], (x, y - 1.4)], width=1.0)
    board.track(vin, [(20.025, 19.0), b.r_en_top[1]], width=0.4)
    board.track(b.en, [b.r_en_top[2], b.r_en_bot[1]], width=0.3)
    return inductor, c_out


def ideal_diode(board, v5, v5_pi, gnd):
    """The ideal diode beside the Pi's 5V pins."""
    d = circuits.ideal_diode(board, v5, v5_pi, gnd)
    board.place(d.fet, at=(11.5, 43.0), rotation=-90)  # drain pads face the buck, sources the Pi
    board.place(d.pair, at=(16.5, 44.0))
    board.place(d.r_ref, at=(20.0, 45.0))
    board.place(d.r_gate, at=(20.0, 43.0))
    board.track(v5_pi, [d.fet["3"], d.fet["1"]], width=0.6)
    return d.fet


def logic_supply(board, v5, vbus, v3, gnd):
    """The 3.3 V regulator in the middle, its OR-ing diodes toward the 5 V sources."""
    s = circuits.logic_supply(board, v5, vbus, v3, gnd)
    board.place(s.ldo, at=(31.0, 43.5))
    board.place(s.d_5v, at=(16.0, 38.5), rotation=180)
    board.place(s.d_usb, at=(23.5, 37.8), rotation=180)
    board.place(s.c_in, at=(27.0, 38.0))
    board.place(s.c_out, at=(37.5, 44.0), rotation=90)
    board.place(s.led, at=(43.5, 47.5))
    board.place(s.r_led, at=(40.0, 47.5))
    return s.ldo_in, s.d_5v


def usb_bridge(board, ldo_in, vbus, v3, gnd, ch_txd, ch_rxd):
    """USB-C on the bottom edge and the CH343P above it."""
    u = circuits.usb_bridge(board, ldo_in, vbus, v3, gnd, ch_txd, ch_rxd)
    usb = u.usb
    board.place(usb, at=(52.3, 3.675))  # its PCB-edge line on the bottom edge
    board.place(u.bridge, at=(51.8, 14.0))
    board.place(u.r_cc1, at=(48.0, 10.2), rotation=90)
    board.place(u.r_cc2, at=(55.2, 10.5), rotation=90)
    board.place(u.c_vbus, at=(55.2, 14.5), rotation=90)
    board.place(u.c_vdd5, at=(48.5, 15.0), rotation=90)
    board.place(u.c_vio, at=(48.5, 18.0), rotation=90)
    board.place(u.c_v3, at=(50.6, 10.6), rotation=-90)
    # The receptacle's GND pads sit in its fine-pitch row: tie each to the shell's through-hole tab.
    x0, y0 = usb.at
    board.track(gnd, [usb["A1"], (x0 - 4.32, y0 + 3.105)], width=0.3)
    board.track(gnd, [usb["A12"], (x0 + 4.32, y0 + 3.105)], width=0.3)
    # GCT's land pattern puts the receptacle's GND pads 0.19 mm from its own locating pegs.
    board.rule("""(rule "J4 land pattern" (constraint hole_clearance (min 0.15mm))
        (condition "A.memberOfFootprint('J4') && B.memberOfFootprint('J4')"))""")


def half_duplex(board, v3, gnd, u1txd, u1rxd, data):
    """The bus switch beside the servo ports: the PNP, the two buffers and their resistors."""
    h = circuits.half_duplex(board, v3, gnd, u1txd, u1rxd, data)
    board.place(h.q, at=(52.0, 36.0))
    board.place(h.drive, at=(52.0, 30.0))
    board.place(h.listen, at=(52.0, 24.5))
    for part, at in ((h.r_txpu, (48.0, 36.0)), (h.r_base, (48.0, 39.5)), (h.r_txen, (55.5, 36.0)),
                     (h.r_data, (55.5, 30.0)), (h.r_rxpu, (55.5, 24.5)), (h.c_drive, (48.0, 30.0)),
                     (h.c_listen, (48.0, 24.5)), (h.c_bulk, (48.0, 43.0)), (h.clamp, (55.5, 41.0))):
        board.place(part, at=at, rotation=90)
    x, y = h.listen["GND"].position
    board.track(gnd, [h.listen["GND"], (x - 1.2, y)], width=0.3)  # into the pour: routes crowd its spokes


@glb(out="../GLB/bus_servo_hat.glb")
@step(out="../STEP/bus_servo_hat.step")
@pcb(out="../PCB/bus_servo_hat.kicad_pcb", gerber=True, bom=True, pos=True)
def bus_servo_hat():
    board = pcb.Board(outline=outline(), fab=pcb.JLCPCB, title="Bus servo HAT")
    vin = board.net("VIN", power_flag=True)  # the servo supply, 9-12.6 V; its current paths are drawn
    v5 = board.net("+5V")  # the buck's output; its current path is drawn by hand below
    v5_pi = board.net("5V_PI")  # the Pi's 5V pins (its symbol's pin 2 drives it), drawn by hand too
    v3, vbus, gnd = board.net("+3V3"), board.net("VBUS"), board.net("GND")  # the Pi's GND pin 6 drives GND
    data = board.net("DATA")
    txd, rxd = board.net("TXD"), board.net("RXD")  # the host's TX and RX
    u1txd, u1rxd = board.net("U1TXD"), board.net("U1RXD")  # the bus side
    ch_txd, ch_rxd = board.net("CH_TXD"), board.net("CH_RXD")  # the USB bridge's side

    bulk = power_input(board, vin, gnd)
    inductor, c_out = buck(board, vin, v5, gnd)
    pi_fet = ideal_diode(board, v5, v5_pi, gnd)
    ldo_in, d_5v = logic_supply(board, v5, vbus, v3, gnd)
    usb_bridge(board, ldo_in, vbus, v3, gnd, ch_txd, ch_rxd)
    half_duplex(board, v3, gnd, u1txd, u1rxd, data)

    # The Pi: 5 V in on pins 2 and 4, its UART on GPIO14/15, nothing else.
    pi = board.part("Connector:Raspberry_Pi_4", ref="J1", value="Raspberry Pi GPIO",
                    footprint="Connector_PinSocket_2.54mm:PinSocket_2x20_P2.54mm_Vertical")
    board.connect(v5_pi, pi["2"], pi["4"])
    board.connect(gnd, *[pin for pin in pi.pins() if pin.name == "GND"])
    board.connect(txd, pi["GPIO14/UART_TXD"])
    board.connect(rxd, pi["GPIO15/UART_RXD"])
    board.no_connect(*pi.unconnected())
    board.place(pi, at=PI_PIN1, rotation=-90, side="bottom")  # pin 2 above pin 1, pin 3 right of it

    # Host select: jumpers on 1-3 and 2-4 = A (the Pi, or the UART header), on 3-5 and 4-6 = B (USB).
    jumpers = board.part("Connector_Generic:Conn_02x03_Odd_Even", ref="J9", value="HOST A|B",
                         footprint="Connector_PinHeader_2.54mm:PinHeader_2x03_P2.54mm_Vertical")
    for pin, net in zip(range(1, 7), (rxd, txd, u1rxd, u1txd, ch_rxd, ch_txd)):
        board.connect(net, jumpers[pin])
    board.place(jumpers, at=(38.0, 30.0))
    uart = board.part("Connector_Generic:Conn_01x03", ref="J10", value="UART",
                      footprint="Connector_PinHeader_2.54mm:PinHeader_1x03_P2.54mm_Vertical")
    board.connect(gnd, uart[1])
    board.connect(rxd, uart[2])
    board.connect(txd, uart[3])
    board.place(uart, at=(38.0, 34.5), rotation=90)

    # Four servo ports down the right edge, pin 1 DATA, 2 VIN, 3 GND as the original.
    ports = []
    for index, y in enumerate((9.0, 19.95, 30.9, 41.85)):
        port = board.part("Connector_Generic:Conn_01x03", ref=f"J{5 + index}", value="Servo",
                          footprint="Connector_JST:JST_XH_B3B-XH-A_1x03_P2.50mm_Vertical")
        board.connect(data, port[1])
        board.connect(vin, port[2])
        board.connect(gnd, port[3])
        board.place(port, at=(60.6, y), rotation=90)
        ports.append(port)

    # The servo trunk, 2 mm: up from the bulk capacitor, over the camera slot, down the ports.
    trunk = 57.6
    board.track(vin, [bulk[1], (39.5, 21.6), (trunk, 21.6)], width=2.0)
    stubs = [port[2].position[1] for port in ports]
    board.track(vin, [(trunk, y) for y in sorted({*stubs, 21.6})], width=2.0)
    for port in ports:
        board.track(vin, [(trunk, port[2].position[1]), port[2]], width=2.0)
    # The Pi's current, 1.5 mm: buck output -> the ideal diode's drain; 1.2 mm from its source
    # around the 3V3 pin (no room between header pins) to the Pi's 5V pins 2 and 4.
    board.track(v5, [inductor[2], c_out[0][1], c_out[1][1], (13.4, 32.725), (13.4, 38.5), (13.4, 40.2)], width=1.5)
    board.track(v5, [(13.4, 38.5), d_5v["A"]], width=0.5)
    board.track(v5_pi, [pi_fet["2"], (12.135, 48.5), (6.2, 48.5), (6.2, 53.77), pi["2"], pi["4"]], width=1.2)

    for at in HOLES:
        board.hole(at=at, diameter=2.75)
    board.zone(gnd, layers=["F.Cu"])
    board.zone(gnd, layers=["B.Cu"], pads="solid")  # header pins: the routes leave no room for 2 spokes
    board.text("BUS SERVO HAT", at=(30.0, 20.5), size=1.2)
    board.autoroute()
    return board


if __name__ == "__main__":
    bus_servo_hat()
