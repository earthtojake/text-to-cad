"""Casting and machining vocabulary for the W16.

Every builder — block, heads, sump, turbo housings, covers — shapes its metal
through these helpers so the whole engine reads as ONE foundry and ONE machine
shop:

  CAST surfaces   generous radii, 2-4 deg draft, soft transitions, a parting
                  line where the mould split.  Nothing on a cast face is sharp.
  MACHINED faces  dead flat, crisp at the edge, bright.  A machined face is a
                  PLANE cut through cast stock (`machined_face`), plus a thin
                  skin solid (`machined_skin`) the caller colours
                  `palette.MACHINED` so the eye reads the material change.

Conventions
  * build123d algebra mode; `from cadgen import build123d as bd`.
  * Every primitive is returned in its OWN local frame with the base at z=0 and
    +Z up.  The caller places it — with `locate()`, or `bd.Pos`/`bd.Rot`.
  * Millimetres.  Casting radii 3-8 mm on the block/heads/sump, 1-2 mm on small
    covers and bosses; draft 2-4 deg.

Return conventions (mixed, deliberately — read the signature)
  * Ops that run a RETRY LADDER return `(part, applied|None)`:
    `safe_fillet`, `safe_chamfer`, `fillet_all`, `soften`, `cast_body`.
    `applied` is the radius/length actually achieved, `None` when the feature
    was skipped entirely.  Cosmetic finishing NEVER raises — a lost fillet is a
    duller casting, not a failed build, so check the returned radius when the
    radius matters.
  * Everything else returns geometry: `drafted_prism`, `boss`, `rib`, `web`,
    `parting_line`, `machined_face`, `fuse_all`, `cut_all` return a `Part`;
    `machined_skin` returns `Part | None`.
  * `parting_line` / `machined_face` / `machined_skin` are no-ops when the plane
    misses the part: the part comes back unchanged (skin comes back `None`) with
    one warning line on stderr.

Selecting edges
  Use `edges_at()` / `edge_center()`, never an index — every boolean
  reorders the edge list. Note that `Edge.center()` on a CIRCLE returns a
  point ON the circle, not its centre, which silently breaks the obvious
  "find the boss root circle" filter; `edge_center()` is the bbox centre and
  answers what you meant.

Soundness gate
  `is_sound()` is valid + closed + every solid positive-volume + the BOP check
  (`BRepAlgoAPI_Check`).  Validity alone accepts inverted solids and BOP-faulty
  skinny faces that only blow up several booleans later, so every boolean and
  every ladder step in this module is gated by it.  Set `BOP_CHECK = False` to
  drop the (expensive) BOP half on very large assemblies.
"""

from __future__ import annotations

import math
import sys
from typing import Callable, Iterable, Sequence

from cadgen import build123d as bd


# Run BRepAlgoAPI_Check as part of is_sound(). Costs real time on big
# compounds; turn it off only when a build is provably clean and too slow.
BOP_CHECK = True

# Ladder step for every retry: each attempt is 0.75x the last.
LADDER_STEP = 0.75

_EPS = 1e-7
_KEY_ND = 4  # decimal places when fingerprinting an edge by its bbox centre


def _warn(msg: str) -> None:
    print(f"[castings] {msg}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Frames.  Never Plane.rotated(): it composes in WORLD axes and silently
# yaws a frame whose own axes are not the global ones.
# ---------------------------------------------------------------------------

def _vec(v) -> bd.Vector:
    return v if isinstance(v, bd.Vector) else bd.Vector(*v)


def _perp(z: bd.Vector) -> bd.Vector:
    """Some unit vector perpendicular to `z` (world-axis biased, so an
    axis-aligned z_dir gives an axis-aligned x_dir)."""
    for cand in ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)):
        c = bd.Vector(*cand)
        cross = z.cross(c)
        if cross.length > 1e-6:
            return cross.cross(z).normalized()
    return bd.Vector(1, 0, 0)


def frame(origin, z_dir, x_dir=None) -> bd.Plane:
    """A `Plane` built from EXPLICIT direction vectors.

    `z_dir` becomes the plane normal (local +Z); `x_dir` is orthogonalised
    against it, and defaults to a world-axis-biased perpendicular. Use this
    instead of `Plane.rotated()`, which rotates in world axes and produces a
    valid solid of the wrong shape.
    """
    z = _vec(z_dir)
    if z.length < 1e-9:
        raise ValueError("frame(): z_dir is zero-length")
    z = z.normalized()
    if x_dir is None:
        x = _perp(z)
    else:
        x = _vec(x_dir)
        x = x - z * x.dot(z)  # orthogonalise
        if x.length < 1e-6:
            raise ValueError("frame(): x_dir is parallel to z_dir")
        x = x.normalized()
    return bd.Plane(origin=_vec(origin), x_dir=x, z_dir=z)


