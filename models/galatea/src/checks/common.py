"""Shared by Galatea's checks: the robot's parts by link, as meshes and as exact solids,
posed by `lib.kin`, and the interference test over them.

The meshes come from one GLB export of the model as built (the server's own tessellation,
each prototype once); the solids are the model's own (`handle.shape`), matched to the
meshes part by part. A pose never goes back to the server: every link is a rigid body, so
`kin.link_transforms` places its parts.

Two parts interfere when the solids share volume: `overlap_volume`, the kernel's exact
intersection, which is 0 for parts that only touch. That is the verdict. The meshes serve
two lesser purposes: to place parts, and to say which pairs need the kernel at all. A
pair whose meshes neither cross nor come within their own error of it (`surfaces_near`)
cannot share volume, and is left out. Where a sweep or a motion has hundreds
of frames, a pair whose meshes cross is first sized by them (`mesh_depth`): one sunk
deeper than DEEP goes to the kernel at that frame, and every other crossing pair goes to
it once, at the frame where it sat deepest. A mesh alone never convicts a pair.

(An earlier version of this file asked whether sample points of one mesh lay inside the
other. A flat plate has no points but on its outline and a 2.6 mm skin has no inside to
speak of, so it passed a rail through a shin guard. It is gone.)
"""

import multiprocessing
import os
import queue
import resource
import signal
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import trimesh  # noqa: E402

from lib import kin  # noqa: E402

SHARED = 0.5         # two solids sharing more than this interfere, mm^3 (a boolean's own noise is far below it)
PATIENCE = 900.0     # a pair's intersection may take this long, seconds, before it is given up as unmeasured
                     # (the chest's back plate against its frame takes four minutes alone)
WORKERS = min(4, os.cpu_count() or 1)
REACH = 0.5          # the least a mesh is pushed out to find what its solid could touch, mm
DEEP = 0.6           # a mesh sunk deeper than this into another is no fit of a pin in its bore, mm
GL_TO_CAD = np.array([[1000.0, 0, 0, 0], [0, 0, -1000.0, 0], [0, 1000.0, 0, 0], [0, 0, 0, 1]])   # a GLB node: metres, Y up


class Geometry:
    """One distinct mesh, in its own frame (millimetres)."""

    def __init__(self, name, mesh):
        mesh = mesh.copy()
        mesh.merge_vertices(merge_tex=True, merge_norm=True)
        # A sphere's pole or a loft's apex meshes as a few degenerate triangles; such a mesh
        # still answers "is this point inside" by ray casting, so it counts as closed.
        _, counts = np.unique(mesh.edges_sorted, axis=0, return_counts=True)
        self.name, self.mesh, self.watertight = name, mesh, int((counts != 2).sum()) <= 8
        self.edges = mesh.edges_unique
        self.pulled = mesh.vertices - 0.05 * mesh.vertex_normals       # so a shared face is not a crossing
        # A mesh stands at most a quarter per cent of its part's box from the surface it facets.
        # Pushed out by twice that (and no less than REACH), it reaches whatever the solid could.
        lo, hi = mesh.bounds
        self.pushed = mesh.vertices + max(REACH, 0.005 * float(np.linalg.norm(hi - lo))) * mesh.vertex_normals
        lo, hi = mesh.bounds
        self.corners = np.array([[x, y, z] for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])])


class Part:
    def __init__(self, link, path, geometry, placed):
        self.link, self.path, self.geometry = link, path, geometry
        self.rest = GL_TO_CAD @ placed            # its frame -> the world at the zero pose, mm
        self.world = self.rest
        self.moved = np.eye(4)                    # its link's transform at the current pose
        self.solid = None                         # its exact solid at the zero pose (`load_parts(exact=True)`)
        self._box()

    def pose(self, link_matrix):
        self.moved = link_matrix
        self.world = link_matrix @ self.rest
        self._box()

    def _box(self):
        corners = self.geometry.corners @ self.world[:3, :3].T + self.world[:3, 3]
        self.lo, self.hi = corners.min(axis=0), corners.max(axis=0)


