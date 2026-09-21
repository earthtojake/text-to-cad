import assert from "node:assert/strict";
import { test } from "node:test";

import {
  assemblyBreadcrumb,
  assemblyInspectionNode,
  buildAssemblyLeafToNodePickMap,
  buildComposedPackageMeshData,
  descendantLeafPartIds,
  findAssemblyNode,
  findAssemblyNodes,
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

test("batch assembly lookup preserves requested order, normalization, duplicates, missing and root semantics", () => {
  const first = { id: " duplicate ", nodeType: "part", children: [] };
  const root = { id: "actual-root", children: [
    { id: "group", children: [first, { id: "leaf", nodeType: "part" }] },
    { id: "duplicate", nodeType: "part" }, { id: "root", nodeType: "part" },
    { id: 0, nodeType: "part" }, { id: 12, nodeType: "part" },
  ] };
  const ids = [" leaf ", "duplicate", "group", "duplicate", "missing", "actual-root", "root", "", null,
    undefined, false, 0, "0", 12, { toString: () => " leaf " }];
  const actual = findAssemblyNodes(root, ids);
  const expected = ids.map(id => findAssemblyNode(root, id));
  actual.forEach((node, i) => assert.equal(node, expected[i], `request ${i}`));
  assert.equal(actual[1], first);
  assert.deepEqual(actual.filter(Boolean).map(node => ({ ...node, leafPartIds: descendantLeafPartIds(node) })),
    expected.filter(Boolean).map(node => ({ ...node, leafPartIds: descendantLeafPartIds(node) })));
  assert.deepEqual(findAssemblyNodes(null, ids), ids.map(() => null));
  assert.deepEqual(findAssemblyNodes(root, []), []);
});

test("batch lookup visits the tree once and retains no index between live tree changes", () => {
  let reads = 0;
  const nodes = Array.from({ length: 2048 }, (_, index) => ({
    get id() { reads++; return `part-${index}`; }, children: [],
  }));
  const root = { get id() { reads++; return "actual-root"; }, children: nodes };
  const requested = nodes.map((_, i) => `part-${nodes.length - 1 - i}`);
  const found = findAssemblyNodes(root, [...requested, "part-0", "missing"]);
  assert.equal(reads, nodes.length + 1, "one ID read per tree node, independent of request count/order");
  assert.equal(found[0], nodes.at(-1)); assert.equal(found.at(-2), nodes[0]); assert.equal(found.at(-1), null);
  const replacement = { id: "part-0", children: [{ id: "new-child", nodeType: "part" }] };
  root.children = [replacement];
  assert.deepEqual(findAssemblyNodes(root, ["part-0", "new-child", "part-1"]), [replacement, replacement.children[0], null]);
  reads = 0;
  assert.deepEqual(findAssemblyNodes(root, ["root", "", null]), [root, root, root]);
  assert.equal(reads, 0, "root aliases need no traversal");
});

test("batch lookup handles deeply nested trees iteratively and stops after the final requested match", () => {
  const leaf = { id: "needle", nodeType: "part", children: [] };
  let root = leaf;
  for (let index = 0; index < 10000; index++) root = { id: `nested-${index}`, children: [root] };
  assert.equal(findAssemblyNodes(root, ["needle"])[0], leaf);
  const short = { id: "match", get children() { throw new Error("unneeded descendants"); } };
  assert.deepEqual(findAssemblyNodes(short, ["match", "match"]), [short, short]);
});

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
    ],
    assembly: {
      root: {
        id: "o1",
        name: "demo",
        nodeType: "assembly",
        children: [
          { id: "o1.1", name: "part_a", nodeType: "part", children: [] },
          { id: "o1.2", name: "part_b", nodeType: "part", children: [] }
        ]
      }
    }
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
    ],
    assembly: {
      root: {
        id: "o1",
        name: "demo",
        nodeType: "assembly",
        children: [
          { id: "o1.1", name: "plain", nodeType: "part", children: [] },
          { id: "o1.2", name: "mirror", nodeType: "part", children: [] }
        ]
      }
    }
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

test("multiple components keep their own buffers without an aggregate allocation", () => {
  const a = unitTriangleComponentMeshData();
  const b = unitTriangleComponentMeshData();
  const descriptor = { components: { a: {}, b: {} }, occurrences: [
    { id: "first", component: "a", transform: IDENTITY_4X4 },
    { id: "second", component: "b", transform: IDENTITY_4X4 },
    { id: "repeat", component: "a", transform: IDENTITY_4X4 }
  ] };
  descriptor.assembly = { root: { id: "root", nodeType: "assembly",
    children: descriptor.occurrences.map(({ id }) => ({ id, nodeType: "part", children: [] })) } };
  const composed = buildComposedPackageMeshData(descriptor, { a, b });
  assert.equal(composed.vertices.length, 0);
  assert.equal(composed.normals.length, 0);
  assert.equal(composed.indices.length, 0);
  assert.equal(composed.parts[0].sourceMesh, a);
  assert.equal(composed.parts[1].sourceMesh, b);
  assert.equal(composed.parts[2].sourceMesh, a);
  const single = buildComposedPackageMeshData({ entryKind: "part", occurrences: [descriptor.occurrences[0]] }, { a });
  assert.equal(single.vertices, a.vertices);
  assert.equal(single.normals, a.normals);
  assert.equal(single.indices, a.indices);
});

