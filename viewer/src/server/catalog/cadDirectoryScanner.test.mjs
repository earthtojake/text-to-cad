import assert from "node:assert/strict";
import crypto from "node:crypto";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import {
  STEP_EDGE_RENDER_VISIBILITY_CLASSES,
  STEP_TOPOLOGY_SCHEMA_VERSION
} from "cadjs/common/stepTopology.mjs";
import {
  isCatalogRelevantPath,
  isServedCadAsset,
  catalogFileRefForPath,
  normalizeViewerRootDir,
  readStepSourceStatus,
  resolveViewerRoot,
  scanCadDirectory,
  scanCadFile,
  validateStepTopologyArtifact,
} from "./cadDirectoryScanner.mjs";

function makeTempRepo() {
  return fs.mkdtempSync(path.join(os.tmpdir(), "cad-viewer-scan-"));
}

function writeFile(filePath, content = "") {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, content);
}

function sha256Buffer(buffer) {
  return crypto.createHash("sha256").update(buffer).digest("hex");
}

function writeStep(filePath, content = "ISO-10303-21;\nEND-ISO-10303-21;\n") {
  writeFile(filePath, content);
  return sha256Buffer(Buffer.from(content));
}

function writeStepWithSourceMetadata(filePath, {
  sourcePath,
  sourceHash = "source-hash",
} = {}) {
  return writeStep(filePath, [
    "ISO-10303-21;",
    "DATA;",
    `#1=DESCRIPTIVE_REPRESENTATION_ITEM('cadpy:sourcePath','${sourcePath}');`,
    "#2=REPRESENTATION('cadpy:sourcePath',(#1),#9);",
    "#3=PROPERTY_DEFINITION('cadpy metadata','cadpy:sourcePath',#10);",
    "#4=PROPERTY_DEFINITION_REPRESENTATION(#3,#2);",
    `#5=DESCRIPTIVE_REPRESENTATION_ITEM('cadpy:sourceHash','${sourceHash}');`,
    "#6=REPRESENTATION('cadpy:sourceHash',(#5),#9);",
    "#7=PROPERTY_DEFINITION('cadpy metadata','cadpy:sourceHash',#10);",
    "#8=PROPERTY_DEFINITION_REPRESENTATION(#7,#6);",
    "ENDSEC;",
    "END-ISO-10303-21;",
    "",
  ].join("\n"));
}

function pad4(buffer, byte = 0) {
  const padding = (4 - (buffer.length % 4)) % 4;
  return padding ? Buffer.concat([buffer, Buffer.alloc(padding, byte)]) : buffer;
}

function topologyGlb(manifest, {
  selector = true,
  displayEdges = true,
  extensionSchemaVersion = STEP_TOPOLOGY_SCHEMA_VERSION,
  manifestSchemaVersion = extensionSchemaVersion
} = {}) {
  let binary = Buffer.alloc(0);
  const bufferViews = [];
  function addBufferView(payload) {
    binary = pad4(binary);
    const byteOffset = binary.length;
    binary = Buffer.concat([binary, payload]);
    const index = bufferViews.length;
    bufferViews.push({ buffer: 0, byteOffset, byteLength: payload.length });
    return index;
  }
  const edgeRendering = manifest.edgeRendering || {
    visibilityClasses: STEP_EDGE_RENDER_VISIBILITY_CLASSES,
    generatedVisibilityClasses: ["feature"],
    visibilityClassCounts: { feature: 1 },
    generatedVisibilityClassCounts: { feature: 1 },
  };
  const indexManifest = { schemaVersion: manifestSchemaVersion, profile: "index", entryKind: manifest.entryKind || (manifest.assembly ? "assembly" : "part"), edgeRendering, ...manifest };
  const indexView = addBufferView(Buffer.from(JSON.stringify(indexManifest), "utf8"));
  const surfaceHalfEdgesView = addBufferView(Buffer.alloc(0));
  const edgeView = displayEdges
    ? addBufferView(Buffer.from(JSON.stringify({
      schemaVersion: manifestSchemaVersion,
      profile: "surface-edges",
      sourceKind: manifest.sourceKind,
      sourcePath: manifest.sourcePath,
      sourceHash: manifest.sourceHash,
      stepHash: manifest.stepHash,
      classCodes: { none: 0, feature: 1, tangent: 2, seam: 3, degenerate: 4, boundary: 5, nonManifold: 6, unknown: 7 },
      primitiveAttributes: { barycentric: "_CAD_EDGE_BARYCENTRIC", class: "_CAD_EDGE_CLASS" },
      halfEdgeColumns: ["edgeRow", "faceRow", "occurrenceRow", "primitiveIndex", "triangleIndex", "side", "classCode"],
      halfEdgesView: "surfaceHalfEdges",
      edgeRendering,
      buffers: {
        littleEndian: true,
        views: {
          surfaceHalfEdges: {
            dtype: "uint32",
            bufferView: surfaceHalfEdgesView,
            byteOffset: 0,
            byteLength: 0,
            count: 0,
            itemSize: 4
          }
        }
      },
    }), "utf8"))
    : null;
  const selectorView = selector
    ? addBufferView(Buffer.from(JSON.stringify({ schemaVersion: manifestSchemaVersion, profile: "selector", ...manifest }), "utf8"))
    : null;
  binary = pad4(binary);
  const extension = { schemaVersion: extensionSchemaVersion, entryKind: indexManifest.entryKind, indexView, encoding: "utf-8" };
  if (selectorView !== null) {
    extension.selectorView = selectorView;
  }
  if (edgeView !== null) {
    extension.edgeView = edgeView;
  }
  const gltf = {
    asset: { version: "2.0" },
    buffers: [{ byteLength: binary.length }],
    bufferViews,
    meshes: [{
      primitives: [{
        attributes: {
          _CAD_EDGE_BARYCENTRIC: 0,
          _CAD_EDGE_CLASS: 1,
        },
      }],
    }],
    extensionsUsed: ["STEP_topology"],
    extensions: { STEP_topology: extension },
  };
  const jsonChunk = pad4(Buffer.from(JSON.stringify(gltf), "utf8"), 0x20);
  const header = Buffer.alloc(12);
  const jsonHeader = Buffer.alloc(8);
  const binHeader = Buffer.alloc(8);
  header.writeUInt32LE(0x46546c67, 0);
  header.writeUInt32LE(2, 4);
  header.writeUInt32LE(12 + 8 + jsonChunk.length + 8 + binary.length, 8);
  jsonHeader.writeUInt32LE(jsonChunk.length, 0);
  jsonHeader.write("JSON", 4, "latin1");
  binHeader.writeUInt32LE(binary.length, 0);
  binHeader.write("BIN\0", 4, "latin1");
  return Buffer.concat([header, jsonHeader, jsonChunk, binHeader, binary]);
}

