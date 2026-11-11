"""The interference check: which parts of a document share volume, exactly, as built and where its
mechanism puts them.

An assembly is clear when no two of its parts share volume apart from the fits named on purpose.
``overlap_volume`` says so of one pair; this says it of a document: every pair of parts, at every
stance asked -- as built, at a pose or a mechanism state, at samples of a configuration sequence. The
verdict is the kernel's, on the parts' own solids: a mesh only says which pairs have air between them, and
so need no kernel (**The first pass**).

**What is measured** (``measure``). Each stance is every part's placement (the document's as built,
``mechanism.posed_instances`` posed). A pair is a candidate at a stance when the two parts' boxes
meet there: each part's own tight box (``BRepBndLib.AddOptimal``, measured once a part), placed, and
tested as boxes that turn with their parts (the separating axes of two oriented boxes), so a long
part standing at an angle rules out what the box of its box would not. A candidate is measured once
for each way the two parts stand to one another: the pair's key is its two parts' geometry and the
placement of one in the other's frame, so the copies of a part, the parts of one link at every pose,
and a stance that moves neither are one measurement.

**The first pass** (``_apart``). The kernel takes seconds over a pair, a minute over a drive beside a
lofted skin, and most pairs whose boxes meet have air between them: a mechanism inside its cover. So each
measurement is first asked of the two parts' meshes, made once a part (``_Surface``: as the engine meshes
a part, no coarser than ``TOLERANCE``), by the kernel's own proximity test, a tree of each mesh's triangles
(``BRepExtrema_ShapeProximity``, what other OCCT applications ask the same question with): where no
triangle of one comes within ``reach`` of a triangle of the other -- the two meshes' deflections with
``SLACK`` and ``MARGIN`` -- the true surfaces do not meet, and where moreover no shell of either lies
inside a solid of the other (a part swallowed whole: a point of each shell classified against each solid,
exactly), the two share nothing: 0, with no Boolean. Every other pair is the Boolean's. A part whose mesh
is not whole is never ruled out so.

**What is kept** (``_Kept``). A measurement is a fact of two geometries and how one stands to the other,
whatever document they are in: each is kept in the engine's cache under the two parts' geometry keys and
that placement, as it is made, and read there by the next check. So a model edited is measured again only
where a part that changed is one of the two, and a check stopped by its time goes on, when asked again,
from what it had measured.

**Who measures** (``_Crew``). The pairs are measured in a few processes of their own
(``jobs``), each started by this one and fed a pair at a time, the pairs of the fewest faces first, so
that what a check out of time leaves unmeasured is the slow few. A pair's Boolean cannot be stopped
from inside -- a kernel call holds its interpreter until it returns -- so a pair over its time
(``pair_seconds``) has its process killed and another started, and is reported **unmeasured**, as
is a pair whose process exited under it, one the kernel refused, and every pair not reached when
the check's own time (``seconds``) was up. An unmeasured pair has not been shown clear: the check
passes only with no interference and nothing unmeasured.

**What is said** (the report): each pair that shares volume, by its two occurrences' paths, with
the most it shared and the stances it did at; the named fits that do (``fits``: pairs of refs or
globs, measured and listed apart); each pair unmeasured, with why; and what was looked at -- the
parts, the stances, the pairs whose boxes met (``pairs.boxes_meet``), the measurements those came to
(``distinct``), and of those the ones the first pass ruled out (``apart``), the ones read from what was kept
(``kept``) and the ones the kernel made (``measured``).
"""

from __future__ import annotations

import hashlib
import json
import os
import queue
import re
import sys
import threading
import time
from pathlib import Path
from typing import Any

import numpy as np

__all__ = ["held", "measure"]

# A pair's placement in its partner's frame, rounded to tell two ways of standing apart: far below a
# kernel tolerance, far above the noise of two forward kinematics of one pose.
_PLACES = 7
# The stances a row of the report names before it counts the rest.
_NAMED = 4
# The slowest measurements a report names.
_SLOWEST = 5
# The first pass (``_apart``), millimetres. A part is meshed no coarser than TOLERANCE; a mesh is trusted to
# lie within SLACK times its deflection of its surface, and MARGIN more: two parts whose meshes come no
# nearer than that for both have air between their surfaces. A fine mesh costs a part a fraction of a second
# and spares a drive standing half a millimetre inside its cover a Boolean of minutes.
TOLERANCE = 0.05
SLACK = 1.5
MARGIN = 0.05
# What is kept (``_Kept``): the folder of the engine's cache, and how often it is written while a check runs.
KEPT = "interference"
_KEY = re.compile(r"[0-9a-f]{16,64}")  # a geometry key (``document.geometry_key``): what a kept file is named by
RECIPE = "1"  # of a measurement and of the first pass: another makes every kept one unknown
SAVED_EVERY = 10.0


