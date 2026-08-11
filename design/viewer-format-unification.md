# Viewer format unification: capabilities, not identities

## 0. Execution status

| Phase | Status |
|---|---|
| U0 registry + content signal + ratchet | **DONE** `f4d9495c` |
| U1 projection as a viewport trait | **DONE** |
| U2 one params/animation surface | **DONE** `3826d4da` |
| U3 context menu + camera actions everywhere | **DONE** `bcaf9f7a` |
| U4 theme wiring fixes + capability table | **DONE** `b4725fae` |
| U5 loading/alerts/artifact state | **DONE** `7dcbd2e1` |

Identity-check count: **93 → 34**, predicate calls **→ 3**, locked in by
`tests/python/global/test_viewer_format_capability_policy.py`. `FloatingToolBar`,
`CadRenderPane`, `CadViewer`, `viewerAlerts`, `entryIconKind`, `entryIconStatus` and
`CadWorkspaceHome` are at **zero** and asserted so. What remains is deliberate:
`useCadAssets` is the loader, and `stepArtifactStatus` speaks STEP package vocabulary.

### What U0/U1 found that the plan did not predict

- **Upstream's "Orbit for DXF" (`5d5bc3ae`) was incomplete.** It enabled the button while
  FOUR other format checks kept preview mode unreachable: the workspace handler bail, the
  pane's `previewMode={dxfMode ? false : previewMode}`, and an effect that force-exited
  DXF from preview. This is the thesis in miniature — one feature, four hand-maintained
  gates. Orbit is now verified working on DXF, STL, STEP and implicit.
- **`normalizeRenderFormat` resolves unknown formats to STEP.** Correct when picking a
  loader, catastrophic for capabilities: an unrecognised entry would have inherited
  STEP's full set (parts, topology, clip, artifact gating), failing open on every one.
  `renderCapabilities` does its own normalization and falls back to a conservative row.
  Caught by the registry's own test, not by review.
- **The e2e sweep paid for itself immediately**, catching a temporal-dead-zone crash
  (`selectedViewportContent` referencing `effectiveRenderFormat`, declared 500 lines
  later) that blanked all six formats and that both the production build and the 292 unit
  tests passed.
- **CORRECTION — there is no ortho "first-fit off-centre bug".** U1 step 4 as originally
  written was wrong. Measured: the apparent off-centring was an artifact of the sweep's
  900px clip over a 1440px viewport, plus the frame insets that deliberately bias a model
  left when its file sheet is open. With the pane measured properly, STL sits at +28px of
  centre (no sheet) and STEP/implicit at ~-163px (sheet open, inset applied) — all
  correct. Nothing to fix.

### What U2–U5 found that the plan did not predict

- **U0 half-shipped the toolbar Play button.** It flipped the gate to the `animations`
  capability but left the button fed from STEP state, so an implicit's clips still could
  not be played — the button was hidden, because `stepAnimationAvailable` is false for a
  format with no sidecar. A capability without the data behind it is not a capability.
  Fixed in U2 and A/B-measured.
- **The viewport display/projection control had been dead since `f75c2696`
  (2026-07-06).** Its prop chain survived — CadWorkspace → CadRenderPane → CadViewer,
  gated on `isStepView` — so projection *looked* STEP-gated when nothing rendered it at
  all. Deleted in U3 along with the orphaned `DisplayProjectionControl`.
- **`isStepView` was four capabilities wearing one name** (parts, topology, displayModes,
  sidecar params). That is why every one of its ~15 uses had to be re-read to work out
  which sense was meant. Gone as of U3.
- **U4's wiring fix was the smaller half.** `applyImplicitLightingUniforms` did read the
  wrong fields, but fixing only that would have changed nothing: implicitjs's OWN
  `normalizeThemeSettings` did not know `lighting.fill` or `lighting.rim` existed and
  dropped them before any uniform could read them. The theme schema is duplicated across
  `packages/cadjs` and `packages/implicitjs` (the latter may not import the former), and a
  field added to one is silently disabled for the other.
- **`artifactManaged` does NOT mirror the server's `owns_entry`,** despite the note U0
  wrote saying it must. The server owns implicit entries too — it builds their packages
  for export and snapshot — but an implicit raymarches live and must never block on that
  build. Corrected in U5; the old note would have led someone to make implicit wait for a
  build it has no use for.
