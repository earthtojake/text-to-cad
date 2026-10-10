"""Thin-walled parts as Reissner-Mindlin shells: the fit ladder's ``idealise`` rung for a thin plate.

A part is a thin plate when it is unambiguously one: every face is a skin face
(planar, at one of two levels a thickness ``t`` apart, facing out of them) or
a side face (its normal everywhere across the thickness), the two skins have
the same area, the volume is that area times ``t``, :func:`assembly._thickness`
reads the same ``t``, and ``t`` is under :data:`THIN` of the plate's smaller
span. Anything else (a step in thickness, a rib, a bend) is left solid.

The plate is then solved on its mid-surface: three-node triangles with six
DOF per node (membrane, Reissner-Mindlin bending, a small drilling stiffness),
the transverse shear reduced to its edge-tangential tying values (MITC3: the
reduced shear integration that keeps linear triangles from locking) and
stabilised as Lyly, Stenberg and Vihinen do (shear stiffness times
t^2 / (t^2 + alpha h^2)). Stresses are recovered at the top and bottom fibres,
smoothed to the nodes by a patch fit, and mapped with the displacement onto
the solid part's own surface (the "carrier": the coarse mesh run.py makes of
the real part), so the GLB shows the part, its faces and their refs, never a
sheet. Loads and fixtures keep their meaning: a skin face is the mid-surface
under it, a side face the mid-surface's edge along it.

Static is the first adopter (:func:`solve`). A laminate (the composite
analysis) takes the same mid-surface, loads and fixtures
(:func:`solve_mid_surface`) with classical laminate theory's A, B and D and a
transverse shear stiffness in place of the isotropic plane-stress matrices
(:meth:`ShellModel.element_matrices`'s ``abd``). Modal and buckling would add, on
the same mesh and DOF numbering: a consistent mass (rho t on the translations,
rho t^3/12 on the two bending rotations, none on the drilling one) and, for
buckling, the membrane geometric stiffness from this solve's membrane forces
(N_ab dw/dx_a dw/dx_b, plus the same on the in-plane displacements for a
curved shell); :meth:`ShellModel.element_matrices` is where they would join.

The helpers at the end (carrier triangles, nearest triangles, the outcome)
are shared with :mod:`.beam`. Stdlib at import; numeric work inside functions.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from cadgen._internal.fea.fit import Estimate, Geometry, Step

__all__ = ["THIN", "Plate", "detect", "estimate", "idealise", "solve"]

#: A plate is thin when its thickness is under this share of its smaller span (spec 9, rung 4).
THIN = 0.05
#: Lyly-Stenberg shear stabilisation: shear stiffness times t^2 / (t^2 + ALPHA h^2).
ALPHA = 0.1
#: Reissner-Mindlin's shear correction factor.
SHEAR_CORRECTION = 5.0 / 6.0
#: The drilling rotation's stiffness, as a share of E t A per element (it only keeps the system regular).
DRILLING = 1e-3
#: Mid-surface elements across the plate's smaller span (at least; the study's size may ask finer).
ACROSS = 30
#: At most this many elements across the smaller span, however fine the study's size.
MOST_ACROSS = 150
#: The mid-surface's elements along its edges are this many times smaller (netgen grades between).
EDGE_REFINE = 4.0
#: The carrier mesh (the real part, for the GLB only): elements across the smaller span.
CARRIER_ACROSS = 12
#: Skins must agree with each other and with the volume this closely to be one plate (relative).
AGREE = 0.01
#: _thickness and the skins' separation must agree this closely (relative).
THICKNESS_AGREE = 0.02
#: A normal is "along" or "across" the plate normal within this (cosine).
PARALLEL = 1e-6
ACROSS_TOL = 1e-4


# -- detection ----------------------------------------------------------------------------------------


@dataclass
class FaceRecord:
    ordinal: int
    face: Any
    area: float
    centroid: "tuple[float, float, float]"
    kind: str                                   # "plane", "cylinder", "other"
    normals: list                               # sampled outward unit normals, (k, 3)
    axis: "tuple[float, float, float] | None"   # a cylinder's axis direction
    axis_point: "tuple[float, float, float] | None"


@dataclass
class Plate:
    """A detected thin plate: its normal (out of the top skin), levels, thickness, span and faces by ordinal."""

    normal: "tuple[float, float, float]"
    top_level: float
    thickness: float
    span: float
    length: float
    area: float
    top: tuple[int, ...]
    bottom: tuple[int, ...]
    sides: tuple[int, ...]
    top_faces: list = field(default_factory=list, repr=False)

    @property
    def slenderness(self) -> float:
        return self.thickness / self.span

    @property
    def mid_level(self) -> float:
        return self.top_level - 0.5 * self.thickness


def face_records(shape) -> list[FaceRecord]:
    """Every face of ``shape`` in cadgen's ordinal order: area, centroid, kind and sampled outward normals."""
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.BRepGProp import BRepGProp, BRepGProp_Face
    from OCP.GeomAbs import GeomAbs_Cylinder, GeomAbs_Plane
    from OCP.gp import gp_Pnt, gp_Vec
    from OCP.GProp import GProp_GProps
    from OCP.TopoDS import TopoDS

    from cadgen._internal.entity_ordinals import entity_map

    records = []
    faces = entity_map(shape, "face")
    for ordinal in range(1, faces.Extent() + 1):
        face = TopoDS.Face_s(faces.FindKey(ordinal))
        props = GProp_GProps()
        BRepGProp.SurfaceProperties_s(face, props)
        centre = props.CentreOfMass()
        adaptor = BRepAdaptor_Surface(face)
        kind_id = adaptor.GetType()
        axis = point = None
        if kind_id == GeomAbs_Plane:
            kind = "plane"
        elif kind_id == GeomAbs_Cylinder:
            kind = "cylinder"
            placed = adaptor.Cylinder().Axis()
            axis = (placed.Direction().X(), placed.Direction().Y(), placed.Direction().Z())
            point = (placed.Location().X(), placed.Location().Y(), placed.Location().Z())
        else:
            kind = "other"
        sampler = BRepGProp_Face(face)
        u1, u2, v1, v2 = sampler.Bounds()
        normals = []
        for a in (0.2, 0.5, 0.8):
            for b in (0.2, 0.5, 0.8):
                p, v = gp_Pnt(), gp_Vec()
                sampler.Normal(u1 + a * (u2 - u1), v1 + b * (v2 - v1), p, v)
                length = v.Magnitude()
                if length > 0:
                    normals.append((v.X() / length, v.Y() / length, v.Z() / length))
        records.append(FaceRecord(ordinal, face, float(props.Mass()), (centre.X(), centre.Y(), centre.Z()), kind,
                                  normals, axis, point))
    return records


