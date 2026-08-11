# Implicit raymarch performance: findings and plan of attack

## 0. Execution status — P1–P5 DONE, P6 not needed

| Step | Status |
|---|---|
| P1 demand-driven re-queue | **DONE** |
| P2 interaction-quality uniforms for camera moves | **DONE** |
| P3 idle-restore hysteresis (400 ms, two-stage) | **DONE** |
| P4 fixed interaction pixel budget | **DONE** |
| P5 background out of the shader | **DONE** (scissor half: **not needed**, see below) |
| P6 shader-side tuning | **NOT NEEDED** — measurements below leave nothing to chase |

Measured on `planetary-gear.implicit.js` at 2560×1330 css @ DPR 2 (≈13.6 M pixels),
Metal-backed Chromium. OLD = pre-integration `ImplicitCadViewer`:

| Scenario | OLD | Before P1 | **After P1–P5** |
|---|---|---|---|
| Orbit drag | 45.1 fps | 54.6 fps | **116.4 fps** |
| Discrete wheel | 51.2 fps | 18.2 fps | **113.5 fps** |
| 60 Hz trackpad pinch | 27.9 fps, p95 84 ms | 16.0 fps, p95 250 ms | **100.9 fps, p95 16.7 ms** |
| Idle | 0 app frames | 0 app frames | **0 app frames** |
| Gesture-end restore | — | — | **one 25 ms frame, none over 50 ms** |

Frame counts confirm this is real rendering, not a starved loop: a 4.4 s orbit drag issues
**524 app frames (119 fps)** and a 60 Hz pinch **339 frames (78 fps)**, while idle issues
**zero**. Quality is deferred, never lost — with the camera held still, triggering the
interaction tier and letting it restore returns a **pixel-identical** frame (0.000 % of
pixels differ); mid-gesture 12.5 % differ, which is the cheap tier doing its job.

### Why the scissor half of P5 was dropped

P5's scissor was justified by an expected 2–4× on fill cost. After P1–P4 the renderer is
vsync-bound in every interactive scenario and idle costs nothing, so a scissor would buy
headroom no user can observe, in exchange for per-frame bounds projection and scissor
state in the shared loop. It is recorded here as the first lever to pull if a slower GPU
ever needs one; nothing in the current code blocks it.

### P5's background split shipped for CONSISTENCY, not speed

The shader used to paint its own background, which is why the integration had to suppress
the shared grid, stage floor and scene background: the pass was opaque and drew over them.
That left implicits as the only format without the themed grid — a real divergence, and
the reason this half shipped anyway.

The pass now composites instead of replacing. `uPaintBackground` (default 1, so the
snapshot CLI and `renderImplicitCadToDataUrl` are untouched) is turned off by the viewer;
misses emit the stage-floor shadow as black-with-alpha, so ordinary blending darkens the
shared floor exactly as multiplying the background used to. The quad draws last with
depth off. `CadViewer` no longer suppresses anything, and `handleImplicitModelBounds`
sizes the shared grid, stage and lighting scope from the implicit's own bounds.

Result: implicits render the **same** themed background, grid, stage floor and lighting as
STL/GLB/3MF/STEP/DXF. Verified pixel-identical background against an STL under the Dark
theme (delta 0 at every sample point). A side effect: the full-corpus sweep is now **47/47
non-blank** — `menger-sponge`, whose field is empty, at least draws the shared stage.

Investigation of "the implicit renderer in the viewer is extremely slow" after the
shared-render-type integration (`design/implicit-shared-viewer-integration.md`). The
verdict is **both**: one real regression introduced by the integration, sitting on top of
an inherent fill-rate cost the old viewer had too and that a fullscreen retina window
exposes. The plan fixes the regression first (small, surgical), then attacks the
inherent cost in ROI order.

## 1. Measured findings

Method: Metal-backed headless Chromium (`--use-angle=metal`), `deviceScaleFactor: 2`,
frame cadence sampled by an independent `requestAnimationFrame` chain (vsync-to-vsync
gaps stretch to the GPU frame time when WebGL work queues). OLD = pre-integration build
(commit `14421404`, `ImplicitCadViewer`); NEW = the integrated shared path. Same models
dir, same machine, back-to-back runs.

`planetary-gear.implicit.js` (heavy SDF), 2560×1330 css @ DPR 2 (≈13.6 M pixels):

| Scenario | OLD | NEW | Verdict |
|---|---|---|---|
| Idle (app-issued rAFs / 5 s) | 0 | 0 | clean — no busy loop on either |
| Orbit drag (4 s) | 22.2 ms · 45 fps | 18.3 ms · 55 fps | parity (new slightly better) |
| Discrete wheel (5.5 Hz) | 19.5 ms · 51 fps · p95 123 | 55 ms · 18 fps · p95 174 | **regression ~3×** |
| Trackpad pinch (ctrl+wheel @ 60 Hz) | 35.9 ms · 28 fps · p95 84 | 62.4 ms · 16 fps · **p95 250** | **regression; quarter-second stalls** |

