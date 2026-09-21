# Appearance, Inspect and Render

The mechanism behind the app's two viewing modes: which control lives where,
what each one is worth in pixels and milliseconds, and the constants the UI
resolves. The contract — what each mode OWNS and where its state persists — is
in [the app README](../README.md#appearance-display-and-render). Control
anatomy, spacing and row kinds are in [settings-ui.md](./settings-ui.md); the
shared scene schema both modes resolve through belongs to `cadgen-js`.

## App appearance

App appearance is a global **System / Light / Dark** preference; System follows
the live OS preference.

- A host-scoped `cad-viewer-appearance` cookie remembers the choice across
  browser sessions and viewer ports. A localStorage mirror notifies other tabs
  on the same origin and is the fallback when cookies are blocked
  ([storage.md](./storage.md)).
- A synchronous startup script applies the preference before the app mounts.
- The navbar shows the resolved Sun or Moon icon; System appears only as a
  dropdown choice.
- Neutral light and charcoal panel tokens stay independent of the model's
  lighting and materials.

## Display (Inspect)

Display owns the CAD inspection projection, style, edge visibility, grid,
origin axes, part colors, clipping, and exploded view.

- **Shaded with edges** shows shaded surfaces with CAD edges; **Shaded** shows
  those surfaces without edges.
- Inspect uses the same model lighting, materials and dark edge colors in light
  and dark appearance; only the canvas and guides adapt.
- Edge weights are fixed by edge type.
- The grid is an on/off world reference; origin axes remain independently
  configurable.

## The Viewing mode menu

The navbar's **Viewing mode** icon menu switches between **Inspect** and
**Render**, showing the active mode's cube or clapperboard icon.

- Inspect shows only CAD inspection tabs and restores their saved split, order
  and active selection unchanged.
- Render opens with **Studio** first and active; **Materials** follows for STEP
  models, including those without named materials; **Kinematics** follows when
  the model declares pose controls; **Animation** follows when it provides
  clips.
- The default **Light** or **Dark** studio follows global app appearance; the
  session stores no studio choice of its own, and backdrop customizations stay
  local to the model session.
- Render tabs start in one row on each entry. Dragging and splitting them is
  temporary and never overwrites the durable per-kind CAD arrangement.
- The floating toolbar's rightmost button opens **Fullscreen**, hiding panels and orbiting
  the model. Escape or the floating toolbar's **Exit fullscreen** button
  restores the previous layout.

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
Studio editor and the Materials editor are fetched the first time Render is
asked for, not on every load: an Inspect-only session never pays for them.
`src/client/render/renderStudioChunk.js` is the one boundary. The two panels go
through `React.lazy`, and the scene half answers `studioScene()` with `null`
until it arrives — a state the transition above already covers, because
`environmentReady` stays false and the canvas stays under the destination
backdrop, so a photographic camera is never presented over CAD lighting. The
chunk is warmed from the Viewing mode button's hover and focus and again from
the switch itself, so a mode change normally has it already; a cold cache sees
the tab's muted "Loading studio settings..." line for the round trip. There is
no idle prefetch: a background fetch would compete with the tessellation work
that actually governs first geometry.

**What that means for tests.** A test that wants the Studio or Materials panel
mounts `RenderSettingsContent.js` / `MaterialsSettingsContent.js` directly —
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

## The Materials tab

Click a part in the list or Render viewport (Shift-click for multiple), carry a
selection from Inspect, or Select all parts. The Parts list marks the
selection; the photographic scene receives no selected parts, because the
Inspect selection tint and occlusion ghost would repaint the material being
previewed.

- Click an **In this model** swatch or **Preset** to apply immediately; a
  preset creates and assigns its material together.
- Undo restores the last local material change.
- A material's options menu can select every part using it. Color and surface
  sliders stay behind **Advanced settings**. Shared editing remains explicit,
  with **Make unique for selection** available before editing a shared
  material.
- **Reset authored** clears local assignments and definitions.
- Part picking is enabled only while the STEP Materials tab is open; face and
  edge selectors stay disabled. Appearance wrappers retain their geometry
  identity for detail-adoption and disposal acknowledgments.

The edits, that one step of history and the panel's part selection are the
model's session, held by the workspace rather than the panel, so looking at
Studio and coming back leaves all three where they were.

## Setup and Reset

The top **Setup** section in Studio contains Quality. **Reset** sits at the
bottom of the tab and clears photographic customizations, restoring defaults
for the current global light/dark appearance while keeping the current camera
pose. The viewer has no studio preset selector and no settings clipboard.