def obb_half_sizes(shape) -> list[tuple[float, tuple[float, float, float]]]:
    """The oriented bounding box's half sizes with their directions, smallest first."""
    from OCP.Bnd import Bnd_OBB
    from OCP.BRepBndLib import BRepBndLib

    box = Bnd_OBB()
    BRepBndLib.AddOBB_s(shape, box, True, True, False)
    pairs = [(box.XHSize(), box.XDirection()), (box.YHSize(), box.YDirection()), (box.ZHSize(), box.ZDirection())]
    return sorted((float(size), (d.X(), d.Y(), d.Z())) for size, d in pairs)


def _dot(a, b) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


_DETECTED: dict[int, tuple[Any, Any]] = {}


def cached(shape, kind: str, find):
    """``find(shape)`` once per shape and kind (the ladder estimates several times, then solves)."""
    key = hash((id(shape), kind))
    hit = _DETECTED.get(key)
    if hit is not None and hit[0] is shape:
        return hit[1]
    found = find(shape)
    if len(_DETECTED) > 16:
        _DETECTED.clear()
    _DETECTED[key] = (shape, found)
    return found


def detect(geometry: "Geometry") -> Plate | None:
    """The part as a thin plate, or ``None`` when it is not unambiguously one (see the module's rules)."""
    if geometry is None or geometry.shape is None:
        return None
    return cached(geometry.shape, "shell", lambda shape: _detect(shape, geometry.volume_mm3, geometry.area_mm2))


def _detect(shape, volume: float, area: float, thin: float = THIN) -> Plate | None:
    """The plate rules of the module; ``thin`` is the thickness-to-span ceiling (a laminate reads thick plates too)."""
    from cadgen._internal.fea.assembly import _thickness

    records = face_records(shape)
    planes = [r for r in records if r.kind == "plane" and r.normals]
    if not planes or not volume > 0:
        return None
    largest = max(planes, key=lambda r: r.area)
    n = largest.normals[0]
    top_level = _dot(n, largest.centroid)
    top, bottom, sides, levels = [], [], [], []
    for record in records:
        if not record.normals:
            return None
        along = [_dot(n, m) for m in record.normals]
        if record.kind == "plane" and all(abs(a - 1.0) < PARALLEL for a in along):
            if abs(_dot(n, record.centroid) - top_level) > 1e-6 * max(1.0, abs(top_level)) + 1e-9:
                return None   # a second top level: a step, a boss, a pocket
            top.append(record)
        elif record.kind == "plane" and all(abs(a + 1.0) < PARALLEL for a in along):
            levels.append(_dot(n, record.centroid))
            bottom.append(record)
        elif all(abs(a) < ACROSS_TOL for a in along):
            sides.append(record)
        else:
            return None
    if not bottom or max(levels) - min(levels) > 1e-6 * max(1.0, abs(top_level)) + 1e-9:
        return None
    t = top_level - levels[0]
    if not t > 0:
        return None
    top_area, bottom_area = sum(r.area for r in top), sum(r.area for r in bottom)
    if abs(top_area - bottom_area) > AGREE * top_area or abs(volume - top_area * t) > AGREE * volume:
        return None
    if abs(_thickness(shape, volume, area) - t) > THICKNESS_AGREE * t:
        return None
    halves = obb_half_sizes(shape)
    span, length = 2.0 * halves[1][0], 2.0 * halves[2][0]
    if not span > 0 or t / span >= thin:
        return None
    return Plate(tuple(n), top_level, t, span, length, top_area, tuple(r.ordinal for r in top),
                 tuple(r.ordinal for r in bottom), tuple(r.ordinal for r in sides), [r.face for r in top])


# -- the rung -----------------------------------------------------------------------------------------


def _usable(analysis, ctx) -> bool:
    """Static, one part, solid so far, and not yet cut by symmetry."""
    plan = ctx.plan
    return (getattr(analysis, "name", None) == "static" and getattr(ctx, "assembly", None) is None
            and plan.idealisation == "solid" and not plan.symmetry and ctx.geometry is not None)


def element_size(plate: Plate, requested: float | None) -> float:
    """The mid-surface's element size: the study's, at least ACROSS and at most MOST_ACROSS across the span."""
    size = plate.span / ACROSS
    if requested:
        size = min(size, float(requested))
    return max(size, plate.span / MOST_ACROSS)


def model_error_pct(slenderness: float) -> float:
    """Plate and beam theory's textbook model error against 3D elasticity, of order (t/L)^2, as a percentage."""
    return 100.0 * slenderness ** 2


def model_error_words(theory: str, ratio_name: str, slenderness: float, near: str) -> str:
    pct = model_error_pct(slenderness)
    return (f"{theory}'s model error at a {ratio_name} of {slenderness:.2g} is about {pct:.2g}% (of order the ratio squared); "
            f"within about one {near} of a fixture, a load or an edge the 3D stress is not resolved")


def idealise(analysis, ctx, inputs) -> "Step | None":
    """The ``idealise`` rung for a thin plate: the plan solves its mid-surface as a shell."""
    from cadgen._internal.fea.fit import Step

    if not _usable(analysis, ctx):
        return None
    plate = detect(ctx.geometry)
    if plate is None:
        return None
    plan = ctx.plan
    h = element_size(plate, plan.requested_mm)
    carrier = max(float(plan.requested_mm or 0.0), plate.span / CARRIER_ACROSS)
    plan.idealisation = "shell"
    undo_solid_rungs(plan)
    plan.size_mm = carrier
    words = (f"Solved the {plate.thickness:.3g} mm thin plate as its mid-surface (a shell) to fit; "
             "stresses are read at its top and bottom faces")
    accuracy = model_error_words("Plate theory", "thickness-to-span ratio", plate.slenderness, "thickness")
    return Step("idealise", words, accuracy, model_error_pct(plate.slenderness), detail={
        "idealisation": "shell", "thickness_mm": round(plate.thickness, 6), "span_mm": round(plate.span, 4),
        "slenderness": round(plate.slenderness, 6), "element_size_mm": round(h, 4),
        "elements": int(round(_triangles(plate.area, h))), "surface_mesh_mm": round(carrier, 4),
    })


