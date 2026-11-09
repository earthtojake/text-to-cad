"""MJCF: a document as a MuJoCo model, written from its robot description (``description.py``).

``write(view, path)`` describes the document (``describe``) and writes it; ``write_description``
writes a description it is handed (the tests', ``cad.mujoco.spec``'s). The file is one MJCF at
``path`` and its meshes beside it, binary STLs in metres in ``<path.parent>/<assets>/``, each named
``<model>_<mesh>.stl``: a prototype's triangles once however many links place it, the header naming
it, the triangles in the mesh's order, each normal from its corners, so the same description writes
the same bytes. Nothing here imports MuJoCo: the writer is text and numpy (law 3).

The XML is laid out as MuJoCo Menagerie lays a robot out, so a scene includes or attaches it as it
does one of theirs: ``compiler`` (radians, the mesh folder, ``autolimits``), ``option`` (the
``implicitfast`` integrator MuJoCo's guide recommends; a scene that attaches the model keeps its own),
``default`` (a class named for the model holding ``visual``, group 2 and colliding with nothing, and
``collision``, group 3: MuJoCo prefixes every class of an attached model, so the classes survive an
attach), ``asset`` (a ``material`` per distinct material name and colour, a ``mesh`` per prototype),
``worldbody``, ``contact``, ``equality`` and ``keyframe``.

``worldbody`` is the description's tree from its root: the ground's geometry in the world itself
when the ground is MuJoCo's ``world``, else a body of its own with no joint; every other link a body
at its joint's origin, which is the link's frame (the description's rule), so a joint stands at its
body's origin on its Z (``axis="0 0 1"``) with ``ref`` zero. A revolute is a ``hinge`` with its
range, a continuous one a hinge without; a prismatic a ``slide``; a cylindrical a hinge and a slide
on one body (``<name>`` and ``<name>/slide``); a spherical a ``ball``; a floating one (a base declared
``cad.build123d.free``) a ``freejoint``, its body a child of the world's; a fixed one no joint, so a part
declared a body (``cad.build123d.body``) is a child ``<body>`` of its link's with none. A joint's drive
effort (``cad.build123d.limits``) is its ``actuatorfrcrange``, ``-effort effort`` (N*m, N), which bounds
what any actuator on it applies; MJCF has no bound on a joint's speed, so a drive's velocity is not
written (an actuator's own ``ctrlrange`` is the scene's). A joint's dynamics are its ``armature``,
``damping`` and ``frictionloss`` (``limits``' ``armature``, ``damping`` and ``friction``), each where
declared; an actuator, its gains and contact tuning are the scene's. A link's
``inertial`` is written on its principal axes (a tensor whose moments miss MuJoCo's triangle
inequality by rounding alone is nudged onto it; any further and MuJoCo says so); a link with none is
given none, and MuJoCo computes one from its geoms (visual and collision alike). A visual is a geom
of class ``visual``, a collision one of class ``collision`` named ``<part>_collision`` where its
visual holds the part's name: a mesh, which MuJoCo hulls, or a primitive in MuJoCo's half sizes (a
box's half extents, a sphere's radius, a cylinder's or a capsule's radius and half its length, the
capsule's length its cylinder's, as ``describe`` fits it); a decomposed part (``cad.build123d.collision(part,
"decomposed")``) is a ``collision`` geom per convex hull, ``<part>_hull<i>``, each of the mesh asset of that
name, a file of its own (``<model>_<part>_hull<i>.stl``), while its visual is the part whole. Each has its
``friction`` the part's
contact friction (``cad.build123d.friction``: the sliding coefficient alone, the torsional and rolling
then MuJoCo's defaults, or all three) where it declares one, none where it does not, so MuJoCo's
default (or a scene's ``default`` class) holds; a named frame a ``site``.
Every name is unique in its kind -- bodies among bodies, joints among joints, MuJoCo's namespaces, so a
body and a joint may share one -- a repeat given ``_2``, ``_3`` and said (``export.note``). ``contact``
excludes each body pair that touches at rest across a joint that moves (``export/contact.py``'s rule:
MuJoCo's ``filterparent`` passes the pair at a robot's first joint, whose parent is welded to the
world) and each pair the model declares (``cad.build123d.exclude``), in that order, each once. A coupling is an
``equality`` of the follower on its leader (``polycoef`` its offset and ratio); a virtual pinion's racks follow
the first of them (the description has no pinion), so the file holds the one control the hardware has.

**Loops.** A joint that closes a loop (``description``'s **Loops**: a ``Closure``) is no joint of the tree:
it is a ``site`` on each of its two bodies at the joint's frame, ``<name>/1`` on the parent's and
``<name>/2`` on the child's, which coincide as built, and ``connect`` equalities of sites, named for the
joint. A ball is one ``connect`` (the point held: three constraints). A turn is two: the sites, and a
second pair ``AXIS_SPAN`` along the axis (``<name>/1_axis``, ``<name>/2_axis``, the ``connect``
``<name>/axis``), so the point and the axis's direction are held and the turn about it is free: six rows,
five of them independent, a hinge. A ``weld`` would hold the turn too, and one with ``torquescale="0"``
would free every turn, a ball. In a planar loop some rows repeat what the tree's parallel hinges hold
already; MuJoCo's constraints are soft, so a redundant row costs the solver a row and nothing else. MuJoCo
has no slide equality, so a slide never closes a loop here: the description closes the loop at its turn
or ball nearest the slide, and a loop with neither is refused by name. The closing joint's range is not
enforced (an equality has none), and the export says so where it has one; ``contact`` excludes its two
bodies where they touch at rest, as it does a joint's.

A pose is a ``key``, its ``qpos`` in MuJoCo's joint order (a ball's a unit quaternion from the three
angles, x then y then z as the pair turns, a cylindrical's turn then slide, a free joint's its body's
position and quaternion where the description places it at zero), a joint it does not name at zero, a
follower where its leader puts it.

**The scene.** An export (``write``) to ``<dir>/<name>.xml`` writes ``<dir>/scene.xml`` beside it where
there is none, as MuJoCo Menagerie ships one beside each robot: it ``include``s the robot's file and adds
a ``statistic`` (the robot's centre and extent at zero, so a viewer frames it), Menagerie's ``visual``
(headlight, haze, camera angle), a gradient skybox, a checker ground ``plane`` and a light, all MuJoCo's
built-in textures, so the scene is one file. The plane is at ``z = 0``, or at the robot's lowest point
where it reaches below. A ``scene.xml`` that is there is the person's and is never written over: the
export says when it wrote one (``export.note``), and of one that is there says nothing, unless it includes
no file of the robot's name, so shows another robot. The robot's file is the one an export
writes again; the scene is the person's to edit. An export named ``scene.xml`` writes no scene.

Numbers are written short and the same every time: nine significant digits at most, ``-0`` as ``0``,
a length or an angle within 1e-12 of zero as zero (the rounding of a product of frames). The file and its
meshes are staged beside the target and moved into place, each only where its bytes changed; the mesh
folder moves in whole when there is none, else each mesh moves into it, and nothing else in it is
touched (a scene's own assets may share it).
"""

