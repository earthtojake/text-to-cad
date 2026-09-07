"""Remaining thumb liner datums, on their existing rigid anatomical frames."""
import numpy as np
from cadgen import build123d as bd
from lib.guide_mounts import make_phalanx_comb,_finish,_sweep
from lib.fixed_guide_mounts import make_fixed_outlet_pair
from lib.yaw_guide_mounts import make_yaw_reaction_mounts
from lib.thumb_cmc_mounts import _comb,_host_clamp,_meta_host,_parts_finish
from lib.layout import THUMB_CMC
from lib.finish import finish


def make_thumb_meta_ip_comb():
 label='thumb_metacarpal_ip_inlet_comb';host=_meta_host();y=23.75
 lower,upper,screws,ears,cutters=_comb([(-4.2,y,0),(4.2,y,0)],(0,1,0),label)
 extras=[]
 for side in (-1,1):
  section=host & (bd.Pos(side*7.4,y,-17)*bd.Box(4,.04,12))
  bb=section.bounding_box();x=(bb.min.X+bb.max.X)/2;z=(bb.min.Z+bb.max.Z)/2
  hl,hu,hb,foot=_host_clamp(host,x,y,z,side,label+f'_{side:+d}')
  hu.label=label+f'_rail_{side:+d}_cap';extras.extend([hu,hb])
  c=next(e for e in ears if np.sign(e[0])==side)
  arm=_sweep([(c[0]+side*.34,y,-.36),(side*11.8,y,-5),(side*11.8,y,z-2),foot],.25)
  lower=lower.fuse(arm-host,hl)
 for cutter in [*cutters,upper,*extras,*screws]:lower=lower-cutter
 return _split(lower,label+'_structural_jaw')+[_finish(upper,label+'_scalloped_cap')]+extras+screws


def thumb_downstream_mounts():
 """Eight guide mouths; tuples are already assembled, with rigid frame names."""
 base=bd.Pos(*THUMB_CMC)*bd.Rot(0,0,45);out=[]
 groups=[(make_thumb_meta_ip_comb,0,'thumb_cmc_flexion'),
  (lambda:make_yaw_reaction_mounts(16,'thumb_mcp'),36,'thumb_mcp_abduction'),
  (lambda:make_phalanx_comb(27,16,12.25,[-4.2,4.2],'thumb_mcp_ip_outlet_comb'),36,'thumb_mcp_flexion'),
  (lambda:make_fixed_outlet_pair(27,16,3.5,'thumb_ip_drive_guide'),36,'thumb_mcp_flexion')]
 for factory,y,frame in groups:
  print('THUMB_MOUNT_FACTORY',frame,y,flush=True)
  for p in factory():
   if 'screw' in p.label:finish(p,'steel',p.label)
   out.append((base*bd.Pos(0,y,0)*p,frame,'thumb','fastener' if 'screw' in p.label else 'guide_mount'))
 return out


def _split(shape,label):
 return [_finish(s,label+('_'+str(i+1) if len(shape.solids())>1 else '')) for i,s in enumerate(shape.solids())]


def _attached(host,lower,cap,screws,root,query,label,side=1,cutters=(),controls=None,anchor=None,host_width=3.8):
 q=host.closest_points(query)[0] if anchor is None else anchor;x,y,z=tuple(q)
 hl,hu,hb,foot=_host_clamp(host,x,y,z,side,label,width=host_width,height=4.0)
 # A bowed rib outside the liner's mouth joins an exactly machined split seat.
 root=np.asarray(root,float);end=np.asarray(foot,float)
 control=end-.25*(end-root)+np.array([side*.75,0,0])
 arm=_sweep([root,*(controls if controls is not None else [(root[0]+side*2,root[1],root[2]-2),control]),end],.25)
 body=lower.fuse(arm,hl)-host
 for cutter in cutters:body=body-cutter
 cap=cap-host-body;hu=hu-body
 # Fasteners retain continuous shafts; machine tiny strut contacts only.
 for screw in [*screws,hb]:body=body-screw
 return _split(body,label+'_structural')+_split(cap,label+'_liner_cap')+_split(hu,label+'_host_cap')+[hb,*screws]


def _drive_outlet(host,point,sign,query,label):
 from lib.yaw_guide_mounts import _mouth
 lower,cap,screw=_mouth(1,label)
 place=bd.Pos(*point)*bd.Rot(0,-sign*90,0)*bd.Pos(-.9,3,-5.5)
 lower,cap,screw=place*lower,place*cap,place*screw
 root=(point[0]-sign*.84,point[1]-.275,point[2]-.28)
 return _attached(host,lower,cap,[screw],root,query,label,side=-sign,anchor=_near_anchor(host,query))


