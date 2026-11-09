"""A document described as a robot (``description.py``): the engine's half that needs the kernel.

``describe(view)`` reads a document's structure -- its prototypes with their materials and what
they declare for a simulator (``declarations``: collision, named frames), its instances where
the document places them, and its mechanism (``kinematics``, ``mechanism.block``) -- and makes the
``Description`` every robot format is written from, in SI units, at the as-built state.

**Links.** The first link is ``world``, holding nothing, at the model's origin. With a mechanism,
its ground link (the parts no pair moves) hangs from ``world`` by a ``fixed`` joint named for the
model (a pair's joint is named by its label, so a fixed joint takes ``_2`` where one holds its name), so a fragment attaches under a frame as one body tree; every other link hangs from the link
its pair reaches it from, the pairs followed from the ground breadth first, in the mechanism's pair
order. A pair that reaches a link the tree already holds closes a loop: it is a ``Closure``
(``description``'s **Loops**, where a slide is traded for its loop's nearest turn or ball), its frame on
each of its two links, the two checked to coincide as built within the tolerance the mechanism reads
every pair to (1e-6 of the model's size in millimetres, at least 1), else refused by name. A mechanism
state that moves a joint of a loop is left out of the poses, and warned. A virtual pinion (a revolute
pair to a link of no part that no other pair reaches) is no link: its racks follow the first of them.
With none (a STEP, a model without joints), each top-level node of the document's tree is a
link hung from ``world`` by a ``fixed`` joint named for it, so a scene can make any of them free; an
assembly at the top is one link, all its parts together. A link's name is the one its parts are declared
to make (``declarations.link``: the innermost declaration over each part, a part declared a body aside),
else its mechanism link's (the label of the jointed assembly that holds it, else its first part's), or
its node's, made unique with ``_2``, ``_3``; a joint's is unique among joints alone. A declared name is
refused by name where one link's parts declare two, where two links declare one, and where it is the
ground's, ``world``.

**The base.** A node declared free (``declarations.free``) floats what it holds: each link hung from
``world`` that holds a part at or below it hangs by a ``floating`` joint in place of its ``fixed`` one. A
free node none of whose parts is in a link hung from ``world`` is refused by name.

**The zero.** Given ``zero``, a mechanism state's name, the description is taken there (``description``'s
**Units and frames**): each joint the state moves has its origin turned or slid by its value there (its
value around the as-built state, ``d``), so every link stands as the state poses it; its limits are its
range less ``d``, its ``as_built`` the state's value, a follower's offset what keeps its coupling true
about the new zero, and every pose (the state's own among them, at zero) less ``d``, a spherical joint's
turn composed (``M(d)^-1 @ M(v)``). A name no state has is refused, the states named; so is a state that
moves a joint of a loop (it has no pose without a solver), and a document with no mechanism.

**Bodies.** A part declared a body (``declarations.body``) leaves the link it was made part of: it is a
link of its own, named for the declaration (its name, else the part's), framed at the part's own
placement, hung from that link by a ``fixed`` joint of the same name, after it in link order. A link
every part of which is declared a body keeps its first, and says so.

**Drives and exclusions.** A pair's joint takes the drive limits (``declarations.limits``) declared for
its label on the node that holds its moving joint: a part in the pair's link 1, or an assembly (a link
of several parts), whose parts carry its limits with how many levels above them it is (the one at the
qualifier's path, for a label two pairs share). A declaration no pair's joint takes is warned, by the
node that holds it, and left out. A declared exclusion (``declarations.exclude``) is
each link holding the part that declares it, with each link holding a part at or below a node of
the label it names (a part's own label names it), or at or below the one occurrence a shape it was
given names (``excludePaths``: never the others of that shape's label); a label or a path that
names no node is refused by name,
and two links' pair is kept once. The part pairs themselves are kept too (``part_excludes``, by
occurrence path): a joint stop sweep sets aside those two parts alone, where a simulator filters
their links.

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
none: its mesh, a primitive fitted to its oriented bounding box (``Bnd_OBB``), or, ``decomposed``, the
convex hulls CoACD cuts that mesh into with the options it declares (by ``collision_default``, the
declaration's default: at most 16) (``hulls``: from the engine's cache by the mesh's digest and the options, else
the coacd integration's CoACD in a process of its own, every decomposed geometry and option set in one call;
refused by name where neither has them), each hull a mesh of the description's (``<key>#hull<i>``, or
``<key>#<options digest>#hull<i>`` where options are given, named ``<prototype>_hull<i>``) and a collision ``<part>_hull<i>`` -- each with the
contact friction the part declares (``declarations.friction``). Its mass is its solids' at its material's density,
measured once per prototype in the prototype's frame and moved to the link's (``I' = R I R^T``, then
the parallel-axis theorem about the link's centre of mass), and each point mass it declares
(``declarations.point_mass``), a mass at a point with the inertia it is given (none, else its
diagonal in its frame's axes), moved the same way.

**Mass.** A node of the tree declared to weigh ``grams`` (``declarations.mass``) holds the instances
below it. Each instance belongs to its innermost declared node; a node's own solids are the
instances that belong to it, and its inner nodes the declared nodes below it whose nearest declared
node above is it. Innermost first, each node's solids are scaled by one factor so that they, the
point masses on them and its inner nodes' totals weigh ``grams``: a solid's weight before the scale
is its volume at its material's density, or at one density for all where none of the node's own
solids has one (one that has none, among some that do, carries none of the total, which the others make
up, and is warned by the node's name: no density is guessed for it). A node is
refused by name where its inner nodes and point masses weigh its total or more while it holds solids
of its own, where it has a remainder and its own solids no volume, or where it holds none and its
inner nodes and point masses do not weigh its total (within a part in 10^9). A declared node is
the tree's own node, not its label, so two siblings of one label are two nodes.
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any

import numpy as np

from cad.engine.declarations import DRIVE, MAX_HULLS
from cad.engine.description import (COLLISIONS, Closure, Collision, Description, DescriptionError, Geometry, Inertial,
                                    Joint, Link, Look, Mesh, Pose, Visual, column_major, srgb)

__all__ = ["describe"]

MM = 0.001  # metres per millimetre
UNITS = {"deg": math.pi / 180.0, "mm": MM}  # SI per pair unit
# A half turn about X: a lower pair's motion seen from its other link (``F @ M(v) @ F == M(v)^-1``).
FLIP = np.diag([1.0, -1.0, -1.0, 1.0])
# The ground link of every description, at the model's origin, holding nothing.
WORLD = "world"


def describe(view: Any, *, collision_default: str = "mesh", zero: str | None = None,
             decompose: bool = True) -> Description:
    """The robot ``view``'s document is (see the module docstring): its links, joints, meshes,
    poses and the joints that close its loops, checked (``Description.check``). ``collision_default``
    is a part's collision where it declares none: one of ``description.COLLISIONS``. ``zero`` is the
    mechanism state every joint's zero is taken at (the module's **The zero**), the as-built state where
    None. ``decompose`` False leaves a decomposed part whole, its one collision its own mesh, and runs no
    CoACD: for a reader that asks only whether each part collides (``ranges`` on the parts), never a writer."""
    if collision_default not in COLLISIONS:
        raise ValueError(f"collision_default {collision_default!r} is none of {', '.join(COLLISIONS)}")
    if zero is not None and (not isinstance(zero, str) or not zero):
        raise ValueError(f"zero is a mechanism state's name, not {zero!r}")
    return _Describer(view, collision_default, zero, decompose).run()


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
    def __init__(self, view: Any, collision_default: str, zero: str | None = None, decompose: bool = True) -> None:
        self.view = view
        self.zero = zero
        self.decompose = decompose
        self.source = view.source
        self.structure = self.source.structure
        self.collision_default = collision_default
        self.prototypes = self.structure["prototypes"]
        self.instances = self.structure["instances"]
        self.worlds = [column_major(instance["matrix"]) for instance in self.instances]
        self.warnings: list[str] = []
        self.measured: dict[str, Any] = {}
        self.fitted: dict[str, Any] = {}
        self.turned: dict[str, int | None] = {}  # each prototype's axis of turning, a side of its box (``_turned_axis``)
        self.link_names: set[str] = set()
        self.joint_names: set[str] = set()
        # Each part's declared link name (``declarations.link``: the innermost over it), a body's aside, and the
        # link that took each declared name, by its name.
        self.link_named = {index: str(self._declared(index)["link"][-1][1]) for index in range(len(self.instances))
                           if self._declared(index).get("link") and self._declared(index).get("body") is None}
        self.reserved = set(self.link_named.values())
        self.declared_links: dict[str, str] = {}
        self.meshes: dict[str, Mesh] = {}  # the description's meshes by key, a painted part's looks among them
        self.made: dict[int, Any] = {}  # each placed prototype's engine mesh, its faces' triangle spans

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
        if WORLD in self.reserved:
            raise DescriptionError(f"a link is declared {WORLD!r}, which is the ground's name: name it another")
        world = Link(_unique(WORLD, self.link_names), np.eye(4))
        links, joints, poses, closures = [world], [], [], []
        jointed = kinematics is not None and bool(kinematics.get("links"))
        if jointed:
            closures = self._mechanism(kinematics, links, joints)
            poses = self._poses(kinematics, joints, closures)
            self._drives(kinematics)
        else:
            self._unjointed(links, joints)
        if self.zero is not None and not jointed:
            raise DescriptionError(f"no mechanism state {self.zero!r}: the document has no mechanism, so no state "
                                   "to take the zero at")
        self._bodies(links, joints)
        self._free(links, joints)
        excludes, part_excludes = self._excludes(links)
        self.masses = self._masses()
        meshes = self._meshes()
        self.hulls = self._decompositions(links, meshes) if self.decompose else {}
        for link in links[1:]:
            self._geometry(link)
        if self.zero is not None:
            poses = self._zeroed(kinematics, links, joints, poses)
        found = Description(self.structure["name"], links, joints, meshes, poses, closures, excludes=excludes,
                            part_excludes=part_excludes, zero=self.zero)
        found.check()
        found.warnings = tuple(self.warnings)
        return found

    def _link_name(self, parts: tuple[int, ...], fallback: str) -> str:
        """A link's name: the one its parts declare (``declarations.link``), else ``fallback`` made unique (the
        module's **Links**), each declared name refused where it names two links or one link takes two."""
        declared = sorted({self.link_named[index] for index in parts if index in self.link_named})
        if len(declared) > 1:
            raise DescriptionError(f"link {fallback!r} holds parts declared to be link {declared[0]!r} and link "
                                   f"{declared[1]!r}: one link takes one name")
        if declared:
            name = declared[0]
            if name in self.declared_links:
                raise DescriptionError(f"link name {name!r} is declared on parts of two links, "
                                       f"{self.declared_links[name]!r} and {fallback!r}: a name names one link")
            self.declared_links[name] = fallback
            self.link_names.add(name)
            return name
        found, at = fallback or "part", 2
        while found in self.link_names or found in self.reserved:
            found, at = f"{fallback or 'part'}_{at}", at + 1
        self.link_names.add(found)
        return found

    def _free(self, links: list[Link], joints: list[Joint]) -> None:
        """Each link hung from the world that holds a part at or below a node declared free hung by a
        ``floating`` joint (the module's **The base**); a free node that holds none refused by name."""
        nodes: dict[tuple[int, ...], set[int]] = {}
        names: dict[tuple[int, ...], str] = {}

        def walk(node: dict[str, Any], at: tuple[int, ...], above: list[tuple[int, ...]]) -> None:
            names[at] = node.get("name") or "the model"
            if "children" in node:
                for position, child in enumerate(node["children"]):
                    walk(child, at + (position,), above + [at])
                return
            index = int(node["instance"])
            chain = above + [at]
            for up in self._declared(index).get("free") or ():
                if 0 <= int(up) < len(chain):
                    nodes.setdefault(chain[-1 - int(up)], set()).add(index)

        walk(self.structure["tree"], (), [])
        if not nodes:
            return
        owner = {index: link for link in links for index in link.parts}
        from_world = {joint.child: joint for joint in joints if joint.parent == links[0].name}
        for node, held in sorted(nodes.items()):
            hung = [from_world[owner[index].name] for index in sorted(held)
                    if index in owner and owner[index].name in from_world]
            if not hung:
                index = min(held)
                link = owner.get(index)
                placed = next((joint for joint in joints if link is not None and joint.child == link.name), None)
                where = (f"in link {link.name!r}, which hangs from {placed.parent!r} by joint {placed.name!r}"
                         if link is not None and placed is not None else "in no link")
                raise DescriptionError(f"{names[node]!r} is declared free, and none of its parts is in a link hung "
                                       f"from the world: part {self._name(index)!r} is {where}; declare free the "
                                       "assembly or part that holds the base")
            for joint in hung:
                joint.kind = "floating"

    def _zeroed(self, kinematics: dict[str, Any], links: list[Link], joints: list[Joint],
                poses: list[Pose]) -> list[Pose]:
        """The description taken at the mechanism state ``self.zero`` (the module's **The zero**): each moved
        joint's origin, limits, as-built value and coupling offset, every link's frame from the root, and the
        poses around it."""
        states = list((kinematics.get("configurations") or {}))
        if self.zero not in states:
            known = ", ".join(repr(name) for name in states)
            raise DescriptionError(f"no mechanism state {self.zero!r}: "
                                   + (f"the states are {known}" if states else "the document names none"))
        here = next((pose for pose in poses if pose.name == self.zero), None)
        if here is None:  # left out: it moves a joint of a loop (``_poses``)
            raise DescriptionError(f"mechanism state {self.zero!r} moves a joint of a loop, which has no pose without "
                                   "a solver: no description is taken at it")
        by_name = {joint.name: joint for joint in joints}
        shift = {name: _values(value) for name, value in here.values.items() if name in by_name}
        authored = (kinematics.get("configurations") or {})[self.zero]
        for name, moved in shift.items():
            joint = by_name[name]
            joint.origin = joint.origin @ motion(joint.kind, moved)
            joint.limits = tuple(tuple(None if bound is None else bound - moved[index] for bound in bounds)
                                 for index, bounds in enumerate(joint.limits))
            label_kind = self.pair_kinds.get(name)
            if label_kind is not None and name in authored:
                units = [UNITS[unit] for unit in label_kind["pair"].get("units") or ()]
                joint.as_built = tuple(value * unit for value, unit in zip(_values(authored[name]), units))
        followed = {joint.name: joint.follows for joint in joints if joint.follows is not None}  # as authored
        for joint in joints:
            if joint.follows is not None:
                leader, ratio, offset = joint.follows
                led = shift.get(leader, (0.0,))[0]
                joint.follows = (leader, ratio, offset + ratio * led - shift.get(joint.name, (0.0,))[0])
        # Every link where its joint now puts it at zero, from the root.
        frames = {links[0].name: links[0].frame}
        pending = [links[0].name]
        while pending:
            parent = pending.pop(0)
            for joint in joints:
                if joint.parent == parent:
                    frames[joint.child] = frames[parent] @ joint.origin
                    pending.append(joint.child)
        for link in links:
            link.frame = frames.get(link.name, link.frame)
        found = []
        for pose in poses:
            values: dict[str, float | tuple[float, ...]] = {}
            for name in [*pose.values, *(name for name in shift if name not in pose.values)]:
                joint = by_name[name]
                given = pose.values.get(name)
                if given is None and name in followed and followed[name][0] in pose.values:  # where its leader puts it
                    leader, ratio, offset = followed[name]
                    given = ratio * _values(pose.values[leader])[0] + offset
                old = _values(given) if given is not None else (0.0,) * len(shift.get(name, (0.0,)))
                moved = shift.get(name, (0.0,) * len(old))
                if joint.kind == "spherical":
                    turned = np.linalg.inv(motion("spherical", moved)) @ motion("spherical", old)
                    values[name] = _angles(turned)
                    continue
                around = tuple(value - by for value, by in zip(old, moved))
                values[name] = around[0] if len(around) == 1 else around
            found.append(Pose(pose.name, values))
        return found

    def _declared(self, index: int) -> dict[str, Any]:
        """What instance ``index``'s prototype declares beside its collision and frames (``document.DECLARED``)."""
        return self.prototypes[self.instances[index]["prototype"]]

    def _name(self, index: int) -> str:
        return self.instances[index]["path"].rsplit("/", 1)[-1]

    def _bodies(self, links: list[Link], joints: list[Joint]) -> None:
        """Each part declared a body a link of its own, fixed to the link it was made part of (the module's
        **Bodies**)."""
        for link in list(links[1:]):
            bodies = [index for index in link.parts if self._declared(index).get("body") is not None]
            if not bodies:
                continue
            kept = tuple(index for index in link.parts if index not in bodies)
            if not kept:
                kept = (bodies.pop(0),)
                self.warn(f"part {self._name(kept[0])!r} is declared a body and is all of link {link.name!r}: it "
                          "is that link, a body already")
            link.parts = kept
            at = links.index(link)
            for index in bodies:
                wanted = self._declared(index)["body"] or self._name(index)
                named = _unique(wanted, self.link_names | self.reserved)
                self.link_names.add(named)
                child = Link(named, self.worlds[index].copy(), parts=(index,))
                at += 1
                links.insert(at, child)
                joints.append(self._fixed(child.name, link, child))

    def _excludes(self, links: list[Link]) -> tuple[tuple[tuple[str, str], ...], tuple[tuple[str, str], ...]]:
        """The link pairs the parts' declarations say never collide (the module's **Drives and exclusions**), and
        the part pairs they name, each by its two occurrence paths, sorted: what a joint stop sweep sets aside
        (``ranges``), where a simulator filters the links."""
        owner = {index: at for at, link in enumerate(links) for index in link.parts}
        found: set[tuple[int, int]] = set()
        parts: set[tuple[str, str]] = set()
        for index, at in sorted(owner.items()):
            declared = self._declared(index)
            # A label names every part at or below a node of it; a shape, the path of its occurrence, that alone.
            named_by = [(label, [other for other in owner if label in self.instances[other]["path"].split("/")])
                        for label in declared.get("exclude") or ()]
            named_by += [(path, [other for other in owner if self.instances[other]["path"] == path
                                 or self.instances[other]["path"].startswith(path + "/")])
                         for path in declared.get("excludePaths") or ()]
            for label, named in named_by:
                if not named:
                    raise DescriptionError(f"part {self._name(index)!r} excludes {label!r}, which names no part or "
                                           "assembly of the document")
                for other in sorted({owner[other] for other in named}):
                    if other == at:
                        self.warn(f"part {self._name(index)!r} excludes {label!r}, which link {links[at].name!r} "
                                  "holds too: a body never collides with itself")
                        continue
                    found.add((min(at, other), max(at, other)))
                mine = str(self.instances[index]["path"])
                for other in named:
                    if owner[other] != at:
                        first, second = sorted((mine, str(self.instances[other]["path"])))
                        parts.add((first, second))
        return tuple((links[a].name, links[b].name) for a, b in sorted(found)), tuple(sorted(parts))

    def _drives(self, kinematics: dict[str, Any]) -> None:
        """Each pair's joint given the drive limits declared on the node holding its moving joint -- a part, or an
        assembly whose parts carry them (``document.DECLARED``'s ``up``) -- (the module's **Drives and
        exclusions**); a declaration no joint takes is warned, once per node that holds it."""
        blocks = kinematics["links"]

        def holder(index: int, bounds: dict[str, Any]) -> str:
            """The path of the node that holds the joint: the part's own, or an assembly ``up`` levels above it."""
            names = self.instances[index]["path"].split("/")
            return "/".join(names[:len(names) - int(bounds.get("up") or 0)])

        declared = {(holder(index, bounds), label) for block in blocks for index in block.get("instances") or ()
                    for label, bounds in (self._declared(index).get("drives") or {}).items()}
        for pair in kinematics.get("pairs") or ():
            joint = getattr(self, "pair_joints", {}).get(pair["label"])
            if joint is None:
                continue
            qualifier, _sep, label = pair["label"].rpartition(":")
            for index in blocks[pair["links"][0]].get("instances") or ():
                bounds = (self._declared(index).get("drives") or {}).get(label)
                if bounds is None:
                    continue
                path = holder(index, bounds)
                if qualifier and path != qualifier and not path.endswith("/" + qualifier):
                    continue
                declared.discard((path, label))
                if any(getattr(joint, key) is not None for key in DRIVE):
                    continue
                for key in DRIVE:
                    if bounds.get(key) is not None:
                        setattr(joint, key, float(bounds[key]))
        for path, label in sorted(declared):
            self.warn(f"{path.rsplit('/', 1)[-1]!r} limits joint {label!r}, which is no joint of the description: "
                      "the limits are left out")

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
            link = Link(self._link_name(parts, node["name"]), self.worlds[parts[0]].copy(), parts=parts)
            links.append(link)
            joints.append(self._fixed(link.name, links[0], link))

    def _mechanism(self, kinematics: dict[str, Any], links: list[Link], joints: list[Joint]) -> list[Closure]:
        """The mechanism's links from its ground, each by the pair that reaches it (see the module
        docstring), and the closures of its loops (``description``'s **Loops**)."""
        blocks = kinematics["links"]
        ground = int(kinematics.get("ground") or 0)
        built = [column_major(block["matrix"]) for block in blocks]
        as_built = {label: _values(value) for label, value in (kinematics.get("asBuilt") or {}).items()}
        pairs = kinematics.get("pairs") or []
        made: dict[int, Link] = {}

        def link(at: int, frame: np.ndarray) -> Link:
            parts = tuple(blocks[at].get("instances") or ())
            found = made[at] = Link(self._link_name(parts, blocks[at]["name"]), frame, parts=parts)
            links.append(found)
            return found

        # A pair's joint is named by its label, which poses and couplings name it by; a fixed joint
        # takes another name where a label holds its own.
        self.joint_names.update(pair["label"] for pair in pairs)
        base = link(ground, built[ground].copy())
        joints.append(self._fixed(kinematics.get("name") or self.structure["name"], links[0], base))
        self.pair_joints: dict[str, Joint] = {}
        self.pair_kinds: dict[str, dict[str, Any]] = {}
        self.virtual = _virtual(blocks, pairs, ground)
        for index, pair in enumerate(pairs):
            if not pair.get("frames") and index not in self.virtual:
                self.warn(f"pair {pair['label']!r} has no frames: the description leaves it out")
        order, closing = _spanning(pairs, ground, self.virtual)
        for index, forward in order:
            pair = pairs[index]
            first, second = pair["links"]
            at, other = (first, second) if forward else (second, first)
            joint, frame = self._joint(pair, made[at], built[first], built[second], as_built, forward)
            joint.child = link(other, frame).name
            joints.append(joint)
            self.pair_joints[pair["label"]] = joint
            self.pair_kinds[pair["label"]] = {"pair": pair, "forward": forward}
        pinions = {pairs[index]["links"][1] for index in self.virtual}
        for at in range(len(blocks)):
            if at not in made and at not in pinions:
                self.warn(f"link {blocks[at]['name']!r} is reached by no pair from the ground: it hangs fixed from "
                          f"{WORLD!r} where it was built")
                joints.append(self._fixed(blocks[at]["name"], links[0], link(at, built[at].copy())))
        closures = self._closures(pairs, closing, made, built, as_built)
        self._couplings(kinematics, {closure.name for closure in closures})
        return closures

    def _closures(self, pairs: list[dict[str, Any]], closing: list[tuple[int, bool, tuple[int, ...]]],
                  made: dict[int, Link], built: list[np.ndarray],
                  as_built: dict[str, tuple[float, ...]]) -> list[Closure]:
        """Each closing pair a closure: its joint from the link the tree reached it from, its frame on the
        other link where that link stands, the two checked to be one place as built (within the tolerance
        the mechanism reads every pair to: 1e-6 of the model's size in millimetres, at least 1)."""
        scale = max([1.0] + [float(np.abs(column_major(instance["matrix"])[:3, 3]).max()) / MM
                             for instance in self.instances])
        found = []
        for index, forward, loop in closing:
            pair = pairs[index]
            first, second = pair["links"]
            at, other = (first, second) if forward else (second, first)
            joint, frame = self._joint(pair, made[at], built[first], built[second], as_built, forward)
            here = made[at].frame @ joint.origin
            apart = np.linalg.inv(here) @ frame
            shift, turn = float(np.linalg.norm(apart[:3, 3])) / MM, float(np.abs(apart[:3, :3] - np.eye(3)).max())
            names = tuple(pairs[step]["label"] for step in loop)
            if shift > 1e-6 * scale or turn > 1e-6 * scale:
                rotation = apart[:3, :3]
                spin = (rotation[2, 1] - rotation[1, 2], rotation[0, 2] - rotation[2, 0], rotation[1, 0] - rotation[0, 1])
                angle = math.atan2(math.hypot(*spin) / 2, (float(np.trace(rotation)) - 1) / 2)
                raise DescriptionError(f"the loop through {', '.join(names)} does not close as built: joint "
                                       f"{joint.name!r} stands {shift:.3g} mm and {math.degrees(angle):.3g} deg from "
                                       "where its pair puts it")
            found.append(Closure(joint.name, joint.kind, made[at].name, made[other].name, joint.origin,
                                 np.linalg.inv(made[other].frame) @ frame, joint.limits, joint.as_built, names))
        return found

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

    def _couplings(self, kinematics: dict[str, Any], closing: set[str]) -> None:
        """Each coupling written on the joints that follow: every one from its first-named value
        (``value = ratio * leader``, around zero, in SI), a virtual pinion's from its first rack. A
        joint that closes a loop follows nothing and leads nothing: it is left out, and warned."""
        held = getattr(getattr(self.source, "mechanism", None), "couplings", None) or {}
        pinions = {(kinematics.get("pairs") or [])[index]["label"] for index in getattr(self, "virtual", set())}
        for name, coupling in (kinematics.get("couplings") or {}).items():
            if name in held:
                terms = [(label, index, ratio) for label, ratios in held[name].ratios.items()
                         for index, ratio in enumerate(ratios) if ratio]
            else:
                terms = [tuple(term) for term in coupling.get("terms") or () if term[2]]
            for label in sorted({term[0] for term in terms} & closing):
                self.warn(f"coupling {name!r} drives joint {label!r}, which closes a loop and is no joint of the "
                          "tree: the description leaves it out of the coupling")
            terms = [term for term in terms if term[0] not in pinions and term[0] not in closing]
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

    def _poses(self, kinematics: dict[str, Any], joints: list[Joint], closures: list[Closure]) -> list[Pose]:
        """The mechanism's named states around zero, in SI. A state that moves a joint of a loop has no pose
        without a solver: it is left out, and warned."""
        found = []
        as_built = {label: _values(value) for label, value in (kinematics.get("asBuilt") or {}).items()}
        looped = {label for closure in closures for label in closure.loop}
        for name, values in (kinematics.get("configurations") or {}).items():
            moved = sorted(label for label, value in values.items() if label in looped and any(
                abs(a - b) > 1e-9 for a, b in zip(_values(value), as_built.get(label, _values(value)))))
            if moved:
                self.warn(f"mechanism state {name!r} moves joint {moved[0]!r}, which is in a loop and has no pose "
                          "without a solver: the description leaves the state out")
                continue
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
        self.meshes, self.made = found, meshes(self.view)
        for index, made in self.made.items():
            prototype = self.prototypes[index]
            if prototype["key"] in found:
                continue
            positions = (np.asarray(made.positions, dtype=np.float64).reshape(-1, 3) * MM).astype(np.float32)
            normals = None if made.normals is None else np.asarray(made.normals, dtype=np.float32).reshape(-1, 3)
            found[prototype["key"]] = Mesh(prototype["key"], prototype["name"], positions,
                                           np.asarray(made.indices, dtype=np.uint32).reshape(-1, 3), normals)
        return found

    def _looks(self, instance: dict[str, Any], prototype: dict[str, Any]) -> tuple[Look, ...]:
        """A painted part's looks (``Visual.looks``), as the viewer draws it (``export.mesh.groups``): its faces by
        colour and material, the part's own look first, each look's triangles a mesh of its own added to the
        description's (``<key>#look<hash>``, named ``<prototype>_look<i>``); none for a part of one look."""
        if not prototype.get("faceColors") and not prototype.get("faceMaterials"):
            return ()
        from cad.engine.export.mesh import _material, groups, look_of

        made = self.made.get(instance["prototype"])
        whole = self.meshes.get(prototype["key"])
        faces = getattr(made, "faces", None)
        if made is None or whole is None or faces is None or not len(faces):
            return ()
        own = instance.get("color")
        looks = groups(made, prototype, own)
        if len(looks) < 2:
            return ()
        base = own if own is not None else prototype.get("color")
        mine = look_of(base, _material(prototype.get("material")))
        looks.sort(key=lambda found: found[0] != mine)  # the part's own look first, the rest as the faces have them
        found = []
        for at, ((rgba, held), indices) in enumerate(looks):
            triangles = np.asarray(indices, dtype=np.int64).reshape(-1, 3)
            used, remapped = np.unique(triangles, return_inverse=True)
            key = f"{prototype['key']}#look{hashlib.sha256(triangles.tobytes()).hexdigest()[:12]}"
            if key not in self.meshes:
                self.meshes[key] = Mesh(key, f"{prototype['name']}_look{at}", whole.positions[used],
                                        remapped.reshape(-1, 3).astype(np.uint32),
                                        None if whole.normals is None else whole.normals[used], open=True)
            named = (json.loads(held).get("material") or {}).get("name") if held else None
            found.append(Look(key, srgb(rgba), named or None))
        return tuple(found)

    def _decompositions(self, links: list[Link], meshes: dict[str, Mesh]) -> dict[tuple[str, str], list[str]]:
        """Each decomposed prototype's hulls (the module's **Geometry and mass**), by its key and its
        decomposition options (``_options``): two parts of one geometry cut with other options are cut apart.
        The keys of the hull meshes added to ``meshes``, ``<key>#hull<i>`` (``<key>#<options>#hull<i>`` where
        options are given) named ``<prototype>_hull<i>``, every one decomposed in one call (``hulls``: the
        engine's cache, else the coacd integration's CoACD in a process of its own)."""
        wanted: dict[tuple[str, str], dict[str, Any]] = {}
        for link in links[1:]:
            for index in link.parts:
                prototype = self.prototypes[self.instances[index]["prototype"]]
                if (prototype.get("collision") or self.collision_default) == "decomposed":
                    wanted.setdefault(self._cut(prototype), prototype)
        empty = [cut for cut in wanted if cut[0] not in meshes or not len(meshes[cut[0]].triangles)]
        for cut in empty:
            self.warn(f"part {wanted.pop(cut)['name']!r} is declared decomposed and has no triangles: it collides "
                      "as nothing")
        if not wanted:
            return {}
        from cad.engine.hulls import Failed, Unavailable, hulls

        cuts = list(wanted)
        try:
            made = hulls([(meshes[key].positions, meshes[key].triangles, self._options(wanted[(key, options)]))
                          for key, options in cuts], names=[str(wanted[cut]["name"]) for cut in cuts])
        except Unavailable as error:
            names = ", ".join(repr(wanted[cut]["name"]) for cut in cuts)
            raise DescriptionError(f"part {names} collides as convex hulls (collision 'decomposed'), which CoACD "
                                   f"makes: {error}; or declare it another collision") from None
        except Failed as error:
            named = repr(wanted[cuts[error.index]]["name"]) if error.index is not None else ", ".join(
                repr(wanted[cut]["name"]) for cut in cuts)
            raise DescriptionError(f"part {named} could not be decomposed (collision 'decomposed'): {error}") from None
        found: dict[tuple[str, str], list[str]] = {}
        for (key, options), pieces in zip(cuts, made):
            name = wanted[(key, options)]["name"]
            stem = key if options == "{}" else f"{key}#{hashlib.sha256(options.encode()).hexdigest()[:12]}"
            found[(key, options)] = []
            for at, (positions, triangles) in enumerate(pieces):
                hull = f"{stem}#hull{at}"
                meshes[hull] = Mesh(hull, f"{name}_hull{at}", positions, triangles)
                found[(key, options)].append(hull)
        return found

    def _options(self, prototype: dict[str, Any]) -> dict[str, Any]:
        """A decomposed prototype's options for CoACD, as ``hulls`` takes them: those its ``collision``
        declares (``max_hulls``, ``threshold``), or, decomposed by ``collision_default``, the declaration's
        default (at most ``MAX_HULLS`` hulls)."""
        if prototype.get("collision") != "decomposed":
            return {"maxHulls": MAX_HULLS}
        return dict(prototype.get("decomposition") or {})

    def _cut(self, prototype: dict[str, Any]) -> tuple[str, str]:
        """What one decomposition is of: a prototype's geometry key and its options as canonical JSON."""
        return prototype["key"], json.dumps(self._options(prototype), sort_keys=True, separators=(",", ":"))

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
                                       material.get("name") or None, path=instance["path"],
                                       looks=self._looks(instance, prototype)))
            kind = prototype.get("collision") or self.collision_default
            surface = tuple(float(value) for value in prototype.get("friction") or ())
            if kind == "mesh" or (kind == "decomposed" and not self.decompose):
                link.collisions.append(Collision(name, Geometry("mesh", placement, mesh=key), surface))
            elif kind == "decomposed":
                for at, hull in enumerate(self.hulls.get(self._cut(prototype), ())):
                    link.collisions.append(Collision(f"{name}_hull{at}", Geometry("mesh", placement, mesh=hull),
                                                     surface, part=name))
            elif kind != "none":
                frame, size = self._fit(key, prototype["name"], kind)
                link.collisions.append(Collision(name, Geometry(kind, placement @ frame, size=size), surface))
            for frame_name, values in sorted((prototype.get("frames") or {}).items()):
                named = frame_name
                if named in link.frames:
                    named = f"{name}/{frame_name}"
                    self.warn(f"link {link.name!r} holds frame {frame_name!r} twice: the one on {name} is "
                              f"{named!r}")
                link.frames[named] = placement @ column_major(values)
            rotation = placement[:3, :3]
            points = self._points(prototype)
            for mass, center, inertia in points:
                masses.append((mass, rotation @ center + placement[:3, 3], rotation @ inertia @ rotation.T))
            measured = self.masses.get(index, False)
            if measured is False:
                measured = self._mass(prototype, material)
            if measured is None:
                if not points and index not in self.masses:  # one below a declared mass is said there (``_masses``)
                    massless.append(name)
                continue
            mass, center, inertia = measured
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

    def _points(self, prototype: dict[str, Any]) -> list[tuple[float, np.ndarray, np.ndarray]]:
        """A prototype's point masses (``declarations.point_mass``): each mass (kg), point (m) and inertia
        about it (kg*m^2), in the prototype's frame."""
        found = []
        for _name, point in sorted((prototype.get("pointMasses") or {}).items()):
            at = column_major(point["at"])
            rotation = at[:3, :3]
            own = np.diag([float(value) for value in point.get("inertia") or (0.0, 0.0, 0.0)])
            found.append((float(point["grams"]) * 1e-3, at[:3, 3].copy(), rotation @ own @ rotation.T))
        return found

    def _masses(self) -> dict[int, tuple[float, np.ndarray, np.ndarray] | None]:
        """Each instance below a declared mass, its solids' mass (kg), centre (m) and inertia (kg*m^2) in its
        prototype's frame, scaled as the module's **Mass** says; None where it carries none."""
        chains: dict[int, list[tuple[int, ...]]] = {}
        names: dict[tuple[int, ...], str] = {}

        def walk(node: dict[str, Any], at: tuple[int, ...], above: list[tuple[int, ...]]) -> None:
            names[at] = node.get("name") or "the model"
            if "children" in node:
                for position, child in enumerate(node["children"]):
                    walk(child, at + (position,), above + [at])
            else:
                chains[int(node["instance"])] = above + [at]

        walk(self.structure["tree"], (), [])
        totals: dict[tuple[int, ...], float] = {}
        owner: dict[int, tuple[int, ...]] = {}
        for index, chain in chains.items():
            entries = self._declared(index).get("mass") or ()
            for up, grams in entries:
                if not 0 <= int(up) < len(chain):
                    raise DescriptionError(f"part {self._name(index)!r} is declared part of a mass {up} levels above "
                                           "it, which the tree does not hold")
                totals[chain[-1 - int(up)]] = float(grams)
            if entries:
                owner[index] = chain[-1 - int(min(int(up) for up, _grams in entries))]
        found: dict[int, tuple[float, np.ndarray, np.ndarray] | None] = {}
        for node in sorted(totals, key=len, reverse=True):
            grams = totals[node]
            said = f"{names[node]!r}, declared to weigh {grams:g} g,"
            inner = [other for other in totals if len(other) > len(node) and other[:len(node)] == node
                     and not any(len(node) < len(between) < len(other) and other[:len(between)] == between
                                 for between in totals)]
            own = [index for index, held in sorted(owner.items()) if held == node]
            fixed = sum(totals[other] for other in inner)
            fixed += sum(float(point["grams"]) for index in own
                         for point in (self._declared(index).get("pointMasses") or {}).values())
            solids: list[tuple[int, float, tuple[float, np.ndarray, np.ndarray]]] = []
            weighed = []
            for index in own:
                prototype = self._declared(index)
                material = (prototype.get("material") or {}).get("material") or {}
                weighed.append((index, self._density(prototype, material)))
            uniform = all(density is None for _index, density in weighed)
            unweighed = [index for index, density in weighed if density is None and not uniform]
            if unweighed:
                shown = ", ".join(repr(self._name(index)) for index in unweighed[:3]) + (
                    f" and {len(unweighed) - 3} more" if len(unweighed) > 3 else "")
                one = len(unweighed) == 1
                self.warn(f"{shown} below {said} {'has' if one else 'have'} no density, unlike the other parts "
                          f"there: {'it carries' if one else 'they carry'} none of the {grams:g} g, which they make "
                          f"up (give {'it' if one else 'them'} a material to share it)")
            for index, density in weighed:
                if density is None and not uniform:
                    found[index] = None
                    continue
                measured = self._measured(self._declared(index))
                if measured is None:
                    found[index] = None
                    continue
                solids.append((index, 1.0 if density is None else density, measured))
            weight = sum(volume * density * 1e-9 for _index, density, (volume, _c, _i) in solids)  # kg
            rest = (grams - fixed) * 1e-3  # kg
            slack = grams * 1e-12  # kg: a part in 10^9 of the total
            if weight > 0 and rest <= slack:
                raise DescriptionError(f"{said} holds point masses and inner masses of {fixed:g} g, which leave its "
                                       "own solids nothing to weigh")
            if weight <= 0 and abs(rest) > slack:
                if own:
                    raise DescriptionError(f"{said} has {grams - fixed:g} g left for its own parts after its point "
                                           "masses and inner masses, and they have no volume to carry it")
                raise DescriptionError(f"{said} holds inner masses and point masses of {fixed:g} g, and no solid of "
                                       "its own to make up the rest")
            scale = rest / weight if weight > 0 else 0.0
            for index, density, (volume, center, inertia) in solids:
                per_mm3 = density * scale * 1e-9
                found[index] = (volume * per_mm3, center * MM, inertia * per_mm3 * 1e-6)
        return found

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
        if kind == "cylinder":
            # A part turned about an axis (a pancake motor, a wheel, a disc) is a cylinder about it, however short:
            # the box's side along it the axis, the larger of the two across it the radius.
            turned = self.turned.get(key, -1)
            if turned == -1:
                turned = self.turned[key] = _turned_axis(self._shape(key), axes)
            if turned is not None:
                across = [at for at in order if at != turned]
                order = np.array([turned, *across])
        z, x = axes[order[0]], axes[order[1]]
        frame[:3, 0], frame[:3, 1], frame[:3, 2] = x, np.cross(z, x), z
        radius, length = float(halves[order[1]]), float(2 * halves[order[0]])
        if kind == "capsule":
            length = max(length - 2 * radius, 0.0)
        return frame, (radius, length)


