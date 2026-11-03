import assert from "node:assert/strict";
import test from "node:test";

import {
  BOARD_DISPLAY_DEFAULTS,
  boardActiveLayer,
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

// A four-layer board's sheet as the plot lays it out: its layers bottom to top as KiCad draws them, by kind and side.
const SHEET = {
  layers: [
    ["area", "area", "both"],
    ["B.Fab", "fab", "back"], ["B.CrtYd", "courtyard", "back"], ["B.SilkS", "silk", "back"], ["B.Mask", "mask", "back"], ["B.Cu", "copper", "back"],
    ["In2.Cu", "copper", "both"], ["In1.Cu", "copper", "both"], ["Edge.Cuts", "outline", "both"], ["Dwgs.User", "user", "both"],
    ["F.Fab", "fab", "front"], ["F.CrtYd", "courtyard", "front"], ["F.Paste", "paste", "front"], ["F.SilkS", "silk", "front"], ["F.Mask", "mask", "front"],
    ["F.Cu", "copper", "front"], ["drills", "drill", "both"], ["vias", "via", "both"], ["ratsnest", "ratsnest", "both"], ["names", "names", "both"],
  ].map(([id, kind, side]) => ({ id, kind, side })),
};
const ids = (view) => view.layers;

test("a stored or requested display is read leniently: the defaults wherever it says nothing usable", () => {
  assert.deepEqual(readBoardDisplay(null), BOARD_DISPLAY_DEFAULTS);
  assert.deepEqual(readBoardDisplay({ mode: "placement", side: "bottom" }), { mode: "placement", side: "bottom", poured: true, layers: null, active: null, dim: false, zones: 0.6, tracks: 1 });
  assert.deepEqual(readBoardDisplay({ layers: "all", poured: false }), { mode: "board", side: "top", poured: false, layers: null, active: null, dim: false, zones: 0.6, tracks: 1 });
  assert.equal(readBoardDisplay({ mode: "nonsense" }).mode, "board");
  // An explicit set is kept as given, unknown ids included (the engine checks a snapshot's; a stored set outlives a rebuild), once each.
  assert.deepEqual(readBoardDisplay({ mode: "copper", layers: ["F.Cu", "F.Cu", "In9.Cu", 7, ""] }).layers, ["F.Cu", "In9.Cu"]);
  // A set stored when a board still had a drawing sheet drops it.
  assert.deepEqual(readBoardDisplay({ layers: ["sheet", "F.Cu"] }), { mode: "board", side: "top", poured: true, layers: ["F.Cu"], active: null, dim: false, zones: 0.6, tracks: 1 });
  // The Layers' own: the active layer, Dim, and the zones' and tracks' opacities, each clamped to 0..1.
  assert.deepEqual(readBoardDisplay({ active: "B.SilkS", dim: true, zones: 1.4, tracks: -1 }), { ...BOARD_DISPLAY_DEFAULTS, active: "B.SilkS", dim: true, zones: 1, tracks: 0 });
  assert.deepEqual(readBoardDisplay({ active: 7, dim: "yes", zones: "x" }), BOARD_DISPLAY_DEFAULTS);
});

test("each mode draws its layers: every one for the board, courtyards for assembly and placement, no copper for placement", () => {
  const drawn = (mode) => ids(boardDrawView({ ...BOARD_DISPLAY_DEFAULTS, mode }, SHEET));
  // Board is KiCad's view of a board it opens: every layer, the board's area under them.
  assert.deepEqual(drawn("board"), SHEET.layers.map((layer) => layer.id));
  assert.deepEqual(drawn("copper"), ["area", "B.Cu", "In2.Cu", "In1.Cu", "Edge.Cuts", "F.Cu", "drills", "vias", "ratsnest", "names"]);
  assert.deepEqual(drawn("assembly"), ["area", "B.Fab", "B.CrtYd", "B.SilkS", "Edge.Cuts", "F.Fab", "F.CrtYd", "F.SilkS", "drills", "ratsnest"]);
  // Placement's airwires are every connection, drawn by the overlay: the plot's ratsnest (only the unrouted) is left out.
  // Nor are the vias and drills: a via is routing; the overlay draws the pads' holes and the board's.
  assert.deepEqual(drawn("placement"), ["area", "B.Fab", "B.CrtYd", "Edge.Cuts", "F.Fab", "F.CrtYd"]);
  assert.equal(boardDisplayAirwires({ ...BOARD_DISPLAY_DEFAULTS, mode: "placement" }), true);
  assert.equal(boardDisplayAirwires({ ...BOARD_DISPLAY_DEFAULTS, mode: "copper" }), false);
  assert.equal(boardDisplayAirwires(null), false);
  assert.deepEqual(boardDrawView({ ...BOARD_DISPLAY_DEFAULTS, mode: "copper", side: "bottom", poured: false }, SHEET),
    { layers: boardModeLayers("copper", SHEET), poured: false, side: "bottom", active: null, dim: null, zones: 0.6, tracks: 1 });
  // Dim keeps the active layer bright: the one chosen, else the copper facing the eye; the area is no active layer.
  assert.equal(boardActiveLayer(BOARD_DISPLAY_DEFAULTS, SHEET), "F.Cu");
  assert.equal(boardActiveLayer({ ...BOARD_DISPLAY_DEFAULTS, side: "bottom" }, SHEET), "B.Cu");
  assert.equal(boardActiveLayer({ ...BOARD_DISPLAY_DEFAULTS, active: "area" }, SHEET), "F.Cu");
  assert.deepEqual(boardDrawView({ ...BOARD_DISPLAY_DEFAULTS, active: "In1.Cu", dim: true, zones: 0.2 }, SHEET),
    { layers: boardModeLayers("board", SHEET), poured: true, side: "top", active: "In1.Cu", dim: "In1.Cu", zones: 0.2, tracks: 1 });
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
  assert.deepEqual(without.layers, ["area", "B.Cu", "In2.Cu", "In1.Cu", "Edge.Cuts", "F.Cu", "drills", "vias", "names"]);
  assert.equal(boardDisplayIsCustom(without, SHEET), true);
  // A layer the mode leaves out, ticked, lands where the stack has it.
  const silk = toggleBoardLayer(without, SHEET, "F.SilkS", true);
  assert.deepEqual(silk.layers, ["area", "B.Cu", "In2.Cu", "In1.Cu", "Edge.Cuts", "F.SilkS", "F.Cu", "drills", "vias", "names"]);
  // Ticking the same layer again changes nothing; ticking the set back to the mode's stores the mode's.
  assert.deepEqual(toggleBoardLayer(silk, SHEET, "F.SilkS", true).layers, silk.layers);
  const back = toggleBoardLayer(toggleBoardLayer(silk, SHEET, "F.SilkS", false), SHEET, "ratsnest", true);
  assert.equal(back.layers, null);
  assert.equal(boardDisplayIsCustom(back, SHEET), false);
  assert.equal(back.mode, "copper");
});

test("the Display lists the layers in four groups: front outermost first, inner, back copper first, then the rest and what is not a board layer", () => {
  const groups = boardLayerGroups(SHEET);
  // A list's order, not the drawing's: KiCad draws the front copper over the front's other layers.
  assert.deepEqual(groups.map((group) => [group.id, group.label, group.layers.map((layer) => layer.id)]), [
    ["front", "Front", ["F.CrtYd", "F.Fab", "F.SilkS", "F.Paste", "F.Mask", "F.Cu"]],
    ["inner", "Inner", ["In1.Cu", "In2.Cu"]],
    ["back", "Back", ["B.Cu", "B.Mask", "B.SilkS", "B.Fab", "B.CrtYd"]],
    ["other", "Other", ["Dwgs.User", "Edge.Cuts", "area", "vias", "drills", "ratsnest", "names"]],
  ]);
  assert.deepEqual(groups[3].layers.slice(2).map((layer) => layer.label), ["Board area", "Vias", "Drills", "Ratsnest", "Names"]);
  assert.equal(groups[0].layers[0].label, "F.CrtYd");
  // A two-layer board has no Inner group; no sheet, no groups.
  const two = { layers: SHEET.layers.filter((layer) => !layer.id.startsWith("In")) };
  assert.deepEqual(boardLayerGroups(two).map((group) => group.id), ["front", "back", "other"]);
  assert.deepEqual(boardLayerGroups(null), []);
});
