# Kinematics: joints, mechanism states, couplings and configuration sequences

Read this file when the user asks to articulate or pose a mechanism, or when designing
or reviewing joints and their stops, couplings, named poses, posed files, the mechanism's
own motions, or what its parts declare for a simulator. An explode, a reveal, a showcase
or any movement that is not the mechanism's is a GLB's `animation()`: read
[Animation](animation.md) instead.

## Contents

- [The mechanism is written in the body](#the-mechanism-is-written-in-the-body)
- [Joints place parts and make the mechanism](#joints-place-parts-and-make-the-mechanism)
- [Mechanism states](#mechanism-states)
- [Couplings](#couplings)
- [Loops](#loops)
- [Joint stops](#joint-stops)
- [Declaring for a simulator](#declaring-for-a-simulator)
- [Configuration sequences](#configuration-sequences)
- [Reviewing motion](#reviewing-motion)

## The mechanism is written in the body

Give a model kinematics only where it is a mechanism: parts that move relative to each
other in use (a hinge, a robot arm, a gearbox, a lead screw). A joint exists because the
mechanism moves there: one added to slide a part out for an explode is an animation's
job, and the viewer's Position would show a slider for it.

An assembly's mechanism is written in its body, and its document keeps it:

- **Joints** are build123d's: `RevoluteJoint`, `LinearJoint`, `CylindricalJoint`,
  `BallJoint` and `RigidJoint`, connected with `connect_to`. The values they are
  connected at are the **as-built state**, the pose every file of the model shows.
- **Mechanism states** (named poses), **couplings** (joints that move together by ratio)
  and **configuration sequences** (joint values over time; the viewer calls them motions)
  are `cad.build123d`'s (`from cad.build123d import mechanism_state, gear_pair`). None of
  them moves the build, and a STEP, STL or 3MF export is placements only.
- **`posed(model(), state)`** returns the assembly placed at a state: the body of a posed
  model, or a check's pose ([below](#mechanism-states)).

## Joints place parts and make the mechanism

Build each part where it stands, give the parent the moving joint on an `Axis`, and give
the child a `RigidJoint` at the frame that joint places it at: for a revolute, the
hinge's own frame, `hinge.location`. Connected at 0, the child stays where it was built;
connected at another value, it moves there, and that value is as built.

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

- **An `Axis` and a `RigidJoint`'s location are in world coordinates**, not the part's
  own frame: an axis written in the part's frame is `axis.located(part.location)`.
  `connect_to` moves the child onto whatever axis it is given, so the run warns of a
  moving joint whose axis passes far from the part that holds it.
- **A revolute's `RigidJoint` is `hinge.location`, never a `bd.Plane` of the axis.** A
  plane takes its X from its Z, which on a part read turned (a STEP's leaf) or an axis read
  from geometry need not be the hinge's X, and the child then turns at 0: the run fails,
  naming the frame to use. A `RigidJoint` elsewhere, or one whose Z is not the joint's
  axis, is a placement: `connect_to` puts the child on the joint (a wheel built at the
  origin with `bd.RigidJoint("axle", wheel, bd.Location())`, put on its axle), and nothing
  is checked.
- **A slide's `RigidJoint` is the slide's position with no rotation.** build123d's
  `LinearJoint` turns the child by the inverse of that joint's orientation and by nothing
  else, so one on the plane of a slide along +Y stands the child on end, and no check
  catches it. On a rail that is itself turned, use the rail's orientation at the slide's
  position, `rail.location * bd.Location(guide.relative_axis.position)` (`guide` the
  `LinearJoint`):

  ```python
  slide = bd.Axis((0, -50, 10), (0, 1, 0))   # +position runs the carriage along +Y
  bd.LinearJoint("slide", rail, axis=slide, linear_range=(0, 100))
  bd.RigidJoint("slide", carriage, bd.Location(slide.position))
  rail.joints["slide"].connect_to(carriage.joints["slide"], position=20)   # as built: slide 20
  ```

- **`connect_to` on the joint that stays**:
  `parent.joints[name].connect_to(child.joints[name], angle=..., position=..., angles=...)`
  moves the child's part, and the document reads each joint's value from where its two
  parts then stand. So connect once both parts are placed and before they go into the
  compound that holds them: a part moved afterwards fails the run, and a `connect_to`
  made after the compound does not move what the compound holds.
- **Values are degrees and millimetres.** A joint's `angular_range` or `linear_range` is
  its limits, a value on a limit within them. A mechanism state that puts a joint outside
  them fails the run, and a pose outside them is refused. A configuration sequence that
  leaves a joint's limits is left out whole, and a coupling's value outside its range is
  left out of a mechanism state: the model still builds, and the run says so in a
  `warning:` line (`sequences 0 · warnings 1`).
- **A pair is named by its moving joint's label** (`elbow`). A label two pairs share
  takes the path of the part that holds it (`hand/left:knuckle`);
  `cad model inspect "$ID"` lists the names a pose takes.
- **Links are parts that move as one**: parts whose rigid joints are connected are one
  link, and a part below a jointed sub-assembly moves with it. The ground is every link
  no `connect_to` moved, and every part no joint places.
- **A nested assembly is paired by label.** build123d's `connect_to` cannot place a part
  inside a nested assembly: put each part where it stands and write the two joints there
  with one label, the `RigidJoint` at the moving joint's frame. The server pairs the
  moving joint with the `RigidJoint` of the same label nearest it in the tree. Two rigid
  joints of one label fasten their parts.
- **A jointed child brings its mechanism.** An assembly that places a child model's
  `.shape` holds the child's joints, states and sequences in its own document too, a
  joint two placements share named by its path as above. A part read from a file
  (`xbf.read`, `step.read`) brings none.

## Mechanism states

`mechanism_state(assembly, name, **values)` names a pose by joint label and returns the
assembly; a joint it leaves out stays as built (a state that names none is the as-built
pose under a name: a key, a `--zero`). A cylindrical joint takes `(angle, distance)`, a
ball joint its three angles and a coupling its value (`bend=0.5`). Mechanism states are
what the viewer's Position lists as presets, and what a `--pose` names.

A file of the mechanism in another pose is a model of its own: `posed(hinge(), state)`
returns a copy of the assembly with every part where the named state, or a mapping of
joint label to value, puts it. The copy keeps its joints, couplings, states and
sequences, with the asked values as its as-built state, so its page's Position and
motions still work.

```python
# src/hinge_poses.py
from cad import model
from cad.build123d import posed

from hinge import hinge


@model
def hinge_open():
    return posed(hinge(), "open")
```

`posed` takes the handle the model call returns (in a body, an assembly the body built
too). In a plain script (a check) it poses the document the server holds and returns the
tree `.shape` would, at that pose: placed parts, no joints. A plain script's `.shape`
carries no joints to pose, so pass the handle.

## Couplings

A coupling is a constraint, never a control: its joints move together, each by its
ratio, and only through it. Pick the function by the joints it relates; each refuses a
joint of another kind:

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
gear_pair(finger, "index_bend", index_mcp=90, index_pip=100, index_dip=70)   # degrees at a full bend
configuration_sequence(finger, "grip", [(0, {"index_bend": 0}), (1.5, {"index_bend": 1}), (3, {"index_bend": 0})])

gear_pair(assembly, "drive", sun=1.0, carrier=24 / 84, planet1=-0.952, planet2=-0.952, planet3=-0.952)
rack_and_pinion_pair(assembly, "traverse", pinion=1.0, rack=0.35)   # 0.35 mm of rack per degree
screw_pair(assembly, "feed", lead_screw=2.0)                        # 2 mm a turn; its value: the screw's turn
```

With each knuckle's `angular_range` from 0 to its full bend, `index_bend` ranges over
`[0, 1]`, and `--pose '{"index_bend": 0.6}'` poses the knuckles at 54, 60 and 42 degrees.
A coupling's name poses wherever a joint's does (states, sequences, `--pose`); the viewer
shows the coupling's slider and none of its joints', and setting one of its joints alone
is refused.

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

A robot description has no body or joint for such a pinion: the second slide follows the
first by the ratio of their ratios (MJCF's `<equality><joint>`, URDF's `<mimic>`), so the
file has the one control the hardware has. The pinion's range bounds the coupling, so
give it one no narrower than the racks' (build123d's default is 0 to 360). A pinion part
that turns is a pinion like any other: connect it.

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

The document keeps every pair, and poses none of a loop's (there is no solver): a
configuration sequence that moves one is left out with a warning, a pose that moves one
(a `--pose`, or a mechanism state where it is drawn or checked) is refused, and
`cad model ranges` sweeps none of them. A robot description follows the pairs from the
ground and leaves out the pair that reaches a link a second time, the one paired last.
The MJCF closes the loop there with an equality between two sites, one on each body where
the joint stands (a hinge is two `connect`s, a ball one), and does not enforce that
joint's range; where the last pair is a slide, which MuJoCo has no equality for, it
closes the loop at the loop's hinge or ball nearest it instead. The URDF, a tree, leaves
the joint out. The export's log says each.

## Joint stops

Where a joint's travel is limited by its parts meeting, `cad <type> ranges` (`model`, `xbf`, `step`)
finds the stops from the geometry: it moves each joint alone from the as-built pose, the others as
built, a degree or a millimetre at a time each way, until the parts meet. It writes nothing: write
the stops into the joint's `angular_range` or `linear_range` in the body, rounded towards zero, and
run the model again.

```bash
cad model ranges "$ID"
cad model ranges "$ID" --joint gripper
cad step ranges arm.step --step 0.5 --json
```

Reading a finding:

- **The stop** each way is where the joint's child link meets its parent link (each with the links
  fixed to it), whatever the other joints do, and it names the two parts that met. Stops are in
  degrees or millimetres around the as-built pose, in the joint's own values where its as-built value
  is not zero.
- **A clash**, said beside a stop, is something the joint moves meeting another link first in this
  pose of the other joints: a self-collision of the pose, not the joint's range (an arm drawn folded
  clashes its wrist on its shoulder a few degrees out). Write the stop; a simulator's contacts hold
  the clash.
- **Check the pair before adopting the stop**, with a posed snapshot there. A stop made by a pair
  that does not limit the hardware (a vendor's servo cover the jaw clears) is not the joint's range,
  and neither is a stop wider than the actuator's own travel: write the datasheet's travel instead.
  A stop is where surfaces come near, not where solids overlap, so it reads a little short of
  contact (a lid that folds back flat at 180 reads 174): `cad model interference "$ID" --pose
  '{"hinge": 178}'` at and past it is the exact answer, with the joint's range widened for the test.
- **No stop.** A turn is swept a full turn each way and a slide the document's extent; a joint clear
  that far has none (`why`: `clear all the way round`). A cylindrical or spherical joint and a joint
  of a closed loop are not swept, and a warning says so. A document with no joint fails with
  `no_joints`.

How it decides that two parts meet:

- **Clearance.** Surfaces within `--clearance` (0.3 mm, the least it takes) count as touching, so a
  stop is where the parts all but touch. A larger clearance only narrows a range. Every gap is
  measured to within 0.6 mm over the true one, never under it. Each part is tested on its own
  surface, not on the collision shape a simulator would use.
- **Near a turn's axis.** A millimetre is a wide angle close to the axis, so in a turn a surface also
  counts as near only where its gap is under a tenth of its distance from the axis: within 5.7
  degrees of turning from touching. That decides within ten times the clearance of the axis (3 mm at
  0.3 mm), which is where a lid, a door or a flap hinged on its edge lands: it stops about 6 degrees
  short of flat, whatever the clearance.
- **Touching or near as built.** Parts that touch as built (a horn on its servo), or stand under
  0.3 mm apart, meet only where their contact grows by about 15 mm^2 on a surface that stops the
  motion, or where one is pushed into the other; sliding along each other (a pin in its bore, a
  carriage on its rail) stops nothing. Parts a little farther apart meet only where their gap closes
  to under half of what it was beyond 0.3 mm (0.1 mm for a 0.5 mm gap), not where it narrows a hair.
  At a larger clearance the finding lists the pairs within it as built (`near as built:`), and a stop
  one of them makes says `closed to 0.2 from 0.5 mm as built`.
- **Turning on an output.** A vendor often draws a motor as one solid, case and output flange
  together, with the next link bolted to the output. A pair touching as built on a surface about the
  joint's axis is read as an output and what turns on it: that face, and what lies within the reach
  of their contact about the axis (a locating boss, a bolt's seat), stops nothing, and the finding
  lists the pair (`turns on: plate (link2) on motor (link1)`). Where a stop a few degrees out still
  names that pair `touching as built`, the output carries something that reaches past its face (an
  arm, a cam): split the solid in the model.
- **Overlapping as drawn.** Simplified vendor parts are often drawn sunk into each other. Such a pair
  meets only where one is pushed 0.6 mm deeper into the other than drawn. The finding lists it
  (`overlapping as drawn ... by 180 mm^3, 1.0 mm deep`), and a stop it makes says `deeper than
  drawn`: that stop lies past the true one by up to about that depth, so read it against the geometry
  or the datasheet.

The sweep's time follows the parts' surface area and detail, not their number: an arm of a few
hundred small parts and six joints takes tens of seconds, one of a few large freeform shells minutes,
and a finer `--step` costs in proportion. For a narrower question (do the jaws close?) use `--joint`
or a posed snapshot.

`--json` carries every number in `measurements.joints`, each joint under `joint`: `lower`, `upper`
and `range` in the joint's own values; the `*_contact` and `*_clash` parts, each with its `gap` in mm
(and `near`, the gap as built, or `overlap` in mm^3 and `depth` in mm for a pair drawn overlapping);
the pairs touching as built (`resting`), near as built (`near`: `rest`, and the gap at each stop),
drawn overlapping (`overlapping`: `volume`, `depth`) and turning on an output (`riding`); and `why`
for a joint with no stop.

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
  `location` is a `Location` (`Pos`, `Rot`) or a `Plane` in the part's own frame, the one its
  geometry is in before `part.location` places it (a `bd.Box` is centred on it unless aligned), so the
  frame moves with the part however a joint or a placement moves it. A frame is a part's, never an
  assembly's; a second frame of one name on a part replaces the first.
- **`body(part, name=None)`** keeps a part a body of its own (MJCF a child body, URDF a link
  on a fixed joint) where it would merge into its link: its mass, meshes and frames go with it.
- **`limits(assembly, joint, effort=, velocity=)`** bounds every revolute or linear joint of that
  label on the assembly or below it, in SI, from the drive's datasheet: URDF's `<limit>`, MJCF's
  `actuatorfrcrange` (MJCF has no speed bound). Declare it after the joint is made. A joint without
  one is written `effort="0" velocity="0"` in a URDF, which a ROS controller reads literally
  (`cad urdf validate` warns of it).
- **`mass(part_or_assembly, grams)`** is what it weighs in all: its solids keep the ratios their
  materials' densities give and are scaled alike to make up `grams`, so the centre of mass and the
  shape of the inertia stay the geometry's. Where none of them has a material they share one
  density; a part with no material among parts that have one carries none of the total, and the
  export says so. An inner `mass()` fixes its own subtree; an outer one scales only the solids no
  inner one holds, to make up its total less what the inner ones and its point masses weigh. A total
  those reach or pass, or one its parts have no volume to carry, is refused when exported.
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

They travel with the part as build123d moves it: a copy, `moved` and `located` keep them.

A simulation's choices are not declared on the model (what a part collides as, contact friction,
pairs that never collide, a joint's armature, damping and dry friction, actuators and their gains):
[exports](exports.md#robot-descriptions) says where they are made.

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
  (1e-3 radian, 1e-3 of the model's size).

`ease` is `cubic` (each step eased in and out, every joint arriving together at every
waypoint) or `linear` (constant speed). Between two waypoints a fraction `s` of the way in
time, a `cubic` value is `a + (3 s^2 - 2 s^3) (b - a)` and a `linear` one `a + s (b - a)`,
each joint on its own; a program that plays the sequence elsewhere (a simulator, a check
that follows it in time) uses the same formula. A sequence is a finite clip, and a player
repeats it: one that comes back writes its way back as waypoints. A coupling's name poses in
waypoints and sweeps like a joint's.

- **Prefer waypoints.** A sequence of waypoints is a few numbers in the document and a
  few keys in a GLB; a function of time is sampled on every run that runs its body.
- **A path the joints must follow together is dense waypoints with `ease="linear"`.** An ease
  moves each joint on its own between two waypoints, so two sound poses do not make a sound
  path between them: a foot that should stay on the floor slides, the knee and the hip
  easing separately. Solve the path in your own code (the pelvis over feet that stay, a
  linkage that closes) and write its samples, forty to sixty of them, as waypoints.
- **The fixed link is a choice of frame.** A mechanism has one ground, and a sequence moves
  the joints under it: a robot whose ground is its pelvis crouches by lifting its feet. A
  motion that is right in that frame says nothing of what a floor would hold. Check it in
  the frame of what the robot stands on: the supporting foot's world placement at each
  sample, which should not move, and the centre of mass over it.
- **Every GLB exported from the model carries each sequence** as a glTF animation of its
  name, keyed within 1e-3 of the model's size of the true motion.

## Reviewing motion

A pose is drawn on demand:

```bash
cad model snapshot "$ID" tmp/open.png --pose open
cad model snapshot "$ID" tmp/elbow_45.png --pose '{"elbow": 45}'
cad model snapshot "$ID" tmp/stride.png --pose walk@0.6
```

`--pose` takes a mechanism state's name, joint and coupling values as JSON (a turn in
degrees, a slide in millimetres; the rest as built), or a configuration sequence at a
time of it (`walk@0.6`: the mechanism where the playbar would have it then). An unknown
state, joint or coupling, a value out of range and a coupling's joint set alone are
refused by name before anything renders.

A list of jobs draws a sequence's frames in one command, each job's `jointValues` a pose
as `--pose` takes it. A preset camera is fitted to each picture:
[a camera that does not move](snapshot-review.md#annotations-and-quick-edit-views) says
how to hold one.

```bash
cad model snapshot --job tmp/frames.json
```

```json
[{"input": "<id>", "camera": "right", "jointValues": "walk@0.0", "outputs": [{"path": "tmp/walk_00.png"}]},
 {"input": "<id>", "camera": "right", "jointValues": "walk@0.2", "outputs": [{"path": "tmp/walk_01.png"}]}]
```

The frames stand under the mechanism's fixed link, as the sequence is written: a robot whose
ground is its pelvis walks in the air. For a person, the model's page poses the document
live under Position (a slider per coupling and per joint no coupling moves, the mechanism
states as presets) and plays its configuration sequences on the playbar under the model.

A pose or a motion shows movement; it does not measure it. A check of the model measures
the parts as built, so a part that clears there can still pass through another
mid-motion. `cad model interference "$ID" --pose crouch --pose walk@0.6` measures every pair of
parts at each pose it is given: give it every state, and each sequence at the times that matter
([interference](inspection-and-validation.md#interference)). To measure one pair at a pose in a
check script, pose the model there and take its parts with `find_part`, copied from
[Opening geometry](inspection-and-validation.md#opening-geometry):

```python
from cad.build123d import leaves, overlap_volume, posed

from hinge import hinge

tree = posed(hinge(), "open")
arm, base = find_part(tree, "arm"), find_part(tree, "base")
print(overlap_volume(arm.solids()[0], base.solids()[0]))   # 0: the open arm clears the base
```
