"""A document described as a robot (``description.py``): the engine's half that needs the kernel.

``describe(view)`` reads a document's structure -- its prototypes with their materials and what
they declare for a simulator (``declarations``: collision, named frames), its instances where
the document places them, and its mechanism (``kinematics``, ``mechanism.block``) -- and makes the
``Description`` every robot format is written from, in SI units, at the as-built state.

**Links.** The first link is ``world``, holding nothing, at the model's origin. With a mechanism,
its ground link (the parts no pair moves) hangs from ``world`` by a ``fixed`` joint named for the
model (a pair's joint is named by its label, so a fixed joint takes ``_2`` where one holds its name), so a fragment attaches under a frame as one body tree; every other link hangs from the link
its pair reaches it from, the pairs followed from the ground as ``mechanism.link_worlds`` follows
them. With none (a STEP, a model without joints), each top-level node of the document's tree is a
link hung from ``world`` by a ``fixed`` joint named for it, so a scene can make any of them free; an
assembly at the top is one link, all its parts together. A link's name is its mechanism link's (its
first part's), or its node's, made unique with ``_2``, ``_3``.

**Frames** (``description.py``'s **Units and frames**). For a pair from link 1 (the part holding the
moving joint) to link 2 (the rigid joint's), with ``W1``/``W2`` the links as built, ``item_1``/``item_2``
the pair's frames on them, ``M`` its motion and ``v0`` its as-built value, the law is ``W2 = W1 @ item_1
@ M(v0) @ item_2^-1``. Reached from link 1 (the parent), the child's frame is ``W2 @ item_2`` and the
joint's origin ``P^-1 @ W1 @ item_1 @ M(v0)`` (``P`` the parent's frame), so the child stands at ``P @
origin @ M(q)`` at ``q`` around zero. Reached from link 2, the pair runs backwards: ``F`` a half turn
about X, which turns every lower pair's motion into its inverse (``F @ M(v) @ F == M(v)^-1``), the
child's frame is ``W1 @ item_1 @ F`` and the origin ``P^-1 @ W2 @ item_2 @ F @ M(v0)``, so a joint's
value is its pair's either way. A spherical pair has no such ``F``: backwards, the child's frame is
``W1 @ item_1`` and the origin ``P^-1 @ W2 @ item_2 @ M(v0)^-1``. A spherical joint's value around zero
is the intrinsic X-Y-Z angles of its turn from the as-built state, which is what its poses hold;
its limits are each angle's range less its as-built angle.

**Geometry and mass.** Each instance a link holds is a visual of its prototype's mesh, placed in the
link frame; its collision is what the prototype declares, ``collision_default`` where it declares
none, a primitive fitted to its oriented bounding box (``Bnd_OBB``). Its mass is its solids' at its
material's density, measured once per prototype in the prototype's frame and moved to the link's
(``I' = R I R^T``, then the parallel-axis theorem about the link's centre of mass).
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from cad.engine.description import (COLLISIONS, Collision, Description, DescriptionError, Geometry, Inertial, Joint,
                                    Link, Mesh, Pose, Visual, column_major, srgb)

__all__ = ["describe"]

MM = 0.001  # metres per millimetre
UNITS = {"deg": math.pi / 180.0, "mm": MM}  # SI per pair unit
# A half turn about X: a lower pair's motion seen from its other link (``F @ M(v) @ F == M(v)^-1``).
FLIP = np.diag([1.0, -1.0, -1.0, 1.0])
# The ground link of every description, at the model's origin, holding nothing.
WORLD = "world"


def describe(view: Any, *, collision_default: str = "mesh") -> Description:
    """The robot ``view``'s document is (see the module docstring): its links, joints, meshes,
    poses and loops, checked (``Description.check``, but for a loop: a description with one is
    made, and every writer refuses it). ``collision_default`` is a part's collision where it
    declares none: one of ``description.COLLISIONS``."""
    if collision_default not in COLLISIONS:
        raise ValueError(f"collision_default {collision_default!r} is none of {', '.join(COLLISIONS)}")
    return _Describer(view, collision_default).run()


def _rotation(axis: int, angle: float) -> np.ndarray:
    c, s = math.cos(angle), math.sin(angle)
    found = np.eye(4)
    i, j = [(1, 2), (2, 0), (0, 1)][axis]
    found[i, i], found[i, j], found[j, i], found[j, j] = c, -s, s, c
    return found


def motion(kind: str, values: tuple[float, ...]) -> np.ndarray:
    """A joint's motion at ``values`` (radians, metres): ``mechanism.pair_motion`` in SI -- a turn
    about Z, a slide along Z, both (turn, then slide), or intrinsic X-Y-Z turns."""
    if kind in ("revolute", "continuous"):
        return _rotation(2, values[0])
    if kind == "prismatic":
        found = np.eye(4)
        found[2, 3] = values[0]
        return found
    if kind == "cylindrical":
        found = _rotation(2, values[0])
        found[2, 3] = values[1]
        return found
    if kind == "spherical":
        return _rotation(0, values[0]) @ _rotation(1, values[1]) @ _rotation(2, values[2])
    return np.eye(4)


def _angles(rotation: np.ndarray) -> tuple[float, float, float]:
    """The intrinsic X-Y-Z angles (radians) of a rotation: ``Rx(a) @ Ry(b) @ Rz(c)``."""
    b = math.asin(max(-1.0, min(1.0, float(rotation[0, 2]))))
    if abs(math.cos(b)) < 1e-12:  # gimbal lock: the X and Z turns are one; all of it in X
        return float(math.atan2(rotation[2, 1], rotation[1, 1])), b, 0.0
    return (float(math.atan2(-rotation[1, 2], rotation[2, 2])), b, float(math.atan2(-rotation[0, 1], rotation[0, 0])))


def _values(value: Any) -> tuple[float, ...]:
    return (float(value),) if isinstance(value, (int, float)) else tuple(float(item) for item in value)


def _unique(name: str, taken: set[str]) -> str:
    found, at = name or "part", 2
    while found in taken:
        found, at = f"{name}_{at}", at + 1
    taken.add(found)
    return found


class _Describer:
    def __init__(self, view: Any, collision_default: str) -> None:
        self.view = view
        self.source = view.source
        self.structure = self.source.structure
        self.collision_default = collision_default
        self.prototypes = self.structure["prototypes"]
        self.instances = self.structure["instances"]
        self.worlds = [column_major(instance["matrix"]) for instance in self.instances]
        self.warnings: list[str] = []
        self.measured: dict[str, Any] = {}
        self.fitted: dict[str, Any] = {}
        self.link_names: set[str] = set()
        self.joint_names: set[str] = set()

    def warn(self, text: str) -> None:
        if text not in self.warnings:
            self.warnings.append(text)

    # --- the tree --------------------------------------------------------------------------

    def run(self) -> Description:
        kinematics = self.structure.get("kinematics")
        if kinematics is not None and kinematics.get("pose"):
            raise DescriptionError("the structure is posed (its instances stand at a pose): a description is made "
                                   "of the document as built")
        for text in (kinematics or {}).get("warnings") or ():
            self.warn(text)
        world = Link(_unique(WORLD, self.link_names), np.eye(4))
        links, joints, poses, loops, closing = [world], [], [], (), set()
        if kinematics is not None and kinematics.get("links"):
            loops = tuple((kinematics.get("loop") or ()))
            closing = self._mechanism(kinematics, links, joints)
            poses = self._poses(kinematics, joints)
        else:
            self._unjointed(links, joints)
        meshes = self._meshes()
        for link in links[1:]:
            self._geometry(link)
        found = Description(self.structure["name"], links, joints, meshes, poses, loops)
        checked = found if not loops else Description(found.name, links, [j for j in joints if j.name not in closing],
                                                      meshes, poses)
        checked.check()
        found.warnings = tuple(self.warnings)
        return found

    def _fixed(self, name: str, parent: Link, child: Link) -> Joint:
        return Joint(_unique(name, self.joint_names), "fixed", parent.name, child.name,
                     np.linalg.inv(parent.frame) @ child.frame)

    def _unjointed(self, links: list[Link], joints: list[Joint]) -> None:
        """No mechanism: each top-level node of the tree a link, hung from the world."""
        tree = self.structure["tree"]
        for node in (tree["children"] if "children" in tree else [tree]):
            parts = tuple(_leaves(node))
            if not parts:
                continue
            link = Link(_unique(node["name"], self.link_names), self.worlds[parts[0]].copy(), parts=parts)
            links.append(link)
            joints.append(self._fixed(link.name, links[0], link))

    def _mechanism(self, kinematics: dict[str, Any], links: list[Link], joints: list[Joint]) -> set[str]:
        """The mechanism's links from its ground, each by the pair that reaches it (see the module
        docstring); returns the names of the joints that close a loop."""
        blocks = kinematics["links"]
        ground = int(kinematics.get("ground") or 0)
        built = [column_major(block["matrix"]) for block in blocks]
        as_built = {label: _values(value) for label, value in (kinematics.get("asBuilt") or {}).items()}
        pairs = kinematics.get("pairs") or []
        made: dict[int, Link] = {}

        def link(at: int, frame: np.ndarray) -> Link:
            found = made[at] = Link(_unique(blocks[at]["name"], self.link_names), frame,
                                    parts=tuple(blocks[at].get("instances") or ()))
            links.append(found)
            return found

        # A pair's joint is named by its label, which poses and couplings name it by; a fixed joint
        # takes another name where a label holds its own.
        self.joint_names.update(pair["label"] for pair in pairs)
        base = link(ground, built[ground].copy())
        joints.append(self._fixed(kinematics.get("name") or self.structure["name"], links[0], base))
        self.pair_joints: dict[str, Joint] = {}
        self.pair_kinds: dict[str, dict[str, Any]] = {}
        closing: set[str] = set()
        used: set[int] = set()
        queue = [ground]
        while queue:
            at = queue.pop(0)
            for index, pair in enumerate(pairs):
                first, second = pair["links"]
                if index in used or at not in (first, second) or first == second:
                    continue
                used.add(index)
                if not pair.get("frames"):
                    self.warn(f"pair {pair['label']!r} has no frames: the description leaves it out")
                    continue
                forward = at == first
                other = second if forward else first
                joint, frame = self._joint(pair, made[at], built[first], built[second], as_built, forward)
                if other in made:  # the pair closes a loop: its child stands where the tree put it
                    closing.add(joint.name)
                    joint.child = made[other].name
                else:
                    joint.child = link(other, frame).name
                    queue.append(other)
                joints.append(joint)
                self.pair_joints[pair["label"]] = joint
                self.pair_kinds[pair["label"]] = {"pair": pair, "forward": forward}
        for at in range(len(blocks)):
            if at not in made:
                self.warn(f"link {blocks[at]['name']!r} is reached by no pair from the ground: it hangs fixed from "
                          f"{WORLD!r} where it was built")
                joints.append(self._fixed(blocks[at]["name"], links[0], link(at, built[at].copy())))
        self._couplings(kinematics)
        return closing

    def _joint(self, pair: dict[str, Any], parent: Link, first: np.ndarray, second: np.ndarray,
               as_built: dict[str, tuple[float, ...]], forward: bool) -> tuple[Joint, np.ndarray]:
        """The joint a pair is, from ``parent`` (its first link when ``forward``), and its child's frame."""
        label, kind = pair["label"], pair["type"]
        units = [UNITS[unit] for unit in pair.get("units") or ()]
        built = as_built.get(label, (0.0,) * len(units))
        si = tuple(value * unit for value, unit in zip(built, units))
        item_1, item_2 = (column_major(frame) for frame in pair["frames"])
        moved = motion(kind, si)
        inverse = np.linalg.inv(parent.frame)
        if forward:
            child, origin = second @ item_2, inverse @ first @ item_1 @ moved
        elif kind == "spherical":
            child, origin = first @ item_1, inverse @ second @ item_2 @ np.linalg.inv(moved)
        else:
            child, origin = first @ item_1 @ FLIP, inverse @ second @ item_2 @ FLIP @ moved
        limits = []
        for index, unit in enumerate(units):
            given = (pair.get("limits") or [])[index] if index < len(pair.get("limits") or []) else None
            lower, upper = given if given else (None, None)
            limits.append(tuple(None if bound is None else (float(bound) - built[index]) * unit
                                for bound in (lower, upper)))
        if kind == "revolute" and limits[0] == (None, None):
            kind = "continuous"
        return Joint(label, kind, parent.name, "", origin, tuple(limits), si), child

    def _couplings(self, kinematics: dict[str, Any]) -> None:
        """Each coupling written on the joints that follow: every one from its first-named value
        (``value = ratio * leader``, around zero, in SI)."""
        held = getattr(getattr(self.source, "mechanism", None), "couplings", None) or {}
        for name, coupling in (kinematics.get("couplings") or {}).items():
            if name in held:
                terms = [(label, index, ratio) for label, ratios in held[name].ratios.items()
                         for index, ratio in enumerate(ratios) if ratio]
            else:
                terms = [tuple(term) for term in coupling.get("terms") or () if term[2]]
            if len(terms) < 2:
                continue
            (hub, hub_index, hub_ratio), others = terms[0], terms[1:]
            for label, index, ratio in others:
                ends = [self.pair_kinds.get(hub), self.pair_kinds.get(label)]
                if None in ends or label == hub or any(len(end["pair"].get("units") or ()) != 1 for end in ends):
                    self.warn(f"coupling {name!r} relates {hub!r} and {label!r} as no joint following another can "
                              "(a screw, or a pair of several values): the description leaves it out")
                    continue
                unit, hub_unit = (UNITS[end["pair"]["units"][0]] for end in (ends[1], ends[0]))
                follower = self.pair_joints[label]
                follower.follows = (self.pair_joints[hub].name, (ratio * unit) / (hub_ratio * hub_unit), 0.0)

    def _poses(self, kinematics: dict[str, Any], joints: list[Joint]) -> list[Pose]:
        """The mechanism's named states around zero, in SI."""
        found = []
        as_built = {label: _values(value) for label, value in (kinematics.get("asBuilt") or {}).items()}
        for name, values in (kinematics.get("configurations") or {}).items():
            pose: dict[str, float | tuple[float, ...]] = {}
            for label, value in values.items():
                joint = getattr(self, "pair_joints", {}).get(label)
                if joint is None:
                    continue
                described = self.pair_kinds[label]
                pair = described["pair"]
                units = [UNITS[unit] for unit in pair.get("units") or ()]
                given, built = _values(value), as_built.get(label, (0.0,) * len(units))
                if pair["type"] == "spherical":
                    then = motion("spherical", tuple(v * u for v, u in zip(built, units)))
                    now = motion("spherical", tuple(v * u for v, u in zip(given, units)))
                    turned = (np.linalg.inv(then) @ now if described["forward"] else then @ np.linalg.inv(now))
                    pose[joint.name] = _angles(turned)
                    continue
                around = tuple((v - b) * u for v, b, u in zip(given, built, units))
                pose[joint.name] = around[0] if len(around) == 1 else around
            found.append(Pose(name, pose))
        return found

    # --- geometry and mass -------------------------------------------------------------------

    def _meshes(self) -> dict[str, Mesh]:
        from cad.engine.export.mesh import meshes

        found: dict[str, Mesh] = {}
        for index, made in meshes(self.view).items():
            prototype = self.prototypes[index]
            if prototype["key"] in found:
                continue
            positions = (np.asarray(made.positions, dtype=np.float64).reshape(-1, 3) * MM).astype(np.float32)
            normals = None if made.normals is None else np.asarray(made.normals, dtype=np.float32).reshape(-1, 3)
            found[prototype["key"]] = Mesh(prototype["key"], prototype["name"], positions,
                                           np.asarray(made.indices, dtype=np.uint32).reshape(-1, 3), normals)
        return found

    def _geometry(self, link: Link) -> None:
        """A link's visuals, collisions, named frames and inertial, each in its frame."""
        inverse = np.linalg.inv(link.frame)
        masses: list[tuple[float, np.ndarray, np.ndarray]] = []
        massless: list[str] = []
        for index in link.parts:
            instance = self.instances[index]
            prototype = self.prototypes[instance["prototype"]]
            name = instance["path"].rsplit("/", 1)[-1]
            placement = inverse @ self.worlds[index]
            material = (prototype.get("material") or {}).get("material") or {}
            key = prototype["key"]
            link.visuals.append(Visual(name, Geometry("mesh", placement, mesh=key),
                                       srgb(instance.get("color") or prototype.get("color")),
                                       material.get("name") or None))
            kind = prototype.get("collision") or self.collision_default
            if kind == "mesh":
                link.collisions.append(Collision(name, Geometry("mesh", placement, mesh=key)))
            elif kind != "none":
                frame, size = self._fit(key, prototype["name"], kind)
                link.collisions.append(Collision(name, Geometry(kind, placement @ frame, size=size)))
            for frame_name, values in sorted((prototype.get("frames") or {}).items()):
                named = frame_name
                if named in link.frames:
                    named = f"{name}/{frame_name}"
                    self.warn(f"link {link.name!r} holds frame {frame_name!r} twice: the one on {name} is "
                              f"{named!r}")
                link.frames[named] = placement @ column_major(values)
            measured = self._mass(prototype, material)
            if measured is None:
                massless.append(name)
                continue
            mass, center, inertia = measured
            rotation = placement[:3, :3]
            masses.append((mass, rotation @ center + placement[:3, 3], rotation @ inertia @ rotation.T))
        if not masses:
            if link.parts:
                self.warn(f"link {link.name!r} has no inertial: none of its parts has a material with a density")
            return
        if massless:
            self.warn(f"link {link.name!r}'s inertial leaves out {', '.join(massless)}: no density (or no solid)")
        total = sum(mass for mass, _center, _inertia in masses)
        center = sum(mass * at for mass, at, _inertia in masses) / total
        inertia = np.zeros((3, 3))
        for mass, at, own in masses:
            offset = at - center
            inertia += own + mass * (float(offset @ offset) * np.eye(3) - np.outer(offset, offset))
        link.inertial = Inertial(float(total), center, inertia)

    def _density(self, prototype: dict[str, Any], material: dict[str, Any]) -> float | None:
        density = material.get("density")
        if density is None:
            return None
        if isinstance(density, bool) or not isinstance(density, (int, float)) or not math.isfinite(density):
            raise DescriptionError(f"part {prototype['name']!r}: its material {material.get('name')!r} has a density "
                                   f"of {density!r}, which is no number of kg/m^3")
        if density <= 0:
            raise DescriptionError(f"part {prototype['name']!r}: its material {material.get('name')!r} has a density "
                                   f"of {density:g} kg/m^3, which is not positive")
        return float(density)

    def _mass(self, prototype: dict[str, Any], material: dict[str, Any]) -> tuple[float, np.ndarray, np.ndarray] | None:
        """A prototype's mass (kg), centre (m) and inertia about it (kg*m^2), in its own frame, or None
        where it has no density or no solid."""
        density = self._density(prototype, material)
        if density is None:
            return None
        measured = self._measured(prototype)
        if measured is None:
            return None
        volume, center, inertia = measured
        per_mm3 = density * 1e-9  # kg/m^3 as kg/mm^3
        return volume * per_mm3, center * MM, inertia * per_mm3 * 1e-6

    def _measured(self, prototype: dict[str, Any]) -> tuple[float, np.ndarray, np.ndarray] | None:
        """A prototype's solids at unit density, measured once per key: volume (mm^3), centre (mm) and
        inertia about it (mm^5), in its own frame; None where it has none, warned."""
        key = prototype["key"]
        if key in self.measured:
            return self.measured[key]
        from OCP.BRepGProp import BRepGProp
        from OCP.GProp import GProp_GProps
        from OCP.TopAbs import TopAbs_SOLID
        from OCP.TopExp import TopExp_Explorer

        shape = self._shape(key)
        found = None
        if shape is not None:
            combined, count = GProp_GProps(), 0
            explorer = TopExp_Explorer(shape, TopAbs_SOLID)
            while explorer.More():
                own = GProp_GProps()
                BRepGProp.VolumeProperties_s(explorer.Current(), own)
                if not own.Mass() > 0:
                    raise DescriptionError(f"part {prototype['name']!r}: a solid of it has no positive volume (it is "
                                           "inside out), so it has no mass")
                combined.Add(own, 1.0)
                count += 1
                explorer.Next()
            if count:
                at = combined.CentreOfMass()
                tensor = combined.MatrixOfInertia()
                found = (float(combined.Mass()), np.array([at.X(), at.Y(), at.Z()]),
                         np.array([[tensor.Value(i, j) for j in (1, 2, 3)] for i in (1, 2, 3)]))
        if found is None:
            self.warn(f"part {prototype['name']!r} is no solid (a shell, a face or a mesh): it carries no mass")
        self.measured[key] = found
        return found

    def _shape(self, key: str) -> Any:
        """A prototype's B-rep in its own frame, or None for a mesh file's part (no B-rep)."""
        if key not in (self.source.shapes or {}):
            return None
        from cad.engine.mesh import read_shape

        return read_shape(self.source.shape_data(key))

    def _fit(self, key: str, name: str, kind: str) -> tuple[np.ndarray, tuple[float, ...]]:
        """A primitive fitted to a prototype's oriented bounding box: its frame in the prototype's
        (metres) and its sizes (``Geometry.size``)."""
        box = self.fitted.get(key)
        if box is None:
            from OCP.Bnd import Bnd_OBB
            from OCP.BRepBndLib import BRepBndLib

            shape = self._shape(key)
            if shape is None:
                raise DescriptionError(f"part {name!r} is a mesh: no {kind} is fitted to it without its B-rep")
            obb = Bnd_OBB()
            BRepBndLib.AddOBB_s(shape, obb, False, True, False)
            if obb.IsVoid():
                raise DescriptionError(f"part {name!r} has no extent to fit a {kind} to")
            axes = [np.array([d.X(), d.Y(), d.Z()]) for d in (obb.XDirection(), obb.YDirection(), obb.ZDirection())]
            halves = np.array([obb.XHSize(), obb.YHSize(), obb.ZHSize()]) * MM
            centre = obb.Center()
            box = self.fitted[key] = (axes, halves, np.array([centre.X(), centre.Y(), centre.Z()]) * MM)
        axes, halves, centre = box
        frame = np.eye(4)
        frame[:3, 3] = centre
        if kind == "box":
            frame[:3, 0], frame[:3, 1] = axes[0], axes[1]
            frame[:3, 2] = np.cross(axes[0], axes[1])
            return frame, tuple(float(2 * half) for half in halves)
        if kind == "sphere":
            return frame, (float(np.linalg.norm(halves)),)
        order = np.argsort(-halves, kind="stable")  # the longest side the axis, the next X
        z, x = axes[order[0]], axes[order[1]]
        frame[:3, 0], frame[:3, 1], frame[:3, 2] = x, np.cross(z, x), z
        radius, length = float(halves[order[1]]), float(2 * halves[order[0]])
        if kind == "capsule":
            length = max(length - 2 * radius, 0.0)
        return frame, (radius, length)


def _leaves(node: dict[str, Any]) -> list[int]:
    if "children" not in node:
        return [node["instance"]]
    return [index for child in node["children"] for index in _leaves(child)]
