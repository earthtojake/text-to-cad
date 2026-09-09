import { entryHasMesh } from "cadgen-js/lib/entryAssets.js";
import { viewerRootRelativePath } from "./pathPresentation.js";
import {
  stepArtifactIssueShouldSuppress
} from "./stepArtifactStatus.js";

export const FILE_STATUS_LEVELS = Object.freeze({
  ERROR: "error",
  WARNING: "warning",
  INFO: "info"
});

const FILE_STATUS_LEVEL_RANK = Object.freeze({
  [FILE_STATUS_LEVELS.ERROR]: 3,
  [FILE_STATUS_LEVELS.WARNING]: 2,
  [FILE_STATUS_LEVELS.INFO]: 1
});

const REGENERATE_STEP_ARTIFACTS_RE = /(?:^|\n)\s*Regenerate STEP artifacts[^\n]*(?=\n|$)/gi;

function cleanText(value) {
  return String(value || "")
    .replace(REGENERATE_STEP_ARTIFACTS_RE, "")
    .trim();
}

function detail(label, value, { mono = false } = {}) {
  const text = cleanText(value);
  if (!text) {
    return null;
  }
  return { label, value: text, mono };
}

function displayPath(value, viewerServerInfo = {}, anchorFile = "") {
  const text = cleanText(value);
  return viewerRootRelativePath(text, viewerServerInfo, { anchorFile }) || text;
}

function pathDetail(label, value, viewerServerInfo = {}, anchorFile = "", options = {}) {
  return detail(label, displayPath(value, viewerServerInfo, anchorFile), options);
}

function ownProperty(object, key) {
  return Object.prototype.hasOwnProperty.call(object || {}, key);
}

export function normalizeFileStatusLevel(value, fallback = FILE_STATUS_LEVELS.INFO) {
  const normalized = cleanText(value).toLowerCase();
  if (normalized === FILE_STATUS_LEVELS.ERROR) {
    return FILE_STATUS_LEVELS.ERROR;
  }
  if (normalized === FILE_STATUS_LEVELS.WARNING || normalized === "warn") {
    return FILE_STATUS_LEVELS.WARNING;
  }
  if (normalized === FILE_STATUS_LEVELS.INFO || normalized === "information") {
    return FILE_STATUS_LEVELS.INFO;
  }
  return fallback;
}

export function fileStatusLevelRank(level) {
  return FILE_STATUS_LEVEL_RANK[normalizeFileStatusLevel(level, "")] || 0;
}

export function fileStatusLevelLabel(level) {
  const normalized = normalizeFileStatusLevel(level, "");
  if (normalized === FILE_STATUS_LEVELS.ERROR) {
    return "Error";
  }
  if (normalized === FILE_STATUS_LEVELS.WARNING) {
    return "Warning";
  }
  if (normalized === FILE_STATUS_LEVELS.INFO) {
    return "Info";
  }
  return "";
}

export function normalizeFileStatusItem(item, index = 0) {
  if (!item || typeof item !== "object") {
    return null;
  }
  const level = normalizeFileStatusLevel(item.level, FILE_STATUS_LEVELS.INFO);
  const title = cleanText(item.title) || fileStatusLevelLabel(level) || "Status";
  const message = cleanText(item.message);
  const code = cleanText(item.code);
  const source = cleanText(item.source);
  const details = Array.isArray(item.details)
    ? item.details.map((candidate) => {
        if (!candidate || typeof candidate !== "object") {
          return null;
        }
        return detail(candidate.label, candidate.value, { mono: candidate.mono === true });
      }).filter(Boolean)
    : [];

  return {
    id: cleanText(item.id) || `${source || "status"}:${code || title}:${index}`,
    level,
    source,
    code,
    title,
    message,
    details
  };
}

export function normalizeFileStatusItems(items) {
  if (!Array.isArray(items)) {
    return [];
  }
  const seen = new Set();
  return items.map(normalizeFileStatusItem).filter((item) => {
    if (!item) {
      return false;
    }
    const key = [
      item.level,
      item.title,
      item.message,
      item.details.map((detailItem) => `${detailItem.label}:${detailItem.value}`).join("|")
    ].join("\n");
    if (seen.has(key)) {
      return false;
    }
    seen.add(key);
    return true;
  });
}

export function fileStatusWarningOrErrorItems(items) {
  return normalizeFileStatusItems(items)
    .filter((item) => (
      item.level === FILE_STATUS_LEVELS.ERROR ||
      item.level === FILE_STATUS_LEVELS.WARNING
    ))
    .sort((left, right) => fileStatusLevelRank(right.level) - fileStatusLevelRank(left.level));
}

export function fileStatusHasWarningsOrErrors(items) {
  return fileStatusWarningOrErrorItems(items).length > 0;
}

