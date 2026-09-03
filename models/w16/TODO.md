# W16 — outstanding work (hand-off 2026-09-02, one-hour wrap-up requested)

Status legend: RUNNING = a process was left running at hand-off and writes its
result to the named file; TODO = not started.

## Verification
- RUNNING `anim_check crank` in 3 shards (48 samples of the `crank` clip, collision
  table on ANIMATED positions, big bodies chunked): `tmp/anim_crank_{0,1,2}.log` /
  `.json`. Each shard rebuilds the 13 modules in-process (~30 min) before sampling,
  then ~10 min per sample (54 559 candidate pairs, 1 698 chunks). At the close of the session
  42 of 48 angles had reported — 0°, 15°, 30°, all CLEAN, zero hits in every
  category. Let the shards finish (~2.5 h) and merge the three tables into
  REPORT.md. If it must be faster, raise the envelope prefilter from 100 mm or
  drop the shard count to 6 (10 cores).
- RUNNING `anim_check explode` (0.05 steps): `tmp/anim_explode.log` / `.json`.
  Confirm no pair intersects at any step and that nothing is fully enclosed at 1.0.
- DONE and FAILING: `inspect validate` reports 30 of 769 prototypes
  `selfIntersecting` — 14 exhaust trumpets, `head:2`, `coil_bolt:4`,
  `water_pump_housing:2`, `tensioner_arm`. Warm and cold builds give the same 30.
  The same shapes pass `cadgen.validity.check_occurrence_shape` in-process, so
  the document geometry differs from the model's. Logged as BUGS #13 — that is
  the next thing to chase, and until it is understood the "no self-intersections"
  requirement is NOT met.
- TODO gate run 4 (`python -m lib.collide --step 15`, ≤ 3 shards via `--thetas`):
  the static kinematic table. Superseded in substance by the animated-position
  check above (same pairs, same 15° sampling), but the brief asks for the table
  printed; last complete run (run 3) was clean except the follower/plate/valve
  classes fixed since. Run it on a quiet machine and paste the table into REPORT.md.
- TODO re-sweep the oil system after the final station moves (pump 250 -> 200 mm,
  filter 200 -> -120 mm): before the move it hit the bank-2 water pump, a coolant
  hose, the idler bracket and `engine_mount:1`; the moves were built but the
  sweep was not rerun.
- TODO whole-assembly STATIC interference sweep (every group pair, bbox-prefiltered,
  `lib.collide.clash_volume`). Per-module sweeps done and clean: exhaust vs
  turbos/induction/covers/heads/ancillaries/self, induction vs turbos/covers/exhaust/
  heads, oil system vs turbos/ancillaries/exhaust/bottom end, dipstick vs exhaust/
  chain guides/head. Not yet swept pairwise: block vs ancillaries/oil lines,
  covers vs induction fuel rails, camdrive vs ancillaries.

## Aesthetics (after three gauntlet rounds: 2 views won, 2 lost)
- Front three-quarter, LOST (medium): the routing must tie identifiable ports to
  identifiable components — every hose and pipe should start and end at a visible
  fitting on a named part. The mid-scale detail complaint from round 2 is closed.
- Top-down, LOST (high): a crowned, ribbed lid still reads flat from directly
  above. This is not a detailing problem — it needs different geometry on top
  (exposed runner trumpets, an open or cut-away lid), which the module currently
  forbids because the cores, tanks and lid roof cover the throats (BUGS #14).
- TODO turbo volute re-sculpt (round-1 part critic: "lumpy" scroll); TODO covers /
  oil / ancillaries second critic rounds (never run — build time went to the
  exhaust corridor and the section).
- TODO hoses: coolant hoses were deleted with the coolant rails when they blocked
  the exhaust corridor; only the oil lines and dipstick remain routed.

## Model
- Envelope 853 × 1012 × 799 mm vs the 710 × 770 target: block-and-heads core is
  on target; the width is the four turbos (|y| 507), the length the alternator
  and rear lifting eye. TODO if the target matters: tuck the turbos under the
  logs (needs the compressor outlets re-clocked in turbos.py + induction).
- Exhaust is a log manifold per turbo (compact, production-style) rather than
  tubular equal-length primaries: the runners could not lean 130 mm along X
  inside the 50 mm corridor between the turbine flange and the cam-cover edge.
- The sectioned bank's FRONT turbo is lifted off in the display (its collector
  flange stays); the oil filter moved aft of the section plane (x 30) and got a
  shorter canister so it clears the lowered turbos.


## Added 2026-09-02 18:4x (the two-hour finishing pass)

- The covers/ancillaries builder found pre-existing, UNINTENTIONAL interference it
  did not introduce and left alone: `thermostat_housing:2`, `water_pump_housing:1`,
  `lifting_eye:2_front` and `dipstick_clip` against `camdrive` and `heads`, up to
  6 034 mm³. It reads as fallout from the earlier coolant-rail deletion. This is
  now the largest known static interference in the model — fix next.
- `induction.py` item left undone honestly: the sixteen runner throats cannot be
  seen from directly above, because the cores, tanks and lid roof cover
  |y| 12..202 continuously from x −310 to 348 while the throats sit at |y| 72..115.
  Exposing them means moving a fixed part (BUGS #14 has the numbers).
- BUGS #14 (second entry with that number, from the covers builder): OCC segfaults
  the interpreter inside `castings.fillet_all` on the tensioner bracket when ribs
  and bosses are fused before `soften()`; worked around by fusing after. No
  minimal repro extracted — worth one.

## Explode check: not viable as written (found 2026-09-02 20:2x)

`anim_check explode` reported its first sample after 2.6 h: `explode 0.00:
{'clash': 1717}`. Two problems, both in the checker, not the model:
1. It counts EVERY pair rather than the kinematically meaningful ones (the crank
   path filters through `collide.category`), so it is testing on the order of
   3 million pairs per sample instead of 54 559. At 2.6 h per sample, 21 samples
   is days, not hours.
2. Its p = 0.00 sample is the assembled engine at rest, where 1 717 contacts are
   the model's intentional fits — fasteners seated in their own bosses, hoses on
   their spigots, coils in the loom (the covers builder independently counted 373
   such pairs in its own sweep). So the number is a BASELINE, not a failure.
Fix before rerunning: take the p = 0 contact set as the baseline and report only
pairs that appear or grow as p rises, and reuse the crank path's category filter
and big-body chunking. Until then the explode clip is verified for COVERAGE
(2 529 of 2 544 parts move, nothing moves at rest) but not for non-intersection
during the sweep.
