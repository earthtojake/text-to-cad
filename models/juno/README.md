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

## Layout

This is a `cad-project`: authored code lives in `src/`, generated artifacts in
the format folders (which are gitignored and rebuilt by running the scripts).

```
juno/
  juno.urdf  juno.srdf     authored robot description (NOT generated)
  src/
    juno.py                the full 28-occurrence assembly
    <link>.py     x28      one per URDF link: @step + @threemf
    lib/                   shared part builders + the chain spec
  STEP/  3MF/              generated outputs
    juno.step.js           the render module beside juno.step: the seven animation clips (authored, committed)
  tmp/                     snapshots and scratch
```

- `src/juno.py` — the assembly. `@step(out="../STEP/juno.step", kinematics=…)`.
  Joints are authored as
  `cadgen.assembly.AssemblyHelper` revolute frames driven by the pose angles
  in `src/lib/chain.py`, and the SAME spec is read back out to build the
  typed-mate kinematics (below), so the CAD, the mates and the URDF cannot
  drift.
- `src/<link>.py` (28 files) — one per physical URDF link, each returning the
  matching `lib.*` builder's part-local compound and declaring both
  `@step(out="../STEP/<link>.step")` and
  `@threemf(out="../3MF/<link>.3mf")`. The 3MF is the mesh `juno.urdf`
  references; the URDF's 29th link, `base_footprint`, is a frame-only ground
  reference with no geometry and therefore no script and no mesh.
- `src/lib/` — part builders (sculpted segments, joint hardware, shared style
  library). Each builder returns an identity-location labeled compound in its
  part-local frame. `chain.py` is the shared kinematic chain/pose/limit spec
  used by the CAD assembly, the typed mates, and the authored URDF/SRDF; it is
  stdlib-only and also carries the chain FK (`link_frames`,
  `world_joint_axes`).
- `juno.urdf` — authored URDF (source of truth for the robot description): a
  frame-only `base_footprint` ground root plus 28 physical links and 27
  revolute joints (zero pose stands with soles on z = 0), per-link 3MF mesh
  visuals, bbox collisions, CAD-derived inertials at an assumed 35 kg total
  mass.
- `juno.srdf` — authored MoveIt2 SRDF (source of truth for planning
  semantics): limb/torso/head planning groups, hand end effectors, disabled
  collisions, and whole-body group states (`zero`, `athletic_ready`,
  `t_pose`, `wave_right`, `squat`).

## Kinematics: 27 revolute mates, zero = the athletic stance

`src/juno.py` declares the body chain as typed mates (pure data in the
`STEP/juno.step.json` sidecar — no rebuild to pose it), built programmatically
from `lib/chain.py`:

- one `cadgen.revolute` per joint, `parent`/`child` are the link labels
  (`#pelvis`, `#torso`, …), and each axis is given as literal
  `origin=`/`direction=` numbers — the joint's frame in WORLD millimetres at
  the authored pose, which is exactly the screw axis a product-of-exponentials
  FK evaluates about;
- **zero is the artifact as written.** The STEP is baked in the athletic ready
  stance, so every mate's rest value is that stance: limits are the URDF
  travel range MINUS the authored angle, and the five SRDF group states are
  stored as DELTAS from it (`athletic_ready` is therefore all zeros). Feeding
  absolute joint angles would land every preset at athletic + pose.

Check a pose: `cadgen step snapshot STEP/juno.step tmp/zero.png --kinematics zero`
(the robot stands straight-legged, soles at z = -898).

## Animation

`STEP/juno.step.js`, the render module beside the document, holds the
choreography; the viewer loads it by name and no build reads it. It knows
nothing about the mates: it runs its own chain FK each
frame and applies, per link, the rigid delta from the baked athletic placement
as one rotation about the model origin plus a translation. Seven clips:

- `walkLoop` — march in place, planted stance feet, no IK;
- `strideLoop` — treadmill strides, the stance foot slides flat on the ground;
- `runLoop` — flight phases, body bounce, toe-pivot push-off, forward lean;
- `jumpLoop` — countermovement hop, hands overhead, underdamped landing;
- `danceLoop` — Elvis: right finger up-and-right, left leg kicked out on a
  shaking planted toe (closed-form lateral+sagittal leg IK);
- `handstandLoop` — toe-pivot fold to a palms-flat inverted hold with
  per-frame toe/palm contact anchoring;
- `kickLoop` — chambered karate front kick behind a fists-up guard.

All gaits share antiphase arm swing, torso counter-sway, and head
stabilization. The retired sidecar's live `strideLength` / `legLift` /
`armSwing` / `torsoSway` parameters are baked at their published defaults,
because a clip is a pure function of time. Occurrence refs `#o1.1..#o1.28`
follow the `asm.add` order in `src/juno.py`.

## Conventions

Units mm. Pelvis waist-yaw joint center is the world origin; +X forward,
+Y robot-left, +Z up. Soles rest at z = -874.6 in the default (athletic)
stance and z = -898 at the `zero` pose.

Build one model: `python src/<script>.py` (unchanged models are no-ops).
Build the project: `ls src/*.py | xargs -n1 -P4 python`.
Edit the robot description directly in `juno.urdf` / `juno.srdf`, then
validate with the URDF/SRDF skills.
