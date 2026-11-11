# CAD to MuJoCo: sample projects

Two sample projects. Each takes a robot maker's raw CAD through text-to-cad's whole process -- the
assembly STEP read into a model, its parts grouped into links, its joints found from the geometry,
materials declared, the mechanism exported as URDF and made a MuJoCo file by its MuJoCo function --
and checks the result against the description Google built by hand in
[MuJoCo Menagerie](https://github.com/google-deepmind/mujoco_menagerie) and against the maker's own
URDF. They show the method on real robots, and they are samples, not a benchmark: the simulator's
choices in each MuJoCo function (which parts collide and as what, the actuators' gains) are a
sample's, chosen so the robot holds a pose, not measured. Every difference from the references is
either a fact the CAD cannot carry (actuators, gains, contact tuning), a decision the model script
made and could make better, or a gap in text-to-cad.

A robot is here only if its maker publishes the raw CAD. Of the four robots
[MuJoCo Playground](https://playground.mujoco.org/) lists, two do:

| Robot | Raw CAD | Maker's description | Menagerie model |
| --- | --- | --- | --- |
| The Robot Studio SO-101 | `SO101 Assembly.step`, SO-ARM100 (Apache-2.0) | `so101_new_calib.urdf` (onshape-to-robot) | `robotstudio_so101/so101.xml`, from the maker's MJCF |
| Trossen WidowX AI (follower) | `wxai_follower.step`, Trossen's downloads page | `wxai_follower.urdf`, trossen_arm_description (BSD-3-Clause) | `trossen_wxai/wxai_follower.xml`, from the maker's URDF |

i2rt YAM and Unitree G1 publish a URDF and meshes but no STEP: there is nothing upstream of their
descriptions to convert, so there is no sample of them.

Three more from beyond Playground are fetched and pinned, not yet converted:

| Robot | Raw CAD | Maker's description | Menagerie model |
| --- | --- | --- | --- |
| UFACTORY xArm7 (`xarm7`) | `xArm 7 (XS1305).step`, the arm alone, [UFACTORY's downloads page](https://www.ufactory.cc/downloads) (no license stated) | `xarm_device.urdf.xacro` (dof 7), xarm_ros (BSD-3-Clause) | `ufactory_xarm7/xarm7.xml` (with the gripper; `xarm7_nohand.xml` without), from the maker's URDF |
| Seeed reBot DevArm, RS build (`rebot_devarm`) | `reBot_B601_RS_v1.0_20260625.step`, the full assembly beside per-part STEPs, reBot-DevArm (CERN-OHL-W-2.0) | `ReBot_Arm_RS.urdf`, reBot-Isaacsim (MIT; its `urdf/RS/` carries CERN-OHL-W-2.0) | `seeed_rebot_devarm/seeed_rebot_devarm.xml`, from that URDF |
| ROBOTIS OP3 (`op3`) | `ROBOTIS-OP3_part_asm.stp`, ROBOTIS-OP-Series-Data (no license stated) | `robotis_op3.urdf.xacro`, ROBOTIS-OP3-Common (Apache-2.0) | `robotis_op3/op3.xml`, from the maker's URDF |

The xArm7's and the OP3's descriptions are xacro, expanded with `xacro` before a comparison reads
them.

### Candidates beyond Playground

Other Menagerie robots whose makers publish raw CAD without a login, found by reading every
Menagerie model's provenance and checking each maker's files (as of November 2026; none is wired in
yet but the three above):

| Menagerie model | Raw CAD | License | Why it is worth adding |
| --- | --- | --- | --- |
| `leap_hand` | full assembly STEP, left and right ([leaphand.com CAD page](https://v1.leaphand.com/leap_cad)) | CC BY-SA 4.0 | a dexterous hand: many joints, a real multi-body assembly |
| `robotiq_2f85`, `robotiq_2f85_v4` | the assembly STEP Menagerie's v4 README names as its own source | not stated | a small, well-known gripper with a linkage: low risk |
| `trs_so_arm100` | `SO_5DOF_ARM100_Assembly.step` in the same SO-ARM100 repository | Apache-2.0 | the SO-101's predecessor: almost free given SO-101 |
| `low_cost_robot_arm` | `arm.step` and per-part STEPs in AlexanderKoch-Koch/low_cost_robot | MIT | printed parts and servos, as SO-101, from another maker |
| `ufactory_lite6` | one STEP per arm on UFACTORY's downloads page (the xArm7's is fetched above) | not stated | a second industrial arm, likely fused bodies: the link split must be recovered |
| `tetheria_aero_hand_open` | left and right STEP in TetherIA/aero-hand-open | CC BY-NC-SA 4.0 | a second hand; non-commercial |

Not possible as a sample: Pollen Robotics' Microduck (not in Menagerie; its CAD is an Onshape document that needs an account to export, its public meshes are CC BY-NC-SA, and its MJCF in microduck_rl was made from that same document by onshape-to-robot, so there is no independent hand-made reference), Universal Robots (STEP behind a login), Franka (SolidWorks native, no STEP), the
Onshape-sourced models (an export needs an account, and Menagerie's model was made from the same
document), and most others (no raw CAD published).

## Running it

```bash
cd models/mujoco
python3 src/fetch.py              # the STEPs, the makers' URDFs and Menagerie, pinned (src/sources.py)
python3 src/fetch.py op3          # one robot: so101, wxai, xarm7, rebot_devarm, op3
python src/so101.py               # the model: reads the STEP, exports out/so101/export/so101.{xml,urdf}
python src/so101_mujoco.py        # its MuJoCo function: saves out/so101/so101.xml, assets/ and scene.xml
python src/wxai.py
python src/wxai_mujoco.py
python src/check.py               # the proof each robot works, with numbers
python src/compare.py             # reports/<robot>.md and .json
cad run mujoco-studio --model out/so101/scene.xml   # look at it in MuJoCo Studio
```

Each robot is two scripts. The model (`src/<robot>.py`) holds what is true of the machine: parts,
materials, joints, stops, the drives' published torque and speed, frames. Its plain exports collide
each part as its mesh and have no actuators. The MuJoCo function (`src/<robot>_mujoco.py`) holds what
is chosen for a simulation: it makes the model a `mujoco.MjSpec` (`cad.mujoco.spec`), chooses each
part's collision, adds a position actuator a joint and a key that commands a pose, and saves the
robot's file (`cad.mujoco.save`). `compare.py` compares that file with Menagerie's, and the plain URDF
with the maker's. `check.py` compiles the saved file, runs `cad mujoco check`'s checks, loads the folder after
copying it elsewhere, counts the collision geoms and holds the commanded pose under gravity.

An MJCF is MuJoCo's own file: cad writes it and checks it (`cad mujoco check out/so101/so101.xml`: what
MuJoCo refuses or warns of, what collides as what, the contact excludes) and MuJoCo Studio shows it.
The CAD Viewer shows the model and the plain URDF.

Everything fetched or written lands in folders Git ignores (`upstream/`, `menagerie/`, `out/`,
`reports/`): the repository holds the scripts alone, and every source is pinned by commit or by
SHA-256, so a run is reproducible.

## Results so far

Status, November 2026: both robots converted, exported, validated and compared. Per-robot working
notes, with every decision and its source, are in [notes/](notes/).

**WidowX AI** (`python src/compare.py wxai`; full notes in [notes/wxai.md](notes/wxai.md)):

| Measure | vs Menagerie | vs Trossen's URDF |
| --- | --- | --- |
| Joints paired by name | 8 of 8 | 8 of 8 |
| Worst axis angle / axis-line offset | 0.12 deg / 1.25 mm | 0.27 deg / 0 mm |
| Calibration offsets (their value at our zero) | at most 0.3 deg | at most 0.3 deg |
| Total mass | -2.7% (calibrated to Trossen's 4 kg spec) | same |
| Worst link mass / COM | 25% / 16 mm | same |
| Gravity torque error | 9.7% RMS | same |

The joints were found from the bearing cylinders each parent and child share, and agree with the
STEP's part placements to 0.000 mm (one 0.40 mm). The mass is the weak point: Trossen's STEP draws each
link as a filled "dummy" block in steel, so it cannot say where the motors are. The gripper stroke
measured on the CAD (22 mm per side, to the end stop) disagrees with Menagerie's -10 to 45 mm.

**SO-101** (`python src/compare.py so101`; full notes in [notes/so101.md](notes/so101.md)):

| Measure | vs Menagerie | vs the maker's URDF |
| --- | --- | --- |
| Joints paired by name | 6 of 6 | 6 of 6 |
| Axes | within 0.5-1 deg but two (below) | same |
| Total mass | -1.3% (636.8 vs 645.4 g) | +0.8% |
| Per-link mass | within 0-4% but the base (-10%) and the jaw | same |
| Gravity torque error | 5.8% RMS | 1.5% RMS |

The STEP is the full assembly: printed parts, six ST3215 servos with their internals, 65 screws and
nuts. The one human input is which printed parts form which link; every other part goes to the link it
touches, a servo as a unit by its case and its horns to the link they drive, which reproduces the
maker's grouping. Each axis is the drive horn's rim, checked against the parts' own bores (0.00 mm).
The joint stops come from a self-collision sweep of the CAD (`src/so101_ranges.py`, written before
`cad model ranges` shipped; its numbers are the ones `so101.py` writes), within 5-10 deg of
the references, with no number taken from them. Mass: printed parts as PLA with a 0.8 mm solid skin
and the maker's 15% infill (277 g where solid would be 709 g), each servo at its published 55 g (the
STEP's servo model overlaps itself), fasteners at the STEP's own steels. The two axes that differ, the
gripper (15 deg) and wrist roll (5.3 mm line offset), differ the same against both references and agree
with the STEP's bores: the STEP carries newer revisions of those parts (follower v10, jaw v3) than the
references' meshes (v1). The jaw's mass is high because the servo's horns turn with it here; Menagerie
also has a camera mount this STEP does not.

**Do the robots work?** (`python src/check.py`, MuJoCo 4.0.0, Linux x86-64.) Each saved file
compiles, loads after its folder is copied elsewhere, and has no health-check error:

| Measure | SO-101 | WidowX AI |
| --- | --- | --- |
| Bodies / joints / actuators / keys | 7 / 6 / 6 / 1 (`home`) | 9 / 8 / 8 / 2 (`gripper_open`, `home`) |
| Mass | 0.6368 kg | 4.0001 kg |
| Collision geoms | 31 (18 box, 13 mesh) | 13 (13 mesh) |
| Health-check warnings | none | 1: link_2 and link_5's hulls meet by 1.43 mm in the folded pose |
| Holds `home` under gravity: 2500 steps of 2 ms, threshold 0.02 | worst joint elbow_flex, 0.0072 rad off, no contact (kp 60) | worst joint joint_3, 0.0134 rad off, no contact (kp 600, 100; carriages 10000) |
| Plain `export/<robot>.xml` | no errors, no warnings | no errors; the same warning, and the two carriages' hulls (18.5 mm) |
| Plain `export/<robot>.urdf` | no errors, no warnings | no errors; 2 warnings: the carriage joints have no published speed |

**The comparison tool** never compares joint values or frames directly: it registers the root links'
shapes, then finds each joint's matching pose, parent first. Validated by its self-test (an imposed
transform recovered to 1e-12, offsets to 1e-5 deg) and by Menagerie against the SO-101 maker's own
URDF (0.000 deg offsets, 0.04 mm shapes). It also found two facts about the references: Menagerie's
SO-101 carries a camera mount (+13.4 g) the plain vendor URDF lacks, and Menagerie's WidowX meshes
are not Trossen's pinned STLs.

## What the samples found in text-to-cad

Fixed: a vendor STEP's densities read 1000 times too light (OCCT drops the "kilo" of kg/m^3; our own
STEPs say grams, so no test saw it). Every gap below is fixed on this branch too; they stay listed,
ranked by how much they cost a CAD-to-simulation user:

1. **Fixed: mass from a STEP that does not carry it.** There was no way to give a link a measured mass
   (scale its parts' densities to a target) or a mass budget for parts the CAD omits (motors in a dummy
   link). `mass(part_or_assembly, grams)` now scales a node's solids alike to a measured total (an inner
   one fixing its own subtree), and `point_mass(part, grams, at)` puts a motor where it sits, counted in
   every total above it.
2. **Fixed: a fixed part cannot stay its own body.** Every rigidly joined part merged into its link,
   so a camera mount or a fingertip could not be addressed as Menagerie's can; `body(part, name)` now
   keeps it a body fixed to its link.
3. **Fixed: no coupling between two slides.** `rack_and_pinion_pair` and `gear_pair` refused two
   prismatic joints, so a parallel gripper's mirrored fingers could not be one control. A pinion that
   holds no part (a `RevoluteJoint` on the palm, connected to nothing, named first) now couples them:
   the MJCF writes no body for it and the second finger's `<equality><joint>` on the first, the URDF
   its `<mimic>`, one control as Menagerie has.
4. **Fixed: no contact exclusion.** Hulls of adjacent links that overlap at rest needed `<exclude>`; the
   MJCF writer now excludes every jointed pair touching at rest (the world-welded first joint's too).
   Any other pair is the MuJoCo function's, in MuJoCo's own API (`s.add_exclude`).
5. **Fixed: one convex hull per part.** A concave part (a link with a pocket, a gripper body) collided
   as its hull. `cad.mujoco.decompose(s, part, max_hulls=, threshold=)`, in the MuJoCo function, now
   collides it as the convex hulls CoACD cuts its mesh into (`cad[coacd]`), one geom each
   (`<part>_hull<i>`), while its visual stays whole; the hulls are cached by the part's mesh and
   options. `fit(s, part, kind)` collides a part as a primitive fitted to its exact solid.
6. **Fixed: the joint recipe is fragile on a vendor STEP.** Face axes carry 1e-17 noise that can flip
   build123d's default plane X, turning a link 90 deg at angle 0. kinematics.md's recipe now builds the
   rigid joint from the hinge's own frame (`hinge.location`) and snaps a direction read from geometry,
   and the engine refuses a child that `connect_to` turned at its joint's zero though it was built
   where it stands, naming the joint, the turn and the frame to use.
7. **Fixed: URDF details.** Joint limits were written with effort and velocity 0, and a joint was silently
   renamed when it shared a link's name (`gripper` became `gripper_2`). `limits(assembly, joint,
   effort=, velocity=)` gives the drive's limits (`cad urdf validate` warns of a 0), and links and
   joints are named in their own kinds.
8. **Fixed: no joint limits from geometry.** The STEP has no stops; a model script's own self-collision
   sweep found them for SO-101 in 41 s. `cad model ranges` (also `cad xbf|step ranges`) now sweeps each
   joint alone until its parts meet and prints a table of each joint's stops (0.3 mm by default;
   `--joint` names the joints to sweep).
9. **Fixed: reading a large STEP is slow to work with.** build123d's `located` on a `step.read` leaf
   deep-copies the whole tree (7 s and 400 MB a call); `leaves(tree)` (`cad.build123d`) now places a read
   tree's leaves on its own B-rep without the copy. And a snapshot of the exported robot
   failed when the daemon started without a display; a snapshot the daemon cannot draw is now drawn by
   the calling process where it has a display (`xvfb-run cad urdf snapshot ...`).
10. **Fixed: nowhere to put a simulation's choices.** A servo's reflected inertia, damping and dry
   friction, a surface's contact friction, actuators, gains and contact tuning are not facts the CAD
   holds. They go in the robot's MuJoCo function, on the `mujoco.MjSpec` `cad.mujoco.spec` makes of
   the model, in MuJoCo's own API (`joint.armature`, `geom.friction`, `s.add_actuator`), and
   `cad.mujoco.save` writes the robot's file. The model keeps the hardware's facts, the drive's
   torque and speed among them (`limits(assembly, joint, effort=, velocity=)`).
11. **Fixed: no way to list a spec's parts.** The SO-101 has 133 parts and its MuJoCo function chooses
   by a rule (every part but the printed ones and the servo cases collides as nothing), but a part
   could only be named one at a time, and a wrong name listed the first twelve. `cad.mujoco.parts(s)`
   now answers every part's label path. Found by porting these samples to MuJoCo functions.