class Refused(ValueError):
    """An option the document does not answer (a pose it has no state for, a fit that names nothing)."""


def held(source: Any, check: dict[str, Any], read: Any = None) -> dict[str, Any]:
    """The check one of the engine's checks processes runs of a document it holds (``source``, an
    ``export.Source``: a STEP's or an xbf's file, a held document's bytes), as ``check`` asks it
    (``{"type", "process": "interference", "resolved"}``, its options resolved by the caller,
    ``cad._internal.interference.options``). Plain data: ``{"measured": {"process", "resolved", "report"}}``,
    ``{"unmeasured": {"code", "message"}}`` for a document with no B-rep, or ``{"refused": words}`` for
    an option the document does not answer."""
    loaded = getattr(source, "loaded", None)
    if loaded is None:
        return {"unmeasured": {"code": "document_unreadable",
                               "message": f"{read or getattr(source, 'name', 'the document')} holds no B-rep to measure"}}
    resolved = dict(check.get("resolved") or {})
    try:
        from cad.engine import places

        report = measure(loaded.structure(), [prototype.shape for prototype in loaded.prototypes], resolved,
                         kept=places.cache_dir() / KEPT)
    except Refused as refused:
        return {"refused": str(refused)}
    return {"measured": {"process": "interference", "resolved": resolved, "report": report}}


# --- the stances ---------------------------------------------------------------------------------


def _matrix(column_major: Any) -> np.ndarray:
    return np.array(column_major, dtype=float).reshape(4, 4).T


def _stances(structure: dict[str, Any], options: dict[str, Any]) -> list[tuple[str, list[np.ndarray]]]:
    """Each stance asked, by name, as every instance's world matrix: as built first, then each pose
    (a mechanism state's name or ``{joint: value}``; ``states``: every state), then each motion's
    samples (``samples`` of them, its two ends among them; ``motions`` ``"all"``: every sequence)."""
    from cad.engine import mechanism

    found = [("as built", [_matrix(instance["matrix"]) for instance in structure["instances"]])]
    kinematics = structure.get("kinematics")
    poses = list(options.get("poses") or [])
    motions = options.get("motions") or []
    if kinematics is None:
        if poses or motions or options.get("states"):
            raise Refused("the document has no joints: it has no pose, mechanism state or configuration sequence "
                          "to stand at")
        return found
    if options.get("states"):
        poses += [name for name in sorted(kinematics.get("configurations") or {}) if name not in poses]
    for pose in poses:
        try:
            posed = mechanism.posed_structure(structure, pose)
        except ValueError as error:  # mechanism.KinematicsError: what the pose names wrong, by name
            raise Refused(f"pose: {error}") from None
        named = pose if isinstance(pose, str) else json.dumps(pose, separators=(",", ":"))
        found.append((f"pose {named}", [_matrix(instance["matrix"]) for instance in posed["instances"]]))
    if motions == "all":
        motions = sorted(kinematics.get("motions") or {})
    samples = int(options.get("samples") or 12)
    for name in motions:
        try:
            timeline = mechanism.Timeline(kinematics, name)
        except ValueError as error:
            raise Refused(f"motion: {error}") from None
        for step in range(samples):
            at = timeline.duration * step / max(samples - 1, 1)
            matrices = mechanism.posed_instances(structure, timeline.values(at))
            found.append((f"motion {name} at {at:.3g} s", [_matrix(matrix) for matrix in matrices]))
    return found


# --- the parts, and the pairs whose boxes meet ---------------------------------------------------


def _own_box(shape: Any) -> tuple[np.ndarray, np.ndarray] | None:
    """A part's tight box in its own frame, as its centre and half extents; None for one with no solid
    (a surface, a wire: nothing a volume is shared with)."""
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib
    from OCP.TopAbs import TopAbs_SOLID
    from OCP.TopExp import TopExp_Explorer

    if not TopExp_Explorer(shape, TopAbs_SOLID).More():
        return None
    box = Bnd_Box()
    BRepBndLib.AddOptimal_s(shape, box, False, False)
    if box.IsVoid():
        return None
    least, most = box.CornerMin(), box.CornerMax()
    low, high = np.array([least.X(), least.Y(), least.Z()]), np.array([most.X(), most.Y(), most.Z()])
    return (low + high) / 2, (high - low) / 2 + 1e-6


def _paths(structure: dict[str, Any]) -> dict[int, str]:
    """Each instance's occurrence path (``hand/finger.2``), as a ref names it."""
    from cad.engine import refs

    return {int(node.payload["instance"]): "/".join(step.segment for step in node.path())
            for node in refs.structure_tree(structure).parts() if "instance" in node.payload}


