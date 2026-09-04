# w16 models

Quad-turbo 8.0 L W16, sectioned museum cutaway with working kinematics.

| Script   | Artifact        | Description                                                            |
|----------|-----------------|------------------------------------------------------------------------|
| w16.py   | STEP/w16.step   | Full engine assembly: the thirteen system models below, linked in occurrence order; carries `w16.anim.js` |
| block.py | STEP/block.step | `o1.1` block casting + main caps + shells + block fasteners |
| crank.py | STEP/crank.step | `o1.2` crankshaft, damper, flywheel |
| pistons.py | STEP/pistons.step | `o1.3` 16 x piston/rings/pin/circlips/rod/cap/bolts/shells |
| heads.py | STEP/heads.step | `o1.4` two heads, plugs, core plugs, head bolts |
| valvetrain.py | STEP/valvetrain.step | `o1.5` 64 valves + springs + retainers + followers + HLAs |
| cams.py | STEP/cams.step | `o1.6` four camshafts + caps |
| camdrive.py | STEP/camdrive.step | `o1.7` sprockets, chains, guides, tensioners |
| covers.py | STEP/covers.step | `o1.8` cam covers, coils, plug wells, breathers |
| oil_system.py | STEP/oil_system.step | `o1.9` dry-sump pan, windage tray, pumps, filter |
| turbos.py | STEP/turbos.step | `o1.10` four turbochargers |
| exhaust.py | STEP/exhaust.step | `o1.11` 16 primaries, collectors, downpipes, shields |
| induction.py | STEP/induction.step | `o1.12` intercoolers, plenums, throttles, charge pipes, fuel rails |
| ancillaries.py | STEP/ancillaries.step | `o1.13` alternator, water pumps, belt, coolant manifolds, bell housing |

Build: `python src/w16.py` builds the root and every stale system beneath it
(in parallel, one worker per system) and links their results; `python
src/<system>.py` builds one system alone — the engine does not pick it up
until `w16.py` is rerun. Unchanged models are no-ops. The museum section is
one flag, `lib/spec.py:SECTIONED`, read by every system. Imported sources: none.

## Settled architecture (sources in `lib/spec.py`)

- 7993 cc, 86 x 86 mm, two VR8 banks (15 deg within a bank) at 90 deg, 64 valves,
  4 cams, 4 turbos, 2 air-to-liquid intercoolers, dry sump. Sources: Wikipedia
  "Bugatti W16 engine" (bore/stroke/displacement/angles), Bugatti newsroom (710 mm
  length), firing order 1-14-9-4-7-12-15-6-13-8-3-16-11-2-5-10 as published for
  the Veyron/Chiron.
- 8 crankpins, uniform 74 mm pitch, 5 mains; each pin carries cylinder i (bank 1)
  and i+8 (bank 2) from OPPOSITE rows. Pin phase angles are DERIVED from the
  firing order + even 45 deg firing (not published).
- Desaxe bores (15 mm), wedge-crown pistons, roller finger followers (one cam
  cannot serve two rows of buckets), all intake valves parallel and all exhaust
  valves parallel across both rows.

## Mesh tolerances

Every model here — `w16.py` and the thirteen system models — declares the same
`mesh_tolerance=0.0006, mesh_angular_tolerance=0.3`, so a system rendered on its
own tessellates exactly as it does inside the engine. Decorator arguments must be
literals (cadgen reads them statically), so the value is repeated in each file
rather than imported from `lib/spec.py`; change all fourteen together.

## `lib/` — shared code, no models

| Module            | Role                                                             |
|-------------------|------------------------------------------------------------------|
| `spec.py`         | **Single source of truth**: every shared number and the frame     |
| `kin.py`          | Pure kinematics: pistons/rods, valve lift, followers, lobe synthesis |
| `geo.py`          | Frames, prisms, section cutter                                    |
| `palette.py`      | Material colours (sRGB hex via `cadgen.srgb`)                    |
| `castings.py`     | Casting/machining vocabulary: draft, ribs, bosses, ladders        |
| `fasteners.py`    | Bolts, nuts, studs, lifting eye, ID pad, `place()`                |
| `bottom_end.py`   | Crank, main caps + shells, flywheel, damper                       |
| `pistons.py`      | Pistons, rings, pins, rods, rod bolts + shells                    |
| `block.py`        | Block/crankcase casting (sectioned on bank 1)                     |
| `heads.py`        | Heads (sectioned on bank 1)                                       |
| `valvetrain.py`   | Valves, springs, retainers, collets, followers, HLAs              |
| `cams.py`         | Camshafts with synthesised lobes, caps, cap bolts                 |
| `collide.py`      | Kinematic collision gate: `cd src && python -m lib.collide`       |

The section: bank-1 statics are cut for `x > SECTION_X` (cylinder 3's
centreline), keeping the centre spine; moving parts are never cut.
