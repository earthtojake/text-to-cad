"""The Robot Studio SO-101 follower arm, from its maker's assembly STEP to a robot description.

The benchmark's question is how far text-to-cad's process gets from a robot maker's raw CAD to a
MuJoCo description without copying anything from a hand-made one. Every number here comes from
the STEP's geometry, the STEP's materials, or a physical source named beside it; Menagerie's and
the maker's URDF/MJCF were read only for the link and joint NAMES and which printed parts make
which link (the comparison matches by name).

What the model does (``notes/so101.md`` records why, and what was tried):

1. Reads ``SO101 Assembly.step`` (``step.read``): 97 occurrences under the root, in the pose the
   maker saved -- the arm stretched out level along -Y, the moving jaw open, standing at 90 degrees
   to the static jaw. That pose is every joint's zero.
2. Groups the leaves into links. The one human input is ``PRINTED``: which printed parts form
   which link. Every other leaf goes to a link by geometry (``lib/step_links.py``): its surface
   samples within ``TOUCH`` mm of a link's printed parts, the link it touches most. A servo's housing
   (its three case shells, ``CASE``) decides the servo's body, the motor, board and gears inside it
   following; its horns (``HORN``) go to the link they touch most, never the housing's.
3. Finds each joint FROM GEOMETRY: the servo whose housing one link holds and whose drive horn the
   other link touches is the joint between them, about the axis of the horn's rim (its largest
   cylindrical face, ``BRepAdaptor_Surface``), pointing out of the servo through the horn. The
   moving jaw is screwed to the gripper servo's horn, so its pivot is that axis too.
4. Builds the mechanism where the parts stand: each link a sub-assembly, a ``RevoluteJoint`` on the
   parent's at the world axis, a ``RigidJoint`` on the child's at the axis' plane, connected at 0.
5. Gives every part what a simulator needs: an effective density for the printed parts (the maker's
   print settings), a calibrated one for the servo bodies (the servo's published mass), the STEP's
   own materials for metal; collision shapes per part; a ``tcp`` frame at the static jaw's tip.

Limits come from a self-collision sweep of the exported description (``so101_ranges.py``).
"""

from __future__ import annotations

import math
import re
from pathlib import Path

import build123d as bd
from cad import model, step
from cad.build123d import collision, frame

from lib.step_links import (Printed, assign, centroid, cylinder_axes, leaves, mesh, nearest_link, printed_density,
                            volume_and_area)

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent  # models/mujoco
STEP_FILE = ROOT / "upstream/so101/STEP/SO101/SO101 Assembly.step"
OUT = ROOT / "out/so101"

# The human input: which printed parts (top-level occurrences of the STEP) make which link, named as
# Menagerie names its bodies. Read from the maker's URDF (which meshes each link holds), not its numbers.
PRINTED = {
    "base": ("Base_SO101 v12:1", "Base_08p v18:1", "WaveShare_Mounting_Plate_SO101 v4:1"),
    "shoulder": ("Rotation_Pitch_SO101 v8:1", "Motor_holder_SO101_Base v6:1"),
    "upper_arm": ("Upper_arm_SO101 v9:1",),
    "lower_arm": ("Under_arm_SO101 v12:1", "Motor_holder_SO101_Wrist v8:1"),
    "wrist": ("Wrist_Roll_Pitch_SO100 v15:1",),
    "gripper": ("Wrist_Roll_Follower_SO101 v10:1",),
    "moving_jaw_so101_v1": ("Moving_Jaw_SO101 v3:1",),
}
# The official joint names, by the pair of links a servo turns (parent holds the housing, child the horn).
JOINTS = {
    ("base", "shoulder"): "shoulder_pan",
    ("shoulder", "upper_arm"): "shoulder_lift",
    ("upper_arm", "lower_arm"): "elbow_flex",
    ("lower_arm", "wrist"): "wrist_flex",
    ("wrist", "gripper"): "wrist_roll",
    ("gripper", "moving_jaw_so101_v1"): "gripper",
}
# Occurrences left out of the robot, by the start of their name:
LEFT_OUT = {
    # The driver board stands 85 mm under the base's foot, 75 mm behind it: not mounted on the arm in
    # this STEP (exploded or forgotten). Every one of its ~120 leaves is "Steel" (Fusion's default).
    "Bus Servo Adapter": "unmounted driver board",
    # Servo cables (swept bundles, Fusion's default "Steel"): flexible, and two of five cross a joint,
    # so no rigid link holds them. Their mass is estimated in the notes.
    "Component": "servo cable",
}
# The servo sub-assembly's leaves (Feetech SCS215/ST3215 model), read by name: the case shells and
# the metal horns (金属舵盘 = metal servo horn; 驱动 = drive, on the output spline; 从动 = idler).
SERVO = "ST3215 Servo"
CASE = ("ZK_", "SG-ZIJI", "XG-ZIJI")
HORN = "舵盘"
DRIVE = "驱动"
TOUCH = 0.5  # mm: a sample this close to a printed part touches it (mesh chords and sample spacing below it)