#: The share of a part's surface its faces turned about one axis (cylinders and cones) must hold for a fitted cylinder to
#: take that axis rather than the part's longest side (``_turned_axis``), and how near (degrees) the axis must lie to
#: a side of the part's oriented bounding box.
TURNED = 0.25
TURNED_ALIGNED = 5.0


def _turned_axis(shape: Any, axes: list[np.ndarray]) -> int | None:
    """Which side of a part's oriented bounding box (``axes``, unit vectors) its axis of turning lies along, or None:
    the direction its cylindrical and conical faces share, weighed by their area, where those faces hold at least
    ``TURNED`` of its surface and the direction lies within ``TURNED_ALIGNED`` of a side. A housing turned about one
    axis is mostly such faces; a block with a hole or a boss is not."""
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.BRepGProp import BRepGProp
    from OCP.GeomAbs import GeomAbs_Cone, GeomAbs_Cylinder
    from OCP.GProp import GProp_GProps
    from OCP.TopAbs import TopAbs_FACE
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS

    if shape is None:
        return None
    total, by_side = 0.0, [0.0, 0.0, 0.0]
    explorer = TopExp_Explorer(shape, TopAbs_FACE)
    while explorer.More():
        face = TopoDS.Face(explorer.Current())
        props = GProp_GProps()
        BRepGProp.SurfaceProperties_s(face, props)
        area = props.Mass()
        total += area
        surface = BRepAdaptor_Surface(face)
        kind = surface.GetType()
        if kind in (GeomAbs_Cylinder, GeomAbs_Cone):
            axis = (surface.Cylinder() if kind == GeomAbs_Cylinder else surface.Cone()).Axis().Direction()
            direction = np.array([axis.X(), axis.Y(), axis.Z()])
            cosines = [abs(float(direction @ side)) for side in axes]
            nearest = int(np.argmax(cosines))
            if cosines[nearest] >= math.cos(math.radians(TURNED_ALIGNED)):
                by_side[nearest] += area
        explorer.Next()
    best = int(np.argmax(by_side))
    return best if total > 0 and by_side[best] >= TURNED * total else None


