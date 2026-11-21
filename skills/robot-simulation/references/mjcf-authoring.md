# MJCF authoring

Read this to write or edit a MuJoCo model by hand, or to read a generated one: the layout `cad mujoco check` holds a file to, and the traps MuJoCo's own manual leaves an author to find. The file is MuJoCo's XML, `<mujoco model="...">` at its root, as `.xml` or `.mjcf`.

A robot that has a CAD model here is not authored by hand: export it, and make its simulation's choices in its MuJoCo function ([mujoco-environment.md](mujoco-environment.md)). A generated file follows this layout; change the model or the function, never the file. A robot that has only a URDF starts from MuJoCo's own URDF loader ([interoperability.md](interoperability.md#mjcf)).

## Layout

Split the robot from its world, as an export does:

- `arm.xml`, named for the robot: the compiler line, default classes, assets, the body tree, equalities, actuators and keys. It compiles alone.
- `scene.xml`: solver options and contact defaults, then `<include file="arm.xml"/>`, then the floor, the lights and whatever else stands in the world ([the scene file](mujoco-environment.md#the-scene-file)). An include resolves against the main file's folder, and MuJoCo refuses a file included twice.

The robot's file opens with its ledger as a comment ([urdf-authoring.md](urdf-authoring.md#the-ledger) has the block), then:

```xml
<mujoco model="arm">
  <compiler angle="radian" meshdir="assets" autolimits="true"/>
  <option integrator="implicitfast"/>
  <default>
    <default class="arm">
      <default class="visual">
        <geom type="mesh" contype="0" conaffinity="0" group="2"/>
      </default>
      <default class="collision">
        <geom type="mesh" group="3"/>
      </default>
    </default>
  </default>
  ...
</mujoco>
```

- `angle="radian"` covers every angle in the file: `euler`, `axisangle`, a hinge's `range` and `ref`. `meshdir` is where mesh files are found, relative to the main file ([meshes.md](meshes.md)).
- One class named for the robot, set as `childclass` on its root body, holds a `visual` and a `collision` class. Joint `armature` and `damping` go in the robot's class and one actuator on each driven joint in its file, their numbers from the data sheet or from [tuning](mujoco-environment.md#tuning).

## Frames and joints

- A body's `pos` and orientation are in its parent's frame. A joint's `pos` and `axis`, and the body's geoms, sites and `<inertial>`, are in the body's own. An element takes one orientation: `quat` (w x y z), `euler`, `axisangle`, `xyaxes` or `zaxis`. `euler` is intrinsic `xyz` unless the compiler's `eulerseq` says otherwise: a URDF's `rpy` copied into it needs `eulerseq="XYZ"`.
- A body with no joint is welded to its parent: there is no fixed joint to write. A body may carry several joints, composed in order (a hinge and a slide make a cylindrical joint).
- A geom's size is half sizes where a URDF's are full: a box's half extents, a cylinder's or a capsule's radius and half length.
- Two joints that move together are an equality, `<equality><joint joint1="follower" joint2="leader" polycoef="0 1 0 0 0"/></equality>`: `joint1 = polycoef[0] + polycoef[1] * joint2`. A closed loop is a tree and `<connect site1="..." site2="..."/>` equalities where the closing joint stands, as an export writes one ([from-cad.md](from-cad.md#states-couplings-and-loops)).

## Visual and collision geoms

MuJoCo collides every geom unless told not to, and its viewer draws groups 0 to 2 and hides 3 and up. So:

- **visual** geoms take `contype="0" conaffinity="0" group="2"`, from the `visual` class.
- **collision** geoms take `group="3"`, from the `collision` class: primitives sized from the part, or coarse convex meshes. MuJoCo collides a mesh as its convex hull, so a concave part that must keep its pocket collides as several convex meshes, one geom each (for a model generated from CAD, `decompose()` in its MuJoCo function).

A geom in groups 0 to 2 that collides beside group-3 geoms is warned of as `visual_geoms_collide`, and a pair of bodies that meets at rest as `contacts_at_rest`: MuJoCo's parent filter does not cover a body welded to the world, so a base and its first link collide unless a `<contact><exclude>` names them ([mjcf-checks.md](mjcf-checks.md#model-health)).

A visual geom still carries mass. A body with no `<inertial>` is weighed from its geoms, visual and collision both, so a part that is drawn and collided counts twice (`inertia_from_visuals`). Give each body an `<inertial>` (`pos`, `mass`, and `diaginertia` or `fullinertia="ixx iyy izz ixy ixz iyz"`), computed, never guessed ([inertials.md](inertials.md)).

## Keyframes

Give the model a key named `home`, the pose a person and a controller start from. The health checks read the model there as well as at `qpos0`.

```xml
<keyframe>
  <key name="home" qpos="0 -0.7854 1.5708" ctrl="0 -0.7854 1.5708"/>
</keyframe>
```

- `qpos` holds every joint's value in the body tree's order, depth first: 1 number for a hinge or a slide, 4 for a ball (a quaternion), 7 for a free joint (position, then quaternion). `ctrl` holds one value per actuator, in actuator order.
- MuJoCo refuses a key longer than the model and pads a shorter one without a word, `qpos` with `qpos0` and `ctrl` with 0: count the values.
- MuJoCo opens a model at `qpos0` (each joint at its `ref`), not at `home`: a key is a pose to choose, in MuJoCo Studio or with `mj_resetDataKeyframe`.

What stands in for a picture of an MJCF is in [snapshots.md](snapshots.md#an-mjcf).
