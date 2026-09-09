import assert from "node:assert/strict";
import test from "node:test";

import { buildSidebarDirectoryTree, sidebarLabelForEntry } from "./sidebar.js";
import {
  buildBreadcrumbNodes,
  collapsedBreadcrumbNodes,
  ellipsisBreadcrumbMenuDirectory
} from "./breadcrumbs.js";

test("breadcrumb dropdown directories target adjacent siblings", () => {
  const selectedEntry = {
    file: "assemblies/robot/arm/base.step",
    kind: "part",
    source: { format: "step", path: "assemblies/robot/arm/base.step" }
  };
  const tree = buildSidebarDirectoryTree([
    selectedEntry,
    {
      file: "assemblies/robot/arm/forearm.step",
      kind: "part",
      source: { format: "step", path: "assemblies/robot/arm/forearm.step" }
    },
    {
      file: "assemblies/robot/wrist.step",
      kind: "part",
      source: { format: "step", path: "assemblies/robot/wrist.step" }
    },
    {
      file: "assemblies/fixtures/clamp.step",
      kind: "part",
      source: { format: "step", path: "assemblies/fixtures/clamp.step" }
    },
    {
      file: "benchmarks/block.step",
      kind: "part",
      source: { format: "step", path: "benchmarks/block.step" }
    }
  ], { rootName: "models" });

  const nodes = buildBreadcrumbNodes({
    directoryTree: tree,
    selectedEntry,
    selectedFileLabel: "base.step",
    selectedFileTitle: "assemblies/robot/arm/base.step"
  });

  assert.deepEqual(
    nodes.map((node) => `${node.type}:${node.id || node.label}`),
    [
      "directory:assemblies",
      "directory:assemblies/robot",
      "directory:assemblies/robot/arm",
      "entry:base.step"
    ]
  );
  assert.equal(nodes[0].menuDirectory.id, "");
  assert.equal(nodes[1].menuDirectory.id, "assemblies");
  assert.equal(nodes[2].menuDirectory.id, "assemblies/robot");
  assert.equal(nodes[3].menuDirectory.id, "assemblies/robot/arm");
  assert.deepEqual(
    nodes[3].menuDirectory.entries.map((entry) => entry.file).sort(),
    [
      "assemblies/robot/arm/base.step",
      "assemblies/robot/arm/forearm.step"
    ]
  );
});

test("the breadcrumb tail of a generated model reads as the file on disk", () => {
  // CadWorkspaceTopBar builds selectedFileLabel with sidebarLabelForEntry and
  // selectedFileTitle from entry.file, so both ends of the breadcrumb name the artifact.
  // This used to end in `moonwatch.py` -- a file that is not even in that directory.
  const selectedEntry = {
    file: "watches/moonwatch.step",
    kind: "assembly",
    sourceUrl: "/watches/moonwatch.step.json"
  };
  const tree = buildSidebarDirectoryTree([selectedEntry], { rootName: "models" });

  const nodes = buildBreadcrumbNodes({
    directoryTree: tree,
    selectedEntry,
    selectedFileLabel: sidebarLabelForEntry(selectedEntry),
    selectedFileTitle: String(selectedEntry.file)
  });

  const tail = nodes[nodes.length - 1];
  assert.equal(tail.type, "entry");
  assert.equal(tail.label, "moonwatch.step");
  assert.equal(tail.title, "watches/moonwatch.step");
});

test("breadcrumb helpers support collapsed paths", () => {
  const items = collapsedBreadcrumbNodes([
    { label: "models" },
    { label: "assemblies" },
    { label: "robot" },
    { label: "arm" },
    { label: "base.step" }
  ]);

  assert.equal(items.length, 4);
  assert.equal(items[1].type, "ellipsis");
  assert.deepEqual(items[1].nodes.map((node) => node.label), ["assemblies", "robot"]);
});

test("collapsed breadcrumb directories browse their own nested folders", () => {
  const selectedEntry = {
    file: "robots/tom/v2/printable/link.step",
    kind: "part",
    source: { format: "step", path: "robots/tom/v2/printable/link.step" }
  };
  const tree = buildSidebarDirectoryTree([
    selectedEntry,
    {
      file: "robots/tom/v2/raw/source.step",
      kind: "part",
      source: { format: "step", path: "robots/tom/v2/raw/source.step" }
    },
    {
      file: "robots/lerobot/base.step",
      kind: "part",
      source: { format: "step", path: "robots/lerobot/base.step" }
    }
  ], { rootName: "models" });

  const nodes = buildBreadcrumbNodes({
    directoryTree: tree,
    selectedEntry,
    selectedFileLabel: "link.step",
    selectedFileTitle: "robots/tom/v2/printable/link.step"
  });
  const collapsedItems = collapsedBreadcrumbNodes(nodes);
  const hiddenNodes = collapsedItems.find((item) => item.type === "ellipsis")?.nodes || [];
  const tomNode = hiddenNodes.find((node) => node.label === "tom");
  const v2Node = hiddenNodes.find((node) => node.label === "v2");

  assert.equal(tomNode.menuDirectory.id, "robots");
  assert.equal(ellipsisBreadcrumbMenuDirectory(tomNode).id, "robots/tom");
  assert.deepEqual(
    ellipsisBreadcrumbMenuDirectory(tomNode).directories.map((directory) => directory.id),
    ["robots/tom/v2"]
  );
  assert.equal(v2Node.menuDirectory.id, "robots/tom");
  assert.equal(ellipsisBreadcrumbMenuDirectory(v2Node).id, "robots/tom/v2");
  assert.deepEqual(
    ellipsisBreadcrumbMenuDirectory(v2Node).directories.map((directory) => directory.id).sort(),
    ["robots/tom/v2/printable", "robots/tom/v2/raw"]
  );
});
