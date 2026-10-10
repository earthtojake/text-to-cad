"""The DSN routing problem of a KiCad board: its layers, outline, footprints, nets, rules and obstacles."""

from __future__ import annotations

import fnmatch
import json
import math
import re
from dataclasses import dataclass, field
from typing import Iterable

from cadgen.kicad import sexpr
from cadgen.kicad.design import DesignError
from cadgen.kicad.geometry import board_origin
from cadgen.kicad.sexpr import Sym
from cadgen.kicad.specctra.shapes import (
    GRAPHIC,
    DsnFrame,
    Point,
    arc_edge,
    bezier,
    blob,
    board_outline,
    circle_edge,
    convex_pieces,
    curve_points,
    curve_step,
    hull,
    loop_points,
    node_xy,
    placed,
    pts_loop,
    rounded_rect,
    stadium,
    strokes,
)

#: Tenths of a micrometre: Freerouting's grid, and the unit of the session's integers.
RESOLUTION = 10
#: Millimetres every clearance is written above the board's, for the session's rounding.
MARGIN = 0.001

_DEFAULT_CLASS = "kicad_default"
# KiCad's defaults for a project that does not say (Board Setup > Constraints).
_KICAD_RULES = {"min_clearance": 0.0, "min_copper_edge_clearance": 0.5, "min_hole_clearance": 0.25}
_KICAD_NETCLASS = {"track_width": 0.2, "clearance": 0.2, "via_diameter": 0.6, "via_drill": 0.3}
_SAFE_PIN = re.compile(r"[A-Za-z0-9]+")
_SAFE_REF = re.compile(r"[A-Za-z][A-Za-z0-9_]*")


def _num(value: float) -> str:
    """A DSN number: micrometres to the nanometre, never in exponent form."""
    text = f"{value:.3f}".rstrip("0").rstrip(".")
    return "0" if text in ("", "-0") else text


def _sanitize(text: str, limit: int = 32) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", str(text)).strip("_")[:limit]


def _shown(net: str) -> str:
    """A net's name as KiCad shows it (its files escape ``/`` as ``{slash}``)."""
    return net.replace("{slash}", "/")


# --- rules and net classes ---------------------------------------------------------------------


@dataclass(frozen=True)
class _NetClass:
    name: str
    track_width: float
    clearance: float
    via_diameter: float
    via_drill: float
    priority: int


def _project(project: str | dict) -> dict:
    if isinstance(project, dict):
        return project
    try:
        return json.loads(project)
    except (TypeError, ValueError) as error:
        raise DesignError(f"the board's .kicad_pro is not KiCad's project JSON ({error})") from None


def _rules(project: dict) -> dict[str, float]:
    found = (((project.get("board") or {}).get("design_settings") or {}).get("rules")) or {}
    return {key: float(found.get(key, default) or 0.0) for key, default in _KICAD_RULES.items()}


def _netclasses(project: dict) -> tuple[dict[str, _NetClass], list[tuple[str, str]], dict[str, list[str]]]:
    settings = project.get("net_settings") or {}
    raw = {str(entry.get("name")): entry for entry in settings.get("classes") or [] if entry.get("name")}
    default_raw = raw.get("Default", {})
    default_values = {key: float(default_raw.get(key) or value) for key, value in _KICAD_NETCLASS.items()}
    classes: dict[str, _NetClass] = {}
    for name, entry in raw.items():
        values = {key: float(entry[key]) if entry.get(key) is not None else default_values[key] for key in _KICAD_NETCLASS}
        priority = entry.get("priority")
        classes[name] = _NetClass(name=name, priority=int(priority) if priority is not None else 2**31 - 1, **values)
    if "Default" not in classes:
        classes["Default"] = _NetClass(name="Default", priority=2**31 - 1, **default_values)
    patterns = [
        (str(entry.get("pattern")), str(entry.get("netclass")))
        for entry in settings.get("netclass_patterns") or []
        if entry.get("pattern") is not None and entry.get("netclass") is not None
    ]
    assigned: dict[str, list[str]] = {}
    for net, names in (settings.get("netclass_assignments") or {}).items():
        assigned[str(net)] = [str(names)] if isinstance(names, str) else [str(name) for name in names or []]
    return classes, patterns, assigned


def _class_of(net: str, classes: dict[str, _NetClass], patterns, assigned) -> _NetClass:
    names = list(assigned.get(net, []))
    names += [netclass for pattern, netclass in patterns if pattern == net or fnmatch.fnmatchcase(net, pattern)]
    found = [classes[name] for name in names if name in classes]
    if not found:
        return classes["Default"]
    return min(found, key=lambda netclass: (netclass.priority, netclass.name))


# --- footprints ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Pad:
    """One pad seen from the top, in its footprint's frame (KiCad mm, y down)."""

    number: str
    kind: str
    x: float
    y: float
    angle: float  # relative to the footprint, degrees
    copper: tuple[str, ...]
    shape: tuple  # hashable: the copper outline in the pad's frame
    drill: tuple[float, float] | None
    hole: tuple[float, float]  # the drill's offset from the pad's position (front view)
    net: str | None


def _flip_layer(name: str) -> str:
    if name.startswith("F."):
        return "B." + name[2:]
    if name.startswith("B."):
        return "F." + name[2:]
    return name


