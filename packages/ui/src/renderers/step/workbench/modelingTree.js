import { sub, dot, cross, length, near, parallel, unique, inward, faceEdges, centroid, translatedContours, contourArea } from './modelingGeometry.js';

import { boundaryProfile as profile } from './modelingProfiles.js';
import { localPrismaticFeatures } from './modelingLocalFeatures.js';
import { boreFeatures } from './modelingBores.js';
import { solidReconstruction } from './modelingSolidRecipes.js';

function sweepPairs(index, faces, edges) {
  const groups = new Map();
  for (const face of index.faces) {
    if (face.surfaceType !== 'plane' || !face.normal) continue;
    for (const loop of face.loops || []) {
      const boundary = unique(loop.map(e => e.edgeOrd)).map(id => edges.get(id));
      if (!boundary.length || boundary.some(e => !e || e.faceOrds?.length !== 2)) continue;
      const walls = unique(boundary.flatMap(e => e.faceOrds).filter(id => id !== face.ord));
      if (!walls.length || walls.some(id => faces.get(id)?.shape !== face.shape)) continue;
      const key = walls.join(',');
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push({ face, loop, boundary, walls });
    }
  }
  const pairs = [];
  for (const ends of groups.values()) {
    if (ends.length !== 2) continue;
    const [a,b] = ends, axis = a.face.normal, delta = sub(centroid(b.boundary),centroid(a.boundary));
    const depth = length(delta);
    if (dot(axis,b.face.normal) > -0.999999 || depth < 1e-4 || Math.abs(dot(delta,axis))/depth < 0.999999 || !translatedContours(a.boundary,b.boundary,delta)) continue;
    const walls = a.walls.map(id => faces.get(id)), allowed = new Set([...a.walls,a.face.ord,b.face.ord]);
    if (walls.some(f => !f.loops?.length || faceEdges(f).some(id => edges.get(id)?.faceOrds?.some(neighbor => !allowed.has(neighbor))))) continue;
    if (!walls.every(f => f.surfaceType === 'cylinder' ? parallel(f.params?.axis,axis) : f.surfaceType === 'plane' && Math.abs(dot(f.normal,axis)) < 1e-6)) continue;
    const sweptArea = a.boundary.reduce((sum,e) => sum+e.length,0)*depth;
    if (Math.abs(walls.reduce((sum,f) => sum+f.area,0)-sweptArea) > Math.max(1e-4,sweptArea*1e-6)) continue;
    pairs.push({ a,b,walls,depth,axis });
  }
  return pairs;
}

function extrudeTree(shape, shapeFaces, pairs, edges) {
  for (const pair of pairs) {
    const {a,b,depth} = pair;
    if (a.face.shape !== shape.ord) continue;
    const caps = pairs.filter(p => p.a.face.ord === a.face.ord && p.b.face.ord === b.face.ord);
    if (caps.length !== a.face.loops.length || caps.length !== b.face.loops.length) continue;
    const covered = unique([a.face.ord,b.face.ord,...caps.flatMap(p => p.a.walls)]);
    if (covered.length !== shapeFaces.length || !near(a.face.area,b.face.area)) continue;
    const volume = a.face.area*depth;
    if (!Number.isFinite(shape.volume) || Math.abs(shape.volume-volume) > Math.max(1e-4,volume*1e-6)) continue;
    const contours = caps.map(p => ({...p,area:contourArea(p.a.loop,edges,a.face.normal)})).sort((x,y) => y.area-x.area);
    if (contours.some(p => !Number.isFinite(p.area)) || !near(contours[0].area-contours.slice(1).reduce((sum,p) => sum+p.area,0),a.face.area)) continue;
    const [outer,...holes] = contours;
    const id = `extrude:${shape.ord}`;
    return [{ id, kind:'extrude', label:'Base extrude', faces:unique([a.face.ord,b.face.ord,...outer.a.walls]), edges:[],
      note:'Inferred extrusion: matching end contours, side surfaces and solid volume.',
      measurements:[['Depth',depth,'mm']], reconstruction:{face:a.face.ord,direction:sub(centroid(b.boundary),centroid(a.boundary))}, children:[profile(id,outer.a.loop,edges)] },
    ...holes.map((p,i) => ({ id:`${id}:cut:${i}`, kind:'cut', label:`Cut extrude ${i+1}`, faces:p.a.walls, edges:[],
      note:'Through cut inferred from this solid’s constant cross-section.', measurements:[['Depth',depth,'mm']],
      children:[profile(`${id}:cut:${i}`,p.a.loop,edges)] }))];
  }
  return null;
}

