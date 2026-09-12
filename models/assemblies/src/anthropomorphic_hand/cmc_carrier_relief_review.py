"""Shallow, path-shaped wrist-guide saddle in the original CMC carrier rib."""
import json
from pathlib import Path
import numpy as np
from cadgen import step,build123d as bd
from lib.native_integration import frozen_bodies
from lib.transport_guide import path_wire
ROOT=Path(__file__).resolve().parents[2]

def local_pieces(path,center):
    lower=np.array(center)-2.;upper=np.array(center)+2.;out=[]
    def visit(seg,depth=0):
        if seg['kind']=='bezier':
            cp=np.asarray(seg['points']);lo=cp.min(0);hi=cp.max(0)
            if np.linalg.norm(np.maximum(0,np.maximum(lower-hi,lo-upper)))>.5:return
            if max(hi-lo)>1.5 and depth<16:
                levels=[cp]
                while len(levels[-1])>1:levels.append((levels[-1][:-1]+levels[-1][1:])/2)
                visit({'kind':'bezier','points':[a[0].tolist() for a in levels]},depth+1)
                visit({'kind':'bezier','points':[a[-1].tolist() for a in levels[::-1]]},depth+1)
                return
        out.append(seg)
    for seg in path:visit(seg)
    return out

@step(out='../../STEP/anthropomorphic_hand/cmc_carrier_relief_review.step',mesh_tolerance=.001,mesh_angular_tolerance=.01)
def cmc_carrier_relief_review():
    source=next(b for b in frozen_bodies(False) if b.name=='thumb_cmc_carrier')
    row=next(r for r in json.loads((ROOT/'validation/anthropomorphic_hand/secondary_hardware_diagnostic.json').read_text()) if r['body']==source.name)
    shape=source.shape;before=shape.volume
    for segment in local_pieces(row['path_neutral'],row['curve_point_neutral']):
        wire=path_wire([segment]);profile=bd.Plane(origin=wire.position_at(0),z_dir=wire.tangent_at(0))*bd.Circle(.50)
        cutter=bd.sweep(profile,path=wire,is_frenet=True)
        shape=shape-cutter
    assert shape.is_valid and len(shape.solids())==1
    shape.label=source.name;shape.color=source.shape.color;shape.cad_material=source.shape.cad_material
    (ROOT/'validation/anthropomorphic_hand/cmc_carrier_relief_frames.json').write_text(json.dumps([dict(name=source.name,frame=source.frame,system=source.system,kind=source.kind)],indent=2)+'\n')
    (ROOT/'validation/anthropomorphic_hand/cmc_carrier_relief_changes.json').write_text(json.dumps({'original_volume':before,'revised_volume':shape.volume,'removed_volume':before-shape.volume,'cutter_radius':.50,'unchanged_tendon_radius':.45,'contact_sample':'wrist_flexion_35'},indent=2)+'\n')
    return bd.Compound(label='CMC_carrier_with_wrist_guide_saddle',children=[shape])
if __name__=='__main__':cmc_carrier_relief_review()