function entryByFile(catalog, file) {
  return catalog.entries.find((entry) => entry.file === file);
}

function assertStepArtifactError(entry, code) {
  assert.equal(entry.artifact.ok, false);
  assert.equal(entry.artifact.error, code);
  assert.match(entry.artifact.message, /\.$/);
  assert.doesNotMatch(entry.artifact.message, /Regenerate STEP artifacts/);
  assert.equal(entry.assets, undefined);
  assert.equal(entry.step, undefined);
  assert.equal(entry.stepArtifact, undefined);
}

test("scanCadDirectory discovers CAD files directly and infers STEP assets", () => {
  const repoRoot = makeTempRepo();
  const stepHash = writeStep(path.join(repoRoot, "workspace/sample_part/sample_part.step"));
  writeFile(path.join(repoRoot, "workspace/sample_part/.sample_part.step.glb"), topologyGlb({
    sourcePath: "workspace/sample_part/sample_part.step",
    stepHash,
    assembly: {
      mesh: { addressing: "gltf-node-extras" },
      root: { nodeType: "assembly" }
    },
  }));
  writeFile(path.join(repoRoot, "workspace/sample_part/.sample_part.step.js"), "export default { manifest: { schemaVersion: 1 } };\n");
  writeFile(path.join(repoRoot, "workspace/sample_part/.sample_part.step/ignored.step"), "ignored\n");
  writeFile(path.join(repoRoot, "workspace/sample_part/sample_part.stl"), "solid sample_part\nendsolid sample_part\n");
  writeFile(path.join(repoRoot, "workspace/sample_part/sample_part.3mf"), "3mf\n");
  writeFile(path.join(repoRoot, "workspace/sample_part/sample_part.glb"), "native glb\n");
  writeFile(path.join(repoRoot, "workspace/sample_part/sample_part.gcode"), "G1 X1 Y1 E0.02\n");
  writeFile(path.join(repoRoot, "workspace/implicit/orb.implicit.js"), "export default { distance: 'length(p) - 1.0' };\n");
  writeFile(path.join(repoRoot, "workspace/implicit/implicit-cad.mjs"), "export const helper = true;\n");
  writeFile(path.join(repoRoot, "workspace/sheets/bracket.dxf"), "0\nEOF\n");
  writeFile(path.join(repoRoot, "workspace/robots/sample_robot.urdf"), "<robot name=\"sample_robot\" />\n");
  writeFile(path.join(repoRoot, "workspace/robots/sample_robot.srdf"), "<robot name=\"sample_robot\" xmlns:tcad=\"https://text-to-cad.dev/srdf\"><tcad:urdf path=\"sample_robot.urdf\"/></robot>\n");
  writeFile(path.join(repoRoot, "workspace/robots/legacy_robot.srdf"), "<robot name=\"sample_robot\" xmlns:explorer=\"https://text-to-cad.dev/explorer\"><explorer:urdf path=\"sample_robot.urdf\"/></robot>\n");
  writeFile(path.join(repoRoot, "workspace/robots/sample_robot.sdf"), "<sdf version=\"1.12\"><model name=\"sample_robot\" /></sdf>\n");
  writeFile(path.join(repoRoot, "workspace/robots/.sample_robot.urdf/ignored.urdf"), "<robot name=\"ignored\" />\n");
  writeFile(path.join(repoRoot, "workspace/sample_part/sample_part.py"), "print('ignored')\n");
  writeFile(path.join(repoRoot, "workspace/.hidden/hidden.step"), "ISO-10303-21;\nEND-ISO-10303-21;\n");

  const catalog = scanCadDirectory({ repoRoot, rootDir: "workspace" });

  assert.equal(catalog.schemaVersion, 4);
  assert.equal(catalog.root, undefined);
  const stepEntry = entryByFile(catalog, "sample_part/sample_part.step");
  const stepGlbBytes = fs.statSync(path.join(repoRoot, "workspace/sample_part/.sample_part.step.glb")).size;
  assert.equal(stepEntry.kind, "assembly");
  assert.equal(stepEntry.file, "sample_part/sample_part.step");
  assert.equal(stepEntry.artifact, undefined);
  assert.equal(stepEntry.sourceKind, "step");
  assert.ok(stepEntry.moduleUrl.startsWith("/workspace/sample_part/.sample_part.step.js?v="));
  assert.equal(stepEntry.step, undefined);
  assert.equal(stepEntry.source, undefined);
  assert.equal(stepEntry.assets, undefined);
  assert.ok(stepEntry.url.startsWith("/workspace/sample_part/.sample_part.step.glb?v="));
  assert.equal(stepEntry.bytes, stepGlbBytes);
  assert.equal(stepEntry.hash.length, 64);
  for (const [file, kind] of [
    ["sample_part/sample_part.stl", "stl"],
    ["sample_part/sample_part.3mf", "3mf"],
    ["sample_part/sample_part.glb", "glb"],
    ["sample_part/sample_part.gcode", "gcode"],
    ["implicit/orb.implicit.js", "implicit"],
    ["sheets/bracket.dxf", "dxf"],
    ["robots/sample_robot.urdf", "urdf"],
    ["robots/legacy_robot.srdf", "srdf"],
    ["robots/sample_robot.srdf", "srdf"],
    ["robots/sample_robot.sdf", "sdf"],
  ]) {
    const entry = entryByFile(catalog, file);
    assert.equal(entry.kind, kind);
    assert.ok(entry.url.startsWith(`/workspace/${file}?v=`));
    assert.equal(entry.hash.length, 64);
    assert.equal(entry.assets, undefined);
    assert.equal(entry.artifact, undefined);
  }
  assert.ok(entryByFile(catalog, "sample_part/sample_part.gcode").url.startsWith("/workspace/sample_part/sample_part.gcode?v="));
  assert.equal(entryByFile(catalog, "sheets/bracket.dxf").kind, "dxf");
  assert.equal(entryByFile(catalog, "robots/sample_robot.urdf").kind, "urdf");
  assert.equal(entryByFile(catalog, "robots/legacy_robot.srdf").kind, "srdf");
  assert.equal(entryByFile(catalog, "robots/sample_robot.srdf").kind, "srdf");
  assert.equal(entryByFile(catalog, "robots/sample_robot.sdf").kind, "sdf");
  assert.ok(entryByFile(catalog, "robots/sample_robot.sdf").url.startsWith("/workspace/robots/sample_robot.sdf?v="));
  assert.ok(entryByFile(catalog, "robots/sample_robot.srdf").url.startsWith("/workspace/robots/sample_robot.srdf?v="));
  assert.equal(entryByFile(catalog, "robots/sample_robot.srdf").relations.urdf.file, "robots/sample_robot.urdf");
  assert.ok(entryByFile(catalog, "robots/sample_robot.srdf").relations.urdf.url.startsWith("/workspace/robots/sample_robot.urdf?v="));
  assert.equal(entryByFile(catalog, "robots/legacy_robot.srdf").relations.urdf.file, "robots/sample_robot.urdf");
  assert.equal(entryByFile(catalog, "sample_part/sample_part.py"), undefined);
  assert.equal(entryByFile(catalog, "sample_part/.sample_part.step.glb"), undefined);
  assert.equal(entryByFile(catalog, "sample_part/.sample_part.step.js"), undefined);
  assert.equal(entryByFile(catalog, "implicit/implicit-cad.mjs"), undefined);
  assert.equal(entryByFile(catalog, "sample_part/.sample_part.step/ignored.step"), undefined);
  assert.equal(entryByFile(catalog, "robots/.sample_robot.urdf/ignored.urdf"), undefined);
  assert.equal(entryByFile(catalog, ".hidden/hidden.step"), undefined);
});

