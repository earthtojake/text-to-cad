"""Trossen WidowX AI (follower), from Trossen's own STEP to a robot description.

    python src/wxai.py      # builds the model, exports out/wxai/export/wxai.xml, wxai.urdf

The model READS the maker's assembly STEP (``upstream/wxai/wxai_follower.step``, fetched by
``src/fetch.py wxai``) and adds only what a careful engineer would: which parts move together (the
links), the joints found on the geometry, materials, limits from Trossen's published
specification, and two named frames found on the geometry. No number is copied from Trossen's URDF
or from MuJoCo Menagerie's ``trossen_wxai``; their link and joint NAMES and their sign conventions
are used so the comparison matches by name. ``notes/wxai.md`` says what was tried and what it gave.

The STEP: 15 occurrences, one simplified ("dummy") solid per link, all at the arm's folded zero
pose (the driver's sleep pose: every joint 0, the gripper closed with its pads touching), so the STEP
pose IS the simulator's zero and every part is built where it stands.
"""

from __future__ import annotations

from pathlib import Path

import build123d as bd
from bd_materials import FinishedMaterial, metals, plastics
from bd_materials.core import RangeMaterial
from cad import model, step
from cad.build123d import frame, limits, mechanism_state
from threejs_materials import PbrProperties

from lib.step_axes import cylinder_lines, free_directions, free_travel, shared_axis

ROOT = Path(__file__).resolve().parent.parent  # models/mujoco
STEP = ROOT / "upstream" / "wxai" / "wxai_follower.step"
OUT = ROOT / "out" / "wxai"

# The STEP's occurrences by what each is (its labels are the CAD's file names), in the official link names.
PARTS = {
    "base_link": "base_link dummy:step:1:1",
    "link_1": "link_1 dummy.step:1",
    "link_2": "link_2 dummy.step:1",              # a compound of 3 solids, no material in the STEP
    "link_3": "link_3 dummy.step:1",
    "link_4": "link_4 dummy.step:1",              # stands 0.40 mm off its bearings at both ends (see JOINTS)
    "link_5": "link_5:1",
    "link_6": "link_6 standard dummy.step:1",     # wrist + gripper body: rails, end stops, motor housing
    "carriage_right": "gripper_leader_right:1",   # at -Y: a linear-guide carriage with its rack arm
    "carriage_left": "gripper_leader_right:2",    # the same part turned a half turn about X, at +Y
    "gripper_left": "103107032_01.step:1",        # the finger at +Y
    "gripper_right": "103107033_01.step:1",       # the finger at -Y
    "gripper_sock_left": "gripper sock left.step:1",    # the fingertip pads ("socks"), touching at Y=0
    "gripper_sock_right": "gripper sock right.step:1",
    "camera_mount_d405": "camera mount dummy.STEP:1",   # a saddle plate on link_6 (a nested occurrence)
    "camera_housing_d405": "103107028_03 v2:1",   # the tilted shroud the D405 sits in (no camera in the STEP)
}

# The revolute joints: (parent, child, sign, whose bearing line is the axis). The axis LINE is the
# cylinder line the two parts share (lib/step_axes.shared_axis): every one found, none assumed. Its
# position along the line is the child's occurrence origin projected onto it (the frame Trossen placed
# at each joint, which lies on the bearing line within 0.07 mm for all but link_4: see notes).
# The SIGN is a convention where the range is symmetric (joint_0, 3, 4, 5: Trossen's, so values compare
# by name) and geometry where it is not: joint_1's 0..180 and joint_2's 0..135 (the spec's ranges) only
# fit the folded zero pose one way -- +Y lifts link_2 from lying back to standing up, -Y about joint_2
# unfolds link_3 upward off link_2 -- the other way drives each link through the one below it.
# "parent" / "child": link_4 is the one part off the chain (0.40 mm), so joint_3 takes link_3's bore
# and joint_4 link_5's bore, each the line its neighbours agree on.
JOINTS = {
    "joint_0": ("base_link", "link_1", +1, "parent"),
    "joint_1": ("link_1", "link_2", +1, "parent"),
    "joint_2": ("link_2", "link_3", -1, "parent"),
    "joint_3": ("link_3", "link_4", -1, "parent"),
    "joint_4": ("link_4", "link_5", -1, "child"),
    "joint_5": ("link_5", "link_6", +1, "parent"),
}

