/**
 * A board's Display: which of a plot's layers are drawn, with or without the pours, from which
 * side. One object serves the viewer's Display settings (`@text-to-cad/ui`'s
 * `renderers/plot/board/BoardDisplay.jsx`), the file view it is kept in, and
 * `cadgen pcb snapshot --display`, so a headless picture is exactly what the Display shows.
 *
 * ```jsonc
 * { "mode": "board", "side": "top", "poured": true, "layers": ["F.Cu", "Edge.Cuts"] }
 * ```
 *
 * **Modes** are presets, as a 3D view's are (`ui/docs/render-mode.md`): each names the layer
 * KINDS it draws and whether pours are filled. **Board** is the board as it is made (`plot2d`'s
 * default view: every layer but the courtyards, mask and paste included). **Copper** is the
 * copper, vias, holes, outline and ratsnest. **Assembly** is the silkscreen, fab and courtyards
 * with the holes, outline and ratsnest. **Placement** is the board before it is wired: no copper
 * and no drill layer (a via's hole is routing); the overlay draws the pads, their holes and every
 * connection as an airwire (`board2d/boardOverlay.js`).
 *
 * `layers` is the ids drawn, or null for the mode's own set (resolved against the sheet, so a
 * rebuild that adds a layer draws it under the mode). A display whose layers or pours differ
 * from its mode's reads as Custom; the mode is kept as what Reset returns to. The side is not a
 * preset's, as a 3D view's camera is not.
 *
 * Nothing here is React or canvas: pure functions over the payload's sheet (`layoutPlot`'s, or
 * the raw `payload.sheets[0]`: only `layers[].id`, `kind` and `side` are read).
 */

/** What each mode draws, by layer kind (the outline always), its pours, and whether the overlay draws airwires. */
export const BOARD_DISPLAY_MODES = Object.freeze({
  board: Object.freeze({ kinds: Object.freeze(["copper", "mask", "paste", "silk", "fab", "adhesive", "user", "margin", "via", "drill", "outline", "ratsnest"]), poured: true, airwires: false }),
  copper: Object.freeze({ kinds: Object.freeze(["copper", "via", "drill", "outline", "ratsnest"]), poured: true, airwires: false }),
  assembly: Object.freeze({ kinds: Object.freeze(["silk", "fab", "courtyard", "drill", "outline", "ratsnest"]), poured: true, airwires: false }),
  placement: Object.freeze({ kinds: Object.freeze(["fab", "courtyard", "outline"]), poured: true, airwires: true }),
});
/** The mode ids, in the order a menu lists them. */
export const BOARD_DISPLAY_MODE_IDS = Object.freeze(["board", "copper", "assembly", "placement"]);
export const BOARD_DISPLAY_SIDES = Object.freeze(["top", "bottom"]);
export const BOARD_DISPLAY_DEFAULTS = Object.freeze({ mode: "board", side: "top", poured: true, layers: null });
// Before modes a display named its layers with a word (`all`, `copper`, `assembly`); `all` is Board.
const LEGACY_LAYERS = Object.freeze({ all: "board", copper: "copper", assembly: "assembly" });
/** The ids of what goes through the board, and how the Display names them. */
export const BOARD_THROUGH_LAYER_LABELS = Object.freeze({ vias: "Vias", ratsnest: "Ratsnest", drills: "Drills" });
const INNER_COPPER = /^In\d+\.Cu$/;

const sheetLayers = (sheet) => (Array.isArray(sheet?.layers) ? sheet.layers : []);
const sameSet = (left, right) => left.length === right.length && left.every((id) => right.includes(id));

/**
 * A stored or requested display, read leniently: the defaults where it says nothing usable.
 * `layers` keeps unknown ids (a stored set outlives a rebuild; a snapshot's is checked by cadgen).
 *
 * @param {unknown} raw
 * @returns {{ mode: string, side: "top"|"bottom", poured: boolean, layers: string[]|null }}
 */
export function readBoardDisplay(raw) {
  const value = raw && typeof raw === "object" && !Array.isArray(raw) ? raw : {};
  const mode = BOARD_DISPLAY_MODES[value.mode] ? value.mode : LEGACY_LAYERS[value.layers] || BOARD_DISPLAY_DEFAULTS.mode;
  const layers = Array.isArray(value.layers)
    ? [...new Set(value.layers.filter((id) => typeof id === "string" && id))]
    : null;
  return {
    mode,
    side: value.side === "bottom" ? "bottom" : "top",
    poured: typeof value.poured === "boolean" ? value.poured : BOARD_DISPLAY_MODES[mode].poured,
    layers,
  };
}

