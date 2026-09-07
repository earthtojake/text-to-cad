"""Exact final rear fastener fit and side-entry nut insertion tests."""
from pathlib import Path
import sys,json,hashlib
ROOT=Path(__file__).resolve().parents[4]
SRC=ROOT/'models/assemblies/src/anthropomorphic_hand'
sys.path.insert(0,str(SRC))
from cadgen import build123d as bd
from lib.actuator_fasteners import actuator_fasteners
from check_actuator_fasteners import bbox,overlap,volume

def main():
    parts=[p for p,*_ in actuator_fasteners()]
    selected=[p for p in parts if p.label.startswith('rear_chassis_')]
    frame=bd.import_step(ROOT/'models/assemblies/STEP/anthropomorphic_hand/forearm_frame_review.step')
    structural=list(frame.solids());boxes=[bbox(p) for p in parts]
    report={'body_count':len(parts),'rear_body_count':len(selected),'collisions':[],'nut_seats':[],'insertion_samples':[],'sources':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (SRC/'lib/actuator_fasteners.py',SRC/'lib/forearm_frame.py',ROOT/'models/assemblies/STEP/anthropomorphic_hand/forearm_frame_review.step')}}
    for p in selected:
        pb=bbox(p)
        for other,ob in zip(parts,boxes):
            if p is other or not overlap(pb,ob):continue
            v=volume(p,other)
            if v>1e-7:report['collisions'].append([p.label,other.label,v])
        for i,s in enumerate(structural):
            v=volume(p,s)
            if v>1e-7:report['collisions'].append([p.label,'structure_'+str(i),v])
        if 'captive_nut' in p.label:
            d=min(p.distance_to(s) for s in structural)
            # A tiny approach toward the rear load-bearing ledge must produce
            # positive common volume, proving actual finite seat contact.
            approach=bd.Pos(0,-.001,0)*p
            seat_volume=sum(volume(approach,s) for s in structural)
            report['nut_seats'].append({'nut':p.label,'distance_mm':d,'approach_volume_mm3':seat_volume})
            sign=1 if p.center().X>0 else -1
            for distance in (0,.5,1.,1.5,2.,3.):
                shifted=bd.Pos(sign*distance,0,0)*p
                v=sum(volume(shifted,s) for s in structural)
                report['insertion_samples'].append({'nut':p.label,'outboard_displacement_mm':distance,'intersection_volume_mm3':v})
        print(p.label,'checked',flush=True)
    report['ok']=not report['collisions'] and len(report['nut_seats'])==4 and all(r['distance_mm']<1e-7 and r['approach_volume_mm3']>1e-8 for r in report['nut_seats']) and all(r['intersection_volume_mm3']<1e-7 for r in report['insertion_samples'])
    Path(__file__).with_suffix('.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2),flush=True)
    if not report['ok']:raise SystemExit(1)

if __name__=='__main__':main()
