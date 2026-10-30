"""What a drawing reads off a part's faces: its holes and its turned axes.

An engineering drawing states a hole as one callout -- ``4× ⌀6.6 THRU ⌴ ⌀11 ↧6.5``
-- and every number in it is a fact of the geometry: the diameter of the bore,
whether it runs through, how deep it goes, the counterbore or countersink at its
mouth, and how many identical holes the part has. Typing those numbers into the
drawing script lets them drift from the model, so this module reads them off the
B-rep instead, and the drawing checks anything the author does type against them.

A hole is a chain of concave, full-circle cylinders and cones on one axis line,
end to end, whose inside is air. Two pieces of one drilled hole separated by air
-- a pin hole through both arms of a clevis, a bore broken through by a cross hole
or a slot -- are one hole. Which end is its mouth comes from the solid itself: a
point on the axis just past an end is either air (an open end) or material (the
floor of a blind hole). A boss or a shaft is a convex cylinder and is never a
hole; a slot's rounded end is half a cylinder, and an O-ring groove or a pocket
around a standoff has material inside it, so neither is one either.

The same cylinders give a drawing its centre lines: a turned feature seen from
the side is drawn with its axis as a chain line, and :func:`axes` returns those
axes with the length of the part they span.

Two patterns a callout states as one thing are read here too. A slot is two
concave half cylinders of one radius on parallel axes, open toward each other,
with air between them: ``8 × 30 SLOT THRU``. A bolt circle is three or more
identical holes equally spaced on a circle around a turned axis of the part:
``6× ⌀6 THRU EQ SP ON ⌀60``.

A part's blends and chamfers are read too, so a drawing can state them in a
general note and say which it leaves unstated. A blend is a part-cylinder or
torus face tangent to both faces it joins: a fillet where it rounds an inside
corner, a round where it rounds an outside edge. A chamfer is a narrow flat
strip bevelling a square outside edge, or a short cone bevelling a turned
part's end.

Nothing here imports the kernel at module scope.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

__all__ = ["Hole", "Axis", "Slot", "BoltCircle", "Blend", "Chamfer", "holes", "axes", "slots", "bolt_circles",
           "turned_diameters", "blends", "chamfers", "sharp_edges"]

#: Model millimetres two positions on an axis may differ by and still touch. A
#: counterbore's floor and the bore below it meet at one plane, so their ranges
#: share an end; tessellation-free B-rep values agree far closer than this.
_TOUCH = 1e-4
#: The thickness, in mm, past which what a part and its mirror do not share is a
#: feature, not a boolean's sliver: a micron.
_SLIVER = 1e-3
#: How far past an end of a hole the solid is sampled to decide whether it is open.
_PROBE = 0.05


@dataclass(frozen=True)
class Hole:
    """One hole, as a callout states it.

    ``mouth`` is the point on the axis where the hole opens (for a through hole,
    the end with the counterbore or countersink, else the end at the larger
    coordinate along ``axis``); ``axis`` is the unit direction from the mouth into
    the material. Sizes are model millimetres; ``depth`` is measured from the
    mouth to the end of the full-diameter bore, so a drill point below it is not
    counted, and is None for a through hole.
    """

    mouth: tuple[float, float, float]
    axis: tuple[float, float, float]
    diameter: float
    thru: bool
    depth: float | None = None
    cbore: tuple[float, float] | None = None
    csk: tuple[float, float] | None = None
    #: A through hole's counterbore or countersink at its far end, as (diameter,
    #: depth) and (diameter, angle): a bore chamfered at both ends has both.
    far_cbore: tuple[float, float] | None = None
    far_csk: tuple[float, float] | None = None
    #: From the mouth to the far end of the hole, along ``axis``.
    length: float = 0.0
    #: Why no one callout states this hole, when none can: an end opened out in
    #: steps (a chamfered counterbore, a counterbore in a counterbore). Such a hole
    #: is refused wherever a callout or a table would state it.
    problem: str | None = None

    def signature(self) -> tuple:
        """What makes two holes "the same hole" for a ``4×`` count."""
        r = lambda v: None if v is None else round(v, 3)
        pair = lambda p: None if p is None else (round(p[0], 3), round(p[1], 3))
        return (r(self.diameter), self.thru, r(self.depth), pair(self.cbore), pair(self.csk),
                pair(self.far_cbore), pair(self.far_csk), self.problem)


@dataclass(frozen=True)
class Axis:
    """A turned feature's axis: the line, and the stretch of it the part occupies."""

    start: tuple[float, float, float]
    end: tuple[float, float, float]
    #: The largest radius turned about it, for sizing a centre mark.
    radius: float = 0.0


@dataclass(frozen=True)
class Slot:
    """An obround slot, as a callout states it.

    ``mouth`` is the slot's centre (midway between its two arc centres) where it
    opens, ``axis`` the unit direction into the material, ``ends`` the two arc
    centres at the mouth and ``direction`` the unit vector between them. Sizes are
    model millimetres; ``length`` is end to end, and ``depth`` is None for a
    slot through the part.
    """

    mouth: tuple[float, float, float]
    axis: tuple[float, float, float]
    direction: tuple[float, float, float]
    ends: tuple[tuple[float, float, float], tuple[float, float, float]]
    width: float
    length: float
    thru: bool
    depth: float | None = None
    #: From the mouth to the slot's far end, along ``axis``.
    run: float = 0.0
    #: A wider slot sunk at the mouth, as (width, length, depth).
    cbore: tuple[float, float, float] | None = None

    def signature(self) -> tuple:
        r = lambda v: None if v is None else round(v, 3)
        sunk = None if self.cbore is None else tuple(round(v, 3) for v in self.cbore)
        return ("slot", r(self.width), r(self.length), self.thru, r(self.depth), sunk)


@dataclass(frozen=True)
class BoltCircle:
    """Identical holes equally spaced on a circle: their centre (at the holes'
    mouths), the holes' common axis, the circle's diameter and the hole mouths."""

    centre: tuple[float, float, float]
    axis: tuple[float, float, float]
    diameter: float
    mouths: tuple[tuple[float, float, float], ...]


@dataclass
class _Segment:
    kind: str  # "cyl" or "cone"
    lo: float  # axial range along the line's canonical direction
    hi: float
    r_lo: float  # radius at each end (equal for a cylinder)
    r_hi: float
    concave: bool
    span: float  # angular extent in radians; full is 2*pi
    #: Unit radial direction from the axis to the middle of the face: which way a
    #: part cylinder (a slot's end, a fillet) faces.
    bulge: tuple = (0.0, 0.0, 0.0)


def _canonical(direction, point) -> tuple[tuple, tuple]:
    """A line's direction with a fixed sign, and its point nearest the origin."""
    d = list(direction)
    for c in d:
        if abs(c) > 1e-9:
            if c < 0:
                d = [-v for v in d]
            break
    n = math.sqrt(sum(c * c for c in d))
    d = [c / n for c in d]
    t = sum(p * c for p, c in zip(point, d))
    foot = [p - t * c for p, c in zip(point, d)]
    return tuple(d), tuple(foot)


def _line_key(d, foot) -> tuple:
    return tuple(round(c, 4) for c in d) + tuple(round(c, 3) for c in foot)


