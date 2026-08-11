"""Shared geometry vocabulary for the F1 concept car.

Every part module builds from these helpers so the car has ONE surface
language. Read `spec.py` first — it states the coordinate system and the
design rules these helpers implement.

The three primitives that matter:

  * `airfoil_face()` / `wing_element()` — every aerodynamic surface
  * `blade_face()`   / `blade_member()` — every structural member in the flow
  * `section_face()` / `body_loft()`    — every sculpted bodywork volume

All of them return build123d shapes already positioned in CAR coordinates.
"""

from __future__ import annotations

import math
from typing import Iterable, Sequence

from build123d import (
    Axis,
    Color,
    Compound,
    Edge,
    Face,
    Line,
    Location,
    Plane,
    Pos,
    Rotation,
    Shape,
    Solid,
    Spline,
    Vector,
    Wire,
    chamfer,
    fillet,
    loft,
    make_face,
    mirror,
)

from . import spec

FLOW = Vector(-1, 0, 0)  # local flow direction: air runs toward -X


# ==========================================================================
# labelling / grouping
# ==========================================================================


def as_body(shape):
    """Normalise a boolean result into ONE addressable body.

    build123d returns a plain Python list (not a Compound) when a cut leaves
    disjoint solids — e.g. a bolt-on pad trimmed against a ribbed casting that
    ends up as two islands either side of a rib. That list is not a tree node,
    so it detonates much later with anytree's "Cannot add non-node object"
    from inside the assembly build, pointing at the assembly rather than at
    the boolean that actually produced it. Fold it into a Compound here.
    """
    if isinstance(shape, (list, tuple)):
        parts = [s for s in shape if s is not None and getattr(s, "wrapped", None)]
        if not parts:
            return None
        return parts[0] if len(parts) == 1 else Compound(children=parts)
    return shape


def styled(shape, label: str, color: Color):
    """Label + colour one body. Every exported solid must go through this."""
    shape = as_body(shape)
    if shape is None:
        return None
    shape.label = label
    shape.color = color
    return shape


def group(label: str, children: Iterable) -> Compound:
    """Bundle labelled bodies into one labelled compound (a part)."""
    kids = [c for c in children if c is not None]
    comp = Compound(children=kids)
    comp.label = label
    return comp


def mirror_y(shape):
    """Mirror a shape across the car centreline plane (y = 0)."""
    return mirror(shape, about=Plane.XZ)


def pair(shape, label: str, color: Color | None = None):
    """Build the left body and its mirrored right twin as two labelled bodies.

    The input must be modelled on the LEFT (+Y) side.
    """
    left = shape
    right = mirror_y(shape)
    if color is not None:
        styled(left, f"{label}:left", color)
        styled(right, f"{label}:right", color)
    else:
        left.label = f"{label}:left"
        right.label = f"{label}:right"
        if getattr(shape, "color", None) is not None:
            right.color = shape.color
    return [left, right]


# ==========================================================================
# robust boolean / fillet helpers
# ==========================================================================


def safe_fillet(part, edges, ladder: Sequence[float] = spec.FILLET_LADDER):
    """Fillet with a descending radius ladder; return the first success.

    3D fillets after booleans are the single most failure-prone operation in
    this model, so every cosmetic fillet goes through here and the model
    survives (unfilleted) rather than crashing the build.
    """
    try:
        edge_list = list(edges)
    except Exception:
        return part
    if not edge_list:
        return part
    for r in ladder:
        try:
            out = fillet(edge_list, r)
            if out is not None and out.is_valid:
                return out
        except Exception:
            continue
    return part


def safe_chamfer(part, edges, length: float, length2: float | None = None):
    try:
        edge_list = list(edges)
    except Exception:
        return part
    if not edge_list:
        return part
    for scale in (1.0, 0.6, 0.35, 0.15):
        try:
            if length2 is not None:
                out = chamfer(edge_list, length * scale, length2 * scale)
            else:
                out = chamfer(edge_list, length * scale)
            if out is not None and out.is_valid:
                return out
        except Exception:
            continue
    return part