- **The "DXF auto-fit frames its drawing far too small" bug was not a camera bug.**
  `parseHatchEntity` read HATCH seed points as boundary vertices; two seeds 62 m off a
  1.8 m sheet inflated the drawing's bounds 35×, and auto-fit was faithfully framing them.
  Fixed in `72daa145` (bounds 63817×21822 mm → 1879×1979 mm; sweep coverage 0.0055 →
  0.0685 against a 0.005 blank threshold, so the standing gate had been one stray seed
  away from failing for an unrelated reason).

### Open

- **Background parity drift in four themes** (cinematic 7.0, clay-sunrise 5.4, pink 4.7,
  blue 4.5, out of 255), found by the U4 conformance harness. Ruled out by measurement:
  the U4 lighting work, the implicit shader's own gradient ramp (the viewer composites the
  raymarch over the shared stage, so that ramp is not what is on screen), and the
  environment map. Budgeted per theme so it cannot grow or spread.
- **The implicit's two backdrops disagree.** The shader's own ramp (headless/standalone
  renders) is a `smoothstep`; the canvas path the mesh renderer bakes is a linear ramp
  between stops. Unmeasured in the headless path.

Execution plan. The goal, in the owner's words: unify, standardize and reuse as much
viewer logic across file formats as possible, **so that an improvement to one file
format is inherited by all of the others**. The mechanism: viewer code stops asking
"is this format X?" and starts asking "can this format do X?" against a single
capability registry, with a policy test that stops the old pattern growing back.

Builds on `release/0.4.0` after PR #195 (implicit as a shared render type,
`design/implicit-shared-viewer-integration.md`) and the perf/consistency batch
(`design/implicit-render-performance.md`). Written 2026-08-09.

## 1. The failure mode, with receipts

The viewer already HAS one shared component stack — `CadViewer`, `useViewerRuntime`,
one toolbar, one sheet shell. What is not shared is the **gating**: every feature is
wired per-format by identity checks, so every feature must be hand-enabled once per
format, and every format added multiplies the surface. Three incidents in one week:

- **Orbit was hand-enabled twice.** Implicit's Orbit/screenshot buttons were dead
  because the gate asked `!selectedMeshData` (fixed in `2c5939bd`); days earlier DXF's
  Orbit had been gated off separately and was fixed by `5d5bc3ae`, whose own commit
  message says it: *"The Orbit tool was gated off for DXF for no reason."* Same
  button, same class of bug, two hand-fixes.
- **Implicit export posted to a route the server does not implement** (405) because
  the format grew its own export path instead of joining the shared one. Fixed in
  `2c5939bd` by deleting the parallel path — the shared route already supported it.
- **Projection is a theme trait that four of five formats ignore.** The default
  workbench theme declares `projection: ORTHOGRAPHIC` (`themeSettings.js:1099`); only
  STEP honors it (`CadRenderPane.js:370`). Measured: with the gate removed, STL/3MF/
  DXF render correctly in ortho **with zero code changes** — the dual-camera runtime
  is already format-agnostic. Only implicit actually fails (shader, §U1).

The scale of the pattern (counted on this tree, non-test client code):
**93 `RENDER_FORMAT.X` identity checks** (50 in `CadWorkspace.js` alone, 13 in
`viewerAlerts.js`), **9 independent `xxxMode` boolean derivations**, **8 per-kind
switches**. Each is a place a fourth format must be hand-added and a place an
improvement fails to propagate.

What IS already unified, and proves the target architecture works: the camera/
controls/zoom/fit stack, the stage/theme scene, the render-loop tuning hooks
(`renderOnDemandOnly`, `resolveExtraPixelRatioCap`, `idleQualityDelayMs`,
`onIdleQualityRestore` — opt-in, inert for non-installers), the `/__cad/export`
route, and the zoom pill / screenshot / orbit / pan / draw gates as of `2c5939bd`
(inline `viewportContent` branches — correct behaviour, wrong mechanism; U0 replaces
the mechanism).

## 2. Target architecture

Three contracts, all mostly extant, none written down:

1. **Capability registry** (new, the keystone): one frozen data table, keyed by
   render format, holding every fact the client currently derives from format
   identity. Pure data in cadjs (non-React, like `fileFormats.js` which already
   hosts format-keyed maps).