# Joint limits, degrees: Trossen's published WidowX AI specification, "Joint limits" table,
# https://docs.trossenrobotics.com/trossen_arm/main/specifications/wxai.html (read 2026-11-08):
# joint 0 -180..180, 1 0..180, 2 0..135, 3 -90..90, 4 -90..90, 5 -180..180. (The v1.5 page,
# https://docs.trossenrobotics.com/trossen_arm/v1.5/specifications.html, has joint 0 at +-175 and
# joint 2 at 0..270: the current page is taken.)
LIMITS = {
    "joint_0": (-180.0, 180.0),
    "joint_1": (0.0, 180.0),
    "joint_2": (0.0, 135.0),
    "joint_3": (-90.0, 90.0),
    "joint_4": (-90.0, 90.0),
    "joint_5": (-180.0, 180.0),
}

# The drives' limits, from the same table: velocity (rad/s) and effort (N*m, nominal) per joint; and the
# gripper's "Max Gripping Force", 100 N, as each carriage's effort (the table gives the gripper no speed).
DRIVES = {
    "joint_0": (6.2832, 27.0),
    "joint_1": (6.2832, 27.0),
    "joint_2": (6.2832, 27.0),
    "joint_3": (9.4248, 7.0),
    "joint_4": (9.4248, 7.0),
    "joint_5": (9.4248, 7.0),
}
GRIPPER_FORCE = 100.0  # N

# Each carriage's travel from closed (pads touching, the STEP pose) to open, mm: MEASURED on the CAD by
# a self-collision sweep (``measure_gripper()`` below: lib/step_axes.free_travel of the carriage, its
# finger and its pad along its slide against link_6, until the interference grows: the carriage
# reaches link_6's end stop) = 22.0 mm each side. Cross-check: 2 x 22.0 = 44 mm between the fingers,
# the "gripper stroke" 0.044 m of the v1.5 specification page (the current page says 0.04 m).
GRIPPER_TRAVEL = 22.0

# Mass. The STEP's materials are not physical: every part is "Steel" (7850 kg/m^3 declared; read by
# the engine as 7.85, see notes) but link_2 and the camera mount, which have none, and every part is
# a filled dummy solid -- 17.4 kg as steel against a published 4 kg. Trossen's specification gives
# the arm's weight: "Weight 4 kg" (same page as LIMITS), taken as everything in this STEP (arm and
# gripper; the D405 camera itself is not in the STEP). The parts whose material is plain are given
# it from the catalogue; the seven actuated links (aluminium housings around motors and gearboxes,
# drawn as filled envelopes) share one effective density: the spec's mass less the plain parts',
# over the links' volume.
SPEC_MASS = 4.0  # kg, Trossen's specification (above)


def _finish(material, name: str, color: str, metalness: float, roughness: float) -> FinishedMaterial:
    return FinishedMaterial(material, pbr=PbrProperties.create(name, color=color, metalness=metalness,
                                                                 roughness=roughness))


PLAIN = {  # part -> its catalogue material: what each is, from its shape and the product
    "carriage_left": lambda: _finish(metals.aluminum().material, "Machined aluminium carriage", "#3a3a3c", 0.8, 0.45),
    "carriage_right": lambda: _finish(metals.aluminum().material, "Machined aluminium carriage", "#3a3a3c", 0.8, 0.45),
    "gripper_left": lambda: _finish(plastics.nylon().material, "PA12 finger", "#222222", 0.0, 0.7),
    "gripper_right": lambda: _finish(plastics.nylon().material, "PA12 finger", "#222222", 0.0, 0.7),
    "gripper_sock_left": lambda: _finish(plastics.tpu().material, "TPU fingertip pad", "#111111", 0.0, 0.9),
    "gripper_sock_right": lambda: _finish(plastics.tpu().material, "TPU fingertip pad", "#111111", 0.0, 0.9),
    "camera_mount_d405": lambda: _finish(metals.aluminum().material, "Aluminium camera saddle", "#2c2c2e", 0.8, 0.5),
    "camera_housing_d405": lambda: _finish(plastics.abs_().material, "ABS camera shroud", "#19191a", 0.0, 0.6),
}
ACTUATED = ("base_link", "link_1", "link_2", "link_3", "link_4", "link_5", "link_6")