def undo_solid_rungs(plan) -> None:
    """The idealised model replaces the solid solve: the rungs that only shrank it are undone (fit_budget unsays
    them). Its carrier is meshed quadratic and direct, as a study asked, with no second pass to refine."""
    if "iterative" in plan.taken:
        plan.solver = "direct"
    if "linear_elements" in plan.taken:
        plan.order = 2
    plan.refine_to_mm, plan.size_field = None, None


def _triangles(area: float, h: float) -> float:
    return 4.0 * area / (math.sqrt(3.0) * h * h)


def estimate(ctx) -> "Estimate":
    """The shell's cost: the carrier mesh and its element space (no solid solve), and a sparse direct
    solve of six DOF per mid-surface node."""
    plate = detect(ctx.geometry)
    h = element_size(plate, ctx.plan.requested_mm)
    nodes = _triangles(plate.area, h) + 1   # twice the uniform mesh's: the edges are graded finer
    return idealised_cost(ctx, 6 * nodes, 42.0)


def idealised_cost(ctx, dofs: float, per_row: float) -> "Estimate":
    """An idealised model's cost: its carrier mesh (meshed and given an element space for the GLB) and a
    sparse direct solve of ``dofs`` with about ``per_row`` entries a row."""
    from cadgen._internal.fea import fit

    elements, _, _ = fit.plan_counts(ctx)
    order = ctx.plan.order
    carrier_bytes = 0.25 * fit.BYTES_PER_ELEMENT[order] * elements
    carrier_seconds = fit.SECONDS_PER_ELEMENT[order] * elements
    n = max(int(dofs), 1)
    matrix = 12.0 * per_row * n
    memory = fit.BASE_BYTES + carrier_bytes + 2.0 * matrix + 16.0 * fit.FILL * n ** 1.25
    seconds = carrier_seconds + 1e-5 * n + fit.DIRECT_SECONDS * n ** 1.5
    return fit.Estimate(dofs=n, memory_bytes=int(memory), seconds=float(seconds))


# -- the model ----------------------------------------------------------------------------------------


@dataclass
class ShellModel:
    """The mid-surface mesh and its frames: nodes (N, 3), triangles (T, 3) facing +normal, thickness."""

    nodes: Any
    triangles: Any
    thickness: float
    normal: Any
    e1: Any
    e2: Any

    def frames(self):
        """Each triangle's local frame (T, 3, 3) (rows: x along its first edge, y, z = the plate normal),
        its area and its nodes' local coordinates (T, 3, 3)."""
        import numpy as np

        corners = self.nodes[self.triangles]
        x = corners[:, 1] - corners[:, 0]
        x /= np.linalg.norm(x, axis=1)[:, None]
        cross = np.cross(corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0])
        area = 0.5 * np.linalg.norm(cross, axis=1)
        z = cross / (2.0 * area)[:, None]
        y = np.cross(z, x)
        frame = np.stack([x, y, z], axis=1)
        local = np.einsum("tij,tkj->tki", frame, corners - corners[:, :1])
        return frame, area, local

    def element_matrices(self, E: float, nu: float, abd: dict | None = None):
        """Per triangle: the global 18 x 18 stiffness, and the membrane and bending strain operators (local).

        ``abd`` (a laminate) replaces the isotropic constitutive matrices: ``A``, ``B``, ``D`` (3 x 3) and the
        transverse shear ``H`` (2 x 2, shear correction included), all in the laminate's frame whose 0° direction
        is ``axis`` (a unit vector in the plate's plane; its 90° direction is the normal x axis)."""
        import numpy as np

        if abd is not None:
            return laminate_matrices(self, abd)

        t = self.thickness
        frame, area, local = self.frames()
        corners = self.nodes[self.triangles]
        x, y = local[..., 0], local[..., 1]
        twice = 2.0 * area
        dx = np.stack([y[:, 1] - y[:, 2], y[:, 2] - y[:, 0], y[:, 0] - y[:, 1]], 1) / twice[:, None]
        dy = np.stack([x[:, 2] - x[:, 1], x[:, 0] - x[:, 2], x[:, 1] - x[:, 0]], 1) / twice[:, None]
        count = len(self.triangles)
        membrane, bending = np.zeros((count, 3, 18)), np.zeros((count, 3, 18))
        for i in range(3):
            o = 6 * i
            # Local DOF per node: u, v, w, theta_x, theta_y, theta_z; beta_x = theta_y, beta_y = -theta_x.
            membrane[:, 0, o], membrane[:, 1, o + 1] = dx[:, i], dy[:, i]
            membrane[:, 2, o], membrane[:, 2, o + 1] = dy[:, i], dx[:, i]
            bending[:, 0, o + 4], bending[:, 1, o + 3] = dx[:, i], -dy[:, i]
            bending[:, 2, o + 4], bending[:, 2, o + 3] = dy[:, i], -dx[:, i]
        Q = plane_stress(E, nu)
        G = E / (2.0 * (1.0 + nu))
        h = np.max(np.linalg.norm(corners - np.roll(corners, 1, axis=1), axis=2), axis=1)
        shear = SHEAR_CORRECTION * G * t * t * t / (t * t + ALPHA * h * h)
        K = area[:, None, None] * (
            t * np.einsum("tki,kl,tlj->tij", membrane, Q, membrane)
            + t ** 3 / 12.0 * np.einsum("tki,kl,tlj->tij", bending, Q, bending)
        )
        # MITC3: the shear strain is the lowest-order edge (Nedelec) field with the tangential shear of
        # each edge, (w_j - w_i) + (beta_i + beta_j) . e_ij / 2, integrated at the edge midpoints.
        gradient = np.stack([dx, dy], axis=2)
        for q in range(3):
            weights = np.full(3, 0.5)
            weights[(q + 2) % 3] = 0.0
            strain = np.zeros((count, 2, 18))
            for i, j in ((0, 1), (1, 2), (2, 0)):
                whitney = weights[i] * gradient[:, j, :] - weights[j] * gradient[:, i, :]
                edge = local[:, j, :2] - local[:, i, :2]
                tied = np.zeros((count, 18))
                tied[:, 6 * j + 2] += 1.0
                tied[:, 6 * i + 2] -= 1.0
                for k in (i, j):
                    tied[:, 6 * k + 4] += 0.5 * edge[:, 0]
                    tied[:, 6 * k + 3] -= 0.5 * edge[:, 1]
                strain += whitney[:, :, None] * tied[:, None, :]
            K += (area / 3.0 * shear)[:, None, None] * np.einsum("tki,tkj->tij", strain, strain)
        drilling = DRILLING * E * t * area
        relative = np.eye(3) - 1.0 / 3.0
        for i in range(3):
            for j in range(3):
                K[:, 6 * i + 5, 6 * j + 5] += drilling * relative[i, j]
        T = rotation_blocks(frame, 6)
        return np.einsum("tki,tkl,tlj->tij", T, K, T), membrane, bending, frame, area


