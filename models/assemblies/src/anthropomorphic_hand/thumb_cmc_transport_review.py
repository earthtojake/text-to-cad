"""Six neutral CMC tendon and reaction-liner swept solids for strict validation."""
from cadgen import build123d as bd,step
from lib.thumb_cmc_transport import thumb_cmc_packet
from lib.bowden_guide import make_bowden_body

@step(out='../../STEP/anthropomorphic_hand/thumb_cmc_transport_review.step',mesh_tolerance=.006,mesh_angular_tolerance=.035)
def thumb_cmc_transport_review():
    children=[]
    for row in thumb_cmc_packet():
        children.append(make_bowden_body(row['path'],row['tendon']+'_cmc_tendon'))
        children.append(make_bowden_body(row['path'],row['tendon']+'_cmc_reaction_liner',liner=True))
    return bd.Compound(label='thumb_cmc_six_continuous_reaction_transports',children=children)

if __name__=='__main__':thumb_cmc_transport_review()
