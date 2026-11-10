---
name: robot-simulation
description: Robot and world descriptions (URDF, SRDF, MJCF) for ROS, MoveIt and MuJoCo. Use to generate a robot description or a MuJoCo scene from a CAD model's joints, materials and collision, or to write and review a `.urdf`, `.srdf` or MJCF `.xml` by hand (links, joints, inertials, meshes, MoveIt groups, MuJoCo classes, actuators, keyframes, model health). Not the CAD part itself, which the `cad` skill makes, nor a simulation run.
license: MIT
metadata:
  repository: earthtojake/text-to-cad
---

# Robots and worlds for simulation and motion planning

A robot is described for its consumers in XML: a URDF for its structure (ROS, RViz,
robot_state_publisher), an SRDF beside it for MoveIt's planning semantics, and an MJCF for MuJoCo.
There are two routes to one:

- **Generate it from CAD.** A text-to-cad model that holds the mechanism (build123d joints, mechanism
  states, couplings), materials, and what each part collides as and which frames it names, is written
  as an MJCF or a URDF by `cad model export`, or handed to a MuJoCo scene in code by
  `cad.mujoco.spec`. Frames, limits, masses, inertias and meshes come from the kernel, exactly: the
  model is the source of truth, and the file is regenerated, never edited.
- **Author it by hand.** A robot with no CAD model here, an SRDF (always), a MuJoCo scene, or a file
  that already exists: the `.urdf`, `.srdf` or MJCF `.xml` is the source of truth, written
  and edited directly. The work is constrained kinematic modeling, not XML writing: the risks are
  frame placement, joint-axis semantics, units, mesh scale, inertial data and planning semantics, and
  a file can pass every check while placing a joint in the wrong spot.

## Start with the task

