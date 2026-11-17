"""``fit`` and ``bake``: exact parts held to a GSL concept's field, with no mesh of the concept.

Both read the exact parts as triangles (a GLB: ``cad gsl fit`` and ``cad gsl bake`` mesh a document id, an
``.xbf`` or a ``.step`` into one first, at ``chord``) and sample their surfaces by area, every vertex and about
``density`` points a square millimetre more, each point labelled by its part. The concept is never meshed: omega's
evaluator scores the points (``omega_core.Session``), and the concept is written in the exact parts' frame.

- ``fit`` asks whether exact parts fit around a concept part: each part's clearance (the least field over its
  surface), the points where it runs into the concept's material, and the contacts the design means
  (``contact``: the exact surface near a point lies on the concept's).
- ``bake`` holds an exact part to the concept it was baked from, both ways: the field over the exact surface
  (signed: below zero the concept carries material the exact part does not), and the distance from points on the
  concept's surface (omega's ``surface``) to the exact triangles. It keeps a copy of the concept as baked beside it
  (``<stem>.baked.gsl``, with the values given), and ``stale`` holds the concept as it is now to that copy on the
  exact surface: where the field moved, by how much, on which part.

Neither judges the concept's own features where no exact part comes near them: a picture of the field does.
"""

from __future__ import annotations

import contextvars
import json
import math
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cad.results import CheckResult

__all__ = ["CHORD_MM", "DENSITY", "TOLERANCE_MM", "as_glb", "bake", "fit", "record_path", "sample"]

#: The chord tolerance (mm) a document is meshed at to be sampled: a curved face's triangles lie within it.
CHORD_MM = 0.01
#: Points a square millimetre of exact surface, besides every vertex: about 0.5 mm apart.
DENSITY = 4.0
#: Below this (mm), a field value is the concept's surface: a contact, no interference, no change.
TOLERANCE_MM = 0.01
#: How far from a contact's point (mm) the exact surface is looked for.
CONTACT_RADIUS_MM = 3.0
#: Points one evaluator request carries.
_BATCH = 200_000
#: Seeds over the concept's box, at most, that the reverse direction projects onto its surface.
_SEEDS = 60_000
_RECORD_SUFFIX = ".baked.gsl"
_DEFS_LINE = "// cad-gsl-bake-defs: "


@dataclass
class Sampled:
    """Points on exact parts' surfaces (``points`` (N, 3) mm), each one's part (``part`` (N,), an index into
    ``names``), and the triangles they were drawn from, placed (``triangles`` (T, 3, 3) mm)."""

    points: Any
    part: Any
    names: list[str]
    triangles: Any
    matrices: Any = None  # each named part's placement (4, 4), by its index in ``names``
    owners: Any = None  # each triangle's part, an index into ``names``


def as_glb(exact: Any, folder: Path, chord: float = CHORD_MM) -> Path:
    """``exact`` as a GLB to sample: a ``.glb`` as it is; a document id, an ``.xbf``, a ``.step``, an ``.stl`` or a
    ``.3mf`` meshed into ``folder`` at ``chord`` by the engine's export."""
    from cad.engine.ids import is_id

    text = str(exact)
    if not is_id(text) and Path(text).suffix.lower() == ".glb":
        return Path(text).expanduser().resolve()
    from cad.engine.api import export

    out = Path(folder) / "exact.glb"
    export(text if is_id(text) else str(Path(text).expanduser().resolve()), out, tolerance=chord, progress=False)
    return out


