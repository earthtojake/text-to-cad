# Snapshots

## Display presets

`--display` accepts `solid` (the default), `render`, `xray`, `hidden-line`,
`wireframe`, a JSON object, or a JSON file path. The CLI defaults to
`appearance: "light"`; use `"dark"` to request dark appearance. Presets supply
all group defaults. An omitted group inherits its preset; a supplied group
merges its parameters and implies `enabled: true` unless explicitly false.

```bash
cadgen step snapshot part.step review.png --display render
cadgen step snapshot part.step review.png --display '{"mode":"render","appearance":"dark","floor":{"enabled":false},"background":{"opacity":0.5}}'
cadgen step snapshot part.step review.png --display display.json --camera front
```

The public groups are `camera`, `surfaces`, `edges`, `lighting`, `background`,
`floor`, `grid`, and `axes`. `clip` and `exploded` remain independent inspection
tools. `--camera` or a job/output `camera` specifies pose and framing;
`display.camera` specifies projection and focal length (20–200 mm). Render
defaults to perspective; other presets use orthographic projection. Opacity is
0 for transparent and 1 for opaque, including partially transparent PNG
backgrounds. Unknown keys and retired modes are refused.

`edges`, `clip`, `exploded`, the `xray`, `hidden-line` and `wireframe` presets and
the `hidden` and `off` surface styles describe a CAD model: its topology edges,
its parts and its solids. They apply to STEP/STP inputs only. A mesh or a robot
description (STL, 3MF, GLB, URDF, SRDF, SDF) takes `solid` or `render`, the
`shaded` or `flat` surface style and the remaining groups, and refuses the rest
by name before anything is rendered.

## Meshes and robot descriptions

A GLB, an STL, a 3MF and a URDF, SRDF or SDF are drawn with the scene the CAD
Viewer draws for them: the snapshot's page and the viewer build it with the same
code, dress it in the same look for the same display settings, and pose it the
same way. A snapshot therefore cannot show one of these files differently from the
viewer; only the camera framing, the image size and the encoding are the
snapshot's own.

- A GLB is its own glTF scene: nodes, skins, morph targets and authored
  materials, drawn where its skins and morph weights put them. `solid` wears the
  viewer's surface over its colours, maps and opacity; `render` shows the finish
  the file authored. Its clips are the viewer's playbar: a snapshot draws the file
  at rest, lights and grounds it on the box its clips sweep, as the viewer does,
  and refuses `--animation` and `--video`.
- An STL is one object and a 3MF one per object (and per material within one),
  each in its colour. They author no finish: `solid` wears the viewer's surface and
  `render` the studio's.
- A robot is drawn where the viewer opens it: every joint at its default, then an
  SRDF's `home` group state, with the joints `--joint-values` names on top. A
  colour the description gives a visual wins over the colours its link mesh
  carries, and a link mesh that cannot be loaded fails the snapshot rather than
  leaving the link out.
- The ground is sized from the rest placement, so a pose never rescales it; only
  the floor's height follows a posed robot down.
- `--mode list` lists what the scene drew, one row per mesh: a `ref` naming it,
  its `name`, its triangle and vertex counts, and its bounds as drawn. For these
  inputs a ref is a name, not a selector: `--focus` and `--hide` are STEP-only.

## Drawings

A `.dxf` is not rendered in a scene at all, so `cadgen dxf snapshot` is the
narrowest door of the seven. It draws the whole drawing, fitted to the image and
head on, in the pens the file declares — the same picture the CAD Viewer's DXF
pane shows, from the same server-side payload, through the same drawing code.
What the viewer cannot show, the CLI does not render.

```bash
cadgen dxf snapshot plate.dxf review.png
cadgen dxf snapshot plate.dxf review.png --appearance dark --width 1600 --height 1000
```

It takes `TARGET`, `OUT`, `--job`, `--appearance` (`light`, the default, or
`dark`), `--width`/`--height`, `--size-profile`, `--debug` and `--json`, plus
`output.renderScale` and `output.transparent` in a job. An entity with no pen of
its own (ACI 7) is painted in the appearance's foreground on its background, so
`--appearance` is the whole of a drawing's display.

Everything that describes a scene is gone from the door rather than accepted and
ignored, and gone is not silent. `--camera`, `--display`, `--mode` and
`--view-labels` are out of the signature and out of `--help`, and passing one is
refused by name — what the flag meant, why a flat drawing has no such thing, and
what to pass instead — rather than reported as an unrecognized argument. A job
(or `cadgen snapshot` routing a `.dxf`) that carries `camera`,
any `display` key but `appearance`, `mode` other than `view`, `section`,
`scale`, an output `label`/`viewLabel`, or `output.padding`, `output.viewLabels`
or `output.tightFrame` is refused by name with what a drawing is — in the same
words, because the flag and the job key are one request arriving two ways.

## Requests and OUT

A request is accepted or refused before anything is built or deleted. Every
refusal that can be decided from the request, the input's kind and the files
beside it — unknown keys and values, a setting the input's kind cannot take, the
wrong door, conflicting options, an SRDF with no single paired URDF, an unknown
pose, clip or joint name — leaves an existing OUT untouched, for every job in a
packet. Only then is OUT cleared, so a failed build or render leaves no file
rather than the previous one. Occurrence refs are the one request check that
needs the built tree, so they are checked after the clear.

