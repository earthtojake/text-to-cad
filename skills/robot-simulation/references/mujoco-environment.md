# A MuJoCo environment from CAD

Read this to take a CAD-made mechanism into a MuJoCo simulation: the simulator's choices in the
robot's MuJoCo function, a scene in `scene.xml` or composed in code, and tuning. What the model
declares and what an export writes is [from-cad.md](from-cad.md), hand-written MJCF is
[mjcf-authoring.md](mjcf-authoring.md), and every finding the checks print is in
[mjcf-checks.md](mjcf-checks.md).

## Contents

- [What comes from where](#what-comes-from-where)
- [The example model](#the-example-model)
- [The MuJoCo function](#the-mujoco-function)
- [The scene file](#the-scene-file)
- [The scene in code](#the-scene-in-code)
- [Tuning](#tuning)

## What comes from where

The model holds what is true of the machine and is regenerated on every change
([from-cad.md](from-cad.md)). What a simulation chooses has two owners, and is changed there:

| Owner | Holds |
| --- | --- |
| The robot's MuJoCo function, on its `MjSpec` | Each part's collision shape, or none; friction and the other contact settings of its collision geoms; excluded pairs; joint `armature`, `damping` and `frictionloss`; actuators, their gains and control ranges; sensors; keys with a `ctrl`; an equality's `solref` where a loop must hold stiffer than MuJoCo's default |
| The scene, a scene function or `scene.xml` | Where each robot stands and what it is attached to; a loose part's free joint; the floor, lights and cameras; robots from elsewhere, and the prefixes that keep names apart; solver settings (timestep, cone, `impratio`) and contact softness (`solref`, `solimp`); its own `home` key over every joint and actuator |

Their numbers come from the robot's data sheet and from [tuning](#tuning), not from the CAD.

## The example model

The gripper that SKILL.md's MuJoCo function is written for, its fingers turning together, and a block
to pick up. The rest of this file runs from it:

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

Declare on finished parts, as a material is set: an operation after a `frame()`, `body()`, `mass()`
or `point_mass()` makes a new shape that has lost it, with no warning, while a move or a copy keeps
it.

`cad model export "$ID" sim/gripper.xml` writes the file a MuJoCo function starts from (`spec()`
holds the same), abridged:

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

- Each link is a body at its joint's frame, the joint on that frame's Z (`axis="0 0 1"`). The ground
  link, the parts no joint moves, has no joint and is welded where it is attached. A cylindrical
  joint is a hinge and a slide on one body, `<name>` and `<name>/slide`.
- Each part is a `visual` geom named for it and a `collision` geom of the same mesh,
  `<part>_collision`.
- `<contact>` excludes each jointed pair of bodies whose parts touch at rest. MuJoCo's own parent
  filter misses the pair at a first joint, whose parent is welded to the world.
- The keys are the mechanism states, a follower where its leader puts it.

## The MuJoCo function

SKILL.md has the gripper's function, `src/gripper_mujoco.py`. Its run ends with what `save` checked
of the file:

```text
collisions: 3 collision geoms (box 3) on 3 bodies: palm 1 (box 1); left 1 (box 1); right 1 (box 1)
excludes: 2 contact excludes, each between two bodies whole: palm and left touching at rest; palm and right touching at rest
wrote /path/to/sim/gripper.xml
```

Read both lines against the function: three boxes, as fitted, and no exclude but the export's two.

**`spec(thing, zero=, tolerance=, assets=)`** makes a `mujoco.MjSpec` of a model call's handle, a
build123d shape, a `.step`, an `.xbf`, or an MJCF path (an export, a robot made elsewhere). For a
document, `zero=` takes the robot at a mechanism state, as an export's `--zero` does, `tolerance=`
meshes its parts finer, in millimetres, and `assets=` writes its meshes into a folder relative to
the working directory instead of the engine's cache. The spec names every mesh and texture by
absolute path, which is why `save`, not MuJoCo's `to_file`, writes it.

**Choosing a collision.** `parts(s)` lists every part's label path, sorted, for a function that
chooses by a rule (every fastener of a hundred-part assembly at once). Three helpers each take one
path:

- **`fit(s, part, kind)`** replaces the part's collision with a `box`, `sphere`, `cylinder` or
  `capsule` fitted to the oriented bounding box of the part's exact solid. A capsule lies along the
  box's longest side. A cylinder lies along the axis the part is turned about (where its rim is a
  round face as wide as the part, or round faces make a quarter of its surface, so a disc or a
  pancake motor keeps its own axis however thin), else along the longest side. Fast and stable, and
  as wrong as that box is for a part far from the shape.
- **`decompose(s, part, max_hulls=16, threshold=None)`** replaces it with the convex hulls CoACD
  cuts the part's mesh into, each a collision geom `<part>_hull<i>`; the visual stays whole. It is
  for a concave part whose one hull would fill its pocket or the gap between a gripper's jaws.
  `max_hulls` caps the count (`None` for no limit); `threshold` (0.01 to 1, CoACD's 0.05 by default)
  is the concavity left, a smaller one cutting finer. The first run takes a few seconds to about a
  minute a part and says each as it is done; the hulls are cached by the part's mesh and options, so
  only a changed part is cut again. It is refused, naming `cad[coacd]`, where CoACD has no wheel (an
  Intel Mac, Windows on ARM, a musl Linux). A hull's corners lie on the part, but its faces bridge
  the part's concave places, by a few millimetres on a large part at any threshold.
- **`collisions(s, part)`** returns the part's collision geoms, a list (empty for a part that
  collides as nothing). Set `friction`, `condim`, `contype` or `margin` on them, or `s.delete(geom)`
  each for a part that should not collide (a fastener, a cover, a motor inside its case). `fit` and
  `decompose` return the same list for what they made.

**Naming a part.** A part is its label path as `cad model inspect` prints it (`gripper/left`). Its
last segment, or any trailing run of segments, is enough where that names one part (`left`,
`left_servo/case`); a name that fits none or several is refused with the candidates. A part placed
several times (one servo in each joint) has a path per occurrence. Parts of one label in one link
share a path: `collisions` returns all their geoms (a link's screws at once), and `fit` and
`decompose`, which work on one solid, refuse it. Do not reach a geom by its generated name
(`left_collision`): the writer's naming rules are no contract.

**A spec read from an MJCF** has no solids and no label paths: its parts are the meshes its colliding
geoms use, by mesh name. `collisions` and `decompose` work on it; `fit` is refused.

**The excludes follow the parts' meshes, not the function's choices.** `spec()` excludes each
jointed pair of bodies whose parts touch as built, before the function changes anything. An exclude
is between two bodies whole, so after collisions are deleted or replaced one can stand between
bodies that no longer touch, and it then stops every other part of those bodies from colliding (a
finger in a carriage's body against the palm the carriage runs in). Read `s.excludes`, or the
`excludes:` line, and `s.delete(exclude)` the leftover. Any other pair is the function's to exclude,
by body name: `s.add_exclude(bodyname1="left", bodyname2="right")` for fingers that touch when
closed, which the line then reports as `left and right 30 mm apart at rest`.

**Keys.** The keys made from mechanism states carry no `ctrl`: reset to one and every position
actuator still commands 0, the zero pose. A key that commands its pose is the function's,
`s.add_key(name=..., qpos=..., ctrl=...)`, with one `ctrl` per actuator in actuator order.

**`save(s, path)`** writes the spec with MuJoCo's own writer, copies every mesh and texture it names
into `assets/` beside the file, and writes a `scene.xml` there when there is none and the spec has
no floor of its own (a floor, a light and the robot framed). It never writes over a `scene.xml`, and
removes only the meshes its last save of that file wrote and no longer names. It works on a copy, so
`s` stays usable. Then it checks the file as `cad mujoco check` does and prints each warning, the
`collisions:` and `excludes:` lines
([mjcf-checks.md](mjcf-checks.md#what-collides-and-the-excludes)) and `wrote <path>`. A spec MuJoCo
refuses is refused in MuJoCo's words, and nothing is written. A relative path is taken against the
working directory. MuJoCo's own writers do not ship a spec: `to_file` leaves this computer's paths
in the file, and `to_zip` zips the XML without the meshes it names.

**Attaching consumes a spec.** `scene.attach(s, ...)` takes `s`'s bodies, joints and geoms into the
scene, and `save`, `parts`, `fit`, `decompose` and `collisions` each refuse `s` after it. A robot's
function makes every choice, and saves the robot's own file where one is wanted, before a scene
attaches it.

**MuJoCo's Python API has traps**, each checked on MuJoCo 4.0.1:

- `joint.damping` and `joint.stiffness` are 3-element arrays: `joint.damping = 0.1` raises
  `TypeError`; write `[0.1, 0, 0]`. `armature` and `frictionloss` take a float.
- The force bound is `joint.actfrcrange` on the spec and `actuatorfrcrange` in the file.
- `s.joint("typo")`, `s.geom("typo")` and `s.body("typo")` return `None`, and the error comes a line
  later, `'NoneType' object has no attribute ...`. `collisions` and `fit` refuse an unknown part by
  name instead.
- A material's `textures` is one name a role, ten of them. `s.add_material(name=..., textures=["",
  "grid"])` takes the short list unchecked and MuJoCo then reads past it, which can crash the
  process. Make the material, then set one role:
  `material.textures[mujoco.mjtTextureRole.mjTEXROLE_RGB] = "grid"`.
- A new `mujoco.MjSpec()` reads angles in degrees: set `compiler.degree = False`, or every `range`
  and `ref` is read 57 times too small (a key's `qpos` is radians either way). A spec from `spec()`
  is in radians already.
- `inheritrange=True` on a joint with no range (a continuous one) is refused when the spec compiles:
  give that actuator a `ctrlrange` of its own.
- MuJoCo writes about 6 significant digits (`range="0 0.349066"`) where the plain export writes 9,
  and a position actuator as `<general ... gainprm biasprm>`, its `dampratio` already turned into a
  damping, not as `<position kp kv>`.

## The scene file

The `scene.xml` an export or a `save` writes beside the robot once includes the robot's file and adds
a floor and a light. It is yours to edit, and nothing writes over it. Solver options and contact
defaults go above its `<include>`:

```xml
<mujoco model="gripper scene">
  <option timestep="0.002" cone="elliptic" impratio="10"/>

  <default>
    <geom solref="0.005 1"/>
  </default>

  <include file="gripper.xml"/>
  ...
</mujoco>
```

A class the included file defines copies the top-level defaults that stand at the `<include>`. A
`<default>` written after it reaches the elements in no class (the floor) and none in the robot's
classes, and every element of a generated robot is in its class: `cad mujoco check` warns
`defaults_after_include`. With these lines above it, `defaults_not_recommended` is cleared.

A scene that composes several models is written in code.

## The scene in code

A scene is a function one level up: it makes a `mujoco.MjSpec`, attaches each piece (`spec()` of a
CAD model or of a robot made elsewhere, or the spec a robot's MuJoCo function returns), adds the
world with MuJoCo's own API, and returns it for `save` to write:

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
    save(pick(gripper_mujoco(), block()), "sim/pick.xml")
```

```bash
cad run src/pick.py
cad mujoco check sim/pick.xml
```

- **Read every piece with `spec()`**, a robot made elsewhere too. MuJoCo finds an attached model's
  meshes by that model's own folder but writes their names bare, so a robot read with
  `MjSpec.from_file` and attached loses its meshes in the saved scene: `save` refuses that scene,
  naming `spec(path)`.
- **`attach`** copies the child into the scene at a `frame` (a placement in the parent) or a `site`
  (the arm's flange; a CAD robot's `frame()` is a site), under a `prefix` that every name of the
  child takes: bodies, joints, geoms, sites, actuators, default classes, keys (`gripper/left`,
  `gripper/grip`, `arm/attachment_site`). A child whose root body has no joint is welded there.
  Attaching consumes the child's spec ([above](#the-mujoco-function)): to keep the robot's own file
  too, save it first (`hand = gripper_mujoco()`, `save(hand, "sim/gripper.xml")`, then
  `pick(hand, block())`).
- **A loose part** is one body under the world once attached: `add_freejoint` on it.
- **Options.** The scene's `<option>` is the one kept, its defaults included (Euler, a pyramidal
  cone), and MuJoCo warns `Attach conflict` for each setting a piece's file has otherwise. Set the
  scene's options before attaching.
- **Keys.** The children's keys come along prefixed (`arm/home`, `gripper/closed`), each padded to
  the scene's length with every other joint at `qpos0`. Give the scene a `home` of its own over
  every joint and actuator ([how a key counts](mjcf-authoring.md#keyframes)).
- **`save` makes the folder travel.** Every file the scene names, the attached robots' too, is
  copied into `sim/assets/`, a second file of one name as `_2`. A scene has a floor of its own, so
  no `scene.xml` is written beside it.

## Tuning

Tune only a model with no model-health warning ([mjcf-checks.md](mjcf-checks.md#model-health)): each
is a modelling error that no solver setting fixes, and tuning around one hides it. Fix one scenario
from `home` as the baseline (the block left to settle, the gripper closed on it, one arm motion) and
note what it does in MuJoCo Studio: rests, slips, jitters, sinks, explodes. Then change one parameter
at its owner ([above](#what-comes-from-where)), run the script, check, run the same scenario, and
keep the change or revert it, with the reason for each kept change in a comment beside it.

What to try, in the order MuJoCo's modelling guide gives:

- **Integrator**: `implicitfast`, stable with damping and position actuators.
- **Timestep**: 0.5 to 2 ms for contact-rich manipulation, 5 ms at most with contacts. Halve it when
  contacts jitter or penetrate.
- **Contact stiffness**: `solref[0]`, the contact's time constant, 0.004 to 0.01 for manipulation
  and at least twice the timestep. Smaller is stiffer and needs a smaller timestep.
- **Friction cone**: `elliptic` with `impratio` 10 for grasping, so a held part does not creep out.
  Geom `friction` (sliding, torsional, rolling) and `condim` (3 by default; 4 adds torsional, 6
  rolling) on a gripper's pads when a grasp turns or rolls.
- **Joints**: `armature` and a light `damping` on every actuated joint steady an implicit integrator
  without changing the motion much.
- **Actuators**: gains from the data sheet (`kp`, and `kv` or `dampratio` for a position actuator),
  control ranges inside the joint's limits.

`armature` is the rotor's inertia times the gear ratio squared, and a servo's listing gives the
ratio far more often than the rotor. Take the best of these, and say which in a comment beside the
number: the rotor inertia from the motor's own data sheet (1 g*cm^2 is 1e-7 kg*m^2); else `m r^2 / 2`
of a solid cylinder the rotor's size (from the motor's part number, a teardown, or the motor the
vendor's STEP draws inside the servo), an upper bound, since a coreless motor's cup rotor is far
lighter; else a value tuned from the drive's order of magnitude:

| Drive | Rotor, kg*m^2 | Gear ratio | At the joint, kg*m^2 |
| --- | --- | --- | --- |
| Hobby or smart servo: a small brushed motor | 1e-8 (a coreless micro motor) to 1e-6 (an iron-core can motor about 25 mm across) | as listed | 1e-7 x ratio^2 as a first value, good to a factor of ten: 0.00625 at 1:250 |
| Industrial or collaborative arm: a brushless motor through a harmonic or cycloidal drive | 1e-5 to 1e-4 | 50 to 160 | 0.03 to 2, the larger at the shoulder |
| Quasi-direct drive (a legged robot's joint): a flat brushless motor 50 to 100 mm across through a planetary | 1e-5 to 1e-4 | 6 to 10 | 4e-4 to 1e-2 |

Raise a tuned armature while the joint rings or chatters under its position actuator, and lower it
while the joint lags a command the hardware follows.

A mass or an inertia is never a tuning knob: it is the model's (a material, `mass()`). Nor is a
collision shape, which changes in the MuJoCo function where contact is wrong, never to steady the
solver.
