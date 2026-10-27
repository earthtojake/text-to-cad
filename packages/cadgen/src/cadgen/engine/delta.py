"""A model's delta: what its build holds at a glance against the revision built before it.

A build's worker says what its tree holds (``facts``): its part occurrences, its world bounds --
each part's box in its own frame, kept by the part's geometry key, so a part a build hands back
unchanged is not measured again, placed where each occurrence stands, as ``cadgen inspect``
places its exact boxes -- and its mechanism's joints, configuration sequences and warnings.

The bounds are measured where they decide the model's, to within each part's mesh tolerance, and
nowhere else. Every part starts with a bound, the kernel's quick box (``BRepBndLib.Add``), which the
part never reaches past (but by the spacing of a surface of revolution, of extrusion or of no known
kind, which the kernel samples) and which can reach far past it: a free-form face's poles (168 mm on
juno's panels; edges alone fall short of its bulge, 47.88 x 20.75 for a 60 x 60 loft), a spline
edge's poles (2.6 mm on a 47 mm extruded spline), a torus's circumscribed octagons (3.3 mm on a 40 mm
filleted cylinder). Each side of the world box is the occurrence whose bound reaches farthest once
the part sides it is placed from are measured (``_extreme``). The farthest is narrowed a step at a
time (``_Box.step``): its part listed, each element with a bound of its own (``_bound``) and its
vertices, which it surely reaches; then each side walked, its elements farthest first, a free-form
face's bound narrowed by its poles (``_narrowed``) and an element measured exactly
(``BRepBndLib.AddOptimal``) only while its bound reaches more than the part's mesh tolerance past
what the walk found. A cold walk of tom (221 parts, 628 occurrences, 27,445 faces, 1,605 of them
free-form) lists 5 parts and measures no element; of juno (246 parts, 570 free-form faces), 41
and 12. Measuring every part exactly took 5.5 s on tom and 8.2 s on juno.

The daemon keeps each document's facts beside its record, and in the registry's, and says the
build's against the last (``delta``): each fact now, and what it was when it changed; a first build
has nothing to compare. The CLI prints it under the run line (``cli._describe``).
An edit that keeps every one of those -- a hole's size, a thickness, a fillet -- is still said: the
facts keep each part's geometry key (``shapes``: the digest the build keyed the part by, shortened,
and how many occurrences have it) and, per key, a digest of its parts' colours and materials
(``looks``), so the delta counts the parts whose geometry
no part of the build before had (``changed``), and says when only the look changed. Both come from
what the tree already holds: nothing is measured for them. Volume is not among them:
measured, it costs a kernel pass per part.
"""
from __future__ import annotations

import hashlib
import heapq
import math
from collections import OrderedDict
from typing import Any

from cadgen.engine.kernel.bounds import box_limits

# Per part geometry key, what is known of its box in its own frame (``_Box``), or None for no geometry.
_BOXES: "OrderedDict[str, _Box | None]" = OrderedDict()
_BOXES_HELD = 1 << 16
FACTS = ("parts", "bounds", "joints", "sequences", "warnings")
_KEY = 12  # the hex digits of a part's geometry key the facts keep: enough to tell two builds' parts apart
# A placement's rotation term smaller than this decides nothing: the part side it multiplies is
# not measured for it.
_TERM = 1e-12
# A free-form face's bound narrowed a second time (``_narrowed``): its parameter range in this many
# pieces each way.
_PIECES = 4


def _shown(value: float) -> float:
    """A measure as the run line prints it (``cli._number``): four significant figures below a
    thousand, whole above. Bounds are compared so, so a change too small to print is none."""
    return float(f"{value:.4g}") if abs(value) < 1000 else float(round(value))


def _outward(side: int) -> float:
    """A box's side (``Bnd_Box.Get``'s order: 0, 1, 2 its least x, y and z, 3, 4, 5 its greatest) as
    a sign: a value on it is farther the greater it is times this."""
    return 1.0 if side >= 3 else -1.0


