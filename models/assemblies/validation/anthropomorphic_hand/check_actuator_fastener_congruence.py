"""Prove each station reuses the same16 topology objects with identical local poses."""
from pathlib import Path
import sys,json,hashlib
ROOT=Path(__file__).resolve().parents[4]
SRC=ROOT/'models/assemblies/src/anthropomorphic_hand'
sys.path.insert(0,str(SRC))
from cadgen import build123d as bd
from lib.actuator_fasteners import actuator_fasteners
from lib.layout import TENDONS

def main():
    parts=[p for p,*_ in actuator_fasteners()];reference=None;rows=[]
    for t in TENDONS:
        x,y,_=t['actuator_center'];station=bd.Pos(x,y,0)*bd.Rot(0,180 if t['sign']<0 else 0,0)
        selected=[p for p in parts if p.label.startswith(t['actuator']+'_')]
        restored=[station.inverse()*p for p in selected]
        if reference is None:reference=restored
        errors=[];partners=0;max_error=0.
        for i,(a,b) in enumerate(zip(restored,reference)):
            partner=a.wrapped.IsPartner(b.wrapped)
            partners+=int(partner)
            av=[v for xyz in tuple(a.location) for v in xyz];bv=[v for xyz in tuple(b.location) for v in xyz]
            delta=max(abs(u-v) for u,v in zip(av,bv));max_error=max(max_error,delta)
            if not partner or delta>1e-8:errors.append(i)
        rows.append({'station':t['actuator'],'count':len(restored),'identical_topology_objects':partners,'max_local_pose_delta':max_error,'errors':errors})
    result={'ok':all(r['count']==16 and r['identical_topology_objects']==16 and not r['errors'] for r in rows),'station_count':len(rows),'occurrences_proven':sum(r['count'] for r in rows),'proof':'TopoDS_Shape.IsPartner proves each paired occurrence references the identical TShape; inverse station transforms then prove identical local translation and orientation to1e-8. Rigid transformation preserves intersections and distances against co-transformed drive prototypes.','sources':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (SRC/'lib/actuator_fasteners.py',SRC/'lib/layout.py')},'stations':rows}
    Path(__file__).with_suffix('.json').write_text(json.dumps(result,indent=2)+'\n')
    print(result['ok'],result['station_count'],result['occurrences_proven'])
    if not result['ok']:raise SystemExit(1)

if __name__=='__main__':main()
