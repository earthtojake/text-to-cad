"""Parallel exact sweep of all 434 target-joint route/hardware poses.

Loads the frozen native STEP once per worker and preserves every original
Boolean test. The prior seating/release report is extended, never inferred.
"""
import sys,json,math,time,multiprocessing
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor,as_completed
ROOT=Path(__file__).resolve().parents[4]
sys.path.insert(0,str(ROOT/'models/assemblies/src/anthropomorphic_hand'))
from cadgen import build123d as bd,read_step
from lib.drive_terminal import terminal_placements
from lib.layout import FINGERS,assembled_transforms,finger_fan_matrix
from lib.assembly import matrix_location
from lib.joint_hardware import joint_hardware
from lib.transport_guide import make_tendon
KINDS=('drive_pulley','drive_terminal_cover','drive_terminal_cover_screw','drive_terminal_ferrule','drive_terminal_bond_line','drive_pulley_grub_screw')
_CONTEXT=None


def vol(a,b):
    boxa=a.bounding_box();boxb=b.bounding_box()
    if any(getattr(boxa.max,k)<getattr(boxb.min,k)-1e-7 or getattr(boxb.max,k)<getattr(boxa.min,k)-1e-7 for k in 'XYZ'):return 0.
    return (a&b).volume


def initialize():
    global _CONTEXT
    root=read_step(ROOT/'models/assemblies/STEP/anthropomorphic_hand/drive_terminal_placements.step')
    def leaves(node):return [s for c in node.children for s in leaves(c)] if node.children else [node]
    byname={p.label:p for p in leaves(root)}
    assert len(byname)==336
    rows=terminal_placements();fan={f.name:matrix_location(finger_fan_matrix(f)) for f in FINGERS}
    hardware=[]
    for body,frame,system,kind in joint_hardware():
        if system in fan:body=fan[system]*body
        hardware.append((body,frame,body.bounding_box()))
    _CONTEXT=(rows,byname,hardware)


def check_route(index):
    rows,byname,hardware=_CONTEXT;row=rows[index];j=row['joint']
    moving=[byname[row['name']+'_'+kind] for kind in KINDS]
    center=(row['placement']*bd.Vertex(0,0,0)).center();radius=j.drive_radius+1.
    nearby=[(h,frame) for h,frame,box in hardware if sum(max(getattr(box.min,k)-getattr(center,k),0.,getattr(center,k)-getattr(box.max,k))**2 for k in 'XYZ')<=radius**2]
    angles=sorted(set([0.,*j.limits,*range(math.ceil(j.limits[0]/10)*10,math.floor(j.limits[1]/10)*10+1,10)]))
    result={'name':row['name'],'motion_seating':[],'hardware_motion':[],'failures':[]}
    for q in angles:
        fk=assembled_transforms({j.name:q});placed=[matrix_location(fk[j.name])*body for body in moving]
        arc=dict(row['route']['path'][-1]);arc['sweepDeg']+=q;rope=make_tendon([arc])
        max_overlap=0.
        for body in placed:
            overlap=vol(rope,body);max_overlap=max(max_overlap,overlap)
            if overlap>1e-7:result['failures'].append({'name':row['name'],'q':q,'rope_overlap':overlap,'body':body.label})
        result['motion_seating'].append({'name':row['name'],'q':q,'maximum_overlap':max_overlap})
        max_overlap=0.
        for h,frame in nearby:
            target=matrix_location(fk[frame])*h
            for body in placed:
                overlap=vol(body,target);max_overlap=max(max_overlap,overlap)
                if overlap>1e-7:result['failures'].append({'joint':j.name,'q':q,'a':body.label,'b':h.label,'overlap':overlap})
        result['hardware_motion'].append({'name':row['name'],'q':q,'nearby_hardware_count':len(nearby),'maximum_overlap':max_overlap})
    return result


def main():
    out=Path(__file__).with_name('drive_terminal_motion_check.json');start=time.monotonic()
    report={'partial':True,'ok':False,'source':'frozen drive_terminal_placements.step','motion_seating':[],'hardware_motion':[],'failures':[],'completed_routes':[]}
    def save():
        report['elapsed_seconds']=time.monotonic()-start;out.write_text(json.dumps(report,indent=2)+'\n')
    with ProcessPoolExecutor(max_workers=8,mp_context=multiprocessing.get_context('spawn'),initializer=initialize) as pool:
        futures=[pool.submit(check_route,i) for i in range(48)]
        for future in as_completed(futures):
            r=future.result();report['completed_routes'].append(r['name'])
            for k in ('motion_seating','hardware_motion','failures'):report[k].extend(r[k])
            save();print(r['name'],'done; completed',len(report['completed_routes']),'failures',len(report['failures']),flush=True)
    report['partial']=False;report['ok']=not report['failures'];save()
    print(json.dumps({k:len(v) if isinstance(v,list) else v for k,v in report.items()}),flush=True)
    return 0 if report['ok'] else 1

if __name__=='__main__':sys.exit(main())
