"""Replace the splice bank's drum-crossing rib while keeping every interface."""
import hashlib,json
from pathlib import Path
import numpy as np
from cadgen import step,read_step,build123d as bd
from lib.native_integration import ROOT,leaves
from lib.layout import THUMB_CMC
from lib.finish import finish

def split(cp,t):
    layers=[np.asarray(cp,float)]
    while len(layers[-1])>1:layers.append((1-t)*layers[-1][:-1]+t*layers[-1][1:])
    return np.array([r[0] for r in layers]),np.array([r[-1] for r in layers[::-1]])

def rib(cp,radius):
    edge=bd.Edge.make_bezier(*[tuple(p) for p in cp])
    return bd.sweep(bd.Plane(origin=edge.position_at(0),z_dir=edge.tangent_at(0))*bd.Circle(radius),path=edge)

def make_radial_bank_arm():
    from lib.phalanx_r5_boolean import cut
    source=ROOT/'STEP/anthropomorphic_hand/imported/rigid_clearance_inputs.step'
    read_step(source)  # Declare the native model dependency before reconstruction.
    parts={p.label:p for p in leaves(bd.import_step(str(source)))}
    name='thumb_radial_shared_guide_bank_structural';base=bd.Pos(*THUMB_CMC)*bd.Rot(0,0,45)
    body=parts[name];host=parts['palm_metacarpal_truss']
    old_path=Path(__file__).with_name('lib')/'remaining_support_paths.json'
    plan_path=ROOT/'validation/anthropomorphic_hand/radial_bank_arm_search.json'
    old=json.loads(old_path.read_text())['thumb_splice'];new=json.loads(plan_path.read_text())['candidate']
    assert new['root']==old['root'] and new['end']==old['end']
    cp=[old['root'],*old['controls'],old['end']]
    left,_=split(cp,.93);_,middle=split(left,.07/.93)
    stripped=cut(body,base*rib(middle,.275))
    replacement=base*rib([new['root'],*new['controls'],new['end']],.25)
    raw=stripped.fuse(replacement)
    result=cut(raw,host)
    print('REPAIRED BANK',[(s.volume,str(s.bounding_box())) for s in result.solids()],flush=True)
    assert len(result.solids())==1 and result.is_valid and result.volume>0
    result=finish(result.solids()[0],'aluminum',name)
    report={'scope':__doc__,'pass':True,'input_sha256':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (source,old_path,plan_path,Path(__file__))},'original_volume_mm3':body.volume,'repaired_volume_mm3':result.volume,'original_arm':old,'replacement_arm':new,'removed_original_parameter_interval':[.07,.93],'removal_radius_mm':.275,'rib_radius_mm':.25}
    (ROOT/'validation/anthropomorphic_hand/radial_bank_arm_repair_build.json').write_text(json.dumps(report,indent=2)+'\n')
    return result

@step(out='../../STEP/anthropomorphic_hand/radial_bank_arm_repair_review.step')
def radial_bank_arm_repair_review():
    return bd.Compound(label='continuous_radial_splice_bank',children=[make_radial_bank_arm()])

if __name__=='__main__':radial_bank_arm_repair_review()
