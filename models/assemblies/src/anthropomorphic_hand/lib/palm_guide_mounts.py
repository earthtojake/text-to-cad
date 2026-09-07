"""Palm-side reaction banks fixed to the existing metacarpal bearing bosses.

Short split comb rows capture the actual wrist and reaction-liner endpoints.
Open side rails collect their reaction forces into a removable split clamp
around the fixed dorsal MCP boss. All returned geometry is already fanned.
"""
from collections import defaultdict
import numpy as np
from cadgen import build123d as bd
from lib.guide_mounts import guide_end_registry,_finish,_rod,_sweep,_bolt
from lib.layout import FINGERS,finger_fan_matrix,MCP_PALM_SUPPORT_PLANES


def _row(xs,y,z,label):
    """One row of bores; split jaws, screw ears and actual socket fasteners."""
    xs=sorted(xs);a=min(xs);b=max(xs)
    raw=bd.Pos(a,y,z)*bd.Cylinder(.57,.55,rotation=(90,0,0))
    for x in xs[1:]:raw=raw.fuse(bd.Pos(x,y,z)*bd.Cylinder(.57,.55,rotation=(90,0,0)))
    if b>a:raw=raw.fuse(bd.Pos((a+b)/2,y,z)*bd.Box(b-a,.55,1.05))
    lower=raw & (bd.Pos((a+b)/2,y,z-2.04)*bd.Box(b-a+5,4,4))
    upper=raw & (bd.Pos((a+b)/2,y,z+2.04)*bd.Box(b-a+5,4,4))
    ends=[(-1,a),(1,b)] if len(xs)>1 else [(1 if a>=0 else -1,a)]
    screws=[];roots=[]
    for sign,outer in ends:
        c=outer+sign*.98
        for top in (False,True):
            zz=z+(.32 if top else -.32)
            ear=bd.Pos(c,y,zz)*bd.Cylinder(.48,.46)
            bridge=bd.Pos((c+outer)/2,y,zz)*bd.Box(.98,.55,.40)
            if top:upper=upper.fuse(ear,bridge)
            else:lower=lower.fuse(ear,bridge)
        hole=bd.Pos(c,y,z)*bd.Cylinder(.32,3)
        upper=upper-hole;lower=lower-hole
        roots.append((sign,(c+sign*.35,y,z-.40)))
        screws.append(_bolt(c,y,z+.55,1.1,label+('_left' if sign<0 else '_right')+'_M0p6_screw'))
    for x in xs:
        bore=bd.Pos(x,y,z)*bd.Cylinder(.47,2,rotation=(90,0,0))
        lower=lower-bore;upper=upper-bore
    return lower,_finish(upper,label+'_upper_jaw'),screws,roots


def _boss_clamp(host,z=12.5,label='metacarpal_boss_clamp'):
    raw=bd.Pos(0,0,z)*(bd.Cylinder(4.18,1.0)-bd.Cylinder(3.77,3))
    back=raw & (bd.Pos(0,-5.04,z)*bd.Box(12,10,4))
    front=raw & (bd.Pos(0,5.04,z)*bd.Box(12,10,4))
    screws=[]
    for sign in (-1,1):
        x=sign*4.9
        for forward in (False,True):
            lug=bd.Pos(x,.40 if forward else -.40,z)*bd.Cylinder(.74,.75,rotation=(90,0,0))
            bridge=bd.Pos(sign*4.425,.40 if forward else -.40,z)*bd.Box(.95,.75,.85)
            if forward:front=front.fuse(lug,bridge)
            else:back=back.fuse(lug,bridge)
        bore=bd.Pos(x,0,z)*bd.Cylinder(.42,4,rotation=(90,0,0))
        back=back-bore;front=front-bore
        # M0.8 cross bolt, with a real hexagonal socket recess.
        screw=bd.Cylinder(.40,1.57)
        head=bd.Pos(0,0,.975)*bd.Cylinder(.70,.4)
        socket=bd.Pos(0,0,1.20)*bd.extrude(bd.RegularPolygon(.30,6),amount=-.28)
        screw=screw.fuse(head)-socket
        screw=bd.Pos(x,0,z)*bd.Rot(-90,0,0)*screw
        screws.append(_finish(screw,label+('_left' if sign<0 else '_right')+'_M0p8_screw','#6F7E85'))
    return back-host,_finish(front-host,label+'_front_cap'),screws


