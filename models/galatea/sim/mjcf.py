# /// script
# dependencies = ["fast-simplification", "mujoco", "numpy", "scipy", "trimesh"]
# ///
"""Galatea as a MuJoCo model: writes `sim/galatea.xml` and the meshes it draws, from the CAD model.

    cad run sim/mjcf.py            from models/galatea; half a minute while the engine holds the robot's document
    cad run sim/mjcf.py --poses    the file's keyframes alone, written again from lib/poses.py: two seconds

It calls the model, so if the model's sources have changed since the engine last built it, the robot is
built first (six minutes in an environment whose worker has not built it before). `--poses` is for when
only the poses have changed: the keyframes are all of the file that they reach, so it writes those again
and calls nothing of the CAD model.

What comes from where. The joint tree, every joint's centre, axis and travel, and the couplings are
`lib/kin.py` and `lib/dims.py`. The parts, their meshes and where they stand are the model's own
(`checks/common.load_parts`). A link's mass, centre of mass and inertia tensor are summed over its
parts as `checks/balance.py` weighs them: a part's mesh at its material's density, a drive at its
maker's mass. Each drive's peak torque (`dims.ACTUATORS`, `dims.DRIVES`) limits its servo. Collision
shapes are boxes and capsules fitted to the parts' boxes. Nothing spatial or inertial is typed here.

What does not come from the model is in `SERVO`, `HAND`, `PASSIVE`, `TOE` and `FLOOR` below: the
servos' gains, the rotors' reflected inertia, the toe's spring and the floor's friction. The CAD
model does not hold them (the toe's spring and the fingers' drives are on its list of what is not
modelled), so they are assumptions of this simulation, named as such in the file written.

Frames. MuJoCo's units are metres, kilograms, seconds and radians. A link's frame has its origin at
the centre of the joint that carries it and stands parallel to the world at the zero pose, so every
body is written without a rotation, every mesh is the link's parts in that frame, and a joint's axis
is `dims.py`'s as it stands. The pelvis, the floating base, has its origin midway between the hip
centres. The meshes are written in millimetres and scaled by 0.001 where they are referenced.
"""

import argparse
import math
import re
import shutil
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import mujoco
import numpy as np
import trimesh

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "src"))
sys.path.insert(0, str(HERE.parent / "src" / "checks"))

from lib import dims, kin  # noqa: E402
from lib.poses import POSES  # noqa: E402

XML = HERE / "galatea.xml"
MESHES = HERE / "meshes"
MM = 0.001
PELVIS = (0.0, 0.0, dims.HIP[2])       # the pelvis's frame: midway between the hip centres
TOTAL_KG = 57.4                         # what `checks/balance.py` weighs the robot at: this build must agree within a per cent

# ---------------------------------------------------------------------------------------------
# Assumptions of the simulation: what the CAD model does not hold
# ---------------------------------------------------------------------------------------------
TIME_STEP = 0.001            # s. The soles' contacts and the servos are stiff: a millisecond keeps them well inside stability
ERROR_AT_RATED = 1.0         # degrees: a servo's stiffness is its drive's rated torque for this much error
DERIVATIVE_TIME = 0.03       # s: a servo's damping is its stiffness times this
# A drive's rotor as its joint feels it, kg m^2 (rotor inertia times the gear ratio squared). RobStride's
# specification gives none; these are of the size a quasi-direct drive of each frame has.
SERVO = {"RS04": 0.040, "RS03": 0.018, "RS06": 0.010, "RS00": 0.0025, "RS05": 0.0006}
# The fingers' tendon drives and the thumb's opposition are not in the CAD model: one small servo each.
HAND = dict(kp=2.0, kv=0.06, peak=0.6, armature=1e-4, damping=0.002)
# Joints nothing drives: the linkages' cranks and rods, the knuckles a tendon closes after the first.
PASSIVE = dict(armature=1e-4, damping=0.005)
# The toe's spring, which the CAD model leaves out: stiff enough to carry the toe cap, soft enough for heel-off.
TOE = dict(stiffness=20.0, damping=0.3, armature=1e-4)
# The soles are TPU; the floor is taken as a sealed hard floor. Sliding friction, and the contact's time constant.
FLOOR = dict(friction=0.7, solref=(0.005, 1.0), solimp=(0.95, 0.99, 0.001))
COUPLING_SOLREF = (0.004, 1.0)          # a coupling's joint equality: stiff, twice the least a 1 ms step allows

