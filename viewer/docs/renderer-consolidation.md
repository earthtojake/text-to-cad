# CAD renderer consolidation

Status/handoff doc for unifying the CAD render paths around one shared
viewport shell + pluggable scene backends. Goal: global render features are
added once and work for every render format, **in every host** — the
interactive viewer *and* the headless snapshot pipeline.

The mesh viewer (`CadViewer`) is the **reference implementation**; the
implicit viewer is being brought in line with it (not vice-versa).

## The render paths (why the seam lives in packages/)

There were four render shells, not two, and the strategy had to name all of
them or it would have consolidated the wrong half. The headless pair is now one;
the two viewer shells remain:

1. **Viewer mesh** — `CadViewer` + `useViewerRuntime` (React shell).
2. **Viewer implicit** — `ImplicitCadViewer` (bespoke renderer/RAF/framing).
3. **Headless mesh** — `packages/cadjs/src/common/renderMeshScene.js` +
   `headlessRenderEntry.js` (`window.__snapshotRender`), esbuild-bundled by
   `scripts/bundle/skills/bundle-cad.sh` into the cad skill's
   `snapshot-render.js`. Driven by the Python CLI
   `skills/cad/scripts/snapshot/__main__.py`.
4. ~~**Headless implicit** — a standalone ~980-line Node CLI,
   `packages/implicitjs/scripts/snapshot.mjs`, with its own Playwright driver,
   its own render runtime and its own job schema.~~ **RESOLVED.** The CLI, its
   runtime and its tests are deleted. `implicitHeadlessRenderEntry.js` survives
   as a BACKEND: cadjs's `headlessRenderEntry` dispatches implicit jobs to it,
   and every rendering skill drives that one bundle through the shared Python
   CLI `cadgen.snapshot_cli`. Six skills now render (cad, dxf, implicit-cad,
   urdf, srdf, sdf) and each is a declaration of which input kinds it accepts.

So there are **three** render shells, not four. Paths 3 and 4 were drifting
near-copies (duplicated gifenc/orbit-frame/job scaffolding; default orbit
elevation 30° in mesh vs 28° in implicit) — that drift is gone with the copy.
Paths 1 and 3 duplicate mesh scene assembly with different light rigs and
theme schemas (`useViewerRuntime`'s hardwired hemisphere/ambient/key/fill/rim
rig reading flat viewerTheme keys, key light at 240,-150,340, vs
`renderOptions.js applyLighting` consuming nested `themeSettings.lighting.*`,
directional at 160,-140,240). Both share only `cadScene.buildModel`. The
interactive default view direction (`DEFAULT_VIEW_DIRECTION` in the camera
kit, ~az 52°/el 22°) also differs from the headless default `iso` preset
(~az 45°/el 29.5°), so the same model renders from different angles in the
viewer vs a default snapshot.

**Placement rule that follows:** the `SceneBackend` interface and the backend
implementations live in `packages/` (interface + implicit backend in
`implicitjs`, source of truth per AGENTS.md; mesh backend core in `cadjs`;
viewer consumes via `cadjs/implicit/*` re-exports). `useViewerRuntime` is the
*interactive React shell* that hosts a backend; `headlessRenderEntry` is the
*headless shell* that hosts the same backends. A backend defined inside
`viewer/` is structurally unreachable from the snapshot bundle (bundle-cad.sh
bundles from cadjs source only; cadjs must stay non-React), which would force
a second implicit render integration. **Acceptance criterion for the seam:
the same backend module renders under both shells (verify with a headless
smoke render + a viewer screenshot).**

## Branch / layout

Work lives on `claude/viewer-renderer-consolidation-ax9vix`, **rebased onto
`release/0.4.0`** (the Python-backend viewer runtime; the old Node server is
gone). Development uses the symlink layout (`viewer/packages/{cadjs,implicitjs}`
→ `../../packages/*`, so edits to `packages/*` source are live in the viewer
build). Do not develop against a `main`-derived copy layout — source edits
there are shadowed by the checked-in bundle copies.

**Fresh checkout setup (replaces the old hand-rolled symlink recipes):**

```bash
npm ci --prefix packages/cadjs        # creates node_modules/{three,gifenc,implicitjs->../../implicitjs}
npm ci --prefix packages/implicitjs   # three/gifenc/playwright for implicitjs + headless recipes
npm ci --prefix viewer
```