class _Box:
    """A part's box in its own frame, as far as it has been measured: numbers only, no shape held.

    ``quick``: the kernel's quick box of the whole part (the module); ``tolerance``, the part's mesh
    tolerance (``_tolerance``). Once the part is listed (``step``): ``listed``, each element's bound
    as listed (``_bound``), in the order ``_elements`` lists them, None for one with no geometry;
    ``bounds``, each as narrowed since (``cuts``: how many more times it can be, ``_narrowed``);
    ``measured``, each element measured exactly, by its place. Per side (``Bnd_Box.Get``'s order: 0,
    1, 2 the least x, y and z, 3, 4, 5 the greatest), its walk: ``walk``, the elements by their listed
    bound, farthest first; ``next``, how far along it the walk is; ``best``, the farthest exact value
    it found, outward (``_outward``), starting from the part's vertices. A walk's steps depend on the
    part alone, so what it finds does too, whatever was walked before it."""

    __slots__ = ("quick", "tolerance", "listed", "bounds", "cuts", "measured", "walk", "next", "best")

    def __init__(self, quick: tuple[float, ...]) -> None:
        self.quick = quick
        self.tolerance = _tolerance(quick)
        self.listed: list[tuple[float, ...] | None] | None = None
        self.bounds: list[tuple[float, ...] | None] = []
        self.cuts: list[int] = []
        self.measured: dict[int, tuple[float, ...] | None] = {}
        self.walk: list[list[int] | None] = [None] * 6
        self.next = [0] * 6
        self.best: list[float | None] = [None] * 6

    def _ahead(self, side: int) -> int | None:
        """The element ``side``'s walk is at, or None at its end. The part is listed."""
        listed, outward = self.listed or [], _outward(side)
        walk = self.walk[side]
        if walk is None:
            walk = self.walk[side] = sorted((at for at, six in enumerate(listed) if six is not None),
                                            key=lambda at: -outward * listed[at][side])
        return walk[self.next[side]] if self.next[side] < len(walk) else None

    def _reaches(self, side: int, at: int, bound: tuple[float, ...] | None) -> bool:
        """Whether ``bound`` (element ``at``'s) reaches more than the tolerance past what ``side``'s walk found."""
        best = self.best[side]
        return bound is not None and (best is None or _outward(side) * bound[side] > best + self.tolerance)

    def exact(self, side: int) -> bool:
        """Whether ``side``'s walk is done: listed, and no element left reaches more than the
        tolerance past the farthest exact value it found -- the part's side, within its mesh tolerance."""
        if self.listed is None:
            return False
        at = self._ahead(side)
        return at is None or not self._reaches(side, at, self.listed[at])

    def side(self, side: int) -> float:
        """``side`` as far as it is known: a bound the part does not reach past while its walk goes on,
        then the farthest exact value the walk found (no more than the tolerance short of the part's)."""
        if self.listed is None:
            return self.quick[side]
        at = self._ahead(side)
        if at is not None and self._reaches(side, at, self.listed[at]):
            bound = self.listed[at]
            assert bound is not None
            return bound[side]
        best = self.best[side]
        return self.quick[side] if best is None else _outward(side) * best

    def step(self, side: int, shape: Any, listed: dict[int, list]) -> None:
        """One step of ``side``'s walk: the part listed, each element with its bound and the farthest
        vertices as each side's start; or else, at the element the walk is at, its bound narrowed
        (``_narrowed``), the element passed once its bound reaches no more than the tolerance past what
        the walk found, or else measured exactly (once for every side). ``listed``: this walk's
        elements of each part it has stepped, by its ``_Box``: a shape's sub-shapes are listed once a
        walk, and never kept beyond it."""
        elements = listed.get(id(self))
        if elements is None:
            elements = listed[id(self)] = _elements(shape)
        if self.listed is None:
            found = [_bound(element) for element in elements]
            self.listed = [bound for bound, _cuts in found]
            self.bounds = list(self.listed)
            self.cuts = [cuts for _bound, cuts in found]
            corners = _vertices(shape)
            if corners is not None:
                self.best = [_outward(other) * corners[other] for other in range(6)]
            return
        at = self._ahead(side)
        if at is None or not self._reaches(side, at, self.listed[at]):
            return
        if self._reaches(side, at, self.bounds[at]) and self.cuts[at]:
            narrower = _narrowed(elements[at], self.cuts[at])
            self.cuts[at] = self.cuts[at] - 1 if narrower is not None else 0
            if narrower is not None:
                self.bounds[at] = _cut(self.bounds[at], narrower)
            return
        if self._reaches(side, at, self.bounds[at]):
            if at not in self.measured:
                from OCP.Bnd import Bnd_Box
                from OCP.BRepBndLib import BRepBndLib

                found = Bnd_Box()
                BRepBndLib.AddOptimal_s(elements[at], found, False, False)
                self.measured[at] = None if found.IsVoid() else _got(found)
            six, best = self.measured[at], self.best[side]
            if six is not None and (best is None or _outward(side) * six[side] > best):
                self.best[side] = _outward(side) * six[side]
        self.next[side] += 1