def locate(shape, origin, z_dir, x_dir=None):
    """A moved COPY of `shape` whose local +Z now points along `z_dir` and
    whose local origin sits at `origin`.

    Uses `.moved()`, which COMPOSES with any transform the shape already
    carries; `.located()` would assign an absolute location and throw an
    existing rotation away.
    """
    return shape.moved(frame(origin, z_dir, x_dir).location)


# ---------------------------------------------------------------------------
# Soundness
# ---------------------------------------------------------------------------

def _is_closed(shape) -> bool:
    """Every non-degenerate edge bounded by exactly two faces."""
    from OCP.TopExp import TopExp
    from OCP.TopTools import TopTools_IndexedDataMapOfShapeListOfShape
    from OCP.BRep import BRep_Tool
    from OCP.TopAbs import TopAbs_ShapeEnum
    from OCP.TopoDS import TopoDS
    try:
        m = TopTools_IndexedDataMapOfShapeListOfShape()
        TopExp.MapShapesAndAncestors_s(
            shape.wrapped,
            TopAbs_ShapeEnum.TopAbs_EDGE,
            TopAbs_ShapeEnum.TopAbs_FACE,
            m,
        )
        if m.Extent() == 0:
            return False
        for i in range(1, m.Extent() + 1):
            edge = m.FindKey(i)
            if BRep_Tool.Degenerated_s(TopoDS.Edge_s(edge)):
                continue
            if m.FindFromIndex(i).Extent() != 2:
                return False
        return True
    except Exception:
        return False


def is_sound(shape) -> bool:
    """True when `shape` is a real solid body: non-null, `is_valid`, closed,
    every solid of positive volume, and (unless `BOP_CHECK` is off) passing
    `BRepAlgoAPI_Check`.

    Volume is checked PER SOLID: an inverted member inside a compound cancels
    against a sound one, so an aggregate volume sees nothing wrong.
    """
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Check
    if shape is None:
        return False
    wrapped = getattr(shape, "wrapped", None)
    if wrapped is None or wrapped.IsNull():
        return False
    try:
        valid = shape.is_valid
        if callable(valid):
            valid = valid()
        if not valid:
            return False
        solids = shape.solids()
        if not solids:
            return False
        for solid in solids:
            if solid.volume <= _EPS:
                return False
        if not _is_closed(shape):
            return False
        if BOP_CHECK and not BRepAlgoAPI_Check(wrapped).IsValid():
            return False
    except Exception:
        return False
    return True


# ---------------------------------------------------------------------------
# Retry ladders.  Cosmetic finishing never raises.
# ---------------------------------------------------------------------------

def _ladder(value: float, floor: float):
    while value >= floor - _EPS:
        yield value
        value *= LADDER_STEP


def safe_fillet(part, edges, r: float, min_r: float = 0.3):
    """Fillet `edges` at `r`, retrying at 0.75x steps down to `min_r`.

    A result is accepted only if `is_sound()` passes it, so a BOP-faulty
    fillet is stepped down rather than carried forward to detonate in a later
    boolean. Returns `(part, applied_r)`, or `(part_unchanged, None)` when even
    `min_r` fails. Never raises.
    """
    edge_list = [e for e in edges] if edges is not None else []
    if not edge_list or r <= 0:
        return part, None
    for radius in _ladder(r, min_r):
        try:
            result = bd.fillet(edge_list, radius=radius)
        except Exception:
            continue
        if is_sound(result):
            return result, radius
    return part, None


def safe_chamfer(part, edges, length: float, min_length: float = 0.3, **kwargs):
    """Chamfer `edges` at `length` with the same 0.75x ladder and the same
    soundness gate as `safe_fillet`. Returns `(part, applied_length|None)`.

    Extra kwargs (`angle=`, `reference=`) pass through to `bd.chamfer`.

    NOTE: do not chamfer tangent chains or multi-arc outlines in 3D — OCC
    answers with silent failure, minutes of churn, or an uncatchable SIGSEGV
    that no gate here can trap. Bake those bevels into the section profile.
    """
    edge_list = [e for e in edges] if edges is not None else []
    if not edge_list or length <= 0:
        return part, None
    for value in _ladder(length, min_length):
        try:
            result = bd.chamfer(edge_list, length=value, **kwargs)
        except Exception:
            continue
        if is_sound(result):
            return result, value
    return part, None


def edge_center(edge) -> bd.Vector:
    """The bounding-box centre of an edge.

    Use this, NOT `Edge.center()`. On a circular edge `Edge.center()` returns a
    point ON the circle (its mid-parameter point), so the junction circle of a
    boss standing at x=40 with r=15 answers x=25, and every "select the root
    circle at the boss centre" filter matches nothing and quietly leaves the
    root sharp. Bounding-box centre gives the true circle centre, and for a
    straight edge gives its midpoint.
    """
    return edge.bounding_box().center()