def _meeting(centres: np.ndarray, axes: np.ndarray, halves: np.ndarray, solid: np.ndarray) -> list[tuple[int, int]]:
    """The pairs of instances whose placed boxes meet: first as the boxes of those boxes (one
    comparison a pair), then as the boxes themselves, turned with their parts (``_boxes_meet``)."""
    reach = np.einsum("nij,nj->ni", np.abs(axes), halves)  # the half extents of each placed box's own box
    low, high = centres - reach, centres + reach
    firsts: list[np.ndarray] = []
    seconds: list[np.ndarray] = []
    order = np.flatnonzero(solid)
    for at, first in enumerate(order[:-1]):
        rest = order[at + 1:]
        near = rest[np.all((low[rest] <= high[first]) & (high[rest] >= low[first]), axis=1)]
        if len(near):
            firsts.append(np.full(len(near), first))
            seconds.append(near)
    if not firsts:
        return []
    a, b = np.concatenate(firsts), np.concatenate(seconds)
    meet = _boxes_meet(centres[a], axes[a], halves[a], centres[b], axes[b], halves[b])
    return [(int(first), int(second)) for first, second in zip(a[meet], b[meet])]


def _boxes_meet(ca: np.ndarray, ra: np.ndarray, ha: np.ndarray, cb: np.ndarray, rb: np.ndarray, hb: np.ndarray) -> np.ndarray:
    """Which of these pairs of oriented boxes meet, a row a pair (the separating-axis test: a pair is
    apart when one of fifteen axes -- each box's three and their nine cross products -- separates
    them). ``r``: a box's axes as columns; a mirrored part's serve as they are, a box being its own
    mirror image."""
    rotation = np.einsum("nki,nkj->nij", ra, rb)
    across = np.abs(rotation) + 1e-9  # two axes almost parallel make a cross product of noise
    apart = np.einsum("nki,nk->ni", ra, cb - ca)
    meet = np.all(np.abs(apart) <= ha + np.einsum("nij,nj->ni", across, hb), axis=1)
    meet &= np.all(np.abs(np.einsum("nij,ni->nj", rotation, apart)) <= np.einsum("nij,ni->nj", across, ha) + hb, axis=1)
    for i in range(3):
        u, v = (i + 1) % 3, (i + 2) % 3
        for j in range(3):
            p, q = (j + 1) % 3, (j + 2) % 3
            reach = (ha[:, u] * across[:, v, j] + ha[:, v] * across[:, u, j]
                     + hb[:, p] * across[:, i, q] + hb[:, q] * across[:, i, p])
            meet &= np.abs(apart[:, v] * rotation[:, u, j] - apart[:, u] * rotation[:, v, j]) <= reach
    return meet


def _named(structure: dict[str, Any], name: str) -> set[int]:
    """The instances a fit's name holds: a ref's part, or every part of its assembly, or of each
    occurrence a glob matches (``refs.matching``)."""
    from cad.engine import refs

    try:
        if refs.GLOB & set(name) and '"' not in name:
            nodes = refs.glob_structure(structure, name)
        else:
            hits = refs.resolve_structure(structure, name)
            if any(hit.kind is not None for hit in hits):
                raise Refused(f"fit: {name!r} names an element of a part; a fit is between parts or assemblies")
            nodes = [hit.node for hit in hits]
    except refs.RefError as error:
        raise Refused(f"fit: {error}") from None
    found = {int(part.payload["instance"]) for node in nodes for part in node.parts() if "instance" in part.payload}
    if not found:
        raise Refused(f"fit: {name!r} matches no part or assembly of {structure.get('name') or 'the document'}")
    return found


# --- the first pass: which pairs have air between them -------------------------------------------


