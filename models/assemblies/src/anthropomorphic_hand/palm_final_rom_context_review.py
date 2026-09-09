from pathlib import Path
from cadgen import step,read_step,build123d as bd
from lib.finish import finish

def leaves(s):return [p for c in s.children for p in leaves(c)] if s.children else [s]
@step(out='../../STEP/anthropomorphic_hand/palm_final_rom_context_review.step',mesh_tolerance=.006,mesh_angular_tolerance=.06)
def palm_final_rom_context_review():
    base=Path(__file__).resolve().parents[2]/'STEP/anthropomorphic_hand';parts=[]
    for file in ['palm_main_final_rom_review','palm_little_comb_rom_review','palm_cradle_clearance_review','palm_hardware_review','compact_cmc_yaw_review','positive_yaw_bushing_review']:
        for p in leaves(read_step(base/(file+'.step'))):
            language='pad' if p.label.endswith('silicone_pad') else 'dark' if p.label.endswith('carrier') else 'aluminum' if 'truss' in p.label or 'cradle' in p.label else 'steel'
            parts.append(finish(p,language,p.label))
    return bd.Compound(label='full_motion_palm_with_real_bearings_and_removable_pads',children=parts)
if __name__=='__main__':palm_final_rom_context_review()
