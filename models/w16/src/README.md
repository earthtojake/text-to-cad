# w16 models

Quad-turbo 8.0 L W16, sectioned museum cutaway with working kinematics.

| Script   | Artifact        | Description                                                            |
|----------|-----------------|------------------------------------------------------------------------|
| w16.py   | STEP/w16.step   | Full engine assembly, grouped by system; carries `w16.anim.js`         |

Build: `python src/w16.py` (unchanged models are no-ops). Imported sources: none.

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
