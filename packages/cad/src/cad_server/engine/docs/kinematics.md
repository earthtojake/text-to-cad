# Kinematics

A page of [the engine's documentation](../README.md). A name in bold in parentheses, such as (**Kinematics**), is another page or a named paragraph of one: the index says which.

At document time the engine harvests every joint on every part of the result and pairs them
two ways: by `connect_to` where the author used it, and, for every joint `connect_to` did not
join, by label -- a moving joint and a `RigidJoint` of the same label on another part are its
pair (the nearest in the tree; two alike are refused by name), and two rigid joints of one label,
each the other's nearest, fasten their parts. `connect_to` wins where both would pair a joint.
build123d's `connect_to` composes locations within each part's own compound, so it cannot place
a part in a nested assembly: there the model puts each part where it stands, authors the two
joints there, and the label pairs them. The engine never moves a part: every value, as built
included, is computed from where the two joints' frames stand in the built tree. The pairs make
a mechanism in ISO 10303-105's terms (STEP AP242's kinematics):

- **Links** are occurrences that move as one: two parts whose rigid joints are connected
  are one link. The **ground** is every link no `connect_to` moved (the joint whose
  `connect_to` is called stays put; the other's part moves), and every part no joint places.
  A part below a jointed sub-assembly moves with it.
- **Pairs**: a revolute joint is a `REVOLUTE_PAIR`, a linear one a `PRISMATIC_PAIR`, a
  cylindrical one a `CYLINDRICAL_PAIR`, a ball a `SPHERICAL_PAIR`, each `_WITH_RANGE` where
  its range is finite, named by the moving joint's label (a label two pairs share takes the
  path of the part that holds it: `hand/left:knuckle`). Link 1 holds the moving joint, link 2
  the rigid one. Its frames, `transform_item_1` and `transform_item_2`, are
  AXIS2_PLACEMENT_3Ds in their links' frames (a link's frame: its first occurrence's
  placement as built) that coincide at value 0; link 2 stands at
  `link_1 · item_1 · M(v) · item_2⁻¹`, `M` a turn about Z, a slide along Z, both
  (cylindrical: angle, then distance) or build123d's intrinsic X-Y-Z rotation (spherical).
  Degrees and millimetres.
- **Mechanism states**: the as-built values and each named state (`mechanism_state`), each a pose
  (where its parts stand), as `MECHANISM_STATE_REPRESENTATION`s of pair values (the structure's and the viewer's
  `configurations`).
- **Couplings**: each `gear_pair`, `rack_and_pinion_pair` or `screw_pair`, a constraint among
  pairs, as the AP242 couplers it is named after (below).
- **Configuration sequences**: each `configuration_sequence`, a definition (waypoints and an ease),
  as AP242's `INTERPOLATED_CONFIGURATION_SEQUENCE` (the structure's and the viewer's `motions`): its
  segments' times (`t_parameter`), interpolation and states (a mechanism state it names, or pair
  values).

