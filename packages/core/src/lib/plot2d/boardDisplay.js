/**
 * A board's Display: which of a plot's layers are drawn, with or without the pours, from which
 * side. One object serves the viewer's Display and Layers (`@cad/ui`'s
 * `renderers/board/BoardDisplay.jsx`, `LayersSection.jsx`), the file view it is kept in, the views a
 * Quick Edit carries, and `cad <type> snapshot --display`, so a headless picture is exactly what the
 * Display shows.
 *
 * ```jsonc
 * { "mode": "board", "side": "top", "poured": true, "layers": ["F.Cu", "Edge.Cuts"],
 *   "active": "F.Cu", "others": "shown", "zones": 0.6, "tracks": 1 }
 * ```
 *
 * **Modes** are presets, as a 3D view's are (`ui/docs/render-mode.md`): each names the layer
 * KINDS it draws, the board's area under them all. No drawing sheet (KiCad's page border and title
 * block) is drawn: a board is the board alone, which the fit frames. **Board** is KiCad's own
 * view of a board it opens (`plot2d`'s default view): every layer. **Copper** is the copper, vias,
 * holes, outline, ratsnest and the pads' and vias' names. **Assembly** is the silkscreen, fab and
 * courtyards with the holes, outline and ratsnest. **Placement** is the board before it is wired:
 * no copper and no drill layer (a via's hole is routing); the overlay draws the pads, their holes
 * and every connection as an airwire (`board2d/boardOverlay.js`).
 *
 * `layers` is the ids drawn, or null for the mode's own set (resolved against the sheet, so a
 * rebuild that adds a layer draws it under the mode). A display whose layers differ from its
 * mode's reads as Custom; the mode is kept as what choosing it again returns to. The pours and the
 * side are switches of their own, kept through a change of mode, as a 3D view's Grid is, and so is
 * what the Layers section sets above its list, as KiCad's Appearance panel does: the **active**
 * layer (the one a row's press chose, drawn on top of the stack; null for KiCad's own order, its
 * active layer the copper facing the eye), **others** (KiCad's high-contrast modes, "Inactive layers":
 * `shown` as they are, `dimmed` faded, `hidden` not drawn; a display that says the earlier `dim: true`
 * reads as `dimmed`), and the opacity of the **zones**' fills (KiCad's 60%) and of the **tracks**
 * (100%). Dimmed or hidden, what keeps a person's bearings stays at full strength: the board's area,
 * its outline (Edge.Cuts), and with a copper layer active, the holes through it (every drill, every
 * via that spans it: `plot.js`'s `focusedLayers`).
 *
 * Nothing here is React or canvas: pure functions over the payload's sheet (`layoutPlot`'s, or
 * the raw `payload.sheets[0]`: only `layers[].id`, `kind` and `side` are read).
 */