def load_parts(handle, exact=False):
    """{link: [Part, ...]} for the model `handle` (a model call's handle) as built; with
    `exact`, each part also carries its solid from the model's own tree."""
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "model.glb"
        handle.export(str(path))
        scene = trimesh.load(str(path), process=False)
    geometries = {name: Geometry(name, mesh) for name, mesh in scene.geometry.items()}
    links = {}
    for node in scene.graph.nodes_geometry:
        placed, name = scene.graph[node]
        link = node.split("/")[0]
        links.setdefault(link, []).append(Part(link, node, geometries[name], placed))
    open_meshes = sorted(name for name, g in geometries.items() if not g.watertight)
    if open_meshes:
        print(f"note: {len(open_meshes)} meshes are not closed: {open_meshes[:8]}")
    if exact:
        _attach_solids(links, handle.shape)
    return links


def _attach_solids(links, tree):
    """Give each part the leaf of the model's tree it was meshed from: the one of its link
    and label whose box sits where the mesh's does."""
    for group in tree.children:
        leaves = {}
        for leaf in group.children:
            box = leaf.bounding_box()
            centre = np.array([(box.min.X + box.max.X) / 2, (box.min.Y + box.max.Y) / 2, (box.min.Z + box.max.Z) / 2])
            leaves.setdefault(leaf.label, []).append((centre, leaf))
        for part in links[group.label]:
            label = part.path.split("/")[-1]
            pool = leaves.get(label) or leaves[label.rsplit("_", 1)[0]]         # a repeated label's node is numbered
            centre = (part.lo + part.hi) / 2
            nearest = min(range(len(pool)), key=lambda k: float(np.linalg.norm(pool[k][0] - centre)))
            # A label borne once is its part. One borne by several (screws, a pair of covers) is told
            # apart by place; their boxes are tight, where a lofted skin's own box is a loose one.
            if len(pool) > 1 and np.linalg.norm(pool[nearest][0] - centre) > 3.0:
                raise ValueError(f"{part.path}: no solid of the model sits where its mesh does")
            part.solid = pool.pop(nearest)[1]


def _matrix(transform):
    r, p = transform
    m = np.eye(4)
    m[:3, :3], m[:3, 3] = np.array(r), np.array(p)
    return m


def pose_parts(links, pose):
    """Move every link's parts to where `pose` (controls) puts them."""
    transforms = kin.link_transforms(pose)
    for link, parts in links.items():
        matrix = _matrix(transforms[link])
        for part in parts:
            part.pose(matrix)


def boxes_meet(a_lo, a_hi, b_lo, b_hi, slack=0.0):
    return bool(np.all(a_lo <= b_hi + slack) and np.all(b_lo <= a_hi + slack))


def link_box(parts):
    return np.min([p.lo for p in parts], axis=0), np.max([p.hi for p in parts], axis=0)


def near_pairs(links, within=True, between=True, skip=None):
    """Every pair of parts whose boxes meet at the current pose: inside each link, and link
    against link (`skip(link_a, link_b)` leaves a pair of links out)."""
    pairs, names = [], list(links)
    if within:
        for name in names:
            if skip and skip(name, name):
                continue
            parts = links[name]
            pairs += [(a, b) for i, a in enumerate(parts) for b in parts[i + 1:] if boxes_meet(a.lo, a.hi, b.lo, b.hi)]
    if between:
        boxes = {name: link_box(parts) for name, parts in links.items()}
        for i, na in enumerate(names):
            for nb in names[i + 1:]:
                if (skip and skip(na, nb)) or not boxes_meet(*boxes[na], *boxes[nb]):
                    continue
                pairs += [(a, b) for a in links[na] if boxes_meet(a.lo, a.hi, *boxes[nb])
                          for b in links[nb] if boxes_meet(a.lo, a.hi, b.lo, b.hi)]
    return pairs


# ---------------------------------------------------------------------------------------------
# The meshes' part: which pairs' surfaces pass through each other
# ---------------------------------------------------------------------------------------------
def _edges_into(a, b, vertices):
    """a's mesh edges, in b's frame, that reach b's box: (start points, unit directions, lengths)."""
    carry = np.linalg.inv(b.world) @ a.world                      # a's frame -> b's frame
    points = vertices @ carry[:3, :3].T + carry[:3, 3]
    start, end = points[a.geometry.edges[:, 0]], points[a.geometry.edges[:, 1]]
    lo, hi = b.geometry.mesh.bounds
    reach = np.all(np.maximum(start, end) >= lo, axis=1) & np.all(np.minimum(start, end) <= hi, axis=1)
    start, along = start[reach], (end - start)[reach]
    length = np.linalg.norm(along, axis=1)
    keep = length > 1e-9
    return start[keep], along[keep] / length[keep, None], length[keep]


