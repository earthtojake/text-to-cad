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

Render's floor defaults to the model's lowest point (`placement: "lowest"`, its
minimum Z), as in the Viewer. `placement: "origin"` moves it to the document's Z=0
plane, moving neither geometry nor lighting. `--camera` or a top-level/output
`camera` controls pose and framing (`preset`, `position`, `target`, `up`,
`direction`, `zoom`, `orthographicHalfHeight`); projection and focal length belong
only in `display.camera`. `clip` and `exploded` remain independent inspection tools
under `display`. Selection, kinematics, robot joint values, animation frames and
video compose with every display preset where the source format supports them.
`edges`, `clip`, `exploded`, the `xray`, `hidden-line` and `wireframe` presets and
the `hidden`/`off` surface styles are STEP/STP-only: a mesh, drawing or robot
description has no CAD edges, parts to explode or solids to section, and its
snapshot door refuses them by name. Those inputs take `solid` or `render`.

For close macro views in normal CAD, a JSON job can set `quality.tessellation` to
`{"chordTolerance": 0.0005, "angleTolerance": 0.10}`. Chord tolerance is
relative to each component's bounding diagonal; angle tolerance is radians.
These positive numeric overrides have cadgen mesh the exact STEP surfaces at
those tolerances, stored as separate mesh entries. They do not change the STEP geometry or a model's
declared mesh-export tolerances, and lower tolerances cost more memory and render
time. `chordTolerance` must be from `0.00005` to `0.05` and `angleTolerance` from
`0.05` to `1.5708` radians, the same bounds as a mesh export's; finer sampling
costs minutes of meshing instead of improving the image, and a job outside them is
refused. Existing mesh documents cannot be remeshed this way. The explicit
top-level sampling request works in every display mode. When it is omitted,
`display.lighting.quality` selects the photographic preview or final LOD.

Scene setup, output capture and geometric sampling are separate closed objects.
`display` carries the grouped view settings.
`camera` carries the common pose and framing: a preset (`front`, `back`, `left`,
`right`, `top`, `bottom`, `iso`), an `azimuth:elevation` pair of exactly two
numbers, or a camera object. `output` supports `sizeProfile`, `padding` (0–0.15),
`renderScale` (1–3) and the booleans `viewLabels`, `tightFrame` and
`transparent`. Top-level `quality` supports exact-surface tessellation, and
`timeoutSeconds` is a positive number of seconds. Scene units use the top-level
`scale` (`cad` or `urdf`). Unknown keys and out-of-range values are refused, so a
misspelling cannot render the wrong thing quietly.

### Flags and job keys

A JSON job's keys are the flags without their dashes, and the job is the only
place some shapes exist. `--animation CLIP --time SECONDS` is ONE request, so a
job carries it as one `animation` object — `time` is not a top-level job key:

```json
{
  "input": "models/arm.step",
  "kinematics": "open",
  "animation": { "clip": "demo", "time": 2.0 },
  "outputs": [{ "path": "/tmp/render/demo_t2.png", "camera": "iso" }]
}
```

`clip` names a clip in the document's sidecar and is required;
`time` is seconds, finite and >= 0, defaulting to 0. A bare clip name is the
FLAG's spelling, not the job's: `"animation": "demo"` is refused, as is any key
the job does not support — the error lists the supported set.

A `"video"` object beside it renders the clip's SPAN into the `.mp4` or `.gif`
the single output names, instead of one frame: `{"fps": 30, "seconds": <what is
left of the clip>, "start": 0, "quality": "review", "loop": true}`, every key
optional and every other key refused. It needs `animation`, refuses an
`animation.time`, refuses a `start` past the end of the clip, and needs ffmpeg
installed. See `kinematics.md`, "Rendering the whole clip".

In a JSON job these two flags are the one exception to "job key = flag name without dashes": they nest under a job-level `selection` object, and a top-level `"hide"` or `"focus"` is rejected as an unknown key. Selection applies to the whole job, not to one output — to hide or focus parts for a single view, give that view its own job in a `jobs` array.

