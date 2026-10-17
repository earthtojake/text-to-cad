from cadgen import step
from lib.assembly import Body,compound
from lib.native_integration import frozen_bodies
from lib.palette import ASSEMBLY_MATERIALS
from lib.braided_presentation import braided_presentation
from phalanx_beauty_review import replacements
from phalanx_continuous_representative_r5 import candidate_bodies
ANIMATION = braided_presentation()


@step(out='../STEP/phalanx_continuous_context_r5.step', animation=ANIMATION, materials=ASSEMBLY_MATERIALS)
def phalanx_continuous_context_r5():
    old=frozen_bodies();repl=replacements();new=candidate_bodies();repl.update({shape.label:shape for shape in new})
    prefixes=('middle_mcp_outlet_comb','middle_pip_inlet_comb','middle_pip_drive_guide')
    removed=[body for body in old if body.name=='middle_proximal_frame' or body.name.startswith(prefixes)]
    removed_names={body.name for body in removed}
    retained=[body for body in old if body.name not in removed_names]
    by_name={body.name:body for body in old}
    def metadata_for(shape):
        key=shape.label
        if key not in by_name:
            stem=key.rsplit('_',1)[0] if key.rsplit('_',1)[-1].isdigit() else key
            matches=sorted(name for name in by_name if name==stem or name.startswith(stem+'_'))
            assert matches,(key,'no corresponding original metadata');key=matches[0]
        return by_name[key]
    parts=[Body(repl.get(body.name,body.shape),body.frame,body.system,body.kind) for body in retained]
    parts.extend(Body(shape,metadata_for(shape).frame,metadata_for(shape).system,metadata_for(shape).kind) for shape in new)
    assert len(parts)==3151-len(removed)+len(new)
    return compound(parts,'continuous_skeletal_rail_in_complete_hand')
if __name__=='__main__':phalanx_continuous_context_r5()
