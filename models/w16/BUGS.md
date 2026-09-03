# BUGS.md — text-to-cad repo findings while building the W16

Scope: bugs, errors, unexpected behaviour, missing features and unclear docs in the
text-to-cad repo itself (skills, cadgen, CAD Viewer), hit while building
`models/w16`. Problems with the engine model itself are NOT logged here.

Each entry: what I was doing, the exact command, the exact error/wrong output,
workaround, blocked?, fixed? (and which root file changed).

---

## 1. `from lib import ...` inside a model helper fails under the pipeline with an opaque error

- Doing: first full build of `src/w16.py`, whose part modules lazily imported a
  sibling module (`from lib import fasteners as F`) inside a function.
- Command: `python src/w16.py --verbose`
- Result: `ModuleNotFoundError: No module named 'lib'` from deep inside the
  build, although the same functions import fine under plain `python -c`.
- Cause: documented in `skills/cad/references/step-generation.md` ("sys.path
  does not survive into the model function"), but the failure names neither
  the rule nor the fix. A teaching error ("import at module top level; the
  pipeline restores sys.path before calling the model") would save a search.
- Workaround: hoisted every `from lib import ...` to module top. Not blocking.
  Not fixed in the repo (docs/UX nit).

## 2. Lazy-import hint fires even though every module uses `from cadgen import build123d as bd`

- Doing: rebuilding an already-current `src/w16.py`.
- Command: `python src/w16.py`
- Output: `hint: w16.py imported the CAD kernel at module top; use 'from cadgen
  import build123d as bd' ...` — but every module already does exactly that.
  Something at import time (module-level `bd.Align`/`bd.Location` defaults in
  helper modules, or `cadgen.srgb` in `palette.py`) resolves an attribute and
  triggers the kernel import; the hint points at the wrong fix.
- Impact: a current no-op re-run still pays the ~2.5 s import. Cosmetic;
  logged, not fixed.

## 3. (to verify) raw `bd.export_step` + `cadgen step snapshot` renders `srgb()` colours ~2 stops dark

- Reported by the fastener-vocabulary builder while previewing parts written
  with plain `build123d.export_step` and rendered through the imported-STEP
  path. `cadgen/color.py` says the package path applies the linear->sRGB byte
  conversion; the imported-document path may be skipping it. Generated `@step`
  models (this project) look right. Not blocking; to re-check with a minimal
  repro before filing.

## 4. `cadgen step snapshot` on a huge assembly: no way to render only ONE clip time

- Doing: verifying motion. The `.anim.js` can only be reviewed live in the
  Viewer; `snapshot` takes `--kinematics` (typed mates) but has no
  `--animation <clip> --time <t>` for choreography, so still evidence of an
  animated pose needs a separate Python harness (`src/lib/collide.py`).
  Missing feature, not blocking.

## 5. `inspect validate` reports `invalidTopology` for a solid that is valid in-process and valid after build123d's own STEP round trip

- Doing: validating the skeleton assembly.
- Command: `cadgen step inspect validate STEP/w16.step` → 16 x `rod_cap:N ['invalidTopology']`.
- Repro (tmp/fix/fixtest3.py): a big-end ring with two fused boss cylinders,
  split at z=0 by a box cut. `BRepCheck_Analyzer` + `BRepAlgoAPI_Check` pass on
  the shape in the model process; `bd.export_step` → `bd.import_step` gives a
  valid solid; but the same part written by the cadgen pipeline is reported
  invalid by `validate` (and `cadgen.read_step` of the written file shows the
  same). The exact-shape package path (brep blobs) appears to alter the
  topology of this particular shape; ring-only and ring+bridge variants pass.
- Workaround: `shape.fix()` (ShapeFix) before returning the part makes it
  survive. Applied in `src/lib/pistons.py`. Not blocking. Repo not changed —
  needs a cadgen-side look at what the package round trip does to that solid.

## 6. `selfIntersecting` only after rotation: two overlapping boolean tools (hex socket + tangent lead-in cone)

- Doing: validate flagged all 32 rotated `cam_cap_bolt` (M8 socket cap) but not
  the same bolt unrotated. Cause was in OUR fastener code (lead-in cone base
  tangent to the hex socket faces inside one cut) — recorded here only because
  the validity gate is orientation-dependent: the same shape passes
  `validate` at identity and fails at 30/45 deg. Not a repo bug; fixed in
  `src/lib/fasteners.py` by shrinking the cone base inside the hex.

## 7. No per-part material properties — one roughness/metalness/clearcoat for the whole scene

- Doing: presentation renders for blind A/B critics. Two independent critics
  named the same single largest gap: every part reads as the same material
  ("chrome-plastic" / "unpainted 3D print") — cast, machined, carbon and
  fasteners cannot be told apart.
- Where: `packages/cadgen-js/src/lib/viewer/surfaceMaterials.js`
  `applyMaterialSettingsToRecord` resolves roughness/metalness/clearcoat from
  the THEME only; the source colour is the only per-part channel that reaches
  the material. The theme JSON `materials` block is global.
- Impact: the brief's "four surface languages" can only be approximated by
  colour value (dark carbon, mid cast, bright machined) under one global
  gloss. Missing feature (e.g. a per-label finish map in the sidecar, or
  reading a finish from the source colour alpha / a label suffix). Not
  blocking; worked around with palette values + a lower global gloss.

## 8. `inspect validate` findings differ between runs / disagree with in-process checks (to confirm)

- Doing: validating the skeleton STEP twice while builders were running.
- Run A (`tmp/validate2.json`, 1394 occurrences): 48 failures — 32 `cam_cap_bolt`
  selfIntersecting, 16 `rod_cap` invalidTopology.
- Run B (`tmp/validate3.json`, also 1394 occurrences, ~80 min later under a
  load average of ~25): 97 failures — the same 32 bolts, plus 64 `follower`
  (invalidTopology and/or selfIntersecting) and 1 `head` selfIntersecting.
- In-process, `cadgen.validity.check_occurrence_shape` on the SAME follower
  and head shapes (rest and rotated) reports no reasons, and a fixture model
  (`tmp/fix/fixtest4.py`) carrying those exact parts through the full
  pipeline validates `ok: true`.
- Either the document changed between runs with an identical part count
  (builders were rebuilding with stub modules, so possible) or the check is
  load/ordering sensitive. Needs one clean re-validate on a stable build to
  settle; logged so it is not forgotten. Not blocking.

## 9. Warm daemon worker reuses a `lib` package across different model scripts (reported by a builder; to confirm)

- Doing: a builder verified its module through a scratch model
  `tmp/turbos_model.py` (which does `sys.path.insert(0, ".../src")` and imports
  `lib.*`) while sibling agents ran other scratch models with their own `lib`
  packages through the same warm daemon.
- Symptom: the scratch build imported the WRONG `lib` (a sibling model's
  cached package) inside the warm worker; the builder had to run with
  `CADGEN_DAEMON=0` (cold, 7 m 15 s) to get a correct build.
- Suspicion: the worker keeps `sys.modules['lib']` (and `lib.*`) alive between
  jobs; two scripts whose importable packages share a top-level name collide.
  The cad-project convention makes every project's shared package `src/lib`,
  so this bites exactly the recommended layout when two projects (or a project
  and a scratch copy) build through one daemon.
- Workaround: `CADGEN_DAEMON=0`, or unique package names. Not fixed; needs a
  minimal repro (two projects with `src/lib/spec.py` exposing different
  constants, built alternately through one daemon).

## 10. `cadgen step inspect validate` on the ~2700-occurrence assembly: "cadgen-daemon: worker closed the connection", exit 1, no partial result

- Doing: validating the scratch assembly `tmp/noexh/noexh.step` (all systems
  but exhaust; 155 MB STEP) through the default warm-daemon path.
- Command: `cadgen step inspect validate tmp/noexh/noexh.step > validate.json`
- Result after ~35 min: stderr `cadgen-daemon: worker closed the connection`,
  exit 1, empty JSON. The earlier 1394-occurrence skeleton validated in ~11 min
  (78 min under load), so this is size-related: the worker died (OOM or a
  crash in the BOP self-intersection test) and the client reports only the
  broken pipe — no traceback, no per-part results up to the failure, no hint
  to retry cold. Re-running with `CADGEN_DAEMON=0` (see below) is the
  workaround; a partial report + a "worker died, run cold" hint would save an
  hour.

## 11. A read-only door (`inspect validate`) silently rebuilds a stale document; the failure then surfaces as a model import error

- Doing: `CADGEN_DAEMON=0 cadgen step inspect validate tmp/noexh/noexh.step` on
  a document that had gone stale (a palette edit).
- Result: no "document is stale, rebuilding" line — the door rebuilt the model
  on demand (documented behaviour) and died 40 s later with
  `ModuleNotFoundError: No module named 'lib'` raised inside
  `src/lib/block.py:_rail_bosses` (a builder's in-function `from lib import
  oil_system`, i.e. entry #1's rule broken again, hit through a door that the
  user did not expect to run Python at all).
- Impact/UX: a validate that turns into a 15-minute cold rebuild, and an
  import traceback with no pointer to the sys.path rule. A one-line
  "stale -> rebuilding" notice on every door and the teaching error from #1
  would make both obvious. Model side: fixed by using package-relative
  imports (`from . import oil_system`) for the lazy, circular cases.

## 12. `safe_fillet`/`fillet_all` accept a fillet that INFLATES the solid — `is_sound` cannot see it

- Doing: rounding the two cast end faces of the new intercooler lid, a single
  closed edge loop on a planar face (the lid's crowned+ribbed section, whose
  corners are already rounded in 2D). `C.fillet_all(body, 1.5, exclude=...,
  min_r=0.5)` on that loop only.
- Result: OCC returned a solid at r = 0.63 that `geo.sound()` (OCCT valid +
  BOP valid + closed shells + positive volume) PASSES, and whose bounding box
  has grown 0.74 mm past the end plane it was filleting and **4.3 mm above the
  casting's own crown** (530.0 -> 534.32). A fillet can only remove material
  from a convex edge, so the result is geometric nonsense that every gate in
  `castings.py` waves through. Reproduced in `tmp/ind_sec2.log`.
- Impact: the ladder in `safe_fillet` steps down on *soundness*, so it will
  happily settle on a smaller radius that is just as wrong. A cheap extra gate
  — reject a fillet whose bounding box grew — would catch this class for every
  caller; suggested for `castings.safe_fillet` (repo tooling, not cadgen).
- Worked around in `src/lib/induction.py` by not filleting that loop at all
  (the lid's end faces are left crisp; every other edge is rounded in 2D
  before extrusion, which is both cheaper and exact).

## Upstream status after cadgen `43ffa724` (2026-09-02)

The user reported that release/0.5.0 moved to `43ffa724` mid-build. Entries
above with an upstream fix, and what changed here in response:

- #1: fixed at the root — the pipeline now raises a teaching error naming the
  rule and the fix. Imports were already hoisted; nothing to do.
- #2: fixed — `srgb()` returns a plain channel tuple and no longer imports the
  kernel; the eager-kernel hint now names the file:line that first imported it.
- #3: fixed — `srgb()` colours were written to STEP ~2.5 stops dark and read
  back that way by `read_step` / the viewer's STEP import. The package path was
  always right. Rebuild before judging colours through any imported-STEP route.
- #4: implemented — `cadgen step snapshot STEP/w16.step out.png --animation
  <clip> --time <seconds>`, or `"animation": {"clip", "time"}` in a `--job`
  packet. Used for the animation stills below.
- #5: fixed — the op memo ran booleans in OCCT's non-destructive mode, which
  changes results for tangent geometry (the boss-on-ring rod caps). The
  `shape.fix()` workaround in `src/lib/pistons.py` is removed; re-validated
  below. #8's follower/head findings are expected to clear for the same reason.
- #7: already existed — `shape.cad_material = {roughness, metalness, clearcoat,
  clearcoatRoughness, opacity}` on a leaf rides the package occurrence
  (documented under "Finish" in `skills/cad/references/build123d-modeling.md`;
  I had searched `step-generation.md` and the snapshot docs, not the modeling
  reference). `src/lib/palette.py` now maps every palette colour to a finish.
- Memory: the user reports my full builds were killed by the OS at 100–230 GB
  overnight. The memo no longer pins every intermediate shape; root cause not
  yet proven. Rule kept: one full `src/w16.py` build at a time, per-subsystem
  entries otherwise.
- Validate: 78 min under load because all 2,546 placed occurrences are checked
  serially in one process. Unchanged; re-validate only when nothing else builds.
- #6 follow-up: the fused socket+lead-in tool still produced `selfIntersecting`
  for M6x16 socket bolts at 15 and 30 deg tilts (the 13 `coil_bolt` findings in
  the no-exhaust validate, `tmp/noexh/validate5.json`; 45 deg and upright were
  clean, which is why the earlier check passed). Reproduced in-process with
  `cadgen.validity.check_occurrence_shape` — so this one is model geometry, not
  a cadgen defect. Fixed in `src/lib/fasteners.py`: plain hex cut + a chamfer on
  the six mouth edges (stable across 5 sizes x 6 axes).

## Upstream status after cadgen `8e5fa085` (2026-09-02, evening)

- #9 and #11: fixed at the root — the memo was evicting `lib` mid-job, which is
  why lazy `from lib import ...` failed only in daemon workers. Warm builds are
  safe again (no `CADGEN_DAEMON=0` needed). Every door now prints a "stale,
  rebuilding" line before it rebuilds.
- #10 (validate on the big assembly): `inspect validate` now checks each unique
  part once across a worker pool, streams progress, and `--out PATH` leaves a
  readable partial report if killed; a dead worker says so and prints the exact
  cold rerun.
- Memory: a build now aborts with one line naming its stage once it passes half
  the machine's memory (`CADGEN_MAX_RSS_GB`), and `--verbose` stage lines carry
  peak RSS. The overnight 100–230 GB kills did not reproduce upstream on today's
  code; if one recurs, the abort line is the evidence to keep.
- Eager kernel import in this model: `src/lib/castings.py` imported `OCP.BRep`
  and friends at module scope (the hint now names the line). Moved into the
  functions that use them, so a no-op re-run stays kernel-free.

## 13. `inspect validate` flags 30 parts that pass the identical in-process check

- Doing: final validate of `STEP/w16.step` (2 545 occurrences, 769 prototypes)
  after the warm-daemon build on cadgen `8e5fa085`.
- Command: `cadgen step inspect validate STEP/w16.step --out tmp/validate_final.json`
- Result: `failureCount: 30` — 14 × `exhaust_trumpet:*`, plus `head:2`,
  `coil_bolt:4`, `water_pump_housing:2`, `tensioner_arm`, all `selfIntersecting`
  (`selfIntersectionCheck: "first-placement"`).
- In-process control: the SAME shapes, rebuilt in a plain Python process and
  checked with `cadgen.validity.check_occurrence_shape` (the function validate
  itself calls), return `[]` — clean. Probed cylinder 3's trumpet in three
  constructions (the shipped two-section shell, a ruled loft, a cleaned
  difference) and the M6 socket bolt at three tilts: all clean.
- So the geometry that reaches the document is not the geometry the model
  function produced in-process — the same class as #8, which was fixed for the
  rod caps by the non-destructive-boolean change.
- Blocked? No, the model builds and renders. Not fixed here.
- Next step for whoever picks this up: a cold (`CADGEN_DAEMON=0`) rebuild +
  validate was launched to see whether the warm daemon path is the difference;
  result in `tmp/cold_final.log` / `tmp/validate_cold.json`.
- #13 follow-up: the COLD (`CADGEN_DAEMON=0`) rebuild + validate reproduces the
  same 30 findings exactly (14 trumpets, `head:2`, `coil_bolt:4`,
  `water_pump_housing:2`, `tensioner_arm`). So it is NOT the warm daemon: the
  difference is between the shape the model function returns in-process and the
  shape that reaches the document/package. `tmp/validate_cold.json`.

## #14 — a strict top-down view of this engine can only ever show the intercooler lids

- Doing: the induction top-face pass, brief item 4 ("if the runner throats are
  not visible from above, raise or expose enough of each throat that the plan
  view shows sixteen of them").
- Finding: it is not achievable without moving a fixed part. The intercooler
  cores + end tanks occupy `|y| 18..200` continuously from `x -310` to `x 348`
  at `z 406..514`, and the cast lid roofs `|y| 12..202` above them. The sixteen
  runner throats live at `|y| 72..115, z 301..344` — under that roof for their
  whole length. So does the plenum, the fuel rail, the injectors and (on bank 2)
  the throttle body. In an orthographic plan view the ONLY induction parts with
  a clear line to the camera are the two lids, the charge pipes at `|y| 435`,
  and whatever the museum section opens up on bank 1 for `x > 121`.
- Consequence: a critic asked to judge "the top-down view" is, for `|y| < 202`,
  judging two lids and nothing else — which is exactly why the lid needed the
  articulation (grid ribs, proud bosses, relieved split line, per-bank casting
  numbers, asymmetric water hardware) rather than the throats needing raising.
- Not a defect in any module; the packaging is correct for a real W16. Recorded
  so the next agent does not spend its budget trying to expose the throats from
  directly overhead. The place they DO read is the bank-1 section face and any
  3/4 view.

## #15 — agent trap: a backgrounded build can survive a shell that looks like it failed

- Doing: launching the clearance sweep with
  `cd ... && SP=... nohup "$SP/watch.sh" python "$SP/sweep.py" > "$SP/sweep.log" &`.
- The first attempt reported `tail: /sweep.log: No such file or directory` and
  looked like it had not started. It had: the `nohup` child was running with a
  1 GB RSS while the follow-up command started a SECOND copy, so two OCCT builds
  ran concurrently for ~40 s — the exact thing `BUILDING.md`'s memory rule
  forbids, and the machine has already run out of memory once over this.
- Rule of thumb for the next agent: after backgrounding anything, confirm with
  `ps -eo pid,rss,command | grep <script>` BEFORE relaunching, and kill the
  strays. A failed `tail` says nothing about the child.

## 14. OCC segfaults (SIGSEGV, whole process, no traceback) inside `fillet_all` on a cast bracket — the "narrow face" guard does not cover it

- Doing: adding cast gussets and bolt bosses to `ancillaries.build_tensioner()`'s
  bracket, fused BEFORE the standard `soften(bracket, 4.0, min_r=0.8)` pass, the
  way the rest of the module builds a casting.
- Command: `.venv/bin/python -m lib.ancillaries` (from `models/w16/src`).
- Result: `Segmentation fault: 11`. The process dies inside the fillet pass, so
  there is no Python traceback, no partial result, and — in a pipeline run — no
  indication of which part was being built. Peak RSS at death was 0.72 GB, so it
  is not memory. The last thing on stderr is `castings.fillet_all`'s own
  `skipped 22 edge(s) on faces narrower than r=4.0 (OCC can hard-crash there)`
  line, i.e. the guard fired, excluded 22 edges, and OCC hard-crashed anyway on
  what was left.
- Workaround: fuse the ribs/bosses AFTER `soften()` (and after the block clip).
  Costs the root fillets on the new features; nothing else changes. The same
  change on the alternator bracket dropped `fillet_all`'s narrow-edge skip count
  back from 72 to 33.
- Blocked? No. Fixed? No — worked around in the model.
- For whoever picks this up: a minimal repro was NOT extracted (the failing
  shape is a 4-piece `_plate` fuse plus two thin `_rib` prisms and two drafted
  cones). Worth reducing, because a kernel call that can take the interpreter
  down with it makes any long unattended build unsafe: `fillet_all` cannot
  defend against it with a try/except, only by not filleting.

## 16. Kinematics tab reported showing an error; not reproducible on a fresh load

- Reported by the user while the viewer was open across several sidecar rewrites.
- What I checked, all clean:
  - `STEP/w16.step.json` parses, holds exactly `{animation, schemaVersion: 5}`,
    and is served over the same URL the client uses (`/__cad/asset?file=...`,
    HTTP 200, 128 786 bytes).
  - The model declares no `kinematics=`, so `loadKinematicsModuleDefinition`
    should return `null` and the tab should be ABSENT, not errored:
    `packages/cadgen-js/src/common/kinematicsModule.js:145` returns null when the
    sidecar has no `kinematics` section, and
    `PoseControlsSection` only keeps the tab when there is a definition, a
    loading status, or an error.
  - Two fresh loads (one cache-busted) show tabs `Reference, Animation, Measure,
    Display` — no Kinematics tab, no error text anywhere in the DOM, no console
    errors.
  - The sidecar write is atomic (`_internal/source_sidecar.py:149` writes a temp
    then `replace_atomic`), so a reader cannot catch a half-written file. The
    catalog's `poseUrl` carries no cache-bust token, so it cannot go stale.
- Best hypothesis: a page held open across a sidecar rewrite latched a failed
  fetch into `stepModuleLoadState.status = "error"`, and the tab then renders to
  show that error. A reload clears it. If it recurs on a FRESH load, the missing
  evidence is the error TEXT — it comes straight from the rejected promise in
  `CadWorkspace.js:1669` and would name the real cause.
- Not blocking; the model has no kinematics to show in that tab by design (its
  motion is choreography, not mates).
