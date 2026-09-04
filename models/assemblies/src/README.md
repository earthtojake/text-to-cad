# assemblies models

The repo's demo assemblies as one `$cad-project`, one group per assembly:
`src/<assembly>/` holds the root model plus every part model and helper that
assembly owns, and its artifacts land in `STEP/<assembly>/` (meshes in
`STL/<assembly>/`, `3MF/<assembly>/`, `GLB/<assembly>/`). Standalone parts
live in the sibling `models/examples/` project and 2D drawings in
`models/drawings/`. Nothing here is committed except this `src/` tree — build
what you need.

```bash
python models/assemblies/src/flying_car/flying_car.py       # one assembly and whatever is stale beneath it
ls models/assemblies/src/*/*.py | xargs -n1 -P4 python       # every model
```

Unchanged models are no-ops. A group is self-contained: its scripts import
siblings and its own `lib/` with no path setup (python puts the script's
directory on `sys.path`), and nothing imports across groups.

Two models carry kinematics and choreography: `planetary_gear_assembly`
(mates + a `drive` coupling + `quarter_cycle`/`half_cycle` poses) and
`mars_rover_concept` (27 mates, 7 couplings, 4 poses). Their `.anim.js` clips
sit beside the scripts and are copied into the artifact sidecar at build.
`miniature_spiral_staircase` declares a `_highres` mesh variant at
`mesh_tolerance=4e-4` to exercise the tolerance path.

### Single-model assemblies

One script per group: the assembly is composed inside one model body.

| Script | Artifact | Description |
|--------|----------|-------------|
| `compact_humanoid/compact_humanoid.py` | `STEP/compact_humanoid/compact_humanoid.step` | Original 28-DOF compact humanoid research platform concept |
| `cutaway_turbofan_engine/cutaway_turbofan_engine.py` | `STEP/cutaway_turbofan_engine/cutaway_turbofan_engine.step` | Labeled multi-body cutaway turbofan display model |
| `flying_car/flying_car.py` | `STEP/flying_car/flying_car.step` | Four-rotor flying car concept |
| `lunar_rover_corner_assembly/lunar_rover_corner_assembly.py` | `STEP/lunar_rover_corner_assembly/lunar_rover_corner_assembly.step` | Lunar rover corner module: wheel, hub motor, suspension |
| `mars_rover_concept/mars_rover_concept.py` | `STEP/mars_rover_concept/mars_rover_concept.step` | Mars rover concept on terrain, mated + animated |
| `mechanical_iris_aperture/mechanical_iris_aperture.py` | `STEP/mechanical_iris_aperture/mechanical_iris_aperture.step` | Labeled mechanical iris aperture assembly |
| `miniature_spiral_staircase/miniature_spiral_staircase.py` | `STEP/miniature_spiral_staircase/miniature_spiral_staircase.step + STL/miniature_spiral_staircase/miniature_spiral_staircase_highres.stl, 3MF/miniature_spiral_staircase/miniature_spiral_staircase_highres.3mf, GLB/miniature_spiral_staircase/miniature_spiral_staircase_highres.glb` | Labeled miniature spiral staircase STEP compound |
| `motorcycle_shock_absorber/motorcycle_shock_absorber.py` | `STEP/motorcycle_shock_absorber/motorcycle_shock_absorber.step` | Motorcycle rear shock absorber (coilover damper) assembly |
| `pelican_riding_bicycle/pelican_riding_bicycle.py` | `STEP/pelican_riding_bicycle/pelican_riding_bicycle.step` | Pelican riding a bicycle (organic + mechanical mix) |
| `photo_coffee_cup/photo_coffee_cup.py` | `STEP/photo_coffee_cup/photo_coffee_cup.step` | Photo-inspired takeaway coffee cup model |
| `planetary_gear_assembly/planetary_gear_assembly.py` | `STEP/planetary_gear_assembly/planetary_gear_assembly.step + STL/planetary_gear_assembly/planetary_gear_assembly.stl, 3MF/planetary_gear_assembly/planetary_gear_assembly.3mf, GLB/planetary_gear_assembly/planetary_gear_assembly.glb` | Labeled simplified planetary gear assembly |
| `planetary_gear_stage/planetary_gear_stage.py` | `STEP/planetary_gear_stage/planetary_gear_stage.step` | Simplified planetary gear assembly |
| `robotic_hand_end_effector/robotic_hand_end_effector.py` | `STEP/robotic_hand_end_effector/robotic_hand_end_effector.step` | Labeled cybernetic robotic hand end-effector STEP assembly |
| `sculpted_humanoid/sculpted_humanoid.py` | `STEP/sculpted_humanoid/sculpted_humanoid.step` | Sculpted full-scale humanoid research platform |
| `six_axis_industrial_robot_arm/six_axis_industrial_robot_arm.py` | `STEP/six_axis_industrial_robot_arm/six_axis_industrial_robot_arm.step` | Labeled six-axis industrial robot arm display assembly |
| `six_blade_open_propeller/six_blade_open_propeller.py` | `STEP/six_blade_open_propeller/six_blade_open_propeller.step` | Six-blade open propeller |
| `spiral_staircase/spiral_staircase.py` | `STEP/spiral_staircase/spiral_staircase.step` | Miniature spiral staircase model |

### Multi-model assemblies

Groups whose root links other models in the same directory; running the root
builds the stale children in parallel and links their results.

| Script | Artifact | Description |
|--------|----------|-------------|
| `research_humanoid/research_humanoid.py` | `STEP/research_humanoid/research_humanoid.step` | Production-realistic, adult-scale humanoid research platform; links the two hand models below |
| `research_humanoid/research_humanoid_hand_left.py` | `STEP/research_humanoid/research_humanoid_hand_left.step` | Its left 15-axis dexterous hand, a sub-assembly model (`lib/research_humanoid_lib.build_hand`) |
| `research_humanoid/research_humanoid_hand_right.py` | `STEP/research_humanoid/research_humanoid_hand_right.step` | The right hand — a mirror image, so its own model from the same factory |
| `link_robot/link_robot.py` | `STEP/link_robot/link_robot.step` | Three-level link tree used by the store tests: a base, two placements of `link_arm`, one of `link_pin` |
| `link_robot/link_arm.py` | `STEP/link_robot/link_arm.step` | A bar plus two placements of the pin model |
| `link_robot/link_pin.py` | `STEP/link_robot/link_pin.step` | The leaf: a plain cylinder |

`planetary_gear_stage/lib/gear_teeth.py` is that group's own copy of the two
gear-profile helpers it needs; the parts in `models/examples` keep theirs in
`lib/part_common.py`, because a group never imports across projects.

Build: `python src/<group>/<group>.py` per group; unchanged models are no-ops.
