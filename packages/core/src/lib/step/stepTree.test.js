import assert from "node:assert/strict";
import { test } from "node:test";

import {
  assignStepTreeTopologyReferencePartIds,
  buildStepTreeRoot,
  buildStepTreeRootWithTopology,
  collectStepTreeAncestorIds,
  flattenVisibleStepTreeRows,
  STEP_MODEL_RENDER_PART_ID,
  STEP_MODEL_ROOT_ID,
  stepTreeRootChildIndexForNode,
  stepTreeNodeLeafPartIds
} from "./stepTree.js";

const nestedRoot = {
  id: "root",
  nodeType: "assembly",
  displayName: "root assembly",
  children: [
    {
      id: "sub",
      nodeType: "assembly",
      displayName: "sub assembly",
      children: [
        {
          id: "leaf-a",
          nodeType: "part",
          displayName: "leaf A",
          children: []
        },
        {
          id: "leaf-b",
          nodeType: "part",
          displayName: "leaf B",
          children: []
        }
      ]
    },
    {
      id: "leaf-c",
      nodeType: "part",
      displayName: "leaf C",
      children: []
    }
  ]
};

test("visible STEP tree rows follow independent expansion state", () => {
  assert.deepEqual(
    flattenVisibleStepTreeRows(nestedRoot, []).map((row) => row.id),
    ["root"]
  );
  assert.deepEqual(
    flattenVisibleStepTreeRows(nestedRoot, ["root"]).map((row) => [row.id, row.depth, row.expanded]),
    [
      ["root", 0, true],
      ["sub", 1, false],
      ["leaf-c", 1, false]
    ]
  );
  assert.deepEqual(
    flattenVisibleStepTreeRows(nestedRoot, ["root", "sub"]).map((row) => row.id),
    ["root", "sub", "leaf-a", "leaf-b", "leaf-c"]
  );
});

test("visible STEP tree rows can elide a wrapper root assembly", () => {
  assert.deepEqual(
    flattenVisibleStepTreeRows(nestedRoot, [], { omitRoot: true }).map((row) => [row.id, row.depth, row.expanded]),
    [
      ["sub", 0, false],
      ["leaf-c", 0, false]
    ]
  );
  assert.deepEqual(
    flattenVisibleStepTreeRows(nestedRoot, ["sub"], { omitRoot: true }).map((row) => [row.id, row.depth]),
    [
      ["sub", 0],
      ["leaf-a", 1],
      ["leaf-b", 1],
      ["leaf-c", 0]
    ]
  );
});

test("visible STEP tree rows can limit only root assembly items", () => {
  const root = {
    id: "root-many",
    nodeType: "assembly",
    children: Array.from({ length: 18 }, (_, index) => ({
      id: `root-child-${index + 1}`,
      nodeType: "part",
      displayName: `Root child ${index + 1}`,
      children: []
    }))
  };

  assert.deepEqual(
    flattenVisibleStepTreeRows(root, [], {
      omitRoot: true,
      rootChildLimit: 15,
      showAllRootChildren: false
    }).map((row) => row.id),
    Array.from({ length: 15 }, (_, index) => `root-child-${index + 1}`)
  );
  assert.deepEqual(
    flattenVisibleStepTreeRows(root, [], {
      omitRoot: true,
      rootChildLimit: 15,
      showAllRootChildren: true
    }).map((row) => row.id),
    Array.from({ length: 18 }, (_, index) => `root-child-${index + 1}`)
  );
});

test("root item limit does not limit nested assembly descendants", () => {
  const root = {
    id: "root-nested-limit",
    nodeType: "assembly",
    children: [
      {
        id: "large-sub",
        nodeType: "assembly",
        displayName: "large sub assembly",
        children: Array.from({ length: 18 }, (_, index) => ({
          id: `large-sub-child-${index + 1}`,
          nodeType: "part",
          displayName: `Large sub child ${index + 1}`,
          children: []
        }))
      },
      {
        id: "root-hidden",
        nodeType: "part",
        displayName: "hidden root child",
        children: []
      }
    ]
  };

  assert.deepEqual(
    flattenVisibleStepTreeRows(root, ["large-sub"], {
      omitRoot: true,
      rootChildLimit: 1,
      showAllRootChildren: false
    }).map((row) => row.id),
    [
      "large-sub",
      ...Array.from({ length: 18 }, (_, index) => `large-sub-child-${index + 1}`)
    ]
  );
});

