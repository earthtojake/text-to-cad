# STEP Assemblies

Multi-part `<name>.step.py` generators — anything whose `gen_step()` builds a
`children=`-style compound of named sub-parts. Single-body generators with no
`children=` live in [`../parts/`](../parts/README.md) instead.

Everything here is a **flat** single-file generator (plus an optional
`<name>.params.js` viewer parameter/animation sidecar). Anything that needs a
folder of its own — multi-file concept packages, reconstructions, robot
description packages — lives in [`../../renders/`](../../renders/README.md).

## Concept generators

- `gd01_mecha_concept`: GD01-inspired manned transformable mecha — open-cockpit
  biped with silver roll cage, glossy red armor, black understructure, and a
  parameter sidecar driving the biped-to-quadruped transformation, walk/crawl
  gaits, cockpit access, actuator demo, and exploded reveal.
- `lunar_mass_driver`: SpaceX-inspired lunar mass driver launch complex —
  speculative reusable cargo launcher (not a reconstruction) at compressed
  ~200 m diorama scale: 12 instanced coil segments climbing a vertical-easement
  ramp, levitated sled + cargo canister, retractable gantries, transfer crane,
  Starship-derived lander, control tower, solar farm, radiators, power trunks,
  rovers, drones, dust plumes, and Earth in the sky. All named scene parameters
  live on `MassDriverParams` in the generator; the sidecar adds live controls
  plus exact-loop launch/reload, coil-wave, deploy, patrol, and exploded-reveal
  animations. Sidecar constants mirror the generator defaults, so refresh them
  after rebuilding with different counts.
- `mars_rover_concept`: NASA/JPL-inspired full Mars rover on a terrain
  diorama — rocker-bogie suspension, six grousered wheels with four-corner
  steering, cutaway body with avionics/battery/science internals, mast with
  stereo head, five-joint arm with instrument turret, HGA/UHF/whip antennas,
  solar wings, and RTG. 18 geometry parameters in the generator plus a
  27-parameter sidecar with nine looped animations (terrain traverse, steering
  sweep, suspension cycle, mast scan, arm deploy, antennas + solar, cutaway
  reveal, exploded assembly, grand tour).

## Standalone demo assemblies

- `cutaway_turbofan_engine.step.py`, `flying_car.step.py`,
  `lunar_rover_corner_assembly.step.py`, `mechanical_iris_aperture.step.py`,
  `miniature_spiral_staircase.step.py`, `pelican_riding_bicycle.step.py`,
  `photo_coffee_cup.step.py`, `planetary_gear_assembly.step.py` (+
  `.params.js`), `robotic_hand_end_effector.step.py`,
  `six_axis_industrial_robot_arm.step.py`, `six_blade_open_propeller.step.py`:
  more expressive than the structured fixtures in `../parts/` and not expected
  to form a systematic test suite.
- `compact_humanoid.step.py`, `sculpted_humanoid.step.py`: two of the three
  GPT-5.6 humanoid concepts that build multi-part assemblies (the third,
  `research_humanoid`, is a single body and lives in `../parts/`).
- `spiral_staircase.step.py`, `planetary_gear_stage.step.py`: two structured
  fixtures that build multi-part compounds; the rest of that set is in
  `../parts/`. `planetary_gear_stage` imports `part_common.py` from there via a
  `sys.path` insert, so it depends on `../parts/` staying a sibling.
