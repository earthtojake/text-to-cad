"""Middle finger full routing prototype from palm input to eight terminations."""
from cadgen import build123d as bd,step
from lib.finger_routing import middle_finger_routes,MIDDLE,yaw_drive_plane
from lib.transport_guide import make_tendon
from lib.bowden_guide import make_bowden_body
from lib.phalanx import make_phalanx
from lib.pulley import make_pulley


@step(out='../../STEP/anthropomorphic_hand/middle_routing_review.step',
      mesh_tolerance=.008,mesh_angular_tolerance=.045)
def middle_routing_review():
    children=[];f=MIDDLE;base=(f.x,f.base_y,0.)
    y=f.base_y
    for i,(length,width) in enumerate(zip(f.lengths,f.widths)):
        shape=make_phalanx(length,width,distal=i==2,label=f'middle_link_{i+1:02d}')
        children.append(bd.Pos(f.x,y,0)*shape)
        y+=length
    targets=[('mcp_abduction',f.base_y,5.5,'yaw'),('mcp_flexion',f.base_y,5.5,'flex'),
             ('pip',f.base_y+f.lengths[0],4.5,'flex'),('dip',f.base_y+sum(f.lengths[:2]),3.5,'flex')]
    for target,y,radius,axis in targets:
        for sign,suffix in ((1,'positive'),(-1,'negative')):
            shape=make_pulley(radius,label=f'middle_{target}_{suffix}_drive_pulley')
            if axis=='yaw':placement=bd.Pos(f.x,y,yaw_drive_plane(sign))
            else:placement=bd.Pos(f.x+sign*.9,y,0)*bd.Rot(0,90,0)
            children.append(placement*shape)
    for route in middle_finger_routes():
        children.append(make_tendon(route['path'],route['name']))
        for group in route['groups']:
            if group['guide'] in ('snug_reaction_liner','fixed_curved_guide'):
                children.append(make_bowden_body(group['path'],group['label'],liner=True))
    return bd.Compound(label='middle_finger_full_tendon_routing_prototype',children=children)


if __name__=='__main__':
    middle_routing_review()
