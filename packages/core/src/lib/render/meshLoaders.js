import {
  renderFormatFromPath,
  RENDER_FORMAT
} from "../fileFormats.js";
import {
  loadRender3Mf,
  loadRenderDxfMesh,
  loadRenderGlb,
  loadRenderStl,
  peekRender3Mf,
  peekRenderDxfMesh,
  peekRenderGlb,
  peekRenderStl
} from "../renderAssetClient.js";

function meshRenderFormat(format) {
  return format === RENDER_FORMAT.STL
    || format === RENDER_FORMAT.THREE_MF
    || format === RENDER_FORMAT.GLB
    || format === RENDER_FORMAT.DXF
    ? format
    : "";
}

function renderFormatFromMeshAssetUrl(url) {
  const directFormat = meshRenderFormat(renderFormatFromPath(url, {
    baseUrl: typeof window !== "undefined" ? window.location.href : ""
  }));
  if (directFormat) {
    return directFormat;
  }
  try {
    const parsedUrl = new URL(url, typeof window !== "undefined" ? window.location.href : "http://localhost/");
    for (const parameterName of ["file", "path"]) {
      const parameterValue = parsedUrl.searchParams.get(parameterName);
      const parameterFormat = meshRenderFormat(renderFormatFromPath(parameterValue || "", {
        baseUrl: parsedUrl.href
      }));
      if (parameterFormat) {
        return parameterFormat;
      }
    }
  } catch {
    // Fall through to the caller-provided fallback.
  }
  return "";
}

export function meshFormatFromUrl(url) {
  return renderFormatFromMeshAssetUrl(url) || RENDER_FORMAT.GLB;
}

function normalizeMeshFallback(fallback) {
  return fallback === RENDER_FORMAT.STL || fallback === RENDER_FORMAT.THREE_MF || fallback === RENDER_FORMAT.GLB
    ? fallback
    : RENDER_FORMAT.GLB;
}

export function resolveMeshFormatFromUrl(url, { fallback = RENDER_FORMAT.GLB } = {}) {
  return renderFormatFromMeshAssetUrl(url) || normalizeMeshFallback(fallback);
}

export function peekRenderMeshByUrl(url, options = {}) {
  const format = resolveMeshFormatFromUrl(url, options);
  if (format === RENDER_FORMAT.DXF) {
    return peekRenderDxfMesh(url);
  }
  if (format === RENDER_FORMAT.STL) {
    return peekRenderStl(url);
  }
  if (format === RENDER_FORMAT.THREE_MF) {
    return peekRender3Mf(url);
  }
  return peekRenderGlb(url);
}

export async function loadRenderMeshByUrl(url, options = {}) {
  const format = resolveMeshFormatFromUrl(url, options);
  if (format === RENDER_FORMAT.DXF) {
    return loadRenderDxfMesh(url, options);
  }
  if (format === RENDER_FORMAT.STL) {
    return loadRenderStl(url, options);
  }
  if (format === RENDER_FORMAT.THREE_MF) {
    return loadRender3Mf(url, options);
  }
  return loadRenderGlb(url, options);
}
