import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import {
  inlineStepGlbArtifactPathForSource,
  isInlineStepGlbArtifactPath,
  isInlineStepParameterPath,
  isPathInsidePerStepViewerDirectory,
  isPerStepViewerDirectoryName,
  stepParameterPathForStepSource,
} from "cadjs/common/stepSidecars.mjs";
import {
  STEP_EDGE_BARYCENTRIC_ATTRIBUTE,
  STEP_EDGE_CLASS_ATTRIBUTE,
  STEP_EDGE_VISIBILITY_CLASSES,
  STEP_TOPOLOGY_EXTENSION,
  STEP_TOPOLOGY_SCHEMA_VERSION,
  isCurrentStepTopologySchemaVersion
} from "cadjs/common/stepTopology.mjs";
import { toPosixPath } from "cadjs/lib/pathUtils.mjs";
import { readTextToCadStepMetadataFile } from "../step/stepMetadata.mjs";

export const DEFAULT_VIEWER_ROOT_DIR = "";
export const CAD_CATALOG_SCHEMA_VERSION = 4;

const SOURCE_EXTENSIONS = new Set([".step", ".stp", ".stl", ".3mf", ".glb", ".gcode", ".dxf", ".urdf", ".srdf", ".sdf"]);
const IMPLICIT_CAD_EXTENSIONS = Object.freeze([".implicit.js", ".implicit.mjs"]);
const REGENERATE_STEP_COMMAND = "python -m cadpy.step_artifact --repo-root . --step";
export const VIEWER_SKIPPED_DIRECTORIES = new Set([
  ".agents",
  ".cache",
  ".viewer",
  ".git",
  ".venv",
  "__pycache__",
  "build",
  "coverage",
  "dist",
  "node_modules",
  "viewer",
]);
const SRDF_URDF_METADATA_PATTERN = /<\s*(?:tcad|explorer):urdf\b[^>]*\bpath\s*=\s*["']([^"']+)["'][^>]*>/i;
const STEP_EDGE_RENDER_CLASS_ORDER = Object.freeze(["feature", "tangent", "seam", "degenerate"]);
const TEXT_TO_CAD_COMMENT_METADATA_RE = /<!--\s*cadpy:([A-Za-z][A-Za-z0-9]*)=([\s\S]*?)-->/g;
const PYTHON_GENERATOR_BY_KIND = Object.freeze({
  dxf: "gen_dxf",
  step: "gen_step",
  stp: "gen_step",
  urdf: "gen_urdf",
  srdf: "gen_srdf",
  sdf: "gen_sdf",
});

function encodeUrlPath(repoRelativePath) {
  return `/${repoRelativePath.split("/").map((part) => encodeURIComponent(part)).join("/")}`;
}

