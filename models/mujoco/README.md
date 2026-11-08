# CAD to MuJoCo benchmark

Takes a robot maker's raw CAD through text-to-cad's whole process -- the assembly STEP read into a
model, its parts grouped into links, its joints found from the geometry, materials and collision
declared, the mechanism exported as MJCF, URDF and SDF -- and compares the result with the
description Google built by hand in [MuJoCo Menagerie](https://github.com/google-deepmind/mujoco_menagerie)
and with the maker's own URDF. The comparison is what refines the method: every difference is
either a fact the CAD cannot carry (actuators, damping, contact tuning), a decision the model
script made and should make better, or a gap in text-to-cad.

A robot is here only if its maker publishes the raw CAD. Of the four robots
[MuJoCo Playground](https://playground.mujoco.org/) lists, two do:

| Robot | Raw CAD | Maker's description | Menagerie model |
| --- | --- | --- | --- |
| The Robot Studio SO-101 | `SO101 Assembly.step`, SO-ARM100 (Apache-2.0) | `so101_new_calib.urdf` (onshape-to-robot) | `robotstudio_so101/so101.xml`, from the maker's MJCF |
| Trossen WidowX AI (follower) | `wxai_follower.step`, Trossen's downloads page | `wxai_follower.urdf`, trossen_arm_description (BSD-3-Clause) | `trossen_wxai/wxai_follower.xml`, from the maker's URDF |

i2rt YAM and Unitree G1 publish a URDF and meshes but no STEP: there is nothing upstream of their
descriptions to convert, so they are not benchmarked.

### Candidates beyond Playground

Other Menagerie robots whose makers publish raw CAD without a login, found by reading every
Menagerie model's provenance and checking each maker's files (as of November 2026; none is wired in
yet):

| Menagerie model | Raw CAD | License | Why it is worth adding |
| --- | --- | --- | --- |
| `leap_hand` | full assembly STEP, left and right ([leaphand.com CAD page](https://v1.leaphand.com/leap_cad)) | CC BY-SA 4.0 | a dexterous hand: many joints, a real multi-body assembly |
| `robotiq_2f85`, `robotiq_2f85_v4` | the assembly STEP Menagerie's v4 README names as its own source | not stated | a small, well-known gripper with a linkage: low risk |
| `trs_so_arm100` | `SO_5DOF_ARM100_Assembly.step` in the same SO-ARM100 repository | Apache-2.0 | the SO-101's predecessor: almost free given SO-101 |
| `low_cost_robot_arm` | `arm.step` and per-part STEPs in AlexanderKoch-Koch/low_cost_robot | MIT | printed parts and servos, as SO-101, from another maker |
| `ufactory_xarm7`, `ufactory_lite6` | one STEP per arm on UFACTORY's downloads page | not stated | industrial arms, likely fused bodies: the link split must be recovered |
| `tetheria_aero_hand_open` | left and right STEP in TetherIA/aero-hand-open | CC BY-NC-SA 4.0 | a second hand; non-commercial |
| `robotis_op3`, `seeed_rebot_devarm` | one assembly STEP / per-part STEPs | none stated / CERN-OHL-W | a humanoid; an arm without its actuators |

Not benchmarkable: Universal Robots (STEP behind a login), Franka (SolidWorks native, no STEP), the
Onshape-sourced models (an export needs an account, and Menagerie's model was made from the same
document), and most others (no raw CAD published).

## Running it

```bash
cd models/mujoco
python3 src/fetch.py              # the STEPs, the makers' URDFs and Menagerie, pinned (src/sources.py)
python src/so101.py               # the model: reads the STEP, exports out/so101/so101.{xml,urdf,sdf}
python src/wxai.py
python src/compare.py             # reports/<robot>.md and .json
cad run mujoco-studio --model out/so101/so101.xml   # look at it in MuJoCo Studio
```

Everything fetched or written lands in folders Git ignores (`upstream/`, `menagerie/`, `out/`,
`reports/`): the repository holds the scripts alone, and every source is pinned by commit or by
SHA-256, so a run is reproducible.

## Results so far

Status, November 2026: WidowX AI done end to end; SO-101's model (`src/so101.py`, in progress)
reads the STEP and groups its 80 occurrences into links, its comparison not yet run. Per-robot
working notes are in [notes/](notes/).

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

**The comparison tool** never compares joint values or frames directly: it registers the root links'
shapes, then finds each joint's matching pose, parent first. Validated by its self-test (an imposed
transform recovered to 1e-12, offsets to 1e-5 deg) and by Menagerie against the SO-101 maker's own
URDF (0.000 deg offsets, 0.04 mm shapes). It also found two facts about the references: Menagerie's
SO-101 carries a camera mount (+13.4 g) the plain vendor URDF lacks, and Menagerie's WidowX meshes
are not Trossen's pinned STLs.

## What the benchmark found in text-to-cad

Fixed: a vendor STEP's densities read 1000 times too light (OCCT drops the "kilo" of kg/m^3; our own
STEPs say grams, so no test saw it). Open, ranked by how much they cost a CAD-to-simulation user:

1. **Mass from a STEP that does not carry it.** No way to give a link a measured mass (scale its
   parts' densities to a target) or a mass budget for parts the CAD omits (motors in a dummy link).
2. **A fixed part cannot stay its own body.** Every rigidly joined part merges into its link, so a
   camera mount or a fingertip cannot be addressed in the simulator as Menagerie's can.
3. **No coupling between two slides.** `rack_and_pinion_pair` and `gear_pair` refuse two prismatic
   joints, so a parallel gripper's mirrored fingers cannot be one control.
4. **No contact exclusion.** Hulls of adjacent links that overlap at rest need `<exclude>`, which a model
   cannot declare.
5. **One convex hull per part.** A concave part (a link with a pocket, a gripper body) collides as its
   hull; a convex decomposition or per-face primitives would be closer.
6. **The joint recipe is fragile on a vendor STEP.** Face axes carry 1e-17 noise that can flip build123d's
   default plane X, turning a link 90 deg at angle 0; build the rigid joint from the hinge's own frame.
7. **URDF details:** joint limits written with effort and velocity 0, and a joint renamed when it shares
   a link's name, which breaks a mimic.
8. **Actuators, armature, damping, contact parameters** are the consumer's own and never come from CAD;
   a documented scene layer (native `MjSpec`) is the place, and the skill shows it.
