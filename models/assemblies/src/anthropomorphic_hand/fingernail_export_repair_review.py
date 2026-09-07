"""Export-stable dorsal nail systems with their unchanged mounting datums."""
import json
from pathlib import Path
from cadgen import build123d as bd,step
from lib.fingernail import fingernail_bodies
@step(out='../../STEP/anthropomorphic_hand/fingernail_export_repair_review.step')
def fingernail_export_repair_review():
    bodies=fingernail_bodies();root=Path(__file__).resolve().parents[2]
    (root/'validation/anthropomorphic_hand/fingernail_export_repair_frames.json').write_text(json.dumps([dict(name=s.label,frame=f,system=system,kind=k) for s,f,system,k in bodies],indent=2)+'\n')
    return bd.Compound(label='export_stable_dorsal_nail_systems',children=[s for s,*_ in bodies])
if __name__=='__main__':fingernail_export_repair_review()
