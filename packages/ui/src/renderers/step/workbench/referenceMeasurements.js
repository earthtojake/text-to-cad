const finite = value => value !== null && value !== undefined && value !== '' && Number.isFinite(Number(value)) ? Number(value) : null;
const positive = value => finite(value) > 0 ? Number(value) : null;
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