def edges_at(part, z: float | None = None, near=None, tol: float = 1e-3,
             kind=None) -> list:
    """Select edges of `part` by geometry rather than by index.

    `z`     keeps edges lying ENTIRELY in the plane z = value (a face
            perimeter, a deck rail, a boss junction circle).
    `near`  keeps edges whose `edge_center` is within `tol` of that point.
    `kind`  filters on `Edge.geom_type` — a `GeomType`, or its name as a
            string (`"CIRCLE"`, `"LINE"`).

    Index-based edge picking breaks after every boolean; this does not.
    """
    out = []
    for edge in part.edges():
        bb = edge.bounding_box()
        if z is not None and not (abs(bb.min.Z - z) < tol and abs(bb.max.Z - z) < tol):
            continue
        if near is not None:
            target = _vec(near)
            if (edge_center(edge) - target).length > tol:
                continue
        if kind is not None:
            gt = edge.geom_type
            name = kind if isinstance(kind, str) else getattr(kind, "name", str(kind))
            if getattr(gt, "name", str(gt)).upper() != name.upper():
                continue
        out.append(edge)
    return out


def _edge_key(edge) -> tuple:
    """Fingerprint an edge by its bounding-box centre. A fillet trims
    neighbouring edges symmetrically, so that centre survives where the edge
    OBJECT does not — which is what lets `fillet_all` re-resolve its remaining
    targets against topology that changed under it."""
    c = edge_center(edge)
    return (round(c.X, _KEY_ND), round(c.Y, _KEY_ND), round(c.Z, _KEY_ND))


def _face_width(face) -> float:
    """How narrow a face is, as 2 x area / perimeter.

    This is the width of a long thin strip (a 10 x 0.15 ledge answers 0.15),
    the radius of a disc, and half the side of a square — scale-correct and,
    crucially, ORIENTATION-INDEPENDENT. A bounding box is not: a wall carrying
    3 deg of draft over 55 mm has a box 2.9 mm "thick" along its own normal, so
    a box-based measure calls every drafted casting wall narrow and quietly
    refuses to round the part at all.
    """
    try:
        perimeter = sum(e.length for e in face.edges())
        if perimeter <= _EPS:
            return 0.0
        return 2.0 * face.area / perimeter
    except Exception:
        return float("inf")   # unmeasurable: do not exclude on a guess


def _narrow_edge_keys(part, r: float) -> set:
    """Fingerprints of edges bounding a face narrower than `r` — a fillet of
    radius r cannot roll along a face it does not fit on, and OCC's response
    to being asked is sometimes a SIGSEGV rather than an exception."""
    keys = set()
    for face in part.faces():
        if _face_width(face) < r:
            for edge in face.edges():
                keys.add(_edge_key(edge))
    return keys


def _resolve(part, keys) -> list:
    """Re-select edges of `part` matching the given bbox-centre fingerprints.
    Edges swallowed by an earlier fillet simply do not come back."""
    wanted = set(keys)
    return [e for e in part.edges() if _edge_key(e) in wanted]


def fillet_all(part, r: float, exclude: Callable | None = None,
               min_r: float = 0.3, batch: int = 8, skip_narrow: bool = True):
    """Fillet EVERY edge of `part` with the ladder — the standard cast finish.

    `exclude(edge) -> bool` drops edges from the set (machined faces, mating
    flanges, edges a later feature owns).

    `skip_narrow` (default on) additionally drops edges bounding a face
    narrower than `r`. This is not a nicety. Filleting a body that carries a
    sub-radius step — a 0.15 mm ledge left by a boolean, a sliver face — can
    take OCC down with an UNCATCHABLE SIGSEGV once one pass has already
    beveled a neighbour, killing the whole build with no traceback and no
    partial output; measured on a 60x40x20 block with a 0.15 mm step, where
    every individual fillet raised cleanly and only the SEQUENCE crashed.
    No try/except in this module can defend against that, so the defence is to
    not ask. Clean slivers out of the body rather than turning this off.

    Tries the whole edge set in one operation first, which is both fastest and
    gives the cleanest corner blends. If that fails at every rung, it falls
    back to filleting in batches of `batch` edges, re-resolving each batch
    against the CURRENT topology and bisecting a failing batch down to single
    edges — so one impossible edge costs one edge, not the whole casting.

    Returns `(part, applied_r|None)`; on the batched path `applied_r` is the
    SMALLEST radius achieved (the worst degradation), not the nominal.
    """
    if r <= 0:
        return part, None
    targets = [e for e in part.edges() if exclude is None or not exclude(e)]
    if skip_narrow:
        narrow = _narrow_edge_keys(part, r)
        if narrow:
            kept = [e for e in targets if _edge_key(e) not in narrow]
            if len(kept) < len(targets):
                _warn(f"fillet_all: skipped {len(targets) - len(kept)} edge(s) "
                      f"on faces narrower than r={r} (OCC can hard-crash there)")
            targets = kept
    if not targets:
        return part, None

    whole, applied = safe_fillet(part, targets, r, min_r)
    if applied is not None:
        return whole, applied

    keys = [_edge_key(e) for e in targets]
    current = part
    worst = None

    def _apply(group_keys) -> None:
        nonlocal current, worst
        if not group_keys:
            return
        edges = _resolve(current, group_keys)
        if not edges:
            return
        result, got = safe_fillet(current, edges, r, min_r)
        if got is not None:
            current = result
            worst = got if worst is None else min(worst, got)
            return
        if len(group_keys) == 1:
            return
        half = len(group_keys) // 2
        _apply(group_keys[:half])
        _apply(group_keys[half:])

    for i in range(0, len(keys), batch):
        _apply(keys[i:i + batch])

    if worst is None:
        _warn(f"fillet_all: no edge accepted r={r} down to {min_r}; left sharp")
    return current, worst


