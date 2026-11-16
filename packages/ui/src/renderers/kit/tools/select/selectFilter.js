// What a picking tool takes, as the person filters it from the dropdown on its chevron
// (`SelectFilterMenu.jsx`, every file's): a list of the kinds a click may take, each ticked on its own
// (KiCad's Selection Filter). A kind left out is not pickable. Beside the kinds a filter may hold
// `extras`, boxes that are no kind (a board's Locked items, a posable model's Position): the menu's
// All ticks or unticks the kinds alone and leaves them as they are.
//
// Importing this module has no environmental effects.

/** Whether `filter` picks `id`'s kind. */
export const selects = (filter, id) => filter.includes(id);

/**
 * `filter` with `id` ticked (`on`) or not, in `order` (every id the filter may hold, in the order it is
 * kept): what is outside `order` is dropped.
 *
 * @param {readonly string[]} filter
 * @param {string} id
 * @param {boolean} on
 * @param {readonly string[]} order
 */
export function tickFilter(filter, id, on, order) {
  return order.filter(other => (other === id ? on : filter.includes(other)));
}

/** `filter` with every one of `kinds` ticked (`on`) or none, the rest of `order` as it was. */
export function tickAllKinds(filter, kinds, on, order) {
  return order.filter(other => (kinds.includes(other) ? on : filter.includes(other)));
}

/** All's box: ticked when every kind is, a dash ("indeterminate") when some are, else unticked. */
export function allTicked(filter, kinds) {
  const count = kinds.filter(id => filter.includes(id)).length;
  return count === kinds.length ? true : count ? "indeterminate" : false;
}

/** The glyph a filter's badge wears where nothing else fits: a funnel, "filtered". */
export const FILTER_BADGE = "filter";

/**
 * The badge on the tool's strip button (`modeGlyphs.jsx`'s `ToolModeIcon` `mode`): none ("all") when
 * every kind is ticked; the kind's glyph (`glyphs`) when exactly one is; where no kind is and `alone` is
 * ticked (Position: the knobs alone, the model picking nothing), its glyph; else the funnel — several
 * kinds, none at all, or one with no glyph of its own.
 *
 * @param {readonly string[]} filter
 * @param {readonly string[]} kinds
 * @param {{ glyphs?: Record<string, string>, alone?: string | null }} [options]
 */
export function filterBadge(filter, kinds, { glyphs = {}, alone = null } = {}) {
  const on = kinds.filter(id => filter.includes(id));
  if (on.length === kinds.length) return "all";
  if (on.length === 1) return glyphs[on[0]] ?? FILTER_BADGE;
  if (!on.length && alone && filter.includes(alone)) return glyphs[alone] ?? FILTER_BADGE;
  return FILTER_BADGE;
}

// A box's word in telemetry's name for it, where it is not the id itself: Measure's kinds and the
// overlays in the plural, as the names an earlier release sent spell them.
const CONTROL_WORDS = Object.freeze({ vertex: "vertices", edge: "edges", face: "faces", annotation: "annotations", measurement: "measurements" });

/**
 * The name telemetry counts a press on a filter's box by (`usage/controls.js`): `<tool>_filter_<box>`,
 * "all" for All, snake case (`select_filter_faces`, `measure_filter_vertices`, `select_filter_rule_areas`).
 *
 * @param {string} tool  The menu's `name`: "select" or "measure".
 * @param {string} id
 */
export function filterControl(tool, id) {
  const word = CONTROL_WORDS[id] ?? id.replace(/[A-Z]/g, letter => `_${letter.toLowerCase()}`);
  return `${tool}_filter_${word}`;
}
