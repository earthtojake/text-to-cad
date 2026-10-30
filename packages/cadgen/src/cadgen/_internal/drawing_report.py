"""What a drawing leaves unstated, read off the part and checked against what its
sheets state, and the general notes a part's own geometry makes true.

Part of :mod:`cadgen.eng_drawing`; nothing here imports the kernel or ezdxf at
module scope.
"""

from __future__ import annotations

import math
import re
from collections.abc import Hashable
from dataclasses import dataclass, field

from cadgen._internal.drawing_annotation import _feature_text, _looks_into, hole_callout_text
from cadgen._internal.drawing_base import _fmt, _shown, _where
from cadgen._internal.drawing_features import Slot


@dataclass
class _Facts:
    """What a drawing's sheets state, gathered as they render, for the report of
    what they leave unstated: a record per part drawn (keyed by its shape), one
    per parts list (keyed by the list), and one per sheet, for its stage."""

    parts: dict = field(default_factory=dict)
    lists: dict = field(default_factory=dict)
    sheets: list = field(default_factory=list)

    def of_list(self, parts) -> dict:
        """The record of one parts list: the items its tables list and its balloons key."""
        return self.lists.setdefault(id(parts), {"parts": parts, "listed": set(), "ballooned": set()})


def _merge_facts(into: _Facts, more: _Facts) -> None:
    """Fold one sheet's facts into the drawing's: a part shown on two sheets is
    stated by both."""
    into.sheets.extend(more.sheets)
    for mine, theirs in ((into.parts, more.parts), (into.lists, more.lists)):
        for key, record in theirs.items():
            if key not in mine:
                mine[key] = record
                continue
            for name, value in record.items():
                if isinstance(value, set):
                    mine[key][name] |= value
                elif isinstance(value, list):
                    mine[key][name].extend(value)


def _member_key(feature) -> tuple:
    """One hole or slot, by what it is and where it opens."""
    return (feature.signature(), tuple(round(c, 4) for c in feature.mouth))


def _feature_key(feature) -> tuple:
    """Holes or slots one callout covers: the same kind, opening the same way. A
    plain through hole or slot reads the same from either end; a blind or
    opened-out one made from the other face is a different callout, in the other
    view."""
    from cadgen._internal.drawing_features import _canonical

    plain = feature.thru and not any(getattr(feature, name, None)
                                     for name in ("cbore", "csk", "far_cbore", "far_csk"))
    direction = _canonical(feature.axis, (0.0, 0.0, 0.0))[0] if plain else feature.axis
    return (feature.signature(), tuple(round(c, 4) for c in direction))


def _whose(record: dict, records: list) -> str:
    """On a drawing of several parts, the sheet a report line is about."""
    return f"sheet {record['sheet'][0]} ({record['sheet'][1]}): " if len(records) > 1 else ""


