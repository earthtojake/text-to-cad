# Hand project — repository bug log

Started 2026-09-06. Records repository issues and missing capabilities, not hand design errors. No acceptance gate is waived by an entry here.

## 001 — Live animation cannot deform a tendon body

- Trying to: animate a continuous swept tendon while its endpoints and pulley wraps change.
- Exact command:
  ```sh
  node --input-type=module - <<'JS'
  import * as THREE from './packages/cadgen-js/node_modules/three/build/three.module.js';
  import {createAnimationFrame} from './packages/cadgen-js/src/common/animationRuntime.js';
  const f=createAnimationFrame(THREE,{parts:[{id:'o1.1',label:'tendon'}]});
  console.log(JSON.stringify({handleMethods:Object.keys(f.model.get('tendon')),frameFields:Object.keys(f)}));
  JS
  ```
- Exact output: `{"handleMethods":["rotate","translate","opacity","visible"],"frameFields":["model","matrices","styles"]}`.
- Missing behavior: no path deformation; one rigid transform cannot preserve a full tendon running between independently moving pulleys.
- Workaround: none that meets the continuous swept-body requirement.
- Blocking: yes, final motion deliverable.
- Fixed: implemented and tested; real STEP proof bends a 60 mm straight tube into a constant-length arc. Shared JS tests and viewer tests pass; final combined-suite rerun remains required after integration. Root files changed: `packages/cadgen-js/src/common/animationRuntime.js`, `packages/cadgen-js/src/common/tubeDeformation.js` (new), `packages/cadgen-js/src/common/tubeDeformation.test.js` (new), `packages/cadgen-js/src/common/tubeBraidMaterial.js` (new), `packages/cadgen-js/src/common/cadScene.js`, `packages/cadgen-js/src/common/stepModuleEffects.js`, `packages/cadgen-js/src/lib/viewer/topologyDisplayEdgeLine.js`, `apps/viewer/src/client/components/CadViewer.js`, `packages/cadgen-js/docs/tube-deformation.md` (new), `packages/cadgen-js/README.md`, `skills/cad/references/kinematics.md`, and generated `packages/cadgen/src/cadgen/_runtime/browser/snapshot-render.js`.

## 002 — Animation lifecycle descriptions disagree after render-module migration

- Trying to: find the authoritative animation authoring contract.
- Exact command: `cat CONTRIBUTING.md packages/cadgen/README.md packages/cadgen-js/README.md apps/viewer/README.md apps/docs/README.md skills/cad/references/kinematics.md`.
- Wrong documentation: package/app README text describes animation as copied `.anim.js` text in a sidecar; `skills/cad/references/kinematics.md` and `packages/cadgen-js/src/common/renderModule.js` instead specify a live adjacent `<name>.step.js` module. The kinematics reference's imported-STEP section also still describes `--animation` copying text into a sidecar.
- Workaround: follow the implemented render-module loader and the dedicated render-module section.
- Blocking: no.
- Fixed: no. Root files changed: none.

## 003 — Validation help incorrectly promises source rebuilds

- Trying to: discover the required strict geometry validation command.
- Exact command: `./.venv/bin/python -m cadgen.cli step inspect validate --help`.
- Exact wrong output: `A stale generated document is rebuilt from its script first; that decision is announced on stderr.`
- Related help error: `./.venv/bin/python -m cadgen.cli step inspect interfere --help` gives source-script and extensionless target examples at `packages/cadgen/src/cadgen/cli/step_inspect/cli.py:204`; the actual command requires a document.
- Expected: documents-only doors inspect the supplied artifact; the model script is run explicitly, per package laws and skill instructions.
- Workaround: explicitly build model scripts before inspection; do not rely on that help sentence.
- Blocking: no.
- Fixed: no. Root files changed: none.

## Environment note — branch creation initially denied by sandbox

`git switch -c codex/anthropomorphic-tendon-hand` returned `fatal: cannot lock ref 'refs/heads/codex/anthropomorphic-tendon-hand': Unable to create '/Users/jakefitzgerald/robots/text-to-cad/.git/refs/heads/codex/anthropomorphic-tendon-hand.lock': Operation not permitted`. Repeating the same command with tool escalation succeeded. This was an environment restriction, not a repository defect; it no longer blocks work.

## 004 — Curved-surface inspection bounds overestimate exact geometry

- Trying to: check pulley and guide envelopes for assembly clearance.
- Exact commands: `./.venv/bin/python -m cadgen.cli step inspect refs models/assemblies/STEP/anthropomorphic_hand/pulley_review.step --facts --planes --positioning`; `./.venv/bin/python -m cadgen.cli step inspect refs models/assemblies/STEP/anthropomorphic_hand/transport_review.step --facts --format json`.
- Wrong output: R7 pulley reported Y bounds ±8.1179416 although exact optimal BREP bounds are ±7.5000001. Transport reported X size 38.667377 / max 19.333689; exact BREP gives size 38.0000001 / max 19.0.
- Workaround: use exact kernel optimal bounding boxes for fit and collision broad phase. Conservative reported bounds do not establish an actual clash.
- Blocking: no.
- Fixed: no; no root source changed for this issue.

- Additional cartridge evidence (2026-09-06): `cadgen step inspect refs models/assemblies/STEP/anthropomorphic_hand/tension_cartridge_review.step --facts --planes --positioning` reports the two springs at X±10 with X±18.8756161924 and Y±8.8756161924; `inspect frame` reports one spring as17.7512323mm wide. Reimporting that same STEP with `bd.import_step(...).bounding_box()` gives X±18.2000001 and Y±8.2000001, consistent with the authored R8.20 outside annulus. All48 exact spring/motor/frame placement fit checks pass using kernel geometry. No new root source change.

## 005 — Macro snapshots have no explicit exact-surface tessellation control

- Trying to: remove visible radial faceting in the dished pulley macro.
- Exact build/render commands: `CADGEN_JOBS=2 ./.venv/bin/python models/assemblies/src/anthropomorphic_hand/pulley_review.py`; `CADGEN_JOBS=2 ./.venv/bin/python -m cadgen.cli step snapshot --job models/assemblies/src/anthropomorphic_hand/pulley_render_job.json`.
- Observation: reducing decorator `mesh_tolerance` / `mesh_angular_tolerance` to .0008/.008 did not improve the STEP snapshot. The STEP snapshot's `loadPackageMeshData` used `{}` tessellation options at all sizes; decorator mesh-export settings do not control artifact-side rendering.
- Fix: added explicit JSON `render.tessellation` chord/angle options with separate shared-cache keys, positive finite validation, and refusal for already-tessellated mesh inputs. Source files changed: `packages/cadgen-js/src/common/source.js`, `packages/cadgen-js/src/common/source.test.js`, `skills/cad/references/snapshot-review.md`; browser runtime regenerated through the bundle script.
- Validation: the new real-surface test confirms more triangles at finer tolerance, separate cache entries, and a warm fine-cache hit without source fetch. Initial test harness omitted the required assembly hierarchy, then the provider's required `get` method; both corrected in `source.test.js`. Exact test command: `node --test packages/cadgen-js/src/common/source.test.js`; final result 18/18 pass.
- Blocking: no longer. Fixed: API implemented and presentation-large render visually checked at chordTolerance .0005 / angleTolerance .10; radial faceting was removed. Aggressive-quality stability is tracked separately below.

