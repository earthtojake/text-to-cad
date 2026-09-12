"""Ninety-six forearm liner mouths on twelve removable reaction bridge banks.

The five upstream banks and one distal portal on each face capture the accepted
capstan guide outlets and wrist inlets. Split jaws have R.47 through bores;
liners remain R.45. Fasteners are separate named solids with socket recesses.
"""
from collections import defaultdict
from cadgen import build123d as bd, report
from .guide_mounts import guide_end_registry, _bolt, _finish, _rod, _sweep
from .finish import finish
from .forearm_frame import SIDE_RAIL_X,SIDE_RAIL_WIDTH,SIDE_RAIL_LENGTH,SIDE_RAIL_HEIGHT,SIDE_RAIL_CENTER_Y,SIDE_RAIL_FILLET


def _row(xs,y,z,label):
    xs=sorted(xs);a,b=xs[0],xs[-1]
    raw=bd.Pos((a+b)/2,y,z)*bd.Box(b-a,.55,1.05)
    raw=raw.fuse(*[bd.Pos(x,y,z)*bd.Cylinder(.59,.55,rotation=(90,0,0)) for x in xs])
    lower=raw & (bd.Pos((a+b)/2,y,z-2.04)*bd.Box(b-a+5,4,4))
    upper=raw & (bd.Pos((a+b)/2,y,z+2.04)*bd.Box(b-a+5,4,4))
    screws=[];roots=[]
    for sign,outer in ((-1,a),(1,b)):
        c=outer+sign*.98
        for top in (False,True):
            zz=z+(.32 if top else -.32)
            ear=bd.Pos(c,y,zz)*bd.Cylinder(.48,.46)
            bridge=bd.Pos((c+outer)/2,y,zz)*bd.Box(.98,.55,.40)
            if top:upper=upper.fuse(ear,bridge)
            else:lower=lower.fuse(ear,bridge)
        hole=bd.Pos(c,y,z)*bd.Cylinder(.32,3)
        upper=upper-hole;lower=lower-hole
        counterbore=bd.Pos(c,y,z+.55)*bd.Cylinder(.46,.40)
        upper=upper-counterbore
        roots.append((sign,(c+sign*.35,y,z-.40)))
        shank=bd.Pos(c,y,z-.095)*bd.Cylinder(.30,.89)
        head=bd.Pos(c,y,z+.475)*bd.Cylinder(.45,.25)
        head=bd.fillet(head.edges(),.035)
        socket=bd.Pos(c,y,z+.61)*bd.extrude(bd.RegularPolygon(.20,6),amount=-.17)
        screws.append(finish(shank.fuse(head)-socket,'steel',label+('_left' if sign<0 else '_right')+'_M0p6_recessed_split_jaw_screw'))
    for x in xs:
        bore=bd.Pos(x,y,z)*bd.Cylinder(.47,2,rotation=(90,0,0))
        lower=lower-bore;upper=upper-bore
    return lower,finish(_finish(upper,label+'_removable_upper_jaw'),'dark',label+'_removable_upper_jaw'),screws,roots


def _foot(host,x,y,label):
    foot=bd.Pos(x,y,5.0)*bd.extrude(bd.RectangleRounded(3.20,5.0,.35),amount=2.50)
    foot=bd.fillet(foot.edges().group_by(bd.Axis.Z)[-1],.10)
    foot=foot-host
    foot=foot-bd.Pos(x,y-1,6)*bd.Cylinder(.54,7)
    shank=bd.Pos(x,y-1,6.10)*bd.Cylinder(.50,2.8)
    head=bd.Pos(x,y-1,7.85)*bd.Cylinder(.85,.70)
    head=bd.fillet(head.edges(),.10)
    socket=bd.Pos(x,y-1,8.25)*bd.extrude(bd.RegularPolygon(.37,6),amount=-.45)
    bolt=finish(shank.fuse(head)-socket,'steel',label+'_M1_frame_mount_screw')
    return foot,bolt


def forearm_guide_rows():
    rows=defaultdict(list)
    for e in guide_end_registry():
        if e.frame!='forearm' or not (e.name.endswith('_exit_guide_outlet') or e.name.endswith('_wrist_guide_inlet')):continue
        if sum((v-t)**2 for v,t in zip(e.tangent,(0,1,0)))>1e-10:raise ValueError(f'{e.name}: expected +Y mouth tangent')
        x,y,z=e.point;rows[(y,z)].append(x)
    if sum(map(len,rows.values()))!=96:raise ValueError('Expected 96 forearm liner endpoints')
    return dict(rows)