`mandelbulb-distance-estimate` (cheap SDF, tight bounds): wheel 10.7 → 15.7 ms — same
shape, smaller because each redundant frame is cheaper.

At 1440×900 @ DPR 2 the numbers shrink (~95 fps orbit both builds) — the pain scales
with pixel count, which is why my original integration verification (DPR 1) missed it.

### 1a. The regression: redundant full-cost frames while `interactionState.active`

`useViewerRuntime.js` `renderFrame` re-queues the next frame while any of:

```
cameraTransitionActive || keyboardOrbitMoved || needsMoreFrames ||
interactionState.active || previewOrbitActive        (~L440–447)
```

`interactionState.active` is true from `beginInteraction()` (every wheel event, every
pointer-down) until the idle timer fires **140 ms after the last event**. During a
gesture the shared loop therefore renders **every vsync**, even when the camera did not
move between wheel events — and each of those frames is a full raymarch (10–40 ms at
this size). During a 60 Hz pinch the queue saturates and stalls reach 250 ms.

The deleted `ImplicitCadViewer` only re-queued while something actually moved:
`transitionActive || keyboardOrbitMoved || controlsActive || controls.autoRotate` —
camera changes still rendered via the controls `change` event, so nothing was lost.

For meshes this continuous window is invisible (~1–3 ms frames at interaction pixel
ratio); it only became a problem when a 25 ms/frame render type moved into the shared
loop. This is precisely the kind of thing the integration plan's gates should have
caught — the benchmark harness below is the missing gate, now written down.

### 1b. The inherent cost: the shader is fill-bound and fullscreen retina is 4×

Even the OLD build managed only 45 fps orbit / 28 fps pinch at fullscreen retina on
planetary-gear. Costs that scale per-pixel:

- Idle renders at pixel ratio **2.0** (min of shared `IDLE_PIXEL_RATIO_CAP = 2` and
  implicit `resolutionScale` default 2 — identical before/after), with full quality:
  up to 192 steps, soft-shadow march, 5-tap AO, multi-eval normals per hit pixel.
- Interaction drops only the pixel ratio (1.25). The reduced-quality uniform tier
  (`IMPLICIT_INTERACTION_STEP_BUDGET = 96`, `IMPLICIT_INTERACTION_DETAIL = 0.75`,
  shadows/AO off — `graphicsSettings.js`) engages **only** for param drags/animation
  (`dynamicRenderActive`) and preview orbit — never for plain camera interaction. True
  in the old viewer too.
- Every pixel runs the fragment shader, including background: rays that miss still pay
  the bounds test plus, within the floor fade radius, a **soft-shadow march for the
  floor matte** (`implicit_floor_shadowed_background`, implicitjs `render.js` ~L1450).
- The 1.25 ↔ 2.0 pixel-ratio flip on each interaction/idle boundary reallocates the
  drawing buffer and pays one ~4×-cost full-quality frame; with the 140 ms idle delay
  this fires **between discrete wheel ticks** (both builds' wheel p95 ≥ 120 ms show it).

## 2. Plan of attack, in ROI order

### P1 — fix the regression: demand-driven re-queue for the implicit pass (small)

In `useImplicitRaymarch`, set a runtime flag (e.g. `runtime.renderOnDemandOnly = true`)
while the pass is mounted; in `renderFrame` (~L440), drop the `interactionState.active`
term from the re-queue condition when that flag is set. Camera movement still renders —
every OrbitControls `change` calls `requestRender`, and damping/transition/keyboard/
preview keep their own terms. Mesh path untouched (flag never set).

Gate: pinch p95 ≤ OLD's 84 ms; wheel fps ≥ OLD's 51. Orbit must not drop below the
current 55 fps (it should not move — drags produce a change event per frame anyway).

### P2 — interaction-quality uniforms during camera moves (~2× during gestures)

Extend the existing interaction tier (step budget 96, detail 0.75, shadows/AO off) to
plain camera interaction, not just param drags. The visual pop during motion is already
accepted behaviour for param drags; motion hides it. Implementation: the shared runtime
already tracks `interactionState.interactionQuality` (added for the pixel-ratio hook);
read it in the quad's `onBeforeRender` and swap uniform tiers when it flips (cheap:
compare a tier flag, call `updateImplicitCadGraphicsUniforms` only on change). The idle
restore then repaints full quality via the existing idle-quality frame.

Gate: pinch/orbit fps on planetary-gear improves ≥ 1.5× over post-P1; idle screenshot
byte-comparable to pre-change (full quality must fully restore).

### P3 — idle-restore hysteresis (kills the wheel-cadence stutter both builds show)