def _surface_segments(shape) -> dict[tuple, tuple[tuple, tuple, list[_Segment]]]:
    """Every cylindrical and conical face, grouped by the axis line it turns about."""
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.BRepTools import BRepTools
    from OCP.GeomAbs import GeomAbs_Cone, GeomAbs_Cylinder

    lines: dict[tuple, tuple[tuple, tuple, list[_Segment]]] = {}
    for face in shape.faces():
        surface = BRepAdaptor_Surface(face.wrapped)
        kind = surface.GetType()
        if kind == GeomAbs_Cylinder:
            gp = surface.Cylinder()
        elif kind == GeomAbs_Cone:
            gp = surface.Cone()
        else:
            continue
        ax = gp.Axis()
        loc, direction = ax.Location(), ax.Direction()
        d, foot = _canonical((direction.X(), direction.Y(), direction.Z()), (loc.X(), loc.Y(), loc.Z()))
        # The axial range and the radius at each end, from points on the face's own
        # edges: a circle sits at one axial position, so its ends are exact.
        samples = []
        for edge in face.edges():
            for t in (0.0, 0.5, 1.0):
                p = edge.position_at(t)
                rel = (p.X - foot[0], p.Y - foot[1], p.Z - foot[2])
                along = sum(a * b for a, b in zip(rel, d))
                radial = math.sqrt(max(0.0, sum(c * c for c in rel) - along * along))
                samples.append((along, radial))
        if not samples:
            continue
        lo = min(a for a, _ in samples)
        hi = max(a for a, _ in samples)
        if hi - lo < _TOUCH:
            continue
        if kind == GeomAbs_Cylinder:
            r_lo = r_hi = gp.Radius()
        else:
            r_lo = max((r for a, r in samples if abs(a - lo) < 1e-6), default=0.0)
            r_hi = max((r for a, r in samples if abs(a - hi) < 1e-6), default=0.0)
        # Concave when the face's outward normal (out of the material) points back
        # toward the axis: material outside, air inside -- a bore, not a boss.
        u0, u1, v0, v1 = BRepTools.UVBounds_s(face.wrapped)
        point = face.position_at(0.5, 0.5)
        normal = face.normal_at(point)
        rel = (point.X - foot[0], point.Y - foot[1], point.Z - foot[2])
        along = sum(a * b for a, b in zip(rel, d))
        radial = tuple(c - along * k for c, k in zip(rel, d))
        concave = sum(a * b for a, b in zip(radial, (normal.X, normal.Y, normal.Z))) < 0
        reach = math.sqrt(sum(c * c for c in radial)) or 1.0
        segment = _Segment("cyl" if kind == GeomAbs_Cylinder else "cone", lo, hi, r_lo, r_hi, concave, u1 - u0,
                           tuple(c / reach for c in radial))
        lines.setdefault(_line_key(d, foot), (d, foot, []))[2].append(segment)
    return lines


def _merge_split_faces(segments: list[_Segment]) -> list[_Segment]:
    """One segment per surface: a STEP from some kernels splits a full cylinder into
    two half faces, and two halves of one bore are one bore."""
    merged: list[_Segment] = []
    for seg in sorted(segments, key=lambda s: (s.kind, s.lo, s.hi, s.r_lo, s.r_hi, s.concave)):
        for other in merged:
            if (other.kind == seg.kind and other.concave == seg.concave
                    and abs(other.lo - seg.lo) < _TOUCH and abs(other.hi - seg.hi) < _TOUCH
                    and abs(other.r_lo - seg.r_lo) < _TOUCH and abs(other.r_hi - seg.r_hi) < _TOUCH):
                # The merged face faces the way its pieces do between them: two
                # quarters of a slot's end make the half that opens toward the slot.
                summed = tuple(a * other.span + b * seg.span for a, b in zip(other.bulge, seg.bulge))
                reach = math.sqrt(sum(c * c for c in summed)) or 1.0
                other.bulge = tuple(c / reach for c in summed)
                other.span += seg.span
                break
        else:
            merged.append(_Segment(seg.kind, seg.lo, seg.hi, seg.r_lo, seg.r_hi, seg.concave, seg.span, seg.bulge))
    return merged


def _full(seg: _Segment) -> bool:
    return seg.span >= 2 * math.pi - 1e-6


def _chains(segments: list[_Segment]) -> list[list[_Segment]]:
    """Runs of segments that touch end to end along the axis."""
    chains: list[list[_Segment]] = []
    for seg in sorted(segments, key=lambda s: (s.lo, s.hi)):
        if chains and abs(chains[-1][-1].hi - seg.lo) < _TOUCH:
            chains[-1].append(seg)
        else:
            chains.append([seg])
    return chains


class _Ray:
    """Whether a feature is open past one of its ends, asked of one solid.

    Open means air just past the end AND no face of the part ahead within the
    feature's own width. Air alone was the old test, and a blind hole or slot
    with a filleted or ball floor has air just past where its straight wall
    stops: it read THRU. A face far ahead is a different matter -- a through
    hole in the floor of a closed box looks out at the lid -- so only a face
    close enough to be the feature's own floor closes it.
    """

    def __init__(self, shape) -> None:
        from OCP.IntCurvesFace import IntCurvesFace_ShapeIntersector

        self.shape = shape
        self.cast = IntCurvesFace_ShapeIntersector()
        self.cast.Load(shape.wrapped, 1e-7)

    def open(self, start, direction, width: float) -> bool:
        from build123d import Vector
        from OCP.gp import gp_Dir, gp_Lin, gp_Pnt

        if self.shape.is_inside(Vector(*start)):
            return False
        self.cast.Perform(gp_Lin(gp_Pnt(*start), gp_Dir(*direction)), 0.0, max(width, 1.0))
        return self.cast.NbPnt() == 0

    def depth(self, start, direction) -> float | None:
        """How far along ``direction`` from ``start`` the first face of the part is."""
        from OCP.gp import gp_Dir, gp_Lin, gp_Pnt

        self.cast.Perform(gp_Lin(gp_Pnt(*start), gp_Dir(*direction)), _PROBE, 1e9)
        hits = [self.cast.WParameter(i) for i in range(1, self.cast.NbPnt() + 1)]
        return min(hits) if hits else None


def _perpendicular(d) -> tuple[tuple, tuple]:
    """Two unit vectors square to ``d`` and to each other."""
    seed = (1.0, 0.0, 0.0) if abs(d[0]) < 0.9 else (0.0, 1.0, 0.0)
    u = (d[1] * seed[2] - d[2] * seed[1], d[2] * seed[0] - d[0] * seed[2], d[0] * seed[1] - d[1] * seed[0])
    n = math.sqrt(sum(c * c for c in u))
    u = tuple(c / n for c in u)
    v = (d[1] * u[2] - d[2] * u[1], d[2] * u[0] - d[0] * u[2], d[0] * u[1] - d[1] * u[0])
    return u, v


def _tori(shape) -> dict[tuple, list[tuple[float, float, float, float]]]:
    """Every toroidal face -- a fillet round a turned edge -- grouped by the axis
    line it turns about, as its axial range and its least and greatest radius."""
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_Torus

    found: dict[tuple, list[tuple[float, float, float, float]]] = {}
    for face in shape.faces():
        surface = BRepAdaptor_Surface(face.wrapped)
        if surface.GetType() != GeomAbs_Torus:
            continue
        ax = surface.Torus().Axis()
        loc, direction = ax.Location(), ax.Direction()
        d, foot = _canonical((direction.X(), direction.Y(), direction.Z()), (loc.X(), loc.Y(), loc.Z()))
        samples = []
        for edge in face.edges():
            for t in (0.0, 0.5, 1.0):
                p = edge.position_at(t)
                rel = (p.X - foot[0], p.Y - foot[1], p.Z - foot[2])
                along = sum(a * b for a, b in zip(rel, d))
                samples.append((along, math.sqrt(max(0.0, sum(c * c for c in rel) - along * along))))
        if samples:
            found.setdefault(_line_key(d, foot), []).append(
                (min(a for a, _ in samples), max(a for a, _ in samples),
                 min(r for _, r in samples), max(r for _, r in samples)))
    return found


