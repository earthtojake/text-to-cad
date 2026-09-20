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
its parts and its solids. They apply to STEP/STP inputs only. Every other input
(STL, 3MF, GLB, DXF, URDF, SRDF, SDF) takes `solid` or `render`, the `shaded` or
`flat` surface style and the remaining groups, and refuses the rest by name
before anything is rendered.

## Diagnostics

`cadgen step snapshot part.step review.png --debug --json` adds diagnostics to
`SnapshotResult.debug`. The same flag is available on the other snapshot doors
and as `debug=True` in Python. Every diagnostic entry identifies its input;
existing artifact-resolution information remains alongside `stageTimings`.
Normal results keep their file, warning and aggregate timing fields.

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
