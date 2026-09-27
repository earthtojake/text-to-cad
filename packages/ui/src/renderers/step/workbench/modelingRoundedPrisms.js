import { sub, scale, length, near, unique, inward, faceEdges } from './modelingGeometry.js';

const rounded = v => Math.round(v*1e5)/1e5;
const node = (id,kind,label,faces,extra={}) => ({id,kind,label,faces,edges:[],...extra});

// Discover four-corner profiles through connected planar walls. Radius alone
// must not merge neighboring slots, concentric cavities or unrelated blends.
function profiles(fs, edges) {
  const byId=new Map(fs.map(f=>[f.ord,f])), seen=new Set(), groups=[];
  const adjacent=f=>unique(faceEdges(f).flatMap(id=>edges.get(id)?.faceOrds||[])).filter(id=>byId.has(id));
  for(const seed of fs.filter(f=>f.surfaceType==='cylinder')) {
    if(seen.has(seed.ord))continue;
    const s=seed.surface,axis=s.zdir.findIndex(v=>Math.abs(v)>.999999);
    if(axis<0)continue;
    const group=[],queue=[seed],supports=new Set();seen.add(seed.ord);
    while(queue.length){
      const f=queue.pop();group.push(f);
      const neighbors=adjacent(f).flatMap(id=>{const n=byId.get(id);if(n.surfaceType==='plane' && Math.abs(n.normal[axis])<1e-6){supports.add(id);return adjacent(n);}return [id];});
      for(const id of neighbors){const n=byId.get(id);if(!seen.has(id) && n.surfaceType==='cylinder' && near(n.surface.radius,s.radius) && Math.abs(n.surface.zdir[axis])>.999999 && inward(n)===inward(seed)){seen.add(id);queue.push(n);}}
    }
    const [u,v]=[0,1,2].filter(i=>i!==axis);
    const corners=[...new Set(group.map(f=>[f.surface.origin[u],f.surface.origin[v]].map(rounded).join(',')))].map(p=>p.split(',').map(Number));
    const us=[...new Set(corners.map(p=>p[0]))].sort((a,b)=>a-b),vs=[...new Set(corners.map(p=>p[1]))].sort((a,b)=>a-b);
    if(corners.length!==4 || us.length!==2 || vs.length!==2 || us[1]-us[0]<1e-4 || vs[1]-vs[0]<1e-4)continue;
    const heights=group.flatMap(f=>f.uv.slice(2).map(t=>f.surface.origin[axis]+t*f.surface.zdir[axis]));
    const range=[Math.min(...heights),Math.max(...heights)].map(rounded);
    if(range[1]-range[0]<1e-4)continue;
    const ends=range.map((z,end)=>{
      const blends=fs.filter(f=>f.surfaceType==='torus' && Math.abs(f.surface.zdir[axis])>.999999 && near(f.surface.origin[axis],z) && near(Math.abs(f.surface.majorRadius-s.radius),f.surface.minorRadius) && corners.some(p=>near(p[0],f.surface.origin[u]) && near(p[1],f.surface.origin[v])));
      if(blends.length!==4 || blends.some(f=>!near(f.surface.minorRadius,blends[0].surface.minorRadius)))return null;
      const radius=blends[0].surface.minorRadius,flare=blends[0].surface.majorRadius>s.radius;
      range[end]=rounded(z+(end===0?-radius:radius));
      return {radius,flare,faces:blends.map(f=>f.ord)};
    });
    groups.push({axis,u,v,us,vs,radius:s.radius,range,ends,inward:inward(seed),faces:unique([...group.map(f=>f.ord),...supports,...ends.flatMap(e=>e?.faces||[])])});
  }
  return groups;
}

function boundary(g,position){
  const {axis,u,v,us:[x,X],vs:[y,Y],radius:r}=g;
  const at=(a,b,h)=>{const p=[0,0,0];p[u]=a;p[v]=b;p[axis]=h;return p;};
  const centers=[[X,Y],[x,Y],[x,y],[X,y]],edges=[];
  for(const [i,[a,b]] of centers.entries()){
    const start=i*Math.PI/2,end=start+Math.PI/2;
    edges.push({reversed:false,curve:{kind:'circle',origin:at(a,b,position),xdir:at(1,0,0),ydir:at(0,1,0),radius:r,range:[start,end]}});
    const [c,d]=centers[(i+1)%4],p=at(a+r*Math.cos(end),b+r*Math.sin(end),position),q=at(c+r*Math.cos(end),d+r*Math.sin(end),position),delta=sub(q,p),size=length(delta);
    edges.push({reversed:false,curve:{kind:'line',origin:p,dir:scale(delta,1/size),range:[0,size]}});
  }
  return {kind:'boundary',edges};
}