2. **Content signal** (generalizes `2c5939bd`): one `selectedViewportContent` derived
   once in `CadWorkspace` from the registry's `content` field — the answer to "is
   anything on screen?" for every consumer (toolbar gates, CTA, preview mode, alert
   blocking, view cube). Kills the `selectedMeshData`-vs-`selectedImplicitModel`
   branch at every call site.
3. **Render-backend contract** (extant, undocumented): `CadViewer` owns camera,
   controls, stage, overlays, screenshots; a backend (mesh compose, implicit
   raymarch, DXF fold preview, robot loader) owns geometry — it consumes content,
   publishes bounds, and may install the opt-in loop-tuning hooks. New formats
   implement a backend + declare a registry row; they do not touch the shell.

### Registry sketch (fields from the audit, `packages/cadjs/src/lib/renderCapabilities.js`)

```js
export const RENDER_CAPABILITIES = Object.freeze({
  [RENDER_FORMAT.STEP]: {
    content: "mesh",            // which loaded object is the viewport content
    sheetKind: "step",
    sceneScale: "cad",
    themeProjection: true,      // honor themeSettings.projection (U1 sets all true)
    planView: false,            // 2D/3D top-down lock toggle
    tools: { select: true, pan: true, draw: true, orbit: true, screenshot: true },
    parts: true, topology: true, exploded: true, displayModes: true, clip: true,
    params: "sidecar",          // "sidecar" | "module" | null
    animations: true,
    artifactManaged: true,      // mirrors server owns_entry — keep the mirror note
    exportFormats: ["step", "3mf", "stl", "glb"],
  },
  // stl / 3mf / glb: content mesh, sheetKind mesh, everything else minimal
  // dxf: planView true, draw true, exportFormats per source kind
  // implicit: content "implicit", params "module", animations true, graphics tab
  // urdf / srdf / sdf: content "robot", sceneScale "urdf", posePicker...
});
```

Exact field list is settled during U0 by inventorying the 93 call sites; the table
above names the ones this audit already identified. Rules:

- A capability is added when the SECOND format needs it, not speculatively.
- Format-specific *content* (DXF bends/material editing, STEP tree, URDF joints,
  implicit graphics tab) stays format-specific — sections plugged into the shared
  sheet shell, as today. The registry gates *which* sections mount; it does not
  absorb their internals.
- The registry is data, not behaviour. Behaviour lives in the shared shell (one
  implementation per capability) or in the backend (one per format).

### The enforcement mechanism

A repo policy test (pattern: `tests/python/global/test_models_directory_policy.py`)
greps non-test client code for `RENDER_FORMAT.` member checks and mode-boolean
derivations outside an explicit allowlist (the registry itself, `fileFormats.js`,
the render backends, `useCadAssets` loader arms) and **ratchets**: the count may only
decrease. Without this the 93 grows back; with it, every phase's deletions are
locked in. This is what makes "an improvement to one is inherited by all" a property
of the codebase instead of a code-review aspiration.

## 3. Phases

Each phase is independently shippable and gated. U0 is the keystone; order after it
is by user-visible value over effort.

### U0 — registry + content signal + policy ratchet

1. Author `renderCapabilities.js` from the call-site inventory; port
   `CadRenderPane`'s five mode booleans, `FloatingToolBar`'s four, the
   `viewerPickModeForRenderPane` boolean pile, `fileSheetSections`' kind switch, the
   two export-format maps (`StepExportDropdown.js`, `FileAccessContextMenu.jsx` —
   both re-derive kind→formats today; collapse into one
   `exportFormatsForEntry(entry)` in `modelExport.js` reading the registry), and
   `CadWorkspace`'s zoom-pill / preview / draw-mode / loading-label gates.
2. Derive `selectedViewportContent` once; delete every inline
   `implicitMode ? selectedImplicitModel : selectedMeshData` branch.
3. Land the policy ratchet test with the starting count baked in.
4. Write `viewer/docs/render-types.md`: the backend contract (ownership split, the
   four tuning hooks, bounds publication) and the registry field reference. The
   settings-UI doc (`viewer/docs/settings-ui.md`) is the precedent for binding docs.