def _laminate_rotation(frame, normal, axis):
    """Each element's x axis against the laminate's 0° direction: (cos, sin) of the angle, (T,) each."""
    import numpy as np

    x0 = np.asarray(axis, dtype=float)
    y0 = np.cross(np.asarray(normal, dtype=float), x0)
    return frame[:, 0] @ x0, frame[:, 0] @ y0


def strain_rotation(c, s):
    """(T, 3, 3): ε in a frame turned by angle (c, s) from this one, Voigt with engineering shear: ε' = T ε."""
    import numpy as np

    c, s = np.asarray(c, dtype=float), np.asarray(s, dtype=float)
    out = np.zeros((*c.shape, 3, 3))
    out[..., 0, 0], out[..., 0, 1], out[..., 0, 2] = c * c, s * s, c * s
    out[..., 1, 0], out[..., 1, 1], out[..., 1, 2] = s * s, c * c, -c * s
    out[..., 2, 0], out[..., 2, 1], out[..., 2, 2] = -2.0 * c * s, 2.0 * c * s, c * c - s * s
    return out


def laminate_matrices(self, abd):
    """:meth:`ShellModel.element_matrices` for a laminate: each element's A, B, D and H turned into its own frame."""
    import numpy as np

    t = self.thickness
    frame, area, local = self.frames()
    corners = self.nodes[self.triangles]
    x, y = local[..., 0], local[..., 1]
    twice = 2.0 * area
    dx = np.stack([y[:, 1] - y[:, 2], y[:, 2] - y[:, 0], y[:, 0] - y[:, 1]], 1) / twice[:, None]
    dy = np.stack([x[:, 2] - x[:, 1], x[:, 0] - x[:, 2], x[:, 1] - x[:, 0]], 1) / twice[:, None]
    count = len(self.triangles)
    membrane, bending = np.zeros((count, 3, 18)), np.zeros((count, 3, 18))
    for i in range(3):
        o = 6 * i
        membrane[:, 0, o], membrane[:, 1, o + 1] = dx[:, i], dy[:, i]
        membrane[:, 2, o], membrane[:, 2, o + 1] = dy[:, i], dx[:, i]
        bending[:, 0, o + 4], bending[:, 1, o + 3] = dx[:, i], -dy[:, i]
        bending[:, 2, o + 4], bending[:, 2, o + 3] = dy[:, i], -dx[:, i]
    # The element's x axis is at angle phi from the laminate's 0°: laminate strain = T(-phi) element strain.
    c, s = _laminate_rotation(frame, self.normal, abd["axis"])
    T = strain_rotation(c, -s)
    A, B, D = (np.einsum("tki,kl,tlj->tij", T, np.asarray(abd[key], dtype=float), T) for key in ("A", "B", "D"))
    P = np.zeros((count, 2, 2))
    P[:, 0, 0], P[:, 0, 1], P[:, 1, 0], P[:, 1, 1] = c, -s, s, c
    H = np.einsum("tki,kl,tlj->tij", P, np.asarray(abd["H"], dtype=float), P)
    h = np.max(np.linalg.norm(corners - np.roll(corners, 1, axis=1), axis=2), axis=1)
    stabilised = (t * t / (t * t + ALPHA * h * h))[:, None, None] * H
    coupling = np.einsum("tki,tkl,tlj->tij", membrane, B, bending)
    K = area[:, None, None] * (
        np.einsum("tki,tkl,tlj->tij", membrane, A, membrane) + coupling + np.transpose(coupling, (0, 2, 1))
        + np.einsum("tki,tkl,tlj->tij", bending, D, bending)
    )
    gradient = np.stack([dx, dy], axis=2)
    for q in range(3):
        weights = np.full(3, 0.5)
        weights[(q + 2) % 3] = 0.0
        strain = np.zeros((count, 2, 18))
        for i, j in ((0, 1), (1, 2), (2, 0)):
            whitney = weights[i] * gradient[:, j, :] - weights[j] * gradient[:, i, :]
            edge = local[:, j, :2] - local[:, i, :2]
            tied = np.zeros((count, 18))
            tied[:, 6 * j + 2] += 1.0
            tied[:, 6 * i + 2] -= 1.0
            for k in (i, j):
                tied[:, 6 * k + 4] += 0.5 * edge[:, 0]
                tied[:, 6 * k + 3] -= 0.5 * edge[:, 1]
            strain += whitney[:, :, None] * tied[:, None, :]
        K += (area / 3.0)[:, None, None] * np.einsum("tki,tkl,tlj->tij", strain, stabilised, strain)
    # The drilling rotation only keeps the system regular: its stiffness from the laminate's mean membrane modulus.
    drilling = DRILLING * 0.5 * (abd["A"][0][0] + abd["A"][1][1]) * area
    relative = np.eye(3) - 1.0 / 3.0
    for i in range(3):
        for j in range(3):
            K[:, 6 * i + 5, 6 * j + 5] += drilling * relative[i, j]
    R = rotation_blocks(frame, 6)
    return np.einsum("tki,tkl,tlj->tij", R, K, R), membrane, bending, frame, area



def plane_stress(E: float, nu: float):
    import numpy as np

    return E / (1.0 - nu * nu) * np.array([[1.0, nu, 0.0], [nu, 1.0, 0.0], [0.0, 0.0, 0.5 * (1.0 - nu)]])


