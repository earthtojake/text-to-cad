"""Orbit's board, from its schematic, in KiCad edits (kicad_pcb.edit): each stage states the board it wants.

    cad run scripts/board.py setup     # board, 4 layers, JLCPCB rules, outline, the schematic's netlist
    cad run scripts/board.py place     # every part, the rings parametrically from geometry.py
    cad run scripts/board.py route     # the LED chain as arcs, power vias, the electronics on the back
    cad run scripts/board.py zones     # GND and +5V planes, pours, refill
    cad run scripts/board.py all       # the four in order

The geometry every stage and the CAD model share is geometry.py (radii, counts, the outline).
"""
from __future__ import annotations

import math
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from cad import kicad_pcb, kicad_sch  # noqa: E402
from kicode.board_types import (ArcTrack, BoardArc, BoardSegment, BoardText, Track, Via, Zone)  # noqa: E402
from kicode.geometry import Angle, PolygonWithHoles, PolyLine, PolyLineNode, Vector2  # noqa: E402
from kicode.proto.board.board_types_pb2 import BoardLayer as BL, ZoneConnectionStyle, ZoneType  # noqa: E402
from kicode.util.units import from_mm  # noqa: E402

import geometry as G  # noqa: E402

PROJECT = HERE.parent
BOARD = PROJECT / "orbit.kicad_pcb"
SCHEMATIC = PROJECT / "orbit.kicad_sch"


def v(x, y):
    return Vector2.from_xy(from_mm(x), from_mm(y))


def to_mm(vec):
    return (vec.x / 1e6, vec.y / 1e6)


# ------------------------------------------------------------------------------------------- setup

def setup(b):
    # 4 copper layers: F.Cu (LEDs, the chain), In1 GND, In2 +5V, B.Cu (the electronics)
    if b.get_copper_layer_count() != 4:
        others = [layer for layer in b.get_enabled_layers()
                  if layer not in (BL.BL_F_Cu, BL.BL_B_Cu) and not str(b.get_layer_name(layer)).startswith("In")]
        b.set_enabled_layers(4, others)
    rules = b.get_design_rules()
    r = rules.rules if hasattr(rules, "rules") else rules
    c = r.constraints
    c.min_clearance = from_mm(G.CLEARANCE)
    c.min_track_width = from_mm(G.MIN_TRACK)
    c.min_connection_width = from_mm(G.MIN_TRACK)
    c.min_via_annular_width = from_mm((G.VIA_D - G.VIA_DRILL) / 2)
    c.min_via_size = from_mm(G.VIA_D)
    c.min_through_drill = from_mm(0.2)       # the module's own thermal vias are 0.2 mm (JLCPCB: 0.15 mm min)
    c.copper_edge_clearance = from_mm(G.EDGE_CLEARANCE)
    c.hole_clearance = from_mm(0.19)         # GCT's USB4105 land pattern: 0.194 mm from its pegs to its GND pads
    c.hole_to_hole_min = from_mm(0.25)
    c.min_silk_text_height = from_mm(1.0)
    c.min_silk_text_thickness = from_mm(0.15)
    b.set_design_rules(r)
    # The outline: a circle with a flat where the USB-C receptacle meets the edge
    shapes = [s for s in b.get_shapes() if s.layer == BL.BL_Edge_Cuts]
    if not shapes:
        (x0, y0), (x1, y1), mid = G.outline_arc()
        arc = BoardArc()
        arc.start, arc.mid, arc.end = v(x0, y0), v(*mid), v(x1, y1)
        flat = BoardSegment()
        flat.start, flat.end = v(x1, y1), v(x0, y0)
        for shape in (arc, flat):
            shape.layer = BL.BL_Edge_Cuts
            shape.attributes.stroke.width = from_mm(0.1)
        b.create_items([arc, flat])
    # The schematic's parts and nets
    with tempfile.TemporaryDirectory() as tmp:
        (netlist,) = kicad_sch.export(str(SCHEMATIC), "netlist", tmp).written
        result = b.import_netlist(str(netlist))
        print("netlist:", result.report.strip().splitlines()[-3:] if result.report else "", "new footprints",
              result.new_footprint_count, "errors", result.error_count)


# ------------------------------------------------------------------------------------------- place

