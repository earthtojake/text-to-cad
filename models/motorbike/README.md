# motorbike — retro step-through scooter

An original, unbranded CAD interpretation of a reference photo of a Honda
Giorno-class scooter model kit in exploded view (cream body panels, brown
saddle, black underbone frame, silver unit engine, chrome trim — reference
image kept locally, not part of the tree). Real-scooter scale from public
Giorno-class figures (wheelbase ~1190 mm, seat height ~735 mm, 10 in cast
wheels) treated as design intent. No logos, badges, or wordmarks.

## Layout

```
motorbike/
  src/        authored code — 20 model scripts + lib/ (see src/README.md)
  STEP/       generated artifacts + their .step.json sidecars (not committed)
  tmp/        snapshots and scratch (gitignored)
```

`src/README.md` is the model catalog: which script builds which artifact, what
each `lib/` module owns, and the assembly's declared kinematics. Read it first.

- `src/lib/spec.py` — **single source of truth**: bike-frame coordinate
  conventions, palette, hardpoints (axles, steering axis, engine pivot, shock
  mounts, bodywork section tables). No builder restates a shared dimension.
- `src/lib/lib.py` — shared geometry vocabulary (revolved wheel profiles,
  partial annular fender bands, lofts along X and along a curved side-view
  path, spline-swept tubes, coil springs between two points). API contracts
  were probed before use; see the header notes.
- Builder modules `src/lib/{wheels,chassis,frontend,drivetrain,bodywork,trim}.py`
  each expose `build_*()` returning labeled, colored shapes authored directly
  in the BIKE frame.
- 19 part entries under `src/`, each an individually buildable STEP.
- `src/motorbike.py` — full assembly: 23 labeled children (46 rendered parts)
  composed at identity, with native build123d joints recording the placement
  relationships AND a `kinematics=` block of typed mates for the viewer.
  Occurrence order is frozen; see its header.

## Coordinates

+X forward (front wheel), +Y rider left, +Z up; z = 0 is the ground plane,
x = 0 at mid-wheelbase. The steering axis passes through `FRONT_AXLE`,
raked 27 deg, parameterized by `steer_point(t)`.

## Commands (run from this directory)

```bash
python src/<entry>.py                                   # its __main__ builds the model
python src/<entry>.py                                   # unchanged: a no-op
ls src/*.py | xargs -n1 -P4 python                      # everything, in parallel
cadgen step inspect refs STEP/<entry>.step --facts
cadgen step inspect validate STEP/<entry>.step
cadgen step inspect interfere STEP/motorbike.step
cadgen step snapshot STEP/<entry>.step tmp/<entry>.png
cadgen step snapshot STEP/motorbike.step tmp/turned.png --kinematics turned_left
```

Snapshots are expensive (a headless browser each): batch several into one
`--job` packet rather than running them in parallel.

The CAD Viewer opened at this directory catalogs `STEP/`; model scripts never
appear in it, so before anything is built the catalog is `src/`, not the viewer.

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
- A leaf solid must never carry the same label as the group it sits in: a
  `#<label>` mate ref resolves leaf-first, so the group's other children would
  silently be left behind. That is why `trim.build_mirror` labels its shell
  `mirror_shell:<side>` while the assembly labels the group `mirror:<side>`.

## Verification (2026-08-31, cad-project migration)

- All 20 entries build from `src/`; every component content hash is identical
  to the pre-migration flat-layout build, so the move, the `from lib import ...`
  rewrite and the lazy `bd.` import idiom are geometry-neutral.
- `inspect refs --facts`: assembly 46 occurrences / 845 faces / 2257 edges,
  bounds (-808.0, -412.0, 0.0) → (814.3, 412.0, 974.5). Front axle x = +595,
  rear axle x = -595 (wheelbase 1190.0 exactly); both tires touch z = 0.
- Snapshot review: every one of the 20 entries rendered and read, plus the
  assembly at iso / side / rear, and posed at `turned_left`, `stand_down` and
  a wheel-spin + full-bump combination to confirm each mate drives exactly the
  parts it names.
