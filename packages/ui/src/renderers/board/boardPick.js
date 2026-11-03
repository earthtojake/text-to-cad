/**
 * What Select takes on a board, as pure rules (`tools.js` names the tools): its filter, KiCad's
 * Selection Filter — the kinds a click may take and whether it takes locked items — what a click
 * may take under it (the board index's `kinds`, `@cad/core`'s `board2d/boardIndex.js`), and the
 * working layer a dragged area is on.
 *
 * Importing this module has no environmental effects.
 */

/**
 * The kinds Select's filter ticks, in KiCad's order: Footprints (`parts`), Text, Tracks, Vias, Pads,
 * Graphics (a board's and a footprint's shapes), Zones (the pours), Rule Areas (the keepout zones)
 * and Dimensions. All items ticks them all.
 */
export const BOARD_SELECT_KINDS = Object.freeze(["parts", "texts", "tracks", "vias", "pads", "graphics", "zones", "ruleAreas", "dimensions"]);
/** KiCad's Locked items: ticked, a click takes what KiCad saved locked too. Unticked as a board opens. */
export const BOARD_LOCKED = "locked";
/** The filter a board opens on: every kind, and no locked items, as KiCad's opens. */
export const BOARD_DEFAULT_FILTER = BOARD_SELECT_KINDS;
/**
 * The filter's grid, KiCad's two columns row by row: All items and Locked items, then the kinds.
 * KiCad's Grid Items, Points and Other items are not here: the board's index holds none of them.
 */
export const BOARD_FILTER_GRID = Object.freeze([
  Object.freeze(["all", BOARD_LOCKED]), Object.freeze(["parts", "texts"]), Object.freeze(["tracks", "vias"]),
  Object.freeze(["pads", "graphics"]), Object.freeze(["zones", "ruleAreas"]), Object.freeze(["dimensions"])
]);

const KNOWN = new Set([...BOARD_SELECT_KINDS, BOARD_LOCKED]);
/**
 * A filter as Select holds it: the kinds and Locked items it names, in the grid's order, what it
 * names besides dropped — `nets` and `points`, the earlier filter's Nets and Point or area, and
 * anything else; not a list at all, the filter a board opens on.
 * @param {unknown} raw
 * @returns {readonly string[]}
 */
export function readBoardFilter(raw) {
  if (!Array.isArray(raw)) return BOARD_DEFAULT_FILTER;
  const named = new Set(raw.filter(id => KNOWN.has(id)));
  return [...BOARD_SELECT_KINDS, BOARD_LOCKED].filter(id => named.has(id));
}

/**
 * What a click may pick under a filter (the board index's `kinds`), or null for nothing. It takes
 * the most specific thing under the pointer of the kinds ticked — a pad, then a via, a track, a
 * text, a dimension, a graphic, a pour or a rule area by its outline, then a part, as KiCad picks;
 * with Footprints ticked a footprint's own graphics are its part's, without it they are themselves;
 * with the zones alone ticked (Zones, Rule Areas) a zone is taken anywhere inside it. Locked items
 * unticked leaves what KiCad saved locked alone, but for a pad (KiCad lets a single click take one).
 * @param {readonly string[]} filter
 */
export function boardPickKinds(filter) {
  const kinds = BOARD_SELECT_KINDS.filter(id => filter.includes(id));
  if (!kinds.length) return null;
  const has = id => kinds.includes(id);
  return {
    parts: has("parts"), pads: has("pads"), tracks: has("tracks"), vias: has("vias"), texts: has("texts"), dimensions: has("dimensions"),
    shapes: has("graphics"), footprintShapes: has("graphics") && !has("parts"),
    zones: has("zones"), ruleAreas: has("ruleAreas"), zoneFill: kinds.every(id => id === "zones" || id === "ruleAreas"),
    nets: false, locked: filter.includes(BOARD_LOCKED)
  };
}

/** Whether a filter ticks every kind (All items; Locked items is not a kind). */
export const boardFilterAll = filter => BOARD_SELECT_KINDS.every(id => filter.includes(id));

// What a working layer is, nearest first: the copper, then what is printed on the board, then the rest.
const WORKING_KINDS = Object.freeze(["copper", "silk", "fab", "courtyard", "user", "mask", "paste", "adhesive"]);
/**
 * The layer a dragged area is on: the view's working layer, the one drawn nearest the eye of the
 * kind a person works on first — the copper (F.Cu from the top, B.Cu from below, an inner layer when
 * it is the copper drawn), else the silkscreen, the fabrication layer, the courtyard, a user layer —
 * so it says the side looked at and the layer isolated; null when only the outline and what goes
 * through the board are drawn.
 * @param {{ layers: readonly { id: string, kind: string }[] } | null} sheet  The plot's sheet, its layers back to front.
 * @param {Iterable<string>} drawn  The ids the Display draws.
 * @param {"top" | "bottom"} side
 */
export function boardWorkingLayer(sheet, drawn, side = "top") {
  const shown = new Set(drawn);
  const stack = (sheet?.layers || []).filter(layer => shown.has(layer.id));
  const nearest = side === "bottom" ? stack : [...stack].reverse();
  for (const kind of WORKING_KINDS) {
    const found = nearest.find(layer => layer.kind === kind);
    if (found) return found.id;
  }
  return null;
}