def _copper(layers: Iterable[str], board_copper: tuple[str, ...], *, flipped: bool) -> tuple[str, ...]:
    names: set[str] = set()
    for layer in layers:
        layer = str(layer)
        if layer in ("*.Cu", "F&B.Cu"):
            names.update(board_copper if layer == "*.Cu" else ("F.Cu", "B.Cu"))
        elif layer.endswith(".Cu"):
            names.add(_flip_layer(layer) if flipped else layer)
    return tuple(name for name in board_copper if name in names)


def _mirror(node):
    """``node`` with every y in it negated (a footprint's bottom-side flip, undone)."""
    if not isinstance(node, list):
        return node
    out = [node[0]]
    head = sexpr.head(node)
    if head in {"start", "end", "mid", "center", "xy", "at", "offset"} and len(node) >= 3 and isinstance(node[2], (int, float)):
        return [node[0], node[1], -node[2], *node[3:]]
    for child in node[1:]:
        out.append(_mirror(child))
    return out


def _freeze(node):
    if isinstance(node, list):
        return tuple(_freeze(child) for child in node)
    if isinstance(node, float):
        return round(node, 9)
    return node if not isinstance(node, Sym) else str(node)


def _read_pad(pad: list, *, theta: float, bottom: bool, board_copper: tuple[str, ...]) -> _Pad:
    if bottom:
        pad = _mirror(pad)
    at = sexpr.find(pad, "at")
    x, y = node_xy(at, (0.0, 0.0))
    stored_angle = float(at[3]) if at is not None and len(at) > 3 else 0.0
    angle = (theta - stored_angle) if bottom else (stored_angle - theta)
    angle = round(angle % 360.0, 6) % 360.0
    size = sexpr.find(pad, "size")
    width = float(size[1]) if size is not None and len(size) > 1 else 0.0
    height = float(size[2]) if size is not None and len(size) > 2 else width
    drill_node = sexpr.find(pad, "drill")
    drill = None
    hole = (0.0, 0.0)
    if drill_node is not None:
        numbers = [float(item) for item in drill_node[1:] if isinstance(item, (int, float))]
        if numbers:
            drill = (numbers[0], numbers[1] if len(numbers) > 1 else numbers[0])
        hole = node_xy(sexpr.find(drill_node, "offset"), (0.0, 0.0))
    layers = sexpr.find(pad, "layers")
    copper = _copper(layers[1:] if layers is not None else (), board_copper, flipped=bottom)
    shape_name = str(pad[3]) if len(pad) > 3 else "circle"
    details = []
    for key in ("roundrect_rratio", "rect_delta", "options", "primitives"):
        child = sexpr.find(pad, key)
        if child is not None:
            details.append(_freeze(child))
    net = sexpr.value(pad, "net")
    if isinstance(net, int):
        # A board written before KiCad 10 numbers its nets: (net 3 "GND").
        net_node = sexpr.find(pad, "net")
        net = net_node[2] if net_node is not None and len(net_node) > 2 else None
    return _Pad(
        number=str(pad[1]),
        kind=str(pad[2]),
        x=x,
        y=y,
        angle=angle,
        copper=copper,
        shape=(shape_name, round(width, 9), round(height, 9), round(hole[0], 9), round(hole[1], 9), tuple(details)),
        drill=drill,
        hole=hole,
        net=str(net) if net not in (None, "") else None,
    )


def _reference(footprint: list) -> str:
    for prop in sexpr.find_all(footprint, "property"):
        if len(prop) > 2 and prop[1] == "Reference":
            return str(prop[2])
    for text in sexpr.find_all(footprint, "fp_text"):
        if len(text) > 2 and text[1] == "reference":
            return str(text[2])
    return ""


# Pad outlines, in the pad's own frame: DSN micrometres, y up, centred on the pad's position.


def _custom_outline(pad_shape: tuple, width: float, height: float, cx: float, cy: float) -> list[Point]:
    """A custom pad's convex hull: its anchor and every primitive, strokes included."""
    details = {item[0]: item for item in pad_shape[5]}
    anchor = "circle"
    options = details.get("options")
    if options is not None:
        for child in options[1:]:
            if isinstance(child, tuple) and child and child[0] == "anchor" and len(child) > 1:
                anchor = str(child[1])
    points: list[Point] = blob(cx, cy, width / 2) if anchor == "circle" else [
        (cx - width / 2, cy - height / 2), (cx + width / 2, cy - height / 2),
        (cx + width / 2, cy + height / 2), (cx - width / 2, cy + height / 2),
    ]
    primitives = details.get("primitives")
    for primitive in (primitives[1:] if primitives is not None else ()):
        if not isinstance(primitive, tuple) or not primitive:
            continue
        values = {child[0]: child for child in primitive[1:] if isinstance(child, tuple) and child}
        stroke = float(values["width"][1]) * 1000.0 / 2 if "width" in values and len(values["width"]) > 1 else 0.0

        def local(key: str) -> Point:
            node = values[key]
            return cx + float(node[1]) * 1000.0, cy - float(node[2]) * 1000.0

        kind = str(primitive[0])
        if kind in ("gr_poly", "gr_line", "gr_rect", "gr_curve", "gr_arc", "gr_circle", "gr_bbox"):
            corners: list[Point] = []
            if kind == "gr_poly" and "pts" in values:
                corners = [(cx + float(xy[1]) * 1000.0, cy - float(xy[2]) * 1000.0) for xy in values["pts"][1:] if xy and xy[0] == "xy"]
            elif kind in ("gr_line",) and {"start", "end"} <= set(values):
                corners = [local("start"), local("end")]
            elif kind in ("gr_rect", "gr_bbox") and {"start", "end"} <= set(values):
                (x1, y1), (x2, y2) = local("start"), local("end")
                corners = [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]
            elif kind == "gr_curve" and "pts" in values:
                corners = [(cx + float(xy[1]) * 1000.0, cy - float(xy[2]) * 1000.0) for xy in values["pts"][1:] if xy and xy[0] == "xy"]
            elif kind == "gr_arc" and {"start", "mid", "end"} <= set(values):
                edge = arc_edge(local("start"), local("mid"), local("end"))
                corners = curve_points(edge, outside=True) + [edge.end]
            elif kind == "gr_circle" and {"center", "end"} <= set(values):
                centre, rim = local("center"), local("end")
                corners = blob(centre[0], centre[1], math.hypot(rim[0] - centre[0], rim[1] - centre[1]) + stroke)
                stroke = 0.0
            for x, y in corners:
                points.extend(blob(x, y, stroke))
    return hull(points)


