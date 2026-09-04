# moonwatch models

| Script                  | Artifact                       | Description                                                        |
|-------------------------|--------------------------------|--------------------------------------------------------------------|
| moonwatch.py            | STEP/moonwatch.step            | Full watch: case + dial/hands + movement + bracelet; carries the kinematics and `moonwatch.step.js` |
| case.py                 | STEP/case.step                 | Case cluster: middle, bezel stack, crystal, caseback, crown, pushers, lugs |
| dial.py                 | STEP/dial.step                 | Three-register step dial, applied indices, printed tracks, full hand stack |
| movement.py             | STEP/movement.step             | Complete movement = movement_base + keyless_works + chrono_works    |
| movement_base.py        | STEP/movement_base.step        | Main plate, barrel, going train, bridges, escapement, balance       |
| keyless_works.py        | STEP/keyless_works.step        | Stem, winding/sliding pinions, setting lever, yoke, motion works    |
| chrono_works.py         | STEP/chrono_works.step         | Column wheel, levers, lateral clutch, runners, hammers              |
| bracelet.py             | STEP/bracelet.step             | Flat three-link bracelet, end links, fold-over clasp                |
| finishing_sampler.py    | STEP/finishing_sampler.step    | Standing coupon exercising the shared finishing vocabulary          |

Build: `python src/<script>` per row; unchanged models are no-ops.
Imported sources: none — every artifact is generated.

## Composition

`moonwatch.py` and `movement.py` compose their children by FUNCTION: they
import the sibling model module (importing never builds) and wrap its model
function with `cadgen.compose.memo`, which caches the child's geometry as a
traced scope keyed by that child's own source closure. The retired
path-addressed `cadgen.compose.child_entry()` seam raises a teaching error.

## Shared code — `lib/`

`lib/` holds plain modules; none of them is a model.

- `lib/spec.py` — master dimensional spec + shared palette. **Single source of
  truth**; no builder restates a shared dimension. Read its header for the
  coordinate conventions (watch frame vs movement local frame).
- `lib/finishing.py` — shared finishing vocabulary: `anglage_top`,
  `safe_chamfer`/`safe_fillet` (retry ladders), `slotted_screw`, `jewel*`,
  `snailing_cutter`, `geneva_stripes_cutter`, `perlage_cutter`,
  `straight_grain_cutter`, `train_wheel`, `pinion`, `heart_cam`. Use these —
  do not fork private variants of the same vocabulary.
- `lib/materials.py` — applies the shared material/appearance pass to a
  finished compound.
- Cluster builders: `lib/case.py`, `lib/dial.py`, `lib/mvt_base.py`,
  `lib/mvt_keyless.py`, `lib/mvt_chrono.py`, `lib/bracelet.py` — each exposes
  `build_*()` returning labeled, colored parts in the frame documented in
  `lib/spec.py`.

Scripts sit directly in `src/`, so python already has `src/` on `sys.path`:
`from lib import spec as S` and `import case` both work from any working
directory, with no `sys.path` manipulation.

## Articulation

`moonwatch.py` declares `KINEMATICS` (typed mates, pure data), which lands in
`STEP/moonwatch.step.json`. Choreography is `STEP/moonwatch.step.js`, the render
module beside the document — authored, committed, loaded by the viewer by name;
no build reads it.

- **Mates** — the watch's real DOFs: `hour`, `minute`, `chrono_seconds`,
  `sub_seconds`, `chrono_minutes`, `chrono_hours`, the going train (`center`,
  `third`, `fourth`), the escapement (`escape`, `pallet`, `balance`), the
  chronograph (`chrono_runner`, `coupling`), `crown` (cylindrical: `.turn` to
  wind, `.travel` to pull out for setting), and the `pusher_start` /
  `pusher_reset` sliders. Parts that must ride a moving part but are its
  SIBLINGS in the instance tree (hand lume + hub, wheel pinions, pallet
  stones, the balance's 16 timing screws, the stem on the crown) are joined
  with `fastened` mates.
- **Couplings** — the gear ratios, as ratio arithmetic, not code:
  `running` (seconds of elapsed time, 0..3600) and `chrono` (seconds of
  chronograph running, 0..1800).
- **Poses** — `rest`, `one_minute`, `half_hour`, `chrono_at_10min`,
  `start_pressed`, `reset_pressed`, `winding`, `setting`.
- **`moonwatch.step.js`** — choreography only: the `running`, `reveal`,
  `showcase` and `grand_tour` clips (staged explodes, the movement's
  lift-and-flip out of the case, the sinusoidal balance swing and the escape
  wheel's per-beat snap — neither of the last two is a linear gearing, so
  neither is a mate).

The bezel is deliberately NOT a mate: a tachymeter bezel is press-fit and does
not rotate.
