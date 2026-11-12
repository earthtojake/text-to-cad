"""Turning a maker's assembly STEP into links: the geometry a careful engineer reads off the CAD.

A vendor STEP is a tree of occurrences: printed parts, bought parts (servos, each a sub-assembly of
its housing, motor, gears and horns), fasteners and boards. A robot description wants links: rigid
sets of parts. The one human input is which printed parts form which link (``printed``: link name ->
the occurrence names); every other leaf is put on a link by GEOMETRY here:

- ``leaves(tree)``: every leaf solid of the tree with its world placement and path;
- ``mesh(shape)``: a leaf's triangles (OCCT's mesher), for proximity queries;
- ``contacts(points, printed)``: how many of a leaf's surface samples touch each link's printed
  parts (within ``touch`` mm). A leaf goes to the link it touches most: a screw to the part it is
  driven into, a nut to the part it sits in, a servo housing to the holder that clamps it, a horn to
  the part screwed onto it (``assign``);
- ``cylinder_axes(shape)``: a leaf's cylindrical faces, each as (radius, point, direction, area),
  from OCCT's own surface (``BRepAdaptor_Surface``), so a servo horn's rim gives the output axis.

Nothing here builds or names a model: ``so101.py`` calls it. Kernel objects are made inside the
functions, never at module level (the cad skill's model contract).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np


@dataclass
class Leaf:
    """A leaf solid of the STEP: its path of labels from the root, the shape as read (its own frame)
    and its world placement (a build123d Location)."""

    path: tuple[str, ...]
    shape: Any
    world: Any
    link: str | None = None
    why: str = ""
    touches: dict[str, int] = field(default_factory=dict)

    @property
    def name(self) -> str:
        return self.path[-1]

    @property
    def top(self) -> str:
        """The occurrence directly under the root: the part or sub-assembly the leaf belongs to."""
        return self.path[1] if len(self.path) > 1 else self.path[0]

    def placed(self) -> Any:
        """The leaf where it stands in the assembly: a new object, placed, out of the tree.

        build123d's ``located`` deep-copies the node WITH its parent, so the whole read tree is copied
        for every leaf (and, outside the engine, every B-rep in it: 7 s and 400 MB a call here). The
        copy below maps the parent to None, so only the leaf is copied (in the engine, a new handle on
        the same B-rep: one prototype however many placements)."""
        import copy

        parent = self.shape.parent
        found = copy.deepcopy(self.shape, {} if parent is None else {id(parent): None})
        found.locate(self.world)
        return found


def leaves(tree: Any) -> list[Leaf]:
    """Every leaf of ``tree`` holding a solid, in tree order, with its world placement."""
    import build123d as bd

    found: list[Leaf] = []

    def walk(node: Any, parent: Any, path: tuple[str, ...]) -> None:
        world = parent * node.location
        children = list(node.children)
        here = path + (node.label or "",)
        if not children:
            if node.solids():
                found.append(Leaf(here, node, world))
            return
        for child in children:
            walk(child, world, here)

    walk(tree, bd.Location(), ())
    return found


def mesh(shape: Any, deflection: float = 0.2, angle: float = 0.3) -> tuple[np.ndarray, np.ndarray]:
    """A shape's triangles where it stands (its location applied): ``(vertices (n, 3), faces (m, 3))``.
    A face the mesher leaves empty is skipped."""
    from OCP.BRep import BRep_Tool
    from OCP.BRepMesh import BRepMesh_IncrementalMesh
    from OCP.TopAbs import TopAbs_FACE, TopAbs_REVERSED
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopLoc import TopLoc_Location
    from OCP.TopoDS import TopoDS

    wrapped = shape.wrapped
    BRepMesh_IncrementalMesh(wrapped, deflection, False, angle, True)
    vertices, faces, offset = [], [], 0
    explorer = TopExp_Explorer(wrapped, TopAbs_FACE)
    while explorer.More():
        face = TopoDS.Face(explorer.Current())
        location = TopLoc_Location()
        triangulation = BRep_Tool.Triangulation_s(face, location)
        explorer.Next()
        if triangulation is None:
            continue
        transform = location.Transformation()
        nodes = np.array([[p.X(), p.Y(), p.Z()] for p in
                          (triangulation.Node(i).Transformed(transform) for i in range(1, triangulation.NbNodes() + 1))])
        tris = np.array([triangulation.Triangle(i).Get() for i in range(1, triangulation.NbTriangles() + 1)]) - 1
        if face.Orientation() == TopAbs_REVERSED:
            tris = tris[:, ::-1]
        vertices.append(nodes)
        faces.append(tris + offset)
        offset += len(nodes)
    if not vertices:
        return np.zeros((0, 3)), np.zeros((0, 3), dtype=int)
    return np.vstack(vertices), np.vstack(faces).astype(int)


def surface_samples(vertices: np.ndarray, faces: np.ndarray, count: int, seed: int = 1) -> np.ndarray:
    """``count`` points spread over a mesh's surface by area (a fixed seed: the same points every run)."""
    if len(faces) == 0:
        return vertices
    a, b, c = (vertices[faces[:, i]] for i in range(3))
    areas = 0.5 * np.linalg.norm(np.cross(b - a, c - a), axis=1)
    rng = np.random.default_rng(seed)
    picked = rng.choice(len(faces), size=count, p=areas / areas.sum())
    u, v = rng.random(count), rng.random(count)
    flip = u + v > 1
    u[flip], v[flip] = 1 - u[flip], 1 - v[flip]
    return a[picked] + u[:, None] * (b[picked] - a[picked]) + v[:, None] * (c[picked] - a[picked])