test("scanCadFile updates a single catalog entry without walking sibling directories", () => {
  const repoRoot = makeTempRepo();
  const stepPath = path.join(repoRoot, "workspace/sample_part/sample_part.step");
  const stepHash = writeStep(stepPath);
  writeFile(path.join(repoRoot, "workspace/sample_part/.sample_part.step.glb"), topologyGlb({
    sourcePath: "workspace/sample_part/sample_part.step",
    stepHash,
    entryKind: "part",
  }));
  writeFile(path.join(repoRoot, "workspace/sample_part/.sample_part.step.js"), "export default { manifest: { schemaVersion: 1 } };\n");
  writeFile(path.join(repoRoot, "workspace/ignored/ignored.step"), "ISO-10303-21;\nEND-ISO-10303-21;\n");

  const entry = scanCadFile({ repoRoot, rootDir: "workspace", filePath: stepPath });

  assert.equal(entry.file, "sample_part/sample_part.step");
  assert.equal(entry.kind, "part");
  assert.ok(entry.moduleUrl.startsWith("/workspace/sample_part/.sample_part.step.js?v="));
  assert.ok(entry.url.startsWith("/workspace/sample_part/.sample_part.step.glb?v="));
});

test("scanCadFile maps inline STEP sidecars back to their logical STEP entry", () => {
  const repoRoot = makeTempRepo();
  const stepPath = path.join(repoRoot, "workspace/sample_part/sample_part.step");
  const stepHash = writeStep(stepPath);
  const glbPath = path.join(repoRoot, "workspace/sample_part/.sample_part.step.glb");
  writeFile(glbPath, topologyGlb({
    sourcePath: "workspace/sample_part/sample_part.step",
    stepHash,
    entryKind: "assembly",
  }));

  assert.equal(
    catalogFileRefForPath({ repoRoot, rootDir: "workspace", filePath: glbPath }),
    "sample_part/sample_part.step"
  );
  assert.equal(
    scanCadFile({ repoRoot, rootDir: "workspace", filePath: glbPath }).file,
    "sample_part/sample_part.step"
  );

  fs.unlinkSync(stepPath);
  const generatedOnlyEntry = scanCadFile({ repoRoot, rootDir: "workspace", filePath: glbPath });
  assert.equal(generatedOnlyEntry.file, "sample_part/sample_part.step");
  assert.equal(generatedOnlyEntry.sourceKind, "step");
});

test("scanCadDirectory can skip STEP artifact status for fast catalog reads", () => {
  const repoRoot = makeTempRepo();
  const stepPath = path.join(repoRoot, "workspace", "fast.step");
  writeStep(stepPath);

  const catalog = scanCadDirectory({
    repoRoot,
    rootDir: "workspace",
    includeArtifactStatus: false,
  });
  const entry = entryByFile(catalog, "fast.step");

  assert.equal(entry.file, "fast.step");
  assert.equal(entry.artifact, undefined);
  const status = readStepSourceStatus({ repoRoot, stepPath });
  assert.equal(status.artifact.error, "missing_glb");
  assert.equal(status.artifact.glbPath, "workspace/.fast.step.glb");
});