# ---------------------------------------------------------------------------------------------
# The picture: a dark floor under three lamps, in a backdrop of the lit floor's own colour, so that no horizon shows
# ---------------------------------------------------------------------------------------------
GROUND = (0.070, 0.073, 0.080)
AMBIENT = 0.13
LAMPS = [  # name, the way its light travels, colour, highlight, whether it casts the shadow
    ("key", (-0.38, 0.62, -0.68), (0.78, 0.78, 0.76), 0.55, True),        # from the robot's front left, high
    ("fill", (0.66, 0.62, -0.42), (0.30, 0.32, 0.36), 0.12, False),       # from its front right, low and cool
    ("rim", (0.22, -0.84, -0.50), (0.42, 0.44, 0.50), 0.40, False),       # from behind
]

# ---------------------------------------------------------------------------------------------
# Meshes for drawing
# ---------------------------------------------------------------------------------------------
EDGE = 5.0          # mm: a mesh finer than this mean edge length is decimated to it (the drives' own solids, mostly)
LEAST = 80          # triangles: no mesh is decimated below this
CREASE = 40.0       # degrees: faces that turn less than this at a shared vertex are shaded as one surface

# ---------------------------------------------------------------------------------------------
# Collision shapes: (link without its side, name, kind, the part labels whose box it is fitted to or None for all)
# A box is the parts' box at the zero pose, where every link's frame is parallel to the world. A capsule is the
# largest that lies in that box along its longest side.
# ---------------------------------------------------------------------------------------------
SHAPES = [
    ("pelvis", "pelvis", "box", None), ("lumbar_yoke", "abdomen", "box", None), ("chest", "chest", "box", None),
    ("head", "head", "box", None),
    ("hip_yoke", "hip_yoke", "box", None), ("hip_cradle", "hip", "box", None),
    ("thigh", "thigh", "capsule", None), ("shin", "shin", "capsule", None),
    ("foot", "heel", "box", ("heel_pad",)), ("foot", "ball", "box", ("ball_pad",)), ("foot", "upper", "box", ("foot_shell",)),
    ("toe", "toe", "box", ("toe_pad",)), ("toe", "toe_cap", "box", ("toe_cap",)),
    ("shoulder_block", "shoulder", "box", None), ("upper_arm", "upper_arm", "capsule", None),
    ("forearm", "forearm", "capsule", None), ("forearm_distal", "forearm_distal", "capsule", None),
    ("wrist_link", "wrist", "box", None), ("palm", "palm", "box", None),
    *[(f"{finger}_{bone}", f"{finger}_{bone}", "capsule", None) for finger in dims.FINGERS for bone in ("prox", "mid", "dist")],
    *[(f"thumb_{bone}", f"thumb_{bone}", "capsule", None) for bone in ("meta", "prox", "dist")],
]
SOLES = ("heel", "ball", "toe")          # the shapes a foot stands on


def num(value, digits=6):
    text = f"{float(value):.{digits}g}"
    return "0" if text in ("0", "-0") else text


def vec(values, digits=6):
    """Numbers as MJCF writes a vector. An entry a thousand million times smaller than the vector's largest is
    arithmetic's dust (1e-18 m beside a centimetre) and is written as 0, so that two builds write the same file."""
    values = [float(v) for v in values]
    dust = 1e-9 * max((abs(v) for v in values), default=0.0)
    return " ".join(num(0.0 if abs(v) < dust else v, digits) for v in values)


def matrix(transform):
    """A `kin` transform as a 4 x 4 array."""
    r, p = transform
    m = np.eye(4)
    m[:3, :3], m[:3, 3] = np.array(r), np.array(p)
    return m


def label_of(part):
    """A part's label, as the model's tree spells it: a repeated label's node is numbered."""
    return re.sub(r"_\d+$", "", part.path.split("/")[-1])


# ---------------------------------------------------------------------------------------------
# The model
# ---------------------------------------------------------------------------------------------
def finishes(node, found=None):
    """{part label: its material} from the model's tree: every part of one label wears one material."""
    found = {} if found is None else found
    if node.children:
        for child in node.children:
            finishes(child, found)
    else:
        found[node.label] = node.material
    return found


def frames():
    """{link: its frame's origin at the zero pose, mm}: the centre of the joint that carries it."""
    origins = {"pelvis": PELVIS}
    origins.update({child: origin for _, child, origin, _, _ in kin.all_joints().values()})
    return origins