def sample(glb: Path, density: float = DENSITY, seed: int = 0) -> Sampled:
    """Points on each placed part of ``glb``: its vertices, and ``density`` a square millimetre more drawn
    uniformly over its triangles (the same points for the same file). A part placed twice is sampled twice, its
    names numbered (``screw``, ``screw#2``)."""
    import numpy as np

    from cad.engine.formats.gltf import read_gltf

    read = read_gltf(Path(glb))
    rng = np.random.default_rng(seed)
    points, owners, names, placed_triangles, matrices, triangle_owners = [], [], [], [], [], []
    seen: dict[str, int] = {}
    for index, matrix, name in read.placed:
        part = read.parts[index]
        if not len(part.triangles):
            continue
        seen[name] = seen.get(name, 0) + 1
        label = name if seen[name] == 1 else f"{name}#{seen[name]}"
        world = part.points @ matrix[:3, :3].T + matrix[:3, 3]
        tri = world[part.triangles]
        area = 0.5 * np.linalg.norm(np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]), axis=1)
        count = np.floor(area * density + rng.random(len(area))).astype(np.int64)
        which = np.repeat(np.arange(len(tri)), count)
        r1, r2 = rng.random(len(which)), rng.random(len(which))
        flip = r1 + r2 > 1.0
        r1[flip], r2[flip] = 1.0 - r1[flip], 1.0 - r2[flip]
        chosen = tri[which]
        drawn = chosen[:, 0] + r1[:, None] * (chosen[:, 1] - chosen[:, 0]) + r2[:, None] * (chosen[:, 2] - chosen[:, 0])
        mine = np.concatenate([world, drawn])
        points.append(mine)
        owners.append(np.full(len(mine), len(names), np.int64))
        triangle_owners.append(np.full(len(tri), len(names), np.int64))
        names.append(label)
        matrices.append(np.asarray(matrix, float))
        placed_triangles.append(tri)
    if not points:
        return Sampled(np.zeros((0, 3)), np.zeros(0, np.int64), [], np.zeros((0, 3, 3)))
    return Sampled(np.concatenate(points), np.concatenate(owners), names, np.concatenate(placed_triangles), matrices,
                   np.concatenate(triangle_owners))


def _union(session: Any, code: str, defs: str) -> str:
    """The concept's shape as one expression, the union of its returns (``min(a, b)``), named outright: omega-core
    0.1.1's ``eval`` defaults to none, and ``surface`` and ``bounds`` take one expression."""
    request: dict[str, Any] = {"op": "describe", "code": code}
    if defs:
        request["defs"] = defs
    returns = list(session.request(request)["returns"])
    if not returns:
        raise ValueError("the concept returns no shape")
    return returns[0] if len(returns) == 1 else f"min({', '.join(returns)})"


def _field(session: Any, text: str, points: Any, defs: str) -> Any:
    """The concept's field at ``points``: the union (least) of its returns."""
    import numpy as np

    from cad.omega._check import queryable

    out = np.empty(len(points))
    code = queryable(text)
    shape = _union(session, code, defs)
    for start in range(0, len(points), _BATCH):
        chunk = points[start:start + _BATCH]
        request: dict[str, Any] = {"op": "eval", "code": code, "exprs": [shape], "points": chunk.tolist()}
        if defs:
            request["defs"] = defs
        out[start:start + len(chunk)] = np.asarray(session.request(request)["groups"][0]["values"][0], np.float64)
    return out


def _point(text: str) -> tuple[float, float, float]:
    parts = [part.strip() for part in text.split(",")]
    values = [float(part) for part in parts] if len(parts) == 3 else []
    if len(values) != 3 or not all(math.isfinite(value) for value in values):
        raise ValueError(f"a point is x,y,z in mm (31.5,21.5,0), not {text!r}")
    return values[0], values[1], values[2]


def _at(point: Any) -> list[float]:
    return [round(float(c), 3) for c in point]


def _opening(path: Path, exact: Any, define: tuple[str, ...], verbose: bool, label: str):
    """What both operations check first: the concept is a ``.gsl`` file, the values parse, ``gsl`` is found.
    ``(target, where, defs, gsl, failed result or None)``."""
    import importlib.util

    from cad._internal.validation_door import display_path, failed, resolved_target
    from cad.omega._check import SUFFIXES
    from cad.omega._mesh import statements
    from cad.omega._program import EXTRA, OmegaMissingError, find_gsl

    target = resolved_target(path, label="omega")
    if verbose:
        print(f"[omega] {label} {exact} against {target}", file=sys.stderr)
    if target.suffix.lower() not in SUFFIXES:
        return target, "", "", None, failed(target, f"target must be a {' or '.join(SUFFIXES)} file")
    if not target.is_file():
        return target, "", "", None, failed(target, "file not found")
    try:
        defs = statements(tuple(define))
    except ValueError as error:
        return target, "", "", None, failed(target, str(error), code="bad_define")
    if importlib.util.find_spec("omega_core") is None:
        raise ModuleNotFoundError(f"omega_core comes with cad's omega integration: install {EXTRA}, or run the script "
                                  f"with cad run (add `{EXTRA}` to its header)", name="omega_core")
    try:
        gsl = find_gsl()
    except OmegaMissingError as error:
        return target, "", "", None, failed(target, str(error), code="program_missing")
    return target, display_path(target), defs, gsl, None


