"""Native rib continuity, unchanged splice bores and source/export equality."""
import hashlib,json
from pathlib import Path
import numpy as np
from check_native_reported_contacts import native_shapes,sha,HERE
from radial_bank_arm_repair_review import make_radial_bank_arm
from cadgen import build123d as bd
from lib.guide_mounts import guide_end_registry
from lib.phalanx_r5_boolean import common,cut

def main():
    source=make_radial_bank_arm()
    folder=HERE.parents[1]/'STEP/anthropomorphic_hand';path=folder/'radial_bank_arm_repair_review.step'
    part=next(iter(native_shapes(path).values()));original_path=folder/'imported/rigid_clearance_inputs.step';old=native_shapes(original_path)
    assert len(part.solids())==1 and part.is_valid and part.volume>0
    forward=cut(source,part);backward=cut(part,source)
    equal=not forward.solids() and not backward.solids()
    bores=[]
    for e in guide_end_registry():
        if e.frame!='wrist_flexion' or not e.name.startswith('thumb_') or '_wrist_guide_outlet' not in e.name or not ('_mcp_' in e.name or '_ip_' in e.name):continue
        tool=bd.Plane(origin=e.point,z_dir=e.tangent).location*bd.Cylinder(.47,1.)
        hit=common(part,tool);v=sum(s.volume for s in hit.solids())
        bores.append(dict(name=e.name,obstruction_mm3=v,pass_=v<1e-7))
    assert len(bores)==6
    contacts=[]
    for n in ('thumb_cmc_abduction_negative_drive_pulley','thumb_cmc_abduction_positive_drive_pulley','thumb_cmc_abduction_negative_bushing'):
        hit=common(part,old[n]);v=sum(s.volume for s in hit.solids());contacts.append(dict(body=n,intersection_mm3=v))
    report={'scope':__doc__,'input_sha256':{str(p):sha(p) for p in (path,original_path,Path(__file__))},'native_volume_mm3':part.volume,'source_volume_mm3':source.volume,'source_minus_native_mm3':sum(s.volume for s in forward.solids()),'native_minus_source_mm3':sum(s.volume for s in backward.solids()),'source_native_equal':equal,'bores':bores,'remaining_interface_contacts':contacts,'pass':equal and all(r['pass_'] for r in bores)}
    (HERE/'radial_bank_arm_repair_local_check.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report),flush=True);assert report['pass']
if __name__=='__main__':main()
