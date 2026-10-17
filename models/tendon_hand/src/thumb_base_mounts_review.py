from cadgen import build123d as bd,step
from lib.thumb_remaining_mounts import thumb_base_mounts
@step(out='../STEP/thumb_base_mounts_review.step')
def thumb_base_mounts_review():
 return bd.Compound(label='thumb_base_guide_mounts',children=[s for s,f,y,k in thumb_base_mounts()])
if __name__=='__main__':thumb_base_mounts_review()
