# moonwatch — hand-wound column-wheel chronograph

A 42 mm moonwatch-archetype chronograph, modeled to auction-catalog macro
quality: caliber 321-lineage movement (Lemania 2310 base — 27.0 mm × 6.74 mm,
18,000 vph, 7-column wheel, lateral clutch), black tachymeter bezel, black
three-register dial, twisted lyre lugs, display caseback, flat three-link
bracelet. Unbranded: no logos, no wordmarks, no caliber engraving — numerals
and scale markings only.

## Layout

```
moonwatch/
  src/            authored code — the only thing you edit
    README.md     the model catalog + shared-code and articulation notes
    *.py          one @step model per file (9 of them)
    lib/          shared builders and the dimensional spec (never models)
  STEP/           generated artifacts + their .step.json sidecars (gitignored)
    moonwatch.step.js   the render module beside moonwatch.step: choreography (authored, committed)
  render/         committed presentation JSON (themes + snapshot job template)
  tmp/            snapshots and scratch (gitignored)
```

`ls src/*.py` IS the model catalog; see `src/README.md` for the table, the
`lib/` inventory, and the kinematics/animation split.

`render/presentation_theme.json` is the ONLY appearance used for critic
comparisons (solid display, `presentation-large` size profile);
`render/job_template.json` is the snapshot job skeleton (replace `REPLACE`).

## Commands (run from this directory)

```bash
PY=../../.venv/bin/python
CADGEN=../../.venv/bin/cadgen

$PY src/<model>.py                                  # its __main__ builds the model
ls src/*.py | xargs -n1 -P4 $PY                     # rebuild everything
$CADGEN step inspect refs STEP/<model>.step --facts
$CADGEN step inspect validate STEP/<model>.step
$CADGEN step snapshot STEP/<model>.step tmp/<model>.png
$CADGEN step snapshot STEP/moonwatch.step tmp/set.png --kinematics setting
$CADGEN step snapshot --job <job.json>
```

`out=` on each decorator resolves relative to the SCRIPT, so every model writes
to `../STEP/<name>.step` and the project relocates as a unit.

Parallelize ACROSS models, never within one: the warm daemon runs a pool of
worker processes and overflows to cold rather than queueing, so several
builders no longer serialize behind one another. Snapshots each pay a headless
browser — run them serially, or batch views into one `--job` packet.

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
- Labels are the canonical refs for mates and animation targets, and they are
  unique across the full assembly — keep them that way.
- All models must exit 0, pass `inspect validate` (watertight, no
  self-intersection), and be snapshot-reviewed with the presentation theme
  before hand-off.
