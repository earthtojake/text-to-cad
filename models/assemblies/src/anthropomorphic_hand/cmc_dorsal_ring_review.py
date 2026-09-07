"""Wide-mouth CMC dorsal retainer selected by all225 pose clearance proof."""
import json
from pathlib import Path
from cadgen import build123d as bd,step
from lib.retaining_ring import make_retaining_ring
from lib.assembly import joint_location
from lib.layout import JOINT_BY_NAME
ROOT=Path('models/assemblies/validation/anthropomorphic_hand')
@step(out='../../STEP/anthropomorphic_hand/cmc_dorsal_ring_review.step',mesh_tolerance=.0008,mesh_angular_tolerance=.008)
def cmc_dorsal_ring_review():
 report=json.loads((ROOT/'cmc_dorsal_ring_rotation_wide_probe.json').read_text());assert report['sample_count']==225
 best=max(report['rows'],key=lambda r:r['minimum_gap']);assert best['minimum_gap']>0
 name='thumb_cmc_abduction_dorsal_drive_stub_retaining_ring';j=JOINT_BY_NAME['thumb_cmc_abduction']
 p=joint_location(j)*bd.Pos(0,0,-9.99)*bd.Rot(0,0,best['angle'])*make_retaining_ring(opening_half_angle=40);p.label=name
 (ROOT/'cmc_dorsal_ring_frames.json').write_text(json.dumps([dict(name=name,frame=j.name,system='thumb',kind='retaining_ring')],indent=2)+'\n')
 (ROOT/'cmc_dorsal_ring_selected.json').write_text(json.dumps(best,indent=2)+'\n')
 return bd.Compound(children=[p],label='CMC_dorsal_wide_mouth_retainer')
if __name__=='__main__':cmc_dorsal_ring_review()
