// The viewer's single keys, as a design or CAD tool has them: a letter takes up a tool (V Select,
// M Measure; each drawing tool its own, P the pen, R the rectangle — Figma's), F frames the model.
// They are a viewer's while it owns the keyboard (`kit/shell/useViewerShortcuts.js`), never a text
// field's, and never with ⌘, Ctrl or Alt held. A tooltip shows each beside its name. The zoom's keys
// are the design tools' too (`ZOOM_SHORTCUTS`, `pressZoomKey`): + and - (with ⌘ or Ctrl as well, which
// would otherwise zoom the page), ⇧1 fits, ⇧2 frames the selection, ⇧0 is 100%.
//
// Importing this module has no environmental effects.

import { toolFamily } from "../../../annotation/tools.js";

/** A strip tool's key, by what it is. */
export const TOOL_SHORTCUTS = Object.freeze({ select: "V", measure: "M", fit: "F" });

/** Each drawing tool's key: Pencil's and Shapes' variants. */
export const DRAWING_SHORTCUTS = Object.freeze({
  freedraw: "P", highlighter: "⇧P", eraser: "E",
  rectangle: "R", line: "L", arrow: "⇧L", ellipse: "O", text: "T",
});

/** The key a keydown is, as the shortcuts spell it ("P", "⇧P"), or null for anything else. */
export function shortcutOfEvent(event) {
  if (!event || event.metaKey || event.ctrlKey || event.altKey) return null;
  const letter = /^Key([A-Z])$/.exec(String(event.code || ""))?.[1] ?? (/^[a-z]$/i.test(event.key || "") ? event.key.toUpperCase() : null);
  return letter ? `${event.shiftKey ? "⇧" : ""}${letter}` : null;
}

/** A shortcut as `aria-keyshortcuts` spells it: "⇧L" is "Shift+L". */
export const ariaShortcut = shortcut => (shortcut ? shortcut.replace(/^⇧/, "Shift+") : undefined);

/**
 * What a key does with the strip it is pressed over: a drawing tool's key takes its strip tool up
 * (Pencil or Shapes) with that tool in hand (`selectDrawing`), any other tool's takes that tool up,
 * and F frames the model (`fit`). A tool already in hand stays so. True when the key did something.
 *
 * @param {KeyboardEvent} event
 * @param {{ tools: readonly { id: string, shortcut?: string, active?: boolean, disabled?: boolean, onSelect(): void }[],
 *   selectDrawing?: ((tool: string) => void) | null, fit?: (() => unknown) | null }} options
 */
export function pressToolKey(event, { tools, selectDrawing = null, fit = null }) {
  const key = shortcutOfEvent(event);
  if (!key) return false;
  const take = tool => { if (tool && !tool.disabled) { if (!tool.active) tool.onSelect(); return true; } return false; };
  const drawing = selectDrawing && Object.keys(DRAWING_SHORTCUTS).find(id => DRAWING_SHORTCUTS[id] === key);
  if (drawing) {
    const strip = tools.find(tool => tool.id === toolFamily(drawing));
    if (!strip || strip.disabled) return false;
    selectDrawing(drawing);
    return take(strip);
  }
  if (key === TOOL_SHORTCUTS.fit && fit) { fit(); return true; }
  return take(tools.find(tool => tool.shortcut === key));
}

/** How far Zoom in and Zoom out go: half again, and back. */
export const ZOOM_FACTOR = 1.5;

/**
 * The zoom menu's keys, as Figma's shows them: Zoom in and out with ⌘ on a Mac (the host's
 * `environment.platform`) or Ctrl elsewhere — the plain + and - do the same — and ⇧0, F, ⇧2 (⇧1 fits too).
 */
export const zoomShortcuts = platform => (platform === "darwin"
  ? { in: "⌘+", out: "⌘-", actual: "⇧0", fit: TOOL_SHORTCUTS.fit, selection: "⇧2" }
  : { in: "Ctrl+=", out: "Ctrl+-", actual: "⇧0", fit: TOOL_SHORTCUTS.fit, selection: "⇧2" });

/** What a keydown asks of the zoom: "in", "out", "fit", "selection", "actual", or null. */
export function zoomKeyOfEvent(event) {
  if (!event || event.altKey) return null;
  const key = String(event.key || ""), code = String(event.code || "");
  if (key === "+" || key === "=" || code === "NumpadAdd") return "in";
  if (key === "-" || code === "NumpadSubtract") return "out";
  if (!event.shiftKey || event.metaKey || event.ctrlKey) return null;
  // ⇧ and a digit, by where the key is (its character is the layout's: ! on one, 1 on another).
  const digit = /^Digit([0-9])$/.exec(code)?.[1] ?? { "!": "1", "@": "2", ")": "0" }[key];
  return { 1: "fit", 2: "selection", 0: "actual" }[digit] ?? null;
}

/**
 * What a key does with the view's zoom (`kit/shell/ZoomControl.jsx`'s `ViewZoom`): + (or =) zooms in
 * and - out by `ZOOM_FACTOR`, ⇧1 fits, ⇧2 frames the selection (only with something picked), ⇧0 is 100%
 * (`zoomTo100`, or the fit where 100% is the fit). True when the key did something.
 *
 * @param {KeyboardEvent} event
 * @param {import("../shell/ZoomControl.jsx").ViewZoom | null | undefined} zoom
 */
export function pressZoomKey(event, zoom) {
  const action = zoom ? zoomKeyOfEvent(event) : null;
  if (action === "in" || action === "out") { zoom.zoomBy(action === "in" ? ZOOM_FACTOR : 1 / ZOOM_FACTOR); return true; }
  if (action === "fit") { zoom.fit(); return true; }
  if (action === "actual") { if (zoom.zoomTo100) zoom.zoomTo100(); else zoom.fit(); return true; }
  if (action === "selection" && zoom.zoomToSelection && zoom.selectionAvailable) { zoom.zoomToSelection(); return true; }
  return false;
}
