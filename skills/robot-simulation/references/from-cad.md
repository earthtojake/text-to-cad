# A robot description from a CAD model

Read this when a text-to-cad model is the source of a URDF or an MJCF: what the model declares, how
each declaration is written, and what an export prints. What each format cannot say is tabled in
[interoperability.md](interoperability.md#one-description-two-writers); a simulation's choices are
the [MuJoCo function](mujoco-environment.md#the-mujoco-function)'s.

## Contents

- [The mechanism and its zero](#the-mechanism-and-its-zero)
- [Joint ranges](#joint-ranges)
- [Links and the base](#links-and-the-base)
- [States, couplings and loops](#states-couplings-and-loops)
- [Mass](#mass)
- [Frames, bodies and drive limits](#frames-bodies-and-drive-limits)
- [The export](#the-export)

## The mechanism and its zero

The links and joints are the model's mechanism: build123d's `RevoluteJoint`, `LinearJoint`,
`CylindricalJoint` and `BallJoint`, connected with `connect_to`. The as-built pose is every joint's
zero in the description, and each joint's limits are its range less the value it was built at: a
finger built at 30 degrees in a range of 0 to 40 is written as a hinge of -30 to 10 degrees, with no
warning. Build open, straight or homed, and the file's values are the CAD's.

Where the robot has a controller, the description's zero should be the controller's zero, so a joint
value means the same in the simulator and on the hardware. Where there is none yet, build the
mechanism at the pose a simulator should start from (fingers open, arm straight). Where the
controller's zero is another pose than the one drawn, name that pose a mechanism state and export
with `--zero <state>`: every body stands as the state poses it, each joint counts from there (its
limits and the other states shifted with it), and the CAD stays as drawn. A vendor's STEP is often
drawn at its controller's zero ([from a vendor STEP](from-a-vendor-step.md#6-zero-and-states) says
how to tell).

## Joint ranges

- **Stops that are the parts meeting**: `cad model ranges <id>` moves each joint alone until its child
  link meets its parent and prints each stop, in degrees or millimetres, in the joint's own values
  (the ones `angular_range` takes, whatever value it was built at). Write them into the joint's
  `angular_range` or `linear_range`, rounded towards zero, and run the model again (`cad model ranges --help` has the options).
- **A servo's own travel**, narrower than that, is its datasheet's.
- **A joint the parts never stop** (a wrist roll): give it the actuator's travel (a position servo's
  one turn, `angular_range=(-180, 180)` around the pose its encoder centres on), a limited hinge in
  MJCF and a `revolute` in URDF.
- **A joint that turns without end** (a slip ring, a wheel): `angular_range=(-math.inf, math.inf)`, a
  hinge with no range in MJCF and a `continuous` joint in URDF.

## Links and the base

- **`link(part_or_assembly, name)`** names the link its parts make (`base_link`, `upper_arm_link`).
  Without it a link takes its jointed assembly's label (the `Compound` that holds its joint), else
  its first part's; a body is named by `body()`. Two links of one name, or one link's parts declaring
  two, are refused by name.
- **The base link.** Name the link the robot stands on `base_link`, the frame ROS tools expect.
  Where that link has a mass or stands off the world's origin, the URDF roots at an empty
  `base_footprint` on a fixed joint above it, as REP 105 roots a base, because KDL takes no inertia
  on the root; `base_link` stays the robot's base frame. A root of another name gets an empty
  `base_link` above it instead.
- **`free(assembly)`** says the robot is not bolted to the world (a humanoid, a quadruped, a mobile
  base, a part dropped on a table). On the top assembly its base floats: an MJCF `<freejoint>`, its
  seven values in every key, and a URDF's root, which floats already. The floating base's frame
  stands at its link's centre of mass with the model's axes, so a key's first three values and the
  simulator's base position read where the base is (a humanoid's at its torso, not on the floor
  between its feet). Mount an IMU or a camera on a `frame()` of the torso's part, not on the base
  frame. In a model with no joints, each top-level part or assembly is a body, and `free()` on one,
  or on a part inside it, floats that body alone. Bolted is the default.

## States, couplings and loops

- **Mechanism states** (`mechanism_state(assembly, "home", ...)`) are the named poses: MJCF keys (a
  URDF holds no poses). Name one `home`, the pose a person and a controller start from.
- **Couplings** (`gear_pair`, `rack_and_pinion_pair`) are a follower joint on its leader: MJCF's
  `<equality><joint>`, URDF's `<mimic>`. Two slides one pinion drives (a parallel gripper) couple
  through a `RevoluteJoint` on the palm connected to nothing, named first in the
  `rack_and_pinion_pair`, where the CAD draws no pinion: the file has no body or joint for it, and
  the second slide follows the first, one control as on the hardware.
- **Closed loops** (a four-bar, a slider-crank): connect the joints of a tree from the ground, then
  pair the loop's last joint by label where both parts already stand. The MJCF closes the loop there
  with an equality between a site on each body (two `connect`s for a hinge, one for a ball; where the
  last joint is a slide, at the loop's nearest hinge or ball instead). The URDF leaves that joint out
  and says so. A loop's joints have no named pose and no stops from `cad model ranges`.

## Mass

Every number here is the kernel's, exact, from the solids ([inertials.md](inertials.md) has the
parts a density weighs wrongly, and the checks).

- **Materials** (`part.material = metals.aluminum()`, from `bd_materials`) give each part a density,
  so each link's mass, centre of mass and inertia tensor follow. A part with no material weighs
  nothing, and a link of such parts has no inertial.
- **`mass(part_or_assembly, grams)`** is what the hardware weighs (a scale's reading, a
  datasheet's): the solids below it keep their densities' ratios and are scaled alike to make up
  `grams`, so the centre of mass and the inertia's shape stay the geometry's. Where none of them has
  a material they share one density; a part with no material among parts that have one carries none
  of the total, and the export says so. An inner `mass()` fixes its own subtree; an outer one scales
  only the solids no inner one holds.
- **`point_mass(part, grams, at, name=, inertia=)`** is a lump the CAD leaves out (a motor inside a
  filled housing), at `at` in the part's own frame, with no inertia of its own unless `inertia=(ixx,
  iyy, izz)` (kg*m^2, in `at`'s axes) gives it. A `mass()` above it counts it: the lumps are fixed
  and the solids make up the rest, and a total the lumps reach or pass is refused.

## Frames, bodies and drive limits

- **`frame(part, name, location)`** names a frame on a part (a tool point, a camera mount, a
  sensor), in the part's own frame, the one its geometry is in before it is placed: for a 100 mm bar
  built up from its own origin and then placed 140 mm up (`bd.Pos(0, 0, 140) * bar`), the tip is
  `bd.Pos(0, 0, 100)`, not world z 240.
  A site in MJCF, an empty link on a fixed joint in URDF. The export's summary names each frame it
  wrote, and the MJCF's `<site pos>` says where it stands, in metres in its link's frame.
- **`body(part, name=None)`** keeps a part a body of its own, fixed to the link it would merge into
  (a camera mount, a fingertip the simulator addresses), with its own mass and geoms.
- **`limits(assembly, joint, effort=, velocity=)`** is a joint's drive limits from its datasheet, in
  N*m or N and rad/s or m/s: the URDF's `<limit>` and MJCF's `actuatorfrcrange` (MJCF has no speed
  bound). Without them a URDF says `effort="0" velocity="0"`, which a ROS controller reads literally;
  a joint given only one of the two has the other written 0, and the export's log names it.

## The export

```bash
cad run src/gripper.py
cad model ranges "$ID"
cad model export "$ID" sim/gripper.xml
cad model export "$ID" description/gripper.urdf --zero home
cad step export vendor/part.step sim/part.xml
```

- **Read what it wrote.** After the file's line, an export says its links and how its base stands,
  its joints by kind, its total mass, then its couplings, loops, frames, collisions, contact excludes
  (the jointed pairs touching at rest), keys and zero; every warning (a link with no mass, a joint
  left out) is a line of the log before it. `--json` gives the same as the file row's `robot`. A mass
  of 0, a link you did not expect or a missing joint is a model to fix.
- **Its meshes** are written beside the file ([meshes](meshes.md)), with a list of them
  (`.gripper.xml.meshes`). By that list, the next export of the file removes the meshes it no longer
  names (parts renamed or gone), never a file it did not write nor one another robot's list names.
- **The scene.** An MJCF export to `sim/gripper.xml` writes `sim/scene.xml` beside it when there is
  none: it includes the robot's file and adds a floor, a light and a skybox. The scene is yours to
  edit (solver settings, cameras, other bodies), and an export never writes over it.
- **The layout** is that of published MuJoCo robots: radians, `meshdir="assets"`, `autolimits`,
  `implicitfast`, a `visual` class in group 2 that collides with nothing and a `collision` class in
  group 3, explicit `<inertial>`s, a site per frame, a key per state.
- **What a plain export does not hold**: a chosen collision shape, joint dynamics or an actuator.
  Each part collides as its own mesh (MuJoCo collides a mesh as its convex hull), and nothing drives
  or holds its joints. It needs no MuJoCo to write.
- **A STEP has no mechanism**: exported as it is, each top-level part is a body fixed to the world.
  Articulate it in a model first ([from a vendor STEP](from-a-vendor-step.md)).