def _unstated(facts: _Facts) -> list[str]:
    """What the drawing leaves out that a shop needs to make the part.

    Read off the part, not guessed at: every kind of hole it has, its overall
    size along each axis, and every turned diameter, each checked against what
    the sheets call out or measure. A drawing is allowed to be unfinished; it
    is not allowed to look finished when it is not, so each line names the call
    that states the missing fact.
    """
    from cadgen._internal.drawing_features import revolved, turned_diameters

    lines: list[str] = []
    records = list(facts.parts.values())
    for record in records:
        shape, views = record["shape"], record["views"]
        # On a drawing of several parts, each line says whose sheet it is about.
        whose = _whose(record, records)
        kinds: dict[tuple, list] = {}
        # An assembly's holes and diameters are its parts', stated on their sheets.
        features = [] if record.get("assembly") else [*_found(record, "holes"), *_found(record, "slots")]
        for feature in features:
            kinds.setdefault(_feature_key(feature), []).append(feature)
        for key, members in kinds.items():
            # Each one, not each kind: a detail's callout covers what its circle
            # holds, and the identical holes outside it are still unstated.
            members = [m for m in members if _member_key(m) not in record["called"]]
            if not members:
                continue
            feature = members[0]
            is_slot = isinstance(feature, Slot)
            text = _feature_text(feature, len(members))
            where = next((name for name, look in views if _looks_into(feature, look)), None)
            verb = "slot" if is_slot else "hole"
            fix = (f"{where}.{verb}({_where(feature.mouth)}) states it, or {where}.holes() calls out every hole "
                   f"and slot the {where} view looks down." if where else
                   f"No view on the drawing looks into it; add the view that looks down the {verb}.")
            lines.append(f"incomplete: {whose}{text} is not called out. {fix}")
        size = shape.bounding_box().size
        turned = [] if record.get("assembly") else turned_diameters(shape)
        whole = None if record.get("assembly") else revolved(shape, bores=True)
        # A stated diameter of the part's largest turned surface states its width
        # across that axis too: a shaft's ⌀30 is its size in Y and in Z, and a
        # cone's widest circle is a spring seat's.
        across = [d for d in [*turned, *([whole.diameter] if whole else [])]
                  if any(abs(v - d) <= 0.01 for v in record["values"])]
        for axis, extent in enumerate((size.X, size.Y, size.Z)):
            if any(a == axis and abs(v - extent) <= 0.01 for a, v in record["axes"]):
                continue
            if any(abs(d - extent) <= 0.01 for d in across):
                continue
            where = next((name for name, look in views if abs(look[axis]) < 1e-9), None)
            if any(a == axis and abs(v - extent) <= 0.01 for a, v in record.get("referenced", ())):
                if _fixed(record, axis):
                    continue
                lines.append(f"incomplete: {whose}the overall size along {'XYZ'[axis]} ({_fmt(extent)}) is given "
                             "only as a reference dimension, and no other dimension fixes it: a reference asks "
                             "nothing. Dimension it as a requirement, or the sizes that add up to it.")
                continue
            fix = f"{where}.overall() states it." if where else "No view on the drawing shows that direction."
            lines.append(f"incomplete: {whose}the overall size along {'XYZ'[axis]} ({_fmt(extent)}) is not "
                         f"dimensioned. {fix}")
        for diameter in turned:
            if any(abs(v - diameter) <= 0.01 for v in record["values"]):
                continue
            lines.append(
                f"incomplete: {whose}the turned diameter ⌀{_fmt(diameter)} is not dimensioned. Dimension it across "
                f"its profile with text=\"%%c<>\", or diameter(..., size={_fmt(diameter)}) where it is seen as a "
                "circle."
            )
    for record in records:
        if record.get("assembly"):
            continue
        whose = _whose(record, records)
        lines.extend(_unstated_edges(record, whose))
        lines.extend(_unlocated(record, whose))
        lines.extend(_unplaced_faces(record, whose))
        lines.extend(_unstated_turns(record, whose))
    for entry in facts.lists.values():
        parts, listed, keyed = entry["parts"], entry["listed"], entry["ballooned"]
        if not listed:
            lines.append("incomplete: balloons key a parts list that no sheet draws; sheet.parts_list(parts) draws "
                         "it above the title block.")
            continue
        missing = [n for n in range(1, len(parts) + 1) if n not in listed]
        if missing:
            lines.append(f"incomplete: the parts list leaves out item{'s' if len(missing) > 1 else ''} "
                         f"{', '.join(map(str, missing))}; draw the rest with parts_list(parts, first=...) on a "
                         "further sheet.")
        for a, b in parts.twins:
            lines.append(f"note: items {a} and {b} ({parts[a].description or 'unnamed'} and "
                         f"{parts[b].description or 'unnamed'}) are the same shape under different names; "
                         f"parts.merge({a}, {b}) lists them as one part, if they are one.")
        for item in parts:
            # An item the model does not hold (an adhesive) has nothing to balloon.
            if item.number in listed and item.number not in keyed and item.shape is not None:
                lines.append(
                    f"incomplete: item {item.number} ({item.description or 'unnamed'}) has no balloon: no ballooned "
                    "view shows any of it unhidden. balloons() on a view from a side where it shows keys it."
                )
    for record in facts.sheets:
        lines.extend(_unstated_for_stage(record, _whose(record, facts.sheets)))
    return lines


#: Coordinates this close (model mm) are one place, for tying features together.
_PLACE = 2
#: More unstated slopes than this on one part are one line, not one each.
_MANY_SLOPES = 3


def _anchors(record: dict) -> dict[int, set]:
    """Where locations may start, along each model axis: the part's extremes, the
    faces made datums, the centre lines stated symmetric, the centres of datum
    features of size, and the axis of a part whose outline is turned (a centred
    bore on a flange is located by the flange's diameter), or that is turned
    whole (a coned spring perch's bore by the perch)."""
    from cadgen._internal.drawing_features import revolved, turned_surfaces

    shape = record["shape"]
    box = shape.bounding_box()
    lo, hi = (box.min.X, box.min.Y, box.min.Z), (box.max.X, box.max.Y, box.max.Z)
    anchors = {axis: {round(lo[axis], _PLACE), round(hi[axis], _PLACE)} for axis in range(3)}
    for axis in record["symmetric"]:
        anchors[axis].add(round((lo[axis] + hi[axis]) / 2, _PLACE))
    for axis, value in record["anchors"]:
        anchors[axis].add(round(value, _PLACE))
    for point in record["datums"]:
        axis = _plane_axis(shape, point)
        if axis is not None:
            anchors[axis].add(round(point[axis], _PLACE))
    for surface in turned_surfaces(shape):
        along = next((k for k in range(3) if abs(abs(surface.axis[k]) - 1) < 1e-9), None)
        across = [k for k in range(3) if k != along]
        if along is not None and all(abs(hi[k] - lo[k] - surface.diameter) <= 0.01 for k in across):
            for k in across:
                anchors[k].add(round(surface.middle[k], _PLACE))
    whole = revolved(shape, bores=True)
    if whole is not None:
        for k in range(3):
            if k != whole.axis:
                anchors[k].add(round(whole.at[k], _PLACE))
    return anchors


def _plane_axis(shape, point) -> int | None:
    """The model axis a planar face through ``point`` is square to, if it is."""
    from build123d import GeomType, Vector

    for face in shape.faces():
        if face.geom_type != GeomType.PLANE or face.distance_to(Vector(*point)) > 1e-6:
            continue
        normal = face.normal_at()
        return next((k for k, c in enumerate((normal.X, normal.Y, normal.Z)) if abs(abs(c) - 1) < 1e-9), None)
    return None


