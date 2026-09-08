# Handoff: PR #370 viewer memory/perf work — step-by-step for the next agent

Written 2026-09-08 by the reviewing session, which ran out of budget mid-round.
Follow the steps in order. Delete this file in the last commit before merge.

Background documents (read-only, outside the repo):
- Design: `~/robots/text-to-cad-notes/design/viewer-memory.md`
- Bug-log verdicts: `~/robots/text-to-cad-notes/tendon-hand-bugs.md`

## 0. Facts you must not guess

- Repo: `/Users/jakefitzgerald/robots/text-to-cad` (call it MAIN). MAIN is on
  branch `codex/anthropomorphic-tendon-hand` at an OLD commit and has the warm
  CAD cache (`~/.cache/cadgen`, schema 17) and the hand's built STEP files under
  `MAIN/models/assemblies/STEP/anthropomorphic_hand/`. Do not switch MAIN's branch.
- Review worktree: `MAIN/.claude/worktrees/pr370-review` (call it WT), branch
  `review/pr370-bugs`, which IS the PR branch (pushing it updates PR #370):
  `git -C WT push origin HEAD:codex/anthropomorphic-tendon-hand`.
- Python in WT: `PYTHONPATH=WT/packages/cadgen/src MAIN/.venv/bin/python`.
  Without PYTHONPATH you silently run MAIN's cadgen.
- Node deps: `WT/packages/cadgen-js/node_modules` is a symlink to MAIN's.
  `WT/apps/viewer/node_modules` is a real directory of per-entry symlinks with
  `cadgen-js -> WT/packages/cadgen-js`. Check with
  `readlink -f WT/apps/viewer/node_modules/cadgen-js`; it must print the WT path.
  If it prints MAIN's path, the viewer tests are testing the wrong code.
- Suites (run from WT):
  `npm --prefix packages/cadgen-js test` (expect ~818 pass),
  `npm --prefix apps/viewer run test` (expect ~345–363 pass),
  `PYTHON_BIN=MAIN/.venv/bin/python scripts/test/test-python.sh`,
  `PYTHON_BIN=MAIN/.venv/bin/python scripts/test/test-global.sh`,
  `scripts/bundle/bundle.sh` then `scripts/bundle/bundle.sh --check` whenever
  anything under `packages/cadgen-js/src` changed (commit the regenerated
  `packages/cadgen/src/cadgen/_runtime/browser/snapshot-render.js`).
- The pre-commit hook runs the bundle check against the WORKING TREE. If
  unrelated uncommitted cadgen-js edits exist, commit with `--no-verify` only
  when your staged files do not feed the bundlers.
- The hand fixture is `assemblies/STEP/anthropomorphic_hand/hand_mechanical_candidate_r13.step`
  (866 components, 3,259 occurrences, store tree hash starts `2a8d6619`). A
  smaller fixture that loads in ~30 s: `assemblies/STEP/anthropomorphic_hand/routing_layout_review.step`
  (303 components, 1,216 occurrences).
- NEVER open the hand in the user's browser. Their Chrome crashed twice.
  Measure headlessly only (step 1). A viewer instance on port 3400 was started
  for the user by the previous session; you may stop it
  (`lsof -ti :3400 | xargs kill`); never stop other instances.
- User constraints, binding: every feature preserved (per-occurrence
  highlight, dim, hide, focus, opacity, exploded view, hover/selection
  picking, tube deformation, per-class edge colour/opacity/thickness,
  animation, kinematics). Pausing hover/selection raycasts while the camera
  moves is allowed. Hiding edges or any geometry during motion is NOT.
  No backwards-compat shims; hard cutovers. cadgen-js stays non-React.

## 1. How to measure (do this before and after every change)

Harness files are committed at `WT/scripts/bench/viewer-memory/`:
`measure.mjs` (memory/timing), `profile.mjs` and `cpu-profile.mjs` (CDP CPU
profiles), `publish-timing.mjs`; `baseline-r13.json` and
`after3-r13-fb1632c5b.json` are reference results.

```bash
# 1. build the WT client somewhere the user's instance does not serve
cd WT/apps/viewer && npx vite build --outDir /tmp/wt-dist        # or: npm run build (writes apps/viewer/dist)
# 2. serve it from MAIN's server (warm store, schema 17) on a fresh port
cd MAIN/models && MAIN/.venv/bin/python -m cadgen.viewer --host 127.0.0.1 --port 3450 --new --dist /tmp/wt-dist --json &
# 3. measure (Playwright is resolved from MAIN/apps/viewer/node_modules)
cd WT/scripts/bench/viewer-memory && node measure.mjs --url http://127.0.0.1:3450 \
  --file assemblies/STEP/anthropomorphic_hand/hand_mechanical_candidate_r13.step \
  --label r13 --runs 2 --timeout-ms 900000 --out /tmp/r13.json
# 4. stop ONLY your instance
lsof -ti :3450 | xargs kill
```

`measure.mjs` waits for `window.__cadMeshCost.final === true`, then reports
TTFP, first geometry on screen, time-to-loaded, JS heap peak, CPU typed-array
bytes, GPU buffer bytes/count, renderer/gpu/all-process RSS peaks, draw calls
per frame, median frame. It reads `window.__cadMeshCost` (set on every
progressive publish by `apps/viewer/src/client/components/workbench/hooks/packageProgressiveLoad.js`)
and `window.__cadRenderMemoryProbe()` (GPU-array and cache bytes,
`apps/viewer/src/client/render/renderMemoryAccounting.js`).

Reference numbers, r13, headless, 2 runs:

| metric | baseline (old client) | at `fb1632c5b` |
|---|---|---|
| first geometry on screen | ~86 s | 4.7 s |
| time to fully loaded | 86–90 s | 186 s |
| CPU typed arrays | 2.50 GB | 0.54 GB |
| GPU buffer bytes / count | 2418 MiB / 4,381 | 524 MiB / 5,337 |
| JS heap peak | 3.3 GB | 1.9 GB |
| renderer RSS peak | 4.5 GB | 3.4 GB |
| all-process RSS peak | 7.3 GB | 4.2 GB |
| draw calls per frame | 6,690 | 9,949 |

## 2. What is already on the PR branch (all pushed, all suites green)

| commit | what |
|---|---|
| `bbc48ff9c` | BUGS.md triage fixes in cadgen (read_step tree from re-read STEP, op_memo content identity, snapshot uploads bypass the Playwright pipe, AddOptimal bounds, validate in own frame, GLB Map cap, tube stack cleanup, docs/CLI) |
| `ef70578f3` | `cadgen.declare_input`; op_memo digest purity; CONTRIBUTING node_modules recipe |
| `a781efc57` | viewer progressive publish (`packageProgressiveLoad.js`, `useCadAssets.js`) |
| `15c8e28b7` | indexed component geometry; CAD edges via line pass (`surfMeshData.js`, `cadScene.js`, `renderEdges.js`) |
| `4fe5188d2` | geometry cache keyed on component (fixes 7 GB re-upload leak); edges as indexed GL_LINES |
| `fb1632c5b` | 24-entry render-asset leash (`renderAssetClient.js`), `__cadRenderMemoryProbe` |
| `52c4ad771` | render module gated to FINAL publish (wrong, undo in step 4), tube rest-prep cache, BVH idle 30 s, Issues tab removed |
| `56df5d051` | first version of this handoff |

## 3. Unverified work now ON THIS BRANCH — verify first

At the user's request the whole working tree was pushed to the PR as the last
commit ("WIP" in its subject). Its state:

- apps/viewer (DONE, viewer suite 348/348 at the time): steps 4 and 5 below
  are implemented — `CadWorkspace.js` (gating reversed, `meshStateIsComplete`
  only gates clip validation, `tolerantAnimationClip` makes missing labels
  no-ops while partial), `packageProgressiveLoad.js` (+test: count+byte
  admission `PROGRESSIVE_LOAD_MAX_INFLIGHT_BYTES` 256 MB,
  `PROGRESSIVE_LOAD_UNMEASURED_SHARE` 4, HEAD content-length estimator),
  `useCadAssets.js`. Read steps 4–5 as the acceptance spec and confirm.
- cadgen-js + `CadViewer.js` + `renderMemoryAccounting.js` (NOT DONE, NOT
  TESTED as a whole): an agent's mid-implementation of steps 6 and 7 —
  `cadEdgeInstances.js` (new), `cadScene.js` (+test), `renderEdges.js`,
  `displayRecordTransform.js`, `partVisualState.js`, `selectorPickGroups.js`,
  `modelRuntime.js`, `tubeDeformation.js`. The browser bundle was NOT
  regenerated for these, so `scripts/bundle/bundle.sh --check` fails at this
  commit until you run `scripts/bundle/bundle.sh`.

Procedure: run `npm --prefix packages/cadgen-js test` and
`npm --prefix apps/viewer run test`. If both pass, run `scripts/bundle/bundle.sh`,
commit, and continue with steps 6–7 using the diff of the WIP commit as your
starting point. If cadgen-js fails and the cause is not obvious within an
hour, revert ONLY the cadgen-js/CadViewer/renderMemoryAccounting parts of the
WIP commit (`git checkout 52c4ad771 -- <those paths>`, delete
`cadEdgeInstances.js`), keep the apps/viewer parts, run `bundle.sh`, commit,
and redo steps 6–7 from the design. Do not merge with the bundle check red.

## 4. Undo the final-publish render-module gating (user-reported bug)

Symptoms: while the hand loads, the Animation tab shows "loading animation"
and its controls do nothing; clicking the Kinematics tab bounces to the next
tab. Cause: commit `52c4ad771` made `CadWorkspace.js` treat a partial mesh
state as "no render module yet" (`selectedMeshPartial`, helper
`meshStateAcceptsRenderModule` in `packageProgressiveLoad.js`), nulling
`selectedStepParameterRuntime`, disabling `animationRenderFrame`, and giving
the Pose/Animation sections `status: "loading"`; the tab layout skips sections
in that status.

Required behaviour:
1. Attach the `.step.js` render module on the FIRST publish and keep it
   attached across publishes.
2. Occurrence lookups (by label) for occurrences not yet loaded return a
   no-op handle: no error, no alert. When a later publish adds that
   occurrence, bind it (re-run the module's setup against the new composition,
   or re-attach on each publish if attach is cheap — measure with
   `performance.now()` around it on the routing fixture and say which).
3. Pose, Kinematics and Animation sections are visible and interactive while
   partial (a "N/total parts loaded" hint is fine). Never `status: "loading"`.
4. `validateRenderModuleClips` (lists clip errors) runs only when
   `missingComponentIds` is empty and `assemblyInteractionReady` is true.
5. Keep the alert dedupe/clear added in `CadViewer.js` (`applySceneState.onError`
   alerts deduped by title+message, cleared when a pass runs clean).
6. Delete `meshStateAcceptsRenderModule` if nothing uses it.

Tests: extend `packageProgressiveLoad.test.js` with a fake label-resolving
module over a 9-component/18-occurrence progressive load: module invoked on
publish 1, missing labels are no-ops, late occurrences get bound, clip
validation runs once on final. Run the viewer suite.

## 5. Cut the load-time memory peak (the crash)

Target: renderer RSS peak during load well under 2 GB on r13 (measure per §1;
sample at 250 ms if you extend `measure.mjs`). Known contributors:
- `useCadAssets.js` decodes 8 components concurrently in workers
  (`concurrency = 8` in `packageProgressiveLoad.js` `createProgressivePackageLoader`);
  hand components decode to up to ~90 MB each; worker intermediates count
  against the renderer process. Add byte-aware admission: cap in-flight decode
  bytes (start 256 MB) alongside the count cap; use the cache entry size if
  known before fetch, else the fetched byte length; release each decoded
  payload's worker-side copy as soon as meshData and the selector bundle are
  built.
- `packages/cadgen-js/src/lib/renderAssetClient.js`: the surf leash is
  count-bounded (`SURF_CACHE_LIMIT = 24`). 24 × 90 MB pins >2 GB. Make it
  byte-bounded (e.g. 256 MB total decoded bytes with a small count floor so
  tiny models behave as today), evict oldest first, test with large fake
  entries.
- Verify departed/replaced records dispose GPU buffers and BVHs (test).
Acceptance: r13 renderer RSS peak < 2 GB headless, first geometry ≤ 6 s,
all suites green. Only then may the user be given a link.

## 6. Load time 186 s → toward 86 s: incremental scene records

CDP profile on the routing fixture attributed the extra time to: every
publish tearing down and rebuilding ALL display records in `cadScene.js` /
`CadViewer.js` (re-creating meshes, materials, edge objects, re-posing tubes,
re-queuing BVH builds) and React re-rendering the parts tree per publish
(occurrences × ~28 publishes). Fix: when a new composed mesh state arrives for
the same file/request, reuse existing records for occurrences already present,
create records only for new occurrences, remove only departed ones. Add a test
that builds incrementally over 3 publishes and asserts the record set,
matrices, materials, edge objects and BVH identity equal a one-shot build.
Measure per-publish main-thread time before/after with
`scripts/bench/viewer-memory/publish-timing.mjs`.

## 7. Orbit speed and edge thickness: instanced edge lines

Each occurrence is one surface Mesh + one edge LineSegments → ~10k draw calls
on the hand; WebGL draw-call overhead dominates orbit. Replace per-occurrence
edge objects with ONE instanced fat-line geometry per component
(LineSegments2-style or a screen-space line shader): instance matrix per
occurrence, per-instance colour/opacity/visibility attributes so highlight,
dim, hide, focus, exploded view and selection keep working per occurrence;
per-class colour, opacity AND thickness from `display.edges.classes` (the
GL_LINES cutover in `4fe5188d2` reduced thickness to on/off — restore it).
Deformed tubes keep their own non-instanced edge objects. Budgets: edge GPU
bytes ≤ 10% of surface bytes, ≤ ~10 GPU buffers per component (keep the cache
keyed on the component — the 7 GB leak came from keying on the composed
mesh), add an accounting test. Report draw calls/frame and orbit median/p90
frame time before/after on the routing fixture with a scripted drag.

Later (assess, then do if time): instance SURFACE meshes per component with
the same per-instance state design (~866 draw calls instead of ~6.5k).

## 8. Small follow-ups (not started)

- `packages/cadgen/src/cadgen/_internal/node_resolve_register.mjs` uses
  deprecated `module.register` (Node DEP0205). `module.registerHooks` needs
  Node ≥ 22.15; the wheel's shipped floor is Node 20 (`node_runtime.py:120`,
  `skills/dxf/SKILL.md`). Raise the floor first, then migrate.
- `op_memo._tshape_digest` still serializes BinTools' mutable `Checked` flag
  (documented in the function's docstring): missed disk hits only.
- Emitting per-component bounds in `assembly.json` would let the first
  progressive publish frame the exact model.

## 9. Before merging

Run all suites in §0, `scripts/bundle/bundle.sh --check`, re-measure r13 per
§1 and paste the table in the PR, delete this file, push.
