# A robot from its vendor STEP

A vendor's STEP of a robot holds parts and their placements, but no mechanism. Exported as it is
(`cad step export vendor/arm.step sim/arm.xml`), each of its top-level parts is a body welded to
the world. To get a robot that moves, write a model that reads the STEP, groups its parts into
links, puts a joint at each hinge, and declares the hardware's facts: masses, stops and drive
limits. Then export it as MJCF and URDF, and write its MuJoCo function: the collision shapes, joint
dynamics and actuators a simulation chooses. The steps below go in order, and each names the reference with the detail. The times given
are ranges on a laptop: they grow with the parts' surface area and detail (a few large freeform
shells cost more than hundreds of small printed parts) and shrink on a faster machine.

Vendor STEPs come in two kinds, and steps 2, 4 and 8 say what each needs:

- **An assembly with its internals**: printed or machined parts, servos or motors with their horns,
  fasteners, boards and cables, often hundreds of parts. A hobby or desktop arm usually comes so.
- **One plain solid per link**: a simplified ("dummy") envelope of each link, or an industrial arm's
  outer shells, with no motors, gearboxes or fasteners inside. A link may be a few solids (a shell
  and a cap). Such solids are often modelled filled, and neighbours are often drawn a little into
  each other.

## 1. Read it

Convert the STEP once (quote a path with spaces in it), and read the xbf in the model's body:

```bash
cad step export vendor/arm.step vendor/arm.xbf
cad step inspect vendor/arm.step --query structure
cad step snapshot vendor/arm.step tmp/as-drawn.png --camera right
```

The conversion takes seconds. `xbf.read(HERE / "../vendor/arm.xbf")` then hands the model a tree,
and `leaves(tree, paths=True)` gives each part placed where it stands, with its path of labels
(the `cad` skill's inspection reference, Opening geometry).
`path[1]` is the top-level component (`Forearm v4:1`, `Servo v2:3`). `inspect --query structure`
counts the parts; use a throwaway `cad run` script to print each leaf's path, volume, face count
and bounds once: it maps the STEP faster than reading the inspect output does. Look at the pose the
vendor drew, too: it may be the controller's zero, or only a pose to ship it in (step 6).

**Which way is up.** Many CAD tools draw Y up, and a STEP from one lies on its side in a Z-up
simulator. No export option turns a robot over: place it in the model. Re-place every leaf with one
rigid placement as you take it, a rotation that takes the vendor's up to +Z and a translation that
puts the base's mounting face on z = 0 and its first axis on the Z axis:

```python
TO_WORLD = bd.Pos(0, 0, BASE_LIFT) * bd.Location((0, 0, 0), (90, 0, 0))   # vendor +Y up to +Z
for path, part in leaves(xbf.read(STEP_XBF), paths=True):
    part = TO_WORLD * part        # keeps its label, colour and material
```

Where the vendor's axes are not one turn from the world's (X the robot's left, Y up, Z forward,
say), build the rotation from where two of its axes go: `bd.Plane`'s `x_dir` is where the vendor's
X goes, its `z_dir` where the vendor's Z goes, and their cross product, Z x X, is where the
vendor's Y goes. Check that it is the up you mean; a pair that would need a mirror cannot be built,
and a Plane is always a rotation:

```python
# vendor X (the robot's left) to world +Y, vendor Z (forward) to world +X: vendor Y (up) lands on +Z
TO_WORLD = bd.Pos(0, 0, LIFT) * bd.Location(bd.Plane(origin=(0, 0, 0), x_dir=(0, 1, 0), z_dir=(1, 0, 0)))
point = (TO_WORLD * bd.Location(vendor_point)).position   # a point: a Location times a Vector is refused
```

One rigid placement for every part keeps each part where it stands on its hinges, so measure the
axes (step 3) on the re-placed parts, or move each measured axis by the same placement. A snapshot
of the re-placed parts shows the base on the ground.

## 2. Group the parts into links

This step is the one human decision. Every part goes into exactly one link, and a joint sits
between two links. In a STEP of one plain solid per link, each solid (or the few solids of one
link) is a row of the table below, in chain order from the base; there is nothing more to sort, and
the rules here are for an assembly with its internals:

- **Printed or machined parts by function.** A bracket that carries a servo and the arm segment
  that servo turns are two links.
- **A servo's case goes with the link it is screwed to.** Its horns (the drive horn on the output
  shaft and the idle horn opposite it, where it has one) go with the link they turn. A motor or a
  servo drawn as one solid, its case and its output (flange, horn) together, cannot be split by
  parts: the whole solid goes with the link its case is screwed to, and the next link's plate,
  bolted to its output face, goes with the next link. Where the output is bolted to the parent's
  bracket (a servo mounted the other way round), the case is the child's. `ranges` reads such a
  pair as an output and what turns on it (step 5), so the sweep needs no split. Vendors label
  parts in their own language, so a horn's label may not say which it is; the geometry does. The
  drive horn is splined onto the shaft, so it has many more cylindrical faces than the idle horn,
  which turns on a plain bore: count `part.faces().filter_by(bd.GeomType.CYLINDER)` on each and
  take the larger count as the drive horn.