from __future__ import annotations

import hashlib
import math
import re
import struct
from collections.abc import Iterable
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

import numpy as np

from cad.engine.atomic_replace import replace_atomic, same_bytes, staging
from cad.engine.description import Description, DescriptionError, Geometry, Joint, Link
from cad.engine.export import ExportRefused, note

__all__ = ["SCENE", "digest", "rendered", "scene", "write", "write_description"]

#: The moments a principal inertia may miss the triangle inequality by and be nudged onto it, kg*m^2.
NUDGE = 1e-9
#: A length or an angle this near zero is zero: what a product of rotations leaves of one.
SNAP = 1e-12
#: How far along a turn that closes a loop its second pair of sites stands, metres (the module's **Loops**).
AXIS_SPAN = 0.1
#: The scene an export writes beside the robot where there is none (the module's **The scene**).
SCENE = "scene.xml"
_RECORD = np.dtype([("normal", "<f4", 3), ("corners", "<f4", (3, 3)), ("attribute", "<u2")])


def write(view: Any, path: Path) -> None:
    """The export ``Kind``'s writer: ``view``'s document described (at its ``zero``, where it has one) and
    written to ``path``, with a scene beside it where there is none (the module's **The scene**); what it
    holds said (``export.described``)."""
    from cad.engine.describe import describe
    from cad.engine.export import described

    description = describe(view, zero=getattr(view, "zero", None))
    for text in description.warnings:
        note(text)
    write_description(description, path, scene=True)
    described(description.summary("mjcf"))


