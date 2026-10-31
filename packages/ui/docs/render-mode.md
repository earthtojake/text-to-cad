# Display modes

The Viewer and native snapshots share the sparse display contract. Core's
`common/viewSettings.js` validates it and resolves the mode, or Preview's Render,
into renderer groups.
`common/sceneSettings.js` translates those groups into the scene recipe. The binding
controls are in [settings-ui.md](settings-ui.md#display-settings-and-section-primitives).

A file's display is a mode and the Grid switch. A mode is a look at its own defaults, with
nothing to set. Render is no display mode: it is the photographic look Preview asks for
over the same display, with Preview's own settings (the viewer's alone, kept beside the
display). Native snapshots remain technical images rendered by OCCT.

| Mode | Surface / edge recipe |
| --- | --- |
| Solid (default) | Shaded, the model's visible CAD edges |
| Shaded | Shaded, no edges |
| Parts | Solid, each part its own palette colour |
| X-ray | 22% opacity, all edges |
| Hidden line | Depth-only surfaces, visible edges (light on a dark backdrop) |
| Wireframe | No fill, all edges (light on a dark backdrop) |
| Render (Preview's, asked for on its own) | Shaded, no edges, no grid, photographic studio |

A file without CAD edges (STL, 3MF, GLB, a robot) offers Solid, drawn without edges, and
Parts where it has several parts, objects or links; Shaded would be Solid again there. The
grid is off by default and the same measuring grid in every mode. Appearance, camera, Clip
and Explode are shared. Camera defaults to orthographic with a 50mm lens; Render resolves to
perspective without overwriting that shared camera choice.

## Sparse public contract

```json
{ "mode": "parts", "grid": true, "appearance": "light", "camera": { "projection": "orthographic" } }
```

Omitted mode is Solid, and `mode` is one of the six; `grid` is a boolean, off unless said.
The display also takes `clip` and `exploded`. Anything else is refused: there are no
per-mode settings, style groups or axes. Preview's own settings (`parts`, `lighting`,
`background`, `floor`) are a separate sparse object (`normalizePreviewSettings`): `parts`
contains `colorMode` (`original`, `single`, `by-part`), `color` and `colors`; `lighting`
contains `quality`, `exposure`, `rotation`, `size`, `fill`; `background` contains `color`,
`opacity`; `floor` contains `enabled`, `placement`, `color`, `opacity`, `finish`.

Viewer appearance inherits the host; snapshots default to light. Preview's lighting quality
defaults to Preview. There is no Custom state, legacy alias or
migration. A stored display or Preview settings record is read setting by setting at the
file-session read boundary (`readViewSettings`, `readPreviewSettings`): what this build
cannot read (an older per-mode tree, a mode it no longer has) is left out, the rest kept.
The same display shape powers live `setDisplaySettings` and snapshot `--display`; either
refuses `mode: "render"` as it refuses any mode it does not know. A snapshot turns the grid
on with `--grid` (`display.grid`); it has no Preview rendering option. `--camera` holds
pose/framing only. A Quick Edit's views carry the mode and the grid (`display.mode`,
`display.grid`) with Clip and Explode, so a snapshot of them replays the view.

## State and updates

`kit/view-settings/viewSettingsStore.js` owns one sparse display, and Preview's settings,
per mounted file. `selectMode(mode)` selects a mode; `setGrid(on)` switches the grid (off
is left unsaid); `patch(patch)` merges the display's shared fields. `patchPreview(patch)`
merges Preview's settings and `resetPreview()` removes them. `restore(display, preview)`
replaces state once on mount; persistence reads the latest `getSnapshot().display` and
`.preview`. `renderScene()` resolves Preview's scene without committing anything.

No action reframes the camera, changes model pose, selection or visibility. The store
preserves equal JSON branches; a Preview edit leaves the display's scene identity unchanged.
Clip edits do not invalidate materials, lighting, geometry or camera. No-op actions publish
nothing. Do not merge captured props, persist resolved defaults or keep a second display
state.

The view injects its offered `modes` and `settings` (`edges`, `clip`, `exploded`). Unsupported
saved modes resolve to Solid without rewriting storage; unoffered settings do not affect the
scene. The shared UI discovers no host APIs.

## Rendering costs and camera behavior

