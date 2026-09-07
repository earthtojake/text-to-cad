"""R3.5 driven terminal, assembled and with its installation cover lifted."""
from cadgen import build123d as bd,step
from lib.drive_terminal import make_terminal_pulley_parts,make_driven_ferrule,make_pulley_grub_screw,make_cover_screw,make_driven_bond_line,arc_tube
from lib.finish import finish

@step(out='../../STEP/anthropomorphic_hand/drive_terminal_macro.step',mesh_tolerance=.0005,mesh_angular_tolerance=.006)
def drive_terminal_macro():
    children=[]
    wheel,cover=make_terminal_pulley_parts()
    ferrule=make_driven_ferrule()
    screw=make_pulley_grub_screw()
    rope=finish(arc_tube(3.5,.30,-3.5*2.61799387799,0,-60,-1),'tendon_flex','unchanged_R3_5_rope_wrap')
    for x,name,lift in ((-5,'assembled',0),(5,'cover_installation',3.0)):
        for role,part in (('pulley',wheel),('cover_screw',bd.Pos(0,0,lift+1. if lift else 0)*make_cover_screw()),('ferrule',bd.Pos(0,0,1.9 if lift else 0)*ferrule),('resin_bond_line',bd.Pos(0,0,.9 if lift else 0)*make_driven_bond_line()),('socket_grub_screw',screw),('tendon_wrap',rope),('capture_cover',bd.Pos(0,0,lift)*cover)):
            body=bd.Pos(x,0,0)*part;body.label=name+'_'+role;children.append(body)
    return bd.Compound(label='R3_5_captured_driven_tendon_macro',children=children)

if __name__=='__main__':drive_terminal_macro()