# Mass. Printed parts: the maker's print settings (SO-ARM100 README, "Printing the Parts": PLA+,
# 0.4 mm nozzle at 0.2 mm layers, 15 % infill). PLA's density, 1240 kg/m^3, is bd_materials' PLA
# (NatureWorks Ingeo's published 1.24 g/cm^3). The solid skin is 0.8 mm: two 0.4 mm perimeters, and
# four 0.2 mm solid layers top and bottom (the slicers' defaults for a 0.4 mm nozzle).
PLA_DENSITY = 1240.0
PRINT_SHELL = 0.8
PRINT_INFILL = 0.15
# Servo: the ST3215's published mass, 55 g (Feetech STS3215 / Waveshare ST3215 specification). The
# STEP's servo is a simplified model whose solids overlap (its leaves hold 41.3 cm^3 inside a
# 24.7 x 45.2 x 35 mm case, 39 cm^3), so its PPS density (1637 kg/m^3) would weigh 78 g. The body's
# density is set so a servo with both STEP horns (steel, kept) weighs the published mass.
SERVO_MASS = 55.0  # g
# Molex 50-37-5033 (KK 254 crimp housing, 3 circuits): nylon 6/6 (Molex's datasheet); the STEP gives
# it no material. bd_materials' nylon density.

# Joint limits, degrees around the STEP pose: physical stops found by so101_ranges.py (a self-collision
# sweep of the exported description, each joint alone, the others at zero). None: no stop in a turn.
LIMITS: dict[str, tuple[float, float] | None] = {
    "shoulder_pan": None,
    "shoulder_lift": None,
    "elbow_flex": None,
    "wrist_flex": None,
    "wrist_roll": None,
    "gripper": None,
}


def _slug(text: str) -> str:
    """An ASCII name for a label: the formats name meshes and geoms by it."""
    text = text.replace(HORN, "horn").replace(DRIVE, "drive").replace("从动", "idler").replace("金属", "")
    return re.sub(r"_+", "_", re.sub(r"[^A-Za-z0-9]+", "_", text)).strip("_").lower()


def _servo_density(servo: list) -> float:
    """The body density (kg/m^3) that makes a two-horn servo weigh ``SERVO_MASS``, horns at the STEP's
    own density."""
    body = sum(volume_and_area(leaf.shape)[0] for leaf in servo if HORN not in leaf.name)  # mm^3
    horns = sum(volume_and_area(leaf.shape)[0] * leaf.shape.material.material.density * 1e-6  # g
                for leaf in servo if HORN in leaf.name)
    return (SERVO_MASS - horns) / body * 1e6


def _material(part, finished) -> None:
    """Set a part's material, keeping the colour the STEP gave it."""
    color = part.color
    part.material = finished
    part.color = color


