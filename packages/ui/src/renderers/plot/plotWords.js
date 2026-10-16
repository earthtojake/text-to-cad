/**
 * What the plot pane calls the document on screen. A board is laid out, drawn and navigated one
 * way, and named in its own words here; a payload of a kind this build does not know is spoken
 * of as a plot. Until the payload says what it is, the file's name does.
 */

/** Each kind's noun, and whose colours the pane draws it in. */
const KINDS = Object.freeze({ board: Object.freeze({ noun: "board", tool: "KiCad" }) });
const UNKNOWN = Object.freeze({ noun: "plot", tool: "KiCad" });

/** @param {string} path */
export function plotKindForPath(path) {
  return /\.kicad_pcb$/i.test(String(path || "")) ? "board" : "";
}

const capital = (text) => text.charAt(0).toUpperCase() + text.slice(1);
// One frozen set per kind, so a renderer can hand them to effects without re-running them.
const cache = new Map();

/**
 * Every sentence the pane says about a plot of `kind`. The same object for the same kind.
 *
 * @param {string} kind
 */
export function plotWords(kind) {
  const known = Object.hasOwn(KINDS, kind) ? kind : "";
  if (!cache.has(known)) cache.set(known, wordsFor(KINDS[known] || UNKNOWN));
  return cache.get(known);
}

function wordsFor({ noun, tool }) {
  const a = `A ${noun}`;
  return Object.freeze({
    noun,
    label: capital(noun),
    reading: `Reading ${noun}`,
    /** The update pill's status, while a newer revision is read behind the one on screen. */
    updateStatus: Object.freeze({ pending: true, label: `Updating ${noun}…` }),
    openFailed: `Couldn’t open the ${noun}`,
    captureFailed: `Couldn’t capture the ${noun}`,
    /** A copy to the clipboard (references, or a drawing) that the host refused. */
    copyFailed: `Couldn’t copy from the ${noun}`,
    remains: `The existing ${noun} remains visible.`,
    /** Host commands a flat picture cannot answer, each with the sentence its caller reads. */
    declined: Object.freeze({
      select: `${a} is shown as a flat picture without its index: it has no parts, pads or nets to select.`,
      clearSelection: `${a} is shown as a flat picture without its index, so it never has a selection to clear.`
    }),
    noCamera: `${a} is a flat picture shown head on: it has no camera to pose. Zoom and pan it in the view, `
      + `or call resetCamera to fit the whole ${noun} again.`,
    noDisplay: `${a} has no Display settings: it is drawn in ${tool}’s own colours, on its own background, `
      + "with no surfaces, lighting or render mode to configure.",
    /** A board drawn layer by layer: its Display settings are the person's, in the view. */
    displayInView: `${a}’s Display settings (the side it is seen from, which layers are drawn, its copper pours) `
      + "are set in the view’s Display menu, not by a host; it has no surfaces, lighting or render mode."
  });
}