def _pad_outline(pad: _Pad) -> tuple:
    """The pad's copper as one DSN shape spec in its own frame: ``(kind, numbers...)``."""
    name, width, height, ox, oy, _details = pad.shape
    w, h = width * 1000.0, height * 1000.0
    cx, cy = ox * 1000.0, -oy * 1000.0
    details = {item[0]: item for item in pad.shape[5]}
    if name == "circle" or (name == "oval" and abs(w - h) < 1e-9):
        return ("circle", max(w, h), cx, cy)
    if name == "rect":
        return ("rect", cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)
    if name == "oval":
        return ("polygon", tuple(stadium(w, h, cx, cy)))
    if name in ("roundrect", "chamfered_rect"):
        ratio = float(details["roundrect_rratio"][1]) if "roundrect_rratio" in details else 0.0
        radius = ratio * min(w, h)
        if radius <= 0:
            return ("rect", cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)
        return ("polygon", tuple(rounded_rect(w, h, radius, cx, cy)))
    if name == "trapezoid":
        delta = details.get("rect_delta")
        dx = abs(float(delta[1])) * 1000.0 if delta is not None and len(delta) > 1 else 0.0
        dy = abs(float(delta[2])) * 1000.0 if delta is not None and len(delta) > 2 else 0.0
        # The trapezoid's bounding box holds it whichever way its delta leans.
        return ("rect", cx - (w + dy) / 2, cy - (h + dx) / 2, cx + (w + dy) / 2, cy + (h + dx) / 2)
    if name == "custom":
        return ("polygon", tuple(_custom_outline(pad.shape, w, h, cx, cy)))
    raise DesignError(f"pad {pad.number} has a shape KiCad 10 does not write: {name!r}")


def _shape_node(spec: tuple, layer: str) -> list:
    kind = spec[0]
    if kind == "circle":
        return ["circle", layer, _num(spec[1]), _num(spec[2]), _num(spec[3])]
    if kind == "rect":
        return ["rect", layer, *(_num(value) for value in spec[1:])]
    return ["polygon", layer, "0", *(_num(value) for point in spec[1] for value in point)]


# --- the DSN document ---------------------------------------------------------------------------------


@dataclass(frozen=True)
class ViaKind:
    diameter: float
    drill: float
    layers: tuple[str, str]


@dataclass(frozen=True)
class Dsn:
    """A board's routing problem, and the way from its aliases back to the board."""

    text: str
    frame: DsnFrame
    layers: tuple[str, ...]
    nets: dict[str, str]  # DSN net alias -> KiCad net name
    widths: dict[str, float]  # DSN net alias -> its class's track width (mm)
    vias: dict[str, ViaKind]  # DSN padstack name -> the via it is
    routed: tuple[str, ...]  # KiCad nets the router was given, sorted


class _Q(str):
    """A DSN string written in quotes."""


def _atom(item) -> str:
    if isinstance(item, _Q):
        if '"' in item or "\n" in item:
            raise DesignError(f"{str(item)!r} cannot be written into a Specctra file (it holds a quote or a newline)")
        return f'"{item}"'
    return str(item)


def _render(node: list, depth: int, out: list[str]) -> None:
    indent = "  " * depth
    if not any(isinstance(item, list) for item in node):
        line = indent + "(" + " ".join(_atom(item) for item in node) + ")"
        if len(line) <= 120:
            out.append(line)
            return
        # Long runs of numbers wrap; Freerouting reads whitespace (never a tab) between tokens.
        words = [_atom(item) for item in node]
        head, rest = words[:3], words[3:]
        out.append(indent + "(" + " ".join(head))
        for start in range(0, len(rest), 10):
            out.append(indent + "  " + " ".join(rest[start:start + 10]))
        out[-1] += ")"
        return
    first = next(index for index, item in enumerate(node) if isinstance(item, list))
    out.append(indent + "(" + " ".join(_atom(item) for item in node[:first]))
    for item in node[first:]:
        if isinstance(item, list):
            _render(item, depth + 1, out)
        else:
            out.append(indent + "  " + _atom(item))
    out.append(indent + ")")


def _via_name(index: int, kind: ViaKind, board_copper: tuple[str, ...]) -> str:
    first, last = board_copper.index(kind.layers[0]), board_copper.index(kind.layers[1])
    # KiCad's spelling (outer:drill in µm) is how Freerouting reads a via's drill from its name.
    return f"V{index}_{round(kind.diameter * 1000)}:{round(kind.drill * 1000)}_um_L{first}_{last}"


