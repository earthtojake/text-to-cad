import assert from "node:assert/strict";
import test from "node:test";

import {
  CAD_PANEL,
  FILE_PANEL_TREE,
  SOURCE_PANEL,
  markdownPanels,
  nextOpenPanel,
  resolveOpenPanel,
  treePanel,
  viewerPanels
} from "./panels.js";

/**
 * The panels contract: a surface declares what the nav row draws for it, the
 * file tree is the last entry in the same list, and exactly one of them is
 * open. Both apps read this — there is no per-kind special case left in either
 * row, and no second list for the standalone viewer.
 */

const Icon = () => null;
const part = { label: "Part", icon: Icon };
const panelsOf = (declared, open = "", options) => [...declared, treePanel(open, options)];

test("a viewer file declares Display, then its own panel; a file with nothing of its own, Display alone", () => {
  assert.deepEqual(
    viewerPanels(true, { file: part }).map((panel) => [panel.id, panel.label, panel.content]),
    [["cad-display", "Display", "slot"], ["cad-file", "Part", "slot"]]
  );
  assert.deepEqual(viewerPanels(true).map((panel) => panel.id), ["cad-display"]);
  // And there are none at all until the surface behind them is up: a toggle
  // over a runtime's failure card would open nothing.
  assert.deepEqual(viewerPanels(false, { file: part }), []);
});

test("a file opened directly opens with its own panel, or nothing: never Display, never the tree", () => {
  assert.equal(resolveOpenPanel(panelsOf(viewerPanels(true, { file: part })), null)?.id, CAD_PANEL.file);
  assert.equal(resolveOpenPanel(panelsOf(viewerPanels(true)), null), null);
  assert.equal(resolveOpenPanel(panelsOf([]), null), null);
  // Only with no file to show at all is the tree the thing to reach for.
  assert.equal(resolveOpenPanel(panelsOf([], "", { empty: true }), null)?.id, FILE_PANEL_TREE);
  // A default only: a person who opened Display keeps it.
  assert.equal(resolveOpenPanel(panelsOf(viewerPanels(true, { file: part })), CAD_PANEL.display)?.id, CAD_PANEL.display);
});

test("markdown's one panel is named by what pressing it does", () => {
  assert.deepEqual(
    markdownPanels("").map((panel) => [panel.id, panel.label, panel.content]),
    [["source", "View source", "body"]]
  );
  assert.deepEqual(markdownPanels(SOURCE_PANEL).map((panel) => panel.label), ["View preview"]);
});

test("the files toggle is last in every list, and named by what it does", () => {
  const viewer = panelsOf(viewerPanels(true, { file: part }));
  assert.deepEqual(viewer.map((panel) => panel.id), ["cad-display", "cad-file", "tree"]);
  assert.equal(viewer.at(-1)?.label, "Show files");
  assert.deepEqual(panelsOf([], FILE_PANEL_TREE).map((panel) => [panel.id, panel.label]), [["tree", "Hide files"]]);
});

test("one panel is open at a time, whichever was up before", () => {
  // A press names its panel; pressing the open one closes it and leaves
  // nothing open.
  assert.equal(nextOpenPanel("", CAD_PANEL.file), CAD_PANEL.file);
  assert.equal(nextOpenPanel(CAD_PANEL.file, CAD_PANEL.file), "");
  // A press while ANOTHER panel is up opens this one — "show me this instead"
  // — whether the other is the surface's or the host's own tree.
  assert.equal(nextOpenPanel(FILE_PANEL_TREE, CAD_PANEL.display), CAD_PANEL.display);
  assert.equal(nextOpenPanel(CAD_PANEL.display, CAD_PANEL.file), CAD_PANEL.file);
  assert.equal(nextOpenPanel(CAD_PANEL.file, FILE_PANEL_TREE), FILE_PANEL_TREE);
  assert.equal(nextOpenPanel(SOURCE_PANEL, FILE_PANEL_TREE), FILE_PANEL_TREE);
});

test("a panel this file does not have shows nothing", () => {
  // `""` is nothing open, and so is an id that is not in the list: a surface
  // that was reading markdown's source and is pointed at a `.step`, a mesh asked
  // for a file panel it does not have, or a pane whose surface has not come up.
  const viewer = panelsOf(viewerPanels(true, { file: part }));
  assert.equal(resolveOpenPanel(viewer, ""), null);
  assert.equal(resolveOpenPanel(viewer, SOURCE_PANEL), null);
  assert.equal(resolveOpenPanel(viewer, "cad-file-sheet"), null);
  assert.equal(resolveOpenPanel(panelsOf(viewerPanels(true)), CAD_PANEL.file), null);
  assert.equal(resolveOpenPanel(panelsOf(viewerPanels(false, { file: part })), CAD_PANEL.file), null);
});