def _near_anchor(host,query):
 section=host & (bd.Pos(*query)*bd.Box(8,8,8))
 return (section if section is not None and len(section.solids()) else host).closest_points(query)[0]


def thumb_base_mounts():
 """Sixteen remaining mouth datums, before/at CMC and MCP yaw drives."""
 from lib.palm_frame import make_palm_frame_bodies
 from lib.guide_mounts import guide_end_registry
 from lib.assembly import matrix_location
 base=bd.Pos(*THUMB_CMC)*bd.Rot(0,0,45)
 palm=next(p for p in make_palm_frame_bodies() if p.label=='palm_metacarpal_truss')
 host=base.inverse()*palm;out=[]
 def add(parts,frame):
  for p in parts:
   if 'screw' in p.label:finish(p,'steel',p.label)
   out.append((base*p,frame,'thumb','fastener' if 'screw' in p.label else 'guide_mount'))
 # The CMC carrier owns the two yaw-reaction outlets.
 add(make_yaw_reaction_mounts(19,'thumb_cmc',7.,9.5),'thumb_cmc_abduction')
 # Two CMC and two MCP yaw drive entries use open jaws facing away from drums.
 for sign in (-1,1):
  plane=-11 if sign>0 else -13.5;point=(-sign*7,-3,plane)
  drive_parts=_drive_outlet(host,point,sign,(-sign*5,-1,-18),'thumb_cmc_yaw_drive_'+str(sign))
  if sign<0:
   # The final palm rib grazes the last .097 mm of this bolt's free tip.
   # Retain both jaw engagements and shorten that unused tip by .11 mm.
   drive_parts=[_finish(p & (bd.Pos(p.center().X,p.center().Y,p.bounding_box().min.Z+.11+5)*bd.Box(8,8,10)),p.label) if p.label.endswith('_host_M0p6_screw') else p for p in drive_parts]
  add(drive_parts,'wrist_flexion')
  point=(-sign*5.5,33,-9.5 if sign>0 else -12)
  add(_drive_outlet(_meta_host(),point,sign,(-sign*6.5,33,-19),'thumb_mcp_yaw_drive_'+str(sign)),'thumb_cmc_flexion')
 # Each 1-mm splice/inlet pair shares a genuine two-row clamp backbone.
 import json
 from pathlib import Path
 anchors=json.loads(Path(__file__).with_name('thumb_fixed_anchors.json').read_text())
 for sign in(-1,1):
  label='thumb_cmc_fixed_flex_'+str(sign);query=(sign*3,-21,sign*12)
  plan=anchors[str(sign)];x,hy,hz=plan['anchor']
  hl,hu,hb,foot=_host_clamp(host,x,hy,hz,plan['side'],label,width=plan.get('width',3.8),height=4.)
  hu.label=label+'_host_cap';lowers=[hl];caps=[hu];bolts=[hb];holes=[]
  for y in(-24.,-23.):
   point=(sign*.9,y,sign*7);rowlabel=label+'_'+str(int(-y))
   lower,cap,screws,ears,cutters=_comb([point],(0,1,0),rowlabel,ear_sides=(sign,))
   cap.label=rowlabel+'_liner_cap'
   if sign<0 and y==-23:
    c=np.asarray(ears[0]);axis=c+[.20,0,0]
    bore=bd.Pos(*axis)*bd.Cylinder(.22,4)
    lower=lower.fuse(bd.Pos(*(c+[0,0,-.30]))*bd.Cylinder(.33,.48))-bore
    cap=cap.fuse(bd.Pos(*(c+[0,0,.30]))*bd.Cylinder(.33,.48))-bore
    cap.label=rowlabel+'_liner_cap';cutters[-1]=bore
    shank=bd.Pos(*axis)*bd.Cylinder(.20,1.08)
    head=bd.Pos(*(axis+[0,0,.74]))*bd.fillet(bd.Cylinder(.40,.40).edges(),.045)
    socket=bd.Pos(*(axis+[0,0,.94]))*bd.extrude(bd.RegularPolygon(.17,6),amount=-.23)
    screw=_finish(shank.fuse(head)-socket,rowlabel+'_liner_M0p4_screw')
    flip=bd.Pos(*axis)*bd.Rot(180,0,0)*bd.Pos(*(-axis));screws=[flip*screw]
   c=ears[0];root=np.array((c[0]+sign*.32,c[1],c[2]-.36));end=np.array(foot)
   arm=_sweep([root,*plan['arms'][0 if y==-24 else 1]['controls'],end],.25)
   lowers.extend([lower,arm]);caps.append(cap);bolts.extend(screws);holes.extend(cutters)
  raw=[s for p in lowers for s in p.solids()];body=bd.Part(bd.Compound(children=list(raw[0].fuse(*raw[1:]).solids())).wrapped)-host
  body=body.cut(*holes,*caps,*bolts)
  parts=_split(body,label+'_structural')+[p for cap in caps for p in _split(cap-host,cap.label)]+bolts
  add(parts,'wrist_flexion')
 # The four fixed CMC mouths use a single dorsal clamp and captive fastener.
 fixed=[p for p,fr,sy,k in out if p.label.startswith('thumb_cmc_fixed_flex_')]
 keep=[p for p in fixed if 'structural' not in p.label and not (p.label.startswith('thumb_cmc_fixed_flex_1_') and ('host_cap' in p.label or 'host_M0p6' in p.label))]
 raw=[s for p in fixed if 'structural' in p.label for s in p.solids()]
 shared=raw[0].fuse(*raw[1:]).cut(*keep)
 out=[entry for entry in out if not entry[0].label.startswith('thumb_cmc_fixed_flex_')]
 for p in [*_split(shared,'thumb_cmc_fixed_flex_shared_structural'),*keep]:out.append((p,'wrist_flexion','thumb','fastener' if 'screw' in p.label else 'guide_mount'))
 # The six wrist splice outlets share an oblique, scalloped bank.
 ends=[e for e in guide_end_registry() if e.frame=='wrist_flexion' and e.name.startswith('thumb_') and '_wrist_guide_outlet' in e.name and ('_mcp_' in e.name or '_ip_' in e.name)]
 assert len(ends)==6
 r=np.array([[2**-.5,2**-.5,0],[-2**-.5,2**-.5,0],[0,0,1.]])
 points=[tuple(r@(np.array(e.point)-np.array(THUMB_CMC))) for e in ends]
 tangent=tuple(r@np.array(ends[0].tangent))
 # Registry conversions are rounded only to merge an exact common datum plane.
 y=sum(p[1] for p in points)/6;z=sum(p[2] for p in points)/6;points=[(p[0],y,z) for p in points]
 label='thumb_wrist_splice_outlet_comb';lower,cap,screws,ears,cutters=_comb(points,tangent,label)
 screws=[_finish(p & (bd.Pos(*max(ears))*bd.Cylinder(.44,4)),p.label) if '_liner_+1_' in p.label else p for p in screws]
 c=min(ears);root=(c[0]-.32,c[1],c[2]-.36)
 # The radial CMC drive jaw already owns this exact palm-ring clamp.
 # Join the splice arm to that body and retain its existing cap and screw.
 q=_near_anchor(host,(-5,-1,-18));foot=np.array(tuple(q))+[-1.78,0,-.85]
 import json
 from pathlib import Path
 plan=json.loads(Path(__file__).with_name('remaining_support_paths.json').read_text())['thumb_splice']
 arm=_sweep([root,*plan['controls'],foot],.25)
 old=[p for p,fr,sy,k in out if p.label.startswith('thumb_cmc_yaw_drive_1_structural')]
 out=[entry for entry in out if not entry[0].label.startswith('thumb_cmc_yaw_drive_1_structural')]
 raw=[lower,arm,*[base.inverse()*p for p in old]];solids=[s for p in raw for s in p.solids()]
 body=bd.Part(bd.Compound(children=list(solids[0].fuse(*solids[1:]).solids())).wrapped)-host
 mates=[base.inverse()*p for p,fr,sy,k in out if p.label.startswith('thumb_cmc_yaw_drive_1_')]
 body=body.cut(*cutters,cap,*screws,*mates)
 add(_split(body,'thumb_radial_shared_guide_bank_structural')+_split(cap-host,label+'_liner_cap')+screws,'wrist_flexion')
 from lib.remaining_cap_relief import clear_cap
 return [(q,fr,sy,k) for p,fr,sy,k in out for q in clear_cap(p)]


def thumb_remaining_mounts():return thumb_downstream_mounts()+thumb_base_mounts()