@dataclass
class _Footprints:
    """The board's footprints as Freerouting reads them: each an image seen from the top, its pads
    padstacks; where each image is placed; and the pins on each net."""

    images: list[list] = field(default_factory=list)
    padstacks: list[list] = field(default_factory=list)
    placements: dict[str, list[list]] = field(default_factory=dict)
    net_pins: dict[str, list[str]] = field(default_factory=dict)


def _footprints(pcb_tree: list, frame: DsnFrame, board_copper: tuple[str, ...], hole_growth: float) -> _Footprints:
    """Every footprint of ``pcb_tree`` as an image, a padstack per distinct pad (an unplated hole's
    grown by ``hole_growth`` micrometres) and a placement; images and padstacks shared alike."""
    found = _Footprints()
    stacks: dict[tuple, str] = {}
    images: dict[tuple, str] = {}
    refs_seen: set[str] = set()

    def padstack(pad: _Pad, outline: tuple, layers: tuple[str, ...], drilled: bool) -> str:
        key = (outline, layers, drilled, pad.drill if drilled else None, pad.kind == "np_thru_hole")
        stack = stacks.get(key)
        if stack is None:
            number = len(stacks) + 1
            if pad.kind == "np_thru_hole":
                stack = f"H{number}"
            elif drilled:
                outer = min(pad.shape[1], pad.shape[2])
                stack = f"T{number}_{round(outer * 1000)}:{round(min(pad.drill) * 1000)}_um"
            else:
                stack = f"S{number}"
            stacks[key] = stack
            found.padstacks.append(["padstack", stack, *(["shape", _shape_node(outline, layer)] for layer in layers), ["attach", "off"]])
        return stack

    for index, footprint in enumerate(item for item in pcb_tree[1:] if sexpr.head(item) == "footprint"):
        at = sexpr.find(footprint, "at")
        theta = float(at[3]) if at is not None and len(at) > 3 else 0.0
        bottom = sexpr.value(footprint, "layer") == "B.Cu"
        pads = [
            _read_pad(pad, theta=theta, bottom=bottom, board_copper=board_copper)
            for pad in sexpr.find_all(footprint, "pad")
        ]
        numbers = [pad.number for pad in pads if pad.copper and pad.kind != "np_thru_hole"]
        pins: list[list] = []
        pin_of: list[tuple[str, _Pad]] = []
        for pad_index, pad in enumerate(pads):
            px, py = pad.x * 1000.0, -pad.y * 1000.0
            if pad.kind == "np_thru_hole":
                if pad.drill is None:
                    continue
                # An unplated hole is a pin of no net: an obstacle on every layer.
                outline, pad_layers, drilled, pin_name = _hole_outline(pad, hole_growth), board_copper, False, f"@{pad_index + 1}"
            elif pad.copper:
                pin_name = pad.number if _SAFE_PIN.fullmatch(pad.number) and numbers.count(pad.number) == 1 else f"@{pad_index + 1}"
                outline, pad_layers, drilled = _pad_outline(pad), pad.copper, pad.drill is not None and pad.kind == "thru_hole"
            else:
                continue
            stack = padstack(pad, outline, pad_layers, drilled)
            pin: list = ["pin", stack, pin_name, _num(px), _num(py)]
            if pad.angle:
                pin.append(["rotate", _num(pad.angle)])
            pins.append(pin)
            pin_of.append((pin_name, pad))
        if not pins:
            continue
        lib_id = str(footprint[1]) if len(footprint) > 1 and not isinstance(footprint[1], list) else "footprint"
        image_key = (lib_id, _freeze(pins))
        image = images.get(image_key)
        if image is None:
            image = f"I{len(images) + 1}_{_sanitize(lib_id.split(':')[-1])}"
            images[image_key] = image
            found.images.append(["image", image, *pins])
        ref = _reference(footprint)
        component = ref if _SAFE_REF.fullmatch(ref) and ref not in refs_seen else f"@{index + 1}"
        refs_seen.add(component)
        x, y = frame.to_dsn(*node_xy(at, (0.0, 0.0)))
        rotation = round(((theta + 180.0) if bottom else theta) % 360.0, 6) % 360.0
        found.placements.setdefault(image, []).append(
            ["place", component, _num(x), _num(y), "back" if bottom else "front", _num(rotation), ["lock_type", "position"]]
        )
        for pin_name, pad in pin_of:
            if pad.net is not None and pad.kind != "np_thru_hole":
                found.net_pins.setdefault(pad.net, []).append(f"{component}-{pin_name}")
    return found