def write_description(description: Description, path: Any, *, assets: str = "assets",
                      scene: bool = False) -> list[Path]:
    """Write ``description`` as an MJCF at ``path`` and its meshes in ``<path.parent>/<assets>``, and, given
    ``scene``, a ``scene.xml`` beside it where there is none (the module's **The scene**); the files it
    wrote, the MJCF first."""
    path = Path(path)
    text, files = rendered(description, assets)
    written = place(path, text, files, assets)
    if scene and path.name.lower() != SCENE:
        beside = path.parent / SCENE
        if beside.exists():
            if not _includes(beside, path):
                note(f"the existing {SCENE} beside it includes no {path.name}, so it shows another robot: it is "
                     f"yours to edit, and an export never writes over it")
        else:
            from cad.engine.atomic_replace import put

            put(beside, lambda temporary: Path(temporary).write_text(scene_of(description, path.name), encoding="utf-8"))
            note(f"wrote {SCENE} beside it: a floor and a light around the robot, yours to edit (an export never "
                 "writes over it)")
            written.append(beside)
    return written


def _includes(scene: Path, robot: Path) -> bool:
    """Whether the MJCF ``scene`` includes the file ``robot`` (an ``include`` naming it, relative to the scene's
    folder, as MuJoCo resolves one); False for a scene that does not read as XML."""
    import xml.etree.ElementTree as ElementTree

    try:
        root = ElementTree.parse(scene).getroot()
    except (OSError, ElementTree.ParseError):
        return False
    wanted = robot.resolve()
    return any((scene.parent / found).resolve() == wanted
               for found in (element.get("file") for element in root.iter("include")) if found)


def scene_of(description: Description, robot: str) -> str:
    """A Menagerie scene that includes the MJCF ``robot`` (a file name beside it) of ``description`` (the
    module's **The scene**)."""
    low, high = _bounds(description)
    centre, extent = (low + high) / 2, max(float(np.linalg.norm(high - low)), 0.1)
    floor = float(low[2]) if low[2] < -1e-6 else 0.0  # a micron's rounding below the origin is on it
    level = "" if floor == 0 else f' pos="0 0 {_number(floor)}"'
    lines = [
        f'<mujoco model="{escape(description.name, {chr(34): "&quot;"})} scene">',
        f'  <include file="{escape(robot, {chr(34): "&quot;"})}"/>',
        "",
        f'  <statistic center="{_numbers(centre)}" extent="{_number(extent)}"/>',
        "",
        "  <visual>",
        '    <headlight diffuse="0.6 0.6 0.6" ambient="0.3 0.3 0.3" specular="0 0 0"/>',
        '    <rgba haze="0.15 0.25 0.35 1"/>',
        '    <global azimuth="120" elevation="-20"/>',
        "  </visual>",
        "",
        "  <asset>",
        '    <texture type="skybox" builtin="gradient" rgb1="0.3 0.5 0.7" rgb2="0 0 0" width="512" height="3072"/>',
        '    <texture type="2d" name="groundplane" builtin="checker" mark="edge" rgb1="0.2 0.3 0.4" '
        'rgb2="0.1 0.2 0.3" markrgb="0.8 0.8 0.8" width="300" height="300"/>',
        '    <material name="groundplane" texture="groundplane" texuniform="true" texrepeat="5 5" '
        'reflectance="0.2"/>',
        "  </asset>",
        "",
        "  <worldbody>",
        f'    <light pos="{_numbers((centre[0], centre[1], floor + max(1.5, 2 * extent)))}" dir="0 0 -1" '
        'directional="true"/>',
        f'    <geom name="floor"{level} size="0 0 0.05" type="plane" material="groundplane"/>',
        "  </worldbody>",
        "</mujoco>",
    ]
    return "\n".join(lines) + "\n"


def _bounds(description: Description) -> tuple[np.ndarray, np.ndarray]:
    """The box around the description's visuals at zero, in metres (a unit box at the origin where it has none)."""
    found: list[np.ndarray] = []
    for link in description.links:
        frame = np.asarray(link.frame, dtype=float)
        for visual in link.visuals:
            geometry = visual.geometry
            placed = frame @ np.asarray(geometry.placement, dtype=float)
            if geometry.kind == "mesh" and geometry.mesh in description.meshes:
                points = np.asarray(description.meshes[geometry.mesh].positions, dtype=float).reshape(-1, 3)
                points = points * float(geometry.scale)
            else:
                reach = max([float(value) for value in geometry.size] or [0.0])
                points = np.array([[x, y, z] for x in (-reach, reach) for y in (-reach, reach) for z in (-reach, reach)])
            if len(points):
                found.append(points @ placed[:3, :3].T + placed[:3, 3])
    if not found:
        return np.full(3, -0.05), np.full(3, 0.05)
    every = np.concatenate(found)
    return every.min(axis=0), every.max(axis=0)