- **Cables, boards and connectors go with the link they are clipped to.**
- **Fasteners go with the part they hold.** Use the nearest part, found by bounding boxes first. A
  solid-to-solid `closest_points` on printed parts of thousands of faces runs for minutes per
  hundred pairs, so measure from the fastener's centre (`bd.Vertex`) to the few candidates the
  boxes leave. Two cases override the nearest part. A fastener on a joint's axis (its centre within
  a millimetre of it) is the horn's centre screw: it threads into the parent's output shaft but
  turns with the child, so it goes with the child. A fastener through two parts goes with the link
  of the two it clamps together, even where a part of another link is nearer to its centre (a horn
  beside the screw that holds a bracket to its servo). At a joint the screws that clamp a plate to an
  output have boxes inside parts of both links, so the nearest part is ambiguous there: they go with
  the plate's link, and the screws that hold the case with the case's.
- **A vendor's own sub-assemblies.** Where the STEP holds a sub-assembly per link (`LINK-2_ASM`,
  `Forearm_ASM`), take each as a link, and its membership for the fasteners too: a vendor puts the
  screws that hold a plate to an output in the plate's sub-assembly and those that hold a case in
  the case's. Check its boundary at each joint (the motor's case in one, the plate on its output in
  the next) and place any loose top-level part by the rules above.
