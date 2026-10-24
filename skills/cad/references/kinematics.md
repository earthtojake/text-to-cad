# Kinematics: joints, mechanism states, couplings and configuration sequences

Read this file when the user asks to articulate or pose a mechanism, or when designing
or reviewing joints, couplings, named poses, posed files or the mechanism's own
motions. An explode, a reveal, a showcase or any movement that is not the mechanism's
is a GLB's `animation()`: read [Animation](animation.md) instead.

## Contents

- [The mechanism is written in the body](#the-mechanism-is-written-in-the-body)
- [Joints place parts and make the mechanism](#joints-place-parts-and-make-the-mechanism)
- [Mechanism states](#mechanism-states)
- [Couplings](#couplings)
- [Configuration sequences](#configuration-sequences)
- [Reviewing motion](#reviewing-motion)

## The mechanism is written in the body

Give a model kinematics only when it is a mechanism: parts that move relative to each
other in use (a hinge, a robot arm, a gearbox, a lead screw). An assembly's mechanism
is written in its body, and its document keeps it:

- **Joints** are build123d's: `RevoluteJoint`, `LinearJoint`, `CylindricalJoint`,
  `BallJoint` and `RigidJoint`, connected with `connect_to`. The values they are
  connected at are the **as-built state**, the pose every file of the model shows.

The functions that say more are `cadgen.ap242`'s, named after the STEP AP242 entities
they write (`from cadgen.ap242 import mechanism_state, gear_pair`):

- **Mechanism states** name other poses: `mechanism_state(assembly, name, **values)`.
- **Couplings** make joints move together by ratio, one function per pair the document
  writes: `gear_pair`, `rack_and_pinion_pair` and `screw_pair(assembly, name, **joints)`.
- **Configuration sequences** are the mechanism's motions over time:
  `configuration_sequence(assembly, name, ...)`. The viewer calls them motions.
- **`posed(assembly, state)`** returns the assembly placed at a named state: the body of
  a posed model ([below](#mechanism-states)).

None of the first three moves the build. The document keeps the mechanism, its states,
couplings and sequences; a STEP, STL or 3MF export is placements only, and a GLB export
bakes each configuration sequence into an animation clip of its name.

## Joints place parts and make the mechanism

Build each part where it stands, give the parent the moving joint on an `Axis`, and give
the child a `RigidJoint` on the plane of that same axis. Connected at 0, the child stays
where it was built; connected at another value, it moves there, and that value is as
built:

```python
# src/hinge.py
import build123d as bd
from cadgen import model
from cadgen.ap242 import configuration_sequence, mechanism_state

ELBOW = ((40, 0, 20), (0, -1, 0))   # the elbow's origin and direction: +angle lifts the arm


@model
def hinge():
    base = bd.Box(100, 60, 20, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    arm = bd.Pos(40, 0, 20) * bd.Box(120, 20, 10, align=(bd.Align.MIN, bd.Align.CENTER, bd.Align.MIN))
    base.label, arm.label = "base", "arm"
    elbow = bd.Axis(*ELBOW)
    bd.RevoluteJoint("elbow", base, axis=elbow, angular_range=(-10, 120))
    bd.RigidJoint("elbow", arm, bd.Plane(origin=elbow.position, z_dir=elbow.direction).location)
    base.joints["elbow"].connect_to(arm.joints["elbow"], angle=30)   # as built: elbow 30
    assembly = bd.Compound(children=[base, arm], label="hinge")
    mechanism_state(assembly, "closed", elbow=0)
    mechanism_state(assembly, "open", elbow=90)
    return configuration_sequence(assembly, "cycle", [(0, "closed"), (2, "open"), (5, "closed")])


if __name__ == "__main__":
    hinge()
```

- **`connect_to` on the joint that stays**:
  `parent.joints[name].connect_to(child.joints[name], angle=..., position=..., angles=...)`
  moves the child's part. Connect parts before putting them in the compound that holds
  them.
- **Values are degrees and millimetres.** A joint's `angular_range` or `linear_range` is
  its limits; a pose or a mechanism state outside them is refused.
- **A pair is named by its moving joint's label** (`elbow`). A label two pairs share
  takes the path of the part that holds it (`hand/left:knuckle`).
- **Links are parts that move as one**: parts whose rigid joints are connected are one
  link, and a part below a jointed sub-assembly moves with it. The ground is every link
  no `connect_to` moved, and every part no joint places.
- **A nested assembly is paired by label.** build123d's `connect_to` cannot place a part
  inside a nested assembly: put each part where it stands, write the two joints there
  with one label, and the engine pairs the moving joint with the `RigidJoint` of the same
  label nearest it in the tree. Two rigid joints of one label fasten their parts.
- **The document keeps what STEP AP242 can say, and nothing else.** A pair the built
  parts contradict (its part moved after `connect_to`, connected after its compound was
  made, a rigid joint off the joint's axis, or two parts rigid joints make one body)
  fails the run by name: fix where the part stands. Pairs closing a loop are kept and not
  posed. A mechanism state, configuration sequence or coupling naming a joint the
  assembly does not hold fails the run, as does a coupling driving a joint its pair does
  not relate.
- **No helper joints.** A joint exists because the mechanism moves there. A prismatic
  joint per part only to slide it out for an explode is an animation's job
  ([animation](animation.md)), and the viewer's Position would show a slider for each.

## Mechanism states

`mechanism_state(assembly, name, **values)` names a pose by joint label, the joints it
leaves out as built, and returns the assembly. A cylindrical joint takes
`(angle, distance)` and a ball joint its three angles; a coupling takes its value
(`curl=0.5`). Mechanism states are what the viewer's Position lists as presets, and what
a snapshot's `--pose` names.

A file of the mechanism in another pose is a model of its own: `posed(assembly, state)`
returns a copy of the assembly with every part where the named state, or a mapping of
joint label to value, puts it. The copy keeps its joints, couplings, states and
sequences, with the asked values as its as-built state, so its page's Position and
motions still work. An unknown state or joint is refused by name.

```python
# src/hinge_poses.py
from cadgen import model
from cadgen.ap242 import posed

from hinge import hinge


@model
def hinge_open():
    return posed(hinge().shape, "open")


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
| `rack_and_pinion_pair(assembly, name, **joints)` | the first a revolute (pinion) or prismatic (rack) joint, every other of the other kind | a ratio: degrees or millimetres per unit |
| `screw_pair(assembly, name, joint=pitch)` | one cylindrical joint | its pitch: millimetres of travel per 360 degrees of turn; the coupling's value is the turn |

At value `c` each joint stands at its as-built value plus its ratio times `c`, so
`c = 0` is as built. Its range is its joints' limits: the tightest interval of `c` in
which every joint stays within its own (a joint with no limits bounds nothing), so give
the joints the limits the mechanism has. A joint takes at most one coupling, and a ball
joint none. Two joints of other kinds (two slides, a slide and a cylindrical joint's
turn) have no pair: drive them by a configuration sequence.

```python
# src/index_finger.py
import build123d as bd
from cadgen import model
from cadgen.ap242 import configuration_sequence, gear_pair

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
        bd.RevoluteJoint(joint, parent, axis=knuckle, angular_range=(0, CURL[joint]))
        bd.RigidJoint(joint, child, bd.Plane(origin=knuckle.position, z_dir=knuckle.direction).location)
        parent.joints[joint].connect_to(child.joints[joint], angle=0)   # as built: straight
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
cadgen snapshot "$ID" tmp/open.png --pose open
cadgen snapshot "$ID" tmp/elbow_45.png --pose '{"elbow": 45}'
```

`--pose` takes a mechanism state's name, or joint and coupling values as JSON (the rest
as built): it says how the picture is drawn. An unknown state, joint or coupling, a
value out of range and a coupling's joint set alone are refused by name before anything
renders.

On the model's page, Position poses the document live: a slider per coupling and per
joint no coupling moves, and the mechanism states as presets. The Motion tool plays the
document's configuration sequences (play, pause, scrub, loop, speed), so the page is
where to review one.

A pose or a motion shows movement; it does not measure it. A check of the model measures
the parts as built, so a part that clears there can still pass through another
mid-motion. Measure a pose by checking its posed model:

```python
from cadgen.geometry import overlap_volume

from hinge_poses import hinge_open

posed = hinge_open().shape
parts = {part.label: part for part in posed.leaves}
print(overlap_volume(parts["arm"].solids()[0], parts["base"].solids()[0]))   # 0: the open arm clears the base
```
