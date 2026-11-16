# How URDF, SRDF and MJCF fit together

Use this reference when work touches more than one description of the same robot, or upstream geometry, model packages, or the CAD Viewer.

## Format boundary

- **URDF** owns physical robot structure: links, joints, geometry, inertials, limits, mimic joints, transmissions, and robot-state publishing.
- **SRDF** owns MoveIt semantics: virtual joints, passive joints, planning groups, group states, end effectors, and disabled collision pairs.
- **MJCF** owns a MuJoCo model: bodies, joints, geoms, default classes, actuators, equalities and keyframes, and a scene's floor and lights.

Do not place geometry, inertials, joint origins, link poses, mesh references, physical joint limits, transmissions, or `ros2_control` interfaces in SRDF. Neither the URDF nor the MJCF defines planning groups, end-effectors, group states, or disabled-collision matrices: if the task becomes IK or path-planning work, that is the SRDF's job ([SKILL.md](../SKILL.md#srdf)).

## Ownership

- A CAD model owns everything its writers generate: frames, limits, inertials, meshes, named frames and poses. Fix them there and export again. A robot's MuJoCo function owns a simulation's choices on it: collision shapes, contact friction, excluded pairs, joint dynamics, actuators ([mujoco-environment.md](mujoco-environment.md#the-mujoco-function)).
- CAD or mesh workflows own mesh generation and per-link splitting/export for a hand-written description ([meshes.md](meshes.md)).
- The URDF owns its references, scales, placements, and structure.
- SRDF/MoveIt workflows own semantic groups, named joint poses via `<group_state>`, and planning metadata. Renaming links or joints in the URDF breaks them; update both in the same task.
- An SRDF pairs with its URDF by colocation and robot name alone ([srdf-authoring.md](srdf-authoring.md#urdf-pairing-non-negotiable)).

## One description, two writers

A CAD model with a mechanism is described once (links with their frames, exact inertials, visual
meshes, each part's mesh as its collision, and named frames; joints with axes and limits around the as-built zero;
couplings; mechanism states as named poses; all in SI units) and written by the destination's
suffix: `cad model export <id> robot.xml` (MJCF) or `robot.urdf`. Each
writes its meshes as binary STL in metres beside the file: in `assets/` for an MJCF (its
`meshdir`), in `meshes/` for a URDF, named by relative path. An export lists the meshes it wrote
there (`.robot.xml.meshes`), and the next export of that file removes those it no longer names (parts
renamed or gone), never a file it did not write nor one another robot's list names. The two files of one
model name every link and joint alike, so a controller, an SRDF and a policy read the same names in
each (URDF names keep `[A-Za-z0-9_]`, every other character `_`). MJCF and URDF keep links
and joints apart, so a link and a joint may share a name, which the URDF export says (`cad urdf
validate` warns `joint_link_name_collision`: some tools name the two together); name the link apart
with `link(shape, name)` (a finger's joint `finger_left`, its link `finger_left_link`). A name already
held in its kind is given `_2` and the export says so. What each drops is what its format cannot say:

| | MJCF | URDF |
| --- | --- | --- |
| Named poses (mechanism states) | keys | not written: URDF has none (an SRDF's group states hold them for MoveIt) |
| Couplings | `<equality><joint>` | `<mimic>` on the follower |
| A pinion that holds no part (two slides on one `rack_and_pinion_pair`) | no body or joint: the second slide's `<equality><joint>` on the first | no link or joint: the second slide's `<mimic>` of the first |
| A joint that closes a loop | a `site` on each body where it stands and an `<equality>`: two `connect`s for a hinge, one for a ball | left out, and said in the export's log: URDF is a tree |
| Ball joints | `ball` | refused by name: URDF has no ball joint |
| Cylindrical joints | a hinge and a slide on one body | `<name>` and `<name>_slide` with a massless link `<name>_turn` between |
| Collisions | each part's mesh as a `collision` geom, which MuJoCo collides as its convex hull | each part's mesh as its `<collision>` |
| Named frames | sites | an empty link on a fixed joint `<frame>_joint`, as a ROS `tool0` |
| A link with no material | no `<inertial>`: MuJoCo weighs its geoms | no `<inertial>` (the validator warns of a moving one) |
| A part with painted faces (a STEP's or xbf's face colours, `paint()`) | a visual geom per colour, as the viewer draws it, each `mass="0"` on a mesh with `inertia="shell"` | a `<visual>` per colour |
| Joint effort and velocity (`limits()`) | effort as `actuatorfrcrange`; no velocity: MJCF has no speed bound | `<limit effort velocity>`; `0` where not declared, which `cad urdf validate` warns of |
| A part kept a body (`body()`) | a child body with no joint | a link on a fixed joint |
| Contact exclusions | `<contact><exclude>` for every jointed pair touching at rest | not written (an SRDF's `disable_collisions` for MoveIt) |
| A simulation's choices: collision shapes, contact friction, excluded pairs, joint armature, damping and dry friction, actuators | not in the plain export: a MuJoCo function sets them on the robot's spec and saves its file | not written: no primitive or hull `<collision>`, no `<dynamics>`; the simulator that reads the URDF makes them |
| Declared masses and point masses (`mass()`, `point_mass()`) | in each body's `<inertial>` | in each link's `<inertial>` |
| A free base (`free()`) | a `<freejoint>` on the base body, its position and quaternion in every key | the root, which floats already; no world link or joint |
| A bolted base (the default) | the base body with no joint, welded to the world | the root too: a URDF bolts nothing (a consumer adds its own `world` link) |
| A root link with mass, or placed off the world's frame | as any body | an empty `base_link` (`base_footprint` where the root is named `base_link`, as REP 105 roots a base) on a fixed joint before it, at the root's placement: KDL takes no inertia on the root |
| A zero state (`--zero home`) | every body at the state, ranges and keys around it | every link at the state, limits around it |
| A scene | `scene.xml` beside it, written once when there is none, never written over | none |

A URDF carries the robot's structure, mass and limits: its links, its joints with `<limit lower
upper effort velocity>`, exact inertials, visual meshes with their colours, each part's mesh as its
`<collision>`, frames as empty links, couplings as `<mimic>`, the root handling, a floating base and
`--zero`. What a simulator chooses for it is made in that simulator.

The URDF's root is the link hung from the ground, under an empty `base_link` (`base_footprint` above a root named `base_link`) where it has a mass or stands off the world's frame. Never edit a
generated file (the `scene.xml` an MJCF export writes once is yours), and
never derive one format from another: export each from the model. An SRDF is always hand-written,
over the generated URDF's names ([srdf-authoring.md](srdf-authoring.md)).

## When the URDF changes

Renamed links or joints, changed limits, or restructured chains invalidate the SRDF silently. After any URDF edit, re-run the SRDF validator on the paired `.srdf`, and re-check group states against the new limits. Treat URDF+SRDF as a pair in every task that touches either.

## MJCF

A robot with a CAD model here gets its MJCF generated from the model ([above](#one-description-two-writers)), and its scene composed in code ([mujoco-environment.md](mujoco-environment.md)). For a robot that has only a hand-written URDF: MuJoCo loads a URDF directly (`MjModel.from_xml_path("robot.urdf")`, with a `<mujoco><compiler .../></mujoco>` extension element inside `<robot>` for its compiler settings), and its `compile` sample saves what it loaded as MJCF. That is the usual start for a robot that has a URDF; text-to-cad ships no converter in either direction. Keep the URDF the source of the structure and record it (path and revision) in the MJCF's ledger comment. Never re-author the same robot independently in MJCF: the two drift apart where no validator looks.

A converted MJCF is a draft. Fix, then check with `cad mujoco check` ([mjcf-checks.md](mjcf-checks.md)):

- **angle units**: the saved file may say `angle="degree"` or nothing (degrees); set `<compiler angle="radian"/>` and confirm every `range`, `ref` and `euler` is radians;
- **mesh scale**: a URDF's `scale` becomes the `<mesh scale>`; a millimetre STL without it is 1000x too large ([meshes.md](meshes.md));
- **collision groups**: a URDF's visual and collision become geoms that all collide in group 0; move them into a `visual` class (`contype="0" conaffinity="0" group="2"`) and a `collision` class (`group="3"`) ([mjcf-authoring.md](mjcf-authoring.md#visual-and-collision-geoms));
- **inertials**: a URDF's `<inertial>` carries over; a link without one gets an inertia from its geoms, visual ones included, which is rarely right ([inertials.md](inertials.md));
- **what a URDF has not**: actuators, the `home` key, `<option integrator="implicitfast"/>`, the robot/scene split.

The joint names carry over; keep them, so the URDF, the SRDF and the MJCF name one joint one way.

## CAD Viewer

CAD Viewer can review `.urdf` and `.srdf` files visually and help catch gross placement or resource issues. It does not open an MJCF: that is MuJoCo's own file, which the person opens in MuJoCo Studio (`cad run mujoco-studio --model scene.xml`). It cannot prove simulator dynamics, inertial validity, joint-axis semantics, or planning correctness.

After creating or modifying a file, show it ([Show the model](../SKILL.md#show-the-model)). Report any failure explicitly.

An SRDF is drawn as its paired URDF's geometry, opened at its `home` group state when it declares one ([snapshots.md](snapshots.md)).
