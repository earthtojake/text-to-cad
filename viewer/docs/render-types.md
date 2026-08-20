# Render types: capabilities and the backend contract

Binding for viewer work that touches more than one file format. The rule this document
exists to enforce:

> Viewer code asks what a format **can do**, never what it **is**.

Every `renderFormat === RENDER_FORMAT.X` check is a place a new format must be
hand-added, and a place an improvement to one format fails to reach the others. That is
not theoretical. The Orbit button was gated off for implicit and for DXF independently and
had to be fixed twice; when it was finally enabled for DXF, the button still did nothing
because **four** separate format checks stood between it and preview mode (the toolbar
gate, the workspace handler bail, the pane's `previewMode={dxfMode ? false : ...}`, and an
effect that force-exited DXF from preview). Implicit meanwhile grew an entire parallel
export path to `/__cad/implicit-export`, an endpoint the server does not implement.

## The capability registry

`packages/cadjs/src/lib/renderCapabilities.js` — one frozen table, keyed by render
format. Pure data: no behaviour, no imports beyond the format enum.

| Capability | Meaning |
|---|---|
| `content` | Which loaded object is the viewport's content: `mesh`, `implicit`, `robot`. Resolved once into `selectedViewportContent`. |
| `assetKind` | Which asset the viewer LOADS: `mesh`, `drawing`, `implicit`, `robot`. Not the same question as `content` — a DXF loads a drawing and renders it through the mesh viewport, so it shares the viewport but not the loader. |
| `iconKind` | The file-list glyph. |
| `sheetKind` | Which file-sheet section set mounts. |
| `label` | User-facing format name (status chips, sheet titles, loading labels). |
| `rebuildCommand` | The manual rebuild command shown on a build-failure card, or `""` when the viewer builds it or the file IS the asset. |
| `sceneScale` | `cad` or `urdf`; picks the scene-scale profile. |
| `tools` | `select`, `pan`, `draw`, `orbit`, `screenshot`. Orbit and screenshot are true for everything — they act on the viewport, not the geometry. |
| `parts` | Per-part selection, hiding, isolate, assembly tree. |
| `topology` | Face/edge/vertex references. Implies `parts`. |
| `exploded`, `displayModes`, `clip` | STEP-tier display transforms. |
| `planView` | Offers the 2D/3D top-down lock. |
| `themeProjection` | Honours `themeSettings.projection`. |
| `params` | `sidecar` (`.step.js`), `module` (in-`.implicit.js`), or `null`. |
| `animations` | Has animation clips, so transport controls apply. |
| `posePicker` | Robot pose picking. |
| `artifactManaged` | Builds a package before it can render. A **subset** of `owns_entry` in `server_py/artifact.py`, not a mirror: the server also owns implicit entries (it builds their packages for export and snapshot) but an implicit raymarches live and must never wait on that build. A format listed here that the server does not own blocks forever. |
| `exportFormats` | What `/__cad/export` can produce for it. |

### Rules

- Add a capability when the **second** format needs it, never speculatively.
- An unknown format resolves to the conservative default row (everything optional off).
  Deliberately *not* `normalizeRenderFormat`, which resolves unknowns to STEP and would
  hand an unrecognised entry STEP's full capability set.
- Capabilities decide **which** panels and tools mount. Format-specific *content* — STEP's
  tree, DXF's bends, an implicit's graphics tab — stays format-specific.

## The content signal

`selectedViewportContent` in `CadWorkspace` is the single answer to "is there anything on
screen?", derived from `content`. Toolbar gates, the CTA, preview mode, the zoom pill and
alert blocking all read it. Asking `!selectedMeshData` instead is what left an implicit's
screenshot and orbit buttons permanently disabled: a raymarched model never loads a mesh.

## The render-backend contract

`CadViewer` is the shell and owns the camera, `OrbitControls`, the themed stage, frame
insets, overlays, screenshots and the imperative viewer API. A **backend** owns geometry
only:

