"""Simulate the bus servo HAT's circuits with ngspice: its servo bus at 1 Mbps, and plugging in its supply.

`python bus_servo_hat_sim.py` prints what it measured, then each check that failed, and exits 1 if
any did; its plots land in `../tmp/`. The circuits are the board's own (`bus_servo_hat_circuits.py`).
Their models are generic, fitted to the datasheets (`models/hat.lib` says where each number comes
from), so a thin margin here is worth confirming with the makers' models, or on the bench.
"""

import sys
from pathlib import Path

from cadgen import pcb

import bus_servo_hat_circuits as circuits

PLOTS = Path(__file__).resolve().parent.parent / "tmp"
failures = []


def check(ok, message):
    if not ok:
        failures.append(message)


def widest_dip(wave, level, start, stop):
    """The longest time ``wave`` stays below ``level`` between ``start`` and ``stop`` (0 if never)."""
    falls = wave.crossings(level, rising=False, start=start, stop=stop)
    rises = wave.crossings(level, rising=True, start=start, stop=stop)
    return max((min((r for r in rises if r > f), default=stop) - f for f in falls), default=0.0)


# ---- the servo bus -------------------------------------------------------------------------------

BIT = 1e-6  # 1 Mbps, the servos' default rate
VCC = 3.3
VIL, VIH = 0.8, 2.0  # what the buffers and the Pi's UART read as low and high at 3.3 V
THRESHOLD = VCC / 2  # where the buffers switch
PING = [0xFF, 0xFF, 0x01, 0x02, 0x01, 0xFB]  # the host pings servo 1...
STATUS = [0xFF, 0xFF, 0x01, 0x02, 0x00, 0xFC]  # ...which answers
HOST_START = 2e-6
HOST_END = HOST_START + 10 * len(PING) * BIT
REPLY_START = HOST_END + 10e-6  # the servo answers 10 us after the host's last stop bit
REPLY_END = REPLY_START + 10 * len(STATUS) * BIT
# The cable and the servos' inputs on DATA, as a capacitance (assumed): one servo on a short lead,
# four on a metre, a long chain. The 120 pF of the clamp diode on DATA is the board's own.
BUSES = ("100p", "300p", "1n")


def uart_bits(frame):
    for byte in frame:
        yield 0  # start bit
        yield from ((byte >> index) & 1 for index in range(8))  # least significant first
        yield 1  # stop bit


def uart(frame, start, edge=2e-9):
    """A UART line, idle high, sending ``frame`` from ``start``: ``(seconds, volts)`` for a pwl source."""
    points, level = [(0.0, VCC)], 1
    for index, bit in enumerate(uart_bits(frame)):
        if bit != level:
            at = start + index * BIT
            points += [(at, VCC * level), (at + edge, VCC * bit)]
            level = bit
    return points


def bus_bench(bus):
    """The board's bus switch between the Pi's UART and the servos' wire, and a servo that answers."""
    tb = pcb.Testbench(title=f"HAT servo bus, {bus}F on DATA")
    v3, tx, rx, data = tb.net("+3V3"), tb.net("TX"), tb.net("RX"), tb.net("DATA")
    switch = circuits.half_duplex(tb, v3, tb.ground, tx, rx, data)
    tb.source(v3, dc=VCC)
    # The Pi's TX pin: push-pull at 3.3 V, its default 8 mA drive about 40 ohm.
    pin, r_pin = tb.net("PI_TX"), tb.part("Device:R", value="40")
    tb.connect(pin, r_pin[1])
    tb.connect(tx, r_pin[2])
    tb.source(pin, dc=VCC, pwl=uart(PING, HOST_START))
    tb.load(data, farads=bus)
    # Servo 1 answers on the same wire, driving it only while it talks (a generic 3.3 V buffer).
    servo = tb.part("74xGxx:74LVC1G126", value="servo",
                    properties=circuits.model("LVC1G126", "1=OE 2=A 3=GND 4=Y 5=VCC"))
    talk, says = tb.net("SERVO_OE"), tb.net("SERVO_TX")
    tb.connect(talk, servo[1])
    tb.connect(says, servo[2])
    tb.connect(tb.ground, servo[3])
    tb.connect(data, servo[4])
    tb.connect(v3, servo[5])
    on, off = REPLY_START - 2 * BIT, REPLY_END + BIT
    tb.source(talk, dc=0, pwl=[(0, 0), (on, 0), (on + 2e-9, VCC), (off, VCC), (off + 2e-9, 0)])
    tb.source(says, dc=VCC, pwl=uart(STATUS, REPLY_START))
    return tb, switch