test("scanCadDirectory emits minimal entries for python-backed generated GLB artifacts", () => {
  const repoRoot = makeTempRepo();
  const stepHash = writeStep(path.join(repoRoot, "workspace/generated/generated.step"));
  writeFile(path.join(repoRoot, "workspace/generated/generated.py"), "def gen_step():\n    return None\n");
  const sourceHash = sha256Buffer(fs.readFileSync(path.join(repoRoot, "workspace/generated/generated.py")));
  writeFile(path.join(repoRoot, "workspace/generated/.generated.step.glb"), topologyGlb({
    sourceKind: "python",
    sourcePath: "workspace/generated/generated.py",
    sourceHash,
    stepHash,
    entryKind: "part",
  }));

  const catalog = scanCadDirectory({ repoRoot, rootDir: "workspace" });
  const entry = entryByFile(catalog, "generated/generated.step");

  assert.equal(entry.kind, "part");
  assert.equal(entry.sourceKind, "python");
  assert.equal(entry.artifact, undefined);
  assert.ok(entry.url.startsWith("/workspace/generated/.generated.step.glb?v="));
  assert.equal(entry.hash.length, 64);
  assert.equal(entry.stepArtifact, undefined);
  assert.equal(entry.step, undefined);
});

test("scanCadDirectory reads Python source hash from GLB artifacts", () => {
  const repoRoot = makeTempRepo();
  const stepHash = writeStep(path.join(repoRoot, "workspace/generated/generated.step"));
  const generatorPath = path.join(repoRoot, "workspace/generated/generated.py");
  writeFile(generatorPath, "from helper import SIZE\n\ndef gen_step():\n    return None\n");
  writeFile(path.join(repoRoot, "workspace/generated/helper.py"), "SIZE = 1\n");
  const sourceHash = sha256Buffer(fs.readFileSync(generatorPath));
  writeFile(path.join(repoRoot, "workspace/generated/.generated.step.glb"), topologyGlb({
    sourceKind: "python",
    sourcePath: "workspace/generated/generated.py",
    sourceHash,
    stepHash,
    entryKind: "part",
  }));

  const catalog = scanCadDirectory({ repoRoot, rootDir: "workspace" });
  const entry = entryByFile(catalog, "generated/generated.step");

  assert.equal(entry.artifact, undefined);
  assert.equal(entry.sourceKind, "python");
  assert.equal(entry.source.sourceHash, sourceHash);
});

test("scanCadDirectory accepts Python STEP topology generated from a nested project root", () => {
  const repoRoot = makeTempRepo();
  const projectRoot = path.join(repoRoot, "workspace/arm7");
  const stepPath = path.join(projectRoot, "STEP/assembly.step");
  const generatorPath = path.join(projectRoot, "STEP/assembly.py");
  const stepHash = writeStep(stepPath);
  writeFile(generatorPath, "from armkit import SIZE\n\ndef gen_step():\n    return None\n");
  writeFile(path.join(projectRoot, "armkit.py"), "SIZE = 1\n");
  const sourceHash = sha256Buffer(fs.readFileSync(generatorPath));
  writeFile(path.join(projectRoot, "STEP/.assembly.step.glb"), topologyGlb({
    sourceKind: "python",
    sourcePath: "assembly.py",
    sourceHash,
    stepHash,
    stepPath: "assembly.step",
    entryKind: "assembly",
  }));

  const catalog = scanCadDirectory({ repoRoot, rootDir: "workspace" });
  const entry = entryByFile(catalog, "arm7/STEP/assembly.step");
  const validation = validateStepTopologyArtifact({
    repoRoot,
    sourcePath: stepPath,
    cadPath: "workspace/arm7/STEP/assembly",
  });

  assert.equal(validation.stepArtifact.ok, true);
  assert.equal(validation.stepArtifact.sourcePath, "workspace/arm7/STEP/assembly.py");
  assert.equal(entry.artifact, undefined);
  assert.equal(entry.sourceKind, "python");
  assert.equal(entry.source.file, "workspace/arm7/STEP/assembly.py");
  assert.equal(entry.source.sourceHash, sourceHash);
});

test("scanCadDirectory marks non-STEP files as Python-backed from metadata comments", () => {
  const repoRoot = makeTempRepo();
  const generatorPath = path.join(repoRoot, "workspace/robots/robot_urdf.py");
  writeFile(generatorPath, "def gen_urdf():\n    return {'xml': '<robot name=\"sample\" />'}\n");
  const sourceHash = sha256Buffer(fs.readFileSync(generatorPath));
  writeFile(path.join(repoRoot, "workspace/robots/robot.urdf"), [
    `<!-- cadpy:sourcePath=robot_urdf.py -->`,
    `<!-- cadpy:sourceHash=${sourceHash} -->`,
    "<robot name=\"sample\" />",
    "",
  ].join("\n"));
  writeFile(generatorPath, "def gen_urdf():\n    return {'xml': '<robot name=\"changed\" />'}\n");

  const catalog = scanCadDirectory({ repoRoot, rootDir: "workspace" });
  const entry = entryByFile(catalog, "robots/robot.urdf");

  assert.equal(entry.kind, "urdf");
  assert.equal(entry.sourceKind, "python");
  assert.equal(entry.source.file, "workspace/robots/robot_urdf.py");
  assert.equal(entry.source.sourceHash, sourceHash);
  assert.equal(entry.sourceStatus, undefined);
});

test("scanCadDirectory discovers python-backed logical STEP entries from GLB artifacts", () => {
  const repoRoot = makeTempRepo();
  const generatorPath = path.join(repoRoot, "workspace/generated_only/generated_only.py");
  writeFile(generatorPath, "def gen_step():\n    return None\n");
  const sourceHash = sha256Buffer(fs.readFileSync(generatorPath));
  writeFile(path.join(repoRoot, "workspace/generated_only/.generated_only.step.glb"), topologyGlb({
    sourceKind: "python",
    sourcePath: "workspace/generated_only/generated_only.py",
    sourceHash,
    entryKind: "assembly",
  }));

  const catalog = scanCadDirectory({ repoRoot, rootDir: "workspace" });
  const entry = entryByFile(catalog, "generated_only/generated_only.step");

  assert.equal(entry.kind, "assembly");
  assert.equal(entry.sourceKind, "python");
  assert.equal(entry.artifact, undefined);
  assert.ok(entry.url.startsWith("/workspace/generated_only/.generated_only.step.glb?v="));
  assert.equal(entry.hash.length, 64);
  assert.equal(entry.stepArtifact, undefined);
  assert.equal(entry.step, undefined);
});