def weigh(links, materials, drive_model):
    """{link: (kg, centre of mass in the world at the zero pose mm, inertia tensor about it kg mm^2 on the world's axes)}.

    As `checks/balance.py` weighs: a part is its mesh's volume at its material's density, about its mesh's centre
    of mass; a drive (`drive_model` names a part's, as `checks/common.py` does) is its maker's mass at the middle
    of its box. A drive's tensor is that of the maker's solid taken as one density (which is how the CAD model
    carries it), scaled to the maker's mass."""
    weighed, strayed = {}, 0.0
    for link, parts in links.items():
        rows = []
        for part in parts:
            label, mesh = label_of(part), part.geometry.mesh
            properties = trimesh.triangles.mass_properties(mesh.triangles, density=1.0, skip_inertia=False)
            volume, about = float(properties["volume"]), np.array(properties["inertia"])       # mm^3, mm^5 about its centre
            drive = drive_model(label)
            if drive:
                kg, centre = dims.ACTUATORS[drive]["kg"], mesh.bounds.mean(axis=0)
                strayed = max(strayed, float(np.linalg.norm(centre - properties["center_mass"])))
            else:
                kg, centre = abs(volume) * 1e-9 * materials[label].material.density, np.array(properties["center_mass"])
            turn = part.rest[:3, :3]
            rows.append((kg, (part.rest @ np.append(centre, 1.0))[:3], turn @ (about * kg / volume) @ turn.T))
        mass = sum(kg for kg, _, _ in rows)
        com = sum(kg * at for kg, at, _ in rows) / mass
        tensor = np.zeros((3, 3))
        for kg, at, about in rows:                         # each part's tensor carried to the link's centre of mass
            d = at - com
            tensor += about + kg * (float(d @ d) * np.eye(3) - np.outer(d, d))
        weighed[link] = (mass, com, tensor)
    return weighed, strayed


def sound(link, mass, tensor):
    """Refuse a link whose mass properties no body can have."""
    moments = np.linalg.eigvalsh(tensor)
    if not (mass > 0 and np.all(np.isfinite(tensor)) and moments[0] > 0 and moments[0] + moments[1] >= moments[2] * (1 - 1e-9)):
        raise ValueError(f"{link}: mass {mass:g} kg with principal moments {moments} is no rigid body's")


# ---------------------------------------------------------------------------------------------
# Meshes
# ---------------------------------------------------------------------------------------------
def thinned(mesh):
    """`mesh` with no more triangles than a mean edge of EDGE asks for (quadric decimation), or as it is."""
    wanted = max(LEAST, int(mesh.area / (0.433 * EDGE * EDGE)))
    if len(mesh.faces) <= 1.25 * wanted:
        return mesh
    thin = mesh.simplify_quadric_decimation(face_count=wanted)
    thin.update_faces(thin.nondegenerate_faces())
    thin.remove_unreferenced_vertices()
    return thin


def shaded(vertices, faces):
    """(normals, each face's three indices into them): a corner's normal is the mean, weighted by the corner's
    angle, of the normals of the faces round its vertex that turn less than CREASE from its own face. A curved
    skin is then drawn smooth and an edge sharp."""
    corners = vertices[faces]
    sides = np.roll(corners, -1, axis=1) - corners                               # a -> b, b -> c, c -> a
    flat = np.cross(sides[:, 0], sides[:, 1])
    size = np.linalg.norm(flat, axis=1)
    flat = flat / np.maximum(size, 1e-12)[:, None]
    out, back = sides, -np.roll(sides, 1, axis=1)
    cosine = np.einsum("fij,fij->fi", out, back) / np.maximum(np.linalg.norm(out, axis=2) * np.linalg.norm(back, axis=2), 1e-12)
    angle = np.where(size[:, None] > 1e-9, np.arccos(np.clip(cosine, -1.0, 1.0)), 0.0)

    vertex, face = faces.ravel(), np.repeat(np.arange(len(faces)), 3)
    order = np.argsort(vertex, kind="stable")
    vertex, face, weight = vertex[order], face[order], angle.ravel()[order]
    first = np.flatnonzero(np.r_[True, vertex[1:] != vertex[:-1]])
    count = np.diff(np.r_[first, len(vertex)])
    start, many = np.repeat(first, count), np.repeat(count, count)              # per corner: where its vertex's corners begin
    mine = np.repeat(np.arange(len(vertex)), many)                               # every (corner, corner of the same vertex)
    other = np.repeat(start, many) + (np.arange(len(mine)) - np.repeat(np.cumsum(many) - many, many))
    near = np.einsum("ij,ij->i", flat[face[mine]], flat[face[other]]) >= math.cos(math.radians(CREASE))
    mine, other = mine[near], other[near]
    summed = np.stack([np.bincount(mine, weights=weight[other] * flat[face[other], k], minlength=len(vertex)) for k in range(3)], axis=1)
    length = np.linalg.norm(summed, axis=1)
    normal = np.where(length[:, None] > 1e-9, summed / np.maximum(length, 1e-12)[:, None], flat[face])
    normal[np.linalg.norm(normal, axis=1) < 0.5] = (0.0, 0.0, 1.0)              # a face with no area has no normal of its own
    corner_normal = np.empty((len(vertex), 3))
    corner_normal[order] = normal
    normals, index = np.unique(np.round(corner_normal, 4), axis=0, return_inverse=True)
    return normals, index.reshape(-1, 3)


