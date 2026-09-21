import { add, sub, scale, dot, length, parallel, near, inward, faceEdges, contourArea } from './modelingGeometry.js';
import { localPrismaticFeatures } from './modelingLocalFeatures.js';

// A planar back face can define stock; recessed parallel faces define outward
// cuts. Local bosses and tangent corner blends finish the candidate. Exact
// replay must still match the original solid before any playback is offered.
export function stockCutReconstruction(fs, edges) {
  if (fs.some(f => !['plane', 'cylinder'].includes(f.surfaceType) || !f.surface?.origin)) return null;
  const faces = new Map(fs.map(f => [f.ord, f]));
  const planes = fs.filter(f => f.surfaceType === 'plane');
  const local = localPrismaticFeatures(fs, faces, edges).filter(f => f.kind === 'boss');
  const loops = f => (f.loops || []).map(loop => ({ loop, area: contourArea(loop, edges, f.normal) })).filter(l => Number.isFinite(l.area)).sort((a, b) => b.area - a.area);
  const profile = (id, label, loop) => ({ id, kind: 'sketch', label, dependsOn: [], profile: { kind: 'boundary', edges: loop.map(u => ({ reversed: u.reversed, curve: edges.get(u.edgeOrd).curve })) } });
  const node = (id, kind, label, faceIds, measurements = []) => ({ id, kind, label, faces: faceIds, edges: [], measurements });
  for (const cap of [...planes].sort((a, b) => b.area - a.area)) {
    if (cap.loops?.length !== 1) continue;
    const axis = scale(cap.normal, -1), aligned = planes.filter(f => parallel(f.normal, axis));
    const level = f => dot(sub(f.surface.origin, cap.surface.origin), axis);
    const depth = Math.max(...aligned.map(level));
    if (depth < 1e-4 || aligned.some(f => level(f) < -1e-4)) continue;
    const floors = aligned.filter(f => dot(f.normal, axis) > .999999 && level(f) > 1e-4 && level(f) < depth - 1e-4).sort((a, b) => level(b) - level(a));
    if (!floors.length || !local.length) continue;
    const outline = loops(cap)[0];
    if (!outline) continue;
    const steps = [profile('stock-profile', 'Stock profile', outline.loop), { id: 'stock', kind: 'extrude', label: 'Base extrude', sketch: 'stock-profile', dependsOn: ['stock-profile'], direction: scale(axis, depth) }];
    const children = [{ ...node('stock', 'extrude', 'Base extrude', [cap.ord], [['Depth', depth, 'mm']]), children: [node('stock-profile', 'profile', 'Stock profile', [cap.ord])] }];
    let previous = 'stock';
    for (const [i, floor] of floors.entries()) {
      const outline = loops(floor)[0]; if (!outline) return null;
      const sk = `recess-profile-${i}`, id = `recess-${i}`, distance = depth - level(floor);
      steps.push(profile(sk, `Recess profile ${i + 1}`, outline.loop), { id, kind: 'cut', label: `Cut extrude ${i + 1}`, input: previous, sketch: sk, dependsOn: [previous, sk], direction: scale(axis, distance) });
      const ids = [...new Set([floor.ord, ...outline.loop.flatMap(u => edges.get(u.edgeOrd).faceOrds)])];
      children.push({ ...node(id, 'cut', `Cut extrude ${i + 1}`, ids, [['Tool depth', distance, 'mm']]), children: [node(sk, 'profile', `Recess profile ${i + 1}`, [floor.ord])] }); previous = id;
    }
    for (const [i, boss] of local.entries()) {
      const cap = faces.get(boss.reconstruction.capFace), sk = `boss-profile-${i}`, tool = `boss-tool-${i}`, id = `boss-${i}`;
      steps.push(profile(sk, `Boss profile ${i + 1}`, cap.loops[0]), { id: tool, kind: 'extrude', label: `Boss tool ${i + 1}`, sketch: sk, dependsOn: [sk], direction: boss.reconstruction.direction }, { id, kind: 'add', label: `Boss extrude ${i + 1}`, input: previous, tool, dependsOn: [previous, tool] });
      children.push({ ...node(id, 'boss', `Boss extrude ${i + 1}`, boss.faces, boss.measurements), children: [node(sk, 'profile', `Boss profile ${i + 1}`, [cap.ord])] }); previous = id;
    }
    // Quarter-cylinder outside blends have two orthogonal planar tangent supports.
    for (const f of fs.filter(f => f.surfaceType === 'cylinder' && !inward(f) && near(f.uv[1] - f.uv[0], Math.PI / 2))) {
      const supports = [...new Set(faceEdges(f).flatMap(id => edges.get(id).faceOrds))].map(id => faces.get(id)).filter(g => g?.surfaceType === 'plane' && Math.abs(dot(g.normal, f.surface.zdir)) < 1e-6);
      const planar = supports.map(g => ({ face: g, axis: g.normal.findIndex(v => Math.abs(v) > .999999) })).filter(g => g.axis >= 0);
      if (planar.length !== 2 || planar[0].axis === planar[1].axis) return null;
      const axial = [0, 1, 2].find(i => i !== planar[0].axis && i !== planar[1].axis);
      if (Math.abs(f.surface.zdir[axial]) < .999999) return null;
      const ends = faceEdges(f).map(id => edges.get(id).curve).filter(c => c.kind === 'circle').map(c => c.origin[axial]);
      if (ends.length < 2) return null;
      const min = [0, 0, 0], max = [0, 0, 0]; min[axial] = Math.min(...ends); max[axial] = Math.max(...ends);
      for (const { face, axis } of planar) min[axis] = max[axis] = face.surface.origin[axis];
      const id = `blend-${f.ord}`;
      steps.push({ id, kind: 'fillet', label: 'Corner fillet', input: previous, dependsOn: [previous], radius: f.surface.radius, edges: { axis: planar[0].axis, position: min[planar[0].axis], bounds: [...min, ...max], count: 1 } });
      children.push(node(id, 'round', 'Corner fillet', [f.ord], [['Radius', f.surface.radius, 'mm']])); previous = id;
    }
    if (steps.length <= 128) return { recipe: { schema: 1, units: 'mm', steps, output: previous }, children };
  }
  return null;
}
