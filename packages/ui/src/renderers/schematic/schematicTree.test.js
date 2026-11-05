import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

import { createSchematicIndex } from "@cad/core/lib/schematic2d/schematicIndex.js";
import { buildSchematicTree, buildSheetTree, schematicDetail, schematicRowOwners, schematicTreeNodeIds, sheetOfSelector } from "./schematicTree.js";

const PAYLOAD = JSON.parse(fs.readFileSync(new URL("./__fixtures__/schematic.plot.json", import.meta.url), "utf8"));
const index = createSchematicIndex(PAYLOAD.schematic);

test("the Parts are the parts in their sheets' blocks and the Nets a list of their own, loose pins together; a part's pins and a net's are its detail", () => {
  const tree = buildSchematicTree(index);
  assert.deepEqual(tree.parts.roots.map(node => [node.id, node.label, node.detail]), [["sheet:/", "divider", "3"], ["sheet:/Load/", "Load", "2"]]);
  assert.deepEqual(tree.parts.roots[0].picks, ["#J1", "#R1", "#R2"]);
  const r1 = tree.parts.nodesById.get("part:R1");
  assert.deepEqual([r1.detail, r1.children], ["10k", []]);
  // The Parts' search reads each part with its pins.
  assert.deepEqual(tree.partsSearch[0].children.find(part => part.id === "part:R1").children.map(pin => [pin.id, pin.label, pin.detail]),
    [["pin:R1.1", "1", "+5V"], ["pin:R1.2", "2", "/MID"]]);
  assert.deepEqual(tree.nets.roots.map(node => node.id), ["net:/MID", "net:+5V", "net:GND", "net:VOUT", "group:unconnected"]);
  assert.deepEqual(tree.nets.nodesById.get("group:unconnected").children.map(node => node.id), ["net:unconnected-(R3-Pad2)"]);
  assert.deepEqual(schematicTreeNodeIds("#R1"), ["part:R1"]);
  assert.deepEqual(schematicTreeNodeIds("#R1.2"), []);
  assert.deepEqual(schematicRowOwners(index, "#R1.2"), ["part:R1", "net:/MID"]);
  assert.deepEqual(schematicTreeNodeIds("#net:/MID"), ["net:/MID"]);
  assert.deepEqual(schematicTreeNodeIds("#sheet:/Load/"), []);
  const part = schematicDetail(index, "#R1.2");
  assert.deepEqual([part.id, part.count, part.rows.map(pin => [pin.pick, pin.label, pin.detail])], ["part:R1", "2 pins", [["#R1.1", "1", "+5V"], ["#R1.2", "2", "/MID"]]]);
  const net = schematicDetail(index, "#net:/MID");
  assert.deepEqual([net.label, net.count, net.rows.map(pin => pin.label)], ["/MID", "3 pins", ["C1.1", "R1.2", "R2.1"]]);
  assert.equal(schematicDetail(index, "#sheet:/Load/"), null);
});

test("the Hierarchy is the root and the sheets it places, each its page", () => {
  const tree = buildSheetTree(index);
  assert.deepEqual(tree.roots.map(node => [node.path, node.label, node.detail, node.children.map(child => [child.path, child.label, child.detail])]),
    [["/", "divider", "1", [["/Load/", "Load", "2"]]]]);
  assert.equal(sheetOfSelector("#sheet:Load"), "/Load/");
  assert.equal(sheetOfSelector("#R1"), null);
});
