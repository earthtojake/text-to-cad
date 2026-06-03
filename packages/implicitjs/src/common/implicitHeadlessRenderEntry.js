import gifencDefault, {
  GIFEncoder as exportedGifEncoder,
  applyPalette as exportedApplyPalette,
  quantize as exportedQuantize
} from "gifenc";
import * as THREE from "three";
import {
  normalizeParameterValue,
  normalizeParameterValues
} from "./parameters.js";
import { loadImplicitCadModule } from "../lib/implicitCad/loader.js";
import {
  snapshotImplicitCadModel,
  snapshotImplicitCadOutputOptions
} from "../lib/implicitCad/snapshot.js";

const GIFEncoder = exportedGifEncoder || gifencDefault?.GIFEncoder || gifencDefault;
const quantize = exportedQuantize || gifencDefault?.quantize;
const applyPalette = exportedApplyPalette || gifencDefault?.applyPalette;
const implicitModuleCache = new Map();

function isObject(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function clampNumber(value, min, max) {
  const numeric = Number(value);
  return Math.min(Math.max(Number.isFinite(numeric) ? numeric : min, min), max);
}

function implicitParameterValues(rawParameters) {
  if (!isObject(rawParameters)) {
    return {};
  }
  return isObject(rawParameters.values) ? rawParameters.values : rawParameters;
}

function implicitAnimationState(rawParameters, job = {}, output = {}) {
  const raw = isObject(output.implicitAnimationState)
    ? output.implicitAnimationState
    : isObject(job.implicitAnimationState)
      ? job.implicitAnimationState
      : isObject(rawParameters?.animationState)
        ? rawParameters.animationState
        : isObject(rawParameters?.animation)
          ? rawParameters.animation
          : {};
  return raw;
}

function canonicalJsonValue(value) {
  if (Array.isArray(value)) {
    return value.map(canonicalJsonValue);
  }
  if (!isObject(value)) {
    return value;
  }
  return Object.fromEntries(
    Object.keys(value)
      .sort()
      .map((key) => [key, canonicalJsonValue(value[key])])
  );
}

function canonicalJson(value) {
  return JSON.stringify(canonicalJsonValue(value));
}

function findImplicitAnimation(definition, animationId) {
  const animations = Array.isArray(definition?.animations) ? definition.animations : [];
  if (!animations.length) {
    return null;
  }
  const id = String(animationId || "").trim();
  return animations.find((animation) => animation.id === id) || animations[0] || null;
}

function buildAnimatedImplicitParameterValues(definition, animation, currentValues, elapsedSec) {
  if (!definition || typeof animation?.update !== "function") {
    return currentValues;
  }
  const duration = Math.max(Number(animation.duration) || 1, 0.001);
  const clampedElapsedSec = clampNumber(elapsedSec, 0, duration);
  const progress = duration > 0 ? clampNumber(clampedElapsedSec / duration, 0, 1) : 0;
  const normalizedCurrent = normalizeParameterValues(definition, currentValues);
  const nextValues = { ...normalizedCurrent };
  const set = (parameterId, value) => {
    const id = String(parameterId || "").trim();
    const parameter = definition.parameterMap?.[id];
    if (!parameter) {
      return;
    }
    nextValues[id] = normalizeParameterValue(parameter, value);
  };
  animation.update({
    ...normalizedCurrent,
    elapsed: clampedElapsedSec,
    elapsedSec: clampedElapsedSec,
    duration,
    progress,
    cycle: duration > 0 ? clampedElapsedSec / duration : 0,
    t: clampedElapsedSec,
    loop: animation.loop !== false,
    params: normalizedCurrent,
    set
  });
  return nextValues;
}

function applyImplicitAnimation(definition, parameterValues, animationState = {}) {
  const animation = findImplicitAnimation(definition, animationState.activeId);
  if (!animation) {
    return parameterValues;
  }
  return buildAnimatedImplicitParameterValues(
    definition,
    animation,
    parameterValues,
    Number(animationState.elapsedSec ?? animationState.elapsed ?? 0)
  );
}

function implicitRuntimeState(model, job = {}, output = {}) {
  const rawParameters = isObject(output.implicitParameters)
    ? output.implicitParameters
    : isObject(job.implicitParameters)
      ? job.implicitParameters
      : {};
  const animationState = implicitAnimationState(rawParameters, job, output);
  const parameterValues = applyImplicitAnimation(
    model?.definition,
    implicitParameterValues(rawParameters),
    animationState
  );
  return { animationState, parameterValues };
}

function implicitRuntimeModel(model, job = {}, output = {}) {
  const { animationState, parameterValues } = implicitRuntimeState(model, job, output);
  return typeof model?.definition?.buildModel === "function"
    ? model.definition.buildModel(
        parameterValues,
        animationState
      )
    : model;
}

function cachedImplicitRuntimeModel(model, job = {}, output = {}, cache = null) {
  if (!cache || typeof model?.definition?.buildModel !== "function") {
    return implicitRuntimeModel(model, job, output);
  }
  const state = implicitRuntimeState(model, job, output);
  const key = canonicalJson(state);
  if (cache.has(key)) {
    return cache.get(key);
  }
  const runtimeModel = model.definition.buildModel(state.parameterValues, state.animationState);
  cache.set(key, runtimeModel);
  return runtimeModel;
}

async function loadCachedImplicitCadModule(inputUrl) {
  const key = String(inputUrl || "");
  if (!implicitModuleCache.has(key)) {
    implicitModuleCache.set(
      key,
      loadImplicitCadModule(key).catch((error) => {
        implicitModuleCache.delete(key);
        throw error;
      })
    );
  }
  return implicitModuleCache.get(key);
}

function orbitFrameOutputs(job) {
  const orbit = isObject(job.orbit) ? job.orbit : {};
  const output = Array.isArray(job.outputs) && job.outputs.length && isObject(job.outputs[0])
    ? job.outputs[0]
    : {};
  const width = Math.max(1, Math.floor(Number(output.width || job.width || orbit.width || 720)));
  const height = Math.max(1, Math.floor(Number(output.height || job.height || orbit.height || 480)));
  const fps = Math.max(1, Math.min(Number(orbit.fps || 18), 60));
  const durationSeconds = Math.max(0.1, Math.min(Number(orbit.durationSeconds || 4), 60));
  const frameCount = Math.max(2, Math.min(Math.round(fps * durationSeconds), 720));
  const startAzimuth = Number.isFinite(Number(orbit.startAzimuth)) ? Number(orbit.startAzimuth) : -45;
  const elevation = Number.isFinite(Number(orbit.elevation)) ? Number(orbit.elevation) : 28;
  const turns = Number.isFinite(Number(orbit.turns)) ? Number(orbit.turns) : 1;
  return {
    path: String(output.path || job.output || ""),
    width,
    height,
    fps,
    durationSeconds,
    frameCount,
    appearance: output.appearance || job.appearance || "workbench",
    graphics: {
      ...(isObject(job.graphics) ? job.graphics : {}),
      ...(isObject(output.graphics) ? output.graphics : {}),
    },
    render: {
      ...(isObject(job.render) ? job.render : {}),
      ...(isObject(output.render) ? output.render : {}),
    },
    outputs: Array.from({ length: frameCount }, (_, index) => ({
      path: "",
      width,
      height,
      camera: `${startAzimuth + ((360 * turns * index) / frameCount)}:${elevation}`,
    }))
  };
}

function implicitAnimationOptions(job, output = {}) {
  if (isObject(output.implicitAnimation)) {
    return output.implicitAnimation;
  }
  if (isObject(job.implicitAnimation)) {
    return job.implicitAnimation;
  }
  if (String(job.mode || "").trim().toLowerCase() === "animate") {
    return {};
  }
  return null;
}

function implicitAnimationFrameOutputs(model, job) {
  const output = Array.isArray(job.outputs) && job.outputs.length && isObject(job.outputs[0])
    ? job.outputs[0]
    : {};
  const options = implicitAnimationOptions(job, output);
  const animation = findImplicitAnimation(model?.definition, options?.activeId || options?.id || job.implicitAnimationState?.activeId);
  if (!animation) {
    throw new Error("Implicit CAD animation snapshot requires an animation on the model");
  }
  const width = Math.max(1, Math.floor(Number(output.width || job.width || options?.width || 720)));
  const height = Math.max(1, Math.floor(Number(output.height || job.height || options?.height || 480)));
  const fps = Math.max(1, Math.min(Number(options?.fps || 18), 60));
  const durationSeconds = Math.max(0.1, Math.min(Number(options?.durationSeconds || options?.duration || animation.duration || 4), 60));
  const frameCount = Math.max(2, Math.min(Math.round(fps * durationSeconds), 720));
  const baseRawParameters = isObject(output.implicitParameters)
    ? output.implicitParameters
    : isObject(job.implicitParameters)
      ? job.implicitParameters
      : {};
  const baseAnimationState = implicitAnimationState(baseRawParameters, job, output);
  return {
    path: String(output.path || job.output || ""),
    width,
    height,
    fps,
    durationSeconds,
    frameCount,
    loop: options?.loop !== false && animation.loop !== false,
    appearance: output.appearance || job.appearance || "workbench",
    graphics: {
      ...(isObject(job.graphics) ? job.graphics : {}),
      ...(isObject(output.graphics) ? output.graphics : {}),
    },
    render: {
      ...(isObject(job.render) ? job.render : {}),
      ...(isObject(output.render) ? output.render : {}),
    },
    outputs: Array.from({ length: frameCount }, (_, index) => ({
      ...output,
      path: "",
      width,
      height,
      implicitAnimationState: {
        ...baseAnimationState,
        activeId: animation.id,
        playing: true,
        elapsedSec: (durationSeconds * index) / frameCount,
      },
    }))
  };
}

async function dataUrlToImageData(dataUrl, width, height) {
  const image = new Image();
  image.decoding = "async";
  const loaded = new Promise((resolve, reject) => {
    image.onload = resolve;
    image.onerror = () => reject(new Error("Failed to load rendered implicit CAD GIF frame"));
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

function shouldEncodeTransparentGif(job = {}, output = {}) {
  return Boolean(job.render?.transparent || output.render?.transparent);
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

function gifDataUrlFromEncoder(encoder) {
  encoder.finish();
  const bytes = encoder.bytesView();
  let binary = "";
  for (let index = 0; index < bytes.length; index += 1) {
    binary += String.fromCharCode(bytes[index]);
  }
  return `data:image/gif;base64,${btoa(binary)}`;
}

async function renderImplicitGifFrames(model, job, frameSpec, { mode = "orbit" } = {}) {
  const encoder = GIFEncoder();
  const transparent = shouldEncodeTransparentGif(job, frameSpec);
  const runtimeModelCache = new Map();
  for (const frameOutput of frameSpec.outputs) {
    const modelForOutput = cachedImplicitRuntimeModel(model, job, frameOutput, runtimeModelCache);
    const renderedOutput = await snapshotImplicitCadModel(THREE, modelForOutput, {
      width: frameSpec.width,
      height: frameSpec.height,
      camera: frameOutput.camera || job.camera || "iso",
      appearance: frameOutput.appearance || frameSpec.appearance,
      graphics: {
        ...(isObject(frameSpec.graphics) ? frameSpec.graphics : {}),
        ...(isObject(frameOutput.graphics) ? frameOutput.graphics : {}),
      },
      render: {
        ...(isObject(frameSpec.render) ? frameSpec.render : {}),
        ...(isObject(frameOutput.render) ? frameOutput.render : {}),
      },
    });
    const imageData = await dataUrlToImageData(renderedOutput.dataUrl, frameSpec.width, frameSpec.height);
    const frame = encodeGifFrameImageData(imageData, { transparent });
    encoder.writeFrame(frame.indexed, frameSpec.width, frameSpec.height, {
      palette: frame.palette,
      transparent: frame.transparent,
      transparentIndex: frame.transparentIndex,
      delay: 1000 / frameSpec.fps,
      repeat: frameSpec.loop === false ? -1 : 0,
      dispose: frame.transparent ? 2 : -1
    });
  }
  return {
    ok: true,
    mode,
    outputs: [{
      path: frameSpec.path,
      width: frameSpec.width,
      height: frameSpec.height,
      frameCount: frameSpec.frameCount,
      fps: frameSpec.fps,
      durationSeconds: frameSpec.durationSeconds,
      loop: frameSpec.loop !== false,
      mimeType: "image/gif",
      dataUrl: gifDataUrlFromEncoder(encoder)
    }],
    warnings: [],
  };
}

export async function runImplicitCadHeadlessRenderJob(job = {}) {
  const resolved = isObject(job.resolved) ? job.resolved : {};
  const inputUrl = String(resolved.inputUrl || job.inputUrl || job.url || "").trim();
  if (!inputUrl) {
    throw new Error("Implicit CAD snapshot job requires resolved.inputUrl");
  }
  const model = await loadCachedImplicitCadModule(inputUrl);
  const mode = String(job.mode || "view").trim().toLowerCase();
  if (mode === "orbit") {
    return renderImplicitGifFrames(model, job, orbitFrameOutputs(job), { mode: "orbit" });
  }
  if (mode === "animate" || implicitAnimationOptions(job, Array.isArray(job.outputs) ? job.outputs[0] : {})) {
    return renderImplicitGifFrames(model, job, implicitAnimationFrameOutputs(model, job), { mode: "animate" });
  }
  const outputs = Array.isArray(job.outputs) ? job.outputs : [];
  const renderedOutputs = [];
  const runtimeModelCache = new Map();
  for (const output of outputs) {
    const outputObject = isObject(output) ? output : {};
    const modelForOutput = cachedImplicitRuntimeModel(model, job, outputObject, runtimeModelCache);
    renderedOutputs.push(await snapshotImplicitCadModel(THREE, modelForOutput, {
      ...snapshotImplicitCadOutputOptions(job, outputObject),
    }));
  }
  return {
    ok: true,
    mode,
    outputs: renderedOutputs,
    warnings: [],
  };
}

if (typeof window !== "undefined") {
  window.__implicitCadSnapshotRender = runImplicitCadHeadlessRenderJob;
}