def is_valid_shape(shape) -> bool:
    """True only if OCC's checker passes AND the volume is positive.

    `Shape.is_valid` alone is not enough: OCC will report a shell with a large
    NEGATIVE volume as valid (an inverted orientation), and that body then
    exports and renders as a hole in the world. Always ask for both.
    """
    from OCP.BRepCheck import BRepCheck_Analyzer

    try:
        if shape is None or shape.wrapped is None:
            return False
        if not BRepCheck_Analyzer(shape.wrapped).IsValid():
            return False
        return shape.volume > 0.0
    except Exception:
        return False


def repair(shape, precision: float = 1e-4, max_tolerance: float = 1e-2):
    """Heal a topologically invalid solid produced by a boolean.

    A cut through a sculpted loft routinely leaves ONE bad face — a wire whose
    trim is a hair off the surface — while the geometry is otherwise exactly
    right. The body still has the correct volume and bounds, but every
    subsequent boolean against it returns a null shape, so the failure surfaces
    far from its cause. Running ShapeFix here turns that into a local, cheap
    repair. Returns the original shape if the repair does not improve it.
    """
    from OCP.ShapeFix import ShapeFix_Shape

    if is_valid_shape(shape):
        return shape
    try:
        fixer = ShapeFix_Shape(shape.wrapped)
        fixer.SetPrecision(precision)
        fixer.SetMaxTolerance(max_tolerance)
        fixer.Perform()
        healed = Shape.cast(fixer.Shape())
        if healed is None:
            solids = Solid(fixer.Shape()).solids()
            healed = solids[0] if solids else None
        if healed is not None and is_valid_shape(healed):
            healed.label = getattr(shape, "label", "") or ""
            if getattr(shape, "color", None) is not None:
                healed.color = shape.color
            return healed
    except Exception:
        pass
    return shape


def cut(target, tool):
    """Boolean subtract, then heal — the combination this model always wants."""
    return repair(target - tool)


def fuse_all(base, others):
    """Fuse a list onto a base, healing between steps.

    Fusing onto an already-invalid solid is what produces OCC's
    "Null TopoDS_Shape object", and the traceback then points at the fuse
    rather than at whichever earlier operation actually broke the body.
    """
    out = repair(base)
    for other in others:
        if other is None:
            continue
        try:
            fused = out + repair(other)
            out = repair(fused)
        except Exception:
            continue
    return out


def obox(shape):
    """TIGHT bounds. `bbox()` is pole-based and over-reports on B-splines."""
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib

    box = Bnd_Box()
    BRepBndLib.AddOptimal_s(shape.wrapped, box, False, True)
    v = box.Get()
    return v[:3], v[3:]


def _sections_box(faces: Sequence[Face]):
    lo = [float("inf")] * 3
    hi = [float("-inf")] * 3
    for f in faces:
        a, b = obox(f)
        for i in range(3):
            lo[i] = min(lo[i], a[i])
            hi[i] = max(hi[i], b[i])
    return lo, hi


def loft_escaped(solid, faces: Sequence[Face], margin_frac: float = 0.06) -> bool:
    """True if a lofted solid strays outside the box of its own sections.

    A smooth loft is allowed to bow slightly between stations, so the test
    carries a real margin; what it catches is the pathological case where OCC's
    smooth loft WANDERS — hundreds of millimetres outside every section it was
    built from — while still reporting a valid, watertight, positive-volume
    solid. Nothing in the normal validation chain sees that.
    """
    lo, hi = _sections_box(faces)
    diag = math.dist(lo, hi) or 1.0
    slack = max(3.0, margin_frac * diag)
    try:
        a, b = obox(solid)
    except Exception:
        return False
    for i in range(3):
        if a[i] < lo[i] - slack or b[i] > hi[i] + slack:
            return True
    return False


