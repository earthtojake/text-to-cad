"""The arm's mates as build123d joints on the built occurrences.

`tom.py` builds the arm, places it at joint zero, and hands its final mates (`lib/mates.py`
records, axes at joint zero) to `author_joints`. Each mate becomes a pair of joints, named after
the mate, on the occurrences its `#parent`/`#child` refs label:

- revolute: a `RevoluteJoint` on the parent about the mate's axis, with the mate's range, and a
  `RigidJoint` on the child at that joint's own frame (the plane build123d makes of the axis in
  the parent's frame), so the as-built pose is joint zero;
- fastened: a `RigidJoint` on each, at the child's own origin.

Every frame is given in its part's own coordinates (the occurrences sit at different depths of the
tree, so a world datum is carried into each part's frame first). `connect_to` then places the child
at angle 0: its as-built pose. build123d's `connect_to` composes LOCAL locations, so it can only
re-place a child whose enclosing compound sits where the parent's does; where it would move the
child off its as-built pose, the child keeps its pose and the mate is reported as `unplaced`.
"""
from __future__ import annotations

from dataclasses import asdict, is_dataclass

import build123d as bd

__all__ = ["author_joints"]


def _rows(kinematics) -> list[dict]:
    return [asdict(m) if is_dataclass(m) else dict(m) for m in kinematics["mates"]]


def _occurrences(root):
    """label -> (node, world location of its enclosing compound), first occurrence wins."""
    found = {}

    def walk(node, enclosing):
        if node.label and node.label not in found:
            found[node.label] = (node, enclosing)
        world = enclosing * node.location
        for child in node.children or ():
            walk(child, world)

    walk(root, bd.Location())
    return found


def _same(a: bd.Location, b: bd.Location, tol: float = 1e-6) -> bool:
    ta, tb = a.wrapped.Transformation(), b.wrapped.Transformation()
    return all(abs(ta.Value(r, c) - tb.Value(r, c)) < tol for r in (1, 2, 3) for c in (1, 2, 3, 4))


def author_joints(arm, kinematics) -> dict[str, list[str]]:
    """Author every mate of ``kinematics`` on ``arm`` (built at the mates' zero). Returns the
    mates by outcome: ``placed`` (connect_to kept the as-built pose), ``unplaced`` (joints
    authored, connect_to would have moved the child, so the child kept its pose), ``missing``
    (a ref that labels no occurrence)."""
    nodes = _occurrences(arm)
    report = {"placed": [], "unplaced": [], "missing": []}
    for row in _rows(kinematics):
        parent = nodes.get(row["parent"].lstrip("#"))
        child = nodes.get(row["child"].lstrip("#"))
        if parent is None or child is None:
            report["missing"].append(row["name"])
            continue
        (p, p_enclosing), (c, c_enclosing) = parent, child
        p_world, c_world = p_enclosing * p.location, c_enclosing * c.location
        # A world datum, in the frame build123d's joint constructors read: the part's own
        # location times its world inverse.
        in_p = lambda datum: p.location * p_world.inverse() * datum  # noqa: E731
        in_c = lambda datum: c.location * c_world.inverse() * datum  # noqa: E731
        name = row["name"]
        if row["kind"] == "revolute":
            origin, direction = row["axis"]["origin"], row["axis"]["dir"]
            frame = bd.Plane(origin=origin, z_dir=direction).location
            axis_frame = in_p(frame)
            bd.RevoluteJoint(name, p, axis=bd.Axis(axis_frame.position, axis_frame.to_axis().direction),
                             angular_range=tuple(row["limits"]["value"]))
            # The child's frame is the revolute joint's own: the plane build123d makes of the axis in
            # the PARENT's frame, whose X is that frame's default for the axis, not the world plane's.
            # A frame built from the world datum instead turns about the axis by the angle between
            # the two X's, so the as-built pose would be that angle, not joint zero, and outside a
            # narrow range (elbowRoll's) no value of the pair.
            joint_frame = p_world * p.joints[name].relative_axis.location
            bd.RigidJoint(name, c, in_c(joint_frame))
            connect = lambda: p.joints[name].connect_to(c.joints[name], angle=0.0)  # noqa: E731
        else:
            frame = c_world
            bd.RigidJoint(name, p, in_p(frame))
            bd.RigidJoint(name, c, in_c(frame))
            connect = lambda: p.joints[name].connect_to(c.joints[name])  # noqa: E731
        before = c.location
        connect()
        if _same(c.location, before):
            report["placed"].append(name)
        else:
            c.locate(before)
            report["unplaced"].append(name)
    return report