def board_dsn(
    pcb_tree: list,
    project: str | dict,
    *,
    skip: Iterable[str] = (),
    layers: Iterable[str] | None = None,
    name: str = "board",
    host_version: str = "",
) -> Dsn:
    """The DSN routing problem of the board ``pcb_tree`` (a ``.kicad_pcb`` tree, KiCad 10).

    ``project`` is the board's ``.kicad_pro`` (text or parsed): its net classes
    and constraints are the routing rules. ``skip`` names nets the router must
    leave alone (a ground carried by a pour): their pads and copper stay in the
    problem as obstacles. A name that is no net of the board is refused.
    ``layers`` names the copper layers tracks may run on (all by default); the
    rest are written as Freerouting's power layers, which it never routes and
    vias pass through.
    """
    if sexpr.head(pcb_tree) != "kicad_pcb":
        raise DesignError("board_dsn takes a KiCad board tree, (kicad_pcb ...)")
    settings = _project(project)
    rules = _rules(settings)
    classes, patterns, assigned = _netclasses(settings)
    frame = DsnFrame(*board_origin(pcb_tree))
    board_copper = _copper_layers(pcb_tree)
    default = classes["Default"]
    hole_growth = max(0.0, rules["min_hole_clearance"] - max(default.clearance, rules["min_clearance"])) * 1000.0
    footprints = _footprints(pcb_tree, frame, board_copper, hole_growth)
    image_nodes, padstack_nodes, placements, net_pins = footprints.images, footprints.padstacks, footprints.placements, footprints.net_pins

    # The nets the router is given: two pads or more, and not skipped.
    skipped = set()
    for net in skip:
        if net not in net_pins:
            listing = ", ".join(sorted(_shown(name) for name, pins in net_pins.items() if len(pins) > 1)) or "none"
            raise DesignError(
                f"autoroute(skip=...) names {_shown(net)!r}, which is no net with pads on this board "
                f"(its routable nets are {listing})"
            )
        skipped.add(net)
    routed = sorted(net for net, pins in net_pins.items() if len(pins) > 1 and net not in skipped)
    aliases = {net: f"N{index + 1}_{_sanitize(net)}".rstrip("_") for index, net in enumerate(routed)}
    net_class = {net: _class_of(net, classes, patterns, assigned) for net in routed}

    # Vias: one kind per net class the router may drop, and every kind the board already has.
    via_kinds: dict[ViaKind, str] = {}

    def via_named(kind: ViaKind) -> str:
        if kind not in via_kinds:
            via_kinds[kind] = _via_name(len(via_kinds) + 1, kind, board_copper)
        return via_kinds[kind]

    through = (board_copper[0], board_copper[-1])
    used_classes = sorted({netclass.name: netclass for netclass in net_class.values()}.values(), key=lambda c: (c.name != "Default", c.name))
    class_via = {netclass.name: via_named(ViaKind(netclass.via_diameter, netclass.via_drill, through)) for netclass in used_classes}
    if "Default" not in class_via:
        class_via["Default"] = via_named(ViaKind(default.via_diameter, default.via_drill, through))

    # The board's own copper, fixed.
    wiring: list[list] = []
    for item in pcb_tree[1:]:
        head = sexpr.head(item)
        if head in ("segment", "arc", "via"):
            wiring.extend(_fixed_wiring(item, head, frame, board_copper, aliases, via_named))

    def clearance_of(netclass: _NetClass) -> float:
        return max(netclass.clearance, rules["min_clearance"]) + MARGIN

    routing = set(board_copper) if layers is None else set(layers)
    unknown = sorted(routing - set(board_copper))
    if unknown or not routing:
        raise DesignError(
            f"autoroute(layers=...) takes this board's copper layers ({', '.join(board_copper)}); got {', '.join(unknown) or 'none'}"
        )
    structure: list = ["structure"]
    for index, layer in enumerate(board_copper):
        kind = "signal" if layer in routing else "power"
        structure.append(["layer", layer, ["type", kind], ["property", ["index", str(index)]]])
    boundaries, holes = board_outline(pcb_tree, frame)
    for boundary in boundaries:
        points = boundary + boundary[:1]
        structure.append(["boundary", ["path", "pcb", "0", *(_num(value) for point in points for value in point)], ["clearance_class", "edge"]])
    track_zones, via_zones = _zone_obstacles(pcb_tree, frame, board_copper)
    obstacles = [(hole, board_copper, True) for hole in holes]
    obstacles += [(points, zone_layers, False) for points, zone_layers in track_zones]
    obstacles += [(points, drawn_layers, False) for points, drawn_layers in _copper_obstacles(pcb_tree, frame, board_copper)]
    _add_obstacles(obstacles, image_nodes, padstack_nodes, placements)
    for index, (points, zone_layers) in enumerate(via_zones):
        targets = ["signal"] if set(zone_layers) == set(board_copper) else list(zone_layers)
        for layer in targets:
            structure.append(["via_keepout", f"zone{index + 1}", ["polygon", layer, "0", *(_num(value) for point in points for value in point)]])
    structure.append(["via", *[via_kinds[kind] for kind in via_kinds if via_kinds[kind] in class_via.values()]])
    structure.append(
        [
            "rule",
            ["width", _num(default.track_width * 1000.0)],
            ["clearance", _num(clearance_of(default) * 1000.0)],
            ["clearance", _num((rules["min_copper_edge_clearance"] + MARGIN) * 1000.0), ["type", "default_edge"]],
        ]
    )
    structure.append(["control", ["via_at_smd", "off"]])

    library: list = ["library", *image_nodes, *padstack_nodes]
    for kind, via in via_kinds.items():
        library.append(
            ["padstack", via, *(["shape", ["circle", layer, _num(kind.diameter * 1000.0), "0", "0"]]
                               for layer in board_copper[board_copper.index(kind.layers[0]):board_copper.index(kind.layers[1]) + 1]), ["attach", "off"]]
        )

    network: list = ["network"]
    for net in routed:
        network.append(["net", aliases[net], ["pins", *net_pins[net]]])
    for number, netclass in enumerate(used_classes):
        members = [aliases[net] for net in routed if net_class[net] is netclass]
        class_name = _DEFAULT_CLASS if netclass.name == "Default" else f"C{number}{_sanitize(netclass.name).replace('_', '')}"
        network.append(
            [
                "class",
                class_name,
                *members,
                ["circuit", ["use_via", class_via[netclass.name]]],
                ["rule", ["width", _num(netclass.track_width * 1000.0)], ["clearance", _num(clearance_of(netclass) * 1000.0)]],
            ]
        )

    document: list = [
        "pcb",
        _Q(f"{name}.dsn"),
        ["parser", ["string_quote", '"'], ["space_in_quoted_tokens", "on"], ["host_cad", "cadgen"], ["host_version", _Q(host_version or "cadgen")]],
        ["resolution", "um", str(RESOLUTION)],
        ["unit", "um"],
        structure,
        ["placement", *(["component", image, *places] for image, places in placements.items())],
        library,
        network,
        ["wiring", *wiring],
    ]
    out: list[str] = []
    _render(document, 0, out)
    text = "\n".join(out) + "\n"
    return Dsn(
        text=text,
        frame=frame,
        layers=board_copper,
        nets={alias: net for net, alias in aliases.items()},
        widths={aliases[net]: net_class[net].track_width for net in routed},
        vias={name: kind for kind, name in via_kinds.items()},
        routed=tuple(routed),
    )


