// Analytic STEP geometry helpers. Coordinates are component-local, in millimetres.
export const dot = (a, b) => a.reduce((sum, v, i) => sum + v * b[i], 0);
export const sub = (a, b) => a.map((v, i) => v - b[i]);
export const add = (a, b) => a.map((v, i) => v + b[i]);
export const scale = (a, s) => a.map(v => v * s);
export const cross = (a, b) => [a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]];
export const length = a => Math.sqrt(dot(a, a));
export const near = (a, b) => Number.isFinite(a) && Number.isFinite(b) && Math.abs(a-b) < 1e-4;
export const same = (a, b) => a?.length === 3 && b?.length === 3 && length(sub(a, b)) < 1e-4;
export const parallel = (a, b) => a?.length === 3 && b?.length === 3 && Math.abs(dot(a, b)) > 0.999999;
export const unique = a => [...new Set(a)].sort((a, b) => a-b);
export const inward = f => dot(cross(f.surface.xdir, f.surface.ydir), f.surface.zdir) * (f.reversed ? -1 : 1) < 0;
export const faceEdges = f => unique((f.loops || []).flatMap(loop => loop.map(e => e.edgeOrd)));
export const centroid = edges => scale(edges.reduce((sum, e) => add(sum, e.center), [0,0,0]), 1/edges.length);

function point(curve, t) {
  if (curve.kind === 'line') return add(curve.origin, scale(curve.dir, t));
  if (curve.kind === 'circle') return add(curve.origin, add(scale(curve.xdir, curve.radius*Math.cos(t)), scale(curve.ydir, curve.radius*Math.sin(t))));
  return null;
}

export function translatedContours(a, b, delta) {
  if (!a.length || a.length !== b.length) return false;
  const remaining = [...b];
  for (const edge of a) {
    const curve = edge.curve;
    if (!['line', 'circle'].includes(curve?.kind) || !curve.range) return false;
    const i = remaining.findIndex(other => {
      const c = other.curve;
      if (c?.kind !== curve.kind || !c.range || !near(edge.length, other.length) || !same(add(edge.center, delta), other.center)) return false;
      if (c.kind === 'circle' && (!near(c.radius, curve.radius) || !parallel(c.zdir, curve.zdir) || !same(add(curve.origin, delta), c.origin))) return false;
      if (c.kind === 'circle' && near(edge.length, 2*Math.PI*curve.radius)) return true;
      const [start, end] = curve.range.map(t => add(point(curve, t), delta));
      const [x, y] = c.range.map(t => point(c, t));
      return same(start, x) && same(end, y) || same(start, y) && same(end, x);
    });
    if (i < 0) return false;
    remaining.splice(i, 1);
  }
  return true;
}

// Exact line integral for planar line/circle contours, not a bounding-box sketch.
export function contourArea(loop, edges, normal) {
  let integral = 0;
  for (const use of loop) {
    const c = edges.get(use.edgeOrd)?.curve;
    if (!c?.range || !['line','circle'].includes(c.kind)) return NaN;
    const [a,b] = c.range;
    let term;
    if (c.kind === 'line') term = dot(cross(point(c,a), point(c,b)), normal);
    else term = c.radius * ((Math.cos(b)-Math.cos(a))*dot(cross(c.origin,c.xdir),normal) + (Math.sin(b)-Math.sin(a))*dot(cross(c.origin,c.ydir),normal)) + c.radius*c.radius*(b-a)*dot(cross(c.xdir,c.ydir),normal);
    integral += (use.reversed ? -1 : 1)*term;
  }
  return Math.abs(integral/2);
}

export function curveSamplePoints(curve) {
  if (!curve?.range || !['line','circle'].includes(curve.kind)) return [];
  const [a,b]=curve.range;
  return [0,0.25,0.5,0.75,1].map(t=>point(curve,a+(b-a)*t));
}
