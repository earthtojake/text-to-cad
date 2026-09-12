"""Exact curve/solid and skeleton overlap checks for physical reaction combs."""
import sys,json,hashlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'src/anthropomorphic_hand'))
import numpy as np
from cadgen import build123d as bd
from lib.guide_mounts import make_phalanx_comb
from lib.layout import FINGERS,JOINT_BY_NAME,transforms,finger_fan_matrix
from lib.assembly import matrix_location
import check_middle_hardware_paths as h

def prototypes(name):
 f=next(f for f in FINGERS if f.name==name);out=[]
 if '--yaw-outlets' in sys.argv:
  from lib.yaw_guide_mounts import make_yaw_reaction_mounts
  for part in make_yaw_reaction_mounts(f.widths[0],name+'_mcp'):
   out.append((part.label,name+'_mcp_abduction',bd.Pos(f.x,f.base_y,0)*part))
  return out
 if '--fixed-outlets' in sys.argv:
  from lib.fixed_guide_mounts import make_fixed_outlet_pair
  for i,radius in enumerate((4.5,3.5)):
   frame=name+('_mcp_flexion' if i==0 else '_pip')
   for part in make_fixed_outlet_pair(f.lengths[i],f.widths[i],radius,name+('_pip_drive_guide' if i==0 else '_dip_drive_guide')):
    out.append((part.label,frame,bd.Pos(f.x,f.base_y+sum(f.lengths[:i]),0)*part))
  return out
 if '--from-step' in sys.argv:
  from cadgen import read_step
  source=Path(__file__).resolve().parents[2]/('STEP/anthropomorphic_hand/'+name+'_guide_mounts.step')
  raw=read_step(source)
  for part in raw.children:
   frame=name+('_pip' if '_pip_outlet_' in part.label else '_mcp_flexion')
   out.append((part.label,frame,matrix_location(np.linalg.inv(finger_fan_matrix(f)))*part))
  return out
 groups=[('mcp_outlet',0,12.25,[-4.2,-3.,3.,4.2]),('pip_inlet',0,f.lengths[0]-12.25,[-4.2,4.2]),('pip_outlet',1,10. if name=='little' else 12.25,[-4.2,4.2])]
 for role,i,station,lanes in groups:
  frame=name+('_mcp_flexion' if i==0 else '_pip')
  for p in make_phalanx_comb(f.lengths[i],f.widths[i],station,lanes,name+'_'+role+'_comb'):
   out.append((p.label,frame,bd.Pos(f.x,f.base_y+sum(f.lengths[:i]),0)*p))
 return out

def common_volume(a,b):
 from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
 from OCP.TopTools import TopTools_ListOfShape
 args=TopTools_ListOfShape();args.Append(a.wrapped)
 tools=TopTools_ListOfShape();tools.Append(b.wrapped)
 op=BRepAlgoAPI_Common();op.SetArguments(args);op.SetTools(tools)
 op.SetFuzzyValue(1e-6);op.Build()
 if not op.IsDone():raise RuntimeError('OCCT common did not finish')
 result=bd.Part(op.Shape())
 return sum(s.volume for s in result.solids())

def cached_routes(finger_name,pose):
 from lib.finger_routing import finger_routes
 root=Path(__file__).resolve().parents[2]/'src/anthropomorphic_hand/lib'
 sources=['finger_routing.py','bowden_mcp.py','yaw_transport.py','pip_transport.py','layout.py']
 digest=hashlib.sha256(b''.join((root/n).read_bytes() for n in sources)).hexdigest()
 cachefile=Path(__file__).with_name(finger_name+'_mount_audit_route_packets.json')
 data=json.loads(cachefile.read_text()) if cachefile.exists() else {}
 if data.get('source_sha256')!=digest:data={'source_sha256':digest,'packets':{}}
 key=json.dumps(pose,sort_keys=True)
 if key not in data['packets']:
  data['packets'][key]=finger_routes(finger_name,pose)
  cachefile.write_text(json.dumps(data,indent=2)+'\n')
 return data['packets'][key]

if __name__=='__main__':
 name=sys.argv[1] if len(sys.argv)>1 else 'middle';parts=prototypes(name)
 h.finger_routes=cached_routes
 fixed=h.hardware(finger_name=name)
 poses=[('neutral',{})]
 if '--all' in sys.argv:
  for role in ['pip','dip','mcp_flexion','mcp_abduction']:
   joint=name+'_'+role;lo,hi=JOINT_BY_NAME[joint].limits
   poses.extend((joint+str(q),{joint:float(q)}) for q in sorted(set([lo,hi,0.]+list(np.arange(lo,hi,10.)))))
  poses.append(('fist',{name+'_mcp_flexion':90,name+'_pip':110,name+'_dip':80}))
 report={'finger':name,'scope':'body_only' if '--body-only' in sys.argv else 'routes_and_bodies','rows':[]}
 cachepath=Path(__file__).with_name(name+'_mount_body_distance_cache.json')
 modelroot=Path(__file__).resolve().parents[2]
 fingerprint=hashlib.sha256(b''.join((modelroot/'src/anthropomorphic_hand/lib'/n).read_bytes() for n in ['guide_mounts.py','fixed_guide_mounts.py','yaw_guide_mounts.py','palm_guide_mounts.py','phalanx.py','pulley.py','universal_carrier.py','layout.py'])+((modelroot/('STEP/anthropomorphic_hand/'+name+'_guide_mounts.step')).read_bytes() if '--from-step' in sys.argv else b'')).hexdigest()
 saved=json.loads(cachepath.read_text()) if cachepath.exists() else {}
 cache=saved.get('values',{}) if saved.get('source_sha256')==fingerprint else {}
 for label,pose in poses:
  print('Checking',name,label,flush=True)
  row={'pose':pose,'collisions':[]} if '--body-only' in sys.argv else h.check(pose,parts,finger_name=name)
  print('Route findings',row['collisions'],flush=True);row['label']=label;row['body_interferences']=[]
  fk=transforms(pose)
  moved=[(n,fr,matrix_location(fk[fr])*s) for n,fr,s in parts]
  frameb=[(n,fr,matrix_location(fk[fr])*s) for n,fr,s in fixed]
  mountbounds={n:s.bounding_box(optimal=False) for n,fr,s in moved}
  framebounds={n:s.bounding_box(optimal=False) for n,fr,s in frameb}
  for n,fr,s in moved:
   for nn,ff,ss in frameb:
    if h.bbox_gap(mountbounds[n],framebounds[nn])>.005:continue
    key=json.dumps([n,nn,np.round((np.linalg.inv(fk[fr])@fk[ff]).ravel(),7).tolist()])
    if key in cache:volume=cache[key]
    else:
     print('Body common',n,nn,flush=True)
     volume=common_volume(s,ss)
     cache[key]=volume
     cachepath.write_text(json.dumps({'source_sha256':fingerprint,'values':cache},indent=2)+'\n')
    if volume>1e-7:row['body_interferences'].append({'mount':n,'other':nn,'volume':volume})
  report['rows'].append(row);report['pass']=all(not r['collisions'] and not r['body_interferences'] for r in report['rows'])
  Path(__file__).with_name(name+('_fixed_outlet' if '--fixed-outlets' in sys.argv else '_yaw_outlet' if '--yaw-outlets' in sys.argv else '')+('_guide_comb_body_report.json' if '--body-only' in sys.argv else '_guide_comb_report.json')).write_text(json.dumps(report,indent=2)+'\n')
  print(label,'collisions',len(row['collisions']),'body_interferences',len(row['body_interferences']),flush=True)
 if not report['pass']:raise SystemExit(1)
