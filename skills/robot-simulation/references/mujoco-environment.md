# A MuJoCo environment from CAD

Use this reference to put CAD-made parts into a MuJoCo simulation: a mechanism written as an MJCF
from its model, then a scene composed in code from those pieces, a Menagerie robot and whatever the
simulation adds, checked, shown to the person, and tuned. Hand-written MJCF is
[mjcf-authoring.md](mjcf-authoring.md); every finding the checks print is in
[mjcf-checks.md](mjcf-checks.md).

## Contents

- [What comes from where](#what-comes-from-where)
- [The model](#the-model)
- [The generated MJCF](#the-generated-mjcf)
- [The scene in code](#the-scene-in-code)
- [Check and show the scene](#check-and-show-the-scene)
- [Tuning](#tuning)
- [What is not supported](#what-is-not-supported)

## What comes from where

A simulation is three kinds of fact, each with one owner. Put each where it belongs and nothing is
written twice:

| Determined by geometry (generated) | Decided in the scene (native `MjSpec`) | The consumer's own |
| --- | --- | --- |
| Links and their frames, joint axes, joint limits around the as-built zero | Where each piece stands, and what it is attached to (a frame, a site) | Actuators: kind, gains, control ranges |
| Masses, centres of mass, inertia tensors (materials' densities) | A free body (`add_freejoint`) for a part that moves loose | Sensors |
| Visual meshes (STL, metres) and their colours | The floor, lights, cameras | Solver settings: timestep, cone, `impratio`, `solref` |
| Collision shapes (`collision()`), named frames as sites (`frame()`) | Robots from elsewhere (Menagerie), and the prefixes that keep their names apart | Joint armature and damping, friction, `condim` |
| Couplings as `<equality><joint>`, mechanism states as keys | The scene's own `home` key over every joint | Controllers, policies, the simulation loop |

The first column is regenerated from the model on every change, never edited. The second and third
are written in the scene script, so the scene is rebuilt from the regenerated pieces and keeps its
own decisions. The third is still the scene script's text, but its numbers come from the robot's
data sheet and the tuning below, not from the CAD.

## The model

A two-finger gripper whose fingers turn together, and a block to pick up. The fingers are built
open, which is every joint's zero in the description; the coupling makes the right finger the
left's follower; the materials give every link its mass; `collision()` makes each part a fitted
box; `frame()` names the tool point:

```python
# src/gripper.py
import build123d as bd
from bd_materials import metals, plastics
from cad import model
from cad.build123d import collision, frame, gear_pair, mechanism_state

CLOSE = 20  # degrees each finger turns from open to closed


@model
def gripper():
    palm = bd.Box(60, 30, 20, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    palm.label = "palm"
    palm.material = metals.aluminum()
    collision(palm, "box")
    frame(palm, "tcp", bd.Pos(0, 0, 65))   # between the fingertips, in the palm's own frame (mm)
    fingers = []
    for name, x, limits in (("left", -20, (0, CLOSE)), ("right", 20, (-CLOSE, 0))):
        finger = bd.Pos(x, 0, 20) * bd.Box(10, 20, 50, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
        finger.label = name
        finger.material = plastics.pom()
        collision(finger, "box")
        pivot = bd.Axis((x, 0, 20), (0, 1, 0))   # +angle turns the left finger in
        bd.RevoluteJoint(name, palm, axis=pivot, angular_range=limits)
        bd.RigidJoint(name, finger, bd.Plane(origin=pivot.position, z_dir=pivot.direction).location)
        palm.joints[name].connect_to(finger.joints[name], angle=0)   # as built: open
        fingers.append(finger)
    assembly = bd.Compound(children=[palm, *fingers], label="gripper")
    gear_pair(assembly, "grip", left=CLOSE, right=-CLOSE)   # 0 open, 1 closed
    mechanism_state(assembly, "home", grip=0)
    mechanism_state(assembly, "closed", grip=1)
    return assembly


@model
def block():
    body = bd.Box(40, 40, 40, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    body.label = "block"
    body.material = plastics.pla()
    collision(body, "box")
    return body


if __name__ == "__main__":
    gripper()
    block()
```

- **Build at the simulator's zero.** A joint's value in the description is its turn or slide from
  where it was built, and its limits are its range less that value: a finger built at 30 degrees in
  a range of 0 to 40 is a hinge of range -30 to 10 degrees, in radians. Build open, straight or
  homed, and the MuJoCo values are the CAD's.
- **Declare on finished parts**, after the last operation, as a material is set: `collision()` and
  `frame()` travel with the part as build123d moves it, and a copy keeps them. `collision()` on an
  assembly is every part's below it that declares none. A frame is a part's, never an assembly's.
- **Collision kinds.** `box`, `sphere`, `cylinder` and `capsule` are fitted by the kernel to the
  part's oriented bounding box (a cylinder's and a capsule's axis its longest side): fast and stable,
  and as wrong as the box is for a part far from its shape. `mesh` (the default) is the part's own
  mesh, which MuJoCo collides as its convex hull. `none` for a part that only shows (a cover, a
  label). Split a concave part that must collide as itself into convex parts in the model.
- **Check the signs in CAD first**: `cad model snapshot "$ID" tmp/closed.png --pose closed`. The
  writers copy the mechanism's signs; they cannot know which way is meant.

## The generated MJCF

```bash
cad run src/gripper.py
cad model export "$ID" sim/gripper.xml
cad mjcf validate sim/gripper.xml --compile required
```

`$ID` is the gripper's `id:` line from the run. The export writes `sim/gripper.xml` and its meshes,
`sim/assets/gripper_palm.stl` and `gripper_left.stl` (the right finger is the same prototype, so
one mesh serves both). The file, abridged:

```xml
<mujoco model="gripper">
  <compiler angle="radian" meshdir="assets" autolimits="true"/>
  <option integrator="implicitfast"/>
  <default>
    <default class="gripper">
      <default class="visual">
        <geom contype="0" conaffinity="0" group="2"/>
      </default>
      <default class="collision">
        <geom group="3"/>
      </default>
    </default>
  </default>
  <asset>
    <material name="Alu_G6061_T6" rgba="0.962100154 0.96539993 0.965800074 1"/>
    <mesh name="palm" file="gripper_palm.stl"/>
    ...
  </asset>
  <worldbody>
    <body name="palm" childclass="gripper">
      <inertial pos="0 0 0.01" mass="0.0972" diaginertia="1.053e-05 3.24e-05 3.645e-05"/>
      <geom class="visual" type="mesh" mesh="palm" name="palm" material="Alu_G6061_T6"/>
      <geom class="collision" type="box" size="0.015 0.03 0.01" name="palm_collision" pos="0 0 0.01" .../>
      <site name="tcp" pos="0 0 0.065"/>
      <body name="left" pos="-0.02 0 0.02" quat="0.5 -0.5 -0.5 -0.5">
        <inertial pos="0.025 0 0" mass="0.0141" diaginertia="5.875e-07 3.4075e-06 3.055e-06"/>
        <joint name="left" type="hinge" axis="0 0 1" range="0 0.34906585"/>
        ...
      </body>
      ...
    </body>
  </worldbody>
  <equality>
    <joint joint1="right" joint2="left" polycoef="0 -1 0 0 0"/>
  </equality>
  <keyframe>
    <key name="closed" qpos="0.34906585 -0.34906585"/>
    <key name="home" qpos="0 0"/>
  </keyframe>
</mujoco>
```

What to read in it:

- **Bodies.** The ground link (the parts no joint moves, here the palm) is a body with no joint, so
  it is welded to whatever it is attached to; every other link is a body standing at its joint's
  frame, the joint on that frame's Z (`axis="0 0 1"`) with `ref` zero. A revolute joint is a `hinge`
  (with its range, or without for a continuous one), a slide a `slide`, a cylindrical one a hinge and
  a slide on one body (`<name>` and `<name>/slide`), a ball joint a `ball`.
- **Inertials** are explicit, on their principal axes, from the solids at their materials'
  densities: 60 x 30 x 20 mm of aluminium at 2700 kg/m^3 is the palm's 0.0972 kg. A link whose parts
  have no material has no `<inertial>`, and MuJoCo then weighs its visual and collision geoms both
  (`inertia_from_visuals`): give the parts materials.
- **Geoms.** Each part is a `visual` geom of its mesh and a `collision` geom named `<part>_collision`
  in MuJoCo's half sizes; the classes keep visuals out of contacts and out of group 3.
- **Sites** are the `frame()`s, in their link's frame, in metres.
- **The coupling** is an equality: `right = 0 + -1 * left`.
- **Keys** are the mechanism states, each joint's value in radians or metres from the as-built
  zero, a follower where its leader puts it. No `ctrl`: the file has no actuators.
- **Not in it**: a floor, a light, actuators, sensors, solver settings beyond the integrator. A
  scene adds them.

The robot file alone validates with `defaults_not_recommended` (a pyramidal cone, the default
`solref`) and `mass_summary` as infos: solver settings are the scene's, so they are expected here.

## The scene in code

`from cad.mujoco import spec` turns each CAD piece into a `mujoco.MjSpec`, MuJoCo's own editable
model, holding the same bodies, classes, equalities and keys the export holds. Everything else is
MuJoCo's own API, used directly: `MjSpec.from_file`, `attach` with a `prefix` and a `site` or a
`frame`, `add_body`, `add_geom`, `add_joint`, `add_freejoint`, `add_site`, `add_camera`,
`add_light`, `add_key`, `add_actuator`, `add_sensor`, `add_equality`, `compile`, `to_file`. The
scene script is the one script that writes the scene, as `exports.py` is the one that writes files:

```python
# src/scene.py
# /// script
# dependencies = ["mujoco-menagerie"]
# ///
import mujoco
import mujoco_menagerie
from cad.mujoco import spec

from gripper import block, gripper

HOME_ARM = [0, 0, 0, -1.57079, 0, 1.57079, -0.7853]   # Menagerie's Panda home, radians


def build(hand, part) -> mujoco.MjSpec:
    scene = mujoco.MjSpec()
    scene.modelname = "pick"
    scene.compiler.degree = False   # radians
    scene.option.integrator = mujoco.mjtIntegrator.mjINT_IMPLICITFAST
    scene.option.cone = mujoco.mjtCone.mjCONE_ELLIPTIC
    scene.option.impratio = 10
    scene.option.timestep = 0.002
    scene.worldbody.add_light(pos=[0, 0, 2], dir=[0, 0, -1], type=mujoco.mjtLightType.mjLIGHT_DIRECTIONAL)
    scene.worldbody.add_geom(name="floor", type=mujoco.mjtGeom.mjGEOM_PLANE, size=[0, 0, 0.05])

    # The arm at the origin, the CAD gripper on its flange, the CAD block loose on the floor.
    panda = mujoco_menagerie.get("franka_emika_panda").path() / "panda_nohand.xml"   # the arm without its hand
    scene.attach(spec(panda), prefix="panda/", frame=scene.worldbody.add_frame())
    scene.attach(spec(hand, assets="sim/assets"), prefix="gripper/", site=scene.site("panda/attachment_site"))
    scene.attach(spec(part, assets="sim/assets"), prefix="block/", frame=scene.worldbody.add_frame(pos=[0.5, 0, 0]))
    scene.body("block/block").add_freejoint(name="block/free")

    # The consumer's own: an actuator on the leading finger, a sensor, a camera, contact stiffness.
    grip = scene.add_actuator(name="gripper/grip", target="gripper/left", trntype=mujoco.mjtTrn.mjTRN_JOINT,
                              ctrlrange=[0, 0.349])
    grip.set_to_position(kp=20, kv=1)
    scene.add_sensor(name="tcp_pos", type=mujoco.mjtSensor.mjSENS_FRAMEPOS, objtype=mujoco.mjtObj.mjOBJ_SITE,
                     objname="gripper/tcp")
    scene.worldbody.add_camera(name="overview", pos=[1.4, -1.0, 0.9], mode=mujoco.mjtCamLight.mjCAMLIGHT_TARGETBODY,
                               targetbody="block/block")
    for geom in scene.geoms:
        geom.solref = [0.005, 1]   # solref[0] >= 2 x timestep

    # qpos: 7 arm hinges, the 2 finger hinges, the block's free joint (position, then quaternion).
    scene.add_key(name="home", qpos=[*HOME_ARM, 0, 0, 0.5, 0, 0, 1, 0, 0, 0], ctrl=[*HOME_ARM, 0])
    return scene


if __name__ == "__main__":
    scene = build(gripper(), block())   # the documents, built or replayed by the server
    scene.compile()   # raises with MuJoCo's message for a scene it refuses
    scene.to_file("sim/scene.xml")
```

```bash
cad run src/scene.py
```

What each step does, and the traps:

- **`spec(thing, assets=...)`** takes a model call's handle (as here), a build123d shape, a
  `.step`, an `.xbf`, or an MJCF path: an authored model, an export, a Menagerie robot (the Panda
  here). For a document it writes the meshes and the fragment's own MJCF into `assets`, a folder
  relative to the working directory (`sim/assets` beside the scene); without `assets`, into a folder
  of the engine's cache named by their content, which wiping the cache loses. `tolerance=` meshes
  the parts finer, in millimetres (a document only: an MJCF's meshes are its files).
- **Every spec names its files by absolute path.** MuJoCo resolves an attached model's meshes by
  its own folder when it compiles, but `to_file` writes them bare, so a robot read with
  `MjSpec.from_file` and attached is lost the moment the scene is saved. `spec()` names each mesh and
  texture absolutely and clears the spec's own folders, so the scene compiles and, saved anywhere,
  loads again: load a Menagerie robot through `spec()` too, never `MjSpec.from_file`. A saved scene
  that cannot find a mesh fails `cad mjcf validate` with `mesh_file_not_found`.
- **A saved scene's paths are this computer's.** It loads anywhere here, and nowhere else. A robot
  meant to travel as a folder is an export instead (`cad model export <id> robot/robot.xml`, its
  meshes relative beside it), which a scene `<include>`s, or attaches in code without saving.
- **`attach`** copies the child into the scene under a `prefix`, at a `frame` (a placement in the
  parent) or a `site` (the arm's flange). Every name of the child is prefixed (bodies, joints, geoms,
  sites, default classes, keys): `gripper/left`, `panda/attachment_site`. The child's root body has
  no joint, so it is welded where it is attached.
- **A free body.** A part with no mechanism is one body under the world; `add_freejoint` on it, after
  attaching, makes it loose. Its 7 `qpos` values are its position, then its quaternion.
- **Options.** Each piece carries its own `<option integrator>`; a scene whose integrator differs
  makes MuJoCo warn once about the conflict when attaching, and the scene's own is kept (Menagerie's
  files do the same). Set the scene's option first, as here, and the warning does not come.
- **Keys.** The children's keys come along prefixed (`panda/home`, `gripper/closed`), each padded to
  the scene's length with every other joint at `qpos0`. Give the scene its own `home` over every
  joint: `qpos` is 1 per hinge or slide, 4 per ball, 7 per free joint, in MuJoCo's joint order (the
  body tree, depth first), and `ctrl` one
  per actuator, in actuator order (the Panda's seven, then the grip). A key of the wrong length is
  no pose.
- **Composing two models of one family** of default classes is safe: classes are prefixed with the
  model, so the gripper's `visual` and the Panda's are `gripper/visual` and `panda/panda/visual`.
- **`to_zip`** writes the XML into a zip, not the mesh files it names: it is no way to ship a scene.

A robot made in the same project attaches the same way: an arm model of its own with a `frame()` on
its last link, and the gripper attached at that site (`scene.site("arm/flange")`).

## Check and show the scene

```bash
cad mjcf validate sim/scene.xml --compile required
```

On the scene above it prints:

```text
warning: joint_limits_at_rest at sim/scene.xml: 1 joint(s) lie outside their range at qpos0: joint 'panda/joint4' is 0 rad, range [-3.072, -0.0698] rad ([-176, -3.999] deg) Hint: ...
info: geom_not_drawn at sim/scene.xml <worldbody> geom 'floor': an unbounded plane (a size of 0) is not drawn by the viewer; its grid stands in for the floor
info: joint_not_posable at sim/scene.xml body 'block/block' joint 'block/free': a free joint is not posable in the viewer: body 'block/block' is drawn where it is authored
info: compiled at sim/scene.xml: compiled by MuJoCo 4.0.0: 13 bodies, 10 joints, 68 geoms, 62 meshes, 4 keyframes
info: mass_summary at sim/scene.xml: moving mass 16.27 kg in 12 moving bodies, 15 degrees of freedom (nv), 8 actuators (nu); moving geometry spans 0.622 x 0.302 x 1.12 m at qpos0
OK sim/scene.xml: MJCF 'pick', 13 bodies, 8 controls, 53 visuals, 62 mesh files, 3 keyframes
```

Read every line:

- `joint_limits_at_rest` at `qpos0` is the Panda's own (its elbow's range excludes zero, as
  Menagerie ships it); the check found nothing at `home`, so start the simulation from `home`. The
  same warning at `home` is a key to fix.
- `contacts_at_rest`, `visual_geoms_collide`, `inertia_from_visuals` and `scale_suspect` are absent:
  nothing intersects at rest, visuals do not collide, every body has its inertial, and the sizes are
  metres. Any of them present is a modelling error to fix before anything else
  ([mjcf-checks.md](mjcf-checks.md#model-health) says what to do for each).
- `defaults_not_recommended` is absent: the scene set the cone, `impratio` and `solref`.
- `mass_summary`: 16 kg moving in 15 degrees of freedom and 8 actuators, about a metre tall. A
  number off by 1000 is a unit; a count off by one is a joint or an actuator missing.

Then look at it. A still for your own review, and MuJoCo itself for the person:

```bash
cad mjcf snapshot sim/scene.xml tmp/home.png --pose home
cad run mujoco-studio --model sim/scene.xml
```

The still draws the model at `home` as the viewer reads it (the free block where it is authored).
MuJoCo Studio compiles and simulates the scene in the person's browser, reloading as `scene.xml`
changes: give the person the URL it prints. It listens on every interface with no authentication
(Studio's own limitation), so run it on this computer or a trusted network.

## Tuning

Tune only a model that is healthy: every `contacts_at_rest`, `visual_geoms_collide`,
`inertia_from_visuals`, `scale_suspect` and `joint_limits_at_rest` at `home` cleared. Each of those
is a modelling error, and no solver setting fixes one; tuning around it hides it. Then:

1. **Baseline.** The validated scene and one fixed scenario, started from `home`: the block left to
   settle, the gripper closed on it, the arm moved through one motion. Note what it does in MuJoCo
   Studio (rests still, slips, jitters, sinks into the floor, explodes).
2. **One parameter at a time**, in the scene script for what the scene owns and in the model for what
   the geometry owns. Change one, run the script, `cad mjcf validate sim/scene.xml --compile
   required` after every write, run the same scenario, and keep the change or revert it.
3. **Record** each kept change and the reason in a comment beside it in the scene script.

What to try, in the order MuJoCo's modelling guide gives:

- **Integrator** `implicitfast`: stable with damping and position actuators. Leave Euler for a
  reason only.
- **Timestep** 0.5 to 2 ms for contact-rich manipulation (5 ms at most with contacts). Halve it
  when contacts jitter or penetrate; it costs simulated time per second.
- **Contact stiffness**: `solref[0]` (the contact's time constant) at least twice the timestep, 0.004
  to 0.01 for manipulation; smaller is stiffer and needs a smaller timestep.
- **Friction cone**: `elliptic` with `impratio` 10 for grasping, so a held part does not creep out.
  Geom `friction` (sliding, torsional, rolling) and `condim` (3 by default; 4 adds torsional, 6
  rolling) on the gripper's pads when a grasp turns or rolls.
- **Joints**: `armature` (the reflected rotor inertia, from the actuator's data sheet) and a light
  `damping` on every actuated joint; both steady an implicit integrator without changing the
  motion much.
- **Actuators**: gains from the robot's data sheet (`kp`, and `kv` or `dampratio` for a position
  actuator), control ranges inside the joint's limits.

A mass, an inertia or a collision shape is never a tuning knob here: it is the model's, and changes
in the model (a material, a `collision()` kind) and is regenerated.

## What is not supported

- Reading compiled models (`.mjb`) and packages (`.mjz`), and textures: the viewer and the checks
  read the XML and its STL and OBJ meshes.
- Playing a simulation in the CAD Viewer: it opens an MJCF kinematically, with a slider per joint
  and the keys as poses. MuJoCo Studio is where a simulation runs.
- Converting between URDF and MJCF beyond what MuJoCo's own loader does with a URDF
  ([interoperability.md](interoperability.md#mjcf)). A robot with a CAD model is generated in each
  format from that model instead.
- A mechanism with a closed loop: every writer refuses it by name.
