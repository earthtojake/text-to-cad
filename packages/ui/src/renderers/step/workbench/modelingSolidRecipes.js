import { stockCutReconstruction } from './modelingStockCuts.js';
import { splitShaftReconstruction, transversePrismReconstruction } from './modelingImportedPrisms.js';
import { roundedPrismReconstruction } from './modelingRoundedPrisms.js';
import { add, sub, scale, dot, cross, length, near, parallel, unique, inward, faceEdges } from './modelingGeometry.js';

const node = (id, kind, label, faces, extra = {}) => ({ id, kind, label, faces, edges: [], ...extra });
const polygon = points => ({ kind: 'polygon', points });
const sketch = (id, label, profile) => ({ id, kind: 'sketch', label, dependsOn: [], profile });
const recipe = steps => ({ schema: 1, units: 'mm', steps, output: steps.at(-1).id });

// Six orthogonal support planes plus equal-radius edge/corner blends. Dimensions
// come from the support planes, not an axis-aligned bounding box or a part name.
function roundedBox(fs) {
  const planes = fs.filter(f => f.surfaceType === 'plane'), blends = fs.filter(f => ['cylinder', 'sphere'].includes(f.surfaceType));
  if (planes.length !== 6 || blends.length !== 20 || fs.length !== 26) return null;
  const radius = blends[0].surface.radius;
  if (!(radius > 0) || blends.some(f => !near(f.surface.radius, radius)) || blends.filter(f => f.surfaceType === 'sphere').length !== 8) return null;
  const axes = [];
  for (const f of planes) if (!axes.some(a => parallel(a, f.normal))) axes.push(f.normal);
  if (axes.length !== 3 || Math.abs(dot(axes[0], axes[1])) > 1e-6 || !parallel(cross(axes[0], axes[1]), axes[2])) return null;
  axes[2] = cross(axes[0], axes[1]);
  const bounds = axes.map(axis => planes.filter(f => parallel(axis, f.normal)).map(f => dot(f.surface.origin, axis)).sort((a, b) => a - b));
  if (bounds.some(values => values.length !== 2 || values[1] - values[0] <= 2 * radius)) return null;
  const at = coordinates => coordinates.reduce((p, v, i) => add(p, scale(axes[i], v)), [0, 0, 0]);
  const [[x, X], [y, Y], [z, Z]] = bounds;
  const points = [[x,y,z], [X,y,z], [X,Y,z], [x,Y,z]].map(at);
  const steps = [sketch('profile', 'Rectangle', polygon(points)),
    { id: 'base', kind: 'extrude', label: 'Base extrude', sketch: 'profile', dependsOn: ['profile'], direction: scale(axes[2], Z-z), measurements: [['Depth', Z-z, 'mm']] },
    { id: 'blend', kind: 'fillet', label: 'Fillet', input: 'base', dependsOn: ['base'], edges: 'all', radius, measurements: [['Radius', radius, 'mm']] }];
  return { recipe: recipe(steps), children: [
    node('base', 'extrude', 'Base extrude', planes.map(f => f.ord), { measurements: [['Width', X-x, 'mm'], ['Height', Y-y, 'mm'], ['Depth', Z-z, 'mm']], children: [node('profile', 'profile', 'Rectangle', planes.map(f => f.ord))] }),
    node('blend', 'round', 'Fillet', blends.map(f => f.ord), { measurements: [['Radius', radius, 'mm']] }),
  ] };
}

function convexSection(points, axis) {
  const uniquePoints = [];
  for (const p of points) if (!uniquePoints.some(q => length(sub(p, q)) < 1e-5)) uniquePoints.push(p);
  if (uniquePoints.length < 3 || uniquePoints.length > 64) return null;
  const center = scale(uniquePoints.reduce(add, [0,0,0]), 1/uniquePoints.length), [u,v] = [0,1,2].filter(i => i !== axis);
  uniquePoints.sort((a,b) => Math.atan2(a[v]-center[v],a[u]-center[u])-Math.atan2(b[v]-center[v],b[u]-center[u]));
  // Only convex section candidates. Reject inner points/branches instead of
  // silently taking a convex hull that would erase pockets or other topology.
  for (let i = 0; i < uniquePoints.length; i++) {
    const a = sub(uniquePoints[(i+1)%uniquePoints.length],uniquePoints[i]), b = sub(uniquePoints[(i+2)%uniquePoints.length],uniquePoints[(i+1)%uniquePoints.length]);
    if (a[u]*b[v]-a[v]*b[u] < -1e-6) return null;
  }
  return uniquePoints;
}

