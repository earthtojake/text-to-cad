import assert from "node:assert/strict";
import test from "node:test";

import { stepSelectionMaterialInfo } from "./stepSelectionMaterial.js";

const appearance = {
  materials: {
    steel: { name: "Brushed steel", roughness: 0.25, metalness: 1 },
    rubber: { name: "Rubber", baseColor: "#222222", roughness: 0.9 }
  },
  assignments: { "o1.1": "steel", "o1.2": "steel", "o1.3": "rubber" }
};
const meshData = {
  parts: [
    { id: "leaf-a", occurrenceId: "o1.1", sourceColor: "#778899" },
    { id: "leaf-b", occurrenceId: "o1.2", sourceColor: "#8899AA" },
    { id: "leaf-c", occurrenceId: "o1.3", sourceColor: "#FFFFFF" },
    { id: "leaf-d", occurrenceId: "o1.4", sourceColor: "#FF0000" }
  ]
};

test("a face resolves its owner occurrence and reports only authored material channels", () => {
  const info = stepSelectionMaterialInfo({
    references: [{ id: "o1.1.f9", selectorType: "face", pickData: {} }],
    meshData,
    appearance
  });
  assert.deepEqual(info, {
    status: "assigned",
    label: "Brushed steel",
    color: { value: "#778899", mixed: false },
    channels: [
      { key: "roughness", label: "Roughness", value: 0.25 },
      { key: "metalness", label: "Metalness", value: 1 }
    ]
  });
});

test("assemblies and multi-selection distinguish shared, mixed, and unassigned material state", () => {
  const shared = stepSelectionMaterialInfo({
    references: [{ id: "group", nodeType: "assembly", leafPartIds: ["leaf-a", "leaf-b"], children: [] }],
    meshData,
    appearance
  });
  assert.equal(shared.status, "assigned");
  assert.equal(shared.label, "Brushed steel");
  assert.deepEqual(shared.color, { value: "", mixed: true });

  const mixed = stepSelectionMaterialInfo({
    references: [
      { id: "leaf-a", occurrenceId: "o1.1", nodeType: "part", children: [] },
      { id: "leaf-c", occurrenceId: "o1.3", nodeType: "part", children: [] }
    ],
    meshData,
    appearance
  });
  assert.deepEqual(mixed, { status: "mixed", label: "Mixed", color: null, channels: [] });

  const assignedAndBare = stepSelectionMaterialInfo({
    references: [{ id: "group", nodeType: "assembly", leafPartIds: ["leaf-c", "leaf-d"], children: [] }],
    meshData,
    appearance
  });
  assert.deepEqual(assignedAndBare, { status: "mixed", label: "Mixed", color: null, channels: [] });
});

test("a lightweight assembly selection expands through the mesh tree without topology", () => {
  const info = stepSelectionMaterialInfo({
    references: [{ id: "module", nodeType: "assembly", children: [] }],
    meshData: {
      ...meshData,
      assemblyRoot: {
        id: "root",
        children: [{
          id: "module",
          children: [
            { id: "leaf-a", occurrenceId: "o1.1", nodeType: "part", children: [] },
            { id: "leaf-c", occurrenceId: "o1.3", nodeType: "part", children: [] }
          ]
        }]
      }
    },
    appearance
  });
  assert.deepEqual(info, { status: "mixed", label: "Mixed", color: null, channels: [] });
});

test("an unassigned source color stays a color and never becomes a material guess", () => {
  const info = stepSelectionMaterialInfo({
    references: [{ id: "leaf-d", occurrenceId: "o1.4", nodeType: "part", children: [] }],
    meshData,
    appearance
  });
  assert.deepEqual(info, {
    status: "unassigned",
    label: "Unassigned",
    color: { value: "#FF0000", mixed: false },
    channels: []
  });
});

test("render-part material metadata remains inspectable when no appearance block is available", () => {
  const info = stepSelectionMaterialInfo({
    references: [{ id: "body", occurrenceId: "body", nodeType: "part", children: [] }],
    meshData: { parts: [{
      occurrenceId: "body",
      materialId: "paint",
      materialName: "Paint",
      color: "#123456",
      material: { roughness: 0.4, metalness: 0 }
    }] }
  });
  assert.equal(info.label, "Paint");
  assert.deepEqual(info.color, { value: "#123456", mixed: false });
  assert.deepEqual(info.channels.map(({ key, value }) => [key, value]), [["roughness", 0.4], ["metalness", 0]]);
});

test("an appearance block's missing assignment wins over stale render-part material metadata", () => {
  const info = stepSelectionMaterialInfo({
    references: [{ id: "body", occurrenceId: "body", nodeType: "part", children: [] }],
    meshData: { parts: [{
      occurrenceId: "body",
      materialId: "old-paint",
      materialName: "Old paint",
      sourceColor: "#ABCDEF",
      material: { roughness: 0.2 }
    }] },
    appearance: { materials: { "old-paint": { name: "Old paint" } }, assignments: {} }
  });
  assert.deepEqual(info, {
    status: "unassigned",
    label: "Unassigned",
    color: { value: "#ABCDEF", mixed: false },
    channels: []
  });
});