def _bridge_fillets(bores: list[_Segment], tori: list[tuple[float, float, float, float]]) -> None:
    """Close the gap a fillet leaves between two steps of one hole: a counterbore
    whose floor is filleted into its wall stops short of the floor, and its wall
    and the bore below would read as two holes. The step the fillet rounds into
    is taken down to the floor, as the callout's depth measures it."""
    cylinders = [s for s in bores if s.kind == "cyl"]
    for lo, hi, r_min, r_max in tori:
        for a in cylinders:
            for b in cylinders:
                if a is b or abs(a.hi - lo) > 1e-6 or abs(b.lo - hi) > 1e-6 or abs(a.r_lo - b.r_lo) < _TOUCH:
                    continue
                wide, narrow = (a, b) if a.r_lo > b.r_lo else (b, a)
                grown = (wide if abs(r_max - wide.r_lo) < 1e-6 else narrow if abs(r_min - narrow.r_lo) < 1e-6
                         else None)
                if grown is None:
                    continue
                if grown is a:
                    a.hi = hi
                else:
                    b.lo = lo


def _steps(segments, narrowest: float) -> list[_Segment]:
    """The steps an end of a hole opens out in, from that end inward to the bore."""
    out = []
    for seg in segments:
        if seg.kind == "cyl" and abs(seg.r_lo - narrowest) < _TOUCH:
            break
        out.append(seg)
    return out


def holes(shape) -> list[Hole]:
    """Every hole in ``shape``, read off its faces, in a deterministic order."""
    from build123d import Vector

    found: list[Hole] = []
    ray = None
    tori = None
    for key, (d, foot, segments) in _surface_segments(shape).items():
        u, v = _perpendicular(d)

        def at(a: float, x: float = 0.0, y: float = 0.0):
            return Vector(*(f + a * c + x * cu + y * cv for f, c, cu, cv in zip(foot, d, u, v)))

        def air(a: float, radius: float) -> bool:
            """Is the disc of ``radius`` square to the axis at ``a`` all air? A bore
            is; an O-ring groove or a pocket around a standoff has material inside."""
            samples = [(0.0, 0.0)] + [(radius * f * math.cos(t), radius * f * math.sin(t))
                                      for f in (0.45, 0.85) for t in (0.3, 2.4, 4.5)]
            return not any(shape.is_inside(at(a, x, y)) for x, y in samples)

        bores = [s for s in _merge_split_faces(segments) if s.concave and _full(s)]
        if tori is None:
            tori = _tori(shape)
        _bridge_fillets(bores, tori.get(key, []))
        groups: list[list[list[_Segment]]] = []
        for chain in _chains(bores):
            # Two pieces of one bore with air between them -- a clevis's two arms,
            # a bore broken through by a cross hole or a slot -- are one hole.
            last = groups[-1][-1] if groups else None
            if (last is not None and abs(last[-1].r_hi - chain[0].r_lo) < _TOUCH
                    and all(not shape.is_inside(at(last[-1].hi + (chain[0].lo - last[-1].hi) * f))
                            for f in (0.1, 0.5, 0.9))):
                groups[-1].append(chain)
            else:
                groups.append([chain])
        for group in groups:
            ray = ray or _Ray(shape)
            hole = _read_chain([seg for chain in group for seg in chain], d, foot, at, air, ray)
            if hole == "sealed" and len(group) > 1:
                # Closed at both ends, the pieces are not one bore drilled through
                # air: two blind holes facing each other across a gap (into the
                # two walls of a channel) are each their own.
                for chain in group:
                    piece = _read_chain(chain, d, foot, at, air, ray)
                    if isinstance(piece, Hole):
                        found.append(piece)
            elif isinstance(hole, Hole):
                found.append(hole)
    found.sort(key=lambda h: (h.signature(), h.axis, h.mouth))
    return found


def _read_chain(chain: list[_Segment], d, foot, at, air, ray: _Ray) -> "Hole | str | None":
    """One run of bore segments on a line as a hole: None when it is not one (no
    bore, material inside, a conical recess), ``"sealed"`` when it is closed at
    both ends."""
    cylinders = [s for s in chain if s.kind == "cyl"]
    if not cylinders:
        return None  # a conical recess with no bore is not a drilled hole
    longest = max(cylinders, key=lambda s: s.hi - s.lo)
    if not air((longest.lo + longest.hi) / 2, longest.r_lo):
        return None
    lo, hi = chain[0].lo, chain[-1].hi
    narrowest = min(s.r_lo for s in cylinders)
    open_lo = ray.open(tuple(at(lo - _PROBE)), tuple(-c for c in d), 2 * narrowest)
    open_hi = ray.open(tuple(at(hi + _PROBE)), d, 2 * narrowest)
    if not (open_lo or open_hi):
        return "sealed"  # a sealed void, not something a drill makes
    thru = open_lo and open_hi
    # The mouth: a blind hole's open end; a through hole's counterbored or
    # countersunk end, else its end at the larger coordinate.
    if thru:
        lo_wide = chain[0].r_lo > narrowest + _TOUCH
        hi_wide = chain[-1].r_hi > narrowest + _TOUCH
        from_hi = hi_wide or not lo_wide
    else:
        from_hi = open_hi
    ordered = list(reversed(chain)) if from_hi else list(chain)
    mouth_at = hi if from_hi else lo
    axis = tuple(-c for c in d) if from_hi else d

    def from_mouth(position: float) -> float:
        return abs(position - mouth_at)

    def widening(seg: _Segment, *, at_mouth: bool) -> tuple | None:
        """The counterbore or countersink a chain's end segment makes, if any."""
        outer_at_hi = from_hi if at_mouth else not from_hi
        outer = seg.r_hi if outer_at_hi else seg.r_lo
        if outer <= narrowest + _TOUCH:
            return None
        if seg.kind == "cone":
            inner = seg.r_lo if outer_at_hi else seg.r_hi
            spread = math.degrees(2 * math.atan2(outer - inner, seg.hi - seg.lo))
            return ("csk", (2 * outer, round(spread, 1)))
        return ("cbore", (2 * outer, seg.hi - seg.lo))

    def described(steps: list[_Segment]) -> str:
        return ", then ".join(
            f"a cone ⌀{2 * max(s.r_lo, s.r_hi):g} to ⌀{2 * min(s.r_lo, s.r_hi):g}" if s.kind == "cone"
            else f"a bore ⌀{2 * s.r_lo:g} for {s.hi - s.lo:g}" for s in steps)

    problems = []
    mouth_steps = _steps(ordered, narrowest)
    far_steps = _steps(list(reversed(ordered)), narrowest) if thru else []
    for name, steps in (("mouth", mouth_steps), ("far end", far_steps)):
        if len(steps) > 1:
            problems.append(f"its {name} opens out in {len(steps)} steps ({described(steps)})")
    mouth_end = widening(mouth_steps[0], at_mouth=True) if len(mouth_steps) == 1 else None
    far_end = widening(far_steps[0], at_mouth=False) if len(far_steps) == 1 and len(ordered) > 1 else None
    depth = None
    if not thru:
        # From the mouth to the bottom of the deepest full-diameter stretch: a
        # groove partway down does not end the hole, a drill point does not
        # count.
        deepest = [s for s in ordered if s.kind == "cyl" and abs(s.r_lo - narrowest) < _TOUCH][-1]
        depth = max(from_mouth(deepest.lo), from_mouth(deepest.hi))
    mouth = tuple(f + mouth_at * c for f, c in zip(foot, d))
    return Hole(
        mouth=_tidy(mouth), axis=_tidy(axis), diameter=2 * narrowest, thru=thru, depth=depth,
        cbore=mouth_end[1] if mouth_end and mouth_end[0] == "cbore" else None,
        csk=mouth_end[1] if mouth_end and mouth_end[0] == "csk" else None,
        far_cbore=far_end[1] if far_end and far_end[0] == "cbore" else None,
        far_csk=far_end[1] if far_end and far_end[0] == "csk" else None,
        length=hi - lo, problem="; ".join(problems) or None,
    )


