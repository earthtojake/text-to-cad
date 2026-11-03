/**
 * What Select takes on a board, as pure rules (`tools.js` names the tools): its filter's kinds and
 * what a press may take under each (the board index's `kinds`, `@cad/core`'s `board2d/boardIndex.js`),
 * Point or area, and the working layer a point or an area is on.
 *
 * Importing this module has no environmental effects.
 */

/** What Select's filter offers on a board, in the order its menu lists them, All taking them all. */
export const BOARD_SELECT_KINDS = Object.freeze(["parts", "pads", "nets", "tracks", "vias", "zones", "texts", "dimensions", "graphics"]);
/** Select's other way to point: a place, not a thing (its own mode, after the kinds). */
export const BOARD_POINT_MODE = "points";

// Each kind alone: what a press may take (the board index's `kinds`, `board2d/boardIndex.js`).
const ALONE = Object.freeze({
  parts: { parts: true }, pads: { pads: true }, tracks: { tracks: true }, vias: { vias: true }, zones: { zones: true, zoneFill: true },
  texts: { texts: true }, dimensions: { dimensions: true }, graphics: { shapes: true, footprintShapes: true }
});

/**
 * What a press may pick under a filter (the board index's `kinds`), or null for nothing. All (every
 * kind ticked) takes the most specific thing under the pointer — a pad, then a via, a track, a text,
 * a dimension, a board's graphic, a pour by its outline, then a part, a footprint's own graphics
 * being its part's, as KiCad picks; one kind alone takes that kind wherever it is (a zone anywhere
 * inside it, a footprint's graphic itself). Nets alone takes whole nets: any copper under the
 * pointer, a pad's or a pour's too, picks its net. Point or area picks nothing.
 * @param {readonly string[]} filter
 */
export function boardPickKinds(filter) {
  const kinds = BOARD_SELECT_KINDS.filter(id => filter.includes(id));
  if (!kinds.length) return null;
  if (kinds.length === BOARD_SELECT_KINDS.length) {
    return { pads: true, tracks: true, vias: true, zones: true, texts: true, dimensions: true, shapes: true, parts: true, nets: false };
  }
  if (kinds.length === 1 && kinds[0] === "nets") return { pads: true, tracks: true, vias: true, zones: true, zoneFill: true, nets: true };
  // A filter of some kinds (a host's, or one kept from before): each kind's reach, together; nets as copper.
  const picked = Object.assign({}, ...kinds.map(id => ALONE[id] || {}));
  if (kinds.includes("nets")) Object.assign(picked, { tracks: true, vias: true });
  return picked;
}

/** Whether a filter is Select's Point or area: a tap names a point, a drag an area. */
export const boardPointing = filter => filter.includes(BOARD_POINT_MODE);

// What a working layer is, nearest first: the copper, then what is printed on the board, then the rest.
const WORKING_KINDS = Object.freeze(["copper", "silk", "fab", "courtyard", "user", "mask", "paste", "adhesive"]);
/**
 * The layer a point or an area is on: the view's working layer, the one drawn nearest the eye of the
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
