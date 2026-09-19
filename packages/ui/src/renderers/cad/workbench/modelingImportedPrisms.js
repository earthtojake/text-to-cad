import { add, sub, scale, dot, cross, length, parallel, near, inward, faceEdges, centroid, translatedContours } from './modelingGeometry.js';
const feature = (id, kind, label, fs, measurements = []) => ({ id, kind, label, faces: fs.map(f => f.ord), edges: [], measurements });
const recipe = steps => ({ schema: 1, units: 'mm', steps, output: steps.at(-1).id });

// Imported exporters often split one full cylinder into two semicylindrical faces.
// Group by actual axis, radius and axial interval rather than counting faces.
function cylinderGroups(fs, edges) {
  const groups = [];
  for (const f of fs.filter(f => f.surfaceType === 'cylinder')) {
    const s = f.surface, axis = s.zdir;
    const points = faceEdges(f).flatMap(id => {
      const e = edges.get(id), c = e?.curve;
      return c?.kind === 'circle' ? [c.origin] : c?.kind === 'line' ? c.range.map(t => add(c.origin, scale(c.dir, t))) : [];
    });
    if (!points.length) return null;
    const values = points.map(p => dot(p, axis)), z = [Math.min(...values), Math.max(...values)];
    let group = groups.find(g => dot(g.axis, axis) > .999999 && near(g.radius, s.radius) && length(cross(sub(g.origin, s.origin), axis)) < 1e-4 && z.every((v, i) => near(v, g.z[i])) && g.inward === inward(f));
    if (!group) { group = { axis, origin: s.origin, radius: s.radius, z, inward: inward(f), faces: [], angle: 0, surface: s }; groups.push(group); }
    group.faces.push(f); group.angle += f.uv[1] - f.uv[0];
  }
  return groups.every(g => near(g.angle, 2 * Math.PI)) ? groups : null;
}

export function splitShaftReconstruction(fs, edges) {
  if (fs.some(f => !['plane', 'cylinder'].includes(f.surfaceType))) return null;
  const groups = cylinderGroups(fs, edges);
  if (!groups?.length || groups.some(g => g.inward)) return null;
  const { axis, origin } = groups[0];
  if (groups.some(g => !parallel(g.axis, axis) || length(cross(sub(g.origin, origin), axis)) > 1e-4) || fs.some(f => f.surfaceType === 'plane' && !parallel(f.normal, axis))) return null;
  // Disjoint, adjoining coaxial cylinders define a stepped solid shaft.
  const sorted = groups.map(g => ({ ...g, z: g.z.map(v => v - dot(origin, axis)) })).sort((a, b) => a.z[0] - b.z[0]);
  if (sorted.some((g, i) => i && !near(g.z[0], sorted[i - 1].z[1]))) return null;
  const profile = [[0, sorted[0].z[0]], ...sorted.flatMap(g => [[g.radius, g.z[0]], [g.radius, g.z[1]]]), [0, sorted.at(-1).z[1]]];
  const steps = [{ id: 'shaft-profile', kind: 'sketch', label: 'Axial profile', dependsOn: [], profile: { kind: 'axial', axis, origin, profile } },
    { id: 'shaft-revolve', kind: 'revolve', label: 'Base revolve', sketch: 'shaft-profile', dependsOn: ['shaft-profile'], axis, origin, angle: 2 * Math.PI }];
  return { recipe: recipe(steps), children: [{ ...feature('shaft-revolve', 'revolve', 'Base revolve', fs, [['Angle', 360, '°']]), children: [feature('shaft-profile', 'profile', 'Axial profile', fs)] }] };
}

export function transversePrismReconstruction(fs, edges) {
  if (fs.some(f => !['plane', 'cylinder'].includes(f.surfaceType))) return null;
  const groups = cylinderGroups(fs, edges);
  if (!groups?.length || groups.some(g => !g.inward)) return null;
  const planes = fs.filter(f => f.surfaceType === 'plane' && f.loops?.length === 1);
  for (const a of planes) for (const b of planes) {
    if (a.ord >= b.ord || dot(a.normal, b.normal) > -.999999) continue;
    const ae = a.loops[0].map(u => edges.get(u.edgeOrd)), be = b.loops[0].map(u => edges.get(u.edgeOrd));
    const delta = sub(centroid(be), centroid(ae));
    if (dot(delta, a.normal) >= -1e-4 || !parallel(scale(delta, 1 / length(delta)), a.normal) || !translatedContours(ae, be, delta)) continue;
    const steps = [{ id: 'stock-profile', kind: 'sketch', label: 'Base profile', dependsOn: [], profile: { kind: 'boundary', edges: a.loops[0].map(u => ({ reversed: u.reversed, curve: edges.get(u.edgeOrd).curve })) } },
      { id: 'stock', kind: 'extrude', label: 'Base extrude', sketch: 'stock-profile', dependsOn: ['stock-profile'], direction: delta }];
    const children = [{ ...feature('stock', 'extrude', 'Base extrude', fs.filter(f => f.surfaceType === 'plane'), [['Depth', length(delta), 'mm']]), children: [feature('stock-profile', 'profile', 'Base profile', [a, b])] }];
    for (const [i, g] of groups.entries()) {
      const sk = `bore-profile-${i}`, id = `bore-${i}`, previous = steps.at(-1).id, s = g.surface;
      const origin = add(g.origin, scale(g.axis, g.z[0] - dot(g.origin, g.axis)));
      steps.push({ id: sk, kind: 'sketch', label: `Hole profile ${i + 1}`, dependsOn: [], profile: { kind: 'boundary', edges: [{ reversed: false, curve: { kind: 'circle', origin, xdir: s.xdir, ydir: s.ydir, radius: g.radius, range: [0, 2 * Math.PI] } }] } });
      steps.push({ id, kind: 'cut', label: `Hole ${i + 1}`, input: previous, sketch: sk, dependsOn: [previous, sk], direction: scale(g.axis, g.z[1] - g.z[0]) });
      children.push({ ...feature(id, 'hole', `Hole ${i + 1}`, g.faces, [['Diameter', 2 * g.radius, 'mm'], ['Depth', g.z[1] - g.z[0], 'mm']]), children: [feature(sk, 'profile', 'Circle', g.faces)] });
    }
    if (steps.length <= 128) return { recipe: recipe(steps), children };
  }
  return null;
}
