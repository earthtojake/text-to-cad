// Read-only recognition over the SAME topology/mesh used for picking. No
// source inspection, reconstruction, persistence or mutation of a CAD model.
// Deliberately conservative: constant-radius cylindrical walls, or a straight
// rounded slot with two semicylinders and two tangent planar walls.
const dot = (a, b) => a.reduce((sum, x, i) => sum + x * b[i], 0);
const sub = (a, b) => a.map((x, i) => x - b[i]);
const cross = (a, b) => [a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]];
const unit = a => { const n = Math.hypot(...(a || [])); return a?.length === 3 && n > 1e-10 ? a.map(x => x/n) : null; };
const near = (a, b) => Number.isFinite(a) && Number.isFinite(b) && Math.abs(a-b) <= Math.max(1e-5, Math.abs(b)*0.002);
const parallel = (a, b) => a && b && Math.abs(dot(a,b)) > 0.99999;
const bodyKey = r => JSON.stringify([r.partId || '', r.occurrenceId || '', r.shapeId || '']);
const radial = (point, origin, axis) => { const delta = sub(point,origin); const along = dot(delta,axis); return delta.map((x,i) => x-along*axis[i]); };

// Winding distinguishes the inside of a hole from the outside of a boss.
// Curved face average normals can vanish; sample oriented proxy triangles.
export function hasInwardCylinderWinding(data, positions, indices) {
  const { origin, axis: rawAxis } = data.params || {};
  const axis = unit(rawAxis);
  if (!axis || origin?.length !== 3 || !positions || !indices || data.triangleCount < 2) return false;
  const count = Math.min(12, data.triangleCount);
  let samples = 0;
  for (let k = 0; k < count; k++) {
    const triangle = data.triangleStart + Math.floor(k*data.triangleCount/count);
    const vertices = [0,1,2].map(j => {
      const i = indices[triangle*3+j]*3;
      return [positions[i],positions[i+1],positions[i+2]];
    });
    const normal = unit(cross(sub(vertices[1],vertices[0]),sub(vertices[2],vertices[0])));
    const center = [0,1,2].map(i => vertices.reduce((s,v) => s+v[i],0)/3);
    const outward = unit(radial(center,origin,axis));
    if (!normal || !outward) continue;
    if (dot(normal,outward) > -0.9) return false;
    samples++;
  }
  return samples >= 2;
}

function classify(walls, runtime, edgesBySelector) {
  const cylinders = walls.filter(r => r.pickData.surfaceType === 'cylinder');
  const planes = walls.filter(r => r.pickData.surfaceType === 'plane');
  if (!cylinders.length || cylinders.length+planes.length !== walls.length) return null;
  if (!cylinders.every(r => r.pickData.inwardCylinder === true || (
    r.pickData.inwardCylinder == null && hasInwardCylinderWinding(
      r.pickData, runtime.proxy?.facePositions, runtime.proxy?.faceIndices,
    )
  ))) return null;
  const first = cylinders[0].pickData.params;
  const radius = Number(first.radius), axis = unit(first.axis);
  if (!(radius > 0) || !axis || !cylinders.every(r => near(Number(r.pickData.params?.radius),radius) && parallel(unit(r.pickData.params?.axis),axis))) return null;
  // Rim edge centers lie in the end planes even for arcs. This gives depth
  // in the cylinder's axis rather than a world-axis bounding-box estimate.
  const depths = cylinders.map(r => {
    const levels = (r.pickData.adjacentSelectors || []).map(s => edgesBySelector.get(s))
      .filter(e => e?.pickData.curveType === 'circle' && e.pickData.center?.length === 3)
      .map(e => dot(e.pickData.center,axis));
    return levels.length >= 2 ? [Math.min(...levels),Math.max(...levels)] : null;
  });
  if (depths.some(d => !d)) return null;
  const depth = depths[0][1]-depths[0][0];
  if (!(depth > 1e-6) || !depths.every(d => near(d[1]-d[0],depth) && Math.abs(d[0]-depths[0][0]) < Math.max(1e-5,depth*0.002))) return null;
  if (!planes.length) {
    if (!cylinders.every(r => Math.hypot(...radial(r.pickData.params.origin,first.origin,axis)) < 1e-5)) return null;
    if (!near(cylinders.reduce((s,r) => s+r.pickData.area,0),2*Math.PI*radius*depth)) return null;
    return { kind:'hole', dimensions:[{label:'Diameter',value:2*radius},{label:'Wall depth',value:depth}] };
  }
  if (cylinders.length !== 2 || planes.length !== 2 || walls.length !== 4) return null;
  const distance = Math.hypot(...radial(cylinders[1].pickData.params.origin,first.origin,axis));
  if (!(distance > 1e-5) || !cylinders.every(r => near(r.pickData.area,Math.PI*radius*depth))) return null;
  const normals = planes.map(r => unit(r.pickData.normal));
  if (!normals.every(Boolean) || dot(normals[0],normals[1]) > -0.99999) return null;
  for (const [i,plane] of planes.entries()) {
    const origin = plane.pickData.params?.origin;
    if (!origin || Math.abs(dot(normals[i],axis)) > 1e-5 || !near(plane.pickData.area,distance*depth)) return null;
    if (!cylinders.every(r => near(Math.abs(dot(sub(r.pickData.params.origin,origin),normals[i])),radius))) return null;
  }
  return { kind:'slot', dimensions:[{label:'Length',value:distance+2*radius},{label:'Width',value:2*radius},{label:'Wall depth',value:depth}] };
}