def _tolerance(quick: tuple[float, ...]) -> float:
    """A part's mesh tolerance: the linear deflection its display mesh is made at (``mesh.deflection``:
    ``(Lx + Ly + Lz) / 300 * DEVIATION`` of its box), from its quick box. A side found is no
    farther from the part's than the mesh's faces are from its surface."""
    from cadgen.engine.mesh import DEVIATION

    return max(sum(quick[axis + 3] - quick[axis] for axis in range(3)) / 300.0 * DEVIATION, 1e-4)


def _vertices(shape: Any) -> tuple[float, ...] | None:
    """The box of a part's vertices: points on it, so a side reaches at least that far. None for none."""
    from OCP.BRep import BRep_Tool
    from OCP.TopAbs import TopAbs_VERTEX
    from OCP.TopExp import TopExp
    from OCP.TopoDS import TopoDS
    from OCP.collections import IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher

    found = IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher()
    TopExp.MapShapes_s(shape, TopAbs_VERTEX, found)
    if not found.Extent():
        return None
    points = [BRep_Tool.Pnt_s(TopoDS.Vertex(found.FindKey(at))) for at in range(1, found.Extent() + 1)]
    xs, ys, zs = [p.X() for p in points], [p.Y() for p in points], [p.Z() for p in points]
    return min(xs), min(ys), min(zs), max(xs), max(ys), max(zs)


def _box(part: Any) -> _Box | None:
    """What is known of ``part``'s box (``_Box``), by its geometry key: its quick box made on its key's
    first walk; None for a part with no geometry."""
    found = _BOXES.get(part.key, ())
    if found != ():
        _BOXES.move_to_end(part.key)
        return found
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib

    box = Bnd_Box()
    BRepBndLib.Add_s(part.shape, box, False)
    found = None if box.IsVoid() else _Box(_got(box))
    _BOXES[part.key] = found
    while len(_BOXES) > _BOXES_HELD:
        _BOXES.popitem(last=False)
    return found


def _got(box: Any) -> tuple[float, ...]:
    """A box's six values without its gap: the kernel enlarges a quick box by each element's
    tolerance, which is no geometry (an exact box has none)."""
    box.SetGap(0.0)
    return tuple(box_limits(box))


def _cut(bound: Any, tighter: tuple[float, ...]) -> tuple[float, ...]:
    """Where two boxes an element lies in both overlap."""
    return (*(max(a, b) for a, b in zip(bound[:3], tighter[:3])), *(min(a, b) for a, b in zip(bound[3:], tighter[3:])))


def _elements(shape: Any) -> list:
    """What a part's box is the box of: its faces, then each edge outside a face and each vertex
    outside an edge (a wire's, a point's), in the kernel's order, the same for every shape of one
    geometry key."""
    from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_SHAPE, TopAbs_VERTEX
    from OCP.TopExp import TopExp_Explorer

    found = []
    for kind, outside in ((TopAbs_FACE, TopAbs_SHAPE), (TopAbs_EDGE, TopAbs_FACE), (TopAbs_VERTEX, TopAbs_EDGE)):
        explorer = TopExp_Explorer(shape, kind, outside)
        while explorer.More():
            found.append(explorer.Current())
            explorer.Next()
    return found


def _bound(element: Any) -> tuple[tuple[float, ...] | None, int]:
    """A box an element does not reach past (but by a sampled surface's spacing), None for one with no
    geometry, and how many times it can be narrowed (``_narrowed``): the kernel's quick box, and a
    torus's own box where the kernel's circumscribes an octagon about each of its circles."""
    from OCP.Bnd import Bnd_Box
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.BRepBndLib import BRepBndLib
    from OCP.GeomAbs import GeomAbs_BezierSurface, GeomAbs_BSplineSurface, GeomAbs_Torus
    from OCP.TopAbs import TopAbs_FACE
    from OCP.TopoDS import TopoDS

    box = Bnd_Box()
    BRepBndLib.Add_s(element, box, False)
    if box.IsVoid():
        return None, 0
    found = _got(box)
    if element.ShapeType() != TopAbs_FACE:
        return found, 0
    surface = BRepAdaptor_Surface(TopoDS.Face(element), False)
    kind = surface.GetType()
    if kind == GeomAbs_Torus:
        # Along a unit direction whose cosine with the axis is c, a torus reaches no farther from
        # its centre than (R + r) sqrt(1 - c^2) + r |c|.
        torus = surface.Torus()
        centre, axis = torus.Location(), torus.Axis().Direction()
        major, minor = torus.MajorRadius(), torus.MinorRadius()
        reach = [(major + minor) * math.sqrt(max(0.0, 1.0 - c * c)) + minor * abs(c)
                 for c in (axis.X(), axis.Y(), axis.Z())]
        middle = (centre.X(), centre.Y(), centre.Z())
        return _cut(found, (*(m - r for m, r in zip(middle, reach)), *(m + r for m, r in zip(middle, reach)))), 0
    return found, 2 if kind in (GeomAbs_BSplineSurface, GeomAbs_BezierSurface) else 0


