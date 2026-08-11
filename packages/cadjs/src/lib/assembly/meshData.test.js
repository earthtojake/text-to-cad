import assert from "node:assert/strict";
import { test } from "node:test";

import {
  assemblyBreadcrumb,
  assemblyInspectionNode,
  buildAssemblyLeafToNodePickMap,
  buildComposedPackageMeshData,
  descendantLeafPartIds,
  findAssemblyNode,
  focusedLeafPartIdsForAssemblyInspection,
  flattenAssemblyNodes,
  flattenAssemblyLeafParts,
  leafPartIdsForAssemblySelection,
  normalizeAssemblyInspectionNodeId,
  representativeAssemblyLeafPartId,
  rootAssemblyInspectionNodeId,
  selectableAssemblyNodeIdsForInspection,
  treeSelectableAssemblyNodeIdsForInspection,
  resolveAssemblyPickedPartId
} from "./meshData.js";

test("assembly helpers navigate nested assemblies down to leaf parts", () => {
  const root = {
    id: "root",
    nodeType: "assembly",
    displayName: "sample_root",
    children: [
      {
        id: "sample_module",
        nodeType: "assembly",
        displayName: "sample_module",
        children: [
          {
            id: "sample_part",
            nodeType: "part",
            displayName: "sample_part",
            children: []
          }
        ]
      }
    ]
  };

  assert.deepEqual(flattenAssemblyLeafParts(root).map((part) => part.id), ["sample_part"]);
  assert.deepEqual(flattenAssemblyNodes(root).map((node) => node.id), ["root", "sample_module", "sample_part"]);
  assert.equal(findAssemblyNode(root, "sample_module")?.displayName, "sample_module");
  assert.deepEqual(assemblyBreadcrumb(root, "sample_part").map((node) => node.id), ["root", "sample_module", "sample_part"]);
  assert.deepEqual(descendantLeafPartIds(root.children[0]), ["sample_part"]);
  assert.equal(representativeAssemblyLeafPartId(root.children[0]), "sample_part");
});

test("assembly picking maps rendered leaves to scoped assembly nodes", () => {
  const root = {
    id: "root",
    nodeType: "assembly",
    children: [
      {
        id: "module",
        occurrenceId: "o1.1",
        nodeType: "assembly",
        leafPartIds: ["leaf_a", "leaf_b"],
        children: [
          {
            id: "leaf_a",
            occurrenceId: "o1.1.1",
            nodeType: "part",
            sourcePath: "parts/a.step",
            children: []
          },
          {
            id: "leaf_b",
            occurrenceId: "o1.1.2",
            nodeType: "part",
            children: []
          }
        ]
      }
    ]
  };

  const pickPartIdMap = buildAssemblyLeafToNodePickMap(root.children);
  assert.deepEqual(
    [...pickPartIdMap.entries()],
    [
      ["leaf_a", "module"],
      ["leaf_b", "module"]
    ]
  );
  assert.equal(
    resolveAssemblyPickedPartId("leaf_a", {
      pickPartIdMap,
      validLeafPartIds: ["leaf_a", "leaf_b"]
    }),
    "module"
  );
  assert.equal(
    resolveAssemblyPickedPartId("legacy_mesh_leaf", {
      pickPartIdMap: new Map([["legacy_mesh_leaf", "module"]]),
      validLeafPartIds: ["leaf_a", "leaf_b"]
    }),
    "module"
  );
  const assemblyPartMap = new Map(flattenAssemblyNodes(root).map((node) => [node.id, node]));
  assert.deepEqual(
    leafPartIdsForAssemblySelection("module", {
      assemblyPartMap,
      fallbackPartId: "leaf_a",
      validLeafPartIds: ["leaf_a", "leaf_b"]
    }),
    ["leaf_a", "leaf_b"]
  );
  assert.deepEqual(
    leafPartIdsForAssemblySelection("leaf_a", {
      assemblyPartMap,
      validLeafPartIds: ["leaf_a", "leaf_b"]
    }),
    ["leaf_a"]
  );
  assert.deepEqual(
    leafPartIdsForAssemblySelection("missing", {
      assemblyPartMap,
      fallbackPartId: "leaf_b",
      validLeafPartIds: ["leaf_a", "leaf_b"]
    }),
    ["leaf_b"]
  );
  assert.equal(representativeAssemblyLeafPartId(root.children[0]), "leaf_a");
});

