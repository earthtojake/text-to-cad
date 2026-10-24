# motorbike models

`motorbike.py` is the assembly (`@model`; a run writes nothing). Every other `.py`
directly under `src/` is one part of it, a `@model` of its own, as the original's parts
each were: the assembly calls it (`frame()`, `seat()`, …), so it builds in the
assembly's run as a child, and running its own script (`python seat.py`) shows it alone,
on a page of its own. A part called twice is one prototype placed twice. No part is a
`@memo`: the engine replays a part whose code is unchanged, and a marker per part saved
under 0.1 s of an edit (see "When to use `@memo`" in `models/README.md`). Shared code
lives in `src/lib/`.

| Script               | What it is                | Description                                              |
|----------------------|---------------------------|----------------------------------------------------------|
| motorbike.py         | the model                 | Full assembly: 23 occurrences of 21 parts, build123d joints |
| frame.py             | part model               | Welded underbone frame + steel floor pan (the fixed root) |
| center_stand.py      | part model               | Center stand, folded-up pose under the floor pan          |
| front_fork.py        | part model               | Telescopic fork + chrome axle on the steering axis        |
| handlebar.py         | part model               | Bar, stem collar, grips and levers; owns `MIRROR_MOUNT_*` |
| front_fender.py      | part model               | Cream arc band over the front tire                        |
| front_wheel.py       | part model               | Tire + five-spoke cast rim + brake disc                   |
| rear_wheel.py        | part model               | Tire + five-spoke cast rim + drum hub                     |
| engine.py            | part model               | Unit powertrain doubling as the swingarm (CVT + covers)   |
| exhaust.py           | part model               | Head pipe + oval chrome muffler, rider right              |
| rear_shock.py        | part model               | Coilover between the frame lug and the engine boss        |
| leg_shield.py        | part model               | Cream step-through apron                                  |
| steering_cover.py    | part model               | Head-tube shroud above the apron                          |
| under_seat_body.py   | part model               | Rear body panel carrying seat and tail                    |
| rear_fender.py       | part model               | Cream arc over the rear tire                              |
| seat.py              | part model               | Brown saddle                                              |
| headlight.py         | part model               | Chrome shell + clear dome lens                            |
| tail_light.py        | part model               | Housing + red lens                                        |
| turn_signal_left.py  | part model               | Front-left amber signal; the assembly links it 2x (rear-left is `Pos * turn_signal_left()`) |
| turn_signal_right.py | part model               | Its mirror image (same `lib/trim.py` factory, right side); linked 2x the same way |
| mirror_left.py       | part model               | Left bar-end mirror at `handlebar.MIRROR_MOUNT_LEFT` (a constant from another file: tracked by value) |
| mirror_right.py      | part model               | Its mirror image at `handlebar.MIRROR_MOUNT_RIGHT` — its own part, because a reflection is new geometry |

Build from `src/`: `python motorbike.py`. A part script
defines no model and builds nothing on its own. No imported sources — every
artifact is generated.

## `src/lib/` — shared code, no models

| Module          | Role                                                                 |
|-----------------|----------------------------------------------------------------------|
| `lib/spec.py`   | **Single source of truth**: coordinates, palette, materials, every hardpoint |
| `lib/lib.py`    | Geometry vocabulary: revolved bands, lofts, swept tubes, coils        |
| `lib/wheels.py` | `build_front_wheel` / `build_rear_wheel`                              |
| `lib/chassis.py`| `build_frame` / `build_center_stand`                                  |
| `lib/frontend.py`| `build_front_fork` / `build_handlebar` / `build_front_fender`        |
| `lib/drivetrain.py`| `build_engine` / `build_exhaust` / `build_rear_shock`              |
| `lib/bodywork.py`| leg shield, steering cover, under-seat body, rear fender, seat       |
| `lib/trim.py`   | headlight, tail light, turn signal, mirror (`build_mirror(side, base)`) |

