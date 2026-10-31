import assert from "node:assert/strict";
import test from "node:test";

import {
  entryAssetHash,
  entryAssetUrl,
  entryMeshAssetHash,
  entryMeshAssetUrl,
  entryUrdfAssetHash
} from "./entryAssets.js";

function stepEntry(overrides = {}) {
  return {
    file: "parts/bracket.step",
    kind: "part",
    url: "/assets/bracket.glb",
    hash: "glb-hash",
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
  assert.equal(entryAssetUrl(entry, "missing"), "");
  assert.equal(entryAssetHash(null, "glb"), "");
});

test("a mesh file's asset is its own", () => {
  assert.equal(entryMeshAssetHash({ kind: "stl", url: "/mesh.stl", hash: "stl-hash" }), "stl-hash");
});

test("a robot's signature is its description's, and an SRDF's its URDF's too", () => {
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

test("a DXF entry's render asset is its own file", () => {
  // Nothing bakes a drawing: the entry's url IS the asset, and no glb relation
  // exists for it. What the DXF pane draws is the server's flattened payload for
  // that same file (GET /__cad/drawing).
  const dxf = { file: "parts/bracket.dxf", kind: "dxf", url: "/__cad/asset?file=%2Fx%2Fbracket.dxf&v=1", hash: "h1" };
  assert.equal(entryMeshAssetUrl(dxf), dxf.url);
  assert.equal(entryMeshAssetHash(dxf), "h1");
  // An unbuilt generated drawing has no asset yet.
  assert.equal(entryMeshAssetUrl({ file: "parts/outline.dxf.py", kind: "dxf", url: "" }), "");
});
