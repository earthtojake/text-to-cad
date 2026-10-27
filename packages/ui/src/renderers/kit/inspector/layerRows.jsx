/**
 * The rows of a file's Layers section — a drawing's, a board's — drawn alike: ONE glyph per row in
 * one column (`docs/settings-ui.md`), a layer's colour box, or, where things hang under the layer,
 * its disclosure chevron instead, and that column starting on the section title's edge. A sidebar
 * section's head puts its title 12px in (`px-1`, then `pl-2`: `ToolPanel.jsx`); a list padded
 * `px-1` as the head is starts its rows `LAYER_ROW_INSET_PX` in, so a group's label, a colour box
 * and a chevron all stand on the title's line, and every name on one line after them.
 */

/** Where a row's glyph column starts, in a list padded `px-1`: the head's `pl-2`. */
export const LAYER_ROW_INSET_PX = 8;
/** The glyph column: a tree glyph's 12px, the glyph at its left edge. */
export const LAYER_GLYPH_COLUMN_CLASS = "flex h-6 w-3 shrink-0 items-center";

/** A layer's colour, a small box at the glyph column's left edge (`color` unset: the theme's ink). */
export function LayerSwatch({ color }) {
  return <span className={LAYER_GLYPH_COLUMN_CLASS} aria-hidden="true" data-layer-glyph="swatch">
    <span className="block size-2.5 rounded-[3px] shadow-[inset_0_0_0_1px_color-mix(in_oklab,currentColor_35%,transparent)]"
      style={{ backgroundColor: color || "var(--foreground)" }} />
  </span>;
}
