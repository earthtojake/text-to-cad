"""Joint zero is the servo-centre pose: upper arm standing, forearm level (the design's `zero`).

The revision layers place every part at the folded rest, so that is the pose they author. A
cadgen mate measures from wherever its child was built, and the viewer's Default pose is q=0
(cadgen kinematics: "0 is always the artifact as written"). So zero is moved by re-placing the
finished arm: every occurrence takes the forward kinematics of ZERO_FROM_REST about the as-built
axes, each mate's axis moves with its parent link, and limits and presets shift by the same
angles. The folded rest becomes the `rest` preset (shoulder pitch +90, elbow pitch -90).

Both pitch axes are parallel to Y, so past the elbow the two rotations cancel: the forearm, wrist,
gripper and camera translate but keep their orientation, and link-local datums (the claw-tip TCP,
the camera frame) do not change. Joint zero is also where every servo sits mid-travel: the arm.json
template's ticks centre each joint's range on 2048 (control/calibration.py).
"""
from __future__ import annotations

from dataclasses import asdict, is_dataclass

__all__ = ["ZERO_FROM_REST", "rezeroed_kinematics", "posed_at_zero", "carried_by"]

# The as-built (folded rest) joint values that become joint zero, degrees.
ZERO_FROM_REST = {"shoulderPitch": -90.0, "elbowPitch": 90.0}


def _rows(kinematics) -> list[dict]:
    return [asdict(m) if is_dataclass(m) else dict(m) for m in kinematics["mates"]]


def _label(ref: str) -> str:
    return ref[1:] if ref.startswith("#") else ref


def carried_by(kinematics) -> dict[str, list[str]]:
    """Every occurrence a mate names -> the revolute mates that carry it, base first."""
    rows = _rows(kinematics)
    up = {_label(r["child"]): r for r in rows}
    out = {}
    for label in {_label(r[side]) for r in rows for side in ("child", "parent")}:
        chain, node = [], label
        while node in up:
            if up[node]["kind"] == "revolute":
                chain.append(up[node]["name"])
            node = _label(up[node]["parent"])
        out[label] = chain[::-1]
    return out


def _rotation(axis: dict, degrees: float):
    from math import radians
    from OCP.gp import gp_Ax1, gp_Dir, gp_Pnt, gp_Trsf
    t = gp_Trsf()
    t.SetRotation(gp_Ax1(gp_Pnt(*axis["origin"]), gp_Dir(*axis["dir"])), radians(degrees))
    return t


def _chain_transforms(kinematics) -> dict[tuple[str, ...], object]:
    """chain (tuple of mate names, base first) -> gp_Trsf of ZERO_FROM_REST along it: the product
    of exponentials about the as-built axes."""
    from OCP.gp import gp_Trsf
    axes = {r["name"]: r["axis"] for r in _rows(kinematics) if r["kind"] == "revolute"}
    cache = {}
    for chain in {tuple(c) for c in carried_by(kinematics).values()}:
        t = gp_Trsf()
        for name in chain:
            if ZERO_FROM_REST.get(name):
                t = t.Multiplied(_rotation(axes[name], ZERO_FROM_REST[name]))
        cache[chain] = t
    cache.setdefault((), gp_Trsf())
    return cache


def rezeroed_kinematics(kinematics: dict) -> dict:
    """The as-built kinematics measured from ZERO_FROM_REST: axes carried with their parent
    links, limits and presets shifted."""
    from OCP.gp import gp_Dir, gp_Pnt
    from lib.mates import revolute
    carried = carried_by(kinematics)
    moves = _chain_transforms(kinematics)
    mates = []
    for mate, row in zip(kinematics["mates"], _rows(kinematics)):
        if row["kind"] == "revolute":
            t = moves[tuple(carried[_label(row["parent"])])]
            o = gp_Pnt(*row["axis"]["origin"]).Transformed(t)
            d = gp_Dir(*row["axis"]["dir"]).Transformed(t)
            z = ZERO_FROM_REST.get(row["name"], 0.0)
            lo, hi = row["limits"]["value"]
            mate = revolute(row["name"], parent=row["parent"], child=row["child"],
                            origin=[round(v, 9) for v in (o.X(), o.Y(), o.Z())],
                            direction=[round(v, 12) + 0.0 for v in (d.X(), d.Y(), d.Z())],
                            limits=(lo - z, hi - z))
        mates.append(mate)
    poses = {}
    for name, pose in kinematics.get("poses", {}).items():
        dofs = dict.fromkeys([*pose, *ZERO_FROM_REST])
        poses[name] = {dof: float(pose.get(dof, 0.0)) - ZERO_FROM_REST.get(dof, 0.0) + 0.0 for dof in dofs}
    return {**kinematics, "mates": mates, "poses": poses}


def posed_at_zero(assembly, kinematics: dict):
    """``assembly`` (built at the folded rest) re-placed at joint zero, its tree unchanged.

    ``kinematics`` is the AS-BUILT data. An occurrence a mate names moves with the mates that
    carry it; any other occurrence moves with its nearest named ancestor (an occurrence id covers
    its subtree), which is how the viewer and the clips move them too. The occurrences move
    into the result, so ``assembly`` is consumed: read nothing from it afterwards."""
    import build123d as b
    from OCP.TopLoc import TopLoc_Location
    carried = carried_by(kinematics)
    moves = _chain_transforms(kinematics)

    def loc(trsf):
        return b.Location(TopLoc_Location(trsf))

    def rebuild(node, parent_world, parent_chain):
        chain = tuple(carried.get(node.label, parent_chain))
        # read before regrouping: handing a compound's children to a new compound makes
        # build123d rebuild the old one, which resets its location
        own = node.location
        world = parent_world * own
        children = list(node.children or ())
        if chain == parent_chain and not children:
            return node
        # relative change: parent_world^-1 * T(parent)^-1 * T(node) * parent_world
        delta = (parent_world.inverse() * loc(moves[parent_chain]).inverse()
                 * loc(moves[chain]) * parent_world)
        if not children:
            q = b.Compound.cast(node.wrapped.Moved(delta.wrapped))
            q.label, q.color = node.label, node.color
            return q
        kids = [rebuild(c, world, chain) for c in children]
        q = b.Compound(children=kids, label=node.label, color=node.color)
        q.move(delta * own)
        return q

    root_chain = tuple(carried.get(assembly.label, ()))
    assert root_chain == (), ("the assembly root is carried by a joint", root_chain)
    return rebuild(assembly, b.Location(), ())