def _sampled(exact: Any, scratch: Path, chord: float, density: float, findings: Any, where: str) -> Sampled | None:
    from cad.engine.formats.gltf import GltfError

    try:
        glb = as_glb(exact, scratch, chord)
        sampled = sample(glb, density)
    except (GltfError, OSError, ValueError, RuntimeError) as error:
        findings.add("error", "exact_unread", f"the exact parts were not read from {exact}: {error}", path=where)
        return None
    if not len(sampled.points):
        findings.add("error", "exact_empty", f"{exact} holds no triangles to sample", path=where)
        return None
    placed = _PLACED.get()
    if placed is not None:
        sampled = _in_frame(sampled, placed)
        if sampled is None:
            findings.add("error", "exact_empty", f"{exact} holds no triangles of {placed['only']['part']}", path=where)
    return sampled


# How an assembly places the concept being checked (``assembly``): ``{"frame": its placement (4, 4), "only": the
# one exact part to hold to it, {"part", "matrix"}, or None for every part}``. The concept is written in its own
# part's frame, so the exact surface is taken into that frame, where every place said is.
_PLACED: "contextvars.ContextVar[dict | None]" = contextvars.ContextVar("cad_omega_placed", default=None)


def _in_frame(sampled: Sampled, placed: dict) -> Sampled | None:
    import numpy as np

    keep = np.ones(len(sampled.names), bool)
    only = placed.get("only")
    if only is not None:
        # The part by its name; among several of one name, the one placed where the document places it.
        stem = [index for index, name in enumerate(sampled.names) if name.partition("#")[0] == only["part"]]
        if not stem:
            return None
        at = np.asarray(only["matrix"], float)[:3, 3]
        chosen = min(stem, key=lambda index: float(np.linalg.norm(sampled.matrices[index][:3, 3] - at)))
        keep[:] = False
        keep[chosen] = True
    inverse = np.linalg.inv(np.asarray(placed["frame"], float))
    points = sampled.points[keep[sampled.part]] @ inverse[:3, :3].T + inverse[:3, 3]
    triangles = sampled.triangles[keep[sampled.owners]] @ inverse[:3, :3].T + inverse[:3, 3]
    renumbered = np.cumsum(keep) - 1
    return Sampled(points, renumbered[sampled.part[keep[sampled.part]]],
                   [name for name, kept in zip(sampled.names, keep) if kept], triangles,
                   [matrix for matrix, kept in zip(sampled.matrices, keep) if kept],
                   renumbered[sampled.owners[keep[sampled.owners]]])


PLAN = "concepts.json"


def as_plan(document: Any, folder: Path, chord: float = CHORD_MM) -> Path:
    """An assembly that names its concepts (``cad.gsl.concept``, ``cad.gsl.baked``) as what ``assembly`` reads,
    made where the engine is: its exact parts as a GLB in ``folder`` and, beside it, ``concepts.json``, each
    placed part that names a concept with its ``.gsl``, its role, its values and where it stands. ``document``
    is a document id or an ``.xbf`` (a STEP holds no declaration); a plan already made is given back."""
    import json

    from cad.engine.api import export
    from cad.engine.document import Loaded
    from cad.engine.ids import is_id

    text, folder = str(document), Path(folder)
    if not is_id(text) and Path(text).name == PLAN:
        return Path(text).expanduser().resolve()
    if is_id(text):
        held = folder / "exact.xbf"
        export(text, held, progress=False)
    elif Path(text).suffix.lower() == ".xbf":
        held = Path(text).expanduser().resolve()
    else:
        raise ValueError(f"an assembly that names its concepts is a document id or an .xbf, not {Path(text).name}")
    glb = as_glb(text, folder, chord)
    structure = Loaded(held).structure()
    concepts = []
    for instance in structure["instances"]:
        prototype = structure["prototypes"][instance["prototype"]]
        concept = prototype.get("concept")
        if concept:
            concepts.append({"part": prototype.get("name") or instance["path"], "path": instance["path"],
                             "gsl": concept["gsl"], "role": concept["role"], "values": concept.get("values") or {},
                             "matrix": [float(value) for value in instance["matrix"]]})
    plan = folder / PLAN
    plan.write_text(json.dumps({"document": text, "exact": str(glb), "concepts": concepts}, indent=1), encoding="utf-8")
    return plan