test("scanCadDirectory treats missing GLBs for STEP files with Python metadata as Python-backed", () => {
  const repoRoot = makeTempRepo();
  writeFile(path.join(repoRoot, "workspace/generated/generated.py"), "def gen_step():\n    return None\n");
  writeStepWithSourceMetadata(path.join(repoRoot, "workspace/generated/generated.step"), {
    sourcePath: "generated.py",
    sourceHash: "direct-source-hash",
  });

  const catalog = scanCadDirectory({ repoRoot, rootDir: "workspace" });
  const entry = entryByFile(catalog, "generated/generated.step");

  assert.equal(entry.sourceKind, "python");
  assert.deepEqual(entry.source, {
    file: "workspace/generated/generated.py",
    sourcePath: "workspace/generated/generated.py",
    sourceHash: "direct-source-hash",
  });
  assert.equal(entry.artifact.error, "missing_glb");
});

test("scanCadDirectory requires sourcePath instead of recovering Python identity from embedded file lists", () => {
  const repoRoot = makeTempRepo();
  const stepPath = path.join(repoRoot, "workspace/generated/generated.step");
  writeStep(stepPath);
  writeFile(path.join(repoRoot, "workspace/generated/__init__.py"), "\n");
  writeFile(path.join(repoRoot, "workspace/generated/helper.py"), "def gen_step():\n    return None\n");
  writeFile(path.join(repoRoot, "workspace/generated/generated.py"), "def gen_step():\n    return None\n");
  writeFile(path.join(repoRoot, "workspace/generated/.generated.step.glb"), topologyGlb({
    sourceKind: "python",
    sourceHash: "source-hash",
    entryKind: "part",
  }));

  const validation = validateStepTopologyArtifact({
    repoRoot,
    sourcePath: stepPath,
    cadPath: "workspace/generated/generated",
  });

  assert.equal(validation.stepArtifact.ok, false);
  assert.equal(validation.stepArtifact.error.code, "missing_source_path");
});

test("scanCadDirectory ignores Python dependency changes for STEP artifact freshness", () => {
  const repoRoot = makeTempRepo();
  try {
    const stepHash = writeStep(path.join(repoRoot, "workspace/generated/generated.step"));
    const generatorPath = path.join(repoRoot, "workspace/generated/generated.py");
    writeFile(path.join(repoRoot, "workspace/generated/generated.py"), [
      "def gen_step():",
      "    return None",
      "",
    ].join("\n"));
    const sourceHash = sha256Buffer(fs.readFileSync(generatorPath));
    writeFile(path.join(repoRoot, "workspace/generated/helper.py"), "SIZE = 1\n");
    writeFile(path.join(repoRoot, "workspace/generated/.generated.step.glb"), topologyGlb({
      sourceKind: "python",
      sourcePath: "workspace/generated/generated.py",
      sourceHash,
      stepHash,
      entryKind: "part",
    }));
    writeFile(path.join(repoRoot, "workspace/generated/helper.py"), "SIZE = 2\n");

    const catalog = scanCadDirectory({ repoRoot, rootDir: "workspace" });
    const entry = entryByFile(catalog, "generated/generated.step");

    assert.equal(entry.artifact, undefined);
    assert.equal(entry.sourceKind, "python");
  } finally {
    fs.rmSync(repoRoot, { recursive: true, force: true });
  }
});

test("scanCadDirectory keeps Python artifact current when STEP file hash matches", () => {
  const repoRoot = makeTempRepo();
  try {
    const stepHash = writeStep(path.join(repoRoot, "workspace/generated/generated.step"));
    const generatorPath = path.join(repoRoot, "workspace/generated/generated.py");
    writeFile(generatorPath, "def gen_step():\n    return None\n");
    const sourceHash = sha256Buffer(fs.readFileSync(generatorPath));
    writeFile(path.join(repoRoot, "workspace/generated/.generated.step.glb"), topologyGlb({
      sourceKind: "python",
      sourcePath: "workspace/generated/generated.py",
      sourceHash,
      stepHash,
      entryKind: "part",
    }));
    writeFile(generatorPath, "def gen_step():\n    return 'changed source, same STEP'\n");

    const catalog = scanCadDirectory({ repoRoot, rootDir: "workspace" });
    const entry = entryByFile(catalog, "generated/generated.step");

    assert.equal(entry.artifact, undefined);
    assert.equal(entry.sourceKind, "python");
  } finally {
    fs.rmSync(repoRoot, { recursive: true, force: true });
  }
});

test("readStepSourceStatus reports missing and current STEP files", () => {
  const repoRoot = makeTempRepo();
  try {
    const stepPath = path.join(repoRoot, "workspace/generated/generated.step");

    const missing = readStepSourceStatus({
      repoRoot,
      stepPath,
    });
    assert.equal(missing.ok, false);
    assert.equal(missing.sourceKind, "step");
    assert.equal(missing.step.status, "missing");

    const pythonMissing = readStepSourceStatus({
      repoRoot,
      stepPath,
      pythonSourcePath: path.join(repoRoot, "workspace/generated/generated.py"),
    });
    assert.equal(pythonMissing.ok, false);
    assert.equal(pythonMissing.sourceKind, "python");
    assert.equal(pythonMissing.sourcePath, "workspace/generated/generated.py");
    assert.equal(pythonMissing.step.status, "missing");

    writeStep(stepPath);
    const fresh = readStepSourceStatus({
      repoRoot,
      stepPath,
    });
    assert.equal(fresh.ok, true);
    assert.equal(fresh.step.status, "current");
  } finally {
    fs.rmSync(repoRoot, { recursive: true, force: true });
  }
});

