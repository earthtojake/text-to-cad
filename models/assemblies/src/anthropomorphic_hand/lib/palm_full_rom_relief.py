"""Native full225-pose palm relief and four narrower positive MCP seats.

Complete R1.83..2.30 bearing annuli remain, with original rear rib landings.
The separately relocated positive CMC seat is added in its own revision.
"""
import json
from pathlib import Path
from cadgen import build123d as bd,read_step
from .transport_guide import path_wire
from .finish import finish


def relieved_palm(which):
    base=Path(__file__).resolve().parents[3]/'STEP/anthropomorphic_hand'
    shape=read_step(base/('imported/palm_frame_integration.step' if which=='main' else 'palm_little_review.step'))
    centers=[(-36,101),(-12,105),(12,100)] if which=='main' else [(36,89)]
    protected=[]
    for x,y in centers:
        shape=shape.fuse(bd.Pos(x,y,12.5)*(bd.Cylinder(3.05,2)-bd.Cylinder(1.83,3)))
        protected.append(bd.Pos(x,y,12.5)*(bd.Cylinder(2.30,2)-bd.Cylinder(1.83,3)))
    rows=json.loads(Path(__file__).with_name('palm_full_rom_relief_paths.json').read_text())
    alltools=[]
    for i,row in enumerate(rows):
        if row['body']!=which or row['gap']>.055 or row['tendon'].startswith('thumb_'):continue
        radius=row['radius']+.08
        if 'cup_reaction' in row['group']:
            # Both actual contact zones are below the cup bearing bands.
            clip=bd.Pos(18,49,-9)*bd.Box(11,20,7)
        else:
            finger=row['tendon'].split('_')[0]
            if finger not in ('index','middle','ring','little'):continue
            x,y={'index':(-36,101),'middle':(-12,105),'ring':(12,100),'little':(36,89)}[finger]
            clip=bd.Pos(x,y,12.5)*bd.Box(16,16,6)
        box=clip.bounding_box(optimal=False)
        for segment in row['path']:
            edge=path_wire([segment]).edges()[0]
            ts=[]
            for j in range(101):
                p=edge.position_at(j/100)
                if all(box.min.to_tuple()[a]-radius<=p.to_tuple()[a]<=box.max.to_tuple()[a]+radius for a in range(3)):ts.append(j/100)
            if not ts:continue
            lo=max(0,min(ts)-.02);hi=min(1,max(ts)+.02)
            wire=bd.Wire([edge.trim(lo,hi)])
            section=bd.Plane(origin=wire.position_at(0),z_dir=wire.tangent_at(0))*bd.Circle(radius)
            tools=[bd.sweep(section,path=wire,is_frenet=True)]
            tools.extend(bd.Pos(*wire.position_at(t))*bd.Sphere(radius) for t in (0,1))
            for tool in tools:
                tool=tool & clip
                if not tool:continue
                for band in protected:
                    if tool.distance_to(band)>.001:continue
                    cut=tool&band
                    if cut and sum(s.volume for s in cut.solids())>1e-8:raise ValueError(('protected seat',row['group'],row['sample']))
                alltools.append(tool)
        print('TOOL',which,i,row['group'],len(alltools),flush=True)
    # A single Boolean avoids repeatedly rebuilding the large imported frame.
    shape=shape.cut(*alltools)
    solids=sorted(shape.solids(),key=lambda s:s.volume,reverse=True)
    print('SOLIDS',which,[s.volume for s in solids],flush=True)
    if len(solids)>1:
        shape=solids[0]
        for band in protected:
            missing=band-shape
            if missing and sum(s.volume for s in missing.solids())>1e-6:raise ValueError(('detached bearing seat',which,band.center()))
        if sum(s.volume for s in solids[1:])>10:raise ValueError(('large detached frame pieces',which,[s.volume for s in solids]))
    if not shape.is_valid or len(shape.solids())!=1:raise ValueError(('disconnected palm',which,len(shape.solids())))
    print('CUT COMPLETE',which,len(alltools),flush=True)
    label='palm_metacarpal_truss' if which=='main' else 'fifth_metacarpal_cupping_truss'
    return finish(shape.solids()[0],'aluminum',label)