def assembly(operation: str, document: Any, *, contact: tuple[str, ...] = (), define: tuple[str, ...] = (),
             strict: bool = False, **options: Any) -> CheckResult:
    """``fit`` or ``bake`` over an assembly that names its concepts: ``fit`` holds every exact part to each part
    that is a concept (``cad.gsl.concept``); ``bake`` holds each part baked from one (``cad.gsl.baked``) to it,
    alone. Each concept is taken where the document places it, with the values it was given there."""
    import json
    import tempfile

    import numpy as np

    from cad._internal.validation_door import failed

    with tempfile.TemporaryDirectory(prefix="cad-omega-assembly-", ignore_cleanup_errors=True) as scratch:
        try:
            plan = as_plan(document, Path(scratch), options.get("chord", CHORD_MM))
            read = json.loads(plan.read_text(encoding="utf-8"))
        except (OSError, ValueError, RuntimeError) as error:
            return failed(Path(str(document)), f"the assembly's concepts were not read: {error}", code="exact_unread")
        shown = Path(read["document"])
        if contact or define:
            return failed(shown, "an assembly names its concepts' values where it places them: give no "
                          f"{'--contact' if contact else '--define'} with it, or name one concept and the exact parts",
                          code="bad_define")
        role = "body" if operation == "fit" else "baked"
        wanted = [concept for concept in read["concepts"] if concept["role"] == role]
        if not wanted:
            said = ("no part that is a concept (cad.gsl.concept)" if role == "body"
                    else "no part baked from a concept (cad.gsl.baked)")
            return failed(shown, f"{read['document']} holds {said}", code="no_concepts")
        run = fit if operation == "fit" else bake
        results = []
        for concept in wanted:
            frame = np.asarray(concept["matrix"], float).reshape(4, 4).T
            only = {"part": concept["part"], "matrix": frame} if role == "baked" else None
            token = _PLACED.set({"frame": frame, "only": only})
            try:
                results.append((concept, run(Path(concept["gsl"]), read["exact"], strict=strict,
                                             define=tuple(f"{name}={value:g}" for name, value in concept["values"].items()),
                                             **options)))
            finally:
                _PLACED.reset(token)
    ok = all(result.ok for _concept, result in results)
    findings = tuple(finding for _concept, result in results for finding in result.findings)
    summary = "\n".join(result.summary for _concept, result in results if result.summary) if ok else ""
    return CheckResult(ok=ok, path=results[0][1].path, findings=findings, summary=summary,
                       measurements={"concepts": [{"part": concept["part"], "gsl": concept["gsl"], "role": concept["role"],
                                                   **result.measurements} for concept, result in results]})


def _result(target: Path, findings: Any, strict: bool, summary: str, measurements: dict) -> CheckResult:
    from cad._internal.validation_door import blocks, result_from_findings

    done = result_from_findings(target, findings.deduplicated(), strict=strict,
                                summary=summary if not blocks(findings, strict=strict) else "")
    return CheckResult(ok=done.ok, path=done.path, findings=done.findings, summary=done.summary,
                       measurements=measurements)