This is exactly what CI's setup-deps does. Without the first one,
`npm --prefix viewer run build`, viewer/package tests, and any direct esbuild
against cadjs source fail with `ERR_MODULE_NOT_FOUND: Cannot find package
'implicitjs'` (cadjs's `file:../implicitjs` dep is materialized by npm from
the committed lockfile; the link itself is gitignored).
`scripts/bundle/skills/bundle-cad.sh` no longer needs it — it resolves
implicitjs hermetically via `NODE_PATH=packages` (a directory `--alias`
cannot: it bypasses implicitjs's exports map).

## Verification commands

- `npm --prefix viewer run build` — primary green signal (vite bundles everything)
- `npm --prefix viewer run test`
- `npm --prefix packages/cadjs test` / `npm --prefix packages/implicitjs test`
- `scripts/bundle/bundle.sh --check` — generated runtimes (snapshot-render.js
  freshness; run before handoff)
- **Visual (gate for Phases 1–3):** unit tests do NOT exercise 3D rendering.
  Use `viewer/scripts/capture-render-baselines.mjs` (committed harness): it
  drives a running dev viewer with playwright and captures fixed-fixture,
  fixed-camera screenshots of a mesh model and an implicit model per theme.
  Capture a baseline before starting a phase, re-capture after, and eyeball
  the diff. Launch the viewer via the `cad-viewer` skill launcher and point
  `?dir=` at the repo `models/` root. Fixtures: dozens of
  `models/implicits/*.implicit.js` (e.g. `parametric-pulse.implicit.js`); for
  mesh use a direct GLB/STL (e.g.
  `models/mesh/glb/miniature_spiral_staircase_highres.glb`) — a raw `*.step`
  triggers slow on-demand artifact generation (backend delay, not a render
  bug). The mesh renderer has no `preserveDrawingBuffer`, so in-page canvas
  readback reads blank — trust the composited `page.screenshot`.

## Done (landed on this branch)

1. **Shared viewport camera kit** —
   `viewer/src/client/components/viewer/viewportCameraKit.js`. Renderer-agnostic
   camera/keyboard-orbit/view-plane/orbit/easing/frame-inset helpers (canonical
   `CadViewer` implementations; zero imports, duck-types THREE off `runtime`).
   Both viewers import it; their local copies were deleted. Behavior-preserving.

2. **`cadjs` depends on `implicitjs`; `camera.js` deduped** —
   `packages/cadjs/src/common/camera.js` re-exports the byte-identical
   `implicitjs/common/camera.js`. Dependency flows `cadjs → implicitjs` only;
   `packageBoundary.test.mjs` enforces the direction (all import styles,
   src + vendored scripts).

3. **Single install** — `cadjs/implicit/*` re-export layer; all viewer imports
   moved off bare `implicitjs` (including release/0.4.0's client-side
   `implicitExport.js` → `cadjs/implicit/{loader,exportModel}`);
   `implicitjs` dropped from `viewer/package.json`.
   `viewer/src/importPolicy.test.mjs` fences the invariant (a bare implicitjs
   import resolves silently through the hoisted transitive link, so only a
   test catches it).

4. **Implicit imperative-handle parity** — `ImplicitCadViewer` ref exposes
   `resetZoom`/`zoomToFit`/`zoomToFitSelection` (all map to `runAutoZoom`
   `{force:true}`; implicit has no sub-part selection so selection-fit fits the
   whole model). **Reachability caveat:** the shared context menu that calls
   these is STEP-only today (`openGlobalViewerContextMenu` returns null when
   `!isStepView`), so they are contract parity/groundwork; user-facing wiring
   is the Phase 5 cross-format menu unlock.

5. **Hermetic snapshot bundling** — `bundle-cad.sh` resolves cadjs's
   implicitjs imports from `packages/` source via NODE_PATH (see above), so
   fresh checkouts and CI can regenerate `snapshot-render.js` without a prior
   package install.

## Remaining work

Ordering: **Phase H first or in parallel with Phase 1a** — it is the cheapest
place to prove the backend/capability design, it delivers goal-(c) value
(implicit snapshots through the unified skill tool) without touching the
~66-field viewer runtime contract, and PR #139's reimplementation (snapshot
mesh inputs) should land as part of it rather than before it.

### Phase H — headless unification (new; was entirely missing from this plan)

The headless side already has the seam shape Phase 1 wants: twin
job-in/dataUrls-out window entrypoints with cousin job schemas
(`window.__snapshotRender` in cadjs `headlessRenderEntry.js`;
`window.__implicitCadSnapshotRender` in implicitjs). Unify them:

1. **Kind dispatch at `runHeadlessRenderJob`** — the seam must sit *above*
   `loadSource` (its return contract is meshData-centric; an implicit model
   produces no meshData, so "one more case" inside `loadMeshDataFromUrl` is
   impossible). Shape: `const backend = BACKENDS[resolveJobKind(job)];
   return backend.run(job)`. The mesh backend wraps today's
   loadSource/capturePreparedSource/renderOrbit; the implicit backend
   delegates to implicitjs's headless entry (cadjs imports it directly —
   sanctioned direction; no new public re-export subpath is required for a
   cadjs-internal import). Keep the orbit/GIF encode helpers backend-agnostic
   (they already operate on dataUrl frames) and collapse the near-duplicate
   `headlessOrbitFrames.js` / `implicitHeadlessOrbitFrames.js` (reconcile the
   30° vs 28° elevation default deliberately).
2. **One render-contract table, generated as data** — the Python CLI
   hand-maintains per-format capability mirrors (`MESH_INPUT_KINDS`,
   `MESH_SUPPORTED_RENDER_MODES`, a 36-entry `DISPLAY_MODE_ALIASES` copy of
   `normalizeDisplayMode`, scattered per-format rejections). One mirror is
   already factually wrong: section mode is rejected for meshes as "requires
   STEP topology", but `sectionSegments` slices raw meshData and is
   format-agnostic — decide section-for-meshes on merit and reject (if at
   all) with an honest policy message. Fix: a data-only module in cadjs
   (per render format/kind: render modes, display modes + alias map,
   selectors, stepParameters, exploded, section, projections — implicit is
   perspective-only — and sceneScale) emitted by `bundle-cad.sh` as JSON
   beside `snapshot-render.js` (so `bundle.sh --check` catches staleness);
   the Python CLI validates from the vendored JSON and keeps only error
   text; `SceneBackend.capabilities` (Phase 1) derives from the same table.
   Capability flips then *relax* CLI validation (delete a rejection) instead
   of growing a second mirror.
3. **Python CLI gains `.implicit.js` input** driven by that table; the
   `implicit-cad` skill's 20-line snapshot shim re-points at the unified
   tool; the standalone implicitjs Node snapshot CLI (~980 lines, duplicate
   size-profile tables and playwright driver) is retired for skill use.
