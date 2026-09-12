"""Exact BRep terminal seating, release, placement and hardware motion checks."""
import sys,json,math,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[4]
sys.path.insert(0,str(ROOT/'models/assemblies/src/anthropomorphic_hand'))
from cadgen import build123d as bd
from cadgen.validity import _is_self_intersecting
from lib.drive_terminal import *
from lib.transport_guide import make_tendon
from lib.layout import FINGERS,assembled_transforms,finger_fan_matrix
from lib.assembly import matrix_location
from lib.joint_hardware import joint_hardware
OUT=Path(__file__).with_name('drive_terminal_check.json')
KINDS=('drive_pulley','drive_terminal_cover','drive_terminal_cover_screw','drive_terminal_ferrule','drive_terminal_bond_line','drive_pulley_grub_screw')


def vol(a,b):
    boxa=a.bounding_box();boxb=b.bounding_box()
    if any(getattr(boxa.max,k)<getattr(boxb.min,k)-1e-7 or getattr(boxb.max,k)<getattr(boxa.min,k)-1e-7 for k in 'XYZ'):return 0.
    return (a&b).volume


def main():
    start=time.monotonic();report={'strict':[],'seating':[],'capture':[],'hardware_motion':[],
        'withdrawal':[],'capstan_bond_seating':[],'end_release':[],'motion_seating':[],'pair_checks':0,'failures':[],'partial':True}
    def save():
        report['elapsed_seconds']=time.monotonic()-start
        OUT.write_text(json.dumps(report,indent=2)+'\n')
    rows=terminal_placements();print('Building registry',flush=True)
    capstan_bonds=capstan_bond_bodies();bodies=drive_terminal_bodies()+capstan_bonds;byname={b[0].label:b for b in bodies}
    print('Registry built',len(bodies),flush=True)
    for body,frame,system,kind in ([] if '--skip-strict' in sys.argv else bodies):
        si=_is_self_intersecting(body.wrapped)
        result={'name':body.label,'solid_count':len(body.solids()),'valid':body.is_valid,'self_intersection':si,'volume':body.volume}
        report['strict'].append(result)
        if not body.is_valid or len(body.solids())!=1 or si is not False:report['failures'].append(result)
    report['strict_check_mode']='native --every-placement separately' if '--skip-strict' in sys.argv else 'serial every placement'
    save()
    for row in rows:
        name=row['name'];rope=make_tendon([row['route']['path'][-1]],name+'_drive_wrap')
        parts={k:byname[name+'_'+k][0] for k in KINDS}
        f=parts['drive_terminal_ferrule'];s=parts['drive_pulley_grub_screw']
        result={'name':name,'rope_pulley':vol(rope,parts['drive_pulley'])+vol(rope,parts['drive_terminal_cover']),
                'rope_ferrule':vol(rope,f),'ferrule_pulley':sum(vol(f,parts[k]) for k in ('drive_pulley','drive_terminal_cover')),
                'screw_pulley':vol(s,parts['drive_pulley']),
                'rope_cover_screw':vol(rope,parts['drive_terminal_cover_screw']),
                'rope_bond_line':vol(rope,parts['drive_terminal_bond_line']),
                'bond_line_ferrule':vol(parts['drive_terminal_bond_line'],f)}
        report['seating'].append(result)
        if max(v for k,v in result.items() if k!='name')>1e-7:report['failures'].append(result)
        save()
    from lib.capstan import sweep_round,make_terminal_ferrule
    from lib.capstan_path import full_groove_path,prefix_length,path_length
    from lib.layout import TENDONS
    capstan_rope=sweep_round(prefix_length(full_groove_path(),.8),.30)
    capstan_ferrule=make_terminal_ferrule()
    for t,(bond,*_) in zip(TENDONS,capstan_bonds):
        x,y,_=t['actuator_center'];sign=t['sign']
        placement=bd.Pos(x,y,sign*4.)*(bd.Rot(0,0,0) if sign==1 else bd.Rot(0,180,0))*bd.Pos(0,0,29)
        result={'name':bond.label,'rope_overlap':vol(bond,placement*capstan_rope),'ferrule_overlap':vol(bond,placement*capstan_ferrule)}
        report['capstan_bond_seating'].append(result)
        if max(result['rope_overlap'],result['ferrule_overlap'])>1e-7:report['failures'].append(result)
        save()
    print('Seat',len(report['seating']),'failures',len(report['failures']),flush=True)
    for radius in (3.5,4.5,5.5,7.,11.):
        bore=3.03 if radius==11 else 1.03
        wheel,cover=make_terminal_pulley_parts(radius,bore)
        ferrule=make_driven_ferrule(radius);bond=make_driven_bond_line(radius);screw=make_cover_screw(radius);grub=make_pulley_grub_screw(bore)
        retracted=arc_tube(radius,.30,-2.,-.85,-60.,-1)
        result={'family':radius,'travel_mm':.85,'rope_ferrule_overlap':vol(retracted,ferrule),'rope_bond_overlap':vol(retracted,bond),'rope_bond_distance':retracted.distance_to(bond)}
        report['end_release'].append(result)
        if max(result['rope_ferrule_overlap'],result['rope_bond_overlap'])>1e-7 or result['rope_bond_distance']<.04:report['failures'].append(result)
        for axis in range(3):
            for sign in (-1,1):
                delta=[0.,0.,0.];delta[axis]=sign*.25
                overlap=sum(vol(a,bd.Pos(*delta)*ferrule) for a in (wheel,cover))
                result={'radius':radius,'axis':axis,'sign':sign,'capture_overlap':overlap}
                report['capture'].append(result)
                if overlap<1e-7:report['failures'].append(result)
        for step in range(1,41):
            z=step*.05;shift=bd.Pos(0,0,z)
            result={'radius':radius,'z':z,'screw':sum(vol(shift*screw,a) for a in (wheel,cover,ferrule)),
                    'cover_after_screw_removed':vol(shift*cover,wheel)+vol(shift*cover,ferrule),
                    'ferrule_after_cover_removed':vol(shift*ferrule,wheel),
                    'bond_after_rope_and_ferrule_removed':vol(shift*bond,wheel),
                    'inclined_grub':sum(vol(bd.Pos(z/math.sqrt(2),0,z/math.sqrt(2))*grub,a) for a in (wheel,cover))}
            report['withdrawal'].append(result)
            if max(v for k,v in result.items() if k not in ('radius','z'))>1e-7:report['failures'].append(result)
        # The seated screw shoulder must restrain the cover before withdrawal.
        overlap=vol(bd.Pos(0,0,.10)*cover,screw)
        if overlap<1e-7:report['failures'].append({'radius':radius,'cover_not_retained_by_screw':overlap})
        print('Release family',radius,'failures',len(report['failures']),flush=True);save()
    first=full_groove_path()[0];length=path_length([first])
    reverse={'kind':'bezier','points':list(reversed(first['points']))}
    trimmed=prefix_length([reverse],length-.85)[0]
    trimmed['points']=list(reversed(trimmed['points']))
    retracted=sweep_round([trimmed],.30);bond=make_capstan_bond_line()
    result={'family':'capstan','travel_mm':.85,'rope_ferrule_overlap':vol(retracted,capstan_ferrule),'rope_bond_overlap':vol(retracted,bond),'rope_bond_distance':retracted.distance_to(bond)}
    report['end_release'].append(result)
    if max(result['rope_ferrule_overlap'],result['rope_bond_overlap'])>1e-7 or result['rope_bond_distance']<.04:report['failures'].append(result)
    boxes=[s.bounding_box() for s,*_ in bodies]
    for i,(a,*_) in enumerate(bodies):
        for n,(b,*_) in enumerate(bodies[i+1:],i+1):
            report['pair_checks']+=1
            if any(getattr(boxes[i].max,k)<getattr(boxes[n].min,k)-1e-7 or getattr(boxes[n].max,k)<getattr(boxes[i].min,k)-1e-7 for k in 'XYZ'):continue
            overlap=vol(a,b)
            if overlap>1e-7:report['failures'].append({'a':a.label,'b':b.label,'neutral_overlap':overlap})
    save();print('Mutual pairs',report['pair_checks'],'failures',len(report['failures']),flush=True)
    if '--neutral-release-only' in sys.argv:
        report['partial']=False
        report['scope']='Strict/seating/capture/release/neutral mutual; target ROM is certified separately by drive_terminal_motion_check.py.'
        report['ok']=not report['failures'];save()
        return 0 if report['ok'] else 1
    fan={f.name:matrix_location(finger_fan_matrix(f)) for f in FINGERS}
    hardware=[]
    for body,frame,system,kind in joint_hardware():
        if system in fan:body=fan[system]*body
        hardware.append((body,frame,body.bounding_box()))
    for row in rows:
        j=row['joint'];moving=[byname[row['name']+'_'+kind][0] for kind in KINDS]
        center=(row['placement']*bd.Vertex(0,0,0)).center();radius=j.drive_radius+1.
        # Each hardware frame either stays fixed or rotates about this same
        # target axis. Distance to the pulley center therefore stays invariant.
        nearby=[(h,frame) for h,frame,box in hardware if sum(max(getattr(box.min,k)-getattr(center,k),0.,getattr(center,k)-getattr(box.max,k))**2 for k in 'XYZ')<=radius**2]
        angles=sorted(set([0.,*j.limits,*range(math.ceil(j.limits[0]/10)*10,math.floor(j.limits[1]/10)*10+1,10)]))
        for q in angles:
            fk=assembled_transforms({j.name:q});placed=[matrix_location(fk[j.name])*body for body in moving]
            arc=dict(row['route']['path'][-1]);arc['sweepDeg']+=q
            rope=make_tendon([arc])
            for body in placed:
                overlap=vol(rope,body)
                if overlap>1e-7:report['failures'].append({'name':row['name'],'q':q,'rope_overlap':overlap,'body':body.label})
            report['motion_seating'].append({'name':row['name'],'q':q})
            for h,frame in nearby:
                target=matrix_location(fk[frame])*h
                for body in placed:
                    overlap=vol(body,target)
                    if overlap>1e-7:report['failures'].append({'joint':j.name,'q':q,'a':body.label,'b':h.label,'overlap':overlap})
            report['hardware_motion'].append({'name':row['name'],'q':q,'nearby_hardware_count':len(nearby)})
        print(row['name'],'done; failures',len(report['failures']),flush=True);save()
    report['partial']=False;report['ok']=not report['failures'];save()
    print(json.dumps({'ok':report['ok'],'counts':{k:len(v) for k,v in report.items() if isinstance(v,list)},'seconds':report['elapsed_seconds']}),flush=True)
    return 0 if report['ok'] else 1

if __name__=='__main__':sys.exit(main())
