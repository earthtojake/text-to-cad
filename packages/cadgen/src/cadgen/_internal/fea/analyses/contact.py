"""Contact (lite): parts that press on each other or slide instead of being glued, and parts resting on a rigid plane.

The study (spec 5.17) takes static's ``fixtures`` and ``loads``, ``steps``
(the starting number of load steps, 5), and two kinds of contact:

- ``connections`` of ``"type": "contact"`` between two named parts, with an
  optional Coulomb ``friction`` (0, frictionless, by default). Only this
  analysis accepts them; every other touching pair stays bonded, as in every
  other analysis. The two parts are meshed apart, nothing glued between them.
- ``rigid_planes``: ``{"point_mm", "normal", "parts", "friction"}``, a rigid
  floor the named parts (every part, by default) cannot pass through; the
  normal points from the plane to the parts.

:mod:`..contact_ops` pairs each surface node of the smaller part with the
closest point of the other's surface before loading (small sliding) and
enforces no interpenetration by augmented Lagrange inside
:mod:`..nonlinear_driver`, with Coulomb friction by a return map. The parts
stay linear elastic. A part nothing fixes may rest on contacts alone (a very
weak spring keeps it from drifting where nothing else holds it); a part held
by nothing at all is a study error naming it.

What it writes: a series of load steps (``kind: "time"``, unit ``%``,
"60 % load"), each with the von Mises stress, the displacement and the contact
pressure (on contact faces, else 0). Checks: ``stress`` (by default),
``displacement`` and ``contact_pressure`` (``limit_MPa``, optional ``faces``),
judged at the last load carried. Findings say in plain words which pairs press
and how hard, which separate, which slide or stick, and where the contact
pressure peaks. Stdlib only at import.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar

from cadgen._internal.fea.analyses import kinds
from cadgen._internal.fea.analyses.base import AnalysisResult, FieldSpec, Series, SeriesFrame, SolveContext
from cadgen._internal.fea.analyses.nonlinear import NonlinearAnalysis, NonlinearInputs, load_label, part_materials, pick_frames, with_materials
from cadgen._internal.fea.study import parse_fixtures, parse_loads

if TYPE_CHECKING:
    import numpy as np

__all__ = [
    "ContactAnalysis", "ContactInputs", "ContactPair", "DEFAULT_STEPS", "LIMITS", "RigidPlane", "contact_words",
    "mark_unsettled", "parse_rigid_planes", "path_deadline", "parse_steps", "unsettled_extras", "unsettled_sentence", "unsettled_steps",
]

#: Load steps a study starts with when it names none.
DEFAULT_STEPS = 5
#: The most starting steps a study may ask for.
MAX_STEPS = 200
#: The largest Coulomb coefficient a study may give.
MAX_FRICTION = 2.0
#: The Uzawa updates a load step takes on average, as extra Newton solves, for the cost estimate.
AUGMENT_COST = 2.0
#: Frames a series keeps when the budget does not say.
MAX_FRAMES = 24
#: The contact forces still changing by more than this share after the last Uzawa update is worth a warning.
UNSETTLED = 0.1
#: A body resting on contacts whose drift springs carry more than this share of its load (or of the whole load) is not
#: held by them.
LOOSE_SHARE = 0.01
#: A node moved along the surface less than this share of the largest displacement has not slid.
SLIDE_SHARE = 0.02

#: What this lite solver leaves out, written into its output, its verdict's Details and the skill.
LIMITS = (
    "Small sliding: each surface node is paired once, before loading, with the surface it faces, so parts may slide "
    "only a fraction of an element along each other",
    "Node-to-surface contact: the pressure is resolved to the mesh, so a point or line contact needs fine elements "
    "where it touches",
    "Static: no impact or inertia; friction is Coulomb with one coefficient, the same at rest and sliding",
    "The parts stay linear elastic, and an overlap within the contact tolerance counts as just touching (no press fit)",
    "A part held only by contacts is kept from drifting where they do not hold it by a very weak spring",
)


@dataclass(frozen=True)
class ContactPair:
    """A ``contact`` connection: the two parts as the study names them, and Coulomb's μ."""

    between: tuple[str, str]
    friction: float = 0.0


@dataclass(frozen=True)
class RigidPlane:
    """A rigid plane: a point on it, its unit normal (towards the parts), the parts it holds up (all when empty), μ."""

    point: tuple[float, float, float]
    normal: tuple[float, float, float]
    parts: tuple[str, ...] = ()
    friction: float = 0.0


@dataclass(frozen=True)
class ContactInputs(NonlinearInputs):
    pairs: tuple[ContactPair, ...] = ()
    planes: tuple[RigidPlane, ...] = ()


def contact_words(between: tuple[str, str], friction: float) -> str:
    """A pair as Study and the findings name it: "pin presses on plate, friction 0.2" or ", no friction"."""
    return f"{between[0]} presses on {between[1]}, " + (f"friction {friction:g}" if friction else "no friction")


def _friction(entry: dict, where: str) -> float:
    if "friction" not in entry:
        return 0.0
    value = kinds.number(entry["friction"], where=f"{where}.friction")
    if not 0.0 <= value <= MAX_FRICTION:
        raise ValueError(f"{where}.friction: Coulomb's coefficient, from 0 (frictionless) to {MAX_FRICTION:g}, like 0.2 "
                         f"for dry steel on steel; got {value:g}")
    return value


def _pairs(document: dict) -> tuple[ContactPair, ...]:
    entries = document.get("connections")
    if not isinstance(entries, list):
        return ()
    pairs = []
    for index, entry in enumerate(entries):
        where = f"connections[{index}]"
        if not isinstance(entry, dict):
            continue  # study._connections says what is wrong with it
        unknown = set(entry) - {"between", "type", "friction"}
        if unknown:
            raise ValueError(f"{where}: unknown keys {sorted(unknown)}; a connection takes between, type and (contact) friction")
        if entry.get("type") != "contact":
            if "friction" in entry:
                raise ValueError(f"{where}.friction: only a contact connection slides; {kinds.json_text(entry.get('type'))} "
                                 "parts are glued or apart")
            continue
        between = entry.get("between")
        if not isinstance(between, list) or len(between) != 2 or not all(isinstance(n, str) and n.strip() for n in between):
            raise ValueError(f'{where}.between: name the two parts, like ["pin", "plate"]')
        pairs.append(ContactPair((between[0].strip(), between[1].strip()), _friction(entry, where)))
    return tuple(pairs)


