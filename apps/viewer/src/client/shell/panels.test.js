import assert from "node:assert/strict";
import test from "node:test";

import {
  CAD_PANEL,
  FILE_PANEL_TREE,
  SOURCE_PANEL,
  cadPanels,
  markdownPanels,
  nextOpenPanel,
  panelClosedBy,
  panelsFor,
  resolveOpenPanel
} from "./panels.js";

/**
 * The panels contract: a surface declares what the nav row draws for it, the
 * file tree is the last entry in the same list, and exactly one of them is
 * open. Both apps read this — there is no per-kind special case left in either
 * row, and no second list for the standalone viewer.
 */

test("a CAD surface declares its theme editor and its Inspector, in that order", () => {
  assert.deepEqual(
    cadPanels(true).map((panel) => [panel.id, panel.label, panel.content]),
    [
      ["cad-theme", "Theme settings", "slot"],
      // "Inspector" is the name a person sees; the id stays `cad-file-sheet`
      // because the desktop's stored `panel` field holds it and the viewer's
      // host contract calls the same panel `fileSheetOpen`.
      ["cad-file-sheet", "Inspector", "slot"]
    ]
  );
  // And there are none at all until the surface behind them is up: two toggles
  // over a runtime's failure card would open nothing.
  assert.deepEqual(cadPanels(false), []);
});

test("markdown's one panel is named by what pressing it does", () => {
  assert.deepEqual(
    markdownPanels("").map((panel) => [panel.id, panel.label, panel.content]),
    [["source", "View source", "body"]]
  );
  assert.deepEqual(markdownPanels(SOURCE_PANEL).map((panel) => panel.label), ["View preview"]);
});

test("the files toggle is last in every list, and named by what it does", () => {
  const cad = panelsFor(cadPanels(true), "");
  assert.deepEqual(cad.map((panel) => panel.id), ["cad-theme", "cad-file-sheet", "tree"]);
  assert.equal(cad.at(-1)?.label, "Show files");
  // A surface with no panels of its own has the tree alone.
  assert.deepEqual(
    panelsFor([], FILE_PANEL_TREE).map((panel) => [panel.id, panel.label]),
    [["tree", "Hide files"]]
  );
});

test("one panel is open at a time, whichever was up before", () => {
  const cad = panelsFor(cadPanels(true), "");

  // The default is what a surface opens with when nobody has said: a CAD
  // file's Inspector, and the tree for everything else. The tree is last, so
  // its default never wins over a renderer's own.
  assert.equal(resolveOpenPanel(cad, null)?.id, CAD_PANEL.fileSheet);
  assert.equal(resolveOpenPanel(panelsFor([], ""), null)?.id, FILE_PANEL_TREE);

  // A press names its panel; pressing the open one closes it and leaves
  // nothing open.
  assert.equal(nextOpenPanel("", CAD_PANEL.theme), CAD_PANEL.theme);
  assert.equal(nextOpenPanel(CAD_PANEL.theme, CAD_PANEL.theme), "");
  // A press while ANOTHER panel is up opens this one — "show me this instead"
  // — whether the other is the surface's or the host's own tree.
  assert.equal(nextOpenPanel(CAD_PANEL.fileSheet, CAD_PANEL.theme), CAD_PANEL.theme);
  assert.equal(nextOpenPanel(FILE_PANEL_TREE, CAD_PANEL.theme), CAD_PANEL.theme);
  assert.equal(nextOpenPanel(CAD_PANEL.theme, FILE_PANEL_TREE), FILE_PANEL_TREE);
  assert.equal(nextOpenPanel(SOURCE_PANEL, FILE_PANEL_TREE), FILE_PANEL_TREE);
  assert.equal(nextOpenPanel(FILE_PANEL_TREE, SOURCE_PANEL), SOURCE_PANEL);
});

test("a panel this file does not have shows nothing", () => {
  // `""` is nothing open, and so is an id that is not in the list: a surface
  // that was reading markdown's source and is pointed at a `.step`, or a CAD
  // pane whose surface has not come up, names a panel that is not there.
  const cad = panelsFor(cadPanels(true), "");
  assert.equal(resolveOpenPanel(cad, ""), null);
  assert.equal(resolveOpenPanel(cad, SOURCE_PANEL), null);
  const notReady = panelsFor(cadPanels(false), "");
  assert.equal(resolveOpenPanel(notReady, CAD_PANEL.fileSheet), null);
  // ...and with nobody having said, the tree is what is left.
  assert.equal(resolveOpenPanel(notReady, null)?.id, FILE_PANEL_TREE);
});

test("a surface reporting its own panel shut leaves another host's panel alone", () => {
  // The CAD surface reports BOTH of its flags on every change, so a "the
  // Inspector is shut" arriving while the file tree is open must not close
  // the column.
  assert.equal(panelClosedBy(true, FILE_PANEL_TREE, CAD_PANEL.fileSheet), CAD_PANEL.fileSheet);
  assert.equal(panelClosedBy(false, FILE_PANEL_TREE, CAD_PANEL.fileSheet), FILE_PANEL_TREE);
  assert.equal(panelClosedBy(false, CAD_PANEL.fileSheet, CAD_PANEL.fileSheet), "");
});
