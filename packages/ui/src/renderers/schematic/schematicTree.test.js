import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

import { createSchematicIndex } from "@cad/core/lib/schematic2d/schematicIndex.js";
import { buildSchematicTree, buildSheetTree, schematicTreeNodeIds, sheetOfSelector } from "./schematicTree.js";

const PAYLOAD = JSON.parse(fs.readFileSync(new URL("./__fixtures__/schematic.plot.json", import.meta.url), "utf8"));
const index = createSchematicIndex(PAYLOAD.schematic);

test("the Circuit is the parts in their sheets' blocks, each with its pins, then the nets with theirs, loose pins together", () => {
  const tree = buildSchematicTree(index);
  assert.deepEqual(tree.roots.map(node => [node.id, node.label, node.detail]), [
    ["sheet:/", "divider", "3"], ["sheet:/Load/", "Load", "2"], ["group:nets", "Nets", "5"]
  ]);
  assert.deepEqual(tree.roots[0].picks, ["#J1", "#R1", "#R2"]);
  const r1 = tree.nodesById.get("part:R1");
  assert.deepEqual([r1.detail, r1.children.map(pin => [pin.id, pin.label, pin.detail])], ["10k", [["pin:R1.1", "1", "+5V"], ["pin:R1.2", "2", "/MID"]]]);
  const nets = tree.nodesById.get("group:nets").children;
  assert.deepEqual(nets.map(node => node.id), ["net:/MID", "net:+5V", "net:GND", "net:VOUT", "group:unconnected"]);
  assert.deepEqual(tree.nodesById.get("net:/MID").children.map(pin => pin.label), ["C1.1", "R1.2", "R2.1"]);
  assert.deepEqual(tree.nodesById.get("group:unconnected").children.map(node => node.id), ["net:unconnected-(R3-Pad2)"]);
  assert.deepEqual(schematicTreeNodeIds("#R1.2"), ["pin:R1.2", "netpin:R1.2"]);
  assert.deepEqual(schematicTreeNodeIds("#net:/MID"), ["net:/MID"]);
  assert.deepEqual(schematicTreeNodeIds("#sheet:/Load/"), []);
});

test("the Hierarchy is the root and the sheets it places, each its page", () => {
  const tree = buildSheetTree(index);
  assert.deepEqual(tree.roots.map(node => [node.path, node.label, node.detail, node.children.map(child => [child.path, child.label, child.detail])]),
    [["/", "divider", "1", [["/Load/", "Load", "2"]]]]);
  assert.equal(sheetOfSelector("#sheet:Load"), "/Load/");
  assert.equal(sheetOfSelector("#R1"), null);
});
