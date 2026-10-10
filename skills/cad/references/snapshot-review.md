# Snapshots

A snapshot renders a saved document the way the CAD Viewer draws it:
`cadgen step snapshot` for STEP/STP, and the `stl`, `3mf` or `glb` command's
`snapshot` for a mesh (see [mesh exports](supported-exports.md)). It shows
arrangement and appearance; dimensions come from
[measurement](inspection-and-validation.md). The CAD topology, selection, section
and motion options below apply to STEP. A pose or clip frame takes `--kinematics`
and/or `--animation CLIP --time SECONDS`, and a clip can render to video; see
[kinematics](kinematics.md#reviewing-motion).

A STEP model with no surfaces (empty, or only curves and points) has nothing a
view can draw: the snapshot still writes its image and warns that the model has
no surfaces. A view or list that warns faces `could not be meshed` draws that part
without them (and a list counts it without them); they are usually slivers a
boolean left, and the warning names the part's ref and the faces (`#o1.2`, `f7`).

## Views

No fixed set of views shows every face. Opposed isometric views reveal more
exterior faces, orthographic views show patterns and silhouettes, and a section
shows internal geometry. Several views can share one JSON job:

```json
{
  "input": "models/part.step",
  "mode": "view",
  "outputs": [
    { "path": "/tmp/render/iso.png", "camera": "iso" },
    { "path": "/tmp/render/iso_opposite.png", "camera": { "direction": [-1, 1, -0.8] } },
    { "path": "/tmp/render/top_ortho.png", "camera": "top" },
    { "path": "/tmp/render/front_ortho.png", "camera": "front" }
  ],
  "output": { "viewLabels": true, "padding": 0.12, "sizeProfile": "diagnostic" }
}
```

Set `input` to the saved STEP/STP artifact using a relative or absolute path
(documents only: run a `.py` model first). With no explicit display settings,
snapshots use the `solid` preset, Light appearance and an orthographic isometric
camera. Every mode defaults to 1600x1200 (the `diagnostic` profile). Job `mode`
remains `view`, `section`, or `list`; display presets are a separate choice.

`--size-profile` (`output.sizeProfile` in a job) is one of exactly these names;
anything else is refused with this list:

| Profile | Size |
| --- | --- |
| `simple` | 1200x900 |
| `simple-square` | 1024x1024 |
| `diagnostic` (default), `labeled` | 1600x1200 |
| `assembly` | 1800x1200 |
| `assembly-large` | 1920x1440 |
| `presentation`, `contact-sheet` | 2400x1600 |
| `presentation-large` | 2800x1800 |

`--width`/`--height` (an output's `width`/`height` in a job) override the profile
with a whole number of pixels from 1 to 8192; a larger request is refused rather
than clamped. With `--job` they size every output in the packet.

`--display` accepts a preset name, inline JSON, or a JSON file path. The six
presets are `solid` (the default: shaded, with edge linework), `render`
(perspective projection and photographic lighting), `xray` (translucent surfaces
with occluded edges visible), `hidden-line` (linework with occluded edges
suppressed), `wireframe` (edges only) and `grid` (Solid on a finer, plainer
measuring grid; the only preset that draws the grid). Every preset but Render
starts with orthographic projection. `appearance` is `light` (the CLI default) or
`dark`. The Viewer and CLI accept the same grouped display object:

```bash
cadgen step snapshot STEP/part.step tmp/review.png --display render
cadgen step snapshot STEP/part.step tmp/review.png --display '{"mode":"render","floor":{"enabled":false},"background":{"opacity":0.5}}'
cadgen step snapshot STEP/part.step tmp/review.png --display display.json --camera front
```

Omitted groups inherit the chosen preset. A supplied group merges its parameters
with those defaults and implies `enabled: true`, unless `enabled: false` is
explicit. Every group below supports boolean `enabled`; opacity is 0 for fully
transparent and 1 for opaque.

| Group | Parameters |
| --- | --- |
| `camera` | `projection`: `orthographic` or `perspective`; `focalLength`: 20–200 mm |
| `surfaces` | `style`: `shaded`, `flat`, `hidden`, `off`; `colorMode`: `original`, `single`, `by-part`; hex `color`; 1–50 hex `colors`; `opacity`: 0–1 |
| `edges` | `visibility`: `visible` or `all`; hex `color` |
| `lighting` | `quality`: `preview` or `final`; `exposure`: -5–5; `rotation`: -180–180 degrees; `size`: 0.25–3; `fill`: 0–1 |
| `background` | hex `color`; `opacity`: 0–1, including partial PNG alpha |
| `floor` | `placement`: `lowest` or `origin`; `finish`: `matte` or `glossy`; hex `color`; `opacity`: 0–1 |
| `grid`, `axes` | hex `color`; `opacity`: 0–1 |

Render's floor sits at the model's lowest point; `placement: "origin"` moves it to
Z=0. `--camera` (or a job's top-level or per-output `camera`) sets pose and
framing (`preset`, `position`, `target`, `up`, `direction`, `zoom`,
`orthographicHalfHeight`); projection and focal length belong in
`display.camera`. `clip` and `exploded` are further `display` tools. `edges`,
`clip`, `exploded`, the `xray`, `hidden-line` and `wireframe` presets and the
`hidden`/`off` surface styles are STEP-only; meshes, drawings and robot
descriptions take `solid` or `render`.

For close views of a STEP, a JSON job can set `quality.tessellation` to
`{"chordTolerance": 0.0005, "angleTolerance": 0.10}` (chord relative to each
component's bounding diagonal, angle in radians; bounds `0.00005`–`0.05` and
`0.05`–`1.5708`, as for mesh exports). cadgen meshes the exact surfaces at those
tolerances for the image alone; finer costs memory and render time. Mesh
documents cannot be remeshed this way.

`camera` is a preset (`front`, `back`, `left`, `right`, `top`, `bottom`, `iso`),
an `azimuth:elevation` pair, or a camera object. `output` takes `sizeProfile`,
`padding` (0–0.15), `renderScale` (1–3) and the booleans `viewLabels`,
`tightFrame` and `transparent`. Top-level `timeoutSeconds` is a positive number
and `scale` is `cad` or `urdf`. Unknown keys and out-of-range values are refused.

### Flags and job keys

A JSON job's keys are the flags without their dashes. `--animation CLIP --time
SECONDS` is one `animation` object in a job; `time` is not a top-level key:

```json
{
  "input": "models/arm.step",
  "kinematics": "open",
  "animation": { "clip": "demo", "time": 2.0 },
  "outputs": [{ "path": "/tmp/render/demo_t2.png", "camera": "iso" }]
}
```

`clip` is required; `time` is seconds, default 0. A bare `"animation": "demo"` is
refused (that is the flag's spelling). A `"video"` object beside `animation`
renders the clip's span instead of one frame; see
[rendering the whole clip](kinematics.md#rendering-the-whole-clip).

`--focus` and `--hide` nest under a job-level `selection` object, which applies
to the whole job (give a view its own job in a `jobs` array to select per view):

```json
{
  "input": "STEP/assembly.step",
  "mode": "view",
  "selection": { "hide": ["#o1.3", "#o1.4"] },
  "outputs": [{ "path": "tmp/render/without_covers.png", "camera": "iso" }]
}
```

With `--job FILE`, other flags override every job in it; there is no stdin form.

## Section planes

`--mode section` cuts the model with a plane and draws the cut outline. Say where
with `--section PLANE[:OFFSET]`:

```bash
cadgen step snapshot STEP/housing.step tmp/cut.png --mode section --section XZ:12.5
cadgen step snapshot STEP/housing.step tmp/cut.svg --mode section --section YZ
```

`PLANE` is `XY`, `XZ` or `YZ` (default `XY`); `OFFSET` moves it along its normal
in model units (default 0), so `XZ:12.5` cuts at Y = 12.5. In a job it is
`"section": {"plane": "XZ", "offset": 12.5}` beside `"mode": "section"`. A plane
that cuts no material renders an empty drawing and warns. Section mode is
STEP-only and takes no kinematics, animation or Render display.

The cut is exact (a bore cut across its axis is a true circle), limited by
`--focus`/`--hide`, filled and hatched per solid; a sheet body's cut is lines
only. A `.svg` is the same drawing, y up, in model units from the point its
root's `data-origin` names, and needs no browser.

`--mode list` writes no image: it prints one row per placed part — its `ref`
(what `--focus`, `--hide` and `scene.resolve(ref)` accept), its `name`, its exact
`bounds` in model units, and the `triangleCount`/`vertexCount` of the display
mesh a view would draw. `--focus`/`--hide` narrow the rows. A STEP list starts no
browser, so it is the cheap way to learn what an assembly contains.

OUT's extension picks the format: section mode writes `.png` or `.svg`, view
mode `.png`, a video `.mp4` or `.gif`; any other extension is refused.

## Output paths

OUT (and an output's `path` in a job) is written exactly as given, relative to
the working directory. A refused request (an unknown key, value, pose, clip or
joint, or an option this input cannot take) leaves an existing file untouched,
so after a refusal the path can still hold an older image. An accepted request
clears the target first, so a failed build or render leaves no file. A directory
as OUT gets a timestamped name, printed on the `saved snapshot:` line.