**What AP242 cannot hold is refused or left out, never patched** (law 12). A pair the built
tree contradicts fails the build by name: one whose part stands where it cannot put it (moved
after `connect_to`, connected after its compound was made, a rigid joint off the joint's axis)
or that joins two parts rigid joints make one body has no value the standard can hold. A moving
joint matching two rigid joints alike, a linear joint connected to a revolute one (a pin in a
slot, which no AP242 lower pair is) and a mechanism state's value a pair cannot take (another
count of numbers than the joint's, a coupling's value outside the coupling's range) are left
out and warned; pairs that close a loop are kept and not posed (a robot description closes them:
below). A child `connect_to` turned about its joint's own axis at its zero though it was built where
it stands fails the build too: where a `RigidJoint` stood at its joint's origin with its Z on the
joint's axis before the connection (a joint connected again: before its first), the child at the
pair's zero must stand where it was built, turned by no more than 1e-9 radian times the model's
size in millimetres (at least 1), and the refusal names the joint, the turn, how far the parts moved
and the frame to build the `RigidJoint` at (a revolute's `joint.location`, a slide's position in its
part's orientation). The engine records each `connect_to` as a model's body runs it
(`mechanism.watch`, installed with the kernel's patches); a `RigidJoint` elsewhere, or one whose Z
the connection turns onto the axis (a wheel built at the origin, put on its axle), is a placement,
which `connect_to` makes as build123d's joints do. The warnings are the build's
report (`kinematics.warnings`), never the document's. The harvest's errors are a mechanism state,
a configuration sequence or a coupling naming a joint its assembly does not hold, a mechanism
state putting a joint outside the joint's range, said in one line (`mechanism state
'turned_left' of car puts joint 'steer' at 32 deg, outside its range -30 to 30`; a value on a
bound is within it), a coupling named as a joint is, a coupling driving a joint its pair does
not relate or no coupler can hold (below), and a joint two couplings drive.

**Couplings.** A coupling is a constraint, made by the function named after the AP242 pair it
is written as:

| Function | Its joints | AP242 |
| --- | --- | --- |
| `gear_pair(assembly, name, **joints)` | revolute joints, a ratio each (degrees per unit of its value) | `KinematicPairWithMotionCoupling`, `Kind` `gear_pair`, from the first-named joint to each other one |
| `rack_and_pinion_pair(assembly, name, **joints)` | the first-named a revolute joint (the pinion, which may hold no part) or a prismatic one (the rack), every other of the other kind, a ratio each | `Kind` `rack_and_pinion_pair`, from the first-named joint to each other one |
| `screw_pair(assembly, name, joint=pitch)` | one cylindrical joint and its pitch, the millimetres it travels per 360 degrees of turn; the coupling's value is its turn | Part 105's `SCREW_PAIR` (`pitch`) |

Its joints move together, each by its ratio, and only through it, each named by its label. At
value `c` each joint stands at its as-built value plus its ratio times `c`: `c = 0` is as built,
so a coupling never moves the build. Its range is derived, never given: the tightest interval of
`c` in which every joint stays within its own limits (a joint with no limits bounds nothing; a
side nothing bounds is open). Its name poses wherever a joint's does --
`mechanism_state(..., curl=0.5)`, a configuration sequence's waypoints and sweeps, `--pose
'{"curl": 0.6}'` -- and mechanism states and configuration sequences resolve it to pair values
at document time, so their AP242 states and a GLB's bake are as ever; a pose, a mechanism state
or a configuration sequence setting one of its joints alone is refused (a state's or a
sequence's value left out, and warned).

In the document each coupler holds `s1 · d1 + s2 · d2 = 0` over the two values' displacements
from as built (`CouplingRatios`, with `CouplingTypes` saying which value of each pair), so the
ratios read back as written; a coupling of more than two joints is chained as two-joint couplers
from its first-named joint, never one `three_joint_coupler`. A joint its function does not
relate -- a gear pair's prismatic joint, a rack and pinion's two pinions, a screw's revolute
joint, any coupling's ball joint (no coupler relates a ball's three angles) -- fails the build
by name, as does a coupling of one value alone and one whose joints' limits leave it no range
around as built. A function coupling, a cam or a loop is no part of the mechanism: a
configuration sequence says it.

**A pinion that holds no part.** A rack and pinion's first-named joint may be a `RevoluteJoint` on
the part that carries it, connected to nothing: a reference axis where the CAD draws no pinion, so
two slides (a parallel gripper's fingers) couple to each other through it. The harvest makes it a
revolute pair from its carrier's link to a `KINEMATIC_LINK` of no part (AP242's needs no shape),
named by its label, at the value its joint holds (0 unless posed): the coupler is AP242's, the
coupling's name poses wherever a joint's does, and the pinion's range bounds the coupling as any
joint's does. A robot description has no link for it (below).

```python
import build123d as bd
from cad.build123d import configuration_sequence, gear_pair, mechanism_state, screw_pair
from cad import xbf

CURL = {"index_mcp_flexion": 90, "index_pip": 100, "index_dip": 70}  # degrees at a full curl
BONES = {"base": 30, "proximal": 40, "middle": 25, "distal": 20}     # lengths along +X

@xbf("XBF/index_finger.xbf")
def index_finger():
    bones, x = [], -BONES["base"]
    for name, length in BONES.items():
        bone = bd.Pos(x, 0, 0) * bd.Box(length, 16, 12, align=(bd.Align.MIN, bd.Align.CENTER, bd.Align.CENTER))
        bone.label, x = name, x + length
        bones.append(bone)
    for joint, parent, child in zip(CURL, bones, bones[1:]):
        knuckle = bd.Axis(child.location.position, (0, 1, 0))
        bd.RevoluteJoint(joint, parent, axis=knuckle, angular_range=(0, CURL[joint]))
        bd.RigidJoint(joint, child, bd.Plane(origin=knuckle.position, z_dir=knuckle.direction).location)
        parent.joints[joint].connect_to(child.joints[joint], angle=0)  # as built: straight
    finger = bd.Compound(children=bones, label="index_finger")
    gear_pair(finger, "index_curl", **CURL)                           # one control: 0 straight, 1 a fist
    return configuration_sequence(finger, "grip", [(0, {"index_curl": 0}), (1.5, {"index_curl": 1}),
                                                   (3, {"index_curl": 0})])

SWEEP, TRAVEL = {"left": -70, "right": 70}, 40                       # a door's turn and travel when open

@xbf("XBF/hypercar.xbf")
def hypercar():
    chassis = bd.Box(4400, 900, 400, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    chassis.label = "chassis"
    doors = []
    for side, y in (("left", 475), ("right", -475)):
        door = bd.Pos(400, y, 500) * bd.Box(1000, 50, 600)
        door.label = f"door_{side}"
        hinge = bd.Axis((800, 450 if side == "left" else -450, 500), (0.3, 0, 1))  # a helical hinge
        bd.CylindricalJoint(f"door_{side}", chassis, axis=hinge, angular_range=tuple(sorted((0, SWEEP[side]))),
                            linear_range=(0, TRAVEL))
        bd.RigidJoint(f"door_{side}", door, bd.Plane(origin=hinge.position, z_dir=hinge.direction).location)
        chassis.joints[f"door_{side}"].connect_to(door.joints[f"door_{side}"], angle=0, position=0)  # shut
        doors.append(door)
    car = bd.Compound(children=[chassis, *doors], label="hypercar")
    for side in SWEEP:                                                # each door's pitch: travel per turn
        screw_pair(car, side, **{f"door_{side}": 360 * TRAVEL / SWEEP[side]})
    return mechanism_state(car, "open", **SWEEP)                      # shut is as built
```

`cad xbf snapshot XBF/index_finger.xbf c.png --pose '{"index_curl": 0.6}'` draws the
knuckles at 54, 60 and 42 degrees: the picture of the same finger with no coupling at
`--pose '{"index_mcp_flexion": 54, "index_pip": 60, "index_dip": 42}'`; its range, `[0, 1]`, is
where every knuckle stays within its own. A model returning `posed(car().shape, {"left": -35,
"right": 35})` exports the doors a half turn and a half travel open. A gear train
is a gear pair: `gear_pair(actuator, "drive", rotor_spin=360, output=80, ...)`, a
quasi-direct-drive actuator's, ranged by its joints' limits. A coupling's joint in no pair is
left out of it and warned. A label names the joint in each placement of a
sub-assembly placed several times, and a name two couplings share takes the path of the assembly
holding each (`hand/index:curl`), as a label two pairs share does.

The xbf holds the mechanism as a subtree under `Main():100`, found by the
`TDataStd_UAttribute` of its GUID, of standard attributes only: `TDataStd_Name` on every
label, `TDataStd_NamedData` for an entity's AP242 name (`entity`) and attributes (named as
the standard names them), `TDataStd_ReferenceList` for references, `TDataStd_RealArray` and
`TDataStd_IntegerArray` for a configuration's values, `XCAFDoc_AssemblyItemRef` for an
occurrence (`mechanism.py` draws the tree); `test_kinematics`' conformance test walks the subtree and holds
it to law 12. A motion's segments say its ease as AP242's
`interpolation` (`linear_interpolation_type`, `synchronous_interpolation_type`; the last
segment's `discontinuous_interpolation_type`), and a coupling is its couplers under
`:6 "couplings"`, a label per coupling holding them. The structure serves couplings as
`kinematics.couplings`: `{name: {range, terms: [[pair, value index, ratio]]}}`, a side of the
range null where nothing bounds it. **STEP carries none of it**: OCCT reads AP242
kinematics but cannot write them, so every STEP, posed or not, is placements only.

`--pose` on `cad <type> snapshot` poses the mechanism at a
mechanism state (its name, among the structure's `configurations`) or at joint and coupling values (`'{"elbow": 45}'`, `'{"curl": 0.6}'`:
a turn in degrees, a slide in millimetres, the rest as built): the engine places each link by composing its pairs from the ground down,
exact forward kinematics, and draws that. No flag is as built. An unknown configuration, joint or
coupling, a value out of range (a joint's, a coupling's, or a joint's a coupling puts it at), a
coupling's joint set alone, a coupling set with one of its joints and a pair of a loop are
refused by name before anything renders.

**The viewer's Position** shows a slider per coupling under the Pose row (0 as built, its range
the coupling's, an open side spanning one turn or 100 mm of its first value): dragging it poses
every joint it drives through the page's forward kinematics (`xbfKinematics.js`), and choosing a
mechanism state puts it where that state stands on it (0 where it is off its line). A
coupling's joints have no slider of their own.