4. **Structure the Python resolvers for it** (do this in the PR #139
   reimplementation): one `normalize_common_job(...)` (the mesh resolver's
   tail is a ~40-line near-verbatim copy of the STEP resolver's) + a
   `KIND_RESOLVERS` table carrying the capability metadata; an implicit kind
   becomes one table entry with an implicit `resolved` payload (module URL).

PR #139 reimplementation notes (it must be redone on the post-merge
`release/0.4.0` tip — its diff does not apply to this branch's tree): carry
its tests + debug plumbing verbatim, and fix in the redo: (a) `--debug`
output never reaches the printed `--json` result (merge `resolved.debug` into
the emitted result; test through `print_render_result`); (b) job-level
`display` JSON bypasses the closed-set value validation (validate in
`resolve_render_job` before the kind split); (c) echo `projection` per
rendered output (an explicit position/target camera forces the perspective
camera per-output, so a job-level echo misreports); (d) gate
selector/display-edge runtime loads on `sourceIsStep(kind)` (direct meshes
currently download twice and null out via doomed GLB parses); (e) the
advertised cache-key fix is upstream — what #139 adds is the pinning test.

### Phase 1 — SceneBackend seam (split into 1a/1b/1c; one blame surface each)

The only genuine rendering difference between the two viewers is one line in
the frame loop:

```
// mesh
renderer.render(scene, camera)
// implicit
updateImplicitCadMaterialUniforms(material, camera, w, h)   // feed camera as uniforms
renderer.render(shaderScene.scene, screenCamera)            // fullscreen quad + ortho screen-camera
```

Everything else the implicit component does (renderer/controls setup, RAF
loop, interaction/idle pixel-ratio quality, keyboard orbit, view planes,
frame insets, screenshot, perspective, resize, auto-zoom) re-implements
`useViewerRuntime`.

**Interface** (define as a documented plain-object contract in `implicitjs`,
re-exported via cadjs; amended from the original sketch with seams the two
implementations already disagree on):

- `createRenderer(options)` / `rendererOptions` — implicit needs
  `preserveDrawingBuffer:true` (canvas-crop screenshots) while mesh uses
  `createCadWebGlRenderer` (tone mapping/shadows/localClipping) with
  composite re-render screenshots; a hardwired config breaks one of them.
  If Phase 1c converges implicit onto composite screenshots, record that
  decision here — it obviates preserveDrawingBuffer.
- `attach(runtime)` — scene assembly; mesh: lights/groups/grid/background;
  implicit: `createImplicitCadFullscreenScene` + own
  `THREE.OrthographicCamera(-1,1,1,-1,0,1)` screen camera (the factory
  returns `{scene, material, quad, shaderKey, dispose}` — key is `quad`, no
  screenCamera in the return) + `compileAsync` warmup re-arm.
- `renderFrame(runtime) -> { rendered }` — implicit legitimately skips
  presenting while the shader compiles (`shaderSceneReady` gate); the shell
  and screenshot paths must be able to observe "did not present" or they
  capture stale buffers.
- `updateModel(runtime, model, opts)` — implicit: shaderKey compare → dispose
  + recreate + re-arm warmup (no in-place shader swap exists).
- `getBounds()` **plus `onBoundsChanged` notification** — implicit bounds
  refine asynchronously after CPU SDF sampling (`refineImplicitFit`);
  pull-only bounds would leave auto-zoom stale.
- `resolvePixelRatio({ interacting })` — mesh uses idle/interaction caps + a
  screen-space-line-count heuristic; implicit uses graphics-settings
  resolution scale driven from a React effect today.
- `dispose()`; `capabilities` (derived from the Phase H table).
- Context-loss recovery is a shell concern (mesh has
  `webglcontextlost/restored` handling + `runtimeResetToken`; implicit has
  none today) — backends must be re-attachable after restore.

**1a — extract the mesh backend, behavior-preserving.** Generalize
`useViewerRuntime` to take a backend; move its hardwired lights
(`useViewerRuntime.js:179-223`), scene groups (:225-236), renderer config
(:157-165), grid/background, and the render call (:367) into the mesh
backend. Promote the three accepted-but-never-passed hook params —
`onManualCameraInteraction`/`onViewportResize`/`onContextLost`(/`onContextRestored`),
`useViewerRuntime.js:69-71`, invoked at :293/:429/:462 — into the documented
shell→host contract instead of inventing parallel seams. The mesh backend may
stay *physically* in `viewer/` initially, but contract-conforming and
React/DOM-free so relocating to cadjs later is a file move. Zero expected
visual diff — verify with the baseline harness. The `CadViewer` →
`useViewerRuntime` call site (`CadViewer.js:~2736`) injects ~50 params; only
~8 are viewportCameraKit helpers importable directly; the rest
(stepCameraTransition engine, getPixelRatioCap, applyCameraFrameInsets,
clearSceneGroup, dispose helpers, applySceneBackground, updateGridHelper,
unmemoized closures) must be extracted into shared modules or the backend.
Note: the hook publishes a ~66-field runtime blackboard
(`useViewerRuntime.js:~557-624`) that CadViewer reads pervasively and later
grafts onto (`runtime.cadScene` at CadViewer.js:~3226) — the mesh backend's
attach must keep populating all of it, and unit tests won't catch a miss.
`getScreenSpaceLineMaterialCount` already peeks
`runtime.cadScene.runtime.screenSpaceLineMaterials` — the interface should
subsume this second runtime concept, not add a third. The two viewers also
still carry divergent `stepCameraTransition` engines (mesh: selectable
easing, ortho halfHeight/zoom lerp, inset reapply, no completion emit —
the shell loop emits per active frame; implicit: fixed easing + completion
emit) — converge on the mesh engine + shell-loop emit when extracting.

**1b — implement the implicit backend in implicitjs** (attach/renderFrame/
updateModel per the contract above; implicit-only extras — compileAsync gate,
resolution scale — live in the backend) and adopt it **inside the existing
`ImplicitCadViewer` shell** (keep its component and remount lifecycle for
now). `updateImplicitCadMaterialUniforms(material, camera, w, h)` is not
THREE-first (reads camera.position/matrixWorld/projectionMatrixInverse, sets
uResolution) — easy to mis-wire.

**1c — rewrite `ImplicitCadViewer` to mount `useViewerRuntime` with the
implicit backend**, deleting its bespoke renderer/controls/RAF/frame-inset/
screenshot/perspective code (~600–800 lines). Framing techniques differ:
mesh uses `camera.setViewOffset` for frame insets; implicit shears
`projectionMatrix.elements[8]/[9]`. Converge on the mesh technique and verify
the raymarch framing visually (the shader reads `projectionMatrixInverse`, so
setViewOffset should carry through). Dead plumbing to prune while here:
unused `BASE_VIEWER_THEME` param (:54).

### Phase 1d — fit/framing consolidation (new; the actually-triplicated math)

The camera kit contains no fit math. Three copies exist: mesh viewer
`cadjs/lib/viewer/autoZoom.js` (autoZoomFrameForBounds/fitDistanceForRadius),
headless `cadjs/common/renderOptions.js:~405-482`
(frameHalfHeightForView/fitOrthographicCamera/fitPerspectiveCamera — where
the known snapshot auto-fit gaps live), and the implicit path (`runAutoZoom`
+ `estimateImplicitCadFrameBounds(Async)`). Consolidate into one module in
`implicitjs/common` (the only placement headless implicit can reach under the
one-way dependency rule), consumed by all three. While here, reconcile the
**default view direction** (kit `DEFAULT_VIEW_DIRECTION [2.1,-1.65,1.08]` vs
headless `iso [1,-1,0.8]`) as a deliberate product decision — one canonical
default shared by viewer and snapshot — and derive the kit's
`VIEW_PLANE_FACES` directions from `RENDER_CAMERA_PRESETS` (keep only
labels/tooltips viewer-local). This phase, not kit relocation, is what gives
PR #139 and implicit snapshots the *same framing code* as the viewer.

### Phase 2 — perspective format convergence (rewritten)

- Converge implicit onto the mesh perspective snapshot format
  (`cadjs/lib/perspective` + `readScopedPerspectiveSnapshot`), **deleting**
  `IMPLICIT_CAMERA_VERSION` and the `{implicit:true}` guard outright.
  **No localStorage migration** — the original premise was false: every
  producer path already strips the implicit payload to the mesh shape before
  storing (`clonePerspectiveSnapshot` at the CadWorkspace emit;
  `normalizeTabCameraSnapshot` keeps only position/target/up/zoom on the
  persistence path), so no implicit-format state exists anywhere to migrate,
  and normalize-on-read handles hypothetical stale data anyway.
- **Call it what it is: a silent bug fix.** Because producers strip the very
  fields the implicit guard requires, the implicit restore branch is dead
  code today — implicit models *always* auto-fit on mount/tab-return. After
  convergence, stored cameras will start applying. Expected user-visible
  change; cover it in the visual pass (implicit model A: frame a view, switch
  tab, return — camera should restore instead of re-fitting).
- **Definition of done includes headless paste-ability:** a viewer
  `getPerspective` payload must round-trip into snapshot `--camera`. Today it
  throws `Unsupported camera fields: projection, modelKey, sceneScaleMode,
  coordinateSystem` (strict `CAMERA_SPEC_KEYS` validation in
  `implicitjs/common/camera.js`). Add a `perspectiveToCameraSpec` helper next
  to `clonePerspectiveSnapshot` that strips the metadata keys and maps
  `projection` into the job's `display.projection` (bare key-stripping is not
  enough: the headless path infers perspective from explicit position specs,
  so a stripped orthographic view would silently render perspective). Add a
  round-trip test: viewer getPerspective JSON fed as `--camera` reproduces
  the framing headlessly.