/** The ids a mode draws of a sheet, in the sheet's order. */
export function boardModeLayers(mode, sheet) {
  const kinds = (BOARD_DISPLAY_MODES[mode] || BOARD_DISPLAY_MODES.board).kinds;
  return sheetLayers(sheet).filter((layer) => kinds.includes(layer.kind)).map((layer) => layer.id);
}

/** The ids a display draws of a sheet: its own set, else its mode's. */
export function boardDisplayLayers(display, sheet) {
  return display.layers ?? boardModeLayers(display.mode, sheet);
}

/** Whether a display has left its mode's preset: its pours, or its layers (judged against the sheet). */
export function boardDisplayIsCustom(display, sheet = null) {
  const preset = BOARD_DISPLAY_MODES[display.mode] || BOARD_DISPLAY_MODES.board;
  if (display.poured !== preset.poured) return true;
  if (display.layers == null) return false;
  return !sameSet(display.layers, boardModeLayers(display.mode, sheet));
}

/** The display's mode chosen: the preset's layers and pours, the side kept. */
export const selectBoardMode = (display, mode) => ({
  mode, side: display.side, poured: (BOARD_DISPLAY_MODES[mode] || BOARD_DISPLAY_MODES.board).poured, layers: null,
});

/**
 * One layer ticked or unticked. A set that is the mode's own again is stored as the mode's
 * (`layers: null`), so it reads as the mode and follows it through a rebuild.
 */
export function toggleBoardLayer(display, sheet, id, shown) {
  const current = boardDisplayLayers(display, sheet);
  const next = shown ? (current.includes(id) ? current : [...current, id]) : current.filter((layer) => layer !== id);
  const ordered = sheetLayers(sheet).map((layer) => layer.id).filter((layer) => next.includes(layer));
  const layers = sameSet(ordered, boardModeLayers(display.mode, sheet)) ? null : ordered;
  return { ...display, layers };
}

/** Whether a display draws the board's airwires and pads itself (its plot without copper). */
export const boardDisplayAirwires = (display) => Boolean(display && (BOARD_DISPLAY_MODES[display.mode] || BOARD_DISPLAY_MODES.board).airwires);

/** Whether a display draws any copper layer: when it does, its pours are a choice. */
export const boardDisplayDrawsCopper = (display, sheet) => {
  const drawn = new Set(boardDisplayLayers(display, sheet));
  return sheetLayers(sheet).some((layer) => layer.kind === "copper" && drawn.has(layer.id));
};

/** The drawing's view for a display (`drawPlot`'s `view`): the ids to draw, the pours, the side. */
export function boardDrawView(display, sheet) {
  return { layers: boardDisplayLayers(display, sheet), poured: display.poured, side: display.side };
}

/**
 * A sheet's layers as the Display lists them, in four groups: Front (outermost first, down to
 * the copper), Inner (the inner coppers, `In1.Cu` first), Back (the copper first, outwards) and
 * Other (the outline, the user layers and the margin in the stack's order, then the vias, the
 * ratsnest and the drills). A group with no layers is left out.
 *
 * @returns {{ id: "front"|"inner"|"back"|"other", label: string, layers: { id: string, label: string }[] }[]}
 */
export function boardLayerGroups(sheet) {
  const layers = sheetLayers(sheet);
  const row = (layer) => ({ id: layer.id, label: BOARD_THROUGH_LAYER_LABELS[layer.id] || layer.id });
  const front = layers.filter((layer) => layer.side === "front").reverse();
  const inner = layers.filter((layer) => layer.kind === "copper" && INNER_COPPER.test(layer.id)).reverse();
  const back = layers.filter((layer) => layer.side === "back").reverse();
  const placed = new Set([...front, ...inner, ...back].map((layer) => layer.id));
  const through = new Set(Object.keys(BOARD_THROUGH_LAYER_LABELS));
  const rest = layers.filter((layer) => !placed.has(layer.id));
  const other = [...rest.filter((layer) => !through.has(layer.id)), ...rest.filter((layer) => through.has(layer.id))];
  return [
    { id: "front", label: "Front", layers: front.map(row) },
    { id: "inner", label: "Inner", layers: inner.map(row) },
    { id: "back", label: "Back", layers: back.map(row) },
    { id: "other", label: "Other", layers: other.map(row) },
  ].filter((group) => group.layers.length > 0);
}
