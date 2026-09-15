import assert from "node:assert/strict";
import test from "node:test";

import {
  applySourceMaterialOverlayToMeshData,
  assignSourceMaterialOverlay,
  duplicateSourceMaterialOverlay,
  effectiveSourceAppearance,
  patchSourceMaterialOverlay,
  sourceMaterialFallbackColor,
  sourceMaterialOverlayIsEmpty,
  sourceMaterialUsage
} from "./sourceMaterialSession.js";
import * as materialSession from "./sourceMaterialSession.js";

test("part-first assignment applies a preset atomically only to the selected parts", () => {
  const result = materialSession.applyMaterialChoice(appearance, null, ["finger"], "preset:matte-plastic");
  const effective = effectiveSourceAppearance(appearance, result.overlay);
  assert.equal(effective.assignments.palm, "steel");
  assert.equal(effective.assignments.finger, result.materialId);
  assert.equal(effective.materials[result.materialId].metalness, 0);
  assert.equal(materialSession.applyMaterialChoice(appearance, null, [], "preset:rubber"), null);
  assert.equal(materialSession.applyMaterialChoice(appearance, null, ["finger"], "material:missing"), null);
});

test("selection describes mixed, unassigned, and shared materials", () => {
  assert.equal(materialSession.materialForSelection(appearance, ["palm", "finger"]).label, "Mixed");
  assert.equal(materialSession.materialForSelection(appearance, ["bare"]).label, "Unassigned");
  assert.equal(materialSession.materialForSelection(appearance, ["palm"]).materialId, "steel");
  const assigned = materialSession.applyMaterialChoice(appearance, null, ["finger"], "material:steel");
  assert.equal(effectiveSourceAppearance(appearance, assigned.overlay).assignments.finger, "steel");
});

const appearance = {
  materials: {
    steel: { name: "Steel", baseColor: "#778899", metalness: 0.8 },
    rubber: { name: "Rubber", roughness: 0.9 }
  },
  assignments: { palm: "steel", finger: "rubber" }
};

test("material session patches stay separate and assignments report usage", () => {
  const overlay = patchSourceMaterialOverlay(null, "steel", { roughness: 0.2 });
  const reassigned = assignSourceMaterialOverlay(overlay, ["finger"], "steel");
  assert.deepEqual(appearance.materials.steel, { name: "Steel", baseColor: "#778899", metalness: 0.8 });
  assert.deepEqual(sourceMaterialUsage(appearance, reassigned, [{ id: "palm" }, { id: "finger" }]), {
    steel: 2,
    rubber: 0
  });
});

test("duplicate creates one session material and redirects only chosen occurrences", () => {
  const result = duplicateSourceMaterialOverlay(appearance, null, "steel", ["finger"]);
  assert.equal(result.materialId, "steel-copy-1");
  assert.equal(result.overlay.materials[result.materialId].name, "Steel copy");
  assert.equal(result.overlay.assignments.finger, result.materialId);
  assert.equal(result.overlay.assignments.palm, undefined);
});

test("display mesh overlays named material channels without mutating cached parts", () => {
  const meshData = {
    appearance,
    parts: [
      { id: "palm", occurrenceId: "palm", sourceColor: "#111111", sourceOpacity: 0.5, color: "#778899", opacity: 0.5, material: { roughness: 0.7 } },
      { id: "finger", occurrenceId: "finger", sourceColor: "#222222", sourceOpacity: 0.8, color: "#222222", opacity: 0.8, material: { roughness: 0.9 } }
    ]
  };
  const overlay = patchSourceMaterialOverlay(null, "steel", { baseColor: "#abcdef", opacity: 0.6 });
  const displayed = applySourceMaterialOverlayToMeshData(meshData, overlay);
  assert.notEqual(displayed, meshData);
  assert.equal(displayed.parts[0].color, "#ABCDEF");
  assert.equal(displayed.parts[0].materialId, "steel");
  assert.equal(displayed.parts[0].material.opacity, 0.6);
  assert.equal(displayed.parts[0].opacity, 0.3);
  assert.equal(displayed.parts[0].material.roughness, 0.42);
  assert.equal(meshData.parts[0].color, "#778899");
  assert.equal(displayed.parts[1].color, "#222222", "missing base color preserves the STEP part color");
});

test("reassignment restores intrinsic color and composes intrinsic alpha", () => {
  const meshData = {
    appearance,
    parts: [{
      id: "palm",
      occurrenceId: "palm",
      sourceColor: "#123456",
      sourceOpacity: 0.4,
      color: "#778899",
      opacity: 0.4
    }]
  };
  const overlay = assignSourceMaterialOverlay(null, ["palm"], "rubber");
  const displayed = applySourceMaterialOverlayToMeshData(meshData, overlay);
  assert.equal(displayed.parts[0].color, "#123456");
  assert.equal(displayed.parts[0].opacity, 0.4);
});

test("resetting a nonempty overlay restores the authored material", () => {
  const overlay = patchSourceMaterialOverlay(null, "steel", { opacity: 0.35 });
  assert.equal(effectiveSourceAppearance(appearance, overlay).materials.steel.opacity, 0.35);
  assert.equal(sourceMaterialOverlayIsEmpty(overlay), false);
  assert.equal(sourceMaterialOverlayIsEmpty(null), true);
  assert.equal(effectiveSourceAppearance(appearance, null).materials.steel.opacity, undefined);
});

test("fallback colors come only from consistently colored assigned parts", () => {
  const effective = {
    materials: appearance.materials,
    assignments: { blue: "steel", grayA: "rubber", grayB: "rubber", bare: "steel-copy" }
  };
  const parts = [
    { id: "blue", color: "#123456" },
    { id: "grayA", color: "#888888" },
    { id: "grayB", color: "#999999" },
    { id: "bare", color: "" }
  ];
  assert.equal(sourceMaterialFallbackColor(effective, "steel", parts), "#123456");
  assert.equal(sourceMaterialFallbackColor(effective, "rubber", parts), "#b8b8b8");
  assert.equal(sourceMaterialFallbackColor(effective, "steel-copy", parts), "#b8b8b8");
});

test("a preset can be assigned to a bare STEP without changing its intrinsic appearance", () => {
  const mesh = { parts: [{ id: "case", sourceColor: "#123456", sourceOpacity: 0.5 }] };
  const added = materialSession.addSourceMaterialPreset(null, null, "polished-metal");
  const overlay = assignSourceMaterialOverlay(added.overlay, ["case"], added.materialId);
  const displayed = applySourceMaterialOverlayToMeshData(mesh, overlay);
  assert.equal(displayed.parts[0].material.metalness, 1);
  assert.equal(displayed.parts[0].color, "#123456");
  assert.equal(displayed.parts[0].opacity, 0.5);
  assert.equal(mesh.parts[0].material, undefined);
  assert.equal(applySourceMaterialOverlayToMeshData(mesh, null), mesh);
  const second = materialSession.addSourceMaterialPreset(null, overlay, "polished-metal");
  assert.notEqual(second.materialId, added.materialId);
  assert.equal(effectiveSourceAppearance(null, second.overlay).assignments.case, added.materialId);
});

test("changing finish preserves color and opacity while replacing every finish channel", () => {
  const overlay = materialSession.applySourceMaterialPreset(null, "steel", "matte-plastic");
  const effective = effectiveSourceAppearance(appearance, overlay);
  assert.equal(effective.materials.steel.baseColor, "#778899");
  assert.equal(effective.materials.steel.metalness, 0);
  assert.equal(effective.materials.steel.clearcoat, 0);
  assert.equal(overlay.materials.steel.opacity, undefined);
});
