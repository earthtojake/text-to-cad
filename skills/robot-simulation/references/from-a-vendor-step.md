# A robot from its vendor STEP

Read this when a robot's source is a vendor's STEP. It holds parts and their placements but no
mechanism, so the robot is a model that reads the STEP, groups its parts into links, puts a joint at
each hinge and declares the hardware's facts (masses, stops, drive limits), then its exports, then
its MuJoCo function. The steps go in that order. Each declaration and what an export prints are in
[from CAD](from-cad.md).

Vendor STEPs come in two kinds, and the steps say what each needs:

- **An assembly with its internals**: printed or machined parts, servos or motors with their horns,
  fasteners, boards and cables, often hundreds of parts. A hobby or desktop arm usually comes so.
- **One plain solid per link**: a simplified envelope of each link, or an industrial arm's outer
  shells, with no motors, gearboxes or fasteners inside. A link may be a few solids (a shell and a
  cap). Such solids are often modelled filled, and neighbours drawn a little into each other.

## 1. Read it

```bash
cad step export vendor/arm.step vendor/arm.xbf      # once: the model reads the xbf
cad step inspect vendor/arm.step --query structure  # counts the parts
cad step snapshot vendor/arm.step tmp/as-drawn.png --camera right
```

In the model's body, `leaves(xbf.read(path), paths=True)` gives each part placed where it stands,
with its path of labels (the `cad` skill's inspection reference, Opening geometry): `path[1]` is the
top-level component (`Forearm v4:1`, `Servo v2:3`). Print each leaf's path, volume, face count and
bounds once from a throwaway `cad run` script: it maps the STEP faster than the inspect output does.
Note the pose the vendor drew: it may be the controller's zero, or only a pose to ship it in
(step 6).

**Which way is up.** Many CAD tools draw Y up, and no export option turns a robot over. Re-place
every leaf as you take it with one rigid placement, which takes the vendor's up to +Z and puts the
base's mounting face on z = 0 and its first axis on the Z axis, and measure the axes (step 3) on the
re-placed parts. A snapshot then shows the base on the ground.

```python
TO_WORLD = bd.Pos(0, 0, LIFT) * bd.Location((0, 0, 0), (90, 0, 0))   # vendor +Y up to +Z
# Where no single turn does it, say where two of the vendor's axes go: here its X (the robot's left)
# to world +Y and its Z (forward) to +X. Its Y lands on their cross product, Z x X: check that it is
# the up you mean (+Z here), since a Plane is always a rotation and never a mirror.
TO_WORLD = bd.Pos(0, 0, LIFT) * bd.Location(bd.Plane(origin=(0, 0, 0), x_dir=(0, 1, 0), z_dir=(1, 0, 0)))

part = TO_WORLD * part                                    # keeps its label, colour and material
point = (TO_WORLD * bd.Location(vendor_point)).position   # a point: a Location times a Vector is refused
```

## 2. Group the parts into links

Every part goes into exactly one link, and a joint sits between two links. The grouping is the one
input the geometry does not settle. In a STEP of one plain solid per link, each solid (or the few
solids of one link) is a link, in chain order from the base. In an assembly with its internals:

- **Printed or machined parts go by function.** A bracket that carries a servo and the arm segment
  that servo turns are two links.
- **A servo's case goes with the link it is screwed to, and its horns** (the drive horn on the
  output shaft, and the idle horn opposite it where it has one) **with the link they turn.** A label
  may not say which horn is which (vendors label parts in their own language); the geometry does. The
  drive horn is splined onto its shaft, so it has many more cylindrical faces
  (`part.faces().filter_by(bd.GeomType.CYLINDER)`) than the idle horn on its plain bore.
- **A motor or servo drawn as one solid**, its case and its output (flange, horn) together, cannot be
  split by parts: it goes with the link its case is screwed to, and the plate bolted to its output
  face with the next link. Where the output is bolted to the parent's bracket (a servo mounted the
  other way round), the case is the child's. `ranges` reads such a pair as an output and what turns
  on it (step 5), so the sweep needs no split.