/** What each mode draws, by layer kind (the outline always), and whether the overlay draws airwires. */
export const BOARD_DISPLAY_MODES = Object.freeze({
  board: Object.freeze({ kinds: Object.freeze(["area", "copper", "mask", "paste", "silk", "fab", "courtyard", "adhesive", "user", "margin", "via", "drill", "outline", "ratsnest", "names"]), airwires: false }),
  copper: Object.freeze({ kinds: Object.freeze(["area", "copper", "via", "drill", "outline", "ratsnest", "names"]), airwires: false }),
  assembly: Object.freeze({ kinds: Object.freeze(["area", "silk", "fab", "courtyard", "drill", "outline", "ratsnest"]), airwires: false }),
  placement: Object.freeze({ kinds: Object.freeze(["area", "fab", "courtyard", "outline"]), airwires: true }),
});
/** The mode ids, in the order a menu lists them. */
export const BOARD_DISPLAY_MODE_IDS = Object.freeze(["board", "copper", "assembly", "placement"]);
export const BOARD_DISPLAY_SIDES = Object.freeze(["top", "bottom"]);
export const BOARD_DISPLAY_DEFAULTS = Object.freeze({ mode: "board", side: "top", poured: true, layers: null, active: null, others: "shown", zones: 0.6, tracks: 1 });
/** What the layers but the active one are, in the order a menu lists them and Ctrl/Cmd+H cycles them (KiCad's). */
export const BOARD_DISPLAY_OTHERS = Object.freeze(["shown", "dimmed", "hidden"]);
/** The next of `BOARD_DISPLAY_OTHERS` after `others`, round to the first: Ctrl/Cmd+H's step. */
export const nextBoardOthers = (others) => BOARD_DISPLAY_OTHERS[(BOARD_DISPLAY_OTHERS.indexOf(others) + 1) % BOARD_DISPLAY_OTHERS.length];
/** What a set stored when a board still had a drawing sheet may name: no layer now, dropped as it is read. */
const GONE = new Set(["sheet"]);
/** The ids of what is not a board layer — the canvas under it, what goes through it — and how the Display names them. */
export const BOARD_THROUGH_LAYER_LABELS = Object.freeze({
  area: "Board area", vias: "Vias", drills: "Drills", ratsnest: "Ratsnest", names: "Names"
});
const INNER_COPPER = /^In\d+\.Cu$/;
// The sides' layers as the Layers section lists them, whatever order they are drawn in: the front
// outermost first down to its copper, the back from its copper outwards.
const FRONT_ORDER = ["F.CrtYd", "F.Fab", "F.SilkS", "F.Paste", "F.Adhes", "F.Mask", "F.Cu"];
const BACK_ORDER = ["B.Cu", "B.Mask", "B.Adhes", "B.Paste", "B.SilkS", "B.Fab", "B.CrtYd"];
// The rest as KiCad's Appearance panel lists them, then what is not a board layer.
const OTHER_ORDER = ["Dwgs.User", "Cmts.User", "Eco1.User", "Eco2.User", "Edge.Cuts", "Margin"];
const rankIn = (order, id) => {
  const at = order.indexOf(id);
  if (at >= 0) return at;
  const user = /^User\.(\d+)$/.exec(id);
  return user ? order.length + Number(user[1]) : order.length + 100;
};

const unit = (value, fallback) => (typeof value === "number" && Number.isFinite(value) ? Math.min(1, Math.max(0, value)) : fallback);
const sheetLayers = (sheet) => (Array.isArray(sheet?.layers) ? sheet.layers : []);
const sameSet = (left, right) => left.length === right.length && left.every((id) => right.includes(id));

/**
 * A stored or requested display, read leniently: the defaults where it says nothing usable.
 * `layers` keeps unknown ids (a stored set outlives a rebuild; a snapshot's is checked by the engine),
 * but not the drawing sheet a set stored before it was dropped names.
 *
 * @param {unknown} raw
 * @returns {{ mode: string, side: "top"|"bottom", poured: boolean, layers: string[]|null, active: string|null, others: "shown"|"dimmed"|"hidden",
 *   zones: number, tracks: number }}
 */
