# A robot from its vendor STEP

A vendor's STEP of a robot holds parts and their placements, but no mechanism. Exported as it is
(`cad step export vendor/arm.step sim/arm.xml`), each of its top-level parts is a body welded to
the world. To get a robot that moves, write a model that reads the STEP, groups its parts into
links, puts a joint at each hinge, and declares what a simulator needs. Then export it as MJCF and
URDF. The steps below go in order, and each names the reference with the detail. The times are from
one run: a 270-part, six-servo desktop arm on a laptop.

## 1. Read it

Copy the STEP to a path with no spaces in it, convert it once, and read the xbf in the model's body:

```bash
cad step export vendor/arm.step vendor/arm.xbf
cad step inspect vendor/arm.step --query structure
cad step snapshot vendor/arm.step tmp/as-drawn.png --camera right
```

The conversion takes seconds. `xbf.read(HERE / "../vendor/arm.xbf")` then hands the model a tree,
and `leaves(tree, paths=True)` gives each part placed where it stands, with its path of labels
(the `cad` skill's inspection reference, Opening geometry).
`path[1]` is the top-level component (`Upper_arm v12:1`, `ST3215 Servo v2:3`). Use a throwaway
`cad run` script to print each component's joined bounds once: it maps the STEP faster than
reading the inspect output does. Look at the pose the vendor drew, too. An arm drawn folded at rest
is a fine CAD pose, but not a simulator's zero (step 7).

## 2. Group the parts into links

This step is the one human decision. Every part goes into exactly one link, and a joint sits
between two links:

- **Printed or machined parts by function.** A bracket that carries a servo and the arm segment
  that servo turns are two links.
- **A servo's case goes with the link it is screwed to.** Its horns (the drive horn on the output
  shaft and the idle horn opposite it) go with the link they turn.
- **Cables, boards and connectors go with the link they are clipped to.**
- **Fasteners go with the part they hold.** Use the nearest part, found by bounding boxes first. A
  solid-to-solid `closest_points` on printed parts of thousands of faces runs for minutes per
  hundred pairs, so measure from the fastener's centre (`bd.Vertex`) to the few candidates the
  boxes leave.

Write the grouping as a table of component name to link, and raise on any component the table does
not name, so that a new revision of the STEP fails loudly instead of dropping a part. Put each link
in a `bd.Compound(children=..., label=...)` and name it for ROS with `link()`. A posed snapshot
(step 7) shows every link moving as one piece. A part left behind or swinging with the wrong link
was sorted wrong.

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
  skill's kinematics reference). A tilt of half a degree comes from the vendor's mates, and the
  parts are drawn on it: keep it. Square an axis only if you also place the parts square on it.
  A part that turns about a squared axis while it stays where the STEP drew it wobbles 0.1 to
  0.2 mm against neighbours it clears by less than a millimetre, and `ranges` then finds stops
  that are not there (a gripper shut at -49 degrees instead of -95).
- **Pick each direction's sign** so that a positive angle is the motion you mean (lift raises, the
  gripper opens). The writers copy the sign and cannot know which way is meant.
- **Build each joint at the hinge's own frame.** Put the `RevoluteJoint` on the parent link (its
  Compound, or the part that carries the bearing), `bd.RevoluteJoint(name, parent_link,
  axis=bd.Axis(point, direction), angular_range=...)`. Put `bd.RigidJoint(name, child_link, hinge.location)` on the child link, then
  call `hinge.connect_to(child_link.joints[name], angle=0)`. The child stays where it was drawn.

## 4. Mass

Vendor materials are often wrong for weighing: cables marked steel, printed parts modelled solid.
Weigh each part as the hardware is:

- **Printed parts:** a material (`plastics.pla()`), then `mass(part, grams)` estimated from the print
  settings ([inertials](inertials.md#a-printed-part)).
- **Servos and motors:** `mass(case, grams)` on the servo's sub-assembly, from the datasheet, or
  `point_mass()` where the CAD leaves the motor out.
- **Boards and cables:** a weighed figure, or an assumed one written in a comment beside it.

`cad model inspect "$ID"` weighs the result. Read its total against the hardware's.

## 5. Collisions

- **Printed parts:** `collision(part, "decomposed")`, so that the pocket a servo sits in stays a
  pocket. The first export decomposes each part, at about 15 s per printed part (3 minutes for
  eleven). The hulls are cached by each part's mesh and options, and only a changed part
  decomposes again.
- **Servo cases:** `"box"` on the case's shell leaves (the body and its covers) and `"none"` on the
  motor, gears and board inside. `collision()` on the servo's assembly applies to every leaf below
  it, so it would box the internals too.
- **Fasteners, horns clamped inside a bracket, cables and boards:** `"none"`.

Match labels by pattern while you loop over the leaves, as the `cad` skill's inspection reference
shows under Opening geometry.

## 6. Stops and drive limits

```bash
cad run src/arm.py
cad model ranges "$ID"
```

At its defaults (1 mm clearance, 1 degree steps), `ranges` took 19 s for six joints. With
`--clearance 0.2 --step 0.5` it took 7 minutes, because it sweeps on one core. Start at the
defaults, and narrow one question with a posed snapshot instead. Each stop should name two parts of
neighbouring links. A stop at 0, or one that names a part of a link that is not a neighbour, means
a part is in the wrong link. Write the stops into `angular_range`, rounded towards zero. A joint
found clear all the way round has no stop in the parts: give it the actuator's own travel, or make
it continuous ([Generate from CAD](../SKILL.md#generate-from-cad)).

Then declare `limits(arm, joint, effort=, velocity=, armature=)` from the actuator's datasheet:
the stall torque in N*m, and the no-load speed in rad/s at the supply voltage you use. The armature
needs an estimate when the datasheet gives none
([tuning](mujoco-environment.md#tuning)).

## 7. Zero and states

The CAD's pose is every joint's zero unless you name another one. Compute a `home` state in the
model from the measured axes (the arm upright, the gripper closed), name the vendor's pose `rest`
with every joint at 0, and export with `--zero home`. Each joint then counts from `home`, and
`rest` becomes a key. Check the signs on the model before exporting:

```bash
cad model snapshot "$ID" tmp/home.png --pose home --camera right
cad model snapshot "$ID" tmp/lift.png --pose '{"shoulder_lift": 30}' --camera right
```

## 8. Export, validate, compare

```bash
cad model export "$ID" sim/arm.xml --zero home
cad model export "$ID" description/arm.urdf --zero home
cad mjcf validate sim/scene.xml --compile required
cad urdf validate description/arm.urdf
cad mjcf snapshot sim/scene.xml tmp/mjcf.png --pose '{"shoulder_lift": 30}' --camera right
cad urdf snapshot description/arm.urdf tmp/urdf.png --pose '{"shoulder_lift": 30}' --camera right
```

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
