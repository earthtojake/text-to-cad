import fs from "node:fs/promises";
import path from "node:path";
import { pathToFileURL } from "node:url";

import { normalizeImplicitCadModel } from "./model.js";
import {
  exportImplicitCadAnimatedGlb,
  exportImplicitCadModel,
  IMPLICIT_CAD_EXPORT_FORMATS,
  normalizeImplicitExportFormat
} from "./exportModel.js";

function isObject(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function normalizeFormat(value) {
  return normalizeImplicitExportFormat(value);
}

function formatFromOutputPath(outputPath) {
  return normalizeFormat(path.extname(String(outputPath || "")).slice(1));
}

export function defaultImplicitCadExportPath(inputPath, format = "glb") {
  const normalizedFormat = normalizeFormat(format) || "glb";
  const raw = String(inputPath || "").trim();
  const basename = raw
    .replace(/\.implicit\.(?:mjs|js)$/i, "")
    .replace(/\.(?:mjs|js)$/i, "");
  return `${basename}.${normalizedFormat}`;
}

export async function loadImplicitCadModelFromPath(inputPath, {
  params = null,
  parameterValues = null,
  animationState = null,
} = {}) {
  const resolvedInput = path.resolve(String(inputPath || ""));
  const stats = await fs.stat(resolvedInput);
  if (!stats.isFile()) {
    throw new Error(`Implicit CAD input is not a file: ${resolvedInput}`);
  }
  const inputUrl = pathToFileURL(resolvedInput);
  inputUrl.searchParams.set("mtime", String(Number(stats.mtimeMs)));
  const moduleValue = await import(inputUrl.href);
  const defaultModel = normalizeImplicitCadModel(moduleValue, { sourceUrl: inputUrl.href });
  const nextParams = isObject(params) ? params : isObject(parameterValues) ? parameterValues : null;
  if (nextParams || animationState) {
    return defaultModel.definition.buildModel(
      nextParams || defaultModel.defaultParameterValues,
      isObject(animationState) ? animationState : defaultModel.animationState
    );
  }
  return defaultModel;
}

export async function exportImplicitCadFile({
  input,
  output = "",
  format = "",
  params = null,
  parameterValues = null,
  animationState = null,
  animated = false,
  frames = undefined,
  duration = undefined,
  resolution = 96,
  maxCells = undefined,
  normalEpsilon = undefined,
  smoothNormals = undefined,
} = {}) {
  const inputPath = path.resolve(String(input || ""));
  const outputFormat = animated ? "glb" : normalizeFormat(format) || formatFromOutputPath(output) || "glb";
  const outputPath = path.resolve(output || defaultImplicitCadExportPath(inputPath, outputFormat));
  const model = await loadImplicitCadModelFromPath(inputPath, {
    params,
    parameterValues,
    animationState,
  });
  const result = animated
    ? exportImplicitCadAnimatedGlb(model, {
        animationId: animationState?.activeId,
        params: model.parameterValues,
        duration,
        frames,
        resolution,
        maxCells,
        normalEpsilon,
        smoothNormals,
      })
    : exportImplicitCadModel(model, {
        format: outputFormat,
        resolution,
        maxCells,
        normalEpsilon,
        smoothNormals,
      });
  await fs.mkdir(path.dirname(outputPath), { recursive: true });
  await fs.writeFile(outputPath, result.body);
  return {
    ok: true,
    input: inputPath,
    output: outputPath,
    format: result.format,
    contentType: result.contentType,
    bytes: result.body.length,
    triangleCount: result.mesh.triangleCount,
    vertexCount: result.mesh.vertexCount,
    grid: result.mesh.grid,
    model: {
      name: result.model.name,
      bounds: result.model.bounds,
      units: result.model.units,
    },
  };
}

export {
  exportImplicitCadAnimatedGlb,
  exportImplicitCadModel,
  IMPLICIT_CAD_EXPORT_FORMATS
};