def digest(text: str, files: dict[str, bytes]) -> str:
    """What a rendering holds, as a hex digest: the MJCF and every mesh, by name."""
    found = hashlib.sha256(text.encode("utf-8"))
    for name in sorted(files):
        found.update(b"\0" + name.encode("utf-8") + b"\0" + files[name])
    return found.hexdigest()


def place(path: Path, text: str, files: dict[str, bytes], assets: str) -> list[Path]:
    """A rendering moved into place: staged beside ``path``, the meshes first and the MJCF last, so a
    reader of the MJCF finds every mesh it names; each file only where its bytes changed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    folder = path.parent / assets
    written = [path] + [folder / name for name in files]
    with staging(path) as staged:
        held = staged.parent / "assets"
        held.mkdir()
        for name, data in files.items():
            (held / name).write_bytes(data)
        staged.write_bytes(text.encode("utf-8"))
        if files and not folder.exists():
            folder.parent.mkdir(parents=True, exist_ok=True)
            replace_atomic(held, folder)
        else:
            folder.mkdir(parents=True, exist_ok=True)
            for name in files:
                if not same_bytes(folder / name, held / name):
                    replace_atomic(held / name, folder / name)
        if not same_bytes(path, staged):
            replace_atomic(staged, path)
    return written


# --- the rendering ---------------------------------------------------------------------------------


def rendered(description: Description, assets: str = "assets") -> tuple[str, dict[str, bytes]]:
    """``description`` as MJCF text and its mesh files' bytes by file name, nothing written."""
    for closure in description.closures:
        if closure.kind in ("prismatic", "cylindrical"):
            raise ExportRefused(f"{description.name}: joint {closure.name!r} closes the loop through "
                                f"{', '.join(closure.loop)} and slides, and MuJoCo has no slide equality: an MJCF "
                                "closes a loop at a turn or a ball, which this loop has none of")
    try:
        description.check()
    except DescriptionError as error:
        raise ExportRefused(f"{description.name}: {error}") from error
    return _Writer(description, assets).render()


class _Names:
    """Names unique within one of MuJoCo's namespaces: a repeat gets ``_2``, ``_3``, ..."""

    def __init__(self) -> None:
        self.taken: set[str] = set()

    def __call__(self, wanted: str) -> str:
        name, at = wanted, 1
        while name in self.taken:
            at += 1
            name = f"{wanted}_{at}"
        self.taken.add(name)
        return name


class _Element:
    def __init__(self, tag: str, attributes: Iterable[tuple[str, str | None]] = (), children: list | None = None):
        self.tag = tag
        self.attributes = [(key, value) for key, value in attributes if value is not None]
        self.children = children if children is not None else []

    def add(self, tag: str, attributes: Iterable[tuple[str, str | None]] = ()) -> _Element:
        child = _Element(tag, attributes)
        self.children.append(child)
        return child

    def lines(self, depth: int) -> list[str]:
        indent = "  " * depth
        opened = indent + "<" + self.tag + "".join(f' {key}="{escape(value, {chr(34): "&quot;"})}"'
                                                    for key, value in self.attributes)
        if not self.children:
            return [opened + "/>"]
        found = [opened + ">"]
        for child in self.children:
            found.extend(child.lines(depth + 1))
        return found + [f"{indent}</{self.tag}>"]


