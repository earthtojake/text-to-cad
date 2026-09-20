# Snapshot review

Read this file when choosing visual checks for saved STEP/STP or mesh outputs.
Use `cadgen step snapshot` for STEP, or the corresponding `stl`, `3mf` or `glb`
snapshot command for meshes (see [mesh exports](supported-exports.md)). The
CAD topology, selection, section and motion controls below apply to STEP.

## Policy

Every created or visibly updated part or assembly gets at least one reviewed
PNG snapshot of its STEP, or its mesh when no STEP is declared. Passing geometry
checks does not waive this visual review. Use the format's snapshot command.
For a STEP pose or clip frame, pass `--kinematics` and/or
`--animation CLIP --time SECONDS`. A motion review may additionally need video;
see [kinematics](kinematics.md#reviewing-motion).

Skip saved snapshots only when no visible geometry was created or updated, or no valid artifact exists:

- pure format/export requests where geometry is unchanged
- source changes that do not alter visible geometry
- inspection-only tasks (for example direct measurement questions) that create or update nothing
- failed Python or STEP generation before a valid artifact exists

When skipping, report the reason and the deterministic evidence that still ran.

Do not loop on snapshots. Rerender only when a source repair changed visible geometry or when a specific visual finding needs confirmation.

## Packet sizing

Choose views that expose the features being checked. One may be enough;
add an opposing view for hidden exterior features, an orthographic view for
a pattern or silhouette, or a section for internal geometry. No fixed set of
views proves every face or feature is correct.

## Small packet

For example, a four-view comparison can use one JSON job:

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

Use only the views relevant to the design. Opposed isometric views reveal more
exterior faces, but neither they nor orthographic views reveal all occluded geometry.

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

`--display` accepts a preset name, inline JSON, or a JSON file path. The five
presets are `solid` (default), `render`, `xray`, `hidden-line`, and `wireframe`.
Render starts with perspective projection and photographic lighting; the other
presets start with orthographic projection. `appearance` is `light` (the CLI
default) or `dark`. The Viewer and CLI accept the same grouped display object:

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
| `floor` | `placement`: `lowest` or `origin`; hex `color`; `opacity`: 0–1 |
| `grid`, `axes` | hex `color`; `opacity`: 0–1 |

Render's floor defaults to the document's Z=0 plane. `placement: "lowest"` moves
it to the model's minimum Z, moving neither geometry nor lighting. `--camera` or a top-level/output
`camera` controls pose and framing (`preset`, `position`, `target`, `up`,
`direction`, `zoom`, `orthographicHalfHeight`); projection and focal length belong
only in `display.camera`. `clip` and `exploded` remain independent inspection tools
under `display`. Selection, kinematics, robot joint values, animation frames and
video compose with every display preset where the source format supports them.
`edges`, `clip`, `exploded`, the `xray`, `hidden-line` and `wireframe` presets and
the `hidden`/`off` surface styles are STEP/STP-only: a mesh, drawing or robot
description has no CAD edges, parts to explode or solids to section, and its
snapshot door refuses them by name. Those inputs take `solid` or `render`.
The old `display.render`, `guides` and `partColor` fields and old display-mode
names are rejected. Use the group table above when updating a saved JSON file.

For close macro views in normal CAD, a JSON job can set `quality.tessellation` to
`{"chordTolerance": 0.0005, "angleTolerance": 0.10}`. Chord tolerance is
relative to each component's bounding diagonal; angle tolerance is radians.
These positive numeric overrides retessellate the exact STEP surfaces and use
separate shared-cache entries. They do not change the STEP geometry or a model's
declared mesh-export tolerances. Use them only when visible faceting needs finer
sampling; lower tolerances cost more memory and render time. `chordTolerance`
must be at least `0.00001` and `angleTolerance` at least `0.005` — finer than
that exhausts the renderer instead of improving the image, and the job is
refused.
Existing mesh documents cannot be retessellated this way. The explicit top-level
sampling request works in every display mode. When it is omitted,
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

`clip` names a clip embedded in the document sidecar's animation and is required;
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
is refused. A plane that misses the model renders an empty drawing with a
warning that says so. Section mode is STEP-only, and takes no kinematics,
animation or Render display.

OUT's extension picks the format and nothing else does: section mode writes
`.png` or `.svg`, view mode writes `.png`, and a video writes `.mp4` or `.gif`.
Any other extension — a view named `.svg` or `.jpg` — is refused instead of
writing PNG bytes under it.

## Output paths

Name the file and you get that file:

```bash
cadgen step snapshot STEP/bracket.step tmp/review.png
# then Read tmp/review.png
```

OUT (and an output's `path` in a JSON packet) is written exactly as given,
relative to the working directory. Check the command's exit before reading. A
refused request — an unknown key or value, a setting this kind of input cannot
take, the wrong door, conflicting options, an unknown pose, clip or joint name —
leaves an existing file untouched, for every job in a packet. Once the request is
accepted the target is cleared before anything is built, so a failed build or
render (and an occurrence ref the model does not have, which needs the built
tree to check) leaves no file; successful output is written atomically.
Reuse `tmp/review.png` during iteration, or name before/after images when both
are needed for comparison.

Pass a directory (`tmp/` as OUT, or an output `path` that is one) only when the name does not matter: a timestamped name is generated inside it, and that is the one case where you read the path from the `saved snapshot:` line.

## Targeted additions

Add views only when the brief or a failure mode calls for them:

- reference-image reproduction: one snapshot from the reference image's viewpoint for side-by-side comparison
- `--mode section --section PLANE[:OFFSET]`: shell, bore, internal cavity, passage, blind hole, enclosure, or wall/floor relationship (see [Section planes](#section-planes))
- `display.mode: "solid"`: shaded CAD view with visible edge linework
- `display.edges.enabled: false`: shaded surfaces without the edge overlay
- `display.mode: "xray"`: translucent surfaces with hidden/occluded edges visible
- `display.mode: "hidden-line"`: line-focused review with occluded edges suppressed
- `display.mode: "wireframe"`: edge-only review for internal overlap or interference
- labeled or annotated review: use supported CAD Viewer refs, selections, screenshots, or GUI review links

Exploded or labeled review is an intent, not a render mode. Satisfy it through supported CAD Viewer mechanisms, supported JSON job settings, or the GUI link.

## Diagnostic review

Visual review is diagnostic, not authoritative. Convert every visual concern into a follow-up geometry check before using it as a validation claim:

- hole pattern appears asymmetric -> measure hole centers and compare offsets
- lid, child part, or occurrence appears offset -> inspect frames and mating deltas
- gusset, boss, standoff, rib, or plate may be floating -> inspect solid count, labels, connectivity, contact, or relevant distances
- cavity, bore, or blind hole looks wrong -> run section review, then measure wall thickness, depth, or through-condition
- repeated pattern looks uneven -> measure pattern centers, angular spacing, or occurrence frames

Final reports should include the generated snapshot PNGs or the documented skip reason, and state which deterministic checks support any visual finding.