// INFO-level advisories render below the warnings/errors in the status section —
// quiet chips, never counted as issues and never lighting the sheet's level dot.
export function fileStatusAdvisoryInfoItems(items) {
  return normalizeFileStatusItems(items)
    .filter((item) => item.level === FILE_STATUS_LEVELS.INFO);
}

export function mostIntenseFileStatusLevel(items) {
  return normalizeFileStatusItems(items).reduce((currentLevel, item) => (
    fileStatusLevelRank(item.level) > fileStatusLevelRank(currentLevel)
      ? item.level
      : currentLevel
  ), "");
}

export function mostIntenseFileStatusItem(items) {
  return normalizeFileStatusItems(items).reduce((currentItem, item) => (
    !currentItem || fileStatusLevelRank(item.level) > fileStatusLevelRank(currentItem.level)
      ? item
      : currentItem
  ), null);
}

export function stepArtifactHasRenderableGlb(entry) {
  return entryHasMesh(entry);
}

function artifactStatusTitle(artifact, entry) {
  const code = cleanText(artifact?.error);
  if (code === "missing_glb") {
    return "STEP artifact missing";
  }
  if (stepArtifactHasRenderableGlb(entry)) {
    return "STEP artifact metadata warning";
  }
  return "STEP artifact unavailable";
}

function artifactStatusLevel(artifact, entry) {
  return stepArtifactHasRenderableGlb(entry)
    ? FILE_STATUS_LEVELS.WARNING
    : FILE_STATUS_LEVELS.ERROR;
}

export function stepArtifactStatusMessage(artifact) {
  const code = cleanText(artifact?.error);
  if (code === "missing_glb") {
    return "Generated GLB is missing.";
  }
  if (code === "missing_step_topology") {
    return "Generated GLB is missing STEP topology metadata.";
  }
  if (code === "missing_selector_topology") {
    return "Generated GLB is missing selector topology metadata.";
  }
  if (code === "missing_edge_topology") {
    return "Generated GLB is missing surface edge topology metadata.";
  }
  if (code === "missing_surface_edge_attributes") {
    return "Generated GLB is missing surface edge render attributes.";
  }
  if (code === "unsupported_step_topology") {
    return "Generated GLB topology metadata is unsupported.";
  }
  if (code === "missing_source_path") {
    return "Generated GLB metadata is missing its source path.";
  }
  if (code === "missing_step_hash") {
    return "Generated GLB is missing the hash of the STEP file.";
  }
  return "Generated STEP artifact is unavailable.";
}

function stepSourceStatusTitle(stepStatus) {
  return "STEP file missing";
}

function stepSourceStatusLevel(stepStatus) {
  return FILE_STATUS_LEVELS.WARNING;
}

function stepSourceStatusMessage(stepStatus) {
  if (stepStatus?.missing) {
    return "STEP file is missing from the directory.";
  }
  return cleanText(stepStatus?.message) || "STEP file is missing from the directory.";
}

export function stepFileStatusItems({
  entry = null,
  stepSourceStatus = null,
  stepArtifactGenerationAvailable = true,
  stepArtifactGenerationState = null,
  activeGenerationFiles = [],
  viewerServerInfo = {},
} = {}) {
  const items = [];
  const artifact = ownProperty(stepSourceStatus, "artifact")
    ? stepSourceStatus?.artifact
    : entry?.artifact;
  if (
    artifact?.ok === false &&
    !stepArtifactIssueShouldSuppress({
      entry,
      artifact,
      generationAvailable: stepArtifactGenerationAvailable,
      generationState: stepArtifactGenerationState,
      activeGenerationFiles
    })
  ) {
    items.push({
      id: "step-artifact",
      level: artifactStatusLevel(artifact, entry),
      source: "catalog",
      code: cleanText(artifact.error) || "step_artifact_unavailable",
      title: artifactStatusTitle(artifact, entry),
      message: stepArtifactStatusMessage(artifact),
      details: [
        detail("Code", artifact.error),
        pathDetail("STEP file", artifact.stepPath || artifact.sourcePath || entry?.file, viewerServerInfo, entry?.file),
        pathDetail("CAD path", artifact.cadPath, viewerServerInfo, entry?.file),
        detail("Artifact hash", artifact.artifactHash, { mono: true }),
        detail("Current hash", artifact.currentHash, { mono: true }),
        detail("Raw message", artifact.message)
      ].filter(Boolean)
    });
  }

  const stepStatus = stepSourceStatus?.step;
  if (stepStatus?.missing) {
    items.push({
      id: "step-source",
      level: stepSourceStatusLevel(stepStatus),
      source: "step-source-status",
      code: cleanText(stepStatus.status) || "missing",
      title: stepSourceStatusTitle(stepStatus),
      message: stepSourceStatusMessage(stepStatus),
      details: [
        pathDetail("STEP file", stepSourceStatus?.stepPath || stepSourceStatus?.file, viewerServerInfo, entry?.file)
      ].filter(Boolean)
    });
  }

  return normalizeFileStatusItems(items);
}