def _circle_links(record: dict) -> dict[int, list]:
    """A bolt circle locates its holes from its centre: each hole's place tied to
    the centre's, along each model axis."""
    links: dict[int, list] = {axis: [] for axis in range(3)}
    for circle in _found(record, "circles"):
        for mouth in circle.mouths:
            for axis in range(3):
                links[axis].append((round(mouth[axis], _PLACE), round(circle.centre[axis], _PLACE)))
    return links


def _interfaces(facts: _Facts) -> list[str]:
    """Where an assembly's parts meet, for the person to settle how each joint
    works: whether it turns, slides, locates or is fixed decides a fit, and
    what holds it along its axis decides its end play. A pin in a bore of its
    own size, or faces that touch, are what the model says at nominal sizes,
    which no shop can make: each is named, and what decides it. The lines are
    the joints to review, printed whether or not the sheets state them yet;
    each sheet's requirements: line says which sizes still have no fit."""
    from cadgen._internal.drawing_assembly import interfaces

    lines: list[str] = []
    for entry in facts.lists.values():
        parts = entry["parts"]

        def named(number: int) -> str:
            return f"item {number} ({parts[number].description or 'unnamed'})"

        fits, abutments = interfaces(parts)
        for fit in fits:
            gap = round(fit.bore - fit.shaft, 4)
            head = (f"interface: {named(fit.inner)} ⌀{_fmt(fit.shaft)} in {named(fit.outer)} ⌀{_fmt(fit.bore)}, "
                    f"on the axis {_axis_words(fit.axis)} through {_where(fit.at)}{_places(fit.places)}: ")
            if gap > 0:
                lines.append(head + f"{_fmt(gap)} clearance at nominal sizes.")
                continue
            what = "no clearance" if gap == 0 else f"{_fmt(-gap)} interference"
            lines.append(head + f"{what} at nominal sizes. Whether it turns, slides, locates or is fixed decides the "
                         "fit both sizes need (fit= or tol= on each).")
        for touch in abutments:
            a, b = touch.items
            lines.append(f"interface: {named(a)} and {named(b)} touch face to face square to the axis "
                         f"{_axis_words(touch.axis)}, at {_where(touch.at)}{_places(touch.places)}: no end play at "
                         "nominal sizes. What holds the joint along its axis decides the end play it needs, or "
                         "that it is clamped there.")
    return lines


def _vector(v) -> str:
    """A direction as ``(0.71, 0.71, 0)``: no quotes, no minus zero."""
    return f"({', '.join(_fmt(round(c, 3) + 0.0) for c in v)})"


def _places(count: int) -> str:
    return f" ({count} places)" if count > 1 else ""


def _axis_words(d) -> str:
    """A direction as words: ``along Y``, or its components."""
    k = next((k for k in range(3) if abs(abs(d[k]) - 1) < 1e-9), None)
    return f"along {'XYZ'[k]}" if k is not None else f"along ({', '.join(_fmt(c) for c in d)})"


def _redundant(facts: _Facts) -> list[str]:
    """The dimensions a part's other dimensions already fix: along one axis, a
    dimension whose two ends the others tie together closes a loop, and the
    loop states one size twice. A shop meets both, and their tolerances cannot
    both hold.

    A dimension's end is the feature it lands on, not the coordinate it shares:
    a hole whose centre line it is on, or the one flat face square to the axis
    it touches. Two pairs of holes at one spacing, or two bosses of one height,
    are two sizes. An end off the part at its extreme (an overall size's corner)
    is every face at that extreme, and an end where coplanar faces meet is each
    of them. Hole tables and bolt circles place features without asking a size,
    so they close no loop of their own, though a dimension can close one with
    them. A basic dimension is the exact target a frame bounds, a reference
    dimension asks nothing, and a diameter across a profile is its feature's
    size, however many steps share it: none of them is part of a loop."""
    from build123d import GeomType, Vector

    lines: list[str] = []
    records = list(facts.parts.values())
    for record in records:
        if record.get("assembly"):
            continue  # an assembly's envelope is reference dimensions
        whose = _whose(record, records)
        shape = record["shape"]
        holes = _found(record, "holes")
        box = shape.bounding_box()
        for axis in range(3):
            extremes = (round(tuple(box.min)[axis], _PLACE), round(tuple(box.max)[axis], _PLACE))
            flats = []
            for face in shape.faces():
                if face.geom_type == GeomType.PLANE:
                    normal = tuple(face.normal_at())
                    if abs(abs(normal[axis]) - 1) < 1e-9:
                        flats.append((round(tuple(face.center())[axis], _PLACE), face))
            near: dict[tuple, list[tuple[tuple, str]]] = {}

            def tie(a: tuple, b: tuple, what: str) -> None:
                near.setdefault(a, []).append((b, what))
                near.setdefault(b, []).append((a, what))

            def node(point) -> tuple:
                for hole in holes:
                    if abs(hole.axis[axis]) > 1e-6:
                        continue  # a hole along this axis is no one place on it
                    rel = [p - m for p, m in zip(point, hole.mouth)]
                    along = sum(r * d for r, d in zip(rel, hole.axis))
                    if math.dist([r - along * d for r, d in zip(rel, hole.axis)], (0.0, 0.0, 0.0)) <= 0.01:
                        return ("hole", round(hole.mouth[axis], _PLACE),
                                tuple(round(c, 3) for c, d in zip(hole.mouth, hole.axis) if abs(d) < 1e-6))
                place = round(point[axis], _PLACE)
                level = [(k, face) for k, (at, face) in enumerate(flats) if at == place]
                touching = [k for k, face in level if face.distance_to(Vector(*point)) < 1e-3]
                if len(touching) == 1:
                    return ("face", touching[0])
                if not touching and len(level) == 1 and place not in extremes:
                    return ("face", level[0][0])
                spot = ("at", place)
                for k in touching or ([k for k, _face in level] if place in extremes else []):
                    tie(spot, ("face", k), "")
                return spot

            for circle in _found(record, "circles"):
                for mouth in circle.mouths:
                    tie(node(mouth), node(circle.centre), "bolt circle")
            spans = [(node(ends[0]), node(ends[1]), what, kind)
                     for k, _a, _b, what, kind, ends in record["spans"] if k == axis and kind in ("size", "table")]
            for a, b, what, kind in spans:
                if kind == "table":
                    tie(a, b, what)
            for a, b, what, kind in spans:
                if kind != "size" or a == b:
                    continue
                loop = _path(near, a, b)
                if loop is None:
                    tie(a, b, what)
                    continue
                named = [n for n in dict.fromkeys([*loop, what]) if n]
                lines.append(f"redundant: {whose}along {'XYZ'[axis]}, {_and('the ' + n for n in named)} state one "
                             "size twice: a shop meets both, and their tolerances cannot both hold. Make one of the "
                             "dimensions reference=True, or leave it out.")
    return lines


