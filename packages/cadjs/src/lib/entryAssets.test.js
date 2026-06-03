import assert from "node:assert/strict";
import test from "node:test";

import {
  entryAssetHash,
  entryAssetBytes,
  entryAssetUrl,
  entryHasDxf,
  entryHasGcode,
  entryHasDisplayEdges,
  entryHasMesh,
  entryHasReferences,
  entryHasUrdf,
  entryMeshAssetBytes,
  entryMeshAssetHash,
  entryMeshAssetSignature,
  entryReferenceAssetSignature,
  entryDisplayEdgeTopologyAssetUrl,
  entrySelectorTopologyAssetUrl,
  entryTopologyAssetUrl,
  entryStepModuleUrl,
  entryUrdfAssetHash
} from "./entryAssets.js";

function stepEntry(overrides = {}) {
  return {
    file: "parts/bracket.step",
    kind: "part",
    url: "/assets/bracket.glb",
    hash: "glb-hash",
    bytes: 42,
    ...overrides
  };
}

test("entry asset helpers normalize urls and hashes", () => {
  const entry = stepEntry({
    url: " /mesh.glb ",
    hash: " hash-a "
  });

  assert.equal(entryAssetUrl(entry, "glb"), "/mesh.glb");
  assert.equal(entryAssetHash(entry, "glb"), "hash-a");
  assert.equal(entryAssetBytes(stepEntry(), "glb"), 42);
  assert.equal(entryMeshAssetBytes(stepEntry()), 42);
  assert.equal(entryAssetUrl(entry, "missing"), "");
  assert.equal(entryAssetHash(null, "glb"), "");
  assert.equal(entryAssetBytes(null, "glb"), 0);
});

test("entry mesh signatures distinguish assemblies from simple mesh sidecars", () => {
  assert.equal(entryMeshAssetHash(stepEntry()), "glb-hash");
  assert.equal(entryMeshAssetSignature(stepEntry()), "glb-hash");
  assert.equal(entryMeshAssetSignature(stepEntry({ kind: "assembly" })), "glb-hash");
  assert.equal(entryMeshAssetHash({
    kind: "stl",
    url: "/mesh.stl",
    hash: "stl-hash"
  }), "stl-hash");
});

test("entry topology urls resolve to the primary STEP GLB", () => {
  assert.equal(entrySelectorTopologyAssetUrl(stepEntry()), "/assets/bracket.glb");
  assert.equal(entryDisplayEdgeTopologyAssetUrl(stepEntry()), "/assets/bracket.glb");
  assert.equal(entryTopologyAssetUrl(stepEntry()), "/assets/bracket.glb");
});

test("STEP module urls are explicit catalog data instead of guessed sidecars", () => {
  assert.equal(entryStepModuleUrl(stepEntry()), "");
  assert.equal(entryStepModuleUrl(stepEntry({ moduleUrl: " /assets/.bracket.step.js " })), "/assets/.bracket.step.js");
  assert.equal(entryStepModuleUrl({ kind: "stl", moduleUrl: "/assets/not-step.js" }), "");
});

test("entry availability helpers preserve existing viewer gates", () => {
  assert.equal(entryHasMesh(stepEntry()), true);
  assert.equal(entryHasReferences(stepEntry()), true);
  assert.equal(entryHasDisplayEdges(stepEntry()), true);
  assert.equal(entryHasMesh(stepEntry({ artifact: { ok: false } })), true);
  assert.equal(entryHasReferences(stepEntry({ artifact: { ok: false } })), true);
  assert.equal(entryHasDisplayEdges(stepEntry({ artifact: { ok: false } })), true);
  assert.equal(entryHasDisplayEdges(stepEntry({ hash: "" })), false);
  assert.equal(entryHasReferences(stepEntry({ hash: "" })), false);
  assert.equal(entryHasDxf({ kind: "dxf", url: "/plate.dxf", hash: "dxf-hash" }), true);
  assert.equal(entryHasGcode({ kind: "gcode", url: "/part.gcode", hash: "gcode-hash" }), true);
  assert.equal(entryHasUrdf({ kind: "urdf", url: "/robot.urdf", hash: "urdf-hash" }), true);
  assert.equal(entryHasUrdf({ kind: "sdf", url: "/robot.sdf", hash: "sdf-hash" }), true);
});

test("robot and reference signatures match persisted session expectations", () => {
  assert.equal(entryReferenceAssetSignature(stepEntry()), "glb-hash");
  assert.equal(entryUrdfAssetHash({
    kind: "srdf",
    url: "/robot.srdf",
    hash: "srdf-hash",
    relations: {
      urdf: { url: "/robot.urdf", hash: "urdf-hash" }
    }
  }), "urdf-hash:srdf-hash");
  assert.equal(entryUrdfAssetHash({
    kind: "sdf",
    url: "/robot.sdf",
    hash: "sdf-hash"
  }), "sdf-hash");
});
