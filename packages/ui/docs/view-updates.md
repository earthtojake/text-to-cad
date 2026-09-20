# Responsive View updates

View controls always edit the per-file `viewSettingsStore` immediately. That
store is the only settings authority. A mode is a preset batch; the renderer
never branches on its name. Rendering completion cannot rewrite controls,
persistence, feature gates, or the Custom label.

`render/viewUpdateCoordinator.js` owns one active operation and one replaceable
requested scene recipe. `workbench/useAppliedViewSettings.js` binds it to React.
Rapid edits replace pending work; they do not accumulate in a queue. Preparation
is cancellable. Once scene reconciliation starts it finishes serially, but a
superseded result is not presented. File changes/unmount cancel work and reject
outstanding captures. Errors leave controls editable and expose Retry.

## Cost policy

`render/viewUpdatePlan.js` is the single classification point. Compare resource
boundaries, never preset names:

| Preparation | Live update |
| --- | --- |
| Lighting enable, quality, softbox size/fill | Exposure, rotation |
| Surface style/color source, crossing opaque/transparent | Surface color, opacity within one transparency class |
| Edge enable/visibility | Edge color |
| Floor enable | Floor color, opacity, placement |
| Clip enable/disable | Clip position and Flip after preparation |
| Appearance shader change | Projection, background, grid, axes, Explode |

Both paths yield until the controls have painted, then apply the latest recipe.
Only the preparation path loads resources and compiles shader variants. Live
updates coalesce to the next frame and do not wait for an artificial debounce.

Clip's plus starts an X center cut (50% of bounds), with Flip off. Disabling
clears its overrides; reopening restores this default. Explicit coordinates,
including zero, remain supported. Explode similarly starts at 50% when enabled
and reopened; editing it to zero keeps the control open. Clip and Explode stay
outside mode presets.

## Renderer and resources

`render/studioEnvironmentCache.js` keeps at most three reflection maps per
viewport. `studioEnvironment.worker.js` generates PMREM in worker WebGL and
transfers half-float pixels; model geometry stays on the main renderer. Rotation
and exposure reuse the map. Superseded work terminates the worker; completed
maps are reused by key. Workers terminate after transferring their pixels, so inactive tabs do not
retain extra WebGL contexts. Disposal releases textures and any pending worker. Browsers
without OffscreenCanvas/Worker use a synchronous compatibility path after the
controls paint; the full responsiveness benefit requires worker WebGL.

`render/viewUpdateGate.js` preserves the previous canvas framebuffer while the
scene is reconciled and Three's `compileAsync` prepares its programs. The
renderer/context and cached geometry stay mounted. `viewportBuffer.js` queues
canvas resolution changes and flushes them inside the next actual draw callback.
Changing DPR or dimensions outside that callback clears the retained frame, so
no quality effect or resize observer may resize the backing buffer directly. Presentation resumes after
preparation; completion is acknowledged after an actual draw. Camera input is
accepted during preparation, though the displayed pose can briefly wait while
the scene is held. Shader support and GPU drivers can still impose synchronous
work (notably shadow allocation/first draw); this is not a second renderer or a
promise that all GPU work is preemptible.

Screenshot/prompt capture awaits the coordinator's latest presented revision,
so it cannot accidentally capture a half-applied recipe. Ordinary snapshots
outside FileViewer retain their own scene setup lifecycle.

## Status placement

`components/viewer/ViewUpdateStatus.jsx` only takes `status`, `onRetry`, and
`className`. It has no scene/store knowledge. The FileViewer currently places it
at the viewport's bottom left. Move that invocation or reuse the component
without changing scheduling. It appears after 150ms with “Updating view…” (or
“Preparing section view…” for Clip), stays nonmodal, and never disables controls.
Fast changes produce no spinner. Failures show a retry action.

Tests cover latest-request wins, cancellation back to the visible recipe,
serialized reconciliation, failure/retry, capture readiness, disposal, and
StrictMode/control independence. Real browser checks must also exercise cold
Render, rapid preset/clip edits, a completed capture, and a warm return.
