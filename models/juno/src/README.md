# juno models

`models/juno` on cadgen 0.8: a ~1.40 m research humanoid with 27 body
degrees of freedom, and the 28 link meshes its URDF references. One script,
`juno.py`, holds every model:

| Model | Files | What it is |
| --- | --- | --- |
| `juno` | — | The robot: 28 links, 363 occurrences, 27 revolute joints and `pelvis_lift`, 5 configurations, 7 motions |
| `pelvis` ... `hand_right` (28) | `3MF/<link>.3mf`, by `exports.py` | One URDF link alone, in its part-local frame; `../juno.urdf` references the 3MF |

Build from this folder: `python juno.py` builds all 29. `../juno.urdf` and
`../juno.srdf` are authored (not generated); the URDF's meshes are `3MF/<link>.3mf`, which `exports.py` writes
(`export(link, ...)` for each link model): run it after changing a link, before loading the
URDF.

```
python juno.py                                    # prints each model's id: and view:
python exports.py                                # the URDF's link meshes, 3MF/<link>.3mf
cadgen snapshot "$ID" juno.png --pose wave_right         # ID: the juno model's id: line
cadgen urdf snapshot ../juno.urdf urdf.png
cadgen export "$ID" GLB/juno.glb                  # the seven motions as clips
```

## How it is built

`lib/` holds the part builders unchanged (`build123d` imported directly),
`lib/chain.py`, the chain spec the URDF and SRDF mirror: offsets, travel, the
athletic stance and the SRDF group states, and `lib/gaits.py`, the seven clips'
choreography (below).

`links()` is the script's one `@memo` function: all 28 links (~4,300 kernel
calls, ~23 s cold). The robot and each link model call it, so a build makes every
link once. The first call runs it, or replays it when no edit reaches a builder,
and every other call is a new placement of its result. Measured: 30.8 s cold with
it, 56.2 s without it, when the robot and the link models each build the links.
Because every link model reaches `links()`, an edit to any builder re-runs it;
`exports.py` then writes each 3MF with the same bytes unless its mesh changed.

## Kinematics

The old `AssemblyHelper` frames and typed mates are one thing now: each joint is a
build123d `RevoluteJoint` on the parent link and a `RigidJoint` on the child
(`lib/juno_lib.revolute_attach`), connected root to leaf at the athletic ready
stance. That stance is the as-built configuration. Values are the absolute
angles, not deltas from it, and each joint's range is the URDF's travel
(`lib/chain.py`), but the ankle pitch's (below). The SRDF's five group states
are configurations: `zero`, `athletic_ready` (as built), `t_pose`, `wave_right`,
`squat`. The robot compound is the ground (the world): it holds `pelvis_lift`, a
slide along world Z with its rigid half on the pelvis, 0 as built (-200..200 mm),
and every other link hangs from the pelvis. Soles stand at z = -874.6 as built.

## Motions

The seven clips of the old `ANIMATION_JS` are motions of `juno`, with their old
names and durations: `danceLoop` 3.2 s, `handstandLoop` 4.6 s, `kickLoop`
2.8 s, `jumpLoop` 1.8 s, `runLoop` 0.8 s, `strideLoop` 1.9 s and `walkLoop` 1.5 s.
The old clips looped; a motion carries no loop (AP242 has none: a player repeats a
clip), and each of these ends on the pose it starts from. `lib/gaits.py` is the old module's gait functions in Python,
the IK included (the two-link leg IK, the run's toe pivot, the jump's reach clamp,
the dance's kicked-out leg, the handstand's keyed folds and its press-hip
bisection), with the published defaults the clips baked in (lift, swing and sway
1, stride 230 mm). Over 201 phases per gait its FK puts every link where the old
JavaScript did, within 1e-11 mm. Each motion is a function of time
(`juno._over_time`): the gait at its phase, wrapped as the old clips were. Posed by
the engine from its samples, every link stays within 0.4 mm of the gait's FK.

An old frame was `fkFrames(angles, extras, rootOffset, rootPitchDeg)`: the 27
joint angles, an extra torso pitch and roll folded in at `waist_yaw` that no joint
has, and the pelvis's motion in the world. The motions keep the angles exactly and
put the root's vertical on `pelvis_lift`. One joint fits between the world and the
pelvis (a second would need a compound between them, which would change the tree),
and a slide along Z keeps the most: walk and stride need no root motion (the stance
foot stays planted under a fixed pelvis), run and jump are a vertical bounce, kick
and dance dip. A pitch about Y would keep only part of the handstand (its root also
translates to hold a toe or a palm on the floor, which no fixed axis gives) and lose
the vertical of four clips, putting the run's and the jump's feet through the floor.
Measured over each clip, what the restoration keeps and loses (upper body = the
worst link's offset from the old frame):

| Clip | Old root motion | Old torso extras | Kept | Lost (deliberate) |
| --- | --- | --- | --- | --- |
| `walkLoop` | none | roll ±1.2° | every joint; stance feet planted, within 0.1 mm of the old | the torso roll (upper body ≤ 10 mm) |
| `strideLoop` | none | roll ±1.5° | the same | the torso roll (≤ 12 mm) |
| `runLoop` | Z ±22 mm | lean 7°, roll ±1.6° | the bounce; feet within 0.1 mm | the forward lean and the roll: the torso runs upright, and the neck still pitches 5.6° up against a lean that is gone (≤ 56 mm) |
| `jumpLoop` | Z -120..+160 mm | lean ≤ 8° in the crouch and landing | crouch, flight and landing spring; feet within 0.1 mm | the crouch lean (≤ 64 mm) |
| `kickLoop` | Y 0..42 mm, Z -18..0 | lean back 7° on the snap | the dip; the planted left foot stays planted | the 42 mm weight shift over the left leg (the body stays centred, so the kicking leg is up to 42 mm right of the old) and the lean back (≤ 56 mm) |
| `danceLoop` | Y -55..0 mm, Z -28..0 | roll -3° | the dip and the beat bounce; the right foot planted, the left toe on its old spot (≤ 2.4 mm) | the 55 mm shift over the right leg and the lean (≤ 56 mm) |
| `handstandLoop` | pitch 0..178° about Y; X -51..280, Z -395..13 mm | none | every joint angle: the folds, the arms overhead, the hold's wobble | the inversion: a slide cannot pitch the body, so the handstand plays in the pelvis's frame, upright; the hands never reach the floor and the feet leave it (up to 1.65 m from the old) |

The kick and the dance shifted the pelvis sideways and rolled the planted leg's
hip and ankle to keep its sole in place. With no lateral joint, `gaits.kick` and
`gaits.dance` take `pelvis_dy=0.0`: the same contacts solved under a pelvis that
does not shift, so the planted sole stays on its spot (the old drifted up to 1.7 and
2.7 mm, the restored 0.9 and 1.5). The jump's reach clamp still lifts the soles up
to 6.3 mm at takeoff and landing, as the old did.

The old clips played joint values with no limit, and two reach past the URDF's
assumed ankle travel: the run's heel recovery dorsiflexes the ankle to -51.6° and the
jump's crouch to -41.1°, below the URDF's -30. The model's `ankle_pitch_*` travel is
-55..50 (`juno.ANKLE_PITCH_RANGE_DEG`); `lib/chain.py`, the URDF and the SRDF keep
-30..50.

## Not ported

- Per-link STEP files. `cadgen export` writes one of a link model on demand.
- The 28 one-link scripts. Each link is a model of `juno.py` now, so no model
  calls another.
