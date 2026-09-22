# View presets and grouped settings

The CAD viewer and snapshots consume one grouped display contract. **Solid**,
**Render**, **X-ray**, **Hidden line**, and **Wireframe** are presets over that
contract, not separate lists of settings. `common/viewSettings.js` in core owns
normalization, defaults, group gates, Custom detection and Reset.
`common/sceneSettings.js` translates the resolved groups into the renderer recipe.

The binding control patterns are in [settings-ui.md](./settings-ui.md); host
injection and agent commands are in [viewer-host.md](./viewer-host.md). The shared
UI does not discover app storage, transport or desktop APIs.

## Viewer mode choices

| Preset | Surfaces / edges | Lighting, background, floor | Projection |
| --- | --- | --- | --- |
| Solid (default) | Authored opaque shading / visible edges | Neutral workbench defaults | Orthographic |
| Render | Authored shading / edges off | Enabled | Perspective |
| X-ray | 22% surface opacity / all edges | Neutral workbench defaults | Orthographic |
| Hidden line | Depth-only surfaces / visible edges | Neutral workbench defaults | Orthographic |
| Wireframe | No surface fill / all edges | Neutral workbench defaults | Orthographic |

Render is option two. Grid and origin axes default on outside Render, off in
Render. All settings remain available in every preset. Changing a view value
shows **Custom**, retaining the selected preset as the reset target. Returning
all values to their preset values restores its name. Custom is derived, never
stored as a preset ID.
The dropdown shows Custom as a muted placeholder with no selected option.
Only presets appear in its list. Selecting the remembered base preset reapplies
its defaults.

## State and updates

`kit/view-settings/viewSettingsStore.js` owns one canonical, sparse display state per
mounted file. `useViewSettings` subscribes React to that store. UI controls and
live agent commands use the same explicit operations: `patch`, `setEnabled`,
`selectPreset`, `reset`. Session restoration uses `restore` once on mount;
persistence reads `getSnapshot().display`, including edits accepted before the
next React render. Never merge against a control's captured props, feed resolved
defaults back into the store, or maintain another display state alongside it.

The store derives the scene recipe and preserves equal JSON branches. The
viewport's render-state resolver preserves those identities through its internal
normalization. A Clip edit changes clipping only; it does not invalidate surface
materials, lighting, geometry or camera. No-op actions publish no update.
Projection/lens flow down as camera props and the viewport applies them once.
Camera pose remains viewport-owned, separate from preset settings.

Selecting a preset replaces visual overrides, including projection/lens. **Reset**
restores that selected preset and disables Clip/Explode. Selecting a preset
preserves those tools. Neither action changes camera viewpoint/zoom, selection,
visibility, the open panel or the model's pose.
Projection remains editable in every preset, including orthographic Render.

## Groups and enablement

| Group | Controls | Disabled behavior |
| --- | --- | --- |
| Camera | Projection in Mode; standard 50mm perspective lens | No UI gate |
| Surfaces | Shaded/flat/hidden/off, original/single/by-part colors, opacity | Always expanded; Off is an explicit surface style |
| Edges | Visible/all, color | No CAD edges |
| Lighting | Quality, exposure, rotation, softbox size, fill | Neutral CAD lighting/reflections |
| Background | Color and opacity | Natural light/dark workbench background |
| Floor | Origin/lowest point, color and opacity | No floor |
| Grid | Color and opacity | No grid |
| Axes | Color and opacity (same default color as Grid) | No origin axes |

Expanded means enabled. A disabled section is gray and collapsed. Clicking or
keyboard-activating its title/plus enables it. Only the minus disables it.
Hover changes styling only: moving the pointer, scrolling or closing a dropdown
must never change settings or turn a preset into Custom. Disabling removes
custom values in that group. Re-enabling starts from preset values.
This is feature state, not a separate accordion preference.

There is no redundant Floor checkbox or Background transparency toggle. Color
pickers include opacity, with an opaque checkerboard behind the color swatch:
0% is transparent, 100% opaque. The background's fractional alpha reaches the
actual canvas and PNG, not just the preview.

**Mode** and **Surfaces** stay visible. Explode is gated: collapsing clears its
amount and reopening starts at 50%; editing back to 0% does not auto-collapse.
Clip follows the
same gate rule: disabling discards its offsets and Flip; re-enabling restores
the default X center cut. Preset selection preserves Clip/Explode; Display Reset
disables both tools. Grid and Axes are independent sections.
The fixed panel order is Mode, Surfaces, Explode, Clip, Edges, Grid, Axes,
Lighting, Background, Floor. Preset changes never reorder controls.
The remaining optional effects use the same feature gate primitive. A surface
gate that just restores ordinary shading is not a meaningful disable action.
The Lens slider and Camera section are omitted: perspective uses the standard
50mm focal length. Focal length remains in the camera/display API for scripted
framing and snapshots, but is not a routine viewer control.