def axes(shape) -> list[Axis]:
    """The axis of every turned feature -- a full cylinder or cone, bore or boss --
    spanning the stretch of the line the part's turned faces occupy. Features
    that share a line and touch or overlap (a stepped shaft, a counterbored hole)
    are one axis."""
    found: list[Axis] = []
    for d, foot, segments in _surface_segments(shape).values():
        full = [s for s in _merge_split_faces(segments) if _full(s)]
        if not any(s.kind == "cyl" for s in full):
            continue  # a chamfer alone does not make a turned feature
        spans: list[list[float]] = []
        for seg in sorted(full, key=lambda s: s.lo):
            if spans and seg.lo <= spans[-1][1] + _TOUCH:
                spans[-1][1] = max(spans[-1][1], seg.hi)
                spans[-1][2] = max(spans[-1][2], seg.r_lo, seg.r_hi)
            else:
                spans.append([seg.lo, seg.hi, max(seg.r_lo, seg.r_hi)])
        for lo, hi, radius in spans:
            found.append(Axis(start=_tidy(tuple(f + lo * c for f, c in zip(foot, d))),
                              end=_tidy(tuple(f + hi * c for f, c in zip(foot, d))), radius=round(radius, 9)))
    found.sort(key=lambda a: (a.start, a.end))
    return found


def slots(shape) -> list[Slot]:
    """Every obround slot in ``shape``: two concave half cylinders of one radius,
    on parallel axes over the same stretch, each open toward the other, with air
    all along the gap between them. Ends are paired nearest first, so three slots
    in a row stay three. Pairs stacked on one centre line make one slot with a
    counterbore, and a chamfer at an end belongs to the slot's depth. Through
    when it is open past both ends (see :class:`_Ray`)."""
    from build123d import Vector

    halves, cones = [], []
    for d, foot, segments in _surface_segments(shape).values():
        for seg in _merge_split_faces(segments):
            if seg.concave and abs(seg.span - math.pi) < 1e-3:
                (halves if seg.kind == "cyl" else cones).append((d, foot, seg))

    def point(foot, d, t: float) -> tuple:
        return tuple(f + t * c for f, c in zip(foot, d))

    candidates = []
    for i, (d, foot_a, a) in enumerate(halves):
        for j in range(i + 1, len(halves)):
            d_b, foot_b, b = halves[j]
            if any(abs(x - y) > 1e-6 for x, y in zip(d, d_b)):
                continue
            if abs(a.r_lo - b.r_lo) > _TOUCH or abs(a.lo - b.lo) > _TOUCH or abs(a.hi - b.hi) > _TOUCH:
                continue
            between = tuple(y - x for x, y in zip(foot_a, foot_b))
            gap = math.sqrt(sum(c * c for c in between))
            if gap < _TOUCH:
                continue
            toward = tuple(c / gap for c in between)
            # Each end opens toward the other: its face bulges away from it.
            if sum(x * y for x, y in zip(a.bulge, toward)) > -0.99 or sum(x * y for x, y in zip(b.bulge, toward)) < 0.99:
                continue
            candidates.append((round(gap, 9), i, j, between))
    pairs = []
    used: set[int] = set()
    for gap, i, j, between in sorted(candidates):
        if i in used or j in used:
            continue
        d, foot_a, a = halves[i]
        mid = (a.lo + a.hi) / 2
        # Air all along the gap, not just at its middle: two notches facing each
        # other across a part are not a slot.
        if any(shape.is_inside(Vector(*point(tuple(f + t * c for f, c in zip(foot_a, between)), d, mid)))
               for t in (0.02, 0.25, 0.5, 0.75, 0.98)):
            continue
        used.update((i, j))
        middle = tuple(f + c / 2 for f, c in zip(foot_a, between))
        toward = _canonical(tuple(c / gap for c in between), (0.0, 0.0, 0.0))[0]
        pairs.append({"d": d, "middle": _canonical(d, middle)[1], "toward": toward, "lo": a.lo, "hi": a.hi,
                      "r": a.r_lo, "gap": gap, "feet": (foot_a, halves[j][1])})

    # Pairs stacked on one centre line, touching end to end, are one slot.
    lines: dict[tuple, list] = {}
    for pair in pairs:
        key = _line_key(pair["d"], pair["middle"]) + tuple(round(c, 4) for c in pair["toward"])
        lines.setdefault(key, []).append(pair)
    ray = _Ray(shape) if pairs else None
    found: list[Slot] = []
    for stack in lines.values():
        stack.sort(key=lambda p: p["lo"])
        chains: list[list] = []
        for pair in stack:
            if chains and abs(chains[-1][-1]["hi"] - pair["lo"]) < _TOUCH:
                chains[-1].append(pair)
            else:
                chains.append([pair])
        for chain in chains:
            d, middle = chain[0]["d"], chain[0]["middle"]
            lo, hi = chain[0]["lo"], chain[-1]["hi"]
            # A chamfer at either end runs on the end arcs' own axes: half cones
            # touching the straight wall. The slot's depth includes them.
            end_lines = {_line_key(*_canonical(d, f)) for f in chain[0]["feet"] + chain[-1]["feet"]}
            for cd, cfoot, cone in cones:
                if _line_key(*_canonical(cd, cfoot)) not in end_lines:
                    continue
                if abs(cone.hi - lo) < _TOUCH:
                    lo = cone.lo
                elif abs(cone.lo - hi) < _TOUCH:
                    hi = cone.hi
            narrow = min(chain, key=lambda p: p["r"])
            # Open along its whole length, not just at its middle: a blind slot with
            # a hole through its floor is open where the hole is.
            feet = [_canonical(d, f)[1] for f in narrow["feet"]]
            along = [tuple(a + t * (b - a) for a, b in zip(*feet)) for t in (0.0, 0.25, 0.5, 0.75, 1.0)]
            open_lo = all(ray.open(point(c, d, lo - _PROBE), tuple(-k for k in d), 2 * narrow["r"]) for c in along)
            open_hi = all(ray.open(point(c, d, hi + _PROBE), d, 2 * narrow["r"]) for c in along)
            if not (open_lo or open_hi):
                continue
            thru = open_lo and open_hi
            wide_hi = chain[-1]["r"] > narrow["r"] + _TOUCH
            wide_lo = chain[0]["r"] > narrow["r"] + _TOUCH
            from_hi = (wide_hi or not wide_lo) if thru else open_hi
            mouth_at = hi if from_hi else lo
            axis = tuple(-c for c in d) if from_hi else d
            mouth_pair = chain[-1] if from_hi else chain[0]
            cbore = None
            if mouth_pair is not narrow and mouth_pair["r"] > narrow["r"] + _TOUCH:
                cbore = (2 * mouth_pair["r"], mouth_pair["gap"] + 2 * mouth_pair["r"],
                         abs(mouth_at - (mouth_pair["lo"] if from_hi else mouth_pair["hi"])))
            depth = None
            if not thru:
                # A blind slot is as deep as its floor on the centre line: a floor
                # fillet or a ball end runs on below where the straight wall stops.
                # Along the centre line, the floor's least depth: a hole in it
                # runs deeper, or right through, where it is.
                depths = [found for found in (ray.depth(point(c, d, mouth_at), axis) for c in along)
                          if found is not None]
                depth = min(depths) if depths else None
                if depth is None:
                    deepest = [p for p in chain if abs(p["r"] - narrow["r"]) < _TOUCH]
                    depth = abs(mouth_at - (deepest[0]["lo"] if from_hi else deepest[-1]["hi"]))
            ends = tuple(_tidy(point(_canonical(d, f)[1], d, mouth_at)) for f in narrow["feet"])
            found.append(Slot(
                mouth=_tidy(point(middle, d, mouth_at)), axis=_tidy(axis), direction=_tidy(narrow["toward"]),
                ends=(ends[0], ends[1]), width=2 * narrow["r"], length=narrow["gap"] + 2 * narrow["r"],
                thru=thru, depth=depth, run=hi - lo, cbore=cbore,
            ))
    found.sort(key=lambda sl: (sl.signature(), sl.axis, sl.mouth))
    return found


