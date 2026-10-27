import assert from "node:assert/strict";
import test from "node:test";

import { openUntilChoice } from "./treeExpansion.js";

const node = (id, ...children) => ({ id, children });
const open = (roots, idOf) => [...openUntilChoice(roots, item => item.children, idOf)].sort();

test("a tree opens until there is a choice: its roots, then every node with one child, all the way down", () => {
  const tree = [
    node("parts",
      node("diodes", node("D1", node("D1.1"), node("D1.2"))),
      node("connectors", node("J1", node("J1.1"), node("J1.2")), node("J2", node("J2.1")))),
    node("nets", node("VBUS", node("J1.1"), node("R1.1")), node("NC", node("J2.1"))),
  ];
  // The roots open whatever they hold; Diodes holds one part, so it opens on it; a part with two
  // pads is a choice and stays shut; Connectors holds two and stays shut, yet J2 under it holds
  // one pad and is open for when Connectors opens; a net with one pad opens on it.
  assert.deepEqual(open(tree), ["J2", "NC", "diodes", "nets", "parts"]);
  // A leaf, a root among them, has nothing to open; a chain of single children opens to its end.
  assert.deepEqual(open([node("lone"), node("base", node("link1", node("link2", node("tool"))))]), ["base", "link1", "link2"]);
  assert.deepEqual(open([]), []);
});

test("ids come from the caller: a tree with no visible root opens a drawing's layers on their one block, not their several", () => {
  const drawing = { name: "", inserts: [{ name: "CUT", inserts: [] }, { name: "HARDWARE", inserts: [{ name: "99" }, { name: "9B" }] }, { name: "BOLTS", inserts: [{ name: "A1" }] }] };
  const opened = openUntilChoice([drawing], layer => layer.inserts, layer => layer.name);
  opened.delete("");
  assert.deepEqual([...opened], ["BOLTS"]);
});
