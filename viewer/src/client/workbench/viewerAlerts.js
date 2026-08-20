import { entryIsDrawingDocument } from "cadjs/lib/entryAssets.js";
import { entrySourceFormat } from "cadjs/lib/fileFormats.js";
import {
  isArtifactManagedFormat,
  rebuildCommandForEntry,
  renderFormatLabel
} from "cadjs/lib/renderCapabilities.js";
import {
  stepArtifactHasRenderableGlb,
  stepArtifactStatusMessage
} from "./fileStatusItems.js";
import { failedStepArtifact } from "./stepArtifactStatus.js";
import { entryStepSourceKind } from "./entryIconStatus.js";
import { fileKey } from "./sidebar.js";

// The command to rebuild an entry by hand, shown on build-failure cards.
//
// This was eight format checks that all returned "" except one — every branch but imported
// STEP existed only to say "nothing to run here". The command now lives on the registry row
// and the only rule left is the one that is genuinely about the ENTRY rather than the
// format: a generator-backed STEP is rebuilt by the viewer, so telling the user to run the
// importer against it would be wrong.
export function buildCadCommand(fileRef, entry = null) {
  if (entryStepSourceKind(entry) === "python") {
    return "";
  }
  return rebuildCommandForEntry(entrySourceFormat(entry), fileRef);
}

export function buildViewerMeshAlert(entry, hasMeshData, loadError, artifact = null) {
  const fileRef = fileKey(entry);
  if (!fileRef) {
    return null;
  }

  const sourceFormat = entrySourceFormat(entry);
  const command = buildCadCommand(fileRef, entry);
  // A format the viewer does not build is its own asset: there is nothing to rebuild, so
  // the only useful advice is "is the file there?". That is `artifactManaged`, not a list
  // of the three mesh formats — a fourth would have inherited the wrong advice.
  const ownAsset = !isArtifactManagedFormat(sourceFormat);
  const ownAssetResolution = `Confirm the ${renderFormatLabel(sourceFormat) || "source file"} exists in the repo and reload the page.`;
  const reloadResolution = ownAsset
    ? ownAssetResolution
    : "Try reloading the page. If the problem persists, rebuild the render assets for this entry.";
  const missingResolution = ownAsset
    ? ownAssetResolution
    : "Rebuild the CAD assets for this entry, then reload the page.";

  // A failed render-artifact build is the REASON there is no mesh, so it outranks the
  // generic "no mesh data" card — and it applies to every artifact-managed kind, not just
  // STEP. A DXF whose build rejected an entity used to report only that nothing loaded,
  // which told the user neither what was wrong nor that a rebuild would not help.
  if (artifact?.status === "error" && !hasMeshData) {
    const detail = String(artifact.error || "").trim();
    return {
      severity: "error",
      summary: "Build failed",
      title: "Render artifact build failed",
      message: detail || "The render artifact for this entry could not be built.",
      resolution: missingResolution,
      command
    };
  }

  const stepArtifactError = failedStepArtifact(entry, sourceFormat);
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

  // A dimensioned DRAWING has no mesh BY DESIGN -- it encloses nothing to extrude, bakes no
  // preview and renders as lines (issue #246). Reporting that as an error told the user to
  // rebuild assets that were already complete. A genuine build failure still reports above.
  if (!hasMeshData && entryIsDrawingDocument(entry)) {
    return null;
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