test("STEP tree query keeps matching descendants visible with ancestors", () => {
  assert.deepEqual(
    flattenVisibleStepTreeRows(nestedRoot, [], { query: "leaf b" }).map((row) => row.id),
    ["root", "sub", "leaf-b"]
  );
});

test("STEP tree query supports elided wrapper roots", () => {
  assert.deepEqual(
    flattenVisibleStepTreeRows(nestedRoot, [], { query: "leaf b", omitRoot: true }).map((row) => row.id),
    ["sub", "leaf-b"]
  );
});

test("STEP tree leaf ids include nested descendant parts", () => {
  assert.deepEqual(stepTreeNodeLeafPartIds(nestedRoot.children[0]), ["leaf-a", "leaf-b"]);
});

test("plain STEP parts get a synthetic selectable root", () => {
  const root = buildStepTreeRoot({
    selectedEntry: {
      file: "parts/bracket.step",
      kind: "part"
    },
    meshData: {
      bounds: {
        min: [0, 0, 0],
        max: [1, 2, 3]
      }
    }
  });
  assert.equal(root.id, STEP_MODEL_ROOT_ID);
  assert.equal(root.displayName, "bracket.step");
  assert.deepEqual(root.leafPartIds, [STEP_MODEL_RENDER_PART_ID]);
});

test("STEP tree topology rows attach below their owning part", () => {
  const root = {
    id: "root",
    nodeType: "assembly",
    displayName: "root assembly",
    children: [
      {
        id: "part-a",
        nodeType: "part",
        displayName: "part A",
        children: []
      }
    ]
  };
  const augmented = buildStepTreeRootWithTopology({
    root,
    references: [
      {
        id: "topology|part-a|occurrence|fixture.base",
        selectorType: "occurrence",
        displaySelector: "fixture.base",
        summary: "base_plate",
        partId: "part-a",
        rowIndex: 0
      },
      {
        id: "topology|part-a|shape|fixture.base.s1",
        selectorType: "shape",
        displaySelector: "fixture.base.s1",
        occurrenceId: "fixture.base",
        summary: "base_plate solid volume=1200",
        partId: "part-a",
        pickData: {
          name: "base_plate"
        },
        rowIndex: 0
      },
      {
        id: "topology|part-a|face|fixture.base.f1",
        selectorType: "face",
        displaySelector: "fixture.base.f1",
        occurrenceId: "fixture.base",
        shapeId: "fixture.base.s1",
        summary: "plane area=100",
        partId: "part-a",
        rowIndex: 0
      },
      {
        id: "topology|part-a|edge|fixture.base.e1",
        selectorType: "edge",
        displaySelector: "fixture.base.e1",
        occurrenceId: "fixture.base",
        shapeId: "fixture.base.s1",
        summary: "line length=10",
        partId: "part-a",
        rowIndex: 0
      }
    ]
  });

  assert.equal(root.children[0].children.length, 0);
  assert.deepEqual(
    augmented.children[0].children.map((child) => [child.nodeType, child.displayName, child.detail]),
    [
      ["topology-shape", "base_plate", "base_plate solid volume=1200"],
      ["topology-face", "Face f1", "plane area=100"],
      ["topology-edge", "Edge e1", "line length=10"]
    ]
  );

  assert.deepEqual(
    flattenVisibleStepTreeRows(augmented, [
      "root",
      "part-a"
    ]).map((row) => [row.nodeType, row.label, row.detail]),
    [
      ["assembly", "root assembly", ""],
      ["part", "part A", ""],
      ["topology-shape", "base_plate", "base_plate solid volume=1200"],
      ["topology-face", "Face f1", "plane area=100"],
      ["topology-edge", "Edge e1", "line length=10"]
    ]
  );
});

test("STEP tree keeps occurrence rows when one part owns multiple topology occurrences", () => {
  const root = {
    id: "root",
    nodeType: "part",
    displayName: "part",
    children: []
  };
  const augmented = buildStepTreeRootWithTopology({
    root,
    references: [
      {
        id: "topology|part-a|face|fixture.base.f1",
        selectorType: "face",
        displaySelector: "fixture.base.f1",
        occurrenceId: "fixture.base",
        partId: "root",
        rowIndex: 0
      },
      {
        id: "topology|part-a|face|fixture.lid.f1",
        selectorType: "face",
        displaySelector: "fixture.lid.f1",
        occurrenceId: "fixture.lid",
        partId: "root",
        rowIndex: 1
      }
    ]
  });
  const occurrence = augmented.children[0];

  assert.equal(occurrence.nodeType, "topology-occurrence");
  assert.equal(occurrence.id, "step-topology:root:occurrence:fixture.base");
  assert.equal(occurrence.topologyReferenceId, occurrence.id);
  assert.deepEqual(
    augmented.children.map((child) => [child.nodeType, child.displaySelector, child.children.length]),
    [
      ["topology-occurrence", "fixture.base", 1],
      ["topology-occurrence", "fixture.lid", 1]
    ]
  );
});