Every builder authors geometry DIRECTLY in the bike frame from `lib/spec.py`,
so a part entry and the assembly place identical geometry and the assembly
composes its children at identity. No builder restates a shared dimension.
The one hardpoint outside `lib/spec.py` is the pair of bar-end mirror mounts,
which `handlebar.py` owns; `mirror_left.py`, `mirror_right.py` and
`motorbike.py` import them from that file. A constant imported from another
file is tracked by VALUE, so only a changed mount runs the mirrors again.

Imports need no setup — `src/` is on `sys.path` because the script lives there:

```python
from lib import spec as S
from lib import chassis as B
```

## Materials

Every part is painted with `lib.paint(shape, name, *details, color=, material=)`:
its label, its palette colour and its material, one of the `lib/spec.py`
materials beside the palette. Each is a catalogue entry in the finish the part
wears (`materials.steel_1018.but(...)`), with `color=None`, so the palette is
the colour that shows and the material adds the finish:

| Parts | Material | Finish |
| --- | --- | --- |
| frame, fork, stand, handlebar, damper | Steel 1018 | gloss black paint: metallic 0, coat |
| leg shield, steering cover, under-seat body, fenders | ABS | painted, clear coat |
| seat | `Leather` (the project's own, 860 kg/m^3) | soft sheen coat |
| tires / grips | NBR 70A / TPU 95A | catalogue |
| cast rims, engine case, CVT and crank covers, drum hub | Aluminum 6061-T6 | as cast: roughness 0.6, no grain |
| brake levers | Aluminum 6061-T6 | catalogue (machined) |
| exhaust, headlight shell, signal housings, mirror shells | Stainless 304 | polished: roughness 0.1, no grain |
| axles, damper rod / brake disc | Steel 4140 | hard chrome, roughness 0.12 / ground, 0.3 |
| shock spring | Spring steel 1095 | yellow powder coat: metallic 0, coat |
| tail-light housing | ABS | catalogue |
| headlight lens / tail and signal lenses | Polycarbonate / Acrylic (PMMA) | catalogue: transmissive, the palette's tint and alpha |
| mirror glass | Glass, soda-lime | silvered: metallic, roughness 0.03, no transmission |

## Joints (`motorbike.py` only)

The assembly states its relationships as build123d joints on world-coincident
datums, each placed with `connect_to` at its as-built pose. The revolute ones
carry the ranges the old typed mates declared:

| Joint (fixed side)   | Fixed → moving             | Range            |
|----------------------|----------------------------|------------------|
| `head_tube_axis`     | frame → front_fork         | -40 .. 40 deg    |
| `front_axle_hub`     | front_fork → front_wheel   | ±3600 deg        |
| `engine_pivot`       | frame → engine             | -5 .. 12 deg     |
| `rear_axle_hub`      | engine → rear_wheel        | ±3600 deg        |
| `stand_bracket`      | frame → center_stand       | -76.2 .. 0 deg   |

Every other mount is a `RigidJoint` pair: handlebar, front fender and mirrors
on the fork and bar; exhaust on the engine; apron, shroud, body, seat, fenders,
lamps and signals on the frame and bodywork; the rear shock by its upper eye on
the frame lug only. Its lower eye on the engine boss is not jointed: a second
rigid mount would close a loop through the shock and weld the engine to the
frame, so `engine_pivot` could not move. The old kinematics left the shock
unmated for the same reason; it stays put while the engine swings.

The old `KINEMATICS` presets are configurations on these joints, by the joint that
carries each old mate now (`steering` is `head_tube_axis`, `engine_swing`
`engine_pivot`, `center_stand_pivot` `stand_bracket`; same axes and senses):

| Configuration | Joint values |
|---------------|--------------|
| `stand_down`  | `stand_bracket` -76.2 deg (the foot on the floor) |
| `turned_left` | `head_tube_axis` 32 deg |
| `bump`        | `engine_pivot` 12 deg |

`ride`, which set no joint, is the bike as built, so it is no configuration.

One motion is in the model's code: `steer`, `head_tube_axis` from -20 to 20 degrees
over 2 s and back over 2 s, as out-and-back waypoints (a motion has no loop or
pingpong; a player repeats it). The document keeps it as a definition; `cadgen export
<id> GLB/motorbike.glb` bakes it into a glTF clip named `steer`.