test("nested assembly selection resolves descendant render leaves without loading sibling topology", () => {
  const root = {
    id: "root",
    nodeType: "assembly",
    children: [
      {
        id: "outer",
        nodeType: "assembly",
        children: [
          {
            id: "inner",
            nodeType: "assembly",
            children: [
              {
                id: "leaf_a",
                nodeType: "part",
                occurrenceId: "o1.1.1.1",
                children: []
              },
              {
                id: "leaf_b",
                nodeType: "part",
                occurrenceId: "o1.1.1.2",
                children: []
              }
            ]
          }
        ]
      },
      {
        id: "sibling_leaf",
        nodeType: "part",
        occurrenceId: "o1.2",
        children: []
      }
    ]
  };
  const assemblyPartMap = new Map(flattenAssemblyNodes(root).map((node) => [node.id, node]));
  const validLeafPartIds = flattenAssemblyLeafParts(root).map((node) => node.id);

  assert.deepEqual(
    leafPartIdsForAssemblySelection("inner", {
      assemblyPartMap,
      validLeafPartIds
    }),
    ["leaf_a", "leaf_b"]
  );
  assert.deepEqual(
    leafPartIdsForAssemblySelection("outer", {
      assemblyPartMap,
      validLeafPartIds
    }),
    ["leaf_a", "leaf_b"]
  );
  assert.deepEqual(
    leafPartIdsForAssemblySelection("root", {
      assemblyPartMap,
      validLeafPartIds
    }),
    ["leaf_a", "leaf_b", "sibling_leaf"]
  );
});

test("assembly inspection helpers keep one inspected node and limit selectable children", () => {
  const root = {
    id: "root",
    nodeType: "assembly",
    children: [
      {
        id: "module",
        nodeType: "assembly",
        children: [
          {
            id: "leaf_a",
            nodeType: "part",
            children: []
          },
          {
            id: "leaf_b",
            nodeType: "part",
            children: []
          }
        ]
      },
      {
        id: "compound_part",
        nodeType: "part",
        children: [
          {
            id: "leaf_c",
            nodeType: "part",
            children: []
          },
          {
            id: "leaf_d",
            nodeType: "part",
            children: []
          }
        ]
      },
      {
        id: "sibling",
        nodeType: "part",
        children: []
      }
    ]
  };

  assert.equal(rootAssemblyInspectionNodeId(root), "root");
  assert.equal(normalizeAssemblyInspectionNodeId(root, ""), "root");
  assert.equal(normalizeAssemblyInspectionNodeId(root, "missing"), "root");
  assert.equal(normalizeAssemblyInspectionNodeId(root, "leaf_a"), "leaf_a");
  assert.equal(assemblyInspectionNode(root, "module")?.id, "module");

  assert.deepEqual(selectableAssemblyNodeIdsForInspection(root, ""), ["module", "compound_part", "sibling"]);
  assert.deepEqual(selectableAssemblyNodeIdsForInspection(root, "module"), ["leaf_a", "leaf_b"]);
  assert.deepEqual(selectableAssemblyNodeIdsForInspection(root, "compound_part"), ["leaf_c", "leaf_d"]);
  assert.deepEqual(selectableAssemblyNodeIdsForInspection(root, "leaf_a"), []);
  assert.equal(selectableAssemblyNodeIdsForInspection(root, "module").includes("sibling"), false);

  assert.deepEqual(treeSelectableAssemblyNodeIdsForInspection(root, ""), ["module", "compound_part", "sibling"]);
  assert.deepEqual(treeSelectableAssemblyNodeIdsForInspection(root, "module"), ["leaf_a", "leaf_b"]);
  assert.deepEqual(treeSelectableAssemblyNodeIdsForInspection(root, "compound_part"), ["leaf_c", "leaf_d"]);
  assert.deepEqual(treeSelectableAssemblyNodeIdsForInspection(root, "leaf_a"), []);
  assert.equal(treeSelectableAssemblyNodeIdsForInspection(root, "module").includes("sibling"), false);

  assert.deepEqual(focusedLeafPartIdsForAssemblyInspection(root, ""), []);
  assert.deepEqual(focusedLeafPartIdsForAssemblyInspection(root, "module"), ["leaf_a", "leaf_b"]);
  assert.deepEqual(focusedLeafPartIdsForAssemblyInspection(root, "compound_part"), ["leaf_c", "leaf_d"]);
  assert.deepEqual(focusedLeafPartIdsForAssemblyInspection(root, "leaf_a"), ["leaf_a"]);
});

