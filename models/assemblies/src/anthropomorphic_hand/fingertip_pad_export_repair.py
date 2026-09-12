"""Export-stable fingertip pads and their actual mounting hardware."""
import hashlib,json
from pathlib import Path
from cadgen import build123d as bd,step
from lib.fingertip_pad import fingertip_pad_bodies

@step(out='../../STEP/anthropomorphic_hand/fingertip_pad_export_repair.step')
def fingertip_pad_export_repair():
    bodies=fingertip_pad_bodies()
    root=Path(__file__).resolve().parents[2]
    (root/'validation/anthropomorphic_hand/fingertip_pad_export_repair_frames.json').write_text(json.dumps([
        dict(name=s.label,frame=f,system=system,kind=k) for s,f,system,k in bodies],indent=2)+'\n')
    return bd.Compound(label='export_stable_fingertip_pad_systems',children=[s for s,*_ in bodies])

if __name__=='__main__':fingertip_pad_export_repair()