OUT's extension decides the encoding, and no job key does: view mode writes
`.png`, section mode `.png` or `.svg`, a video `.mp4` or `.gif`. Any other
extension is refused.

A job comes from `--job FILE` or from `TARGET OUT` and the flags; there is no
stdin form. With `--job`, each flag given overrides that setting in every job of
the packet, and `--width`/`--height` size every output.

## Section planes

`--mode section` draws the outline a plane cuts through a STEP model.
`--section PLANE[:OFFSET]` (job key `"section": {"plane", "offset"}`) places it:
`PLANE` is `XY` (the default), `XZ` or `YZ`, and `OFFSET` moves it along its own
normal in model units, defaulting to 0.

```bash
cadgen step snapshot part.step cut.svg --mode section --section XZ:12.5
```

Those are the only two keys, a `section` outside section mode is refused, and a
plane that misses the model returns an empty drawing with a warning.

## Sizes

An output is sized by `--size-profile` (`output.sizeProfile`) — `simple`
1200x900, `simple-square` 1024x1024, `diagnostic` 1600x1200 (the default),
`labeled` 1600x1200, `assembly` 1800x1200, `assembly-large` 1920x1440,
`presentation` 2400x1600, `presentation-large` 2800x1800, `contact-sheet`
2400x1600 — or by `--width`/`--height`, whole pixels from 1 to 8192. An unknown
profile or a size outside that range is refused, never clamped.
`output.padding` is 0–0.15, `output.renderScale` 1–3, and `timeoutSeconds` a
positive number, checked when the job is resolved.

## Diagnostics

`cadgen step snapshot part.step review.png --debug --json` adds diagnostics to
`SnapshotResult.debug`; without `--json` each entry prints as one `debug: {…}` line
after the saved paths. The same flag is available on the other snapshot doors
and as `debug=True` in Python. Every diagnostic entry identifies its input;
artifact-resolution information remains alongside `stageTimings`: a STEP entry's
`stepArtifact` names the `documentHash`, `tree` and store `view` it rendered,
their `componentCount` and `occurrenceCount`, and whether a `selectorIndex` was
composed. Normal results keep their file, warning and aggregate timing fields.

Still view renders report these measured browser durations in milliseconds:

| Field | Measured work |
| --- | --- |
| `loadSourceMs` | Source fetch, cached-mesh decoding or tessellation, and source composition |
| `preparePoseMs` | Requested animation loading/frame resolution and kinematics runtime preparation |
| `buildModelMs` | Render context and model/display-record construction |
| `prepareViewportMs` | Viewport, renderer and scene setup; this is not a draw |
| `waitViewportMs` | Waiting for the prepared viewport's asynchronous readiness |
| `captureMs` | Entire capture call, including readiness and all output stages below |

Exact-surface packages also report `stageTimings.sourceLoad`. Counts distinguish
`componentCount`, `cacheBatchCount`, `cacheHitCount` and `cacheMissCount`.
Measured durations are `probeMs` (metadata), `cacheReadMs` (bounded body fetch
and integrity validation), `cacheDecodeMs` (component views and metadata),
`meshBuildMs` (owned render arrays), and `composeMs` (occurrence composition).
Misses additionally measure `surfaceReadMs` (fetch and parse), `tessellateMs`
and `cacheWriteMs`. Miss-stage times sum per-component intervals across the
small concurrent pool, so they can overlap; absent stages are omitted.

`stageTimings.outputs` contains one measured entry per image, in output order,
with its `path` and these durations:

| Field | Measured work |
| --- | --- |
| `updateModelMs` | Output sizing, model pose/effects, exploded placement, topology edges and line resolution |
| `frameCameraMs` | Camera selection/fitting, including visible-vertex tight framing when enabled |
| `prepareStudioMs` | Camera depth and photographic studio setup; absent without a studio |
| `drawSubmitMs` | The renderer's synchronous draw call |
| `encodeImageMs` | Image readback, optional view label and PNG/data-URL encoding |

WebGL submission may return before GPU work finishes. `encodeImageMs` can
include waiting for that work; these fields are browser wall times, not GPU
profiler measurements. `captureMs` contains `waitViewportMs` and the output
stages, so do not add those overlapping durations together.

Only stages actually reported by the runtime are included. List, section and
video results do not invent still-image measurements. Invalid/nonfinite
values and image payloads are excluded from diagnostic output. Measurements
belong to one render call and cannot carry over from a previous job.

The ordinary `timings.total_ms` covers the render packet, including browser
startup, shutdown and writing its outputs. Input resolution happens before
that interval. The browser stages cover narrower work and need not add up to
that total or to the complete CLI process time. Use this attribution to choose
a targeted profile; a small model's stage proportions do not establish where
a larger assembly spends its time.

Photographic snapshots use the same floor placement as the Viewer. The
translucent floor defaults to the document's Z=0 plane. To place it at the
model's lowest point instead:

```bash
cadgen step snapshot part.step review.png --display '{"mode":"render","floor":{"placement":"lowest"}}'
```

`display.floor.placement` accepts `origin` (the default) or `lowest`; it moves
only the floor, never the model or lighting. `display.floor.enabled: false`
removes the floor.