class Printed:
    """The printed parts by link, as dense samples of their surfaces in a KD-tree (scipy), for
    proximity queries: a point is within ``touch`` of a part when a sample of the part is. The
    samples are spaced finer than ``touch`` (``density`` per mm^2), so the answer is within a
    fraction of it of the exact distance, at a small fraction of the memory a triangle query takes."""

    def __init__(self, parts: list[tuple[str, Leaf]], deflection: float = 0.2, density: float = 12.0) -> None:
        from scipy.spatial import cKDTree

        points, owners = [], []
        self.links: list[str] = []
        for link, leaf in parts:
            vertices, faces = mesh(leaf.placed(), deflection)
            a, b, c = (vertices[faces[:, i]] for i in range(3))
            area = float(0.5 * np.linalg.norm(np.cross(b - a, c - a), axis=1).sum())
            sampled = np.vstack([vertices, surface_samples(vertices, faces, int(area * density))])
            if link not in self.links:
                self.links.append(link)
            points.append(sampled)
            owners.append(np.full(len(sampled), self.links.index(link)))
        self.owner = np.concatenate(owners)
        self.tree = cKDTree(np.vstack(points))

    def contacts(self, points: np.ndarray, touch: float) -> dict[str, int]:
        """How many of ``points`` lie within ``touch`` mm of each link's printed parts (a point near
        two links counts for both)."""
        found: dict[str, int] = {}
        for at, near in enumerate(self.tree.query_ball_point(points, touch)):
            for link in {int(self.owner[i]) for i in near}:
                found[self.links[link]] = found.get(self.links[link], 0) + 1
        return found


def assign(leaf: Leaf, printed: Printed, *, samples: int = 300, touch: float = 0.5,
           exclude: tuple[str, ...] = ()) -> str | None:
    """The link ``leaf`` touches most (its surface samples within ``touch`` mm of a link's printed
    parts), leaving out the links in ``exclude``; None when it touches none. Records the counts on
    the leaf."""
    vertices, faces = mesh(leaf.placed(), 0.3)
    points = surface_samples(vertices, faces, samples)
    leaf.touches = printed.contacts(points, touch)
    ranked = sorted(((count, link) for link, count in leaf.touches.items() if link not in exclude), reverse=True)
    return ranked[0][1] if ranked else None


def cylinder_axes(shape: Any) -> list[tuple[float, np.ndarray, np.ndarray, float]]:
    """A shape's cylindrical faces where it stands: (radius, a point on the axis, the axis direction,
    the face's area), the largest radius first."""
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_Cylinder

    found = []
    for face in shape.faces():
        surface = BRepAdaptor_Surface(face.wrapped)
        if surface.GetType() != GeomAbs_Cylinder:
            continue
        cylinder = surface.Cylinder()
        axis = cylinder.Axis()
        at, direction = axis.Location(), axis.Direction()
        found.append((cylinder.Radius(), np.array([at.X(), at.Y(), at.Z()]),
                      np.array([direction.X(), direction.Y(), direction.Z()]), face.area))
    return sorted(found, key=lambda row: (-round(row[0], 3), -row[3]))


def centroid(shape: Any) -> np.ndarray:
    """A shape's centre of volume where it stands (mm)."""
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps

    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape.wrapped, props)
    at = props.CentreOfMass()
    return np.array([at.X(), at.Y(), at.Z()])


def volume_and_area(shape: Any) -> tuple[float, float]:
    """A shape's volume (mm^3) and surface area (mm^2)."""
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps

    volume, area = GProp_GProps(), GProp_GProps()
    BRepGProp.VolumeProperties_s(shape.wrapped, volume)
    BRepGProp.SurfaceProperties_s(shape.wrapped, area)
    return volume.Mass(), area.Mass()


def printed_density(volume: float, area: float, *, solid: float, shell: float, infill: float) -> float:
    """The effective density (kg/m^3) of an FDM print of a part of ``volume`` (mm^3) and surface
    ``area`` (mm^2): a solid skin ``shell`` mm thick under every surface (perimeters on the sides,
    solid layers top and bottom) and ``infill`` (a fraction) of the material in the rest. The skin is
    ``area * shell`` of it, all of a part thinner than twice the shell. ``solid`` is the filament's
    density (kg/m^3)."""
    skin = min(1.0, area * shell / volume)
    return solid * (skin + infill * (1.0 - skin))


def nearest_link(leaf: Leaf, printed: Printed) -> tuple[str, float]:
    """The link of the printed part nearest ``leaf`` (its surface samples' nearest sample of a
    printed part) and that distance (mm): the fallback for a leaf that touches none."""
    vertices, faces = mesh(leaf.placed(), 0.5, 0.5)
    points = surface_samples(vertices, faces, 200)
    distance, index = printed.tree.query(points)
    best = int(np.argmin(distance))
    return printed.links[int(printed.owner[index[best]])], float(distance[best])