def read_parts() -> dict[str, bd.Shape]:
    """The STEP's occurrences as parts named for their links, each a new placement of what the reader
    made (never the reader's objects themselves), standing where the STEP has it, in world coordinates."""
    tree = step.read(STEP)
    found = {child.label: child for child in tree.children}
    parts = {}
    for name, label in PARTS.items():
        occurrence = found[label]
        if occurrence.children:  # a nested occurrence (the camera saddle): its one solid, placed in the world
            (inner,) = occurrence.children
            part = inner.located(occurrence.location * inner.location)
        else:
            part = occurrence.located(occurrence.location)
        part.label = name
        parts[name] = part
    return parts


def axis_of(parts: dict[str, bd.Shape], joint: str) -> bd.Axis:
    """A revolute joint's axis: the bearing line its two parts share, signed by JOINTS, at the child's
    occurrence origin projected onto the line."""
    parent, child, sign, whose = JOINTS[joint]
    origin = parts[child].location.position
    shared = shared_axis(parts[parent], parts[child], near=(origin.X, origin.Y, origin.Z))
    line = shared.parent if whose == "parent" else shared.child
    direction = bd.Vector(*line.direction) * sign
    point = bd.Vector(*line.point)
    at = point + bd.Vector(*line.direction) * (origin - point).dot(bd.Vector(*line.direction))
    return bd.Axis(at, direction)


def _stayed(part: bd.Shape, before: bd.Location, joint: str) -> None:
    """Connected at 0, a part stays where the STEP has it: refused otherwise (a joint frame's X that
    build123d chose differently on the two sides turns it)."""
    moved = before.inverse() * part.location
    turned = max(abs(a) for a in moved.orientation)
    assert moved.position.length < 1e-6 and turned < 1e-6, f"{joint} moved {part.label}: {moved}"


def fasten(parent: bd.Shape, child: bd.Shape, label: str) -> None:
    """``child`` fastened to ``parent`` where it stands: one link."""
    where = child.location
    bd.RigidJoint(label, parent, where)
    bd.RigidJoint(label, child, where)
    parent.joints[label].connect_to(child.joints[label])


def camera_frame(housing: bd.Shape) -> bd.Location:
    """The camera's frame in the world, from the shroud's geometry: its two screw clearance holes for
    the camera (r 1.62 mm, the only tilted cylinders) give the optical axis' direction and, midway
    between them, a line on it; the frame stands where that line leaves the shroud's front, X along
    the line (looking out), Z up and back, as a camera body frame is."""
    holes = [line for line in cylinder_lines(housing)
             if abs(line.direction[1]) < 1e-3 and 0.1 < abs(line.direction[2]) < 0.9
             and any(abs(r - 1.62) < 0.05 for r in line.radii)]
    assert len(holes) == 2, f"expected the camera's two screw holes, found {len(holes)}"
    look = bd.Vector(*holes[0].direction)
    if look.X < 0:
        look = -look
    middle = (bd.Vector(*holes[0].point) + bd.Vector(*holes[1].point)) * 0.5
    front = max(bd.Vector(v).dot(look) for v in housing.vertices())
    origin = middle + look * (front - middle.dot(look))
    up = bd.Vector(0, 1, 0).cross(look) * -1  # perpendicular to the look direction, in the XZ plane, upward
    if up.Z < 0:
        up = -up
    return bd.Plane(origin=origin, x_dir=look, z_dir=up).location


def own(part: bd.Shape, world: bd.Location) -> bd.Location:
    """A world location in ``part``'s own frame, as ``frame()`` takes it."""
    return part.location.inverse() * world


