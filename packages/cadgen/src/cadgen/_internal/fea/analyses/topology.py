"""Lighten it (lite): density-based topology optimisation, where the material should go and where it can go.

The study takes static's ``fixtures`` and ``loads`` (or several ``load_cases``, each its own ``loads``,
their compliances summed) and these keys:

- ``objective``: ``"stiffest"`` (the default): the stiffest part from ``volume_fraction`` of its material
  (minimum compliance); ``"lightest"``: the least material whose design still passes the study's stress
  check (and displacement checks, where it names them), found by a short search over the volume fraction,
  each step a stiffest design checked by a static solve.
- ``volume_fraction``: the share of the part's volume to keep (0.3 by default; ``lightest`` starts there,
  0.5 by default).
- ``keep``: faces whose nearby material stays solid, beyond the fixtures, the loaded faces and the bolt
  holes (whole cylindrical holes), which always do.
- ``min_member_mm``: the thinnest bar or wall the design may make, the density filter's size (three
  design elements by default; never under two and a half).
- ``penalty``: SIMP's exponent (3 by default), reached by continuation from 1.
- ``symmetry``: planes the design must be symmetric about: ``"x"`` (through the part's middle) or
  ``{"axis": "x", "at_mm": 20}``.
- ``extrusion``: a direction the design must be prismatic along (a part cut from plate or extruded):
  ``"z"`` or ``{"direction": [0, 0, 1]}``.
- ``iterations``: the most optimisation iterations (150 by default).

The design mesh is linear tetrahedra, fixed for the whole run (:mod:`..topology_ops` holds the numerics:
SIMP, a Helmholtz density filter, Heaviside projection with continuation, Optimality Criteria). What it
writes: the density as the field "material kept" with a series of design frames over the iterations (the
last, the final design, opens), the compliance and volume curves, the stress and displacement of a
verification static solve of the thresholded design (rho > 0.5, the pieces the fixtures hold), and the
design's surface at rho = 0.5 as a smoothed STL beside the GLB. Checks: ``mass_saved``, plus ``stress`` and
``displacement`` on the verified design. Stdlib only at import.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, ClassVar

from cadgen._internal.fea.analyses import kinds
from cadgen._internal.fea.analyses.base import AnalysisResult, FieldSpec, Series, SeriesFrame, SolveContext
from cadgen._internal.fea.analyses.static import StaticAnalysis, StaticInputs
from cadgen._internal.fea.study import Load, parse_fixtures, parse_loads

if TYPE_CHECKING:
    import numpy as np

__all__ = ["LIMITS", "OBJECTIVES", "TopologyAnalysis", "TopologyInputs"]

OBJECTIVES = ("stiffest", "lightest")
DEFAULT_FRACTION = {"stiffest": 0.3, "lightest": 0.5}
DEFAULT_ITERATIONS = 150
MAX_ITERATIONS = 2000
#: The default thinnest member, in design elements; and the least the filter allows.
MEMBER_ELEMENTS, LEAST_MEMBER_ELEMENTS = 3.0, 2.5
#: lightest: the stiffest designs it solves to find the least material that passes (the first included).
LIGHTEST_ROUNDS = 5
#: The design mesh never gets coarser than this many elements across the part's diagonal.
MIN_ELEMENTS_ACROSS = 12.0
_AXES = "xyz"

#: What this lite solver leaves out, written into its output, its verdict's Details and the skill.
LIMITS = (
    "Linear elastic, small displacement, one material: the design is the stiffest for these loads, not checked for "
    "buckling, fatigue or vibration",
    "The design mesh is fixed linear tetrahedra: members thinner than about three elements cannot form, and the "
    "surface is a smoothed staircase to rebuild in CAD",
    "The verification solve runs on the kept design elements (linear tets): its stress is a guide; re-run a static "
    "study on the rebuilt part",
    "Loads stay where they are: no self-weight, pressure that follows a moving surface, or load that depends on the design",
)


def _figure(value: float) -> str:
    return f"{value:.3g}"


@dataclass(frozen=True)
class TopologyInputs(StaticInputs):
    objective: str = "stiffest"
    volume_fraction: float = 0.3
    keep: tuple[str, ...] = ()
    min_member_mm: float | None = None
    penalty: float = 3.0
    #: Each plane as (axis "x"/"y"/"z", offset in mm or None for the part's middle).
    symmetry: tuple[tuple[str, float | None], ...] = ()
    extrusion: tuple[float, float, float] | None = None
    #: Each load case's name and loads; one unnamed case for a study with plain ``loads``.
    cases: tuple[tuple[str, tuple[Load, ...]], ...] = ()
    iterations: int = DEFAULT_ITERATIONS
    #: What the solve found that the echo says (the faces kept solid, bolt holes included): filled by ``solve``.
    found: dict = field(default_factory=dict, compare=False, hash=False)


# -- parse -----------------------------------------------------------------------------------------------


def _fraction(document: dict, objective: str) -> float:
    if "volume_fraction" not in document:
        return DEFAULT_FRACTION[objective]
    value = kinds.number(document["volume_fraction"], where="volume_fraction", positive=True)
    if not 0.01 <= value < 1.0:
        raise ValueError(f"volume_fraction: the share of the part's material to keep, between 0.01 and 1 (0.3 keeps 30 %), "
                         f"got {value:g}")
    return value


def _symmetry(raw: Any) -> tuple[tuple[str, float | None], ...]:
    if raw is None:
        return ()
    entries = raw if isinstance(raw, list) else [raw]
    planes = []
    for index, entry in enumerate(entries):
        where = f"symmetry[{index}]"
        if isinstance(entry, str) and entry.lower() in _AXES:
            planes.append((entry.lower(), None))
            continue
        if isinstance(entry, dict) and set(entry) <= {"axis", "at_mm"} and str(entry.get("axis", "")).lower() in _AXES \
                and entry.get("axis"):
            at = kinds.number(entry["at_mm"], where=f"{where}.at_mm") if "at_mm" in entry else None
            planes.append((str(entry["axis"]).lower(), at))
            continue
        raise ValueError(f'{where}: a plane the design is symmetric about: "x", "y" or "z" (through the part\'s middle), '
                         'or {"axis": "x", "at_mm": 20}')
    if len({axis for axis, _ in planes}) != len(planes):
        raise ValueError("symmetry: name each axis once")
    return tuple(planes)


def _extrusion(raw: Any) -> tuple[float, float, float] | None:
    if raw is None:
        return None
    words = 'the direction the design is extruded along: "x", "y", "z" or {"direction": [0, 0, 1]}'
    if isinstance(raw, str) and raw.lower() in _AXES:
        vector = [0.0, 0.0, 0.0]
        vector[_AXES.index(raw.lower())] = 1.0
        return tuple(vector)  # type: ignore[return-value]
    if isinstance(raw, dict) and set(raw) == {"direction"} and isinstance(raw["direction"], list) and len(raw["direction"]) == 3:
        vector = [kinds.number(v, where="extrusion.direction") for v in raw["direction"]]
        size = math.sqrt(sum(v * v for v in vector))
        if size == 0:
            raise ValueError("extrusion.direction: the direction is zero")
        return tuple(v / size for v in vector)  # type: ignore[return-value]
    raise ValueError(f"extrusion: {words}")


def _cases(document: dict) -> tuple[tuple[str, tuple[Load, ...]], ...]:
    if ("loads" in document) == ("load_cases" in document):
        raise ValueError("study: give 'loads' (one load case) or 'load_cases' (several, each with its own loads), exactly one")
    if "loads" in document:
        return (("", parse_loads(document, body=False)),)
    raw = document["load_cases"]
    if not isinstance(raw, list) or not raw:
        raise ValueError('load_cases: a list of load cases, like [{"name": "lift", "loads": [...]}, {"name": "brake", "loads": [...]}]')
    cases = []
    for index, entry in enumerate(raw):
        where = f"load_cases[{index}]"
        if not isinstance(entry, dict) or "loads" not in entry or set(entry) - {"name", "loads"}:
            raise ValueError(f"{where}: a load case takes 'loads' and an optional 'name'")
        try:
            loads = parse_loads({"loads": entry["loads"]}, body=False)
        except ValueError as exc:
            raise ValueError(f"{where}.{exc}") from exc
        name = entry.get("name", f"case {index + 1}")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"{where}.name: a short name for the load case")
        cases.append((name.strip(), loads))
    return tuple(cases)


def _iterations(document: dict) -> int:
    raw = document.get("iterations", DEFAULT_ITERATIONS)
    if isinstance(raw, bool) or not isinstance(raw, int) or not 10 <= raw <= MAX_ITERATIONS:
        raise ValueError(f"iterations: the most optimisation iterations, a whole number from 10 to {MAX_ITERATIONS}, "
                         f"got {kinds.json_text(raw)}")
    return raw


# -- holes kept solid ------------------------------------------------------------------------------------


def hole_faces(geometry) -> list[int]:
    """The ordinals of whole cylindrical holes (bolt holes): cylinders the material surrounds (the face reversed
    on its outward-pointing surface), going most of the way round, smaller than a quarter of the part."""
    if geometry is None or geometry.shape is None:
        return []
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.BRepTools import BRepTools
    from OCP.GeomAbs import GeomAbs_Cylinder
    from OCP.TopAbs import TopAbs_REVERSED
    from OCP.TopoDS import TopoDS

    from cadgen._internal.entity_ordinals import entity_map

    faces = entity_map(geometry.shape, "face")
    found = []
    for ordinal in range(1, faces.Extent() + 1):
        face = TopoDS.Face_s(faces.FindKey(ordinal))
        adaptor = BRepAdaptor_Surface(face)
        if adaptor.GetType() != GeomAbs_Cylinder:
            continue
        radius = adaptor.Cylinder().Radius()
        if radius > 0.25 * geometry.bbox_diagonal_mm:
            continue
        u0, u1, _, _ = BRepTools.UVBounds_s(face)
        if u1 - u0 < 0.99 * math.pi or face.Orientation() != TopAbs_REVERSED:
            continue
        found.append(ordinal)
    return found


# -- the verification solve on the kept elements ---------------------------------------------------------


def kept_volume(volume, kept: "np.ndarray"):
    """The design mesh's elements ``kept`` as a mesh of their own: its nodes, tets and boundary, each boundary
    triangle on the face it lay on (0 for one the design cut). Returns (mesh, node map old -> new or -1)."""
    import dataclasses

    import numpy as np

    tets = volume.tets[kept][:, :4]
    used = np.unique(tets)
    renumber = np.full(len(volume.nodes), -1, dtype=np.int64)
    renumber[used] = np.arange(len(used))
    local = renumber[tets]
    faces = np.concatenate([local[:, [1, 2, 3]], local[:, [0, 3, 2]], local[:, [0, 1, 3]], local[:, [0, 2, 1]]])
    key = np.sort(faces, axis=1)
    _, first, counts = np.unique(key, axis=0, return_index=True, return_counts=True)
    boundary = faces[first[counts == 1]]
    n = len(volume.nodes)
    original = np.sort(volume.boundary[:, :3], axis=1).astype(np.int64)
    original_key = (original[:, 0] * n + original[:, 1]) * n + original[:, 2]
    order = np.argsort(original_key)
    back = np.sort(used[boundary], axis=1).astype(np.int64)
    wanted = (back[:, 0] * n + back[:, 1]) * n + back[:, 2]
    where = np.clip(np.searchsorted(original_key[order], wanted), 0, len(order) - 1)
    hit = original_key[order][where] == wanted
    ordinal = np.where(hit, volume.boundary_ordinal[order][where], 0)
    sub = dataclasses.replace(volume, nodes=volume.nodes[used], tets=local, boundary=boundary, boundary_ordinal=ordinal,
                              domain=None)
    return sub, renumber


def connected_to(tets: "np.ndarray", kept: "np.ndarray", seeds: "np.ndarray", nodes: int) -> "np.ndarray":
    """The ``kept`` elements in a piece (sharing nodes) that touches a node of ``seeds``."""
    import numpy as np
    import scipy.sparse as sparse
    from scipy.sparse.csgraph import connected_components

    rows = np.flatnonzero(kept)
    corners = tets[rows][:, :4]
    element = np.repeat(np.arange(len(rows)), 4)
    graph = sparse.coo_matrix((np.ones(element.size), (element, len(rows) + corners.ravel())),
                              shape=(len(rows) + nodes, len(rows) + nodes))
    _, label = connected_components(graph, directed=False)
    held = set(np.unique(label[len(rows) + np.asarray(seeds, dtype=np.int64)]).tolist()) if len(seeds) else set()
    out = np.zeros(len(tets), dtype=bool)
    out[rows[np.isin(label[:len(rows)], list(held))]] = True
    return out


# -- the analysis ----------------------------------------------------------------------------------------


class TopologyAnalysis:
    name: ClassVar[str] = "topology"
    tier: ClassVar[int] = 3
    word: ClassVar[str] = "Lighten it"
    estimate_only: ClassVar[bool] = False
    limits: ClassVar[tuple[str, ...]] = LIMITS
    study_keys: ClassVar[frozenset[str]] = frozenset({
        "fixtures", "loads", "load_cases", "objective", "volume_fraction", "keep", "min_member_mm", "penalty", "symmetry",
        "extrusion", "iterations",
    })
    material_needs: ClassVar[frozenset[str]] = frozenset()
    mesh_orders: ClassVar[tuple[int, ...]] = (1,)
    connection_types: ClassVar[tuple[str, ...]] = ("bonded", "free")
    fields: ClassVar[tuple[FieldSpec, ...]] = (
        FieldSpec("material_kept", "_MATERIAL_KEPT", "material kept", "", per_frame=True),
        FieldSpec("von_mises", "_VON_MISES", "von Mises stress", "MPa"),
        FieldSpec("displacement", "_DISPLACEMENT", "displacement", "mm", 3, 1000.0),
    )
    checks: ClassVar[tuple] = (kinds.MASS_SAVED, kinds.STRESS, kinds.DISPLACEMENT)
    default_checks: ClassVar[tuple[dict, ...]] = ({"kind": "mass_saved", "min_percent": 25.0}, {"kind": "stress"})
    drives: ClassVar[tuple[str, ...]] = ("field", "deformation", "threshold", "frame")
    default_controls: ClassVar[dict[str, dict]] = {
        "frame": {"drives": "frame", "type": "number", "min": 0.0, "max": None},
        "field": {"drives": "field", "type": "enum", "options": ["material_kept", "von_mises", "displacement"]},
        "threshold": {"drives": "threshold", "type": "number", "field": "material_kept", "min": 0.0, "max": 1.0, "default": 0.5},
    }
    upstream: ClassVar[tuple[str, ...]] = ()
    ladder: ClassVar[tuple[str, ...]] = ("iterative", "symmetry", "coarse_design")
    noun: ClassVar[str] = "this load"
    governing_word: ClassVar[str] = "compliance"

    # -- parse ---------------------------------------------------------------------------------------

    def parse(self, document: dict) -> TopologyInputs:
        fixtures = parse_fixtures(document)
        cases = _cases(document)
        objective = document.get("objective", "stiffest")
        if objective not in OBJECTIVES:
            raise ValueError(f"objective: {kinds.json_text(objective)} is not one of {list(OBJECTIVES)} "
                             "(stiffest: the stiffest part from the material kept; lightest: the least material that holds)")
        fraction = _fraction(document, objective)
        keep: tuple[str, ...] = ()
        if "keep" in document:
            keep = kinds.faces({"faces": document["keep"]}, where="keep")
        member = None
        if "min_member_mm" in document:
            member = kinds.number(document["min_member_mm"], where="min_member_mm", positive=True)
        penalty = 3.0
        if "penalty" in document:
            penalty = kinds.number(document["penalty"], where="penalty", positive=True)
            if not 1.0 <= penalty <= 6.0:
                raise ValueError(f"penalty: SIMP's exponent, from 1 to 6 (3 is usual), got {penalty:g}")
        loads = tuple(load for _, case in cases for load in case)
        refs = tuple(dict.fromkeys(ref for group in (*fixtures, *loads) for ref in group.faces))
        refs = tuple(dict.fromkeys((*refs, *keep)))
        anchors = tuple(dict.fromkeys(ref for fixture in fixtures for ref in fixture.faces))
        view = document.get("view")
        checks = view.get("checks") if isinstance(view, dict) else None
        if objective == "lightest" and isinstance(checks, list) and checks and not any(
                isinstance(c, dict) and c.get("kind") in ("stress", "displacement") for c in checks):
            raise ValueError("view.checks: a lightest study needs a limit to stay within: add a stress check (its safety "
                             "factor) or a displacement check (the most it may move)")
        return TopologyInputs(
            refs, anchors, True, fixtures=fixtures, loads=loads, objective=objective, volume_fraction=fraction, keep=keep,
            min_member_mm=member, penalty=penalty, symmetry=_symmetry(document.get("symmetry")),
            extrusion=_extrusion(document.get("extrusion")), cases=cases, iterations=_iterations(document),
        )

    # -- the ladder (fit.py drives these) -------------------------------------------------------------

    def _rounds(self, inputs: TopologyInputs) -> int:
        return LIGHTEST_ROUNDS if inputs.objective == "lightest" else 1

    def estimate(self, ctx: SolveContext, inputs: TopologyInputs):
        """A linear solve per iteration (``len(cases)`` right-hand sides), the iterations of every round, plus the
        verification solves."""
        from cadgen._internal.fea import fit

        passes = inputs.iterations * self._rounds(inputs) * (1.0 + 0.3 * (len(inputs.cases) - 1)) + 2 * self._rounds(inputs)
        return fit.solid_estimate(ctx, passes=passes)

    def apply(self, rung, ctx: SolveContext, inputs: TopologyInputs):
        from cadgen._internal.fea import fit

        if rung == "coarse_design":
            return self._apply_coarse(ctx, inputs)
        if rung in ("iterative", "symmetry"):
            return fit.apply_generic(rung, self, ctx, inputs)
        return None

    def _apply_coarse(self, ctx: SolveContext, inputs: TopologyInputs):
        """A coarser design mesh, the coarsest that fits from the fine end; it says the member size it resolves."""
        from cadgen._internal.fea import fit

        plan, geometry = ctx.plan, ctx.geometry
        size = plan.size_mm or plan.requested_mm
        if size is None:
            return None
        diagonal = geometry.bbox_diagonal_mm if geometry is not None else ctx.volume.bbox_diagonal
        ceiling = diagonal / MIN_ELEMENTS_ACROSS
        if ceiling < 1.25 * size:
            return None
        chosen = ceiling
        for k in range(1, 13):
            plan.size_mm = size * (ceiling / size) ** (k / 12)
            if self.estimate(ctx, inputs).fits(ctx.budget):
                chosen = plan.size_mm
                break
        plan.size_mm = chosen
        member = MEMBER_ELEMENTS * chosen
        asked = inputs.min_member_mm
        accuracy = (f"members under about {_figure(member)} mm cannot form" if asked is None or asked < member
                    else None)
        return fit.Step(
            "coarse_design",
            f"Used a coarser design mesh ({_figure(chosen)} mm elements, from {_figure(size)} mm) to fit: it resolves "
            f"members down to about {_figure(member)} mm",
            accuracy, None, detail={"from_size_mm": round(size, 4), "to_size_mm": round(chosen, 4), "member_mm": round(member, 4)},
        )

    def symmetric_about(self, plane, inputs: TopologyInputs, ctx: SolveContext) -> bool:
        """As static's (fixtures, every case's loads and the checks), and every kept face onto itself; an
        extrusion must lie in the plane."""
        if not StaticAnalysis().symmetric_about(plane, inputs, ctx):
            return False
        ordinals = {ctx.ordinal_of[ref] for ref in inputs.keep}
        if {plane.mirror.get(o) for o in ordinals} != ordinals:
            return False
        if inputs.extrusion is not None and abs(inputs.extrusion[plane.component]) > 1e-9:
            return False
        return True

    # -- solve ---------------------------------------------------------------------------------------

    def solve(self, ctx: SolveContext, inputs: TopologyInputs) -> AnalysisResult:
        import time

        import numpy as np
        from scipy.spatial import cKDTree

        from cadgen._internal.fea import operators, topology_ops as topo
        from cadgen._internal.fea.analyses.nonlinear import external_load
        from cadgen._internal.fea.supports import check_held, supports_of

        if ctx.assembly is not None:
            raise ValueError("topology studies lighten one part: solve it with --occurrence, or study each part on its own")
        space = ctx.space
        if space.order != 1:
            raise ValueError("study.mesh.order: topology studies take order 1 (linear design elements)")
        material = ctx.materials[0]
        volume = ctx.volume
        basis = space.basis
        timings: dict[str, float] = {}
        warnings: list[str] = []
        started = time.perf_counter()
        fit_plan = ctx.plan
        planes = list(fit_plan.prepared.planes) if fit_plan is not None and fit_plan.prepared is not None else []
        share = 0.5 ** len(planes)

        points = space.dof_locations
        tets = space.tets
        Ke, element_volume, gradients = topo.tet_stiffness(points, tets, operators.elasticity_matrix(material))
        node_dofs = np.stack([basis.nodal_dofs[c] for c in range(3)], axis=1)
        element_dofs = node_dofs[tets].reshape(len(tets), 12)
        plane_dofs = []
        for plane in planes:
            dofs = basis.get_dofs(space.facets_of_ordinals([plane.ordinal], "a symmetry plane")).all()
            plane_dofs.append(dofs[space.component[dofs] == plane.component])
        supports = supports_of(space, inputs.fixtures, ctx.ordinal_of, held=plane_dofs)
        check_held(space, supports)
        free = np.setdiff1d(np.arange(basis.N), supports.fixed)
        F = np.stack([external_load(space, [material], loads, (), ctx.ordinal_of, share) for _, loads in inputs.cases], axis=1)

        # The element size the design mesh resolves, and the thinnest member the filter lets form.
        h = float(volume.max_h)
        edges = np.linalg.norm(points[tets[:, 1]] - points[tets[:, 0]], axis=1)
        h = min(h, float(np.median(edges)) * 1.2) if len(edges) else h
        least = LEAST_MEMBER_ELEMENTS * h
        member = inputs.min_member_mm if inputs.min_member_mm is not None else MEMBER_ELEMENTS * h
        if member < least:
            warnings.append(f"min_member_mm {member:g} is under the {least:.3g} mm the {h:.3g} mm design mesh can resolve; "
                            f"the design keeps members of about {least:.3g} mm (a finer mesh.size_mm makes thinner ones)")
            member = least
        radius = topo.filter_radius(member)

        # What stays solid: near the fixtures, the loads, the bolt holes and the faces the study keeps.
        holes = hole_faces(ctx.geometry)
        named = {ctx.ordinal_of[ref] for ref in inputs.face_refs}
        kept_ordinals = sorted(named | set(holes))
        rows = np.isin(volume.boundary_ordinal, kept_ordinals)
        centroids = points[tets].mean(axis=1)
        keep = np.zeros(len(tets), dtype=bool)
        depth = h  # one design element: the skin the fixtures, loads and holes sit on
        if rows.any():
            triangles = volume.boundary[rows][:, :3]
            samples = np.concatenate([points[np.unique(triangles)], points[triangles].mean(axis=1)])
            distance, _ = cKDTree(samples).query(centroids)
            keep = distance <= depth
        reasons = {ordinal: "kept" for ordinal in {ctx.ordinal_of[ref] for ref in inputs.keep}}
        for ordinal in {ctx.ordinal_of[ref] for f in inputs.fixtures for ref in f.faces}:
            reasons.setdefault(ordinal, "fixture")
        for ordinal in {ctx.ordinal_of[ref] for load in inputs.loads for ref in load.faces}:
            reasons.setdefault(ordinal, "load")
        for ordinal in holes:
            reasons.setdefault(ordinal, "bolt hole")
        kept_faces = [{"face": volume.faces[o].ref, "why": reasons.get(o, "kept")} for o in kept_ordinals if o in volume.faces]
        inputs.found["kept_solid"] = [entry["face"] for entry in kept_faces]

        # Symmetry planes and extrusion the design must keep (the ladder's own half needs none about its plane).
        design_map = topo.DesignMap(len(tets))
        lows, highs = points.min(axis=0), points.max(axis=0)
        cut_axes = {plane.axis for plane in planes}
        for axis, at in inputs.symmetry:
            if axis in cut_axes:
                continue
            component = _AXES.index(axis)
            offset = at if at is not None else 0.5 * (lows[component] + highs[component])
            miss = design_map.add_mirror(centroids, component, offset, h)
            if miss > 0.6:
                raise ValueError(f"symmetry: the part is not symmetric about the {axis.upper()} = {offset:.4g} mm plane "
                                 f"(its elements' mirror images miss by {miss:.1f} elements on average); "
                                 "name the plane with at_mm, or leave symmetry out")
        if inputs.extrusion is not None:
            design_map.add_extrusion(centroids, np.asarray(inputs.extrusion), h)
        if design_map.active:
            keep = design_map.apply(keep.astype(float), element_volume) > 1e-9
        kept_share = float(element_volume[keep].sum() / element_volume.sum())
        if kept_share >= inputs.volume_fraction - 0.01:
            raise ValueError(
                f"volume_fraction: the material kept solid near the fixtures, loads, holes and kept faces is already "
                f"{kept_share * 100:.0f} % of the part, so keeping {inputs.volume_fraction * 100:.0f} % leaves nothing to "
                "design; keep more material, or a finer mesh.size_mm keeps a thinner layer")

        problem = topo.TopologyProblem(
            points=points, tets=tets, Ke=Ke, volume=element_volume, gradients=gradients, element_dofs=element_dofs,
            ndof=int(basis.N), loads=F, free=free, keep=keep, frame=supports if supports.turned else None,
            near_nullspace=operators.rigid_body_modes(space.locations, space.component),
        )
        method = "iterative" if fit_plan is not None and fit_plan.solver != "direct" else "auto"
        schedule = topo.Schedule(penalty=inputs.penalty, max_iterations=inputs.iterations)
        frames_max = int(getattr(ctx.budget, "max_frames", 24) or 24) if ctx.budget is not None else 24
        timings["assemble_s"] = time.perf_counter() - started

        # The full part, solid: the baseline the design's compliance is measured against.
        solver = topo.LinearSolver(problem, method)
        solid_compliance = float(problem.energies(solver.solve(problem.assemble(np.ones(len(tets))))).sum())

        def verify(projected):
            return self._verify(ctx, inputs, volume, space, tets, element_volume, Ke, projected, supports, planes, material)

        started = time.perf_counter()
        rounds: list[dict] = []
        if inputs.objective == "stiffest":
            x, projected, history, used = topo.optimise(problem, inputs.volume_fraction, schedule, radius=radius,
                                                        design_map=design_map, method=method, keep_frames=frames_max,
                                                        log=ctx.log)
            verified = verify(projected)
            chosen_fraction = inputs.volume_fraction
        else:
            x, projected, history, used, verified, chosen_fraction, rounds = self._lightest(
                ctx, inputs, problem, schedule, radius, design_map, method, frames_max, verify, kept_share)
        timings["solve_s"] = time.perf_counter() - started
        if not history.converged:
            warnings.append(f"the design was still changing after {inputs.iterations} iterations; raise iterations for a "
                            "settled design (the last one is written)")

        # Mirror the half back into the whole part.
        started = time.perf_counter()
        frames = topo.frames_to_keep(history, frames_max)
        frame_values = [history.frames[k].astype(float) for k in frames]
        vm = verified["von_mises"]
        disp = verified["displacement"]
        dof_locations, boundary, out_tets, out_elements, vertices = (space.dof_locations, space.boundary_quadratic, space.tets,
                                                                     space.element_dofs, space.vertices)
        element_projected = projected
        reactions, applied = list(verified["reactions"]), tuple(verified["applied"])
        for plane in reversed(planes):
            from cadgen._internal.fea import symmetry

            whole, kept_rows = symmetry.unfold_volume(volume, plane)
            scalars = {f"m{i}": values for i, values in enumerate(frame_values)}
            scalars["vm"] = vm
            dof_locations, scalars, vectors, boundary, out_tets, out_elements, vertices = symmetry.unfold_fields(
                plane, vertices, dof_locations, kept_rows, scalars=scalars, vectors={"u": disp}, boundary=boundary,
                tets=out_tets, element_dofs=out_elements,
            )
            frame_values = [scalars[f"m{i}"] for i in range(len(frame_values))]
            vm, disp = scalars["vm"], vectors["u"]
            element_projected = np.concatenate([element_projected, element_projected])
            reactions = [symmetry.unfold_force(plane, r) for r in reactions]
            applied = symmetry.unfold_force(plane, applied)
            volume = whole
        ctx.volume = volume
        whole_factor = 2.0 ** len(planes)

        # The design's surface at rho = 0.5, smoothed for rebuilding in CAD.
        final_nodal = frame_values[-1]
        surface_vertices, surface_triangles, fixed = topo.iso_surface(dof_locations, out_tets, final_nodal, boundary)
        smoothed = topo.smooth(surface_vertices, surface_triangles, fixed)
        surface_volume = topo.enclosed_volume(smoothed, surface_triangles) if len(surface_triangles) else 0.0
        timings["surface_s"] = time.perf_counter() - started

        attributes = {"material_kept": "_MATERIAL_KEPT"}
        last = len(frames) - 1
        series = Series(kind="time", unit="", default=last, frames=[
            SeriesFrame(value=float(k), label="Final design" if i == last else f"Iteration {k}",
                        attributes={name: attr if i == 0 else f"{attr}_F{i}" for name, attr in attributes.items()})
            for i, k in enumerate(frames)
        ])
        iterations = len(history.compliance) - 1
        x_axis = list(range(len(history.compliance)))
        curves = {
            "compliance_Nmm": {"x": x_axis, "x_unit": "iteration", "y": [round(c * whole_factor, 6) for c in history.compliance],
                               "y_unit": "N mm"},
            "volume_fraction": {"x": x_axis, "x_unit": "iteration", "y": [round(v, 6) for v in history.volume], "y_unit": ""},
            "grey_fraction": {"x": x_axis, "x_unit": "iteration", "y": [round(g, 6) for g in history.grey], "y_unit": ""},
        }
        if rounds:
            curves["lightest_rounds"] = {"x": [r["volume_fraction"] for r in rounds], "x_unit": "",
                                         "y": [1.0 if r["passes"] else 0.0 for r in rounds], "y_unit": "passes"}
        domain_volume = float(element_volume.sum()) * whole_factor
        density = getattr(material, "density", None)
        return AnalysisResult(
            dof_locations=dof_locations, vertices=vertices, tets=out_tets, boundary_quadratic=boundary,
            element_dofs=out_elements,
            fields={"material_kept": frame_values[0], "von_mises": vm, "displacement": disp},
            deformation=disp, series=series, frame_fields={"material_kept": frame_values}, curves=curves,
            reactions=reactions, applied=applied, dofs=int(basis.N),
            solver=f"{history.solver}; {iterations} iterations", timings=timings, warnings=warnings,
            scalars={
                "history": history, "iterations": iterations, "converged": history.converged,
                "compliance": history.compliance[-1] * whole_factor, "solid_compliance": solid_compliance * whole_factor,
                "verified_compliance": verified["compliance"] * whole_factor if verified["compliance"] is not None else None,
                "volume_fraction": history.volume[-1], "target_fraction": chosen_fraction,
                "design_fraction": verified["fraction"], "kept_share": kept_share, "grey": history.grey[-1],
                "domain_volume_mm3": domain_volume, "density": density, "surface": (smoothed, surface_triangles),
                "surface_volume_mm3": surface_volume, "min_member_mm": member, "filter_radius_mm": radius,
                "design_size_mm": h, "kept_faces": kept_faces, "solved": verified["solved"],
                "dropped_pieces": verified["dropped"], "cases": [
                    {"name": name or "load", "compliance_Nmm": round(c * whole_factor, 6)}
                    for (name, _), c in zip(inputs.cases, verified["case_compliance"])],
                "rounds": rounds, "final_stage_start": history.final_stage_start, "element_density": element_projected,
                "part_refs": None,
            },
        )

    def _verify(self, ctx, inputs, volume, space, tets, element_volume, Ke, projected, supports, planes, material) -> dict:
        """The thresholded design (rho > 0.5, the pieces a fixture holds) solved as a static part: its stress,
        displacement, compliance and reactions, each field on every node of the design mesh (0 off the design)."""
        import numpy as np

        from cadgen._internal.fea import solve as static_solve
        from cadgen._internal.fea.analyses.static import solved_record
        from cadgen._internal.fea.femspace import FemSpace

        points = space.dof_locations
        nodes = len(points)
        kept = projected > 0.5
        fixture_rows = np.isin(volume.boundary_ordinal, [ctx.ordinal_of[ref] for f in inputs.fixtures for ref in f.faces])
        seeds = np.unique(volume.boundary[fixture_rows][:, :3])
        held = connected_to(tets, kept, seeds, nodes)
        dropped = int(kept.sum() - held.sum())
        fraction = float(element_volume[held].sum() / element_volume.sum())
        out = {"von_mises": np.zeros(nodes), "displacement": np.zeros((nodes, 3)), "reactions": [], "applied": (0.0, 0.0, 0.0),
               "compliance": None, "case_compliance": [0.0] * len(inputs.cases), "solved": None, "fraction": fraction,
               "dropped": dropped}
        if not held.any():
            return out
        sub, renumber = kept_volume(volume, held)
        rollers = [((p.ordinal,), p.component) for p in planes if (sub.boundary_ordinal == p.ordinal).any()]
        sub_space = FemSpace.build(sub, 1)
        node_dofs = np.stack([sub_space.basis.nodal_dofs[c] for c in range(3)], axis=1)
        sub_dofs = node_dofs[renumber[tets[held]]].reshape(-1, 12)
        share = 0.5 ** len(planes)
        best = None
        compliances = []
        for name, loads in inputs.cases:
            scaled = tuple(_scaled(load, share) for load in loads)
            try:
                outcome = static_solve.solve_linear_static(sub, material, inputs.fixtures, scaled, ctx.ordinal_of,
                                                           space=sub_space, rollers=rollers)
            except (RuntimeError, ValueError) as exc:
                out["error"] = str(exc)
                return out
            ue = outcome.u[sub_dofs]
            compliances.append(float(np.einsum("ei,eij,ej->", ue, Ke[held], ue)))
            if best is None or float(outcome.von_mises.max()) > float(best.von_mises.max()):
                best = outcome
        used = np.flatnonzero(renumber >= 0)
        out["von_mises"][used] = best.von_mises[renumber[used]]
        out["displacement"][used] = best.displacement[renumber[used]]
        out["reactions"] = list(best.reactions)
        out["applied"] = tuple(best.applied)
        out["compliance"] = float(sum(compliances))
        out["case_compliance"] = compliances
        out["solved"] = solved_record(sub, best, ctx.study, ctx.ordinal_of, ctx.part_name, inputs.fixtures)
        return out

    def _lightest(self, ctx, inputs, problem, schedule, radius, design_map, method, frames_max, verify, kept_share):
        """The least volume fraction whose stiffest design passes the study's stress and displacement checks: from
        ``volume_fraction`` up until one passes, then halving the gap to the last that failed."""
        from cadgen._internal.fea import topology_ops as topo

        checks = [c for c in ctx.study.checks if c["kind"] in ("stress", "displacement")] if ctx.study is not None else []
        if not checks:
            checks = [{"kind": "stress"}]
        margin = ctx.study.margin if ctx.study is not None else 2.0

        def passes(verified) -> bool:
            import numpy as np

            solved = verified["solved"]
            if solved is None:
                return False
            for check in checks:
                if check["kind"] == "stress":
                    if solved.yield_MPa is None or solved.peak_MPa * margin > solved.yield_MPa:
                        return False
                elif float(np.linalg.norm(verified["displacement"], axis=1).max()) > check["limit_mm"]:
                    return False
            return True

        rounds: list[dict] = []
        best = None
        start = None
        low = max(kept_share + 0.02, 0.03)
        fraction = max(inputs.volume_fraction, low + 0.01)
        failed_below = low
        passed_at = None
        for _ in range(LIGHTEST_ROUNDS):
            x, projected, history, used = topo.optimise(problem, fraction, schedule, radius=radius, design_map=design_map,
                                                        method=method, start=start, keep_frames=frames_max, log=ctx.log)
            verified = verify(projected)
            ok = passes(verified)
            rounds.append({"volume_fraction": round(fraction, 4), "passes": ok,
                           "max_von_mises_MPa": round(float(verified["von_mises"].max()), 4),
                           "max_displacement_mm": round(float((verified["displacement"] ** 2).sum(axis=1).max() ** 0.5), 6)})
            if ok and (best is None or fraction < best[5]):
                best = (x, projected, history, used, verified, fraction)
            start = x
            if ok:
                passed_at = fraction
                fraction = 0.5 * (failed_below + fraction)
            else:
                failed_below = fraction
                fraction = 0.5 * (fraction + (passed_at if passed_at is not None else 1.0))
            if passed_at is not None and passed_at - failed_below < 0.01:
                break
        if best is None:
            best = (x, projected, history, used, verified, rounds[-1]["volume_fraction"])
        return (*best, rounds)

    # -- the automatic finer solve: not for a fixed design mesh ----------------------------------------

    def needs_finer(self, result: AnalysisResult, inputs: TopologyInputs, check_results: list[dict]) -> bool:
        return False

    # -- judging -------------------------------------------------------------------------------------

    def _mass_saved(self, result: AnalysisResult) -> float:
        return 100.0 * (1.0 - result.scalars["design_fraction"])

    def judge(self, check: dict, index: int, ctx: SolveContext, result: AnalysisResult, inputs: TopologyInputs) -> dict:
        import numpy as np

        from cadgen._internal.fea import checks

        where = f"view.checks[{index}]"
        if check["kind"] == "mass_saved":
            saved = self._mass_saved(result)
            need = float(check.get("min_percent", 25.0))
            ratio = need / saved if saved > 0 else math.inf
            return {
                "kind": "mass_saved", "label": check.get("label") or kinds.MASS_SAVED.default_label,
                "value": round(saved, 4), "limit": need, "unit": "%", "ratio": round(ratio, 6) if math.isfinite(ratio) else 1e9,
                "close_at": 0.9, "status": checks.check_status(ratio, 0.9), "where": {"ref": None, "at": [0.0, 0.0, 0.0]},
                "kept_percent": round(100.0 - saved, 4),
            }
        solved = result.scalars["solved"]
        if check["kind"] == "stress":
            if solved is None:
                return {"kind": "stress", "label": check.get("label") or "Strength", "value": 0.0, "limit": 1.0, "unit": "MPa",
                        "ratio": 1e9, "close_at": 0.5, "status": "fails", "where": {"ref": None, "at": [0.0, 0.0, 0.0]}}
            return checks.stress_check(solved, label=check.get("label"))
        peak = kinds.field_max_over(
            np.linalg.norm(result.fields["displacement"], axis=1), tuple(check.get("faces", ())),
            boundary=result.boundary_quadratic, boundary_ordinal=ctx.volume.boundary_ordinal, locations=result.dof_locations,
            face_ref=ctx.volume.faces, ordinal_of=ctx.ordinal_of, where=where,
        )
        return checks.displacement_check(peak.value, check["limit_mm"], at=peak.at, ref=peak.ref, faces=peak.faces,
                                         label=check.get("label"))

    def findings(self, ctx: SolveContext, result: AnalysisResult, inputs: TopologyInputs,
                 check_results: list[dict], *, assembly: bool) -> list[dict]:
        from cadgen._internal.fea import checks

        s = result.scalars
        found: list[dict] = []

        def finding(severity, kind, summary, description, items=()):
            return {"check": "fea", "severity": severity, "type": kind, "summary": summary, "description": description,
                    "items": list(items)}

        saved = self._mass_saved(result)
        ratio = s["verified_compliance"] / s["solid_compliance"] if s["verified_compliance"] and s["solid_compliance"] else None
        found.append(finding(
            "info", "topology_design",
            f"Kept {100 - saved:.0f} % of the material (saves {saved:.0f} %)"
            + (f": the design is {ratio:.2f}× as flexible as the solid part" if ratio else ""),
            f"compliance {s['compliance']:.4g} N mm (solid part {s['solid_compliance']:.4g} N mm) after {s['iterations']} iterations; "
            f"the design's surface at density 0.5 is written as an STL to rebuild in CAD"))
        if s["dropped_pieces"]:
            found.append(finding(
                "warning", "topology_loose_pieces",
                f"Left out {s['dropped_pieces']} design elements that no fixture holds",
                "pieces of the design above density 0.5 that are not joined to a fixed face carry nothing; the verification "
                "solve and the mass leave them out"))
        if s["grey"] > 0.1:
            found.append(finding(
                "warning", "topology_grey",
                f"{s['grey'] * 100:.0f} % of the design is still between solid and void",
                "raise iterations, or the design's thin regions are near the smallest member the mesh resolves"))
        stress = next((c for c in check_results if c["kind"] == "stress"), None)
        if stress is not None and s["solved"] is not None:
            found += checks.findings(s["solved"])
        for check in check_results:
            if check["kind"] == "mass_saved" and check["status"] == "fails":
                found.append(finding("error", "barely_lighter",
                                     f"The design saves {check['value']:.0f} % of the mass, less than the {check['limit']:g} % asked",
                                     "keep less material (a lower volume_fraction), or keep fewer faces solid"))
        return sorted(found, key=lambda item: {"error": 0, "warning": 1, "info": 2}[item["severity"]])

    # -- what is written -----------------------------------------------------------------------------

    def deformation_scale(self, result: AnalysisResult, bbox_diagonal: float, requested: float | None) -> float | None:
        # Drawn at its true size: the void's nodes do not move, so an exaggeration would tear the design domain's surface.
        return requested if requested is not None else 1.0

    def summary(self, result: AnalysisResult, inputs: TopologyInputs, check_results: list[dict]) -> dict:
        import numpy as np

        s = result.scalars
        saved = self._mass_saved(result)
        moved = np.linalg.norm(result.fields["displacement"], axis=1)
        vm = result.fields["von_mises"]
        density = s["density"]
        domain = s["domain_volume_mm3"]
        solved = s["solved"]
        summary: dict[str, Any] = {
            "objective": inputs.objective,
            "volume_fraction_target": round(s["target_fraction"], 6),
            "volume_fraction": round(s["volume_fraction"], 6),
            "design_volume_fraction": round(s["design_fraction"], 6),
            "mass_saved_percent": round(saved, 4),
            "part_volume_mm3": round(domain, 4),
            "design_volume_mm3": round(domain * s["design_fraction"], 4),
            "surface_volume_mm3": round(s["surface_volume_mm3"], 4),
            "part_mass_kg": None if not density else round(density * domain * 1000.0, 6),
            "design_mass_kg": None if not density else round(density * domain * s["design_fraction"] * 1000.0, 6),
            "compliance_Nmm": round(s["compliance"], 6),
            "verified_compliance_Nmm": None if s["verified_compliance"] is None else round(s["verified_compliance"], 6),
            "solid_compliance_Nmm": round(s["solid_compliance"], 6),
            "compliance_ratio": None if not s["verified_compliance"] else round(s["verified_compliance"] / s["solid_compliance"], 6),
            "iterations": s["iterations"],
            "converged": s["converged"],
            "final_stage_start": s["final_stage_start"],
            "penalty": inputs.penalty,
            "grey_percent": round(100.0 * s["grey"], 4),
            "min_member_mm": round(s["min_member_mm"], 4),
            "design_element_mm": round(s["design_size_mm"], 4),
            "kept_solid": s["kept_faces"],
            "kept_solid_percent": round(100.0 * s["kept_share"], 4),
            "load_cases": s["cases"],
            "max_von_mises_MPa": round(float(vm.max()), 4),
            "max_von_mises_at_mm": [round(float(c), 3) for c in result.dof_locations[int(vm.argmax())]],
            "max_displacement_mm": round(float(moved.max()), 6),
            "max_displacement_at_mm": [round(float(c), 3) for c in result.dof_locations[int(moved.argmax())]],
            "safety_factor": None,
            "dropped_elements": s["dropped_pieces"],
            "frames": len(result.series.frames),
            "deformation_scale": s.get("deformation_scale"),
        }
        if solved is not None:
            from cadgen._internal.fea import checks

            summary["safety_factor"] = checks.floored_factor(solved)
            summary["yield_MPa"] = solved.yield_MPa
        if s["rounds"]:
            summary["lightest_rounds"] = s["rounds"]
        summary["checks"] = check_results
        return summary

    def extras_name(self, stem: str) -> str:
        return f"{stem} topology"

    def field_ranges(self, summary: dict, result: AnalysisResult) -> dict[str, tuple[float, float]]:
        import numpy as np

        return {
            "material_kept": (0.0, 1.0),
            "von_mises": (0.0, round(float(result.fields["von_mises"].max()), 4)),
            "displacement": (0.0, round(float(np.linalg.norm(result.fields["displacement"], axis=1).max()), 6)),
        }

    def extras_head(self, summary: dict) -> dict:
        return {"mass_saved_percent": summary["mass_saved_percent"], "volume_fraction": summary["volume_fraction_target"]}

    def study_echo(self, inputs: TopologyInputs, bare: Callable[[tuple[str, ...]], list[str]]) -> dict:
        echo = StaticAnalysis().study_echo(inputs, bare)
        echo.update({
            "objective": inputs.objective,
            "volume_fraction": inputs.volume_fraction,
            "keep": bare(inputs.keep),
            "kept_solid": list(inputs.found.get("kept_solid", [])),
            "penalty": inputs.penalty,
        })
        if inputs.min_member_mm is not None:
            echo["min_member_mm"] = inputs.min_member_mm
        if inputs.symmetry:
            echo["symmetry"] = [{"axis": axis, **({"at_mm": at} if at is not None else {})} for axis, at in inputs.symmetry]
        if inputs.extrusion is not None:
            echo["extrusion"] = list(inputs.extrusion)
        if len(inputs.cases) > 1:
            echo["load_cases"] = [
                {"name": name, "loads": StaticAnalysis().study_echo(StaticInputs((), (), True, loads=loads), bare)["loads"]}
                for name, loads in inputs.cases
            ]
        return echo

    def write_files(self, result: AnalysisResult, summary: dict, glb_path) -> dict:
        """The design's surface at density 0.5, smoothed, as an STL beside the GLB; its name goes in the summary."""
        from cadgen._internal.fea import topology_ops as topo

        vertices, triangles = result.scalars["surface"]
        path = glb_path.with_name(f"{glb_path.stem}.design.stl")
        topo.write_stl(path, vertices, triangles, name=f"cadgen topology {glb_path.stem}")
        summary["design_stl"] = path.name
        summary["design_triangles"] = int(len(triangles))
        return {"design_stl": path.name}

    def human_lines(self, summary: dict) -> list[str]:
        ratio = summary.get("compliance_ratio")
        lines = [
            f"{summary['objective']}: kept {100 - summary['mass_saved_percent']:.1f} % of the material (target "
            f"{summary['volume_fraction_target'] * 100:.1f} %), saves {summary['mass_saved_percent']:.1f} %",
            f"compliance {summary['compliance_Nmm']:.4g} N mm, solid part {summary['solid_compliance_Nmm']:.4g} N mm"
            + (f"; the verified design is {ratio:.2f}× as flexible" if ratio else ""),
            f"verified design: peak stress {summary['max_von_mises_MPa']:.4g} MPa, max displacement "
            f"{summary['max_displacement_mm']:.4g} mm"
            + (f", safety factor {summary['safety_factor']:.3g}" if summary.get("safety_factor") else ""),
            f"{summary['iterations']} iterations ({'converged' if summary['converged'] else 'not settled'}), "
            f"{summary['grey_percent']:.1f} % grey, members down to {summary['min_member_mm']:.3g} mm",
        ]
        if summary.get("design_stl"):
            lines.append(f"design surface: {summary['design_stl']} (rebuild it in CAD, then re-run a static study)")
        return lines


def _scaled(load: Load, share: float) -> Load:
    """A force's share on a symmetric half (a pressure acts on what is there)."""
    import dataclasses

    if load.type != "force" or share == 1.0:
        return load
    return dataclasses.replace(load, vector=tuple(share * c for c in load.vector))