test("scanCadDirectory preserves Python source kind when Python artifacts have topology errors", () => {
  const repoRoot = makeTempRepo();
  try {
    const stepHash = writeStep(path.join(repoRoot, "workspace/generated/generated.step"));
    writeFile(path.join(repoRoot, "workspace/sources/generated.py"), "def gen_step():\n    return None\n");
    const sourceHash = sha256Buffer(fs.readFileSync(path.join(repoRoot, "workspace/sources/generated.py")));
    writeFile(path.join(repoRoot, "workspace/generated/.generated.step.glb"), topologyGlb({
      sourceKind: "python",
      sourcePath: "workspace/sources/generated.py",
      sourceHash,
      stepHash,
      entryKind: "part",
    }, { displayEdges: false }));

    const catalog = scanCadDirectory({ repoRoot, rootDir: "workspace" });
    const entry = entryByFile(catalog, "generated/generated.step");

    assert.equal(entry.sourceKind, "python");
    assert.equal(entry.artifact.error, "missing_edge_topology");
    assert.equal(entry.artifact.sourceKind, "python");
  } finally {
    fs.rmSync(repoRoot, { recursive: true, force: true });
  }
});

test("scanCadDirectory keeps same-stem generator details out of catalog entries", () => {
  const repoRoot = makeTempRepo();
  const stepHash = writeStep(path.join(repoRoot, "workspace/raw/raw.step"));
  writeFile(path.join(repoRoot, "workspace/raw/raw.py"), "def gen_step():\n    return None\n");
  writeFile(path.join(repoRoot, "workspace/raw/.raw.step.glb"), topologyGlb({
    sourcePath: "workspace/raw/raw.step",
    stepHash,
    entryKind: "part",
  }));

  const catalog = scanCadDirectory({ repoRoot, rootDir: "workspace" });
  const entry = entryByFile(catalog, "raw/raw.step");

  assert.equal(entry.artifact, undefined);
  assert.equal(entry.sourceKind, "step");
  assert.ok(entry.url.startsWith("/workspace/raw/.raw.step.glb?v="));
  assert.equal(entry.hash.length, 64);
  assert.equal(entry.stepArtifact, undefined);
  assert.equal(entry.step, undefined);
});

test("scanCadDirectory ignores legacy STEP artifact folders and reports missing canonical GLB", () => {
  const repoRoot = makeTempRepo();
  const stepHash = writeStep(path.join(repoRoot, "workspace/sample_part/sample_part.step"));
  writeFile(path.join(repoRoot, "workspace/sample_part/.sample_part.step/model.glb"), topologyGlb({
    cadRef: "workspace/sample_part/sample_part",
    sourcePath: "workspace/sample_part/sample_part.step",
    stepHash,
    entryKind: "part",
    stats: { shapeCount: 1 },
  }));

  const catalog = scanCadDirectory({ repoRoot, rootDir: "workspace" });
  const entry = entryByFile(catalog, "sample_part/sample_part.step");

  assert.equal(entry.kind, "part");
  assertStepArtifactError(entry, "missing_glb");
  assert.equal(entry.url, "/workspace/sample_part/.sample_part.step.glb");
  assert.equal(entry.hash, "");
  assert.equal(entry.bytes, 0);
});

test("scanCadDirectory reports malformed canonical GLBs as missing STEP topology", () => {
  const repoRoot = makeTempRepo();
  writeStep(path.join(repoRoot, "workspace/sample_part/sample_part.step"));
  writeFile(path.join(repoRoot, "workspace/sample_part/.sample_part.step.glb"), "not a glb");

  const catalog = scanCadDirectory({ repoRoot, rootDir: "workspace" });
  const entry = entryByFile(catalog, "sample_part/sample_part.step");

  assertStepArtifactError(entry, "missing_step_topology");
});

test("scanCadDirectory reports old STEP_topology schema versions", () => {
  const repoRoot = makeTempRepo();
  const stepHash = writeStep(path.join(repoRoot, "workspace/sample_part/sample_part.step"));
  writeFile(path.join(repoRoot, "workspace/sample_part/.sample_part.step.glb"), topologyGlb({
    sourcePath: "workspace/sample_part/sample_part.step",
    stepHash,
    entryKind: "part",
  }, { extensionSchemaVersion: STEP_TOPOLOGY_SCHEMA_VERSION - 1 }));

  const catalog = scanCadDirectory({ repoRoot, rootDir: "workspace" });
  const entry = entryByFile(catalog, "sample_part/sample_part.step");

  assertStepArtifactError(entry, "unsupported_step_topology");
});

test("scanCadDirectory reports future STEP_topology schema versions", () => {
  const repoRoot = makeTempRepo();
  const stepHash = writeStep(path.join(repoRoot, "workspace/sample_part/sample_part.step"));
  writeFile(path.join(repoRoot, "workspace/sample_part/.sample_part.step.glb"), topologyGlb({
    sourcePath: "workspace/sample_part/sample_part.step",
    stepHash,
    entryKind: "part",
  }, { extensionSchemaVersion: STEP_TOPOLOGY_SCHEMA_VERSION + 1 }));

  const catalog = scanCadDirectory({ repoRoot, rootDir: "workspace" });
  const entry = entryByFile(catalog, "sample_part/sample_part.step");

  assertStepArtifactError(entry, "unsupported_step_topology");
});

test("scanCadDirectory reports stale STEP hashes recorded in GLB artifacts", () => {
  const repoRoot = makeTempRepo();
  const actualStepHash = writeStep(path.join(repoRoot, "workspace/sample_part/sample_part.step"));
  writeFile(path.join(repoRoot, "workspace/sample_part/.sample_part.step.glb"), topologyGlb({
    sourcePath: "workspace/sample_part/sample_part.step",
    stepHash: "step-hash-from-glb",
    entryKind: "part",
  }));

  const catalog = scanCadDirectory({ repoRoot, rootDir: "workspace" });
  const entry = entryByFile(catalog, "sample_part/sample_part.step");

  assert.notEqual(actualStepHash, "step-hash-from-glb");
  assert.equal(entry.artifact.ok, false);
  assert.equal(entry.artifact.error, "stale_step_artifact");
  assert.equal(entry.artifact.stale, true);
  assert.equal(entry.artifact.sourceKind, "step");
  assert.equal(entry.artifact.artifactHash, "step-hash-from-glb");
  assert.equal(entry.artifact.currentHash, actualStepHash);
  assert.equal(
    entry.artifact.message,
    "Generated GLB doesn't match the hash of the STEP file: workspace/sample_part/.sample_part.step.glb."
  );
  assert.ok(entry.url.startsWith("/workspace/sample_part/.sample_part.step.glb?v="));
  assert.equal(entry.hash.length, 64);
  assert.ok(entry.bytes > 0);
  assert.equal(entry.stepArtifact, undefined);
  assert.equal(entry.step, undefined);
});

