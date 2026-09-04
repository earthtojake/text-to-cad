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
trade in `src/lib/chain.py`). Named poses are capsule-tuned to small
positive clearances (`src/lib/clearance.py`): `precision_pinch` and
`ok_sign` kiss the thumb-index pads at ~0.7-0.8 mm surface clearance,
`tripod_pinch` chuck-grips a virtual ~12 mm object, and the `fist` thumb
rests on the index middle phalanx — no pose or animation blend
interpenetrates.

## Files

- `src/` — the authored code. `src/README.md` is the model catalog.
  - `src/lyra.py` — the full-hand assembly (`@step`), baked in the `relaxed`
    pose. It also declares the 16-DOF `kinematics=` block (revolute mates +
    the seven named poses, built straight from `lib/chain.py`).
  - `src/<link>.py` — one model per URDF link (17). Each stacks
    `@threemf(out="../3MF/<link>.3mf")` on `@step(out="../STEP/<link>.step")`,
    so running the script emits both the STEP part and the mesh the URDF
    references.
  - `src/lib/` — shared code. `chain.py` is the kinematic chain/pose/limit
    spec (stdlib-only FK included) shared by the CAD assembly, the authored
    URDF/SRDF, and the animation module; `common.py` holds the palette and
    the verified `revolute_attach()` joint math; `palm.py` / `digits.py`
    build the parts; `clearance.py` is the stdlib capsule-collision
    self-check (run `python -m lib.clearance` from `src/` after editing
    poses or animation key orders — it sweeps every named pose and every
    blend path).
  - `STEP/lyra.step.js` — the render module beside the document: the
    animation clips, loaded by the viewer by name (authored, committed; no
    build reads it). Clips: `poseTour` (a finger-ripple wave,
    then relaxed -> precision pinch -> OK sign -> point -> tripod pinch ->
    fist; key order chosen so every blend is collision-free), `graspLoop`
    (power grasp), `pinchLoop` (pinch with pad double-tap), `rippleLoop`
    (traveling finger curl wave), `countLoop` (count to five from a fist;
    the thumb lifts to a hover before any finger extends). Each clip
    recomputes chain FK per frame and applies the rigid delta against the
    baked pose.
- `STEP/`, `3MF/`, `tmp/` — GENERATED, and not committed: a fresh clone
  regenerates them by running the scripts. `lyra.urdf` references
  `3MF/<link>.3mf`, so build the link models before loading the URDF.
- `lyra.urdf` — authored URDF: a frame-only `wrist_mount` root plus 17
  physical links and 16 revolute joints, per-link 3MF mesh visuals, bbox
  collisions, CAD-derived inertials at an assumed 0.62 kg total mass.
- `lyra.srdf` — authored MoveIt2 SRDF: per-digit joint groups,
  `fingers`/`hand` unions, a palm-mounted `hand_eef` end effector, disabled
  collisions, and hand group states (`zero`, `relaxed`, `fist`,
  `precision_pinch`, `tripod_pinch`, `point`, `ok_sign`) — the same seven
  the STEP's kinematics block carries as pose presets.

## Conventions

Units mm. RIGHT hand: the wrist-flange mount face center is the origin,
+Z distal (fingers up), +Y palmar, +X radial (thumb side). Every link frame
sits at its joint center with axes parallel to the palm at zero angles
(URDF joints are pure translations). Positive joint angles flex/curl.
Regenerate everything by running the scripts: `ls src/*.py | xargs -n1 -P4 python`
(each link script writes its own STEP part and 3MF mesh; unchanged models
no-op). Review a pose with
`cadgen step snapshot STEP/lyra.step tmp/fist.png --kinematics fist`.
Edit the robot description directly in `lyra.urdf` / `lyra.srdf`, then
validate them with the URDF/SRDF skills.
