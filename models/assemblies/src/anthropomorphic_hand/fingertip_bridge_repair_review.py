"""Five mounting bridge export repairs; silicone and all hardware are retained."""
import json
from pathlib import Path
from cadgen import build123d as bd,step
from lib.fingertip_bridge_repair import bridge_bodies

@step(out='../../STEP/anthropomorphic_hand/fingertip_bridge_repair_review.step')
def fingertip_bridge_repair_review():
    bodies=bridge_bodies();root=Path(__file__).resolve().parents[2]
    rows=[dict(name=s.label,frame=frame,system=system,kind=kind) for s,frame,system,kind in bodies]
    (root/'validation/anthropomorphic_hand/fingertip_bridge_repair_frames.json').write_text(json.dumps(rows,indent=2)+'\n')
    return bd.Compound(label='fingertip_bridge_export_repair',children=[s for s,*_ in bodies])
if __name__=='__main__':fingertip_bridge_repair_review()
