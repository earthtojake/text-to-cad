"""Layout step 0: the board's rules, from JLCPCB's standard 2-layer service (1 oz copper, HASL or ENIG),
https://jlcpcb.com/capabilities/pcb-capabilities as the pcb skill's manufacturing reference tabulates it
(read 2026-11-04): track/space 0.10/0.10 mm minimum, drill 0.15 mm (0.3 mm without surcharge), via
0.15/0.25 mm hole/pad minimum, annular ring 0.18 mm on plated holes, copper to routed edge 0.2 mm,
silkscreen 1.0 mm text / 0.15 mm stroke. The board keeps a margin over each: 0.15 mm space, 0.2 mm
tracks, 0.3/0.6 mm vias (no surcharge), 0.3 mm to the edge.

Netclasses, by current (IPC-2221, outer layer, 10 C rise, 1 oz):
  Power (VBUS, +5V): 0.5 mm, 1.5 A; nine LEDs at 60 mA full white are 0.54 A. GND is a pour on both
  layers (its few tracks 0.3-0.5 mm), at the default clearance.
  Supply (+3V3, +1V1): 0.3 mm, 0.9 A against the RP2040's 50 mA and the flash's 25 mA.
  USB (the pair): 0.25 mm at a 0.2 mm gap. USB full speed (12 Mb/s, the RP2040's only speed) has
  no controlled-impedance requirement on a 1.6 mm two-layer board; the pair is kept short and coupled.
Writes the project file (.kicad_pro) and the custom rules (.kicad_dru). Run with any Python.
"""
import json
import os

PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRO = os.path.join(PROJ, "macropad.kicad_pro")

d = json.load(open(PRO))
rules = d["board"]["design_settings"]["rules"]
rules.update({"min_clearance": 0.15, "min_track_width": 0.15, "min_via_diameter": 0.5, "min_via_annular_width": 0.1,
              "min_through_hole_diameter": 0.3, "min_hole_clearance": 0.25, "min_hole_to_hole": 0.25,
              "min_copper_edge_clearance": 0.3, "min_text_height": 0.8, "min_text_thickness": 0.12,
              "min_silk_clearance": 0.0})
d["board"]["design_settings"].setdefault("defaults", {})["board_outline_line_width"] = 0.1
base = dict(d["net_settings"]["classes"][0])
default = dict(base, name="Default", track_width=0.2, clearance=0.15, via_diameter=0.6, via_drill=0.3)
power = dict(base, name="Power", track_width=0.5, clearance=0.2, via_diameter=0.6, via_drill=0.3, priority=0)
supply = dict(base, name="Supply", track_width=0.3, clearance=0.15, via_diameter=0.6, via_drill=0.3, priority=1)
usb = dict(base, name="USB", track_width=0.25, clearance=0.15, diff_pair_width=0.25, diff_pair_gap=0.2,
           via_diameter=0.6, via_drill=0.3, priority=2)
d["net_settings"]["classes"] = [default, power, supply, usb]
d["net_settings"]["netclass_patterns"] = [
    {"netclass": "Power", "pattern": "VBUS"}, {"netclass": "Power", "pattern": "+5V"},
    {"netclass": "Supply", "pattern": "+3V3"}, {"netclass": "Supply", "pattern": "+1V1"},
    {"netclass": "USB", "pattern": "*USB_D*"}, {"netclass": "USB", "pattern": "*RP_D*"},
]
json.dump(d, open(PRO, "w"), indent=2)

open(os.path.join(PROJ, "macropad.kicad_dru"), "w").write('''(version 2)
# GCT's land pattern for the USB4105 puts its pads 0.17 mm from its own locating pegs (the same rule
# the repository's usb_uart example carries)
(rule "J1 land pattern"
  (constraint hole_clearance (min 0.15mm))
  (condition "A.memberOfFootprint('J1') && B.memberOfFootprint('J1')"))
# the receptacle's ground pads and shell tabs sit too close for thermal spokes: solid to the pours
(rule "J1 solid to pour"
  (constraint zone_connection solid)
  (condition "A.memberOfFootprint('J1') && A.NetName == 'GND'"))
# the encoder's two ground pins sit between its signal pins, where the top pour cannot always reach
# with two spokes: solid to the pour (a 1 mm THT pin hand-solders fine solid)
(rule "SW10 ground solid"
  (constraint zone_connection solid)
  (condition "A.memberOfFootprint('SW10') && A.NetName == 'GND'"))
# the SK6812MINI-E's stock land pattern sits 0.247 mm from its own cut-out (the window it shines
# through); JLCPCB routes copper to 0.2 mm of an edge, so the LEDs alone get 0.2 mm
(rule "LED cut-out"
  (constraint edge_clearance (min 0.2mm))
  (condition "A.memberOfFootprint('D*')"))
# the RP2040's 0.4 mm pads: its own fan-out runs at the netclass minimum under the package
(rule "QFN fan-out"
  (constraint track_width (min 0.15mm))
  (condition "A.intersectsCourtyard('U1')"))
# bends at 45 or 90 degrees, none acute (85: a right angle measures 89.9999 after rounding)
(rule "no acute bends"
  (constraint track_angle (min 85deg))
  (condition "A.Type == 'Track'"))
''')
print("rules written")
