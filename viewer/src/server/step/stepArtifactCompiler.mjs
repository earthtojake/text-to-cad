import fs from "node:fs";
import path from "node:path";

import {
  inlineStepGlbArtifactPathForSource,
} from "cadjs/common/stepSidecars.mjs";
import {
  VIEWER_SKIPPED_DIRECTORIES,
  normalizeViewerRootDir,
  repoRelativePath,
  resolveViewerRoot,
  validateStepTopologyArtifact,
} from "../catalog/cadDirectoryScanner.mjs";
import { ensurePythonStepTopologyArtifact } from "./pythonStepArtifact.mjs";

const STEP_SUFFIXES = new Set([".step", ".stp"]);

function isHiddenDirectoryName(name) {
  return String(name || "").startsWith(".");
}

function isPerStepViewerDirectoryName(name) {
  const normalized = String(name || "").toLowerCase();
  return normalized.startsWith(".") && (normalized.endsWith(".step") || normalized.endsWith(".stp"));
}

function isPerUrdfViewerDirectoryName(name) {
  const normalized = String(name || "").toLowerCase();
  return normalized.startsWith(".") && normalized.endsWith(".urdf");
}

function shouldSkipDirectory(name) {
  return (
    VIEWER_SKIPPED_DIRECTORIES.has(name) ||
    isHiddenDirectoryName(name) ||
    isPerStepViewerDirectoryName(name) ||
    isPerUrdfViewerDirectoryName(name)
  );
}

