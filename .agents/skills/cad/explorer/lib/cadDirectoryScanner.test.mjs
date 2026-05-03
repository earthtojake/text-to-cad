import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import {
  isServedCadAsset,
  normalizeExplorerRootDir,
  resolveExplorerRoot,
  scanCadDirectory,
} from "./cadDirectoryScanner.mjs";

function makeTempRepo() {
  return fs.mkdtempSync(path.join(os.tmpdir(), "cad-explorer-scan-"));
}

function writeFile(filePath, content = "") {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, content);
}

function entryByFile(catalog, file) {
  return catalog.entries.find((entry) => entry.file === file);
}

test("scanCadDirectory discovers CAD files directly and infers STEP assets", () => {
  const repoRoot = makeTempRepo();
  writeFile(path.join(repoRoot, "workspace/sample_part/sample_part.step"), "ISO-10303-21;\nEND-ISO-10303-21;\n");
  writeFile(path.join(repoRoot, "workspace/sample_part/.sample_part.step/model.glb"), "glb");
  writeFile(path.join(repoRoot, "workspace/sample_part/.sample_part.step/topology.json"), JSON.stringify({
    schemaVersion: 2,
    assembly: { root: { nodeType: "assembly" } },
  }));
  writeFile(path.join(repoRoot, "workspace/sample_part/.sample_part.step/topology.bin"), "bin");
  writeFile(path.join(repoRoot, "workspace/sample_part/.sample_part.step/ignored.step"), "ignored\n");
  writeFile(path.join(repoRoot, "workspace/sample_part/sample_part.stl"), "solid sample_part\nendsolid sample_part\n");
  writeFile(path.join(repoRoot, "workspace/sample_part/sample_part.3mf"), "3mf\n");
  writeFile(path.join(repoRoot, "workspace/sheets/bracket.dxf"), "0\nEOF\n");
  writeFile(path.join(repoRoot, "workspace/robots/sample_robot.urdf"), "<robot name=\"sample_robot\" />\n");
  writeFile(path.join(repoRoot, "workspace/robots/.sample_robot.urdf/explorer.json"), JSON.stringify({
    schemaVersion: 3,
    kind: "texttocad-urdf-explorer",
    poses: []
  }));
  writeFile(path.join(repoRoot, "workspace/robots/.sample_robot.urdf/robot-motion/explorer.json"), JSON.stringify({
    schemaVersion: 1,
    kind: "texttocad-robot-motion-explorer",
    motionServer: {
      version: 1,
      commands: {
        "urdf.solvePose": {
          endEffectors: []
        }
      }
    }
  }));
  writeFile(path.join(repoRoot, "workspace/robots/.sample_robot.urdf/ignored.urdf"), "<robot name=\"ignored\" />\n");
  writeFile(path.join(repoRoot, "workspace/sample_part/sample_part.py"), "print('ignored')\n");
  writeFile(path.join(repoRoot, "workspace/.hidden/hidden.step"), "ISO-10303-21;\nEND-ISO-10303-21;\n");

  const catalog = scanCadDirectory({ repoRoot, rootDir: "workspace" });

  assert.equal(catalog.root.dir, "workspace");
  assert.equal(entryByFile(catalog, "sample_part/sample_part.step").kind, "assembly");
  assert.equal(entryByFile(catalog, "sample_part/sample_part.step").cadPath, "workspace/sample_part/sample_part");
  assert.ok(entryByFile(catalog, "sample_part/sample_part.step").assets.glb.url.startsWith("/workspace/sample_part/.sample_part.step/model.glb?v="));
  assert.ok(entryByFile(catalog, "sample_part/sample_part.step").assets.topologyBinary.hash);
  assert.equal(entryByFile(catalog, "sample_part/sample_part.stl").kind, "stl");
  assert.equal(entryByFile(catalog, "sample_part/sample_part.3mf").kind, "3mf");
  assert.equal(entryByFile(catalog, "sheets/bracket.dxf").kind, "dxf");
  assert.equal(entryByFile(catalog, "robots/sample_robot.urdf").kind, "urdf");
  assert.ok(entryByFile(catalog, "robots/sample_robot.urdf").assets.explorerMetadata.url.startsWith("/workspace/robots/.sample_robot.urdf/explorer.json?v="));
  assert.ok(entryByFile(catalog, "robots/sample_robot.urdf").assets.motionExplorerMetadata.url.startsWith("/workspace/robots/.sample_robot.urdf/robot-motion/explorer.json?v="));
  assert.equal(entryByFile(catalog, "sample_part/sample_part.py"), undefined);
  assert.equal(entryByFile(catalog, "sample_part/.sample_part.step/ignored.step"), undefined);
  assert.equal(entryByFile(catalog, "robots/.sample_robot.urdf/ignored.urdf"), undefined);
  assert.equal(entryByFile(catalog, ".hidden/hidden.step"), undefined);
});