export function readBoardDisplay(raw) {
  const value = raw && typeof raw === "object" && !Array.isArray(raw) ? raw : {};
  const mode = BOARD_DISPLAY_MODES[value.mode] ? value.mode : BOARD_DISPLAY_DEFAULTS.mode;
  const layers = Array.isArray(value.layers)
    ? [...new Set(value.layers.filter((id) => typeof id === "string" && id && !GONE.has(id)))]
    : null;
  return {
    mode,
    side: value.side === "bottom" ? "bottom" : "top",
    poured: typeof value.poured === "boolean" ? value.poured : BOARD_DISPLAY_DEFAULTS.poured,
    layers,
    active: typeof value.active === "string" && value.active && !GONE.has(value.active) ? value.active : null,
    // `others`, else what the earlier `dim` said (true: dimmed).
    others: BOARD_DISPLAY_OTHERS.includes(value.others) ? value.others : value.dim === true ? "dimmed" : BOARD_DISPLAY_DEFAULTS.others,
    zones: unit(value.zones, BOARD_DISPLAY_DEFAULTS.zones),
    tracks: unit(value.tracks, BOARD_DISPLAY_DEFAULTS.tracks),
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

/** Whether a display's layers have left its mode's set (judged against the sheet). */
export function boardDisplayIsCustom(display, sheet = null) {
  if (display.layers == null) return false;
  return !sameSet(display.layers, boardModeLayers(display.mode, sheet));
}

/** The display's mode chosen: the preset's layers, its switches (the pours, the side) kept. */
export const selectBoardMode = (display, mode) => ({
  ...display, mode: BOARD_DISPLAY_MODES[mode] ? mode : BOARD_DISPLAY_DEFAULTS.mode, layers: null,
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

// What a press on a row may make active: a board layer, not the board's area or what goes through it.
const ACTIVE_KINDS = new Set(["copper", "mask", "paste", "silk", "fab", "courtyard", "adhesive", "user", "margin", "outline"]);
/** Whether a sheet's layer `id` can be the active layer (a board layer, not the area, the vias, the drills, the ratsnest or the names). */
export const boardLayerActivatable = (sheet, id) => sheetLayers(sheet).some((layer) => layer.id === id && ACTIVE_KINDS.has(layer.kind));

/**
 * The display's active layer on a sheet: the one chosen, while the sheet has it, else KiCad's — the
 * copper facing the eye (F.Cu from the top, B.Cu from below) — else null.
 */
export function boardActiveLayer(display, sheet) {
  if (display.active && boardLayerActivatable(sheet, display.active)) return display.active;
  const facing = display.side === "bottom" ? "B.Cu" : "F.Cu";
  return sheetLayers(sheet).some((layer) => layer.id === facing) ? facing : null;
}

const focusOf = (display, sheet) => {
  const layer = display.others === "dimmed" || display.others === "hidden" ? boardActiveLayer(display, sheet) : null;
  return layer ? { layer, others: display.others } : null;
};

/**
 * The drawing's view for a display (`drawPlot`'s `view`): the ids to draw, the pours, the side, the
 * active layer chosen (drawn on top), the focus — the layer kept at full strength and whether the rest
 * are dimmed or hidden, null while they are shown — and the zones' and tracks' opacities.
 */
export function boardDrawView(display, sheet) {
  return { layers: boardDisplayLayers(display, sheet), poured: display.poured, side: display.side,
    active: display.active && boardLayerActivatable(sheet, display.active) ? display.active : null,
    focus: focusOf(display, sheet), zones: display.zones ?? BOARD_DISPLAY_DEFAULTS.zones,
    tracks: display.tracks ?? BOARD_DISPLAY_DEFAULTS.tracks };
}

/**
 * A sheet's layers as the Display lists them, in four groups: Front (outermost first, down to
 * the copper), Inner (the inner coppers, `In1.Cu` first), Back (the copper first, outwards) and
 * Other (the user layers, the outline and the margin as KiCad lists them, then the board's area,
 * the vias, the drills, the ratsnest and the names). A group with no layers is
 * left out. The order is a list's, not the drawing's.
 *
 * @returns {{ id: "front"|"inner"|"back"|"other", label: string, layers: { id: string, label: string }[] }[]}
 */
export function boardLayerGroups(sheet) {
  const layers = sheetLayers(sheet);
  const row = (layer) => ({ id: layer.id, label: BOARD_THROUGH_LAYER_LABELS[layer.id] || layer.id });
  const sorted = (list, order) => [...list].sort((a, b) => rankIn(order, a.id) - rankIn(order, b.id));
  const front = sorted(layers.filter((layer) => layer.side === "front"), FRONT_ORDER);
  const inner = layers.filter((layer) => layer.kind === "copper" && INNER_COPPER.test(layer.id))
    .sort((a, b) => Number(/\d+/.exec(a.id)[0]) - Number(/\d+/.exec(b.id)[0]));
  const back = sorted(layers.filter((layer) => layer.side === "back"), BACK_ORDER);
  const placed = new Set([...front, ...inner, ...back].map((layer) => layer.id));
  const through = Object.keys(BOARD_THROUGH_LAYER_LABELS);
  const rest = layers.filter((layer) => !placed.has(layer.id));
  const other = [...sorted(rest.filter((layer) => !through.includes(layer.id)), OTHER_ORDER),
    ...rest.filter((layer) => through.includes(layer.id)).sort((a, b) => through.indexOf(a.id) - through.indexOf(b.id))];
  return [
    { id: "front", label: "Front", layers: front.map(row) },
    { id: "inner", label: "Inner", layers: inner.map(row) },
    { id: "back", label: "Back", layers: back.map(row) },
    { id: "other", label: "Other", layers: other.map(row) },
  ].filter((group) => group.layers.length > 0);
}
