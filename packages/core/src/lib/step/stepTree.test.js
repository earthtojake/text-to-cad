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

// Occurrence tokens as cadgen mints them (`o:` + 12 hex) and element names (`f:`, `e:` and the
// element's lineage); a ref is `<occurrence token>/<element name>`. The values are arbitrary,
// their shape is the grammar's.
const BASE = "o:1a2b3c4d5e6f";
const LID = "o:2b3c4d5e6f70";
const PAD = "o:7c8d9e0f1a2b";
const ARM = "o:9e8d7c6b5a40";
const SERVO = "o:3f2a9c1d7e5b";
const GRIPPER = "o:a1b2c3d4e5f6";
const ELSEWHERE = "o:0f1e2d3c4b5a";
const F1 = "f:arm.extrude1.3";
const F2 = "f:arm.hole1.1";
const E1 = "e:arm.extrude1.5";
const ref = (occurrence, element) => `${occurrence}/${element}`;

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
  // A body is no reference (the occurrence names it), so the runtime hands the tree an
  // occurrence, its faces and its edges, and the tree shows each element by its name.
  const augmented = buildStepTreeRootWithTopology({
    root,
    references: [
      {
        id: `topology|part-a|occurrence|${BASE}`,
        selectorType: "occurrence",
        displaySelector: BASE,
        summary: "base_plate",
        partId: "part-a",
        rowIndex: 0
      },
      {
        id: `topology|part-a|face|${ref(BASE, F1)}`,
        selectorType: "face",
        displaySelector: ref(BASE, F1),
        occurrenceId: BASE,
        summary: "plane area=100",
        partId: "part-a",
        rowIndex: 0
      },
      {
        id: `topology|part-a|edge|${ref(BASE, E1)}`,
        selectorType: "edge",
        displaySelector: ref(BASE, E1),
        occurrenceId: BASE,
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
      ["topology-face", `Face ${F1}`, "plane area=100"],
      ["topology-edge", `Edge ${E1}`, "line length=10"]
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
      ["topology-face", `Face ${F1}`, "plane area=100"],
      ["topology-edge", `Edge ${E1}`, "line length=10"]
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
        id: `topology|root|face|${ref(BASE, F1)}`,
        selectorType: "face",
        displaySelector: ref(BASE, F1),
        occurrenceId: BASE,
        partId: "root",
        rowIndex: 0
      },
      {
        id: `topology|root|face|${ref(LID, F1)}`,
        selectorType: "face",
        displaySelector: ref(LID, F1),
        occurrenceId: LID,
        partId: "root",
        rowIndex: 1
      }
    ]
  });
  const occurrence = augmented.children[0];

  assert.equal(occurrence.nodeType, "topology-occurrence");
  assert.equal(occurrence.id, `step-topology:root:occurrence:${BASE}`);
  assert.equal(occurrence.topologyReferenceId, occurrence.id);
  assert.deepEqual(
    augmented.children.map((child) => [child.nodeType, child.displaySelector, child.children.length]),
    [
      ["topology-occurrence", BASE, 1],
      ["topology-occurrence", LID, 1]
    ]
  );
});

test("STEP tree flattens the occurrence wrapper that duplicates its part", () => {
  // The part IS the occurrence ARM: its own elements sit directly under it, while another
  // occurrence's keep their wrapper. An element's owner is read off its ref.
  const root = {
    id: ARM,
    occurrenceId: ARM,
    nodeType: "part",
    displayName: "triangular_prism",
    children: []
  };
  const augmented = buildStepTreeRootWithTopology({
    root,
    references: [
      {
        id: `topology|${ARM}|face|${ref(ARM, F1)}`,
        selectorType: "face",
        displaySelector: ref(ARM, F1),
        partId: ARM,
        rowIndex: 0
      },
      {
        id: `topology|${ARM}|face|${ref(LID, F1)}`,
        selectorType: "face",
        displaySelector: ref(LID, F1),
        partId: ARM,
        rowIndex: 1
      }
    ]
  });

  assert.deepEqual(
    augmented.children.map((child) => [child.nodeType, child.displaySelector, child.children.length]),
    [
      ["topology-occurrence", LID, 1],
      ["topology-face", ref(ARM, F1), 0]
    ]
  );
});

