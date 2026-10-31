// The viewer's single keys, as a design or CAD tool has them: a letter takes up a tool (V Select,
// M Measure; each drawing tool its own, P the pen, R the rectangle — Figma's), F frames the model.
// They are a viewer's while it owns the keyboard (`kit/shell/useViewerShortcuts.js`), never a text
// field's, and never with ⌘, Ctrl or Alt held. A tooltip shows each beside its name.
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