def soften(part, r: float, exclude: Callable | None = None, min_r: float = 0.3,
           skip_narrow: bool = True):
    """The standard cast finishing pass: round every edge of `part` at `r`.

    Alias for `fillet_all`. Returns `(part, applied_r|None)`.
    """
    return fillet_all(part, r, exclude=exclude, min_r=min_r,
                      skip_narrow=skip_narrow)


# ---------------------------------------------------------------------------
# Cast primitives
# ---------------------------------------------------------------------------

def drafted_prism(profile_face_or_sketch, height: float, draft_deg: float = 3.0,
                  top_r: float | None = None):
    """Extrude a closed profile by `height` with mould draft: the walls
    CONVERGE upward by `draft_deg` (positive taper shrinks the section).

    Base sits in the profile's own plane, material grows along +normal.
    `top_r` rounds the top face perimeter (the ladder applies; a lost top
    radius does not fail the build).

    `extrude(..., taper=)` is fragile on dense spline outlines, so the draft
    itself steps down 3 deg -> 1.5 deg -> 0 rather than throwing.
    """
    angles = [draft_deg]
    if draft_deg > 0:
        angles += [draft_deg * 0.5, 0.0]
    solid = None
    for angle in angles:
        try:
            candidate = bd.extrude(profile_face_or_sketch, amount=height,
                                   taper=angle)
        except Exception:
            continue
        if is_sound(candidate):
            solid = candidate
            if angle != draft_deg:
                _warn(f"drafted_prism: draft fell back {draft_deg} -> {angle} deg")
            break
    if solid is None:
        raise ValueError("drafted_prism: extrude failed at every draft angle")

    if top_r:
        top_z = solid.bounding_box().max.Z
        solid, _ = safe_fillet(solid, edges_at(solid, z=top_z), top_r)
    return solid


def cast_body(profile_sketch, height: float, draft_deg: float = 3.0,
              edge_r: float = 4.0):
    """A finished cast body in one call: drafted prism + all-edge softening.

    Returns `(part, applied_r|None)` — the applied casting radius, which is
    what tells you whether the ladder degraded the look.
    """
    solid = drafted_prism(profile_sketch, height, draft_deg)
    return fillet_all(solid, edge_r)


def boss(d: float, h: float, draft_deg: float = 3.0,
         fillet_r: float | None = None, hole_d: float | None = None,
         hole_depth: float | None = None):
    """A cast boss: drafted cylinder, base at z=0, +Z up, base diameter `d`.

    Walls converge upward by `draft_deg` (the pattern has to leave the sand).
    `fillet_r` rounds the crown rim. `hole_d` adds a bore — through when
    `hole_depth` is None, otherwise blind `hole_depth` deep from the crown.

    NO root fillet is applied here: the root blend only exists once the boss is
    fused to its parent wall, so the caller fuses and then runs `safe_fillet`
    over the junction circle.
    """
    r_base = d / 2.0
    r_top = r_base - h * math.tan(math.radians(max(draft_deg, 0.0)))
    r_top = max(r_top, r_base * 0.25, 0.2)

    body = bd.Cone(r_base, r_top, h, align=(None, None, None))

    if fillet_r:
        body, _ = safe_fillet(body, edges_at(body, z=h),
                              min(fillet_r, r_top * 0.6), min_r=0.15)

    if hole_d:
        r_hole = hole_d / 2.0
        if hole_depth is None:
            bore = bd.Pos(0, 0, -1.0) * bd.Cylinder(
                r_hole, h + 2.0, align=(None, None, None))
        else:
            depth = min(hole_depth, h)
            bore = bd.Pos(0, 0, h - depth) * bd.Cylinder(
                r_hole, depth + 1.0, align=(None, None, None))
        body = cut_all(body, [bore])
    return body


