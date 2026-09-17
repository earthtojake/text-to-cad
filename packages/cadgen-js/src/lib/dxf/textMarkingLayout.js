/** Where to put a text marking's rendered box, given the anchor DXF stored and how the file
 *  said the anchor relates to the text.
 *
 * DXF anchors text by a point plus an alignment: a dimension value hangs from its middle
 * centre, a title from its baseline left, a right-justified note from its baseline right.
 * The parser records the anchor and the alignment names; the viewer, which is the only
 * party that knows the rendered width, turns them into the box centre here. All in flat
 * sheet coordinates, before any fold.
 *
 * The box is `planeWidth` by `planeHeight` and holds the glyphs at cap height `heightMm`
 * sitting on a baseline `baselineFraction` of the box height above its bottom edge; that is
 * the canvas layout the viewer paints, expressed once so the placement matches it.
 */
export function textMarkingCenter({
  anchor,
  hAlign = "left",
  vAlign = "baseline",
  heightMm,
  planeWidth,
  planeHeight,
  rotationDeg = 0,
  baselineFraction = 0.28,
}) {
  const rotation = ((Number(rotationDeg) || 0) * Math.PI) / 180;
  const ex = [Math.cos(rotation), Math.sin(rotation)];
  const ey = [-Math.sin(rotation), Math.cos(rotation)];
  // Along the text: the anchor is the box's left, centre or right edge.
  const along = hAlign === "center" ? 0 : hAlign === "right" ? -planeWidth / 2 : planeWidth / 2;
  // Across the text: where the anchor sits relative to the baseline, in mm.
  const anchorAboveBaseline = vAlign === "top" ? heightMm : vAlign === "middle" ? heightMm / 2 : 0;
  // The box centre is half a box above the bottom edge; the baseline is baselineFraction up.
  const baselineToCenter = planeHeight * (0.5 - baselineFraction);
  const across = baselineToCenter - anchorAboveBaseline;
  return [
    anchor[0] + ex[0] * along + ey[0] * across,
    anchor[1] + ex[1] * along + ey[1] * across,
  ];
}
