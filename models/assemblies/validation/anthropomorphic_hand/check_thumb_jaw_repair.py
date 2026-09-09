"""Native reaction-arm continuity, interface bores and neutral pulley checks."""
import hashlib,json,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parents[1]/'src/anthropomorphic_hand'))
from cadgen import build123d as bd
from lib.phalanx_r5_boolean import common
from lib.layout import THUMB_CMC
from check_native_reported_contacts import native_shapes

def main():
    folder=HERE.parents[1]/'STEP/anthropomorphic_hand'
    path=folder/'thumb_cmc_negative_jaw_repair_review.step';original_path=folder/'imported/rigid_clearance_inputs.step'
    shapes=native_shapes(original_path);new=native_shapes(path)
    name='thumb_cmc_negative_yaw_outlet_structural_jaw_1';assert set(new)=={name}
    part=new[name];assert part.is_valid and len(part.solids())==1 and part.volume>0
    rows=[]
    for other in ['thumb_cmc_abduction_negative_drive_pulley','thumb_cmc_abduction_positive_drive_pulley','thumb_cmc_flexion_negative_drive_pulley']:
        hit=common(part,shapes[other]);v=hit.volume if hit.solids() else 0.
        rows.append(dict(body=other,intersection_mm3=v,pass_=v<1e-7))
    base=bd.Pos(*THUMB_CMC)*bd.Rot(0,0,45)
    holes=[(-.9,-3.275,-7.95,.22),(0,-3.5,-15.2,.32),(0,3.5,-15.2,.32)]
    bores=[]
    for x,y,z,r in holes:
        cutter=base*bd.Pos(x,y,z)*bd.Cylinder(r,3,rotation=(0,90,0))
        hit=common(part,cutter);v=hit.volume if hit.solids() else 0.
        bores.append(dict(center_local_mm=[x,y,z],radius_mm=r,obstruction_mm3=v,pass_=v<1e-7))
    report={'pass':all(r['pass_'] for r in rows) and all(r['pass_'] for r in bores),'scope':__doc__,'input_sha256':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (path,original_path,Path(__file__))},'body_volume_mm3':part.volume,'pulley_contacts':rows,'bores':bores}
    (HERE/'thumb_cmc_jaw_repair_local_check.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report),flush=True)

if __name__=='__main__':main()