def _found(record: dict, what: str) -> list:
    """A part's holes, slots or bolt circles, read off it once for every check
    that asks."""
    from cadgen._internal.drawing_features import bolt_circles, holes as find_holes, slots as find_slots

    cache = record.setdefault("_found", {})
    if what not in cache:
        if what == "holes":
            cache[what] = find_holes(record["shape"])
        elif what == "slots":
            cache[what] = find_slots(record["shape"])
        else:
            cache[what] = bolt_circles(record["shape"], _found(record, "holes"))
    return cache[what]


def _slope_links(record: dict) -> dict[int, list]:
    """What an aligned dimension ties together where an angle fixes its
    direction: its length and its angle give its run and its rise, so its two
    ends are tied along each model axis it leans across. An angle fixes a leg's
    direction when its other leg runs along a model axis, and then fixes the
    direction square to it in the same view (the right angle a drawing
    implies)."""
    known = []
    for vertex, p1, p2, look in record["angles"]:
        legs = [tuple(q - v for q, v in zip(p, vertex)) for p in (p1, p2)]
        for leg, other in (legs, legs[::-1]):
            if sum(abs(c) > 1e-9 for c in other) == 1:
                known.append((leg, look))
    links: dict[int, list] = {axis: [] for axis in range(3)}
    for p, q in record["aligned"]:
        run = tuple(b - a for a, b in zip(p, q))
        length = math.sqrt(sum(c * c for c in run)) or 1.0
        for leg, look in known:
            if abs(sum(a * b for a, b in zip(run, look))) > 1e-6 * length:
                continue  # not in that angle's view
            reach = math.sqrt(sum(c * c for c in leg)) or 1.0
            along = abs(sum(a * b for a, b in zip(run, leg))) / (length * reach)
            if along > 0.9999 or along < 1e-4:
                for k in range(3):
                    if abs(run[k]) > 1e-9:
                        links[k].append((round(p[k], _PLACE), round(q[k], _PLACE)))
                break
    return links


def _fixed(record: dict, axis: int) -> bool:
    """Whether a part's other dimensions fix its overall size along ``axis``: its
    two extremes tied together through them, an aligned dimension at a stated
    angle counting for its run and its rise."""
    box = record["shape"].bounding_box()
    near: dict[float, list[tuple[float, str]]] = {}
    links = _circle_links(record)[axis] + _slope_links(record)[axis] + [
        (round(a, _PLACE), round(b, _PLACE)) for k, a, b, *_rest in record["spans"] if k == axis]
    for a, b in links:
        near.setdefault(a, []).append((b, ""))
        near.setdefault(b, []).append((a, ""))
    return _path(near, round(tuple(box.min)[axis], _PLACE), round(tuple(box.max)[axis], _PLACE)) is not None


def _and(words) -> str:
    """``a``, ``a and b``, ``a, b and c``."""
    words = list(words)
    return words[0] if len(words) == 1 else f"{', '.join(words[:-1])} and {words[-1]}"


def _path(near: dict, a: Hashable, b: Hashable) -> list[str] | None:
    """What ties place ``a`` to place ``b`` through ``near``, the shortest way, or None."""
    came: dict[Hashable, tuple[Hashable, str] | None] = {a: None}
    queue = [a]
    for place in queue:
        if place == b:
            out = []
            while came[place] is not None:
                place, what = came[place]
                out.append(what)
            return out[::-1]
        for other, what in near.get(place, ()):
            if other not in came:
                came[other] = (place, what)
                queue.append(other)
    return None


def _reached(record: dict) -> dict[int, set]:
    """Every place along each model axis the sheet ties to an anchor through its
    dimensions, its hole tables and its bolt circles; worked out once a part."""
    if "_reached" not in record:
        record["_reached"] = _reach(record)
    return record["_reached"]


