# Snapshot diagnostics

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

Photographic snapshots use the same ground placement as the Viewer. The default
translucent floor remains at the document's original Z=0 plane, including when
geometry extends below it. To align the floor to the lowest point explicitly:

```bash
cadgen step snapshot part.step review.png --render '{"backdrop":{"groundPlacement":"lowest"}}'
```

`groundPlacement` accepts `origin` (the default) or `lowest`; it moves only the
floor, never the model or lighting. `backdrop.ground: false` removes the floor.
