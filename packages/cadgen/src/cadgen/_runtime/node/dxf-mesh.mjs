#!/usr/bin/env node
var pr=Object.defineProperty;var d=(s,t)=>pr(s,"name",{value:t,configurable:!0});import rn from"node:fs";import or from"node:path";function T(s,t=0){let e=Number(s);return Number.isFinite(e)?e:t}d(T,"toFiniteNumber");var mr=new Map([["cut","cut"],["profile","cut"],["bend","bend"],["fold","bend"],["engrave","engrave"],["etch","engrave"],["ref","reference"],["reference","reference"],["note","reference"],["notes","reference"],["annotation","reference"],["construction","reference"],["dim","reference"],["dims","reference"],["dimension","reference"],["dimensions","reference"],["section","reference"],["sections","reference"],["hidden","reference"],["center","reference"],["centre","reference"],["centerline","reference"],["centreline","reference"],["phantom","reference"],["title","reference"],["titleblock","reference"],["border","reference"],["frame","reference"],["viewport","reference"],["hatch","reference"],["text","reference"],["label","reference"],["labels","reference"],["leader","reference"],["axis","reference"]]);function St(s){let t=String(s||"").trim().toLowerCase().split(/[^a-z0-9]+/).filter(Boolean);for(let e of["cut","bend","engrave","reference"])if(t.some(n=>mr.get(n)===e))return e;return"cut"}d(St,"semanticKindForLayer");function lt(s){return String(s||"").trim()||"0"}d(lt,"normalizeLayerName");function Nt(s){let t=s%360;return t<0?t+360:t}d(Nt,"normalizeAngle");function gr(s,t,e){let n=Math.abs(e);return n>=360-1e-9?!0:e>=0?(Nt(s)-Nt(t)+360)%360<=n+1e-9:(Nt(t)-Nt(s)+360)%360<=n+1e-9}d(gr,"angleInSweep");function ae(s,t,e){let n=e*Math.PI/180;return[s[0]+t*Math.cos(n),s[1]+t*Math.sin(n)]}d(ae,"pointOnCircle");function _r(s){let t=s.startAngleDeg+s.sweepAngleDeg,e=[ae(s.center,s.radius,s.startAngleDeg),ae(s.center,s.radius,t)];for(let n of[0,90,180,270])gr(n,s.startAngleDeg,s.sweepAngleDeg)&&e.push(ae(s.center,s.radius,n));return e}d(_r,"arcExtremaPoints");function un(s,t){return s?{minX:Math.min(s.minX,t.minX),minY:Math.min(s.minY,t.minY),maxX:Math.max(s.maxX,t.maxX),maxY:Math.max(s.maxY,t.maxY)}:t}d(un,"expandBounds");function xr(s){return{minX:Math.min(s.start[0],s.end[0]),minY:Math.min(s.start[1],s.end[1]),maxX:Math.max(s.start[0],s.end[0]),maxY:Math.max(s.start[1],s.end[1])}}d(xr,"lineBounds");function yr(s){return{minX:s.center[0]-s.radius,minY:s.center[1]-s.radius,maxX:s.center[0]+s.radius,maxY:s.center[1]+s.radius}}d(yr,"circleBounds");function vr(s){let t=_r(s),e=t.map(i=>i[0]),n=t.map(i=>i[1]);return{minX:Math.min(...e),minY:Math.min(...n),maxX:Math.max(...e),maxY:Math.max(...n)}}d(vr,"arcBounds");function oe(s,{minX:t,maxY:e}){return[s[0]-t,e-s[1]]}d(oe,"screenPoint");function O(s){let t=Math.round(T(s)*1e6)/1e6;return Math.abs(t)<1e-9?0:t}d(O,"formatNumber");function Mr(s){let e=String(s||"").replace(/\r\n?/g,`
`).split(`
`);if(e.length&&e[e.length-1]===""&&e.pop(),e.length%2!==0)throw new Error("DXF group code stream is malformed");let n=[];for(let i=0;i<e.length;i+=2){let r=Number.parseInt(e[i].trim(),10);if(!Number.isFinite(r))throw new Error(`Invalid DXF group code: ${JSON.stringify(e[i])}`);n.push({code:r,value:e[i+1]??""})}return n}d(Mr,"parseRecordPairs");function Sr(s){let t=0;for(let e=0;e<s.length;e+=1){let n=s[e];if(n.code!==9)continue;let i=String(n.value||"").trim(),r=s[e+1];r&&i==="$INSUNITS"&&(t=Math.max(0,Math.trunc(T(r.value,0))))}return{sourceUnits:t,defaultThicknessMm:0}}d(Sr,"parseHeader");var br=new Map([[0,1],[1,25.4],[2,304.8],[4,1],[5,10],[6,1e3],[7,1e6],[8,254e-7],[9,.0254],[10,914.4],[13,.001],[14,100]]);function Er(s){return br.get(Math.trunc(T(s,0)))??1}d(Er,"dxfUnitsScaleMm");var bi=new Map([[1,"#ff3b30"],[2,"#ffd60a"],[3,"#34c759"],[4,"#32ade6"],[5,"#3a5cff"],[6,"#ff2ddf"],[7,"#e5e7eb"],[8,"#8e8e93"],[9,"#c7c7cc"]]);function Ar(s){let t=Math.trunc(T(s,7));if(bi.has(t))return bi.get(t);if(t>=250&&t<=255){let n=Math.round(51+(t-250)*204/5).toString(16).padStart(2,"0");return`#${n}${n}${n}`}return null}d(Ar,"aciColorHex");function Tr(s){let t=new Map,e=0;for(;e<s.length;){let n=s[e];if(n.code!==0||String(n.value||"").trim().toUpperCase()!=="LAYER"){e+=1;continue}e+=1;let i=[];for(;e<s.length&&s[e].code!==0;)i.push(s[e]),e+=1;let r=lt(i.find(a=>a.code===2)?.value),o=Math.trunc(T(i.find(a=>a.code===62)?.value,7));t.set(r,{aci:Math.abs(o),visibleDefault:o>=0})}return t}d(Tr,"parseLayerTable");function wr(s){let t=lt(s.find(o=>o.code===8)?.value),e=T(s.find(o=>o.code===10)?.value),n=T(s.find(o=>o.code===20)?.value),i=T(s.find(o=>o.code===11)?.value),r=T(s.find(o=>o.code===21)?.value);return{layer:t,start:[e,n],end:[i,r]}}d(wr,"parseLineEntity");function Cr(s){let t=lt(s.find(o=>o.code===8)?.value),e=T(s.find(o=>o.code===40)?.value,-1);if(e<=0)throw new Error("Invalid DXF arc radius");let n=Nt(T(s.find(o=>o.code===50)?.value)),r=(Nt(T(s.find(o=>o.code===51)?.value))-n+360)%360;return r<=1e-9&&(r=360),{layer:t,center:[T(s.find(o=>o.code===10)?.value),T(s.find(o=>o.code===20)?.value)],radius:e,startAngleDeg:n,sweepAngleDeg:r}}d(Cr,"parseArcEntity");function Rr(s){let t=lt(s.find(n=>n.code===8)?.value),e=T(s.find(n=>n.code===40)?.value,-1);if(e<=0)throw new Error("Invalid DXF circle radius");return{layer:t,center:[T(s.find(n=>n.code===10)?.value),T(s.find(n=>n.code===20)?.value)],radius:e}}d(Rr,"parseCircleEntity");function Ai(s,t,e,n){let i=e[0]-t[0],r=e[1]-t[1],o=Math.hypot(i,r);if(o<=1e-9||Math.abs(n)<=1e-9)return null;let a=4*Math.atan(n),c=o*(1+n*n)/(4*Math.abs(n)),l=[(t[0]+e[0])/2,(t[1]+e[1])/2],u=[-r/o,i/o],h=o*(1-n*n)/(4*n),f=[l[0]+u[0]*h,l[1]+u[1]*h];return{layer:s,center:f,radius:c,startAngleDeg:Nt(Math.atan2(t[1]-f[1],t[0]-f[0])*180/Math.PI),sweepAngleDeg:a*180/Math.PI}}d(Ai,"arcFromBulgeSegment");function Ir(s){let t=lt(s.find(c=>c.code===8)?.value),e=Math.trunc(T(s.find(c=>c.code===70)?.value,0)),n=[],i=null;for(let c of s){if(c.code===10){i&&Number.isFinite(i.point[0])&&Number.isFinite(i.point[1])&&n.push(i),i={point:[T(c.value),Number.NaN],bulge:0};continue}if(c.code===20&&i){i.point[1]=T(c.value);continue}c.code===42&&i&&(i.bulge=T(c.value))}if(i&&Number.isFinite(i.point[0])&&Number.isFinite(i.point[1])&&n.push(i),n.length<2)throw new Error("Invalid DXF LWPOLYLINE; expected at least 2 vertices");let r=[],o=[],a=d((c,l)=>{let u=c.point,h=l.point;if(!(u[0]===h[0]&&u[1]===h[1])){if(Math.abs(c.bulge)>1e-9){let f=Ai(t,u,h,c.bulge);f&&o.push(f);return}r.push({layer:t,start:u,end:h})}},"addSegment");for(let c=0;c<n.length-1;c+=1)a(n[c],n[c+1]);return(e&1)!==0&&a(n[n.length-1],n[0]),{lines:r,arcs:o}}d(Ir,"parseLwpolylineEntity");var Ce=72;function Re(s,t,{closed:e=!1}={}){let n=[];for(let i=0;i<t.length-1;i+=1){let r=t[i],o=t[i+1];r[0]===o[0]&&r[1]===o[1]||n.push({layer:s,start:r,end:o})}if(e&&t.length>2){let i=t[0],r=t[t.length-1];(i[0]!==r[0]||i[1]!==r[1])&&n.push({layer:s,start:r,end:i})}return n}d(Re,"samplePolylinePoints");function Pr(s){let t=lt(s.find(g=>g.code===8)?.value),e=T(s.find(g=>g.code===10)?.value),n=T(s.find(g=>g.code===20)?.value),i=T(s.find(g=>g.code===11)?.value),r=T(s.find(g=>g.code===21)?.value),o=T(s.find(g=>g.code===40)?.value,1),a=T(s.find(g=>g.code===41)?.value,0),c=T(s.find(g=>g.code===42)?.value,Math.PI*2),l=Math.hypot(i,r);if(!(l>0)||!(o>0))throw new Error("Invalid DXF ellipse axes");let u=Math.atan2(r,i),h=Math.cos(u),f=Math.sin(u),m=l*o,p=c-a,_=Math.abs(Math.abs(p)-Math.PI*2)<1e-6,x=[];for(let g=0;g<=Ce;g+=1){let M=a+p*g/Ce,y=l*Math.cos(M),v=m*Math.sin(M);x.push([e+y*h-v*f,n+y*f+v*h])}return _&&(x[x.length-1]=[...x[0]]),{lines:Re(t,x),arcs:[]}}d(Pr,"parseEllipseEntity");function Lr(s){let t=lt(s.find(x=>x.code===8)?.value),e=Math.trunc(T(s.find(x=>x.code===70)?.value,0)),n=Math.max(1,Math.trunc(T(s.find(x=>x.code===71)?.value,3))),i=s.filter(x=>x.code===40).map(x=>T(x.value)),r=[],o=[],a=null,c=null;for(let x of s)x.code===10?(a&&r.push(a),a=[T(x.value),0]):x.code===20&&a?a[1]=T(x.value):x.code===11?(c&&o.push(c),c=[T(x.value),0]):x.code===21&&c&&(c[1]=T(x.value));a&&r.push(a),c&&o.push(c);let l=(e&1)!==0;if(r.length<=n){let x=r.length>=2?r:o;if(x.length<2)throw new Error("Invalid DXF spline; expected at least 2 points");return{lines:Re(t,x,{closed:l}),arcs:[]}}let u=n+1,h=i.length>=r.length+u?i:Array.from({length:r.length+u},(x,g)=>g<u?0:g>=r.length?r.length-n:g-n),f=d(x=>{let g=n;for(;g<r.length-1&&h[g+1]<=x;)g+=1;let M=[];for(let y=0;y<=n;y+=1){let v=r[g-n+y]||r[r.length-1];M.push([v[0],v[1]])}for(let y=1;y<=n;y+=1)for(let v=n;v>=y;v-=1){let b=g-n+v,A=h[b],z=h[b+u-y]-A,w=z>0?(x-A)/z:0;M[v]=[M[v-1][0]*(1-w)+M[v][0]*w,M[v-1][1]*(1-w)+M[v][1]*w]}return M[n]},"evaluate"),m=h[n],p=h[r.length],_=[];for(let x=0;x<=Ce;x+=1){let g=m+(p-m)*x/Ce;_.push(f(Math.min(g,p)))}return{lines:Re(t,_,{closed:l}),arcs:[]}}d(Lr,"parseSplineEntity");function Nr(s,t){let e=lt(s.find(c=>c.code===8)?.value),n=Math.trunc(T(s.find(c=>c.code===70)?.value,0)),i=t.map(c=>({point:[T(c.find(l=>l.code===10)?.value),T(c.find(l=>l.code===20)?.value)],bulge:T(c.find(l=>l.code===42)?.value,0)})).filter(c=>Number.isFinite(c.point[0])&&Number.isFinite(c.point[1]));if(i.length<2)throw new Error("Invalid DXF POLYLINE; expected at least 2 vertices");let r=[],o=[],a=d((c,l)=>{let u=c.point,h=l.point;if(!(u[0]===h[0]&&u[1]===h[1])){if(Math.abs(c.bulge)>1e-9){let f=Ai(e,u,h,c.bulge);f&&o.push(f);return}r.push({layer:e,start:u,end:h})}},"addSegment");for(let c=0;c<i.length-1;c+=1)a(i[c],i[c+1]);return(n&1)!==0&&a(i[i.length-1],i[0]),{lines:r,arcs:o}}d(Nr,"parsePolylineEntity");var Dr=new Set([75,98]);function Ur(s){let t=lt(s.find(r=>r.code===8)?.value),e=[],n=[],i=d(()=>{n.length>=3&&e.push(...Re(t,n,{closed:!0})),n=[]},"flush");for(let r of s){if(Dr.has(r.code))break;if(r.code===92){i();continue}if(r.code===10){n.push([T(r.value),Number.NaN]);continue}r.code===20&&n.length&&(n[n.length-1][1]=T(r.value))}if(i(),!e.length)throw new Error("Invalid DXF hatch; no boundary path");return{lines:e,arcs:[]}}d(Ur,"parseHatchEntity");var Fr=new Set(["ATTRIB","ATTDEF","LEADER","MLEADER","MULTILEADER","POINT","VIEWPORT","SEQEND","TOLERANCE","OLE2FRAME","WIPEOUT","IMAGE","RAY","XLINE","ACAD_PROXY_ENTITY","ACAD_TABLE","BODY","REGION","SHAPE","SOLID","TRACE","3DFACE","HELIX","MESH","SPLINE_PROXY"]);function Ti(s){let t=String(s??"");return t=t.replace(/\\P/gi,`
`).replace(/\\~/g," "),t=t.replace(/\\[fFhHcCtTqQwWaA][^;]*;/g,""),t=t.replace(/\\S([^^;]*)\^([^;]*);/g,"$1/$2"),t=t.replace(/[{}]/g,""),t=t.replace(/%%d/gi,"\xB0").replace(/%%p/gi,"\xB1").replace(/%%c/gi,"\u2205"),t=t.replace(/%%[uo]/gi,""),t.trim()}d(Ti,"stripMtextFormatting");function Or(s){let t=lt(s.find(n=>n.code===8)?.value),e=String(s.find(n=>n.code===1)?.value??"").trim();return e?{layer:t,position:[T(s.find(n=>n.code===10)?.value),T(s.find(n=>n.code===20)?.value)],heightMm:Math.max(T(s.find(n=>n.code===40)?.value,2.5),.01),rotationDeg:T(s.find(n=>n.code===50)?.value,0),value:e}:null}d(Or,"parseTextEntity");function Br(s){let t=lt(s.find(r=>r.code===8)?.value),e=s.filter(r=>r.code===3).map(r=>String(r.value??"")),n=String(s.find(r=>r.code===1)?.value??""),i=Ti(e.join("")+n);return i?{layer:t,position:[T(s.find(r=>r.code===10)?.value),T(s.find(r=>r.code===20)?.value)],heightMm:Math.max(T(s.find(r=>r.code===40)?.value,2.5),.01),rotationDeg:T(s.find(r=>r.code===50)?.value,0),value:i}:null}d(Br,"parseMtextEntity");function zr(s){let t=lt(s.find(n=>n.code===8)?.value),e=String(s.find(n=>n.code===1)?.value??"").trim();return!e||e==="<>"?null:{layer:t,position:[T(s.find(n=>n.code===11)?.value),T(s.find(n=>n.code===21)?.value)],heightMm:2.5,rotationDeg:T(s.find(n=>n.code===53)?.value,0),value:Ti(e)}}d(zr,"parseDimensionEntity");function Vr(s,t){if(!t)return s;let e=Math.abs(t.sx)||1,n=Math.atan2(t.sin,t.cos)*180/Math.PI;return{...s,position:kt(s.position,t),heightMm:s.heightMm*e,rotationDeg:s.rotationDeg+n}}d(Vr,"transformTextMarking");function kt(s,t){if(!t)return s;let{cos:e,sin:n,sx:i,sy:r,tx:o,ty:a}=t,c=s[0]*i,l=s[1]*r;return[c*e-l*n+o,c*n+l*e+a]}d(kt,"transformPoint");function kr({lines:s,arcs:t,circles:e},n){if(!n)return{lines:s,arcs:t,circles:e};let{cos:i,sin:r,sx:o,sy:a,tx:c,ty:l}=n,u=Math.abs(o),h=Math.atan2(r,i)*180/Math.PI;return{lines:s.map(f=>({...f,start:kt(f.start,n),end:kt(f.end,n)})),arcs:t.map(f=>({...f,center:kt(f.center,n),radius:f.radius*u,startAngleDeg:f.startAngleDeg+h})),circles:(e||[]).map(f=>({...f,center:kt(f.center,n),radius:f.radius*u}))}}d(kr,"transformGeometry");function Gr(s){let t=T(s.find(p=>p.code===10)?.value),e=T(s.find(p=>p.code===20)?.value),n=T(s.find(p=>p.code===41)?.value,1)||1,i=T(s.find(p=>p.code===42)?.value,1)||1,r=T(s.find(p=>p.code===50)?.value,0),o=Math.max(1,Math.trunc(T(s.find(p=>p.code===70)?.value,1))),a=Math.max(1,Math.trunc(T(s.find(p=>p.code===71)?.value,1))),c=T(s.find(p=>p.code===44)?.value,0),l=T(s.find(p=>p.code===45)?.value,0),u=r*Math.PI/180,h=Math.cos(u),f=Math.sin(u),m=[];for(let p=0;p<o;p+=1)for(let _=0;_<a;_+=1)m.push({cos:h,sin:f,sx:n,sy:i,tx:t+p*c,ty:e+_*l});return m}d(Gr,"insertTransforms");function Hr(s,t){if(!s)return t;if(!t)return s;let e=kt([t.tx,t.ty],s),n=s.cos*t.cos-s.sin*t.sin,i=s.sin*t.cos+s.cos*t.sin;return{cos:n,sin:i,sx:s.sx*t.sx,sy:s.sy*t.sy,tx:e[0],ty:e[1]}}d(Hr,"composeTransforms");function wi(s,{blocks:t=new Map,transform:e=null,depth:n=0,apparatus:i=null}={}){let r=[],o=[],a=[],c=[],l=d(f=>{let m=kr({lines:f.lines||[],arcs:f.arcs||[],circles:f.circles||[]},e);r.push(...m.lines),o.push(...m.arcs),a.push(...m.circles)},"push"),u=d(f=>{f&&c.push(Vr(f,e))},"pushText"),h=0;for(;h<s.length;){let f=s[h];if(f.code!==0){h+=1;continue}let m=String(f.value||"").trim().toUpperCase();if(m==="ENDSEC"||m==="ENDBLK")break;let p=[];for(h+=1;h<s.length&&s[h].code!==0;)p.push(s[h]),h+=1;if(i&&(m==="DIMENSION"||m==="ARC_DIMENSION"?i.dimensions+=1:(m==="LEADER"||m==="MLEADER"||m==="MULTILEADER")&&(i.leaders+=1),p.some(_=>_.code===67&&Number(_.value)===1)&&(i.paperspaceEntities+=1)),m==="LINE"){l({lines:[wr(p)]});continue}if(m==="ARC"){l({arcs:[Cr(p)]});continue}if(m==="CIRCLE"){l({circles:[Rr(p)]});continue}if(m==="LWPOLYLINE"){l(Ir(p));continue}if(m==="ELLIPSE"){l(Pr(p));continue}if(m==="SPLINE"){l(Lr(p));continue}if(m==="HATCH"){l(Ur(p));continue}if(m==="TEXT"){u(Or(p));continue}if(m==="MTEXT"){u(Br(p));continue}if(m==="DIMENSION"){u(zr(p));continue}if(m==="POLYLINE"){let _=[];for(;h<s.length;){let x=s[h];if(x.code!==0){h+=1;continue}let g=String(x.value||"").trim().toUpperCase();if(g==="VERTEX"){let M=[];for(h+=1;h<s.length&&s[h].code!==0;)M.push(s[h]),h+=1;_.push(M);continue}if(g==="SEQEND")for(h+=1;h<s.length&&s[h].code!==0;)h+=1;break}l(Nr(p,_));continue}if(m==="INSERT"){if(n>=16)throw new Error("DXF block nesting is too deep");let _=String(p.find(g=>g.code===2)?.value||"").trim(),x=t.get(_.toUpperCase());if(!x)continue;for(let g of Gr(p)){let M=wi(x,{blocks:t,transform:Hr(e,g),depth:n+1});r.push(...M.lines),o.push(...M.arcs),a.push(...M.circles),c.push(...M.texts)}continue}if(!Fr.has(m))throw new Error(`Unsupported DXF entity ${m}`)}return{lines:r,arcs:o,circles:a,texts:c}}d(wi,"parseEntities");function Wr(s){let t=new Map,e=0;for(;e<s.length;){let n=s[e];if(n.code!==0||String(n.value||"").trim().toUpperCase()!=="BLOCK"){e+=1;continue}e+=1;let i=[];for(;e<s.length&&s[e].code!==0;)i.push(s[e]),e+=1;let r=String(i.find(a=>a.code===2)?.value||"").trim(),o=[];for(;e<s.length;){let a=s[e];if(a.code===0&&String(a.value||"").trim().toUpperCase()==="ENDBLK"){e+=1;break}o.push(a),e+=1}r&&t.set(r.toUpperCase(),o)}return t}d(Wr,"parseBlocks");function Xr(s){let t=new Map,e=0;for(;e<s.length;){let n=s[e];if(n.code!==0||String(n.value||"").trim().toUpperCase()!=="SECTION"){e+=1;continue}let i=s[e+1],r=String(i?.value||"").trim().toUpperCase();e+=2;let o=[];for(;e<s.length;){let a=s[e];if(a.code===0&&String(a.value||"").trim().toUpperCase()==="ENDSEC"){e+=1;break}o.push(a),e+=1}t.set(r,o)}return t}d(Xr,"splitSections");function Ei(s,t,e){return{layer:s,kind:t,d:e}}d(Ei,"buildPathRecord");function we(s,t){let e=s.get(t);if(e)return e;let n={name:t,kind:St(t),pathCount:0,circleCount:0,textCount:0};return s.set(t,n),n}d(we,"touchLayer");function qr(s,t){if(t===1)return s;let e=d(n=>[n[0]*t,n[1]*t],"scalePoint");return{lines:s.lines.map(n=>({...n,start:e(n.start),end:e(n.end)})),arcs:s.arcs.map(n=>({...n,center:e(n.center),radius:n.radius*t})),circles:s.circles.map(n=>({...n,center:e(n.center),radius:n.radius*t})),texts:s.texts.map(n=>({...n,position:e(n.position),heightMm:n.heightMm*t}))}}d(qr,"scaleEntitiesToMm");function Ci(s,{fileRef:t="",sourceUrl:e=""}={}){if(/^version https:\/\/git-lfs/.test(String(s||"")))throw new Error("This DXF is a Git LFS pointer, not the drawing itself. Run `git lfs checkout` on it and rebuild.");let n=Mr(s),i=Xr(n),r=Sr(i.get("HEADER")||[]),o=Tr(i.get("TABLES")||[]),a=Wr(i.get("BLOCKS")||[]),c=Er(r.sourceUnits),l={dimensions:0,leaders:0,paperspaceEntities:0},u=qr(wi(i.get("ENTITIES")||[],{blocks:a,apparatus:l}),c),h=null;for(let g of u.lines)h=un(h,xr(g));for(let g of u.arcs)h=un(h,vr(g));for(let g of u.circles)h=un(h,yr(g));if(!h)throw new Error("Failed to compute DXF bounds");let f=Math.max(h.maxX-h.minX,0),m=Math.max(h.maxY-h.minY,0),p=[],_=[],x=new Map;for(let g of u.lines){let M=oe(g.start,{minX:h.minX,maxY:h.maxY}),y=oe(g.end,{minX:h.minX,maxY:h.maxY});p.push(Ei(g.layer,St(g.layer),`M ${O(M[0])} ${O(M[1])} L ${O(y[0])} ${O(y[1])}`)),we(x,g.layer).pathCount+=1}for(let g of u.arcs){let M=oe(ae(g.center,g.radius,g.startAngleDeg),{minX:h.minX,maxY:h.maxY}),y=oe(ae(g.center,g.radius,g.startAngleDeg+g.sweepAngleDeg),{minX:h.minX,maxY:h.maxY}),v=Math.abs(g.sweepAngleDeg)>180+1e-9?1:0,b=g.sweepAngleDeg>=0?0:1;p.push(Ei(g.layer,St(g.layer),`M ${O(M[0])} ${O(M[1])} A ${O(g.radius)} ${O(g.radius)} 0 ${v} ${b} ${O(y[0])} ${O(y[1])}`)),we(x,g.layer).pathCount+=1}for(let g of u.circles){let M=oe(g.center,{minX:h.minX,maxY:h.maxY});_.push({layer:g.layer,kind:St(g.layer),cx:O(M[0]),cy:O(M[1]),r:O(g.radius)}),we(x,g.layer).circleCount+=1}for(let g of u.texts)we(x,g.layer).textCount+=1;return{fileRef:t,sourceUrl:e,sourceUnits:r.sourceUnits,unitsScaleMm:c,defaultThicknessMm:O(r.defaultThicknessMm),bounds:{minX:0,minY:0,maxX:O(f),maxY:O(m),width:O(f),height:O(m)},counts:{paths:p.length,circles:_.length,entities:p.length+_.length},apparatus:l,layers:[...x.keys()].sort().map(g=>{let M=x.get(g),y=o.get(g);return{...M,colorAci:y?y.aci:null,colorHex:y?Ar(y.aci):null,visibleDefault:y?y.visibleDefault:!0}}),geometry:{lines:u.lines.map(g=>({layer:g.layer,kind:St(g.layer),start:[O(g.start[0]),O(g.start[1])],end:[O(g.end[0]),O(g.end[1])]})),arcs:u.arcs.map(g=>({layer:g.layer,kind:St(g.layer),center:[O(g.center[0]),O(g.center[1])],radius:O(g.radius),startAngleDeg:O(g.startAngleDeg),sweepAngleDeg:O(g.sweepAngleDeg)})),circles:u.circles.map(g=>({layer:g.layer,kind:St(g.layer),center:[O(g.center[0]),O(g.center[1])],radius:O(g.radius)})),texts:u.texts.map(g=>({layer:g.layer,kind:St(g.layer),position:[O(g.position[0]),O(g.position[1])],heightMm:O(g.heightMm),rotationDeg:O(g.rotationDeg),value:g.value}))},paths:p,circles:_}}d(Ci,"parseDxf");var Xi=1;var qi=3;var vn=0,Mn=1,Sn=2,bn=3,En=4,An=5,Tn=6,wn=7,Yi=0,$i=1,Zi=2;var Wn=1,Xn=2,qn=3,Yn=4,$n=5,Zn=6,Jn=7;var Kn=300,Ji=301,Qn=302;var Ki=306,Cn=1e3,le=1001,Rn=1002;var Qi=1006;var ji=1008;var ts=1009;var es=1023;var de=2300,Oe=2301,Ue=2302,In=2303,Pn=2400,Ln=2401,Nn=2402;var jn="",ut="srgb",Dn="srgb-linear",Un="linear",Fe="srgb";var he=2e3,Fn=2001;function Yr(s){return ArrayBuffer.isView(s)&&!(s instanceof DataView)}d(Yr,"isTypedArray");function On(s){return document.createElementNS("http://www.w3.org/1999/xhtml",s)}d(On,"createElementNS");var Ri={},Be=null;function ns(s){let t=s[0];if(typeof t=="string"&&t.startsWith("TSL:")){let e=s[1];e&&e.isStackTrace?s[0]+=" "+e.getLocation():s[1]='Stack trace not available. Enable "THREE.Node.captureStackTrace" to capture stack traces.'}return s}d(ns,"enhanceLogMessage");function tt(...s){s=ns(s);let t="THREE."+s.shift();if(Be)Be("warn",t,...s);else{let e=s[0];e&&e.isStackTrace?console.warn(e.getError(t)):console.warn(t,...s)}}d(tt,"warn");function $(...s){s=ns(s);let t="THREE."+s.shift();if(Be)Be("error",t,...s);else{let e=s[0];e&&e.isStackTrace?console.error(e.getError(t)):console.error(t,...s)}}d($,"error");function Yt(...s){let t=s.join(" ");t in Ri||(Ri[t]=!0,tt(...s))}d(Yt,"warnOnce");var $r={[vn]:Mn,[Sn]:Tn,[En]:wn,[bn]:An,[Mn]:vn,[Tn]:Sn,[wn]:En,[An]:bn},fe=class{static{d(this,"EventDispatcher")}addEventListener(t,e){this._listeners===void 0&&(this._listeners={});let n=this._listeners;n[t]===void 0&&(n[t]=[]),n[t].indexOf(e)===-1&&n[t].push(e)}hasEventListener(t,e){let n=this._listeners;return n===void 0?!1:n[t]!==void 0&&n[t].indexOf(e)!==-1}removeEventListener(t,e){let n=this._listeners;if(n===void 0)return;let i=n[t];if(i!==void 0){let r=i.indexOf(e);r!==-1&&i.splice(r,1)}}dispatchEvent(t){let e=this._listeners;if(e===void 0)return;let n=e[t.type];if(n!==void 0){t.target=this;let i=n.slice(0);for(let r=0,o=i.length;r<o;r++)i[r].call(this,t);t.target=null}}},Q=["00","01","02","03","04","05","06","07","08","09","0a","0b","0c","0d","0e","0f","10","11","12","13","14","15","16","17","18","19","1a","1b","1c","1d","1e","1f","20","21","22","23","24","25","26","27","28","29","2a","2b","2c","2d","2e","2f","30","31","32","33","34","35","36","37","38","39","3a","3b","3c","3d","3e","3f","40","41","42","43","44","45","46","47","48","49","4a","4b","4c","4d","4e","4f","50","51","52","53","54","55","56","57","58","59","5a","5b","5c","5d","5e","5f","60","61","62","63","64","65","66","67","68","69","6a","6b","6c","6d","6e","6f","70","71","72","73","74","75","76","77","78","79","7a","7b","7c","7d","7e","7f","80","81","82","83","84","85","86","87","88","89","8a","8b","8c","8d","8e","8f","90","91","92","93","94","95","96","97","98","99","9a","9b","9c","9d","9e","9f","a0","a1","a2","a3","a4","a5","a6","a7","a8","a9","aa","ab","ac","ad","ae","af","b0","b1","b2","b3","b4","b5","b6","b7","b8","b9","ba","bb","bc","bd","be","bf","c0","c1","c2","c3","c4","c5","c6","c7","c8","c9","ca","cb","cc","cd","ce","cf","d0","d1","d2","d3","d4","d5","d6","d7","d8","d9","da","db","dc","dd","de","df","e0","e1","e2","e3","e4","e5","e6","e7","e8","e9","ea","eb","ec","ed","ee","ef","f0","f1","f2","f3","f4","f5","f6","f7","f8","f9","fa","fb","fc","fd","fe","ff"];var yh=Math.PI/180,Zr=180/Math.PI;function ti(){let s=Math.random()*4294967295|0,t=Math.random()*4294967295|0,e=Math.random()*4294967295|0,n=Math.random()*4294967295|0;return(Q[s&255]+Q[s>>8&255]+Q[s>>16&255]+Q[s>>24&255]+"-"+Q[t&255]+Q[t>>8&255]+"-"+Q[t>>16&15|64]+Q[t>>24&255]+"-"+Q[e&63|128]+Q[e>>8&255]+"-"+Q[e>>16&255]+Q[e>>24&255]+Q[n&255]+Q[n>>8&255]+Q[n>>16&255]+Q[n>>24&255]).toLowerCase()}d(ti,"generateUUID");function F(s,t,e){return Math.max(t,Math.min(e,s))}d(F,"clamp");function Jr(s,t){return(s%t+t)%t}d(Jr,"euclideanModulo");function dn(s,t,e){return(1-e)*s+e*t}d(dn,"lerp");var et=class s{static{d(this,"Vector2")}static{s.prototype.isVector2=!0}constructor(t=0,e=0){this.x=t,this.y=e}get width(){return this.x}set width(t){this.x=t}get height(){return this.y}set height(t){this.y=t}set(t,e){return this.x=t,this.y=e,this}setScalar(t){return this.x=t,this.y=t,this}setX(t){return this.x=t,this}setY(t){return this.y=t,this}setComponent(t,e){switch(t){case 0:this.x=e;break;case 1:this.y=e;break;default:throw new Error("THREE.Vector2: index is out of range: "+t)}return this}getComponent(t){switch(t){case 0:return this.x;case 1:return this.y;default:throw new Error("THREE.Vector2: index is out of range: "+t)}}clone(){return new this.constructor(this.x,this.y)}copy(t){return this.x=t.x,this.y=t.y,this}add(t){return this.x+=t.x,this.y+=t.y,this}addScalar(t){return this.x+=t,this.y+=t,this}addVectors(t,e){return this.x=t.x+e.x,this.y=t.y+e.y,this}addScaledVector(t,e){return this.x+=t.x*e,this.y+=t.y*e,this}sub(t){return this.x-=t.x,this.y-=t.y,this}subScalar(t){return this.x-=t,this.y-=t,this}subVectors(t,e){return this.x=t.x-e.x,this.y=t.y-e.y,this}multiply(t){return this.x*=t.x,this.y*=t.y,this}multiplyScalar(t){return this.x*=t,this.y*=t,this}divide(t){return this.x/=t.x,this.y/=t.y,this}divideScalar(t){return this.multiplyScalar(1/t)}applyMatrix3(t){let e=this.x,n=this.y,i=t.elements;return this.x=i[0]*e+i[3]*n+i[6],this.y=i[1]*e+i[4]*n+i[7],this}min(t){return this.x=Math.min(this.x,t.x),this.y=Math.min(this.y,t.y),this}max(t){return this.x=Math.max(this.x,t.x),this.y=Math.max(this.y,t.y),this}clamp(t,e){return this.x=F(this.x,t.x,e.x),this.y=F(this.y,t.y,e.y),this}clampScalar(t,e){return this.x=F(this.x,t,e),this.y=F(this.y,t,e),this}clampLength(t,e){let n=this.length();return this.divideScalar(n||1).multiplyScalar(F(n,t,e))}floor(){return this.x=Math.floor(this.x),this.y=Math.floor(this.y),this}ceil(){return this.x=Math.ceil(this.x),this.y=Math.ceil(this.y),this}round(){return this.x=Math.round(this.x),this.y=Math.round(this.y),this}roundToZero(){return this.x=Math.trunc(this.x),this.y=Math.trunc(this.y),this}negate(){return this.x=-this.x,this.y=-this.y,this}dot(t){return this.x*t.x+this.y*t.y}cross(t){return this.x*t.y-this.y*t.x}lengthSq(){return this.x*this.x+this.y*this.y}length(){return Math.sqrt(this.x*this.x+this.y*this.y)}manhattanLength(){return Math.abs(this.x)+Math.abs(this.y)}normalize(){return this.divideScalar(this.length()||1)}angle(){return Math.atan2(-this.y,-this.x)+Math.PI}angleTo(t){let e=Math.sqrt(this.lengthSq()*t.lengthSq());if(e===0)return Math.PI/2;let n=this.dot(t)/e;return Math.acos(F(n,-1,1))}distanceTo(t){return Math.sqrt(this.distanceToSquared(t))}distanceToSquared(t){let e=this.x-t.x,n=this.y-t.y;return e*e+n*n}manhattanDistanceTo(t){return Math.abs(this.x-t.x)+Math.abs(this.y-t.y)}setLength(t){return this.normalize().multiplyScalar(t)}lerp(t,e){return this.x+=(t.x-this.x)*e,this.y+=(t.y-this.y)*e,this}lerpVectors(t,e,n){return this.x=t.x+(e.x-t.x)*n,this.y=t.y+(e.y-t.y)*n,this}equals(t){return t.x===this.x&&t.y===this.y}fromArray(t,e=0){return this.x=t[e],this.y=t[e+1],this}toArray(t=[],e=0){return t[e]=this.x,t[e+1]=this.y,t}fromBufferAttribute(t,e){return this.x=t.getX(e),this.y=t.getY(e),this}rotateAround(t,e){let n=Math.cos(e),i=Math.sin(e),r=this.x-t.x,o=this.y-t.y;return this.x=r*n-o*i+t.x,this.y=r*i+o*n+t.y,this}random(){return this.x=Math.random(),this.y=Math.random(),this}*[Symbol.iterator](){yield this.x,yield this.y}},_t=class{static{d(this,"Quaternion")}constructor(t=0,e=0,n=0,i=1){this.isQuaternion=!0,this._x=t,this._y=e,this._z=n,this._w=i}static slerpFlat(t,e,n,i,r,o,a){let c=n[i+0],l=n[i+1],u=n[i+2],h=n[i+3],f=r[o+0],m=r[o+1],p=r[o+2],_=r[o+3];if(h!==_||c!==f||l!==m||u!==p){let x=c*f+l*m+u*p+h*_;x<0&&(f=-f,m=-m,p=-p,_=-_,x=-x);let g=1-a;if(x<.9995){let M=Math.acos(x),y=Math.sin(M);g=Math.sin(g*M)/y,a=Math.sin(a*M)/y,c=c*g+f*a,l=l*g+m*a,u=u*g+p*a,h=h*g+_*a}else{c=c*g+f*a,l=l*g+m*a,u=u*g+p*a,h=h*g+_*a;let M=1/Math.sqrt(c*c+l*l+u*u+h*h);c*=M,l*=M,u*=M,h*=M}}t[e]=c,t[e+1]=l,t[e+2]=u,t[e+3]=h}static multiplyQuaternionsFlat(t,e,n,i,r,o){let a=n[i],c=n[i+1],l=n[i+2],u=n[i+3],h=r[o],f=r[o+1],m=r[o+2],p=r[o+3];return t[e]=a*p+u*h+c*m-l*f,t[e+1]=c*p+u*f+l*h-a*m,t[e+2]=l*p+u*m+a*f-c*h,t[e+3]=u*p-a*h-c*f-l*m,t}get x(){return this._x}set x(t){this._x=t,this._onChangeCallback()}get y(){return this._y}set y(t){this._y=t,this._onChangeCallback()}get z(){return this._z}set z(t){this._z=t,this._onChangeCallback()}get w(){return this._w}set w(t){this._w=t,this._onChangeCallback()}set(t,e,n,i){return this._x=t,this._y=e,this._z=n,this._w=i,this._onChangeCallback(),this}clone(){return new this.constructor(this._x,this._y,this._z,this._w)}copy(t){return this._x=t.x,this._y=t.y,this._z=t.z,this._w=t.w,this._onChangeCallback(),this}setFromEuler(t,e=!0){let n=t._x,i=t._y,r=t._z,o=t._order,a=Math.cos,c=Math.sin,l=a(n/2),u=a(i/2),h=a(r/2),f=c(n/2),m=c(i/2),p=c(r/2);switch(o){case"XYZ":this._x=f*u*h+l*m*p,this._y=l*m*h-f*u*p,this._z=l*u*p+f*m*h,this._w=l*u*h-f*m*p;break;case"YXZ":this._x=f*u*h+l*m*p,this._y=l*m*h-f*u*p,this._z=l*u*p-f*m*h,this._w=l*u*h+f*m*p;break;case"ZXY":this._x=f*u*h-l*m*p,this._y=l*m*h+f*u*p,this._z=l*u*p+f*m*h,this._w=l*u*h-f*m*p;break;case"ZYX":this._x=f*u*h-l*m*p,this._y=l*m*h+f*u*p,this._z=l*u*p-f*m*h,this._w=l*u*h+f*m*p;break;case"YZX":this._x=f*u*h+l*m*p,this._y=l*m*h+f*u*p,this._z=l*u*p-f*m*h,this._w=l*u*h-f*m*p;break;case"XZY":this._x=f*u*h-l*m*p,this._y=l*m*h-f*u*p,this._z=l*u*p+f*m*h,this._w=l*u*h+f*m*p;break;default:tt("Quaternion: .setFromEuler() encountered an unknown order: "+o)}return e===!0&&this._onChangeCallback(),this}setFromAxisAngle(t,e){let n=e/2,i=Math.sin(n);return this._x=t.x*i,this._y=t.y*i,this._z=t.z*i,this._w=Math.cos(n),this._onChangeCallback(),this}setFromRotationMatrix(t){let e=t.elements,n=e[0],i=e[4],r=e[8],o=e[1],a=e[5],c=e[9],l=e[2],u=e[6],h=e[10],f=n+a+h;if(f>0){let m=.5/Math.sqrt(f+1);this._w=.25/m,this._x=(u-c)*m,this._y=(r-l)*m,this._z=(o-i)*m}else if(n>a&&n>h){let m=2*Math.sqrt(1+n-a-h);this._w=(u-c)/m,this._x=.25*m,this._y=(i+o)/m,this._z=(r+l)/m}else if(a>h){let m=2*Math.sqrt(1+a-n-h);this._w=(r-l)/m,this._x=(i+o)/m,this._y=.25*m,this._z=(c+u)/m}else{let m=2*Math.sqrt(1+h-n-a);this._w=(o-i)/m,this._x=(r+l)/m,this._y=(c+u)/m,this._z=.25*m}return this._onChangeCallback(),this}setFromUnitVectors(t,e){let n=t.dot(e)+1;return n<1e-8?(n=0,Math.abs(t.x)>Math.abs(t.z)?(this._x=-t.y,this._y=t.x,this._z=0,this._w=n):(this._x=0,this._y=-t.z,this._z=t.y,this._w=n)):(this._x=t.y*e.z-t.z*e.y,this._y=t.z*e.x-t.x*e.z,this._z=t.x*e.y-t.y*e.x,this._w=n),this.normalize()}angleTo(t){return 2*Math.acos(Math.abs(F(this.dot(t),-1,1)))}rotateTowards(t,e){let n=this.angleTo(t);if(n===0)return this;let i=Math.min(1,e/n);return this.slerp(t,i),this}identity(){return this.set(0,0,0,1)}invert(){return this.conjugate()}conjugate(){return this._x*=-1,this._y*=-1,this._z*=-1,this._onChangeCallback(),this}dot(t){return this._x*t._x+this._y*t._y+this._z*t._z+this._w*t._w}lengthSq(){return this._x*this._x+this._y*this._y+this._z*this._z+this._w*this._w}length(){return Math.sqrt(this._x*this._x+this._y*this._y+this._z*this._z+this._w*this._w)}normalize(){let t=this.length();return t===0?(this._x=0,this._y=0,this._z=0,this._w=1):(t=1/t,this._x=this._x*t,this._y=this._y*t,this._z=this._z*t,this._w=this._w*t),this._onChangeCallback(),this}multiply(t){return this.multiplyQuaternions(this,t)}premultiply(t){return this.multiplyQuaternions(t,this)}multiplyQuaternions(t,e){let n=t._x,i=t._y,r=t._z,o=t._w,a=e._x,c=e._y,l=e._z,u=e._w;return this._x=n*u+o*a+i*l-r*c,this._y=i*u+o*c+r*a-n*l,this._z=r*u+o*l+n*c-i*a,this._w=o*u-n*a-i*c-r*l,this._onChangeCallback(),this}slerp(t,e){let n=t._x,i=t._y,r=t._z,o=t._w,a=this.dot(t);a<0&&(n=-n,i=-i,r=-r,o=-o,a=-a);let c=1-e;if(a<.9995){let l=Math.acos(a),u=Math.sin(l);c=Math.sin(c*l)/u,e=Math.sin(e*l)/u,this._x=this._x*c+n*e,this._y=this._y*c+i*e,this._z=this._z*c+r*e,this._w=this._w*c+o*e,this._onChangeCallback()}else this._x=this._x*c+n*e,this._y=this._y*c+i*e,this._z=this._z*c+r*e,this._w=this._w*c+o*e,this.normalize();return this}slerpQuaternions(t,e,n){return this.copy(t).slerp(e,n)}random(){let t=2*Math.PI*Math.random(),e=2*Math.PI*Math.random(),n=Math.random(),i=Math.sqrt(1-n),r=Math.sqrt(n);return this.set(i*Math.sin(t),i*Math.cos(t),r*Math.sin(e),r*Math.cos(e))}equals(t){return t._x===this._x&&t._y===this._y&&t._z===this._z&&t._w===this._w}fromArray(t,e=0){return this._x=t[e],this._y=t[e+1],this._z=t[e+2],this._w=t[e+3],this._onChangeCallback(),this}toArray(t=[],e=0){return t[e]=this._x,t[e+1]=this._y,t[e+2]=this._z,t[e+3]=this._w,t}fromBufferAttribute(t,e){return this._x=t.getX(e),this._y=t.getY(e),this._z=t.getZ(e),this._w=t.getW(e),this._onChangeCallback(),this}toJSON(){return this.toArray()}_onChange(t){return this._onChangeCallback=t,this}_onChangeCallback(){}*[Symbol.iterator](){yield this._x,yield this._y,yield this._z,yield this._w}},D=class s{static{d(this,"Vector3")}static{s.prototype.isVector3=!0}constructor(t=0,e=0,n=0){this.x=t,this.y=e,this.z=n}set(t,e,n){return n===void 0&&(n=this.z),this.x=t,this.y=e,this.z=n,this}setScalar(t){return this.x=t,this.y=t,this.z=t,this}setX(t){return this.x=t,this}setY(t){return this.y=t,this}setZ(t){return this.z=t,this}setComponent(t,e){switch(t){case 0:this.x=e;break;case 1:this.y=e;break;case 2:this.z=e;break;default:throw new Error("THREE.Vector3: index is out of range: "+t)}return this}getComponent(t){switch(t){case 0:return this.x;case 1:return this.y;case 2:return this.z;default:throw new Error("THREE.Vector3: index is out of range: "+t)}}clone(){return new this.constructor(this.x,this.y,this.z)}copy(t){return this.x=t.x,this.y=t.y,this.z=t.z,this}add(t){return this.x+=t.x,this.y+=t.y,this.z+=t.z,this}addScalar(t){return this.x+=t,this.y+=t,this.z+=t,this}addVectors(t,e){return this.x=t.x+e.x,this.y=t.y+e.y,this.z=t.z+e.z,this}addScaledVector(t,e){return this.x+=t.x*e,this.y+=t.y*e,this.z+=t.z*e,this}sub(t){return this.x-=t.x,this.y-=t.y,this.z-=t.z,this}subScalar(t){return this.x-=t,this.y-=t,this.z-=t,this}subVectors(t,e){return this.x=t.x-e.x,this.y=t.y-e.y,this.z=t.z-e.z,this}multiply(t){return this.x*=t.x,this.y*=t.y,this.z*=t.z,this}multiplyScalar(t){return this.x*=t,this.y*=t,this.z*=t,this}multiplyVectors(t,e){return this.x=t.x*e.x,this.y=t.y*e.y,this.z=t.z*e.z,this}applyEuler(t){return this.applyQuaternion(Ii.setFromEuler(t))}applyAxisAngle(t,e){return this.applyQuaternion(Ii.setFromAxisAngle(t,e))}applyMatrix3(t){let e=this.x,n=this.y,i=this.z,r=t.elements;return this.x=r[0]*e+r[3]*n+r[6]*i,this.y=r[1]*e+r[4]*n+r[7]*i,this.z=r[2]*e+r[5]*n+r[8]*i,this}applyNormalMatrix(t){return this.applyMatrix3(t).normalize()}applyMatrix4(t){let e=this.x,n=this.y,i=this.z,r=t.elements,o=1/(r[3]*e+r[7]*n+r[11]*i+r[15]);return this.x=(r[0]*e+r[4]*n+r[8]*i+r[12])*o,this.y=(r[1]*e+r[5]*n+r[9]*i+r[13])*o,this.z=(r[2]*e+r[6]*n+r[10]*i+r[14])*o,this}applyQuaternion(t){let e=this.x,n=this.y,i=this.z,r=t.x,o=t.y,a=t.z,c=t.w,l=2*(o*i-a*n),u=2*(a*e-r*i),h=2*(r*n-o*e);return this.x=e+c*l+o*h-a*u,this.y=n+c*u+a*l-r*h,this.z=i+c*h+r*u-o*l,this}project(t){return this.applyMatrix4(t.matrixWorldInverse).applyMatrix4(t.projectionMatrix)}unproject(t){return this.applyMatrix4(t.projectionMatrixInverse).applyMatrix4(t.matrixWorld)}transformDirection(t){let e=this.x,n=this.y,i=this.z,r=t.elements;return this.x=r[0]*e+r[4]*n+r[8]*i,this.y=r[1]*e+r[5]*n+r[9]*i,this.z=r[2]*e+r[6]*n+r[10]*i,this.normalize()}divide(t){return this.x/=t.x,this.y/=t.y,this.z/=t.z,this}divideScalar(t){return this.multiplyScalar(1/t)}min(t){return this.x=Math.min(this.x,t.x),this.y=Math.min(this.y,t.y),this.z=Math.min(this.z,t.z),this}max(t){return this.x=Math.max(this.x,t.x),this.y=Math.max(this.y,t.y),this.z=Math.max(this.z,t.z),this}clamp(t,e){return this.x=F(this.x,t.x,e.x),this.y=F(this.y,t.y,e.y),this.z=F(this.z,t.z,e.z),this}clampScalar(t,e){return this.x=F(this.x,t,e),this.y=F(this.y,t,e),this.z=F(this.z,t,e),this}clampLength(t,e){let n=this.length();return this.divideScalar(n||1).multiplyScalar(F(n,t,e))}floor(){return this.x=Math.floor(this.x),this.y=Math.floor(this.y),this.z=Math.floor(this.z),this}ceil(){return this.x=Math.ceil(this.x),this.y=Math.ceil(this.y),this.z=Math.ceil(this.z),this}round(){return this.x=Math.round(this.x),this.y=Math.round(this.y),this.z=Math.round(this.z),this}roundToZero(){return this.x=Math.trunc(this.x),this.y=Math.trunc(this.y),this.z=Math.trunc(this.z),this}negate(){return this.x=-this.x,this.y=-this.y,this.z=-this.z,this}dot(t){return this.x*t.x+this.y*t.y+this.z*t.z}lengthSq(){return this.x*this.x+this.y*this.y+this.z*this.z}length(){return Math.sqrt(this.x*this.x+this.y*this.y+this.z*this.z)}manhattanLength(){return Math.abs(this.x)+Math.abs(this.y)+Math.abs(this.z)}normalize(){return this.divideScalar(this.length()||1)}setLength(t){return this.normalize().multiplyScalar(t)}lerp(t,e){return this.x+=(t.x-this.x)*e,this.y+=(t.y-this.y)*e,this.z+=(t.z-this.z)*e,this}lerpVectors(t,e,n){return this.x=t.x+(e.x-t.x)*n,this.y=t.y+(e.y-t.y)*n,this.z=t.z+(e.z-t.z)*n,this}cross(t){return this.crossVectors(this,t)}crossVectors(t,e){let n=t.x,i=t.y,r=t.z,o=e.x,a=e.y,c=e.z;return this.x=i*c-r*a,this.y=r*o-n*c,this.z=n*a-i*o,this}projectOnVector(t){let e=t.lengthSq();if(e===0)return this.set(0,0,0);let n=t.dot(this)/e;return this.copy(t).multiplyScalar(n)}projectOnPlane(t){return fn.copy(this).projectOnVector(t),this.sub(fn)}reflect(t){return this.sub(fn.copy(t).multiplyScalar(2*this.dot(t)))}angleTo(t){let e=Math.sqrt(this.lengthSq()*t.lengthSq());if(e===0)return Math.PI/2;let n=this.dot(t)/e;return Math.acos(F(n,-1,1))}distanceTo(t){return Math.sqrt(this.distanceToSquared(t))}distanceToSquared(t){let e=this.x-t.x,n=this.y-t.y,i=this.z-t.z;return e*e+n*n+i*i}manhattanDistanceTo(t){return Math.abs(this.x-t.x)+Math.abs(this.y-t.y)+Math.abs(this.z-t.z)}setFromSpherical(t){return this.setFromSphericalCoords(t.radius,t.phi,t.theta)}setFromSphericalCoords(t,e,n){let i=Math.sin(e)*t;return this.x=i*Math.sin(n),this.y=Math.cos(e)*t,this.z=i*Math.cos(n),this}setFromCylindrical(t){return this.setFromCylindricalCoords(t.radius,t.theta,t.y)}setFromCylindricalCoords(t,e,n){return this.x=t*Math.sin(e),this.y=n,this.z=t*Math.cos(e),this}setFromMatrixPosition(t){let e=t.elements;return this.x=e[12],this.y=e[13],this.z=e[14],this}setFromMatrixScale(t){let e=this.setFromMatrixColumn(t,0).length(),n=this.setFromMatrixColumn(t,1).length(),i=this.setFromMatrixColumn(t,2).length();return this.x=e,this.y=n,this.z=i,this}setFromMatrixColumn(t,e){return this.fromArray(t.elements,e*4)}setFromMatrix3Column(t,e){return this.fromArray(t.elements,e*3)}setFromEuler(t){return this.x=t._x,this.y=t._y,this.z=t._z,this}setFromColor(t){return this.x=t.r,this.y=t.g,this.z=t.b,this}equals(t){return t.x===this.x&&t.y===this.y&&t.z===this.z}fromArray(t,e=0){return this.x=t[e],this.y=t[e+1],this.z=t[e+2],this}toArray(t=[],e=0){return t[e]=this.x,t[e+1]=this.y,t[e+2]=this.z,t}fromBufferAttribute(t,e){return this.x=t.getX(e),this.y=t.getY(e),this.z=t.getZ(e),this}random(){return this.x=Math.random(),this.y=Math.random(),this.z=Math.random(),this}randomDirection(){let t=Math.random()*Math.PI*2,e=Math.random()*2-1,n=Math.sqrt(1-e*e);return this.x=n*Math.cos(t),this.y=e,this.z=n*Math.sin(t),this}*[Symbol.iterator](){yield this.x,yield this.y,yield this.z}},fn=new D,Ii=new _t,L=class s{static{d(this,"Matrix3")}static{s.prototype.isMatrix3=!0}constructor(t,e,n,i,r,o,a,c,l){this.elements=[1,0,0,0,1,0,0,0,1],t!==void 0&&this.set(t,e,n,i,r,o,a,c,l)}set(t,e,n,i,r,o,a,c,l){let u=this.elements;return u[0]=t,u[1]=i,u[2]=a,u[3]=e,u[4]=r,u[5]=c,u[6]=n,u[7]=o,u[8]=l,this}identity(){return this.set(1,0,0,0,1,0,0,0,1),this}copy(t){let e=this.elements,n=t.elements;return e[0]=n[0],e[1]=n[1],e[2]=n[2],e[3]=n[3],e[4]=n[4],e[5]=n[5],e[6]=n[6],e[7]=n[7],e[8]=n[8],this}extractBasis(t,e,n){return t.setFromMatrix3Column(this,0),e.setFromMatrix3Column(this,1),n.setFromMatrix3Column(this,2),this}setFromMatrix4(t){let e=t.elements;return this.set(e[0],e[4],e[8],e[1],e[5],e[9],e[2],e[6],e[10]),this}multiply(t){return this.multiplyMatrices(this,t)}premultiply(t){return this.multiplyMatrices(t,this)}multiplyMatrices(t,e){let n=t.elements,i=e.elements,r=this.elements,o=n[0],a=n[3],c=n[6],l=n[1],u=n[4],h=n[7],f=n[2],m=n[5],p=n[8],_=i[0],x=i[3],g=i[6],M=i[1],y=i[4],v=i[7],b=i[2],A=i[5],R=i[8];return r[0]=o*_+a*M+c*b,r[3]=o*x+a*y+c*A,r[6]=o*g+a*v+c*R,r[1]=l*_+u*M+h*b,r[4]=l*x+u*y+h*A,r[7]=l*g+u*v+h*R,r[2]=f*_+m*M+p*b,r[5]=f*x+m*y+p*A,r[8]=f*g+m*v+p*R,this}multiplyScalar(t){let e=this.elements;return e[0]*=t,e[3]*=t,e[6]*=t,e[1]*=t,e[4]*=t,e[7]*=t,e[2]*=t,e[5]*=t,e[8]*=t,this}determinant(){let t=this.elements,e=t[0],n=t[1],i=t[2],r=t[3],o=t[4],a=t[5],c=t[6],l=t[7],u=t[8];return e*o*u-e*a*l-n*r*u+n*a*c+i*r*l-i*o*c}invert(){let t=this.elements,e=t[0],n=t[1],i=t[2],r=t[3],o=t[4],a=t[5],c=t[6],l=t[7],u=t[8],h=u*o-a*l,f=a*c-u*r,m=l*r-o*c,p=e*h+n*f+i*m;if(p===0)return this.set(0,0,0,0,0,0,0,0,0);let _=1/p;return t[0]=h*_,t[1]=(i*l-u*n)*_,t[2]=(a*n-i*o)*_,t[3]=f*_,t[4]=(u*e-i*c)*_,t[5]=(i*r-a*e)*_,t[6]=m*_,t[7]=(n*c-l*e)*_,t[8]=(o*e-n*r)*_,this}transpose(){let t,e=this.elements;return t=e[1],e[1]=e[3],e[3]=t,t=e[2],e[2]=e[6],e[6]=t,t=e[5],e[5]=e[7],e[7]=t,this}getNormalMatrix(t){return this.setFromMatrix4(t).invert().transpose()}transposeIntoArray(t){let e=this.elements;return t[0]=e[0],t[1]=e[3],t[2]=e[6],t[3]=e[1],t[4]=e[4],t[5]=e[7],t[6]=e[2],t[7]=e[5],t[8]=e[8],this}setUvTransform(t,e,n,i,r,o,a){let c=Math.cos(r),l=Math.sin(r);return this.set(n*c,n*l,-n*(c*o+l*a)+o+t,-i*l,i*c,-i*(-l*o+c*a)+a+e,0,0,1),this}scale(t,e){return Yt("Matrix3: .scale() is deprecated. Use .makeScale() instead."),this.premultiply(pn.makeScale(t,e)),this}rotate(t){return Yt("Matrix3: .rotate() is deprecated. Use .makeRotation() instead."),this.premultiply(pn.makeRotation(-t)),this}translate(t,e){return Yt("Matrix3: .translate() is deprecated. Use .makeTranslation() instead."),this.premultiply(pn.makeTranslation(t,e)),this}makeTranslation(t,e){return t.isVector2?this.set(1,0,t.x,0,1,t.y,0,0,1):this.set(1,0,t,0,1,e,0,0,1),this}makeRotation(t){let e=Math.cos(t),n=Math.sin(t);return this.set(e,-n,0,n,e,0,0,0,1),this}makeScale(t,e){return this.set(t,0,0,0,e,0,0,0,1),this}equals(t){let e=this.elements,n=t.elements;for(let i=0;i<9;i++)if(e[i]!==n[i])return!1;return!0}fromArray(t,e=0){for(let n=0;n<9;n++)this.elements[n]=t[n+e];return this}toArray(t=[],e=0){let n=this.elements;return t[e]=n[0],t[e+1]=n[1],t[e+2]=n[2],t[e+3]=n[3],t[e+4]=n[4],t[e+5]=n[5],t[e+6]=n[6],t[e+7]=n[7],t[e+8]=n[8],t}clone(){return new this.constructor().fromArray(this.elements)}},pn=new L,Pi=new L().set(.4123908,.3575843,.1804808,.212639,.7151687,.0721923,.0193308,.1191948,.9505322),Li=new L().set(3.2409699,-1.5373832,-.4986108,-.9692436,1.8759675,.0415551,.0556301,-.203977,1.0569715);function Kr(){let s={enabled:!0,workingColorSpace:Dn,spaces:{},convert:d(function(i,r,o){return this.enabled===!1||r===o||!r||!o||(this.spaces[r].transfer===Fe&&(i.r=gt(i.r),i.g=gt(i.g),i.b=gt(i.b)),this.spaces[r].primaries!==this.spaces[o].primaries&&(i.applyMatrix3(this.spaces[r].toXYZ),i.applyMatrix3(this.spaces[o].fromXYZ)),this.spaces[o].transfer===Fe&&(i.r=$t(i.r),i.g=$t(i.g),i.b=$t(i.b))),i},"convert"),workingToColorSpace:d(function(i,r){return this.convert(i,this.workingColorSpace,r)},"workingToColorSpace"),colorSpaceToWorking:d(function(i,r){return this.convert(i,r,this.workingColorSpace)},"colorSpaceToWorking"),getPrimaries:d(function(i){return this.spaces[i].primaries},"getPrimaries"),getTransfer:d(function(i){return i===jn?Un:this.spaces[i].transfer},"getTransfer"),getToneMappingMode:d(function(i){return this.spaces[i].outputColorSpaceConfig.toneMappingMode||"standard"},"getToneMappingMode"),getLuminanceCoefficients:d(function(i,r=this.workingColorSpace){return i.fromArray(this.spaces[r].luminanceCoefficients)},"getLuminanceCoefficients"),define:d(function(i){Object.assign(this.spaces,i)},"define"),_getMatrix:d(function(i,r,o){return i.copy(this.spaces[r].toXYZ).multiply(this.spaces[o].fromXYZ)},"_getMatrix"),_getDrawingBufferColorSpace:d(function(i){return this.spaces[i].outputColorSpaceConfig.drawingBufferColorSpace},"_getDrawingBufferColorSpace"),_getUnpackColorSpace:d(function(i=this.workingColorSpace){return this.spaces[i].workingColorSpaceConfig.unpackColorSpace},"_getUnpackColorSpace"),fromWorkingColorSpace:d(function(i,r){return Yt("ColorManagement: .fromWorkingColorSpace() has been renamed to .workingToColorSpace()."),s.workingToColorSpace(i,r)},"fromWorkingColorSpace"),toWorkingColorSpace:d(function(i,r){return Yt("ColorManagement: .toWorkingColorSpace() has been renamed to .colorSpaceToWorking()."),s.colorSpaceToWorking(i,r)},"toWorkingColorSpace")},t=[.64,.33,.3,.6,.15,.06],e=[.2126,.7152,.0722],n=[.3127,.329];return s.define({[Dn]:{primaries:t,whitePoint:n,transfer:Un,toXYZ:Pi,fromXYZ:Li,luminanceCoefficients:e,workingColorSpaceConfig:{unpackColorSpace:ut},outputColorSpaceConfig:{drawingBufferColorSpace:ut}},[ut]:{primaries:t,whitePoint:n,transfer:Fe,toXYZ:Pi,fromXYZ:Li,luminanceCoefficients:e,outputColorSpaceConfig:{drawingBufferColorSpace:ut}}}),s}d(Kr,"createColorManagement");var ht=Kr();function gt(s){return s<.04045?s*.0773993808:Math.pow(s*.9478672986+.0521327014,2.4)}d(gt,"SRGBToLinear");function $t(s){return s<.0031308?s*12.92:1.055*Math.pow(s,.41666)-.055}d($t,"LinearToSRGB");var Gt,ze=class{static{d(this,"ImageUtils")}static getDataURL(t,e="image/png"){if(/^data:/i.test(t.src)||typeof HTMLCanvasElement>"u")return t.src;let n;if(t instanceof HTMLCanvasElement)n=t;else{Gt===void 0&&(Gt=On("canvas")),Gt.width=t.width,Gt.height=t.height;let i=Gt.getContext("2d");t instanceof ImageData?i.putImageData(t,0,0):i.drawImage(t,0,0,t.width,t.height),n=Gt}return n.toDataURL(e)}static sRGBToLinear(t){if(typeof HTMLImageElement<"u"&&t instanceof HTMLImageElement||typeof HTMLCanvasElement<"u"&&t instanceof HTMLCanvasElement||typeof ImageBitmap<"u"&&t instanceof ImageBitmap){let e=On("canvas");e.width=t.width,e.height=t.height;let n=e.getContext("2d");n.drawImage(t,0,0,t.width,t.height);let i=n.getImageData(0,0,t.width,t.height),r=i.data;for(let o=0;o<r.length;o++)r[o]=gt(r[o]/255)*255;return n.putImageData(i,0,0),e}else if(t.data){let e=t.data.slice(0);for(let n=0;n<e.length;n++)e instanceof Uint8Array||e instanceof Uint8ClampedArray?e[n]=Math.floor(gt(e[n]/255)*255):e[n]=gt(e[n]);return{data:e,width:t.width,height:t.height}}else return tt("ImageUtils.sRGBToLinear(): Unsupported image type. No color space conversion applied."),t}},Qr=0,Ve=class{static{d(this,"TextureSource")}constructor(t=null){this.isTextureSource=!0,Object.defineProperty(this,"id",{value:Qr++}),this.uuid=ti(),this.data=t,this.dataReady=!0,this.version=0}getSize(t){let e=this.data;return typeof HTMLVideoElement<"u"&&e instanceof HTMLVideoElement?t.set(e.videoWidth,e.videoHeight,0):typeof VideoFrame<"u"&&e instanceof VideoFrame?t.set(e.displayWidth,e.displayHeight,0):e!==null?t.set(e.width,e.height,e.depth||0):t.set(0,0,0),t}set needsUpdate(t){t===!0&&this.version++}toJSON(t){let e=t===void 0||typeof t=="string";if(!e&&t.images[this.uuid]!==void 0)return t.images[this.uuid];let n={uuid:this.uuid,url:""},i=this.data;if(i!==null){let r;if(Array.isArray(i)){r=[];for(let o=0,a=i.length;o<a;o++)i[o].isDataTexture?r.push(mn(i[o].image)):r.push(mn(i[o]))}else r=mn(i);n.url=r}return e||(t.images[this.uuid]=n),n}};function mn(s){return typeof HTMLImageElement<"u"&&s instanceof HTMLImageElement||typeof HTMLCanvasElement<"u"&&s instanceof HTMLCanvasElement||typeof ImageBitmap<"u"&&s instanceof ImageBitmap?ze.getDataURL(s):s.data?{data:Array.from(s.data),width:s.width,height:s.height,type:s.data.constructor.name}:(tt("Texture: Unable to serialize Texture."),{})}d(mn,"serializeImage");var jr=0,gn=new D,Zt=class s extends fe{static{d(this,"Texture")}constructor(t=s.DEFAULT_IMAGE,e=s.DEFAULT_MAPPING,n=le,i=le,r=Qi,o=ji,a=es,c=ts,l=s.DEFAULT_ANISOTROPY,u=jn){super(),this.isTexture=!0,Object.defineProperty(this,"id",{value:jr++}),this.uuid=ti(),this.name="",this.source=new Ve(t),this.mipmaps=[],this.mapping=e,this.channel=0,this.wrapS=n,this.wrapT=i,this.magFilter=r,this.minFilter=o,this.anisotropy=l,this.format=a,this.internalFormat=null,this.type=c,this.offset=new et(0,0),this.repeat=new et(1,1),this.center=new et(0,0),this.rotation=0,this.matrixAutoUpdate=!0,this.matrix=new L,this.generateMipmaps=!0,this.premultiplyAlpha=!1,this.flipY=!0,this.unpackAlignment=4,this.colorSpace=u,this.userData={},this.updateRanges=[],this.version=0,this.onUpdate=null,this.renderTarget=null,this.isRenderTargetTexture=!1,this.isArrayTexture=!!(t&&t.depth&&t.depth>1),this.pmremVersion=0,this.normalized=!1}get width(){return this.source.getSize(gn).x}get height(){return this.source.getSize(gn).y}get depth(){return this.source.getSize(gn).z}get image(){return this.source.data}set image(t){this.source.data=t}updateMatrix(){this.matrix.setUvTransform(this.offset.x,this.offset.y,this.repeat.x,this.repeat.y,this.rotation,this.center.x,this.center.y)}addUpdateRange(t,e){this.updateRanges.push({start:t,count:e})}clearUpdateRanges(){this.updateRanges.length=0}clone(){return new this.constructor().copy(this)}copy(t){return this.name=t.name,this.source=t.source,this.mipmaps=t.mipmaps.slice(0),this.mapping=t.mapping,this.channel=t.channel,this.wrapS=t.wrapS,this.wrapT=t.wrapT,this.magFilter=t.magFilter,this.minFilter=t.minFilter,this.anisotropy=t.anisotropy,this.format=t.format,this.internalFormat=t.internalFormat,this.type=t.type,this.normalized=t.normalized,this.offset.copy(t.offset),this.repeat.copy(t.repeat),this.center.copy(t.center),this.rotation=t.rotation,this.matrixAutoUpdate=t.matrixAutoUpdate,this.matrix.copy(t.matrix),this.generateMipmaps=t.generateMipmaps,this.premultiplyAlpha=t.premultiplyAlpha,this.flipY=t.flipY,this.unpackAlignment=t.unpackAlignment,this.colorSpace=t.colorSpace,this.renderTarget=t.renderTarget,this.isRenderTargetTexture=t.isRenderTargetTexture,this.isArrayTexture=t.isArrayTexture,this.userData=JSON.parse(JSON.stringify(t.userData)),this.needsUpdate=!0,this}setValues(t){for(let e in t){let n=t[e];if(n===void 0){tt(`Texture.setValues(): parameter '${e}' has value of undefined.`);continue}let i=this[e];if(i===void 0){tt(`Texture.setValues(): property '${e}' does not exist.`);continue}i&&n&&i.isVector2&&n.isVector2||i&&n&&i.isVector3&&n.isVector3||i&&n&&i.isMatrix3&&n.isMatrix3?i.copy(n):this[e]=n}}toJSON(t){let e=t===void 0||typeof t=="string";if(!e&&t.textures[this.uuid]!==void 0)return t.textures[this.uuid];let n={metadata:{version:4.7,type:"Texture",generator:"Texture.toJSON"},uuid:this.uuid,name:this.name,image:this.source.toJSON(t).uuid,mapping:this.mapping,channel:this.channel,repeat:[this.repeat.x,this.repeat.y],offset:[this.offset.x,this.offset.y],center:[this.center.x,this.center.y],rotation:this.rotation,wrap:[this.wrapS,this.wrapT],format:this.format,internalFormat:this.internalFormat,type:this.type,normalized:this.normalized,colorSpace:this.colorSpace,minFilter:this.minFilter,magFilter:this.magFilter,anisotropy:this.anisotropy,flipY:this.flipY,generateMipmaps:this.generateMipmaps,premultiplyAlpha:this.premultiplyAlpha,unpackAlignment:this.unpackAlignment};return Object.keys(this.userData).length>0&&(n.userData=this.userData),e||(t.textures[this.uuid]=n),n}dispose(){this.dispatchEvent({type:"dispose"})}transformUv(t){if(this.mapping!==Kn)return t;if(t.applyMatrix3(this.matrix),t.x<0||t.x>1)switch(this.wrapS){case Cn:t.x=t.x-Math.floor(t.x);break;case le:t.x=t.x<0?0:1;break;case Rn:Math.abs(Math.floor(t.x)%2)===1?t.x=Math.ceil(t.x)-t.x:t.x=t.x-Math.floor(t.x);break}if(t.y<0||t.y>1)switch(this.wrapT){case Cn:t.y=t.y-Math.floor(t.y);break;case le:t.y=t.y<0?0:1;break;case Rn:Math.abs(Math.floor(t.y)%2)===1?t.y=Math.ceil(t.y)-t.y:t.y=t.y-Math.floor(t.y);break}return this.flipY&&(t.y=1-t.y),t}set needsUpdate(t){t===!0&&(this.version++,this.source.needsUpdate=!0)}set needsPMREMUpdate(t){t===!0&&this.pmremVersion++}};Zt.DEFAULT_IMAGE=null;Zt.DEFAULT_MAPPING=Kn;Zt.DEFAULT_ANISOTROPY=1;var Bn=class s{static{d(this,"Vector4")}static{s.prototype.isVector4=!0}constructor(t=0,e=0,n=0,i=1){this.x=t,this.y=e,this.z=n,this.w=i}get width(){return this.z}set width(t){this.z=t}get height(){return this.w}set height(t){this.w=t}set(t,e,n,i){return this.x=t,this.y=e,this.z=n,this.w=i,this}setScalar(t){return this.x=t,this.y=t,this.z=t,this.w=t,this}setX(t){return this.x=t,this}setY(t){return this.y=t,this}setZ(t){return this.z=t,this}setW(t){return this.w=t,this}setComponent(t,e){switch(t){case 0:this.x=e;break;case 1:this.y=e;break;case 2:this.z=e;break;case 3:this.w=e;break;default:throw new Error("THREE.Vector4: index is out of range: "+t)}return this}getComponent(t){switch(t){case 0:return this.x;case 1:return this.y;case 2:return this.z;case 3:return this.w;default:throw new Error("THREE.Vector4: index is out of range: "+t)}}clone(){return new this.constructor(this.x,this.y,this.z,this.w)}copy(t){return this.x=t.x,this.y=t.y,this.z=t.z,this.w=t.w!==void 0?t.w:1,this}add(t){return this.x+=t.x,this.y+=t.y,this.z+=t.z,this.w+=t.w,this}addScalar(t){return this.x+=t,this.y+=t,this.z+=t,this.w+=t,this}addVectors(t,e){return this.x=t.x+e.x,this.y=t.y+e.y,this.z=t.z+e.z,this.w=t.w+e.w,this}addScaledVector(t,e){return this.x+=t.x*e,this.y+=t.y*e,this.z+=t.z*e,this.w+=t.w*e,this}sub(t){return this.x-=t.x,this.y-=t.y,this.z-=t.z,this.w-=t.w,this}subScalar(t){return this.x-=t,this.y-=t,this.z-=t,this.w-=t,this}subVectors(t,e){return this.x=t.x-e.x,this.y=t.y-e.y,this.z=t.z-e.z,this.w=t.w-e.w,this}multiply(t){return this.x*=t.x,this.y*=t.y,this.z*=t.z,this.w*=t.w,this}multiplyScalar(t){return this.x*=t,this.y*=t,this.z*=t,this.w*=t,this}applyMatrix4(t){let e=this.x,n=this.y,i=this.z,r=this.w,o=t.elements;return this.x=o[0]*e+o[4]*n+o[8]*i+o[12]*r,this.y=o[1]*e+o[5]*n+o[9]*i+o[13]*r,this.z=o[2]*e+o[6]*n+o[10]*i+o[14]*r,this.w=o[3]*e+o[7]*n+o[11]*i+o[15]*r,this}divide(t){return this.x/=t.x,this.y/=t.y,this.z/=t.z,this.w/=t.w,this}divideScalar(t){return this.multiplyScalar(1/t)}setAxisAngleFromQuaternion(t){this.w=2*Math.acos(t.w);let e=Math.sqrt(1-t.w*t.w);return e<1e-4?(this.x=1,this.y=0,this.z=0):(this.x=t.x/e,this.y=t.y/e,this.z=t.z/e),this}setAxisAngleFromRotationMatrix(t){let e,n,i,r,c=t.elements,l=c[0],u=c[4],h=c[8],f=c[1],m=c[5],p=c[9],_=c[2],x=c[6],g=c[10];if(Math.abs(u-f)<.01&&Math.abs(h-_)<.01&&Math.abs(p-x)<.01){if(Math.abs(u+f)<.1&&Math.abs(h+_)<.1&&Math.abs(p+x)<.1&&Math.abs(l+m+g-3)<.1)return this.set(1,0,0,0),this;e=Math.PI;let y=(l+1)/2,v=(m+1)/2,b=(g+1)/2,A=(u+f)/4,R=(h+_)/4,z=(p+x)/4;return y>v&&y>b?y<.01?(n=0,i=.707106781,r=.707106781):(n=Math.sqrt(y),i=A/n,r=R/n):v>b?v<.01?(n=.707106781,i=0,r=.707106781):(i=Math.sqrt(v),n=A/i,r=z/i):b<.01?(n=.707106781,i=.707106781,r=0):(r=Math.sqrt(b),n=R/r,i=z/r),this.set(n,i,r,e),this}let M=Math.sqrt((x-p)*(x-p)+(h-_)*(h-_)+(f-u)*(f-u));return Math.abs(M)<.001&&(M=1),this.x=(x-p)/M,this.y=(h-_)/M,this.z=(f-u)/M,this.w=Math.acos((l+m+g-1)/2),this}setFromMatrixPosition(t){let e=t.elements;return this.x=e[12],this.y=e[13],this.z=e[14],this.w=e[15],this}min(t){return this.x=Math.min(this.x,t.x),this.y=Math.min(this.y,t.y),this.z=Math.min(this.z,t.z),this.w=Math.min(this.w,t.w),this}max(t){return this.x=Math.max(this.x,t.x),this.y=Math.max(this.y,t.y),this.z=Math.max(this.z,t.z),this.w=Math.max(this.w,t.w),this}clamp(t,e){return this.x=F(this.x,t.x,e.x),this.y=F(this.y,t.y,e.y),this.z=F(this.z,t.z,e.z),this.w=F(this.w,t.w,e.w),this}clampScalar(t,e){return this.x=F(this.x,t,e),this.y=F(this.y,t,e),this.z=F(this.z,t,e),this.w=F(this.w,t,e),this}clampLength(t,e){let n=this.length();return this.divideScalar(n||1).multiplyScalar(F(n,t,e))}floor(){return this.x=Math.floor(this.x),this.y=Math.floor(this.y),this.z=Math.floor(this.z),this.w=Math.floor(this.w),this}ceil(){return this.x=Math.ceil(this.x),this.y=Math.ceil(this.y),this.z=Math.ceil(this.z),this.w=Math.ceil(this.w),this}round(){return this.x=Math.round(this.x),this.y=Math.round(this.y),this.z=Math.round(this.z),this.w=Math.round(this.w),this}roundToZero(){return this.x=Math.trunc(this.x),this.y=Math.trunc(this.y),this.z=Math.trunc(this.z),this.w=Math.trunc(this.w),this}negate(){return this.x=-this.x,this.y=-this.y,this.z=-this.z,this.w=-this.w,this}dot(t){return this.x*t.x+this.y*t.y+this.z*t.z+this.w*t.w}lengthSq(){return this.x*this.x+this.y*this.y+this.z*this.z+this.w*this.w}length(){return Math.sqrt(this.x*this.x+this.y*this.y+this.z*this.z+this.w*this.w)}manhattanLength(){return Math.abs(this.x)+Math.abs(this.y)+Math.abs(this.z)+Math.abs(this.w)}normalize(){return this.divideScalar(this.length()||1)}setLength(t){return this.normalize().multiplyScalar(t)}lerp(t,e){return this.x+=(t.x-this.x)*e,this.y+=(t.y-this.y)*e,this.z+=(t.z-this.z)*e,this.w+=(t.w-this.w)*e,this}lerpVectors(t,e,n){return this.x=t.x+(e.x-t.x)*n,this.y=t.y+(e.y-t.y)*n,this.z=t.z+(e.z-t.z)*n,this.w=t.w+(e.w-t.w)*n,this}equals(t){return t.x===this.x&&t.y===this.y&&t.z===this.z&&t.w===this.w}fromArray(t,e=0){return this.x=t[e],this.y=t[e+1],this.z=t[e+2],this.w=t[e+3],this}toArray(t=[],e=0){return t[e]=this.x,t[e+1]=this.y,t[e+2]=this.z,t[e+3]=this.w,t}fromBufferAttribute(t,e){return this.x=t.getX(e),this.y=t.getY(e),this.z=t.getZ(e),this.w=t.getW(e),this}random(){return this.x=Math.random(),this.y=Math.random(),this.z=Math.random(),this.w=Math.random(),this}*[Symbol.iterator](){yield this.x,yield this.y,yield this.z,yield this.w}};var W=class s{static{d(this,"Matrix4")}static{s.prototype.isMatrix4=!0}constructor(t,e,n,i,r,o,a,c,l,u,h,f,m,p,_,x){this.elements=[1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1],t!==void 0&&this.set(t,e,n,i,r,o,a,c,l,u,h,f,m,p,_,x)}set(t,e,n,i,r,o,a,c,l,u,h,f,m,p,_,x){let g=this.elements;return g[0]=t,g[4]=e,g[8]=n,g[12]=i,g[1]=r,g[5]=o,g[9]=a,g[13]=c,g[2]=l,g[6]=u,g[10]=h,g[14]=f,g[3]=m,g[7]=p,g[11]=_,g[15]=x,this}identity(){return this.set(1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1),this}clone(){return new s().fromArray(this.elements)}copy(t){let e=this.elements,n=t.elements;return e[0]=n[0],e[1]=n[1],e[2]=n[2],e[3]=n[3],e[4]=n[4],e[5]=n[5],e[6]=n[6],e[7]=n[7],e[8]=n[8],e[9]=n[9],e[10]=n[10],e[11]=n[11],e[12]=n[12],e[13]=n[13],e[14]=n[14],e[15]=n[15],this}copyPosition(t){let e=this.elements,n=t.elements;return e[12]=n[12],e[13]=n[13],e[14]=n[14],this}setFromMatrix3(t){let e=t.elements;return this.set(e[0],e[3],e[6],0,e[1],e[4],e[7],0,e[2],e[5],e[8],0,0,0,0,1),this}extractBasis(t,e,n){return this.determinantAffine()===0?(t.set(1,0,0),e.set(0,1,0),n.set(0,0,1),this):(t.setFromMatrixColumn(this,0),e.setFromMatrixColumn(this,1),n.setFromMatrixColumn(this,2),this)}makeBasis(t,e,n){return this.set(t.x,e.x,n.x,0,t.y,e.y,n.y,0,t.z,e.z,n.z,0,0,0,0,1),this}extractRotation(t){if(t.determinantAffine()===0)return this.identity();let e=this.elements,n=t.elements,i=1/Ht.setFromMatrixColumn(t,0).length(),r=1/Ht.setFromMatrixColumn(t,1).length(),o=1/Ht.setFromMatrixColumn(t,2).length();return e[0]=n[0]*i,e[1]=n[1]*i,e[2]=n[2]*i,e[3]=0,e[4]=n[4]*r,e[5]=n[5]*r,e[6]=n[6]*r,e[7]=0,e[8]=n[8]*o,e[9]=n[9]*o,e[10]=n[10]*o,e[11]=0,e[12]=0,e[13]=0,e[14]=0,e[15]=1,this}makeRotationFromEuler(t){let e=this.elements,n=t.x,i=t.y,r=t.z,o=Math.cos(n),a=Math.sin(n),c=Math.cos(i),l=Math.sin(i),u=Math.cos(r),h=Math.sin(r);if(t.order==="XYZ"){let f=o*u,m=o*h,p=a*u,_=a*h;e[0]=c*u,e[4]=-c*h,e[8]=l,e[1]=m+p*l,e[5]=f-_*l,e[9]=-a*c,e[2]=_-f*l,e[6]=p+m*l,e[10]=o*c}else if(t.order==="YXZ"){let f=c*u,m=c*h,p=l*u,_=l*h;e[0]=f+_*a,e[4]=p*a-m,e[8]=o*l,e[1]=o*h,e[5]=o*u,e[9]=-a,e[2]=m*a-p,e[6]=_+f*a,e[10]=o*c}else if(t.order==="ZXY"){let f=c*u,m=c*h,p=l*u,_=l*h;e[0]=f-_*a,e[4]=-o*h,e[8]=p+m*a,e[1]=m+p*a,e[5]=o*u,e[9]=_-f*a,e[2]=-o*l,e[6]=a,e[10]=o*c}else if(t.order==="ZYX"){let f=o*u,m=o*h,p=a*u,_=a*h;e[0]=c*u,e[4]=p*l-m,e[8]=f*l+_,e[1]=c*h,e[5]=_*l+f,e[9]=m*l-p,e[2]=-l,e[6]=a*c,e[10]=o*c}else if(t.order==="YZX"){let f=o*c,m=o*l,p=a*c,_=a*l;e[0]=c*u,e[4]=_-f*h,e[8]=p*h+m,e[1]=h,e[5]=o*u,e[9]=-a*u,e[2]=-l*u,e[6]=m*h+p,e[10]=f-_*h}else if(t.order==="XZY"){let f=o*c,m=o*l,p=a*c,_=a*l;e[0]=c*u,e[4]=-h,e[8]=l*u,e[1]=f*h+_,e[5]=o*u,e[9]=m*h-p,e[2]=p*h-m,e[6]=a*u,e[10]=_*h+f}return e[3]=0,e[7]=0,e[11]=0,e[12]=0,e[13]=0,e[14]=0,e[15]=1,this}makeRotationFromQuaternion(t){return this.compose(to,t,eo)}lookAt(t,e,n){let i=this.elements;return rt.subVectors(t,e),rt.lengthSq()===0&&(rt.z=1),rt.normalize(),bt.crossVectors(n,rt),bt.lengthSq()===0&&(Math.abs(n.z)===1?rt.x+=1e-4:rt.z+=1e-4,rt.normalize(),bt.crossVectors(n,rt)),bt.normalize(),Ie.crossVectors(rt,bt),i[0]=bt.x,i[4]=Ie.x,i[8]=rt.x,i[1]=bt.y,i[5]=Ie.y,i[9]=rt.y,i[2]=bt.z,i[6]=Ie.z,i[10]=rt.z,this}multiply(t){return this.multiplyMatrices(this,t)}premultiply(t){return this.multiplyMatrices(t,this)}multiplyMatrices(t,e){let n=t.elements,i=e.elements,r=this.elements,o=n[0],a=n[4],c=n[8],l=n[12],u=n[1],h=n[5],f=n[9],m=n[13],p=n[2],_=n[6],x=n[10],g=n[14],M=n[3],y=n[7],v=n[11],b=n[15],A=i[0],R=i[4],z=i[8],w=i[12],N=i[1],k=i[5],G=i[9],q=i[13],Y=i[2],V=i[6],S=i[10],C=i[14],I=i[3],P=i[7],B=i[11],st=i[15];return r[0]=o*A+a*N+c*Y+l*I,r[4]=o*R+a*k+c*V+l*P,r[8]=o*z+a*G+c*S+l*B,r[12]=o*w+a*q+c*C+l*st,r[1]=u*A+h*N+f*Y+m*I,r[5]=u*R+h*k+f*V+m*P,r[9]=u*z+h*G+f*S+m*B,r[13]=u*w+h*q+f*C+m*st,r[2]=p*A+_*N+x*Y+g*I,r[6]=p*R+_*k+x*V+g*P,r[10]=p*z+_*G+x*S+g*B,r[14]=p*w+_*q+x*C+g*st,r[3]=M*A+y*N+v*Y+b*I,r[7]=M*R+y*k+v*V+b*P,r[11]=M*z+y*G+v*S+b*B,r[15]=M*w+y*q+v*C+b*st,this}multiplyScalar(t){let e=this.elements;return e[0]*=t,e[4]*=t,e[8]*=t,e[12]*=t,e[1]*=t,e[5]*=t,e[9]*=t,e[13]*=t,e[2]*=t,e[6]*=t,e[10]*=t,e[14]*=t,e[3]*=t,e[7]*=t,e[11]*=t,e[15]*=t,this}determinant(){let t=this.elements,e=t[0],n=t[4],i=t[8],r=t[12],o=t[1],a=t[5],c=t[9],l=t[13],u=t[2],h=t[6],f=t[10],m=t[14],p=t[3],_=t[7],x=t[11],g=t[15],M=c*m-l*f,y=a*m-l*h,v=a*f-c*h,b=o*m-l*u,A=o*f-c*u,R=o*h-a*u;return e*(_*M-x*y+g*v)-n*(p*M-x*b+g*A)+i*(p*y-_*b+g*R)-r*(p*v-_*A+x*R)}determinantAffine(){let t=this.elements,e=t[0],n=t[4],i=t[8],r=t[1],o=t[5],a=t[9],c=t[2],l=t[6],u=t[10];return e*(o*u-a*l)-n*(r*u-a*c)+i*(r*l-o*c)}transpose(){let t=this.elements,e;return e=t[1],t[1]=t[4],t[4]=e,e=t[2],t[2]=t[8],t[8]=e,e=t[6],t[6]=t[9],t[9]=e,e=t[3],t[3]=t[12],t[12]=e,e=t[7],t[7]=t[13],t[13]=e,e=t[11],t[11]=t[14],t[14]=e,this}setPosition(t,e,n){let i=this.elements;return t.isVector3?(i[12]=t.x,i[13]=t.y,i[14]=t.z):(i[12]=t,i[13]=e,i[14]=n),this}invert(){let t=this.elements,e=t[0],n=t[1],i=t[2],r=t[3],o=t[4],a=t[5],c=t[6],l=t[7],u=t[8],h=t[9],f=t[10],m=t[11],p=t[12],_=t[13],x=t[14],g=t[15],M=e*a-n*o,y=e*c-i*o,v=e*l-r*o,b=n*c-i*a,A=n*l-r*a,R=i*l-r*c,z=u*_-h*p,w=u*x-f*p,N=u*g-m*p,k=h*x-f*_,G=h*g-m*_,q=f*g-m*x,Y=M*q-y*G+v*k+b*N-A*w+R*z;if(Y===0)return this.set(0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0);let V=1/Y;return t[0]=(a*q-c*G+l*k)*V,t[1]=(i*G-n*q-r*k)*V,t[2]=(_*R-x*A+g*b)*V,t[3]=(f*A-h*R-m*b)*V,t[4]=(c*N-o*q-l*w)*V,t[5]=(e*q-i*N+r*w)*V,t[6]=(x*v-p*R-g*y)*V,t[7]=(u*R-f*v+m*y)*V,t[8]=(o*G-a*N+l*z)*V,t[9]=(n*N-e*G-r*z)*V,t[10]=(p*A-_*v+g*M)*V,t[11]=(h*v-u*A-m*M)*V,t[12]=(a*w-o*k-c*z)*V,t[13]=(e*k-n*w+i*z)*V,t[14]=(_*y-p*b-x*M)*V,t[15]=(u*b-h*y+f*M)*V,this}scale(t){let e=this.elements,n=t.x,i=t.y,r=t.z;return e[0]*=n,e[4]*=i,e[8]*=r,e[1]*=n,e[5]*=i,e[9]*=r,e[2]*=n,e[6]*=i,e[10]*=r,e[3]*=n,e[7]*=i,e[11]*=r,this}getMaxScaleOnAxis(){let t=this.elements,e=t[0]*t[0]+t[1]*t[1]+t[2]*t[2],n=t[4]*t[4]+t[5]*t[5]+t[6]*t[6],i=t[8]*t[8]+t[9]*t[9]+t[10]*t[10];return Math.sqrt(Math.max(e,n,i))}makeTranslation(t,e,n){return t.isVector3?this.set(1,0,0,t.x,0,1,0,t.y,0,0,1,t.z,0,0,0,1):this.set(1,0,0,t,0,1,0,e,0,0,1,n,0,0,0,1),this}makeRotationX(t){let e=Math.cos(t),n=Math.sin(t);return this.set(1,0,0,0,0,e,-n,0,0,n,e,0,0,0,0,1),this}makeRotationY(t){let e=Math.cos(t),n=Math.sin(t);return this.set(e,0,n,0,0,1,0,0,-n,0,e,0,0,0,0,1),this}makeRotationZ(t){let e=Math.cos(t),n=Math.sin(t);return this.set(e,-n,0,0,n,e,0,0,0,0,1,0,0,0,0,1),this}makeRotationAxis(t,e){let n=Math.cos(e),i=Math.sin(e),r=1-n,o=t.x,a=t.y,c=t.z,l=r*o,u=r*a;return this.set(l*o+n,l*a-i*c,l*c+i*a,0,l*a+i*c,u*a+n,u*c-i*o,0,l*c-i*a,u*c+i*o,r*c*c+n,0,0,0,0,1),this}makeScale(t,e,n){return this.set(t,0,0,0,0,e,0,0,0,0,n,0,0,0,0,1),this}makeShear(t,e,n,i,r,o){return this.set(1,n,r,0,t,1,o,0,e,i,1,0,0,0,0,1),this}compose(t,e,n){let i=this.elements,r=e._x,o=e._y,a=e._z,c=e._w,l=r+r,u=o+o,h=a+a,f=r*l,m=r*u,p=r*h,_=o*u,x=o*h,g=a*h,M=c*l,y=c*u,v=c*h,b=n.x,A=n.y,R=n.z;return i[0]=(1-(_+g))*b,i[1]=(m+v)*b,i[2]=(p-y)*b,i[3]=0,i[4]=(m-v)*A,i[5]=(1-(f+g))*A,i[6]=(x+M)*A,i[7]=0,i[8]=(p+y)*R,i[9]=(x-M)*R,i[10]=(1-(f+_))*R,i[11]=0,i[12]=t.x,i[13]=t.y,i[14]=t.z,i[15]=1,this}decompose(t,e,n){let i=this.elements;t.x=i[12],t.y=i[13],t.z=i[14];let r=this.determinantAffine();if(r===0)return n.set(1,1,1),e.identity(),this;let o=Ht.set(i[0],i[1],i[2]).length(),a=Ht.set(i[4],i[5],i[6]).length(),c=Ht.set(i[8],i[9],i[10]).length();r<0&&(o=-o),ft.copy(this);let l=1/o,u=1/a,h=1/c;return ft.elements[0]*=l,ft.elements[1]*=l,ft.elements[2]*=l,ft.elements[4]*=u,ft.elements[5]*=u,ft.elements[6]*=u,ft.elements[8]*=h,ft.elements[9]*=h,ft.elements[10]*=h,e.setFromRotationMatrix(ft),n.x=o,n.y=a,n.z=c,this}makePerspective(t,e,n,i,r,o,a=he,c=!1){let l=this.elements,u=2*r/(e-t),h=2*r/(n-i),f=(e+t)/(e-t),m=(n+i)/(n-i),p,_;if(c)p=r/(o-r),_=o*r/(o-r);else if(a===he)p=-(o+r)/(o-r),_=-2*o*r/(o-r);else if(a===Fn)p=-o/(o-r),_=-o*r/(o-r);else throw new Error("THREE.Matrix4.makePerspective(): Invalid coordinate system: "+a);return l[0]=u,l[4]=0,l[8]=f,l[12]=0,l[1]=0,l[5]=h,l[9]=m,l[13]=0,l[2]=0,l[6]=0,l[10]=p,l[14]=_,l[3]=0,l[7]=0,l[11]=-1,l[15]=0,this}makeOrthographic(t,e,n,i,r,o,a=he,c=!1){let l=this.elements,u=2/(e-t),h=2/(n-i),f=-(e+t)/(e-t),m=-(n+i)/(n-i),p,_;if(c)p=1/(o-r),_=o/(o-r);else if(a===he)p=-2/(o-r),_=-(o+r)/(o-r);else if(a===Fn)p=-1/(o-r),_=-r/(o-r);else throw new Error("THREE.Matrix4.makeOrthographic(): Invalid coordinate system: "+a);return l[0]=u,l[4]=0,l[8]=0,l[12]=f,l[1]=0,l[5]=h,l[9]=0,l[13]=m,l[2]=0,l[6]=0,l[10]=p,l[14]=_,l[3]=0,l[7]=0,l[11]=0,l[15]=1,this}equals(t){let e=this.elements,n=t.elements;for(let i=0;i<16;i++)if(e[i]!==n[i])return!1;return!0}fromArray(t,e=0){for(let n=0;n<16;n++)this.elements[n]=t[n+e];return this}toArray(t=[],e=0){let n=this.elements;return t[e]=n[0],t[e+1]=n[1],t[e+2]=n[2],t[e+3]=n[3],t[e+4]=n[4],t[e+5]=n[5],t[e+6]=n[6],t[e+7]=n[7],t[e+8]=n[8],t[e+9]=n[9],t[e+10]=n[10],t[e+11]=n[11],t[e+12]=n[12],t[e+13]=n[13],t[e+14]=n[14],t[e+15]=n[15],t}},Ht=new D,ft=new W,to=new D(0,0,0),eo=new D(1,1,1),bt=new D,Ie=new D,rt=new D,Ni=new W,Di=new _t,pe=class s{static{d(this,"Euler")}constructor(t=0,e=0,n=0,i=s.DEFAULT_ORDER){this.isEuler=!0,this._x=t,this._y=e,this._z=n,this._order=i}get x(){return this._x}set x(t){this._x=t,this._onChangeCallback()}get y(){return this._y}set y(t){this._y=t,this._onChangeCallback()}get z(){return this._z}set z(t){this._z=t,this._onChangeCallback()}get order(){return this._order}set order(t){this._order=t,this._onChangeCallback()}set(t,e,n,i=this._order){return this._x=t,this._y=e,this._z=n,this._order=i,this._onChangeCallback(),this}clone(){return new this.constructor(this._x,this._y,this._z,this._order)}copy(t){return this._x=t._x,this._y=t._y,this._z=t._z,this._order=t._order,this._onChangeCallback(),this}setFromRotationMatrix(t,e=this._order,n=!0){let i=t.elements,r=i[0],o=i[4],a=i[8],c=i[1],l=i[5],u=i[9],h=i[2],f=i[6],m=i[10];switch(e){case"XYZ":this._y=Math.asin(F(a,-1,1)),Math.abs(a)<.9999999?(this._x=Math.atan2(-u,m),this._z=Math.atan2(-o,r)):(this._x=Math.atan2(f,l),this._z=0);break;case"YXZ":this._x=Math.asin(-F(u,-1,1)),Math.abs(u)<.9999999?(this._y=Math.atan2(a,m),this._z=Math.atan2(c,l)):(this._y=Math.atan2(-h,r),this._z=0);break;case"ZXY":this._x=Math.asin(F(f,-1,1)),Math.abs(f)<.9999999?(this._y=Math.atan2(-h,m),this._z=Math.atan2(-o,l)):(this._y=0,this._z=Math.atan2(c,r));break;case"ZYX":this._y=Math.asin(-F(h,-1,1)),Math.abs(h)<.9999999?(this._x=Math.atan2(f,m),this._z=Math.atan2(c,r)):(this._x=0,this._z=Math.atan2(-o,l));break;case"YZX":this._z=Math.asin(F(c,-1,1)),Math.abs(c)<.9999999?(this._x=Math.atan2(-u,l),this._y=Math.atan2(-h,r)):(this._x=0,this._y=Math.atan2(a,m));break;case"XZY":this._z=Math.asin(-F(o,-1,1)),Math.abs(o)<.9999999?(this._x=Math.atan2(f,l),this._y=Math.atan2(a,r)):(this._x=Math.atan2(-u,m),this._y=0);break;default:tt("Euler: .setFromRotationMatrix() encountered an unknown order: "+e)}return this._order=e,n===!0&&this._onChangeCallback(),this}setFromQuaternion(t,e,n){return Ni.makeRotationFromQuaternion(t),this.setFromRotationMatrix(Ni,e,n)}setFromVector3(t,e=this._order){return this.set(t.x,t.y,t.z,e)}reorder(t){return Di.setFromEuler(this),this.setFromQuaternion(Di,t)}equals(t){return t._x===this._x&&t._y===this._y&&t._z===this._z&&t._order===this._order}fromArray(t){return this._x=t[0],this._y=t[1],this._z=t[2],t[3]!==void 0&&(this._order=t[3]),this._onChangeCallback(),this}toArray(t=[],e=0){return t[e]=this._x,t[e+1]=this._y,t[e+2]=this._z,t[e+3]=this._order,t}_onChange(t){return this._onChangeCallback=t,this}_onChangeCallback(){}*[Symbol.iterator](){yield this._x,yield this._y,yield this._z,yield this._order}};pe.DEFAULT_ORDER="XYZ";var ke=class{static{d(this,"Layers")}constructor(){this.mask=1}set(t){this.mask=(1<<t|0)>>>0}enable(t){this.mask|=1<<t|0}enableAll(){this.mask=-1}toggle(t){this.mask^=1<<t|0}disable(t){this.mask&=~(1<<t|0)}disableAll(){this.mask=0}test(t){return(this.mask&t.mask)!==0}isEnabled(t){return(this.mask&(1<<t|0))!==0}},no=0,Ui=new D,Wt=new _t,mt=new W,Pe=new D,ce=new D,io=new D,so=new _t,Fi=new D(1,0,0),Oi=new D(0,1,0),Bi=new D(0,0,1),zi={type:"added"},ro={type:"removed"},Xt={type:"childadded",child:null},_n={type:"childremoved",child:null},Jt=class s extends fe{static{d(this,"Object3D")}constructor(){super(),this.isObject3D=!0,Object.defineProperty(this,"id",{value:no++}),this.uuid=ti(),this.name="",this.type="Object3D",this.parent=null,this.children=[],this.up=s.DEFAULT_UP.clone();let t=new D,e=new pe,n=new _t,i=new D(1,1,1);function r(){n.setFromEuler(e,!1)}d(r,"onRotationChange");function o(){e.setFromQuaternion(n,void 0,!1)}d(o,"onQuaternionChange"),e._onChange(r),n._onChange(o),Object.defineProperties(this,{position:{configurable:!0,enumerable:!0,value:t},rotation:{configurable:!0,enumerable:!0,value:e},quaternion:{configurable:!0,enumerable:!0,value:n},scale:{configurable:!0,enumerable:!0,value:i},modelViewMatrix:{value:new W},normalMatrix:{value:new L}}),this.matrix=new W,this.matrixWorld=new W,this.matrixAutoUpdate=s.DEFAULT_MATRIX_AUTO_UPDATE,this.matrixWorldAutoUpdate=s.DEFAULT_MATRIX_WORLD_AUTO_UPDATE,this.matrixWorldNeedsUpdate=!1,this.layers=new ke,this.visible=!0,this.castShadow=!1,this.receiveShadow=!1,this.frustumCulled=!0,this.renderOrder=0,this.animations=[],this.customDepthMaterial=void 0,this.customDistanceMaterial=void 0,this.static=!1,this.userData={},this.pivot=null}onBeforeShadow(){}onAfterShadow(){}onBeforeRender(){}onAfterRender(){}applyMatrix4(t){this.matrixAutoUpdate&&this.updateMatrix(),this.matrix.premultiply(t),this.matrix.decompose(this.position,this.quaternion,this.scale)}applyQuaternion(t){return this.quaternion.premultiply(t),this}setRotationFromAxisAngle(t,e){this.quaternion.setFromAxisAngle(t,e)}setRotationFromEuler(t){this.quaternion.setFromEuler(t,!0)}setRotationFromMatrix(t){this.quaternion.setFromRotationMatrix(t)}setRotationFromQuaternion(t){this.quaternion.copy(t)}rotateOnAxis(t,e){return Wt.setFromAxisAngle(t,e),this.quaternion.multiply(Wt),this}rotateOnWorldAxis(t,e){return Wt.setFromAxisAngle(t,e),this.quaternion.premultiply(Wt),this}rotateX(t){return this.rotateOnAxis(Fi,t)}rotateY(t){return this.rotateOnAxis(Oi,t)}rotateZ(t){return this.rotateOnAxis(Bi,t)}translateOnAxis(t,e){return Ui.copy(t).applyQuaternion(this.quaternion),this.position.add(Ui.multiplyScalar(e)),this}translateX(t){return this.translateOnAxis(Fi,t)}translateY(t){return this.translateOnAxis(Oi,t)}translateZ(t){return this.translateOnAxis(Bi,t)}localToWorld(t){return this.updateWorldMatrix(!0,!1),t.applyMatrix4(this.matrixWorld)}worldToLocal(t){return this.updateWorldMatrix(!0,!1),t.applyMatrix4(mt.copy(this.matrixWorld).invert())}lookAt(t,e,n){t.isVector3?Pe.copy(t):Pe.set(t,e,n);let i=this.parent;this.updateWorldMatrix(!0,!1),ce.setFromMatrixPosition(this.matrixWorld),this.isCamera||this.isLight?mt.lookAt(ce,Pe,this.up):mt.lookAt(Pe,ce,this.up),this.quaternion.setFromRotationMatrix(mt),i&&(mt.extractRotation(i.matrixWorld),Wt.setFromRotationMatrix(mt),this.quaternion.premultiply(Wt.invert()))}add(t){if(arguments.length>1){for(let e=0;e<arguments.length;e++)this.add(arguments[e]);return this}return t===this?($("Object3D.add: object can't be added as a child of itself.",t),this):(t&&t.isObject3D?(t.removeFromParent(),t.parent=this,this.children.push(t),t.dispatchEvent(zi),Xt.child=t,this.dispatchEvent(Xt),Xt.child=null):$("Object3D.add: object not an instance of THREE.Object3D.",t),this)}remove(t){if(arguments.length>1){for(let n=0;n<arguments.length;n++)this.remove(arguments[n]);return this}let e=this.children.indexOf(t);return e!==-1&&(t.parent=null,this.children.splice(e,1),t.dispatchEvent(ro),_n.child=t,this.dispatchEvent(_n),_n.child=null),this}removeFromParent(){let t=this.parent;return t!==null&&t.remove(this),this}clear(){return this.remove(...this.children)}attach(t){return this.updateWorldMatrix(!0,!1),mt.copy(this.matrixWorld).invert(),t.parent!==null&&(t.parent.updateWorldMatrix(!0,!1),mt.multiply(t.parent.matrixWorld)),t.applyMatrix4(mt),t.removeFromParent(),t.parent=this,this.children.push(t),t.updateWorldMatrix(!1,!0),t.dispatchEvent(zi),Xt.child=t,this.dispatchEvent(Xt),Xt.child=null,this}getObjectById(t){return this.getObjectByProperty("id",t)}getObjectByName(t){return this.getObjectByProperty("name",t)}getObjectByProperty(t,e){if(this[t]===e)return this;for(let n=0,i=this.children.length;n<i;n++){let o=this.children[n].getObjectByProperty(t,e);if(o!==void 0)return o}}getObjectsByProperty(t,e,n=[]){this[t]===e&&n.push(this);let i=this.children;for(let r=0,o=i.length;r<o;r++)i[r].getObjectsByProperty(t,e,n);return n}getWorldPosition(t){return this.updateWorldMatrix(!0,!1),t.setFromMatrixPosition(this.matrixWorld)}getWorldQuaternion(t){return this.updateWorldMatrix(!0,!1),this.matrixWorld.decompose(ce,t,io),t}getWorldScale(t){return this.updateWorldMatrix(!0,!1),this.matrixWorld.decompose(ce,so,t),t}getWorldDirection(t){this.updateWorldMatrix(!0,!1);let e=this.matrixWorld.elements;return t.set(e[8],e[9],e[10]).normalize()}raycast(){}intersectsFrustum(){}traverse(t){t(this);let e=this.children;for(let n=0,i=e.length;n<i;n++)e[n].traverse(t)}traverseVisible(t){if(this.visible===!1)return;t(this);let e=this.children;for(let n=0,i=e.length;n<i;n++)e[n].traverseVisible(t)}traverseAncestors(t){let e=this.parent;e!==null&&(t(e),e.traverseAncestors(t))}updateMatrix(){this.matrix.compose(this.position,this.quaternion,this.scale);let t=this.pivot;if(t!==null){let e=t.x,n=t.y,i=t.z,r=this.matrix.elements;r[12]+=e-r[0]*e-r[4]*n-r[8]*i,r[13]+=n-r[1]*e-r[5]*n-r[9]*i,r[14]+=i-r[2]*e-r[6]*n-r[10]*i}this.matrixWorldNeedsUpdate=!0}updateMatrixWorld(t){this.matrixAutoUpdate&&this.updateMatrix(),(this.matrixWorldNeedsUpdate||t)&&(this.matrixWorldAutoUpdate===!0&&(this.parent===null?this.matrixWorld.copy(this.matrix):this.matrixWorld.multiplyMatrices(this.parent.matrixWorld,this.matrix)),this.matrixWorldNeedsUpdate=!1,t=!0);let e=this.children;for(let n=0,i=e.length;n<i;n++)e[n].updateMatrixWorld(t)}updateWorldMatrix(t,e,n=!1){let i=this.parent;if(t===!0&&i!==null&&i.updateWorldMatrix(!0,!1),this.matrixAutoUpdate&&this.updateMatrix(),(this.matrixWorldNeedsUpdate||n)&&(this.matrixWorldAutoUpdate===!0&&(this.parent===null?this.matrixWorld.copy(this.matrix):this.matrixWorld.multiplyMatrices(this.parent.matrixWorld,this.matrix)),this.matrixWorldNeedsUpdate=!1,n=!0),e===!0){let r=this.children;for(let o=0,a=r.length;o<a;o++)r[o].updateWorldMatrix(!1,!0,n)}}toJSON(t){let e=t===void 0||typeof t=="string",n={};e&&(t={geometries:{},materials:{},textures:{},images:{},shapes:{},skeletons:{},animations:{},nodes:{}},n.metadata={version:4.7,type:"Object",generator:"Object3D.toJSON"});let i={};i.uuid=this.uuid,i.type=this.type,i.name=this.name,i.castShadow=this.castShadow,i.receiveShadow=this.receiveShadow,i.visible=this.visible,i.frustumCulled=this.frustumCulled,i.renderOrder=this.renderOrder,i.static=this.static,i.matrixAutoUpdate=this.matrixAutoUpdate,Object.keys(this.userData).length>0&&(i.userData=this.userData),i.layers=this.layers.mask,i.matrix=this.matrix.toArray(),i.up=this.up.toArray(),this.pivot!==null&&(i.pivot=this.pivot.toArray()),this.morphTargetDictionary!==void 0&&(i.morphTargetDictionary=Object.assign({},this.morphTargetDictionary)),this.morphTargetInfluences!==void 0&&(i.morphTargetInfluences=this.morphTargetInfluences.slice()),this.isInstancedMesh&&(i.type="InstancedMesh",i.count=this.count,i.instanceMatrix=this.instanceMatrix.toJSON(),this.instanceColor!==null&&(i.instanceColor=this.instanceColor.toJSON())),this.isBatchedMesh&&(i.type="BatchedMesh",i.perObjectFrustumCulled=this.perObjectFrustumCulled,i.sortObjects=this.sortObjects,i.drawRanges=this._drawRanges,i.reservedRanges=this._reservedRanges,i.geometryInfo=this._geometryInfo.map(a=>({...a,boundingBox:a.boundingBox?a.boundingBox.toJSON():void 0,boundingSphere:a.boundingSphere?a.boundingSphere.toJSON():void 0})),i.instanceInfo=this._instanceInfo.map(a=>({...a})),i.availableInstanceIds=this._availableInstanceIds.slice(),i.availableGeometryIds=this._availableGeometryIds.slice(),i.nextIndexStart=this._nextIndexStart,i.nextVertexStart=this._nextVertexStart,i.geometryCount=this._geometryCount,i.maxInstanceCount=this._maxInstanceCount,i.maxVertexCount=this._maxVertexCount,i.maxIndexCount=this._maxIndexCount,i.geometryInitialized=this._geometryInitialized,i.matricesTexture=this._matricesTexture.toJSON(t),i.indirectTexture=this._indirectTexture.toJSON(t),this._colorsTexture!==null&&(i.colorsTexture=this._colorsTexture.toJSON(t)),this.boundingSphere!==null&&(i.boundingSphere=this.boundingSphere.toJSON()),this.boundingBox!==null&&(i.boundingBox=this.boundingBox.toJSON()));function r(a,c){return a[c.uuid]===void 0&&(a[c.uuid]=c.toJSON(t)),c.uuid}if(d(r,"serialize"),this.isScene)this.background&&(this.background.isColor?i.background=this.background.toJSON():this.background.isTexture&&(i.background=this.background.toJSON(t).uuid)),this.environment&&this.environment.isTexture&&this.environment.isRenderTargetTexture!==!0&&(i.environment=this.environment.toJSON(t).uuid);else if(this.isMesh||this.isLine||this.isPoints){i.geometry=r(t.geometries,this.geometry);let a=this.geometry.parameters;if(a!==void 0&&a.shapes!==void 0){let c=a.shapes;if(Array.isArray(c))for(let l=0,u=c.length;l<u;l++){let h=c[l];r(t.shapes,h)}else r(t.shapes,c)}}if(this.isSkinnedMesh&&(i.bindMode=this.bindMode,i.bindMatrix=this.bindMatrix.toArray(),this.skeleton!==void 0&&(r(t.skeletons,this.skeleton),i.skeleton=this.skeleton.uuid)),this.material!==void 0)if(Array.isArray(this.material)){let a=[];for(let c=0,l=this.material.length;c<l;c++)a.push(r(t.materials,this.material[c]));i.material=a}else i.material=r(t.materials,this.material);if(this.children.length>0){i.children=[];for(let a=0;a<this.children.length;a++)i.children.push(this.children[a].toJSON(t).object)}if(this.animations.length>0){i.animations=[];for(let a=0;a<this.animations.length;a++){let c=this.animations[a];i.animations.push(r(t.animations,c))}}if(e){let a=o(t.geometries),c=o(t.materials),l=o(t.textures),u=o(t.images),h=o(t.shapes),f=o(t.skeletons),m=o(t.animations),p=o(t.nodes);a.length>0&&(n.geometries=a),c.length>0&&(n.materials=c),l.length>0&&(n.textures=l),u.length>0&&(n.images=u),h.length>0&&(n.shapes=h),f.length>0&&(n.skeletons=f),m.length>0&&(n.animations=m),p.length>0&&(n.nodes=p)}return n.object=i,n;function o(a){let c=[];for(let l in a){let u=a[l];delete u.metadata,c.push(u)}return c}d(o,"extractFromCache")}clone(t){return new this.constructor().copy(this,t)}copy(t,e=!0){if(this.name=t.name,this.up.copy(t.up),this.position.copy(t.position),this.rotation.order=t.rotation.order,this.quaternion.copy(t.quaternion),this.scale.copy(t.scale),this.pivot=t.pivot!==null?t.pivot.clone():null,this.matrix.copy(t.matrix),this.matrixWorld.copy(t.matrixWorld),this.matrixAutoUpdate=t.matrixAutoUpdate,this.matrixWorldAutoUpdate=t.matrixWorldAutoUpdate,this.matrixWorldNeedsUpdate=t.matrixWorldNeedsUpdate,this.layers.mask=t.layers.mask,this.visible=t.visible,this.castShadow=t.castShadow,this.receiveShadow=t.receiveShadow,this.frustumCulled=t.frustumCulled,this.renderOrder=t.renderOrder,this.static=t.static,this.animations=t.animations.slice(),this.userData=JSON.parse(JSON.stringify(t.userData)),e===!0)for(let n=0;n<t.children.length;n++){let i=t.children[n];this.add(i.clone())}return this}dispose(){this.dispatchEvent({type:"dispose"})}};Jt.DEFAULT_UP=new D(0,1,0);Jt.DEFAULT_MATRIX_AUTO_UPDATE=!0;Jt.DEFAULT_MATRIX_WORLD_AUTO_UPDATE=!0;var is={aliceblue:15792383,antiquewhite:16444375,aqua:65535,aquamarine:8388564,azure:15794175,beige:16119260,bisque:16770244,black:0,blanchedalmond:16772045,blue:255,blueviolet:9055202,brown:10824234,burlywood:14596231,cadetblue:6266528,chartreuse:8388352,chocolate:13789470,coral:16744272,cornflowerblue:6591981,cornsilk:16775388,crimson:14423100,cyan:65535,darkblue:139,darkcyan:35723,darkgoldenrod:12092939,darkgray:11119017,darkgreen:25600,darkgrey:11119017,darkkhaki:12433259,darkmagenta:9109643,darkolivegreen:5597999,darkorange:16747520,darkorchid:10040012,darkred:9109504,darksalmon:15308410,darkseagreen:9419919,darkslateblue:4734347,darkslategray:3100495,darkslategrey:3100495,darkturquoise:52945,darkviolet:9699539,deeppink:16716947,deepskyblue:49151,dimgray:6908265,dimgrey:6908265,dodgerblue:2003199,firebrick:11674146,floralwhite:16775920,forestgreen:2263842,fuchsia:16711935,gainsboro:14474460,ghostwhite:16316671,gold:16766720,goldenrod:14329120,gray:8421504,green:32768,greenyellow:11403055,grey:8421504,honeydew:15794160,hotpink:16738740,indianred:13458524,indigo:4915330,ivory:16777200,khaki:15787660,lavender:15132410,lavenderblush:16773365,lawngreen:8190976,lemonchiffon:16775885,lightblue:11393254,lightcoral:15761536,lightcyan:14745599,lightgoldenrodyellow:16448210,lightgray:13882323,lightgreen:9498256,lightgrey:13882323,lightpink:16758465,lightsalmon:16752762,lightseagreen:2142890,lightskyblue:8900346,lightslategray:7833753,lightslategrey:7833753,lightsteelblue:11584734,lightyellow:16777184,lime:65280,limegreen:3329330,linen:16445670,magenta:16711935,maroon:8388608,mediumaquamarine:6737322,mediumblue:205,mediumorchid:12211667,mediumpurple:9662683,mediumseagreen:3978097,mediumslateblue:8087790,mediumspringgreen:64154,mediumturquoise:4772300,mediumvioletred:13047173,midnightblue:1644912,mintcream:16121850,mistyrose:16770273,moccasin:16770229,navajowhite:16768685,navy:128,oldlace:16643558,olive:8421376,olivedrab:7048739,orange:16753920,orangered:16729344,orchid:14315734,palegoldenrod:15657130,palegreen:10025880,paleturquoise:11529966,palevioletred:14381203,papayawhip:16773077,peachpuff:16767673,peru:13468991,pink:16761035,plum:14524637,powderblue:11591910,purple:8388736,rebeccapurple:6697881,red:16711680,rosybrown:12357519,royalblue:4286945,saddlebrown:9127187,salmon:16416882,sandybrown:16032864,seagreen:3050327,seashell:16774638,sienna:10506797,silver:12632256,skyblue:8900331,slateblue:6970061,slategray:7372944,slategrey:7372944,snow:16775930,springgreen:65407,steelblue:4620980,tan:13808780,teal:32896,thistle:14204888,tomato:16737095,turquoise:4251856,violet:15631086,wheat:16113331,white:16777215,whitesmoke:16119285,yellow:16776960,yellowgreen:10145074},Et={h:0,s:0,l:0},Le={h:0,s:0,l:0};function xn(s,t,e){return e<0&&(e+=1),e>1&&(e-=1),e<1/6?s+(t-s)*6*e:e<1/2?t:e<2/3?s+(t-s)*6*(2/3-e):s}d(xn,"hue2rgb");var Z=class{static{d(this,"Color")}constructor(t,e,n){return this.isColor=!0,this.r=1,this.g=1,this.b=1,this.set(t,e,n)}set(t,e,n){if(e===void 0&&n===void 0){let i=t;i&&i.isColor?this.copy(i):typeof i=="number"?this.setHex(i):typeof i=="string"&&this.setStyle(i)}else this.setRGB(t,e,n);return this}setScalar(t){return this.r=t,this.g=t,this.b=t,this}setHex(t,e=ut){return t=Math.floor(t),this.r=(t>>16&255)/255,this.g=(t>>8&255)/255,this.b=(t&255)/255,ht.colorSpaceToWorking(this,e),this}setRGB(t,e,n,i=ht.workingColorSpace){return this.r=t,this.g=e,this.b=n,ht.colorSpaceToWorking(this,i),this}setHSL(t,e,n,i=ht.workingColorSpace){if(t=Jr(t,1),e=F(e,0,1),n=F(n,0,1),e===0)this.r=this.g=this.b=n;else{let r=n<=.5?n*(1+e):n+e-n*e,o=2*n-r;this.r=xn(o,r,t+1/3),this.g=xn(o,r,t),this.b=xn(o,r,t-1/3)}return ht.colorSpaceToWorking(this,i),this}setStyle(t,e=ut){function n(r){r!==void 0&&parseFloat(r)<1&&tt("Color: Alpha component of "+t+" will be ignored.")}d(n,"handleAlpha");let i;if(i=/^(\w+)\(([^\)]*)\)/.exec(t)){let r,o=i[1],a=i[2];switch(o){case"rgb":case"rgba":if(r=/^\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*(?:,\s*(\d*\.?\d+)\s*)?$/.exec(a))return n(r[4]),this.setRGB(Math.min(255,parseInt(r[1],10))/255,Math.min(255,parseInt(r[2],10))/255,Math.min(255,parseInt(r[3],10))/255,e);if(r=/^\s*(\d+)\%\s*,\s*(\d+)\%\s*,\s*(\d+)\%\s*(?:,\s*(\d*\.?\d+)\s*)?$/.exec(a))return n(r[4]),this.setRGB(Math.min(100,parseInt(r[1],10))/100,Math.min(100,parseInt(r[2],10))/100,Math.min(100,parseInt(r[3],10))/100,e);break;case"hsl":case"hsla":if(r=/^\s*(\d*\.?\d+)\s*,\s*(\d*\.?\d+)\%\s*,\s*(\d*\.?\d+)\%\s*(?:,\s*(\d*\.?\d+)\s*)?$/.exec(a))return n(r[4]),this.setHSL(parseFloat(r[1])/360,parseFloat(r[2])/100,parseFloat(r[3])/100,e);break;default:tt("Color: Unknown color model "+t)}}else if(i=/^\#([A-Fa-f\d]+)$/.exec(t)){let r=i[1],o=r.length;if(o===3)return this.setRGB(parseInt(r.charAt(0),16)/15,parseInt(r.charAt(1),16)/15,parseInt(r.charAt(2),16)/15,e);if(o===6)return this.setHex(parseInt(r,16),e);tt("Color: Invalid hex color "+t)}else if(t&&t.length>0)return this.setColorName(t,e);return this}setColorName(t,e=ut){let n=is[t.toLowerCase()];return n!==void 0?this.setHex(n,e):tt("Color: Unknown color "+t),this}clone(){return new this.constructor(this.r,this.g,this.b)}copy(t){return this.r=t.r,this.g=t.g,this.b=t.b,this}copySRGBToLinear(t){return this.r=gt(t.r),this.g=gt(t.g),this.b=gt(t.b),this}copyLinearToSRGB(t){return this.r=$t(t.r),this.g=$t(t.g),this.b=$t(t.b),this}convertSRGBToLinear(){return this.copySRGBToLinear(this),this}convertLinearToSRGB(){return this.copyLinearToSRGB(this),this}getHex(t=ut){return ht.workingToColorSpace(j.copy(this),t),Math.round(F(j.r*255,0,255))*65536+Math.round(F(j.g*255,0,255))*256+Math.round(F(j.b*255,0,255))}getHexString(t=ut){return("000000"+this.getHex(t).toString(16)).slice(-6)}getHSL(t,e=ht.workingColorSpace){ht.workingToColorSpace(j.copy(this),e);let n=j.r,i=j.g,r=j.b,o=Math.max(n,i,r),a=Math.min(n,i,r),c,l,u=(a+o)/2;if(a===o)c=0,l=0;else{let h=o-a;switch(l=u<=.5?h/(o+a):h/(2-o-a),o){case n:c=(i-r)/h+(i<r?6:0);break;case i:c=(r-n)/h+2;break;case r:c=(n-i)/h+4;break}c/=6}return t.h=c,t.s=l,t.l=u,t}getRGB(t,e=ht.workingColorSpace){return ht.workingToColorSpace(j.copy(this),e),t.r=j.r,t.g=j.g,t.b=j.b,t}getStyle(t=ut){ht.workingToColorSpace(j.copy(this),t);let e=j.r,n=j.g,i=j.b;return t!==ut?`color(${t} ${e.toFixed(3)} ${n.toFixed(3)} ${i.toFixed(3)})`:`rgb(${Math.round(e*255)},${Math.round(n*255)},${Math.round(i*255)})`}offsetHSL(t,e,n){return this.getHSL(Et),this.setHSL(Et.h+t,Et.s+e,Et.l+n)}add(t){return this.r+=t.r,this.g+=t.g,this.b+=t.b,this}addColors(t,e){return this.r=t.r+e.r,this.g=t.g+e.g,this.b=t.b+e.b,this}addScalar(t){return this.r+=t,this.g+=t,this.b+=t,this}sub(t){return this.r=Math.max(0,this.r-t.r),this.g=Math.max(0,this.g-t.g),this.b=Math.max(0,this.b-t.b),this}multiply(t){return this.r*=t.r,this.g*=t.g,this.b*=t.b,this}multiplyScalar(t){return this.r*=t,this.g*=t,this.b*=t,this}lerp(t,e){return this.r+=(t.r-this.r)*e,this.g+=(t.g-this.g)*e,this.b+=(t.b-this.b)*e,this}lerpColors(t,e,n){return this.r=t.r+(e.r-t.r)*n,this.g=t.g+(e.g-t.g)*n,this.b=t.b+(e.b-t.b)*n,this}lerpHSL(t,e){this.getHSL(Et),t.getHSL(Le);let n=dn(Et.h,Le.h,e),i=dn(Et.s,Le.s,e),r=dn(Et.l,Le.l,e);return this.setHSL(n,i,r),this}setFromVector3(t){return this.r=t.x,this.g=t.y,this.b=t.z,this}applyMatrix3(t){let e=this.r,n=this.g,i=this.b,r=t.elements;return this.r=r[0]*e+r[3]*n+r[6]*i,this.g=r[1]*e+r[4]*n+r[7]*i,this.b=r[2]*e+r[5]*n+r[8]*i,this}equals(t){return t.r===this.r&&t.g===this.g&&t.b===this.b}fromArray(t,e=0){return this.r=t[e],this.g=t[e+1],this.b=t[e+2],this}toArray(t=[],e=0){return t[e]=this.r,t[e+1]=this.g,t[e+2]=this.b,t}fromBufferAttribute(t,e){return this.r=t.getX(e),this.g=t.getY(e),this.b=t.getZ(e),this}toJSON(){return this.getHex()}*[Symbol.iterator](){yield this.r,yield this.g,yield this.b}},j=new Z;Z.NAMES=is;function oo(s,t,e=2){let n=t&&t.length,i=n?t[0]*e:s.length,r=ss(s,0,i,e,!0),o=[];if(!r||r.next===r.prev)return o;let a,c,l;if(n&&(r=uo(s,t,r,e)),s.length>80*e){a=s[0],c=s[1];let u=a,h=c;for(let f=e;f<i;f+=e){let m=s[f],p=s[f+1];m<a&&(a=m),p<c&&(c=p),m>u&&(u=m),p>h&&(h=p)}l=Math.max(u-a,h-c),l=l!==0?32767/l:0}return me(r,o,e,a,c,l,0),o}d(oo,"earcut");function ss(s,t,e,n,i){let r;if(i===bo(s,t,e,n)>0)for(let o=t;o<e;o+=n)r=Vi(o/n|0,s[o],s[o+1],r);else for(let o=e-n;o>=t;o-=n)r=Vi(o/n|0,s[o],s[o+1],r);return r&&Kt(r,r.next)&&(_e(r),r=r.next),r}d(ss,"linkedList");function Dt(s,t){if(!s)return s;t||(t=s);let e=s,n;do if(n=!1,!e.steiner&&(Kt(e,e.next)||X(e.prev,e,e.next)===0)){if(_e(e),e=t=e.prev,e===e.next)break;n=!0}else e=e.next;while(n||e!==t);return t}d(Dt,"filterPoints");function me(s,t,e,n,i,r,o){if(!s)return;!o&&r&&_o(s,n,i,r);let a=s;for(;s.prev!==s.next;){let c=s.prev,l=s.next;if(r?co(s,n,i,r):ao(s)){t.push(c.i,s.i,l.i),_e(s),s=l.next,a=l.next;continue}if(s=l,s===a){o?o===1?(s=lo(Dt(s),t),me(s,t,e,n,i,r,2)):o===2&&ho(s,t,e,n,i,r):me(Dt(s),t,e,n,i,r,1);break}}}d(me,"earcutLinked");function ao(s){let t=s.prev,e=s,n=s.next;if(X(t,e,n)>=0)return!1;let i=t.x,r=e.x,o=n.x,a=t.y,c=e.y,l=n.y,u=Math.min(i,r,o),h=Math.min(a,c,l),f=Math.max(i,r,o),m=Math.max(a,c,l),p=n.next;for(;p!==t;){if(p.x>=u&&p.x<=f&&p.y>=h&&p.y<=m&&ue(i,a,r,c,o,l,p.x,p.y)&&X(p.prev,p,p.next)>=0)return!1;p=p.next}return!0}d(ao,"isEar");function co(s,t,e,n){let i=s.prev,r=s,o=s.next;if(X(i,r,o)>=0)return!1;let a=i.x,c=r.x,l=o.x,u=i.y,h=r.y,f=o.y,m=Math.min(a,c,l),p=Math.min(u,h,f),_=Math.max(a,c,l),x=Math.max(u,h,f),g=zn(m,p,t,e,n),M=zn(_,x,t,e,n),y=s.prevZ,v=s.nextZ;for(;y&&y.z>=g&&v&&v.z<=M;){if(y.x>=m&&y.x<=_&&y.y>=p&&y.y<=x&&y!==i&&y!==o&&ue(a,u,c,h,l,f,y.x,y.y)&&X(y.prev,y,y.next)>=0||(y=y.prevZ,v.x>=m&&v.x<=_&&v.y>=p&&v.y<=x&&v!==i&&v!==o&&ue(a,u,c,h,l,f,v.x,v.y)&&X(v.prev,v,v.next)>=0))return!1;v=v.nextZ}for(;y&&y.z>=g;){if(y.x>=m&&y.x<=_&&y.y>=p&&y.y<=x&&y!==i&&y!==o&&ue(a,u,c,h,l,f,y.x,y.y)&&X(y.prev,y,y.next)>=0)return!1;y=y.prevZ}for(;v&&v.z<=M;){if(v.x>=m&&v.x<=_&&v.y>=p&&v.y<=x&&v!==i&&v!==o&&ue(a,u,c,h,l,f,v.x,v.y)&&X(v.prev,v,v.next)>=0)return!1;v=v.nextZ}return!0}d(co,"isEarHashed");function lo(s,t){let e=s;do{let n=e.prev,i=e.next.next;!Kt(n,i)&&os(n,e,e.next,i)&&ge(n,i)&&ge(i,n)&&(t.push(n.i,e.i,i.i),_e(e),_e(e.next),e=s=i),e=e.next}while(e!==s);return Dt(e)}d(lo,"cureLocalIntersections");function ho(s,t,e,n,i,r){let o=s;do{let a=o.next.next;for(;a!==o.prev;){if(o.i!==a.i&&vo(o,a)){let c=as(o,a);o=Dt(o,o.next),c=Dt(c,c.next),me(o,t,e,n,i,r,0),me(c,t,e,n,i,r,0);return}a=a.next}o=o.next}while(o!==s)}d(ho,"splitEarcut");function uo(s,t,e,n){let i=[];for(let r=0,o=t.length;r<o;r++){let a=t[r]*n,c=r<o-1?t[r+1]*n:s.length,l=ss(s,a,c,n,!1);l===l.next&&(l.steiner=!0),i.push(yo(l))}i.sort(fo);for(let r=0;r<i.length;r++)e=po(i[r],e);return e}d(uo,"eliminateHoles");function fo(s,t){let e=s.x-t.x;if(e===0&&(e=s.y-t.y,e===0)){let n=(s.next.y-s.y)/(s.next.x-s.x),i=(t.next.y-t.y)/(t.next.x-t.x);e=n-i}return e}d(fo,"compareXYSlope");function po(s,t){let e=mo(s,t);if(!e)return t;let n=as(e,s);return Dt(n,n.next),Dt(e,e.next)}d(po,"eliminateHole");function mo(s,t){let e=t,n=s.x,i=s.y,r=-1/0,o;if(Kt(s,e))return e;do{if(Kt(s,e.next))return e.next;if(i<=e.y&&i>=e.next.y&&e.next.y!==e.y){let h=e.x+(i-e.y)*(e.next.x-e.x)/(e.next.y-e.y);if(h<=n&&h>r&&(r=h,o=e.x<e.next.x?e:e.next,h===n))return o}e=e.next}while(e!==t);if(!o)return null;let a=o,c=o.x,l=o.y,u=1/0;e=o;do{if(n>=e.x&&e.x>=c&&n!==e.x&&rs(i<l?n:r,i,c,l,i<l?r:n,i,e.x,e.y)){let h=Math.abs(i-e.y)/(n-e.x);ge(e,s)&&(h<u||h===u&&(e.x>o.x||e.x===o.x&&go(o,e)))&&(o=e,u=h)}e=e.next}while(e!==a);return o}d(mo,"findHoleBridge");function go(s,t){return X(s.prev,s,t.prev)<0&&X(t.next,s,s.next)<0}d(go,"sectorContainsSector");function _o(s,t,e,n){let i=s;do i.z===0&&(i.z=zn(i.x,i.y,t,e,n)),i.prevZ=i.prev,i.nextZ=i.next,i=i.next;while(i!==s);i.prevZ.nextZ=null,i.prevZ=null,xo(i)}d(_o,"indexCurve");function xo(s){let t,e=1;do{let n=s,i;s=null;let r=null;for(t=0;n;){t++;let o=n,a=0;for(let l=0;l<e&&(a++,o=o.nextZ,!!o);l++);let c=e;for(;a>0||c>0&&o;)a!==0&&(c===0||!o||n.z<=o.z)?(i=n,n=n.nextZ,a--):(i=o,o=o.nextZ,c--),r?r.nextZ=i:s=i,i.prevZ=r,r=i;n=o}r.nextZ=null,e*=2}while(t>1);return s}d(xo,"sortLinked");function zn(s,t,e,n,i){return s=(s-e)*i|0,t=(t-n)*i|0,s=(s|s<<8)&16711935,s=(s|s<<4)&252645135,s=(s|s<<2)&858993459,s=(s|s<<1)&1431655765,t=(t|t<<8)&16711935,t=(t|t<<4)&252645135,t=(t|t<<2)&858993459,t=(t|t<<1)&1431655765,s|t<<1}d(zn,"zOrder");function yo(s){let t=s,e=s;do(t.x<e.x||t.x===e.x&&t.y<e.y)&&(e=t),t=t.next;while(t!==s);return e}d(yo,"getLeftmost");function rs(s,t,e,n,i,r,o,a){return(i-o)*(t-a)>=(s-o)*(r-a)&&(s-o)*(n-a)>=(e-o)*(t-a)&&(e-o)*(r-a)>=(i-o)*(n-a)}d(rs,"pointInTriangle");function ue(s,t,e,n,i,r,o,a){return!(s===o&&t===a)&&rs(s,t,e,n,i,r,o,a)}d(ue,"pointInTriangleExceptFirst");function vo(s,t){return s.next.i!==t.i&&s.prev.i!==t.i&&!Mo(s,t)&&(ge(s,t)&&ge(t,s)&&So(s,t)&&(X(s.prev,s,t.prev)||X(s,t.prev,t))||Kt(s,t)&&X(s.prev,s,s.next)>0&&X(t.prev,t,t.next)>0)}d(vo,"isValidDiagonal");function X(s,t,e){return(t.y-s.y)*(e.x-t.x)-(t.x-s.x)*(e.y-t.y)}d(X,"area");function Kt(s,t){return s.x===t.x&&s.y===t.y}d(Kt,"equals");function os(s,t,e,n){let i=De(X(s,t,e)),r=De(X(s,t,n)),o=De(X(e,n,s)),a=De(X(e,n,t));return!!(i!==r&&o!==a||i===0&&Ne(s,e,t)||r===0&&Ne(s,n,t)||o===0&&Ne(e,s,n)||a===0&&Ne(e,t,n))}d(os,"intersects");function Ne(s,t,e){return t.x<=Math.max(s.x,e.x)&&t.x>=Math.min(s.x,e.x)&&t.y<=Math.max(s.y,e.y)&&t.y>=Math.min(s.y,e.y)}d(Ne,"onSegment");function De(s){return s>0?1:s<0?-1:0}d(De,"sign");function Mo(s,t){let e=s;do{if(e.i!==s.i&&e.next.i!==s.i&&e.i!==t.i&&e.next.i!==t.i&&os(e,e.next,s,t))return!0;e=e.next}while(e!==s);return!1}d(Mo,"intersectsPolygon");function ge(s,t){return X(s.prev,s,s.next)<0?X(s,t,s.next)>=0&&X(s,s.prev,t)>=0:X(s,t,s.prev)<0||X(s,s.next,t)<0}d(ge,"locallyInside");function So(s,t){let e=s,n=!1,i=(s.x+t.x)/2,r=(s.y+t.y)/2;do e.y>r!=e.next.y>r&&e.next.y!==e.y&&i<(e.next.x-e.x)*(r-e.y)/(e.next.y-e.y)+e.x&&(n=!n),e=e.next;while(e!==s);return n}d(So,"middleInside");function as(s,t){let e=Vn(s.i,s.x,s.y),n=Vn(t.i,t.x,t.y),i=s.next,r=t.prev;return s.next=t,t.prev=s,e.next=i,i.prev=e,n.next=e,e.prev=n,r.next=n,n.prev=r,n}d(as,"splitPolygon");function Vi(s,t,e,n){let i=Vn(s,t,e);return n?(i.next=n.next,i.prev=n,n.next.prev=i,n.next=i):(i.prev=i,i.next=i),i}d(Vi,"insertNode");function _e(s){s.next.prev=s.prev,s.prev.next=s.next,s.prevZ&&(s.prevZ.nextZ=s.nextZ),s.nextZ&&(s.nextZ.prevZ=s.prevZ)}d(_e,"removeNode");function Vn(s,t,e){return{i:s,x:t,y:e,prev:null,next:null,z:0,prevZ:null,nextZ:null,steiner:!1}}d(Vn,"createNode");function bo(s,t,e,n){let i=0;for(let r=t,o=e-n;r<e;r+=n)i+=(s[o]-s[r])*(s[r+1]+s[o+1]),o=r;return i}d(bo,"signedArea");var kn=class{static{d(this,"Earcut")}static triangulate(t,e,n=2){return oo(t,e,n)}},Qt=class s{static{d(this,"ShapeUtils")}static area(t){let e=t.length,n=0;for(let i=e-1,r=0;r<e;i=r++)n+=t[i].x*t[r].y-t[r].x*t[i].y;return n*.5}static isClockWise(t){return s.area(t)<0}static triangulateShape(t,e){let n=[],i=[],r=[];ki(t),Gi(n,t);let o=t.length;e.forEach(ki);for(let c=0;c<e.length;c++)i.push(o),o+=e[c].length,Gi(n,e[c]);let a=kn.triangulate(n,i);for(let c=0;c<a.length;c+=3)r.push(a.slice(c,c+3));return r}};function ki(s){let t=s.length;t>2&&s[t-1].equals(s[0])&&s.pop()}d(ki,"removeDupEndPts");function Gi(s,t){for(let e=0;e<t.length;e++)s.push(t[e].x),s.push(t[e].y)}d(Gi,"addContour");function cs(s){let t={};for(let e in s){t[e]={};for(let n in s[e]){let i=s[e][n];if(Hi(i))i.isRenderTargetTexture?(tt("UniformsUtils: Textures of render targets cannot be cloned via cloneUniforms() or mergeUniforms()."),t[e][n]=null):t[e][n]=i.clone();else if(Array.isArray(i))if(Hi(i[0])){let r=[];for(let o=0,a=i.length;o<a;o++)r[o]=i[o].clone();t[e][n]=r}else t[e][n]=i.slice();else t[e][n]=i}}return t}d(cs,"cloneUniforms");function nt(s){let t={};for(let e=0;e<s.length;e++){let n=cs(s[e]);for(let i in n)t[i]=n[i]}return t}d(nt,"mergeUniforms");function Hi(s){return s&&(s.isColor||s.isMatrix3||s.isMatrix4||s.isVector2||s.isVector3||s.isVector4||s.isTexture||s.isQuaternion)}d(Hi,"isThreeObject");function qt(s,t){return!s||s.constructor===t?s:typeof t.BYTES_PER_ELEMENT=="number"?new t(s):Array.prototype.slice.call(s)}d(qt,"convertArray");function yn(s){return s!==void 0&&s.inTangents!==void 0&&s.outTangents!==void 0}d(yn,"hasTangents");var At=class{static{d(this,"Interpolant")}constructor(t,e,n,i){this.parameterPositions=t,this._cachedIndex=0,this.resultBuffer=i!==void 0?i:new e.constructor(n),this.sampleValues=e,this.valueSize=n,this.settings=null,this.DefaultSettings_={}}evaluate(t){let e=this.parameterPositions,n=this._cachedIndex,i=e[n],r=e[n-1];n:{t:{let o;e:{i:if(!(t<i)){for(let a=n+2;;){if(i===void 0){if(t<r)break i;return n=e.length,this._cachedIndex=n,this.copySampleValue_(n-1)}if(n===a)break;if(r=i,i=e[++n],t<i)break t}o=e.length;break e}if(!(t>=r)){let a=e[1];t<a&&(n=2,r=a);for(let c=n-2;;){if(r===void 0)return this._cachedIndex=0,this.copySampleValue_(0);if(n===c)break;if(i=r,r=e[--n-1],t>=r)break t}o=n,n=0;break e}break n}for(;n<o;){let a=n+o>>>1;t<e[a]?o=a:n=a+1}if(i=e[n],r=e[n-1],r===void 0)return this._cachedIndex=0,this.copySampleValue_(0);if(i===void 0)return n=e.length,this._cachedIndex=n,this.copySampleValue_(n-1)}this._cachedIndex=n,this.intervalChanged_(n,r,i)}return this.interpolate_(n,r,t,i)}getSettings_(){return this.settings||this.DefaultSettings_}copySampleValue_(t){let e=this.resultBuffer,n=this.sampleValues,i=this.valueSize,r=t*i;for(let o=0;o!==i;++o)e[o]=n[r+o];return e}interpolate_(){throw new Error("THREE.Interpolant: Call to abstract method.")}intervalChanged_(){}},Ge=class extends At{static{d(this,"CubicInterpolant")}constructor(t,e,n,i){super(t,e,n,i),this._weightPrev=-0,this._offsetPrev=-0,this._weightNext=-0,this._offsetNext=-0,this.DefaultSettings_={endingStart:Pn,endingEnd:Pn}}intervalChanged_(t,e,n){let i=this.parameterPositions,r=t-2,o=t+1,a=i[r],c=i[o];if(a===void 0)switch(this.getSettings_().endingStart){case Ln:r=t,a=2*e-n;break;case Nn:r=i.length-2,a=e+i[r]-i[r+1];break;default:r=t,a=n}if(c===void 0)switch(this.getSettings_().endingEnd){case Ln:o=t,c=2*n-e;break;case Nn:o=1,c=n+i[1]-i[0];break;default:o=t-1,c=e}let l=(n-e)*.5,u=this.valueSize;this._weightPrev=l/(e-a),this._weightNext=l/(c-n),this._offsetPrev=r*u,this._offsetNext=o*u}interpolate_(t,e,n,i){let r=this.resultBuffer,o=this.sampleValues,a=this.valueSize,c=t*a,l=c-a,u=this._offsetPrev,h=this._offsetNext,f=this._weightPrev,m=this._weightNext,p=(n-e)/(i-e),_=p*p,x=_*p,g=-f*x+2*f*_-f*p,M=(1+f)*x+(-1.5-2*f)*_+(-.5+f)*p+1,y=(-1-m)*x+(1.5+m)*_+.5*p,v=m*x-m*_;for(let b=0;b!==a;++b)r[b]=g*o[u+b]+M*o[l+b]+y*o[c+b]+v*o[h+b];return r}},He=class extends At{static{d(this,"LinearInterpolant")}constructor(t,e,n,i){super(t,e,n,i)}interpolate_(t,e,n,i){let r=this.resultBuffer,o=this.sampleValues,a=this.valueSize,c=t*a,l=c-a,u=(n-e)/(i-e),h=1-u;for(let f=0;f!==a;++f)r[f]=o[l+f]*h+o[c+f]*u;return r}},We=class extends At{static{d(this,"DiscreteInterpolant")}constructor(t,e,n,i){super(t,e,n,i)}interpolate_(t){return this.copySampleValue_(t-1)}},Xe=class extends At{static{d(this,"BezierInterpolant")}interpolate_(t,e,n,i){let r=this.resultBuffer,o=this.sampleValues,a=this.valueSize,c=t*a,l=c-a,u=this.inTangents,h=this.outTangents;if(!u||!h){let p=(n-e)/(i-e),_=1-p;for(let x=0;x!==a;++x)r[x]=o[l+x]*_+o[c+x]*p;return r}let f=a*2,m=t-1;for(let p=0;p!==a;++p){let _=o[l+p],x=o[c+p],g=m*f+p*2,M=h[g],y=h[g+1],v=t*f+p*2,b=u[v],A=u[v+1],R=Ao(n,e,M,b,i);r[p]=ls(R,_,y,A,x)}return r}};function ls(s,t,e,n,i){let r=1-s;return r*r*r*t+3*r*r*s*e+3*r*s*s*n+s*s*s*i}d(ls,"cubicBezier");function Eo(s,t,e,n,i){let r=1-s;return 3*r*r*(e-t)+6*r*s*(n-e)+3*s*s*(i-n)}d(Eo,"cubicBezierSlope");function Ao(s,t,e,n,i){let r=(s-t)/(i-t);for(let o=0;o<8;o++){let a=ls(r,t,e,n,i)-s;if(Math.abs(a)<1e-10)break;let c=Eo(r,t,e,n,i);if(Math.abs(c)<1e-10)break;r=Math.max(0,Math.min(1,r-a/c))}return r}d(Ao,"solveBezierParameter");var ot=class{static{d(this,"KeyframeTrack")}constructor(t,e,n,i){if(t===void 0)throw new Error("THREE.KeyframeTrack: track name is undefined");if(e===void 0||e.length===0)throw new Error("THREE.KeyframeTrack: no keyframes in track named "+t);this.name=t,this.times=qt(e,this.TimeBufferType),this.values=qt(n,this.ValueBufferType),this.setInterpolation(i||this.DefaultInterpolation)}static toJSON(t){let e=t.constructor,n;if(e.toJSON!==this.toJSON)n=e.toJSON(t);else{n={name:t.name,times:qt(t.times,Array),values:qt(t.values,Array)};let i=t.getInterpolation();i!==t.DefaultInterpolation&&(n.interpolation=i),yn(t.settings)&&(n.settings={inTangents:qt(t.settings.inTangents,Array),outTangents:qt(t.settings.outTangents,Array)})}return n.type=t.ValueTypeName,n}InterpolantFactoryMethodDiscrete(t){return new We(this.times,this.values,this.getValueSize(),t)}InterpolantFactoryMethodLinear(t){return new He(this.times,this.values,this.getValueSize(),t)}InterpolantFactoryMethodSmooth(t){return new Ge(this.times,this.values,this.getValueSize(),t)}InterpolantFactoryMethodBezier(t){let e=new Xe(this.times,this.values,this.getValueSize(),t);return this.settings&&(e.inTangents=this.settings.inTangents,e.outTangents=this.settings.outTangents),e}setInterpolation(t){let e;switch(t){case de:e=this.InterpolantFactoryMethodDiscrete;break;case Oe:e=this.InterpolantFactoryMethodLinear;break;case Ue:e=this.InterpolantFactoryMethodSmooth;break;case In:e=this.InterpolantFactoryMethodBezier;break}if(e===void 0){let n="unsupported interpolation for "+this.ValueTypeName+" keyframe track named "+this.name;if(this.createInterpolant===void 0)if(t!==this.DefaultInterpolation)this.setInterpolation(this.DefaultInterpolation);else throw new Error(n);return tt("KeyframeTrack:",n),this}return this.createInterpolant=e,this}getInterpolation(){switch(this.createInterpolant){case this.InterpolantFactoryMethodDiscrete:return de;case this.InterpolantFactoryMethodLinear:return Oe;case this.InterpolantFactoryMethodSmooth:return Ue;case this.InterpolantFactoryMethodBezier:return In}}getValueSize(){return this.values.length/this.times.length}shift(t){if(t!==0){let e=this.times;for(let n=0,i=e.length;n!==i;++n)e[n]+=t}return this}scale(t){if(t!==1){let e=this.times;for(let n=0,i=e.length;n!==i;++n)e[n]*=t;yn(this.settings)&&(Wi(this.settings.inTangents,t),Wi(this.settings.outTangents,t))}return this}trim(t,e){let n=this.times,i=n.length,r=0,o=i-1;for(;r!==i&&n[r]<t;)++r;for(;o!==-1&&n[o]>e;)--o;if(++o,r!==0||o!==i){r>=o&&(o=Math.max(o,1),r=o-1);let a=this.getValueSize();this.times=n.slice(r,o),this.values=this.values.slice(r*a,o*a)}return this}validate(){let t=!0,e=this.getValueSize();e-Math.floor(e)!==0&&($("KeyframeTrack: Invalid value size in track.",this),t=!1);let n=this.times,i=this.values,r=n.length;r===0&&($("KeyframeTrack: Track is empty.",this),t=!1);let o=null;for(let a=0;a!==r;a++){let c=n[a];if(typeof c=="number"&&isNaN(c)){$("KeyframeTrack: Time is not a valid number.",this,a,c),t=!1;break}if(o!==null&&o>c){$("KeyframeTrack: Out of order keys.",this,a,c,o),t=!1;break}o=c}if(i!==void 0&&Yr(i))for(let a=0,c=i.length;a!==c;++a){let l=i[a];if(isNaN(l)){$("KeyframeTrack: Value is not a valid number.",this,a,l),t=!1;break}}return t}optimize(){let t=this.times.slice(),e=this.values.slice(),n=this.getValueSize(),i=this.getInterpolation()===Ue,r=t.length-1,o=1;for(let a=1;a<r;++a){let c=!1,l=t[a],u=t[a+1];if(l!==u&&(a!==1||l!==t[0]))if(i)c=!0;else{let h=a*n,f=h-n,m=h+n;for(let p=0;p!==n;++p){let _=e[h+p];if(_!==e[f+p]||_!==e[m+p]){c=!0;break}}}if(c){if(a!==o){t[o]=t[a];let h=a*n,f=o*n;for(let m=0;m!==n;++m)e[f+m]=e[h+m]}++o}}if(r>0){t[o]=t[r];for(let a=r*n,c=o*n,l=0;l!==n;++l)e[c+l]=e[a+l];++o}return o!==t.length?(this.times=t.slice(0,o),this.values=e.slice(0,o*n)):(this.times=t,this.values=e),this}clone(){let t=this.times.slice(),e=this.values.slice(),n=this.constructor,i=new n(this.name,t,e);return i.createInterpolant=this.createInterpolant,yn(this.settings)&&(i.settings={inTangents:this.settings.inTangents.slice(),outTangents:this.settings.outTangents.slice()}),i}};function Wi(s,t){for(let e=0,n=s.length;e!==n;e+=2)s[e]*=t}d(Wi,"scaleTangentTimes");ot.prototype.ValueTypeName="";ot.prototype.TimeBufferType=Float32Array;ot.prototype.ValueBufferType=Float32Array;ot.prototype.DefaultInterpolation=Oe;var Tt=class extends ot{static{d(this,"BooleanKeyframeTrack")}constructor(t,e,n){super(t,e,n)}};Tt.prototype.ValueTypeName="bool";Tt.prototype.ValueBufferType=Array;Tt.prototype.DefaultInterpolation=de;Tt.prototype.InterpolantFactoryMethodLinear=void 0;Tt.prototype.InterpolantFactoryMethodSmooth=void 0;var qe=class extends ot{static{d(this,"ColorKeyframeTrack")}constructor(t,e,n,i){super(t,e,n,i)}};qe.prototype.ValueTypeName="color";var Ye=class extends ot{static{d(this,"NumberKeyframeTrack")}constructor(t,e,n,i){super(t,e,n,i)}};Ye.prototype.ValueTypeName="number";var $e=class extends At{static{d(this,"QuaternionLinearInterpolant")}constructor(t,e,n,i){super(t,e,n,i)}interpolate_(t,e,n,i){let r=this.resultBuffer,o=this.sampleValues,a=this.valueSize,c=(n-e)/(i-e),l=t*a;for(let u=l+a;l!==u;l+=4)_t.slerpFlat(r,0,o,l-a,o,l,c);return r}},xe=class extends ot{static{d(this,"QuaternionKeyframeTrack")}constructor(t,e,n,i){super(t,e,n,i)}InterpolantFactoryMethodLinear(t){return new $e(this.times,this.values,this.getValueSize(),t)}};xe.prototype.ValueTypeName="quaternion";xe.prototype.InterpolantFactoryMethodSmooth=void 0;var wt=class extends ot{static{d(this,"StringKeyframeTrack")}constructor(t,e,n){super(t,e,n)}};wt.prototype.ValueTypeName="string";wt.prototype.ValueBufferType=Array;wt.prototype.DefaultInterpolation=de;wt.prototype.InterpolantFactoryMethodLinear=void 0;wt.prototype.InterpolantFactoryMethodSmooth=void 0;var Ze=class extends ot{static{d(this,"VectorKeyframeTrack")}constructor(t,e,n,i){super(t,e,n,i)}};Ze.prototype.ValueTypeName="vector";var Je=class{static{d(this,"LoadingManager")}constructor(t,e,n){let i=this,r=!1,o=0,a=0,c,l=[];this.onStart=void 0,this.onLoad=t,this.onProgress=e,this.onError=n,this._abortController=null,this.itemStart=function(u){a++,r===!1&&i.onStart!==void 0&&i.onStart(u,o,a),r=!0},this.itemEnd=function(u){o++,i.onProgress!==void 0&&i.onProgress(u,o,a),o===a&&(r=!1,i.onLoad!==void 0&&i.onLoad())},this.itemError=function(u){i.onError!==void 0&&i.onError(u)},this.resolveURL=function(u){return u=u.normalize("NFC"),c?c(u):u},this.setURLModifier=function(u){return c=u,this},this.addHandler=function(u,h){return l.push(u,h),this},this.removeHandler=function(u){let h=l.indexOf(u);return h!==-1&&l.splice(h,2),this},this.getHandler=function(u){for(let h=0,f=l.length;h<f;h+=2){let m=l[h],p=l[h+1];if(m.global&&(m.lastIndex=0),m.test(u))return p}return null},this.abort=function(){return this.abortController.abort(),this._abortController=null,this}}get abortController(){return this._abortController||(this._abortController=new AbortController),this._abortController}},hs=new Je,Ke=class{static{d(this,"Loader")}constructor(t){this.manager=t!==void 0?t:hs,this.crossOrigin="anonymous",this.withCredentials=!1,this.path="",this.resourcePath="",this.requestHeader={},typeof __THREE_DEVTOOLS__<"u"&&__THREE_DEVTOOLS__.dispatchEvent(new CustomEvent("observe",{detail:this}))}load(){}loadAsync(t,e){let n=this;return new Promise(function(i,r){n.load(t,i,e,r)})}parse(){}setCrossOrigin(t){return this.crossOrigin=t,this}setWithCredentials(t){return this.withCredentials=t,this}setPath(t){return this.path=t,this}setResourcePath(t){return this.resourcePath=t,this}setRequestHeader(t){return this.requestHeader=t,this}abort(){return this}};Ke.DEFAULT_MATERIAL_NAME="__DEFAULT";var ei="\\[\\]\\.:\\/",To=new RegExp("["+ei+"]","g"),ni="[^"+ei+"]",wo="[^"+ei.replace("\\.","")+"]",Co=/((?:WC+[\/:])*)/.source.replace("WC",ni),Ro=/(WCOD+)?/.source.replace("WCOD",wo),Io=/(?:\.(WC+)(?:\[(.+)\])?)?/.source.replace("WC",ni),Po=/\.(WC+)(?:\[(.+)\])?/.source.replace("WC",ni),Lo=new RegExp("^"+Co+Ro+Io+Po+"$"),No=["material","materials","bones","map"],Gn=class{static{d(this,"Composite")}constructor(t,e,n){let i=n||H.parseTrackName(e);this._targetGroup=t,this._bindings=t.subscribe_(e,i)}getValue(t,e){this.bind();let n=this._targetGroup.nCachedObjects_,i=this._bindings[n];i!==void 0&&i.getValue(t,e)}setValue(t,e){let n=this._bindings;for(let i=this._targetGroup.nCachedObjects_,r=n.length;i!==r;++i)n[i].setValue(t,e)}bind(){let t=this._bindings;for(let e=this._targetGroup.nCachedObjects_,n=t.length;e!==n;++e)t[e].bind()}unbind(){let t=this._bindings;for(let e=this._targetGroup.nCachedObjects_,n=t.length;e!==n;++e)t[e].unbind()}},H=class s{static{d(this,"PropertyBinding")}constructor(t,e,n){this.path=e,this.parsedPath=n||s.parseTrackName(e),this.node=s.findNode(t,this.parsedPath.nodeName),this.rootNode=t,this.getValue=this._getValue_unbound,this.setValue=this._setValue_unbound}static create(t,e,n){return t&&t.isAnimationObjectGroup?new s.Composite(t,e,n):new s(t,e,n)}static sanitizeNodeName(t){return t.replace(/\s/g,"_").replace(To,"")}static parseTrackName(t){let e=Lo.exec(t);if(e===null)throw new Error("THREE.PropertyBinding: Cannot parse trackName: "+t);let n={nodeName:e[2],objectName:e[3],objectIndex:e[4],propertyName:e[5],propertyIndex:e[6]},i=n.nodeName&&n.nodeName.lastIndexOf(".");if(i!==void 0&&i!==-1){let r=n.nodeName.substring(i+1);No.indexOf(r)!==-1&&(n.nodeName=n.nodeName.substring(0,i),n.objectName=r)}if(n.propertyName===null||n.propertyName.length===0)throw new Error("THREE.PropertyBinding: can not parse propertyName from trackName: "+t);return n}static findNode(t,e){if(e===void 0||e===""||e==="."||e===-1||e===t.name||e===t.uuid)return t;if(t.skeleton){let n=t.skeleton.getBoneByName(e);if(n!==void 0)return n}if(t.children){let n=d(function(r){for(let o=0;o<r.length;o++){let a=r[o];if(a.name===e||a.uuid===e)return a;let c=n(a.children);if(c)return c}return null},"searchNodeSubtree"),i=n(t.children);if(i)return i}return null}_getValue_unavailable(){}_setValue_unavailable(){}_getValue_direct(t,e){t[e]=this.targetObject[this.propertyName]}_getValue_array(t,e){let n=this.resolvedProperty;for(let i=0,r=n.length;i!==r;++i)t[e++]=n[i]}_getValue_arrayElement(t,e){t[e]=this.resolvedProperty[this.propertyIndex]}_getValue_toArray(t,e){this.resolvedProperty.toArray(t,e)}_setValue_direct(t,e){this.targetObject[this.propertyName]=t[e]}_setValue_direct_setNeedsUpdate(t,e){this.targetObject[this.propertyName]=t[e],this.targetObject.needsUpdate=!0}_setValue_direct_setMatrixWorldNeedsUpdate(t,e){this.targetObject[this.propertyName]=t[e],this.targetObject.matrixWorldNeedsUpdate=!0}_setValue_array(t,e){let n=this.resolvedProperty;for(let i=0,r=n.length;i!==r;++i)n[i]=t[e++]}_setValue_array_setNeedsUpdate(t,e){let n=this.resolvedProperty;for(let i=0,r=n.length;i!==r;++i)n[i]=t[e++];this.targetObject.needsUpdate=!0}_setValue_array_setMatrixWorldNeedsUpdate(t,e){let n=this.resolvedProperty;for(let i=0,r=n.length;i!==r;++i)n[i]=t[e++];this.targetObject.matrixWorldNeedsUpdate=!0}_setValue_arrayElement(t,e){this.resolvedProperty[this.propertyIndex]=t[e]}_setValue_arrayElement_setNeedsUpdate(t,e){this.resolvedProperty[this.propertyIndex]=t[e],this.targetObject.needsUpdate=!0}_setValue_arrayElement_setMatrixWorldNeedsUpdate(t,e){this.resolvedProperty[this.propertyIndex]=t[e],this.targetObject.matrixWorldNeedsUpdate=!0}_setValue_fromArray(t,e){this.resolvedProperty.fromArray(t,e)}_setValue_fromArray_setNeedsUpdate(t,e){this.resolvedProperty.fromArray(t,e),this.targetObject.needsUpdate=!0}_setValue_fromArray_setMatrixWorldNeedsUpdate(t,e){this.resolvedProperty.fromArray(t,e),this.targetObject.matrixWorldNeedsUpdate=!0}_getValue_unbound(t,e){this.bind(),this.getValue(t,e)}_setValue_unbound(t,e){this.bind(),this.setValue(t,e)}bind(){let t=this.node,e=this.parsedPath,n=e.objectName,i=e.propertyName,r=e.propertyIndex;if(t||(t=s.findNode(this.rootNode,e.nodeName),this.node=t),this.getValue=this._getValue_unavailable,this.setValue=this._setValue_unavailable,!t){tt("PropertyBinding: No target node found for track: "+this.path+".");return}if(n){let l=e.objectIndex;switch(n){case"materials":if(!t.material){$("PropertyBinding: Can not bind to material as node does not have a material.",this);return}if(!t.material.materials){$("PropertyBinding: Can not bind to material.materials as node.material does not have a materials array.",this);return}t=t.material.materials;break;case"bones":if(!t.skeleton){$("PropertyBinding: Can not bind to bones as node does not have a skeleton.",this);return}t=t.skeleton.bones;for(let u=0;u<t.length;u++)if(t[u].name===l){l=u;break}break;case"map":if("map"in t){t=t.map;break}if(!t.material){$("PropertyBinding: Can not bind to material as node does not have a material.",this);return}if(!t.material.map){$("PropertyBinding: Can not bind to material.map as node.material does not have a map.",this);return}t=t.material.map;break;default:if(t[n]===void 0){$("PropertyBinding: Can not bind to objectName of node undefined.",this);return}t=t[n]}if(l!==void 0){if(t[l]===void 0){$("PropertyBinding: Trying to bind to objectIndex of objectName, but is undefined.",this,t);return}t=t[l]}}let o=t[i];if(o===void 0){let l=e.nodeName;$("PropertyBinding: Trying to update property for track: "+l+"."+i+" but it wasn't found.",t);return}let a=this.Versioning.None;this.targetObject=t,t.isMaterial===!0?a=this.Versioning.NeedsUpdate:t.isObject3D===!0&&(a=this.Versioning.MatrixWorldNeedsUpdate);let c=this.BindingType.Direct;if(r!==void 0){if(i==="morphTargetInfluences"){if(!t.geometry){$("PropertyBinding: Can not bind to morphTargetInfluences because node does not have a geometry.",this);return}if(!t.geometry.morphAttributes){$("PropertyBinding: Can not bind to morphTargetInfluences because node does not have a geometry.morphAttributes.",this);return}t.morphTargetDictionary[r]!==void 0&&(r=t.morphTargetDictionary[r])}c=this.BindingType.ArrayElement,this.resolvedProperty=o,this.propertyIndex=r}else o.fromArray!==void 0&&o.toArray!==void 0?(c=this.BindingType.HasFromToArray,this.resolvedProperty=o):Array.isArray(o)?(c=this.BindingType.EntireArray,this.resolvedProperty=o):this.propertyName=i;this.getValue=this.GetterByBindingType[c],this.setValue=this.SetterByBindingTypeAndVersioning[c][a]}unbind(){this.node=null,this.getValue=this._getValue_unbound,this.setValue=this._setValue_unbound}};H.Composite=Gn;H.prototype.BindingType={Direct:0,EntireArray:1,ArrayElement:2,HasFromToArray:3};H.prototype.Versioning={None:0,NeedsUpdate:1,MatrixWorldNeedsUpdate:2};H.prototype.GetterByBindingType=[H.prototype._getValue_direct,H.prototype._getValue_array,H.prototype._getValue_arrayElement,H.prototype._getValue_toArray];H.prototype.SetterByBindingTypeAndVersioning=[[H.prototype._setValue_direct,H.prototype._setValue_direct_setNeedsUpdate,H.prototype._setValue_direct_setMatrixWorldNeedsUpdate],[H.prototype._setValue_array,H.prototype._setValue_array_setNeedsUpdate,H.prototype._setValue_array_setMatrixWorldNeedsUpdate],[H.prototype._setValue_arrayElement,H.prototype._setValue_arrayElement_setNeedsUpdate,H.prototype._setValue_arrayElement_setMatrixWorldNeedsUpdate],[H.prototype._setValue_fromArray,H.prototype._setValue_fromArray_setNeedsUpdate,H.prototype._setValue_fromArray_setMatrixWorldNeedsUpdate]];var vh=new Float32Array(1);var Hn=class s{static{d(this,"Matrix2")}static{s.prototype.isMatrix2=!0}constructor(t,e,n,i){this.elements=[1,0,0,1],t!==void 0&&this.set(t,e,n,i)}identity(){return this.set(1,0,0,1),this}fromArray(t,e=0){for(let n=0;n<4;n++)this.elements[n]=t[n+e];return this}set(t,e,n,i){let r=this.elements;return r[0]=t,r[2]=e,r[1]=n,r[3]=i,this}};typeof __THREE_DEVTOOLS__<"u"&&__THREE_DEVTOOLS__.dispatchEvent(new CustomEvent("register",{detail:{revision:"186"}}));typeof window<"u"&&(window.__THREE__?tt("WARNING: Multiple instances of Three.js being imported."):window.__THREE__="186");var Do=`#ifdef USE_ALPHAHASH
	if ( diffuseColor.a < getAlphaHashThreshold( vPosition ) ) discard;
#endif`,Uo=`#ifdef USE_ALPHAHASH
	const float ALPHA_HASH_SCALE = 0.05;
	float hash2D( vec2 value ) {
		return fract( 1.0e4 * sin( 17.0 * value.x + 0.1 * value.y ) * ( 0.1 + abs( sin( 13.0 * value.y + value.x ) ) ) );
	}
	float hash3D( vec3 value ) {
		return hash2D( vec2( hash2D( value.xy ), value.z ) );
	}
	float getAlphaHashThreshold( vec3 position ) {
		float maxDeriv = max(
			length( dFdx( position.xyz ) ),
			length( dFdy( position.xyz ) )
		);
		float pixScale = 1.0 / ( ALPHA_HASH_SCALE * maxDeriv );
		vec2 pixScales = vec2(
			exp2( floor( log2( pixScale ) ) ),
			exp2( ceil( log2( pixScale ) ) )
		);
		vec2 alpha = vec2(
			hash3D( floor( pixScales.x * position.xyz ) ),
			hash3D( floor( pixScales.y * position.xyz ) )
		);
		float lerpFactor = fract( log2( pixScale ) );
		float x = ( 1.0 - lerpFactor ) * alpha.x + lerpFactor * alpha.y;
		float a = min( lerpFactor, 1.0 - lerpFactor );
		vec3 cases = vec3(
			x * x / ( 2.0 * a * ( 1.0 - a ) ),
			( x - 0.5 * a ) / ( 1.0 - a ),
			1.0 - ( ( 1.0 - x ) * ( 1.0 - x ) / ( 2.0 * a * ( 1.0 - a ) ) )
		);
		float threshold = ( x < ( 1.0 - a ) )
			? ( ( x < a ) ? cases.x : cases.y )
			: cases.z;
		return clamp( threshold , 1.0e-6, 1.0 );
	}
#endif`,Fo=`#ifdef USE_ALPHAMAP
	diffuseColor.a *= texture2D( alphaMap, vAlphaMapUv ).g;
#endif`,Oo=`#ifdef USE_ALPHAMAP
	uniform sampler2D alphaMap;
#endif`,Bo=`#ifdef USE_ALPHATEST
	#ifdef ALPHA_TO_COVERAGE
	diffuseColor.a = smoothstep( alphaTest, alphaTest + fwidth( diffuseColor.a ), diffuseColor.a );
	if ( diffuseColor.a == 0.0 ) discard;
	#else
	if ( diffuseColor.a < alphaTest ) discard;
	#endif
#endif`,zo=`#ifdef USE_ALPHATEST
	uniform float alphaTest;
#endif`,Vo=`#ifdef USE_AOMAP
	float ambientOcclusion = ( texture2D( aoMap, vAoMapUv ).r - 1.0 ) * aoMapIntensity + 1.0;
	reflectedLight.indirectDiffuse *= ambientOcclusion;
	#if defined( USE_CLEARCOAT ) 
		clearcoatSpecularIndirect *= ambientOcclusion;
	#endif
	#if defined( USE_SHEEN ) 
		sheenSpecularIndirect *= ambientOcclusion;
	#endif
	#if defined( USE_ENVMAP ) && defined( STANDARD )
		float dotNV = saturate( dot( geometryNormal, geometryViewDir ) );
		reflectedLight.indirectSpecular *= computeSpecularOcclusion( dotNV, ambientOcclusion, material.roughness );
	#endif
#endif`,ko=`#ifdef USE_AOMAP
	uniform sampler2D aoMap;
	uniform float aoMapIntensity;
#endif`,Go=`#ifdef USE_BATCHING
	#if ! defined( GL_ANGLE_multi_draw )
	#define gl_DrawID _gl_DrawID
	uniform int _gl_DrawID;
	#endif
	uniform highp sampler2D batchingTexture;
	uniform highp usampler2D batchingIdTexture;
	mat4 getBatchingMatrix( const in float i ) {
		int size = textureSize( batchingTexture, 0 ).x;
		int j = int( i ) * 4;
		int x = j % size;
		int y = j / size;
		vec4 v1 = texelFetch( batchingTexture, ivec2( x, y ), 0 );
		vec4 v2 = texelFetch( batchingTexture, ivec2( x + 1, y ), 0 );
		vec4 v3 = texelFetch( batchingTexture, ivec2( x + 2, y ), 0 );
		vec4 v4 = texelFetch( batchingTexture, ivec2( x + 3, y ), 0 );
		return mat4( v1, v2, v3, v4 );
	}
	float getIndirectIndex( const in int i ) {
		int size = textureSize( batchingIdTexture, 0 ).x;
		int x = i % size;
		int y = i / size;
		return float( texelFetch( batchingIdTexture, ivec2( x, y ), 0 ).r );
	}
#endif
#ifdef USE_BATCHING_COLOR
	uniform sampler2D batchingColorTexture;
	vec4 getBatchingColor( const in float i ) {
		int size = textureSize( batchingColorTexture, 0 ).x;
		int j = int( i );
		int x = j % size;
		int y = j / size;
		return texelFetch( batchingColorTexture, ivec2( x, y ), 0 );
	}
#endif`,Ho=`#ifdef USE_BATCHING
	mat4 batchingMatrix = getBatchingMatrix( getIndirectIndex( gl_DrawID ) );
#endif`,Wo=`vec3 transformed = vec3( position );
#ifdef USE_ALPHAHASH
	vPosition = vec3( position );
#endif`,Xo=`vec3 objectNormal = vec3( normal );
#ifdef USE_TANGENT
	vec3 objectTangent = vec3( tangent.xyz );
#endif`,qo=`float G_BlinnPhong_Implicit( ) {
	return 0.25;
}
float D_BlinnPhong( const in float shininess, const in float dotNH ) {
	return RECIPROCAL_PI * ( shininess * 0.5 + 1.0 ) * pow( dotNH, shininess );
}
vec3 BRDF_BlinnPhong( const in vec3 lightDir, const in vec3 viewDir, const in vec3 normal, const in vec3 specularColor, const in float shininess ) {
	vec3 halfDir = normalize( lightDir + viewDir );
	float dotNH = saturate( dot( normal, halfDir ) );
	float dotVH = saturate( dot( viewDir, halfDir ) );
	vec3 F = F_Schlick( specularColor, 1.0, dotVH );
	float G = G_BlinnPhong_Implicit( );
	float D = D_BlinnPhong( shininess, dotNH );
	return F * ( G * D );
} // validated`,Yo=`#ifdef USE_IRIDESCENCE
	const mat3 XYZ_TO_REC709 = mat3(
		 3.2404542, -0.9692660,  0.0556434,
		-1.5371385,  1.8760108, -0.2040259,
		-0.4985314,  0.0415560,  1.0572252
	);
	vec3 Fresnel0ToIor( vec3 fresnel0 ) {
		vec3 sqrtF0 = sqrt( fresnel0 );
		return ( vec3( 1.0 ) + sqrtF0 ) / ( vec3( 1.0 ) - sqrtF0 );
	}
	vec3 IorToFresnel0( vec3 transmittedIor, float incidentIor ) {
		return pow2( ( transmittedIor - vec3( incidentIor ) ) / ( transmittedIor + vec3( incidentIor ) ) );
	}
	float IorToFresnel0( float transmittedIor, float incidentIor ) {
		return pow2( ( transmittedIor - incidentIor ) / ( transmittedIor + incidentIor ));
	}
	vec3 evalSensitivity( float OPD, vec3 shift ) {
		float phase = 2.0 * PI * OPD * 1.0e-9;
		vec3 val = vec3( 5.4856e-13, 4.4201e-13, 5.2481e-13 );
		vec3 pos = vec3( 1.6810e+06, 1.7953e+06, 2.2084e+06 );
		vec3 var = vec3( 4.3278e+09, 9.3046e+09, 6.6121e+09 );
		vec3 xyz = val * sqrt( 2.0 * PI * var ) * cos( pos * phase + shift ) * exp( - pow2( phase ) * var );
		xyz.x += 9.7470e-14 * sqrt( 2.0 * PI * 4.5282e+09 ) * cos( 2.2399e+06 * phase + shift[ 0 ] ) * exp( - 4.5282e+09 * pow2( phase ) );
		xyz /= 1.0685e-7;
		vec3 rgb = XYZ_TO_REC709 * xyz;
		return rgb;
	}
	vec3 evalIridescence( float outsideIOR, float eta2, float cosTheta1, float thinFilmThickness, vec3 baseF0 ) {
		vec3 I;
		float iridescenceIOR = mix( outsideIOR, eta2, smoothstep( 0.0, 0.03, thinFilmThickness ) );
		float sinTheta2Sq = pow2( outsideIOR / iridescenceIOR ) * ( 1.0 - pow2( cosTheta1 ) );
		float cosTheta2Sq = 1.0 - sinTheta2Sq;
		if ( cosTheta2Sq < 0.0 ) {
			return vec3( 1.0 );
		}
		float cosTheta2 = sqrt( cosTheta2Sq );
		float R0 = IorToFresnel0( iridescenceIOR, outsideIOR );
		float R12 = F_Schlick( R0, 1.0, cosTheta1 );
		float T121 = 1.0 - R12;
		float phi12 = 0.0;
		if ( iridescenceIOR < outsideIOR ) phi12 = PI;
		float phi21 = PI - phi12;
		vec3 baseIOR = Fresnel0ToIor( clamp( baseF0, 0.0, 0.9999 ) );		vec3 R1 = IorToFresnel0( baseIOR, iridescenceIOR );
		vec3 R23 = F_Schlick( R1, 1.0, cosTheta2 );
		vec3 phi23 = vec3( 0.0 );
		if ( baseIOR[ 0 ] < iridescenceIOR ) phi23[ 0 ] = PI;
		if ( baseIOR[ 1 ] < iridescenceIOR ) phi23[ 1 ] = PI;
		if ( baseIOR[ 2 ] < iridescenceIOR ) phi23[ 2 ] = PI;
		float OPD = 2.0 * iridescenceIOR * thinFilmThickness * cosTheta2;
		vec3 phi = vec3( phi21 ) + phi23;
		vec3 R123 = clamp( R12 * R23, 1e-5, 0.9999 );
		vec3 r123 = sqrt( R123 );
		vec3 Rs = pow2( T121 ) * R23 / ( vec3( 1.0 ) - R123 );
		vec3 C0 = R12 + Rs;
		I = C0;
		vec3 Cm = Rs - T121;
		for ( int m = 1; m <= 2; ++ m ) {
			Cm *= r123;
			vec3 Sm = 2.0 * evalSensitivity( float( m ) * OPD, float( m ) * phi );
			I += Cm * Sm;
		}
		return max( I, vec3( 0.0 ) );
	}
#endif`,$o=`#ifdef USE_BUMPMAP
	uniform sampler2D bumpMap;
	uniform float bumpScale;
	vec2 dHdxy_fwd() {
		vec2 dSTdx = dFdx( vBumpMapUv );
		vec2 dSTdy = dFdy( vBumpMapUv );
		float Hll = bumpScale * texture2D( bumpMap, vBumpMapUv ).x;
		float dBx = bumpScale * texture2D( bumpMap, vBumpMapUv + dSTdx ).x - Hll;
		float dBy = bumpScale * texture2D( bumpMap, vBumpMapUv + dSTdy ).x - Hll;
		return vec2( dBx, dBy );
	}
	vec3 perturbNormalArb( vec3 surf_pos, vec3 surf_norm, vec2 dHdxy, float faceDirection ) {
		vec3 vSigmaX = normalize( dFdx( surf_pos.xyz ) );
		vec3 vSigmaY = normalize( dFdy( surf_pos.xyz ) );
		vec3 vN = surf_norm;
		vec3 R1 = cross( vSigmaY, vN );
		vec3 R2 = cross( vN, vSigmaX );
		float fDet = dot( vSigmaX, R1 ) * faceDirection;
		vec3 vGrad = sign( fDet ) * ( dHdxy.x * R1 + dHdxy.y * R2 );
		return normalize( abs( fDet ) * surf_norm - vGrad );
	}
#endif`,Zo=`#if NUM_CLIPPING_PLANES > 0
	vec4 plane;
	#ifdef ALPHA_TO_COVERAGE
		float distanceToPlane, distanceGradient;
		float clipOpacity = 1.0;
		#pragma unroll_loop_start
		for ( int i = 0; i < UNION_CLIPPING_PLANES; i ++ ) {
			plane = clippingPlanes[ i ];
			distanceToPlane = - dot( vClipPosition, plane.xyz ) + plane.w;
			distanceGradient = fwidth( distanceToPlane ) / 2.0;
			clipOpacity *= smoothstep( - distanceGradient, distanceGradient, distanceToPlane );
			if ( clipOpacity == 0.0 ) discard;
		}
		#pragma unroll_loop_end
		#if UNION_CLIPPING_PLANES < NUM_CLIPPING_PLANES
			float unionClipOpacity = 1.0;
			#pragma unroll_loop_start
			for ( int i = UNION_CLIPPING_PLANES; i < NUM_CLIPPING_PLANES; i ++ ) {
				plane = clippingPlanes[ i ];
				distanceToPlane = - dot( vClipPosition, plane.xyz ) + plane.w;
				distanceGradient = fwidth( distanceToPlane ) / 2.0;
				unionClipOpacity *= 1.0 - smoothstep( - distanceGradient, distanceGradient, distanceToPlane );
			}
			#pragma unroll_loop_end
			clipOpacity *= 1.0 - unionClipOpacity;
		#endif
		diffuseColor.a *= clipOpacity;
		if ( diffuseColor.a == 0.0 ) discard;
	#else
		#pragma unroll_loop_start
		for ( int i = 0; i < UNION_CLIPPING_PLANES; i ++ ) {
			plane = clippingPlanes[ i ];
			if ( dot( vClipPosition, plane.xyz ) > plane.w ) discard;
		}
		#pragma unroll_loop_end
		#if UNION_CLIPPING_PLANES < NUM_CLIPPING_PLANES
			bool clipped = true;
			#pragma unroll_loop_start
			for ( int i = UNION_CLIPPING_PLANES; i < NUM_CLIPPING_PLANES; i ++ ) {
				plane = clippingPlanes[ i ];
				clipped = ( dot( vClipPosition, plane.xyz ) > plane.w ) && clipped;
			}
			#pragma unroll_loop_end
			if ( clipped ) discard;
		#endif
	#endif
#endif`,Jo=`#if NUM_CLIPPING_PLANES > 0
	varying vec3 vClipPosition;
	uniform vec4 clippingPlanes[ NUM_CLIPPING_PLANES ];
#endif`,Ko=`#if NUM_CLIPPING_PLANES > 0
	varying vec3 vClipPosition;
#endif`,Qo=`#if NUM_CLIPPING_PLANES > 0
	vClipPosition = - mvPosition.xyz;
#endif`,jo=`#if defined( USE_COLOR ) || defined( USE_COLOR_ALPHA )
	diffuseColor *= vColor;
#endif`,ta=`#if defined( USE_COLOR ) || defined( USE_COLOR_ALPHA )
	varying vec4 vColor;
#endif`,ea=`#if defined( USE_COLOR ) || defined( USE_COLOR_ALPHA ) || defined( USE_INSTANCING_COLOR ) || defined( USE_BATCHING_COLOR )
	varying vec4 vColor;
#endif`,na=`#if defined( USE_COLOR ) || defined( USE_COLOR_ALPHA ) || defined( USE_INSTANCING_COLOR ) || defined( USE_BATCHING_COLOR )
	vColor = vec4( 1.0 );
#endif
#ifdef USE_COLOR_ALPHA
	vColor *= color;
#elif defined( USE_COLOR )
	vColor.rgb *= color;
#endif
#ifdef USE_INSTANCING_COLOR
	vColor.rgb *= instanceColor.rgb;
#endif
#ifdef USE_BATCHING_COLOR
	vColor *= getBatchingColor( getIndirectIndex( gl_DrawID ) );
#endif`,ia=`#define PI 3.141592653589793
#define PI2 6.283185307179586
#define PI_HALF 1.5707963267948966
#define RECIPROCAL_PI 0.3183098861837907
#define RECIPROCAL_PI2 0.15915494309189535
#define EPSILON 1e-6
#ifndef saturate
#define saturate( a ) clamp( a, 0.0, 1.0 )
#endif
#define whiteComplement( a ) ( 1.0 - saturate( a ) )
float pow2( const in float x ) { return x*x; }
vec3 pow2( const in vec3 x ) { return x*x; }
float pow3( const in float x ) { return x*x*x; }
float pow4( const in float x ) { float x2 = x*x; return x2*x2; }
float max3( const in vec3 v ) { return max( max( v.x, v.y ), v.z ); }
float average( const in vec3 v ) { return dot( v, vec3( 0.3333333 ) ); }
highp float rand( const in vec2 uv ) {
	const highp float a = 12.9898, b = 78.233, c = 43758.5453;
	highp float dt = dot( uv.xy, vec2( a,b ) ), sn = mod( dt, PI );
	return fract( sin( sn ) * c );
}
#ifdef HIGH_PRECISION
	float precisionSafeLength( vec3 v ) { return length( v ); }
#else
	float precisionSafeLength( vec3 v ) {
		float maxComponent = max3( abs( v ) );
		return length( v / maxComponent ) * maxComponent;
	}
#endif
struct IncidentLight {
	vec3 color;
	vec3 direction;
	bool visible;
};
struct ReflectedLight {
	vec3 directDiffuse;
	vec3 directSpecular;
	vec3 indirectDiffuse;
	vec3 indirectSpecular;
};
#ifdef USE_ALPHAHASH
	varying vec3 vPosition;
#endif
vec3 transformDirection( in vec3 dir, in mat4 matrix ) {
	return normalize( ( matrix * vec4( dir, 0.0 ) ).xyz );
}
#define inverseTransformDirection transformDirectionByInverseViewMatrix
vec3 transformNormalByInverseViewMatrix( in vec3 normal, in mat4 viewMatrix ) {
	return normalize( ( vec4( normal, 0.0 ) * viewMatrix ).xyz );
}
vec3 transformDirectionByInverseViewMatrix( in vec3 dir, in mat4 viewMatrix ) {
	return normalize( ( vec4( dir, 0.0 ) * viewMatrix ).xyz );
}
bool isPerspectiveMatrix( mat4 m ) {
	return m[ 2 ][ 3 ] == - 1.0;
}
vec2 equirectUv( in vec3 dir ) {
	float u = atan( dir.z, dir.x ) * RECIPROCAL_PI2 + 0.5;
	float v = asin( clamp( dir.y, - 1.0, 1.0 ) ) * RECIPROCAL_PI + 0.5;
	return vec2( u, v );
}
vec3 BRDF_Lambert( const in vec3 diffuseColor ) {
	return RECIPROCAL_PI * diffuseColor;
}
vec3 F_Schlick( const in vec3 f0, const in float f90, const in float dotVH ) {
	float fresnel = exp2( ( - 5.55473 * dotVH - 6.98316 ) * dotVH );
	return f0 * ( 1.0 - fresnel ) + ( f90 * fresnel );
}
float F_Schlick( const in float f0, const in float f90, const in float dotVH ) {
	float fresnel = exp2( ( - 5.55473 * dotVH - 6.98316 ) * dotVH );
	return f0 * ( 1.0 - fresnel ) + ( f90 * fresnel );
} // validated`,sa=`#ifdef ENVMAP_TYPE_CUBE_UV
	#define cubeUV_minMipLevel 4.0
	#define cubeUV_minTileSize 16.0
	float getFace( vec3 direction ) {
		vec3 absDirection = abs( direction );
		float face = - 1.0;
		if ( absDirection.x > absDirection.z ) {
			if ( absDirection.x > absDirection.y )
				face = direction.x > 0.0 ? 0.0 : 3.0;
			else
				face = direction.y > 0.0 ? 1.0 : 4.0;
		} else {
			if ( absDirection.z > absDirection.y )
				face = direction.z > 0.0 ? 2.0 : 5.0;
			else
				face = direction.y > 0.0 ? 1.0 : 4.0;
		}
		return face;
	}
	vec2 getUV( vec3 direction, float face ) {
		vec2 uv;
		if ( face == 0.0 ) {
			uv = vec2( direction.z, direction.y ) / abs( direction.x );
		} else if ( face == 1.0 ) {
			uv = vec2( - direction.x, - direction.z ) / abs( direction.y );
		} else if ( face == 2.0 ) {
			uv = vec2( - direction.x, direction.y ) / abs( direction.z );
		} else if ( face == 3.0 ) {
			uv = vec2( - direction.z, direction.y ) / abs( direction.x );
		} else if ( face == 4.0 ) {
			uv = vec2( - direction.x, direction.z ) / abs( direction.y );
		} else {
			uv = vec2( direction.x, direction.y ) / abs( direction.z );
		}
		return 0.5 * ( uv + 1.0 );
	}
	vec3 bilinearCubeUV( sampler2D envMap, vec3 direction, float mipInt ) {
		float face = getFace( direction );
		float filterInt = max( cubeUV_minMipLevel - mipInt, 0.0 );
		mipInt = max( mipInt, cubeUV_minMipLevel );
		float faceSize = exp2( mipInt );
		highp vec2 uv = getUV( direction, face ) * ( faceSize - 2.0 ) + 1.0;
		if ( face > 2.0 ) {
			uv.y += faceSize;
			face -= 3.0;
		}
		uv.x += face * faceSize;
		uv.x += filterInt * 3.0 * cubeUV_minTileSize;
		uv.y += 4.0 * ( exp2( CUBEUV_MAX_MIP ) - faceSize );
		uv.x *= CUBEUV_TEXEL_WIDTH;
		uv.y *= CUBEUV_TEXEL_HEIGHT;
		#ifdef texture2DGradEXT
			return texture2DGradEXT( envMap, uv, vec2( 0.0 ), vec2( 0.0 ) ).rgb;
		#else
			return texture2D( envMap, uv ).rgb;
		#endif
	}
	#define cubeUV_r0 1.0
	#define cubeUV_m0 - 2.0
	#define cubeUV_r1 0.8
	#define cubeUV_m1 - 1.0
	#define cubeUV_r4 0.4
	#define cubeUV_m4 2.0
	#define cubeUV_r5 0.305
	#define cubeUV_m5 3.0
	#define cubeUV_r6 0.21
	#define cubeUV_m6 4.0
	float roughnessToMip( float roughness ) {
		float mip = 0.0;
		if ( roughness >= cubeUV_r1 ) {
			mip = ( cubeUV_r0 - roughness ) * ( cubeUV_m1 - cubeUV_m0 ) / ( cubeUV_r0 - cubeUV_r1 ) + cubeUV_m0;
		} else if ( roughness >= cubeUV_r4 ) {
			mip = ( cubeUV_r1 - roughness ) * ( cubeUV_m4 - cubeUV_m1 ) / ( cubeUV_r1 - cubeUV_r4 ) + cubeUV_m1;
		} else if ( roughness >= cubeUV_r5 ) {
			mip = ( cubeUV_r4 - roughness ) * ( cubeUV_m5 - cubeUV_m4 ) / ( cubeUV_r4 - cubeUV_r5 ) + cubeUV_m4;
		} else if ( roughness >= cubeUV_r6 ) {
			mip = ( cubeUV_r5 - roughness ) * ( cubeUV_m6 - cubeUV_m5 ) / ( cubeUV_r5 - cubeUV_r6 ) + cubeUV_m5;
		} else {
			mip = - 2.0 * log2( 1.16 * roughness );		}
		return mip;
	}
	vec4 textureCubeUV( sampler2D envMap, vec3 sampleDir, float roughness ) {
		float mip = clamp( roughnessToMip( roughness ), cubeUV_m0, CUBEUV_MAX_MIP );
		float mipF = fract( mip );
		float mipInt = floor( mip );
		vec3 color0 = bilinearCubeUV( envMap, sampleDir, mipInt );
		if ( mipF == 0.0 ) {
			return vec4( color0, 1.0 );
		} else {
			vec3 color1 = bilinearCubeUV( envMap, sampleDir, mipInt + 1.0 );
			return vec4( mix( color0, color1, mipF ), 1.0 );
		}
	}
#endif`,ra=`vec3 transformedNormal = objectNormal;
#ifdef USE_TANGENT
	vec3 transformedTangent = objectTangent;
#endif
#ifdef USE_BATCHING
	mat3 bm = mat3( batchingMatrix );
	transformedNormal /= vec3( dot( bm[ 0 ], bm[ 0 ] ), dot( bm[ 1 ], bm[ 1 ] ), dot( bm[ 2 ], bm[ 2 ] ) );
	transformedNormal = bm * transformedNormal;
	#ifdef USE_TANGENT
		transformedTangent = bm * transformedTangent;
	#endif
#endif
#ifdef USE_INSTANCING
	mat3 im = mat3( instanceMatrix );
	transformedNormal /= vec3( dot( im[ 0 ], im[ 0 ] ), dot( im[ 1 ], im[ 1 ] ), dot( im[ 2 ], im[ 2 ] ) );
	transformedNormal = im * transformedNormal;
	#ifdef USE_TANGENT
		transformedTangent = im * transformedTangent;
	#endif
#endif
transformedNormal = normalMatrix * transformedNormal;
#ifdef FLIP_SIDED
	transformedNormal = - transformedNormal;
#endif
#ifdef USE_TANGENT
	transformedTangent = ( modelViewMatrix * vec4( transformedTangent, 0.0 ) ).xyz;
#endif`,oa=`#ifdef USE_DISPLACEMENTMAP
	uniform sampler2D displacementMap;
	uniform float displacementScale;
	uniform float displacementBias;
#endif`,aa=`#ifdef USE_DISPLACEMENTMAP
	transformed += normalize( objectNormal ) * ( texture2D( displacementMap, vDisplacementMapUv ).x * displacementScale + displacementBias );
#endif`,ca=`#ifdef USE_EMISSIVEMAP
	vec4 emissiveColor = texture2D( emissiveMap, vEmissiveMapUv );
	#ifdef DECODE_VIDEO_TEXTURE_EMISSIVE
		emissiveColor = sRGBTransferEOTF( emissiveColor );
	#endif
	totalEmissiveRadiance *= emissiveColor.rgb;
#endif`,la=`#ifdef USE_EMISSIVEMAP
	uniform sampler2D emissiveMap;
#endif`,ha="gl_FragColor = linearToOutputTexel( gl_FragColor );",ua=`vec4 LinearTransferOETF( in vec4 value ) {
	return value;
}
vec4 sRGBTransferEOTF( in vec4 value ) {
	return vec4( mix( pow( value.rgb * 0.9478672986 + vec3( 0.0521327014 ), vec3( 2.4 ) ), value.rgb * 0.0773993808, vec3( lessThanEqual( value.rgb, vec3( 0.04045 ) ) ) ), value.a );
}
vec4 sRGBTransferOETF( in vec4 value ) {
	return vec4( mix( pow( value.rgb, vec3( 0.41666 ) ) * 1.055 - vec3( 0.055 ), value.rgb * 12.92, vec3( lessThanEqual( value.rgb, vec3( 0.0031308 ) ) ) ), value.a );
}`,da=`#ifdef USE_ENVMAP
	#ifdef ENV_WORLDPOS
		vec3 cameraToFrag;
		if ( isOrthographic ) {
			cameraToFrag = normalize( vec3( - viewMatrix[ 0 ][ 2 ], - viewMatrix[ 1 ][ 2 ], - viewMatrix[ 2 ][ 2 ] ) );
		} else {
			cameraToFrag = normalize( vWorldPosition - cameraPosition );
		}
		vec3 worldNormal = transformNormalByInverseViewMatrix( normal, viewMatrix );
		#ifdef ENVMAP_MODE_REFLECTION
			vec3 reflectVec = reflect( cameraToFrag, worldNormal );
		#else
			vec3 reflectVec = refract( cameraToFrag, worldNormal, refractionRatio );
		#endif
	#else
		vec3 reflectVec = vReflect;
	#endif
	#ifdef ENVMAP_TYPE_CUBE
		vec4 envColor = textureCube( envMap, envMapRotation * reflectVec );
		#ifdef ENVMAP_BLENDING_MULTIPLY
			outgoingLight = mix( outgoingLight, outgoingLight * envColor.xyz, specularStrength * reflectivity );
		#elif defined( ENVMAP_BLENDING_MIX )
			outgoingLight = mix( outgoingLight, envColor.xyz, specularStrength * reflectivity );
		#elif defined( ENVMAP_BLENDING_ADD )
			outgoingLight += envColor.xyz * specularStrength * reflectivity;
		#endif
	#endif
#endif`,fa=`#ifdef USE_ENVMAP
	uniform float envMapIntensity;
	uniform mat3 envMapRotation;
	#ifdef ENVMAP_TYPE_CUBE
		uniform samplerCube envMap;
	#else
		uniform sampler2D envMap;
	#endif
#endif`,pa=`#ifdef USE_ENVMAP
	uniform float reflectivity;
	#if defined( USE_BUMPMAP ) || defined( USE_NORMALMAP ) || defined( PHONG ) || defined( LAMBERT )
		#define ENV_WORLDPOS
	#endif
	#ifdef ENV_WORLDPOS
		varying vec3 vWorldPosition;
		uniform float refractionRatio;
	#else
		varying vec3 vReflect;
	#endif
#endif`,ma=`#ifdef USE_ENVMAP
	#if defined( USE_BUMPMAP ) || defined( USE_NORMALMAP ) || defined( PHONG ) || defined( LAMBERT )
		#define ENV_WORLDPOS
	#endif
	#ifdef ENV_WORLDPOS
		
		varying vec3 vWorldPosition;
	#else
		varying vec3 vReflect;
		uniform float refractionRatio;
	#endif
#endif`,ga=`#ifdef USE_ENVMAP
	#ifdef ENV_WORLDPOS
		vWorldPosition = worldPosition.xyz;
	#else
		vec3 cameraToVertex;
		if ( isOrthographic ) {
			cameraToVertex = normalize( vec3( - viewMatrix[ 0 ][ 2 ], - viewMatrix[ 1 ][ 2 ], - viewMatrix[ 2 ][ 2 ] ) );
		} else {
			cameraToVertex = normalize( worldPosition.xyz - cameraPosition );
		}
		vec3 worldNormal = transformNormalByInverseViewMatrix( transformedNormal, viewMatrix );
		#ifdef ENVMAP_MODE_REFLECTION
			vReflect = reflect( cameraToVertex, worldNormal );
		#else
			vReflect = refract( cameraToVertex, worldNormal, refractionRatio );
		#endif
	#endif
#endif`,_a=`#ifdef USE_FOG
	vFogDepth = - mvPosition.z;
#endif`,xa=`#ifdef USE_FOG
	varying float vFogDepth;
#endif`,ya=`#ifdef USE_FOG
	#ifdef FOG_EXP2
		float fogFactor = 1.0 - exp( - fogDensity * fogDensity * vFogDepth * vFogDepth );
	#else
		float fogFactor = smoothstep( fogNear, fogFar, vFogDepth );
	#endif
	gl_FragColor.rgb = mix( gl_FragColor.rgb, fogColor, fogFactor );
#endif`,va=`#ifdef USE_FOG
	uniform vec3 fogColor;
	varying float vFogDepth;
	#ifdef FOG_EXP2
		uniform float fogDensity;
	#else
		uniform float fogNear;
		uniform float fogFar;
	#endif
#endif`,Ma=`#ifdef USE_GRADIENTMAP
	uniform sampler2D gradientMap;
#endif
vec3 getGradientIrradiance( vec3 normal, vec3 lightDirection ) {
	float dotNL = dot( normal, lightDirection );
	vec2 coord = vec2( dotNL * 0.5 + 0.5, 0.0 );
	#ifdef USE_GRADIENTMAP
		return vec3( texture2D( gradientMap, coord ).r );
	#else
		vec2 fw = fwidth( coord ) * 0.5;
		return mix( vec3( 0.7 ), vec3( 1.0 ), smoothstep( 0.7 - fw.x, 0.7 + fw.x, coord.x ) );
	#endif
}`,Sa=`#ifdef USE_LIGHTMAP
	uniform sampler2D lightMap;
	uniform float lightMapIntensity;
#endif`,ba=`LambertMaterial material;
material.diffuseColor = diffuseColor.rgb;
material.specularStrength = specularStrength;`,Ea=`varying vec3 vViewPosition;
struct LambertMaterial {
	vec3 diffuseColor;
	float specularStrength;
};
void RE_Direct_Lambert( const in IncidentLight directLight, const in vec3 geometryPosition, const in vec3 geometryNormal, const in vec3 geometryViewDir, const in vec3 geometryClearcoatNormal, const in LambertMaterial material, inout ReflectedLight reflectedLight ) {
	float dotNL = saturate( dot( geometryNormal, directLight.direction ) );
	vec3 irradiance = dotNL * directLight.color;
	reflectedLight.directDiffuse += irradiance * BRDF_Lambert( material.diffuseColor );
}
void RE_IndirectDiffuse_Lambert( const in vec3 irradiance, const in vec3 geometryPosition, const in vec3 geometryNormal, const in vec3 geometryViewDir, const in vec3 geometryClearcoatNormal, const in LambertMaterial material, inout ReflectedLight reflectedLight ) {
	reflectedLight.indirectDiffuse += irradiance * BRDF_Lambert( material.diffuseColor );
}
#define RE_Direct				RE_Direct_Lambert
#define RE_IndirectDiffuse		RE_IndirectDiffuse_Lambert`,Aa=`uniform bool receiveShadow;
uniform vec3 ambientLightColor;
#if defined( USE_LIGHT_PROBES )
	uniform vec3 lightProbe[ 9 ];
#endif
vec3 shGetIrradianceAt( in vec3 normal, in vec3 shCoefficients[ 9 ] ) {
	float x = normal.x, y = normal.y, z = normal.z;
	vec3 result = shCoefficients[ 0 ] * 0.886227;
	result += shCoefficients[ 1 ] * 2.0 * 0.511664 * y;
	result += shCoefficients[ 2 ] * 2.0 * 0.511664 * z;
	result += shCoefficients[ 3 ] * 2.0 * 0.511664 * x;
	result += shCoefficients[ 4 ] * 2.0 * 0.429043 * x * y;
	result += shCoefficients[ 5 ] * 2.0 * 0.429043 * y * z;
	result += shCoefficients[ 6 ] * ( 0.743125 * z * z - 0.247708 );
	result += shCoefficients[ 7 ] * 2.0 * 0.429043 * x * z;
	result += shCoefficients[ 8 ] * 0.429043 * ( x * x - y * y );
	return result;
}
vec3 getLightProbeIrradiance( const in vec3 lightProbe[ 9 ], const in vec3 normal ) {
	vec3 worldNormal = transformNormalByInverseViewMatrix( normal, viewMatrix );
	vec3 irradiance = shGetIrradianceAt( worldNormal, lightProbe );
	return irradiance;
}
vec3 getAmbientLightIrradiance( const in vec3 ambientLightColor ) {
	vec3 irradiance = ambientLightColor;
	return irradiance;
}
float getDistanceAttenuation( const in float lightDistance, const in float cutoffDistance, const in float decayExponent ) {
	float distanceFalloff = 1.0 / max( pow( lightDistance, decayExponent ), 0.01 );
	if ( cutoffDistance > 0.0 ) {
		distanceFalloff *= pow2( saturate( 1.0 - pow4( lightDistance / cutoffDistance ) ) );
	}
	return distanceFalloff;
}
float getSpotAttenuation( const in float coneCosine, const in float penumbraCosine, const in float angleCosine ) {
	return smoothstep( coneCosine, penumbraCosine, angleCosine );
}
#if NUM_SUN_LIGHTS > 0
	struct SunLight {
		vec3 direction;
		vec3 color;
	};
	uniform SunLight sunLights[ NUM_SUN_LIGHTS ];
	void getSunLightInfo( const in SunLight sunLight, out IncidentLight light ) {
		light.color = sunLight.color;
		light.direction = sunLight.direction;
		light.visible = true;
	}
#endif
#if NUM_DIR_LIGHTS > 0
	struct DirectionalLight {
		vec3 direction;
		vec3 color;
	};
	uniform DirectionalLight directionalLights[ NUM_DIR_LIGHTS ];
	void getDirectionalLightInfo( const in DirectionalLight directionalLight, out IncidentLight light ) {
		light.color = directionalLight.color;
		light.direction = directionalLight.direction;
		light.visible = true;
	}
#endif
#if NUM_POINT_LIGHTS > 0
	struct PointLight {
		vec3 position;
		vec3 color;
		float distance;
		float decay;
	};
	uniform PointLight pointLights[ NUM_POINT_LIGHTS ];
	void getPointLightInfo( const in PointLight pointLight, const in vec3 geometryPosition, out IncidentLight light ) {
		vec3 lVector = pointLight.position - geometryPosition;
		light.direction = normalize( lVector );
		float lightDistance = length( lVector );
		light.color = pointLight.color;
		light.color *= getDistanceAttenuation( lightDistance, pointLight.distance, pointLight.decay );
		light.visible = ( light.color != vec3( 0.0 ) );
	}
#endif
#if NUM_SPOT_LIGHTS > 0
	struct SpotLight {
		vec3 position;
		vec3 direction;
		vec3 color;
		float distance;
		float decay;
		float coneCos;
		float penumbraCos;
	};
	uniform SpotLight spotLights[ NUM_SPOT_LIGHTS ];
	void getSpotLightInfo( const in SpotLight spotLight, const in vec3 geometryPosition, out IncidentLight light ) {
		vec3 lVector = spotLight.position - geometryPosition;
		light.direction = normalize( lVector );
		float angleCos = dot( light.direction, spotLight.direction );
		float spotAttenuation = getSpotAttenuation( spotLight.coneCos, spotLight.penumbraCos, angleCos );
		if ( spotAttenuation > 0.0 ) {
			float lightDistance = length( lVector );
			light.color = spotLight.color * spotAttenuation;
			light.color *= getDistanceAttenuation( lightDistance, spotLight.distance, spotLight.decay );
			light.visible = ( light.color != vec3( 0.0 ) );
		} else {
			light.color = vec3( 0.0 );
			light.visible = false;
		}
	}
#endif
#if NUM_RECT_AREA_LIGHTS > 0
	struct RectAreaLight {
		vec3 color;
		vec3 position;
		vec3 halfWidth;
		vec3 halfHeight;
	};
	uniform sampler2D ltc_1;	uniform sampler2D ltc_2;
	uniform RectAreaLight rectAreaLights[ NUM_RECT_AREA_LIGHTS ];
#endif
#if NUM_HEMI_LIGHTS > 0
	struct HemisphereLight {
		vec3 direction;
		vec3 skyColor;
		vec3 groundColor;
	};
	uniform HemisphereLight hemisphereLights[ NUM_HEMI_LIGHTS ];
	vec3 getHemisphereLightIrradiance( const in HemisphereLight hemiLight, const in vec3 normal ) {
		float dotNL = dot( normal, hemiLight.direction );
		float hemiDiffuseWeight = 0.5 * dotNL + 0.5;
		vec3 irradiance = mix( hemiLight.groundColor, hemiLight.skyColor, hemiDiffuseWeight );
		return irradiance;
	}
#endif
#include <lightprobes_pars_fragment>`,Ta=`#ifdef USE_ENVMAP
	vec3 getIBLIrradiance( const in vec3 normal ) {
		#ifdef ENVMAP_TYPE_CUBE_UV
			vec3 worldNormal = transformNormalByInverseViewMatrix( normal, viewMatrix );
			vec4 envMapColor = textureCubeUV( envMap, envMapRotation * worldNormal, 1.0 );
			return PI * envMapColor.rgb * envMapIntensity;
		#else
			return vec3( 0.0 );
		#endif
	}
	vec3 getIBLRadiance( const in vec3 viewDir, const in vec3 normal, const in float roughness ) {
		#ifdef ENVMAP_TYPE_CUBE_UV
			vec3 reflectVec = reflect( - viewDir, normal );
			reflectVec = normalize( mix( reflectVec, normal, pow4( roughness ) ) );
			reflectVec = transformDirectionByInverseViewMatrix( reflectVec, viewMatrix );
			vec4 envMapColor = textureCubeUV( envMap, envMapRotation * reflectVec, roughness );
			return envMapColor.rgb * envMapIntensity;
		#else
			return vec3( 0.0 );
		#endif
	}
	#ifdef USE_RETROREFLECTION
		vec3 getIBLRetroRadiance( const in vec3 viewDir, const in vec3 normal, const in float roughness ) {
			#ifdef ENVMAP_TYPE_CUBE_UV
				vec3 retroVec = normalize( mix( viewDir, normal, pow4( roughness ) ) );
				retroVec = transformDirectionByInverseViewMatrix( retroVec, viewMatrix );
				vec4 envMapColor = textureCubeUV( envMap, envMapRotation * retroVec, roughness );
				return envMapColor.rgb * envMapIntensity;
			#else
				return vec3( 0.0 );
			#endif
		}
	#endif
	#ifdef USE_ANISOTROPY
		vec3 getIBLAnisotropyRadiance( const in vec3 viewDir, const in vec3 normal, const in float roughness, const in vec3 bitangent, const in float anisotropy ) {
			#ifdef ENVMAP_TYPE_CUBE_UV
				vec3 bentNormal = cross( bitangent, viewDir );
				bentNormal = normalize( cross( bentNormal, bitangent ) );
				bentNormal = normalize( mix( bentNormal, normal, pow2( pow2( 1.0 - anisotropy * ( 1.0 - roughness ) ) ) ) );
				return getIBLRadiance( viewDir, bentNormal, roughness );
			#else
				return vec3( 0.0 );
			#endif
		}
		#ifdef USE_RETROREFLECTION
			vec3 getIBLAnisotropyRetroRadiance( const in vec3 viewDir, const in vec3 normal, const in float roughness, const in vec3 bitangent, const in float anisotropy ) {
				#ifdef ENVMAP_TYPE_CUBE_UV
					vec3 bentNormal = cross( bitangent, viewDir );
					bentNormal = normalize( cross( bentNormal, bitangent ) );
					bentNormal = normalize( mix( bentNormal, normal, pow2( pow2( 1.0 - anisotropy * ( 1.0 - roughness ) ) ) ) );
					return getIBLRetroRadiance( viewDir, bentNormal, roughness );
				#else
					return vec3( 0.0 );
				#endif
			}
		#endif
	#endif
#endif`,wa=`ToonMaterial material;
material.diffuseColor = diffuseColor.rgb;`,Ca=`varying vec3 vViewPosition;
struct ToonMaterial {
	vec3 diffuseColor;
};
void RE_Direct_Toon( const in IncidentLight directLight, const in vec3 geometryPosition, const in vec3 geometryNormal, const in vec3 geometryViewDir, const in vec3 geometryClearcoatNormal, const in ToonMaterial material, inout ReflectedLight reflectedLight ) {
	vec3 irradiance = getGradientIrradiance( geometryNormal, directLight.direction ) * directLight.color;
	reflectedLight.directDiffuse += irradiance * BRDF_Lambert( material.diffuseColor );
}
void RE_IndirectDiffuse_Toon( const in vec3 irradiance, const in vec3 geometryPosition, const in vec3 geometryNormal, const in vec3 geometryViewDir, const in vec3 geometryClearcoatNormal, const in ToonMaterial material, inout ReflectedLight reflectedLight ) {
	reflectedLight.indirectDiffuse += irradiance * BRDF_Lambert( material.diffuseColor );
}
#define RE_Direct				RE_Direct_Toon
#define RE_IndirectDiffuse		RE_IndirectDiffuse_Toon`,Ra=`BlinnPhongMaterial material;
material.diffuseColor = diffuseColor.rgb;
material.specularColor = specular;
material.specularShininess = shininess;
material.specularStrength = specularStrength;`,Ia=`varying vec3 vViewPosition;
struct BlinnPhongMaterial {
	vec3 diffuseColor;
	vec3 specularColor;
	float specularShininess;
	float specularStrength;
};
void RE_Direct_BlinnPhong( const in IncidentLight directLight, const in vec3 geometryPosition, const in vec3 geometryNormal, const in vec3 geometryViewDir, const in vec3 geometryClearcoatNormal, const in BlinnPhongMaterial material, inout ReflectedLight reflectedLight ) {
	float dotNL = saturate( dot( geometryNormal, directLight.direction ) );
	vec3 irradiance = dotNL * directLight.color;
	reflectedLight.directDiffuse += irradiance * BRDF_Lambert( material.diffuseColor );
	reflectedLight.directSpecular += irradiance * BRDF_BlinnPhong( directLight.direction, geometryViewDir, geometryNormal, material.specularColor, material.specularShininess ) * material.specularStrength;
}
void RE_IndirectDiffuse_BlinnPhong( const in vec3 irradiance, const in vec3 geometryPosition, const in vec3 geometryNormal, const in vec3 geometryViewDir, const in vec3 geometryClearcoatNormal, const in BlinnPhongMaterial material, inout ReflectedLight reflectedLight ) {
	reflectedLight.indirectDiffuse += irradiance * BRDF_Lambert( material.diffuseColor );
}
#define RE_Direct				RE_Direct_BlinnPhong
#define RE_IndirectDiffuse		RE_IndirectDiffuse_BlinnPhong`,Pa=`PhysicalMaterial material;
material.diffuseColor = diffuseColor.rgb;
material.diffuseContribution = diffuseColor.rgb * ( 1.0 - metalnessFactor );
material.metalness = metalnessFactor;
vec3 dxy = max( abs( dFdx( nonPerturbedNormal ) ), abs( dFdy( nonPerturbedNormal ) ) );
float geometryRoughness = max( max( dxy.x, dxy.y ), dxy.z );
material.roughness = max( roughnessFactor, 0.0525 );material.roughness += geometryRoughness;
material.roughness = min( material.roughness, 1.0 );
#ifdef IOR
	material.ior = ior;
	#ifdef USE_SPECULAR
		float specularIntensityFactor = specularIntensity;
		vec3 specularColorFactor = specularColor;
		#ifdef USE_SPECULAR_COLORMAP
			specularColorFactor *= texture2D( specularColorMap, vSpecularColorMapUv ).rgb;
		#endif
		#ifdef USE_SPECULAR_INTENSITYMAP
			specularIntensityFactor *= texture2D( specularIntensityMap, vSpecularIntensityMapUv ).a;
		#endif
		material.specularF90 = mix( specularIntensityFactor, 1.0, metalnessFactor );
	#else
		float specularIntensityFactor = 1.0;
		vec3 specularColorFactor = vec3( 1.0 );
		material.specularF90 = 1.0;
	#endif
	material.specularColor = min( pow2( ( material.ior - 1.0 ) / ( material.ior + 1.0 ) ) * specularColorFactor, vec3( 1.0 ) ) * specularIntensityFactor;
	material.specularColorBlended = mix( material.specularColor, diffuseColor.rgb, metalnessFactor );
#else
	material.specularColor = vec3( 0.04 );
	material.specularColorBlended = mix( material.specularColor, diffuseColor.rgb, metalnessFactor );
	material.specularF90 = 1.0;
#endif
#ifdef USE_CLEARCOAT
	material.clearcoat = clearcoat;
	material.clearcoatRoughness = clearcoatRoughness;
	material.clearcoatF0 = vec3( 0.04 );
	material.clearcoatF90 = 1.0;
	#ifdef USE_CLEARCOATMAP
		material.clearcoat *= texture2D( clearcoatMap, vClearcoatMapUv ).x;
	#endif
	#ifdef USE_CLEARCOAT_ROUGHNESSMAP
		material.clearcoatRoughness *= texture2D( clearcoatRoughnessMap, vClearcoatRoughnessMapUv ).y;
	#endif
	material.clearcoat = saturate( material.clearcoat );	material.clearcoatRoughness = max( material.clearcoatRoughness, 0.0525 );
	material.clearcoatRoughness += geometryRoughness;
	material.clearcoatRoughness = min( material.clearcoatRoughness, 1.0 );
#endif
#ifdef USE_DISPERSION
	material.dispersion = dispersion;
#endif
#ifdef USE_RETROREFLECTION
	material.retroreflectivity = retroreflectivity;
#endif
#ifdef USE_IRIDESCENCE
	material.iridescence = iridescence;
	material.iridescenceIOR = iridescenceIOR;
	#ifdef USE_IRIDESCENCEMAP
		material.iridescence *= texture2D( iridescenceMap, vIridescenceMapUv ).r;
	#endif
	#ifdef USE_IRIDESCENCE_THICKNESSMAP
		material.iridescenceThickness = (iridescenceThicknessMaximum - iridescenceThicknessMinimum) * texture2D( iridescenceThicknessMap, vIridescenceThicknessMapUv ).g + iridescenceThicknessMinimum;
	#else
		material.iridescenceThickness = iridescenceThicknessMaximum;
	#endif
#endif
#ifdef USE_SHEEN
	material.sheenColor = sheenColor;
	#ifdef USE_SHEEN_COLORMAP
		material.sheenColor *= texture2D( sheenColorMap, vSheenColorMapUv ).rgb;
	#endif
	material.sheenRoughness = clamp( sheenRoughness, 0.0001, 1.0 );
	#ifdef USE_SHEEN_ROUGHNESSMAP
		material.sheenRoughness *= texture2D( sheenRoughnessMap, vSheenRoughnessMapUv ).a;
	#endif
#endif
#ifdef USE_ANISOTROPY
	#ifdef USE_ANISOTROPYMAP
		mat2 anisotropyMat = mat2( anisotropyVector.x, anisotropyVector.y, - anisotropyVector.y, anisotropyVector.x );
		vec3 anisotropyPolar = texture2D( anisotropyMap, vAnisotropyMapUv ).rgb;
		vec2 anisotropyV = anisotropyMat * normalize( 2.0 * anisotropyPolar.rg - vec2( 1.0 ) ) * anisotropyPolar.b;
	#else
		vec2 anisotropyV = anisotropyVector;
	#endif
	material.anisotropy = length( anisotropyV );
	if( material.anisotropy == 0.0 ) {
		anisotropyV = vec2( 1.0, 0.0 );
	} else {
		anisotropyV /= material.anisotropy;
		material.anisotropy = saturate( material.anisotropy );
	}
	material.alphaT = mix( pow2( material.roughness ), 1.0, pow2( material.anisotropy ) );
	material.anisotropyT = tbn[ 0 ] * anisotropyV.x + tbn[ 1 ] * anisotropyV.y;
	material.anisotropyB = tbn[ 1 ] * anisotropyV.x - tbn[ 0 ] * anisotropyV.y;
#endif`,La=`uniform sampler2D dfgLUT;
struct PhysicalMaterial {
	vec3 diffuseColor;
	vec3 diffuseContribution;
	vec3 specularColor;
	vec3 specularColorBlended;
	float roughness;
	float metalness;
	float specularF90;
	float dispersion;
	vec2 dfg;
	vec3 multiScatteringCompensation;
	#ifdef USE_RETROREFLECTION
		float retroreflectivity;
	#endif
	#ifdef USE_CLEARCOAT
		float clearcoat;
		float clearcoatRoughness;
		vec3 clearcoatF0;
		float clearcoatF90;
	#endif
	#ifdef USE_IRIDESCENCE
		float iridescence;
		float iridescenceIOR;
		float iridescenceThickness;
		vec3 iridescenceFresnel;
		vec3 iridescenceF0Dielectric;
		vec3 iridescenceF0Metallic;
	#endif
	#ifdef USE_SHEEN
		vec3 sheenColor;
		float sheenRoughness;
	#endif
	#ifdef IOR
		float ior;
	#endif
	#ifdef USE_TRANSMISSION
		float transmission;
		float transmissionAlpha;
		float thickness;
		float attenuationDistance;
		vec3 attenuationColor;
	#endif
	#ifdef USE_ANISOTROPY
		float anisotropy;
		float alphaT;
		vec3 anisotropyT;
		vec3 anisotropyB;
	#endif
};
vec3 clearcoatSpecularDirect = vec3( 0.0 );
vec3 clearcoatSpecularIndirect = vec3( 0.0 );
vec3 sheenSpecularDirect = vec3( 0.0 );
vec3 sheenSpecularIndirect = vec3(0.0 );
vec3 Schlick_to_F0( const in vec3 f, const in float f90, const in float dotVH ) {
    float x = clamp( 1.0 - dotVH, 0.0, 1.0 );
    float x2 = x * x;
    float x5 = clamp( x * x2 * x2, 0.0, 0.9999 );
    return ( f - vec3( f90 ) * x5 ) / ( 1.0 - x5 );
}
float V_GGX_SmithCorrelated( const in float alpha, const in float dotNL, const in float dotNV ) {
	float a2 = pow2( alpha );
	float gv = dotNL * sqrt( a2 + ( 1.0 - a2 ) * pow2( dotNV ) );
	float gl = dotNV * sqrt( a2 + ( 1.0 - a2 ) * pow2( dotNL ) );
	return 0.5 / max( gv + gl, EPSILON );
}
float D_GGX( const in float alpha, const in float dotNH ) {
	float a2 = pow2( alpha );
	float denom = pow2( dotNH ) * ( a2 - 1.0 ) + 1.0;
	return RECIPROCAL_PI * a2 / pow2( denom );
}
#ifdef USE_ANISOTROPY
	float V_GGX_SmithCorrelated_Anisotropic( const in float alphaT, const in float alphaB, const in float dotTV, const in float dotBV, const in float dotTL, const in float dotBL, const in float dotNV, const in float dotNL ) {
		float gv = dotNL * length( vec3( alphaT * dotTV, alphaB * dotBV, dotNV ) );
		float gl = dotNV * length( vec3( alphaT * dotTL, alphaB * dotBL, dotNL ) );
		return 0.5 / max( gv + gl, EPSILON );
	}
	float D_GGX_Anisotropic( const in float alphaT, const in float alphaB, const in float dotNH, const in float dotTH, const in float dotBH ) {
		float a2 = alphaT * alphaB;
		highp vec3 v = vec3( alphaB * dotTH, alphaT * dotBH, a2 * dotNH );
		highp float v2 = dot( v, v );
		float w2 = a2 / v2;
		return RECIPROCAL_PI * a2 * pow2 ( w2 );
	}
#endif
#ifdef USE_CLEARCOAT
	vec3 BRDF_GGX_Clearcoat( const in vec3 lightDir, const in vec3 viewDir, const in vec3 normal, const in PhysicalMaterial material) {
		vec3 f0 = material.clearcoatF0;
		float f90 = material.clearcoatF90;
		float roughness = material.clearcoatRoughness;
		float alpha = pow2( roughness );
		vec3 halfDir = normalize( lightDir + viewDir );
		float dotNL = saturate( dot( normal, lightDir ) );
		float dotNV = saturate( dot( normal, viewDir ) );
		float dotNH = saturate( dot( normal, halfDir ) );
		float dotVH = saturate( dot( viewDir, halfDir ) );
		vec3 F = F_Schlick( f0, f90, dotVH );
		float V = V_GGX_SmithCorrelated( alpha, dotNL, dotNV );
		float D = D_GGX( alpha, dotNH );
		return F * ( V * D );
	}
#endif
vec3 BRDF_GGX( const in vec3 lightDir, const in vec3 viewDir, const in vec3 normal, const in PhysicalMaterial material ) {
	vec3 f0 = material.specularColorBlended;
	float f90 = material.specularF90;
	float roughness = material.roughness;
	float alpha = pow2( roughness );
	vec3 halfDir = normalize( lightDir + viewDir );
	float dotNL = saturate( dot( normal, lightDir ) );
	float dotNV = saturate( dot( normal, viewDir ) );
	float dotNH = saturate( dot( normal, halfDir ) );
	float dotVH = saturate( dot( viewDir, halfDir ) );
	vec3 F = F_Schlick( f0, f90, dotVH );
	#ifdef USE_IRIDESCENCE
		F = mix( F, material.iridescenceFresnel, material.iridescence );
	#endif
	#ifdef USE_ANISOTROPY
		float dotTL = dot( material.anisotropyT, lightDir );
		float dotTV = dot( material.anisotropyT, viewDir );
		float dotTH = dot( material.anisotropyT, halfDir );
		float dotBL = dot( material.anisotropyB, lightDir );
		float dotBV = dot( material.anisotropyB, viewDir );
		float dotBH = dot( material.anisotropyB, halfDir );
		float V = V_GGX_SmithCorrelated_Anisotropic( material.alphaT, alpha, dotTV, dotBV, dotTL, dotBL, dotNV, dotNL );
		float D = D_GGX_Anisotropic( material.alphaT, alpha, dotNH, dotTH, dotBH );
	#else
		float V = V_GGX_SmithCorrelated( alpha, dotNL, dotNV );
		float D = D_GGX( alpha, dotNH );
	#endif
	return F * ( V * D );
}
vec2 LTC_Uv( const in vec3 N, const in vec3 V, const in float roughness ) {
	const float LUT_SIZE = 64.0;
	const float LUT_SCALE = ( LUT_SIZE - 1.0 ) / LUT_SIZE;
	const float LUT_BIAS = 0.5 / LUT_SIZE;
	float dotNV = saturate( dot( N, V ) );
	vec2 uv = vec2( roughness, sqrt( 1.0 - dotNV ) );
	uv = uv * LUT_SCALE + LUT_BIAS;
	return uv;
}
float LTC_ClippedSphereFormFactor( const in vec3 f ) {
	float l = length( f );
	return max( ( l * l + f.z ) / ( l + 1.0 ), 0.0 );
}
vec3 LTC_EdgeVectorFormFactor( const in vec3 v1, const in vec3 v2 ) {
	float x = dot( v1, v2 );
	float y = abs( x );
	float a = 0.8543985 + ( 0.4965155 + 0.0145206 * y ) * y;
	float b = 3.4175940 + ( 4.1616724 + y ) * y;
	float v = a / b;
	float theta_sintheta = ( x > 0.0 ) ? v : 0.5 * inversesqrt( max( 1.0 - x * x, 1e-7 ) ) - v;
	return cross( v1, v2 ) * theta_sintheta;
}
vec3 LTC_Evaluate( const in vec3 N, const in vec3 V, const in vec3 P, const in mat3 mInv, const in vec3 rectCoords[ 4 ] ) {
	vec3 v1 = rectCoords[ 1 ] - rectCoords[ 0 ];
	vec3 v2 = rectCoords[ 3 ] - rectCoords[ 0 ];
	vec3 lightNormal = cross( v1, v2 );
	if( dot( lightNormal, P - rectCoords[ 0 ] ) < 0.0 ) return vec3( 0.0 );
	vec3 T1, T2;
	T1 = normalize( V - N * dot( V, N ) );
	T2 = - cross( N, T1 );
	mat3 mat = mInv * transpose( mat3( T1, T2, N ) );
	vec3 coords[ 4 ];
	coords[ 0 ] = mat * ( rectCoords[ 0 ] - P );
	coords[ 1 ] = mat * ( rectCoords[ 1 ] - P );
	coords[ 2 ] = mat * ( rectCoords[ 2 ] - P );
	coords[ 3 ] = mat * ( rectCoords[ 3 ] - P );
	coords[ 0 ] = normalize( coords[ 0 ] );
	coords[ 1 ] = normalize( coords[ 1 ] );
	coords[ 2 ] = normalize( coords[ 2 ] );
	coords[ 3 ] = normalize( coords[ 3 ] );
	vec3 vectorFormFactor = vec3( 0.0 );
	vectorFormFactor += LTC_EdgeVectorFormFactor( coords[ 0 ], coords[ 1 ] );
	vectorFormFactor += LTC_EdgeVectorFormFactor( coords[ 1 ], coords[ 2 ] );
	vectorFormFactor += LTC_EdgeVectorFormFactor( coords[ 2 ], coords[ 3 ] );
	vectorFormFactor += LTC_EdgeVectorFormFactor( coords[ 3 ], coords[ 0 ] );
	float result = LTC_ClippedSphereFormFactor( vectorFormFactor );
	return vec3( result );
}
#if defined( USE_SHEEN )
float D_Charlie( float roughness, float dotNH ) {
	float alpha = pow2( roughness );
	float invAlpha = 1.0 / alpha;
	float cos2h = dotNH * dotNH;
	float sin2h = max( 1.0 - cos2h, 0.0078125 );
	return ( 2.0 + invAlpha ) * pow( sin2h, invAlpha * 0.5 ) / ( 2.0 * PI );
}
float V_Neubelt( float dotNV, float dotNL ) {
	return saturate( 1.0 / ( 4.0 * ( dotNL + dotNV - dotNL * dotNV ) ) );
}
vec3 BRDF_Sheen( const in vec3 lightDir, const in vec3 viewDir, const in vec3 normal, vec3 sheenColor, const in float sheenRoughness ) {
	vec3 halfDir = normalize( lightDir + viewDir );
	float dotNL = saturate( dot( normal, lightDir ) );
	float dotNV = saturate( dot( normal, viewDir ) );
	float dotNH = saturate( dot( normal, halfDir ) );
	float D = D_Charlie( sheenRoughness, dotNH );
	float V = V_Neubelt( dotNV, dotNL );
	return sheenColor * ( D * V );
}
#endif
float IBLSheenBRDF( const in vec3 normal, const in vec3 viewDir, const in float roughness ) {
	float dotNV = saturate( dot( normal, viewDir ) );
	float r2 = roughness * roughness;
	float rInv = 1.0 / ( roughness + 0.1 );
	float a = -1.9362 + 1.0678 * roughness + 0.4573 * r2 - 0.8469 * rInv;
	float b = -0.6014 + 0.5538 * roughness - 0.4670 * r2 - 0.1255 * rInv;
	float DG = exp( a * dotNV + b );
	return saturate( DG );
}
vec3 EnvironmentBRDF( const in vec3 normal, const in vec3 viewDir, const in vec3 specularColor, const in float specularF90, const in float roughness ) {
	float dotNV = saturate( dot( normal, viewDir ) );
	vec2 fab = texture2D( dfgLUT, vec2( roughness, dotNV ) ).rg;
	return specularColor * fab.x + specularF90 * fab.y;
}
#ifdef USE_IRIDESCENCE
void computeMultiscatteringIridescence( const in vec2 fab, const in vec3 specularColor, const in float specularF90, const in float iridescence, const in vec3 iridescenceF0, inout vec3 singleScatter, inout vec3 multiScatter ) {
#else
void computeMultiscattering( const in vec2 fab, const in vec3 specularColor, const in float specularF90, inout vec3 singleScatter, inout vec3 multiScatter ) {
#endif
	#ifdef USE_IRIDESCENCE
		vec3 Fr = mix( specularColor, iridescenceF0, iridescence );
	#else
		vec3 Fr = specularColor;
	#endif
	vec3 FssEss = Fr * fab.x + specularF90 * fab.y;
	float Ess = fab.x + fab.y;
	float Ems = 1.0 - Ess;
	vec3 Favg = Fr + ( 1.0 - Fr ) * 0.047619;	vec3 Fms = FssEss * Favg / ( 1.0 - Ems * Favg );
	singleScatter += FssEss;
	multiScatter += Fms * Ems;
}
#if NUM_RECT_AREA_LIGHTS > 0
	void RE_Direct_RectArea_Physical( const in RectAreaLight rectAreaLight, const in vec3 geometryPosition, const in vec3 geometryNormal, const in vec3 geometryViewDir, const in vec3 geometryClearcoatNormal, const in PhysicalMaterial material, inout ReflectedLight reflectedLight ) {
		vec3 normal = geometryNormal;
		vec3 viewDir = geometryViewDir;
		vec3 position = geometryPosition;
		vec3 lightPos = rectAreaLight.position;
		vec3 halfWidth = rectAreaLight.halfWidth;
		vec3 halfHeight = rectAreaLight.halfHeight;
		vec3 lightColor = rectAreaLight.color;
		float roughness = material.roughness;
		vec3 rectCoords[ 4 ];
		rectCoords[ 0 ] = lightPos + halfWidth - halfHeight;		rectCoords[ 1 ] = lightPos - halfWidth - halfHeight;
		rectCoords[ 2 ] = lightPos - halfWidth + halfHeight;
		rectCoords[ 3 ] = lightPos + halfWidth + halfHeight;
		vec2 uv = LTC_Uv( normal, viewDir, roughness );
		vec4 t1 = texture2D( ltc_1, uv );
		vec4 t2 = texture2D( ltc_2, uv );
		mat3 mInv = mat3(
			vec3( t1.x, 0, t1.y ),
			vec3(    0, 1,    0 ),
			vec3( t1.z, 0, t1.w )
		);
		vec3 fresnel = ( material.specularColorBlended * t2.x + ( material.specularF90 - material.specularColorBlended ) * t2.y );
		reflectedLight.directSpecular += lightColor * fresnel * LTC_Evaluate( normal, viewDir, position, mInv, rectCoords );
		reflectedLight.directDiffuse += lightColor * material.diffuseContribution * LTC_Evaluate( normal, viewDir, position, mat3( 1.0 ), rectCoords );
		#ifdef USE_CLEARCOAT
			vec3 Ncc = geometryClearcoatNormal;
			vec2 uvClearcoat = LTC_Uv( Ncc, viewDir, material.clearcoatRoughness );
			vec4 t1Clearcoat = texture2D( ltc_1, uvClearcoat );
			vec4 t2Clearcoat = texture2D( ltc_2, uvClearcoat );
			mat3 mInvClearcoat = mat3(
				vec3( t1Clearcoat.x, 0, t1Clearcoat.y ),
				vec3(             0, 1,             0 ),
				vec3( t1Clearcoat.z, 0, t1Clearcoat.w )
			);
			vec3 fresnelClearcoat = material.clearcoatF0 * t2Clearcoat.x + ( material.clearcoatF90 - material.clearcoatF0 ) * t2Clearcoat.y;
			clearcoatSpecularDirect += lightColor * fresnelClearcoat * LTC_Evaluate( Ncc, viewDir, position, mInvClearcoat, rectCoords );
		#endif
	}
#endif
void RE_Direct_Physical( const in IncidentLight directLight, const in vec3 geometryPosition, const in vec3 geometryNormal, const in vec3 geometryViewDir, const in vec3 geometryClearcoatNormal, const in PhysicalMaterial material, inout ReflectedLight reflectedLight ) {
	float dotNL = saturate( dot( geometryNormal, directLight.direction ) );
	vec3 irradiance = dotNL * directLight.color;
	#ifdef USE_CLEARCOAT
		float dotNLcc = saturate( dot( geometryClearcoatNormal, directLight.direction ) );
		vec3 ccIrradiance = dotNLcc * directLight.color;
		clearcoatSpecularDirect += ccIrradiance * BRDF_GGX_Clearcoat( directLight.direction, geometryViewDir, geometryClearcoatNormal, material );
	#endif
	#ifdef USE_SHEEN
 
 		sheenSpecularDirect += irradiance * BRDF_Sheen( directLight.direction, geometryViewDir, geometryNormal, material.sheenColor, material.sheenRoughness );
 
 		float sheenAlbedoV = IBLSheenBRDF( geometryNormal, geometryViewDir, material.sheenRoughness );
 		float sheenAlbedoL = IBLSheenBRDF( geometryNormal, directLight.direction, material.sheenRoughness );
 
 		float sheenEnergyComp = 1.0 - max3( material.sheenColor ) * max( sheenAlbedoV, sheenAlbedoL );
 
 		irradiance *= sheenEnergyComp;
 
 	#endif
	vec3 specularBRDF = BRDF_GGX( directLight.direction, geometryViewDir, geometryNormal, material );
	#ifdef USE_RETROREFLECTION
		vec3 retroViewDir = reflect( - geometryViewDir, geometryNormal );
		vec3 retroSpecularBRDF = BRDF_GGX( directLight.direction, retroViewDir, geometryNormal, material );
		specularBRDF = mix( specularBRDF, retroSpecularBRDF, saturate( material.retroreflectivity ) );
	#endif
	reflectedLight.directSpecular += irradiance * specularBRDF * material.multiScatteringCompensation;
	vec3 halfDir = normalize( directLight.direction + geometryViewDir );
	float dotVH = saturate( dot( geometryViewDir, halfDir ) );
	vec3 F = F_Schlick( material.specularColor, material.specularF90, dotVH );
	#ifdef USE_RETROREFLECTION
		vec3 retroHalfDir = normalize( directLight.direction + retroViewDir );
		float dotRetroVH = saturate( dot( retroViewDir, retroHalfDir ) );
		vec3 retroF = F_Schlick( material.specularColor, material.specularF90, dotRetroVH );
		F = mix( F, retroF, saturate( material.retroreflectivity ) );
	#endif
	reflectedLight.directDiffuse += irradiance * BRDF_Lambert( material.diffuseContribution ) * ( 1.0 - F );
}
void RE_IndirectDiffuse_Physical( const in vec3 irradiance, const in vec3 geometryPosition, const in vec3 geometryNormal, const in vec3 geometryViewDir, const in vec3 geometryClearcoatNormal, const in PhysicalMaterial material, inout ReflectedLight reflectedLight ) {
	vec3 singleScattering = vec3( 0.0 );
	vec3 multiScattering = vec3( 0.0 );
	#ifdef USE_IRIDESCENCE
		computeMultiscatteringIridescence( material.dfg, material.specularColor, material.specularF90, material.iridescence, material.iridescenceF0Dielectric, singleScattering, multiScattering );
	#else
		computeMultiscattering( material.dfg, material.specularColor, material.specularF90, singleScattering, multiScattering );
	#endif
	vec3 diffuse = irradiance * BRDF_Lambert( material.diffuseContribution ) * ( 1.0 - singleScattering - multiScattering );
	#ifdef USE_SHEEN
		float sheenAlbedo = IBLSheenBRDF( geometryNormal, geometryViewDir, material.sheenRoughness );
		sheenSpecularIndirect += irradiance * material.sheenColor * sheenAlbedo * RECIPROCAL_PI;
		float sheenEnergyComp = 1.0 - max3( material.sheenColor ) * sheenAlbedo;
		diffuse *= sheenEnergyComp;
	#endif
	reflectedLight.indirectDiffuse += diffuse;
}
void RE_IndirectSpecular_Physical( const in vec3 radiance, const in vec3 irradiance, const in vec3 clearcoatRadiance, const in vec3 geometryPosition, const in vec3 geometryNormal, const in vec3 geometryViewDir, const in vec3 geometryClearcoatNormal, const in PhysicalMaterial material, inout ReflectedLight reflectedLight) {
	#ifdef USE_CLEARCOAT
		clearcoatSpecularIndirect += clearcoatRadiance * EnvironmentBRDF( geometryClearcoatNormal, geometryViewDir, material.clearcoatF0, material.clearcoatF90, material.clearcoatRoughness );
	#endif
	#ifdef USE_SHEEN
		sheenSpecularIndirect += irradiance * material.sheenColor * IBLSheenBRDF( geometryNormal, geometryViewDir, material.sheenRoughness ) * RECIPROCAL_PI;
 	#endif
	vec3 singleScatteringDielectric = vec3( 0.0 );
	vec3 multiScatteringDielectric = vec3( 0.0 );
	vec3 singleScatteringMetallic = vec3( 0.0 );
	vec3 multiScatteringMetallic = vec3( 0.0 );
	#ifdef USE_IRIDESCENCE
		computeMultiscatteringIridescence( material.dfg, material.specularColor, material.specularF90, material.iridescence, material.iridescenceF0Dielectric, singleScatteringDielectric, multiScatteringDielectric );
		computeMultiscatteringIridescence( material.dfg, material.diffuseColor, material.specularF90, material.iridescence, material.iridescenceF0Metallic, singleScatteringMetallic, multiScatteringMetallic );
	#else
		computeMultiscattering( material.dfg, material.specularColor, material.specularF90, singleScatteringDielectric, multiScatteringDielectric );
		computeMultiscattering( material.dfg, material.diffuseColor, material.specularF90, singleScatteringMetallic, multiScatteringMetallic );
	#endif
	vec3 singleScattering = mix( singleScatteringDielectric, singleScatteringMetallic, material.metalness );
	vec3 multiScattering = mix( multiScatteringDielectric, multiScatteringMetallic, material.metalness );
	vec3 totalScatteringDielectric = singleScatteringDielectric + multiScatteringDielectric;
	vec3 diffuse = material.diffuseContribution * ( 1.0 - totalScatteringDielectric );
	vec3 cosineWeightedIrradiance = irradiance * RECIPROCAL_PI;
	vec3 indirectSpecular = radiance * singleScattering;
	indirectSpecular += multiScattering * cosineWeightedIrradiance;
	vec3 indirectDiffuse = diffuse * cosineWeightedIrradiance;
	#ifdef USE_SHEEN
		float sheenAlbedo = IBLSheenBRDF( geometryNormal, geometryViewDir, material.sheenRoughness );
		float sheenEnergyComp = 1.0 - max3( material.sheenColor ) * sheenAlbedo;
		indirectSpecular *= sheenEnergyComp;
		indirectDiffuse *= sheenEnergyComp;
	#endif
	reflectedLight.indirectSpecular += indirectSpecular;
	reflectedLight.indirectDiffuse += indirectDiffuse;
}
#define RE_Direct				RE_Direct_Physical
#define RE_Direct_RectArea		RE_Direct_RectArea_Physical
#define RE_IndirectDiffuse		RE_IndirectDiffuse_Physical
#define RE_IndirectSpecular		RE_IndirectSpecular_Physical
float computeSpecularOcclusion( const in float dotNV, const in float ambientOcclusion, const in float roughness ) {
	return saturate( pow( dotNV + ambientOcclusion, exp2( - 16.0 * roughness - 1.0 ) ) - 1.0 + ambientOcclusion );
}`,Na=`
vec3 geometryPosition = - vViewPosition;
vec3 geometryNormal = normal;
vec3 geometryViewDir = ( isOrthographic ) ? vec3( 0, 0, 1 ) : normalize( vViewPosition );
vec3 geometryClearcoatNormal = vec3( 0.0 );
#ifdef USE_CLEARCOAT
	geometryClearcoatNormal = clearcoatNormal;
#endif
#ifdef USE_IRIDESCENCE
	float dotNVi = saturate( dot( normal, geometryViewDir ) );
	if ( material.iridescenceThickness == 0.0 ) {
		material.iridescence = 0.0;
	} else {
		material.iridescence = saturate( material.iridescence );
	}
	if ( material.iridescence > 0.0 ) {
		vec3 iridescenceFresnelDielectric = evalIridescence( 1.0, material.iridescenceIOR, dotNVi, material.iridescenceThickness, material.specularColor );
		vec3 iridescenceFresnelMetallic = evalIridescence( 1.0, material.iridescenceIOR, dotNVi, material.iridescenceThickness, material.diffuseColor );
		material.iridescenceFresnel = mix( iridescenceFresnelDielectric, iridescenceFresnelMetallic, material.metalness );
		material.iridescenceF0Dielectric = Schlick_to_F0( iridescenceFresnelDielectric, 1.0, dotNVi );
		material.iridescenceF0Metallic = Schlick_to_F0( iridescenceFresnelMetallic, 1.0, dotNVi );
	}
#endif
#ifdef STANDARD
	float dotNVms = saturate( dot( geometryNormal, geometryViewDir ) );
	material.dfg = texture2D( dfgLUT, vec2( material.roughness, dotNVms ) ).rg;
	#if ( NUM_SUN_LIGHTS > 0 || NUM_DIR_LIGHTS > 0 || NUM_POINT_LIGHTS > 0 || NUM_SPOT_LIGHTS > 0 )
		float EssMs = material.dfg.x + material.dfg.y;
		material.multiScatteringCompensation = 1.0 + material.specularColorBlended * ( 1.0 / EssMs - 1.0 );
	#endif
#endif
IncidentLight directLight;
#if ( NUM_POINT_LIGHTS > 0 ) && defined( RE_Direct )
	PointLight pointLight;
	#if defined( USE_SHADOWMAP ) && NUM_POINT_LIGHT_SHADOWS > 0
	PointLightShadow pointLightShadow;
	#endif
	#pragma unroll_loop_start
	for ( int i = 0; i < NUM_POINT_LIGHTS; i ++ ) {
		pointLight = pointLights[ i ];
		getPointLightInfo( pointLight, geometryPosition, directLight );
		#if defined( USE_SHADOWMAP ) && ( UNROLLED_LOOP_INDEX < NUM_POINT_LIGHT_SHADOWS ) && ( defined( SHADOWMAP_TYPE_PCF ) || defined( SHADOWMAP_TYPE_BASIC ) )
		pointLightShadow = pointLightShadows[ i ];
		directLight.color *= ( directLight.visible && receiveShadow ) ? getPointShadow( pointShadowMap[ i ], pointLightShadow.shadowMapSize, pointLightShadow.shadowIntensity, pointLightShadow.shadowBias, pointLightShadow.shadowRadius, vPointShadowCoord[ i ], pointLightShadow.shadowCameraNear, pointLightShadow.shadowCameraFar ) : 1.0;
		#endif
		RE_Direct( directLight, geometryPosition, geometryNormal, geometryViewDir, geometryClearcoatNormal, material, reflectedLight );
	}
	#pragma unroll_loop_end
#endif
#if ( NUM_SPOT_LIGHTS > 0 ) && defined( RE_Direct )
	SpotLight spotLight;
	vec4 spotColor;
	vec3 spotLightCoord;
	bool inSpotLightMap;
	#if defined( USE_SHADOWMAP ) && NUM_SPOT_LIGHT_SHADOWS > 0
	SpotLightShadow spotLightShadow;
	#endif
	#pragma unroll_loop_start
	for ( int i = 0; i < NUM_SPOT_LIGHTS; i ++ ) {
		spotLight = spotLights[ i ];
		getSpotLightInfo( spotLight, geometryPosition, directLight );
		#if ( UNROLLED_LOOP_INDEX < NUM_SPOT_LIGHT_SHADOWS_WITH_MAPS )
		#define SPOT_LIGHT_MAP_INDEX UNROLLED_LOOP_INDEX
		#elif ( UNROLLED_LOOP_INDEX < NUM_SPOT_LIGHT_SHADOWS )
		#define SPOT_LIGHT_MAP_INDEX NUM_SPOT_LIGHT_MAPS
		#else
		#define SPOT_LIGHT_MAP_INDEX ( UNROLLED_LOOP_INDEX - NUM_SPOT_LIGHT_SHADOWS + NUM_SPOT_LIGHT_SHADOWS_WITH_MAPS )
		#endif
		#if ( SPOT_LIGHT_MAP_INDEX < NUM_SPOT_LIGHT_MAPS )
			spotLightCoord = vSpotLightCoord[ i ].xyz / vSpotLightCoord[ i ].w;
			inSpotLightMap = all( lessThan( abs( spotLightCoord * 2. - 1. ), vec3( 1.0 ) ) );
			spotColor = texture2D( spotLightMap[ SPOT_LIGHT_MAP_INDEX ], spotLightCoord.xy );
			directLight.color = inSpotLightMap ? directLight.color * spotColor.rgb : directLight.color;
		#endif
		#undef SPOT_LIGHT_MAP_INDEX
		#if defined( USE_SHADOWMAP ) && ( UNROLLED_LOOP_INDEX < NUM_SPOT_LIGHT_SHADOWS )
		spotLightShadow = spotLightShadows[ i ];
		directLight.color *= ( directLight.visible && receiveShadow ) ? getShadow( spotShadowMap[ i ], spotLightShadow.shadowMapSize, spotLightShadow.shadowIntensity, spotLightShadow.shadowBias, spotLightShadow.shadowRadius, vSpotLightCoord[ i ] ) : 1.0;
		#endif
		RE_Direct( directLight, geometryPosition, geometryNormal, geometryViewDir, geometryClearcoatNormal, material, reflectedLight );
	}
	#pragma unroll_loop_end
#endif
#if ( NUM_SUN_LIGHTS > 0 ) && defined( RE_Direct )
	SunLight sunLight;
	#if defined( USE_SHADOWMAP ) && NUM_SUN_LIGHT_SHADOWS > 0
	SunLightShadow sunLightShadow;
	#endif
	#pragma unroll_loop_start
	for ( int i = 0; i < NUM_SUN_LIGHTS; i ++ ) {
		sunLight = sunLights[ i ];
		getSunLightInfo( sunLight, directLight );
		#if defined( USE_SHADOWMAP ) && ( UNROLLED_LOOP_INDEX < NUM_SUN_LIGHT_SHADOWS )
		sunLightShadow = sunLightShadows[ i ];
		directLight.color *= ( directLight.visible && receiveShadow ) ? getSunShadow( sunShadowMap[ i ], sunLightShadow, UNROLLED_LOOP_INDEX ) : 1.0;
		#endif
		RE_Direct( directLight, geometryPosition, geometryNormal, geometryViewDir, geometryClearcoatNormal, material, reflectedLight );
	}
	#pragma unroll_loop_end
#endif
#if ( NUM_DIR_LIGHTS > 0 ) && defined( RE_Direct )
	DirectionalLight directionalLight;
	#if defined( USE_SHADOWMAP ) && NUM_DIR_LIGHT_SHADOWS > 0
	DirectionalLightShadow directionalLightShadow;
	#endif
	#pragma unroll_loop_start
	for ( int i = 0; i < NUM_DIR_LIGHTS; i ++ ) {
		directionalLight = directionalLights[ i ];
		getDirectionalLightInfo( directionalLight, directLight );
		#if defined( USE_SHADOWMAP ) && ( UNROLLED_LOOP_INDEX < NUM_DIR_LIGHT_SHADOWS )
		directionalLightShadow = directionalLightShadows[ i ];
		directLight.color *= ( directLight.visible && receiveShadow ) ? getShadow( directionalShadowMap[ i ], directionalLightShadow.shadowMapSize, directionalLightShadow.shadowIntensity, directionalLightShadow.shadowBias, directionalLightShadow.shadowRadius, vDirectionalShadowCoord[ i ] ) : 1.0;
		#endif
		RE_Direct( directLight, geometryPosition, geometryNormal, geometryViewDir, geometryClearcoatNormal, material, reflectedLight );
	}
	#pragma unroll_loop_end
#endif
#if ( NUM_RECT_AREA_LIGHTS > 0 ) && defined( RE_Direct_RectArea )
	RectAreaLight rectAreaLight;
	#pragma unroll_loop_start
	for ( int i = 0; i < NUM_RECT_AREA_LIGHTS; i ++ ) {
		rectAreaLight = rectAreaLights[ i ];
		RE_Direct_RectArea( rectAreaLight, geometryPosition, geometryNormal, geometryViewDir, geometryClearcoatNormal, material, reflectedLight );
	}
	#pragma unroll_loop_end
#endif
#if defined( RE_IndirectDiffuse )
	vec3 iblIrradiance = vec3( 0.0 );
	vec3 irradiance = getAmbientLightIrradiance( ambientLightColor );
	#if defined( USE_LIGHT_PROBES )
		irradiance += getLightProbeIrradiance( lightProbe, geometryNormal );
	#endif
	#if ( NUM_HEMI_LIGHTS > 0 )
		#pragma unroll_loop_start
		for ( int i = 0; i < NUM_HEMI_LIGHTS; i ++ ) {
			irradiance += getHemisphereLightIrradiance( hemisphereLights[ i ], geometryNormal );
		}
		#pragma unroll_loop_end
	#endif
	#ifdef USE_LIGHT_PROBES_GRID
		vec3 probeWorldPos = ( ( vec4( geometryPosition, 1.0 ) - viewMatrix[ 3 ] ) * viewMatrix ).xyz;
		vec3 probeWorldNormal = transformNormalByInverseViewMatrix( geometryNormal, viewMatrix );
		irradiance += getLightProbeGridIrradiance( probeWorldPos, probeWorldNormal );
	#endif
#endif
#if defined( RE_IndirectSpecular )
	vec3 radiance = vec3( 0.0 );
	vec3 clearcoatRadiance = vec3( 0.0 );
#endif`,Da=`#if defined( RE_IndirectDiffuse )
	#ifdef USE_LIGHTMAP
		vec4 lightMapTexel = texture2D( lightMap, vLightMapUv );
		vec3 lightMapIrradiance = lightMapTexel.rgb * lightMapIntensity;
		irradiance += lightMapIrradiance;
	#endif
	#if defined( USE_ENVMAP ) && defined( ENVMAP_TYPE_CUBE_UV )
		#if defined( STANDARD ) || defined( LAMBERT ) || defined( PHONG )
			iblIrradiance += getIBLIrradiance( geometryNormal );
		#endif
	#endif
#endif
#if defined( USE_ENVMAP ) && defined( RE_IndirectSpecular )
	#ifdef USE_ANISOTROPY
		vec3 iblRadiance = getIBLAnisotropyRadiance( geometryViewDir, geometryNormal, material.roughness, material.anisotropyB, material.anisotropy );
	#else
		vec3 iblRadiance = getIBLRadiance( geometryViewDir, geometryNormal, material.roughness );
	#endif
	#ifdef USE_RETROREFLECTION
		#ifdef USE_ANISOTROPY
			vec3 retroIBLRadiance = getIBLAnisotropyRetroRadiance( geometryViewDir, geometryNormal, material.roughness, material.anisotropyB, material.anisotropy );
		#else
			vec3 retroIBLRadiance = getIBLRetroRadiance( geometryViewDir, geometryNormal, material.roughness );
		#endif
		iblRadiance = mix( iblRadiance, retroIBLRadiance, saturate( material.retroreflectivity ) );
	#endif
	radiance += iblRadiance;
	#ifdef USE_CLEARCOAT
		clearcoatRadiance += getIBLRadiance( geometryViewDir, geometryClearcoatNormal, material.clearcoatRoughness );
	#endif
#endif`,Ua=`#if defined( RE_IndirectDiffuse )
	#if defined( LAMBERT ) || defined( PHONG )
		irradiance += iblIrradiance;
	#endif
	RE_IndirectDiffuse( irradiance, geometryPosition, geometryNormal, geometryViewDir, geometryClearcoatNormal, material, reflectedLight );
#endif
#if defined( RE_IndirectSpecular )
	RE_IndirectSpecular( radiance, iblIrradiance, clearcoatRadiance, geometryPosition, geometryNormal, geometryViewDir, geometryClearcoatNormal, material, reflectedLight );
#endif`,Fa=`#ifdef USE_LIGHT_PROBES_GRID
uniform highp sampler3D probesSH;
uniform vec3 probesMin;
uniform vec3 probesMax;
uniform vec3 probesResolution;
vec3 getLightProbeGridIrradiance( vec3 worldPos, vec3 worldNormal ) {
	vec3 res = probesResolution;
	vec3 gridRange = probesMax - probesMin;
	vec3 resMinusOne = res - 1.0;
	vec3 probeSpacing = gridRange / resMinusOne;
	vec3 samplePos = worldPos + worldNormal * probeSpacing * 0.5;
	vec3 uvw = clamp( ( samplePos - probesMin ) / gridRange, 0.0, 1.0 );
	uvw = uvw * resMinusOne / res + 0.5 / res;
	float nz          = res.z;
	float paddedSlices = nz + 2.0;
	float atlasDepth  = 7.0 * paddedSlices;
	float uvZBase     = uvw.z * nz + 1.0;
	vec4 s0 = texture( probesSH, vec3( uvw.xy, ( uvZBase                       ) / atlasDepth ) );
	vec4 s1 = texture( probesSH, vec3( uvw.xy, ( uvZBase +       paddedSlices   ) / atlasDepth ) );
	vec4 s2 = texture( probesSH, vec3( uvw.xy, ( uvZBase + 2.0 * paddedSlices   ) / atlasDepth ) );
	vec4 s3 = texture( probesSH, vec3( uvw.xy, ( uvZBase + 3.0 * paddedSlices   ) / atlasDepth ) );
	vec4 s4 = texture( probesSH, vec3( uvw.xy, ( uvZBase + 4.0 * paddedSlices   ) / atlasDepth ) );
	vec4 s5 = texture( probesSH, vec3( uvw.xy, ( uvZBase + 5.0 * paddedSlices   ) / atlasDepth ) );
	vec4 s6 = texture( probesSH, vec3( uvw.xy, ( uvZBase + 6.0 * paddedSlices   ) / atlasDepth ) );
	vec3 c0 = s0.xyz;
	vec3 c1 = vec3( s0.w, s1.xy );
	vec3 c2 = vec3( s1.zw, s2.x );
	vec3 c3 = s2.yzw;
	vec3 c4 = s3.xyz;
	vec3 c5 = vec3( s3.w, s4.xy );
	vec3 c6 = vec3( s4.zw, s5.x );
	vec3 c7 = s5.yzw;
	vec3 c8 = s6.xyz;
	float x = worldNormal.x, y = worldNormal.y, z = worldNormal.z;
	vec3 result = c0 * 0.886227;
	result += c1 * 2.0 * 0.511664 * y;
	result += c2 * 2.0 * 0.511664 * z;
	result += c3 * 2.0 * 0.511664 * x;
	result += c4 * 2.0 * 0.429043 * x * y;
	result += c5 * 2.0 * 0.429043 * y * z;
	result += c6 * ( 0.743125 * z * z - 0.247708 );
	result += c7 * 2.0 * 0.429043 * x * z;
	result += c8 * 0.429043 * ( x * x - y * y );
	return max( result, vec3( 0.0 ) );
}
#endif`,Oa=`#if defined( USE_LOGARITHMIC_DEPTH_BUFFER )
	gl_FragDepth = vIsPerspective == 0.0 ? gl_FragCoord.z : log2( vFragDepth ) * logDepthBufFC * 0.5;
#endif`,Ba=`#if defined( USE_LOGARITHMIC_DEPTH_BUFFER )
	uniform float logDepthBufFC;
	varying float vFragDepth;
	varying float vIsPerspective;
#endif`,za=`#ifdef USE_LOGARITHMIC_DEPTH_BUFFER
	varying float vFragDepth;
	varying float vIsPerspective;
#endif`,Va=`#ifdef USE_LOGARITHMIC_DEPTH_BUFFER
	vFragDepth = 1.0 + gl_Position.w;
	vIsPerspective = float( isPerspectiveMatrix( projectionMatrix ) );
#endif`,ka=`#ifdef USE_MAP
	vec4 sampledDiffuseColor = texture2D( map, vMapUv );
	#ifdef DECODE_VIDEO_TEXTURE
		sampledDiffuseColor = sRGBTransferEOTF( sampledDiffuseColor );
	#endif
	diffuseColor *= sampledDiffuseColor;
#endif`,Ga=`#ifdef USE_MAP
	uniform sampler2D map;
#endif`,Ha=`#if defined( USE_MAP ) || defined( USE_ALPHAMAP )
	#if defined( USE_POINTS_UV )
		vec2 uv = vUv;
	#else
		vec2 uv = ( uvTransform * vec3( gl_PointCoord.x, 1.0 - gl_PointCoord.y, 1 ) ).xy;
	#endif
#endif
#ifdef USE_MAP
	diffuseColor *= texture2D( map, uv );
#endif
#ifdef USE_ALPHAMAP
	diffuseColor.a *= texture2D( alphaMap, uv ).g;
#endif`,Wa=`#if defined( USE_POINTS_UV )
	varying vec2 vUv;
#else
	#if defined( USE_MAP ) || defined( USE_ALPHAMAP )
		uniform mat3 uvTransform;
	#endif
#endif
#ifdef USE_MAP
	uniform sampler2D map;
#endif
#ifdef USE_ALPHAMAP
	uniform sampler2D alphaMap;
#endif`,Xa=`float metalnessFactor = metalness;
#ifdef USE_METALNESSMAP
	vec4 texelMetalness = texture2D( metalnessMap, vMetalnessMapUv );
	metalnessFactor *= texelMetalness.b;
#endif`,qa=`#ifdef USE_METALNESSMAP
	uniform sampler2D metalnessMap;
#endif`,Ya=`#ifdef USE_INSTANCING_MORPH
	float morphTargetInfluences[ MORPHTARGETS_COUNT ];
	float morphTargetBaseInfluence = texelFetch( morphTexture, ivec2( 0, gl_InstanceID ), 0 ).r;
	for ( int i = 0; i < MORPHTARGETS_COUNT; i ++ ) {
		morphTargetInfluences[i] =  texelFetch( morphTexture, ivec2( i + 1, gl_InstanceID ), 0 ).r;
	}
#endif`,$a=`#if defined( USE_MORPHCOLORS )
	vColor *= morphTargetBaseInfluence;
	for ( int i = 0; i < MORPHTARGETS_COUNT; i ++ ) {
		#if defined( USE_COLOR_ALPHA )
			if ( morphTargetInfluences[ i ] != 0.0 ) vColor += getMorph( gl_VertexID, i, 2 ) * morphTargetInfluences[ i ];
		#elif defined( USE_COLOR )
			if ( morphTargetInfluences[ i ] != 0.0 ) vColor += getMorph( gl_VertexID, i, 2 ).rgb * morphTargetInfluences[ i ];
		#endif
	}
#endif`,Za=`#ifdef USE_MORPHNORMALS
	objectNormal *= morphTargetBaseInfluence;
	for ( int i = 0; i < MORPHTARGETS_COUNT; i ++ ) {
		if ( morphTargetInfluences[ i ] != 0.0 ) objectNormal += getMorph( gl_VertexID, i, 1 ).xyz * morphTargetInfluences[ i ];
	}
#endif`,Ja=`#ifdef USE_MORPHTARGETS
	#ifndef USE_INSTANCING_MORPH
		uniform float morphTargetBaseInfluence;
		uniform float morphTargetInfluences[ MORPHTARGETS_COUNT ];
	#endif
	uniform sampler2DArray morphTargetsTexture;
	uniform ivec2 morphTargetsTextureSize;
	vec4 getMorph( const in int vertexIndex, const in int morphTargetIndex, const in int offset ) {
		int texelIndex = vertexIndex * MORPHTARGETS_TEXTURE_STRIDE + offset;
		int y = texelIndex / morphTargetsTextureSize.x;
		int x = texelIndex - y * morphTargetsTextureSize.x;
		ivec3 morphUV = ivec3( x, y, morphTargetIndex );
		return texelFetch( morphTargetsTexture, morphUV, 0 );
	}
#endif`,Ka=`#ifdef USE_MORPHTARGETS
	transformed *= morphTargetBaseInfluence;
	for ( int i = 0; i < MORPHTARGETS_COUNT; i ++ ) {
		if ( morphTargetInfluences[ i ] != 0.0 ) transformed += getMorph( gl_VertexID, i, 0 ).xyz * morphTargetInfluences[ i ];
	}
#endif`,Qa=`float faceDirection = gl_FrontFacing ? 1.0 : - 1.0;
#ifdef FLAT_SHADED
	vec3 fdx = dFdx( vViewPosition );
	vec3 fdy = dFdy( vViewPosition );
	vec3 normal = normalize( cross( fdx, fdy ) );
#else
	vec3 normal = normalize( vNormal );
	#ifdef DOUBLE_SIDED
		normal *= faceDirection;
	#endif
#endif
#if defined( USE_NORMALMAP_TANGENTSPACE ) || defined( USE_CLEARCOAT_NORMALMAP ) || defined( USE_ANISOTROPY )
	#ifdef USE_TANGENT
		mat3 tbn = mat3( normalize( vTangent ), normalize( vBitangent ), normal );
	#else
		mat3 tbn = getTangentFrame( - vViewPosition, normal,
		#if defined( USE_NORMALMAP )
			vNormalMapUv
		#elif defined( USE_CLEARCOAT_NORMALMAP )
			vClearcoatNormalMapUv
		#else
			vUv
		#endif
		);
	#endif
	#ifdef DOUBLE_SIDED
		tbn[0] *= faceDirection;
		tbn[1] *= faceDirection;
	#endif
#endif
#ifdef USE_CLEARCOAT_NORMALMAP
	#ifdef USE_TANGENT
		mat3 tbn2 = mat3( normalize( vTangent ), normalize( vBitangent ), normal );
	#else
		mat3 tbn2 = getTangentFrame( - vViewPosition, normal, vClearcoatNormalMapUv );
	#endif
	#ifdef DOUBLE_SIDED
		tbn2[0] *= faceDirection;
		tbn2[1] *= faceDirection;
	#endif
#endif
vec3 nonPerturbedNormal = normal;`,ja=`#ifdef USE_NORMALMAP_OBJECTSPACE
	normal = texture2D( normalMap, vNormalMapUv ).xyz * 2.0 - 1.0;
	#ifdef FLIP_SIDED
		normal = - normal;
	#endif
	#ifdef DOUBLE_SIDED
		normal = normal * faceDirection;
	#endif
	normal = normalize( normalMatrix * normal );
#elif defined( USE_NORMALMAP_TANGENTSPACE )
	vec3 mapN = texture2D( normalMap, vNormalMapUv ).xyz * 2.0 - 1.0;
	#if defined( USE_PACKED_NORMALMAP )
		mapN = vec3( mapN.xy, sqrt( saturate( 1.0 - dot( mapN.xy, mapN.xy ) ) ) );
	#endif
	mapN.xy *= normalScale;
	normal = normalize( tbn * mapN );
#elif defined( USE_BUMPMAP )
	normal = perturbNormalArb( - vViewPosition, normal, dHdxy_fwd(), faceDirection );
#endif`,tc=`#ifndef FLAT_SHADED
	varying vec3 vNormal;
	#ifdef USE_TANGENT
		varying vec3 vTangent;
		varying vec3 vBitangent;
	#endif
#endif`,ec=`#ifndef FLAT_SHADED
	varying vec3 vNormal;
	#ifdef USE_TANGENT
		varying vec3 vTangent;
		varying vec3 vBitangent;
	#endif
#endif`,nc=`#ifndef FLAT_SHADED
	vNormal = normalize( transformedNormal );
	#ifdef USE_TANGENT
		vTangent = normalize( transformedTangent );
		vBitangent = normalize( cross( vNormal, vTangent ) * tangent.w );
		#ifdef FLIP_SIDED
			vBitangent = - vBitangent;
		#endif
	#endif
#endif`,ic=`#ifdef USE_NORMALMAP
	uniform sampler2D normalMap;
	uniform vec2 normalScale;
#endif
#ifdef USE_NORMALMAP_OBJECTSPACE
	uniform mat3 normalMatrix;
#endif
#if ! defined ( USE_TANGENT ) && ( defined ( USE_NORMALMAP_TANGENTSPACE ) || defined ( USE_CLEARCOAT_NORMALMAP ) || defined( USE_ANISOTROPY ) )
	mat3 getTangentFrame( vec3 eye_pos, vec3 surf_norm, vec2 uv ) {
		vec3 q0 = dFdx( eye_pos.xyz );
		vec3 q1 = dFdy( eye_pos.xyz );
		vec2 st0 = dFdx( uv.st );
		vec2 st1 = dFdy( uv.st );
		vec3 N = surf_norm;
		vec3 q1perp = cross( q1, N );
		vec3 q0perp = cross( N, q0 );
		vec3 T = q1perp * st0.x + q0perp * st1.x;
		vec3 B = q1perp * st0.y + q0perp * st1.y;
		float det = max( dot( T, T ), dot( B, B ) );
		float scale = ( det == 0.0 ) ? 0.0 : inversesqrt( det );
		return mat3( T * scale, B * scale, N );
	}
#endif`,sc=`#ifdef USE_CLEARCOAT
	vec3 clearcoatNormal = nonPerturbedNormal;
#endif`,rc=`#ifdef USE_CLEARCOAT_NORMALMAP
	vec3 clearcoatMapN = texture2D( clearcoatNormalMap, vClearcoatNormalMapUv ).xyz * 2.0 - 1.0;
	clearcoatMapN.xy *= clearcoatNormalScale;
	clearcoatNormal = normalize( tbn2 * clearcoatMapN );
#endif`,oc=`#ifdef USE_CLEARCOATMAP
	uniform sampler2D clearcoatMap;
#endif
#ifdef USE_CLEARCOAT_NORMALMAP
	uniform sampler2D clearcoatNormalMap;
	uniform vec2 clearcoatNormalScale;
#endif
#ifdef USE_CLEARCOAT_ROUGHNESSMAP
	uniform sampler2D clearcoatRoughnessMap;
#endif`,ac=`#ifdef USE_IRIDESCENCEMAP
	uniform sampler2D iridescenceMap;
#endif
#ifdef USE_IRIDESCENCE_THICKNESSMAP
	uniform sampler2D iridescenceThicknessMap;
#endif`,cc=`#ifdef OPAQUE
diffuseColor.a = 1.0;
#endif
#ifdef USE_TRANSMISSION
diffuseColor.a *= material.transmissionAlpha;
#endif
gl_FragColor = vec4( outgoingLight, diffuseColor.a );`,lc=`vec3 packNormalToRGB( const in vec3 normal ) {
	return normalize( normal ) * 0.5 + 0.5;
}
vec3 unpackRGBToNormal( const in vec3 rgb ) {
	return 2.0 * rgb.xyz - 1.0;
}
const float PackUpscale = 256. / 255.;const float UnpackDownscale = 255. / 256.;const float ShiftRight8 = 1. / 256.;
const float Inv255 = 1. / 255.;
const vec4 PackFactors = vec4( 1.0, 256.0, 256.0 * 256.0, 256.0 * 256.0 * 256.0 );
const vec2 UnpackFactors2 = vec2( UnpackDownscale, 1.0 / PackFactors.g );
const vec3 UnpackFactors3 = vec3( UnpackDownscale / PackFactors.rg, 1.0 / PackFactors.b );
const vec4 UnpackFactors4 = vec4( UnpackDownscale / PackFactors.rgb, 1.0 / PackFactors.a );
vec4 packDepthToRGBA( const in float v ) {
	if( v <= 0.0 )
		return vec4( 0., 0., 0., 0. );
	if( v >= 1.0 )
		return vec4( 1., 1., 1., 1. );
	float vuf;
	float af = modf( v * PackFactors.a, vuf );
	float bf = modf( vuf * ShiftRight8, vuf );
	float gf = modf( vuf * ShiftRight8, vuf );
	return vec4( vuf * Inv255, gf * PackUpscale, bf * PackUpscale, af );
}
vec3 packDepthToRGB( const in float v ) {
	if( v <= 0.0 )
		return vec3( 0., 0., 0. );
	if( v >= 1.0 )
		return vec3( 1., 1., 1. );
	float vuf;
	float bf = modf( v * PackFactors.b, vuf );
	float gf = modf( vuf * ShiftRight8, vuf );
	return vec3( vuf * Inv255, gf * PackUpscale, bf );
}
vec2 packDepthToRG( const in float v ) {
	if( v <= 0.0 )
		return vec2( 0., 0. );
	if( v >= 1.0 )
		return vec2( 1., 1. );
	float vuf;
	float gf = modf( v * 256., vuf );
	return vec2( vuf * Inv255, gf );
}
float unpackRGBAToDepth( const in vec4 v ) {
	return dot( v, UnpackFactors4 );
}
float unpackRGBToDepth( const in vec3 v ) {
	return dot( v, UnpackFactors3 );
}
float unpackRGToDepth( const in vec2 v ) {
	return v.r * UnpackFactors2.r + v.g * UnpackFactors2.g;
}
vec4 pack2HalfToRGBA( const in vec2 v ) {
	vec4 r = vec4( v.x, fract( v.x * 255.0 ), v.y, fract( v.y * 255.0 ) );
	return vec4( r.x - r.y / 255.0, r.y, r.z - r.w / 255.0, r.w );
}
vec2 unpackRGBATo2Half( const in vec4 v ) {
	return vec2( v.x + ( v.y / 255.0 ), v.z + ( v.w / 255.0 ) );
}
float viewZToOrthographicDepth( const in float viewZ, const in float near, const in float far ) {
	return ( viewZ + near ) / ( near - far );
}
float orthographicDepthToViewZ( const in float depth, const in float near, const in float far ) {
	#ifdef USE_REVERSED_DEPTH_BUFFER
	
		return depth * ( far - near ) - far;
	#else
		return depth * ( near - far ) - near;
	#endif
}
float viewZToPerspectiveDepth( const in float viewZ, const in float near, const in float far ) {
	return ( ( near + viewZ ) * far ) / ( ( far - near ) * viewZ );
}
float perspectiveDepthToViewZ( const in float depth, const in float near, const in float far ) {
	
	#ifdef USE_REVERSED_DEPTH_BUFFER
		return ( near * far ) / ( ( near - far ) * depth - near );
	#else
		return ( near * far ) / ( ( far - near ) * depth - far );
	#endif
}`,hc=`#ifdef PREMULTIPLIED_ALPHA
	gl_FragColor.rgb *= gl_FragColor.a;
#endif`,uc=`vec4 mvPosition = vec4( transformed, 1.0 );
#ifdef USE_BATCHING
	mvPosition = batchingMatrix * mvPosition;
#endif
#ifdef USE_INSTANCING
	mvPosition = instanceMatrix * mvPosition;
#endif
mvPosition = modelViewMatrix * mvPosition;
gl_Position = projectionMatrix * mvPosition;`,dc=`#ifdef DITHERING
	gl_FragColor.rgb = dithering( gl_FragColor.rgb );
#endif`,fc=`#ifdef DITHERING
	vec3 dithering( vec3 color ) {
		float grid_position = rand( gl_FragCoord.xy );
		vec3 dither_shift_RGB = vec3( 0.25 / 255.0, -0.25 / 255.0, 0.25 / 255.0 );
		dither_shift_RGB = mix( 2.0 * dither_shift_RGB, -2.0 * dither_shift_RGB, grid_position );
		return color + dither_shift_RGB;
	}
#endif`,pc=`float roughnessFactor = roughness;
#ifdef USE_ROUGHNESSMAP
	vec4 texelRoughness = texture2D( roughnessMap, vRoughnessMapUv );
	roughnessFactor *= texelRoughness.g;
#endif`,mc=`#ifdef USE_ROUGHNESSMAP
	uniform sampler2D roughnessMap;
#endif`,gc=`#if NUM_SPOT_LIGHT_COORDS > 0
	varying vec4 vSpotLightCoord[ NUM_SPOT_LIGHT_COORDS ];
#endif
#if NUM_SPOT_LIGHT_MAPS > 0
	uniform sampler2D spotLightMap[ NUM_SPOT_LIGHT_MAPS ];
#endif
#ifdef USE_SHADOWMAP
	#if NUM_SUN_LIGHT_SHADOWS > 0
		#define SUN_LIGHT_CASCADES 2
		#if defined( SHADOWMAP_TYPE_PCF )
			uniform sampler2DShadow sunShadowMap[ NUM_SUN_LIGHT_SHADOWS ];
		#else
			uniform sampler2D sunShadowMap[ NUM_SUN_LIGHT_SHADOWS ];
		#endif
		uniform mat4 sunShadowMatrix[ NUM_SUN_LIGHT_SHADOWS * SUN_LIGHT_CASCADES ];
		uniform vec4 sunShadowCascade[ NUM_SUN_LIGHT_SHADOWS * SUN_LIGHT_CASCADES ];
		varying vec4 vSunShadowWorldPosition;
		varying vec3 vSunShadowWorldNormal;
		struct SunLightShadow {
			float shadowIntensity;
			float shadowBias;
			float shadowNormalBias;
			float shadowRadius;
			vec2 shadowMapSize;
		};
		uniform SunLightShadow sunLightShadows[ NUM_SUN_LIGHT_SHADOWS ];
	#endif
	#if NUM_DIR_LIGHT_SHADOWS > 0
		#if defined( SHADOWMAP_TYPE_PCF )
			uniform sampler2DShadow directionalShadowMap[ NUM_DIR_LIGHT_SHADOWS ];
		#else
			uniform sampler2D directionalShadowMap[ NUM_DIR_LIGHT_SHADOWS ];
		#endif
		varying vec4 vDirectionalShadowCoord[ NUM_DIR_LIGHT_SHADOWS ];
		struct DirectionalLightShadow {
			float shadowIntensity;
			float shadowBias;
			float shadowNormalBias;
			float shadowRadius;
			vec2 shadowMapSize;
		};
		uniform DirectionalLightShadow directionalLightShadows[ NUM_DIR_LIGHT_SHADOWS ];
	#endif
	#if NUM_SPOT_LIGHT_SHADOWS > 0
		#if defined( SHADOWMAP_TYPE_PCF )
			uniform sampler2DShadow spotShadowMap[ NUM_SPOT_LIGHT_SHADOWS ];
		#else
			uniform sampler2D spotShadowMap[ NUM_SPOT_LIGHT_SHADOWS ];
		#endif
		struct SpotLightShadow {
			float shadowIntensity;
			float shadowBias;
			float shadowNormalBias;
			float shadowRadius;
			vec2 shadowMapSize;
		};
		uniform SpotLightShadow spotLightShadows[ NUM_SPOT_LIGHT_SHADOWS ];
	#endif
	#if NUM_POINT_LIGHT_SHADOWS > 0
		#if defined( SHADOWMAP_TYPE_PCF )
			uniform samplerCubeShadow pointShadowMap[ NUM_POINT_LIGHT_SHADOWS ];
		#elif defined( SHADOWMAP_TYPE_BASIC )
			uniform samplerCube pointShadowMap[ NUM_POINT_LIGHT_SHADOWS ];
		#endif
		varying vec4 vPointShadowCoord[ NUM_POINT_LIGHT_SHADOWS ];
		struct PointLightShadow {
			float shadowIntensity;
			float shadowBias;
			float shadowNormalBias;
			float shadowRadius;
			vec2 shadowMapSize;
			float shadowCameraNear;
			float shadowCameraFar;
		};
		uniform PointLightShadow pointLightShadows[ NUM_POINT_LIGHT_SHADOWS ];
	#endif
	#if defined( SHADOWMAP_TYPE_PCF )
		float interleavedGradientNoise( vec2 position ) {
			return fract( 52.9829189 * fract( dot( position, vec2( 0.06711056, 0.00583715 ) ) ) );
		}
		vec2 vogelDiskSample( int sampleIndex, int samplesCount, float phi ) {
			const float goldenAngle = 2.399963229728653;
			float r = sqrt( ( float( sampleIndex ) + 0.5 ) / float( samplesCount ) );
			float theta = float( sampleIndex ) * goldenAngle + phi;
			return vec2( cos( theta ), sin( theta ) ) * r;
		}
	#endif
	#if defined( SHADOWMAP_TYPE_PCF )
		float getShadow( sampler2DShadow shadowMap, vec2 shadowMapSize, float shadowIntensity, float shadowBias, float shadowRadius, vec4 shadowCoord ) {
			float shadow = 1.0;
			shadowCoord.xyz /= shadowCoord.w;
			shadowCoord.z += shadowBias;
			bool inFrustum = shadowCoord.x >= 0.0 && shadowCoord.x <= 1.0 && shadowCoord.y >= 0.0 && shadowCoord.y <= 1.0;
			bool frustumTest = inFrustum && shadowCoord.z <= 1.0;
			if ( frustumTest ) {
				vec2 texelSize = vec2( 1.0 ) / shadowMapSize;
				float radius = shadowRadius * texelSize.x;
				float phi = interleavedGradientNoise( gl_FragCoord.xy ) * PI2;
				shadow = (
					texture( shadowMap, vec3( shadowCoord.xy + vogelDiskSample( 0, 5, phi ) * radius, shadowCoord.z ) ) +
					texture( shadowMap, vec3( shadowCoord.xy + vogelDiskSample( 1, 5, phi ) * radius, shadowCoord.z ) ) +
					texture( shadowMap, vec3( shadowCoord.xy + vogelDiskSample( 2, 5, phi ) * radius, shadowCoord.z ) ) +
					texture( shadowMap, vec3( shadowCoord.xy + vogelDiskSample( 3, 5, phi ) * radius, shadowCoord.z ) ) +
					texture( shadowMap, vec3( shadowCoord.xy + vogelDiskSample( 4, 5, phi ) * radius, shadowCoord.z ) )
				) * 0.2;
			}
			return mix( 1.0, shadow, shadowIntensity );
		}
	#elif defined( SHADOWMAP_TYPE_VSM )
		float getShadow( sampler2D shadowMap, vec2 shadowMapSize, float shadowIntensity, float shadowBias, float shadowRadius, vec4 shadowCoord ) {
			float shadow = 1.0;
			shadowCoord.xyz /= shadowCoord.w;
			#ifdef USE_REVERSED_DEPTH_BUFFER
				shadowCoord.z -= shadowBias;
			#else
				shadowCoord.z += shadowBias;
			#endif
			bool inFrustum = shadowCoord.x >= 0.0 && shadowCoord.x <= 1.0 && shadowCoord.y >= 0.0 && shadowCoord.y <= 1.0;
			bool frustumTest = inFrustum && shadowCoord.z <= 1.0;
			if ( frustumTest ) {
				vec2 distribution = texture2D( shadowMap, shadowCoord.xy ).rg;
				float mean = distribution.x;
				float variance = distribution.y * distribution.y;
				#ifdef USE_REVERSED_DEPTH_BUFFER
					float hard_shadow = step( mean, shadowCoord.z );
				#else
					float hard_shadow = step( shadowCoord.z, mean );
				#endif
				
				if ( hard_shadow == 1.0 ) {
					shadow = 1.0;
				} else {
					variance = max( variance, 0.0000001 );
					float d = shadowCoord.z - mean;
					float p_max = variance / ( variance + d * d );
					p_max = clamp( ( p_max - 0.3 ) / 0.65, 0.0, 1.0 );
					shadow = max( hard_shadow, p_max );
				}
			}
			return mix( 1.0, shadow, shadowIntensity );
		}
	#else
		float getShadow( sampler2D shadowMap, vec2 shadowMapSize, float shadowIntensity, float shadowBias, float shadowRadius, vec4 shadowCoord ) {
			float shadow = 1.0;
			shadowCoord.xyz /= shadowCoord.w;
			#ifdef USE_REVERSED_DEPTH_BUFFER
				shadowCoord.z -= shadowBias;
			#else
				shadowCoord.z += shadowBias;
			#endif
			bool inFrustum = shadowCoord.x >= 0.0 && shadowCoord.x <= 1.0 && shadowCoord.y >= 0.0 && shadowCoord.y <= 1.0;
			bool frustumTest = inFrustum && shadowCoord.z <= 1.0;
			if ( frustumTest ) {
				float depth = texture2D( shadowMap, shadowCoord.xy ).r;
				#ifdef USE_REVERSED_DEPTH_BUFFER
					shadow = step( depth, shadowCoord.z );
				#else
					shadow = step( shadowCoord.z, depth );
				#endif
			}
			return mix( 1.0, shadow, shadowIntensity );
		}
	#endif
	#if NUM_SUN_LIGHT_SHADOWS > 0
		float getSunShadow(
			#if defined( SHADOWMAP_TYPE_PCF )
				sampler2DShadow shadowMap,
			#else
				sampler2D shadowMap,
			#endif
			SunLightShadow sunLightShadow,
			int shadowIndex
		) {
			vec4 shadowWorldPosition = vec4( vSunShadowWorldPosition.xyz + vSunShadowWorldNormal * sunLightShadow.shadowNormalBias, 1.0 );
			float viewDepth = vSunShadowWorldPosition.w;
			int cascadeOffset = shadowIndex * SUN_LIGHT_CASCADES;
			float shadow = 1.0;
			for ( int i = SUN_LIGHT_CASCADES - 1; i >= 0; i -- ) {
				vec4 cascade = sunShadowCascade[ cascadeOffset + i ];
				if ( viewDepth >= cascade.x && viewDepth < cascade.y ) {
					float cascadeShadow = getShadow(
						shadowMap,
						sunLightShadow.shadowMapSize,
						sunLightShadow.shadowIntensity,
						sunLightShadow.shadowBias,
						sunLightShadow.shadowRadius,
						sunShadowMatrix[ cascadeOffset + i ] * shadowWorldPosition
					);
					shadow = mix( cascadeShadow, shadow, smoothstep( cascade.z, cascade.y, viewDepth ) );
				}
			}
			return shadow;
		}
	#endif
	#if NUM_POINT_LIGHT_SHADOWS > 0
	#if defined( SHADOWMAP_TYPE_PCF )
	float getPointShadow( samplerCubeShadow shadowMap, vec2 shadowMapSize, float shadowIntensity, float shadowBias, float shadowRadius, vec4 shadowCoord, float shadowCameraNear, float shadowCameraFar ) {
		float shadow = 1.0;
		vec3 lightToPosition = shadowCoord.xyz;
		vec3 bd3D = normalize( lightToPosition );
		vec3 absVec = abs( lightToPosition );
		float viewSpaceZ = max( max( absVec.x, absVec.y ), absVec.z );
		if ( viewSpaceZ - shadowCameraFar <= 0.0 && viewSpaceZ - shadowCameraNear >= 0.0 ) {
			#ifdef USE_REVERSED_DEPTH_BUFFER
				float dp = ( shadowCameraNear * ( shadowCameraFar - viewSpaceZ ) ) / ( viewSpaceZ * ( shadowCameraFar - shadowCameraNear ) );
				dp -= shadowBias;
			#else
				float dp = ( shadowCameraFar * ( viewSpaceZ - shadowCameraNear ) ) / ( viewSpaceZ * ( shadowCameraFar - shadowCameraNear ) );
				dp += shadowBias;
			#endif
			float texelSize = shadowRadius / shadowMapSize.x;
			vec3 absDir = abs( bd3D );
			vec3 tangent = absDir.x > absDir.z ? vec3( 0.0, 1.0, 0.0 ) : vec3( 1.0, 0.0, 0.0 );
			tangent = normalize( cross( bd3D, tangent ) );
			vec3 bitangent = cross( bd3D, tangent );
			float phi = interleavedGradientNoise( gl_FragCoord.xy ) * PI2;
			vec2 sample0 = vogelDiskSample( 0, 5, phi );
			vec2 sample1 = vogelDiskSample( 1, 5, phi );
			vec2 sample2 = vogelDiskSample( 2, 5, phi );
			vec2 sample3 = vogelDiskSample( 3, 5, phi );
			vec2 sample4 = vogelDiskSample( 4, 5, phi );
			shadow = (
				texture( shadowMap, vec4( bd3D + ( tangent * sample0.x + bitangent * sample0.y ) * texelSize, dp ) ) +
				texture( shadowMap, vec4( bd3D + ( tangent * sample1.x + bitangent * sample1.y ) * texelSize, dp ) ) +
				texture( shadowMap, vec4( bd3D + ( tangent * sample2.x + bitangent * sample2.y ) * texelSize, dp ) ) +
				texture( shadowMap, vec4( bd3D + ( tangent * sample3.x + bitangent * sample3.y ) * texelSize, dp ) ) +
				texture( shadowMap, vec4( bd3D + ( tangent * sample4.x + bitangent * sample4.y ) * texelSize, dp ) )
			) * 0.2;
		}
		return mix( 1.0, shadow, shadowIntensity );
	}
	#elif defined( SHADOWMAP_TYPE_BASIC )
	float getPointShadow( samplerCube shadowMap, vec2 shadowMapSize, float shadowIntensity, float shadowBias, float shadowRadius, vec4 shadowCoord, float shadowCameraNear, float shadowCameraFar ) {
		float shadow = 1.0;
		vec3 lightToPosition = shadowCoord.xyz;
		vec3 absVec = abs( lightToPosition );
		float viewSpaceZ = max( max( absVec.x, absVec.y ), absVec.z );
		if ( viewSpaceZ - shadowCameraFar <= 0.0 && viewSpaceZ - shadowCameraNear >= 0.0 ) {
			float dp = ( shadowCameraFar * ( viewSpaceZ - shadowCameraNear ) ) / ( viewSpaceZ * ( shadowCameraFar - shadowCameraNear ) );
			dp += shadowBias;
			vec3 bd3D = normalize( lightToPosition );
			float depth = textureCube( shadowMap, bd3D ).r;
			#ifdef USE_REVERSED_DEPTH_BUFFER
				depth = 1.0 - depth;
			#endif
			shadow = step( dp, depth );
		}
		return mix( 1.0, shadow, shadowIntensity );
	}
	#endif
	#endif
#endif`,_c=`#if NUM_SPOT_LIGHT_COORDS > 0
	uniform mat4 spotLightMatrix[ NUM_SPOT_LIGHT_COORDS ];
	varying vec4 vSpotLightCoord[ NUM_SPOT_LIGHT_COORDS ];
#endif
#ifdef USE_SHADOWMAP
	#if NUM_SUN_LIGHT_SHADOWS > 0
		varying vec4 vSunShadowWorldPosition;
		varying vec3 vSunShadowWorldNormal;
	#endif
	#if NUM_DIR_LIGHT_SHADOWS > 0
		uniform mat4 directionalShadowMatrix[ NUM_DIR_LIGHT_SHADOWS ];
		varying vec4 vDirectionalShadowCoord[ NUM_DIR_LIGHT_SHADOWS ];
		struct DirectionalLightShadow {
			float shadowIntensity;
			float shadowBias;
			float shadowNormalBias;
			float shadowRadius;
			vec2 shadowMapSize;
		};
		uniform DirectionalLightShadow directionalLightShadows[ NUM_DIR_LIGHT_SHADOWS ];
	#endif
	#if NUM_SPOT_LIGHT_SHADOWS > 0
		struct SpotLightShadow {
			float shadowIntensity;
			float shadowBias;
			float shadowNormalBias;
			float shadowRadius;
			vec2 shadowMapSize;
		};
		uniform SpotLightShadow spotLightShadows[ NUM_SPOT_LIGHT_SHADOWS ];
	#endif
	#if NUM_POINT_LIGHT_SHADOWS > 0
		uniform mat4 pointShadowMatrix[ NUM_POINT_LIGHT_SHADOWS ];
		varying vec4 vPointShadowCoord[ NUM_POINT_LIGHT_SHADOWS ];
		struct PointLightShadow {
			float shadowIntensity;
			float shadowBias;
			float shadowNormalBias;
			float shadowRadius;
			vec2 shadowMapSize;
			float shadowCameraNear;
			float shadowCameraFar;
		};
		uniform PointLightShadow pointLightShadows[ NUM_POINT_LIGHT_SHADOWS ];
	#endif
#endif`,xc=`#if ( defined( USE_SHADOWMAP ) && ( NUM_DIR_LIGHT_SHADOWS > 0 || NUM_SUN_LIGHT_SHADOWS > 0 || NUM_POINT_LIGHT_SHADOWS > 0 ) ) || ( NUM_SPOT_LIGHT_COORDS > 0 )
	#ifdef HAS_NORMAL
		vec3 shadowWorldNormal = transformNormalByInverseViewMatrix( transformedNormal, viewMatrix );
	#else
		vec3 shadowWorldNormal = vec3( 0.0 );
	#endif
	vec4 shadowWorldPosition;
#endif
#if defined( USE_SHADOWMAP )
	#if NUM_SUN_LIGHT_SHADOWS > 0
		vSunShadowWorldPosition = vec4( worldPosition.xyz, - mvPosition.z );
		vSunShadowWorldNormal = shadowWorldNormal;
	#endif
	#if NUM_DIR_LIGHT_SHADOWS > 0
		#pragma unroll_loop_start
		for ( int i = 0; i < NUM_DIR_LIGHT_SHADOWS; i ++ ) {
			shadowWorldPosition = worldPosition + vec4( shadowWorldNormal * directionalLightShadows[ i ].shadowNormalBias, 0 );
			vDirectionalShadowCoord[ i ] = directionalShadowMatrix[ i ] * shadowWorldPosition;
		}
		#pragma unroll_loop_end
	#endif
	#if NUM_POINT_LIGHT_SHADOWS > 0
		#pragma unroll_loop_start
		for ( int i = 0; i < NUM_POINT_LIGHT_SHADOWS; i ++ ) {
			shadowWorldPosition = worldPosition + vec4( shadowWorldNormal * pointLightShadows[ i ].shadowNormalBias, 0 );
			vPointShadowCoord[ i ] = pointShadowMatrix[ i ] * shadowWorldPosition;
		}
		#pragma unroll_loop_end
	#endif
#endif
#if NUM_SPOT_LIGHT_COORDS > 0
	#pragma unroll_loop_start
	for ( int i = 0; i < NUM_SPOT_LIGHT_COORDS; i ++ ) {
		shadowWorldPosition = worldPosition;
		#if ( defined( USE_SHADOWMAP ) && UNROLLED_LOOP_INDEX < NUM_SPOT_LIGHT_SHADOWS )
			shadowWorldPosition.xyz += shadowWorldNormal * spotLightShadows[ i ].shadowNormalBias;
		#endif
		vSpotLightCoord[ i ] = spotLightMatrix[ i ] * shadowWorldPosition;
	}
	#pragma unroll_loop_end
#endif`,yc=`float getShadowMask() {
	float shadow = 1.0;
	#ifdef USE_SHADOWMAP
	#if NUM_SUN_LIGHT_SHADOWS > 0
	SunLightShadow sunLight;
	#pragma unroll_loop_start
	for ( int i = 0; i < NUM_SUN_LIGHT_SHADOWS; i ++ ) {
		sunLight = sunLightShadows[ i ];
		shadow *= receiveShadow ? getSunShadow( sunShadowMap[ i ], sunLight, UNROLLED_LOOP_INDEX ) : 1.0;
	}
	#pragma unroll_loop_end
	#endif
	#if NUM_DIR_LIGHT_SHADOWS > 0
	DirectionalLightShadow directionalLight;
	#pragma unroll_loop_start
	for ( int i = 0; i < NUM_DIR_LIGHT_SHADOWS; i ++ ) {
		directionalLight = directionalLightShadows[ i ];
		shadow *= receiveShadow ? getShadow( directionalShadowMap[ i ], directionalLight.shadowMapSize, directionalLight.shadowIntensity, directionalLight.shadowBias, directionalLight.shadowRadius, vDirectionalShadowCoord[ i ] ) : 1.0;
	}
	#pragma unroll_loop_end
	#endif
	#if NUM_SPOT_LIGHT_SHADOWS > 0
	SpotLightShadow spotLight;
	#pragma unroll_loop_start
	for ( int i = 0; i < NUM_SPOT_LIGHT_SHADOWS; i ++ ) {
		spotLight = spotLightShadows[ i ];
		shadow *= receiveShadow ? getShadow( spotShadowMap[ i ], spotLight.shadowMapSize, spotLight.shadowIntensity, spotLight.shadowBias, spotLight.shadowRadius, vSpotLightCoord[ i ] ) : 1.0;
	}
	#pragma unroll_loop_end
	#endif
	#if NUM_POINT_LIGHT_SHADOWS > 0 && ( defined( SHADOWMAP_TYPE_PCF ) || defined( SHADOWMAP_TYPE_BASIC ) )
	PointLightShadow pointLight;
	#pragma unroll_loop_start
	for ( int i = 0; i < NUM_POINT_LIGHT_SHADOWS; i ++ ) {
		pointLight = pointLightShadows[ i ];
		shadow *= receiveShadow ? getPointShadow( pointShadowMap[ i ], pointLight.shadowMapSize, pointLight.shadowIntensity, pointLight.shadowBias, pointLight.shadowRadius, vPointShadowCoord[ i ], pointLight.shadowCameraNear, pointLight.shadowCameraFar ) : 1.0;
	}
	#pragma unroll_loop_end
	#endif
	#endif
	return shadow;
}`,vc=`#ifdef USE_SKINNING
	mat4 boneMatX = getBoneMatrix( skinIndex.x );
	mat4 boneMatY = getBoneMatrix( skinIndex.y );
	mat4 boneMatZ = getBoneMatrix( skinIndex.z );
	mat4 boneMatW = getBoneMatrix( skinIndex.w );
#endif`,Mc=`#ifdef USE_SKINNING
	uniform mat4 bindMatrix;
	uniform mat4 bindMatrixInverse;
	uniform highp sampler2D boneTexture;
	mat4 getBoneMatrix( const in float i ) {
		int size = textureSize( boneTexture, 0 ).x;
		int j = int( i ) * 4;
		int x = j % size;
		int y = j / size;
		vec4 v1 = texelFetch( boneTexture, ivec2( x, y ), 0 );
		vec4 v2 = texelFetch( boneTexture, ivec2( x + 1, y ), 0 );
		vec4 v3 = texelFetch( boneTexture, ivec2( x + 2, y ), 0 );
		vec4 v4 = texelFetch( boneTexture, ivec2( x + 3, y ), 0 );
		return mat4( v1, v2, v3, v4 );
	}
#endif`,Sc=`#ifdef USE_SKINNING
	vec4 skinVertex = bindMatrix * vec4( transformed, 1.0 );
	vec4 skinned = vec4( 0.0 );
	skinned += boneMatX * skinVertex * skinWeight.x;
	skinned += boneMatY * skinVertex * skinWeight.y;
	skinned += boneMatZ * skinVertex * skinWeight.z;
	skinned += boneMatW * skinVertex * skinWeight.w;
	transformed = ( bindMatrixInverse * skinned ).xyz;
#endif`,bc=`#ifdef USE_SKINNING
	mat4 skinMatrix = mat4( 0.0 );
	skinMatrix += skinWeight.x * boneMatX;
	skinMatrix += skinWeight.y * boneMatY;
	skinMatrix += skinWeight.z * boneMatZ;
	skinMatrix += skinWeight.w * boneMatW;
	skinMatrix = bindMatrixInverse * skinMatrix * bindMatrix;
	objectNormal = vec4( skinMatrix * vec4( objectNormal, 0.0 ) ).xyz;
	#ifdef USE_TANGENT
		objectTangent = vec4( skinMatrix * vec4( objectTangent, 0.0 ) ).xyz;
	#endif
#endif`,Ec=`float specularStrength;
#ifdef USE_SPECULARMAP
	vec4 texelSpecular = texture2D( specularMap, vSpecularMapUv );
	specularStrength = texelSpecular.r;
#else
	specularStrength = 1.0;
#endif`,Ac=`#ifdef USE_SPECULARMAP
	uniform sampler2D specularMap;
#endif`,Tc=`#if defined( TONE_MAPPING )
	gl_FragColor.rgb = toneMapping( gl_FragColor.rgb );
#endif`,wc=`#ifndef saturate
#define saturate( a ) clamp( a, 0.0, 1.0 )
#endif
uniform float toneMappingExposure;
vec3 LinearToneMapping( vec3 color ) {
	return saturate( toneMappingExposure * color );
}
vec3 ReinhardToneMapping( vec3 color ) {
	color *= toneMappingExposure;
	return saturate( color / ( vec3( 1.0 ) + color ) );
}
vec3 CineonToneMapping( vec3 color ) {
	color *= toneMappingExposure;
	color = max( vec3( 0.0 ), color - 0.004 );
	return pow( ( color * ( 6.2 * color + 0.5 ) ) / ( color * ( 6.2 * color + 1.7 ) + 0.06 ), vec3( 2.2 ) );
}
vec3 RRTAndODTFit( vec3 v ) {
	vec3 a = v * ( v + 0.0245786 ) - 0.000090537;
	vec3 b = v * ( 0.983729 * v + 0.4329510 ) + 0.238081;
	return a / b;
}
vec3 ACESFilmicToneMapping( vec3 color ) {
	const mat3 ACESInputMat = mat3(
		vec3( 0.59719, 0.07600, 0.02840 ),		vec3( 0.35458, 0.90834, 0.13383 ),
		vec3( 0.04823, 0.01566, 0.83777 )
	);
	const mat3 ACESOutputMat = mat3(
		vec3(  1.60475, -0.10208, -0.00327 ),		vec3( -0.53108,  1.10813, -0.07276 ),
		vec3( -0.07367, -0.00605,  1.07602 )
	);
	color *= toneMappingExposure / 0.6;
	color = ACESInputMat * color;
	color = RRTAndODTFit( color );
	color = ACESOutputMat * color;
	return saturate( color );
}
const mat3 LINEAR_REC2020_TO_LINEAR_SRGB = mat3(
	vec3( 1.6605, - 0.1246, - 0.0182 ),
	vec3( - 0.5876, 1.1329, - 0.1006 ),
	vec3( - 0.0728, - 0.0083, 1.1187 )
);
const mat3 LINEAR_SRGB_TO_LINEAR_REC2020 = mat3(
	vec3( 0.6274, 0.0691, 0.0164 ),
	vec3( 0.3293, 0.9195, 0.0880 ),
	vec3( 0.0433, 0.0113, 0.8956 )
);
vec3 agxDefaultContrastApprox( vec3 x ) {
	vec3 x2 = x * x;
	vec3 x4 = x2 * x2;
	return + 15.5 * x4 * x2
		- 40.14 * x4 * x
		+ 31.96 * x4
		- 6.868 * x2 * x
		+ 0.4298 * x2
		+ 0.1191 * x
		- 0.00232;
}
vec3 AgXToneMapping( vec3 color ) {
	const mat3 AgXInsetMatrix = mat3(
		vec3( 0.856627153315983, 0.137318972929847, 0.11189821299995 ),
		vec3( 0.0951212405381588, 0.761241990602591, 0.0767994186031903 ),
		vec3( 0.0482516061458583, 0.101439036467562, 0.811302368396859 )
	);
	const mat3 AgXOutsetMatrix = mat3(
		vec3( 1.1271005818144368, - 0.1413297634984383, - 0.14132976349843826 ),
		vec3( - 0.11060664309660323, 1.157823702216272, - 0.11060664309660294 ),
		vec3( - 0.016493938717834573, - 0.016493938717834257, 1.2519364065950405 )
	);
	const float AgxMinEv = - 12.47393;	const float AgxMaxEv = 4.026069;
	color *= toneMappingExposure;
	color = LINEAR_SRGB_TO_LINEAR_REC2020 * color;
	color = AgXInsetMatrix * color;
	color = max( color, 1e-10 );	color = log2( color );
	color = ( color - AgxMinEv ) / ( AgxMaxEv - AgxMinEv );
	color = clamp( color, 0.0, 1.0 );
	color = agxDefaultContrastApprox( color );
	color = AgXOutsetMatrix * color;
	color = pow( max( vec3( 0.0 ), color ), vec3( 2.2 ) );
	color = LINEAR_REC2020_TO_LINEAR_SRGB * color;
	color = clamp( color, 0.0, 1.0 );
	return color;
}
vec3 NeutralToneMapping( vec3 color ) {
	const float StartCompression = 0.8 - 0.04;
	const float Desaturation = 0.15;
	color *= toneMappingExposure;
	float x = min( color.r, min( color.g, color.b ) );
	float offset = x < 0.08 ? x - 6.25 * x * x : 0.04;
	color -= offset;
	float peak = max( color.r, max( color.g, color.b ) );
	if ( peak < StartCompression ) return color;
	float d = 1. - StartCompression;
	float newPeak = 1. - d * d / ( peak + d - StartCompression );
	color *= newPeak / peak;
	float g = 1. - 1. / ( Desaturation * ( peak - newPeak ) + 1. );
	return mix( color, vec3( newPeak ), g );
}
vec3 CustomToneMapping( vec3 color ) { return color; }`,Cc=`#ifdef USE_TRANSMISSION
	material.transmission = transmission;
	material.transmissionAlpha = 1.0;
	material.thickness = thickness;
	material.attenuationDistance = attenuationDistance;
	material.attenuationColor = attenuationColor;
	#ifdef USE_TRANSMISSIONMAP
		material.transmission *= texture2D( transmissionMap, vTransmissionMapUv ).r;
	#endif
	#ifdef USE_THICKNESSMAP
		material.thickness *= texture2D( thicknessMap, vThicknessMapUv ).g;
	#endif
	vec3 pos = vWorldPosition;
	vec3 v = normalize( cameraPosition - pos );
	vec3 n = transformNormalByInverseViewMatrix( normal, viewMatrix );
	vec4 transmitted = getIBLVolumeRefraction(
		n, v, material.roughness, material.diffuseContribution, material.specularColorBlended, material.specularF90,
		pos, modelMatrix, viewMatrix, projectionMatrix, material.dispersion, material.ior, material.thickness,
		material.attenuationColor, material.attenuationDistance );
	material.transmissionAlpha = mix( material.transmissionAlpha, transmitted.a, material.transmission );
	totalDiffuse = mix( totalDiffuse, transmitted.rgb, material.transmission );
#endif`,Rc=`#ifdef USE_TRANSMISSION
	uniform float transmission;
	uniform float thickness;
	uniform float attenuationDistance;
	uniform vec3 attenuationColor;
	#ifdef USE_TRANSMISSIONMAP
		uniform sampler2D transmissionMap;
	#endif
	#ifdef USE_THICKNESSMAP
		uniform sampler2D thicknessMap;
	#endif
	uniform vec2 transmissionSamplerSize;
	uniform sampler2D transmissionSamplerMap;
	uniform mat4 modelMatrix;
	uniform mat4 projectionMatrix;
	varying vec3 vWorldPosition;
	float w0( float a ) {
		return ( 1.0 / 6.0 ) * ( a * ( a * ( - a + 3.0 ) - 3.0 ) + 1.0 );
	}
	float w1( float a ) {
		return ( 1.0 / 6.0 ) * ( a *  a * ( 3.0 * a - 6.0 ) + 4.0 );
	}
	float w2( float a ){
		return ( 1.0 / 6.0 ) * ( a * ( a * ( - 3.0 * a + 3.0 ) + 3.0 ) + 1.0 );
	}
	float w3( float a ) {
		return ( 1.0 / 6.0 ) * ( a * a * a );
	}
	float g0( float a ) {
		return w0( a ) + w1( a );
	}
	float g1( float a ) {
		return w2( a ) + w3( a );
	}
	float h0( float a ) {
		return - 1.0 + w1( a ) / ( w0( a ) + w1( a ) );
	}
	float h1( float a ) {
		return 1.0 + w3( a ) / ( w2( a ) + w3( a ) );
	}
	vec4 bicubic( sampler2D tex, vec2 uv, vec4 texelSize, float lod ) {
		uv = uv * texelSize.zw + 0.5;
		vec2 iuv = floor( uv );
		vec2 fuv = fract( uv );
		float g0x = g0( fuv.x );
		float g1x = g1( fuv.x );
		float h0x = h0( fuv.x );
		float h1x = h1( fuv.x );
		float h0y = h0( fuv.y );
		float h1y = h1( fuv.y );
		vec2 p0 = ( vec2( iuv.x + h0x, iuv.y + h0y ) - 0.5 ) * texelSize.xy;
		vec2 p1 = ( vec2( iuv.x + h1x, iuv.y + h0y ) - 0.5 ) * texelSize.xy;
		vec2 p2 = ( vec2( iuv.x + h0x, iuv.y + h1y ) - 0.5 ) * texelSize.xy;
		vec2 p3 = ( vec2( iuv.x + h1x, iuv.y + h1y ) - 0.5 ) * texelSize.xy;
		return g0( fuv.y ) * ( g0x * textureLod( tex, p0, lod ) + g1x * textureLod( tex, p1, lod ) ) +
			g1( fuv.y ) * ( g0x * textureLod( tex, p2, lod ) + g1x * textureLod( tex, p3, lod ) );
	}
	vec4 textureBicubic( sampler2D sampler, vec2 uv, float lod ) {
		vec2 fLodSize = vec2( textureSize( sampler, int( lod ) ) );
		vec2 cLodSize = vec2( textureSize( sampler, int( lod + 1.0 ) ) );
		vec2 fLodSizeInv = 1.0 / fLodSize;
		vec2 cLodSizeInv = 1.0 / cLodSize;
		vec4 fSample = bicubic( sampler, uv, vec4( fLodSizeInv, fLodSize ), floor( lod ) );
		vec4 cSample = bicubic( sampler, uv, vec4( cLodSizeInv, cLodSize ), ceil( lod ) );
		return mix( fSample, cSample, fract( lod ) );
	}
	vec3 getVolumeTransmissionRay( const in vec3 n, const in vec3 v, const in float thickness, const in float ior, const in mat4 modelMatrix ) {
		vec3 refractionVector = refract( - v, normalize( n ), 1.0 / ior );
		vec3 modelScale;
		modelScale.x = length( vec3( modelMatrix[ 0 ].xyz ) );
		modelScale.y = length( vec3( modelMatrix[ 1 ].xyz ) );
		modelScale.z = length( vec3( modelMatrix[ 2 ].xyz ) );
		return normalize( refractionVector ) * thickness * modelScale;
	}
	float applyIorToRoughness( const in float roughness, const in float ior ) {
		return roughness * clamp( ior * 2.0 - 2.0, 0.0, 1.0 );
	}
	vec4 getTransmissionSample( const in vec2 fragCoord, const in float roughness, const in float ior ) {
		float lod = log2( transmissionSamplerSize.x ) * applyIorToRoughness( roughness, ior );
		return textureBicubic( transmissionSamplerMap, fragCoord.xy, lod );
	}
	vec3 volumeAttenuation( const in float transmissionDistance, const in vec3 attenuationColor, const in float attenuationDistance ) {
		if ( isinf( attenuationDistance ) ) {
			return vec3( 1.0 );
		} else {
			vec3 attenuationCoefficient = -log( attenuationColor ) / attenuationDistance;
			vec3 transmittance = exp( - attenuationCoefficient * transmissionDistance );			return transmittance;
		}
	}
	vec4 getIBLVolumeRefraction( const in vec3 n, const in vec3 v, const in float roughness, const in vec3 diffuseColor,
		const in vec3 specularColor, const in float specularF90, const in vec3 position, const in mat4 modelMatrix,
		const in mat4 viewMatrix, const in mat4 projMatrix, const in float dispersion, const in float ior, const in float thickness,
		const in vec3 attenuationColor, const in float attenuationDistance ) {
		vec4 transmittedLight;
		vec3 transmittance;
		#ifdef USE_DISPERSION
			float halfSpread = ( ior - 1.0 ) * 0.025 * dispersion;
			vec3 iors = vec3( ior - halfSpread, ior, ior + halfSpread );
			for ( int i = 0; i < 3; i ++ ) {
				vec3 transmissionRay = getVolumeTransmissionRay( n, v, thickness, iors[ i ], modelMatrix );
				vec3 refractedRayExit = position + transmissionRay;
				vec4 ndcPos = projMatrix * viewMatrix * vec4( refractedRayExit, 1.0 );
				vec2 refractionCoords = ndcPos.xy / ndcPos.w;
				refractionCoords += 1.0;
				refractionCoords /= 2.0;
				vec4 transmissionSample = getTransmissionSample( refractionCoords, roughness, iors[ i ] );
				transmittedLight[ i ] = transmissionSample[ i ];
				transmittedLight.a += transmissionSample.a;
				transmittance[ i ] = diffuseColor[ i ] * volumeAttenuation( length( transmissionRay ), attenuationColor, attenuationDistance )[ i ];
			}
			transmittedLight.a /= 3.0;
		#else
			vec3 transmissionRay = getVolumeTransmissionRay( n, v, thickness, ior, modelMatrix );
			vec3 refractedRayExit = position + transmissionRay;
			vec4 ndcPos = projMatrix * viewMatrix * vec4( refractedRayExit, 1.0 );
			vec2 refractionCoords = ndcPos.xy / ndcPos.w;
			refractionCoords += 1.0;
			refractionCoords /= 2.0;
			transmittedLight = getTransmissionSample( refractionCoords, roughness, ior );
			transmittance = diffuseColor * volumeAttenuation( length( transmissionRay ), attenuationColor, attenuationDistance );
		#endif
		vec3 attenuatedColor = transmittance * transmittedLight.rgb;
		vec3 F = EnvironmentBRDF( n, v, specularColor, specularF90, roughness );
		float transmittanceFactor = ( transmittance.r + transmittance.g + transmittance.b ) / 3.0;
		return vec4( ( 1.0 - F ) * attenuatedColor, 1.0 - ( 1.0 - transmittedLight.a ) * transmittanceFactor );
	}
#endif`,Ic=`#if defined( USE_UV ) || defined( USE_ANISOTROPY )
	varying vec2 vUv;
#endif
#ifdef USE_MAP
	varying vec2 vMapUv;
#endif
#ifdef USE_ALPHAMAP
	varying vec2 vAlphaMapUv;
#endif
#ifdef USE_LIGHTMAP
	varying vec2 vLightMapUv;
#endif
#ifdef USE_AOMAP
	varying vec2 vAoMapUv;
#endif
#ifdef USE_BUMPMAP
	varying vec2 vBumpMapUv;
#endif
#ifdef USE_NORMALMAP
	varying vec2 vNormalMapUv;
#endif
#ifdef USE_EMISSIVEMAP
	varying vec2 vEmissiveMapUv;
#endif
#ifdef USE_METALNESSMAP
	varying vec2 vMetalnessMapUv;
#endif
#ifdef USE_ROUGHNESSMAP
	varying vec2 vRoughnessMapUv;
#endif
#ifdef USE_ANISOTROPYMAP
	varying vec2 vAnisotropyMapUv;
#endif
#ifdef USE_CLEARCOATMAP
	varying vec2 vClearcoatMapUv;
#endif
#ifdef USE_CLEARCOAT_NORMALMAP
	varying vec2 vClearcoatNormalMapUv;
#endif
#ifdef USE_CLEARCOAT_ROUGHNESSMAP
	varying vec2 vClearcoatRoughnessMapUv;
#endif
#ifdef USE_IRIDESCENCEMAP
	varying vec2 vIridescenceMapUv;
#endif
#ifdef USE_IRIDESCENCE_THICKNESSMAP
	varying vec2 vIridescenceThicknessMapUv;
#endif
#ifdef USE_SHEEN_COLORMAP
	varying vec2 vSheenColorMapUv;
#endif
#ifdef USE_SHEEN_ROUGHNESSMAP
	varying vec2 vSheenRoughnessMapUv;
#endif
#ifdef USE_SPECULARMAP
	varying vec2 vSpecularMapUv;
#endif
#ifdef USE_SPECULAR_COLORMAP
	varying vec2 vSpecularColorMapUv;
#endif
#ifdef USE_SPECULAR_INTENSITYMAP
	varying vec2 vSpecularIntensityMapUv;
#endif
#ifdef USE_TRANSMISSIONMAP
	uniform mat3 transmissionMapTransform;
	varying vec2 vTransmissionMapUv;
#endif
#ifdef USE_THICKNESSMAP
	uniform mat3 thicknessMapTransform;
	varying vec2 vThicknessMapUv;
#endif`,Pc=`#if defined( USE_UV ) || defined( USE_ANISOTROPY )
	varying vec2 vUv;
#endif
#ifdef USE_MAP
	uniform mat3 mapTransform;
	varying vec2 vMapUv;
#endif
#ifdef USE_ALPHAMAP
	uniform mat3 alphaMapTransform;
	varying vec2 vAlphaMapUv;
#endif
#ifdef USE_LIGHTMAP
	uniform mat3 lightMapTransform;
	varying vec2 vLightMapUv;
#endif
#ifdef USE_AOMAP
	uniform mat3 aoMapTransform;
	varying vec2 vAoMapUv;
#endif
#ifdef USE_BUMPMAP
	uniform mat3 bumpMapTransform;
	varying vec2 vBumpMapUv;
#endif
#ifdef USE_NORMALMAP
	uniform mat3 normalMapTransform;
	varying vec2 vNormalMapUv;
#endif
#ifdef USE_DISPLACEMENTMAP
	uniform mat3 displacementMapTransform;
	varying vec2 vDisplacementMapUv;
#endif
#ifdef USE_EMISSIVEMAP
	uniform mat3 emissiveMapTransform;
	varying vec2 vEmissiveMapUv;
#endif
#ifdef USE_METALNESSMAP
	uniform mat3 metalnessMapTransform;
	varying vec2 vMetalnessMapUv;
#endif
#ifdef USE_ROUGHNESSMAP
	uniform mat3 roughnessMapTransform;
	varying vec2 vRoughnessMapUv;
#endif
#ifdef USE_ANISOTROPYMAP
	uniform mat3 anisotropyMapTransform;
	varying vec2 vAnisotropyMapUv;
#endif
#ifdef USE_CLEARCOATMAP
	uniform mat3 clearcoatMapTransform;
	varying vec2 vClearcoatMapUv;
#endif
#ifdef USE_CLEARCOAT_NORMALMAP
	uniform mat3 clearcoatNormalMapTransform;
	varying vec2 vClearcoatNormalMapUv;
#endif
#ifdef USE_CLEARCOAT_ROUGHNESSMAP
	uniform mat3 clearcoatRoughnessMapTransform;
	varying vec2 vClearcoatRoughnessMapUv;
#endif
#ifdef USE_SHEEN_COLORMAP
	uniform mat3 sheenColorMapTransform;
	varying vec2 vSheenColorMapUv;
#endif
#ifdef USE_SHEEN_ROUGHNESSMAP
	uniform mat3 sheenRoughnessMapTransform;
	varying vec2 vSheenRoughnessMapUv;
#endif
#ifdef USE_IRIDESCENCEMAP
	uniform mat3 iridescenceMapTransform;
	varying vec2 vIridescenceMapUv;
#endif
#ifdef USE_IRIDESCENCE_THICKNESSMAP
	uniform mat3 iridescenceThicknessMapTransform;
	varying vec2 vIridescenceThicknessMapUv;
#endif
#ifdef USE_SPECULARMAP
	uniform mat3 specularMapTransform;
	varying vec2 vSpecularMapUv;
#endif
#ifdef USE_SPECULAR_COLORMAP
	uniform mat3 specularColorMapTransform;
	varying vec2 vSpecularColorMapUv;
#endif
#ifdef USE_SPECULAR_INTENSITYMAP
	uniform mat3 specularIntensityMapTransform;
	varying vec2 vSpecularIntensityMapUv;
#endif
#ifdef USE_TRANSMISSIONMAP
	uniform mat3 transmissionMapTransform;
	varying vec2 vTransmissionMapUv;
#endif
#ifdef USE_THICKNESSMAP
	uniform mat3 thicknessMapTransform;
	varying vec2 vThicknessMapUv;
#endif`,Lc=`#if defined( USE_UV ) || defined( USE_ANISOTROPY )
	vUv = vec3( uv, 1 ).xy;
#endif
#ifdef USE_MAP
	vMapUv = ( mapTransform * vec3( MAP_UV, 1 ) ).xy;
#endif
#ifdef USE_ALPHAMAP
	vAlphaMapUv = ( alphaMapTransform * vec3( ALPHAMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_LIGHTMAP
	vLightMapUv = ( lightMapTransform * vec3( LIGHTMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_AOMAP
	vAoMapUv = ( aoMapTransform * vec3( AOMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_BUMPMAP
	vBumpMapUv = ( bumpMapTransform * vec3( BUMPMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_NORMALMAP
	vNormalMapUv = ( normalMapTransform * vec3( NORMALMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_DISPLACEMENTMAP
	vDisplacementMapUv = ( displacementMapTransform * vec3( DISPLACEMENTMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_EMISSIVEMAP
	vEmissiveMapUv = ( emissiveMapTransform * vec3( EMISSIVEMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_METALNESSMAP
	vMetalnessMapUv = ( metalnessMapTransform * vec3( METALNESSMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_ROUGHNESSMAP
	vRoughnessMapUv = ( roughnessMapTransform * vec3( ROUGHNESSMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_ANISOTROPYMAP
	vAnisotropyMapUv = ( anisotropyMapTransform * vec3( ANISOTROPYMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_CLEARCOATMAP
	vClearcoatMapUv = ( clearcoatMapTransform * vec3( CLEARCOATMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_CLEARCOAT_NORMALMAP
	vClearcoatNormalMapUv = ( clearcoatNormalMapTransform * vec3( CLEARCOAT_NORMALMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_CLEARCOAT_ROUGHNESSMAP
	vClearcoatRoughnessMapUv = ( clearcoatRoughnessMapTransform * vec3( CLEARCOAT_ROUGHNESSMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_IRIDESCENCEMAP
	vIridescenceMapUv = ( iridescenceMapTransform * vec3( IRIDESCENCEMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_IRIDESCENCE_THICKNESSMAP
	vIridescenceThicknessMapUv = ( iridescenceThicknessMapTransform * vec3( IRIDESCENCE_THICKNESSMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_SHEEN_COLORMAP
	vSheenColorMapUv = ( sheenColorMapTransform * vec3( SHEEN_COLORMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_SHEEN_ROUGHNESSMAP
	vSheenRoughnessMapUv = ( sheenRoughnessMapTransform * vec3( SHEEN_ROUGHNESSMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_SPECULARMAP
	vSpecularMapUv = ( specularMapTransform * vec3( SPECULARMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_SPECULAR_COLORMAP
	vSpecularColorMapUv = ( specularColorMapTransform * vec3( SPECULAR_COLORMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_SPECULAR_INTENSITYMAP
	vSpecularIntensityMapUv = ( specularIntensityMapTransform * vec3( SPECULAR_INTENSITYMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_TRANSMISSIONMAP
	vTransmissionMapUv = ( transmissionMapTransform * vec3( TRANSMISSIONMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_THICKNESSMAP
	vThicknessMapUv = ( thicknessMapTransform * vec3( THICKNESSMAP_UV, 1 ) ).xy;
#endif`,Nc=`#if defined( USE_ENVMAP ) || defined( DISTANCE ) || defined ( USE_SHADOWMAP ) || defined ( USE_TRANSMISSION ) || NUM_SPOT_LIGHT_COORDS > 0
	vec4 worldPosition = vec4( transformed, 1.0 );
	#ifdef USE_BATCHING
		worldPosition = batchingMatrix * worldPosition;
	#endif
	#ifdef USE_INSTANCING
		worldPosition = instanceMatrix * worldPosition;
	#endif
	worldPosition = modelMatrix * worldPosition;
#endif`,Dc=`varying vec2 vUv;
uniform mat3 uvTransform;
void main() {
	vUv = ( uvTransform * vec3( uv, 1 ) ).xy;
	gl_Position = vec4( position.xy, 1.0, 1.0 );
}`,Uc=`uniform sampler2D t2D;
uniform float backgroundIntensity;
varying vec2 vUv;
void main() {
	vec4 texColor = texture2D( t2D, vUv );
	#ifdef DECODE_VIDEO_TEXTURE
		texColor = vec4( mix( pow( texColor.rgb * 0.9478672986 + vec3( 0.0521327014 ), vec3( 2.4 ) ), texColor.rgb * 0.0773993808, vec3( lessThanEqual( texColor.rgb, vec3( 0.04045 ) ) ) ), texColor.w );
	#endif
	texColor.rgb *= backgroundIntensity;
	gl_FragColor = texColor;
	#include <tonemapping_fragment>
	#include <colorspace_fragment>
}`,Fc=`varying vec3 vWorldDirection;
#include <common>
void main() {
	vWorldDirection = transformDirection( position, modelMatrix );
	#include <begin_vertex>
	#include <project_vertex>
	gl_Position.z = gl_Position.w;
}`,Oc=`#ifdef ENVMAP_TYPE_CUBE
	uniform samplerCube envMap;
#elif defined( ENVMAP_TYPE_CUBE_UV )
	uniform sampler2D envMap;
#endif
uniform float backgroundBlurriness;
uniform float backgroundIntensity;
uniform mat3 backgroundRotation;
varying vec3 vWorldDirection;
#include <cube_uv_reflection_fragment>
void main() {
	#ifdef ENVMAP_TYPE_CUBE
		vec4 texColor = textureCube( envMap, backgroundRotation * vWorldDirection );
	#elif defined( ENVMAP_TYPE_CUBE_UV )
		vec4 texColor = textureCubeUV( envMap, backgroundRotation * vWorldDirection, backgroundBlurriness );
	#else
		vec4 texColor = vec4( 0.0, 0.0, 0.0, 1.0 );
	#endif
	texColor.rgb *= backgroundIntensity;
	gl_FragColor = texColor;
	#include <tonemapping_fragment>
	#include <colorspace_fragment>
}`,Bc=`varying vec3 vWorldDirection;
#include <common>
void main() {
	vWorldDirection = transformDirection( position, modelMatrix );
	#include <begin_vertex>
	#include <project_vertex>
	gl_Position.z = gl_Position.w;
}`,zc=`uniform samplerCube tCube;
uniform float tFlip;
uniform float opacity;
varying vec3 vWorldDirection;
void main() {
	vec4 texColor = textureCube( tCube, vec3( tFlip * vWorldDirection.x, vWorldDirection.yz ) );
	gl_FragColor = texColor;
	gl_FragColor.a *= opacity;
	#include <tonemapping_fragment>
	#include <colorspace_fragment>
}`,Vc=`#include <common>
#include <batching_pars_vertex>
#include <uv_pars_vertex>
#include <displacementmap_pars_vertex>
#include <morphtarget_pars_vertex>
#include <skinning_pars_vertex>
#include <logdepthbuf_pars_vertex>
#include <clipping_planes_pars_vertex>
varying vec2 vHighPrecisionZW;
void main() {
	#include <uv_vertex>
	#include <batching_vertex>
	#include <skinbase_vertex>
	#include <morphinstance_vertex>
	#ifdef USE_DISPLACEMENTMAP
		#include <beginnormal_vertex>
		#include <morphnormal_vertex>
		#include <skinnormal_vertex>
	#endif
	#include <begin_vertex>
	#include <morphtarget_vertex>
	#include <skinning_vertex>
	#include <displacementmap_vertex>
	#include <project_vertex>
	#include <logdepthbuf_vertex>
	#include <clipping_planes_vertex>
	vHighPrecisionZW = gl_Position.zw;
}`,kc=`#if DEPTH_PACKING == 3200
	uniform float opacity;
#endif
#include <common>
#include <packing>
#include <uv_pars_fragment>
#include <map_pars_fragment>
#include <alphamap_pars_fragment>
#include <alphatest_pars_fragment>
#include <alphahash_pars_fragment>
#include <logdepthbuf_pars_fragment>
#include <clipping_planes_pars_fragment>
varying vec2 vHighPrecisionZW;
void main() {
	vec4 diffuseColor = vec4( 1.0 );
	#include <clipping_planes_fragment>
	#if DEPTH_PACKING == 3200
		diffuseColor.a = opacity;
	#endif
	#include <map_fragment>
	#include <alphamap_fragment>
	#include <alphatest_fragment>
	#include <alphahash_fragment>
	#include <logdepthbuf_fragment>
	#ifdef USE_REVERSED_DEPTH_BUFFER
		float fragCoordZ = vHighPrecisionZW[ 0 ] / vHighPrecisionZW[ 1 ];
	#else
		float fragCoordZ = 0.5 * vHighPrecisionZW[ 0 ] / vHighPrecisionZW[ 1 ] + 0.5;
	#endif
	#if DEPTH_PACKING == 3200
		gl_FragColor = vec4( vec3( 1.0 - fragCoordZ ), opacity );
	#elif DEPTH_PACKING == 3201
		gl_FragColor = packDepthToRGBA( fragCoordZ );
	#elif DEPTH_PACKING == 3202
		gl_FragColor = vec4( packDepthToRGB( fragCoordZ ), 1.0 );
	#elif DEPTH_PACKING == 3203
		gl_FragColor = vec4( packDepthToRG( fragCoordZ ), 0.0, 1.0 );
	#endif
}`,Gc=`#define DISTANCE
varying vec3 vWorldPosition;
#include <common>
#include <batching_pars_vertex>
#include <uv_pars_vertex>
#include <displacementmap_pars_vertex>
#include <morphtarget_pars_vertex>
#include <skinning_pars_vertex>
#include <clipping_planes_pars_vertex>
void main() {
	#include <uv_vertex>
	#include <batching_vertex>
	#include <skinbase_vertex>
	#include <morphinstance_vertex>
	#ifdef USE_DISPLACEMENTMAP
		#include <beginnormal_vertex>
		#include <morphnormal_vertex>
		#include <skinnormal_vertex>
	#endif
	#include <begin_vertex>
	#include <morphtarget_vertex>
	#include <skinning_vertex>
	#include <displacementmap_vertex>
	#include <project_vertex>
	#include <worldpos_vertex>
	#include <clipping_planes_vertex>
	vWorldPosition = worldPosition.xyz;
}`,Hc=`#define DISTANCE
uniform vec3 referencePosition;
uniform float nearDistance;
uniform float farDistance;
varying vec3 vWorldPosition;
#include <common>
#include <uv_pars_fragment>
#include <map_pars_fragment>
#include <alphamap_pars_fragment>
#include <alphatest_pars_fragment>
#include <alphahash_pars_fragment>
#include <clipping_planes_pars_fragment>
void main() {
	vec4 diffuseColor = vec4( 1.0 );
	#include <clipping_planes_fragment>
	#include <map_fragment>
	#include <alphamap_fragment>
	#include <alphatest_fragment>
	#include <alphahash_fragment>
	float dist = length( vWorldPosition - referencePosition );
	dist = ( dist - nearDistance ) / ( farDistance - nearDistance );
	dist = saturate( dist );
	gl_FragColor = vec4( dist, 0.0, 0.0, 1.0 );
}`,Wc=`varying vec3 vWorldDirection;
#include <common>
void main() {
	vWorldDirection = transformDirection( position, modelMatrix );
	#include <begin_vertex>
	#include <project_vertex>
}`,Xc=`uniform sampler2D tEquirect;
varying vec3 vWorldDirection;
#include <common>
void main() {
	vec3 direction = normalize( vWorldDirection );
	vec2 sampleUV = equirectUv( direction );
	gl_FragColor = texture2D( tEquirect, sampleUV );
	#include <tonemapping_fragment>
	#include <colorspace_fragment>
}`,qc=`uniform float scale;
attribute float lineDistance;
varying float vLineDistance;
#include <common>
#include <uv_pars_vertex>
#include <color_pars_vertex>
#include <fog_pars_vertex>
#include <morphtarget_pars_vertex>
#include <logdepthbuf_pars_vertex>
#include <clipping_planes_pars_vertex>
void main() {
	vLineDistance = scale * lineDistance;
	#include <uv_vertex>
	#include <color_vertex>
	#include <morphinstance_vertex>
	#include <morphcolor_vertex>
	#include <begin_vertex>
	#include <morphtarget_vertex>
	#include <project_vertex>
	#include <logdepthbuf_vertex>
	#include <clipping_planes_vertex>
	#include <fog_vertex>
}`,Yc=`uniform vec3 diffuse;
uniform float opacity;
uniform float dashSize;
uniform float totalSize;
varying float vLineDistance;
#include <common>
#include <color_pars_fragment>
#include <uv_pars_fragment>
#include <map_pars_fragment>
#include <fog_pars_fragment>
#include <logdepthbuf_pars_fragment>
#include <clipping_planes_pars_fragment>
void main() {
	vec4 diffuseColor = vec4( diffuse, opacity );
	#include <clipping_planes_fragment>
	if ( mod( vLineDistance, totalSize ) > dashSize ) {
		discard;
	}
	vec3 outgoingLight = vec3( 0.0 );
	#include <logdepthbuf_fragment>
	#include <map_fragment>
	#include <color_fragment>
	outgoingLight = diffuseColor.rgb;
	#include <opaque_fragment>
	#include <tonemapping_fragment>
	#include <colorspace_fragment>
	#include <fog_fragment>
	#include <premultiplied_alpha_fragment>
}`,$c=`#include <common>
#include <batching_pars_vertex>
#include <uv_pars_vertex>
#include <envmap_pars_vertex>
#include <color_pars_vertex>
#include <fog_pars_vertex>
#include <morphtarget_pars_vertex>
#include <skinning_pars_vertex>
#include <logdepthbuf_pars_vertex>
#include <clipping_planes_pars_vertex>
void main() {
	#include <uv_vertex>
	#include <color_vertex>
	#include <morphinstance_vertex>
	#include <morphcolor_vertex>
	#include <batching_vertex>
	#if defined ( USE_ENVMAP ) || defined ( USE_SKINNING )
		#include <beginnormal_vertex>
		#include <morphnormal_vertex>
		#include <skinbase_vertex>
		#include <skinnormal_vertex>
		#include <defaultnormal_vertex>
	#endif
	#include <begin_vertex>
	#include <morphtarget_vertex>
	#include <skinning_vertex>
	#include <project_vertex>
	#include <logdepthbuf_vertex>
	#include <clipping_planes_vertex>
	#include <worldpos_vertex>
	#include <envmap_vertex>
	#include <fog_vertex>
}`,Zc=`uniform vec3 diffuse;
uniform float opacity;
#ifndef FLAT_SHADED
	varying vec3 vNormal;
#endif
#include <common>
#include <dithering_pars_fragment>
#include <color_pars_fragment>
#include <uv_pars_fragment>
#include <map_pars_fragment>
#include <alphamap_pars_fragment>
#include <alphatest_pars_fragment>
#include <alphahash_pars_fragment>
#include <aomap_pars_fragment>
#include <lightmap_pars_fragment>
#include <envmap_common_pars_fragment>
#include <envmap_pars_fragment>
#include <fog_pars_fragment>
#include <specularmap_pars_fragment>
#include <logdepthbuf_pars_fragment>
#include <clipping_planes_pars_fragment>
void main() {
	vec4 diffuseColor = vec4( diffuse, opacity );
	#include <clipping_planes_fragment>
	#include <logdepthbuf_fragment>
	#include <map_fragment>
	#include <color_fragment>
	#include <alphamap_fragment>
	#include <alphatest_fragment>
	#include <alphahash_fragment>
	#include <specularmap_fragment>
	ReflectedLight reflectedLight = ReflectedLight( vec3( 0.0 ), vec3( 0.0 ), vec3( 0.0 ), vec3( 0.0 ) );
	#ifdef USE_LIGHTMAP
		vec4 lightMapTexel = texture2D( lightMap, vLightMapUv );
		reflectedLight.indirectDiffuse += lightMapTexel.rgb * lightMapIntensity * RECIPROCAL_PI;
	#else
		reflectedLight.indirectDiffuse += vec3( 1.0 );
	#endif
	#include <aomap_fragment>
	reflectedLight.indirectDiffuse *= diffuseColor.rgb;
	vec3 outgoingLight = reflectedLight.indirectDiffuse;
	#include <envmap_fragment>
	#include <opaque_fragment>
	#include <tonemapping_fragment>
	#include <colorspace_fragment>
	#include <fog_fragment>
	#include <premultiplied_alpha_fragment>
	#include <dithering_fragment>
}`,Jc=`#define LAMBERT
varying vec3 vViewPosition;
#include <common>
#include <batching_pars_vertex>
#include <uv_pars_vertex>
#include <displacementmap_pars_vertex>
#include <envmap_pars_vertex>
#include <color_pars_vertex>
#include <fog_pars_vertex>
#include <normal_pars_vertex>
#include <morphtarget_pars_vertex>
#include <skinning_pars_vertex>
#include <shadowmap_pars_vertex>
#include <logdepthbuf_pars_vertex>
#include <clipping_planes_pars_vertex>
void main() {
	#include <uv_vertex>
	#include <color_vertex>
	#include <morphinstance_vertex>
	#include <morphcolor_vertex>
	#include <batching_vertex>
	#include <beginnormal_vertex>
	#include <morphnormal_vertex>
	#include <skinbase_vertex>
	#include <skinnormal_vertex>
	#include <defaultnormal_vertex>
	#include <normal_vertex>
	#include <begin_vertex>
	#include <morphtarget_vertex>
	#include <skinning_vertex>
	#include <displacementmap_vertex>
	#include <project_vertex>
	#include <logdepthbuf_vertex>
	#include <clipping_planes_vertex>
	vViewPosition = - mvPosition.xyz;
	#include <worldpos_vertex>
	#include <envmap_vertex>
	#include <shadowmap_vertex>
	#include <fog_vertex>
}`,Kc=`#define LAMBERT
uniform vec3 diffuse;
uniform vec3 emissive;
uniform float opacity;
#include <common>
#include <dithering_pars_fragment>
#include <color_pars_fragment>
#include <uv_pars_fragment>
#include <map_pars_fragment>
#include <alphamap_pars_fragment>
#include <alphatest_pars_fragment>
#include <alphahash_pars_fragment>
#include <aomap_pars_fragment>
#include <lightmap_pars_fragment>
#include <emissivemap_pars_fragment>
#include <cube_uv_reflection_fragment>
#include <envmap_common_pars_fragment>
#include <envmap_pars_fragment>
#include <envmap_physical_pars_fragment>
#include <fog_pars_fragment>
#include <bsdfs>
#include <lights_pars_begin>
#include <normal_pars_fragment>
#include <lights_lambert_pars_fragment>
#include <shadowmap_pars_fragment>
#include <bumpmap_pars_fragment>
#include <normalmap_pars_fragment>
#include <specularmap_pars_fragment>
#include <logdepthbuf_pars_fragment>
#include <clipping_planes_pars_fragment>
void main() {
	vec4 diffuseColor = vec4( diffuse, opacity );
	#include <clipping_planes_fragment>
	ReflectedLight reflectedLight = ReflectedLight( vec3( 0.0 ), vec3( 0.0 ), vec3( 0.0 ), vec3( 0.0 ) );
	vec3 totalEmissiveRadiance = emissive;
	#include <logdepthbuf_fragment>
	#include <map_fragment>
	#include <color_fragment>
	#include <alphamap_fragment>
	#include <alphatest_fragment>
	#include <alphahash_fragment>
	#include <specularmap_fragment>
	#include <normal_fragment_begin>
	#include <normal_fragment_maps>
	#include <emissivemap_fragment>
	#include <lights_lambert_fragment>
	#include <lights_fragment_begin>
	#include <lights_fragment_maps>
	#include <lights_fragment_end>
	#include <aomap_fragment>
	vec3 outgoingLight = reflectedLight.directDiffuse + reflectedLight.indirectDiffuse + totalEmissiveRadiance;
	#include <envmap_fragment>
	#include <opaque_fragment>
	#include <tonemapping_fragment>
	#include <colorspace_fragment>
	#include <fog_fragment>
	#include <premultiplied_alpha_fragment>
	#include <dithering_fragment>
}`,Qc=`#define MATCAP
varying vec3 vViewPosition;
#include <common>
#include <batching_pars_vertex>
#include <uv_pars_vertex>
#include <color_pars_vertex>
#include <displacementmap_pars_vertex>
#include <fog_pars_vertex>
#include <normal_pars_vertex>
#include <morphtarget_pars_vertex>
#include <skinning_pars_vertex>
#include <logdepthbuf_pars_vertex>
#include <clipping_planes_pars_vertex>
void main() {
	#include <uv_vertex>
	#include <color_vertex>
	#include <morphinstance_vertex>
	#include <morphcolor_vertex>
	#include <batching_vertex>
	#include <beginnormal_vertex>
	#include <morphnormal_vertex>
	#include <skinbase_vertex>
	#include <skinnormal_vertex>
	#include <defaultnormal_vertex>
	#include <normal_vertex>
	#include <begin_vertex>
	#include <morphtarget_vertex>
	#include <skinning_vertex>
	#include <displacementmap_vertex>
	#include <project_vertex>
	#include <logdepthbuf_vertex>
	#include <clipping_planes_vertex>
	#include <fog_vertex>
	vViewPosition = - mvPosition.xyz;
}`,jc=`#define MATCAP
uniform vec3 diffuse;
uniform float opacity;
uniform sampler2D matcap;
varying vec3 vViewPosition;
#include <common>
#include <dithering_pars_fragment>
#include <color_pars_fragment>
#include <uv_pars_fragment>
#include <map_pars_fragment>
#include <alphamap_pars_fragment>
#include <alphatest_pars_fragment>
#include <alphahash_pars_fragment>
#include <fog_pars_fragment>
#include <normal_pars_fragment>
#include <bumpmap_pars_fragment>
#include <normalmap_pars_fragment>
#include <logdepthbuf_pars_fragment>
#include <clipping_planes_pars_fragment>
void main() {
	vec4 diffuseColor = vec4( diffuse, opacity );
	#include <clipping_planes_fragment>
	#include <logdepthbuf_fragment>
	#include <map_fragment>
	#include <color_fragment>
	#include <alphamap_fragment>
	#include <alphatest_fragment>
	#include <alphahash_fragment>
	#include <normal_fragment_begin>
	#include <normal_fragment_maps>
	vec3 viewDir = normalize( vViewPosition );
	vec3 x = normalize( vec3( viewDir.z, 0.0, - viewDir.x ) );
	vec3 y = cross( viewDir, x );
	vec2 uv = vec2( dot( x, normal ), dot( y, normal ) ) * 0.495 + 0.5;
	#ifdef USE_MATCAP
		vec4 matcapColor = texture2D( matcap, uv );
	#else
		vec4 matcapColor = vec4( vec3( mix( 0.2, 0.8, uv.y ) ), 1.0 );
	#endif
	vec3 outgoingLight = diffuseColor.rgb * matcapColor.rgb;
	#include <opaque_fragment>
	#include <tonemapping_fragment>
	#include <colorspace_fragment>
	#include <fog_fragment>
	#include <premultiplied_alpha_fragment>
	#include <dithering_fragment>
}`,tl=`#define NORMAL
#if defined( FLAT_SHADED ) || defined( USE_BUMPMAP ) || defined( USE_NORMALMAP_TANGENTSPACE )
	varying vec3 vViewPosition;
#endif
#include <common>
#include <batching_pars_vertex>
#include <uv_pars_vertex>
#include <displacementmap_pars_vertex>
#include <normal_pars_vertex>
#include <morphtarget_pars_vertex>
#include <skinning_pars_vertex>
#include <logdepthbuf_pars_vertex>
#include <clipping_planes_pars_vertex>
void main() {
	#include <uv_vertex>
	#include <batching_vertex>
	#include <beginnormal_vertex>
	#include <morphinstance_vertex>
	#include <morphnormal_vertex>
	#include <skinbase_vertex>
	#include <skinnormal_vertex>
	#include <defaultnormal_vertex>
	#include <normal_vertex>
	#include <begin_vertex>
	#include <morphtarget_vertex>
	#include <skinning_vertex>
	#include <displacementmap_vertex>
	#include <project_vertex>
	#include <logdepthbuf_vertex>
	#include <clipping_planes_vertex>
#if defined( FLAT_SHADED ) || defined( USE_BUMPMAP ) || defined( USE_NORMALMAP_TANGENTSPACE )
	vViewPosition = - mvPosition.xyz;
#endif
}`,el=`#define NORMAL
uniform float opacity;
#if defined( FLAT_SHADED ) || defined( USE_BUMPMAP ) || defined( USE_NORMALMAP_TANGENTSPACE )
	varying vec3 vViewPosition;
#endif
#include <uv_pars_fragment>
#include <normal_pars_fragment>
#include <bumpmap_pars_fragment>
#include <normalmap_pars_fragment>
#include <logdepthbuf_pars_fragment>
#include <clipping_planes_pars_fragment>
void main() {
	vec4 diffuseColor = vec4( 0.0, 0.0, 0.0, opacity );
	#include <clipping_planes_fragment>
	#include <logdepthbuf_fragment>
	#include <normal_fragment_begin>
	#include <normal_fragment_maps>
	gl_FragColor = vec4( normalize( normal ) * 0.5 + 0.5, diffuseColor.a );
	#ifdef OPAQUE
		gl_FragColor.a = 1.0;
	#endif
}`,nl=`#define PHONG
varying vec3 vViewPosition;
#include <common>
#include <batching_pars_vertex>
#include <uv_pars_vertex>
#include <displacementmap_pars_vertex>
#include <envmap_pars_vertex>
#include <color_pars_vertex>
#include <fog_pars_vertex>
#include <normal_pars_vertex>
#include <morphtarget_pars_vertex>
#include <skinning_pars_vertex>
#include <shadowmap_pars_vertex>
#include <logdepthbuf_pars_vertex>
#include <clipping_planes_pars_vertex>
void main() {
	#include <uv_vertex>
	#include <color_vertex>
	#include <morphcolor_vertex>
	#include <batching_vertex>
	#include <beginnormal_vertex>
	#include <morphinstance_vertex>
	#include <morphnormal_vertex>
	#include <skinbase_vertex>
	#include <skinnormal_vertex>
	#include <defaultnormal_vertex>
	#include <normal_vertex>
	#include <begin_vertex>
	#include <morphtarget_vertex>
	#include <skinning_vertex>
	#include <displacementmap_vertex>
	#include <project_vertex>
	#include <logdepthbuf_vertex>
	#include <clipping_planes_vertex>
	vViewPosition = - mvPosition.xyz;
	#include <worldpos_vertex>
	#include <envmap_vertex>
	#include <shadowmap_vertex>
	#include <fog_vertex>
}`,il=`#define PHONG
uniform vec3 diffuse;
uniform vec3 emissive;
uniform vec3 specular;
uniform float shininess;
uniform float opacity;
#include <common>
#include <dithering_pars_fragment>
#include <color_pars_fragment>
#include <uv_pars_fragment>
#include <map_pars_fragment>
#include <alphamap_pars_fragment>
#include <alphatest_pars_fragment>
#include <alphahash_pars_fragment>
#include <aomap_pars_fragment>
#include <lightmap_pars_fragment>
#include <emissivemap_pars_fragment>
#include <cube_uv_reflection_fragment>
#include <envmap_common_pars_fragment>
#include <envmap_pars_fragment>
#include <envmap_physical_pars_fragment>
#include <fog_pars_fragment>
#include <bsdfs>
#include <lights_pars_begin>
#include <normal_pars_fragment>
#include <lights_phong_pars_fragment>
#include <shadowmap_pars_fragment>
#include <bumpmap_pars_fragment>
#include <normalmap_pars_fragment>
#include <specularmap_pars_fragment>
#include <logdepthbuf_pars_fragment>
#include <clipping_planes_pars_fragment>
void main() {
	vec4 diffuseColor = vec4( diffuse, opacity );
	#include <clipping_planes_fragment>
	ReflectedLight reflectedLight = ReflectedLight( vec3( 0.0 ), vec3( 0.0 ), vec3( 0.0 ), vec3( 0.0 ) );
	vec3 totalEmissiveRadiance = emissive;
	#include <logdepthbuf_fragment>
	#include <map_fragment>
	#include <color_fragment>
	#include <alphamap_fragment>
	#include <alphatest_fragment>
	#include <alphahash_fragment>
	#include <specularmap_fragment>
	#include <normal_fragment_begin>
	#include <normal_fragment_maps>
	#include <emissivemap_fragment>
	#include <lights_phong_fragment>
	#include <lights_fragment_begin>
	#include <lights_fragment_maps>
	#include <lights_fragment_end>
	#include <aomap_fragment>
	vec3 outgoingLight = reflectedLight.directDiffuse + reflectedLight.indirectDiffuse + reflectedLight.directSpecular + reflectedLight.indirectSpecular + totalEmissiveRadiance;
	#include <envmap_fragment>
	#include <opaque_fragment>
	#include <tonemapping_fragment>
	#include <colorspace_fragment>
	#include <fog_fragment>
	#include <premultiplied_alpha_fragment>
	#include <dithering_fragment>
}`,sl=`#define STANDARD
varying vec3 vViewPosition;
#ifdef USE_TRANSMISSION
	varying vec3 vWorldPosition;
#endif
#include <common>
#include <batching_pars_vertex>
#include <uv_pars_vertex>
#include <displacementmap_pars_vertex>
#include <color_pars_vertex>
#include <fog_pars_vertex>
#include <normal_pars_vertex>
#include <morphtarget_pars_vertex>
#include <skinning_pars_vertex>
#include <shadowmap_pars_vertex>
#include <logdepthbuf_pars_vertex>
#include <clipping_planes_pars_vertex>
void main() {
	#include <uv_vertex>
	#include <color_vertex>
	#include <morphinstance_vertex>
	#include <morphcolor_vertex>
	#include <batching_vertex>
	#include <beginnormal_vertex>
	#include <morphnormal_vertex>
	#include <skinbase_vertex>
	#include <skinnormal_vertex>
	#include <defaultnormal_vertex>
	#include <normal_vertex>
	#include <begin_vertex>
	#include <morphtarget_vertex>
	#include <skinning_vertex>
	#include <displacementmap_vertex>
	#include <project_vertex>
	#include <logdepthbuf_vertex>
	#include <clipping_planes_vertex>
	vViewPosition = - mvPosition.xyz;
	#include <worldpos_vertex>
	#include <shadowmap_vertex>
	#include <fog_vertex>
#ifdef USE_TRANSMISSION
	vWorldPosition = worldPosition.xyz;
#endif
}`,rl=`#define STANDARD
#ifdef PHYSICAL
	#define IOR
	#define USE_SPECULAR
#endif
uniform vec3 diffuse;
uniform vec3 emissive;
uniform float roughness;
uniform float metalness;
uniform float opacity;
#ifdef IOR
	uniform float ior;
#endif
#ifdef USE_SPECULAR
	uniform float specularIntensity;
	uniform vec3 specularColor;
	#ifdef USE_SPECULAR_COLORMAP
		uniform sampler2D specularColorMap;
	#endif
	#ifdef USE_SPECULAR_INTENSITYMAP
		uniform sampler2D specularIntensityMap;
	#endif
#endif
#ifdef USE_CLEARCOAT
	uniform float clearcoat;
	uniform float clearcoatRoughness;
#endif
#ifdef USE_DISPERSION
	uniform float dispersion;
#endif
#ifdef USE_RETROREFLECTION
	uniform float retroreflectivity;
#endif
#ifdef USE_IRIDESCENCE
	uniform float iridescence;
	uniform float iridescenceIOR;
	uniform float iridescenceThicknessMinimum;
	uniform float iridescenceThicknessMaximum;
#endif
#ifdef USE_SHEEN
	uniform vec3 sheenColor;
	uniform float sheenRoughness;
	#ifdef USE_SHEEN_COLORMAP
		uniform sampler2D sheenColorMap;
	#endif
	#ifdef USE_SHEEN_ROUGHNESSMAP
		uniform sampler2D sheenRoughnessMap;
	#endif
#endif
#ifdef USE_ANISOTROPY
	uniform vec2 anisotropyVector;
	#ifdef USE_ANISOTROPYMAP
		uniform sampler2D anisotropyMap;
	#endif
#endif
varying vec3 vViewPosition;
#include <common>
#include <dithering_pars_fragment>
#include <color_pars_fragment>
#include <uv_pars_fragment>
#include <map_pars_fragment>
#include <alphamap_pars_fragment>
#include <alphatest_pars_fragment>
#include <alphahash_pars_fragment>
#include <aomap_pars_fragment>
#include <lightmap_pars_fragment>
#include <emissivemap_pars_fragment>
#include <iridescence_fragment>
#include <cube_uv_reflection_fragment>
#include <envmap_common_pars_fragment>
#include <envmap_physical_pars_fragment>
#include <fog_pars_fragment>
#include <lights_pars_begin>
#include <normal_pars_fragment>
#include <lights_physical_pars_fragment>
#include <transmission_pars_fragment>
#include <shadowmap_pars_fragment>
#include <bumpmap_pars_fragment>
#include <normalmap_pars_fragment>
#include <clearcoat_pars_fragment>
#include <iridescence_pars_fragment>
#include <roughnessmap_pars_fragment>
#include <metalnessmap_pars_fragment>
#include <logdepthbuf_pars_fragment>
#include <clipping_planes_pars_fragment>
void main() {
	vec4 diffuseColor = vec4( diffuse, opacity );
	#include <clipping_planes_fragment>
	ReflectedLight reflectedLight = ReflectedLight( vec3( 0.0 ), vec3( 0.0 ), vec3( 0.0 ), vec3( 0.0 ) );
	vec3 totalEmissiveRadiance = emissive;
	#include <logdepthbuf_fragment>
	#include <map_fragment>
	#include <color_fragment>
	#include <alphamap_fragment>
	#include <alphatest_fragment>
	#include <alphahash_fragment>
	#include <roughnessmap_fragment>
	#include <metalnessmap_fragment>
	#include <normal_fragment_begin>
	#include <normal_fragment_maps>
	#include <clearcoat_normal_fragment_begin>
	#include <clearcoat_normal_fragment_maps>
	#include <emissivemap_fragment>
	#include <lights_physical_fragment>
	#include <lights_fragment_begin>
	#include <lights_fragment_maps>
	#include <lights_fragment_end>
	#include <aomap_fragment>
	vec3 totalDiffuse = reflectedLight.directDiffuse + reflectedLight.indirectDiffuse;
	vec3 totalSpecular = reflectedLight.directSpecular + reflectedLight.indirectSpecular;
	#include <transmission_fragment>
	vec3 outgoingLight = totalDiffuse + totalSpecular + totalEmissiveRadiance;
	#ifdef USE_SHEEN
 
		outgoingLight = outgoingLight + sheenSpecularDirect + sheenSpecularIndirect;
 
 	#endif
	#ifdef USE_CLEARCOAT
		float dotNVcc = saturate( dot( geometryClearcoatNormal, geometryViewDir ) );
		vec3 Fcc = F_Schlick( material.clearcoatF0, material.clearcoatF90, dotNVcc );
		outgoingLight = outgoingLight * ( 1.0 - material.clearcoat * Fcc ) + ( clearcoatSpecularDirect + clearcoatSpecularIndirect ) * material.clearcoat;
	#endif
	#include <opaque_fragment>
	#include <tonemapping_fragment>
	#include <colorspace_fragment>
	#include <fog_fragment>
	#include <premultiplied_alpha_fragment>
	#include <dithering_fragment>
}`,ol=`#define TOON
varying vec3 vViewPosition;
#include <common>
#include <batching_pars_vertex>
#include <uv_pars_vertex>
#include <displacementmap_pars_vertex>
#include <color_pars_vertex>
#include <fog_pars_vertex>
#include <normal_pars_vertex>
#include <morphtarget_pars_vertex>
#include <skinning_pars_vertex>
#include <shadowmap_pars_vertex>
#include <logdepthbuf_pars_vertex>
#include <clipping_planes_pars_vertex>
void main() {
	#include <uv_vertex>
	#include <color_vertex>
	#include <morphinstance_vertex>
	#include <morphcolor_vertex>
	#include <batching_vertex>
	#include <beginnormal_vertex>
	#include <morphnormal_vertex>
	#include <skinbase_vertex>
	#include <skinnormal_vertex>
	#include <defaultnormal_vertex>
	#include <normal_vertex>
	#include <begin_vertex>
	#include <morphtarget_vertex>
	#include <skinning_vertex>
	#include <displacementmap_vertex>
	#include <project_vertex>
	#include <logdepthbuf_vertex>
	#include <clipping_planes_vertex>
	vViewPosition = - mvPosition.xyz;
	#include <worldpos_vertex>
	#include <shadowmap_vertex>
	#include <fog_vertex>
}`,al=`#define TOON
uniform vec3 diffuse;
uniform vec3 emissive;
uniform float opacity;
#include <common>
#include <dithering_pars_fragment>
#include <color_pars_fragment>
#include <uv_pars_fragment>
#include <map_pars_fragment>
#include <alphamap_pars_fragment>
#include <alphatest_pars_fragment>
#include <alphahash_pars_fragment>
#include <aomap_pars_fragment>
#include <lightmap_pars_fragment>
#include <emissivemap_pars_fragment>
#include <gradientmap_pars_fragment>
#include <fog_pars_fragment>
#include <bsdfs>
#include <lights_pars_begin>
#include <normal_pars_fragment>
#include <lights_toon_pars_fragment>
#include <shadowmap_pars_fragment>
#include <bumpmap_pars_fragment>
#include <normalmap_pars_fragment>
#include <logdepthbuf_pars_fragment>
#include <clipping_planes_pars_fragment>
void main() {
	vec4 diffuseColor = vec4( diffuse, opacity );
	#include <clipping_planes_fragment>
	ReflectedLight reflectedLight = ReflectedLight( vec3( 0.0 ), vec3( 0.0 ), vec3( 0.0 ), vec3( 0.0 ) );
	vec3 totalEmissiveRadiance = emissive;
	#include <logdepthbuf_fragment>
	#include <map_fragment>
	#include <color_fragment>
	#include <alphamap_fragment>
	#include <alphatest_fragment>
	#include <alphahash_fragment>
	#include <normal_fragment_begin>
	#include <normal_fragment_maps>
	#include <emissivemap_fragment>
	#include <lights_toon_fragment>
	#include <lights_fragment_begin>
	#include <lights_fragment_maps>
	#include <lights_fragment_end>
	#include <aomap_fragment>
	vec3 outgoingLight = reflectedLight.directDiffuse + reflectedLight.indirectDiffuse + totalEmissiveRadiance;
	#include <opaque_fragment>
	#include <tonemapping_fragment>
	#include <colorspace_fragment>
	#include <fog_fragment>
	#include <premultiplied_alpha_fragment>
	#include <dithering_fragment>
}`,cl=`uniform float size;
uniform float scale;
#include <common>
#include <color_pars_vertex>
#include <fog_pars_vertex>
#include <morphtarget_pars_vertex>
#include <logdepthbuf_pars_vertex>
#include <clipping_planes_pars_vertex>
#ifdef USE_POINTS_UV
	varying vec2 vUv;
	uniform mat3 uvTransform;
#endif
void main() {
	#ifdef USE_POINTS_UV
		vUv = ( uvTransform * vec3( uv, 1 ) ).xy;
	#endif
	#include <color_vertex>
	#include <morphinstance_vertex>
	#include <morphcolor_vertex>
	#include <begin_vertex>
	#include <morphtarget_vertex>
	#include <project_vertex>
	gl_PointSize = size;
	#ifdef USE_SIZEATTENUATION
		bool isPerspective = isPerspectiveMatrix( projectionMatrix );
		if ( isPerspective ) gl_PointSize *= ( scale / - mvPosition.z );
	#endif
	#include <logdepthbuf_vertex>
	#include <clipping_planes_vertex>
	#include <worldpos_vertex>
	#include <fog_vertex>
}`,ll=`uniform vec3 diffuse;
uniform float opacity;
#include <common>
#include <color_pars_fragment>
#include <map_particle_pars_fragment>
#include <alphatest_pars_fragment>
#include <alphahash_pars_fragment>
#include <fog_pars_fragment>
#include <logdepthbuf_pars_fragment>
#include <clipping_planes_pars_fragment>
void main() {
	vec4 diffuseColor = vec4( diffuse, opacity );
	#include <clipping_planes_fragment>
	vec3 outgoingLight = vec3( 0.0 );
	#include <logdepthbuf_fragment>
	#include <map_particle_fragment>
	#include <color_fragment>
	#include <alphatest_fragment>
	#include <alphahash_fragment>
	outgoingLight = diffuseColor.rgb;
	#include <opaque_fragment>
	#include <tonemapping_fragment>
	#include <colorspace_fragment>
	#include <fog_fragment>
	#include <premultiplied_alpha_fragment>
}`,hl=`#include <common>
#include <batching_pars_vertex>
#include <fog_pars_vertex>
#include <morphtarget_pars_vertex>
#include <skinning_pars_vertex>
#include <logdepthbuf_pars_vertex>
#include <shadowmap_pars_vertex>
void main() {
	#include <batching_vertex>
	#include <beginnormal_vertex>
	#include <morphinstance_vertex>
	#include <morphnormal_vertex>
	#include <skinbase_vertex>
	#include <skinnormal_vertex>
	#include <defaultnormal_vertex>
	#include <begin_vertex>
	#include <morphtarget_vertex>
	#include <skinning_vertex>
	#include <project_vertex>
	#include <logdepthbuf_vertex>
	#include <worldpos_vertex>
	#include <shadowmap_vertex>
	#include <fog_vertex>
}`,ul=`uniform vec3 color;
uniform float opacity;
#include <common>
#include <fog_pars_fragment>
#include <bsdfs>
#include <lights_pars_begin>
#include <logdepthbuf_pars_fragment>
#include <shadowmap_pars_fragment>
#include <shadowmask_pars_fragment>
void main() {
	#include <logdepthbuf_fragment>
	gl_FragColor = vec4( color, opacity * ( 1.0 - getShadowMask() ) );
	#include <tonemapping_fragment>
	#include <colorspace_fragment>
	#include <fog_fragment>
	#include <premultiplied_alpha_fragment>
}`,dl=`uniform float rotation;
uniform vec2 center;
#include <common>
#include <uv_pars_vertex>
#include <fog_pars_vertex>
#include <logdepthbuf_pars_vertex>
#include <clipping_planes_pars_vertex>
void main() {
	#include <uv_vertex>
	vec4 mvPosition = modelViewMatrix[ 3 ];
	vec2 scale = vec2( length( modelMatrix[ 0 ].xyz ), length( modelMatrix[ 1 ].xyz ) );
	#ifndef USE_SIZEATTENUATION
		bool isPerspective = isPerspectiveMatrix( projectionMatrix );
		if ( isPerspective ) scale *= - mvPosition.z;
	#endif
	vec2 alignedPosition = ( position.xy - ( center - vec2( 0.5 ) ) ) * scale;
	vec2 rotatedPosition;
	rotatedPosition.x = cos( rotation ) * alignedPosition.x - sin( rotation ) * alignedPosition.y;
	rotatedPosition.y = sin( rotation ) * alignedPosition.x + cos( rotation ) * alignedPosition.y;
	mvPosition.xy += rotatedPosition;
	gl_Position = projectionMatrix * mvPosition;
	#include <logdepthbuf_vertex>
	#include <clipping_planes_vertex>
	#include <fog_vertex>
}`,fl=`uniform vec3 diffuse;
uniform float opacity;
#include <common>
#include <uv_pars_fragment>
#include <map_pars_fragment>
#include <alphamap_pars_fragment>
#include <alphatest_pars_fragment>
#include <alphahash_pars_fragment>
#include <fog_pars_fragment>
#include <logdepthbuf_pars_fragment>
#include <clipping_planes_pars_fragment>
void main() {
	vec4 diffuseColor = vec4( diffuse, opacity );
	#include <clipping_planes_fragment>
	vec3 outgoingLight = vec3( 0.0 );
	#include <logdepthbuf_fragment>
	#include <map_fragment>
	#include <alphamap_fragment>
	#include <alphatest_fragment>
	#include <alphahash_fragment>
	outgoingLight = diffuseColor.rgb;
	#include <opaque_fragment>
	#include <tonemapping_fragment>
	#include <colorspace_fragment>
	#include <fog_fragment>
}`,U={alphahash_fragment:Do,alphahash_pars_fragment:Uo,alphamap_fragment:Fo,alphamap_pars_fragment:Oo,alphatest_fragment:Bo,alphatest_pars_fragment:zo,aomap_fragment:Vo,aomap_pars_fragment:ko,batching_pars_vertex:Go,batching_vertex:Ho,begin_vertex:Wo,beginnormal_vertex:Xo,bsdfs:qo,iridescence_fragment:Yo,bumpmap_pars_fragment:$o,clipping_planes_fragment:Zo,clipping_planes_pars_fragment:Jo,clipping_planes_pars_vertex:Ko,clipping_planes_vertex:Qo,color_fragment:jo,color_pars_fragment:ta,color_pars_vertex:ea,color_vertex:na,common:ia,cube_uv_reflection_fragment:sa,defaultnormal_vertex:ra,displacementmap_pars_vertex:oa,displacementmap_vertex:aa,emissivemap_fragment:ca,emissivemap_pars_fragment:la,colorspace_fragment:ha,colorspace_pars_fragment:ua,envmap_fragment:da,envmap_common_pars_fragment:fa,envmap_pars_fragment:pa,envmap_pars_vertex:ma,envmap_physical_pars_fragment:Ta,envmap_vertex:ga,fog_vertex:_a,fog_pars_vertex:xa,fog_fragment:ya,fog_pars_fragment:va,gradientmap_pars_fragment:Ma,lightmap_pars_fragment:Sa,lights_lambert_fragment:ba,lights_lambert_pars_fragment:Ea,lights_pars_begin:Aa,lights_toon_fragment:wa,lights_toon_pars_fragment:Ca,lights_phong_fragment:Ra,lights_phong_pars_fragment:Ia,lights_physical_fragment:Pa,lights_physical_pars_fragment:La,lights_fragment_begin:Na,lights_fragment_maps:Da,lights_fragment_end:Ua,lightprobes_pars_fragment:Fa,logdepthbuf_fragment:Oa,logdepthbuf_pars_fragment:Ba,logdepthbuf_pars_vertex:za,logdepthbuf_vertex:Va,map_fragment:ka,map_pars_fragment:Ga,map_particle_fragment:Ha,map_particle_pars_fragment:Wa,metalnessmap_fragment:Xa,metalnessmap_pars_fragment:qa,morphinstance_vertex:Ya,morphcolor_vertex:$a,morphnormal_vertex:Za,morphtarget_pars_vertex:Ja,morphtarget_vertex:Ka,normal_fragment_begin:Qa,normal_fragment_maps:ja,normal_pars_fragment:tc,normal_pars_vertex:ec,normal_vertex:nc,normalmap_pars_fragment:ic,clearcoat_normal_fragment_begin:sc,clearcoat_normal_fragment_maps:rc,clearcoat_pars_fragment:oc,iridescence_pars_fragment:ac,opaque_fragment:cc,packing:lc,premultiplied_alpha_fragment:hc,project_vertex:uc,dithering_fragment:dc,dithering_pars_fragment:fc,roughnessmap_fragment:pc,roughnessmap_pars_fragment:mc,shadowmap_pars_fragment:gc,shadowmap_pars_vertex:_c,shadowmap_vertex:xc,shadowmask_pars_fragment:yc,skinbase_vertex:vc,skinning_pars_vertex:Mc,skinning_vertex:Sc,skinnormal_vertex:bc,specularmap_fragment:Ec,specularmap_pars_fragment:Ac,tonemapping_fragment:Tc,tonemapping_pars_fragment:wc,transmission_fragment:Cc,transmission_pars_fragment:Rc,uv_pars_fragment:Ic,uv_pars_vertex:Pc,uv_vertex:Lc,worldpos_vertex:Nc,background_vert:Dc,background_frag:Uc,backgroundCube_vert:Fc,backgroundCube_frag:Oc,cube_vert:Bc,cube_frag:zc,depth_vert:Vc,depth_frag:kc,distance_vert:Gc,distance_frag:Hc,equirect_vert:Wc,equirect_frag:Xc,linedashed_vert:qc,linedashed_frag:Yc,meshbasic_vert:$c,meshbasic_frag:Zc,meshlambert_vert:Jc,meshlambert_frag:Kc,meshmatcap_vert:Qc,meshmatcap_frag:jc,meshnormal_vert:tl,meshnormal_frag:el,meshphong_vert:nl,meshphong_frag:il,meshphysical_vert:sl,meshphysical_frag:rl,meshtoon_vert:ol,meshtoon_frag:al,points_vert:cl,points_frag:ll,shadow_vert:hl,shadow_frag:ul,sprite_vert:dl,sprite_frag:fl},E={common:{diffuse:{value:new Z(16777215)},opacity:{value:1},map:{value:null},mapTransform:{value:new L},alphaMap:{value:null},alphaMapTransform:{value:new L},alphaTest:{value:0}},specularmap:{specularMap:{value:null},specularMapTransform:{value:new L}},envmap:{envMap:{value:null},envMapRotation:{value:new L},reflectivity:{value:1},ior:{value:1.5},refractionRatio:{value:.98},dfgLUT:{value:null}},aomap:{aoMap:{value:null},aoMapIntensity:{value:1},aoMapTransform:{value:new L}},lightmap:{lightMap:{value:null},lightMapIntensity:{value:1},lightMapTransform:{value:new L}},bumpmap:{bumpMap:{value:null},bumpMapTransform:{value:new L},bumpScale:{value:1}},normalmap:{normalMap:{value:null},normalMapTransform:{value:new L},normalScale:{value:new et(1,1)}},displacementmap:{displacementMap:{value:null},displacementMapTransform:{value:new L},displacementScale:{value:1},displacementBias:{value:0}},emissivemap:{emissiveMap:{value:null},emissiveMapTransform:{value:new L}},metalnessmap:{metalnessMap:{value:null},metalnessMapTransform:{value:new L}},roughnessmap:{roughnessMap:{value:null},roughnessMapTransform:{value:new L}},gradientmap:{gradientMap:{value:null}},fog:{fogDensity:{value:25e-5},fogNear:{value:1},fogFar:{value:2e3},fogColor:{value:new Z(16777215)}},lights:{ambientLightColor:{value:[]},lightProbe:{value:[]},sunLights:{value:[],properties:{direction:{},color:{}}},sunLightShadows:{value:[],properties:{shadowIntensity:1,shadowBias:{},shadowNormalBias:{},shadowRadius:{},shadowMapSize:{}}},sunShadowMatrix:{value:[]},sunShadowCascade:{value:[]},directionalLights:{value:[],properties:{direction:{},color:{}}},directionalLightShadows:{value:[],properties:{shadowIntensity:1,shadowBias:{},shadowNormalBias:{},shadowRadius:{},shadowMapSize:{}}},directionalShadowMatrix:{value:[]},spotLights:{value:[],properties:{color:{},position:{},direction:{},distance:{},coneCos:{},penumbraCos:{},decay:{}}},spotLightShadows:{value:[],properties:{shadowIntensity:1,shadowBias:{},shadowNormalBias:{},shadowRadius:{},shadowMapSize:{}}},spotLightMap:{value:[]},spotLightMatrix:{value:[]},pointLights:{value:[],properties:{color:{},position:{},decay:{},distance:{}}},pointLightShadows:{value:[],properties:{shadowIntensity:1,shadowBias:{},shadowNormalBias:{},shadowRadius:{},shadowMapSize:{},shadowCameraNear:{},shadowCameraFar:{}}},pointShadowMatrix:{value:[]},hemisphereLights:{value:[],properties:{direction:{},skyColor:{},groundColor:{}}},rectAreaLights:{value:[],properties:{color:{},position:{},width:{},height:{}}},ltc_1:{value:null},ltc_2:{value:null},probesSH:{value:null},probesMin:{value:new D},probesMax:{value:new D},probesResolution:{value:new D}},points:{diffuse:{value:new Z(16777215)},opacity:{value:1},size:{value:1},scale:{value:1},map:{value:null},alphaMap:{value:null},alphaMapTransform:{value:new L},alphaTest:{value:0},uvTransform:{value:new L}},sprite:{diffuse:{value:new Z(16777215)},opacity:{value:1},center:{value:new et(.5,.5)},rotation:{value:0},map:{value:null},mapTransform:{value:new L},alphaMap:{value:null},alphaMapTransform:{value:new L},alphaTest:{value:0}}},us={basic:{uniforms:nt([E.common,E.specularmap,E.envmap,E.aomap,E.lightmap,E.fog]),vertexShader:U.meshbasic_vert,fragmentShader:U.meshbasic_frag},lambert:{uniforms:nt([E.common,E.specularmap,E.envmap,E.aomap,E.lightmap,E.emissivemap,E.bumpmap,E.normalmap,E.displacementmap,E.fog,E.lights,{emissive:{value:new Z(0)},envMapIntensity:{value:1}}]),vertexShader:U.meshlambert_vert,fragmentShader:U.meshlambert_frag},phong:{uniforms:nt([E.common,E.specularmap,E.envmap,E.aomap,E.lightmap,E.emissivemap,E.bumpmap,E.normalmap,E.displacementmap,E.fog,E.lights,{emissive:{value:new Z(0)},specular:{value:new Z(1118481)},shininess:{value:30},envMapIntensity:{value:1}}]),vertexShader:U.meshphong_vert,fragmentShader:U.meshphong_frag},standard:{uniforms:nt([E.common,E.envmap,E.aomap,E.lightmap,E.emissivemap,E.bumpmap,E.normalmap,E.displacementmap,E.roughnessmap,E.metalnessmap,E.fog,E.lights,{emissive:{value:new Z(0)},roughness:{value:1},metalness:{value:0},envMapIntensity:{value:1}}]),vertexShader:U.meshphysical_vert,fragmentShader:U.meshphysical_frag},toon:{uniforms:nt([E.common,E.aomap,E.lightmap,E.emissivemap,E.bumpmap,E.normalmap,E.displacementmap,E.gradientmap,E.fog,E.lights,{emissive:{value:new Z(0)}}]),vertexShader:U.meshtoon_vert,fragmentShader:U.meshtoon_frag},matcap:{uniforms:nt([E.common,E.bumpmap,E.normalmap,E.displacementmap,E.fog,{matcap:{value:null}}]),vertexShader:U.meshmatcap_vert,fragmentShader:U.meshmatcap_frag},points:{uniforms:nt([E.points,E.fog]),vertexShader:U.points_vert,fragmentShader:U.points_frag},dashed:{uniforms:nt([E.common,E.fog,{scale:{value:1},dashSize:{value:1},totalSize:{value:2}}]),vertexShader:U.linedashed_vert,fragmentShader:U.linedashed_frag},depth:{uniforms:nt([E.common,E.displacementmap]),vertexShader:U.depth_vert,fragmentShader:U.depth_frag},normal:{uniforms:nt([E.common,E.bumpmap,E.normalmap,E.displacementmap,{opacity:{value:1}}]),vertexShader:U.meshnormal_vert,fragmentShader:U.meshnormal_frag},sprite:{uniforms:nt([E.sprite,E.fog]),vertexShader:U.sprite_vert,fragmentShader:U.sprite_frag},background:{uniforms:{uvTransform:{value:new L},t2D:{value:null},backgroundIntensity:{value:1}},vertexShader:U.background_vert,fragmentShader:U.background_frag},backgroundCube:{uniforms:{envMap:{value:null},backgroundBlurriness:{value:0},backgroundIntensity:{value:1},backgroundRotation:{value:new L}},vertexShader:U.backgroundCube_vert,fragmentShader:U.backgroundCube_frag},cube:{uniforms:{tCube:{value:null},tFlip:{value:-1},opacity:{value:1}},vertexShader:U.cube_vert,fragmentShader:U.cube_frag},equirect:{uniforms:{tEquirect:{value:null}},vertexShader:U.equirect_vert,fragmentShader:U.equirect_frag},distance:{uniforms:nt([E.common,E.displacementmap,{referencePosition:{value:new D},nearDistance:{value:1},farDistance:{value:1e3}}]),vertexShader:U.distance_vert,fragmentShader:U.distance_frag},shadow:{uniforms:nt([E.lights,E.fog,{color:{value:new Z(0)},opacity:{value:1}}]),vertexShader:U.shadow_vert,fragmentShader:U.shadow_frag}};us.physical={uniforms:nt([us.standard.uniforms,{clearcoat:{value:0},clearcoatMap:{value:null},clearcoatMapTransform:{value:new L},clearcoatNormalMap:{value:null},clearcoatNormalMapTransform:{value:new L},clearcoatNormalScale:{value:new et(1,1)},clearcoatRoughness:{value:0},clearcoatRoughnessMap:{value:null},clearcoatRoughnessMapTransform:{value:new L},dispersion:{value:0},retroreflectivity:{value:0},iridescence:{value:0},iridescenceMap:{value:null},iridescenceMapTransform:{value:new L},iridescenceIOR:{value:1.3},iridescenceThicknessMinimum:{value:100},iridescenceThicknessMaximum:{value:400},iridescenceThicknessMap:{value:null},iridescenceThicknessMapTransform:{value:new L},sheen:{value:0},sheenColor:{value:new Z(0)},sheenColorMap:{value:null},sheenColorMapTransform:{value:new L},sheenRoughness:{value:1},sheenRoughnessMap:{value:null},sheenRoughnessMapTransform:{value:new L},transmission:{value:0},transmissionMap:{value:null},transmissionMapTransform:{value:new L},transmissionSamplerSize:{value:new et},transmissionSamplerMap:{value:null},thickness:{value:0},thicknessMap:{value:null},thicknessMapTransform:{value:new L},attenuationDistance:{value:0},attenuationColor:{value:new Z(0)},specularColor:{value:new Z(1,1,1)},specularColorMap:{value:null},specularColorMapTransform:{value:new L},specularIntensity:{value:1},specularIntensityMap:{value:null},specularIntensityMapTransform:{value:new L},anisotropyVector:{value:new et},anisotropyMap:{value:null},anisotropyMapTransform:{value:new L}}]),vertexShader:U.meshphysical_vert,fragmentShader:U.meshphysical_frag};var pl=new L;pl.set(-1,0,0,0,1,0,0,0,1);var r0={[Wn]:"LINEAR_TONE_MAPPING",[Xn]:"REINHARD_TONE_MAPPING",[qn]:"CINEON_TONE_MAPPING",[Yn]:"ACES_FILMIC_TONE_MAPPING",[Zn]:"AGX_TONE_MAPPING",[Jn]:"NEUTRAL_TONE_MAPPING",[$n]:"CUSTOM_TONE_MAPPING"};var o0=new Float32Array(16),a0=new Float32Array(9),c0=new Float32Array(4);var l0={[Wn]:"Linear",[Xn]:"Reinhard",[qn]:"Cineon",[Yn]:"ACESFilmic",[Zn]:"AgX",[Jn]:"Neutral",[$n]:"Custom"};var h0={[Xi]:"SHADOWMAP_TYPE_PCF",[qi]:"SHADOWMAP_TYPE_VSM"};var u0={[Ji]:"ENVMAP_TYPE_CUBE",[Qn]:"ENVMAP_TYPE_CUBE",[Ki]:"ENVMAP_TYPE_CUBE_UV"};var d0={[Qn]:"ENVMAP_MODE_REFRACTION"};var f0={[Yi]:"ENVMAP_BLENDING_MULTIPLY",[$i]:"ENVMAP_BLENDING_MIX",[Zi]:"ENVMAP_BLENDING_ADD"};var ml=new L;ml.set(-1,0,0,0,1,0,0,0,1);var p0=new Uint16Array([12469,15057,12620,14925,13266,14620,13807,14376,14323,13990,14545,13625,14713,13328,14840,12882,14931,12528,14996,12233,15039,11829,15066,11525,15080,11295,15085,10976,15082,10705,15073,10495,13880,14564,13898,14542,13977,14430,14158,14124,14393,13732,14556,13410,14702,12996,14814,12596,14891,12291,14937,11834,14957,11489,14958,11194,14943,10803,14921,10506,14893,10278,14858,9960,14484,14039,14487,14025,14499,13941,14524,13740,14574,13468,14654,13106,14743,12678,14818,12344,14867,11893,14889,11509,14893,11180,14881,10751,14852,10428,14812,10128,14765,9754,14712,9466,14764,13480,14764,13475,14766,13440,14766,13347,14769,13070,14786,12713,14816,12387,14844,11957,14860,11549,14868,11215,14855,10751,14825,10403,14782,10044,14729,9651,14666,9352,14599,9029,14967,12835,14966,12831,14963,12804,14954,12723,14936,12564,14917,12347,14900,11958,14886,11569,14878,11247,14859,10765,14828,10401,14784,10011,14727,9600,14660,9289,14586,8893,14508,8533,15111,12234,15110,12234,15104,12216,15092,12156,15067,12010,15028,11776,14981,11500,14942,11205,14902,10752,14861,10393,14812,9991,14752,9570,14682,9252,14603,8808,14519,8445,14431,8145,15209,11449,15208,11451,15202,11451,15190,11438,15163,11384,15117,11274,15055,10979,14994,10648,14932,10343,14871,9936,14803,9532,14729,9218,14645,8742,14556,8381,14461,8020,14365,7603,15273,10603,15272,10607,15267,10619,15256,10631,15231,10614,15182,10535,15118,10389,15042,10167,14963,9787,14883,9447,14800,9115,14710,8665,14615,8318,14514,7911,14411,7507,14279,7198,15314,9675,15313,9683,15309,9712,15298,9759,15277,9797,15229,9773,15166,9668,15084,9487,14995,9274,14898,8910,14800,8539,14697,8234,14590,7790,14479,7409,14367,7067,14178,6621,15337,8619,15337,8631,15333,8677,15325,8769,15305,8871,15264,8940,15202,8909,15119,8775,15022,8565,14916,8328,14804,8009,14688,7614,14569,7287,14448,6888,14321,6483,14088,6171,15350,7402,15350,7419,15347,7480,15340,7613,15322,7804,15287,7973,15229,8057,15148,8012,15046,7846,14933,7611,14810,7357,14682,7069,14552,6656,14421,6316,14251,5948,14007,5528,15356,5942,15356,5977,15353,6119,15348,6294,15332,6551,15302,6824,15249,7044,15171,7122,15070,7050,14949,6861,14818,6611,14679,6349,14538,6067,14398,5651,14189,5311,13935,4958,15359,4123,15359,4153,15356,4296,15353,4646,15338,5160,15311,5508,15263,5829,15188,6042,15088,6094,14966,6001,14826,5796,14678,5543,14527,5287,14377,4985,14133,4586,13869,4257,15360,1563,15360,1642,15358,2076,15354,2636,15341,3350,15317,4019,15273,4429,15203,4732,15105,4911,14981,4932,14836,4818,14679,4621,14517,4386,14359,4156,14083,3795,13808,3437,15360,122,15360,137,15358,285,15355,636,15344,1274,15322,2177,15281,2765,15215,3223,15120,3451,14995,3569,14846,3567,14681,3466,14511,3305,14344,3121,14037,2800,13753,2467,15360,0,15360,1,15359,21,15355,89,15346,253,15325,479,15287,796,15225,1148,15133,1492,15008,1749,14856,1882,14685,1886,14506,1783,14324,1608,13996,1398,13702,1183]);var dt=1e-6,xt=1e-4;function gs(s){let t=0;for(let e=0;e<s.length;e+=1){let[n,i]=s[e],[r,o]=s[(e+1)%s.length];t+=n*o-r*i}return t/2}d(gs,"polygonArea");function gl(s){return Math.abs(gs(s))}d(gl,"polygonAbsArea");function Qe(s){let t=gs(s);if(Math.abs(t)<=dt){let i=s.reduce((r,[o,a])=>[r[0]+o,r[1]+a],[0,0]);return[i[0]/s.length,i[1]/s.length]}let e=0,n=0;for(let i=0;i<s.length;i+=1){let[r,o]=s[i],[a,c]=s[(i+1)%s.length],l=r*c-a*o;e+=(r+a)*l,n+=(o+c)*l}return[e/(6*t),n/(6*t)]}d(Qe,"loopCentroid");function pt(s,t){return(t[0]-s.origin[0])*s.normal[0]+(t[1]-s.origin[1])*s.normal[1]}d(pt,"foldSignedDistance");function ye(s,t){return(t[0]-s.origin[0])*s.direction[0]+(t[1]-s.origin[1])*s.direction[1]}d(ye,"foldAlongCoordinate");function ii(s){let t=[];for(let e of s){let n=t[t.length-1];(!n||Math.hypot(e[0]-n[0],e[1]-n[1])>xt)&&t.push(e)}for(;t.length>1;){let e=t[0],n=t[t.length-1];if(Math.hypot(e[0]-n[0],e[1]-n[1])<=xt){t.pop();continue}break}return t}d(ii,"dropRepeatedPoints");function _l(s,t){let e=d((h,f,m,p)=>h*p-f*m,"cross"),[n,i]=[s.start,s.end],[r,o]=[t.start,t.end],a=e(o[0]-r[0],o[1]-r[1],n[0]-r[0],n[1]-r[1]),c=e(o[0]-r[0],o[1]-r[1],i[0]-r[0],i[1]-r[1]),l=e(i[0]-n[0],i[1]-n[1],r[0]-n[0],r[1]-n[1]),u=e(i[0]-n[0],i[1]-n[1],o[0]-n[0],o[1]-n[1]);return a>0!=c>0&&l>0!=u>0}d(_l,"segmentsCross");function xl(s,t,e){let n=e[0]-t[0],i=e[1]-t[1],r=n*n+i*i;if(r<=dt)return Math.hypot(s[0]-t[0],s[1]-t[1]);let o=Math.max(0,Math.min(1,((s[0]-t[0])*n+(s[1]-t[1])*i)/r));return Math.hypot(s[0]-(t[0]+o*n),s[1]-(t[1]+o*i))}d(xl,"pointToSegmentDistance");function ds(s,t){let e=1/0;for(let n=0;n<t.length;n+=1)e=Math.min(e,xl(s,t[n],t[(n+1)%t.length]));return e}d(ds,"distanceToLoopBoundary");function fs(s,t,e=.05){let n=s.bendLine.start,i=s.bendLine.end,r=ds(n,t.outerLoop),o=ds(i,t.outerLoop),a=9,c=0;for(let l=1;l<a;l+=1){let u=l/a,h=[n[0]+u*(i[0]-n[0]),n[1]+u*(i[1]-n[1])];ri(h,t.outerLoop)&&(c+=1)}return{crosses:r<=e&&o<=e&&c===a-1,startGap:r,endGap:o,interiorFraction:c/(a-1)}}d(fs,"foldSegmentCrossesRegion");function ps(s,t){let e=null;for(let n=0;n<s.length;n+=1){let i=s[n],r=s[(n+1)%s.length],o=r[0]-i[0],a=r[1]-i[1],c=o*o+a*a;if(c<=dt)continue;let l=Math.max(0,Math.min(1,((t[0]-i[0])*o+(t[1]-i[1])*a)/c)),u=[i[0]+l*o,i[1]+l*a],h=Math.hypot(t[0]-u[0],t[1]-u[1]);(!e||h<e.distance)&&(e={edgeIndex:n,t:l,point:u,distance:h})}return e}d(ps,"projectPointOntoLoop");function yl(s,t,e){let n=ps(s,t),i=ps(s,e);if(!n||!i)return null;let[r,o]=n.edgeIndex+n.t<=i.edgeIndex+i.t?[n,i]:[i,n];if(r.edgeIndex===o.edgeIndex&&Math.abs(r.t-o.t)<=dt)return null;let a=[r.point];for(let l=r.edgeIndex+1;l<=o.edgeIndex;l+=1)a.push(s[l%s.length]);a.push(o.point);let c=[o.point];for(let l=o.edgeIndex+1;l<=r.edgeIndex+s.length;l+=1)c.push(s[l%s.length]);return c.push(r.point),[ii(a),ii(c)]}d(yl,"splitLoopAtSegment");function ms(s,t,e,n){let i=e*t.halfWidth,r=d(_=>e*pt(t,_)>=t.halfWidth-xt,"clearOfBand"),o=d(_=>{let x=ye(t,_);return x>=n.min-xt&&x<=n.max+xt},"withinSpan"),a=d(_=>[t.origin[0]+_*t.direction[0]+i*t.normal[0],t.origin[1]+_*t.direction[1]+i*t.normal[1]],"bandEdgePoint"),c=d((_,x)=>{let g=e*pt(t,_)-t.halfWidth,y=e*pt(t,x)-t.halfWidth-g;if(Math.abs(y)<=dt)return null;let v=-g/y;return[_[0]+v*(x[0]-_[0]),_[1]+v*(x[1]-_[1])]},"crossingToBandEdge"),l=d((_,x,g)=>{let M=ye(t,_),v=ye(t,x)-M;if(Math.abs(v)<=dt)return null;let b=(g-M)/v;return b<-xt||b>1+xt?null:[_[0]+b*(x[0]-_[0]),_[1]+b*(x[1]-_[1])]},"crossingAtAlong"),u=d(_=>{let x=0;for(;x<_.length;){let A=s[_[x]];if(r(A)||!o(A))break;x+=1}if(x>=_.length)return null;let g=s[_[x]];if(r(g)){let A=x>0?s[_[x-1]]:null,R=A?c(A,g):null;return{drop:x,insert:R?[R]:[]}}let y=ye(t,g)>n.max?n.max:n.min,v=x>0?s[_[x-1]]:null,b=v?l(v,g,y):null;return{drop:x,insert:b?[a(y),b]:[a(y)]}},"lead"),h=s.map((_,x)=>x),f=u(h),m=u([...h].reverse());if(!f||!m)return[];let p=s.slice(f.drop,s.length-m.drop);return ii([...f.insert,...p,...[...m.insert].reverse()])}d(ms,"trimBandFromFace");function vl(s,t,e){let n=yl(s,t.bendLine.start,t.bendLine.end);if(!n)return null;let i=n.map(o=>o.length>=3&&pt(t,Qe(o))>=0?1:-1);if(i[0]===i[1])return null;let r=i[0]===1?0:1;return{positive:ms(n[r],t,1,e),negative:ms(n[1-r],t,-1,e)}}d(vl,"splitFaceAtFold");function _s(s,t,{tolerance:e=.05}={}){let n=[{loop:s,sides:[]}],i=[];for(let a=0;a<t.length;a+=1){let c=t[a],l=-1,u=null;for(let y=0;y<n.length;y+=1){let v=fs(c,{outerLoop:n[y].loop},e);if(v.crosses){l=y;break}(!u||v.interiorFraction>u.interiorFraction)&&(u=v)}if(l<0){if(n.filter(b=>fs(c,{outerLoop:b.loop},e).interiorFraction>0).length>1){let b=t.slice(0,a).map((A,R)=>({other:A,otherIndex:R})).filter(({other:A})=>_l(c.bendLine,A.bendLine)).map(({otherIndex:A})=>`bend ${A+1}`);throw new Error(`DXF 3D bend preview cannot fold crossing bend lines: bend ${a+1} crosses ${b.length?b.join(" and "):"another bend"} inside the material. One blank cannot be folded along both -- a brake needs each fold to separate two faces, and at the crossing all four quarters would have to move at once. Add a relief cut at the crossing, or shorten one line so the folds meet end to end.`)}let v=Math.max(u?.startGap||0,u?.endGap||0);throw new Error(`DXF 3D bend preview requires a fold line that runs edge to edge: bend ${a+1}, from (${c.bendLine.start[0].toFixed(3)}, ${c.bendLine.start[1].toFixed(3)}) to (${c.bendLine.end[0].toFixed(3)}, ${c.bendLine.end[1].toFixed(3)}), does not cut any face of the blank in two (its ends stop ${v.toFixed(3)} mm short of the material's edge). Extend the bend line, or add relief cuts at its ends so the fold really does separate the two faces.`)}let h=n[l],f=vs(c),m={min:f.min,max:f.max},p=vl(h.loop,c,m),_=p?.negative||[],x=p?.positive||[];if(_.length<3||x.length<3)throw new Error(`DXF 3D bend preview could not split the blank at bend ${a+1}: its bend radius band covers the whole face.`);let g={loop:_,sides:[...h.sides,{foldIndex:a,side:-1}]},M={loop:x,sides:[...h.sides,{foldIndex:a,side:1}]};n=[...n.slice(0,l),g,M,...n.slice(l+1)],i.push({foldIndex:a,negative:g,positive:M})}let r=n.map((a,c)=>({id:`region-${c}`,index:c,outerLoop:a.loop,holeLoops:[],sides:t.map((l,u)=>({foldIndex:u,side:pt(l,Qe(a.loop))>=0?1:-1})),area:gl(a.loop),centroid:Qe(a.loop)})),o=Ml(r,t);return{regions:r,adjacency:o}}d(_s,"decomposeFoldRegions");function si(s,t){return s.sides.find(e=>e.foldIndex===t)?.side||0}d(si,"sideOf");function Ml(s,t){let e=[];return t.forEach((n,i)=>{let r=null;for(let o=0;o<s.length;o+=1)for(let a=o+1;a<s.length;a+=1){if(si(s[o],i)===si(s[a],i))continue;let c=Sl(s[o],s[a],n);c<=xt||(!r||c>r.contactLength)&&(r={foldIndex:i,regions:[o,a],contactLength:c})}r&&e.push(r)}),e}d(Ml,"buildFoldAdjacency");function Sl(s,t,e){let n=ve(s,e),i=ve(t,e);return!n||!i?0:Math.max(0,Math.min(n.max,i.max)-Math.max(n.min,i.min))}d(Sl,"foldContactLength");function ve(s,t){let e=1/0,n=-1/0;for(let i of s.outerLoop){let r=Math.abs(pt(t,i));if(Math.abs(r-t.halfWidth)>.001)continue;let o=(i[0]-t.origin[0])*t.direction[0]+(i[1]-t.origin[1])*t.direction[1];e=Math.min(e,o),n=Math.max(n,o)}return Number.isFinite(e)&&n>e?{min:e,max:n}:null}d(ve,"foldLineSpanForRegion");function bl(s,t){let e=Math.abs(s.angleRadians);if(e<=1e-9||s.halfWidth<=dt)return new W().identity();let n=s.angleRadians<0?-1:1,i=s.halfWidth,r=s.neutralRadius,o=new D(s.normal[0],0,s.normal[1]).multiplyScalar(t>=0?1:-1),a=new D(s.direction[0],0,s.direction[1]),c=new W().makeBasis(o,new D(0,1,0),a),l=new W().makeTranslation(s.origin[0],0,s.origin[1]),u=new W().makeTranslation(-i,0,0).multiply(new W().makeRotationAxis(new D(0,0,1),n*e)).multiply(new W().makeTranslation(i,0,0)),h=new D(i,0,0).applyMatrix4(u),f=new D(-i+r*Math.sin(e),n*r*(1-Math.cos(e)),0),m=new W().makeTranslation(f.x-h.x,f.y-h.y,0).multiply(u);return l.clone().multiply(c).multiply(m).multiply(c.clone().invert()).multiply(l.clone().invert())}d(bl,"foldHingeMatrix");function xs(s,t,e){let n=s.map(()=>new W().identity());if(!s.length)return{placements:n,rootIndex:-1,parents:[]};let i=s.map(()=>0);for(let u of e)i[u.regions[0]]+=1,i[u.regions[1]]+=1;let r=s.reduce((u,h,f)=>i[f]!==i[u]?i[f]>i[u]?f:u:h.area>s[u].area?f:u,0),o=s.map(()=>[]);for(let u of e){let[h,f]=u.regions;o[h].push({region:f,foldIndex:u.foldIndex}),o[f].push({region:h,foldIndex:u.foldIndex})}let a=s.map(()=>null),c=s.map(()=>!1);c[r]=!0;let l=[r];for(;l.length;){let u=l.shift();for(let h of o[u]){if(c[h.region])continue;c[h.region]=!0,a[h.region]={region:u,foldIndex:h.foldIndex};let f=t[h.foldIndex],m=si(s[h.region],h.foldIndex);n[h.region]=n[u].clone().multiply(bl(f,m)),l.push(h.region)}}return{placements:n,rootIndex:r,parents:a,visited:c}}d(xs,"buildRegionPlacements");function ys({bendLine:s,angleRadians:t,insideRadiusMm:e=0,kFactor:n=.5,halfThicknessMm:i=1}){let r=s.end[0]-s.start[0],o=s.end[1]-s.start[1],a=Math.hypot(r,o);if(!(a>dt))return null;let c=[r/a,o/a],l=[-c[1],c[0]],u=e>0?e:Math.max(i*2*.6,dt),h=u+n*i*2,f=Math.abs(t);return{bendLine:s,origin:[s.start[0],s.start[1]],direction:c,normal:l,angleRadians:t,neutralRadius:h,insideRadius:u,halfWidth:f>1e-9?h*f/2:0,length:a}}d(ys,"buildFoldLine");function vs(s){let t=d(i=>(i[0]-s.origin[0])*s.direction[0]+(i[1]-s.origin[1])*s.direction[1],"at"),e=t(s.bendLine.start),n=t(s.bendLine.end);return{min:Math.min(e,n),max:Math.max(e,n)}}d(vs,"foldLineSpan");function ri(s,t){let e=!1;for(let n=0,i=t.length-1;n<t.length;i=n,n+=1){let[r,o]=t[n],[a,c]=t[i];o>s[1]!=c>s[1]&&s[0]<(a-r)*(s[1]-o)/(c-o||dt)+r&&(e=!e)}return e}d(ri,"pointInsideLoop");function Ms(s,t,e){for(let n of t){for(let o=0;o<e.length;o+=1){let a=e[o];if(a.halfWidth<=dt)continue;let c=vs(a),l=n.map(p=>ye(a,p));if(Math.min(...l)>c.max+a.halfWidth||Math.max(...l)<c.min-a.halfWidth)continue;let h=n.map(p=>pt(a,p)),f=h.some(p=>Math.abs(p)<a.halfWidth-xt),m=h.some(p=>p>0)&&h.some(p=>p<0);if(f||m)throw new Error(`DXF 3D bend preview does not support holes crossing bend radius bands: a cutout crosses bend ${o+1}`)}let i=Qe(n),r=s.find(o=>ri(i,o.outerLoop))||s.find(o=>n.every(a=>ri(a,o.outerLoop)));r&&r.holeLoops.push(n)}return s}d(Ms,"assignHolesToRegions");function El(s,t){let e=new D(s.normal[0],0,s.normal[1]).multiplyScalar(t>=0?1:-1),n=new D(s.direction[0],0,s.direction[1]),i=new W().makeBasis(e,new D(0,1,0),n);return new W().makeTranslation(s.origin[0],0,s.origin[1]).multiply(i)}d(El,"foldBasis");function Ss({foldLine:s,side:t,span:e,halfThickness:n,parentMatrix:i=new W().identity(),segments:r=0}){let o=Math.abs(s.angleRadians);if(o<=1e-9||!e||e.max-e.min<=dt)return{triangles:[],edges:[]};let a=s.angleRadians<0?-1:1,c=s.neutralRadius,l=Math.max(r||Math.ceil(o/(Math.PI/18)+1),2),u=i.clone().multiply(El(s,t)),h=d((g,M,y)=>new D(g,M,y).applyMatrix4(u).toArray(),"toWorld"),f={u:-s.halfWidth,y:a*c},m=[];for(let g=0;g<=l;g+=1){let M=g/l*o,y=f.u+c*Math.sin(M),v=f.y-a*c*Math.cos(M),b=Math.sin(M)*a,A=-Math.cos(M);m.push({u:y,y:v,outer:[y+b*n*a,v+A*n*a],inner:[y-b*n*a,v-A*n*a]})}let p=[],_=[],x=d((g,M,y,v)=>{p.push([g,M,y],[g,y,v])},"quad");for(let g=0;g<m.length-1;g+=1){let M=m[g],y=m[g+1];for(let v of["outer","inner"]){let b=v==="inner",A=h(M[v][0],M[v][1],e.min),R=h(y[v][0],y[v][1],e.min),z=h(y[v][0],y[v][1],e.max),w=h(M[v][0],M[v][1],e.max);b?x(A,w,z,R):x(A,R,z,w)}for(let[v,b]of[[e.min,!1],[e.max,!0]]){let A=h(M.outer[0],M.outer[1],v),R=h(y.outer[0],y.outer[1],v),z=h(y.inner[0],y.inner[1],v),w=h(M.inner[0],M.inner[1],v);b?x(A,w,z,R):x(A,R,z,w)}}for(let g of["outer","inner"])for(let M of[e.min,e.max])for(let y=0;y<m.length-1;y+=1)_.push([h(m[y][g][0],m[y][g][1],M),h(m[y+1][g][0],m[y+1][g][1],M)]);return{triangles:p,edges:_}}d(Ss,"buildFoldBridgeGeometry");var ai=2,bs=.2,Es=25,ci=0,As=0,Ts=180,je={UP:"up",DOWN:"down"},ws=1e3,Al=.35,Tl=10,wl=160,Cs=.04,Ct=.001;function Rt(s,t,e){return Math.min(Math.max(s,t),e)}d(Rt,"clamp");function it(s,t=0){let e=Number(s);return Number.isFinite(e)?e:t}d(it,"toFiniteNumber");function jt(s){return!Array.isArray(s)||s.length<2?[0,0]:[it(s[0]),it(s[1])]}d(jt,"normalizePoint");function ui(s,t,e=Ct){return Math.abs(s[0]-t[0])<=e&&Math.abs(s[1]-t[1])<=e}d(ui,"pointsEqual");function Me(s){return`${Math.round(s[0]*ws)}:${Math.round(s[1]*ws)}`}d(Me,"pointKey");function li(s){return[...s].reverse()}d(li,"reversePoints");function Ls(s){return s.length>1&&ui(s[0],s[s.length-1])?s.slice(0,-1):s}d(Ls,"removeDuplicateClosure");function Ns(s){let t=[];for(let e of s)t.length&&ui(t[t.length-1],e)||t.push(e);return Ls(t)}d(Ns,"removeConsecutiveDuplicates");function Cl(s,t){let e=Math.max(Math.abs(s),.01),n=Rt(1-Al/e,-1,1),i=n<=-1?Math.PI/8:Rt(2*Math.acos(n),Math.PI/64,Math.PI/10);return Rt(Math.ceil(Math.max(Math.abs(t),Math.PI/36)/i),Tl,wl)}d(Cl,"sampleCountForSweep");function Ds(s,t,e,n){let i=it(e)*Math.PI/180,r=it(n)*Math.PI/180,o=Cl(t,r),a=[];for(let c=0;c<=o;c+=1){let l=c/o,u=i+r*l;a.push([s[0]+t*Math.cos(u),s[1]+t*Math.sin(u)])}return a}d(Ds,"sampleArcPoints");function Rs(s,t){let e=Ds(s,t,0,360);return Ls(e)}d(Rs,"sampleCirclePoints");function hi(s){if(!Array.isArray(s)||s.length<3)return 0;let t=0;for(let e=0;e<s.length;e+=1){let n=s[e],i=s[(e+1)%s.length];t+=n[0]*i[1]-i[0]*n[1]}return t/2}d(hi,"polygonSignedArea");function te(s,{clockwise:t}){let e=Ns(s);if(e.length<3)return e;let n=e.map(([r,o])=>new et(r,o)),i=Qt.isClockWise(n);return t&&!i||!t&&i?li(e):e}d(te,"normalizeLoopWinding");function di(s){let t=s?.geometry||{},e=Array.isArray(t.lines)?t.lines:[],n=Array.isArray(t.arcs)?t.arcs:[],i=Array.isArray(t.circles)?t.circles:[],r=[],o=[],a=[],c=[];for(let l of e){let u=jt(l?.start),h=jt(l?.end),f=String(l?.kind||"").trim().toLowerCase();if(f==="bend"){a.push([u,h]);continue}if(!ui(u,h)){if(f==="engrave"){c.push([u,h]);continue}f&&f!=="cut"||r.push({points:[u,h]})}}for(let l of n){let u=jt(l?.center),h=Math.max(it(l?.radius),0);if(h<=0)continue;let f=String(l?.kind||"").trim().toLowerCase(),m=Ds(u,h,it(l?.startAngleDeg),it(l?.sweepAngleDeg));if(f==="bend"){a.push([m[0],m[m.length-1]]);continue}if(f==="engrave"){c.push(m);continue}f&&f!=="cut"||r.push({points:m})}for(let l of i){let u=jt(l?.center),h=Math.max(it(l?.radius),0);if(h<=0)continue;let f=String(l?.kind||"").trim().toLowerCase();if(f==="engrave"){let m=Rs(u,h);c.push([...m,m[0]]);continue}f&&f!=="cut"||o.push(Rs(u,h))}return{cutPrimitives:r,cutCircleLoops:o,bendLines:a,engravePolylines:c}}d(di,"readGeometryRecords");function Us(s){let t=new Map,e=new Set,n=[],i=[],r=d((o,a)=>{let c=t.get(o);if(c){c.push(a);return}t.set(o,[a])},"addAdjacency");s.forEach((o,a)=>{let c=Me(o.points[0]),l=Me(o.points[o.points.length-1]);r(c,{index:a,reverse:!1}),r(l,{index:a,reverse:!0})});for(let o=0;o<s.length;o+=1){if(e.has(o))continue;e.add(o);let a=[...s[o].points],c=0,l=d(()=>{let h=Me(a[0]),f=Me(a[a.length-1]);for(;f!==h;){let m=(t.get(f)||[]).filter(({index:g})=>!e.has(g));if(!m.length)return!1;let p=m[0];e.add(p.index);let _=s[p.index].points,x=p.reverse?li(_):_;if(a=a.concat(x.slice(1)),f=Me(x[x.length-1]),c+=1,c>s.length+4)throw new Error("DXF preview contour walk did not terminate")}return!0},"extend"),u=l();if(u||(a=li(a),u=l()),u){a=Ns(a),a.length>=3&&n.push(a);continue}a.length>=2&&i.push(a)}return{loops:n,openChains:i}}d(Us,"chainCutPrimitives");function Rl(s){let{cutPrimitives:t,cutCircleLoops:e,bendLines:n}=di(s);if(!t.length&&!e.length)throw new Error("DXF preview requires cut-layer contour geometry");let{loops:i}=Us(t);for(let r of e)r.length>=3&&i.push(r);if(!i.length)throw new Error("DXF preview could not resolve any closed cut contours");return{loops:i,bendLines:n}}d(Rl,"buildCutLoops");function Fs(s){let{cutPrimitives:t,engravePolylines:e}=di(s),{openChains:n}=Us(t);return[...e,...n]}d(Fs,"extractDxfScorePolylines");function Il(s,t){let e=jt(s?.[0]),n=jt(s?.[1]),i=n[1]<e[1]?[n,e]:[e,n];return{id:`bend-${t+1}`,index:t,start:i[0],end:i[1],x:(i[0][0]+i[1][0])/2,yMin:Math.min(i[0][1],i[1][1]),yMax:Math.max(i[0][1],i[1][1])}}d(Il,"normalizeBendLine");function Os(s){return s.map((t,e)=>Il(t,e)).sort((t,e)=>{let n=t.x-e.x;return Math.abs(n)>Ct?n:t.yMin-e.yMin}).map((t,e)=>({...t,id:`bend-${e+1}`,index:e}))}d(Os,"sortBendLines");function Pl(s){let{bendLines:t}=di(s);return Os(t)}d(Pl,"extractOrderedDxfBendLines");function Ll(s,t){s.forEach((e,n)=>{if(Se(t?.[n]?.angleDeg,0)===0)return;if(Math.hypot(e.end[0]-e.start[0],e.end[1]-e.start[1])<=Ct)throw new Error("DXF bend line length is too small for preview bending")})}d(Ll,"validateActiveBendLines");function Bs(s){return String(s||"").trim().toLowerCase()===je.DOWN?je.DOWN:je.UP}d(Bs,"normalizeDxfBendDirection");function Se(s,t=ci){let e=Rt(it(t,ci),As,Ts),n=it(s,e);return Rt(n,As,Ts)}d(Se,"normalizeDxfBendAngleDeg");function Nl(s,t=ai){let e=Rt(it(t,ai),bs,Es),n=it(s,e);return n<=0?e:Rt(n,bs,Es)}d(Nl,"normalizeDxfPreviewThicknessMm");function Dl(s,t){let e=Pl(s),n=Array.isArray(t)?t:[];return e.map((i,r)=>{let o=n[r]&&typeof n[r]=="object"?n[r]:{};return{id:i.id,direction:Bs(o.direction),angleDeg:Se(o.angleDeg,ci)}})}d(Dl,"normalizeDxfBendSettings");function Ul(s){let t=Number.POSITIVE_INFINITY,e=Number.POSITIVE_INFINITY,n=Number.NEGATIVE_INFINITY,i=Number.NEGATIVE_INFINITY;for(let r of s)t=Math.min(t,r[0]),e=Math.min(e,r[1]),n=Math.max(n,r[0]),i=Math.max(i,r[1]);return{minX:t,minY:e,maxX:n,maxY:i}}d(Ul,"loopBounds");function Fl(s,t,e){let n=(s[1]-t[1])*(e[0]-t[0])-(s[0]-t[0])*(e[1]-t[1]);if(Math.abs(n)>Ct)return!1;let i=(s[0]-t[0])*(e[0]-t[0])+(s[1]-t[1])*(e[1]-t[1]);if(i<-Ct)return!1;let r=(e[0]-t[0])**2+(e[1]-t[1])**2;return i<=r+Ct}d(Fl,"pointOnSegment");function zs(s,t){let e=!1;for(let n=0,i=t.length-1;n<t.length;i=n,n+=1){let r=t[n],o=t[i];if(Fl(s,o,r))return!0;if(!(r[1]>s[1]!=o[1]>s[1]))continue;let c=o[0]+(s[1]-o[1])*(r[0]-o[0])/(r[1]-o[1]);s[0]<c&&(e=!e)}return e}d(zs,"pointInLoop");function Ol(s){let t=s.map((n,i)=>({loop:n,index:i,parentIndex:-1,depth:-1,area:Math.abs(hi(n))}));for(let n=0;n<t.length;n+=1){let i=t[n],r=i.loop[0],o=-1,a=Number.POSITIVE_INFINITY;for(let c=0;c<t.length;c+=1){if(c===n)continue;let l=t[c];l.area<=i.area+Ct||l.area>=a||zs(r,l.loop)&&(o=c,a=l.area)}i.parentIndex=o}let e=d(n=>{let i=t[n];return i.depth>=0||(i.depth=i.parentIndex<0?0:e(i.parentIndex)+1),i.depth},"resolveDepth");for(let n=0;n<t.length;n+=1)e(n);return t}d(Ol,"loopContainmentNodes");function Bl(s){let t=Ol(s),e=[];for(let n of t){if(n.depth%2!==0)continue;let i=te(n.loop,{clockwise:!0}),r=Ul(i),o=t.filter(a=>a.parentIndex===n.index&&a.depth%2===1).map(a=>te(a.loop,{clockwise:!1}));e.push({index:e.length,transformIndex:0,leftX:r.minX,rightX:r.maxX,outerLoop:i,holeLoops:o,isLeftExterior:!0,isRightExterior:!0})}if(!e.length)throw new Error("DXF preview could not build flat extrusion geometry");return e}d(Bl,"buildFlatStripDefinitions");function zl(s,t,e,n,i){let r=[(t.start[0]+t.end[0])/2,(t.start[1]+t.end[1])/2];if(e>=0){let a=n.find(c=>c.foldIndex===e);if(a){let[c,l]=a.regions;return i[l]?.region===c?c:l}}let o=s.findIndex(a=>zs(r,a.outerLoop));return o>=0?o:0}d(zl,"regionIndexForGuide");function Vl(s,t,e){for(let n of e.foldLines||[]){if(n.halfWidth<=Ct)continue;let i=Math.abs(pt(n,s)),r=Math.abs(pt(n,t));if(Math.abs(i-n.halfWidth)<=.001&&Math.abs(r-n.halfWidth)<=.001)return!0}return!1}d(Vl,"isFoldBandEdge");function Vs(s,t,e,n,i){let r=s.length/3;s.push(...e,...n,...i),t.push(r,r+1,r+2)}d(Vs,"appendTriangle");function kl(s,t,e,n=!0){let i=t[0]-s[0],r=t[2]-s[2],o=e[0]-s[0],a=e[2]-s[2],c=r*o-i*a;return n&&c<0||!n&&c>0?[s,e,t]:[s,t,e]}d(kl,"orientTriangleY");function Ut(s,t){let[e,n,i]=t,r=s.elements;return[r[0]*e+r[4]*n+r[8]*i+r[12],r[1]*e+r[5]*n+r[9]*i+r[13],r[2]*e+r[6]*n+r[10]*i+r[14]]}d(Ut,"applyMatrixToPoint");function tn(s,t,e,n,i,r,o){let a=kl(Ut(e,n),Ut(e,i),Ut(e,r),o);Vs(s,t,a[0],a[1],a[2])}d(tn,"appendTransformedTriangle");function en(s,t,e,n){return s.push(t,e,n),s.length/3-1}d(en,"appendVertex");function oi(s,t,e,n,i){let r=Ut(e,n),o=Ut(e,i),a=en(s,r[0],r[1],r[2]),c=en(s,o[0],o[1],o[2]);t.push(a,c)}d(oi,"appendTransformedEdgeSegment");function Is(s,t,e,n,i,r,o=()=>!1){for(let a=0;a<n.length;a+=1){let c=n[a],l=n[(a+1)%n.length];o(c,l)||(tn(s,t,e,[c[0],i,c[1]],[l[0],i,l[1]],[l[0],r,l[1]],!0),tn(s,t,e,[c[0],i,c[1]],[l[0],r,l[1]],[c[0],r,c[1]],!0))}}d(Is,"appendLoopSideFaces");function Ps(s,t,e,n,i,r,o=()=>!1){for(let a=0;a<n.length;a+=1){let c=n[a],l=n[(a+1)%n.length];o(c,l)||(oi(s,t,e,[c[0],i,c[1]],[l[0],i,l[1]]),oi(s,t,e,[c[0],r,c[1]],[l[0],r,l[1]]),oi(s,t,e,[c[0],i,c[1]],[c[0],r,c[1]]))}}d(Ps,"appendLoopEdgeSegments");function Gl(s){return(Bs(s?.direction)===je.DOWN?-1:1)*(Se(s?.angleDeg)*Math.PI/180)}d(Gl,"bendAngleRadiansForSetting");function Hl(s){if(!s.length)return{min:[0,0,0],max:[0,0,0]};let t=Number.POSITIVE_INFINITY,e=Number.POSITIVE_INFINITY,n=Number.POSITIVE_INFINITY,i=Number.NEGATIVE_INFINITY,r=Number.NEGATIVE_INFINITY,o=Number.NEGATIVE_INFINITY;for(let a=0;a<s.length;a+=3){let c=s[a],l=s[a+1],u=s[a+2];t=Math.min(t,c),e=Math.min(e,l),n=Math.min(n,u),i=Math.max(i,c),r=Math.max(r,l),o=Math.max(o,u)}return{min:[t,e,n],max:[i,r,o]}}d(Hl,"buildBounds");function Wl(s){let{loops:t,bendLines:e}=Rl(s),n=[...t].sort((a,c)=>Math.abs(hi(c))-Math.abs(hi(a))),i=te(n[0]||[],{clockwise:!0});if(!i.length)throw new Error("DXF preview requires one outer contour");let r=n.slice(1).map(a=>te(a,{clockwise:!1})),o=Os(e);return{loops:n,outerLoop:i,holeLoops:r,bendLines:o}}d(Wl,"buildTriangulatedFlatPattern");function ks(s,t,e=null,n=null){let i=n?.guideElevationSign===-1?-1:1,{loops:r,outerLoop:o,holeLoops:a,bendLines:c}=Wl(s),l=Nl(t,it(s?.defaultThicknessMm,ai)),u=Dl(s,e);Ll(c,u);let h=l/2,f,m,p,_=c.some((w,N)=>Se(u?.[N]?.angleDeg,0)!==0),x=[];if(c.length&&_){let w=[],N=[];c.forEach((S,C)=>{let I=u?.[C];if(Se(I?.angleDeg,0)===0){N.push({bendLine:S,foldIndex:-1});return}let B=ys({bendLine:S,angleRadians:Gl(I),insideRadiusMm:it(n?.bendInsideRadiusMm,0),kFactor:Rt(it(n?.bendKFactor,.5),.05,.95),halfThicknessMm:h});if(!B)throw new Error("DXF bend line length is too small for preview bending");N.push({bendLine:S,foldIndex:w.length}),w.push(B)});let{regions:k,adjacency:G}=_s(o,w);Ms(k,a,w);let{placements:q,parents:Y}=xs(k,w,G);f=k.map((S,C)=>({index:C,transformIndex:C,outerLoop:te(S.outerLoop,{clockwise:!0}),holeLoops:S.holeLoops.map(I=>te(I,{clockwise:!1})),region:S,foldLines:w})),p=q,x=G.map(S=>{let[C,I]=S.regions,P=Y[I]?.region===C,B=P?C:I,st=P?I:C,K=w[S.foldIndex],zt=k[st].sides.find(ie=>ie.foldIndex===S.foldIndex)?.side||1,yt=ve(k[B],K),Pt=ve(k[st],K);return!yt||!Pt?null:Ss({foldLine:K,side:zt,span:{min:Math.max(yt.min,Pt.min),max:Math.min(yt.max,Pt.max)},halfThickness:h,parentMatrix:q[B]})}).filter(Boolean);let V=i*(h+Cs);m=N.flatMap(({bendLine:S,foldIndex:C})=>{let I=zl(k,S,C,G,Y),P=p[I]||new W().identity();return[...Ut(P,[S.start[0],V,S.start[1]]),...Ut(P,[S.end[0],V,S.end[1]])]})}else{f=Bl(r),p=[new W().identity()];let w=i*(h+Cs);m=c.flatMap(N=>[N.start[0],w,N.start[1],N.end[0],w,N.end[1]])}let g=[],M=[],y=[],v=[];for(let w of f){let N=p[w.transformIndex]||p[p.length-1]||new W().identity(),k=w.outerLoop.map(([S,C])=>new et(S,C)),G=w.holeLoops.map(S=>S.map(([C,I])=>new et(C,I))),q=Qt.triangulateShape(k,G),Y=k.concat(...G);for(let S of q){let C=Y[S[0]],I=Y[S[1]],P=Y[S[2]];tn(g,M,N,[C.x,h,C.y],[I.x,h,I.y],[P.x,h,P.y],!0),tn(g,M,N,[C.x,-h,C.y],[I.x,-h,I.y],[P.x,-h,P.y],!1)}let V=w.foldLines?(S,C)=>Vl(S,C,w):()=>!1;Is(g,M,N,w.outerLoop,h,-h,V),Ps(y,v,N,w.outerLoop,h,-h,V);for(let S of w.holeLoops)Is(g,M,N,S,h,-h),Ps(y,v,N,S,h,-h)}for(let w of x){for(let[N,k,G]of w.triangles)Vs(g,M,N,k,G);for(let[N,k]of w.edges){en(y,N[0],N[1],N[2]),en(y,k[0],k[1],k[2]);let G=y.length/3-2;v.push(G,G+1)}}let b=g.length/3,A=new Float32Array(g.length+y.length);A.set(g,0),A.set(y,g.length);let R=new Uint32Array(v.length);for(let w=0;w<v.length;w+=1)R[w]=v[w]+b;return{format_version:"dxf-preview-mesh-v2",has_source_colors:!1,bounds:Hl(A),vertex_count:A.length/3,triangle_count:M.length/3,edge_index_count:R.length,vertices:A,colors:new Float32Array(0),normals:new Float32Array(0),indices:new Uint32Array(M),edge_indices:R,guide_line_segments:new Float32Array(m),parts:[]}}d(ks,"buildDxfPreviewMeshData");function Xl(s){return typeof s=="string"?s:""}d(Xl,"normalizeLayerName");function Gs(s,t,e,n,i,r){s.push(t,r,e,n,r,i)}d(Gs,"pushSegment");function ql(s,t){let e=Math.max(8,t),n=Math.min(1,Math.abs(s)/(Math.PI*2));return Math.max(8,Math.ceil(e*n))}d(ql,"arcSegmentCount");function Hs(s,t,e,n){let[i,r]=t.center||[0,0],o=Number(t.radius);if(!Number.isFinite(o)||o<=0)return;let a=Number(t.startAngleDeg),c=Number(t.sweepAngleDeg);if(!Number.isFinite(a)||!Number.isFinite(c)||c===0)return;let l=a*Math.PI/180,u=c*Math.PI/180,h=ql(u,n),f=null;for(let m=0;m<=h;m+=1){let p=l+u*(m/h),_=[i+o*Math.cos(p),r+o*Math.sin(p)];f&&Gs(s,f[0],f[1],_[0],_[1],e),f=_}}d(Hs,"sampleArc");function Yl(s,t,e,n){Hs(s,{center:t.center,radius:t.radius,startAngleDeg:0,sweepAngleDeg:360},e,n)}d(Yl,"sampleCircle");function Ws(s,t=null){let e=s?.geometry,n=Number(t?.elevation)||0,i=Number(t?.arcSegments)||48,r=new Map,o=d(c=>{let l=Xl(c);return r.has(l)||r.set(l,[]),r.get(l)},"bucket");if(!e||typeof e!="object")return{layers:[]};for(let c of Array.isArray(e.lines)?e.lines:[]){let l=c?.start,u=c?.end;!Array.isArray(l)||!Array.isArray(u)||Gs(o(c.layer),l[0],l[1],u[0],u[1],n)}for(let c of Array.isArray(e.arcs)?e.arcs:[])Hs(o(c?.layer),c,n,i);for(let c of Array.isArray(e.circles)?e.circles:[])Yl(o(c?.layer),c,n,i);let a=[];for(let[c,l]of r)l.length&&a.push({name:c,positions:new Float32Array(l)});return{layers:a}}d(Ws,"buildDxfDrawingLineGroups");function Xs(s){let t=[1/0,1/0,1/0],e=[-1/0,-1/0,-1/0];for(let n of s?.layers||[]){let{positions:i}=n;for(let r=0;r<i.length;r+=3)for(let o=0;o<3;o+=1){let a=i[r+o];a<t[o]&&(t[o]=a),a>e[o]&&(e[o]=a)}}return Number.isFinite(t[0])?{min:t,max:e}:null}d(Xs,"drawingLineBounds");var $l=75e-5,Zl=.05,Jl=.03,fi="#1f2937";function qs(s,t){let e=s.max[0]-s.min[0],n=s.max[2]-s.min[2],i=Math.hypot(e,n);return Math.max(Number(t)||0,i*$l,Zl)}d(qs,"halfWidthForBounds");function Ys(s,t,e,n,i,r,o,a){let c=i-t,l=o-n,u=Math.hypot(c,l);if(!(u>0))return;let h=-l/u*a,f=c/u*a;s.push(t-h,e,n-f,t+h,e,n+f,i+h,r,o+f,t-h,e,n-f,i+h,r,o+f,i-h,r,o-f)}d(Ys,"pushRibbon");function $s(s,t=null){let e=Ws(s,t);if(!e.layers.length)return new Float32Array(0);let n=qs(Xs(e),t?.halfWidth),i=[];for(let r of e.layers){let{positions:o}=r;for(let a=0;a+5<o.length;a+=6)Ys(i,o[a],o[a+1],o[a+2],o[a+3],o[a+4],o[a+5],n)}return Float32Array.from(i)}d($s,"drawingLinesToRibbonPositions");function Zs(s,t,e=null){let n;try{n=Fs(s)}catch{return new Float32Array(0)}if(!n.length)return new Float32Array(0);let i=s?.bounds||{},r=Math.abs(Number(i.width)||0),o=Math.abs(Number(i.height)||0),a=qs({min:[0,0,0],max:[r,0,o]},e?.halfWidth),l=(e?.elevationSign===-1?-1:1)*(Math.abs(Number(t)||0)/2+Jl),u=[];for(let h of n)for(let f=0;f+1<h.length;f+=1){let m=h[f],p=h[f+1];Ys(u,m[0],l,m[1],p[0],l,p[1],a)}return Float32Array.from(u)}d(Zs,"dxfEngraveRibbonPositions");function pi(s,{scale:t=.001}={}){let e=s||new Float32Array(0),n=new Float32Array(e.length);for(let i=0;i+2<e.length;i+=3)n[i]=e[i]*t,n[i+1]=e[i+2]*t,n[i+2]=-e[i+1]*t;return n}d(pi,"dxfSoupToGlbPositions");function Js(s,{scale:t=.001}={}){let e=s?.vertices,n=s?.indices;if(!e?.length||!n?.length)throw new Error("DXF preview produced no triangles");let i=new Float32Array(n.length*3);for(let r=0;r<n.length;r+=1){let o=n[r]*3,a=r*3;i[a]=e[o]*t,i[a+1]=e[o+2]*t,i[a+2]=-e[o+1]*t}return i}d(Js,"dxfPreviewPositions");function nn(s){return s<=.04045?s/12.92:((s+.055)/1.055)**2.4}d(nn,"srgbToLinear");var ee=globalThis.Buffer,Kl=typeof TextEncoder<"u"?new TextEncoder:null;function Ql(s,t=0){let e=Number(s);return Number.isFinite(e)?e:t}d(Ql,"finiteNumber");function be(s){return Math.min(Math.max(Ql(s),0),1)}d(be,"clamp01");function jl(s,t="utf-8"){if(ee?.from)return ee.from(String(s),t);if(t!=="utf-8"&&t!=="utf8"){let e=String(s),n=new Uint8Array(e.length);for(let i=0;i<e.length;i+=1)n[i]=e.charCodeAt(i)&255;return n}return Kl.encode(String(s))}d(jl,"bytesFromString");function sn(s,t=0){if(ee?.alloc)return ee.alloc(s,t);let e=new Uint8Array(s);return t&&e.fill(t),e}d(sn,"allocBytes");function mi(s,t=void 0){if(ee?.concat)return ee.concat(s,t);let e=t??s.reduce((r,o)=>r+o.length,0),n=new Uint8Array(e),i=0;for(let r of s)n.set(r,i),i+=r.length;return n}d(mi,"concatBytes");function at(s){return new Uint8Array(s.buffer,s.byteOffset,s.byteLength)}d(at,"typedArrayBytes");function th(s){return new DataView(s.buffer,s.byteOffset,s.byteLength)}d(th,"viewFor");function Ft(s,t,e){th(s).setUint32(t,e,!0)}d(Ft,"writeUInt32LE");function Ks(s,t=32){let e=(4-s.length%4)%4;return e?mi([s,sn(e,t)]):s}d(Ks,"align4Buffer");function Ee(s,t="model"){return String(s||t).trim().replace(/[\x00-\x1f<>:"/\\|?*]+/g,"-")||t}d(Ee,"sanitizeName");function gi(s){let t=[1/0,1/0,1/0],e=[-1/0,-1/0,-1/0];for(let n=0;n<s.length;n+=3)t[0]=Math.min(t[0],s[n]),t[1]=Math.min(t[1],s[n+1]),t[2]=Math.min(t[2],s[n+2]),e[0]=Math.max(e[0],s[n]),e[1]=Math.max(e[1],s[n+1]),e[2]=Math.max(e[2],s[n+2]);return{min:t.map(n=>Number.isFinite(n)?n:0),max:e.map(n=>Number.isFinite(n)?n:0)}}d(gi,"boundsForPositions");function Qs(s,t="#d4d4d8"){let e=String(s||t).trim(),n=/^#(?:[0-9a-fA-F]{3}){1,2}$/.test(e)?e:t,i=n.length===4?`${n[1]}${n[1]}${n[2]}${n[2]}${n[3]}${n[3]}`:n.slice(1);return[parseInt(i.slice(0,2),16)/255,parseInt(i.slice(2,4),16)/255,parseInt(i.slice(4,6),16)/255]}d(Qs,"hexToRgb01");function js(s,t){let e=Ks(mi(t),0);s.buffers=[{byteLength:e.length}];let n=Ks(jl(JSON.stringify(s)),32),i=20+n.length+8+e.length,r=sn(12);Ft(r,0,1179937895),Ft(r,4,2),Ft(r,8,i);let o=sn(8);Ft(o,0,n.length),Ft(o,4,1313821514);let a=sn(8);return Ft(a,0,e.length),Ft(a,4,5130562),mi([r,o,n,a,e],i)}d(js,"buildGlb");var Ot=5126,eh=5122,nh=5120,tr=5123,ih=5125,It=34962,er=34963,sh=4,rh=65535,Bt=32767,_i=127;function xi(s){return s+3&-4}d(xi,"align4");function ir(s,t){if(s.length>=t)return s;let e=new Uint8Array(t);return e.set(s,0),e}d(ir,"padTo");function nr(s,t,e,n){if(e===t)return ir(s,xi(s.length));let i=new Uint8Array(n*e);for(let r=0;r<n;r+=1)i.set(s.subarray(r*t,(r+1)*t),r*e);return i}d(nr,"strideElements");function oh(s,t){let e=s[t],n=s[t+1],i=s[t+2],r=s[t+3],o=s[t+4],a=s[t+5],c=s[t+6],l=s[t+7],u=s[t+8],h=r-e,f=o-n,m=a-i,p=c-e,_=l-n,x=u-i,g=f*x-m*_,M=m*p-h*x,y=h*_-f*p,v=Math.sqrt(g*g+M*M+y*y);return v>1e-12?[g/v,M/v,y/v]:[0,0,1]}d(oh,"faceNormal");function ah(s,t,{weldDecimals:e=5}={}){let n=Math.floor(s.length/3),i=10**e,r=d(h=>Math.round(h*i)/i,"q"),o=[],a=[],c=new Uint32Array(n),l=new Map,u=t&&t.length===s.length;for(let h=0;h*9<s.length;h+=1){let f=h*9,m=u?null:oh(s,f);for(let p=0;p<3;p+=1){let _=f+p*3,x=s[_],g=s[_+1],M=s[_+2],y=u?t[_]:m[0],v=u?t[_+1]:m[1],b=u?t[_+2]:m[2],A=`${r(x)},${r(g)},${r(M)},${r(y)},${r(v)},${r(b)}`,R=l.get(A);R===void 0&&(R=o.length/3,l.set(A,R),o.push(x,g,M),a.push(y,v,b)),c[h*3+p]=R}}return{positions:new Float32Array(o),normals:new Float32Array(a),indices:c.subarray(0,Math.floor(s.length/3)*3)}}d(ah,"weldMesh");function ch(s,t){let e=s.length/3,n=new Int16Array(s.length),i=[Math.max(t.max[0]-t.min[0],1e-9),Math.max(t.max[1]-t.min[1],1e-9),Math.max(t.max[2]-t.min[2],1e-9)];for(let r=0;r<e;r+=1)for(let o=0;o<3;o+=1){let a=r*3+o,c=(s[a]-t.min[o])/i[o];n[a]=Math.max(-Bt,Math.min(Bt,Math.round(c*Bt)))}return{array:n,scale:i.map(r=>r/Bt),translation:[t.min[0],t.min[1],t.min[2]]}}d(ch,"quantizePositions");function lh(s){let t=new Int8Array(s.length);for(let e=0;e<s.length;e+=1)t[e]=Math.max(-_i,Math.min(_i,Math.round(s[e]*_i)));return t}d(lh,"quantizeNormals");var hh=.42,uh=.03;function Ae(s,t){let e=Number(s?.[t]);return Number.isFinite(e)?be(e):null}d(Ae,"finishChannel");function dh(s,t,e=null,n=null){let i=Qs(s).map(be).map(nn).map(Math.fround),r=Ae(n,"opacity"),o=e==null?r===null?1:r:be(e),a=Ae(n,"roughness"),c=Ae(n,"metalness"),l=Ae(n,"clearcoat"),u=Ae(n,"clearcoatRoughness"),h={name:Ee(t||"material","material"),doubleSided:!0,extras:{cadSourceColor:!0},pbrMetallicRoughness:{baseColorFactor:[...i,o],roughnessFactor:a===null?hh:a,metallicFactor:c===null?uh:c}};return o<1&&(h.alphaMode="BLEND"),l!==null&&l>0&&(h.extensions={KHR_materials_clearcoat:{clearcoatFactor:l,...u===null?{}:{clearcoatRoughnessFactor:u}}}),h}d(dh,"materialFor");var fh=[["translation",3,"VEC3"],["rotation",4,"VEC4"],["scale",3,"VEC3"]];function ph(s,{nodeIndexByKey:t,targetCountByKey:e,accessors:n,pushView:i}){let r=[];for(let o of Array.isArray(s)?s:[]){let a=[],c=[],l=new Map,u=d(h=>{let f=l.get(h);if(f!==void 0)return f;if(!h||!h.length)throw new Error("writeGlb: an animation channel needs a non-empty times array");return n.push({bufferView:i(at(h)),byteOffset:0,componentType:Ot,count:h.length,type:"SCALAR",min:[h[0]],max:[h[h.length-1]]}),f=n.length-1,l.set(h,f),f},"timeAccessorFor");for(let h of o?.channels||[]){let f=t.get(String(h?.node));if(f===void 0)throw new Error(`writeGlb: animation channel targets node ${JSON.stringify(h?.node)}, which no primitive declared`);let m=u(h?.times||o?.times);if(h?.weights){let p=h?.times||o?.times,_=Number(h.targetCount),x=e.get(String(h.node))||0;if(!Number.isInteger(_)||_<1||_!==x)throw new Error(`writeGlb: weights channel on node ${JSON.stringify(h.node)} declares ${h.targetCount} morph targets, but its mesh has ${x}`);if(h.weights.length!==p.length*_)throw new Error(`writeGlb: weights channel on node ${JSON.stringify(h.node)} has ${h.weights.length} scalars for ${p.length} times x ${_} targets`);n.push({bufferView:i(at(h.weights)),byteOffset:0,componentType:Ot,count:h.weights.length,type:"SCALAR"}),a.push({input:m,output:n.length-1,interpolation:"LINEAR"}),c.push({sampler:a.length-1,target:{node:f,path:"weights"}})}for(let[p,_,x]of fh){let g=h?.[p];g&&(n.push({bufferView:i(at(g)),byteOffset:0,componentType:Ot,count:g.length/_,type:x}),a.push({input:m,output:n.length-1,interpolation:"LINEAR"}),c.push({sampler:a.length-1,target:{node:f,path:p}}))}}c.length&&r.push({name:Ee(o?.name||"clip","clip"),samplers:a,channels:c})}return r}d(ph,"buildAnimations");function sr(s,t={}){let{preset:e="export",name:n="model",units:i="mm",weldDecimals:r=5,encoder:o=null,occurrenceIdPrefix:a=null,upAxis:c="y",animations:l=null,nodeTransforms:u=null}=t,h=String(c).trim().toLowerCase();if(h!=="y"&&h!=="z")throw new Error(`writeGlb: upAxis must be "y" (glTF) or "z" (CAD), got ${JSON.stringify(c)}`);let f=String(a||t.sourceKind||Ee(n,"model")),m=e==="render";if(m&&!o)throw new Error("writeGlb: preset 'render' requires meshoptimizer's MeshoptEncoder (await MeshoptEncoder.ready)");if(m&&(l||u))throw new Error("writeGlb: preset 'render' spends every node transform on dequantization, so it carries no animation or node TRS \u2014 use preset 'export' for an animated file");let p=Array.isArray(s?.primitives)&&s.primitives.length?s.primitives:[{positions:s?.positions,normals:s?.normals,color:t.color}],_=[],x=[],g=[],M=[],y=[],v=[],b=new Map,A=0,R=d(S=>{let C=xi(A);C>A&&(_.push(new Uint8Array(C-A)),A=C),_.push(S);let I=A;return A+=S.length,I},"appendBytes"),z=d((S,C)=>{let P={buffer:0,byteOffset:R(S),byteLength:S.length};return C&&(P.target=C),x.push(P),x.length-1},"pushView"),w=d((S,{count:C,stride:I,mode:P,target:B})=>{let st=R(S),K={byteLength:C*I,byteStride:I,extensions:{EXT_meshopt_compression:{buffer:0,byteOffset:st,byteLength:S.length,count:C,byteStride:I,mode:P}}};return B&&(K.target=B),x.push(K),x.length-1},"pushCompressedView");for(let S of p){let C=S?.positions instanceof Float32Array?S.positions:new Float32Array(S?.positions||[]);if(!C.length)continue;let I=Array.isArray(S?.targets)&&S.targets.length?S.targets:null;if(I){if(!S?.indices)throw new Error("writeGlb: morph targets need already-indexed input \u2014 a weld can merge two vertices a target moves apart, and the deltas would then be 1:1 with nothing");if(m)throw new Error("writeGlb: preset 'render' quantizes every attribute and carries no morph targets \u2014 use preset 'export' for a deforming file")}let P=S?.indices?{positions:C,normals:S.normals instanceof Float32Array&&S.normals.length===C.length?S.normals:new Float32Array(C.length),indices:S.indices}:ah(C,S?.normals,{weldDecimals:r}),B=P.positions.length/3,st=gi(P.positions),K=null;if(typeof S?.colorAt=="function"){K=new Uint16Array(B*4);for(let J=0;J<B;J+=1){let Vt=S.colorAt(P.positions[J*3],P.positions[J*3+1],P.positions[J*3+2],P.normals[J*3],P.normals[J*3+1],P.normals[J*3+2]);for(let ct=0;ct<3;ct+=1)K[J*4+ct]=Math.round(nn(be(Number(Vt?.[ct])||0))*65535);K[J*4+3]=65535}}let zt,yt,Pt=null,ie,an,cn=null,yi=null;if(m){let J=ch(P.positions,st),Vt=nr(at(J.array),6,8,B),ct=nr(at(lh(P.normals)),3,4,B);zt=w(o.encodeVertexBuffer(Vt,B,8),{count:B,stride:8,mode:"ATTRIBUTES",target:It}),yt=w(o.encodeVertexBuffer(ct,B,4),{count:B,stride:4,mode:"ATTRIBUTES",target:It}),K&&(Pt=w(o.encodeVertexBuffer(at(K),B,8),{count:B,stride:8,mode:"ATTRIBUTES",target:It})),cn=J.scale,yi=J.translation,ie={bufferView:zt,byteOffset:0,componentType:eh,count:B,type:"VEC3",min:[0,0,0],max:[Bt,Bt,Bt]},an={bufferView:yt,byteOffset:0,componentType:nh,count:B,type:"VEC3",normalized:!0}}else zt=z(at(P.positions),It),yt=z(at(P.normals),It),K&&(Pt=z(at(K),It)),ie={bufferView:zt,byteOffset:0,componentType:Ot,count:B,type:"VEC3",min:st.min,max:st.max},an={bufferView:yt,byteOffset:0,componentType:Ot,count:B,type:"VEC3"};let ln=B<=rh,vt=ln?new Uint16Array(P.indices):new Uint32Array(P.indices),vi=ln?2:4,lr=m?w(o.encodeIndexBuffer(new Uint8Array(vt.buffer,vt.byteOffset,vt.byteLength),vt.length,vi),{count:vt.length,stride:vi,mode:"TRIANGLES",target:er}):z(ir(at(vt),xi(vt.byteLength)),er);g.push(ie);let hr=g.length-1;g.push(an);let ur=g.length-1,hn=null;K&&(g.push({bufferView:Pt,byteOffset:0,componentType:tr,count:B,type:"VEC4",normalized:!0}),hn=g.length-1),g.push({bufferView:lr,byteOffset:0,componentType:ln?tr:ih,count:vt.length,type:"SCALAR"});let dr=g.length-1,Mt=I?.map((J,Vt)=>{let ct=J?.positionDeltas;if(!(ct instanceof Float32Array)||ct.length!==P.positions.length)throw new Error(`writeGlb: morph target ${Vt} has ${ct?.length??"no"} position deltas for ${P.positions.length/3} vertices`);let Mi=gi(ct);g.push({bufferView:z(at(ct),It),byteOffset:0,componentType:Ot,count:B,type:"VEC3",min:Mi.min,max:Mi.max});let Si={POSITION:g.length-1},re=J?.normalDeltas;if(re){if(!(re instanceof Float32Array)||re.length!==P.positions.length)throw new Error(`writeGlb: morph target ${Vt} has ${re.length} normal deltas for ${P.positions.length/3} vertices`);g.push({bufferView:z(at(re),It),byteOffset:0,componentType:Ot,count:B,type:"VEC3"}),Si.NORMAL=g.length-1}return Si})||null;v.push(dh(K?"#ffffff":S?.color,S?.materialName||S?.name,S?.opacity??null,S?.material??null));let fr={attributes:{POSITION:hr,NORMAL:ur,...hn===null?{}:{COLOR_0:hn}},indices:dr,material:v.length-1,mode:sh,...Mt?{targets:Mt}:{}},se=S?.node===void 0||S?.node===null?`\0primitive:${b.size}`:String(S.node),Lt=b.get(se);if(!Lt)Lt={key:se,input:S,primitives:[],quantization:null,targetCount:Mt?Mt.length:0},b.set(se,Lt);else{if(Lt.targetCount!==(Mt?Mt.length:0))throw new Error(`writeGlb: node ${JSON.stringify(se)} mixes primitives with ${Lt.targetCount} and ${Mt?Mt.length:0} morph targets, and glTF weights are per MESH`);if(m)throw new Error(`writeGlb: preset 'render' cannot put two primitives on node ${JSON.stringify(se)}: each quantized primitive owns its node's transform`)}Lt.primitives.push(fr),cn&&(Lt.quantization={scale:cn,translation:yi})}let N=new Map,k=new Map;for(let S of b.values()){k.set(S.key,S.targetCount),M.push({primitives:S.primitives,...S.targetCount?{weights:new Array(S.targetCount).fill(0)}:{}});let C={mesh:M.length-1,name:Ee(S.input?.name||n,n),extras:{cadOccurrenceId:String(S.input?.occurrenceId||`${f}:${y.length}`),cadSourceKind:t.sourceKind||"mesh",cadUnits:i,cadUpAxis:h}};S.quantization&&(C.scale=S.quantization.scale,C.translation=S.quantization.translation);let I=u instanceof Map?u.get(S.key):null;I&&(I.translation&&(C.translation=[...I.translation]),I.rotation&&(C.rotation=[...I.rotation]),I.scale&&(C.scale=[...I.scale])),N.set(S.key,y.length),y.push(C)}let G=ph(l,{nodeIndexByKey:N,targetCountByKey:k,accessors:g,pushView:z}),q=m?["KHR_mesh_quantization","EXT_meshopt_compression"]:[],Y=[...q];v.some(S=>S.extensions?.KHR_materials_clearcoat)&&Y.push("KHR_materials_clearcoat");let V={asset:{version:"2.0",generator:"cadgen-js writeGlb"},scene:0,scenes:[{nodes:y.map((S,C)=>C)}],nodes:y,meshes:M,materials:v,bufferViews:x,accessors:g,...G.length?{animations:G}:{}};return Y.length&&(V.extensionsUsed=Y),q.length&&(V.extensionsRequired=q),js(V,_)}d(sr,"writeGlb");function mh(s){let t={};for(let e=0;e<s.length;e+=1){let n=s[e];if(!n.startsWith("--"))continue;let i=s[e+1];i===void 0||i.startsWith("--")?t[n.slice(2)]="true":(t[n.slice(2)]=i,e+=1)}return t}d(mh,"parseArgs");function on(s){process.stdout.write(`${JSON.stringify({ok:!1,error:String(s)})}
`),process.exit(1)}d(on,"fail");var ar=mh(process.argv.slice(2)),ne=String(ar.out||"");(!ne||!or.isAbsolute(ne))&&on("--out must be an absolute .glb path");var Te=String(ar.name||"drawing"),cr="";try{cr=rn.readFileSync(0,"utf8")}catch(s){on(`could not read DXF from stdin: ${s.message}`)}try{let s=Ci(cr,{fileRef:Te}),t=new Float32Array(0),e="prism",n=null;try{let l=ks(s,1,null);t=Js(l)}catch(l){n=l}let i=t.length?pi(Zs(s,1,{elevationSign:-1})):new Float32Array(0);t.length||(t=pi($s(s)),e="lines");let r=(t.length+i.length)/9;if(!r){if(n)throw n;on("the DXF has no renderable geometry (no cut contours and no line work)")}let o=e==="lines"?[{positions:t,name:Te,color:fi}]:[{positions:t,name:Te}];i.length&&o.push({positions:i,name:`${Te}_engrave`,color:fi});let a=sr({primitives:o,name:Te,units:"mm"},{preset:"export",sourceKind:"dxf",occurrenceIdPrefix:"dxf",upAxis:"z"});rn.mkdirSync(or.dirname(ne),{recursive:!0});let c=`${ne}.${process.pid}.tmp`;rn.writeFileSync(c,a),rn.renameSync(c,ne),process.stdout.write(`${JSON.stringify({ok:!0,path:ne,triangleCount:r,renderMode:e,bytes:a.length})}
`)}catch(s){on(s&&s.stack?s.stack.split(`
`)[0]:s)}
/*! Bundled license information:

three/build/three.core.js:
three/build/three.module.js:
  (**
   * @license
   * Copyright 2010-2026 Three.js Authors
   * SPDX-License-Identifier: MIT
   *)
*/