def bolt_circles(shape, found: list[Hole] | None = None) -> list[BoltCircle]:
    """Identical holes, three or more, opening the same way, equally spaced on a
    circle whose centre lies on a turned axis of the part (a bore, a boss, the
    part's own outside). The turned axis is what makes it a bolt circle rather than
    a pattern a rectangular plate happens to make: four corner holes on a square
    are equally spaced too, and are dimensioned as pitches."""
    found = holes(shape) if found is None else found
    surfaces = list(_surface_segments(shape).values())
    lines = [(d, foot) for d, foot, segments in surfaces
             if any(s.kind == "cyl" and _full(s) for s in _merge_split_faces(segments))]
    # The outside radius of every turned surface round each line.
    outside: dict[tuple, float] = {}
    for d, foot, segments in surfaces:
        for seg in _merge_split_faces(segments):
            if seg.kind == "cyl" and _full(seg) and not seg.concave:
                key = _line_key(d, foot)
                outside[key] = max(outside.get(key, 0.0), seg.r_lo)
    groups: dict[tuple, list[Hole]] = {}
    for hole in found:
        groups.setdefault((hole.signature(), hole.axis), []).append(hole)
    circles: list[BoltCircle] = []
    for (_sig, axis), members in groups.items():
        if len(members) < 3:
            continue
        u, v = _perpendicular(axis)
        centre = tuple(sum(h.mouth[k] for h in members) / len(members) for k in range(3))
        polar = []
        for hole in members:
            rel = tuple(m - c for m, c in zip(hole.mouth, centre))
            x, y = sum(a * b for a, b in zip(rel, u)), sum(a * b for a, b in zip(rel, v))
            along = sum(a * b for a, b in zip(rel, axis))
            polar.append((math.atan2(y, x) % (2 * math.pi), math.hypot(x, y), along))
        radius = sum(r for _a, r, _z in polar) / len(polar)
        if radius < _TOUCH or any(abs(r - radius) > 1e-3 or abs(z) > 1e-3 for _a, r, z in polar):
            continue
        angles = sorted(a for a, _r, _z in polar)
        step = 2 * math.pi / len(angles)
        gaps = [(b - a) for a, b in zip(angles, angles[1:] + [angles[0] + 2 * math.pi])]
        if any(abs(g - step) > 1e-3 for g in gaps):
            continue
        d, foot = _canonical(axis, centre)
        if not any(all(abs(x - y) < 1e-6 for x, y in zip(d, line_d))
                   and math.dist(foot, line_foot) < 1e-3 for line_d, line_foot in lines):
            continue
        # Four holes equally spaced are also the corners of a square, and on a
        # square plate (a motor mount round its bore) they are dimensioned as
        # pitches. Only a round part -- a turned outside enclosing them -- makes
        # four a bolt circle.
        if len(members) == 4 and outside.get(_line_key(d, foot), 0.0) < radius:
            continue
        circles.append(BoltCircle(centre=_tidy(centre), axis=axis, diameter=2 * radius,
                                  mouths=tuple(h.mouth for h in members)))
    circles.sort(key=lambda c: (round(c.diameter, 3), c.axis, c.centre))
    return circles


@dataclass(frozen=True)
class Turned:
    """A turned outside surface -- a shaft's step, a boss -- by diameter, with the
    direction of its axis and the point on the axis midway along it."""

    diameter: float
    axis: tuple[float, float, float]
    middle: tuple[float, float, float]


def turned_surfaces(shape) -> list[Turned]:
    """The part's turned outside surfaces, one per diameter (the first found where
    two steps share one), smallest first."""
    found: dict[float, Turned] = {}
    for d, foot, segments in _surface_segments(shape).values():
        for seg in _merge_split_faces(segments):
            if seg.kind == "cyl" and not seg.concave and _full(seg):
                middle = (seg.lo + seg.hi) / 2
                diameter = round(2 * seg.r_lo, 6)
                found.setdefault(diameter, Turned(diameter, d, _tidy(tuple(f + middle * c for f, c in zip(foot, d)))))
    return [found[d] for d in sorted(found)]


@dataclass(frozen=True)
class Revolved:
    """A part turned whole about a principal axis (0 X, 1 Y, 2 Z): every face a
    surface of revolution on one line along it, or a plane square to it. Such a
    part draws the same picture from every side of its axis. ``diameter`` is its
    largest, at ``at`` on the axis."""

    axis: int
    diameter: float
    at: tuple[float, float, float]


def revolved(shape, *, bores: bool = False) -> Revolved | None:
    """How a part is turned whole about a principal axis, or None if it is not.
    ``bores=True`` leaves out what is drilled across the axis after turning (a
    cross hole, a cotter hole, and a blind one's flat bottom): such a part is
    still turned, though its views from the side are not all alike."""
    from build123d import GeomType
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_Cone, GeomAbs_Cylinder, GeomAbs_Plane, GeomAbs_Sphere, GeomAbs_Torus

    across: dict[tuple, tuple] = {}  # the bores drilled across: line key -> (direction, foot, radius)
    if bores:
        lines = _surface_segments(shape)
        outside = [key for key, (_d, _foot, segments) in lines.items() if any(not s.concave for s in segments)]
        if len(outside) == 1:
            across = {key: (d, foot, max(max(s.r_lo, s.r_hi) for s in segments))
                      for key, (d, foot, segments) in lines.items()
                      if key != outside[0] and all(s.concave for s in segments)}
    line = None
    normals = []
    for face in shape.faces():
        surface = BRepAdaptor_Surface(face.wrapped)
        kind = surface.GetType()
        if kind == GeomAbs_Plane:
            n = surface.Plane().Axis().Direction()
            normal = (n.X(), n.Y(), n.Z())
            if not any(_bottom_of(face, normal, bore) for bore in across.values()):
                normals.append(normal)
            continue
        if kind == GeomAbs_Cylinder:
            ax = surface.Cylinder().Axis()
        elif kind == GeomAbs_Cone:
            ax = surface.Cone().Axis()
        elif kind == GeomAbs_Torus:
            ax = surface.Torus().Axis()
        elif kind == GeomAbs_Sphere:
            ax = surface.Sphere().Position().Axis()
        else:
            return None
        loc, direction = ax.Location(), ax.Direction()
        d, foot = _canonical((direction.X(), direction.Y(), direction.Z()), (loc.X(), loc.Y(), loc.Z()))
        key = _line_key(d, foot)
        if kind == GeomAbs_Sphere:
            continue  # a sphere turns about any line through its centre: checked below
        if key in across:
            continue  # drilled across the axis
        if line is None:
            line = (key, d, foot)
        elif key != line[0]:
            return None
    if line is None:
        return None
    _key, d, foot = line
    axis = next((k for k in range(3) if abs(abs(d[k]) - 1) < 1e-6), None)
    if axis is None or any(abs(abs(n[axis]) - 1) > 1e-6 for n in normals):
        return None
    largest, at = 0.0, foot
    for edge in shape.edges():
        if edge.geom_type != GeomType.CIRCLE:
            continue
        c = edge.arc_center
        rel = (c.X - foot[0], c.Y - foot[1], c.Z - foot[2])
        along = sum(a * b for a, b in zip(rel, d))
        if math.dist(rel, tuple(along * x for x in d)) > _TOUCH:
            continue  # a torus's seam arc; a cross hole would have failed on its surface
        if edge.radius > largest:
            largest, at = edge.radius, _tidy((c.X, c.Y, c.Z))
    return Revolved(axis, round(2 * largest, 6), at) if largest else None