def _reach(record: dict) -> dict[int, set]:
    links = _circle_links(record)
    for axis, slopes in _slope_links(record).items():
        links[axis].extend(slopes)
    box = record["shape"].bounding_box()
    middle = tuple(round((lo + hi) / 2, _PLACE) for lo, hi in zip(box.min, box.max))
    for axis, a, b, *_rest in record["spans"]:
        a, b = round(a, _PLACE), round(b, _PLACE)
        links[axis].append((a, b))
        if axis in record["symmetric"] and round((a + b) / 2, _PLACE) == middle[axis]:
            # Across a centre line stated symmetric, each end is half of it from the
            # line (ISO 129-1): a spacing centred on it places both.
            links[axis].append((a, middle[axis]))
    reached = _anchors(record)
    for axis in range(3):
        grown = True
        while grown:
            grown = False
            for a, b in links[axis]:
                if (a in reached[axis]) != (b in reached[axis]):
                    reached[axis] |= {a, b}
                    grown = True
            if axis in record["symmetric"]:
                # One side of a part stated symmetric places the other: the mirror
                # of every place reached is reached (ISO 129-1).
                mirrored = {round(2 * middle[axis] - place, _PLACE) for place in reached[axis]}
                if not mirrored <= reached[axis]:
                    reached[axis] |= mirrored
                    grown = True
    return reached


def _unlocated(record: dict, whose: str) -> list[str]:
    """Every hole and slot the sheet calls out but does not place: a feature is
    located across its axis when its centre (or a slot's end) ties to an anchor
    through dimensions, a hole table or a bolt circle. A size or a spacing tied to
    nothing leaves it anywhere on the part."""
    shape, views = record["shape"], record["views"]
    reached = None
    kinds: dict[tuple, list] = {}
    for feature in [*_found(record, "holes"), *_found(record, "slots")]:
        if _member_key(feature) not in record["called"]:
            continue
        along = next((k for k in range(3) if abs(abs(feature.axis[k]) - 1) < 1e-9), None)
        if along is None:
            continue  # an inclined hole is located in the view square to it, which measures no model axis
        if reached is None:
            reached = _reached(record)
        places = [feature.mouth, *getattr(feature, "ends", ())]
        missing = [axis for axis in range(3) if axis != along
                   and not any(round(p[axis], _PLACE) in reached[axis] for p in places)]
        if missing:
            kinds.setdefault(_feature_key(feature), []).append((feature, missing))
    lines = []
    for members in kinds.values():
        feature = members[0][0]
        missing = sorted({axis for _f, axes in members for axis in axes})
        is_slot = isinstance(feature, Slot)
        text = _feature_text(feature, len(members))
        where = next((name for name, look in views if _looks_into(feature, look)), "view")
        across = " and ".join("XYZ"[axis] for axis in missing)
        lines.append(
            f"incomplete: {whose}{text} is not located along {across}: no dimension ties it to an edge, a datum "
            f"or a located feature. {where}.dim(edge point, its centre) locates it, a hole_table() lists where "
            f"each is, or {where}.symmetric(\"h\" or \"v\") states the part symmetric about the centre line it "
            "sits on."
        )
    return lines


def _owned(face, features) -> bool:
    """Whether a planar face belongs to a hole or slot whose callout states it: a
    counterbore's floor, a blind hole's bottom, a slot's floor."""
    points = [(v.X, v.Y, v.Z) for v in face.vertices()] or [tuple(face.center())]
    for feature in features:
        axis, mouth = feature.axis, feature.mouth
        normal = face.normal_at()
        square = abs(abs(normal.X * axis[0] + normal.Y * axis[1] + normal.Z * axis[2]) - 1) <= 1e-6
        if not square and not isinstance(feature, Slot):
            continue  # a slot's flat walls are its own too; a hole's are round
        if isinstance(feature, Slot):
            reach, line = feature.width / 2, feature.ends
        else:
            reach = max([feature.diameter, *(pair[0] for pair in (feature.cbore, feature.csk, feature.far_cbore,
                                                                     feature.far_csk) if pair)]) / 2
            line = (mouth, mouth)

        def off(p, a=line[0], b=line[1]) -> float:
            # Distance from p to the feature's axis (or a slot's centre segment), across its axis.
            ab = tuple(q - r for q, r in zip(b, a))
            ap = tuple(q - r for q, r in zip(p, a))
            run = sum(c * c for c in ab)
            t = 0.0 if run < 1e-12 else max(0.0, min(1.0, sum(x * y for x, y in zip(ap, ab)) / run))
            d = tuple(q - (r + t * s) for q, r, s in zip(p, a, ab))
            along = sum(x * y for x, y in zip(d, axis))
            return math.sqrt(max(0.0, sum(x * x for x in d) - along * along))

        if all(off(p) <= reach + 0.01 for p in points):
            return True
    return False


