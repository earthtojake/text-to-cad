"""Slender prismatic parts as 3D Timoshenko frames: the fit ladder's ``idealise`` rung for a bar.

A part is a slender bar when it is unambiguously one: a straight prism, with
two planar end faces facing out along one axis, every other face running
along that axis (its normal everywhere across it), both ends of the same area
and the volume that area times the length, and the length more than
:data:`SLENDER` times the section's largest dimension. Anything else (a taper,
a step, a cross hole, a bend) is left solid.

The bar is then a line of two-node Timoshenko beam elements along its
centroidal axis, each with the exact shear-flexible stiffness (Przemieniecki:
bending with phi = 12 E I / (k G A L^2)), the section's area, principal second
moments and torsion constant measured from its end face (a circle's or tube's
polar moment is exact; another section uses Saint-Venant's A^4 / (4 pi^2 I_p)).
Loads come from the carrier's own surface triangles on each loaded face, each
as a force and a moment about the axis shared by the two nearest nodes, so a
pressure, a force or an off-axis push keeps its moment. Stresses are read at
every point of the carrier (the coarse mesh of the real part, for the GLB):
axial force and both bending moments give sigma = N/A + z M_y/I_y - y M_z/I_z,
torsion tau = T r / J; transverse shear stress is not added (under 2% of the
bending stress at this slenderness).

Static is the first adopter. Modal and buckling would add, per element in the
same frame: a consistent mass (rho A on the translations, rho I_p on the twist,
rho I on the bending rotations for rotary inertia) and the geometric stiffness
of this solve's axial force (N / (30 L) times the standard 4 x 4 bending block
in each plane, with its shear-flexible correction). :func:`element_stiffness`
is where they would join.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

from cadgen._internal.fea import shell

if TYPE_CHECKING:
    from cadgen._internal.fea.fit import Estimate, Geometry, Step

__all__ = ["SLENDER", "Bar", "detect", "element_stiffness", "estimate", "idealise", "solve"]

#: A bar is slender when its length is over this many times its section's largest dimension (spec 9, rung 4).
SLENDER = 20.0
#: Elements along the bar: at least this many, at most MOST, else the study's size.
FEWEST, MOST = 40, 400
#: The carrier mesh (the real part, for the GLB only): at least half the section across an element.
CARRIER_SECTION = 0.5


@dataclass
class Bar:
    """A detected slender prism: its axis from the first end's section centroid, length and section."""

    origin: "tuple[float, float, float]"
    axis: "tuple[float, float, float]"
    length: float
    depth: float                     # the section's largest dimension
    area: float
    frame: "tuple[tuple[float, float, float], ...]"   # rows: axis, principal y, principal z
    Iz: float                        # integral of y^2 (bending in the axis-y plane)
    Iy: float                        # integral of z^2 (bending in the axis-z plane)
    J: float                         # torsion constant
    circular: bool
    ends: tuple[int, ...] = ()
    sides: tuple[int, ...] = ()
    torsion_note: str = ""

    @property
    def slenderness(self) -> float:
        return self.depth / self.length


def detect(geometry: "Geometry") -> Bar | None:
    """The part as a slender bar, or ``None`` when it is not unambiguously one (see the module's rules)."""
    if geometry is None or geometry.shape is None:
        return None
    return shell.cached(geometry.shape, "beam", lambda shape: _detect(shape, geometry.volume_mm3))


