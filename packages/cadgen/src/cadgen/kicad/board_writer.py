"""A :class:`~cadgen.kicad.design.Board` as a ``.kicad_pcb`` document.

The writer emits KiCad 10's board format (``version 20260206``) the way KiCad
writes it: footprints are copied from the library with their pads, graphics and
3D model references, placed and given their nets; the outline is ``Edge.Cuts``
graphics; copper is segments, arcs, vias and zones. Zones are written unfilled:
KiCad fills them when the build runs its checks, and the filled board is what
the build saves.

Frames. The board script works in millimetres with y up and its own origin.
KiCad's file is y down, on a page. :class:`Frame` maps one to the other and
puts the script's (0, 0) at the board's drill/place origin, so KiCad's STEP and
placement exports (run from that origin) come back in the script's own
coordinates.

A footprint in a board file stores its children in its own frame, but pad and
text ANGLES are absolute (the footprint's rotation is added in). A bottom-side
footprint is stored flipped top-to-bottom in its frame (y negated, layers
swapped front to back, pad angles negated, text angles ``180 - a`` and
mirrored), then rotated: exactly what KiCad's own flip leaves in a file.
"""

from __future__ import annotations

import copy
import math
from dataclasses import dataclass

from cadgen.kicad import sexpr
from cadgen.kicad.design import SCRIPT_FIELD, Board, Part, Pin, _natural, kicad_net_name, script_reference, unit_letter
from cadgen.kicad.ids import Ids
from cadgen.kicad.outline import outline_bounds, outline_segments, polygon_rings
from cadgen.kicad.sexpr import Sym

__all__ = ["BOARD_FORMAT_VERSION", "Frame", "board_document", "unconnected_net_name"]

BOARD_FORMAT_VERSION = 20260206
GENERATOR = "cadgen"
GENERATOR_VERSION = "10.0"
EDGE_WIDTH = 0.05

_PAGES = (("A4", 297.0, 210.0), ("A3", 420.0, 297.0), ("A2", 594.0, 420.0), ("A1", 841.0, 594.0), ("A0", 1189.0, 841.0))
_PAGE_MARGIN = 20.0


def _page_for(width: float, height: float) -> tuple[str, float, float]:
    """The smallest landscape ISO page holding ``width`` x ``height`` plus a margin."""
    for name, page_width, page_height in _PAGES:
        if width + 2 * _PAGE_MARGIN <= page_width and height + 2 * _PAGE_MARGIN <= page_height:
            return name, page_width, page_height
    return "User", math.ceil(width + 2 * _PAGE_MARGIN), math.ceil(height + 2 * _PAGE_MARGIN)


def _nm(value: float) -> float:
    rounded = round(float(value), 6)
    return 0.0 if rounded == 0 else rounded


@dataclass(frozen=True)
class Frame:
    """Board coordinates (mm, y up, script origin) to KiCad's (mm, y down, page)."""

    offset_x: float
    offset_y: float
    page: str
    page_width: float
    page_height: float

    @classmethod
    def for_outline(cls, outline) -> "Frame":
        min_x, min_y, max_x, max_y = outline_bounds(outline)
        page, width, height = _page_for(max_x - min_x, max_y - min_y)
        # The board's centre at the page's centre, on a 0.1 mm grid.
        offset_x = round(width / 2 - (min_x + max_x) / 2, 1)
        offset_y = round(height / 2 + (min_y + max_y) / 2, 1)
        return cls(offset_x=offset_x, offset_y=offset_y, page=page, page_width=width, page_height=height)

    def x(self, x: float) -> float:
        return _nm(x + self.offset_x)

    def y(self, y: float) -> float:
        return _nm(self.offset_y - y)

    def point(self, point: tuple[float, float]) -> tuple[float, float]:
        return self.x(point[0]), self.y(point[1])

    @property
    def origin(self) -> tuple[float, float]:
        return self.point((0.0, 0.0))


def unconnected_net_name(ref: str, pin_name: str, number: str, *, unit: str = "") -> str:
    """KiCad's name for the net of a pin connected to nothing (each gets its own).

    As KiCad derives it from the schematic: a named pin's net carries the
    reference with the pin's unit letter (``unit``, ``U1B``, on a symbol of
    several units), the name and the number; an unnamed pin's, the bare
    reference and the number; both escaped as KiCad escapes net names.
    """
    if pin_name and pin_name not in {"~", number}:
        return kicad_net_name(f"unconnected-({ref}{unit}-{pin_name}-Pad{number})")
    return kicad_net_name(f"unconnected-({ref}-Pad{number})")


