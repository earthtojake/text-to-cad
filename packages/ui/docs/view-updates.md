# Responsive View updates

View controls always edit the per-file `viewSettingsStore` immediately. That
store is the only settings authority. A mode is a preset batch; the renderer
never branches on its name. Rendering completion cannot rewrite controls,
persistence, feature gates, or the Custom label.

`kit/view-settings/viewUpdateCoordinator.js` owns one active operation and one replaceable
requested scene recipe. `kit/view-settings/useAppliedViewSettings.js` binds it to React.
Rapid edits replace pending work; they do not accumulate in a queue. Preparation
is cancellable. Once scene reconciliation starts it finishes serially, but a
superseded result is not presented. File changes/unmount cancel work and reject
outstanding captures. Errors leave controls editable and expose Retry.

## Cost policy

`kit/view-settings/viewUpdatePlan.js` is the single classification point. Compare resource
boundaries, never preset names:

| Preparation | Live update |
| --- | --- |
| Lighting enable, quality, softbox size/fill | Exposure, rotation |
| Surface style/color source, crossing opaque/transparent | Surface color, opacity within one transparency class |
| Edge enable/visibility | Edge color |
| Floor enable | Floor color, opacity, placement |
| Clip enable/disable | Clip position, Reverse and Part colours after preparation |
| Appearance shader change | Projection, background, grid, axes, Explode |

Both paths yield until the controls have painted, then apply the latest recipe.
Only the preparation path loads resources and compiles shader variants. Live
updates coalesce to the next frame and do not wait for an artificial debounce.

Explode and Clip are popovers from their strip tiles: the slider, the amount and Reset, and
Clip's axis dropdown with Part colours and Reverse. Editing the slider enables the effect;
Reset puts it back to neutral. Clip uses original model bounds for its slider and the rendered
plane, independent of pose and Explode. Its neutral endpoint is the maximum coordinate
(minimum when flipped). It has one active axis and plane. The slider starts neutral on the left and
advances from maximum to minimum coordinate; a flipped cut (`invert`) reverses that direction. CLI coordinates, including zero, remain supported. Clip and Explode stay outside mode presets.

## Renderer and resources

`kit/look/studioEnvironmentCache.js` keeps at most three reflection maps per GPU device,
shared by every viewport of the page (per viewport where there is no device). `studioEnvironment.worker.js` generates PMREM in worker WebGL and
transfers half-float pixels; model geometry stays on the main renderer. Rotation
and exposure reuse the map. Superseded work terminates the worker; completed
maps are reused by key. Workers terminate after transferring their pixels, so inactive tabs do not
retain extra WebGL contexts. Disposal releases textures and any pending worker. Browsers
without OffscreenCanvas/Worker use a synchronous compatibility path after the
controls paint; the full responsiveness benefit requires worker WebGL.

`kit/view-settings/viewUpdateGate.js` preserves the previous canvas framebuffer while the
scene is reconciled and Three's `compileAsync` prepares its programs. The
renderer/context and cached geometry stay mounted. `viewportBuffer.js` queues
canvas resolution changes and flushes them inside the next actual draw callback.
Changing DPR or dimensions outside that callback clears the retained frame, so
no quality effect or resize observer may resize the backing buffer directly. A viewport
resize DRAWS that frame instead, synchronously inside its ResizeObserver callback (after
layout, before paint): the canvas is sized 100% by CSS, and a frame requested from there
with `requestAnimationFrame` would land a frame late, painting the old picture stretched
over the new box whenever the viewer changes width in one step (a window snap). That synchronous frame replaces any queued one, so a drag still draws once
per frame, and an idle viewer draws nothing. While the gate holds, the draw is skipped
like any other, the buffer keeps its size, and the held picture waits for the frame that
releases it (`kit/viewport/ViewportResize.browser.test.mjs`). Presentation resumes after
preparation; completion is acknowledged after an actual draw. Camera input is
accepted during preparation, though the displayed pose can briefly wait while
the scene is held. Shader support and GPU drivers can still impose synchronous
work (notably shadow allocation/first draw); this is not a second renderer or a
promise that all GPU work is preemptible.

Screenshot/prompt capture awaits the coordinator's latest presented revision,
so it cannot accidentally capture a half-applied recipe. Ordinary snapshots
outside FileViewer retain their own scene setup lifecycle.

## Status placement

`kit/status/ViewUpdateStatus.jsx` only takes `status`, `onRetry`, and
`className`. It has no scene/store knowledge. RendererShell draws it centred under the tool
strip and the tool in hand's sub-toolbar, or at the top of the viewport in the strip's row
where there is no strip (preview, a load), without changing scheduling. It appears after 150ms with “Updating view…” (or
“Preparing section view…” for Clip), stays nonmodal, and never disables controls.
Fast changes produce no spinner. Failures show a retry action.

A job the engine runs behind the view -- a build rewriting the model on screen, a STEP's import
before anything is on screen -- says where it is in the engine's one progress event
(`kit/status/progressEvent.js`: `{kind, stage, job, outputs, detail, done, total, elapsedMs}`, the
engine's `progress.py`). The page reads its `kind` and `stage` and nothing of the engine's words: the
status line says `t("progress.<kind>.<stage>")` with the count where the stage has one ("Writing
files 1/2…", `modelUpdateStatus` and `statusLine`), and the loading overlay says the same key with
its fraction (`loadingState.js`), each in the view's language (`i18n/locales`, a key per stage of
every kind, held to the engine's vocabulary by `tests/python/global/test_progress_vocabulary_sync.py`).
A stage with no countable units says its stage alone; the page never times, guesses or invents a
fraction. The page's own loading steps (`Finding file`, `Loading geometry`, …) keep their closed
vocabulary beside it (`statusLabels.js`).

Tests cover latest-request wins, cancellation back to the visible recipe,
serialized reconciliation, failure/retry, capture readiness, disposal, and
StrictMode/control independence. Real browser checks must also exercise cold
Render, rapid preset/clip edits, a completed capture, and a warm return.