def _narrowed(face: Any, cuts: int) -> tuple[float, ...] | None:
    """A free-form face's bound narrower than the kernel's (which takes a whole patch's poles for any
    piece of it), by the convex hull property: its surface cut to the face's parameter range, the box
    of its poles (``cuts`` 2), then of the poles of each of ``_PIECES`` x ``_PIECES`` pieces of that
    range, which hug the surface the closer the smaller they are (``cuts`` 1). None where it cannot be."""
    patch = _patch(face)
    if patch is None:
        return None
    surface, low_u, high_u, low_v, high_v = patch
    if cuts > 1:
        return _hull(surface, low_u, high_u, low_v, high_v)
    us = [low_u + (high_u - low_u) * at / _PIECES for at in range(_PIECES + 1)]
    vs = [low_v + (high_v - low_v) * at / _PIECES for at in range(_PIECES + 1)]
    found: tuple[float, ...] | None = None
    for u in range(_PIECES):
        for v in range(_PIECES):
            hull = _hull(surface, us[u], us[u + 1], vs[v], vs[v + 1])
            if hull is None:
                return None
            found = hull if found is None else (*map(min, found[:3], hull[:3]), *map(max, found[3:], hull[3:]))
    return found


def _patch(face: Any) -> tuple[Any, float, float, float, float] | None:
    """A free-form face's surface as a B-spline of its own (the conversion copies one, so the face's
    is never changed) and the face's parameter range on it; None where there is none to cut."""
    from OCP.BRep import BRep_Tool
    from OCP.BRepTools import BRepTools
    from OCP.GeomConvert import GeomConvert
    from OCP.TopoDS import TopoDS

    face = TopoDS.Face(face)
    try:
        surface = GeomConvert.SurfaceToBSplineSurface_s(BRep_Tool.Surface_s(face))
        low_u, high_u, low_v, high_v = BRepTools.UVBounds_s(face)
        first_u, last_u, first_v, last_v = surface.Bounds()
    except Exception:  # noqa: BLE001 - a surface the kernel will not convert keeps the bound it has
        return None
    if not surface.IsUPeriodic():
        low_u, high_u = max(low_u, first_u), min(high_u, last_u)
    if not surface.IsVPeriodic():
        low_v, high_v = max(low_v, first_v), min(high_v, last_v)
    if not (high_u - low_u > 1e-9 and high_v - low_v > 1e-9):
        return None
    return surface, low_u, high_u, low_v, high_v


def _hull(surface: Any, low_u: float, high_u: float, low_v: float, high_v: float) -> tuple[float, ...] | None:
    """The box of the poles of a B-spline surface cut to a parameter range (a copy is cut): the
    surface there lies inside it. None where the kernel will not cut it."""
    from OCP.Bnd import Bnd_Box
    from OCP.GeomConvert import GeomConvert

    try:
        cut = GeomConvert.SurfaceToBSplineSurface_s(surface)
        cut.CheckAndSegment(low_u, high_u, low_v, high_v)
        box = Bnd_Box()
        for row in range(1, cut.NbUPoles() + 1):
            for column in range(1, cut.NbVPoles() + 1):
                box.Add(cut.Pole(row, column))
    except Exception:  # noqa: BLE001 - a range the kernel will not cut keeps the bound it has
        return None
    return None if box.IsVoid() else _got(box)


def _reach(box: _Box, row: tuple[float, ...], outward: float) -> tuple[float, list[int]]:
    """How far an occurrence's bound reaches along one world axis (``row``: that axis's row of its
    placement, the rotation's three terms then the translation), ``outward`` 1 for the greatest side
    and -1 for the least, signed outward; and the part sides it is placed from."""
    total, sides = outward * row[3], []
    for axis in range(3):
        term = outward * row[axis]
        if abs(term) < _TERM:
            continue
        side = axis + 3 if term > 0 else axis
        total += term * box.side(side)
        sides.append(side)
    return total, sides