def write_obj(path, vertices, normals, faces, face_normals):
    lines = ["# Galatea, one link's parts of one look, in the link's frame. Millimetres. Written by sim/mjcf.py."]
    lines += ["v %.3f %.3f %.3f" % tuple(row) for row in vertices]
    lines += ["vn %.4f %.4f %.4f" % tuple(row) for row in normals]
    lines += ["f %d//%d %d//%d %d//%d" % (a, d, b, e, c, f) for (a, b, c), (d, e, f) in zip(faces + 1, face_normals + 1)]
    path.write_text("\n".join(lines) + "\n")


def draw(links, materials, origins):
    """Write each link's parts, one mesh per look, in the link's frame: {link: [(look, mesh name, file)]}."""
    if MESHES.exists():
        shutil.rmtree(MESHES)
    MESHES.mkdir()
    drawn, before, after, written = {}, 0, 0, {}
    for link, parts in links.items():
        by_look = {}
        for part in parts:
            name = part.geometry.name
            if name not in written:
                thin = thinned(part.geometry.mesh)
                vertices, faces = np.asarray(thin.vertices, dtype=float), np.asarray(thin.faces, dtype=np.int64)
                written[name] = (vertices, faces, *shaded(vertices, faces), len(part.geometry.mesh.faces))
            vertices, faces, normals, face_normals, full = written[name]
            before, after = before + full, after + len(faces)
            placed = part.rest.copy()
            placed[:3, 3] -= origins[link]
            turn = placed[:3, :3]
            by_look.setdefault(materials[label_of(part)].pbr.name, []).append(
                (vertices @ turn.T + placed[:3, 3], faces, normals @ turn.T, face_normals))
        drawn[link] = []
        for look, pieces in sorted(by_look.items()):
            v0 = np.cumsum([0] + [len(piece[0]) for piece in pieces])
            n0 = np.cumsum([0] + [len(piece[2]) for piece in pieces])
            file = f"{link}.{look}.obj"
            write_obj(MESHES / file, np.vstack([piece[0] for piece in pieces]), np.vstack([piece[2] for piece in pieces]),
                      np.vstack([piece[1] + v0[k] for k, piece in enumerate(pieces)]),
                      np.vstack([piece[3] + n0[k] for k, piece in enumerate(pieces)]))
            drawn[link].append((look, f"{link}.{look}", file))
    return drawn, before, after


def look_of(material):
    """A finish's PBR look as MuJoCo's own renderer can draw it. That renderer shades by Phong's model, so
    a metal's or a lacquer's reflections become a highlight: its strength from metalness and clear coat, its
    width from roughness. A metal keeps most of its base colour as its diffuse one, or it would draw as grey
    plastic. Transmission becomes transparency, and an emissive look glows."""
    values = material.pbr.values

    def get(name, default=0.0):
        value = getattr(values, name, None)
        return default if value is None else value

    metal, rough, coat = get("metalness"), get("roughness", 0.5), get("clearcoat")
    gloss = 1.0 - rough
    colour = np.array(values.color[:3], dtype=float) * (1.0 - 0.3 * metal)
    attributes = dict(rgba=vec([*colour, 1.0 - get("transmission")], 4),
                      specular=num(min(1.0, (0.2 + 0.8 * max(metal, coat)) * (0.3 + 0.7 * gloss)), 3), shininess=num(gloss, 3),
                      metallic=num(metal, 3), roughness=num(rough, 3))
    if getattr(values, "emissive", None) is not None:
        attributes["emission"] = num(get("emissive_intensity", 1.0), 3)
    return attributes


# ---------------------------------------------------------------------------------------------
# Collision shapes
# ---------------------------------------------------------------------------------------------
def shapes(links, origins):
    """{link: [(name, attributes)]}: the boxes and capsules of SHAPES, fitted to the parts' boxes, in metres."""
    fitted = {}
    for side in ("", *(f"{s}_" for s in kin.SIDES)):
        for bare, name, kind, labels in SHAPES:
            link = side + bare
            if (bare in dims.CENTRE_LINKS) != (side == ""):
                continue
            parts = [part for part in links[link] if labels is None or label_of(part) in labels]
            if not parts:
                raise ValueError(f"{link}: no part of {labels} to fit {name} to")
            lo = (np.min([part.lo for part in parts], axis=0) - origins[link]) * MM
            hi = (np.max([part.hi for part in parts], axis=0) - origins[link]) * MM
            centre, half = (lo + hi) / 2, (hi - lo) / 2
            if kind == "box":
                attributes = dict(type="box", pos=vec(centre), size=vec(half))
            else:
                along = int(np.argmax(half))
                radius = float(np.min(np.delete(half, along)))
                reach = np.zeros(3)
                reach[along] = max(half[along] - radius, 1e-4)
                attributes = dict(type="capsule", fromto=vec([*(centre - reach), *(centre + reach)]), size=num(radius))
            fitted.setdefault(link, []).append((side + name, attributes))
    return fitted


