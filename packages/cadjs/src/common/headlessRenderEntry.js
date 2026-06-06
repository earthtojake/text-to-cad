import gifencDefault, {
  GIFEncoder as exportedGifEncoder,
  applyPalette as exportedApplyPalette,
  quantize as exportedQuantize
} from "gifenc";
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
  stepParameterFrameRuntime
} from "./source.js";

const GIFEncoder = exportedGifEncoder || gifencDefault?.GIFEncoder || gifencDefault;
const quantize = exportedQuantize || gifencDefault?.quantize;
const applyPalette = exportedApplyPalette || gifencDefault?.applyPalette;

function orbitFrameOutputs(job) {
  const orbit = job.orbit && typeof job.orbit === "object" ? job.orbit : {};
  const output = Array.isArray(job.outputs) && job.outputs.length ? job.outputs[0] : {};
  const width = Math.max(1, Math.floor(Number(output.width || job.width || orbit.width || 720)));
  const height = Math.max(1, Math.floor(Number(output.height || job.height || orbit.height || 480)));
  const fps = Math.max(1, Math.min(Number(orbit.fps || 18), 60));
  const durationSeconds = Math.max(0.1, Math.min(Number(orbit.durationSeconds || 4), 60));
  const frameCount = Math.max(2, Math.min(Math.round(fps * durationSeconds), 720));
  const startAzimuth = Number.isFinite(Number(orbit.startAzimuth)) ? Number(orbit.startAzimuth) : -45;
  const elevation = Number.isFinite(Number(orbit.elevation)) ? Number(orbit.elevation) : 30;
  const turns = Number.isFinite(Number(orbit.turns)) ? Number(orbit.turns) : 1;
  return {
    path: String(output.path || job.output || ""),
    width,
    height,
    fps,
    durationSeconds,
    frameCount,
    outputs: Array.from({ length: frameCount }, (_, index) => ({
      path: "",
      width,
      height,
      camera: `${startAzimuth + ((360 * turns * index) / frameCount)}:${elevation}`
    }))
  };
}

async function dataUrlToImageData(dataUrl, width, height) {
  const image = new Image();
  image.decoding = "async";
  const loaded = new Promise((resolve, reject) => {
    image.onload = resolve;
    image.onerror = () => reject(new Error("Failed to load rendered orbit frame"));
  });
  image.src = dataUrl;
  await loaded;
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const context = canvas.getContext("2d", { willReadFrequently: true });
  context.drawImage(image, 0, 0, width, height);
  return context.getImageData(0, 0, width, height);
}

function shouldEncodeTransparentGif(job = {}) {
  const backgroundType = String(
    job.appearance?.background?.type || ""
  ).toLowerCase();
  return Boolean(job.render?.transparent) || backgroundType === "transparent";
}

function encodeGifFrameImageData(imageData, { transparent = false } = {}) {
  if (!transparent) {
    const palette = quantize(imageData.data, 256);
    return {
      indexed: applyPalette(imageData.data, palette),
      palette,
      transparent: false,
      transparentIndex: 0
    };
  }

  const palette = quantize(imageData.data, 256, {
    format: "rgba4444",
    oneBitAlpha: true
  });
  const transparentIndex = palette.findIndex((color) => Number(color?.[3]) <= 127);
  return {
    indexed: applyPalette(imageData.data, palette, "rgba4444"),
    palette,
    transparent: transparentIndex >= 0,
    transparentIndex: Math.max(transparentIndex, 0)
  };
}

async function capturePreparedSource(source, job) {
  const context = renderJobContext(source.meshData, job);
  const model = buildModel(THREE, source, modelOptionsForRenderJob(context, job));
  if (context.mode === "list" || context.mode === "section") {
    try {
      return await captureModel({ model, context }, { job });
    } finally {
      model.dispose();
    }
  }
  const viewport = renderModel(THREE, model, { job, context });
  try {
    return await captureModel(viewport, { job });
  } finally {
    viewport.dispose();
  }
}