def rotation_blocks(frame, blocks: int):
    """(T, 3b, 3b): each element's frame on the diagonal, ``blocks`` times (local = T global)."""
    import numpy as np

    out = np.zeros((len(frame), 3 * blocks, 3 * blocks))
    for b in range(blocks):
        out[:, 3 * b:3 * b + 3, 3 * b:3 * b + 3] = frame
    return out


def assemble(element, connectivity, size: int):
    """The global sparse matrix of per-element ``element`` (E, k, k) on ``connectivity`` (E, k) DOF ids."""
    import numpy as np
    import scipy.sparse as sparse

    k = connectivity.shape[1]
    rows = np.repeat(connectivity, k, axis=1).ravel()
    cols = np.tile(connectivity, (1, k)).ravel()
    return sparse.csr_matrix((element.ravel(), (rows, cols)), shape=(size, size))


def solve_fixed(K, f, fixed):
    """u with ``fixed`` DOF at zero, by a sparse direct solve."""
    import numpy as np
    import scipy.sparse.linalg as linalg

    free = np.setdiff1d(np.arange(len(f)), fixed)
    u = np.zeros(len(f))
    if len(free):
        u[free] = linalg.spsolve(K[free][:, free].tocsc(), f[free])
    return u


def mesh_mid_surface(plate: Plate, h: float) -> ShellModel:
    """The top skin meshed by netgen at ``h``, moved down half the thickness, every triangle facing +normal."""
    import tempfile
    from pathlib import Path

    import numpy as np
    from OCP.BRep import BRep_Builder
    from OCP.BRepTools import BRepTools
    from OCP.TopoDS import TopoDS_Compound

    from cadgen._internal.step_scene_loader import kernel_messages_on_stderr

    builder = BRep_Builder()
    compound = TopoDS_Compound()
    builder.MakeCompound(compound)
    for face in plate.top_faces:
        builder.Add(compound, face)
    import netgen.meshing as ngmesh
    import netgen.occ as ngocc

    with tempfile.TemporaryDirectory(prefix="cadgen-shell-") as tmp:
        path = Path(tmp) / "skin.brep"
        BRepTools.Write_s(compound, str(path))
        with kernel_messages_on_stderr():
            ngmesh.SetMessageImportance(0)
            # Finer along every edge (clamps, holes, the outline): the peaks sit there, and a linear
            # triangle's constant curvature reads them low by about a third of its size's share.
            shape = ngocc.OCCGeometry(str(path)).shape
            for edge in shape.edges:
                edge.maxh = float(h) / EDGE_REFINE
            mesh = ngocc.OCCGeometry(shape).GenerateMesh(maxh=float(h), grading=0.3)
            nodes = np.array(mesh.Coordinates(), dtype=float, copy=True)
            triangles = mesh.Elements2D().NumPy()["nodes"][:, :3].astype(np.int64) - 1
            del mesh
    if nodes.shape[1] == 2:
        nodes = np.c_[nodes, np.zeros(len(nodes))]
    n = np.asarray(plate.normal, dtype=float)
    used = np.unique(triangles)
    renumber = np.full(len(nodes), -1)
    renumber[used] = np.arange(len(used))
    nodes, triangles = nodes[used], renumber[triangles]
    nodes = nodes - (nodes @ n - plate.mid_level)[:, None] * n   # onto the mid-plane exactly
    cross = np.cross(nodes[triangles[:, 1]] - nodes[triangles[:, 0]], nodes[triangles[:, 2]] - nodes[triangles[:, 0]])
    flip = cross @ n < 0
    triangles[flip] = triangles[flip][:, [0, 2, 1]]
    e1 = np.cross(n, [1.0, 0.0, 0.0] if abs(n[0]) < 0.9 else [0.0, 1.0, 0.0])
    e1 /= np.linalg.norm(e1)
    return ShellModel(nodes, triangles, plate.thickness, n, e1, np.cross(n, e1))


def boundary_edges(triangles):
    """The edges on one triangle only, (B, 2), with that triangle's third node (B,)."""
    import numpy as np

    edges = np.concatenate([triangles[:, [0, 1]], triangles[:, [1, 2]], triangles[:, [2, 0]]])
    third = np.concatenate([triangles[:, 2], triangles[:, 0], triangles[:, 1]])
    key = np.sort(edges, axis=1)
    _, inverse, counts = np.unique(key, axis=0, return_inverse=True, return_counts=True)
    once = counts[inverse.ravel()] == 1
    return edges[once], third[once]


def node_patch_fit(nodes2d, triangles, values):
    """Nodal values from per-element ``values`` (T, c) by a least-squares linear fit over each node's patch
    of element centroids (superconvergent patch recovery, Zienkiewicz-Zhu), the plain patch mean where the
    patch is too small to fit a plane."""
    import numpy as np

    centroids = nodes2d[triangles].mean(axis=1)
    count, comps = len(nodes2d), values.shape[1]
    node = triangles.ravel()
    element = np.repeat(np.arange(len(triangles)), 3)
    offset = centroids[element] - nodes2d[node]
    basis = np.c_[np.ones(len(node)), offset]
    normal = np.zeros((count, 3, 3))
    np.add.at(normal, node, basis[:, :, None] * basis[:, None, :])
    rhs = np.zeros((count, 3, comps))
    np.add.at(rhs, node, basis[:, :, None] * values[element][:, None, :])
    mean = rhs[:, 0, :] / np.maximum(normal[:, 0, 0], 1.0)[:, None]
    patch = normal[:, 0, 0]
    det = np.linalg.det(normal)
    scale = (np.einsum("nii->n", normal) / 3.0) ** 3
    good = (patch >= 3) & (np.abs(det) > 1e-6 * np.maximum(scale, 1e-300))
    out = mean.copy()
    if good.any():
        out[good] = np.linalg.solve(normal[good], rhs[good])[:, 0, :]
    return out


def von_mises(S):
    """von Mises of (..., 3, 3) stress tensors."""
    import numpy as np

    d = S[..., 0, 0], S[..., 1, 1], S[..., 2, 2]
    shear = S[..., 0, 1] ** 2 + S[..., 1, 2] ** 2 + S[..., 0, 2] ** 2
    return np.sqrt(np.maximum(0.5 * ((d[0] - d[1]) ** 2 + (d[1] - d[2]) ** 2 + (d[2] - d[0]) ** 2) + 3.0 * shear, 0.0))


