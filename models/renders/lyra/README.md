# lyra — dexterous humanoid hand concept

An aesthetically refined five-digit robotic RIGHT hand for an advanced
bipedal robot: slim pearl-composite shell tubes over an exposed graphite
structural spine, machined-aluminum precision knuckle clevises with visible
pivot pins and rim washers, tendon-driven architecture (dorsal tendon
channel grooves fanning to each knuckle plus a five-dial tensioner row at
the wrist), integrated tactile sensing (2x2 palm pad array, per-phalanx
soft-touch strips, palmar fingertip caps, amber-ringed palm sensor), and a
6-bolt wrist flange. Graceful human-like proportions (~198 mm flange to
middle fingertip), clean industrial design, no logos.

## Degrees of freedom (16)

| Group | Joints | DOF |
| --- | --- | --- |
| Each finger (x4) | MCP, PIP, DIP flexion (about -X) | 12 |
| Thumb | CMC yaw (opposition swing about +Z), CMC flex, MP, IP (about -Y) | 4 |

MCP abduction/spread is intentionally omitted (documented tendon-budget
trade in `lyra_parts/chain.py`). Named poses are capsule-tuned to small
positive clearances (`lyra_parts/clearance.py`): `precision_pinch` and
`ok_sign` kiss the thumb-index pads at ~0.7-0.8 mm surface clearance,
`tripod_pinch` chuck-grips a virtual ~12 mm object, and the `fist` thumb
rests on the index middle phalanx — no pose or animation blend
interpenetrates.

## Files

- `lyra.py` — build123d generator (`gen_step()`); authoritative source.
  Joints are authored as `cadgen.assembly.AssemblyHelper` revolute frames
  driven by the baked `relaxed` pose.
- `lyra_parts/` — part-builder package. `chain.py` is the shared kinematic
  chain/pose/limit spec (stdlib-only FK included) used by the CAD assembly,
  the authored URDF/SRDF artifacts, and the animation sidecar; `lib.py`
  holds the palette and the verified `revolute_attach()` joint math;
  `palm.py` / `digits.py` build the parts; `clearance.py` is the stdlib capsule-collision self-check (run
  `python -m lyra_parts.clearance` from this directory after editing
  poses or animation key orders — it sweeps every named pose and every
  sidecar blend path).
- `lyra.step` — generated STEP assembly (derived artifact), baked in the
  `relaxed` pose. Occurrence refs `#o1.1..#o1.17` follow the `asm.add`
  order in `lyra.py` (palm, then index/middle/ring/pinky
  proximal/middle/distal, then thumb base/metacarpal/proximal/distal).
- `lyra.params.js` — CAD Viewer animation sidecar driving per-frame chain FK
  deltas against the baked pose. Animations: `poseTour` (a finger-ripple
  wave, then relaxed -> precision pinch -> OK sign -> point -> tripod
  pinch -> fist; key order chosen so every blend is collision-free),
  `graspLoop` (power grasp), `pinchLoop` (pinch with pad double-tap),
  `rippleLoop` (traveling finger curl wave with overlapping per-digit
  pulses), `countLoop` (count to five from a fist; the thumb lifts to a
  hover before any finger extends).
  Controls: `phase`, `mode`, `pose` (named SRDF pose hold), `grip`.
- `lyra.urdf` — generated URDF (derived artifact): a frame-only
  `wrist_mount` root plus 17 physical links and 16 revolute joints,
  per-link 3MF mesh visuals, bbox collisions, CAD-derived inertials at an
  assumed 0.62 kg total mass.
- `lyra.srdf` — generated MoveIt2 SRDF (derived artifact): per-digit joint
  groups, `fingers`/`hand` unions, a palm-mounted `hand_eef` end effector,
  disabled collisions, and hand group states (`zero`, `relaxed`, `fist`,
  `precision_pinch`, `tripod_pinch`, `point`, `ok_sign`).
- `STEP/` — per-link wrapper sources (`gen_step()` per link) and their
  generated STEP parts; `3MF/` — per-link mm mesh sidecars referenced by
  the URDF.

## Conventions

Units mm. RIGHT hand: the wrist-flange mount face center is the origin,
+Z distal (fingers up), +Y palmar, +X radial (thumb side). Every link frame
sits at its joint center with axes parallel to the palm at zero angles
(URDF joints are pure translations). Positive joint angles flex/curl.
Regenerate with the CAD skill: `python scripts/gen models/renders/lyra/lyra.py`.
Regenerate link meshes per link with the CAD skill, e.g.
`python scripts/export models/renders/lyra/STEP/<link>.py --3mf ../3MF/<link>.3mf`.
Edit the robot description directly in `lyra.urdf` / `lyra.srdf`, then
validate with the URDF/SRDF skills:
`python scripts/validate models/renders/lyra/lyra.urdf`
and `python scripts/validate models/renders/lyra/lyra.srdf`.