function reuseFixture() {
  const descriptor = { occurrences: [
    { id: "first", component: "a", transform: IDENTITY_4X4 },
    { id: "second", component: "b", transform: IDENTITY_4X4 },
    { id: "repeat", component: "a", transform: IDENTITY_4X4 },
  ] };
  descriptor.assembly = { root: { id: "root", nodeType: "assembly",
    children: descriptor.occurrences.map(({ id }) => ({ id, nodeType: "part", children: [] })) } };
  return { descriptor, a: { ...unitTriangleComponentMeshData(), lodLevel: 0 }, b: unitTriangleComponentMeshData() };
}

test("LOD composition keeps unchanged occurrences and tree identity while updating repeated triangle ranges", () => {
  const { descriptor, a, b } = reuseFixture();
  const before = buildComposedPackageMeshData(descriptor, { a, b });
  const refined = { ...a, lodLevel: 1, indices: new Uint32Array([0, 1, 2, 0, 2, 1]),
    parts: a.parts.map(part => ({ ...part, triangleCount: 2 })) };
  const after = buildComposedPackageMeshData(descriptor, { a: refined, b }, { previous: before });
  assert.equal(after.parts[1], before.parts[1], "unaffected occurrence metadata is shared");
  for (const index of [0, 2]) {
    assert.notEqual(after.parts[index], before.parts[index]);
    assert.equal(after.parts[index].sourceMesh, refined);
    assert.equal(after.parts[index].sourceMeshKey, "a:flat:l1");
    assert.equal(after.parts[index].sourcePartRanges[0].triangleCount, 2);
  }
  assert.equal(after.assemblyRoot, before.assemblyRoot, "identical bounds/appearance preserve the tree");
  assert.equal(after.bounds, before.bounds);
  assert.equal(before.parts[0].sourceMesh, a, "old display ownership is not mutated");
});

test("changed component bounds rebuild only affected tree paths and preserve exact new bounds", () => {
  const { descriptor, a, b } = reuseFixture();
  const before = buildComposedPackageMeshData(descriptor, { a, b });
  const changed = { ...a, bounds: { min: [-2, 0, 0], max: [3, 2, 1] } };
  const after = buildComposedPackageMeshData(descriptor, { a: changed, b }, { previous: before });
  assert.notEqual(after.assemblyRoot, before.assemblyRoot);
  assert.equal(after.assemblyRoot.children[1], before.assemblyRoot.children[1]);
  assert.deepEqual(after.parts[0].bounds, changed.bounds);
  assert.deepEqual(after.bounds, changed.bounds);
  assert.deepEqual(before.parts[0].bounds, a.bounds);
});

test("cross-revision composition removes descendants when a subassembly becomes a leaf", () => {
  const { descriptor, a, b } = reuseFixture();
  const leaf = descriptor.assembly.root.children[0];
  descriptor.assembly.root.children[0] = {
    id: "group", nodeType: "assembly", children: [leaf]
  };
  const before = buildComposedPackageMeshData(descriptor, { a, b });
  const edited = structuredClone(descriptor);
  edited.assembly.root.children[0] = { id: "first", nodeType: "part", children: [] };
  const after = buildComposedPackageMeshData(edited, { a, b }, { previous: before });
  assert.deepEqual(after.assemblyRoot.children[0].children, []);
  assert.deepEqual(after.assemblyRoot.children[0].leafPartIds, ["first"]);
  assert.deepEqual(after.assemblyRoot, buildComposedPackageMeshData(edited, { a, b }).assemblyRoot);
  assert.equal(after.assemblyRoot.children[1], before.assemblyRoot.children[1], "unaffected leaf keeps its identity");
  assert.equal(before.assemblyRoot.children[0].children[0].id, "first", "prior tree remains intact");

  // Removing the last child of a still-present grouping node also clears it.
  edited.assembly.root.children[0] = { id: "group", nodeType: "assembly", children: [] };
  const empty = buildComposedPackageMeshData(edited, { a, b }, { previous: before });
  assert.deepEqual(empty.assemblyRoot.children[0].children, []);
  assert.deepEqual(empty.assemblyRoot, buildComposedPackageMeshData(edited, { a, b }).assemblyRoot);
});

