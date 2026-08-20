import fs from "node:fs/promises";
import path from "node:path";
import { pathToFileURL } from "node:url";

import { normalizeImplicitCadModel } from "./model.js";
import { unsupportedNodeVersionMessage } from "./nodeModuleSupport.js";
import {
  exportImplicitCadAnimatedGlb,
  exportImplicitCadModel,
  exportImplicitCadModelFormats,
  IMPLICIT_CAD_EXPORT_FORMATS,
  normalizeImplicitExportFormat
} from "./exportModel.js";

function isObject(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function normalizeFormat(value) {
  return normalizeImplicitExportFormat(value);
}

/** Normalize one requested output. A request is either a bare format string or
 * `{ format, output }`; a missing/empty `output` means the default sibling path
 * (`<name>.<ext>` beside the model). A supplied relative path resolves against the
 * current working directory. */
function normalizeOutputRequests(outputs, inputPath) {
  const requests = [];
  const seenFormats = new Set();
  const seenPaths = new Map();
  for (const entry of Array.isArray(outputs) ? outputs : [outputs]) {
    if (!entry) {
      continue;
    }
    const rawFormat = typeof entry === "string" ? entry : entry.format;
    const rawOutput = typeof entry === "string" ? "" : entry.output;
    const format = normalizeFormat(rawFormat);
    if (!format) {
      throw new Error(`Unsupported implicit CAD export format: ${rawFormat || "(missing)"}`);
    }
    if (seenFormats.has(format)) {
      throw new Error(`Duplicate implicit CAD export format: ${format}`);
    }
    seenFormats.add(format);
    const output = String(rawOutput || "").trim()
      ? path.resolve(String(rawOutput).trim())
      : path.resolve(defaultImplicitCadExportPath(inputPath, format));
    const collision = seenPaths.get(output);
    if (collision) {
      throw new Error(`--${collision} and --${format} resolve to the same output path: ${output}`);
    }
    seenPaths.set(output, format);
    requests.push({ format, output });
  }
  return requests;
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
  let moduleValue;
  try {
    moduleValue = await import(inputUrl.href);
  } catch (error) {
    // Blame the interpreter when the interpreter is at fault: on Node < 22 a plain `.js`
    // model file fails with "Unexpected token 'export'", which reads as a broken model.
    const unsupported = unsupportedNodeVersionMessage(error, { inputPath: resolvedInput });
    if (unsupported) {
      throw new Error(unsupported, { cause: error });
    }
    throw error;
  }
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

/** Export one implicit model file to every requested format from ONE mesh pass.
 * `outputs` is a list of requested formats, each optionally carrying its own output
 * path (`{ format, output }`); an omitted path writes the sibling `<name>.<ext>`. */
export async function exportImplicitCadFile({
  input,
  outputs = [],
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
  const requests = normalizeOutputRequests(outputs, inputPath);
  if (!requests.length) {
    throw new Error(
      `At least one export format is required: ${IMPLICIT_CAD_EXPORT_FORMATS.map((format) => `--${format}`).join(", ")}.`
    );
  }
  if (animated && requests.some((request) => request.format !== "glb")) {
    throw new Error("Animated export is GLB-only: --animated cannot be combined with --stl or --3mf.");
  }
  const model = await loadImplicitCadModelFromPath(inputPath, {
    params,
    parameterValues,
    animationState,
  });
  const built = animated
    ? (() => {
        const result = exportImplicitCadAnimatedGlb(model, {
          animationId: animationState?.activeId,
          params: model.parameterValues,
          duration,
          frames,
          resolution,
          maxCells,
          normalEpsilon,
          ...(smoothNormals === undefined ? {} : { smoothNormals }),
        });
        return { mesh: result.mesh, model: result.model, outputs: [result] };
      })()
    : exportImplicitCadModelFormats(model, {
        formats: requests.map((request) => request.format),
        resolution,
        maxCells,
        normalEpsilon,
        ...(smoothNormals === undefined ? {} : { smoothNormals }),
      });
  const byFormat = new Map(built.outputs.map((exported) => [exported.format, exported]));
  const files = [];
  for (const request of requests) {
    const exported = byFormat.get(request.format);
    await fs.mkdir(path.dirname(request.output), { recursive: true });
    await fs.writeFile(request.output, exported.body);
    files.push({
      format: request.format,
      output: request.output,
      contentType: exported.contentType,
      bytes: exported.body.length,
    });
  }
  return {
    ok: true,
    input: inputPath,
    files,
    triangleCount: built.mesh.triangleCount,
    vertexCount: built.mesh.vertexCount,
    grid: built.mesh.grid,
    model: {
      name: built.model.name,
      bounds: built.model.bounds,
      units: built.model.units,
    },
  };
}

export {
  exportImplicitCadAnimatedGlb,
  exportImplicitCadModel,
  exportImplicitCadModelFormats,
  IMPLICIT_CAD_EXPORT_FORMATS
};