# ---------------------------------------------------------------------------------------------
# The MJCF
# ---------------------------------------------------------------------------------------------
LEDGER = """
Galatea, a 1.76 m humanoid, for MuJoCo. Written by sim/mjcf.py from the CAD model (the engine's document
{document}): edit that, not this file.

Units: metres, kilograms, seconds, radians. Meshes are in millimetres, scaled by 0.001.
World: +Z up, the robot faces -Y, its left is +X, the floor is z = 0.
Frames: a body's frame has its origin at the centre of the joint that carries it and is parallel to the world
  at the zero pose (standing straight, arms hanging). The pelvis, the floating base, has its origin midway
  between the hip centres, {pelvis_z} m over the floor.
Joints: centre, axis and range from src/lib/dims.py through src/lib/kin.py (all_joints); positive is the
  anatomical motion named there, the same on both sides.
Couplings (src/lib/kin.py, couplings), as joint equalities at their exact ratios: each knee's and each ankle's
  parallelogram linkage (pivot : crank : rod = 1 : 1 : -1), each finger's knuckles (85 : 100 : 70), each
  thumb's (55 : 75).
Inertials: per link, summed over its parts as src/checks/balance.py weighs them (a part's mesh at its
  material's density, a drive at its maker's mass at the middle of its box). {mass} kg in all.
Servos: a position servo on every driven joint, limited to its drive's peak torque (dims.ACTUATORS, dims.DRIVES).
  A knee's and an ankle's servo act on the pivot, which the linkage follows one to one.
Collision: boxes and capsules fitted to the parts' boxes (class "collision", group 3); they meet the floor and
  not each other. The meshes (class "visual", group 2) collide with nothing.
Assumed, because the CAD model does not hold them: the servos' stiffness (a drive's rated torque per
  {error} degree of error) and damping (stiffness x {derivative} s), the rotors' reflected inertia, the hand's servos,
  the toe's spring ({toe} N m/rad), the floor's friction ({friction}).
The weld "hold_pelvis" is off. sim/run.py turns it on only for a clip it labels as held.
"""


def element(parent, tag, **attributes):
    return ET.SubElement(parent, tag, {key.rstrip("_"): value for key, value in attributes.items()})


def servo_of(control):
    """A control's drive as (class name, model, how many), or None for a control no drive of `dims.DRIVES` turns."""
    bare = control[2:] if control[:2] in ("l_", "r_") else control
    if bare not in dims.DRIVES:
        return None
    model, count = dims.DRIVES[bare]
    return (model if count == 1 else f"{model}x{count}"), model, count


def controls():
    """[(control, the joint its servo turns, the servo's class)] for every driven control: every control but the
    toes. A coupling's servo turns its first joint: a linkage's pivot, a finger's first knuckle. A control no drive
    of `dims.DRIVES` turns is the hand's: a finger's curl, the thumb's opposition."""
    couplings, rows = kin.couplings(), []
    for control in kin.controls():
        if control[2:] == "toe":
            continue
        servo = servo_of(control)
        rows.append((control, next(iter(couplings[control])) if control in couplings else control, servo[0] if servo else "hand"))
    return rows


