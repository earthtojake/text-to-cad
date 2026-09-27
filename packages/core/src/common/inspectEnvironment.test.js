import assert from "node:assert/strict";
import test from "node:test";
import * as THREE from "three";
import { createInspectEnvironmentResource, hasAuthoredMaterials } from "./inspectEnvironment.js";

test("neutral reflection fill is demanded only by authored material parts", () => {
  assert.equal(hasAuthoredMaterials(null), false);
  assert.equal(hasAuthoredMaterials({ parts: [{ color: "#abcdef" }] }), false);
  assert.equal(hasAuthoredMaterials({ parts: [{ material: { metalness: 1 } }] }), true);
});

test("Inspect owns a small neutral reflection texture and disposes it once", () => {
  const resource = createInspectEnvironmentResource(THREE);
  const { texture } = resource;
  assert.equal(texture.mapping, THREE.EquirectangularReflectionMapping);
  assert.equal(texture.colorSpace, THREE.LinearSRGBColorSpace);
  assert.equal(texture.image.data.byteLength, 32768);
  const data = texture.image.data;
  for (let index = 0; index < data.length; index += 4) {
    assert.ok(data[index] >= 0.2 && data[index] <= 0.8);
    assert.equal(data[index], data[index + 1]);
    assert.equal(data[index], data[index + 2]);
    assert.equal(data[index + 3], 1);
  }
  assert.ok(data[0] < data[data.length - 4]);
  let disposals = 0;
  texture.addEventListener("dispose", () => disposals++);
  resource.dispose();
  resource.dispose();
  assert.equal(disposals, 1);
});
