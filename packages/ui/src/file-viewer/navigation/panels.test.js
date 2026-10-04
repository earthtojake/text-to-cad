import assert from "node:assert/strict";
import test from "node:test";

import { nextOpenPanel, resolveOpenPanel } from "./panels.js";
import * as panels from "./panels.js";

/**
 * The panels contract: a surface declares what the nav row draws for it, and exactly one of them
 * is open. The file explorer is not a panel: it is the popover the navbar's file name opens.
 */

/** A host renderer's own panel, which replaces the body. */
const SOURCE_PANEL = "source";
const source = { id: SOURCE_PANEL, label: "View source", icon: () => null, content: "body" };
const other = { id: "other", label: "Other", icon: () => null, content: "slot" };

test("the panels module is the rule alone", () => {
  assert.deepEqual(Object.keys(panels).sort(), ["nextOpenPanel", "resolveOpenPanel"]);
});

test("a file opened directly opens with nothing beside it, unless its own declaration asks", () => {
  assert.equal(resolveOpenPanel([], null), null);
  assert.equal(resolveOpenPanel([{ ...source, defaultOpen: true }], null)?.id, SOURCE_PANEL);
  // A retired panel id a host stored cannot occupy the column.
  for (const retired of ["cad-display", "cad-file", "tree"]) assert.equal(resolveOpenPanel([], retired), null);
});

test("one panel is open at a time, whichever was up before", () => {
  assert.equal(nextOpenPanel("", SOURCE_PANEL), SOURCE_PANEL);
  assert.equal(nextOpenPanel(SOURCE_PANEL, SOURCE_PANEL), "");
  assert.equal(nextOpenPanel("other", SOURCE_PANEL), SOURCE_PANEL);
  assert.equal(resolveOpenPanel([source, other], ""), null);
});