test("new descriptor appearance, mirror and placement cannot reuse previous occurrence metadata", () => {
  const { descriptor, a, b } = reuseFixture();
  const before = buildComposedPackageMeshData(descriptor, { a, b });
  const edited = structuredClone(descriptor);
  edited.occurrences[0] = { ...edited.occurrences[0], color: [1, 0, 0, 0.5],
    material: { roughness: 0.25 }, transform: [-1, 0, 0, 12, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1] };
  const after = buildComposedPackageMeshData(edited, { a, b }, { previous: before });
  assert.notEqual(after.parts[0], before.parts[0]);
  assert.equal(after.parts[1], before.parts[1], "unchanged rows cross an immutable revision boundary");
  assert.equal(after.parts[2], before.parts[2]);
  assert.equal(after.assemblyRoot.children[1], before.assemblyRoot.children[1], "unchanged tree branches cross the revision");
  assert.equal(after.parts[0].mirrored, true);
  assert.equal(after.parts[0].color, "#ff0000");
  assert.equal(after.parts[0].opacity, 0.5);
  assert.deepEqual(after.parts[0].material, { roughness: 0.25 });
  assert.deepEqual(after.parts[0].bounds, { min: [11, 0, 0], max: [12, 1, 0] });
  assert.equal(before.parts[0].mirrored, false);
});

test("cross-revision reuse conservatively invalidates any occurrence, component topology, or tree metadata change", () => {
  const { descriptor, a, b } = reuseFixture();
  const before = buildComposedPackageMeshData(descriptor, { a, b });

  const futureAppearance = structuredClone(descriptor);
  futureAppearance.occurrences[0].futureAppearance = { coating: "oxide", layers: [1, 2] };
  const appearance = buildComposedPackageMeshData(futureAppearance, { a, b }, { previous: before });
  assert.notEqual(appearance.parts[0], before.parts[0], "unknown future consumed keys take the safe fresh-row path");
  assert.equal(appearance.parts[1], before.parts[1]);

  const renamedTree = structuredClone(descriptor);
  renamedTree.assembly.root.children[1].name = "renamed only in the structure tree";
  const renamed = buildComposedPackageMeshData(renamedTree, { a, b }, { previous: before });
  assert.equal(renamed.parts[1], before.parts[1], "tree-only metadata does not rebuild the render row");
  assert.notEqual(renamed.assemblyRoot.children[1], before.assemblyRoot.children[1]);
  assert.equal(renamed.assemblyRoot.children[1].name, "renamed only in the structure tree");

  const changedTopology = { ...b, parts: b.parts.map((part) => ({ ...part, triangleCount: 7 })) };
  const topology = buildComposedPackageMeshData(structuredClone(descriptor), { a, b: changedTopology }, { previous: before });
  assert.notEqual(topology.parts[1], before.parts[1], "selector triangle ranges follow the exact component parts array");
  assert.equal(topology.parts[0], before.parts[0]);

  const partial = buildComposedPackageMeshData(structuredClone(descriptor), { a }, { previous: before });
  assert.deepEqual(partial.parts.map((part) => part.id), ["first", "repeat"]);
  assert.equal(partial.parts[0], before.parts[0]);
  assert.equal(partial.parts[1], before.parts[2]);
  assert.deepEqual(partial.missingComponentIds, ["b"]);
});

test("duplicate occurrence ids never borrow a prior row by id", () => {
  const { descriptor, a, b } = reuseFixture();
  const before = buildComposedPackageMeshData(descriptor, { a, b });
  const duplicate = structuredClone(descriptor);
  duplicate.occurrences[1].id = duplicate.occurrences[0].id;
  duplicate.assembly.root.children[1].id = duplicate.occurrences[0].id;
  const after = buildComposedPackageMeshData(duplicate, { a, b }, { previous: before });
  assert.notEqual(after.parts[0], before.parts[0]);
  assert.notEqual(after.parts[1], before.parts[0]);
});

test("mutating the same descriptor object cannot masquerade as an immutable occurrence revision", () => {
  const { descriptor, a, b } = reuseFixture();
  descriptor.occurrences[0].material = { roughness: 0.42 };
  const before = buildComposedPackageMeshData(descriptor, { a, b });
  descriptor.occurrences[0].transform = [...descriptor.occurrences[0].transform];
  descriptor.occurrences[0].transform[3] = 91;
  descriptor.occurrences[0].material.roughness = 0.19;
  const after = buildComposedPackageMeshData(descriptor, { a, b }, { previous: before });
  assert.notEqual(after.parts[0], before.parts[0]);
  assert.equal(after.parts[0].transform[3], 91);
  assert.equal(after.parts[0].material.roughness, 0.19);
  assert.equal(before.parts[0].material.roughness, 0.42, "descriptor mutation cannot alter the displayed predecessor");
  assert.equal(after.parts[1], before.parts[1]);
});

