"""Material-only braid presentation; intentionally no final pose/explode clip."""
import sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'src/anthropomorphic_hand'))
from lib.neutral_routes import NEUTRAL_ROUTES
from lib.layout import TENDONS
root=Path(__file__).resolve().parents[2]
ropes=[{'name':r['name'],'normal':[t['sign'],0,0],'segments':r['path']} for r,t in zip(NEUTRAL_ROUTES,TENDONS)]
script='// Static surface presentation only; no joint choreography.\nconst ropes = '+json.dumps(ropes,separators=(',',':'))+';\n'
script+='export const clips={presentation:{label:"Braided surface study",duration:1,loop:false,update(t,m){for(const rope of ropes){const rest={normal:rope.normal,segments:rope.segments};m.get(rope.name).deformTube({rest,path:rest,maxSegmentLength:1000000,braid:{pitch:.8,depth:.022,strands:8}});}}}};\n'
(root/'STEP/anthropomorphic_hand/hand_progress_review.step.js').write_text(script)
jobfile=root/'src/anthropomorphic_hand/integrated_render_job.json';job=json.loads(jobfile.read_text());job['animation']={'clip':'presentation','time':0};jobfile.write_text(json.dumps(job,indent=2)+'\n')
print('Wrote48rope static presentation')
