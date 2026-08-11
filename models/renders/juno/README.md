# juno — compact humanoid robotics platform concept

A sleek research-humanoid CAD concept with Unitree-G1-like proportions:
~1.40 m tall, athletic ready stance, exposed cylindrical actuator modules at
every joint, warm-porcelain composite shells over graphite structure with
machined-aluminum joint rims, coral-orange accents on repeated functional
details (actuator hubs, toe/heel bumpers, head vents, fingertip pads), a
gloss midnight-blue sensor visor displaying cyan pixel-grid eyes (Anki
Cozmo style), and dexterous five-digit hands. Clean industrial design,
no logos.

## Degrees of freedom (27 body DOF)

| Group | Joints | DOF |
| --- | --- | --- |
| Each leg (x2) | hip yaw, hip roll, hip pitch, knee, ankle pitch, ankle roll | 12 |
| Each arm (x2) | shoulder pitch, shoulder roll, shoulder yaw, elbow, wrist roll, wrist pitch | 12 |
| Waist | yaw | 1 |
| Neck | yaw, pitch | 2 |

Hands add posed (cosmetic) finger articulation on top of the 27 counted DOF.

## Files

- `juno.py` — build123d generator (`gen_step()`); authoritative source.
  Pose angles are module-level parameters; joints are authored as
  `cadgen.assembly.AssemblyHelper` revolute frames driven by those angles.
- `juno_parts/` — part-builder package (sculpted segments, joint hardware,
  shared style library). Each builder returns an identity-location labeled
  compound in its part-local frame. `chain.py` is the shared kinematic
  chain/pose/limit spec used by the CAD assembly and mirrored by the
  authored URDF/SRDF artifacts.
- `juno.step` — generated STEP assembly (derived artifact).
- `juno.params.js` — CAD Viewer animation sidecar with four in-place gaits
  built on per-frame chain FK plus two-link leg IK around the baked
  athletic stance: `walkLoop` (march, planted stance feet), `strideLoop`
  (treadmill-style strides, stance foot slides flat on the ground),
  `runLoop` (flight phases, body bounce, toe-pivot push-off, pumping bent
  arms, forward lean), and `jumpLoop` (countermovement hop with hands
  overhead and an underdamped springy landing). All gaits share antiphase
  arm swing, torso counter-sway, and head stabilization. Three showpiece
  loops: `danceLoop` (Elvis: right finger pointing up to the right, left
  leg kicked out to the left on a shaking planted toe via closed-form
  lateral+sagittal leg IK), `handstandLoop` (toe-pivot fold to a
  palms-flat inverted hold, whole-body root rotation with per-frame
  toe/palm contact anchoring), and `kickLoop` (chambered karate front
  kick behind a fists-up guard). Controls: `phase`, `gait`,
  `strideLength`, `legLift`, `armSwing`, `torsoSway`. Occurrence refs
  `#o1.1..#o1.28` follow the `asm.add` order in `juno.py`.
- `juno.urdf` — authored URDF (source of truth for the robot
  description): a frame-only
  `base_footprint` ground root plus 28 physical links and 27 revolute
  joints (zero pose stands with soles on z = 0), per-link 3MF mesh
  visuals, bbox collisions, CAD-derived inertials at an assumed 35 kg
  total mass.
- `juno.srdf` — authored MoveIt2 SRDF (source of truth for planning
  semantics): limb/torso/head
  planning groups, hand end effectors, disabled collisions, and whole-body
  group states (`zero`, `athletic_ready`, `t_pose`, `wave_right`, `squat`).
- `STEP/` — per-link wrapper sources (`gen_step()` per link) and their
  generated STEP parts; `3MF/` — per-link mm mesh sidecars referenced by
  the URDF.

## Conventions

Units mm. Pelvis waist-yaw joint center is the world origin; +X forward,
+Y robot-left, +Z up. Soles rest near z = -774 in the default stance.
Regenerate with the CAD skill: `python scripts/gen models/renders/juno/juno.py`.
Regenerate link meshes per link with the CAD skill, e.g.
`python scripts/export models/renders/juno/STEP/<link>.py --3mf ../3MF/<link>.3mf`.
Edit the robot description directly in `juno.urdf` / `juno.srdf`, then
validate with the URDF/SRDF skills:
`python scripts/validate models/renders/juno/juno.urdf`
and `python scripts/validate models/renders/juno/juno.srdf`.