def loft_solid(faces: Sequence[Face], ruled: bool = False):
    """Loft a section stack; fall back to ruled if the smooth loft misbehaves.

    Two independent failure modes, and only the first is loud:

      1. the loft raises, or returns an invalid / zero-volume shape;
      2. the loft SUCCEEDS and returns a perfectly valid watertight solid that
         is the wrong shape — OCC's smooth loft can wander far outside the
         sections it interpolates. That produced a wheel cover whose vane
         cutter escaped its sections by ~200 mm, gouged through to the rim, and
         exported a 190 MB component GLB; it differed front-to-rear only
         because the excursion is sensitive to the sections' absolute Y, so
         two corners of the car silently disagreed with the other two.

    Case 2 passes `is_valid`, passes watertightness, passes a positive-volume
    check, and passes `inspect refs`. Only comparing the result against its own
    input sections catches it, which is what `loft_escaped` does.
    """
    fs = [f for f in faces if f is not None]
    if len(fs) < 2:
        raise ValueError("loft_solid needs at least two sections")
    try:
        out = loft(fs, ruled=ruled)
        if (
            out is not None
            and out.is_valid
            and out.volume > 0
            and not loft_escaped(out, fs)
        ):
            return out
    except Exception:
        pass
    return loft(fs, ruled=True)


# ==========================================================================
# AIRFOIL — the one aerodynamic section family
# ==========================================================================


def _naca_points(
    chord: float,
    thickness: float,
    camber: float,
    camber_pos: float,
    n: int,
    te_thickness: float,
):
    """Closed airfoil loop in LOCAL 2D coords: LE at (0,0), TE at (chord, 0).

    `camber` is stated POSITIVE for a downforce-generating (inverted) section;
    internally the mean line bows the other way so local +y stays "up".
    """
    m = -abs(camber)
    p = min(max(camber_pos, 0.15), 0.75)
    te_frac = max(te_thickness, spec.TE_THICKNESS) / max(chord, 1e-6)

    def half_t(x: float) -> float:
        # NACA 4-digit thickness, re-closed to a finite trailing edge so the
        # solid is manufacturable and still reads as a genuinely thin edge.
        base = 5.0 * thickness * (
            0.2969 * math.sqrt(x)
            - 0.1260 * x
            - 0.3516 * x * x
            + 0.2843 * x**3
            - 0.1036 * x**4
        )
        return base + 0.5 * te_frac * x

    def mean(x: float):
        if m == 0.0:
            return 0.0, 0.0
        if x < p:
            return m / (p * p) * (2 * p * x - x * x), 2 * m / (p * p) * (p - x)
        return (
            m / ((1 - p) ** 2) * ((1 - 2 * p) + 2 * p * x - x * x),
            2 * m / ((1 - p) ** 2) * (p - x),
        )

    upper, lower = [], []
    for i in range(n):
        beta = math.pi * i / (n - 1)
        x = 0.5 * (1.0 - math.cos(beta))  # cosine clustering: clean LE + TE
        t = half_t(x)
        yc, dyc = mean(x)
        a = math.atan(dyc)
        sa, ca = math.sin(a), math.cos(a)
        upper.append(((x - t * sa) * chord, (yc + t * ca) * chord))
        lower.append(((x + t * sa) * chord, (yc - t * ca) * chord))
    return upper, lower


def airfoil_profile(
    chord: float,
    thickness: float = 0.095,
    camber: float = 0.055,
    camber_pos: float = 0.40,
    samples: int = 37,
    te_thickness: float | None = None,
):
    """Closed planar wire of one airfoil section, in local 2D coords."""
    te = spec.TE_THICKNESS if te_thickness is None else te_thickness
    upper, lower = _naca_points(chord, thickness, camber, camber_pos, samples, te)
    top = Spline(*upper)
    bot = Spline(*lower)
    tail = Line(top @ 1, bot @ 1)
    return top + tail + bot


