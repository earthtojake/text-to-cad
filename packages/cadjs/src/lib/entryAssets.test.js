import assert from "node:assert/strict";
import test from "node:test";

import {
  entryAssetHash,
  entryAssetBytes,
  entryAssetUrl,
  entryHasDxf,
  entryHasDisplayEdges,
  entryHasMesh,
  entryHasReferences,
  entryHasUrdf,
  entryMeshAssetBytes,
  entryMeshAssetHash,
  entryMeshAssetSignature,
  entryMeshAssetUrl,
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
  assert.equal(entryHasUrdf({ kind: "urdf", url: "/robot.urdf", hash: "urdf-hash" }), true);
  assert.equal(entryHasUrdf({ kind: "sdf", url: "/robot.sdf", hash: "sdf-hash" }), true);
});

function packagedEntry(kind, file, glbFile) {
  // What the scanner publishes for a kind whose geometry is baked into a __cadgen__ render
  // package: the entry keeps its own source/exchange file as `url`, and the package's mesh
  // arrives as a `glb` relation.
  return {
    file,
    kind,
    url: `/assets/${file}`,
    hash: "source-hash",
    relations: {
      glb: { file: glbFile, url: `/assets/${glbFile}`, hash: "baked-hash", bytes: 2048 }
    }
  };
}

test("a DXF or implicit entry resolves its mesh from the render package", () => {
  const dxf = packagedEntry("dxf", "plate.dxf", "__cadgen__/models/plate.dxf/preview.glb");
  const implicit = packagedEntry("implicit", "orb.implicit.js", "__cadgen__/models/orb.implicit.js/model.glb");
  for (const entry of [dxf, implicit]) {
    assert.equal(entryMeshAssetUrl(entry), `/assets/${entry.relations.glb.file}`);
    assert.equal(entryMeshAssetHash(entry), "baked-hash");
    assert.equal(entryMeshAssetBytes(entry), 2048);
    assert.equal(entryHasMesh(entry), true);
  }
  // The entry's own file stays reachable under its native key — Export and the file
  // metadata are about the DXF, not about the mesh baked from it.
  assert.equal(entryAssetUrl(dxf, "dxf"), "/assets/plate.dxf");
  assert.equal(entryHasDxf(dxf), true);
});

test("an unbuilt package leaves the entry with no mesh at all", () => {
  // No silent fall back to parsing the source in the browser: with no package the entry has
  // no mesh, and the artifact state machine reports needs-build.
  const dxf = { file: "plate.dxf", kind: "dxf", url: "/assets/plate.dxf", hash: "source-hash" };
  assert.equal(entryMeshAssetUrl(dxf), "");
  assert.equal(entryHasMesh(dxf), false);
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