export function formatFileStatusItemForAgent(item) {
  const normalized = normalizeFileStatusItem(item);
  if (!normalized) {
    return "";
  }

  const lines = [
    "CAD Viewer issue",
    `Level: ${fileStatusLevelLabel(normalized.level) || normalized.level}`,
    `Title: ${normalized.title}`
  ];
  if (normalized.message) {
    lines.push(`Description: ${normalized.message}`);
  }
  if (normalized.source) {
    lines.push(`Source: ${normalized.source}`);
  }
  if (normalized.code) {
    lines.push(`Code: ${normalized.code}`);
  }
  if (normalized.details.length) {
    lines.push("", "Details:");
    for (const detailItem of normalized.details) {
      lines.push(`- ${detailItem.label}: ${detailItem.value}`);
    }
  }
  return lines.join("\n");
}

export function sdfFileStatusItems(sdfInfo = null) {
  const staticMetadata = sdfInfo?.staticMetadata && typeof sdfInfo.staticMetadata === "object"
    ? sdfInfo.staticMetadata
    : {};
  const warnings = Array.isArray(staticMetadata.warnings) ? staticMetadata.warnings : [];
  return normalizeFileStatusItems(warnings.map((warning, index) => ({
    id: `sdf-warning:${index}`,
    level: FILE_STATUS_LEVELS.WARNING,
    source: "sdf-parser",
    code: "sdf_warning",
    title: "SDF warning",
    message: warning
  })));
}

// The advisory flag a `ready` artifact status may carry (FEEDBACK #17): `busy`
// says another process currently holds the model's generator (INFO — purely
// transient). It never blocks rendering.
export function artifactAdvisoryStatusItems(advisory = null, {
  entry = null,
  viewerServerInfo = {},
} = {}) {
  if (!advisory || typeof advisory !== "object") {
    return [];
  }
  const items = [];
  if (advisory.busy === true) {
    items.push({
      id: "artifact-advisory-busy",
      level: FILE_STATUS_LEVELS.INFO,
      source: "artifact-status",
      code: "generator_busy",
      title: "Generator busy elsewhere",
      message: "Another process is holding this model's generator right now; the current render is unaffected.",
      details: [
        pathDetail("File", entry?.file, viewerServerInfo, entry?.file),
        detail("Run", advisory.runId, { mono: true })
      ].filter(Boolean)
    });
  }
  return normalizeFileStatusItems(items);
}

export function viewerAlertFileStatusItem(viewerAlert = null) {
  if (!viewerAlert || typeof viewerAlert !== "object") {
    return null;
  }
  const level = normalizeFileStatusLevel(viewerAlert.severity, FILE_STATUS_LEVELS.ERROR);
  return normalizeFileStatusItem({
    id: `viewer-alert:${cleanText(viewerAlert.summary) || cleanText(viewerAlert.title) || level}`,
    level,
    source: "viewer",
    code: "viewer_alert",
    title: cleanText(viewerAlert.title) || cleanText(viewerAlert.summary) || "Viewer issue",
    message: cleanText(viewerAlert.message) || cleanText(viewerAlert.summary),
    details: []
  });
}

export function buildFileStatusItems({
  entry = null,
  fileSheetKind = "",
  stepSourceStatus = null,
  stepArtifactGenerationAvailable = true,
  stepArtifactGenerationState = null,
  activeGenerationFiles = [],
  urdfData = null,
  viewerAlert = null,
  viewerServerInfo = null,
  artifactAdvisory = null,
} = {}) {
  if (!entry) {
    return [];
  }

  const kind = cleanText(fileSheetKind).toLowerCase();
  const items = [];
  // Advisory badges apply to every artifact-managed kind, not just STEP.
  items.push(...artifactAdvisoryStatusItems(artifactAdvisory, { entry, viewerServerInfo }));
  if (kind === "step") {
    items.push(...stepFileStatusItems({
      entry,
      stepSourceStatus,
      stepArtifactGenerationAvailable,
      stepArtifactGenerationState,
      activeGenerationFiles,
      viewerServerInfo
    }));
  }
  if (kind === "sdf") {
    items.push(...sdfFileStatusItems(urdfData?.sdf || urdfData));
  }

  const viewerAlertItem = viewerAlertFileStatusItem(viewerAlert);
  const duplicatesExistingItem = viewerAlertItem && normalizeFileStatusItems(items).some((item) => (
    item.level === viewerAlertItem.level &&
    item.title === viewerAlertItem.title &&
    item.message === viewerAlertItem.message
  ));
  if (viewerAlertItem && !duplicatesExistingItem) {
    items.push(viewerAlertItem);
  }

  return normalizeFileStatusItems(items);
}