## 006 — Fine pulley snapshot loses the browser driver connection

- Trying to: render four dished pulleys at `render.tessellation={"chordTolerance":0.0001,"angleTolerance":0.025}` with presentation-large profile.
- Exact command: `CADGEN_JOBS=2 ./.venv/bin/python -m cadgen.cli step snapshot --job models/assemblies/src/anthropomorphic_hand/pulley_render_job.json`.
- Exact error: `[cadgen step snapshot] FAILED: Exception: Page.evaluate: Connection closed while reading from the driver` followed by `.venv/lib/python3.13/site-packages/playwright/_impl/_connection.py:632`.
- Second reproduction: `CADGEN_JOBS=2 ./.venv/bin/python -m cadgen.cli step snapshot --job models/assemblies/src/anthropomorphic_hand/capstan_render_job.json` returned the same driver error after 48 groove-lip fillets were added, at .0005/.10 tessellation. Retry at .001/.18 exited 0 at the same 2800×1800 image size. A compact process snapshot during the retry showed the Playwright driver at about1.7GiB RSS on a64GiB host; this is an observation, not a diagnosis.
- Cause: not established. Do not infer out-of-memory from the message alone.
- D-bore pulley reproduction: after adding the R11 wrist pulley and keyed hubs, the same `CADGEN_JOBS=2 ./.venv/bin/python -m cadgen.cli step snapshot --job models/assemblies/src/anthropomorphic_hand/pulley_render_job.json` command failed twice with the identical driver-disconnect message at .0001/.025. Geometry build and strict five-prototype validation passed. Updating that model render job to chordTolerance .001 / angleTolerance .18, preserving 2800×1800 output, exited 0 and wrote both macro views. Both were visually reviewed. No repository runtime source changed; underlying cause remains unestablished.
- Workaround: `CADGEN_JOBS=2 ./.venv/bin/python -m cadgen.cli step snapshot --job tmp/anthropomorphic_hand/pulley_medium_job.json` with chordTolerance .0005 / angleTolerance .10 exited 0. The 2800×1800 result was visually checked and has smooth pulley profiles. Blocking: no. Fixed: no; cause remains unestablished.

- Forearm-frame reproduction: `./.venv/bin/python -m cadgen.cli step snapshot --job models/assemblies/src/anthropomorphic_hand/forearm_frame_render_job.json` failed twice with the same Playwright driver-disconnect error at 2800×1800 and chordTolerance .001 / angleTolerance .12. A single default-tessellation 1800×1400 frame snapshot succeeded and was visually inspected. Further authored-theme retry uses a coarser .002/.18 mesh; no runtime code changed.

## 007 — Opposed phalanx snapshot framing clips a part

- Trying to: inspect the back of three phalanx prototypes.
- Exact command: `CADGEN_JOBS=2 ./.venv/bin/python -m cadgen.cli step snapshot --job models/assemblies/src/anthropomorphic_hand/phalanx_render_job.json`.
- Wrong output: `tmp/anthropomorphic_hand/phalanx_dorsal.png`, camera direction `[0.3,-0.2,-1]`, clips the upper distal frame despite padding .13 (specialist report; parent confirmation pending).
- Workaround: explicit camera framing and additional padding if needed.
- Blocking: no; primary three-quarter snapshot works.
- Fixed: no.

## 008 — Nonblocking production-bundle warnings

- Trying to: bundle the targeted animation/rendering fixes.
- Exact command: `scripts/bundle/bundle.sh`.
- Output: Node `[DEP0205] DeprecationWarning: module.register() is deprecated. Use module.registerHooks() instead.`; Lucide sourcemap `Can't resolve original location of error`; Vite warnings that mixed static/dynamic imports will not split modules; chunks exceed 800 kB.
- Workaround: none needed; production bundle exits 0 and `scripts/bundle/bundle.sh --check` passes.
- Blocking: no. Fixed: no; unrelated build tuning left alone.

## Environment note — normal CAD cache and process/network access

Authorized model builds initially hit `PermissionError: [Errno 1] Operation not permitted` writing temporary objects under `/Users/jakefitzgerald/.cache/cadgen/objects/`. Commands included `CADGEN_JOBS=2 ./.venv/bin/python models/assemblies/src/anthropomorphic_hand/pulley_review.py`, `transport_review.py`, `phalanx_review.py`, and the runtime fixture. Retrying the same builds with escalation succeeded; no alternate cache/store was created. Downloading the DLR reference with `curl -L --fail --max-time 40 ...` initially returned `curl: (6) Could not resolve host: www.dlr.de`; the escalated download succeeded. `ps -axo rss,comm` and `sysctl -n hw.memsize` were denied in the sandbox; escalated process inspection works. These are environment restrictions, not repository defects.

## 009 — Plain build123d STEP import exposes prototype names for reused geometry

- Trying to: map imported finger hardware back to unique authored drive-pulley labels.
- Exact command: `./.venv/bin/python -c "from build123d import import_step; a=import_step('models/assemblies/STEP/anthropomorphic_hand/middle_routing_review.step'); print([c.label for c in a.children[3:7]])"`.
- Wrong output reported by routing builder: yaw and flex pulley occurrences both receive `middle_mcp_flexion_positive_drive_pulley` / `middle_mcp_flexion_negative_drive_pulley` through the plain build123d importer.
- Workaround verified: `./.venv/bin/python -m cadgen.cli step inspect refs models/assemblies/STEP/anthropomorphic_hand/middle_routing_review.step '#middle_mcp_abduction_positive_drive_pulley' '#middle_mcp_flexion_positive_drive_pulley' --facts` resolves distinct `o1.4` and `o1.6`, with correct centers `[-12,105,8]` and `[-11.1,105,0]`. Cadgen's occurrence scene preserves both names. Use the occurrence scene or source registry for mapping.
- Blocking: no. Fixed: no. This is an importer interoperability limitation, not lost names in Cadgen's Viewer tree; no repository source changed.


- Palm follow-up: `.venv/bin/python /tmp/palm_cup_contact.py` used `bd.import_step` on `drive_terminal_placements.step` and reported a CMC pulley as `palm_cup_negative_drive_pulley`: bounding box X−42.586..−27.5, Y28.5..43.5, Z−14.25..−12.75 mm. `.venv/bin/python /tmp/palm_named_pulley_check.py`, using `cadgen.read_step` on the same STEP, confirms its correct occurrence name `thumb_cmc_abduction_negative_drive_pulley` and identical bounds. Palm hardware and motion audits now use `read_step` for occurrence ownership. No repository runtime changes.

## 010 — Kernel fillet operation crashes on a strictly valid cupping frame

