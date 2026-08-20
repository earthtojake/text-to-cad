# motorbike — retro step-through scooter

An original, unbranded CAD interpretation of a reference photo of a Honda
Giorno-class scooter model kit in exploded view (cream body panels, brown
saddle, black underbone frame, silver unit engine, chrome trim — reference
image kept locally, not part of the tree). Real-scooter scale from public
Giorno-class figures (wheelbase ~1190 mm, seat height ~735 mm, 10 in cast
wheels) treated as design intent. No logos, badges, or wordmarks.

## Layout

- `_spec.py` — **single source of truth**: bike-frame coordinate conventions,
  palette, hardpoints (axles, steering axis, engine pivot, shock mounts,
  bodywork section tables). No builder restates a shared dimension.
- `_lib.py` — shared geometry vocabulary (revolved wheel profiles, partial
  annular fender bands, lofts along X and along a curved side-view path,
  spline-swept tubes, coil springs between two points). API contracts were
  probed before use; see the header notes.
- Builder modules: `_wheels.py`, `_chassis.py`, `_frontend.py`,
  `_drivetrain.py`, `_bodywork.py`, `_trim.py` — each exposes `build_*()`
  returning labeled, colored shapes authored directly in the BIKE frame.
- Part entries (each an individually buildable STEP): `frame`,
  `center_stand`, `front_fork`, `handlebar`, `front_fender`, `front_wheel`,
  `rear_wheel`, `engine`, `exhaust`, `rear_shock`, `leg_shield`,
  `steering_cover`, `under_seat_body`, `rear_fender`, `seat`, `headlight`,
  `tail_light`, `turn_signal` (instanced 4x), `mirror` (instanced 2x).
- `motorbike.step.py` — full assembly: 23 labeled children composed at
  identity, with native build123d joints recording the functional
  relationships (steering, wheel spin, engine swing, stand pivot, rigid
  mounts). Occurrence order is frozen; see its header.

## Coordinates

+X forward (front wheel), +Y rider left, +Z up; z = 0 is the ground plane,
x = 0 at mid-wheelbase. The steering axis passes through `FRONT_AXLE`,
raked 27 deg, parameterized by `steer_point(t)`.

## Commands (run from this directory)

```bash
PY=../../../.venv/bin/python
$PY ../../../skills/cad/scripts/gen <entry>.step.py            # render package
$PY ../../../skills/cad/scripts/gen <entry>.step.py --write    # + .step file
$PY ../../../skills/cad/scripts/inspect refs <entry>.step.py --facts
$PY ../../../skills/cad/scripts/inspect validate <entry>.step.py
$PY ../../../skills/cad/scripts/inspect interfere motorbike.step.py
$PY ../../../skills/cad/scripts/snapshot --input <entry>.step.py -o out.png
```

Viewer links select the GENERATED entry — `?file=<name>.step.py`, e.g.
`…/models/renders/motorbike?file=motorbike.step.py`. Do NOT keep exported
`<name>.step` files inside this directory: a same-stem `.step` beside (or
under, in any subfolder) its `.step.py` generator is owned by the generator,
so the viewer reports the entry ready from the generator's render package
while the entry's own asset URL points at an unbuilt import-cache path — the
page freezes on the loading screen. Export with `gen --write` only when a
standalone `.step` is needed, and keep it outside this tree (or export from
the viewer's Save dialog).

## Design notes

- The engine is a **unit powertrain doubling as the swingarm** (scooter
  layout): it pivots on the frame at `ENGINE_PIVOT` and carries the rear
  wheel on a flange outboard of the left-side carrier plate; the CVT drum is
  rider-left, the exhaust rider-right. A wheel-arch annular cut keeps every
  engine-side solid out of the rear tire band between the sidewalls.
- Shock hardpoints (`SHOCK_UPPER`/`SHOCK_LOWER`) were placed by sampled
  clearance against the CVT drum and frame spine, then verified with
  `inspect interfere` (spring clears the drum by >10 mm).
- Body panels are **stylized solids**, not shelled: the frame spine and the
  shock's upper end are intentionally enclosed by the under-seat body, and
  the headlight shell is recessed into the apron. `inspect interfere`
  reports those as volumes; they are accepted mount/enclosure overlaps, not
  defects.
- Modeling rules honored: no 3D fillet after large booleans, rounded 2D
  profiles and lofts instead, booleans accumulated into single ops.

## Verification (2026-08-15)

- All 20 entries build; `inspect validate` clean (46/46 assembly occurrences).
- `inspect interfere`: no unintended clashes after the fixes above.
- `inspect measure`: wheelbase 1190.0 mm exactly; both wheel transforms
  identity after joint composition; fork axle and wheel axle coincide
  (dz 0.0); tires touch z = 0; seat top 752.5 mm.
- Snapshot review: side/iso/front/rear assembly views plus every part entry
  rendered and visually audited (see hand-off notes in the session).
