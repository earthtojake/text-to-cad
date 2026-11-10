"""Shared by Galatea's checks: the robot's parts as meshes, by link, posed by `lib.kin`,
and an interference test over them.

The meshes come from one GLB export of the model as built (the server's own tessellation,
each prototype once). A pose never goes back to the server: every link is a rigid body,
so `kin.link_transforms` places its meshes.

Two parts interfere when points just under one's surface lie inside the other. The test
samples each part's surface (its mesh vertices and triangle centres), so it finds a part
pushed into another by more than a millimetre or two (1.5 mm is the threshold: the meshes
facet a pin and its bore differently) and ignores parts that only touch; it reports how
deep the deepest point sits, not a volume. Exact booleans over the lofted
skins run a machine out of memory.
"""

import multiprocessing
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import trimesh  # noqa: E402

from lib import kin  # noqa: E402

INSET = 0.7          # test points sit this far under the surface, mm
PROBES = 4000        # at most this many test points per distinct part
GL_TO_CAD = np.array([[1000.0, 0, 0, 0], [0, 0, -1000.0, 0], [0, 1000.0, 0, 0], [0, 0, 0, 1]])   # a GLB node: metres, Y up


class Geometry:
    """One distinct mesh, in its own frame (millimetres), with its test points."""

    def __init__(self, name, mesh):
        mesh = mesh.copy()
        mesh.merge_vertices(merge_tex=True, merge_norm=True)
        # A sphere's pole or a loft's apex meshes as a few degenerate triangles; such a mesh
        # still answers "is this point inside" by ray casting, so it counts as closed.
        _, counts = np.unique(mesh.edges_sorted, axis=0, return_counts=True)
        self.name, self.mesh, self.watertight = name, mesh, int((counts != 2).sum()) <= 8
        points = np.vstack([mesh.vertices - INSET * mesh.vertex_normals, mesh.triangles_center - INSET * mesh.face_normals])
        if len(points) > PROBES:
            points = points[np.random.default_rng(0).choice(len(points), PROBES, replace=False)]
        self.probes = points
        lo, hi = mesh.bounds
        self.corners = np.array([[x, y, z] for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])])


class Part:
    def __init__(self, link, path, geometry, placed):
        self.link, self.path, self.geometry = link, path, geometry
        self.rest = GL_TO_CAD @ placed            # its frame -> the world at the zero pose, mm
        self.world = self.rest
        self._box()

    def pose(self, link_matrix):
        self.world = link_matrix @ self.rest
        self._box()

    def _box(self):
        corners = self.geometry.corners @ self.world[:3, :3].T + self.world[:3, 3]
        self.lo, self.hi = corners.min(axis=0), corners.max(axis=0)


def load_parts(handle):
    """{link: [Part, ...]} for the model `handle` (a model call's handle) as built."""
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
        print(f"note: {len(open_meshes)} meshes are not closed and are tested as probes only: {open_meshes[:8]}")
    return links


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


def _depth_inside(a, b):
    """How deep (mm) the deepest of a's test points sits inside b."""
    if not b.geometry.watertight:
        return 0.0
    carry = np.linalg.inv(b.world) @ a.world                      # a's frame -> b's frame
    points = a.geometry.probes @ carry[:3, :3].T + carry[:3, 3]
    lo, hi = b.geometry.mesh.bounds
    near = points[np.all((points >= lo) & (points <= hi), axis=1)]
    if not len(near):
        return 0.0
    inside = near[b.geometry.mesh.contains(near)]
    if not len(inside):
        return 0.0
    _, distance, _ = trimesh.proximity.closest_point(b.geometry.mesh, inside[:300])
    return float(distance.max()) + INSET


def part_depth(a, b):
    """Penetration depth (mm) between two parts: 0 when they are apart or only touch."""
    if not boxes_meet(a.lo, a.hi, b.lo, b.hi):
        return 0.0
    return max(_depth_inside(a, b), _depth_inside(b, a))


def link_box(parts):
    return np.min([p.lo for p in parts], axis=0), np.max([p.hi for p in parts], axis=0)


_PAIRS = []


def _measure(index):
    a, b = _PAIRS[index]
    return part_depth(a, b)


def interferences(links, within=True, between=True, threshold=1.5, skip=None):
    """[(depth mm, part a, part b), ...] deeper than `threshold`."""
    global _PAIRS
    pairs, names = [], list(links)
    if within:
        for name in names:
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
    _PAIRS = pairs
    if len(pairs) > 200:                                   # worth forking: the workers inherit the meshes
        with multiprocessing.get_context("fork").Pool(min(4, os.cpu_count() or 1)) as pool:
            depths = pool.map(_measure, range(len(pairs)), chunksize=16)
    else:
        depths = [_measure(i) for i in range(len(pairs))]
    return sorted(((depth, a.path, b.path) for depth, (a, b) in zip(depths, pairs) if depth > threshold), reverse=True)
