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

## Scope

Every file family has a renderer of its own: a DXF, a GLB, a triangle mesh (STL, 3MF), a
robot description (URDF, SRDF, SDF) and a cadgen engine document (an `.xbf`, and a STEP, which
the engine reads and serves as one) (`src/renderers/dxf`, `src/renderers/glb`,
`src/renderers/mesh`, `src/renderers/robot`, `src/renderers/xbf`; see [CAD renderer](cad-renderer.md#kit)):
a vertical slice owns its tools, tabs and scene outright and consults no capability table. The
rows below remain for what is not a renderer: the file list's icon and label. An engine document is read by the page from the
engine that serves it (`engineDocument` on the workspace service says where), never through the
viewer's server; its row says `assetKind: engine-document`, `parts` and `topology`. The headless snapshot renderer consults no table either: it draws
each of those families with the scene builder its renderer uses
([one scene builder per family](cad-renderer.md#one-scene-builder-per-family-the-viewer-and-the-snapshot-cli)).

The DXF slice does not even have a scene: it is a canvas painted from
`GET /__cad/drawing`, so none of the viewport capabilities below describes it — and its
row says so, with `assetKind: drawing` and no viewport tools (its own are its renderer's). `cadgen dxf snapshot` paints the same
payload with the same code (`@text-to-cad/core/lib/drawing2d`), so the CLI cannot produce a
picture the pane could not.

## The capability registry

`packages/core/src/lib/renderCapabilities.js` — one frozen table, keyed by render
format. Pure data: no behaviour, no imports beyond the format enum.

| Capability | Meaning |
|---|---|
| `assetKind` | Which asset a format LOADS: `mesh`, `drawing`, `robot`. |
| `iconKind` | The file-list glyph. |
| `tools` | `select`, `pan`, `draw`, `orbit`, `screenshot`. Orbit and screenshot are true for every format WITH a viewport — they act on the viewport, not the geometry. `dxf` claims none of them: it has no viewport, and its tools (Select, Annotate, Measure) are its renderer's own, over a 2D canvas. |
| `parts` | Per-part selection, hiding, isolate, assembly tree. |
| `topology` | Face/edge/vertex references. Implies `parts`. |
| `animations` | Has animation clips, so transport controls apply. An engine document's motions are its renderer's own (its Motion section, [CAD renderer](cad-renderer.md#engine-document-renderer)), read from the document's mechanism, never from this table. |
| `artifactManaged` | Builds a package before it can render. A format listed here that the backend cannot produce a package for blocks forever, so a format the viewer renders from its own file belongs out. |

What a 3D file's tools and view offer — Measure, Clip, Explode, the display modes — is not
in this table: each renderer offers its own tools ([CAD renderer](cad-renderer.md#tools-on-a-scene-of-triangles)),
and `viewFeaturesForKind` (`@text-to-cad/core/common/viewSettings.js`) is the one rule of
what a file's view offers, for the viewer and a snapshot alike.

### Rules

- Add a capability when the **second** format needs it, never speculatively.
- An unknown format resolves to the conservative default row (everything optional off).
  Deliberately *not* `normalizeRenderFormat`, which resolves unknowns to STEP and would
  hand an unrecognised entry STEP's full capability set.
- Capabilities decide **which** panels and tools mount. Format-specific *content* — STEP's
  tree — stays format-specific.

## The render-backend contract

The kit's viewport (`renderers/kit/shell/ShellViewport.jsx`) is the shell and owns the camera,
`OrbitControls`, the scene stage, frame presentation, the Draw overlay, screenshots and the
imperative viewer API. A renderer's **scene** (the contract `renderers/kit/scene.js` re-exports from core) owns geometry only:

1. **Consume content**: the document its renderer loaded (an engine document's structure and
   part buffers, a GLB's native scene, a mesh file's objects, a robot's parts). Each family's
   scene is built in `@text-to-cad/core`, where the snapshot CLI builds the same one.
2. **Publish bounds** so the shared fit and its zoom baseline work. The mesh
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
shell. If you find yourself adding a format check to `FloatingToolBar` or to anything under
`renderers/kit/`, the capability you need is missing from the table.

## Enforcement

A ratcheting policy test in the repo where this app is developed counts identity
checks in non-test client code: the number may only go down. It also asserts a
growing set of files at **zero** — the toolbar, the alert
builder, the file-list icon and status, and the home screen — since those are the surfaces
every format flows through. Lower the budgets in the same commit that removes checks.

What is left is deliberate. A DXF is rendered from the file that is on disk — the backend
flattens those bytes to 2D primitives per request and never owns a package for one
(`owns_dxf_path` always answers False).

## Standing gate

The `packaging` CI job's `scripts/test/test-viewer-browser.sh` opens one fixture per load path
(STEP, STL, DXF, URDF) through the real backend and the bundled viewer and asserts each
draws something with no page errors: a blank-but-error-free viewport is the signature
failure here (a shader that fails to compile, a gate that hides the geometry). It runs on
every change to shared viewer code; there is no separate manual sweep.

## Known non-uniformities

Recorded so they are not mistaken for bugs, and so the next person knows the cost:


## Scene recipe conformance

Inspect and Render resolve through `@text-to-cad/core/common/sceneSettings.js`.
Inspect's fixed light/dark workbench basis follows app appearance; Render uses
its independent studio configuration. Legacy CAD theme preferences are not an
input. The internal `themeSettings` recipe remains a renderer implementation
detail, normalized through the shared core schema so every backend receives the
same lighting, materials and stage settings.

The browser qualification in `scripts/test/test-viewer-browser.sh` opens every
load path through the real backend and bundle and checks mode framing, that a saved
revision keeps the camera and that Zoom to fit frames the revision; picking and the
display presets are the `packages/ui` browser specs'. Both use
isolated generated fixtures rather than a sweep of saved theme presets.