- Trying to: blend the visible tube-to-bearing and tube-to-tube junctions on the fifth metacarpal frame. The unblended two-body palm STEP passed full `cadgen step inspect validate`, including self-intersection checks.
- Exact command: `PYTHONPATH=models/assemblies/src/anthropomorphic_hand .venv/bin/python -u /tmp/little_blend_trial.py`. The diagnostic calls `make_little_metacarpal()`, selects 38 adjacent B-spline junction edges, and calls `shape.fillet(.12, edges)`.
- Exact output/error: `SELECTED 38`, followed by process exit code `139` (segmentation fault), with no Python exception.
- Related attempt: the whole-palm 310-edge R0.12 fillet continued consuming CPU for more than eight minutes at roughly 638 MiB RSS and was deliberately terminated; this is a bounded performance observation, not proof of a hang.
- Workaround: six local R0.03 junction groups succeed for the fifth metacarpal, followed by cutting the keyed drive bores. `CADGEN_JOBS=2 .venv/bin/python models/assemblies/src/anthropomorphic_hand/palm_little_review.py` exits 0; `CADGEN_VALIDATE_WORKERS=2 .venv/bin/python -m cadgen.cli step inspect validate models/assemblies/STEP/anthropomorphic_hand/palm_little_review.step --out tmp/anthropomorphic_hand/palm_little_validate.json` reports `ok:true`, one solid and zero failures. Whole-palm junction geometry is still being revised; broad multi-edge fillets are avoided. The first nine-edge R0.08 attempt failed cleanly with `ValueError: Failed creating a fillet with radius of 0.08, try a smaller value or use max_fillet() to find the largest valid fillet radius`.
- Blocking: the crash is bypassed for the fifth metacarpal. Finishing the main palm still requires geometry revisions; baseline generation and collision checks work.
- Fixed: no. Root source files changed: none. This is a dependency robustness issue; no repository workaround or kernel patch has been applied.

## 011 — Wrist fillet differs between direct factory and forced build

- Trying to: verify that the wrist model's source factories reproduce the same valid geometry used by its STEP build.
- Exact successful command: `CADGEN_JOBS=2 .venv/bin/python models/assemblies/src/anthropomorphic_hand/wrist_review.py --force`; exit0, wrote `models/assemblies/STEP/anthropomorphic_hand/wrist_review.step` (10.014seconds reported).
- Exact failing command on the same then-unchanged source: `.venv/bin/python - <<'PY'` followed by `import sys`, `sys.path.insert(0,'models/assemblies/src/anthropomorphic_hand')`, `from lib.wrist import make_wrist_palm_cradle`, `s=make_wrist_palm_cradle();print(s.volume,s.is_valid)`, and closing `PY`. It exits1 at `lib/wrist.py`, `_finish`, `shape.fillet(.03,[current])`: `OCP.OCP.Standard.Standard_Failure: BRep_API: command not done`, then `ValueError: Failed creating a fillet with radius of 0.03, try a smaller value or use max_fillet() to find the largest valid fillet radius`.
- Observation only: the cause is not established; this may involve kernel operation order or build behavior. No cache or kernel diagnosis is asserted.
- Workaround: explicitly distinguish smooth swept seams from actual junctions using adjacent face normals, sort junction edges deterministically, and round keyed-eye entries after the cradle junction blends. Recheck with a fresh direct factory process as well as the normal forced build.
- Final geometry observation: fresh direct factory volumes are833.8071848201,537.8838100045,526.0683580097mm³; STEP reimport volumes are833.7983970763,537.8807964598,526.0657190848mm³. Both routes validate; the small numerical differences are not attributed to a cause.
- Blocking: temporarily blocked confidence in reproducibility. Workaround verified: fresh direct factory calls now produce three valid single solids, and the forced STEP build exits0. Fixed in repository: no. Root source files changed: none.

## 012 — Arbitrary routing JSON has no declared-input helper

- Trying to: make a STEP build depend on a numerically solved routing atlas stored beside its Python helper.
- Exact inspection command: `rg -n 'read_json|read_text|input_file|track.*file|read_step' packages/cadgen/src/cadgen/__init__.py skills/cad/references/step-generation.md`.
- Observed limitation: the public source-input helper found is `read_step`; an ordinary `Path(...).read_text()` of a JSON atlas is not a declared geometry input. No stale build was accepted, and no runtime error is asserted.
- Workaround: export the accepted atlas as a Python literal module and import it, so the documented Python dependency closure tracks it.
- Blocking: no. Fixed in repository: no; a non-CAD data-input declaration would be an additional feature, beyond this task. Root source files changed: none for this issue.

## 013 — JSON still-frame animation request needed source lookup

- Trying to: apply a static braided material clip in a JSON presentation render job.
- Exact command: `.venv/bin/python -m cadgen.cli step snapshot --job models/assemblies/src/anthropomorphic_hand/routing_layout_render_job.json`.
- Exact error from the initial job: `SnapshotError: unknown render job key(s): time; supported keys: animation, camera, debug, display, height, input, jointValues, kinematics, mode, outputs, render, scale, sceneScale, selection, sizeProfile, theme, timeoutSeconds, width`.
- Cause/workaround: the CLI examples use separate `--animation` and `--time` flags; JSON instead needs `"animation":{"clip":"presentation","time":0}`. The parser source made the nested form clear. Corrected the model's render job; no parser defect is asserted.
- Blocking: no. Fixed in repository: no. Root source files changed: none for this documentation discoverability issue.

## 014 — Full braided-tendon initialization exceeds snapshot timeout

- Trying to: render48 full routed tendon bodies with the static `presentation` material clip at2800×1800.
- Exact command: `.venv/bin/python -m cadgen.cli step snapshot --job models/assemblies/src/anthropomorphic_hand/routing_layout_render_job.json`.
- Exact error: `SnapshotError: snapshot timed out after 300s`. The same assembly, tessellation, and theme without the animation clip rendered successfully. Observed renderer memory was approximately2.7GiB, not evidence of an out-of-memory failure.
- Cause: rest-mesh projection searched every sample of every cubic segment for every vertex, repeatedly evaluating cached curve samples.
- Targeted fix: cache table positions and conservative segment bounding boxes; visit nearest bounds first and prune only when their distance lower bound exceeds the best exact candidate. A multi-turn cubic-helix regression compares the pruned result with exhaustive segment search at81 positions. All tube deformation tests pass.
- Blocking: yes, for the full moving-tendon deliverable. Fix authored; all802 shared JS and347 Viewer tests pass; bundle/freshness checks pass; the unchanged full48-tendon JSON job now exports all four2800-class presentation views successfully. Fixed: yes. Root files changed: `packages/cadgen-js/src/common/tubeDeformation.js`, `packages/cadgen-js/src/common/tubeDeformation.test.js`, regenerated runtime outputs.
- Subsequent sandbox-only launch failed with Chromium `bootstrap_check_in ... Permission denied (1100)`/SIGTRAP; rerunning the identical render with approved execution outside the sandbox launched successfully. This is an execution restriction, not an attributed CAD repository defect.