function revolveTree(shape, fs, edges) {
  const first = fs.find(f => f.surfaceType === 'cylinder');
  if (!first) return null;
  const axis = first.surface.zdir, origin = first.surface.origin;
  const radial = p => length(cross(sub(p,origin),axis));
  // Conservative full revolutions only. Split/trimmed surfaces remain imported.
  if (!fs.every(f => {
    if (f.surfaceType === 'plane') return parallel(f.normal,axis) && faceEdges(f).every(id => {
      const e = edges.get(id), c = e?.curve;
      return c?.kind === 'circle' && parallel(c.zdir,axis) && radial(c.origin)<1e-4 && near(e.length,2*Math.PI*c.radius);
    });
    return ['cylinder','cone'].includes(f.surfaceType) && parallel(f.surface.zdir,axis) && radial(f.surface.origin)<1e-4 && near(f.uv[1]-f.uv[0],2*Math.PI);
  })) return null;
  const segments = [];
  for (const f of fs) {
    const points = [];
    for (const eid of faceEdges(f)) {
      const c = edges.get(eid)?.curve;
      if (c?.kind !== 'circle') continue;
      const p = [c.radius,dot(sub(c.origin,origin),axis)];
      if (!points.some(q => near(q[0],p[0]) && near(q[1],p[1]))) points.push(p);
    }
    if (points.length === 1 && f.surfaceType === 'plane') points.push([0,points[0][1]]);
    if (points.length !== 2) return null;
    segments.push({face:f,points});
  }
  const equal = (a,b) => near(a[0],b[0]) && near(a[1],b[1]);
  const remaining = [...segments], ordered = [remaining.shift()];
  while (remaining.length) {
    const end = ordered.at(-1).points[1];
    const i = remaining.findIndex(s => s.points.some(p => equal(end,p)));
    if (i < 0) break;
    const next = remaining.splice(i,1)[0];
    ordered.push({...next,points:equal(end,next.points[0]) ? next.points : [...next.points].reverse()});
  }
  if (remaining.length) return null;
  const start = ordered[0].points[0], end = ordered.at(-1).points[1];
  if (!equal(start,end)) {
    if (!near(start[0],0) || !near(end[0],0)) return null;
    ordered.push({face:null,points:[end,start]});
  }
  const volume = Math.abs(Math.PI*ordered.reduce((sum,{points:[[r0,z0],[r1,z1]]}) => sum+(z1-z0)*(r0*r0+r0*r1+r1*r1)/3,0));
  if (!Number.isFinite(shape.volume) || Math.abs(volume-shape.volume)>Math.max(1e-4,volume*1e-6)) return null;
  const id = `revolve:${shape.ord}`;
  return [{id,kind:'revolve',label:'Base revolve',faces:fs.map(f => f.ord),edges:[],
    note:'Inferred 360° revolution. Its closed axial profile matches the analytic surfaces and solid volume.', measurements:[['Angle',360,'°']],
    reconstruction:{origin,axis,profile:ordered.map(s=>s.points[0])},
    children:[{id:`${id}:profile`,kind:'profile',label:'Axial profile',faces:fs.map(f => f.ord),edges:[],
      note:'Inferred axial section; selecting a segment highlights its swept face.',
      children:ordered.filter(s=>s.face).map(({face:f,points:[a,b]},i) => ({id:`${id}:segment:${f.ord}`,kind:'curve',label:`${f.surfaceType === 'plane' ? 'Radial' : f.surfaceType === 'cone' ? 'Tapered' : 'Axial'} segment ${i+1}`,faces:[f.ord],edges:[],
        measurements:[['Length',Math.hypot(a[0]-b[0],a[1]-b[1]),'mm'],...(f.params?.radius ? [['Radius',f.params.radius,'mm']] : [])]}))}]}];
}

function roundGroups(fs, edges) {
  const candidates = new Map();
  for (const f of fs) {
    const radius = f.surfaceType === 'torus' ? f.params?.minorRadius : f.surfaceType === 'cylinder' && f.uv[1]-f.uv[0] < Math.PI+1e-4 ? f.params?.radius : null;
    const tangent = faceEdges(f).filter(id => edges.get(id)?.class === 'tangent');
    if (radius > 0 && tangent.length >= 2) candidates.set(f.ord,{face:f,radius,tangent});
  }
  const seen = new Set(), result = [];
  for (const seed of candidates.values()) {
    if (seen.has(seed.face.ord)) continue;
    const group = [], queue = [seed]; seen.add(seed.face.ord);
    while (queue.length) {
      const item = queue.pop(); group.push(item.face.ord);
      for (const eid of item.tangent) for (const neighbor of edges.get(eid).faceOrds) {
        const next = candidates.get(neighbor);
        if (next && !seen.has(neighbor) && near(next.radius,seed.radius)) { seen.add(neighbor); queue.push(next); }
      }
    }
    // At least two tangent connections to non-blend support faces.
    const members = new Set(group);
    const supports = new Set(group.flatMap(id => candidates.get(id).tangent.flatMap(eid => edges.get(eid).faceOrds)).filter(id => !members.has(id)));
    if (supports.size < 2 || group.length < 3 || !group.some(id => candidates.get(id).face.surfaceType === 'torus')) continue;
    result.push({id:`round:${unique(group).join('-')}`,kind:'round',label:`Fillet candidate ${result.length+1}`,faces:unique(group),edges:[],
      note:'Constant-radius tangent blend. Original fillet operation and order are unknown.', measurements:[['Radius',seed.radius,'mm']]});
  }
  return result;
}