The photographic rig stays lazy. Preview's Render creates its photographic
softbox environment; the other modes use neutral CAD lighting, but for an engine document
(`.xbf`), whose scene brings its engine's look as its own rig (core's `lib/xbf/xbfLook.js`,
`lib/viewer/sceneRig.js`): the viewport lights it by that in place of the theme's lights, with
the look's environment and under its own tone curve. Authored finishes show in Solid and Shaded:
a file's reflect a small neutral environment; an engine document's reflect its look's
environment, the studio image its engine serves beside the look (`GET /api/look/environment`),
which lights every surface of the document and which the engine's OCCT stills reflect too, and
every surface of it answers light as OCCT's PBR program does (core's `lib/viewer/surfaceBrdf.js`,
the look's `brdf`), not by three's own physical model. Parts draws a plain finish. An engine
document's X-ray is its look's colour-only model (the scene's `rigFor` its own rig): no finish, an
ambient term and plain lights, no environment, three's own physical model, as the engine's OCCT
stills draw it by Phong, its see-through layers blended in linear light as OCCT blends them (the
rig's `blend`): the viewport draws the surfaces through a half-float frame of the rig's and encodes
them once, its edges, highlights and ink over them as before (core's `renderWithSceneRig`), where
three's canvas would blend each layer after encoding it and draw dark see-through parts too dark.
It holds about 60 bytes a pixel while X-ray is on; every other mode, and every other file, is
drawn as before. Authored materials are read-only. Color
overrides are presentation settings, not edits to the model or its material
assignments.

| Lighting quality | Shadow map | Environment | Capture scale | Samples at rest |
| --- | --- | --- | --- | --- |
| Preview | 2048 px | 256 px | 1× | 32 |
| Final | 4096 px | 512 px | 2× | 64 |

Render is drawn through the studio's frame (core's `studioFrame.js`, see
[the render pipeline](../../core/docs/render-pipeline.md#the-studios-frame)): ambient
occlusion from the frame's depth, and, while the view rests, a picture that converges over
its samples: anti-aliased, its occlusion smooth, the key's shadows a softbox's (Softbox size
sets how soft). The viewport's loop (`useViewerRuntime`) draws each frame through it and says
whether anything but the camera changed (`runtime.requestRender`/`requestFrame` say so); while
samples are owed it asks for the next frame itself, and once the picture has converged it
draws nothing more. A drag, a routine's frame or a setting starts the picture again; the
damped tail of an orbit, moving the model less than a quarter of a pixel, does not. So
orbiting pays one draw and a few small passes a frame (about 1.5 ms more at 3024 × 1964 on
an M1 Max) and a still view converges in about half a second. A snapshot is OCCT's, drawn in
the engine (`engine/render/occt.py`), not through this frame. Software WebGL has no frame: one
draw, as before.

Each interactive viewport keeps its renderer (a view of the page's one GPU device:
[the GPU device](cad-renderer.md#the-gpu-device)), canvas and camera controls
across every mode and settings edit. It uses shadow-compatible conventional
depth throughout, fitting near/far planes to the current model, closeup records
and floor/grid planes on every frame; a perspective near plane stays at or beyond
1/256 of the orbit pivot's depth, so a closeup never trades depth resolution for
a near plane at the eye. The grid's bounds also fit the far plane;
it is independent of the studio floor used by Render. The grid
(`lib/viewer/stageGrid.js`, one shader quad the viewer and the snapshot both draw) is graph
paper on the floor, after Tinkercad's workplane: thin minor lines at a round step (1, 2 or
5 x 10^n) near twenty across the default framing at density 1, a heavier major line every 5 or
10 of them, in one cool cyan-blue ink (`GRID_LINE_DEFAULTS`: `#4ea8cc` at 0.45 on a light
backdrop, `#5d9ac0` at 0.35 on a dark one; minors are the same ink at 0.6 of its strength), with
a red X and a green Y axis through the origin, anti-aliased in the fragment shader. Each family
of lines fades only once its cells crowd under about 3.5 pixels, so there is no moire zoomed
out or at a grazing angle; the sheet is at full strength to 1.5 framings from the origin, past
the default view's corners, and dissolves gently by 6, and fades a little as the plane turns
edge-on, so it reaches the edges of the view yet has no edge of its own. Display has no separate Axes setting. The grid, the stage and the Render studio's floor are
SIZED from the model's rest placement for every renderer: a pose, a
playing routine, or a pose set in Preview never rescales or
slides the ground; its height, the lighting and the shadow reach follow the model. Enabling photographic effects updates that live scene;
it never clears or covers the canvas with a loading screen. Only actual context
recovery replaces the renderer. Quality never changes a mesh: every mode draws
the meshes the file's document holds.

Enabling Clip prepares its shader/cap variants before presentation. Moving an
enabled cut stays live. Explicit neutral boundaries
still avoid unnecessary caps. See [responsive View updates](view-updates.md)
for scheduling, resource caching, loading presentation and capture readiness.

Render's floor stands under the model's lowest point (`RENDER_FLOOR_PLACEMENT`, `lowest`), at 60%
opacity, its opacity letting geometry below it show; Model origin (the document's Z=0 plane) is a
choice away and is remembered in Render, as Glossy is.
Render's floor carries a studio's soft grounding shadow, as deep
as the floor is opaque: darkest where the model touches it, the key light's cast
shadow softening and fading away from the model. The viewer re-renders its
shadows, and re-bakes this one, only for a change that can alter them: never
while the camera alone moves, and never for a hover, a selection or any other
highlight, which leave every part casting as it did (a highlighted part keeps
its shadow). While a routine plays or a pose is dragged, the key's cast shadow on the
floor follows every frame and the contact darkening under the model at most every
100 ms; once the model stops, both are baked for its final pose. A floor at zero
opacity bakes nothing, and a viewer that renders in software, whose key casts no
shadow, draws no floor shadow.
Its finish is Matte, or Glossy: a glossier floor that also reflects the model, crisp
where the model meets it and softening and fading over the model's height, as a
polished studio floor shows a product, in either appearance. The reflection is a
second draw of the scene at half the canvas's resolution, before each frame the camera
or the model moved in (about 4 ms of render CPU a frame on a large assembly); a hover
or selection keeps the last one and catches up within 400 ms. A Matte floor allocates
none of it and draws nothing extra, and switching back to Matte releases it. In
software, a glossy floor reflects nothing.
Its double-sided surface uses its actual elevation during
camera depth fitting, avoiding the origin-placement near-plane gap. Its color
and opacity are independent of Background.
The floor has no edge, as a product shot's seamless sweep has none: it is at its
opacity around the model and fades to nothing a few model radii out, its shadow and
reflection with it, so a low camera or a wide view shows no horizon line or corner.
Behind it, Background is a studio backdrop rather than a flat fill: its color lifted
toward white behind the middle of the frame, shaded toward the corners (more for a dark
color) and above the horizon. Its opacity carries the gradient; at zero it draws nothing.
Light Render defaults to a pure white background and retains the slightly gray
floor (`#e7e7e5`); dark Render's background and floor are one charcoal (`#202226`), never
black. Explicit background colors still override the mode default.
Pose and animation passes publish current placed bounds before
drawing, and so does the exploded view wherever it comes to rest (a slider move,
the end of its ease) and at most every 100 ms while it eases in or out. Depth and
lighting follow moving parts without changing camera framing or the floor's
footprint.

All modes share surface-under-cursor zoom, zero-pose framing and the fit
padding: 1.1 across, and 1.1 down on a square or narrower viewport, easing to
1.25 at 16:9 and wider (`interactiveFitPadding`), so a wide view leaves room
above and below the model. Mode changes do not refit, and neither does a
rebuild of the open file. Motion changes geometry, not what 100% means. A
changed camera clears current screen-space drawings; camera state republished
unchanged after a runtime replacement does not.

## Where the controls live

Display is a dropdown from the Display tile at the strip's end (the current mode's sphere,
between Projection and Preview: `kit/shell/DisplayPopover.jsx`), present for every 3D file:
the offered modes (`DisplayModeOptions.js`), then the Grid switch. On a phone it is the
More menu's Display submenu, the same list. Preview, a view of its own over the editor's,
draws the model in Render whatever the file's mode (the store's `renderScene()`, as
`kit/viewport/previewViewScene.js` draws it), and the tools view never does. Preview's own
settings are its settings panel (`kit/shell/PreviewSettings.jsx`: Orbit, then
`PreviewRenderSettings.jsx`), its edits the file's Preview settings. A file's model tree and Position are
sections of the file sidebar (see
[settings-ui.md](./settings-ui.md#the-file-sidebar-and-the-tool-stack)); nothing in them is
a display setting.

Display and Preview, the view's controls at the strip's end, are offered by a 3D view
alone, as its renderer declares to the shell (`useRendererShell`'s `previewable`):

| Renderer | Files | Display and Preview |
| --- | --- | --- |
| `xbf` | `.xbf`, STEP, STP | Yes |
| `glb` | GLB | Yes |
| `mesh` | STL, 3MF | Yes |
| `robot` | URDF, SRDF, SDF | Yes |
| `dxf` | DXF | No: a 2D drawing, on a surface of its own, without the shell |

A view without them has no Display or Preview control, not a disabled one, and a
request for Preview leaves its normal view as it is.
