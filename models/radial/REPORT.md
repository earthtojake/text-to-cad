# Nine-cylinder radial: final report (2026-09-25)

Final assembly `models/radial/STEP/radial.step` (geometry 2026-09-25 03:23; re-saved 04:36 only to embed the explode clip, with no system STEP changed), 18 system STEPs in
`models/radial/STEP/`, sources in `models/radial/src/`. Unbranded: no names, logos or plate text.
Paths under `tmp/` below (renders, videos, gate logs) are generated and not committed. Rebuild with
`python src/radial.py`, then run the tools in `src/README.md`.

**Bearing STEP round trips:** the three bearing fixes from the original model worktree are
included. An isolated check on 2026-09-29 with unmodified main cadgen confirmed valid source and
saved solids with a maximum relative volume difference of 1.01e-7. No full engine rebuild was
repeated for the renderer/model split; the original worktree records a successful full build
with PR #449 on 2026-09-27.

## Figures and sources

| figure | model | public source |
|---|---|---|
| bore × stroke | 146 × 146 mm | R-1340 Wasp: 5.75 × 5.75 in (Wikipedia "Pratt & Whitney R-1340 Wasp"; FAA TCDS) |
| overall diameter | ~1,270 mm across the heads (vertex measure of the rocker covers) | R-1340: 51.75 in = 1,314 mm (same sources) |
| cylinders | 9, single row, 40° pitch | — |
| firing order | 1-3-5-7-9-2-4-6-8 | FAA-H-8083-32 Powerplant Handbook |
| cam ring | 4 lobes per track, 2 tracks, 1/8 crank speed, turning opposite the crank; 32T crank gear → 48/15T idler → 80T internal ring | (n−1)/2 rule, FAA-H-8083-32; enginehistory.org R-1340 |
| reduction | 3:2 planetary: crank-driven 72T bell, fixed 36T sun, 6 × 18T planets, carrier = prop shaft (prop/crank = 72/108 = 2/3) | enginehistory.org R-1340 / R-1535 |
| supercharger | gear-driven centrifugal, 10:1 (60/20 × 40/12), coaxial | Wikipedia R-1340; enginehistory.org |
| rotation | clockwise viewed from the rear | US right-hand convention |
| rings | 3 compression, 2 oil control, 1 scraper | enginehistory.org R-1340 |
| master rod | L 265, knuckle circle ρ 62, 8 knuckle pins, 8 articulating rods (L 203) | design, within the real envelope |

Design numbers not taken from a source are marked "(design)" in `src/lib/spec.py`.

## Consistency

`spec.check_spec()` and `kin.check_timing()` pass. They assert:
- the firing order;
- 1/|cam ratio| = 2 × lobes;
- the cam and blower gear trains;
- the planetary assembly and tooth-count conditions;
- valve timing phased to the firing order.

The animation's JS runtime matches kin.py to 3.5e-12 across all moving labels (animcheck PASS).

## Validation (final geometry)

- **Builds:** every build exited 0. The final assembly build took 68 s: 18 system checks, then the assembly in 32 s. After the fuel-line fix it took 25 s.
- **Solids:**
  - validity (BRepCheck, closed shells, positive volume): 0 bad across all 18 systems;
  - self-intersection, topology and boundary edges: 0 issues across all 18 systems.

  Logs: `tmp/final/checks.log`.

  **Correction (2026-09-26):** three components are damaged in the saved STEP even though they pass
  BRepCheck. Found by the STEP read-back verification developed afterwards on branch
  `claude/cadgen-perf-readback-validity`, which compares written volume against read-back volume.
  OCCT's STEP writer changed their geometry, and `main` stored the result at exit 0.

  | part | volume written | volume read back |
  |---|---|---|
  | `propshaft:thrust_balls` | 49,564 mm³ | 38,550 mm³ (−22%) |
  | `impeller:bearing_front` | | −19% |
  | `impeller:bearing_rear` | | −7.5% |

  **Fixed:** preserve the dimensions and labels, but orient the sphere seams and poles clear of
  their boolean trimming loops. Thrust balls use radial poles and a +Y seam; impeller balls
  use bearing-axis poles and outward radial seams. These are the original model's 2026-09-27
  fixes, carried into the sample sources. Isolated STEP round trips on 2026-09-29 produced:

  | part | volume written | volume read back |
  |---|---|---|
  | `propshaft:thrust_balls` | 49,564.131808 mm³ | 49,564.136788 mm³ |
  | `impeller:bearing_front` | 5,963.905259 mm³ | 5,963.905259 mm³ |
  | `impeller:bearing_rear` | 3,587.927839 mm³ | 3,587.927839 mm³ |

  All three source and saved shapes pass validity checks. This check builds only the three
  bearing shapes; it does not rebuild the engine or certify its teardown choreography.