- **Cables, boards and connectors** go with the link they are clipped to.
- **Fasteners go with the part they hold**: the nearest part, found by bounding boxes first, then by
  distance from the fastener's centre (a `bd.Vertex`) to the few candidates the boxes leave. A
  solid-to-solid `closest_points` on printed parts of thousands of faces takes minutes per hundred
  pairs. Three cases override the nearest part:
  - A fastener on a joint's axis (its centre within a millimetre of it) is the horn's centre screw:
    it threads into the parent's output shaft but turns with the child, so it is the child's.
  - A fastener through two parts goes with the link of the two it clamps, even where a part of
    another link is nearer its centre (a horn beside the screw that holds a bracket to its servo).
  - At a joint, the screws that clamp a plate to an output lie inside parts of both links: they go
    with the plate's link, and the screws that hold the case with the case's.
- **A vendor's own sub-assembly per link** (`LINK-2_ASM`, `Forearm_ASM`) is a link, and its
  membership settles its fasteners too: a vendor puts the screws that hold a plate in the plate's
  sub-assembly. Check its boundary at each joint (the motor's case in one, the plate on its output in
  the next), and place any loose top-level part by the rules above.
- **A branched or free-floating robot** (a humanoid, a legged robot) is a base with a chain per limb.
  The base is the torso or pelvis: declare `free()` on the top assembly, and put the soles, not a
  mounting face, on z = 0. One component (a servo, a bracket) repeats in every limb and several times
  along one, so key the table below by component and position: the leaf's centre in bands along the
  limb (its height down a leg, its distance out along an arm) and its side (the sign of its
  coordinate across the body). Left and right limbs are mirror images, so one joint's measured axis
  points the other way on the other side: give each side the sign that makes a positive angle the
  motion you mean (step 6 for the controller's).

Write the grouping as a table of component to link, and raise on any leaf the table does not place,
so that a new revision of the STEP fails loudly instead of dropping a part. As you take the leaves:

- Relabel a vendor's anonymous bodies (`if part.label in ("SOLID", "Body1"): part.label = path[-2]`):
  every message, the exported files and a MuJoCo function name a part by its label.
- Drop empty bodies, placeholders with no volume (`if part.volume <= 0: continue`): kept, they weigh
  nothing, and a `mass()` declared on one alone is refused.
- Put each link's parts in a `bd.Compound(children=..., label=...)` and name it for ROS with `link()`.

A posed snapshot (step 6) shows every link moving as one piece: a part left behind, or swinging with
the wrong link, was sorted wrong.

## 3. Find each joint axis from the geometry

A hinge's axis is a circle in the parts: a servo horn, a bearing bore, a shaft, a flange. Read it on
both sides of the hinge, the parent's and the child's, in world coordinates:

```python
for face in part.faces().filter_by(bd.GeomType.CYLINDER):     # a horn, a bore, a shaft
    axis = face.axis_of_rotation                               # an Axis: .position and .direction
    offset = face.position_at(0.5, 0.5) - axis.position        # face.radius is None on a trimmed cylinder
    radius = (offset - axis.direction * offset.dot(axis.direction)).length
for edge in part.edges().filter_by(bd.GeomType.CIRCLE):       # a bore's rim, a flange's edge
    centre, normal, radius = edge.arc_center, edge.normal(), edge.radius
```

Cylindrical faces come first. Smooth covers and freeform shells often have none that match across a
hinge, but their rims still do: circular edges of the parent and the child with one normal and
coaxial centres. Keep the axes the two sides share to within about a millimetre (a servo's two horns
are coaxial, so check that they agree), and write them in the model as `(point, direction)`
constants. Then:

- **Keep the measured axis; snap only noise** (a component within `1e-9` of 0 is 0). A tilt of a
  fraction of a degree comes from the vendor's mates, and the parts are drawn on it. A part turned
  about a squared axis while it stands where the STEP drew it wobbles a tenth of a millimetre or more
  against neighbours it clears by less than a millimetre, and `ranges` then finds stops that are not
  there (a jaw that stops far short of closing). Square an axis only if you also place the parts
  square on it.
- **Where the two sides disagree** (a vendor's parts can be drawn a few tenths of a millimetre off
  each other's axis), **use the child's bore**: the child then turns in place and the parent keeps
  its offset, where on the parent's axis the child would swing on a small circle into its
  neighbours. Write the offset in a comment beside the axis.
- **Pick each direction's sign** so that a positive angle is the motion you mean (lift raises, the
  jaw opens), or the controller's sign where it is known (step 6).
- **Build each joint at the hinge's own frame**, on the two links' Compounds, so that the child stays
  where it was drawn:

```python
hinge = bd.RevoluteJoint(name, parent_link, axis=bd.Axis(point, direction), angular_range=(lower, upper))
bd.RigidJoint(name, child_link, hinge.location)
hinge.connect_to(child_link.joints[name], angle=0)
```

## 4. Mass

Vendor materials are often wrong for weighing: cables marked steel, printed parts modelled solid,
shells modelled filled. Weigh each part as the hardware is, and count each part once. A material you
set replaces the part's colour (the faces the vendor painted keep theirs): set `part.color` back
after it, or, where the STEP has no colours at all (`part.color` is None), give the parts a neutral
one.

- **One plain solid per link.** The datasheet's weight of the arm is usually all there is: one
  material on every solid and `mass(arm, TOTAL_G)` split it by volume, and a `point_mass()` for each
  joint's actuator puts the mass back at the joints
  ([inertials](inertials.md#a-link-drawn-as-one-plain-solid)).
- **Printed parts**: a material, then `mass(part, grams)` estimated from the print settings
  ([inertials](inertials.md#a-printed-part)).
- **Servos and motors**: the datasheet's weight is the servo as sold, so check what the listing
  includes: a hobby or smart servo's usually weighs it with one horn fitted, sometimes with its whole
  bag of horns and screws, sometimes bare. Horns the STEP draws as solids of their own turn with the
  child link while the case stays on the parent, so one `mass()` cannot hold both. Give each horn the
  listing includes its share (`mass(horn, grams)`: a spare horn's listed weight, or its volume at its
  metal's density) and the servo's sub-assembly, the `bd.Compound` of its case and internals, the
  rest of the listing. A horn the listing leaves out adds its own weight on top. Where the CAD leaves
  the motor out, `point_mass()` adds it.
- **Boards and cables**: a weighed figure, or an assumed one written in a comment beside it.

`cad model inspect "$ID"` weighs the result and lists each declared mass: read its total against the
hardware's.

## 5. Stops and drive limits

```bash
cad model ranges "$ID"               # every joint, each swept alone until its child link meets its parent
cad model ranges "$ID" --joint jaw   # one joint again, after a change
```

The sweep takes tens of seconds for a few hundred small parts and minutes for a few large freeform
shells: its time follows the parts' surface area, not their count. Keep the default clearance: its
stops are where the parts all but touch, and a larger `--clearance` only narrows a range (at 1 mm a
jaw can stop well short of closing). Each joint's line gives its stops and, for each, the two parts
that met and their links (the `cad` skill's kinematics reference, Joint stops, reads every phrase of
it). Read what made a stop before writing it into the joint's `angular_range`, rounded towards zero:

- **A part named in a link it does not belong to** was sorted wrong (step 2). A stop at 0 means the
  same, unless the vendor drew the arm at that stop: an arm drawn folded flat (a forearm resting on
  its upper arm) has a real stop at 0, which a posed snapshot a few degrees the other way confirms.
- **`touching as built`.** Vendor parts often stand a fraction of a millimetre apart (a moving jaw
  beside the cover of the servo that drives it). Check a stop that says so with a posed snapshot at
  it: a servo's case is often several shells, and a part that clears one sweeps into the next.
- **A stop that is not the hardware's** (the jaws still wide apart when the jaw meets that cover):
  the sweep cannot tell. Write the range you read from the hardware instead: the datasheet's travel,
  or the pose where the parts really meet. What the simulator collides there is step 8's choice.
- **`turns on: plate (link2) on motor (link1)`** is a horn on its servo, or a motor drawn as one
  solid with its output and the next link bolted to it: contact there stops nothing, and the case
  beyond the output still does, as on the hardware. A stop a few degrees out that still names such a
  pair `touching as built` means the output carries something past its own reach: split the output
  from the case in the model, or write the range you read from the hardware.
- **`deeper than drawn`.** Simplified parts are often drawn sunk into each other (a link a little too
  wide for its clevis, a carriage inside its rail), and stop the joint only where one is pushed
  deeper. Such a stop lies past the true one by up to about the depth it gives: read it against a
  posed snapshot and the datasheet, and write the narrower.
- **A clash**, said beside a stop, is what the joint moves meeting another link in the drawn pose of
  the other joints (a wrist resting on the shoulder of an arm drawn folded). Write the stop: the
  clash moves with the other joints, and the simulator's contacts hold it.
- **A stop wider than the actuator's travel.** A stop past a half turn (-239 degrees) is the parts'
  own, within the full turn swept each way: where the actuator's travel is narrower (a servo's
  position range), write that. A joint found clear all the way round takes the actuator's travel, or
  is continuous ([joint ranges](from-cad.md#joint-ranges)).

Then declare `limits(arm, joint, effort=, velocity=)` from the actuator's datasheet: its stall torque
in N*m, and its no-load speed in rad/s at the supply voltage you use. Give both
([a URDF writes 0 for one left out](from-cad.md#frames-bodies-and-drive-limits)): where the datasheet
has no speed (a gripper's often has none), give the drive's from its maker, or measure it.

## 6. Zero and states

A joint's zero is a fact of the hardware: its controller counts from one pose, and the description's
zero should be that pose ([from CAD](from-cad.md#the-mechanism-and-its-zero)). The drawn pose is
every joint's zero unless you export with `--zero <state>`. Vendors often draw a robot at its zero,
and their published joint ranges tell: lay each range over the stops swept around the drawn pose
(step 5).

- A range that is one-sided or lopsided around 0 (0 to 150, -10 to 200) puts the zero at or near one
  end of the travel. A drawn pose folded against a stop, with ranges that start at 0, is that pose.
- Where the drawn pose is the zero, every published range fits inside the swept stops, each end a
  little inside the stop on its side (a controller stops short of the parts). Try each joint's two
  signs: usually only one puts the range inside the stops, and that is the controller's sign.
- Where neither sign fits (the range runs through a stop either way), the drawn pose is not that
  joint's zero.
- Mirrored limbs: a controller counts the left and right joints either mirrored (both knees bend at
  positive angles) or the same way about one axis (one knee positive, the other negative). A lopsided
  range that fits one side's stops with one sign fits the other side's with the opposite sign where
  it is mirrored.

Where the ranges fit, keep the drawn pose as the zero, write the datasheet's ranges as the limits,
and say so in the model's docstring with the evidence (each range against its stops). Re-zero only
when you know the controller's zero is another pose, from the vendor's own description (a URDF, a
driver's calibration) or its manual: make that pose a mechanism state, name the drawn pose too
(`mechanism_state(arm, "drawn")`, a state that moves no joint), and export with `--zero <state>`.

**What stays undetermined.** A roll joint clear all the way round has no stop to fit a range
against, and a symmetric range (±360) says nothing either: neither its zero nor its sign can be told
from the geometry or the datasheet. The same holds for a joint whose range and stops are both
symmetric. Keep the drawn pose's 0 and a stated convention for the sign (positive turns
counter-clockwise looking out along the link), and write in the docstring that both are unchecked,
so that whoever connects the controller checks them.

**States.** `home` is the pose the hardware starts from: the zero itself where the controller parks
there. A working pose is another state. Compute a state's angles from the measured axes rather than
by eye: a link runs from its joint's axis to the next joint's, and each joint turns every link after
it, so take them in order. A state outside a joint's range fails the run: such an angle may be the
same pose a full turn round, and where no turn brings it inside, the pose is out of this robot's
reach (an elbow that stops short of straight cannot stand the arm upright).

Check each joint's sign on the model before exporting:

```bash
cad model snapshot "$ID" tmp/home.png --pose home --camera right
cad model snapshot "$ID" tmp/lift.png --pose '{"shoulder": 30}' --camera right
```

## 7. Export and compare

```bash
cad model export "$ID" sim/arm.xml description/arm.urdf   # add --zero <state> only where step 6 re-zeroed
cad mujoco check sim/scene.xml
cad urdf validate description/arm.urdf
cad urdf snapshot description/arm.urdf tmp/urdf.png --pose '{"shoulder": 30}' --camera right
```

Both files come from one model, so the two exports' summaries must name the same links and joints
and the same mass, and `cad mujoco check` must count those bodies and joints (one joint more on a
free base, its `<freejoint>`). Then compare the URDF's snapshot with the model's (step 6) at the same
pose and camera: the robot must stand the same way, and each joint turn the same way. A difference is
a bug in a writer, whatever the checks say: report it, and do not ship around it.

## 8. The MuJoCo function

What a simulation chooses for the robot goes in a MuJoCo function beside the model, whose file
replaces the plain export: read [MuJoCo environment](mujoco-environment.md#the-mujoco-function)
before writing one. Where step 6 re-zeroed, it takes the same state: `spec(arm(), zero="<state>")`.

**Collisions.** A maker's assembly has a hundred parts or more, most of them fasteners: choose by a
rule over `parts(s)` rather than naming each screw.

- **One plain solid per link**: `decompose()` a concave link (a yoke, a clevis, a gripper's palm with
  its slot), keep the default hull on a convex one (a base, a roll link), and delete the collisions
  of a part that runs inside another (a sliding bar inside its guide).
- **Printed parts**: `decompose()`, so that the pocket a servo sits in stays a pocket.
- **Servo cases**: `fit(s, part, "box")` on each shell of the case (the body and its covers), and
  delete the collisions of the motor, gears and board inside.
- **Fasteners, horns clamped inside a bracket, cables and boards**: delete their collisions.

**Joints.** Each driven joint takes its armature ([tuning](mujoco-environment.md#tuning) says where
that number comes from), a light damping and a position actuator, whose gains are a start for tuning
unless the datasheet gives them. `limits(effort=)` already bounds its force. A coupled follower takes
no actuator: its equality drives it.

**Check it.** Read what the run printed against those choices
([what collides, and the excludes](mjcf-checks.md#what-collides-and-the-excludes)). Then:

- **Hulls at their cap.** A part that reaches its cap says so as it is done (`decomposed bracket: 16
  hulls, the cap (max_hulls=16) in 8.1 s`): CoACD merged hulls to fit, so some bridge a concave
  region. Find out whether that matters before changing anything: in a throwaway script, set the
  joint whose parts enter that region to each end and the middle of its range (`mujoco.mj_forward`)
  and print the geom names of `d.contact[:d.ncon]`. A contact between two hulls at a pose where the
  parts clear each other in the CAD (`cad model snapshot` at that pose) is a hull bridging the gap; a
  pair of bodies the file excludes makes no contact at all, so read the `excludes` line first. A hull
  that fills a pocket a neighbour moves into, a slot or the gap between jaws is contact the hardware
  does not make: raise that part's cap (`max_hulls=32`) or lower its `threshold`. One that only
  rounds over an inside corner nothing reaches does not matter, and a part whose shape never matters
  for contact can take fewer.
- **Hulls that meet at rest.** A hull's faces bridge its part's concave places by a few millimetres
  at any threshold, so two links that clear each other by less beside one (a wrist parked against the
  upper arm in the drawn pose) meet as hulls, and `cad mujoco check` warns `contacts_at_rest`. No
  hull setting clears them: a finer threshold costs tens of times longer, and the deepest bridge
  stays. Where the links never meet in the hardware's working range, exclude the pair
  (`s.add_exclude(bodyname1="wrist_link", bodyname2="upper_arm_link")`), with a comment saying the
  simulator lets them pass through each other. Where they must still collide, try a fitted
  `"cylinder"` or `"capsule"` on the convex one of the pair.
- **It holds a pose.** In a throwaway script, reset to a key that commands its pose (a state's key
  carries no `ctrl`: [keys](mujoco-environment.md#the-mujoco-function)) and step the scene for 2 s.
  Each joint should end within a few hundredths of a radian of the key. One that sags is a gain, an
  armature or a force bound to look at; one that rings or explodes is a model-health warning to clear
  first.

Then open it for the person: `cad run mujoco-studio --model sim/scene.xml`.