def placements():
    """Every part: (x, y) from the centre, KiCad orientation, side. The rings come from a radius and a count."""
    at = {}
    for i in range(G.N_MINUTE):
        deg = G.led_angle(i, G.N_MINUTE)
        center = G.polar(G.R_MINUTE, deg)
        at[f"D{i + 1}"] = (*center, G.led_rotation(deg), "F")
        at[f"C{101 + i}"] = (*G.local_to_board(G.CAP_LOCAL, center, deg), (G.led_rotation(deg) + 180) % 360, "F")
    for i in range(G.N_HOUR):
        deg = G.led_angle(i, G.N_HOUR)
        center = G.polar(G.R_HOUR, deg)
        at[f"D{G.N_MINUTE + i + 1}"] = (*center, G.led_rotation(deg), "F")
        at[f"C{101 + G.N_MINUTE + i}"] = (*G.local_to_board(G.CAP_LOCAL, center, deg),
                                          (G.led_rotation(deg) + 180) % 360, "F")
    for i, deg in enumerate(G.MOUNT_ANGLES):
        at[f"H{i + 1}"] = (*G.polar(G.MOUNT_R, deg), 0, "F")
    at.update({
        # Front, the face's centre: the ambient light sensor behind the diffuser's window, its bus pull-ups
        "U5": (0.0, 0.0, 0, "F"), "C9": (-3.1, -0.65, 180, "F"), "C10": (-3.1, -2.25, 180, "F"),
        "R8": (1.0, -3.0, 0, "F"), "R9": (1.0, 2.8, 0, "F"),
        "TP6": (*G.polar(31.0, 337.0), 0, "F"),
        # Front, inside the hour ring at 12: the EN, IO8 and BOOT pull-ups on a 3.3 V bus
        "R3": (3.4, -29.6, 90, "F"), "R6": (7.2, -29.6, 90, "F"),
        "R4": (10.5, -30.0, 90, "F"),
        # Back: the module at the top edge, antenna up, 100 nF at its 3V3 pin
        "U1": (*G.MODULE_AT, 0, "B"), "C6": (13.95, -51.6, 180, "B"),
        # Back: the 3.3 V regulator below the module
        "U2": (0.0, -29.0, 180, "B"), "C3": (-3.4, -28.0, 90, "B"), "C4": (2.6, -25.0, 180, "B"),
        "C5": (-1.6, -24.0, 0, "B"), "R5": (-2.4, -33.2, 270, "B"),
        # Back: the LED data level shifter and its 33 ohm, right of the module
        "U4": (15.0, -38.6, 180, "B"), "C8": (18.2, -37.4, 90, "B"), "R7": (16.9, -41.4, 180, "B"),
        # Back: BOOT and RESET
        "SW1": (14.5, -24.0, 0, "B"), "SW2": (-15.5, -22.0, 0, "B"), "C7": (-13.6, -27.0, 0, "B"),
        # Back: USB-C on the flat, its ESD array and CC pull-downs, the polyfuse, bulk capacitance
        "J1": (*G.USB_AT, 0, "B"), "U3": (0.0, 43.0, 270, "B"),
        "R1": (6.4, 36.6, 90, "B"), "R2": (-11.6, 30.0, 90, "B"),
        "F1": (-8.0, 53.6, 0, "B"),
        "C1": (-20.0, 8.0, 0, "B"), "C2": (16.0, 8.0, 0, "B"),
        # Back: test points: +5V, 3V3, GND and the console UART
        "TP1": (-5.0, 4.0, 0, "B"), "TP2": (-1.2, -19.0, 0, "B"), "TP3": (-2.0, 4.0, 0, "B"),
        "TP4": (-6.6, -34.0, 0, "B"), "TP5": (-5.6, -36.9, 0, "B"),
    })
    return at


HIDDEN_REFS = {"U5", "C9", "C10", "R8", "R9", "TP1", "TP2", "TP3", "TP4", "TP5", "TP6", "C8", "R7", "C5", "C3", "C4",
               "R5", "U2", "U4", "R3", "R4", "R6", "C6", "C7", "R1", "R2", "U3"}


def place(b):
    want = placements()
    footprints = {fp.reference_field.text.value: fp for fp in b.get_footprints()}
    missing = sorted(set(footprints) - set(want))
    if missing:
        raise SystemExit(f"no place for {missing}")
    flip = [fp for ref, fp in footprints.items() if (want[ref][3] == "B") != (fp.layer == BL.BL_B_Cu)]
    if flip:
        b.flip_items(flip)
        footprints = {fp.reference_field.text.value: fp for fp in b.get_footprints()}
    moved = []
    for ref, fp in footprints.items():
        x, y, rot, side = want[ref]
        if side == "B":
            rot = (rot + 180) % 360  # KiCad's back side at 0 degrees mirrors y; at 180 it mirrors x, as seen from the front
        target = v(G.CX + x, G.CY + y)
        ring_part = ref.startswith("D") or (ref.startswith("C") and len(ref) == 4)
        # 144 ring parts and the crowded small ones: references on the fab layer only; the silkscreen says
        # what a person needs (SILK below)
        show = not ring_part and ref not in HIDDEN_REFS
        if (fp.position != target or abs(fp.orientation.degrees - Angle.from_degrees(rot).normalize180().degrees) > 1e-6
                or fp.reference_field.visible != show):
            fp.orientation = Angle.from_degrees(rot)
            fp.position = target
            fp.reference_field.visible = show
            moved.append(fp)
    if moved:
        b.update_items(moved)
    print(f"place: {len(moved)} moved, {len(flip)} flipped")