test("STEP tree flattens duplicate semantic occurrence wrappers", () => {
  const root = {
    id: "o1.6",
    occurrenceId: "o1.6",
    nodeType: "part",
    displayName: "triangular_prism",
    children: []
  };
  const augmented = buildStepTreeRootWithTopology({
    root,
    references: [
      {
        id: "topology|o1.6|face|triangular_prism.f1",
        selectorType: "face",
        displaySelector: "triangular_prism.f1",
        occurrenceId: "triangular_prism",
        partId: "o1.6",
        rowIndex: 0
      },
      {
        id: "topology|o1.6|face|fixture.lid.f1",
        selectorType: "face",
        displaySelector: "fixture.lid.f1",
        occurrenceId: "fixture.lid",
        partId: "o1.6",
        rowIndex: 1
      }
    ]
  });

  assert.deepEqual(
    augmented.children.map((child) => [child.nodeType, child.displaySelector, child.children.length]),
    [
      ["topology-occurrence", "fixture.lid", 1],
      ["topology-face", "triangular_prism.f1", 0]
    ]
  );
});

test("STEP tree flattens duplicate numbered component occurrence wrappers", () => {
  const root = {
    id: "root",
    occurrenceId: "o1",
    nodeType: "assembly",
    displayName: "root assembly",
    children: [
      {
        id: "o1.7.1",
        occurrenceId: "o1.7.1",
        nodeType: "part",
        displayName: "cube_top_pad",
        children: []
      }
    ]
  };
  const augmented = buildStepTreeRootWithTopology({
    root,
    references: [
      {
        id: "o1.7.1",
        selectorType: "occurrence",
        displaySelector: "o1.7.1",
        summary: "cube_top_pad",
        partId: "o1.7.1",
        rowIndex: 0
      },
      {
        id: "o1.7.1.s1",
        selectorType: "shape",
        displaySelector: "o1.7.1.s1",
        occurrenceId: "o1.7.1",
        summary: "cube_top_pad solid volume=490",
        partId: "o1.7.1",
        rowIndex: 0
      },
      {
        id: "fixture.lid.f1",
        selectorType: "face",
        displaySelector: "fixture.lid.f1",
        occurrenceId: "fixture.lid",
        partId: "o1.7.1",
        rowIndex: 1
      }
    ]
  });

  assert.deepEqual(
    augmented.children[0].children.map((child) => [child.nodeType, child.displaySelector, child.children.length]),
    [
      ["topology-occurrence", "fixture.lid", 1],
      ["topology-shape", "o1.7.1.s1", 0]
    ]
  );

  assert.deepEqual(
    flattenVisibleStepTreeRows(augmented, ["root", "o1.7.1"]).map((row) => [row.id, row.depth]),
    [
      ["root", 0],
      ["o1.7.1", 1],
      ["step-topology:o1.7.1:occurrence:fixture.lid", 2],
      ["step-topology:o1.7.1:shape:o1.7.1.s1", 2]
    ]
  );
});

test("STEP tree can assign topology references to assembly parts by occurrence id", () => {
  const root = {
    id: "root",
    occurrenceId: "o1",
    nodeType: "assembly",
    displayName: "root assembly",
    children: [
      {
        id: "servo-part",
        occurrenceId: "o1.3.2",
        sourceOccurrenceId: "o1.4",
        nodeType: "part",
        displayName: "servo",
        children: []
      },
      {
        id: "gripper-part",
        occurrenceId: "o1.4",
        nodeType: "part",
        displayName: "gripper",
        children: []
      }
    ]
  };
  const references = [
    {
      id: "o1",
      selectorType: "occurrence",
      displaySelector: "o1",
      summary: "root"
    },
    {
      id: "o1.3.2",
      selectorType: "occurrence",
      displaySelector: "o1.3.2",
      summary: "servo"
    },
    {
      id: "o1.3.2.s1",
      selectorType: "shape",
      displaySelector: "o1.3.2.s1",
      occurrenceId: "o1.3.2",
      summary: "servo solid"
    },
    {
      id: "o1.3.2.f1",
      selectorType: "face",
      displaySelector: "o1.3.2.f1",
      occurrenceId: "o1.3.2",
      summary: "plane area=10"
    },
    {
      id: "o1.4.s1",
      selectorType: "shape",
      displaySelector: "o1.4.s1",
      occurrenceId: "o1.4",
      summary: "gripper solid"
    },
    {
      id: "manual-part-ref",
      selectorType: "shape",
      displaySelector: "o1.9.s1",
      occurrenceId: "o1.9",
      partId: "explicit-part",
      summary: "explicit part"
    }
  ];

  const assigned = assignStepTreeTopologyReferencePartIds(root, references);

  assert.deepEqual(
    assigned.map((reference) => reference.partId || ""),
    ["", "servo-part", "servo-part", "servo-part", "gripper-part", "explicit-part"]
  );
  assert.equal(references[1].partId, undefined);

  const augmented = buildStepTreeRootWithTopology({ root, references: assigned });
  assert.deepEqual(
    augmented.children.map((child) => [
      child.id,
      child.children.map((topologyChild) => topologyChild.displaySelector)
    ]),
    [
      ["servo-part", ["o1.3.2.s1", "o1.3.2.f1"]],
      ["gripper-part", ["o1.4.s1"]]
    ]
  );
});

