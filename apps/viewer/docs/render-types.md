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
| `animations` | Can expose animation clips. STEP gates on render-module clips; direct GLB gates on playable embedded clips. |
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

The repository's self-contained browser gate loads generated test inputs for every
format and asserts non-empty model bounds, real-framebuffer foreground coverage, toolbar
and context-menu capabilities, and no page errors. It uses Metal on macOS and SwiftShader
on Linux. See the
[repository contribution guide](https://github.com/earthtojake/text-to-cad/blob/main/CONTRIBUTING.md#viewer-development-in-this-repo)
for the command.

## Known non-uniformities

Recorded so they are not mistaken for bugs, and so the next person knows the cost:

- **Select is inert for DXF.** It keeps the button for a uniform toolbar shape; it has no
  pickable topology.

## Scene conformance

CAD appearance and the isolated photographic Render configuration reach every
mesh renderer (STEP/STL/3MF/GLB/DXF) and change the picture. Render always uses
its fixed shaded, authored-color view policy; CAD selection, clipping,
visibility, edges, guides, and exploded transforms never enter that path.
Shared cadgen-js scene settings are the single public schema.

The repository browser gate loads one mesh scene through the real Appearance and Render
controls. It checks that CAD light/dark and the Light/Dark Render backdrops produce
distinct framebuffers after the model's non-empty bounds and foreground draw have been
established independently.