def check_bus(bus):
    tb, switch = bus_bench(bus)
    run = tb.transient(stop=REPLY_END + 3e-6, step=2e-9)
    tx, data, rx, txen = run["TX"], run["DATA"], run["RX"], run[switch.txen]
    name = f"bus {bus}F"

    # The servos hear the host: DATA, sampled mid-bit, is each bit the host sent.
    for index, bit in enumerate(uart_bits(PING)):
        at = HOST_START + (index + 0.5) * BIT
        level = data.at(at)
        check(level > VIH if bit else level < VIL, f"{name}: host bit {index} reads {level:.2f} V on DATA mid-bit; sent {bit}")
    # DATA follows TX: each of its edges, how long after TX's.
    host, heard = dict(start=HOST_START - BIT / 2, stop=HOST_END + BIT / 2), dict(start=HOST_START - BIT / 2, stop=HOST_END + BIT)
    tx_rises = tx.crossings(THRESHOLD, rising=True, **host)
    delays = {True: [], False: []}  # after each rise, after each fall
    for rising in (True, False):
        data_edges = data.crossings(THRESHOLD, rising=rising, **heard)
        for at in tx.crossings(THRESHOLD, rising=rising, **host):
            follow = [t for t in data_edges if at <= t < at + BIT / 2]
            check(bool(follow), f"{name}: DATA does not follow TX's {'rise' if rising else 'fall'} at {at * 1e6:.2f} us")
            if follow:
                delays[rising].append(follow[0] - at)
    # How long the '126 keeps driving after each rise (until TXEN crosses its threshold), and
    # how fast DATA rises: 10 to 90 %.
    windows, rise_times = [], []
    txen_falls = txen.crossings(THRESHOLD, rising=False, start=HOST_START, stop=REPLY_START)
    for at in tx_rises:
        off = [t for t in txen_falls if t > at]
        windows.append(off[0] - at if off else float("inf"))
    for at in data.crossings(THRESHOLD, rising=True, **heard):
        low = data.crossings(0.1 * VCC, rising=True, start=at - BIT / 2, stop=at)
        high = data.crossings(0.9 * VCC, rising=True, start=at, stop=at + BIT / 2)
        rise_times.append(high[0] - low[-1] if low and high else float("inf"))
    worst_rise = max(rise_times)
    check(worst_rise < 0.1 * BIT, f"{name}: DATA takes {worst_rise * 1e9:.0f} ns to rise (10-90 %), a tenth of a bit is 100 ns")
    distortion = max(delays[False]) - min(delays[True])
    check(abs(distortion) < 0.1 * BIT, f"{name}: low bits on DATA are {distortion * 1e9:.0f} ns short of TX's")
    # The host does not hear itself while it sends. As TX falls, TXEN turns the '126 on and the '125
    # off at once, so RX may dip for a moment; a UART samples 16 times a bit and checks a start bit
    # at its middle, so a dip shorter than one sample cannot be read as a bit.
    rx_low = rx.window(HOST_START, HOST_END + BIT).min()
    dip = widest_dip(rx, THRESHOLD, HOST_START, HOST_END + BIT)
    check(dip < BIT / 16, f"{name}: RX stays low for {dip * 1e9:.0f} ns while the host sends: it would read its own bytes")
    # The switch lets go of the bus soon after the host's last stop bit, before a servo answers.
    last_rise = max(tx_rises)
    released = [t for t in txen_falls if t > last_rise]
    release = released[0] - last_rise if released else float("inf")
    check(release < 2 * BIT, f"{name}: the bus is let go {release * 1e6:.2f} us after the host's last rise")
    check(data.window(last_rise + release + 0.2e-6, REPLY_START - 2 * BIT).min() > VIH,
          f"{name}: DATA does not rest high between the host's frame and the servo's")
    # The host hears the servo: RX, sampled mid-bit, is each bit the servo sent.
    for index, bit in enumerate(uart_bits(STATUS)):
        at = REPLY_START + (index + 0.5) * BIT
        level = rx.at(at)
        check(level > VIH if bit else level < VIL, f"{name}: servo bit {index} reads {level:.2f} V on RX mid-bit; sent {bit}")
    print(f"  {bus + 'F':>6}  DATA falls {max(delays[False]) * 1e9:4.0f} ns and rises {max(delays[True]) * 1e9:4.0f} ns after TX, "
          f"rises in {worst_rise * 1e9:4.0f} ns (driven {min(windows) * 1e9:4.0f} ns), low bits {distortion * 1e9:3.0f} ns short; "
          f"RX dips to {rx_low:.2f} V for {dip * 1e9:2.0f} ns; bus let go {release * 1e9:4.0f} ns after the last rise")
    return tb, switch


