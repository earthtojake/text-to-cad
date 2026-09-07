"""Ten drive terminal prototypes: five pulley radii and both antagonists."""
from cadgen import build123d as bd, step
from lib.drive_terminal import make_terminal_pulley_parts,make_driven_ferrule,make_pulley_grub_screw,make_cover_screw,make_driven_bond_line,arc_tube
from lib.finish import finish

@step(out='../../STEP/anthropomorphic_hand/drive_terminal_review.step',mesh_tolerance=.0008,mesh_angular_tolerance=.008)
def drive_terminal_review():
    children=[]
    for r,x in zip((3.5,4.5,5.5,7.,11.),(-42,-30,-16,2,29)):
        bore=3.03 if r==11 else 1.03
        for sign,y in ((1,0),(-1,27)):
            phase=-60*sign;direction=-sign;name=f'R{r}_{"positive" if sign==1 else "negative"}'
            placement=bd.Pos(x,y,0)
            wheel,cover=make_terminal_pulley_parts(r,bore,phase,direction)
            wheel.label=name+'_captured_terminal_pulley';cover.label=name+'_capture_cover'
            screw=make_cover_screw(r,phase,direction);screw.label=name+'_cover_socket_screw'
            bond=make_driven_bond_line(r,phase,direction);bond.label=name+'_resin_bond_line'
            children.extend(placement*body for body in (wheel,cover,screw,bond,
                make_driven_ferrule(r,phase,direction,name+'_curved_blind_ferrule'),
                make_pulley_grub_screw(bore,name+'_inclined_socket_grub_screw',side=sign),
                finish(arc_tube(r,.30,-r*2.61799387799,0,phase,direction),'tendon_flex' if sign==1 else 'tendon_extend',name+'_unchanged_tendon_wrap')))
    return bd.Compound(label='ten_captured_driven_tendon_terminal_prototypes',children=children)

if __name__=='__main__':drive_terminal_review()