- Full follow-up render with900second timeout reached a concrete allocation failure: `Page.evaluate: RangeError: Array buffer allocation failed`, at `new Float64Array`, runtime `j1 ... snapshot-render.js:4142:9979`. The initial2.7GiB observation does not describe this later run. Value-keyed path caching, unchanged-pose reuse, and deferred hidden edges now pass focused tests but have not resolved the full assembly. Root file additionally changed: `packages/cadgen-js/src/common/cadScene.js`. Investigating actual imported buffer sizes before further changes.
- Follow-up diagnosis: the render surface carries triangle-local edge attributes, so the first real tendon has472869 source vertices, although its indexed CAD tessellation has82293. Refined surface mapping duplicated64bytes per repeated corner. The targeted mapping now shares exact position/normal records (185338 records for682571 refined display vertices), and shares immutable index/display buffers between rest and posed surfaces. Actual-tendon initialization measured18.97s with about77.6MB retained array buffers in a standalone run.32 focused runtime/scene tests pass; full-scene verification remains pending.
- Static presentation verification now passes: the same four-output2800×1800 JSON render command exits0 and saves palm, dorsal, whole, and joint-macro images with braided materials. A material-only clip explicitly requests no longitudinal resplitting (`maxSegmentLength:1000000`) because its rest and posed paths are identical; native CAD triangles and full tendon solids are retained. Moving-curve initialization and frame performance remain a separate unresolved requirement. Additional targeted fixes cache identical source-position projections and skip an unnecessary resplitting pass when the authored maximum segment length exceeds the whole path.33 focused tests pass.

- Moving-tube benchmark on the actual index tendon (805305 refined display vertices) took1.461s per changed frame on the CPU, which blocks usable full-hand motion. An internal GPU display backend is now authored: immutable rest-coordinate lookup plus transported frame textures, conservative displayed bounds, and on-demand exact CPU materialization before ray casting. The same benchmark now measures21.2ms including path normalization; renderer verification and broader tests are pending. Added root file `packages/cadgen-js/src/common/tubeGpuDeformation.js`; updated `packages/cadgen-js/src/lib/viewer/raycastBvh.js` to invoke the deformation's conservative pick precheck and CPU materialization. This is a rendering approximation of the same analytic paths, never collision validation.
- Follow-up verification: the native STEP fixture renders successfully through the GPU path at bend0.75, with its braid and endpoint visible. Dense line, R3.5 arc and spatial-cubic frame checks stay below0.001mm display error; exact CPU picking agrees vertex-for-vertex and late highlight materials receive the same deformation. All801 shared-runtime tests and347 Viewer client tests pass. Full-hand display performance remains to be verified with the final assembly.

## 015 — Full assembly GLB export exceeds a JavaScript Map limit

- Trying to: export the current routed assembly for a native mesh memory benchmark.
- Exact command: `.venv/bin/python -m cadgen.cli glb build models/assemblies/STEP/anthropomorphic_hand/routing_layout_review.step models/assemblies/GLB/anthropomorphic_hand/routing_layout_review.glb --mesh-tolerance .001 --mesh-angular-tolerance .18`.
- Exact error: `[cadgen glb build] FAILED: RuntimeError: mesh export failed for glb: Map maximum size exceeded`, raised in `packages/cadgen/src/cadgen/_internal/mesh_export.py:98`.
- Workaround: benchmark the actual cached component tessellations directly; the native STEP assembly loads in CAD Viewer and its presentation snapshots succeed. No GLB output is accepted.
- Blocking: no, since the requested deliverable is the STEP assembly with live Viewer parameters. Fixed: no. Root files changed: none for this issue.

## 016 — Rational ellipsoid parameter seam appears in solid snapshot

- Trying to: render smooth silicone ellipsoid fingertips with topology edges disabled.
- Exact command: `.venv/bin/python -m cadgen.cli step snapshot --job models/assemblies/src/anthropomorphic_hand/fingertip_pad_render_job.json`.
- Observed result: command exits 0, but an unrotated nonuniformly scaled `bd.Sphere(1)` shows a thin dark meridian from the top pole to the rim even with `display.edges.enabled=false`; strict `--every-placement` validation reports zero failures.
- Workaround: orient the sphere's parameter seam into the lower hemisphere before its exact affine ellipsoid transform. The outer ellipsoid geometry and contact dimensions remain identical; the reviewed palmar snapshot is clean. No runtime files changed. Underlying seam rendering cause remains unconfirmed.
- Follow-up: the opposite underside view also shows black/white speckling at the pad/carrier planar bond patch. A 2.5% carrier-footprint inset leaves the palmar contact surface untouched and recesses the hard tactile edge, but does not eliminate the underside speckling. All35 final placements pass strict validation; this remaining contact-patch display artifact is reported for whole-assembly render review rather than hidden with changed contact geometry.

- Palm follow-up: `.venv/bin/python -m cadgen.cli step snapshot models/assemblies/STEP/anthropomorphic_hand/palm_frame_candidate_review.step --job models/assemblies/src/anthropomorphic_hand/palm_pad_face_render_job.json` exits0 but shows black/white triangular speckling on the radial pad-seat top in rendered mode. `palm_accepted_strict.json` reports one solid and zero every-placement failures. `.venv/bin/python models/assemblies/validation/anthropomorphic_hand/inspect_palm_pad_face.py` finds one planar top face at Z12.6, two boundary wires, area14.60455mm²; no overlapping top-face pair exists. Its relationship to the preceding planar contact-patch artifact remains unconfirmed. No renderer code or contact geometry was changed for this observation.

## 017 — Daemon status busy-worker summary disagrees with worker rows

- Trying to: diagnose the large hand Viewer's refresh while bounding CAD concurrency.
- Exact command: `.venv/bin/python -m cadgen.cli daemon status` (escalated to access the shared daemon socket).
- Observed output: `workers 5 bound (5 busy), 2 spare`, then three bound worker rows marked `idle` and two marked `busy`; the same response says `jobs running 2/10`. The meaning of the summary's `busy` count is unclear and differs from the individual status labels.
- Workaround: use the individual job/worker rows and the running-job count. Blocking: no. Fixed: no. Root files changed: none for this issue.
- Environment note: the identical non-escalated command printed `No CAD daemon is running`, while the escalated response found PID1142 already up38m39s. Shared-socket visibility is restricted by this session's sandbox; no duplicate daemon was launched.

## 018 — Full2963-body presentation render loses Playwright driver connection

- Trying to: render the rebuilt hand with its112guide-mount bodies and336tendon-terminal bodies in the authored solid studio theme, four macro-resolution views.
- Exact command: `.venv/bin/python -m cadgen.cli step snapshot --job models/assemblies/src/anthropomorphic_hand/integrated_render_job.json` (escalated).
- Exact error: `[cadgen step snapshot] FAILED: Exception: Page.evaluate: Connection closed while reading from the driver`, raised in `.venv/lib/python3.13/site-packages/playwright/_impl/_connection.py:632`.
- The native build exited0; the active Viewer's artifact endpoint reports `state: rendered`, and its completed assembly record contains2963occurrences/690components. No completed PNG was produced by this attempt. System-wide memory was59%free when the failure was observed; this does not establish the driver's peak allocation or cause.
- Workaround: pending diagnosis/retry with verbose output. Blocking: yes for current integrated beauty comparisons. Fixed: no. Root files changed: none for this issue so far.

- Related housing-context reproduction: `.venv/bin/python -m cadgen.cli step snapshot --job models/assemblies/validation/anthropomorphic_hand/forearm_housing_context_render_job_driver_failure.json --json` failed after roughly five minutes with `Page.evaluate: Target page, context or browser has been closed`. The full native forearm context had completed successfully before this render. Exact returned browser log is preserved in `forearm_housing_context_snapshot_driver_failure.json`; final standard-theme retry is separate. This is a renderer failure; no geometry was altered to conceal it.