test("STEP tree topology rows can be limited to loaded parts", () => {
  const root = {
    id: "root",
    occurrenceId: "o1",
    nodeType: "assembly",
    displayName: "root assembly",
    children: [
      {
        id: "part-a",
        occurrenceId: "o1.1",
        nodeType: "part",
        displayName: "part A",
        children: []
      },
      {
        id: "part-b",
        occurrenceId: "o1.2",
        nodeType: "part",
        displayName: "part B",
        children: []
      }
    ]
  };
  const references = [
    {
      id: "o1.1.f1",
      selectorType: "face",
      displaySelector: "o1.1.f1",
      occurrenceId: "o1.1",
      partId: "part-a",
      summary: "plane area=10"
    },
    {
      id: "o1.2.f1",
      selectorType: "face",
      displaySelector: "o1.2.f1",
      occurrenceId: "o1.2",
      partId: "part-b",
      summary: "plane area=20"
    }
  ];

  const augmented = buildStepTreeRootWithTopology({
    root,
    references,
    topologyPartIds: ["part-b"]
  });

  assert.deepEqual(
    augmented.children.map((child) => [
      child.id,
      child.children.map((topologyChild) => topologyChild.displaySelector)
    ]),
    [
      ["part-a", []],
      ["part-b", ["o1.2.f1"]]
    ]
  );
});

test("STEP tree flattens redundant topology occurrence rows for single STEP roots", () => {
  const root = {
    id: STEP_MODEL_ROOT_ID,
    nodeType: "part",
    displayName: "base_plate.step",
    children: []
  };
  const augmented = buildStepTreeRootWithTopology({
    root,
    references: [
      {
        id: "o1.f1",
        selectorType: "face",
        displaySelector: "o1.f1",
        occurrenceId: "o1",
        partId: STEP_MODEL_ROOT_ID,
        summary: "plane area=100"
      }
    ]
  });

  const folder = augmented.children[0];
  assert.equal(folder.nodeType, "topology-folder");
  assert.equal(folder.displayName, "base_plate");
  assert.equal(folder.visualOnly, true);
  assert.deepEqual(folder.leafPartIds, [STEP_MODEL_RENDER_PART_ID]);
  assert.deepEqual(
    folder.children.map((child) => [child.nodeType, child.displaySelector]),
    [["topology-face", "o1.f1"]]
  );
  assert.deepEqual(
    flattenVisibleStepTreeRows(augmented, [folder.id], { omitRoot: true })
      .map((row) => [row.nodeType, row.label, row.depth]),
    [
      ["topology-folder", "base_plate", 0],
      ["topology-face", "Face f1", 1]
    ]
  );
});

test("ancestor ids are collected without the selected node", () => {
  assert.deepEqual(collectStepTreeAncestorIds(nestedRoot, "leaf-b"), ["root", "sub"]);
});

test("root child index resolves direct children and descendants", () => {
  assert.equal(stepTreeRootChildIndexForNode(nestedRoot, "sub"), 0);
  assert.equal(stepTreeRootChildIndexForNode(nestedRoot, "leaf-b"), 0);
  assert.equal(stepTreeRootChildIndexForNode(nestedRoot, "leaf-c"), 1);
  assert.equal(stepTreeRootChildIndexForNode(nestedRoot, "root"), -1);
  assert.equal(stepTreeRootChildIndexForNode(nestedRoot, "missing"), -1);
});