def plot_bus(bus):
    tb, switch = bus_bench(bus)
    nets = ["TX", switch.txen, "DATA", "RX"]
    tb.transient(stop=HOST_START + 12 * BIT, step=1e-9).plot(PLOTS / "hat_bus_host.png", nets=nets,
                                                            title=f"The host's first byte on DATA ({bus}F)")
    tb.transient(stop=REPLY_START + 12 * BIT, step=1e-9, start=HOST_END - 3 * BIT).plot(
        PLOTS / "hat_bus_turnaround.png", nets=nets, title=f"The host lets go and the servo answers ({bus}F)")


# ---- plugging in the supply ------------------------------------------------------------------------

BATTERY = 12.6  # a full 3S LiPo, the top of the HAT's input range
VIN_LOWEST = 9.0  # the bottom of its input range
VIN_ABS_MAX = 19.0  # TPS565208 datasheet: VIN absolute maximum (17 V recommended)
LEADS = ("300n", "1u", "2u")  # the battery lead's inductance: a lead pair has about 1 uH a metre
# The 220 uF capacitor's series resistance. The board's part, EEE-FK1E221P, has 0.16 ohm at most:
# it is checked at half that, that, and double that (cold, or aged). The others are what a
# different capacitor would do: a polymer's 0.02 ohm, a general-purpose can's 0.6.
PART_ESRS = ("0.08", "0.16", "0.32")
ESRS = ("0.02", *PART_ESRS, "0.6")
# TPS565208 datasheet: the EN pin's own resistance to ground (120 to 400 kOhm, 245 typical); EN is
# high above 1.6 V and low below 0.8 V, and typically turns on at 1.40 V and off at 1.10 V.
EN_PIN = {"typical": 245e3, "lowest": 120e3}
EN_ON_TYPICAL, EN_HIGH, EN_OFF_TYPICAL = 1.40, 1.6, 1.10


def supply_bench(en_pin=EN_PIN["typical"], bulk_esr="0.16", title="HAT supply"):
    """The input and the buck's input side; the TPS565208 itself is left out."""
    tb = pcb.Testbench(title=title)
    vin, v5 = tb.net("VIN"), tb.net("+5V")
    power = circuits.power_input(tb, vin, tb.ground, bulk_esr=bulk_esr)
    buck = circuits.buck(tb, vin, v5, tb.ground)
    # The TPS565208's EN pin pulls down through its own resistance; BST, which only its boost
    # capacitor reaches with the IC out, gets a path to ground.
    tb.load(buck.en, ohms=en_pin)
    tb.load(buck.bst, ohms=1e9)
    return tb, vin, power, buck


def plug_bench(lead, esr, into):
    """The battery plugged in at 1 us through its lead (20 mOhm with its own resistance, ``lead`` henries)."""
    tb, vin, power, buck = supply_bench(bulk_esr=esr, title=f"HAT plug-in: {lead}H lead, {esr} ohm ESR, into the {into}")
    cell, end = tb.net("BATTERY"), tb.net("LEAD")
    tb.source(cell, dc=0, pulse=dict(v1=0, v2=BATTERY, delay=1e-6, rise=20e-9))
    resistance, inductance = tb.part("Device:R", value="20m"), tb.part("Device:L", value=lead)
    tb.connect(cell, resistance[1])
    tb.connect(end, resistance[2], inductance[1])
    tb.connect(power.vin_raw if into == "terminal" else vin, inductance[2])
    tb.probe(inductance[1], power.tvs[1])
    return tb, power, inductance