- Follow-up diagnosis for018: the same JSON job fails with `NODE_OPTIONS=--max-old-space-size=12288`, so a larger driver heap does not resolve it. The diagnostic wrapper `NODE_OPTIONS=--max-old-space-size=12288 .venv/bin/python models/assemblies/validation/anthropomorphic_hand/diagnose_integrated_render.py` captures `Error: Cannot create a string longer than 0x1fffffe8 characters` / `ERR_STRING_TOO_LONG` in Playwright's `PipeTransport2._dispatch`, before the connection error. A real loopback asset server was active at the time. The exact oversized transfer is still under investigation.
- Targeted fix authored: the shared HTTP mesh-cache provider skips optional browser uploads above32MiB while preserving the full in-memory mesh and unrestricted large cache reads/native filesystem writes. The diagnostic render now passes the previously fatal92,616,420-byte palm upload by skipping that cache write; final full-render verification remains pending. Root files changed: `packages/cadgen-js/src/lib/surf/tessellationCache.js`, its test, and `packages/cadgen-js/README.md`; generated runtimes and freshness check pass. All802 shared-runtime and347 Viewer tests pass. Final verification: the normal full-hand JSON render job produces all four presentation images, and Viewer3250 loads2963bodies. Fixed: yes; no remaining block from018.

- Resource-bound follow-up: `.venv/bin/python -m cadgen.cli step snapshot --job models/assemblies/src/anthropomorphic_hand/palm_hardware_render_job.json` failed with `TimeoutError: BrowserType.launch: Timeout 15000ms exceeded` before rendering the18-body context. At10:35UTC, `sysctl vm.swapusage` reported42.0GB swap used and `vm_stat` about60MB free pages; the foreground Codex renderer used621% CPU. This is a launch-time/environment observation, distinct from the oversized transport issue above. No shared process was stopped. Retrying the unchanged JSON job succeeded and exported all four presentation/macro views.

## 019 — Snapshot failure suggests an unsupported verbose flag


- Trying to: follow the diagnostic hint printed by the failed full-hand snapshot.
- Exact command: `NODE_OPTIONS=--max-old-space-size=12288 .venv/bin/python -m cadgen.cli step snapshot --job models/assemblies/src/anthropomorphic_hand/integrated_render_job.json --verbose`.
- Exact error: `cadgen step snapshot: error: unrecognized arguments: --verbose`. The preceding failure explicitly printed `re-run with --verbose for the full traceback`.
- Workaround: inspect the saved error and retry the supported JSON job without that flag; use supported debug instrumentation only when necessary. Blocking: no. Fixed: no. Root files changed: none for this issue.

## 020 — Full assembly tube display exceeds browser buffer allocation

- Trying to: render all48 native tendon bodies with braided surface presentation at the specified largest profile.
- Exact command: `NODE_OPTIONS=--max-old-space-size=12288 .venv/bin/python models/assemblies/validation/anthropomorphic_hand/diagnose_integrated_render.py`.
- Exact error: `Page.evaluate: RangeError: Array buffer allocation failed`, at `new Float32Array` in `applyGpuTube`, snapshot-render.js4173:795, after the cache-transport guard passed the previous failure.
- Initial workaround: static2963-body assembly loads without activating braid deformation. The compact-mapping fix below subsequently resolves the full braided snapshot failure.
- Initially blocking full braided snapshots and animation; now resolved for the full48-tendon snapshot. Fix: share a compact GPU mapping texture/index buffer, derive braid coordinates in the shader, and reconstruct double-precision CPU mapping on demand for picking. The18 focused deformation tests pass, including exact CPU/GPU picking parity; all802 shared JS and347 Viewer tests pass; bundle/freshness checks pass; the unchanged full48-tendon JSON job now exports all four2800-class presentation views successfully. Fixed: yes. Root files changed: `packages/cadgen-js/src/common/tubeDeformation.js`, `tubeGpuDeformation.js`, and `tubeGpuDeformation.test.js`.

## 021 — Guide STEP import and strict inspection disagree on native solids

- Trying to: strictly validate all44 newly modeled fifth-ray guide support bodies after native source validity checks.
- Exact command: `.venv/bin/python -m cadgen.cli step inspect validate models/assemblies/STEP/anthropomorphic_hand/cup_guide_mounts_review.step --every-placement --out models/assemblies/validation/anthropomorphic_hand/cup_guide_validate.json`.
- Exact result: `little_cup_child_bank_structural_2` reports `invalidTopology`, volume57.25436482590134; `little_cup_fixed_bank_-1_structural_1` reports `nonPositiveVolume`, volume−1.3386327070827524. Copying the identical STEP to `cup_guide_mounts_frozen.step` and inspecting that reproduces both findings.
- Independent import evidence: `cadgen.read_step` of the same STEP returns these individually named bodies with `is_valid=True`, exact `BRepGProp.VolumeProperties_s` signed volumes57.26895649661562 and13.818745742266223, respectively. `BRepAlgoAPI_Check` reports valid for the child support. The source factory also checks valid, single, positive-volume solids; explicit `ShapeFix_Solid` does not resolve the inspection disagreement.
- Workaround: redesign the converging support branches while repairing separate clearance findings. The revised41-body and40-body guide artifacts both pass strict every-placement inspection. The original failing artifact was not accepted or integrated.
- Blocking: no for the revised model. Runtime discrepancy fixed: no. Runtime files changed: none.

## 022 — Solid display ignores the edge enabled flag

- Trying to: present native hardware in solid display without technical seam overlays.
- Exact command: `.venv/bin/python -m cadgen.cli step snapshot --job models/assemblies/src/anthropomorphic_hand/integrated_render_job.json`.
- Unexpected output: the job has `display.edges.enabled=false`, but native seam and tangent lines remain visible. Source inspection confirms `displayModeForcesEdges(solid)` intentionally forces them on and `displayModeShowsEdges` ignores its edgeSettings argument.
- Workaround: preserve the user-requested solid mode and author zero-opacity/zero-thickness edge classes under the JSON render job’s `display.edges` field. The theme settings object does not accept an `edges` key. This changes only technical overlays; native surfaces and geometry checks remain unchanged.
- Blocking: no once routed around. Fixed: no runtime change; behavior is intentional but the ineffective flag was unclear. Root files changed: none.

## 023 — OCCT near-coincident reverse subtraction fails volume conservation

