import test from "node:test";
import assert from "node:assert/strict";
import {
  applyTopologyDisplayEdgeSurfaceOffset,
  explodedPickSelectorRuntime,
  resolveTopologyDisplayEdgeRuntimes,
  rowMajorArrayFromMatrix4,
  selectorTransformsFromDisplayRecords,
  shouldRenderTopologyDisplayEdges,
  topologyDisplayEdgeSurfaceOffsetForSettings
} from "./topologyDisplayEdgeRuntime.js";

const TRANSLATE_2_3_4 = Object.freeze({
  elements: [
    1, 0, 0, 0,
    0, 1, 0, 0,
    0, 0, 1, 0,
    2, 3, 4, 1
  ]
});

const TRANSLATE_3_4_5 = Object.freeze({
  elements: [
    1, 0, 0, 0,
    0, 1, 0, 0,
    0, 0, 1, 0,
    3, 4, 5, 1
  ]
});

function edgeRuntime() {
  return {
    edges: [{ occurrenceId: "part-a" }],
    proxy: {
      edgePositions: new Float32Array([0, 0, 0, 1, 0, 0]),
      edgeIndices: new Uint32Array([0, 1]),
      edgeIds: new Uint32Array([0])
    }
  };
}

test("rowMajorArrayFromMatrix4 converts Three.js matrix storage", () => {
  assert.deepEqual(rowMajorArrayFromMatrix4(TRANSLATE_2_3_4), [
    1, 0, 0, 2,
    0, 1, 0, 3,
    0, 0, 1, 4,
    0, 0, 0, 1
  ]);
});

test("selectorTransformsFromDisplayRecords reads part effect transforms", () => {
  const transforms = selectorTransformsFromDisplayRecords([
    { partId: "part-a", effectMatrix: TRANSLATE_2_3_4 },
    { partId: "identity", effectMatrix: { elements: [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1] } }
  ]);
  assert.equal(transforms.size, 1);
  assert.deepEqual(transforms.get("part-a"), [
    1, 0, 0, 2,
    0, 1, 0, 3,
    0, 0, 1, 4,
    0, 0, 0, 1
  ]);
});

test("resolveTopologyDisplayEdgeRuntimes draws the line from the selector runtime as the records place it", () => {
  const baseRuntime = edgeRuntime();
  const resolved = resolveTopologyDisplayEdgeRuntimes({
    selectorRuntime: baseRuntime,
    displayRecords: [{ partId: "part-a", effectMatrix: TRANSLATE_2_3_4 }]
  });
  assert.equal(resolved.transformCount, 1);
  assert.equal(resolved.selectorRuntime, resolved.transformedSelectorRuntime);
  assert.notEqual(resolved.selectorRuntime, baseRuntime);
  assert.deepEqual([...resolved.selectorRuntime.proxy.edgePositions], [2, 3, 4, 3, 3, 4]);
  // Nothing moved: the runtime as given.
  assert.equal(resolveTopologyDisplayEdgeRuntimes({ selectorRuntime: baseRuntime, displayRecords: [] }).selectorRuntime, baseRuntime);
});

test("resolveTopologyDisplayEdgeRuntimes reuses stable transformed runtimes", () => {
  const baseSelectorRuntime = {
    edges: [{ occurrenceId: "part-a" }],
    proxy: {}
  };
  const first = resolveTopologyDisplayEdgeRuntimes({
    selectorRuntime: baseSelectorRuntime,
    displayRecords: [{ partId: "part-a", effectMatrix: TRANSLATE_2_3_4 }]
  });
  const second = resolveTopologyDisplayEdgeRuntimes({
    selectorRuntime: baseSelectorRuntime,
    displayRecords: [{
      partId: "part-a",
      effectMatrix: { elements: [...TRANSLATE_2_3_4.elements] }
    }]
  });
  const changed = resolveTopologyDisplayEdgeRuntimes({
    selectorRuntime: baseSelectorRuntime,
    displayRecords: [{ partId: "part-a", effectMatrix: TRANSLATE_3_4_5 }]
  });

  assert.equal(second.transformedSelectorRuntime, first.transformedSelectorRuntime);
  assert.notEqual(changed.transformedSelectorRuntime, first.transformedSelectorRuntime);
});

test("shouldRenderTopologyDisplayEdges gates CAD topology overlays", () => {
  const runtime = edgeRuntime();
  assert.equal(shouldRenderTopologyDisplayEdges({
    edgesVisible: true,
    cadEdgeSource: true,
    selectorRuntime: runtime
  }), true);
  assert.equal(shouldRenderTopologyDisplayEdges({
    edgesVisible: true,
    wireframeMode: true,
    cadEdgeSource: true,
    selectorRuntime: runtime
  }), false);
  assert.equal(shouldRenderTopologyDisplayEdges({
    edgesVisible: true,
    cadEdgeSource: true,
    selectorRuntime: { surfaceEdgeRendering: true, edges: [] }
  }), false);
});

test("surface offset scales for thick topology display edges", () => {
  const material = {};
  applyTopologyDisplayEdgeSurfaceOffset([{ material }], { thickness: 6 });

  assert.equal(topologyDisplayEdgeSurfaceOffsetForSettings({ thickness: 1 }), 0);
  assert.equal(topologyDisplayEdgeSurfaceOffsetForSettings({ thickness: 6 }), 0);
  assert.equal(material.polygonOffset, false);
  assert.equal(material.polygonOffsetFactor, 0);
  assert.equal(material.polygonOffsetUnits, 0);
  assert.equal(material.needsUpdate, true);
});

test("picking while exploded composes each part's explode offset over its effect", () => {
  const records = [
    { partId: "posed-and-exploded", effectMatrix: TRANSLATE_2_3_4, explodedViewMatrix: TRANSLATE_3_4_5 },
    { partId: "exploded-only", explodedViewMatrix: TRANSLATE_3_4_5 }
  ];
  // Highlights and edges keep reading the effect alone.
  const effectOnly = selectorTransformsFromDisplayRecords(records);
  assert.deepEqual([...effectOnly.keys()], ["posed-and-exploded"]);
  const picking = selectorTransformsFromDisplayRecords(records, { includeExplode: true });
  assert.deepEqual(picking.get("posed-and-exploded").filter((_, index) => index % 4 === 3), [5, 7, 9, 1]);
  assert.deepEqual(picking.get("exploded-only").filter((_, index) => index % 4 === 3), [3, 4, 5, 1]);
  // Nothing exploded: the caller's own runtime stands.
  assert.equal(explodedPickSelectorRuntime({ proxy: {} }, [{ partId: "a", effectMatrix: TRANSLATE_2_3_4 }]), null);
  assert.equal(explodedPickSelectorRuntime(null, records), null);
});
