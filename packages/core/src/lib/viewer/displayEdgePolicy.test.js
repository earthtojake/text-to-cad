import assert from "node:assert/strict";
import { test } from "node:test";
import {
  DERIVED_DISPLAY_EDGE_TRIANGLE_LIMIT,
  shouldBuildDerivedDisplayEdges,
  shouldShowRecordDisplayEdges
} from "./displayEdgePolicy.js";

test("display edge policy derives edges for explicit edge index buffers", () => {
  assert.equal(shouldBuildDerivedDisplayEdges({
    edge_indices: new Uint32Array([0, 1])
  }, { triangleLimit: 0 }), true);
});

test("display edge policy limits derived edges for large triangle meshes", () => {
  assert.equal(shouldBuildDerivedDisplayEdges({
    indices: new Uint32Array([0, 1, 2, 0, 2, 3])
  }, { triangleLimit: 2 }), true);
  assert.equal(shouldBuildDerivedDisplayEdges({
    indices: new Uint32Array([0, 1, 2, 0, 2, 3, 0, 3, 4])
  }, { triangleLimit: 2 }), false);
  assert.equal(DERIVED_DISPLAY_EDGE_TRIANGLE_LIMIT, 500000);
});

test("display edge policy avoids duplicate record edges when CAD topology edges are active", () => {
  assert.equal(shouldShowRecordDisplayEdges({
    edgesVisible: true,
    topologyDisplayEdgesVisible: true,
    displayEdgesVisible: true
  }), false);
  assert.equal(shouldShowRecordDisplayEdges({
    edgesVisible: true,
    topologyDisplayEdgesVisible: false,
    displayEdgesVisible: true
  }), true);
  assert.equal(shouldShowRecordDisplayEdges({
    edgesVisible: true,
    topologyDisplayEdgesVisible: false,
    wireframeMode: true
  }), true);
});
