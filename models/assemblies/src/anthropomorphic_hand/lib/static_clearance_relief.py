"""Explicit machined clearances; joint and tendon datums remain unchanged.

Only the named support is cut. Shafts, bearings, pulley profiles and guide
endpoints keep their authored geometry. Failed/disconnected cuts are rejected.
This candidate still requires attachment, full-assembly and tendon checks.
"""
import hashlib,json
from pathlib import Path
import numpy as np
from cadgen import build123d as bd,read_step
from lib.native_integration import leaves
from lib.assembly import matrix_location
from lib.layout import assembled_transforms
from lib.finish import finish

ROOT=Path(__file__).resolve().parents[3]
PAIRS=[
 ('fifth_metacarpal_cupping_truss','little_cup_fixed_bank_-1_structural_1'),
 ('little_cup_child_bank_structural','palm_cup_keyed_shaft'),
 ('palm_metacarpal_truss','little_cup_child_bank_structural'),
 ('palm_metacarpal_truss','thumb_cmc_abduction_palmar_stub_keyed_shaft'),
 ('palm_metacarpal_truss','thumb_cmc_abduction_positive_bushing'),
 ('palm_metacarpal_truss','thumb_cmc_flexion_positive_drive_pulley'),
 ('palm_metacarpal_truss','thumb_cmc_negative_yaw_outlet_structural_jaw_1'),
 ('palm_metacarpal_truss','thumb_cmc_positive_yaw_outlet_M0p4_pinch_screw'),
 ('ring_palm_bank_structural_body','ring_mcp_negative_yaw_outlet_structural_jaw_1'),
 ('thumb_cmc_yaw_drive_1_host_cap','thumb_cmc_abduction_negative_bushing'),
 ('thumb_radial_shared_guide_bank_structural','thumb_cmc_abduction_negative_bushing'),
 ('thumb_cmc_negative_yaw_outlet_structural_jaw_1','thumb_cmc_abduction_negative_drive_pulley'),
 ('thumb_cmc_yaw_drive_-1_liner_cap','thumb_cmc_abduction_negative_drive_pulley'),
 ('thumb_cmc_yaw_drive_-1_structural_2','thumb_cmc_abduction_negative_drive_pulley'),
 ('thumb_radial_shared_guide_bank_structural','thumb_cmc_abduction_negative_drive_pulley'),
 ('thumb_cmc_negative_yaw_outlet_structural_jaw_1','thumb_cmc_abduction_positive_drive_pulley'),
 ('thumb_cmc_yaw_drive_1_liner_cap','thumb_cmc_abduction_positive_drive_pulley'),
 ('thumb_radial_shared_guide_bank_structural','thumb_cmc_abduction_positive_drive_pulley'),
 ('thumb_cmc_negative_yaw_outlet_outer_jaw','thumb_cmc_flexion_negative_drive_pulley'),
 ('thumb_cmc_negative_yaw_outlet_structural_jaw_1','thumb_cmc_flexion_negative_drive_pulley'),
 ('thumb_cmc_positive_yaw_outlet_outer_jaw','thumb_cmc_flexion_positive_drive_pulley'),
 ('thumb_cmc_positive_yaw_outlet_structural_jaw_1','thumb_cmc_flexion_positive_drive_pulley'),
 ('thumb_mcp_ip_outlet_comb_scalloped_upper_jaw','thumb_metacarpal_frame'),
]

def overlaps(a,b):
    ba=a.bounding_box();bb=b.bounding_box()
    return all(getattr(ba.max,k)>=getattr(bb.min,k)-1e-7 and getattr(bb.max,k)>=getattr(ba.min,k)-1e-7 for k in ('X','Y','Z'))