140 ms after the last wheel tick is too eager for a renderer whose idle frame costs 4×.
For the implicit pass only, lengthen the effective idle-restore delay (~400 ms) and
restore in two stages: full-quality uniforms first, pixel-ratio 2.0 one frame later —
so the expensive frame and the buffer reallocation do not land on the same vsync.
Implementation: small extension where `scheduleIdleQuality` consults the runtime
(`runtime.idleQualityDelayMs` override, set by the hook), keeping mesh behaviour as-is.

Gate: discrete-wheel p95 < 40 ms on planetary-gear at fullscreen retina (was 123 OLD /
174 NEW).

### P4 — fixed pixel budget during interaction (fullscreen independence)

Interaction cost still scales with window size (1.25 ratio of a 5K window is a lot of
rays). Replace the interaction pixel-ratio constant with a **fixed budget**: choose the
largest ratio ≤ 1.25 such that drawing-buffer pixels ≤ ~2.5 M (tune on the benchmark).
One-line change in the hook's `resolveExtraPixelRatioCap` (it already receives the
interaction flag; compute from `renderer.domElement.clientWidth/Height`). This makes
gesture cost constant across window sizes — the difference between "usable" and
"extremely slow" on a fullscreen 5K display.

Gate: pinch fps at 2560×1330 within 20% of pinch fps at 1440×900, same model.

### P5 — scissored raymarch + background split (the big structural win, idle included)

Today every pixel runs the SDF shader. Split the pass:

1. **Background** leaves the shader: solid/gradient becomes the shared scene clear
   color / `scene.background` (also un-suppresses the shared stage direction the
   integration doc pointed at). The shader's miss path returns transparent instead of
   painting background.
2. **Scissor the quad pass** to the screen-space projection of
   `runtime.modelBounds ∪ floor-shadow disc` (`uFloorCenter`/`uFloorFadeRadius` are
   already known), padded ~10%. Project 8 bounds corners + disc extremes with the
   shared camera each frame in `onBeforeRender`; set `renderer.setScissor/Test`.

Typical framings put the model+shadow in 25–45% of the viewport → 2–4× on **everything,
idle frames included**, multiplicative with P1–P4. This touches implicitjs's shader
(the miss path and the alpha handling) — the previous batch's "do not touch implicitjs
internals" fence was scoped to that batch, but the snapshot/export paths share this
shader, so the change must keep `renderImplicitCadToDataUrl` and the headless snapshot
rendering background-correct (they can keep painting background in-shader via a uniform
toggle, or clear-color the offscreen renderer the same way).

Gate: full-corpus 47-model sweep non-blank; screenshot parity on planetary-gear,
catenoid-ring-bridge, gosper-curve-tube in light and dark themes (background gradients
must survive); orbit fps at fullscreen retina ≥ 2× post-P2 numbers on planetary-gear.

### P6 — shader-side tuning (follow-up, measure-first)

Only after P1–P5, with the harness: per-feature cost split (shadows, AO, normal taps,
step scale) by toggling the existing Graphics switches under the benchmark; consider a
cheaper AO (2-tap) tier, `uMaxStep` auto-tuning from bounds, and per-model
`maxSteps` audits (192 default; several models likely converge far earlier). No code
until the numbers say where the time goes.

## 3. Benchmark harness (the gate for every step)

Scripted Metal-backed Chromium, DPR 2, viewports 1440×900 and 2560×1330; scenarios:
5 s idle rAF count (must stay 0), 4 s orbit drag, discrete wheel at 5.5 Hz, ctrl+wheel
pinch at 60 Hz; models planetary-gear (heavy), mandelbulb-distance-estimate (cheap),
rounded-orb (baseline). Report mean/p50/p95 vsync gaps. Compare against the OLD build
by checking out `14421404` in a scratch worktree, `npm install` in `viewer/`,
`packages/cadjs`, `packages/implicitjs`, `npm --prefix viewer run build`, and serving
with `VIEWER_CAD_PYTHON=<main-checkout>/.venv/bin/python npm --prefix <worktree>/viewer
run start -- --port <free> --host 127.0.0.1` from the models dir. Every P-step lands
with its before/after row for this matrix; the P1 row must show wheel/pinch back at or
better than OLD before anything else merges.

## 4. Explicitly not the problem (measured, do not chase)

- **No idle busy loop** — 0 app-issued rAFs over 5 s on both builds. Idle burns nothing.
- **Orbit-drag parity** — the shared OrbitControls/damping path is not slower; it is
  slightly faster than the old viewer at fullscreen retina.
- **Pixel-ratio configuration parity** — idle 2.0 / interaction 1.25 on both builds;
  the integration did not change resolution policy.
- **React re-render churn per camera frame** — present on both builds (perspective
  emit → workspace setState); not a differentiator in the A/B. Revisit only if
  profiling after P1–P4 shows main-thread bound frames.