- **Trying to do:** Certify that removal of one redundant structural arch from the little intermediate phalanx adds no material, while retaining all joint and tendon geometry. This is an upstream geometry-kernel behavior encountered through the repository's `cadgen.build123d` surface; no repository defect has yet been isolated.
- **Exact commands:** `./.venv/bin/python models/assemblies/validation/anthropomorphic_hand/check_phalanx_beauty_subset.py` and `./.venv/bin/python models/assemblies/validation/anthropomorphic_hand/probe_little_middle_subset.py`.
- **Wrong output:** The baseline volume is `367.55715625368435 mm³`; the refined, strictly valid native STEP volume is `360.77479153353227 mm³`, a difference of `6.7823647201520885 mm³`. build123d's cleaned `old-new` returns `403.138630721881 mm³`. A separate raw `BRepAlgoAPI_Cut(old,new)` reports `IsDone=True`, `BRepCheck_Analyzer.IsValid=True`, and `400.60768722106883 mm³`. Both reverse-cut volumes exceed the original body volume. The forward raw `new-old` reports `0.0 mm³`. Native `cadgen step inspect validate .../phalanx_beauty_native/little_middle_frame.step --every-placement` reports one occurrence and zero failures.
- **Workaround:** Do not accept the reverse-cut value as a certificate. A raw common-volume cross-check is being tested; otherwise retain the already accepted original body for this variant. The anomalous values remain in the diagnostic logs rather than being silently replaced.
- **Blocked:** Blocks acceptance of this refinement's subset certificate until an independent sound proof or original-geometry fallback is complete; the accepted hand mechanism is unaffected.
- **Fixed:** No. No repository root source file changed for this issue.

### 023 follow-up — direct checks replace the rejected inheritance proof

The reverse-cut certificate was not accepted. The final refinement retains four reduced-arch phalanges and restores the other11 actual phalanges directly from the frozen native assembly. All15 placed native bodies passed strict inspection with zero failures. Rather than inherit collision results through a suspect near-coincident Boolean, the workflow now reruns the complete225-pose phalanx collision gate and all48 full tendon paths against the four changed native bodies. Root integration separately checks those four bodies against all other hardware. Diagnostic raw/adaptive/fuzzy experiments are retained under `models/assemblies/validation/anthropomorphic_hand/probe_*phalanx.py` and `tmp/anthropomorphic_hand/*adaptive*.log`; none of their failed results is a pass certificate. No kernel or repository code was changed.

## 024 — Native STEP reassembly drops occurrence PBR metadata

- Trying to: rebuild a full contextual presentation from the accepted native STEP without regenerating thousands of parts.
- Exact command: `./.venv/bin/python models/assemblies/src/anthropomorphic_hand/phalanx_beauty_context.py`, followed by `./.venv/bin/python -m cadgen.cli step snapshot --job models/assemblies/src/anthropomorphic_hand/phalanx_beauty_render_job.json --json`.
- Unexpected output: imported off-white silicone pads render metallic. `read_step` leaf objects have no `cad_material`, although the source artifact's stored occurrence `middle_fingertip_silicone_pad` has `{clearcoat:0.04, metalness:0.01, roughness:0.67}`. Some leaf-level colors are also absent on imported wrappers. STEP's normal material limitations are understood; automatic reuse of the already known presentation metadata is missing from this import workflow.
- Workaround: archive the exact source tree's occurrence colors/materials by name into `integration_native_base_appearance.json`, restore them on reassembled native leaves, and preserve geometry hashes independently. New subsystem appearances are archived by their native STEP hashes too.
- Blocking: blocked acceptance of those presentation comparisons until corrected. Fixed: no runtime change; model-side restoration is in place. Root runtime files changed: none.

## 025 — Identical native STEP leaf occurrences inherit the last prototype label

- Trying to: export four independently named, geometrically identical positive MCP bushings at their assembled positions, then map those native bodies back to frame metadata.
- Exact commands: `./.venv/bin/python models/assemblies/src/anthropomorphic_hand/positive_yaw_bushing_review.py`; `./.venv/bin/python models/assemblies/validation/anthropomorphic_hand/check_positive_yaw_hardware.py`.
- Exact wrong output/error: all four imported top-level children had label `little_mcp_abduction_positive_bushing`; the metadata lookup raised `KeyError: 'index_mcp_abduction_positive_bushing'`. The four placements were distinct and correct, but their direct leaf labels were not preserved through prototype deduplication/native STEP export-import.
- Workaround: author an explicitly named one-child `Compound` occurrence for each bushing. Reimport then returned the four intended top-level labels, with one watertight solid in each wrapper. Strict every-placement inspection passed all four occurrences.
- Blocking: temporarily blocked the native route-check lookup; worked around. Fixed: no runtime change. Root runtime files changed: none.

## 026 — Corrected-Frenet evaluation stalls on a trimmed near-straight Bezier

- Trying to: sweep circular clearance cutters along the unchanged full-pose tendon curves, trimmed to their local palm contact region.
- Exact command: `./.venv/bin/python models/assemblies/src/anthropomorphic_hand/palm_main_full_rom_review.py`, with `bd.sweep(section,path=wire,is_frenet=False)` in `lib/palm_full_rom_relief.py`. The analogous little-frame build also stalled; the main worker stopped advancing after `TOOL main 42 index_dip_positive_mcp_reaction 70`.
- Observed evidence: `sample 95148 1 -file /tmp/palm_full_worker_sample.txt` placed all 757 main-thread samples in `GeomFill_CorrectedFrenet::GetAngleAT(double) const`; the operation remained there for several minutes. Earlier untrimmed joined sweeps returned `Standard_Failure: BRepOffsetAPI_MakePipeShell::MakeSolid`.
- Workaround: trim individual Bezier edges to the contact vicinity and use `is_frenet=True` for the circular profile, whose swept solid is independent of section twist. The little full-pose frame then generated successfully in 43.866 seconds. Native strict and clearance checks are still required for each resulting artifact.
- Blocking: delayed the palm repair until the kernel stall was identified. No repository runtime changes; only model-side circular cutter construction changed.

### 023 follow-up — overlapping fifth-ray cutters returned a null shape

- Exact command: `./.venv/bin/python models/assemblies/src/anthropomorphic_hand/ring_palm_guide_mounts.py`, with `body.cut(*tools)` for four transformed, substantially coincident fifth-ray hosts in `lib/palm_guide_mounts.py`.
- Exact failure: `ValueError: Null TopoDS_Shape object` at line129 after61.344 seconds. The separately measured native common at cup0/10/20/25 was only0.001150128 mm³ with identical bounds.
- Workaround: cut one small rectangular machining relief around those exact native common bounds, with0.020 mm added clearance. The model then built successfully; independent native host, moving-hardware, tendon and strict checks are required before acceptance. No repository runtime changes.

### 026 follow-up — circular Frenet workaround validated

Both resulting final palm solids passed strict every-placement inspection with zero failures (`palm_main_final_rom_strict.json`, `palm_little_comb_rom_strict.json`). The exact final files also passed all225 authored static tendon packets and native moving-comb intersection checks. No runtime or kernel changes were made.

## 027 — Same-domain Boolean cleanup grows to a 49 GB footprint

