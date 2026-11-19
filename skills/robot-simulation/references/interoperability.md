# How URDF, SRDF and MJCF fit together

Read this when work touches more than one description of the same robot: what the two generated
formats say differently, and how a robot that has only a URDF gets an MJCF. Which format owns what,
and what a URDF edit asks of the SRDF beside it, are in [SKILL.md](../SKILL.md#author-by-hand).

## One description, two writers

A CAD model with a mechanism is described once and written by the destination's suffix, `cad model
export <id> robot.xml` (MJCF) or `robot.urdf` ([from CAD](from-cad.md)). Export each from the model,
never one from the other. An SRDF is always hand-written, over the generated URDF's names
([srdf-authoring.md](srdf-authoring.md)).

The two files name every link and joint alike, so a controller, an SRDF and a policy read the same
names in each, except that a URDF name keeps `[A-Za-z0-9_]` and takes `_` for any other character.
Each format keeps links and joints apart, so a link and a joint may share a name. The URDF export
says where they do, since tools that name the two together collide them (`cad urdf validate` warns
`joint_link_name_collision`): name the link apart with `link(shape, name)` (a finger's joint
`finger_left`, its link `finger_left_link`). A name already held in its kind takes `_2`.

What one format cannot say, or says its own way:

| | MJCF | URDF |
| --- | --- | --- |
| Named poses (mechanism states) | keys | not written: URDF has none (an SRDF's group states hold them for MoveIt) |
| A joint that closes a loop | a `site` on each body where it stands and an `<equality>`: two `connect`s for a hinge, one for a ball | left out, and said in the export's log: URDF is a tree |
| A ball joint | `ball` | the export is refused by name: URDF has no ball joint |
| A cylindrical joint | a hinge `<name>` and a slide `<name>/slide` on one body | `<name>` and `<name>_slide`, with a massless link `<name>_turn` between |
| A named frame (`frame()`) | a site | an empty link on a fixed joint `<frame>_joint`, as a ROS `tool0` |
| A drive's speed bound (`limits(velocity=)`) | not written: MJCF has none | `<limit velocity>` |
| The base, bolted (the default) or free (`free()`) | the base body with no joint, welded to the world, or with a `<freejoint>` | the root either way: a URDF bolts nothing (a consumer adds its own `world` link) |
| A root link with mass, or placed off the world's frame | as any body | an empty `base_link` (`base_footprint` above a root named `base_link`) on a fixed joint before it ([the base link](from-cad.md#links-and-the-base)) |
| A link with no material | no `<inertial>`: MuJoCo weighs its geoms, visual and collision both, and the check warns `inertia_from_visuals` | no `<inertial>`: `cad urdf validate` warns of a moving one |
| A part with painted faces (a STEP's or an xbf's face colours, `paint()`) | a visual geom per colour, as the viewer draws it | a `<visual>` per colour |
| Collisions | each part's mesh as a `collision` geom, which MuJoCo collides as its convex hull | each part's mesh as its `<collision>` |
| Contact exclusions | `<contact><exclude>` for every jointed pair touching at rest | not written (an SRDF's `disable_collisions` for MoveIt) |
| A simulation's choices: collision shapes, contact friction, excluded pairs, joint armature, damping and dry friction, actuators | a MuJoCo function sets them on the robot's spec and saves its file | not written: no primitive or hull `<collision>`, no `<dynamics>`; the simulator that reads the URDF makes them |

## MJCF

A robot with a CAD model here gets its MJCF from the model ([above](#one-description-two-writers)).
A robot that has only a hand-written URDF gets a first one from MuJoCo itself, which reads a URDF;
text-to-cad ships no converter in either direction. In a script `cad run` runs:

```python
import mujoco

model = mujoco.MjModel.from_xml_path("robot.urdf")
mujoco.mj_saveLastXML("robot.xml", model)   # what MuJoCo loaded, as MJCF, in radians
```

Keep the URDF the source of the structure and record its path and revision in the MJCF's ledger
comment. Never author the same robot a second time in MJCF: the two drift apart where no validator
looks. What MuJoCo makes of a URDF, by its defaults for one:

- **Visuals are dropped, and every link on a fixed joint is fused into its parent**: a
  `base_footprint`, a camera's link and a frame-only `tool0` are gone. A
  `<mujoco><compiler discardvisual="false" fusestatic="false"/></mujoco>` element inside `<robot>`
  keeps both.
- **Geoms**: a `<collision>` becomes a geom in group 0 that collides, and a kept `<visual>` one in
  group 1 that does not. Move them into a `collision` class (`group="3"`) and a `visual` class
  (`group="2"`) ([mjcf-authoring.md](mjcf-authoring.md#visual-and-collision-geoms)).
- **Meshes**: a `package://` path is not resolved, and the load fails (`Error opening file`). Make
  the paths relative to the URDF, or add `strippath="true" meshdir="meshes"` to that `<compiler>`,
  which finds each mesh by its file name in that folder. A URDF's `scale` becomes the
  `<mesh scale>`; a millimetre STL without one is 1000x too large ([meshes.md](meshes.md)).
- **Inertials** carry over. A link without one is weighed from its collision geoms at MuJoCo's
  default density, 1000 kg/m^3, which is rarely right ([inertials.md](inertials.md)).
- **Joints** keep their names, ranges and effort (as `actuatorfrcrange`), and a `<mimic>` becomes an
  `<equality><joint>`. A velocity limit is dropped.
- **What a URDF has not**: actuators, a `home` key, `<option integrator="implicitfast"/>`, the split
  into robot and scene.

The result is a draft: check it with `cad mujoco check` ([mjcf-checks.md](mjcf-checks.md)), and keep
its joint names, so the URDF, the SRDF and the MJCF name one joint one way.
