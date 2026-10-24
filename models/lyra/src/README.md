# lyra models

`models/lyra` on cadgen 0.8: a five-digit robotic right hand (~198 mm
flange to middle fingertip) with 16 degrees of freedom, and the 17 link meshes its
URDF references. One script, `lyra.py`, holds every model:

| Model | Files | What it is |
| --- | --- | --- |
| `lyra` | — | The hand: 17 links, 111 occurrences, 16 revolute joints, 7 configurations, 5 motions |
| `palm` ... `thumb_distal` (17) | `3MF/<link>.3mf`, by `exports.py` | One URDF link alone, in its part-local frame; `../lyra.urdf` references the 3MF |

Build from this folder: `python lyra.py` builds all 18. `../lyra.urdf` and
`../lyra.srdf` are authored (not generated); the URDF's meshes are `3MF/<link>.3mf`, which `exports.py` writes
(`export(link, ...)` for each link model): run it after changing a link, before loading the
URDF.

```
python lyra.py                                    # prints each model's id: and view:
python exports.py                                # the URDF's link meshes, 3MF/<link>.3mf
cadgen snapshot "$ID" lyra.png --pose fist         # ID: the lyra model's id: line
cadgen urdf snapshot ../lyra.urdf urdf.png
cadgen export "$ID" GLB/lyra.glb                  # the five motions, baked as clips
```

## How it is built

`lib/` holds the part builders (`palm.py`, `digits.py`) unchanged but for
`import build123d as bd`, and the shared code: `chain.py`, the chain spec the URDF
and SRDF mirror (offsets, travel, the named poses, a stdlib FK); `common.py`, the
palette and `revolute_attach`; `clearance.py`, the stdlib capsule self-check of
every pose and motion path.

`links()` is the script's one `@memo` function: all 17 links (~1,650 kernel calls,
~3.8 s). The hand and each link model call it, so a build makes every link once:
the first call runs it, or replays it when no edit reaches a builder, and every
other call is a new placement of its result. Measured cold: 7.7 s with it, 11.1 s
without it, when each link model builds its own link (those calls are misses, not
memo hits). An edit to a builder runs it again (an edit of the thumb's tip radius:
2.2 s, 18 misses), and `exports.py` writes each 3MF with the same bytes unless its mesh
changed.

## Kinematics

The old `AssemblyHelper` frames and typed mates are one thing now: each joint is a
build123d `RevoluteJoint` on the parent link and a `RigidJoint` on the child
(`lib/common.revolute_attach`), connected root to leaf at the relaxed pose. That
pose is the as-built configuration. Values are the chain's absolute angles, no
longer deltas from the relaxed build, and each joint's range is the URDF's travel.
The SRDF's seven hand group states are configurations: `zero`, `relaxed` (as built),
`fist`, `precision_pinch`, `tripod_pinch`, `point`, `ok_sign`. The palm is the
ground.

## Motions

The five clips were joint-space already (chain FK at every sample, applied as a
rigid delta against the relaxed build), so each is a motion now: a function of time
returning every joint's angle, which the document keeps as samples and a GLB export bakes
into a clip of the same name: `poseTour` (11.5 s), `graspLoop` (2.6 s), `pinchLoop`
(2.8 s), `rippleLoop` (2.6 s), `countLoop` (7 s). The old clips looped; a motion has
no loop, and each ends on the pose it starts from, so a player repeats it the same
way. Their key orders are the ones `lib/clearance.py` checks.

## Not ported

- Per-link STEP files. `cadgen export` writes one of a link model on demand.
- The 17 one-link scripts. Each link is a model of `lyra.py` now, so no model
  calls another.
- The clips' display labels ("Pose tour", ...): a motion has its name alone.
