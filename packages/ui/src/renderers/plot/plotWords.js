/**
 * What the plot pane calls the document on screen. A plot's `kind` (`"board"`, `"schematic"`,
 * `"harness"`) changes WORDS and nothing else: every kind is laid out, drawn and navigated the
 * same way. Until the payload says what it is, the file's name does.
 */

/** Each kind's noun, and the tool whose picture of it the pane shows. */
const KINDS = Object.freeze({
  board: Object.freeze({ noun: "board", tool: "KiCad" }),
  schematic: Object.freeze({ noun: "schematic", tool: "KiCad" }),
  harness: Object.freeze({ noun: "harness", tool: "WireViz" })
});
const UNKNOWN = Object.freeze({ noun: "plot", tool: "its own tool" });

/** The kind a file's name implies, before its payload has said. */
const KIND_BY_NAME = [[/\.kicad_pcb$/i, "board"], [/\.kicad_sch$/i, "schematic"], [/[^/\\]\.harness\.yml$/i, "harness"]];

/** @param {string} path */
export function plotKindForPath(path) {
  return KIND_BY_NAME.find(([pattern]) => pattern.test(String(path || "")))?.[1] || "";
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
    remains: `The existing ${noun} remains visible.`,
    /** Host commands a flat picture cannot answer, each with the sentence its caller reads. */
    declined: Object.freeze({
      select: `${a} is shown as the picture ${tool} draws of it, without CAD references: it has no parts, faces `
        + "or edges to select. Selection needs a model with topology, such as a STEP file.",
      clearSelection: `${a} is shown as the picture ${tool} draws of it, without CAD references, so it never `
        + "has a selection to clear."
    }),
    noCamera: `${a} is a flat picture shown head on: it has no camera to pose. Zoom and pan it in the view, `
      + `or call resetCamera to fit the whole ${noun} again.`,
    noDisplay: `${a} has no Display settings: it is drawn in ${tool}’s own colours, on its own background, `
      + "with no surfaces, lighting or render mode to configure."
  });
}