# ------------------------------------------------------------------------------------------- route

LAYER = {"F.Cu": BL.BL_F_Cu, "B.Cu": BL.BL_B_Cu, "In1.Cu": BL.BL_In1_Cu, "In2.Cu": BL.BL_In2_Cu}


def route(b):
    import routing
    board = kicad_pcb.read(str(BOARD))
    bd, plan = routing.plan(board)
    nets = {n.name: n for n in b.get_nets()}
    old = list(b.get_tracks()) + list(b.get_vias())
    if old:
        b.remove_items(old)
    C = lambda p: v(G.CX + p[0], G.CY + p[1])  # noqa: E731
    items = []
    for net, layer, width, pts in plan.tracks:
        for a, c in zip(pts, pts[1:]):
            if math.dist(a, c) < 1e-6:
                continue
            t = Track()
            t.start, t.end, t.layer, t.width, t.net = C(a), C(c), LAYER[layer], from_mm(width), nets[net]
            items.append(t)
    for net, layer, width, s, m, e in plan.arcs:
        a = ArcTrack()
        a.start, a.mid, a.end, a.layer, a.width, a.net = C(s), C(m), C(e), LAYER[layer], from_mm(width), nets[net]
        items.append(a)
    for net, at in plan.vias:
        via = Via()
        via.position, via.net = C(at), nets[net]
        via.diameter, via.drill_diameter = from_mm(G.VIA_D), from_mm(G.VIA_DRILL)
        items.append(via)
    b.create_items(items)
    print(f"route: {len(plan.tracks)} polylines, {len(plan.arcs)} arcs, {len(plan.vias)} vias; "
          f"{len(plan.moved)} vias moved along the ring, {len(plan.dropped)} GND vias left out")
    for what, net, at, why in plan.dropped:
        print(f"  left out {what} at ({at[0]:.2f}, {at[1]:.2f}): {', '.join(sorted(set(why)))[:90]}")


# ------------------------------------------------------------------------------------------- zones

ZONES = [("GND", BL.BL_F_Cu, "front GND pour"), ("GND", BL.BL_In1_Cu, "GND plane"),
         ("+5V", BL.BL_In2_Cu, "+5V plane"), ("GND", BL.BL_B_Cu, "back GND pour")]


def outline_points(step=2.0):
    """The board's outline as a polygon (KiCad keeps a zone its copper-to-edge clearance from the real edge)."""
    half = math.degrees(math.asin(math.sqrt(G.R_BOARD ** 2 - G.FLAT_Y ** 2) / G.R_BOARD))
    a0, a1 = 180.0 + half, 540.0 - half          # clockwise from 12, from the flat's right end round to its left
    n = int((a1 - a0) / step)
    pts = [G.polar(G.R_BOARD, 180.0 - half)]
    pts += [G.polar(G.R_BOARD, (180.0 - half) - (360 - 2 * half) * k / n) for k in range(1, n)]
    pts.append(G.polar(G.R_BOARD, 180.0 + half))
    return pts


def zones(b):
    nets = {n.name: n for n in b.get_nets()}
    copper = [z for z in b.get_zones() if not z.is_rule_area() or z.name == "antenna keep-out"]
    if copper:
        b.remove_items(copper)      # the board holds exactly these pours and its own keep-out, made afresh each run
    new = []
    # The antenna's keep-out, on the board itself: the module's own rule area, flipped to the back over IPC,
    # does not stay over the antenna, so it keeps nothing out there. Espressif: no copper under the antenna,
    # 5 mm round it.
    keep = Zone()
    keep.type = ZoneType.ZT_RULE_AREA
    keep.name = "antenna keep-out"
    keep.layers = [BL.BL_F_Cu, BL.BL_In1_Cu, BL.BL_In2_Cu, BL.BL_B_Cu]
    ra = keep.rule_area_settings
    ra.keepout_copper = ra.keepout_vias = ra.keepout_tracks = ra.keepout_pads = True
    ra.keepout_footprints = False
    poly = keep._proto.outline.polygons.add()
    for x, y in ((-11.4, -64.3), (16.6, -64.3), (16.6, -52.7), (-11.4, -52.7)):
        node = poly.outline.nodes.add()
        node.point.CopyFrom(v(G.CX + x, G.CY + y).proto)
    poly.outline.closed = True
    new.append(keep)
    for net, layer, name in ZONES:
        z = Zone()
        z.layers = [layer]
        z.net = nets[net]
        z.name = name
        z.clearance = from_mm(0.2)
        z.min_thickness = from_mm(0.2)
        if layer in (BL.BL_F_Cu, BL.BL_B_Cu):  # the pours meet small pads solidly: spokes there neck below 0.15 mm
            z.connection.zone_connection = ZoneConnectionStyle.ZCS_FULL
        poly = z._proto.outline.polygons.add()
        for x, y in outline_points():
            node = poly.outline.nodes.add()
            node.point.CopyFrom(v(G.CX + x, G.CY + y).proto)
        poly.outline.closed = True
        new.append(z)
    if new:
        b.create_items(new)
    b.refill_zones()
    print(f"zones: {len(new)} made, all refilled")