def _bottom_of(face, normal, bore) -> bool:
    """Whether a flat face is the bottom of a bore drilled across the axis: square
    to the bore, and within its radius of the bore's axis."""
    d, foot, radius = bore
    if abs(abs(sum(a * b for a, b in zip(normal, d))) - 1) > 1e-6:
        return False
    rel = [c - f for c, f in zip(face.center(), foot)]
    along = sum(a * b for a, b in zip(rel, d))
    return math.dist(rel, [along * c for c in d]) <= radius + _TOUCH


def turned_diameters(shape) -> list[float]:
    """The diameters of the part's turned outside surfaces, which a drawing must
    state as surely as it states a hole."""
    return [t.diameter for t in turned_surfaces(shape)]


def mirror_symmetric(shape, axis: int) -> bool:
    """Whether a part is its own mirror image about the plane square to model
    ``axis`` through the middle of its extent. Its faces, mirrored, are looked
    for among its own first; where the faces are split differently on the two
    sides, the part and its mirror are compared as solids: what one has and the
    other lacks is a feature if any piece of it is thicker than ``_SLIVER``
    (twice its volume over its area), and only the slivers a boolean leaves
    along faces both share are not. A share of the part's volume would not do:
    one off-centre ⌀2 hole is a few millionths of a large plate."""
    from build123d import Plane, Vector

    box = shape.bounding_box()
    middle = (tuple(box.min)[axis] + tuple(box.max)[axis]) / 2

    def signature(face, flip: bool) -> tuple:
        centre = list(face.center())
        if flip:
            centre[axis] = 2 * middle - centre[axis]
        return (str(face.geom_type), round(face.area, 2), *(round(c, 2) + 0.0 for c in centre))

    faces = shape.faces()
    if sorted(signature(f, False) for f in faces) == sorted(signature(f, True) for f in faces):
        return True
    normal = [0.0, 0.0, 0.0]
    normal[axis] = 1.0
    origin = list(box.center())
    origin[axis] = middle
    mirrored = shape.mirror(Plane(origin=Vector(*origin), z_dir=Vector(*normal)))
    return not any(2 * piece.volume > _SLIVER * piece.area for piece in (shape - mirrored).solids())


@dataclass(frozen=True)
class Taper:
    """A turned cone that is part of the shape, not a chamfer: its diameters at
    each end, and the point on its axis at each end (small end first)."""

    small: float
    large: float
    ends: tuple[tuple[float, float, float], tuple[float, float, float]]
    axis: tuple[float, float, float]


def tapers(shape) -> list[Taper]:
    """The part's outside tapers: full convex cones between two diameters that
    are not chamfers bevelling an edge (a chamfer is its note's)."""
    found = []
    for d, foot, segments in _surface_segments(shape).values():
        line = _merge_split_faces(segments)
        for seg in line:
            if seg.kind != "cone" or seg.concave or not _full(seg) or _cone_bevel(seg, line):
                continue
            if min(seg.r_lo, seg.r_hi) < 1e-6:
                continue  # a point is a cone's tip, not a diameter
            ends = [tuple(f + t * c for f, c in zip(foot, d)) for t in (seg.lo, seg.hi)]
            small, large = sorted((2 * seg.r_lo, 2 * seg.r_hi))
            if seg.r_lo > seg.r_hi:
                ends.reverse()
            found.append(Taper(round(small, 6), round(large, 6), (_tidy(ends[0]), _tidy(ends[1])), d))
    return found


@dataclass(frozen=True)
class Groove:
    """A turned groove: a torus cut round a turned surface, not a fillet. Its
    section radius, the point on its axis at its middle, and ``ring``, the radius
    of the circle its section's centre runs round."""

    radius: float
    middle: tuple[float, float, float]
    axis: tuple[float, float, float]
    ring: float


def grooves(shape) -> list[Groove]:
    """The part's turned grooves: concave toroidal faces that are not blends
    rounding a corner (a fillet is its note's)."""
    from build123d import Vector
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_Torus

    rounded = [Vector(*b.point) for b in blends(shape)]
    found = []
    for face in shape.faces():
        surface = BRepAdaptor_Surface(face.wrapped)
        if surface.GetType() != GeomAbs_Torus:
            continue
        if any(_distance_to_face(face.wrapped, p) < 1e-6 for p in rounded):
            continue
        torus = surface.Torus()
        ax = torus.Axis()
        loc, direction = ax.Location(), ax.Direction()
        middle = (loc.X(), loc.Y(), loc.Z())
        d = (direction.X(), direction.Y(), direction.Z())
        # A groove's surface faces into the ring its section's centre runs round
        # (the air is in the torus); a bead's faces out of it.
        point = face.position_at(0.5, 0.5)
        normal = face.normal_at(point)
        rel = [p - m for p, m in zip(point, middle)]
        radial = [r - sum(a * b for a, b in zip(rel, d)) * c for r, c in zip(rel, d)]
        reach = math.sqrt(sum(c * c for c in radial)) or 1.0
        centre = [m + torus.MajorRadius() * c / reach for m, c in zip(middle, radial)]
        if sum(n * (c - p) for n, c, p in zip(normal, centre, point)) <= 0:
            continue
        groove = Groove(round(torus.MinorRadius(), 6), _tidy(middle), d, round(torus.MajorRadius(), 6))
        if groove not in found:
            found.append(groove)
    return found


@dataclass(frozen=True)
class Blend:
    """A fillet (``concave``: an inside corner rounded) or a round (an outside edge
    rounded), by radius; ``point`` is on its face."""

    radius: float
    concave: bool
    point: tuple[float, float, float]


@dataclass(frozen=True)
class Chamfer:
    """A bevelled outside edge: ``legs`` are its two lengths along the faces it
    joins, equal for a 45-degree chamfer; ``point`` is on its face."""

    legs: tuple[float, float]
    point: tuple[float, float, float]

    @property
    def symmetric(self) -> bool:
        return abs(self.legs[0] - self.legs[1]) < 1e-3


#: Two faces whose normals differ by less than this meet tangent: a blend's edge.
_TANGENT = math.cos(math.radians(2.0))
#: A chamfer is a bevel, not a face: no leg longer than this, and its strip at
#: most this share of its length.
_CHAMFER_MAX = 15.0
_CHAMFER_SHARE = 0.25


