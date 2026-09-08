import * as THREE from "three";
import {
  buildModel
} from "./cadScene.js";
import {
  captureModel,
  modelOptionsForRenderJob,
  renderJobContext,
  renderModel
} from "./renderMeshScene.js";
import {
  hasStepParameterRenderValues
} from "./stepParameters.js";
import {
  loadSource,
  sourceIsStep,
  stepParameterRuntime
} from "./source.js";
import { animationClipDuration, resolveAnimationFrame } from "./animationClock.js";
import { loadRenderModule } from "./renderModule.js";
import {
  createHttpTessellationCacheProvider,
  setTessellationCacheProvider
} from "../lib/surf/tessellationCache.js";

// Coarse per-stage wall times for the last view-mode job, attached to its
// result so the driver can print where a slow snapshot actually went (load =
// fetch + tessellate/cache-hit + meshData; build = scene composition; render
// = GL draw; capture = readback + encode).
const headlessStageTimings = {};

async function capturePreparedSource(source, job) {
  const buildStarted = performance.now();
  const context = renderJobContext(source.meshData, job);
  const model = buildModel(THREE, source, modelOptionsForRenderJob(context, job));
  headlessStageTimings.buildModelMs = Math.round(performance.now() - buildStarted);
  if (context.mode === "list" || context.mode === "section") {
    try {
      return await captureModel({ model, context }, { job });
    } finally {
      model.dispose();
    }
  }
  const renderStarted = performance.now();
  const viewport = renderModel(THREE, model, { job, context });
  headlessStageTimings.renderMs = Math.round(performance.now() - renderStarted);
  try {
    const captureStarted = performance.now();
    const captured = await captureModel(viewport, { job });
    headlessStageTimings.captureMs = Math.round(performance.now() - captureStarted);
    if (captured && typeof captured === "object" && !Array.isArray(captured)) {
      captured.stageTimings = { ...headlessStageTimings };
    }
    return captured;
  } finally {
    viewport.dispose();
  }
}

// `job.animation` is the JOB PACKET's frame request ({clip, time}); the
// `stepAnimation` it becomes is the SETTINGS key renderMeshScene routes to the
// shared effects pass — the same `{clip, elapsedSec}` the viewer's Animation
// tab hands its own pass. The choreography loads through the one render-module
// loader the viewer uses (the `.step.js` beside the document, resolved by the
// CLI as `resolved.renderModuleUrl`): the sidecar is never consulted here, so
// the two systems stay independent end to end and meet only in the effect
// records.
async function loadStepAnimation(job, source) {
  const request = job.animation;
  if (request === undefined || request === null) {
    return null;
  }
  if (!sourceIsStep(source)) {
    throw new Error("animation is supported only for STEP/STP sources");
  }
  if (String(job.mode || "view").toLowerCase() !== "view") {
    throw new Error("an animation frame supports only view mode");
  }
  const renderModuleUrl = String(job.resolved?.renderModuleUrl || "").trim();
  if (!renderModuleUrl) {
    throw new Error("animation requires resolved.renderModuleUrl (the .step.js beside the document)");
  }
  const renderModule = await loadRenderModule(renderModuleUrl);
  if (!renderModule) {
    throw new Error("the document has no render module beside it, so there is no clip frame to render");
  }
  return resolveAnimationFrame(renderModule.clips, request);
}

// Everything a render needs before a single pixel is drawn: the fetched and
// tessellated source, the compiled clip frame, and the job carrying the runtime
// objects the shared render path reads. A still pays for this once and throws it
// away; a video pays for it once and keeps it (see prepareHeadlessRenderSequence).
async function prepareRenderJob(job) {
  const loadStarted = performance.now();
  const source = await loadSource(job);
  const stepAnimation = await loadStepAnimation(job, source);
  headlessStageTimings.loadSourceMs = Math.round(performance.now() - loadStarted);
  const stepParameterSource = source.stepParameterSource;
  // `job.kinematics` is the JOB PACKET's pose input (a preset name or {dof: value}); the
  // `stepParameters` set below is the shared buildModel/renderMeshScene SETTINGS key,
  // carrying the compiled runtime object. They used to be the same key, so a packet field
  // and a runtime object took turns living on it.
  const explicitParams = hasStepParameterRenderValues(job.kinematics);
  const renderJob = {
    ...job,
    selectorRuntime: source.selectorRuntime,
    displayEdgeRuntime: source.displayEdgeRuntime,
    stepAnimation
  };
  if (stepParameterSource && explicitParams && String(job.mode || "view").toLowerCase() !== "view") {
    throw new Error("kinematics values support only view mode; set display.mode for display-style changes");
  }
  return {
    source,
    stepAnimation,
    renderJob: stepParameterSource
      ? {
          ...renderJob,
          stepParameters: stepParameterRuntime(stepParameterSource)
        }
      : renderJob
  };
}

