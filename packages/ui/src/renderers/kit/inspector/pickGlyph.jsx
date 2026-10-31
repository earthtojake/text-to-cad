import { createElement } from "react";

// What a Quick Edit chip carries, as a glyph: a reference's pick drawn as Select's modes draw them
// (`SelectionModes.jsx`), on the 24-unit grid — a face as a faint cube with its top face solid, an
// edge as a faint cube with its front edge heavy, a solid as the cube whole, a vertex as a dot in a
// ring — and a measurement's ruler and the annotation's pen (lucide's). One drawing, for React
// (`PickGlyph`) and for a plain DOM node (`pickGlyphNode`, Quick Edit's note), so a chip and its
// pill in the note are the same.

const CUBE = "M12 2.5 20.5 7.25v9.5L12 21.5l-8.5-4.75v-9.5Z";
const SEAMS = "M3.5 7.25 12 12l8.5-4.75M12 12v9.5";
const FAINT = [["path", { d: CUBE, "stroke-width": "1.5", "stroke-opacity": "0.45" }], ["path", { d: SEAMS, "stroke-width": "1.5", "stroke-opacity": "0.45" }]];
const GLYPHS = Object.freeze({
  face: [...FAINT, ["path", { d: "M12 2.5 20.5 7.25 12 12 3.5 7.25Z", fill: "currentColor", "stroke-width": "2" }]],
  edge: [...FAINT, ["path", { d: "M12 12v9.5", "stroke-width": "3.5" }]],
  solid: [["path", { d: CUBE, "stroke-width": "2" }], ["path", { d: SEAMS, "stroke-width": "2" }]],
  vertex: [["circle", { cx: "12", cy: "12", r: "8.5", "stroke-width": "1.5", "stroke-opacity": "0.45" }], ["circle", { cx: "12", cy: "12", r: "4", fill: "currentColor", stroke: "none" }]],
  ruler: [["path", { d: "M21.3 15.3a2.4 2.4 0 0 1 0 3.4l-2.6 2.6a2.4 2.4 0 0 1-3.4 0L2.7 8.7a2.41 2.41 0 0 1 0-3.4l2.6-2.6a2.41 2.41 0 0 1 3.4 0Z", "stroke-width": "2" }],
    ["path", { d: "m14.5 12.5 2-2", "stroke-width": "2" }], ["path", { d: "m11.5 9.5 2-2", "stroke-width": "2" }],
    ["path", { d: "m8.5 6.5 2-2", "stroke-width": "2" }], ["path", { d: "m17.5 15.5 2-2", "stroke-width": "2" }]],
  pencil: [["path", { d: "M21.174 6.812a1 1 0 0 0-3.986-3.987L3.842 16.174a2 2 0 0 0-.5.83l-1.321 4.352a.5.5 0 0 0 .623.622l4.353-1.32a2 2 0 0 0 .83-.497z", "stroke-width": "2" }],
    ["path", { d: "m15 5 4 4", "stroke-width": "2" }]],
});
const SVG = { viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", "stroke-linecap": "round", "stroke-linejoin": "round" };
const camel = attrs => Object.fromEntries(Object.entries(attrs).map(([name, value]) => [name.replace(/-(\w)/g, (_, c) => c.toUpperCase()), value]));

/** Whether there is a glyph for `kind` ("face", "edge", "solid", "vertex", "ruler", "pencil"). */
export const hasPickGlyph = kind => Boolean(GLYPHS[kind]);

/** `kind`'s glyph, sized by `className` (coloured by `color`, else the text's); nothing for a kind without one. */
export function PickGlyph({ kind, className, color = null }) {
  const shapes = GLYPHS[kind];
  if (!shapes) return null;
  return <svg {...camel(SVG)} className={className} style={color ? { color } : undefined} aria-hidden="true" data-pick-glyph={kind}>
    {shapes.map(([tag, attrs], index) => createElement(tag, { key: index, ...camel(attrs) }))}
  </svg>;
}

/** The same glyph as a DOM node, for markup React does not own. */
export function pickGlyphNode(document, kind, className = "", color = null) {
  const ns = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(ns, "svg");
  for (const [name, value] of Object.entries(SVG)) svg.setAttribute(name, value);
  svg.setAttribute("class", className);
  if (color) svg.style.color = color;
  svg.setAttribute("aria-hidden", "true");
  svg.setAttribute("data-pick-glyph", kind);
  for (const [tag, attrs] of GLYPHS[kind] || []) {
    const shape = document.createElementNS(ns, tag);
    for (const [name, value] of Object.entries(attrs)) shape.setAttribute(name, value);
    svg.append(shape);
  }
  return svg;
}

/**
 * A pick's compact name: its part, then its kind's glyph and its number on that part ("base ◧5"),
 * or, for several of one kind, their count ("base ◧×5"). The words ("base · face 5") stay its
 * accessible name. With no part (`name` left out: a document of one part, which the page names
 * already), `words` after the glyph alone ("face 5", "5 faces").
 * @typedef {{ name?: string, kind: string, number?: string, count?: number, words?: string }} CompactName
 */
export const compactSuffix = compact => (compact.count ? `×${compact.count}` : String(compact.number || ""));
