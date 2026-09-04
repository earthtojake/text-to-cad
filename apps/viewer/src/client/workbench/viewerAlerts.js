import { entrySourceFormat } from "cadgen-js/lib/fileFormats.js";
import {
  ASSET_KIND,
  renderCapabilities
} from "cadgen-js/lib/renderCapabilities.js";
import {
  stepArtifactHasRenderableGlb,
  stepArtifactStatusMessage
} from "./fileStatusItems.js";
import { failedStepArtifact } from "./stepArtifactStatus.js";
import { fileKey } from "./sidebar.js";

// A viewer alert is a TITLE and a DESCRIPTION (`message`), plus `severity` and the
// short `summary` the sidebar and status tab key on. Nothing else: no resolution
// paragraph, no rebuild command — the description says what went wrong, and the
// document's own tooling is where a rebuild happens.
export function buildViewerMeshAlert(entry, hasMeshData, loadError, artifact = null) {
  const fileRef = fileKey(entry);
  if (!fileRef) {
    return null;
  }

  const sourceFormat = entrySourceFormat(entry);

  // A failed compile is the REASON there is no mesh, so it outranks the generic "no
  // mesh data" card — and it applies to every compiled kind, not just STEP. The
  // description is the compile job's own reason, verbatim.
  if (artifact?.status === "failed" && !hasMeshData) {
    const detail = String(artifact.error || "").trim();
    return {
      severity: "error",
      summary: "Compile failed",
      title: "Compile failed",
      message: detail || "The document could not be compiled."
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
        message: stepArtifactStatusMessage(stepArtifactError)
      };
    }
  }

  if (loadError) {
    return {
      severity: "error",
      summary: "Mesh load failed",
      title: "Failed to load render mesh",
      message: loadError
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
      message: "The selected entry is listed in the CAD catalog but no renderable mesh data could be loaded for it."
    };
  }

  return null;
}