def check_plug_in():
    worst, worst_part = None, None
    print(f"  {'into':8} {'lead':>5} {'ESR':>5}  {'VIN peak':>8}  {'inrush':>7}  {'TVS':>6}  {'FET VGS':>7}")
    for into in ("terminal", "jack"):
        for lead in LEADS:
            for esr in ESRS:
                tb, power, inductance = plug_bench(lead, esr, into)
                run = tb.transient(stop=300e-6, step=20e-9)
                peak = run["VIN"].max()
                vgs = (run[power.gate] - run["VIN"]).min()
                print(f"  {into:8} {lead + 'H':>5} {esr:>5}  {peak:6.2f} V  {run.current(inductance[1]).max():5.1f} A  "
                      f"{run.current(power.tvs[1]).max():4.2f} A  {vgs:5.2f} V" + ("" if esr in PART_ESRS else "  (another capacitor)"))
                if worst is None or peak > worst[0]:
                    worst = (peak, tb, into, lead, esr)
                if esr in PART_ESRS and (worst_part is None or peak > worst_part[0]):
                    worst_part = (peak, tb, into, lead, esr)
    peak, tb, into, lead, esr = worst_part
    tb.transient(stop=300e-6, step=20e-9).plot(PLOTS / "hat_plug_in.png", nets=["BATTERY", "VIN_RAW", "VIN"],
                                                title=f"Plugging in 12.6 V: {lead}H lead, {esr} ohm ESR, into the {into}")
    check(peak < VIN_ABS_MAX, f"plug-in: VIN peaks at {peak:.1f} V ({lead}H lead, {esr} ohm ESR, into the {into}); "
                              f"the TPS565208's VIN absolute maximum is {VIN_ABS_MAX:g} V")
    print(f"  the board's capacitor: VIN peaks at {peak:.2f} V at worst ({lead}H lead, {esr} ohm, into the {into}); "
          f"another capacitor: {worst[0]:.2f} V ({worst[3]}H lead, {worst[4]} ohm, into the {worst[2]})")


def check_buck_start():
    """Where the buck starts as VIN rises: the EN divider against the TPS565208's EN thresholds."""
    starts = {}
    for case, en_pin in EN_PIN.items():
        tb, vin, power, buck = supply_bench(en_pin=en_pin, title=f"HAT EN divider, {case} EN pin")
        supply = tb.source(vin, dc=0)
        en = tb.dc_sweep(supply, 0, BATTERY, 0.01)[buck.en]
        starts[case] = {level: en.crossings(level)[0] for level in (EN_ON_TYPICAL, EN_HIGH, EN_OFF_TYPICAL)}
    typical, lowest = starts["typical"], starts["lowest"]
    print(f"  typically starts at VIN {typical[EN_ON_TYPICAL]:.2f} V and stops at {typical[EN_OFF_TYPICAL]:.2f} V; "
          f"sure to start only above {lowest[EN_HIGH]:.2f} V (EN 1.6 V, the EN pin's lowest resistance)")
    check(lowest[EN_HIGH] <= VIN_LOWEST, f"buck start: the buck is sure to start only above VIN {lowest[EN_HIGH]:.1f} V, "
                                         f"over the HAT's lowest input, {VIN_LOWEST:g} V: the Pi may get no 5 V")


if __name__ == "__main__":
    PLOTS.mkdir(exist_ok=True)
    print("Servo bus at 1 Mbps (the host pings servo 1, which answers):")
    for bus in BUSES:
        check_bus(bus)
    plot_bus("300p")
    print(f"Plugging in {BATTERY} V:")
    check_plug_in()
    print("The buck's start:")
    check_buck_start()
    print(f"Plots: {PLOTS}")
    for failure in failures:
        print(f"FAILED {failure}")
    sys.exit(1 if failures else 0)