function pathIsImplicitCadSource(value = "") {
  const pathname = String(value || "").split(/[?#]/, 1)[0].toLowerCase();
  return IMPLICIT_CAD_EXTENSIONS.some((extension) => pathname.endsWith(extension));
}

function relativePathStaysInsideRoot(relativePath) {
  return relativePath === "" || (
    relativePath !== ".." &&
    !relativePath.startsWith(`..${path.sep}`) &&
    !path.isAbsolute(relativePath)
  );
}

function normalizeStepEdgeRenderVisibilityClasses(value) {
  const rawValues = Array.isArray(value) ? value : value === undefined || value === null ? [] : [value];
  const validValues = new Set(Object.values(STEP_EDGE_VISIBILITY_CLASSES));
  const normalized = [];
  for (const raw of rawValues) {
    const classId = String(raw || "").trim();
    if (validValues.has(classId) && !normalized.includes(classId)) {
      normalized.push(classId);
    }
  }
  if (!normalized.includes(STEP_EDGE_VISIBILITY_CLASSES.FEATURE)) {
    normalized.unshift(STEP_EDGE_VISIBILITY_CLASSES.FEATURE);
  }
  return [
    ...STEP_EDGE_RENDER_CLASS_ORDER.filter((classId) => normalized.includes(classId)),
    ...normalized.filter((classId) => !STEP_EDGE_RENDER_CLASS_ORDER.includes(classId))
  ];
}

export function normalizeViewerRootDir(value = DEFAULT_VIEWER_ROOT_DIR) {
  const rawValue = String(value ?? "").trim();
  const slashNormalized = rawValue.replace(/\\/g, "/");
  const normalized = path.posix.normalize(slashNormalized);
  if (!normalized || normalized === ".") {
    return DEFAULT_VIEWER_ROOT_DIR;
  }
  if (normalized === ".." || normalized.startsWith("../")) {
    throw new Error(`CAD Viewer root directory must stay inside the directory root: ${rawValue}`);
  }
  return normalized.replace(/(?!^\/)\/+$/, "");
}

export function resolveViewerRoot(repoRoot, rootDir = DEFAULT_VIEWER_ROOT_DIR) {
  const normalizedDir = normalizeViewerRootDir(rootDir);
  const resolvedRepoRoot = path.resolve(repoRoot);
  const rootPath = normalizedDir
    ? path.resolve(resolvedRepoRoot, normalizedDir)
    : resolvedRepoRoot;
  const relativePath = path.relative(resolvedRepoRoot, rootPath);
  if (!relativePathStaysInsideRoot(relativePath)) {
    throw new Error(`CAD Viewer root directory must stay inside the directory root: ${normalizedDir}`);
  }
  return {
    dir: normalizedDir,
    rootPath,
    rootName: normalizedDir ? path.basename(rootPath) : path.basename(resolvedRepoRoot),
  };
}

export function repoRelativePath(repoRoot, filePath) {
  return toPosixPath(path.relative(path.resolve(repoRoot), path.resolve(filePath)));
}

function scanRelativePath(rootPath, filePath) {
  return toPosixPath(path.relative(path.resolve(rootPath), path.resolve(filePath)));
}

function fileStats(filePath) {
  try {
    const stats = fs.statSync(filePath, { bigint: true });
    return stats.isFile() ? stats : null;
  } catch {
    return null;
  }
}

function fileVersion(filePath) {
  const stats = fileStats(filePath);
  if (!stats) {
    return "";
  }
  return `${stats.size.toString(36)}-${stats.mtimeNs.toString(36)}`;
}

function sha256File(filePath) {
  const hash = crypto.createHash("sha256");
  const fd = fs.openSync(filePath, "r");
  try {
    const buffer = Buffer.alloc(1024 * 1024);
    let bytesRead = 0;
    do {
      bytesRead = fs.readSync(fd, buffer, 0, buffer.length, null);
      if (bytesRead > 0) {
        hash.update(buffer.subarray(0, bytesRead));
      }
    } while (bytesRead > 0);
  } finally {
    fs.closeSync(fd);
  }
  return hash.digest("hex");
}

function pathIsInside(filePath, rootPath) {
  const relative = path.relative(path.resolve(rootPath), path.resolve(filePath));
  return relativePathStaysInsideRoot(relative);
}

function dedupePaths(paths) {
  const result = [];
  const seen = new Set();
  for (const rawPath of paths) {
    const resolved = path.resolve(rawPath);
    if (!seen.has(resolved)) {
      seen.add(resolved);
      result.push(resolved);
    }
  }
  return result;
}

function normalizeManifestPath(manifestPath) {
  const value = String(manifestPath || "").trim();
  if (!value || value.includes("\0")) {
    return "";
  }
  return value.replace(/\\/g, "/");
}

function resolveManifestSourcePath(repoRoot, manifestPath, baseDir = repoRoot) {
  const value = normalizeManifestPath(manifestPath);
  if (!value) {
    return null;
  }
  const resolved = path.isAbsolute(value)
    ? path.resolve(value)
    : path.resolve(baseDir, value);
  if (!pathIsInside(resolved, repoRoot)) {
    return null;
  }
  return resolved;
}

function normalizeManifestRelativePath(manifestPath) {
  const value = String(manifestPath || "").trim().replace(/\\/g, "/").replace(/^\/+/, "");
  if (!value || value === "." || value.startsWith("../")) {
    return "";
  }
  return value;
}

function manifestIdentityRootForStep(repoRoot, actualStepPath, manifestStepPath) {
  const resolvedRepoRoot = path.resolve(repoRoot);
  const normalizedStepPath = normalizeManifestRelativePath(manifestStepPath);
  if (!normalizedStepPath || !actualStepPath) {
    return resolvedRepoRoot;
  }
  const actualRepoPath = repoRelativePath(resolvedRepoRoot, actualStepPath);
  if (actualRepoPath === normalizedStepPath) {
    return resolvedRepoRoot;
  }
  if (!actualRepoPath.endsWith(`/${normalizedStepPath}`)) {
    return resolvedRepoRoot;
  }
  const prefix = actualRepoPath.slice(0, actualRepoPath.length - normalizedStepPath.length).replace(/\/+$/, "");
  if (!prefix) {
    return resolvedRepoRoot;
  }
  const resolvedPrefix = path.resolve(resolvedRepoRoot, ...prefix.split("/").filter(Boolean));
  return pathIsInside(resolvedPrefix, resolvedRepoRoot) ? resolvedPrefix : resolvedRepoRoot;
}

function sourcePathFromManifest(repoRoot, manifestPath, { identityRoot = null, baseDir = null } = {}) {
  const value = normalizeManifestPath(manifestPath);
  if (!value) {
    return { sourcePath: "", manifestSourcePath: "", filePath: null, identityRoot: path.resolve(repoRoot) };
  }
  const resolvedRepoRoot = path.resolve(repoRoot);
  const resolvedIdentityRoot = identityRoot && pathIsInside(identityRoot, resolvedRepoRoot)
    ? path.resolve(identityRoot)
    : resolvedRepoRoot;
  const roots = dedupePaths([
    baseDir ? path.resolve(baseDir) : null,
    resolvedIdentityRoot,
    resolvedRepoRoot,
  ].filter(Boolean));
  const candidates = [];
  for (const root of roots) {
    if (!pathIsInside(root, resolvedRepoRoot)) {
      continue;
    }
    const filePath = resolveManifestSourcePath(resolvedRepoRoot, value, root);
    if (!filePath) {
      continue;
    }
    candidates.push({
      sourcePath: repoRelativePath(resolvedRepoRoot, filePath),
      manifestSourcePath: value,
      filePath,
      identityRoot: resolvedIdentityRoot,
    });
  }
  const candidate = candidates.find((entry) => fileStats(entry.filePath)) || candidates[0];
  if (candidate) {
    return candidate;
  }
  const filePath = resolveManifestSourcePath(resolvedRepoRoot, value, resolvedRepoRoot);
  return {
    sourcePath: value,
    manifestSourcePath: value,
    filePath,
    identityRoot: resolvedIdentityRoot,
  };
}

function fileHasGenStep(filePath) {
  try {
    return /\bgen_step\s*\(/.test(fs.readFileSync(filePath, "utf-8"));
  } catch {
    return false;
  }
}

function generatorSourcePathFromManifest(repoRoot, manifestPath, { identityRoot = null, baseDir = null } = {}) {
  const candidate = sourcePathFromManifest(repoRoot, manifestPath, { identityRoot, baseDir });
  if (
    candidate.sourcePath &&
    candidate.filePath &&
    path.extname(candidate.filePath).toLowerCase() === ".py" &&
    path.basename(candidate.filePath) !== "__init__.py" &&
    fileHasGenStep(candidate.filePath)
  ) {
    return candidate;
  }
  return {
    sourcePath: "",
    manifestSourcePath: candidate.manifestSourcePath || "",
    filePath: null,
    identityRoot: candidate.identityRoot || path.resolve(repoRoot),
  };
}

function fileHasPythonGenerator(filePath, generatorName) {
  if (!generatorName) {
    return false;
  }
  try {
    const source = fs.readFileSync(filePath, "utf-8");
    return new RegExp(`\\b${generatorName}\\s*\\(`).test(source);
  } catch {
    return false;
  }
}

function generatorSourcePathFromMetadata(repoRoot, manifestPath, generatorName, { baseDir = null } = {}) {
  const candidate = sourcePathFromManifest(repoRoot, manifestPath, { baseDir });
  if (
    candidate.sourcePath &&
    candidate.filePath &&
    path.extname(candidate.filePath).toLowerCase() === ".py" &&
    path.basename(candidate.filePath) !== "__init__.py" &&
    fileHasPythonGenerator(candidate.filePath, generatorName)
  ) {
    return candidate;
  }
  return { sourcePath: "", filePath: null };
}

function readXmlTextToCadMetadata(filePath) {
  let text = "";
  try {
    text = fs.readFileSync(filePath, "utf-8");
  } catch {
    return {};
  }
  const metadata = {};
  for (const match of text.matchAll(TEXT_TO_CAD_COMMENT_METADATA_RE)) {
    metadata[String(match[1] || "").trim()] = String(match[2] || "").trim();
  }
  return metadata;
}

function readDxfTextToCadMetadata(filePath) {
  let lines = [];
  try {
    lines = fs.readFileSync(filePath, "utf-8").split(/\r?\n/);
  } catch {
    return {};
  }
  const metadata = {};
  for (let index = 0; index + 1 < lines.length; index += 1) {
    if (String(lines[index] || "").trim() !== "999") {
      continue;
    }
    const value = String(lines[index + 1] || "").trim();
    if (!value.startsWith("cadpy:")) {
      continue;
    }
    const [key, ...rest] = value.slice("cadpy:".length).split("=");
    const normalizedKey = String(key || "").trim();
    if (rest.length && /^[A-Za-z][A-Za-z0-9]*$/.test(normalizedKey)) {
      metadata[normalizedKey] = rest.join("=").trim();
    }
  }
  return metadata;
}

function readGeneratedFileMetadata(filePath, kind) {
  const normalizedKind = String(kind || "").trim().toLowerCase();
  if (normalizedKind === "dxf") {
    return readDxfTextToCadMetadata(filePath);
  }
  if (["urdf", "srdf", "sdf"].includes(normalizedKind)) {
    return readXmlTextToCadMetadata(filePath);
  }
  if (normalizedKind === "step" || normalizedKind === "stp") {
    try {
      return readTextToCadStepMetadataFile(filePath);
    } catch {
      return {};
    }
  }
  return {};
}

function generatedSourceStatusForFile({ repoRoot, sourcePath, kind }) {
  const normalizedKind = String(kind || "").trim().toLowerCase();
  const generatorName = PYTHON_GENERATOR_BY_KIND[normalizedKind] || "";
  if (!generatorName) {
    return null;
  }
  const metadata = readGeneratedFileMetadata(sourcePath, normalizedKind);
  const metadataSourcePath = String(metadata.sourcePath || "").trim();
  if (!metadataSourcePath) {
    return null;
  }
  const sourceIdentity = generatorSourcePathFromMetadata(
    repoRoot,
    metadataSourcePath,
    generatorName,
    { baseDir: path.dirname(sourcePath) },
  );
  const base = {
    sourceKind: "python",
    source: {
      file: sourceIdentity.sourcePath || metadataSourcePath,
      sourcePath: sourceIdentity.sourcePath || metadataSourcePath,
      ...(metadata.sourceHash ? { sourceHash: String(metadata.sourceHash) } : {}),
    },
  };
  if (!sourceIdentity.filePath) {
    return {
      ...base,
      sourceStatus: {
        ok: false,
        status: "missing",
        stale: false,
        sourceKind: "python",
        sourcePath: metadataSourcePath,
        message: "Python generator source is unavailable.",
      },
    };
  }
  return {
    ...base,
    source: {
      ...base.source,
      file: sourceIdentity.sourcePath,
      sourcePath: sourceIdentity.sourcePath,
      sourceHash: String(metadata.sourceHash || ""),
    },
  };
}

function assetForPath(repoRoot, filePath) {
  const stats = fileStats(filePath);
  if (!stats) {
    return null;
  }
  const version = `${stats.size.toString(36)}-${stats.mtimeNs.toString(36)}`;
  const repoPath = repoRelativePath(repoRoot, filePath);
  return {
    url: `${encodeUrlPath(repoPath)}?v=${encodeURIComponent(version)}`,
    hash: sha256File(filePath),
    bytes: Number(stats.size),
  };
}

function assetUrlForPath(repoRoot, filePath) {
  return encodeUrlPath(repoRelativePath(repoRoot, filePath));
}

function readExact(fd, length, position) {
  const buffer = Buffer.alloc(length);
  const bytesRead = fs.readSync(fd, buffer, 0, length, position);
  return bytesRead === length ? buffer : null;
}

function glbBufferViewRange(gltf, binOffset, binLength, viewIndex) {
  const view = Array.isArray(gltf?.bufferViews) ? gltf.bufferViews[Number(viewIndex)] : null;
  if (!view || Number(view.buffer || 0) !== 0) {
    return null;
  }
  const byteOffset = binOffset + Number(view.byteOffset || 0);
  const byteLength = Number(view.byteLength || 0);
  if (!Number.isFinite(byteOffset) || !Number.isFinite(byteLength) || byteLength < 0) {
    return null;
  }
  if (byteOffset < binOffset || byteOffset + byteLength > binOffset + binLength) {
    return null;
  }
  return { byteOffset, byteLength };
}

function parseJsonBufferView(fd, gltf, binOffset, binLength, viewIndex, encoding = "utf-8") {
  const range = glbBufferViewRange(gltf, binOffset, binLength, viewIndex);
  if (!range) {
    throw new Error("STEP topology buffer view range is invalid");
  }
  const bytes = readExact(fd, range.byteLength, range.byteOffset);
  if (!bytes) {
    throw new Error("STEP topology buffer view range is invalid");
  }
  const payload = JSON.parse(bytes.toString(String(encoding || "utf-8")));
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    throw new Error("STEP topology JSON buffer view is not an object");
  }
  return payload;
}

function gltfPrimitivesHaveSurfaceEdgeAttributes(gltf) {
  const meshes = Array.isArray(gltf?.meshes) ? gltf.meshes : [];
  let primitiveCount = 0;
  for (const mesh of meshes) {
    for (const primitive of Array.isArray(mesh?.primitives) ? mesh.primitives : []) {
      primitiveCount += 1;
      const attributes = primitive?.attributes || {};
      if (
        attributes[STEP_EDGE_BARYCENTRIC_ATTRIBUTE] === undefined ||
        attributes[STEP_EDGE_CLASS_ATTRIBUTE] === undefined
      ) {
        return false;
      }
    }
  }
  return primitiveCount > 0;
}

function readGlbTopologyContainer(filePath) {
  let fd = null;
  try {
    fd = fs.openSync(filePath, "r");
    const header = readExact(fd, 12, 0);
    if (!header || header.readUInt32LE(0) !== 0x46546c67 || header.readUInt32LE(4) !== 2) {
      throw new Error("Not a GLB v2 file");
    }
    const totalLength = Math.min(header.readUInt32LE(8), fs.fstatSync(fd).size);
    let offset = 12;
    let gltf = null;
    let binOffset = 0;
    let binLength = 0;
    while (offset + 8 <= totalLength) {
      const chunkHeader = readExact(fd, 8, offset);
      if (!chunkHeader) {
        throw new Error("Invalid GLB chunk header");
      }
      const chunkLength = chunkHeader.readUInt32LE(0);
      const chunkType = chunkHeader.toString("latin1", 4, 8);
      offset += 8;
      if (offset + chunkLength > totalLength) {
        throw new Error("Invalid GLB chunk length");
      }
      if (chunkType === "JSON") {
        const jsonBytes = readExact(fd, chunkLength, offset);
        if (!jsonBytes) {
          throw new Error("GLB is missing JSON chunk");
        }
        gltf = JSON.parse(jsonBytes.toString("utf8").trim());
      } else if (chunkType === "BIN\u0000") {
        binOffset = offset;
        binLength = chunkLength;
      }
      offset += chunkLength;
    }
    return {
      fd,
      gltf,
      binOffset,
      binLength,
    };
  } catch {
    if (fd !== null) {
      fs.closeSync(fd);
    }
    throw new Error("Invalid GLB topology container");
  }
}

function stepArtifactError({ code, reason, repoRoot, cadPath, sourcePath, glbPath, details = {} }) {
  const glbRelPath = repoRelativePath(repoRoot, glbPath);
  return {
    ok: false,
    error: {
      code,
      message: `${reason}: ${glbRelPath}.`,
      cadPath,
      stepPath: repoRelativePath(repoRoot, sourcePath),
      glbPath: glbRelPath,
      regenerateCommand: REGENERATE_STEP_COMMAND,
      ...details,
    },
  };
}

function staleStepArtifactError({
  repoRoot,
  cadPath,
  sourcePath,
  glbPath,
  manifestSourcePath = "",
  sourceKind = "step",
  artifactHash,
  currentHash,
}) {
  return stepArtifactError({
    code: "stale_step_artifact",
    reason: "Generated GLB doesn't match the hash of the STEP file",
    repoRoot,
    cadPath,
    sourcePath,
    glbPath,
    details: {
      stale: true,
      sourceKind,
      ...(manifestSourcePath ? { sourcePath: manifestSourcePath } : {}),
      artifactHash,
      currentHash,
    },
  });
}

export function validateStepTopologyArtifact({ repoRoot, sourcePath, cadPath }) {
  const glbPath = inlineStepGlbArtifactPathForSource(sourcePath);
  let stepHash = "";
  let sourceHash = "";
  let artifactSourcePath = "";
  const fail = (code, reason) => ({
    topology: null,
    stepArtifact: stepArtifactError({ code, reason, repoRoot, cadPath, sourcePath, glbPath }),
    glbPath,
    stepHash,
    sourceHash,
  });

  if (!fileStats(glbPath)) {
    return fail(
      "missing_glb",
      "STEP topology validation requires the generated GLB artifact, but it is missing"
    );
  }

  let container = null;
  try {
    container = readGlbTopologyContainer(glbPath);
    const extension = container.gltf?.extensions?.[STEP_TOPOLOGY_EXTENSION];
    if (!extension || typeof extension !== "object" || Array.isArray(extension)) {
      return fail(
        "missing_step_topology",
        "STEP topology validation requires readable STEP_topology indexView in the GLB"
      );
    }
    if (!isCurrentStepTopologySchemaVersion(extension.schemaVersion)) {
      return fail(
        "unsupported_step_topology",
        `STEP topology validation requires STEP_topology schemaVersion ${STEP_TOPOLOGY_SCHEMA_VERSION} in the GLB`
      );
    }
    const manifest = parseJsonBufferView(
      container.fd,
      container.gltf,
      container.binOffset,
      container.binLength,
      extension.indexView,
      extension.encoding
    );
    const topology = {
      index: manifest,
      entryKind: String(extension.entryKind || manifest.entryKind || "").trim().toLowerCase(),
      hasSelector: false,
      hasDisplayEdges: false,
    };
    if (!isCurrentStepTopologySchemaVersion(manifest.schemaVersion)) {
      return {
        topology,
        stepArtifact: stepArtifactError({
          code: "unsupported_step_topology",
          reason: `STEP topology validation requires STEP_topology schemaVersion ${STEP_TOPOLOGY_SCHEMA_VERSION} in the GLB`,
          repoRoot,
          cadPath,
          sourcePath,
          glbPath,
        }),
        glbPath,
        stepHash,
      };
    }
    const artifactSourceKind = String(manifest.sourceKind || "step").trim().toLowerCase();
    const artifactUsesPythonSource = artifactSourceKind === "python";
    const artifactNormalizedSourceKind = artifactUsesPythonSource ? "python" : "step";
    const artifactIdentityDetails = () => ({
      sourceKind: artifactNormalizedSourceKind,
      ...(artifactSourcePath ? { sourcePath: artifactSourcePath } : {}),
    });
    const manifestIdentityRoot = manifestIdentityRootForStep(repoRoot, sourcePath, manifest.stepPath);
    const sourceIdentity = artifactUsesPythonSource
      ? generatorSourcePathFromManifest(repoRoot, manifest.sourcePath, {
          identityRoot: manifestIdentityRoot,
          baseDir: path.dirname(glbPath),
        })
      : sourcePathFromManifest(repoRoot, manifest.sourcePath, {
          identityRoot: manifestIdentityRoot,
          baseDir: path.dirname(glbPath),
        });
    artifactSourcePath = sourceIdentity.sourcePath;
    if (!artifactSourcePath || !sourceIdentity.filePath) {
      return {
        topology,
        stepArtifact: stepArtifactError({
          code: "missing_source_path",
          reason: "GLB STEP_topology is missing required sourcePath identity",
          repoRoot,
          cadPath,
          sourcePath,
          glbPath,
          details: {
            sourceKind: artifactNormalizedSourceKind,
          },
        }),
        glbPath,
        stepHash,
        sourceHash,
      };
    }
    stepHash = String(manifest.stepHash || "").trim();
    sourceHash = String(manifest.sourceHash || "").trim();
    if (!stepHash && fileStats(sourcePath)) {
      return {
        topology,
        stepArtifact: stepArtifactError({
          code: "missing_step_hash",
          reason: "GLB STEP_topology is missing STEP file identity",
          repoRoot,
          cadPath,
          sourcePath,
          glbPath,
          details: artifactIdentityDetails(),
        }),
        glbPath,
        stepHash,
        sourceHash,
      };
    }
    const currentStepHash = fileStats(sourcePath) ? sha256File(sourcePath) : "";
    if (currentStepHash && stepHash !== currentStepHash) {
      return {
        topology,
        stepArtifact: staleStepArtifactError({
          repoRoot,
          cadPath,
          sourcePath,
          glbPath,
          manifestSourcePath: artifactSourcePath,
          sourceKind: artifactNormalizedSourceKind,
          artifactHash: stepHash,
          currentHash: currentStepHash,
        }),
        glbPath,
        stepHash,
        sourceHash,
      };
    }
    let edgeRendering = null;
    try {
      const edgeManifest = parseJsonBufferView(
        container.fd,
        container.gltf,
        container.binOffset,
        container.binLength,
        extension.edgeView,
        extension.encoding
      );
      const edgeVisibilityClasses = edgeManifest?.edgeRendering && typeof edgeManifest.edgeRendering === "object"
        ? normalizeStepEdgeRenderVisibilityClasses(edgeManifest.edgeRendering.visibilityClasses)
        : [];
      const indexEdgeVisibilityClasses = manifest?.edgeRendering && typeof manifest.edgeRendering === "object"
        ? normalizeStepEdgeRenderVisibilityClasses(manifest.edgeRendering.visibilityClasses)
        : [];
      if (
        !isCurrentStepTopologySchemaVersion(edgeManifest.schemaVersion) ||
        String(edgeManifest.profile || "") !== "surface-edges" ||
        String(edgeManifest.sourcePath || "").trim() !== String(manifest.sourcePath || "").trim() ||
        (stepHash && String(edgeManifest.stepHash || "").trim() !== stepHash) ||
        !edgeVisibilityClasses.length ||
        edgeVisibilityClasses.join("\n") !== indexEdgeVisibilityClasses.join("\n") ||
        !edgeVisibilityClasses.includes(STEP_EDGE_VISIBILITY_CLASSES.FEATURE) ||
        !edgeManifest?.buffers?.views?.surfaceHalfEdges
      ) {
        return {
          topology,
          stepArtifact: stepArtifactError({
            code: "missing_edge_topology",
          reason: `STEP topology validation requires STEP_topology edgeView schemaVersion ${STEP_TOPOLOGY_SCHEMA_VERSION} in the GLB`,
          repoRoot,
          cadPath,
          sourcePath,
          glbPath,
          details: artifactIdentityDetails(),
        }),
        glbPath,
        stepHash,
        sourceHash,
        };
      }
      edgeRendering = edgeManifest.edgeRendering && typeof edgeManifest.edgeRendering === "object"
        ? {
            visibilityClasses: edgeVisibilityClasses,
            generatedVisibilityClasses: (Array.isArray(edgeManifest.edgeRendering.generatedVisibilityClasses)
              ? edgeManifest.edgeRendering.generatedVisibilityClasses
              : edgeVisibilityClasses
            )
              .map((classId) => String(classId || "").trim())
              .filter((classId, index, list) => (
                edgeVisibilityClasses.includes(classId) &&
                STEP_EDGE_RENDER_CLASS_ORDER.includes(classId) &&
                list.indexOf(classId) === index
              )),
            visibilityClassCounts: edgeManifest.edgeRendering.visibilityClassCounts || {},
            generatedVisibilityClassCounts: edgeManifest.edgeRendering.generatedVisibilityClassCounts || {},
          }
        : null;
      if (!gltfPrimitivesHaveSurfaceEdgeAttributes(container.gltf)) {
        return {
          topology,
          stepArtifact: stepArtifactError({
            code: "missing_surface_edge_attributes",
            reason: `STEP topology validation requires ${STEP_EDGE_BARYCENTRIC_ATTRIBUTE} and ${STEP_EDGE_CLASS_ATTRIBUTE} on every STEP mesh primitive`,
            repoRoot,
            cadPath,
            sourcePath,
            glbPath,
            details: artifactIdentityDetails(),
          }),
          glbPath,
          stepHash,
          sourceHash,
        };
      }
    } catch {
      return {
        topology,
        stepArtifact: stepArtifactError({
          code: "missing_edge_topology",
          reason: "STEP topology validation requires readable STEP_topology edgeView in the GLB",
          repoRoot,
          cadPath,
          sourcePath,
          glbPath,
          details: artifactIdentityDetails(),
        }),
        glbPath,
        stepHash,
        sourceHash,
      };
    }
    topology.hasDisplayEdges = true;
    try {
      const selectorManifest = parseJsonBufferView(
        container.fd,
        container.gltf,
        container.binOffset,
        container.binLength,
        extension.selectorView,
        extension.encoding
      );
      if (!isCurrentStepTopologySchemaVersion(selectorManifest.schemaVersion)) {
        return {
          topology,
          stepArtifact: stepArtifactError({
            code: "unsupported_step_topology",
            reason: `STEP topology validation requires STEP_topology schemaVersion ${STEP_TOPOLOGY_SCHEMA_VERSION} in the GLB`,
            repoRoot,
            cadPath,
            sourcePath,
            glbPath,
            details: artifactIdentityDetails(),
          }),
          glbPath,
          stepHash,
          sourceHash,
        };
      }
    } catch {
      return {
        topology,
        stepArtifact: stepArtifactError({
          code: "missing_selector_topology",
          reason: "STEP topology validation requires readable STEP_topology selectorView in the GLB",
          repoRoot,
          cadPath,
          sourcePath,
          glbPath,
          details: artifactIdentityDetails(),
        }),
        glbPath,
        stepHash,
        sourceHash,
        };
      }
    topology.hasSelector = true;
    const stepArtifact = {
      ok: true,
      glbPath: repoRelativePath(repoRoot, glbPath),
      ...(artifactSourcePath ? { sourcePath: artifactSourcePath } : {}),
      sourceKind: artifactUsesPythonSource ? "python" : "step",
      ...(edgeRendering ? { edgeRendering } : {}),
      ...(artifactUsesPythonSource
        ? {
            sourceHash,
            ...(stepHash ? { stepHash } : {}),
          }
        : {
            stepHash,
          }),
    };
    return {
      topology,
      stepArtifact,
      glbPath,
      stepHash,
      sourceHash,
    };
  } catch {
    return fail(
      "missing_step_topology",
      "STEP topology validation requires readable STEP_topology indexView in the GLB"
    );
  } finally {
    if (container?.fd !== null && container?.fd !== undefined) {
      try {
        fs.closeSync(container.fd);
      } catch {
        // Ignore close failures during catalog scanning.
      }
    }
  }
}

export function readStepSourceStatus({
  repoRoot,
  stepPath,
  pythonSourcePath = "",
  cadPath = "",
} = {}) {
  if (!repoRoot) {
    throw new Error("repoRoot is required");
  }
  if (!stepPath) {
    throw new Error("stepPath is required");
  }
  const resolvedRepoRoot = path.resolve(repoRoot);
  const resolvedStepPath = path.resolve(stepPath);
  const extension = path.extname(resolvedStepPath) || ".step";
  const normalizedCadPath = cadPath || cadPathForStepSource(resolvedRepoRoot, resolvedStepPath, extension);
  const validation = validateStepTopologyArtifact({
    repoRoot: resolvedRepoRoot,
    sourcePath: resolvedStepPath,
    cadPath: normalizedCadPath,
  });
  const stepArtifact = validation.stepArtifact || {};
  const artifact = catalogArtifactFromValidation(stepArtifact) || null;
  const normalizedPythonSourcePath = pythonSourcePath
    ? repoRelativePath(
        resolvedRepoRoot,
        path.isAbsolute(pythonSourcePath)
          ? path.resolve(pythonSourcePath)
          : path.resolve(resolvedRepoRoot, pythonSourcePath),
      )
    : "";
  const hasPythonSource = Boolean(normalizedPythonSourcePath) ||
    String(stepArtifact.sourceKind || artifact?.sourceKind || "").trim().toLowerCase() === "python";
  const sourceKind = hasPythonSource ? "python" : "step";
  const file = repoRelativePath(resolvedRepoRoot, resolvedStepPath);
  const sourcePath = String(stepArtifact.sourcePath || artifact?.sourcePath || normalizedPythonSourcePath || "").trim();
  const base = {
    ok: true,
    file,
    stepPath: file,
    sourceKind,
    artifact,
    ...(sourcePath ? { sourcePath } : {}),
  };

  if (!fileStats(resolvedStepPath)) {
    return {
      ...base,
      ok: false,
      step: {
        ok: false,
        status: "missing",
        missing: true,
        stale: false,
        message: "STEP file is missing.",
      },
    };
  }

  return {
    ...base,
    step: {
      ok: true,
      status: "current",
      missing: false,
      stale: false,
      currentHash: sha256File(resolvedStepPath),
    },
  };
}

function stepKindFromTopology(topology) {
  const index = topology?.index && typeof topology.index === "object" ? topology.index : topology;
  if (topology?.entryKind === "assembly" || index?.entryKind === "assembly") {
    return "assembly";
  }
  return index?.assembly?.root && typeof index.assembly.root === "object"
    ? "assembly"
    : "part";
}

function sourceFormatFromExtension(extension) {
  const normalized = extension.toLowerCase().replace(/^\./, "");
  return normalized === "stp" ? "stp" : normalized;
}

function sourceFormatForPath(sourcePath, extension = path.extname(sourcePath)) {
  return pathIsImplicitCadSource(sourcePath) ? "implicit" : sourceFormatFromExtension(extension);
}

function isPerUrdfViewerDirectoryName(name) {
  const normalized = String(name || "").toLowerCase();
  return normalized.startsWith(".") && normalized.endsWith(".urdf");
}

function isHiddenDirectoryName(name) {
  return String(name || "").startsWith(".");
}

function isPathInsidePerUrdfViewerDirectory(filePath) {
  return String(filePath || "")
    .split(path.sep)
    .some((part) => isPerUrdfViewerDirectoryName(part));
}

function fileRefForSource(rootPath, sourcePath) {
  return scanRelativePath(rootPath, sourcePath);
}

function cadPathForStepSource(repoRoot, sourcePath, extension) {
  const relativePath = repoRelativePath(repoRoot, sourcePath);
  return relativePath.slice(0, -extension.length);
}

function sourcePathForInlineStepGlbArtifact(glbPath) {
  const name = path.basename(glbPath);
  if (!isInlineStepGlbArtifactPath(glbPath)) {
    return null;
  }
  return path.join(path.dirname(glbPath), name.slice(1, -".glb".length));
}

function sourcePathForInlineStepParameter(parameterPath) {
  const name = path.basename(parameterPath);
  if (!isInlineStepParameterPath(parameterPath)) {
    return null;
  }
  return path.join(path.dirname(parameterPath), name.slice(1, -".js".length));
}

function catalogArtifactFromValidation(stepArtifact) {
  if (!stepArtifact || typeof stepArtifact !== "object") {
    return undefined;
  }
  if (stepArtifact.ok) {
    return undefined;
  }
  const rawError = stepArtifact.error && typeof stepArtifact.error === "object"
    ? stepArtifact.error
    : {};
  const error = String(rawError.code || stepArtifact.error || "step_artifact_error").trim();
  const message = String(rawError.message || "").trim();
  const sourceKind = String(rawError.sourceKind || "").trim();
  const artifactHash = String(rawError.artifactHash || "").trim();
  const currentHash = String(rawError.currentHash || "").trim();
  const sourceHash = String(rawError.sourceHash || "").trim();
  const stepPath = String(rawError.stepPath || "").trim();
  const glbPath = String(rawError.glbPath || "").trim();
  const cadPath = String(rawError.cadPath || "").trim();
  return {
    ok: false,
    error,
    ...(rawError.stale ? { stale: true } : {}),
    ...(stepPath ? { stepPath } : {}),
    ...(glbPath ? { glbPath } : {}),
    ...(cadPath ? { cadPath } : {}),
    ...(sourceKind ? { sourceKind } : {}),
    ...(sourceHash ? { sourceHash } : {}),
    ...(artifactHash ? { artifactHash } : {}),
    ...(currentHash ? { currentHash } : {}),
    ...(message ? { message } : {}),
  };
}

function readStepCatalogMetadata({ repoRoot, glbPath, sourcePath = "" } = {}) {
  if (!fileStats(glbPath)) {
    return {};
  }
  let container = null;
  try {
    container = readGlbTopologyContainer(glbPath);
    const extension = container.gltf?.extensions?.[STEP_TOPOLOGY_EXTENSION];
    if (!extension || typeof extension !== "object" || Array.isArray(extension)) {
      return {};
    }
    if (!isCurrentStepTopologySchemaVersion(extension.schemaVersion)) {
      return {};
    }
    const manifest = parseJsonBufferView(
      container.fd,
      container.gltf,
      container.binOffset,
      container.binLength,
      extension.indexView,
      extension.encoding
    );
    const sourceKind = String(manifest?.sourceKind || "step").trim().toLowerCase() === "python"
      ? "python"
      : "step";
    const manifestIdentityRoot = manifestIdentityRootForStep(repoRoot, sourcePathForInlineStepGlbArtifact(glbPath) || sourcePath, manifest?.stepPath);
    const sourceIdentity = sourceKind === "python"
      ? generatorSourcePathFromManifest(repoRoot, manifest?.sourcePath, {
          identityRoot: manifestIdentityRoot,
          baseDir: path.dirname(glbPath),
        })
      : sourcePathFromManifest(repoRoot, manifest?.sourcePath, {
          identityRoot: manifestIdentityRoot,
          baseDir: path.dirname(glbPath),
        });
    return {
      topology: {
        index: manifest,
        entryKind: String(extension.entryKind || manifest?.entryKind || "").trim().toLowerCase(),
        hasSelector: Boolean(extension.selectorView),
        hasDisplayEdges: Boolean(extension.edgeView),
      },
      sourceKind,
      sourcePath: sourceIdentity.sourcePath,
      sourceHash: String(manifest?.sourceHash || ""),
      stepHash: String(manifest?.stepHash || ""),
    };
  } catch {
    return {};
  } finally {
    if (container?.fd !== null && container?.fd !== undefined) {
      try {
        fs.closeSync(container.fd);
      } catch {
        // Ignore close failures during lightweight catalog metadata reads.
      }
    }
  }
}

function pythonStepSourceFromStepMetadata(repoRoot, stepPath) {
  const metadata = readGeneratedFileMetadata(stepPath, "step");
  const metadataSourcePath = String(metadata.sourcePath || "").trim();
  if (!metadataSourcePath) {
    return null;
  }
  const sourceIdentity = sourcePathFromManifest(repoRoot, metadataSourcePath, { baseDir: path.dirname(stepPath) });
  if (!sourceIdentity.sourcePath) {
    return null;
  }
  const sourceExtension = path.extname(sourceIdentity.filePath || sourceIdentity.sourcePath).toLowerCase();
  if (sourceExtension !== ".py") {
    return null;
  }
  return {
    sourcePath: sourceIdentity.sourcePath,
    sourceHash: String(metadata.sourceHash || ""),
  };
}

function createStepEntry({ repoRoot, rootPath, sourcePath, extension, includeArtifactStatus = true }) {
  const cadPath = cadPathForStepSource(repoRoot, sourcePath, extension);
  const validation = includeArtifactStatus
    ? validateStepTopologyArtifact({
        repoRoot,
        sourcePath,
        cadPath,
      })
    : null;
  const glbPath = validation?.glbPath || inlineStepGlbArtifactPathForSource(sourcePath);
  const catalogMetadata = includeArtifactStatus
    ? {}
    : readStepCatalogMetadata({ repoRoot, glbPath, sourcePath });
  const topology = validation?.topology || catalogMetadata.topology || null;
  const stepArtifact = validation?.stepArtifact || {};
  const glbAsset = assetForPath(repoRoot, glbPath);
  const stepModuleAsset = assetForPath(repoRoot, stepParameterPathForStepSource(sourcePath));
  const artifact = includeArtifactStatus ? catalogArtifactFromValidation(stepArtifact) : undefined;
  const artifactSourceKind = String(
    stepArtifact.sourceKind ||
    stepArtifact.error?.sourceKind ||
    catalogMetadata.sourceKind ||
    artifact?.sourceKind ||
    "",
  ).trim().toLowerCase();
  const metadataPythonSource = (!includeArtifactStatus || artifact) && artifactSourceKind !== "python"
    ? pythonStepSourceFromStepMetadata(repoRoot, sourcePath)
    : null;
  const sourceKind = artifactSourceKind === "python" || metadataPythonSource ? "python" : "step";
  const artifactSourcePath = String(
    stepArtifact.sourcePath ||
    stepArtifact.error?.sourcePath ||
    catalogMetadata.sourcePath ||
    ""
  ).trim();
  const pythonSourcePath = artifactSourcePath || metadataPythonSource?.sourcePath || "";
  return {
    file: fileRefForSource(rootPath, sourcePath),
    kind: stepKindFromTopology(topology),
    url: glbAsset?.url || assetUrlForPath(repoRoot, glbPath),
    hash: glbAsset?.hash || "",
    bytes: glbAsset?.bytes || 0,
    sourceKind,
    ...(sourceKind === "python" && pythonSourcePath ? {
      source: {
        file: pythonSourcePath,
        sourcePath: pythonSourcePath,
        ...((stepArtifact.sourceHash || catalogMetadata.sourceHash || metadataPythonSource?.sourceHash)
          ? { sourceHash: stepArtifact.sourceHash || catalogMetadata.sourceHash || metadataPythonSource.sourceHash }
          : {}),
      },
    } : {}),
    ...(stepModuleAsset ? { moduleUrl: stepModuleAsset.url } : {}),
    ...(artifact ? { artifact } : {}),
  };
}

function linkedUrdfPathForSrdf(sourcePath, repoRoot) {
  let xmlText = "";
  try {
    xmlText = fs.readFileSync(sourcePath, "utf-8");
  } catch {
    return null;
  }
  const match = SRDF_URDF_METADATA_PATTERN.exec(xmlText);
  const rawRef = String(match?.[1] || "").trim();
  if (!rawRef || rawRef.includes("\\") || rawRef.startsWith("/")) {
    return null;
  }
  const resolved = path.resolve(path.dirname(sourcePath), rawRef);
  const relativeToRepo = path.relative(path.resolve(repoRoot), resolved);
  if (!relativePathStaysInsideRoot(relativeToRepo) || path.extname(resolved).toLowerCase() !== ".urdf") {
    return null;
  }
  return fileStats(resolved) ? resolved : null;
}

function createSingleAssetEntry({ repoRoot, rootPath, sourcePath, extension }) {
  const kind = sourceFormatForPath(sourcePath, extension);
  const asset = assetForPath(repoRoot, sourcePath);
  const file = fileRefForSource(rootPath, sourcePath);
  const generatedSource = generatedSourceStatusForFile({ repoRoot, sourcePath, kind });
  const entry = {
    file,
    kind,
    url: asset?.url || assetUrlForPath(repoRoot, sourcePath),
    hash: asset?.hash || "",
    bytes: asset?.bytes || 0,
    ...(generatedSource?.sourceKind === "python" ? { sourceKind: "python" } : {}),
    ...(generatedSource?.source ? { source: generatedSource.source } : {}),
    ...(generatedSource?.sourceStatus ? { sourceStatus: generatedSource.sourceStatus } : {}),
  };
  if (kind === "srdf") {
    const linkedUrdfPath = linkedUrdfPathForSrdf(sourcePath, repoRoot);
    if (linkedUrdfPath) {
      const urdfAsset = assetForPath(repoRoot, linkedUrdfPath);
      if (urdfAsset) {
        entry.relations = {
          urdf: {
            file: fileRefForSource(rootPath, linkedUrdfPath),
            ...urdfAsset,
          },
        };
      }
    }
  }
  return entry;
}

function shouldSkipDirectory(name) {
  return VIEWER_SKIPPED_DIRECTORIES.has(name) || isHiddenDirectoryName(name) || isPerStepViewerDirectoryName(name) || isPerUrdfViewerDirectoryName(name);
}

function scanPathIncluded(includePath, rootPath, entryPath, isDirectory) {
  if (typeof includePath !== "function") {
    return true;
  }
  return includePath({
    filePath: entryPath,
    relativePath: scanRelativePath(rootPath, entryPath),
    isDirectory,
  }) !== false;
}

function collectCadSourceFiles(rootPath, { scanRootPath = rootPath, includePath = null } = {}, result = []) {
  let entries = [];
  try {
    entries = fs.readdirSync(rootPath, { withFileTypes: true });
  } catch {
    return result;
  }

  for (const entry of entries) {
    const entryPath = path.join(rootPath, entry.name);
    if (entry.isDirectory()) {
      if (!shouldSkipDirectory(entry.name) && scanPathIncluded(includePath, scanRootPath, entryPath, true)) {
        collectCadSourceFiles(entryPath, { scanRootPath, includePath }, result);
      }
      continue;
    }
    if (!entry.isFile()) {
      continue;
    }
    if (!scanPathIncluded(includePath, scanRootPath, entryPath, false)) {
      continue;
    }
    const extension = path.extname(entry.name).toLowerCase();
    if (isInlineStepGlbArtifactPath(entryPath)) {
      const sourcePath = sourcePathForInlineStepGlbArtifact(entryPath);
      if (sourcePath && !fileStats(sourcePath)) {
        result.push(entryPath);
      }
      continue;
    }
    if ((SOURCE_EXTENSIONS.has(extension) || pathIsImplicitCadSource(entryPath)) && !isInlineStepGlbArtifactPath(entryPath)) {
      result.push(entryPath);
      continue;
    }
  }
  return result;
}

function compareEntries(a, b) {
  return String(a.file || "").localeCompare(String(b.file || ""), undefined, {
    numeric: true,
    sensitivity: "base",
  });
}

function pathHasSkippedDirectory(rootPath, filePath) {
  const relativePath = scanRelativePath(rootPath, filePath);
  if (!relativePathStaysInsideRoot(relativePath)) {
    return true;
  }
  const parts = relativePath.split("/").filter(Boolean);
  return parts.slice(0, -1).some((part) => shouldSkipDirectory(part));
}

function logicalStepSourcePathForInlineArtifactPath(filePath) {
  if (isInlineStepGlbArtifactPath(filePath)) {
    return sourcePathForInlineStepGlbArtifact(filePath);
  }
  if (isInlineStepParameterPath(filePath)) {
    return sourcePathForInlineStepParameter(filePath);
  }
  return null;
}

function logicalStepSourceExistsForSidecar(sourcePath) {
  return Boolean(
    sourcePath &&
    (
      fileStats(sourcePath) ||
      fileStats(inlineStepGlbArtifactPathForSource(sourcePath)) ||
      fileStats(stepParameterPathForStepSource(sourcePath))
    )
  );
}

export function catalogFileRefForPath({ repoRoot, rootDir = DEFAULT_VIEWER_ROOT_DIR, filePath } = {}) {
  if (!repoRoot) {
    throw new Error("repoRoot is required");
  }
  if (!filePath) {
    throw new Error("filePath is required");
  }
  const resolved = resolveViewerRoot(repoRoot, rootDir);
  const resolvedFilePath = path.resolve(filePath);
  if (!pathIsInside(resolvedFilePath, resolved.rootPath) || pathHasSkippedDirectory(resolved.rootPath, resolvedFilePath)) {
    return "";
  }
  const logicalStepSourcePath = logicalStepSourcePathForInlineArtifactPath(resolvedFilePath);
  if (logicalStepSourcePath) {
    return fileRefForSource(resolved.rootPath, logicalStepSourcePath);
  }
  if (isPathInsidePerStepViewerDirectory(resolvedFilePath) || isPathInsidePerUrdfViewerDirectory(resolvedFilePath)) {
    return "";
  }
  const extension = path.extname(resolvedFilePath).toLowerCase();
  return (SOURCE_EXTENSIONS.has(extension) || pathIsImplicitCadSource(resolvedFilePath))
    ? fileRefForSource(resolved.rootPath, resolvedFilePath)
    : "";
}

export function scanCadFile({
  repoRoot,
  rootDir = DEFAULT_VIEWER_ROOT_DIR,
  filePath,
  includeArtifactStatus = true,
} = {}) {
  if (!repoRoot) {
    throw new Error("repoRoot is required");
  }
  if (!filePath) {
    throw new Error("filePath is required");
  }
  const resolved = resolveViewerRoot(repoRoot, rootDir);
  const resolvedFilePath = path.resolve(filePath);
  if (!pathIsInside(resolvedFilePath, resolved.rootPath) || pathHasSkippedDirectory(resolved.rootPath, resolvedFilePath)) {
    return null;
  }

  const logicalStepSourcePath = logicalStepSourcePathForInlineArtifactPath(resolvedFilePath);
  if (logicalStepSourcePath) {
    if (!logicalStepSourceExistsForSidecar(logicalStepSourcePath)) {
      return null;
    }
    return createStepEntry({
      repoRoot,
      rootPath: resolved.rootPath,
      sourcePath: logicalStepSourcePath,
      extension: path.extname(logicalStepSourcePath).toLowerCase(),
      includeArtifactStatus,
    });
  }

  if (isPathInsidePerStepViewerDirectory(resolvedFilePath) || isPathInsidePerUrdfViewerDirectory(resolvedFilePath)) {
    return null;
  }

  const extension = path.extname(resolvedFilePath).toLowerCase();
  if ((!SOURCE_EXTENSIONS.has(extension) && !pathIsImplicitCadSource(resolvedFilePath)) || !fileStats(resolvedFilePath)) {
    if ((extension === ".step" || extension === ".stp") && fileStats(inlineStepGlbArtifactPathForSource(resolvedFilePath))) {
      return createStepEntry({
        repoRoot,
        rootPath: resolved.rootPath,
        sourcePath: resolvedFilePath,
        extension,
        includeArtifactStatus,
      });
    }
    return null;
  }
  if (extension === ".step" || extension === ".stp") {
    return createStepEntry({
      repoRoot,
      rootPath: resolved.rootPath,
      sourcePath: resolvedFilePath,
      extension,
      includeArtifactStatus,
    });
  }
  return createSingleAssetEntry({
    repoRoot,
    rootPath: resolved.rootPath,
    sourcePath: resolvedFilePath,
    extension,
  });
}

export function scanCadDirectory({
  repoRoot,
  rootDir = DEFAULT_VIEWER_ROOT_DIR,
  includePath = null,
  includeArtifactStatus = true,
} = {}) {
  if (!repoRoot) {
    throw new Error("repoRoot is required");
  }
  const resolved = resolveViewerRoot(repoRoot, rootDir);
  const entries = collectCadSourceFiles(resolved.rootPath, {
    scanRootPath: resolved.rootPath,
    includePath,
  })
    .map((sourcePath) => {
      const logicalSourcePath = isInlineStepGlbArtifactPath(sourcePath)
        ? sourcePathForInlineStepGlbArtifact(sourcePath)
        : sourcePath;
      const extension = path.extname(logicalSourcePath).toLowerCase();
      if (extension === ".step" || extension === ".stp") {
        return createStepEntry({
          repoRoot,
          rootPath: resolved.rootPath,
          sourcePath: logicalSourcePath,
          extension,
          includeArtifactStatus,
        });
      }
      return createSingleAssetEntry({
        repoRoot,
        rootPath: resolved.rootPath,
        sourcePath,
        extension,
      });
    })
    .sort(compareEntries);

  return {
    schemaVersion: CAD_CATALOG_SCHEMA_VERSION,
    entries,
  };
}

export function sortCatalogEntries(entries) {
  return [...(Array.isArray(entries) ? entries : [])].sort(compareEntries);
}

export function isServedCadAsset(filePath) {
  const extension = path.extname(filePath).toLowerCase();
  if (isInlineStepGlbArtifactPath(filePath)) {
    return true;
  }
  if (isInlineStepParameterPath(filePath)) {
    return true;
  }
  if (isPathInsidePerStepViewerDirectory(filePath)) {
    return false;
  }
  if (isPathInsidePerUrdfViewerDirectory(filePath)) {
    return false;
  }
  if (SOURCE_EXTENSIONS.has(extension) || pathIsImplicitCadSource(filePath)) {
    return true;
  }
  return false;
}

function isCatalogRelevantPythonSource(filePath) {
  const normalized = path.normalize(String(filePath || ""));
  if (path.extname(normalized).toLowerCase() !== ".py") {
    return false;
  }
  return !normalized.split(/[\\/]+/u).some((part) => VIEWER_SKIPPED_DIRECTORIES.has(part));
}

export function isCatalogRelevantPath(filePath) {
  return isServedCadAsset(filePath) || isCatalogRelevantPythonSource(filePath);
}