No behaviour change intended; gate is the full e2e format sweep (one load +
screenshot per format — formalize the ad-hoc harness from the perf batch as
`viewer/scripts/e2e-format-sweep.mjs`, since every later phase gates on it),
all suites green, ratchet baseline recorded.

### U1 — projection becomes a viewport trait (first consumer)

The standing theming question, answered for every format at once:

1. `cadProjection = normalizeCameraProjection(themeSettings?.projection)` for every
   format with `themeProjection: true` — which U0 sets true across the board.
   Measured on this tree: STL/3MF/DXF need nothing else.
2. Implicit ortho: `uOrthographic` uniform + ray branch in the shader (origin from
   the unprojected image-plane point, direction = camera forward, ~15 lines in
   `implicitCadFragmentShader`). Same care as the `uPaintBackground` change: default
   0 = perspective so snapshot/export are byte-identical; bundled runtimes
   regenerate via `scripts/bundle/bundle.sh`.
3. **`planMode` forces orthographic.** Its own comment declares it "a generic
   top-down camera lock, reusable by any model, not a DXF feature" — but a
   perspective plan view foreshortens off-centre. This is the strongest correctness
   argument in the whole plan.
4. Fix the ortho **first-fit off-centre bug** found while measuring: with a non-STEP
   format opening ortho, initial framing lands off-centre — the first fit appears to
   run before the projection sync. Diagnose ordering between
   `syncRuntimeCameraProjection` and the first `zoomRuntimeToBounds`.
5. Generalize the 2D/3D toggle off `selectedEntryIsDrawing` onto the `planView`
   capability (still only DXF-enabled by default; flipping it for another format
   becomes a one-field change).

Gate: ortho + perspective screenshot per format; implicit 47-model sweep in both
projections; zoom-percent pill sane under ortho (it reads half-height, not
distance); STEP pixel-unchanged.

**Decision required (product):** honoring the theme flips STL/GLB/3MF/DXF's default
look to orthographic, because the default theme is ortho and STEP already renders
that way. Recommended: accept — STEP is the reference implementation and the theme
is currently lying for every other format. Alternative: flip the default theme to
perspective, which changes STEP's default look instead. One of the two moves; the
plan assumes the first.

### U2 — one parameter/animation surface

Two parallel systems exist: STEP `.step.js` sidecars (toolbar Play at
`FloatingToolBar.js` `showStepAnimationPlay` — gated `=== RENDER_FORMAT.STEP` — plus
the Parameters sheet section) and implicit in-module definitions (same sheet section
id already, but animation driveable only from the sheet, and its own copy/paste
handlers in `CadWorkspace`). Unify the **consumer surface**, not the stores:

1. Registry exposes `params`/`animations`; toolbar Play gates on "has animation
   clips", whichever store backs it.
2. One parameter-values copy/paste/reset handler set keyed off the active runtime.
3. The two stores stay as they are (they drive different recompute pipelines);
   merging them is not required for inheritance and is deferred until a third
   parameterized format exists.

Gate: Play/Pause works from the toolbar on an implicit animation and a STEP
animation; params sheet unchanged on both.

### U3 — context menu and camera actions everywhere

`openGlobalViewerContextMenu` bails unless `isStepView` (`CadWorkspace.js`), so
Reset Zoom / Zoom to fit exist for STEP only — and the implicit
`zoomToFitSelection` fallback shipped in PR #195 is unreachable dead code. Camera
actions are viewport-level, not format-level:

1. Global right-click menu for every format: camera section always; parts/topology
   sections gated on registry capabilities (`parts`, `topology`) instead of
   `isStepView`.
2. This un-strands `zoomToFitSelection` and gives every format the same
   right-click affordances the STL/implicit audit flagged as missing.

Gate: menu opens with camera actions on all six format families; STEP menu
unchanged; part actions absent where `parts: false`.

### U4 — theme contract: wiring fixes + conformance harness

The audit found the implicit renderer diverges from the theme in ways that are pure
wiring, plus structural gaps that should be *declared* rather than silently
dropped:

1. Wiring fixes in `applyImplicitLightingUniforms`: rim from `lighting.rim`
   (currently hardcoded to `DEFAULT_LIGHTING_RIG`), fill from `lighting.fill`
   (currently repurposes `lighting.spot`), bounce stays `lighting.point`. Verify by
   A/B screenshots across all 8 themes on 3 models — this changes implicit pixels
   by design; the gate is that theme switches now *track the mesh look*, judged on
   the same-scene comparison.