def _pierces(a, b, vertices=None):
    """Does an edge of a's mesh pass through a triangle of b's?"""
    start, along, length = _edges_into(a, b, a.geometry.pulled if vertices is None else vertices)
    if not len(start):
        return False
    hits, rays, _ = b.geometry.mesh.ray.intersects_location(start, along, multiple_hits=False)
    return bool(len(rays) and np.any(np.linalg.norm(hits - start[rays], axis=1) < length[rays] - 1e-6))


def _swallows(a, b):
    """Does b's mesh hold one of a's vertices? (With no edge through a triangle: all of a.)"""
    if not b.geometry.watertight:
        return False
    carry = np.linalg.inv(b.world) @ a.world
    return bool(b.geometry.mesh.contains(a.geometry.pulled[:1] @ carry[:3, :3].T + carry[:3, 3])[0])


def surfaces_cross(pair):
    """Do the two parts' meshes pass through each other, or one lie inside the other?"""
    a, b = pair
    return _pierces(a, b) or _pierces(b, a) or _swallows(a, b) or _swallows(b, a)


def surfaces_near(pair):
    """Do the meshes cross, or would they if either stood further out by its own error
    twice over? A pair that fails this is apart by more than the meshes can be wrong, so
    its solids share nothing."""
    a, b = pair
    return surfaces_cross(pair) or _pierces(a, b, a.geometry.pushed) or _pierces(b, a, b.geometry.pushed)


def _sunk(a, b):
    """How deep (mm) a's mesh edges run inside b's mesh: the deepest point midway between
    where an edge enters and where it leaves."""
    if not b.geometry.watertight:
        return 0.0
    start, along, length = _edges_into(a, b, a.geometry.pulled)
    if not len(start):
        return 0.0
    hits, rays, _ = b.geometry.mesh.ray.intersects_location(start, along, multiple_hits=True)
    if not len(rays):
        return 0.0
    reach = np.linalg.norm(hits - start[rays], axis=1)
    inside = reach < length[rays] - 1e-6
    probes = []
    for ray in np.unique(rays[inside]):
        stops = np.sort(np.concatenate([[0.0], reach[(rays == ray) & inside], [length[ray]]]))
        probes.append(start[ray] + along[ray] * ((stops[:-1] + stops[1:]) / 2)[:, None])
    if not probes:
        return 0.0
    probes = np.vstack(probes)[:600]
    held = probes[b.geometry.mesh.contains(probes)]
    if not len(held):
        return 0.0
    return float(trimesh.proximity.closest_point(b.geometry.mesh, held)[1].max())


def mesh_depth(pair):
    """How deep (mm) the two parts' meshes sit in each other: a pin in its bore a tenth or two
    (their facets differ), a plate through a skin half the skin's thickness, more for more."""
    a, b = pair
    return max(_sunk(a, b), _sunk(b, a))


_PAIRS = []


def _crosses(index):
    return surfaces_cross(_PAIRS[index])


def _nears(index):
    return surfaces_near(_PAIRS[index])


def _depth(index):
    return mesh_depth(_PAIRS[index]) if surfaces_cross(_PAIRS[index]) else -1.0


def _over(pairs, measure):
    global _PAIRS
    _PAIRS = pairs
    if len(pairs) > 200:                                   # worth forking: the workers inherit the meshes
        with multiprocessing.get_context("fork").Pool(WORKERS) as pool:
            return pool.map(measure, range(len(pairs)), chunksize=16)
    return [measure(i) for i in range(len(pairs))]


def crossing_pairs(pairs):
    """The pairs of `pairs` whose meshes cross."""
    return [pair for pair, crossed in zip(pairs, _over(pairs, _crosses)) if crossed]


def near_crossing_pairs(pairs):
    """The pairs of `pairs` whose meshes cross or come within REACH of it."""
    return [pair for pair, near in zip(pairs, _over(pairs, _nears)) if near]


def crossing_depths(pairs):
    """[(pair, mm), ...] for the pairs whose meshes cross: how deep."""
    return [(pair, depth) for pair, depth in zip(pairs, _over(pairs, _depth)) if depth >= 0.0]


