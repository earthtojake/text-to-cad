# /// script
# dependencies = ["shapely>=2", "scipy"]
# ///
"""SHORT CIRCUIT's playfield board, from its schematic and the design model, in KiCad edits.

    cad run scripts/board.py setup     # the board, 4 layers, JLCPCB rules, the outline, the schematic's netlist
    cad run scripts/board.py place     # every part, from geometry.py (the design model's numbers)
    cad run scripts/board.py art       # the playfield's art: gold (copper + mask), silkscreen, stitching vias
    cad run scripts/board.py route     # every track and via (routes.py)
    cad run scripts/board.py zones     # the ground planes and pours, refilled
    cad run scripts/board.py silk      # the underside's legends
    cad run scripts/board.py all       # the six in order, then finish (title block, stackup)

`route` reads tmp/routes.json, which `cad run scripts/routes.py` plans from the placed board; `build.py` runs every
step in order. The board is build output, saved with its zones' fills (what DRC and check_board.py read).
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from cad import kicad_pcb, kicad_sch  # noqa: E402
from kicode.board_types import BoardCircle, BoardPolygon, BoardSegment, BoardText, Track, Via, Zone  # noqa: E402
from kicode.geometry import Angle, PolygonWithHoles, PolyLine, PolyLineNode, Vector2  # noqa: E402
from kicode.proto.board.board_types_pb2 import BoardLayer as BL, ZoneConnectionStyle  # noqa: E402
from kicode.util.units import from_mm  # noqa: E402

import geometry as G  # noqa: E402

L = G.L
PROJECT = G.PROJECT
BOARD = PROJECT / "pinball.kicad_pcb"
SCHEMATIC = PROJECT / "pinball.kicad_sch"
LAYER = {"F.Cu": BL.BL_F_Cu, "B.Cu": BL.BL_B_Cu, "In1.Cu": BL.BL_In1_Cu, "In2.Cu": BL.BL_In2_Cu}


def v(x, y):
    return Vector2.from_xy(from_mm(x), from_mm(y))


def pf(x, y):
    """A playfield point as a KiCad vector."""
    return v(*G.kicad(x, y))


def polygon_of(poly, layer, net=None, width=0.0, fill=True):
    """A hole-free shapely polygon (playfield frame) as a filled board polygon."""
    outline = PolyLine()
    for x, y in G.kpoly(poly):
        outline.append(PolyLineNode.from_point(v(x, y)))
    outline.closed = True
    item = BoardPolygon()
    pwh = PolygonWithHoles()
    pwh.outline = outline
    item.polygons.append(pwh)
    item.layer = layer
    item.attributes.stroke.width = from_mm(width)
    item.attributes.fill.filled = fill
    if net is not None:
        item.net = net
    return item


def setup(b):
    if b.get_copper_layer_count() != 4:
        others = [layer for layer in b.get_enabled_layers()
                  if layer not in (BL.BL_F_Cu, BL.BL_B_Cu) and not str(b.get_layer_name(layer)).startswith("In")]
        b.set_enabled_layers(4, others)
    rules = b.get_design_rules()
    r = rules.rules if hasattr(rules, "rules") else rules
    c = r.constraints
    c.min_clearance = from_mm(G.CLEARANCE)
    c.min_track_width = from_mm(0.15)
    c.min_connection_width = from_mm(0.15)
    c.min_via_annular_width = from_mm(0.13)
    c.min_via_size = from_mm(0.6)
    c.min_through_drill = from_mm(0.3)
    c.copper_edge_clearance = from_mm(G.EDGE_CLEARANCE)
    c.hole_clearance = from_mm(G.HOLE_CLEARANCE)
    c.hole_to_hole_min = from_mm(0.25)
    c.min_silk_text_height = from_mm(0.6)
    c.min_silk_text_thickness = from_mm(0.1)
    b.set_design_rules(r)
    # the outline: the design model's rounded rectangle, as arcs and lines
    if not [s for s in b.get_shapes() if s.layer == BL.BL_Edge_Cuts]:
        make_outline(b)
    with tempfile.TemporaryDirectory() as tmp:
        (netlist,) = kicad_sch.export(str(SCHEMATIC), "netlist", tmp).written
        result = b.import_netlist(str(netlist))
        print("netlist: new footprints", result.new_footprint_count, "errors", result.error_count)
        if result.error_count:
            print(result.report)


def make_outline(b):
    from kicode.board_types import BoardArc
    W, H, R = L.BOARD_W, L.BOARD_L, L.BOARD_CORNER
    k = 1 - 0.7071067811865476
    items = []

    def seg(a, c):
        s = BoardSegment()
        s.start, s.end = pf(*a), pf(*c)
        items.append(s)

    def arc(a, m, c):
        s = BoardArc()
        s.start, s.mid, s.end = pf(*a), pf(*m), pf(*c)
        items.append(s)
    seg((R, 0), (W - R, 0))
    arc((W - R, 0), (W - R * k, R * k), (W, R))
    seg((W, R), (W, H - R))
    arc((W, H - R), (W - R * k, H - R * k), (W - R, H))
    seg((W - R, H), (R, H))
    arc((R, H), (R * k, H - R * k), (0, H - R))
    seg((0, H - R), (0, R))
    arc((0, R), (R * k, R * k), (R, 0))
    for s in items:
        s.layer = BL.BL_Edge_Cuts
        s.attributes.stroke.width = from_mm(0.1)
    b.create_items(items)


NAMED = {"U3", "U5", "U8", "U9", "SW1", "SW2"}


def place(b):
    want = G.part_places()
    footprints = {fp.reference_field.text.value: fp for fp in b.get_footprints()}
    missing = sorted(set(footprints) - set(want))
    if missing:
        raise SystemExit(f"no place for {missing}")
    absent = sorted(set(want) - set(footprints))
    if absent:
        raise SystemExit(f"not on the board: {absent}")
    flip = [fp for ref, fp in footprints.items() if (want[ref][3] == "B") != (fp.layer == BL.BL_B_Cu)]
    if flip:
        b.flip_items(flip)
        footprints = {fp.reference_field.text.value: fp for fp in b.get_footprints()}
    moved = []
    hide = ("S", "H", "FID", "TP", "C", "R", "LED", "Q", "Y", "L", "D")
    for ref, fp in footprints.items():
        x, y, rot, side = want[ref]
        target = pf(x, y)
        # a part a legend names (SILK_B) shows its reference there, not again beside it
        show = ref not in NAMED and (ref.startswith("SW") or not ref.startswith(hide))
        if (fp.position != target or abs(fp.orientation.degrees - Angle.from_degrees(rot).normalize180().degrees) > 1e-6
                or fp.reference_field.visible != show):
            fp.orientation = Angle.from_degrees(rot)
            fp.position = target
            fp.reference_field.visible = show
            moved.append(fp)
    if moved:
        b.update_items(moved)
    print(f"place: {len(moved)} moved, {len(flip)} flipped")


def _placed_avoid():
    """From the placed board: the pads on the top copper, and everything a through via must miss."""
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    board = kicad_pcb.read(str(BOARD))

    def poly(points):
        return Polygon([G.playfield(x, y) for x, y in points]).buffer(0)
    top, through = [], []
    for part in board.parts:
        if part.ref.startswith("S") and part.ref[1:].isdigit():
            pass                       # a comb's lands are its own ground and its own net: art.py knows them
        for pad in part.pads:
            if not pad.polygon or len(pad.polygon) < 3:
                continue
            shape = poly(pad.polygon)
            if pad.side in ("top", "both"):
                top.append(shape)
            through.append(shape)
        if part.side == "bottom" and part.outline and len(part.outline) >= 3:
            through.append(poly(part.outline))
    return unary_union(top), unary_union(through)


def art(b):
    avoid_top, avoid_through = _placed_avoid()
    a = G.board_art(avoid_top=avoid_top, avoid_through=avoid_through)
    for k, val in a.report.items():
        print(f"  {k}: {val}")
    nets = {n.name: n for n in b.get_nets()}
    gnd = nets["GND"]
    old = [s for s in b.get_shapes() if s.layer in (BL.BL_F_Cu, BL.BL_F_Mask, BL.BL_F_SilkS)]
    if old:
        b.remove_items(old)
    old_vias = list(b.get_vias())      # art runs before route: every via on the board is an old stitching via
    if old_vias:
        b.remove_items(old_vias)
    items = []
    # each comb on its switch's nets: the footprint's lands carry the nets, the copper touches them
    pads = {fp.reference_field.text.value: fp for fp in b.get_footprints()}
    for s in G.sensors():
        sense_net = next(p.net for p in pads[s.ref].definition.pads if p.number == "1")
        for piece in G._holefree(s.sense):
            items.append(polygon_of(piece, BL.BL_F_Cu, sense_net))
        for piece in G._holefree(s.gnd):
            items.append(polygon_of(piece, BL.BL_F_Cu, gnd))
    for poly in a.copper_gnd:
        items.append(polygon_of(poly, BL.BL_F_Cu, gnd))
    for poly in a.copper_free:
        items.append(polygon_of(poly, BL.BL_F_Cu))
    for x, y, d in a.dots:
        c = BoardCircle()
        c.center, c.radius_point = pf(x, y), pf(x + d / 2, y)
        c.layer = BL.BL_F_Cu
        c.attributes.stroke.width = from_mm(0.0)
        c.attributes.fill.filled = True
        items.append(c)
    for poly in a.mask:
        items.append(polygon_of(poly, BL.BL_F_Mask))
    for x, y, d in a.silk:
        c = BoardCircle()
        c.center, c.radius_point = pf(x, y), pf(x + d / 2, y)
        c.layer = BL.BL_F_SilkS
        c.attributes.stroke.width = from_mm(0.0)
        c.attributes.fill.filled = True
        items.append(c)
    for x, y, d, dr in a.vias:
        via = Via()
        via.position, via.net = pf(x, y), gnd
        via.diameter, via.drill_diameter = from_mm(d), from_mm(dr)
        items.append(via)
    print(f"art: {len(a.copper_gnd)} GND shapes, {len(a.copper_free)} floating, {len(a.dots)} gold dots, "
          f"{len(a.mask)} mask openings, {len(a.silk)} silk dots, {len(a.vias)} stitching vias")
    b.create_items(items)


def route(b):
    """Every track and via of tmp/routes.json (routes.py plans them from the placed board)."""
    plan = json.loads((PROJECT / "tmp" / "routes.json").read_text())
    nets = {n.name: n for n in b.get_nets()}
    # the art's stitching vias are the only ones not the routing's size (0.84 / 0.9 mm): they stay
    old = [t for t in b.get_tracks()] + [v_ for v_ in b.get_vias() if abs(v_.diameter - from_mm(G.VIA_D)) < 1000]
    if old:
        b.remove_items(old)
    items = []
    for net, layer, width, pts in plan["tracks"]:
        for a, c in zip(pts, pts[1:]):
            if abs(a[0] - c[0]) < 1e-4 and abs(a[1] - c[1]) < 1e-4:
                continue
            t = Track()
            t.start, t.end, t.layer, t.width, t.net = v(*a), v(*c), LAYER[layer], from_mm(width), nets[net]
            items.append(t)
    for net, at in plan["vias"]:
        via = Via()
        via.position, via.net = v(*at), nets[net]
        via.diameter, via.drill_diameter = from_mm(G.VIA_D), from_mm(G.VIA_DRILL)
        items.append(via)
    b.create_items(items)
    print(f"route: {len(plan['tracks'])} polylines, {len(items)} items")


def _art_args():
    return (True, *_placed_avoid())


def _square(cx, cy, h):
    line = PolyLine()
    for x, y in ((cx - h, cy - h), (cx + h, cy - h), (cx + h, cy + h), (cx - h, cy + h)):
        line.append(PolyLineNode.from_point(v(x, y)))
    line.closed = True
    outline = PolygonWithHoles()
    outline.outline = line
    return outline


def zones(b):
    """Solid ground: In1.Cu whole, In2.Cu and B.Cu poured round the wiring. F.Cu stays the art's, but over U1 (behind
    the arch, under the backbox's wedge, where there is no art) the top copper is ground for the decoupling capacitors
    that stand there. Under U1 on In2.Cu, an island of 3V3 joins its supply vias."""
    nets = {n.name: n for n in b.get_nets()}
    old = [z for z in b.get_zones() if not z.is_rule_area()]
    if old:
        b.remove_items(old)
    new = []

    def zone(layer, net, name, outline, priority=0):
        z = Zone()
        z.layers = [layer]
        z.net = nets[net]
        z.name = name
        z.clearance = from_mm(0.2)
        z.min_thickness = from_mm(0.2)
        z.connection.zone_connection = ZoneConnectionStyle.ZCS_FULL  # small dense pads: spokes neck below 0.15 mm
        z.priority = priority
        z.outline = outline
        new.append(z)
    W, H = L.BOARD_W, L.BOARD_L
    k0, k1 = G.kicad(0.0, H), G.kicad(W, 0.0)
    whole = _square((k0[0] + k1[0]) / 2, (k0[1] + k1[1]) / 2, max(W, H))
    for layer, name in ((BL.BL_In1_Cu, "GND plane"), (BL.BL_In2_Cu, "In2 GND pour"), (BL.BL_B_Cu, "back GND pour")):
        zone(layer, "GND", name, whole)
    ux, uy = G.kicad(*G.MCU_AT)
    zone(BL.BL_In2_Cu, "+3V3", "U1 3V3 island", _square(ux, uy, G.U1_ISLAND), priority=1)
    zone(BL.BL_F_Cu, "GND", "U1 top ground", _square(ux, uy, 6.4))
    b.create_items(new)
    b.refill_zones()
    print(f"zones: {len(new)} made, refilled")


# (text, (x, y) playfield frame, height mm): the underside's legends a person reads, through the smoked panels
SILK_B = [
    ("SHORT CIRCUIT", (L.CENTER_X, 160.0), 3.0),
    ("SC-PF REV A  4 LAYERS  1.6 MM  ENIG", (L.CENTER_X, 163.4), 1.0),
    ("THE BALL IS THE SWITCH", (L.CENTER_X, 170.0), 1.0),
    ("USB-C PD 9V  U3", (64.0, 224.7), 1.0),
    ("5V BUCK  U5", (L.CENTER_X - 28.0, 230.0), 1.2),
    ("3V3 LDO", (31.5, 210.0), 1.0),
    ("SOUND  U8", (60.0, 208.5), 1.0),
    ("TILT  U9", (60.0, 199.8), 1.0),
    ("BOOTSEL  SW1", (96.0, 233.6), 1.0),
    ("RESET  SW2", (96.0, 209.6), 1.0),
    ("SWCLK SWDIO 3V3 GND", (93.25, 201.4), 0.8),
    ("FLIPPER L", (41.0, 96.4), 1.0),
    ("FLIPPER R", (L.mirror_x(41.0), 96.4), 1.0),
    ("BACKBOX", (49.5, 193.6), 1.0),
    ("SPEAKER", (60.0, 223.3), 1.0),
]


def silk(b):
    """The underside's legends (the top's silkscreen is the art)."""
    old = [t for t in b.get_text() if t.layer == BL.BL_B_SilkS]
    if old:
        b.remove_items(old)
    new = []
    for text, (x, y), h in SILK_B:
        item = BoardText()
        item.value = text
        item.layer = BL.BL_B_SilkS
        item.position = pf(x, y)
        item.attributes.size = Vector2.from_xy(from_mm(h), from_mm(h))
        item.attributes.stroke_width = from_mm(max(0.12, h * 0.15))
        item.attributes.mirrored = True
        new.append(item)
    b.create_items(new)
    print(f"silk: {len(new)} legends")


STAGES = {"setup": setup, "place": place, "art": art, "route": route, "zones": zones, "silk": silk}


def finish():
    """What the API does not reach, in the saved file as text: the title block and the stackup (black mask, ENIG)."""
    text = BOARD.read_text()
    if "(title_block" not in text:
        block = ('\t(title_block\n\t\t(title "SHORT CIRCUIT: the playfield")\n\t\t(date "2026-11-08")\n\t\t(rev "A")\n'
                 '\t\t(company "text-to-cad")\n\t\t(comment 1 "SC-PF REV A")\n\t)\n')
        text = text.replace('\t(paper "A4")\n', '\t(paper "A4")\n' + block, 1)
    if "(stackup" not in text:
        layer = lambda name, kind, thick=None, extra="": (
            f'\t\t\t(layer "{name}"\n\t\t\t\t(type "{kind}")\n'
            + (f"\t\t\t\t(thickness {thick})\n" if thick else "") + extra + "\t\t\t)\n")
        mask = '\t\t\t\t(color "Black")\n'
        silk_ = '\t\t\t\t(color "White")\n'
        fr4 = '\t\t\t\t(material "FR4")\n\t\t\t\t(epsilon_r 4.5)\n\t\t\t\t(loss_tangent 0.02)\n'
        stack = ("\t\t(stackup\n"
                 + layer("F.SilkS", "Top Silk Screen", extra=silk_)
                 + layer("F.Paste", "Top Solder Paste")
                 + layer("F.Mask", "Top Solder Mask", 0.01, mask)
                 + layer("F.Cu", "copper", 0.035)
                 + '\t\t\t(layer "dielectric 1"\n\t\t\t\t(type "prepreg")\n\t\t\t\t(thickness 0.2)\n' + fr4 + "\t\t\t)\n"
                 + layer("In1.Cu", "copper", 0.0175)
                 + '\t\t\t(layer "dielectric 2"\n\t\t\t\t(type "core")\n\t\t\t\t(thickness 1.065)\n' + fr4 + "\t\t\t)\n"
                 + layer("In2.Cu", "copper", 0.0175)
                 + '\t\t\t(layer "dielectric 3"\n\t\t\t\t(type "prepreg")\n\t\t\t\t(thickness 0.2)\n' + fr4 + "\t\t\t)\n"
                 + layer("B.Cu", "copper", 0.035)
                 + layer("B.Mask", "Bottom Solder Mask", 0.01, mask)
                 + layer("B.Paste", "Bottom Solder Paste")
                 + layer("B.SilkS", "Bottom Silk Screen", extra=silk_)
                 + '\t\t\t(copper_finish "ENIG")\n\t\t\t(dielectric_constraints no)\n\t\t)\n')
        text = text.replace("\t(setup\n", "\t(setup\n" + stack, 1)
    BOARD.write_text(text)


DRU = """(version 2)
# A comb's chevron fingers converge to 0.113 mm where they meet the spines (playfield.py's geometry; JLCPCB's
# limit is 0.09 mm on 4 layers); straight combs keep their 0.4 mm. Only on the top copper, only the combs.
(rule "comb fingers"
  (layer "F.Cu")
  (constraint clearance (min 0.1mm))
  (condition "A.hasNetclass('Sense') || B.hasNetclass('Sense')"))
