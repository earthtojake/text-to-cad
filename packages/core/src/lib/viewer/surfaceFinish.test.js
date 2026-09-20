import assert from "node:assert/strict";
import test from "node:test";
import * as THREE from "three";

import { applySurfaceFinish, resolveSurfaceFinish, SURFACE_FINISH_DEFAULTS } from "./surfaceFinish.js";

test("the finish is plain data: theme values, else the viewer's defaults", () => {
  assert.deepEqual(resolveSurfaceFinish(null), { roughness: 0.92, metalness: 0.03, clearcoat: 0 });
  assert.deepEqual(resolveSurfaceFinish(null), { ...SURFACE_FINISH_DEFAULTS });
  assert.deepEqual(resolveSurfaceFinish({ surfaceRoughness: 0.4, surfaceMetalness: "0.5" }), { roughness: 0.4, metalness: 0.5, clearcoat: 0 });
});

test("a finish dresses standard materials and null restores what was authored", () => {
  const authored = new THREE.MeshStandardMaterial({ color: "#336699", roughness: 0.2, metalness: 1 });
  const basic = new THREE.MeshBasicMaterial({ color: "#ffffff" });
  const root = new THREE.Group();
  root.add(new THREE.Mesh(new THREE.BoxGeometry(), authored), new THREE.Mesh(new THREE.BoxGeometry(), [authored, basic]));
  applySurfaceFinish(root, { roughness: 0.92, metalness: 0.03, clearcoat: 0 });
  assert.equal(authored.roughness, 0.92);
  assert.equal(authored.metalness, 0.03);
  assert.equal(authored.color.getHexString(), "336699", "colour identifies the part and is never touched");
  assert.equal("roughness" in basic, false, "materials without a finish are left alone");
  applySurfaceFinish(root, { roughness: 0.5 });
  assert.equal(authored.metalness, 1, "a partial finish falls back to the authored value, not the previous finish");
  applySurfaceFinish(root, null);
  assert.deepEqual([authored.roughness, authored.metalness], [0.2, 1]);
});
