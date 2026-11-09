# How URDF, SRDF and MJCF fit together

Use this reference when work touches more than one description of the same robot, or upstream geometry, model packages, or the CAD Viewer.

## Format boundary

- **URDF** owns physical robot structure: links, joints, geometry, inertials, limits, mimic joints, transmissions, and robot-state publishing.
- **SRDF** owns MoveIt semantics: virtual joints, passive joints, planning groups, group states, end effectors, and disabled collision pairs.
- **MJCF** owns a MuJoCo model: bodies, joints, geoms, default classes, actuators, equalities and keyframes, and a scene's floor and lights.

Do not place geometry, inertials, joint origins, link poses, mesh references, physical joint limits, transmissions, or `ros2_control` interfaces in SRDF. Neither the URDF nor the MJCF defines planning groups, end-effectors, group states, or disabled-collision matrices: if the task becomes IK or path-planning work, that is the SRDF's job ([SKILL.md](../SKILL.md#srdf)).

## Ownership

- A CAD model owns everything its writers generate: frames, limits, inertials, meshes, collision shapes, named frames and poses. Fix them there and export again.
- CAD or mesh workflows own mesh generation and per-link splitting/export for a hand-written description ([meshes.md](meshes.md)).
- The URDF owns its references, scales, placements, and structure.
- SRDF/MoveIt workflows own semantic groups, named joint poses via `<group_state>`, and planning metadata. Renaming links or joints in the URDF breaks them; update both in the same task.
- An SRDF pairs with its URDF by colocation and robot name alone ([srdf-authoring.md](srdf-authoring.md#urdf-pairing-non-negotiable)).

## One description, two writers

A CAD model with a mechanism is described once (links with their frames, exact inertials, visual
meshes, collision shapes and named frames; joints with axes and limits around the as-built zero;
couplings; mechanism states as named poses; all in SI units) and written by the destination's
suffix: `cad model export <id> robot.xml` (MJCF) or `robot.urdf`. Each
writes its meshes as binary STL in metres beside the file: in `assets/` for an MJCF (its
`meshdir`), in `meshes/` for a URDF, named by relative path. The two files of one
model name every link and joint alike, so a controller, an SRDF and a policy read the same names in
each (URDF names keep `[A-Za-z0-9_]`, every other character `_`). MJCF and URDF keep links
and joints apart, so a link and a joint may share a name; a name already held in its kind is given
`_2` and the export says so. What each drops is what its format cannot say:

| | MJCF | URDF |
| --- | --- | --- |
| Named poses (mechanism states) | keys | not written: URDF has none (an SRDF's group states hold them for MoveIt) |
| Couplings | `<equality><joint>` | `<mimic>` on the follower |
| A pinion that holds no part (two slides on one `rack_and_pinion_pair`) | no body or joint: the second slide's `<equality><joint>` on the first | no link or joint: the second slide's `<mimic>` of the first |
| A joint that closes a loop | a `site` on each body where it stands and an `<equality>`: two `connect`s for a hinge, one for a ball | left out, and said in the export's log: URDF is a tree |
| Ball joints | `ball` | refused by name: URDF has no ball joint |
| Cylindrical joints | a hinge and a slide on one body | `<name>` and `<name>_slide` with a massless link `<name>_turn` between |
| Capsule collisions | `capsule` | a cylinder and a sphere at each end |
| Decomposed collisions (`collision(part, "decomposed")`) | a `collision` geom and a mesh asset per convex hull, `<part>_hull<i>` | a `<collision>` per hull, `<part>_hull<i>`, each its own mesh file |
| Named frames | sites | an empty link on a fixed joint `<frame>_joint`, as a ROS `tool0` |
| A link with no material | no `<inertial>`: MuJoCo weighs its geoms | no `<inertial>` (the validator warns of a moving one) |
| Joint effort and velocity (`limits()`) | effort as `actuatorfrcrange`; no velocity: MJCF has no speed bound | `<limit effort velocity>`; `0` where not declared, which `cad urdf validate` warns of |
| A part kept a body (`body()`) | a child body with no joint | a link on a fixed joint |
| Contact exclusions (`exclude()`) | `<contact><exclude>`, and every jointed pair touching at rest | not written (an SRDF's `disable_collisions` for MoveIt) |
| Joint dynamics (`limits(armature=, damping=, friction=)`) | `armature`, `damping`, `frictionloss` on the joint | `<dynamics damping friction>`; no armature (the export's log says so) |
| Declared masses and point masses (`mass()`, `point_mass()`) | in each body's `<inertial>` | in each link's `<inertial>` |
| Contact friction (`friction()`) | `friction` on the part's collision geoms (one value, or three) | not written: URDF has none (the export's log says so) |

The URDF's root is the first part hung from the ground (a ROS `base_link`). Never edit a generated file, and
never derive one format from another: export each from the model. An SRDF is always hand-written,
over the generated URDF's names ([srdf-authoring.md](srdf-authoring.md)).

## When the URDF changes

Renamed links or joints, changed limits, or restructured chains invalidate the SRDF silently. After any URDF edit, re-run the SRDF validator on the paired `.srdf`, and re-check group states against the new limits. Treat URDF+SRDF as a pair in every task that touches either.

## MJCF

A robot with a CAD model here gets its MJCF generated from the model ([above](#one-description-two-writers)), and its scene composed in code ([mujoco-environment.md](mujoco-environment.md)). For a robot that has only a hand-written URDF: MuJoCo loads a URDF directly (`MjModel.from_xml_path("robot.urdf")`, with a `<mujoco><compiler .../></mujoco>` extension element inside `<robot>` for its compiler settings), and its `compile` sample saves what it loaded as MJCF. That is the usual start for a robot that has a URDF; text-to-cad ships no converter in either direction. Keep the URDF the source of the structure and record it (path and revision) in the MJCF's ledger comment. Never re-author the same robot independently in MJCF: the two drift apart where no validator looks.

A converted MJCF is a draft. Fix, then validate with `cad mjcf validate --compile required` ([mjcf-checks.md](mjcf-checks.md)):

- **angle units**: the saved file may say `angle="degree"` or nothing (degrees); set `<compiler angle="radian"/>` and confirm every `range`, `ref` and `euler` is radians;
- **mesh scale**: a URDF's `scale` becomes the `<mesh scale>`; a millimetre STL without it is 1000x too large ([meshes.md](meshes.md));
- **collision groups**: a URDF's visual and collision become geoms that all collide in group 0; move them into a `visual` class (`contype="0" conaffinity="0" group="2"`) and a `collision` class (`group="3"`) ([mjcf-authoring.md](mjcf-authoring.md#visual-and-collision-geoms));
- **inertials**: a URDF's `<inertial>` carries over; a link without one gets an inertia from its geoms, visual ones included, which is rarely right ([inertials.md](inertials.md));
- **what a URDF has not**: actuators, the `home` key, `<option integrator="implicitfast"/>`, the robot/scene split.

The joint names carry over; keep them, so the URDF, the SRDF and the MJCF name one joint one way.

## CAD Viewer

CAD Viewer can review `.urdf`, `.srdf` and MJCF (`.xml` with a `<mujoco>` root, `.mjcf`) files visually and help catch gross placement or resource issues. It cannot prove simulator dynamics, inertial validity, joint-axis semantics, or planning correctness.

After creating or modifying a file, show it ([Show the model](../SKILL.md#show-the-model)). Report any failure explicitly.

An SRDF is drawn as its paired URDF's geometry, opened at its `home` group state when it declares one ([snapshots.md](snapshots.md)). An MJCF opens at `qpos0` with its keyframes as poses ([mjcf-authoring.md](mjcf-authoring.md#what-the-viewer-draws)).
