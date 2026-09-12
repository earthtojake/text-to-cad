"""Physical seats and staged local removal of housing screws and split caps."""
import sys,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[4];sys.path.insert(0,str(ROOT/'models/assemblies/src/anthropomorphic_hand'))
from cadgen import read_step,build123d as bd
from lib.forearm_housing import _rail
HERE=Path(__file__).resolve().parent;STEP=ROOT/'models/assemblies/STEP/anthropomorphic_hand'
def leaves(n):return [s for c in n.children for s in leaves(c)] if n.children else [n]
def volume(a,b):
    x=a&b
    return 0. if x is None else x.volume
parts={s.label:s for s in leaves(read_step(STEP/'forearm_housing_review.step'))}
report={'seats':[],'removal':[],'failures':[]}
for side in ('left','right'):
    sign=-1 if side=='left' else 1;frame=parts[side+'_forearm_open_side_frame']
    rail=(bd.Rot(0,180,0)*_rail()) if sign<0 else _rail()
    for i in (1,2):
        cap=parts[f'{side}_forearm_rail_clamp_{i}_removable_cap']
        for n in (1,2):
            screw=parts[f'{side}_forearm_rail_clamp_{i}_M1p6_socket_screw_{n}']
            v=volume(bd.Pos(sign*.001,0,0)*screw,cap)
            report['seats'].append({'body':screw.label,'approach_overlap':v})
            if v<1e-7:report['failures'].append({'unseated':screw.label})
            for step in range(1,21):
                v=sum(volume(bd.Pos(-sign*step*.05,0,0)*screw,h) for h in (cap,frame,rail))
                report['removal'].append({'body':screw.label,'distance':step*.05,'overlap':v})
                if v>1e-7:report['failures'].append(report['removal'][-1])
        v=volume(bd.Pos(sign*.001,0,0)*cap,rail)
        report['seats'].append({'body':cap.label,'approach_overlap':v})
        if v<1e-7:report['failures'].append({'unseated':cap.label})
        for step in range(1,21):
            v=sum(volume(bd.Pos(-sign*step*.05,0,0)*cap,h) for h in (frame,rail))
            report['removal'].append({'body':cap.label,'distance':step*.05,'overlap':v})
            if v>1e-7:report['failures'].append(report['removal'][-1])
    for i in (1,2):
        for j in (1,2):
            anchor=parts[f'{side}_forearm_edge_{i}_tie_anchor_{j}']
            for n in (1,2):
                screw=parts[f'{side}_forearm_edge_{i}_tie_anchor_{j}_M1p2_socket_screw_{n}']
                v=volume(bd.Pos(-sign*.001,0,0)*screw,anchor)
                report['seats'].append({'body':screw.label,'approach_overlap':v})
                if v<1e-7:report['failures'].append({'unseated':screw.label})
report['ok']=not report['failures'];(HERE/'forearm_housing_seats.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'ok':report['ok'],'seats':len(report['seats']),'removal':len(report['removal']),'failures':report['failures']}))
sys.exit(0 if report['ok'] else 1)