def _copper_layers(tree: list) -> tuple[str, ...]:
    layers = sexpr.find(tree, "layers")
    names = [
        str(entry[1])
        for entry in (layers[1:] if layers is not None else [])
        if isinstance(entry, list) and len(entry) >= 2 and str(entry[1]).endswith(".Cu")
    ]
    inner = sorted((name for name in names if name.startswith("In")), key=lambda name: int(re.sub(r"\D", "", name) or 0))
    ordered = (["F.Cu"] if "F.Cu" in names else []) + inner + (["B.Cu"] if "B.Cu" in names else [])
    if len(ordered) < 2:
        raise DesignError("the board has fewer than two copper layers to route on")
    return tuple(ordered)


def _hole_outline(pad: _Pad, growth: float) -> tuple:
    """An unplated hole as a pad outline in its own frame, grown so copper keeps the hole clearance.

    A pad wider than its drill has a copper ring of no net: the outline holds
    the ring too.
    """
    dx, dy = (value * 1000.0 for value in pad.drill)
    if pad.copper:
        dx, dy = max(dx, pad.shape[1] * 1000.0), max(dy, pad.shape[2] * 1000.0)
    cx, cy = pad.hole[0] * 1000.0, -pad.hole[1] * 1000.0
    if abs(dx - dy) < 1e-9:
        return ("circle", dx + 2 * growth, cx, cy)
    return ("polygon", tuple(stadium(dx + 2 * growth, dy + 2 * growth, cx, cy)))


def _zone_layers(zone: list, board_copper: tuple[str, ...]) -> tuple[str, ...]:
    layers = sexpr.find(zone, "layers")
    names = [str(name) for name in layers[1:]] if layers is not None else [str(sexpr.value(zone, "layer", ""))]
    return _copper(names, board_copper, flipped=False)


def _zone_obstacles(tree: list, frame: DsnFrame, board_copper: tuple[str, ...]):
    """Rule areas that forbid tracks, and those that forbid only vias: ``(points, layers)`` each.

    A footprint's rule areas count too (KiCad stores a footprint's zones in
    board coordinates). A zone's later polygons are cutouts of its first,
    which an obstacle may cover.
    """
    zones = [item for item in tree[1:] if sexpr.head(item) == "zone"]
    for footprint in (item for item in tree[1:] if sexpr.head(item) == "footprint"):
        zones.extend(sexpr.find_all(footprint, "zone"))
    tracks_out: list[tuple[list[Point], tuple[str, ...]]] = []
    vias_out: list[tuple[list[Point], tuple[str, ...]]] = []
    for zone in zones:
        keepout = sexpr.find(zone, "keepout")
        if keepout is None:
            continue
        rules = {str(child[0]): str(child[1]) for child in keepout[1:] if isinstance(child, list) and len(child) > 1}
        tracks, vias = rules.get("tracks") == "not_allowed", rules.get("vias") == "not_allowed"
        layers = _zone_layers(zone, board_copper)
        if not (tracks or vias) or not layers:
            continue
        polygon = sexpr.find(zone, "polygon")
        pts = sexpr.find(polygon, "pts") if polygon is not None else None
        loop = pts_loop(pts, lambda point: frame.to_dsn(*point)) if pts is not None else []
        if len(loop) < 2:
            continue
        (tracks_out if tracks else vias_out).append((loop_points(loop, keep_inside=False), layers))
    return tracks_out, vias_out


def _stroke_radius(node: list) -> float:
    """Half a graphic's stroke width, in micrometres."""
    stroke = sexpr.find(node, "stroke")
    width = sexpr.value(stroke, "width") if stroke is not None else sexpr.value(node, "width")
    return float(width or 0.0) * 1000.0 / 2


def _filled(node: list) -> bool:
    fill = sexpr.find(node, "fill")
    if fill is None or len(fill) < 2:
        return False
    value = fill[1]
    if isinstance(value, list):  # KiCad 6: (fill (type solid))
        value = sexpr.value(fill, "type", "none")
    return str(value) in ("yes", "solid")