def solve(analysis, ctx, inputs):
    """Static on the plan's shell: the mid-surface solved, its fields mapped onto the carrier (``ctx.volume``)."""
    import time

    import numpy as np

    plate = detect(ctx.geometry)
    if plate is None:
        raise RuntimeError("the shell idealisation lost its plate between the ladder and the solve")
    material = ctx.study.material
    E, nu, t = float(material.E), float(material.nu), plate.thickness
    h = element_size(plate, ctx.plan.requested_mm)
    mid = solve_mid_surface(ctx, inputs, plate, h, E=E, nu=nu, density=float(material.density or 0.0))
    model, u, timings, count, size = mid.model, mid.u, mid.timings, mid.count, mid.size
    membrane, bending, frame, triangles, nodes, n = mid.membrane, mid.bending, mid.frame, mid.model.triangles, mid.model.nodes, mid.model.normal
    reactions, applied, connectivity = mid.reactions, mid.applied, mid.connectivity

    # Fibre stresses: membrane plus or minus half the thickness times the bending curvature, per element.
    started = time.perf_counter()
    T = rotation_blocks(frame, 6)
    local = np.einsum("tij,tj->ti", T, u[connectivity])
    Q = plane_stress(E, nu)
    strain = np.einsum("tki,ti->tk", membrane, local)
    curvature = np.einsum("tki,ti->tk", bending, local)
    tensors = []
    for z in (0.5 * t, -0.5 * t):
        s = (strain + z * curvature) @ Q.T                                    # (T, 3) local sx, sy, sxy
        plane = np.zeros((len(triangles), 3, 3))
        plane[:, 0, 0], plane[:, 1, 1] = s[:, 0], s[:, 1]
        plane[:, 0, 1] = plane[:, 1, 0] = s[:, 2]
        tensors.append(np.einsum("tki,tkl,tlj->tij", frame, plane, frame))    # global
    element_peak = np.maximum(von_mises(tensors[0]), von_mises(tensors[1]))
    flat = np.c_[nodes @ model.e1, nodes @ model.e2]
    upper = node_patch_fit(flat, triangles, tensors[0].reshape(-1, 9)).reshape(-1, 3, 3)
    lower = node_patch_fit(flat, triangles, tensors[1].reshape(-1, 9)).reshape(-1, 3, 3)

    # Onto the carrier: each point's mid-surface spot, its height z in the plate, and the fields there.
    points = ctx.space.dof_locations if ctx.space is not None else ctx.volume.nodes
    z = np.clip(points @ n - plate.mid_level, -0.5 * t, 0.5 * t)
    where, weights = locate(np.c_[points @ model.e1, points @ model.e2], flat, triangles)
    corner = triangles[where]
    U = u.reshape(-1, 6)
    translation = np.einsum("pk,pkc->pc", weights, U[corner, :3])
    rotation = np.einsum("pk,pkc->pc", weights, U[corner, 3:])
    displacement = translation + np.cross(rotation, z[:, None] * n[None, :])
    top = np.einsum("pk,pkij->pij", weights, upper[corner])
    bottom = np.einsum("pk,pkij->pij", weights, lower[corner])
    share = (z / t + 0.5)[:, None, None]
    stress = von_mises(bottom + share * (top - bottom))
    timings["stress_s"] = time.perf_counter() - started

    detail = {"idealisation": "shell", "nodes": int(count), "elements": int(len(triangles)), "element_size_mm": round(h, 4),
              "thickness_mm": round(t, 6)}
    outcome = outcome_on_carrier(ctx, displacement, stress, float(element_peak.max()), reactions, applied, size,
                                 timings, "direct (shell)")
    return finish(analysis, ctx, inputs, outcome, detail)


@dataclass
class MidSurface:
    """A solved mid-surface: the model, its displacement (6 per node), the element operators and the balance."""

    model: Any
    u: Any
    membrane: Any
    bending: Any
    frame: Any
    area: Any
    connectivity: Any
    reactions: list
    applied: tuple
    size: int
    count: int
    timings: dict