def describe(document, weighed, drawn, fitted, looks, origins, keys=()):
    """The MJCF as an element tree; `document` is the id of the model's document it is written from."""
    joints = kin.all_joints()
    hangs = {}
    for label, (parent, *_) in joints.items():
        hangs.setdefault(parent, []).append(label)
    rows = controls()
    class_of = {joint: name for _, joint, name in rows}

    root = ET.Element("mujoco", model="galatea")
    root.append(ET.Comment(LEDGER.format(document=document, pelvis_z=num(PELVIS[2] * MM),
                                         mass=f"{sum(m for m, _, _ in weighed.values()):.2f}",
                                         error=num(ERROR_AT_RATED), derivative=num(DERIVATIVE_TIME), toe=num(TOE["stiffness"]),
                                         friction=num(FLOOR["friction"]))))
    element(root, "compiler", angle="radian", meshdir="meshes", autolimits="true")
    element(root, "option", timestep=num(TIME_STEP), integrator="implicitfast", cone="elliptic", impratio="10")
    visual = element(root, "visual")
    element(visual, "global", offwidth="1600", offheight="900", fovy="30", azimuth="125", elevation="-8")
    element(visual, "quality", shadowsize="8192", offsamples="4")
    element(visual, "headlight", ambient=vec([AMBIENT] * 3), diffuse="0 0 0", specular="0 0 0")
    element(visual, "map", znear="0.02", zfar="60", shadowclip="1.2")
    # The floor has no highlight, so every lamp lights it alike everywhere: its colour times the light that falls on it.
    falls = sum(np.array(colour) * max(0.0, -way[2] / math.sqrt(sum(c * c for c in way))) for _, way, colour, _, _ in LAMPS)
    lit = vec(np.array(GROUND) * (AMBIENT + falls), 4)
    element(visual, "rgba", haze=f"{lit} 1")
    element(root, "statistic", center="0 0 0.9", extent="2")

    defaults = element(root, "default")
    element(element(defaults, "default", class_="visual"), "geom", type="mesh", contype="0", conaffinity="0", group="2")
    element(element(defaults, "default", class_="collision"), "geom", contype="0", conaffinity="1", group="3",
            rgba="0.25 0.6 0.9 0.4", friction=vec([FLOOR["friction"], 0.005, 0.0001]), solref=vec(FLOOR["solref"]),
            solimp=vec(FLOOR["solimp"]))
    for name, model, count in sorted({servo_of(control) for control, _, _ in rows if servo_of(control)}):
        spec = dims.ACTUATORS[model]
        kp = count * spec["rated"] / math.radians(ERROR_AT_RATED)
        drive = element(defaults, "default", class_=name)
        element(drive, "joint", armature=num(count * SERVO[model]))
        element(drive, "position", kp=num(kp), kv=num(kp * DERIVATIVE_TIME), forcerange=vec([-count * spec["peak"], count * spec["peak"]]))
    hand = element(defaults, "default", class_="hand")
    element(hand, "joint", armature=num(HAND["armature"]), damping=num(HAND["damping"]))
    element(hand, "position", kp=num(HAND["kp"]), kv=num(HAND["kv"]), forcerange=vec([-HAND["peak"], HAND["peak"]]))
    element(element(defaults, "default", class_="passive"), "joint", armature=num(PASSIVE["armature"]), damping=num(PASSIVE["damping"]))
    element(element(defaults, "default", class_="toe"), "joint", stiffness=num(TOE["stiffness"]), damping=num(TOE["damping"]),
            armature=num(TOE["armature"]), springref="0")

    asset = element(root, "asset")
    element(asset, "texture", name="backdrop", type="skybox", builtin="flat", rgb1=lit, rgb2=lit, width="64", height="384")
    element(asset, "material", name="floor", rgba=vec([*GROUND, 1.0]), specular="0", shininess="0", reflectance="0.15")
    for look, attributes in sorted(looks.items()):
        element(asset, "material", name=look, **attributes)
    for link in drawn:
        for _, mesh, file in drawn[link]:
            element(asset, "mesh", name=mesh, file=file, scale=vec([MM] * 3))

    world = element(root, "worldbody")
    for name, way, colour, highlight, shadow in LAMPS:
        element(world, "light", name=name, type="directional", pos=vec(-4.0 * np.array(way) + (0.0, 0.0, 0.9)), dir=vec(way),
                diffuse=vec(colour), specular=vec([highlight] * 3), castshadow="true" if shadow else "false")
    element(world, "geom", name="floor", type="plane", size="0 0 0.05", material="floor", contype="1", conaffinity="0",
            friction=vec([FLOOR["friction"], 0.005, 0.0001]), solref=vec(FLOOR["solref"]), solimp=vec(FLOOR["solimp"]))
    element(world, "body", name="hanger", mocap="true", pos=vec(np.array(PELVIS) * MM))

    def body(parent, link, carried_by):
        origin = np.array(origins[link])
        at = origin if carried_by is None else origin - np.array(origins[joints[carried_by][0]])
        node = element(parent, "body", name=link, pos=vec(at * MM))
        if carried_by is None:
            element(node, "freejoint", name="root")
        else:
            _, _, _, direction, (low, high) = joints[carried_by]
            name = class_of.get(carried_by) or ("toe" if carried_by[2:] == "toe" else "passive")
            element(node, "joint", name=carried_by, class_=name, axis=vec(direction),
                    range=vec([math.radians(low), math.radians(high)], 9))
        mass, com, tensor = weighed[link]
        sound(link, mass, tensor)
        about = tensor * MM * MM
        element(node, "inertial", pos=vec((com - origin) * MM), mass=num(mass),
                fullinertia=vec([about[0, 0], about[1, 1], about[2, 2], about[0, 1], about[0, 2], about[1, 2]]))
        for look, mesh, _ in drawn[link]:
            element(node, "geom", class_="visual", mesh=mesh, material=look)
        for name, attributes in fitted.get(link, ()):
            element(node, "geom", name=name, class_="collision", **attributes)
        for label in hangs.get(link, ()):
            body(node, joints[label][1], label)

    body(world, "pelvis", None)

    equality = element(root, "equality")
    element(equality, "weld", name="hold_pelvis", body1="pelvis", body2="hanger", active="false", solref="0.004 1")
    for coupling, ratios in kin.couplings().items():
        (first, ratio), *rest = ratios.items()
        for joint, other in rest:
            element(equality, "joint", name=f"{coupling}.{joint.split('_', 1)[1]}", joint1=joint, joint2=first,
                    polycoef=vec([0.0, other / ratio, 0.0, 0.0, 0.0], 12), solref=vec(COUPLING_SOLREF))

    actuator = element(root, "actuator")
    for control, joint, name in rows:
        low, high = joints[joint][4]
        element(actuator, "position", name=control, class_=name, joint=joint, ctrlrange=vec([math.radians(low), math.radians(high)], 9))

    if keys:
        keyframe = element(root, "keyframe")
        for name, qpos, ctrl in keys:
            element(keyframe, "key", name=name, qpos=vec(qpos, 9), ctrl=vec(ctrl, 9))
    ET.indent(root, space="  ")
    return root