def _positive_bank(row_spec,host,label,foot_y,front=False):
    structure=[];caps=[];fasteners=[];bores=[];screwaxes=[]
    maxz=max(z for y,z,xs in row_spec)
    for side in (-1,1):
        x=side*38.
        foot,bolt=_foot(host,x,foot_y,label+('_left' if side<0 else '_right'))
        structure.append(foot);fasteners.append(bolt)
        if front:
            # A swept side arch carries the forward mouth portal while staying
            # entirely outside the complete moving wrist/tendon corridor.
            structure.append(_sweep([(x,foot_y+1.2,7.1),(x,foot_y+1.2,22),(x,-12,28),(x,-12,37)],.72))
            structure.append(_rod((x,-12,36.5),(x,-12,maxz),.65))
            structure.append(_rod((x,-17,37),(x,-12,37),.60))
        else:
            structure.append(_sweep([(x,foot_y+1.2,7.1),(x,foot_y+1.2,11),(x,foot_y,16),(x,foot_y,maxz)],.65))
    for index,(y,z,xs) in enumerate(row_spec):
        tag=label+f'_row_{index+1:02d}'
        low,cap,screws,roots=_row(xs,y,z,tag)
        structure.append(low);caps.append(cap);fasteners.extend(screws)
        for side,p in roots:
            # Rise beside the screw ear, then travel at this row's own Z.
            # This avoids the staggered next row, just1.2mm lower.
            structure.append(_sweep([p,(p[0]+side*.60,y,z-.40),(p[0]+side*1.1,y,z),(side*38,y,z)],.24))
            screwaxes.append((p[0]-side*.35,y,z))
        bores.extend((x,y,z) for x in xs)
    body=structure[0].fuse(*structure[1:])
    body=body.cut(*[bd.Pos(x,y,z)*bd.Cylinder(.47,2,rotation=(90,0,0)) for x,y,z in bores])
    body=body.cut(*[bd.Pos(x,y,z)*bd.Cylinder(.32,1.12) for x,y,z in screwaxes])
    # Feet already carry the exact mating cut. All rising branches begin above
    # the rail crest; the independent full-frame audit verifies this separation.
    if len(body.solids())!=1:print('FOREARM_BANK_DISCONNECTED',label,[(v.volume,str(v.bounding_box())) for v in body.solids()],flush=True)
    body=finish(_finish(body,label+'_structural_lower_jaws_and_arches'),'dark',label+'_structural_lower_jaws_and_arches')
    return [body,*caps,*fasteners]


def make_forearm_guide_mount_bodies(host=None):
    """Named solids in assembled forearm coordinates; twelve base pairs hold96 mouths."""
    if host is None:
        rail=bd.Box(SIDE_RAIL_WIDTH,SIDE_RAIL_LENGTH,SIDE_RAIL_HEIGHT)
        rail=bd.fillet(rail.edges(),SIDE_RAIL_FILLET)
        host=bd.Compound(children=[bd.Pos(x,SIDE_RAIL_CENTER_Y,0)*rail for x in (-SIDE_RAIL_X,SIDE_RAIL_X)])
    rows=forearm_guide_rows();parts=[]
    # The dorsal source geometry is mirrored from its actual lane coordinates,
    # so a proper 180-degree Y rotation returns the unchanged world lane X.
    for sign in (1,-1):
        face='palmar' if sign>0 else 'dorsal'
        local_host=host if sign>0 else bd.Rot(0,180,0)*host
        local_rows={(y,abs(z)):[sign*x for x in xs] for (y,z),xs in rows.items() if z*sign>0}
        for y in (-222.,-181.,-140.,-99.,-58.):
            report(f'{face} forearm guide bridge {y:g}')
            spec=[(yy,z,xs) for (yy,z),xs in local_rows.items() if yy==y]
            bank=_positive_bank(spec,local_host,f'{face}_forearm_exit_bridge_{int(-y)}',y)
            parts.extend(bank if sign>0 else [bd.Rot(0,180,0)*b for b in bank])
        spec=sorted((y,z,xs) for (y,z),xs in local_rows.items() if y in (-17.,-12.))
        bank=_positive_bank(spec,local_host,f'{face}_forearm_distal_wrist_portal',-35.,True)
        parts.extend(bank if sign>0 else [bd.Rot(0,180,0)*b for b in bank])
    return parts