class _Writer:
    def __init__(self, description: Description, assets: str) -> None:
        self.description = description
        self.assets = assets
        self.geoms, self.sites, self.materials_named, self.meshes_named = _Names(), _Names(), _Names(), _Names()
        self.files_named = _Names()
        # Bodies and joints, each its own namespace (MuJoCo's): a body and a joint may share a name.
        self.bodies, self.joints = _Names(), _Names()
        self.body_of: dict[str, str] = {}
        self.materials: dict[tuple, str] = {}
        self.material_rows: list[tuple[str, tuple]] = []
        self.meshes: dict[tuple[str, float], str] = {}
        self.mesh_rows: list[tuple[str, str, float]] = []
        self.files: dict[str, bytes] = {}
        self.mesh_files: dict[str, str] = {}  # each mesh's file, by its key: written once however it is scaled
        self.qpos: list[tuple[Joint, int]] = []  # each moving joint and how many values it holds, in MuJoCo's order
        self.joint_names: dict[str, str] = {}  # each moving joint's written name, by the description's
        # Each link's closure sites (the module's **Loops**): (closure, which, its frame in the link's), and each
        # site's written name by (closure, which).
        self.closure_sites: dict[str, list[tuple[str, str, np.ndarray]]] = {}
        self.closure_named: dict[tuple[str, str], str] = {}
        for closure in description.closures:
            along = np.eye(4)
            along[2, 3] = AXIS_SPAN
            hinge = closure.kind in ("revolute", "continuous")
            for which, link, frame in (("1", closure.parent, closure.origin), ("2", closure.child, closure.frame)):
                frame = np.asarray(frame, dtype=float)
                rows = self.closure_sites.setdefault(link, [])
                rows.append((closure.name, which, frame))
                if hinge:
                    rows.append((closure.name, f"{which}_axis", frame @ along))

    def render(self) -> tuple[str, dict[str, bytes]]:
        d = self.description
        world = _Element("worldbody")
        root = d.root
        if root.name == "world":
            self.body_of[root.name] = self.bodies("world")
            self._content(world, root, np.asarray(root.frame, dtype=float))
            for joint in d.children(root.name):
                self._body(world, joint, childclass=d.name)
        else:
            body = world.add("body", [("name", self._named(root.name)), ("childclass", d.name),
                                      *_placement(root.frame)])
            self._content(body, root, np.eye(4))
            for joint in d.children(root.name):
                self._body(body, joint)
        sections = [
            _Element("compiler", [("angle", "radian"), ("meshdir", self.assets), ("autolimits", "true")]),
            _Element("option", [("integrator", "implicitfast")]),
            self._default(),
        ]
        asset = _Element("asset")
        for name, rgba in self.material_rows:
            asset.add("material", [("name", name), ("rgba", _numbers(rgba, snap=0))])
        for name, file, scale in self.mesh_rows:
            asset.add("mesh", [("name", name), ("file", file),
                               ("scale", _numbers((scale,) * 3, snap=0) if scale != 1 else None)])
        if asset.children:
            sections.append(asset)
        sections.append(world)
        contact = self._contact()
        if contact.children:
            sections.append(contact)
        equality = self._equality()
        if equality.children:
            sections.append(equality)
        keyframe = self._keyframe()
        if keyframe.children:
            sections.append(keyframe)
        top = _Element("mujoco", [("model", d.name)], sections)
        lines = [top.lines(0)[0]]
        for at, section in enumerate(sections):
            if at:
                lines.append("")
            lines.extend(section.lines(1))
        lines.append("</mujoco>")
        return "\n".join(lines) + "\n", self.files

    def _default(self) -> _Element:
        default = _Element("default")
        own = default.add("default", [("class", self.description.name)])
        own.add("default", [("class", "visual")]).add("geom", [("contype", "0"), ("conaffinity", "0"), ("group", "2")])
        own.add("default", [("class", "collision")]).add("geom", [("group", "3")])
        return default

    def _named(self, link: str) -> str:
        """A link's body name, unique among bodies; a rename said."""
        found = self.body_of[link] = self.bodies(link)
        if found != link:
            note(f"body {link!r} is written {found!r}: another body holds its name")
        return found

    def _joint_name(self, wanted: str) -> str:
        found = self.joints(wanted)
        if found != wanted:
            note(f"joint {wanted!r} is written {found!r}: another joint holds its name")
        return found

    def _body(self, parent: _Element, joint: Joint, childclass: str | None = None) -> None:
        link = self.description.link(joint.child)
        body = parent.add("body", [("name", self._named(link.name)), ("childclass", childclass),
                                   *_placement(joint.origin)])
        if link.inertial is not None:
            body.children.append(_inertial(link))
        self._joint(body, joint)
        self._content(body, link, np.eye(4))
        for child in self.description.children(link.name):
            self._body(body, child)

    def _joint(self, body: _Element, joint: Joint) -> None:
        def ranged(index: int) -> str | None:
            if index >= len(joint.limits):
                return None
            lower, upper = joint.limits[index]
            return None if lower is None or upper is None else _numbers((lower, upper))

        axis = ("axis", "0 0 1")
        if joint.kind == "fixed":
            return
        name = self.joint_names[joint.name] = self._joint_name(joint.name)
        effort = ("actuatorfrcrange", None if joint.effort is None else _numbers((-joint.effort, joint.effort), snap=0))
        dynamics = [(key, None if value is None else _number(value, snap=0)) for key, value in (
            ("armature", joint.armature), ("damping", joint.damping), ("frictionloss", joint.friction))]
        if joint.kind in ("revolute", "continuous"):
            body.add("joint", [("name", name), ("type", "hinge"), axis,
                               ("range", ranged(0) if joint.kind == "revolute" else None), effort, *dynamics])
            self.qpos.append((joint, 1))
        elif joint.kind == "prismatic":
            body.add("joint", [("name", name), ("type", "slide"), axis, ("range", ranged(0)), effort, *dynamics])
            self.qpos.append((joint, 1))
        elif joint.kind == "cylindrical":
            body.add("joint", [("name", name), ("type", "hinge"), axis, ("range", ranged(0))])
            body.add("joint", [("name", self._joint_name(f"{name}/slide")), ("type", "slide"), axis,
                               ("range", ranged(1))])
            self.qpos.append((joint, 2))
        elif joint.kind == "spherical":
            body.add("joint", [("name", name), ("type", "ball")])
            self.qpos.append((joint, 4))
        elif joint.kind == "floating":
            body.add("freejoint", [("name", name)])
            self.qpos.append((joint, 7))

    def _content(self, body: _Element, link: Link, frame: np.ndarray) -> None:
        """A link's geoms and sites, each placed in ``body``'s frame (``frame`` the link's in it)."""
        for visual in link.visuals:
            colour = tuple(float(value) for value in visual.color)
            painted: list[tuple[str, str | None]]
            if visual.material:
                painted = [("material", self._material(visual.material, colour))]
            else:
                painted = [("rgba", _numbers(colour, snap=0))]
            body.add("geom", [("class", "visual"), *self._shape(visual.geometry), ("name", self.geoms(visual.name)),
                              *painted, *_placement(frame @ visual.geometry.placement)])
        for collision in link.collisions:
            # A part's collision shares its visual's name: it is told apart as Menagerie tells them.
            named = collision.name if collision.name not in self.geoms.taken else f"{collision.name}_collision"
            body.add("geom", [("class", "collision"), *self._shape(collision.geometry), ("name", self.geoms(named)),
                              ("friction", _numbers(collision.friction, snap=0) if collision.friction else None),
                              *_placement(frame @ collision.geometry.placement)])
        for name, placed in link.frames.items():
            body.add("site", [("name", self.sites(name)), *_placement(frame @ np.asarray(placed, dtype=float))])
        for closure, which, placed in self.closure_sites.get(link.name, ()):
            named = self.closure_named[(closure, which)] = self.sites(f"{closure}/{which}")
            body.add("site", [("name", named), *_placement(frame @ placed)])

    def _shape(self, geometry: Geometry) -> list[tuple[str, str | None]]:
        size = [float(value) for value in geometry.size]
        if geometry.kind == "mesh":
            return [("type", "mesh"), ("mesh", self._mesh(str(geometry.mesh), float(geometry.scale)))]
        if geometry.kind == "box":
            return [("type", "box"), ("size", _numbers([value / 2 for value in size]))]
        if geometry.kind == "sphere":
            return [("type", "sphere"), ("size", _numbers(size[:1]))]
        if geometry.kind in ("cylinder", "capsule"):
            return [("type", geometry.kind), ("size", _numbers((size[0], size[1] / 2)))]
        raise ExportRefused(f"{self.description.name}: no MJCF geom is a {geometry.kind!r}")

    def _material(self, name: str, rgba: tuple) -> str:
        key = (name, _numbers(rgba, snap=0))
        found = self.materials.get(key)
        if found is None:
            found = self.materials[key] = self.materials_named(name)
            self.material_rows.append((found, rgba))
        return found

    def _mesh(self, key: str, scale: float) -> str:
        found = self.meshes.get((key, scale))
        if found is not None:
            return found
        mesh = self.description.meshes[key]
        wanted = mesh.name if scale == 1 else f"{mesh.name}_x{_number(scale, snap=0)}"
        found = self.meshes[(key, scale)] = self.meshes_named(wanted)
        file = self.mesh_files.get(key)
        if file is None:
            file = self.mesh_files[key] = self.files_named(f"{_stem(self.description.name)}_{_stem(mesh.name)}") + ".stl"
            self.files[file] = _stl(f"{self.description.name}/{mesh.name}", mesh.positions, mesh.triangles)
        self.mesh_rows.append((found, file, scale))
        return found

    def _contact(self) -> _Element:
        from cad.engine.export.contact import touching

        contact = _Element("contact")
        seen: set[frozenset[str]] = set()
        for first, second in [*touching(self.description), *self.description.excludes]:
            key = frozenset((first, second))
            if key in seen:
                continue
            seen.add(key)
            contact.add("exclude", [("body1", self.body_of[first]), ("body2", self.body_of[second])])
        return contact

    def _equality(self) -> _Element:
        equality = _Element("equality")
        kinds = {joint.name: joint.kind for joint in self.description.joints}
        for joint in self.description.joints:
            if joint.follows is None:
                continue
            leader, ratio, offset = joint.follows
            for name in (joint.name, leader):
                if kinds.get(name) not in ("revolute", "continuous", "prismatic", "cylindrical"):
                    raise ExportRefused(f"{self.description.name}: joint {joint.name!r} follows {leader!r}, and MJCF "
                                        f"couples one value to one value: {name!r} is "
                                        + (f"a {kinds[name]} joint" if name in kinds else "no joint here"))
            equality.add("joint", [("joint1", self.joint_names[joint.name]), ("joint2", self.joint_names[leader]),
                                   ("polycoef", _numbers((offset, ratio, 0, 0, 0), snap=0))])
        named = _Names()
        for closure in self.description.closures:
            hinge = closure.kind in ("revolute", "continuous")
            for suffix in ("", "_axis") if hinge else ("",):
                equality.add("connect", [("name", named(closure.name + ("/axis" if suffix else ""))),
                                         ("site1", self.closure_named[(closure.name, "1" + suffix)]),
                                         ("site2", self.closure_named[(closure.name, "2" + suffix)])])
            if any(bound is not None for bounds in closure.limits for bound in bounds):
                note(f"joint {closure.name!r} closes a loop as an equality, which holds no range: its range is not "
                     "enforced")
        return equality

    def _keyframe(self) -> _Element:
        keyframe = _Element("keyframe")
        moving = {joint.name: joint for joint, _count in self.qpos}
        for pose in self.description.poses:
            unknown = sorted(name for name in pose.values if name not in moving)
            if unknown:
                raise ExportRefused(f"{self.description.name}: pose {pose.name!r} names {', '.join(map(repr, unknown))}, "
                                    "which is no moving joint here")
            values: list[float] = []
            for joint, count in self.qpos:
                values.extend(_qpos(joint, count, pose.values))
            keyframe.add("key", [("name", pose.name), ("qpos", _numbers(values))])
        return keyframe