def written(root):
    XML.write_text(ET.tostring(root, encoding="unicode") + "\n")
    return mujoco.MjModel.from_xml_path(str(XML))


def targets(pose):
    """{control: radians at its servo's joint} for a pose in the model's controls (degrees, a finger's curl 0 to 1)."""
    values = kin.expand(pose)
    return {control: math.radians(values.get(joint, 0.0)) for control, joint, _ in controls()}


def keyframes(model):
    """[(name, qpos, ctrl)]: the zero pose, and each named pose set on the floor as `stances.py` sets it (a pose
    that tips the pelvis flat on its left foot, any other lowered, level, onto its lowest sole point)."""
    planted = {"bow": "l_foot", "crouch": "l_foot"}
    keys = []
    for name, pose in {"zero": {}, **POSES}.items():
        ground = matrix(kin.stance(pose, planted[name]) if name in planted else kin.settle(pose))
        qpos = model.qpos0.copy()
        qpos[:3] = (ground @ np.append(PELVIS, 1.0))[:3] * MM
        quaternion = np.zeros(4)
        mujoco.mju_mat2Quat(quaternion, ground[:3, :3].ravel())
        qpos[3:7] = quaternion
        for joint, degrees in kin.expand(pose).items():
            qpos[model.joint(joint).qposadr[0]] = math.radians(degrees)
        ctrl = np.zeros(model.nu)
        for control, value in targets(pose).items():
            ctrl[model.actuator(control).id] = value
        keys.append((name, qpos, ctrl))
    return keys


def rekeyed():
    """`galatea.xml` with its keyframes written again from `lib/poses.py` as it is now, and nothing else in it
    touched: for when only the poses have changed since the file was written. Nothing of the CAD model is called
    or imported. A file whose joints or couplings are not `lib/kin.py`'s as they are now is refused: the poses are
    not all that changed, and that wants the whole build."""
    if not XML.exists():
        raise SystemExit(f"{XML} is not there: `cad run sim/mjcf.py` writes it, and the meshes it draws")
    root = ET.parse(XML, ET.XMLParser(target=ET.TreeBuilder(insert_comments=True))).getroot()
    joints, origins = kin.all_joints(), frames()
    have = {joint.get("name"): (body.get("pos"), joint.get("axis"), joint.get("range"))
            for body in root.iter("body") for joint in body.findall("joint")}
    want = {label: (vec((np.array(origin) - np.array(origins[parent])) * MM), vec(direction),
                    vec([math.radians(low), math.radians(high)], 9))
            for label, (parent, _, origin, direction, (low, high)) in joints.items()}
    tied = {(tie.get("joint1"), tie.get("joint2"), tie.get("polycoef")) for tie in root.find("equality").findall("joint")}
    ties = set()
    for ratios in kin.couplings().values():
        (first, ratio), *rest = ratios.items()
        ties |= {(joint, first, vec([0.0, other / ratio, 0.0, 0.0, 0.0], 12)) for joint, other in rest}
    if have != want or tied != ties:
        differ = sorted(label for label in have.keys() | want.keys() if have.get(label) != want.get(label)) or sorted(j for j, _, _ in tied ^ ties)
        raise SystemExit(f"{XML.name} was written from another mechanism than lib/kin.py has now ({', '.join(differ[:6])}"
                         f"{' ...' if len(differ) > 6 else ''}): `cad run sim/mjcf.py` writes the whole of it again")

    keyframe = root.find("keyframe")
    before = {key.get("name"): (key.get("qpos"), key.get("ctrl")) for key in keyframe}
    for key in list(keyframe):
        keyframe.remove(key)
    for name, qpos, ctrl in keyframes(mujoco.MjModel.from_xml_path(str(XML))):
        element(keyframe, "key", name=name, qpos=vec(qpos, 9), ctrl=vec(ctrl, 9))
    after = {key.get("name"): (key.get("qpos"), key.get("ctrl")) for key in keyframe}
    ET.indent(root, space="  ")
    changed = sorted(name for name in before.keys() | after.keys() if before.get(name) != after.get(name))
    if ET.tostring(root, encoding="unicode") + "\n" == XML.read_text():
        return print(f"{XML.relative_to(HERE.parent)}: its {len(after)} keyframes are lib/poses.py's already; nothing written")
    if not changed:
        raise SystemExit(f"{XML.name} does not read back as it was written, though its keyframes stand: it has been edited by hand, or written "
                         "by another state of this script. `cad run sim/mjcf.py` writes the whole of it again")
    model = written(root)
    print(f"{XML.relative_to(HERE.parent)}: {len(changed)} of its {model.nkey} keyframes written again from lib/poses.py "
          f"({', '.join(changed)}); nothing else in it has changed")


