"""The bus servo HAT's circuits: each block's parts and how they connect, shared by the board and
its testbenches.

`bus_servo_hat.py` lays these blocks out on the HAT and `bus_servo_hat_sim.py` simulates them, so
the circuit tested is the circuit made. A block takes the circuit it is built in, a board or a
`pcb.Testbench`, and the nets it joins; it adds its parts in a fixed order (the board's reference
designators follow that order) and returns them by name.

A part a testbench includes simulates from its own `Sim.*` fields, which reach the board's
schematic too. The models are generic, fitted to the datasheets, in `models/hat.lib`, which says
where each number comes from. A part with no model a testbench can run (the TPS565208, the
AMS1117, the CH343P, a connector) is left out of simulation, and a testbench drives its nets.
"""

from types import SimpleNamespace

R_0603 = "Resistor_SMD:R_0603_1608Metric"
C_0603 = "Capacitor_SMD:C_0603_1608Metric"
C_0805 = "Capacitor_SMD:C_0805_2012Metric"
C_1206 = "Capacitor_SMD:C_1206_3216Metric"
SOD_323 = "Diode_SMD:D_SOD-323"
SOT_23_5 = "Package_TO_SOT_SMD:SOT-23-5"

# A testbench reads a model path from this folder, KiCad from the board's project folder
# (`../PCB`); this one reaches the same file from both.
MODELS = "../src/models/hat.lib"
# A connector, or an IC with no model: left out of simulation.
UNSIMULATED = {"Sim.Enable": "0"}


def model(name, pins=None, params=None):
    """The `Sim.*` fields that simulate a part as `name` in `models/hat.lib`."""
    fields = {"Sim.Library": MODELS, "Sim.Name": name}
    if pins:
        fields["Sim.Pins"] = pins
    if params:
        fields["Sim.Params"] = params
    return fields


def resistor(c, value):
    return c.part("Device:R", footprint=R_0603, value=value)


def capacitor(c, value, footprint=C_0603):
    # A value with its rating ("10u 25V") is a label KiCad's simulator cannot read: the
    # capacitance goes in Sim.Params, and the label stays the board's.
    farads, _, rating = value.partition(" ")
    properties = {"Sim.Params": f"c={farads}"} if rating else None
    return c.part("Device:C", footprint=footprint, value=value, properties=properties)


def schottky(c):
    return c.part("Device:D_Schottky", footprint=SOD_323, value="B5819WS",
                  properties={"MPN": "B5819WS", **model("B5819WS", "1=K 2=A")})


def power_input(c, vin, gnd, *, bulk_esr="0.16"):
    """The barrel jack straight onto VIN; the screw terminal through a P-FET that blocks reversed wires.

    The 220 uF capacitor's series resistance damps the supply's ringing when it is plugged in, so
    the board names the part: Panasonic's EEE-FK1E221P, 0.16 ohm at most at 100 kHz and 20 C.
    A capacitor of more (a general-purpose can) lets the ringing reach the TVS's clamp, at the
    buck's absolute maximum; one of much less (a polymer) damps nothing. `bulk_esr` is its
    resistance in ohms, which a testbench varies.
    """
    vin_raw, gate = c.net("VIN_RAW"), c.net("GATE")
    jack = c.part("Connector:Barrel_Jack_Switch", footprint="Connector_BarrelJack:BarrelJack_Horizontal",
                  value="DC 5.5x2.1", ref="J2", properties=UNSIMULATED)
    terminal = c.part("Connector:Screw_Terminal_01x02", ref="J3", value="KF350-2P",
                      footprint="TerminalBlock_Phoenix:TerminalBlock_Phoenix_PT-1,5-2-3.5-H_1x02_P3.50mm_Horizontal",
                      properties=UNSIMULATED)
    # AO4407A (-30 V, 12 A, 12.7 mOhm at -6 V) in the FDS9435A's SO-8 pinout: S 1-3, G 4, D 5-8.
    fet = c.part("Transistor_FET:FDS9435A", value="AO4407A",
                 properties={"MPN": "AO4407A", **model("AO4407A", "1=S 2=S 3=S 4=G 5=D 6=D 7=D 8=D")})
    zener = c.part("Device:D_Zener", footprint=SOD_323, value="BZT52C6V8S",
                   properties={"MPN": "BZT52C6V8S", **model("BZT52C6V8", "1=K 2=A")})
    tvs = c.part("Device:D_TVS", footprint="Diode_SMD:D_SMA", value="SMAJ15CA",
                 properties={"MPN": "SMAJ15CA", **model("SMAJ15CA", "1=A1 2=A2")})
    bulk = c.part("Device:C_Polarized", footprint="Capacitor_SMD:CP_Elec_8x10", value="220u 25V",
                  properties={"MPN": "EEE-FK1E221P", "Manufacturer": "Panasonic", "LCSC": "C128511",
                              **model("ECAP", "1=P 2=N", f"c=220u esr={bulk_esr} esl=10n")})
    c.connect(vin, jack[1], *[fet[n] for n in ("1", "2", "3")], zener["K"], tvs[1], bulk[1])
    c.connect(gnd, jack[2], jack[3], terminal[1], tvs[2], bulk[2])
    c.connect(vin_raw, terminal[2], *[fet[n] for n in ("5", "6", "7", "8")])
    c.connect(gate, fet["4"], zener["A"])
    r_gate = resistor(c, "2k")
    c.connect(gate, r_gate[1])
    c.connect(gnd, r_gate[2])
    return SimpleNamespace(jack=jack, terminal=terminal, fet=fet, zener=zener, tvs=tvs, bulk=bulk, r_gate=r_gate,
                           vin_raw=vin_raw, gate=gate)