def _open_net_name(part: Part, pin: Pin) -> str:
    """The net of a pin on no net. Of a stack of such pins (one point in the schematic), KiCad
    names the net after one: the least name, as it orders candidate drivers."""
    names = []
    for member in pin.stack:
        unit = ""
        if part.symbol.unit_count > 1:
            unit = unit_letter(next((p.unit for p in part.symbol.pins if p.number == member.number), 1) or 1)
        names.append(unconnected_net_name(part.ref, member.name, member.number, unit=unit))
    return min(names)


# --- layers ----------------------------------------------------------------------

_USER_LAYERS = (
    (9, "F.Adhes", "user", "F.Adhesive"),
    (11, "B.Adhes", "user", "B.Adhesive"),
    (13, "F.Paste", "user", None),
    (15, "B.Paste", "user", None),
    (5, "F.SilkS", "user", "F.Silkscreen"),
    (7, "B.SilkS", "user", "B.Silkscreen"),
    (1, "F.Mask", "user", None),
    (3, "B.Mask", "user", None),
    (17, "Dwgs.User", "user", "User.Drawings"),
    (19, "Cmts.User", "user", "User.Comments"),
    (21, "Eco1.User", "user", "User.Eco1"),
    (23, "Eco2.User", "user", "User.Eco2"),
    (25, "Edge.Cuts", "user", None),
    (27, "Margin", "user", None),
    (31, "F.CrtYd", "user", "F.Courtyard"),
    (29, "B.CrtYd", "user", "B.Courtyard"),
    (35, "F.Fab", "user", None),
    (33, "B.Fab", "user", None),
)


def _layers(board: Board) -> list:
    node: list = [Sym("layers")]
    copper = board.copper_layers
    ids = {"F.Cu": 0, "B.Cu": 2}
    for index in range(1, len(copper) - 1):
        ids[f"In{index}.Cu"] = 2 + 2 * index
    for name in copper:
        node.append([ids[name], name, Sym("signal")])
    for number, name, kind, user_name in _USER_LAYERS:
        entry = [number, name, Sym(kind)]
        if user_name:
            entry.append(user_name)
        node.append(entry)
    return node


def _stackup(board: Board) -> list:
    copper = board.copper_layers
    copper_thickness = 0.035
    mask = 0.01
    dielectrics = len(copper) - 1
    dielectric = _nm((board.thickness - copper_thickness * len(copper) - 2 * mask) / dielectrics)
    if dielectric <= 0:
        raise ValueError(f"a {board.layer_count}-layer board cannot be {board.thickness} mm thick")
    node: list = [
        Sym("stackup"),
        [Sym("layer"), "F.SilkS", [Sym("type"), "Top Silk Screen"]],
        [Sym("layer"), "F.Paste", [Sym("type"), "Top Solder Paste"]],
        [Sym("layer"), "F.Mask", [Sym("type"), "Top Solder Mask"], [Sym("thickness"), mask]],
    ]
    for index, name in enumerate(copper):
        node.append([Sym("layer"), name, [Sym("type"), "copper"], [Sym("thickness"), copper_thickness]])
        if index < dielectrics:
            kind = "core" if index % 2 == 0 else "prepreg"
            node.append(
                [
                    Sym("layer"),
                    f"dielectric {index + 1}",
                    [Sym("type"), kind],
                    [Sym("thickness"), dielectric],
                    [Sym("material"), "FR4"],
                    [Sym("epsilon_r"), 4.5],
                    [Sym("loss_tangent"), 0.02],
                ]
            )
    node.extend(
        [
            [Sym("layer"), "B.Mask", [Sym("type"), "Bottom Solder Mask"], [Sym("thickness"), mask]],
            [Sym("layer"), "B.Paste", [Sym("type"), "Bottom Solder Paste"]],
            [Sym("layer"), "B.SilkS", [Sym("type"), "Bottom Silk Screen"]],
            [Sym("copper_finish"), "None"],
            [Sym("dielectric_constraints"), Sym("no")],
        ]
    )
    return node


# --- footprints --------------------------------------------------------------------

_POINT_KEYS = ("start", "end", "mid", "center", "at", "offset")