test("scanCadDirectory preserves Python source kind for stale STEP GLB artifacts", () => {
  const repoRoot = makeTempRepo();
  const actualStepHash = writeStep(path.join(repoRoot, "workspace/generated/generated.step"));
  writeFile(path.join(repoRoot, "workspace/generated/generated.py"), "def gen_step():\n    return None\n");
  writeFile(path.join(repoRoot, "workspace/generated/.generated.step.glb"), topologyGlb({
    sourceKind: "python",
    sourcePath: "workspace/generated/generated.py",
    sourceHash: "old-python-source-hash",
    stepHash: "step-hash-from-glb",
    entryKind: "part",
  }));

  const catalog = scanCadDirectory({ repoRoot, rootDir: "workspace" });
  const entry = entryByFile(catalog, "generated/generated.step");

  assert.notEqual(actualStepHash, "step-hash-from-glb");
  assert.equal(entry.sourceKind, "python");
  assert.equal(entry.source.file, "workspace/generated/generated.py");
  assert.equal(entry.artifact.ok, false);
  assert.equal(entry.artifact.error, "stale_step_artifact");
  assert.equal(entry.artifact.sourceKind, "python");
});

test("scanCadDirectory accepts legacy STEP_topology CAD refs when the GLB is otherwise valid", () => {
  const repoRoot = makeTempRepo();
  const stepHash = writeStep(path.join(repoRoot, "workspace/sample_part/sample_part.step"));
  writeFile(path.join(repoRoot, "workspace/sample_part/.sample_part.step.glb"), topologyGlb({
    cadRef: "workspace/other_part",
    sourcePath: "workspace/sample_part/sample_part.step",
    stepHash,
    entryKind: "part",
  }));

  const catalog = scanCadDirectory({ repoRoot, rootDir: "workspace" });
  const entry = entryByFile(catalog, "sample_part/sample_part.step");

  assert.equal(entry.artifact, undefined);
  assert.ok(entry.url.startsWith("/workspace/sample_part/.sample_part.step.glb?v="));
  assert.equal(entry.hash.length, 64);
  assert.equal(entry.assets, undefined);
});

test("scanCadDirectory reports missing edge topology", () => {
  const repoRoot = makeTempRepo();
  const stepHash = writeStep(path.join(repoRoot, "workspace/sample_part/sample_part.step"));
  writeFile(path.join(repoRoot, "workspace/sample_part/.sample_part.step.glb"), topologyGlb({
    sourcePath: "workspace/sample_part/sample_part.step",
    stepHash,
    entryKind: "part",
  }, { displayEdges: false }));

  const catalog = scanCadDirectory({ repoRoot, rootDir: "workspace" });
  const entry = entryByFile(catalog, "sample_part/sample_part.step");

  assertStepArtifactError(entry, "missing_edge_topology");
});

test("isServedCadAsset allows hidden STEP runtime modules only by convention", () => {
  assert.equal(isServedCadAsset("/workspace/sample/.gearbox.step.js"), true);
  assert.equal(isServedCadAsset("/workspace/sample/.gearbox.stp.js"), false);
  assert.equal(isServedCadAsset("/workspace/sample/gearbox.step.js"), false);
  assert.equal(isServedCadAsset("/workspace/sample/gearbox.js"), false);
});

test("isCatalogRelevantPath watches Python generators without serving them", () => {
  assert.equal(isServedCadAsset(path.join("workspace", "generated", "part.py")), false);
  assert.equal(isCatalogRelevantPath(path.join("workspace", "generated", "part.py")), true);
  assert.equal(isCatalogRelevantPath(path.join("workspace", "__pycache__", "part.py")), false);
});

test("scanCadDirectory reports missing selector topology", () => {
  const repoRoot = makeTempRepo();
  const stepHash = writeStep(path.join(repoRoot, "workspace/sample_part/sample_part.step"));
  writeFile(path.join(repoRoot, "workspace/sample_part/.sample_part.step.glb"), topologyGlb({
    sourcePath: "workspace/sample_part/sample_part.step",
    stepHash,
    entryKind: "part",
  }, { selector: false }));

  const catalog = scanCadDirectory({ repoRoot, rootDir: "workspace" });
  const entry = entryByFile(catalog, "sample_part/sample_part.step");

  assertStepArtifactError(entry, "missing_selector_topology");
});

test("scanCadDirectory uses the requested root directory as the catalog root", () => {
  const repoRoot = makeTempRepo();
  writeFile(path.join(repoRoot, "workspace/imports/sample_part.step"), "ISO-10303-21;\nEND-ISO-10303-21;\n");

  const catalog = scanCadDirectory({ repoRoot, rootDir: "workspace/imports" });

  assert.equal(catalog.root, undefined);
  assert.deepEqual(catalog.entries.map((entry) => entry.file), ["sample_part.step"]);
});

test("scanCadDirectory can filter scan-root-relative files and directories", () => {
  const repoRoot = makeTempRepo();
  writeFile(path.join(repoRoot, "workspace/keep/sample_part.step"), "ISO-10303-21;\nEND-ISO-10303-21;\n");
  writeFile(path.join(repoRoot, "workspace/excluded/skipped_part.step"), "ISO-10303-21;\nEND-ISO-10303-21;\n");
  writeFile(path.join(repoRoot, "workspace/skipped_file.stl"), "solid skipped\nendsolid skipped\n");

  const visited = [];
  const catalog = scanCadDirectory({
    repoRoot,
    rootDir: "workspace",
    includePath: ({ relativePath, isDirectory }) => {
      visited.push(`${isDirectory ? "dir" : "file"}:${relativePath}`);
      return relativePath !== "excluded" && relativePath !== "skipped_file.stl";
    },
  });

  assert.deepEqual(catalog.entries.map((entry) => entry.file), ["keep/sample_part.step"]);
  assert.ok(!visited.includes("file:excluded/skipped_part.step"));
});