def rib(length: float, height: float, thickness: float, draft_deg: float = 3.0,
        end_r: float | None = None, top_r: float | None = None):
    """A cast stiffening rib: runs along +X from x=0 to x=`length`, centred on
    y=0, base at z=0.

    Tapered in THICKNESS only — `thickness` at the root, converging by
    `draft_deg` per side up to `height` — so the rib draws from the mould while
    keeping its full length. Built as one extruded trapezoid section rather
    than a drafted prism, which would pull the ends in too.

    `end_r` rounds the blunt ends in plan; `top_r` rounds the two long top
    edges. Both use the ladder.
    """
    taper = 2.0 * height * math.tan(math.radians(max(draft_deg, 0.0)))
    t_top = max(thickness - taper, thickness * 0.25, 0.2)
    hb, ht = thickness / 2.0, t_top / 2.0

    # Section in the YZ plane (local u -> Y, v -> Z), wound CCW, extruded +X.
    section = bd.Plane.YZ * bd.Polygon(
        (-hb, 0.0), (hb, 0.0), (ht, height), (-ht, height), align=None
    )
    body = bd.extrude(section, amount=length)
    if not is_sound(body):
        raise ValueError("rib: section extrude produced an unsound solid")

    if top_r:
        body, _ = safe_fillet(body, edges_at(body, z=height),
                              min(top_r, t_top * 0.45), min_r=0.15)

    if end_r:
        ends = []
        for e in body.edges():
            bb = e.bounding_box()
            at_x0 = abs(bb.min.X) < 1e-6 and abs(bb.max.X) < 1e-6
            at_x1 = (abs(bb.min.X - length) < 1e-6
                     and abs(bb.max.X - length) < 1e-6)
            if (at_x0 or at_x1) and bb.max.Z > 1e-6:
                ends.append(e)
        body, _ = safe_fillet(body, ends, min(end_r, ht * 0.9), min_r=0.15)
    return body


