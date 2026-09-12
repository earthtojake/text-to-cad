import { distanceBetweenPoints, isFinitePoint, measurementFromPicks, normalizeVector3 } from '@hardcore/core/lib/viewer/measurement.js';

const finite = value => value !== null && value !== undefined && value !== '' && Number.isFinite(Number(value)) ? Number(value) : null;
const positive = value => finite(value) > 0 ? Number(value) : null;
const dot = (a,b) => a.reduce((sum,n,i)=>sum+n*b[i],0);
const summary = ref => String(ref.summary || '').match(/^(.*?)\s+(area|length|volume)\s*=\s*([-\d.eE+]+)\s*$/);
const valueOf = (ref,key) => {
  const direct=finite(ref.pickData?.[key]), parsed=summary(ref);
  const value=direct ?? (parsed?.[2]===key ? finite(parsed[3]) : null);
  return value !== null && value >= 0 ? value : null;
};

/** Analytic radii and parameter spans; never infer an arc angle from tessellated length. */
export function referenceMeasurements(ref) {
  const pick=ref.pickData || {}, params=pick.params || {}, type=ref.selectorType;
  const kind=pick.curveType || pick.surfaceType || summary(ref)?.[1] || '';
  const circular=type==='edge' && ['circle','arc'].includes(kind);
  const radius=(circular || (type==='face' && ['cylinder','sphere'].includes(kind))) ? positive(params.radius) : null;
  const span=circular ? positive(params.sweepRadians) : null;
  const sweep=span !== null && span <= 2*Math.PI+1e-8 ? Math.min(span,2*Math.PI) : null;
  const arc=sweep !== null && sweep < 2*Math.PI-1e-8;
  const length=type==='edge' ? (radius !== null && sweep !== null ? radius*sweep : valueOf(ref,'length')) : null;
  const area=type==='face' ? valueOf(ref,'area') : null;
  const rows=[];
  if(radius !== null) rows.push(['Diameter Ø',2*radius,'mm'],['Radius R',radius,'mm']);
  if(length !== null) rows.push([arc ? 'Arc length' : circular && sweep !== null ? 'Circumference' : 'Length',length,'mm']);
  if(arc) rows.push(['Sweep angle',sweep*180/Math.PI,'°']);
  if(area !== null) rows.push(['Area',area,'mm²']);
  if(type==='shape' && valueOf(ref,'volume') !== null) rows.push(['Volume',valueOf(ref,'volume'),'mm³']);
  if(type==='face' && kind==='torus') {
    if(positive(params.majorRadius)) rows.push(['Major radius',Number(params.majorRadius),'mm']);
    if(positive(params.minorRadius)) rows.push(['Tube radius',Number(params.minorRadius),'mm']);
  }
  return {kind:arc ? 'arc' : kind,rows,length,area,radius,circular};
}

function pairRows(a,b) {
  const qa=referenceMeasurements(a), qb=referenceMeasurements(b), pa=a.pickData || {}, pb=b.pickData || {};
  const aa=pa.params || {}, ab=pb.params || {};
  if(qa.circular && qb.circular && isFinitePoint(aa.center) && isFinitePoint(ab.center)) {
    return [['Center distance',distanceBetweenPoints(aa.center,ab.center),'mm']];
  }
  const planes=a.selectorType==='face' && b.selectorType==='face' && qa.kind==='plane' && qb.kind==='plane';
  const lines=a.selectorType==='edge' && b.selectorType==='edge' && qa.kind==='line' && qb.kind==='line';
  const cylinders=a.selectorType==='face' && b.selectorType==='face' && qa.kind==='cylinder' && qb.kind==='cylinder';
  if(!planes && !lines && !cylinders)return [];
  const directionA=normalizeVector3(planes ? pa.normal || aa.axis : lines ? aa.direction : aa.axis);
  const directionB=normalizeVector3(planes ? pb.normal || ab.axis : lines ? ab.direction : ab.axis);
  if(!directionA || !directionB)return [];
  const pointA=isFinitePoint(aa.origin) ? aa.origin : pa.center, pointB=isFinitePoint(ab.origin) ? ab.origin : pb.center;
  const pick=(ref,point,direction)=>({referenceId:ref.id,reference:{...ref,pickData:{...ref.pickData,normal:direction}},point,snapKind:planes ? 'face':'edge',geometry:{kind:'line',direction}});
  const measured=measurementFromPicks(pick(a,pointA,directionA),pick(b,pointB,directionB));
  if(!measured)return [];
  const parallel=Math.abs(dot(directionA,directionB))>1-1e-8;
  if(!parallel)return measured.angleDeg !== null ? [[cylinders ? 'Axis angle':'Angle',measured.angleDeg,'°']] : [];
  const delta=pointB.map((n,i)=>n-pointA[i]), along=dot(delta,directionA);
  // Explicit plane/axis spacing, not a claimed minimum between trimmed surfaces.
  const spacing=planes ? Math.abs(along) : Math.hypot(...delta.map((n,i)=>n-along*directionA[i]));
  return [[planes ? 'Plane spacing' : cylinders ? 'Axis spacing':'Line spacing',spacing,'mm']];
}

export function selectionMeasurements(references) {
  const refs=[...new Map(references.map((ref,i)=>[ref.id || ref.normalizedSelector || i,ref])).values()];
  const rows=[];
  for(const [type,key,label,unit] of [['edge','length','Total length','mm'],['face','area','Total area','mm²']]) {
    const selected=refs.filter(ref=>ref.selectorType===type), values=selected.map(ref=>referenceMeasurements(ref)[key]);
    if(refs.every(ref=>['edge','face'].includes(ref.selectorType)) && selected.length>1 && values.every(value=>value !== null)) rows.push([label,values.reduce((sum,value)=>sum+value,0),unit]);
  }
  if(refs.length===2)rows.push(...pairRows(...refs));
  return rows;
}