- **A branched or free-floating robot** (a humanoid, a legged robot) is a base with a chain per limb.
  The base is the torso or pelvis: declare `free()` on the top assembly (its frame then stands at the
  base link's centre of mass), and put the soles, not a mounting face, on z = 0. One component (a
  servo, a bracket) repeats in every limb and several times along one, so a table of component name
  to link cannot place it: key the table by component and position, the leaf's centre in bands along
  the limb (its height down a leg, its distance out along an arm) and its side (the sign of its
  coordinate across the body), and raise on a leaf that falls in no band. Left and right limbs are
  mirror images, so one joint's measured axis points the other way on the other side: give each side
  the sign that makes a positive angle the motion you mean (step 6 for the controller's).

Write the grouping as a table of component name to link (by name and position where names repeat
across links, above), and raise on any component the table does not name, so that a new revision of the STEP fails loudly instead of dropping a part. A vendor often
labels its bodies `SOLID` or `Body1`. `ranges` names such a part by its component
(`Forearm v4/SOLID`), but `inspect` and the exported files show the label, so relabel each one as
you take it: `if part.label in ("SOLID", "Body1"): part.label = path[-2]`. A vendor's STEP can also
hold empty bodies, leaves with no volume (a placeholder for a part the vendor never drew). Drop them
as you take the leaves (`if part.volume <= 0: continue`): kept, they weigh nothing (a declared mass
over them goes to the parts with volume, and one declared on them alone is refused: no volume to
carry it), and they are only clutter in the links. Put each link in a
`bd.Compound(children=..., label=...)` and name it for ROS with `link()`. A posed snapshot (step 6)
shows every link moving as one piece. A part left behind or swinging with the wrong link was sorted
wrong.

## 3. Find each joint axis from the geometry

A hinge's axis is a circle in the parts: a servo horn, a bearing bore, a shaft, a flange. Look
for it on both sides of the hinge, the parent's and the child's, where the two agree. build123d gives
each in world coordinates, from two sources:

```python
import build123d as bd


def cylinders(part):
    """(point, direction, radius) of each cylindrical face. build123d's face.radius is None on a
    trimmed cylinder (common in vendor STEPs), so measure it from a point of the face."""
    for face in part.faces().filter_by(bd.GeomType.CYLINDER):
        axis = face.axis_of_rotation
        offset = face.position_at(0.5, 0.5) - axis.position
        radius = (offset - axis.direction * offset.dot(axis.direction)).length
        yield axis.position, axis.direction, radius


def circles(part):
    """(centre, normal, radius) of each circular edge: a bore's rim, a flange's edge."""
    for edge in part.edges().filter_by(bd.GeomType.CIRCLE):
        yield edge.arc_center, edge.normal(), edge.radius
```

Cylindrical faces come first: a horn, a bore. Smooth covers and freeform shells often have none
that match across a hinge (one side of the joint is a freeform surface), but their rims still do:
circular edges of the parent and the child with one normal and coaxial centres are the hinge's axis,
at the point where they lie. Group each side's circles by axis (direction within a hundredth of a
degree, the axis line within a few hundredths of a millimetre), and keep the axes the two sides share
to within about a millimetre (the two halves of a hinge can disagree by tenths: below).
A servo's two horns are coaxial, so check that their axes agree before you trust either one.
Measure the axes once in a script and write them in the model as `(point, direction)` constants.
Then:

- **Keep the measured axis; snap only noise.** A component within `1e-9` of 0 is 0 (the `cad`
  skill's kinematics reference). A tilt of a fraction of a degree comes from the vendor's mates, and
  the parts are drawn on it: keep it. Square an axis only if you also place the parts square on it.
  A part that turns about a squared axis while it stays where the STEP drew it wobbles a tenth of a
  millimetre or more against neighbours it clears by less than a millimetre, and `ranges` then finds
  stops that are not there (a jaw that stops far short of closing).
- **Where the two sides disagree, use the child's bore.** A vendor's parts can be drawn a few
  tenths of a millimetre off each other's axis (the parent's bore here, the child's a little there).
  Put the joint on the child's own bore, the axis the child is drawn around: it then turns in
  place, and the parent, which does not move, keeps its offset. On the parent's axis the child
  would swing on a small circle and rub against neighbours it clears by less than that. Write the
  offset in a comment beside the axis.
- **Pick each direction's sign** so that a positive angle is the motion you mean (lift raises, the
  jaw opens), or the controller's sign where it is known (step 6). The writers copy the sign and
  cannot know which way is meant.
- **Build each joint at the hinge's own frame.** Put the `RevoluteJoint` on the parent link (its
  Compound, or the part that carries the bearing), `bd.RevoluteJoint(name, parent_link,
  axis=bd.Axis(point, direction), angular_range=...)`. Put `bd.RigidJoint(name, child_link, hinge.location)` on the child link, then
  call `hinge.connect_to(child_link.joints[name], angle=0)`. The child stays where it was drawn.

## 4. Mass

Vendor materials are often wrong for weighing: cables marked steel, printed parts modelled solid,
shells modelled filled. A material you set replaces the part's colour (the faces the vendor painted
keep theirs); set `part.color` back after it to keep the vendor's. A STEP with no colours at all
(`part.color` is None on every part) takes the material's colour everywhere, since there is none to
keep: give the parts a neutral one after the material instead (`part.color = bd.Color(0.75, 0.75,
0.75)`), or the vendor's from its pictures. Weigh each part as the hardware is, and count each part
once: what a listing weighs, your declarations together weigh.

