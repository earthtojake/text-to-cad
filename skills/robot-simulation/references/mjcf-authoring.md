# MJCF authoring

Use this reference when writing or editing a MuJoCo model: its compiler settings, default classes, assets, body tree, joints, geoms, actuators, equalities and keyframes. The deliverable is an MJCF document, MuJoCo's XML, with `<mujoco model="...">` at its root, as `.xml` (or `.mjcf`). It describes a model for MuJoCo; it is not a URDF in other words, and not a simulation run: nothing here steps the physics.

The conventions below are MuJoCo Menagerie's (google-deepmind/mujoco_menagerie), the reference collection of MuJoCo robots; its Franka `panda.xml` is a good one to read beside this.

## Edit loop

1. Locate the target `.xml`. It is the source of truth; author and edit the XML directly.
2. Identify the consumer (MuJoCo's version, a training or control stack) and whether the robot already has a URDF ([interoperability.md](interoperability.md#mjcf)).
3. Keep a ledger as a comment block at the top of `robot.xml`: frames, joints and their positive motion, units, mesh sources and scale, assumptions ([urdf-ledger.md](urdf-ledger.md) has the shape).
4. Write the compiler line, the default classes and the assets first, then the body tree, then actuators, equalities and keyframes.
5. Compute inertials and unit conversions with formulas or a throwaway script, never freehand ([inertials.md](inertials.md)). Mesh files and scale: [meshes.md](meshes.md).
6. Validate with `cad mjcf validate scene.xml --compile required` ([mjcf-checks.md](mjcf-checks.md)).
7. Snapshot the `home` key and each joint moved; show the model ([Show the model](../SKILL.md#show-the-model)). To show it as MuJoCo compiles and simulates it: `cad run mujoco-studio --model path/to/scene.xml`, MuJoCo Studio's web viewer, which reloads the model as the file changes; the person opens the URL it prints.
8. Report assumptions, skipped checks and risks ([guardrails.md](guardrails.md#the-report)).

## Units: the compiler line

MuJoCo reads every angle in a file -- `euler`, `axisangle`, a hinge's `range` and `ref` -- in **degrees** unless the compiler says otherwise. A model written in radians without saying so opens with every limit 57 times too small. Always set it explicitly:

```xml
<compiler angle="radian" meshdir="assets" autolimits="true"/>
```

- `angle="radian"`: every angle in the file is radians. A keyframe's `qpos` and `ctrl` are radians whatever `angle` says.
- `meshdir="assets"`: mesh files are found under `assets/` beside the main file (`assetdir` sets mesh and texture folders together; `texturedir` textures alone).
- `autolimits="true"`: a joint or actuator with a `range` is limited; no `limited="true"` needed.
- `eulerseq` is `xyz` (intrinsic) unless set; set it only to match a source that uses another sequence.

Lengths are metres and masses kilograms, as everywhere in this skill.

## Robot and scene

Split the robot from its world:

- `robot.xml` (named for the robot, `panda.xml`): the compiler, defaults, assets, the robot's body tree, its actuators, equalities and keyframes. No floor, no light, no skybox.
- `scene.xml`: `<include file="panda.xml"/>`, then the floor plane, the light and anything else of the world.

```xml
<mujoco model="panda scene">
  <include file="panda.xml"/>
  <worldbody>
    <light pos="0 0 1.5" dir="0 0 -1" directional="true"/>
    <geom name="floor" size="0 0 0.05" type="plane" material="groundplane"/>
  </worldbody>
</mujoco>
```

An include is read relative to the main file's folder and splices the included file's children in; each file is included once. Validate and snapshot `scene.xml` to see the robot standing in its world, and `robot.xml` to see it alone.

## Default classes

Defaults are how a model stays short and consistent. Give the robot one class named for it, set as `childclass` on its root body so everything below inherits it, with a `visual` and a `collision` class inside:

```xml
<default>
  <default class="panda">
    <joint armature="0.1" damping="1"/>
    <default class="visual">
      <geom type="mesh" contype="0" conaffinity="0" group="2"/>
    </default>
    <default class="collision">
      <geom type="mesh" group="3"/>
    </default>
  </default>
</default>
```

- An element takes its attributes from its own `class`, else the nearest enclosing body's `childclass`, else `main`; an attribute written on the element wins.
- Classes nest: an inner class inherits the outer class's attributes and overrides what it sets.
- A class an element names must be declared; a name used twice is an error.

## Visual and collision geoms

MuJoCo collides every geom unless told not to, so a visual mesh needs `contype="0" conaffinity="0"`. The convention:

- **visual** geoms: `group="2"`, no contacts. Full-detail meshes, materials.
- **collision** geoms: `group="3"`. Primitives (`box`, `capsule`, `cylinder`, `sphere`) sized from the part, or a coarse convex mesh; name a collision mesh with a `_c` suffix (`link1_c`). MuJoCo hulls every mesh it collides, so a concave visual mesh used for collision collides as its convex hull.

The CAD Viewer and `cad mjcf snapshot` draw groups 0 to 2, as MuJoCo's own viewer does by default, and leave 3 and up out, so a model following this convention shows its visuals and hides its collision geoms. A geom left in group 0 is drawn whether it is meant for collision or not.

A geom's size is MuJoCo's: half sizes for a `box`, a radius (and a half length) for a `sphere`, `capsule` or `cylinder`. `fromto="x1 y1 z1 x2 y2 z2"` places a capsule, cylinder or box between two points instead of `pos` and an orientation.

## Bodies and frames

- A `<body>` is placed in its parent by `pos` and one orientation: `quat` (w x y z), `euler`, `axisangle`, `xyaxes` or `zaxis`. Two orientations on one element are an error.
- A body with **no joint is welded** to its parent: there is no `fixed` joint to write.
- A floating base gets `<freejoint/>` as its only joint. A `<freejoint/>` belongs to a body directly under `<worldbody>`.
- A body may carry several joints; MuJoCo composes them in order about the body's frame.
- `<frame>` groups elements under one transform without making a body.
- Names are lowercase snake_case and numbered from the base: bodies `link0`..`link7`, joints `joint1`..`joint7`, actuators `actuator1`..`actuator8`. Every consumer (controllers, keyframes, policies) reads them; a rename updates every one in the same task.

## Joints

- `type="hinge"` (the default) turns about `axis`, `type="slide"` slides along it; `axis` is in the body's frame, never of zero length.
- `range` in radians (with `angle="radian"`) or metres. With `autolimits="true"` a range limits the joint; without a range a hinge turns freely.
- `ref` is the joint's value in the authored pose (MuJoCo's `qpos0`). Leave it at zero unless the source says otherwise.
- `type="ball"` and `free` exist for spherical joints and floating bodies; the viewer draws such a body where it is authored and cannot pose it.
- Two joints that move together are coupled by `<equality><joint joint1="follower" joint2="leader" polycoef="0 1 0 0 0"/></equality>`: `joint1 = polycoef[0] + polycoef[1] * joint2` (a gripper's second finger). The viewer follows a linear coupling and treats a polynomial one as a joint of its own.

## Inertia

Let the compiler compute each body's mass and inertia from its geoms where they represent the part (`<compiler inertiafromgeom="auto"/>`, the default, does this for a body with no `<inertial>`). Where they do not -- vendor data, a mesh that is a shell, a body whose geoms are all visual -- give the body an `<inertial pos mass diaginertia="..."/>` or `fullinertia="Ixx Iyy Izz Ixy Ixz Iyz"`, computed, never guessed ([inertials.md](inertials.md)). A visual geom with `contype="0" conaffinity="0"` still adds mass to a computed inertia (`<compiler inertiagrouprange>` counts every group by default), so a body with a visual and a collision geom of the same part counts it twice: give it an `<inertial>`, as Menagerie's Panda does, or keep the visual geoms out of the range.

## Actuators and options

- One actuator per controlled joint, named `actuator1`.. in joint order: `<position joint="joint1" kp="..." ctrlrange="..."/>` or `<motor>`/`<general>`, values from the robot's data sheet.
- `<option integrator="implicitfast"/>`: stable for damped, position-controlled robots and Menagerie's default.

## Keyframes

Every model ships a `home` key, the pose a person and a controller start from:

```xml
<keyframe>
  <key name="home" qpos="0 0 0 -1.5708 0 1.5708 -0.7853 0.04 0.04" ctrl="0 0 0 -1.5708 0 1.5708 -0.7853 255"/>
</keyframe>
```

- `qpos` lists every joint's value in tree order: a hinge or slide takes 1 number, a `ball` 4 (a quaternion), a `free` 7 (position, then quaternion). A key of the wrong length is no pose.
- `ctrl` lists one value per actuator, in actuator order.
- Radians and metres, always.

The viewer opens the model as MuJoCo does, at `qpos0` (each joint at its `ref`), not at `home`; `home` and every other key are poses to choose (`cad mjcf snapshot model.xml out.png --pose home`).

## What the viewer draws

The CAD Viewer (`cad viewer model.xml`) shows an MJCF in its robot view, a slider per hinge and slide joint, and `cad mjcf snapshot` draws the same still. It reads the model with its own reader, not MuJoCo, so it draws less than MuJoCo compiles:

- drawn: `sphere`, `capsule`, `cylinder`, `box`, a `plane` with a size, and STL and OBJ meshes, in groups 0 to 2, each in its `rgba` or material colour;
- not drawn, each said as a finding: `hfield`, `sdf` and `ellipsoid` geoms, a plane with no size (the viewer's grid stands in for the floor), an MSH or inline mesh, and what `<replicate>`, `<attach>`, `<flexcomp>`, `<flex>` and `<composite>` would expand into (MuJoCo's compiler makes those bodies; the reader sees nothing);
- not posable: a `ball` or `free` joint's body, drawn where it is authored;
- not read: textures, sites, cameras, lights, tendons, sensors and actuators (the model keeps them; the viewer does not draw them).

Not supported at all: compiled models (`.mjb`) and packages (`.mjz`), exporting the compiled geometry, converting between URDF and MJCF, and playing a simulation. For the model exactly as MuJoCo compiles it, `cad mjcf validate --compile required`.
