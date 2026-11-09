# A robot from its vendor STEP

A vendor's STEP of a robot holds parts and their placements, but no mechanism. Exported as it is
(`cad step export vendor/arm.step sim/arm.xml`), each of its top-level parts is a body welded to
the world. To get a robot that moves, write a model that reads the STEP, groups its parts into
links, puts a joint at each hinge, and declares what a simulator needs. Then export it as MJCF and
URDF. The steps below go in order, and each names the reference with the detail. The times given
are ranges for a desktop arm of a few hundred parts on a laptop: they grow with the parts' size and
detail and shrink on a faster machine.

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
`path[1]` is the top-level component (`Forearm v4:1`, `Servo v2:3`). Use a throwaway `cad run`
script to print each component's joined bounds once: it maps the STEP faster than reading the
inspect output does. Look at the pose the vendor drew, too. An arm drawn folded at rest is a fine
CAD pose, but not a simulator's zero (step 7).

## 2. Group the parts into links

This step is the one human decision. Every part goes into exactly one link, and a joint sits
between two links:

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

A hinge's axis is a cylinder in the parts: a servo horn, a bearing bore, a shaft. build123d gives
a cylindrical face's axis in world coordinates:

```python
import build123d as bd

horn_face = horn.faces().filter_by(bd.GeomType.CYLINDER).sort_by(bd.SortBy.AREA)[-1]
axis = horn_face.axis_of_rotation   # an Axis: a point on it and its direction
radius = horn_face.radius
```

A servo's two horns are coaxial, so check that their axes agree before you trust either one.
Measure the axes once in a script and write them in the model as `(point, direction)` constants.
Then:

- **Keep the measured axis; snap only noise.** A component within `1e-9` of 0 is 0 (the `cad`
  skill's kinematics reference). A tilt of a fraction of a degree comes from the vendor's mates, and
  the parts are drawn on it: keep it. Square an axis only if you also place the parts square on it.
  A part that turns about a squared axis while it stays where the STEP drew it wobbles a tenth of a
  millimetre or more against neighbours it clears by less than a millimetre, and `ranges` then finds
  stops that are not there (a jaw that stops far short of closing).
- **Pick each direction's sign** so that a positive angle is the motion you mean (lift raises, the
  jaw opens). The writers copy the sign and cannot know which way is meant.
- **Build each joint at the hinge's own frame.** Put the `RevoluteJoint` on the parent link (its
  Compound, or the part that carries the bearing), `bd.RevoluteJoint(name, parent_link,
  axis=bd.Axis(point, direction), angular_range=...)`. Put `bd.RigidJoint(name, child_link, hinge.location)` on the child link, then
  call `hinge.connect_to(child_link.joints[name], angle=0)`. The child stays where it was drawn.

## 4. Mass

Vendor materials are often wrong for weighing: cables marked steel, printed parts modelled solid.
A material you set replaces the part's colour (the faces the vendor painted keep theirs); set
`part.color` back after it to keep the vendor's. Weigh each part as the hardware is, and count each
part once: what a listing weighs, your declarations together weigh.

- **Printed parts:** a material (`plastics.pla()`), then `mass(part, grams)` estimated from the print
  settings ([inertials](inertials.md#a-printed-part)).
- **Servos and motors:** the datasheet's weight is the servo as sold. Check what that includes: a
  hobby or smart servo's listing usually weighs it with one horn fitted, sometimes with its whole
  bag of horns and screws, sometimes bare. Check the listing; don't count a part twice. When the
  STEP draws the horns as solids of their own, they are inside that weight, and the horns turn with
  the child link while the case stays on the parent (step 2), so one `mass()` cannot hold both.
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

  Where the CAD leaves the motor out, `point_mass()` adds it.
- **Boards and cables:** a weighed figure, or an assumed one written in a comment beside it.

`cad model inspect "$ID"` weighs the result. Read its total against the hardware's: the listed
servos, the printed parts and the rest, each once.

## 5. Collisions

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

## 6. Stops and drive limits

```bash
cad run src/arm.py
cad model ranges "$ID"
```

At its defaults (0.3 mm clearance, 1 degree steps), `ranges` takes tens of seconds for an arm of a
few hundred parts and six joints, by the parts' detail and the machine. The defaults stop each joint
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
snapshot at it. Where it is not the hardware's stop (the jaws still wide apart when the jaw meets
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
the stall torque in N*m, and the no-load speed in rad/s at the supply voltage you use. The armature
needs an estimate when the datasheet gives none, and a listing rarely does
([tuning](mujoco-environment.md#tuning)).

## 7. Zero and states

The CAD's pose is every joint's zero unless you name another one. Compute a `home` state in the
model from the measured axes, name the vendor's pose `rest` with every joint at 0, and export with
`--zero home`. Each joint then counts from `home`, and `rest` becomes a key.

`home` is your choice, said in the model's docstring. For a desktop arm, upright means every link
of the pitch chain pointing straight up (each joint at the angle that stands its link vertical),
the wrist in line, the roll at 0 and the gripper closed. Compute each angle from the axes: a link
runs from its joint's axis to the next joint's (the last along the roll axis), and each joint turns
every link after it, so take them in order. An angle is only meaningful within its range: move it
by a full turn into the range, or the export refuses the state (`wrist at -350 deg, outside its
range -90 to 90`). For an arm whose joints are `base_yaw`, `shoulder`, `elbow`, `wrist`,
`tool_roll` and `jaw`:

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


home = {"base_yaw": 0, "tool_roll": 0, "jaw": RANGES["jaw"][0]}
for at, joint in enumerate(PITCH):
    axis = bd.Vector(*AXES[joint][1])
    angle = turn(along[joint], UP, axis)
    lo, hi = RANGES[joint]
    home[joint] = next((a for a in (angle, angle - 360, angle + 360) if lo <= a <= hi), angle)
    for later in PITCH[at + 1:]:   # this joint carries every link after it
        along[later] = along[later].rotate(bd.Axis((0, 0, 0), axis), home[joint])
mechanism_state(arm, "home", **home)
```

Check the signs on the model before exporting:

```bash
cad model snapshot "$ID" tmp/home.png --pose home --camera right
cad model snapshot "$ID" tmp/lift.png --pose '{"shoulder": 30}' --camera right
```

## 8. Export, validate, compare

```bash
cad model export "$ID" sim/arm.xml --zero home
cad model export "$ID" description/arm.urdf --zero home
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