def parse_rigid_planes(document: dict) -> tuple[RigidPlane, ...]:
    raw = document.get("rigid_planes")
    if raw is None:
        return ()
    if not isinstance(raw, list) or not raw:
        raise ValueError('rigid_planes: a list like [{"point_mm": [0, 0, 0], "normal": [0, 0, 1], "parts": ["plate"]}]')
    planes = []
    for index, entry in enumerate(raw):
        where = f"rigid_planes[{index}]"
        if not isinstance(entry, dict):
            raise ValueError(f"{where}: expected an object with point_mm and normal")
        unknown = set(entry) - {"point_mm", "normal", "parts", "friction"}
        if unknown:
            raise ValueError(f"{where}: unknown keys {sorted(unknown)}; a rigid plane takes point_mm, normal, parts and friction")
        vectors = []
        for key, words in (("point_mm", "a point on the plane as [x, y, z] in mm"),
                           ("normal", "the direction the plane faces, towards the parts, as [x, y, z], like [0, 0, 1]")):
            value = entry.get(key)
            if not isinstance(value, list) or len(value) != 3:
                raise ValueError(f"{where}.{key}: {words}")
            vectors.append(tuple(kinds.number(v, where=f"{where}.{key}") for v in value))
        length = math.sqrt(sum(c * c for c in vectors[1]))
        if not length > 0:
            raise ValueError(f"{where}.normal: the normal is zero; give the direction the plane faces, like [0, 0, 1]")
        parts = entry.get("parts", [])
        if isinstance(parts, str):
            parts = [parts]
        if not isinstance(parts, list) or not all(isinstance(p, str) and p.strip() for p in parts):
            raise ValueError(f'{where}.parts: the parts that rest on it by name, like ["plate"] (leave it out for every part)')
        planes.append(RigidPlane(vectors[0], tuple(c / length for c in vectors[1]), tuple(p.strip() for p in parts),
                                 _friction(entry, where)))
    return tuple(planes)


def parse_steps(document: dict) -> int:
    raw = document.get("steps", DEFAULT_STEPS)
    if isinstance(raw, bool) or not isinstance(raw, int) or not 1 <= raw <= MAX_STEPS:
        raise ValueError(f"steps: the number of load steps to start with, a whole number from 1 to {MAX_STEPS}, "
                         f"got {kinds.json_text(raw)}")
    return raw


def _material_specs(document: dict) -> list[Any]:
    specs = [document["material"]] if "material" in document else []
    parts = document.get("parts")
    if isinstance(parts, dict):
        specs += [entry["material"] for entry in parts.values() if isinstance(entry, dict) and "material" in entry]
    return specs


def unsettled_sentence(percent: float, of: str = "the load") -> str:
    """What a result says of a load step whose contact forces did not settle (it was kept at the smallest step)."""
    return (f"Contact did not settle at {percent:.0f}% of {of}: the forces here do not balance, so this result is "
            "not reliable")


def unsettled_steps(path, of: str = "the load") -> list[dict]:
    """The driver's steps kept unsettled (``PathResult.unsettled``), as ``{"percent", "of"}``."""
    return [{"percent": round(factor * 100.0, 4), "of": of} for factor in path.unsettled]


def unsettled_extras(unsettled: list[dict]) -> dict:
    """``extras.analysis.unsettled``: the shares of the load whose contact did not settle, and the first."""
    return {"at_percent": [step["percent"] for step in unsettled], "first_percent": unsettled[0]["percent"]}


def path_deadline(ctx) -> float:
    """Seconds after which a load path stuck cutting its steps stops (``nonlinear_driver.solve_path``'s ``deadline_s``):
    the study's time target (``fit.Budget.seconds``, 600 s by default)."""
    budget = getattr(ctx, "budget", None)
    return float(getattr(budget, "seconds", 0.0) or 600.0)


def mark_unsettled(judged: dict, scalars: dict) -> dict:
    """A check of a result with an unsettled step fails, saying at what share of the load (the first)."""
    unsettled = scalars.get("unsettled") or []
    if unsettled:
        judged["status"] = "fails"
        judged["unsettled_at_percent"] = unsettled[0]["percent"]
    return judged


def _pair_name(pair: ContactPair) -> str:
    return f"{pair.between[0]} on {pair.between[1]}"


def _plane_name(index: int, count: int) -> str:
    return "the rigid plane" if count == 1 else f"rigid plane {index + 1}"