def _unplaced_faces(record: dict, whose: str) -> list[str]:
    """The flat faces a part's sheets leave without a place or an angle. A face
    square to a model axis (a step, a shoulder, a rib's side, a plate's top) is
    placed when its position ties to an anchor through dimensions; an inclined
    face is stated by an angle in a view that sees it edge-on. Faces a called-out
    hole or slot owns, and chamfers, are stated by their callouts and notes."""
    from build123d import GeomType, Vector

    from cadgen._internal.drawing_features import chamfers

    shape, views = record["shape"], record["views"]
    features = [f for f in [*_found(record, "holes"), *_found(record, "slots")] if _member_key(f) in record["called"]]
    bevels = [c.point for c in chamfers(shape)]
    reached = None
    steps: dict[tuple[int, float], None] = {}
    slopes: dict[tuple, None] = {}
    for face in shape.faces():
        if face.geom_type != GeomType.PLANE:
            continue
        n = face.normal_at()
        normal = (n.X, n.Y, n.Z)
        axis = next((k for k in range(3) if abs(abs(normal[k]) - 1) < 1e-9), None)
        if axis is not None:
            if reached is None:
                reached = _reached(record)
            place = round(tuple(face.center())[axis], _PLACE)
            if place not in reached[axis] and not _owned(face, features):
                steps[(axis, place)] = None
            continue
        if any(face.distance_to(Vector(*p)) < 1e-6 for p in bevels):
            continue
        seen = [name for name, look in views if abs(sum(a * b for a, b in zip(normal, look))) < 1e-6]
        stated = False
        for vertex, p1, p2, look in record["angles"]:
            if abs(sum(a * b for a, b in zip(normal, look))) > 1e-6:
                continue
            for leg in (p1, p2):
                u = tuple(q - r for q, r in zip(leg, vertex))
                length = math.sqrt(sum(c * c for c in u)) or 1.0
                along = abs(sum(a * b for a, b in zip(normal, u))) / length
                # A leg along the face states its angle; a leg along its normal states
                # it square to a stated slope, the right angle a drawing implies.
                if along < 0.01 or along > 0.9999:
                    stated = True
        if not stated and sum(abs(c) < 1e-9 for c in normal) == 1:
            # A slope seen edge-on, both its ends placed in the plane it leans in, is
            # defined by them: a gusset given by its legs.
            if reached is None:
                reached = _reached(record)
            leans = [k for k in range(3) if abs(normal[k]) >= 1e-9]
            stated = all(round(getattr(v, "XYZ"[k]), _PLACE) in reached[k] for v in face.vertices() for k in leans)
        if not stated:
            slopes[(tuple(round(c, 3) for c in normal), seen[0] if seen else None)] = None
    lines = []
    for axis, place in sorted(steps):
        where = next((name for name, look in views if abs(look[axis]) < 1e-9), None)
        fix = (f"{where}.dim(...) from an edge, or from a located face, places it." if where else
               "No view on the drawing sees it edge-on.")
        lines.append(f"incomplete: {whose}the face at {'XYZ'[axis]} = {_fmt(place)} (square to {'XYZ'[axis]}) is "
                     f"not located: no dimension ties it to an edge, a datum or a located face. {fix}")
    if len(slopes) > _MANY_SLOPES:
        # Past a few, a line each buries the rest of the report: one line says how
        # many, which views can state them, and the first few to look for.
        shown = ", ".join(_vector(normal) for normal, _where in list(slopes)[:_MANY_SLOPES])
        seen = sorted({where for _normal, where in slopes if where})
        unseen = sum(1 for _normal, where in slopes if where is None)
        fix = [f"{where}.angle(vertex, p1, p2), one leg along a face, states each it sees edge-on." for where in seen]
        fix += [f"No view on the drawing sees {unseen} of them edge-on; add one."] if unseen else []
        lines.append(f"incomplete: {whose}{len(slopes)} inclined faces have no angle (their normals {shown} and "
                     f"{len(slopes) - _MANY_SLOPES} more). {' '.join(fix)}")
        return lines
    for normal, where in slopes:
        fix = (f"{where}.angle(vertex, p1, p2), one leg along the face, states it." if where else
               "No view on the drawing sees it edge-on; add one.")
        lines.append(f"incomplete: {whose}an inclined face (its normal {_vector(normal)}) has no "
                     f"angle. {fix}")
    return lines


def _unstated_turns(record: dict, whose: str) -> list[str]:
    """A taper's two ends and a groove's size and place: a taper is stated by both
    its end diameters, each end placed along its axis; a groove by its radius and
    its middle placed along its axis."""
    from cadgen._internal.drawing_features import grooves, tapers

    shape, views = record["shape"], record["views"]
    stated = record["values"]
    side = next((name for name, look in views), None)
    reached = None
    lines = []
    for taper in tapers(shape):
        along = next((k for k in range(3) if abs(abs(taper.axis[k]) - 1) < 1e-9), None)
        missing = [f"⌀{_fmt(d)}" for d in (taper.small, taper.large) if not any(abs(v - d) <= 0.01 for v in stated)]
        if along is not None:
            if reached is None:
                reached = _reached(record)
            missing += [f"its end at {'XYZ'[along]} = {_fmt(end[along])}" for end in taper.ends
                        if round(end[along], _PLACE) not in reached[along]]
        if missing:
            lines.append(f"incomplete: {whose}the taper from ⌀{_fmt(taper.large)} to ⌀{_fmt(taper.small)} leaves "
                         f"{', '.join(missing)} unstated: a diameter across its profile at each end "
                         "(text=\"%%c<>\"), and each end placed along its axis, state it.")
    for groove in grooves(shape):
        along = next((k for k in range(3) if abs(abs(groove.axis[k]) - 1) < 1e-9), None)
        named = any(abs(r - groove.radius) <= 0.01 for r in record.get("radii", ()))
        missing = [] if named else [f"its radius R{_fmt(groove.radius)}"]
        if along is not None:
            if reached is None:
                reached = _reached(record)
            if round(groove.middle[along], _PLACE) not in reached[along]:
                missing.append(f"its place along {'XYZ'[along]}")
        if missing:
            at = f"{'XYZ'[along]} = {_fmt(groove.middle[along])}" if along is not None else _where(groove.middle)
            lines.append(f"incomplete: {whose}the groove R{_fmt(groove.radius)} at {at} leaves "
                         f"{' and '.join(missing)} unstated: "
                         f"{side or 'a view'}.radius(...) on its arc and a dimension to its middle state it.")
    return lines


