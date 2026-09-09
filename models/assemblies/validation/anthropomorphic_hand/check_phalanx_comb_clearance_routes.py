"""Exact static-route packet / real guide body clearance across all accepted poses."""
import sys,json,gzip,hashlib,time,itertools,io
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).parent
sys.path.insert(0,str(ROOT/'src/anthropomorphic_hand'))
from cadgen import read_step,build123d as bd
from lib.layout import assembled_transforms as transforms
from lib.assembly import matrix_location
from lib.finger_routing import transform_path
from lib.transport_guide import path_wire
from check_guide_mount_mutual import leaves
from OCP.BRepClass3d import BRepClass3d_SolidClassifier
from OCP.TopAbs import TopAbs_IN,TopAbs_ON
from OCP.gp import gp_Pnt


class ExactBodyDistance:
 def __init__(self,part):
  self.part=part;self.faces=list(part.faces());boxes=[f.bounding_box() for f in self.faces]
  self.lo=np.array([tuple(b.min) for b in boxes]);self.hi=np.array([tuple(b.max) for b in boxes])
  self.classifiers=[BRepClass3d_SolidClassifier(s.wrapped) for s in part.solids()]
 def distance(self,wire,radius):
  p=wire.position_at(0)
  for c in self.classifiers:
   c.Perform(gp_Pnt(*p),1e-7)
   if c.State() in(TopAbs_IN,TopAbs_ON):return 0.
  b=wire.bounding_box();lo=np.array(tuple(b.min));hi=np.array(tuple(b.max));gap=np.maximum(0,np.maximum(self.lo-hi,lo-self.hi));indices=np.where((gap*gap).sum(axis=1)<(radius+.002)**2)[0]
  d=radius+.002
  for i in indices:
   d=min(d,wire.distance_to(self.faces[i])-1e-6)
   if d<radius-1e-7:break
  return d

def frame(name):
 if name.startswith('thumb_cmc_child_'):return 'thumb_cmc_flexion'
 if name.startswith(('index_','middle_','ring_','little_mcp_')):return name.split('_')[0]+'_mcp_abduction'
 if name.startswith('little_cup_child'):return 'palm_cup'
 if name.startswith('little_cup_fixed'):return 'wrist_flexion'
 if name.startswith('wrist_abduction'):return 'forearm'
 if name.startswith('wrist_flexion'):return 'wrist_abduction'
 if name.startswith('palm_cup'):return 'wrist_flexion'
 if name.startswith('thumb_metacarpal') or name.startswith('thumb_mcp_yaw_drive'):return 'thumb_cmc_flexion'
 if name.startswith('thumb_mcp_ip_outlet') or name.startswith('thumb_ip_drive_guide'):return 'thumb_mcp_flexion'
 if name.startswith('thumb_mcp_'):return 'thumb_mcp_abduction'
 if name.startswith(('thumb_cmc_negative_yaw_outlet','thumb_cmc_positive_yaw_outlet')):return 'thumb_cmc_abduction'
 if name.startswith('thumb_'):return 'wrist_flexion'
 raise ValueError(name)

def corners(p):
 b=p.bounding_box(optimal=False)
 return np.array([[x,y,z,1] for x in (b.min.X,b.max.X) for y in(b.min.Y,b.max.Y) for z in(b.min.Z,b.max.Z)])

def near_segments(path,lower,upper,radius):
 out=[]
 def visit(seg,depth=0):
  if seg['kind']=='bezier':
   cp=np.asarray(seg['points'],float);lo=cp.min(axis=0);hi=cp.max(axis=0)
   gap=np.maximum(0,np.maximum(lower-hi,lo-upper))
   if np.linalg.norm(gap)>radius+.002:return
   if max(hi-lo)>2. and depth<14:
    levels=[cp]
    while len(levels[-1])>1:levels.append((levels[-1][:-1]+levels[-1][1:])/2)
    left=np.array([a[0] for a in levels]);right=np.array([a[-1] for a in levels[::-1]])
    visit({'kind':'bezier','points':left.tolist()},depth+1);visit({'kind':'bezier','points':right.tolist()},depth+1);return
  else:
   bb=path_wire([seg]).bounding_box();lo=np.array(tuple(bb.min));hi=np.array(tuple(bb.max))
   if np.linalg.norm(np.maximum(0,np.maximum(lower-hi,lo-upper)))>radius+.002:return
  out.append(seg)
 for seg in path:visit(seg)
 return out

