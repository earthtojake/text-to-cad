import assert from "node:assert/strict";
import test from "node:test";

import {
  minimalAssemblyIsolationNodeIds,
  selectableTreeNodeIdsForIsolation
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
          children: []
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

test("tree selection during isolate excludes isolate roots but keeps descendants selectable", () => {
  assert.deepEqual(
    selectableTreeNodeIdsForIsolation(root, ["assembly_a", "part_a1"], "root"),
    ["part_a1", "part_a2"]
  );
  assert.deepEqual(
    selectableTreeNodeIdsForIsolation(root, ["part_a1", "part_b"], "root"),
    []
  );
  assert.deepEqual(
    selectableTreeNodeIdsForIsolation(root, [], "root"),
    ["assembly_a", "part_a1", "part_a2", "part_b"]
  );
});
