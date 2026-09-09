"""Local palm pockets for the context-clearing R2 thumb arm across225 poses."""
import hashlib,json
from pathlib import Path
import numpy as np
from cadgen import build123d as bd,step,report
from OCP.Bnd import Bnd_Box
from OCP.BRepBndLib import BRepBndLib
from lib.native_integration import ROOT
from lib.layout import assembled_transforms
from lib.assembly import matrix_location
from lib.phalanx_r5_boolean import common,cut
from lib.finish import finish
from lib.palm_seating_zones import seating_zones
from lib.guide_mounts import guide_end_registry
from hand_mechanical_candidate import native_parts

@step(out='../../STEP/anthropomorphic_hand/palm_thumb_arm_clearance_r11.step')
def palm_thumb_arm_clearance_r11():
    folder=ROOT/'STEP/anthropomorphic_hand';reports=ROOT/'validation/anthropomorphic_hand'
    oldpath=folder/'static_clearance_relief_review.step';armpath=folder/'thumb_reaction_arm_clearance_r2.step';manifestpath=reports/'final_static_route_packet_manifest.json'
    name='palm_metacarpal_truss';old=native_parts(oldpath)[name];arm=native_parts(armpath)['thumb_cmc_negative_yaw_outlet_structural_jaw_1']
    manifest=json.loads(manifestpath.read_text());samples=manifest['rows'];assert manifest['complete'] and len(samples)==225
    source=old;seen=set();changes=[]
    for sample in samples:
        fk=assembled_transforms(sample['pose']);relative=np.linalg.inv(fk['wrist_flexion'])@fk['thumb_cmc_abduction'];key=tuple(np.round(relative.ravel(),12))
        if key in seen:continue
        seen.add(key);tool=matrix_location(relative)*arm;hit=common(source,tool)
        if not hit.solids() or sum(s.volume for s in hit.solids())<=1e-7:continue
        report('Machining palm at '+sample['label'])
        box=Bnd_Box();BRepBndLib.AddOptimal_s(hit.wrapped,box,False,True);x0,y0,z0,x1,y1,z1=box.Get();d=.025
        pocket=bd.Pos((x0+x1)/2,(y0+y1)/2,(z0+z1)/2)*bd.Box(x1-x0+2*d,y1-y0+2*d,z1-z0+2*d)
        candidate=cut(source,pocket)
        assert len(candidate.solids())==1 and candidate.is_valid and candidate.volume>0,('pocket disconnects palm',sample['label'])
        remainder=common(candidate,tool);assert not remainder.solids() or sum(s.volume for s in remainder.solids())<=1e-7
        changes.append(dict(sample=sample['label'],pose=sample['pose'],contact_mm3=sum(s.volume for s in hit.solids()),contact_bounds_mm=[x0,y0,z0,x1,y1,z1],clearance_mm=d))
        source=candidate
    report('Checking protected palm mount zones')
    removed=cut(old,source);assert removed.solids() and not cut(source,old).faces()
    zones=[]
    for zone,shape in seating_zones():
        hit=common(removed,shape);v=sum(s.volume for s in hit.solids());gap=removed.distance_to(shape)
        zones.append(dict(zone=zone,intersection_mm3=v,gap_mm=gap,pass_=v<1e-7 and gap>.025))
    bb=removed.bounding_box();lo=np.array(tuple(bb.min));hi=np.array(tuple(bb.max))
    ends=[dict(name=e.name,bbox_gap_mm=float(np.linalg.norm(np.maximum(np.maximum(lo-np.asarray(e.point),np.asarray(e.point)-hi),0.)))) for e in guide_end_registry() if e.frame=='wrist_flexion']
    assert all(r['pass_'] for r in zones) and min(r['bbox_gap_mm'] for r in ends)>3.
    evidence=dict(scope=__doc__,changes=changes,construction_unique_relative_poses=len(seen),removed_material_mm3=removed.volume,protected_zones=zones,nearest_guide_ends=sorted(ends,key=lambda r:r['bbox_gap_mm'])[:8],input_sha256={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (Path(__file__),oldpath,armpath,manifestpath,Path(__file__).parent/'lib/palm_seating_zones.py')},pass_=True)
    (reports/'palm_thumb_arm_clearance_r11_build.json').write_text(json.dumps(evidence,indent=2)+'\n')
    return bd.Compound(label='palm_R11_thumb_arm_clearance',children=[finish(source.solids()[0],'aluminum',name)])

if __name__=='__main__':palm_thumb_arm_clearance_r11()