- **Static interference:** every leaf pair at rest, 11,538 pairs, **0 clashes**
  (`tmp/final/gate_static5.log`). The first final run found one clash: the new accessory fuel line
  through cylinder 6's intake elbow (164.7 mm³). It was re-routed with ≥ 14.9 mm clearance and
  re-gated.
- **Kinematic gate:** 720° in 10° steps (73 angles), every moving leaf against every other motion
  group, clash = common volume > 0.5 mm³. **0 clashes in every category** (piston-valve, rod-rod,
  rod-crankcase, pushrod-fin, piston-piston, piston-barrel, other). No part was shrunk to pass. The
  printed table is in `tmp/final/kin_table.txt`.

  Caveat: this run loaded the STEP from just before the fuel-line re-route. That change is one static
  line at least 14.9 mm from its neighbours and away from every moving part. The static gate was re-run
  on the final file.

**Correction (2026-09-27): the gates' 0-clash result is weaker than stated above.** A parity
battery later pushed real part pairs into each other by a known distance, confirmed each overlap
with an exact boolean, and counted how many the gate caught:

| pushed in by | moving pairs caught | static pairs caught |
|---|---|---|
| 0.3 mm | 2 of 19 | 6 of 11 |
| 0.6 mm | 22 of 26 | 12 of 13 |
| 5 mm | all | 21 of 23 |

(Log: `tmp/perf/parity_compare.log`.) Shallow interference below about 0.6 mm can go undetected:
the gate samples at about 1 mm pitch and treats anything under 0.25 mm deep as contact. The two
static misses at 5 mm point to a containment-check bug for thin parts fully inside another body.
The delivered engine may therefore contain undetected minor interference. Not yet fixed.

## Gauntlet

- **Part rounds:** none won (all 9 lost). Per the user's direction they stopped at "good enough".
- **Whole engine** (4 views × 2 museum references, blind A/B, fresh Opus critics):

| round | result |
|---|---|
| 1 | 0/6 |
| 2 | 2/8 (section won both) |
| 3 | 0/8 |
| **4 (final)** | **4/8**: front A_06 WON, front three-quarter B_03 WON, section C_04 WON, rear three-quarter D_08 WON; lost front A_01, front three-quarter B_01, section C_03, dead rear D_01 |

In round 4 every view beat at least one of its references. The cylinder-mass gap named in round 3 is
fixed. Why the remaining four lost:

- **Front A_01 and front three-quarter B_01:** a monochrome satin-grey palette against restored
  brass, olive and black finishes.
- **Section C_03:** the head section reads as a flat red slab edged by stepped rectangular fins, and
  the combustion-chamber dome still reads dark.
- **Dead rear D_01:** too sparse and clean between the collector and the accessory case.

Full log: `GAUNTLET.md`.

## Known gaps and deviations

- **Exhaust collector:** couldn't sit at head height. Every cylinder's intake elbow and rear plug
  lead occupies that zone, and the carburettor blocks the bottom. It is a heavier ring hard against
  the rear of the heads instead.
