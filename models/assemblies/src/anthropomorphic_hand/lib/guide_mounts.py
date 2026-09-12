"""Tendon liner endpoint ownership and physical split reaction combs.

All placement comes from the accepted neutral routes. Returned bodies are already
in the assembled neutral fan; callers must not apply the finger fan again.
Guide ends shared by two adjacent liners use one clamping datum.
"""
from dataclasses import dataclass, field
from collections import defaultdict
import numpy as np
from cadgen import build123d as bd, srgb
from lib.layout import JOINT_BY_NAME, FINGERS, finger_fan_matrix
from lib.finger_routing import endpoint, tangent
from lib.neutral_routes import NEUTRAL_ROUTES


@dataclass
class GuideEnd:
    name: str
    frame: str
    point: tuple
    tangent: tuple
    routes: list = field(default_factory=list)
    ends: list = field(default_factory=list)


def guide_end_registry(routes=None):
    """Fixed parent/child material frames, including compliant wrist endpoints.

    The floating inlet of each capstan follower is deliberately not a rigid
    mounting datum. Its downstream mouth is rigidly attached to the forearm.
    """
    entries={}
    for route in (NEUTRAL_ROUTES if routes is None else routes):
        groups=route['groups']
        for gi,g in enumerate(groups):
            guide=g.get('guide')
            if guide not in ('snug_reaction_liner','fixed_curved_guide','compliant_wrist_guide','open_saddle'):continue
            neutralizes=g.get('neutralizes',[])
            for end in (False,True):
                if guide=='open_saddle' and not end:continue
                if neutralizes:
                    frame=neutralizes[-1] if end else JOINT_BY_NAME[neutralizes[0]].parent
                elif g['frame']!='variable':frame=g['frame']
                elif not end:frame='forearm'
                else:
                    following=groups[gi+1] if gi+1<len(groups) else None
                    if following and following.get('neutralizes'):
                        frame=JOINT_BY_NAME[following['neutralizes'][0]].parent
                    elif following and following['frame']!='variable':frame=following['frame']
                    else:frame=JOINT_BY_NAME[route['joint']].parent
                segment=g['path'][-1 if end else 0]
                p=tuple(float(v) for v in endpoint(segment,end));t=tuple(float(v) for v in tangent(segment,end))
                key=(frame,tuple(round(v,6) for v in p),tuple(round(v,6) for v in t))
                if key not in entries:entries[key]=GuideEnd(g['label']+('_outlet' if end else '_inlet'),frame,p,t)
                entries[key].routes.append(route['name']);entries[key].ends.append((g['label'],'outlet' if end else 'inlet'))
    return list(entries.values())


def _finish(s,label,color='#9DADB5'):
    if not s.is_valid or len(s.solids())!=1 or s.volume<=0:
        raise ValueError(f'{label}: invalid mount, solids={len(s.solids())}')
    s.label=label;s.color=srgb(color);s.cad_material={'metalness':.85,'roughness':.28}
    return s


def _rod(a,b,r=.22):
    a=np.array(a,float);b=np.array(b,float);v=b-a
    return bd.Plane(origin=(a+b)/2,z_dir=v).location*bd.Cylinder(r,float(np.linalg.norm(v)))


def _sweep(points,r=.24):
    e=bd.Edge.make_bezier(*points)
    return bd.sweep(bd.Plane(origin=e.position_at(0),z_dir=e.tangent_at(0))*bd.Circle(r),path=e)


def _bolt(x,y,z,length,label):
    """M0.6 socket screw envelope with working socket, unthreaded B-rep shank."""
    sh=bd.Pos(x,y,z-length/2)*bd.Cylinder(.30,length)
    head=bd.Pos(x,y,z+.20)*bd.Cylinder(.50,.40)
    head=bd.fillet(head.edges(),.055)
    socket=bd.Pos(x,y,z+.40)*bd.extrude(bd.RegularPolygon(.23,6),amount=-.23)
    return _finish(sh.fuse(head)-socket,label,'#6F7E85')


def _rail_saddle(host,x,y,z,label):
    """Two machined jaws exactly seated on the unchanged phalanx rail.

    The host subtraction is the mating datum. Positive volume overlap with the
    skeleton is zero; the saddle reproduces its exact curved contact surfaces.
    """
    outer=bd.Pos(x,y,z)*bd.Box(2.25,1.10,2.4)
    outer=bd.fillet(outer.edges(),.10)
    shell=outer-host
    # Native upper and lower jaws close about the dorsal rail's mid-height.
    lower=shell & (bd.Pos(x,y,z-1.25)*bd.Box(5,3,2.48))
    upper=shell & (bd.Pos(x,y,z+1.25)*bd.Box(5,3,2.48))
    # Inboard screw ears make both jaws removable without changing the rail.
    sx=x-np.sign(x)*1.75
    for is_upper,part in ((False,lower),(True,upper)):
        ez=z+(.43 if is_upper else -.43)
        tab=bd.Pos((x+sx)/2,y,ez)*bd.Box(abs(sx-x)+.65,1.0,.42)
        # Tab must not enter the rail; reapply its exact seating profile.
        part=part.fuse(tab)-host
        part=part-(bd.Pos(sx,y,z)*bd.Cylinder(.32,4))
        if is_upper:upper=part
        else:lower=part
    return lower,upper,(sx,y,z+.64)