export async function runHeadlessRenderJob(job) {
  const { source, renderJob } = await prepareRenderJob(job);
  return capturePreparedSource(source, renderJob);
}

// --- video: prepare once, then move only the clock -------------------------
//
// A still throws its source and model away when it is done. Rendering a clip
// that way would re-fetch and re-tessellate the whole document for every frame
// — minutes of load per second of video — so a sequence prepares ONCE and then
// answers per-frame capture requests against the model already on the GPU.
//
// The per-frame update is a merged `callbacks.animation` and nothing else:
// cadScene's `settingsSignature` reads materials, edge style and display mode,
// none of which move, so `update()` re-runs the effects pass over the records
// it already built instead of rebuilding them. That seam is the whole reason a
// video is affordable, and `sequencePoseState` is the one place it is used.
//
// The host drives it a frame at a time (`__snapshotRenderSequenceFrame(index)`)
// rather than collecting an array: a 30 s 60 fps render is 1800 PNGs, and the
// driver pipe cannot carry that in one protocol message.

export const VIDEO_FPS_MIN = 1;
export const VIDEO_FPS_MAX = 120;
// The schedule's ceiling, mirroring cadgen's MAX_VIDEO_FRAMES: an fps bound
// alone bounds nothing, because the frame count is fps TIMES seconds and every
// frame is a full-size PNG written to disk before ffmpeg sees one of them.
// 7200 frames is four minutes of review at 30 fps and tens of gigabytes of
// frames at the default size; past that the request is a typo, not a video.
export const VIDEO_MAX_FRAMES = 7200;

function formatSeconds(value) {
  return `${Number(value.toFixed(3))}s`;
}

/** The frame schedule a `video` request implies over one clip.
 *
 * `seconds` defaults to the span the clip still HAS from `start`, and the frame
 * count is `seconds * fps` rounded, so the last frame sits one interval BEFORE
 * `start + seconds`. That is what makes a looping clip loop cleanly: the frame
 * at `start + seconds` is the frame at `start` again, and rendering both
 * stutters on every repeat.
 *
 * Every time is measured against the clip, because `evaluateAnimationClip`
 * ANSWERS a time past the end rather than refusing it: a non-looping clip
 * clamps, so the tail of the video is one still image repeated, and a looping
 * one wraps, so it renders a different span than the one asked for. Both are
 * exit-0 wrong answers that nothing downstream can tell from a right one. */
export function resolveVideoPlan(request, clip) {
  const raw = request && typeof request === "object" ? request : {};
  const fps = Number(raw.fps ?? 30);
  if (!Number.isInteger(fps) || fps < VIDEO_FPS_MIN || fps > VIDEO_FPS_MAX) {
    throw new Error(`video fps must be a whole number ${VIDEO_FPS_MIN}..${VIDEO_FPS_MAX}, got ${JSON.stringify(raw.fps)}`);
  }
  const start = raw.start === undefined || raw.start === null ? 0 : Number(raw.start);
  if (!Number.isFinite(start) || start < 0) {
    throw new Error(`video start must be seconds >= 0, got ${JSON.stringify(raw.start)}`);
  }
  const duration = animationClipDuration(clip);
  if (start >= duration) {
    throw new Error(
      `video start ${formatSeconds(start)} is at or past the end of a ${formatSeconds(duration)} clip: `
      + "every frame would be the same one"
    );
  }
  const looping = clip?.loop !== false;
  const seconds = raw.seconds === undefined || raw.seconds === null
    // A looping clip's default is one whole cycle from wherever it starts; a
    // clip that stops at its end has only the part of it that is left.
    ? (looping ? duration : duration - start)
    : Number(raw.seconds);
  if (!Number.isFinite(seconds) || seconds <= 0) {
    throw new Error(`video seconds must be a positive number, got ${JSON.stringify(raw.seconds)}`);
  }
  const frameCount = Math.max(1, Math.round(seconds * fps));
  if (frameCount > VIDEO_MAX_FRAMES) {
    throw new Error(
      `video ${formatSeconds(seconds)} at ${fps} fps schedules ${frameCount} frames, `
      + `past the ${VIDEO_MAX_FRAMES}-frame ceiling`
    );
  }
  const warnings = [];
  // An explicit span that overruns a clip which does not loop is the caller's
  // to make, but the frames it buys past the end are all the final pose, and
  // nothing in the finished file says so.
  if (!looping && (start + seconds) - duration > 1e-9) {
    warnings.push(
      `video covers ${formatSeconds(start)}..${formatSeconds(start + seconds)} of a `
      + `${formatSeconds(duration)} clip that does not loop: every frame past its end is the same final pose`
    );
  }
  return { fps, seconds, start, frameCount, warnings };
}