# ------------------------------------------------------------------------------------------- silkscreen

# (text, (x, y) from the centre, layer, height mm): the legends a person reads (JLCPCB: >= 1.0 mm, 0.15 mm)
SILK = [
    ("ORBIT", (0.0, 9.0), "F", 2.0),
    ("60 + 12 LED RING CLOCK", (0.0, 12.5), "F", 1.0),
    ("ORBIT  rev A", (0.0, 18.0), "B", 2.0),
    ("ESP32-C3  WS2812B-2020 x72  USB-C 5V 3A", (0.0, 21.5), "B", 1.0),
    ("made with text-to-cad", (0.0, 24.5), "B", 1.0),
    ("BOOT", (14.5, -20.4), "B", 1.0), ("RESET", (-15.5, -18.4), "B", 1.0),
    ("TX", (-6.6, -31.9), "B", 1.0), ("RX", (-3.2, -37.6), "B", 1.0),
    ("5V", (-5.0, 7.2), "B", 1.0), ("GND", (-1.6, 7.2), "B", 1.0), ("3V3", (1.4, -19.0), "B", 1.0),
    ("USB-C", (0.0, 47.0), "B", 1.0),
]


def silk(b):
    have = {(t.value, t.layer) for t in b.get_text() if isinstance(t, BoardText)}
    new = []
    for text, (x, y), side, h in SILK:
        layer = BL.BL_F_SilkS if side == "F" else BL.BL_B_SilkS
        if (text, layer) in have:
            continue
        item = BoardText()
        item.value = text
        item.layer = layer
        item.position = v(G.CX + x, G.CY + y)
        item.attributes.size = Vector2.from_xy(from_mm(h), from_mm(h))
        item.attributes.stroke_width = from_mm(max(0.15, h * 0.15))
        item.attributes.mirrored = side == "B"
        new.append(item)
    if new:
        b.create_items(new)
    print(f"silk: {len(new)} legends")


STAGES = {"setup": setup, "place": place, "route": route, "zones": zones, "silk": silk}


def project_rules():
    """The netclasses, in the project file (Board Setup > Net Classes): JLCPCB's clearance for every net, and
    a Power class for +5V and VBUS at the width 3 A needs."""
    import json
    pro = PROJECT / "orbit.kicad_pro"
    data = json.loads(pro.read_text())
    ns = data["net_settings"]
    default = next(c for c in ns["classes"] if c["name"] == "Default")
    want = {"clearance": G.CLEARANCE, "track_width": G.SIGNAL, "via_diameter": G.VIA_D, "via_drill": G.VIA_DRILL,
            "diff_pair_width": G.SIGNAL, "diff_pair_gap": 0.2}
    power = {**default, "name": "Power", "track_width": G.POWER_WIDTH, "priority": 0}
    usb = {**default, "name": "USB", "priority": 1}
    changed = any(default.get(k) != val for k, val in want.items())
    default.update(want)
    for cls in (power, usb):
        cls.update({k: val for k, val in want.items() if k != "track_width"})
    classes = {c["name"]: c for c in ns["classes"]}
    for cls in (power, usb):
        if cls["name"] not in classes:
            ns["classes"].append(cls)
            changed = True
    patterns = [{"netclass": "Power", "pattern": "+5V"}, {"netclass": "Power", "pattern": "VBUS"},
                {"netclass": "USB", "pattern": "/Power/USB_D*"}]
    if ns.get("netclass_patterns") != patterns:
        ns["netclass_patterns"] = patterns
        changed = True
    if changed:
        pro.write_text(json.dumps(data, indent=2) + "\n")
        print("project rules: netclasses Default, Power, USB written to orbit.kicad_pro")


def main(stages):
    for stage in stages:
        with kicad_pcb.edit(str(BOARD)) as b:
            STAGES[stage](b)
        print(f"{stage}: saved {BOARD.name}")
        if stage == "setup":
            project_rules()


if __name__ == "__main__":
    names = sys.argv[1:] or ["all"]
    main(list(STAGES) if names == ["all"] else names)
