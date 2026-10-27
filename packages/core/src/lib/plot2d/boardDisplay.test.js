import assert from "node:assert/strict";
import test from "node:test";

import {
  BOARD_DISPLAY_DEFAULTS,
  boardDisplayAirwires,
  boardDisplayDrawsCopper,
  boardDisplayIsCustom,
  boardDrawView,
  boardLayerGroups,
  boardModeLayers,
  readBoardDisplay,
  selectBoardMode,
  toggleBoardLayer
} from "./boardDisplay.js";

// A four-layer board's sheet as the plot lays it out: its layers back to front, by kind and side.
const SHEET = {
  layers: [
    ["B.CrtYd", "courtyard", "back"], ["B.Fab", "fab", "back"], ["B.SilkS", "silk", "back"], ["B.Mask", "mask", "back"], ["B.Cu", "copper", "back"],
    ["In2.Cu", "copper", "both"], ["In1.Cu", "copper", "both"], ["F.Cu", "copper", "front"], ["F.Mask", "mask", "front"], ["F.Paste", "paste", "front"],
    ["F.SilkS", "silk", "front"], ["F.Fab", "fab", "front"], ["F.CrtYd", "courtyard", "front"], ["Dwgs.User", "user", "both"], ["Edge.Cuts", "outline", "both"],
    ["vias", "via", "both"], ["ratsnest", "ratsnest", "both"], ["drills", "drill", "both"],
  ].map(([id, kind, side]) => ({ id, kind, side })),
};
const ids = (view) => view.layers;

test("a stored or requested display is read leniently: the defaults wherever it says nothing usable", () => {
  assert.deepEqual(readBoardDisplay(null), BOARD_DISPLAY_DEFAULTS);
  assert.deepEqual(readBoardDisplay({ mode: "placement", side: "bottom" }), { mode: "placement", side: "bottom", poured: true, layers: null });
  assert.deepEqual(readBoardDisplay({ layers: "all", poured: false }), { mode: "board", side: "top", poured: false, layers: null });
  assert.equal(readBoardDisplay({ mode: "nonsense" }).mode, "board");
  // An explicit set is kept as given, unknown ids included (cadgen checks a snapshot's; a stored set outlives a rebuild), once each.
  assert.deepEqual(readBoardDisplay({ mode: "copper", layers: ["F.Cu", "F.Cu", "In9.Cu", 7, ""] }).layers, ["F.Cu", "In9.Cu"]);
});

test("each mode draws its layers: courtyards for assembly and placement, no copper for placement", () => {
  const drawn = (mode) => ids(boardDrawView({ ...BOARD_DISPLAY_DEFAULTS, mode }, SHEET));
  // Board is the board as it is made: every layer but the courtyards, mask and paste included.
  assert.deepEqual(drawn("board"), ["B.Fab", "B.SilkS", "B.Mask", "B.Cu", "In2.Cu", "In1.Cu", "F.Cu", "F.Mask", "F.Paste", "F.SilkS", "F.Fab", "Dwgs.User", "Edge.Cuts", "vias", "ratsnest", "drills"]);
  assert.deepEqual(drawn("copper"), ["B.Cu", "In2.Cu", "In1.Cu", "F.Cu", "Edge.Cuts", "vias", "ratsnest", "drills"]);
  assert.deepEqual(drawn("assembly"), ["B.CrtYd", "B.Fab", "B.SilkS", "F.SilkS", "F.Fab", "F.CrtYd", "Edge.Cuts", "ratsnest", "drills"]);
  // Placement's airwires are every connection, drawn by the overlay: the plot's ratsnest (only the unrouted) is left out.
  // Nor are the vias and drills: a via is routing; the overlay draws the pads' holes and the board's.
  assert.deepEqual(drawn("placement"), ["B.CrtYd", "B.Fab", "F.Fab", "F.CrtYd", "Edge.Cuts"]);
  assert.equal(boardDisplayAirwires({ ...BOARD_DISPLAY_DEFAULTS, mode: "placement" }), true);
  assert.equal(boardDisplayAirwires({ ...BOARD_DISPLAY_DEFAULTS, mode: "copper" }), false);
  assert.equal(boardDisplayAirwires(null), false);
  assert.deepEqual(boardDrawView({ mode: "copper", side: "bottom", poured: false, layers: null }, SHEET),
    { layers: boardModeLayers("copper", SHEET), poured: false, side: "bottom" });
});