def buck(c, vin, v5, gnd):
    """TPS565208, 5 A: VOUT = 0.76 V x (1 + 57.6k / 10k) = 5.14 V.

    EN is 100k over 30k, against the EN pin's own 120 to 400 kOhm to ground: the buck starts at
    about 6.6 V, and is sure to by 8.3 V, under the HAT's lowest input, 9 V. The TPS565208 itself
    is left out of simulation; a testbench stands in for its pins.
    """
    sw, bst, fb, en = c.net("SW"), c.net("BST"), c.net("FB"), c.net("EN")
    u = c.part("Regulator_Switching:TPS565208", value="TPS565208",
               properties={"MPN": "TPS565208DDCR", **UNSIMULATED})
    inductor = c.part("Device:L", footprint="Inductor_SMD:L_Bourns_SRP7028A_7.3x6.6mm", value="3.3u",
                      properties={"MPN": "SRP7028A-3R3M"})
    c_hf = capacitor(c, "100n")
    c_in = [capacitor(c, "10u 25V", footprint=C_1206) for _ in range(2)]
    c_out = [capacitor(c, "22u 10V", footprint=C_1206) for _ in range(2)]
    c_bst = capacitor(c, "100n")
    r_en_top, r_en_bot = resistor(c, "100k"), resistor(c, "30k")
    r_fb_top, r_fb_bot = resistor(c, "57.6k"), resistor(c, "10k")

    c.connect(vin, u["VIN"], c_hf[1], c_in[0][1], c_in[1][1], r_en_top[1])
    c.connect(gnd, u["GND"], c_hf[2], c_in[0][2], c_in[1][2], c_out[0][2], c_out[1][2], r_en_bot[2], r_fb_bot[2])
    c.connect(en, u["EN"], r_en_top[2], r_en_bot[1])
    c.connect(sw, u["SW"], inductor[1], c_bst[1])
    c.connect(bst, u["VBST"], c_bst[2])
    c.connect(v5, inductor[2], c_out[0][1], c_out[1][1], r_fb_top[1])
    c.connect(fb, u["VFB"], r_fb_top[2], r_fb_bot[1])
    return SimpleNamespace(u=u, inductor=inductor, c_hf=c_hf, c_in=c_in, c_out=c_out, c_bst=c_bst,
                           r_en_top=r_en_top, r_en_bot=r_en_bot, r_fb_top=r_fb_top, r_fb_bot=r_fb_bot,
                           sw=sw, bst=bst, fb=fb, en=en)


