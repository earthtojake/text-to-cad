"""Four-lane two-axis neutral reaction guide prototype at neutral pose."""
from cadgen import build123d as bd,step
from lib.bowden_universal import bowden_universal,FOUR_LANES
from lib.bowden_guide import make_bowden_body


@step(out='../../STEP/anthropomorphic_hand/bowden_review.step',
      mesh_tolerance=.006,mesh_angular_tolerance=.035)
def bowden_review():
    children=[]
    for i,lane in enumerate(FOUR_LANES,1):
        route=bowden_universal(0,0,lane)
        children.append(make_bowden_body(route['path'],f'lane_{i:02d}_tendon'))
        children.append(make_bowden_body(route['path'],f'lane_{i:02d}_reaction_liner',liner=True))
    return bd.Compound(label='four_lane_universal_bowden_geometry_prototype',children=children)


if __name__=='__main__':
    bowden_review()