def section_plane(origin, twist_deg: float = 0.0, sweep_deg: float = 0.0):
    """Plane for a spanwise section: local +x = rearward, local +y = up.

    `twist_deg` positive rotates the trailing edge UP (more downforce).
    `sweep_deg` yaws the section about the vertical so a swept element's
    sections stay perpendicular to its own span rather than to Y.

    The frame is built from explicit direction vectors rather than by calling
    `Plane.rotated()`. build123d 0.10's `Plane.rotated()` composes its matrix
    in WORLD axes, not the plane's own, so `rotated((0, 0, a))` on this frame
    is a yaw about world Z — not the pitch the name implies. Driving incidence
    through it silently produced elements that lay flat and slid sideways
    along their own span (a 34 deg "twist" moved a flap 56 mm outboard and
    0 mm up) while still passing every solid/watertight check. Composing the
    two rotations here in the right order also keeps twist a true pitch on a
    SWEPT element, which swapping the two `rotated()` calls would not.
    """
    t = math.radians(twist_deg)
    s = math.radians(sweep_deg)
    ct, st = math.cos(t), math.sin(t)
    cs, ss = math.cos(s), math.sin(s)
    # pitch the chord line about the span axis, then yaw the whole frame
    x_dir = Vector(-ct * cs, -ct * ss, st)
    normal = Vector(-ss, cs, 0.0)
    return Plane(origin=Vector(*origin), x_dir=x_dir, z_dir=normal)


def airfoil_face(
    origin,
    chord: float,
    twist_deg: float = 0.0,
    thickness: float = 0.095,
    camber: float = 0.055,
    camber_pos: float = 0.40,
    sweep_deg: float = 0.0,
    te_thickness: float | None = None,
    samples: int = 37,
) -> Face:
    """One airfoil section placed in car coordinates.

    `origin` is the LEADING EDGE point (x, y, z). The section is rotated about
    its own leading edge, which is what makes a cascade's slot gaps behave.
    """
    wire = airfoil_profile(
        chord,
        thickness=thickness,
        camber=camber,
        camber_pos=camber_pos,
        samples=samples,
        te_thickness=te_thickness,
    )
    plane = section_plane(origin, twist_deg=twist_deg, sweep_deg=sweep_deg)
    return plane * make_face(wire)


def wing_element(stations: Sequence[dict], ruled: bool = False):
    """Loft an aerodynamic element through spanwise stations.

    Each station dict: {le: (x,y,z), chord, twist, thickness, camber,
    camber_pos, sweep, te}. Missing keys fall back to the section-family
    defaults, which is how every element ends up in the same family.
    """
    faces = []
    for st in stations:
        faces.append(
            airfoil_face(
                st["le"],
                st["chord"],
                twist_deg=st.get("twist", 0.0),
                thickness=st.get("thickness", 0.095),
                camber=st.get("camber", 0.055),
                camber_pos=st.get("camber_pos", 0.40),
                sweep_deg=st.get("sweep", 0.0),
                te_thickness=st.get("te"),
                samples=st.get("samples", 37),
            )
        )
    return loft_solid(faces, ruled=ruled)


def cascade_stations(
    n_elements: int,
    span_stations: Sequence[float],
    root_chord: float = spec.FW_ROOT_CHORD,
    chord_ratio: float = spec.CHORD_RATIO,
) -> list[float]:
    """Chord of each element in a rhythmic cascade (see spec rule 5)."""
    return [root_chord * chord_ratio**i for i in range(n_elements)]


# ==========================================================================
# BLADE — the one structural section family
# ==========================================================================


def blade_profile(chord: float, thickness_ratio: float = 0.30, samples: int = 25):
    """Symmetric teardrop: round nose, long thin tail. No camber."""
    upper, lower = _naca_points(
        chord, thickness_ratio, 0.0, 0.4, samples, spec.TE_THICKNESS
    )
    top = Spline(*upper)
    bot = Spline(*lower)
    tail = Line(top @ 1, bot @ 1)
    return top + tail + bot


def _ortho_basis(axis: Vector, prefer: Vector = FLOW):
    """Frame whose normal is `axis` and whose local +x hugs the flow."""
    n = Vector(axis).normalized()
    ref = Vector(prefer)
    if abs(ref.dot(n)) > 0.97:
        ref = Vector(0, 0, 1)
        if abs(ref.dot(n)) > 0.97:
            ref = Vector(0, 1, 0)
    x_dir = (ref - n * ref.dot(n)).normalized()
    return n, x_dir