def fit(path: Path, exact: Any, *, contact: tuple[str, ...] = (), define: tuple[str, ...] = (),
        tolerance: float = TOLERANCE_MM, contact_radius: float = CONTACT_RADIUS_MM, density: float = DENSITY,
        chord: float = CHORD_MM, strict: bool = False, verbose: bool = False) -> CheckResult:
    import tempfile

    import numpy as np
    import omega_core

    from cad._internal.findings import FindingsReport

    target, where, defs, gsl, refused = _opening(path, exact, define, verbose, "fitting")
    if refused is not None:
        return refused
    findings = FindingsReport()
    try:
        contacts = [_point(given) for given in contact]
    except ValueError as error:
        findings.add("error", "bad_contact", str(error), path=where)
        return _result(target, findings, strict, "", {})
    measurements: dict[str, Any] = {}
    with tempfile.TemporaryDirectory(prefix="cad-omega-fit-", ignore_cleanup_errors=True) as scratch:
        sampled = _sampled(exact, Path(scratch), chord, density, findings, where)
        if sampled is None:
            return _result(target, findings, strict, "", {})
        try:
            with omega_core.Session(source_paths=(target.parent,), program=str(gsl)) as session:
                values = _field(session, target.read_text(encoding="utf-8"), sampled.points, defs)
        except omega_core.EvalError as error:
            findings.add("error", "eval_failed", f"omega's evaluator did not score the points: {error}", path=where)
            return _result(target, findings, strict, "", {})

    rows = []
    for index, name in enumerate(sampled.names):
        mine = sampled.part == index
        value, pts = values[mine], sampled.points[mine]
        least = int(np.argmin(value))
        inside = value < -tolerance
        row = {"part": name, "points": int(mine.sum()), "clearance_mm": round(float(value[least]), 4),
               "at": _at(pts[least]), "in_wall": int(inside.sum())}
        rows.append(row)
        if inside.any():
            findings.add("error", "interference", f"{name} runs {-float(value[least]):.3g} mm into the concept's "
                         f"material at {_at(pts[least])} ({int(inside.sum())} of its {int(mine.sum())} surface "
                         "points are in it)", path=where,
                         hint="move the part or the concept's wall, or make room in the concept there")
    touched = []
    for point in contacts:
        near = np.linalg.norm(sampled.points - np.asarray(point), axis=1) <= contact_radius
        if not near.any():
            findings.add("error", "contact_off_part", f"no exact surface lies within {contact_radius:g} mm of the "
                         f"contact {_at(point)}", path=where, hint="give a point on the exact part's surface where "
                                                                    "it should touch the concept")
            touched.append({"at": _at(point), "gap_mm": None})
            continue
        gaps = np.abs(values[near])
        best = int(np.argmin(gaps))
        gap = float(values[near][best])
        owner = sampled.names[int(sampled.part[near][best])]
        touched.append({"at": _at(point), "gap_mm": round(gap, 4), "part": owner})
        if abs(gap) > tolerance:
            findings.add("error", "no_contact", f"{owner} does not touch the concept near {_at(point)}: the nearest "
                         f"of its surface is {gap:.3g} mm from the concept's", path=where,
                         hint="move the concept's face (or the part) onto the other")
    closest = min(rows, key=lambda row: row["clearance_mm"])
    measurements = {"parts": rows, "contacts": touched, "points": int(len(sampled.points)),
                    "tolerance_mm": tolerance, "chord_mm": chord}
    summary = (f"OK {where}: {len(rows)} exact part{'s' if len(rows) != 1 else ''} clear of the concept, "
               f"the closest {closest['part']} at {closest['clearance_mm']:.3g} mm ({closest['at']})"
               + (f"; {len(touched)} contact{'s' if len(touched) != 1 else ''} touching" if touched else ""))
    return _result(target, findings, strict, summary, measurements)


def record_path(concept: Path) -> Path:
    """Where ``bake`` keeps the concept as baked: ``<stem>.baked.gsl`` beside it."""
    concept = Path(concept)
    return concept.with_name(concept.stem + _RECORD_SUFFIX)


def _record(concept: Path, text: str, defs: str, exact: Any) -> Path:
    from cad._internal.atomic_replace import replace_atomic

    out = record_path(concept)
    when = datetime.now(UTC).strftime("%Y-%m-%dT%H:%MZ")
    head = (f"// {concept.name} as it was baked into {exact}, {when}: kept by cad gsl bake, which holds the\n"
            f"// concept as it is now to this copy (--stale). Not a model to edit.\n"
            f"{_DEFS_LINE}{json.dumps(defs)}\n")
    temporary = out.with_name(out.name + ".tmp")
    temporary.write_text(head + text, encoding="utf-8")
    replace_atomic(temporary, out)
    return out


def _recorded(path: Path) -> tuple[str, str]:
    """A record's concept text and the values it was baked with."""
    text = path.read_text(encoding="utf-8")
    defs = ""
    for line in text.splitlines():
        if line.startswith(_DEFS_LINE):
            defs = json.loads(line[len(_DEFS_LINE):])
            break
    return text, defs


def _concept_surface(session: Any, text: str, defs: str, region: Any) -> Any:
    """Points on the concept's surface over ``region`` (``(low (3,), high (3,))``): a grid of seeds there, those
    near the surface moved onto it by omega's ``surface`` and kept where they converged."""
    import numpy as np

    from cad.omega._check import queryable

    low, high = region
    span = np.maximum(high - low, 1e-6)
    step = max(0.5, float(np.cbrt(np.prod(span) / _SEEDS)))
    axes = [np.arange(low[k], high[k] + step * 0.5, step) for k in range(3)]
    seeds = np.stack(np.meshgrid(*axes, indexing="ij"), axis=-1).reshape(-1, 3)
    values = _field(session, text, seeds, defs)
    seeds = seeds[np.abs(values) < 1.5 * step]
    found = []
    code = queryable(text)
    shape = _union(session, code, defs)
    for start in range(0, len(seeds), _BATCH):
        request: dict[str, Any] = {"op": "surface", "code": code, "expr": shape,
                                   "points": seeds[start:start + _BATCH].tolist(), "maxIters": 64, "tolerance": 1e-6}
        if defs:
            request["defs"] = defs
        for done in session.request(request)["samples"]:
            if done.get("converged") and abs(done.get("value") or 0.0) < 1e-3:
                found.append(done["point"])
    return np.asarray(found, np.float64).reshape(-1, 3)