if __name__=='__main__':
 name=sys.argv[1];files=[ROOT/'STEP/anthropomorphic_hand'/f for f in sys.argv[2:] if not f.startswith('--')]
 parts=[p for f in files for p in leaves(read_step(f))];mapping={r['name']:r['frame'] for r in json.loads((HERE/'phalanx_comb_clearance_frames.json').read_text())};frames=[mapping[p.label] for p in parts];bounds=np.array([corners(p) for p in parts]);manifest=json.loads((HERE/'static_route_packet_manifest.json').read_text())
 digest=hashlib.sha256(b''.join(f.read_bytes() for f in files)).hexdigest();cachefile=HERE/(name+'_route_distance_cache.json')
 body_hashes=[]
 for p in parts:
  stream=io.BytesIO();bd.export_brep(p,stream);body_hashes.append(hashlib.sha256(stream.getvalue()).hexdigest())
 saved=json.loads(cachefile.read_text()) if cachefile.exists() else {}
 if saved.get('schema')==2:cache=saved.get('values',{})
 elif saved.get('step_sha256')==digest:cache={body_hashes[int(k.split(':',1)[0])]+':'+k.split(':',1)[1]:v for k,v in saved.get('values',{}).items()}
 else:cache={}
 rows=[];distancers={}
 entries=manifest['rows'][:1] if '--neutral' in sys.argv else manifest['rows']
 for entry in entries:
  packet=json.load(gzip.open(entry['file'],'rt'));assert packet['pose']==entry['pose'];fk=transforms(entry['pose']);moved=np.array([bounds[i]@fk[fr].T for i,fr in enumerate(frames)]);lo=moved[:,:,:3].min(axis=1);hi=moved[:,:,:3].max(axis=1);inverses={fr:np.linalg.inv(fk[fr]) for fr in set(frames)}
  row={'label':entry['label'],'pose':entry['pose'],'packet_source_sha256':packet['source_sha256'],'collisions':[],'exact_distances':0}
  for route in packet['routes']:
   for group in route['groups']:
    wire=path_wire(group['path']);bb=wire.bounding_box();wl=np.array(tuple(bb.min));wh=np.array(tuple(bb.max));rad=.45 if group.get('guide') in ('snug_reaction_liner','fixed_curved_guide','compliant_wrist_guide','open_saddle') else .30
    gap=np.maximum(0,np.maximum(lo-wh,wl-hi));candidates=np.where((gap*gap).sum(axis=1)<(rad+.01)**2)[0]
    for i in candidates:
     path=transform_path(group['path'],inverses[frames[i]])
     def rounder(x):
      if isinstance(x,dict):return {k:rounder(v) for k,v in x.items()}
      if isinstance(x,list):return [rounder(v) for v in x]
      return round(x,7) if isinstance(x,(float,int)) else x
     key=body_hashes[i]+':'+json.dumps(rounder(path),sort_keys=True)
     if key not in cache:
      pieces=near_segments(path,bounds[i,:,:3].min(axis=0),bounds[i,:,:3].max(axis=0),rad)
      d=rad+.002
      for segment in pieces:
       print('DISTANCE',entry['label'],parts[i].label,group['label'],flush=True)
       if i not in distancers:distancers[i]=ExactBodyDistance(parts[i])
       d=min(d,distancers[i].distance(path_wire([segment]),rad))
       if d<rad-1e-7:break
      cache[key]=d
     d=cache[key];row['exact_distances']+=1
     if d<rad-1e-7:row['collisions'].append({'body':parts[i].label,'route':route['name'],'group':group['label'],'clearance_mm':d-rad})
  rows.append(row);result={'pass':not any(r['collisions'] for r in rows),'step_sha256':digest,'source_sha256':manifest['source_sha256'],'bodies':len(parts),'pose_count':len(rows),'rows':rows}
  (HERE/(name+'_route_report.json')).write_text(json.dumps(result,indent=2)+'\n');cachefile.write_text(json.dumps({'schema':2,'step_sha256':digest,'body_brep_sha256':dict(zip((p.label for p in parts),body_hashes)),'values':cache})+'\n')
  print(entry['label'],'checks',row['exact_distances'],'collisions',len(row['collisions']),flush=True)
 if not result['pass']:raise SystemExit(1)
