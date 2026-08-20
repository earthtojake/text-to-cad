import assert from "node:assert/strict";
import { test } from "node:test";

import { VIEWER_PICK_MODE } from "./constants.js";
import { resolveScenePartRendering } from "./partRendering.js";

function parts(count) {
  return Array.from({ length: count }, (_, index) => ({ id: `o1.${index + 1}`, vertexCount: 3, triangleCount: 1 }));
}

// A composed component-GLB package: top-level arrays per COMPONENT, placement per part.
function composedPackage(count = 1) {
  return { parts: parts(count), partTransformsBaked: false };
}

// An imported STEP's mesh data: one merged mesh, transforms already in the vertices.
function bakedMesh(count = 3) {
  return { parts: parts(count) };
}

test("a composed package always renders per part, even with a single occurrence", () => {
  // The bug: a one-part STEP fell through to the merged mesh, which carries no CAD edge
  // attributes, so it rendered with no edges while assemblies kept theirs.
  const single = resolveScenePartRendering({ meshData: composedPackage(1) });
  assert.equal(single.renderParts, true);
  assert.equal(single.parts.length, 1);

  const many = resolveScenePartRendering({ meshData: composedPackage(9) });
  assert.equal(many.renderParts, true);
  assert.equal(many.parts.length, 9);
});

test("renderParts is never true with an empty list", () => {
  // The contradiction that caused the bug: "render parts" plus no parts, which cadScene reads
  // as "render the merged mesh".
  for (const meshData of [composedPackage(0), bakedMesh(0), null, {}]) {
    const resolved = resolveScenePartRendering({ meshData, renderPartsIndividually: true });
    assert.equal(resolved.renderParts, resolved.parts.length > 0);
    assert.equal(resolved.parts.length, 0);
  }
});

test("a baked mesh with nothing else to say renders as one mesh", () => {
  const resolved = resolveScenePartRendering({ meshData: bakedMesh(3) });
  assert.equal(resolved.renderParts, false);
  assert.deepEqual(resolved.parts, []);
});

test("each remaining reason takes every part", () => {
  for (const reason of ["renderPartsIndividually", "fillRotationParts", "sourceColorParts"]) {
    const resolved = resolveScenePartRendering({ meshData: bakedMesh(3), [reason]: true });
    assert.equal(resolved.renderParts, true, reason);
    assert.equal(resolved.parts.length, 3, reason);
  }
});

test("pickability narrows the list to the pickable parts", () => {
  // The one reason that does NOT take every part: only what can be picked needs its own mesh.
  const pickableParts = [{ id: "o1.2", vertexCount: 3, triangleCount: 1 }];
  const resolved = resolveScenePartRendering({
    meshData: bakedMesh(3),
    pickableParts,
    pickMode: VIEWER_PICK_MODE.PARTS
  });
  assert.equal(resolved.renderParts, true);
  assert.deepEqual(resolved.parts, pickableParts);
});

test("a composed package takes every part even when only one is pickable", () => {
  // Order matters: the composed-package reason must win over the pickable narrowing, or the
  // parts that are not pickable go back to being drawn from the merged mesh.
  const resolved = resolveScenePartRendering({
    meshData: composedPackage(4),
    pickableParts: [{ id: "o1.2", vertexCount: 3, triangleCount: 1 }],
    pickMode: VIEWER_PICK_MODE.PARTS
  });
  assert.equal(resolved.parts.length, 4);
});

test("a pick mode that picks nothing per part renders as one mesh", () => {
  const resolved = resolveScenePartRendering({
    meshData: bakedMesh(3),
    pickableParts: [{ id: "o1.2", vertexCount: 3, triangleCount: 1 }],
    pickMode: VIEWER_PICK_MODE.NONE
  });
  assert.equal(resolved.renderParts, false);
});
