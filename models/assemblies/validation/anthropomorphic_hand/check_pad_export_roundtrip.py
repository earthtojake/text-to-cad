"""Check the actual STEP pads against the authored contact envelope and mounts."""
import hashlib,itertools,json,math,sys
from pathlib import Path
import numpy as np
HERE=Path(__file__).resolve().parent
SOURCE=HERE.parents[1]/'src/anthropomorphic_hand'
sys.path.insert(0,str(SOURCE))
from cadgen import read_step
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps
from OCP.BRepCheck import BRepCheck_Shell,BRepCheck_NoError
from lib.fingertip_pad import PAD_RADII
from lib.native_integration import leaves
from lib.assembly import matrix_location
from lib.layout import assembled_transforms
from lib.phalanx_r5_boolean import common,cut
from check_native_reported_contacts import native_shapes

def volume(shape):
    props=GProp_GProps()
    error=BRepGProp.VolumeProperties_s(shape.wrapped,props,1e-10,True)
    return props.Mass(),error

def main():
    step=HERE.parents[1]/'STEP/anthropomorphic_hand/fingertip_pad_export_repair.step'
    native=native_shapes(step)
    authored={s.label:s for s in leaves(read_step(step))}
    metadata=HERE/'fingertip_pad_export_repair_frames.json'
    frames={r['name']:r['frame'] for r in json.loads(metadata.read_text())}
    assert set(native)==set(authored)==set(frames) and len(native)==30
    report={'pass':False,'scope':__doc__,'input_sha256':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (step,metadata,SOURCE/'lib/fingertip_pad.py',Path(__file__))},'bodies':[],'mounts':[]}
    for name,s in native.items():
        a=authored[name];av,ae=volume(a);nv,ne=volume(s)
        row=dict(name=name,authored_volume_mm3=av,native_volume_mm3=nv,integration_relative_error=max(ae,ne),single_closed_valid_solid=len(s.solids())==1 and len(s.shells())==1 and all(BRepCheck_Shell(sh.wrapped).Closed()==BRepCheck_NoError for sh in s.shells()) and s.is_valid and nv>0)
        row['roundtrip_volume_relative_difference']=abs(nv-av)/av
        row['roundtrip_geometry_equal']=row['roundtrip_volume_relative_difference']<1e-6
        if not row['roundtrip_geometry_equal']:
            # Rational trimmed faces can produce different quadrature mass
            # estimates after STEP splits their parametric intervals. Require
            # two empty native Boolean differences, not a looser mass limit.
            forward=cut(a,s);reverse=cut(s,a)
            row['symmetric_difference']={'source_minus_native_solids':len(forward.solids()),'native_minus_source_solids':len(reverse.solids()),'source_minus_native_faces':len(forward.faces()),'native_minus_source_faces':len(reverse.faces())}
            row['roundtrip_geometry_equal']=not forward.faces() and not reverse.faces()
        row['pass']=row['single_closed_valid_solid'] and row['roundtrip_geometry_equal']
        if name.endswith('silicone_pad'):
            rx,ry,rz=PAD_RADII[name.split('_')[0]];z0=(4.15-5.4)/rz
            expected=math.pi*rx*ry*rz*(2/3-z0+z0**3/3)
            row.update(analytic_pad_volume_mm3=expected,analytic_volume_relative_difference=abs(nv-expected)/expected,bond_plane_z_mm=s.bounding_box().min.Z,palmar_tip_z_mm=s.bounding_box().max.Z)
            row['pass'] &= row['analytic_volume_relative_difference']<1e-6 and abs(row['bond_plane_z_mm']-4.15)<1e-5 and abs(row['palmar_tip_z_mm']-7.4)<1e-5
        report['bodies'].append(row)
        print(json.dumps(row),flush=True)
    for finger in PAD_RADII:
        p=native[f'{finger}_fingertip_silicone_pad'];b=native[f'{finger}_fingertip_conformal_bridge']
        v=volume(common(p,b))[0];gap=p.distance_to(b)
        row=dict(system=finger,pad_bridge_gap_mm=gap,intersection_mm3=v,pass_=gap<1e-5 and v<1e-7)
        report['mounts'].append(row)
    pinch=HERE/'pinch_contact_candidate.json';report['input_sha256'][str(pinch)]=hashlib.sha256(pinch.read_bytes()).hexdigest()
    fk=assembled_transforms(json.loads(pinch.read_text())['pose'])
    pads=[matrix_location(fk[frames[f'{n}_fingertip_silicone_pad']])*native[f'{n}_fingertip_silicone_pad'] for n in ('index','thumb')]
    gap=pads[0].distance_to(pads[1]);v=volume(common(*pads))[0]
    report['pinch']=dict(gap_mm=gap,intersection_mm3=v,pass_=0<=gap<.001 and v<1e-7)
    report['pass']=all(r['pass'] for r in report['bodies']) and all(r['pass_'] for r in report['mounts']) and report['pinch']['pass_']
    (HERE/'fingertip_pad_export_roundtrip.json').write_text(json.dumps(report,indent=2)+'\n')
    print('RESULT',json.dumps(report['pinch']),report['pass'],flush=True)
    assert report['pass']

if __name__=='__main__':main()
