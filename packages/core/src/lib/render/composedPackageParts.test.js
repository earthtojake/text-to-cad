import assert from "node:assert/strict";
import { test } from "node:test";

import { resolvePartsToRender } from "../../common/cadScene.js";

// A composed (component-GLB) package stores each unique component's geometry in the
// component's OWN frame; placement lives only in the per-occurrence transform. Dropping
// to the whole-mesh fallback therefore draws every shared component once at the origin.
const composedMeshData = {
  partTransformsBaked: false,
  parts: [
    { id: "o1.7.1", vertexCount: 300, triangleCount: 100, transform: [1, 0, 0, 1350, 0, 1, 0, 850, 0, 0, 1, 366, 0, 0, 0, 1] },
    { id: "o1.7.2", vertexCount: 300, triangleCount: 100, transform: [1, 0, 0, 1350, 0, 1, 0, -850, 0, 0, 1, 366, 0, 0, 0, 1] }
  ]
};

// A legacy package bakes placement into its vertices, so the merged whole-mesh really is
// world-space and the fallback is valid.
const bakedMeshData = {
  partTransformsBaked: true,
  parts: [
    { id: "o1.1", vertexCount: 300, triangleCount: 100 },
    { id: "o1.2", vertexCount: 300, triangleCount: 100 }
  ]
};

const plainTheme = { materials: {} };

test("composed packages keep per-part rendering when parts are not rendered individually", () => {
  // This is the regression: with the STEP parameter module disabled the viewer asks for
  // merged rendering, and returning [] here lost every occurrence transform.
  const parts = resolvePartsToRender(composedMeshData, plainTheme, {
    renderPartsIndividually: false
  });
  assert.equal(parts.length, 2, "composed package must still render its occurrences");
  assert.deepEqual(parts.map((part) => part.id), ["o1.7.1", "o1.7.2"]);
});

test("composed packages keep per-part rendering with no pickable parts and no colours", () => {
  const parts = resolvePartsToRender(composedMeshData, plainTheme, {
    renderPartsIndividually: false,
    pickableParts: []
  });
  assert.equal(parts.length, 2);
});

test("baked packages may still fall back to the merged whole mesh", () => {
  const parts = resolvePartsToRender(bakedMeshData, plainTheme, {
    renderPartsIndividually: false
  });
  assert.equal(parts.length, 0, "baked geometry is world-space, so the fallback is valid");
});

test("individual rendering is unchanged for both package kinds", () => {
  assert.equal(
    resolvePartsToRender(composedMeshData, plainTheme, { renderPartsIndividually: true }).length,
    2
  );
  assert.equal(
    resolvePartsToRender(bakedMeshData, plainTheme, { renderPartsIndividually: true }).length,
    2
  );
});