### Phase 3 — collapse to one component

Fold `ImplicitCadViewer` into `CadViewer` selecting the backend by
`renderFormat`. `CadRenderPane` stops branching mesh-vs-implicit (keep DXF-2D
routing to `DxfViewer`; FileSheet inspectors stay format-specific).
**Lifecycle change, be explicit:** implicit is remount-per-model today
(`key={implicit:${activeModelKey}}` in CadRenderPane) while the mesh runtime
persists across models — after the fold, the in-place model-swap path is the
*only* transition path. Enumerate and reset in `updateModel`/`dispose` the
per-model state remounting currently clears for free (shader-compile re-arm,
auto-zoom attach state, quantized-bounds keys, framing limits from
model.radius, per-model camera application). Test: switch implicit model
A→B→A without remount. Acceptance criterion to claim as a win: implicit
gains the shell's WebGL context-loss recovery (it has none today).

### Phase 4b — `themeSettings.js` / `displaySettings.js` dedup (scope-tightened)

Not a copy-paste like `camera.js`. `cadjs/common/themeSettings.js` (~1690
lines) extracted CAD edge constants into `cadjs/common/displaySettings.js`;
`implicitjs/common/themeSettings.js` (~1717 lines) still inlines them.
**Scope rule (consumption-based):** a primitive moves into implicitjs only if
implicitjs's own runtime imports it. The theme-preset/theme/environment
core qualifies (implicitjs's renderer deep-imports
themeSettings/renderOptions/stageTheme/surfaceMaterials). The mesh/STEP-only
superstructure does **not**: display modes, exploded-view machinery, and the
651-line stage floor/grid module stay in cadjs even where that means
splitting a module. "Fold the trimmed-subset duplicates
(`implicitjs/lib/viewer/{stageTheme,surfaceMaterials}.js`)" means sharing the
seed/subset helpers — not relocating cadjs's stage machinery into the SDF
package (which ships wholesale inside the implicit-cad skill bundle). Many
cadjs modules import displaySettings; lean on the package unit tests.

