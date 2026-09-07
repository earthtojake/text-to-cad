"""Local DIP liner reliefs at the MCP outer rims, from all225 static packets.

The original complete bearing annuli fromR2.53 toR3.1 remain untouched. This
module does not attempt to cure the separate PIP/CMC inner-seat conflicts.
"""
import json
from pathlib import Path
from cadgen import build123d as bd,read_step
from .transport_guide import path_wire
from .finish import finish


def relieved_palm(which):
    base=Path(__file__).resolve().parents[3]/'STEP/anthropomorphic_hand'
    shape=read_step(base/('palm_frame_candidate_review.step' if which=='main' else 'palm_little_review.step'))
    rows=json.loads(Path(__file__).with_name('palm_rom_relief_paths.json').read_text())
    for row in rows:
        if row['body']!=which:continue
        finger=row['tendon'].split('_')[0]
        x,y={'index':(-36,101),'middle':(-12,105),'ring':(12,100),'little':(36,89)}[finger]
        radius=row['radius']+.13
        clip=bd.Pos(x,y,12.5)*bd.Box(16,16,6)
        protected=bd.Pos(x,y,12.5)*(bd.Cylinder(3.1,2)-bd.Cylinder(2.53,3))
        # Independent Bezier sweeps avoid a pipe-shell failure at a joined seam.
        tools=[]
        for segment in row['path']:
            edge=path_wire([segment]).edges()[0]
            ts=[i/100 for i in range(101) if edge.position_at(i/100).Z>9.0]
            if not ts:continue
            lo=max(0,min(ts)-.02);hi=min(1,max(ts)+.02)
            wire=bd.Wire([edge.trim(lo,hi)])
            if wire.distance_to(clip)>radius:continue
            section=bd.Plane(origin=wire.position_at(0),z_dir=wire.tangent_at(0))*bd.Circle(radius)
            tools.append(bd.sweep(section,path=wire,is_frenet=True))
            tools.extend(bd.Pos(*wire.position_at(t))*bd.Sphere(radius) for t in (0,1))
        for tool in tools:
            tool=tool & clip
            if not tool:continue
            intersection=tool&protected
            if intersection and sum(s.volume for s in intersection.solids())>1e-8:
                raise ValueError(('DIP relief enters protected bearing seat',which,row['tendon']))
            shape=shape-tool
            if not shape.is_valid or len(shape.solids())!=1:
                raise ValueError(('DIP relief lost connected frame',which,row['tendon']))
    label='palm_metacarpal_truss' if which=='main' else 'fifth_metacarpal_cupping_truss'
    return finish(shape.solids()[0],'aluminum',label)
