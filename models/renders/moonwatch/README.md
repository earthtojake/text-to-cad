# moonwatch — hand-wound column-wheel chronograph

A 42 mm moonwatch-archetype chronograph, modeled to auction-catalog macro
quality: caliber 321-lineage movement (Lemania 2310 base — 27.0 mm × 6.74 mm,
18,000 vph, 7-column wheel, lateral clutch), black tachymeter bezel, black
three-register dial, twisted lyre lugs, display caseback, flat three-link
bracelet. Unbranded: no logos, no wordmarks, no caliber engraving — numerals
and scale markings only.

## Files

- `_spec.py` — master dimensional spec + shared palette. **Single source of
  truth**; no builder restates a shared dimension. Read its header for the
  coordinate conventions (watch frame vs movement local frame).
- `_finishing.py` — shared finishing vocabulary: `anglage_top`,
  `safe_chamfer`/`safe_fillet` (retry ladders), `slotted_screw`, `jewel*`,
  `snailing_cutter`, `geneva_stripes_cutter`, `perlage_cutter`,
  `straight_grain_cutter`, `train_wheel`, `pinion`, `heart_cam`. Use
  these — do not fork private
  variants of the same vocabulary.
- `finishing_sampler.step.py` — standing coupon exercising the vocabulary.
- Cluster helpers: `_case.py`, `_dial.py`, `_mvt_base.py`, `_mvt_keyless.py`,
  `_mvt_chrono.py`, `_bracelet.py` — each exposes `build_*()` returning
  labeled, colored parts in the frame documented in `_spec.py`.
- Entries: `case.step.py`, `dial.step.py`, `movement_base.step.py`,
  `keyless_works.step.py`, `chrono_works.step.py`, `movement.step.py`,
  `bracelet.step.py`, `moonwatch.step.py` (full watch).
- `render/presentation_theme.json` — the ONLY appearance used for critic
  comparisons (solid display, `presentation-large` size profile).

## Commands (run from this directory)

```bash
PY=/Users/jakefitzgerald/robots/text-to-cad/.venv/bin/python
$PY ../../../skills/cad/scripts/gen <entry>.step.py
$PY ../../../skills/cad/scripts/inspect refs <entry>.step.py --facts
$PY ../../../skills/cad/scripts/inspect validate <entry>.step.py
$PY ../../../skills/cad/scripts/snapshot --job <job.json>
```

Do NOT use `CADGEN_WARM=1` while several builders run in parallel — the warm
daemon serializes jobs per worktree. (Killing a client now aborts its
in-daemon job.)

## Modeling rules

- Booleans over many tools: build a list and apply in ONE operation
  (`base + [tools]`, `base - [tools]`) — pairwise accumulation is O(n²) and
  unusably slow at watch-finishing feature counts.
- Sub-mm bevels: prefer chamfering edges BEFORE booleans that would multiply
  edge count; use the `safe_*` retry ladders after.
- No 3D `fillet` after large booleans (OCC segfault risk — see repo memory);
  prefer rounded 2D profiles swept/extruded, or chamfers.
- Text (tachymeter numerals, subdial numbers): build123d sketch `Text` with a
  clean sans font, extruded ≤0.06 mm — raised print, or engraved+filled via
  boolean pairs. Never any brand text.
- Every visible part: `label` + `color` set. Anglage-carrying parts use the
  spec palette; polished bevel reads come from geometry + the theme.
- All entries must exit 0 under `scripts/gen`, pass `inspect validate`
  (watertight, no self-intersection), and be snapshot-reviewed with the
  presentation theme before hand-off.