1. **Consume content** for its `content` kind (mesh data, implicit model, robot).
2. **Publish bounds** so the shared fit, zoom baseline and zoom-percent work. The mesh
   path does this via `applyRuntimeModelBounds` after composing; the implicit pass calls
   back with declared bounds, then refined bounds once its CPU SDF scan resolves.
3. **Optionally install loop-tuning hooks** on the runtime. All are inert unless set, so
   the mesh path is unaffected:
   - `renderOnDemandOnly` — do not hold the render loop open for a whole gesture.
   - `idleQualityDelayMs` — raise the idle-restore delay.
   - `onIdleQualityRestore` — restore quality before the pixel ratio, so the expensive
     frame and the drawing-buffer reallocation do not land on the same vsync.
   - `resolveExtraPixelRatioCap` — cap resolution below the shared caps.

A backend never reaches into the camera, controls or stage. If it needs something from
them, that is a shell feature and belongs in the shell where every format gets it.

### Adding a format

Declare a registry row, implement a backend, add a fixture to the sweep. Do not touch the
shell. If you find yourself adding a format check to `FloatingToolBar`, `CadRenderPane` or
`CadViewer`, the capability you need is missing from the table.

## Enforcement

`tests/python/global/test_viewer_format_capability_policy.py` counts identity checks in
non-test client code and **ratchets**: the number may only go down. It also asserts a
growing set of files at **zero** — the toolbar, the render pane, `CadViewer`, the alert
builder, the file-list icon and status, and the home screen — since those are the surfaces
every format flows through. Lower the budgets in the same commit that removes checks.

What is left is deliberate. `useCadAssets` is allowlisted: choosing and running a loader
per format is its whole job, and the `assetKind` field names *which* loader without
pretending the implementations are the same. `stepArtifactStatus.js` keeps its checks
because STEP package error codes, the `stale` flag and the renderable-GLB fallback are
STEP vocabulary — generalising the gate without the vocabulary would show a DXF a card
about a STEP artifact. The generic build-failure card in `viewerAlerts` already covers
every artifact-managed kind.

## Standing gate

`scripts/e2e-format-sweep.mjs` loads one fixture per format against a running
viewer and asserts each draws something with no page errors:

```bash
npm run start -- --port 3245 --host 127.0.0.1   # from the models root
node scripts/e2e-format-sweep.mjs --dir <abs-models-root> [--all-implicits]
```

Run it for any change to shared viewer code. It uses `page.screenshot()` against a
Metal-backed context on purpose: a blank-but-error-free viewport is the signature failure
mode here (a shader that fails to compile, a gate that hides the geometry), sampling the
canvas with `drawImage` reports every format blank because the drawing buffer is not
preserved, and the software rasteriser hides real GPU failures. It has already earned its
keep — it caught a temporal-dead-zone crash that blanked all six formats and that the
build and unit tests both passed.

**Method warning: do not run large sweeps back to back.** Chaining full 47-model
`--all-implicits` runs (or launching several browsers in quick succession) exhausts GPU
contexts and reports large numbers of *false* blanks — a run that reported 33 blank models
reported zero on a clean run of the same build, twice. Let the previous run's browser fully
exit before starting another, and treat any mass-blank result as suspect until reproduced
from a cold start. Isolate a single suspect model rather than trusting one bulk run.

## Known non-uniformities

Recorded so they are not mistaken for bugs, and so the next person knows the cost:

- **Implicit material support is partial.** The raymarcher has a fixed BRDF: theme
  `roughness`/`metalness`/`clearcoat`/`opacity`/`emissiveIntensity` are ignored and
  environment reflections are absent (the shader samples no textures); `environment.intensity`
  is folded into a flat ambient term. Colour shaping (tint/saturation/contrast/brightness)
  does apply, via the shared `shapeSourceColor`. This one is structural, not wiring: a
  raymarched SDF has no material graph to hang those on.