def blade_face(
    center,
    axis,
    chord: float,
    thickness_ratio: float = 0.30,
    roll_deg: float = 0.0,
    samples: int = 25,
) -> Face:
    """One blade section normal to `axis`, centred on the member centreline.

    The section's quarter-chord sits on `center`, which is what makes a
    tapered member's centreline read straight.
    """
    n, x_dir = _ortho_basis(Vector(axis))
    if roll_deg:
        # Rodrigues about the MEMBER AXIS, so a rolled section stays normal to
        # its own path. `Plane.rotated()` would roll about world Z instead and
        # tip the section out of the member — same trap as section_plane().
        r = math.radians(roll_deg)
        x_dir = (x_dir * math.cos(r) + n.cross(x_dir) * math.sin(r)).normalized()
    plane = Plane(origin=Vector(center), x_dir=x_dir, z_dir=n)
    wire = blade_profile(chord, thickness_ratio=thickness_ratio, samples=samples)
    face = make_face(wire)
    # centre the section on its quarter-chord point
    face = Location((-0.25 * chord, 0, 0)) * face
    return plane * face


def blade_member(
    p0,
    p1,
    chord0: float,
    chord1: float | None = None,
    thickness_ratio: float = 0.30,
    roll_deg: float = 0.0,
    samples: int = 25,
):
    """A straight tapered blade from p0 to p1 — the suspension vocabulary."""
    a, b = Vector(p0), Vector(p1)
    axis = b - a
    c1 = chord0 if chord1 is None else chord1
    f0 = blade_face(a, axis, chord0, thickness_ratio, roll_deg, samples)
    f1 = blade_face(b, axis, c1, thickness_ratio, roll_deg, samples)
    return loft_solid([f0, f1], ruled=True)


def blade_path(points: Sequence, chords: Sequence[float], thickness_ratio: float = 0.30,
               roll_deg: float = 0.0, samples: int = 25):
    """A curved blade through a polyline of centreline points."""
    pts = [Vector(p) for p in points]
    faces = []
    for i, p in enumerate(pts):
        if i == 0:
            axis = pts[1] - pts[0]
        elif i == len(pts) - 1:
            axis = pts[-1] - pts[-2]
        else:
            axis = pts[i + 1] - pts[i - 1]
        faces.append(
            blade_face(p, axis, chords[i], thickness_ratio, roll_deg, samples)
        )
    return loft_solid(faces, ruled=False)


# ==========================================================================
# BODY SECTIONS — sculpted bodywork volumes
# ==========================================================================


def section_face(x: float, pts_yz: Sequence[Sequence[float]], periodic: bool = True) -> Face:
    """A closed bodywork cross-section at station x, from (y, z) points.

    The plane at station x has local +x = car +Y and local +y = car +Z, so the
    points you write read exactly like a front-view sketch.
    """
    plane = Plane(origin=(x, 0, 0), x_dir=(0, 1, 0), z_dir=(1, 0, 0))
    pts = [(float(p[0]), float(p[1])) for p in pts_yz]
    if periodic:
        if (
            abs(pts[0][0] - pts[-1][0]) < 1e-9
            and abs(pts[0][1] - pts[-1][1]) < 1e-9
        ):
            pts = pts[:-1]
        wire = Spline(*pts, periodic=True)
        return plane * make_face(wire)
    curve = Spline(*pts)
    closing = Line(curve @ 1, curve @ 0)
    return plane * make_face(curve + closing)


def half_section_face(x: float, pts_yz: Sequence[Sequence[float]]) -> Face:
    """Closed section from a LEFT-side outline, mirrored across the centreline.

    `pts_yz` runs from the centreline bottom (y=0) out and over the top back to
    the centreline (y=0). The centreline closure is a straight line, which is
    what keeps a symmetric body's spine crisp instead of dimpled.
    """
    plane = Plane(origin=(x, 0, 0), x_dir=(0, 1, 0), z_dir=(1, 0, 0))
    pts = [(float(p[0]), float(p[1])) for p in pts_yz]
    right = [(-y, z) for (y, z) in reversed(pts[1:-1])]
    outline = pts + right
    wire = Spline(*outline, periodic=True)
    return plane * make_face(wire)


def body_loft(sections: Sequence[Face], ruled: bool = False):
    """Loft sculpted bodywork through a station stack."""
    return loft_solid(sections, ruled=ruled)