function sameStemPythonGeneratorPath(stepPath) {
  const extension = path.extname(stepPath).toLowerCase();
  if (!STEP_SUFFIXES.has(extension)) {
    return "";
  }
  const candidatePath = path.join(
    path.dirname(stepPath),
    `${path.basename(stepPath, extension)}.py`,
  );
  try {
    return /\bgen_step\s*\(/.test(fs.readFileSync(candidatePath, "utf-8"))
      ? candidatePath
      : "";
  } catch {
    return "";
  }
}

function collectStepFiles(rootPath, result = []) {
  let entries = [];
  try {
    entries = fs.readdirSync(rootPath, { withFileTypes: true });
  } catch {
    return result;
  }
  for (const entry of entries) {
    const entryPath = path.join(rootPath, entry.name);
    if (entry.isDirectory()) {
      if (!shouldSkipDirectory(entry.name)) {
        collectStepFiles(entryPath, result);
      }
      continue;
    }
    if (entry.isFile()) {
      const extension = path.extname(entry.name).toLowerCase();
      if (STEP_SUFFIXES.has(extension)) {
        result.push(entryPath);
      } else if (extension === ".py" && /\bgen_step\s*\(/.test(fs.readFileSync(entryPath, "utf-8"))) {
        const logicalStepPath = path.join(path.dirname(entryPath), `${path.basename(entryPath, extension)}.step`);
        if (!fs.existsSync(logicalStepPath)) {
          result.push(logicalStepPath);
        }
      }
    }
  }
  return result;
}

function cadPathForStepSource(repoRoot, sourcePath) {
  const relativePath = repoRelativePath(repoRoot, sourcePath);
  return relativePath.slice(0, -path.extname(relativePath).length);
}

function canBuildStepArtifact(artifact) {
  const code = String(artifact?.stepArtifact?.error?.code || "");
  return !artifact?.stepArtifact?.ok && [
    "missing_glb",
    "missing_step_topology",
    "missing_edge_topology",
    "missing_surface_edge_attributes",
    "missing_selector_topology",
    "missing_source_path",
    "missing_step_hash",
    "stale_step_artifact",
    "unsupported_step_topology",
  ].includes(code);
}

export async function compileStepTopologyArtifact({
  repoRoot,
  stepPath,
  sourcePath = "",
  targetPath = inlineStepGlbArtifactPathForSource(stepPath),
  force = true,
  skipStepWrite = false,
  writeStepAfterArtifact = false,
  meshTolerance = null,
  meshAngularTolerance = null,
} = {}) {
  if (!repoRoot) {
    throw new Error("repoRoot is required");
  }
  if (!stepPath) {
    throw new Error("stepPath is required");
  }
  const resolvedRepoRoot = path.resolve(repoRoot);
  const resolvedStepPath = path.resolve(stepPath);
  const resolvedSourcePath = sourcePath ? path.resolve(sourcePath) : "";
  const resolvedTargetPath = path.resolve(targetPath);
  const pythonResult = await ensurePythonStepTopologyArtifact({
    repoRoot: resolvedRepoRoot,
    stepPath: resolvedStepPath,
    sourcePath: resolvedSourcePath,
    force,
    skipStepWrite,
    writeStepAfterArtifact,
    resolveOnFirstResult: writeStepAfterArtifact,
    meshTolerance,
    meshAngularTolerance,
  });
  if (!pythonResult?.ok) {
    throw new Error(pythonResult?.error || `Failed to generate STEP topology artifact: ${resolvedStepPath}`);
  }
  const pythonGlbPath = path.resolve(pythonResult.glbPath || inlineStepGlbArtifactPathForSource(resolvedStepPath));
  if (pythonGlbPath !== resolvedTargetPath) {
    fs.mkdirSync(path.dirname(resolvedTargetPath), { recursive: true });
    fs.copyFileSync(pythonGlbPath, resolvedTargetPath);
  }
  return {
    ...pythonResult,
    ok: true,
    stepPath: resolvedStepPath,
    glbPath: resolvedTargetPath,
  };
}

export async function ensureStepTopologyArtifact({
  repoRoot,
  stepPath,
  sourcePath = "",
  force = false,
  skipStepWrite = false,
  writeStepAfterArtifact = false,
  meshTolerance = null,
  meshAngularTolerance = null,
} = {}) {
  const resolvedRepoRoot = path.resolve(repoRoot);
  const resolvedStepPath = path.resolve(stepPath);
  const resolvedSourcePath = sourcePath ? path.resolve(sourcePath) : "";
  const cadPath = cadPathForStepSource(resolvedRepoRoot, resolvedStepPath);
  const current = validateStepTopologyArtifact({
    repoRoot: resolvedRepoRoot,
    sourcePath: resolvedStepPath,
    cadPath,
  });
  const currentArtifactError = current.stepArtifact?.error && typeof current.stepArtifact.error === "object"
    ? current.stepArtifact.error
    : {};
  const currentSourceKind = String(
    current.stepArtifact?.sourceKind ||
    currentArtifactError.sourceKind ||
    "",
  ).trim().toLowerCase();
  const currentSourcePath = String(
    current.stepArtifact?.sourcePath ||
    currentArtifactError.sourcePath ||
    "",
  ).trim();
  const stepFileExists = fs.existsSync(resolvedStepPath);
  const shouldInferPythonSource = Boolean(
    resolvedSourcePath ||
    skipStepWrite ||
    writeStepAfterArtifact ||
    !stepFileExists
  );
  const inferredSourcePath = shouldInferPythonSource
    ? resolvedSourcePath || (
        currentSourceKind === "python" && currentSourcePath
          ? path.resolve(resolvedRepoRoot, currentSourcePath)
          : ""
      ) || sameStemPythonGeneratorPath(resolvedStepPath)
    : "";
  const resolvedSkipStepWrite = Boolean(
    skipStepWrite ||
    inferredSourcePath
  );
  const hasMeshOverride = meshTolerance !== null && meshTolerance !== undefined
    || meshAngularTolerance !== null && meshAngularTolerance !== undefined;
  if (
    !force &&
    !hasMeshOverride &&
    (
      current.stepArtifact?.ok ||
      (!current.stepArtifact?.ok && !canBuildStepArtifact(current))
    )
  ) {
    return {
      ok: Boolean(current.stepArtifact?.ok),
      skipped: true,
      reason: current.stepArtifact?.error?.code || "",
      stepPath: resolvedStepPath,
      glbPath: current.glbPath,
      validation: current.stepArtifact,
    };
  }
  const targetPath = inlineStepGlbArtifactPathForSource(resolvedStepPath);
  const result = await compileStepTopologyArtifact({
    repoRoot: resolvedRepoRoot,
    stepPath: resolvedStepPath,
    sourcePath: inferredSourcePath || undefined,
    targetPath,
    force,
    skipStepWrite: resolvedSkipStepWrite,
    writeStepAfterArtifact: Boolean(writeStepAfterArtifact && resolvedSkipStepWrite),
    meshTolerance,
    meshAngularTolerance,
  });
  const next = validateStepTopologyArtifact({
    repoRoot: resolvedRepoRoot,
    sourcePath: resolvedStepPath,
    cadPath,
  });
  return {
    ...result,
    ok: Boolean(next.stepArtifact?.ok),
    validation: next.stepArtifact,
  };
}

export async function ensureStepArtifactsForCatalog({
  repoRoot,
  rootDir = "",
  force = false,
  meshTolerance = null,
  meshAngularTolerance = null,
} = {}) {
  const resolvedRepoRoot = path.resolve(repoRoot);
  const resolvedRootDir = normalizeViewerRootDir(rootDir);
  const { rootPath } = resolveViewerRoot(resolvedRepoRoot, resolvedRootDir);
  const results = [];
  for (const stepPath of collectStepFiles(rootPath)) {
    const stepFileExists = fs.existsSync(stepPath);
    try {
      results.push(await ensureStepTopologyArtifact({
        repoRoot: resolvedRepoRoot,
        stepPath,
        force,
        skipStepWrite: !stepFileExists && Boolean(sameStemPythonGeneratorPath(stepPath)),
        meshTolerance,
        meshAngularTolerance,
      }));
    } catch (error) {
      results.push({
        ok: false,
        stepPath,
        error: error instanceof Error ? error.message : String(error),
      });
    }
  }
  return results;
}
