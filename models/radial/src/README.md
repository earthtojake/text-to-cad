# radial models

A nine-cylinder, single-row, supercharged, air-cooled radial aircraft engine,
modelled as a museum restoration of the 1930s–40s archetype. It is unbranded:
no names, logos or plate text. It has working kinematics, a sectioned cylinder
and a front crankcase window.

| Script | Artifact | Description |
|---|---|---|
| radial.py | STEP/radial.step | Full engine assembly: the eighteen system models below, in occurrence order. It embeds `ANIMATION_JS` (from `lib/anim_js.py`) with a `running` clip (720°, seamless), an `explode` teardown, and `exploded-running` (the running cycle, partly exploded; see below). |
| crankcase.py | STEP/crankcase.step | split power-section crankcase, cylinder pads, studs, main-bearing housings |
| crankshaft.py | STEP/crankshaft.step | two-piece single-throw crankshaft, counterweights, main bearings, drive gears |
| rods.py | STEP/rods.step | master rod + flange, 8 knuckle pins + retainers, crankpin bearing, 8 articulating rods |
| pistons.py | STEP/pistons.step | 9 pistons, 54 rings, 9 wrist pins + plugs |
| barrels.py | STEP/barrels.step | 9 finned steel cylinder barrels + hold-down nuts |
| heads.py | STEP/heads.step | 9 aluminium heads: deep fins, rocker boxes, covers, guides, seats, 18 spark plugs |
| valvetrain.py | STEP/valvetrain.step | 18 valves, springs, retainers, keepers, 18 rockers + shafts |
| cam.py | STEP/cam.step | cam ring, cam idler, 18 tappets + rollers |
| pushrods.py | STEP/pushrods.step | 18 pushrods, 18 pushrod tubes, packing nuts, connectors |
| nose.py | STEP/nose.step | nose case, tappet guides, thrust-bearing housing, governor pad |
| reduction.py | STEP/reduction.step | planetary reduction: bell gear, fixed sun, 6 planets, carrier, propeller shaft, thrust bearing |
| propeller.py | STEP/propeller.step | hub, three blades, spinner, retention hardware |
| blower.py | STEP/blower.step | blower section, diffuser, impeller, impeller drive gears |
| intake.py | STEP/intake.step | 9 intake pipes, couplings, carburettor |
| accessory.py | STEP/accessory.step | accessory case, 2 magnetos, starter, generator, fuel + oil pumps, oil sump |
| ignition.py | STEP/ignition.step | harness ring, 18 leads, plug elbows, magneto feeds |
| exhaust.py | STEP/exhaust.step | 9 stacks, collector ring, outlet, clamps |
| mount.py | STEP/mount.step | engine mount ring, bosses, bushings, bolts |

**Building.**
- `python src/radial.py` builds the root and every stale system beneath it.
- `python src/<system>.py` builds one system alone. The engine doesn't pick it
  up until `radial.py` is rerun.
- `tools/engine.py build | render JOB.json | build-render JOB.json` serialises
  builds and renders when several people or agents share the assembly.
- A cold build of everything takes about 70 min; heads and valvetrain take about
  25 min each.
- There are no imported sources.

**Shared helpers.**
- `lib/spec.py` is the source of truth for the frame and every shared number.
  Its SOURCES table cites each figure.
- `lib/kin.py` holds all the motion: crank train, valvetrain, gears and springs.
- `lib/geo.py`, `lib/castings.py`, `lib/fasteners.py` and `lib/palette.py` hold
  shared geometry, castings, fasteners and materials.
- The museum section and window live in `lib/geo.py`.
- `lib/explodedrun.py` is the layout of the `exploded-running` clip; `lib/animgen.py`
  bakes it (`python -m lib.animgen`, then `tools/engine.py build`).

## The `exploded-running` clip

The same seamless 720° cycle as `running` (8 s, all motion from `kin.py`), with
one constant offset per group composed on top, so everything keeps running while
the engine hangs partly exploded:

- **Stays assembled at the centre:** crankshaft, master rod, knuckle pins,
  articulating rods and pistons, plus the crank's cam drive gear.
- **Cylinders:** barrel, head, valves, springs, rockers and pushrods move 205 mm
  out along each bore, so every piston slides in free air below its cylinder.
  The rocker covers lift a further 60 mm.
- **Pushrods:** they stay seated in their rockers and keep their full motion. Their
  lower ends float clear of the tappets, which keep lifting in the cam section.
- **Crankcase and nose:** the crankcase front half moves 190 mm forward. The cam
  section (ring at 1/8, idler and tappets) moves 310 mm forward, and the nose case
  with the planetary gearing (the bell gear rides along at crank speed) 430 mm.
  The propeller hub moves 540 mm forward and turns at 2/3.
- **Rear:** the crankcase rear half moves 170 mm back. The blower moves 300 mm back
  with its whole 10:1 train, crank blower gear included. The accessory case moves
  430 mm back.
- **Hidden:** propeller blades, ignition, exhaust, intake, mount, pushrod tubes,
  crankcase through-bolts and the fuel line.

`lib/explodedrun.py` states the reasons.

## Architecture (sources in `lib/spec.py`)

- **Cylinders and size:** 146 × 146 mm bore and stroke (R-1340 Wasp: 5.75 × 5.75
  in), about 1,270 mm across the heads (R-1340: 51.75 in). Nine cylinders at a
  40° pitch.
- **Firing and rotation:** firing order 1-3-5-7-9-2-4-6-8. Clockwise rotation
  seen from the rear.
- **Master rod:** L 265 mm, knuckle circle ρ 62 mm, eight articulating rods of
  L 203 mm.
- **Cam ring:** 4 lobes per track, two tracks, 1/8 crank speed against the
  crank. The drive runs 32T → 48/15T idler → 80T internal ring.
- **Reduction:** 3:2 planetary, with a crank-driven 72T bell, a fixed 36T sun,
  and 6 × 18T planets on a carrier that is the propeller shaft.
- **Supercharger:** gear-driven centrifugal, 10:1 (60/20 × 40/12).
- **Checks:** `spec.check_spec()` and `kin.check_timing()` assert all of the
  above.

## Validation tools (manual; outputs go to ignored `tmp/`)

- **`lib/gate.py`** is the interference gate, run from `src/` as
  `python -m lib.gate --static` or `python -m lib.gate --step 10`.
  - `--static` checks every leaf pair at rest.
  - `--step 10` checks 720° in 10° steps against the viewer's own animation
    runtime.
  - Known gap: overlaps shallower than about 0.6 mm, and some thin parts
    fully inside another body, can go undetected (see `REPORT.md`).
- **`lib/animcheck.py`** checks that the JS animation matches `kin.py`, for
  `running` and for `exploded-running` (kin.py composed with the layout's offsets,
  and exactly its hidden set).
- **`python -m lib.gate --clip exploded-running`** gates that clip over 720° in
  10° steps. Every visible pair whose placement differs from rest is tested, and
  every pair that comes within about 2 mm goes to the exact boolean
  (`--exact-near`, the default), so the sampled test's shallow-overlap gap doesn't
  apply to the pairs it tests. Pairs still at their rest placement are the static
  gate's, and keep its gap.
- **`lib/explodecheck.py`** checks the exploded-view teardown.
- **Hand-off notes** sit beside the source: `REPORT.md` (the final state,
  including known defects), `BUILDING.md` (the builder brief), `GAUNTLET.md`
  (the aesthetic review log) and `BUGS.md` (repo defects found).
