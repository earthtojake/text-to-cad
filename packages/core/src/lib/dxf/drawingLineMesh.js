/** DXF line work as a snapshot-able MESH: strokes extruded to hairline ribbons.
 *
 * The interactive viewer draws a DXF's non-solid line work as `LineSegments` — a
 * document-profile drawing (dimensions, sections, a title block) through
 * `buildDrawingLines.js`, and a cut layout's ENGRAVE/score overlay through
 * `extractDxfScorePolylines`. The headless snapshot pipeline consumes a triangle GLB,
 * and teaching that whole chain (writeGlb, the browser renderer, theming) about line
 * primitives is a lot of new surface for two consumers. So the SAME strokes are turned
 * into thin quads lying in the sheet plane: every segment becomes a ribbon two triangles
 * wide, at a width scaled from the drawing's extent so hairlines stay hairlines at any
 * sheet size.
 *
 * Both producers emit in the MESHER's frame — the sheet lies in XZ with y out of the
 * sheet — so a ribbon soup composes with `buildDxfPreviewMeshData`'s prism and rides the
 * same `dxfSoupToGlbPositions` conversion into GLB space.
 *
 * Text markings are NOT rendered here — the viewer rasterizes DXF TEXT/MTEXT strings onto
 * the sheet itself. Engraved lettering authored as OUTLINES (which is what `@dxf` emits,
 * and what a marking toolchain actually consumes) is geometry and does come through.
 */

import { buildDxfDrawingLineGroups, drawingLineBounds } from "./buildDrawingLines.js";
import { extractDxfScorePolylines } from "./buildPreviewMesh.js";

// Ribbon half-width as a fraction of the drawing's bounding diagonal, with an
// absolute floor so a tiny detail drawing still produces visible (and non-degenerate)
// geometry. 0.075% of the diagonal reads as a crisp hairline at snapshot resolutions.
const RELATIVE_HALF_WIDTH = 7.5e-4;
const MIN_HALF_WIDTH_MM = 0.05;

/** How far above the sheet's top face an engraved stroke floats, in mm. Large enough
 *  never to z-fight the face it marks, small enough to read as lying ON it — the same
 *  bargain `DXF_BEND_GUIDE_ELEVATION_MM` strikes for the dashed crease guides. */
export const DXF_ENGRAVE_ELEVATION_MM = 0.03;

/** The ink an engraved/scored stroke is drawn in. Dark rather than the sheet's own
 *  colour: a marking is a stroke on the surface, and shading alone cannot separate a
 *  0.03 mm step from the face under it. */
export const DXF_ENGRAVE_STROKE_COLOR = "#1f2937";

function halfWidthForBounds(bounds, requested) {
  const spanX = bounds.max[0] - bounds.min[0];
  const spanZ = bounds.max[2] - bounds.min[2];
  const diagonal = Math.hypot(spanX, spanZ);
  return Math.max(
    Number(requested) || 0,
    diagonal * RELATIVE_HALF_WIDTH,
    MIN_HALF_WIDTH_MM,
  );
}

/** One segment as two triangles, pushed into `out` (a plain array of xyz floats).
 *  Endpoints are given in the mesher's frame: x/z in the sheet, y out of it. */
function pushRibbon(out, ax, ay, az, bx, by, bz, halfWidth) {
  const dx = bx - ax;
  const dz = bz - az;
  const length = Math.hypot(dx, dz);
  if (!(length > 0)) {
    return;
  }
  // Perpendicular in the sheet plane, half-width long.
  const px = (-dz / length) * halfWidth;
  const pz = (dx / length) * halfWidth;
  // Quad corners: a-p, a+p, b+p, b-p — two triangles, both wound to face +Y
  // (out of the sheet; the material is double-sided, so this is for lighting).
  out.push(
    ax - px, ay, az - pz,
    ax + px, ay, az + pz,
    bx + px, by, bz + pz,

    ax - px, ay, az - pz,
    bx + px, by, bz + pz,
    bx - px, by, bz - pz,
  );
}

/** Triangle-soup positions (Float32Array, xyz per vertex) for one drawing's line work,
 * or an empty array when the drawing holds nothing renderable. Deterministic for a
 * given parse: segment order follows the layer grouping, width follows the bounds. */
export function drawingLinesToRibbonPositions(dxfData, options = null) {
  const groups = buildDxfDrawingLineGroups(dxfData, options);
  if (!groups.layers.length) {
    return new Float32Array(0);
  }
  const halfWidth = halfWidthForBounds(drawingLineBounds(groups), options?.halfWidth);

  const out = [];
  for (const layer of groups.layers) {
    const { positions } = layer;
    // Segments arrive as xyz pairs in the sheet plane (y out of the sheet).
    for (let index = 0; index + 5 < positions.length; index += 6) {
      pushRibbon(
        out,
        positions[index], positions[index + 1], positions[index + 2],
        positions[index + 3], positions[index + 4], positions[index + 5],
        halfWidth,
      );
    }
  }
  return Float32Array.from(out);
}

/**
 * Triangle-soup positions for a cut layout's ENGRAVE/score overlay — engraved-layer
 * geometry plus any cut-layer chain that never closes — laid on the flat pattern's TOP
 * face. This is the mesh twin of the viewer's score `LineSegments`: without it a
 * snapshot of an engraved plate shows a blank sheet, because the prism is built from
 * closed cut contours alone and every marking is dropped on the floor.
 *
 * `thicknessMm` is the prism thickness the strokes ride on; the ribbons sit
 * `DXF_ENGRAVE_ELEVATION_MM` clear of its face. `options.elevationSign` picks WHICH
 * face — the mesher's +y is the sheet's top in mesher space, but a consumer that
 * re-maps the axes may have flipped it (`dxfSoupToGlbPositions` sends +y to CAD -Z),
 * and a marking on the hidden face is a marking that does not render. Returns an empty
 * array when the drawing carries no markings.
 */
export function dxfEngraveRibbonPositions(dxfData, thicknessMm, options = null) {
  let polylines;
  try {
    polylines = extractDxfScorePolylines(dxfData);
  } catch {
    // A drawing whose cut geometry cannot be chained still has engraved markings
    // worth showing, but there is no separate extractor for them; no overlay is
    // the honest answer, not a thrown snapshot.
    return new Float32Array(0);
  }
  if (!polylines.length) {
    return new Float32Array(0);
  }

  // Stroke weight follows the WHOLE sheet, not the markings' own extent: a serial
  // number in one corner of a large panel must draw at the same hairline as the
  // panel's dimension lines, and scaling it to the lettering's bounding box makes
  // small markings vanish while large ones go fat.
  const bounds = dxfData?.bounds || {};
  const width = Math.abs(Number(bounds.width) || 0);
  const height = Math.abs(Number(bounds.height) || 0);
  const halfWidth = halfWidthForBounds(
    { min: [0, 0, 0], max: [width, 0, height] },
    options?.halfWidth,
  );
  const elevationSign = options?.elevationSign === -1 ? -1 : 1;
  const elevation = elevationSign
    * ((Math.abs(Number(thicknessMm) || 0) / 2) + DXF_ENGRAVE_ELEVATION_MM);

  const out = [];
  for (const polyline of polylines) {
    for (let index = 0; index + 1 < polyline.length; index += 1) {
      const a = polyline[index];
      const b = polyline[index + 1];
      pushRibbon(out, a[0], elevation, a[1], b[0], elevation, b[1], halfWidth);
    }
  }
  return Float32Array.from(out);
}