2. **The render-contract capability table** — deferred from the renderer-
   consolidation effort (PR #138/#143) and resurrected here as a section of
   `viewer/docs/render-types.md`: for every theme field, per render type: honored /
   approximated (env→flat ambient) / unsupported (PBR roughness-metalness-clearcoat-
   opacity, env reflections, per-part fill cycling — all structural for a raymarched
   SDF and explicitly out of scope).
3. Conformance harness: one fixed scene per format × all themes, assert background
   pixel-identity (already proven for implicit-vs-STL) and record surface deltas as
   baselines. Runs from the e2e sweep script.

### U5 — loading, alerts and artifact state behind the registry

The deepest remaining format arms: `useCadAssets`' per-format loaders,
`viewerAlerts.js`' 13 format checks, `ARTIFACT_MANAGED_SOURCE_FORMATS`, per-format
loading labels, `entryIconStatus`/`stepArtifactStatus` gating. Standardize the
*interfaces*: `loadViewportContent(entry)` per backend, `buildViewerAlert(...)` and
`loadingLabel` as registry-adjacent per-type functions, `artifactManaged` as a
registry field (keeping the "mirrors server `owns_entry`" invariant note and its
test). The loader *implementations* stay per-format — they are genuinely different
work.

Gate: e2e sweep incl. artifact-build flows (fresh STEP and DXF build from a clean
`__cadgen__`), unchanged loading/alert UX per format, ratchet strictly lower.

### U6 — horizon (separate efforts, recorded so they are not re-litigated)

Not started; U0–U5 are complete. Three items gained evidence on the way through:

- **The robot family was carried along, not audited.** URDF/SRDF/SDF are structurally
  inside the shared stack but functionally the thinnest render type: no headless render
  path at all, no export, no structure panel despite a URDF being a link tree, no display
  modes, and a load ~20× slower than a mesh. The sweep had no robot fixture until it was
  added here, which is how it stayed invisible. Own plan:
  `design/viewer-robot-parity.md`.

- **The theme schema is duplicated** across `packages/cadjs/src/common/themeSettings.js`
  and `packages/implicitjs/src/common/themeSettings.js`, because implicitjs may not import
  cadjs. U4 proved this silently disables fields (`lighting.fill`, `lighting.rim`).
  Extracting the schema to a third dependency-free package would close the class; the
  conformance harness catches it meanwhile.
- **The two implicit backdrops** (shader ramp vs baked canvas gradient) belong with the
  headless-snapshot unification below, since that is where the shader ramp is what paints.

- **Per-file settings persistence**: three mechanisms exist (shared camera slice,
  `slices.implicit` params/animation, and the new DXF per-file sessionStorage from
  `546057a5`). Fold per-file settings into `fileSessionState` slices keyed by sheet
  kind.
- **Headless snapshot backends**: `runHeadlessRenderJob` still forks mesh vs
  implicit; with the viewer compositing over the shared stage, the fork is the last
  parallel render stack. Unifying it touches the snapshot CLI contract — own
  design doc when taken up.
- Merging the STEP/implicit parameter stores (see U2.3).

## 4. Non-goals

- No changes to server-side producers or package formats (the spec-table
  architecture there is already registry-shaped).
- No PBR/environment-reflection work in the raymarch shader (structural; declared
  in the U4 table instead).
- No removal of format-specific sheet content or tools where the capability is
  real (DXF bends, STEP topology, URDF pose picker, implicit graphics tab).
- No new abstractions for single-format capabilities (rule: second consumer
  creates the capability).

## 5. Standing verification for every phase

`viewer/scripts/e2e-format-sweep.mjs` (formalized in U0): Metal-backed Chromium,
loads one fixture per format family (+ all 47 implicits in the full variant),
screenshots, non-blank + no-pageerror assertions; perf spot-check from the
benchmark harness in `design/implicit-render-performance.md` §3 on planetary-gear;
`npm --prefix viewer run test`, `packages/cadjs`, `packages/implicitjs` suites;
`scripts/bundle/bundle.sh --check` + `scripts/dev/setup-symlinks.sh --check` when
the shader or bundled runtimes are touched; and the U0 policy ratchet, which is the
phase-exit criterion that actually encodes the goal.