def _detect(shape, volume: float) -> Bar | None:
    import numpy as np

    records = shell.face_records(shape)
    halves = shell.obb_half_sizes(shape)
    long_axis = halves[2][1]
    ends = [r for r in records if r.kind == "plane" and r.normals and all(abs(abs(shell.dot(m, long_axis)) - 1.0) < 1e-6 for m in r.normals)]
    if len(ends) < 2 or not volume > 0:
        return None
    a = np.asarray(ends[0].normals[0], dtype=float)
    levels = {r.ordinal: float(a @ np.asarray(r.centroid)) for r in ends}
    high, low = max(levels.values()), min(levels.values())
    length = high - low
    tol = 1e-6 * max(1.0, abs(high), abs(low)) + 1e-9
    first = [r for r in ends if abs(levels[r.ordinal] - low) <= tol]
    last = [r for r in ends if abs(levels[r.ordinal] - high) <= tol]
    if len(first) + len(last) != len(ends) or not length > 0:
        return None   # a planar face across the axis between the ends: a step
    if any(shell.dot(m, a) > -0.999999 for r in first for m in r.normals) or \
       any(shell.dot(m, a) < 0.999999 for r in last for m in r.normals):
        return None
    sides = [r for r in records if r.ordinal not in levels]
    if not sides or any(abs(shell.dot(m, a)) > shell.ACROSS_TOL for r in sides for m in r.normals):
        return None
    area_first, area_last = sum(r.area for r in first), sum(r.area for r in last)
    if abs(area_first - area_last) > shell.AGREE * area_first or abs(volume - area_first * length) > shell.AGREE * volume:
        return None
    section = _section(first, a)
    if section is None:
        return None
    centroid, area, frame, Iz, Iy, depth = section
    if not depth > 0 or length / depth <= SLENDER:
        return None
    # A round bar or tube: every side face a cylinder about the centroidal axis. Its polar moment is the twist constant.
    circular = all(
        r.kind == "cylinder" and r.axis is not None and abs(abs(shell.dot(r.axis, a)) - 1.0) < 1e-6
        and np.linalg.norm(np.cross(np.asarray(r.axis_point) - centroid, a)) < 1e-6 * max(depth, 1.0)
        for r in sides
    )
    polar = Iy + Iz
    if circular:
        J, note = polar, ""
    else:
        J, note = area ** 4 / (4.0 * math.pi ** 2 * polar), "the twist stiffness is Saint-Venant's estimate for this section"
    origin = tuple(float(c) for c in centroid - (centroid @ a - low) * a)
    return Bar(origin, tuple(float(c) for c in a), float(length), float(depth), float(area),
               tuple(tuple(float(c) for c in row) for row in frame), float(Iz), float(Iy), float(J), circular,
               tuple(levels), tuple(r.ordinal for r in sides), note)