def _flip_layer(name: str) -> str:
    if name.startswith("F."):
        return "B." + name[2:]
    if name.startswith("B."):
        return "F." + name[2:]
    return name


def _set_uuid(node: list, value: str) -> None:
    for index, child in enumerate(node):
        if isinstance(child, list) and child and child[0] == "uuid":
            node[index] = [Sym("uuid"), value]
            return
    node.append([Sym("uuid"), value])


def _toggle_mirror(node: list) -> None:
    effects = sexpr.find(node, "effects")
    if effects is None:
        return
    justify = sexpr.find(effects, "justify")
    if justify is None:
        effects.append([Sym("justify"), Sym("mirror")])
        return
    if any(item == "mirror" for item in justify[1:]):
        justify[:] = [item for item in justify if item != "mirror"]
        if len(justify) == 1:
            effects.remove(justify)
    else:
        justify.append(Sym("mirror"))


def _place_points(node: list, place) -> None:
    """Every point under ``node`` (a polygon's ``xy``, an arc's ``start``/``mid``/``end``), moved by ``place``."""
    for child in node[1:]:
        if not isinstance(child, list) or not child:
            continue
        if child[0] in ("xy", "start", "mid", "end") and len(child) >= 3 and isinstance(child[1], (int, float)):
            child[1], child[2] = place(float(child[1]), float(child[2]))
        else:
            _place_points(child, place)


def _mirror_points(node: list) -> None:
    """y -> -y for every coordinate in ``node`` and below (a footprint-frame flip)."""
    for child in node[1:]:
        if not isinstance(child, list) or not child:
            continue
        head = child[0]
        if head in _POINT_KEYS and len(child) >= 3 and isinstance(child[2], (int, float)):
            child[2] = _nm(-child[2])
        elif head == "xy" and len(child) >= 3:
            child[2] = _nm(-child[2])
        elif head == "rect_delta" and len(child) >= 3:
            child[2] = _nm(-child[2])
        if head not in {"xy"}:
            _mirror_points(child)


def _angle_of(node: list) -> float:
    at = sexpr.find(node, "at")
    if at is None or len(at) < 4 or not isinstance(at[3], (int, float)):
        return 0.0
    return float(at[3])


def _set_angle(node: list, angle: float) -> None:
    at = sexpr.find(node, "at")
    if at is None:
        return
    angle = _nm(angle % 360.0)
    if angle == 360.0:
        angle = 0.0
    del at[3:]
    if angle:
        at.append(angle)


_TEXT_HEADS = {"property", "fp_text"}