| Task | Start with | Reference |
| --- | --- | --- |
| **A robot description from a CAD model** (MJCF or URDF) | The model's mechanism, materials, `collision()`, `frame()`, `body()`, `exclude()`, `limits()`, `mass()`, `point_mass()`, `friction()`, `free()` and `link()`, then `cad model export <id> robot.xml` (or `.urdf`, `--zero home` to count the joints from a state). | [Generate from CAD](#generate-from-cad), [interoperability](references/interoperability.md#one-description-two-writers) |
| **A robot from its vendor STEP** (an arm's downloaded assembly) | Read it, group its parts into links, find each axis from the geometry, then declare, export and compare the MJCF with the URDF. | [From a vendor STEP](references/from-a-vendor-step.md) |
| **Joint limits from the parts** | `cad model ranges <id>`: each joint swept alone until its parts meet, then the stops written into the joint's range in the model. | [Generate from CAD](#generate-from-cad) |
| **A MuJoCo environment: CAD parts, a Menagerie robot, a scene** | `spec()` for each CAD piece, composed with MuJoCo's own `MjSpec` in a script, then `cad mjcf validate --compile required`. | [MuJoCo environment](references/mujoco-environment.md) |
| **Tune a MuJoCo model's physics** | The model-health findings of `cad mjcf validate --compile required`, then one parameter at a time. | [Tuning](references/mujoco-environment.md#tuning), [checks](references/mjcf-checks.md#model-health) |
| **Describe a robot's links and joints by hand** (ROS, RViz, TF, MoveIt's model) | The `.urdf` and its ledger, then `cad urdf validate`. | [Authoring](references/urdf-authoring.md), [frames](references/urdf-frames.md), [ledger](references/urdf-ledger.md) |
| **Add MoveIt planning groups, end effectors, named states, collision pairs** | The URDF's link/joint table, then a `.srdf` beside it and `cad srdf validate`. | [Authoring](references/srdf-authoring.md), [end effectors](references/srdf-end-effectors.md), [collisions](references/srdf-disabled-collisions.md), [ledger](references/srdf-ledger.md) |
| **MuJoCo model by hand** | The MJCF (`robot.xml`, and a `scene.xml` that includes it), then `cad mjcf validate --compile required`. | [Authoring](references/mjcf-authoring.md), [checks](references/mjcf-checks.md) |
| **Link meshes from a CAD model for a hand-written file** | One mesh per link in the link's frame: `cad model export <id> link.stl`. | [Meshes](references/meshes.md) |
| **Mass, center of mass, inertia** | Materials on the CAD parts (generated, exact), `mass()` where the hardware's weight is measured and `point_mass()` for what the CAD leaves out; else a formula or a throwaway script, never intuition. | [Inertials](references/inertials.md) |
| **Close a nonlinear four-bar in the CAD Viewer** | `<tcad:four_bar>` on the derived URDF joint. | [Four-bar](references/urdf-four-bar.md) |
| **See the robot, a pose or a named state** | `cad urdf snapshot`, `cad srdf snapshot` or `cad mjcf snapshot`; MuJoCo Studio for the person. | [Snapshots](references/snapshots.md) |
| **Check a change** | The format's `validate` command, then its review. | [Check each change](#check-each-change) |
| **Open an existing URDF, SRDF or MJCF** | Show it to the person. | [Show the model](#show-the-model) |

## Setup

Run the `cad` command (`~/.local/bin/cad` where it is not on your PATH; `cad.exe` on Windows). If
it is missing, install text-to-cad, outside a sandbox or with its permission:

```bash
curl -fsSL https://texttocad.dev/install.sh | sh
```

On Windows, in PowerShell: `irm https://www.texttocad.dev/install.ps1 | iex`. If the CAD app was
only just added, its server may still be starting: try again for up to a minute first. `cad doctor
--check` explains any other failure, changing nothing; `cad doctor` repairs what it reports. Tell the
person any next step `cad setup` prints.

`cad doctor --check` also reports the installation in use and the server's release. Validation needs
nothing beyond the Python standard library; a snapshot and a generated description draw on the CAD
kernel. `cad mjcf validate --compile required` and `cad run mujoco-studio` use MuJoCo's headless core
and Studio's web viewer, `cad[mujoco]` (about 20 MB), which the `cad` command fetches into an
environment of its own the first time and reuses after; a script run by `cad run` that imports
`mujoco` gets the same. A part declared `collision(part, "decomposed")` uses CoACD, `cad[coacd]`
(one wheel, about 3 MB), which the engine likewise fetches into an environment of its own the first
time a part is decomposed, and reuses after. `cad <verb> --help` gives the complete current interface.

## Generate from CAD

The CAD model declares what the geometry determines, and the writers turn it into each format.
Everything below is written in the model's body (the `cad` skill's kinematics reference has the
mechanism):

- **The mechanism** is the links and joints: build123d's `RevoluteJoint`, `LinearJoint`,
  `CylindricalJoint` and `BallJoint` connected with `connect_to`. The as-built pose is every joint's
  zero in the description, and each joint's limits are its range around that zero. Where the robot
  has a controller, the description's zero is the controller's zero, so that a joint value means the
  same in the simulator and on the hardware; where none exists yet, build the mechanism at the pose a
  simulator should start from (fingers open, arm straight). A vendor's STEP is often drawn at its
  controller's zero: its published ranges fit the swept stops around the pose drawn (the vendor-STEP
  recipe's step 7 says how to tell). Where the controller's zero is another pose, name that pose a
  mechanism state and export with `--zero <state>`: every body stands as the state poses it, each
  joint counts from there (its limits and the other states shifted with it), and the CAD stays as
  drawn. Where the hardware's stops are the parts meeting, find them from the parts:
  `cad model ranges <id>` turns or slides each joint alone until its child link meets its parent and
  prints each stop, in degrees or millimetres around the as-built pose; write them into the joint's
  `angular_range` or `linear_range`, rounded towards zero, and run the model again (the `cad` skill's
  Joint stops section has the options). A servo's own travel, narrower than that, is the datasheet's.
  A joint `ranges` finds clear all the way round (a wrist roll) has no stop in the parts. Give it
  the actuator's own travel from its datasheet (a position servo's one turn, `angular_range=(-180,
  180)` around the pose its encoder centres on), which is a limited hinge in MJCF and a `revolute`
  in URDF. Where the hardware turns without end (a slip ring, a wheel), use `angular_range=(-math.inf,
  math.inf)`: a hinge with no range in MJCF, a `continuous` joint in URDF.