def main(arguments):
    parser = argparse.ArgumentParser(prog="cad run sim/mjcf.py", description="Galatea as a MuJoCo model: sim/galatea.xml and its meshes.")
    parser.add_argument("--poses", action="store_true",
                        help="write only the keyframes again, from lib/poses.py as it is now: nothing of the CAD model is called")
    if parser.parse_args(arguments).poses:
        return rekeyed()
    # The CAD model's own modules, imported only here: `--poses` neither needs them nor waits for them.
    import build123d  # noqa: F401  (the model needs cad's build123d integration)
    from common import drive_model, load_parts
    from galatea import galatea

    started = time.time()
    handle = galatea()
    links = load_parts(handle)
    materials = finishes(handle.shape)
    origins = {link: np.array(origin) for link, origin in frames().items()}
    if set(origins) != set(links):
        raise ValueError(f"the model's links and the joint tree's differ: {sorted(set(origins) ^ set(links))}")

    weighed, strayed = weigh(links, materials, drive_model)
    total = sum(mass for mass, _, _ in weighed.values())
    if abs(total - TOTAL_KG) > 0.01 * TOTAL_KG:
        raise ValueError(f"the links weigh {total:.2f} kg in all, not within a per cent of {TOTAL_KG} kg")
    print(f"mass {total:.2f} kg in {len(weighed)} links ({TOTAL_KG} kg by checks/balance.py); a drive's own centre of mass "
          f"lies at most {strayed:.1f} mm from the middle of its box, where its mass is put")

    drawn, before, after = draw(links, materials, origins)
    files = sorted(MESHES.glob("*.obj"))
    print(f"meshes: {len(files)} files for {len(drawn)} links, {after:,} triangles of the model's {before:,}, "
          f"{sum(file.stat().st_size for file in files) / 1e6:.0f} MB in {MESHES.relative_to(HERE.parent)}/")
    looks = {material.pbr.name: look_of(material) for material in materials.values()}
    fitted = shapes(links, origins)

    model = written(describe(handle.id, weighed, drawn, fitted, looks, origins))
    model = written(describe(handle.id, weighed, drawn, fitted, looks, origins, keyframes(model)))

    data = mujoco.MjData(model)
    mujoco.mj_resetDataKeyframe(model, data, model.key("zero").id)
    mujoco.mj_forward(model, data)
    lowest = min(float(data.geom_xpos[model.geom(f"{s}_{name}").id][2] - model.geom(f"{s}_{name}").size[2])
                 for s in kin.SIDES for name in SOLES)
    com = data.subtree_com[model.body("pelvis").id] / MM
    print(f"{XML.relative_to(HERE.parent)}: {model.nbody - 2} links, {model.njnt - 1} joints, {model.nu} servos, "
          f"{model.neq - 1} coupling equalities, {sum(len(v) for v in fitted.values())} collision shapes, {model.nkey} keyframes, "
          f"{XML.stat().st_size / 1e3:.0f} kB")
    print(f"  as MuJoCo compiles it: {float(model.body_mass.sum()):.2f} kg, centre of mass at the zero pose "
          f"({com[0]:.1f}, {com[1]:.1f}, {com[2]:.1f}) mm, the soles' boxes {lowest * 1000:+.3f} mm from the floor")
    print(f"done in {time.time() - started:.0f} s")


if __name__ == "__main__":
    main(sys.argv[1:])
