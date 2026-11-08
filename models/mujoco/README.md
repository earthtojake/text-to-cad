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
