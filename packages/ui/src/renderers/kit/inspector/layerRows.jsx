import { TreeRowGlyph } from "@cad/ui/primitives/tree-row";

/**
 * A layer's colour, a small box in a row's glyph slot (`primitives/tree-row.jsx`), its left edge on
 * the slot's, the panel's 16px line, as the search icon's is (`color` unset: the theme's ink). A
 * board's layer row has it in its one slot; a drawing's, in the box after its slot.
 */
export function LayerSwatch({ color }) {
  return <TreeRowGlyph data-layer-glyph="swatch">
    <span className="block size-2.5 justify-self-start rounded-[3px] shadow-[inset_0_0_0_1px_color-mix(in_oklab,currentColor_35%,transparent)]"
      style={{ backgroundColor: color || "var(--foreground)" }} />
  </TreeRowGlyph>;
}