def _graphic_regions(node: list, convert) -> list[list[Point]]:
    """The copper of one gr_/fp_ graphic as regions that hold it (DSN micrometres)."""
    kind = str(node[0])[3:]
    radius = _stroke_radius(node)
    filled = _filled(node)
    if kind == "line":
        return strokes([convert(node_xy(sexpr.find(node, "start"))), convert(node_xy(sexpr.find(node, "end")))], radius, closed=False)
    if kind in ("arc", "circle"):
        if kind == "arc":
            edge = arc_edge(*(convert(node_xy(sexpr.find(node, key))) for key in ("start", "mid", "end")))
        else:
            center = convert(node_xy(sexpr.find(node, "center")))
            rim = convert(node_xy(sexpr.find(node, "end")))
            edge = circle_edge(center, math.hypot(rim[0] - center[0], rim[1] - center[1]))
        if edge.center is None:
            return strokes([edge.start, edge.end], radius, closed=False)
        if kind == "circle" and filled:
            return [curve_points(circle_edge(edge.center, edge.radius + radius), outside=True)]
        count = max(1, math.ceil(abs(edge.sweep) / curve_step(edge.radius)))
        sagitta = edge.radius * (1 - math.cos(abs(edge.sweep) / count / 2))
        points = edge.sample(count)
        return strokes(points[:-1] if kind == "circle" else points, radius + sagitta, closed=kind == "circle")
    if kind == "rect":
        (x1, y1), (x2, y2) = node_xy(sexpr.find(node, "start")), node_xy(sexpr.find(node, "end"))
        corners = [convert(point) for point in ((x1, y1), (x2, y1), (x2, y2), (x1, y2))]
        return ([corners] if filled else []) + strokes(corners, radius, closed=True)
    if kind == "poly":
        pts = sexpr.find(node, "pts")
        loop = pts_loop(pts, convert) if pts is not None else []
        if len(loop) < 2:
            return []
        points = loop_points(loop, keep_inside=False)
        return ([points] if filled else []) + strokes(points, radius, closed=True)
    pts = sexpr.find(node, "pts")
    points = [convert(node_xy(xy)) for xy in sexpr.find_all(pts, "xy")] if pts is not None else []
    if len(points) != 4:
        return []
    curve = [edge.start for edge in bezier(points)] + [points[-1]]
    return strokes(curve, radius, closed=False)


def _hidden(node: list) -> bool:
    hide = sexpr.find(node, "hide")
    if hide is not None:
        return len(hide) < 2 or hide[1] == "yes"
    effects = sexpr.find(node, "effects")
    return any(item == "hide" for item in node[1:]) or (effects is not None and any(item == "hide" for item in effects[1:]))


def _text_region(node: list, place, frame: DsnFrame) -> list[Point] | None:
    """A box that holds a copper text's strokes, estimated from its font, never smaller.

    KiCad's stroke font advances about a glyph width per character and stands a
    little over its height: the box allows 1.25 widths a character and 1.7
    heights a line, plus the stroke.
    """
    index = 1 if sexpr.head(node) == "gr_text" else 2  # (gr_text "T" ...), (fp_text reference "R1" ...)
    text = str(node[index]) if len(node) > index and not isinstance(node[index], list) else ""
    if not text.strip() or _hidden(node):
        return None
    at = sexpr.find(node, "at")
    anchor = place(node_xy(at, (0.0, 0.0)))
    angle = float(at[3]) if at is not None and len(at) > 3 and isinstance(at[3], (int, float)) else 0.0
    effects = sexpr.find(node, "effects")
    font = sexpr.find(effects, "font") if effects is not None else None
    size = sexpr.find(font, "size") if font is not None else None
    height = float(size[1]) if size is not None and len(size) > 1 else 1.0
    width = float(size[2]) if size is not None and len(size) > 2 else height
    thickness = float(sexpr.value(font, "thickness", 0.15 * height) if font is not None else 0.15 * height)
    lines = text.split("\n")
    length = max(len(line) for line in lines) * width * 1.25 + thickness
    tall = len(lines) * height * 1.7 + thickness
    justify = [str(item) for item in (sexpr.find(effects, "justify") or [])[1:]] if effects is not None else []
    xs = (0.0, length) if "left" in justify else (-length, 0.0) if "right" in justify else (-length / 2, length / 2)
    if "mirror" in justify:
        xs = (-xs[1], -xs[0])
    ys = (0.0, tall) if "top" in justify else (-tall, 0.0) if "bottom" in justify else (-tall / 2, tall / 2)
    corners = []
    for x, y in ((xs[0], ys[0]), (xs[1], ys[0]), (xs[1], ys[1]), (xs[0], ys[1])):
        dx, dy = placed((0.0, 0.0), angle)((x, y))
        corners.append(frame.to_dsn(anchor[0] + dx, anchor[1] + dy))
    return corners


def _box(points: list[Point]) -> tuple[float, float, float, float]:
    xs, ys = [point[0] for point in points], [point[1] for point in points]
    return min(xs), min(ys), max(xs), max(ys)


def _overlaps(a: tuple, b: tuple) -> bool:
    return a[0] <= b[2] and b[0] <= a[2] and a[1] <= b[3] and b[1] <= a[3]


