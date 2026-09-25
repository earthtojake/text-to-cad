# Render types: capabilities and the backend contract

Binding for viewer work that touches more than one file format. The rule this document
exists to enforce:

> Viewer code asks what a format **can do**, never what it **is**.

Every `renderFormat === RENDER_FORMAT.X` check is a place a new format must be
hand-added, and a place an improvement to one format fails to reach the others. That is
not theoretical. The Orbit button was gated off per format independently and had to be
fixed twice; when it was finally enabled for DXF, the button still did nothing because
**four** separate format checks stood between it and preview mode (the toolbar gate, the
workspace handler bail, the pane's `previewMode={dxfMode ? false : ...}`, and an effect
that force-exited DXF from preview). Another format grew an entire parallel export path to
an endpoint the server does not implement.

## The capability registry

`packages/cadgen-js/src/lib/renderCapabilities.js` — one frozen table, keyed by render
format. Pure data: no behaviour, no imports beyond the format enum.

| Capability | Meaning |
|---|---|
| `content` | Which loaded object is the viewport's content: `mesh`, `robot`. Resolved once into `selectedViewportContent`. |
| `assetKind` | Which asset the viewer LOADS: `mesh`, `drawing`, `robot`. Not the same question as `content` — a DXF loads a drawing and renders it through the mesh viewport, so it shares the viewport but not the loader. |
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
| `params` | `sidecar` (the model's `@step(pose=...)` block), or `null`. |
| `animations` | Has animation clips, so transport controls apply. |
| `artifactManaged` | Builds a package before it can render. A format listed here that the backend cannot produce a package for blocks forever, so a format the viewer renders from its own file belongs out. |
| `exportFormats` | What `/__cad/export` can produce for it. |

### Rules

- Add a capability when the **second** format needs it, never speculatively.
- An unknown format resolves to the conservative default row (everything optional off).
  Deliberately *not* `normalizeRenderFormat`, which resolves unknowns to STEP and would
  hand an unrecognised entry STEP's full capability set.
- Capabilities decide **which** panels and tools mount. Format-specific *content* — STEP's
  tree, DXF's bends — stays format-specific.

## The content signal

`selectedViewportContent` in `CadWorkspace` is the single answer to "is there anything on
screen?", derived from `content`. Toolbar gates, the CTA, preview mode, the zoom pill and
alert blocking all read it, rather than each one re-deriving the answer per format.

## The render-backend contract

`CadViewer` is the shell and owns the camera, `OrbitControls`, the themed stage, frame
insets, overlays, screenshots and the imperative viewer API. A **backend** owns geometry
only:

1. **Consume content** for its `content` kind (mesh data, robot).
2. **Publish bounds** so the shared fit, zoom baseline and zoom-percent work. The mesh
   path does this via `applyRuntimeModelBounds` after composing; a backend with no mesh
   calls back with its own bounds instead.
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

A ratcheting policy test in the repo where this app is developed counts identity
checks in non-test client code: the number may only go down. It also asserts a
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
node scripts/e2e-format-sweep.mjs --dir <abs-models-root> [--out <dir>]
```

Run it for any change to shared viewer code. It uses `page.screenshot()` against a
Metal-backed context on purpose: a blank-but-error-free viewport is the signature failure
mode here (a shader that fails to compile, a gate that hides the geometry), sampling the
canvas with `drawImage` reports every format blank because the drawing buffer is not
preserved, and the software rasteriser hides real GPU failures. It has already earned its
keep — it caught a temporal-dead-zone crash that blanked all six formats and that the
build and unit tests both passed.

**Method warning: do not run large sweeps back to back.** Chaining full runs (or launching
several browsers in quick succession) exhausts GPU
contexts and reports large numbers of *false* blanks — a run that reported 33 blank models
reported zero on a clean run of the same build, twice. Let the previous run's browser fully
exit before starting another, and treat any mass-blank result as suspect until reproduced
from a cold start. Isolate a single suspect model rather than trusting one bulk run.

## Known non-uniformities

Recorded so they are not mistaken for bugs, and so the next person knows the cost:

- **Select is inert for DXF.** It keeps the button for a uniform toolbar shape; it has no
  pickable topology.

## Theme conformance

Every theme field reaches the mesh renderer (STEP/STL/3MF/GLB/DXF) and changes the
picture. `common/themeSettings.js` is the single schema: it used to be duplicated across
two packages, and a field added to one and not the other was silently dropped for that
renderer at normalization time — that is how `lighting.fill` and `lighting.rim` came to be
ignored. One copy, one normalization, and that failure mode is gone.

### Conformance harness

```bash
node scripts/e2e-theme-conformance.mjs --dir <abs-models-root> [--out <dir>] [--baseline <file>]
```

Loads one mesh scene under all eight presets and asserts **surface response** — the
model's own pixels must actually differ across themes. A renderer that ignores the theme
still starts up and still draws while rendering all eight identically, which is exactly
what happened while `lighting.fill` and `lighting.rim` were being dropped at
normalization.

`scripts/theme-conformance-baseline.json` records the measured means so a change of
look is visible in a diff rather than only in a pass/fail.