test("scanCadDirectory uses the requested root directory as the displayed root", () => {
  const repoRoot = makeTempRepo();
  writeFile(path.join(repoRoot, "workspace/imports/sample_part.step"), "ISO-10303-21;\nEND-ISO-10303-21;\n");

  const catalog = scanCadDirectory({ repoRoot, rootDir: "workspace/imports" });

  assert.equal(catalog.root.dir, "workspace/imports");
  assert.equal(catalog.root.name, "imports");
  assert.deepEqual(catalog.entries.map((entry) => entry.file), ["sample_part.step"]);
});

test("scanCadDirectory defaults to the workspace root", () => {
  const repoRoot = makeTempRepo();
  writeFile(path.join(repoRoot, "workspace/imports/sample_part.step"), "ISO-10303-21;\nEND-ISO-10303-21;\n");
  writeFile(path.join(repoRoot, ".agents/ignored.step"), "ISO-10303-21;\nEND-ISO-10303-21;\n");

  const catalog = scanCadDirectory({ repoRoot });

  assert.equal(catalog.root.dir, "");
  assert.equal(catalog.root.name, path.basename(repoRoot));
  assert.deepEqual(catalog.entries.map((entry) => entry.file), ["workspace/imports/sample_part.step"]);
});

test("normalizeExplorerRootDir rejects traversal", () => {
  assert.equal(normalizeExplorerRootDir(""), "");
  assert.equal(normalizeExplorerRootDir("workspace/samples"), "workspace/samples");
  assert.throws(() => normalizeExplorerRootDir("../workspace"), /inside the workspace/);
});

test("normalizeExplorerRootDir preserves absolute paths", () => {
  // Previously the leading slash was stripped, which silently turned an
  // absolute EXPLORER_ROOT_DIR into a workspace-relative join onto a
  // nonsense path. Now the leading slash flows through to resolveExplorerRoot.
  assert.equal(normalizeExplorerRootDir("/abs/path/exports"), "/abs/path/exports");
  assert.equal(normalizeExplorerRootDir("/abs/path/exports/"), "/abs/path/exports");
});

test("resolveExplorerRoot accepts an absolute path inside the workspace", () => {
  const repo = makeTempRepo();
  try {
    const absoluteDir = path.join(repo, "exports");
    fs.mkdirSync(absoluteDir, { recursive: true });
    const resolved = resolveExplorerRoot(repo, absoluteDir);
    assert.equal(resolved.rootPath, path.resolve(absoluteDir));
    assert.equal(resolved.rootName, "exports");
  } finally {
    fs.rmSync(repo, { recursive: true, force: true });
  }
});

test("resolveExplorerRoot rejects an absolute path outside the workspace", () => {
  const repo = makeTempRepo();
  try {
    assert.throws(
      () => resolveExplorerRoot(repo, "/elsewhere/outside"),
      /inside the workspace/,
    );
  } finally {
    fs.rmSync(repo, { recursive: true, force: true });
  }
});

test("isServedCadAsset allows only explorer.json inside URDF sidecar directories", () => {
  assert.equal(isServedCadAsset(path.join("workspace", ".sample_robot.urdf", "explorer.json")), true);
  assert.equal(isServedCadAsset(path.join("workspace", ".sample_robot.urdf", "robot-motion", "explorer.json")), true);
  assert.equal(isServedCadAsset(path.join("workspace", ".sample_robot.urdf", "robot-motion", "motion_server.json")), false);
  assert.equal(isServedCadAsset(path.join("workspace", ".sample_robot.urdf", "ignored.urdf")), false);
  assert.equal(isServedCadAsset(path.join("workspace", ".sample_robot.urdf", "other.json")), false);
});

test("isServedCadAsset serves standalone 3MF entries", () => {
  assert.equal(isServedCadAsset(path.join("workspace", "meshes", "sample_part.3mf")), true);
});

test("isServedCadAsset does not expose workspace-local JavaScript files", () => {
  assert.equal(isServedCadAsset(path.join("workspace", "sample_robot.js")), false);
});
