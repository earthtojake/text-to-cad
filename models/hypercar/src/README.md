# hypercar models

`models/hypercar` on cadgen 0.8: a mid-engine hypercar whose body panels are cut
from one master surface. `hypercar.py` is the one model (`@model`; a run writes nothing):

| Script | Model | What it is |
| --- | --- | --- |
| `hypercar.py` | `hypercar` | The car: 13 system stages, 706 parts, the dihedral doors' mechanism, the `doors` motion and the `showcase` and `explode` animations (clips of its GLB) |
| `body.py` ... `details.py` (13) | nothing | One system each, a `@memo` stage the car calls in its body |

Build from this folder: `python hypercar.py`. The GLB is exported on demand
(`cadgen export "$ID" GLB/hypercar.glb`, the id the run prints), its three clips baked.

```
python hypercar.py
cadgen snapshot "$ID" open.png --pose open
cadgen snapshot "$ID" half.png --pose '{"door_left": [-31, 155], "door_right": [31, 155]}'
```

A half-open STEP is a model of its own: one returning `posed(hypercar(), {"door_left": [-31, 155],
"door_right": [31, 155]})` (`cadgen.ap242`) and declaring `@step`.

## How it is built

`lib/` holds the part builders, one module per system (each `build()` returns the
system's labelled group), plus `surfaces.py` (the one master body surface every
panel is cut from), `palette.py` (colours, authored as sRGB hex) and `context.py`
(`group`, `style`, and `compound_from_instances`, which places a prototype N
times as `prototype.moved(location)` where the original called cadgen's). The
builders are unchanged but for `import build123d as bd` and the wheels: each corner
places its axle's wheel prototype (`base * leaf`) instead of baking a world-space
copy of it, which the old viewer needed and an xbf does not.

The order of `SYSTEMS` in `hypercar.py` is the occurrence order:

    body   glazing   lighting   chassis
    suspension_front   suspension_rear   wheels   brakes
    powertrain   interior   aero   hinge   details

Each system is a `@memo` function in its own file (`body.py`: `body()` returns
`lib/body.py`'s group): a stage of the car's build that an edit elsewhere replays
from the worker's memory. Every one holds more than a thousand kernel calls,
counted on a warm worker by running each alone (`wheels` 23,875, `details` 9,923,
`lighting` 4,019, `body` 3,856, `interior` 3,281, `suspension_front` 2,769,
`chassis` 2,457, `glazing` 1,991, `brakes` 1,758, `suspension_rear` 1,724, `aero`
1,573, `hinge` 1,522, `powertrain` 1,253; the car's own body, one), so each saves
its share of the 60,000 hits a re-run of the whole car would take.

Measured on 2026-10-22 (one machine, its load 5-25 from other work): cold 186-211 s
(the bodies 162-183 s, the GLB 15-17 s); a no-op 1.3-1.4 s, both files kept; the old
benchmark's edit (`LOWER_ARM`'s first point 22 -> 23 in `lib/hinge.py`) 3.6-4.5 s,
`hinge` and the car run and 12 stages replayed. The edited xbf and GLB are the bytes
a cold build of the edited code writes, and reverting the edit writes the first
cold build's bytes again.

## Kinematics

The dihedral synchro-helix doors. Each door is a build123d `CylindricalJoint` --
rotation and axial travel about the same tower axis, from `lib/hinge.py`'s
constants -- and a `RigidJoint` of the same label on the door skin, where it stands
shut: the parts live in different systems' groups, so `connect_to` cannot place
them, and the label pairs them as built (shut, 0 and 0). The joint is held by the
chassis. Everything that rides the door (side glass, door cards and pull, the
mirror's five parts, the hinge's door bracket and lower lug) is fastened to it by a
pair of rigid joints.

| Joint | Range | Rides it |
| --- | --- | --- |
| `door_left` | turn -62 .. 0 deg, travel 0 .. 310 mm | the left door and its 11 riders |
| `door_right` | turn 0 .. 62 deg, travel 0 .. 310 mm | the right door and its 11 riders |

The old poses are `shut`, as built, and the configuration `open`, which sets each
door's turn and travel together (`door_left=(-62, 310)`, `door_right=(62, 310)`).
The old `doors` clip is the motion `doors`: waypoints shut, open at 3.5 s, shut at
7 s, cubic, so turn and travel stay in step along the helix.

- The old `doors` coupling (one 0..1 control for both doors) is dropped: a
  convenience control, not a mechanical relation; `open` and the motion set the
  two door joints themselves.

### The explodes

The old `showcase` (48 s, a strip-down tour) and `explode` (10 s, the whole car
apart and back) moved 37 groups of parts and 10 of the engine's,
each by one fixed vector times a 0..1 factor: radial (away from the car's long axis,
from the group's pinned rest centre), lateral (out in Y by its side) or fixed. The
chassis never moved.
Both are GLB animations now (`cadgen.gltf`): each group a translation along its
vector, that factor times it, sampled every 0.1 s, after the pose; the vectors, centres,
windows and engine anchor are the old clip's numbers, and the groups name parts by the
old occurrence ids (`o1.3.49`), the port's tree being the old one, child for child:

- 35 groups (the flanks, each door with its own, the upper skins, the nose, the lamps,
  each suspension corner, wheel and brake, the powertrain, the interior, the aero sets,
  the hinges, the details), a system's own compound where a group is a whole
  sub-assembly;
- 10 for the engine's own sub-explode (heads, cam covers, gear covers, cam bosses,
  intake, exhaust, transaxle), inside the powertrain, so the V12 comes apart where the
  unit already stands, as the old moves added up;
- the doors' riders, four sets a side, each on its own group's vector and window, as
  the old clips moved them.

The mechanism takes no part in them: every group moves by its own translation, exactly
as the old clips moved it. The old clips looped; an animation has no loop (a player
repeats a clip), and each of these ends where it starts, so it repeats seamlessly. The
doors stay shut in both clips, as before.

## Not ported

- `render/presentation_theme.json` and `presentation_display.json`, the old
  snapshot's theme and edge styling: an xbf is drawn in the engine's one look.