- **Select is inert for DXF and implicit.** Both keep the button for a uniform toolbar
  shape; neither has pickable topology.

## Theme conformance per render type

Every theme field, and what each render type does with it. `honoured` means the value
reaches the renderer and changes the picture; `approximated` means it is folded into
something cheaper; `unsupported` means it is structurally out of reach and is *declared*
here rather than silently dropped.

| Theme field | Mesh (STEP/STL/3MF/GLB/DXF) | Implicit (raymarch) |
|---|---|---|
| `background` (colour, gradient, angle) | honoured | honoured — asserted pixel-identical to mesh by the sweep |
| `floor` (mode, colour, grid, shadow) | honoured | honoured — the implicit composites over the same shared stage |
| `projection` | honoured | honoured (`uOrthographic` + parallel-ray branch, U1) |
| `lighting.toneMappingExposure` | honoured | honoured |
| `lighting.hemisphere` | honoured | honoured |
| `lighting.ambient` | honoured | honoured |
| `lighting.directional` (key) | honoured | honoured |
| `lighting.fill` | honoured | honoured (U4) |
| `lighting.rim` | honoured | honoured (U4) |
| `lighting.point` (bounce) | honoured | honoured |
| `lighting.spot` | honoured | unsupported — no cone/attenuation term in the shader |
| `environment.intensity` | honoured (IBL) | approximated — folded into a flat white ambient term |
| `environment.presetId` / reflections | honoured | unsupported — the shader samples no textures |
| `materials.*` tint/saturation/contrast/brightness | honoured | honoured (shared `shapeSourceColor`) |
| `materials.*` roughness/metalness/clearcoat/opacity/emissive | honoured | unsupported — fixed BRDF |
| per-part fill cycling | honoured | unsupported — one SDF body, no parts |

**The schema lives in two files.** `packages/implicitjs` may not import `packages/cadjs`,
so `common/themeSettings.js` is duplicated in both. A field added to one and not the other
is silently dropped for that renderer at normalization time, before any uniform wiring can
matter — that is exactly how `lighting.fill` and `lighting.rim` came to be ignored. Change
both, together.

**The implicit has two backdrops.** In the viewer the raymarch pass composites over the
shared stage, so what you see behind an implicit model is `cadjs/lib/viewer/stageTheme.js`,
the same code every other format uses. The shader's own `uBackgroundMode` ramp only paints
in headless/standalone renders. The two are not the same function — the canvas path ramps
linearly between stops (radial: inner 0.1, outer 0.75 of the texture width), the shader
uses `smoothstep(0.0, 0.72, ...)` — so a headless implicit render and a headless mesh
render of the same theme have different gradient falloff. Unmeasured; recorded here so it
is not rediscovered as a viewer bug, which it is not.

### Conformance harness

```bash
node scripts/e2e-theme-conformance.mjs --dir <abs-models-root> [--out <dir>] [--baseline <file>]
```

Loads one mesh scene and one implicit scene under all eight presets and asserts:

1. **Background parity** between renderers, per theme — the backdrop is shared code, so the
   target is zero. Four themes carry a budgeted, pre-existing drift (`cinematic` 7.0,
   `clay-sunrise` 5.4, `pink` 4.7, `blue` 4.5, out of 255); the budgets ratchet down the
   same way the identity-check counts do. Verified NOT caused by the U4 lighting work
   (A/B identical), NOT the shader gradient above (swapping it moved the numbers by 0.0),
   and NOT the environment map (forcing `environment.enabled = false` on cinematic leaves
   7.1). Cause open.
2. **Surface response** — each renderer's model pixels must actually differ across themes.
   A renderer that ignores the theme passes any background check while rendering all eight
   identically, which is exactly what the raymarcher did while `lighting.fill` and
   `lighting.rim` were being dropped at normalization.

`scripts/theme-conformance-baseline.json` records the measured means so a change of
look is visible in a diff rather than only in a pass/fail.