def _closest(points: Any, a: Any, b: Any, c: Any) -> Any:
    """The point of each triangle ``a b c`` nearest each of ``points`` (row by row; Ericson's regions)."""
    import numpy as np

    ab, ac, ap = b - a, c - a, points - a
    d1, d2 = np.einsum("ij,ij->i", ab, ap), np.einsum("ij,ij->i", ac, ap)
    bp = points - b
    d3, d4 = np.einsum("ij,ij->i", ab, bp), np.einsum("ij,ij->i", ac, bp)
    cp = points - c
    d5, d6 = np.einsum("ij,ij->i", ab, cp), np.einsum("ij,ij->i", ac, cp)
    va, vb, vc = d3 * d6 - d5 * d4, d5 * d2 - d1 * d6, d1 * d4 - d3 * d2
    denom = va + vb + vc
    denom = np.where(np.abs(denom) < 1e-30, 1e-30, denom)
    v, w = vb / denom, vc / denom
    out = a + v[:, None] * ab + w[:, None] * ac  # inside the face
    edge_bc = (va <= 0) & (d4 - d3 >= 0) & (d5 - d6 >= 0)
    t = (d4 - d3) / np.where((d4 - d3) + (d5 - d6) == 0, 1e-30, (d4 - d3) + (d5 - d6))
    out = np.where(edge_bc[:, None], b + t[:, None] * (c - b), out)
    edge_ac = (vb <= 0) & (d2 >= 0) & (d6 <= 0)
    t = d2 / np.where(d2 - d6 == 0, 1e-30, d2 - d6)
    out = np.where(edge_ac[:, None], a + t[:, None] * ac, out)
    edge_ab = (vc <= 0) & (d1 >= 0) & (d3 <= 0)
    t = d1 / np.where(d1 - d3 == 0, 1e-30, d1 - d3)
    out = np.where(edge_ab[:, None], a + t[:, None] * ab, out)
    out = np.where(((d6 >= 0) & (d5 <= d6))[:, None], c, out)
    out = np.where(((d3 >= 0) & (d4 <= d3))[:, None], b, out)
    out = np.where(((d1 <= 0) & (d2 <= 0))[:, None], a, out)
    return out


def distance_to_triangles(points: Any, triangles: Any) -> Any:
    """Each point's distance (mm) to the nearest of ``triangles`` (T, 3, 3): the triangles binned on a grid,
    each point measured against the cells about its own, the ring widened until the nearest found is nearer
    than any cell outside it could be."""
    import numpy as np

    if not len(points):
        return np.zeros(0)
    lows, highs = triangles.min(axis=1), triangles.max(axis=1)
    size = max(float(np.median(np.max(highs - lows, axis=1))) * 2.0, 0.5)
    origin = lows.min(axis=0)
    cells: dict[tuple[int, int, int], list[int]] = {}
    first = np.floor((lows - origin) / size).astype(np.int64)
    last = np.floor((highs - origin) / size).astype(np.int64)
    for index in range(len(triangles)):
        for i in range(first[index, 0], last[index, 0] + 1):
            for j in range(first[index, 1], last[index, 1] + 1):
                for k in range(first[index, 2], last[index, 2] + 1):
                    cells.setdefault((i, j, k), []).append(index)
    home = np.floor((points - origin) / size).astype(np.int64)
    best = np.full(len(points), np.inf)
    groups: dict[tuple[int, int, int], list[int]] = {}
    for index, key in enumerate(map(tuple, home)):
        groups.setdefault(key, []).append(index)
    span = int(np.max(np.floor((highs.max(axis=0) - origin) / size)) + 2)
    for key, members in groups.items():
        rows = np.asarray(members)
        ring = 1
        while True:
            candidates = sorted({t for di in range(-ring, ring + 1) for dj in range(-ring, ring + 1)
                                 for dk in range(-ring, ring + 1)
                                 for t in cells.get((key[0] + di, key[1] + dj, key[2] + dk), ())})
            if candidates:
                tri = triangles[candidates]
                pts = points[rows]
                count, many = len(pts), len(tri)
                p = np.repeat(pts, many, axis=0)
                a, b, c = (np.tile(tri[:, n], (count, 1)) for n in range(3))
                d = np.linalg.norm(p - _closest(p, a, b, c), axis=1).reshape(count, many).min(axis=1)
                best[rows] = d
            # A triangle outside the ring is at least ring cells from the home cell's points.
            if (candidates and np.all(best[rows] <= ring * size)) or ring > span:
                break
            ring *= 2
    # A point the rings never proved (one far outside the triangles' grid) is measured against every triangle.
    unsure = np.flatnonzero(~np.isfinite(best) | (best > span * size))
    for start in range(0, len(unsure), 64):
        rows = unsure[start:start + 64]
        p = np.repeat(points[rows], len(triangles), axis=0)
        a, b, c = (np.tile(triangles[:, n], (len(rows), 1)) for n in range(3))
        best[rows] = np.linalg.norm(p - _closest(p, a, b, c), axis=1).reshape(len(rows), -1).min(axis=1)
    return best