def make_reliefs():
    from lib.phalanx_r5_boolean import common,cut
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib
    manifest_path=ROOT/'validation/anthropomorphic_hand/rigid_clearance_inputs.json'
    manifest=json.loads(manifest_path.read_text());step=Path(manifest['step'])
    assert hashlib.sha256(step.read_bytes()).hexdigest()==manifest['step_sha256']
    originals={s.label:s for s in leaves(read_step(step))};parts=dict(originals)
    records=manifest['bodies'];frames={n:r['frame'] for n,r in records.items()}
    jaw_path=ROOT/'STEP/anthropomorphic_hand/thumb_cmc_negative_jaw_repair_review.step'
    jaw_check_path=ROOT/'validation/anthropomorphic_hand/thumb_cmc_jaw_repair_local_check.json'
    jaw_check=json.loads(jaw_check_path.read_text())
    assert jaw_check['input_sha256'][str(jaw_path)]==hashlib.sha256(jaw_path.read_bytes()).hexdigest()
    assert all(r['pass_'] for r in jaw_check['bores'])
    assert all(r['pass_'] for r in jaw_check['pulley_contacts'] if '_abduction_' in r['body'])
    read_step(jaw_path)  # Declare the native model input before raw STEP reconstruction.
    jaw=bd.import_step(str(jaw_path));assert len(jaw.solids())==1
    jaw=jaw.solids()[0];jaw.label='thumb_cmc_negative_yaw_outlet_structural_jaw_1'
    originals[jaw.label]=jaw;parts[jaw.label]=jaw
    bank_path=ROOT/'STEP/anthropomorphic_hand/radial_bank_arm_repair_review.step'
    bank_check_path=ROOT/'validation/anthropomorphic_hand/radial_bank_arm_repair_local_check.json'
    bank_check=json.loads(bank_check_path.read_text());assert bank_check['pass']
    assert bank_check['input_sha256'][str(bank_path)]==hashlib.sha256(bank_path.read_bytes()).hexdigest()
    assert next(r for r in bank_check['remaining_interface_contacts'] if r['body']=='thumb_cmc_abduction_negative_drive_pulley')['intersection_mm3']<1e-7
    read_step(bank_path)
    bank=bd.import_step(str(bank_path));assert len(bank.solids())==1
    bank=bank.solids()[0];bank.label='thumb_radial_shared_guide_bank_structural'
    originals[bank.label]=bank;parts[bank.label]=bank
    samples_path=ROOT/'validation/anthropomorphic_hand/static_route_packet_manifest.json'
    samples=json.loads(samples_path.read_text())['rows']
    # The over-folded maximum-angle fist is retained as a rejected candidate;
    # every independent joint sample and the accepted pinch remain covered.
    samples=[s for s in samples if s['label']!='full_fist_candidate']
    inputs={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (manifest_path,step,samples_path,Path(__file__),jaw_path,jaw_check_path,bank_path,bank_check_path)}
    report={'pass':False,'scope':__doc__,'input_sha256':inputs,'preconstruction_replacements':{jaw.label:str(jaw_path),bank.label:str(bank_path)},'pairs':[]}
    out=ROOT/'validation/anthropomorphic_hand/static_clearance_relief_build.json'
    padded={}
    from lib.guide_mounts import guide_end_registry
    guide_ends=guide_end_registry()
    for target,obstacle in PAIRS:
        assert target in parts and obstacle in originals,(target,obstacle)
        source=parts[target];before=source.volume;seen=set();changes=[]
        for sample in samples:
            fk=assembled_transforms(sample['pose']);relative=np.linalg.inv(fk[frames[target]])@fk[frames[obstacle]]
            # Quantization is used only to avoid duplicate construction cuts,
            # never to certify clearance; all poses are checked independently.
            key=tuple(np.round(relative.ravel(),12))
            if key in seen:continue
            seen.add(key);tool=matrix_location(relative)*originals[obstacle]
            obstacle_at_pose=tool
            if not overlaps(source,tool):continue
            hit=common(source,tool)
            if not hit.solids() or hit.volume<=1e-7:continue
            if obstacle not in padded:
                try:
                    inflated=originals[obstacle].solids()[0].offset_3d([], .025,tolerance=1e-6)
                    assert len(inflated.solids())==1 and inflated.is_valid
                except Exception:
                    # Thin branched support solids need not admit a global
                    # OCCT offset. Machine a local rounded rectangular pocket
                    # around the exact contact instead of changing the guide.
                    inflated=None
                padded[obstacle]=inflated
            if padded[obstacle] is not None:
                tool=matrix_location(relative)*padded[obstacle]
                construction='offset_counterpart'
            else:
                bounds=Bnd_Box();BRepBndLib.AddOptimal_s(hit.wrapped,bounds,False,True)
                x0,y0,z0,x1,y1,z1=bounds.Get();d=.025
                tool=bd.Pos((x0+x1)/2,(y0+y1)/2,(z0+z1)/2)*bd.Box(x1-x0+2*d,y1-y0+2*d,z1-z0+2*d)
                tool=bd.fillet(tool.edges(),d*.99)
                construction='rounded_local_contact_pocket'
            if target=='palm_metacarpal_truss' and obstacle=='thumb_cmc_abduction_positive_bushing':
                # Preserve the complete 8.6..10.0 mm bearing seating annulus.
                tool=common(tool,bd.Pos(-35,36,8.6-25)*bd.Box(30,30,50))
            candidate=cut(source,tool)
            swarf=[]
            if (target,obstacle)==('palm_metacarpal_truss','thumb_cmc_negative_yaw_outlet_structural_jaw_1') and len(candidate.solids())==2:
                retained,chip=sorted(candidate.solids(),key=lambda s:s.volume,reverse=True)
                bb=chip.bounding_box();bounds=np.array([tuple(bb.min),tuple(bb.max)])
                # Only the two individually inspected offcuts are removable.
                # Both are >1.04 mm from every protected seating zone and
                # >4.35 mm from guide mouths. Any other fragment still fails.
                for suffix in ('','_2'):
                    evidence_path=ROOT/f'validation/anthropomorphic_hand/palm_clearance_fragment_inspection{suffix}.json'
                    evidence=json.loads(evidence_path.read_text())
                    assert evidence['protected_zones_clear'] and evidence['guide_mouths_clear']
                    assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in evidence['input_sha256'].items())
                    if abs(chip.volume-evidence['chip_mm3'])<1e-5 and np.max(np.abs(bounds-np.asarray(evidence['bounds_mm'])))<1e-5 and retained.volume>source.volume*.99:
                        swarf.append(dict(volume_mm3=chip.volume,bounds_mm=bounds.tolist(),inspection=str(evidence_path),inspection_sha256=hashlib.sha256(evidence_path.read_bytes()).hexdigest()))
                        inputs[str(evidence_path)]=hashlib.sha256(evidence_path.read_bytes()).hexdigest()
                        candidate=retained
                        break
            if (target,obstacle)==('thumb_radial_shared_guide_bank_structural','thumb_cmc_abduction_negative_bushing') and len(candidate.solids())==2:
                retained,chip=sorted(candidate.solids(),key=lambda s:s.volume,reverse=True)
                bb=chip.bounding_box();lo=np.array(tuple(bb.min));hi=np.array(tuple(bb.max))
                nearest=min(float(np.linalg.norm(np.maximum(np.maximum(lo-np.asarray(e.point),np.asarray(e.point)-hi),0.))) for e in guide_ends if e.frame==frames[target])
                # This inspected 0.005724 mm³ shaving is at the bushing relief,
                # >8 mm from every guide mouth. It is machining swarf, not an
                # independent support or an endpoint-bearing fragment.
                if chip.volume<=.006 and nearest>3. and retained.volume>source.volume*.95:
                    swarf.append(dict(volume_mm3=chip.volume,bounds_mm=[lo.tolist(),hi.tolist()],guide_endpoint_gap_lower_bound_mm=nearest))
                    candidate=retained
            if len(candidate.solids())!=1 or not candidate.is_valid or candidate.volume<=0:
                from cadgen.step_export import export_build123d_step_file
                diagnostic=[]
                for index,fragment in enumerate(sorted(candidate.solids(),key=lambda s:s.volume,reverse=True)):
                    fragment.label='retained_body' if index==0 else f'detached_fragment_{index}'
                    diagnostic.append(fragment)
                    print('REJECTED FRAGMENT',target,index,fragment.volume,str(fragment.bounding_box()),flush=True)
                export_build123d_step_file(bd.Compound(label='rejected_clearance_result',children=diagnostic),ROOT/f'STEP/anthropomorphic_hand/rejected_clearance_{target}.step')
                raise ValueError(('clearance disconnects support',target,obstacle,sample['label'],[s.volume for s in candidate.solids()]))
            followups=[]
            # A rounded pocket can leave a residual on a tangent curved edge
            # while returning a valid solid. A planar cleanup pocket avoids
            # repeating that same failing surface intersection. Its extent is
            # still just the exact residual bounds plus the design clearance.
            for attempt in range(3):
                remainder=common(candidate,obstacle_at_pose)
                if not remainder.solids() or remainder.volume<=1e-7:break
                bounds=Bnd_Box();BRepBndLib.AddOptimal_s(remainder.wrapped,bounds,False,True)
                x0,y0,z0,x1,y1,z1=bounds.Get();d=.025
                pocket=bd.Pos((x0+x1)/2,(y0+y1)/2,(z0+z1)/2)*bd.Box(x1-x0+2*d,y1-y0+2*d,z1-z0+2*d)
                if target=='palm_metacarpal_truss' and obstacle=='thumb_cmc_abduction_positive_bushing':
                    pocket=common(pocket,bd.Pos(-35,36,8.6-25)*bd.Box(30,30,50))
                corrected=cut(candidate,pocket)
                assert len(corrected.solids())==1 and corrected.is_valid and corrected.volume>0,('residual pocket disconnects support',target,obstacle,sample['label'])
                followups.append(dict(residual_contact_mm3=remainder.volume,bounds_mm=[x0,y0,z0,x1,y1,z1],clearance_mm=d,construction='planar_residual_cleanup'))
                candidate=corrected
            remainder=common(candidate,obstacle_at_pose)
            assert not remainder.solids() or remainder.volume<=1e-7,('unresolved post-cut contact',target,obstacle,sample['label'],remainder.volume)
            source=candidate.solids()[0]
            changes.append(dict(sample=sample['label'],removed_contact_mm3=hit.volume,pose=sample['pose'],construction=construction,discarded_machining_swarf=swarf,verified_residual_pockets=followups))
        source=finish(source,'aluminum',target);parts[target]=source
        row=dict(target=target,obstacle=obstacle,before_mm3=before,after_mm3=source.volume,removed_fraction=(before-source.volume)/before,clearance_mm=.025,changes=changes)
        report['pairs'].append(row);out.write_text(json.dumps(report,indent=2)+'\n');print('RELIEF',target,obstacle,len(changes),row['removed_fraction'],flush=True)
    targets=sorted({a for a,b in PAIRS})
    assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in inputs.items())
    report['pass']=True;report['body_frames']={n:frames[n] for n in targets};out.write_text(json.dumps(report,indent=2)+'\n')
    return [parts[n] for n in targets]