def solve_mid_surface(ctx, inputs, plate: Plate, h: float, *, E: float, nu: float, density: float,
                      abd: dict | None = None) -> MidSurface:
    """The plate's mid-surface meshed at ``h``, loaded and held as the study says (a skin face is the mid-surface
    under it, a side face its edge along it) and solved: isotropic (E, nu) or a laminate (``abd``)."""
    import time

    import numpy as np

    started = time.perf_counter()
    t = plate.thickness
    model = mesh_mid_surface(plate, h)
    timings = {"shell_mesh_s": time.perf_counter() - started}
    n = model.normal
    nodes, triangles = model.nodes, model.triangles
    count = len(nodes)
    size = 6 * count

    started = time.perf_counter()
    Ke, membrane, bending, frame, area = model.element_matrices(E, nu, abd)
    connectivity = (6 * triangles[:, :, None] + np.arange(6)).reshape(len(triangles), 18)
    K = assemble(Ke, connectivity, size)
    timings["assemble_s"] = time.perf_counter() - started

    # Which face is above, below and along each part of the mid-surface (the carrier's faces).
    carrier = carrier_triangles(ctx)
    centroids = nodes[triangles].mean(axis=1)
    above = _classify(centroids + 0.5 * t * n, carrier, plate.top)
    below = _classify(centroids - 0.5 * t * n, carrier, plate.bottom)
    edges, third = boundary_edges(triangles)
    rim = np.unique(edges)
    tolerance = 0.25 * h + 1e-9

    def side_nodes(ordinal: int):
        rows = carrier.rows_of(ordinal)
        if not len(rows):
            return np.zeros(0, dtype=np.int64)
        distance = distance_to_triangles(nodes[rim], carrier.corners[rows])
        return rim[distance <= tolerance]

    def region(ordinal: int):
        """(triangles under a skin face, boundary edges along a side face) of one face."""
        if ordinal in plate.top:
            return np.flatnonzero(above == ordinal), np.zeros(0, dtype=np.int64), 0.5 * t
        if ordinal in plate.bottom:
            return np.flatnonzero(below == ordinal), np.zeros(0, dtype=np.int64), -0.5 * t
        on = np.zeros(count, dtype=bool)
        on[side_nodes(ordinal)] = True
        return np.zeros(0, dtype=np.int64), np.flatnonzero(on[edges].all(axis=1)), 0.0

    lengths = np.linalg.norm(nodes[edges[:, 1]] - nodes[edges[:, 0]], axis=1)
    outward = np.cross(nodes[edges[:, 1]] - nodes[edges[:, 0]], n)
    outward /= np.maximum(np.linalg.norm(outward, axis=1), 1e-300)[:, None]
    middle = 0.5 * (nodes[edges[:, 0]] + nodes[edges[:, 1]])
    inward = np.einsum("ij,ij->i", nodes[third] - middle, outward) > 0
    outward[inward] *= -1.0

    f = np.zeros(size)

    def add(at_nodes, force, lever):
        """Force rows (k, 3) shared equally by ``at_nodes`` (k, m), with the moment of ``lever`` (k,) n x force."""
        m = at_nodes.shape[1]
        moment = np.cross(lever[:, None] * n[None, :], force)
        for j in range(m):
            for c in range(3):
                np.add.at(f, 6 * at_nodes[:, j] + c, force[:, c] / m)
                np.add.at(f, 6 * at_nodes[:, j] + 3 + c, moment[:, c] / m)

    for load in inputs.surface_loads:
        ordinals = [ctx.ordinal_of[ref] for ref in load.faces]
        parts = [region(o) for o in ordinals]
        if load.type == "pressure":
            p = float(load.pressure)
            for ordinal, (tris, rows, z) in zip(ordinals, parts):
                if len(tris):
                    out = n if z > 0 else -n
                    add(triangles[tris], -p * area[tris, None] * out[None, :], np.full(len(tris), z))
                if len(rows):
                    add(edges[rows], -p * (lengths[rows] * t)[:, None] * outward[rows], np.zeros(len(rows)))
        else:
            vector = np.asarray(load.vector, dtype=float)
            weight = sum(area[tris].sum() + (lengths[rows] * t).sum() for tris, rows, _ in parts)
            if not weight > 0:
                raise ValueError(f"the force on {', '.join(load.faces)} reaches no part of the plate's mid-surface")
            for tris, rows, z in parts:
                if len(tris):
                    add(triangles[tris], (area[tris] / weight)[:, None] * vector[None, :], np.full(len(tris), z))
                if len(rows):
                    add(edges[rows], (lengths[rows] * t / weight)[:, None] * vector[None, :], np.zeros(len(rows)))
    rho = density
    for b in inputs.body_accelerations:
        add(triangles, rho * t * area[:, None] * np.asarray(b, dtype=float)[None, :], np.zeros(len(triangles)))
    applied = tuple(float(f[c::6].sum()) for c in range(3))

    fixture_nodes = []
    for fixture in inputs.fixtures:
        held = set()
        for ref in fixture.faces:
            tris, rows, _ = region(ctx.ordinal_of[ref])
            held.update(np.unique(triangles[tris]).tolist())
            if not len(tris):
                held.update(side_nodes(ctx.ordinal_of[ref]).tolist())
        if not held:
            raise ValueError(f"the fixture on {', '.join(fixture.faces)} holds no part of the plate's mid-surface")
        fixture_nodes.append(np.array(sorted(held), dtype=np.int64))
    fixed = np.unique(np.concatenate([6 * nodes_[:, None] + np.arange(6) for nodes_ in fixture_nodes]).ravel())

    started = time.perf_counter()
    u = solve_fixed(K, f, fixed)
    timings["solve_s"] = time.perf_counter() - started
    residual = K @ u - f
    reactions = [tuple(float(residual[6 * held + c].sum()) for c in range(3)) for held in fixture_nodes]

    return MidSurface(model, u, membrane, bending, frame, area, connectivity, reactions, applied, size, count, timings)


def _classify(points, carrier, ordinals):
    """The face (of ``ordinals``) each point lies on: the carrier triangle nearest it."""
    import numpy as np

    rows = np.flatnonzero(np.isin(carrier.ordinal, list(ordinals)))
    if len(ordinals) == 1 or not len(rows):
        return np.full(len(points), ordinals[0] if ordinals else 0, dtype=np.int64)
    index, _ = nearest_triangles(points, carrier.corners[rows])
    return carrier.ordinal[rows][index]


def locate(points2d, nodes2d, triangles):
    """For each point, the triangle it lies in (or the nearest) and its barycentric weights (clipped, summing to 1)."""
    import numpy as np
    from scipy.spatial import cKDTree

    corners = nodes2d[triangles]
    tree = cKDTree(corners.mean(axis=1))
    k = min(12, len(triangles))
    _, candidates = tree.query(points2d, k=k)
    candidates = np.asarray(candidates).reshape(len(points2d), k)
    a, b, c = (corners[candidates][:, :, i] for i in range(3))
    v0, v1, v2 = b - a, c - a, points2d[:, None, :] - a
    det = v0[..., 0] * v1[..., 1] - v0[..., 1] * v1[..., 0]
    l1 = (v2[..., 0] * v1[..., 1] - v2[..., 1] * v1[..., 0]) / det
    l2 = (v0[..., 0] * v2[..., 1] - v0[..., 1] * v2[..., 0]) / det
    bary = np.stack([1.0 - l1 - l2, l1, l2], axis=-1)
    best = np.argmax(bary.min(axis=-1), axis=1)
    rows = np.arange(len(points2d))
    weights = np.clip(bary[rows, best], 0.0, None)
    weights /= np.maximum(weights.sum(axis=1), 1e-300)[:, None]
    return candidates[rows, best], weights


# -- shared with beam.py -------------------------------------------------------------------------------


@dataclass
class Carrier:
    """The carrier mesh's surface triangles: corners (B, 3, 3), unit outward normals, areas, centroids, face ordinals."""

    corners: Any
    normals: Any
    areas: Any
    centroids: Any
    ordinal: Any

    def rows_of(self, ordinal: int):
        import numpy as np

        return np.flatnonzero(self.ordinal == ordinal)


