import {
  assetKindForRenderFormat,
  ASSET_KIND
} from "cadjs/lib/renderCapabilities.js";
import {
  stepArtifactCanGenerate,
  stepArtifactGenerationInProgress,
  stepArtifactIsStale,
  stepArtifactNeedsWarning
} from "./stepArtifactStatus.js";

export function entryIconStatus(entry, {
  sourceFormat = "",
  hasMesh = true,
  hasDxf = true,
  hasImplicit = true,
  hasUrdf = true,
  activeStepArtifactGenerationFile = "",
  activeStepArtifactGenerationFiles = [],
  // Entries the viewer is actively loading RIGHT NOW -- an asset read, a decode, a module
  // load. Distinct from artifact generation: a built package still has to be fetched and
  // decoded, and during that the file explorer should say so.
  loadingFiles = [],
  stepArtifactGenerationAvailable = true
} = {}) {
  const normalizedSourceFormat = String(sourceFormat || "").trim().toLowerCase();
  const activeArtifactGenerationFileSet = new Set(
    [
      ...(Array.isArray(activeStepArtifactGenerationFiles)
        ? activeStepArtifactGenerationFiles
        : activeStepArtifactGenerationFiles
          ? [activeStepArtifactGenerationFiles]
          : []),
      ...(Array.isArray(activeStepArtifactGenerationFile)
        ? activeStepArtifactGenerationFile
        : activeStepArtifactGenerationFile
          ? [activeStepArtifactGenerationFile]
          : [])
    ]
      .map((file) => String(file || "").trim())
      .filter(Boolean)
  );
  // "Has this entry's asset arrived yet?" — one question, asked against whichever asset the
  // format actually loads. The caller still passes one flag per asset kind because the file
  // list holds all of them at once; the format no longer decides which flag by name.
  const loadedByAssetKind = {
    [ASSET_KIND.MESH]: hasMesh,
    [ASSET_KIND.DRAWING]: hasDxf,
    [ASSET_KIND.IMPLICIT]: hasImplicit,
    [ASSET_KIND.ROBOT]: hasUrdf
  };
  const pending = loadedByAssetKind[assetKindForRenderFormat(normalizedSourceFormat)] === false;
  const artifactGenerationFiles = [...activeArtifactGenerationFileSet];
  const artifactGenerationInProgress = stepArtifactGenerationInProgress({
    entry,
    activeGenerationFiles: artifactGenerationFiles
  });
  const options = {
    generationAvailable: stepArtifactGenerationAvailable || artifactGenerationInProgress
  };
  const artifactCanGenerate = stepArtifactCanGenerate(entry, normalizedSourceFormat, options);
  const artifactBuildable = artifactCanGenerate;
  const artifactStale = stepArtifactIsStale(entry, normalizedSourceFormat);
  const artifactErrorCode = String(entry?.artifact?.error || "").trim();
  const artifactWarning = !artifactGenerationInProgress &&
    stepArtifactNeedsWarning(entry, normalizedSourceFormat, {
      generationAvailable: stepArtifactGenerationAvailable
    });
  const artifactGenerating = Boolean(artifactBuildable && artifactGenerationInProgress);
  // A model that simply lacks a built __cadgen__ artifact is NOT "loading" — nothing loads in a
  // static file list (generation happens lazily when the model is opened). Only an actively-running
  // generation shows a spinner; an un-built entry just shows its normal type icon.
  // Same file-ref matching the generation check uses -- reused rather than reimplemented,
  // so "which entry is this?" cannot answer differently in two places.
  const assetLoading = stepArtifactGenerationInProgress({
    entry,
    activeGenerationFiles: loadingFiles
  });
  const loading = artifactGenerating || assetLoading;
  const statusLabel = artifactGenerating
    ? "generating artifact"
    : assetLoading
      ? "loading"
    : artifactWarning
      ? (artifactStale ? "artifact stale" : artifactErrorCode === "missing_glb" ? "artifacts missing" : "artifact warning")
      : artifactBuildable
        ? "artifact generates on open"
        : pending
          ? "pending"
          : "ready";

  return {
    artifactBuildable,
    artifactGenerating,
    artifactStale,
    artifactWarning,
    loading,
    pending,
    sourceFormat: normalizedSourceFormat,
    statusLabel
  };
}

export function entryStepSourceKind(entry) {
  const artifactSourceKind = String(entry?.artifact?.sourceKind || "").trim().toLowerCase();
  if (artifactSourceKind === "python") {
    return artifactSourceKind;
  }
  const sourceKind = String(entry?.sourceKind || entry?.stepSourceKind || "").trim().toLowerCase();
  if (sourceKind === "python") {
    return sourceKind;
  }
  return "";
}

export function entryIsPythonBackedStep(entry) {
  return entryStepSourceKind(entry) === "python";
}