test("assembly picking maps rendered leaves to the current selectable node before accepting leaf ids", () => {
  const pickPartIdMap = new Map([
    ["leaf_a", "module"],
    ["leaf_b", "module"],
    ["sibling", "sibling"]
  ]);
  const validLeafPartIds = ["leaf_a", "leaf_b", "sibling"];

  assert.equal(
    resolveAssemblyPickedPartId("leaf_a", { pickPartIdMap, validLeafPartIds }),
    "module"
  );
  assert.equal(
    resolveAssemblyPickedPartId("sibling", { pickPartIdMap, validLeafPartIds }),
    "sibling"
  );
  assert.equal(
    resolveAssemblyPickedPartId("unknown", { pickPartIdMap, validLeafPartIds }),
    "unknown"
  );
});

function unitTriangleComponentMeshData() {
  // One part: a triangle in the component's LOCAL frame, +z normals.
  return {
    vertices: new Float32Array([
      0, 0, 0,
      1, 0, 0,
      0, 1, 0
    ]),
    normals: new Float32Array([
      0, 0, 1,
      0, 0, 1,
      0, 0, 1
    ]),
    colors: new Float32Array(0),
    indices: new Uint32Array([0, 1, 2]),
    parts: [
      {
        id: "o1",
        occurrenceId: "o1",
        primitiveIndex: 0,
        vertexOffset: 0,
        vertexCount: 3,
        triangleOffset: 0,
        triangleCount: 1
      }
    ],
    bounds: { min: [0, 0, 0], max: [1, 1, 0] }
  };
}

const IDENTITY_4X4 = [
  1, 0, 0, 0,
  0, 1, 0, 0,
  0, 0, 1, 0,
  0, 0, 0, 1
];

test("composed package renders occurrences over shared component geometry (no baking)", () => {
  const descriptor = {
    schemaVersion: 1,
    kind: "assembly-package",
    rootName: "demo",
    components: { cA: { glb: "components/cA.glb", contentHash: "abc" } },
    occurrences: [
      { id: "o1.1", name: "part_a", component: "cA", transform: IDENTITY_4X4 },
      {
        id: "o1.2",
        name: "part_b",
        component: "cA",
        transform: [
          1, 0, 0, 10,
          0, 1, 0, 0,
          0, 0, 1, 0,
          0, 0, 0, 1
        ]
      }
    ]
  };
  const componentMeshData = unitTriangleComponentMeshData();
  const composed = buildComposedPackageMeshData(descriptor, { cA: componentMeshData });

  assert.equal(composed.parts.length, 2);
  // No baking: each occurrence is placed by its transform at render time.
  assert.equal(composed.partTransformsBaked, false);
  // Top-level holds the UNIQUE component geometry once (not one copy per occurrence).
  assert.equal(composed.vertices.length, 9); // 1 unique component * 3 verts * 3
  assert.equal(composed.indices.length, 3);

  // Each occurrence references the same shared component geometry (one cached BufferGeometry)
  // and carries its own placement transform.
  assert.equal(composed.parts[0].sourceMesh, componentMeshData);
  assert.equal(composed.parts[1].sourceMesh, componentMeshData);
  assert.equal(composed.parts[0].sourceMeshKey, composed.parts[1].sourceMeshKey);
  assert.deepEqual([...composed.parts[0].transform], IDENTITY_4X4);
  assert.deepEqual([...composed.parts[1].transform], [1, 0, 0, 10, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]);

  // Occurrence id + component id + component-local face range preserved for selectors.
  assert.equal(composed.parts[1].occurrenceId, "o1.2");
  assert.equal(composed.parts[1].componentId, "cA");
  assert.equal(composed.parts[1].sourcePartRanges[0].occurrenceId, "o1.2");
  assert.equal(composed.parts[1].sourcePartRanges[0].primitiveIndex, 0);
  assert.equal(composed.parts[1].sourcePartRanges[0].triangleOffset, 0); // component-local
  // Bounds reflect the placed (world) box even though vertices are not baked.
  assert.deepEqual(composed.parts[1].bounds, { min: [10, 0, 0], max: [11, 1, 0] });
});

