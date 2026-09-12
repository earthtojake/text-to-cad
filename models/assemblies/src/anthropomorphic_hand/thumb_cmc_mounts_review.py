from cadgen import build123d as bd,step
from lib.thumb_cmc_mounts import thumb_cmc_mounts
@step(out='../../STEP/anthropomorphic_hand/thumb_cmc_mounts_review.step',mesh_tolerance=.006,mesh_angular_tolerance=.035)
def thumb_cmc_mounts_review():
 return bd.Compound(label='thumb_cmc_twelve_anchored_guide_ends',children=[p for p,f,s,k in thumb_cmc_mounts()])
if __name__=='__main__':thumb_cmc_mounts_review()