**One plain solid per link.** The datasheet's weight of the arm is usually all there is: one
material on every solid and `mass(arm, TOTAL_G)` split it by volume, which puts each link's centre
of mass too far from its joints, where the hardware's motors are. `point_mass()` for each joint's
actuator, listed or estimated, at its axis on the link that holds it, moves the mass back where it
is; the total stays the datasheet's ([inertials](inertials.md#a-link-drawn-as-one-plain-solid) has
the code). Say in the model's docstring which masses are listed and which estimated.

**An assembly with its internals:**

- **Printed parts:** a material (`plastics.pla()`), then `mass(part, grams)` estimated from the print
  settings ([inertials](inertials.md#a-printed-part)).
- **Servos and motors:** the datasheet's weight is the servo as sold. Check what that includes: a
  hobby or smart servo's listing usually weighs it with one horn fitted, sometimes with its whole
  bag of horns and screws, sometimes bare. Check the listing; don't count a part twice. Where the
  CAD leaves the motor out, `point_mass()` adds it. When the STEP draws as solids of their own horns
  that the listing includes, they are inside its weight, and the horns turn with the child link while
  the case stays on the parent (step 2), so one `mass()` cannot hold both.
  Split the listing between them: give each horn its share (a spare horn's listed weight, or its
  volume at its metal's density), and the servo's sub-assembly (the `bd.Compound` of its case and
  internals) the rest. Together they weigh what the listing says, so the horns add nothing:

  ```python
  SERVO_G = 60.0   # the listing: the servo as sold, both horns fitted
  HORN_G = 3.0     # one horn: the vendor's spare, listed apart (or its volume at its metal's density)
  for horn in (drive_horn, idle_horn):
      mass(horn, HORN_G)                   # in the child link, which it turns
  mass(servo_case, SERVO_G - 2 * HORN_G)   # case, motor, gears and board: the rest of the listing
  ```

  Subtract only the horns the listing includes. A horn it leaves out (bought apart) adds its own
  weight on top.
- **Boards and cables:** a weighed figure, or an assumed one written in a comment beside it.

`cad model inspect "$ID"` weighs the result. Read its total against the hardware's: the listed
servos, the printed parts and the rest, each once.

## 5. Stops and drive limits

```bash
cad run src/arm.py
cad model ranges "$ID"
```

At its defaults (0.3 mm clearance, 1 degree steps), `ranges` takes tens of seconds for an arm of a
few hundred small parts and six joints, and minutes for one of a few large freeform shells: its time
follows the parts' surface area and detail, not their count. A long sweep says each joint on stderr
as it starts. The defaults stop each joint
where its parts all but touch: write those stops. A larger `--clearance` only narrows a range (at
1 mm a jaw can stop well short of closing), so keep the default. To ask again about one joint after
a change, sweep it alone: `cad model ranges "$ID" --joint jaw`.

Each stop names the two parts that met one step past it, and they should be parts of neighbouring
links. One that names a part of a link that is not a neighbour means a part is in the wrong link.
A stop at 0 means the same, unless the vendor drew the arm at that stop: an arm drawn folded flat
(a forearm resting on its upper arm) has a real stop at 0, which a posed snapshot a few degrees
the other way confirms. Vendor parts often sit a fraction of a millimetre apart (a moving jaw beside
the cover of the servo that drives it): such a pair stops a joint only where its contact grows on a
surface that stops the motion, where one part is pushed into the other (a part resting face to face
on its parent and turned into it stops where it lies), or where its gap closes to half; a pin in its
bore or a carriage on its rail stops nothing. The stop says so (`touching as built`). Check such a
stop with a posed snapshot at it.

A motor or a servo drawn as one solid, its case and output together, with the next link bolted to
that output: the sweep reads the pair as an output and what turns on it, and lists it under the
joint (`turns on: plate (link2) on motor (link1)`). Neither the output's face nor what of the solid
lies within the reach of their contact about the axis (a locating boss, a pin, a bolt's seat
through the face) stops the joint, so it sweeps on to its real stop. The case beyond that reach
still stops it, as it does the hardware. Where a stop a few degrees out still names such a pair
`touching as built`, the output carries something past that reach which the hardware turns with it:
split the output from the case in the model, or write the range you read from the hardware.

**A clash and a stop.** A stop is where the child meets its parent, whatever the other joints do;
a clash, said beside it, is what the joint moves meeting another link in the drawn pose of the
others (a wrist resting on the shoulder of an arm drawn folded, a thigh meeting the torso while the
hip's other joints stand as drawn). Write the stop, not the clash: the clash moves with the other
joints, and the simulator's contacts hold it, since those links collide. A stop past a half turn
(-239 degrees) is the parts' own, within the full turn swept each way; where the actuator's own
travel is narrower (a servo's position range), write that.

Simplified parts are often drawn sunk into each other: a link a little too wide for its clevis, a
forearm resting a millimetre into the upper arm it folds onto, a gripper's carriage drawn inside its
rail. `ranges` finds these and lists them under the joint (`overlapping as drawn ... by 180 mm^3,
1.0 mm deep`). Such a pair stops the joint only where one part is pushed deeper into the other than
drawn, by 0.6 mm more: its overlap shrinking, or sliding along with the joint, stops nothing, so the
sweep goes on to the real stop. A stop such a pair makes says `deeper than drawn (overlapping ...,
1.0 mm deep, as built)`, and lies past the true one by up to about that depth: read it against a
posed snapshot and the datasheet, and write the narrower.

Where a stop is not the hardware's (the jaws still wide apart when the jaw meets the cover of the
servo beside it), the sweep cannot tell: check it with a posed snapshot at the stop, and write the
range you read from the hardware (the datasheet's travel, or the posed snapshot where the parts
really meet) instead. A servo's case is often several shells (a middle and two covers), and the
part that clears one sweeps into the next, so look at the whole case at the stop. The simulator
collides those parts as the MuJoCo function chooses (step 8), which is where a pair the hardware
never brings together is set aside.

Write the stops into `angular_range`, rounded towards zero. A joint found clear all the way round
has no stop in the parts: give it the actuator's own travel, or make it continuous
([Generate from CAD](../SKILL.md#generate-from-cad)).

Then declare `limits(arm, joint, effort=, velocity=)` from the actuator's datasheet: the stall
torque in N*m, and the no-load speed in rad/s at the supply voltage you use. Give both: a URDF
requires the two, writes 0 for one left out, and a ROS controller reads that 0 as no speed (or no
torque) allowed; the export names each joint it wrote so. Where the datasheet has no speed (a
gripper's often has none), give the drive's from its maker, or measure it. The joint's armature,
damping and dry friction are the simulation's, in step 8.

## 6. Zero and states

A joint's zero is a fact of the hardware: its controller counts from one pose. Make the
description's zero that pose, so that a joint value means the same in the simulator, in a driver
and in the vendor's datasheet. The CAD's pose is every joint's zero unless you export with
`--zero <state>`.

**Is the drawn pose the controller's zero?** Vendors often draw a robot at its zero, and their
published joint ranges tell. Sweep the stops first (step 5), then lay each published range over the
stops found around the drawn pose:

- A range that is one-sided or lopsided around 0 (0 to 150, -10 to 200) puts the zero at or near
  one end of the travel. A drawn pose folded against a stop, with ranges that start at 0, is that
  pose.
- Where the drawn pose is the zero, every published range fits inside the swept stops, each end a
  little inside the stop on its side (a controller stops short of the parts). Try each joint's two
  signs: usually only one puts the range inside the stops, and that is the controller's sign.
- Where neither sign fits (the range runs through a stop either way), the drawn pose is not that
  joint's zero.
- Mirrored limbs: a vendor's controller often counts the left and right joints mirrored (both
  knees bend at positive angles) or the same way about one axis (one knee positive, the other
  negative). Its published ranges say which: a lopsided range that fits one side's stops with one
  sign fits the other side's with the opposite sign where it is mirrored.

Where the ranges fit, keep the drawn pose as the zero and say so in the model's docstring, with the
evidence (each range against its stops). The limits you write are then the datasheet's numbers.
Re-zero only when you know the controller's zero is another pose, from the vendor's own description
(a URDF, a driver's calibration) or its manual: compute that pose as a state from the measured axes
(below), name the drawn pose `drawn` with every joint at 0, and export with `--zero <state>`. Each
joint then counts from that state, and `drawn` becomes a key.

**What stays undetermined.** A roll joint clear all the way round has no stop to fit a range
against, and a symmetric range (±360) says nothing either: neither its zero nor its sign can be told
from the geometry or the datasheet. The same holds for a joint whose range and stops are both
symmetric. Keep the drawn pose's 0 and a stated convention for the sign (positive turns
counter-clockwise looking out along the link), and write in the docstring that both are unchecked,
so that whoever connects the controller checks them.

**`home` and other states.** `home` is the pose the hardware starts from: the zero itself where the
controller parks there. A working pose (the upper arm up, the forearm forward) is another state,
`ready`. Compute a state's angles from the measured axes rather than by eye. A link runs from its
joint's axis to the next joint's (the last along the roll axis), and each joint turns every link
after it, so take them in order. A state must lie within every joint's range: an angle outside it
may be the same pose a full turn round, and where no turn brings it inside, the pose is out of this
robot's reach (an elbow that stops short of straight cannot stand the arm upright): choose another
pose. For an arm whose joints are `base_yaw`, `shoulder`, `elbow`, `wrist`, `tool_roll` and `jaw`,
standing each pitch link straight up:

```python
UP = bd.Vector(0, 0, 1)
PITCH = ["shoulder", "elbow", "wrist"]
point = {name: bd.Vector(*AXES[name][0]) for name in AXES}       # AXES: (point, direction) measured
along = {"shoulder": point["elbow"] - point["shoulder"],
         "elbow": point["wrist"] - point["elbow"],
         "wrist": bd.Vector(*AXES["tool_roll"][1])}


def turn(v, target, axis):
    """Degrees about axis that turn v onto target's direction, -180 to 180."""
    n = axis.normalized()
    v, target = v - n * v.dot(n), target - n * target.dot(n)
    return math.degrees(math.atan2(n.dot(v.cross(target)), v.dot(target)))


upright = {"base_yaw": 0, "tool_roll": 0, "jaw": RANGES["jaw"][0]}
for at, joint in enumerate(PITCH):
    axis = bd.Vector(*AXES[joint][1])
    angle = turn(along[joint], UP, axis)
    lo, hi = RANGES[joint]
    within = [a for a in (angle, angle - 360, angle + 360) if lo <= a <= hi]
    if not within:
        raise ValueError(f"{joint} at {angle:.0f} deg is outside its range {lo} to {hi}: out of reach")
    upright[joint] = within[0]
    for later in PITCH[at + 1:]:   # this joint carries every link after it
        along[later] = along[later].rotate(bd.Axis((0, 0, 0), axis), upright[joint])
mechanism_state(arm, "upright", **upright)
```

Check the signs on the model before exporting:

```bash
cad model snapshot "$ID" tmp/upright.png --pose upright --camera right
cad model snapshot "$ID" tmp/lift.png --pose '{"shoulder": 30}' --camera right
```

## 7. Export, validate, compare

```bash
cad model export "$ID" sim/arm.xml          # --zero <state> only where step 6 re-zeroed
cad model export "$ID" description/arm.urdf
cad mujoco check sim/scene.xml
cad urdf validate description/arm.urdf
cad urdf snapshot description/arm.urdf tmp/urdf.png --pose '{"shoulder": 30}' --camera right
```

`--pose` is in degrees, as for the model, though the files hold radians.

Read each export's summary first: the links, the joints, the mass, the collisions. Both files come
from one model, so the two summaries must name the same links and joints and the same mass, and
`cad mujoco check` must count the same bodies and joints. Then compare the URDF snapshot with the
model's snapshot of step 6 at the same pose and camera: the robot must stand the same way and each
joint must turn the same way. A difference is a bug in a writer, whatever the checks say. Report it,
and do not ship around it. No `cad` command draws an MJCF; the person sees it in Studio (step 9).

## 8. The MuJoCo function

The model carries the hardware. What a simulation chooses for it goes in a MuJoCo function in a
script beside the model: each part's collision shape, each driven joint's armature and damping, and
a position actuator on every driven joint. It saves the robot's file where the plain export went,
with its meshes in `assets/` beside it. [MuJoCo environment](mujoco-environment.md#the-mujoco-function)
has each helper, what `save` does and MuJoCo 4.0.0's traps; read it before writing one.

Name each part by its label path as `cad model inspect "$ID"` prints it (`base_link/screw`,
`shoulder_servo/case`): a last segment is enough where it names one part, and a name that is
ambiguous or names no part is refused with the parts there. Several parts of one label in one link
(its screws) share one path, and `collisions` returns them all. A maker's assembly has a hundred
parts or more, most of them fasteners: `parts(s)` lists every path, so choose by a rule over it
(`for path in parts(s): ...`, deleting the collisions of every part that is not a printed part or a
case) rather than naming each screw.

**Collisions.** Every part collides as its own mesh (its convex hull) until the function chooses
otherwise.

- **One plain solid per link:** `decompose()` a concave link (a yoke, a clevis, a gripper's palm with
  its slot), keep the default hull on a convex one (a base, a roll link), and delete the collisions
  of a part that runs inside another (a sliding bar inside its guide).
- **Printed parts:** `decompose()`, so that the pocket a servo sits in stays a pocket. The first
  run decomposes each part, from a few seconds to about a minute each by its size and detail
  (minutes for a dozen parts), and says each on stderr as it is done. The hulls are cached by each
  part's mesh and options, and only a changed part decomposes again.
- **Servo cases:** `fit(s, part, "box")` on each shell of the case (the body and its covers), and
  delete the collisions of the motor, gears and board inside.
- **Fasteners, horns clamped inside a bracket, cables and boards:** delete their collisions.

**Joint dynamics and actuators.** Each driven joint takes its armature (the rotor's inertia through
its gearbox: the datasheet's where it gives one, else an estimate, [tuning](mujoco-environment.md#tuning)
says how) and a light damping, then a position actuator. The force is already bounded: `limits(effort=)`
in the model wrote each joint's `actuatorfrcrange`. A coupled follower takes no actuator: its
equality drives it.

```python
# src/arm_mujoco.py: the simulator's choices. Run it: cad run src/arm_mujoco.py
import mujoco
from cad.mujoco import collisions, decompose, fit, save, spec

from arm import arm

PRINTED = ["upper_arm", "jaw"]                 # concave printed parts: their pockets stay pockets
CASES = ["shoulder_servo/case"]                # each shell of each servo's case
NONE = ["base_link/screw", "upper_link/screw"]   # fasteners, a case's internals, cables, boards
DRIVEN = ["shoulder", "jaw"]                   # every joint an actuator drives (no coupled follower)
ARMATURE = 0.00625   # kg*m^2: 1e-7 x 250^2, tuned, not measured (the listing gives the ratio, not the rotor)


def arm_mujoco() -> mujoco.MjSpec:
    s = spec(arm())

    for part in PRINTED:
        decompose(s, part)
    for part in CASES:
        fit(s, part, "box")
    for part in NONE:
        for geom in collisions(s, part):
            s.delete(geom)

    for name in DRIVEN:
        joint = s.joint(name)
        joint.armature = ARMATURE
        joint.damping = [0.1, 0, 0]          # N*m*s/rad: light, to steady the integrator
        servo = s.add_actuator(name=name, target=name, trntype=mujoco.mjtTrn.mjTRN_JOINT)
        servo.set_to_position(kp=10, dampratio=1, inheritrange=True)   # a start for tuning
    return s


if __name__ == "__main__":
    save(arm_mujoco(), "sim/arm.xml")
```

```bash
cad run src/arm_mujoco.py
cad mujoco check sim/scene.xml
```

The run prints what `save` checked: each warning, then a `collisions:` line (the collision geoms by
kind and by body, and the moving bodies that collide as nothing) and an `excludes:` line (each
contact exclude and how its two bodies stand at rest). Read both against the lists above: every
case a `box`, every printed part its hulls, nothing left on a link whose parts were all deleted by
mistake, and no exclude between two bodies now apart that nobody meant (`s.delete(exclude)`).
`cad mujoco check sim/arm.xml --json` has every geom's name, kind and size.

Where step 6 re-zeroed, the spec counts from the same state: `spec(arm(), zero="<state>")`, as the
export's `--zero` does. `inheritrange=True` takes each control range from the joint's range. A joint with no range (a
continuous roll) is refused it when the spec compiles: give its actuator `set_to_position(kp=10,
dampratio=1)` and `servo.ctrlrange = [-3.1416, 3.1416]` instead. `kp` and `dampratio` are a starting
point for [tuning](mujoco-environment.md#tuning), not a datasheet value.

**Look at the hulls.** A part that reaches its cap of hulls (16 by default) says so as it is done:
`decomposed bracket: 16 hulls, the cap (max_hulls=16) in 8.1 s`. At the cap, CoACD merged hulls to
fit, so some of them bridge a concave region. Whether that matters depends on what touches it: find
out before you change anything. Move the joint whose parts enter the concave region through its
range and ask MuJoCo what touches, from a throwaway script (`cad run tmp/touch.py`):

```python
import mujoco

m = mujoco.MjModel.from_xml_path("sim/arm.xml")
d = mujoco.MjData(m)
joint = m.joint("jaw")
for value in (joint.range[0], sum(joint.range) / 2, joint.range[1]):
    d.qpos[:] = m.qpos0
    d.qpos[joint.qposadr[0]] = value
    mujoco.mj_forward(m, d)
    print(round(float(value), 3), [(m.geom(c.geom1).name, m.geom(c.geom2).name) for c in d.contact[:d.ncon]])
```

A contact between two hulls at a pose where the parts clear each other in the CAD (`cad model
snapshot` at the same pose) is a hull bridging the gap. A pair of bodies the file excludes makes no
contact at all, so read the `excludes` line first. The person can see the hulls themselves in
Studio (step 9).

A hull that fills a pocket a neighbour moves into, a slot, or the gap between jaws is contact the
simulator makes and the hardware does not: raise that part's cap (`decompose(s, part,
max_hulls=32)`) or lower its `threshold=`, and run the function again. A hull that only rounds over
an inside corner nothing reaches does not matter, and a part whose shape never matters for contact
can take fewer (`max_hulls=8`).

Expect hulls to stand proud of the part. Their corners lie on the part's surface, but their faces
bridge its concave places, by a few millimetres on a link a few hundred millimetres long, and a
lower `threshold` or more hulls hardly changes that: the deepest bridge stays, and a fine threshold
costs tens of times longer. So two links that clear each other by less than that beside a concave
place (a wrist parked against the upper arm in the drawn pose) overlap at rest as hulls, and
`cad mujoco check` says `contacts_at_rest`, naming the two hulls. Where those links never meet in
the hardware's working range, exclude the pair in the function, by the links' body names
(`s.add_exclude(bodyname1="wrist_link", bodyname2="upper_arm_link")`), with a comment saying the
simulator lets them pass through each other: MuJoCo excludes bodies whole, not single geoms. Where
they must still collide, no hull setting clears them: try a fitted shape on the convex one of the
pair (`"cylinder"`, `"capsule"`), and check again until the warning is gone.

## 9. Studio

Check that the robot holds its pose under gravity, from a throwaway script (`cad run tmp/hold.py`):

```python
import mujoco

m = mujoco.MjModel.from_xml_path("sim/scene.xml")
d = mujoco.MjData(m)
mujoco.mj_resetDataKeyframe(m, d, m.key("home").id)
for _ in range(1000):   # 2 s at the default 2 ms step
    mujoco.mj_step(m, d)
print(d.qpos)
```

Each joint should end within a few hundredths of a radian of `home`. A joint that sags is a gain,
an armature or a force bound to look at ([tuning](mujoco-environment.md#tuning)); one that rings or
explodes is a model-health warning to clear first. Then open it for the person:

```bash
cad run mujoco-studio --model sim/scene.xml
```