async function renderOrbit(source, job) {
  const orbit = orbitFrameOutputs(job);
  const frameResult = await capturePreparedSource(source, {
    ...job,
    mode: "view",
    outputs: orbit.outputs,
    render: {
      ...(job.render || {}),
      lockFraming: true
    }
  });
  const encoder = GIFEncoder();
  const transparent = shouldEncodeTransparentGif(job);
  for (let index = 0; index < frameResult.outputs.length; index += 1) {
    const imageData = await dataUrlToImageData(frameResult.outputs[index].dataUrl, orbit.width, orbit.height);
    const frame = encodeGifFrameImageData(imageData, { transparent });
    encoder.writeFrame(frame.indexed, orbit.width, orbit.height, {
      palette: frame.palette,
      transparent: frame.transparent,
      transparentIndex: frame.transparentIndex,
      delay: 1000 / orbit.fps,
      repeat: 0,
      dispose: frame.transparent ? 2 : -1
    });
  }
  encoder.finish();
  const bytes = encoder.bytesView();
  let binary = "";
  for (let index = 0; index < bytes.length; index += 1) {
    binary += String.fromCharCode(bytes[index]);
  }
  return {
    ok: true,
    mode: "orbit",
    outputs: [{
      path: orbit.path,
      width: orbit.width,
      height: orbit.height,
      frameCount: orbit.frameCount,
      mimeType: "image/gif",
      dataUrl: `data:image/gif;base64,${btoa(binary)}`
    }],
    timings: frameResult.timings,
    warnings: frameResult.warnings || []
  };
}

async function renderParamAnimation(source, job, stepParameterSource) {
  const params = stepParameterSource.renderParameters;
  const output = Array.isArray(job.outputs) && job.outputs.length ? job.outputs[0] : {};
  const width = Math.max(1, Math.floor(Number(output.width || job.width || 720)));
  const height = Math.max(1, Math.floor(Number(output.height || job.height || 480)));
  const frameOutputs = Array.from({ length: params.frameCount }, (_, index) => ({
    ...output,
    path: "",
    width,
    height,
    stepParameters: stepParameterFrameRuntime(stepParameterSource, index)
  }));
  const frameResult = await capturePreparedSource(source, {
    ...job,
    outputs: frameOutputs,
    render: {
      ...(job.render || {}),
      lockFraming: true
    }
  });
  const encoder = GIFEncoder();
  const transparent = shouldEncodeTransparentGif(job);
  for (let index = 0; index < frameResult.outputs.length; index += 1) {
    const imageData = await dataUrlToImageData(frameResult.outputs[index].dataUrl, width, height);
    const frame = encodeGifFrameImageData(imageData, { transparent });
    encoder.writeFrame(frame.indexed, width, height, {
      palette: frame.palette,
      transparent: frame.transparent,
      transparentIndex: frame.transparentIndex,
      delay: 1000 / params.fps,
      repeat: params.loop === false ? -1 : 0,
      dispose: frame.transparent ? 2 : -1
    });
  }
  encoder.finish();
  const bytes = encoder.bytesView();
  let binary = "";
  for (let index = 0; index < bytes.length; index += 1) {
    binary += String.fromCharCode(bytes[index]);
  }
  return {
    ok: true,
    mode: String(job.mode || "view").toLowerCase(),
    outputs: [{
      path: String(output.path || job.output || ""),
      width,
      height,
      frameCount: params.frameCount,
      fps: params.fps,
      durationSeconds: params.durationSeconds,
      loop: params.loop !== false,
      mimeType: "image/gif",
      dataUrl: `data:image/gif;base64,${btoa(binary)}`
    }],
    timings: frameResult.timings,
    warnings: frameResult.warnings || []
  };
}

export async function runHeadlessRenderJob(job) {
  const source = await loadSource(job);
  const stepParameterSource = source.stepParameterSource;
  const explicitParams = hasStepParameterRenderValues(job.stepParameters);
  const renderJob = {
    ...job,
    selectorRuntime: source.selectorRuntime,
    displayEdgeRuntime: source.displayEdgeRuntime
  };
  if (stepParameterSource && explicitParams && String(job.mode || "view").toLowerCase() !== "view") {
    throw new Error("stepParameters support only view mode; set display.mode for display-style changes");
  }
  const renderJobWithStepParameters = stepParameterSource
    ? {
        ...renderJob,
        stepParameters: stepParameterFrameRuntime(stepParameterSource, 0)
      }
    : renderJob;
  if (stepParameterSource?.renderParameters?.animated) {
    return renderParamAnimation(source, renderJob, stepParameterSource);
  }
  if (String(job.mode || "view").toLowerCase() === "orbit") {
    return renderOrbit(source, renderJobWithStepParameters);
  }
  return capturePreparedSource(source, renderJobWithStepParameters);
}

if (typeof window !== "undefined") {
  window.__snapshotRender = runHeadlessRenderJob;
}
