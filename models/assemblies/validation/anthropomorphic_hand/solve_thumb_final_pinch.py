import sys,json
from pathlib import Path
sys.path.insert(0,'models/assemblies/src/anthropomorphic_hand')
from lib.thumb_cmc_transport import thumb_cmc_packet
root=Path('models/assemblies/validation/anthropomorphic_hand');whole=json.loads((root/'pinch_contact_candidate.json').read_text())['pose'];f=whole['thumb_cmc_flexion'];y=whole['thumb_cmc_abduction'];packet=thumb_cmc_packet(f,y);row={'flex':f,'yaw':y,'outlet_y':16.,'whole_pose':whole,'rows':[{'lane':r['lane'],'length':r['working_length'],'params':r['parameters'],'curves':[s['points'] for s in r['path']]} for r in packet]};(root/'thumb_cmc_final_pinch_packet.json').write_text(json.dumps([row],indent=2));print('SOLVED',f,y,flush=True)