def _extreme(placed: list, axis: int, outward: float, listed: dict[int, list]) -> float:
    """One side of the world box (``outward`` 1 its greatest value along ``axis``, -1 its least): the
    occurrence whose bound reaches farthest once every part side it is placed from is exact. Each
    time the farthest is not, it is narrowed a step (``_Box.step``) and put back; a bound narrowed
    does not grow (but by a sampled surface's spacing), so none put back can reach past the one
    found."""
    heap = [(-_reach(box, rows[axis], outward)[0], at) for at, (box, _shape, rows) in enumerate(placed)]
    heapq.heapify(heap)
    while True:
        reached, at = heapq.heappop(heap)
        box, shape, rows = placed[at]
        now, sides = _reach(box, rows[axis], outward)
        if now != -reached:  # its part narrowed since it was put in: put in again where it reaches now
            heapq.heappush(heap, (-now, at))
            continue
        open_sides = [side for side in sides if not box.exact(side)]
        if not open_sides:
            return outward * now
        if box.listed is None:
            box.step(open_sides[0], shape, listed)
        else:
            for side in open_sides:
                box.step(side, shape, listed)
        heapq.heappush(heap, (-_reach(box, rows[axis], outward)[0], at))


def facts(tree: Any, model: str, signature: tuple) -> dict[str, Any]:
    """What a built tree (``document.Tree``, its parts keyed) holds: ``parts``, its occurrences;
    ``bounds``, its world box's size (None with no geometry); ``joints``, ``sequences`` and
    ``warnings``, its mechanism's. A model whose tree has the signature its last build here had
    (``build._finish``'s: every part, placement, name and harvest) is not walked again."""
    last = _LAST.get(model)
    if last is not None and last[0] == signature:
        return dict(last[1])
    found = _walked(tree)
    _LAST[model] = (signature, found)
    return dict(found)


# Per model (``script::name``), the signature of the tree its last build here made, and its facts.
_LAST: dict[str, tuple[tuple, dict[str, Any]]] = {}


def _walked(tree: Any) -> dict[str, Any]:
    from OCP.gp import gp_Trsf

    from cadgen.engine.document import Assembly

    count = 0
    shapes: dict[str, int] = {}
    looks: dict[str, set[str]] = {}  # per geometry key, its parts' looks: a rename or another copy changes none
    placed: list = []  # each occurrence with geometry: its part's box, its shape, its placement's rows

    def visit(prototype: Any, location: Any, painted: Any = None) -> None:
        nonlocal count
        if isinstance(prototype, Assembly):
            for component in prototype.components:
                visit(component.prototype, location.Multiplied(component.location.Transformation()),
                      component.color if component.color is not None else painted)
            return
        count += 1
        key = prototype.key[:_KEY]
        shapes[key] = shapes.get(key, 0) + 1
        looks.setdefault(key, set()).add(repr((painted, prototype.color, sorted(prototype.face_colors.items()), prototype.material,
                        sorted(prototype.face_materials.items(), key=lambda item: item[0]))))
        box = _box(prototype)
        if box is not None:
            rows = tuple(tuple(location.Value(row, column) for column in (1, 2, 3, 4)) for row in (1, 2, 3))
            placed.append((box, prototype.shape, rows))

    visit(tree.root, gp_Trsf())
    listed: dict[int, list] = {}
    bounds = None if not placed else [
        _shown(_extreme(placed, axis, 1.0, listed) - _extreme(placed, axis, -1.0, listed)) for axis in range(3)]
    mechanism = tree.mechanism
    return {"parts": count,
            "bounds": bounds,
            "joints": len(mechanism.pairs) if mechanism is not None else 0,
            "sequences": len(mechanism.motions) if mechanism is not None else 0,
            "warnings": len(mechanism.warnings) if mechanism is not None else 0,
            "shapes": dict(sorted(shapes.items())),
            "looks": {key: hashlib.blake2b("\0".join(sorted(found)).encode(), digest_size=4).hexdigest()
                      for key, found in sorted(looks.items())}}


def delta(now: dict[str, Any], before: dict[str, Any] | None) -> dict[str, Any]:
    """Each fact ``now`` holds, ``{"now": value}``, with ``"was"`` where ``before`` held another;
    ``first`` when there was no build before to compare. Against a build before whose facts kept
    its parts' geometry keys, ``changed``: ``parts``, how many of this build's part occurrences
    have a geometry no part of the build before had, and ``looks``, whether a colour or a material
    changed on a geometry both builds have."""
    found: dict[str, Any] = {"first": before is None}
    for name in FACTS:
        row: dict[str, Any] = {"now": now.get(name)}
        if before is not None and before.get(name) != row["now"]:
            row["was"] = before.get(name)
        found[name] = row
    if before is not None and before.get("shapes") is not None and now.get("shapes") is not None:
        was, looked, looks = before["shapes"], before.get("looks") or {}, now.get("looks") or {}
        found["changed"] = {"parts": sum(count for key, count in now["shapes"].items() if key not in was),
                            "looks": any(looked[key] != look for key, look in looks.items() if key in looked)}
    return found