def _place_footprint(
    part: Part,
    *,
    frame: Frame,
    ids: Ids,
    board: Board,
    symbol_path: str,
    sheetfile: str,
    script_root=None,
) -> list:
    library = part.footprint
    placement = part._require_placement()
    bottom = placement.side == "bottom"
    tree = copy.deepcopy(library.tree)
    body = [item for item in tree[2:] if not (isinstance(item, list) and item and item[0] in {"version", "generator", "generator_version", "layer", "uuid", "at"})]
    at: list = [Sym("at"), frame.x(placement.x), frame.y(placement.y)]
    if placement.rotation:
        at.append(_nm(placement.rotation))
    node: list = [Sym("footprint"), part.footprint.lib_id, [Sym("layer"), "B.Cu" if bottom else "F.Cu"], [Sym("uuid"), ids(f"footprint:{part.ref}")], at]
    pad_counter = 0
    item_counter = 0
    properties_seen: set[str] = set()
    fields = part.document_fields(script_root)  # the symbol carries the same, Script included
    for item in body:
        if not isinstance(item, list):
            continue
        head = item[0]
        if head == "property":
            key = str(item[1])
            properties_seen.add(key)
            if key == "Reference":
                item[2] = part.ref
            elif key == "Value":
                item[2] = part.value
            elif key in {"Datasheet", "Description"}:
                item[2] = part.symbol.properties.get(key, "")
            elif key in fields:
                item[2] = fields[key]  # the symbol's say, as KiCad's update from the schematic sets it
        if head == "pad":
            _set_uuid(item, ids(f"footprint:{part.ref}:pad:{pad_counter}"))
            pad_counter += 1
            number = str(item[1])
            pin = part._pins.get(number)
            net_name = None
            if pin is not None:
                net = board._pin_nets.get(pin.key)
                if net is not None:
                    net_name = kicad_net_name(net.name)
                else:
                    net_name = _open_net_name(part, pin)
            # Net, then pin function and type, before the uuid, as KiCad orders them.
            item[:] = [entry for entry in item if not (isinstance(entry, list) and entry and entry[0] in {"net", "pinfunction", "pintype"})]
            uuid_index = next(i for i, entry in enumerate(item) if isinstance(entry, list) and entry and entry[0] == "uuid")
            extra: list = []
            if net_name is not None:
                extra.append([Sym("net"), net_name])
            if pin is not None:
                if pin.name and pin.name not in {"~", ""}:
                    extra.append([Sym("pinfunction"), pin.name])
                extra.append([Sym("pintype"), pin.electrical_type])
            item[uuid_index:uuid_index] = extra
            local_angle = _angle_of(item)
            if bottom:
                _mirror_points(item)
                layers = sexpr.find(item, "layers")
                if layers is not None:
                    layers[1:] = [_flip_layer(str(layer)) for layer in layers[1:]]
                local_angle = -local_angle
            _set_angle(item, local_angle + placement.rotation)
        elif head == "zone":
            # Unlike its pads and graphics, a footprint's zone (an antenna keepout, say) is stored
            # in the board's own coordinates once placed: move each corner as its pads move.
            _set_uuid(item, ids(f"footprint:{part.ref}:item:{item_counter}"))
            item_counter += 1
            _place_points(item, lambda x, y: frame.point(part._local_to_board(x, y)))
            if bottom:
                layer = sexpr.find(item, "layer")
                if layer is not None:
                    layer[1] = _flip_layer(str(layer[1]))
                layers = sexpr.find(item, "layers")
                if layers is not None:
                    layers[1:] = [_flip_layer(str(entry)) for entry in layers[1:]]
        elif head in _TEXT_HEADS or head.startswith("fp_") or head in {"dimension", "image", "group"}:
            _set_uuid(item, ids(f"footprint:{part.ref}:item:{item_counter}"))
            item_counter += 1
            if bottom:
                _mirror_points(item)
                layer = sexpr.find(item, "layer")
                if layer is not None:
                    layer[1] = _flip_layer(str(layer[1]))
                layers = sexpr.find(item, "layers")
                if layers is not None:
                    layers[1:] = [_flip_layer(str(entry)) for entry in layers[1:]]
            if head in _TEXT_HEADS:
                local_angle = _angle_of(item)
                if bottom:
                    local_angle = 180.0 - local_angle
                    _toggle_mirror(item)
                _set_angle(item, local_angle + placement.rotation)
        elif head == "attr":
            item = _attr(item[1:], part)
        node.append(item)
    # Fields the symbol carries that the footprint does not: the BOM reads them here, and
    # KiCad's parity check wants every one of the symbol's on its footprint.
    insert_at = max(
        (index for index, entry in enumerate(node) if isinstance(entry, list) and entry and entry[0] == "property"),
        default=len(node) - 1,
    ) + 1
    extra_properties = []
    for key, value in sorted(fields.items()):
        if key in properties_seen:
            continue
        extra_properties.append(
            [
                Sym("property"),
                key,
                value,
                [Sym("at"), 0, 0, *([_nm(placement.rotation)] if placement.rotation else [])],
                [Sym("layer"), "B.Fab" if bottom else "F.Fab"],
                [Sym("hide"), Sym("yes")],
                [Sym("uuid"), ids(f"footprint:{part.ref}:property:{key}")],
                [Sym("effects"), [Sym("font"), [Sym("size"), 1, 1], [Sym("thickness"), 0.15]]],
            ]
        )
    # The symbol's Datasheet and Description travel to the footprint (KiCad's
    # parity check compares them); a library footprint may lack either field.
    for key in ("Datasheet", "Description"):
        if key not in properties_seen:
            extra_properties.insert(
                0,
                [
                    Sym("property"),
                    key,
                    part.symbol.properties.get(key, ""),
                    [Sym("at"), 0, 0, *([_nm(placement.rotation)] if placement.rotation else [])],
                    [Sym("layer"), "B.Fab" if bottom else "F.Fab"],
                    [Sym("hide"), Sym("yes")],
                    [Sym("uuid"), ids(f"footprint:{part.ref}:property:{key}")],
                    [Sym("effects"), [Sym("font"), [Sym("size"), 1.27, 1.27], [Sym("thickness"), 0.15]]],
                ],
            )
    node[insert_at:insert_at] = extra_properties
    # Back-references to the schematic, after the fields, as KiCad places them.
    after_fields = max(
        (index for index, entry in enumerate(node) if isinstance(entry, list) and entry and entry[0] == "property"),
        default=len(node) - 1,
    ) + 1
    node[after_fields:after_fields] = [
        [Sym("path"), symbol_path],
        [Sym("sheetname"), "/"],
        [Sym("sheetfile"), sheetfile],
    ]
    if not any(isinstance(entry, list) and entry and entry[0] == "attr" for entry in node):
        attr = _attr([], part)
        if len(attr) > 1:
            node.append(attr)
    return node