class _Surface:
    """A part as the first pass reads it (the module's **The first pass**): its shape meshed in its own
    frame (``shape``: a copy, the document's own left as it is), the most that mesh may lie from the true
    surface (``linear``), a vertex of each of its shells (``seeds``: a point on every closed surface it
    has), its solids with their boxes (``solids``), whether every face meshed and every shell has a seed
    (``whole``), and how many faces it has (``count``: what a measurement of it costs, roughly)."""

    def __init__(self, shape: Any) -> None:
        from OCP.BRep import BRep_Tool
        from OCP.TopAbs import TopAbs_FACE, TopAbs_SHELL, TopAbs_SOLID, TopAbs_VERTEX
        from OCP.TopExp import TopExp_Explorer
        from OCP.TopLoc import TopLoc_Location
        from OCP.TopoDS import TopoDS

        from cad.engine import mesh

        self.shape = local = mesh.read_shape(mesh.shape_bytes(shape, read=True))
        self.linear = min(mesh.deflection(local), TOLERANCE)
        _mesh(local, self.linear)
        self.whole, self.count = True, 0
        faces = TopExp_Explorer(local, TopAbs_FACE)
        while faces.More():
            self.count += 1
            if BRep_Tool.Triangulation_s(TopoDS.Face(faces.Current()), TopLoc_Location()) is None:
                self.whole = False
            faces.Next()
        self.count = max(1, self.count)
        seeds: list[tuple[float, float, float]] = []
        shells = TopExp_Explorer(local, TopAbs_SHELL)
        while shells.More():
            vertex = TopExp_Explorer(shells.Current(), TopAbs_VERTEX)
            if vertex.More():
                point = BRep_Tool.Pnt_s(TopoDS.Vertex(vertex.Current()))
                seeds.append((point.X(), point.Y(), point.Z()))
            else:
                self.whole = False
            shells.Next()
        self.seeds = np.array(seeds, dtype=float).reshape(-1, 3)
        self.solids: list[list[Any]] = []  # each [the solid, its box's low, its high, its classifier once asked]
        solids = TopExp_Explorer(local, TopAbs_SOLID)
        while solids.More():
            low, high = _box(solids.Current())
            self.solids.append([solids.Current(), low, high, None])
            solids.Next()

    def inside(self, points: np.ndarray) -> bool:
        """Whether any of ``points``, in this part's frame, lies in or on one of its solids."""
        from OCP.BRepClass3d import BRepClass3d_SolidClassifier
        from OCP.gp import gp_Pnt
        from OCP.TopAbs import TopAbs_IN, TopAbs_ON

        for solid in self.solids:
            for point in points[np.all((points >= solid[1]) & (points <= solid[2]), axis=1)]:
                if solid[3] is None:
                    solid[3] = BRepClass3d_SolidClassifier(solid[0])
                solid[3].Perform(gp_Pnt(float(point[0]), float(point[1]), float(point[2])), 1e-7)
                if solid[3].State() in (TopAbs_IN, TopAbs_ON):
                    return True
        return False


def _mesh(shape: Any, linear: float) -> None:
    """Mesh ``shape`` in place as the engine meshes a part (``mesh.mesh_shape``), to ``linear``."""
    from OCP.BRepMesh import BRepMesh_IncrementalMesh
    from OCP.IMeshTools import IMeshTools_Parameters

    from cad.engine import mesh

    parameters = IMeshTools_Parameters()
    parameters.Deflection, parameters.Angle, parameters.Relative, parameters.InParallel = linear, mesh.ANGULAR, False, True
    parameters.EnableControlSurfaceDeflectionAllSurfaces = True
    parameters.ForceFaceDeflection = True
    BRepMesh_IncrementalMesh(shape, parameters)


def _box(shape: Any) -> tuple[np.ndarray, np.ndarray]:
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib

    box = Bnd_Box()
    BRepBndLib.Add_s(shape, box, False)
    if box.IsVoid():
        return np.zeros(3), np.zeros(3)
    least, most = box.CornerMin(), box.CornerMax()
    return (np.array([least.X(), least.Y(), least.Z()]) - 1e-6, np.array([most.X(), most.Y(), most.Z()]) + 1e-6)