def _copper_obstacles(tree: list, frame: DsnFrame, board_copper: tuple[str, ...]) -> list[tuple[list[Point], tuple[str, ...]]]:
    """Copper that is no pad, track or pour -- graphics and text on a copper layer -- as ``(points, layers)``.

    A footprint's copper graphic that touches one of its pads (a net tie, a
    solder jumper's bridge, an antenna's feed) is that pad's copper, and is
    left to KiCad's check rather than walled off from its own net. A board
    graphic on a net is that net's copper, likewise.
    """
    board = lambda point: point  # noqa: E731
    regions: list[tuple[str, list[Point]]] = []

    def take(node: list, place, pads: list[tuple] | None) -> None:
        layer = str(sexpr.value(node, "layer", ""))
        if layer not in board_copper:
            return
        head = sexpr.head(node)
        if head in ("gr_text", "fp_text", "property"):
            region = _text_region(node, place, frame)
            found = [region] if region is not None else []
        else:
            if head.startswith("gr_") and sexpr.value(node, "net") not in (None, "", 0):
                return
            found = [region for region in _graphic_regions(node, lambda point: frame.to_dsn(*place(point))) if len(region) >= 3]
        if pads is not None and any(_overlaps(_box(region), pad) for region in found for pad in pads):
            return
        regions.extend((layer, region) for region in found)

    for item in tree[1:]:
        head = sexpr.head(item)
        if head == "gr_text" or (head is not None and head.startswith("gr_") and head[3:] in GRAPHIC):
            take(item, board, None)
        elif head == "footprint":
            at = sexpr.find(item, "at")
            theta = float(at[3]) if at is not None and len(at) > 3 else 0.0
            place = placed(node_xy(at, (0.0, 0.0)), theta)
            pads = []
            for pad in sexpr.find_all(item, "pad"):
                size = sexpr.find(pad, "size")
                reach = math.hypot(float(size[1]), float(size[2]) if len(size) > 2 else float(size[1])) * 500.0 if size is not None else 0.0
                cx, cy = frame.to_dsn(*place(node_xy(sexpr.find(pad, "at"), (0.0, 0.0))))
                pads.append((cx - reach, cy - reach, cx + reach, cy + reach))
            for child in item[1:]:
                child_head = sexpr.head(child)
                if child_head in ("fp_text", "property") or (child_head is not None and child_head.startswith("fp_") and child_head[3:] in GRAPHIC):
                    take(child, place, pads)
    return [(region, (layer,)) for layer, region in regions]


# Every obstacle to tracks is a pin of no net on a locked part of its own. Freerouting
# 2.4's maze search keeps a keepout's bare clearance while its trace insertion asks a
# little more (ClearanceMatrix.clearance_safety_margin), so a route that hugs a keepout
# is found and then refused; around a pin both agree.
_OBSTACLES = "I0_obstacles"


def _add_obstacles(obstacles, image_nodes: list[list], padstack_nodes: list[list], placements: dict[str, list[list]]) -> None:
    """``(points, layers, edge)`` obstacles as pins of no net on one locked part at the origin.

    An ``edge`` obstacle (a hole in the outline) keeps the edge clearance;
    the rest the board's.
    """
    pins: list[list] = []
    infos: list[list] = []
    for points, layers, edge in obstacles:
        for piece in convex_pieces(points):
            number = len(pins) + 1
            stack = f"K{number}"
            coordinates = [_num(value) for point in piece for value in point]
            padstack_nodes.append(["padstack", stack, *(["shape", ["polygon", layer, "0", *coordinates]] for layer in layers), ["attach", "off"]])
            pins.append(["pin", stack, str(number), "0", "0"])
            if edge:
                infos.append(["pin", str(number), ["clearance_class", "edge"]])
    if pins:
        image_nodes.append(["image", _OBSTACLES, *pins])
        placements[_OBSTACLES] = [["place", "@obstacles", "0", "0", "front", "0", ["lock_type", "position"], *infos]]


def _fixed_wiring(item: list, head: str, frame: DsnFrame, board_copper, aliases: dict[str, str], via_named) -> list[list]:
    net = sexpr.value(item, "net")
    if isinstance(net, int):
        node = sexpr.find(item, "net")
        net = node[2] if node is not None and len(node) > 2 else None
    alias = aliases.get(str(net)) if net not in (None, "") else None
    tail: list = ([["net", alias]] if alias is not None else []) + [["type", "fix"]]
    if head == "via":
        size, drill = sexpr.value(item, "size"), sexpr.value(item, "drill")
        layers = sexpr.find(item, "layers")
        pair = tuple(str(name) for name in (layers[1:3] if layers is not None else ()))
        if len(pair) != 2 or any(name not in board_copper for name in pair):
            pair = (board_copper[0], board_copper[-1])
        if board_copper.index(pair[0]) > board_copper.index(pair[1]):
            pair = (pair[1], pair[0])
        if size is None or drill is None:
            return []
        name = via_named(ViaKind(float(size), float(drill), pair))
        x, y = frame.to_dsn(*node_xy(sexpr.find(item, "at")))
        return [["via", name, _num(x), _num(y), *tail]]
    layer = str(sexpr.value(item, "layer", ""))
    if layer not in board_copper:
        return []
    width = float(sexpr.value(item, "width", 0.0)) * 1000.0
    start = frame.to_dsn(*node_xy(sexpr.find(item, "start")))
    end = frame.to_dsn(*node_xy(sexpr.find(item, "end")))
    if head == "segment":
        if start == end:
            return []
        points = [start, end]
    else:
        edge = arc_edge(start, frame.to_dsn(*node_xy(sexpr.find(item, "mid"))), end)
        if edge.center is None:
            points = [start, end]
        else:
            count = max(1, math.ceil(abs(edge.sweep) / curve_step(edge.radius)))
            points = edge.sample(count)
            # The arc bulges past its chords by up to the sagitta: widen the polyline to cover it.
            width += 2 * edge.radius * (1 - math.cos(abs(edge.sweep) / count / 2)) + 2 * MARGIN * 1000.0
    return [["wire", ["path", layer, _num(width), *(_num(value) for point in points for value in point)], *tail]]
