# Handoff: PR #370 review + viewer memory/perf work (2026-09-08)

Written because the reviewing session ran out of budget mid-round. Delete this
file before merge. The design record is
`~/robots/text-to-cad-notes/design/viewer-memory.md`; the bug-log verdicts are in
`~/robots/text-to-cad-notes/tendon-hand-bugs.md` (the PR's old `BUGS.md`, with a
verdict table appended).

## State of this branch (all pushed, all suites green at each commit)

| commit | what |
|---|---|
| `bbc48ff9c` | BUGS.md triage fixes: tree built from the re-read STEP (028/029), op_memo content identity (011), snapshot uploads bypass the Playwright pipe (006/018), AddOptimal bounds (004), validate in own frame (021), GLB Map cap (015), tube stack cleanup, docs/CLI records |
| `ef70578f3` | `cadgen.declare_input`; op_memo digest purity; CONTRIBUTING worktree node_modules fix |
| `a781efc57` | Viewer lever C: progressive publish |
| `15c8e28b7` | Viewer lever B: indexed geometry, CAD edges via line pass |
| `4fe5188d2` | Fix: geometry cache keyed on component (the composed-mesh key re-uploaded everything per publish → 7 GB GPU); edges as indexed GL_LINES |
| `fb1632c5b` | 24-entry render-asset leash, `window.__cadRenderMemoryProbe()`, (throttle — since deleted) |
| `52c4ad771` | Render module gated to final publish (WRONG, see below), tube rest-prep cache, BVH idle 30 s, throttle deleted, Issues tab removed |

Headless measurement, r13 hand (866 components / 3,259 occurrences, warm
store), baseline → `fb1632c5b`:

| metric | before | after |
|---|---|---|
| first geometry on screen | ~86 s | 4.7 s |
| time to fully loaded | 86–90 s | 186 s |
| CPU typed arrays | 2.50 GB | 0.54 GB |
| GPU buffer bytes | 2418 MiB | 524 MiB |
| JS heap peak | 3.3 GB | 1.9 GB |
| renderer RSS peak | 4.5 GB | 3.4 GB |
| all-process RSS peak | 7.3 GB | 4.2 GB |
| draw calls / frame | 6,690 | 9,949 |

Harness: `tmp/viewer-memory/measure.mjs` in the review worktree (gitignored;
copy it somewhere durable — `scripts/bench/` is the right home). Protocol:
main checkout server over its warm schema-17 store with
`--dist <worktree>/apps/viewer/dist`, `--new`, own high port, wait on
`window.__cadMeshCost.final`. Never open the hand in the user's browser.

## Open problems, in priority order

1. **The user's real Chrome still crashes loading the hand** (from `52c4ad771`).
   Headless renderer peak 3.4 GB is not enough margin. Target: load-time
   renderer peak well under 2 GB. Suspects: 8-wide worker decode with ~90 MB
   components (worker intermediates count against the renderer), the
   count-bounded (24 entries) render-asset leash in
   `packages/cadgen-js/src/lib/renderAssetClient.js` (24 × 90 MB), transient
   copies in `surfMeshData`. Fix direction: byte-aware decode admission in
   `useCadAssets.js` (cap in-flight bytes ~256 MB), byte-bounded leash, release
   worker-side payloads promptly. Then re-measure at 250 ms sampling.
2. **Render-module gating in `52c4ad771` is wrong UX and must be reversed.**
   User: while loading, the animation tab shows "loading animation" with dead
   controls, and the kinematics tab bounces to the next tab. Wanted: attach the
   `.step.js` module on the FIRST publish, occurrence lookups for unloaded
   labels are silent no-ops that bind when the occurrence arrives, sections
   interactive while partial, clip validation only on the final state. Keep the
   alert dedupe/clear. Files: `apps/viewer/src/client/components/CadWorkspace.js`
   (`selectedMeshPartial`, `meshStateAcceptsRenderModule`),
   `workbench/hooks/packageProgressiveLoad.js`, `useCadAssets.js`.
3. **Load time 186 s vs 86 s.** Profile attribution (routing fixture): every
   publish tears down and rebuilds all display records (re-poses tubes, churns
   React over occurrences × publishes), plus MeshBVH builds. Fix: incremental
   records across publishes (reuse records for present occurrences, add new,
   remove departed). Partially started — see WIP branch below.
4. **Orbit is sluggish**: ~10k draw calls/frame (surface mesh + edge object per
   occurrence). Fix: one instanced fat-line geometry per component (instance
   matrix per occurrence, per-instance colour/opacity/visibility) — also
   restores per-class edge THICKNESS, which the GL_LINES cutover reduced to
   on/off (flagged, not approved by the user). Later: instance surface meshes
   the same way (~866 draw calls instead of ~6.5k). Prior art: the old
   `claude/falcon-perf-lab` instance-backed records.
5. Follow-ups noted, not started: `node_resolve_register.mjs` DEP0205 needs the
   shipped Node floor raised to ≥22.15 (wheel floor is 20); op_memo
   `Checked`-flag digest residue (documented in the file); `assembly.json`
   component bounds would let the first publish frame the exact model.

## Binding user constraints for perf work

All functionality and features preserved: per-occurrence highlight, dim,
hide, focus, opacity, exploded view, picking, tube deformation, per-class edge
colour/opacity (and thickness, to restore), animation/kinematics. Suspending
hover/selection raycasts while the camera moves is fine. Hiding edges or any
geometry during motion is NOT. No backwards-compat shims; hard cutovers.

## Unverified work in flight

Branch `wip/pr370-viewer-perf-instanced-edges` (`219707c01`, pushed) holds an
agent's mid-implementation of items 3 and 4: `cadEdgeInstances.js` (new),
changes to `cadScene.js`, `renderEdges.js`, `displayRecordTransform.js`,
`partVisualState.js`, `selectorPickGroups.js`, `modelRuntime.js`,
`tubeDeformation.js`, `CadViewer.js`, `renderMemoryAccounting.js`. It was NOT
tested as a whole and the bundle was not regenerated. Either finish it (run
`npm --prefix packages/cadgen-js test`, `npm --prefix apps/viewer run test`,
`scripts/bundle/bundle.sh`, then measure) or discard it and redo items 3–4
from the design doc.

## Worktree notes

- Review worktree: `.claude/worktrees/pr370-review` on `review/pr370-bugs`
  (tracks this PR branch). Its `apps/viewer/node_modules` is a directory of
  per-entry symlinks with `cadgen-js` → the worktree package; a whole-dir
  symlink silently tests the primary checkout's cadgen-js (CONTRIBUTING now
  says so).
- A viewer instance on port 3400 (main checkout server, `--dist` the worktree's
  `apps/viewer/dist`) was started for the user by the reviewing session and
  can be stopped.
- Python in the worktree: `PYTHONPATH=<worktree>/packages/cadgen/src <main>/.venv/bin/python`.
