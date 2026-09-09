"""Exact intersections, contact topology, and all48 rigid-placement congruence."""
from pathlib import Path
import sys,json,hashlib,time
ROOT=Path(__file__).resolve().parents[4]
SRC=ROOT/'models/assemblies/src/anthropomorphic_hand'
sys.path.insert(0,str(SRC))
from cadgen import build123d as bd
from lib.actuator_fasteners import actuator_fasteners
from lib.layout import TENDONS
from lib.motor import make_motor_case,make_motor_endcap,make_motor_shaft
from lib.gearbox import make_gearbox_housing,make_gearbox_spindle
from lib.tension_cartridge import make_tension_cartridge
from lib.wrist import make_wrist_fixed_fork


def bbox(s):
    b=s.bounding_box();return tuple(b.min),tuple(b.max)

def overlap(a,b):return all(min(a[1][k],b[1][k])-max(a[0][k],b[0][k])>1e-7 for k in range(3))

def volume(a,b):
    c=a.intersect(b)
    return sum(s.volume for s in c.solids()) if c is not None else 0.

def run():
    start=time.time();parts=[p for p,*_ in actuator_fasteners()]
    report={'body_count':len(parts),'sources':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [SRC/'lib/actuator_fasteners.py',SRC/'lib/motor.py',SRC/'lib/forearm_frame.py',SRC/'lib/tension_cartridge.py']},'own_collisions':[],'mate_collisions':[],'congruence':[]}
    print('Generated',len(parts),'hardware bodies',flush=True)
    boxes=[bbox(s) for s in parts];exact=0
    for i,p in enumerate(parts):
        for j in range(i):
            if not overlap(boxes[i],boxes[j]):continue
            exact+=1;v=volume(p,parts[j])
            if v>1e-7:report['own_collisions'].append((p.label,parts[j].label,v))
    report['own_exact_pairs']=exact
    print('Own pairs',exact,'collisions',len(report['own_collisions']),flush=True)
    # Kernel-common with actual freshly built motor parts and torque springs.
    spring=make_tension_cartridge();case=make_motor_case();endcap=make_motor_endcap();shaft=make_motor_shaft()
    housing=make_gearbox_housing();spindle=make_gearbox_spindle()
    localmates=spring+[bd.Pos(0,0,4)*s for s in (case,endcap,shaft,housing,spindle)]
    first=None;exact=0
    for t in TENDONS:
        x,y,_=t['actuator_center'];sign=t['sign'];placement=bd.Pos(x,y,0)*bd.Rot(0,180 if sign<0 else 0,0)
        selected=[p for p in parts if p.label.startswith(t['actuator']+'_')]
        # Use actual inverse rigid transformation for geometric congruence.
        restored=[placement.inverse()*p for p in selected]
        if first is None:first=restored
        mismatches=[]
        for i,(a,b) in enumerate(zip(restored,first)):
            if abs(a.volume-b.volume)>1e-7 or max(abs(u-v) for u,v in zip(tuple(a.center()),tuple(b.center())))>1e-7:mismatches.append(i)
        report['congruence'].append({'station':t['actuator'],'count':len(selected),'mismatches':mismatches})
        mates=[placement*m for m in localmates];mb=[bbox(m) for m in mates]
        for p in selected:
            pb=bbox(p)
            for m,bb in zip(mates,mb):
                if not overlap(pb,bb):continue
                exact+=1;v=volume(p,m)
                if v>1e-7:report['mate_collisions'].append((p.label,m.label,v))
        print('Station',t['actuator'],'checked',flush=True)
    report['actuator_mate_exact_pairs']=exact
    # Reimport authoritative chassis review to avoid reconstructing a costly
    # unchanged chassis. The actual fork is regenerated from its current source.
    frame=bd.import_step(ROOT/'models/assemblies/STEP/anthropomorphic_hand/forearm_frame_review.step')
    frameparts=list(frame.solids());fork=make_wrist_fixed_fork()
    mates=frameparts+[fork];mb=[bbox(m) for m in mates];exact=0
    contact=[]
    groups=[(t['actuator'],bd.Compound(children=[p for p in parts if p.label.startswith(t['actuator']+'_')])) for t in TENDONS]
    groups += [(p.label,p) for p in parts if not p.label.startswith('actuator_')]
    for group_name,p in groups:
        p.label=group_name;pb=bbox(p)
        for i,(m,bb) in enumerate(zip(mates,mb)):
            if overlap(pb,bb):
                exact+=1;v=volume(p,m)
                if v>1e-7:report['mate_collisions'].append((p.label,'frame_or_fork_'+str(i),v))
        print('Structure',group_name,flush=True)
        if p.label.startswith(('wrist_frame','rear_')):
            distances=[p.distance_to(m) for m in mates]
            contact.append({'part':p.label,'nearest_structural_body_mm':min(distances)})
    report['structure_exact_pairs']=exact;report['structure_distances']=contact
    report['seconds']=time.time()-start
    report['ok']=not report['own_collisions'] and not report['mate_collisions'] and all(r['count']==16 and not r['mismatches'] for r in report['congruence'])
    target=Path(__file__).with_suffix('.json');target.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ('sources','congruence','structure_distances')},indent=2),flush=True)
    if not report['ok']:raise SystemExit(1)

if __name__=='__main__':run()