def carrier_triangles(ctx) -> Carrier:
    """``ctx.volume``'s boundary triangles with outward normals (away from the tetrahedron each closes)."""
    import numpy as np

    volume = ctx.volume
    nodes = volume.nodes
    triangles = volume.boundary[:, :3]
    corners = nodes[triangles]
    cross = np.cross(corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0])
    areas = 0.5 * np.linalg.norm(cross, axis=1)
    normals = cross / np.maximum(2.0 * areas, 1e-300)[:, None]
    # The tetrahedron each triangle closes: its fourth corner is inside the part.
    tets = volume.tets[:, :4]
    faces = np.concatenate([tets[:, [0, 1, 2]], tets[:, [0, 1, 3]], tets[:, [0, 2, 3]], tets[:, [1, 2, 3]]])
    fourth = np.concatenate([tets[:, 3], tets[:, 2], tets[:, 1], tets[:, 0]])
    keys = np.sort(faces, axis=1)
    wanted = np.sort(triangles, axis=1)
    width = int(max(nodes.shape[0], 1))
    code = lambda k: (k[:, 0] * width + k[:, 1]) * width + k[:, 2]  # noqa: E731
    order = np.argsort(code(keys))
    position = np.searchsorted(code(keys)[order], code(wanted))
    position = np.clip(position, 0, len(order) - 1)
    hit = code(keys)[order][position] == code(wanted)
    inside = nodes[fourth[order][position]]
    flip = hit & (np.einsum("ij,ij->i", inside - corners[:, 0], normals) > 0)
    normals[flip] *= -1.0
    return Carrier(corners, normals, areas, corners.mean(axis=1), np.asarray(volume.boundary_ordinal))


def distance_to_triangles(points, corners):
    """Each point's distance to the nearest of ``corners`` (T, 3, 3), all pairs (chunked)."""
    import numpy as np

    out = np.full(len(points), np.inf)
    if not len(corners):
        return out
    chunk = max(1, 2_000_000 // max(len(corners), 1))
    for start in range(0, len(points), chunk):
        p = points[start:start + chunk][:, None, :]
        out[start:start + chunk] = _point_triangle(p, corners[None, :, 0], corners[None, :, 1], corners[None, :, 2]).min(axis=1)
    return out


def nearest_triangles(points, corners):
    """Each point's nearest triangle of ``corners`` (T, 3, 3) among the 16 with the nearest centroids, and the distance."""
    import numpy as np
    from scipy.spatial import cKDTree

    k = min(16, len(corners))
    _, candidates = cKDTree(corners.mean(axis=1)).query(points, k=k)
    candidates = np.asarray(candidates).reshape(len(points), k)
    c = corners[candidates]
    d = _point_triangle(points[:, None, :], c[:, :, 0], c[:, :, 1], c[:, :, 2])
    best = np.argmin(d, axis=1)
    rows = np.arange(len(points))
    return candidates[rows, best], d[rows, best]


def _point_triangle(p, a, b, c):
    """Distance from points to triangles (broadcast): to the plane inside, else to the nearest edge."""
    import numpy as np

    ab, ac = b - a, c - a
    normal = np.cross(ab, ac)
    norm = np.linalg.norm(normal, axis=-1)
    unit = normal / np.maximum(norm, 1e-300)[..., None]
    height = np.einsum("...i,...i->...", p - a, unit)
    q = p - height[..., None] * unit
    inside = np.ones(np.broadcast(height, norm).shape, dtype=bool)
    for x, y in ((a, b), (b, c), (c, a)):
        inside &= np.einsum("...i,...i->...", np.cross(y - x, q - x), unit) >= 0
    edge = np.minimum(np.minimum(_segment(p, a, b), _segment(p, b, c)), _segment(p, c, a))
    return np.where(inside & (norm > 0), np.abs(height), edge)


def _segment(p, a, b):
    import numpy as np

    d = b - a
    s = np.clip(np.einsum("...i,...i->...", p - a, d) / np.maximum(np.einsum("...i,...i->...", d, d), 1e-300), 0.0, 1.0)
    return np.linalg.norm(p - (a + s[..., None] * d), axis=-1)


def outcome_on_carrier(ctx, displacement, stress, element_peak: float, reactions, applied, dofs: int, timings, solver: str):
    """An idealised solve as :class:`~cadgen._internal.fea.solve.SolveOutcome` on the carrier's element space, so
    static's checks, findings, summary and GLB read it as they read a solid solve."""
    import numpy as np

    from cadgen._internal.fea.femspace import FemSpace
    from cadgen._internal.fea.solve import SolveOutcome

    space = ctx.space if ctx.space is not None else FemSpace.build(ctx.volume, ctx.plan.order)
    stress = np.maximum(np.asarray(stress, dtype=float), 0.0)
    element_dofs = space.element_dofs
    return SolveOutcome(
        dof_locations=space.dof_locations, displacement=np.asarray(displacement, dtype=float), von_mises=stress,
        von_mises_gauss_max=max(float(element_peak), float(stress.max())), vertices=space.vertices, tets=space.tets,
        boundary_quadratic=space.boundary_quadratic, reactions=list(reactions), applied=tuple(applied), dofs=int(dofs),
        element_dofs=element_dofs, element_von_mises_gauss=stress[element_dofs].max(axis=1), timings=dict(timings),
        warnings=[], solver=solver, von_mises_parts=None, u=None,
    )


def finish(analysis, ctx, inputs, outcome, detail: dict):
    """The outcome as static's result (its per-part numbers through static's own helpers)."""
    from cadgen._internal.fea.analyses.static import _solved

    solved = [_solved(ctx.volume, outcome, ctx.study, ctx.ordinal_of, ctx.part_name, inputs.fixtures)]
    result = analysis._result(outcome, solved, None)
    result.scalars["idealisation"] = detail
    return result


class Idealiser:
    """What :data:`cadgen._internal.fea.fit.IDEALISERS` holds: the rung (called), its estimate and its solve."""

    def __init__(self, rung, cost, run):
        self._rung, self.estimate, self.solve = rung, cost, run

    def __call__(self, analysis, ctx, inputs):
        return self._rung(analysis, ctx, inputs)


def _register() -> None:
    from cadgen._internal.fea import fit

    fit.IDEALISERS.setdefault("shell", Idealiser(idealise, estimate, solve))


_register()
