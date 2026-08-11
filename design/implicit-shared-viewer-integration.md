# Implicit as a shared render type: one viewer component, four formats

Execution plan. The implicit raymarch display stays — but it moves INSIDE the shared
`CadViewer` runtime as the 4th render type next to STL, GLB, and 3MF, driven by the same
camera, `OrbitControls`, zoom defaults, fit/reset logic, toolbar, and perspective
persistence the mesh formats share. `ImplicitCadViewer.js` (1,140 lines, a second
`WebGLRenderer`, a second `OrbitControls`, duplicated zoom/damping/fit constants) is
deleted at the end.

Decision context this plan builds on — do not relitigate any of it:

- **Raymarch is the display path for implicits.** Baked-mesh display was shipped and then
  reversed for quality (`design/implicit-viewer-raymarch-restore.md`, decision recorded
  2026-08-07: "display and exchange are split — raymarch for pixels, mesh packages for
  export"). This plan changes WHO HOSTS the raymarch pass, never WHAT renders the pixels.
- **Implicits are not artifact-managed for display.** They render live from their module;
  no generating/stale states (`CadWorkspace.js` comment at `ARTIFACT_MANAGED_SOURCE_FORMATS`,
  ~L298). Unchanged here.
- The workspace data flow (module load, params, animation, 36 ms rebuild throttle) already
  lives in `CadWorkspace`/`useCadAssets` and is format-agnostic state. Unchanged here.

## 0.0 Execution status — steps I1–I4, I6, I7 DONE

| Step | Title | Status |
|---|---|---|
| I1 | `useImplicitRaymarch` hook | **DONE** |
| I2 | CadViewer implicit arm | **DONE** |
| I3 | CadRenderPane: delete the fork | **DONE** |
| I4 | CadWorkspace rewiring | **DONE** — zoom pill only; see below |
| I5 | Dead client export path | **NOT DONE** — separable cleanup, still outstanding |
| I6 | Delete ImplicitCadViewer | **DONE** (1,140 lines) |
| I7 | Tests | **DONE** — `viewer/src/client/components/viewer/implicitFit.test.js` |

Corrections to the plan, found while executing:

- **I4's camera-persistence work was unnecessary.** No `fileSessionState` change was
  needed and the shared validator already rejects foreign snapshots. Verified
  behaviourally instead: after an orbit, a reload returns an implicit to its default fit —
  **byte-identical to what a mesh model does in the same flow**, which is the parity the
  step was really asking for.
- **`resetZoomAndPan` / `zoomToFit` needed no implicit branch at all.** Both already route
  through `runtimeFramingBounds(runtime, …)`, which falls back to `runtime.modelBounds` —
  so setting that via `applyRuntimeModelBounds` in the implicit arm was sufficient. Only
  `zoomToFitSelection` needed a fallback (an implicit has no sub-part selection).
- **The mesh-build effect had to stop clearing the runtime's model identity.**
  `clearDisplayedModel()` runs for an implicit (no mesh data) and reset `activeModelKey`,
  which made `emitPerspectiveChange` treat every camera move as belonging to a stale model
  and silently stop persisting the view. It now takes `preserveModelIdentity`.
- **Stage suppression had to be gated at the funnels, not in an effect.** An effect racing
  the theme/environment effects is order-dependent; `updateActiveGridHelper` and a new
  `applyActiveSceneBackground` wrapper are the single funnels every grid/background update
  goes through, including the runtime's first one.
- **Resolution scaling needed a shared-runtime hook.** `applyRenderQuality` gained an
  opt-in `resolveExtraPixelRatioCap` that only ever caps DOWN, so the mesh path (which
  installs no resolver) is unaffected.

Verified end-to-end in the dev viewer under Metal-backed playwright (`page.screenshot`,
never canvas `drawImage` — see the METHOD WARNING in the restore doc):

- **46/47 implicits render.** The one exception, `menger-sponge`, is the pre-existing empty
  -field model defect recorded in `design/implicit-viewer-raymarch-restore.md` §R5, not a
  regression.
- Shared controls all drive the raymarch: zoom in (0.228→0.285 coverage), zoom out
  (→0.229), wheel (→0.963), **Reset view (→0.211, repeatable)**, orbit, view cube.
- The **zoom percent pill is live** (reads 800% after a wheel zoom) — a capability
  implicits did not have before.
- Live parameters still re-render: gear thickness 6.5→12 mm moved 16.8% of sampled pixels;
  carrier orbit 0→120° moved 3.0%.
- Theme switch retints the shader (light `223,227,235` → dark `34,42,54`).
- STL, 3MF, GLB, STEP and DXF all still render, with their grid and stage intact —
  confirming the suppression is implicit-only.
- Gates: `viewer` 290 tests, `cadjs` 469, `implicitjs` 364 — all pass; `viewer run build`
  clean; `scripts/bundle/bundle.sh --check` and `scripts/dev/setup-symlinks.sh --check`
  clean.

One cosmetic artefact is visible in screenshots and is **pre-existing, not from this
change**: a faint vertical line at the exact viewport centre, present identically on the
untouched STL path.

## 0. Scope fence

**In scope (all client-side):**
- A new hook that mounts the existing fullscreen raymarch quad inside the shared viewer
  runtime and feeds it the shared camera.
- An implicit arm in `CadViewer.js` (bounds, fit, stage suppression).
- Deleting the `CadRenderPane` component fork and `ImplicitCadViewer.js`.
- Unhiding the shared zoom toolbar for implicit; unifying camera-perspective snapshots.
- Deleting the dead client-side export path (`/__cad/implicit-export`).

**Do NOT touch:**
- `packages/implicitjs` shader/render internals (`render.js` GLSL, SDF evaluator,
  mesher, equality harness). This plan only CALLS its existing exports. If an export is
  missing a parameter you need, stop and reread — the answer is in the reuse table (§2).
- The export pipeline (`implicit_export.py`, `/__cad/export`, `export.mjs`) and the
  implicit artifact/package server plumbing (`implicit_artifact.py`,
  `implicit_package.py`, scanner relations). Package retirement is R6 of
  `design/implicit-viewer-raymarch-restore.md`, a separate effort.
- Headless snapshot (`implicitHeadlessRenderEntry.js` and the `headlessRenderEntry.js`
  fork). The viewer look does not change (same shader, same in-shader background/floor),
  so snapshot parity is unaffected. Unifying the headless backends is a possible
  follow-up, not this batch.
- `ImplicitFileSheet.js`, `ImplicitGraphicsSection.js`, `implicitGraphicsSettings.js`,
  the params/animation state machine in `CadWorkspace.js`, `slices.implicit` session
  persistence, loading arms, `buildViewerImplicitAlert`. All keep working as-is.
- STEP, STL, 3MF, GLB, DXF, URDF paths — every diff to a shared file must be a no-op for
  them, verified by the gates in §6.

## 1. The seam (why this is cheap)

The raymarch material's vertex shader emits clip-space directly
(`packages/implicitjs/src/lib/implicitCad/render.js:1588`:
`gl_Position = vec4(position.xy, 0.0, 1.0)`), so the quad covers the viewport under ANY
scene and ANY camera. The fragment shader builds rays purely from uniforms
(`uCameraPosition`, `uCameraWorld`, `uProjectionInverse`, `uResolution` — render.js
~L1264, ray construction ~L1484) and paints background + floor-shadow matte + model in
one pass. Therefore:

- Add the quad to the shared `runtime.scene`; the existing
  `renderer.render(scene, camera)` in `useViewerRuntime.js` (~L415) draws it with zero
  loop changes.
- Feed the shared camera via `quad.onBeforeRender` →
  `updateImplicitCadMaterialUniforms(material, camera, w, h)` (render.js ~L1872).
  `w/h` are DRAWING-BUFFER pixels (`renderer.getDrawingBufferSize`) because the shader
  divides `gl_FragCoord` by `uResolution`.
- Viewport frame insets come free: `CadViewer` applies them to the shared camera's
  projection, and the shader reads `projectionMatrixInverse`.
- The shader assumes a perspective camera. Implicit is already forced to PERSPECTIVE
  along with every non-STEP format (`workbench/CadRenderPane.js` ~L357–363), so nothing
  new is needed; ortho raymarch is explicitly out of scope.
- The shader paints its own background and floor shadow (deliberately matched to the mesh
  stage look — render.js ~L1365, ~L1448). So for implicit the shared stage objects
  (floor, grid, environment/background, lights, shadow rig) are HIDDEN, not restyled.
  Set `material.depthTest = false`, `material.depthWrite = false`,
  `quad.frustumCulled = false`.

## 2. Reuse table — existing exports the new code calls

| Need | Existing export (do not rewrite) |
|---|---|
| Quad + material + shaderKey | `createImplicitCadFullscreenScene(THREE, model)` — `cadjs/implicit/render` (re-export of implicitjs render.js ~L1878) |
| Cheap param/animation update (no recompile) | `implicitCadModelShaderKey(model)` compare, then `updateImplicitCadModelUniforms(THREE, material, model)` — port the diff logic from `ImplicitCadViewer.js` ~L644–716 |
| Async shader warmup (KHR_parallel_shader_compile) | `armImplicitShaderCompile` — port from `ImplicitCadViewer.js` ~L302 (it is local there; move it into the new hook file) |
| Theme → shader uniforms | `updateImplicitCadAppearanceUniforms(THREE, material, model, { themeSettings, graphicsSettings })` |
| Graphics settings → uniforms | `updateImplicitCadGraphicsUniforms(material, model, graphicsSettings)` |
| Tight floor/frame bounds (async CPU SDF scan) | `refreshImplicitCadFloorBounds(model, material)` → returns bounds; call `runtime.requestRender()` when it resolves |
| Camera fit, baseline, transitions | shared: `zoomRuntimeToBounds` / `applyRuntimeModelBounds` in `CadViewer.js` (~L613, ~L1099, ~L2150) — NOT `implicitCadCameraState`/`runAutoZooom`/`refineImplicitFit`, which die with `ImplicitCadViewer` |
| Controls, keyboard orbit, view cube, insets | already shared (`viewportCameraKit.js`, `orbitControls.js`, `ViewPlaneControl`) — mounted by `CadViewer`, nothing to do |

## 3. Steps

### I1 — `useImplicitRaymarch` hook

New file `viewer/src/client/components/viewer/hooks/useImplicitRaymarch.js`.
Signature: `useImplicitRaymarch(runtimeRef, { model, modelKey, themeSettings,
graphicsSettings, dynamicRenderActive, enabled })`. Responsibilities:

1. When `enabled` and a runtime exists: create the fullscreen scene once per shader key;
   on model change compare `implicitCadModelShaderKey` — same key → uniform update only;
   new key → dispose old quad/material, build new, `armImplicitShaderCompile`, add to
   `runtime.scene`. Always `runtime.requestRender()` after any uniform change.
2. `quad.onBeforeRender = (renderer, _scene, camera) => updateImplicitCadMaterialUniforms(material, camera, dbw, dbh)`
   with `renderer.getDrawingBufferSize` for `dbw/dbh`.
3. Apply appearance + graphics uniforms on `themeSettings`/`graphicsSettings` change.
4. Kick `refreshImplicitCadFloorBounds` per model (skip while `dynamicRenderActive`,
   mirroring `ImplicitCadViewer.js` ~L495/~L520); surface the resolved tight bounds to
   the caller (return value or callback) so CadViewer can refine the fit.
5. Resolution scaling during interaction: while `dynamicRenderActive`, cap the shared
   renderer's pixel ratio with
   `implicitGraphicsRenderResolutionScale(graphicsSettings, ...)` and restore it when
   inactive — port the `setPixelRatioCap` pattern from `ImplicitCadViewer.js` ~L817,
   ~L857–922. Add the cap helper to the shared runtime object in `useViewerRuntime.js`
   rather than reaching into `renderer` from the hook.
6. Cleanup on unmount/disable: remove quad from scene, dispose geometry/material,
   restore pixel ratio.

### I2 — CadViewer implicit arm

`viewer/src/client/components/CadViewer.js`:

1. New props: `implicitModel`, `implicitModelKey`, `implicitGraphicsSettings`,
   `implicitDynamicRenderActive` (names match what `CadRenderPane` already receives).
   Internal `implicitActive = renderFormat === RENDER_FORMAT.IMPLICIT`.
2. Mount `useImplicitRaymarch` gated on `implicitActive`.
3. Audit every `meshData` guard so an implicit entry with `meshData == null` still
   brings up the runtime, controls, and render loop (search for early returns and
   `viewportHasRenderableContent`-style gates; `workbench/CadRenderPane.js` ~L424 already
   computes renderable-content correctly).
4. Stage suppression when `implicitActive`: hide floor/grid/environment scene objects,
   `scene.background = null`, skip shadow-map work. Prefer one `implicitActive` branch
   where the stage is (re)built over scattering visibility flips.
5. Bounds + fit: build a `THREE.Box3` from `implicitModel.bounds` (model units are mm,
   same as the mesh path — verify `sceneScaleMode` is the CAD 1:1 mode, and never the
   URDF scale). Call `applyRuntimeModelBounds` and first-fit via `zoomRuntimeToBounds`
   with `resetZoomBaseline: true` — the exact pattern the mesh path uses (~L2817). When
   the hook reports tight bounds, re-apply and re-fit ONLY if the user has not detached
   auto-zoom and not while `implicitDynamicRenderActive` (mirrors
   `ImplicitCadViewer.js` ~L538).
6. Imperative handle: no implicit-specific additions. The shared implementations of
   `applyZoomPercent`, `resetView`, `resetZoom`, `zoomToFit`, `activateViewPlaneFace`,
   `activateDefaultViewPlane`, `captureScreenshot`, `getPerspective`/`setPerspective`
   now serve implicit — that is the point of the change. `zoomToFitSelection` falls back
   to model bounds (no selection exists for implicit).
7. Picking/selection/drawing/exploded hooks: already prop-gated off by the pane; assert
   they no-op cleanly with no mesh in the scene (raycast against an empty `modelGroup`
   must not throw).

### I3 — CadRenderPane: delete the fork

`viewer/src/client/components/workbench/CadRenderPane.js` ~L463–480: remove the
`implicitMode ? <ImplicitCadViewer/> : <CadViewer/>` ternary; always render `CadViewer`,
passing the implicit props through. Keep `implicitMode` (~L354) as the capability row
that strips selection/pan/draw/params props — same pattern as `meshOnlyMode`/`dxfMode`.
Drop the `ImplicitCadViewer` import. `previewMode` auto-rotate now rides the shared
controls path.

### I4 — CadWorkspace rewiring

`viewer/src/client/components/CadWorkspace.js`:

1. ~L8287: `zoomControlsVisible` currently excludes implicit
   (`effectiveRenderFormat !== RENDER_FORMAT.IMPLICIT && !!selectedMeshData`). Change to
   show the zoom pill when implicit has a model:
   `implicit ? !!selectedImplicitModel : !!selectedMeshData`.
2. Camera persistence: with one component, implicit camera slices become the shared
   snapshot format automatically. Delete nothing in `fileSessionState.js`; old slices
   stamped `implicit: true` / `cameraVersion: 8` (written by the deleted viewer's
   `perspectiveSnapshot`, `ImplicitCadViewer.js` ~L145) must simply be REJECTED by the
   shared validation (`perspectiveSnapshotMatchesScene`) and fall back to the default
   fit. Verify that rejection happens; if the shared validator would accept a stale
   implicit payload, add the version check that makes it reject. No migration, no shim
   (repo compat posture: `design/unified-glb-render-artifacts.md` §0.2).
3. Loading arms, alerts, params/animation state, export handler
   (`handleExportModelFile` → `/__cad/export`): unchanged.

### I5 — Dead client export path

`viewer/src/client/workbench/implicitExport.js` POSTs `/__cad/implicit-export`, which no
`viewer/server_py` handler implements — it is dead code from before the server-side
export landed. Delete the module and its wiring (`onExportImplicitFile` through
`FileViewerSidebar`/`FileAccessContextMenu`); route those menu entries to the existing
server-side export flow (`handleExportModelFile`). Verify with a grep that no
`implicit-export` reference survives in `viewer/` or `packages/`.

### I6 — Delete ImplicitCadViewer

Delete `viewer/src/client/components/ImplicitCadViewer.js`. Then audit the
`cadjs/implicit/*` re-export subpaths (`packages/cadjs/src/implicit/`,
`packages/cadjs/package.json` exports): keep the ones the new hook imports
(`render` at minimum, `graphicsSettings` via the workbench store), delete any that lose
their last importer. `implicitCadCameraState` and friends stay exported — headless
snapshot still uses them (`configureImplicitCadCamera`).

### I7 — Tests

- Fix/replace anything importing `ImplicitCadViewer` (grep first).
- Keep `implicitGraphicsSettings.test.js` and the implicitjs suites untouched and green
  (the SDF equality harness gates nothing here but must not regress).
- Add a small test for the shader-key diff logic in `useImplicitRaymarch` (same key →
  no material rebuild; changed key → rebuild) — this is the one piece of ported logic
  with real regression surface.
- `fileFormats.js` / `entryAssets.js` behavior is unchanged; do not touch their tests.

## 4. Deletion inventory (end state)

- `viewer/src/client/components/ImplicitCadViewer.js` — including its private constants
  (`DEFAULT_ZOOM_SPEED 4.5` / `ACCELERATED 10` / `TRACKPAD 14`, damping `0.14`,
  `AUTO_ZOOM_FRAME_MARGIN 1.08`, `DEFAULT_FOV_DEG 48`, `IMPLICIT_CAMERA_VERSION 8`) and
  its fit/transition machinery. The shared defaults win everywhere
  (`useViewerRuntime.js` controls setup ~L184, `cadjs/lib/viewer/autoZoom.js`
  `DEFAULT_AUTO_ZOOM_PADDING 1.04`). Feel differences are accepted — uniformity is the
  goal.
- The `CadRenderPane` component fork and `ImplicitCadViewer` import.
- The `zoomControlsVisible` implicit exclusion (`CadWorkspace.js` ~L8287).
- `viewer/src/client/workbench/implicitExport.js` + `/__cad/implicit-export` wiring.
- Any `cadjs/implicit/*` subpath with no remaining importer.

## 5. Decisions (made; the executor does not reopen them)

1. **Hosting model:** raymarch quad inside the shared scene, shared render loop, uniforms
   via `onBeforeRender`. NOT a second renderer, NOT gl_FragDepth compositing with the
   shared stage — the in-shader background/floor stays (it already matches the stage
   look). Depth-composited integration is a possible later batch.
2. **Perspective-only.** Same forced-perspective rule as STL/3MF/GLB/DXF today.
3. **Shared zoom/controls constants replace the implicit-specific ones.** No per-format
   tuning knobs are added.
4. **Old implicit camera session slices invalidate** (fall back to default fit). No
   migration.
5. **Tone mapping / color:** `ShaderMaterial` bypasses the renderer's ACES tone mapping
   and output-color-space chunks, so pixels should be identical to the standalone
   renderer. This is verified by the screenshot gate, not assumed: if a shift appears,
   scope the fix to the implicit pass (e.g. `renderer.toneMapping = NoToneMapping`
   saved/restored around the implicit frame) — do not touch mesh rendering.

## 6. Gates

- `npm --prefix viewer run test` and `run build`; `npm --prefix packages/cadjs test`;
  `npm --prefix packages/implicitjs test`.
- **Full-corpus visual sweep**: load all 43 implicits through the dev viewer with
  playwright, `--use-angle=metal` (SwiftShader renders differently — repo memory), assert
  non-blank viewport via `page.screenshot()` (canvas `drawImage` sampling reports blank
  for every format — known trap). Screenshot `planetary-gear-a`, `catenoid-ring-bridge`,
  `gosper-curve-tube` and compare against pre-change captures of the same models —
  background, floor shadow, and surface shading must match.
- **Shared-feature checks on one implicit model** (this is the acceptance list for the
  whole change): wheel zoom + trackpad pinch use shared speeds; keyboard orbit; view
  cube; **zoom % pill appears and works** (new); Reset Zoom / Zoom to fit via toolbar
  AND context menu; params slider live-updates the surface with interaction-time
  resolution scaling engaged and released; animation play; graphics settings (detail,
  shadows, AO, rim); theme switch; screenshot copy/download; camera persists across a
  tab switch and restores.
- **Other formats untouched**: STEP, STL, 3MF, GLB, DXF, URDF each loaded once,
  screenshot-verified.
- `scripts/bundle/bundle.sh` then `--check`; dev symlink layout restored
  (`scripts/dev/setup-symlinks.sh --check`); no `git add -A`.

## 7. Cross-references

- `design/implicit-viewer-raymarch-restore.md` — why raymarch is the display path; R6
  (retiring the implicit render package) remains open and separate.
- `design/unified-glb-render-artifacts.md` — package/CLI architecture and the
  no-shims compat posture (§0.2) this plan inherits.
- `viewer/docs/settings-ui.md` — binding if any settings UI is touched (it should not
  be; the implicit sheets are out of scope).
