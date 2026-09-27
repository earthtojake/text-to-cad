import assert from "node:assert/strict";
import test from "node:test";

import {
  minimalAssemblyIsolationNodeIds,
  selectableViewerNodeIdsForExpandedTree,
} from "./assemblyIsolation.js";

const root = {
  id: "root",
  nodeType: "assembly",
  children: [
    {
      id: "assembly_a",
      nodeType: "assembly",
      children: [
        {
          id: "part_a1",
          nodeType: "part",
          children: []
        },
        {
          id: "part_a2",
          nodeType: "part",
          children: [
            {
              id: "part_a2_leaf",
              nodeType: "part",
              children: []
            }
          ]
        }
      ]
    },
    {
      id: "part_b",
      nodeType: "part",
      children: []
    }
  ]
};

test("minimal assembly isolation keeps only the highest selected ancestor", () => {
  assert.deepEqual(
    minimalAssemblyIsolationNodeIds(root, ["part_a1", "assembly_a"], { rootId: "root" }),
    ["assembly_a"]
  );
  assert.deepEqual(
    minimalAssemblyIsolationNodeIds(root, ["assembly_a", "part_a1", "part_b"], { rootId: "root" }),
    ["assembly_a", "part_b"]
  );
});

test("viewer selection follows the expanded tree frontier", () => {
  assert.deepEqual(
    selectableViewerNodeIdsForExpandedTree(root, [], { rootId: "root" }),
    ["assembly_a", "part_b"]
  );
  assert.deepEqual(
    selectableViewerNodeIdsForExpandedTree(root, ["assembly_a"], { rootId: "root" }),
    ["part_a1", "part_a2", "part_b"]
  );
  assert.deepEqual(
    selectableViewerNodeIdsForExpandedTree(root, ["assembly_a", "part_a2"], { rootId: "root" }),
    ["part_a1", "part_a2_leaf", "part_b"]
  );
});

test("viewer selection keeps expanded topology nodes selectable as component fallback", () => {
  assert.deepEqual(
    selectableViewerNodeIdsForExpandedTree(root, ["assembly_a", "part_a1"], {
      rootId: "root",
      topologyNodeIds: ["part_a1"]
    }),
    ["part_a1", "part_a2", "part_b"]
  );
});

test("viewer selection scopes expanded tree frontier to isolation roots", () => {
  assert.deepEqual(
    selectableViewerNodeIdsForExpandedTree(root, ["assembly_a"], {
      rootId: "root",
      isolatedNodeIds: ["assembly_a"]
    }),
    ["part_a1", "part_a2"]
  );
  assert.deepEqual(
    selectableViewerNodeIdsForExpandedTree(root, ["assembly_a", "part_a2"], {
      rootId: "root",
      isolatedNodeIds: ["assembly_a"]
    }),
    ["part_a1", "part_a2_leaf"]
  );
});
