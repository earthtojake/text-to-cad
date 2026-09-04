# lyra models

The hand assembly plus one model per URDF link. Every link model emits both a
STEP part and the 3MF mesh `lyra.urdf` references, and `lyra.py` composes
those same models by CALLING them: a stale link builds on its own worker, a
current one loads, and the hand links its tree. Rebuilding a link alone leaves
the hand to be rerun.

| Script                 | Artifact                                       | Description                          |
|------------------------|------------------------------------------------|--------------------------------------|
| lyra.py                | STEP/lyra.step                                 | Full 16-DOF hand, baked `relaxed`    |
| palm.py                | STEP/palm.step, 3MF/palm.3mf                   | Palm + wrist flange (root link)      |
| index_proximal.py      | STEP/index_proximal.step, 3MF/…                | Index proximal phalanx               |
| index_middle.py        | STEP/index_middle.step, 3MF/…                  | Index middle phalanx                 |
| index_distal.py        | STEP/index_distal.step, 3MF/…                  | Index distal phalanx                 |
| middle_proximal.py     | STEP/middle_proximal.step, 3MF/…               | Middle proximal phalanx              |
| middle_middle.py       | STEP/middle_middle.step, 3MF/…                 | Middle middle phalanx                |
| middle_distal.py       | STEP/middle_distal.step, 3MF/…                 | Middle distal phalanx                |
| ring_proximal.py       | STEP/ring_proximal.step, 3MF/…                 | Ring proximal phalanx                |
| ring_middle.py         | STEP/ring_middle.step, 3MF/…                   | Ring middle phalanx                  |
| ring_distal.py         | STEP/ring_distal.step, 3MF/…                   | Ring distal phalanx                  |
| pinky_proximal.py      | STEP/pinky_proximal.step, 3MF/…                | Pinky proximal phalanx               |
| pinky_middle.py        | STEP/pinky_middle.step, 3MF/…                  | Pinky middle phalanx                 |
| pinky_distal.py        | STEP/pinky_distal.step, 3MF/…                  | Pinky distal phalanx                 |
| thumb_base.py          | STEP/thumb_base.step, 3MF/…                    | Thumb CMC base                       |
| thumb_metacarpal.py    | STEP/thumb_metacarpal.step, 3MF/…              | Thumb metacarpal                     |
| thumb_proximal.py      | STEP/thumb_proximal.step, 3MF/…                | Thumb proximal phalanx               |
| thumb_distal.py        | STEP/thumb_distal.step, 3MF/…                  | Thumb distal phalanx                 |

Build everything: `ls src/*.py | xargs -n1 -P4 python`; unchanged models no-op.

`lib/` holds the shared code: `chain.py` (the kinematic spec — offsets, limits,
named poses, stdlib-only FK — shared with `lyra.urdf`/`lyra.srdf`), `common.py`
(palette + `revolute_attach`), `palm.py` / `digits.py` (the part builders), and
`clearance.py` (capsule self-check; run `python -m lib.clearance` from `src/`
after editing a pose or an animation key order).

Kinematics: 16 revolute mates built from `lib/chain.py`, plus the seven named
poses. The STEP is baked in `relaxed`, so ZERO IS THE ARTIFACT AS WRITTEN — the
mates' limits and the pose presets are DELTAS from that stance, which is why
`cadgen step snapshot STEP/lyra.step tmp/zero.png --kinematics zero` shows a
flat open hand rather than a doubly-bent one.

Animation (`lyra.step.js`): `poseTour`, `graspLoop`, `pinchLoop`, `rippleLoop`,
`countLoop` — per-frame chain FK, applied as a rigid delta against the baked
pose.
