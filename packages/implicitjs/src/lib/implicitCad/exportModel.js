import { buildImplicitAnimatedModel, findImplicitAnimation } from "./animation.js";
import { meshImplicitCadModel } from "./mesh.js";
import { normalizeImplicitCadModel } from "./model.js";
import { createImplicitCadColorEvaluator, createImplicitCadSdfEvaluator } from "./sdfEvaluator.js";
import { meshToAnimatedGlb, meshToFormat, triangleNormal } from "./exporters.js";

export const IMPLICIT_CAD_EXPORT_FORMATS = Object.freeze(["glb", "stl", "3mf"]);
export const IMPLICIT_EXPORT_FORMATS = IMPLICIT_CAD_EXPORT_FORMATS;

function isObject(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function finiteNumber(value, fallback = 0) {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : fallback;
}

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

export function normalizeImplicitExportFormat(value) {
  const normalized = String(value || "").trim().toLowerCase().replace(/^\./, "");
  if (normalized === "gltf") {
    return "glb";
  }
  return IMPLICIT_CAD_EXPORT_FORMATS.includes(normalized) ? normalized : "";
}

function rgb01ToHex(rgb) {
  const channel = (value) => {
    const numeric = Number(value);
    const clamped = Math.min(Math.max(Number.isFinite(numeric) ? numeric : 0, 0), 1);
    return Math.round(clamped * 255).toString(16).padStart(2, "0");
  };
  return `#${channel(rgb?.[0])}${channel(rgb?.[1])}${channel(rgb?.[2])}`;
}

/** Average the model's color function over the mesh to get one material display color.
 * The normal handed to `color(p, normal)` is the TRIANGLE's geometric normal, recomputed
 * from positions rather than read from `mesh.normals`: the display color is a property of
 * the surface, so it must not shift when one mesh pass serves several formats and
 * `smoothNormals` is chosen for the GLB. */
function sampleImplicitCadMeshColor(model, mesh, { sampleLimit = 768 } = {}) {
  if (!model?.colorSource) {
    return model?.material?.color;
  }
  try {
    const colorAt = createImplicitCadColorEvaluator(model);
    const positions = mesh.positions || new Float32Array();
    const vertexCount = Math.floor(positions.length / 3);
    const stride = Math.max(1, Math.floor(vertexCount / Math.max(sampleLimit, 1)));
    const sum = [0, 0, 0];
    let count = 0;
    for (let vertex = 0; vertex < vertexCount; vertex += stride) {
      const offset = vertex * 3;
      const color = colorAt(
        [positions[offset], positions[offset + 1], positions[offset + 2]],
        triangleNormal(positions, Math.floor(vertex / 3) * 9)
      );
      if (!color.every((component) => Number.isFinite(component))) {
        continue;
      }
      sum[0] += color[0];
      sum[1] += color[1];
      sum[2] += color[2];
      count += 1;
    }
    return count ? rgb01ToHex(sum.map((component) => component / count)) : model?.material?.color;
  } catch {
    return model?.material?.color;
  }
}

function estimateGradient(sdf, point, epsilon) {
  const [x, y, z] = point;
  const gradient = [
    finiteNumber(sdf(x + epsilon, y, z), 0) - finiteNumber(sdf(x - epsilon, y, z), 0),
    finiteNumber(sdf(x, y + epsilon, z), 0) - finiteNumber(sdf(x, y - epsilon, z), 0),
    finiteNumber(sdf(x, y, z + epsilon), 0) - finiteNumber(sdf(x, y, z - epsilon), 0),
  ];
  const length = Math.hypot(gradient[0], gradient[1], gradient[2]);
  return length > 1e-9
    ? [gradient[0] / length, gradient[1] / length, gradient[2] / length]
    : [0, 0, 1];
}

function projectMeshPositionsToModel(basePositions, targetModel, {
  iterations = 8,
  maxStep = null,
} = {}) {
  const sdf = createImplicitCadSdfEvaluator(targetModel);
  const targetPositions = new Float32Array(basePositions.length);
  const epsilon = Math.max(finiteNumber(targetModel.normalEpsilon, targetModel.radius * 0.001), 1e-4);
  const stepLimit = Math.max(
    finiteNumber(maxStep, finiteNumber(targetModel.maxStep, targetModel.radius * 0.08)),
    epsilon
  );
  for (let index = 0; index < basePositions.length; index += 3) {
    const point = [
      basePositions[index],
      basePositions[index + 1],
      basePositions[index + 2],
    ];
    for (let pass = 0; pass < iterations; pass += 1) {
      const distance = finiteNumber(sdf(point[0], point[1], point[2]), 0);
      if (Math.abs(distance) <= epsilon * 0.35) {
        break;
      }
      const normal = estimateGradient(sdf, point, epsilon);
      const step = clamp(distance, -stepLimit, stepLimit);
      point[0] -= normal[0] * step;
      point[1] -= normal[1] * step;
      point[2] -= normal[2] * step;
    }
    targetPositions[index] = point[0];
    targetPositions[index + 1] = point[1];
    targetPositions[index + 2] = point[2];
  }
  return targetPositions;
}

function definitionFromModel(modelValue) {
  if (modelValue?.definition?.buildModel) {
    return modelValue.definition;
  }
  if (modelValue?.buildModel) {
    return modelValue;
  }
  return normalizeImplicitCadModel(modelValue).definition;
}

function runtimeModelForExport(modelValue, {
  params = null,
  parameterValues = null,
  animationState = null,
} = {}) {
  const model = normalizeImplicitCadModel(modelValue);
  const nextParams = isObject(params)
    ? params
    : isObject(parameterValues)
      ? parameterValues
      : null;
  if (!nextParams && !animationState) {
    return model;
  }
  return typeof model.definition?.buildModel === "function"
    ? model.definition.buildModel(
        nextParams || model.parameterValues || model.defaultParameterValues || {},
        isObject(animationState) ? animationState : model.animationState || {}
      )
    : model;
}

/** Export one implicit model to SEVERAL formats from ONE mesh pass. Meshing is the
 * expensive step, so every requested format is serialized from the same triangles —
 * `--stl --3mf --glb` samples the SDF once, not three times. */
export function exportImplicitCadModelFormats(modelValue, {
  formats = ["glb"],
  params = null,
  parameterValues = null,
  animationState = null,
  resolution = 96,
  maxCells = undefined,
  normalEpsilon = undefined,
  // One mesh serves every format, so this is a single shared choice rather than a
  // per-format one. It only changes the GLB: the STL writer recomputes facet normals
  // from positions and the 3MF writer reads positions only.
  smoothNormals = true,
} = {}) {
  const requested = [];
  for (const value of Array.isArray(formats) ? formats : [formats]) {
    const normalized = normalizeImplicitExportFormat(value);
    if (!normalized) {
      throw new Error(`Unsupported implicit CAD export format: ${value || "(missing)"}`);
    }
    if (!requested.includes(normalized)) {
      requested.push(normalized);
    }
  }
  if (!requested.length) {
    throw new Error("Implicit CAD export requires at least one format.");
  }
  const model = runtimeModelForExport(modelValue, {
    params,
    parameterValues,
    animationState,
  });
  const mesh = meshImplicitCadModel(model, {
    resolution,
    maxCells,
    normalEpsilon,
    smoothNormals,
  });
  if (!mesh.triangleCount) {
    throw new Error("Implicit CAD export produced an empty mesh. Check bounds, parameters, and resolution.");
  }
  const options = {
    name: model.name,
    color: sampleImplicitCadMeshColor(model, mesh),
  };
  const outputs = requested.map((format) => ({
    ...meshToFormat(mesh, format, options),
    format,
  }));
  return { mesh, model, outputs };
}

export function exportImplicitCadModel(modelValue, {
  format = "glb",
  params = null,
  parameterValues = null,
  animationState = null,
  resolution = 96,
  maxCells = undefined,
  normalEpsilon = undefined,
  smoothNormals = undefined,
} = {}) {
  const outputFormat = normalizeImplicitExportFormat(format);
  const { mesh, model, outputs } = exportImplicitCadModelFormats(modelValue, {
    formats: [format],
    params,
    parameterValues,
    animationState,
    resolution,
    maxCells,
    normalEpsilon,
    smoothNormals: smoothNormals ?? outputFormat === "glb",
  });
  return {
    ...outputs[0],
    mesh,
    model,
    format: outputFormat,
  };
}

export function exportImplicitCadAnimatedGlb(modelOrDefinition, {
  animationId = "",
  params = null,
  parameterValues = null,
  duration = undefined,
  frames = 18,
  resolution = 64,
  maxCells = undefined,
  normalEpsilon = undefined,
  smoothNormals = true,
  projectionIterations = 8,
} = {}) {
  const definition = definitionFromModel(modelOrDefinition);
  const animation = findImplicitAnimation(definition, animationId);
  if (!animation) {
    throw new Error("Animated GLB export requires an animation on the implicit model.");
  }
  const baseValues = isObject(params)
    ? params
    : isObject(parameterValues)
      ? parameterValues
      : modelOrDefinition?.parameterValues || definition.defaultParameterValues || {};
  const durationSeconds = Math.max(finiteNumber(duration, animation.duration), 0.001);
  const frameCount = Math.max(3, Math.min(Math.floor(finiteNumber(frames, 18)), 48));
  const baseModel = buildImplicitAnimatedModel(definition, {
    animationId: animation.id,
    params: baseValues,
    elapsedSec: 0,
    playing: false
  });
  const baseMesh = meshImplicitCadModel(baseModel, {
    resolution,
    maxCells,
    normalEpsilon,
    smoothNormals,
  });
  if (!baseMesh.triangleCount) {
    throw new Error("Animated GLB export produced an empty base mesh. Check bounds, parameters, and resolution.");
  }

  const targetPositions = [];
  const times = [];
  for (let frame = 0; frame < frameCount; frame += 1) {
    const elapsedSec = (durationSeconds * frame) / (frameCount - 1);
    times.push(elapsedSec);
    if (frame === 0 || (animation.loop !== false && frame === frameCount - 1)) {
      continue;
    }
    const frameModel = buildImplicitAnimatedModel(definition, {
      animationId: animation.id,
      params: baseValues,
      elapsedSec,
      playing: false
    });
    targetPositions.push(projectMeshPositionsToModel(baseMesh.positions, frameModel, {
      iterations: projectionIterations,
    }));
  }

  const body = meshToAnimatedGlb(baseMesh, {
    name: baseModel.name,
    color: sampleImplicitCadMeshColor(baseModel, baseMesh),
    duration: durationSeconds,
    times,
    targetPositions,
  });
  return {
    body,
    contentType: "model/gltf-binary",
    extension: ".glb",
    format: "glb",
    mesh: baseMesh,
    model: baseModel,
    animation,
    frameCount,
    duration: durationSeconds,
  };
}

export const exportImplicitModel = exportImplicitCadModel;
export const exportImplicitAnimatedGlb = exportImplicitCadAnimatedGlb;
