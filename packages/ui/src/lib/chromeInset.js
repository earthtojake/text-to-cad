// How far the chrome that floats over a view sits in from its edges: the viewport's tool strip
// at its top centre, the panel's pill at its top-left, and the file explorer that opens over it. One number, so a person
// reads the explorer and the strip as the same kind of thing, at the same distance from the edge.
export const CHROME_INSET_PX = 8;
// How far the view's corner control (a flat view's zoom pill, `kit/shell/ZoomControl.jsx`) stands in from the view's
// right and bottom edges. A floating toolbar's shadow falls below it (`shadow-md`, 4px down): at the chrome's 8px the
// pill's shadow ran all the way into the bottom edge and the corner read tighter than the strip, whose 8px at the top is
// clear canvas, its shadow falling away from the edge. The shadow's 4px more puts clear canvas under the pill too, and
// leaves the strip's 8px of untouched canvas beside it at the right, the corner's two edges reading as one gap.
export const CORNER_INSET_PX = CHROME_INSET_PX + 4;