@model
def so101():
    from bd_materials import plastics

    tree = step.read(STEP_FILE)
    every = leaves(tree)
    kept = [leaf for leaf in every if not any(leaf.top.startswith(prefix) for prefix in LEFT_OUT)]
    owner = {name: link for link, names in PRINTED.items() for name in names}
    missing = {name for name in owner} - {leaf.top for leaf in kept}
    if missing:
        raise ValueError(f"printed parts not in the STEP: {sorted(missing)}")

    # Links: printed parts by name, everything else by contact.
    printed = Printed([(owner[leaf.top], leaf) for leaf in kept if leaf.top in owner])
    servos: dict[str, list] = {}
    for leaf in kept:
        if leaf.top in owner:
            leaf.link, leaf.why = owner[leaf.top], "printed"
        elif leaf.top.startswith(SERVO):
            servos.setdefault(leaf.top, []).append(leaf)
        else:
            leaf.link = assign(leaf, printed, touch=TOUCH)
            leaf.why = "touch"
            if leaf.link is None:
                leaf.link, distance = nearest_link(leaf, printed)
                leaf.why = f"nearest, {distance:.1f} mm"
    joints = {}
    for top, servo in servos.items():
        cases = [leaf for leaf in servo if leaf.name.startswith(CASE)]
        touches: dict[str, int] = {}
        for leaf in cases:
            assign(leaf, printed, touch=TOUCH)
            for link, count in leaf.touches.items():
                touches[link] = touches.get(link, 0) + count
        holder = max(touches, key=touches.get)
        horns = [leaf for leaf in servo if HORN in leaf.name]
        for leaf in servo:
            leaf.link, leaf.why = holder, f"{top} body"
        for leaf in horns:
            leaf.link, leaf.why = assign(leaf, printed, touch=TOUCH, exclude=(holder,)), f"{top} horn"
        drive = next(leaf for leaf in horns if DRIVE in leaf.name)
        name = JOINTS.get((holder, drive.link))
        if name is None:
            raise ValueError(f"{top}: its housing is on {holder} and its horn on {drive.link}, no joint of JOINTS")
        # The output axis: the drive horn's rim, its largest cylinder, pointing out of the servo.
        radius, at, direction, _area = cylinder_axes(drive.placed())[0]
        body = centroid(next(leaf for leaf in servo if leaf.name.startswith("ZK_")).placed())
        if direction @ (centroid(drive.placed()) - body) < 0:
            direction = -direction
        joints[name] = (holder, drive.link, at, direction, servo)

    # Parts: placed where they stand, named, given materials and collision shapes.
    servo_density = _servo_density(next(iter(servos.values())))
    links: dict[str, list] = {link: [] for link in PRINTED}
    taken: set[str] = set()
    for leaf in kept:
        part = leaf.placed()
        if leaf.top.startswith(SERVO):
            label = f"{_slug(leaf.top.replace('ST3215 Servo v2', 'st3215'))}_{_slug(leaf.name)}"
        elif leaf.top in owner or leaf.name == leaf.top:
            label = _slug(leaf.top)
        else:
            label = f"{_slug(leaf.top)}_{_slug(leaf.name)}"
        while label in taken:
            label += "_"
        taken.add(label)
        part.label = label
        if leaf.why == "printed":
            volume, area = volume_and_area(part)
            density = printed_density(volume, area, solid=PLA_DENSITY, shell=PRINT_SHELL, infill=PRINT_INFILL)
            _material(part, plastics.pla(density=round(density, 1)))
            collision(part, "mesh")  # MuJoCo collides its convex hull
        elif leaf.top.startswith(SERVO) and HORN not in leaf.name:
            _material(part, plastics.pps(density=round(servo_density, 1)))
            collision(part, "box" if leaf.name.startswith(CASE) else "none")
        elif leaf.top.startswith("050375033"):
            _material(part, plastics.nylon())
            collision(part, "none")
        else:  # screws, nuts, horns: the STEP's own steel
            collision(part, "none")
        links[leaf.link].append(part)

    assemblies = {link: bd.Compound(children=parts, label=link) for link, parts in links.items()}

    # The static jaw's tip: the centroid of the gripper's printed part's last 8 mm along the wrist
    # roll axis (the jaw's length), a frame whose Z points out of the jaw and X along the jaw's pivot.
    follower = next(part for part in links["gripper"] if part.label == _slug(PRINTED["gripper"][0]))
    roll, pivot = joints["wrist_roll"][3], joints["gripper"][3]
    vertices, _faces = mesh(follower, 0.5, 0.5)
    reach = vertices @ roll
    tip = vertices[reach > reach.max() - 8.0].mean(axis=0)
    x_dir = pivot - (pivot @ roll) * roll
    world = bd.Location(bd.Plane(origin=tuple(tip), x_dir=tuple(x_dir), z_dir=tuple(roll)))
    frame(follower, "tcp", follower.location.inverse() * world)

    for name, (parent, child, at, direction, _servo) in joints.items():
        axis = bd.Axis(tuple(at), tuple(direction))
        limits = LIMITS.get(name)
        bd.RevoluteJoint(name, assemblies[parent], axis=axis,
                         angular_range=limits if limits else (-math.inf, math.inf))
        bd.RigidJoint(name, assemblies[child], bd.Plane(origin=axis.position, z_dir=axis.direction).location)
    for parent, child in JOINTS:
        name = JOINTS[(parent, child)]
        assemblies[parent].joints[name].connect_to(assemblies[child].joints[name], angle=0)  # as built: the STEP pose
    return bd.Compound(children=list(assemblies.values()), label="so101")


if __name__ == "__main__":
    import time

    started = time.time()
    arm = so101()
    built = time.time()
    OUT.mkdir(parents=True, exist_ok=True)
    arm.export(OUT / "so101.xml", OUT / "so101.urdf", OUT / "so101.sdf")
    print(f"built in {built - started:.1f} s, exported in {time.time() - built:.1f} s")
