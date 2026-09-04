import { entrySourceFormat } from "cadgen-js/lib/fileFormats.js";
import {
  ASSET_KIND,
  isArtifactManagedFormat,
  rebuildCommandForEntry,
  renderCapabilities,
  renderFormatLabel
} from "cadgen-js/lib/renderCapabilities.js";
import {
  stepArtifactHasRenderableGlb,
  stepArtifactStatusMessage
} from "./fileStatusItems.js";
import { failedStepArtifact } from "./stepArtifactStatus.js";
import { fileKey } from "./sidebar.js";

// The command to rebuild an entry by hand, shown on build-failure cards, comes
// straight off the format's registry row: it acts on the document that is
// there, so how that document came to exist does not change it.
export function buildViewerMeshAlert(entry, hasMeshData, loadError, artifact = null) {
  const fileRef = fileKey(entry);
  if (!fileRef) {
    return null;
  }

  const sourceFormat = entrySourceFormat(entry);
  const command = rebuildCommandForEntry(sourceFormat, fileRef);
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
  if (artifact?.status === "failed" && !hasMeshData) {
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
    const missingGlb = code === "missing_glb";
    const summary = missingGlb ? "STEP artifact missing" : "STEP artifact unavailable";
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

  // A dimensioned DRAWING has no mesh BY DESIGN -- it encloses nothing to extrude
  // and renders as lines (issue #246). The profile is decided from the PARSED file
  // now, which this alert path cannot see, so any meshless DXF stays quiet: a
  // layout's mesh is built from the same parse, and a genuinely broken file
  // reports through loadError above.
  if (!hasMeshData && renderCapabilities(entrySourceFormat(entry)).assetKind === ASSET_KIND.DRAWING) {
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

