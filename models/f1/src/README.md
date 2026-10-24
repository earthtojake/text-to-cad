# f1 models

`models/f1` on cadgen 0.8: an original ground-effect Formula 1 concept car. `f1.py`
is the one model (`@model`; a run writes nothing):

| Script | Model | What it is |
| --- | --- | --- |
| `f1.py` | `f1` | The car: 28 children, the DRS and steering joints, 3 configurations, the `drs` and `steering` motions and the `showcase`, `teardown` and `engine` animations (clips of its GLB) |
| `stages.py` | nothing | Eight `@memo` stages, each building a group of the children |
| `front_wing.py` ... `details.py` (28) | nothing | One child each, a function a stage calls; `power_unit`, `drivetrain`, `suspension_rear` and `details` are `@memo` stages of their own |
| `cover_panel.py`, `gearbox_casing.py`, `drivetrain_ancillaries.py`, `rear_structure.py` | nothing | Pieces of `engine_cover` and `drivetrain`, which call them |

Build from this folder: `python f1.py`.

```
python f1.py                                         # prints the car's id: and view:
cadgen snapshot "$ID" drs.png --pose drs_open
cadgen snapshot "$ID" lock.png --pose full_lock_left
cadgen export "$ID" GLB/f1.glb                       # the five clips
```

## How it is built

`lib/` holds the part builders each child wraps, unchanged but for `import
build123d as bd`. Read its two contracts first: `lib/spec.py` is the coordinate
system, package dimensions, suspension hardpoints, the DRS four-bar and the colour
palette; `lib/surfaces.py` is the shared surface vocabulary (airfoil family, blade
family, body lofts) every part module builds from.

Every child is a function in its own file, labelled with its name in the car, in
the order of `CHILDREN` in `f1.py`; the mirrored pairs (sidepods, track rods, the
four corners) are separate functions from one `lib/` factory, because a reflection
is new geometry.

The car's body calls its children through `@memo` stages, each a group of children
that share builder code, returning them by name (`stages.py`):

| Stage | Children | Kernel calls |
| --- | --- | --- |
| `front_end` | front_wing, nose | 2,377 |
| `survival_cell` | monocoque, halo, cockpit | 7,625 |
| `sidepods` | sidepod_left, sidepod_right, cooling | 1,098 |
| `engine_bodywork` | engine_cover, airbox | 2,157 |
| `underbody` | floor, diffuser | 1,570 |
| `power_unit` | power_unit | 11,403 |
| `drivetrain` | drivetrain | 1,875 |
| `rear_aero` | rear_wing, drs_flap, drs_actuator, beam_wing | 1,660 |
| `front_suspension` | suspension_front, steering_rack, track_rod_left, track_rod_right | 3,100 |
| `suspension_rear` | suspension_rear | 2,376 |
| `corners` | corner_fl, corner_fr, corner_rl, corner_rr | 2,711 |
| `details` | details | 990 |

Each was counted on a warm worker by running it alone; the car's own body is one
call. A child of a few hundred calls is no stage of its own (`drs_flap` holds 300),
but running one costs its Python as well as its hits (0.5-1.8 ms a call here), so
the small children ride in the stage of the parts they belong with. Children that
share a builder's cache are one stage: `lib/wheels.py` builds each axle's left
corner once and mirrors it for the right, and `lib/sidepods.py` its left panel;
split into stages of their own, a right corner run alone builds its left corner
in another order than a cold build, and its elements took other names.
The engine cover's shell (`cover_panel`, its own model in the original) shares
`lib/engine_cover.py`'s louvre and airbox-envelope caches with the parts around it,
so it is no stage of its own either: an edit that reaches `engine_bodywork` re-runs
it, 45-60 s, most of it the shell's validity checks (`surfaces.repair`,
`is_valid_shape`), which no kernel hit saves.

Measured on 2026-10-22 (one machine, its load 10-25 from other work): cold 529 s
(500-600 s over four cold builds, one at load 110; the builders alone take about
as long in plain Python: the gearbox casing 80-95 s, the cover shell 65-70 s); a no-op 1.1-1.3 s, both files kept; an
edit of `lib/front_wing.py`'s `_ACCENT_FRAC` (0.07 -> 0.075) 6.5 s and its revert
6.1 s, `front_end` and the car run and 11 stages replayed. A warm build from a
worker that had built other code writes the cold build's bytes; the edited xbf
holds the element names, geometry and colours a cold build of the edited code
writes. One difference stays: once the `drivetrain` stage has been replayed, the
gearbox casing's BRep holds one edge's continuity entry at another place in that
edge's list than a cold build writes it (likely the replay re-applying an in-place
change OCCT made during the casing's own construction: built in plain Python, the
rest of the drivetrain leaves the casing's bytes alone), so a warm rewrite is that
entry apart from the cold file.

