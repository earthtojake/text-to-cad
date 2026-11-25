import { TreeRowGlyph } from "@cad/ui/primitives/tree-row";

const CHIP_CLASS = "block size-2.5 shrink-0 rounded-[3px] shadow-[inset_0_0_0_1px_color-mix(in_oklab,currentColor_35%,transparent)]";

/**
 * A layer's colour, a small box in a row's one glyph slot (`primitives/tree-row.jsx`) in place of a
 * kind icon, its left edge on the slot's, the panel's 16px line, as the search icon's is (`color`
 * unset: the theme's ink). A layer that is a branch (a drawing's, with block references under it) has
 * its chevron in the slot, and its colour after its name (`LayerColorMark`).
 */
export function LayerSwatch({ color }) {
  return <TreeRowGlyph data-layer-glyph="swatch">
    <span className={`${CHIP_CLASS} justify-self-start`} style={{ backgroundColor: color || "var(--foreground)" }} />
  </TreeRowGlyph>;
}

/** A branch layer's colour, the same box, after its name: its slot is its chevron's. */
export function LayerColorMark({ color }) {
  return <span aria-hidden="true" data-layer-glyph="mark" className={CHIP_CLASS} style={{ backgroundColor: color || "var(--foreground)" }} />;
}
