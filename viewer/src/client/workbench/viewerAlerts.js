import { entrySourceFormat } from "cadjs/lib/fileFormats.js";
import { RENDER_FORMAT } from "./constants.js";
import {
  stepArtifactHasRenderableGlb,
  stepArtifactStatusMessage
} from "./fileStatusItems.js";
import { entryStepSourceKind } from "./entryIconStatus.js";
import { fileKey } from "./sidebar.js";

export const CAD_BUILD_COMMANDS = Object.freeze({
  dxf: "",
  step: "python -m cadpy.step_artifact --repo-root . --step",
  urdf: "",
  sdf: ""
});

function commandForFile(command, fileRef) {
  const normalizedCommand = String(command || "").trim();
  return normalizedCommand ? `${normalizedCommand} ${fileRef}` : "";
}

export function buildCadCommand(fileRef, entry = null) {
  const sourceFormat = entrySourceFormat(entry);
  if (sourceFormat === RENDER_FORMAT.STEP && entryStepSourceKind(entry) === "python") {
    return "";
  }
  if (sourceFormat === RENDER_FORMAT.DXF) {
    return commandForFile(CAD_BUILD_COMMANDS.dxf, fileRef);
  }
  if (sourceFormat === RENDER_FORMAT.URDF || sourceFormat === RENDER_FORMAT.SRDF) {
    return String(entry?.kind || "").trim().toLowerCase() === "srdf" ? "" : commandForFile(CAD_BUILD_COMMANDS.urdf, fileRef);
  }
  if (sourceFormat === RENDER_FORMAT.SDF) {
    return commandForFile(CAD_BUILD_COMMANDS.sdf, fileRef);
  }
  if (sourceFormat === RENDER_FORMAT.STL) {
    return "";
  }
  if (sourceFormat === RENDER_FORMAT.THREE_MF) {
    return "";
  }
  if (sourceFormat === RENDER_FORMAT.GLB) {
    return "";
  }
  if (sourceFormat === RENDER_FORMAT.GCODE) {
    return "";
  }
  return commandForFile(CAD_BUILD_COMMANDS.step, fileRef);
}

export function buildViewerMeshAlert(entry, hasMeshData, loadError) {
  const fileRef = fileKey(entry);
  if (!fileRef) {
    return null;
  }

  const sourceFormat = entrySourceFormat(entry);
  const command = buildCadCommand(fileRef, entry);
  const meshSidecarFormat = sourceFormat === RENDER_FORMAT.STL ||
    sourceFormat === RENDER_FORMAT.THREE_MF ||
    sourceFormat === RENDER_FORMAT.GLB ||
    sourceFormat === RENDER_FORMAT.GCODE;
  const meshSidecarLabel = sourceFormat === RENDER_FORMAT.THREE_MF
    ? "3MF"
    : sourceFormat === RENDER_FORMAT.GLB
      ? "GLB"
      : sourceFormat === RENDER_FORMAT.GCODE
        ? "G-code"
        : "STL";
  const reloadResolution = meshSidecarFormat
    ? `Confirm the ${meshSidecarLabel} exists in the repo and reload the page.`
    : "Try reloading the page. If the problem persists, rebuild the render assets for this entry.";
  const missingResolution = meshSidecarFormat
    ? `Confirm the ${meshSidecarLabel} exists in the repo and reload the page.`
    : "Rebuild the CAD assets for this entry, then reload the page.";

  const stepArtifactError = sourceFormat === RENDER_FORMAT.STEP && entry?.artifact?.ok === false
    ? entry?.artifact
    : null;
  if (stepArtifactError && !hasMeshData) {
    const code = String(stepArtifactError.error || "").trim();
    const stale = stepArtifactError.stale === true || code === "stale_step_artifact";
    const missingGlb = code === "missing_glb";
    const summary = stale
      ? "STEP artifact stale"
      : missingGlb
        ? "STEP artifact missing"
        : "STEP artifact unavailable";
    const renderableGlb = stepArtifactHasRenderableGlb(entry);
    if (!renderableGlb || !loadError) {
      return {
        severity: renderableGlb ? "warning" : "error",
        ...(renderableGlb ? { blocking: false } : {}),
        compact: true,
        summary,
        title: summary,
        message: stepArtifactStatusMessage(stepArtifactError),
        command
      };
    }
  }

  if (loadError) {
    return {
      severity: "error",
      summary: "Mesh load failed",
      title: "Failed to load render mesh",
      message: loadError,
      resolution: reloadResolution,
      command
    };
  }

  if (!hasMeshData) {
    return {
      severity: "error",
      summary: "Mesh unavailable",
      title: "No mesh data is available",
      message: "The selected entry is listed in the CAD catalog but no renderable mesh data could be loaded for it.",
      resolution: missingResolution,
      command
    };
  }

  return null;
}

export function buildViewerDxfAlert(fileRef, hasDxfData, loadError, previewError) {
  if (!fileRef) {
    return null;
  }

  const command = commandForFile(CAD_BUILD_COMMANDS.dxf, fileRef);

  if (loadError) {
    return {
      severity: "error",
      summary: "DXF load failed",
      title: "Failed to load DXF flat pattern",
      message: loadError,
      resolution: "Try reloading the page. If the problem persists, rebuild the CAD assets for this entry.",
      command
    };
  }

  if (previewError) {
    return {
      severity: "warning",
      summary: "DXF 3D preview unavailable",
      title: "Failed to build the DXF 3D preview",
      message: previewError,
      resolution: "The flat pattern can still be shown, but the 3D extrusion preview could not be built from the current DXF geometry.",
      command
    };
  }

  if (!hasDxfData) {
    return {
      severity: "error",
      summary: "DXF unavailable",
      title: "No DXF flat pattern is available",
      message: "The selected entry does not have a ready DXF companion asset for the flat-pattern viewer.",
      resolution: "Rebuild the CAD assets for this entry, then reload the page.",
      command
    };
  }

  return null;
}

export function buildViewerImplicitAlert(fileRef, hasImplicitData, loadError) {
  if (!fileRef) {
    return null;
  }
  if (loadError) {
    return {
      severity: "error",
      summary: "Implicit CAD load failed",
      title: "Failed to load implicit CAD module",
      message: loadError,
      resolution: "Check the exported GLSL distance function and reload the page."
    };
  }
  if (!hasImplicitData) {
    return {
      severity: "error",
      summary: "Implicit CAD unavailable",
      title: "No implicit CAD model is available",
      message: "The selected entry is listed in the CAD catalog but the implicit CAD module did not load.",
      resolution: "Confirm the .implicit.js or .implicit.mjs file exists and exports an implicit.js/0.1.0 model."
    };
  }
  return null;
}