def _virtual(blocks: list[dict[str, Any]], pairs: list[dict[str, Any]], ground: int) -> set[int]:
    """The virtual pinions' pairs, by index: a revolute pair to a link, not the ground, that holds no part
    and that no other pair reaches (``mechanism``'s virtual pinion, a ``rack_and_pinion_pair``'s reference
    axis)."""
    touched: dict[int, int] = {}
    for pair in pairs:
        for end in set(pair["links"]):
            touched[end] = touched.get(end, 0) + 1
    return {index for index, pair in enumerate(pairs)
            if pair["type"] == "revolute" and pair["links"][1] != ground and not blocks[pair["links"][1]].get("instances")
            and touched.get(pair["links"][1]) == 1 and pair["links"][0] != pair["links"][1]}


def _spanning(pairs: list[dict[str, Any]], ground: int,
              skipped: set[int]) -> tuple[list[tuple[int, bool]], list[tuple[int, bool, tuple[int, ...]]]]:
    """The tree of ``description``'s **Loops**: each pair that reaches a link, ``(index, forward)`` in the
    order they are followed (breadth first from ``ground``, the pairs in their order; ``forward`` from its
    first link), and each pair that closes a loop, ``(index, forward, the loop's pairs)``, the loop from the
    ground's side. ``skipped``: pairs no tree holds (virtual pinions). A closing pair that is a slide is
    traded for the loop's turn or ball nearest it, which closes the loop in its place."""
    cut: set[int] = set()
    for _attempt in range(len(pairs) + 1):
        reached: dict[int, tuple[int, int] | None] = {ground: None}  # each link: (the pair, the link it came from)
        order: list[tuple[int, bool]] = []
        closing: list[tuple[int, bool, tuple[int, ...]]] = []
        used: set[int] = set()
        queue = [ground]
        while queue:
            at = queue.pop(0)
            for index, pair in enumerate(pairs):
                first, second = pair["links"]
                if index in used or at not in (first, second) or first == second:
                    continue
                used.add(index)
                if index in skipped or not pair.get("frames"):
                    continue
                other = second if at == first else first
                if index in cut or other in reached:
                    closing.append((index, at == first, ()))
                    continue
                reached[other] = (index, at)
                order.append((index, at == first))
                queue.append(other)

        def chain(link: int) -> list[int]:
            found = []
            came = reached.get(link)
            while came is not None:
                step, link = came
                found.append(step)
                came = reached.get(link)
            return found

        traded = None
        for row, (index, forward, _loop) in enumerate(closing):
            first, second = pairs[index]["links"]
            left, right = chain(first if forward else second), chain(second if forward else first)
            while left and right and left[-1] == right[-1]:
                left.pop()
                right.pop()
            closing[row] = (index, forward, (*reversed(left), index, *right))
            if traded is None and pairs[index]["type"] in ("prismatic", "cylindrical"):
                nearest = [step for pair_of in zip(left + [None] * len(right), right + [None] * len(left))
                           for step in pair_of if step is not None]
                traded = next((step for step in nearest if pairs[step]["type"] in ("revolute", "spherical")
                               and step not in cut), None)
        if traded is None:
            return order, closing
        cut.add(traded)
    return order, closing


def _leaves(node: dict[str, Any]) -> list[int]:
    if "children" not in node:
        return [node["instance"]]
    return [index for child in node["children"] for index in _leaves(child)]