def ideal_diode(c, v5, v5_pi, gnd):
    """The buck's 5 V to the Pi's 5V pins through a P-FET that turns off when the Pi's side is higher.

    Raspberry Pi's own back-powering circuit: a PNP pair compares the two sides; while the
    buck's side is higher the gate is pulled low (FET on), and the moment the Pi's side is
    higher (the Pi on its own USB-C, the servo supply off) the second PNP pulls the gate up.
    """
    gate, ref = c.net("PI_GATE"), c.net("PI_REF")
    fet = c.part("Transistor_FET:AON6411", value="AON6411", properties={"MPN": "AON6411"})
    pair = c.part("Transistor_BJT:MMDT3906", value="MMDT3906", properties={"MPN": "MMDT3906-7-F"})
    r_ref, r_gate = resistor(c, "47k"), resistor(c, "10k")
    c.connect(v5, fet["D"], pair["E1"])
    c.connect(v5_pi, *[fet[n] for n in ("1", "2", "3")], pair["E2"])
    c.connect(ref, pair["B1"], pair["C1"], pair["B2"], r_ref[1])
    c.connect(gate, fet["G"], pair["C2"], r_gate[1])
    c.connect(gnd, r_ref[2], r_gate[2])
    return SimpleNamespace(fet=fet, pair=pair, r_ref=r_ref, r_gate=r_gate, gate=gate, ref=ref)


def logic_supply(c, v5, vbus, v3, gnd):
    """3.3 V for the logic from whichever is up, the buck's 5 V or USB's, as the original does."""
    ldo_in = c.net("LDO_IN", power_flag=True)  # fed through the OR-ing diodes
    ldo = c.part("Regulator_Linear:AMS1117-3.3", value="AMS1117-3.3", properties=UNSIMULATED)
    d_5v, d_usb = schottky(c), schottky(c)
    c_in = capacitor(c, "10u", footprint=C_0805)
    c_out = capacitor(c, "22u", footprint=C_0805)
    c.connect(v5, d_5v["A"])
    c.connect(vbus, d_usb["A"])
    c.connect(ldo_in, d_5v["K"], d_usb["K"], ldo["VI"], c_in[1])
    c.connect(v3, ldo["VO"], c_out[1])
    c.connect(gnd, ldo["GND"], c_in[2], c_out[2])
    # A red LED: 2.0 V at 20 mA (KiCad's LED symbol names its pins but carries no model).
    led = c.part("Device:LED", footprint="LED_SMD:LED_0603_1608Metric", value="red",
                 properties={"Sim.Device": "D", "Sim.Params": "is=6e-19 n=2 rs=2"})
    r_led = resistor(c, "1k")
    c.connect(v3, r_led[1])
    c.connect(c.net(), r_led[2], led["A"])
    c.connect(gnd, led["K"])
    return SimpleNamespace(ldo=ldo, d_5v=d_5v, d_usb=d_usb, c_in=c_in, c_out=c_out, led=led, r_led=r_led,
                           ldo_in=ldo_in)


