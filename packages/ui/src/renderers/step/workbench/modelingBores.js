import { sub, dot, cross, length, near, parallel, unique, inward, faceEdges, curveSamplePoints } from './modelingGeometry.js';
import { boundaryProfile } from './modelingProfiles.js';

const sameAxis = (a,b) => parallel(a.axis,b.axis) && length(cross(sub(a.origin,b.origin),a.axis))<1e-4;
const circleAtAxis = (edge,axis) => edge?.curve?.kind==='circle' && parallel(edge.curve.zdir,axis.axis) && length(cross(sub(edge.curve.origin,axis.origin),axis.axis))<1e-4;
const closeArea = (a,b) => Math.abs(a-b)<Math.max(1e-4,Math.abs(b)*1e-6);

// A cylindrical wall can surround a central post or other material. A complete
// circular rim alone is not evidence of an empty bore. Reject intruding boundary
// points and fully enclosed face bounds; this is conservative, not a mesh fit.
function hasIntrusion(fs,edges,segment) {
  const {axis,radius,depth,ends}=segment, origin=ends[0].edges[0].curve.origin;
  const inside=p=>{const d=sub(p,origin),z=dot(d,axis.axis);return z>1e-4 && z<depth-1e-4 && dot(d,d)-z*z<(radius-1e-4)**2;};
  const members=new Set(segment.faces), shape=fs.find(f=>members.has(f.ord)).shape;
  const other=fs.filter(f=>f.shape===shape && !members.has(f.ord));
  for(const eid of unique(other.flatMap(faceEdges)))if(curveSamplePoints(edges.get(eid)?.curve).some(inside))return true;
  return other.some(f=>f.bbox && [0,1,2,3,4,5,6,7].every(bits=>inside([f.bbox[bits&1?3:0],f.bbox[bits&2?4:1],f.bbox[bits&4?5:2]])));
}

// Merge adjacent patches of the SAME cylinder before interpreting a bore. STEP
// exporters often split one wall into two half-cylinders at a seam.
function cylindricalSegments(fs,faces,edges) {
  const available=new Map(fs.filter(f=>f.surfaceType==='cylinder' && inward(f)).map(f=>[f.ord,f]));
  const seen=new Set(),segments=[];
  for(const seed of available.values()) {
    if(seen.has(seed.ord))continue;
    const axis=seed.params,group=[],queue=[seed];seen.add(seed.ord);
    while(queue.length){const f=queue.pop();group.push(f);
      for(const eid of faceEdges(f))for(const id of edges.get(eid)?.faceOrds||[]){const next=available.get(id);
        if(next && !seen.has(id) && next.shape===seed.shape && near(next.params.radius,axis.radius) && sameAxis(next.params,axis)){seen.add(id);queue.push(next);}
      }
    }
    const members=new Set(group.map(f=>f.ord));
    const rim=unique(group.flatMap(faceEdges)).map(id=>edges.get(id)).filter(e=>e?.faceOrds?.some(id=>!members.has(id)));
    if(!rim.length || rim.some(e=>e.faceOrds.length!==2 || !circleAtAxis(e,axis) || !near(e.curve.radius,axis.radius)))continue;
    const ends=[];
    for(const e of rim){const z=dot(sub(e.curve.origin,axis.origin),axis.axis);let end=ends.find(end=>near(end.z,z));if(!end){end={z,edges:[]};ends.push(end);}end.edges.push(e);}
    if(ends.length!==2 || ends.some(end=>!closeArea(end.edges.reduce((s,e)=>s+e.length,0),2*Math.PI*axis.radius)))continue;
    ends.sort((a,b)=>a.z-b.z);const depth=ends[1].z-ends[0].z;
    if(depth<1e-4 || !closeArea(group.reduce((sum,f)=>sum+f.area,0),2*Math.PI*axis.radius*depth))continue;
    const segment={faces:unique(group.map(f=>f.ord)),axis,radius:axis.radius,depth,ends};
    if(!hasIntrusion(fs,edges,segment))segments.push(segment);
  }
  return segments;
}