# KiCad's order for footprint attributes, as it writes them.
_ATTR_ORDER = (
    "smd",
    "through_hole",
    "board_only",
    "exclude_from_pos_files",
    "exclude_from_bom",
    "allow_missing_courtyard",
    "dnp",
    "allow_soldermask_bridges",
)


def _attr(flags: list, part: Part) -> list:
    """A footprint's ``attr``, with what the schematic owns set as KiCad's update from it sets it.

    "Exclude from BOM" and "do not populate" are the symbol's; a library
    footprint's own say (a test point's ``exclude_from_bom``) gives way to its
    symbol's, or KiCad's parity check reports the two disagreeing.
    """
    kept = {str(flag) for flag in flags if str(flag) not in ("exclude_from_bom", "dnp")}
    if not part.symbol.in_bom:
        kept.add("exclude_from_bom")
    if part.dnp:
        kept.add("dnp")
    known = [flag for flag in _ATTR_ORDER if flag in kept]
    return [Sym("attr"), *(Sym(flag) for flag in known + sorted(kept - set(_ATTR_ORDER)))]


def _hole_footprint(index: int, ref: str, hole, *, frame: Frame, ids: Ids, script_root=None) -> list:
    size = hole.diameter
    script = script_reference(hole.script, script_root)
    node = [
        Sym("footprint"),
        f"cadgen:Hole_{size:g}mm",
        [Sym("layer"), "F.Cu"],
        [Sym("uuid"), ids(f"hole:{index}")],
        [Sym("at"), frame.x(hole.at[0]), frame.y(hole.at[1])],
        [Sym("property"), "Reference", ref, [Sym("at"), 0, -(size / 2 + 1.2)], [Sym("layer"), "F.Fab"], [Sym("hide"), Sym("yes")],
         [Sym("uuid"), ids(f"hole:{index}:reference")], [Sym("effects"), [Sym("font"), [Sym("size"), 1, 1], [Sym("thickness"), 0.15]]]],
        [Sym("property"), "Value", f"Hole {size:g}mm", [Sym("at"), 0, size / 2 + 1.2], [Sym("layer"), "F.Fab"], [Sym("hide"), Sym("yes")],
         [Sym("uuid"), ids(f"hole:{index}:value")], [Sym("effects"), [Sym("font"), [Sym("size"), 1, 1], [Sym("thickness"), 0.15]]]],
        [Sym("attr"), Sym("board_only"), Sym("exclude_from_pos_files"), Sym("exclude_from_bom"), Sym("allow_missing_courtyard")],
        [Sym("pad"), "", Sym("np_thru_hole"), Sym("circle"), [Sym("at"), 0, 0], [Sym("size"), size, size], [Sym("drill"), size],
         [Sym("layers"), "*.Cu", "*.Mask"], [Sym("uuid"), ids(f"hole:{index}:pad")]],
    ]
    if script is not None:
        # The line that made the hole, as a part's: a hole has no symbol, so nothing compares it.
        node.insert(7, [Sym("property"), SCRIPT_FIELD, script, [Sym("at"), 0, 0], [Sym("layer"), "F.Fab"], [Sym("hide"), Sym("yes")],
                        [Sym("uuid"), ids(f"hole:{index}:script")],
                        [Sym("effects"), [Sym("font"), [Sym("size"), 1, 1], [Sym("thickness"), 0.15]]]])
    return node


# --- board items -----------------------------------------------------------------


def _stroke(width: float) -> list:
    return [Sym("stroke"), [Sym("width"), width], [Sym("type"), Sym("default")]]


