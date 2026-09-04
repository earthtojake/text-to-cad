# Building the W16 — rules for every part builder

Read this whole file before touching a module. Then read `src/lib/spec.py`
(the frame and every shared number) and skim `src/lib/geo.py`,
`src/lib/palette.py`, `src/lib/castings.py`, `src/lib/fasteners.py`.

## Environment

- Python: `/Users/jakefitzgerald/robots/text-to-cad/.venv/bin/python` (cadgen is
  installed editable there). Node 22 is on PATH.
- Project root: `/Users/jakefitzgerald/robots/text-to-cad/models/w16`. Run
  everything from there. Scratch renders go in `tmp/` (gitignored).
- Skills docs: `/Users/jakefitzgerald/robots/text-to-cad/skills/cad/SKILL.md` and
  `references/build123d-modeling.md` (READ the traps section: `align=None`,
  `.located()` vs `.moved()`, multi-tool booleans, tangent booleans, fillets
  last, `Plane.rotated` is world-axes, colour is linear unless via `srgb()`).
- Build the whole engine: `python src/w16.py`. Each system is its own model
  (`src/<system>.py` wraps `lib/<system>.build`), so the engine builds only the
  systems whose sources changed, in parallel, and links the rest from the
  store; `python src/<system>.py` builds yours alone (the engine picks it up on
  its next run). `cadgen store why src/w16.py` says which system is stale and
  why. Other agents build concurrently; builds never wait on one another.
- Never edit `spec.py`, `kin.py`, `geo.py`, `palette.py`, `castings.py`,
  `fasteners.py`, `collide.py`, `animgen.py`, `w16.py` without being told to.
  Add helpers inside your own module.
- Never `git commit`. Never touch files outside `models/w16`.

## The frame (memorise it)

- X = crank axis, +X = FRONT (damper, chains). −X = rear (flywheel).
- Z up. +Y = bank 1 (cylinders 1–8), −Y = bank 2 (9–16). Banks at ±45°, rows
  at ±7.5° inside a bank. Bank coordinates: `spec.bank_point(bank, x, m, h)`
  (m toward the engine centre in the deck plane, h up the bank centreline from
  the crank axis). Deck at h = 226, head top (cam centreline plane) at 358,
  cam-cover joint at 386.
- Every module authors geometry DIRECTLY in the engine frame and returns a
  flat list of labelled, coloured leaf solids (`palette.style(shape, label,
  colour)`); the system model `src/<system>.py` wraps that list as one
  labelled group and `w16.py` links the groups. Labels are unique, lower_snake,
  `part:qualifier` (`turbo_housing:1_compressor`). Colour every leaf.

## Four surface languages — keep them distinct

- Cast alloy (`palette.CAST`): block, heads, sump, turbo centre housings,
  covers that are cast, coolant manifolds. Generous radii (3–8 mm on big
  castings), 2–4° draft, parting lines, soft transitions, bosses with root
  fillets, ribs following load paths. Use `castings.py`.
- Machined (`palette.MACHINED` / `MACHINED_STEEL`): every mating face, cam
  caps, bearing caps, compressor housings, damper, flywheel face, throttle
  bodies. Crisp, flat, sharp 0.5 mm chamfers, no draft.
- Carbon / dark composite (`palette.CARBON`, `COMPOSITE`): plenums, cam
  covers, some brackets. Smooth, tight radii, visible fastener pattern.
- Fasteners: titanium (`TITANIUM`) bolts, `STEEL_DARK` studs/nuts/chains/cams,
  turbine housings `HEAT_TINT` with a `HEAT_TINT_BLUE` band, primaries
  `INCONEL`. Use `fasteners.py` and seat every bolt with `fasteners.place()`
  or `geo.locate()`; consistent head types per system; deliberate patterns
  (rings, rows). Random bolt placement is an automatic fail.

## Kinematics are sacred

- Anything that moves is positioned by `lib/kin.py` at θ = 0 and animated by
  `w16.anim.js`. Do not change a moving part's frame, size envelope where it
  meets another moving part, or label scheme. If a visual change you want
  would move a moving part, STOP and report it instead.
- New static geometry must not intrude into any moving part's swept volume:
  crank counterweights (R 78 about the X axis, x −300..300), rod swing
  (`spec.CRANKCASE_CLEAR_R` = 88 about the axis over each bay), piston travel
  in the bores, valve/follower pockets in the heads, cam lobes (R 20.4 about
  each cam axis), chain runs (the two loops at x = 318 / 330).
- If you touch a moving part or anything within 5 mm of one, run the gate:
  `cd src && python -m lib.collide --step 45 --cyl 1,2,9,10` (fast subset) and
  report the table. The full gate is run centrally.

## The museum section

Bank-1 STATICS are cut for x > `spec.SECTION_X` (121), y > 12, z > −10:
block, head, cam cover, plenum/runners, fuel rail, cam caps in that region.
Use `geo.sectioned(shape, bank, enabled)` for solids and
`geo.in_section_void(point, bank, enabled)` to omit a fastener seated in the
removed region. Moving parts are NEVER cut. Cut faces are plain material (no
red paint). Bank 2 is intact.

## Deliverable per module

1. Your module `src/lib/<name>.py` exposing `build(sectioned: bool = True)`
   → list of leaf solids (plus any documented sub-builders). Every solid
   passes `geo.sound()`; check with a loop before you hand over.
2. `python src/w16.py` exits 0 with your module in it.
3. Renders in context, with the PRESENTATION theme (never the default):
   ```bash
   cadgen step snapshot --job tmp/<name>_job.json
   ```
   where the job is
   ```json
   {"input": "STEP/w16.step", "mode": "view",
    "theme": "render/presentation_theme.json",
    "display": "render/presentation_display.json",
    "outputs": [{"path": "tmp/<name>_a.png", "camera": {"position": [x,y,z], "target": [x,y,z]}}],
    "render": {"padding": 0.04, "sizeProfile": "presentation"}}
   ```
   (camera `position`/`target` are engine-frame mm; use `"camera": "iso"` etc.
   for presets). READ every render you make. Zero faceting, zero missing
   fillets, zero unblended intersections at render resolution.
4. A short report: what you built, labels, part count, checks run, renders,
   anything you could not make work (be honest — a hidden fallback that
   changed the look is a bug).

## Performance rules

- One multi-operand boolean, never pairwise chains. Tools inside one cut must
  not overlap each other (fuse overlapping tools first, or cut in families).
- Fillet last; use the ladders; never 3D-chamfer tangent chains.
- Build a prototype once and place copies with `.moved(Location)` /
  `geo.locate()` so repeated parts share geometry.
- Keep helix sweeps, threads and dense patterns light; a real-looking part
  beats a heavy one.

## Timing log (record-keeping, mandatory)

After EVERY `python src/w16.py` you run, append one row to the "Full assembly"
table in `PERFORMANCE.md`: what you changed since your previous build, the
result (built / current / FAILED), the wall time (`time python src/w16.py`),
and whether the log shows your module rebuilding or being served from cache.
Do not do any performance work; just record.

## Memory discipline (mandatory — the machine ran out of memory once)

Run ONE build at a time: never a `python src/w16.py` and a scratch model in
parallel, never two scratch models at once, never a snapshot while your build
is still running. Delete scratch STEPs as soon as they are rendered. The
central gate runs in at most three shards.
