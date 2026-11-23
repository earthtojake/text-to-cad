import { createContext, useContext } from "react";

/**
 * What a view says of what it picks: ONE shape, which a Quick Edit chip's card and the hover tip read
 * (`ItemDetail.jsx`, `HoverTip.jsx`), so a pick reads the same wherever it is shown: the thing in focus
 * alone, its name and a few key facts, never what it holds or is connected to. A view hands it to its frame (`ViewFrame.jsx`'s `inspect`); nothing here knows what is shown.
 *
 * @typedef {object} DetailFact  One line of what it is.
 * @property {string} label
 * @property {import("react").ReactNode} value  A string, or a value with its own parts (a coordinate, a link).
 * @property {string} [title]  What the label means, as its hint.
 * @property {string | false | (() => string)} [copy]  What a click on the value copies (`InfoRow`'s): false for none.
 *
 * @typedef {object} DetailItem
 * @property {string} id  Stable while it describes the same pick.
 * @property {string} pick  What a press on its name selects again ("" for none: a chip's card, which copies).
 * @property {string} kind  Its glyph: a key of the view's `glyphs`, else a pick glyph (`pickGlyph.jsx`).
 * @property {string} title  Its name ("U3.5", "Circle on CUT", "upper_arm").
 * @property {string} [tip]  What it is, short, after its name in the hover tip ("U12.57 · /TVRAM12").
 * @property {DetailFact[]} facts  Its few key facts.
 *
 * @typedef {object} Inspect  A view's picks, as its frame reads them.
 * @property {readonly string[]} selected  What is picked, in order.
 * @property {(id: string) => DetailItem | null} describe  One pick.
 * @property {string} [hovered]  What a press would pick now ("" for nothing): the hover tip's.
 * @property {(id: string) => string} [tip]  The hover tip's words for a pick, from what is in hand: its name
 *   and its short kind, measuring and listing nothing (the tip runs as the pointer moves; `describe` runs
 *   for a chip's card). Without it, `hoverTipText(describe(id))`.
 * @property {Record<string, import("react").ComponentType<any>>} [glyphs]  The view's own glyphs, by kind.
 * @property {string} [data]  The prefix of a card's data attributes (`ItemDetail.jsx`'s `data-<data>-detail-row`).
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