def _edge_items(board: Board, *, frame: Frame, ids: Ids) -> list[list]:
    items: list[list] = []
    for index, segment in enumerate(outline_segments(board.outline, what="the board outline")):
        uuid = [Sym("uuid"), ids(f"edge:{index}")]
        layer = [Sym("layer"), "Edge.Cuts"]
        if segment.kind == "line":
            start, end = (frame.point(point) for point in segment.points)
            items.append([Sym("gr_line"), [Sym("start"), *start], [Sym("end"), *end], _stroke(EDGE_WIDTH), layer, uuid])
        elif segment.kind == "arc":
            start, mid, end = (frame.point(point) for point in segment.points)
            items.append([Sym("gr_arc"), [Sym("start"), *start], [Sym("mid"), *mid], [Sym("end"), *end], _stroke(EDGE_WIDTH), layer, uuid])
        else:
            center = frame.point(segment.points[0])
            end = (center[0] + segment.radius, center[1])
            items.append(
                [Sym("gr_circle"), [Sym("center"), *center], [Sym("end"), _nm(end[0]), end[1]], _stroke(EDGE_WIDTH),
                 [Sym("fill"), Sym("no")], layer, uuid]
            )
    return items


def _pts(points, *, frame: Frame) -> list:
    return [Sym("pts"), *([Sym("xy"), *frame.point(point)] for point in points)]


def _zone_rings(board: Board, zone, *, frame: Frame) -> list[list[tuple[float, float]]]:
    if zone.shape is not None:
        return polygon_rings(zone.shape, what="a zone shape")
    min_x, min_y, max_x, max_y = outline_bounds(board.outline)
    margin = 0.5
    return [[(min_x - margin, max_y + margin), (max_x + margin, max_y + margin), (max_x + margin, min_y - margin), (min_x - margin, min_y - margin)]]


def _zone(board: Board, zone, index: int, *, frame: Frame, ids: Ids) -> list[list]:
    rules = board.rules
    items: list[list] = []
    for ring_index, ring in enumerate(_zone_rings(board, zone, frame=frame)):
        layers = [Sym("layer"), zone.layers[0]] if len(zone.layers) == 1 else [Sym("layers"), *zone.layers]
        node: list = [Sym("zone")]
        if zone.keepout is None:
            node.append([Sym("net"), kicad_net_name(zone.net.name)])
        node.extend([layers, [Sym("uuid"), ids(f"zone:{index}:{ring_index}")], [Sym("hatch"), Sym("edge"), 0.5]])
        if zone.priority:
            node.append([Sym("priority"), zone.priority])
        if zone.keepout is not None:
            node.append([Sym("connect_pads"), [Sym("clearance"), 0]])
            node.append([Sym("min_thickness"), 0.25])
            node.append(
                [Sym("keepout"), *([Sym(name), Sym("not_allowed" if forbidden else "allowed")] for name, forbidden in zone.keepout.items())]
            )
            node.append([Sym("fill"), [Sym("thermal_gap"), 0.5], [Sym("thermal_bridge_width"), 0.5]])
        else:
            clearance = zone.clearance if zone.clearance is not None else board.netclass_of(zone.net).clearance
            connect: list = [Sym("connect_pads")]
            if zone.pads == "solid":
                connect.append(Sym("yes"))
            elif zone.pads == "none":
                connect.append(Sym("no"))
            connect.append([Sym("clearance"), clearance])
            node.append(connect)
            node.append([Sym("min_thickness"), zone.min_thickness if zone.min_thickness is not None else max(rules.min_track_width, 0.2)])
            node.append([Sym("filled_areas_thickness"), Sym("no")])
            node.append(
                [
                    Sym("fill"),
                    [Sym("thermal_gap"), zone.thermal_gap if zone.thermal_gap is not None else 0.5],
                    [Sym("thermal_bridge_width"), zone.thermal_width if zone.thermal_width is not None else 0.5],
                ]
            )
        node.append([Sym("polygon"), _pts(ring, frame=frame)])
        items.append(node)
    return items