class ContactAnalysis(NonlinearAnalysis):
    name: ClassVar[str] = "contact"
    tier: ClassVar[int] = 3
    word: ClassVar[str] = "Contact"
    estimate_only: ClassVar[bool] = False
    limits: ClassVar[tuple[str, ...]] = LIMITS
    study_keys: ClassVar[frozenset[str]] = frozenset({"fixtures", "loads", "steps", "rigid_planes"})
    material_needs: ClassVar[frozenset[str]] = frozenset()
    mesh_orders: ClassVar[tuple[int, ...]] = (2,)
    # The one analysis that accepts contact pairs (study._connections reads this); bonded stays the default.
    connection_types: ClassVar[tuple[str, ...]] = ("bonded", "free", "contact")
    fields: ClassVar[tuple[FieldSpec, ...]] = (
        FieldSpec("von_mises", "_VON_MISES", "von Mises stress", "MPa", per_frame=True),
        FieldSpec("displacement", "_DISPLACEMENT", "displacement", "mm", 3, 1000.0, per_frame=True),
        FieldSpec("contact_pressure", "_CONTACT_PRESSURE", "contact pressure", "MPa", per_frame=True),
    )
    checks: ClassVar[tuple] = (kinds.STRESS, kinds.DISPLACEMENT, kinds.CONTACT_PRESSURE)
    default_checks: ClassVar[tuple[dict, ...]] = ({"kind": "stress"},)
    # No load_scale: contact is not proportional to the load (it opens, closes and slides).
    drives: ClassVar[tuple[str, ...]] = ("field", "deformation", "threshold", "frame")
    default_controls: ClassVar[dict[str, dict]] = {
        "frame": {"drives": "frame", "type": "number", "min": 0.0, "max": 100.0},
        "field": {"drives": "field", "type": "enum", "options": ["von_mises", "displacement", "contact_pressure"]},
        "deformation": {"drives": "deformation", "type": "number", "min": 0.0, "max": None},
    }
    upstream: ClassVar[tuple[str, ...]] = ()
    ladder: ClassVar[tuple[str, ...]] = ("iterative", "adaptive_steps", "local_refine", "defeature", "symmetry")
    noun: ClassVar[str] = "this load"
    governing_word: ClassVar[str] = "peak contact pressure"

    # -- parse ---------------------------------------------------------------------------------------

    def parse(self, document: dict) -> ContactInputs:
        from cadgen._internal.fea.materials import material_from_spec

        fixtures = parse_fixtures(document, required=False)
        loads = parse_loads(document)
        steps = parse_steps(document)
        pairs = _pairs(document)
        planes = parse_rigid_planes(document)
        if not pairs and not planes:
            raise ValueError(
                'study: a contact study needs a contact: connections like [{"between": ["pin", "plate"], "type": "contact", '
                '"friction": 0.2}], or rigid_planes like [{"point_mm": [0, 0, 0], "normal": [0, 0, 1]}] for a rigid floor'
            )
        if not fixtures and not planes:
            raise ValueError(
                "study: nothing holds the parts still: add 'fixtures' (faces held fixed), or 'rigid_planes' "
                "(a rigid floor they rest on)"
            )
        view = document.get("view")
        checks = view.get("checks") if isinstance(view, dict) else None
        stress = [(i, c) for i, c in enumerate(checks)] if isinstance(checks, list) else [(None, {"kind": "stress"})]
        yieldless = any(material_from_spec(spec).yield_strength is None for spec in _material_specs(document))
        for index, check in stress:
            if isinstance(check, dict) and check.get("kind") == "stress" and yieldless:
                where = f"view.checks[{index}]" if index is not None else "view.checks"
                raise ValueError(f"{where}: a stress check compares the peak with a yield strength, and a material here has "
                                 "none; give its yield_MPa, or check the contact_pressure or displacement instead")
        refs = tuple(dict.fromkeys(ref for group in (*fixtures, *loads) for ref in group.faces))
        anchors = tuple(dict.fromkeys(ref for fixture in fixtures for ref in fixture.faces))
        needs = frozenset({"density"}) if any(load.body for load in loads) else frozenset()
        # requires_anchor is False: a part may rest on a contact or a rigid plane alone; solve() says when nothing holds one.
        return ContactInputs(refs, anchors, False, fixtures=fixtures, loads=loads, material_needs=needs, steps=steps,
                             model="elastic", pairs=pairs, planes=planes)

    # -- the ladder (fit.py drives these) -------------------------------------------------------------

    def estimate(self, ctx: SolveContext, inputs: ContactInputs):
        """Nonlinear's (each Newton iteration of each load step), with the Uzawa updates' extra solves."""
        from cadgen._internal.fea import fit

        base = super().estimate(ctx, inputs)
        return fit.Estimate(dofs=base.dofs, memory_bytes=base.memory_bytes, seconds=base.seconds * AUGMENT_COST)

    def apply(self, rung, ctx: SolveContext, inputs: ContactInputs):
        from cadgen._internal.fea import fit

        if rung == "adaptive_steps":
            if ctx.plan.adaptive_steps:
                return None
            ctx.plan.adaptive_steps = True
            from cadgen._internal.fea.nonlinear_driver import MAX_GROWTH

            return fit.Step(
                "adaptive_steps",
                f"Let the load steps grow (up to {MAX_GROWTH}× the {inputs.steps} starting ones) while the contacts "
                "settle in a few Newton iterations, cutting them where they do not, to fit the time target",
                "friction's slip is followed along the load in larger steps; the final contact is solved to the same "
                "tolerance", None, detail={"starting_steps": inputs.steps, "max_growth": MAX_GROWTH},
            )
        return super().apply(rung, ctx, inputs)

    def symmetric_about(self, plane, inputs: ContactInputs, ctx: SolveContext) -> bool:
        """Static's rule (one part only), and every rigid plane lies across the symmetry plane (its normal in it)."""
        from cadgen._internal.fea.analyses.static import StaticAnalysis

        if not StaticAnalysis().symmetric_about(plane, inputs, ctx):
            return False
        return all(abs(rigid.normal[plane.component]) <= 1e-9 for rigid in inputs.planes)

    def governing(self, result: AnalysisResult):
        """local_refine follows the contact pressure at the last load carried (the stress where nothing presses)."""
        pressure = result.scalars["final"]["contact_pressure"]
        if float(pressure.max()) > 0:
            return pressure, float(pressure.max())
        return super().governing(result)

    # -- solve ---------------------------------------------------------------------------------------

    def _part_index(self, ctx: SolveContext, name: str, where: str) -> int:
        if ctx.assembly is None:
            return 0
        from cadgen._internal.fea.run import find_part

        return find_part(ctx.assembly.parts, ctx.assembly.names, name, where)

    def _part_names(self, ctx: SolveContext) -> list[str]:
        return list(ctx.assembly.names) if ctx.assembly is not None else [ctx.part_name or "the part"]

    def solve(self, ctx: SolveContext, inputs: ContactInputs) -> AnalysisResult:
        import time

        import numpy as np

        from cadgen._internal.fea import contact_ops, nonlinear_driver, operators
        from cadgen._internal.fea.analyses.nonlinear import external_load
        from cadgen._internal.fea.checks import quoted
        from cadgen._internal.fea.supports import check_held, driven, held_bodies, path_to_global, supports_of

        space = ctx.space
        basis = space.basis
        materials = list(ctx.materials)
        timings: dict[str, float] = {}
        warnings: list[str] = []
        started = time.perf_counter()
        fit_plan = ctx.plan
        planes = list(fit_plan.prepared.planes) if fit_plan is not None and fit_plan.prepared is not None else []
        share = 0.5 ** len(planes)
        external = external_load(space, materials, inputs.surface_loads, inputs.body_accelerations, ctx.ordinal_of, share)
        plane_dofs = []
        for plane in planes:
            dofs = basis.get_dofs(space.facets_of_ordinals([plane.ordinal], "a symmetry plane")).all()
            plane_dofs.append(dofs[space.component[dofs] == plane.component])
        # Fixed faces, rollers (a sloped or curved one's nodes turned into their own axes: supports.py) and planes.
        supports = supports_of(space, inputs.fixtures, ctx.ordinal_of, held=plane_dofs)
        check_held(space, supports)
        fixture_dofs = supports.per_fixture
        fixed = supports.fixed
        free = np.setdiff1d(np.arange(basis.N), fixed)
        K = operators.stiffness(space, materials).tocsr()

        # The contacts: pairs between parts, then rigid planes.
        names = self._part_names(ctx)
        if ctx.assembly is not None:
            refs = [part.ref for part in ctx.assembly.parts]
        else:  # one part: its occurrence, as its faces' refs name it
            refs = [next((face.ref.rpartition(".f")[0] for face in ctx.volume.faces.values()), "")]
        node_part, node_body = contact_ops.body_of_nodes(space)
        points = space.dof_locations
        tolerance = float(ctx.study.contact_tolerance_mm) if ctx.study is not None else 0.1
        E_of_part = {index: float(materials[min(index, len(materials) - 1)].E) for index in range(max(len(names), 1))}

        def diagonal(parts) -> float:
            chosen = np.isin(node_part, list(parts))
            if not chosen.any():
                return 0.0
            return float(np.linalg.norm(points[chosen].max(axis=0) - points[chosen].min(axis=0)))

        rows: list = []
        contacts: list[dict] = []
        for n, pair in enumerate(inputs.pairs):
            where = f"connections (contact {n + 1})"
            i, j = (self._part_index(ctx, name, f"{where}.between") for name in pair.between)
            if i == j:
                raise ValueError(f"{where}.between: both names are {quoted(names[i])}")
            volume = (lambda k: ctx.assembly.parts[k].volume_mm3) if ctx.assembly is not None else (lambda k: 0.0)
            slave, master = (i, j) if volume(i) <= volume(j) else (j, i)
            search = max(2.0 * tolerance, 0.1 * min(diagonal([i]), diagonal([j])))
            spec = contact_ops.PairSpec(slave, master, pair.friction, len(contacts))
            found = contact_ops.pair_constraints(space, spec, node_part, min(E_of_part[i], E_of_part[j]),
                                                 search_mm=search, tolerance_mm=tolerance)
            rows.append(found)
            contacts.append({"kind": "pair", "name": _pair_name(pair), "between": [names[i], names[j]], "refs": [refs[i], refs[j]],
                             "friction": pair.friction, "words": contact_words((names[i], names[j]), pair.friction)})
        for n, plane in enumerate(inputs.planes):
            parts = tuple(sorted({self._part_index(ctx, name, f"rigid_planes[{n}].parts") for name in plane.parts})) \
                if plane.parts and ctx.assembly is not None else tuple(range(max(len(names), 1)))
            normal = np.asarray(plane.normal, dtype=float)
            on = np.isin(node_part, list(parts))
            if on.any() and float((points[on].mean(axis=0) - np.asarray(plane.point)) @ normal) < 0:
                normal = -normal  # it faces the parts it holds up
            spec = contact_ops.PlaneSpec(plane.point, tuple(float(c) for c in normal), parts, plane.friction, n)
            found = contact_ops.plane_constraints(space, spec, node_part, E_of_part,
                                                  search_mm=max(2.0 * tolerance, 0.1 * diagonal(parts)), tolerance_mm=tolerance)
            rows.append(found)
            contacts.append({"kind": "plane", "name": _plane_name(n, len(inputs.planes)), "refs": [refs[p] for p in parts],
                             "friction": plane.friction, "normal": [float(c) for c in normal],
                             "words": f"{' and '.join(names[p] for p in parts)} on {_plane_name(n, len(inputs.planes))}"})
        # Plane rows are owned by ``-1 - plane index``; number them after the pairs for one list of contacts.
        constraints = contact_ops.Constraints.concatenate(rows, space.scalar_count)
        owner = np.where(constraints.owner >= 0, constraints.owner, len(inputs.pairs) + (-1 - constraints.owner))

        # What holds each body (a connected piece of mesh): a fixture, a rigid plane, or a contact with a held body.
        bodies = int(node_body.max()) + 1 if len(node_body) else 0
        scalar_of = np.zeros(basis.N, dtype=np.int64)
        vdofs = contact_ops.vector_dofs(space)
        for c in range(3):
            scalar_of[vdofs[:, c]] = np.arange(space.scalar_count)
        fixed_bodies = held_bodies(space, supports, node_body[scalar_of])  # a body on rollers alone may still move
        holds = set(fixed_bodies)
        holds |= set(np.unique(node_body[constraints.node[constraints.owner < 0]]).tolist())
        links = []
        for k in range(len(inputs.pairs)):
            mine = constraints.owner == k
            if mine.any():
                links.append((set(np.unique(node_body[constraints.node[mine]]).tolist()),
                              set(np.unique(node_body[constraints.master_nodes(mine)]).tolist())))
        grown = True
        while grown:
            grown = False
            for a, b in links:
                if (a & holds) and not b <= holds or (b & holds) and not a <= holds:
                    holds |= a | b
                    grown = True
        unheld = [b for b in range(bodies) if b not in holds]
        if unheld:
            parts_of = sorted({int(p) for p in np.unique(node_part[np.isin(node_body, unheld)])})
            who = " and ".join(quoted(names[p]) for p in parts_of)
            raise ValueError(
                f"{who} {'is' if len(parts_of) == 1 else 'are'} not held by anything: fix a face of it, put it in contact "
                "with a held part (the faces must face each other, near enough to touch), or give it a rigid plane to rest on"
            )
        loose = [b for b in range(bodies) if b not in fixed_bodies]
        floating = [vdofs[node_body == b].ravel() for b in loose]
        stabilise = contact_ops.stabilising_springs(K, basis.N, floating)
        # A body resting on contacts alone first moves, rigidly, along its load until it touches (a stress-free move).
        shift = contact_ops.close_gaps(constraints, node_body, vdofs, external, loose)
        timings["assemble_s"] = time.perf_counter() - started

        history: list[tuple] = []

        def record(u, response):
            vm = operators.von_mises(operators.stress(space, materials, u))
            history.append((vm, response))

        solver = getattr(fit_plan, "solver", "direct") if fit_plan is not None else "direct"
        method = "iterative" if solver in ("iterative", "matrix_free") else "direct"
        adaptive = bool(getattr(fit_plan, "adaptive_steps", False)) if fit_plan is not None else False
        problem = contact_ops.ContactProblem(space, K, free, external, constraints, stabilise, method=method,
                                             on_commit=record)
        if ctx.log:
            ctx.log(f"{constraints.count} contact nodes over {len(contacts)} contacts; {len(floating)} bodies rest on contacts alone")
        # runaway=None: a part that rests on a contact has no stiffness of its own until the contact closes.
        path = path_to_global(nonlinear_driver.solve_path(driven(problem, supports, free), steps=inputs.steps, solver=solver,
                                                          adaptive=adaptive, runaway=None, log=ctx.log,
                                                          deadline_s=path_deadline(ctx)), supports)
        timings["solve_s"] = path.seconds
        warnings += path.warnings
        if problem.unsettled > UNSETTLED:
            warnings.append(f"the contact forces were still changing by {problem.unsettled * 100:.2g} % after "
                            f"{contact_ops.MAX_AUGMENTATIONS} updates at a load step")
        if ctx.log:
            ctx.log(f"followed the load to {path.factor * 100:.4g}% in {len(path.records)} steps, {path.iterations} Newton "
                    f"iterations and {problem.augmentations} contact updates, in {path.seconds:.1f}s")

        started = time.perf_counter()
        frames_max = int(getattr(ctx.budget, "max_frames", MAX_FRAMES) or MAX_FRAMES) if ctx.budget is not None else MAX_FRAMES
        records = path.records
        if not records:  # not even the smallest first step: the unloaded parts are the one frame
            zeros = np.zeros(problem.size)
            records = [nonlinear_driver.StepRecord(0.0, 0, zeros, 0.0)]
            history = [(np.zeros(basis.dx.shape), problem.response(zeros))]
        picked = pick_frames(len(records), max(frames_max, 1))
        # A step kept although its contact did not settle is always among the frames, and its label says so.
        loose_steps = {i for i, record in enumerate(records) if not record.settled}
        picked = sorted(set(picked) | loose_steps)

        def nodal(values):
            return np.clip(space.scalar.project(values), 0.0, float(values.max()))

        stress_frames, displacement_frames, pressure_frames = [], [], []
        for index in picked:
            vm_q, response = history[index]
            stress_frames.append(nodal(vm_q))
            displacement_frames.append(space.nodal(records[index].u + shift))
            pressure_frames.append(contact_ops.pressure_field(space, constraints, response.normal_force))
        final = records[-1]
        final_response = history[-1][1]
        final_pressure = pressure_frames[-1]  # the last step is always among the frames
        # A body resting on contacts alone whose load its drift springs take (more than a hair of it) is not held:
        # it comes loose when none of its contacts presses, else it slides away (friction cannot hold it sideways).
        pressing_bodies = set(np.unique(node_body[constraints.node[final_response.pressing]]).tolist())
        pressing_bodies |= set(np.unique(node_body[constraints.master_nodes(final_response.pressing & (constraints.owner >= 0))]).tolist())
        loose_parts: list[dict] = []
        total = float(np.linalg.norm([final.factor * external[space.component == k].sum() for k in range(3)]))
        for b, dofs in zip(loose, floating):
            spring = [float((stabilise[dofs] * final.u[dofs])[space.component[dofs] == k].sum()) for k in range(3)]
            load = [float(final.factor * external[dofs][space.component[dofs] == k].sum()) for k in range(3)]
            unheld = math.sqrt(sum(c * c for c in spring))
            if unheld > LOOSE_SHARE * max(math.sqrt(sum(c * c for c in load)), total, 1e-300):
                loose_parts.append({"parts": sorted({names[int(p)] for p in np.unique(node_part[node_body == b])}),
                                    "pressing": b in pressing_bodies, "unheld_N": unheld / share})
        stats = self._contact_stats(contacts, constraints, owner, final_response, final_pressure, points, share,
                                    float(np.linalg.norm(space.nodal(final.u + shift), axis=1).max()))
        internal, _ = problem.evaluate(final.u, tangent=False) if path.records else (np.zeros(problem.size), None)
        residual = internal - final.factor * external
        reactions = [tuple(float(residual[dofs][space.component[dofs] == c].sum()) for c in range(3)) for dofs in fixture_dofs]
        applied = tuple(float(final.factor * external[space.component == c].sum()) for c in range(3))
        requested = tuple(float(external[space.component == c].sum()) for c in range(3))
        vm_gauss = float(history[-1][0].max())
        dof_locations, boundary, tets, element_dofs, vertices = (space.dof_locations, space.boundary_quadratic, space.tets,
                                                                  space.element_dofs, space.vertices)
        if planes:
            from cadgen._internal.fea import symmetry

            volume = ctx.volume
            for plane in reversed(planes):
                whole, keep = symmetry.unfold_volume(volume, plane)
                scalars = {f"vm{i}": values for i, values in enumerate(stress_frames)}
                scalars.update({f"cp{i}": values for i, values in enumerate(pressure_frames)})
                vectors = {f"u{i}": values for i, values in enumerate(displacement_frames)}
                dof_locations, scalars, vectors, boundary, tets, element_dofs, vertices = symmetry.unfold_fields(
                    plane, vertices, dof_locations, keep, scalars=scalars, vectors=vectors, boundary=boundary, tets=tets,
                    element_dofs=element_dofs,
                )
                stress_frames = [scalars[f"vm{i}"] for i in range(len(stress_frames))]
                pressure_frames = [scalars[f"cp{i}"] for i in range(len(pressure_frames))]
                displacement_frames = [vectors[f"u{i}"] for i in range(len(displacement_frames))]
                reactions = [symmetry.unfold_force(plane, r) for r in reactions]
                applied = symmetry.unfold_force(plane, applied)
                requested = symmetry.unfold_force(plane, requested)
                volume = whole
            ctx.volume = volume
        timings["stress_s"] = time.perf_counter() - started

        factors = [records[i].factor for i in picked]
        attributes = {"von_mises": "_VON_MISES", "displacement": "_DISPLACEMENT", "contact_pressure": "_CONTACT_PRESSURE"}
        unsettled = unsettled_steps(path)
        series = Series(kind="time", unit="%", default=len(picked) - 1, frames=[
            SeriesFrame(value=round(records[i].factor * 100.0, 6),
                        label=load_label(records[i].factor) + (" · did not settle" if i in loose_steps else ""),
                        attributes={name: attribute if n == 0 else f"{attribute}_F{n}" for name, attribute in attributes.items()})
            for n, i in enumerate(picked)
        ])
        frame_fields = {"von_mises": stress_frames, "displacement": displacement_frames, "contact_pressure": pressure_frames}
        fields = {name: values[0] for name, values in frame_fields.items()}
        final_fields = {name: values[-1] for name, values in frame_fields.items()}
        curve_x = [round(record.factor * 100.0, 6) for record in path.records]
        curves = {
            "max_displacement_mm": {"x": curve_x, "x_unit": "%", "y_unit": "mm",
                                    "y": [round(float(np.linalg.norm(space.nodal(r.u + shift), axis=1).max()), 6) for r in path.records]},
            "contact_force_N": {"x": curve_x, "x_unit": "%", "y_unit": "N",
                                "y": [round(float(h[1].normal_force.sum()) / share, 6) for h in history[:len(path.records)]]},
        }
        how = f"{path.how}, {len(path.records)} {'adaptive ' if adaptive else ''}load steps, {problem.augmentations} contact updates"
        peak_node = int(final_fields["contact_pressure"].argmax())
        return AnalysisResult(
            dof_locations=dof_locations, vertices=vertices, tets=tets, boundary_quadratic=boundary, element_dofs=element_dofs,
            fields=fields, deformation=displacement_frames[0], series=series, frame_fields=frame_fields, curves=curves,
            reactions=reactions, applied=applied, dofs=int(basis.N), solver=how, timings=timings, warnings=warnings,
            scalars={
                "path": path, "final": final_fields, "factor": path.factor if path.records else 0.0, "collapsed": path.collapsed,
                "requested": requested, "model": "elastic", "adaptive": adaptive, "von_mises_gauss_max": vm_gauss,
                "frame_factors": factors, "contacts": stats, "augmentations": problem.augmentations,
                "contact_nodes": constraints.count, "floating_bodies": len(floating), "loose_parts": loose_parts,
                "peak_pressure_at": [round(float(c), 3) for c in dof_locations[peak_node]],
                "analysis_warnings": ([stop_words(path.factor)] if path.collapsed else [])
                + [unsettled_sentence(step["percent"], step["of"]) for step in unsettled[:1]],
                "unsettled": unsettled,
                "analysis_extras": {"unsettled": unsettled_extras(unsettled)} if unsettled else {},
                "part_refs": None if ctx.assembly is None else [part.ref for part in ctx.assembly.parts],
                "part_names": names, "part_materials": part_materials(ctx),
            },
        )

    def _contact_stats(self, contacts, constraints, owner, response, pressure, points, share: float,
                       moved: float) -> list[dict]:
        """Each contact at the last load carried: force, area, peak pressure and where, sliding, slipping."""
        import numpy as np

        stats = []
        for k, contact in enumerate(contacts):
            mine = owner == k
            p = response.normal_force[mine]
            pressing = p > 0
            slaves = constraints.node[mine][pressing]
            entry = {key: contact[key] for key in ("kind", "name", "words", "friction", "between", "refs", "normal") if key in contact}
            entry.update({"nodes": int(mine.sum()), "touching": bool(pressing.any()),
                          "force_N": float(p.sum()) / share, "area_mm2": float(constraints.area[mine][pressing].sum()) / share,
                          "friction_N": float(np.linalg.norm(response.tangential[mine].sum(axis=0))) / share})
            if pressing.any():
                values = pressure[slaves]
                peak = int(values.argmax())
                slide = np.linalg.norm(response.sliding[mine][pressing], axis=1)
                entry.update({
                    "peak_MPa": float(values[peak]), "peak_at": [float(c) for c in points[slaves[peak]]],
                    "max_slide_mm": float(slide.max()),
                    "slides": bool(slide.max() > SLIDE_SHARE * max(moved, 1e-12)),
                    "slipping_share": float(response.slipping[mine][pressing].mean()) if contact["friction"] else None,
                })
            else:
                entry.update({"peak_MPa": 0.0, "peak_at": None, "max_slide_mm": 0.0, "slides": False, "slipping_share": None})
            stats.append(entry)
        return stats

    # -- judging -------------------------------------------------------------------------------------

    def judge(self, check: dict, index: int, ctx: SolveContext, result: AnalysisResult, inputs: ContactInputs) -> dict:
        from cadgen._internal.fea import checks

        if check["kind"] != "contact_pressure":
            return mark_unsettled(super().judge(check, index, ctx, result, inputs), result.scalars)
        common = dict(boundary=result.boundary_quadratic, boundary_ordinal=ctx.volume.boundary_ordinal,
                      locations=result.dof_locations, face_ref=ctx.volume.faces, ordinal_of=ctx.ordinal_of,
                      where=f"view.checks[{index}]")
        peak = kinds.field_max_over(result.scalars["final"]["contact_pressure"], tuple(check.get("faces", ())), **common)
        limit = float(check["limit_MPa"])
        ratio = peak.value / limit
        judged = {
            "kind": "contact_pressure", "label": check.get("label") or kinds.CONTACT_PRESSURE.default_label,
            "value": round(peak.value, 6), "limit": limit, "unit": "MPa", "ratio": round(ratio, 6), "close_at": 0.9,
            "status": checks.check_status(ratio, 0.9), "where": {"ref": peak.ref, "at": [round(c, 3) for c in peak.at]},
        }
        if check.get("faces"):
            judged["faces"] = list(peak.faces)
        judged["at"] = self._at(result)
        judged["scaling"] = "none"  # contact opens, closes and slides: not linear in the load
        if result.scalars["collapsed"]:
            judged["status"] = "fails"
            judged["collapsed_at_percent"] = round(result.scalars["factor"] * 100.0, 4)
        return mark_unsettled(judged, result.scalars)

    def findings(self, ctx: SolveContext, result: AnalysisResult, inputs: ContactInputs,
                 check_results: list[dict], *, assembly: bool) -> list[dict]:
        scalars = result.scalars
        path = scalars["path"]
        found: list[dict] = []

        def finding(severity, kind, summary, description, items=()):
            return {"check": "fea", "severity": severity, "type": kind, "summary": summary, "description": description,
                    "items": list(items)}

        for step in (scalars.get("unsettled") or [])[:1]:
            others = len(scalars["unsettled"]) - 1
            found.append(finding(
                "error", "contact_unsettled", unsettled_sentence(step["percent"], step["of"]),
                "the contact forces kept changing there even at the smallest load step, and the last re-solve found no "
                "equilibrium, so the parts' forces do not add up; every check fails until it settles"
                + (f" ({others} more step{'s' if others > 1 else ''} did not settle either)" if others else "")
                + ": try more load steps, a finer mesh where the parts touch, or friction 0 to see whether it is the sliding",
            ))
        if scalars["collapsed"]:
            found.append(finding(
                "error", "contact_stops",
                f"The contact could not be followed past about {scalars['factor'] * 100:.0f} % of the load",
                f"past {scalars['factor'] * 100:.4g} % of the load Newton's method finds no equilibrium, even in steps of "
                f"{path.smallest_step * 100:.3g} %: a part may be sliding or lifting off with nothing to stop it; the last "
                "frame is the last load solved",
            ))
        for loose in scalars["loose_parts"]:
            who = " and ".join(f"'{part}'" for part in loose["parts"])
            if not loose["pressing"]:
                found.append(finding(
                    "error", "comes_loose",
                    f"{who} comes loose: it rests only on contacts, and under this load it lifts off every one of them",
                    "nothing holds it once its contacts open, so its displacement is only how far its weak drift spring "
                    "lets it go and says nothing; hold it with a fixture, or load it towards what it rests on",
                ))
            else:
                found.append(finding(
                    "error", "slides_away",
                    f"{who} slides away: its contacts cannot hold {loose['unheld_N']:.3g} N of its load sideways",
                    "it rests only on contacts, and friction (or none) holds less than the sideways load, so nothing stops "
                    "it sliding; its displacement is only how far its weak drift spring lets it go and says nothing",
                ))
        for contact in scalars["contacts"]:
            name = contact["name"]
            if not contact["touching"]:
                found.append(finding(
                    "warning", "contact_separates",
                    f"{name[0].upper()}{name[1:]}: they separate under this load and no longer touch"
                    if contact["kind"] == "pair" else f"Nothing presses on {name}: the part lifts off it",
                    "no point of the contact carries a force at the last load, so it passes no load (a contact never pulls)",
                ))
                continue
            at = [round(c, 3) for c in contact["peak_at"]]
            found.append(finding(
                "info", "contact_presses",
                f"{contact['words'].split(',')[0]}: {contact['force_N']:.4g} N over {contact['area_mm2']:.3g} mm², "
                f"peak contact pressure {contact['peak_MPa']:.4g} MPa",
                f"the contact carries {contact['force_N']:.6g} N at the last load; its pressure peaks at {at}",
                [{"text": "peak contact pressure", "ref": None, "at": at}],
            ))
            if contact["friction"]:
                share = contact["slipping_share"] or 0.0
                if share > 0:
                    found.append(finding(
                        "info", "contact_slides",
                        f"{name[0].upper()}{name[1:]} slides over {share * 100:.0f} % of the contact (friction {contact['friction']:g}), "
                        f"up to {contact['max_slide_mm']:.3g} mm",
                        "where the sideways force reaches friction times the pressure the surfaces slip; elsewhere they stick",
                    ))
                else:
                    found.append(finding("info", "contact_sticks",
                                         f"{name[0].upper()}{name[1:]} sticks: friction {contact['friction']:g} holds it from sliding",
                                         "the sideways force stays under friction times the pressure everywhere in the contact"))
            elif contact["slides"]:
                found.append(finding(
                    "info", "contact_slides",
                    f"{name[0].upper()}{name[1:]} slides freely (no friction), up to {contact['max_slide_mm']:.3g} mm",
                    "with no friction nothing holds the surfaces from sliding along each other",
                ))
        touching = [c for c in scalars["contacts"] if c["touching"]]
        if touching:
            top = max(touching, key=lambda c: c["peak_MPa"])
            at = [round(c, 3) for c in top["peak_at"]]
            found.append(finding(
                "info", "peak_contact_pressure",
                f"The contact pressure peaks at {top['peak_MPa']:.4g} MPa where {top['name']} touch" if top["kind"] == "pair"
                else f"The contact pressure peaks at {top['peak_MPa']:.4g} MPa on {top['name']}",
                f"at {at}, at the last load carried",
                [{"text": "peak contact pressure", "ref": None, "at": at}],
            ))
        if path.cuts and not scalars["collapsed"]:
            found.append(finding(
                "info", "load_steps_cut",
                f"Cut the load steps down to {path.smallest_step * 100:.3g} % to get through where the contacts open, close or slip",
                f"{path.cuts} steps did not converge at first and were halved"))
        return sorted(found, key=lambda item: {"error": 0, "warning": 1, "info": 2}[item["severity"]])

    # -- what is written -----------------------------------------------------------------------------

    def summary(self, result: AnalysisResult, inputs: ContactInputs, check_results: list[dict]) -> dict:
        import numpy as np

        scalars = result.scalars
        path = scalars["path"]
        final = scalars["final"]
        moved = np.linalg.norm(final["displacement"], axis=1)
        peak = int(final["von_mises"].argmax())
        node_moved = int(moved.argmax())
        factor = scalars["factor"]
        pressure = final["contact_pressure"]

        def rounded(contact: dict) -> dict:
            out = {}
            for key, value in contact.items():
                if isinstance(value, float):
                    out[key] = round(value, 6)
                elif key == "peak_at" and value is not None:
                    out[key] = [round(c, 3) for c in value]
                else:
                    out[key] = value
            return out

        unsettled = scalars.get("unsettled") or []
        status = stop_words(factor) if scalars["collapsed"] else "Carries the full load"
        if unsettled:
            status = f"Not reliable: contact did not settle at {unsettled[0]['percent']:.0f}% of {unsettled[0]['of']}"
        summary: dict[str, Any] = {
            "status": status,
            "collapsed": scalars["collapsed"],
            "unsettled_at_percent": [step["percent"] for step in unsettled],
            "load_percent": round(factor * 100.0, 4),
            "max_von_mises_MPa": round(float(final["von_mises"][peak]), 4),
            "max_von_mises_gauss_MPa": round(scalars["von_mises_gauss_max"], 4),
            "max_von_mises_at_mm": [round(float(c), 3) for c in result.dof_locations[peak]],
            "max_displacement_mm": round(float(moved[node_moved]), 6),
            "max_displacement_at_mm": [round(float(c), 3) for c in result.dof_locations[node_moved]],
            "max_contact_pressure_MPa": round(float(pressure.max()), 4),
            "max_contact_pressure_at_mm": scalars["peak_pressure_at"] if float(pressure.max()) > 0 else None,
            "contacts": [rounded(c) for c in scalars["contacts"]],
            "yield_MPa": scalars.get("yield_MPa"),
            "applied_force_N": [round(x, 4) for x in result.applied],
            "requested_force_N": [round(x, 4) for x in scalars["requested"]],
            "reaction_force_N": [round(sum(r[c] for r in result.reactions), 4) for c in range(3)],
            "steps_requested": inputs.steps,
            "steps": len(path.records),
            "step_cuts": path.cuts,
            "smallest_step_percent": round(path.smallest_step * 100.0, 6),
            "newton_iterations": path.iterations,
            "contact_updates": scalars["augmentations"],
            "contact_nodes": scalars["contact_nodes"],
            "adaptive": scalars["adaptive"],
            "frames": len(result.series.frames),
            "deformation_scale": scalars.get("deformation_scale"),
        }
        if scalars.get("part_refs"):
            summary["parts"] = with_materials([{"ref": ref, "name": name} for ref, name in zip(scalars["part_refs"], scalars["part_names"])],
                                              scalars)
        summary["checks"] = check_results
        return summary

    def extras_name(self, stem: str) -> str:
        return f"{stem} contact"

    def field_ranges(self, summary: dict, result: AnalysisResult) -> dict[str, tuple[float, float]]:
        import numpy as np

        frames = result.frame_fields
        return {
            "von_mises": (0.0, round(max(float(f.max()) for f in frames["von_mises"]), 4)),
            "displacement": (0.0, round(max(float(np.linalg.norm(f, axis=1).max()) for f in frames["displacement"]), 6)),
            "contact_pressure": (0.0, round(max(float(f.max()) for f in frames["contact_pressure"]), 4)),
        }

    def extras_head(self, summary: dict) -> dict:
        head = {"load_percent": summary["load_percent"], "collapsed": summary["collapsed"], "contacts": summary["contacts"]}
        if summary.get("unsettled_at_percent"):
            head["unsettled_at_percent"] = summary["unsettled_at_percent"]
        return head

    def study_echo(self, inputs: ContactInputs, bare: Callable[[tuple[str, ...]], list[str]]) -> dict:
        from cadgen._internal.fea.analyses.static import StaticAnalysis

        return {
            **StaticAnalysis().study_echo(inputs, bare), "steps": inputs.steps,
            "contact_pairs": [{"between": list(pair.between), "friction": pair.friction} for pair in inputs.pairs],
            "rigid_planes": [{"point_mm": list(plane.point), "normal": list(plane.normal), "parts": list(plane.parts),
                              "friction": plane.friction} for plane in inputs.planes],
        }

    def human_lines(self, summary: dict) -> list[str]:
        head = summary["status"].lower() if summary["collapsed"] or summary.get("unsettled_at_percent") else "carries the full load"
        lines = [f"{head}: max von Mises {summary['max_von_mises_MPa']:g} MPa, max displacement "
                 f"{summary['max_displacement_mm']:g} mm, peak contact pressure {summary['max_contact_pressure_MPa']:g} MPa"]
        for contact in summary["contacts"]:
            if contact["touching"]:
                lines.append(f"{contact['name']}: presses with {contact['force_N']:g} N over {contact['area_mm2']:g} mm², "
                             f"peak {contact['peak_MPa']:g} MPa")
            else:
                lines.append(f"{contact['name']}: no longer touching")
        lines.append(f"followed in {summary['steps']} {'adaptive ' if summary['adaptive'] else ''}load steps "
                     f"({summary['newton_iterations']} Newton iterations, {summary['contact_updates']} contact updates"
                     + (f", {summary['step_cuts']} cut, smallest {summary['smallest_step_percent']:g} %" if summary["step_cuts"] else "")
                     + ")")
        return lines


def stop_words(factor: float) -> str:
    """"Stops at about 70 % of the load": where the contact could not be followed further."""
    percent = factor * 100.0
    if percent < 1.0:
        return "Stops before 1 % of the load"
    return f"Stops at about {percent:.0f} % of the load"
