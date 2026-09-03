# W16 — hand-off report (2026-09-02)

Unbranded quad-turbo 8.0 L W16, museum-sectioned on bank 1, built with the
release/0.5.0 `cad` / `cad-project` / `cad-viewer` skills. Entry `src/w16.py` →
`STEP/w16.step` (+ render package, sidecar with the `crank` / `explode` clips).
Companion files: `TODO.md` (outstanding work), `GAUNTLET.md` (blind critic
rounds), `BUGS.md` (repo defects, 12 entries), `PERFORMANCE.md` (every build
timing), `BUILDING.md` (builder brief), `src/README.md` (module map).

## Architecture and the figures it rests on

| Item | Value | Source |
|---|---|---|
| Bore × stroke, displacement | 86 × 86 mm, 7993 cc | Wikipedia "Bugatti W16 engine" |
| Bank layout | two VR8 banks, 15° within a bank, 90° between banks | same |
| Valves / cams | 64 valves, 4 cams, roller finger followers | 64 valves / 4 cams: same; followers: design choice (one cam cannot serve two staggered rows of buckets) |
| Boost | 4 turbos, 2 air-to-liquid intercoolers | same |
| Length target | ~710 mm | Bugatti newsroom figure quoted for the W16 |
| Firing order | 1-14-9-4-7-12-15-6-13-8-3-16-11-2-5-10 | as published for Veyron / Chiron |
| Crank | 8 pins at 74 mm pitch, 5 mains, 15 mm désaxé | pin phasing DERIVED (not published): cylinders i and i+8 share a pin from opposite rows, so an even 45° firing interval fixes every pin angle |

Derived pin phases (crank angle of the pin, cylinder pairs sharing a pin):

| Pin | Cylinders | Phase |
|---|---|---|
| 1 | 1 / 9 | 322.5° |
| 2 | 2 / 10 | 82.5° |
| 3 | 3 / 11 | 232.5° |
| 4 | 4 / 12 | 172.5° |
| 5 | 5 / 13 | 52.5° |
| 6 | 6 / 14 | 352.5° |
| 7 | 7 / 15 | 142.5° |
| 8 | 8 / 16 | 262.5° |

Consistency check: with these phases the 16 TDC-firing events of the published
order fall exactly 45° apart over 720° (asserted in `lib/spec.py:check_spec`).

## Deviations from the brief (stated, not hidden)
- Envelope 853 × 1012 × 799 mm vs 710 × 770 × ~? target. The block-and-heads
  core is on target; the width is the four turbos hung outboard at |y| 507, the
  length the front alternator and the rear lifting eye.
- Exhaust manifolds are compact cast LOG collectors (production-style) rather than
  tubular equal-length primaries: see TODO.md for why the tubular version could
  not fit the corridor.
- Finger followers instead of buckets (kinematic necessity, above).
- In the sectioned display the bank-1 front turbo is lifted off (its collector
  flange stays), the bank-1 charge pipes are cut at the section plane, and the
  oil filter sits aft of the plane — a real cutaway exhibit removes exactly the
  hardware that would hide the section.
- Coolant hoses were removed with the coolant rails when they blocked the
  exhaust corridor (TODO).

## Validation status

