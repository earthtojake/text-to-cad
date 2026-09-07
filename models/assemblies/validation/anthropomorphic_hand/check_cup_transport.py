"""Independent analytic and actual-body gate for cup reaction liner candidates."""
import json,sys
from pathlib import Path
import numpy as np
from scipy.spatial import cKDTree
from cadgen import build123d as bd
from OCP.gp import gp_Trsf
from lib.cup_transport import cup_packet,rotation,CUP_ORIGIN
from lib.path_analysis import path_length,path_min_radius,sample_path
from lib.transport_guide import path_wire
from lib.pulley import make_pulley
from check_middle_hardware_paths import bbox_gap

if __name__=='__main__':
    assembly=bd.import_step('models/assemblies/STEP/anthropomorphic_hand/palm_frame_review.step')
    children=list(assembly.children)
    print([(p.label,p.volume) for p in children],flush=True)
    fixed=next(p for p in children if 'palm_metacarpal' in p.label)
    moving=list(bd.import_step('models/assemblies/STEP/anthropomorphic_hand/palm_little_review.step').children)[0]
    base=[('palm',False,fixed),('little_metacarpal',True,moving),('cup_shaft',False,bd.Pos(22,55,0)*bd.Cylinder(1,40,rotation=(90,0,0)))]
    for y in (45.,47.):base.append((f'cup_drive_{y}',False,bd.Pos(22,y,0)*bd.Rot(90,0,0)*make_pulley(7.)))
    samples=[float(v) for v in sys.argv[1:] if not v.startswith('--')] or list(range(0,26,5))
    report={'scope':[s[0] for s in base],'rows':[],'pass':False}
    out=Path(__file__).with_name('cup_transport_report.json')
    for q in samples:
        row={'angle_deg':q};packet=(json.loads(Path(__file__).with_name(f'cup_candidate_{q:g}.json').read_text()) if '--saved' in sys.argv else cup_packet(q));clouds=[sample_path(r['path'],.025) for r in packet]
        row['minimum_radius_mm']=min(path_min_radius(r['path']) for r in packet)
        row['maximum_length_error_mm']=max(abs(path_length(r['path'])-r['length']) for r in packet)
        row['minimum_mutual_gap_lower_bound_mm']=min(float(cKDTree(clouds[i]).query(clouds[j],workers=1)[0].min())-.025-.9 for i in range(len(packet)) for j in range(i+1,len(packet)))
        r=rotation(q);matrix=np.eye(4);matrix[:3,:3]=r;matrix[:3,3]=CUP_ORIGIN-r@CUP_ORIGIN
        tr=gp_Trsf();tr.SetValues(*matrix[:3,:].ravel().tolist());loc=bd.Location(tr)
        bodies=[(name,loc*solid if moves else solid) for name,moves,solid in base]
        bounds={name:solid.bounding_box() for name,solid in bodies}
        collisions=[];tested=0
        for route in packet:
            wire=path_wire(route['path']);wb=wire.bounding_box()
            for name,solid in bodies:
                if bbox_gap(wb,bounds[name])>.55:continue
                dist=wire.distance_to(solid);tested+=1
                if dist<.45-1e-7:collisions.append({'tendon':route['tendon'],'solid':name,'centerline_distance_mm':dist,'clearance_mm':dist-.45})
        row['collisions']=collisions;row['exact_body_distances']=tested
        row['pass']=not collisions and row['minimum_radius_mm']>=3.5 and row['maximum_length_error_mm']<1e-8 and row['minimum_mutual_gap_lower_bound_mm']>=0
        report['rows'].append(row);out.write_text(json.dumps(report,indent=2)+'\n')
        Path(__file__).with_name(f'cup_packet_{q:g}.json').write_text(json.dumps(packet,indent=2)+'\n')
        print(json.dumps(row),flush=True)
    report['pass']=all(r['pass'] for r in report['rows']);out.write_text(json.dumps(report,indent=2)+'\n')
    if not report['pass']:raise SystemExit(1)
