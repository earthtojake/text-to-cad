# Kinematics: joints, mechanism states, couplings and configuration sequences

Read this file when the user asks to articulate or pose a mechanism, or when designing
or reviewing joints, couplings, named poses, posed files, the mechanism's own
motions, or what its parts declare for a simulator. An explode, a reveal, a showcase
or any movement that is not the mechanism's is a GLB's `animation()`: read
[Animation](animation.md) instead.

## Contents

- [The mechanism is written in the body](#the-mechanism-is-written-in-the-body)
- [Joints place parts and make the mechanism](#joints-place-parts-and-make-the-mechanism)
- [Mechanism states](#mechanism-states)
- [Couplings](#couplings)
- [Loops](#loops)
- [Declaring for a simulator](#declaring-for-a-simulator)
- [Configuration sequences](#configuration-sequences)
- [Reviewing motion](#reviewing-motion)

## The mechanism is written in the body

Give a model kinematics only when it is a mechanism: parts that move relative to each
other in use (a hinge, a robot arm, a gearbox, a lead screw). An assembly's mechanism
is written in its body, and its document keeps it:

- **Joints** are build123d's: `RevoluteJoint`, `LinearJoint`, `CylindricalJoint`,
  `BallJoint` and `RigidJoint`, connected with `connect_to`. The values they are
  connected at are the **as-built state**, the pose every file of the model shows.

The functions that say more are `cad.build123d`'s, named after the STEP AP242 entities
they write (`from cad.build123d import mechanism_state, gear_pair`):

- **Mechanism states** name other poses: `mechanism_state(assembly, name, **values)`.
- **Couplings** make joints move together by ratio, one function per pair the document
  writes: `gear_pair`, `rack_and_pinion_pair` and `screw_pair(assembly, name, **joints)`.
- **Configuration sequences** are the mechanism's motions over time:
  `configuration_sequence(assembly, name, ...)`. The viewer calls them motions.
- **`posed(model(), state)`** returns the assembly placed at a named state: the body of
  a posed model, or a check's pose ([below](#mechanism-states)).

None of the first three moves the build. The document keeps the mechanism, its states,
couplings and sequences; a STEP, STL or 3MF export is placements only, and a GLB export
bakes each configuration sequence into an animation clip of its name.

## Joints place parts and make the mechanism

Build each part where it stands, give the parent the moving joint on an `Axis`, and give
the child a `RigidJoint` at the frame that joint places it at: a revolute's own frame,
`hinge.location` (the parent's placement times the joint's axis in it), or, for a
`LinearJoint`, the axis's position with no rotation (below). Connected at 0, the child stays
where it was built; connected at another value, it moves there, and that value is as
built. The server enforces it where angle 0 cannot be as built: a child whose `RigidJoint` stood
at its joint's origin with its Z on the joint's axis, and that `connect_to` turned about that axis
at 0, fails the run, naming the joint, the turn and the frame to use instead. A `RigidJoint`
elsewhere, or one whose Z is not the joint's axis, is a placement: `connect_to` puts the child on
the joint (a wheel built at the origin with `bd.RigidJoint("axle", wheel, bd.Location())`, put on
its axle), and nothing is checked. A `RigidJoint` on `bd.Plane(origin=axis.position, z_dir=axis.direction)` takes its X
from its Z, and a part read turned (a STEP's leaf) or an axis read from geometry, whose
direction carries `1e-17` of noise, gives the hinge another X, so the child turns at 0. Snap a
direction read from geometry before making an `Axis` of it (a component within `1e-9` of 0 is
0). A joint's `Axis` and a `RigidJoint`'s location are in world coordinates, not the
part's own frame: an axis written in the part's frame is `axis.located(part.location)`, and
a moving joint's axis that passes farther from its part, and from every part rigidly joined
to it, than each one's own size is warned as a local one, since `connect_to` moves the child
onto whatever axis it is given:

```python
# src/hinge.py
import build123d as bd
from cad import model
from cad.build123d import configuration_sequence, mechanism_state

ELBOW = ((40, 0, 20), (0, -1, 0))   # the elbow's origin and direction: +angle lifts the arm


@model
def hinge():
    base = bd.Box(100, 60, 20, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    arm = bd.Pos(40, 0, 20) * bd.Box(120, 20, 10, align=(bd.Align.MIN, bd.Align.CENTER, bd.Align.MIN))
    base.label, arm.label = "base", "arm"
    elbow = bd.RevoluteJoint("elbow", base, axis=bd.Axis(*ELBOW), angular_range=(-10, 120))
    bd.RigidJoint("elbow", arm, elbow.location)   # the hinge's own frame: at 0 the arm stays put
    elbow.connect_to(arm.joints["elbow"], angle=30)   # as built: elbow 30
    assembly = bd.Compound(children=[base, arm], label="hinge")
    mechanism_state(assembly, "closed", elbow=0)
    mechanism_state(assembly, "open", elbow=90)
    return configuration_sequence(assembly, "cycle", [(0, "closed"), (2, "open"), (5, "closed")])


if __name__ == "__main__":
    hinge()
```

A slide places its child by position alone. build123d's `LinearJoint` turns the child by
nothing but the inverse of the child's `RigidJoint` orientation, so that joint is
`bd.Location(slide.position)`, the slide's position with no rotation; one on the plane of a
slide along +Y would stand the child on end. On a rail that is itself turned, the rail's
orientation at the slide's position: `rail.location * bd.Location(guide.relative_axis.position)`:

```python
# src/linear_guide.py
import build123d as bd
from cad import model
from cad.build123d import configuration_sequence, mechanism_state

SLIDE = ((0, -50, 10), (0, 1, 0))   # the slide's origin and direction: +position runs the carriage along +Y


@model
def linear_guide():
    rail = bd.Box(30, 140, 10, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    carriage = bd.Pos(0, -50, 10) * bd.Box(40, 30, 15, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    rail.label, carriage.label = "rail", "carriage"
    slide = bd.Axis(*SLIDE)
    bd.LinearJoint("slide", rail, axis=slide, linear_range=(0, 100))
    bd.RigidJoint("slide", carriage, bd.Location(slide.position))   # the slide's position, no rotation
    rail.joints["slide"].connect_to(carriage.joints["slide"], position=20)   # as built: slide 20
    assembly = bd.Compound(children=[rail, carriage], label="linear_guide")
    mechanism_state(assembly, "home", slide=0)
    mechanism_state(assembly, "end", slide=100)
    return configuration_sequence(assembly, "stroke", [(0, "home"), (2, "end"), (4, "home")])


if __name__ == "__main__":
    linear_guide()
```

- **`connect_to` on the joint that stays**:
  `parent.joints[name].connect_to(child.joints[name], angle=..., position=..., angles=...)`
  moves the child's part. Connect parts before putting them in the compound that holds
  them.
- **Values are degrees and millimetres.** A joint's `angular_range` or `linear_range` is
  its limits, a value on a limit within them. A mechanism state that puts a joint outside
  them fails the run, in one line naming the state, the joint, the value and the range; a
  pose outside them is refused. A coupling's value outside its range is left out of a
  mechanism state, and a configuration sequence that goes outside a joint's limits is left
  out, each with a warning.
- **A pair is named by its moving joint's label** (`elbow`). A label two pairs share
  takes the path of the part that holds it (`hand/left:knuckle`).
- **Links are parts that move as one**: parts whose rigid joints are connected are one
  link, and a part below a jointed sub-assembly moves with it. The ground is every link
  no `connect_to` moved, and every part no joint places.
- **A nested assembly is paired by label.** build123d's `connect_to` cannot place a part
  inside a nested assembly: put each part where it stands, write the two joints there
  with one label, and the server pairs the moving joint with the `RigidJoint` of the same
  label nearest it in the tree. Two rigid joints of one label fasten their parts.
- **The document keeps what STEP AP242 can say, and nothing else.** A pair the built
  parts contradict (its part moved after `connect_to`, connected after its compound was
  made, a rigid joint off the joint's axis, or two parts rigid joints make one body)
  fails the run by name: fix where the part stands. Pairs closing a loop are kept and not
  posed ([Loops](#loops)). A mechanism state, configuration sequence or coupling naming a joint the
  assembly does not hold fails the run, as does a coupling driving a joint its pair does
  not relate.
- **No helper joints.** A joint exists because the mechanism moves there. A prismatic
  joint per part only to slide it out for an explode is an animation's job
  ([animation](animation.md)), and the viewer's Position would show a slider for each.

## Mechanism states

`mechanism_state(assembly, name, **values)` names a pose by joint label, the joints it
leaves out as built (a state that names none is the as-built pose under a name: a key, a
`--zero`), and returns the assembly. A cylindrical joint takes
`(angle, distance)` and a ball joint its three angles; a coupling takes its value
(`curl=0.5`). Mechanism states are what the viewer's Position lists as presets, and what
a snapshot's `--pose` names.

A file of the mechanism in another pose is a model of its own: `posed(hinge(), state)`
returns a copy of the assembly with every part where the named state, or a mapping of
joint label to value, puts it. The copy keeps its joints, couplings, states and
sequences, with the asked values as its as-built state, so its page's Position and
motions still work. An unknown state or joint is refused by name.

`posed` takes the handle the model call returns, as every verb does. In a body it poses
the child's shape. In a plain script (a check) it poses the document the server holds and
returns the tree `.shape` would, at that pose: placed parts, no joints. A plain script's
`.shape` carries no joints, so `posed(hinge().shape, ...)` there is refused with the call
to make instead.

```python
# src/hinge_poses.py
from cad import model
from cad.build123d import posed

from hinge import hinge


@model
def hinge_open():
    return posed(hinge(), "open")


if __name__ == "__main__":
    hinge_open()
```

## Couplings

A coupling is a constraint, never a control: its joints move together, each by its
ratio, and only through it. Pick the function by the joints it relates; each writes the
AP242 pair it is named after and refuses a joint of another kind:

| Function | Joints | Each joint takes |
| --- | --- | --- |
| `gear_pair(assembly, name, **joints)` | two or more revolute joints | a ratio: degrees per unit of the coupling |
| `rack_and_pinion_pair(assembly, name, **joints)` | the first a revolute (pinion, or a pinion that holds no part) or prismatic (rack) joint, every other of the other kind | a ratio: degrees or millimetres per unit |
| `screw_pair(assembly, name, joint=pitch)` | one cylindrical joint | its pitch: millimetres of travel per 360 degrees of turn; the coupling's value is the turn |

At value `c` each joint stands at its as-built value plus its ratio times `c`, so
`c = 0` is as built. Its range is its joints' limits: the tightest interval of `c` in
which every joint stays within its own (a joint with no limits bounds nothing), so give
the joints the limits the mechanism has. A joint takes at most one coupling, and a ball
joint none. Two slides couple through a pinion (below), even one the CAD does not draw;
a slide and a cylindrical joint's turn have no pair: drive them by a configuration sequence.

```python
# src/index_finger.py
import build123d as bd
from cad import model
from cad.build123d import configuration_sequence, gear_pair

CURL = {"index_mcp": 90, "index_pip": 100, "index_dip": 70}           # degrees at a full curl
BONES = {"base": 30, "proximal": 40, "middle": 25, "distal": 20}     # lengths along +X


@model
def index_finger():
    bones, x = [], -BONES["base"]
    for name, length in BONES.items():
        bone = bd.Pos(x, 0, 0) * bd.Box(length, 16, 12, align=(bd.Align.MIN, bd.Align.CENTER, bd.Align.CENTER))
        bone.label, x = name, x + length
        bones.append(bone)
    for joint, parent, child in zip(CURL, bones, bones[1:]):
        knuckle = bd.Axis(child.location.position, (0, 1, 0))
        hinge = bd.RevoluteJoint(joint, parent, axis=knuckle, angular_range=(0, CURL[joint]))
        bd.RigidJoint(joint, child, hinge.location)
        hinge.connect_to(child.joints[joint], angle=0)   # as built: straight
    finger = bd.Compound(children=bones, label="index_finger")
    gear_pair(finger, "index_curl", **CURL)                             # 0 straight, 1 a fist
    return configuration_sequence(finger, "grip", [(0, {"index_curl": 0}), (1.5, {"index_curl": 1}),
                                                   (3, {"index_curl": 0})])


if __name__ == "__main__":
    index_finger()
```

`--pose '{"index_curl": 0.6}'` poses the knuckles at 54, 60 and 42 degrees; its range,
`[0, 1]`, is where every knuckle stays within its own. The viewer shows the coupling's
slider and none of its joints', and setting one of its joints alone is refused. A
planetary stage turns its carrier and planets from the sun, ranged by the sun's limits;
a pinion drives a rack; a lead screw advances 2 mm a turn:

```python
gear_pair(assembly, "drive", sun=1.0, carrier=24 / 84, planet1=-0.952, planet2=-0.952, planet3=-0.952)
rack_and_pinion_pair(assembly, "traverse", pinion=1.0, rack=0.35)   # 0.35 mm of rack per degree
screw_pair(assembly, "feed", lead_screw=2.0)                        # its value: the screw's turn
```

**Two slides, one pinion.** A parallel gripper's fingers are two racks on one pinion. Where
the CAD draws no pinion, the pinion is a `RevoluteJoint` on the part that carries it,
connected to nothing: a reference axis. Named first in a `rack_and_pinion_pair`, it holds no
part and moves nothing, and the two slides move together through it, each by its ratio, the
pitch circle's millimetres per degree (`2 * pi * r / 360`):

```python
for side, x, out in (("left", -30, -1), ("right", 30, 1)):
    slide = bd.LinearJoint(side, palm, axis=bd.Axis((x, 0, 10), (out, 0, 0)), linear_range=(0, 30))
    bd.RigidJoint(side, fingers[side], bd.Location((x, 0, 10)))
    slide.connect_to(fingers[side].joints[side], position=0)
bd.RevoluteJoint("pinion", palm, axis=bd.Axis((0, 0, 10), (0, 1, 0)), angular_range=(-360, 360))
rack_and_pinion_pair(gripper, "grip", pinion=1, left=0.15272, right=0.15272)   # r = 8.75 mm
```

The document keeps the pinion as AP242 has it, a revolute pair to a link of no part, and
`grip` poses the fingers wherever a joint's name does. A robot description has no body or
joint for it: the right finger follows the left by the ratio of their ratios (MJCF's
`<equality><joint>`, URDF's `<mimic>`), so the file has the one control the hardware has.
The pinion's range bounds the coupling, so give it one no narrower than the racks'
(build123d's default is 0 to 360). A pinion part that turns is a pinion like any other:
connect it.

## Loops

A linkage whose pairs close a loop (a four-bar, a slider-crank, a parallel gripper's
fingers on two links each) is built as any mechanism: every part where it stands. Connect
the joints that make a tree from the ground, each with `connect_to`, then pair the loop's
last joint by label: a moving joint on one part and a `RigidJoint` of the same label at its
frame on the other, where both already stand. That joint closes the loop:

```python
def hinge(name, holder, child, at, connect=True):
    joint = bd.RevoluteJoint(name, holder, axis=bd.Axis(at, (0, 1, 0)), angular_range=(-360, 360))
    bd.RigidJoint(name, child, joint.location)
    if connect:
        joint.connect_to(child.joints[name], angle=0)

hinge("crank", base, crank, A)
hinge("knee", crank, coupler, B)
hinge("rocker", base, rocker, D)
hinge("pin", rocker, coupler, C, connect=False)   # the loop's last joint: the coupler is placed already
```

The document keeps every pair; a loop's pairs are not posed (there is no solver), so a
mechanism state or a configuration sequence that moves one is refused or left out, and
`cad model ranges` sweeps none of them. A robot description follows the pairs from the
ground and leaves out the pair that reaches a link a second time, the one paired last: the
MJCF closes the loop there with an equality between two sites, one on each body where the
joint stands (a hinge is two `connect`s, a ball one), and the URDF, a tree, leaves it out
and says so in the export's log. A slide never closes a loop in an MJCF (MuJoCo has no
slide equality): where the last pair is a slide, the description closes the loop at the
loop's hinge or ball nearest it instead. The closing joint's range is not enforced.

## Declaring for a simulator

A mechanism exported as a robot description (an MJCF or a URDF:
[exports](exports.md#robot-descriptions)) takes its links, joints, couplings and states from the
mechanism and each link's mass from its parts' materials. Declarations from `cad.build123d` say
the rest of what is true of the machine, on finished parts, after the last operation, as a material
is set:

```python
from cad.build123d import body, frame, free, limits, link, mass, point_mass

frame(arm, "tool", bd.Pos(240, 0, 25))      # a named frame, in the arm's own frame (mm)
body(camera, "camera_mount")                # its own body, fixed to the link it is fastened to
limits(root, "elbow", effort=27, velocity=6.28)  # the elbow's drive: N*m and rad/s (N, m/s on a slide)
point_mass(housing, 85, bd.Pos(0, 0, 12), name="servo")  # g, at a point in the housing's own frame (mm)
mass(forearm, 310)                          # g: the forearm assembly as weighed, the servo included
link(forearm, "forearm_link")               # the name of the link the forearm's parts make
free(root)                                  # the base is not bolted to the world (a mobile robot)
```

- **`frame(part, name, location)`** names a frame on a part (a tool tip, a camera mount, a sensor):
  `location` is a `Location` (`Pos`, `Rot`) or a `Plane` in the part's OWN frame, the one its
  geometry is in before `part.location` places it (a `bd.Box` is centred on it unless aligned), so the
  frame moves with the part however a joint or a placement moves it. A frame is a part's, never an
  assembly's; a second frame of one name on a part replaces the first.
- **`body(part, name=None)`** keeps a part a body of its own (MJCF a child body, URDF a link
  on a fixed joint) where it would merge into its link: its mass, meshes and frames go with it.
- **`limits(assembly, joint, effort=, velocity=)`** bounds every revolute or linear joint of that
  label on the assembly or below it, in SI, from the drive's datasheet: URDF's `<limit>`, MJCF's
  `actuatorfrcrange` (MJCF has no speed bound). Declare it after the joint is made. A joint without
  one is written `effort="0" velocity="0"` in a URDF, which `cad urdf validate` warns a ROS
  controller reads literally.
- **`mass(part_or_assembly, grams)`** is what it weighs in all: its solids keep the ratios their
  materials' densities give (one density for all where none of them has a material; a part with no material among parts that have one carries none of the total, and the export says so) and are scaled alike to
  make up `grams`, so the centre of mass and the shape of the inertia stay the geometry's. An inner
  `mass()` fixes its own subtree; an outer one scales only the solids no inner one holds, to make up
  its total less what the inner ones and its point masses weigh. A total its point masses and inner
  masses reach or pass, or one its parts have no volume to carry, is refused when exported.
- **`point_mass(part, grams, at, name=, inertia=)`** adds a lump the CAD leaves out (a motor inside a
  filled housing) at `at`, a `Location` in the part's own frame as a frame's is, with no inertia of
  its own unless `inertia=(ixx, iyy, izz)` (kg*m^2, in `at`'s axes) gives it. Several per part, each
  by name. Every `mass()` above it counts it.
- **`free(part_or_assembly)`**: what it holds is not bolted to the world. On the top assembly, the
  robot's base floats (MJCF a `<freejoint>`, its seven values in every key; a URDF's root floats
  already); in a model with no joints, the one top-level part or assembly it names. A free node none of
  whose parts is in a link hung from the world (a forearm) is refused by name: declare it on what holds
  the base. Bolted is the default.
- **`link(part_or_assembly, name)`** names the link its parts make, instead of the label of the
  jointed assembly that holds the link's joint, else its first part's. An inner declaration names its
  own link over an outer one; a body takes its `body()` name. One link whose parts declare two names,
  a name declared on two links, and `world` (the ground's) are refused by name.

They travel with the part as build123d moves it (a copy, `moved` and `located` keep them), and
cost nothing until a robot description is exported. A part that declares other ones is a
prototype of its own in the document.

A simulation's choices are not declared on the model: what a part collides as (each part's own
mesh unless chosen otherwise), contact friction, pairs that never collide, a joint's armature,
damping and dry friction, actuators and their gains. Those are made on the exported robot in
MuJoCo's own API ([exports](exports.md#robot-descriptions) says whose they are).

## Configuration sequences

A configuration sequence is the mechanism's motion: joint values over time, written in
the body beside the mechanism states:

```python
configuration_sequence(arm, "cycle", [(0, "folded"), (2, "reach"), (5, "folded")])  # waypoints, eased
configuration_sequence(arm, "wave", [(0, {"wrist": -30}), (1, {"wrist": 30}), (2, {"wrist": -30})],
                       ease="linear")
configuration_sequence(arm, "nod", lambda t: {"elbow": 45 + 20 * math.sin(t)}, duration=6)  # of time
```

`configuration_sequence(assembly, name, waypoints_or_fn=None, *, sweep=None,
duration=None, ease="cubic")` takes one of:

- waypoints `[(t, pose), ...]`: seconds from 0, increasing, each pose a mechanism
  state's name or `{joint: value}` (the rest as built); the last time is the duration;
- `sweep={joint: (from, to)}` with `duration`;
- a function `t -> {joint: value}` with `duration`, kept as samples close enough to it
  (1e-3 radian, 1e-3 of the model's size), the same code always the same samples.

`ease` is `cubic` (each step eased in and out, every joint arriving together at every
waypoint) or `linear` (constant speed). A sequence is a finite clip, and a player repeats
it: one that comes back writes its way back as waypoints. A coupling's name poses in
waypoints and sweeps like a joint's. A sequence naming a mechanism state or a joint the
assembly lacks fails the run.

- **Prefer waypoints.** A sequence of waypoints is a few numbers in the document and a
  few keys in a GLB; a function of time is sampled on every run that runs its body.
- **A sequence costs nothing outside a GLB**: STEP, STL and 3MF carry no motion.
- Every GLB exported from the model carries each sequence as a glTF animation of its
  name, keyed within 1e-3 of the model's size of the true motion. Blender, three.js and
  the CAD Viewer play it, repeating.

A configuration sequence moves joints only. What the mechanism does not do (parts flying
apart, a cover vanishing, a part spinning for show) is an animation of the GLB:
[Animation](animation.md).

## Reviewing motion

A pose is drawn on demand:

```bash
cad model snapshot "$ID" tmp/open.png --pose open
cad model snapshot "$ID" tmp/elbow_45.png --pose '{"elbow": 45}'
```

`--pose` takes a mechanism state's name, or joint and coupling values as JSON (a turn
in degrees, a slide in millimetres; the rest as built): it says how the picture is
drawn. An unknown state, joint or coupling, a value out of range and a coupling's joint
set alone are refused by name before anything renders.

On the model's page, Position poses the document live: a slider per coupling and per
joint no coupling moves, and the mechanism states as presets. The playbar under the model, in the
tools view and Preview alike, plays the document's configuration sequences (play, pause, scrub, loop, speed), so the page is
where to review one.

A pose or a motion shows movement; it does not measure it. A check of the model measures
the parts as built, so a part that clears there can still pass through another
mid-motion. Measure a pose by posing the model in the check, taking its parts placed with
`leaves(tree)` (`cad.build123d`) through `find_part`, copied from
[Opening geometry](inspection-and-validation.md#opening-geometry). Where a joint's stops are
the parts meeting, `cad model ranges` finds them ([Joint stops](../SKILL.md#joint-stops)):

```python
from cad.build123d import leaves, overlap_volume, posed

from hinge import hinge

tree = posed(hinge(), "open")
arm, base = find_part(tree, "arm"), find_part(tree, "base")
print(overlap_volume(arm.solids()[0], base.solids()[0]))   # 0: the open arm clears the base
```
