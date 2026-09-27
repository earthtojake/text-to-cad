import assert from "node:assert/strict";
import test from "node:test";

import {
  FILE_PANEL_TREE,
  nextOpenPanel,
  resolveOpenPanel,
  treePanel
} from "./panels.js";
import * as panels from "./panels.js";

/**
 * The panels contract: a surface declares what the nav row draws for it, the
 * file tree is the last entry in the same list, and exactly one of them is
 * open. Both apps read this — there is no per-kind special case left in either
 * row, and no second list for the standalone viewer.
 */

/** A host renderer's own panel: the desktop markdown's source view, which replaces the body. */
const SOURCE_PANEL = "source";
const source = { id: SOURCE_PANEL, label: "View source", icon: () => null, content: "body" };
const panelsOf = (declared, open = "", options) => [...declared, treePanel(open, options)];

test("a CAD file declares no panel of its own: its controls live in the viewer's tool stack", () => {
  assert.deepEqual(Object.keys(panels).sort(), ["FILE_PANEL_TREE", "nextOpenPanel", "resolveOpenPanel", "treePanel"]);
});

test("a file opened directly opens with nothing beside it, unless its own declaration asks; the tree only with no file", () => {
  assert.equal(resolveOpenPanel(panelsOf([]), null), null);
  assert.equal(resolveOpenPanel(panelsOf([{ ...source, defaultOpen: true }]), null)?.id, SOURCE_PANEL);
  // Only with no file to show at all is the tree the thing to reach for.
  assert.equal(resolveOpenPanel(panelsOf([], "", { empty: true }), null)?.id, FILE_PANEL_TREE);
  // A retired panel id a host stored cannot occupy the column: the old Display
  // panel's, or a CAD file's old Settings.
  for (const retired of ["cad-display", "cad-file"]) assert.equal(resolveOpenPanel(panelsOf([]), retired), null);
});

test("the files toggle is last in every list, and named by what it does", () => {
  assert.deepEqual(panelsOf([source]).map((panel) => panel.id), [SOURCE_PANEL, "tree"]);
  assert.equal(panelsOf([]).at(-1)?.label, "Show files");
  assert.deepEqual(panelsOf([], FILE_PANEL_TREE).map((panel) => [panel.id, panel.label]), [["tree", "Hide files"]]);
});

test("one panel is open at a time, whichever was up before", () => {
  // A press names its panel; pressing the open one closes it and leaves
  // nothing open.
  assert.equal(nextOpenPanel("", SOURCE_PANEL), SOURCE_PANEL);
  assert.equal(nextOpenPanel(SOURCE_PANEL, SOURCE_PANEL), "");
  // A press while ANOTHER panel is up opens this one — "show me this instead".
  assert.equal(nextOpenPanel(FILE_PANEL_TREE, SOURCE_PANEL), SOURCE_PANEL);
  assert.equal(nextOpenPanel(SOURCE_PANEL, FILE_PANEL_TREE), FILE_PANEL_TREE);
});

test("a panel this file does not have shows nothing", () => {
  // `""` is nothing open, and so is an id that is not in the list: a surface
  // that was reading markdown's source and is pointed at a `.step`.
  const viewer = panelsOf([]);
  assert.equal(resolveOpenPanel(viewer, ""), null);
  assert.equal(resolveOpenPanel(viewer, SOURCE_PANEL), null);
});