- **The base link.** Name the link the robot stands on `base_link` (`link(base, "base_link")`), the
  frame ROS tools expect. Where that link has a mass or stands off the world's origin, the URDF
  roots at an empty `base_footprint` on a fixed joint above it, as REP 105 roots a base, because
  KDL takes no inertia on the root; `base_link` keeps its name and stays the robot's base frame. A
  root of another name gets an empty `base_link` above it instead.
- **Mechanism states** (`mechanism_state(assembly, "home", ...)`) are the named poses, MJCF keys
  (a URDF holds no poses). Name one `home`, the pose a person and a controller start from: the zero
  itself where the hardware starts there, another state where it does not.
- **Couplings** (`gear_pair`, `rack_and_pinion_pair`) are a follower joint on its leader: MJCF's
  `<equality><joint>`, URDF's `<mimic>`. Two slides a pinion drives (a parallel gripper) couple
  through a `RevoluteJoint` on the palm connected to nothing, named first in the
  `rack_and_pinion_pair`, where the CAD draws no pinion: the file has no body or joint for it, and
  the second slide follows the first, one control as on the hardware.
- **Closed loops** (a four-bar, a slider-crank): connect the joints of a tree from the ground,
  then pair the loop's last joint by label where both parts already stand. The MJCF closes the
  loop there with an equality between a site on each body (a hinge two `connect`s, a ball one;
  where the last joint is a slide, at the loop's nearest hinge or ball instead); the URDF leaves
  that joint out and says so. A loop's joints have no named pose and no stops from `cad model
  ranges`.
- **Materials** (`bd_materials`, `part.material = metals.aluminum()`) give each part a density, so
  each link's mass, centre of mass and inertia tensor are the kernel's, exact. A part with no material
  weighs nothing, and a link of such parts has no inertial ([Inertials](references/inertials.md)).
- **`mass(part_or_assembly, grams)`** is what the hardware weighs (a scale's reading, a datasheet's):
  the solids below it keep their densities' ratios (one density for all where none of them has a material; a part with no material among parts that have one carries none of the total, and the export says so) and are
  scaled alike to make up `grams`, so the centre of mass and the inertia's shape stay the geometry's.
  An inner `mass()` fixes its own subtree; an outer one scales only the solids no inner one holds.
- **`point_mass(part, grams, at, name=, inertia=)`** is a lump the CAD leaves out (a motor inside a
  filled housing), at `at` in the part's own frame, no inertia of its own unless `inertia=(ixx, iyy,
  izz)` (kg*m^2) gives it. A `mass()` above it counts it: the lumps are fixed and the solids make up
  the rest, and a total the lumps reach or pass is refused.
- **`collision(part, kind)`** says what a simulator collides a part as: `mesh` (the default, which
  MuJoCo hulls), a `box`, `sphere`, `cylinder` or `capsule` the kernel fits to the part,
  `decomposed`, or `none`. On an assembly it applies to every part below it that declares none.
  `decomposed` is for a concave part whose one hull would fill its pocket or the gap between a
  gripper's jaws: CoACD cuts its mesh into convex hulls, each a collision geom of its own (MJCF and
  URDF alike, `<part>_hull<i>`), while the visual stays whole. `max_hulls=` caps the count (16 by
  default, `None` for no limit) and `threshold=` (0.01 to 1, CoACD's 0.05 by default) is the concavity
  it leaves: smaller cuts finer. A hull's corners lie on the part, but its faces bridge the part's
  concave places by a few millimetres on a large part, at any threshold: two links that nearly touch
  there overlap at rest as hulls (the vendor-STEP recipe's step 5 says what to do). The engine fetches `cad[coacd]` on first need; the export is refused,
  naming the part and the extra, only where CoACD has no wheel (an Intel Mac, Windows on ARM, a musl
  Linux) or no engine runs to fetch it.
  The hulls are cached by the part's mesh and options, so only a changed part decomposes again; the
  first export decomposes every part, from a few seconds to about a minute each by its size and the
  machine, and says one that reached its cap (CoACD merged hulls to fit): look at the hulls with
  `cad mjcf snapshot sim/scene.xml tmp/collision.png --display collision`.
- **`frame(part, name, location)`** names a frame on a part (a tool point, a camera mount, a sensor),
  in the part's own frame, the one its geometry is in before it is placed; it is a site in MJCF.
- **`body(part, name=None)`** keeps a part a body of its own, fixed to the link it would merge into (a
  camera mount, a fingertip the simulator addresses), with its own mass and geoms.
- **`exclude(a, b)`** says two parts (or assemblies) never collide, one given as the shape and the other
  as the shape or its label. A shape names that shape alone, wherever it is placed, however many parts
  share its label (a vendor STEP repeats labels: a bracket in each hip); a label names every part at or
  below a node of that label, in every link. `cad model ranges` sets the same pair aside (one declaration
  for both, with no form for one alone). The MJCF excludes every
  jointed pair whose collisions touch at rest by itself, the first joint's on a world-welded base too.
- **`limits(assembly, joint, effort=, velocity=, armature=, damping=, friction=)`**: a joint's drive
  limits, N*m or N and rad/s or m/s, the URDF's `<limit>` and MJCF's `actuatorfrcrange`, and
  its dynamics: the rotor's reflected inertia (kg*m^2, kg), viscous damping (N*m*s/rad, N*s/m) and dry
  friction (N*m, N), MJCF's `armature`, `damping` and `frictionloss` and URDF's `<dynamics damping
  friction>` (URDF has no armature: the export's log says it is left out). Without a drive limit a URDF
  says `effort="0" velocity="0"`, which a ROS controller reads literally; a joint given only one of
  the two has the other written 0, and the export's log names it. Actuators, gains and contact
  tuning are the scene's.
- **`friction(part_or_assembly, coefficient)`** is the contact friction of a part's surface, set where
  its material is and inherited as one is: a sliding coefficient (MuJoCo keeps its torsional and
  rolling defaults) or the three. MJCF writes it on the part's collision geoms; URDF has none (said in
  the export's log). Where none is declared, nothing is written and the simulator's default holds:
  never invent a coefficient for a material.
- **`free(assembly)`** says the robot is not bolted to the world (a humanoid, a quadruped, a mobile
  base, a part dropped on a table): on the top assembly, its base floats, an MJCF `<freejoint>` (its
  seven values in every key, the base where it stands) and a URDF's root, which floats already. The
  floating base's frame stands at its link's centre of mass, its axes the model's: a humanoid's at its
  torso, not on the floor between its feet, so a key's first three values and the simulator's base
  position read where the base is (a URDF fixes it to an empty root at the model's origin, `base_link`,
  or `base_footprint` where the base is named `base_link`). Mount an IMU or a camera on a `frame()` of
  the torso's part, not on the base frame. Bolted is the default, an arm on a bench. On a part or a sub-assembly of a model with no joints, that
  node's body alone floats.
- **`link(part_or_assembly, name)`** names the link its parts make (`base_link`, `upper_arm_link`)
  where the first part's label is not the name a consumer wants. A link otherwise takes its jointed
  assembly's label (the `Compound` that holds its joint), else its first part's; a body is named by
  `body()`. Two links of one name, or one link's parts declaring two, are refused by name.

```python
from cad.build123d import body, collision, exclude, frame, free, friction, limits, link, mass, point_mass

collision(palm, "box")
frame(palm, "tcp", bd.Pos(0, 0, 65))   # mm, in the palm's own frame
body(camera, "camera")                 # fixed to the palm, a body of its own
exclude(left, right)                   # the fingers touch when closed
limits(root, "left", effort=2, velocity=1.5, armature=0.002, damping=0.1)   # N*m, rad/s, kg*m^2, N*m*s/rad
point_mass(palm, 120, bd.Pos(0, 0, 20), name="motor")   # g, mm in the palm's own frame
mass(palm, 410)                        # g: the palm as weighed, its motor included
friction(pads, 1.1)                    # the pads' rubber, sliding
link(palm, "base_link")                # the palm's link, named as ROS names a base
free(root)                             # on a mobile base: not bolted to the world
```

Then run the model, find its stops where they are the parts' (`cad model ranges`), and write the
file from the document the run left in the server (`$ID` is the `id:` line the run printed); the
suffix picks the format, and the meshes are written as binary STL
in metres beside it:

```bash
cad run src/gripper.py
cad model ranges "$ID"
cad model export "$ID" sim/gripper.xml
cad model export "$ID" description/gripper.urdf --zero home
cad step export vendor/part.step sim/part.xml
```

Each robot export says what it wrote after the file's line: its links and how its base stands, its
joints by kind, its total mass, then its couplings, loops, frames, collisions by kind, the contact
excludes the file holds (`6 contact excludes (1 declared, 5 automatic)`: yours, and the jointed pairs
touching at rest), keys and zero; every warning (a link with no mass, a joint left out) is a line of the export's log
before it. `--json` gives the same as the file row's `robot`. Read it before anything else: a mass of
0, a link you did not expect or a missing joint is a model to fix.

An MJCF export to `sim/gripper.xml` writes `sim/scene.xml` beside it when there is none: MuJoCo
Menagerie's scene, which includes the robot's file and adds a floor, a light and a skybox, so `cad run
mujoco-studio --model sim/scene.xml` opens it standing on something. The scene is yours to edit
(actuators, cameras, other bodies); an export never writes over it and says it kept it. The robot's
file is the one an export writes again. **The generated MJCF has no actuators**: nothing drives or
holds its joints until the scene adds one per joint, which takes a few lines in `scene.xml`
([actuators in the scene](references/mujoco-environment.md#actuators-in-the-scene)).

A generated MJCF is laid out as MuJoCo Menagerie lays out a robot (radians, `meshdir="assets"`,
`autolimits`, `implicitfast`, a `visual` class in group 2 that collides with nothing and a
`collision` class in group 3, explicit `<inertial>`s, a site per frame, a key per state); what each
format drops is in [Interoperability](references/interoperability.md#one-description-two-writers).
It holds no floor, light, actuator, sensor or solver setting: those belong to the scene (the
`scene.xml` written beside it, or your own) and the consumer. A STEP has no mechanism: each of its top-level parts is a body hung fixed from the world. A robot's
STEP is articulated in a model first ([from a vendor STEP](references/from-a-vendor-step.md)).
In code, `from cad.mujoco import spec` makes a model call's handle, a build123d shape, a `.step`,
an `.xbf` or an MJCF path (a Menagerie robot) into a `mujoco.MjSpec`, MuJoCo's own editable model,
with its files named by absolute path. Everything after that is native MuJoCo: `scene.attach(spec(gripper(), assets="sim/assets"), prefix="gripper/", site=...)`,
`add_body`, `add_freejoint`, `add_actuator`, `add_key`, `compile()`, `to_file()`. There is no other
wrapper. [MuJoCo environment](references/mujoco-environment.md) walks through one, with what is
generated, what the scene decides and what the consumer owns.

- **Never edit a generated file.** A change to a frame, a limit, a mass or a mesh is a change to the
  model: edit it, run it, export again. What the geometry does not determine (actuators, sensors, a
  floor, solver settings, a Menagerie arm) goes in the scene script, which rebuilds the scene from
  the regenerated pieces.
- **Check what the kernel cannot know**: that each joint's positive motion is the one intended, and
  that the collision kinds suit the physics. A generated file can still have its joint signs wrong
  if the model does.

## How the formats fit together

- **URDF** owns physical robot structure: links, joints, geometry, inertials, limits, mimic
  joints, transmissions, and robot-state publishing.
- **SRDF** owns MoveIt semantics on top of a valid URDF: virtual joints, passive joints, planning
  groups, group states, end effectors, and disabled collision pairs. It pairs with its URDF by
  colocation and robot name alone: same folder, same `<robot name>`, exactly one such URDF.
- **MJCF** owns a MuJoCo model: bodies, joints, geoms, default classes, actuators, equalities and
  keyframes, in one file or a `scene.xml` that includes the robot's.
- **Meshes** are owned by the CAD workflow: a generated description writes them itself, and a
  hand-authored one takes one asset per link, exported in that link's frame, its source units
  recorded. Fix a wrong export there, never with URDF origins or MJCF body positions.

Names are identifiers every consumer shares: SRDF groups, controllers and TF read the URDF's link
and joint names, so a rename updates every consumer in the same task, and any URDF edit re-runs
`cad srdf validate` on the SRDF beside it ([Interoperability](references/interoperability.md)).

## Rules for every format

1. Identify the target consumers first: RViz, robot_state_publisher, MoveIt, a real robot driver,
   MuJoCo or another simulator, and how strict they are.
2. Before writing XML by hand, establish the ledger (frames, joints, geometry, units, assumptions)
   and keep it as a comment block at the top of the file. Update it in the same edit that changes
   the modeled facts; a stale ledger is worse than none. A number the kernel computed is not
   ledgered: it is regenerated. A generated file has no ledger; the model is its source.
3. SI units: meters, kilograms, seconds, radians, unless the target explicitly requires otherwise.
   URDF limits and SRDF group states never hold degrees; an MJCF says `<compiler angle="radian"/>`,
   since MuJoCo's default is degrees. These are the files' units: a snapshot's `--pose` takes
   degrees (metres for a slide), as `cad model snapshot` does
   ([Check each change](#check-each-change)).
4. Do not infer spatial transforms, mesh units, handedness, axes, joint signs or planning
   semantics from vague prose or visual impression. Use CAD transforms, dimensioned drawings,
   measured values, existing source data, simulator documentation, or explicit documented
   assumptions ([Guardrails](references/guardrails.md)).
5. Never freehand computed numbers (inertia tensors, centers of mass, unit conversions across many
   links, mirrored transforms, adjacency lists). Where a CAD model exists, generate them from it;
   otherwise compute them with closed-form formulas or a throwaway helper script. A helper is
   scaffolding; for complex or parametric models it may be kept on disk beside related model source
   and named in the ledger, and the checked-in XML stays canonical: regenerating is an explicit
   editing action, never an implicit build step.
6. Never encode a kinematic fix by offsetting only a visual mesh; correct the link and joint
   frames, unless the mesh is genuinely offset from its link frame.
7. Regenerate upstream geometry, mesh and robot-description assets with their owning workflows
   before editing a description that references them.
8. Check every created or modified file ([below](#check-each-change)) and report the checks run,
   the checks skipped, the assumptions and the risks
   ([report shape](references/guardrails.md#the-report)).

## Author by hand

Each section below is a format written directly. For a robot that has a CAD model here, generate the
URDF or MJCF instead ([above](#generate-from-cad)) and author only what it does not carry: the
SRDF, a MuJoCo scene.

### URDF

The robot's tree of links and joints. Most URDF errors are frame errors: a joint's `<origin>` is
the parent-link-frame transform to the joint frame at zero position, the child link frame
coincides with the joint frame, `<axis>` is expressed in the joint frame, and the `visual`,
`collision` and `inertial` origins are each expressed in the link frame, independently
([Frames](references/urdf-frames.md)).

1. Identify the `.urdf` and its consumers; read or create the ledger
   ([URDF ledger](references/urdf-ledger.md)).
2. Prepare mesh assets first when links reference meshes ([Meshes](references/meshes.md)).
3. Author the XML per the [authoring contract](references/urdf-authoring.md): links in tree order,
   then joints; physical links carry `inertial`, `visual`, `collision` as the consumer needs them;
   frame-only links (`base_footprint`, `tool0`, optical frames) are empty and listed as frame-only
   in the ledger.
4. Joint types `fixed`, `revolute`, `continuous`, `prismatic` (the validator rejects `floating`
   and `planar`). Revolute limits in radians, prismatic in meters, no lower/upper on
   `continuous`. Every movable joint has a stated positive-motion convention; the axis sign is part
   of the model.
5. Compute the inertials ([Inertials](references/inertials.md)).
6. Check it ([URDF checks](references/urdf-checks.md)): `cad urdf validate`, `check_urdf` when
   installed, then the viewer sweep of every movable joint.

### SRDF

MoveIt planning semantics for an existing valid URDF. The common failure is not invalid XML but a
plausible SRDF with the wrong planning group, tool link, default state, disabled-collision matrix
or joint units. Derive groups, end effectors, states and disabled collisions from the URDF
topology, MoveIt Setup Assistant output, sampled collision analysis, or explicit user data; never
type a link or joint name from memory.

1. **Start from a valid URDF** (`cad urdf validate`), and **extract its table**: robot name, links,
   joints with type, parent, child, limits and mimic flags. Copy every name from it
   ([SRDF authoring](references/srdf-authoring.md#extract-the-urdf-table)).
2. **Identify the planning task**: arm IK, gripper control, mobile base, dual-arm, tool use, or
   local smoke testing. Create or update the [planning ledger](references/srdf-ledger.md) and keep
   a compact copy as a comment block in the `.srdf`.
3. **Pair by colocation**: the `.srdf` in the URDF's folder with the same `<robot name>`. No
   metadata element links the files.
4. **Virtual and passive joints** deliberately, only when the robot model needs them.
5. **Planning groups from URDF topology**: a chain for a serial manipulator whose base and tip form
   a real parent-to-child path (the validator verifies it); joint, link or subgroup members only
   when deliberate.
6. **End effectors** after group membership is known: no links shared with the parent group, and
   the actual target/TCP link recorded ([End effectors](references/srdf-end-effectors.md)).
7. **Group states in URDF-native units**: radians for revolute and continuous, meters for
   prismatic, within URDF limits, never setting fixed, mimic or passive joints.
8. **Disabled collisions from evidence**: URDF adjacency, Setup Assistant sampling, or a
   user-provided matrix, each pair with a truthful reason and provenance; no broad invented lists
   ([Disabled collisions](references/srdf-disabled-collisions.md)).
9. Check it ([SRDF checks](references/srdf-checks.md)), and report incomplete validation, a missing
   MoveIt environment, manually reasoned disables, and inferred target links.

### MJCF

A MuJoCo model, MuJoCo's XML (`<mujoco>` at its root). The traps are units and defaults: MuJoCo reads
angles in degrees unless `<compiler angle="radian"/>` says otherwise (a keyframe's `qpos` is radians
whatever it says), and a geom or joint takes attributes from the default class it falls under.

1. Identify the consumer (MuJoCo's version, a training stack, a viewer) and whether the robot has a
   URDF to start from ([Interoperability](references/interoperability.md#mjcf)).
2. Split the robot from its world: `robot.xml` with no floor or light, and `scene.xml` that
   `<include>`s it and adds them ([MJCF authoring](references/mjcf-authoring.md)).
3. Set `<compiler angle="radian" meshdir="assets" autolimits="true"/>` explicitly; give the robot
   `<default>` classes, a `visual` one and a `collision` one, and `childclass` on its root body.
4. A body with no joint is welded to its parent; a floating base gets `<freejoint/>`. Leave inertia
   to the compiler from the geoms where it can, else compute an `<inertial>` ([Inertials](references/inertials.md)).
5. Ship a `<key name="home">` whose `qpos` (and `ctrl`) is the model's length.
6. Check it ([MJCF checks](references/mjcf-checks.md)): `cad mjcf validate --compile required`, then
   a snapshot of `home` and of each joint moved.
7. Clear every model-health warning the compile reports before tuning any physics, then tune one
   parameter at a time from a baseline, validating after every write
   ([Tuning](references/mujoco-environment.md#tuning)).

## Check each change

Each format has its validator and its snapshot; a generated file is checked like a hand-written one:

```bash
cad urdf validate path/to/robot.urdf
cad urdf validate path/to/robot.urdf --packages robot_description=/path/to/pkg
cad srdf validate path/to/robot.srdf --strict
cad mjcf validate path/to/scene.xml --compile required
cad mjcf validate path/to/scene.xml --compile required --strict --json
cad urdf snapshot path/to/robot.urdf review.png --pose '{"shoulder_pitch": 30}'
cad srdf snapshot path/to/robot.srdf review.png --pose arm/ready
cad mjcf snapshot path/to/scene.xml review.png --pose home
cad run mujoco-studio --model path/to/scene.xml
```

A snapshot's `--pose` takes a turn in degrees and a slide in metres, though the file holds
radians: `{"shoulder_pitch": 30}` is 30 degrees, and 0.5 is half a degree, drawn as if at zero.

`cad run mujoco-studio` shows the person an MJCF as MuJoCo itself runs it, in MuJoCo Studio's web
viewer: it reloads the model as the file changes and prints a URL for the person to open; it comes
with `cad[mujoco]` (fetched once), and it listens on every network interface with no authentication,
so it is for this computer or a trusted network.

| Change | Check it with |
| --- | --- |
| A CAD model's mechanism, materials, `collision()`, `frame()`, `body()`, `exclude()`, `limits()`, `mass()`, `point_mass()`, `friction()`, `free()` or `link()` | Run it, export again, and validate the file (and the scene built from it); `cad model snapshot` of each mechanism state first, where the joint signs show. |
| A scene script | Run it, then `cad mjcf validate` on the scene it wrote with `--compile required`: every model-health warning cleared or explained; `--pose home` in a snapshot. |
| Any `.urdf` | `cad urdf validate` until clean; `check_urdf FILE` (liburdfdom) when installed. |
| A joint origin, axis, sign or limit | The viewer sweep: every movable joint through its limits against the ledger's positive-motion statement, or snapshots at `--pose` values. The only check that catches a flipped sign. |
| A mesh, its scale or its placement | A snapshot: meshes at sane scale and pose; ~1000x too large or small is a `scale` bug. |
| An inertial | The [sanity gates](references/inertials.md#sanity-gates). |
| Any `.srdf` | `cad srdf validate` (it cross-checks every name, chain, state and pair against the paired URDF); named states in a snapshot (`--pose group/state`). |
| A URDF with an SRDF beside it | `cad srdf validate` on that SRDF again, and its group states against the new limits. |
| Any MJCF | `cad mjcf validate --compile required` (MuJoCo's own compiler and the model-health checks, fetched once as `cad[mujoco]`); the `home` key in a snapshot (`--pose home`). |
| MuJoCo physics (solver, contacts, gains) | The tuning loop: one parameter changed, validated, and run in MuJoCo Studio against the baseline ([Tuning](references/mujoco-environment.md#tuning)). |
| A MoveIt or ROS consumer | Its own load when available: RViz, robot_state_publisher's TF tree, MoveIt Setup Assistant (IK for the primary group, plan to a named state). |

- One run validates ONE file and collects every finding (severity, code, XML path) with a summary.
  `--strict` treats warnings as failures; `--json` prints one line of `{"ok", "path", "findings":
  [{"severity", "code", "message", "location", "hint"}], "summary"}`, where `location` is the XML
  path. It exits 1 if the target fails its checks, and 2, with nothing checked, for a command line
  it refuses -- a file of another format, one that is not there, an option or a value it does not
  take (`--compile` is `auto`, `required` or `never`) -- which `--json` says as one
  `{"ok": false, "error", "reason"}`. Relative targets resolve from the working directory: run
  from the workspace that owns the files.
- A clean check is a guardrail, not proof: it cannot show that a joint origin or axis matches the
  robot, that mesh units match `scale`, that a planning group matches the task, or that a gain is
  right. Say which validator or smoke test passed, never just that the file
  is valid.
- Fix the owning file: the CAD model for anything generated, the URDF for hand-written structure,
  the CAD workflow for a bad mesh export, the scene script for what the scene adds; then re-run the
  check from the top. Report a project-policy failure as policy, not invalidity.
- A file you write is the robot's model, not an export: show it. Visual review cannot prove
  planning correctness or dynamics; the viewer does not play a simulation. Report which checks ran and which were skipped.

## Show the model

Show the person each model you create or change, and any model or file they ask to see. If your
tools include `cad_show` (your host may prefix it), call it with the model's id or the file's
absolute path; its description says the rest. Otherwise give the person the page's link once, to
open in the app's browser pane where it has one, or their browser: a model's page is the `view:` line its run prints, and a file's is the `url` that
`cad viewer --json FILE [FILE ...]` prints for it (never guess the port). A file you export is a
download: give its path. Never screenshot the viewer to check your own work; review with
`cad <type> snapshot`. If it fails to launch, say so.
