import { sub, dot, length, parallel, unique, inward, faceEdges, centroid, translatedContours, contourArea } from './modelingGeometry.js';
import { boundaryProfile } from './modelingProfiles.js';

// A closed cap and its lateral walls are enough to identify a local prism.
// Its surrounding part need not be prismatic, nor one uninterrupted support face.
export function localPrismaticFeatures(fs, faces, edges) {
  const features = [];
  for (const cap of fs) {
    if (cap.surfaceType !== 'plane' || !cap.normal || cap.loops?.length !== 1) continue;
    const loop = cap.loops[0], boundaryIds = unique(loop.map(e=>e.edgeOrd));
    const boundary = boundaryIds.map(id=>edges.get(id));
    if (!boundary.length || boundary.some(e=>!e || e.faceOrds?.length!==2)) continue;
    const wallIds = unique(boundary.flatMap(e=>e.faceOrds).filter(id=>id!==cap.ord));
    const walls = wallIds.map(id=>faces.get(id));
    if (!walls.length || walls.some(f=>!f || f.shape!==cap.shape)) continue;
    const axis = cap.normal;
    if (!walls.every(f=>f.surfaceType==='cylinder' ? parallel(f.params?.axis,axis) : f.surfaceType==='plane' && Math.abs(dot(f.normal,axis))<1e-6)) continue;
    const wallSet = new Set(wallIds), capEdges = new Set(boundaryIds);
    const rim = unique(walls.flatMap(faceEdges)).filter(id=>!capEdges.has(id)).map(id=>edges.get(id))
      .filter(e=>e?.faceOrds?.some(id=>!wallSet.has(id)));
    if (!rim.length || rim.some(e=>e.faceOrds.length!==2)) continue;
    const center = centroid(boundary), delta = sub(centroid(rim),center), depth=length(delta), signedDepth=dot(delta,axis);
    if (depth<1e-4 || Math.abs(signedDepth)/depth<0.999999 || !translatedContours(boundary,rim,delta)) continue;
    const sideArea = boundary.reduce((sum,e)=>sum+e.length,0)*depth;
    if (Math.abs(walls.reduce((sum,f)=>sum+f.area,0)-sideArea)>Math.max(1e-4,sideArea*1e-6)) continue;
    const area = contourArea(loop,edges,axis);
    if (!Number.isFinite(area) || Math.abs(area-cap.area)>Math.max(1e-4,area*1e-6)) continue;
    const pocket = signedDepth>0;
    // Convex analytic profiles only for now. Do not guess inwardness from the
    // bounding box, or confuse an outside boss with a cylindrical bore.
    if (!walls.every(f=>f.surfaceType==='cylinder' ? inward(f)===pocket : (dot(sub(center,f.center),f.normal)>1e-4)===pocket && Math.abs(dot(sub(center,f.center),f.normal))>1e-4)) continue;
    const id = `${pocket ? 'pocket' : 'boss'}:${cap.ord}:${wallIds.join('-')}`;
    features.push({id,kind:pocket?'pocket':'boss',label:pocket?'Pocket':'Boss extrude',faces:unique([cap.ord,...wallIds]),edges:[],
      note:pocket?'Closed pocket inferred from its floor, boundary and straight walls. Original operation order is unknown.':'Local extrusion inferred from its end profile and straight walls. Original operation order is unknown.',
      measurements:[['Depth',depth,'mm'],['Profile area',area,'mm²']],
      reconstruction:{kind:pocket?'pocket':'boss',capFace:cap.ord,direction:delta,expectedVolume:area*depth},
      children:[boundaryProfile(id,loop,edges)]});
  }
  // Prefer the most descriptive region when opposite faces propose the same prism.
  const seen = new Set();
  return features.filter(f=>{const key=f.faces.join(',');if(seen.has(key))return false;seen.add(key);return true;});
}