def _apart(a: _Surface, b: _Surface, placed: np.ndarray) -> bool:
    """Whether two parts certainly share nothing, ``b`` standing in ``a``'s frame at ``placed`` (3 x 4): no
    triangle of one mesh within ``reach`` of a triangle of the other (the kernel's own proximity test, a
    tree of each mesh's triangles: ``BRepExtrema_ShapeProximity``), so the true surfaces meet nowhere, and
    no shell of either inside a solid of the other. False is no verdict: the pair is the kernel's."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
    from OCP.BRepExtrema import BRepExtrema_ShapeProximity
    from OCP.gp import gp_Trsf
    from OCP.TopLoc import TopLoc_Location

    if not (a.whole and b.whole):
        return False
    trsf = gp_Trsf()
    trsf.SetValues(*(float(value) for value in placed.ravel()))
    if trsf.IsNegative() or abs(trsf.ScaleFactor() - 1.0) > 1e-9:
        moved = BRepBuilderAPI_Transform(b.shape, trsf, True).Shape()  # a mirrored placement: a copy, meshed anew
        _mesh(moved, b.linear)
    else:
        moved = b.shape.Moved(TopLoc_Location(trsf))
    proximity = BRepExtrema_ShapeProximity(a.shape, moved, SLACK * (a.linear + b.linear) + MARGIN)
    proximity.Perform()
    # ``IsDone`` says an overlap was found, not that the test ran: what says it ran is each side's triangles,
    # loaded. A side with none (a shape the tool read no mesh of) is ruled out of nothing.
    if not (proximity.ElementSet1().Size() and proximity.ElementSet2().Size()):
        return False
    if proximity.OverlapSubShapes1().Extent() or proximity.OverlapSubShapes2().Extent():
        return False
    # Surfaces that meet nowhere: each shell of one is wholly inside a solid of the other, or wholly outside it.
    turn, shift = placed[:3, :3], placed[:3, 3]
    if len(b.seeds) and a.inside(b.seeds @ turn.T + shift):
        return False
    return not (len(a.seeds) and b.inside((a.seeds - shift) @ np.linalg.inv(turn).T))


# --- what is kept --------------------------------------------------------------------------------


class _Kept:
    """The measurements kept in the engine's cache (the module's **What is kept**): a file for each two
    geometries, ``<folder>/<recipe>/<xx>/<digest>.json``, holding the volume shared at each placement of
    one in the other's frame measured so far, and a file for each geometry's tight box (``box``). Read when first asked of, written as measurements come
    (``SAVED_EVERY`` seconds at most apart) and at the end, each file over what it holds then, so two checks
    at once lose nothing but a measurement one of them repeats. A folder that takes no file keeps nothing,
    and says nothing: it is a cache."""

    def __init__(self, folder: Path | None) -> None:
        self.folder = None if folder is None else Path(folder) / RECIPE
        self.held: dict[str, dict[str, float]] = {}
        self.new: dict[str, dict[str, float]] = {}
        self.boxes: dict[Path, list[float] | None] = {}
        self.lock = threading.Lock()
        self.saved = time.monotonic()

    @staticmethod
    def _names(key: tuple) -> tuple[str, str]:
        first, second, stood = key
        return (hashlib.blake2b(f"{first}\0{second}".encode(), digest_size=16).hexdigest(),
                hashlib.blake2b(repr(stood).encode(), digest_size=12).hexdigest())

    def _path(self, name: str) -> Path:
        assert self.folder is not None
        return self.folder / name[:2] / f"{name}.json"

    def _read(self, name: str) -> dict[str, float]:
        try:
            found = json.loads(self._path(name).read_text(encoding="utf-8"))
            return {str(at): float(volume) for at, volume in found["volumes"].items()}
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            return {}

    def get(self, key: tuple | None) -> float | None:
        """The volume kept for a measurement, or None."""
        if self.folder is None or key is None:
            return None
        name, at = self._names(key)
        with self.lock:
            if name not in self.held:
                self.held[name] = self._read(name)
            return self.held[name].get(at)

    def put(self, key: tuple | None, volume: float) -> None:
        """Keep a measurement, and write what is new when it is time."""
        if self.folder is None or key is None:
            return
        name, at = self._names(key)
        with self.lock:
            self.held.setdefault(name, {})[at] = volume
            self.new.setdefault(name, {})[at] = volume
            due = time.monotonic() - self.saved >= SAVED_EVERY
        if due:
            self.save()

    def box(self, key: str, shape: Any) -> tuple[np.ndarray, np.ndarray] | None:
        """A part's tight box (``_own_box``), read where its geometry's was kept: the kernel takes a tenth
        of a second and more over one, a maker's drive several, and a check asks every part's."""
        if self.folder is None or not _KEY.fullmatch(key):
            return _own_box(shape)
        path = self.folder / "boxes" / key[:2] / f"{key}.json"
        try:
            found = json.loads(path.read_text(encoding="utf-8"))["box"]
            return None if found is None else (np.array(found[:3], dtype=float), np.array(found[3:6], dtype=float))
        except (OSError, ValueError, KeyError, TypeError, IndexError):
            pass
        box = _own_box(shape)
        with self.lock:
            self.boxes[path] = None if box is None else [*box[0].tolist(), *box[1].tolist()]
        return box

    def save(self) -> None:
        """Write every measurement and every box not yet written."""
        from cad.engine.atomic_replace import put

        with self.lock:
            new, self.new, self.saved = self.new, {}, time.monotonic()
            boxes, self.boxes = self.boxes, {}
        for path, box in boxes.items():
            body = json.dumps({"box": box}, separators=(",", ":"))
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                put(path, lambda staged: staged.write_text(body, encoding="utf-8"))
            except OSError:
                self.folder = None
                return
        for name, volumes in new.items():
            path = self._path(name)
            body = json.dumps({"volumes": {**self._read(name), **volumes}}, separators=(",", ":"), sort_keys=True)
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                put(path, lambda staged: staged.write_text(body, encoding="utf-8"))
            except OSError:
                self.folder = None  # a cache that cannot be written is none
                return


# --- the measuring -------------------------------------------------------------------------------


def measure(structure: dict[str, Any], shapes: list[Any], options: dict[str, Any],
            kept: Path | None = None) -> dict[str, Any]:
    """The interference report of a document (the module's docstring): ``structure`` as the engine
    serves it, ``shapes`` each prototype's shape, ``options`` resolved (``poses``, ``states``,
    ``motions``, ``samples``, ``fits``, ``jobs``, ``pair_seconds``, ``seconds``, ``min_volume``).
    ``kept``: the folder measurements are kept in and read from (``_Kept``); none keeps nothing."""
    import tempfile

    from cad.engine import mesh

    started = time.monotonic()
    seconds = float(options.get("seconds") or 0) or None
    instances = structure["instances"]
    paths = _paths(structure)
    fits = [(str(a), str(b), _named(structure, str(a)), _named(structure, str(b))) for a, b in options.get("fits") or []]
    stances = _stances(structure, options)
    store = _Kept(kept)
    boxes = [store.box(str(prototype.get("key") or ""), shape)
             for prototype, shape in zip(structure["prototypes"], shapes)]
    solid = np.array([boxes[instance["prototype"]] is not None for instance in instances], dtype=bool)
    keys = [str(structure["prototypes"][instance["prototype"]].get("key") or instance["prototype"])
            for instance in instances]
    named = [bool(structure["prototypes"][instance["prototype"]].get("key")) for instance in instances]

    # Every candidate, at every stance, as one measurement for each way its two parts stand to one another.
    tasks: dict[tuple, int] = {}
    orders: list[dict[str, Any]] = []
    seen: dict[tuple[int, int], list[tuple[int, int]]] = {}  # an instance pair -> (stance, measurement)
    candidates = 0
    for stance, (_name, matrices) in enumerate(stances):
        centres = np.zeros((len(instances), 3))
        axes = np.tile(np.eye(3), (len(instances), 1, 1))
        halves = np.zeros((len(instances), 3))
        for index, instance in enumerate(instances):
            box = boxes[instance["prototype"]]
            if box is not None:
                matrix = matrices[index]
                centres[index], axes[index], halves[index] = matrix[:3, :3] @ box[0] + matrix[:3, 3], matrix[:3, :3], box[1]
        for first, second in _meeting(centres, axes, halves, solid):
            candidates += 1
            a, b = (first, second) if keys[first] <= keys[second] else (second, first)
            placed = np.linalg.inv(matrices[a]) @ matrices[b]
            stood = tuple(np.round(placed[:3, :4], _PLACES).ravel().tolist())
            if keys[a] == keys[b]:  # two copies of one part: either may be the one stood in the other's frame
                other = tuple(np.round(np.linalg.inv(placed)[:3, :4], _PLACES).ravel().tolist())
                if other < stood:
                    stood, placed = other, np.linalg.inv(placed)
            key = (keys[a], keys[b], stood)
            if key not in tasks:
                tasks[key] = len(orders)
                orders.append({"n": len(orders), "a": instances[a]["prototype"], "b": instances[b]["prototype"],
                               "placed": placed[:3, :4].ravel().tolist(),
                               # Kept only under two geometry keys: a part with none is known by its place in
                               # this document alone.
                               "key": key if named[a] and named[b] else None})
            seen.setdefault((first, second), []).append((stance, tasks[key]))

    # Each measurement: read from what was kept, else ruled out by the two surfaces, else the kernel's.
    deadline = None if seconds is None else started + seconds
    answers: dict[int, dict[str, Any]] = {}
    surfaces: dict[int, _Surface] = {}
    asked: list[dict[str, Any]] = []
    known = ruled = 0
    try:
        for order in orders:
            volume = store.get(order["key"])
            if volume is not None:
                answers[order["n"]], known = {"volume": volume}, known + 1
                continue
            if deadline is not None and time.monotonic() >= deadline:
                answers[order["n"]] = {"unmeasured": "not reached before the check's time was up"}
                continue
            for index in (order["a"], order["b"]):
                if index not in surfaces:
                    surfaces[index] = _Surface(shapes[index])
            if _apart(surfaces[order["a"]], surfaces[order["b"]], np.array(order["placed"], dtype=float).reshape(3, 4)):
                answers[order["n"]], ruled = {"volume": 0.0}, ruled + 1
                store.put(order["key"], 0.0)
            else:
                asked.append(order)
        if asked:
            # The pairs of the fewest faces first: what a check out of time leaves is the slow few.
            asked.sort(key=lambda order: surfaces[order["a"]].count * surfaces[order["b"]].count)

            def done(order: dict[str, Any], answer: dict[str, Any]) -> None:
                if "volume" in answer:
                    store.put(order["key"], answer["volume"])

            with tempfile.TemporaryDirectory(prefix="cad-interference-") as folder:
                for index in sorted({order[side] for order in asked for side in ("a", "b")}):
                    (Path(folder) / f"{index}.brep").write_bytes(mesh.shape_bytes(shapes[index], read=True))
                crew = _Crew(Path(folder), int(options.get("jobs") or _jobs()),
                             float(options.get("pair_seconds") or 300.0), deadline, done)
                answers.update(crew.run(asked))
    finally:
        store.save()

    floor = float(options.get("min_volume") or 0.0)
    interferences, fitted, unmeasured = [], [], []
    for (first, second), found in sorted(seen.items()):
        volumes = [(answers[task].get("volume"), stance) for stance, task in found]
        row = {"a": paths.get(first, str(first)), "b": paths.get(second, str(second))}
        shared = [(volume, stance) for volume, stance in volumes if volume is not None and volume > floor]
        if shared:
            at = [stances[stance][0] for _volume, stance in shared]
            entry = {**row, "volume": max(volume for volume, _stance in shared), "stances": len(at), "at": at[:_NAMED]}
            fit = next((f"{a} in {b}" for a, b, held_a, held_b in fits
                        if (first in held_a and second in held_b) or (first in held_b and second in held_a)), None)
            if fit is None:
                interferences.append(entry)
            else:
                fitted.append({**entry, "fit": fit})
        missed = [(answers[task]["unmeasured"], stance) for stance, task in found if "unmeasured" in answers[task]]
        if missed:
            unmeasured.append({**row, "reason": missed[0][0], "stances": len(missed),
                               "at": [stances[stance][0] for _why, stance in missed][:_NAMED]})
    interferences.sort(key=lambda entry: -entry["volume"])
    # The measurements that took longest, each by the first pair it answered: where a slow check's time went.
    first_of: dict[int, tuple[int, int]] = {}
    for pair, found in sorted(seen.items()):
        for _stance, task in found:
            first_of.setdefault(task, pair)
    timed = sorted(((answers[order["n"]].get("seconds", 0.0), order["n"]) for order in asked), reverse=True)[:_SLOWEST]
    slowest = [{"a": paths.get(first_of[task][0], ""), "b": paths.get(first_of[task][1], ""), "seconds": round(took, 2)}
               for took, task in timed if took >= 1.0]
    return {
        "name": str(structure.get("name") or ""),
        "parts": int(solid.sum()), "skipped": int(len(instances) - solid.sum()),
        "stances": [name for name, _matrices in stances],
        "pairs": {"boxes_meet": candidates, "distinct": len(orders), "kept": known, "apart": ruled,
                  "measured": sum(1 for order in asked if "volume" in answers[order["n"]])},
        "interferences": interferences, "fits": fitted, "unmeasured": unmeasured, "slowest": slowest,
        # A check that left a pair unmeasured is not kept by the engine: asked again, it measures again.
        "partial": bool(unmeasured),
        "seconds": round(time.monotonic() - started, 2),
    }


def _jobs() -> int:
    """The processes that measure when none are asked: one for each of the machine's cores, four at most --
    each holds a kernel and the parts it has measured, and the check's own process waits on them."""
    return max(1, min(4, os.cpu_count() or 1))