// Annular planar shoulders and full conical walls can connect bore stages.
// Reject support planes spanning other holes, incomplete rims and exterior cones.
function connector(face,axis,edges) {
  if(face.surfaceType==='plane') {if(!parallel(face.normal,axis.axis))return null;}
  else if(face.surfaceType==='cone') {if(!inward(face) || !sameAxis({origin:face.surface.origin,axis:face.surface.zdir},axis) || !near(face.uv[1]-face.uv[0],2*Math.PI))return null;}
  else return null;
  const boundary=faceEdges(face).map(id=>edges.get(id)).filter(e=>e?.length>1e-6 && e.faceOrds?.some(id=>id!==face.ord));
  if(!boundary.length || boundary.some(e=>!circleAtAxis(e,axis)))return null;
  const rings=[];
  for(const e of boundary){const r=e.curve.radius,z=dot(sub(e.curve.origin,axis.origin),axis.axis);let ring=rings.find(x=>near(x.r,r)&&near(x.z,z));if(!ring){ring={r,z,edges:[]};rings.push(ring);}ring.edges.push(e);}
  if(rings.length<1 || rings.length>2 || rings.some(r=>!closeArea(r.edges.reduce((s,e)=>s+e.length,0),2*Math.PI*r.r)))return null;
  if(face.surfaceType==='plane' && !closeArea(face.area,Math.PI*Math.abs(rings[0].r**2-(rings[1]?.r||0)**2)))return null;
  return {face,rings,cap:rings.length===1};
}

export function boreFeatures(fs,faces,edges) {
  const segments=cylindricalSegments(fs,faces,edges), byFace=new Map();
  segments.forEach((s,i)=>s.faces.forEach(id=>byFace.set(id,i)));
  const seen=new Set(),result=[];
  for(let seedIndex=0;seedIndex<segments.length;seedIndex++) {
    if(seen.has(seedIndex))continue;
    const seed=segments[seedIndex],axis=seed.axis,stageIds=new Set([seedIndex]),links=new Map(),queue=[seedIndex];seen.add(seedIndex);
    while(queue.length){const i=queue.pop(),stage=segments[i];
      for(const end of stage.ends)for(const edge of end.edges)for(const id of edge.faceOrds){
        if(stage.faces.includes(id)||links.has(id))continue;
        const face=faces.get(id);if(!face || face.shape!==faces.get(seed.faces[0]).shape)continue;
        const link=connector(face,axis,edges);if(!link)continue;
        // Every non-cap ring must be attached to a recognized cylindrical stage,
        // or be the outer rim of a conical countersink.
        const adjacent=unique(faceEdges(face).flatMap(eid=>edges.get(eid)?.faceOrds||[]).map(fid=>byFace.get(fid)).filter(n=>n!==undefined));
        if(face.surfaceType==='plane' && !link.cap && adjacent.length!==2)continue;
        if(adjacent.some(j=>!sameAxis(segments[j].axis,axis)))continue;
        links.set(id,link);
        for(const j of adjacent)if(!stageIds.has(j)&&!seen.has(j)){stageIds.add(j);seen.add(j);queue.push(j);}
      }
    }
    const stages=[...stageIds].map(i=>segments[i]),linked=[...links.values()];
    const allFaces=unique([...stages.flatMap(s=>s.faces),...linked.map(l=>l.face.ord)]);
    const caps=linked.filter(l=>l.cap),hasShoulder=linked.some(l=>l.face.surfaceType==='plane'&&!l.cap),hasCone=linked.some(l=>l.face.surfaceType==='cone'&&!l.cap);
    const label=hasShoulder?'Counterbore':hasCone?'Countersunk bore':caps.length?'Blind bore':'Bore';
    const id=`bore:${allFaces.join('-')}`;
    const zs=stages.flatMap(s=>s.ends.map(e=>dot(sub(e.edges[0].curve.origin,axis.origin),axis.axis)));
    linked.forEach(l=>l.rings.forEach(r=>zs.push(r.z)));
    const outer=stages.toSorted((a,b)=>b.radius-a.radius)[0],depth=Math.max(...zs)-Math.min(...zs);
    const rim=outer.ends[0].edges.map(e=>({edgeOrd:e.ord,reversed:false}));
    result.push({id,kind:'hole',label,faces:allFaces,edges:[],
      note:'Bore geometry inferred from coaxial walls and complete circular boundaries. Dimensions describe the surviving geometry.',
      measurements:[['Diameter',2*outer.radius,'mm'],['Axial span',depth,'mm']],
      reconstruction:{kind:'bore',segments:stages.map(s=>({faces:s.faces,radius:s.radius,origin:s.ends[0].edges[0].curve.origin,axis:s.axis.axis,depth:s.depth}))},
      children:[boundaryProfile(id,rim,edges),...stages.map((s,i)=>({id:`${id}:stage:${i}`,kind:'hole',label:`Bore stage ${i+1}`,faces:s.faces,edges:[],measurements:[['Diameter',2*s.radius,'mm'],['Depth',s.depth,'mm']]}))]});
  }
  return result;
}