def superellipse_pts(
    half_w: float,
    half_h: float,
    n_top: float = 2.6,
    n_bot: float = 2.2,
    cy: float = 0.0,
    cz: float = 0.0,
    samples: int = 28,
):
    """Superellipse outline in (y, z) — the default bodywork cross-section.

    n = 2 is an ellipse; higher n squares the corners off. Different exponents
    above and below the waist give the flat-topped / tucked-under look.
    """
    pts = []
    for i in range(samples):
        a = 2.0 * math.pi * i / samples
        ca, sa = math.cos(a), math.sin(a)
        n = n_top if sa >= 0 else n_bot
        y = cy + half_w * math.copysign(abs(ca) ** (2.0 / n), ca)
        z = cz + half_h * math.copysign(abs(sa) ** (2.0 / n), sa)
        pts.append((y, z))
    return pts


# ==========================================================================
# small reusable detail geometry
# ==========================================================================


def rounded_plate_pts(
    length: float,
    height: float,
    corner: float,
    samples: int = 6,
):
    """(u, v) outline of a plate with rounded corners, centred on the origin."""
    hl, hh, r = length / 2.0, height / 2.0, corner
    pts = []
    corners = [
        (hl - r, hh - r, 0.0),
        (-hl + r, hh - r, math.pi / 2),
        (-hl + r, -hh + r, math.pi),
        (hl - r, -hh + r, 3 * math.pi / 2),
    ]
    for cu, cv, a0 in corners:
        for i in range(samples + 1):
            a = a0 + (math.pi / 2) * i / samples
            pts.append((cu + r * math.cos(a), cv + r * math.sin(a)))
    return pts


def swept_plate(
    stations: Sequence[dict],
    ruled: bool = False,
):
    """Loft a plate (endplate, fence, strake) through stations.

    Each station: {plane: Plane, pts: [(u,v), ...]}. Written this way so a
    plate can twist and curl along its length instead of being an extrusion.
    """
    faces = []
    for st in stations:
        wire = Spline(*st["pts"], periodic=True)
        faces.append(st["plane"] * make_face(wire))
    return loft_solid(faces, ruled=ruled)


def plate_plane(origin, normal, up=(0, 0, 1)):
    """Plane for a plate section: local +x along flow-ish, +y toward `up`."""
    n = Vector(normal).normalized()
    u = Vector(up)
    if abs(u.dot(n)) > 0.97:
        u = Vector(1, 0, 0)
    y_dir = (u - n * u.dot(n)).normalized()
    x_dir = y_dir.cross(n).normalized()
    return Plane(origin=Vector(origin), x_dir=x_dir, z_dir=n)


def accent_stripe_solid(base_solid, plane: Plane, thickness: float):
    """Intersect a body with a thin slab to make a flush accent stripe."""
    from build123d import Box

    slab = plane * Box(4000, 4000, thickness)
    try:
        return base_solid & slab
    except Exception:
        return None


def bbox(shape):
    """Exact bounding box WITHOUT tessellating the shape.

    `Shape.bounding_box()` triangulates, which mutates the shared TShape and
    breaks cadgen's content-addressed component dedup. Always use this instead.
    Returns ((xmin, ymin, zmin), (xmax, ymax, zmax)).
    """
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib

    box = Bnd_Box()
    BRepBndLib.Add_s(shape.wrapped, box, False)
    xmin, ymin, zmin, xmax, ymax, zmax = box.Get()
    return (xmin, ymin, zmin), (xmax, ymax, zmax)


def bbox_size(shape):
    lo, hi = bbox(shape)
    return tuple(hi[i] - lo[i] for i in range(3))


def taper(a: float, b: float, t: float, ease: float = 1.0) -> float:
    """Eased interpolation for taper laws; ease>1 biases toward `a`."""
    t = min(max(t, 0.0), 1.0)
    return a + (b - a) * (t**ease)


def arc_pts(center, radius: float, a0: float, a1: float, n: int = 12, plane_axes=("y", "z")):
    """Sample an arc in a named coordinate pair — handy for section outlines."""
    out = []
    for i in range(n + 1):
        a = math.radians(a0 + (a1 - a0) * i / n)
        out.append((center[0] + radius * math.cos(a), center[1] + radius * math.sin(a)))
    return out