class _Crew:
    """The processes that measure the pairs (the module's docstring): ``jobs`` of them, each fed one
    order at a time, in the order given, by a thread of this process that waits for its answer no longer
    than ``pair_seconds`` and not past ``deadline``. ``done`` hears each order with its answer as it comes."""

    def __init__(self, folder: Path, jobs: int, pair_seconds: float, deadline: float | None,
                 done: Any = None) -> None:
        self.folder, self.jobs, self.pair_seconds, self.deadline = folder, max(1, jobs), pair_seconds, deadline
        self.done = done

    def run(self, orders: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
        """Each order's answer by its number: ``{"volume"}``, or ``{"unmeasured": why}``."""
        waiting: queue.SimpleQueue = queue.SimpleQueue()
        for order in orders:
            waiting.put(order)
        answers: dict[int, dict[str, Any]] = {}
        threads = [threading.Thread(target=self._work, args=(waiting, answers), name=f"cad-interference-{at}", daemon=True)
                   for at in range(min(self.jobs, len(orders)))]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        return answers

    def _start(self) -> tuple[Any, queue.SimpleQueue]:
        import site
        import subprocess

        from cad.engine.places import windowless

        # This library first on the child's path where its interpreter would not find it by itself (a
        # checkout, a test's path): as a check a caller measures itself starts its process.
        root = Path(__file__).resolve().parents[2]
        env = dict(os.environ)
        if root not in {Path(found).resolve() for found in (*site.getsitepackages(), site.getusersitepackages())}:
            env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(root), env.get("PYTHONPATH")]))
        process = subprocess.Popen([sys.executable, "-c", "from cad.build123d._interference import _serve; _serve()",
                                    str(self.folder)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, env=env,
                                   text=True, encoding="utf-8", **windowless())
        lines: queue.SimpleQueue = queue.SimpleQueue()

        def read() -> None:
            try:
                for line in process.stdout:  # type: ignore[union-attr]
                    lines.put(line)
            except (OSError, ValueError):
                pass
            lines.put(None)  # its end of file: the process is gone

        threading.Thread(target=read, name="cad-interference-read", daemon=True).start()
        return process, lines

    @staticmethod
    def _end(process: Any) -> None:
        try:
            process.kill()
        except OSError:
            pass
        for stream in (process.stdin, process.stdout):
            try:
                stream.close()
            except (OSError, ValueError):
                pass
        try:
            process.wait(timeout=10)
        except Exception:  # noqa: BLE001 - a process that will not be waited for is left to the system
            pass

    def _work(self, waiting: queue.SimpleQueue, answers: dict[int, dict[str, Any]]) -> None:
        held: tuple[Any, queue.SimpleQueue] | None = None
        try:
            while True:
                try:
                    order = waiting.get_nowait()
                except queue.Empty:
                    return
                left = None if self.deadline is None else self.deadline - time.monotonic()
                if left is not None and left <= 0:
                    answers[order["n"]] = {"unmeasured": "not reached before the check's time was up"}
                    continue
                if held is None:
                    held = self._start()
                process, lines = held
                limit = self.pair_seconds if left is None else min(self.pair_seconds, left)
                began = time.monotonic()
                try:
                    sent = {name: order[name] for name in ("n", "a", "b", "placed")}
                    process.stdin.write(json.dumps(sent, separators=(",", ":")) + "\n")
                    process.stdin.flush()
                    line = lines.get(timeout=limit)
                except queue.Empty:
                    self._end(process)
                    held = None
                    answers[order["n"]] = {"unmeasured": (f"not measured within {self.pair_seconds:g} s"
                                                          if limit >= self.pair_seconds else
                                                          "stopped as the check's time was up")}
                    continue
                except (OSError, ValueError):
                    line = None
                if line is None:
                    self._end(process)
                    held = None
                    answers[order["n"]] = {"unmeasured": "the process measuring it exited (the system ends one "
                                                         "when memory runs out)"}
                    continue
                answer = json.loads(line)
                answers[order["n"]] = ({"volume": float(answer["volume"])} if "volume" in answer
                                       else {"unmeasured": f"the kernel could not intersect them: {answer.get('error')}"})
                answers[order["n"]]["seconds"] = time.monotonic() - began
                if self.done is not None:
                    self.done(order, answers[order["n"]])
        finally:
            if held is not None:
                self._end(held[0])


def _serve() -> None:
    """A process of the crew's: each order on its standard input (a line of JSON: ``{"n", "a", "b",
    "placed"}``, the two parts by their files in the folder its argument names, the second placed in
    the first's frame) measured, and answered on what was its standard output (``{"n", "volume"}`` or
    ``{"n", "error"}``); the kernel's own prints go to its standard error. It ends at the end of its
    input, at once, whatever it is measuring: its caller closed it, or is gone."""
    from OCP.gp import gp_Trsf

    from cad.build123d._geometry import _overlap_volume
    from cad.engine import mesh

    folder = Path(sys.argv[1])
    out = os.fdopen(os.dup(1), "w", encoding="utf-8")
    os.dup2(2, 1)
    shapes: dict[int, Any] = {}

    def part(index: int) -> Any:
        if index not in shapes:
            shapes[index] = mesh.read_shape((folder / f"{index}.brep").read_bytes())
        return shapes[index]

    def placed(shape: Any, rows: list[float]) -> Any:
        import build123d as bd
        from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
        from OCP.TopLoc import TopLoc_Location

        trsf = gp_Trsf()
        trsf.SetValues(*(float(value) for value in rows))
        if trsf.IsNegative() or abs(trsf.ScaleFactor() - 1.0) > 1e-9:
            return bd.Shape.cast(BRepBuilderAPI_Transform(shape, trsf, True).Shape())  # a mirrored placement: a copy
        return bd.Shape.cast(shape.Moved(TopLoc_Location(trsf)))

    # Its input is read apart from the measuring, so that its end is heard while a Boolean runs: a caller
    # that closed it, or is gone, waits for nothing, and a Boolean left running holds a core for minutes.
    lines: queue.SimpleQueue = queue.SimpleQueue()

    def read() -> None:
        try:
            for line in sys.stdin:
                lines.put(line)
        finally:
            os._exit(0)

    threading.Thread(target=read, name="cad-interference-orders", daemon=True).start()
    while True:
        order = json.loads(lines.get())
        try:
            import build123d as bd

            volume = float(_overlap_volume(bd.Shape.cast(part(order["a"])), placed(part(order["b"]), order["placed"]),
                                           parallel=True))
            if volume != volume or volume in (float("inf"), float("-inf")):
                raise ValueError("the shared volume is not a finite number")
            answer = {"n": order["n"], "volume": volume}
        except Exception as error:  # noqa: BLE001 - what the kernel refused is the pair's answer: unmeasured
            answer = {"n": order["n"], "error": f"{type(error).__name__}: {error}"}
        out.write(json.dumps(answer, separators=(",", ":")) + "\n")
        out.flush()