test("composed package drives a per-occurrence override colour through the material (hex, not vertex baking)", () => {
  // The baked composer wrote override floats straight into per-occurrence vertex colours; the
  // shared-geometry composer can't (geometry is shared), so it routes the override to part.color
  // as an sRGB hex string the viewer parses via readSourceColor -> new THREE.Color. Encoding the
  // linear override [r,g,b] to sRGB hex makes that round-trip land on the same linear albedo the
  // baked path shaded.
  const descriptor = {
    occurrences: [
      // linear black-ish grey, the way a dark-anodized part authors its occurrence colour.
      { id: "o1.1", name: "dark", component: "cA", transform: IDENTITY_4X4, color: [0.1, 0.095, 0.09, 1.0] }
    ],
    assembly: {
      root: {
        id: "o1",
        name: "demo",
        nodeType: "assembly",
        children: [{ id: "o1.1", name: "dark", nodeType: "part", children: [] }]
      }
    }
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

test("composed package carries named material identity and multiplies source alpha", () => {
  const component = unitTriangleComponentMeshData();
  component.parts[0].color = "#123456";
  component.parts[0].opacity = 0.5;
  const appearance = {
    materials: { paint: { name: "Red paint", baseColor: "#CC1122", opacity: 0.4 } },
    assignments: { "o1.1": "paint" }
  };
  const descriptor = {
    appearance,
    occurrences: [{
      id: "o1.1", name: "painted", component: "cA", transform: IDENTITY_4X4,
      baseColor: "#CC1122", materialId: "paint", materialName: "Red paint",
      material: { roughness: 0.42, metalness: 0.03, clearcoat: 0, clearcoatRoughness: 0.26, opacity: 0.4 }
    }],
    assembly: { root: { id: "o1", name: "demo", nodeType: "assembly", children: [
      { id: "o1.1", name: "painted", nodeType: "part", children: [] }
    ] } }
  };
  const composed = buildComposedPackageMeshData(descriptor, { cA: component });
  assert.equal(composed.appearance, appearance);
  assert.equal(composed.parts[0].color, "#CC1122");
  assert.equal(composed.parts[0].sourceColor, "#123456");
  assert.equal(composed.parts[0].sourceOpacity, 0.5);
  assert.equal(composed.parts[0].materialId, "paint");
  assert.equal(composed.parts[0].materialName, "Red paint");
  assert.equal(composed.parts[0].opacity, 0.2);
  assert.equal(composed.assemblyRoot.children[0].materialId, "paint");
  assert.equal(composed.assemblyRoot.children[0].sourceColor, "#123456");
  assert.equal(composed.assemblyRoot.children[0].sourceOpacity, 0.5);
});

test("composed package preserves an exact zero source alpha before material scaling", () => {
  const component = unitTriangleComponentMeshData();
  const descriptor = {
    occurrences: [{
      id: "o1.1", component: "cA", transform: IDENTITY_4X4,
      color: [0.1, 0.2, 0.3, 0], material: { opacity: 0.4 }
    }],
    assembly: { root: { id: "o1", nodeType: "assembly", children: [
      { id: "o1.1", nodeType: "part", children: [] }
    ] } }
  };
  const composed = buildComposedPackageMeshData(descriptor, { cA: component });
  assert.equal(composed.parts[0].sourceOpacity, 0);
  assert.equal(composed.parts[0].opacity, 0);
  assert.equal(composed.assemblyRoot.children[0].sourceOpacity, 0);
});

test("composed package mesh records missing components instead of throwing", () => {
  const descriptor = {
    occurrences: [
      { id: "o1.1", name: "present", component: "cA", transform: IDENTITY_4X4 },
      { id: "o1.2", name: "absent", component: "cMissing", transform: IDENTITY_4X4 }
    ],
    assembly: {
      root: {
        id: "o1",
        name: "demo",
        nodeType: "assembly",
        children: [
          { id: "o1.1", name: "present", nodeType: "part", children: [] },
          { id: "o1.2", name: "absent", nodeType: "part", children: [] }
        ]
      }
    }
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

  // An assembly with the same single occurrence keeps its recorded structure tree.
  const assemblyDescriptor = {
    ...partDescriptor,
    entryKind: "assembly",
    assembly: {
      root: {
        id: "o1",
        name: "bracket",
        nodeType: "assembly",
        children: [{ id: "o1.1", name: "bracket", nodeType: "part", children: [] }]
      }
    }
  };
  const assembly = buildComposedPackageMeshData(assemblyDescriptor, { cA: unitTriangleComponentMeshData() });
  assert.ok(assembly.assemblyRoot, "an assembly keeps its structure tree");
  assert.equal(assembly.assemblyRoot.nodeType, "assembly");
});