def _section(faces, a):
    """The end section's centroid, area, principal frame (axis, y, z), I_z = ∫y², I_y = ∫z² and largest dimension."""
    import numpy as np
    from OCP.BRep import BRep_Builder
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    from OCP.TopoDS import TopoDS_Compound

    builder = BRep_Builder()
    compound = TopoDS_Compound()
    builder.MakeCompound(compound)
    for record in faces:
        builder.Add(compound, record.face)
    props = GProp_GProps()
    BRepGProp.SurfaceProperties_s(compound, props)
    area = float(props.Mass())
    if not area > 0:
        return None
    centre = props.CentreOfMass()
    matrix = props.MatrixOfInertia()
    inertia = np.array([[matrix.Value(i, j) for j in (1, 2, 3)] for i in (1, 2, 3)])
    second = 0.5 * np.trace(inertia) * np.eye(3) - inertia     # ∫ r rᵀ dA about the centroid
    helper = np.array([1.0, 0.0, 0.0]) if abs(a[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
    u = np.cross(a, helper)
    u /= np.linalg.norm(u)
    v = np.cross(a, u)
    plane = np.array([[u @ second @ u, u @ second @ v], [v @ second @ u, v @ second @ v]])
    values, vectors = np.linalg.eigh(plane)
    y = vectors[0, 1] * u + vectors[1, 1] * v      # the stiffer direction first
    z = np.cross(a, y)
    Iz, Iy = float(values[1]), float(values[0])
    halves = shell.obb_half_sizes(compound)
    depth = 2.0 * halves[2][0]
    return np.array([centre.X(), centre.Y(), centre.Z()]), area, np.array([a, y, z]), Iz, Iy, depth


# -- the rung -----------------------------------------------------------------------------------------


def elements_along(bar: Bar, requested: float | None) -> int:
    count = math.ceil(bar.length / float(requested)) if requested else FEWEST
    return int(min(max(count, FEWEST), MOST))


def idealise(analysis, ctx, inputs) -> "Step | None":
    """The ``idealise`` rung for a slender bar: the plan solves its centreline as a Timoshenko frame."""
    from cadgen._internal.fea.fit import Step

    if not shell.usable(analysis, ctx):
        return None
    bar = detect(ctx.geometry)
    if bar is None:
        return None
    plan = ctx.plan
    count = elements_along(bar, plan.requested_mm)
    carrier = max(float(plan.requested_mm or 0.0), CARRIER_SECTION * bar.depth)
    plan.idealisation = "beam"
    shell.undo_solid_rungs(plan)
    plan.size_mm = carrier
    words = (f"Solved the slender {bar.length:.3g} mm bar as a beam along its centreline to fit "
             f"(a {bar.depth:.3g} mm section, {count} elements); stresses are read across its section")
    accuracy = shell.model_error_words("Beam theory", "section-to-length ratio", bar.slenderness, "section depth")
    if bar.torsion_note:
        accuracy += f"; {bar.torsion_note}"
    return Step("idealise", words, accuracy, shell.model_error_pct(bar.slenderness), detail={
        "idealisation": "beam", "length_mm": round(bar.length, 4), "section_mm": round(bar.depth, 4),
        "slenderness": round(bar.slenderness, 6), "elements": count, "area_mm2": round(bar.area, 6),
        "Iy_mm4": round(bar.Iy, 6), "Iz_mm4": round(bar.Iz, 6), "J_mm4": round(bar.J, 6), "surface_mesh_mm": round(carrier, 4),
    })


def estimate(ctx) -> "Estimate":
    """The frame's cost: the carrier mesh and its element space, and a banded solve of six DOF per node."""
    bar = detect(ctx.geometry)
    count = elements_along(bar, ctx.plan.requested_mm) if bar is not None else FEWEST
    return shell.idealised_cost(ctx, 6 * (count + 1), 18.0)


# -- the model ----------------------------------------------------------------------------------------


def shear_factor(circular: bool, nu: float) -> float:
    """Timoshenko's shear correction: a solid circle's 6(1+nu)/(7+6nu), else a rectangle's 10(1+nu)/(12+11nu)."""
    return 6.0 * (1.0 + nu) / (7.0 + 6.0 * nu) if circular else 10.0 * (1.0 + nu) / (12.0 + 11.0 * nu)


def element_stiffness(L: float, E: float, G: float, A: float, Iy: float, Iz: float, J: float, k: float):
    """The 12 x 12 local stiffness of a two-node Timoshenko beam (u, v, w, rx, ry, rz at each end)."""
    import numpy as np

    K = np.zeros((12, 12))
    axial, twist = E * A / L, G * J / L
    for i, j, value in ((0, 0, axial), (6, 6, axial), (0, 6, -axial), (3, 3, twist), (9, 9, twist), (3, 9, -twist)):
        K[i, j] = K[j, i] = value

    def bend(I, sign):
        phi = 12.0 * E * I / (k * G * A * L * L)
        c = E * I / ((1.0 + phi) * L ** 3)
        s = sign * 6.0 * L
        return c * np.array([
            [12.0, s, -12.0, s],
            [s, (4.0 + phi) * L * L, -s, (2.0 - phi) * L * L],
            [-12.0, -s, 12.0, -s],
            [s, (2.0 - phi) * L * L, -s, (4.0 + phi) * L * L],
        ])

    for dofs, block in (((1, 5, 7, 11), bend(Iz, 1.0)), ((2, 4, 8, 10), bend(Iy, -1.0))):
        index = np.array(dofs)
        K[np.ix_(index, index)] = block
    return K


def solve(analysis, ctx, inputs):
    """Static on the plan's frame: the centreline solved, its fields mapped onto the carrier (``ctx.volume``)."""
    import time

    import numpy as np

    started = time.perf_counter()
    bar = detect(ctx.geometry)
    if bar is None:
        raise RuntimeError("the beam idealisation lost its bar between the ladder and the solve")
    material = ctx.study.material
    E, nu = float(material.E), float(material.nu)
    G = E / (2.0 * (1.0 + nu))
    k = shear_factor(bar.circular, nu)
    count = elements_along(bar, ctx.plan.requested_mm)
    L = bar.length / count
    origin, a = np.asarray(bar.origin), np.asarray(bar.axis)
    frame = np.asarray(bar.frame)
    nodes = count + 1
    size = 6 * nodes
    local = element_stiffness(L, E, G, bar.area, bar.Iy, bar.Iz, bar.J, k)
    T = np.zeros((12, 12))
    for b in range(4):
        T[3 * b:3 * b + 3, 3 * b:3 * b + 3] = frame
    Ke = T.T @ local @ T
    connectivity = (6 * np.arange(count)[:, None] + np.arange(12)[None, :])
    K = shell.assemble(np.broadcast_to(Ke, (count, 12, 12)).copy(), connectivity, size)

    carrier = shell.carrier_triangles(ctx)
    f = np.zeros(size)

    def along(points):
        s = np.clip((points - origin) @ a, 0.0, bar.length)
        element = np.minimum((s / L).astype(np.int64), count - 1)
        return s, element, s / L - element

    def spread(points, forces):
        """Forces at ``points`` onto the two nearest nodes, each with the moment about the axis it carries."""
        s, element, xi = along(points)
        arm = points - (origin + s[:, None] * a)
        moments = np.cross(arm, forces)
        for node, share in ((element, 1.0 - xi), (element + 1, xi)):
            for c in range(3):
                np.add.at(f, 6 * node + c, share * forces[:, c])
                np.add.at(f, 6 * node + 3 + c, share * moments[:, c])

    for load in inputs.surface_loads:
        rows = np.concatenate([carrier.rows_of(ctx.ordinal_of[ref]) for ref in load.faces])
        if not len(rows):
            raise ValueError(f"the load on {', '.join(load.faces)} reaches no surface of the bar")
        if load.type == "pressure":
            forces = -float(load.pressure) * carrier.areas[rows, None] * carrier.normals[rows]
        else:
            share = carrier.areas[rows] / carrier.areas[rows].sum()
            forces = share[:, None] * np.asarray(load.vector, dtype=float)[None, :]
        spread(carrier.centroids[rows], forces)
    rho = float(material.density or 0.0)
    for b in inputs.body_accelerations:
        weight = rho * bar.area * L * np.asarray(b, dtype=float)
        for c in range(3):
            f[c::6][:-1] += 0.5 * weight[c]
            f[c::6][1:] += 0.5 * weight[c]
    applied = tuple(float(f[c::6].sum()) for c in range(3))

    stations = np.arange(nodes) * L
    fixture_nodes = []
    for fixture in inputs.fixtures:
        rows = np.concatenate([carrier.rows_of(ctx.ordinal_of[ref]) for ref in fixture.faces])
        if not len(rows):
            raise ValueError(f"the fixture on {', '.join(fixture.faces)} holds no surface of the bar")
        s = np.clip((carrier.corners[rows].reshape(-1, 3) - origin) @ a, 0.0, bar.length)
        tol = 1e-6 * bar.length
        held = np.flatnonzero((stations >= s.min() - tol) & (stations <= s.max() + tol))
        if not len(held):
            held = np.array([int(np.argmin(np.abs(stations - 0.5 * (s.min() + s.max()))))])
        fixture_nodes.append(held)
    fixed = np.unique(np.concatenate([6 * held[:, None] + np.arange(6) for held in fixture_nodes]).ravel())
    timings = {"assemble_s": time.perf_counter() - started}

    started = time.perf_counter()
    u = shell.solve_fixed(K, f, fixed)
    timings["solve_s"] = time.perf_counter() - started
    residual = K @ u - f
    reactions = [tuple(float(residual[6 * held + c].sum()) for c in range(3)) for held in fixture_nodes]

    # Section forces: each element's end forces in its own frame (start: minus the first end's, end: the second's).
    started = time.perf_counter()
    end_forces = np.einsum("ij,ej->ei", local, np.einsum("ij,ej->ei", T, u[connectivity]))
    start, finish_ = -end_forces[:, :6], end_forces[:, 6:]
    points = ctx.space.dof_locations if ctx.space is not None else ctx.volume.nodes
    s, element, xi = along(points)
    section = (1.0 - xi)[:, None] * start[element] + xi[:, None] * finish_[element]
    N, T_, My, Mz = section[:, 0], section[:, 3], section[:, 4], section[:, 5]
    arm = points - (origin + s[:, None] * a)
    y, z = arm @ frame[1], arm @ frame[2]
    sigma = N / bar.area + z * My / bar.Iy - y * Mz / bar.Iz
    tau = T_ * np.sqrt(y * y + z * z) / bar.J
    stress = np.sqrt(sigma * sigma + 3.0 * tau * tau)
    U = u.reshape(-1, 6)
    weights = np.c_[1.0 - xi, xi]
    translation = weights[:, :1] * U[element, :3] + weights[:, 1:] * U[element + 1, :3]
    rotation = weights[:, :1] * U[element, 3:] + weights[:, 1:] * U[element + 1, 3:]
    displacement = translation + np.cross(rotation, arm)
    timings["stress_s"] = time.perf_counter() - started

    detail = {"idealisation": "beam", "nodes": int(nodes), "elements": int(count), "element_length_mm": round(L, 4),
              "shear_factor": round(k, 4)}
    outcome = shell.outcome_on_carrier(ctx, displacement, stress, float(stress.max()), reactions, applied, size,
                                       timings, "direct (beam)")
    return shell.finish(analysis, ctx, inputs, outcome, detail)


def _register() -> None:
    from cadgen._internal.fea import fit

    fit.IDEALISERS.setdefault("beam", shell.Idealiser(idealise, estimate, solve))


_register()