export function buildModelingTree(index, floats) {
  if (!Array.isArray(index?.faces) || !Array.isArray(index?.edges)) throw new Error('Exact surface data is unavailable.');
  if (index.faces.length > 6000 || index.edges.length > 20000) throw new Error('This part exceeds the prototype’s analysis limit.');
  const faces = new Map(index.faces.map(f => [f.ord,f])), edges = new Map(index.edges.map(e => [e.ord,e]));
  const pairs = sweepPairs(index,faces,edges);
  return (index.shapes || []).map(shape => {
    const fs = index.faces.filter(f => f.shape === shape.ord), id = `body:${shape.ord}`;
    if (!fs.length) return null;
    if (shape.kind !== 'solid') return {id,kind:'body',label:`Surface body ${shape.ord}`,faces:fs.map(f=>f.ord),edges:[],children:[],complete:false};
    const full = extrudeTree(shape,fs,pairs,edges) || revolveTree(shape,fs,edges);
    if (full) return {id,kind:'body',label:`Body ${shape.ord}`,faces:fs.map(f=>f.ord),edges:[],complete:true,children:full};
    const reconstructed = solidReconstruction(fs,edges,floats);
    if (reconstructed) return {id,kind:'body',label:`Body ${shape.ord}`,faces:fs.map(f=>f.ord),edges:[],complete:true,...reconstructed};
    // Circular cuts belong to bore recognition, including its material-intrusion
    // checks. Do not reintroduce a rejected bore through the generic cut path.
    const circularRim = boundary => boundary.every(e => e.curve?.kind === 'circle' && near(e.curve.radius,boundary[0].curve.radius) && length(sub(e.curve.origin,boundary[0].curve.origin)) < 1e-4);
    const cuts = pairs.filter(p => !circularRim(p.a.boundary)).filter(p => p.a.face.shape === shape.ord && p.walls.every(f => f.surfaceType === 'cylinder' ? inward(f) : dot(sub(centroid(p.a.boundary),f.center),f.normal)>1e-4))
      .map((p,i) => ({id:`cut:${p.a.walls.join('-')}`,kind:'cut',label:`Cut extrude candidate ${i+1}`,faces:p.a.walls,edges:[],
        note:'Matching planar contours and straight walls suggest a through cut. Overall body reconstruction is incomplete.',
        measurements:[['Wall depth',p.depth,'mm']],children:[profile(`cut:${p.a.walls.join('-')}`,p.a.loop,edges)]}));
    const bores = boreFeatures(fs,faces,edges);
    const boreFaces = new Set(bores.flatMap(n=>n.faces));
    const local = localPrismaticFeatures(fs,faces,edges).filter(n=>!n.faces.some(id=>boreFaces.has(id)));
    const used = new Set([...bores,...local].flatMap(n=>n.faces));
    const otherCuts = cuts.filter(n=>!n.faces.some(id=>used.has(id)));
    const rounds = roundGroups(fs.filter(f=>!used.has(f.ord)),edges);
    const features = [...local,...bores,...otherCuts,...rounds];
    const counts = new Map();
    for(const n of features.filter(n=>['pocket','boss','hole'].includes(n.kind))){const label=n.label;counts.set(label,(counts.get(label)||0)+1);n.label=`${label} ${counts.get(label)}`;}
    const claimed = new Set(features.flatMap(n=>n.faces));
    return {id,kind:'body',label:`Imported body ${shape.ord}`,faces:fs.map(f=>f.ord),edges:[],complete:false,
      children:[...features,{id:`${id}:remaining`,kind:'remainder',label:'Other geometry',faces:fs.filter(f=>!claimed.has(f.ord)).map(f=>f.ord),edges:[],note:'No supported modeling operation has been inferred for these faces.'}].filter(n=>n.faces.length)};
  }).filter(Boolean);
}

// All-or-nothing canonical references, scoped to this exact assembly occurrence.
export function modelingReferenceIds(node, occurrenceId, references) {
  const bySelector = new Map();
  for (const ref of references) {
    if (!['face','edge'].includes(ref.selectorType) || ref.occurrenceId !== occurrenceId) continue;
    bySelector.set(ref.normalizedSelector,bySelector.has(ref.normalizedSelector) ? null : ref.id);
  }
  const ids = [...(node.faces||[]).map(n=>`${occurrenceId}.f${n}`),...(node.edges||[]).map(n=>`${occurrenceId}.e${n}`)].map(key=>bySelector.get(key));
  return ids.length && ids.every(Boolean) ? ids : [];
}