export function videoFrameElapsedSec(plan, index) {
  return plan.start + (index / plan.fps);
}

/** The `update` patch that poses a prepared model at one moment of its clip.
 *
 * The merged `callbacks.animation` is the only thing that changes, so applying
 * it re-runs the effects pass over the existing records; nothing rebuilds. */
export function sequencePoseState(stepAnimation, elapsedSec) {
  return {
    callbacks: {
      animation: { ...stepAnimation, elapsedSec }
    }
  };
}

/** Re-pose a prepared model at one moment of its clip. */
export function poseSequenceFrame(model, stepAnimation, elapsedSec) {
  return model.update(sequencePoseState(stepAnimation, elapsedSec));
}

/** Bounds containing every frame of the plan.
 *
 * `captureModel` fits the camera to the bounds the model has AT CAPTURE TIME,
 * which is right for a still and wrong for a sequence: a moving model would
 * make the camera breathe frame to frame. Fitting to frame 0 alone is worse
 * still — the clip travels out of shot wherever it moves furthest. So the
 * camera is fitted once, to the union, and this pre-pass pays one effects pass
 * per frame (no GL, no readback) to know what that union is. */
// How many poses the union is measured over. It SAMPLES rather than walking
// every frame: a clip's extent moves smoothly, so a couple of hundred poses
// bound it as well as thousands do — and a frame is not free (the tendon hand
// re-solves 48 swept centerlines per pose, at which point enumerating 1,800
// frames costs more than the render). The first and last frame are always
// included, and the result is padded by a hair so a pose between two samples
// cannot poke outside the frame the camera is then locked to.
const SEQUENCE_BOUNDS_SAMPLES = 192;
const SEQUENCE_BOUNDS_MARGIN = 0.01;

export function sequenceFrameBounds(model, stepAnimation, plan) {
  const min = [Infinity, Infinity, Infinity];
  const max = [-Infinity, -Infinity, -Infinity];
  const samples = Math.min(plan.frameCount, SEQUENCE_BOUNDS_SAMPLES);
  const last = plan.frameCount - 1;
  for (let sample = 0; sample < samples; sample += 1) {
    const index = samples === 1 ? 0 : Math.round((sample * last) / (samples - 1));
    const bounds = poseSequenceFrame(model, stepAnimation, videoFrameElapsedSec(plan, index)).bounds;
    for (let axis = 0; axis < 3; axis += 1) {
      min[axis] = Math.min(min[axis], Number(bounds?.min?.[axis] ?? 0));
      max[axis] = Math.max(max[axis], Number(bounds?.max?.[axis] ?? 0));
    }
  }
  const margin = SEQUENCE_BOUNDS_MARGIN * Math.max(
    ...[0, 1, 2].map((axis) => (Number.isFinite(max[axis] - min[axis]) ? max[axis] - min[axis] : 0)),
    1
  );
  return {
    min: min.map((value) => value - margin),
    max: max.map((value) => value + margin)
  };
}

let activeRenderSequence = null;

export async function prepareHeadlessRenderSequence(job) {
  disposeHeadlessRenderSequence();
  const { source, stepAnimation, renderJob } = await prepareRenderJob(job);
  if (!stepAnimation) {
    throw new Error("a video renders a clip: the job needs an animation request beside its video request");
  }
  const context = renderJobContext(source.meshData, renderJob);
  const model = buildModel(THREE, source, modelOptionsForRenderJob(context, renderJob));
  let viewport = null;
  try {
    const plan = resolveVideoPlan(renderJob.video, stepAnimation.clip);
    // The union is measured BEFORE the scene is built, because the stage floor
    // and grid are sized to the bounds `renderModel` is handed while the camera
    // is locked to this union: built from the t = 0 pose they end up inside the
    // frame, and a travelling part walks off the shadow catcher mid-clip.
    const frameBounds = sequenceFrameBounds(model, stepAnimation, plan);
    context.warnings.push(...plan.warnings);
    viewport = renderModel(THREE, model, { job: renderJob, context, floorBounds: frameBounds });
    activeRenderSequence = { job: renderJob, model, viewport, stepAnimation, plan, frameBounds };
  } catch (error) {
    // Whichever of the two exists owns the GPU buffers: a viewport disposes the
    // model it was built over, and before that the model is on its own.
    (viewport || model).dispose();
    throw error;
  }
  return {
    ok: true,
    frames: activeRenderSequence.plan.frameCount,
    fps: activeRenderSequence.plan.fps,
    seconds: activeRenderSequence.plan.seconds,
    start: activeRenderSequence.plan.start
  };
}