## Kinematics

Both of this car's mechanisms are closed loops: the DRS is a planar four-bar, and
the steering solves each wheel against a fixed-length track rod. Their joints are
the loops' tree -- each moving child on a joint to the part that holds it, the
closing links unjointed -- and every pose of them is solved in Python from the
`lib/spec.py` hardpoints the geometry is built from (the old clips' solves, kept).
Each joint is authored where its parts stand as built and paired by its label
(`connect_to` would move a child that a later build replays as it stands):

| Joint | Kind | On -> moves | Range |
| --- | --- | --- | --- |
| `drs_flap` | revolute about Y at `spec.DRS_PIVOT` | rear_wing -> drs_flap | -64 .. 0 deg |
| `drs_crank` | revolute about Y at `spec.DRS_CRANK_PIVOT` | rear_wing -> drs_actuator | 0 .. 67.5 deg |
| `steer_left`, `steer_right` | revolute about each steer axis (the two front ball joints) | suspension_front -> corner_fl, corner_fr | the wheel's angle at the rack's full 62 mm each way: -23.1 .. 22.5 deg (left), -22.5 .. 23.1 deg (right) |
| `rack` | linear along Y | monocoque -> steering_rack | -62 .. 62 mm |
| `track_rod_left`, `track_rod_right` | ball at the rack end | steering_rack -> track rod | -10 .. 10 deg each axis |

Configurations: `drs_open` (the flap laid flat, the crank where the four-bar puts
it), `full_lock_left` and `full_lock_right` (the rack at 55.4 mm, where the inside
wheel reaches `spec.MAX_STEER_DEG`). Motions, each a function of time the document
keeps as samples: `drs`, open and shut on a raised cosine over 4 s, and
`steering`, left through centre to right and back over 6 s; each ends where it
starts, so a player repeats it seamlessly (a motion carries no loop), and the GLB
carries each as a clip.

### The teardown

The old `showcase`, `teardown` and `engine` clips are GLB animations (`cadgen.gltf`),
with their names and durations; each ends where it starts, as the old looping clips
did, and carries no loop of its own (players repeat a clip). Each child but the
monocoque moves along its old direction by its old distance, and the power unit's
twelve systems move inside it (`eng_induction`, `eng_head_left` ... `eng_ancillaries`,
the old group names, each its leaves by label), on top of the power unit's own move.
The mechanism takes no part: each child is a reference of its own in the car's tree,
so no child drags another by its explode, and each moves after the DRS and the
steering pose it, in the car's frame, as the old frame applied it.

The monocoque never moves, as it was the old clips' fixed reference. The animations
are the old functions of the two clocks, sampled every 0.05 s: `showcase` (22.5 s) the
old loop-closed beat sheet, the car opening 1.5-10.5 s and the engine 11.2-14.8 s,
both closing by 22.3 s; `teardown` (12 s) the car apart and back on a raised cosine;
`engine` (8 s) the engine alone. The GLB carries all five clips.

Deliberate differences from the old clips:

- **The engine's systems ride the power unit once.** The old frame translated each
  system's leaves by the power unit's offset plus their own (its comment: "Sub-parts
  inherit the power unit's own offset, or they would detach from it"), and then
  translated every leaf under the power unit by that offset again: the viewer's
  handles act on the leaves and add up, so in the old `showcase` and `teardown` the
  88 system leaves rose 2,160 mm while the crankcase rose 1,080 mm, and the
  systems hung a power unit's lift above the core before the engine clock started.
  An animation composes them once, which is what the comment meant: the systems sit
  on the core until the engine clock opens them. The `engine` clip, whose explode is
  0, is unchanged.
- **The cylinder heads' joint rails move with the heads**, as the old groups list
  had them (`head_joint_rail:left` in `eng_head_left`); the old comment's static
  spine ("the crankcase, sump, bearing webs and joint rails never move") is the
  other twelve leaves: crankcase, sump pan, the front and gearbox faces, the two
  belt ribs and the six main webs.

The old `drs` clip turned the crank the wrong way: its solve measured the crank's
angle from +X toward +Z, a turn about -Y, and the clip turned the actuator that
far about +Y, so the crank end and the flap lug, 137.6 mm apart through the link,
came within 15.8 mm of each other at full open. `drs_crank` takes the solve's own
sense: posed by the engine's forward kinematics, `drs_open` keeps the link at its
137.6 mm, and `full_lock_left` puts each track rod's outer ball on its steering
arm's (0.0 mm apart).

## Not ported

- `../f1_stage.appearance.json`, the old viewer stage (lights, floor, the
  materials' satin finish): an xbf is drawn in the engine's one look.