function ruledLoft(fs, edges, floats) {
  if (!floats) return null;
  const ruled = fs.filter(f => f.surfaceType === 'bsplinesurface');
  if (!ruled.length || fs.some(f => !['plane','cylinder','bsplinesurface'].includes(f.surfaceType))) return null;
  const patches = [];
  for (const f of ruled) {
    const s = f.surface;
    if (s.kind !== 'nurbs' || s.degU !== 1 || s.degV !== 1 || s.nu !== 2 || s.nv !== 2 || s.weights || s.periodicU || s.periodicV) return null;
    const [offset,count] = s.poles;
    if (count !== 12 || offset+count > floats.length) return null;
    // SURF control points are float32. Decimal snapping proposes a recipe only;
    // the independent double-precision BREP comparison remains the acceptance gate.
    patches.push({ face: f, points: Array.from({length:4},(_,i) => Array.from(floats.slice(offset+3*i,offset+3*i+3), v => Math.round(v*1e5)/1e5)) });
  }
  for (const axis of [0,1,2]) {
    // A section axis must align with one of each bilinear patch's parameters.
    if (!patches.every(({points:p}) => near(p[0][axis],p[2][axis]) && near(p[1][axis],p[3][axis]) && !near(p[0][axis],p[1][axis]) || near(p[0][axis],p[1][axis]) && near(p[2][axis],p[3][axis]) && !near(p[0][axis],p[2][axis]))) continue;
    const points = patches.flatMap(p => p.points), levels = [...new Set(points.map(p => p[axis]))].sort((a,b) => a-b);
    if (levels.length < 2 || levels.length > 32) continue;
    const sections = levels.map(level => convexSection(points.filter(p => near(p[axis], level)),axis));
    if (sections.some(p => !p) || sections.some(p => p.length !== sections[0].length)) continue;
    const steps = sections.map((points,i) => sketch(`section-${i+1}`, `Section ${i+1}`, polygon(points)));
    const profiles = steps.map((s,i) => node(s.id,'profile',s.label,patches.filter(p => p.points.some(v => near(v[axis],levels[i]))).map(p => p.face.ord), { measurements: [['Position',levels[i],'mm']] }));
    steps.push({id:'loft',kind:'loft',label:'Base loft',sketches:steps.map(s=>s.id),dependsOn:steps.map(s=>s.id),measurements:[['Length',levels.at(-1)-levels[0],'mm']]});
    const children = [node('loft','loft','Base loft',fs.filter(f=>f.surfaceType!=='cylinder').map(f=>f.ord),{measurements:steps.at(-1).measurements,children:profiles})];
    const cylinders = fs.filter(f=>f.surfaceType==='cylinder'), covered = new Set();
    let previous='loft';
    // Reconstruct capped cylindrical cut tools from their actual floor plane and
    // radius. Extend outward past the stock; no inferred cut through the center.
    for (const cap of fs.filter(f=>f.surfaceType==='plane')) {
      const adjacent=unique(faceEdges(cap).flatMap(id=>edges.get(id)?.faceOrds||[]));
      const walls=cylinders.filter(f=>adjacent.includes(f.ord) && inward(f) && parallel(f.surface.zdir,cap.normal));
      if (!walls.length) continue;
      const first=walls[0].surface;
      if (walls.some(f=>!near(f.surface.radius,first.radius) || length(cross(sub(f.surface.origin,first.origin),first.zdir))>1e-4)) continue;
      const denominator=dot(first.zdir,cap.normal);
      const origin=add(first.origin,scale(first.zdir,dot(sub(cap.surface.origin,first.origin),cap.normal)/denominator));
      const depth=Math.max(...points.map(p=>dot(sub(p,origin),cap.normal)))+1;
      if (depth<=0) continue;
      const sk=`cut-profile-${children.length}`,id=`cut-${children.length}`;
      steps.push(sketch(sk,`Cut profile ${children.length}`,{kind:'boundary',edges:[{reversed:false,curve:{kind:'circle',origin,xdir:first.xdir,ydir:first.ydir,radius:first.radius,range:[0,2*Math.PI]}}]}));
      steps.push({id,kind:'cut',label:`Cut extrude ${children.length}`,input:previous,sketch:sk,dependsOn:[previous,sk],direction:scale(cap.normal,depth),measurements:[['Radius',first.radius,'mm']]});
      const faces=[cap.ord,...walls.map(f=>f.ord)];
      children.push(node(id,'cut',steps.at(-1).label,faces,{measurements:steps.at(-1).measurements,children:[node(sk,'profile','Circle',faces,{measurements:[['Radius',first.radius,'mm']]})]}));
      walls.forEach(f=>covered.add(f.ord));previous=id;
    }
    if (cylinders.some(f=>!covered.has(f.ord)) || steps.length>128) continue;
    const cutFaces=new Set(children.slice(1).flatMap(n=>n.faces));
    children[0].faces=children[0].faces.filter(id=>!cutFaces.has(id));
    return { recipe:recipe(steps), children };
  }
  return null;
}

export function solidReconstruction(fs, edges, floats) {
  return roundedBox(fs) || ruledLoft(fs, edges, floats) || roundedPrismReconstruction(fs, edges) || splitShaftReconstruction(fs, edges) || transversePrismReconstruction(fs, edges) || stockCutReconstruction(fs, edges);
}
