"""Local screw clearance in the rerouted splice bank, preserving its guide mouths."""
import hashlib,json
from pathlib import Path
from cadgen import build123d as bd,read_step,step
from lib.native_integration import ROOT,leaves
from lib.finish import finish

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

@step(out='../../STEP/anthropomorphic_hand/radial_bank_screw_clearance_candidate.step')
def radial_bank_screw_clearance_candidate():
    from lib.phalanx_r5_boolean import common,cut
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib
    name='thumb_radial_shared_guide_bank_structural';other='thumb_wrist_splice_outlet_comb_liner_-1_M0p6_screw'
    registry_path=ROOT/'validation/anthropomorphic_hand/final_rigid_delta_gate.json';registry=json.loads(registry_path.read_text())
    digest=registry['body_revisions'][other]['step_sha256'];screw_path=next(Path(p) for p,h in registry['input_sha256'].items() if p.endswith('.step') and h==digest)
    bank_path=ROOT/'STEP/anthropomorphic_hand/static_clearance_relief_review.step';assert sha(screw_path)==digest
    shapes={}
    for path,wanted in ((bank_path,name),(screw_path,other)):
        read_step(path)
        shapes.update({s.label:s for s in leaves(bd.import_step(str(path))) if s.label==wanted})
    assert set(shapes)=={name,other};body,obstacle=shapes[name],shapes[other]
    hit=common(body,obstacle);assert hit.solids() and hit.volume>1e-7
    box=Bnd_Box();BRepBndLib.AddOptimal_s(hit.wrapped,box,False,True);x0,y0,z0,x1,y1,z1=box.Get();d=.025
    pocket=bd.Pos((x0+x1)/2,(y0+y1)/2,(z0+z1)/2)*bd.Box(x1-x0+2*d,y1-y0+2*d,z1-z0+2*d)
    pocket=bd.fillet(pocket.edges(),d*.99);result=cut(body,pocket)
    assert len(result.solids())==1 and result.is_valid and result.volume>0
    remainder=common(result,obstacle);assert not remainder.solids() or remainder.volume<1e-7
    report=dict(scope=__doc__,input_sha256={str(p):sha(p) for p in (Path(__file__),registry_path,bank_path,screw_path)},original_contact_mm3=hit.volume,removed_material_mm3=body.volume-result.volume,pocket_bounds_mm=[x0,y0,z0,x1,y1,z1],clearance_mm=d,remaining_contact_mm3=remainder.volume if remainder.solids() else 0.,pass_=True)
    (ROOT/'validation/anthropomorphic_hand/radial_bank_screw_clearance_build.json').write_text(json.dumps(report,indent=2)+'\n')
    shape=finish(result.solids()[0],'aluminum',name)
    return bd.Compound(label='radial_bank_screw_clearance_candidate',children=[shape])
if __name__=='__main__':radial_bank_screw_clearance_candidate()