def bake(path: Path, exact: Any, *, stale: bool = False, define: tuple[str, ...] = (),
         max_deviation: float = 0.0, tolerance: float = TOLERANCE_MM, density: float = DENSITY,
         chord: float = CHORD_MM, strict: bool = False, verbose: bool = False) -> CheckResult:
    import tempfile

    import numpy as np
    import omega_core

    from cad._internal.findings import FindingsReport
    from cad._internal.validation_door import display_path

    target, where, defs, gsl, refused = _opening(path, exact, define, verbose, "baking" if not stale else "staling")
    if refused is not None:
        return refused
    findings = FindingsReport()
    text = target.read_text(encoding="utf-8")
    kept = record_path(target)
    if stale and not kept.is_file():
        findings.add("error", "no_record", f"{target.name} has no record of a bake ({kept.name}): bake it first",
                     path=where, hint=f"cad gsl bake {target.name} <exact part>")
        return _result(target, findings, strict, "", {})
    with tempfile.TemporaryDirectory(prefix="cad-omega-bake-", ignore_cleanup_errors=True) as scratch:
        sampled = _sampled(exact, Path(scratch), chord, density, findings, where)
        if sampled is None:
            return _result(target, findings, strict, "", {})
        try:
            with omega_core.Session(source_paths=(target.parent,), program=str(gsl)) as session:
                now = _field(session, text, sampled.points, defs)
                if stale:
                    old_text, old_defs = _recorded(kept)
                    then = _field(session, old_text, sampled.points, old_defs)
                    surface = None
                else:
                    low = sampled.points.min(axis=0)
                    high = sampled.points.max(axis=0)
                    code = _queryable(text)
                    bounds = session.request({"op": "bounds", "code": code, "expr": _union(session, code, defs),
                                              **({"defs": defs} if defs else {})})
                    if bounds.get("found"):
                        low = np.minimum(low, np.asarray(bounds["bboxMin"]))
                        high = np.maximum(high, np.asarray(bounds["bboxMax"]))
                    margin = 1.0
                    surface = _concept_surface(session, text, defs, (low - margin, high + margin))
        except omega_core.EvalError as error:
            findings.add("error", "eval_failed", f"omega's evaluator did not score the points: {error}", path=where)
            return _result(target, findings, strict, "", {})

    if stale:
        return _staleness(target, where, kept, sampled, now, then, tolerance, findings, strict)

    rows = []
    for index, name in enumerate(sampled.names):
        mine = sampled.part == index
        value, pts = now[mine], sampled.points[mine]
        size = np.abs(value)
        worst = int(np.argmax(size))
        proud = int(np.argmax(value))
        short = int(np.argmin(value))
        rows.append({"part": name, "points": int(mine.sum()), "max_mm": round(float(size[worst]), 4),
                     "at": _at(pts[worst]), "p99_mm": round(float(np.quantile(size, 0.99)), 4),
                     "within_tolerance": round(float((size <= tolerance).mean()), 4),
                     "exact_proud_mm": round(max(float(value[proud]), 0.0), 4), "exact_proud_at": _at(pts[proud]),
                     "concept_proud_mm": round(max(-float(value[short]), 0.0), 4), "concept_proud_at": _at(pts[short])})
    reverse: dict[str, Any] = {"points": int(len(surface))}
    if len(surface):
        distance = distance_to_triangles(surface, sampled.triangles)
        far = int(np.argmax(distance))
        reverse.update(max_mm=round(float(distance[far]), 4), at=_at(surface[far]),
                       p99_mm=round(float(np.quantile(distance, 0.99)), 4),
                       within_tolerance=round(float((distance <= tolerance).mean()), 4))
    else:
        findings.add("error", "no_concept_surface", "no point of the concept's surface was found near the exact "
                     "parts: the concept is empty there, or in another frame", path=where,
                     hint="write the concept in the exact parts' frame")
    worst_row = max(rows, key=lambda row: row["max_mm"])
    deviation = max(worst_row["max_mm"], reverse.get("max_mm", 0.0))
    if max_deviation > 0 and deviation > max_deviation:
        findings.add("error", "deviation", f"the exact parts depart from the concept by up to {deviation:.3g} mm, "
                     f"more than the {max_deviation:g} asked: {worst_row['part']} at {worst_row['at']} "
                     f"(exact surface to concept) and {reverse.get('max_mm', 0.0):.3g} mm at {reverse.get('at')} "
                     "(concept surface to exact)", path=where)
    measurements: dict[str, Any] = {"parts": rows, "reverse": reverse, "points": int(len(sampled.points)),
                                    "tolerance_mm": tolerance, "chord_mm": chord}
    from cad._internal.validation_door import blocks

    if not blocks(findings, strict=strict):
        measurements["record"] = str(_record(target, text, defs, exact))
    summary = (f"OK {where}: baked into {exact}; the exact surface is within {worst_row['max_mm']:.3g} mm of the "
               f"concept ({worst_row['part']} at {worst_row['at']}), the concept's within "
               f"{reverse.get('max_mm', 0.0):.3g} mm of the exact parts; kept as baked in "
               f"{display_path(kept)}")
    return _result(target, findings, strict, summary, measurements)