def _text(board: Board, text, index: int, *, frame: Frame, ids: Ids) -> list:
    thickness = text.thickness if text.thickness is not None else max(round(text.size * 0.15, 3), board.rules.min_text_thickness)
    at: list = [Sym("at"), *frame.point(text.at)]
    if text.rotation:
        at.append(_nm(text.rotation))
    effects: list = [Sym("effects"), [Sym("font"), [Sym("size"), text.size, text.size], [Sym("thickness"), thickness]]]
    if text.layer.startswith("B."):
        effects.append([Sym("justify"), Sym("mirror")])
    return [Sym("gr_text"), text.text, at, [Sym("layer"), text.layer], [Sym("uuid"), ids(f"text:{index}")], effects]


def _hole_refs(board: Board) -> list[str]:
    taken = {part.ref for part in board.parts}
    refs: list[str] = []
    number = 1
    for _hole in board.holes:
        while f"H{number}" in taken:
            number += 1
        refs.append(f"H{number}")
        taken.add(f"H{number}")
    return refs


def board_document(board: Board, *, project: str, frame: Frame, symbol_paths: dict[str, str], script_root=None) -> list:
    """The ``.kicad_pcb`` tree. ``symbol_paths`` maps a reference to its symbol's sheet path;
    ``script_root`` is the model script's folder, which ``Script`` fields are relative to."""
    ids = Ids(project)
    origin = frame.origin
    title_block: list = [Sym("title_block"), [Sym("title"), board.title or project]]
    document: list = [
        Sym("kicad_pcb"),
        [Sym("version"), BOARD_FORMAT_VERSION],
        [Sym("generator"), GENERATOR],
        [Sym("generator_version"), GENERATOR_VERSION],
        [Sym("general"), [Sym("thickness"), board.thickness], [Sym("legacy_teardrops"), Sym("no")]],
        [Sym("paper"), frame.page] if frame.page != "User" else [Sym("paper"), "User", frame.page_width, frame.page_height],
        title_block,
        _layers(board),
        [
            Sym("setup"),
            _stackup(board),
            [Sym("pad_to_mask_clearance"), 0],
            [Sym("allow_soldermask_bridges_in_footprints"), Sym("no")],
            [Sym("tenting"), [Sym("front"), Sym("yes")], [Sym("back"), Sym("yes")]],
            [Sym("aux_axis_origin"), *origin],
            [Sym("grid_origin"), *origin],
        ],
    ]
    sheetfile = f"{project}.kicad_sch"
    for part in sorted(board.parts, key=lambda part: _natural(part.ref)):
        document.append(
            _place_footprint(
                part, frame=frame, ids=ids, board=board, symbol_path=symbol_paths[part.ref], sheetfile=sheetfile,
                script_root=script_root,
            )
        )
    for index, (hole, ref) in enumerate(zip(board.holes, _hole_refs(board))):
        document.append(_hole_footprint(index, ref, hole, frame=frame, ids=ids, script_root=script_root))
    document.extend(_edge_items(board, frame=frame, ids=ids))
    for index, text in enumerate(board.texts):
        document.append(_text(board, text, index, frame=frame, ids=ids))
    for index, track in enumerate(board.tracks):
        width = track.width if track.width is not None else board.netclass_of(track.net).track_width
        common = [[Sym("width"), width], [Sym("layer"), track.layer], [Sym("net"), kicad_net_name(track.net.name)], [Sym("uuid"), ids(f"track:{index}")]]
        if track.mid is None:
            document.append([Sym("segment"), [Sym("start"), *frame.point(track.start)], [Sym("end"), *frame.point(track.end)], *common])
        else:
            document.append(
                [Sym("arc"), [Sym("start"), *frame.point(track.start)], [Sym("mid"), *frame.point(track.mid)], [Sym("end"), *frame.point(track.end)], *common]
            )
    for index, via in enumerate(board.vias):
        netclass = board.netclass_of(via.net)
        document.append(
            [
                Sym("via"),
                [Sym("at"), *frame.point(via.at)],
                [Sym("size"), via.diameter if via.diameter is not None else netclass.via_diameter],
                [Sym("drill"), via.drill if via.drill is not None else netclass.via_drill],
                [Sym("layers"), *via.layers],
                [Sym("net"), kicad_net_name(via.net.name)],
                [Sym("uuid"), ids(f"via:{index}")],
            ]
        )
    for index, zone in enumerate(board.zones):
        document.extend(_zone(board, zone, index, frame=frame, ids=ids))
    for raw in board.raw_items:
        document.append(sexpr.parse(raw))
    document.append([Sym("embedded_fonts"), Sym("no")])
    return document