test("an explicit set is what is drawn, and the pours are a choice only while a copper layer is", () => {
  const display = { ...BOARD_DISPLAY_DEFAULTS, mode: "assembly", layers: ["F.SilkS", "Edge.Cuts"] };
  assert.deepEqual(ids(boardDrawView(display, SHEET)), ["F.SilkS", "Edge.Cuts"]);
  assert.equal(boardDisplayDrawsCopper(display, SHEET), false);
  assert.equal(boardDisplayDrawsCopper({ ...display, layers: ["F.SilkS", "In1.Cu"] }, SHEET), true);
  assert.equal(boardDisplayDrawsCopper({ ...BOARD_DISPLAY_DEFAULTS, mode: "copper" }, SHEET), true);
  assert.equal(boardDisplayDrawsCopper({ ...BOARD_DISPLAY_DEFAULTS, mode: "assembly" }, SHEET), false);
});

test("a display reads as Custom once its layers leave the mode's; the pours and the side are switches of their own, kept through a change of mode", () => {
  const unpoured = { mode: "copper", side: "bottom", poured: false, layers: null };
  assert.equal(boardDisplayIsCustom(unpoured, SHEET), false);
  // The mode's own set, spelt out, is not custom; one layer more or less is.
  assert.equal(boardDisplayIsCustom({ ...BOARD_DISPLAY_DEFAULTS, mode: "copper", layers: [...boardModeLayers("copper", SHEET)].reverse() }, SHEET), false);
  assert.equal(boardDisplayIsCustom({ ...BOARD_DISPLAY_DEFAULTS, mode: "copper", layers: ["F.Cu"] }, SHEET), true);
  assert.equal(boardDisplayIsCustom({ ...BOARD_DISPLAY_DEFAULTS, layers: null }, null), false);
  // Choosing a mode is its layers again; the pours and the side stay as they were.
  assert.deepEqual(selectBoardMode({ ...unpoured, layers: ["F.Cu"] }, "copper"), { mode: "copper", side: "bottom", poured: false, layers: null });
  assert.deepEqual(selectBoardMode(unpoured, "placement"), { mode: "placement", side: "bottom", poured: false, layers: null });
});

test("a checkbox toggles one layer in the sheet's order, and the set ticked back to the mode's is the mode's again", () => {
  const copper = { ...BOARD_DISPLAY_DEFAULTS, mode: "copper" };
  const without = toggleBoardLayer(copper, SHEET, "ratsnest", false);
  assert.deepEqual(without.layers, ["B.Cu", "In2.Cu", "In1.Cu", "F.Cu", "Edge.Cuts", "vias", "drills"]);
  assert.equal(boardDisplayIsCustom(without, SHEET), true);
  // A layer the mode leaves out, ticked, lands where the stack has it.
  const silk = toggleBoardLayer(without, SHEET, "F.SilkS", true);
  assert.deepEqual(silk.layers, ["B.Cu", "In2.Cu", "In1.Cu", "F.Cu", "F.SilkS", "Edge.Cuts", "vias", "drills"]);
  // Ticking the same layer again changes nothing; ticking the set back to the mode's stores the mode's.
  assert.deepEqual(toggleBoardLayer(silk, SHEET, "F.SilkS", true).layers, silk.layers);
  const back = toggleBoardLayer(toggleBoardLayer(silk, SHEET, "F.SilkS", false), SHEET, "ratsnest", true);
  assert.equal(back.layers, null);
  assert.equal(boardDisplayIsCustom(back, SHEET), false);
  assert.equal(back.mode, "copper");
});

test("the Display lists the layers in four groups: front outermost first, inner, back copper first, then the rest and what goes through", () => {
  const groups = boardLayerGroups(SHEET);
  assert.deepEqual(groups.map((group) => [group.id, group.label, group.layers.map((layer) => layer.id)]), [
    ["front", "Front", ["F.CrtYd", "F.Fab", "F.SilkS", "F.Paste", "F.Mask", "F.Cu"]],
    ["inner", "Inner", ["In1.Cu", "In2.Cu"]],
    ["back", "Back", ["B.Cu", "B.Mask", "B.SilkS", "B.Fab", "B.CrtYd"]],
    ["other", "Other", ["Dwgs.User", "Edge.Cuts", "vias", "ratsnest", "drills"]],
  ]);
  assert.deepEqual(groups[3].layers.slice(2).map((layer) => layer.label), ["Vias", "Ratsnest", "Drills"]);
  assert.equal(groups[0].layers[0].label, "F.CrtYd");
  // A two-layer board has no Inner group; no sheet, no groups.
  const two = { layers: SHEET.layers.filter((layer) => !layer.id.startsWith("In")) };
  assert.deepEqual(boardLayerGroups(two).map((group) => group.id), ["front", "back", "other"]);
  assert.deepEqual(boardLayerGroups(null), []);
});