# ---------------------------------------------------------------------------------------------
# The kernel's part: how much volume two solids share
# ---------------------------------------------------------------------------------------------
def _relative(a, b):
    """b's link as a sees it: the transform that carries b's zero-pose solid into the frame
    of a's, as a rounded tuple (the key a measurement is remembered by)."""
    return tuple(np.round(np.linalg.inv(a.moved) @ b.moved, 6).ravel())


def _shared(a, b, relative):
    import build123d as bd
    from cad.build123d import overlap_volume

    m = np.array(relative).reshape(4, 4)
    there = bd.Plane(origin=tuple(m[:3, 3]), x_dir=tuple(m[:3, 0]), z_dir=tuple(m[:3, 2])).location
    return float(overlap_volume(a.solid, b.solid.moved(there)))


def _crew_member(tasks, results):
    resource.setrlimit(resource.RLIMIT_AS, (8 * 2 ** 30, 8 * 2 ** 30))     # a runaway boolean fails; it does not take the machine
    while True:
        task = tasks.get()
        if task is None:
            return
        index, relative = task
        results.put(("began", os.getpid(), index, None))
        a, b = _PAIRS[index]
        try:
            results.put(("done", os.getpid(), index, _shared(a, b, relative)))
        except BaseException as error:  # noqa: BLE001  (a kernel failure is a finding, not a crash)
            results.put(("done", os.getpid(), index, f"{type(error).__name__}: {str(error)[:120]}"))


_KNOWN = {}        # (part a, part b, how b sits to a) -> shared volume: a pair is measured once per relative placement


def shared_volumes(pairs, progress=None):
    """[(mm^3 or a failure's text, part a, part b), ...] for every pair: the kernel's exact
    intersection of the two solids where the current pose puts them. A pair that takes longer
    than PATIENCE, or kills its worker, comes back as a failure: unmeasured is not clear."""
    global _PAIRS
    keys = [(a.path, b.path, _relative(a, b)) for a, b in pairs]
    todo = [i for i, key in enumerate(keys) if key not in _KNOWN]
    _PAIRS = pairs
    if todo:
        context = multiprocessing.get_context("fork")
        tasks, results = context.Queue(), context.Queue()
        for i in todo:
            tasks.put((i, keys[i][2]))
        crew = {}

        def hire():
            member = context.Process(target=_crew_member, args=(tasks, results), daemon=True)
            member.start()
            crew[member.pid] = [member, None, 0.0]                 # the process, the pair it is on, since when

        for _ in range(min(WORKERS, len(todo))):
            hire()
        left, started = len(todo), time.time()
        while left:
            try:
                what, pid, index, value = results.get(timeout=1.0)
            except queue.Empty:
                what = None
            if what == "began" and pid in crew:
                crew[pid][1:] = [index, time.time()]
            elif what == "done":
                _KNOWN[keys[index]] = value
                left -= 1
                if pid in crew:
                    crew[pid][1] = None
                if progress and (len(todo) - left) % progress == 0:
                    print(f"  measured {len(todo) - left} of {len(todo)} pairs ({time.time() - started:.0f} s)", flush=True)
            for pid, (member, index, since) in list(crew.items()):
                overdue = index is not None and time.time() - since > PATIENCE
                if overdue or not member.is_alive():
                    if overdue:
                        os.kill(pid, signal.SIGKILL)
                    member.join()
                    del crew[pid]
                    if index is not None and keys[index] not in _KNOWN:
                        _KNOWN[keys[index]] = "gave up after %d s" % PATIENCE if overdue else "the kernel died on it"
                        left -= 1
                    if left:
                        hire()
        for _ in crew:
            tasks.put(None)
        for member, _, _ in crew.values():
            member.join(timeout=5)
    return [(_KNOWN[key], a.path, b.path) for key, (a, b) in zip(keys, pairs)]


def interferences(pairs, progress=None):
    """What of `pairs` interferes: [(mm^3, part a, part b), ...] sharing more than SHARED,
    largest first, and then the pairs that could not be measured, [(why, part a, part b), ...]."""
    measured = shared_volumes(pairs, progress)
    overlaps = sorted(((v, a, b) for v, a, b in measured if not isinstance(v, str) and v > SHARED), reverse=True)
    return overlaps, [(v, a, b) for v, a, b in measured if isinstance(v, str)]