def _edge_faces(shape):
    from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE
    from OCP.TopExp import TopExp
    from OCP.collections import IndexedDataMap_TopoDS_Shape_List_TopoDS_Shape_TopTools_ShapeMapHasher

    found = IndexedDataMap_TopoDS_Shape_List_TopoDS_Shape_TopTools_ShapeMapHasher()
    TopExp.MapShapesAndAncestors_s(shape.wrapped, TopAbs_EDGE, TopAbs_FACE, found)
    return found


def _others(found, edge, face) -> list:
    """The faces other than ``face`` that share ``edge``."""
    from build123d.topology.shape_core import downcast

    if not found.Contains(edge.wrapped):
        return []
    return [downcast(f) for f in found.FindFromKey(edge.wrapped) if not f.IsSame(face.wrapped)]


def _normal(face, point) -> tuple | None:
    """A face's outward normal at a point on (or nearest) it."""
    from OCP.BRep import BRep_Tool
    from OCP.BRepGProp import BRepGProp_Face
    from OCP.GeomAPI import GeomAPI_ProjectPointOnSurf
    from OCP.gp import gp_Pnt, gp_Vec

    project = GeomAPI_ProjectPointOnSurf(gp_Pnt(*point), BRep_Tool.Surface_s(face))
    if project.NbPoints() == 0:
        return None
    u, v = project.LowerDistanceParameters()
    at, n = gp_Pnt(), gp_Vec()
    BRepGProp_Face(face).Normal(u, v, at, n)
    size = n.Magnitude()
    return None if size < 1e-12 else (n.X() / size, n.Y() / size, n.Z() / size)


def _surface_key(face) -> tuple | None:
    """Which cylinder or torus a face lies on: its kind, axis line and radii."""
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_Cylinder, GeomAbs_Torus

    surface = BRepAdaptor_Surface(face)
    kind = surface.GetType()
    if kind == GeomAbs_Cylinder:
        gp = surface.Cylinder()
        radii = (round(gp.Radius(), 4),)
    elif kind == GeomAbs_Torus:
        gp = surface.Torus()
        radii = (round(gp.MajorRadius(), 4), round(gp.MinorRadius(), 4))
    else:
        return None
    ax = gp.Axis()
    d, foot = _canonical((ax.Direction().X(), ax.Direction().Y(), ax.Direction().Z()),
                         (ax.Location().X(), ax.Location().Y(), ax.Location().Z()))
    return ("cyl" if kind == GeomAbs_Cylinder else "torus",) + _line_key(d, foot) + radii


def _blend_faces(shape) -> list[tuple]:
    """Each blend face of the part with what it is, as ``(face, Blend)``."""
    from OCP.BRepTools import BRepTools

    found = _edge_faces(shape)
    keyed = [(face, _surface_key(face.wrapped)) for face in shape.faces()]
    spans: dict[tuple, float] = {}
    for face, key in keyed:
        if key is not None and key[0] == "cyl":
            u0, u1, _v0, _v1 = BRepTools.UVBounds_s(face.wrapped)
            spans[key] = spans.get(key, 0.0) + (u1 - u0)
    slot_ends = set()
    for slot in slots(shape):
        for end in slot.ends:
            d, foot = _canonical(slot.axis, end)
            slot_ends.add(("cyl",) + _line_key(d, foot) + (round(slot.width / 2, 4),))
    out = []
    for face, key in keyed:
        if key is None or key in slot_ends or (key[0] == "cyl" and spans[key] >= 2 * math.pi - 1e-6):
            continue
        tangent = _tangent_neighbours(found, face, key)
        if len(tangent) < 2:
            continue
        if key[0] == "cyl" and _full_round_end(face, tangent):
            continue
        out.append((face, _blend_of(face)))
    return out


def _tangent_neighbours(found, face, key) -> list:
    """The faces that meet ``face`` tangent along an edge, other than pieces of its
    own surface."""
    tangent: list = []
    for edge in face.edges():
        middle = edge.position_at(0.5)
        point = (middle.X, middle.Y, middle.Z)
        mine = _normal(face.wrapped, point)
        for other in _others(found, edge, face):
            if _surface_key(other) == key or any(other.IsSame(t) for t in tangent):
                continue
            theirs = _normal(other, point)
            if mine and theirs and sum(a * b for a, b in zip(mine, theirs)) > _TANGENT:
                tangent.append(other)
    return tangent


def _full_round_end(face, tangent: list) -> bool:
    """Whether a half cylinder between two parallel flat faces facing apart is the
    rounded end of a notch or a link, the whole width of the feature, rather than
    a blend of a corner."""
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.BRepTools import BRepTools
    from OCP.GeomAbs import GeomAbs_Plane

    u0, u1, _v0, _v1 = BRepTools.UVBounds_s(face.wrapped)
    if abs((u1 - u0) - math.pi) > 1e-3 or len(tangent) != 2:
        return False
    normals = []
    for other in tangent:
        surface = BRepAdaptor_Surface(other)
        if surface.GetType() != GeomAbs_Plane:
            return False
        axis = surface.Plane().Axis().Direction()
        flip = -1.0 if other.Orientation() == 1 else 1.0  # TopAbs_REVERSED
        normals.append((axis.X() * flip, axis.Y() * flip, axis.Z() * flip))
    return sum(a * b for a, b in zip(*normals)) < -1 + 1e-6


def _blend_of(face) -> Blend:
    """A blend face's radius, and whether it rounds an inside corner."""
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_Cylinder

    surface = BRepAdaptor_Surface(face.wrapped)
    at = face.position_at(0.5, 0.5)
    n = face.normal_at(at)
    if surface.GetType() == GeomAbs_Cylinder:
        gp = surface.Cylinder()
        ax = gp.Axis()
        d, foot = _canonical((ax.Direction().X(), ax.Direction().Y(), ax.Direction().Z()),
                             (ax.Location().X(), ax.Location().Y(), ax.Location().Z()))
        rel = (at.X - foot[0], at.Y - foot[1], at.Z - foot[2])
        along = sum(a * b for a, b in zip(rel, d))
        centre = tuple(f + along * k for f, k in zip(foot, d))
        radius = gp.Radius()
    else:
        gp = surface.Torus()
        ax = gp.Axis()
        d = (ax.Direction().X(), ax.Direction().Y(), ax.Direction().Z())
        o = (ax.Location().X(), ax.Location().Y(), ax.Location().Z())
        rel = (at.X - o[0], at.Y - o[1], at.Z - o[2])
        along = sum(a * b for a, b in zip(rel, d))
        radial = tuple(c - along * k for c, k in zip(rel, d))
        reach = math.sqrt(sum(c * c for c in radial)) or 1.0
        centre = tuple(oo + along * k + gp.MajorRadius() * c / reach for oo, k, c in zip(o, d, radial))
        radius = gp.MinorRadius()
    # Concave when the outward normal points at the circle's centre: the air is
    # on the inside of the curve, an inside corner rounded.
    toward = tuple(c - p for c, p in zip(centre, (at.X, at.Y, at.Z)))
    concave = sum(a * b for a, b in zip(toward, (n.X, n.Y, n.Z))) > 0
    return Blend(round(radius, 6), concave, (at.X, at.Y, at.Z))


def blends(shape) -> list[Blend]:
    """The part's fillets and rounds: each cylinder or torus face, not a whole
    turned surface, that meets two other faces tangent along its edges. A slot's
    rounded end is tangent to the slot's sides too, and is the slot's; the
    rounded end of a notch or a link, as wide as the feature, is its end."""
    return [blend for _face, blend in _blend_faces(shape)]