test("scanCadDirectory defaults to the workspace root without emitting root metadata", () => {
  const repoRoot = makeTempRepo();
  writeFile(path.join(repoRoot, "workspace/imports/sample_part.step"), "ISO-10303-21;\nEND-ISO-10303-21;\n");
  writeFile(path.join(repoRoot, ".agents/ignored.step"), "ISO-10303-21;\nEND-ISO-10303-21;\n");

  const catalog = scanCadDirectory({ repoRoot });

  assert.equal(catalog.root, undefined);
  assert.deepEqual(catalog.entries.map((entry) => entry.file), ["workspace/imports/sample_part.step"]);
});

test("normalizeViewerRootDir rejects traversal", () => {
  assert.equal(normalizeViewerRootDir(""), "");
  assert.equal(normalizeViewerRootDir("workspace/samples"), "workspace/samples");
  assert.equal(normalizeViewerRootDir("..workspace/samples"), "..workspace/samples");
  assert.throws(() => normalizeViewerRootDir("../workspace"), /inside the workspace/);
});

test("normalizeViewerRootDir preserves absolute paths", () => {
  assert.equal(normalizeViewerRootDir("/abs/path/exports"), "/abs/path/exports");
  assert.equal(normalizeViewerRootDir("/abs/path/exports/"), "/abs/path/exports");
  assert.equal(normalizeViewerRootDir("/"), "/");
});

test("resolveViewerRoot accepts an absolute path inside the workspace", () => {
  const repo = makeTempRepo();
  try {
    const absoluteDir = path.join(repo, "exports");
    fs.mkdirSync(absoluteDir, { recursive: true });
    const resolved = resolveViewerRoot(repo, absoluteDir);
    assert.equal(resolved.rootPath, path.resolve(absoluteDir));
    assert.equal(resolved.rootName, "exports");
  } finally {
    fs.rmSync(repo, { recursive: true, force: true });
  }
});

test("resolveViewerRoot accepts workspace child names beginning with two dots", () => {
  const repo = makeTempRepo();
  try {
    const rootDir = "..exports";
    const resolved = resolveViewerRoot(repo, rootDir);

    assert.equal(resolved.dir, rootDir);
    assert.equal(resolved.rootPath, path.join(repo, rootDir));
    assert.equal(resolved.rootName, rootDir);
  } finally {
    fs.rmSync(repo, { recursive: true, force: true });
  }
});

test("resolveViewerRoot rejects an absolute path outside the workspace", () => {
  const repo = makeTempRepo();
  try {
    assert.throws(
      () => resolveViewerRoot(repo, "/elsewhere/outside"),
      /inside the workspace/,
    );
  } finally {
    fs.rmSync(repo, { recursive: true, force: true });
  }
});

test("scanCadDirectory links SRDF metadata to URDF files whose names begin with two dots", () => {
  const repoRoot = makeTempRepo();
  try {
    writeFile(path.join(repoRoot, "..robot.urdf"), "<robot name=\"sample_robot\" />\n");
    writeFile(path.join(repoRoot, "sample_robot.srdf"), "<robot name=\"sample_robot\" xmlns:tcad=\"https://text-to-cad.dev/srdf\"><tcad:urdf path=\"..robot.urdf\"/></robot>\n");

    const catalog = scanCadDirectory({ repoRoot });

    assert.equal(entryByFile(catalog, "sample_robot.srdf").relations.urdf.file, "..robot.urdf");
  } finally {
    fs.rmSync(repoRoot, { recursive: true, force: true });
  }
});

test("isServedCadAsset does not serve hidden per-URDF directories", () => {
  assert.equal(isServedCadAsset(path.join("workspace", ".sample_robot.urdf", "metadata.json")), false);
  assert.equal(isServedCadAsset(path.join("workspace", ".sample_robot.urdf", "srdf", "metadata.json")), false);
  assert.equal(isServedCadAsset(path.join("workspace", ".sample_robot.urdf", "srdf", "moveit2_server.json")), false);
  assert.equal(isServedCadAsset(path.join("workspace", ".sample_robot.urdf", "ignored.urdf")), false);
  assert.equal(isServedCadAsset(path.join("workspace", ".sample_robot.urdf", "other.json")), false);
});

test("isServedCadAsset serves standalone 3MF entries", () => {
  assert.equal(isServedCadAsset(path.join("workspace", "meshes", "sample_part.3mf")), true);
});

test("isServedCadAsset serves standalone native GLB entries", () => {
  assert.equal(isServedCadAsset(path.join("workspace", "meshes", "sample_part.glb")), true);
});

test("isServedCadAsset serves standalone SDF entries", () => {
  assert.equal(isServedCadAsset(path.join("workspace", "robots", "sample_robot.sdf")), true);
});

test("isServedCadAsset serves inline GLBs and ignores legacy STEP artifact files", () => {
  assert.equal(isServedCadAsset(path.join("workspace", ".sample_part.step.glb")), true);
  assert.equal(isServedCadAsset(path.join("workspace", ".sample_part.step", "model.glb")), false);
  assert.equal(isServedCadAsset(path.join("workspace", ".sample_part.step", "topology.json")), false);
  assert.equal(isServedCadAsset(path.join("workspace", ".sample_part.step", "topology.bin")), false);
  assert.equal(isServedCadAsset(path.join("workspace", ".sample_part.step", "other.json")), false);
});

test("isServedCadAsset does not expose workspace-local JavaScript files", () => {
  assert.equal(isServedCadAsset(path.join("workspace", "sample_robot.js")), false);
});