# --- pieces ------------------------------------------------------------------------------------------


def _qpos(joint: Joint, count: int, values: dict[str, Any]) -> list[float]:
    """A joint's slice of a key's ``qpos``: its values at the pose, or where its leader puts it, or zero; a free
    joint's its body's position and quaternion at zero."""
    if count == 7:
        origin = np.asarray(joint.origin, dtype=float)
        return [*(float(value) for value in origin[:3, 3]), *(float(value) for value in _quaternion(origin))]
    given = values.get(joint.name)
    if given is None and joint.follows is not None and values.get(joint.follows[0]) is not None:
        leader, ratio, offset = joint.follows
        led = values[leader]
        first = float(led[0] if isinstance(led, (tuple, list)) else led)
        given = ratio * first + offset
    if count == 4:
        angles = [0.0, 0.0, 0.0] if given is None else [float(value) for value in given]
        quaternion = np.array([1.0, 0.0, 0.0, 0.0])
        for axis, angle in enumerate(angles):  # x, then y, then z, as the pair turns (mechanism.pair_motion)
            turn = np.zeros(4)
            turn[0], turn[1 + axis] = math.cos(angle / 2), math.sin(angle / 2)
            quaternion = _product(quaternion, turn)
        return list(quaternion)
    found = [0.0] * count if given is None else [float(value) for value in (
        given if isinstance(given, (tuple, list)) else (given,))]
    return (found + [0.0] * count)[:count]


