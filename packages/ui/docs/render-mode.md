# Appearance, Inspect and Render

The mechanism behind the app's two viewing modes: which control lives where,
what each one is worth in pixels and milliseconds, and the constants the UI
resolves. The contract — what each mode OWNS and where its state persists — is
in [the shared renderer contract](./cad-renderer.md#inspect-render-and-live-revisions). Control
anatomy, spacing and row kinds are in [settings-ui.md](./settings-ui.md); the
shared scene schema both modes resolve through belongs to `@hardcore/core`.

## App appearance

The web host exposes a global **System / Light / Dark** preference; System
follows the live OS preference. Desktop injects its existing app appearance.

- A host-scoped `cad-viewer-appearance` cookie remembers the choice across
  browser sessions and viewer ports. A localStorage mirror notifies other tabs
  on the same origin and is the fallback when cookies are blocked
  ([web storage](../../../apps/web/docs/storage.md)).
- A synchronous startup script applies the preference before the app mounts.
- The web top bar shows the effective appearance with Sun or Moon, including
  when System follows the OS. The menu pairs System, Light and Dark with
  Monitor, Sun and Moon icons respectively.
- Neutral light and charcoal panel tokens stay independent of the model's
  lighting and materials.

## Display (Inspect)

Display owns the CAD inspection projection, style, edge visibility, grid,
origin axes, part colors, clipping, and exploded view.

- **Shaded with edges** shows shaded surfaces with CAD edges; **Shaded** shows
  those surfaces without edges.
- Inspect uses an opinionated light or dark workbench basis, selected by app
  appearance. There is no CAD Theme editor or custom scene-theme preference.
- Edge styling is fixed, with weights following edge type. Display controls
  edge visibility; legacy custom outline settings do not override it.
- The grid is an on/off world reference; origin axes remain independently
  configurable.

## The Viewing mode control

The shared floating toolbar's **Viewing mode** button switches between **Inspect**
and **Render**, showing the active mode's cube or clapperboard icon.

- Inspect shows only CAD inspection tabs and restores their saved split, order
  and active selection unchanged.
- Render opens with **Studio** first and active; **Kinematics** follows when
  the model declares pose controls; **Animation** follows when it provides clips.
- The default **Light** or **Dark** studio follows global app appearance; the
  session stores no studio choice of its own, and backdrop customizations stay
  local to the model session.
- Render tabs start in one row on each entry. Dragging and splitting them is
  temporary and never overwrites the durable per-kind CAD arrangement.
- **View controls → Orbit** hides panels and orbits the model. Escape or
  **Exit orbit** restores the previous layout.

## The Studio editor and the photographic rig

The compact editor controls lens and exposure, softbox rotation, size and fill,
plus backdrop color, transparency, ground visibility and position. The
translucent ground sits under the model — at the bottom of its bounds — by
default, so a document whose geometry reaches below its own origin is never
veiled by its own floor; **Model origin** pins the plane to Z=0 instead, for
models authored standing on it. Either way the geometry keeps its authored
coordinates: the plane moves, the model never does.

Khronos PBR Neutral tone mapping and a generated softbox environment provide
the Render lighting. The overhead side key models depth, while a rear fill
retains detail on dark and polished surfaces. Defaults are checked against
colored assemblies, mechanical models and material samples in both studios.
Backdrop-colored ground fill and a restrained diffuse response keep floor
shadows and the spotlight pool subtle without changing model illumination;
transparent backgrounds retain their shadow catcher. The existing toolbar owns
image capture.

**Per format.** STEP package material properties remain intact. A direct GLB
with embedded animation retains its native hierarchy, skin/morph data, textures
and PBR materials for playback, and its Animation tab appears in both Inspect
and Render. A static direct GLB uses that native hierarchy in Render, retaining
textures and PBR materials, while Inspect uses its normalized base or vertex
color and opacity for CAD interaction. 3MF retains color; STL has no authored
color. Animated GLB measurement is unavailable, because the normalized triangle
picks describe only the rest pose. A bounded load-time animation sample
estimates stable framing, so the camera, floor and studio do not refit on every
playback frame.

## Quality

Quality is independent of the studio. Inspect uses its Interactive policy;
Render offers **Preview** and **Final** and defaults to Final. Preview and
Final share the tessellation ladder, cache entries and memory budget.

| | screen-error target | shadow map | softbox environment | capture scale |
|---|---|---|---|---|
| Preview | 1 px | 2048 px | 256 px | 1x |
| Final | 0.25 px | 4096 px | 512 px | 2x |

Quality changes refine the view without rebuilding exact CAD geometry or the
model scene. Snapshots use the same policy: Final selects the existing finest
L3 STEP tessellation and 2x capture scale unless an explicit output scale
overrides it. CAD tessellation controls cannot be combined with a photographic
snapshot request.

## Depth, zoom and the mode transition

Entering Render creates an ordinary-depth WebGL runtime so the photographic
ground can receive shadows; returning to Inspect restores its wide-range
logarithmic-depth runtime while decoded geometry stays cached.

Close-ups fit the depth range to visible rigid components when the camera
enters the assembly bounds, preserving fine layered details without changing
lighting. Optical zoom and cropped viewports also contribute to the detail
target. The filename badge reports **Limited detail** when memory limits
prevent the requested detail ([lod.md](./lod.md)).

Render zoom uses the subject's bounds for a stable pivot depth. Inspect zoom
anchors to the surface under the cursor, falling back to the model center.
Render pointer movement skips inspection hit tests and does not install CAD
raycast accelerators.

**Zoom is grounded on the zero pose.** A model is framed once, against its
authored placement: a robot at its joint defaults, an assembly before its mates
move anything, an animated document at its load-time framing estimate, a mesh
as loaded. Driving a joint, choosing an SRDF group state, changing a mate value,
scrubbing an animation and a detail swap all change what is lit, shadowed,
clipped and floored — never how the model is framed, and never what 100% means.
**Reset view** re-fits to that same zero-pose box rather than to the pose on
screen, so it reproduces the view the model opened at.

Interactive default and explicit fit actions use the box's projected width and
height, plus perspective depth, with a 1.1 padding multiplier: about 91% of the
limiting viewport dimension. This avoids the excess empty space a bounding
sphere leaves around long or flat models. The mechanism is
[`viewportCameraFit.js`](../src/renderers/cad/components/viewer/viewportCameraFit.js).
The destination lens is applied before fitting, so first entry and later mode
switches use the same frame. Saved views and manual zoom are preserved. Fits
retain the model's base clipping floor, so Render's transient near plane after
zooming cannot change Reset or resize framing. Resizing compares the fitted box
at its recorded orientation and scales both framing and the zoom baseline;
ordinary orbiting never triggers another fit. Snapshot/export framing is
independent and unchanged.

Four things reopen that decision, and none of them is a pose: a different
model; a **change of viewing mode**, because Inspect's orthographic frustum and
Render's photographic lens are two cameras and the one being entered fits the
zero pose itself; a progressive load reaching its full extent, having framed on
the handful of components that arrived first; and a **rebuilt model whose zero
pose changed** — a new revision is a new zero pose, so a save that grew the
geometry re-fits rather than leaving the new geometry clipped outside the old
frame. The last two stand down once the user has taken the view; their camera is
a deliberate choice about this model, and Reset view still takes them to the new
zero pose. A mode change does not stand down: switching is itself the deliberate
act, and it carries Reset view's meaning for the mode being entered — which is
also why a freehand CAD drawing, anchored to the view it was drawn in, ends
there as it does on any other reframe.

Mode changes keep the new canvas covered with the destination backdrop until
geometry and lighting have drawn their first frame. This transition owns no
second GPU scene and does not return during orbit or detail refinement. Render
receives no inspection selectors and no DXF bend-guide overlays; STEP and
embedded GLB animation stay independent of those inspection resources.

**Render is a lazy chunk.** The photographic rig, the softbox environment, the
Studio editor are fetched the first time Render is
asked for, not on every load: an Inspect-only session never pays for them.
`src/renderers/cad/render/renderStudioChunk.js` is the one boundary. The Studio panel goes
through `React.lazy`, and the scene half answers `studioScene()` with `null`
until it arrives — a state the transition above already covers, because
`environmentReady` stays false and the canvas stays under the destination
backdrop, so a photographic camera is never presented over CAD lighting. The
chunk is warmed from the Viewing mode button's hover and focus and again from
the switch itself, so a mode change normally has it already; a cold cache sees
the tab's muted "Loading studio settings..." line for the round trip. There is
no idle prefetch: a background fetch would compete with the tessellation work
that actually governs first geometry.

**What that means for tests.** A test that wants the Studio panel
mounts `RenderSettingsContent.js` directly —
the tab builders return the lazy wrapper, not the panel — and a browser test
that switches to Render waits for the scene as it already does, since the
switch resolves the chunk before anything is presented.

Entering Render applies its perspective camera and fixed presentation view —
shaded authored colors, with guides, edges, clipping, exploded transforms and
selection effects off. Kinematics and animation remain available and compose
through the same model pose state used in Inspect. Returning to Inspect restores
the inspection state and its projection; the CAMERA is not restored in either
direction but re-fitted, so each mode opens at its own view of the zero pose.
The session still records where each mode's camera was left, for the file
session it reopens with and for a snapshot request; nothing replays it across a
switch.

## Read-only materials

Authored appearance is shared by Inspect and Render. STEP sidecar assignments
supply material names, optional base color, roughness, metalness, clearcoat,
clearcoat roughness and opacity. Sparse fields resolve through core defaults;
omitted base color preserves the STEP's color. Material opacity multiplies
source alpha. Inspect's workbench lighting and Render's photographic lighting
make the same material look different without changing its properties. Inspect
adds a small fixed neutral reflection hemisphere only when authored materials
are present, so metallic surfaces stay legible. This procedural texture uses
no external assets or photographic studio; it is reused within the renderer
and disposed on material removal or renderer teardown.

The Model tree's reference section shows the selected occurrences' materials,
including mixed assignments and unassigned parts. Face and edge references use
the owning occurrence. A STEP color alone does not identify a physical material.
There is no Materials tab, material editor, local assignment, preset or undo.
Older persisted material overrides and retired tab IDs are ignored; changes
must come from the model or its annotations, typically through a prompt.

Live appearance changes wrap the cached mesh without copying geometry. Core's
`applySourceAppearanceToMeshData` preserves source colors and alpha and exposes
`sourceAppearanceGeometry` so detail-adoption and disposal acknowledgments
still refer to the exact geometry publication. Removing an assignment restores
the source appearance, rather than leaving stale finish settings behind.

## Shared pipeline and remaining separation

Both modes use the same CAD renderer, source assets, tessellation cache, LOD
controller, animation/kinematics and authored material resolution. They are
presentation and interaction policies over shared model data, not separate
model loaders.

| Concern | Inspect | Render |
| --- | --- | --- |
| Lighting | Fixed workbench rig; neutral reflection fill for authored materials | Lazy photographic softbox environment, ground shadows, exposure and lens controls |
| Interaction | Tree/topology selection, references, measurements, clipping, isolation, explode, drawing | Presentation/orbit/capture; no inspection selectors or selection tints |
| Camera | Display projection, cursor/surface zoom pivot | Perspective lens, model-center zoom pivot |
| Detail | Interactive quality | Preview or Final quality; larger shadows/environment/captures at Final |
| Depth buffer | Logarithmic for wide CAD ranges | Conventional for photographic ground shadows |
| Native GLB | Static inspection mesh; animated GLB keeps its native hierarchy | Native hierarchy/materials/textures |

`common/sceneSettings.js` in core resolves either scene recipe. UI's
`sceneBuildSettings.js`, `viewerPickMode.js` and `useViewerRuntime.js` apply
its build, interaction and GPU-runtime policy. Changing modes recreates the
WebGL runtime because the depth-buffer mode is chosen at renderer construction;
it retains cached CPU geometry and does not recompile the model.

Combining the UI into one configurable view is possible, but retaining the
current performance and behavior still requires these internal policies. Always
loading the photographic rig adds work to first Inspect load; always enabling
inspection adds selector/BVH costs to presentation-only use. Eliminating runtime
recreation also requires choosing and validating one depth strategy across
large CAD ranges and ground shadows. Authored materials are already shared, so
merging modes is not necessary to remove material duplication.

## Setup and Reset

The top **Setup** section in Studio contains Quality. **Reset** sits at the
bottom of the tab and clears photographic customizations, restoring defaults
for the current global light/dark appearance while keeping the current camera
pose. The viewer has no studio preset selector and no settings clipboard.
