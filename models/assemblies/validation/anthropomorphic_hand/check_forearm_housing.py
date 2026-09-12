"""Exact housing fit plus conservative complete-curve route envelopes."""
import sys,json,math,time
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[4]
sys.path.insert(0,str(ROOT/'models/assemblies/src/anthropomorphic_hand'))
from cadgen import read_step,build123d as bd
from lib.layout import TENDONS,JOINT_BY_NAME,assembled_transforms
from lib.forearm_routing import forearm_route
from lib.neutral_routes import NEUTRAL_ROUTES
from lib.transport_guide import path_wire
from lib.wrist import make_wrist_fixed_fork,make_wrist_yaw_carrier,make_wrist_palm_cradle,make_wrist_bushings
from lib.assembly import matrix_location

HERE=Path(__file__).resolve().parent
STEP=ROOT/'models/assemblies/STEP/anthropomorphic_hand'

def leaves(n):return [s for c in n.children for s in leaves(c)] if n.children else [n]
_BOUNDS={}
def bounds(b):
    # Keep a strong reference: transformed temporary shapes must not reuse an
    # earlier object's cached bounds if Python recycles its numeric identity.
    key=id(b)
    if key not in _BOUNDS:
        from OCP.Bnd import Bnd_Box
        from OCP.BRepBndLib import BRepBndLib
        q=Bnd_Box();BRepBndLib.Add_s(b.wrapped,q,False);values=q.Get()
        _BOUNDS[key]=(b,(np.asarray(values[:3]),np.asarray(values[3:])))
    return _BOUNDS[key][1]
def gap(a,b):return float(np.linalg.norm(np.maximum(np.maximum(a[0]-b[1],b[0]-a[1]),0)))
def overlap(a,b):
    if gap(bounds(a),bounds(b))>1e-7:return 0.
    common=a&b
    return 0. if common is None else common.volume
def curve_bounds(s):
    if s['kind']=='arc':
        c=np.asarray(s['center']);v=np.asarray(s['start'])-c;a=np.asarray(s['axis']);r=np.linalg.norm(v)
        e=r*np.sqrt(np.maximum(0,1-a*a));return c-e,c+e
    p=np.asarray(s['points'] if s['kind']=='bezier' else [s['start'],s['end']]);return p.min(0),p.max(0)

def main():
    start=time.monotonic();body=leaves(read_step(STEP/'forearm_housing_review.step'))
    assert len(body)==42 and len({s.label for s in body})==42
    report={'ok':False,'partial':True,'occurrences':42,'mutual_pairs':0,'host_pairs':0,'route_segments':0,'exact_curve_distances':0,'minimum_route_clearance':1e9,'wrist_hardware_poses':0,'failures':[]}
    def save():
        report['elapsed_seconds']=time.monotonic()-start;(HERE/'forearm_housing_check.json').write_text(json.dumps(report,indent=2)+'\n')
    for i,a in enumerate(body):
        for b in body[i+1:]:
            report['mutual_pairs']+=1;v=overlap(a,b)
            if v>1e-7:report['failures'].append({'a':a.label,'b':b.label,'overlap':v})
    save();print('Mutual',report['mutual_pairs'],'failures',len(report['failures']),flush=True)
    for filename,count in [('forearm_mount_system_review.step',110),('actuator_fasteners_review.step',824)]:
        host=leaves(read_step(STEP/filename));assert len(host)==count
        for a in body:
            for b in host:
                report['host_pairs']+=1;v=overlap(a,b)
                if v>1e-7:report['failures'].append({'a':a.label,'host':b.label,'overlap':v})
        save();print('Host',filename,'failures',len(report['failures']),flush=True)
    bb=[bounds(s) for s in body]
    def routes(rows,tag):
        for row in rows:
            for s in row['path']:
                cb=curve_bounds(s);report['route_segments']+=1
                for a,ab in zip(body,bb):
                    clearance=gap(cb,ab)-.30
                    if clearance<.001:
                        clearance=path_wire([s]).distance_to(a)-.30;report['exact_curve_distances']+=1
                    report['minimum_route_clearance']=min(report['minimum_route_clearance'],clearance)
                    if clearance<1e-7:report['failures'].append({'route':row['name'],'case':tag,'body':a.label,'surface_clearance':clearance})
    routes(NEUTRAL_ROUTES,'neutral48');save();print('Neutral paths failures',len(report['failures']),flush=True)
    for q in np.linspace(-5*math.pi,5*math.pi,21):routes([forearm_route(t,float(q)) for t in TENDONS],f'capstan_{q}')
    report['capstan_rotations']=21;report['capstan_routes']=1008;save();print('Capstan range done',flush=True)
    packets=json.loads((HERE/'wrist_mount_repaired_packets.json').read_text())['samples']
    for p in packets:routes(p['routes'],str(p['pose']))
    report['wrist_route_packets']=len(packets);save()
    hardware=[]
    for s in leaves(read_step(STEP/'wrist_review.step')):
        if s.label=='wrist_fixed_bearing_fork' or s.label.startswith('wrist_yaw_bushing_'):frame='forearm'
        elif s.label=='wrist_yaw_carrier' or s.label.startswith('wrist_flex_bushing_'):frame='wrist_abduction'
        elif s.label=='wrist_palm_cradle':frame='wrist_flexion'
        else:continue
        hardware.append((s,frame))
    assert len(hardware)==7
    poses=[{}]
    for joint in ('wrist_abduction','wrist_flexion'):
        lo,hi=JOINT_BY_NAME[joint].limits
        poses.extend({joint:q} for q in sorted({lo,hi,*range(math.ceil(lo/10)*10,math.floor(hi/10)*10+1,10)}))
    for pose in poses:
        fk=assembled_transforms(pose)
        for h,frame in hardware:
            h=matrix_location(fk[frame])*h
            for a in body:
                v=overlap(a,h)
                if v>1e-7:report['failures'].append({'pose':pose,'a':a.label,'wrist':h.label,'overlap':v})
        report['wrist_hardware_poses']+=1
    report['partial']=False;report['ok']=not report['failures'];save();print(json.dumps(report),flush=True)
    return 0 if report['ok'] else 1

if __name__=='__main__':sys.exit(main())