@model
def wxai():
    parts = read_parts()

    # --- materials, on the finished parts ------------------------------------------------------
    plain_mass = 0.0
    for name, made in PLAIN.items():
        parts[name].material = made()
        plain_mass += parts[name].volume * made().material.density * 1e-9
    volume = sum(parts[name].volume for name in ACTUATED)  # mm^3
    effective = (SPEC_MASS - plain_mass) / (volume * 1e-9)  # kg/m^3: ~1810, the links' mean density
    link_material = _finish(RangeMaterial(name="WXAI actuated link (effective)", density=round(effective, 1)),
                            "Anodised aluminium, black", "#2a2a2c", 0.6, 0.5)
    for name in ACTUATED:
        parts[name].material = link_material

    # --- the arm: six revolute joints on the bearing lines the parts share -------------------------
    for joint, (parent, child, _sign, _whose) in JOINTS.items():
        axis = axis_of(parts, joint)
        hinge = bd.RevoluteJoint(joint, parts[parent], axis=axis, angular_range=LIMITS[joint])
        # The child's frame IS the hinge's own axis frame (as build123d holds it, in the parent's frame):
        # kinematics.md's Plane(origin, z_dir) picks its X from the exact components, and the STEP's
        # placements carry 1e-17 noise that flips it 90 degrees against the hinge's (notes, "Gaps").
        bd.RigidJoint(joint, parts[child], parts[parent].location * hinge.relative_axis.location)
        before = parts[child].location
        parts[parent].joints[joint].connect_to(parts[child].joints[joint], angle=0)
        _stayed(parts[child], before, joint)

    # --- the gripper: two carriages on link_6's rails (+Y left, -Y right: positive opens) ------------
    roll = axis_of(parts, "joint_5")
    for side, sign in (("left", +1), ("right", -1)):
        carriage = parts[f"carriage_{side}"]
        slide = bd.Axis(carriage.location.position, (0, sign, 0))
        joint = f"{side}_carriage_joint"
        bd.LinearJoint(joint, parts["link_6"], axis=slide, linear_range=(0.0, GRIPPER_TRAVEL))
        bd.RigidJoint(joint, carriage, bd.Location(slide.position))
        parts["link_6"].joints[joint].connect_to(carriage.joints[joint], position=0)
        fasten(carriage, parts[f"gripper_{side}"], f"gripper_{side}")
        fasten(parts[f"gripper_{side}"], parts[f"gripper_sock_{side}"], f"gripper_sock_{side}")
    # No coupling: text-to-cad has no prismatic-prismatic pair (rack_and_pinion_pair needs a revolute
    # pinion), so the two slides are independent joints here; see notes, "Gaps".

    # --- the camera mount, fastened to link_6 -----------------------------------------------------
    fasten(parts["link_6"], parts["camera_mount_d405"], "camera_mount_d405")
    fasten(parts["camera_mount_d405"], parts["camera_housing_d405"], "camera_housing_d405")

    # --- named frames, found on the geometry --------------------------------------------------------
    # The tool point: on the roll axis (joint_5), at the fingertips' far end (the pads' extreme X).
    tip = max(parts[f"gripper_sock_{side}"].bounding_box().max.X for side in ("left", "right"))
    tcp = roll.position + roll.direction * (tip - roll.position.X) / roll.direction.X
    frame(parts["link_6"], "ee_gripper_link", own(parts["link_6"], bd.Location(tcp)))
    frame(parts["camera_housing_d405"], "camera_link",
          own(parts["camera_housing_d405"], camera_frame(parts["camera_housing_d405"])))

    arm = bd.Compound(children=[parts[name] for name in PARTS], label="wxai")
    for joint, (velocity, effort) in DRIVES.items():
        limits(arm, joint, effort=effort, velocity=velocity)
    for side in ("left", "right"):
        limits(arm, f"{side}_carriage_joint", effort=GRIPPER_FORCE)
    mechanism_state(arm, "gripper_open", left_carriage_joint=GRIPPER_TRAVEL, right_carriage_joint=GRIPPER_TRAVEL)
    return arm


def measure_gripper() -> None:
    """The evidence GRIPPER_TRAVEL and the slide direction rest on (66 s of booleans, so not in the
    model): which direction each carriage moves freely against link_6, and how far before it stops.
    ``python -c "import wxai; wxai.measure_gripper()"`` from src/."""
    parts = read_parts()
    for side, sign in (("left", +1), ("right", -1)):
        moving = [parts[f"carriage_{side}"], parts[f"gripper_{side}"], parts[f"gripper_sock_{side}"]]
        print(side, "change of interference over +-2 mm:",
              free_directions(moving[0], parts["link_6"], [(1, 0, 0), (0, 1, 0), (0, 0, 1)]))
        print(side, "free travel (mm):", free_travel(moving, [parts["link_6"]], (0, sign, 0), 40.0))


if __name__ == "__main__":
    import time

    started = time.perf_counter()
    built = wxai()
    print(f"built in {time.perf_counter() - started:.1f} s")
    (OUT / "export").mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    built.export(OUT / "export/wxai.xml", OUT / "export/wxai.urdf")
    print(f"exported in {time.perf_counter() - started:.1f} s")
