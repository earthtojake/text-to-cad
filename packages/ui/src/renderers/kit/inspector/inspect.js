import { createContext, useContext } from "react";

/**
 * What a view says of what it picks: ONE shape, which the Selected pane, a Quick Edit chip's card and
 * the hover tip all read (`ItemDetail.jsx`, `HoverTip.jsx`), so a pick reads the same wherever it is
 * shown. A view hands it to its frame (`ViewFrame.jsx`'s `inspect`); nothing here knows what is shown.
 *
 * @typedef {object} DetailFact  One line of what it is.
 * @property {string} label
 * @property {import("react").ReactNode} value  A string, or a value with its own parts (a coordinate, a link).
 * @property {string} [title]  What the label means, as its hint.
 * @property {string | false | (() => string)} [copy]  What a click on the value copies (`InfoRow`'s): false for none.
 * @property {string} [section]  The group it is in, ruled off from the one before it ("Parent joint").
 *
 * @typedef {object} DetailRow  One of what it is connected to, a row that picks it.
 * @property {string} id
 * @property {string} kind  Its glyph.
 * @property {string} pick  What a press on it selects.
 * @property {string} label
 * @property {string} [detail]  Muted, after its label.
 *
 * @typedef {object} DetailItem
 * @property {string} id  Stable while it describes the same pick.
 * @property {string} pick  What a press on its name selects again ("" for none: a chip's card, which copies).
 * @property {string} kind  Its glyph: a key of the view's `glyphs`, else a pick glyph (`pickGlyph.jsx`).
 * @property {string} title  Its name ("U3.5", "Circle on CUT", "upper_arm").
 * @property {string} [tip]  What it is, short, after its name in the hover tip ("U12.57 · /TVRAM12").
 * @property {string} [what]  A line in words under its name ("Pad of U3 · ATmega328P").
 * @property {string} [ref]  Its reference id, the card's and the pane's ID row.
 * @property {DetailFact[]} facts
 * @property {{ title: string, count?: string, rows: DetailRow[] } | null} [related]  What it is connected to.
 *
 * @typedef {object} Inspect  A view's picks, as its frame reads them.
 * @property {readonly string[]} selected  What is picked, in order.
 * @property {(id: string) => DetailItem | null} describe  One pick.
 * @property {string} [hovered]  What a press would pick now ("" for nothing): the hover tip's.
 * @property {(id: string) => string} [tip]  The hover tip's words for a pick, from what is in hand: its name
 *   and its short kind, measuring and listing nothing (the tip runs as the pointer moves; `describe` runs
 *   for the pane and a card). Without it, `hoverTipText(describe(id))`.
 * @property {Record<string, import("react").ComponentType<any>>} [glyphs]  The view's own glyphs, by kind.
 * @property {string} [data]  The prefix of the pane's data attributes (`data-<data>-detail-row`).
 * @property {(id: string, options?: { multiSelect?: boolean }) => void} select
 * @property {(id: string) => void} hover
 * @property {(ids: readonly string[]) => void} [frame]  Frames them (a double-click on a row).
 * @property {(ids: readonly string[]) => void} [show]  Brings them on screen without framing (a press on a row).
 * @property {() => void} [onSelect]  A row pressed: the view takes Select in hand.
 * @property {(ids: readonly string[]) => string} [copyText]  What the pane's name copies.
 */

export const InspectContext = createContext(null);
/** The view's picks, where a detail is drawn inside its frame (the pane, a chip's card); null outside one. */
export const useInspect = () => useContext(InspectContext);

/** The hover tip's words for an item: its name, and what it is, short ("U12.57 · /TVRAM12"); "" for none. */
export function hoverTipText(item) {
  return item?.title ? [item.title, item.tip].filter(Boolean).join(" · ") : "";
}

/**
 * The picks as the Selected pane's switcher lists them (`ItemDetail.jsx`'s `SelectedPane`): each its glyph, its name
 * and its short kind, in the order they were picked, those the view can describe.
 * @param {readonly string[]} ids
 * @param {(id: string) => DetailItem | null} describe
 * @returns {{ id: string, kind: string, label: string, detail: string }[]}
 */
export function pickRows(ids, describe) {
  return ids.map(id => {
    const item = describe(id);
    return item ? { id, kind: item.kind, label: item.title, detail: item.tip || "" } : null;
  }).filter(Boolean);
}

/**
 * The active pick among several (Blender's active object), once the picks go from `before` to `after`: a pick added
 * becomes it (the last of those added, as they were picked); else it stays while it is picked, and when it is let go
 * of, the nearest pick left takes over, the one after it, else the one before it. "" with nothing picked.
 * @param {readonly string[]} before
 * @param {readonly string[]} after
 * @param {string} active
 */
export function nextActivePick(before, after, active) {
  if (!after.length) return "";
  const added = after.filter(id => !before.includes(id));
  if (added.length) return added.at(-1);
  if (after.includes(active)) return active;
  const at = before.indexOf(active);
  if (at < 0) return after.at(-1);
  return before.slice(at + 1).find(id => after.includes(id)) ?? before.slice(0, at).reverse().find(id => after.includes(id)) ?? after.at(-1);
}
