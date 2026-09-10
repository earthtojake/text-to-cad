"""Assembled bearing, continuous-keyed shaft and retaining-ring occurrences.

All shafts use a continuous D section for axial withdrawal. Round bushings
support the remaining circular shaft surface. Positive and negative yaw stubs
stay outside each universal joint's crossing flexion shaft.
"""
from cadgen import build123d as bd
from lib.layout import JOINTS,FINGERS,CMC_YAW_HUB_PLANES,MCP_YAW_HUB_PLANES,CMC_PALM_SUPPORT_PLANES,MCP_PALM_SUPPORT_PLANES
from lib.axle import make_driven_axle
from lib.bushing import make_bushing
from lib.retaining_ring import make_retaining_ring


def joint_hardware():
    from lib.assembly import joint_location
    bodies=[];cache={}
    def proto(key,make):
        if key not in cache:cache[key]=make()
        return cache[key]
    def add(shape,placement,name,frame,system,kind):
        p=placement*shape;p.label=name;bodies.append((p,frame,system,kind))
    def shaft_stack(joint,start,length,radius=1.,direction=1.,suffix=''):
        placement=joint_location(joint)*bd.Pos(0,0,start)*(bd.Rot(0,0,0) if direction>0 else bd.Rot(180,0,0))
        flat=.75 if radius==1 else 2.25
        sh=proto(('shaft',length,radius),lambda:make_driven_axle(length,radius,flat,head_radius=1.6 if radius==1 else 4.8))
        add(sh,placement,joint.name+suffix+'_keyed_shaft',joint.name,joint.system,'shaft')
        wide_cmc=joint.name=='thumb_cmc_abduction' and suffix=='_dorsal_drive_stub'
        ring=proto(('ring',radius,wide_cmc),lambda:make_retaining_ring(shaft_radius=radius,opening_half_angle=40 if wide_cmc else 20))
        ring_placement=placement*bd.Pos(0,0,length-.6)
        if wide_cmc:ring_placement=ring_placement*bd.Rot(0,0,275)
        add(ring,ring_placement,joint.name+suffix+'_retaining_ring',joint.name,joint.system,'retaining_ring')
    def bush(joint,inner,length,sign,suffix=''):
        placement=joint_location(joint)*bd.Pos(0,0,inner)*(bd.Rot(0,0,0) if sign>0 else bd.Rot(180,0,0))
        slender=sign>0 and joint.name in {f.name+'_mcp_abduction' for f in FINGERS}
        b=proto(('bushing',length,slender),lambda:make_bushing(length=length,outer_radius=1.8,flange_radius=2.02) if slender else make_bushing(length=length))
        add(b,placement,joint.name+suffix+('_positive' if sign>0 else '_negative')+'_bushing',joint.parent,joint.system,'bushing')
    for j in JOINTS:
        if j.system=='wrist':
            if j.name=='wrist_abduction':shaft_stack(j,-10.82,22.40,3.)
            else:shaft_stack(j,-21.24,43.30,3.)
            continue # Four wrist bushings are placed by the wrist builder.
        if j.name=='palm_cup':
            # Axis is -Y: fixed eyes have centers at local z=+5 and -35.
            bush(j,3.8,2.4,1);bush(j,-33.8,2.4,-1)
            shaft_stack(j,-36.42,43.60)
            continue
        if 'abduction' in j.name:
            cmc='cmc' in j.name
            supports=CMC_PALM_SUPPORT_PLANES if cmc else MCP_PALM_SUPPORT_PLANES
            hubs=CMC_YAW_HUB_PLANES if cmc else MCP_YAW_HUB_PLANES
            bush(j,supports[1]+1,2.,-1)
            if cmc:
                from lib.compact_cmc_yaw import compact_cmc_hardware
                bodies.extend(compact_cmc_hardware())
            else:
                bush(j,supports[0]-1,2.,1)
                palmar_start=supports[0]+1.22
                palmar_inner=hubs[0]-.7
                shaft_stack(j,palmar_start,palmar_start-palmar_inner+.86,direction=-1,suffix='_palmar_stub')
            dorsal_start=supports[1]-1.22
            upper_drive=(-11. if cmc else -9.5)+.75
            if j.system in {f.name for f in FINGERS}:
                from lib.compact_mcp_dorsal import make_compact_mcp_dorsal_axle
                sh=proto(('compact_MCP_dorsal',),make_compact_mcp_dorsal_axle)
                add(sh,joint_location(j)*bd.Pos(0,0,-17.72),j.name+'_dorsal_drive_stub_keyed_shaft',j.name,j.system,'shaft')
                ring=proto(('compact_MCP_ring',),lambda:make_retaining_ring(opening_half_angle=40))
                add(ring,joint_location(j)*bd.Pos(0,0,-8.60)*bd.Rot(0,0,275),j.name+'_dorsal_drive_stub_retaining_ring',j.name,j.system,'retaining_ring')
            else:shaft_stack(j,dorsal_start,upper_drive-dorsal_start+.86,suffix='_dorsal_drive_stub')
            continue
        if j.system=='thumb':
            width=19. if 'cmc' in j.name else 16.
            universal='ip' not in j.name
        else:
            f=next(f for f in FINGERS if f.name==j.system)
            width=f.widths[0 if ('mcp' in j.name or 'pip' in j.name) else 1]
            universal='mcp' in j.name
        if universal:
            for sign in (-1,1):bush(j,sign*(width/2+.05),1.9,sign)
            shaft_stack(j,-(width/2+2.17),width+5.10)
        else:
            for sign in (-1,1):bush(j,sign*(width/2-1.45),1.45,sign)
            shaft_stack(j,-(width/2+.22),width+1.20)
    return bodies