def _tally(sheet, work: list, tables: dict) -> dict:
    """What a sheet states as requirements, for the report: its sizes by kind
    (toleranced, basic, reference, nominal), its datums, frames and key
    characteristics, and the holes, slots and turned diameters it leaves with no
    fit, tolerance or position -- the interfaces a shop asks about first."""
    sizes = dict.fromkeys(("toleranced", "basic", "reference", "nominal"), 0)
    loose: list[str] = []
    frames = keys = 0
    for view, _proj, _bounds, items, *_rest in work:
        sizes["reference" if view._overall_reference else "nominal"] += len(view._overall)
        for dim in items:
            if dim.kind in ("note", "flag"):
                continue
            if dim.kind == "frame":
                frames += 1
                continue
            frames += dim.frame is not None
            keys += dim.key
            held = bool(dim.tol or dim.fit or dim.limits or dim.frame is not None or (dim.hole or {}).get("thread"))
            kind = "basic" if dim.basic else "reference" if dim.reference else "toleranced" if held else "nominal"
            sizes[kind] += 1
            if kind != "nominal":
                continue
            if dim.kind in ("hole", "slot"):
                loose.append(_shown(hole_callout_text(dim.hole)))
            elif dim.kind == "diameter":
                loose.append(f"⌀{_fmt(2 * dim.radius)}")
            elif dim.kind == "linear" and (dim.text or "").startswith("%%c"):
                loose.append(f"⌀{_fmt(math.dist(dim.p1, dim.p2))}")
    # A hole table lists one row per hole: a kind's rows are counted, as a callout
    # counts its holes.
    rows = [_shown(row.size) for table in tables.values() for row in table.rows]
    sizes["nominal"] += len(rows)
    loose.extend(f"{rows.count(size)}× {size}" if rows.count(size) > 1 else size for size in dict.fromkeys(rows))
    datums = sorted({d[0] for view in sheet.views for d in view._datums}
                    | {d.datum for view in sheet.views for d in view._dims if d.datum})
    return {"sizes": sizes, "loose": list(dict.fromkeys(loose)), "frames": frames, "keys": keys,
            "datum_letters": datums, "tolerance": sheet.general_tolerance,
            "profiled": sheet.general_profile is not None}


def _requirements(facts: _Facts) -> list[str]:
    """What each part's sheet states as requirements, apart from what it draws:
    a sheet can locate and size every feature and tolerance none of them, and the
    report says which, so neither is mistaken for the other."""
    lines = []
    for record in facts.sheets:
        if not record["part"] or "sizes" not in record:
            continue
        sizes, total = record["sizes"], sum(record["sizes"].values())
        under = (f" under {record['tolerance']}" if record["tolerance"]
                 else " under the general profile" if record["profiled"] else "")
        if total == sizes["nominal"]:
            stated = f"{total} size{'' if total == 1 else 's'}, all nominal{under}"
        else:
            stated = ", ".join(f"{n} {kind}{under if kind == 'nominal' else ''}" for kind, n in sizes.items() if n)
            stated = f"{total} sizes: {stated}"
        parts = [record["stage"] or "no stage", stated]
        if not (record["tolerance"] or record["profiled"]):
            parts.append("no general tolerance")
        frames = record["frames"] + record["profiled"]
        if not record["datum_letters"] and not frames:
            parts.append("no datums or frames")
        else:
            parts.append(f"datums {' '.join(record['datum_letters'])}" if record["datum_letters"] else "no datums")
            parts.append(f"{frames} frame{'' if frames == 1 else 's'}")
        if record["keys"]:
            parts.append(f"{record['keys']} key characteristic{'' if record['keys'] == 1 else 's'}")
        if record["loose"]:
            parts.append(f"no fit, tolerance or position on {', '.join(record['loose'])}")
        lines.append(f"requirements: {_whose(record, facts.sheets)}{'; '.join(parts)}.")
    return lines