def usb_bridge(c, ldo_in, vbus, v3, gnd, ch_txd, ch_rxd):
    """USB-C to a CH343P. Its core runs from LDO_IN (5 V mode, V3 its own regulator's output),
    its I/O at 3.3 V, so it is powered whenever the board is."""
    usb = c.part("Connector:USB_C_Receptacle_USB2.0_16P", ref="J4", value="USB-C",
                 footprint="Connector_USB:USB_C_Receptacle_GCT_USB4105-xx-A_16P_TopMnt_Horizontal",
                 properties={"MPN": "USB4105-GF-A", **UNSIMULATED})
    bridge = c.part("Interface_USB:CH343P", value="CH343P", properties={"MPN": "CH343P", **UNSIMULATED})
    dp, dn, v3_core = c.net("USB_DP"), c.net("USB_DN"), c.net("CH_V3")
    for pin in usb.pins():
        if pin.name == "GND":
            c.connect(gnd, pin)
        elif pin.name == "VBUS":
            c.connect(vbus, pin)
        elif pin.name == "D+":
            c.connect(dp, pin)
        elif pin.name == "D-":
            c.connect(dn, pin)
    r_cc1, r_cc2 = resistor(c, "5.1k"), resistor(c, "5.1k")
    c.connect(c.net("CC1"), usb["CC1"], r_cc1[1])
    c.connect(c.net("CC2"), usb["CC2"], r_cc2[1])
    c.connect(gnd, r_cc1[2], r_cc2[2], usb["SHIELD"])
    c.no_connect(*usb.unconnected())

    c_vbus = capacitor(c, "10u", footprint=C_0805)
    c_vdd5, c_vio = capacitor(c, "1u"), capacitor(c, "1u")
    c_v3 = capacitor(c, "100n", footprint="Capacitor_SMD:C_0402_1005Metric")
    c.connect(vbus, bridge["VBUS"], c_vbus[1])
    c.connect(ldo_in, bridge["VDD5"], c_vdd5[1])
    c.connect(v3_core, bridge["V3_{OUT}"], c_v3[1])
    c.connect(v3, bridge["VIO"], c_vio[1])
    c.connect(gnd, bridge["GND"], bridge["GND_EPAD"], c_vbus[2], c_vdd5[2], c_vio[2], c_v3[2])
    c.connect(dp, bridge["UD+"])
    c.connect(dn, bridge["UD-"])
    c.connect(ch_txd, bridge["TXD"])
    c.connect(ch_rxd, bridge["RXD"])
    c.no_connect(*bridge.unconnected())
    return SimpleNamespace(usb=usb, bridge=bridge, r_cc1=r_cc1, r_cc2=r_cc2, c_vbus=c_vbus, c_vdd5=c_vdd5,
                           c_vio=c_vio, c_v3=c_v3)


def half_duplex(c, v3, gnd, u1txd, u1rxd, data):
    """The auto-direction switch: TX low -> PNP on -> TXEN high -> '126 drives DATA, '125 off.

    When TX goes high again the '126 drives DATA high until the PNP turns off and TXEN falls;
    then the 10k pull-up holds it, and the '125 passes DATA back to the host's RX.
    """
    txen, base = c.net("TXEN"), c.net("BASE")
    q = c.part("Transistor_BJT:MMBT3906", value="MMBT3906",
               properties={"MPN": "MMBT3906LT1G", **model("MMBT3906")})
    drive = c.part("74xGxx:74LVC1G126", footprint=SOT_23_5, value="74LVC1G126",
                   properties={"MPN": "SN74LVC1G126DBVR", **model("LVC1G126", "1=OE 2=A 3=GND 4=Y 5=VCC")})
    listen = c.part("74xGxx:74LVC1G125", footprint=SOT_23_5, value="74LVC1G125",
                    properties={"MPN": "SN74LVC1G125DBVR", **model("LVC1G125", "1=OEN 2=A 3=GND 4=Y 5=VCC")})
    r_txpu, r_base, r_txen = resistor(c, "10k"), resistor(c, "10k"), resistor(c, "20k")
    r_data, r_rxpu = resistor(c, "10k"), resistor(c, "10k")
    c_drive, c_listen, c_bulk = capacitor(c, "100n"), capacitor(c, "100n"), capacitor(c, "1u")
    clamp = schottky(c)
    c.connect(v3, q["E"], r_txpu[1], r_data[1], r_rxpu[1], drive["VCC"], listen["VCC"],
              c_drive[1], c_listen[1], c_bulk[1])
    c.connect(u1txd, r_txpu[2], r_base[1], drive["2"])
    c.connect(base, r_base[2], q["B"])
    c.connect(txen, q["C"], r_txen[1], drive["1"], listen["1"])
    c.connect(data, drive["4"], r_data[2], listen["2"], clamp["K"])
    c.connect(u1rxd, listen["4"], r_rxpu[2])
    c.connect(gnd, r_txen[2], drive["GND"], listen["GND"], c_drive[2], c_listen[2], c_bulk[2], clamp["A"])
    return SimpleNamespace(q=q, drive=drive, listen=listen, r_txpu=r_txpu, r_base=r_base, r_txen=r_txen,
                           r_data=r_data, r_rxpu=r_rxpu, c_drive=c_drive, c_listen=c_listen, c_bulk=c_bulk,
                           clamp=clamp, txen=txen, base=base)