test("STEP tree flattens the occurrence wrapper of a part named by its token", () => {
  const root = {
    id: "root",
    occurrenceId: BASE,
    nodeType: "assembly",
    displayName: "root assembly",
    children: [
      {
        id: PAD,
        occurrenceId: PAD,
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
        id: PAD,
        selectorType: "occurrence",
        displaySelector: PAD,
        summary: "cube_top_pad",
        partId: PAD,
        rowIndex: 0
      },
      {
        id: ref(PAD, F2),
        selectorType: "face",
        displaySelector: ref(PAD, F2),
        occurrenceId: PAD,
        partId: PAD,
        rowIndex: 0
      },
      {
        id: ref(LID, F1),
        selectorType: "face",
        displaySelector: ref(LID, F1),
        occurrenceId: LID,
        partId: PAD,
        rowIndex: 1
      }
    ]
  });

  assert.deepEqual(
    augmented.children[0].children.map((child) => [child.nodeType, child.displaySelector, child.children.length]),
    [
      ["topology-occurrence", LID, 1],
      ["topology-face", ref(PAD, F2), 0]
    ]
  );

  assert.deepEqual(
    flattenVisibleStepTreeRows(augmented, ["root", PAD]).map((row) => [row.id, row.depth]),
    [
      ["root", 0],
      [PAD, 1],
      [`step-topology:${PAD}:occurrence:${LID}`, 2],
      [`step-topology:${PAD}:face:${ref(PAD, F2)}`, 2]
    ]
  );
});

test("STEP tree can assign topology references to assembly parts by occurrence id", () => {
  // A reference's occurrence is a part's when it IS that part's occurrence (or one of the
  // leaves the part lists); a token is never a prefix of another, so nothing matches by one.
  const root = {
    id: "root",
    occurrenceId: BASE,
    nodeType: "assembly",
    displayName: "root assembly",
    children: [
      {
        id: "servo-part",
        occurrenceId: SERVO,
        nodeType: "part",
        displayName: "servo",
        children: []
      },
      {
        id: "gripper-part",
        occurrenceId: GRIPPER,
        nodeType: "part",
        displayName: "gripper",
        children: []
      }
    ]
  };
  const references = [
    {
      id: BASE,
      selectorType: "occurrence",
      displaySelector: BASE,
      summary: "root"
    },
    {
      id: SERVO,
      selectorType: "occurrence",
      displaySelector: SERVO,
      summary: "servo"
    },
    {
      id: ref(SERVO, F1),
      selectorType: "face",
      displaySelector: ref(SERVO, F1),
      occurrenceId: SERVO,
      summary: "plane area=10"
    },
    {
      id: ref(GRIPPER, E1),
      selectorType: "edge",
      displaySelector: ref(GRIPPER, E1),
      summary: "line length=4"
    },
    {
      id: "manual-part-ref",
      selectorType: "face",
      displaySelector: ref(ELSEWHERE, F1),
      occurrenceId: ELSEWHERE,
      partId: "explicit-part",
      summary: "explicit part"
    }
  ];

  const assigned = assignStepTreeTopologyReferencePartIds(root, references);

  assert.deepEqual(
    assigned.map((reference) => reference.partId || ""),
    ["", "servo-part", "servo-part", "gripper-part", "explicit-part"]
  );
  assert.equal(references[1].partId, undefined);

  const augmented = buildStepTreeRootWithTopology({ root, references: assigned });
  assert.deepEqual(
    augmented.children.map((child) => [
      child.id,
      child.children.map((topologyChild) => topologyChild.displaySelector)
    ]),
    [
      ["servo-part", [ref(SERVO, F1)]],
      ["gripper-part", [ref(GRIPPER, E1)]]
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
        occurrenceId: BASE,
        nodeType: "part",
        displayName: "part A",
        children: []
      },
      {
        id: "part-b",
        occurrenceId: LID,
        nodeType: "part",
        displayName: "part B",
        children: []
      }
    ]
  };
  const references = [
    {
      id: ref(BASE, F1),
      selectorType: "face",
      displaySelector: ref(BASE, F1),
      occurrenceId: BASE,
      partId: "part-a",
      summary: "plane area=10"
    },
    {
      id: ref(LID, F1),
      selectorType: "face",
      displaySelector: ref(LID, F1),
      occurrenceId: LID,
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
      ["part-b", [ref(LID, F1)]]
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
        id: ref(BASE, F1),
        selectorType: "face",
        displaySelector: ref(BASE, F1),
        occurrenceId: BASE,
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
    [["topology-face", ref(BASE, F1)]]
  );
  assert.deepEqual(
    flattenVisibleStepTreeRows(augmented, [folder.id], { omitRoot: true })
      .map((row) => [row.nodeType, row.label, row.depth]),
    [
      ["topology-folder", "base_plate", 0],
      ["topology-face", `Face ${F1}`, 1]
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
