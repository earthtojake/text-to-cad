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
import { resolveAnimationFrame } from "./animationClock.js";
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

export async function runHeadlessRenderJob(job) {
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
  const renderJobWithStepParameters = stepParameterSource
    ? {
        ...renderJob,
        stepParameters: stepParameterRuntime(stepParameterSource)
      }
    : renderJob;
  return capturePreparedSource(source, renderJobWithStepParameters);
}

if (typeof window !== "undefined") {
  window.__snapshotRender = runHeadlessRenderJob;
  // The snapshot host (cadgen's snapshot driver) serves the shared component-
  // tessellation cache (~/.cache/cadgen/meshes) on /__tess_cache/ through its
  // Playwright route, so repeat snapshots — and any component an export
  // already tessellated — skip tessellation entirely, and a snapshot miss
  // warms the cache for later exports. Both directions are best-effort: a
  // host without the route (404) or a disabled cache degrades to plain
  // in-page tessellation.
  // The shared fetch-backed provider: single-entry GET/POST plus the batched
  // POST /__tess_cache/batch — one round trip for a whole assembly's hit set.
  setTessellationCacheProvider(createHttpTessellationCacheProvider());
}
