/** A dimensioned DRAWING rendered as what it is: lines.
 *
 * A cut layout has closed contours, so the viewer extrudes them into a flat pattern and renders
 * a solid. A drawing has no such thing -- plan views, sections, centre lines, dimensions and a
 * title block enclose nothing, and extruding them produces either nothing or nonsense. Issue
 * #246 is the case: a cabinetmaker's panel drawing, 20 dimensions, not one toolpath.
 *
 * So a drawing is drawn. Every entity becomes line segments in the sheet plane, grouped by
 * layer so the viewer can colour them from the layer table and hide them with the same layer
 * switches a cut layout uses. Nothing here bakes, and nothing needs a generated artifact: the
 * package's `geometry.json` already holds the parsed contours.
 */

const DEFAULT_ARC_SEGMENTS = 48;
const MIN_ARC_SEGMENTS = 8;

function normalizeLayerName(value) {
  return typeof value === "string" ? value : "";
}

function pushSegment(target, ax, ay, bx, by, elevation) {
  // The sheet lies in the mesher's XZ plane (y is out of the sheet), matching the flat-pattern
  // mesh, so a drawing and a cut layout share one camera fit and one orientation control.
  target.push(ax, elevation, ay, bx, elevation, by);
}

/** How finely to sample an arc: enough segments that the chord error stays under a fraction of
 * the radius, clamped so a tiny fillet does not cost 48 segments. */
function arcSegmentCount(sweepRadians, requested) {
  const full = Math.max(MIN_ARC_SEGMENTS, requested);
  const fraction = Math.min(1, Math.abs(sweepRadians) / (Math.PI * 2));
  return Math.max(MIN_ARC_SEGMENTS, Math.ceil(full * fraction));
}

function sampleArc(target, arc, elevation, requested) {
  const [cx, cy] = arc.center || [0, 0];
  const radius = Number(arc.radius);
  if (!Number.isFinite(radius) || radius <= 0) {
    return;
  }
  const start = Number(arc.startAngle ?? arc.start_angle ?? 0);
  const end = Number(arc.endAngle ?? arc.end_angle ?? 0);
  if (!Number.isFinite(start) || !Number.isFinite(end)) {
    return;
  }
  // Angles arrive in degrees, counter-clockwise, as DXF stores them.
  const startRadians = (start * Math.PI) / 180;
  let sweep = ((end - start) * Math.PI) / 180;
  if (sweep <= 0) {
    sweep += Math.PI * 2;
  }
  const steps = arcSegmentCount(sweep, requested);
  let previous = null;
  for (let index = 0; index <= steps; index += 1) {
    const angle = startRadians + (sweep * (index / steps));
    const point = [cx + (radius * Math.cos(angle)), cy + (radius * Math.sin(angle))];
    if (previous) {
      pushSegment(target, previous[0], previous[1], point[0], point[1], elevation);
    }
    previous = point;
  }
}

function sampleCircle(target, circle, elevation, requested) {
  sampleArc(
    target,
    { center: circle.center, radius: circle.radius, startAngle: 0, endAngle: 360 },
    elevation,
    requested
  );
}

/** Line segments for one drawing, grouped by layer.
 *
 * Returns `{ layers: [{ name, positions }] }` with `positions` a flat Float32Array of xyz pairs,
 * ready for a `LineSegments` per layer. Grouping by layer rather than emitting one buffer is what
 * lets the viewer colour and hide layers without re-sampling the drawing.
 */
export function buildDxfDrawingLineGroups(dxfData, options = null) {
  const geometry = dxfData?.geometry;
  const elevation = Number(options?.elevation) || 0;
  const requested = Number(options?.arcSegments) || DEFAULT_ARC_SEGMENTS;
  const byLayer = new Map();
  const bucket = (layer) => {
    const name = normalizeLayerName(layer);
    if (!byLayer.has(name)) {
      byLayer.set(name, []);
    }
    return byLayer.get(name);
  };
  if (!geometry || typeof geometry !== "object") {
    return { layers: [] };
  }
  for (const line of Array.isArray(geometry.lines) ? geometry.lines : []) {
    const start = line?.start;
    const end = line?.end;
    if (!Array.isArray(start) || !Array.isArray(end)) {
      continue;
    }
    pushSegment(bucket(line.layer), start[0], start[1], end[0], end[1], elevation);
  }
  for (const arc of Array.isArray(geometry.arcs) ? geometry.arcs : []) {
    sampleArc(bucket(arc?.layer), arc, elevation, requested);
  }
  for (const circle of Array.isArray(geometry.circles) ? geometry.circles : []) {
    sampleCircle(bucket(circle?.layer), circle, elevation, requested);
  }
  const layers = [];
  for (const [name, values] of byLayer) {
    if (!values.length) {
      continue;
    }
    layers.push({ name, positions: new Float32Array(values) });
  }
  return { layers };
}

/** Does this drawing hold anything a 2D render can show? */
export function drawingHasRenderableGeometry(dxfData) {
  return buildDxfDrawingLineGroups(dxfData).layers.length > 0;
}

/** The drawing's extent in the sheet plane, for fitting a camera to a document that has no mesh. */
export function drawingLineBounds(groups) {
  const min = [Infinity, Infinity, Infinity];
  const max = [-Infinity, -Infinity, -Infinity];
  for (const layer of groups?.layers || []) {
    const { positions } = layer;
    for (let index = 0; index < positions.length; index += 3) {
      for (let axis = 0; axis < 3; axis += 1) {
        const value = positions[index + axis];
        if (value < min[axis]) {
          min[axis] = value;
        }
        if (value > max[axis]) {
          max[axis] = value;
        }
      }
    }
  }
  return Number.isFinite(min[0]) ? { min, max } : null;
}