/** Recognize one part occurrence; a blank partId is the single-part runtime. */
export function recognizeStepFeatures(runtime, { partId = '', maxFaces = 20000 } = {}) {
  const references = (runtime?.references || []).filter(r => !partId || r.partId === partId || r.occurrenceId === partId);
  const faces = references.filter(r => r.selectorType === 'face');
  if (!faces.length) return { status:'unavailable', groups:[] };
  if (faces.length > maxFaces) return { status:'too-large', groups:[] };
  const bodies = new Map();
  for (const r of references) {
    const key = bodyKey(r);
    if (!bodies.has(key)) bodies.set(key,[]);
    bodies.get(key).push(r);
  }
  const groups = [];
  for (const body of bodies.values()) {
    const faceMap = new Map(body.filter(r => r.selectorType === 'face').map(r => [r.normalizedSelector,r]));
    const edgeMap = new Map(body.filter(r => r.selectorType === 'edge').map(r => [r.normalizedSelector,r]));
    const adjacency = new Map([...faceMap.keys()].map(id => [id,new Set()]));
    for (const edge of edgeMap.values()) {
      const row = runtime.edges?.[edge.rowIndex];
      if (row?.visibilityClass !== 'tangent' && !(Number(row?.flags) & 128)) continue;
      const connected = edge.pickData.adjacentSelectors || [];
      if (connected.length !== 2 || !connected.every(id => faceMap.has(id))) continue;
      adjacency.get(connected[0]).add(connected[1]); adjacency.get(connected[1]).add(connected[0]);
    }
    const visited = new Set();
    for (const [id,face] of faceMap) {
      if (visited.has(id) || face.pickData.surfaceType !== 'cylinder') continue;
      const queue = [id], walls = []; visited.add(id);
      for (let i=0; i<queue.length; i++) {
        const current = queue[i]; walls.push(faceMap.get(current));
        for (const next of adjacency.get(current)) if (!visited.has(next)) { visited.add(next); queue.push(next); }
      }
      const feature = classify(walls,runtime,edgeMap);
      if (!feature) continue;
      const faceIds = walls.map(r => r.id).sort();
      groups.push({ ...feature, id:JSON.stringify(faceIds), faceIds, partId:face.partId || '', occurrenceId:face.occurrenceId || '', shapeId:face.shapeId || '' });
    }
  }
  groups.sort((a,b) => a.kind.localeCompare(b.kind) || a.id.localeCompare(b.id,undefined,{numeric:true}));
  const counts = {};
  return { status:'ready', groups:groups.map(group => ({...group,label:`${group.kind === 'slot' ? 'Slot' : 'Hole'} ${counts[group.kind] = (counts[group.kind] || 0)+1}`})) };
}