test("composed package flags a mirrored occurrence (rendered DoubleSide, geometry shared)", () => {
  const descriptor = {
    occurrences: [
      { id: "o1.1", name: "plain", component: "cA", transform: IDENTITY_4X4 },
      {
        id: "o1.2",
        name: "mirror",
        component: "cA",
        transform: [
          -1, 0, 0, 0,
          0, 1, 0, 0,
          0, 0, 1, 0,
          0, 0, 0, 1
        ]
      }
    ]
  };
  const componentMeshData = unitTriangleComponentMeshData();
  const composed = buildComposedPackageMeshData(descriptor, { cA: componentMeshData });
  assert.equal(composed.parts[0].mirrored, false);
  assert.equal(composed.parts[1].mirrored, true);
  // Winding is NOT flipped in geometry — the shared component geometry is reused as-is and the
  // negative-determinant transform + DoubleSide material handle the mirror at render time.
  assert.equal(composed.parts[1].sourceMesh, componentMeshData);
  assert.deepEqual([...composed.indices], [0, 1, 2]);
});

test("composed package drives a per-occurrence override colour through the material (hex, not vertex baking)", () => {
  // The baked composer wrote override floats straight into per-occurrence vertex colours; the
  // shared-geometry composer can't (geometry is shared), so it routes the override to part.color
  // as an sRGB hex string the viewer parses via readSourceColor -> new THREE.Color. Encoding the
  // linear override [r,g,b] to sRGB hex makes that round-trip land on the same linear albedo the
  // baked path shaded.
  const descriptor = {
    occurrences: [
      // linear black-ish grey, matching how raptor3 authors dark occurrence colours.
      { id: "o1.1", name: "dark", component: "cA", transform: IDENTITY_4X4, color: [0.1, 0.095, 0.09, 1.0] }
    ]
  };
  const composed = buildComposedPackageMeshData(descriptor, { cA: unitTriangleComponentMeshData() });
  const part = composed.parts[0];
  // Override colour becomes a hex string (not the raw float array) so readSourceColor accepts it.
  assert.match(part.color, /^#[0-9a-f]{6}$/);
  // linearToSRGB([0.1,0.095,0.09]) -> bytes [89,87,85]; the exact hex pins the encoding.
  assert.equal(part.color, "#595755");
  // No component COLOR_0 and an override present => geometry carries no colour attribute; the
  // material (flat part.color) drives the surface, so occurrences of one cid still share geometry.
  assert.equal(part.hasSourceColors, false);
  assert.equal(composed.colors.length, 0);
});

test("composed package mesh records missing components instead of throwing", () => {
  const descriptor = {
    occurrences: [
      { id: "o1.1", name: "present", component: "cA", transform: IDENTITY_4X4 },
      { id: "o1.2", name: "absent", component: "cMissing", transform: IDENTITY_4X4 }
    ]
  };
  const composed = buildComposedPackageMeshData(descriptor, { cA: unitTriangleComponentMeshData() });
  assert.equal(composed.parts.length, 1);
  assert.deepEqual(composed.missingComponentIds, ["cMissing"]);
});

test("single-component part carries NO assemblyRoot so the viewer renders a topology tree", () => {
  // entryKind:"part" is a single-component package: the viewer must render it like a monolithic
  // STEP part (topology tree of solids/faces/edges), NOT a one-node assembly wrapper. Returning a
  // synthesized assemblyRoot would make buildStepTreeRoot show "No assembly tree" in the part view.
  const partDescriptor = {
    kind: "assembly-package",
    entryKind: "part",
    rootName: "bracket",
    components: { cA: { glb: "components/cA.glb", contentHash: "abc" } },
    occurrences: [{ id: "o1.1", name: "bracket", component: "cA", transform: IDENTITY_4X4 }]
  };
  const part = buildComposedPackageMeshData(partDescriptor, { cA: unitTriangleComponentMeshData() });
  assert.equal(part.parts.length, 1, "the single component still composes a render part");
  assert.equal(part.assemblyRoot, null, "a part has no assembly structure tree");

  // An assembly with the same single occurrence DOES synthesize a root (structure tree).
  const assemblyDescriptor = { ...partDescriptor, entryKind: "assembly" };
  const assembly = buildComposedPackageMeshData(assemblyDescriptor, { cA: unitTriangleComponentMeshData() });
  assert.ok(assembly.assemblyRoot, "an assembly keeps its structure tree");
  assert.equal(assembly.assemblyRoot.nodeType, "assembly");
});
