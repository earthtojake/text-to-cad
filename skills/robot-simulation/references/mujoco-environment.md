# A MuJoCo environment from CAD

Use this reference to put CAD-made parts into a MuJoCo simulation: a mechanism written as an MJCF
from its model, its simulator's choices made in a MuJoCo function, then a scene composed in code
from those pieces, a robot made elsewhere and whatever the simulation adds, checked, shown to the person,
and tuned. Hand-written MJCF is [mjcf-authoring.md](mjcf-authoring.md); every finding the checks
print is in [mjcf-checks.md](mjcf-checks.md).

## Contents

- [What comes from where](#what-comes-from-where)
- [The model](#the-model)
- [The plain export](#the-plain-export)
- [The MuJoCo function](#the-mujoco-function)
- [The scene file](#the-scene-file)
- [The scene in code](#the-scene-in-code)
- [Check and show the scene](#check-and-show-the-scene)
- [Tuning](#tuning)
- [What is not supported](#what-is-not-supported)

## What comes from where

A simulation is three kinds of fact, each with one owner. The model carries what is true of the
machine. The robot's MuJoCo function carries what is chosen for simulating it, in MuJoCo's own API.
The scene carries the world around it. Put each where it belongs and nothing is written twice:

| The model (`cad.build123d`, regenerated) | The MuJoCo function (the robot's `MjSpec`) | The scene (a scene function, or `scene.xml`) |
| --- | --- | --- |
| Links and their frames, joint axes, joint limits around the as-built zero (or the `--zero` state) | Each part's collision shape: `fit()`, `decompose()`, or none (`s.delete` on its `collisions()`) | Where each robot stands, and what it is attached to (a frame, a site) |
| Masses, centres of mass, inertia tensors (materials' densities, `mass()` totals, `point_mass()` lumps); a free base (`free()`) | Contact friction and the other contact settings on a part's collision geoms; excluded pairs (`add_exclude`) | A free body (`add_freejoint`) for a part from elsewhere that moves loose |
| Visual meshes (STL, metres) and their colours; each part's mesh as its collision | Joint `armature`, `damping` and `frictionloss` | The floor, lights, cameras |
| Named frames as sites (`frame()`), parts kept bodies (`body()`), link names (`link()`) | Actuators: kind, gains, control ranges | Robots from elsewhere, and the prefixes that keep their names apart |
| The drive's force bound (`limits(effort=)`, `actuatorfrcrange`) | Sensors, and keys with a `ctrl` | Solver settings: timestep, cone, `impratio`, contact softness (`solref`, `solimp`) |
| Couplings as `<equality><joint>`, a loop's closing joint as `connect`s of two sites, mechanism states as keys | An equality's `solref` where a loop must hold stiffer than MuJoCo's default | The scene's own `home` key over every joint and actuator; controllers, policies, the simulation loop |

The first column is regenerated from the model on every change, never edited. The second is the
robot's own file. The third is the scene's. The
numbers in the second and third come from the robot's data sheet and the tuning below, not from the
CAD.

## The model

A two-finger gripper whose fingers turn together, and a block to pick up. The fingers are built
open, which is every joint's zero in the description; the coupling makes the right finger the
left's follower; the materials give every link its mass; `frame()` names the tool point;
`limits()` is the servo's datasheet:

```python
# src/gripper.py
import build123d as bd
from bd_materials import metals, plastics
from cad import model
from cad.build123d import frame, gear_pair, limits, mechanism_state

CLOSE = 20  # degrees each finger turns from open to closed


@model
def gripper():
    palm = bd.Box(60, 30, 20, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    palm.label = "palm"
    palm.material = metals.aluminum()
    frame(palm, "tcp", bd.Pos(0, 0, 65))   # between the fingertips, in the palm's own frame (mm)
    fingers = []
    for name, x, travel in (("left", -20, (0, CLOSE)), ("right", 20, (-CLOSE, 0))):
        finger = bd.Pos(x, 0, 20) * bd.Box(10, 20, 50, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
        finger.label = name
        finger.material = plastics.pom()
        pivot = bd.Axis((x, 0, 20), (0, 1, 0))   # +angle turns the left finger in
        bd.RevoluteJoint(name, palm, axis=pivot, angular_range=travel)
        bd.RigidJoint(name, finger, bd.Plane(origin=pivot.position, z_dir=pivot.direction).location)
        palm.joints[name].connect_to(finger.joints[name], angle=0)   # as built: open
        fingers.append(finger)
    assembly = bd.Compound(children=[palm, *fingers], label="gripper")
    gear_pair(assembly, "grip", left=CLOSE, right=-CLOSE)   # 0 open, 1 closed
    limits(assembly, "left", effort=2, velocity=1.5)        # the servo's datasheet: N*m, rad/s
    mechanism_state(assembly, "home", grip=0)
    mechanism_state(assembly, "closed", grip=1)
    return assembly


@model
def block():
    body = bd.Box(40, 40, 40, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    body.label = "block"
    body.material = plastics.pla()
    return body


if __name__ == "__main__":
    gripper()
    block()
```

- **Build at the simulator's zero.** A joint's value in the description is its turn or slide from
  where it was built, and its limits are its range less that value: a finger built at 30 degrees in
  a range of 0 to 40 is a hinge of range -30 to 10 degrees, in radians. Build open, straight or
  homed, and the MuJoCo values are the CAD's.
- **Declare on finished parts**, after the last operation, as a material is set: `frame()`,
  `body()`, `mass()` and `point_mass()` travel with the part as build123d moves it, and a copy keeps
  them; `limits()` after the joint it bounds is made. `mass()` on an assembly is all of it. A frame
  and a point mass are a part's, never an assembly's.
- **What the machine is, the model says; what a simulation chooses, the MuJoCo function says.** A
  measured weight (`mass()`), a motor the CAD leaves out (`point_mass()`) and the drive's datasheet
  limits (`limits()`) are the robot's, so they live in the CAD model and every export carries them.
  Collision shapes, contact friction, the servo's reflected inertia, damping and dry friction,
  actuators and their gains are the MuJoCo function's. `condim`, solver settings and contact softness
  are the scene's.
- **Check the signs in CAD first**: `cad model snapshot "$ID" tmp/closed.png --pose closed`. The
  writers copy the mechanism's signs; they cannot know which way is meant.

## The plain export

```bash
cad run src/gripper.py
cad model export "$ID" sim/gripper.xml
cad mujoco check sim/gripper.xml
```

`$ID` is the gripper's `id:` line from the run. The export writes `sim/gripper.xml` and its meshes,
`sim/assets/gripper_palm.stl` and `gripper_left.stl` (the right finger is the same prototype, so
one mesh serves both). It needs no MuJoCo. The file, abridged:

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
      <geom class="collision" type="mesh" mesh="palm" name="palm_collision"/>
      <site name="tcp" pos="0 0 0.065"/>
      <body name="left" pos="-0.02 0 0.02" quat="0.5 -0.5 -0.5 -0.5">
        <inertial pos="0.025 0 0" mass="0.0141" diaginertia="5.875e-07 3.4075e-06 3.055e-06"/>
        <joint name="left" type="hinge" axis="0 0 1" range="0 0.34906585" actuatorfrcrange="-2 2"/>
        ...
      </body>
      ...
    </body>
  </worldbody>
  <contact>
    <exclude body1="palm" body2="left"/>
    <exclude body1="palm" body2="right"/>
  </contact>
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
- **Geoms.** Each part is a `visual` geom of its mesh and a `collision` geom of the same mesh named
  `<part>_collision`, which MuJoCo collides as its convex hull; the classes keep visuals out of
  contacts and out of group 3.
- **Sites** are the `frame()`s, in their link's frame, in metres. A `body()` part is a child body
  with no joint.
- **Contacts.** `<contact>` excludes each pair of bodies across a moving joint whose collisions touch
  at rest (MuJoCo's `filterparent` misses the first joint's, whose parent is welded to the world;
  a free base is welded to nothing, and nothing across its freejoint is excluded).
- **The drive's force bound** is `limits(effort=)`: each joint's `actuatorfrcrange`.
- **The coupling** is an equality: `right = 0 + -1 * left`.
- **Keys** are the mechanism states, each joint's value in radians or metres from the as-built
  zero, a follower where its leader puts it. No `ctrl`: a plain export has no actuators.
- **Not in it**: a chosen collision shape, joint dynamics, actuators, sensors, a floor, a light,
  solver settings beyond the integrator. The robot's MuJoCo function adds the robot's choices
  (below); a scene adds the rest: the `scene.xml` an export writes beside the robot once (an
  `include` of the robot, a floor, a light, a skybox), yours to edit and never written over, or a
  scene in code.

The robot file alone checks with `defaults_not_recommended` (a pyramidal cone, the default
`solref`) and `mass_summary` as infos: solver settings are the scene's, so they are expected here.

## The MuJoCo function

A plain Python function, in a script beside the model, that makes the robot a `mujoco.MjSpec` with
`spec()`, makes a simulation's choices on it and returns it. The script's `__main__` saves it with
`save()`. The gripper's:

```python
# src/gripper_mujoco.py
import mujoco
from cad.mujoco import collisions, fit, save, spec

from gripper import gripper


def gripper_mujoco() -> mujoco.MjSpec:
    s = spec(gripper())

    # Collisions: a box fitted to each part's exact solid, and the pads' rubber.
    for part in ("palm", "left", "right"):
        fit(s, part, "box")
    for geom in collisions(s, "left") + collisions(s, "right"):
        geom.friction = [1.1, 0.005, 0.0001]   # sliding, torsional, rolling
    s.add_exclude(bodyname1="left", bodyname2="right")   # the fingers touch when closed

    # The servo: reflected inertia, damping and dry friction on the driven joint, then its actuator.
    left = s.joint("left")
    left.armature = 0.002          # kg*m^2: tuned, not measured
    left.damping = [0.1, 0, 0]     # N*m*s/rad
    left.frictionloss = 0.01       # N*m
    grip = s.add_actuator(name="grip", target="left", trntype=mujoco.mjtTrn.mjTRN_JOINT)
    grip.set_to_position(kp=20, dampratio=1, inheritrange=True)
    return s


if __name__ == "__main__":
    save(gripper_mujoco(), "sim/gripper.xml")
```

```bash
cad run src/gripper_mujoco.py
cad mujoco check sim/scene.xml
```

`cad run` sees the `mujoco` import and adds `cad[mujoco]`. The function's file replaces the plain
export at the same path: it is the robot's file now, actuators and all.
The run ends with what `save` checked of it:

```text
collisions: 3 collision geoms (box 3) on 3 bodies: palm 1 (box 1); left 1 (box 1); right 1 (box 1)
excludes: 3 contact excludes, each between two bodies whole: palm and left touching at rest; palm and right touching at rest; left and right 30 mm apart at rest
wrote /path/to/sim/gripper.xml
```

Read both lines against the function: three boxes, as fitted; and the exclude between the two
fingers, which stand apart when open, is the one the function added on purpose.

**`spec(thing, zero=, tolerance=, assets=)`** takes a model call's handle (as here), a build123d
shape, a `.step`, an `.xbf`, or an MJCF path: an authored model, an export, a robot made elsewhere.
`zero=` takes a document's robot at a mechanism state, as an export's `--zero` does; `tolerance=`
meshes its parts finer, in millimetres; `assets=` writes its meshes into a folder relative to the
working directory instead of the engine's cache (a document only, for each of the three).

**Choosing a collision.** Three helpers, each naming a part by its label path, and `parts(s)`, which
lists every part's path, sorted, for a function that chooses by a rule (every fastener of a
hundred-part assembly at once):

- **`fit(s, part, kind)`** replaces the part's collision with a `box`, `sphere`, `cylinder` or
  `capsule` the kernel fits to the part's exact solid, its oriented bounding box: a capsule's axis
  its longest side; a cylinder's the axis the part is turned about where its rim is a round face as
  wide as the part, or its round faces make a quarter of its surface, so a disc's or a pancake
  motor's is its own axis however thin, else its longest side. Fast and stable, and as wrong as the
  box is for a part far from its shape.
- **`decompose(s, part, max_hulls=16, threshold=None)`** replaces it with the convex hulls CoACD cuts
  the part's mesh into, each a collision geom `<part>_hull<i>`, the visual whole. It is for a concave
  part whose one hull would fill its pocket or the gap between a gripper's jaws. `max_hulls` caps
  the count (`None` for no limit), `threshold` (0.01 to 1, CoACD's 0.05 by default) is the concavity
  it leaves: smaller cuts finer. It uses `cad[coacd]`, which the engine fetches on first need, and
  is refused, naming the extra, only where CoACD has no wheel (an Intel Mac, Windows on ARM, a musl
  Linux). The hulls are cached by the part's mesh and options, so only a changed part decomposes
  again; the first run takes a few seconds to about a minute a part, and says each as it is done.
  A hull's corners lie on the part, but its faces bridge the part's concave places by a few
  millimetres on a large part, at any threshold.
- **`collisions(s, part)`** is the part's collision geoms, a list (empty for a part that collides as
  nothing): set `friction`, `condim`, `contype` or `margin` on them, or `s.delete(geom)` each for a
  part that should not collide (a fastener, a cover, a motor inside its case). `fit` and `decompose`
  return the same list for what they made.

The part's mesh, unchanged, is the default: MuJoCo collides it as its convex hull.

**The excludes follow the parts' meshes, not your choice.** `spec()` excludes each jointed pair of
bodies whose parts touch as built, found before the function changes anything. After deleting or
replacing collisions, read `s.excludes`: a pair that no longer touches is still excluded, and the
exclude is between bodies, so it also stops every other part of those two bodies from colliding (a
finger in a carriage's body against the palm the carriage runs in). `s.delete(exclude)` removes one.

**Naming a part.** A part is its label path, as `cad model inspect` prints it (`gripper/left`); a
last segment, or any trailing run of them, is enough where it names one part (`left`,
`left_servo/case`). A label that names two is refused with their full paths, and one that names
none with the parts there. A part placed several times (one servo in each joint) is named once per
occurrence by its path. Several parts of one label in one link share one path: `collisions` returns
them all (a link's screws at once), and `fit` and `decompose`, which work on one solid, refuse the
path and say how many parts share it. Give those parts distinct labels in the model, or set their
geoms through `collisions`. Never name a part by a generated geom name (`left_collision`): the
writer's rules make those.

**A spec read from an `.xml`** (a robot made elsewhere, an export) has no solids and no label paths: its
parts are its meshes, named by mesh name (`spec("sim/arm.xml")` names the palm `palm`), and a
refusal lists them. `decompose` and `collisions` work on it; `fit` is refused.

**A body weighed by its collision.** A part with no density and no declared mass has no
`<inertial>`, and MuJoCo weighs its body from its geoms, so a collision choice changes its mass;
`fit` and `decompose` warn so, once a body. The cure is in the model: a material with a density, or
`mass()`.

**What `save(s, path)` does.** It works on a copy and leaves `s` as it was, still usable. It writes
the file with MuJoCo's own writer, copies every mesh and texture the spec names into `assets/` beside
it, so the folder travels, and removes the meshes its last save of that file wrote that it no
longer names (never another file). It writes a `scene.xml` beside the file when there is none and
the spec has no floor of its own (a floor, a light and the robot framed), and never writes over
one. Then it checks the file as `cad mujoco check` does and prints each warning, what the model
collides as (`collisions:`), its contact excludes (`excludes:`) and `wrote <path>`
([mjcf-checks.md](mjcf-checks.md#what-collides-and-the-excludes)). A spec MuJoCo refuses is
refused in MuJoCo's words, and nothing is written. A relative path is taken against the working
directory.

**Make every choice before a scene attaches the robot.** `scene.attach(s, ...)` consumes `s`: its
bodies, joints and geoms become the scene's, under the prefix. After it, `save`, `fit`,
`decompose` and `collisions` each refuse `s` by name. So a robot's function makes all its choices,
and is saved if its own file is wanted, before a scene attaches it.

**MuJoCo 4.0.0's traps.** Each checked on 4.0.0:

- `joint.damping` (and `stiffness`) is a 3-element array: `joint.damping = 0.1` raises `TypeError`;
  write `[0.1, 0, 0]`. `armature` and `frictionloss` take a float.
- The force bound is `joint.actfrcrange` on the spec and `actuatorfrcrange` in the file.
- `s.joint("typo")`, `s.geom("typo")` and `s.body("typo")` return `None`, and the error comes a line
  later, `'NoneType' object has no attribute ...`. `collisions` and `fit` refuse an unknown part by
  name instead.
- A material's `textures` is one name a role, ten of them. `s.add_material(name=..., textures=["",
  "grid"])` takes the short list unchecked and MuJoCo then reads past it, which can crash the process.
  Make the material, then set one role: `material.textures[mujoco.mjtTextureRole.mjTEXROLE_RGB] =
  "grid"`.
- A new `mujoco.MjSpec()` reads angles in degrees: set `compiler.degree = False` before giving it
  a range or a key. A spec from `spec()` is in radians already.
- `inheritrange=True` on a joint with no range (a continuous one) is refused when the spec
  compiles: give that actuator a `ctrlrange` of its own.
- MuJoCo writes about 6 significant digits (`range="0 0.349066"`), and a position actuator as
  `<general ... gainprm biasprm>`, its `dampratio` already turned into a damping, not as `<position
  kp kv>`. The plain export writes 9.

## The scene file

The `scene.xml` an export or a `save` writes beside the robot once is the person's, and nothing
writes over it. It includes the robot's file and adds a floor and a light. Add the solver options and
the defaults above its `<include>`, and leave the floor and light as written:

```xml
<mujoco model="arm scene">
  <option timestep="0.002" cone="elliptic" impratio="10"/>

  <default>
    <geom solref="0.005 1"/>
  </default>

  <include file="arm.xml"/>
  ...
</mujoco>
```

- **Defaults go above the `<include>`.** A class the included file defines copies the top-level
  defaults that stand at the `<include>`. A `<geom solref>` written after it reaches the elements in
  no class (the floor), but none in the robot's classes, and every element of a generated robot is
  in its class. `cad mujoco check` warns `defaults_after_include` where it is below.
- The option and `solref` lines clear `defaults_not_recommended`.
- A key the model's mechanism states make has no `ctrl`, so every position actuator commands 0, the
  zero pose (`home`, exported with `--zero home`). A key that commands another pose is the robot's,
  `s.add_key(name=..., qpos=..., ctrl=...)` in its MuJoCo function, with a `ctrl` per actuator in
  actuator order.

Check the scene after every edit (`cad mujoco check sim/scene.xml`). A scene
that composes other models goes in code instead (below).

## The scene in code

A scene is the same thing one level up: a function that makes a `mujoco.MjSpec`, attaches the
robots to it, adds the floor and the rest, and returns it; `save` writes it. `spec()` makes each CAD
piece or robot from elsewhere a spec, and a robot's own MuJoCo function makes one with its choices made.
Everything else is MuJoCo's own API, used directly: `attach` with a `prefix` and a `site` or a
`frame`, `add_body`, `add_geom`, `add_joint`, `add_freejoint`, `add_site`, `add_camera`,
`add_light`, `add_key`, `add_actuator`, `add_sensor`, `add_equality`. The scene script is the one
script that writes the scene, as `exports.py` is the one that writes files:

```python
# src/pick.py
import mujoco
from cad.mujoco import save, spec

from gripper import block
from gripper_mujoco import gripper_mujoco

ARM = "robots/arm/arm.xml"   # an arm made elsewhere: its maker's MJCF, its meshes beside it
HOME_ARM = [0, 0, 0, -1.57079, 0, 1.57079, -0.7853]   # its ready pose (its file's `home` key), radians


def pick(hand: mujoco.MjSpec, part) -> mujoco.MjSpec:
    scene = mujoco.MjSpec()
    scene.modelname = "pick"
    scene.compiler.degree = False   # radians
    scene.option.integrator = mujoco.mjtIntegrator.mjINT_IMPLICITFAST
    scene.option.cone = mujoco.mjtCone.mjCONE_ELLIPTIC
    scene.option.impratio = 10
    scene.option.timestep = 0.002
    scene.worldbody.add_light(pos=[0, 0, 2], dir=[0, 0, -1], type=mujoco.mjtLightType.mjLIGHT_DIRECTIONAL)
    scene.worldbody.add_geom(name="floor", type=mujoco.mjtGeom.mjGEOM_PLANE, size=[0, 0, 0.05])

    # The arm at the origin, the gripper (its choices made) on its flange, the CAD block loose on the floor.
    scene.attach(spec(ARM), prefix="arm/", frame=scene.worldbody.add_frame())
    scene.attach(hand, prefix="gripper/", site=scene.site("arm/attachment_site"))   # the site its file has for a tool
    scene.attach(spec(part), prefix="block/", frame=scene.worldbody.add_frame(pos=[0.5, 0, 0]))
    scene.body("block/block").add_freejoint(name="block/free")

    # The scene's own: a sensor, a camera, contact stiffness.
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
    save(pick(gripper_mujoco(), block()), "sim/pick.xml")   # the documents, built or replayed by the server
```

```bash
cad run src/pick.py
```

What each step does, and the traps:

- **The robot's choices come first.** `gripper_mujoco()` returns the gripper with its collisions,
  dynamics and actuator; the scene attaches it and changes nothing of it. Attaching consumes the
  robot's spec ([above](#the-mujoco-function)), so save the robot's own file, where one is wanted,
  before the scene attaches it (`hand = gripper_mujoco()`, `save(hand, "sim/gripper.xml")`, then
  `pick(hand, block())`); `save` leaves `hand` usable.
- **`spec(thing)`** for each piece with no choices to make: the block, the arm (its own file
  carries its actuators). Without `assets=`, a document's meshes go to a folder of the engine's
  cache named by their content.
- **Every spec names its files by absolute path.** MuJoCo resolves an attached model's meshes by
  its own folder when it compiles, but the scene's writer names them bare, so a robot read with
  `MjSpec.from_file` and attached loses its meshes when the scene is saved. `spec()` names each mesh
  and texture absolutely and clears the spec's own folders: load a robot made elsewhere through `spec()`
  too, never `MjSpec.from_file`: `save` refuses a scene that attached one, in MuJoCo's words (`Error
  opening file`) and naming `spec(path)`. A scene written another way that cannot find a mesh fails
  `cad mujoco check` with `compile_failed`, in MuJoCo's words.
- **`save` makes the folder travel.** It copies every file the scene names, the attached robots'
  included, into `sim/assets/` beside `sim/pick.xml` and names each there (two files of one name
  become two, the second `_2`), so the folder loads on another computer. A scene has a floor of its
  own, so `save` writes no `scene.xml` beside it.
  `to_file` alone would leave this computer's paths in the file, and `to_zip` writes the XML into a
  zip without the mesh files it names: neither ships a scene.
- **`attach`** copies the child into the scene under a `prefix`, at a `frame` (a placement in the
  parent) or a `site` (the arm's flange). Every name of the child is prefixed (bodies, joints, geoms,
  sites, actuators, default classes, keys): `gripper/left`, `gripper/grip`,
  `arm/attachment_site`. The child's root body has no joint, so it is welded where it is attached.
- **A free body.** A part with no mechanism is one body under the world; `add_freejoint` on it, after
  attaching, makes it loose. Its 7 `qpos` values are its position, then its quaternion.
- **Options.** Each piece carries its own `<option integrator>`; a scene whose integrator differs
  makes MuJoCo warn once about the conflict when attaching, and the scene's own is kept. Set the scene's option first, as here, and the warning does not come.
- **Keys.** The children's keys come along prefixed (`arm/home`, `gripper/closed`), each padded to
  the scene's length with every other joint at `qpos0`. Give the scene its own `home` over every
  joint: `qpos` is 1 per hinge or slide, 4 per ball, 7 per free joint, in MuJoCo's joint order (the
  body tree, depth first), and `ctrl` one
  per actuator, in actuator order (the arm's seven, then the gripper's `grip`). A key of the wrong
  length is no pose.
- **Composing two models of one family** of default classes is safe: classes are prefixed with the
  model, so the gripper's `visual` is `gripper/visual` and the arm's its own under `arm/`.

A robot made in the same project attaches the same way: an arm model of its own with a `frame()` on
its last link and a MuJoCo function of its own, and the gripper attached at that site
(`scene.site("arm/flange")`).

## Check and show the scene

```bash
cad mujoco check sim/pick.xml
```

On the scene above it prints:

```text
warning: joint_limits_at_rest at sim/pick.xml: 1 joint(s) lie outside their range at qpos0: joint 'arm/joint4' is 0 rad, range [-3.072, -0.0698] rad ([-176, -3.999] deg) Hint: ...
info: compiled at sim/pick.xml: compiled by MuJoCo 4.0.0: 13 bodies, 10 joints, 68 geoms, 62 meshes, 4 keyframes
info: mass_summary at sim/pick.xml: moving mass 16.27 kg in 12 moving bodies, 15 degrees of freedom (nv), 8 actuators (nu); moving geometry spans 0.622 x 0.302 x 1.12 m at qpos0
info: collisions at sim/pick.xml: 15 collision geoms (mesh 11, box 3, plane 1) on 13 bodies: world 1 (plane 1); arm/link0 1 (mesh 1); ...; gripper/palm 1 (box 1); gripper/left 1 (box 1); gripper/right 1 (box 1); and 1 more. Moving bodies that collide as nothing: arm/attachment
info: excludes at sim/pick.xml: 4 contact excludes, each between two bodies whole: arm/link0 and arm/link1 0.994 mm apart at rest; gripper/palm and gripper/left touching at rest; gripper/palm and gripper/right touching at rest; gripper/left and gripper/right 30 mm apart at rest
OK sim/pick.xml: MuJoCo model 'pick', 13 bodies, 10 joints, 8 actuators, 15 collision geoms, 62 meshes, 4 keys
```

Read every line:

- `joint_limits_at_rest` at `qpos0` is the arm's own (its elbow's range excludes zero, as
  its maker's file has it); the check found nothing at `home`, so start the simulation from `home`. The
  same warning at `home` is a key to fix.
- `contacts_at_rest`, `visual_geoms_collide`, `inertia_from_visuals` and `scale_suspect` are absent:
  nothing intersects at rest, visuals do not collide, every body has its inertial, and the sizes are
  metres. Any of them present is a modelling error to fix before anything else
  ([mjcf-checks.md](mjcf-checks.md#model-health) says what to do for each).
- `defaults_not_recommended` and `defaults_after_include` are absent: the scene set the cone,
  `impratio` and `solref`, above anything it includes.
- `mass_summary`: 16 kg moving in 15 degrees of freedom and 8 actuators, about a metre tall. A
  number off by 1000 is a unit; a count off by one is a joint or an actuator missing.
- `collisions`: the gripper's three boxes came through the attach, the floor collides as a plane
  (the block is the row past the twelve the line names; `--json` has every one), and the one moving
  body that collides as nothing is the arm's attachment frame, which has no geometry. A robot's
  link missing here lost its collision.
- `excludes`: the arm's own (its base and first link, its maker's) and the gripper's three, the
  two fingers apart because the gripper is open. An exclude nobody meant between two bodies that
  stand apart is one to remove ([mjcf-checks.md](mjcf-checks.md#what-collides-and-the-excludes)).
- The last line counts 4 keys: the scene's `home` and the children's, prefixed.

Then show it. No `cad` command draws an MJCF: the check above is your review, and MuJoCo itself
shows the scene to the person:

```bash
cad run mujoco-studio --model sim/pick.xml
```

MuJoCo Studio compiles and simulates the scene in the person's browser, reloading as `pick.xml`
changes: give the person the URL it prints. It listens on every interface with no authentication
(Studio's own limitation), so run it on this computer or a trusted network.

## Tuning

Tune only a model that is healthy: every `contacts_at_rest`, `visual_geoms_collide`,
`inertia_from_visuals`, `scale_suspect` and `joint_limits_at_rest` at `home` cleared. Each of those
is a modelling error, and no solver setting fixes one; tuning around it hides it. Then:

1. **Baseline.** The validated scene and one fixed scenario, started from `home`: the block left to
   settle, the gripper closed on it, the arm moved through one motion. Note what it does in MuJoCo
   Studio (rests still, slips, jitters, sinks into the floor, explodes).
2. **One parameter at a time**, in the scene script for what the scene owns, in the robot's MuJoCo
   function for what it chooses, and in the model for what the geometry owns. Change one, run the
   script, `cad mujoco check sim/pick.xml` after every write, run the same
   scenario, and keep the change or revert it.
3. **Record** each kept change and the reason in a comment beside it in the script that made it.

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
  motion much. Both are set in the MuJoCo function (`joint.armature`, `joint.damping`), each with
  where its number came from in a comment. The armature is the rotor's inertia times the gear ratio
  squared, and a servo's listing gives the ratio far more often than the rotor. Take the best of
  these, in order:
  1. **The motor's rotor inertia**, where its own datasheet lists one (1 g*cm^2 is 1e-7 kg*m^2),
     with its source in a comment.
  2. **The rotor's size**, where you can find it (the motor's part number, a teardown, or the motor
     the vendor's STEP draws inside the servo, measured there): `m r^2 / 2` of a solid cylinder that
     size is an upper bound, since a coreless motor's cup rotor is far lighter. With how you made it
     in a comment. For example, 1e-7 kg*m^2 through a 1:250 gearbox is 0.00625 kg*m^2.
  3. **Neither**: tune one, marked in its comment as tuned rather than measured. Start from the
     order of magnitude: the small brushed motors inside hobby and smart servos have rotors of roughly 1e-8 kg*m^2 (a
     coreless micro motor) to 1e-6 kg*m^2 (an iron-core can motor about 25 mm across), so 1e-7
     times the gear ratio squared is a fair first value, good to a factor of ten either way. An
     industrial or collaborative arm's joint is another class: a brushless motor through a harmonic
     or cycloidal drive, ratios of about 50 to 160, rotors of about 1e-5 to 1e-4 kg*m^2, so its
     reflected inertia is of the order of 0.03 to 2 kg*m^2 (the larger at the shoulder, the smaller
     at the wrist). A quasi-direct-drive actuator (a large flat brushless motor through a
     planetary of about 6:1 to 10:1, a legged robot's joint) is a third: its rotor dominates, about
     1e-5 to 1e-4 kg*m^2 for a motor 50 to 100 mm across, and the low ratio reflects little of it,
     about 4e-4 to 1e-2 kg*m^2. That is an order of magnitude to start from, not a value: tune it. Raise it
     while a joint rings or chatters under its position actuator; lower it while the joint lags a
     command the hardware follows.
- **Actuators**: gains from the robot's data sheet (`kp`, and `kv` or `dampratio` for a position
  actuator), control ranges inside the joint's limits.

A mass or an inertia is never a tuning knob here: it is the model's, and changes in the model (a
material, `mass()`) and is regenerated. A collision shape is the part's shape as the simulator sees
it: change it in the MuJoCo function where contact is wrong, never to steady the solver.

## What is not supported

- Compiled models (`.mjb`) and packages (`.mjz`): the check reads the XML, as MuJoCo compiles it.
- An MJCF in the CAD Viewer or the CAD app, or a still of one: it is MuJoCo's own file. `cad mujoco
  check` checks it, and MuJoCo Studio is where it is seen and where a simulation runs.
- Converting between URDF and MJCF beyond what MuJoCo's own loader does with a URDF
  ([interoperability.md](interoperability.md#mjcf)). A robot with a CAD model is generated in each
  format from that model instead.
- A closed loop's joints posed by name: a loop has no pose without a solver, so a mechanism state
  moving one is left out of the keys; MuJoCo closes the loop when the simulation runs.
