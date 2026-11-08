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