```json
{
  "input": "STEP/assembly.step",
  "mode": "view",
  "selection": { "hide": ["#o1.3", "#o1.4"] },
  "outputs": [{ "path": "tmp/render/without_covers.png", "camera": "iso" }]
}
```

`"selection": { "focus": ["#o1.2"] }` is the `--focus` form; `focus` and `hide` are the only selection keys. Every other flag keeps the plain rule (`--kinematics` → `"kinematics"`, `--animation CLIP --time S` → `"animation": {"clip": ..., "time": ...}`, `--section XZ:12.5` → `"section": {"plane": "XZ", "offset": 12.5}`).

With `--job`, the other flags override the packet: each one given replaces that
setting in every job, and `--width`/`--height` size every output. A job is a
file; there is no stdin form.

## Section planes

`--mode section` cuts the model with a plane and draws the cut outline. Say where
with `--section PLANE[:OFFSET]`:

```bash
cadgen step snapshot STEP/housing.step tmp/cut.png --mode section --section XZ:12.5
cadgen step snapshot STEP/housing.step tmp/cut.svg --mode section --section YZ
```

`PLANE` is `XY`, `XZ` or `YZ` — the two axes the plane contains — and defaults to
`XY`. `OFFSET` moves the plane along its own normal in model units (Z for `XY`,
Y for `XZ`, X for `YZ`) and defaults to 0, so `XZ:12.5` cuts at Y = 12.5. In a job
it is `"section": {"plane": "XZ", "offset": 12.5}` beside `"mode": "section"`;
those are its only two keys, and a `section` on a job whose mode is not `section`
is refused. A plane that cuts no material — it misses the model, only touches
it, or meets nothing but curves — renders an empty drawing with a warning that
says so. Section mode is STEP-only, and takes no kinematics, animation or Render
display.

The cut is exact: cadgen sections each part's solid with the plane, so a bore
cut across its axis is a true circle, not a polygon. `--focus` and `--hide` pick
the parts that are cut. Each solid's cut is filled and hatched (a face lying in
the plane counts), outlined in the appearance's foreground (or
`display.edges.color`), with dash-dot centre lines and a cut locator;
`--view-labels` adds the plane's label. A surface (sheet) body's cut is drawn as
lines and never filled. A `.svg` is the same drawing, y up, in model units
measured from the point its root's `data-origin` names: `0 0`, unless the cut
lies far from the origin. A job whose outputs are all `.svg` needs no browser.

`--mode list` writes no image: it prints one row per placed part — its `ref`
(what `--focus`, `--hide` and `scene.resolve(ref)` accept), its `name`, its exact
`bounds` in model units, and the `triangleCount`/`vertexCount` of the display
mesh a view would draw. `--focus`/`--hide` narrow the rows. A STEP list starts no
browser, so it is the cheap way to learn what an assembly contains.

OUT's extension picks the format and nothing else does: section mode writes
`.png` or `.svg`, view mode writes `.png`, and a video writes `.mp4` or `.gif`.
Any other extension — a view named `.svg` or `.jpg` — is refused instead of
writing PNG bytes under it.

## Output paths

Name the file and you get that file:

```bash
cadgen step snapshot STEP/bracket.step tmp/review.png
```

OUT (and an output's `path` in a JSON packet) is written exactly as given,
relative to the working directory. A refused request — an unknown key or value,
a setting this kind of input cannot take, the wrong door, conflicting options, an
unknown pose, clip or joint name — leaves an existing file untouched, for every
job in a packet, so after a refusal the path can still hold an older image. Once
the request is accepted the target is cleared before anything is built, so a
failed build or render (and an occurrence ref the model does not have, which
needs the built tree to check) leaves no file; successful output is written
atomically.

Pass a directory (`tmp/` as OUT, or an output `path` that is one) only when the name does not matter: a timestamped name is generated inside it, and that is the one case where you read the path from the `saved snapshot:` line.