- Trying to: subtract a detailed curved phalanx rail from small mating guide saddles, preserving exact curved contact faces.
- Exact command: `./.venv/bin/python models/assemblies/src/anthropomorphic_hand/phalanx_continuous_supports_r5.py --json`. The first whole-host attempt and a second attempt using bounded local host patches both stalled in post-Boolean cleanup.
- Exact observed behavior: `sample 73680 1 1 -file tmp/anthropomorphic_hand/support_r5_sample.txt` reported `Physical footprint: 49.0G` and `Physical footprint (peak): 49.0G`; main-thread samples were inside `ShapeUpgrade_UnifySameDomain::IntUnifyFaces` reached from Python `slot_nb_subtract`. RSS alone had misleadingly fallen to about3 GB while the compressed footprint grew. The targeted worker was stopped.
- Workaround being tested: wrap only this candidate model's geometry construction in `bd.SkipClean()` so native OCCT Boolean results bypass the runaway optional same-domain simplification. Strict watertightness/self-intersection, native mutual collision and tendon checks remain required and unchanged.
- Blocking: yes, blocked the guide support build. Fixed: no runtime fix; candidate workaround validation pending. Root runtime files changed: none.

## 028 — Cached read_step geometry and native STEP reconstruction disagree in a local Boolean

- Trying to: derive the exact positive rail contact section for a fixed tendon-guide clamp from the strictly valid continuous-waist phalanx.
- Exact command: `./.venv/bin/python models/assemblies/validation/anthropomorphic_hand/probe_native_rail_clip_r5.py`.
- Exact wrong output: on `phalanx_continuous_r5.step`, `read_step` reported `contains_positive_rail: True` but the raw `BRepAlgoAPI_Common` returned `common_solids: 0` and an all-zero bounding box. Reading the identical STEP path with `bd.import_step` reported the same inside classification and `common_solids: 1`, with bounds `7.549999899999999 <= x <= 9.000000100000003`, `37.98999989999998 <= y <= 38.01000010000004`, `1.9238964048198715 <= z <= 4.087345823870731`. The native part had already passed strict every-placement inspection. Exact output is saved in `tmp/anthropomorphic_hand/native_rail_clip_r5_probe.log`.
- Consequence: an unchecked empty section supplied a zero clamp center, leading to invalid guide jaws and the runaway optional cleanup recorded in BUG027. Explicit non-empty section assertions now reject this before downstream geometry is built.
- Workaround being tested: register the native input through `read_step`, then reconstruct that actual STEP with `bd.import_step` for contact construction; run copied-input serial contact Booleans and preserve all strict and native clearance checks. No cached geometry is accepted as a substitute for this native reconstruction in the candidate support factory.
- Blocking: yes, blocked the matching guide supports. Fixed: no runtime fix; workaround validation pending. Root runtime files changed: none.

### 027/028 follow-up — native guide supports validated

The native reconstruction and copied-input contact Boolean workaround completed
before the login handoff. `phalanx_continuous_supports_r5_strict.json` reports
32 occurrences, every-placement self-intersection checks, and zero failures.
`phalanx_continuous_r5_neutral.json` reports a passing 33-body mutual and neutral
tendon check. The resumed presentation job produced and visually reviewed the
palm and joint macro PNGs. These are local candidate checks; they do not accept
the full hand or its motion range.

## 029 — Solid containment reports a tendon endpoint outside the solid's bounds as inside

- Trying to: reproduce the only reported tendon clash in the complete 225-pose
  static audit: `thumb_ip_negative_cmc_reaction` against
  `palm_metacarpal_truss`, at `thumb_cmc_abduction=45`.
- Reproduction: `./.venv/bin/python models/assemblies/validation/anthropomorphic_hand/check_native_reported_contacts.py`.
  Exact STEP SHA256: `6c2e669df4f176c530c5b1c8623c861b942ca60d1e75cb346bd2548f6a32adf4`.
- Observed: `read_step` and the native occurrence-scene path both report zero
  curve/solid distance. The endpoint `(-47.25,30.6,0)` is classified inside even
  though the solid's exact minimum X is `-39.7500001`. A fresh build123d STEP
  import reports 2.260954546373 mm for the same whole wire. The failure therefore
  is not established as a cache-only defect; root cause remains unassigned.
- Independent proof: the connected wire is 2.260954546373 mm from the compound
  of all boundary faces and has a vertex outside the solid's bounding box.
  It cannot enter the solid without crossing those faces. Its 0.45 mm outer
  envelope has a conservative 1.810953546373 mm surface gap.
- Workaround: the hand's validator now checks this boundary/outside-vertex
  proof when an ordinary distance result reports containment. It preserves
  actual intersections and logs the proof. Six targeted cases cover a clear
  path, envelope overlap, crossing, inside start, contained path, and tangency;
  all pass. No collision tolerance was increased and no palm material removed.
- Files: `models/assemblies/validation/anthropomorphic_hand/path_solid_clearance.py`,
  `check_path_solid_clearance.py`, `check_full_route_bodies.py`, and the native
  diagnostic. No repository runtime implementation changed for this issue.

## 030 — STEP reload selects the opposite cap of a rotated rational ellipsoid

- Trying to: validate the delivered fingertip pad solids rather than their
  in-memory build records. The original sphere had been rotated 90 degrees
  before anisotropic conversion to move its surface seam out of sight.
- Reproduction: export the trimmed upper thumb pad alone with
  `export_build123d_step_file`, then load it through `load_step_scene`.
  `tmp/anthropomorphic_hand/isolate_pad_export.log` records a source upper pad
  at Z=4.15..7.4 mm becoming a lower cap at Z=3.4..4.15 mm. The native thumb
  pad's reported volume falls from about359 to36.529 mm³. Exporting only the
  pad, before constructing its bridge, reproduces this; it is not an assembly
  label mix-up or a later Boolean mutation. The five original pads are affected.
- Repair: preserve the sphere's polar axis, create the required latitude
  interval before anisotropic conversion, and use the same construction for
  the lower carrier cap. Contact radii, center, bond plane and screw datums
  remain unchanged. This is a model construction repair; no runtime change.
- Evidence: `fingertip_pad_export_roundtrip.json` passes all30 actual native
  bodies as valid single closed solids. All five pads match their analytic
  ellipsoid-cap volume and Z limits, all five bond planes contact without
  overlap, and the solved native precision pinch passes the existing limits.
  One ring carrier's source/native mass integration differs although both
  directed Boolean differences are empty; that explicit equality proof is
  retained instead of relaxing the volume comparison threshold.
- Scope: this repairs the exported pad systems only. Their complete hand
  clearance and the final assembled export still require new checks. The
  prior cached-geometry pad certificate does not certify the original STEP.

### 030 follow-up — dorsal nail screw reliefs also invert after export

The five original dorsal nail ellipsoids use the same rotated rational sphere.
Replacing that sphere with one unsplit polar surface is insufficient: the tiny
cylindrical screw cuts can still reload as cap fragments. A two-meridian sphere,
followed by the original scaling and cuts with same-domain cleanup suppressed,
preserves the intended shell. The unchanged phalanx host is built with ordinary
cleanup before this local construction context.

`fingernail_export_roundtrip.json` passes all30 native bodies, source/native
geometry comparisons, five nail envelopes and75 local rigid pairs.
`fingernail_export_repair_strict.json` independently passes all30 occurrences
with self-intersection checks at every placement. This local export acceptance
does not replace complete hand clearance checks.

## 031 — A one-solid compound can hide containment from an OCCT distance query

