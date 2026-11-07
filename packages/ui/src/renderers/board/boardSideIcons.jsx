// Flip's two glyphs (`BoardDisplay.jsx`): the board as two stacked layers, Lucide's `layers-2`, the side it is
// seen from solid. From the top the upper layer is solid over the lower one's edge; from the bottom the same
// glyph mirrored top to bottom, the solid layer under. Drawn at Lucide's line (2), as the strip's other glyphs
// are, so the two states carry the same weight as each other and as their neighbours; the solid layer is the
// line's colour at 85%, its own edge the line itself, so it reads as solid hovered or not, light or dark.
//
// Each is set 0.75 units off the grid's middle, toward its outline layer: the solid layer holds most of the ink,
// and centred by its box the glyph's weight sat 1.4 units off the button's middle (0.8px at 14px); this puts it
// 0.6 units off, its stroke still inside the grid.

const LAYER = "M13 13.74a2 2 0 0 1-2 0L2.5 8.87a1 1 0 0 1 0-1.74L11 2.26a2 2 0 0 1 2 0l8.5 4.87a1 1 0 0 1 0 1.74z";
const EDGE = "m20 14.285 1.5.845a1 1 0 0 1 0 1.74L13 21.74a2 2 0 0 1-2 0l-8.5-4.87a1 1 0 0 1 0-1.74l1.5-.845";
const OPTICAL_SHIFT = 0.75;

function SideIcon({ side, className, strokeWidth = 2, ...props }) {
  // The bottom's glyph is the top's mirrored about the grid's middle, after the top's shift: y to 24 - (y + shift).
  const place = side === "bottom" ? `matrix(1 0 0 -1 0 ${24 - OPTICAL_SHIFT})` : `translate(0 ${OPTICAL_SHIFT})`;
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={strokeWidth} strokeLinecap="round"
      strokeLinejoin="round" aria-hidden="true" focusable="false" data-board-side-icon={side} {...props}>
      <g transform={place}>
        <path d={LAYER} fill="currentColor" fillOpacity="0.85" />
        <path d={EDGE} />
      </g>
    </svg>
  );
}

/** The board seen from the top: the upper layer solid. */
export function BoardTopSideIcon(props) {
  return <SideIcon side="top" {...props} />;
}

/** The board seen from the bottom: the lower layer solid, the top's glyph mirrored. */
export function BoardBottomSideIcon(props) {
  return <SideIcon side="bottom" {...props} />;
}