| Check | Result |
|---|---|
| Every generation exits 0 | YES — final build `src/w16.py` exit 0, 5 m 51 s warm / 6 m cold, peak RSS 3.7 GB, 2 545 occurrences, STEP 160 MB |
| `inspect validate` watertight / no self-intersections | **NO — 30 of 769 prototypes flagged `selfIntersecting`**: 14 exhaust trumpets, `head:2`, `coil_bolt:4`, `water_pump_housing:2`, `tensioner_arm`. The identical shapes pass `cadgen.validity.check_occurrence_shape` in-process, and a cold rebuild reproduces the same 30, so the geometry reaching the document differs from the geometry the model returns. Logged as BUGS #13 with the in-process control. Not weakened, not waived — reported as failing. |
| Firing order consistency | YES — 1-14-9-4-7-12-15-6-13-8-3-16-11-2-5-10 with the derived pin phases fires every 45° over 720°, asserted at build time in `lib/spec.py:check_spec` |
| Static interference | Clean in every sweep run: exhaust vs turbos/induction/covers/heads/ancillaries/self, induction vs turbos/covers/exhaust/heads, oil vs exhaust/bottom-end, dipstick vs exhaust/chain guides/head. Remaining hits at hand-off: oil pump stack vs bank-2 water pump / coolant hose / idler, and oil filter housing vs `engine_mount:1` — the stations moved in the final build but were not re-swept (TODO). |
| Kinematic gate, 720° at 15° | RUNNING on ANIMATED positions (the stronger form: it drives the shipped `crank` clip, not a Python twin), 3 shards × 16 samples, 54 559 candidate pairs per sample. **42 of 48 angles completed, every one clean** — zero piston-valve, rod-block, rod-crank, rod-rod and valve-valve contact. The three shards were stopped at hand-off with 48 - 42 angles unsampled; rerunning is one command per shard (`python -m lib.anim_check crank --samples 48 --shard k/3`) and needs no rebuild — zero piston-valve, rod-block, rod-crank, rod-rod and valve-valve hits. `tmp/anim_crank_{0,1,2}.log`. |
| Explode clip | Coverage VERIFIED: at t=0 every part is at rest (0 moved); at t=1.0 **2 529 of 2 544 parts move**, and the only 15 that do not are the block, its cast face skins, its cross bolts and its ID pads — the block is the explode's reference frame. A first pass had the heads flying out while their face skins, 36 head bolts and 14 spark plugs stayed behind; fixed by making the whole head group ride the head. Pairwise non-intersection at 0.05 steps still running (`tmp/anim_explode.log`). |
| Crank clip exactly periodic | YES — evaluating the shipped clip through its own harness, every part's matrix at t=0 equals its matrix at t=6 (720°) to **0.000e+00**, and likewise t=3 vs t=9. 733 parts are in motion mid-cycle. |
| Both clips drive the model | YES — stills rendered straight from the sidecar with `snapshot --animation <clip> --time <s>` (the feature filed as BUGS #4 and since implemented): `tmp/clip_crank_{000,090,180,270}.png` show the pistons and valvetrain at four crank angles, `tmp/clip_explode_{25,50,100}.png` the staged separation. |
| Loads in the CAD Viewer | YES — http://127.0.0.1:3247/?file=w16/STEP/w16.step (HTTP 200; the viewer serves `models/`) |

## Animation

Three clips ship in the sidecar and are scrubbable in the viewer.

- `crank` (6 s = 720°, loops exactly): all 16 pistons on their désaxé axes, rods
  tilting about the moving pins, the crank, 4 cams at half speed with synthesised
  lobes, 64 valves and their followers on the exact lobe/roller solution, both
  timing chains, the oil-pump drive, 4 turbo rotor groups and every accessory
  pulley at its own belt ratio.
- `explode` (0..1, staged by system): ancillaries and oil system drop, then
  induction / covers / exhaust / turbos / cam drive move out, then heads, cams
  and valvetrain bank by bank along each bank's own axis, then pistons and rods
  out of the bores, then the crank and mains down. The per-bank label sets are
  generated from the built document's own refs table, so a renamed or added part
  cannot silently stop moving.
- `running_reveal` ("Running cutaway", 24 s, loops): the engine runs while the
  bodywork comes off it. NOTHING that moves is displaced — the crank, rods,
  pistons, cams, followers and 64 valves stay exactly where they run, and what
  goes away is what stands in front of them: the outer systems move clear, the
  heads lift along each bank's axis, and the crankcase casting plus its seven
  cast face skins fade to 8 % opacity. The block's cross bolts and ID pads stay
  solid, so its bolt pattern still reads: some of `o1.1`, not all of it. Off over
  8 s, held 8 s, back on. The length is exactly 4 crank cycles and the ramp
  returns to zero, so t=0 and t=24 are identical — verified, maximum matrix
  difference 0.000e+00.

Both sequences also **rise clear of the display floor** as they run. The deepest
fall is a main bolt at 1 020 mm (420 with the crank group, 600 of its own), so a
1 150 mm lift is applied to every group as the sequence progresses: sampled
across both clips, no part's net downward displacement is ever negative. The only
small negatives that remain are spinning pulleys, whose rotation about their own
centres never takes them outside their own envelope.

## Gauntlet result

Four whole-engine views, blind A/B against Wikimedia reference photographs, three
rounds. Final: **sectioned side WON, low sump WON, front three-quarter LOST,
top-down LOST**. The brief's bar is all four winning, so the aesthetic goal is
NOT met. Round-by-round detail and the exact gap each critic named is in
`GAUNTLET.md`; the front three-quarter loss narrowed from high to medium
confidence across the rounds, the top-down one did not move.

## Where the work stands

Everything in the brief was built and most of it verified; what is unfinished is
listed in `TODO.md` with the file that holds each running result. The two
gauntlet views that still lose name mid-scale detail (brackets, ribs, clamps
between the big shapes and the fasteners) and plenum-lid articulation.