export function roundedPrismReconstruction(fs,edges){
  if(fs.some(f=>!['plane','cylinder','torus'].includes(f.surfaceType)))return null;
  const groups=profiles(fs,edges),outer=groups.filter(g=>!g.inward),cuts=groups.filter(g=>g.inward);
  if(!outer.length || !cuts.length || groups.length>16)return null;
  const volume=g=>(g.us[1]-g.us[0]+2*g.radius)*(g.vs[1]-g.vs[0]+2*g.radius)*(g.range[1]-g.range[0]);
  outer.sort((a,b)=>volume(b)-volume(a));cuts.sort((a,b)=>volume(b)-volume(a));
  // Side blends that do not form a rectangular profile still belong to its end
  // fillet. Every cylindrical/toric face must be covered before proposing a body.
  const claimed=new Set(groups.flatMap(g=>g.faces));
  const radii=groups.flatMap(g=>g.ends.filter(Boolean).map(e=>e.radius));
  if(fs.some(f=>f.surfaceType==='torus' && !claimed.has(f.ord) || f.surfaceType==='cylinder' && !claimed.has(f.ord) && !radii.some(r=>near(r,f.surface.radius))))return null;
  const steps=[],children=[];let count=0,current=null;
  const push=(kind,label,extra)=>{const id=`rounded-${++count}`;steps.push({id,kind,label,...extra});return id;};
  const fillet=(input,g,end,label)=>{
    const blend=g.ends[end],position=g.range[end],bounds=[0,0,0,0,0,0];
    bounds[g.u]=g.us[0]-g.radius;bounds[g.u+3]=g.us[1]+g.radius;bounds[g.v]=g.vs[0]-g.radius;bounds[g.v+3]=g.vs[1]+g.radius;bounds[g.axis]=bounds[g.axis+3]=position;
    return push('fillet',label,{input,dependsOn:[input],radius:blend.radius,edges:{axis:g.axis,position,bounds,count:8},measurements:[['Radius',blend.radius,'mm']]});
  };
  for(const [i,g] of [...outer,...cuts].entries()){
    const cutting=g.inward,first=i===0,label=first?'Base extrude':cutting?`Cut extrude ${i-outer.length+1}`:`Boss extrude ${i}`;
    const lo=g.range[0]-(cutting && (!g.ends[0] || g.ends[0].flare) ? 0.1 : 0),hi=g.range[1]+(cutting && (!g.ends[1] || g.ends[1].flare) ? 0.1 : 0);
    const sk=push('sketch',`${label} profile`,{dependsOn:[],profile:boundary(g,lo)}),direction=[0,0,0];direction[g.axis]=hi-lo;
    let tool=push('extrude',cutting?'Cut tool':label,{sketch:sk,dependsOn:[sk],direction,measurements:[['Depth',hi-lo,'mm']]});
    const profile=node(sk,'profile','Rounded rectangle',g.faces,{measurements:[['Corner radius',g.radius,'mm']]});
    const feature=node(tool,first||!cutting?'extrude':'cut',label,g.faces,{measurements:[['Depth',g.range[1]-g.range[0],'mm']],children:[profile]});
    for(const end of [0,1])if(g.ends[end] && !g.ends[end].flare){
      tool=fillet(tool,g,end,cutting?'Cut tool fillet':'Fillet');
      const item=node(tool,'round','Fillet',g.ends[end].faces,{measurements:[['Radius',g.ends[end].radius,'mm']]});
      if(first)children.push(item);else feature.children.push(item);
    }
    current=first?tool:push(cutting?'cut':'add',label,{input:current,tool,dependsOn:[current,tool],measurements:feature.measurements});
    if(first)children.unshift(feature);else children.push({...feature,id:current});
    for(const end of [0,1])if(g.ends[end]?.flare){
      if(!cutting)return null;
      current=fillet(current,g,end,'Opening fillet');
      children.push(node(current,'round','Opening fillet',g.ends[end].faces,{measurements:[['Radius',g.ends[end].radius,'mm']]}));
    }
  }
  return steps.length<=128?{recipe:{schema:1,units:'mm',steps,output:current},children}:null;
}
