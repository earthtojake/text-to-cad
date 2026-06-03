import {
  isRobotRenderFormat,
  RENDER_FORMAT
} from "cadjs/lib/fileFormats.js";
import {
  stepArtifactCanGenerate,
  stepArtifactGenerationInProgress,
  stepArtifactIsStale,
  stepArtifactNeedsWarning
} from "./stepArtifactStatus.js";

export function entryIconStatus(entry, {
  sourceFormat = "",
  entryKey = "",
  hasMesh = true,
  hasDxf = true,
  hasGcode = true,
  hasImplicit = true,
  hasUrdf = true,
  activeGenerationFiles = [],
  activeStepArtifactGenerationFile = "",
  activeStepArtifactGenerationFiles = [],
  stepArtifactGenerationAvailable = true
} = {}) {
  const normalizedSourceFormat = String(sourceFormat || "").trim().toLowerCase();
  const activeScriptGenerationFileSet = new Set(
    [
      ...(Array.isArray(activeGenerationFiles)
        ? activeGenerationFiles
        : activeGenerationFiles
          ? [activeGenerationFiles]
          : [])
    ]
      .map((file) => String(file || "").trim())
      .filter(Boolean)
  );
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
  const pending = normalizedSourceFormat === RENDER_FORMAT.DXF
    ? !hasDxf
    : normalizedSourceFormat === RENDER_FORMAT.GCODE
    ? !hasGcode
    : normalizedSourceFormat === RENDER_FORMAT.IMPLICIT
      ? !hasImplicit
    : isRobotRenderFormat(normalizedSourceFormat)
      ? !hasUrdf
      : !hasMesh;
  const artifactGenerationFiles = [
    ...activeArtifactGenerationFileSet,
    ...activeScriptGenerationFileSet
  ];
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
  const generatorRunning = Boolean(entryKey && activeScriptGenerationFileSet.has(entryKey));
  const artifactWarning = !generatorRunning &&
    !artifactGenerationInProgress &&
    stepArtifactNeedsWarning(entry, normalizedSourceFormat, {
      generationAvailable: stepArtifactGenerationAvailable
    });
  const artifactGenerating = Boolean(
    artifactBuildable &&
    !generatorRunning &&
    artifactGenerationInProgress
  );
  const loading = generatorRunning || artifactGenerating || (pending && !artifactWarning && !artifactBuildable);
  const statusLabel = generatorRunning
    ? "generating"
    : artifactGenerating
    ? "generating artifact"
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
