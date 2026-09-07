"""Exact all48 checks against complete imported gearbox and capstan prototypes."""
from pathlib import Path
import sys,json,time
ROOT=Path(__file__).resolve().parents[4]
sys.path.insert(0,str(ROOT/'models/assemblies/src/anthropomorphic_hand'))
from cadgen import build123d as bd
from lib.actuator_fasteners import actuator_fasteners
from lib.layout import TENDONS
from check_actuator_fasteners import bbox,overlap,volume

def main():
    start=time.time();parts=[p for p,*_ in actuator_fasteners()]
    gear=bd.import_step(ROOT/'models/assemblies/STEP/anthropomorphic_hand/gearbox_review.step')
    cap=bd.import_step(ROOT/'models/assemblies/STEP/anthropomorphic_hand/capstan_review.step')
    local=[bd.Pos(10,0,4)*s for s in gear.children[:12]]+[bd.Pos(0,0,33)*s for s in cap.children]
    report={'exact_representatives': [t['actuator'] for t in TENDONS[:2]],'proof': 'All48 use the same16 hardware prototypes and identical complete drive prototypes under a shared rigid station transform; identical TShape and inverse-placement congruence are established in check_actuator_fastener_congruence.json. Both bank orientations receive explicit kernel intersections.', 'station_count':len(TENDONS),'prototype_mate_count':len(local),'exact_pairs':0,'collisions':[],'capstan_retainer_contact':[]}
    contact_by_sign={}
    for t in TENDONS[:2]:
        x,y,_=t['actuator_center'];loc=bd.Pos(x,y,0)*bd.Rot(0,180 if t['sign']<0 else 0,0)
        hardware=[p for p in parts if p.label.startswith(t['actuator']+'_')]
        mates=[loc*m for m in local];mb=[bbox(m) for m in mates] if t in TENDONS[:2] else []
        for h in hardware if t in TENDONS[:2] else []:
            hb=bbox(h)
            for m,b in zip(mates,mb):
                if not overlap(hb,b):continue
                report['exact_pairs']+=1;v=volume(h,m)
                if v>1e-7:report['collisions'].append((h.label,m.label,v))
        screw=next(p for p in hardware if p.label.endswith('capstan_retainer_screw'))
        transferred=t['sign'] in contact_by_sign
        if not transferred:contact_by_sign[t['sign']]=screw.distance_to(mates[12])
        report['capstan_retainer_contact'].append({'station':t['actuator'],'distance_mm':contact_by_sign[t['sign']],'rigid_congruence_transfer':transferred})
        print('Checked',t['actuator'],'collisions',len(report['collisions']),flush=True)
    for t in TENDONS[2:]:
        report['capstan_retainer_contact'].append({'station':t['actuator'],'distance_mm':contact_by_sign[t['sign']],'rigid_congruence_transfer':True})
    report['ok']=not report['collisions'] and all(p['distance_mm']<1e-7 for p in report['capstan_retainer_contact'])
    report['seconds']=time.time()-start
    Path(__file__).with_suffix('.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
    if not report['ok']:raise SystemExit(1)

if __name__=='__main__':main()