def _unstated_for_stage(record: dict, whose: str) -> list[str]:
    """What a part's sheet leaves out that its stage asks it to define. A concept
    is a drawing to talk over and asks nothing; a prototype states a general
    tolerance and the material; production leaves nothing undefined."""
    stage = record["stage"]
    if stage not in ("prototype", "production") or not record["part"]:
        return []
    lines = []
    if stage == "prototype":
        if not record["general"]:
            lines.append(f"incomplete: {whose}a prototype drawing states a general tolerance for what it does not "
                         "tolerance one by one; Sheet(general_tolerance=...) or general_profile= states it.")
        if not record["material"]:
            lines.append(f"incomplete: {whose}a prototype drawing states the material; Sheet(material=...).")
        return lines
    if not record["datums"]:
        lines.append(f"incomplete: {whose}a production drawing locates its features from datums, and no datum is "
                     "marked; view.datum(\"A\", point) on the face the part locates on defines one.")
    if not record["general"]:
        lines.append(f"incomplete: {whose}a production drawing leaves no surface undefined, and no general profile "
                     "or general tolerance covers what it does not dimension one by one; "
                     "Sheet(general_profile=Frame(\"surface_profile\", ...)) or general_tolerance= covers it.")
    if not (record["material"] and record["spec"]):
        lines.append(f"incomplete: {whose}a production drawing states the material and its spec; "
                     "Sheet(material=..., spec=...).")
    if not record["finish"]:
        lines.append(f"incomplete: {whose}a production drawing states the finish, or that there is none; "
                     "Sheet(finish=...).")
    if not record["keyed"]:
        lines.append(f"note: {whose}a production drawing marks its key characteristics, and no feature is marked "
                     f"{record['mark']}; key=True on the dimension or callout of a feature whose variation affects "
                     "fit, function or safety marks it, if any is one.")
    return lines


def geometry_notes(part) -> list[str]:
    """The general notes the part's own geometry makes true, for
    ``Sheet(notes=...)``. A note that governs unspecified edges -- ``FILLETS R3
    UNLESS OTHERWISE SPECIFIED.`` -- asks the shop to treat every such edge drawn
    without a callout that way, so it is written only when the part leaves no
    edge of its kind sharp: every inside corner a fillet (the commonest radius
    is the note's), or every outside edge rounded (``ROUNDS``) or chamfered
    (``CHAMFERS 1 × 45°``), whichever is commoner. Blends and chamfers of other
    sizes still need stating, and the completeness report says which. A part
    with sharp edges of both kinds gets no notes."""
    from collections import Counter

    from cadgen._internal.drawing_features import blends, chamfers, sharp_edges

    found = blends(part)
    bevels = [c for c in chamfers(part) if c.symmetric]
    outside, inside = sharp_edges(part)
    notes = []
    fillets = Counter(round(b.radius, 3) for b in found if b.concave)
    if fillets and not inside:
        notes.append(f"FILLETS R{_fmt(_commonest(fillets))} UNLESS OTHERWISE SPECIFIED.")
    rounds = Counter(round(b.radius, 3) for b in found if not b.concave)
    sizes = Counter(round(c.legs[0], 3) for c in bevels)
    if not outside and (rounds or sizes):
        if sum(rounds.values()) >= sum(sizes.values()):
            notes.append(f"ROUNDS R{_fmt(_commonest(rounds))} UNLESS OTHERWISE SPECIFIED.")
        else:
            notes.append(f"CHAMFERS {_fmt(_commonest(sizes))} × 45° UNLESS OTHERWISE SPECIFIED.")
    return notes


def _commonest(counts) -> float:
    """The most frequent value; the larger of a tie."""
    return max(counts, key=lambda value: (counts[value], value))


def _unstated_edges(record: dict, whose: str) -> list[str]:
    """The blends and chamfers a part's sheets leave unstated. A blend is stated by
    a note naming its radius and kind (FILLETS for inside corners, ROUNDS for
    outside edges, RADII for either) or by a ``radius()`` callout of its size; a
    chamfer by a note giving its size (``1 × 45°``, or ``1 × 2`` for unequal
    legs)."""
    from cadgen._internal.drawing_features import blends, chamfers

    notes = [note.upper() for note in record.get("notes", ())]
    lines = []
    groups: dict[tuple, int] = {}
    for blend in blends(record["shape"]):
        key = (round(blend.radius, 3), blend.concave)
        groups[key] = groups.get(key, 0) + 1
    for (radius, concave), count in sorted(groups.items()):
        word = "FILLET" if concave else "ROUND"
        mark = re.compile(rf"\bR{re.escape(_fmt(radius))}(?!\.?\d)")  # R0.8 is not R0.85
        named = any(mark.search(note) and (word in note or "RADII" in note) for note in notes)
        if named or radius in record.get("radii", ()):
            continue
        plural = count > 1
        lines.append(
            f"incomplete: {whose}{count} {word.lower()}{'s' if plural else ''} R{_fmt(radius)} "
            f"{'are' if plural else 'is'} not stated. radius(...) states one where a view shows it as an arc, "
            "or geometry_notes(part) gives a general note when the part's edges make one true."
        )
    bevels: dict[tuple, int] = {}
    for chamfer in chamfers(record["shape"]):
        key = tuple(sorted((round(chamfer.legs[0], 3), round(chamfer.legs[1], 3))))
        bevels[key] = bevels.get(key, 0) + 1
    for (a, b), count in sorted(bevels.items()):
        size = f"{_fmt(a)} × 45°" if abs(a - b) < 1e-3 else f"{_fmt(a)} × {_fmt(b)}"
        second = "45°" if abs(a - b) < 1e-3 else re.escape(_fmt(b))
        mark = re.compile(rf"(?<![\d.]){re.escape(_fmt(a))} ?[×X] ?{second}")
        if any(mark.search(note) for note in notes):
            continue
        plural = count > 1
        lines.append(
            f"incomplete: {whose}{count} chamfer{'s' if plural else ''} {size} {'are' if plural else 'is'} not "
            f"stated. A note giving its size states it (\"CHAMFER {size}\"), or geometry_notes(part) gives a "
            "general note when the part's edges make one true."
        )
    return lines
