# motorbike models

Every `.py` directly under `src/` is a model: run it to build it. Shared code
lives in `src/lib/` and is never a model. The assembly composes its children
by CALLING the sibling models (`frame()`, `seat()`, …): a stale child builds on
its own worker, a current one loads, and the assembly links to the child's
geometry instead of copying it. Rebuild the assembly to pick up a child's edit.

| Script               | Artifact                  | Description                                              |
|----------------------|---------------------------|----------------------------------------------------------|
| motorbike.py         | STEP/motorbike.step       | Full assembly: 25 linked children (23 models), typed mates below |
| frame.py             | STEP/frame.step           | Welded underbone frame + steel floor pan (the fixed root) |
| center_stand.py      | STEP/center_stand.step    | Center stand, folded-up pose under the floor pan          |
| front_fork.py        | STEP/front_fork.step      | Telescopic fork + chrome axle on the steering axis        |
| handlebar.py         | STEP/handlebar.step       | Bar, stem collar, grips and levers; owns `MIRROR_MOUNT_*` |
| front_fender.py      | STEP/front_fender.step    | Cream arc band over the front tire                        |
| front_wheel.py       | STEP/front_wheel.step     | Tire + five-spoke cast rim + brake disc                   |
| rear_wheel.py        | STEP/rear_wheel.step      | Tire + five-spoke cast rim + drum hub                     |
| engine.py            | STEP/engine.step          | Unit powertrain doubling as the swingarm (CVT + covers)   |
| exhaust.py           | STEP/exhaust.step         | Head pipe + oval chrome muffler, rider right              |
| rear_shock.py        | STEP/rear_shock.step      | Coilover between the frame lug and the engine boss        |
| leg_shield.py        | STEP/leg_shield.step      | Cream step-through apron                                  |
| steering_cover.py    | STEP/steering_cover.step  | Head-tube shroud above the apron                          |
| under_seat_body.py   | STEP/under_seat_body.step | Rear body panel carrying seat and tail                    |
| rear_fender.py       | STEP/rear_fender.step     | Cream arc over the rear tire                              |
| seat.py              | STEP/seat.step            | Brown saddle                                              |
| headlight.py         | STEP/headlight.step       | Chrome shell + clear dome lens                            |
| tail_light.py        | STEP/tail_light.step      | Housing + red lens                                        |
| turn_signal_left.py  | STEP/turn_signal_left.step | Front-left amber signal; the assembly links it 2x (rear-left is `Pos * turn_signal_left()`) |
| turn_signal_right.py | STEP/turn_signal_right.step | Its mirror image (same `lib/trim.py` factory, right side); linked 2x the same way |
| mirror_left.py       | STEP/mirror_left.step     | Left bar-end mirror at `handlebar.MIRROR_MOUNT_LEFT` (a constant from a model file: tracked by value) |
| mirror_right.py      | STEP/mirror_right.step    | Its mirror image at `handlebar.MIRROR_MOUNT_RIGHT` — its own model, because STEP cannot express a reflection |

Build: `python src/<script>` per row; unchanged models are no-ops. Build them
all with `ls src/*.py | xargs -n1 -P4 python` (parallel ACROSS models, never
within one). No imported sources — every artifact is generated.

## `src/lib/` — shared code, no models

| Module          | Role                                                                 |
|-----------------|----------------------------------------------------------------------|
| `lib/spec.py`   | **Single source of truth**: coordinates, palette, every hardpoint     |
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
`motorbike.py` import them from the model file. A constant imported from a
model file is tracked by VALUE, so only a changed mount makes the mirrors stale.

Imports need no setup — `src/` is on `sys.path` because the script lives there:

```python
from lib import spec as S
from lib import chassis as B
```

## Kinematics (`motorbike.py` only)

`motorbike.py` declares typed mates in `KINEMATICS` on its `@step`; they land
in `STEP/motorbike.step.json` and drive the viewer's pose sliders. Zero is the
bike as written.

| DOF                  | Parent → child             | Range            |
|----------------------|----------------------------|------------------|
| `steering`           | frame → front_fork         | -40 .. 40 deg    |
| `front_wheel_spin`   | front_fork → front_wheel   | free             |
| `engine_swing`       | frame → engine             | -5 .. 12 deg     |
| `rear_wheel_spin`    | engine → rear_wheel        | free             |
| `center_stand_pivot` | frame → center_stand       | -76.2 .. 0 deg   |

`fastened` mates carry the handlebar, front fender and both mirrors with the
fork, and the exhaust with the engine — they are SIBLINGS in the instance tree,
so without one they would not follow. Presets: `ride`, `turned_left`,
`stand_down`, `bump`.

The rear shock is deliberately unmated: its two eyes tie the frame to the
swinging engine, which is a closed loop, and cadgen evaluates pure forward
kinematics by design. It stays put while the engine swings.
