# A robot from its vendor STEP

A vendor's STEP of a robot holds parts and their placements, but no mechanism. Exported as it is
(`cad step export vendor/arm.step sim/arm.xml`), each of its top-level parts is a body welded to
the world. To get a robot that moves, write a model that reads the STEP, groups its parts into
links, puts a joint at each hinge, and declares what a simulator needs. Then export it as MJCF and
URDF. The steps below go in order, and each names the reference with the detail. The times given
are ranges on a laptop: they grow with the parts' surface area and detail (a few large freeform
shells cost more than hundreds of small printed parts) and shrink on a faster machine.

Vendor STEPs come in two kinds, and steps 2 to 5 say what each needs:

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
vendor drew, too: it may be the controller's zero, or only a pose to ship it in (step 7).

**Which way is up.** Many CAD tools draw Y up, and a STEP from one lies on its side in a Z-up
simulator. No export option turns a robot over: place it in the model. Re-place every leaf with one
rigid placement as you take it, a rotation that takes the vendor's up to +Z and a translation that
puts the base's mounting face on z = 0 and its first axis on the Z axis:

```python
TO_WORLD = bd.Pos(0, 0, BASE_LIFT) * bd.Location((0, 0, 0), (90, 0, 0))   # vendor +Y up to +Z
for path, part in leaves(xbf.read(STEP_XBF), paths=True):
    part = TO_WORLD * part        # keeps its label, colour and material
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
  shaft and the idle horn opposite it, where it has one) go with the link they turn. Vendors label
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
  beside the screw that holds a bracket to its servo).

Write the grouping as a table of component name to link, and raise on any component the table does
not name, so that a new revision of the STEP fails loudly instead of dropping a part. A vendor often
labels its bodies `SOLID` or `Body1`. `ranges` names such a part by its component
(`Forearm v4/SOLID`), but `inspect` and the exported files show the label, so relabel each one as
you take it: `if part.label in ("SOLID", "Body1"): part.label = path[-2]`. A vendor's STEP can also
hold empty bodies, leaves with no volume (a placeholder for a part the vendor never drew). Drop them
as you take the leaves (`if part.volume <= 0: continue`): kept, they weigh nothing (a declared mass
over them goes to the parts with volume, and one declared on them alone is refused: no volume to
carry it), and they are only clutter in the links. Put each link in a
`bd.Compound(children=..., label=...)` and name it for ROS with `link()`. A posed snapshot (step 7)
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
  jaw opens), or the controller's sign where it is known (step 7). The writers copy the sign and
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

## 5. Collisions

**One plain solid per link:** `collision(part, "decomposed")` on a concave link (a yoke, a clevis,
a gripper's palm with its slot), the default hull on a convex one (a base, a roll link), and `"none"`
on a part that runs inside another (a sliding bar inside its guide).

**An assembly with its internals:**

- **Printed parts:** `collision(part, "decomposed")`, so that the pocket a servo sits in stays a
  pocket. The first export decomposes each part, from a few seconds to about a minute each by its
  size and detail (minutes for a dozen parts), and says each part on stderr as it is done. The
  hulls are cached by each part's mesh and options, and only a changed part decomposes again.
- **Servo cases:** `"box"` on the case's shell leaves (the body and its covers) and `"none"` on the
  motor, gears and board inside. `collision()` on the servo's assembly applies to every leaf below
  it, so it would box the internals too.
- **Fasteners, horns clamped inside a bracket, cables and boards:** `"none"`.

Match labels by pattern while you loop over the leaves, as the `cad` skill's inspection reference
shows under Opening geometry.

A part that reaches its cap of hulls (16 by default) says so as it is done: `decomposed bracket: 16
hulls, the cap (max_hulls=16) in 8.1 s`. At the cap, CoACD merged hulls to fit, so some of them
bridge a concave region. Whether that matters depends on what touches it: look before you change
anything. Draw the collision geoms, each hull in its own colour, beside the visual snapshot at the
same pose and camera:

```bash
cad mjcf snapshot sim/scene.xml tmp/collision.png --display collision --pose home --camera right
cad mjcf snapshot sim/scene.xml tmp/visual.png --pose home --camera right
```

A hull that fills a pocket a neighbour moves into, a slot, or the gap between jaws is contact the
simulator makes and the hardware does not: raise that part's cap (`max_hulls=32`) or lower its
`threshold=`, and export again. A hull that only rounds over an inside corner nothing reaches does
not matter, and a part whose shape never matters for contact can take fewer (`max_hulls=8`).

Expect hulls to stand proud of the part. Their corners lie on the part's surface, but their faces
bridge its concave places, by a few millimetres on a link a few hundred millimetres long, and a
lower `threshold` or more hulls hardly changes that: the deepest bridge stays, and a fine threshold
costs tens of times longer. So two links that clear each other by less than that beside a concave
place (a wrist parked against the upper arm in the drawn pose) overlap at rest as hulls, and
`cad mjcf validate` says `contacts_at_rest`, naming the two hulls. Where those links never meet in
the hardware's working range, `exclude(a, b)` them, and say in the model that the simulator lets
them pass through each other. Where they must still collide, no hull setting clears them: try a
fitted shape on the convex one of the pair (`"cylinder"`, `"capsule"`), and validate again until the
warning is gone.

## 6. Stops and drive limits

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
the cover of the servo that drives it): such a pair stops a joint only where its contact grows or its
gap closes to half, and the stop says so (`touching as built`). Check such a stop with a posed
snapshot at it.

Simplified parts are often drawn sunk into each other: a link a little too wide for its clevis, a
forearm resting a millimetre into the upper arm it folds onto, a gripper's carriage drawn inside its
rail. `ranges` finds these and lists them under the joint (`overlapping as drawn ... by 180 mm^3,
1.0 mm deep`). Such a pair stops the joint only where one part is pushed deeper into the other than
drawn, by 0.6 mm more: its overlap shrinking, or sliding along with the joint, stops nothing, so the
sweep goes on to the real stop, and no `exclude()` is needed for it. A stop such a pair makes says
`deeper than drawn (overlapping ..., 1.0 mm deep, as built)`, and lies past the true one by up to
about that depth: read it against a posed snapshot and the datasheet, and write the narrower. Where it is not the hardware's stop (the jaws still wide apart when the jaw meets
the cover), set the pair aside in the model and sweep again: the two parts never stop the sweep,
every other pair of their links still does, and the jaw then stops on the other jaw. A servo's case
is often several shells (a middle and two covers), and the part that clears one sweeps into the
next, so set aside the whole case at once: name the servo's assembly, the `bd.Compound` you made of
its case and internals, or its label, and every part below it goes:

```python
exclude(jaw, "jaw_servo")   # the label of the jaw servo's assembly: each shell of its case alike
```

`exclude()` is one declaration with two effects, and there is no way to have one without the other:
`ranges` sets the two parts aside, and the MJCF writes a `<contact><exclude>` of their two links, so
the simulator never collides those links, whole (MuJoCo excludes bodies, not single geoms). That is
usually what you want. A pair that does not stop the hardware's joint should not stop the
simulated one either, and the two links are most often a parent and its child (the case on one, the
part it turns on the other), which MuJoCo already never collides. Where the two links must still
collide in the simulator, do not exclude them: check that stop with a posed snapshot, and write the
range you read from the hardware instead.

`--geometry collision` sweeps the collision shapes as MuJoCo collides them, the pairs the MJCF never
collides set aside (a body and its parent among them): what a joint hits in the simulator before its
range holds it. Write the stops into `angular_range`, rounded towards zero. A joint found clear all
the way round has no stop in the parts: give it the actuator's own travel, or make it continuous
([Generate from CAD](../SKILL.md#generate-from-cad)).

Then declare `limits(arm, joint, effort=, velocity=, armature=)` from the actuator's datasheet:
the stall torque in N*m, and the no-load speed in rad/s at the supply voltage you use. Give both: a
URDF requires the two, writes 0 for one left out, and a ROS controller reads that 0 as no speed (or
no torque) allowed; the export names each joint it wrote so. Where the datasheet has no speed (a
gripper's often has none), give the drive's from its maker, or measure it. The armature
needs an estimate when the datasheet gives none, and a listing rarely does
([tuning](mujoco-environment.md#tuning)).

## 7. Zero and states

A joint's zero is a fact of the hardware: its controller counts from one pose. Make the
description's zero that pose, so that a joint value means the same in the simulator, in a driver
and in the vendor's datasheet. The CAD's pose is every joint's zero unless you export with
`--zero <state>`.

**Is the drawn pose the controller's zero?** Vendors often draw a robot at its zero, and their
published joint ranges tell. Sweep the stops first (step 6), then lay each published range over the
stops found around the drawn pose:

- A range that is one-sided or lopsided around 0 (0 to 150, -10 to 200) puts the zero at or near
  one end of the travel. A drawn pose folded against a stop, with ranges that start at 0, is that
  pose.
- Where the drawn pose is the zero, every published range fits inside the swept stops, each end a
  little inside the stop on its side (a controller stops short of the parts). Try each joint's two
  signs: usually only one puts the range inside the stops, and that is the controller's sign.
- Where neither sign fits (the range runs through a stop either way), the drawn pose is not that
  joint's zero.

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

## 8. Export, validate, compare

```bash
cad model export "$ID" sim/arm.xml          # --zero <state> only where step 7 re-zeroed
cad model export "$ID" description/arm.urdf
cad mjcf validate sim/scene.xml --compile required
cad urdf validate description/arm.urdf
cad mjcf snapshot sim/scene.xml tmp/mjcf.png --pose '{"shoulder": 30}' --camera right
cad urdf snapshot description/arm.urdf tmp/urdf.png --pose '{"shoulder": 30}' --camera right
```

`--pose` is in degrees for each format, as for the model, though the files hold radians.

Read each export's summary first: the links, the joints, the mass, the collisions by kind. Then
compare the MJCF snapshot with the URDF snapshot of the same pose and camera. Both files come from
one model, so the robot must stand the same way and each joint must turn the same way in both. A
difference is a bug in a writer, whatever the validators say. Report it, and do not ship around it.

## 9. Actuators and Studio

The robot's file has no actuators. Add them to `scene.xml`, the person's file, which the export
writes once ([actuators in the scene](mujoco-environment.md#actuators-in-the-scene)). Then validate
the scene again and open it for the person:

```bash
cad mjcf validate sim/scene.xml --compile required
cad run mujoco-studio --model sim/scene.xml
```