def _queryable(text: str) -> str:
    from cad.omega._check import queryable

    return queryable(text)


#: Moved points this close (mm, a grid cell's edge) are one region of change.
_REGION_CELL_MM = 2.0


def _regions(points: Any) -> list[Any]:
    """``points`` grouped into regions: those whose grid cells (``_REGION_CELL_MM``) touch, face, edge or corner,
    are one. Each region is an array of indices into ``points``."""
    import numpy as np

    if not len(points):
        return []
    keys = [tuple(key) for key in np.floor(points / _REGION_CELL_MM).astype(np.int64)]
    members: dict[tuple, list[int]] = {}
    for index, key in enumerate(keys):
        members.setdefault(key, []).append(index)
    seen: set[tuple] = set()
    out = []
    for start in members:
        if start in seen:
            continue
        seen.add(start)
        stack, found = [start], []
        while stack:
            cell = stack.pop()
            found.extend(members[cell])
            for di in (-1, 0, 1):
                for dj in (-1, 0, 1):
                    for dk in (-1, 0, 1):
                        near = (cell[0] + di, cell[1] + dj, cell[2] + dk)
                        if near in members and near not in seen:
                            seen.add(near)
                            stack.append(near)
        out.append(np.asarray(found, np.int64))
    return out


def _staleness(target: Path, where: str, kept: Path, sampled: Sampled, now: Any, then: Any, tolerance: float,
               findings: Any, strict: bool) -> CheckResult:
    """Where the concept's field moved on the exact surface since it was baked (``kept``), part by part."""
    import numpy as np

    change = now - then  # above zero the concept's surface has moved off the exact one outward: it lost material
    rows = []
    for index, name in enumerate(sampled.names):
        mine = sampled.part == index
        delta, pts = change[mine], sampled.points[mine]
        moved = np.flatnonzero(np.abs(delta) > tolerance)
        regions = []
        for region in _regions(pts[moved]):
            members = moved[region]
            worst = members[int(np.argmax(np.abs(delta[members])))]
            regions.append({"change_mm": round(float(delta[worst]), 4), "at": _at(pts[worst]),
                            "min": _at(pts[members].min(axis=0)), "max": _at(pts[members].max(axis=0)),
                            "points": int(len(members))})
        regions.sort(key=lambda found: -abs(found["change_mm"]))
        rows.append({"part": name, "points": int(mine.sum()), "moved": int(len(moved)), "regions": regions})
        for found in regions:
            grew = found["change_mm"] < 0
            findings.add("error", "stale", f"the concept has {'grown' if grew else 'shrunk'} since it was baked, by "
                         f"up to {abs(found['change_mm']):.3g} mm at {found['at']} on {name}, over {found['min']} to "
                         f"{found['max']} ({found['points']} surface points)", path=where,
                         hint="bake the change into the exact part, then cad gsl bake again to keep the new concept")
    summary = (f"OK {where}: unchanged on the exact surface since it was baked "
               f"({len(sampled.points)} points, against {kept.name})")
    return _result(target, findings, strict, summary, {"parts": rows, "points": int(len(sampled.points)),
                                                      "tolerance_mm": tolerance, "record": str(kept)})