## Sparse public contract

```json
{
  "mode": "render",
  "appearance": "light",
  "camera": { "projection": "orthographic" },
  "lighting": { "enabled": false },
  "background": { "color": "#ffffff", "opacity": 0.4 },
  "floor": { "placement": "origin", "color": "#dddddd", "opacity": 0.8 }
}
```

- Omitted mode is `solid`. Omitted groups inherit the selected preset.
- A partial group overrides only supplied properties and implicitly enables the
  group unless `enabled: false` is explicit. Empty `{}` enables preset values.
- `enabled: false` resolves to the group's neutral behavior regardless of stored
  values. The UI removes those values when disabling; a CLI payload may contain
  disabled values but they have no effect.
- `clip` and `exploded` remain tool groups outside Custom and preset selection.
  Display Reset disables them.
- Viewer appearance inherits its host; snapshots default to `light`.
  Explicit `appearance: "light" | "dark"` overrides that baseline.
- Interactive lighting defaults to Preview; snapshots to Final. Core takes this
  as an explicit context baseline, so omitted quality is not Custom. A supplied
  `lighting.quality` overrides the baseline.

The same shape powers live `setDisplaySettings` and snapshot `--display`.
`--display render` is shorthand for the Render preset. JSON or a JSON file can
supply partial grouped overrides. `--camera` contains pose/framing only;
projection and focal length belong to `display.camera`. No `--render`, nested
`display.render`, legacy `guides`/`partColor`, or old mode IDs are accepted at new
public command boundaries. Only saved file sessions migrate those old fields.

The renderer still has lower-level material/depth mode IDs internally. They are
implementation details derived from surfaces/edges; never persist them or expose
them as public display values.

## Rendering costs and camera behavior

The photographic rig stays lazy. Enabling Lighting creates the photographic
softbox environment; Floor or Background alone retain neutral lighting and do
not create a photographic environment. Material information remains read-only
and is shown in the Model reference section. Color overrides are presentation
settings, not edits to the model or its material assignments.

| Lighting quality | Screen error | Shadow map | Environment | Capture scale |
| --- | --- | --- | --- | --- |
| Preview | 1 px | 2048 px | 256 px | 1× |
| Final | 0.25 px | 4096 px | 512 px | 2× |

The interactive viewer retains one WebGL renderer, canvas and camera controls
across every preset and settings edit. It uses shadow-compatible conventional
depth throughout, fitting near/far planes to the current model, closeup records
and floor/grid planes on every frame. The grid's bounds also fit the far plane;
it remains visible when Floor is off. Grid spacing is five cells across the
default model framing. The grid, the stage and the Render studio's floor are
SIZED from the model's rest placement for every renderer, STEP included: a pose, a
playing routine, or entering Render while the model is posed never rescales or
slides the ground; its height, the lighting and the shadow reach follow the model. Enabling photographic effects updates that live scene;
it never clears or covers the canvas with a loading screen. Only actual context
recovery replaces the renderer. Quality refines tessellation within the same
cache and memory budget. Picking/topology stays demand-driven in every preset.

Opening Clip starts a center cut and prepares its shader/cap variants before
presentation. Moving an enabled cut stays live. Explicit neutral boundaries
still avoid unnecessary caps. See [responsive View updates](view-updates.md)
for scheduling, resource caching, loading presentation and capture readiness.

Floor defaults to model origin (Z=0), 60% opacity, with Lowest point available.
Its double-sided shadow-receiving surface uses its actual elevation during
camera depth fitting, avoiding the origin-placement near-plane gap. Its color
and opacity are independent of Background.

All presets share surface-under-cursor zoom, zero-pose framing and the 1.1 fit
padding multiplier. Preset changes do not refit. Motion changes geometry, not
what 100% means. A changed camera clears current screen-space drawings; camera
state republished unchanged after a runtime replacement does not.

## Panel structure

Display is its own panel in the nav row, beside the file's own. A STEP's own
panel stacks **Features**, **Position** (only when the sidecar declares
kinematics) and **Issues** (only when there are any) under headings that never
collapse. Within Position the `Pose` row precedes the joint rows; each is
independently present only when its content exists, without an enable switch.
There are no tabs and no drag or split behavior. The file's own panel stays
mounted while Display is open, so the Features tree keeps disclosure and scroll.
The floating interaction toolbar owns Select/Measure (STEP only)/Draw, plus
Position and Animate where a file has joints or routines, and on a STEP,
Fullscreen last where the host offers it; view actions and capture remain
separate. A robot description's own panel stacks Position, Links and (for an
SDF) SDF.
