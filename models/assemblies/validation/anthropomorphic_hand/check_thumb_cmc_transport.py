"""Independent continuous curve bounds and OCCT hardware audit for CMC liners."""
import sys,json,itertools,time
from pathlib import Path
sys.path.insert(0,'models/assemblies/src/anthropomorphic_hand')
import numpy as np
from scipy.spatial import cKDTree
from scipy.integrate import quad
from lib.path_analysis import path_length,path_min_radius,sample_path,cubic_polynomials,real_unit_roots
from lib.thumb_yaw_transport import thumb_yaw_reaction_span

def path(cs):return [{'kind':'bezier','points':p} for p in cs]

def adaptive_length(cs):
 return sum(quad(lambda t:float(np.linalg.norm(3*((1-t)**2*(c[1]-c[0])+2*(1-t)*t*(c[2]-c[1])+t*t*(c[3]-c[2])))),0,1,epsabs=2e-12,epsrel=2e-13)[0] for c in np.asarray(cs))

def minimum_speed(cs):
 answer=float('inf')
 for points in cs:
  polynomials=cubic_polynomials(points);speed2=sum(p.deriv()**2 for p in polynomials);ts=[0.,1.]+real_unit_roots(speed2.deriv())
  answer=min(answer,min(max(0.,float(speed2(t)))**.5 for t in ts))
 return answer

def self_clearance(path):
 p=sample_path(path,.02);s=np.r_[0.,np.cumsum(np.linalg.norm(np.diff(p,axis=0),axis=1))]
 pairs=cKDTree(p).query_pairs(.925,output_type='ndarray')
 nonlocal_pairs=pairs[abs(s[pairs[:,1]]-s[pairs[:,0]])>2.] if len(pairs) else pairs
 # Local spans have R>=3.5 and no tangent jump; their normal tube radius.45
 # is below the local curvature radius. This check searches all remote spans.
 return {'nonlocal_close_pairs':int(len(nonlocal_pairs)),'certified_centerline_distance_lower_bound_mm':.905 if not len(nonlocal_pairs) else None,'clear':not len(nonlocal_pairs)}

def numeric(rows,flex,yaw):
 paths=[path(r['curves']) for r in rows];names=[str(r['lane']) for r in rows];radii=[.45]*len(rows)
 for s in (-1,1):
  own=thumb_yaw_reaction_span(yaw,s);end=np.asarray(own[-1]['points'][-1]);q=np.deg2rad(yaw);tip=end+3*np.array([-np.sin(q),np.cos(q),0]);own=own+[{'kind':'line','start':end.tolist(),'end':tip.tolist()}];paths.append(own);names.append('own_flex_'+str(s));radii.append(.45)
 for sign in(-1,1):
  z=-11. if sign>0 else -13.5;paths.append([{'kind':'line','start':[-sign*7.,-3.,z],'end':[-sign*7.,0.,z]}]);names.append('own_yaw_'+str(sign));radii.append(.3)
 clouds=[sample_path(p,.02) for p in paths]
 gaps=[]
 for i,j in itertools.combinations(range(len(paths)),2):
  gap=float(cKDTree(clouds[i]).query(clouds[j],workers=1)[0].min()-.02-radii[i]-radii[j])
  gaps.append({'a':names[i],'b':names[j],'certified_gap_mm':gap})
 return {'rows':[{'lane':r['lane'],'length_mm':adaptive_length(r['curves']),'length_error_mm':adaptive_length(r['curves'])-r['length'],'minimum_radius_mm':path_min_radius(p),'minimum_parameter_speed_mm':minimum_speed(r['curves']),'self_clearance':self_clearance(p)} for r,p in zip(rows,paths)],'mutual_gaps':gaps,'clear':all(g['certified_gap_mm']>=0 for g in gaps) and all(path_min_radius(p)>=3.5 for p in paths) and all(minimum_speed(r['curves'])>1e-5 and abs(adaptive_length(r['curves'])-r['length'])<1e-8 for r in rows) and all(self_clearance(p)['clear'] for p in paths)}

def actual_hardware():
 from cadgen import build123d as bd
 from lib.universal_carrier import make_universal_carrier
 from lib.thumb_metacarpal import make_thumb_metacarpal
 from lib.pulley import make_pulley
 out=[('carrier','yaw',make_universal_carrier(phalanx_width=19.,yaw_plane=9.5)),('metacarpal','child',make_thumb_metacarpal())]
 for z in(-11.,-13.5):out.append(('yaw_pulley_'+str(z),'fixed',bd.Pos(0,0,z)*make_pulley(7)))
 for x in(-.9,.9):out.append(('flex_pulley_'+str(x),'yaw',bd.Pos(x,0,0)*bd.Rot(0,90,0)*make_pulley(7)))
 out.append(('flex_shaft','yaw',bd.Cylinder(1,22,rotation=(0,90,0))))
 return out

def hardware_check(rows,flex,yaw,hw):
 from cadgen import build123d as bd
 from lib.transport_guide import path_wire
 solids=[(name,bd.Rot(0,0,yaw)*(bd.Rot(flex,0,0)*s if frame=='child' else s) if frame!='fixed' else s) for name,frame,s in hw]
 results=[]
 for row in rows:
  w=path_wire(path(row['curves']))
  for name,s in solids:
   d=w.distance_to(s)-1e-6
   results.append({'lane':row['lane'],'body':name,'centerline_distance_mm':d,'gap_mm':d-.45})
 return results

if __name__=='__main__':
 src=Path(sys.argv[1] if len(sys.argv)>1 else 'models/assemblies/validation/anthropomorphic_hand/thumb_cmc_threecurve_probe.json')
 data=json.loads(src.read_text());out=[];hw=actual_hardware() if '--hardware' in sys.argv else None
 for pose in data:
  p={'scope':'actual_hardware_and_continuous_path' if hw else 'continuous_path_only','flex':pose['flex'],'yaw':pose['yaw'],**numeric(pose['rows'],pose['flex'],pose['yaw'])}
  if hw:p['hardware']=hardware_check(pose['rows'],pose['flex'],pose['yaw'],hw);p['clear'] &= all(r['gap_mm']>=0 for r in p['hardware'])
  print('AUDIT',p['flex'],p['yaw'],p['clear'],'minR',min(r['minimum_radius_mm'] for r in p['rows']),'gap',min(r['certified_gap_mm'] for r in p['mutual_gaps']),flush=True)
  if hw:print([r for r in p['hardware'] if r['gap_mm']<0],flush=True)
  out.append(p);src.with_name(src.stem+('_audit.json' if hw else '_numeric_audit.json')).write_text(json.dumps(out,indent=2))