def _product(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    w1, x1, y1, z1 = a
    w2, x2, y2, z2 = b
    return np.array([w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2, w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
                     w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2, w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2])


def _inertial(link: Link) -> _Element:
    inertial = link.inertial
    assert inertial is not None
    tensor = np.asarray(inertial.inertia, dtype=float)
    tensor = (tensor + tensor.T) / 2
    scale = max(float(np.abs(tensor).max()), 0.0)
    if scale == 0 or float(np.abs(tensor - np.diag(np.diag(tensor))).max()) <= 1e-12 * scale:
        moments, axes = np.diag(tensor).copy(), np.eye(3)
    else:
        moments, axes = np.linalg.eigh(tensor)
        for column in range(3):  # each axis signed alike every time: its largest component positive
            if axes[np.argmax(np.abs(axes[:, column])), column] < 0:
                axes[:, column] *= -1
        if np.linalg.det(axes) < 0:
            axes[:, 2] *= -1
    for at in range(3):  # MuJoCo's triangle inequality, missed by rounding alone
        others = moments[(at + 1) % 3] + moments[(at + 2) % 3]
        if 0 < moments[at] - others <= NUDGE:
            moments[at] = others
    rotation = np.eye(4)
    rotation[:3, :3] = axes
    quat = _quaternion(rotation)
    return _Element("inertial", [("pos", _numbers(inertial.center)),
                                 ("quat", None if _numbers(quat) == "1 0 0 0" else _numbers(quat)),
                                 ("mass", _number(inertial.mass, snap=0)),
                                 ("diaginertia", _numbers(moments, snap=0))])


def _placement(matrix: Any) -> list[tuple[str, str | None]]:
    """A frame's ``pos`` and ``quat``, each only where it is not the identity's."""
    matrix = np.asarray(matrix, dtype=float)
    pos = _numbers(matrix[:3, 3])
    quat = _numbers(_quaternion(matrix))
    return [("pos", None if pos == "0 0 0" else pos), ("quat", None if quat == "1 0 0 0" else quat)]


def _quaternion(matrix: np.ndarray) -> np.ndarray:
    """A rotation's unit quaternion, w x y z, its w not negative."""
    r = np.asarray(matrix, dtype=float)[:3, :3]
    trace = r[0, 0] + r[1, 1] + r[2, 2]
    if trace > 0:
        s = math.sqrt(trace + 1.0) * 2
        q = [0.25 * s, (r[2, 1] - r[1, 2]) / s, (r[0, 2] - r[2, 0]) / s, (r[1, 0] - r[0, 1]) / s]
    elif r[0, 0] > r[1, 1] and r[0, 0] > r[2, 2]:
        s = math.sqrt(1.0 + r[0, 0] - r[1, 1] - r[2, 2]) * 2
        q = [(r[2, 1] - r[1, 2]) / s, 0.25 * s, (r[0, 1] + r[1, 0]) / s, (r[0, 2] + r[2, 0]) / s]
    elif r[1, 1] > r[2, 2]:
        s = math.sqrt(1.0 + r[1, 1] - r[0, 0] - r[2, 2]) * 2
        q = [(r[0, 2] - r[2, 0]) / s, (r[0, 1] + r[1, 0]) / s, 0.25 * s, (r[1, 2] + r[2, 1]) / s]
    else:
        s = math.sqrt(1.0 + r[2, 2] - r[0, 0] - r[1, 1]) * 2
        q = [(r[1, 0] - r[0, 1]) / s, (r[0, 2] + r[2, 0]) / s, (r[1, 2] + r[2, 1]) / s, 0.25 * s]
    found = np.array(q, dtype=float)
    found /= np.linalg.norm(found)
    return -found if found[0] < 0 else found


def _number(value: Any, *, snap: float = SNAP) -> str:
    value = float(value)
    if abs(value) < snap:
        value = 0.0
    text = f"{value:.9g}"
    return "0" if text == "-0" else text


def _numbers(values: Iterable[Any], *, snap: float = SNAP) -> str:
    return " ".join(_number(value, snap=snap) for value in values)


def _stem(name: str) -> str:
    """A name as a file name's part: letters, digits, ``.``, ``-`` and ``_``, the rest ``_``."""
    return re.sub(r"[^A-Za-z0-9._-]", "_", name).strip(".") or "mesh"


def _stl(name: str, positions: Any, triangles: Any) -> bytes:
    """A binary STL of one mesh: its 80-byte header naming it, then its triangles in order, each normal
    from its corners."""
    header = name.encode("ascii", "replace")
    if header.lower().startswith(b"solid"):  # an ASCII STL's first word: a reader would take it for one
        header = b"mesh " + header
    corners = np.asarray(positions, dtype=np.float32)[np.asarray(triangles, dtype=np.int64).reshape(-1, 3)]
    normal = np.cross(corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0])
    lengths = np.linalg.norm(normal, axis=1, keepdims=True)
    rows = np.zeros(len(corners), dtype=_RECORD)
    rows["normal"] = normal / np.where(lengths > 0, lengths, 1)
    rows["corners"] = corners
    return header[:80].ljust(80, b" ") + struct.pack("<I", len(rows)) + rows.tobytes()