def palm_ray_endpoints(finger_name):
    from lib.assembly import matrix_location
    f=next(f for f in FINGERS if f.name==finger_name)
    world=finger_fan_matrix(f)@np.array([[1,0,0,f.x],[0,1,0,f.base_y],[0,0,1,0],[0,0,0,1]])
    inv=np.linalg.inv(world)
    ends=[e for e in guide_end_registry() if e.frame=='wrist_flexion' and all(r.startswith(finger_name+'_') for r in e.routes)]
    entries=[]
    for end in ends:
        p=(inv@np.array([*end.point,1]))[:3]
        v=inv[:3,:3]@np.array(end.tangent)
        if np.linalg.norm(v-[0,1,0])>1e-6:raise ValueError(f'{end.name}: ray clamp needs +Y tangent, got {v}')
        entries.append((end,np.round(p,8)))
    return entries,world


def make_palm_ray_mounts(finger_name,host):
    """Return fourteen anchored endpoint datums for index, middle or ring ray."""
    from lib.assembly import matrix_location
    if finger_name not in ('index','middle','ring'):raise ValueError('independent fifth-ray and thumb mounts use their own frame contracts')
    entries,world=palm_ray_endpoints(finger_name)
    local_host=matrix_location(np.linalg.inv(world))*host
    grouped=defaultdict(list)
    for end,p in entries:grouped[(float(p[1]),float(p[2]))].append(float(p[0]))
    backbone=[];caps=[];fasteners=[];ymin=min(y for y,z in grouped);zmin=min(z for y,z in grouped)-.8
    def rail_x(sign):
        # Adjacent index/middle banks converge at their wrist-facing ends.
        return sign*(7.2 if (finger_name,sign) in (("index",1),("middle",-1)) else 8.)
    for sign in (-1,1):
        x=rail_x(sign)
        backbone.append(_rod((x,ymin,zmin),(x,ymin,6),.40))
        import json
        from pathlib import Path
        plan=json.loads(Path(__file__).with_name('palm_dorsal_bank_paths.json').read_text())[finger_name+'_'+str(sign)]
        backbone.append(_sweep([plan['root'],*plan['controls'],plan['end']],.45))
    row_bores=[];row_screws=[]
    for index,((y,z),xs) in enumerate(sorted(grouped.items())):
        label=f'{finger_name}_palm_bank_row_{index+1:02d}'
        lower,cap,screws,roots=_row(xs,y,z,label)
        backbone.append(lower);caps.append(cap);fasteners.extend(screws)
        for sign,p in roots:
            x=rail_x(sign);target=(x,y,z-.8)
            backbone.append(_sweep([p,(p[0]+(x-p[0])/3,y,z-.6),(p[0]+2*(x-p[0])/3,y,z-.8),target],.24))
            if abs(y-ymin)>1e-7:
                backbone.append(_rod(target,(x,ymin,z-.8),.35))
        row_bores.extend((x,y,z) for x in xs)
        row_screws.extend((p[0]-sign*.35,y,z) for sign,p in roots)
    boss,cap,screws=_boss_clamp(local_host,z=MCP_PALM_SUPPORT_PLANES[1],label=finger_name+'_palm_bank_boss_clamp')
    backbone.append(boss);caps.append(cap);fasteners.extend(screws)
    body=backbone[0].fuse(*backbone[1:])
    for x,y,z in row_bores:body=body-(bd.Pos(x,y,z)*bd.Cylinder(.47,2,rotation=(90,0,0)))
    for x,y,z in row_screws:body=body-(bd.Pos(x,y,z)*bd.Cylinder(.32,3))
    # Compact neighbouring rows need local relief around their removable caps
    # and fasteners after the support arms are fused.
    body=body.cut(*caps,*fasteners)
    # All branches are machined against the host's actual contact surface.
    body=body-local_host
    if finger_name=='ring':
        # A tiny shared border with the actual fifth-ray frame is relieved
        # through the recorded cup range; the bank mouth datums stay fixed.
        # Native common bounds at cup 0/10/20/25 are identical. Mill a
        # 0.02 mm clearance border around that small protruding corner.
        relief=bd.Pos(17.9786811577,72.6900050971,-.7418332420)*bd.Box(.106381,.498535,.307845)
        body=body-(matrix_location(np.linalg.inv(world))*relief)
    # A palm truss branch can divide the back clamp jaw. Those fitted jaws
    # remain real separate bodies, united mechanically by the front cap and
    # its two screws; do not bridge through the pre-existing palm branch.
    solids=list(body.solids())
    bodies=[_finish(s,finger_name+'_palm_bank_structural_body'+('_'+str(i+1) if len(solids)>1 else '')) for i,s in enumerate(solids)]
    caps=[_finish(p-local_host,p.label) for p in caps]
    placement=matrix_location(world)
    return [(placement*p,'wrist_flexion','palm','guide_mount') for p in [*bodies,*caps,*fasteners]]