def web(points: Sequence, thickness: float, height: float):
    """A cast web/wall following the polyline `points` (2D `(x, y)` or 3D
    tuples; z is ignored). Base at z=0, `height` tall, `thickness` wide,
    centred on the polyline.

    Corners are filled with a cylinder of the wall thickness, so the wall
    reads as one continuous cast rib rather than mitred plates. Everything is
    fused in ONE multi-operand operation.
    """
    pts = [(float(p[0]), float(p[1])) for p in points]
    if len(pts) < 2:
        raise ValueError("web(): need at least two points")
    r = thickness / 2.0
    pieces = []
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        dx, dy = x1 - x0, y1 - y0
        seg = math.hypot(dx, dy)
        if seg < _EPS:
            continue
        plank = bd.Box(seg, thickness, height,
                       align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
        plank = bd.Rot(0, 0, math.degrees(math.atan2(dy, dx))) * plank
        pieces.append(bd.Pos((x0 + x1) / 2.0, (y0 + y1) / 2.0, 0) * plank)
    # Round every joint (and both ends) so no knife edge survives.
    for x, y in pts:
        pieces.append(bd.Pos(x, y, 0)
                      * bd.Cylinder(r, height, align=(None, None, None)))
    if not pieces:
        raise ValueError("web(): polyline has zero length")
    return fuse_all(pieces)


# ---------------------------------------------------------------------------
# Foundry / shop marks
# ---------------------------------------------------------------------------

def _slab(plane: bd.Plane, span: float, thickness: float, align_z=None):
    # `align_z` defaults inside the body: a `bd.` default argument resolves at
    # import and drags the kernel in before the freshness gate can run.
    if align_z is None:
        align_z = bd.Align.CENTER
    box = bd.Box(span, span, thickness,
                 align=(bd.Align.CENTER, bd.Align.CENTER, align_z))
    return box.moved(plane.location)


def _span(part) -> float:
    bb = part.bounding_box()
    return max(bb.size.X, bb.size.Y, bb.size.Z) * 2.0 + 10.0


def parting_line(part, plane: bd.Plane, height: float = 0.35,
                 width: float = 1.2):
    """Add the raised flash bead where the mould halves met.

    Takes the slice of `part` inside a `width`-thick slab about `plane`,
    offsets that slice outward by `height`, and fuses it back — so the bead
    follows the real silhouette all the way round, whatever the section, and
    stands proud by `height` with a soft (arc) crown.

    Cosmetic and non-fatal: on any failure the part comes back UNCHANGED with
    one warning line on stderr.
    """
    try:
        slab = _slab(plane, _span(part), width)
        band = part & slab
        if not is_sound(band):
            _warn("parting_line: plane misses the part (empty slice); skipped")
            return part
        bead = bd.offset(band, amount=height)
        if not is_sound(bead):
            _warn("parting_line: bead offset unsound; skipped")
            return part
        result = part + bead
        if not is_sound(result):
            _warn("parting_line: bead fuse unsound; skipped")
            return part
        return result
    except Exception as exc:  # never fatal — it is a cosmetic mark
        _warn(f"parting_line: {type(exc).__name__}: {exc}; skipped")
        return part


def machined_face(part, plane: bd.Plane, depth: float = 0.6):
    """Take a facing pass: remove every scrap of material on the +normal side
    of `plane`, leaving an exactly planar, crisp-edged machined face.

    This is how a casting gets a mating surface — the deck, the sump rail, a
    bearing cap joint. `depth` is the boolean OVERSHOOT beyond the part's own
    extent, keeping the tool's far faces clear of the part so no coplanar-face
    boolean is attempted.

    Returns the cut part; a plane that removes nothing (entirely outside the
    part) returns it unchanged with a warning.
    """
    try:
        span = _span(part)
        cutter = _slab(plane, span, span + depth, align_z=bd.Align.MIN)
        result = part - cutter
        if not is_sound(result):
            _warn("machined_face: cut unsound; part left as cast")
            return part
        if abs(result.volume - part.volume) < _EPS:
            _warn("machined_face: plane removes no material; part unchanged")
            return part
        return result
    except Exception as exc:
        _warn(f"machined_face: {type(exc).__name__}: {exc}; part left as cast")
        return part


def machined_skin(part, plane: bd.Plane, t: float = 0.3):
    """The thin bright skin lying ON the machined face, for colouring.

    Returns the top `t` mm of `part` immediately BELOW `plane` (the -normal
    side), so it sits exactly flush with the machined surface. Colour it
    `palette.MACHINED` and carry it as a separate labelled child:

        body = machined_face(body, deck)
        skin = machined_skin(body, deck)
        body = body - skin                       # keep the solids disjoint
        deck_face = palette.style(skin, "deck_face", palette.MACHINED)
        assembly = bd.Compound(children=[body, deck_face])

    Returns `None` (with a warning) when the plane misses the part.
    """
    try:
        slab = _slab(plane, _span(part), t, align_z=bd.Align.MAX)
        skin = part & slab
        if not is_sound(skin):
            _warn("machined_skin: no material under the plane; no skin")
            return None
        return skin
    except Exception as exc:
        _warn(f"machined_skin: {type(exc).__name__}: {exc}; no skin")
        return None


# ---------------------------------------------------------------------------
# Booleans.  One list operation, gated; batching only as a fallback.
# ---------------------------------------------------------------------------

def fuse_all(parts: Iterable):
    """Fuse everything in ONE multi-operand operation (`first + [rest]`).

    Accumulating pairwise re-runs the whole intersection network per step and
    decays O(n^2), so the single fuse is the fast path AND the correct one. If
    it comes back unsound the fallback IS pairwise, gated per step, keeping the
    last sound body and warning about each operand it had to drop.
    """
    items = [p for p in parts if p is not None]
    if not items:
        raise ValueError("fuse_all(): nothing to fuse")
    if len(items) == 1:
        return items[0]
    # OCCT booleans can MUTATE their operands when they fail, so every attempt
    # runs on deep copies and the originals stay pristine for the fallback
    # (a failed multi-fuse used to poison the pairwise retry into dropping
    # perfectly good bodies — see the turbo builder's report).
    import copy as _copy

    try:
        result = _copy.deepcopy(items[0]) + [_copy.deepcopy(p) for p in items[1:]]
        if is_sound(result):
            return result
    except Exception as exc:
        _warn(f"fuse_all: multi-fuse raised {type(exc).__name__}; going pairwise")
    else:
        _warn("fuse_all: multi-fuse unsound; going pairwise")

    current = items[0]
    for i, piece in enumerate(items[1:], start=1):
        try:
            candidate = _copy.deepcopy(current) + _copy.deepcopy(piece)
        except Exception:
            candidate = None
        if candidate is not None and is_sound(candidate):
            current = candidate
        else:
            _warn(f"fuse_all: dropped operand {i} (unsound fuse)")
    return current


def _bbox_hits(a, b, pad: float = 1e-6) -> bool:
    ba, bb = a.bounding_box(), b.bounding_box()
    return not (
        ba.max.X < bb.min.X - pad or bb.max.X < ba.min.X - pad
        or ba.max.Y < bb.min.Y - pad or bb.max.Y < ba.min.Y - pad
        or ba.max.Z < bb.min.Z - pad or bb.max.Z < ba.min.Z - pad
    )


def _disjoint_families(tools: list) -> list:
    """Greedily pack tools into batches whose members do not overlap each
    other (by bounding box). Tools that overlap each other deep below the
    surface are the pathological case for a single multi-tool cut."""
    families: list[list] = []
    for tool in tools:
        for fam in families:
            if all(not _bbox_hits(tool, other) for other in fam):
                fam.append(tool)
                break
        else:
            families.append([tool])
    return families


def cut_all(part, tools: Iterable):
    """Subtract every tool in ONE list operation (`part - [a, b, c]`).

    Never accumulate cuts pairwise. When the single operation fails or comes
    back unsound — tools that overlap each other can make a multi-tool cut emit
    detached plugs and knife-edge slivers — it retries in internally disjoint
    families, then tool by tool, dropping only what genuinely cannot cut.
    """
    tool_list = [t for t in tools if t is not None]
    if not tool_list:
        return part
    try:
        result = part - tool_list
        if is_sound(result):
            return result
    except Exception as exc:
        _warn(f"cut_all: multi-cut raised {type(exc).__name__}; batching")
    else:
        _warn("cut_all: multi-cut unsound; batching in disjoint families")

    current = part
    for family in _disjoint_families(tool_list):
        try:
            candidate = current - family
        except Exception:
            candidate = None
        if candidate is not None and is_sound(candidate):
            current = candidate
            continue
        for i, tool in enumerate(family):
            try:
                one = current - tool
            except Exception:
                one = None
            if one is not None and is_sound(one):
                current = one
            else:
                _warn(f"cut_all: dropped a tool ({i}) that could not cut")
    return current


__all__ = [
    "BOP_CHECK",
    "frame",
    "locate",
    "is_sound",
    "edge_center",
    "edges_at",
    "safe_fillet",
    "safe_chamfer",
    "fillet_all",
    "soften",
    "drafted_prism",
    "cast_body",
    "boss",
    "rib",
    "web",
    "parting_line",
    "machined_face",
    "machined_skin",
    "fuse_all",
    "cut_all",
]


# ---------------------------------------------------------------------------
# Self-test: build one of everything at W16 scale and gate it.
#   /Users/.../.venv/bin/python src/lib/castings.py
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import time

    t_start = time.time()
    failures: list[str] = []

    def check(name: str, ok: bool, note: str = "") -> None:
        print(f"  {'ok  ' if ok else 'FAIL'}  {name}{'  ' + note if note else ''}")
        if not ok:
            failures.append(name)

    # 1. drafted prism, softened all over -------------------------------------
    print("drafted prism + soften")
    prism = drafted_prism(bd.Rectangle(160, 110), 70, draft_deg=3.0, top_r=6.0)
    prism, r_soft = soften(prism, 5.0)
    bb = prism.bounding_box()
    check("prism sound", is_sound(prism),
          f"r={r_soft}  vol={prism.volume:,.0f}  z={bb.min.Z:.1f}..{bb.max.Z:.1f}")

    # 2. boss fused into a plate, root fillet, then drilled --------------------
    print("boss + plate + root fillet")
    solo = boss(30, 26, draft_deg=3.0, fillet_r=2.5, hole_d=10.0)
    sb = solo.bounding_box()
    check("standalone bored boss sound", is_sound(solo),
          f"base d={sb.size.X:.1f}  h={sb.size.Z:.1f}")

    # Cast first (no bore), fuse, blend the root, THEN machine the hole through
    # both bodies -- the order the real part is made in, and the only order that
    # leaves a true through-hole rather than a 1 mm dish in the plate.
    plate = bd.extrude(bd.Rectangle(150, 100), amount=14)
    stud = bd.Pos(40, 0, 14) * boss(30, 26, draft_deg=3.0, fillet_r=2.5)
    plated = fuse_all([plate, stud])
    root = edges_at(plated, z=14, near=(40, 0, 14), kind="CIRCLE")
    plated, r_root = safe_fillet(plated, root, 4.0)
    drill = bd.Pos(40, 0, -1) * bd.Cylinder(5.0, 44.0, align=(None, None, None))
    plated = cut_all(plated, [drill])
    thru = edges_at(plated, z=0, near=(40, 0, 0), kind="CIRCLE")
    check("boss on plate sound", is_sound(plated) and r_root is not None
          and len(root) == 1 and len(thru) == 1,
          f"{len(root)} root edge, fillet r={r_root}, bore breaks through"
          f"  vol={plated.volume:,.0f}")

    # 3. cast rib -------------------------------------------------------------
    print("rib")
    stiffener = rib(90, 34, 9, draft_deg=3.0, end_r=2.0, top_r=2.0)
    rb = stiffener.bounding_box()
    check("rib sound", is_sound(stiffener),
          f"x={rb.min.X:.1f}..{rb.max.X:.1f}  y={rb.size.Y:.1f}  z={rb.size.Z:.1f}")

    # 4. web ------------------------------------------------------------------
    print("web")
    wall = web([(0, 0), (60, 0), (60, 45), (110, 45)], thickness=7.0, height=28.0)
    check("web sound", is_sound(wall), f"vol={wall.volume:,.0f}")

    # 5. parting line on a softened box ---------------------------------------
    print("parting line")
    blank = bd.Box(120, 80, 60)
    blank, r_blank = soften(blank, 6.0)
    before = blank.bounding_box().size.Z
    marked = parting_line(blank, frame((0, 0, 0), (0, 0, 1)), height=0.35, width=1.2)
    grew = marked.bounding_box().size.X - blank.bounding_box().size.X
    check("parting line sound", is_sound(marked) and grew > 0.3,
          f"cast r={r_blank}  bead proud {grew / 2:.2f} mm/side")

    # 6. machined face + skin on a rounded block ------------------------------
    print("machined face + skin")
    block, r_block = cast_body(bd.Rectangle(140, 95), 55, draft_deg=3.0, edge_r=6.0)
    deck = frame((0, 0, 50), (0, 0, 1))
    decked = machined_face(block, deck, depth=0.6)
    skin = machined_skin(decked, deck, t=0.3)
    top_faces = [
        f for f in decked.faces()
        if abs(f.center().Z - 50) < 1e-6 and f.normal_at().Z > 0.99
    ]
    check("machined face planar", is_sound(decked) and len(top_faces) == 1,
          f"cast r={r_block}  face area={top_faces[0].area:,.0f} mm2"
          if top_faces else "no planar top face")
    check("machined skin", skin is not None and is_sound(skin)
          and abs(skin.bounding_box().max.Z - 50) < 1e-6,
          f"t={skin.bounding_box().size.Z:.2f}  vol={skin.volume:,.0f}"
          if skin else "none")
    body = cut_all(decked, [skin]) if skin else decked
    check("body minus skin sound", is_sound(body))

    # 7. frames: place a rib on a 45 deg bank face ----------------------------
    print("frame / locate")
    bank_z = (0.0, -math.sin(math.radians(45)), math.cos(math.radians(45)))
    placed = locate(stiffener, (200, 0, 120), bank_z, x_dir=(1, 0, 0))
    pl = frame((200, 0, 120), bank_z, x_dir=(1, 0, 0))
    # every vertex measured along the frame normal: base on the plane (0),
    # crown exactly `height` above it -- i.e. local +Z really is the bank axis
    heights = [(bd.Vector(*tuple(v)) - pl.origin).dot(pl.z_dir)
               for v in placed.vertices()]
    check("locate puts local +Z on the bank axis",
          is_sound(placed) and abs(min(heights)) < 1e-6
          and abs(max(heights) - 34) < 1e-6,
          f"z_dir={tuple(round(v, 3) for v in tuple(pl.z_dir))}  "
          f"rib spans {min(heights):.1f}..{max(heights):.1f} off the bank face")
    # .moved() composes; .located() would have thrown the rotation away
    spun = stiffener.rotate(bd.Axis.Z, 90)
    check("locate composes with an existing rotation",
          abs(locate(spun, (0, 0, 0), (0, 0, 1)).bounding_box().size.Y - 90) < 1e-6)

    # 8. lead-in chamfer on the machined face ---------------------------------
    print("machined lead-in chamfer")
    chamfered, c_len = safe_chamfer(decked, edges_at(decked, z=50), 1.0)
    check("machined face chamfer", is_sound(chamfered) and c_len is not None,
          f"lead-in {c_len} mm")

    # 9. the sliver guard: this body SIGSEGVs without skip_narrow -------------
    print("sliver guard")
    sliver = bd.Box(60, 40, 20) - bd.Pos(0, 0, 10 - 0.075) * bd.Box(10, 50, 0.15)
    guarded, r_guard = fillet_all(sliver, 2.0)
    check("0.15 mm step survives fillet_all", is_sound(guarded)
          and r_guard is not None, f"r={r_guard}, step edges skipped")

    # 10. no-op guards --------------------------------------------------------
    print("guards (warnings below are expected)")
    away = frame((0, 0, 500), (0, 0, 1))
    check("machined_face off-part is a no-op",
          machined_face(block, away).volume == block.volume)
    check("machined_skin off-part returns None", machined_skin(block, away) is None)
    check("parting_line off-part returns the part",
          parting_line(block, away).volume == block.volume)

    print(f"\n{len(failures)} failure(s)  ({time.time() - t_start:.1f} s)")
    if failures:
        print("  " + ", ".join(failures))
        raise SystemExit(1)
