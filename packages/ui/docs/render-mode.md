# View styles, appearance and rendering

The CAD viewer has one viewing state. **View → Mode** selects the surface style:
Shaded with edges, **Render** (second), then the remaining CAD styles. Selecting
Render changes lighting, material presentation and quality; it does not replace
the camera, projection, clipping, explode, guides, visibility, selection, motion,
or tab layout. The interaction tools remain available in every style.

The state contract is in [cad-renderer.md](./cad-renderer.md). Settings use the
binding row and section rules in [settings-ui.md](./settings-ui.md). Core's
`common/sceneSettings.js` resolves the shared scene recipe used by the viewer
and snapshots.

## Controls and ownership

**Model** contains the tree and read-only references. **Motion**, when supported,
contains Animation followed by Position, with transition controls inside Position.
**View** groups scene, camera, grid, axes, edges and colors in one section, followed
by separate Clip and Explode sections. Render adds its lighting, backdrop and
quality controls at the bottom. Hiding those controls preserves their values.
Per-format controls continue to appear alongside these tabs.

There is no Display popover, top-level Inspect/Render switch, or separate Studio
layout. The floating interaction toolbar owns Select, Measure and Draw; its
neighbor owns navigation and capture. A style change preserves the saved tab
arrangement. Earlier Kinematics/Animation and Display/Studio arrangements migrate
to Motion and View without discarding custom splits.

Projection remains independently selectable as Orthographic or Perspective in
all styles. Lens appears for perspective projection. Camera motion, zoom, fit
and reset use the same behavior across styles. Render does not select a new
lens or reframe the model. Reset in the Render section resets only photographic
settings, leaving the shared camera and display settings alone.

## Appearance and authored materials

App appearance selects the light or dark workbench/studio defaults. The web host
exposes System / Light / Dark and shows the effective Sun or Moon icon in its
trigger; desktop supplies its existing appearance preference. The web choice is
remembered in a host-scoped cookie with a localStorage mirror, as described in
[web storage](../../../apps/web/docs/storage.md). Shared UI never owns these
platform effects.

Materials are read-only in every style. STEP sidecar assignments supply names,
optional base color, roughness, metalness, clearcoat, clearcoat roughness and
opacity. Sparse fields resolve through core defaults; omitted base color keeps
the STEP color. Material opacity multiplies source alpha. The Model reference
section shows selected occurrences' assignments, including mixed and unassigned
parts. Face/edge references use their owning occurrence. A STEP color alone does
not identify a physical material. There is no Materials tab or material editor;
model changes are made through source/annotations, typically via a prompt.

Workbench lighting uses a small neutral reflection hemisphere when authored
materials need it; Render uses a photographic softbox environment. Both share
material resolution and obey common part-color settings. Live appearance wraps
cached meshes without copying geometry, preserving `sourceAppearanceGeometry`
for detail adoption and disposal acknowledgments. Removing an assignment restores
the original appearance.

Direct GLB animation retains native hierarchy, skin/morph data, textures and PBR
materials. Static direct GLB uses the native hierarchy in Render; other styles
use normalized geometry/colors for inspection. Animated GLB measurement remains
unavailable because triangle references describe the rest pose. A bounded
load-time animation sample determines stable framing, rather than refitting each
playback frame.

## Photographic controls and costs

Render uses Khronos PBR Neutral tone mapping, exposure and a generated softbox
environment. Controls adjust lighting rotation/size/fill and backdrop color,
transparency and ground placement. Ground defaults to the bottom of model bounds;
Model origin places it at Z=0. Geometry retains its authored coordinates.
Transparent backdrops retain their shadow catcher.

Interactive Render defaults to **Preview**; **Final** adds quality at extra GPU
and capture cost. Both share tessellation cache entries and the memory budget.

| Policy | Screen-error target | Shadow map | Environment | Capture scale |
| --- | --- | --- | --- | --- |
| Preview | 1 px | 2048 px | 256 px | 1× |
| Final | 0.25 px | 4096 px | 512 px | 2× |

Other styles use the Interactive detail policy. Quality changes refine detail
without recompiling the model. Headless rendered snapshots default to Final,
which selects the existing L3 STEP tessellation and 2× capture scale unless an
explicit output scale overrides it.

The photographic rig and settings editor remain a lazy chunk behind
`render/renderStudioChunk.js`, loaded when Render is requested. Ordinary viewing
does not fetch its environment/lighting code. Picking acceleration is still
built on demand; merely displaying Render does not eagerly build every topology
or raycast structure. Expanded tree nodes determine selectable topology in all
styles.

The WebGL runtime still changes depth-buffer strategy at the style boundary:
logarithmic depth for ordinary CAD styles, conventional depth for photographic
ground shadows. Switching recreates the GPU runtime and reuses decoded geometry.
It preserves the current camera, orthographic frustum, projection, zoom baseline
and interaction state. A backdrop covers preparation until the destination's
first complete frame. This transition has no second GPU scene and does not recur
during ordinary orbit or detail refinement.

## Camera and framing

All styles use the same surface-under-cursor zoom pivot, with model center as a
fallback. Orthographic pan/dolly need no depth pivot. Zoom is grounded on the
model's zero pose: joint/pose/animation changes affect geometry and floor bounds,
not what 100% means. Reset fits that same zero-pose box.

Interactive fitting uses projected width/height plus perspective depth, with a
1.1 padding multiplier (about 91% of the limiting viewport dimension), implemented
by `components/viewer/viewportCameraFit.js`. A different model, progressive load
reaching full extent, or a rebuilt zero pose can request a fit; refinement stands
down once the user has deliberately positioned the view. Changing style does not
request a new fit. Resizing preserves framing and its zoom baseline.

Freehand drawings are screen-space annotations: camera movement currently clears
them, but an unchanged camera republished after a style transition does not.
A future camera-anchored annotation workflow can replace that behavior separately.

## Snapshot parity

Snapshots use the same display schema. `--display render` is the concise rendered
form; JSON/file input can combine `mode: "render"`, ordinary display settings and
nested `render` options for quality, lighting and backdrop. Camera and projection
remain in `--camera`. There is no `--render` argument or top-level render payload.
Nested render settings are only valid with display mode render. See cadgen's
snapshot CLI documentation for the exact schema and examples.