# The SK6812MINI-E's stock land pattern sits 0.247 mm from its own cut-out; JLCPCB routes copper to 0.2 mm of an
# edge, so the LEDs alone get 0.2 mm.
(rule "LED cut-out"
  (constraint edge_clearance (min 0.2mm))
  (condition "A.memberOfFootprint('LED*')"))
# The RP2040's 0.4 mm pads: its own fan-out runs at 0.15 mm under the package
(rule "QFN fan-out"
  (constraint track_width (min 0.15mm))
  (condition "A.intersectsCourtyard('U1')"))
"""


def project_rules():
    """The netclasses, in the project file: JLCPCB's clearance everywhere, widths for each rail's current."""
    pro = PROJECT / "pinball.kicad_pro"
    data = json.loads(pro.read_text())
    ns = data["net_settings"]
    default = next(c for c in ns["classes"] if c["name"] == "Default")
    want = {"clearance": G.CLEARANCE, "track_width": G.SIGNAL, "via_diameter": G.VIA_D, "via_drill": G.VIA_DRILL,
            "diff_pair_width": G.SIGNAL, "diff_pair_gap": 0.2}
    default.update(want)
    classes = {c["name"]: c for c in ns["classes"]}
    for name, width in (("Coil", 0.8), ("Power5V", 0.6), ("Power3V3", 0.3), ("Sense", G.SIGNAL)):
        cls = {**default, "name": name, "track_width": width, "priority": 0}
        if name in classes:
            classes[name].update(cls)
        else:
            ns["classes"].append(cls)
    ns["netclass_patterns"] = [{"netclass": "Coil", "pattern": "+9V"}, {"netclass": "Coil", "pattern": "VBUS"},
                               {"netclass": "Coil", "pattern": "*COIL_?_DRAIN"}, {"netclass": "Coil", "pattern": "*BUCK_SW"},
                               {"netclass": "Power5V", "pattern": "+5V"},
                               {"netclass": "Power3V3", "pattern": "+3V3"}, {"netclass": "Power3V3", "pattern": "+1V1"},
                               {"netclass": "Sense", "pattern": "*SENSE_*"}]
    pro.write_text(json.dumps(data, indent=2) + "\n")
    (PROJECT / "pinball.kicad_dru").write_text(DRU)
    print("project rules written")


def main(stages):
    for stage in stages:
        if stage == "finish":
            finish()
            print("finish: title block and stackup written")
            continue
        with kicad_pcb.edit(str(BOARD)) as b:
            STAGES[stage](b)
        print(f"{stage}: saved {BOARD.name}")
        if stage == "setup":
            project_rules()


if __name__ == "__main__":
    names = sys.argv[1:] or ["all"]
    main(list(STAGES) + ["finish"] if names == ["all"] else names)