export async function captureHeadlessRenderSequenceFrame(index) {
  const session = activeRenderSequence;
  if (!session) {
    throw new Error("no prepared render sequence: call __snapshotRenderSequence(job) first");
  }
  if (!Number.isInteger(index) || index < 0 || index >= session.plan.frameCount) {
    throw new Error(`render sequence frame ${JSON.stringify(index)} is outside 0..${session.plan.frameCount - 1}`);
  }
  const captured = await captureModel(session.viewport, {
    job: session.job,
    frameBounds: session.frameBounds,
    // The pose rides INTO captureModel's own `update` rather than being applied
    // just before it: captureModel updates the model itself, so posing
    // separately ran the clip evaluator and the whole effects pass twice on
    // every frame — the largest per-frame cost a video pays, doubled.
    modelState: sequencePoseState(session.stepAnimation, videoFrameElapsedSec(session.plan, index))
  });
  const output = captured?.outputs?.[0];
  if (!output?.dataUrl) {
    throw new Error(`render sequence frame ${index} produced no image`);
  }
  return {
    ok: true,
    index,
    dataUrl: output.dataUrl,
    width: output.width,
    height: output.height,
    // The camera the page RESOLVED, as a still reports it. The host builds the
    // video's output record itself and would otherwise echo the request, which
    // for an explicit-position camera is an object, not a name.
    camera: output.camera
  };
}

export function disposeHeadlessRenderSequence() {
  const session = activeRenderSequence;
  activeRenderSequence = null;
  if (!session) {
    return { ok: true, warnings: [] };
  }
  // One context serves every frame, so a warning raised on frame 0 is still in
  // the list on frame 1799: report the SET, once, as the sequence is torn down.
  const warnings = Array.from(new Set(session.viewport.context.warnings.map(String)));
  session.viewport.dispose();
  return { ok: true, warnings };
}

if (typeof window !== "undefined") {
  window.__snapshotRender = runHeadlessRenderJob;
  window.__snapshotRenderSequence = prepareHeadlessRenderSequence;
  window.__snapshotRenderSequenceFrame = captureHeadlessRenderSequenceFrame;
  window.__snapshotRenderSequenceDispose = disposeHeadlessRenderSequence;
  // The snapshot host (cadgen's snapshot driver) serves the shared component-
  // tessellation cache (~/.cache/cadgen/meshes) on /__tess_cache/ from its
  // loopback asset server, so repeat snapshots — and any component an export
  // already tessellated — skip tessellation entirely, and a snapshot miss
  // warms the cache for later exports. Both directions are best-effort: a
  // host without the route (404) or a disabled cache degrades to plain
  // in-page tessellation.
  //
  // That server is addressed by its ABSOLUTE origin, injected before this
  // bundle runs. A page-relative /__tess_cache/ URL is intercepted by the
  // host's Playwright route first, and interception hands the whole POST body
  // to the driver as escaped text in one protocol message — a 92 MB write-back
  // exceeded Node's string limit there and killed the renderer. Redirecting
  // the request to loopback could not save it: the body had already crossed
  // the pipe. The host raises when it cannot start the server, so the origin
  // is always here; a build talking to some other host degrades to relative
  // URLs and says so.
  // The shared fetch-backed provider: single-entry GET/POST plus the batched
  // POST /__tess_cache/batch — bounded round trips for a whole assembly's hit set.
  const assetOrigin = String(window.__cadgenSnapshotAssetOrigin || "").replace(/\/+$/, "");
  if (!assetOrigin) {
    console.warn("snapshot asset origin missing: bulk cache transfers fall back to the host's route");
  }
  setTessellationCacheProvider(createHttpTessellationCacheProvider({ origin: assetOrigin }));
}
