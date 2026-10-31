import * as THREE from "three";
import {
  headlessResources,
  headlessSceneDress,
  headlessSceneFamily,
  headlessSceneModel
} from "./headlessScene.js";
import {
  captureModel,
  renderJobContext,
  renderModel
} from "./renderMeshScene.js";
import { validateSnapshotRenderJob } from "./snapshotJobValidation.js";
import { scenePartCount } from "./viewSettings.js";
import { runHeadlessDrawingJob } from "./headlessDrawingRender.js";

// Each call owns its measurements. Capture reports camera fitting, draw
// submission and image encoding separately; viewport construction is not a draw.
//
// ONE capture for every file family: the model is the scene of its family's shared builder,
// and the stage, the camera and the encoding are the same for all of them.
async function captureWithModel(model, context, job, stageTimings) {
  if (context.mode === "list") {
    try {
      return await captureModel({ model, context }, { job });
    } finally {
      model.dispose();
    }
  }
  const viewportStarted = performance.now();
  const viewport = renderModel(THREE, model, { job, context });
  stageTimings.prepareViewportMs = Math.round(performance.now() - viewportStarted);
  try {
    const captureStarted = performance.now();
    const captured = await captureModel(viewport, { job, stageTimings });
    stageTimings.captureMs = Math.round(performance.now() - captureStarted);
    if (captured && typeof captured === "object" && !Array.isArray(captured)) {
      captured.stageTimings = stageTimings;
    }
    return captured;
  } finally {
    viewport.dispose();
  }
}

// A GLB, an STL, a 3MF, a robot or an engine document: the file is read by its family's loader
// and drawn by its family's builder, the two the viewer's renderer for it uses
// (`headlessScene.js`), then dressed in the look the viewer's viewport would put on it for these
// settings.
async function captureFamilyScene(family, job) {
  validateSnapshotRenderJob(job);
  const stageTimings = {};
  const loadStarted = performance.now();
  const loaded = await family.load(job, { resources: headlessResources() });
  stageTimings.loadSourceMs = Math.round(performance.now() - loadStarted);
  const buildStarted = performance.now();
  let scene;
  try { scene = family.build(THREE, loaded, job); }
  catch (error) { family.release(loaded); throw error; }
  let context;
  let model;
  try {
    context = renderJobContext({ bounds: scene.bounds, partCount: scenePartCount(scene), explodeParts: scene.explodeParts || 0 }, job);
    model = headlessSceneModel(THREE, scene, headlessSceneDress(context.sceneSettings));
  } catch (error) { scene.dispose(); throw error; }
  stageTimings.buildModelMs = Math.round(performance.now() - buildStarted);
  return captureWithModel(model, context, job, stageTimings);
}

/** A 2D drawing cadgen resolved (a `.dxf`), not a scene. */
function jobIsDrawing(job) {
  return Boolean(job?.resolved?.drawingUrl);
}

export async function runHeadlessRenderJob(job) {
  // A drawing never enters the mesh pipeline: there is no source to fetch, no
  // model to build and no viewport to fit. It is painted on a 2D canvas with
  // the code the viewer's DXF pane paints with (./headlessDrawingRender.js).
  if (jobIsDrawing(job)) {
    return runHeadlessDrawingJob(job);
  }
  const family = headlessSceneFamily(job);
  if (family) {
    return captureFamilyScene(family, job);
  }
  // A STEP is drawn as the engine document it opens as (`resolved.kind` "xbf").
  throw new Error(`a snapshot job draws a DXF or a file family (GLB, STL, 3MF, URDF, SRDF, SDF, an engine document), `
    + `not ${JSON.stringify(String(job?.resolved?.kind || job?.kind || ""))}: a STEP is drawn as the engine document it opens as`);
}

if (typeof window !== "undefined") {
  window.__snapshotRender = runHeadlessRenderJob;
}