`BRepExtrema_DistShapeShape` reports a positive boundary distance for nested
boxes supplied as one-solid compounds, while the contained solid pair reports
zero and `InnerSolution`. A positive compound distance is therefore insufficient
to bypass an interference Boolean. The native rigid validator extracts the
actual solid before its distance query and limits that shortcut to simple
analytic surfaces; all other candidates retain the exact Boolean check.
`rigid_separation_filter_check.json` passes seven synthetic separation/contact/
containment cases and29 known native contact cases. The final-fist tendon
validator likewise passes individual solids to its distance queries. This is a
validator correction, not a collision-tolerance change.

## 032 — Full-hand scene construction exhausts memory by copying mesh attributes

The3257-occurrence hand fails presentation snapshots with `RangeError: Array
buffer allocation failed`, first while copying normals and then while slicing
surface-edge attributes. Changing relative chord tolerance from0.001 to0.003 does not
resolve it. These normal, barycentric and edge-class buffers are immutable
component data already held by the scene; copying them for display wastes
memory. `cadScene.js` now shares their typed-array storage. Deformation still
acquires private position/normal attributes before writing them.

The regression test exercises both buffer sharing and deformation isolation.
All803 shared-JS and347 viewer tests pass; production bundling and freshness
checks pass. The same full-hand job then completes both presentation macros,
saved as `export_repair_pad_macro.png` and `export_repair_cmc_macro.png` under
`tmp/anthropomorphic_hand/`; both were visually inspected. This fixes rendering
capacity and does not confer mechanical or blind aesthetic acceptance.

### 030 follow-up — lower fingertip carriers fail strict self-intersection checks

The complete native hand exposed five conformal fingertip bridges that passed
ordinary topology/closure checks but failed the strict self-intersection gate.
Building the complete two-meridian ellipsoid before cutting its bond plane
repairs all five native occurrences. Both directed surface differences are
empty, all60 mounting pairs clear, and all five pad bonds touch. The evidence is
`fingertip_bridge_local_acceptance.json`; the repaired bridges still await final
integration. This does not weaken the strict gate or alter cap dimensions.

## 033 — Composed mesh copies and a large socket write block native hand snapshots

The3257-occurrence native hand's warmed mesh batch exceeds2GB. Sending it in
one macOS socket write fails with `OSError: [Errno22] Invalid argument`. The
browser then also fails while allocating combined component indices in
`buildComposedPackageMeshData`. Those aggregate arrays duplicate geometry
already referenced by each occurrence's `sourceMesh`.

The snapshot server now sends bounded16MiB chunks. Multicomponent assemblies
retain geometry in their existing component buffers; single-component arrays
are aliased. Viewer geometry gating and memory accounting recognize component
buffers, and section snapshots traverse each occurrence at its placement.
Tests cover buffer reuse, transformed section/list rendering and chunked writes.

All806 shared-JS tests,347 Viewer tests and5 snapshot transport tests pass.
Production bundling, bundle freshness and the shipping contract pass. The same
native six-view presentation job now completes, and every PNG was inspected.
`component_buffer_render_evidence.json` binds source, native model and image
hashes. Rendering success does not accept the hand's pending mechanical or
blind aesthetic gates.

## 034 — Periodic NURBS extension knots shift valid faces out of place

The native radial guide bank renders a floating sliver that is absent from an
independent OCCT mesh of the same STEP. Face108 evaluates up to1.2303mm away
from the exact native surface at identical UV parameters. An independent spline
evaluator reproduces the displacement, identifying exported data as the cause.

`SetUNotPeriodic()` preserves extension knots outside the active domain. The
exporter treated the first stored knot as the domain start and shifted the
surface by one unwanted period. Its coverage guard likewise admitted the face
using extension knots. Extraction now uses `Bounds()` for period translation
and domain fitting; the guard uses the active flat-knot interval indexed by
degree and pole count. Surface geometry and trim parameters stay in one frame.

All25 targeted surface tests pass, including a small swept-tube regression
and an explicit rejection of a window outside the active domain. Corrected
surface assets and their derived mesh cache must be regenerated for components
built before the fix. Native solid geometry and collision thresholds do not
change. The isolated visual retry is clean: the floating sliver is gone. All1926
native-versus-rendered surface samples agree within0.000001mm. The complete
native assembly retains its separate pending acceptance gates.

## 035 — Native Boolean subtraction fails an identical ferrule control

Status: unresolved kernel diagnostic; no collision or validity threshold was
relaxed. The R13 export-equivalence audit is not passing.

For `index_dip_negative_drive_terminal_ferrule`, subtracting two deep copies of
the same native solid returns the complete ten-face body (0.3559933535 mm³).
Subtracting the identical underlying TShape directly returns empty. The source
and final-export bodies both pass strict native validity; the dedicated Boolean
argument checker reports no defect. Additional fuzzy tolerance, non-destructive
mode and the CellsBuilder alternative did not resolve the identity failure.

The reproducible source is `integration_native_base.step` at SHA-256
`3bd64acfbde15af5a2b434387fd74a454d63052f9a5d26482414de7a64c1b03b`, with
diagnostic native BREP files under `models/assemblies/BREP/anthropomorphic_hand/`.
`native_r13_export_single_solid_probe.json` records the native results.

Direct native boundary records agree for 71 of the 72 reported Boolean
mismatches after integer-period trim-coordinate alignment. Controls reject a
0.00000001 mm translation and a 0.01 degree rotation. This scalar-data check
is diagnostic, not a global geometric error bound or an accepted Boolean gate.
The remaining wrist fork has identical supporting surfaces and 190 spatial
edges, but the export removes a degenerate edge and rewrites seven trim curves.
A fresh 225-pose check of the actual final-export fork is separate from any
source/export equality claim. Preserve the failed Boolean evidence.

## 036 — R13 live preview allocates gigabytes before first display

Status: unresolved; the user reports that the preview crashed Chrome. Do not
reopen the full hand in the user's browser as a diagnostic. Port 3253, the
server behind the supplied link, was stopped; the instance registry then
reported no active Viewers.

Read-only accounting of all 866 current default-tessellation cache headers
finds 19,341,464 unique-component triangles. `buildMeshDataFromSurf` expands
each triangle into three vertices with positions, normals, float barycentrics,
byte edge classes and sequential indices: 129 bytes per triangle, or exactly
2,495,048,856 bytes for those CPU arrays alone. Topology, JavaScript objects,
worker intermediates and GPU buffers are additional. The cache itself is
818,492,440 bytes. The hash-bound report is
`models/assemblies/validation/anthropomorphic_hand/native_r13_viewer_memory_accounting.json`.

`useCadAssets.loadMeshForEntry` loads every component before publishing the
scene. This path has no aggregate render-memory budget. Its adaptive detail
controller is attached only after the initial meshes load, so it cannot protect
that first allocation. Earlier observation found a blank/unresponsive page
and Chrome reporting up to 4.0 GB for the tab. Memory exhaustion is consistent
with these facts; no crash dump has established the exact terminating failure.

The previous snapshot/aggregate-copy fix (033) does not bound the component
buffers themselves. Warming the tessellation cache avoids computation but
does not reduce their size. Required follow-up: bounded initial scene detail,
allocation limits and memory/cancellation validation outside the user's browser
before another interactive handoff. No mechanical geometry, acceptance
threshold or renderer tolerance was changed in this diagnosis.
