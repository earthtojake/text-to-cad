import { renderImplicitCadToDataUrl } from "./render.js";

const DEFAULT_SNAPSHOT_WIDTH = 1200;
const DEFAULT_SNAPSHOT_HEIGHT = 900;
const DEFAULT_APPEARANCE = "workbench";
const PNG_MIME_TYPE = "image/png";

function isPlainObject(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function positiveInteger(value, fallback) {
  const numeric = Math.floor(Number(value));
  return Number.isFinite(numeric) && numeric > 0 ? numeric : fallback;
}

function mergedPlainObject(...values) {
  return values.reduce((merged, value) => (
    isPlainObject(value) ? { ...merged, ...value } : merged
  ), {});
}

export function snapshotImplicitCadOutputOptions(job = {}, output = {}) {
  const normalizedJob = isPlainObject(job) ? job : {};
  const normalizedOutput = isPlainObject(output) ? output : {};
  const width = positiveInteger(
    normalizedOutput.width ?? normalizedJob.width,
    DEFAULT_SNAPSHOT_WIDTH
  );
  const height = positiveInteger(
    normalizedOutput.height ?? normalizedJob.height,
    DEFAULT_SNAPSHOT_HEIGHT
  );

  return {
    path: String(normalizedOutput.path || normalizedJob.output || ""),
    width,
    height,
    camera: normalizedOutput.camera || normalizedJob.camera || "iso",
    appearance: normalizedOutput.appearance || normalizedJob.appearance || DEFAULT_APPEARANCE,
    graphics: mergedPlainObject(normalizedJob.graphics, normalizedOutput.graphics),
    render: mergedPlainObject(normalizedJob.render, normalizedOutput.render),
  };
}

export async function snapshotImplicitCadModel(THREE, model, options = {}) {
  const normalizedOptions = isPlainObject(options.job) || isPlainObject(options.output)
    ? snapshotImplicitCadOutputOptions(options.job, options.output)
    : snapshotImplicitCadOutputOptions(options, options);

  return {
    path: normalizedOptions.path,
    width: normalizedOptions.width,
    height: normalizedOptions.height,
    mimeType: PNG_MIME_TYPE,
    dataUrl: await renderImplicitCadToDataUrl(THREE, model, {
      width: normalizedOptions.width,
      height: normalizedOptions.height,
      camera: normalizedOptions.camera,
      appearance: normalizedOptions.appearance,
      graphics: normalizedOptions.graphics,
      render: normalizedOptions.render,
    }),
  };
}

export async function snapshotImplicitCadModelToDataUrl(THREE, model, options = {}) {
  const result = await snapshotImplicitCadModel(THREE, model, options);
  return result.dataUrl;
}