def make_phalanx_comb(length,width,station,lanes,label='reaction_comb'):
    """Four or two actual split bores, scalloped lid and two rail clamps.

    Local finger +Y; lanes lie at Z=0. Short .55-long bores R.47 clear the
    accepted R.45 liners; their .57 outer radii leave daylight at 1.2 pitch.
    Side branches descend to the dorsal rail and do not cross the tendon lanes.
    """
    from lib.phalanx import make_phalanx
    host=make_phalanx(length,width)
    lanes=sorted(lanes);y=station
    ringparts=[bd.Pos(x,y,0)*bd.Cylinder(.57,.55,rotation=(90,0,0)) for x in lanes]
    band=bd.Pos((min(lanes)+max(lanes))/2,y,0)*bd.Box(max(lanes)-min(lanes),.55,1.05)
    raw=band.fuse(*ringparts)
    for x in lanes:raw=raw-(bd.Pos(x,y,0)*bd.Cylinder(.47,1.55,rotation=(90,0,0)))
    bottom=raw & (bd.Pos(0,y,-2.04)*bd.Box(width+8,4,4))
    top=raw & (bd.Pos(0,y,2.04)*bd.Box(width+8,4,4))
    parts=[];railx=width/2-.725
    # Locate the rail's actual dorsal band from a thin local cross section.
    for sign in (-1,1):
        x=sign*railx
        section=host & (bd.Pos(x,y,-3.5)*bd.Box(1.0,.02,4))
        bb=section.bounding_box();z=(bb.min.Z+bb.max.Z)/2
        lower,upper,bolt=_rail_saddle(host,x,y,z,label)
        c=sign*(max(abs(v) for v in lanes)+.98)
        # Clamp screw ears sit laterally beyond the last liner.
        for istop in (False,True):
            zz=.32 if istop else -.32
            ear=bd.Pos(c,y,zz)*bd.Cylinder(.48,.46)
            bridge=bd.Pos((c+sign*max(abs(v) for v in lanes))/2,y,zz)*bd.Box(abs(c)-max(abs(v) for v in lanes),.55,.40)
            if istop:top=top.fuse(ear,bridge)
            else:bottom=bottom.fuse(ear,bridge)
        bottom=bottom-(bd.Pos(c,y,0)*bd.Cylinder(.32,3))
        top=top-(bd.Pos(c,y,0)*bd.Cylinder(.32,3))
        arm=_sweep([(c+sign*.36,y,-.40),(c+sign*.36,y,-1.7),(x-sign*.85,y,z-.95),(x-sign*.25,y,z-1.05)],.25)
        bottom=bottom.fuse(arm,lower)
        bottom=bottom-(bd.Pos(c,y,0)*bd.Cylinder(.32,3))
        parts.append(_finish(upper,label+f'_rail_{"left" if sign<0 else "right"}_cap'))
        parts.append(_bolt(*bolt,1.35,label+f'_rail_{"left" if sign<0 else "right"}_M0p6_screw'))
        parts.append(_bolt(c,y,.55,1.1,label+f'_liner_{"left" if sign<0 else "right"}_M0p6_screw'))
    # Ream after the screw ears/branches are joined: those roots partially
    # cover the outer two bores before the finishing operation.
    for lane in lanes:
        cutter=bd.Pos(lane,y,0)*bd.Cylinder(.47,1.55,rotation=(90,0,0))
        bottom=bottom-cutter;top=top-cutter
    # The curved branch roots also receive the exact rail seating cut.
    bottom=bottom-host
    # Machine the actual cap and fastener seating faces after branch fusion.
    for mate in parts:
        if 'screw' in mate.label:bottom=bottom-mate
    for i,mate in enumerate(parts):
        if 'cap' in mate.label:parts[i]=_finish(mate-bottom,mate.label)
    # At full MCP flexion the positive yaw journal occupies the middle of
    # this comb. Each lateral pair has its own rail saddle and pinch screw;
    # separate the two banks without moving any of the four liner bores.
    if '_mcp_outlet_' in label:
        journal_corridor=bd.Pos(0,y,0)*bd.Box(5.0,4,6)
        bottom=bottom-journal_corridor
        top=top-journal_corridor
    bottoms=list(bottom.solids())
    structural=[_finish(s,label+'_structural_lower_jaw'+('_'+str(i+1) if len(bottoms)>1 else '')) for i,s in enumerate(bottoms)]
    tops=list(top.solids())
    lids=[_finish(s,label+'_scalloped_upper_jaw'+('_'+str(i+1) if len(tops)>1 else '')) for i,s in enumerate(tops)]
    parts=[*structural,*lids,*parts]
    return parts


def phalanx_guide_mounts(finger_names=None):
    """Mount tuples (shape, frame, system, kind), in the assembled neutral fan."""
    from lib.assembly import matrix_location
    out=[]
    for f in FINGERS:
        if finger_names and f.name not in finger_names:continue
        groups=[('mcp_outlet',0,12.25,[-4.2,-3.,3.,4.2]),
                ('pip_inlet',0,f.lengths[0]-12.25,[-4.2,4.2]),
                ('pip_outlet',1,10. if f.name=='little' else 12.25,[-4.2,4.2])]
        for role,segment,station,lanes in groups:
            frame=f.name+('_mcp_flexion' if segment==0 else '_pip')
            placement=matrix_location(finger_fan_matrix(f))*bd.Pos(f.x,f.base_y+sum(f.lengths[:segment]),0)
            for p in make_phalanx_comb(f.lengths[segment],f.widths[segment],station,lanes,f.name+'_'+role+'_comb'):
                out.append((placement*p,frame,f.name,'guide_mount'))
    return out