### Phase 5 — progressive feature unlock (after the shared shell exists)

With the shell + capability table, selectively enable for implicit where it
makes sense: projection toggle, view planes, grid/stage backdrop,
clip-plane/section, annotated screenshots, and the cross-format camera-action
context menu (unlocks the already-landed implicit zoom ref methods; emit a
background right-click from the implicit/mesh/DXF viewers + a minimal
camera-action menu for non-STEP formats). **Each flip lands in the
package-level backend/capability table so the snapshot CLI's validation
relaxes in the same change** — a capability unlock that only touches the
viewer re-opens the drift this plan exists to close.

## Deferred / recorded decisions

- **playwright rides the cadjs dependency cone** (implicitjs declares it as a
  regular dep for its Node CLI only; no install script, so it is dead weight
  rather than a download hazard). When Phase H retires the implicitjs CLI for
  skill use, move playwright out of `dependencies` (the vendored skill
  runtime install must be accounted for). Recorded so the cone growth is a
  choice, not an accident.
- **Not adopted:** pre-adding `cadjs/implicit/{snapshot,headlessRenderEntry,…}`
  re-exports (the headless dispatch is cadjs-internal and imports implicitjs
  directly; re-exporting the side-effectful headless entry as a consumer
  subpath is a footgun); npm workspaces (collides with the dual
  develop-symlink/main-copy layout and per-lockfile CI caching); lockfile
  assertions in the boundary test (npm ci sync validation + the
  import-exercising tests already fail loudly).

## Bundling / release note

Generated bundle copies (`skills/*/scripts/*/packages/*`, `plugins/*`, and on
`main` the `viewer/packages/*` copies) are regenerated from `packages/*`
source with `scripts/bundle/bundle.sh` (requires `rsync`). Run
`scripts/bundle/bundle.sh --check` before handoff; regenerate when a
production-output task requires it. `bundle-cad.sh` resolves cadjs's
implicitjs imports hermetically (NODE_PATH) — keep it that way when adding
the implicit backend to the snapshot bundle. Do not bump `VERSION`
during development.

## Key file map

- `viewer/src/client/components/CadViewer.js` — mesh viewer (reference)
- `viewer/src/client/components/ImplicitCadViewer.js` — implicit viewer (to fold in)
- `viewer/src/client/components/viewer/hooks/useViewerRuntime.js` — the interactive shell to generalize
- `viewer/src/client/components/viewer/viewportCameraKit.js` — shared camera helpers
- `viewer/src/client/components/workbench/CadRenderPane.js` — format → viewer routing
- `viewer/scripts/capture-render-baselines.mjs` — visual baseline harness (phase gate)
- `packages/cadjs/src/implicit/*` — cadjs → implicitjs re-export layer
- `packages/cadjs/src/common/{renderMeshScene,renderOptions,headlessRenderEntry,headlessOrbitFrames}.js` — headless mesh path
- `packages/implicitjs/src/common/{implicitHeadlessRenderEntry,implicitHeadlessOrbitFrames}.js` — headless implicit path (Phase H merges these into the unified runtime)
- `packages/implicitjs/src/lib/implicitCad/render.js` — implicit shader scene API
- `skills/cad/scripts/snapshot/__main__.py` — snapshot CLI (Phase H: KIND_RESOLVERS + vendored render-contract JSON)
- `scripts/bundle/skills/bundle-cad.sh` — snapshot runtime bundler (emits the render contract in Phase H)