def _strip_chamfer(face, found) -> Chamfer | None:
    """A flat face that is a chamfer: a narrow strip between two faces that meet
    square, bevelling their outside corner."""
    from build123d import GeomType

    if face.geom_type != GeomType.PLANE:
        return None
    lines = sorted((e for e in face.edges() if e.geom_type == GeomType.LINE), key=lambda e: -e.length)
    pair = None
    for i, a in enumerate(lines):
        da = (a.position_at(1) - a.position_at(0)).normalized()
        for b in lines[i + 1:]:
            if abs(abs(da.dot((b.position_at(1) - b.position_at(0)).normalized())) - 1) < 1e-6:
                pair = (a, b)
                break
        if pair:
            break
    if pair is None:
        return None
    a, b = pair
    along = (a.position_at(1) - a.position_at(0)).normalized()
    gap = b.position_at(0.5) - a.position_at(0.5)
    width = (gap - along * gap.dot(along)).length
    if not (1e-6 < width <= _CHAMFER_SHARE * min(a.length, b.length)) or width > _CHAMFER_MAX * math.sqrt(2):
        return None
    mine = _normal(face.wrapped, tuple(a.position_at(0.5)))
    sides = []
    for edge in (a, b):
        others = _others(found, edge, face)
        sides.append(_normal(others[0], tuple(edge.position_at(0.5))) if len(others) == 1 else None)
    if mine is None or None in sides:
        return None
    n1, n2 = sides

    def dot(p, q) -> float:
        return sum(x * y for x, y in zip(p, q))

    if abs(dot(n1, n2)) > 1e-3 or dot(mine, n1) <= 1e-3 or dot(mine, n2) <= 1e-3:
        return None
    # An outside corner's bevel runs from one face back away from its outward
    # normal to the other; a bevel of an inside corner (a 45° fillet's stand-in)
    # runs out along it, and is no chamfer: a general note of fillets over it
    # would ask for a radius the corner does not have.
    if dot(tuple(gap), n1) >= 0:
        return None
    legs = (width * dot(mine, n1), width * dot(mine, n2))
    if max(legs) > _CHAMFER_MAX:
        return None
    at = face.position_at(0.5, 0.5)
    return Chamfer((round(legs[0], 6), round(legs[1], 6)), (at.X, at.Y, at.Z))


def _cone_bevel(seg: _Segment, line: list[_Segment]) -> bool:
    """Whether a turned cone is a chamfer: convex, short, between 15 and 75
    degrees, stopping short of its axis (a cone that reaches it is a point), and
    bevelling the end of a cylinder of its larger radius on the same axis (a cone
    that is the whole side of a part is its shape, not a chamfer). ``line`` is
    every segment on the cone's axis line."""
    axial, radial = seg.hi - seg.lo, abs(seg.r_hi - seg.r_lo)
    if seg.concave or axial < 1e-6 or radial < 1e-6 or max(axial, radial) > _CHAMFER_MAX:
        return False
    if min(seg.r_lo, seg.r_hi) < 1e-6:
        return False
    if not 15.0 <= math.degrees(math.atan2(radial, axial)) <= 75.0:
        return False
    wide_at, wide = (seg.lo, seg.r_lo) if seg.r_lo > seg.r_hi else (seg.hi, seg.r_hi)
    return any(other.kind == "cyl" and not other.concave and abs(other.r_lo - wide) < _TOUCH
               and min(abs(other.lo - wide_at), abs(other.hi - wide_at)) < _TOUCH for other in line)


def chamfers(shape) -> list[Chamfer]:
    """The part's chamfers: a narrow flat strip between two faces that meet square,
    bevelling their outside corner, and a short convex cone between 15 and 75
    degrees bevelling a turned part's end. A chamfer at a hole's mouth is the
    hole's: its callout states it."""
    found = _edge_faces(shape)
    out = [c for c in (_strip_chamfer(face, found) for face in shape.faces()) if c is not None]
    for d, foot, segments in _surface_segments(shape).values():
        line = _merge_split_faces(segments)
        for seg in line:
            if seg.kind == "cone" and _cone_bevel(seg, line):
                mid = (seg.lo + seg.hi) / 2
                out.append(Chamfer((round(seg.hi - seg.lo, 6), round(abs(seg.r_hi - seg.r_lo), 6)),
                                   tuple(f + mid * k for f, k in zip(foot, d))))
    return out


#: Two faces whose normals differ by more than this meet at a sharp edge.
_SHARP = math.cos(math.radians(10.0))


def sharp_edges(shape) -> tuple[int, int]:
    """How many of the part's edges are sharp and left unbroken -- neither of their
    faces a blend or a chamfer -- as ``(outside, inside)``. A general note that
    governs unspecified edges is true only when it leaves none of its kind sharp:
    "FILLETS R3 UNLESS OTHERWISE SPECIFIED" over a sharp inside corner asks for a
    radius the part does not have."""
    from build123d import Vector
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_Cone

    found = _edge_faces(shape)
    breaks = [face.wrapped for face, _blend in _blend_faces(shape)]
    breaks += [face.wrapped for face in shape.faces() if _strip_chamfer(face, found) is not None]
    lines = [_merge_split_faces(segments) for _d, _foot, segments in _surface_segments(shape).values()]
    bevels = [seg for line in lines for seg in line if seg.kind == "cone" and _cone_bevel(seg, line)]
    for face in shape.faces():
        if BRepAdaptor_Surface(face.wrapped).GetType() == GeomAbs_Cone:
            segment = _cone_segment(face)
            if segment is not None and any(abs(segment.lo - b.lo) < _TOUCH and abs(segment.hi - b.hi) < _TOUCH
                                           and abs(segment.r_lo - b.r_lo) < _TOUCH for b in bevels):
                breaks.append(face.wrapped)
    outside = inside = 0
    for edge in shape.edges():
        faces = list(found.FindFromKey(edge.wrapped)) if found.Contains(edge.wrapped) else []
        if len(faces) != 2 or faces[0].IsSame(faces[1]) or any(f.IsSame(b) for f in faces for b in breaks):
            continue
        middle = edge.position_at(0.5)
        point = (middle.X, middle.Y, middle.Z)
        normals = [_normal(_as_face(f), point) for f in faces]
        if None in normals or sum(a * b for a, b in zip(*normals)) > _SHARP:
            continue
        # Step off the edge onto the first face: that face runs away from the
        # second face's outward normal at an outside corner, toward it inside.
        tangent = edge.tangent_at(0.5)
        across = Vector(*normals[0]).cross(tangent)
        first = _as_face(faces[0])
        step = across * 0.05
        if _distance_to_face(first, middle + step) > _distance_to_face(first, middle - step):
            step = -step
        if step.dot(Vector(*normals[1])) < 0:
            outside += 1
        else:
            inside += 1
    return outside, inside


def _as_face(shape):
    from build123d.topology.shape_core import downcast

    return downcast(shape)


def _distance_to_face(face, point) -> float:
    """How far a point is from a face (a TopoDS face)."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeVertex
    from OCP.BRepExtrema import BRepExtrema_DistShapeShape
    from OCP.gp import gp_Pnt

    vertex = BRepBuilderAPI_MakeVertex(gp_Pnt(point.X, point.Y, point.Z)).Vertex()
    return BRepExtrema_DistShapeShape(vertex, face).Value()


def _cone_segment(face) -> _Segment | None:
    """A conical face as a turned segment, for :func:`_cone_bevel`."""
    from build123d import Compound

    lines = _surface_segments(Compound([face]))
    for _d, _foot, segments in lines.values():
        for seg in segments:
            if seg.kind == "cone":
                return seg
    return None


def _tidy(values) -> tuple[float, ...]:
    """Round away the last bits of float noise so equal geometry compares equal."""
    return tuple(0.0 if abs(v) < 1e-9 else round(v, 9) for v in values)