- **Combustion-chamber dome in the section:** still renders dark.
- **Exploded view is NOT clean.** The clip is `explode` in the assembly; renders are
  `tmp/final/explode.mp4` (24 s) and `tmp/final/explode_025/050/075/100.png`.

  explodecheck was stopped at 18,000 of 69,533 pairs (26%) with **138 violating pairs**, listed in
  `tmp/final/explode_violations.txt`:

  | violations | pairs | step |
  |---|---|---|
  | barrels vs their hold-down nuts | 49 | 6 |
  | crankcase-to-blower nuts vs the blower case | 18 | 9 |
  | wrist pins and plugs vs the crankcase front half and rear nose case | 24 | 7 |
  | through-bolts and nuts vs the case halves | 14 | 7 |
  | other hardware (wires, counterweight pins, carrier nut) | 33 | — |

  Most are fasteners leaving along the same axis as the part they hold, so the brief's
  "fasteners first" order isn't fully honoured. The full count over all pairs is unknown and is
  likely several hundred. The check can resume from 33,500 cached pair results (`cd src && python -m lib.explodecheck --workers 4`).

  Deviations from the specified 9-step order:
  - **Knuckle pins:** they stop 13 mm short against the crank cheek, so the eight articulating rods
    leave with the master rod as one assembly.
  - **Bell gear:** leaves still bolted to its flange.
  - **Step 7:** the crankcase front half, rear nose case and cam ring leave forward together.
  - **Magneto feeds:** lift out sideways in step 6.
  - **Rockers 4E/7I:** still pass through their pushrods.
  - **Exhaust collector:** the interlock is unresolved, so its moves are forced through the parts around it.
- **Running clip:** `tmp/final/running.mp4`, an 8 s seamless 720° loop showing the firing order,
  cam ring, pushrods, impeller and propeller at 2/3 crank speed. The same clip, `running`, is
  embedded in the assembly for the CAD Viewer.

## Repo defects found (BUGS.md)

1. **STEP export can silently turn a valid solid invalid or into garbage.** Examples:
   - `seat_1I`: a 988 mm spike after read-back;
   - `head_2`: `BadOrientationOfSubshape` at a coincident R24 swept bore;
   - `thrust_inner`: invalid after the round trip.

   The writer should preserve validity or fail the build.
2. **Exact BRepExtrema distance on big finned castings is extremely slow**: seconds to over
   10 min per pair.

## Build performance (measured on the real final runs, not benchmarks)

| change | before | after |
|---|---|---|
| Build tool rebuilds stale systems outside the shared lock, per-system locks, fails fast | assembly runs of 446–1831 s under the lock (child rebuilds inside it); lock waits up to 3166 s; 3 runs failed on another builder's broken heads | final build 68 s end to end (18 system checks 0–5 s each, assembly 32 s under the lock); 25 s after the fuel-line fix; no lock waits in the final phase |
| Gate: nearest-sample depth first (k=4 only for points > PEN_TOL; decisions identical, 400/400 randomized parity), bounded spring cache, angle + 360° twin on one worker | 2767 s wall on 2 workers; sampling 5110 worker-s; peak 5.3 GB/worker; 504 cache drops | **1534 s wall** on 3 workers; sampling 4129 worker-s (−19%; an earlier report of 2949 / −42% was a reporting bug) on a heavier model (denser fins); **peak 4.2–4.3 GB/worker**; **0 cache drops** |
| Validity/self-intersection verdicts cached by STEP content hash | heads self-intersection 1175–2449 s per run | unchanged heads **0 s (2449 s skipped)**; full 18-system pass 13.5 min |
| Heads: heavy checks moved to the end of the build (asked of the heads builder) | heads body 1479 s | final heads build 1391 s (−6%; the builder didn't confirm the check change landed) |
| Static gate (only the depth change applies) | 229 s on 2 workers (lighter model) | 277 s on 2 workers, 197 s on 3 workers: no clear gain |

Not done (saved for later, ranked with evidence in `tmp/perf/REPORT.md`):
- **Heads construction:** rocker-box shell and air-stage restructure.
- **Lighter STEP files:** safety wires, lofted ports, cam lobe sampling.
- **Fastener and cutter caches:** shared modules, so they need one planned full rebuild.
- **Gate:** sample dedup and reusing samples across workers.
- **cadgen library:** daemon heartbeat vs the 3600 s silence kill, the double `Perform()` in
  `self_intersections`, deep copies in `moved()`, per-leaf digests, and assembly re-parse. The agent
  for this was stopped before committing anything, so the local branch `claude/cadgen-build-perf` is still
  at main.
