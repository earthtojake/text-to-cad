import assert from "node:assert/strict";
import test from "node:test";
import * as THREE from "three";
import { buildModel } from "cadgen-js/common/cadScene.js";

import { sceneBuildStructuralKey } from "./sceneBuildSettings.js";

const STRUCTURAL_SETTINGS = Object.freeze({
  displayMode: "shaded",
  applyDisplayModeEdgePolicy: true,
  sceneScaleMode: "cad",
  edgeSettings: { enabled: false, color: "#111827", thickness: 1 },
  recomputeNormals: false,
  silhouette: false,
  wireframeEdgeColor: "#111827"
});

test("live PBR edits retain the scene build identity", () => {
  const before = sceneBuildStructuralKey({
    ...STRUCTURAL_SETTINGS,
    materialSettings: { roughness: 0.2, metalness: 0.1 },
    materialOverrides: { roughness: 0.2 }
  });
  const after = sceneBuildStructuralKey({
    ...STRUCTURAL_SETTINGS,
    materialSettings: { roughness: 0.8, metalness: 0.9 },
    materialOverrides: { roughness: 0.8, clearcoat: 0.7 }
  });

  assert.equal(after, before);
});

test("CAD appearance ink does not invalidate the scene build identity", () => {
  const before = sceneBuildStructuralKey(STRUCTURAL_SETTINGS);
  const after = sceneBuildStructuralKey({
    ...STRUCTURAL_SETTINGS,
    edgeSettings: { ...STRUCTURAL_SETTINGS.edgeSettings, color: "#c5ced8", thickness: 1,
      classes: { feature: { color: "#c5ced8", thickness: 1, opacity: 1 } } },
    wireframeEdgeColor: "#c5ced8"
  });
  assert.equal(after, before);
});

test("structural edge and display changes invalidate the scene build identity", () => {
  const before = sceneBuildStructuralKey(STRUCTURAL_SETTINGS);

  assert.notEqual(
    sceneBuildStructuralKey({ ...STRUCTURAL_SETTINGS, displayMode: "wireframe" }),
    before
  );
  assert.notEqual(
    sceneBuildStructuralKey({
      ...STRUCTURAL_SETTINGS,
      edgeSettings: { ...STRUCTURAL_SETTINGS.edgeSettings, enabled: true }
    }),
    before
  );
});

test("a mutable PBR edit remains authoritative across a later source reuse", () => {
  const source = {
    vertices: new Float32Array([0, 0, 0, 1, 0, 0, 0, 1, 0]),
    normals: new Float32Array([0, 0, 1, 0, 0, 1, 0, 0, 1]),
    indices: new Uint32Array([0, 1, 2]),
    bounds: { min: [0, 0, 0], max: [1, 1, 0] },
    parts: [{ id: "surface", vertexCount: 3, triangleCount: 1 }]
  };
  const initialMaterial = { roughness: 0.2, metalness: 0.1, defaultColor: "#ffffff" };
  const editedMaterial = { ...initialMaterial, roughness: 0.78, metalness: 0.64 };
  const scene = buildModel(THREE, source, {
    materialSettings: initialMaterial,
    materialOverrides: { roughness: 0.2, metalness: 0.1 },
    parameterSetup: false
  });
  try {
    const record = scene.displayRecords[0];
    scene.update({
      materialSettings: editedMaterial,
      materialOverrides: { roughness: 0.78, metalness: 0.64 }
    });
    assert.equal(scene.displayRecords[0], record);
    assert.equal(record.material.roughness, 0.78);
    assert.equal(record.material.metalness, 0.64);

    scene.update({
      source: { ...source },
      materialSettings: editedMaterial,
      materialOverrides: { roughness: 0.78, metalness: 0.64 }
    });
    assert.equal(scene.displayRecords[0].material.roughness, 0.78);
    assert.equal(scene.displayRecords[0].material.metalness, 0.64);
  } finally {
    scene.dispose();
  }
});
