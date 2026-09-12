import test from "node:test";
import assert from "node:assert/strict";
import {
  applyTopologyDisplayEdgeSurfaceOffset,
  displayEdgeRuntimeWithSelectorVisibilityClasses,
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

function displayEdgeRuntime() {
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

test("resolveTopologyDisplayEdgeRuntimes prefers transformed display edges", () => {
  const baseRuntime = displayEdgeRuntime();
  const resolved = resolveTopologyDisplayEdgeRuntimes({
    displayEdgeRuntime: baseRuntime,
    selectorRuntime: { proxy: {} },
    displayRecords: [{ partId: "part-a", effectMatrix: TRANSLATE_2_3_4 }]
  });
  assert.equal(resolved.transformCount, 1);
  assert.equal(resolved.topologyRuntime, resolved.displayEdgeRuntime);
  assert.notEqual(resolved.displayEdgeRuntime, baseRuntime);
  assert.deepEqual([...resolved.displayEdgeRuntime.proxy.edgePositions], [2, 3, 4, 3, 3, 4]);
});

test("resolveTopologyDisplayEdgeRuntimes reuses stable transformed runtimes", () => {
  const baseDisplayRuntime = displayEdgeRuntime();
  const baseSelectorRuntime = {
    edges: [{ occurrenceId: "part-a" }],
    proxy: {}
  };
  const first = resolveTopologyDisplayEdgeRuntimes({
    displayEdgeRuntime: baseDisplayRuntime,
    selectorRuntime: baseSelectorRuntime,
    displayRecords: [{ partId: "part-a", effectMatrix: TRANSLATE_2_3_4 }]
  });
  const second = resolveTopologyDisplayEdgeRuntimes({
    displayEdgeRuntime: baseDisplayRuntime,
    selectorRuntime: baseSelectorRuntime,
    displayRecords: [{
      partId: "part-a",
      effectMatrix: { elements: [...TRANSLATE_2_3_4.elements] }
    }]
  });
  const changed = resolveTopologyDisplayEdgeRuntimes({
    displayEdgeRuntime: baseDisplayRuntime,
    selectorRuntime: baseSelectorRuntime,
    displayRecords: [{ partId: "part-a", effectMatrix: TRANSLATE_3_4_5 }]
  });

  assert.equal(second.transformedSelectorRuntime, first.transformedSelectorRuntime);
  assert.equal(second.transformedDisplayEdgeRuntime, first.transformedDisplayEdgeRuntime);
  assert.notEqual(changed.transformedSelectorRuntime, first.transformedSelectorRuntime);
  assert.notEqual(changed.transformedDisplayEdgeRuntime, first.transformedDisplayEdgeRuntime);
});

test("resolveTopologyDisplayEdgeRuntimes can skip transformed display edges for record-driven overlays", () => {
  const baseRuntime = displayEdgeRuntime();
  const resolved = resolveTopologyDisplayEdgeRuntimes({
    displayEdgeRuntime: baseRuntime,
    selectorRuntime: { proxy: {} },
    displayRecords: [{ partId: "part-a", effectMatrix: TRANSLATE_2_3_4 }],
    transformDisplayEdges: false
  });

  assert.equal(resolved.transformCount, 1);
  assert.equal(resolved.displayEdgeRuntime, baseRuntime);
  assert.equal(resolved.transformedDisplayEdgeRuntime, null);
});

test("display edge runtimes inherit selector visibility classes when compact payloads omit them", () => {
  const displayRuntime = {
    edges: [
      { occurrenceId: "o1", segmentStart: 0, segmentCount: 1 },
      { occurrenceId: "o1", segmentStart: 1, segmentCount: 2 }
    ],
    proxy: {}
  };
  const selectorRuntime = {
    edges: [
      { id: "o1.e1", visibilityClass: "feature" },
      { id: "o1.e2", visibilityClass: "tangent" }
    ],
    proxy: {}
  };

  const enriched = displayEdgeRuntimeWithSelectorVisibilityClasses(displayRuntime, selectorRuntime);
  const enrichedAgain = displayEdgeRuntimeWithSelectorVisibilityClasses(displayRuntime, selectorRuntime);
  assert.notEqual(enriched, displayRuntime);
  assert.equal(enrichedAgain, enriched);
  assert.deepEqual(enriched.edges, [
    { occurrenceId: "o1", segmentStart: 0, segmentCount: 1, visibilityClass: "feature" },
    { occurrenceId: "o1", segmentStart: 1, segmentCount: 2, visibilityClass: "tangent" }
  ]);

  const resolved = resolveTopologyDisplayEdgeRuntimes({
    displayEdgeRuntime: displayRuntime,
    selectorRuntime
  });
  assert.deepEqual(resolved.displayEdgeRuntime.edges, enriched.edges);
});

test("shouldRenderTopologyDisplayEdges gates CAD topology overlays", () => {
  const runtime = displayEdgeRuntime();
  assert.equal(shouldRenderTopologyDisplayEdges({
    edgesVisible: true,
    cadEdgeSource: true,
    displayEdgeRuntime: runtime
  }), true);
  assert.equal(shouldRenderTopologyDisplayEdges({
    edgesVisible: true,
    wireframeMode: true,
    cadEdgeSource: true,
    displayEdgeRuntime: runtime
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
