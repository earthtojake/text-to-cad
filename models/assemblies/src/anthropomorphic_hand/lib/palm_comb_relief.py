"""Local moving-comb pockets from all225 authored static poses."""
import json,numpy as np
from pathlib import Path
from cadgen import build123d as bd,read_step
from .layout import assembled_transforms
from .assembly import matrix_location
from .finish import finish

def leaves(s):return [p for c in s.children for p in leaves(c)] if s.children else [s]
def relieved_palm(which):
    root=Path(__file__).resolve().parents[3];base=root/'STEP/anthropomorphic_hand';val=root/'validation/anthropomorphic_hand'
    shape=read_step(base/('palm_main_full_rom_review.step' if which=='main' else 'palm_little_full_rom_review.step'))
    meta={r['name']:r for r in json.loads((val/'phalanx_comb_clearance_frames.json').read_text())}
    parts=[s for s in leaves(read_step(base/'phalanx_comb_clearance_review.step')) if 'mcp_outlet' in s.label and ('little_' in s.label)==(which=='little')]
    centers={'index':(-36,101),'middle':(-12,105),'ring':(12,100),'little':(36,89)}
    clips={f:bd.Pos(x,y,12.5)*bd.Cylinder(4.8,6) for f,(x,y) in centers.items()}
    bands={f:bd.Pos(x,y,12.5)*(bd.Cylinder(2.3,2)-bd.Cylinder(1.83,3)) for f,(x,y) in centers.items()}
    tools=[];cache=set()
    for i,row in enumerate(json.loads((val/'static_route_packet_manifest.json').read_text())['rows']):
        fk=assembled_transforms(row['pose']);inv=np.linalg.inv(fk['wrist_flexion' if which=='main' else 'palm_cup'])
        for part in parts:
            f=part.label.split('_')[0];m=inv@fk[meta[part.label]['frame']];key=(part.label,tuple(np.round(m.flatten(),7)))
            if key in cache:continue
            cache.add(key);p=bd.Compound.cast(part.wrapped.Moved(matrix_location(m).wrapped));clip=clips[f]
            if p.distance_to(clip)>.12:continue
            c=p.center();enlarged=bd.Pos(*c)*((bd.Pos(*(-c))*p).scale(1.04));cut=p.fuse(enlarged)&clip
            if not cut or not cut.solids():continue
            common=cut&bands[f]
            if common and sum(s.volume for s in common.solids())>1e-7:raise ValueError(('comb reaches bearing band',row['label'],part.label))
            tools.append(cut);print('COMBTOOL',which,row['label'],part.label,len(tools),flush=True)
    if which=='little':
        # Negative flange lies outside the complete -17.5..-15.5 sleeve seat.
        tools.append(bd.Pos(36,89,-18.5)*bd.Cylinder(2.8,2))
    shape=shape.cut(*tools);ss=sorted(shape.solids(),key=lambda s:s.volume,reverse=True);print('CHIPS',which,[s.volume for s in ss],flush=True)
    shape=ss[0]
    if sum(s.volume for s in ss[1:])>10:raise ValueError('large disconnected comb relief')
    for f,band in bands.items():
        if (f=='little')!=(which=='little'):continue
        missing=band-shape
        if missing and sum(s.volume for s in missing.solids())>1e-6:raise ValueError(('detached seat after comb relief',f))
    if not shape.is_valid or len(shape.solids())!=1:raise ValueError('invalid comb-relieved palm')
    return finish(shape,'aluminum','palm_metacarpal_truss' if which=='main' else 'fifth_metacarpal_cupping_truss')
